"""
routes.py
=========
All FastAPI route handlers.

Analytics endpoints
-------------------
GET /api/analytics?period=daily&date=YYYY-MM-DD
GET /api/analytics?period=weekly&week_start=YYYY-MM-DD
GET /api/analytics?period=monthly&month=YYYY-MM
GET /api/analytics?period=custom&start=YYYY-MM-DD&end=YYYY-MM-DD

Utility endpoints
-----------------
GET  /api/dates/available
GET  /api/fetch/status

Control endpoints
-----------------
POST /api/fetch/trigger?date=YYYY-MM-DD
POST /api/fetch/backfill?from=YYYY-MM-DD&to=YYYY-MM-DD

Account endpoints
-----------------
GET    /api/accounts
POST   /api/accounts
GET    /api/accounts/{slug}
PUT    /api/accounts/{slug}
DELETE /api/accounts/{slug}
"""
from __future__ import annotations

from datetime import date, timedelta
from datetime import date as date_cls
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

import database as db
import account_manager as acm

router = APIRouter()


# ── Date utilities ─────────────────────────────────────────────────────────────

def _date_range(start: str, end: str) -> list[str]:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    days, cur = [], s
    while cur <= e:
        days.append(str(cur))
        cur += timedelta(days=1)
    return days


def _week_dates(week_start: str) -> list[str]:
    s = date.fromisoformat(week_start)
    return [str(s + timedelta(days=i)) for i in range(7)]


def _month_dates(month: str) -> list[str]:
    year, mon = int(month[:4]), int(month[5:7])
    s = date(year, mon, 1)
    results, cur = [], s
    while cur.month == mon:
        results.append(str(cur))
        cur += timedelta(days=1)
    return results


