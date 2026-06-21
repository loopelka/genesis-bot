"""
tests/test_descriptions_integration.py — Smoke tests for products_descriptions.json
integration. Uses the real products.xlsx and products_descriptions.json; only
Telegram I/O is mocked.

Covers: descriptions loading + lookup by product_id, product card (with and
without description), catalog rendering, and cart checkout → admin notification.
Cart/FSM/checkout LOGIC is unchanged — these tests only confirm nothing broke.
"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ADMIN_ID", "1")


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── descriptions service ──────────────────────────────────────────────────────

def test_load_and_lookup_by_product_id():
    from services.descriptions_service import descriptions_service as ds
    ds.load()
    rec = ds.get(1)                      # Semaglutide id 1
    assert rec and rec["name"] == "Semaglutide"
    assert ds.get(5)["name"] == "Semaglutide"   # same drug, other dosage id
    assert ds.get(104)["name"] == "Botulinum toxin"
    assert ds.get(99999) is None         # unknown id → None (fallback path)


def test_render_block_contains_required_fields():
    from services.descriptions_service import descriptions_service as ds
    block = ds.render_block(1)
    assert block is not None
    assert "📝" in block                          # short_description
    assert "Кратко" in block                       # key_points
    assert "Направления исследований" in block     # research_areas
    assert ds.render_block(99999) is None          # unknown → None


# ── product card ──────────────────────────────────────────────────────────────

def test_product_card_includes_description():
    import handlers.catalog as cat
    from services import products_service

    captured = {}
    async def fake_edit(message, text, reply_markup=None, **k):
        captured["text"] = text; return True
    cat.safe_edit_message = fake_edit

    product = run(products_service.get_product_by_id(1))
    cb = MagicMock(); cb.message = MagicMock(); cb.message.chat.id = 1
    run(cat._send_product_card(cb, product, bot=MagicMock()))

    assert "Semaglutide" in captured["text"]
    assert "Направления исследований" in captured["text"]
    assert "Для заказа нажмите кнопку ниже." in captured["text"]
    # description block is inserted BEFORE the call-to-action
    assert captured["text"].index("Направления исследований") < \
           captured["text"].index("Для заказа нажмите кнопку ниже.")


def test_product_card_fallback_without_description():
    import handlers.catalog as cat
    from services.models import Product

    captured = {}
    async def fake_edit(message, text, reply_markup=None, **k):
        captured["text"] = text; return True
    cat.safe_edit_message = fake_edit

    ghost = Product(product_id=99999, category="Контроль веса", name="GhostPeptide",
                    dosage="10 мг", price=1000, stock=5, photo_id="")
    cb = MagicMock(); cb.message = MagicMock(); cb.message.chat.id = 1
    run(cat._send_product_card(cb, ghost, bot=MagicMock()))

    # No description for this id → card equals plain card_text(), no error
    assert captured["text"] == ghost.card_text()
    assert "Направления исследований" not in captured["text"]


# ── catalog navigation ────────────────────────────────────────────────────────

def test_catalog_screens_render():
    import handlers.catalog as cat
    captured = {}
    async def fake_edit(message, text, reply_markup=None, **k):
        captured["text"] = text; return True
    cat.safe_edit_message = fake_edit

    cb = MagicMock(); cb.message = MagicMock(); cb.answer = AsyncMock()
    run(cat.cb_show_catalog(cb))
    assert "Каталог" in captured["text"]

    run(cat._show_drug_list(cb, "Контроль веса", 0))
    assert "Контроль веса" in captured["text"]


# ── cart checkout → admin notification (unchanged logic) ──────────────────────

def _run_confirm(send_ok):
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
        async def clear(s): s.cleared = True

    fcs = FakeCartSvc(); fst = FakeState()
    cart.cart_service = fcs
    prod = MagicMock(); prod.name = "Semaglutide"; prod.dosage = "5 мг"
    prod.price = 2100; prod.stock = 10
    cart.products_service.get_product_by_id = AsyncMock(return_value=prod)
    sent = MagicMock() if send_ok else None
    cart.safe_send_message = AsyncMock(return_value=sent)
    captured = {}
    async def fake_edit(message, text, reply_markup=None, **k):
        captured["text"] = text; return True
    cart.safe_edit_message = fake_edit

    cb = MagicMock(); cb.from_user.id = 200; cb.message = MagicMock(); cb.answer = AsyncMock()
    run(cart.cb_cart_confirm(cb, fst, bot=MagicMock()))
    admin_text = cart.safe_send_message.call_args.kwargs.get("text", "") if send_ok else ""
    return fcs.cleared, fst.cleared, captured["text"], admin_text


def test_checkout_success_sends_admin_notification():
    cart_cleared, state_cleared, user_msg, admin_text = _run_confirm(send_ok=True)
    assert cart_cleared and state_cleared
    assert "Заказ оформлен" in user_msg
    assert "Новый заказ" in admin_text and "Semaglutide" in admin_text


def test_checkout_failure_preserves_cart_and_state():
    cart_cleared, state_cleared, user_msg, _ = _run_confirm(send_ok=False)
    assert not cart_cleared and not state_cleared
    assert "Не удалось отправить заказ" in user_msg
