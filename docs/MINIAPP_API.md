# Genesis Bot — Mini App API Contract (backend prep)

Backend-only preparation for a future Telegram Mini App. **No frontend is built.**
The data layer is implemented as pure async functions in `api/catalog_api.py`
over the single source of truth:

- `products.xlsx` — SKU, category, dosage, price, stock
- `products_descriptions.json` — one description per drug (by name)
- `related_products.json` — related drugs (by name)

A future HTTP server (aiohttp / FastAPI) only needs to wrap these functions —
no business logic changes required.

## Data model (`api/schema.py`)

- **ProductDTO** (one SKU): `id, name, category, dosage, price, price_formatted, in_stock, stock_label`
- **DrugDTO** (one drug): `name, category, short_description, description, key_points[], effects[], research_areas[], related[], variants[ProductDTO]`
- **CategoryDTO**: `name, emoji, drug_count, sku_count`

## Endpoints

| Method & path | Function | Returns |
|---|---|---|
| `GET /api/categories` | `get_categories()` | `[CategoryDTO]` |
| `GET /api/catalog` | `get_catalog()` | `[{category, emoji, drugs:[DrugDTO]}]` |
| `GET /api/drug/{name}` | `get_drug(name)` | `DrugDTO` or `404` |
| `GET /api/product/{id}` | `get_product(id)` | SKU + `short_description, effects[], related[]` or `404` |
| `GET /api/related/{name}` | `get_related(name)` | `[string]` |

## Catalog structure

```
Category (7)
└── Drug (47, unique by name)        ← description + effects + related live here
    └── SKU / variant (104 total)    ← id, dosage, price, stock
```

Mapping rule (Э6): description & related are keyed by **drug name** (== `products.xlsx`
column C), so one record covers all dosage variants of that drug.

## Card structure (bot ↔ Mini App parity)

A product card surfaces, in order:
`Название · Категория · Дозировка · Цена · Наличие` → **Краткое описание** →
**Основные эффекты** → **С этим товаром смотрят** → CTA.

The Mini App can additionally render the reserved fields `description`,
`key_points[]`, `research_areas[]` (already present in `products_descriptions.json`,
not shown on the compact Telegram card).

## Example (`get_product(1)`)

```json
{
  "id": 1, "name": "Semaglutide", "category": "Контроль веса",
  "dosage": "5 мг", "price": 2100, "price_formatted": "2 100 ₽",
  "in_stock": true, "stock_label": "✅ В наличии",
  "short_description": "Пептид-аналог гормона сытости GLP-1, ...",
  "effects": ["Изучается чувство насыщения", "..."],
  "related": ["Tirzepatide", "Retatrutide", "Cagrilintide", "Cagri+Sema (5+5 мг)"]
}
```

## Future HTTP wrapper (sketch, not implemented)

```python
# aiohttp example — wire later
from aiohttp import web
from api import get_categories, get_catalog, get_product, get_drug, get_related

async def h_categories(r): return web.json_response(await get_categories())
# ... map remaining endpoints, add auth (Telegram initData validation), CORS.
```

**Not in scope now:** HTTP server, auth/initData validation, CORS, frontend SPA,
WebApp button. Those are deferred until the Mini App is greenlit.
