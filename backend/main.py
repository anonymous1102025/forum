"""
main.py
=======
FastAPI entry-point.

- Registers all routes from routes.py
- Initialises SQLite DB for every registered account on startup
- Schedules daily GA4 fetch at FETCH_HOUR_UTC (default 06:00 UTC)
- Optionally back-fills yesterday on startup if data is missing
- Configures CORS for the React dev server

Run:
    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta, timezone, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db, get_conn, get_available_dates
from routes import router
import account_manager as acm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("analytics")

scheduler = AsyncIOScheduler(timezone="UTC")


async def _daily_fetch_job() -> None:
    import asyncio
    from fetcher import fetch_date

    yesterday = str(date.today() - timedelta(days=1))
    for acc_summary in acm.list_accounts():
        acc = acm.get_account(acc_summary["slug"])
        if not acc:
            continue
        log.info(f"[scheduler] Daily fetch for {acc['name']} — {yesterday}")
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, fetch_date, yesterday, acc
            )
            log.info(f"[scheduler] {acc['name']} done: {result}")
        except Exception as e:
            log.error(f"[scheduler] {acc['name']} failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting GA4 Analytics API …")

    # Initialise DB schema for every registered account
    for acc_summary in acm.list_accounts():
        acc = acm.get_account(acc_summary["slug"])
        if acc:
            init_db(acc["db_path"])
            log.info(f"  DB initialised: {acc['name']} → {acc['db_path']}")

    # Schedule daily fetch
    scheduler.add_job(
        _daily_fetch_job,
        trigger=CronTrigger(hour=settings.fetch_hour_utc, minute=0),
        id="daily_fetch",
        replace_existing=True,
    )
    scheduler.start()
    log.info(f"Scheduler started — daily fetch at {settings.fetch_hour_utc:02d}:00 UTC")

    # Auto-fetch yesterday on startup if data is missing
    if settings.fetch_on_startup:
        import asyncio
        from fetcher import fetch_date

        yesterday = str(date.today() - timedelta(days=1))
        for acc_summary in acm.list_accounts():
            acc = acm.get_account(acc_summary["slug"])
            if not acc:
                continue
            with get_conn(acc["db_path"]) as conn:
                available = get_available_dates(conn)
            if yesterday not in available:
                log.info(f"[startup] {acc['name']}: {yesterday} not in DB — auto-fetching …")
                try:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, fetch_date, yesterday, acc)
                    log.info(f"[startup] {acc['name']} done: {result}")
                except Exception as e:
                    log.error(f"[startup] {acc['name']} failed: {e}")
            else:
                log.info(f"[startup] {acc['name']}: {yesterday} already in DB — skipping.")

    yield

    scheduler.shutdown(wait=False)
    log.info("Scheduler shut down.")


app = FastAPI(
    title="Forum Analytics API",
    description="GA4 data pipeline + analytics API for content/forum sites",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "utc_now": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
