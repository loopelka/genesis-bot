"""
services/store_settings_service.py — Admin-editable store texts.

Source of truth: data/settings.json (in settings.data_dir). Any key not present
falls back to the original hardcoded default below, so customer-facing text is
byte-identical until the owner edits it from Telegram.

Keys: welcome, main_menu, delivery, payment, faq, manager_contacts, promotions
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict

from config.settings import settings

logger = logging.getLogger(__name__)

STORE_SETTINGS_FILE = settings.data_dir / "settings.json"

# Human-readable labels for the admin editor.
EDITABLE_KEYS = {
    "welcome":          "Приветствие (/start)",
    "main_menu":        "Текст главного меню",
    "delivery":         "Доставка",
    "payment":          "Оплата",
    "faq":              "FAQ",
    "manager_contacts": "Контакты менеджера",
    "promotions":       "Акции",
}


class StoreSettingsService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._data: Dict[str, str] = {}
        self._defaults: Dict[str, str] = {}
        self._loaded = False

    def register_defaults(self, defaults: Dict[str, str]) -> None:
        """Called once at import time by callers to register fallback text."""
        self._defaults.update({k: v for k, v in defaults.items() if k not in self._defaults})

    # ── I/O ─────────────────────────────────────────────────────────────────────

    def _load_sync(self) -> None:
        if STORE_SETTINGS_FILE.exists():
            try:
                data = json.loads(STORE_SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._data = {str(k): str(v) for k, v in data.items()}
            except Exception as e:
                logger.warning("Could not load settings.json: %s", e)
                self._data = {}
        else:
            self._data = {}
        self._loaded = True

    def _save_sync(self) -> None:
        try:
            tmp = Path(f"{STORE_SETTINGS_FILE}.tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, STORE_SETTINGS_FILE)
        except Exception as e:
            logger.error("Could not save settings.json: %s", e)

    def _ensure_loaded_sync(self) -> None:
        if not self._loaded:
            self._load_sync()

    # ── Public API ──────────────────────────────────────────────────────────────

    def get(self, key: str) -> str:
        """Synchronous read with default fallback (used by message handlers)."""
        self._ensure_loaded_sync()
        if key in self._data and self._data[key]:
            return self._data[key]
        return self._defaults.get(key, "")

    async def set(self, key: str, value: str) -> None:
        async with self._lock:
            self._ensure_loaded_sync()
            self._data[key] = value
            await asyncio.get_event_loop().run_in_executor(None, self._save_sync)
            logger.info("Store setting updated: %s", key)


store_settings_service = StoreSettingsService()
