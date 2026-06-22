# Genesis Peptide Store Bot — Release Readiness Report

**Date:** 2026-06-22
**Branch:** `main`
**Validation:** 11/11 categories PASS · 23/23 tests PASS · full E2E (incl. FSM recovery) PASS
**Recommendation:** ✅ **GO** (single-instance deploy; see limitations)

---

## Architecture diagram

```
                          Telegram Bot API (long polling)
                                      │
                                   main.py
              keep_alive() Flask :5000   Dispatcher(JsonFileStorage)
                                      │
                 ┌────────────────────┴─────────────────────┐
                 │            Routers (8, ordered)           │
                 │ admin · start · cart · catalog · order ·  │
                 │ info · faq · manager                      │
                 └────────────────────┬─────────────────────┘
                                      │
          ┌───────────────┬───────────┼───────────────┬──────────────┐
          ▼               ▼           ▼               ▼              ▼
   products_service  descriptions_  related_      cart_service   users_service
   (products.xlsx)   service        service       (carts.json)   (users.json)
    openpyxl+TTL    (products_      (related_      atomic write   atomic write
                    descriptions    products
                    .json,by name)  .json)
          │               │           │
          └──────► services/models.Product (card_text) ◄─────────┐
                                      │                           │
                          handlers/catalog._send_product_card     │
                          (name/cat/dosage/price/stock +          │
                           short_description + effects +          │
                           related) → Telegram                    │
                                                                  │
   FSM state ──► services/fsm_storage.JsonFileStorage (fsm_state.json, atomic)
                                                                  │
   api/ (catalog_api + schema)  ── Mini App backend contract (no HTTP yet) ─┘
   Data sources (single source of truth):
     products.xlsx · products_descriptions.json · related_products.json
```

## Final file tree (bot)

```
.env.example  .gitignore  .replit  .replitignore  Dockerfile  requirements.txt
RELEASE_READINESS_REPORT.md  DEPLOY_CHECKLIST.md  FINAL_PROJECT_STATE.md
main.py  keep_alive.py  get_file_id.py
products.xlsx  products_descriptions.json  related_products.json
api/        __init__.py  catalog_api.py  schema.py
config/     __init__.py  faq.py  settings.py
docs/       MINIAPP_API.md
handlers/   __init__.py  admin.py  cart.py  catalog.py  faq.py
            info.py  manager.py  order.py  start.py
keyboards/  __init__.py  builders.py
services/   __init__.py  cart_service.py  descriptions_service.py
            fsm_storage.py  models.py  products_service.py
            related_service.py  users_service.py
utils/      __init__.py  helpers.py  states.py
tests/      test_consolidation.py  test_descriptions_integration.py
            test_p0_regressions.py
attached_assets/  (original requirement specs — historical)
```

## Startup instructions

```bash
pip install -r requirements.txt
cp .env.example .env          # then set BOT_TOKEN and ADMIN_ID
python main.py
```
Expected startup logs:
```
Starting Genesis Peptide Store bot...
Loaded descriptions: 47 drugs → 104 product_ids
Loaded related products for 47 drugs
Loaded 104 products from products.xlsx
Descriptions ↔ catalog: all 47 drugs matched
Bot started: @<username> (id=...) | Admin: <admin_id>
```

## Deployment instructions

**Docker (recommended, any host):**
```bash
docker build -t genesis-bot:latest .
docker run -d --name genesis-bot --restart unless-stopped \
  -e BOT_TOKEN=*** -e ADMIN_ID=*** \
  -v "$PWD/data:/app/data" genesis-bot:latest
docker logs -f genesis-bot
```
**Replit:** Deployments → Redeploy (run command `python main.py`); set `BOT_TOKEN`/`ADMIN_ID` in Secrets. Note: bot is long-polling — prefer a **Reserved VM** over Autoscale so it does not sleep.

Single-instance only (file-based JSON storage + polling). No CI/CD — deploy is manual.

## Environment variables

| Var | Required | Default | Purpose |
|---|---|---|---|
| `BOT_TOKEN` | **yes** | — | Telegram bot token (startup fails if unset) |
| `ADMIN_ID` | **yes** | — | Telegram user id receiving orders (fails if unset/0) |
| `PRODUCTS_FILE` | no | `products.xlsx` | Catalog source path |
| `CACHE_TTL` | no | `300` | Product cache TTL (seconds) |

## Known limitations

- **Single instance only**: JSON file storage (`carts.json`, `users.json`, `fsm_state.json`) + long polling do not support horizontal scaling.
- **Ephemeral hosts**: on autoscale/ephemeral containers the JSON files may not persist across redeploys unless a volume is mounted.
- **No stock enforcement** (project decision): stock shown as availability label only; quantity is not capped.
- **No live Telegram E2E in CI**: validation is handler-level (no real token/network in sandbox).
- **Manual deploy**: no CI/CD; merging to `main` does not auto-deploy.
- **Photos**: all `photo_id` empty — cards render as text (infrastructure ready via `get_file_id.py`).

## Remaining technical debt

- FSM `fsm_state.json` has no TTL — abandoned checkouts (with entered PII) persist until `/start` or completion.
- `related_products.json` is auto-generated (same-category neighbors) — needs manual curation as catalog grows.
- PII present in older git history (`carts.json`/`users.json` pre-untrack) — needs a coordinated history purge.
- Description name-mapping depends on exact `products.xlsx` column C ↔ JSON `name` match (guarded by startup validation, but manual renames must stay in sync).

## Mini App readiness status

**Backend contract: READY (design only).**
- `api/catalog_api.py` — pure async functions: `get_categories, get_catalog, get_product, get_drug, get_related`.
- `api/schema.py` — `ProductDTO, DrugDTO, CategoryDTO` (JSON-serializable).
- `docs/MINIAPP_API.md` — REST contract for a future aiohttp/FastAPI wrapper.
- **Not built (out of scope):** HTTP server, Telegram `initData` auth, CORS, frontend SPA, WebApp button.
