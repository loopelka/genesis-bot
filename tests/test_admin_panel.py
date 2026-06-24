"""
tests/test_admin_panel.py — coverage for the admin store-management layer.

Covers products JSON CRUD + clone + bulk price, category rename cascade,
promo-code validate/redeem (usage limit + expiry), and users count_since.
Each test points the services at a fresh temp DATA_DIR via monkeypatching the
module-level *_FILE paths, so nothing touches the real store.
"""
import asyncio
import os
import time

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ADMIN_ID", "1")


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fresh_products(tmp_path, monkeypatch):
    import importlib
    mod = importlib.import_module("services.products_service")
    monkeypatch.setattr(mod, "PRODUCTS_FILE", tmp_path / "products.json")
    monkeypatch.setattr(mod, "XLSX_PATH", tmp_path / "nonexistent.xlsx")  # no migration
    svc = mod.ProductsService()
    return mod, svc


def test_product_crud_and_hidden(tmp_path, monkeypatch):
    _, svc = _fresh_products(tmp_path, monkeypatch)
    p = run(svc.add_product(category="Cat", name="Alpha", dosage="5mg", price=1000))
    assert p.product_id == 1
    # visible to customer
    assert len(run(svc.get_all_products())) == 1
    # hide → excluded from customer view, still in admin view
    run(svc.set_hidden(p.product_id, True))
    assert run(svc.get_all_products()) == []
    assert len(run(svc.get_all_admin())) == 1
    # update
    run(svc.update_product(p.product_id, price=1500, name="Beta"))
    assert run(svc.get_admin_by_id(p.product_id)).price == 1500
    # delete
    assert run(svc.delete_product(p.product_id)) is True
    assert run(svc.get_all_admin()) == []


def test_product_clone_and_persistence(tmp_path, monkeypatch):
    mod, svc = _fresh_products(tmp_path, monkeypatch)
    src = run(svc.add_product(category="Cat", name="Alpha", dosage="5mg", price=1000))
    clone = run(svc.clone_product(src.product_id))
    assert clone.product_id != src.product_id
    assert "копия" in clone.name
    # a brand-new service instance reads the same JSON back
    svc2 = mod.ProductsService()
    assert len(run(svc2.get_all_admin())) == 2


def test_bulk_price_change(tmp_path, monkeypatch):
    _, svc = _fresh_products(tmp_path, monkeypatch)
    run(svc.add_product(category="A", name="x", dosage="1", price=1000))
    run(svc.add_product(category="A", name="y", dosage="1", price=2000))
    run(svc.add_product(category="B", name="z", dosage="1", price=500))
    affected = run(svc.bulk_price_change("A", 10))
    assert affected == 2
    prices = {p.name: p.price for p in run(svc.get_all_admin())}
    assert prices["x"] == 1100 and prices["y"] == 2200 and prices["z"] == 500
    # all-products decrease
    run(svc.bulk_price_change(None, -50))
    prices = {p.name: p.price for p in run(svc.get_all_admin())}
    assert prices["z"] == 250


def test_category_rename_cascades_products(tmp_path, monkeypatch):
    _, svc = _fresh_products(tmp_path, monkeypatch)
    run(svc.add_product(category="Old", name="x", dosage="1", price=100))
    run(svc.add_product(category="Old", name="y", dosage="1", price=100))
    moved = run(svc.rename_category("Old", "New"))
    assert moved == 2
    cats = run(svc.get_available_categories())
    assert cats == ["New"]


def test_promo_validate_redeem_limit_and_expiry(tmp_path, monkeypatch):
    import importlib
    mod = importlib.import_module("services.promocodes_service")
    monkeypatch.setattr(mod, "PROMOCODES_FILE", tmp_path / "promocodes.json")
    svc = mod.PromoCodesService()

    assert run(svc.create("SALE10", "percent", 10, usage_limit=1)) is True
    rec, reason = run(svc.validate("sale10"))           # case-insensitive
    assert rec is not None and reason == ""
    assert svc.discount_for(rec, 2000) == 200
    assert run(svc.redeem("SALE10")) is True
    rec2, reason2 = run(svc.validate("SALE10"))          # limit reached
    assert rec2 is None and "Лимит" in reason2

    # fixed discount capped at total
    run(svc.create("FLAT", "fixed", 5000))
    rec3, _ = run(svc.validate("FLAT"))
    assert svc.discount_for(rec3, 1000) == 1000

    # expired code
    run(svc.create("OLD", "percent", 50, expires_at=time.time() - 10))
    rec4, reason4 = run(svc.validate("OLD"))
    assert rec4 is None and "истёк" in reason4

    # disabled code
    run(svc.create("OFF", "percent", 10))
    run(svc.disable("OFF"))
    rec5, reason5 = run(svc.validate("OFF"))
    assert rec5 is None and "отключён" in reason5.lower()


def test_users_count_since(tmp_path, monkeypatch):
    import importlib
    mod = importlib.import_module("services.users_service")
    monkeypatch.setattr(mod, "USERS_FILE", tmp_path / "users.json")
    svc = mod.UsersService()
    run(svc.register(1, "a"))
    run(svc.register(2, "b"))
    assert run(svc.count()) == 2
    # both just registered → counted since an hour ago
    assert run(svc.count_since(time.time() - 3600)) == 2
    # none in the future window
    assert run(svc.count_since(time.time() + 3600)) == 0
    user = run(svc.get_user(1))
    assert user["user_id"] == 1 and "registered_ts" in user
