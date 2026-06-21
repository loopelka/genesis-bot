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
    confirming      = State()
