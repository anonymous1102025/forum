"""
fetcher.py
==========
Orchestrates a full GA4 data fetch for one date.

fetch_date(date_str, account)
  1. Calls all GA4 queries via ga4_client
  2. Transforms / normalises raw results
  3. Clears any existing rows for that date (idempotent)
  4. Writes everything to SQLite
  5. Updates the fetch_runs audit log

All expensive aggregations happen here so the API layer just reads
pre-computed values from SQLite.
"""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any

import ga4_client as ga4
import database as db
from ga4_client import set_credentials


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_date(date_str: str, account: dict | None = None) -> dict[str, Any]:
    """
    Full fetch + transform + store for a single date.
    Returns a summary dict with row counts and status.
    """
    db_path = account["db_path"] if account else db._DEFAULT_DB
    creds = ga4.get_credentials(account) if account else {}

    started_at = _now_utc()
    with db.get_conn(db_path) as conn:
        run_id = db.log_fetch_start(conn, date_str, started_at)

    total_rows = 0
    error_msg: str | None = None

    try:
        ctx = set_credentials(creds) if creds else nullcontext()
        with ctx:
            print(f"[fetcher] Fetching {date_str} …")

            # ── Fetch ──────────────────────────────────────────────────────────
            daily         = ga4.fetch_daily_totals(date_str, date_str)
            hourly        = ga4.fetch_hourly_stats(date_str, date_str)
            traffic       = ga4.fetch_traffic_sources(date_str, date_str)
            pages         = ga4.fetch_top_pages(date_str, date_str)
            device        = ga4.fetch_device_split(date_str, date_str)
            cities        = ga4.fetch_city_stats(date_str, date_str)
            utm           = ga4.fetch_utm_breakdown(date_str, date_str)
            events        = ga4.fetch_events(date_str, date_str)
            landing_pages = ga4.fetch_landing_pages(date_str, date_str)
            browsers      = ga4.fetch_browsers(date_str, date_str)
            countries     = ga4.fetch_countries(date_str, date_str)
            referrers     = ga4.fetch_referrers(date_str, date_str)
            search_terms      = ga4.fetch_search_terms(date_str, date_str)
            new_vs_returning  = ga4.fetch_new_vs_returning(date_str, date_str)
            revenue           = ga4.fetch_revenue(date_str, date_str)
            lead_summary      = ga4.fetch_lead_summary(date_str, date_str)
            lead_attribution  = ga4.fetch_lead_attribution(date_str, date_str)
            lead_geo          = ga4.fetch_lead_geo(date_str, date_str)
            lead_devices      = ga4.fetch_lead_devices(date_str, date_str)

            print(f"[fetcher] Fetched — {len(pages)} pages, {len(events)} events, {len(countries)} countries")

            # ── Transform ─────────────────────────────────────────────────────

            # daily_kpis: should be exactly one row for the date
            kpi_row = next((r for r in daily if r.get("date") == date_str), None)
            if not kpi_row:
                # GA4 returns date as YYYYMMDD — normalise both formats
                kpi_row = next((r for r in daily), None)

            if kpi_row:
                kpi_row = {
                    "date":                       date_str,
                    "sessions":                   kpi_row.get("sessions", 0),
                    "users":                      kpi_row.get("users", 0),
                    "new_users":                  kpi_row.get("new_users", 0),
                    "returning_users":            kpi_row.get("returning_users", 0),
                    "pageviews":                  kpi_row.get("pageviews", 0),
                    "pages_per_session":          kpi_row.get("pages_per_session", 0.0),
                    "avg_session_duration_secs":  kpi_row.get("avg_session_duration_secs", 0.0),
                    "bounce_rate":                kpi_row.get("bounce_rate", 0.0),
                    "engagement_rate":            kpi_row.get("engagement_rate", 0.0),
                    "fetched_at":                 started_at,
                }
            else:
                # No data for this date (e.g. site had no traffic)
                kpi_row = {
                    "date": date_str,
                    "sessions": 0, "users": 0, "new_users": 0, "returning_users": 0,
                    "pageviews": 0, "pages_per_session": 0.0,
                    "avg_session_duration_secs": 0.0,
                    "bounce_rate": 0.0, "engagement_rate": 0.0,
                    "fetched_at": started_at,
                }

            # Hourly stats: ensure all 24 hours represented and date is correct
            hourly_map = {r["hour"]: r for r in hourly}
            hourly_rows = [
                {
                    "date":         date_str,
                    "hour":         h,
                    "sessions":     hourly_map.get(h, {}).get("sessions", 0),
                    "pageviews":    hourly_map.get(h, {}).get("pageviews", 0),
                    "active_users": hourly_map.get(h, {}).get("active_users", 0),
                }
                for h in range(24)
            ]

            # Normalise date field on all sub-tables
            def _fix_date(rows: list[dict]) -> list[dict]:
                return [{**r, "date": date_str} for r in rows]

            traffic_rows       = _fix_date(traffic)
            page_rows          = _fix_date(pages)
            device_rows        = _fix_date(device)
            city_rows          = _fix_date(cities)
            utm_rows           = _fix_date(utm)
            event_rows         = _fix_date(events)
            landing_page_rows  = _fix_date(landing_pages)
            browser_rows       = _fix_date(browsers)
            country_rows       = _fix_date(countries)
            referrer_rows          = _fix_date(referrers)
            search_term_rows       = _fix_date(search_terms)
            new_vs_returning_rows  = _fix_date(new_vs_returning)
            revenue_rows           = _fix_date(revenue)
            lead_summary_rows      = _fix_date(lead_summary)
            lead_attribution_rows  = _fix_date(lead_attribution)
            lead_geo_rows          = _fix_date(lead_geo)
            lead_device_rows       = _fix_date(lead_devices)

            # ── Write to DB ───────────────────────────────────────────────────
            with db.get_conn(db_path) as conn:
                db.delete_date(conn, date_str)

                db.upsert(conn, "daily_kpis", kpi_row)
                db.upsert_many(conn, "hourly_stats", hourly_rows)
                db.upsert_many(conn, "traffic_sources_daily", traffic_rows)
                db.upsert_many(conn, "top_pages_daily", page_rows)
                db.upsert_many(conn, "device_daily", device_rows)
                db.upsert_many(conn, "city_stats_daily", city_rows)
                db.upsert_many(conn, "utm_daily", utm_rows)
                db.upsert_many(conn, "events_daily", event_rows)
                db.upsert_many(conn, "landing_pages_daily", landing_page_rows)
                db.upsert_many(conn, "browsers_daily", browser_rows)
                db.upsert_many(conn, "countries_daily", country_rows)
                db.upsert_many(conn, "referrers_daily", referrer_rows)
                db.upsert_many(conn, "search_terms_daily", search_term_rows)
                db.upsert_many(conn, "new_vs_returning_daily", new_vs_returning_rows)
                db.upsert_many(conn, "revenue_daily", revenue_rows)
                db.upsert_many(conn, "leads_daily", lead_summary_rows)
                db.upsert_many(conn, "lead_attribution_daily", lead_attribution_rows)
                db.upsert_many(conn, "lead_geo_daily", lead_geo_rows)
                db.upsert_many(conn, "lead_devices_daily", lead_device_rows)

            total_rows = (
                1 + len(hourly_rows) + len(traffic_rows) +
                len(page_rows) + len(device_rows) + len(city_rows) +
                len(utm_rows) + len(event_rows) + len(landing_page_rows) +
                len(browser_rows) + len(country_rows) + len(referrer_rows) +
                len(search_term_rows) + len(new_vs_returning_rows) +
                len(revenue_rows) + len(lead_summary_rows) +
                len(lead_attribution_rows) + len(lead_geo_rows) + len(lead_device_rows)
            )

    except Exception as exc:
        import traceback
        traceback.print_exc()
        error_msg = str(exc)
        print(f"[fetcher] ERROR for {date_str}: {exc}")

    finally:
        finished_at = _now_utc()
        status = "error" if error_msg else "ok"
        with db.get_conn(db_path) as conn:
            db.log_fetch_end(conn, run_id, finished_at, status, error_msg, total_rows)

    return {
        "date":       date_str,
        "status":     status,
        "rows":       total_rows,
        "started_at": started_at,
        "error":      error_msg,
    }


def fetch_date_range(date_from: str, date_to: str, account: dict | None = None) -> list[dict[str, Any]]:
    """Backfill: fetch every date in [date_from, date_to] inclusive."""
    from datetime import date, timedelta

    start = date.fromisoformat(date_from)
    end   = date.fromisoformat(date_to)

    results = []
    current = start
    while current <= end:
        result = fetch_date(str(current), account=account)
        results.append(result)
        current += timedelta(days=1)
    return results
