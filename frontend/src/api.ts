import type { AnalyticsResponse, Period } from './types'

const BASE = import.meta.env.VITE_API_URL || ''

let _account: string | null = null
export function setCurrentAccount(slug: string | null) { _account = slug }

function accountParam() {
  return _account ? `&account=${_account}` : ''
}

export interface AccountSummary {
  slug:    string
  name:    string
  website: string
}

export async function fetchAccounts(): Promise<AccountSummary[]> {
  const res = await fetch(`${BASE}/api/accounts`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchAnalytics(period: Period, param: string): Promise<AnalyticsResponse> {
  let url = `${BASE}/api/analytics?period=${period}`
  if (period === 'daily')        url += `&date=${param}`
  else if (period === 'weekly')  url += `&week_start=${param}`
  else if (period === 'monthly') url += `&month=${param}`
  else if (period === 'custom') {
    const [start, end] = param.split('..')
    url += `&start=${start}&end=${end}`
  }
  url += accountParam()
  const res = await fetch(url)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchRunLog(limit = 20): Promise<{ runs: any[] }> {
  const res = await fetch(`${BASE}/api/fetch/status?limit=${limit}${accountParam()}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function triggerFetch(date: string): Promise<void> {
  const res = await fetch(
    `${BASE}/api/fetch/trigger?date=${date}${accountParam()}`,
    { method: 'POST' },
  )
  if (!res.ok) throw new Error(await res.text())
}

export async function triggerBackfill(from: string, to: string): Promise<void> {
  const res = await fetch(
    `${BASE}/api/fetch/backfill?from=${from}&to=${to}${accountParam()}`,
    { method: 'POST' },
  )
  if (!res.ok) throw new Error(await res.text())
}
