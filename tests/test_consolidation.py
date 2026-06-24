"""
tests/test_consolidation.py — Unified-state consolidation coverage:
  • JsonFileStorage FSM persistence (survives a simulated restart)
  • related_products.json service + integrity
  • Mini App api/ layer
  • admin panel smoke
"""
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ADMIN_ID", "1")


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── FSM: JsonFileStorage persists across restart ──────────────────────────────

def test_fsm_storage_persists_across_restart(tmp_path):
    from services.fsm_storage import JsonFileStorage
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.context import FSMContext
    from utils.states import CartCheckoutStates

    path = tmp_path / "fsm_state.json"
    key = StorageKey(bot_id=1, chat_id=100, user_id=200)

    async def scenario():
        s1 = JsonFileStorage(path)
        ctx1 = FSMContext(storage=s1, key=key)
        await ctx1.set_state(CartCheckoutStates.waiting_name)
        await ctx1.update_data(customer_name="Иван", country="DE")
        await s1.close()

        # New instance = simulated restart; state must survive.
        s2 = JsonFileStorage(path)
        ctx2 = FSMContext(storage=s2, key=key)
        assert await ctx2.get_state() == "CartCheckoutStates:waiting_name"
        assert await ctx2.get_data() == {"customer_name": "Иван", "country": "DE"}
        await ctx2.clear()
        assert await ctx2.get_state() is None
        assert await ctx2.get_data() == {}

    run(scenario())
    assert not (tmp_path / "fsm_state.tmp").exists()   # atomic write, no residue


def test_main_uses_json_file_storage():
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "JsonFileStorage()" in src
    assert "storage.close()" in src


# ── related products ──────────────────────────────────────────────────────────

def test_related_service_and_integrity():
    from services.related_service import related_service as rs
    from services import products_service
    rs.load()
    rel = rs.get_related("Semaglutide")
    assert isinstance(rel, list) and len(rel) >= 1
    # every referenced name must be a real drug in the catalog
    prods = run(products_service.get_all_products())
    names = {p.name for p in prods}
    for src in ("Semaglutide", "TB 500", "NAD+"):
        for r in rs.get_related(src):
            assert r in names, f"related '{r}' of '{src}' is not a real drug"
    assert rs.get_related("NoSuchDrug") == []


# ── Mini App api layer ────────────────────────────────────────────────────────

def test_api_categories_and_product():
    from api import get_categories, get_product, get_drug, get_related
    cats = run(get_categories())
    assert len(cats) == 7
    assert {"name", "emoji", "drug_count", "sku_count"} <= set(cats[0])

    prod = run(get_product(1))
    assert prod["name"] == "Semaglutide"
    assert prod["effects"] and prod["related"]
    assert run(get_product(999999)) is None


def test_api_drug_aggregates_variants():
    from api import get_drug
    drug = run(get_drug("Tirzepatide"))
    assert drug["name"] == "Tirzepatide"
    assert len(drug["variants"]) == 8           # 8 dosage SKUs
    assert drug["short_description"] and drug["effects"]
    # variants sorted by price ascending
    prices = [v["price"] for v in drug["variants"]]
    assert prices == sorted(prices)


# ── admin smoke ───────────────────────────────────────────────────────────────

def test_admin_menu_requires_admin():
    import handlers.admin as adm
    # non-admin gets nothing
    m = MagicMock(); m.from_user.id = 999999; m.answer = AsyncMock()
    state = MagicMock(); state.clear = AsyncMock()
    run(adm.cmd_admin(m, state))
    m.answer.assert_not_called()
