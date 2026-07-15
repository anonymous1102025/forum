"""
bigquery_client.py
===================
On-demand queries against the GA4 BigQuery Export dataset, used for
individual user-journey lookups that the aggregate GA4 Data API (ga4_client.py)
cannot provide — GA4's RunReport endpoint only returns pre-aggregated rows,
never per-user event sequences.

Design notes
------------
* This data is NOT pre-fetched into SQLite like the rest of the app (see
  fetcher.py). User-journey lookups are long-tail — thousands of possible
  user_pseudo_ids — and BigQuery bills per byte scanned, so caching every
  raw event daily would be expensive and mostly wasted. Queries here run
  live, scoped to a bounded date range, and always filter on
  _TABLE_SUFFIX so BigQuery only scans the daily-sharded tables in range.
* GA4's BigQuery Export schema (event_date, event_timestamp, event_name,
  event_params, user_pseudo_id, traffic_source, device, geo, ...) is a
  fixed format defined by Google:
  https://support.google.com/analytics/answer/7029846
* Credentials reuse the account's existing service account key
  (ga4_credentials_path) but request BigQuery scopes instead of the GA4
  Data API scope. The service account needs, on the destination project:
    roles/bigquery.dataViewer  (on the analytics_<property_id> dataset)
    roles/bigquery.jobUser     (on the project, to run query jobs)
* Each account needs two extra fields in accounts.json to use this:
    bigquery_project   – GCP project the GA4 BigQuery Export writes to
                          (find it in GA4 Admin -> Product Links -> BigQuery Links)
    bigquery_dataset   – optional, defaults to analytics_<ga4_property_id>
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from google.cloud import bigquery
from google.oauth2 import service_account

MAX_DATE_RANGE_DAYS = 90
DEFAULT_CONVERSION_EVENTS = ("generate_lead", "order_confirmation")

_IDENT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

# event_params extraction: GA4 export stores params as a REPEATED RECORD
# (key STRING, value RECORD{string_value,int_value,float_value,double_value}).
# Each param name has one populated value column — map it here.
_PARAM_VALUE_FIELD = {
    "page_location": "string_value",
    "page_title":    "string_value",
    "ga_session_id": "int_value",
}


class BigQueryNotConfigured(Exception):
    pass


def _validate_ident(value: str | None, label: str) -> str:
    if not value or not _IDENT_RE.match(value):
        raise BigQueryNotConfigured(
            f"Account is missing a valid '{label}' — set it in accounts.json. "
            f"Find the destination project in GA4 Admin -> Product Links -> BigQuery Links."
        )
    return value


def _client(account: dict) -> bigquery.Client:
    project = _validate_ident(account.get("bigquery_project"), "bigquery_project")
    creds_path = account.get("ga4_credentials_path")
    if not creds_path:
        raise BigQueryNotConfigured("Account is missing ga4_credentials_path")
    creds = service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
    )
    return bigquery.Client(project=project, credentials=creds)


def _table_ref(account: dict) -> str:
    project = _validate_ident(account.get("bigquery_project"), "bigquery_project")
    dataset = account.get("bigquery_dataset") or f"analytics_{account.get('ga4_property_id', '')}"
    dataset = _validate_ident(dataset, "bigquery_dataset")
    return f"`{project}.{dataset}.events_*`"


def _suffix(date_str: str) -> str:
    return date_str.replace("-", "")


def _check_range(date_from: str, date_to: str) -> None:
    try:
        d1 = datetime.strptime(date_from, "%Y-%m-%d")
        d2 = datetime.strptime(date_to, "%Y-%m-%d")
    except ValueError:
        raise ValueError("date_from/date_to must be YYYY-MM-DD")
    if d2 < d1:
        raise ValueError("date_to must be on or after date_from")
    if (d2 - d1).days > MAX_DATE_RANGE_DAYS:
        raise ValueError(f"Range too large for a live BigQuery scan (max {MAX_DATE_RANGE_DAYS} days)")


def _param(name: str, alias: str | None = None) -> str:
    field = _PARAM_VALUE_FIELD[name]
    return f"(SELECT value.{field} FROM UNNEST(event_params) WHERE key = '{name}') AS {alias or name}"


def fetch_converters(
    account: dict,
    date_from: str,
    date_to: str,
    event_names: tuple[str, ...] = DEFAULT_CONVERSION_EVENTS,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Users who fired a conversion event in [date_from, date_to], with their
    acquisition source and time-from-first-seen-to-conversion.

    Note: first_seen_at / sessions_in_window are bounded by the query
    window — a user first seen before date_from will show a first_seen_at
    of their first *in-window* event, not their true lifetime first visit.
    """
    _check_range(date_from, date_to)
    table = _table_ref(account)
    client = _client(account)

    sql = f"""
    WITH conv_events AS (
      SELECT
        user_pseudo_id,
        event_name AS conversion_event,
        TIMESTAMP_MICROS(event_timestamp) AS converted_at,
        {_param('page_location', 'conversion_page')},
        traffic_source.source AS acq_source,
        traffic_source.medium AS acq_medium,
        traffic_source.name   AS acq_campaign,
        device.category        AS device_category,
        geo.country              AS country,
        geo.city                  AS city,
        ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY event_timestamp) AS rn
      FROM {table}
      WHERE _TABLE_SUFFIX BETWEEN @suffix_from AND @suffix_to
        AND event_name IN UNNEST(@event_names)
    ),
    activity AS (
      SELECT
        user_pseudo_id,
        MIN(TIMESTAMP_MICROS(event_timestamp)) AS first_seen_at,
        COUNTIF(event_name = 'session_start') AS sessions_in_window
      FROM {table}
      WHERE _TABLE_SUFFIX BETWEEN @suffix_from AND @suffix_to
      GROUP BY user_pseudo_id
    )
    SELECT
      c.user_pseudo_id, c.conversion_event, c.converted_at, c.conversion_page,
      c.acq_source, c.acq_medium, c.acq_campaign, c.device_category, c.country, c.city,
      a.first_seen_at, a.sessions_in_window,
      TIMESTAMP_DIFF(c.converted_at, a.first_seen_at, HOUR) AS hours_to_convert
    FROM conv_events c
    JOIN activity a USING (user_pseudo_id)
    WHERE c.rn = 1
    ORDER BY c.converted_at DESC
    LIMIT @limit
    """

    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("suffix_from", "STRING", _suffix(date_from)),
        bigquery.ScalarQueryParameter("suffix_to",   "STRING", _suffix(date_to)),
        bigquery.ArrayQueryParameter("event_names",  "STRING", list(event_names)),
        bigquery.ScalarQueryParameter("limit",       "INT64",  limit),
    ])
    rows = client.query(sql, job_config=job_config).result()
    return [
        {
            "user_pseudo_id":     r.user_pseudo_id,
            "conversion_event":   r.conversion_event,
            "converted_at":       r.converted_at.isoformat() if r.converted_at else None,
            "conversion_page":    r.conversion_page,
            "source":             r.acq_source or "(direct)",
            "medium":             r.acq_medium or "(none)",
            "campaign":           r.acq_campaign or "(not set)",
            "device_category":    r.device_category,
            "country":            r.country,
            "city":               r.city,
            "first_seen_at":      r.first_seen_at.isoformat() if r.first_seen_at else None,
            "sessions_in_window": r.sessions_in_window,
            "hours_to_convert":   r.hours_to_convert,
        }
        for r in rows
    ]


