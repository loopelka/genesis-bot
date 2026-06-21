"""
handlers/cart.py — Shopping cart and multi-item checkout flow.

callback_data used (all prefixed cart: — no conflicts with existing handlers):
    menu:cart              — open cart from main menu
    cart:add:{product_id}  — add item from product card
    cart:inc:{product_id}  — increment qty
    cart:dec:{product_id}  — decrement qty
    cart:del:{product_id}  — remove item from cart
    cart:clear             — clear entire cart
    cart:checkout          — start checkout FSM
    cart:use_tg            — use Telegram username/ID as contact
    cart:skip_comment      — skip comment step
    cart:confirm           — final order confirmation
    cart:cancel_checkout   — abort checkout, return to cart view
"""
import html
import logging

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import settings
from keyboards import (
    kb_back_to_main,
    kb_cart,
    kb_cart_empty,
    kb_cart_confirm,
    kb_cart_cancel_checkout,
    kb_checkout_contact,
    kb_checkout_skip_comment,
)
from services import products_service
from services.cart_service import cart_service
from utils import CartCheckoutStates
from utils.helpers import safe_edit_message, safe_send_message

logger = logging.getLogger(__name__)
router = Router(name="cart")


def _fmt_price(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₽"


# ── Cart rendering ────────────────────────────────────────────────────────────

async def _build_cart_view(user_id: int):
    """
    Returns (text, keyboard, is_empty).
    Fetches live product data. Silently drops products no longer in xlsx.
    """
    items = await cart_service.get_items(user_id)

    if not items:
        return (
            "🛒 <b>Корзина пуста</b>\n\nДобавьте товары из каталога.",
            kb_cart_empty(),
            True,
        )

    resolved = []
    missing  = []
    for product_id, qty in items.items():
        product = await products_service.get_product_by_id(product_id)
        if product is None:
            missing.append(product_id)
        else:
            resolved.append((product, qty))

    for pid in missing:
        await cart_service.remove_item(user_id, pid)
        logger.warning("Removed missing product %d from cart of user %d", pid, user_id)

    if not resolved:
        return (
            "🛒 <b>Корзина пуста</b>\n\nДобавьте товары из каталога.",
            kb_cart_empty(),
            True,
        )

    total = sum(p.price * qty for p, qty in resolved)
    lines = ["🛒 <b>Ваша корзина</b>\n"]
    for product, qty in resolved:
        line_total = product.price * qty
        stock_warn = " ⚠️ нет в наличии" if not product.in_stock else ""
        lines.append(
            f"• {product.name} {product.dosage} × {qty}"
            f" — {_fmt_price(line_total)}{stock_warn}"
        )
    lines.append(f"\n💰 <b>Итого: {_fmt_price(total)}</b>")

    return "\n".join(lines), kb_cart(resolved), False


# ── Open cart from main menu ──────────────────────────────────────────────────

@router.callback_query(F.data == "menu:cart")
async def cb_open_cart(callback: CallbackQuery) -> None:
    await callback.answer()
    text, keyboard, _ = await _build_cart_view(callback.from_user.id)
    await safe_edit_message(message=callback.message, text=text, reply_markup=keyboard)


# ── Add to cart from product card ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("cart:add:"))
async def cb_add_to_cart(callback: CallbackQuery) -> None:
    try:
        product_id = int(callback.data[9:])
    except ValueError:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    product = await products_service.get_product_by_id(product_id)
    if product is None:
        await callback.answer("❌ Товар не найден", show_alert=True)
        return
    if not product.in_stock:
        await callback.answer("❌ Товар недоступен", show_alert=True)
        return

    qty = await cart_service.add_item(callback.from_user.id, product_id)
    await callback.answer(
        f"✅ {product.name} {product.dosage} добавлен в корзину (× {qty})",
        show_alert=True,
    )

    # Send a NEW message with cart view — product card may be a photo (can't edit)
    text, keyboard, _ = await _build_cart_view(callback.from_user.id)
    await callback.message.answer(text=text, reply_markup=keyboard, parse_mode="HTML")


# ── Increment quantity ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cart:inc:"))
async def cb_cart_inc(callback: CallbackQuery) -> None:
    try:
        product_id = int(callback.data[9:])
    except ValueError:
        await callback.answer()
        return
    await cart_service.increment(callback.from_user.id, product_id)
    await callback.answer()
    text, keyboard, _ = await _build_cart_view(callback.from_user.id)
    await safe_edit_message(message=callback.message, text=text, reply_markup=keyboard)


# ── Decrement quantity ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cart:dec:"))
async def cb_cart_dec(callback: CallbackQuery) -> None:
    try:
        product_id = int(callback.data[9:])
    except ValueError:
        await callback.answer()
        return
    await cart_service.decrement(callback.from_user.id, product_id)
    await callback.answer()
    text, keyboard, _ = await _build_cart_view(callback.from_user.id)
    await safe_edit_message(message=callback.message, text=text, reply_markup=keyboard)


# ── Delete item ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cart:del:"))
async def cb_cart_del(callback: CallbackQuery) -> None:
    try:
        product_id = int(callback.data[9:])
    except ValueError:
        await callback.answer()
        return
    await cart_service.remove_item(callback.from_user.id, product_id)
    await callback.answer("🗑 Товар удалён")
    text, keyboard, _ = await _build_cart_view(callback.from_user.id)
    await safe_edit_message(message=callback.message, text=text, reply_markup=keyboard)


# ── Clear cart ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cart:clear")
async def cb_cart_clear(callback: CallbackQuery) -> None:
    await cart_service.clear(callback.from_user.id)
    await callback.answer("🗑 Корзина очищена")
    text, keyboard, _ = await _build_cart_view(callback.from_user.id)
    await safe_edit_message(message=callback.message, text=text, reply_markup=keyboard)


# ── Checkout: start ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "cart:checkout")
async def cb_cart_checkout(callback: CallbackQuery, state: FSMContext) -> None:
    if await cart_service.is_empty(callback.from_user.id):
        await callback.answer("❌ Корзина пуста", show_alert=True)
        return
    await callback.answer()
    await state.set_state(CartCheckoutStates.waiting_name)
    await safe_edit_message(
        message=callback.message,
        text=(
            "📝 <b>Оформление заказа</b>\n\n"
            "<b>Шаг 1 из 4</b> — Как вас зовут?\n\n"
            "Введите ваше имя:"
        ),
        reply_markup=kb_cart_cancel_checkout(),
    )


# ── Checkout step 1: name ─────────────────────────────────────────────────────

@router.message(CartCheckoutStates.waiting_name, F.text)
async def msg_cart_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer(
            "⚠️ Имя слишком короткое. Введите ваше имя:",
            reply_markup=kb_cart_cancel_checkout(),
            parse_mode="HTML",
        )
        return
    await state.update_data(customer_name=name)
    await state.set_state(CartCheckoutStates.waiting_contact)
    await message.answer(
        text=(
            f"✅ Имя: <b>{name}</b>\n\n"
            f"<b>Шаг 2 из 4</b> — Как с вами связаться?\n\n"
            f"Введите номер телефона, Telegram username или любой удобный контакт.\n"
            f"Или нажмите кнопку ниже:"
        ),
        reply_markup=kb_checkout_contact(message.from_user.username),
        parse_mode="HTML",
    )


# ── Checkout step 2a: use Telegram as contact (button) ───────────────────────

@router.callback_query(F.data == "cart:use_tg", CartCheckoutStates.waiting_contact)
async def cb_use_telegram_contact(callback: CallbackQuery, state: FSMContext) -> None:
    user = callback.from_user
    contact = f"@{user.username}" if user.username else f"Telegram ID: {user.id}"
    await state.update_data(customer_contact=contact)
    await state.set_state(CartCheckoutStates.waiting_country)
    await callback.answer()
    await safe_edit_message(
        message=callback.message,
        text=(
            f"✅ Связь: <b>{contact}</b>\n\n"
            f"<b>Шаг 3 из 4</b> — Укажите страну доставки:\n\n"
            f"Введите страну:"
        ),
        reply_markup=kb_cart_cancel_checkout(),
    )


# ── Checkout step 2b: contact typed ──────────────────────────────────────────

@router.message(CartCheckoutStates.waiting_contact, F.text)
async def msg_cart_contact(message: Message, state: FSMContext) -> None:
    contact = message.text.strip()
    if len(contact) < 2:
        await message.answer(
            "⚠️ Слишком коротко. Введите телефон, username или любой контакт:",
            reply_markup=kb_checkout_contact(message.from_user.username),
            parse_mode="HTML",
        )
        return
    await state.update_data(customer_contact=contact)
    await state.set_state(CartCheckoutStates.waiting_country)
    await message.answer(
        text=(
            f"✅ Связь: <b>{contact}</b>\n\n"
            f"<b>Шаг 3 из 4</b> — Укажите страну доставки:\n\n"
            f"Введите страну:"
        ),
        reply_markup=kb_cart_cancel_checkout(),
        parse_mode="HTML",
    )


# ── Checkout step 3: country ──────────────────────────────────────────────────

@router.message(CartCheckoutStates.waiting_country, F.text)
async def msg_cart_country(message: Message, state: FSMContext) -> None:
    country = message.text.strip()
    if len(country) < 2:
        await message.answer(
            "⚠️ Укажите страну доставки:",
            reply_markup=kb_cart_cancel_checkout(),
            parse_mode="HTML",
        )
        return
    await state.update_data(customer_country=country)
    await state.set_state(CartCheckoutStates.waiting_comment)
    await message.answer(
        text=(
            f"✅ Страна: <b>{country}</b>\n\n"
            f"<b>Шаг 4 из 4</b> — Комментарий к заказу\n\n"
            f"Введите пожелания (например, способ доставки, адрес).\n"
            f"Или нажмите <b>Пропустить</b>:"
        ),
        reply_markup=kb_checkout_skip_comment(),
        parse_mode="HTML",
    )


# ── Checkout step 4a: skip comment (button) ───────────────────────────────────

@router.callback_query(F.data == "cart:skip_comment", CartCheckoutStates.waiting_comment)
async def cb_skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(customer_comment="")
    await callback.answer()
    await _show_confirmation(
        msg=callback.message,
        state=state,
        user_id=callback.from_user.id,
        edit=True,
    )


# ── Checkout step 4b: comment typed ──────────────────────────────────────────

@router.message(CartCheckoutStates.waiting_comment, F.text)
async def msg_cart_comment(message: Message, state: FSMContext) -> None:
    comment = message.text.strip()
    if comment == "-":
        comment = ""
    await state.update_data(customer_comment=comment)
    await _show_confirmation(
        msg=message,
        state=state,
        user_id=message.from_user.id,
        edit=False,
    )


# ── Confirmation display ──────────────────────────────────────────────────────

async def _show_confirmation(msg, state: FSMContext, user_id: int, edit: bool) -> None:
    data  = await state.get_data()
    items = await cart_service.get_items(user_id)

    if not items:
        await state.clear()
        text = "❌ Корзина пуста. Оформление отменено."
        if edit:
            await safe_edit_message(msg, text=text, reply_markup=kb_back_to_main())
        else:
            await msg.answer(text=text, reply_markup=kb_back_to_main(), parse_mode="HTML")
        return

    resolved = []
    for product_id, qty in items.items():
        product = await products_service.get_product_by_id(product_id)
        if product:
            resolved.append((product, qty))

    total   = sum(p.price * qty for p, qty in resolved)
    comment = data.get("customer_comment", "") or "—"

    lines = [
        "📋 <b>Проверьте данные заказа:</b>\n",
        f"👤 Имя: <b>{data.get('customer_name', '—')}</b>",
        f"📬 Связь: <b>{data.get('customer_contact', '—')}</b>",
        f"🌍 Страна: <b>{data.get('customer_country', '—')}</b>",
        f"💬 Комментарий: {comment}\n",
        "📦 <b>Товары:</b>",
    ]
    for product, qty in resolved:
        lines.append(
            f"• {product.name} {product.dosage} × {qty}"
            f" — {_fmt_price(product.price * qty)}"
        )
    lines.append(f"\n💰 <b>Итого: {_fmt_price(total)}</b>\n\nВсё верно?")

    await state.set_state(CartCheckoutStates.confirming)
    text = "\n".join(lines)

    if edit:
        await safe_edit_message(msg, text=text, reply_markup=kb_cart_confirm())
    else:
        await msg.answer(text=text, reply_markup=kb_cart_confirm(), parse_mode="HTML")


# ── Confirm: send order to admin ──────────────────────────────────────────────

@router.callback_query(F.data == "cart:confirm", CartCheckoutStates.confirming)
async def cb_cart_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    data    = await state.get_data()
    user_id = callback.from_user.id

    items = await cart_service.get_items(user_id)
    if not items:
        await state.clear()
        await safe_edit_message(
            callback.message,
            text="❌ Корзина пуста. Заказ не оформлен.",
            reply_markup=kb_back_to_main(),
        )
        return

    resolved = []
    for product_id, qty in items.items():
        product = await products_service.get_product_by_id(product_id)
        if product:
            resolved.append((product, qty))

    total   = sum(p.price * qty for p, qty in resolved)
    comment = data.get("customer_comment", "") or "—"

    item_lines = "\n".join(
        f"{html.escape(p.name)} {html.escape(p.dosage)} × {qty}" for p, qty in resolved
    )

    # Escape all user-supplied fields — message is sent with HTML parse mode.
    admin_text = (
        f"🛒 <b>Новый заказ</b>\n\n"
        f"Клиент: {html.escape(data.get('customer_name', '—'))}\n"
        f"Связь: {html.escape(data.get('customer_contact', '—'))}\n"
        f"Страна: {html.escape(data.get('customer_country', '—'))}\n\n"
        f"{item_lines}\n\n"
        f"Итого: <b>{_fmt_price(total)}</b>\n\n"
        f"Комментарий:\n{html.escape(comment)}"
    )

    sent = await safe_send_message(bot=bot, chat_id=settings.admin_id, text=admin_text)
    if not sent:
        # Delivery failed — preserve cart and state so the user can retry.
        logger.error("Cart order delivery FAILED for user=%d; cart preserved", user_id)
        await safe_edit_message(
            callback.message,
            text=(
                "❌ <b>Не удалось отправить заказ менеджеру.</b>\n\n"
                "Корзина сохранена. Попробуйте подтвердить ещё раз."
            ),
            reply_markup=kb_cart_confirm(),
        )
        return

    await cart_service.clear(user_id)
    await state.clear()

    logger.info(
        "Cart order placed: user=%d items=%d total=%d",
        user_id, len(resolved), total,
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Перейти в каталог", callback_data="menu:catalog")
    builder.button(text="⬅️ Главное меню",      callback_data="menu:main")
    builder.adjust(1)

    await safe_edit_message(
        callback.message,
        text=(
            "✅ <b>Заказ оформлен!</b>\n\n"
            "Ваша заявка передана менеджеру.\n"
            "Мы свяжемся с вами для подтверждения и оплаты.\n\n"
            "Спасибо, что выбрали Genesis Peptide Store! 🧬"
        ),
        reply_markup=builder.as_markup(),
    )


# ── Cancel checkout: return to cart ──────────────────────────────────────────

@router.callback_query(F.data == "cart:cancel_checkout")
async def cb_cancel_checkout(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Оформление отменено")
    text, keyboard, _ = await _build_cart_view(callback.from_user.id)
    await safe_edit_message(message=callback.message, text=text, reply_markup=keyboard)
