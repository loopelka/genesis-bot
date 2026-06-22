"""
tests/test_orders_service.py — Order persistence (P0-1) coverage.

Covers:
  • create() persists an order with status 'new' and a snapshot of items
  • monotonic, zero-padded ids; no collisions across calls
  • mark_notified / mark_notify_failed transitions
  • atomic write (no .tmp residue) + non-destructive corrupt-load backup
  • get_all() ordering (newest first) and count()
"""
import asyncio
import importlib
import json
import os
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ADMIN_ID", "1")


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_service(tmp_path, monkeypatch):
    # import_module returns the real submodule (services/__init__ re-exports the
    # singleton under the same name, which would shadow attribute access).
    os_mod = importlib.import_module("services.orders_service")
    monkeypatch.setattr(os_mod, "ORDERS_FILE", tmp_path / "orders.json")
    return os_mod, os_mod.OrdersService()


def test_create_persists_with_snapshot(tmp_path, monkeypatch):
    os_mod, svc = _make_service(tmp_path, monkeypatch)

    oid = run(svc.create(
        user_id=42, username="ivan",
        customer_name="Иван", customer_contact="@ivan",
        items=[{"product_id": 1, "name": "Semaglutide", "dosage": "5 mg", "price": 1000, "qty": 2}],
        total=2000, comment="fast", customer_country="DE", source="cart",
    ))
    assert oid == "000001"

    order = run(svc.get(oid))
    assert order["status"] == os_mod.STATUS_NEW
    assert order["source"] == "cart"
    assert order["total"] == 2000
    assert order["items"][0]["name"] == "Semaglutide"
    assert order["items"][0]["qty"] == 2
    assert order["customer_country"] == "DE"

    # Persisted to disk, valid JSON, no temp residue.
    orders_file = tmp_path / "orders.json"
    assert orders_file.exists()
    assert oid in json.loads(orders_file.read_text(encoding="utf-8"))
    assert not (tmp_path / "orders.json.tmp").exists()


def test_ids_are_monotonic(tmp_path, monkeypatch):
    _, svc = _make_service(tmp_path, monkeypatch)
    ids = [
        run(svc.create(user_id=1, username=None, customer_name="A",
                       customer_contact="x", items=[{"product_id": 1}], total=1))
        for _ in range(3)
    ]
    assert ids == ["000001", "000002", "000003"]
    assert run(svc.count()) == 3


def test_status_transitions(tmp_path, monkeypatch):
    os_mod, svc = _make_service(tmp_path, monkeypatch)
    oid = run(svc.create(user_id=1, username=None, customer_name="A",
                         customer_contact="x", items=[{"product_id": 1}], total=1))
    run(svc.mark_notified(oid))
    assert run(svc.get(oid))["status"] == os_mod.STATUS_NOTIFIED
    run(svc.mark_notify_failed(oid))
    assert run(svc.get(oid))["status"] == os_mod.STATUS_NOTIFY_FAILED
    # unknown id is a safe no-op
    run(svc.set_status("999999", os_mod.STATUS_NOTIFIED))


def test_get_all_newest_first(tmp_path, monkeypatch):
    _, svc = _make_service(tmp_path, monkeypatch)
    run(svc.create(user_id=1, username=None, customer_name="A",
                   customer_contact="x", items=[{"product_id": 1}], total=1))
    run(svc.create(user_id=2, username=None, customer_name="B",
                   customer_contact="y", items=[{"product_id": 2}], total=2))
    all_orders = run(svc.get_all())
    assert [o["id"] for o in all_orders] == ["000002", "000001"]


def test_corrupt_load_is_backed_up(tmp_path, monkeypatch):
    _, svc = _make_service(tmp_path, monkeypatch)
    orders_file = tmp_path / "orders.json"
    orders_file.write_text("{ not valid json", encoding="utf-8")

    svc._load_sync()
    assert svc._orders == {}
    backups = list(tmp_path.glob("orders.json.corrupt.*"))
    assert backups, "corrupt orders.json must be backed up, not discarded"
