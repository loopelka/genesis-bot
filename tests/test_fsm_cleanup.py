"""
tests/test_fsm_cleanup.py — FSM retention cleanup (P0-3).

Covers:
  • cleanup() prunes sessions idle longer than the TTL
  • a recently-active session is NOT evicted (idle timer refreshed on write)
  • ttl <= 0 disables cleanup (no-op)
  • legacy entries without a timestamp get a fresh lease on load (not nuked)
  • data payload never leaks the internal 'ts' field
"""
import asyncio
import json
import os
import time

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ADMIN_ID", "1")

from aiogram.fsm.storage.base import StorageKey
from services.fsm_storage import JsonFileStorage


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _key(uid):
    return StorageKey(bot_id=1, chat_id=uid, user_id=uid)


def test_cleanup_prunes_stale_keeps_fresh(tmp_path):
    s = JsonFileStorage(tmp_path / "fsm.json")
    stale, fresh = _key(1), _key(2)

    run(s.set_state(stale, None))
    run(s.set_data(stale, {"customer_name": "Old"}))
    run(s.set_data(fresh, {"customer_name": "New"}))

    # Backdate the stale entry well beyond the TTL.
    s._data["1:1:1:default"]["ts"] = time.time() - 10_000

    removed = run(s.cleanup(ttl_seconds=3600))
    assert removed == 1
    assert run(s.get_data(stale)) == {}            # gone
    assert run(s.get_data(fresh)) == {"customer_name": "New"}  # kept


def test_cleanup_disabled_when_ttl_non_positive(tmp_path):
    s = JsonFileStorage(tmp_path / "fsm.json")
    run(s.set_data(_key(1), {"x": 1}))
    s._data["1:1:1:default"]["ts"] = time.time() - 10_000
    assert run(s.cleanup(0)) == 0
    assert run(s.cleanup(-5)) == 0
    assert run(s.get_data(_key(1))) == {"x": 1}    # untouched


def test_legacy_entry_without_ts_survives_load(tmp_path):
    path = tmp_path / "fsm.json"
    # Simulate a file written before TTL support: no "ts" key.
    path.write_text(json.dumps({
        "1:1:1:default": {"state": "CartCheckoutStates:waiting_name",
                          "data": {"customer_name": "Иван"}}
    }), encoding="utf-8")

    s = JsonFileStorage(path)
    # Fresh lease on load → an immediate cleanup must not evict it.
    assert run(s.cleanup(3600)) == 0
    assert run(s.get_state(_key(1))) == "CartCheckoutStates:waiting_name"
    assert run(s.get_data(_key(1))) == {"customer_name": "Иван"}


def test_ts_not_leaked_into_data(tmp_path):
    s = JsonFileStorage(tmp_path / "fsm.json")
    k = _key(7)
    run(s.set_data(k, {"a": 1}))
    assert run(s.get_data(k)) == {"a": 1}          # no 'ts' in returned data
    # but the internal record does carry a timestamp
    assert "ts" in s._data["1:7:7:default"]
