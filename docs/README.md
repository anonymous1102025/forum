# Forum Analytics — Project Documentation

Google Analytics 4 data pipeline + dashboard for content/media/forum sites.

## What it does

Pulls raw GA4 data daily via the GA4 Data API, normalises and stores it in SQLite, then serves it through a FastAPI backend to a React dashboard. Everything is pre-computed at fetch time — the API just reads from the database.

## Documents in this folder

| File | What it covers |
|---|---|
| [setup.md](setup.md) | How to get GA4 credentials and run the project |
| [architecture.md](architecture.md) | System design, data flow, file map |
| [ga4_data_catalogue.md](ga4_data_catalogue.md) | Complete catalogue of all GA4 dimensions & metrics |
| [ga4_exploration_report.md](ga4_exploration_report.md) | Auto-generated report from running the explorer on your property |

## Quick start

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure one account
python ga4_explorer.py --credentials keys/sa.json --property 123456789

# Start the API
uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

## Project structure

```
forum_analytics/
  docs/              ← you are here
  backend/
    ga4_client.py    ← all GA4 API queries
    ga4_explorer.py  ← one-shot exploration tool (run once to discover data)
    fetcher.py       ← daily fetch orchestrator
    database.py      ← SQLite schema + helpers
    routes.py        ← FastAPI route handlers
    main.py          ← app entry point + scheduler
    account_manager.py
    config.py
    requirements.txt
    data/            ← SQLite DB files (one per account)
    keys/            ← service account JSON keys (gitignored)
  frontend/
    src/
      App.tsx
      api.ts
      types.ts
```
