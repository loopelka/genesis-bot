"""
services/promocodes_service.py — Discount promo codes.

Source of truth: data/promocodes.json (in settings.data_dir).
Record keyed by uppercased code:
    {
      "code": "SALE10",
      "kind": "percent" | "fixed",
      "value": 10,                 # percent (0-100) or fixed amount in ₽
      "expires_at": 1750000000.0 | null,
      "usage_limit": 100 | null,
      "used_count": 0,
      "active": true
    }
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import List, Optional, Tuple

from config.settings import settings

logger = logging.getLogger(__name__)

PROMOCODES_FILE = settings.data_dir / "promocodes.json"

KIND_PERCENT = "percent"
KIND_FIXED = "fixed"


class PromoCodesService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._codes: dict = {}
        self._loaded = False

    # ── I/O ─────────────────────────────────────────────────────────────────────

    def _load_sync(self) -> None:
        if PROMOCODES_FILE.exists():
            try:
                data = json.loads(PROMOCODES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._codes = data
            except Exception as e:
                logger.warning("Could not load promocodes.json: %s", e)
                try:
                    backup = Path(f"{PROMOCODES_FILE}.corrupt.{int(time.time())}")
                    PROMOCODES_FILE.replace(backup)
                except Exception:
                    pass
                self._codes = {}
        else:
            self._codes = {}
        self._loaded = True

    def _save_sync(self) -> None:
        try:
            tmp = Path(f"{PROMOCODES_FILE}.tmp")
            tmp.write_text(json.dumps(self._codes, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, PROMOCODES_FILE)
        except Exception as e:
            logger.error("Could not save promocodes.json: %s", e)

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            await asyncio.get_event_loop().run_in_executor(None, self._load_sync)

    async def _save(self) -> None:
        await asyncio.get_event_loop().run_in_executor(None, self._save_sync)

    # ── Public API ──────────────────────────────────────────────────────────────

    async def create(
        self, code: str, kind: str, value: int,
        expires_at: Optional[float] = None, usage_limit: Optional[int] = None,
    ) -> bool:
        code = code.strip().upper()
        if not code or kind not in (KIND_PERCENT, KIND_FIXED):
            return False
        async with self._lock:
            await self._ensure_loaded()
            if code in self._codes:
                return False
            self._codes[code] = {
                "code": code, "kind": kind, "value": int(value),
                "expires_at": expires_at, "usage_limit": usage_limit,
                "used_count": 0, "active": True,
            }
            await self._save()
            return True

    async def disable(self, code: str) -> bool:
        code = code.strip().upper()
        async with self._lock:
            await self._ensure_loaded()
            rec = self._codes.get(code)
            if rec is None:
                return False
            rec["active"] = False
            await self._save()
            return True

    async def list_all(self) -> List[dict]:
        async with self._lock:
            await self._ensure_loaded()
            return [dict(v) for v in self._codes.values()]

    async def validate(self, code: str) -> Tuple[Optional[dict], str]:
        """Return (record, "") if usable, else (None, reason)."""
        code = code.strip().upper()
        async with self._lock:
            await self._ensure_loaded()
            rec = self._codes.get(code)
            if rec is None:
                return None, "Промокод не найден"
            if not rec.get("active", True):
                return None, "Промокод отключён"
            exp = rec.get("expires_at")
            if exp is not None and time.time() > exp:
                return None, "Срок действия промокода истёк"
            limit = rec.get("usage_limit")
            if limit is not None and rec.get("used_count", 0) >= limit:
                return None, "Лимит использования исчерпан"
            return dict(rec), ""

    @staticmethod
    def discount_for(rec: dict, total: int) -> int:
        """Compute the discount amount (₽) for a validated record and order total."""
        if rec["kind"] == KIND_PERCENT:
            return max(0, min(total, int(round(total * rec["value"] / 100.0))))
        return max(0, min(total, int(rec["value"])))

    async def redeem(self, code: str) -> bool:
        """Increment usage counter. Call only after a successful order."""
        code = code.strip().upper()
        async with self._lock:
            await self._ensure_loaded()
            rec = self._codes.get(code)
            if rec is None:
                return False
            rec["used_count"] = int(rec.get("used_count", 0)) + 1
            await self._save()
            return True


promocodes_service = PromoCodesService()
