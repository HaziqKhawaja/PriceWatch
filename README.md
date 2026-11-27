# PriceWatch

PriceWatch is an e-commerce price and stock tracker built with FastAPI, SQLAlchemy, Postgres, and Pandas. Users submit product URLs, a scheduler scrapes them periodically, and every scrape is stored as a price snapshot. The API exposes history, Pandas-computed trends, CSV export, and per-user watches that raise notifications (stored in the database and optionally POSTed to a webhook). v1 ships with three mock retailers so everything runs locally without touching real sites.

## Features

- Scheduled scraping (APScheduler, in-process) of three mock retailers with different markup styles.
- Retries with exponential backoff (1s, 2s, 4s), per-retailer rate limiting, and tracked scrape runs.
- Pandas analytics: outlier filtering, daily resampling, 7/30-day moving averages, summary stats.
- Alerts: price-below-target and restock notifications, stored in the DB and optionally delivered to a webhook.
- CSV export of raw or normalized price history.
- JWT authentication with `user` and `admin` roles.
- Alembic migrations; Docker Compose for local dev; pytest with an 85% coverage gate.

## Quickstart

Requires Docker with Compose.

```sh
cp .env.example .env     # set JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD as you like
make up
```

Then open http://localhost:8000/docs (Swagger UI). The API container runs `alembic upgrade head`, seeds the three retailers, seeds an admin user from `ADMIN_EMAIL` / `ADMIN_PASSWORD` (if that user does not already exist), and starts uvicorn on port 8000. Health check: `GET http://localhost:8000/health`.

Other exposed ports: Postgres on 5432, test Postgres on 5433, mock retailers on 8080.

## Walkthrough

All API routes are under `/api/v1`.

```sh
API=http://localhost:8000/api/v1

# 1. Register and log in (login is an OAuth2 password form; username is the email)
curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"s3cretpass"}'

TOKEN=$(curl -s -X POST $API/auth/login \
  -d 'username=me@example.com&password=s3cretpass' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"

# 2. Add a product by URL (also creates a watch for you; response includes product id and watch id)
curl -s -X POST $API/products -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"url":"http://shopalpha.mock:8080/items/1001"}'

# 3. Set a target price and webhook on your watch (use the watch id from step 2)
curl -s -X PATCH $API/watches/1 -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"target_price":"119.99","notify_on_restock":true,"webhook_url":"https://example.com/hook"}'

# 4. Trends, history, and CSV (use the product id from step 2)
curl -s "$API/products/1/trends?days=30" -H "$AUTH"
curl -s "$API/products/1/history" -H "$AUTH"
curl -s "$API/products/1/history.csv?normalized=true" -H "$AUTH" -o product-1.csv

# 5. Notifications
curl -s "$API/notifications?unread=true" -H "$AUTH"
curl -s -X POST $API/notifications/1/read -H "$AUTH"
```

Mock product URLs have the form `http://<store>.mock:8080/items/<id>` with stores `shopalpha`, `betamart`, `gammagoods` and item ids `1001` to `1005`. The `.mock` hostnames are network aliases that resolve only inside the Compose network, which is fine because the API container does the scraping. From your host you can inspect the mock stores at http://localhost:8080 via `GET /stores/{store_key}/items` and `GET /stores/{store_key}/items/{item_id}`.

Adding a product that already exists reuses it and returns your existing watch, so use `PATCH /watches/{id}` to change its settings (`POST /watches` returns 409 for a product you already watch).

Admin routes need the seeded admin account: log in with `ADMIN_EMAIL` as the username.

## Endpoints

`GET /health` is outside the `/api/v1` prefix. List endpoints take `limit` (default 50, max 200) and `offset` and return `{items, total, limit, offset}`.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | none | DB connectivity check |
| POST | `/api/v1/auth/register` | none | Create a `user` account |
| POST | `/api/v1/auth/login` | none | OAuth2 password form, returns bearer token |
| GET | `/api/v1/auth/me` | user | Current user profile |
| POST | `/api/v1/products` | user | Add product by URL (scrapes immediately, creates watch) |
| GET | `/api/v1/products` | user | List products (`retailer`, `in_stock` filters) |
| GET | `/api/v1/products/{id}` | user | Product detail |
| GET | `/api/v1/products/{id}/history` | user | Raw snapshots, newest first |
| GET | `/api/v1/products/{id}/trends` | user | Normalized series and stats (`days`, `include_outliers`) |
| GET | `/api/v1/products/{id}/history.csv` | user | CSV export (`normalized`, `days`, `include_outliers`) |
| GET | `/api/v1/watches` | user | Your watches |
| POST | `/api/v1/watches` | user | Watch an existing product |
| PATCH | `/api/v1/watches/{id}` | user | Update a watch (owner only) |
| DELETE | `/api/v1/watches/{id}` | user | Delete a watch (owner only) |
| GET | `/api/v1/notifications` | user | Your notifications (`unread=true` filter) |
| POST | `/api/v1/notifications/{id}/read` | user | Mark read (owner only) |
| GET | `/api/v1/admin/retailers` | admin | List retailers |
| POST | `/api/v1/admin/retailers` | admin | Create a retailer |
| PATCH | `/api/v1/admin/retailers/{id}` | admin | Update retailer (`active`, `rate_limit_seconds`, ...) |
| POST | `/api/v1/admin/scrape-runs` | admin | Trigger a scrape run now (202) |
| GET | `/api/v1/admin/scrape-runs` | admin | List past runs |

Errors return `{"detail": ...}`: 400 unsupported retailer, 401 bad or missing token, 403 non-admin, 404 not found or not yours, 409 duplicate, 502 product page could not be fetched or parsed.

