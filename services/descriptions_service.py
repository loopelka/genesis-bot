"""
services/descriptions_service.py — Optional product descriptions loaded from
products_descriptions.json.

Format (one record per unique drug):
    {
      "ids": [1, 2, 3],
      "name": "...",
      "category": "...",
      "short_description": "...",
      "description": "...",
      "key_points": [...],
      "effects": [...],
      "research_areas": [...]
    }

Lookup is strictly by product_id via each record's ids[]. The data is static
and trusted, but field values are HTML-escaped at render time for safety, since
product cards are sent with HTML parse mode. If a product_id has no description,
render_block() returns None and the card is shown unchanged.
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
        self._by_id: Dict[int, dict] = {}
        self._loaded = False

    # ── Loading ───────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load and index descriptions by product_id. Safe to call at startup."""
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
            records = 0
            for rec in data:
                if not isinstance(rec, dict):
                    continue
                for pid in rec.get("ids", []) or []:
                    try:
                        self._by_id[int(pid)] = rec
                    except (TypeError, ValueError):
                        continue
                records += 1
            logger.info(
                "Loaded descriptions: %d drugs → %d product_ids",
                records, len(self._by_id),
            )
        except Exception as e:
            logger.error("Could not load %s: %s", DESCRIPTIONS_FILE, e)
            self._by_id = {}
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ── Public API ──────────────────────────────────────────────────────────────

    def get(self, product_id: int) -> Optional[dict]:
        """Return the description record for a product_id, or None."""
        self._ensure_loaded()
        try:
            return self._by_id.get(int(product_id))
        except (TypeError, ValueError):
            return None

    def render_block(self, product_id: int) -> Optional[str]:
        """
        Build the HTML block shown on a product card:
        short_description, key_points and research_areas.
        Returns None if there is no description for this product_id.
        """
        rec = self.get(product_id)
        if not rec:
            return None

        parts: List[str] = []

        short = rec.get("short_description")
        if short:
            parts.append(f"📝 <i>{html.escape(str(short))}</i>")

        key_points = rec.get("key_points") or []
        if key_points:
            lines = "\n".join(f"• {html.escape(str(p))}" for p in key_points)
            parts.append(f"🔎 <b>Кратко:</b>\n{lines}")

        research_areas = rec.get("research_areas") or []
        if research_areas:
            joined = ", ".join(html.escape(str(a)) for a in research_areas)
            parts.append(f"🧪 <b>Направления исследований:</b> {joined}")

        return "\n\n".join(parts) if parts else None


descriptions_service = DescriptionsService()
