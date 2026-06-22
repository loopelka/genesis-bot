"""
services/descriptions_service.py — Product descriptions, single source of truth.

Data file: products_descriptions.json — ONE record per unique drug (not per SKU).
Each record:
    {
      "ids": [1, 2, 3],            # SKU ids of this drug (for validation)
      "name": "...",               # MUST match products.xlsx column C (drug name)
      "category": "...",
      "short_description": "...",
      "description": "...",         # reserved for Mini App
      "key_points": [...],         # reserved for Mini App
      "effects": [...],            # shown on the product card
      "research_areas": [...]      # reserved for Mini App
    }

Mapping (Э6): lookup is PRIMARILY by drug name (product.name == column C); the
per-record ids[] are kept as a secondary key for validation and as a fallback.
Field values are HTML-escaped at render time (cards use HTML parse mode).
If a product has no description, render_block() returns None and the card is
shown unchanged.
"""
import html
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DESCRIPTIONS_FILE = Path("products_descriptions.json")


class DescriptionsService:
    def __init__(self) -> None:
        self._by_name: Dict[str, dict] = {}
        self._by_id: Dict[int, dict] = {}
        self._loaded = False

    # ── Loading ───────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load and index descriptions by drug name and by product_id."""
        self._by_name = {}
        self._by_id = {}
        if not DESCRIPTIONS_FILE.exists():
            logger.warning(
                "%s not found — product cards will render without descriptions",
                DESCRIPTIONS_FILE,
            )
            self._loaded = True
            return
        try:
            data = json.loads(DESCRIPTIONS_FILE.read_text(encoding="utf-8"))
            drugs = 0
            for rec in data:
                if not isinstance(rec, dict):
                    continue
                name = (rec.get("name") or "").strip()
                if name:
                    self._by_name[name.lower()] = rec
                for pid in rec.get("ids", []) or []:
                    try:
                        self._by_id[int(pid)] = rec
                    except (TypeError, ValueError):
                        continue
                drugs += 1
            logger.info(
                "Loaded descriptions: %d drugs → %d product_ids",
                drugs, len(self._by_id),
            )
        except Exception as e:
            logger.error("Could not load %s: %s", DESCRIPTIONS_FILE, e)
            self._by_name = {}
            self._by_id = {}
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get_by_name(self, name: Optional[str]) -> Optional[dict]:
        self._ensure_loaded()
        if not name:
            return None
        return self._by_name.get(str(name).strip().lower())

    def get_by_id(self, product_id: int) -> Optional[dict]:
        self._ensure_loaded()
        try:
            return self._by_id.get(int(product_id))
        except (TypeError, ValueError):
            return None

    def get(self, name: Optional[str] = None, product_id: Optional[int] = None) -> Optional[dict]:
        """Resolve a description record — by name first (Э6), then by id."""
        rec = self.get_by_name(name)
        if rec is None and product_id is not None:
            rec = self.get_by_id(product_id)
        return rec

    # ── Rendering (Э8: short_description + effects) ───────────────────────────

    def render_block(self, name: Optional[str] = None,
                     product_id: Optional[int] = None) -> Optional[str]:
        """
        Build the product-card block: short description + main effects.
        Returns None if there is no description for this product.
        """
        rec = self.get(name=name, product_id=product_id)
        if not rec:
            return None

        parts: List[str] = []

        short = rec.get("short_description")
        if short:
            parts.append(f"📝 <i>{html.escape(str(short))}</i>")

        effects = rec.get("effects") or []
        if effects:
            lines = "\n".join(f"• {html.escape(str(e))}" for e in effects)
            parts.append(f"✨ <b>Основные эффекты:</b>\n{lines}")

        return "\n\n".join(parts) if parts else None

    # ── Validation (Э6: cross-check 47 drugs ↔ 104 SKU) ───────────────────────

    def validate_names(self, product_names) -> Dict[str, List[str]]:
        """
        Compare description names against the live set of catalog drug names.
        Returns {"missing_description": [...], "orphan_description": [...]}.
        Logs a warning on any mismatch (closes the silent-miss risk).
        """
        self._ensure_loaded()
        catalog = {str(n).strip().lower(): str(n) for n in product_names}
        described = set(self._by_name.keys())
        missing = sorted(catalog[k] for k in catalog.keys() - described)
        orphan = sorted(self._by_name[k].get("name", k) for k in described - catalog.keys())
        if missing:
            logger.warning("Descriptions MISSING for %d drugs: %s", len(missing), missing)
        if orphan:
            logger.warning("Descriptions ORPHANED (no SKU): %d: %s", len(orphan), orphan)
        if not missing and not orphan:
            logger.info("Descriptions ↔ catalog: all %d drugs matched", len(described))
        return {"missing_description": missing, "orphan_description": orphan}


descriptions_service = DescriptionsService()
