"""
ga4_client.py
=============
All Google Analytics 4 Data API queries.

Key design decisions
--------------------
* Thread-local credentials via set_credentials() context manager — same
  pattern as the PostHog client, allowing multi-account support.
* One function per data type; each returns plain Python dicts.
* Single-day date ranges: pass date_from == date_to for daily fetches.
* Traffic sources use GA4's sessionDefaultChannelGroup dimension — returns
  clean buckets (Organic Search, Direct, Referral, Organic Social, etc.)
  with no manual CASE WHEN needed.
* UTM breakdown filtered to rows where at least one UTM param is set.
* Bot/spam filtered: GA4 automatically excludes known bots from all reports.
  We additionally normalise "(not set)" dimension values to "Unknown".
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from typing import Any

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Filter,
    FilterExpression,
    GetMetadataRequest,
    Metric,
    OrderBy,
    RunReportRequest,
)
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as OAuthCredentials


# ── Thread-local credentials ───────────────────────────────────────────────────

_local = threading.local()


@contextmanager
def set_credentials(creds: dict[str, str]):
    prev = getattr(_local, "creds", None)
    _local.creds = creds
    try:
        yield
    finally:
        _local.creds = prev


def _get_creds() -> dict[str, str]:
    return getattr(_local, "creds", None) or {}


# ── GA4 client factory ─────────────────────────────────────────────────────────

def _client_and_property() -> tuple[BetaAnalyticsDataClient, str]:
    creds = _get_creds()
    property_id      = creds.get("property_id", "")
    credentials_path = creds.get("credentials_path", "")

    if credentials_path:
        with open(credentials_path) as f:
            key_data = json.load(f)

        if key_data.get("type") == "service_account":
            ga4_creds = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/analytics.readonly"],
            )
        else:
            # OAuth user token saved by auth_setup.py
            ga4_creds = OAuthCredentials.from_authorized_user_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/analytics.readonly"],
            )
            if ga4_creds.expired and ga4_creds.refresh_token:
                ga4_creds.refresh(Request())

        return BetaAnalyticsDataClient(credentials=ga4_creds), property_id

    # Fallback: use GOOGLE_APPLICATION_CREDENTIALS env var
    return BetaAnalyticsDataClient(), property_id


# ── Low-level report runner ────────────────────────────────────────────────────

def _run_report(
    dimensions: list[str],
    metrics: list[str],
    date_from: str,
    date_to: str,
    dimension_filter: FilterExpression | None = None,
    order_bys: list[OrderBy] | None = None,
    limit: int = 10_000,
) -> list[dict[str, Any]]:
    """
    Execute a GA4 RunReport and return rows as list[dict].
    Retries on quota errors (429) with exponential back-off.
    """
    client, property_id = _client_and_property()
    if not property_id:
        raise RuntimeError("GA4 property_id not set — check your account credentials")

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=date_from, end_date=date_to)],
        limit=limit,
    )
    if dimension_filter:
        request.dimension_filter = dimension_filter
    if order_bys:
        request.order_bys = order_bys

    for attempt in range(3):
        try:
            response = client.run_report(request)
            break
        except Exception as e:
            if "quota" in str(e).lower() or "429" in str(e):
                time.sleep(30 * (attempt + 1))
                if attempt == 2:
                    raise
            else:
                raise

    dim_names = [h.name for h in response.dimension_headers]
    met_names = [h.name for h in response.metric_headers]

    rows = []
    for row in response.rows:
        r: dict[str, Any] = {}
        for i, dv in enumerate(row.dimension_values):
            r[dim_names[i]] = dv.value if dv.value != "(not set)" else "Unknown"
        for i, mv in enumerate(row.metric_values):
            r[met_names[i]] = mv.value
        rows.append(r)

    return rows


# ── Type coercions ─────────────────────────────────────────────────────────────

def _int(v: Any) -> int:
    try:
        return int(float(str(v)))
    except (TypeError, ValueError):
        return 0


def _float(v: Any) -> float:
    try:
        return float(str(v))
    except (TypeError, ValueError):
        return 0.0


def _event_filter(event_name: str) -> FilterExpression:
    """Build a dimension filter that restricts a report to a single eventName."""
    return FilterExpression(
        filter=Filter(
            field_name="eventName",
            string_filter=Filter.StringFilter(
                value=event_name,
                match_type=Filter.StringFilter.MatchType.EXACT,
            ),
        )
    )


# ── 1. DAILY TOTALS ───────────────────────────────────────────────────────────

def fetch_daily_totals(date_from: str, date_to: str) -> list[dict]:
    """
    Core daily KPIs: sessions, users, new/returning, pageviews,
    avg session duration, bounce rate, engagement rate.
    Returns one row per day in the range.
    """
    rows = _run_report(
        dimensions=["date"],
        metrics=[
            "sessions",
            "totalUsers",
            "newUsers",
            "screenPageViews",
            "averageSessionDuration",
            "bounceRate",
            "engagementRate",
        ],
        date_from=date_from,
        date_to=date_to,
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
    )
    out = []
    for r in rows:
        sessions = _int(r.get("sessions", 0))
        users    = _int(r.get("totalUsers", 0))
        new_u    = _int(r.get("newUsers", 0))
        pv       = _int(r.get("screenPageViews", 0))
        out.append({
            "date":                       r["date"],
            "sessions":                   sessions,
            "users":                      users,
            "new_users":                  new_u,
            "returning_users":            max(users - new_u, 0),
            "pageviews":                  pv,
            "pages_per_session":          round(pv / sessions, 2) if sessions else 0.0,
            "avg_session_duration_secs":  round(_float(r.get("averageSessionDuration", 0)), 1),
            "bounce_rate":                round(_float(r.get("bounceRate", 0)) * 100, 1),
            "engagement_rate":            round(_float(r.get("engagementRate", 0)) * 100, 1),
        })
    return out


# ── 2. HOURLY STATS ───────────────────────────────────────────────────────────

def fetch_hourly_stats(date_from: str, date_to: str) -> list[dict]:
    """
    Sessions, pageviews, active users broken out by date + hour (0-23).
    For single-day fetches (date_from == date_to) this gives the hour-by-hour view.
    """
    rows = _run_report(
        dimensions=["date", "hour"],
        metrics=["sessions", "screenPageViews", "activeUsers"],
        date_from=date_from,
        date_to=date_to,
        order_bys=[
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="hour")),
        ],
    )
    return [
        {
            "date":         r["date"],
            "hour":         _int(r.get("hour", 0)),
            "sessions":     _int(r.get("sessions", 0)),
            "pageviews":    _int(r.get("screenPageViews", 0)),
            "active_users": _int(r.get("activeUsers", 0)),
        }
        for r in rows
    ]


# ── 3. TRAFFIC SOURCES ────────────────────────────────────────────────────────

def fetch_traffic_sources(date_from: str, date_to: str) -> list[dict]:
    """
    Sessions and users broken out by GA4's sessionDefaultChannelGroup.
    Returns clean buckets: Organic Search, Direct, Referral,
    Organic Social, Paid Search, Paid Social, Email, Display, etc.
    GA4 handles the classification — no manual CASE WHEN needed.
    """
    rows = _run_report(
        dimensions=["date", "sessionDefaultChannelGroup"],
        metrics=["sessions", "totalUsers", "newUsers"],
        date_from=date_from,
        date_to=date_to,
        order_bys=[
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True),
        ],
    )
    return [
        {
            "date":      r["date"],
            "channel":   r.get("sessionDefaultChannelGroup") or "Unknown",
            "sessions":  _int(r.get("sessions", 0)),
            "users":     _int(r.get("totalUsers", 0)),
            "new_users": _int(r.get("newUsers", 0)),
        }
        for r in rows
    ]


# ── 4. TOP PAGES ──────────────────────────────────────────────────────────────

def fetch_top_pages(date_from: str, date_to: str, limit: int = 50) -> list[dict]:
    """
    Top pages by views, with avg engagement time.
    pagePath + pageTitle so we can show both slug and human title.
    """
    rows = _run_report(
        dimensions=["date", "pagePath", "pageTitle"],
        metrics=["screenPageViews", "sessions", "averageSessionDuration"],
        date_from=date_from,
        date_to=date_to,
        order_bys=[
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True),
        ],
        limit=limit,
    )
    return [
        {
            "date":                     r["date"],
            "page_path":                r.get("pagePath") or "/",
            "page_title":               r.get("pageTitle") or "",
            "views":                    _int(r.get("screenPageViews", 0)),
            "sessions":                 _int(r.get("sessions", 0)),
            "avg_engagement_time_secs": round(_float(r.get("averageSessionDuration", 0)), 1),
        }
        for r in rows
    ]


# ── 5. DEVICE SPLIT ───────────────────────────────────────────────────────────

def fetch_device_split(date_from: str, date_to: str) -> list[dict]:
    """Sessions and users by device category: mobile, desktop, tablet."""
    rows = _run_report(
        dimensions=["date", "deviceCategory"],
        metrics=["sessions", "totalUsers"],
        date_from=date_from,
        date_to=date_to,
        order_bys=[
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True),
        ],
    )
    return [
        {
            "date":            r["date"],
            "device_category": r.get("deviceCategory") or "Unknown",
            "sessions":        _int(r.get("sessions", 0)),
            "users":           _int(r.get("totalUsers", 0)),
        }
        for r in rows
    ]


# ── 6. CITY STATS ─────────────────────────────────────────────────────────────

def fetch_city_stats(date_from: str, date_to: str) -> list[dict]:
    """Top cities by sessions, with country for disambiguation."""
    rows = _run_report(
        dimensions=["date", "city", "country"],
        metrics=["sessions", "totalUsers"],
        date_from=date_from,
        date_to=date_to,
        order_bys=[
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True),
        ],
        limit=200,
    )
    return [
        {
            "date":     r["date"],
            "city":     r.get("city") or "Unknown",
            "country":  r.get("country") or "Unknown",
            "sessions": _int(r.get("sessions", 0)),
            "users":    _int(r.get("totalUsers", 0)),
        }
        for r in rows
        if r.get("city") and r["city"] != "Unknown"
    ]


# ── 7. UTM BREAKDOWN ─────────────────────────────────────────────────────────

def fetch_utm_breakdown(date_from: str, date_to: str) -> list[dict]:
    """
    Sessions broken out by UTM source / medium / campaign.
    Filtered to rows where sessionSource is not '(direct)' or 'google'
    without a medium — i.e. only rows that came from tagged links.
    """
    rows = _run_report(
        dimensions=["date", "sessionSource", "sessionMedium", "sessionCampaignName"],
        metrics=["sessions", "totalUsers", "newUsers"],
        date_from=date_from,
        date_to=date_to,
        order_bys=[
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True),
        ],
        limit=5_000,
    )

    out = []
    for r in rows:
        source   = r.get("sessionSource", "") or ""
        medium   = r.get("sessionMedium", "") or ""
        campaign = r.get("sessionCampaignName", "") or ""

        # Skip rows with no meaningful attribution info
        if source in ("(direct)", "Unknown", "") and medium in ("(none)", "Unknown", ""):
            continue

        out.append({
            "date":         r["date"],
            "utm_source":   source,
            "utm_medium":   medium,
            "utm_campaign": campaign,
            "sessions":     _int(r.get("sessions", 0)),
            "users":        _int(r.get("totalUsers", 0)),
            "new_users":    _int(r.get("newUsers", 0)),
        })

    return out


# ── 8. EVENTS ─────────────────────────────────────────────────────────────────

def fetch_events(date_from: str, date_to: str) -> list[dict]:
    """
    All event names with counts for the date range.
    Critical for forums: discovers custom tracking (comment_post, sign_up, etc.)
    """
    rows = _run_report(
        dimensions=["date", "eventName"],
        metrics=["eventCount", "totalUsers"],
        date_from=date_from,
        date_to=date_to,
        order_bys=[
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name="eventCount"), desc=True),
        ],
        limit=1_000,
    )
    return [
        {
            "date":         r["date"],
            "event_name":   r.get("eventName") or "Unknown",
            "event_count":  _int(r.get("eventCount", 0)),
            "unique_users": _int(r.get("totalUsers", 0)),
        }
        for r in rows
    ]


# ── 9. LANDING PAGES ──────────────────────────────────────────────────────────

def fetch_landing_pages(date_from: str, date_to: str, limit: int = 50) -> list[dict]:
    """First page of each session — key for SEO and ad landing page performance."""
    rows = _run_report(
        dimensions=["date", "landingPage"],
        metrics=["sessions", "totalUsers", "newUsers", "bounceRate",
                 "engagementRate", "averageSessionDuration"],
        date_from=date_from,
        date_to=date_to,
        order_bys=[
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True),
        ],
        limit=limit,
    )
    return [
        {
            "date":              r["date"],
            "landing_page":      r.get("landingPage") or "/",
            "sessions":          _int(r.get("sessions", 0)),
            "users":             _int(r.get("totalUsers", 0)),
            "new_users":         _int(r.get("newUsers", 0)),
            "bounce_rate":       round(_float(r.get("bounceRate", 0)) * 100, 1),
            "engagement_rate":   round(_float(r.get("engagementRate", 0)) * 100, 1),
            "avg_duration_secs": round(_float(r.get("averageSessionDuration", 0)), 1),
        }
        for r in rows
    ]


# ── 10. BROWSERS ─────────────────────────────────────────────────────────────

def fetch_browsers(date_from: str, date_to: str) -> list[dict]:
    """Sessions and users by browser — useful for compatibility decisions."""
    rows = _run_report(
        dimensions=["date", "browser"],
        metrics=["sessions", "totalUsers"],
        date_from=date_from,
        date_to=date_to,
        order_bys=[
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True),
        ],
        limit=200,
    )
    return [
        {
            "date":     r["date"],
            "browser":  r.get("browser") or "Unknown",
            "sessions": _int(r.get("sessions", 0)),
            "users":    _int(r.get("totalUsers", 0)),
        }
        for r in rows
    ]


# ── 11. COUNTRIES ─────────────────────────────────────────────────────────────

def fetch_countries(date_from: str, date_to: str) -> list[dict]:
    """Country-level aggregate — broader than city stats."""
    rows = _run_report(
        dimensions=["date", "country"],
        metrics=["sessions", "totalUsers", "newUsers"],
        date_from=date_from,
        date_to=date_to,
        order_bys=[
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True),
        ],
        limit=300,
    )
    return [
        {
            "date":      r["date"],
            "country":   r.get("country") or "Unknown",
            "sessions":  _int(r.get("sessions", 0)),
            "users":     _int(r.get("totalUsers", 0)),
            "new_users": _int(r.get("newUsers", 0)),
        }
        for r in rows
        if r.get("country") and r["country"] != "Unknown"
    ]


# ── 12. REFERRERS ─────────────────────────────────────────────────────────────

def fetch_referrers(date_from: str, date_to: str) -> list[dict]:
    """External sites that referred traffic — sessionMedium == 'referral'."""
    referral_filter = FilterExpression(
        filter=Filter(
            field_name="sessionMedium",
            string_filter=Filter.StringFilter(
                value="referral",
                match_type=Filter.StringFilter.MatchType.EXACT,
            ),
        )
    )
    rows = _run_report(
        dimensions=["date", "sessionSource"],
        metrics=["sessions", "totalUsers", "newUsers"],
        date_from=date_from,
        date_to=date_to,
        dimension_filter=referral_filter,
        order_bys=[
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True),
        ],
        limit=200,
    )
    return [
        {
            "date":      r["date"],
            "referrer":  r.get("sessionSource") or "Unknown",
            "sessions":  _int(r.get("sessions", 0)),
            "users":     _int(r.get("totalUsers", 0)),
            "new_users": _int(r.get("newUsers", 0)),
        }
        for r in rows
    ]


# ── 13. SEARCH TERMS ─────────────────────────────────────────────────────────

def fetch_search_terms(date_from: str, date_to: str) -> list[dict]:
    """
    Site search queries — requires site search tracking enabled in GA4.
    Returns empty list if searchTerm dimension is unavailable.
    """
    try:
        rows = _run_report(
            dimensions=["date", "searchTerm"],
            metrics=["sessions", "totalUsers", "screenPageViews"],
            date_from=date_from,
            date_to=date_to,
            order_bys=[
                OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
                OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True),
            ],
            limit=500,
        )
        return [
            {
                "date":        r["date"],
                "search_term": r.get("searchTerm") or "",
                "sessions":    _int(r.get("sessions", 0)),
                "users":       _int(r.get("totalUsers", 0)),
                "pageviews":   _int(r.get("screenPageViews", 0)),
            }
            for r in rows
            if r.get("searchTerm") and r["searchTerm"] not in ("(not set)", "Unknown", "")
        ]
    except Exception:
        return []


# ── 14. NEW VS RETURNING ─────────────────────────────────────────────────────

def fetch_new_vs_returning(date_from: str, date_to: str) -> list[dict]:
    """Segment by newVsReturning — compare engagement quality between cohorts."""
    rows = _run_report(
        dimensions=["date", "newVsReturning"],
        metrics=["sessions", "totalUsers", "engagementRate",
                 "bounceRate", "averageSessionDuration", "screenPageViewsPerSession"],
        date_from=date_from,
        date_to=date_to,
        order_bys=[
            OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
        ],
    )
    return [
        {
            "date":              r["date"],
            "segment":           r.get("newVsReturning") or "Unknown",
            "sessions":          _int(r.get("sessions", 0)),
            "users":             _int(r.get("totalUsers", 0)),
            "engagement_rate":   round(_float(r.get("engagementRate", 0)) * 100, 1),
            "bounce_rate":       round(_float(r.get("bounceRate", 0)) * 100, 1),
            "avg_duration_secs": round(_float(r.get("averageSessionDuration", 0)), 1),
            "pages_per_session": round(_float(r.get("screenPageViewsPerSession", 0)), 2),
        }
        for r in rows
    ]


# ── 15. METADATA ─────────────────────────────────────────────────────────────

def fetch_revenue(date_from: str, date_to: str) -> list[dict]:
    """Fetch ecommerce revenue and conversion counts per day."""
    rows = _run_report(
        dimensions=["date"],
        metrics=["totalRevenue", "purchaseRevenue", "ecommercePurchases",
                 "transactions", "conversions"],
        date_from=date_from,
        date_to=date_to,
    )
    return [
        {
            "date":             r["date"],
            "total_revenue":    round(_float(r.get("totalRevenue", 0)), 2),
            "purchase_revenue": round(_float(r.get("purchaseRevenue", 0)), 2),
            "purchases":        _int(r.get("ecommercePurchases", 0)),
            "transactions":     _int(r.get("transactions", 0)),
            "conversions":      _int(r.get("conversions", 0)),
        }
        for r in rows
    ]


def fetch_lead_summary(date_from: str, date_to: str, event_name: str = "generate_lead") -> list[dict]:
    """Daily totals for a specific conversion event (default: generate_lead)."""
    rows = _run_report(
        dimensions=["date"],
        metrics=["eventCount", "totalUsers"],
        date_from=date_from,
        date_to=date_to,
        dimension_filter=_event_filter(event_name),
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
    )
    return [
        {
            "date":  r["date"],
            "leads": _int(r.get("eventCount", 0)),
            "users": _int(r.get("totalUsers", 0)),
        }
        for r in rows
    ]


def fetch_lead_attribution(date_from: str, date_to: str, event_name: str = "generate_lead") -> list[dict]:
    """Where generate_lead conversions come from: source / medium / campaign."""
    rows = _run_report(
        dimensions=["date", "sessionSource", "sessionMedium", "sessionCampaignName"],
        metrics=["eventCount", "totalUsers"],
        date_from=date_from,
        date_to=date_to,
        dimension_filter=_event_filter(event_name),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="eventCount"), desc=True)],
        limit=2_000,
    )
    return [
        {
            "date":     r["date"],
            "source":   r.get("sessionSource") or "Unknown",
            "medium":   r.get("sessionMedium") or "Unknown",
            "campaign": r.get("sessionCampaignName") or "Unknown",
            "leads":    _int(r.get("eventCount", 0)),
            "users":    _int(r.get("totalUsers", 0)),
        }
        for r in rows
    ]


def fetch_lead_geo(date_from: str, date_to: str, event_name: str = "generate_lead") -> list[dict]:
    """Cities / countries where generate_lead conversions happened."""
    rows = _run_report(
        dimensions=["date", "city", "country"],
        metrics=["eventCount", "totalUsers"],
        date_from=date_from,
        date_to=date_to,
        dimension_filter=_event_filter(event_name),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="eventCount"), desc=True)],
        limit=2_000,
    )
    return [
        {
            "date":    r["date"],
            "city":    r.get("city") or "Unknown",
            "country": r.get("country") or "Unknown",
            "leads":   _int(r.get("eventCount", 0)),
            "users":   _int(r.get("totalUsers", 0)),
        }
        for r in rows
    ]


def fetch_lead_devices(date_from: str, date_to: str, event_name: str = "generate_lead") -> list[dict]:
    """Device category / browser breakdown of generate_lead conversions."""
    rows = _run_report(
        dimensions=["date", "deviceCategory", "browser"],
        metrics=["eventCount", "totalUsers"],
        date_from=date_from,
        date_to=date_to,
        dimension_filter=_event_filter(event_name),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="eventCount"), desc=True)],
        limit=1_000,
    )
    return [
        {
            "date":            r["date"],
            "device_category": r.get("deviceCategory") or "Unknown",
            "browser":         r.get("browser") or "Unknown",
            "leads":           _int(r.get("eventCount", 0)),
            "users":           _int(r.get("totalUsers", 0)),
        }
        for r in rows
    ]


def fetch_metadata() -> dict:
    """
    Returns all available dimensions and metrics for the property,
    including custom event parameters and custom user properties.
    Use this to discover what custom tracking exists in a property.
    """
    client, property_id = _client_and_property()
    if not property_id:
        raise RuntimeError("GA4 property_id not set")

    req  = GetMetadataRequest(name=f"properties/{property_id}/metadata")
    meta = client.get_metadata(req)

    dims = [
        {
            "api_name":   d.api_name,
            "ui_name":    d.ui_name,
            "description":d.description,
            "custom":     d.custom_definition,
        }
        for d in meta.dimensions
    ]
    mets = [
        {
            "api_name":   m.api_name,
            "ui_name":    m.ui_name,
            "description":m.description,
            "custom":     m.custom_definition,
        }
        for m in meta.metrics
    ]
    return {
        "dimensions":        dims,
        "metrics":           mets,
        "custom_dimensions": [d for d in dims if d["custom"]],
        "custom_metrics":    [m for m in mets if m["custom"]],
    }


# ── Convenience: get_credentials from account dict ───────────────────────────

def get_credentials(account: dict | None) -> dict[str, str]:
    """Extract credential keys from an account_manager account dict."""
    if not account:
        return {}
    return {
        "property_id":       account.get("ga4_property_id", ""),
        "credentials_path":  account.get("ga4_credentials_path", ""),
    }
