"""
services/cart_service.py — Persistent shopping cart storage.

Storage: carts.json in the project root.
Format: {str(user_id): {str(product_id): qty}}

Only product_id and qty are stored. All product details (name, price,
dosage, stock) are fetched from products_service at display/checkout
time to guarantee price and stock accuracy.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

CARTS_FILE = Path("carts.json")


class CartService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._carts: Dict[str, Dict[str, int]] = {}
        self._loaded = False

    # ── I/O ───────────────────────────────────────────────────────────────────

    def _load_sync(self) -> None:
        if CARTS_FILE.exists():
            try:
                data = json.loads(CARTS_FILE.read_text(encoding="utf-8"))
                self._carts = {
                    str(uid): {str(pid): int(qty) for pid, qty in items.items()}
                    for uid, items in data.items()
                }
            except Exception as e:
                logger.warning("Could not load carts.json: %s", e)
                self._carts = {}
        else:
            self._carts = {}
        self._loaded = True

    def _save_sync(self) -> None:
        try:
            CARTS_FILE.write_text(
                json.dumps(self._carts, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Could not save carts.json: %s", e)

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_sync)

    # ── Public API ────────────────────────────────────────────────────────────

    async def add_item(self, user_id: int, product_id: int) -> int:
        """Add product or increment qty by 1. Returns new qty."""
        async with self._lock:
            await self._ensure_loaded()
            uid, pid = str(user_id), str(product_id)
            if uid not in self._carts:
                self._carts[uid] = {}
            self._carts[uid][pid] = self._carts[uid].get(pid, 0) + 1
            qty = self._carts[uid][pid]
            await asyncio.get_event_loop().run_in_executor(None, self._save_sync)
            return qty

    async def increment(self, user_id: int, product_id: int) -> int:
        """Increment qty by 1. Returns new qty."""
        return await self.add_item(user_id, product_id)

    async def decrement(self, user_id: int, product_id: int) -> int:
        """Decrement qty by 1. Removes item when qty reaches 0. Returns new qty."""
        async with self._lock:
            await self._ensure_loaded()
            uid, pid = str(user_id), str(product_id)
            if uid not in self._carts or pid not in self._carts[uid]:
                return 0
            self._carts[uid][pid] -= 1
            qty = self._carts[uid][pid]
            if qty <= 0:
                del self._carts[uid][pid]
                if not self._carts[uid]:
                    del self._carts[uid]
                qty = 0
            await asyncio.get_event_loop().run_in_executor(None, self._save_sync)
            return qty

    async def remove_item(self, user_id: int, product_id: int) -> None:
        """Remove item completely from cart."""
        async with self._lock:
            await self._ensure_loaded()
            uid, pid = str(user_id), str(product_id)
            if uid in self._carts and pid in self._carts[uid]:
                del self._carts[uid][pid]
                if not self._carts[uid]:
                    del self._carts[uid]
            await asyncio.get_event_loop().run_in_executor(None, self._save_sync)

    async def clear(self, user_id: int) -> None:
        """Remove all items from user's cart."""
        async with self._lock:
            await self._ensure_loaded()
            uid = str(user_id)
            if uid in self._carts:
                del self._carts[uid]
            await asyncio.get_event_loop().run_in_executor(None, self._save_sync)

    async def get_items(self, user_id: int) -> Dict[int, int]:
        """Return {product_id: qty} for user's cart."""
        async with self._lock:
            await self._ensure_loaded()
            uid = str(user_id)
            if uid not in self._carts:
                return {}
            return {int(pid): qty for pid, qty in self._carts[uid].items()}

    async def is_empty(self, user_id: int) -> bool:
        items = await self.get_items(user_id)
        return len(items) == 0

    async def item_count(self, user_id: int) -> int:
        """Total qty across all items."""
        items = await self.get_items(user_id)
        return sum(items.values())


cart_service = CartService()
