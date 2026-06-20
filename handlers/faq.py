"""
handlers/faq.py — FAQ section: single formatted page with all Q&A visible.
"""
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

from config.faq import FAQ_ENTRIES
from keyboards import kb_faq_back
from utils.helpers import safe_edit_message

logger = logging.getLogger(__name__)
router = Router(name="faq")


def _build_faq_text() -> str:
    lines = ["❓ <b>Часто задаваемые вопросы</b>\n"]
    for i, entry in enumerate(FAQ_ENTRIES, start=1):
        lines.append(f"<b>{i}. {entry.question}</b>")
        lines.append(entry.answer)
        lines.append("")
    lines.append("📞 Остались вопросы? Пишите: @Ten_genesis")
    return "\n".join(lines)


FAQ_TEXT = _build_faq_text()


@router.callback_query(F.data == "menu:faq")
async def cb_faq_menu(callback: CallbackQuery) -> None:
    """Show full FAQ page with all answers."""
    await callback.answer()

    text = FAQ_TEXT
    if len(text) > 4000:
        text = text[:3990] + "\n\n…(продолжение у менеджера: @Ten_genesis)"

    await safe_edit_message(
        message=callback.message,
        text=text,
        reply_markup=kb_faq_back(),
    )
