"""
handlers/catalog.py — Catalog browsing: categories → drug list → dosage list → product card.

Navigation flow:
    menu:catalog          → category selection
    cat:{category}        → drug list (unique drug names in category)
    page:{category}:{n}   → drug list page n
    drug:{category}:{name}→ dosage variants for that drug
    prod:{product_id}     → full product card
"""
import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from keyboards import (
    kb_categories,
    kb_drug_list,
    kb_dosage_list,
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


# ── Category → drug list ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cat:"))
async def cb_show_category(callback: CallbackQuery) -> None:
    """Show paginated list of unique drug names for a category."""
    await callback.answer()
    category = callback.data[4:]  # strip "cat:"
    drug_names = await products_service.get_drug_names_by_category(category)

    if not drug_names:
        await safe_edit_message(
            message=callback.message,
            text=f"😔 В категории <b>{category}</b> пока нет товаров.",
            reply_markup=kb_back_to_main(),
        )
        return

    from services.models import CATEGORY_EMOJI
    emoji = CATEGORY_EMOJI.get(category, "📦")
    await safe_edit_message(
        message=callback.message,
        text=(
            f"{emoji} <b>{category}</b>\n\n"
            f"Препаратов: {len(drug_names)}\n"
            f"Выберите препарат:"
        ),
        reply_markup=kb_drug_list(drug_names, category, page=0),
    )


# ── Drug list pagination ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("page:"))
async def cb_paginate_drugs(callback: CallbackQuery) -> None:
    """Handle pagination of drug list: page:{category}:{page_number}"""
    await callback.answer()
    parts = callback.data.split(":", 2)  # ["page", category, page_num]
    if len(parts) != 3:
        return

    _, category, page_str = parts
    try:
        page = int(page_str)
    except ValueError:
        return

    drug_names = await products_service.get_drug_names_by_category(category)
    if not drug_names:
        return

    from services.models import CATEGORY_EMOJI
    emoji = CATEGORY_EMOJI.get(category, "📦")
    await safe_edit_message(
        message=callback.message,
        text=(
            f"{emoji} <b>{category}</b>\n\n"
            f"Препаратов: {len(drug_names)}\n"
            f"Выберите препарат:"
        ),
        reply_markup=kb_drug_list(drug_names, category, page=page),
    )


# ── Drug → dosage list ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("drug:"))
async def cb_show_drug(callback: CallbackQuery) -> None:
    """Show dosage variants for a selected drug: drug:{category}:{drug_name}"""
    await callback.answer()
    parts = callback.data.split(":", 2)  # ["drug", category, drug_name]
    if len(parts) != 3:
        return

    _, category, drug_name = parts
    variants = await products_service.get_products_by_drug(category, drug_name)

    if not variants:
        await callback.answer("❌ Дозировки не найдены", show_alert=True)
        return

    # Single variant → go directly to product card
    if len(variants) == 1:
        product = variants[0]
        card_kb = kb_product_card(
            product_id=product.product_id,
            category=product.category,
            in_stock=product.in_stock,
        )
        card_text = product.card_text()

        if product.photo_id:
            sent = await safe_send_photo(
                bot=callback.bot,
                chat_id=callback.message.chat.id,
                photo=product.photo_id,
                caption=card_text,
                reply_markup=card_kb,
            )
            if sent:
                try:
                    await callback.message.delete()
                except Exception:
                    pass
                return

        await safe_edit_message(
            message=callback.message,
            text=card_text,
            reply_markup=card_kb,
        )
        return

    # Multiple variants → show dosage selection
    await safe_edit_message(
        message=callback.message,
        text=(
            f"💊 <b>{drug_name}</b>\n\n"
            f"Выберите дозировку:"
        ),
        reply_markup=kb_dosage_list(variants, category),
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

    if product.photo_id:
        sent = await safe_send_photo(
            bot=bot,
            chat_id=callback.message.chat.id,
            photo=product.photo_id,
            caption=card_text,
            reply_markup=card_kb,
        )
        if sent:
            try:
                await callback.message.delete()
            except Exception:
                pass
            return

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
