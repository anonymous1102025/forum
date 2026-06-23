# Setup Guide

## 1. Google Analytics 4 — Service Account

We use a **service account** (server-to-server auth) — no OAuth pop-ups, no user consent needed.

### Create the service account

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project (or use an existing one)
3. Enable the **Google Analytics Data API**:
   - APIs & Services → Library → search "Google Analytics Data API" → Enable
4. Create a service account:
   - APIs & Services → Credentials → Create Credentials → Service Account
   - Give it any name (e.g. `forum-analytics-reader`)
   - Role: leave blank (GA4 handles its own permissions)
   - Click "Done"
5. Download the JSON key:
   - Click the service account → Keys → Add Key → JSON
   - Save as `backend/keys/<your-site>.json`
   - **Never commit this file** — it's in `.gitignore`

### Grant the service account access to GA4

1. Go to [Google Analytics](https://analytics.google.com)
2. Admin → Property → Property Access Management
3. Click the `+` button → Add users
4. Email = the service account email (looks like `name@project.iam.gserviceaccount.com`)
5. Role = **Viewer** (read-only is enough)
6. Save

### Find your GA4 Property ID

- Admin → Property → Property Settings
- The **Property ID** is a numeric ID like `123456789`
- This is NOT the measurement ID (which starts with `G-`)

---

## 2. Run the explorer (recommended first step)

The explorer connects to your GA4 property, fetches the **Metadata API** (which tells you every dimension and metric available, including your custom events), and saves a report.

```bash
cd backend
python ga4_explorer.py \
  --credentials keys/your-site.json \
  --property 123456789 \
  --output ../docs/ga4_exploration_report.md
```

Read `docs/ga4_exploration_report.md` to understand what data your property has.

---

## 3. Register your account in the app

```bash
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Forum",
    "website": "https://myforum.com",
    "ga4_property_id": "123456789",
    "ga4_credentials_path": "keys/your-site.json"
  }'
```

Or create `backend/accounts.json` manually:

```json
[
  {
    "slug": "myforum",
    "name": "My Forum",
    "website": "https://myforum.com",
    "ga4_property_id": "123456789",
    "ga4_credentials_path": "keys/your-site.json",
    "db_path": "data/myforum.db"
  }
]
```

---

## 4. Run the backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

On startup it:
- Initialises the SQLite DB
- Checks if yesterday's data is missing → fetches it automatically
- Starts a scheduler to fetch every day at 06:00 UTC

---

## 5. Backfill historical data

```bash
# Fetch last 90 days
curl -X POST "http://localhost:8000/api/fetch/backfill?from=2026-03-01&to=2026-06-08&account=myforum"
```

Runs in the background — check progress at `/api/fetch/status`.

---

## 6. Run the frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## Environment variables (backend/.env)

```env
FETCH_HOUR_UTC=6        # Hour (UTC) to run the daily fetch
FETCH_ON_STARTUP=true   # Auto-fetch yesterday on startup if missing
CORS_ORIGINS=http://localhost:3000 http://localhost:5173
```

---

## Security notes

- `backend/keys/` is gitignored — never commit service account keys
- `backend/data/` is gitignored — SQLite files can be large
- The GA4 service account has Viewer access only — it cannot modify your analytics setup
