"""
handlers/admin.py — Full Telegram admin panel for Genesis Peptide Store.

Access is restricted to settings.admin_id. The panel lets the owner manage the
store entirely from Telegram (products, categories, orders, broadcasts, users,
statistics, store texts, promo codes, backups) with no code/file/Excel editing.

All new callbacks are prefixed `adm:` to avoid colliding with the customer
callbacks (`menu:`, `cart:`, `order:`, `cat:`, `drug:`, `prod:`, `goal:`). The
legacy `admin:broadcast/users/stats` callbacks are kept as working aliases.
"""
import asyncio
import io
import logging
import time
import zipfile
from datetime import datetime, timezone
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import settings
from config.settings import settings as cfg
from services import products_service
from services.users_service import users_service
from services.orders_service import orders_service
from services.categories_service import categories_service
from services.store_settings_service import store_settings_service, EDITABLE_KEYS
from services.promocodes_service import (
    promocodes_service, KIND_PERCENT, KIND_FIXED,
)
from utils.states import (
    AdminProductStates, AdminCategoryStates, AdminPromoStates,
    AdminSettingsStates, AdminBackupStates, AdminOrderStates, AdminUserStates,
)
from utils.helpers import safe_edit_message

logger = logging.getLogger(__name__)
router = Router(name="admin")

PAGE = 8


# ── Access control ────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id == settings.admin_id


async def _guard_cb(callback: CallbackQuery) -> bool:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return False
    return True


