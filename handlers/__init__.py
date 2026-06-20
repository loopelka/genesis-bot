"""
handlers/__init__.py — Router aggregator.
Import this and include all_routers in the dispatcher.
"""
from aiogram import Router
from .start import router as start_router
from .catalog import router as catalog_router
from .order import router as order_router
from .info import router as info_router
from .faq import router as faq_router
from .manager import router as manager_router

# Order matters: more specific handlers first
all_routers = [
    start_router,
    catalog_router,
    order_router,
    info_router,
    faq_router,
    manager_router,
]

__all__ = ["all_routers"]
