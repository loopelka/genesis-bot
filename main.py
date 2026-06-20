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
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from handlers import all_routers

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

    # MemoryStorage is sufficient for single-process deployment on Replit.
    # For multi-process/horizontal scaling, switch to RedisStorage.
    storage = MemoryStorage()
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
