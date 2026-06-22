"""
api/catalog_api.py — Mini App data access layer.

Pure async functions over the existing single source of truth
(products.xlsx + products_descriptions.json + related_products.json), reusing
products_service / descriptions_service / related_service. No HTTP, no frontend.

Intended REST mapping (see docs/MINIAPP_API.md):
    GET /api/categories          -> get_categories()
    GET /api/catalog             -> get_catalog()
    GET /api/product/{id}        -> get_product(id)
    GET /api/drug/{name}         -> get_drug(name)
    GET /api/related/{name}      -> get_related(name)
"""
from typing import List, Optional

from services import products_service
from services.descriptions_service import descriptions_service
from services.related_service import related_service
from services.models import CATEGORY_EMOJI, ALL_CATEGORIES
from .schema import ProductDTO, DrugDTO, CategoryDTO


def _to_product_dto(p) -> ProductDTO:
    return ProductDTO(
        id=p.product_id,
        name=p.name,
        category=p.category,
        dosage=p.dosage,
        price=p.price,
        price_formatted=p.price_formatted,
        in_stock=p.in_stock,
        stock_label=p.stock_label,
    )


async def get_categories() -> List[dict]:
    """All categories present in the catalog with drug/SKU counts."""
    products = await products_service.get_all_products()
    out: List[CategoryDTO] = []
    for cat in ALL_CATEGORIES:
        skus = [p for p in products if p.category == cat]
        if not skus:
            continue
        drugs = {p.name for p in skus}
        out.append(CategoryDTO(
            name=cat,
            emoji=CATEGORY_EMOJI.get(cat, "📦"),
            drug_count=len(drugs),
            sku_count=len(skus),
        ))
    return [c.to_dict() for c in out]


async def get_drug(name: str) -> Optional[dict]:
    """One drug aggregated: description + effects + related + all dosage variants."""
    products = await products_service.get_all_products()
    variants = [p for p in products if p.name.lower() == str(name).strip().lower()]
    if not variants:
        return None
    variants.sort(key=lambda p: p.price)
    desc = descriptions_service.get(name=variants[0].name) or {}
    drug = DrugDTO(
        name=variants[0].name,
        category=variants[0].category,
        short_description=desc.get("short_description", ""),
        description=desc.get("description", ""),
        key_points=list(desc.get("key_points", []) or []),
        effects=list(desc.get("effects", []) or []),
        research_areas=list(desc.get("research_areas", []) or []),
        related=related_service.get_related(variants[0].name),
        variants=[_to_product_dto(p) for p in variants],
    )
    return drug.to_dict()


async def get_catalog() -> List[dict]:
    """Full catalog grouped by category → drugs (each drug aggregated)."""
    products = await products_service.get_all_products()
    result: List[dict] = []
    for cat in ALL_CATEGORIES:
        drug_names: List[str] = []
        for p in products:
            if p.category == cat and p.name not in drug_names:
                drug_names.append(p.name)
        if not drug_names:
            continue
        drugs = [await get_drug(n) for n in drug_names]
        result.append({
            "category": cat,
            "emoji": CATEGORY_EMOJI.get(cat, "📦"),
            "drugs": [d for d in drugs if d],
        })
    return result


async def get_product(product_id: int) -> Optional[dict]:
    """One SKU by id, with its drug-level description attached."""
    p = await products_service.get_product_by_id(int(product_id))
    if p is None:
        return None
    dto = _to_product_dto(p).to_dict()
    desc = descriptions_service.get(name=p.name, product_id=p.product_id) or {}
    dto["short_description"] = desc.get("short_description", "")
    dto["effects"] = list(desc.get("effects", []) or [])
    dto["related"] = related_service.get_related(p.name)
    return dto


async def get_related(name: str) -> List[str]:
    """Related drug names for a drug name."""
    return related_service.get_related(name)
