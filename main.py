"""
main.py — Genesis Peptide Store Telegram Bot entry point.

Run with:
    python main.py

Or on Replit:
    Set the run command to: python main.py
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from handlers import all_routers
from services.fsm_storage import JsonFileStorage

# ── Logging setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

# Quieten noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ── Bot setup ─────────────────────────────────────────────────────────────────

async def main() -> None:
    logger.info("Starting Genesis Peptide Store bot...")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Load catalog data (descriptions + related products) at startup.
    # Safe no-op if a file is missing — cards degrade gracefully.
    from services.descriptions_service import descriptions_service
    from services.related_service import related_service
    from services import products_service
    descriptions_service.load()
    related_service.load()
    # Cross-check descriptions against the live catalog (47 drugs ↔ 104 SKU).
    _products = await products_service.get_all_products()
    descriptions_service.validate_names({p.name for p in _products})

    # Persistent FSM storage: active checkout sessions survive restarts
    # (Replit sleep/wake, redeploy, crash). Atomic writes to fsm_state.json.
    storage = JsonFileStorage()
    dp = Dispatcher(storage=storage)

    # Register all routers
    for router in all_routers:
        dp.include_router(router)

    # Startup log
    bot_info = await bot.get_me()
    logger.info(
        "Bot started: @%s (id=%d) | Admin: %d",
        bot_info.username, bot_info.id, settings.admin_id,
    )

    # Drop pending updates and start polling
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Bot stopped. Closing session...")
        await storage.close()
        await bot.session.close()


if __name__ == "__main__":
    from keep_alive import keep_alive
    keep_alive()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
        sys.exit(1)
