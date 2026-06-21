"""
tests/test_p0_regressions.py — Regression checks for the five P0 fixes.

Run from project root:  python -m pytest tests/ -v

Covers:
  P0-1  order:cancel routing
  P0-2  oversell intentionally NOT enforced (stock unused — project decision)
  P0-3  HTML escaping of user input
  P0-4  atomic JSON writes + non-destructive corrupt-load
  P0-5  PII data files are no longer git-tracked
"""
import json
import os
import subprocess
from pathlib import Path

# Bot config validates env at import time.
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ADMIN_ID", "1")

ROOT = Path(__file__).resolve().parents[1]


# ── P0-1 · order:cancel routing ───────────────────────────────────────────────

def _winner(callback_data: str):
    """Return the name of the first order-router handler whose filters match."""
    from handlers.order import router as order_router

    class _CB:
        data = callback_data

    cb = _CB()
    for handler in order_router.callback_query.handlers:
        matched = True
        for f in handler.filters:
            cbk = f.callback
            res = cbk.resolve(cb) if hasattr(cbk, "resolve") else cbk(cb)
            if not res:
                matched = False
                break
        if matched:
            return handler.callback.__name__
    return None


def test_p0_1_cancel_routes_to_cancel_handler():
    assert _winner("order:cancel") == "cb_cancel_order"


def test_p0_1_start_and_subcommands_still_route():
    assert _winner("order:123") == "cb_start_order"
    assert _winner("order:confirm:5") == "cb_confirm_order"
    assert _winner("order:edit:5") == "cb_edit_order"


def test_p0_1_no_broken_eq_filter_in_source():
    src = (ROOT / "handlers" / "order.py").read_text(encoding="utf-8")
    assert ".eq(" not in src, "broken magic_filter .eq() must not return"


# ── P0-2 · oversell guard ─────────────────────────────────────────────────────
# Removed: stock quantities are intentionally NOT used in this project, so there
# is deliberately no oversell guard. (Project decision.)


def test_p0_2_no_oversell_guard_present():
    """Confirm the oversell logic stays removed (stock is not enforced)."""
    cart_src = (ROOT / "handlers" / "cart.py").read_text(encoding="utf-8")
    helpers_src = (ROOT / "utils" / "helpers.py").read_text(encoding="utf-8")
    assert "stock_allows" not in cart_src
    assert "stock_allows" not in helpers_src


# ── P0-3 · HTML escaping ──────────────────────────────────────────────────────

def test_p0_3_order_form_escapes_user_input():
    from services.models import OrderForm
    form = OrderForm(
        product_id=1,
        product_name="TB-500 <b>",
        user_id=42,
        username="ev<il>",
        customer_name="Иван <script>",
        customer_contact="<a href=x>",
        comment="b<r>eak",
    )
    text = form.admin_notification()
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "&lt;b&gt;" in text       # product name escaped
    assert "ev&lt;il&gt;" in text    # username escaped


def test_p0_3_cart_confirm_escapes_and_checks_delivery():
    src = (ROOT / "handlers" / "cart.py").read_text(encoding="utf-8")
    assert "html.escape" in src
    assert "if not sent" in src, "cart confirm must not report success on failed send"


# ── P0-4 · atomic writes + corrupt-load backup ───────────────────────────────

def test_p0_4_atomic_save_and_corrupt_backup(tmp_path, monkeypatch):
    import services.cart_service as cs

    carts_file = tmp_path / "carts.json"
    monkeypatch.setattr(cs, "CARTS_FILE", carts_file)

    svc = cs.CartService()
    svc._carts = {"7": {"1": 2}}
    svc._save_sync()

    # File written, valid JSON, no temp residue.
    assert carts_file.exists()
    assert json.loads(carts_file.read_text(encoding="utf-8")) == {"7": {"1": 2}}
    assert not (tmp_path / "carts.json.tmp").exists()

    # Corrupt the file; a fresh load must NOT wipe silently — it backs up.
    carts_file.write_text("{ this is not json", encoding="utf-8")
    svc2 = cs.CartService()
    svc2._load_sync()
    assert svc2._carts == {}
    backups = list(tmp_path.glob("carts.json.corrupt.*"))
    assert backups, "corrupt carts.json must be backed up, not discarded"


def test_p0_4_users_service_atomic_and_backup(tmp_path, monkeypatch):
    import services.users_service as us

    users_file = tmp_path / "users.json"
    monkeypatch.setattr(us, "USERS_FILE", users_file)

    svc = us.UsersService()
    svc._users = {1: {"username": "a"}}
    svc._save_sync()
    assert json.loads(users_file.read_text(encoding="utf-8")) == {"1": {"username": "a"}}
    assert not (tmp_path / "users.json.tmp").exists()

    users_file.write_text("broken", encoding="utf-8")
    svc2 = us.UsersService()
    svc2._load_sync()
    assert svc2._users == {}
    assert list(tmp_path.glob("users.json.corrupt.*"))


# ── P0-5 · PII files untracked ───────────────────────────────────────────────

def test_p0_5_pii_files_not_tracked():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert "users.json" not in tracked, "users.json must not be git-tracked"
    assert "carts.json" not in tracked, "carts.json must not be git-tracked"
