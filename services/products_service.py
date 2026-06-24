"""
services/products_service.py — Products store.

Source of truth: data/products.json (in settings.data_dir, persisted on the
deploy volume). On first run it is migrated once from the legacy products.xlsx
(openpyxl), after which all admin edits persist to JSON.

Public (customer-facing) interface — unchanged signatures:
    products_service.get_all_products()            # visible only (excludes hidden)
    products_service.get_products_by_category(category)
    products_service.get_product_by_id(product_id)
    products_service.get_available_categories()
    products_service.get_drug_names_by_category(category)
    products_service.get_products_by_drug(category, drug_name)
    products_service.invalidate_cache()
    products_service.last_error

Admin interface (additive):
    get_all_admin(), add_product(...), update_product(...), delete_product(id),
    set_hidden(id, hidden), clone_product(id), search(query),
    bulk_price_change(category, percent), rename_category(old, new)

Legacy xlsx table: A:ID | B:Category | C:Name | D:Dosage | E:Price | F:Stock | G:Photo
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import List, Optional

import openpyxl

from config.settings import settings
from services.models import Product

logger = logging.getLogger(__name__)

XLSX_PATH = Path(settings.products_file)
PRODUCTS_FILE = settings.data_dir / "products.json"


class ProductsService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._products: List[Product] = []
        self._loaded = False
        self._last_error: Optional[str] = None

    # ── Internal I/O ────────────────────────────────────────────────────────────

    def _read_xlsx(self) -> List[Product]:
        """Read legacy products.xlsx into Product objects (migration only)."""
        wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
        ws = wb.active
        products: List[Product] = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            cells = [str(cell).strip() if cell is not None else "" for cell in row]
            if all(c == "" for c in cells):
                continue
            product = Product.from_row(list(cells))
            if product is not None:
                products.append(product)
        wb.close()
        return products

    def _load_sync(self) -> None:
        """Load products from JSON; migrate once from xlsx if JSON is absent."""
        if PRODUCTS_FILE.exists():
            try:
                data = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
                self._products = [
                    p for p in (Product.from_dict(d) for d in data) if p is not None
                ]
                self._last_error = None
                logger.info("Loaded %d products from %s", len(self._products), PRODUCTS_FILE.name)
            except Exception as e:
                logger.warning("Could not load products.json: %s", e)
                try:
                    backup = Path(f"{PRODUCTS_FILE}.corrupt.{int(time.time())}")
                    PRODUCTS_FILE.replace(backup)
                    logger.error("Backed up corrupt products.json to %s", backup)
                except Exception as backup_err:
                    logger.error("Could not back up corrupt products.json: %s", backup_err)
                self._products = []
                self._last_error = str(e)
        elif XLSX_PATH.exists():
            try:
                self._products = self._read_xlsx()
                self._save_sync()
                self._last_error = None
                logger.info(
                    "Migrated %d products from %s -> %s",
                    len(self._products), XLSX_PATH.name, PRODUCTS_FILE.name,
                )
            except Exception as e:
                self._products = []
                self._last_error = str(e)
                logger.exception("Migration from %s failed: %s", XLSX_PATH.name, e)
        else:
            self._products = []
            self._last_error = f"No products source found ({PRODUCTS_FILE} / {XLSX_PATH})"
            logger.error(self._last_error)
        self._loaded = True

    def _save_sync(self) -> None:
        try:
            tmp = Path(f"{PRODUCTS_FILE}.tmp")
            tmp.write_text(
                json.dumps([p.to_dict() for p in self._products], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, PRODUCTS_FILE)
        except Exception as e:
            logger.error("Could not save products.json: %s", e)

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            await asyncio.get_event_loop().run_in_executor(None, self._load_sync)

    async def _save(self) -> None:
        await asyncio.get_event_loop().run_in_executor(None, self._save_sync)

    # ── Customer-facing API (visible products only) ─────────────────────────────

    async def get_all_products(self) -> List[Product]:
        async with self._lock:
            await self._ensure_loaded()
            return [p for p in self._products if not p.hidden]

    async def get_products_by_category(self, category: str) -> List[Product]:
        all_products = await self.get_all_products()
        return [p for p in all_products if p.category.lower() == category.lower()]

    async def get_product_by_id(self, product_id: int) -> Optional[Product]:
        all_products = await self.get_all_products()
        for product in all_products:
            if product.product_id == product_id:
                return product
        return None

    async def get_available_categories(self) -> List[str]:
        all_products = await self.get_all_products()
        seen: List[str] = []
        for p in all_products:
            if p.category not in seen:
                seen.append(p.category)
        return seen

    async def get_drug_names_by_category(self, category: str) -> List[str]:
        products = await self.get_products_by_category(category)
        seen: List[str] = []
        for p in products:
            if p.name not in seen:
                seen.append(p.name)
        return seen

    async def get_products_by_drug(self, category: str, drug_name: str) -> List[Product]:
        products = await self.get_products_by_category(category)
        variants = [p for p in products if p.name.lower() == drug_name.lower()]
        return sorted(variants, key=lambda p: p.price)

    def invalidate_cache(self) -> None:
        self._loaded = False
        logger.info("Product cache invalidated (will reload from disk)")

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    # ── Admin API (additive) ────────────────────────────────────────────────────

    async def get_all_admin(self) -> List[Product]:
        """All products including hidden ones (admin view)."""
        async with self._lock:
            await self._ensure_loaded()
            return list(self._products)

    async def get_admin_by_id(self, product_id: int) -> Optional[Product]:
        async with self._lock:
            await self._ensure_loaded()
            for p in self._products:
                if p.product_id == product_id:
                    return p
            return None

    def _next_id(self) -> int:
        return (max((p.product_id for p in self._products), default=0)) + 1

    async def add_product(
        self, *, category: str, name: str, dosage: str, price: int,
        description: str = "", stock: int = 999, photo_id: str = "",
    ) -> Product:
        async with self._lock:
            await self._ensure_loaded()
            product = Product(
                product_id=self._next_id(), category=category, name=name,
                dosage=dosage, price=int(price), stock=int(stock),
                photo_id=photo_id, hidden=False, description=description,
            )
            self._products.append(product)
            await self._save()
            logger.info("Product added: id=%d %s", product.product_id, name)
            return product

    async def update_product(self, product_id: int, **fields) -> Optional[Product]:
        """Update editable fields: category, name, dosage, price, description."""
        allowed = {"category", "name", "dosage", "price", "description"}
        async with self._lock:
            await self._ensure_loaded()
            for p in self._products:
                if p.product_id == product_id:
                    for k, v in fields.items():
                        if k not in allowed:
                            continue
                        if k == "price":
                            v = int(v)
                        setattr(p, k, v)
                    await self._save()
                    logger.info("Product updated: id=%d", product_id)
                    return p
            return None

    async def delete_product(self, product_id: int) -> bool:
        async with self._lock:
            await self._ensure_loaded()
            before = len(self._products)
            self._products = [p for p in self._products if p.product_id != product_id]
            if len(self._products) != before:
                await self._save()
                logger.info("Product deleted: id=%d", product_id)
                return True
            return False

    async def set_hidden(self, product_id: int, hidden: bool) -> Optional[Product]:
        async with self._lock:
            await self._ensure_loaded()
            for p in self._products:
                if p.product_id == product_id:
                    p.hidden = bool(hidden)
                    await self._save()
                    return p
            return None

    async def clone_product(self, product_id: int) -> Optional[Product]:
        async with self._lock:
            await self._ensure_loaded()
            src = next((p for p in self._products if p.product_id == product_id), None)
            if src is None:
                return None
            d = src.to_dict()
            d["product_id"] = self._next_id()
            d["name"] = f"{src.name} (копия)"
            clone = Product.from_dict(d)
            self._products.append(clone)
            await self._save()
            logger.info("Product cloned: %d -> %d", product_id, clone.product_id)
            return clone

    async def search(self, query: str) -> List[Product]:
        """Search admin products by name (case-insensitive substring)."""
        q = query.strip().lower()
        async with self._lock:
            await self._ensure_loaded()
            return [p for p in self._products if q in p.name.lower()]

    async def bulk_price_change(self, category: Optional[str], percent: float) -> int:
        """Apply a percentage change to prices. category=None → all products.
        Returns the number of products affected."""
        async with self._lock:
            await self._ensure_loaded()
            factor = 1 + percent / 100.0
            affected = 0
            for p in self._products:
                if category is None or p.category.lower() == category.lower():
                    p.price = max(0, int(round(p.price * factor)))
                    affected += 1
            if affected:
                await self._save()
            logger.info("Bulk price change %+.1f%% on %s: %d affected",
                        percent, category or "ALL", affected)
            return affected

    async def rename_category(self, old: str, new: str) -> int:
        """Cascade a category rename across all products. Returns count changed."""
        async with self._lock:
            await self._ensure_loaded()
            changed = 0
            for p in self._products:
                if p.category == old:
                    p.category = new
                    changed += 1
            if changed:
                await self._save()
            return changed

    async def category_counts(self) -> dict:
        """Map of category -> product count (admin, includes hidden)."""
        async with self._lock:
            await self._ensure_loaded()
            counts: dict = {}
            for p in self._products:
                counts[p.category] = counts.get(p.category, 0) + 1
            return counts


products_service = ProductsService()
