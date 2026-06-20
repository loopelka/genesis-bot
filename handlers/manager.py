"""
handlers/manager.py — Free-form message forwarding to admin.

Flow:
  [📞 Менеджер] → user types message → bot forwards to ADMIN_ID
"""
import logging

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import settings
from keyboards import kb_cancel_manager, kb_back_to_main, kb_main_menu
from utils import ManagerStates
from utils.helpers import safe_send_message, safe_edit_message

logger = logging.getLogger(__name__)
router = Router(name="manager")

MANAGER_INTRO_TEXT = (
    "📞 <b>Связь с менеджером</b>\n\n"
    "Напишите ваш вопрос или сообщение ниже.\n"
    "Менеджер ответит вам в ближайшее время."
)


@router.callback_query(F.data == "menu:manager")
async def cb_manager_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt user to write a message for the manager."""
    await callback.answer()
    await state.set_state(ManagerStates.waiting_message)
    await safe_edit_message(
        message=callback.message,
        text=MANAGER_INTRO_TEXT,
        reply_markup=kb_cancel_manager(),
    )


@router.message(ManagerStates.waiting_message, F.text)
async def msg_receive_manager_message(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    """Forward user's message to admin with sender info."""
    user = message.from_user
    username_line = f"@{user.username}" if user.username else "нет username"
    full_name = user.full_name or "Без имени"

    admin_text = (
        f"📞 <b>СООБЩЕНИЕ МЕНЕДЖЕРУ</b>\n\n"
        f"👤 От: {full_name}\n"
        f"🔗 Telegram: {username_line}\n"
        f"🆔 ID: <code>{user.id}</code>\n\n"
        f"💬 Сообщение:\n{message.text}"
    )

    admin_sent = await safe_send_message(
        bot=bot,
        chat_id=settings.admin_id,
        text=admin_text,
    )

    await state.clear()

    if admin_sent:
        logger.info("Manager message forwarded from user %d", user.id)
        await message.answer(
            text=(
                "✅ <b>Сообщение отправлено!</b>\n\n"
                "Менеджер свяжется с вами в ближайшее время."
            ),
            reply_markup=kb_back_to_main(),
            parse_mode="HTML",
        )
    else:
        logger.error("Failed to forward manager message from user %d", user.id)
        await message.answer(
            text=(
                "❌ Не удалось отправить сообщение. Попробуйте позже.\n"
                "Или напишите напрямую: @your_manager_username"
            ),
            reply_markup=kb_back_to_main(),
            parse_mode="HTML",
        )
