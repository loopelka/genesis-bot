"""
config/settings.py — Central configuration for Genesis Peptide Store bot.
Loads from .env and provides typed access to all settings.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_id: int
    products_file: str        # путь до products.xlsx
    cache_ttl: int            # секунды жизни кэша товаров
    fsm_ttl: int              # макс. возраст незавершённой FSM-сессии (сек) до очистки
    fsm_cleanup_interval: int # период фоновой очистки FSM (сек); 0 = выключено

    @classmethod
    def from_env(cls) -> "Settings":
        bot_token = os.getenv("BOT_TOKEN", "")
        admin_id_raw = os.getenv("ADMIN_ID", "0")
        products_file = os.getenv("PRODUCTS_FILE", "products.xlsx")
        cache_ttl = int(os.getenv("CACHE_TTL", "300"))
        # Abandoned checkouts retain customer PII in fsm_state.json until /start
        # or completion. Cap that retention: prune sessions idle longer than
        # FSM_TTL (default 24h), swept every FSM_CLEANUP_INTERVAL (default 1h).
        fsm_ttl = int(os.getenv("FSM_TTL", "86400"))
        fsm_cleanup_interval = int(os.getenv("FSM_CLEANUP_INTERVAL", "3600"))

        if not bot_token:
            raise ValueError("BOT_TOKEN is not set in .env")
        if not admin_id_raw or admin_id_raw == "0":
            raise ValueError("ADMIN_ID is not set in .env")

        return cls(
            bot_token=bot_token,
            admin_id=int(admin_id_raw),
            products_file=products_file,
            cache_ttl=cache_ttl,
            fsm_ttl=fsm_ttl,
            fsm_cleanup_interval=fsm_cleanup_interval,
        )


settings = Settings.from_env()
