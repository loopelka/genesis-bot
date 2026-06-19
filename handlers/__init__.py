from aiogram import Dispatcher

def register_handlers(dp: Dispatcher):
    from handlers.start import router as start_router
    dp.include_router(start_router)
