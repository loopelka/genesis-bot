"""
services/models.py — Domain models for Genesis Peptide Store.
"""
from dataclasses import dataclass, field
from typing import Optional


# ─── Canonical category names ────────────────────────────────────────────────
CATEGORY_VIALS = "Виалки"
CATEGORY_SPRAYS = "Спреи"
CATEGORY_SUPPLIES = "Расходники"
CATEGORY_CONSULT = "Консультация"

ALL_CATEGORIES = [CATEGORY_VIALS, CATEGORY_SPRAYS, CATEGORY_SUPPLIES, CATEGORY_CONSULT]

CATEGORY_EMOJI = {
    CATEGORY_VIALS: "💉",
    CATEGORY_SPRAYS: "🫧",
    CATEGORY_SUPPLIES: "🧰",
    CATEGORY_CONSULT: "🩺",
}


@dataclass
class Product:
    """Represents a single product row from products.xlsx."""
    product_id: int
    category: str
    name: str
    dosage: str
    price: int
    stock: int
    photo_id: str

    @property
    def in_stock(self) -> bool:
        return self.stock > 0

    @property
    def stock_label(self) -> str:
        if self.stock == 0:
            return "❌ Нет в наличии"
        if self.stock <= 3:
            return f"⚠️ Мало: {self.stock} шт."
        return f"✅ В наличии: {self.stock} шт."

    @property
    def price_formatted(self) -> str:
        return f"{self.price:,}".replace(",", " ") + " ₽"

    def card_text(self) -> str:
        emoji = CATEGORY_EMOJI.get(self.category, "📦")
        lines = [
            f"{emoji} <b>{self.name}</b>",
            f"",
            f"📂 <b>Категория:</b> {self.category}",
            f"⚗️ <b>Дозировка:</b> {self.dosage}",
            f"💰 <b>Цена:</b> {self.price_formatted}",
            f"{self.stock_label}",
        ]
        return "\n".join(lines)

    @classmethod
    def from_row(cls, row: list) -> Optional["Product"]:
        """
        Parse a products.xlsx row into a Product.
        Columns: ID | Category | Name | Dosage | Price | Stock | Photo
        Indices:  0  |    1    |  2   |   3    |   4   |   5   |   6
        """
        try:
            while len(row) < 7:
                row.append("")

            product_id = int(str(row[0]).strip())
            category = str(row[1]).strip()
            name = str(row[2]).strip()
            dosage = str(row[3]).strip()
            price_raw = str(row[4]).strip().replace(" ", "").replace(",", "")
            price = int(price_raw) if price_raw.isdigit() else 0
            stock_raw = str(row[5]).strip()
            stock = int(stock_raw) if stock_raw.isdigit() else 0
            photo_id = str(row[6]).strip()

            if not name or not category:
                return None

            return cls(
                product_id=product_id,
                category=category,
                name=name,
                dosage=dosage,
                price=price,
                stock=stock,
                photo_id=photo_id,
            )
        except (ValueError, IndexError):
            return None


@dataclass
class OrderForm:
    """Collects user input during the order flow."""
    product_id: int
    product_name: str
    user_id: int
    username: Optional[str] = None
    customer_name: str = ""
    customer_contact: str = ""
    comment: str = ""

    def admin_notification(self) -> str:
        username_line = f"@{self.username}" if self.username else "нет username"
        return (
            f"🛒 <b>НОВЫЙ ЗАКАЗ</b>\n\n"
            f"🆔 ID товара: <code>{self.product_id}</code>\n"
            f"📦 Товар: <b>{self.product_name}</b>\n\n"
            f"👤 Покупатель: {self.customer_name}\n"
            f"📬 Контакт: {self.customer_contact}\n"
            f"🔗 Telegram: {username_line} (ID: <code>{self.user_id}</code>)\n"
            f"💬 Комментарий: {self.comment or '—'}"
        )
