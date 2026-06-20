"""
handlers/start.py — /start command and main menu navigation.
"""
import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from keyboards import kb_main_menu
from utils.helpers import safe_edit_message

logger = logging.getLogger(__name__)
router = Router(name="start")

WELCOME_TEXT = (
    "👋 Добро пожаловать в <b>Genesis Peptide Store</b>!\n\n"
    "Мы предлагаем качественные пептиды для исследований.\n"
    "Быстрая доставка по всей России через СДЭК.\n\n"
    "Выберите раздел:"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start — clear any active FSM state and show main menu."""
    await state.clear()
    logger.info("User %d started the bot", message.from_user.id)
    await message.answer(
        text=WELCOME_TEXT,
        reply_markup=kb_main_menu(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Return to main menu from any callback."""
    await state.clear()
    await callback.answer()
    await safe_edit_message(
        message=callback.message,
        text=WELCOME_TEXT,
        reply_markup=kb_main_menu(),
    )


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    """Absorb no-op button clicks (pagination info, unavailable items)."""
    await callback.answer()
