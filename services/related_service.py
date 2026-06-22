"""
services/related_service.py — Related-product recommendations.

Data file: related_products.json — a manual association table keyed by drug
NAME (not SKU):  { "<drug name>": ["<related drug>", ...] }

Recommendations are by drug name so a single entry covers all SKU/dosages of a
drug. Missing entries simply yield no recommendations (graceful).
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

RELATED_FILE = Path("related_products.json")


class RelatedService:
    def __init__(self) -> None:
        self._by_name: Dict[str, List[str]] = {}
        self._loaded = False

    def load(self) -> None:
        self._by_name = {}
        if not RELATED_FILE.exists():
            logger.warning("%s not found — no related-product recommendations", RELATED_FILE)
            self._loaded = True
            return
        try:
            data = json.loads(RELATED_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for name, rel in data.items():
                    if isinstance(rel, list):
                        self._by_name[str(name).strip().lower()] = [str(x) for x in rel]
            logger.info("Loaded related products for %d drugs", len(self._by_name))
        except Exception as e:
            logger.error("Could not load %s: %s", RELATED_FILE, e)
            self._by_name = {}
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def get_related(self, name: Optional[str], limit: int = 4) -> List[str]:
        """Return up to `limit` related drug names for a drug name."""
        self._ensure_loaded()
        if not name:
            return []
        return list(self._by_name.get(str(name).strip().lower(), [])[:limit])


related_service = RelatedService()
