"""
services/orders_service.py — Persistent order records.

Storage: orders.json in the project root.
Format: a JSON object keyed by order id (zero-padded string), e.g.
    {
      "000001": {
        "id": "000001",
        "created_at": "2026-06-22T13:21:00+00:00",
        "created_ts": 1750598460.0,
        "source": "cart" | "single",
        "status": "new" | "notified" | "notify_failed",
        "user_id": 123,
        "username": "ivan" | null,
        "customer_name": "...",
        "customer_contact": "...",
        "customer_country": "...",   # "" for the single-product flow
        "comment": "...",
        "items": [
            {"product_id": 1, "name": "...", "dosage": "...", "price": 0, "qty": 1}
        ],
        "total": 0
      }
    }

Design notes:
  • Mirrors the atomic-write + corrupt-backup pattern already used by
    cart_service and users_service (P0-4): temp file + os.replace, and a
    timestamped backup of any unreadable file instead of silent loss.
  • Orders are persisted BEFORE the admin notification is attempted, so a
    failed Telegram delivery never loses the order (see handlers/order.py and
    handlers/cart.py). Delivery outcome is recorded via mark_notified /
    mark_notify_failed.
  • orders.json contains customer PII and is therefore git-ignored, exactly
    like carts.json / users.json.
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ORDERS_FILE = Path("orders.json")

# Valid lifecycle states for an order.
STATUS_NEW = "new"                       # persisted, notification not yet attempted
STATUS_NOTIFIED = "notified"             # admin notification delivered
STATUS_NOTIFY_FAILED = "notify_failed"   # persisted but admin DM failed (recoverable)


class OrdersService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._orders: Dict[str, dict] = {}
        self._loaded = False

    # ── I/O ───────────────────────────────────────────────────────────────────

    def _load_sync(self) -> None:
        if ORDERS_FILE.exists():
            try:
                data = json.loads(ORDERS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._orders = {str(k): v for k, v in data.items()}
                else:
                    self._orders = {}
            except Exception as e:
                # Never silently discard data: back up the corrupt file so it
                # can be recovered, instead of overwriting it with {} on save.
                logger.warning("Could not load orders.json: %s", e)
                try:
                    backup = Path(f"{ORDERS_FILE}.corrupt.{int(time.time())}")
                    ORDERS_FILE.replace(backup)
                    logger.error("Backed up corrupt orders.json to %s", backup)
                except Exception as backup_err:
                    logger.error("Could not back up corrupt orders.json: %s", backup_err)
                self._orders = {}
        else:
            self._orders = {}
        self._loaded = True

    def _save_sync(self) -> None:
        # Atomic write: write to a temp file in the same dir, then os.replace.
        try:
            tmp = Path(f"{ORDERS_FILE}.tmp")
            tmp.write_text(
                json.dumps(self._orders, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, ORDERS_FILE)
        except Exception as e:
            logger.error("Could not save orders.json: %s", e)

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_sync)

    def _next_id(self) -> str:
        """Return the next monotonic, zero-padded order id as a string."""
        max_id = 0
        for key in self._orders:
            try:
                max_id = max(max_id, int(key))
            except (TypeError, ValueError):
                continue
        return f"{max_id + 1:06d}"

    # ── Public API ──────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        user_id: int,
        username: Optional[str],
        customer_name: str,
        customer_contact: str,
        items: List[dict],
        total: int,
        comment: str = "",
        customer_country: str = "",
        source: str = "single",
    ) -> str:
        """
        Persist a new order with status 'new' and return its id.

        `items` is a list of {product_id, name, dosage, price, qty} dicts — a
        price/name snapshot captured at order time so the record stays accurate
        even if the catalog later changes.
        """
        async with self._lock:
            await self._ensure_loaded()
            order_id = self._next_id()
            now = datetime.now(timezone.utc)
            self._orders[order_id] = {
                "id": order_id,
                "created_at": now.isoformat(),
                "created_ts": now.timestamp(),
                "source": source,
                "status": STATUS_NEW,
                "user_id": int(user_id),
                "username": username or None,
                "customer_name": customer_name,
                "customer_contact": customer_contact,
                "customer_country": customer_country or "",
                "comment": comment or "",
                "items": [
                    {
                        "product_id": int(it["product_id"]),
                        "name": str(it.get("name", "")),
                        "dosage": str(it.get("dosage", "")),
                        "price": int(it.get("price", 0)),
                        "qty": int(it.get("qty", 1)),
                    }
                    for it in items
                ],
                "total": int(total),
            }
            await asyncio.get_event_loop().run_in_executor(None, self._save_sync)
            logger.info(
                "Order persisted: id=%s source=%s user=%d items=%d total=%d",
                order_id, source, user_id, len(items), total,
            )
            return order_id

    async def set_status(self, order_id: str, status: str) -> None:
        """Update an order's status. No-op if the order id is unknown."""
        async with self._lock:
            await self._ensure_loaded()
            order = self._orders.get(str(order_id))
            if order is None:
                logger.warning("set_status: unknown order id %s", order_id)
                return
            order["status"] = status
            await asyncio.get_event_loop().run_in_executor(None, self._save_sync)

    async def mark_notified(self, order_id: str) -> None:
        """Mark that the admin notification for this order was delivered."""
        await self.set_status(order_id, STATUS_NOTIFIED)

    async def mark_notify_failed(self, order_id: str) -> None:
        """Mark that the admin notification failed — the order is kept for recovery."""
        await self.set_status(order_id, STATUS_NOTIFY_FAILED)

    async def get(self, order_id: str) -> Optional[dict]:
        async with self._lock:
            await self._ensure_loaded()
            order = self._orders.get(str(order_id))
            return dict(order) if order is not None else None

    async def get_all(self) -> List[dict]:
        """All orders, newest first."""
        async with self._lock:
            await self._ensure_loaded()
            return sorted(
                (dict(o) for o in self._orders.values()),
                key=lambda o: o.get("created_ts", 0),
                reverse=True,
            )

    async def count(self) -> int:
        async with self._lock:
            await self._ensure_loaded()
            return len(self._orders)


orders_service = OrdersService()
