"""
handlers/catalog.py — Catalog browsing.

Navigation flow:
    menu:catalog            → goal selection (kb_goals)
    goal:{key}              → drug list for mapped category
    goal:consult            → consultation info page (static)
    cat:{category}          → drug list for category (page 0)
    page:{category}:{n}     → drug list page n
    drug:{category}:{name}  → dosage list (or direct card if only 1 variant)
    prod:{product_id}       → full product card
"""
import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from keyboards import (
    kb_goals,
    kb_drug_list,
    kb_dosage_list,
    kb_product_card,
    kb_back_to_main,
)
from services import products_service
from services.models import CATEGORY_EMOJI, CONTACT, CONTACT_URL
from utils.helpers import safe_edit_message, safe_send_photo

logger = logging.getLogger(__name__)
router = Router(name="catalog")

# ── goal: → category name mapping ────────────────────────────────────────────

GOAL_TO_CATEGORY: dict[str, str] = {
    "weight":   "Контроль веса",
    "muscle":   "Рост мышц",
    "recovery": "Регенерация",
    "skin":     "Эстетика",
    "brain":    "Когнитивное",
    "longevity":"Долголетие",
    "supplies": "Расходники",
}

CONSULT_TEXT = (
    "🩺 <b>Индивидуальная консультация</b>\n\n"
    "Персональное сопровождение, разбор программ и ответы на вопросы.\n\n"
    f"📩 Для получения информации:\n<b>{CONTACT}</b>"
)


# ── Catalog entry point ───────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:catalog")
async def cb_show_catalog(callback: CallbackQuery) -> None:
    """Show goal/section selection."""
    await callback.answer()
    await safe_edit_message(
        message=callback.message,
        text=(
            "📦 <b>Каталог Genesis Peptide Store</b>\n\n"
            "Выберите раздел:"
        ),
        reply_markup=kb_goals(),
    )


# ── Goal buttons ──────────────────────────────────────────────────────────────

@router.callback_query(F.data.in_(
    {f"goal:{k}" for k in GOAL_TO_CATEGORY}
))
async def cb_goal_category(callback: CallbackQuery) -> None:
    """Map goal:{key} → drug list for the corresponding xlsx category."""
    await callback.answer()
    key      = callback.data[5:]          # strip "goal:"
    category = GOAL_TO_CATEGORY[key]
    await _show_drug_list(callback, category, page=0)


@router.callback_query(F.data == "goal:consult")
async def cb_goal_consult(callback: CallbackQuery) -> None:
    """Static consultation info page."""
    await callback.answer()
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📩 Написать менеджеру", url=CONTACT_URL))
    builder.row(InlineKeyboardButton(text="⬅️ К разделам", callback_data="menu:catalog"))
    await safe_edit_message(
        message=callback.message,
        text=CONSULT_TEXT,
        reply_markup=builder.as_markup(),
    )



# ── Category → drug list ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cat:"))
async def cb_show_category(callback: CallbackQuery) -> None:
    """Show paginated drug list for a category."""
    await callback.answer()
    category = callback.data[4:]
    await _show_drug_list(callback, category, page=0)


# ── Drug list pagination ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("page:"))
async def cb_paginate_drugs(callback: CallbackQuery) -> None:
    """page:{category}:{page_number}"""
    await callback.answer()
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        return
    _, category, page_str = parts
    try:
        page = int(page_str)
    except ValueError:
        return
    await _show_drug_list(callback, category, page=page)


# ── Drug → dosage list ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("drug:"))
async def cb_show_drug(callback: CallbackQuery) -> None:
    """drug:{category}:{drug_name} → dosage selection or direct card."""
    await callback.answer()
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        return
    _, category, drug_name = parts

    variants = await products_service.get_products_by_drug(category, drug_name)
    if not variants:
        await callback.answer("❌ Дозировки не найдены", show_alert=True)
        return

    if len(variants) == 1:
        await _send_product_card(callback, variants[0], bot=callback.bot)
        return

    await safe_edit_message(
        message=callback.message,
        text=f"💊 <b>{drug_name}</b>\n\nВыберите дозировку:",
        reply_markup=kb_dosage_list(variants, category),
    )


# ── Product card ──────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("prod:"))
async def cb_show_product(callback: CallbackQuery, bot: Bot) -> None:
    """Show full product card."""
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

    await _send_product_card(callback, product, bot=bot)


# ── Notify placeholder ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("notify:"))
async def cb_notify(callback: CallbackQuery) -> None:
    await callback.answer(
        "🔔 Мы уведомим вас, когда товар появится в наличии.\n"
        "Пожалуйста, напишите менеджеру для уточнения сроков.",
        show_alert=True,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _show_drug_list(callback: CallbackQuery, category: str, page: int) -> None:
    """Render drug list for a category at a given page."""
    drug_names = await products_service.get_drug_names_by_category(category)
    if not drug_names:
        await safe_edit_message(
            message=callback.message,
            text=f"😔 В разделе <b>{category}</b> пока нет товаров.",
            reply_markup=kb_back_to_main(),
        )
        return

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


async def _send_product_card(callback: CallbackQuery, product, bot: Bot) -> None:
    """Send product card — photo if available, otherwise text."""
    card_kb   = kb_product_card(
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
