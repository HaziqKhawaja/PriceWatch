# PriceWatch — Technical Specification

PriceWatch is a REST API that tracks price and stock of products across retailers, scrapes them on a schedule, normalizes history with Pandas, and alerts users on price drops and restocks. This document is the v1 technical spec.

## Table of Contents

1. [Overview & Goals](#1-overview--goals)
2. [Tech Stack](#2-tech-stack)
3. [Architecture](#3-architecture)
4. [Data Model](#4-data-model)
5. [Scraping & Scheduling](#5-scraping--scheduling)
6. [Analytics (Pandas)](#6-analytics-pandas)
7. [Alerts](#7-alerts)
8. [Authentication & Authorization](#8-authentication--authorization)
9. [API Endpoints](#9-api-endpoints)
10. [Configuration](#10-configuration)
11. [Testing Strategy](#11-testing-strategy)
12. [Docker & Local Development](#12-docker--local-development)
13. [Continuous Integration](#13-continuous-integration)
14. [Milestones](#14-milestones)
15. [Future Work & Open Questions](#15-future-work--open-questions)

---

## 1. Overview & Goals

**Goals**

- Expose a REST API to track price and stock for products across multiple retailers.
- Scrape tracked products on a schedule and keep a full price/stock history.
- Normalize history with Pandas (outlier removal, daily resampling, moving averages, summary stats).
- Alert users on price drops and restocks via a database notification record and an optional webhook.
- Allow users to add products by pasting a product URL.
- Export history as CSV.

**Non-goals (v1)**

- No frontend UI.
- No scraping of real retailers; v1 targets three bundled mock retailers.
- No Celery or Redis; scheduling runs in-process.
- No multi-currency support; all prices are USD.

## 2. Tech Stack

| Component | Choice | Purpose |
|---|---|---|
| Language | Python 3.12 | Runtime |
| Web framework | FastAPI | REST API, OpenAPI docs |
| Validation / settings | Pydantic v2 + pydantic-settings | Schemas, env-based config |
| ORM | SQLAlchemy 2.0 (sync) with psycopg 3 | Persistence |
| Migrations | Alembic | Schema versioning |
| Database | PostgreSQL 16 | Primary store (also used for tests) |
| HTTP client | Requests | Fetching retailer pages |
| HTML parsing | BeautifulSoup4 | Scraper parsers |
| Data analysis | Pandas | History normalization, stats, CSV export |
| Scheduler | APScheduler | In-process periodic scrape job |
| JWT | PyJWT | Token encode/decode (HS256) |
| Password hashing | passlib[bcrypt] | Password storage |
| Testing | PyTest, pytest-cov, httpx TestClient, `responses` | Unit/API tests, coverage gate, HTTP mocking |
| Linting | ruff | Lint (and format) |
| Containers | Docker + docker-compose | Local dev and test environment |
| CI | GitHub Actions | Lint, migrate, test on push/PR |

## 3. Architecture

### 3.1 Services and data flow

```
                         docker-compose
 ┌──────────────────────────────────────────────────────────────┐
 │                                                              │
 │  client ──HTTP /api/v1──►  api (FastAPI)                     │
 │  (curl, scripts)           │  ├─ routes ► services ► SQLAlchemy│
 │                            │  └─ APScheduler (in-process)    │
 │                            │        │                        │
 │                            │        ▼ every N minutes        │
 │                            │   scraping service              │
 │                            │     │  GET (Requests)           │
 │                            │     ▼                           │
 │                            │  mock-retailers ◄── 3 fake stores│
 │                            │     (HTML)                      │
 │                            │     │ parse via scraper registry│
 │                            │     ▼                           │
 │                            │  snapshot + product update      │
 │                            │     ▼                           │
 │                            │  alerts service ──► notifications row
 │                            │                  └─► POST webhook_url
 │                            ▼                                 │
 │                         db (Postgres 16)                     │
 │                                                              │
 │                         db-test (Postgres 16, tests only)    │
 └──────────────────────────────────────────────────────────────┘
```

| Service | Description |
|---|---|
| `api` | FastAPI app with the APScheduler instance started in the lifespan handler. |
| `db` | PostgreSQL 16, application data. |
| `db-test` | Separate PostgreSQL 16 used only by the test suite. |
| `mock-retailers` | Small static/FastAPI app serving 3 fake stores with different HTML structures. Prices and stock change over time (seeded random walk) so scraping produces real history. |

### 3.2 Scraper plugin interface

```python
# app/scrapers/base.py
@dataclass(frozen=True)
class ScrapeResult:
    price: Decimal              # quantized to 0.01
    in_stock: bool
    title: str
    external_id: str | None     # retailer SKU, stored in products.external_id
    currency: str = "USD"

class ParseError(Exception): ...

class BaseScraper(ABC):
    key: str     # matches retailers.scraper_key
    domain: str  # hostname this scraper handles

    def matches(self, url: str) -> bool: ...  # hostname equality, port ignored

    @abstractmethod
    def parse(self, html: str) -> ScrapeResult: ...  # raises ParseError on failure

# app/scrapers/registry.py  (keyed by scraper_key)
def get_scraper_by_key(key: str) -> BaseScraper | None: ...
def get_scraper_for_url(url: str) -> BaseScraper | None: ...  # None => unsupported
```

### 3.3 Mock retailers

| Key | Domain | Markup style |
|---|---|---|
| `shopalpha` | `shopalpha.mock` | Price/stock/title in a JSON-LD `<script type="application/ld+json">` Product block |
| `betamart` | `betamart.mock` | Values in HTML data attributes (e.g. `data-price`, `data-stock`) |
| `gammagoods` | `gammagoods.mock` | Plain CSS classes (e.g. `.price`, `.stock-status`, `.product-title`) |

All three stores are served by the single `mock-retailers` container on port 8080. The three domains are compose network aliases of that service, and the app picks the store from the `Host` header. Product URLs look like `http://shopalpha.mock:8080/items/4412`. Retailer matching uses the URL hostname only, so the port is ignored.

### 3.4 Directory layout

```
PriceWatch/
├── app/
│   ├── main.py            # app factory, lifespan, router wiring
│   ├── config.py          # pydantic-settings
│   ├── db.py              # engine, session dependency
│   ├── scheduler.py       # APScheduler setup and job
│   ├── models/            # SQLAlchemy models
│   ├── schemas/           # Pydantic schemas
│   ├── api/routes/        # FastAPI routers
│   ├── services/
│   │   ├── scraping.py
│   │   ├── analytics.py
│   │   ├── alerts.py
│   │   └── auth.py
│   └── scrapers/          # base, registry, shopalpha, betamart, gammagoods
├── mock_retailers/        # fake store app
├── alembic/
├── tests/
│   ├── unit/
│   ├── api/
│   └── fixtures/html/
├── docker/entrypoint.sh   # migrate, seed, start uvicorn
├── .github/workflows/ci.yml
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml         # ruff, pytest, coverage config
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── SPEC.md
```

## 4. Data Model

All timestamps are `timestamptz`; all money columns are `Numeric(10,2)` (USD). Primary keys are integer identities named `id`. Managed by Alembic.

### 4.1 `users`

| Column | Type | Constraints |
|---|---|---|
| id | integer | PK |
| email | text | NOT NULL, UNIQUE |
| hashed_password | text | NOT NULL |
| role | text | NOT NULL, CHECK in (`user`, `admin`), default `user` |
| created_at | timestamptz | NOT NULL, default now() |

### 4.2 `retailers`

| Column | Type | Constraints |
|---|---|---|
| id | integer | PK |
| name | text | NOT NULL |
| domain | text | NOT NULL, UNIQUE |
| scraper_key | text | NOT NULL (maps to `BaseScraper.key`) |
| active | boolean | NOT NULL, default true |
| rate_limit_seconds | integer | NOT NULL, default 1 |

### 4.3 `products`

Products are global and shared across users.

| Column | Type | Constraints |
|---|---|---|
| id | integer | PK |
| retailer_id | integer | NOT NULL, FK `retailers.id` |
| url | text | NOT NULL, UNIQUE |
| title | text | NOT NULL |
| external_id | text | NULL (retailer SKU) |
| current_price | Numeric(10,2) | NULL until first successful scrape |
| in_stock | boolean | NULL until first successful scrape |
| last_scraped_at | timestamptz | NULL |
| created_at | timestamptz | NOT NULL, default now() |

### 4.4 `price_snapshots`

| Column | Type | Constraints |
|---|---|---|
| id | integer | PK |
| product_id | integer | NOT NULL, FK `products.id` ON DELETE CASCADE |
| price | Numeric(10,2) | NOT NULL |
| in_stock | boolean | NOT NULL |
| scraped_at | timestamptz | NOT NULL, default now() |

Index: `ix_price_snapshots_product_id_scraped_at` on (`product_id`, `scraped_at`).

### 4.5 `watches`

| Column | Type | Constraints |
|---|---|---|
| id | integer | PK |
| user_id | integer | NOT NULL, FK `users.id` ON DELETE CASCADE |
| product_id | integer | NOT NULL, FK `products.id` ON DELETE CASCADE |
| target_price | Numeric(10,2) | NULL (no price alert if null) |
| notify_on_restock | boolean | NOT NULL, default false |
| webhook_url | text | NULL |
| active | boolean | NOT NULL, default true |
| price_alert_active | boolean | NOT NULL, default false (set when a price-drop alert fires; see section 7) |
| created_at | timestamptz | NOT NULL, default now() |

Constraint: UNIQUE (`user_id`, `product_id`).

### 4.6 `notifications`

| Column | Type | Constraints |
|---|---|---|
| id | integer | PK |
| watch_id | integer | NOT NULL, FK `watches.id` ON DELETE CASCADE |
| type | text | NOT NULL, CHECK in (`price_drop`, `restock`) |
| message | text | NOT NULL |
| price | Numeric(10,2) | NULL |
| created_at | timestamptz | NOT NULL, default now() |
| delivered | boolean | NOT NULL, default false (true only after a successful webhook POST) |
| delivery_error | text | NULL |
| read_at | timestamptz | NULL until the user marks it read |

### 4.7 `scrape_runs`

| Column | Type | Constraints |
|---|---|---|
| id | integer | PK |
| started_at | timestamptz | NOT NULL |
| finished_at | timestamptz | NULL until the run completes |
| products_attempted | integer | NOT NULL, default 0 |
| succeeded | integer | NOT NULL, default 0 |
| failed | integer | NOT NULL, default 0 |
| error_summary | text | NULL |

### 4.8 Relationships

- `retailers` 1—N `products`
- `products` 1—N `price_snapshots`
- `users` 1—N `watches` N—1 `products` (many-to-many between users and products via `watches`)
- `watches` 1—N `notifications`

## 5. Scraping & Scheduling

**Scheduler**

- An APScheduler job runs every `SCRAPE_INTERVAL_MINUTES` (default 60), started in the FastAPI lifespan, in-process.
- `SCHEDULER_ENABLED=false` disables it; tests use this.
- Admins can trigger a run immediately (see section 9).

**Per-product scrape**

1. GET the product URL with a timeout (`SCRAPER_TIMEOUT_SECONDS`) and a custom `User-Agent`.
2. On network errors or 5xx responses, retry up to 3 times (`SCRAPER_MAX_RETRIES`) with exponential backoff of 1s, 2s, 4s.
3. Parse the response with the scraper resolved from the registry.
4. Insert a `price_snapshots` row.
5. Update the product's `current_price`, `in_stock`, `last_scraped_at`.
6. Evaluate watches (section 7).

**Rate limiting**: requests to a domain are spaced by at least `retailers.rate_limit_seconds`.

**Run tracking**: each run creates a `scrape_runs` row recording attempted/succeeded/failed counts and `error_summary`. Parse failures are logged, count as failed, and do not abort the run. Inactive retailers (`active = false`) are skipped.

**Adding a product** (`POST /products` with a URL)

1. Match the URL's domain to a retailer; respond 400 if unsupported.
2. Normalize the URL (lowercase scheme and host, drop fragment and trailing slash). If a product with that URL exists, reuse it without scraping. Otherwise scrape immediately (502 on fetch/parse failure) and create the product plus its first snapshot.
3. Get or create the requesting user's watch (re-posting returns the existing watch).

## 6. Analytics (Pandas)

All logic lives in `app/services/analytics.py` as pure functions that take a DataFrame (columns `scraped_at`, `price`, `in_stock`) and return DataFrames/dicts. No DB access, so they are directly unit testable.

**Pipeline**

1. **Outlier filter** — drop rows with `price <= 0`. If there are 8 or more points, additionally drop IQR outliers: keep prices within [Q1 − 1.5·IQR, Q3 + 1.5·IQR]. With fewer than 8 points only the `<= 0` filter applies. Skipped entirely when `include_outliers=true`.
2. **Daily resample** — resample to 1 day taking the last price per day; forward-fill gaps. `in_stock` is resampled the same way (last per day) and forward-filled.
3. **Moving averages** — 7-day and 30-day rolling means over the daily series, `min_periods=1`.
4. **Stats** — computed over the window: `current`, `min`, `max`, `mean`, `pct_change` over the window (first to last daily price), `is_all_time_low` flag, and current price vs 30-day average.

**Query parameters**: `days` (window, default 90, range 1–3650), `include_outliers` (default false).

**Windowing rules**

- Moving averages are computed over the full daily history *before* the window is cut, so `ma_30` on the first window day already reflects the preceding 30 days.
- The window is the last `days` calendar days (UTC) ending today. The series never extends past the last observed day.
- `include_outliers=true` skips filtering entirely (including the `price <= 0` rule). If that makes a percentage's base 0, the percentage is `null`.

**Trends output shape**

```json
{
  "product_id": 12,
  "days": 90,
  "include_outliers": false,
  "series": [
    {
      "date": "2026-11-24",
      "price": 49.99,
      "in_stock": true,
      "ma_7": 51.20,
      "ma_30": 53.10
    }
  ],
  "stats": {
    "current": 49.99,
    "min": 44.50,
    "max": 62.00,
    "mean": 53.40,
    "pct_change": -8.3,
    "is_all_time_low": false,
    "vs_30d_avg_pct": -5.9
  }
}
```

Edge cases: empty input returns `series: []` and null stats; a single point returns one series row with `pct_change: 0`.

The all-time-low flag compares the current price to the minimum across the product's full (outlier-filtered) history, not just the window. The CSV export (`?normalized=true`) uses the same normalized DataFrame via `to_csv`.

## 7. Alerts

Alerts are evaluated by the alerts service after every snapshot is written, for each active watch on that product. Rules compare the new snapshot against the **previous** snapshot (if any).

**Price drop** uses a per-watch flag, `watches.price_alert_active`:
- If `target_price` is set, the new price is `<= target_price`, and the flag is off, a notification is created and the flag is turned on.
- If the new price is `> target_price`, the flag is turned off, which re-arms the alert.
- Changing `target_price` through `PATCH /watches/{id}` also turns the flag off.

This fires once per drop below target and never repeats while the price stays there. Unlike a rule that compares each snapshot with the previous one, it also fires when a watch is created (or its target raised) while the price is already below target.

**Restock** triggers when `watch.notify_on_restock` is true and stock went from `false` (previous snapshot) to `true` (new snapshot). A first snapshot (no previous) never triggers a restock.

**On trigger**

1. Insert a `notifications` row (`type`, `message`, `price`) in the same transaction as the snapshot.
2. After that transaction commits, if `webhook_url` is set, POST a JSON payload with a 5s timeout. On success set `delivered = true`. On failure or non-2xx, store the error in `delivery_error`. No retries in v1. A webhook failure never marks the product scrape as failed.

**Example webhook payload**

```json
{
  "type": "price_drop",
  "notification_id": 481,
  "watch_id": 7,
  "product": {
    "id": 12,
    "title": "Acme Wireless Headphones",
    "url": "http://shopalpha.mock:8080/items/4412",
    "retailer": "ShopAlpha"
  },
  "price": 49.99,
  "target_price": 50.00,
  "previous_price": 54.99,
  "in_stock": true,
  "currency": "USD",
  "triggered_at": "2026-11-26T14:03:11Z"
}
```

For `restock`, `type` is `"restock"` and `target_price` may be null.

## 8. Authentication & Authorization

- **Tokens**: JWT bearer, HS256, signed with `JWT_SECRET`, expiry `JWT_EXPIRE_MINUTES` (default 60). Claims: `sub` (user id), `role`, `exp`. Implemented with PyJWT.
- **Passwords**: hashed with bcrypt via passlib.
- **Login**: OAuth2 password form (`POST /auth/login`) returns `{"access_token": "...", "token_type": "bearer"}`.
- **Roles**: `user` and `admin`. Self-registration always creates `user`.
- **Admin-only routes**: retailer management, manually triggering a scrape run, and viewing `scrape_runs`. Non-admins receive 403; missing/invalid token receives 401.
- **Ownership**: watches and notifications are scoped to the authenticated user; accessing another user's watch returns 404.
- **Admin seeding**: on startup the first admin is created from `ADMIN_EMAIL` / `ADMIN_PASSWORD` if no user with that email exists.


## 9. API Endpoints

All routes live under `/api/v1`, except `GET /health`. Auth is a JWT bearer token (`Authorization: Bearer <token>`). Auth levels: **public** (no token), **user** (any authenticated user), **admin** (role `admin`). Products are global; watches and notifications are per-user.

### 9.1 Conventions

**Pagination.** List endpoints accept `limit` (default `50`, max `200`) and `offset` (default `0`). Responses use the envelope:

```json
{ "items": [ ... ], "total": 137, "limit": 50, "offset": 0 }
```

**Errors.** All errors return `{"detail": ...}`. For 422, `detail` is the FastAPI/Pydantic list of validation errors; otherwise it is a string.

| Status | Used for |
|--------|----------|
| 400 | Unsupported retailer (URL domain has no active retailer) |
| 401 | Missing, invalid, or expired token; bad login credentials |
| 403 | Authenticated but not permitted (non-admin on admin route) |
| 404 | Resource not found, or owned by another user (watches, notifications) |
| 409 | Conflict (duplicate email on register; duplicate watch for the same user and product) |
| 502 | Product page could not be fetched or parsed when adding a product |
| 422 | Request validation failure |

### 9.2 Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | public | Not under `/api/v1`. Runs `SELECT 1`; returns `{"status":"ok"}` or 503 if the DB is unreachable. |

### 9.3 Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | public | Create a `user`-role account (email, password). 409 if email exists. |
| POST | `/auth/login` | public | OAuth2 password form (`username`=email, `password`); returns `{"access_token", "token_type":"bearer"}`. |
| GET | `/auth/me` | user | Current user profile. |

### 9.4 Products

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/products` | user | Submit a product URL. Matches retailer (400 if unsupported), scrapes immediately, creates the product or reuses the existing one, and creates a watch for the caller. |
| GET | `/products` | user | Paginated list. Filters: `retailer` (name or id), `in_stock` (bool). |
| GET | `/products/{id}` | user | Product detail with current price and stock. |

### 9.5 History & Trends

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/products/{id}/history` | user | Raw `price_snapshots`, paginated, newest first. |
| GET | `/products/{id}/trends` | user | Normalized series plus stats. Query: `days` (default 90), `include_outliers` (default `false`). |
| GET | `/products/{id}/history.csv` | user | CSV export (Pandas `to_csv`). `?normalized=true` for the normalized series; default is raw. Also accepts `days` and `include_outliers` when normalized. |

### 9.6 Watches

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/watches` | user | Current user's watches (paginated). |
| POST | `/watches` | user | Watch an existing product (`product_id`, optional `target_price`, `notify_on_restock`, `webhook_url`). 404 unknown product; 409 duplicate. |
| PATCH | `/watches/{id}` | user | Update fields or toggle `active`. Owner only (404 otherwise). |
| DELETE | `/watches/{id}` | user | Delete a watch. Owner only (404 otherwise). Returns 204. |

### 9.7 Notifications

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/notifications` | user | Current user's notifications, newest first, paginated. `?unread=true` filters to `read_at IS NULL`. |
| POST | `/notifications/{id}/read` | user | Mark a notification read (sets `read_at`; idempotent). Owner only (404 otherwise). |

### 9.8 Admin

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/admin/retailers` | admin | List retailers. |
| POST | `/admin/retailers` | admin | Create a retailer (`name`, `domain`, `scraper_key`, `rate_limit_seconds`). 409 on duplicate domain. |
| PATCH | `/admin/retailers/{id}` | admin | Update `active`, `rate_limit_seconds`, etc. |
| POST | `/admin/scrape-runs` | admin | Trigger a scrape run now; returns 202 with the new run record. |
| GET | `/admin/scrape-runs` | admin | List past runs (paginated, newest first). |

### 9.9 Examples

**`POST /api/v1/products`**

Request:

```json
{ "url": "http://shopalpha.mock:8080/items/4412" }
```

Response `201 Created` (`200 OK` if the product already existed; a watch is created either way):

```json
{
  "id": 17,
  "retailer": { "id": 1, "name": "ShopAlpha", "domain": "shopalpha.mock" },
  "url": "http://shopalpha.mock:8080/items/4412",
  "title": "Acme Noise-Cancelling Headphones",
  "external_id": "4412",
  "current_price": "129.99",
  "in_stock": true,
  "last_scraped_at": "2026-11-15T10:02:11Z",
  "created_at": "2026-11-15T10:02:11Z",
  "watch": { "id": 52, "target_price": null, "notify_on_restock": false, "active": true }
}
```

Unsupported domain:

```json
{ "detail": "Unsupported retailer: example.com" }
```

**`GET /api/v1/products/17/trends?days=7`**

```json
{
  "product_id": 17,
  "days": 7,
  "include_outliers": false,
  "series": [
    { "date": "2026-11-09", "price": 139.99, "ma_7": 139.99, "ma_30": 139.99, "in_stock": true },
    { "date": "2026-11-10", "price": 134.99, "ma_7": 137.49, "ma_30": 137.49, "in_stock": true },
    { "date": "2026-11-11", "price": 134.99, "ma_7": 136.66, "ma_30": 136.66, "in_stock": false },
    { "date": "2026-11-12", "price": 134.99, "ma_7": 136.24, "ma_30": 136.24, "in_stock": true },
    { "date": "2026-11-13", "price": 129.99, "ma_7": 134.99, "ma_30": 134.99, "in_stock": true }
  ],
  "stats": {
    "current": 129.99,
    "min": 129.99,
    "max": 139.99,
    "mean": 134.99,
    "pct_change": -7.14,
    "is_all_time_low": true,
    "vs_30d_avg_pct": -3.70
  }
}
```

Empty or single-point history returns `series` with 0 or 1 entries and stats computed over what exists (`pct_change` is `0.0` for a single point; all stats are `null` when empty).

**`POST /api/v1/watches`**

Request:

```json
{
  "product_id": 17,
  "target_price": 119.99,
  "notify_on_restock": true,
  "webhook_url": "https://hooks.example.com/pricewatch"
}
```

Response `201 Created`:

```json
{
  "id": 53,
  "product_id": 17,
  "target_price": "119.99",
  "notify_on_restock": true,
  "webhook_url": "https://hooks.example.com/pricewatch",
  "active": true,
  "created_at": "2026-11-15T10:05:40Z"
}
```

**`GET /api/v1/products/17/history.csv`** (raw, default)

```csv
scraped_at,price,in_stock
2026-11-13T08:00:03+00:00,134.99,True
2026-11-13T09:00:02+00:00,129.99,True
2026-11-13T10:00:04+00:00,129.99,False
```

With `?normalized=true` the columns are `date,price,ma_7,ma_30,in_stock`. Responses use `Content-Type: text/csv` and `Content-Disposition: attachment; filename="product-17-history.csv"`.

---

## 10. Configuration

Settings are loaded by `pydantic-settings` from environment variables (and `.env` in local dev). A `.env.example` is committed with the defaults below.

| Name | Default | Description |
|------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://pricewatch:pricewatch@db:5432/pricewatch` | SQLAlchemy URL for the main database. |
| `TEST_DATABASE_URL` | `postgresql+psycopg://pricewatch:pricewatch@db-test:5432/pricewatch_test` | Database used by the test suite. |
| `JWT_SECRET` | none (required; `.env.example` uses a placeholder) | HS256 signing key. Must be overridden outside local dev. |
| `JWT_EXPIRE_MINUTES` | `60` | Access token lifetime. |
| `SCRAPE_INTERVAL_MINUTES` | `60` | Interval of the APScheduler scrape job. |
| `SCHEDULER_ENABLED` | `true` | Set to `false` to skip starting the scheduler (used by tests). |
| `SCRAPER_TIMEOUT_SECONDS` | `10` | Per-request HTTP timeout for scraping. |
| `SCRAPER_MAX_RETRIES` | `3` | Retries on network errors or 5xx, with 1s/2s/4s backoff. |
| `ADMIN_EMAIL` | none | Email of the seeded first admin (seeding is skipped if unset). |
| `ADMIN_PASSWORD` | none | Password of the seeded first admin. |
| `LOG_LEVEL` | `INFO` | Python logging level. |

When running on the host (outside compose), hostnames `db` and `db-test` become `localhost` with the mapped ports from section 12.

---

## 11. Testing Strategy

Tests run against real PostgreSQL (the `db-test` service), not SQLite, so behavior such as `Numeric(10,2)`, `timestamptz`, and unique constraints matches production.

### 11.1 Fixtures (`tests/conftest.py`)

| Fixture | Scope | Behavior |
|---------|-------|----------|
| `engine` | session | Creates an engine from `TEST_DATABASE_URL` and runs `alembic upgrade head` once, so migrations are exercised too. |
| `db_session` | function | Opens a connection, begins an outer transaction, binds a `Session` with `join_transaction_mode="create_savepoint"`, yields it, then rolls back. No data leaks between tests. |
| `client` | function | `fastapi.testclient.TestClient(app)` with `app.dependency_overrides[get_db]` returning `db_session`. `SCHEDULER_ENABLED=false` is set before the app is imported. |
| `user_token` / `admin_token` | function | Create a `user` and an `admin` row via the service layer and return a signed JWT for each. |
| `auth_headers` / `admin_headers` | function | `{"Authorization": f"Bearer {token}"}` helpers built on the token fixtures. |
| `mock_http` | function | `responses.RequestsMock` activated for the test; outbound HTTP to retailers is served from `tests/fixtures/html/` or failure responses. Any unmatched request fails the test. |
| `seed_retailers` | function | Inserts the three mock retailers (`shopalpha`, `betamart`, `gammagoods`). |

### 11.2 Layout

```
tests/
├── conftest.py
├── fixtures/
│   └── html/
│       ├── shopalpha_in_stock.html      # JSON-LD
│       ├── shopalpha_out_of_stock.html
│       ├── betamart_product.html        # data attributes
│       ├── gammagoods_product.html      # plain CSS classes
│       └── malformed.html
├── unit/
│   ├── test_scrapers.py          # parsers vs. saved HTML
│   ├── test_scraper_registry.py
│   ├── test_scraping_retry.py    # backoff via `responses`
│   ├── test_analytics.py         # synthetic DataFrames
│   ├── test_alerts.py            # edge-trigger logic
│   └── test_security.py          # JWT + password helpers
└── api/
    ├── test_auth.py
    ├── test_products.py          # add product (scraping mocked)
    ├── test_history_trends.py    # trends + CSV
    ├── test_watches.py           # CRUD + ownership (404 for others)
    ├── test_notifications.py
    ├── test_admin.py             # 403 for non-admin
    └── test_health.py
```

### 11.3 What is covered

- **Unit:** each scraper's parser; analytics functions with gaps, outliers (including the under-8-points no-filter case), a single point, and empty input; alert edge-trigger and restock logic; retry/backoff timing (sleep patched) on network errors and 5xx; JWT and password helpers.
- **API:** register/login/me flow; product add with scraping mocked (201, reuse, 400 unsupported); watch CRUD with ownership checks; trends and CSV responses; admin role enforcement; 409 and 422 error paths.

### 11.4 Coverage gate

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=app --cov-report=term-missing --cov-fail-under=85"

[tool.coverage.run]
branch = true
omit = ["alembic/*", "mock_retailers/*"]
```

The test run fails if total coverage drops below 85%.

---

## 12. Docker & Local Development

### 12.1 Dockerfile

Multi-stage build:

1. **`builder`** (`python:3.12-slim`): installs build deps, creates a virtualenv at `/opt/venv`, and installs `requirements.txt` (including dev/test deps in a `dev` build target).
2. **`runtime`** (`python:3.12-slim`): copies `/opt/venv` and the app source, creates a non-root user `app` (`USER app`), sets `PYTHONUNBUFFERED=1`, exposes 8000, and runs `./docker/entrypoint.sh`.

The entrypoint runs `alembic upgrade head`, seeds retailers and the admin user (idempotent), then `exec uvicorn app.main:app --host 0.0.0.0 --port 8000`.

### 12.2 docker-compose.yml outline

```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
      mock-retailers:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request as u; u.urlopen('http://localhost:8000/health')"]
      interval: 10s
      retries: 5

  db:
    image: postgres:16
    environment: { POSTGRES_USER: pricewatch, POSTGRES_PASSWORD: pricewatch, POSTGRES_DB: pricewatch }
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pricewatch -d pricewatch"]
      interval: 5s
      retries: 10

  db-test:
    image: postgres:16
    environment: { POSTGRES_USER: pricewatch, POSTGRES_PASSWORD: pricewatch, POSTGRES_DB: pricewatch_test }
    ports: ["5433:5432"]
    tmpfs: ["/var/lib/postgresql/data"]   # ephemeral, fast
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pricewatch -d pricewatch_test"]
      interval: 5s
      retries: 10

  mock-retailers:
    build: { context: ., dockerfile: mock_retailers/Dockerfile }
    ports: ["8080:8080"]
    networks:
      default:
        aliases: [shopalpha.mock, betamart.mock, gammagoods.mock]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request as u; u.urlopen('http://localhost:8080/health')"]
      interval: 5s
      retries: 10

volumes:
  pgdata:
```

`db-test` is not a dependency of `api`; it is started on demand by the test target (`depends_on` on a `test` profile or `make test`).

### 12.3 Startup sequence

1. `db` and `mock-retailers` become healthy.
2. `api` container starts and the entrypoint runs `alembic upgrade head`.
3. Seed step upserts the retailers (`shopalpha`, `betamart`, `gammagoods`) and creates the admin from `ADMIN_EMAIL`/`ADMIN_PASSWORD` if absent.
4. Uvicorn starts; the FastAPI lifespan starts APScheduler (unless `SCHEDULER_ENABLED=false`).
5. `/health` returns 200; Swagger UI is at `http://localhost:8000/docs`.

Run tests with `docker compose run --rm api pytest` (with `db-test` up).

### 12.4 Makefile targets

| Target | Command |
|--------|---------|
| `up` | `docker compose up --build -d` |
| `down` | `docker compose down` |
| `test` | `docker compose up -d db-test && docker compose run --rm api pytest` |
| `lint` | `docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check ."` |
| `migrate` | `docker compose run --rm api alembic upgrade head` |

---

## 13. Continuous Integration

GitHub Actions runs on every push and pull request. Postgres 16 runs as a service container, so `docker compose` is not needed in CI.

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: pricewatch
          POSTGRES_PASSWORD: pricewatch
          POSTGRES_DB: pricewatch_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U pricewatch -d pricewatch_test"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      DATABASE_URL: postgresql+psycopg://pricewatch:pricewatch@localhost:5432/pricewatch_test
      TEST_DATABASE_URL: postgresql+psycopg://pricewatch:pricewatch@localhost:5432/pricewatch_test
      JWT_SECRET: ci-only-secret
      SCHEDULER_ENABLED: "false"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install dependencies
        run: pip install -r requirements.txt -r requirements-dev.txt
      - name: Lint
        run: |
          ruff check .
          ruff format --check .
      - name: Apply migrations
        run: alembic upgrade head
      - name: Test
        run: pytest   # coverage flags and the 85% gate come from pyproject addopts
```

---

## 14. Milestones

1. **Scaffold, Docker, DB models, Alembic.**
   - `docker compose up` starts `db`, `mock-retailers` (placeholder), and `api` (`db-test` is started by `make test`); `GET /health` returns 200.
   - All tables in section 4 exist via a single Alembic migration; `alembic upgrade head` and `downgrade base` both succeed on a clean DB.
   - `make up|down|lint|migrate` work; `ruff check` passes.

2. **Auth (JWT, roles).**
   - Register, login, and `/auth/me` work; duplicate email returns 409; bad credentials return 401.
   - Expired or tampered tokens return 401; a non-admin hitting an admin route returns 403.
   - Admin is seeded from `ADMIN_EMAIL`/`ADMIN_PASSWORD` on startup, idempotently.

3. **Mock retailers, scrapers, product add.**
   - The mock service serves 3 stores with distinct markup (JSON-LD, data attributes, CSS classes) and time-varying price and stock.
   - Each scraper's parser passes against its saved HTML fixtures; the registry resolves a URL to the right scraper.
   - `POST /products` returns 201 with a scraped product and a watch, reuses an existing product, and returns 400 for an unsupported domain.

4. **Scheduler, retries, scrape_runs.**
   - The scheduler runs every `SCRAPE_INTERVAL_MINUTES`, writes a `price_snapshots` row and updates product fields per product, and is disabled by `SCHEDULER_ENABLED=false`.
   - Retries follow 1s/2s/4s on network errors and 5xx; parse failures are logged and do not abort the run; per-domain rate limiting is honored.
   - Each run creates a `scrape_runs` row with correct attempted/succeeded/failed counts; `POST /admin/scrape-runs` triggers a run and `GET` lists them.

5. **Analytics, trends, CSV.**
   - `services/analytics.py` implements outlier filter, daily resample with forward-fill, 7/30-day MAs, and stats, with unit tests for gaps, outliers, single-point, and empty input.
   - `GET /products/{id}/trends` returns the documented shape and respects `days` and `include_outliers`.
   - `history.csv` returns raw or normalized data with correct headers and content type.

6. **Watches, alerts, webhooks.**
   - Watch CRUD works with owner-only enforcement (404 for others, 409 for duplicates).
   - Price-drop alerts fire once per drop to or below `target_price` (no repeat while the price stays below; re-armed when it rises above or the target changes); restock alerts fire only on false to true.
   - Each alert writes a `notifications` row; webhook delivery POSTs JSON with a 5s timeout and records failures in `delivery_error`; `GET /notifications` supports `?unread`.

7. **Test hardening and CI.**
   - Total coverage is at least 85% and enforced by `--cov-fail-under=85`.
   - The GitHub Actions workflow in section 13 passes on a clean push: ruff, migrations, and pytest.
   - `docker compose run --rm api pytest` passes locally; `.env.example` lists every variable in section 10.

---

## 15. Future Work & Open Questions

Out of scope for v1 (see non-goals), candidates for later:

- **Real retailer adapters:** compliance with robots.txt and ToS, proxy and anti-bot handling, and fixtures captured from real pages.
- **Multi-currency:** add a currency column to snapshots and conversion rates. v1 is USD only.
- **Email alerts:** an additional notification channel beside DB records and webhooks.
- **Frontend dashboard:** charts over `/trends`; v1 is API only.
- **Per-product scrape intervals:** replace the single global interval with adaptive or per-product scheduling.
- **Celery (or similar) workers:** only if scale outgrows the in-process APScheduler; note that multiple API replicas would run duplicate jobs, which needs a single scheduler instance or a lock.

Open questions:

- Webhook retry policy (v1 records failure and does not retry).
- Snapshot retention and partitioning once `price_snapshots` grows large.
- Whether webhook payloads should be signed (HMAC) for receivers.
- Webhook URLs are user-supplied and fetched server-side. Before any non-local deployment, block private and internal addresses to prevent SSRF.
