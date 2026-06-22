"""
tests/test_descriptions_integration.py — Catalog/descriptions integration.
Uses the real products.xlsx and products_descriptions.json; only Telegram I/O
is mocked. Cart/FSM/checkout logic is unchanged — these confirm nothing broke.
"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ADMIN_ID", "1")


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── descriptions service (lookup by name primary, id fallback) ────────────────

def test_lookup_by_name_and_id():
    from services.descriptions_service import descriptions_service as ds
    ds.load()
    assert ds.get_by_name("Semaglutide")["name"] == "Semaglutide"
    assert ds.get_by_id(5)["name"] == "Semaglutide"        # other dosage SKU
    assert ds.get_by_id(104)["name"] == "Botulinum toxin"
    assert ds.get(name="Semaglutide")["name"] == "Semaglutide"
    assert ds.get(product_id=99999) is None


def test_render_block_short_description_and_effects():
    from services.descriptions_service import descriptions_service as ds
    block = ds.render_block(name="Semaglutide")
    assert block is not None
    assert "📝" in block                          # short_description
    assert "Основные эффекты" in block             # effects (Э8)
    assert ds.render_block(product_id=99999) is None


def test_name_mapping_covers_all_47_drugs():
    from services.descriptions_service import descriptions_service as ds
    from services import products_service
    ds.load()
    prods = run(products_service.get_all_products())
    res = ds.validate_names({p.name for p in prods})
    assert res["missing_description"] == []
    assert res["orphan_description"] == []


# ── product card ──────────────────────────────────────────────────────────────

def test_product_card_includes_description_and_related(monkeypatch):
    import handlers.catalog as cat
    from services import products_service

    captured = {}
    async def fake_edit(message, text, reply_markup=None, **k):
        captured["text"] = text; return True
    monkeypatch.setattr(cat, "safe_edit_message", fake_edit)

    product = run(products_service.get_product_by_id(1))   # Semaglutide
    cb = MagicMock(); cb.message = MagicMock(); cb.message.chat.id = 1
    run(cat._send_product_card(cb, product, bot=MagicMock()))

    t = captured["text"]
    assert "Semaglutide" in t
    assert "Основные эффекты" in t
    assert "С этим товаром смотрят" in t
    assert "Для заказа нажмите кнопку ниже." in t
    # description block sits BEFORE the call-to-action
    assert t.index("Основные эффекты") < t.index("Для заказа нажмите кнопку ниже.")


def test_product_card_fallback_without_description(monkeypatch):
    import handlers.catalog as cat
    from services.models import Product

    captured = {}
    async def fake_edit(message, text, reply_markup=None, **k):
        captured["text"] = text; return True
    monkeypatch.setattr(cat, "safe_edit_message", fake_edit)

    ghost = Product(product_id=99999, category="Контроль веса", name="GhostPeptide",
                    dosage="10 мг", price=1000, stock=5, photo_id="")
    cb = MagicMock(); cb.message = MagicMock(); cb.message.chat.id = 1
    run(cat._send_product_card(cb, ghost, bot=MagicMock()))

    # No description / no related → card equals plain card_text(), no error
    assert captured["text"] == ghost.card_text()
    assert "Основные эффекты" not in captured["text"]


# ── catalog navigation ────────────────────────────────────────────────────────

def test_catalog_screens_render(monkeypatch):
    import handlers.catalog as cat
    captured = {}
    async def fake_edit(message, text, reply_markup=None, **k):
        captured["text"] = text; return True
    monkeypatch.setattr(cat, "safe_edit_message", fake_edit)

    cb = MagicMock(); cb.message = MagicMock(); cb.answer = AsyncMock()
    run(cat.cb_show_catalog(cb))
    assert "Каталог" in captured["text"]

    run(cat._show_drug_list(cb, "Контроль веса", 0))
    assert "Контроль веса" in captured["text"]


# ── cart checkout → admin notification (unchanged logic) ──────────────────────

def _run_confirm(send_ok, monkeypatch):
    import handlers.cart as cart

    class FakeCartSvc:
        def __init__(s): s.cleared = False; s.items = {1: 2}
        async def get_items(s, uid): return dict(s.items)
        async def clear(s, uid): s.cleared = True; s.items = {}
    class FakeState:
        def __init__(s):
            s.cleared = False
            s._d = {"customer_name": "Иван", "customer_contact": "@user",
                    "customer_country": "DE", "customer_comment": "DHL"}
        async def get_data(s): return dict(s._d)
        async def update_data(s, **kw): s._d.update(kw); return dict(s._d)
        async def clear(s): s.cleared = True
    class FakeOrders:
        def __init__(s): s.created = []; s.notified = []; s.failed = []
        async def create(s, **kw): s.created.append(kw); return "000001"
        async def mark_notified(s, oid): s.notified.append(oid)
        async def mark_notify_failed(s, oid): s.failed.append(oid)

    fcs = FakeCartSvc(); fst = FakeState(); fo = FakeOrders()
    # monkeypatch.setattr auto-restores, so these stubs never leak to other tests.
    monkeypatch.setattr(cart, "cart_service", fcs)
    monkeypatch.setattr(cart, "orders_service", fo)
    prod = MagicMock(); prod.name = "Semaglutide"; prod.dosage = "5 мг"
    prod.price = 2100; prod.stock = 10
    monkeypatch.setattr(cart.products_service, "get_product_by_id",
                        AsyncMock(return_value=prod))
    sent = MagicMock() if send_ok else None
    send_mock = AsyncMock(return_value=sent)
    monkeypatch.setattr(cart, "safe_send_message", send_mock)
    captured = {}
    async def fake_edit(message, text, reply_markup=None, **k):
        captured["text"] = text; return True
    monkeypatch.setattr(cart, "safe_edit_message", fake_edit)

    cb = MagicMock(); cb.from_user.id = 200; cb.from_user.username = "user"
    cb.message = MagicMock(); cb.answer = AsyncMock()
    run(cart.cb_cart_confirm(cb, fst, bot=MagicMock()))
    admin_text = send_mock.call_args.kwargs.get("text", "") if send_ok else ""
    return fcs.cleared, fst.cleared, captured["text"], admin_text, fo


def test_checkout_success_sends_admin_notification(monkeypatch):
    cart_cleared, state_cleared, user_msg, admin_text, fo = _run_confirm(
        send_ok=True, monkeypatch=monkeypatch)
    assert cart_cleared and state_cleared
    assert "Заказ оформлен" in user_msg
    assert "Новый заказ" in admin_text and "Semaglutide" in admin_text
    # Order persisted before the DM, then marked notified.
    assert len(fo.created) == 1 and fo.notified == ["000001"]


def test_checkout_failure_preserves_cart_and_state(monkeypatch):
    cart_cleared, state_cleared, user_msg, _, fo = _run_confirm(
        send_ok=False, monkeypatch=monkeypatch)
    assert not cart_cleared and not state_cleared
    assert "Не удалось отправить заказ" in user_msg
    # Order still persisted, marked notify_failed (not lost).
    assert len(fo.created) == 1 and fo.failed == ["000001"]
