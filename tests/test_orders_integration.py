"""
tests/test_orders_integration.py — P0-2 end-to-end through the real handlers.

Drives handlers/order.py and handlers/cart.py with a real JsonFileStorage FSM,
the real orders_service / cart_service singletons (redirected to tmp files), and
the real products_service (reads products.xlsx). Only the Bot transport is a mock.

Proves:
  • the order is persisted BEFORE the admin notification is attempted
  • a failed admin DM keeps the order (status notify_failed) and preserves FSM state
  • retrying after a failure re-sends WITHOUT creating a duplicate order
  • a successful DM marks the order notified and clears state / cart
"""
import asyncio
import importlib
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ADMIN_ID", "1")

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from services.fsm_storage import JsonFileStorage


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fresh_orders(tmp_path, monkeypatch):
    os_mod = importlib.import_module("services.orders_service")
    monkeypatch.setattr(os_mod, "ORDERS_FILE", tmp_path / "orders.json")
    svc = os_mod.orders_service          # the singleton the handlers import
    svc._orders = {}
    svc._loaded = False
    return svc


def _fresh_cart(tmp_path, monkeypatch):
    cs_mod = importlib.import_module("services.cart_service")
    monkeypatch.setattr(cs_mod, "CARTS_FILE", tmp_path / "carts.json")
    svc = cs_mod.cart_service
    svc._carts = {}
    svc._loaded = False
    return svc


def _state(tmp_path, uid=20):
    storage = JsonFileStorage(tmp_path / "fsm.json")
    key = StorageKey(bot_id=1, chat_id=uid, user_id=uid)
    return FSMContext(storage=storage, key=key)


def _callback(uid=20, username="ivan"):
    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.from_user.id = uid
    cb.from_user.username = username
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    return cb


# ── Single-product flow (handlers/order.py) ───────────────────────────────────

def test_single_order_persists_survives_failure_and_retries(tmp_path, monkeypatch):
    orders = _fresh_orders(tmp_path, monkeypatch)
    from handlers import order as order_h

    state = _state(tmp_path)
    run(state.update_data(
        product_id=1, product_name="Semaglutide", user_id=20, username="ivan",
        customer_name="Иван", customer_contact="@ivan", comment="",
    ))

    cb = _callback()
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=Exception("telegram down"))

    # First confirm — admin DM fails.
    run(order_h.cb_confirm_order(cb, state, bot))
    assert run(orders.count()) == 1, "order must be persisted even when DM fails"
    all_orders = run(orders.get_all())
    oid = all_orders[0]["id"]
    assert all_orders[0]["status"] == "notify_failed"
    assert all_orders[0]["source"] == "single"
    assert all_orders[0]["items"][0]["name"] == "Semaglutide"
    # State preserved with the order id so the retry is idempotent.
    assert (run(state.get_data())).get("order_id") == oid

    # Retry — admin DM now succeeds.
    bot.send_message = AsyncMock(return_value=MagicMock())
    run(order_h.cb_confirm_order(cb, state, bot))
    assert run(orders.count()) == 1, "retry must NOT create a duplicate order"
    assert run(orders.get(oid))["status"] == "notified"
    assert run(state.get_data()) == {}, "state cleared after success"


def test_edit_after_failure_produces_fresh_order(tmp_path, monkeypatch):
    orders = _fresh_orders(tmp_path, monkeypatch)
    from handlers import order as order_h

    state = _state(tmp_path, uid=22)
    run(state.update_data(
        product_id=1, product_name="Semaglutide", user_id=22, username="ivan",
        customer_name="Иван", customer_contact="@ivan", comment="",
    ))
    cb = _callback(uid=22)
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=Exception("down"))

    # Confirm fails → order persisted, order_id retained.
    run(order_h.cb_confirm_order(cb, state, bot))
    first_id = run(orders.get_all())[0]["id"]
    assert (run(state.get_data())).get("order_id") == first_id

    # User edits details → order_id must be dropped so a fresh record is created.
    run(order_h.cb_edit_order(cb, state))
    assert (run(state.get_data())).get("order_id") in (None, "")

    # Re-confirm (now succeeds) → a NEW order, old failed one kept for audit.
    bot.send_message = AsyncMock(return_value=MagicMock())
    run(order_h.cb_confirm_order(cb, state, bot))
    assert run(orders.count()) == 2
    assert run(orders.get(first_id))["status"] == "notify_failed"
    newest = run(orders.get_all())[0]
    assert newest["id"] != first_id and newest["status"] == "notified"


def test_single_order_success_path(tmp_path, monkeypatch):
    orders = _fresh_orders(tmp_path, monkeypatch)
    from handlers import order as order_h

    state = _state(tmp_path, uid=21)
    run(state.update_data(
        product_id=1, product_name="Semaglutide", user_id=21, username=None,
        customer_name="A", customer_contact="x", comment="hi",
    ))
    cb = _callback(uid=21, username=None)
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())

    run(order_h.cb_confirm_order(cb, state, bot))
    orders_list = run(orders.get_all())
    assert len(orders_list) == 1
    assert orders_list[0]["status"] == "notified"
    assert orders_list[0]["total"] > 0       # price snapshot captured from xlsx
    assert run(state.get_data()) == {}


# ── Cart flow (handlers/cart.py) ──────────────────────────────────────────────

def test_cart_order_persists_and_clears_on_success(tmp_path, monkeypatch):
    orders = _fresh_orders(tmp_path, monkeypatch)
    cart = _fresh_cart(tmp_path, monkeypatch)
    from handlers import cart as cart_h

    run(cart.add_item(20, 1))
    run(cart.add_item(20, 1))   # qty 2

    state = _state(tmp_path)
    run(state.update_data(
        customer_name="Иван", customer_contact="@ivan",
        customer_country="DE", customer_comment="",
    ))
    cb = _callback()
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())

    run(cart_h.cb_cart_confirm(cb, state, bot))
    orders_list = run(orders.get_all())
    assert len(orders_list) == 1
    o = orders_list[0]
    assert o["source"] == "cart"
    assert o["status"] == "notified"
    assert o["customer_country"] == "DE"
    assert o["items"][0]["qty"] == 2
    assert run(cart.is_empty(20)) is True, "cart cleared on success"
    assert run(state.get_data()) == {}
