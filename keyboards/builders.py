"""
keyboards/builders.py — All InlineKeyboardMarkup builders for Genesis Peptide Store.

Naming convention:
  kb_*  — returns InlineKeyboardMarkup
"""
from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.models import Product, ALL_CATEGORIES, CATEGORY_EMOJI


# ── Main Menu ─────────────────────────────────────────────────────────────────

def kb_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons = [
        ("📦 Каталог", "menu:catalog"),
        ("💰 Прайс", "menu:price"),
        ("🚚 Доставка", "menu:delivery"),
        ("💳 Оплата", "menu:payment"),
        ("❓ FAQ", "menu:faq"),
        ("📞 Менеджер", "menu:manager"),
    ]
    for text, callback in buttons:
        builder.button(text=text, callback_data=callback)
    builder.adjust(2)
    return builder.as_markup()


# ── Catalog ───────────────────────────────────────────────────────────────────

def kb_categories(available_categories: List[str]) -> InlineKeyboardMarkup:
    """Show categories that actually have products."""
    builder = InlineKeyboardBuilder()
    for category in ALL_CATEGORIES:
        emoji = CATEGORY_EMOJI.get(category, "📦")
        is_available = category in available_categories
        label = f"{emoji} {category}" if is_available else f"⏳ {category} (скоро)"
        callback = f"cat:{category}" if is_available else "noop"
        builder.button(text=label, callback_data=callback)
    builder.button(text="⬅️ Главное меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def kb_product_list(products: List[Product], category: str, page: int = 0) -> InlineKeyboardMarkup:
    """Paginated product list keyboard. Shows PAGE_SIZE products per page."""
    PAGE_SIZE = 8
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_products = products[start:end]
    total_pages = (len(products) + PAGE_SIZE - 1) // PAGE_SIZE

    builder = InlineKeyboardBuilder()

    for p in page_products:
        stock_icon = "✅" if p.in_stock else "❌"
        label = f"{stock_icon} {p.name} {p.dosage} — {p.price_formatted}"
        builder.button(text=label, callback_data=f"prod:{p.product_id}")

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"page:{category}:{page - 1}")
        )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="▶️ Далее", callback_data=f"page:{category}:{page + 1}")
        )
    if nav_buttons:
        builder.row(*nav_buttons)

    if total_pages > 1:
        builder.row(
            InlineKeyboardButton(
                text=f"📄 {page + 1} / {total_pages}", callback_data="noop"
            )
        )

    builder.row(
        InlineKeyboardButton(text="⬅️ К категориям", callback_data="menu:catalog")
    )
    return builder.as_markup()


def kb_product_card(product_id: int, category: str, in_stock: bool) -> InlineKeyboardMarkup:
    """Keyboard shown on a product card."""
    builder = InlineKeyboardBuilder()
    if in_stock:
        builder.button(text="🛒 Заказать", callback_data=f"order:{product_id}")
    else:
        builder.button(text="🔔 Уведомить о поступлении", callback_data=f"notify:{product_id}")
    builder.button(text="⬅️ Назад", callback_data=f"cat:{category}")
    builder.adjust(1)
    return builder.as_markup()


# ── Order Flow ────────────────────────────────────────────────────────────────

def kb_cancel_order() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить заказ", callback_data="order:cancel")
    return builder.as_markup()


def kb_order_confirm(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить заказ", callback_data=f"order:confirm:{product_id}")
    builder.button(text="✏️ Изменить данные", callback_data=f"order:edit:{product_id}")
    builder.button(text="❌ Отменить", callback_data="order:cancel")
    builder.adjust(1)
    return builder.as_markup()


# ── FAQ ───────────────────────────────────────────────────────────────────────

def kb_faq_list(total_entries: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i in range(total_entries):
        builder.button(text=f"❓ Вопрос {i + 1}", callback_data=f"faq:{i}")
    builder.button(text="⬅️ Главное меню", callback_data="menu:main")
    builder.adjust(2)
    return builder.as_markup()


def kb_faq_back() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Все вопросы", callback_data="menu:faq")
    builder.button(text="⬅️ Главное меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


# ── Manager ───────────────────────────────────────────────────────────────────

def kb_cancel_manager() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="menu:main")
    return builder.as_markup()


# ── Utility ───────────────────────────────────────────────────────────────────

def kb_back_to_main() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Главное меню", callback_data="menu:main")
    return builder.as_markup()


def kb_price_list() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Открыть каталог", callback_data="menu:catalog")
    builder.button(text="⬅️ Главное меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()
