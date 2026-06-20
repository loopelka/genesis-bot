"""
handlers/catalog.py — Catalog browsing: categories → product list → product card.
"""
import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from keyboards import (
    kb_categories,
    kb_product_list,
    kb_product_card,
    kb_back_to_main,
)
from services import products_service
from utils.helpers import safe_edit_message, safe_send_photo, safe_send_message

logger = logging.getLogger(__name__)
router = Router(name="catalog")

# ── Catalog entry point ───────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:catalog")
async def cb_show_catalog(callback: CallbackQuery) -> None:
    """Show category selection."""
    await callback.answer()
    available = await products_service.get_available_categories()
    await safe_edit_message(
        message=callback.message,
        text=(
            "📦 <b>Каталог Genesis Peptide Store</b>\n\n"
            "Выберите категорию:"
        ),
        reply_markup=kb_categories(available),
    )


# ── Category → product list ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cat:"))
async def cb_show_category(callback: CallbackQuery) -> None:
    """Show paginated product list for a category."""
    await callback.answer()
    category = callback.data[4:]  # strip "cat:"
    products = await products_service.get_products_by_category(category)

    if not products:
        await safe_edit_message(
            message=callback.message,
            text=f"😔 В категории <b>{category}</b> пока нет товаров.",
            reply_markup=kb_back_to_main(),
        )
        return

    await safe_edit_message(
        message=callback.message,
        text=(
            f"💉 <b>{category}</b>\n\n"
            f"Найдено товаров: {len(products)}\n"
            f"Выберите товар:"
        ),
        reply_markup=kb_product_list(products, category, page=0),
    )


# ── Pagination ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("page:"))
async def cb_paginate(callback: CallbackQuery) -> None:
    """Handle pagination: page:<category>:<page_number>"""
    await callback.answer()
    parts = callback.data.split(":", 2)  # ["page", category, page_num]
    if len(parts) != 3:
        return

    _, category, page_str = parts
    try:
        page = int(page_str)
    except ValueError:
        return

    products = await products_service.get_products_by_category(category)
    if not products:
        return

    await safe_edit_message(
        message=callback.message,
        text=(
            f"💉 <b>{category}</b>\n\n"
            f"Найдено товаров: {len(products)}\n"
            f"Выберите товар:"
        ),
        reply_markup=kb_product_list(products, category, page=page),
    )


# ── Product card ──────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("prod:"))
async def cb_show_product(callback: CallbackQuery, bot: Bot) -> None:
    """Show full product card — with or without photo."""
    await callback.answer()

    try:
        product_id = int(callback.data[5:])
    except ValueError:
        await callback.answer("❌ Некорректный ID товара", show_alert=True)
        return

    product = await products_service.get_product_by_id(product_id)

    if product is None:
        await callback.answer("❌ Товар не найден. Возможно, он был удалён.", show_alert=True)
        return

    card_kb = kb_product_card(
        product_id=product.product_id,
        category=product.category,
        in_stock=product.in_stock,
    )
    card_text = product.card_text()

    # Try to send photo if file_id present
    if product.photo_id:
        sent = await safe_send_photo(
            bot=bot,
            chat_id=callback.message.chat.id,
            photo=product.photo_id,
            caption=card_text,
            reply_markup=card_kb,
        )
        if sent:
            # Delete the previous inline message to avoid clutter
            try:
                await callback.message.delete()
            except Exception:
                pass
            return
        # Fall through to text card if photo failed

    # Text-only card (no photo or photo send failed)
    await safe_edit_message(
        message=callback.message,
        text=card_text,
        reply_markup=card_kb,
    )


# ── Notify (out of stock placeholder) ────────────────────────────────────────

@router.callback_query(F.data.startswith("notify:"))
async def cb_notify(callback: CallbackQuery) -> None:
    """Placeholder: notify user when out-of-stock product is available."""
    await callback.answer(
        "🔔 Мы уведомим вас, когда товар появится в наличии.\n"
        "Пожалуйста, напишите менеджеру для уточнения сроков.",
        show_alert=True,
    )
