"""
handlers/order.py — Multi-step order flow using FSM.

Flow:
  [🛒 Заказать] → ask name → ask contact → ask comment → confirm → notify admin
"""
import logging
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import settings
from keyboards import kb_cancel_order, kb_order_confirm, kb_back_to_main, kb_main_menu
from services import products_service, orders_service
from services.models import OrderForm
from utils import OrderStates
from utils.helpers import safe_send_message, safe_edit_message

logger = logging.getLogger(__name__)
router = Router(name="order")

# ── Step 1: Start order ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("order:") & ~F.data.startswith("order:confirm")
                       & ~F.data.startswith("order:edit") & (F.data != "order:cancel"))
async def cb_start_order(callback: CallbackQuery, state: FSMContext) -> None:
    """Triggered by 'order:<product_id>' — begin the order flow."""
    await callback.answer()

    try:
        product_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка: некорректный ID товара", show_alert=True)
        return

    product = await products_service.get_product_by_id(product_id)
    if product is None:
        await callback.answer("❌ Товар не найден", show_alert=True)
        return

    if not product.in_stock:
        await callback.answer("❌ Товар закончился", show_alert=True)
        return

    # Save minimal order data in FSM storage
    await state.set_state(OrderStates.waiting_name)
    await state.update_data(
        product_id=product.product_id,
        product_name=product.name,
        user_id=callback.from_user.id,
        username=callback.from_user.username,
    )

    await safe_edit_message(
        message=callback.message,
        text=(
            f"🛒 <b>Оформление заказа</b>\n\n"
            f"Товар: <b>{product.name}</b> {product.dosage}\n"
            f"Цена: {product.price_formatted}\n\n"
            f"<b>Шаг 1/3</b> — Как вас зовут?\n"
            f"Введите ваше имя:"
        ),
        reply_markup=kb_cancel_order(),
    )


# ── Step 2: Receive name ──────────────────────────────────────────────────────

@router.message(OrderStates.waiting_name, F.text)
async def msg_receive_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer(
            "⚠️ Имя слишком короткое. Введите ваше настоящее имя:",
            reply_markup=kb_cancel_order(),
            parse_mode="HTML",
        )
        return

    await state.update_data(customer_name=name)
    await state.set_state(OrderStates.waiting_contact)

    await message.answer(
        text=(
            f"✅ Имя: <b>{name}</b>\n\n"
            f"<b>Шаг 2/3</b> — Как с вами связаться?\n"
            f"Введите ваш Telegram или номер телефона:"
        ),
        reply_markup=kb_cancel_order(),
        parse_mode="HTML",
    )


# ── Step 3: Receive contact ───────────────────────────────────────────────────

@router.message(OrderStates.waiting_contact, F.text)
async def msg_receive_contact(message: Message, state: FSMContext) -> None:
    contact = message.text.strip()
    if len(contact) < 3:
        await message.answer(
            "⚠️ Контакт слишком короткий. Введите Telegram или номер:",
            reply_markup=kb_cancel_order(),
            parse_mode="HTML",
        )
        return

    await state.update_data(customer_contact=contact)
    await state.set_state(OrderStates.waiting_comment)

    await message.answer(
        text=(
            f"✅ Контакт: <b>{contact}</b>\n\n"
            f"<b>Шаг 3/3</b> — Дополнительный комментарий\n"
            f"Введите комментарий к заказу или отправьте <code>-</code> чтобы пропустить:"
        ),
        reply_markup=kb_cancel_order(),
        parse_mode="HTML",
    )


# ── Step 4: Receive comment → show confirmation ───────────────────────────────

@router.message(OrderStates.waiting_comment, F.text)
async def msg_receive_comment(message: Message, state: FSMContext) -> None:
    comment = message.text.strip()
    if comment == "-":
        comment = ""

    await state.update_data(comment=comment)
    await state.set_state(OrderStates.confirming)

    data = await state.get_data()
    order = OrderForm(
        product_id=data["product_id"],
        product_name=data["product_name"],
        user_id=data["user_id"],
        username=data.get("username"),
        customer_name=data["customer_name"],
        customer_contact=data["customer_contact"],
        comment=comment,
    )

    confirm_text = (
        f"📋 <b>Проверьте данные заказа:</b>\n\n"
        f"📦 Товар: <b>{order.product_name}</b>\n"
        f"👤 Имя: {order.customer_name}\n"
        f"📬 Контакт: {order.customer_contact}\n"
        f"💬 Комментарий: {order.comment or '—'}\n\n"
        f"Всё верно?"
    )

    await message.answer(
        text=confirm_text,
        reply_markup=kb_order_confirm(data["product_id"]),
        parse_mode="HTML",
    )


