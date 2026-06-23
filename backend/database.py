"""
database.py
===========
SQLite schema + connection helper + read/write helpers.

Tables
------
fetch_runs            – audit log for every fetch attempt
daily_kpis            – one row per date, all headline KPIs
hourly_stats          – one row per (date, hour) for daily drill-down
traffic_sources_daily – one row per (date, channel)
top_pages_daily       – one row per (date, page_path)
device_daily          – one row per (date, device_category)
city_stats_daily      – one row per (date, city, country)
utm_daily             – one row per (date, source, medium, campaign)
events_daily          – one row per (date, event_name)
landing_pages_daily   – one row per (date, landing_page)
browsers_daily        – one row per (date, browser)
countries_daily       – one row per (date, country)
referrers_daily       – one row per (date, referrer)
search_terms_daily    – one row per (date, search_term)
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Generator

_DEFAULT_DB = "data/analytics.db"


@contextmanager
def get_conn(db_path: str = _DEFAULT_DB) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS fetch_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL DEFAULT 'running',
    error_msg    TEXT,
    rows_fetched INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_fetch_runs_date ON fetch_runs(date);

-- Headline KPIs per day
CREATE TABLE IF NOT EXISTS daily_kpis (
    date                      TEXT PRIMARY KEY,
    sessions                  INTEGER NOT NULL DEFAULT 0,
    users                     INTEGER NOT NULL DEFAULT 0,
    new_users                 INTEGER NOT NULL DEFAULT 0,
    returning_users           INTEGER NOT NULL DEFAULT 0,
    pageviews                 INTEGER NOT NULL DEFAULT 0,
    pages_per_session         REAL    NOT NULL DEFAULT 0,
    avg_session_duration_secs REAL    NOT NULL DEFAULT 0,
    bounce_rate               REAL    NOT NULL DEFAULT 0,
    engagement_rate           REAL    NOT NULL DEFAULT 0,
    fetched_at                TEXT    NOT NULL
);

-- Hourly breakdown (powers the daily view: hour-by-hour)
CREATE TABLE IF NOT EXISTS hourly_stats (
    date          TEXT    NOT NULL,
    hour          INTEGER NOT NULL,
    sessions      INTEGER NOT NULL DEFAULT 0,
    pageviews     INTEGER NOT NULL DEFAULT 0,
    active_users  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, hour)
);

-- Traffic channel split per day
CREATE TABLE IF NOT EXISTS traffic_sources_daily (
    date       TEXT    NOT NULL,
    channel    TEXT    NOT NULL,
    sessions   INTEGER NOT NULL DEFAULT 0,
    users      INTEGER NOT NULL DEFAULT 0,
    new_users  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, channel)
);

-- Top pages per day
CREATE TABLE IF NOT EXISTS top_pages_daily (
    date                     TEXT    NOT NULL,
    page_path                TEXT    NOT NULL,
    page_title               TEXT,
    views                    INTEGER NOT NULL DEFAULT 0,
    sessions                 INTEGER NOT NULL DEFAULT 0,
    avg_engagement_time_secs REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (date, page_path)
);

-- Device split per day
CREATE TABLE IF NOT EXISTS device_daily (
    date             TEXT    NOT NULL,
    device_category  TEXT    NOT NULL,
    sessions         INTEGER NOT NULL DEFAULT 0,
    users            INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, device_category)
);

-- City stats per day
CREATE TABLE IF NOT EXISTS city_stats_daily (
    date     TEXT    NOT NULL,
    city     TEXT    NOT NULL,
    country  TEXT    NOT NULL DEFAULT '',
    sessions INTEGER NOT NULL DEFAULT 0,
    users    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, city, country)
);

-- UTM campaign breakdown per day
CREATE TABLE IF NOT EXISTS utm_daily (
    date          TEXT    NOT NULL,
    utm_source    TEXT    NOT NULL DEFAULT '',
    utm_medium    TEXT    NOT NULL DEFAULT '',
    utm_campaign  TEXT    NOT NULL DEFAULT '',
    sessions      INTEGER NOT NULL DEFAULT 0,
    users         INTEGER NOT NULL DEFAULT 0,
    new_users     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, utm_source, utm_medium, utm_campaign)
);

-- All GA4 events per day (critical for discovering custom tracking)
CREATE TABLE IF NOT EXISTS events_daily (
    date         TEXT    NOT NULL,
    event_name   TEXT    NOT NULL,
    event_count  INTEGER NOT NULL DEFAULT 0,
    unique_users INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, event_name)
);

-- Landing pages (first page of a session) per day
CREATE TABLE IF NOT EXISTS landing_pages_daily (
    date             TEXT    NOT NULL,
    landing_page     TEXT    NOT NULL,
    sessions         INTEGER NOT NULL DEFAULT 0,
    users            INTEGER NOT NULL DEFAULT 0,
    new_users        INTEGER NOT NULL DEFAULT 0,
    bounce_rate      REAL    NOT NULL DEFAULT 0,
    engagement_rate  REAL    NOT NULL DEFAULT 0,
    avg_duration_secs REAL   NOT NULL DEFAULT 0,
    PRIMARY KEY (date, landing_page)
);

-- Browser breakdown per day
CREATE TABLE IF NOT EXISTS browsers_daily (
    date     TEXT    NOT NULL,
    browser  TEXT    NOT NULL,
    sessions INTEGER NOT NULL DEFAULT 0,
    users    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, browser)
);

-- Country breakdown per day (distinct from city_stats_daily)
CREATE TABLE IF NOT EXISTS countries_daily (
    date     TEXT    NOT NULL,
    country  TEXT    NOT NULL,
    sessions INTEGER NOT NULL DEFAULT 0,
    users    INTEGER NOT NULL DEFAULT 0,
    new_users INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, country)
);

-- External referrers per day
CREATE TABLE IF NOT EXISTS referrers_daily (
    date     TEXT    NOT NULL,
    referrer TEXT    NOT NULL,
    sessions INTEGER NOT NULL DEFAULT 0,
    users    INTEGER NOT NULL DEFAULT 0,
    new_users INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, referrer)
);

-- Site search terms per day (requires site search tracking in GA4)
CREATE TABLE IF NOT EXISTS search_terms_daily (
    date        TEXT    NOT NULL,
    search_term TEXT    NOT NULL,
    sessions    INTEGER NOT NULL DEFAULT 0,
    users       INTEGER NOT NULL DEFAULT 0,
    pageviews   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, search_term)
);

-- Ecommerce revenue and GA4 conversions per day
CREATE TABLE IF NOT EXISTS revenue_daily (
    date             TEXT    PRIMARY KEY,
    total_revenue    REAL    NOT NULL DEFAULT 0,
    purchase_revenue REAL    NOT NULL DEFAULT 0,
    purchases        INTEGER NOT NULL DEFAULT 0,
    transactions     INTEGER NOT NULL DEFAULT 0,
    conversions      INTEGER NOT NULL DEFAULT 0
);

-- generate_lead conversion summary per day
CREATE TABLE IF NOT EXISTS leads_daily (
    date  TEXT PRIMARY KEY,
    leads INTEGER NOT NULL DEFAULT 0,
    users INTEGER NOT NULL DEFAULT 0
);

-- generate_lead attribution: source / medium / campaign per day
CREATE TABLE IF NOT EXISTS lead_attribution_daily (
    date     TEXT NOT NULL,
    source   TEXT NOT NULL DEFAULT '',
    medium   TEXT NOT NULL DEFAULT '',
    campaign TEXT NOT NULL DEFAULT '',
    leads    INTEGER NOT NULL DEFAULT 0,
    users    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, source, medium, campaign)
);

-- generate_lead geography: city / country per day
CREATE TABLE IF NOT EXISTS lead_geo_daily (
    date    TEXT NOT NULL,
    city    TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    leads   INTEGER NOT NULL DEFAULT 0,
    users   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, city, country)
);

-- generate_lead device / browser per day
CREATE TABLE IF NOT EXISTS lead_devices_daily (
    date            TEXT NOT NULL,
    device_category TEXT NOT NULL DEFAULT '',
    browser         TEXT NOT NULL DEFAULT '',
    leads           INTEGER NOT NULL DEFAULT 0,
    users           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, device_category, browser)
);

-- New vs returning visitor comparison per day
CREATE TABLE IF NOT EXISTS new_vs_returning_daily (
    date              TEXT    NOT NULL,
    segment           TEXT    NOT NULL,
    sessions          INTEGER NOT NULL DEFAULT 0,
    users             INTEGER NOT NULL DEFAULT 0,
    engagement_rate   REAL    NOT NULL DEFAULT 0,
    bounce_rate       REAL    NOT NULL DEFAULT 0,
    avg_duration_secs REAL    NOT NULL DEFAULT 0,
    pages_per_session REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (date, segment)
);
"""


