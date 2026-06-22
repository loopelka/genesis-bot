"""
services/fsm_storage.py — Persistent JSON-backed FSM storage for aiogram 3.

Replaces MemoryStorage so that active checkout sessions survive bot restarts.

Storage layout (fsm_state.json):
  {
    "<bot_id>:<chat_id>:<user_id>:<destiny>": {
      "state": "OrderStates:waiting_name" | null,
      "data":  { ... }
    }
  }

Writes are atomic (temp-file + os.replace) — consistent with the P0-4 fix
applied to cart_service and users_service.
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType

logger = logging.getLogger(__name__)

FSM_FILE = Path("fsm_state.json")


def _key_str(key: StorageKey) -> str:
    """Serialize a StorageKey to a stable string for use as a JSON dict key."""
    return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.destiny}"


class JsonFileStorage(BaseStorage):
    """
    Simple single-file JSON storage for aiogram FSM state.

    Suitable for single-process, low-concurrency deployments (Replit, VPS).
    All reads and writes are protected by an asyncio.Lock so concurrent
    callbacks cannot race each other.
    """

    def __init__(self, path: Path = FSM_FILE) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    # ── I/O ───────────────────────────────────────────────────────────────────

    def _load_sync(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = raw
                else:
                    self._data = {}
            except Exception as exc:
                logger.warning("Could not load %s: %s — starting fresh", self._path, exc)
                self._data = {}
        else:
            self._data = {}
        self._loaded = True

    def _save_sync(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.error("Could not persist %s: %s", self._path, exc)
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_sync)

    async def _flush(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._save_sync)

    # ── BaseStorage interface ─────────────────────────────────────────────────

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        async with self._lock:
            await self._ensure_loaded()
            k = _key_str(key)
            if k not in self._data:
                self._data[k] = {"state": None, "data": {}}
            self._data[k]["state"] = state.state if state is not None else None
            # Prune fully-cleared entries to keep the file small
            if self._data[k]["state"] is None and not self._data[k]["data"]:
                del self._data[k]
            await self._flush()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        async with self._lock:
            await self._ensure_loaded()
            return self._data.get(_key_str(key), {}).get("state")

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        async with self._lock:
            await self._ensure_loaded()
            k = _key_str(key)
            if k not in self._data:
                self._data[k] = {"state": None, "data": {}}
            self._data[k]["data"] = data
            # Prune fully-cleared entries
            if self._data[k]["state"] is None and not self._data[k]["data"]:
                del self._data[k]
            await self._flush()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        async with self._lock:
            await self._ensure_loaded()
            return dict(self._data.get(_key_str(key), {}).get("data", {}))

    async def close(self) -> None:
        async with self._lock:
            if self._loaded:
                await self._flush()