def fetch_user_journey(
    account: dict,
    user_pseudo_id: str,
    date_from: str,
    date_to: str,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """Full ordered event timeline for one anonymous GA4 user (user_pseudo_id)."""
    _check_range(date_from, date_to)
    table = _table_ref(account)
    client = _client(account)

    sql = f"""
    SELECT
      TIMESTAMP_MICROS(event_timestamp) AS event_time,
      event_name,
      {_param('ga_session_id', 'session_id')},
      {_param('page_location')},
      {_param('page_title')},
      traffic_source.source AS acq_source,
      traffic_source.medium AS acq_medium,
      device.category        AS device_category,
      geo.city                AS city,
      geo.country              AS country
    FROM {table}
    WHERE _TABLE_SUFFIX BETWEEN @suffix_from AND @suffix_to
      AND user_pseudo_id = @user_pseudo_id
    ORDER BY event_timestamp
    LIMIT @limit
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("suffix_from", "STRING", _suffix(date_from)),
        bigquery.ScalarQueryParameter("suffix_to",   "STRING", _suffix(date_to)),
        bigquery.ScalarQueryParameter("user_pseudo_id", "STRING", user_pseudo_id),
        bigquery.ScalarQueryParameter("limit", "INT64", limit),
    ])
    rows = client.query(sql, job_config=job_config).result()
    return [
        {
            "event_time":      r.event_time.isoformat() if r.event_time else None,
            "event_name":      r.event_name,
            "session_id":      r.session_id,
            "page_location":   r.page_location,
            "page_title":      r.page_title,
            "source":          r.acq_source,
            "medium":          r.acq_medium,
            "device_category": r.device_category,
            "city":            r.city,
            "country":         r.country,
        }
        for r in rows
    ]
