"""
handlers/faq.py — FAQ section with interactive per-question navigation.
"""
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

from config.faq import FAQ_ENTRIES
from keyboards import kb_faq_list, kb_faq_back
from utils.helpers import safe_edit_message

logger = logging.getLogger(__name__)
router = Router(name="faq")

FAQ_MENU_TEXT = (
    "❓ <b>Часто задаваемые вопросы</b>\n\n"
    "Выберите вопрос, чтобы увидеть ответ:"
)


@router.callback_query(F.data == "menu:faq")
async def cb_faq_menu(callback: CallbackQuery) -> None:
    """Show FAQ question list."""
    await callback.answer()
    await safe_edit_message(
        message=callback.message,
        text=FAQ_MENU_TEXT,
        reply_markup=kb_faq_list(len(FAQ_ENTRIES)),
    )


@router.callback_query(F.data.startswith("faq:"))
async def cb_faq_entry(callback: CallbackQuery) -> None:
    """Show a specific FAQ entry."""
    await callback.answer()
    try:
        index = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    if index < 0 or index >= len(FAQ_ENTRIES):
        await callback.answer("❌ Вопрос не найден", show_alert=True)
        return

    entry = FAQ_ENTRIES[index]
    text = (
        f"❓ <b>Вопрос {index + 1} из {len(FAQ_ENTRIES)}</b>\n\n"
        f"<b>{entry.question}</b>\n\n"
        f"{entry.answer}"
    )

    await safe_edit_message(
        message=callback.message,
        text=text,
        reply_markup=kb_faq_back(),
    )
