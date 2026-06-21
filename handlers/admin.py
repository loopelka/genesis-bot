"""
handlers/admin.py — Admin panel for Genesis Peptide Store.

Commands (admin only):
    /admin    — show admin menu
    /stats    — user count and product count
    /broadcast — start broadcast flow (FSM)

Sections (scalable):
    📨 Рассылка
    📦 Заказы      (future)
    👥 Пользователи
    📊 Статистика
"""
import asyncio
import logging
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from config import settings
from services import products_service
from services.users_service import users_service

logger = logging.getLogger(__name__)
router = Router(name="admin")


# ── Admin filter ──────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id == settings.admin_id


# ── FSM states ────────────────────────────────────────────────────────────────

class BroadcastStates(StatesGroup):
    waiting_message = State()
    confirming      = State()


# ── Admin menu keyboard ───────────────────────────────────────────────────────

def kb_admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📨 Рассылка",       callback_data="admin:broadcast")
    builder.button(text="👥 Пользователи",   callback_data="admin:users")
    builder.button(text="📊 Статистика",     callback_data="admin:stats")
    builder.button(text="📦 Заказы (скоро)", callback_data="noop")
    builder.adjust(1)
    return builder.as_markup()


# ── /admin command ────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    user_count    = await users_service.count()
    product_count = len(await products_service.get_all_products())
    await message.answer(
        f"🔧 <b>Панель администратора</b>\n\n"
        f"👥 Пользователей: <b>{user_count}</b>\n"
        f"📦 Товаров в каталоге: <b>{product_count}</b>\n\n"
        f"Выберите действие:",
        reply_markup=kb_admin_menu(),
    )


# ── Stats callback ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.answer()
    user_count    = await users_service.count()
    product_count = len(await products_service.get_all_products())
    await callback.message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей зарегистрировано: <b>{user_count}</b>\n"
        f"📦 Товаров в каталоге: <b>{product_count}</b>",
    )


# ── Users callback ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:users")
async def cb_admin_users(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.answer()
    count = await users_service.count()
    await callback.message.answer(
        f"👥 <b>Пользователи</b>\n\n"
        f"Всего зарегистрировано: <b>{count}</b> чел.\n\n"
        f"Для детального просмотра используйте /admin."
    )


# ── Broadcast: start ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.answer()
    count = await users_service.count()
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin:broadcast_cancel")
    await state.set_state(BroadcastStates.waiting_message)
    await callback.message.answer(
        f"📨 <b>Рассылка</b>\n\n"
        f"Получателей: <b>{count}</b>\n\n"
        f"Отправьте текст или фото с подписью для рассылки.\n"
        f"Поддерживается HTML-разметка.",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "admin:broadcast_cancel")
async def cb_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.answer("Рассылка отменена")
    await callback.message.edit_text("❌ Рассылка отменена.")


# ── Broadcast: receive message ────────────────────────────────────────────────

@router.message(BroadcastStates.waiting_message)
async def msg_broadcast_input(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return

    # Save message details for confirmation
    if message.photo:
        await state.update_data(
            bcast_type="photo",
            bcast_photo=message.photo[-1].file_id,
            bcast_caption=message.caption or "",
        )
    elif message.text:
        await state.update_data(
            bcast_type="text",
            bcast_text=message.text,
        )
    else:
        await message.answer("⚠️ Поддерживаются только текст и фото. Попробуйте ещё раз.")
        return

    await state.set_state(BroadcastStates.confirming)

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить всем",   callback_data="admin:broadcast_confirm")
    builder.button(text="❌ Отменить",         callback_data="admin:broadcast_cancel")
    builder.adjust(1)

    count = await users_service.count()
    await message.answer(
        f"📋 <b>Подтверждение рассылки</b>\n\n"
        f"Получателей: <b>{count}</b>\n\n"
        f"Отправить сообщение выше всем пользователям?",
        reply_markup=builder.as_markup(),
    )


# ── Broadcast: confirm and send ───────────────────────────────────────────────

@router.callback_query(F.data == "admin:broadcast_confirm")
async def cb_broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    data = await state.get_data()
    await state.clear()
    await callback.answer()

    user_ids = await users_service.get_all_user_ids()
    if not user_ids:
        await callback.message.answer("⚠️ Список пользователей пуст.")
        return

    await callback.message.edit_text(
        f"📤 Начинаю рассылку для {len(user_ids)} пользователей..."
    )

    ok_count   = 0
    fail_count = 0
    bcast_type = data.get("bcast_type", "text")

    for uid in user_ids:
        try:
            if bcast_type == "photo":
                await bot.send_photo(
                    chat_id=uid,
                    photo=data["bcast_photo"],
                    caption=data.get("bcast_caption", ""),
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(
                    chat_id=uid,
                    text=data["bcast_text"],
                    parse_mode="HTML",
                )
            ok_count += 1
        except Exception as e:
            fail_count += 1
            logger.warning("Broadcast failed for user %d: %s", uid, e)
        await asyncio.sleep(0.05)   # Telegram rate limit: ~20 msg/s

    logger.info("Broadcast done: ok=%d fail=%d", ok_count, fail_count)
    await callback.message.answer(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"Доставлено: <b>{ok_count}</b>\n"
        f"Ошибок: <b>{fail_count}</b>"
    )
