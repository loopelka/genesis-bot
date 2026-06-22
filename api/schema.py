"""
api/schema.py — JSON-serializable DTOs for the Mini App data contract.

Plain dataclasses (no external deps) with .to_dict(). A future FastAPI layer can
swap these for pydantic models without changing the catalog_api functions.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class ProductDTO:
    """One SKU (a single dosage variant of a drug)."""
    id: int
    name: str
    category: str
    dosage: str
    price: int
    price_formatted: str
    in_stock: bool
    stock_label: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DrugDTO:
    """A unique drug: aggregated SKUs + description + related drugs."""
    name: str
    category: str
    short_description: str = ""
    description: str = ""
    key_points: List[str] = field(default_factory=list)
    effects: List[str] = field(default_factory=list)
    research_areas: List[str] = field(default_factory=list)
    related: List[str] = field(default_factory=list)
    variants: List[ProductDTO] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["variants"] = [v.to_dict() if isinstance(v, ProductDTO) else v
                         for v in self.variants]
        return d


@dataclass
class CategoryDTO:
    name: str
    emoji: str
    drug_count: int
    sku_count: int

    def to_dict(self) -> dict:
        return asdict(self)
