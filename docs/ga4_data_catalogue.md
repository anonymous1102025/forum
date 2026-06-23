# GA4 Data Catalogue

A complete reference of everything available in the Google Analytics 4 Data API — dimensions, metrics, and how they map to real business questions.

---

## How GA4 data works

GA4 stores every user interaction as an **event**. Even a page view is an event (`page_view`). Each event has **parameters** (properties attached to it). The Data API lets you query this data by combining **dimensions** (how to group) and **metrics** (what to measure).

```
Event: page_view
  Parameter: page_title = "How to bake bread"
  Parameter: page_location = "https://myforum.com/posts/123"
  Parameter: session_id = "abc123"
  User: new_user
  Session source: google / organic
```

---

## Dimensions

Dimensions are the "group by" columns. You can combine up to 9 per report.

### Time

| Dimension | API Name | Example Values |
|---|---|---|
| Date | `date` | `20260601` |
| Hour | `hour` | `0`–`23` |
| Day of week | `dayOfWeek` | `0` (Sun)–`6` (Sat) |
| Week | `week` | `01`–`53` |
| Month | `month` | `01`–`12` |
| Year | `year` | `2026` |

### Traffic source (session-level — "where did THIS session come from?")

| Dimension | API Name | Example Values |
|---|---|---|
| Channel group | `sessionDefaultChannelGroup` | `Organic Search`, `Direct`, `Referral`, `Organic Social`, `Paid Search` |
| Source | `sessionSource` | `google`, `facebook.com`, `newsletter.com` |
| Medium | `sessionMedium` | `organic`, `cpc`, `referral`, `email`, `(none)` |
| Campaign | `sessionCampaignName` | `spring-launch`, `(not set)` |
| Source/Medium | `sessionSourceMedium` | `google / organic` |
| Campaign ID | `sessionCampaignId` | GA4 campaign ID |
| Google Ads keyword | `sessionGoogleAdsKeyword` | `forum cooking` |

### First user attribution (how did the user FIRST arrive — lifetime first session)

| Dimension | API Name | Example Values |
|---|---|---|
| First channel | `firstUserDefaultChannelGroup` | `Organic Search` |
| First source | `firstUserSource` | `google` |
| First medium | `firstUserMedium` | `organic` |
| First campaign | `firstUserCampaignName` | `welcome-promo` |

### Page / content

| Dimension | API Name | Example Values |
|---|---|---|
| Page path | `pagePath` | `/posts/how-to-bake-bread` |
| Page title | `pageTitle` | `How to Bake Bread — My Forum` |
| Full URL | `fullPageUrl` | `https://myforum.com/posts/123?ref=home` |
| Landing page | `landingPage` | `/` or `/posts/123` |
| Exit page | `exitPage` | `/posts/123` |
| Page referrer | `pageReferrer` | `https://google.com` |
| Content group | `contentGroup` | Requires GA4 content grouping setup |
| Search term | `searchTerm` | `bread recipe` (requires site search tracking) |

### User

| Dimension | API Name | Example Values |
|---|---|---|
| New vs returning | `newVsReturning` | `new`, `returning` |
| Age bracket | `userAgeBracket` | `18-24`, `25-34`, etc. (requires Google signals) |
| Gender | `userGender` | `male`, `female` (requires Google signals) |

### Device

| Dimension | API Name | Example Values |
|---|---|---|
| Device category | `deviceCategory` | `mobile`, `desktop`, `tablet` |
| Operating system | `operatingSystem` | `Android`, `iOS`, `Windows`, `Macintosh` |
| OS version | `operatingSystemVersion` | `14.0`, `11` |
| Browser | `browser` | `Chrome`, `Safari`, `Firefox` |
| Browser version | `browserVersion` | `124.0` |
| Platform | `platform` | `Android`, `iOS`, `web` |
| Screen resolution | `screenResolution` | `1920x1080` |
| Mobile device brand | `mobileDeviceBranding` | `Apple`, `Samsung` |
| Mobile device model | `mobileDeviceModel` | `iPhone` |

### Geography

| Dimension | API Name | Example Values |
|---|---|---|
| Country | `country` | `United Kingdom`, `United States` |
| City | `city` | `London`, `Manchester` |
| Region | `region` | `England`, `California` |
| Continent | `continent` | `Europe`, `Americas` |
| Sub-continent | `subContinent` | `Northern Europe` |

### Event