def _fmt_price(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₽"


# ── FSM: broadcasts (kept from the original implementation, extended) ──────────

class BroadcastStates(StatesGroup):
    waiting_message = State()
    confirming      = State()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN PANEL
# ══════════════════════════════════════════════════════════════════════════════

def kb_admin_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📦 Товары",        callback_data="adm:products")
    b.button(text="📂 Категории",     callback_data="adm:categories")
    b.button(text="📋 Заказы",        callback_data="adm:orders")
    b.button(text="📢 Рассылки",      callback_data="adm:broadcasts")
    b.button(text="👥 Пользователи",  callback_data="adm:users")
    b.button(text="📈 Статистика",    callback_data="adm:stats")
    b.button(text="⚙️ Настройки",     callback_data="adm:settings")
    b.button(text="🎁 Промокоды",     callback_data="adm:promo")
    b.button(text="🛡 Бэкапы",        callback_data="adm:backups")
    b.adjust(2, 2, 2, 2, 1)
    return b.as_markup()


def kb_home() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔧 В админ-панель", callback_data="adm:home")
    return b.as_markup()


async def _panel_text() -> str:
    users = await users_service.count()
    products = len(await products_service.get_all_admin())
    orders = await orders_service.count()
    return (
        "🔧 <b>Админ-панель</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"📦 Товаров: <b>{products}</b>\n"
        f"📋 Заказов: <b>{orders}</b>\n\n"
        "Выберите раздел:"
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(await _panel_text(), reply_markup=kb_admin_menu())


@router.callback_query(F.data == "adm:home")
async def cb_home(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.clear()
    await callback.answer()
    await safe_edit_message(callback.message, text=await _panel_text(), reply_markup=kb_admin_menu())


# ══════════════════════════════════════════════════════════════════════════════
#  PRODUCTS
# ══════════════════════════════════════════════════════════════════════════════

def _kb_products_list(products: list, page: int, total_pages: int, prefix: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in products:
        flag = "🙈 " if p.hidden else ""
        b.row(InlineKeyboardButton(
            text=f"{flag}{p.name} {p.dosage} — {_fmt_price(p.price)}",
            callback_data=f"adm:prod_view:{p.product_id}",
        ))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}{page+1}"))
    if nav:
        b.row(*nav)
    b.row(
        InlineKeyboardButton(text="➕ Добавить", callback_data="adm:prod_add"),
        InlineKeyboardButton(text="🔍 Поиск",    callback_data="adm:prod_search"),
    )
    b.row(
        InlineKeyboardButton(text="📂 По категории", callback_data="adm:prod_cats"),
        InlineKeyboardButton(text="💱 Цены ±%",      callback_data="adm:prod_bulk"),
    )
    b.row(InlineKeyboardButton(text="🔧 В админ-панель", callback_data="adm:home"))
    return b.as_markup()


async def _show_products(message: Message, items: list, page: int, prefix: str, header: str) -> None:
    total_pages = max(1, (len(items) + PAGE - 1) // PAGE)
    page = max(0, min(page, total_pages - 1))
    chunk = items[page * PAGE:(page + 1) * PAGE]
    text = f"{header}\nВсего: <b>{len(items)}</b> · стр. {page+1}/{total_pages}"
    if not items:
        text = f"{header}\n\nНичего не найдено."
    await safe_edit_message(message, text=text,
                            reply_markup=_kb_products_list(chunk, page, total_pages, prefix))


async def _render_product_view(message: Message, pid: int) -> None:
    p = await products_service.get_admin_by_id(pid)
    if p is None:
        await safe_edit_message(message, text="❌ Товар не найден.", reply_markup=kb_home())
        return
    text = (
        f"📦 <b>{p.name}</b>\n\n"
        f"🆔 ID: <code>{p.product_id}</code>\n"
        f"📂 Категория: {p.category}\n"
        f"⚗️ Дозировка: {p.dosage}\n"
        f"💰 Цена: {_fmt_price(p.price)}\n"
        f"👁 Статус: {'🙈 скрыт' if p.hidden else '✅ виден'}\n"
        f"📝 Описание: {p.description or '—'}"
    )
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Изменить", callback_data=f"adm:prod_edit:{pid}")
    b.button(text="🙈 Скрыть" if not p.hidden else "👁 Показать",
             callback_data=f"adm:prod_{'hide' if not p.hidden else 'show'}:{pid}")
    b.button(text="📑 Клонировать", callback_data=f"adm:prod_clone:{pid}")
    b.button(text="🗑 Удалить",     callback_data=f"adm:prod_del:{pid}")
    b.button(text="⬅️ К товарам",   callback_data="adm:products")
    b.adjust(2, 2, 1)
    await safe_edit_message(message, text=text, reply_markup=b.as_markup())


@router.callback_query(F.data == "adm:products")
@router.callback_query(F.data.startswith("adm:prod_page:"))
async def cb_products(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.clear()
    await callback.answer()
    page = int(callback.data.split(":")[-1]) if callback.data.startswith("adm:prod_page:") else 0
    items = await products_service.get_all_admin()
    await _show_products(callback.message, items, page, "adm:prod_page:", "📦 <b>Товары</b>")


# ── Search by name ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:prod_search")
async def cb_prod_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.set_state(AdminProductStates.search_name)
    await callback.answer()
    await safe_edit_message(callback.message, text="🔍 Введите часть названия товара:",
                            reply_markup=kb_home())


@router.message(AdminProductStates.search_name, F.text)
async def msg_prod_search(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    items = await products_service.search(message.text.strip())
    total_pages = max(1, (len(items) + PAGE - 1) // PAGE)
    chunk = items[:PAGE]
    header = f"🔍 <b>Результаты:</b> «{message.text.strip()}»"
    text = f"{header}\nНайдено: <b>{len(items)}</b> · стр. 1/{total_pages}" if items else f"{header}\n\nНичего не найдено."
    await message.answer(text, reply_markup=_kb_products_list(chunk, 0, total_pages, "adm:prod_page:"))


# ── Filter by category ────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:prod_cats")
async def cb_prod_cats(callback: CallbackQuery) -> None:
    if not await _guard_cb(callback):
        return
    await callback.answer()
    counts = await products_service.category_counts()
    b = InlineKeyboardBuilder()
    for name in await categories_service.names():
        b.row(InlineKeyboardButton(
            text=f"{categories_service.emoji_for(name)} {name} ({counts.get(name, 0)})",
            callback_data=f"adm:prod_cat:{name}",
        ))
    b.row(InlineKeyboardButton(text="⬅️ К товарам", callback_data="adm:products"))
    await safe_edit_message(callback.message, text="📂 Выберите категорию:", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("adm:prod_cat:"))
async def cb_prod_cat(callback: CallbackQuery) -> None:
    if not await _guard_cb(callback):
        return
    await callback.answer()
    category = callback.data.split(":", 2)[2]
    items = [p for p in await products_service.get_all_admin() if p.category == category]
    await _show_products(callback.message, items, 0, "adm:prod_page:", f"📂 <b>{category}</b>")


# ── Product detail ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:prod_view:"))
async def cb_prod_view(callback: CallbackQuery) -> None:
    if not await _guard_cb(callback):
        return
    await callback.answer()
    pid = int(callback.data.split(":")[-1])
    await _render_product_view(callback.message, pid)


@router.callback_query(F.data.startswith("adm:prod_hide:"))
@router.callback_query(F.data.startswith("adm:prod_show:"))
async def cb_prod_toggle(callback: CallbackQuery) -> None:
    if not await _guard_cb(callback):
        return
    pid = int(callback.data.split(":")[-1])
    hide = callback.data.startswith("adm:prod_hide:")
    await products_service.set_hidden(pid, hide)
    await callback.answer("🙈 Скрыт" if hide else "👁 Показан")
    await _render_product_view(callback.message, pid)


@router.callback_query(F.data.startswith("adm:prod_clone:"))
async def cb_prod_clone(callback: CallbackQuery) -> None:
    if not await _guard_cb(callback):
        return
    pid = int(callback.data.split(":")[-1])
    clone = await products_service.clone_product(pid)
    await callback.answer("📑 Клонирован" if clone else "❌ Ошибка")
    if clone:
        await _render_product_view(callback.message, clone.product_id)


@router.callback_query(F.data.startswith("adm:prod_del:"))
async def cb_prod_del(callback: CallbackQuery) -> None:
    if not await _guard_cb(callback):
        return
    await callback.answer()
    pid = int(callback.data.split(":")[-1])
    b = InlineKeyboardBuilder()
    b.button(text="✅ Да, удалить", callback_data=f"adm:prod_delok:{pid}")
    b.button(text="⬅️ Отмена",      callback_data=f"adm:prod_view:{pid}")
    b.adjust(1)
    await safe_edit_message(callback.message, text="🗑 Удалить товар безвозвратно?", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("adm:prod_delok:"))
async def cb_prod_delok(callback: CallbackQuery) -> None:
    if not await _guard_cb(callback):
        return
    pid = int(callback.data.split(":")[-1])
    await products_service.delete_product(pid)
    await callback.answer("🗑 Удалён")
    items = await products_service.get_all_admin()
    await _show_products(callback.message, items, 0, "adm:prod_page:", "📦 <b>Товары</b>")


# ── Edit product fields ───────────────────────────────────────────────────────

EDIT_FIELDS = {
    "name": "название", "category": "категорию", "dosage": "дозировку",
    "price": "цену", "description": "описание",
}


@router.callback_query(F.data.startswith("adm:prod_edit:"))
async def cb_prod_edit(callback: CallbackQuery) -> None:
    if not await _guard_cb(callback):
        return
    await callback.answer()
    pid = int(callback.data.split(":")[-1])
    b = InlineKeyboardBuilder()
    b.button(text="Название",   callback_data=f"adm:prod_ef:{pid}:name")
    b.button(text="Категория",  callback_data=f"adm:prod_ec:{pid}")
    b.button(text="Дозировка",  callback_data=f"adm:prod_ef:{pid}:dosage")
    b.button(text="Цена",       callback_data=f"adm:prod_ef:{pid}:price")
    b.button(text="Описание",   callback_data=f"adm:prod_ef:{pid}:description")
    b.button(text="⬅️ Назад",   callback_data=f"adm:prod_view:{pid}")
    b.adjust(2, 2, 1, 1)
    await safe_edit_message(callback.message, text="✏️ Что изменить?", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("adm:prod_ef:"))
async def cb_prod_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    _, _, pid, field = callback.data.split(":")
    await state.set_state(AdminProductStates.edit_value)
    await state.update_data(edit_pid=int(pid), edit_field=field)
    await callback.answer()
    await safe_edit_message(callback.message, text=f"Введите новое значение ({EDIT_FIELDS.get(field, field)}):",
                            reply_markup=kb_home())


@router.message(AdminProductStates.edit_value, F.text)
async def msg_prod_edit_value(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    pid, field = data["edit_pid"], data["edit_field"]
    value: object = message.text.strip()
    if field == "price":
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        if not digits:
            await message.answer("⚠️ Введите число.", reply_markup=kb_home())
            return
        value = int(digits)
    await products_service.update_product(pid, **{field: value})
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ К товару", callback_data=f"adm:prod_view:{pid}")
    await message.answer("✅ Сохранено.", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("adm:prod_ec:"))
async def cb_prod_edit_category(callback: CallbackQuery) -> None:
    if not await _guard_cb(callback):
        return
    await callback.answer()
    pid = int(callback.data.split(":")[-1])
    b = InlineKeyboardBuilder()
    for name in await categories_service.names():
        b.row(InlineKeyboardButton(text=name, callback_data=f"adm:prod_sc:{pid}:{name}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm:prod_edit:{pid}"))
    await safe_edit_message(callback.message, text="📂 Выберите категорию:", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("adm:prod_sc:"))
async def cb_prod_set_category(callback: CallbackQuery) -> None:
    if not await _guard_cb(callback):
        return
    _, _, pid, name = callback.data.split(":", 3)
    await products_service.update_product(int(pid), category=name)
    await callback.answer("✅ Категория обновлена")
    await _render_product_view(callback.message, int(pid))


# ── Add product (FSM) ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:prod_add")
async def cb_prod_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.set_state(AdminProductStates.add_name)
    await callback.answer()
    await safe_edit_message(callback.message, text="➕ <b>Новый товар</b>\n\nВведите название:",
                            reply_markup=kb_home())


@router.message(AdminProductStates.add_name, F.text)
async def msg_add_name(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminProductStates.add_category)
    b = InlineKeyboardBuilder()
    for name in await categories_service.names():
        b.row(InlineKeyboardButton(text=name, callback_data=f"adm:prod_addcat:{name}"))
    await message.answer("📂 Выберите категорию:", reply_markup=b.as_markup())


@router.callback_query(AdminProductStates.add_category, F.data.startswith("adm:prod_addcat:"))
async def cb_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    category = callback.data.split(":", 2)[2]
    await state.update_data(category=category)
    await state.set_state(AdminProductStates.add_dosage)
    await callback.answer()
    await safe_edit_message(callback.message, text="⚗️ Введите дозировку (например, 10 mg):",
                            reply_markup=kb_home())


@router.message(AdminProductStates.add_dosage, F.text)
async def msg_add_dosage(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.update_data(dosage=message.text.strip())
    await state.set_state(AdminProductStates.add_price)
    await message.answer("💰 Введите цену в рублях (число):", reply_markup=kb_home())


@router.message(AdminProductStates.add_price, F.text)
async def msg_add_price(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    digits = "".join(ch for ch in message.text if ch.isdigit())
    if not digits:
        await message.answer("⚠️ Введите число.", reply_markup=kb_home())
        return
    await state.update_data(price=int(digits))
    await state.set_state(AdminProductStates.add_description)
    b = InlineKeyboardBuilder()
    b.button(text="➡️ Пропустить", callback_data="adm:prod_add_nodesc")
    await message.answer("📝 Введите описание или пропустите:", reply_markup=b.as_markup())


async def _finish_add(message_or_cb, state: FSMContext, description: str) -> None:
    data = await state.get_data()
    await state.clear()
    p = await products_service.add_product(
        category=data["category"], name=data["name"], dosage=data["dosage"],
        price=data["price"], description=description,
    )
    b = InlineKeyboardBuilder()
    b.button(text="📦 К товару", callback_data=f"adm:prod_view:{p.product_id}")
    b.button(text="🔧 В админ-панель", callback_data="adm:home")
    b.adjust(1)
    text = f"✅ Товар добавлен: <b>{p.name}</b> (ID {p.product_id})"
    if isinstance(message_or_cb, CallbackQuery):
        await safe_edit_message(message_or_cb.message, text=text, reply_markup=b.as_markup())
    else:
        await message_or_cb.answer(text, reply_markup=b.as_markup())


@router.message(AdminProductStates.add_description, F.text)
async def msg_add_description(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await _finish_add(message, state, message.text.strip())


@router.callback_query(AdminProductStates.add_description, F.data == "adm:prod_add_nodesc")
async def cb_add_nodesc(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await callback.answer()
    await _finish_add(callback, state, "")


# ── Bulk price change ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:prod_bulk")
async def cb_prod_bulk(callback: CallbackQuery) -> None:
    if not await _guard_cb(callback):
        return
    await callback.answer()
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🌐 Все товары", callback_data="adm:prod_bulk:*"))
    for name in await categories_service.names():
        b.row(InlineKeyboardButton(text=name, callback_data=f"adm:prod_bulk:{name}"))
    b.row(InlineKeyboardButton(text="⬅️ К товарам", callback_data="adm:products"))
    await safe_edit_message(callback.message,
                            text="💱 <b>Изменение цен на %</b>\n\nВыберите область:",
                            reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("adm:prod_bulk:"))
async def cb_prod_bulk_scope(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    scope = callback.data.split(":", 2)[2]
    await state.set_state(AdminProductStates.bulk_percent)
    await state.update_data(bulk_scope=scope)
    await callback.answer()
    label = "всех товаров" if scope == "*" else f"категории «{scope}»"
    await safe_edit_message(
        callback.message,
        text=f"💱 Введите процент изменения цен {label}.\n\nНапример: <code>10</code> (+10%) или <code>-15</code> (−15%):",
        reply_markup=kb_home(),
    )


@router.message(AdminProductStates.bulk_percent, F.text)
async def msg_bulk_percent(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    raw = message.text.strip().replace("%", "").replace(",", ".")
    try:
        percent = float(raw)
    except ValueError:
        await message.answer("⚠️ Введите число, например 10 или -15.", reply_markup=kb_home())
        return
    scope = data["bulk_scope"]
    category = None if scope == "*" else scope
    affected = await products_service.bulk_price_change(category, percent)
    b = InlineKeyboardBuilder()
    b.button(text="📦 К товарам", callback_data="adm:products")
    await message.answer(
        f"✅ Цены изменены на <b>{percent:+.1f}%</b>.\nЗатронуто товаров: <b>{affected}</b>.",
        reply_markup=b.as_markup(),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  CATEGORIES
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:categories")
async def cb_categories(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.clear()
    await callback.answer()
    counts = await products_service.category_counts()
    cats = await categories_service.get_all()
    b = InlineKeyboardBuilder()
    for c in cats:
        name = c["name"]
        b.row(InlineKeyboardButton(text=f"{c['emoji']} {name} ({counts.get(name, 0)})",
                                   callback_data="noop"))
        b.row(
            InlineKeyboardButton(text="🔼", callback_data=f"adm:cat_up:{name}"),
            InlineKeyboardButton(text="🔽", callback_data=f"adm:cat_down:{name}"),
            InlineKeyboardButton(text="✏️", callback_data=f"adm:cat_rename:{name}"),
            InlineKeyboardButton(text="🗑", callback_data=f"adm:cat_del:{name}"),
        )
    b.row(InlineKeyboardButton(text="➕ Новая категория", callback_data="adm:cat_create"))
    b.row(InlineKeyboardButton(text="🔧 В админ-панель", callback_data="adm:home"))
    await safe_edit_message(callback.message, text="📂 <b>Категории</b>", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("adm:cat_up:"))
@router.callback_query(F.data.startswith("adm:cat_down:"))
async def cb_cat_move(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    name = callback.data.split(":", 2)[2]
    await categories_service.move(name, -1 if callback.data.startswith("adm:cat_up:") else 1)
    await callback.answer()
    await cb_categories(callback, state)


@router.callback_query(F.data.startswith("adm:cat_del:"))
async def cb_cat_del(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    name = callback.data.split(":", 2)[2]
    counts = await products_service.category_counts()
    if counts.get(name, 0) > 0:
        await callback.answer("❌ Нельзя удалить: в категории есть товары", show_alert=True)
        return
    await categories_service.delete(name)
    await callback.answer("🗑 Удалена")
    await cb_categories(callback, state)


@router.callback_query(F.data == "adm:cat_create")
async def cb_cat_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.set_state(AdminCategoryStates.create_name)
    await callback.answer()
    await safe_edit_message(callback.message, text="➕ Введите название новой категории:", reply_markup=kb_home())


@router.message(AdminCategoryStates.create_name, F.text)
async def msg_cat_create(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    ok = await categories_service.create(message.text.strip())
    b = InlineKeyboardBuilder()
    b.button(text="📂 К категориям", callback_data="adm:categories")
    await message.answer("✅ Категория создана." if ok else "⚠️ Такая категория уже есть.",
                         reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("adm:cat_rename:"))
async def cb_cat_rename(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    name = callback.data.split(":", 2)[2]
    await state.set_state(AdminCategoryStates.rename_value)
    await state.update_data(rename_old=name)
    await callback.answer()
    await safe_edit_message(callback.message, text=f"✏️ Новое имя для «{name}»:", reply_markup=kb_home())


@router.message(AdminCategoryStates.rename_value, F.text)
async def msg_cat_rename(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    old, new = data["rename_old"], message.text.strip()
    ok = await categories_service.rename(old, new)
    if ok:
        await products_service.rename_category(old, new)  # cascade
    b = InlineKeyboardBuilder()
    b.button(text="📂 К категориям", callback_data="adm:categories")
    await message.answer("✅ Переименовано (товары обновлены)." if ok else "⚠️ Имя занято.",
                         reply_markup=b.as_markup())


# ══════════════════════════════════════════════════════════════════════════════
#  ORDERS
# ══════════════════════════════════════════════════════════════════════════════

def _kb_orders(orders: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for o in orders:
        b.row(InlineKeyboardButton(
            text=f"#{o['id']} · {_fmt_price(o.get('total', 0))} · {o.get('customer_name', '—')}",
            callback_data=f"adm:ord_view:{o['id']}",
        ))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"adm:ord_page:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"adm:ord_page:{page+1}"))
    if nav:
        b.row(*nav)
    b.row(InlineKeyboardButton(text="🔍 Поиск по №", callback_data="adm:ord_search"))
    b.row(InlineKeyboardButton(text="🔧 В админ-панель", callback_data="adm:home"))
    return b.as_markup()


@router.callback_query(F.data == "adm:orders")
@router.callback_query(F.data.startswith("adm:ord_page:"))
async def cb_orders(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.clear()
    await callback.answer()
    page = int(callback.data.split(":")[-1]) if callback.data.startswith("adm:ord_page:") else 0
    orders = await orders_service.get_all()
    total_pages = max(1, (len(orders) + PAGE - 1) // PAGE)
    page = max(0, min(page, total_pages - 1))
    chunk = orders[page * PAGE:(page + 1) * PAGE]
    text = f"📋 <b>Заказы</b>\nВсего: <b>{len(orders)}</b> · стр. {page+1}/{total_pages}" if orders \
        else "📋 <b>Заказы</b>\n\nПока нет заказов."
    await safe_edit_message(callback.message, text=text, reply_markup=_kb_orders(chunk, page, total_pages))


@router.callback_query(F.data == "adm:ord_search")
async def cb_ord_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.set_state(AdminOrderStates.search_id)
    await callback.answer()
    await safe_edit_message(callback.message, text="🔍 Введите номер заказа (например 000001 или 1):",
                            reply_markup=kb_home())


@router.message(AdminOrderStates.search_id, F.text)
async def msg_ord_search(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    raw = message.text.strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    oid = f"{int(digits):06d}" if digits else raw
    order = await orders_service.get(oid)
    if order is None:
        b = InlineKeyboardBuilder()
        b.button(text="📋 К заказам", callback_data="adm:orders")
        await message.answer("❌ Заказ не найден.", reply_markup=b.as_markup())
        return
    await message.answer(_order_detail_text(order), reply_markup=_kb_order_back())


def _kb_order_back() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📋 К заказам", callback_data="adm:orders")
    b.button(text="🔧 В админ-панель", callback_data="adm:home")
    b.adjust(1)
    return b.as_markup()


def _order_detail_text(o: dict) -> str:
    items = "\n".join(
        f"• {it.get('name','')} {it.get('dosage','')} × {it.get('qty',1)} — {_fmt_price(it.get('price',0)*it.get('qty',1))}"
        for it in o.get("items", [])
    )
    created = o.get("created_at", "")[:19].replace("T", " ")
    promo = o.get("promo_code")
    discount = o.get("discount", 0)
    promo_line = f"\n🎁 Промокод: {promo} (−{_fmt_price(discount)})" if promo else ""
    return (
        f"📋 <b>Заказ #{o.get('id')}</b>\n\n"
        f"🕒 {created}\n"
        f"👤 {o.get('customer_name','—')}\n"
        f"📬 {o.get('customer_contact','—')}\n"
        f"🌍 {o.get('customer_country','') or '—'}\n"
        f"🔗 @{o.get('username') or '—'} (ID <code>{o.get('user_id')}</code>)\n"
        f"📦 Источник: {o.get('source','—')} · Статус: {o.get('status','—')}\n\n"
        f"{items}\n"
        f"{promo_line}\n"
        f"💰 <b>Итого: {_fmt_price(o.get('total',0))}</b>\n\n"
        f"💬 {o.get('comment','') or '—'}"
    )


@router.callback_query(F.data.startswith("adm:ord_view:"))
async def cb_ord_view(callback: CallbackQuery) -> None:
    if not await _guard_cb(callback):
        return
    await callback.answer()
    oid = callback.data.split(":", 2)[2]
    order = await orders_service.get(oid)
    if order is None:
        await safe_edit_message(callback.message, text="❌ Заказ не найден.", reply_markup=_kb_order_back())
        return
    await safe_edit_message(callback.message, text=_order_detail_text(order), reply_markup=_kb_order_back())


# ══════════════════════════════════════════════════════════════════════════════
#  BROADCASTS  (text / photo+text / video+text)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:broadcasts")
@router.callback_query(F.data == "admin:broadcast")           # legacy alias
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await callback.answer()
    count = await users_service.count()
    await state.set_state(BroadcastStates.waiting_message)
    b = InlineKeyboardBuilder()
    b.button(text="🔧 В админ-панель", callback_data="adm:home")
    await safe_edit_message(
        callback.message,
        text=(
            f"📢 <b>Рассылка</b>\n\nПолучателей: <b>{count}</b>\n\n"
            "Отправьте текст, фото с подписью или видео с подписью.\n"
            "Поддерживается HTML-разметка."
        ),
        reply_markup=b.as_markup(),
    )


@router.message(BroadcastStates.waiting_message)
async def msg_broadcast_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    if message.photo:
        await state.update_data(bc_type="photo", bc_file=message.photo[-1].file_id,
                                bc_caption=message.caption or "")
    elif message.video:
        await state.update_data(bc_type="video", bc_file=message.video.file_id,
                                bc_caption=message.caption or "")
    elif message.text:
        await state.update_data(bc_type="text", bc_text=message.text)
    else:
        await message.answer("⚠️ Поддерживаются текст, фото или видео. Повторите.")
        return
    await state.set_state(BroadcastStates.confirming)
    count = await users_service.count()
    b = InlineKeyboardBuilder()
    b.button(text="✅ Отправить всем", callback_data="adm:bc_confirm")
    b.button(text="❌ Отменить",       callback_data="adm:home")
    b.adjust(1)
    await message.answer(
        f"📋 <b>Подтверждение</b>\n\nПолучателей: <b>{count}</b>\n\n"
        "Сообщение выше — превью. Отправить всем пользователям?",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data == "adm:bc_confirm", BroadcastStates.confirming)
async def cb_broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await _guard_cb(callback):
        return
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    user_ids = await users_service.get_all_user_ids()
    if not user_ids:
        await safe_edit_message(callback.message, text="⚠️ Список пользователей пуст.", reply_markup=kb_home())
        return
    await safe_edit_message(callback.message, text=f"📤 Рассылка для {len(user_ids)} пользователей…")
    ok = fail = 0
    bc_type = data.get("bc_type", "text")
    for uid in user_ids:
        try:
            if bc_type == "photo":
                await bot.send_photo(uid, photo=data["bc_file"], caption=data.get("bc_caption", ""), parse_mode="HTML")
            elif bc_type == "video":
                await bot.send_video(uid, video=data["bc_file"], caption=data.get("bc_caption", ""), parse_mode="HTML")
            else:
                await bot.send_message(uid, text=data["bc_text"], parse_mode="HTML")
            ok += 1
        except Exception as e:
            fail += 1
            logger.warning("Broadcast failed for %d: %s", uid, e)
        await asyncio.sleep(0.05)
    await callback.message.answer(
        f"✅ <b>Рассылка завершена</b>\n\nДоставлено: <b>{ok}</b>\nОшибок: <b>{fail}</b>",
        reply_markup=kb_home(), parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════════════════════
#  USERS
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:users")
@router.callback_query(F.data == "admin:users")               # legacy alias
async def cb_users(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.clear()
    await callback.answer()
    now = time.time()
    total = await users_service.count()
    today = await users_service.count_since(now - 86400)
    week = await users_service.count_since(now - 7 * 86400)
    b = InlineKeyboardBuilder()
    b.button(text="🔍 Карточка пользователя", callback_data="adm:user_search")
    b.button(text="🔧 В админ-панель", callback_data="adm:home")
    b.adjust(1)
    await safe_edit_message(
        callback.message,
        text=(
            "👥 <b>Пользователи</b>\n\n"
            f"Всего: <b>{total}</b>\n"
            f"За сутки: <b>{today}</b>\n"
            f"За неделю: <b>{week}</b>"
        ),
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data == "adm:user_search")
async def cb_user_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.set_state(AdminUserStates.search_id)
    await callback.answer()
    await safe_edit_message(callback.message, text="🔍 Введите Telegram ID пользователя:", reply_markup=kb_home())


@router.message(AdminUserStates.search_id, F.text)
async def msg_user_search(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    digits = "".join(ch for ch in message.text if ch.isdigit())
    b = InlineKeyboardBuilder()
    b.button(text="👥 К пользователям", callback_data="adm:users")
    if not digits:
        await message.answer("⚠️ Введите числовой ID.", reply_markup=b.as_markup())
        return
    uid = int(digits)
    user = await users_service.get_user(uid)
    orders = [o for o in await orders_service.get_all() if o.get("user_id") == uid]
    spend = sum(o.get("total", 0) for o in orders)
    if user is None and not orders:
        await message.answer("❌ Пользователь не найден.", reply_markup=b.as_markup())
        return
    reg = user.get("registered_ts") if user else None
    reg_line = datetime.fromtimestamp(reg, tz=timezone.utc).strftime("%Y-%m-%d") if reg else "—"
    uname = (user or {}).get("username") or "—"
    await message.answer(
        f"👤 <b>Пользователь</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"🔗 @{uname}\n"
        f"📅 Регистрация: {reg_line}\n"
        f"📋 Заказов: <b>{len(orders)}</b>\n"
        f"💰 Сумма заказов: <b>{_fmt_price(spend)}</b>",
        reply_markup=b.as_markup(),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  STATISTICS
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:stats")
@router.callback_query(F.data == "admin:stats")               # legacy alias
async def cb_stats(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.clear()
    await callback.answer()
    users = await users_service.count()
    orders = await orders_service.get_all()
    products = await products_service.get_all_admin()

    sold: dict = {}
    for o in orders:
        for it in o.get("items", []):
            key = it.get("name", "?")
            sold[key] = sold.get(key, 0) + int(it.get("qty", 1))

    top = sorted(sold.items(), key=lambda kv: kv[1], reverse=True)[:5]
    top_lines = "\n".join(f"  {i}. {n} — {q} шт." for i, (n, q) in enumerate(top, 1)) or "  —"

    sold_names = set(sold.keys())
    zero = [p.name for p in products if p.name not in sold_names]
    zero_lines = "\n".join(f"  • {n}" for n in zero[:15]) or "  —"
    zero_more = f"\n  … ещё {len(zero) - 15}" if len(zero) > 15 else ""

    await safe_edit_message(
        callback.message,
        text=(
            "📈 <b>Статистика</b>\n\n"
            f"📋 Заказов: <b>{len(orders)}</b>\n"
            f"👥 Пользователей: <b>{users}</b>\n"
            f"📦 Товаров: <b>{len(products)}</b>\n\n"
            f"🔝 <b>Топ товаров:</b>\n{top_lines}\n\n"
            f"🚫 <b>Без продаж:</b>\n{zero_lines}{zero_more}"
        ),
        reply_markup=kb_home(),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  STORE SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:settings")
async def cb_settings(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.clear()
    await callback.answer()
    b = InlineKeyboardBuilder()
    for key, label in EDITABLE_KEYS.items():
        b.row(InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"adm:set_edit:{key}"))
    b.row(InlineKeyboardButton(text="🔧 В админ-панель", callback_data="adm:home"))
    await safe_edit_message(callback.message, text="⚙️ <b>Настройки магазина</b>\n\nВыберите текст для редактирования:",
                            reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("adm:set_edit:"))
async def cb_set_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    key = callback.data.split(":", 2)[2]
    await state.set_state(AdminSettingsStates.edit_value)
    await state.update_data(set_key=key)
    await callback.answer()
    current = store_settings_service.get(key)
    preview = current if len(current) < 500 else current[:500] + "…"
    await safe_edit_message(
        callback.message,
        text=f"✏️ <b>{EDITABLE_KEYS.get(key, key)}</b>\n\nТекущее значение:\n\n{preview}\n\nОтправьте новый текст:",
        reply_markup=kb_home(),
    )


@router.message(AdminSettingsStates.edit_value, F.text)
async def msg_set_edit(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    await store_settings_service.set(data["set_key"], message.text)
    b = InlineKeyboardBuilder()
    b.button(text="⚙️ К настройкам", callback_data="adm:settings")
    await message.answer("✅ Текст обновлён.", reply_markup=b.as_markup())


# ══════════════════════════════════════════════════════════════════════════════
#  PROMO CODES
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:promo")
async def cb_promo(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.clear()
    await callback.answer()
    codes = await promocodes_service.list_all()
    b = InlineKeyboardBuilder()
    lines = ["🎁 <b>Промокоды</b>\n"]
    if not codes:
        lines.append("Пока нет промокодов.")
    for c in codes:
        val = f"{c['value']}%" if c["kind"] == KIND_PERCENT else _fmt_price(c["value"])
        status = "✅" if c.get("active") else "🚫"
        used = c.get("used_count", 0)
        limit = c.get("usage_limit")
        lim = f"/{limit}" if limit else ""
        lines.append(f"{status} <code>{c['code']}</code> · {val} · использован {used}{lim}")
        if c.get("active"):
            b.row(InlineKeyboardButton(text=f"🚫 Отключить {c['code']}", callback_data=f"adm:promo_off:{c['code']}"))
    b.row(InlineKeyboardButton(text="➕ Создать промокод", callback_data="adm:promo_new"))
    b.row(InlineKeyboardButton(text="🔧 В админ-панель", callback_data="adm:home"))
    await safe_edit_message(callback.message, text="\n".join(lines), reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("adm:promo_off:"))
async def cb_promo_off(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    code = callback.data.split(":", 2)[2]
    await promocodes_service.disable(code)
    await callback.answer("🚫 Отключён")
    await cb_promo(callback, state)


@router.callback_query(F.data == "adm:promo_new")
async def cb_promo_new(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.set_state(AdminPromoStates.code)
    await callback.answer()
    await safe_edit_message(callback.message, text="🎁 Введите код промокода (например SALE10):", reply_markup=kb_home())


@router.message(AdminPromoStates.code, F.text)
async def msg_promo_code(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.update_data(code=message.text.strip().upper())
    b = InlineKeyboardBuilder()
    b.button(text="％ Процент", callback_data="adm:promo_kind:percent")
    b.button(text="₽ Фикс. сумма", callback_data="adm:promo_kind:fixed")
    b.adjust(2)
    await message.answer("Тип скидки:", reply_markup=b.as_markup())


@router.callback_query(AdminPromoStates.code, F.data.startswith("adm:promo_kind:"))
async def cb_promo_kind(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    kind = callback.data.split(":")[-1]
    await state.update_data(kind=kind)
    await state.set_state(AdminPromoStates.value)
    await callback.answer()
    unit = "процент (например 10)" if kind == KIND_PERCENT else "сумму в ₽ (например 500)"
    await safe_edit_message(callback.message, text=f"Введите {unit}:", reply_markup=kb_home())


@router.message(AdminPromoStates.value, F.text)
async def msg_promo_value(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    digits = "".join(ch for ch in message.text if ch.isdigit())
    if not digits:
        await message.answer("⚠️ Введите число.", reply_markup=kb_home())
        return
    await state.update_data(value=int(digits))
    await state.set_state(AdminPromoStates.expiry)
    b = InlineKeyboardBuilder()
    b.button(text="♾ Без срока", callback_data="adm:promo_noexp")
    await message.answer("Срок действия в днях (число) или без срока:", reply_markup=b.as_markup())


async def _promo_ask_limit(target, state: FSMContext) -> None:
    await state.set_state(AdminPromoStates.limit)
    b = InlineKeyboardBuilder()
    b.button(text="♾ Без лимита", callback_data="adm:promo_nolimit")
    text = "Лимит использований (число) или без лимита:"
    if isinstance(target, CallbackQuery):
        await safe_edit_message(target.message, text=text, reply_markup=b.as_markup())
    else:
        await target.answer(text, reply_markup=b.as_markup())


@router.message(AdminPromoStates.expiry, F.text)
async def msg_promo_expiry(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    digits = "".join(ch for ch in message.text if ch.isdigit())
    expires = time.time() + int(digits) * 86400 if digits else None
    await state.update_data(expires_at=expires)
    await _promo_ask_limit(message, state)


@router.callback_query(AdminPromoStates.expiry, F.data == "adm:promo_noexp")
async def cb_promo_noexp(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.update_data(expires_at=None)
    await callback.answer()
    await _promo_ask_limit(callback, state)


async def _promo_finish(target, state: FSMContext, limit: Optional[int]) -> None:
    data = await state.get_data()
    await state.clear()
    ok = await promocodes_service.create(
        code=data["code"], kind=data["kind"], value=data["value"],
        expires_at=data.get("expires_at"), usage_limit=limit,
    )
    b = InlineKeyboardBuilder()
    b.button(text="🎁 К промокодам", callback_data="adm:promo")
    text = f"✅ Промокод <code>{data['code']}</code> создан." if ok else "⚠️ Такой код уже существует."
    if isinstance(target, CallbackQuery):
        await safe_edit_message(target.message, text=text, reply_markup=b.as_markup())
    else:
        await target.answer(text, reply_markup=b.as_markup())


@router.message(AdminPromoStates.limit, F.text)
async def msg_promo_limit(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    digits = "".join(ch for ch in message.text if ch.isdigit())
    await _promo_finish(message, state, int(digits) if digits else None)


@router.callback_query(AdminPromoStates.limit, F.data == "adm:promo_nolimit")
async def cb_promo_nolimit(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await callback.answer()
    await _promo_finish(callback, state, None)


# ══════════════════════════════════════════════════════════════════════════════
#  BACKUPS
# ══════════════════════════════════════════════════════════════════════════════

BACKUP_FILES = ["products.json", "categories.json", "settings.json",
                "promocodes.json", "orders.json", "users.json"]


@router.callback_query(F.data == "adm:backups")
async def cb_backups(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.clear()
    await callback.answer()
    b = InlineKeyboardBuilder()
    b.button(text="📥 Создать и скачать", callback_data="adm:backup_make")
    b.button(text="📤 Восстановить из файла", callback_data="adm:backup_restore")
    b.button(text="🔧 В админ-панель", callback_data="adm:home")
    b.adjust(1)
    await safe_edit_message(
        callback.message,
        text="🛡 <b>Бэкапы</b>\n\nСоздайте резервную копию данных магазина или восстановите её из ZIP-файла.",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data == "adm:backup_make")
async def cb_backup_make(callback: CallbackQuery, bot: Bot) -> None:
    if not await _guard_cb(callback):
        return
    await callback.answer("📦 Готовлю архив…")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in BACKUP_FILES:
            path = cfg.data_dir / name
            if path.exists():
                zf.write(path, arcname=name)
    buf.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    file = BufferedInputFile(buf.read(), filename=f"genesis-backup-{stamp}.zip")
    await bot.send_document(callback.from_user.id, document=file,
                            caption="🛡 Резервная копия данных магазина.")


@router.callback_query(F.data == "adm:backup_restore")
async def cb_backup_restore(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(callback):
        return
    await state.set_state(AdminBackupStates.waiting_file)
    await callback.answer()
    await safe_edit_message(
        callback.message,
        text="📤 Пришлите ZIP-файл бэкапа документом. Файлы данных будут заменены.",
        reply_markup=kb_home(),
    )


@router.message(AdminBackupStates.waiting_file, F.document)
async def msg_backup_restore(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    doc = message.document
    if not (doc.file_name or "").lower().endswith(".zip"):
        await message.answer("⚠️ Нужен ZIP-файл.", reply_markup=kb_home())
        return
    buf = io.BytesIO()
    await bot.download(doc, destination=buf)
    buf.seek(0)
    restored = []
    try:
        with zipfile.ZipFile(buf) as zf:
            for name in zf.namelist():
                base = name.split("/")[-1]
                if base in BACKUP_FILES:
                    data = zf.read(name)
                    target = cfg.data_dir / base
                    tmp = cfg.data_dir / f"{base}.tmp"
                    tmp.write_bytes(data)
                    tmp.replace(target)
                    restored.append(base)
    except Exception as e:
        logger.exception("Backup restore failed: %s", e)
        await message.answer(f"❌ Ошибка восстановления: {e}", reply_markup=kb_home())
        return
    # Force services to reload from the restored files on next access.
    products_service.invalidate_cache()
    for svc in (categories_service, promocodes_service):
        svc._loaded = False
    store_settings_service._loaded = False
    users_service._loaded = False
    orders_service._loaded = False
    b = InlineKeyboardBuilder()
    b.button(text="🔧 В админ-панель", callback_data="adm:home")
    await message.answer(
        f"✅ Восстановлено: {', '.join(restored) or '—'}.\nДанные перезагружены.",
        reply_markup=b.as_markup(),
    )
