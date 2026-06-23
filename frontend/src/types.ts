export type Period = 'daily' | 'weekly' | 'monthly' | 'custom'

export interface Kpis {
  sessions:                  number
  users:                     number
  new_users:                 number
  returning_users:           number
  pageviews:                 number
  pages_per_session:         number
  avg_session_duration_secs: number
  bounce_rate:               number
  engagement_rate:           number
}

export interface TimeSeriesPoint {
  label:       string
  sessions:    number
  users:       number
  pageviews:   number
  hour?:       number
  active_users?: number
}

export interface TrafficSource {
  channel:   string
  sessions:  number
  users:     number
  new_users: number
}

export interface PageRow {
  page_path:                string
  page_title:               string
  views:                    number
  sessions:                 number
  avg_engagement_time_secs: number
}

export interface DeviceRow {
  device_category: string
  sessions:        number
  users:           number
}

export interface CityRow {
  city:     string
  country:  string
  sessions: number
  users:    number
}

export interface UtmRow {
  utm_source:   string
  utm_medium:   string
  utm_campaign: string
  sessions:     number
  users:        number
  new_users:    number
}

export interface EventRow {
  event_name:   string
  event_count:  number
  unique_users: number
}

export interface LandingPageRow {
  landing_page:     string
  sessions:         number
  users:            number
  new_users:        number
  bounce_rate:      number
  engagement_rate:  number
  avg_duration_secs: number
}

export interface BrowserRow {
  browser:  string
  sessions: number
  users:    number
}

export interface CountryRow {
  country:   string
  sessions:  number
  users:     number
  new_users: number
}

export interface ReferrerRow {
  referrer:  string
  sessions:  number
  users:     number
  new_users: number
}

export interface SearchTermRow {
  search_term: string
  sessions:    number
  users:       number
  pageviews:   number
}

export interface RevenueData {
  total_revenue:    number
  purchase_revenue: number
  purchases:        number
  transactions:     number
  conversions:      number
}

export interface RevenueSeriesPoint {
  date:             string
  total_revenue:    number
  purchase_revenue: number
  purchases:        number
  conversions:      number
}

export interface LeadSummary {
  leads: number
  users: number
}

export interface LeadAttributionRow {
  source:   string
  medium:   string
  campaign: string
  leads:    number
  users:    number
}

export interface LeadGeoRow {
  city:    string
  country: string
  leads:   number
  users:   number
}

export interface LeadDeviceRow {
  device_category: string
  browser:          string
  leads:            number
  users:            number
}

export interface NewVsReturningRow {
  segment:           string
  sessions:          number
  users:             number
  engagement_rate:   number
  bounce_rate:       number
  avg_duration_secs: number
  pages_per_session: number
}

export interface AnalyticsResponse {
  period:          Period
  label:           string
  dates_in_range:  string[]
  dates_with_data: string[]
  kpis:            Kpis
  time_series:     TimeSeriesPoint[]
  traffic:         TrafficSource[]
  pages:           PageRow[]
  device:          DeviceRow[]
  cities:          CityRow[]
  utm:             UtmRow[]
  events:          EventRow[]
  landing_pages:   LandingPageRow[]
  browsers:        BrowserRow[]
  countries:       CountryRow[]
  referrers:         ReferrerRow[]
  search_terms:      SearchTermRow[]
  new_vs_returning:  NewVsReturningRow[]
  revenue:           RevenueData
  revenue_series:    RevenueSeriesPoint[]
  leads:             LeadSummary
  lead_attribution:  LeadAttributionRow[]
  lead_geo:          LeadGeoRow[]
  lead_devices:      LeadDeviceRow[]
}
