"""
get_file_id.py — Standalone utility to obtain Telegram file_id for product photos.

Usage:
    1. Set BOT_TOKEN in .env
    2. Run: python get_file_id.py
    3. Send a photo to your bot in Telegram
    4. The script prints the file_id — copy it into products.xlsx column G

Stop with Ctrl+C.
"""
import asyncio
import logging
from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

async def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not set in .env")
        return

    from aiogram import Bot, Dispatcher, Router, F
    from aiogram.filters import CommandStart
    from aiogram.types import Message, PhotoSize
    from aiogram.fsm.storage.memory import MemoryStorage

    logging.basicConfig(level=logging.WARNING)
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message):
        await message.answer(
            "📸 Отправьте фото товара — я пришлю вам его file_id.\n"
            "Скопируйте file_id в столбец G файла products.xlsx."
        )

    @router.message(F.photo)
    async def get_photo_id(message: Message):
        photo: PhotoSize = message.photo[-1]
        file_id = photo.file_id
        print(f"\n📷 Получен file_id:\n{file_id}\n")
        await message.answer(
            f"✅ <b>file_id получен:</b>\n\n<code>{file_id}</code>\n\n"
            f"Скопируйте это значение в столбец <b>G (Фото)</b> файла products.xlsx.",
            parse_mode="HTML",
        )

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    print("=" * 60)
    print("  Genesis Peptide Store — File ID Utility")
    print("=" * 60)
    print("Отправьте фото товара боту в Telegram.")
    print("Нажмите Ctrl+C для выхода.\n")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nУтилита остановлена.")
