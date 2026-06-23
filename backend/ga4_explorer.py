"""
ga4_explorer.py
===============
One-shot tool: connects to your GA4 property, fetches EVERYTHING available,
and saves a markdown report to docs/ga4_exploration_report.md.

Run once when setting up a new property to understand what data is available.

Usage:
    python ga4_explorer.py \\
        --credentials keys/your-service-account.json \\
        --property 123456789 \\
        --days 30 \\
        --output ../docs/ga4_exploration_report.md

What it does:
    1. Metadata API → every available dimension + metric for your property
    2. Top-level KPIs (sessions, users, pageviews, engagement)
    3. All traffic channels
    4. Top 50 pages
    5. All events and their counts → crucial for discovering custom tracking
    6. Device / browser / OS breakdown
    7. Full geo breakdown (country + city)
    8. UTM / campaign attribution
    9. Landing pages
    10. Search terms (if tracked)
    11. Hourly pattern

Everything is saved to JSON in data/exploration/ and a readable markdown report.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path
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


# ── Auth ───────────────────────────────────────────────────────────────────────

def make_client(credentials_path: str | None) -> BetaAnalyticsDataClient:
    # 1. Explicit path supplied — detect type from JSON content
    if credentials_path:
        with open(credentials_path) as f:
            key_data = json.load(f)

        if key_data.get("type") == "service_account":
            creds = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/analytics.readonly"],
            )
        else:
            # OAuth user token (saved by auth_setup.py)
            creds = OAuthCredentials.from_authorized_user_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/analytics.readonly"],
            )
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())

        return BetaAnalyticsDataClient(credentials=creds)

    # 2. Auto-detect: use saved user token if present
    if os.path.exists("keys/user_token.json"):
        return make_client("keys/user_token.json")

    # 3. Fall back to Application Default Credentials
    return BetaAnalyticsDataClient()


# ── Low-level runner ───────────────────────────────────────────────────────────

def run_report(
    client: BetaAnalyticsDataClient,
    property_id: str,
    dimensions: list[str],
    metrics: list[str],
    date_from: str,
    date_to: str,
    dimension_filter: FilterExpression | None = None,
    order_bys: list[OrderBy] | None = None,
    limit: int = 10_000,
) -> list[dict[str, Any]]:
    req = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=date_from, end_date=date_to)],
        limit=limit,
    )
    if dimension_filter:
        req.dimension_filter = dimension_filter
    if order_bys:
        req.order_bys = order_bys

    resp = client.run_report(req)
    dim_names = [h.name for h in resp.dimension_headers]
    met_names = [h.name for h in resp.metric_headers]

    rows = []
    for row in resp.rows:
        r: dict[str, Any] = {}
        for i, dv in enumerate(row.dimension_values):
            r[dim_names[i]] = dv.value
        for i, mv in enumerate(row.metric_values):
            r[met_names[i]] = mv.value
        rows.append(r)
    return rows


def safe_int(v: Any) -> int:
    try: return int(float(str(v)))
    except: return 0


def safe_float(v: Any) -> float:
    try: return round(float(str(v)), 2)
    except: return 0.0


# ── Sections ───────────────────────────────────────────────────────────────────

def fetch_metadata(client: BetaAnalyticsDataClient, property_id: str) -> dict:
    req = GetMetadataRequest(name=f"properties/{property_id}/metadata")
    meta = client.get_metadata(req)

    dims = []
    for d in meta.dimensions:
        dims.append({
            "api_name":      d.api_name,
            "ui_name":       d.ui_name,
            "description":   d.description,
            "deprecated_api_names": list(d.deprecated_api_names),
            "custom":        d.custom_definition,
        })

    mets = []
    for m in meta.metrics:
        mets.append({
            "api_name":      m.api_name,
            "ui_name":       m.ui_name,
            "description":   m.description,
            "type":          str(m.type_),
            "expression":    m.expression,
            "custom":        m.custom_definition,
        })

    custom_dims = [d for d in dims if d["custom"]]
    custom_mets = [m for m in mets if m["custom"]]

    return {
        "total_dimensions": len(dims),
        "total_metrics":    len(mets),
        "custom_dimensions": custom_dims,
        "custom_metrics":   custom_mets,
        "all_dimensions":   dims,
        "all_metrics":      mets,
    }


def fetch_overview(client, pid, date_from, date_to) -> dict:
    rows = run_report(client, pid,
        dimensions=["date"],
        metrics=["sessions", "totalUsers", "newUsers",
                 "screenPageViews", "engagedSessions", "engagementRate",
                 "bounceRate", "averageSessionDuration", "screenPageViewsPerSession"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
    )
    totals: dict[str, Any] = {
        "sessions": 0, "total_users": 0, "new_users": 0,
        "pageviews": 0, "engaged_sessions": 0,
    }
    for r in rows:
        totals["sessions"]        += safe_int(r.get("sessions", 0))
        totals["total_users"]     += safe_int(r.get("totalUsers", 0))
        totals["new_users"]       += safe_int(r.get("newUsers", 0))
        totals["pageviews"]       += safe_int(r.get("screenPageViews", 0))
        totals["engaged_sessions"]+= safe_int(r.get("engagedSessions", 0))

    # Weighted averages
    total_sess = totals["sessions"] or 1
    engagement_rates   = [safe_float(r.get("engagementRate", 0))   * safe_int(r.get("sessions",0)) for r in rows]
    bounce_rates       = [safe_float(r.get("bounceRate", 0))        * safe_int(r.get("sessions",0)) for r in rows]
    avg_durations      = [safe_float(r.get("averageSessionDuration",0)) * safe_int(r.get("sessions",0)) for r in rows]
    pps                = [safe_float(r.get("screenPageViewsPerSession",0)) * safe_int(r.get("sessions",0)) for r in rows]

    totals["avg_engagement_rate"]      = round(sum(engagement_rates) / total_sess * 100, 1)
    totals["avg_bounce_rate"]          = round(sum(bounce_rates) / total_sess * 100, 1)
    totals["avg_session_duration_secs"]= round(sum(avg_durations) / total_sess, 1)
    totals["avg_pages_per_session"]    = round(sum(pps) / total_sess, 2)
    totals["returning_users"]          = max(totals["total_users"] - totals["new_users"], 0)
    totals["daily_rows"]               = rows
    return totals


def fetch_channels(client, pid, date_from, date_to) -> list[dict]:
    rows = run_report(client, pid,
        dimensions=["sessionDefaultChannelGroup"],
        metrics=["sessions", "totalUsers", "newUsers", "engagedSessions",
                 "engagementRate", "bounceRate", "averageSessionDuration"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
    )
    return [{
        "channel":               r.get("sessionDefaultChannelGroup", "Unknown"),
        "sessions":              safe_int(r.get("sessions", 0)),
        "users":                 safe_int(r.get("totalUsers", 0)),
        "new_users":             safe_int(r.get("newUsers", 0)),
        "engaged_sessions":      safe_int(r.get("engagedSessions", 0)),
        "engagement_rate_pct":   round(safe_float(r.get("engagementRate", 0)) * 100, 1),
        "bounce_rate_pct":       round(safe_float(r.get("bounceRate", 0)) * 100, 1),
        "avg_session_duration_secs": safe_float(r.get("averageSessionDuration", 0)),
    } for r in rows]


def fetch_events(client, pid, date_from, date_to) -> list[dict]:
    rows = run_report(client, pid,
        dimensions=["eventName"],
        metrics=["eventCount", "totalUsers", "eventCountPerUser", "sessionsPerUser"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="eventCount"), desc=True)],
        limit=500,
    )
    return [{
        "event_name":          r.get("eventName", ""),
        "event_count":         safe_int(r.get("eventCount", 0)),
        "unique_users":        safe_int(r.get("totalUsers", 0)),
        "events_per_user":     safe_float(r.get("eventCountPerUser", 0)),
    } for r in rows]


def fetch_pages(client, pid, date_from, date_to) -> list[dict]:
    rows = run_report(client, pid,
        dimensions=["pagePath", "pageTitle"],
        metrics=["screenPageViews", "sessions", "activeUsers",
                 "averageSessionDuration", "bounceRate", "engagementRate"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)],
        limit=100,
    )
    return [{
        "page_path":             r.get("pagePath", "/"),
        "page_title":            r.get("pageTitle", ""),
        "views":                 safe_int(r.get("screenPageViews", 0)),
        "sessions":              safe_int(r.get("sessions", 0)),
        "active_users":          safe_int(r.get("activeUsers", 0)),
        "avg_session_duration_secs": safe_float(r.get("averageSessionDuration", 0)),
        "bounce_rate_pct":       round(safe_float(r.get("bounceRate", 0)) * 100, 1),
        "engagement_rate_pct":   round(safe_float(r.get("engagementRate", 0)) * 100, 1),
    } for r in rows]


def fetch_landing_pages(client, pid, date_from, date_to) -> list[dict]:
    rows = run_report(client, pid,
        dimensions=["landingPage"],
        metrics=["sessions", "totalUsers", "newUsers", "bounceRate",
                 "engagementRate", "averageSessionDuration"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=50,
    )
    return [{
        "landing_page":          r.get("landingPage", "/"),
        "sessions":              safe_int(r.get("sessions", 0)),
        "users":                 safe_int(r.get("totalUsers", 0)),
        "new_users":             safe_int(r.get("newUsers", 0)),
        "bounce_rate_pct":       round(safe_float(r.get("bounceRate", 0)) * 100, 1),
        "engagement_rate_pct":   round(safe_float(r.get("engagementRate", 0)) * 100, 1),
        "avg_duration_secs":     safe_float(r.get("averageSessionDuration", 0)),
    } for r in rows]


def fetch_device(client, pid, date_from, date_to) -> dict:
    # Device category
    by_category = run_report(client, pid,
        dimensions=["deviceCategory"],
        metrics=["sessions", "totalUsers", "engagementRate", "bounceRate"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
    )
    # Browser
    by_browser = run_report(client, pid,
        dimensions=["browser"],
        metrics=["sessions", "totalUsers"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=20,
    )
    # Operating system
    by_os = run_report(client, pid,
        dimensions=["operatingSystem"],
        metrics=["sessions", "totalUsers"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=20,
    )
    # Screen resolution
    by_screen = run_report(client, pid,
        dimensions=["screenResolution"],
        metrics=["sessions"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=15,
    )
    return {
        "by_category": [{
            "device":           r.get("deviceCategory", ""),
            "sessions":         safe_int(r.get("sessions", 0)),
            "users":            safe_int(r.get("totalUsers", 0)),
            "engagement_pct":   round(safe_float(r.get("engagementRate", 0)) * 100, 1),
            "bounce_pct":       round(safe_float(r.get("bounceRate", 0)) * 100, 1),
        } for r in by_category],
        "by_browser": [{"browser": r.get("browser",""), "sessions": safe_int(r.get("sessions",0)), "users": safe_int(r.get("totalUsers",0))} for r in by_browser],
        "by_os": [{"os": r.get("operatingSystem",""), "sessions": safe_int(r.get("sessions",0)), "users": safe_int(r.get("totalUsers",0))} for r in by_os],
        "by_screen": [{"resolution": r.get("screenResolution",""), "sessions": safe_int(r.get("sessions",0))} for r in by_screen],
    }


def fetch_geo(client, pid, date_from, date_to) -> dict:
    by_country = run_report(client, pid,
        dimensions=["country"],
        metrics=["sessions", "totalUsers", "newUsers"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=50,
    )
    by_city = run_report(client, pid,
        dimensions=["city", "country"],
        metrics=["sessions", "totalUsers"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=50,
    )
    return {
        "by_country": [{"country": r.get("country",""), "sessions": safe_int(r.get("sessions",0)), "users": safe_int(r.get("totalUsers",0)), "new_users": safe_int(r.get("newUsers",0))} for r in by_country],
        "by_city":    [{"city": r.get("city",""), "country": r.get("country",""), "sessions": safe_int(r.get("sessions",0)), "users": safe_int(r.get("totalUsers",0))} for r in by_city],
    }


def fetch_utm(client, pid, date_from, date_to) -> list[dict]:
    rows = run_report(client, pid,
        dimensions=["sessionSource", "sessionMedium", "sessionCampaignName"],
        metrics=["sessions", "totalUsers", "newUsers", "engagedSessions", "engagementRate"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=100,
    )
    return [{
        "source":          r.get("sessionSource", ""),
        "medium":          r.get("sessionMedium", ""),
        "campaign":        r.get("sessionCampaignName", ""),
        "sessions":        safe_int(r.get("sessions", 0)),
        "users":           safe_int(r.get("totalUsers", 0)),
        "new_users":       safe_int(r.get("newUsers", 0)),
        "engaged_sessions":safe_int(r.get("engagedSessions", 0)),
        "engagement_pct":  round(safe_float(r.get("engagementRate", 0)) * 100, 1),
    } for r in rows]


def fetch_search_terms(client, pid, date_from, date_to) -> list[dict]:
    try:
        rows = run_report(client, pid,
            dimensions=["searchTerm"],
            metrics=["sessions", "totalUsers", "screenPageViews"],
            date_from=date_from, date_to=date_to,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
            limit=50,
        )
        return [{
            "search_term": r.get("searchTerm", ""),
            "sessions":    safe_int(r.get("sessions", 0)),
            "users":       safe_int(r.get("totalUsers", 0)),
            "pageviews":   safe_int(r.get("screenPageViews", 0)),
        } for r in rows if r.get("searchTerm") not in ("(not set)", "")]
    except Exception:
        return []  # searchTerm not available if site search not tracked


def fetch_hourly(client, pid, date_from, date_to) -> list[dict]:
    rows = run_report(client, pid,
        dimensions=["hour", "dayOfWeekName"],
        metrics=["sessions", "activeUsers", "screenPageViews"],
        date_from=date_from, date_to=date_to,
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="hour"))],
    )
    return [{
        "hour":       safe_int(r.get("hour", 0)),
        "day_of_week":r.get("dayOfWeekName", ""),
        "sessions":   safe_int(r.get("sessions", 0)),
        "users":      safe_int(r.get("activeUsers", 0)),
        "pageviews":  safe_int(r.get("screenPageViews", 0)),
    } for r in rows]


def fetch_new_vs_returning(client, pid, date_from, date_to) -> list[dict]:
    rows = run_report(client, pid,
        dimensions=["newVsReturning"],
        metrics=["sessions", "totalUsers", "engagementRate",
                 "bounceRate", "averageSessionDuration", "screenPageViewsPerSession"],
        date_from=date_from, date_to=date_to,
    )
    return [{
        "segment":                  r.get("newVsReturning", ""),
        "sessions":                 safe_int(r.get("sessions", 0)),
        "users":                    safe_int(r.get("totalUsers", 0)),
        "engagement_rate_pct":      round(safe_float(r.get("engagementRate", 0)) * 100, 1),
        "bounce_rate_pct":          round(safe_float(r.get("bounceRate", 0)) * 100, 1),
        "avg_duration_secs":        safe_float(r.get("averageSessionDuration", 0)),
        "pages_per_session":        safe_float(r.get("screenPageViewsPerSession", 0)),
    } for r in rows]


def fetch_referrers(client, pid, date_from, date_to) -> list[dict]:
    """External referrers — other sites that sent traffic."""
    filter_expr = FilterExpression(
        filter=Filter(
            field_name="sessionMedium",
            string_filter=Filter.StringFilter(value="referral", match_type=Filter.StringFilter.MatchType.EXACT),
        )
    )
    rows = run_report(client, pid,
        dimensions=["sessionSource"],
        metrics=["sessions", "totalUsers", "newUsers"],
        date_from=date_from, date_to=date_to,
        dimension_filter=filter_expr,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=50,
    )
    return [{
        "referrer":  r.get("sessionSource", ""),
        "sessions":  safe_int(r.get("sessions", 0)),
        "users":     safe_int(r.get("totalUsers", 0)),
        "new_users": safe_int(r.get("newUsers", 0)),
    } for r in rows]


# ── Markdown report generator ──────────────────────────────────────────────────

def _fmt_dur(secs: float) -> str:
    s = int(secs)
    if s < 60: return f"{s}s"
    return f"{s//60}m {s%60}s"

def _pct(v: float) -> str:
    return f"{v:.1f}%"

def _n(v: int) -> str:
    return f"{v:,}"


_EMPTY_OV = {
    "sessions": 0, "total_users": 0, "new_users": 0, "returning_users": 0,
    "pageviews": 0, "engaged_sessions": 0,
    "avg_engagement_rate": 0.0, "avg_bounce_rate": 0.0,
    "avg_session_duration_secs": 0.0, "avg_pages_per_session": 0.0,
    "daily_rows": [],
}


def generate_report(data: dict, property_id: str, date_from: str, date_to: str) -> str:
    now = date.today().isoformat()
    ov  = data.get("overview") or _EMPTY_OV
    meta= data["metadata"]
    ch  = data["channels"]
    ev  = data["events"]
    pg  = data["pages"]
    lp  = data["landing_pages"]
    dev = data["device"]
    geo = data["geo"]
    utm = data["utm"]
    st  = data["search_terms"]
    nr  = data["new_vs_returning"]
    ref = data["referrers"]

    total_sessions = ov["sessions"] or 1

    lines = [
        f"# GA4 Exploration Report",
        f"",
        f"**Property ID:** `{property_id}`  ",
        f"**Date range:** {date_from} → {date_to}  ",
        f"**Generated:** {now}",
        f"",
        f"---",
        f"",

        # ── HEADLINE ──
        f"## Headline Numbers",
        f"",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Sessions | {_n(ov['sessions'])} |",
        f"| Total Users | {_n(ov['total_users'])} |",
        f"| New Users | {_n(ov['new_users'])} |",
        f"| Returning Users | {_n(ov['returning_users'])} |",
        f"| Pageviews | {_n(ov['pageviews'])} |",
        f"| Engaged Sessions | {_n(ov['engaged_sessions'])} |",
        f"| Avg Engagement Rate | {_pct(ov['avg_engagement_rate'])} |",
        f"| Avg Bounce Rate | {_pct(ov['avg_bounce_rate'])} |",
        f"| Avg Session Duration | {_fmt_dur(ov['avg_session_duration_secs'])} |",
        f"| Avg Pages / Session | {ov['avg_pages_per_session']:.2f} |",
        f"",

        # ── METADATA ──
        f"## What Data Is Available (Metadata)",
        f"",
        f"Your GA4 property has **{meta['total_dimensions']} dimensions** and **{meta['total_metrics']} metrics** available.",
        f"",
    ]

    if meta["custom_dimensions"]:
        lines += [
            f"### Custom Dimensions ({len(meta['custom_dimensions'])} found)",
            f"",
            f"These are property-specific — they come from your own tracking setup.",
            f"",
            f"| API Name | Display Name | Description |",
            f"|---|---|---|",
        ]
        for d in meta["custom_dimensions"]:
            lines.append(f"| `{d['api_name']}` | {d['ui_name']} | {d['description'][:80]} |")
        lines.append("")
    else:
        lines += [f"No custom dimensions found — only standard GA4 dimensions are available.", f""]

    if meta["custom_metrics"]:
        lines += [
            f"### Custom Metrics ({len(meta['custom_metrics'])} found)",
            f"",
            f"| API Name | Display Name | Description |",
            f"|---|---|---|",
        ]
        for m in meta["custom_metrics"]:
            lines.append(f"| `{m['api_name']}` | {m['ui_name']} | {m['description'][:80]} |")
        lines.append("")

    # ── EVENTS ──
    lines += [
        f"## Events",
        f"",
        f"GA4 tracks everything as events. Here are all events fired on your property in this period:",
        f"",
        f"| Event Name | Count | Unique Users | Is Custom? |",
        f"|---|---|---|---|",
    ]
    standard = {"page_view","session_start","first_visit","user_engagement","scroll",
                "click","file_download","video_start","video_progress","video_complete",
                "form_start","form_submit","view_search_results","purchase","add_to_cart",
                "begin_checkout","login","sign_up","share","search","exception",
                "screen_view","app_exception"}
    for e in ev:
        is_custom = "✅ Custom" if e["event_name"] not in standard else "—"
        lines.append(f"| `{e['event_name']}` | {_n(e['event_count'])} | {_n(e['unique_users'])} | {is_custom} |")
    lines.append("")

    custom_events = [e for e in ev if e["event_name"] not in standard]
    if custom_events:
        lines += [
            f"### Custom events found ({len(custom_events)})",
            f"",
            f"These are events your site fires beyond the standard GA4 events:",
            f"",
        ]
        for e in custom_events:
            lines.append(f"- **`{e['event_name']}`** — {_n(e['event_count'])} times by {_n(e['unique_users'])} users")
        lines.append("")
    else:
        lines += [f"No custom events found. Only standard GA4 events are tracked.", f""]

    # ── TRAFFIC CHANNELS ──
    lines += [
        f"## Traffic Channels",
        f"",
        f"| Channel | Sessions | Share | Users | Engagement | Bounce | Avg Duration |",
        f"|---|---|---|---|---|---|---|",
    ]
    for c in ch:
        share = round(c["sessions"] / total_sessions * 100, 1)
        lines.append(f"| {c['channel']} | {_n(c['sessions'])} | {share}% | {_n(c['users'])} | {_pct(c['engagement_rate_pct'])} | {_pct(c['bounce_rate_pct'])} | {_fmt_dur(c['avg_session_duration_secs'])} |")
    lines.append("")

    # ── NEW VS RETURNING ──
    if nr:
        lines += [
            f"## New vs Returning Visitors",
            f"",
            f"| Segment | Sessions | Users | Engagement | Bounce | Avg Duration | Pages/Session |",
            f"|---|---|---|---|---|---|---|",
        ]
        for r in nr:
            lines.append(f"| {r['segment']} | {_n(r['sessions'])} | {_n(r['users'])} | {_pct(r['engagement_rate_pct'])} | {_pct(r['bounce_rate_pct'])} | {_fmt_dur(r['avg_duration_secs'])} | {r['pages_per_session']:.2f} |")
        lines.append("")

    # ── TOP PAGES ──
    lines += [
        f"## Top Pages (by views)",
        f"",
        f"| # | Page | Views | Sessions | Avg Duration | Engagement |",
        f"|---|---|---|---|---|---|",
    ]
    for i, p in enumerate(pg[:30]):
        title = p["page_title"][:50] if p["page_title"] else p["page_path"]
        lines.append(f"| {i+1} | [{title}]({p['page_path']}) | {_n(p['views'])} | {_n(p['sessions'])} | {_fmt_dur(p['avg_session_duration_secs'])} | {_pct(p['engagement_rate_pct'])} |")
    lines.append("")

    # ── LANDING PAGES ──
    lines += [
        f"## Landing Pages (first page of session)",
        f"",
        f"Where visitors start their sessions — key for SEO and ad landing page performance.",
        f"",
        f"| Landing Page | Sessions | New Users | Bounce | Engagement | Avg Duration |",
        f"|---|---|---|---|---|---|",
    ]
    for lpp in lp[:20]:
        lines.append(f"| `{lpp['landing_page']}` | {_n(lpp['sessions'])} | {_n(lpp['new_users'])} | {_pct(lpp['bounce_rate_pct'])} | {_pct(lpp['engagement_rate_pct'])} | {_fmt_dur(lpp['avg_duration_secs'])} |")
    lines.append("")

    # ── REFERRERS ──
    if ref:
        lines += [
            f"## External Referrers",
            f"",
            f"Other websites sending traffic to you.",
            f"",
            f"| Referrer | Sessions | Users | New Users |",
            f"|---|---|---|---|",
        ]
        for r in ref[:20]:
            lines.append(f"| {r['referrer']} | {_n(r['sessions'])} | {_n(r['users'])} | {_n(r['new_users'])} |")
        lines.append("")

    # ── DEVICE ──
    lines += [
        f"## Device Breakdown",
        f"",
        f"### By Category",
        f"",
        f"| Device | Sessions | Users | Engagement | Bounce |",
        f"|---|---|---|---|---|",
    ]
    for d in dev["by_category"]:
        lines.append(f"| {d['device']} | {_n(d['sessions'])} | {_n(d['users'])} | {_pct(d['engagement_pct'])} | {_pct(d['bounce_pct'])} |")
    lines += [f"", f"### Top Browsers", f""]
    for b in dev["by_browser"][:10]:
        share = round(b['sessions'] / total_sessions * 100, 1)
        lines.append(f"- **{b['browser']}** — {_n(b['sessions'])} sessions ({share}%)")
    lines += [f"", f"### Top Operating Systems", f""]
    for o in dev["by_os"][:8]:
        share = round(o['sessions'] / total_sessions * 100, 1)
        lines.append(f"- **{o['os']}** — {_n(o['sessions'])} sessions ({share}%)")
    lines.append("")

    # ── GEO ──
    lines += [
        f"## Geography",
        f"",
        f"### By Country",
        f"",
        f"| Country | Sessions | Users | New Users |",
        f"|---|---|---|---|",
    ]
    for c in geo["by_country"][:20]:
        lines.append(f"| {c['country']} | {_n(c['sessions'])} | {_n(c['users'])} | {_n(c['new_users'])} |")
    lines += [f"", f"### By City", f"", f"| City | Country | Sessions |", f"|---|---|---|"]
    for c in geo["by_city"][:20]:
        lines.append(f"| {c['city']} | {c['country']} | {_n(c['sessions'])} |")
    lines.append("")

    # ── UTM ──
    if utm:
        lines += [
            f"## UTM Campaign Attribution",
            f"",
            f"| Source | Medium | Campaign | Sessions | Engaged | Engagement |",
            f"|---|---|---|---|---|---|",
        ]
        for u in utm[:20]:
            lines.append(f"| {u['source']} | {u['medium']} | {u['campaign'] or '—'} | {_n(u['sessions'])} | {_n(u['engaged_sessions'])} | {_pct(u['engagement_pct'])} |")
        lines.append("")
    else:
        lines += [f"## UTM Campaign Attribution", f"", f"No UTM-tagged traffic found in this period.", f""]

    # ── SEARCH TERMS ──
    if st:
        lines += [
            f"## Site Search Terms",
            f"",
            f"What visitors searched for on your site:",
            f"",
            f"| Search Term | Sessions | Users |",
            f"|---|---|---|",
        ]
        for s in st[:20]:
            lines.append(f"| {s['search_term']} | {_n(s['sessions'])} | {_n(s['users'])} |")
        lines.append("")
    else:
        lines += [f"## Site Search Terms", f"", f"No site search data found — either site search is not tracked, or `searchTerm` dimension is not available for this property.", f""]

    # ── HOURLY ──
    lines += [
        f"## Hourly Traffic Pattern",
        f"",
        f"Aggregated across the full date range — shows peak times.",
        f"",
        f"| Hour | Sessions | Active Users |",
        f"|---|---|---|",
    ]
    hourly_by_hour: dict[int, dict] = {}
    for h in data["hourly"]:
        hr = h["hour"]
        if hr not in hourly_by_hour:
            hourly_by_hour[hr] = {"sessions": 0, "users": 0}
        hourly_by_hour[hr]["sessions"] += h["sessions"]
        hourly_by_hour[hr]["users"]    += h["users"]

    for hr in sorted(hourly_by_hour):
        bar = "█" * min(20, int(hourly_by_hour[hr]["sessions"] / max(1, total_sessions) * 200))
        lines.append(f"| {hr:02d}:00 | {_n(hourly_by_hour[hr]['sessions'])} | {_n(hourly_by_hour[hr]['users'])} | {bar} |")
    lines.append("")

    # ── WHAT TO TRACK NEXT ──
    lines += [
        f"## Recommendations",
        f"",
        f"Based on what was found in your property:",
        f"",
    ]

    if not custom_events:
        lines += [
            f"- **Add custom events** — your site only has standard GA4 events. For a forum, track:",
            f"  - `sign_up` on registration success",
            f"  - `login` on user login",
            f"  - `comment_post` when a comment is submitted",
            f"  - `thread_create` when a new post/thread is created",
            f"  - `search` on site search",
        ]
    if not st:
        lines += [f"- **Enable site search tracking** — go to GA4 Admin → Data Streams → Enhanced Measurement → Site Search"]
    if not utm:
        lines += [f"- **Add UTM parameters** to your email newsletters, social posts, and ad links"]
    if ov['avg_bounce_rate'] > 60:
        lines += [f"- **High bounce rate ({_pct(ov['avg_bounce_rate'])})** — investigate the top landing pages for load speed and content relevance"]
    if ov['avg_pages_per_session'] < 1.5:
        lines += [f"- **Low pages/session ({ov['avg_pages_per_session']:.2f})** — add internal linking between related posts/threads"]

    lines += [f"", f"---", f"", f"*Report generated by `ga4_explorer.py` from `forum_analytics`*"]
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Explore a GA4 property and generate a data report")
    parser.add_argument("--credentials", required=False, default=None, help="Path to service account JSON key (omit to use gcloud ADC)")
    parser.add_argument("--property",    required=True, help="GA4 property ID (numeric, e.g. 123456789)")
    parser.add_argument("--days",        type=int, default=30, help="Number of days to analyse (default: 30)")
    parser.add_argument("--output",      default="../docs/ga4_exploration_report.md", help="Path for markdown output")
    parser.add_argument("--json-output", default=None, help="Optional path to save raw JSON data")
    args = parser.parse_args()

    date_to   = str(date.today() - timedelta(days=1))
    date_from = str(date.today() - timedelta(days=args.days))

    print(f"\n━━━ GA4 Explorer ━━━")
    print(f"Property : {args.property}")
    print(f"Range    : {date_from} → {date_to} ({args.days} days)")
    print(f"Creds    : {args.credentials or 'Application Default Credentials (gcloud)'}")
    print()

    client = make_client(args.credentials)
    pid    = args.property

    sections = [
        ("Metadata (dimensions + metrics catalogue)", "metadata",        lambda: fetch_metadata(client, pid)),
        ("Overview KPIs",                             "overview",         lambda: fetch_overview(client, pid, date_from, date_to)),
        ("Traffic channels",                          "channels",         lambda: fetch_channels(client, pid, date_from, date_to)),
        ("All events",                                "events",           lambda: fetch_events(client, pid, date_from, date_to)),
        ("Top pages",                                 "pages",            lambda: fetch_pages(client, pid, date_from, date_to)),
        ("Landing pages",                             "landing_pages",    lambda: fetch_landing_pages(client, pid, date_from, date_to)),
        ("Device / browser / OS",                     "device",           lambda: fetch_device(client, pid, date_from, date_to)),
        ("Geography",                                 "geo",              lambda: fetch_geo(client, pid, date_from, date_to)),
        ("UTM campaigns",                             "utm",              lambda: fetch_utm(client, pid, date_from, date_to)),
        ("Site search terms",                         "search_terms",     lambda: fetch_search_terms(client, pid, date_from, date_to)),
        ("New vs returning",                          "new_vs_returning", lambda: fetch_new_vs_returning(client, pid, date_from, date_to)),
        ("Referrers",                                 "referrers",        lambda: fetch_referrers(client, pid, date_from, date_to)),
        ("Hourly pattern",                            "hourly",           lambda: fetch_hourly(client, pid, date_from, date_to)),
    ]

    all_data: dict[str, Any] = {}

    for label, key, fn in sections:
        print(f"  Fetching {label}…", end=" ", flush=True)
        try:
            all_data[key] = fn()
            print("✓")
        except Exception as e:
            print(f"✗  ({e})")
            all_data[key] = {}

    # Save JSON
    if args.json_output:
        Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_output, "w") as f:
            json.dump(all_data, f, indent=2, default=str)
        print(f"\nJSON saved → {args.json_output}")

    # Generate markdown report
    report = generate_report(all_data, pid, date_from, date_to)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    print(f"\nReport saved → {args.output}")
    print()

    # Print summary to terminal
    ov = all_data.get("overview", {})
    ev = all_data.get("events", [])
    standard = {"page_view","session_start","first_visit","user_engagement","scroll",
                "click","file_download","video_start","video_progress","video_complete",
                "form_start","form_submit","view_search_results","purchase"}
    custom_ev = [e for e in ev if e.get("event_name","") not in standard]

    print("━━━ Summary ━━━")
    print(f"Sessions      : {ov.get('sessions',0):,}")
    print(f"Users         : {ov.get('total_users',0):,}")
    print(f"Pageviews     : {ov.get('pageviews',0):,}")
    print(f"Engagement    : {ov.get('avg_engagement_rate',0):.1f}%")
    print(f"Avg Duration  : {_fmt_dur(ov.get('avg_session_duration_secs',0))}")
    print(f"Events found  : {len(ev)} total, {len(custom_ev)} custom")
    if custom_ev:
        print(f"Custom events : {', '.join(e['event_name'] for e in custom_ev[:8])}")
    print()


if __name__ == "__main__":
    main()