def init_db(db_path: str = _DEFAULT_DB) -> None:
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)


# ── Write helpers ──────────────────────────────────────────────────────────────

def upsert(conn: sqlite3.Connection, table: str, data: dict[str, Any]) -> None:
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" * len(data))
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})",
        list(data.values()),
    )


def upsert_many(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    cols = ", ".join(rows[0].keys())
    placeholders = ", ".join("?" * len(rows[0]))
    conn.executemany(
        f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})",
        [list(r.values()) for r in rows],
    )


def delete_date(conn: sqlite3.Connection, date: str) -> None:
    tables = [
        "hourly_stats", "traffic_sources_daily", "top_pages_daily",
        "device_daily", "city_stats_daily", "utm_daily",
        "events_daily", "landing_pages_daily", "browsers_daily",
        "countries_daily", "referrers_daily", "search_terms_daily",
        "new_vs_returning_daily",
        "revenue_daily",
        "leads_daily", "lead_attribution_daily", "lead_geo_daily", "lead_devices_daily",
    ]
    for t in tables:
        conn.execute(f"DELETE FROM {t} WHERE date = ?", (date,))


# ── Read helpers ───────────────────────────────────────────────────────────────

def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return rows_to_dicts(conn.execute(sql, params).fetchall())


def query_one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def get_available_dates(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT date FROM daily_kpis ORDER BY date DESC"
    ).fetchall()
    return [r["date"] for r in rows]


def log_fetch_start(conn: sqlite3.Connection, date: str, started_at: str) -> int:
    cur = conn.execute(
        "INSERT INTO fetch_runs (date, started_at, status) VALUES (?, ?, 'running')",
        (date, started_at),
    )
    return cur.lastrowid


def log_fetch_end(
    conn: sqlite3.Connection,
    run_id: int,
    finished_at: str,
    status: str,
    error_msg: str | None,
    rows_fetched: int,
) -> None:
    conn.execute(
        """UPDATE fetch_runs
           SET finished_at=?, status=?, error_msg=?, rows_fetched=?
           WHERE id=?""",
        (finished_at, status, error_msg, rows_fetched, run_id),
    )