## Configuration

Loaded from the environment (and `.env`) by `app/config.py`. Defaults below are the code defaults; `.env.example` overrides some of them.

| Variable | Code default | Meaning |
|----------|--------------|---------|
| `DATABASE_URL` | `postgresql+psycopg://pricewatch:pricewatch@db:5432/pricewatch` | Main database |
| `TEST_DATABASE_URL` | `postgresql+psycopg://pricewatch:pricewatch@db-test:5432/pricewatch_test` | Test suite database |
| `JWT_SECRET` | `dev-insecure-secret` | HS256 signing key; `.env.example` uses `change-me`. Override outside local dev |
| `JWT_EXPIRE_MINUTES` | `60` | Token lifetime |
| `SCRAPE_INTERVAL_MINUTES` | `60` | Scheduler interval |
| `SCHEDULER_ENABLED` | `true` | Set `false` to disable the scheduler (tests and CI do) |
| `SCRAPER_TIMEOUT_SECONDS` | `10` | HTTP timeout per scrape |
| `SCRAPER_MAX_RETRIES` | `3` | Retries on network errors and 5xx |
| `ADMIN_EMAIL` | unset | Admin seeded at startup (skipped if unset) |
| `ADMIN_PASSWORD` | unset | Password for the seeded admin |
| `LOG_LEVEL` | `INFO` | Log level |

The mock retailer service also reads `MOCK_TICK_SECONDS` (default 300): mock prices and stock change each time the tick window rolls over, so lower it to see price movement sooner. It is not in `.env.example`; set it in the `mock-retailers` service environment in `docker-compose.yml` if you want to change it.

## Architecture

```
app/
  main.py        FastAPI app, lifespan (starts scheduler), /health
  config.py      pydantic-settings
  db.py          engine and session
  scheduler.py   APScheduler scrape job
  seed.py        retailers + admin seeding (run by entrypoint)
  api/           deps (auth, admin guard) and routes/ (auth, products, history, watches, notifications, admin)
  models/        SQLAlchemy models: user, retailer, product, price_snapshot, watch, notification, scrape_run
  schemas/       Pydantic request/response models
  scrapers/      base interface, registry, shopalpha, betamart, gammagoods
  services/      auth, products, scraping, scrape_runs, rate_limit, analytics, alerts, webhooks
mock_retailers/  standalone FastAPI app serving the fake stores
alembic/         migrations
tests/           pytest suite
```

**Mock retailers.** One container on port 8080 serves all three stores. The store is chosen from the `Host` header (`shopalpha.mock`, `betamart.mock`, `gammagoods.mock` are Compose aliases). Each store uses a different markup style: ShopAlpha embeds JSON-LD, BetaMart uses `data-*` attributes, GammaGoods uses plain CSS classes. Each has a matching scraper in `app/scrapers/`.

**Scheduler and scraping.** Every `SCRAPE_INTERVAL_MINUTES` the job scrapes all products of active retailers. Each product scrape fetches the page (retrying with backoff), parses it, inserts a snapshot, updates the product's current price and stock, and evaluates watches. Requests per domain are spaced by `retailers.rate_limit_seconds`. Each run is recorded in `scrape_runs` (attempted, succeeded, failed counts); a failure on one product does not abort the run.

**Analytics** (`app/services/analytics.py`, pure functions over a DataFrame): outlier filter (drop price <= 0; with 8 or more points also drop IQR outliers) then daily resample (last price per day, forward-filled) then 7- and 30-day moving averages then stats (current, min, max, mean, pct_change, all-time-low flag, vs 30-day average).

**Alerts** (`app/services/alerts.py`), evaluated after every snapshot for each active watch:
- Price drop: uses a per-watch `price_alert_active` flag. Fires once when the price is at or below `target_price` and the flag is off; the flag re-arms when the price rises above target or when `target_price` is changed via PATCH.
- Restock: fires when `notify_on_restock` is set and stock goes from out to in.
- Each trigger inserts a notification; if the watch has a `webhook_url`, a JSON payload is POSTed after commit (5s timeout, no retries). Delivery status is recorded on the notification and a webhook failure never fails the scrape.

## Development

Everything runs in Docker; no local Python setup is needed.

| Command | Does |
|---------|------|
| `make up` | Build and start the stack in the background |
| `make down` | Stop the stack |
| `make logs` | Follow API logs |
| `make migrate` | `alembic upgrade head` |
| `make lint` | `ruff check .` |
| `make test` | Start `db-test` (Postgres 16, tmpfs) and run pytest; coverage must be at least 85% |

Create a migration after changing models:

```sh
docker compose run --rm -v "$PWD":/app api alembic revision --autogenerate -m "describe change"
docker compose build api && make migrate
```

The image copies source at build time, so mount the repo (`-v "$PWD":/app`) when generating a revision so the file is written to `alembic/versions/` on the host, then rebuild before applying it.

CI (`.github/workflows/ci.yml`) runs on every push and pull request: Postgres 16 service, Python 3.12, `ruff check .` and `ruff format --check .`, `alembic upgrade head`, then `pytest` with the scheduler disabled. The 85% coverage gate is configured in `pyproject.toml`.

## Known limitations and open questions

From SPEC.md section 15:

- Webhook URLs are user-supplied and fetched server-side. Block private and internal addresses (SSRF) before any non-local deployment.
- Webhooks are not retried and payloads are not signed.
- No snapshot retention or partitioning yet.
- USD only; no email alerts; no frontend.
- Real retailer adapters would need robots.txt/ToS compliance and anti-bot handling.
- The scheduler is in-process, so multiple API replicas would run duplicate jobs.
- Set a real `JWT_SECRET` and admin password outside local dev.
