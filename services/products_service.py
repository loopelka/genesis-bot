"""
services/products_service.py — Reads products from local products.xlsx (openpyxl).

Public interface:
    products_service.get_all_products()
    products_service.get_products_by_category(category)
    products_service.get_product_by_id(product_id)
    products_service.get_available_categories()
    products_service.invalidate_cache()
    products_service.last_error

Table structure (row 1 = headers, data from row 2):
    A: ID | B: Category | C: Name | D: Dosage | E: Price | F: Stock | G: Photo
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Optional

import openpyxl
from cachetools import TTLCache

from config.settings import settings
from services.models import Product

logger = logging.getLogger(__name__)

XLSX_PATH = Path(settings.products_file)


class ProductsService:
    def __init__(self) -> None:
        self._cache: TTLCache = TTLCache(maxsize=1, ttl=settings.cache_ttl)
        self._lock = asyncio.Lock()
        self._last_error: Optional[str] = None

    def _read_xlsx(self) -> List[List]:
        if not XLSX_PATH.exists():
            raise FileNotFoundError(
                f"File not found: {XLSX_PATH.resolve()}\n"
                f"Create products.xlsx in the project root."
            )

        wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
        ws = wb.active

        rows = []
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            cells = [str(cell).strip() if cell is not None else "" for cell in row]
            if all(c == "" for c in cells):
                continue
            rows.append(cells)
            logger.debug("Read row %d: %s", i, cells)

        wb.close()
        return rows

    async def get_all_products(self) -> List[Product]:
        async with self._lock:
            if "products" in self._cache:
                return self._cache["products"]

            try:
                loop = asyncio.get_event_loop()
                rows = await loop.run_in_executor(None, self._read_xlsx)

                products: List[Product] = []
                for i, row in enumerate(rows, start=2):
                    product = Product.from_row(row)
                    if product is not None:
                        products.append(product)
                    else:
                        logger.warning("Skipped invalid row %d: %s", i, row)

                self._cache["products"] = products
                self._last_error = None
                logger.info("Loaded %d products from %s", len(products), XLSX_PATH.name)
                return products

            except FileNotFoundError as e:
                self._last_error = str(e)
                logger.error(self._last_error)
                return []

            except Exception as e:
                self._last_error = str(e)
                logger.exception("Error reading %s: %s", XLSX_PATH.name, e)
                return self._cache.get("products", [])

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

    def invalidate_cache(self) -> None:
        self._cache.clear()
        logger.info("Product cache cleared")

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error


products_service = ProductsService()
