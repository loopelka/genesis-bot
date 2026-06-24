"""
services/categories_service.py — Admin-managed category list.

Source of truth: data/categories.json (in settings.data_dir). Seeded once from
the canonical ALL_CATEGORIES + CATEGORY_EMOJI and any categories already present
in products. Used by the Products admin for category pick/filter and by the
Categories admin for CRUD. The customer catalog navigation stays goal-based and
is NOT affected by this service.

Record: {"name": str, "emoji": str, "order": int}
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import List, Optional

from config.settings import settings
from services.models import ALL_CATEGORIES, CATEGORY_EMOJI

logger = logging.getLogger(__name__)

CATEGORIES_FILE = settings.data_dir / "categories.json"


class CategoriesService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._categories: List[dict] = []
        self._loaded = False

    # ── I/O ─────────────────────────────────────────────────────────────────────

    def _seed(self) -> List[dict]:
        seeded: List[dict] = []
        for i, name in enumerate(ALL_CATEGORIES):
            seeded.append({"name": name, "emoji": CATEGORY_EMOJI.get(name, "📦"), "order": i})
        return seeded

    def _load_sync(self) -> None:
        if CATEGORIES_FILE.exists():
            try:
                data = json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))
                self._categories = [
                    {"name": str(c["name"]), "emoji": str(c.get("emoji", "📦")),
                     "order": int(c.get("order", i))}
                    for i, c in enumerate(data)
                ]
            except Exception as e:
                logger.warning("Could not load categories.json: %s", e)
                try:
                    backup = Path(f"{CATEGORIES_FILE}.corrupt.{int(time.time())}")
                    CATEGORIES_FILE.replace(backup)
                except Exception:
                    pass
                self._categories = self._seed()
                self._save_sync()
        else:
            self._categories = self._seed()
            self._save_sync()
        self._categories.sort(key=lambda c: c["order"])
        self._loaded = True

    def _save_sync(self) -> None:
        try:
            for i, c in enumerate(self._categories):
                c["order"] = i
            tmp = Path(f"{CATEGORIES_FILE}.tmp")
            tmp.write_text(
                json.dumps(self._categories, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, CATEGORIES_FILE)
        except Exception as e:
            logger.error("Could not save categories.json: %s", e)

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            await asyncio.get_event_loop().run_in_executor(None, self._load_sync)

    async def _save(self) -> None:
        await asyncio.get_event_loop().run_in_executor(None, self._save_sync)

    # ── Public API ──────────────────────────────────────────────────────────────

    async def get_all(self) -> List[dict]:
        async with self._lock:
            await self._ensure_loaded()
            return [dict(c) for c in self._categories]

    async def names(self) -> List[str]:
        async with self._lock:
            await self._ensure_loaded()
            return [c["name"] for c in self._categories]

    def emoji_for(self, name: str) -> str:
        for c in self._categories:
            if c["name"] == name:
                return c["emoji"]
        return CATEGORY_EMOJI.get(name, "📦")

    async def create(self, name: str, emoji: str = "📦") -> bool:
        name = name.strip()
        async with self._lock:
            await self._ensure_loaded()
            if not name or any(c["name"].lower() == name.lower() for c in self._categories):
                return False
            self._categories.append({"name": name, "emoji": emoji, "order": len(self._categories)})
            await self._save()
            return True

    async def rename(self, old: str, new: str) -> bool:
        new = new.strip()
        async with self._lock:
            await self._ensure_loaded()
            if not new or any(c["name"].lower() == new.lower() for c in self._categories):
                return False
            for c in self._categories:
                if c["name"] == old:
                    c["name"] = new
                    await self._save()
                    return True
            return False

    async def delete(self, name: str) -> bool:
        async with self._lock:
            await self._ensure_loaded()
            before = len(self._categories)
            self._categories = [c for c in self._categories if c["name"] != name]
            if len(self._categories) != before:
                await self._save()
                return True
            return False

    async def move(self, name: str, direction: int) -> bool:
        """Reorder: direction -1 = up, +1 = down."""
        async with self._lock:
            await self._ensure_loaded()
            idx = next((i for i, c in enumerate(self._categories) if c["name"] == name), None)
            if idx is None:
                return False
            new_idx = idx + direction
            if not (0 <= new_idx < len(self._categories)):
                return False
            self._categories[idx], self._categories[new_idx] = (
                self._categories[new_idx], self._categories[idx],
            )
            await self._save()
            return True


categories_service = CategoriesService()
