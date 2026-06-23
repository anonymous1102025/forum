# Architecture

## Data flow

```
Google Analytics 4
       │
       │  GA4 Data API (RunReport + GetMetadata)
       ▼
ga4_client.py  ──── thread-local credentials ────  account_manager.py
       │                                                    │
       │  raw rows (list[dict])                    accounts.json
       ▼
fetcher.py
  1. Fetch all GA4 reports for one date
  2. Transform / normalise / derive computed fields
  3. DELETE existing rows for that date (idempotent)
  4. Write to SQLite
       │
       ▼
database.py (SQLite, WAL mode)
       │
       │  pre-computed reads
       ▼
routes.py (FastAPI)
  - Accepts period params (daily/weekly/monthly/custom)
  - Aggregates across dates in SQLite
  - Returns JSON
       │
       ▼
React frontend
  - Tabs: Overview | Traffic | Content | Audience | Timing
  - Recharts for charts
  - No external UI library
```

## Why SQLite?

- Zero infrastructure — runs on a laptop or a $5 VPS
- WAL mode allows concurrent reads while writing
- Each account gets its own `.db` file — clean isolation
- Fast enough for this workload (daily fetches, <100k rows)

## The fetch-at-write principle

All expensive aggregations (percentages, medians, derived KPIs) happen in `fetcher.py` at fetch time, not at query time. The API routes just `SELECT` pre-computed values. This keeps the API fast (< 5ms) regardless of date range.

## Multi-account design

`account_manager.py` stores a registry in `accounts.json`. Each account has:
- Its own GA4 credentials (service account key path)
- Its own SQLite database file
- `ga4_client.py` uses thread-local storage to hold per-request credentials

All API endpoints accept an optional `?account=slug` parameter.

## Scheduler

`APScheduler` runs a daily job at `FETCH_HOUR_UTC` (default 06:00 UTC). It fetches the previous UTC day for all registered accounts. On startup, it also checks if yesterday is missing and fetches it automatically.

## SQLite schema

| Table | Key | What it stores |
|---|---|---|
| `fetch_runs` | id | Audit log — every fetch attempt |
| `daily_kpis` | date | Headline KPIs: sessions, users, pageviews, engagement |
| `hourly_stats` | date, hour | Hour-by-hour sessions + pageviews |
| `traffic_sources_daily` | date, channel | Sessions by GA4 channel group |
| `top_pages_daily` | date, page_path | Page views + avg engagement time |
| `device_daily` | date, device_category | Sessions by device |
| `city_stats_daily` | date, city, country | Sessions by city |
| `utm_daily` | date, source, medium, campaign | Tagged link traffic |
| `events_daily` | date, event_name | All GA4 events with counts |
| `landing_pages_daily` | date, landing_page | First pages visitors see |
| `browsers_daily` | date, browser | Sessions by browser |
| `countries_daily` | date, country | Sessions by country |
| `referrers_daily` | date, referrer | External referral sources |
| `search_terms_daily` | date, search_term | Site search queries |

## File map

```
backend/
  main.py              FastAPI app, scheduler, lifespan
  config.py            Env var settings (pydantic-settings)
  account_manager.py   accounts.json CRUD
  database.py          SQLite schema, upsert/query helpers
  ga4_client.py        All GA4 Data API queries
  ga4_explorer.py      One-shot tool: metadata + full data snapshot
  fetcher.py           Fetch orchestrator (fetch_date, fetch_date_range)
  routes.py            All FastAPI route handlers
  requirements.txt
  .env / .env.example
  accounts.json        Account registry
  data/                SQLite DB files (gitignored)
  keys/                Service account JSON keys (gitignored)
```
