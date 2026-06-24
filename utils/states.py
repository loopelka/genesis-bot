"""
utils/states.py — FSM (Finite State Machine) states for all multi-step flows.
"""
from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    """States for the single-product quick order flow."""
    waiting_name = State()
    waiting_contact = State()
    waiting_comment = State()
    confirming = State()


class ManagerStates(StatesGroup):
    """States for the free-form manager message flow."""
    waiting_message = State()


class CartCheckoutStates(StatesGroup):
    """States for the multi-item cart checkout flow."""
    waiting_name    = State()
    waiting_contact = State()
    waiting_country = State()
    waiting_comment = State()
    waiting_promo   = State()   # additive, skippable promo-code step
    confirming      = State()


# ── Admin panel FSMs ──────────────────────────────────────────────────────────

class AdminProductStates(StatesGroup):
    add_name        = State()
    add_category    = State()
    add_dosage      = State()
    add_price       = State()
    add_description = State()
    edit_value      = State()
    search_name     = State()
    bulk_percent    = State()


class AdminCategoryStates(StatesGroup):
    create_name = State()
    rename_value = State()


class AdminPromoStates(StatesGroup):
    code  = State()
    value = State()
    expiry = State()
    limit = State()


class AdminSettingsStates(StatesGroup):
    edit_value = State()


class AdminBackupStates(StatesGroup):
    waiting_file = State()


class AdminOrderStates(StatesGroup):
    search_id = State()


class AdminUserStates(StatesGroup):
    search_id = State()
