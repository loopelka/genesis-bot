# Genesis Peptide Store — Final Project State

**Date:** 2026-06-22 · **Branch:** `main` · **Status:** production-ready (single instance)

## Snapshot

- **Stack:** Python 3.12, aiogram 3.x, openpyxl, Flask (keep-alive), JSON storage.
- **Entry point:** `python main.py` (long polling, `JsonFileStorage` FSM).
- **Catalog:** 104 SKU · 47 unique drugs · 7 categories.
- **Single source of truth:** `products.xlsx` + `products_descriptions.json` + `related_products.json`.
- **Tests:** 23 passed / 0 failed / 0 skipped. Validation: 11/11 categories PASS.

## Lineage consolidation (resolved)

Three divergent states unified into one codebase on `main`:
- Adopted **JsonFileStorage** (persistent FSM) from the archive lineage.
- Kept **products_descriptions.json** (JSON, by name) over the archive's column-H approach.
- Removed the unrelated Node/TS workspace and stale artifacts.
- Removed dead code (kb_categories, kb_product_list, user_mention, truncate, item_count).

## Feature status

| Area | Status |
|---|---|
| Catalog (goal → drug → dosage → card) | ✅ working |
| Product card: name/category/dosage/price/stock | ✅ |
| Product card: short_description + effects | ✅ (by drug name) |
| Related products ("С этим товаром смотрят") | ✅ |
| Cart (add/inc/dec/clear/total) | ✅ |
| Checkout FSM (name→contact→country→comment→confirm) | ✅ |
| Order → admin notification (HTML-escaped) | ✅ |
| FSM persistence across restart | ✅ JsonFileStorage |
| Admin panel (stats/users/broadcast) | ✅ gated by ADMIN_ID |
| Quick order + working cancel (P0-1) | ✅ |
| Atomic JSON writes + corrupt-load backup (P0-4) | ✅ |
| PII files untracked (P0-5) | ✅ |
| Mini App backend API contract | ✅ design-only (`api/`, `docs/MINIAPP_API.md`) |
| Stock enforcement | ⛔ intentionally not used |
| Product photos | ⛔ none (text cards; infra ready) |
| Frontend / Mini App UI | ⛔ out of scope |

## Commit history (recent)

```
3c1903e chore: remove dead code (unused keyboards/helpers/method)
c7b4aea Merge consolidation/unified-state into main
c72d406 feat: consolidate to single source of truth + Mini App API prep
4734960 chore: remove Node/TS workspace and stale artifacts
5784f19 Merge release/p0-critical-fixes into main
```

## Validation results (final)

| Category | Result |
|---|---|
| import / startup / configuration | PASS |
| products.xlsx (104 SKU, 7 cats, 47 drugs, no dup ids) | PASS |
| products_descriptions.json (47 recs, ids 1..104, fields, 47↔104) | PASS |
| related_products.json (47 keys, no broken refs) | PASS |
| FSM persistence | PASS |
| admin / catalog / cart / checkout flows | PASS |
| pytest | 23 passed |
| manual E2E incl. FSM recovery | PASS |

## Open items (see RELEASE_READINESS_REPORT.md for detail)

- Single-instance only; ephemeral hosts need a mounted volume for JSON data.
- `fsm_state.json` has no TTL; `related_products.json` needs manual curation.
- PII in old git history needs a coordinated purge.
- Deploy is manual (no CI/CD); after merge, redeploy required.

## Next steps (deferred, not in this release)

- Populate `products.xlsx` column G with photo file_ids (`get_file_id.py`).
- Wrap `api/` in an HTTP server (aiohttp/FastAPI) + build the Mini App frontend.
- Optional: Redis storage for horizontal scaling; FSM TTL; inline search.
