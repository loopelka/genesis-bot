"""
config/settings.py — Central configuration for Genesis Peptide Store bot.
Reads from environment variables (and a local .env if present, for dev).
"""
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Load a local .env for development. On a platform that injects environment
# variables (e.g. JustRunMyApp), no .env exists and this is a harmless no-op —
# values are read straight from os.environ below.
load_dotenv()

logger = logging.getLogger(__name__)

# Runtime state files that hold customer PII / live session data. They live in
# DATA_DIR (see Settings.data_dir) so a persistent volume can back them on hosts
# with ephemeral filesystems (e.g. JustRunMyApp). Catalog files (products.xlsx,
# *_descriptions.json, related_products.json) are committed and read-only, so
# they are intentionally NOT in this list.
STATE_FILES = ("carts.json", "users.json", "orders.json", "fsm_state.json")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_id: int
    products_file: str        # путь до products.xlsx
    cache_ttl: int            # секунды жизни кэша товаров
    fsm_ttl: int              # макс. возраст незавершённой FSM-сессии (сек) до очистки
    fsm_cleanup_interval: int # период фоновой очистки FSM (сек); 0 = выключено
    data_dir: Path            # каталог для runtime-файлов состояния (том на проде)

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
        # Where runtime state files live. Default "." = project dir (unchanged
        # local/Replit behavior). On a host with an ephemeral filesystem, point
        # this at a persistent volume (e.g. DATA_DIR=/data).
        data_dir = Path(os.getenv("DATA_DIR", "."))
        data_dir.mkdir(parents=True, exist_ok=True)

        if not bot_token:
            raise ValueError("BOT_TOKEN environment variable is not set")
        if not admin_id_raw or admin_id_raw == "0":
            raise ValueError("ADMIN_ID environment variable is not set")

        return cls(
            bot_token=bot_token,
            admin_id=int(admin_id_raw),
            products_file=products_file,
            cache_ttl=cache_ttl,
            fsm_ttl=fsm_ttl,
            fsm_cleanup_interval=fsm_cleanup_interval,
            data_dir=data_dir,
        )


def migrate_legacy_data(data_dir: Path) -> None:
    """One-time, non-destructive migration of legacy root state files into DATA_DIR.

    When DATA_DIR points somewhere other than the project root, copy any state
    file that still lives in the root into DATA_DIR — but only if DATA_DIR does
    not already have its own copy. Existing DATA_DIR files are never overwritten,
    and legacy root files are left intact (copy, not move). Safe no-op when
    DATA_DIR is the project root.
    """
    if data_dir.resolve() == Path(".").resolve():
        return
    for name in STATE_FILES:
        legacy = Path(name)
        target = data_dir / name
        if legacy.exists() and not target.exists():
            try:
                shutil.copy2(legacy, target)
                logger.info("Migrated legacy %s -> %s", legacy, target)
            except Exception as e:
                logger.error("Could not migrate %s -> %s: %s", legacy, target, e)


settings = Settings.from_env()
