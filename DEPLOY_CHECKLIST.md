# Genesis Bot — Deploy Checklist

Branch: `main` · Single-instance · Manual deploy (no CI/CD)

## Pre-deploy

- [ ] On `main`, working tree clean (`git status`), latest commit pulled on host.
- [ ] `pip install -r requirements.txt` succeeds (Python 3.12).
- [ ] `python -m pytest tests/ -q` → **23 passed**.
- [ ] `python -m py_compile main.py handlers/*.py services/*.py utils/*.py keyboards/*.py config/*.py api/*.py` → no errors.
- [ ] Data files present in the deploy working directory:
      `products.xlsx`, `products_descriptions.json`, `related_products.json`.
- [ ] Secrets/env set: `BOT_TOKEN`, `ADMIN_ID` (required); `PRODUCTS_FILE`, `CACHE_TTL` (optional).

## Deploy

- [ ] **Docker:** `docker build -t genesis-bot:latest .` then run with `--restart unless-stopped`, env vars, and a mounted volume for `carts.json`/`users.json`/`fsm_state.json` if persistence across redeploys is required.
- [ ] **Replit:** Redeploy with run command `python main.py`; prefer **Reserved VM** (long-polling bot must not sleep).
- [ ] Only ONE instance running for this `BOT_TOKEN` (polling → a second instance causes `409 Conflict`).

## Post-deploy verification

- [ ] Startup logs show: `Loaded descriptions: 47 drugs → 104 product_ids`,
      `Descriptions ↔ catalog: all 47 drugs matched`, `Bot started: @...`.
- [ ] No `MISSING`/`ORPHAN` description warnings in logs.
- [ ] Telegram smoke: `/start` → Каталог → раздел → препарат → дозировка → карточка shows
      **Краткое описание + Основные эффекты + С этим товаром смотрят**.
- [ ] Add to cart → edit qty → checkout → **admin receives order** → cart cleared.
- [ ] Quick-order **«Отменить заказ»** cancels cleanly (no error).
- [ ] `getUpdates` returns `409 Conflict` (confirms exactly one live instance).
- [ ] Health endpoint reachable (if public): `GET /` → "Bot is running ✅", `GET /health` → `{"status":"ok"}`.

## Rollback

- [ ] Redeploy previous known-good commit (`git checkout <sha>` on host or redeploy prior image).
- [ ] Restore `carts.json`/`users.json` from volume/backup if needed (atomic writes prevent corruption; `*.corrupt.*` backups created on bad load).

## Data-edit runbook (no redeploy needed for content)

- [ ] Edit `products.xlsx` (price/stock/dosage) — picked up within `CACHE_TTL` (default 300s).
- [ ] Edit `products_descriptions.json` / `related_products.json` — requires **process restart** (loaded once at startup).
- [ ] Keep JSON `name` keys exactly equal to `products.xlsx` column C (drug name).
