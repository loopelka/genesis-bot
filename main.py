import asyncio
from aiogram import Bot, Dispatcher
from config.settings import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def main():
    from handlers import register_handlers
    register_handlers(dp)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