# ── Confirm → notify admin ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("order:confirm:"))
async def cb_confirm_order(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """User confirmed — send notification to admin and thank user."""
    await callback.answer()
    data = await state.get_data()

    if not data:
        await safe_edit_message(
            message=callback.message,
            text="❌ Сессия истекла. Пожалуйста, начните заказ заново.",
            reply_markup=kb_back_to_main(),
        )
        return

    order = OrderForm(
        product_id=data["product_id"],
        product_name=data["product_name"],
        user_id=data["user_id"],
        username=data.get("username"),
        customer_name=data["customer_name"],
        customer_contact=data["customer_contact"],
        comment=data.get("comment", ""),
    )

    # Persist the order BEFORE notifying the admin, so a failed Telegram
    # delivery never loses it (P0-1/P0-2). Idempotent across retries: the id is
    # stored in FSM state, so pressing "confirm" again re-sends without
    # creating a duplicate record.
    order_id = data.get("order_id")
    if not order_id:
        product = await products_service.get_product_by_id(data["product_id"])
        item = {
            "product_id": data["product_id"],
            "name": data["product_name"],
            "dosage": product.dosage if product else "",
            "price": product.price if product else 0,
            "qty": 1,
        }
        total = product.price if product else 0
        order_id = await orders_service.create(
            user_id=data["user_id"],
            username=data.get("username"),
            customer_name=data["customer_name"],
            customer_contact=data["customer_contact"],
            items=[item],
            total=total,
            comment=data.get("comment", ""),
            source="single",
        )
        await state.update_data(order_id=order_id)

    # Notify admin
    admin_sent = await safe_send_message(
        bot=bot,
        chat_id=settings.admin_id,
        text=order.admin_notification(),
    )
    if not admin_sent:
        # Order is already persisted; record the failed delivery and keep state
        # (with order_id) so the user can retry without duplicating the order.
        await orders_service.mark_notify_failed(order_id)
        logger.error("Failed to deliver order notification to admin %d", settings.admin_id)
        await safe_edit_message(
            message=callback.message,
            text=(
                "❌ <b>Не удалось отправить заказ.</b>\n\n"
                "Попробуйте подтвердить ещё раз или свяжитесь с менеджером."
            ),
            reply_markup=kb_order_confirm(data["product_id"]),
        )
        return

    # Thank the user
    await orders_service.mark_notified(order_id)
    await state.clear()
    await safe_edit_message(
        message=callback.message,
        text=(
            "✅ <b>Заказ оформлен!</b>\n\n"
            "Ваша заявка передана менеджеру.\n"
            "Мы свяжемся с вами в ближайшее время для подтверждения и оплаты.\n\n"
            "Спасибо, что выбрали Genesis Peptide Store! 🧬"
        ),
        reply_markup=kb_back_to_main(),
    )
    logger.info(
        "Order placed: product_id=%d user=%d (%s)",
        order.product_id, order.user_id, order.username or "no_username",
    )


# ── Edit order ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("order:edit:"))
async def cb_edit_order(callback: CallbackQuery, state: FSMContext) -> None:
    """Restart order from step 1 keeping product selection."""
    await callback.answer()
    data = await state.get_data()
    if not data:
        await safe_edit_message(
            message=callback.message,
            text="❌ Сессия истекла. Начните заново.",
            reply_markup=kb_back_to_main(),
        )
        return

    # Drop any persisted order id: re-entered details must produce a fresh,
    # accurate order record rather than re-notify against a stale snapshot.
    await state.update_data(order_id=None)
    await state.set_state(OrderStates.waiting_name)
    await safe_edit_message(
        message=callback.message,
        text=(
            f"✏️ <b>Редактирование заказа</b>\n\n"
            f"Товар: <b>{data['product_name']}</b>\n\n"
            f"<b>Шаг 1/3</b> — Введите ваше имя:"
        ),
        reply_markup=kb_cancel_order(),
    )


# ── Cancel ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "order:cancel")
async def cb_cancel_order(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel the order flow and return to main menu."""
    await callback.answer()
    await state.clear()
    await safe_edit_message(
        message=callback.message,
        text="❌ Заказ отменён.\n\nВозвращаемся в главное меню.",
        reply_markup=kb_main_menu(),
    )
