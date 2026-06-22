"""
services/users_service.py — Persistent user registry for broadcast and analytics.

Storage: JSON file (users.json) in the project root.
Thread-safe for single-process Replit deployment.

Public interface:
    users_service.register(user_id, username)
    users_service.get_all_user_ids() -> List[int]
    users_service.count() -> int
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import List, Optional

from config import settings

logger = logging.getLogger(__name__)

USERS_FILE = settings.data_dir / "users.json"


class UsersService:
    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        self._users: dict[int, dict] = {}
        self._loaded = False

    # ── Internal I/O ─────────────────────────────────────────────────────────

    def _load_sync(self) -> None:
        if USERS_FILE.exists():
            try:
                data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
                self._users = {int(k): v for k, v in data.items()}
            except Exception as e:
                # Never silently discard data: back up the corrupt file so it
                # can be recovered, instead of overwriting it with {} on save.
                logger.warning("Could not load users.json: %s", e)
                try:
                    backup = Path(f"{USERS_FILE}.corrupt.{int(time.time())}")
                    USERS_FILE.replace(backup)
                    logger.error("Backed up corrupt users.json to %s", backup)
                except Exception as backup_err:
                    logger.error("Could not back up corrupt users.json: %s", backup_err)
                self._users = {}
        else:
            self._users = {}
        self._loaded = True

    def _save_sync(self) -> None:
        # Atomic write: write to a temp file in the same dir, then os.replace.
        try:
            tmp = Path(f"{USERS_FILE}.tmp")
            tmp.write_text(
                json.dumps(self._users, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, USERS_FILE)
        except Exception as e:
            logger.error("Could not save users.json: %s", e)

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_sync)

    # ── Public API ────────────────────────────────────────────────────────────

    async def register(self, user_id: int, username: Optional[str] = None) -> bool:
        """
        Register a user. Returns True if the user is new, False if already known.
        """
        async with self._lock:
            await self._ensure_loaded()
            is_new = user_id not in self._users
            self._users[user_id] = {"username": username or ""}
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._save_sync)
            if is_new:
                logger.info("New user registered: %d (@%s)", user_id, username or "—")
            return is_new

    async def get_all_user_ids(self) -> List[int]:
        async with self._lock:
            await self._ensure_loaded()
            return list(self._users.keys())

    async def count(self) -> int:
        async with self._lock:
            await self._ensure_loaded()
            return len(self._users)


users_service = UsersService()