def _month_label(month: str) -> str:
    MONTHS = ["", "January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    year, mon = int(month[:4]), int(month[5:7])
    return f"{MONTHS[mon]} {year}"


def _iso_week_label(d: str) -> str:
    return f"W{date.fromisoformat(d).isocalendar().week:02d}"


def _resolve_db(account: Optional[str]) -> str:
    if not account:
        # Default to the first registered account if one exists
        accounts = acm.list_accounts()
        if accounts:
            return acm.get_account(accounts[0]["slug"])["db_path"]
        return db._DEFAULT_DB
    acc = acm.get_account(account)
    if not acc:
        raise HTTPException(404, f"Account '{account}' not found")
    return acc["db_path"]


# ── DB read helpers ────────────────────────────────────────────────────────────

def _ph(dates: list[str]) -> str:
    return ",".join("?" * len(dates))


def _kpis_for_dates(conn, dates: list[str]) -> dict[str, Any]:
    if not dates:
        return {}
    rows = db.query(
        conn,
        f"SELECT * FROM daily_kpis WHERE date IN ({_ph(dates)}) ORDER BY date",
        tuple(dates),
    )
    if not rows:
        return {}

    sessions       = sum(r["sessions"]   for r in rows)
    users          = sum(r["users"]       for r in rows)
    new_users      = sum(r["new_users"]   for r in rows)
    returning      = sum(r["returning_users"] for r in rows)
    pageviews      = sum(r["pageviews"]   for r in rows)
    pps            = round(pageviews / sessions, 2) if sessions else 0.0

    def _wavg(field: str) -> float:
        total = sum(r["sessions"] for r in rows if r["sessions"])
        if not total:
            return 0.0
        weighted = sum(r[field] * r["sessions"] for r in rows if r["sessions"])
        return round(weighted / total, 1)

    return {
        "sessions":                  sessions,
        "users":                     users,
        "new_users":                 new_users,
        "returning_users":           returning,
        "pageviews":                 pageviews,
        "pages_per_session":         pps,
        "avg_session_duration_secs": _wavg("avg_session_duration_secs"),
        "bounce_rate":               _wavg("bounce_rate"),
        "engagement_rate":           _wavg("engagement_rate"),
    }


def _time_series_hourly(conn, date_str: str) -> list[dict]:
    rows = db.query(conn, "SELECT * FROM hourly_stats WHERE date = ? ORDER BY hour", (date_str,))
    hour_map = {r["hour"]: r for r in rows}
    return [
        {
            "label":        f"{h:02d}:00",
            "hour":         h,
            "sessions":     hour_map.get(h, {}).get("sessions", 0),
            "pageviews":    hour_map.get(h, {}).get("pageviews", 0),
            "active_users": hour_map.get(h, {}).get("active_users", 0),
        }
        for h in range(24)
    ]


def _time_series_daily(conn, dates: list[str]) -> list[dict]:
    rows = db.query(
        conn,
        f"SELECT * FROM daily_kpis WHERE date IN ({_ph(dates)}) ORDER BY date",
        tuple(dates),
    )
    return [
        {
            "label":     r["date"],
            "sessions":  r["sessions"],
            "users":     r["users"],
            "pageviews": r["pageviews"],
        }
        for r in rows
    ]


def _time_series_weekly(conn, dates: list[str]) -> list[dict]:
    rows = db.query(
        conn,
        f"SELECT * FROM daily_kpis WHERE date IN ({_ph(dates)}) ORDER BY date",
        tuple(dates),
    )
    buckets: dict[str, dict] = {}
    for r in rows:
        wk = _iso_week_label(r["date"])
        if wk not in buckets:
            buckets[wk] = {"label": wk, "sessions": 0, "users": 0, "pageviews": 0, "_start": r["date"]}
        buckets[wk]["sessions"]  += r["sessions"]
        buckets[wk]["users"]     += r["users"]
        buckets[wk]["pageviews"] += r["pageviews"]
    return sorted(
        [{k: v for k, v in b.items() if k != "_start"} for b in buckets.values()],
        key=lambda x: x["label"],
    )


def _traffic_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    rows = db.query(
        conn,
        f"""SELECT channel,
                   SUM(sessions)  AS sessions,
                   SUM(users)     AS users,
                   SUM(new_users) AS new_users
            FROM traffic_sources_daily WHERE date IN ({_ph(dates)})
            GROUP BY channel ORDER BY sessions DESC LIMIT 15""",
        tuple(dates),
    )
    return [dict(r) for r in rows]


def _pages_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    rows = db.query(
        conn,
        f"""SELECT page_path, page_title,
                   SUM(views)    AS views,
                   SUM(sessions) AS sessions,
                   ROUND(AVG(avg_engagement_time_secs), 1) AS avg_engagement_time_secs
            FROM top_pages_daily WHERE date IN ({_ph(dates)})
            GROUP BY page_path, page_title
            ORDER BY views DESC LIMIT 30""",
        tuple(dates),
    )
    return [dict(r) for r in rows]


def _device_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    rows = db.query(
        conn,
        f"""SELECT device_category,
                   SUM(sessions) AS sessions,
                   SUM(users)    AS users
            FROM device_daily WHERE date IN ({_ph(dates)})
            GROUP BY device_category ORDER BY sessions DESC""",
        tuple(dates),
    )
    return [dict(r) for r in rows]


def _cities_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    rows = db.query(
        conn,
        f"""SELECT city, country,
                   SUM(sessions) AS sessions,
                   SUM(users)    AS users
            FROM city_stats_daily WHERE date IN ({_ph(dates)})
            GROUP BY city, country ORDER BY sessions DESC LIMIT 20""",
        tuple(dates),
    )
    return [dict(r) for r in rows]


def _utm_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    rows = db.query(
        conn,
        f"""SELECT utm_source, utm_medium, utm_campaign,
                   SUM(sessions)  AS sessions,
                   SUM(users)     AS users,
                   SUM(new_users) AS new_users
            FROM utm_daily WHERE date IN ({_ph(dates)})
            GROUP BY utm_source, utm_medium, utm_campaign
            ORDER BY sessions DESC LIMIT 30""",
        tuple(dates),
    )
    return [dict(r) for r in rows]


def _events_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    rows = db.query(
        conn,
        f"""SELECT event_name,
                   SUM(event_count)  AS event_count,
                   SUM(unique_users) AS unique_users
            FROM events_daily WHERE date IN ({_ph(dates)})
            GROUP BY event_name ORDER BY event_count DESC LIMIT 100""",
        tuple(dates),
    )
    return [dict(r) for r in rows]


def _landing_pages_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    rows = db.query(
        conn,
        f"""SELECT landing_page,
                   SUM(sessions)  AS sessions,
                   SUM(users)     AS users,
                   SUM(new_users) AS new_users,
                   ROUND(AVG(bounce_rate), 1)       AS bounce_rate,
                   ROUND(AVG(engagement_rate), 1)   AS engagement_rate,
                   ROUND(AVG(avg_duration_secs), 1) AS avg_duration_secs
            FROM landing_pages_daily WHERE date IN ({_ph(dates)})
            GROUP BY landing_page ORDER BY sessions DESC LIMIT 30""",
        tuple(dates),
    )
    return [dict(r) for r in rows]


def _browsers_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    rows = db.query(
        conn,
        f"""SELECT browser,
                   SUM(sessions) AS sessions,
                   SUM(users)    AS users
            FROM browsers_daily WHERE date IN ({_ph(dates)})
            GROUP BY browser ORDER BY sessions DESC LIMIT 15""",
        tuple(dates),
    )
    return [dict(r) for r in rows]


def _countries_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    rows = db.query(
        conn,
        f"""SELECT country,
                   SUM(sessions)  AS sessions,
                   SUM(users)     AS users,
                   SUM(new_users) AS new_users
            FROM countries_daily WHERE date IN ({_ph(dates)})
            GROUP BY country ORDER BY sessions DESC LIMIT 30""",
        tuple(dates),
    )
    return [dict(r) for r in rows]


def _referrers_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    rows = db.query(
        conn,
        f"""SELECT referrer,
                   SUM(sessions)  AS sessions,
                   SUM(users)     AS users,
                   SUM(new_users) AS new_users
            FROM referrers_daily WHERE date IN ({_ph(dates)})
            GROUP BY referrer ORDER BY sessions DESC LIMIT 20""",
        tuple(dates),
    )
    return [dict(r) for r in rows]


def _search_terms_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    rows = db.query(
        conn,
        f"""SELECT search_term,
                   SUM(sessions)  AS sessions,
                   SUM(users)     AS users,
                   SUM(pageviews) AS pageviews
            FROM search_terms_daily WHERE date IN ({_ph(dates)})
            GROUP BY search_term ORDER BY sessions DESC LIMIT 30""",
        tuple(dates),
    )
    return [dict(r) for r in rows]


def _revenue_for_dates(conn, dates: list[str]) -> dict:
    if not dates:
        return {}
    rows = db.query(
        conn,
        f"""SELECT
               ROUND(SUM(total_revenue), 2)    AS total_revenue,
               ROUND(SUM(purchase_revenue), 2) AS purchase_revenue,
               SUM(purchases)                  AS purchases,
               SUM(transactions)               AS transactions,
               SUM(conversions)                AS conversions
            FROM revenue_daily WHERE date IN ({_ph(dates)})""",
        tuple(dates),
    )
    return rows[0] if rows else {}


def _revenue_series_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    return db.query(
        conn,
        f"""SELECT date, total_revenue, purchase_revenue, purchases, conversions
            FROM revenue_daily WHERE date IN ({_ph(dates)}) ORDER BY date""",
        tuple(dates),
    )


def _leads_for_dates(conn, dates: list[str]) -> dict:
    if not dates:
        return {}
    rows = db.query(
        conn,
        f"""SELECT SUM(leads) AS leads, SUM(users) AS users
            FROM leads_daily WHERE date IN ({_ph(dates)})""",
        tuple(dates),
    )
    return rows[0] if rows else {}


def _lead_attribution_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    return db.query(
        conn,
        f"""SELECT source, medium, campaign,
                   SUM(leads) AS leads,
                   SUM(users) AS users
            FROM lead_attribution_daily WHERE date IN ({_ph(dates)})
            GROUP BY source, medium, campaign
            ORDER BY leads DESC LIMIT 30""",
        tuple(dates),
    )


def _lead_geo_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    return db.query(
        conn,
        f"""SELECT city, country,
                   SUM(leads) AS leads,
                   SUM(users) AS users
            FROM lead_geo_daily WHERE date IN ({_ph(dates)})
            GROUP BY city, country
            ORDER BY leads DESC LIMIT 30""",
        tuple(dates),
    )


def _lead_devices_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    return db.query(
        conn,
        f"""SELECT device_category, browser,
                   SUM(leads) AS leads,
                   SUM(users) AS users
            FROM lead_devices_daily WHERE date IN ({_ph(dates)})
            GROUP BY device_category, browser
            ORDER BY leads DESC LIMIT 20""",
        tuple(dates),
    )


def _new_vs_returning_for_dates(conn, dates: list[str]) -> list[dict]:
    if not dates:
        return []
    rows = db.query(
        conn,
        f"""SELECT segment,
                   SUM(sessions)                        AS sessions,
                   SUM(users)                           AS users,
                   ROUND(AVG(engagement_rate), 1)       AS engagement_rate,
                   ROUND(AVG(bounce_rate), 1)           AS bounce_rate,
                   ROUND(AVG(avg_duration_secs), 1)     AS avg_duration_secs,
                   ROUND(AVG(pages_per_session), 2)     AS pages_per_session
            FROM new_vs_returning_daily WHERE date IN ({_ph(dates)})
            GROUP BY segment ORDER BY sessions DESC""",
        tuple(dates),
    )
    return [dict(r) for r in rows]


# ── Main analytics endpoint ────────────────────────────────────────────────────

@router.get("/api/analytics")
def get_analytics(
    period:     str           = Query(..., pattern="^(daily|weekly|monthly|custom)$"),
    date:       Optional[str] = Query(None),
    week_start: Optional[str] = Query(None),
    month:      Optional[str] = Query(None),
    start:      Optional[str] = Query(None),
    end:        Optional[str] = Query(None),
    account:    Optional[str] = Query(None),
):
    if period == "daily":
        if not date:
            raise HTTPException(400, "date required for period=daily")
        dates, label, ts_type = [date], date, "hourly"

    elif period == "weekly":
        if not week_start:
            raise HTTPException(400, "week_start required for period=weekly")
        dates, label, ts_type = _week_dates(week_start), f"Week of {week_start}", "daily"

    elif period == "monthly":
        if not month:
            raise HTTPException(400, "month required for period=monthly")
        dates, label, ts_type = _month_dates(month), _month_label(month), "weekly"

    elif period == "custom":
        if not start or not end:
            raise HTTPException(400, "start and end required for period=custom")
        try:
            s, e = date_cls.fromisoformat(start), date_cls.fromisoformat(end)
        except ValueError:
            raise HTTPException(400, "start/end must be YYYY-MM-DD")
        if s > e:
            raise HTTPException(400, "start must be on or before end")
        dates = _date_range(start, end)
        label = f"{start} → {end}" if start != end else start
        ts_type = "hourly" if len(dates) == 1 else "daily" if len(dates) <= 31 else "weekly"

    db_path = _resolve_db(account)

    with db.get_conn(db_path) as conn:
        kpis = _kpis_for_dates(conn, dates)

        if ts_type == "hourly":
            time_series = _time_series_hourly(conn, dates[0])
        elif ts_type == "daily":
            time_series = _time_series_daily(conn, dates)
        else:
            time_series = _time_series_weekly(conn, dates)

        traffic       = _traffic_for_dates(conn, dates)
        pages         = _pages_for_dates(conn, dates)
        device        = _device_for_dates(conn, dates)
        cities        = _cities_for_dates(conn, dates)
        utm           = _utm_for_dates(conn, dates)
        events        = _events_for_dates(conn, dates)
        landing_pages = _landing_pages_for_dates(conn, dates)
        browsers      = _browsers_for_dates(conn, dates)
        countries     = _countries_for_dates(conn, dates)
        referrers         = _referrers_for_dates(conn, dates)
        search_terms      = _search_terms_for_dates(conn, dates)
        new_vs_returning  = _new_vs_returning_for_dates(conn, dates)
        revenue           = _revenue_for_dates(conn, dates)
        revenue_series    = _revenue_series_for_dates(conn, dates)
        leads             = _leads_for_dates(conn, dates)
        lead_attribution  = _lead_attribution_for_dates(conn, dates)
        lead_geo          = _lead_geo_for_dates(conn, dates)
        lead_devices      = _lead_devices_for_dates(conn, dates)

        available       = set(db.get_available_dates(conn))
        dates_with_data = [d for d in dates if d in available]

    return {
        "period":          period,
        "label":           label,
        "dates_in_range":  dates,
        "dates_with_data": dates_with_data,
        "kpis":            kpis,
        "time_series":     time_series,
        "traffic":         traffic,
        "pages":           pages,
        "device":          device,
        "cities":          cities,
        "utm":             utm,
        "events":          events,
        "landing_pages":   landing_pages,
        "browsers":        browsers,
        "countries":       countries,
        "referrers":          referrers,
        "search_terms":       search_terms,
        "new_vs_returning":   new_vs_returning,
        "revenue":            revenue,
        "revenue_series":     revenue_series,
        "leads":              leads,
        "lead_attribution":   lead_attribution,
        "lead_geo":           lead_geo,
        "lead_devices":       lead_devices,
    }


# ── Available dates & fetch status ────────────────────────────────────────────

@router.get("/api/dates/available")
def get_available_dates(account: Optional[str] = Query(None)):
    db_path = _resolve_db(account)
    with db.get_conn(db_path) as conn:
        dates = db.get_available_dates(conn)
    return {"dates": dates}


@router.get("/api/fetch/status")
def get_fetch_status(limit: int = Query(20, ge=1, le=100), account: Optional[str] = Query(None)):
    db_path = _resolve_db(account)
    with db.get_conn(db_path) as conn:
        runs = db.query(conn, "SELECT * FROM fetch_runs ORDER BY id DESC LIMIT ?", (limit,))
    return {"runs": runs}


# ── Fetch trigger / backfill ──────────────────────────────────────────────────

@router.post("/api/fetch/trigger")
def trigger_fetch(
    background_tasks: BackgroundTasks,
    date: str           = Query(..., description="Date to fetch, YYYY-MM-DD"),
    account: Optional[str] = Query(None),
):
    from fetcher import fetch_date
    acc = acm.get_account(account) if account else None
    background_tasks.add_task(fetch_date, date, account=acc)
    return {"message": f"Fetch triggered for {date}", "date": date}


@router.post("/api/fetch/backfill")
def trigger_backfill(
    background_tasks: BackgroundTasks,
    from_date: str      = Query(..., alias="from"),
    to_date:   str      = Query(..., alias="to"),
    account: Optional[str] = Query(None),
):
    from fetcher import fetch_date_range
    acc = acm.get_account(account) if account else None
    background_tasks.add_task(fetch_date_range, from_date, to_date, account=acc)
    return {"message": f"Backfill triggered {from_date} → {to_date}"}


# ── Account management ─────────────────────────────────────────────────────────

class AccountCreateInput(BaseModel):
    name:                  str
    website:               str = ""
    ga4_property_id:       str
    ga4_credentials_path:  str
    slug:                  str = ""


class AccountUpdateInput(BaseModel):
    name:                  Optional[str] = None
    website:               Optional[str] = None
    ga4_property_id:       Optional[str] = None
    ga4_credentials_path:  Optional[str] = None


@router.get("/api/accounts")
def list_accounts():
    return acm.list_accounts()


@router.get("/api/accounts/{slug}")
def get_account(slug: str):
    acc = acm.get_account(slug)
    if not acc:
        raise HTTPException(404, f"Account '{slug}' not found")
    safe = {**acc, "ga4_credentials_path": "***"}
    return safe


@router.post("/api/accounts")
def create_account(data: AccountCreateInput):
    try:
        acc = acm.create_account(data.model_dump(exclude_unset=False))
    except ValueError as e:
        raise HTTPException(400, str(e))
    from database import init_db
    init_db(acc["db_path"])
    return {"message": f"Account '{acc['name']}' created", "account": acc["slug"]}


@router.put("/api/accounts/{slug}")
def update_account(slug: str, data: AccountUpdateInput):
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    try:
        acc = acm.update_account(slug, updates)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"message": f"Account '{slug}' updated", "account": acc["slug"]}


@router.delete("/api/accounts/{slug}")
def delete_account(slug: str):
    try:
        acm.delete_account(slug)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"message": f"Account '{slug}' deleted"}
