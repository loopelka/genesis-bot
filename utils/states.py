"""
utils/states.py — FSM (Finite State Machine) states for all multi-step flows.
"""
from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    """States for the product order flow."""
    waiting_name = State()
    waiting_contact = State()
    waiting_comment = State()
    confirming = State()


class ManagerStates(StatesGroup):
    """States for the free-form manager message flow."""
    waiting_message = State()
