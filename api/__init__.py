"""
api/ — Mini App backend layer (data + serialization only, no HTTP server, no
frontend). These pure functions/DTOs are the contract a future Telegram Mini
App (aiohttp/FastAPI) will expose. See docs/MINIAPP_API.md.
"""
from .catalog_api import (
    get_categories,
    get_catalog,
    get_product,
    get_drug,
    get_related,
)

__all__ = [
    "get_categories",
    "get_catalog",
    "get_product",
    "get_drug",
    "get_related",
]
