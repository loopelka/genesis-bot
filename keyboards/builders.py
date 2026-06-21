"""
keyboards/builders.py — All InlineKeyboardMarkup builders for Genesis Peptide Store.

Naming convention:
  kb_*  — returns InlineKeyboardMarkup
"""
from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.models import Product, ALL_CATEGORIES, CATEGORY_EMOJI, CONTACT_URL


# ── Main Menu ─────────────────────────────────────────────────────────────────

def kb_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons = [
        ("📦 Каталог",              "menu:catalog"),
        ("💰 Прайс",                "menu:price"),
        ("🚚 Доставка",             "menu:delivery"),
        ("💳 Оплата",               "menu:payment"),
        ("❓ FAQ",                   "menu:faq"),
        ("📞 Менеджер",             "menu:manager"),
        ("⚠️ Важная информация",    "menu:important"),
    ]
    for text, cb in buttons:
        builder.button(text=text, callback_data=cb)
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


# ── Catalog: goal selection ───────────────────────────────────────────────────

def kb_goals() -> InlineKeyboardMarkup:
    """Entry-point keyboard: choose a goal / section."""
    builder = InlineKeyboardBuilder()
    rows = [
        ("🔥 Контроль веса",                    "goal:weight"),
        ("💪 Рост мышц и спортивные результаты", "goal:muscle"),
        ("🩹 Регенерация и восстановление",       "goal:recovery"),
        ("✨ Эстетика и кожа",                    "goal:skin"),
        ("🧠 Когнитивное здоровье",               "goal:brain"),
        ("❤️ Долголетие и Wellbeing",             "goal:longevity"),
        ("📦 Расходники",                         "goal:supplies"),
        ("📞 Консультация",                       "goal:consult"),
        ("⬅️ Главное меню",                      "menu:main"),
    ]
    for text, cb in rows:
        builder.button(text=text, callback_data=cb)
    builder.adjust(1)
    return builder.as_markup()


# ── Catalog: category list ────────────────────────────────────────────────────

def kb_categories(available_categories: List[str]) -> InlineKeyboardMarkup:
    """Show every category that has products, skip empty ones."""
    builder = InlineKeyboardBuilder()
    for category in ALL_CATEGORIES:
        emoji = CATEGORY_EMOJI.get(category, "📦")
        if category in available_categories:
            builder.button(text=f"{emoji} {category}", callback_data=f"cat:{category}")
        else:
            builder.button(text=f"⏳ {category} (скоро)", callback_data="noop")
    builder.button(text="⬅️ К разделам", callback_data="menu:catalog")
    builder.adjust(1)
    return builder.as_markup()


# ── Catalog: drug list ────────────────────────────────────────────────────────

def kb_drug_list(drug_names: List[str], category: str, page: int = 0) -> InlineKeyboardMarkup:
    """Paginated list of unique drug names within a category."""
    PAGE_SIZE = 8
    start = page * PAGE_SIZE
    end   = start + PAGE_SIZE
    page_drugs  = drug_names[start:end]
    total_pages = (len(drug_names) + PAGE_SIZE - 1) // PAGE_SIZE

    builder = InlineKeyboardBuilder()
    for name in page_drugs:
        builder.button(text=name, callback_data=f"drug:{category}:{name}")
    builder.adjust(1)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад",  callback_data=f"page:{category}:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️ Далее", callback_data=f"page:{category}:{page + 1}"))
    if nav:
        builder.row(*nav)
    if total_pages > 1:
        builder.row(InlineKeyboardButton(text=f"📄 {page + 1} / {total_pages}", callback_data="noop"))

    builder.row(InlineKeyboardButton(text="⬅️ К разделам", callback_data="menu:catalog"))
    return builder.as_markup()


# ── Catalog: dosage list ──────────────────────────────────────────────────────

def kb_dosage_list(products: List[Product], category: str) -> InlineKeyboardMarkup:
    """Dosage variants for a single drug, sorted by price."""
    builder = InlineKeyboardBuilder()
    for p in products:
        icon  = "✅" if p.in_stock else "❌"
        label = f"{icon} {p.dosage} — {p.price_formatted}"
        builder.button(text=label, callback_data=f"prod:{p.product_id}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cat:{category}"))
    return builder.as_markup()


# ── Catalog: product card ─────────────────────────────────────────────────────

def kb_product_card(product_id: int, category: str, in_stock: bool) -> InlineKeyboardMarkup:
    """Buttons shown on a product card."""
    builder = InlineKeyboardBuilder()

    if in_stock:
        builder.button(text="🛒 Заказать", callback_data=f"order:{product_id}")
    else:
        builder.button(text="🔔 Уведомить о поступлении", callback_data=f"notify:{product_id}")

    builder.row(
        InlineKeyboardButton(text="📞 Консультация", url=CONTACT_URL)
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cat:{category}")
    )
    return builder.as_markup()


# ── Order Flow ────────────────────────────────────────────────────────────────

def kb_cancel_order() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить заказ", callback_data="order:cancel")
    return builder.as_markup()


def kb_order_confirm(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить заказ",  callback_data=f"order:confirm:{product_id}")
    builder.button(text="✏️ Изменить данные",    callback_data=f"order:edit:{product_id}")
    builder.button(text="❌ Отменить",           callback_data="order:cancel")
    builder.adjust(1)
    return builder.as_markup()


# ── FAQ ───────────────────────────────────────────────────────────────────────

def kb_faq_back() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Главное меню", callback_data="menu:main")
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
    builder.button(text="⬅️ Главное меню",   callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


# ── Product list (flat, backward-compat) ──────────────────────────────────────

def kb_product_list(products: List[Product], category: str, page: int = 0) -> InlineKeyboardMarkup:
    """Paginated flat product list — kept for backward compatibility."""
    PAGE_SIZE   = 8
    start       = page * PAGE_SIZE
    end         = start + PAGE_SIZE
    page_prods  = products[start:end]
    total_pages = (len(products) + PAGE_SIZE - 1) // PAGE_SIZE

    builder = InlineKeyboardBuilder()
    for p in page_prods:
        icon  = "✅" if p.in_stock else "❌"
        label = f"{icon} {p.name} {p.dosage}"
        builder.button(text=label, callback_data=f"prod:{p.product_id}")
    builder.adjust(1)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад",  callback_data=f"page:{category}:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️ Далее", callback_data=f"page:{category}:{page + 1}"))
    if nav:
        builder.row(*nav)
    if total_pages > 1:
        builder.row(InlineKeyboardButton(text=f"📄 {page + 1} / {total_pages}", callback_data="noop"))

    builder.row(InlineKeyboardButton(text="⬅️ К разделам", callback_data="menu:catalog"))
    return builder.as_markup()