| Dimension | API Name | Example Values |
|---|---|---|
| Event name | `eventName` | `page_view`, `scroll`, `click`, `user_register`, `comment_post` |

### Custom dimensions

GA4 allows you to register custom dimensions from event parameters. These show up as `customEvent:parameter_name` in the Metadata API. Examples for a forum:

| What you track | GA4 Custom Dimension |
|---|---|
| Post category | `customEvent:post_category` |
| Author name | `customEvent:author` |
| Comment count | `customEvent:comment_count` |
| User role | `customUser:user_type` |

---

## Metrics

Metrics are the numbers you measure. You can combine up to 10 per report.

### Users

| Metric | API Name | What it means |
|---|---|---|
| Total users | `totalUsers` | Unique users in the period |
| Active users | `activeUsers` | Users with at least one engaged session |
| New users | `newUsers` | First-time users |
| Returning users | `returningUsers` | Users seen before |
| DAU | `dauPerMau` | Daily active / monthly active (stickiness ratio, 0–1) |

### Sessions

| Metric | API Name | What it means |
|---|---|---|
| Sessions | `sessions` | Total sessions started |
| Engaged sessions | `engagedSessions` | Sessions lasting 10s+ or with 2+ pageviews or a conversion |
| Sessions per user | `sessionsPerUser` | Average sessions per user |
| Bounce rate | `bounceRate` | % of sessions with no engagement (opposite of engagement rate) |
| Engagement rate | `engagementRate` | % of sessions that were engaged |
| Avg session duration | `averageSessionDuration` | Mean session length in seconds |
| User engagement duration | `userEngagementDuration` | Total time users spent actively engaged |

### Page / content

| Metric | API Name | What it means |
|---|---|---|
| Page views | `screenPageViews` | Total page views |
| Views per session | `screenPageViewsPerSession` | Average pages per session |
| Scrolled users | `scrolledUsers` | Users who scrolled 90%+ of the page |

### Events

| Metric | API Name | What it means |
|---|---|---|
| Event count | `eventCount` | Total times an event fired |
| Events per session | `eventsPerSession` | Average events per session |
| Event count per user | `eventCountPerUser` | Average events per user |

### Conversions / Revenue

| Metric | API Name | What it means |
|---|---|---|
| Conversions | `conversions` | Total conversion events (events marked as conversions in GA4) |
| Total revenue | `totalRevenue` | Total revenue (if ecommerce or in-app purchases tracked) |

---

## Built-in GA4 events (always tracked automatically)

| Event | When it fires |
|---|---|
| `page_view` | Every page load |
| `session_start` | When a new session begins |
| `first_visit` | First time a user visits |
| `user_engagement` | When a user actively engages (10s+ on page) |
| `scroll` | When user scrolls 90% of the page |
| `click` | Outbound link clicks (if enhanced measurement on) |
| `file_download` | File downloads (if enhanced measurement on) |
| `video_start` | YouTube video start (if enhanced measurement on) |
| `video_progress` | YouTube video 10%/25%/50%/75% watched |
| `video_complete` | YouTube video 100% watched |
| `form_start` | User starts filling a form |
| `form_submit` | User submits a form |

---

## Typical forum-specific custom events to look for

These may or may not exist in your property — the explorer will tell you.

| Event | Meaning |
|---|---|
| `sign_up` | New user registration (GA4 recommended event) |
| `login` | User login |
| `share` | Content share |
| `search` | Site search |
| `comment_post` | User posted a comment |
| `thread_create` | User created a new thread/post |
| `upvote` / `like` | User liked/upvoted content |
| `notification_click` | User clicked a notification |

---

## What to check in the explorer report

When you run `ga4_explorer.py`, look for:

1. **Custom dimensions** — tells you what extra data your site sends to GA4
2. **Event names** — all the events tracked, especially any custom ones
3. **Conversions** — which events are marked as conversion goals
4. **Data freshness** — GA4 data is typically 24-48h delayed for standard reports
5. **Sampling** — if you see `dataLossFromOtherRow: true`, the report was sampled
6. **`(not set)`** values — indicates missing tracking on some pages

---

## GA4 Data API limits

| Limit | Value |
|---|---|
| Dimensions per report | 9 |
| Metrics per report | 10 |
| Date ranges per report | 4 |
| Rows per report | 250,000 (max) |
| Requests per day | 200,000 (Analytics Data API) |
| Requests per 100 seconds | 100 per project |
| Concurrent requests | 10 |

Data retention: default 14 months. Can be extended to 50 months in GA4 settings.
