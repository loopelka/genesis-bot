"""
handlers/info.py — Static information pages: delivery, payment, price list.
"""
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards import kb_back_to_main, kb_price_list
from services import products_service
from services.models import CATEGORY_EMOJI
from utils.helpers import safe_edit_message

logger = logging.getLogger(__name__)
router = Router(name="info")

# ── Delivery ──────────────────────────────────────────────────────────────────

DELIVERY_TEXT = (
    "🚚 <b>Доставка</b>\n\n"
    "📦 Курьерская служба: <b>СДЭК</b>\n"
    "⏱ Срок доставки: <b>3–6 рабочих дней</b>\n"
    "📍 Доставляем по всей России\n\n"
    "🔖 Трек-номер для отслеживания предоставляется сразу после отправки заказа.\n\n"
    "📞 По вопросам доставки обращайтесь к менеджеру."
)


@router.callback_query(F.data == "menu:delivery")
async def cb_delivery(callback: CallbackQuery) -> None:
    await callback.answer()
    await safe_edit_message(
        message=callback.message,
        text=DELIVERY_TEXT,
        reply_markup=kb_back_to_main(),
    )


# ── Payment ───────────────────────────────────────────────────────────────────

PAYMENT_TEXT = (
    "💳 <b>Оплата</b>\n\n"
    "После оформления заказа с вами свяжется менеджер для уточнения деталей и оплаты.\n\n"
    "💰 <b>Доступные способы оплаты:</b>\n"
    "• Банковский перевод (СБП)\n"
    "• Карта Сбербанк / Тинькофф\n"
    "• Криптовалюта (USDT, BTC)\n\n"
    "🧾 По запросу предоставляем чек об оплате."
)


@router.callback_query(F.data == "menu:payment")
async def cb_payment(callback: CallbackQuery) -> None:
    await callback.answer()
    await safe_edit_message(
        message=callback.message,
        text=PAYMENT_TEXT,
        reply_markup=kb_back_to_main(),
    )


# ── Price List ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:price")
async def cb_price_list(callback: CallbackQuery) -> None:
    """Generate dynamic price list from products.xlsx grouped by category."""
    await callback.answer()

    all_products = await products_service.get_all_products()

    if not all_products:
        await safe_edit_message(
            message=callback.message,
            text=(
                "💰 <b>Прайс-лист Genesis Peptide Store</b>\n\n"
                "😔 Данные временно недоступны.\n"
                "Попробуйте позже или откройте каталог."
            ),
            reply_markup=kb_price_list(),
        )
        return

    # Group by category
    categories: dict[str, list] = {}
    for p in all_products:
        categories.setdefault(p.category, []).append(p)

    lines = ["💰 <b>Прайс-лист Genesis Peptide Store</b>\n"]
    for category, products in categories.items():
        emoji = CATEGORY_EMOJI.get(category, "📦")
        lines.append(f"\n{emoji} <b>{category}</b>")
        for p in products:
            stock_icon = "✅" if p.in_stock else "❌"
            lines.append(f"  {stock_icon} {p.name} {p.dosage} — {p.price_formatted}")

    lines.append("\n\n📦 Для заказа откройте Каталог.")
    text = "\n".join(lines)

    # Telegram message limit is 4096 chars — trim if needed
    if len(text) > 4000:
        text = text[:3990] + "\n\n…(полный список в каталоге)"

    await safe_edit_message(
        message=callback.message,
        text=text,
        reply_markup=kb_price_list(),
    )
