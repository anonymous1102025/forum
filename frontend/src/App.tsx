import { useState, useEffect, useCallback, useRef } from 'react'
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell,
  ScatterChart, Scatter, ZAxis,
} from 'recharts'
import { ChevronLeft, ChevronRight, RefreshCw, AlertCircle, ExternalLink, Sun, Moon, TrendingDown, TrendingUp, Info } from 'lucide-react'
import { format, addDays, subDays, addWeeks, subWeeks, addMonths, subMonths, startOfWeek, startOfMonth } from 'date-fns'
import { fetchAnalytics, fetchRunLog, triggerFetch, fetchAccounts, setCurrentAccount } from './api'
import type { AnalyticsResponse, Period } from './types'
import type { AccountSummary } from './api'
import { isLoggedIn, clearToken } from './auth'
import LoginPage from './LoginPage'

/* ─── Theme-aware color tokens (CSS custom properties) ───────────────────── */
const C = {
  // Structural — change with theme
  bg:           'var(--bg)',
  surface:      'var(--surface)',
  card:         'var(--card)',
  cardHov:      'var(--card-hov)',
  border:       'var(--border)',
  borderHov:    'var(--border-hov)',
  borderSubtle: 'var(--border-subtle)',
  text:         'var(--text)',
  muted:        'var(--muted)',
  faint:        'var(--faint)',
  faintA:       'var(--faint-a)',
  chartGrid:    'var(--chart-grid)',
  inputBg:      'var(--input-bg)',
  // Accents — same in both themes
  indigo:  '#818cf8',
  indigoD: '#4f46e5',
  emerald: '#34d399',
  rose:    '#fb7185',
  amber:   '#fbbf24',
  sky:     '#38bdf8',
  violet:  '#c084fc',
  chartPalette: ['#818cf8','#34d399','#fb7185','#fbbf24','#38bdf8','#c084fc','#4ade80','#f97316'],
}

const FONT = "'Inter', system-ui, sans-serif"
const MONO = "'JetBrains Mono', 'Fira Mono', monospace"

const CHANNEL_COLOR: Record<string, string> = {
  'Organic Search': C.emerald,
  'Direct':         C.sky,
  'Referral':       C.violet,
  'Organic Social': C.amber,
  'Paid Search':    C.rose,
  'Paid Social':    C.rose,
  'Email':          C.sky,
  'Display':        C.indigo,
}
const chColor = (ch: string) => CHANNEL_COLOR[ch] ?? C.indigo

/* ─── Global CSS + theme vars ────────────────────────────────────────────── */
const GLOBAL_CSS = `
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #09090f; --surface: #0f1117; --card: #13161f; --card-hov: #181c28;
  --border: rgba(255,255,255,0.065); --border-hov: rgba(255,255,255,0.13);
  --border-subtle: rgba(255,255,255,0.032);
  --text: #f1f5f9; --muted: #7c8799; --faint: #343a4d;
  --faint-a: rgba(52,58,77,0.5); --chart-grid: rgba(255,255,255,0.04);
  --input-bg: #0f1117; --scrollbar-thumb: #343a4d;
}
:root.light {
  --bg: #f1f5f9; --surface: #ffffff; --card: #ffffff; --card-hov: #f8fafc;
  --border: rgba(0,0,0,0.08); --border-hov: rgba(0,0,0,0.16);
  --border-subtle: rgba(0,0,0,0.04);
  --text: #0f172a; --muted: #64748b; --faint: #e2e8f0;
  --faint-a: rgba(226,232,240,0.8); --chart-grid: rgba(0,0,0,0.04);
  --input-bg: #f8fafc; --scrollbar-thumb: #cbd5e1;
}
body { background: var(--bg); color: var(--text); font-family: ${FONT}; transition: background 0.2s, color 0.2s; }
@keyframes fadeUp  { from{opacity:0;transform:translateY(10px);}to{opacity:1;transform:none;} }
@keyframes spin    { to{transform:rotate(360deg);} }
@keyframes shimmer { 0%{background-position:-400px 0;}100%{background-position:400px 0;} }
.fade-up { animation: fadeUp 0.28s ease both; }
.spin    { animation: spin 0.9s linear infinite; }
.card-hover { transition: border-color 0.15s, background 0.15s; }
.card-hover:hover { border-color: var(--border-hov) !important; background: var(--card-hov) !important; }
input, select { background: var(--input-bg); color: var(--text); transition: background 0.2s, color 0.2s; }
scrollbar-width: thin; scrollbar-color: var(--scrollbar-thumb) transparent;
`

/* ─── Date helpers ───────────────────────────────────────────────────────── */
type PType = 'daily'|'weekly'|'monthly'|'custom'
const encodeCustom = (s: string, e: string) => `${s}..${e}`
const decodeCustom = (p: string) => { const [s,e]=(p||'').split('..'); return {start:s||'',end:e||''} }
const defaultParam = (p: PType): string => {
  const y = subDays(new Date(),1)
  if (p==='daily')   return format(y,'yyyy-MM-dd')
  if (p==='weekly')  return format(startOfWeek(y,{weekStartsOn:1}),'yyyy-MM-dd')
  if (p==='monthly') return format(startOfMonth(y),'yyyy-MM')
  return encodeCustom(format(subDays(y,29),'yyyy-MM-dd'),format(y,'yyyy-MM-dd'))
}
const nextParam = (p: PType, v: string): string => {
  if (p==='custom') { const {start,end}=decodeCustom(v); const len=Math.round((new Date(end).getTime()-new Date(start).getTime())/86400000)+1; return encodeCustom(format(addDays(new Date(start),len),'yyyy-MM-dd'),format(addDays(new Date(end),len),'yyyy-MM-dd')) }
  const d=new Date(v)
  if (p==='daily')  return format(addDays(d,1),'yyyy-MM-dd')
  if (p==='weekly') return format(addWeeks(d,1),'yyyy-MM-dd')
  return format(addMonths(d,1),'yyyy-MM')
}
const prevParam = (p: PType, v: string): string => {
  if (p==='custom') { const {start,end}=decodeCustom(v); const len=Math.round((new Date(end).getTime()-new Date(start).getTime())/86400000)+1; return encodeCustom(format(subDays(new Date(start),len),'yyyy-MM-dd'),format(subDays(new Date(end),len),'yyyy-MM-dd')) }
  const d=new Date(v)
  if (p==='daily')  return format(subDays(d,1),'yyyy-MM-dd')
  if (p==='weekly') return format(subWeeks(d,1),'yyyy-MM-dd')
  return format(subMonths(d,1),'yyyy-MM')
}
const paramLabel = (p: PType, v: string): string => {
  if (p==='daily')   return format(new Date(v),'EEE d MMM yyyy')
  if (p==='weekly')  { const d=new Date(v); return `${format(d,'d MMM')} – ${format(addDays(d,6),'d MMM yyyy')}` }
  if (p==='monthly') return format(new Date(v+'-01'),'MMMM yyyy')
  const {start,end}=decodeCustom(v)
  return !start||!end?'Custom':`${format(new Date(start),'d MMM')} – ${format(new Date(end),'d MMM yyyy')}`
}
const isFuture = (p: PType, v: string): boolean => {
  const t=new Date()
  if (p==='daily')   return new Date(v)>=t
  if (p==='weekly')  return addWeeks(new Date(v),1)>t
  if (p==='monthly') { const [y,m]=v.split('-').map(Number); return y>t.getFullYear()||(y===t.getFullYear()&&m>=t.getMonth()+1) }
  const {end}=decodeCustom(v); return !end||new Date(end)>=t
}

/* ─── Formatters ─────────────────────────────────────────────────────────── */
const fN   = (v: number) => (v??0).toLocaleString()
const fP   = (v: number) => `${(v??0).toFixed(1)}%`
const fDur = (s: number) => { const v=Math.round(s??0); if(v<60) return `${v}s`; const m=Math.floor(v/60),r=v%60; return r?`${m}m ${r}s`:`${m}m` }
const fGBP = (v: number) => `£${(v??0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`

/* ─── Animated counter ───────────────────────────────────────────────────── */
function AnimNum({ to, fmt=fN, dur=900 }: { to: number; fmt?: (n:number)=>string; dur?: number }) {
  const [val, setVal] = useState(0)
  const raf = useRef<number|null>(null)
  useEffect(() => {
    const s = performance.now()
    const tick = (now: number) => {
      const p = Math.min((now-s)/dur, 1)
      setVal((1-Math.pow(1-p,3))*to)
      if (p<1) raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => { if(raf.current) cancelAnimationFrame(raf.current) }
  }, [to, dur])
  return <>{fmt(val)}</>
}

/* ─── Skeleton ───────────────────────────────────────────────────────────── */
const Skel = ({ w='100%', h=14 }: { w?: string|number; h?: number }) => (
  <div style={{ width:w, height:h, borderRadius:6, background:`linear-gradient(90deg, var(--card) 25%, var(--card-hov) 50%, var(--card) 75%)`, backgroundSize:'400px 100%', animation:'shimmer 1.4s infinite' }} />
)

/* ─── Sparkline ──────────────────────────────────────────────────────────── */
function Sparkline({ data, dataKey, color }: { data: any[]; dataKey: string; color: string }) {
  if (!data?.length) return null
  return (
    <ResponsiveContainer width="100%" height={44}>
      <LineChart data={data} margin={{ top:4, right:2, bottom:2, left:2 }}>
        <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={1.8} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

/* ─── KPI card ───────────────────────────────────────────────────────────── */
function KpiCard({ label, value, fmt=fN, sub, insight, color, sparkData, sparkKey, loading }: {
  label: string; value: number; fmt?: (n:number)=>string; sub?: string
  insight?: string; color: string; sparkData?: any[]; sparkKey?: string; loading?: boolean
}) {
  return (
    <div className="card-hover" style={{ background:C.card, border:`1px solid ${C.border}`, borderRadius:14, padding:'20px 22px', display:'flex', flexDirection:'column', gap:6 }}>
      <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.1em', textTransform:'uppercase', color:C.muted }}>{label}</div>
      <div style={{ fontSize:30, fontWeight:800, fontFamily:MONO, letterSpacing:'-1.5px', color:C.text, lineHeight:1 }}>
        {loading ? <Skel w="55%" h={26} /> : <AnimNum to={value} fmt={fmt} />}
      </div>
      {sub && <div style={{ fontSize:11, color:C.muted, fontFamily:MONO }}>{sub}</div>}
      {sparkData && sparkKey && !loading && (
        <div style={{ marginTop:2, opacity:0.7 }}>
          <Sparkline data={sparkData} dataKey={sparkKey} color={color} />
        </div>
      )}
      {insight && !loading && (
        <div style={{ fontSize:11, color, borderLeft:`2px solid ${color}40`, paddingLeft:8, marginTop:4, lineHeight:1.55 }}>
          {insight}
        </div>
      )}
    </div>
  )
}

/* ─── Insight callout card ───────────────────────────────────────────────── */
interface Insight { icon: string; title: string; body: string; color: string; tab?: string }

function InsightCard({ ins, onNav }: { ins: Insight; onNav?: (t:string)=>void }) {
  return (
    <div className="card-hover" onClick={() => ins.tab && onNav?.(ins.tab)}
      style={{ background:C.card, border:`1px solid ${C.border}`, borderRadius:12, padding:'16px 18px', cursor:ins.tab?'pointer':'default', borderLeft:`3px solid ${ins.color}` }}>
      <div style={{ display:'flex', alignItems:'flex-start', gap:10 }}>
        <span style={{ fontSize:18, flexShrink:0, lineHeight:1, marginTop:1 }}>{ins.icon}</span>
        <div>
          <div style={{ fontSize:12, fontWeight:700, color:C.text, marginBottom:5 }}>{ins.title}</div>
          <div style={{ fontSize:11, color:C.muted, lineHeight:1.6 }}>{ins.body}</div>
          {ins.tab && <div style={{ fontSize:10, color:ins.color, fontWeight:600, marginTop:6 }}>View {ins.tab} →</div>}
        </div>
      </div>
    </div>
  )
}

/* ─── Horizontal bar ─────────────────────────────────────────────────────── */
function HBar({ label, value, max, color=C.indigo, sub, pctLabel, rank }: {
  label: string; value: number; max: number; color?: string; sub?: string; pctLabel?: string; rank?: number
}) {
  const fill = max>0 ? Math.max(2,(value/max)*100) : 0
  return (
    <div style={{ marginBottom:11 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:4 }}>
        <div style={{ fontSize:12, color:rank===0?C.text:C.muted, fontWeight:rank===0?600:400, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', flex:1, minWidth:0, marginRight:8 }}>
          {rank!==undefined && <span style={{ fontFamily:MONO, fontSize:10, color:C.faint, marginRight:6 }}>{String((rank??0)+1).padStart(2,'0')}</span>}
          {label}
          {sub && <span style={{ fontSize:10, color:C.faint, fontFamily:MONO, marginLeft:5 }}>{sub}</span>}
        </div>
        <div style={{ display:'flex', gap:8, flexShrink:0 }}>
          {pctLabel && <span style={{ fontSize:10, fontFamily:MONO, color:color, fontWeight:600 }}>{pctLabel}</span>}
          <span style={{ fontSize:11, fontFamily:MONO, fontWeight:600, color:C.text }}>{fN(value)}</span>
        </div>
      </div>
      <div style={{ height:5, background:C.faintA, borderRadius:99 }}>
        <div style={{ height:'100%', width:`${fill}%`, background:color, borderRadius:99, transition:'width 0.6s ease' }} />
      </div>
    </div>
  )
}

/* ─── Chart tooltip ──────────────────────────────────────────────────────── */
const CTip = ({ active, payload, label }: { active?: boolean; payload?: any[]; label?: string }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:8, padding:'10px 14px', fontFamily:MONO, fontSize:11 }}>
      <div style={{ color:C.muted, marginBottom:4 }}>{label}</div>
      {payload.map((p:any,i:number) => (
        <div key={i} style={{ color:p.color||C.text, fontWeight:600 }}>{p.name}: {typeof p.value==='number'&&p.value>100?fN(p.value):`${p.value}`}</div>
      ))}
    </div>
  )
}

/* ─── Section header ─────────────────────────────────────────────────────── */
const SH = ({ label, title, sub }: { label: string; title: string; sub?: string }) => (
  <div style={{ marginBottom:18 }}>
    <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.1em', textTransform:'uppercase', color:C.muted, marginBottom:4 }}>{label}</div>
    <div style={{ fontSize:15, fontWeight:700, color:C.text }}>{title}</div>
    {sub && <div style={{ fontSize:11, color:C.faint, fontFamily:MONO, marginTop:3 }}>{sub}</div>}
  </div>
)

const Divider = () => <div style={{ borderTop:`1px solid ${C.border}`, margin:'18px 0' }} />

const Card = ({ children, style={} }: { children: React.ReactNode; style?: React.CSSProperties }) => (
  <div className="card-hover" style={{ background:C.card, border:`1px solid ${C.border}`, borderRadius:14, padding:'22px 24px', ...style }}>
    {children}
  </div>
)

/* ─── Score badge ─────────────────────────────────────────────────────────── */
function ScoreBadge({ score, max=100 }: { score: number; max?: number }) {
  const pct = (score/max)*100
  const color = pct>=70?C.emerald:pct>=45?C.amber:C.rose
  return (
    <div style={{ display:'flex', alignItems:'center', gap:8 }}>
      <div style={{ width:48, height:48, borderRadius:'50%', border:`3px solid ${color}`, display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
        <span style={{ fontSize:14, fontWeight:800, fontFamily:MONO, color }}>{Math.round(score)}</span>
      </div>
      <div style={{ flex:1, height:6, background:C.faintA, borderRadius:99 }}>
        <div style={{ height:'100%', width:`${pct}%`, background:color, borderRadius:99, transition:'width 0.8s ease' }} />
      </div>
    </div>
  )
}

/* ─── Info tooltip ────────────────────────────────────────────────────────── */
function InfoTip({ text }: { text: string }) {
  const [show, setShow] = useState(false)
  return (
    <span style={{ position:'relative', display:'inline-flex' }}
      onMouseEnter={()=>setShow(true)} onMouseLeave={()=>setShow(false)}>
      <Info size={11} style={{ color:C.faint, cursor:'help' }} />
      {show && (
        <div style={{ position:'absolute', bottom:'calc(100% + 6px)', left:'50%', transform:'translateX(-50%)', background:C.surface, border:`1px solid ${C.border}`, borderRadius:7, padding:'8px 10px', fontSize:10, color:C.muted, zIndex:99, maxWidth:220, lineHeight:1.5, boxShadow:`0 4px 16px rgba(0,0,0,0.3)` }}>
          {text}
        </div>
      )}
    </span>
  )
}

/* ─── Build insight callouts ─────────────────────────────────────────────── */
function buildInsights(data: AnalyticsResponse): Insight[] {
  const ins: Insight[] = []
  const { kpis, traffic, pages, referrers, new_vs_returning } = data
  const totalSess = traffic.reduce((s,t)=>s+t.sessions,0) || 1

  const ret = new_vs_returning?.find(r=>r.segment==='returning')
  const nw  = new_vs_returning?.find(r=>r.segment==='new')
  if (ret && nw && nw.avg_duration_secs > 0) {
    const ratio = Math.round(ret.avg_duration_secs / nw.avg_duration_secs)
    if (ratio >= 2) ins.push({ icon:'⭐', title:`Returning visitors stay ${ratio}× longer`, body:`Returning visitors spend ${fDur(ret.avg_duration_secs)}/session vs ${fDur(nw.avg_duration_secs)} for new visitors. Grow this loyal audience with email newsletters and event reminders.`, color:C.emerald, tab:'audience' })
  }

  const direct = traffic?.find(t=>t.channel==='Direct')
  if (direct && kpis.sessions > 0) {
    const pct = Math.round(direct.sessions/kpis.sessions*100)
    if (pct > 35) ins.push({ icon:'🔍', title:`${pct}% of traffic is untracked`, body:`"Direct" means visitors from emails, WhatsApp shares, or links without UTM parameters. Add ?utm_source= to all your emails and social posts to see what's actually driving visits.`, color:C.amber, tab:'traffic' })
  }

  const linkedinAll = referrers?.filter(r=>r.referrer.includes('linkedin')||r.referrer.includes('lnkd')).reduce((s,r)=>s+r.sessions,0)??0
  if (linkedinAll > 0) {
    ins.push({ icon:'💼', title:'LinkedIn is your top social referrer', body:`LinkedIn drove ${fN(linkedinAll)} sessions. This high-intent audience is researching events. Post more regularly to grow this channel.`, color:C.indigo, tab:'traffic' })
  }

  if (kpis.bounce_rate > 55 && kpis.sessions > 50) {
    ins.push({ icon:'⚠️', title:`${fP(kpis.bounce_rate)} bounce rate needs attention`, body:`More than half of visitors leave without interacting. For event sites, 40–55% is typical. Improve the homepage CTA and make upcoming events more visible above the fold.`, color:C.rose, tab:'content' })
  }

  const pitchPage = pages?.find(p=>p.page_path?.includes('pitch-my-idea')&&!p.page_path?.includes('apply'))
  if (pitchPage && pitchPage.views > 50) {
    const applyPage = pages?.find(p=>p.page_path?.includes('apply'))
    const dropOff = applyPage ? Math.round(100-(applyPage.views/pitchPage.views)*100) : null
    ins.push({ icon:'🚀', title:`Pitch My Idea is your strongest event page`, body:`${fN(pitchPage.views)} views.${dropOff!==null?` Only ${fN(applyPage!.views)} clicked through to apply — ${dropOff}% drop-off. Make the "Apply" CTA more prominent.`:' Strong interest signal.'}`, color:C.sky, tab:'content' })
  }

  const stripe = referrers?.find(r=>r.referrer==='checkout.stripe.com')
  if (stripe) {
    ins.push({ icon:'💳', title:`${fN(stripe.sessions)} ticket buyers returning via Stripe`, body:`checkout.stripe.com sends ${fN(stripe.sessions)} sessions — these are active purchasers. Add a post-payment redirect to a "What to expect" confirmation page.`, color:C.emerald, tab:'traffic' })
  }

  const topChannel = traffic[0]
  if (topChannel && (topChannel.sessions/totalSess) > 0.55) {
    ins.push({ icon:'⚡', title:`${topChannel.channel} drives ${Math.round(topChannel.sessions/totalSess*100)}% of traffic`, body:`High dependency on a single channel is risky. If ${topChannel.channel} drops, so does your traffic. Diversify by growing email, LinkedIn, and organic search.`, color:C.amber, tab:'traffic' })
  }

  return ins.slice(0, 5)
}

/* ─── Tabs ───────────────────────────────────────────────────────────────── */
const TABS = [
  { id:'overview',   label:'Overview'   },
  { id:'traffic',    label:'Traffic'    },
  { id:'content',    label:'Content'    },
  { id:'audience',   label:'Audience'   },
  { id:'timing',     label:'Timing'     },
  { id:'financial',  label:'Financial'  },
  { id:'insights',   label:'Insights'   },
] as const
type TabId = typeof TABS[number]['id']

/* ─── Empty state ────────────────────────────────────────────────────────── */
const EMPTY_KPIS  = { sessions:0, users:0, new_users:0, returning_users:0, pageviews:0, pages_per_session:0, avg_session_duration_secs:0, bounce_rate:0, engagement_rate:0 }
const EMPTY_REV   = { total_revenue:0, purchase_revenue:0, purchases:0, transactions:0, conversions:0 }
const EMPTY_LEADS = { leads:0, users:0 }
const EMPTY: AnalyticsResponse = { period:'daily', label:'', dates_in_range:[], dates_with_data:[], kpis:EMPTY_KPIS, time_series:[], traffic:[], pages:[], device:[], cities:[], utm:[], events:[], landing_pages:[], browsers:[], countries:[], referrers:[], search_terms:[], new_vs_returning:[], revenue:EMPTY_REV, revenue_series:[], leads:EMPTY_LEADS, lead_attribution:[], lead_geo:[], lead_devices:[] }

/* ═══════════════════════════════════════════════════════════════════════════
   MARKETING CALCULATOR (self-contained, multi-platform)
═══════════════════════════════════════════════════════════════════════════ */
type PlatformId = 'google'|'meta'|'linkedin'|'other'
const PLATFORMS: { id: PlatformId; label: string; color: string }[] = [
  { id:'google',   label:'Google Ads',   color:'#4285F4' },
  { id:'meta',     label:'Meta Ads',     color:'#0866FF' },
  { id:'linkedin', label:'LinkedIn Ads', color:'#0A66C2' },
  { id:'other',    label:'Other',        color:C.violet  },
]
interface PlatformInputs { spend: string; impressions: string; clicks: string; leads: string; revenue: string }
const EMPTY_PLATFORM_INPUTS: PlatformInputs = { spend:'', impressions:'', clicks:'', leads:'', revenue:'' }
const STORAGE_KEY = 'marketing_calc_inputs_v1'

function loadPlatformInputs(): Record<PlatformId, PlatformInputs> {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      return { google:{...EMPTY_PLATFORM_INPUTS,...parsed.google}, meta:{...EMPTY_PLATFORM_INPUTS,...parsed.meta}, linkedin:{...EMPTY_PLATFORM_INPUTS,...parsed.linkedin}, other:{...EMPTY_PLATFORM_INPUTS,...parsed.other} }
    }
  } catch {}
  return { google:{...EMPTY_PLATFORM_INPUTS}, meta:{...EMPTY_PLATFORM_INPUTS}, linkedin:{...EMPTY_PLATFORM_INPUTS}, other:{...EMPTY_PLATFORM_INPUTS} }
}

function computePlatformMetrics(inp: PlatformInputs, sessions: number, conversions: number, autoLeads: number) {
  const spend       = parseFloat(inp.spend)       || 0
  const impressions = parseFloat(inp.impressions) || 0
  const clicks       = parseFloat(inp.clicks)      || 0
  const rev          = parseFloat(inp.revenue)     || 0
  const leadCnt       = parseFloat(inp.leads)       || autoLeads

  return {
    spend, impressions, clicks, revenue: rev, leads: leadCnt,
    ctr:         impressions>0 && clicks>0 ? (clicks/impressions)*100 : null,
    cpc:         clicks>0 && spend>0       ? spend/clicks              : null,
    cpm:         impressions>0 && spend>0  ? (spend/impressions)*1000  : null,
    cps:         sessions>0 && spend>0     ? spend/sessions            : null,
    cpl:         leadCnt>0 && spend>0       ? spend/leadCnt             : null,
    cac:         conversions>0 && spend>0  ? spend/conversions         : null,
    clickToLead: clicks>0 && leadCnt>0      ? (leadCnt/clicks)*100      : null,
    roas:        spend>0 && rev>0          ? rev/spend                 : null,
    roi:         spend>0 && rev>0          ? ((rev-spend)/spend)*100   : null,
    cvr:         sessions>0 && conversions>0 ? (conversions/sessions)*100 : null,
  }
}

function MarketingCalculator({ sessions, conversions, newUsers, autoLeads }: { sessions: number; conversions: number; newUsers: number; autoLeads: number }) {
  const [platform, setPlatform] = useState<PlatformId>('google')
  const [allInputs, setAllInputs] = useState<Record<PlatformId, PlatformInputs>>(loadPlatformInputs)

  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(allInputs)) }, [allInputs])

  const cur = allInputs[platform]
  const setField = (field: keyof PlatformInputs, value: string) =>
    setAllInputs(prev => ({ ...prev, [platform]: { ...prev[platform], [field]: value } }))

  const leadDefault = autoLeads || newUsers
  const m = computePlatformMetrics(cur, sessions, conversions, leadDefault)
  const activePlatform = PLATFORMS.find(p=>p.id===platform)!

  const inp: React.CSSProperties = { width:'100%', padding:'9px 12px', borderRadius:8, border:`1px solid ${C.border}`, background:C.inputBg, color:C.text, fontSize:13, fontFamily:MONO, outline:'none' }
  const field = (label: string, value: string, onChange: (v:string)=>void, placeholder: string) => (
    <div>
      <div style={{ fontSize:10, color:C.muted, fontWeight:600, marginBottom:6, textTransform:'uppercase', letterSpacing:'0.08em' }}>{label}</div>
      <input style={inp} type="number" placeholder={placeholder} value={value} onChange={e=>onChange(e.target.value)} />
    </div>
  )
  const metricRow = (label: string, val: number|null, fmt: (n:number)=>string, color: string, tip: string) => (
    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'9px 0', borderBottom:`1px solid ${C.borderSubtle}` }}>
      <div style={{ display:'flex', alignItems:'center', gap:5 }}>
        <span style={{ fontSize:12, color:C.muted }}>{label}</span>
        <InfoTip text={tip} />
      </div>
      <span style={{ fontSize:14, fontWeight:700, fontFamily:MONO, color: val!==null?color:C.faint }}>
        {val!==null ? fmt(val) : '—'}
      </span>
    </div>
  )

  // Comparison across all platforms that have spend entered
  const comparison = PLATFORMS
    .map(p => ({ ...p, m: computePlatformMetrics(allInputs[p.id], sessions, conversions, leadDefault) }))
    .filter(p => p.m.spend > 0)

  return (
    <Card>
      <SH label="Performance calculator" title="Marketing ROI" sub="Select a platform, enter campaign numbers, and see calculated performance"/>

      {/* Platform selector */}
      <div style={{ display:'flex', gap:6, marginBottom:18, flexWrap:'wrap' }}>
        {PLATFORMS.map(p=>(
          <button key={p.id} onClick={()=>setPlatform(p.id)}
            style={{ display:'flex', alignItems:'center', gap:6, padding:'7px 14px', borderRadius:8, fontSize:12, fontWeight:600, fontFamily:FONT, cursor:'pointer',
              border:`1px solid ${platform===p.id?p.color:C.border}`, background:platform===p.id?`${p.color}18`:'transparent', color:platform===p.id?p.color:C.muted }}>
            <span style={{ width:7, height:7, borderRadius:'50%', background:p.color, flexShrink:0 }}/>
            {p.label}
            {allInputs[p.id].spend && parseFloat(allInputs[p.id].spend)>0 && <span style={{ fontSize:9, opacity:0.7 }}>●</span>}
          </button>
        ))}
      </div>

      {/* Inputs */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(5,1fr)', gap:10, marginBottom:20 }}>
        {field('Ad Spend (£)',   cur.spend,       v=>setField('spend',v),       'e.g. 500')}
        {field('Impressions',    cur.impressions, v=>setField('impressions',v), 'e.g. 50000')}
        {field('Clicks',         cur.clicks,      v=>setField('clicks',v),      'e.g. 800')}
        {field('Leads (auto-fill)', cur.leads,    v=>setField('leads',v),       String(leadDefault))}
        {field('Revenue (£)',    cur.revenue,     v=>setField('revenue',v),     'e.g. 2000')}
      </div>

      {/* Calculated metrics */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:14 }}>
        <div>
          <div style={{ fontSize:11, fontWeight:600, color:C.text, marginBottom:2 }}>Reach & Clicks</div>
          {metricRow('CTR', m.ctr, v=>`${v.toFixed(2)}%`, m.ctr&&m.ctr>2?C.emerald:C.amber, 'Clicks ÷ impressions × 100. Industry benchmark for search/social ads is 1–3%.')}
          {metricRow('CPC', m.cpc, v=>`£${v.toFixed(2)}`, C.sky, 'Ad spend ÷ clicks. Average cost for one click on your ad.')}
          {metricRow('CPM', m.cpm, v=>`£${v.toFixed(2)}`, C.indigo, 'Ad spend ÷ impressions × 1000. Cost to show your ad 1,000 times.')}
        </div>
        <div>
          <div style={{ fontSize:11, fontWeight:600, color:C.text, marginBottom:2 }}>Cost metrics</div>
          {metricRow('Cost per Session', m.cps, v=>`£${v.toFixed(2)}`, C.sky, 'Ad spend ÷ total GA4 sessions. How much does it cost to get one visit?')}
          {metricRow('Cost per Lead (CPL)', m.cpl, v=>`£${v.toFixed(2)}`, C.violet, 'Ad spend ÷ leads. Defaults to GA4 generate_lead count, overridable above.')}
          {metricRow('Cost per Acquisition (CAC)', m.cac, v=>`£${v.toFixed(2)}`, C.amber, 'Ad spend ÷ conversions. The actual cost to acquire one paying customer.')}
        </div>
        <div>
          <div style={{ fontSize:11, fontWeight:600, color:C.text, marginBottom:2 }}>Return metrics</div>
          {metricRow('Click → Lead Rate', m.clickToLead, v=>`${v.toFixed(1)}%`, m.clickToLead&&m.clickToLead>10?C.emerald:C.amber, 'Leads ÷ clicks × 100. Measures landing page effectiveness after the click.')}
          {metricRow('ROAS', m.roas, v=>`${v.toFixed(2)}×`, m.roas&&m.roas>=2?C.emerald:C.rose, 'Revenue ÷ ad spend. A ROAS of 3× means £3 returned for every £1 spent. Aim for 3–5× for events.')}
          {metricRow('ROI', m.roi, v=>`${v.toFixed(1)}%`, m.roi&&m.roi>=0?C.emerald:C.rose, '(Revenue − Spend) ÷ Spend × 100. Positive = profitable campaign.')}
        </div>
      </div>

      {m.spend>0 && m.roas===null && (
        <div style={{ marginTop:14, fontSize:11, color:C.amber, borderLeft:`2px solid ${C.amber}40`, paddingLeft:10, lineHeight:1.6 }}>
          Enter Revenue to calculate ROAS and ROI for {activePlatform.label}.
        </div>
      )}

      {/* Cross-platform comparison */}
      {comparison.length > 1 && (
        <>
          <Divider/>
          <div style={{ fontSize:11, fontWeight:600, color:C.text, marginBottom:10 }}>Platform Comparison</div>
          <div style={{ overflowX:'auto' }}>
            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
              <thead>
                <tr style={{ borderBottom:`1px solid ${C.border}` }}>
                  {['Platform','Spend','Clicks','CTR','CPC','Leads','CPL','ROAS'].map((h,i)=>(
                    <th key={h} style={{ padding:'7px 8px', textAlign:i>0?'right':'left', fontFamily:MONO, fontSize:9, fontWeight:600, color:C.faint, textTransform:'uppercase', letterSpacing:'0.06em' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {comparison.map(p=>(
                  <tr key={p.id} style={{ borderBottom:`1px solid ${C.borderSubtle}` }}>
                    <td style={{ padding:'8px', display:'flex', alignItems:'center', gap:6 }}>
                      <span style={{ width:7, height:7, borderRadius:'50%', background:p.color }}/>
                      <span style={{ color:C.text, fontWeight:600 }}>{p.label}</span>
                    </td>
                    <td style={{ padding:'8px', textAlign:'right', fontFamily:MONO, color:C.text }}>£{p.m.spend.toFixed(0)}</td>
                    <td style={{ padding:'8px', textAlign:'right', fontFamily:MONO, color:C.muted }}>{fN(p.m.clicks)}</td>
                    <td style={{ padding:'8px', textAlign:'right', fontFamily:MONO, color:C.muted }}>{p.m.ctr!==null?`${p.m.ctr.toFixed(1)}%`:'—'}</td>
                    <td style={{ padding:'8px', textAlign:'right', fontFamily:MONO, color:C.muted }}>{p.m.cpc!==null?`£${p.m.cpc.toFixed(2)}`:'—'}</td>
                    <td style={{ padding:'8px', textAlign:'right', fontFamily:MONO, color:C.muted }}>{fN(p.m.leads)}</td>
                    <td style={{ padding:'8px', textAlign:'right', fontFamily:MONO, color:C.muted }}>{p.m.cpl!==null?`£${p.m.cpl.toFixed(2)}`:'—'}</td>
                    <td style={{ padding:'8px', textAlign:'right', fontFamily:MONO, fontWeight:700, color: p.m.roas!==null ? (p.m.roas>=2?C.emerald:C.rose) : C.faint }}>{p.m.roas!==null?`${p.m.roas.toFixed(2)}×`:'—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   App
═══════════════════════════════════════════════════════════════════════════ */
export default function App() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn)

  if (!loggedIn) {
    return <LoginPage onLogin={() => setLoggedIn(true)} />
  }

  return <Dashboard />
}

function Dashboard() {
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem('theme')
    if (saved === 'light') { document.documentElement.className = 'light'; return false }
    return true
  })
  const [period, setPeriod]   = useState<PType>('monthly')
  const [param, setParam]     = useState(() => defaultParam('monthly'))
  const [data, setData]       = useState<AnalyticsResponse>(EMPTY)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string|null>(null)
  const [tab, setTab]         = useState<TabId>('overview')
  const [lastRun, setLastRun] = useState<any>(null)
  const [triggering, setTrig] = useState(false)
  const [accounts, setAccts]  = useState<AccountSummary[]>([])
  const [curAcct, setCurAcct] = useState<string|null>(() => localStorage.getItem('analytics_account'))

  const toggleTheme = () => {
    const next = isDark ? 'light' : 'dark'
    setIsDark(!isDark)
    document.documentElement.className = next === 'light' ? 'light' : ''
    localStorage.setItem('theme', next)
  }

  useEffect(() => {
    fetchAccounts().then(list => {
      setAccts(list)
      if (list.length) {
        const saved = localStorage.getItem('analytics_account')
        const slug  = list.find(a=>a.slug===saved)?.slug ?? list[0].slug
        setCurAcct(slug); setCurrentAccount(slug); localStorage.setItem('analytics_account', slug)
      }
    }).catch(()=>{})
  }, [])

  useEffect(() => {
    if (!curAcct && accounts.length > 0) return
    if (period === 'custom') { const {start,end} = decodeCustom(param); if (!start||!end) return }
    setLoading(true); setError(null)
    fetchAnalytics(period as Period, param)
      .then(d => setData({ ...EMPTY, ...d, revenue: d.revenue ?? EMPTY_REV, revenue_series: d.revenue_series ?? [], leads: d.leads ?? EMPTY_LEADS, lead_attribution: d.lead_attribution ?? [], lead_geo: d.lead_geo ?? [], lead_devices: d.lead_devices ?? [] }))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [period, param, curAcct, accounts.length])

  useEffect(() => { fetchRunLog(1).then(r => setLastRun(r.runs[0] ?? null)).catch(() => {}) }, [])

  const changePeriod = useCallback((p: PType) => { setPeriod(p); setParam(defaultParam(p)) }, [])

  const handleFetch = async () => {
    if (triggering) return
    setTrig(true)
    try {
      const target = period === 'daily' ? param : format(subDays(new Date(), 1), 'yyyy-MM-dd')
      await triggerFetch(target)
      setTimeout(() => { fetchRunLog(1).then(r => setLastRun(r.runs[0] ?? null)); setTrig(false) }, 3000)
    } catch { setTrig(false) }
  }

  const { kpis, time_series, traffic, pages, device, cities, utm, events,
    landing_pages, browsers, countries, referrers, revenue, revenue_series,
    leads, lead_attribution, lead_geo } = data
  const noData    = !loading && !error && data.dates_with_data?.length === 0
  const acctName  = accounts.find(a => a.slug === curAcct)?.name ?? 'Analytics'
  const acctUrl   = accounts.find(a => a.slug === curAcct)?.website ?? ''
  const insights  = !loading && kpis.sessions > 0 ? buildInsights(data) : []
  const totalSess = traffic.reduce((s,t) => s+t.sessions, 0) || 1
  const peakHour  = [...time_series].sort((a,b) => (b.sessions||0) - (a.sessions||0))[0]

  // ── Derived Insights tab data ──────────────────────────────────────────
  const funnelPages = (() => {
    if (!pages.length) return []
    const home    = pages.find(p=>p.page_path==='/'||p.page_path.endsWith('/home')) ?? pages[0]
    const events  = pages.find(p=>p.page_path.includes('event')||p.page_path.includes('agenda'))
    const tickets = pages.find(p=>p.page_path.includes('ticket')||p.page_path.includes('register')||p.page_path.includes('get-'))
    const apply   = pages.find(p=>p.page_path.includes('apply')||p.page_path.includes('purchase'))
    return [home, events, tickets, apply].filter(Boolean).map((p,i,arr) => ({
      name:    p!.page_title || p!.page_path,
      path:    p!.page_path,
      value:   p!.views,
      dropOff: i > 0 ? Math.round(100 - (p!.views / arr[i-1]!.views) * 100) : 0,
      fill:    C.chartPalette[i],
    }))
  })()

  const qualityMatrix = traffic.filter(t => t.sessions > 0).map(t => ({
    name:     t.channel,
    sessions: t.sessions,
    quality:  Math.round(((t as any).engagement_rate_pct ?? 40)),
    fill:     chColor(t.channel),
  }))

  const healthScore = (() => {
    if (!kpis.sessions) return { score: 0, components: [] }
    const engScore  = Math.min(kpis.engagement_rate, 100)
    const durScore  = Math.min((kpis.avg_session_duration_secs / 180) * 100, 100)
    const depthScore = Math.min((kpis.pages_per_session / 3) * 100, 100)
    const retScore  = kpis.users > 0 ? Math.min((kpis.returning_users / kpis.users) * 200, 100) : 50
    const score = Math.round(engScore * 0.35 + durScore * 0.25 + depthScore * 0.2 + retScore * 0.2)
    return {
      score,
      components: [
        { label:'Engagement rate', val:fP(kpis.engagement_rate), score:engScore, tip:'% of sessions 10s+ or 2+ pages' },
        { label:'Avg session duration', val:fDur(kpis.avg_session_duration_secs), score:durScore, tip:'Scored vs 3-min benchmark' },
        { label:'Pages per session', val:(kpis.pages_per_session??0).toFixed(2), score:depthScore, tip:'Scored vs 3 pages/session benchmark' },
        { label:'Return visitor rate', val:kpis.users>0?fP((kpis.returning_users/kpis.users)*100):'—', score:retScore, tip:'Returning ÷ total users' },
      ],
    }
  })()

  const geoConc = (() => {
    if (!countries.length) return null
    const total = countries.reduce((s,c) => s+c.sessions, 0) || 1
    const top   = countries[0]
    const topPct = Math.round((top.sessions / total) * 100)
    const hhi   = countries.reduce((s,c) => s + Math.pow(c.sessions/total, 2), 0)
    return { topCountry: top.country, topPct, hhi: Math.round(hhi * 100), risk: topPct > 70 ? 'high' : topPct > 50 ? 'medium' : 'low' }
  })()

  const chanDep = (() => {
    if (!traffic.length) return null
    const top    = traffic[0]
    const topPct = Math.round((top.sessions / totalSess) * 100)
    const n      = traffic.length
    return { channel: top.channel, topPct, channelCount: n, risk: topPct > 60 ? 'high' : topPct > 40 ? 'medium' : 'low' }
  })()

  const pageDropOff = pages.slice(0,8).map((p,i,arr) => ({
    path:    p.page_path.length > 30 ? '…'+p.page_path.slice(-28) : p.page_path,
    views:   p.views,
    dropOff: i > 0 ? Math.max(0, Math.round(((arr[i-1].views - p.views) / arr[i-1].views) * 100)) : 0,
  }))

  const riskColor = (r: string) => r==='high'?C.rose:r==='medium'?C.amber:C.emerald

  // ── Styles ─────────────────────────────────────────────────────────────
  const navBtn: React.CSSProperties = { width:30, height:30, display:'flex', alignItems:'center', justifyContent:'center', border:`1px solid ${C.border}`, borderRadius:8, background:'transparent', cursor:'pointer', color:C.muted }
  const dateInp: React.CSSProperties = { fontSize:11, fontFamily:MONO, color:C.muted, padding:'5px 8px', border:`1px solid ${C.border}`, borderRadius:7, background:C.surface, cursor:'pointer', outline:'none' }

  return (
    <div style={{ fontFamily:FONT, background:C.bg, minHeight:'100vh', color:C.text }}>
      <style>{GLOBAL_CSS}</style>

      {/* ═══ TOPBAR ══════════════════════════════════════════════════════════ */}
      <div style={{ background:C.surface, borderBottom:`1px solid ${C.border}`, position:'sticky', top:0, zIndex:100 }}>
        <div style={{ maxWidth:1400, margin:'0 auto', padding:'0 28px' }}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'13px 0 0' }}>
            <div style={{ display:'flex', alignItems:'center', gap:18, flexWrap:'wrap' }}>

              {/* Brand/account */}
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                {accounts.length > 1 ? (
                  <select value={curAcct||''} onChange={e=>{ const s=e.target.value; setCurAcct(s); setCurrentAccount(s); localStorage.setItem('analytics_account',s) }}
                    style={{ fontSize:15, fontWeight:700, color:C.text, fontFamily:FONT, border:'none', background:'transparent', cursor:'pointer', outline:'none' }}>
                    {accounts.map(a=><option key={a.slug} value={a.slug}>{a.name}</option>)}
                  </select>
                ) : <span style={{ fontSize:15, fontWeight:700, color:C.text }}>{acctName}</span>}
                <span style={{ fontSize:9, fontWeight:700, letterSpacing:'0.1em', background:`${C.indigo}20`, color:C.indigo, padding:'2px 8px', borderRadius:4, border:`1px solid ${C.indigo}40` }}>GA4</span>
                {acctUrl && <a href={acctUrl} target="_blank" rel="noreferrer" style={{ color:C.faint, textDecoration:'none' }}><ExternalLink size={11}/></a>}
              </div>

              {/* Period selector */}
              <div style={{ display:'flex', gap:2, background:C.bg, borderRadius:9, padding:3, border:`1px solid ${C.border}` }}>
                {(['daily','weekly','monthly','custom'] as PType[]).map(p=>(
                  <button key={p} onClick={()=>changePeriod(p)}
                    style={{ padding:'5px 11px', fontSize:11, fontWeight:600, fontFamily:FONT, cursor:'pointer', border:'none', borderRadius:6, background:period===p?C.card:'transparent', color:period===p?C.text:C.muted, boxShadow:period===p?`0 1px 4px rgba(0,0,0,0.25)`:'none', transition:'all 0.12s' }}>
                    {p[0].toUpperCase()+p.slice(1)}
                  </button>
                ))}
              </div>

              {/* Date nav */}
              {period === 'custom' ? (() => {
                const {start,end} = decodeCustom(param)
                const today = format(new Date(),'yyyy-MM-dd')
                const set = (s: string, e: string) => setParam(encodeCustom(s, e<s?s:e))
                return (
                  <div style={{ display:'flex', alignItems:'center', gap:5, flexWrap:'wrap' }}>
                    <button onClick={()=>setParam(prevParam(period,param))} style={navBtn}><ChevronLeft size={13}/></button>
                    <input type="date" value={start} max={end||today} onChange={e=>set(e.target.value,end)} style={dateInp}/>
                    <span style={{ color:C.faint, fontSize:11 }}>→</span>
                    <input type="date" value={end} min={start} max={today} onChange={e=>set(start,e.target.value)} style={dateInp}/>
                    <button onClick={()=>setParam(nextParam(period,param))} disabled={isFuture(period,nextParam(period,param))} style={{ ...navBtn, opacity:isFuture(period,nextParam(period,param))?0.3:1 }}><ChevronRight size={13}/></button>
                    <div style={{ display:'flex', gap:3, marginLeft:4 }}>
                      {[{l:'7d',d:7},{l:'30d',d:30},{l:'90d',d:90}].map(p=>(
                        <button key={p.l} onClick={()=>{ const y=subDays(new Date(),1); set(format(subDays(y,p.d-1),'yyyy-MM-dd'),format(y,'yyyy-MM-dd')) }}
                          style={{ padding:'4px 8px', fontSize:10, fontFamily:MONO, fontWeight:600, color:C.muted, background:C.card, border:`1px solid ${C.border}`, borderRadius:5, cursor:'pointer' }}>
                          {p.l}
                        </button>
                      ))}
                    </div>
                  </div>
                )
              })() : (
                <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                  <button onClick={()=>setParam(prevParam(period,param))} style={navBtn}><ChevronLeft size={13}/></button>
                  <span style={{ fontSize:12, fontFamily:MONO, color:C.muted, minWidth:170, textAlign:'center' }}>{paramLabel(period,param)}</span>
                  <button onClick={()=>setParam(nextParam(period,param))} disabled={isFuture(period,nextParam(period,param))} style={{ ...navBtn, opacity:isFuture(period,nextParam(period,param))?0.3:1 }}><ChevronRight size={13}/></button>
                </div>
              )}
            </div>

            {/* Right controls */}
            <div style={{ display:'flex', alignItems:'center', gap:12 }}>
              {!loading && kpis.sessions > 0 && (
                <div style={{ display:'flex', gap:16, paddingRight:12, borderRight:`1px solid ${C.border}` }}>
                  {[
                    { v: fP(kpis.engagement_rate), l:'engaged' },
                    { v: fP(kpis.bounce_rate),     l:'bounce'  },
                    { v: fDur(kpis.avg_session_duration_secs), l:'avg time' },
                  ].map(({v,l})=>(
                    <div key={l} style={{ textAlign:'center' }}>
                      <div style={{ fontSize:12, fontWeight:700, fontFamily:MONO, color:C.text }}>{v}</div>
                      <div style={{ fontSize:9, color:C.faint, textTransform:'uppercase', letterSpacing:'0.07em' }}>{l}</div>
                    </div>
                  ))}
                </div>
              )}
              {loading && <span style={{ fontSize:11, color:C.faint, fontFamily:MONO }}>Loading…</span>}
              {error   && <span style={{ fontSize:11, color:C.rose, display:'flex', alignItems:'center', gap:4 }}><AlertCircle size={11}/>Error</span>}
              {lastRun && (
                <div style={{ display:'flex', alignItems:'center', gap:5 }}>
                  <div style={{ width:6, height:6, borderRadius:'50%', background:lastRun.status==='ok'?C.emerald:lastRun.status==='error'?C.rose:C.amber }}/>
                  <span style={{ fontSize:10, color:C.faint, fontFamily:MONO }}>{lastRun.date}</span>
                </div>
              )}
              {/* Theme toggle */}
              <button onClick={toggleTheme} style={{ ...navBtn, border:`1px solid ${C.border}` }} title={isDark?'Switch to light mode':'Switch to dark mode'}>
                {isDark ? <Sun size={13} /> : <Moon size={13} />}
              </button>
              {/* Sign out */}
              <button onClick={() => { clearToken(); window.location.reload() }}
                style={{ ...navBtn, border:`1px solid ${C.border}`, color:C.muted, fontSize:11 }}
                title="Sign out">
                Sign out
              </button>
              <button onClick={handleFetch} disabled={triggering}
                style={{ display:'flex', alignItems:'center', gap:6, fontSize:11, fontWeight:600, fontFamily:FONT, padding:'7px 14px', borderRadius:8, border:`1px solid ${C.border}`, background:C.card, cursor:'pointer', color:C.muted }}>
                <RefreshCw size={11} className={triggering?'spin':''}/>
                {triggering?'Fetching…':'Sync'}
              </button>
            </div>
          </div>

          {/* Tabs row */}
          <div style={{ display:'flex', gap:0, marginTop:14, overflowX:'auto' }}>
            {TABS.map(t=>(
              <button key={t.id} onClick={()=>setTab(t.id)}
                style={{ padding:'10px 16px', fontSize:12, fontWeight:600, fontFamily:FONT, cursor:'pointer', border:'none', background:'none', color:tab===t.id?C.text:C.muted, borderBottom:`2px solid ${tab===t.id?C.indigo:'transparent'}`, transition:'all 0.12s', whiteSpace:'nowrap' }}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ═══ CONTENT ═════════════════════════════════════════════════════════ */}
      <div style={{ maxWidth:1400, margin:'0 auto', padding:'28px 28px' }}>

        {error && (
          <div style={{ background:`${C.rose}12`, border:`1px solid ${C.rose}30`, borderRadius:12, padding:'16px 20px', marginBottom:24 }}>
            <strong style={{ color:C.rose, fontSize:13 }}>Failed to load — </strong>
            <span style={{ fontSize:12, color:C.muted, fontFamily:MONO }}>{error}</span>
          </div>
        )}
        {noData && !error && (
          <div style={{ background:`${C.amber}10`, border:`1px solid ${C.amber}30`, borderRadius:12, padding:'18px 22px', marginBottom:24 }}>
            <div style={{ fontWeight:600, color:C.amber, fontSize:13, marginBottom:4 }}>No data for this period</div>
            <div style={{ fontSize:12, color:C.muted }}>Use the Sync button or trigger a backfill from the backend.</div>
          </div>
        )}

        {/* ═════════════════════════════════════════════════════════════════
            OVERVIEW
        ═════════════════════════════════════════════════════════════════ */}
        {tab === 'overview' && (
          <div className="fade-up">
            <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:14, marginBottom:22 }}>
              <KpiCard label="Sessions"     value={kpis.sessions}   color={C.indigo} loading={loading}
                sub={`${fN(kpis.users)} unique visitors`} sparkData={time_series} sparkKey="sessions"
                insight={kpis.sessions>0?`~${Math.round(kpis.sessions/(data.dates_in_range?.length||30))}/day`:'—'} />
              <KpiCard label="Pageviews"    value={kpis.pageviews}  color={C.violet} loading={loading}
                sub={`${(kpis.pages_per_session??0).toFixed(2)} pages/session`} sparkData={time_series} sparkKey="pageviews"
                insight={kpis.pages_per_session<1.5?'Add internal links to lift above 2':'Good content depth'} />
              <KpiCard label="Engagement"   value={kpis.engagement_rate} fmt={fP} color={kpis.engagement_rate>50?C.emerald:C.amber} loading={loading}
                sub={`${fP(kpis.bounce_rate)} bounce`}
                insight={kpis.engagement_rate<50?'Below 50% event-site benchmark':'Above 50% benchmark'} />
              <KpiCard label="Avg Duration" value={kpis.avg_session_duration_secs} fmt={fDur} color={C.sky} loading={loading}
                sub={`${fN(kpis.new_users)} new · ${fN(kpis.returning_users)} returning`}
                insight={kpis.avg_session_duration_secs>120?'Visitors reading deeply':'Improve content depth'} />
            </div>

            <div style={{ display:'grid', gridTemplateColumns:'1fr 340px', gap:14, marginBottom:14 }}>
              <Card>
                <SH label="Activity" title="Sessions over time" sub={`${fN(kpis.sessions)} total · ${data.dates_with_data?.length??0} days with data`}/>
                {loading ? <Skel h={190}/> : time_series.length === 0 ? (
                  <div style={{ height:190, display:'flex', alignItems:'center', justifyContent:'center', color:C.faint, fontSize:12, fontFamily:MONO }}>No data yet</div>
                ) : (
                  <ResponsiveContainer width="100%" height={190}>
                    <AreaChart data={time_series} margin={{ top:4, right:4, bottom:0, left:-20 }}>
                      <defs><linearGradient id="g1" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={C.indigo} stopOpacity={0.25}/><stop offset="95%" stopColor={C.indigo} stopOpacity={0.02}/></linearGradient></defs>
                      <CartesianGrid strokeDasharray="3 3" stroke={C.chartGrid}/>
                      <XAxis dataKey="label" tick={{ fontSize:10, fill:C.muted, fontFamily:MONO }} tickLine={false} axisLine={false} interval="preserveStartEnd"/>
                      <YAxis tick={{ fontSize:10, fill:C.muted, fontFamily:MONO }} tickLine={false} axisLine={false}/>
                      <Tooltip content={<CTip/>}/>
                      <Area type="monotone" dataKey="sessions" name="Sessions" stroke={C.indigo} strokeWidth={2} fill="url(#g1)" dot={false}/>
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </Card>
              <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                {loading ? [1,2,3].map(i=><Skel key={i} h={80}/>) : insights.length === 0 ? (
                  <div style={{ color:C.faint, fontSize:12, fontFamily:MONO }}>Fetch data to see insights</div>
                ) : insights.map((ins,i)=><InsightCard key={i} ins={ins} onNav={setTab as (t:string)=>void}/>)}
              </div>
            </div>

            {!loading && traffic.length > 0 && (
              <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(160px,1fr))', gap:10 }}>
                {traffic.slice(0,6).map(t=>{
                  const col = chColor(t.channel)
                  return (
                    <div key={t.channel} className="card-hover" style={{ background:C.card, border:`1px solid ${C.border}`, borderRadius:12, padding:'14px 16px', borderTop:`2px solid ${col}` }}>
                      <div style={{ fontSize:10, fontWeight:700, color:col, marginBottom:4 }}>{t.channel}</div>
                      <div style={{ fontSize:22, fontWeight:800, fontFamily:MONO, color:C.text }}>{fN(t.sessions)}</div>
                      <div style={{ fontSize:10, color:C.faint, fontFamily:MONO, marginTop:2 }}>{Math.round(t.sessions/totalSess*100)}% of sessions</div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* ═════════════════════════════════════════════════════════════════
            TRAFFIC
        ═════════════════════════════════════════════════════════════════ */}
        {tab === 'traffic' && (
          <div className="fade-up">
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14, marginBottom:14 }}>
              <Card>
                <SH label="Where visitors come from" title="Traffic Channels" sub="Sessions + share of total"/>
                {loading ? [1,2,3,4,5].map(i=><div key={i} style={{ marginBottom:8 }}><Skel h={20}/></div>) : traffic.length === 0 ? <div style={{ color:C.faint, fontSize:12 }}>No data</div> : (
                  <div>
                    <div style={{ display:'grid', gridTemplateColumns:'1fr 70px 60px', gap:4, marginBottom:8, fontSize:9, fontWeight:700, color:C.faint, textTransform:'uppercase', letterSpacing:'0.08em' }}>
                      <span>Channel</span><span style={{ textAlign:'right' }}>Sessions</span><span style={{ textAlign:'right' }}>Share</span>
                    </div>
                    {traffic.map((t,i)=>(
                      <div key={t.channel} style={{ display:'grid', gridTemplateColumns:'1fr 70px 60px', gap:4, padding:'9px 0', borderBottom:`1px solid ${C.borderSubtle}`, alignItems:'center' }}>
                        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                          <div style={{ width:8, height:8, borderRadius:2, background:chColor(t.channel), flexShrink:0 }}/>
                          <span style={{ fontSize:12, color:i===0?C.text:C.muted, fontWeight:i===0?600:400 }}>{t.channel}</span>
                        </div>
                        <div style={{ textAlign:'right', fontSize:12, fontFamily:MONO, fontWeight:600, color:C.text }}>{fN(t.sessions)}</div>
                        <div style={{ textAlign:'right', fontSize:11, fontFamily:MONO, color:C.muted }}>{Math.round(t.sessions/totalSess*100)}%</div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>

              <Card>
                <SH label="External sites" title="Referrers" sub="Sites sending visitors to you"/>
                {loading ? [1,2,3,4,5,6,7].map(i=><div key={i} style={{ marginBottom:8 }}><Skel h={16}/></div>) : (
                  referrers && referrers.length > 0 ? referrers.slice(0,12).map((r,i)=>(
                    <HBar key={r.referrer} rank={i} label={r.referrer} value={r.sessions} max={referrers[0].sessions}
                      color={r.referrer.includes('linkedin')?C.indigo:r.referrer.includes('stripe')?C.emerald:C.violet}/>
                  )) : <div style={{ color:C.faint, fontSize:12 }}>No referral data</div>
                )}
              </Card>
            </div>

            <Card>
              <SH label="Campaign attribution" title="UTM Breakdown" sub="Traffic from tagged links"/>
              {loading ? <Skel h={120}/> : utm.length === 0 ? (
                <div>
                  <div style={{ color:C.faint, fontSize:12, fontFamily:MONO, marginBottom:12 }}>No UTM-tagged traffic found.</div>
                  <div style={{ fontSize:11, color:C.muted, borderLeft:`2px solid ${C.amber}40`, paddingLeft:10, lineHeight:1.65 }}>
                    Add <code style={{ background:C.bg, padding:'1px 5px', borderRadius:3, fontFamily:MONO, fontSize:10 }}>?utm_source=linkedin&utm_medium=social&utm_campaign=event-launch</code> to all external links.
                  </div>
                </div>
              ) : (
                <div style={{ overflowX:'auto' }}>
                  <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
                    <thead>
                      <tr style={{ borderBottom:`1px solid ${C.border}` }}>
                        {['Source','Medium','Campaign','Sessions','New Users'].map((h,i)=>(
                          <th key={h} style={{ padding:'8px 10px', textAlign:i>=3?'right':'left', fontFamily:MONO, fontSize:9, fontWeight:600, color:C.faint, textTransform:'uppercase', letterSpacing:'0.07em' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {utm.map((u,i)=>(
                        <tr key={i} style={{ borderBottom:`1px solid ${C.borderSubtle}` }}>
                          <td style={{ padding:'9px 10px', fontWeight:500, color:C.text, fontFamily:MONO }}>{u.utm_source}</td>
                          <td style={{ padding:'9px 10px', color:C.muted, fontFamily:MONO }}>{u.utm_medium}</td>
                          <td style={{ padding:'9px 10px', color:C.muted, maxWidth:140, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{u.utm_campaign||'—'}</td>
                          <td style={{ padding:'9px 10px', textAlign:'right', fontFamily:MONO, fontWeight:700, color:C.text }}>{fN(u.sessions)}</td>
                          <td style={{ padding:'9px 10px', textAlign:'right', fontFamily:MONO, color:C.muted }}>{fN(u.new_users)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        )}

        {/* ═════════════════════════════════════════════════════════════════
            CONTENT
        ═════════════════════════════════════════════════════════════════ */}
        {tab === 'content' && (
          <div className="fade-up">
            <div style={{ display:'grid', gridTemplateColumns:'3fr 2fr', gap:14, marginBottom:14 }}>
              <Card>
                <SH label="Page performance" title="Top Pages" sub={`${pages.length} pages · sorted by views`}/>
                {loading ? [1,2,3,4,5,6].map(i=><div key={i} style={{ marginBottom:4 }}><Skel h={36}/></div>) : pages.length === 0 ? <div style={{ color:C.faint, fontSize:12 }}>No page data</div> : (
                  <div style={{ overflowX:'auto' }}>
                    <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
                      <thead>
                        <tr style={{ borderBottom:`1px solid ${C.border}` }}>
                          {['#','Page','Views','Avg Time'].map((h,i)=>(
                            <th key={h} style={{ padding:'7px 8px', textAlign:i>=2?'right':'left', fontFamily:MONO, fontSize:9, fontWeight:600, color:C.faint, textTransform:'uppercase', letterSpacing:'0.07em' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {pages.slice(0,20).map((p,i)=>(
                          <tr key={p.page_path} style={{ borderBottom:`1px solid ${C.borderSubtle}` }}>
                            <td style={{ padding:'9px 8px', fontFamily:MONO, fontSize:9, color:C.faint, width:28 }}>{String(i+1).padStart(2,'0')}</td>
                            <td style={{ padding:'9px 8px', maxWidth:300 }}>
                              <div style={{ fontWeight:i<3?600:400, color:i<3?C.text:C.muted, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:280 }}>
                                {p.page_title||p.page_path}
                                {(p.page_path.includes('pitch')||p.page_path.includes('ticket'))&&<span style={{ fontSize:9, marginLeft:6, background:`${C.amber}20`, color:C.amber, padding:'1px 5px', borderRadius:3, fontWeight:700 }}>EVENT</span>}
                              </div>
                              <div style={{ fontSize:9, color:C.faint, fontFamily:MONO }}>{p.page_path}</div>
                            </td>
                            <td style={{ padding:'9px 8px', textAlign:'right', fontFamily:MONO, fontWeight:700, color:C.text }}>{fN(p.views)}</td>
                            <td style={{ padding:'9px 8px', textAlign:'right', fontFamily:MONO, color:(p as any).avg_engagement_time_secs>60?C.emerald:C.faint }}>{fDur((p as any).avg_engagement_time_secs??0)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
                <Card>
                  <SH label="Entry points" title="Landing Pages" sub="First page visitors see"/>
                  {loading ? [1,2,3,4,5].map(i=><div key={i} style={{ marginBottom:8 }}><Skel h={18}/></div>) : (
                    landing_pages && landing_pages.filter(p=>p.landing_page!=='(not set)').length > 0 ?
                      landing_pages.filter(p=>p.landing_page!=='(not set)').slice(0,8).map((p,i)=>(
                        <HBar key={p.landing_page} rank={i} label={p.landing_page} value={p.sessions}
                          max={landing_pages.filter(lp=>lp.landing_page!=='(not set)')[0]?.sessions??1}
                          color={p.landing_page.includes('pitch')?C.amber:p.landing_page.includes('ticket')?C.emerald:C.indigo}/>
                      )) : <div style={{ color:C.faint, fontSize:12 }}>No landing page data</div>
                  )}
                </Card>
                {events && events.length > 0 && !loading && (
                  <Card>
                    <SH label="GA4 events" title="All Events" sub={`${events.length} event types`}/>
                    {events.slice(0,8).map((e,i)=>(
                      <HBar key={e.event_name} rank={i} label={e.event_name} value={e.event_count} max={events[0].event_count} color={C.indigo}/>
                    ))}
                    {!events.some(e=>(e as any).is_custom) && (
                      <div style={{ fontSize:11, color:C.amber, borderLeft:`2px solid ${C.amber}40`, paddingLeft:10, marginTop:12, lineHeight:1.6 }}>
                        No custom events detected. Add tracking for form_submit, sign_up, and ticket purchases.
                      </div>
                    )}
                  </Card>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ═════════════════════════════════════════════════════════════════
            AUDIENCE
        ═════════════════════════════════════════════════════════════════ */}
        {tab === 'audience' && (
          <div className="fade-up">
            {(() => {
              const ret = data.new_vs_returning?.find(r=>r.segment==='returning')
              const nw  = data.new_vs_returning?.find(r=>r.segment==='new')
              const total = (ret?.sessions??0) + (nw?.sessions??0)
              if (!ret && !nw) return null
              return (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14, marginBottom:14 }}>
                  {([{seg:nw,label:'New Visitors',col:C.sky,icon:'✨'},{seg:ret,label:'Returning Visitors',col:C.violet,icon:'⭐'}] as const).filter(r=>r.seg).map(({seg:s,label,col,icon})=>(
                    <Card key={label}>
                      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:14 }}>
                        <div>
                          <div style={{ fontSize:10, fontWeight:700, color:C.muted, textTransform:'uppercase', letterSpacing:'0.1em', marginBottom:4 }}>{icon} {label}</div>
                          <div style={{ fontSize:28, fontWeight:800, fontFamily:MONO, color:col }}>{fN(s!.sessions)}</div>
                          <div style={{ fontSize:11, color:C.faint, fontFamily:MONO }}>{total>0?Math.round(s!.sessions/total*100):0}% of sessions</div>
                        </div>
                        <div style={{ textAlign:'right' }}>
                          <div style={{ fontSize:9, color:C.faint, textTransform:'uppercase', letterSpacing:'0.07em', marginBottom:2 }}>Avg duration</div>
                          <div style={{ fontSize:18, fontWeight:700, fontFamily:MONO, color:C.text }}>{fDur(s!.avg_duration_secs??0)}</div>
                        </div>
                      </div>
                      <Divider/>
                      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
                        {[
                          { l:'Engagement', v:fP(s!.engagement_rate??0) },
                          { l:'Bounce',     v:fP(s!.bounce_rate??0) },
                          { l:'Pages/Visit', v:(s!.pages_per_session??0).toFixed(2) },
                          { l:'Users',       v:fN(s!.users??0) },
                        ].map(m=>(
                          <div key={m.l} style={{ background:C.bg, borderRadius:8, padding:'10px 12px' }}>
                            <div style={{ fontSize:9, color:C.faint, textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:3 }}>{m.l}</div>
                            <div style={{ fontSize:16, fontWeight:700, fontFamily:MONO, color:C.text }}>{m.v}</div>
                          </div>
                        ))}
                      </div>
                    </Card>
                  ))}
                </div>
              )
            })()}

            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:14 }}>
              <Card>
                <SH label="Geography" title="Top Countries"/>
                {loading ? [1,2,3,4,5].map(i=><div key={i} style={{ marginBottom:8 }}><Skel h={16}/></div>) : (
                  countries.slice(0,10).map((c,i)=>(
                    <HBar key={c.country} rank={i} label={c.country} value={c.sessions} max={countries[0]?.sessions??1} color={C.indigo}/>
                  ))
                )}
              </Card>
              <Card>
                <SH label="Geography" title="Top Cities"/>
                {loading ? [1,2,3,4,5].map(i=><div key={i} style={{ marginBottom:8 }}><Skel h={16}/></div>) : (
                  cities.filter(c=>c.city!=='(not set)').slice(0,10).map((c,i)=>(
                    <HBar key={`${c.city}-${c.country}`} rank={i} label={c.city} value={c.sessions}
                      max={cities.filter(x=>x.city!=='(not set)')[0]?.sessions??1} sub={c.country} color={C.sky}/>
                  ))
                )}
              </Card>
              <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
                <Card>
                  <SH label="Device type" title="Devices"/>
                  {loading ? <Skel h={80}/> : device.length === 0 ? <div style={{ color:C.faint, fontSize:12 }}>No data</div> : (() => {
                    const tot = device.reduce((s,d)=>s+d.sessions,0)||1
                    const DCOL: Record<string,string> = { desktop:C.indigo, mobile:C.sky, tablet:C.violet }
                    return (
                      <div style={{ display:'flex', gap:8 }}>
                        {device.map(d=>{
                          const p = Math.round(d.sessions/tot*100)
                          const col = DCOL[d.device_category.toLowerCase()]||C.faint
                          return (
                            <div key={d.device_category} style={{ flex:p||1, background:`${col}14`, borderTop:`2px solid ${col}`, borderRadius:'0 0 8px 8px', padding:'10px 8px', textAlign:'center' }}>
                              <div style={{ fontSize:18, fontWeight:800, fontFamily:MONO, color:col }}>{p}%</div>
                              <div style={{ fontSize:9, color:C.muted, marginTop:1, textTransform:'uppercase', letterSpacing:'0.07em' }}>{d.device_category}</div>
                            </div>
                          )
                        })}
                      </div>
                    )
                  })()}
                </Card>
                <Card>
                  <SH label="Browsers" title="Top Browsers"/>
                  {loading ? <Skel h={80}/> : (
                    browsers.slice(0,5).map((b,i)=>(
                      <HBar key={b.browser} rank={i} label={b.browser} value={b.sessions} max={browsers[0]?.sessions??1} color={C.emerald}/>
                    ))
                  )}
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* ═════════════════════════════════════════════════════════════════
            TIMING
        ═════════════════════════════════════════════════════════════════ */}
        {tab === 'timing' && (
          <div className="fade-up">
            <div style={{ display:'grid', gridTemplateColumns:'2fr 1fr', gap:14 }}>
              <Card>
                <SH label={period==='daily'?'Hour by hour':'Over time'} title={period==='daily'?'Sessions by Hour':'Sessions Over Time'}
                  sub={peakHour?`Peak: ${peakHour.label} · ${fN(peakHour.sessions)} sessions`:undefined}/>
                {loading ? <Skel h={240}/> : time_series.length === 0 ? (
                  <div style={{ height:240, display:'flex', alignItems:'center', justifyContent:'center', color:C.faint, fontSize:12, fontFamily:MONO }}>No data</div>
                ) : (
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={time_series} margin={{ top:4, right:4, bottom:0, left:-20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={C.chartGrid} vertical={false}/>
                      <XAxis dataKey="label" tick={{ fontSize:10, fill:C.muted, fontFamily:MONO }} tickLine={false} axisLine={false} interval={period==='daily'?1:'preserveStartEnd'}/>
                      <YAxis tick={{ fontSize:10, fill:C.muted, fontFamily:MONO }} tickLine={false} axisLine={false}/>
                      <Tooltip content={<CTip/>}/>
                      <Bar dataKey="sessions" name="Sessions" radius={[3,3,0,0]}>
                        {time_series.map((_,idx)=>{
                          const maxIdx = time_series.reduce((mi,v,i)=>v.sessions>time_series[mi].sessions?i:mi,0)
                          return <Cell key={idx} fill={maxIdx===idx?C.indigo:`${C.indigo}55`}/>
                        })}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
                {period==='daily' && peakHour && !loading && (
                  <div style={{ fontSize:11, color:C.indigo, borderLeft:`2px solid ${C.indigo}40`, paddingLeft:10, marginTop:14, lineHeight:1.6 }}>
                    <strong>Peak at {peakHour.label}</strong> ({fN(peakHour.sessions)} sessions). Schedule LinkedIn posts 30–60 min before this window.
                  </div>
                )}
              </Card>
              <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
                <Card>
                  <SH label="Content depth" title="Session quality"/>
                  {loading ? <Skel h={100}/> : (
                    [
                      { l:'Sessions',       v:fN(kpis.sessions),   col:C.indigo },
                      { l:'Pageviews',      v:fN(kpis.pageviews),  col:C.violet },
                      { l:'Pages/session',  v:(kpis.pages_per_session??0).toFixed(2), col: kpis.pages_per_session>=2?C.emerald:C.amber },
                      { l:'Avg duration',   v:fDur(kpis.avg_session_duration_secs), col:C.sky },
                    ].map(m=>(
                      <div key={m.l} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'10px 0', borderBottom:`1px solid ${C.borderSubtle}` }}>
                        <span style={{ fontSize:12, color:C.muted }}>{m.l}</span>
                        <span style={{ fontSize:15, fontWeight:700, fontFamily:MONO, color:m.col }}>{m.v}</span>
                      </div>
                    ))
                  )}
                </Card>
                <Card>
                  <SH label="When to post" title="Best times" sub="Based on peak traffic"/>
                  {loading ? <Skel h={100}/> : time_series.length === 0 ? (
                    <div style={{ color:C.faint, fontSize:12 }}>Run a daily fetch to see hourly data</div>
                  ) : (
                    [...time_series].sort((a,b)=>(b.sessions||0)-(a.sessions||0)).slice(0,5).map((h,i)=>(
                      <div key={h.label} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'8px 0', borderBottom:`1px solid ${C.borderSubtle}` }}>
                        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                          <span style={{ width:20, fontSize:10, fontFamily:MONO, color:C.faint, textAlign:'right' }}>#{i+1}</span>
                          <span style={{ fontSize:12, fontFamily:MONO, color:C.text, fontWeight:i===0?700:400 }}>{h.label}</span>
                        </div>
                        <span style={{ fontSize:11, fontFamily:MONO, color:i===0?C.indigo:C.muted, fontWeight:i===0?700:400 }}>{fN(h.sessions)}</span>
                      </div>
                    ))
                  )}
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* ═════════════════════════════════════════════════════════════════
            FINANCIAL
        ═════════════════════════════════════════════════════════════════ */}
        {tab === 'financial' && (
          <div className="fade-up">

            {/* Revenue KPI cards */}
            <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:14, marginBottom:22 }}>
              <KpiCard label="GA4 Revenue"    value={revenue?.total_revenue??0}    fmt={fGBP}  color={C.emerald} loading={loading}
                sub="Total revenue tracked in GA4"
                insight={(revenue?.total_revenue??0)===0?'Set up GA4 ecommerce or link Stripe to track revenue':'Revenue tracked'} />
              <KpiCard label="Purchases"      value={revenue?.purchases??0}        color={C.indigo}  loading={loading}
                sub={`${revenue?.transactions??0} transactions`}
                sparkData={revenue_series} sparkKey="purchases"
                insight={(revenue?.purchases??0)>0?`AOV: ${fGBP((revenue?.purchase_revenue??0)/(revenue?.purchases||1))}`:'No purchase events'} />
              <KpiCard label="GA4 Conversions" value={revenue?.conversions??0}     color={C.violet}  loading={loading}
                sub="Events marked as conversions in GA4"
                insight={(revenue?.conversions??0)>0?`${fP((revenue?.conversions??0)/(kpis.sessions||1)*100)} conversion rate`:'No conversions tracked'} />
              <KpiCard label="Conv. Rate"     value={kpis.sessions>0&&(revenue?.conversions??0)>0?(revenue?.conversions??0)/kpis.sessions*100:0} fmt={fP} color={C.sky} loading={loading}
                sub={`${fN(revenue?.conversions??0)} conversions / ${fN(kpis.sessions)} sessions`}
                insight={(revenue?.conversions??0)===0?'Enable conversion tracking in GA4':'Conversion rate'} />
            </div>

            {/* No ecommerce banner */}
            {!loading && (revenue?.total_revenue??0) === 0 && (revenue?.purchases??0) === 0 && (
              <div style={{ background:`${C.amber}10`, border:`1px solid ${C.amber}30`, borderRadius:12, padding:'18px 22px', marginBottom:20 }}>
                <div style={{ fontWeight:600, color:C.amber, fontSize:13, marginBottom:6 }}>GA4 ecommerce not configured</div>
                <div style={{ fontSize:12, color:C.muted, lineHeight:1.7 }}>
                  Cambridge Forum uses Stripe for ticket payments. To see revenue here automatically, either:<br/>
                  <strong style={{ color:C.text }}>Option A</strong> — Add GA4 <code style={{ background:C.bg, padding:'1px 5px', borderRadius:3, fontFamily:MONO, fontSize:10 }}>purchase</code> events with value when Stripe redirects back after payment.<br/>
                  <strong style={{ color:C.text }}>Option B</strong> — Use the marketing calculator below with your Stripe revenue numbers.
                </div>
              </div>
            )}

            {/* generate_lead conversion KPIs */}
            <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:14, marginBottom:14 }}>
              <KpiCard label="Leads (generate_lead)" value={leads?.leads??0} color={C.emerald} loading={loading}
                sub={`${fN(leads?.users??0)} unique users`}
                insight={(leads?.leads??0)>0?'Tracked as a GA4 conversion event':'No generate_lead events found yet'} />
              <KpiCard label="Lead Conversion Rate" value={kpis.sessions>0&&(leads?.leads??0)>0?(leads?.leads??0)/kpis.sessions*100:0} fmt={fP} color={C.sky} loading={loading}
                sub={`${fN(leads?.leads??0)} leads / ${fN(kpis.sessions)} sessions`}
                insight={(leads?.leads??0)>0?'% of sessions that generated a lead':'Enable generate_lead tracking'} />
              <KpiCard label="Leads per User" value={(leads?.users??0)>0?(leads?.leads??0)/(leads?.users??1):0} fmt={v=>v.toFixed(2)} color={C.violet} loading={loading}
                sub="Average leads per converting user"
                insight={(leads?.leads??0)>0?'Most users generate 1 lead':'—'} />
            </div>

            {/* Lead attribution + geography */}
            {!loading && (leads?.leads??0) > 0 && (
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14, marginBottom:14 }}>
                <Card>
                  <SH label="Where leads come from" title="Lead Attribution" sub="Source · Medium · Campaign for generate_lead events"/>
                  {!lead_attribution || lead_attribution.length===0 ? (
                    <div style={{ color:C.faint, fontSize:12 }}>No attribution data for leads in this period</div>
                  ) : (
                    <div style={{ overflowX:'auto' }}>
                      <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
                        <thead>
                          <tr style={{ borderBottom:`1px solid ${C.border}` }}>
                            {['Source','Medium','Campaign','Leads','Users'].map((h,i)=>(
                              <th key={h} style={{ padding:'7px 8px', textAlign:i>=3?'right':'left', fontFamily:MONO, fontSize:9, fontWeight:600, color:C.faint, textTransform:'uppercase', letterSpacing:'0.06em' }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {lead_attribution.slice(0,12).map((r,i)=>(
                            <tr key={`${r.source}-${r.medium}-${r.campaign}-${i}`} style={{ borderBottom:`1px solid ${C.borderSubtle}` }}>
                              <td style={{ padding:'8px', fontWeight:i===0?600:400, color:i===0?C.text:C.muted, fontFamily:MONO }}>{r.source}</td>
                              <td style={{ padding:'8px', color:C.muted, fontFamily:MONO }}>{r.medium}</td>
                              <td style={{ padding:'8px', color:C.muted, maxWidth:120, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{r.campaign}</td>
                              <td style={{ padding:'8px', textAlign:'right', fontFamily:MONO, fontWeight:700, color:C.emerald }}>{fN(r.leads)}</td>
                              <td style={{ padding:'8px', textAlign:'right', fontFamily:MONO, color:C.muted }}>{fN(r.users)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>

                <Card>
                  <SH label="Where leads are located" title="Lead Geography" sub="Cities and countries generating leads"/>
                  {!lead_geo || lead_geo.length===0 ? (
                    <div style={{ color:C.faint, fontSize:12 }}>No geography data for leads in this period</div>
                  ) : (
                    lead_geo.slice(0,10).map((r,i)=>(
                      <HBar key={`${r.city}-${r.country}-${i}`} rank={i} label={r.city} value={r.leads} max={lead_geo[0]?.leads??1} sub={r.country} color={C.emerald}/>
                    ))
                  )}
                </Card>
              </div>
            )}

            {/* Revenue chart + conversion events */}
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14, marginBottom:14 }}>

              {revenue_series && revenue_series.length > 0 ? (
                <Card>
                  <SH label="Revenue over time" title="Daily Revenue"/>
                  <ResponsiveContainer width="100%" height={180}>
                    <AreaChart data={revenue_series} margin={{ top:4, right:4, bottom:0, left:-20 }}>
                      <defs><linearGradient id="g2" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={C.emerald} stopOpacity={0.25}/><stop offset="95%" stopColor={C.emerald} stopOpacity={0.02}/></linearGradient></defs>
                      <CartesianGrid strokeDasharray="3 3" stroke={C.chartGrid}/>
                      <XAxis dataKey="date" tick={{ fontSize:10, fill:C.muted, fontFamily:MONO }} tickLine={false} axisLine={false} interval="preserveStartEnd"/>
                      <YAxis tick={{ fontSize:10, fill:C.muted, fontFamily:MONO }} tickLine={false} axisLine={false}/>
                      <Tooltip content={<CTip/>}/>
                      <Area type="monotone" dataKey="total_revenue" name="Revenue" stroke={C.emerald} strokeWidth={2} fill="url(#g2)" dot={false}/>
                    </AreaChart>
                  </ResponsiveContainer>
                </Card>
              ) : (
                <Card>
                  <SH label="Revenue timeline" title="No revenue data"/>
                  <div style={{ height:180, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:8 }}>
                    <div style={{ fontSize:32 }}>💳</div>
                    <div style={{ fontSize:12, color:C.muted, textAlign:'center', maxWidth:260, lineHeight:1.6 }}>
                      Once GA4 ecommerce events are fired, revenue will appear here per day.
                    </div>
                  </div>
                </Card>
              )}

              <Card>
                <SH label="Conversion signals" title="Key Conversion Events" sub="Events that indicate purchase intent"/>
                {loading ? [1,2,3,4].map(i=><div key={i} style={{ marginBottom:8 }}><Skel h={16}/></div>) : (() => {
                  const convEvents = events.filter(e=>
                    ['purchase','begin_checkout','add_to_cart','sign_up','generate_lead',
                     'form_submit','contact','click'].some(k=>e.event_name.includes(k))
                  )
                  if (convEvents.length === 0) return (
                    <div>
                      <div style={{ color:C.faint, fontSize:12, fontFamily:MONO, marginBottom:10 }}>No purchase intent events found.</div>
                      <div style={{ fontSize:11, color:C.muted, lineHeight:1.65 }}>
                        Standard GA4 events currently tracked: {events.slice(0,4).map(e=>e.event_name).join(', ')}.<br/>
                        Consider adding custom events for: ticket_view, apply_click, register_intent.
                      </div>
                    </div>
                  )
                  return convEvents.map((e,i)=>(
                    <HBar key={e.event_name} rank={i} label={e.event_name} value={e.event_count} max={convEvents[0].event_count} color={C.emerald}/>
                  ))
                })()}
              </Card>
            </div>

            {/* Stripe sessions */}
            {referrers && referrers.some(r=>r.referrer.includes('stripe')) && (
              <Card style={{ marginBottom:14 }}>
                <SH label="Payment signals" title="Stripe Traffic" sub="Sessions arriving from checkout.stripe.com — active ticket buyers"/>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(200px,1fr))', gap:14 }}>
                  {referrers.filter(r=>r.referrer.includes('stripe')).map(r=>(
                    <div key={r.referrer} style={{ background:C.bg, borderRadius:10, padding:'14px 16px', border:`1px solid ${C.emerald}30` }}>
                      <div style={{ fontSize:10, fontWeight:700, color:C.emerald, marginBottom:4 }}>{r.referrer}</div>
                      <div style={{ fontSize:22, fontWeight:800, fontFamily:MONO, color:C.text }}>{fN(r.sessions)}</div>
                      <div style={{ fontSize:10, color:C.faint }}>sessions · {fN(r.new_users)} new users</div>
                    </div>
                  ))}
                </div>
                <div style={{ fontSize:11, color:C.emerald, borderLeft:`2px solid ${C.emerald}40`, paddingLeft:10, marginTop:14, lineHeight:1.6 }}>
                  These sessions are people returning after Stripe payment, confirming ticket purchase. Add a post-payment GA4 <code style={{ fontFamily:MONO, fontSize:10 }}>purchase</code> event to track this as revenue automatically.
                </div>
              </Card>
            )}

            {/* Marketing Calculator */}
            <MarketingCalculator sessions={kpis.sessions} conversions={revenue?.conversions??0} newUsers={kpis.new_users} autoLeads={leads?.leads??0}/>
          </div>
        )}

        {/* ═════════════════════════════════════════════════════════════════
            INSIGHTS
        ═════════════════════════════════════════════════════════════════ */}
        {tab === 'insights' && (
          <div className="fade-up">

            {/* Row 1: Audience health + risk indicators */}
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:14, marginBottom:14 }}>

              {/* Audience health score */}
              <Card>
                <SH label="Composite score" title="Audience Health" sub="Engagement · Duration · Depth · Loyalty"/>
                {loading ? <Skel h={120}/> : (
                  <>
                    <ScoreBadge score={healthScore.score}/>
                    <div style={{ marginTop:16 }}>
                      {healthScore.components.map(c=>(
                        <div key={c.label} style={{ marginBottom:10 }}>
                          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:4 }}>
                            <div style={{ display:'flex', alignItems:'center', gap:5 }}>
                              <span style={{ fontSize:11, color:C.muted }}>{c.label}</span>
                              <InfoTip text={c.tip}/>
                            </div>
                            <span style={{ fontSize:11, fontFamily:MONO, fontWeight:600, color:C.text }}>{c.val}</span>
                          </div>
                          <div style={{ height:4, background:C.faintA, borderRadius:99 }}>
                            <div style={{ height:'100%', width:`${Math.min(c.score,100)}%`, background:c.score>=70?C.emerald:c.score>=45?C.amber:C.rose, borderRadius:99, transition:'width 0.8s ease' }}/>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </Card>

              {/* Channel dependency risk */}
              <Card>
                <SH label="Risk indicator" title="Channel Dependency"/>
                {loading ? <Skel h={120}/> : !chanDep ? <div style={{ color:C.faint, fontSize:12 }}>No data</div> : (
                  <>
                    <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
                      <div style={{ fontSize:42, fontWeight:900, fontFamily:MONO, color:riskColor(chanDep.risk), lineHeight:1 }}>{chanDep.topPct}%</div>
                      <div>
                        <div style={{ fontSize:12, fontWeight:600, color:C.text }}>{chanDep.channel}</div>
                        <div style={{ fontSize:10, color:C.muted }}>{chanDep.channelCount} channels total</div>
                        <div style={{ display:'inline-flex', alignItems:'center', gap:4, marginTop:4, padding:'2px 8px', borderRadius:4, background:`${riskColor(chanDep.risk)}20`, border:`1px solid ${riskColor(chanDep.risk)}40` }}>
                          <span style={{ fontSize:9, fontWeight:700, color:riskColor(chanDep.risk), textTransform:'uppercase', letterSpacing:'0.08em' }}>{chanDep.risk} risk</span>
                        </div>
                      </div>
                    </div>
                    <div style={{ fontSize:11, color:C.muted, lineHeight:1.65, borderLeft:`2px solid ${riskColor(chanDep.risk)}40`, paddingLeft:10 }}>
                      {chanDep.risk==='high'
                        ? `${chanDep.topPct}% dependency on ${chanDep.channel} is dangerous. A single algorithm change or outage could drop traffic by half. Diversify urgently.`
                        : chanDep.risk==='medium'
                        ? `${chanDep.topPct}% from ${chanDep.channel} is moderate. Build email and LinkedIn as backup channels.`
                        : `Good diversification across ${chanDep.channelCount} channels. No single source dominates.`}
                    </div>
                  </>
                )}
              </Card>

              {/* Geographic concentration risk */}
              <Card>
                <SH label="Risk indicator" title="Geographic Concentration"/>
                {loading ? <Skel h={120}/> : !geoConc ? <div style={{ color:C.faint, fontSize:12 }}>No data</div> : (
                  <>
                    <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
                      <div style={{ fontSize:42, fontWeight:900, fontFamily:MONO, color:riskColor(geoConc.risk), lineHeight:1 }}>{geoConc.topPct}%</div>
                      <div>
                        <div style={{ fontSize:12, fontWeight:600, color:C.text }}>{geoConc.topCountry}</div>
                        <div style={{ fontSize:10, color:C.muted }}>top country</div>
                        <div style={{ display:'inline-flex', alignItems:'center', gap:4, marginTop:4, padding:'2px 8px', borderRadius:4, background:`${riskColor(geoConc.risk)}20`, border:`1px solid ${riskColor(geoConc.risk)}40` }}>
                          <span style={{ fontSize:9, fontWeight:700, color:riskColor(geoConc.risk), textTransform:'uppercase', letterSpacing:'0.08em' }}>{geoConc.risk} concentration</span>
                        </div>
                      </div>
                    </div>
                    <div style={{ fontSize:11, color:C.muted, lineHeight:1.65, borderLeft:`2px solid ${riskColor(geoConc.risk)}40`, paddingLeft:10 }}>
                      {geoConc.topPct > 60
                        ? `${geoConc.topPct}% of sessions from ${geoConc.topCountry}. If this is intentional (local event), fine. If you want global reach, create content for other markets.`
                        : `Traffic is reasonably distributed. HHI concentration index: ${geoConc.hhi}/100.`}
                    </div>
                  </>
                )}
              </Card>
            </div>

            {/* Row 2: Page-to-page drop-off + conversion funnel */}
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14, marginBottom:14 }}>

              {/* Page drop-off waterfall */}
              <Card>
                <SH label="Content drop-off" title="Page Views Waterfall" sub="How views fall across your top pages — each bar is % of #1 page"/>
                {loading ? <Skel h={220}/> : pages.length === 0 ? <div style={{ color:C.faint, fontSize:12 }}>No page data</div> : (
                  <>
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={pageDropOff} layout="vertical" margin={{ top:4, right:40, bottom:0, left:0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={C.chartGrid} horizontal={false}/>
                        <XAxis type="number" tick={{ fontSize:10, fill:C.muted, fontFamily:MONO }} tickLine={false} axisLine={false}/>
                        <YAxis dataKey="path" type="category" width={140} tick={{ fontSize:9, fill:C.muted, fontFamily:MONO }} tickLine={false} axisLine={false}/>
                        <Tooltip content={<CTip/>}/>
                        <Bar dataKey="views" name="Views" radius={[0,4,4,0]}>
                          {pageDropOff.map((_,idx)=>(
                            <Cell key={idx} fill={idx===0?C.indigo:idx<3?`${C.indigo}aa`:`${C.indigo}55`}/>
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                    <div style={{ marginTop:12 }}>
                      {pageDropOff.slice(1).filter(p=>p.dropOff>0).slice(0,3).map(p=>(
                        <div key={p.path} style={{ display:'flex', justifyContent:'space-between', fontSize:11, padding:'4px 0', borderBottom:`1px solid ${C.borderSubtle}` }}>
                          <span style={{ color:C.muted, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', flex:1, marginRight:8 }}>{p.path}</span>
                          <span style={{ fontFamily:MONO, color:p.dropOff>50?C.rose:p.dropOff>30?C.amber:C.emerald, fontWeight:600, flexShrink:0 }}>
                            {p.dropOff>0?<>↓{p.dropOff}%</>:'—'}
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </Card>

              {/* Conversion funnel */}
              <Card>
                <SH label="Conversion funnel" title="Cambridge Forum Journey" sub="Sessions through the key event pages"/>
                {loading ? <Skel h={220}/> : funnelPages.length < 2 ? (
                  <div style={{ height:220, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:8 }}>
                    <div style={{ fontSize:28 }}>🔍</div>
                    <div style={{ fontSize:12, color:C.muted, textAlign:'center', lineHeight:1.6 }}>
                      Not enough page data to build funnel.<br/>Fetch more data or check page tracking.
                    </div>
                  </div>
                ) : (
                  <>
                    {funnelPages.map((stage,i)=>{
                      const pctOfTop = Math.round((stage.value/funnelPages[0].value)*100)
                      const dropFromPrev = i>0 ? Math.round(100-((stage.value/funnelPages[i-1].value)*100)) : 0
                      return (
                        <div key={stage.path} style={{ marginBottom:10 }}>
                          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:4 }}>
                            <div>
                              <div style={{ fontSize:12, fontWeight:600, color:C.text }}>{stage.name.length>35?stage.name.slice(0,33)+'…':stage.name}</div>
                              <div style={{ fontSize:9, color:C.faint, fontFamily:MONO }}>{stage.path}</div>
                            </div>
                            <div style={{ textAlign:'right', flexShrink:0, marginLeft:8 }}>
                              <div style={{ fontSize:14, fontWeight:700, fontFamily:MONO, color:C.text }}>{fN(stage.value)}</div>
                              {i>0&&<div style={{ fontSize:10, color:dropFromPrev>60?C.rose:dropFromPrev>30?C.amber:C.emerald, fontFamily:MONO, fontWeight:600 }}>↓{dropFromPrev}% drop</div>}
                            </div>
                          </div>
                          <div style={{ height:6, background:C.faintA, borderRadius:99 }}>
                            <div style={{ height:'100%', width:`${pctOfTop}%`, background:stage.fill, borderRadius:99, transition:'width 0.8s ease' }}/>
                          </div>
                        </div>
                      )
                    })}
                    {funnelPages.length >= 2 && (
                      <div style={{ marginTop:12, fontSize:11, color:C.muted, borderLeft:`2px solid ${C.amber}40`, paddingLeft:10, lineHeight:1.6 }}>
                        Overall funnel conversion: <strong style={{ color:C.text }}>{Math.round((funnelPages[funnelPages.length-1].value/funnelPages[0].value)*100)}%</strong> reach the last tracked stage.
                      </div>
                    )}
                  </>
                )}
              </Card>
            </div>

            {/* Row 3: Return visitor trend + session quality distribution */}
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14, marginBottom:14 }}>

              {/* Return visitor (churn proxy) over time */}
              <Card>
                <SH label="Retention trend" title="New vs Returning Over Time" sub="Declining return rate = visitor churn signal"/>
                {loading ? <Skel h={190}/> : time_series.length === 0 ? (
                  <div style={{ height:190, display:'flex', alignItems:'center', justifyContent:'center', color:C.faint, fontSize:12 }}>No time series data</div>
                ) : (() => {
                  const tsWithUsers = time_series.filter(t => (t.users||0) > 0)
                  if (!tsWithUsers.length) return <div style={{ height:190, display:'flex', alignItems:'center', justifyContent:'center', color:C.faint, fontSize:12, fontFamily:MONO }}>No user data in time series</div>
                  return (
                    <ResponsiveContainer width="100%" height={190}>
                      <AreaChart data={time_series} margin={{ top:4, right:4, bottom:0, left:-20 }}>
                        <defs>
                          <linearGradient id="gNew" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={C.sky} stopOpacity={0.3}/><stop offset="95%" stopColor={C.sky} stopOpacity={0}/></linearGradient>
                          <linearGradient id="gRet" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={C.violet} stopOpacity={0.3}/><stop offset="95%" stopColor={C.violet} stopOpacity={0}/></linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke={C.chartGrid}/>
                        <XAxis dataKey="label" tick={{ fontSize:10, fill:C.muted, fontFamily:MONO }} tickLine={false} axisLine={false} interval="preserveStartEnd"/>
                        <YAxis tick={{ fontSize:10, fill:C.muted, fontFamily:MONO }} tickLine={false} axisLine={false}/>
                        <Tooltip content={<CTip/>}/>
                        <Area type="monotone" dataKey="users" name="Users" stroke={C.sky} strokeWidth={1.8} fill="url(#gNew)" dot={false}/>
                        <Area type="monotone" dataKey="sessions" name="Sessions" stroke={C.violet} strokeWidth={1.8} fill="url(#gRet)" dot={false}/>
                      </AreaChart>
                    </ResponsiveContainer>
                  )
                })()}
                <div style={{ marginTop:12, fontSize:11, color:C.muted, lineHeight:1.6 }}>
                  {kpis.users > 0 ? (
                    <>Return visitor rate: <strong style={{ color:C.text }}>{fP(kpis.returning_users/kpis.users*100)}</strong> — {kpis.returning_users/kpis.users > 0.2 ? 'healthy loyalty' : 'mostly new visitors, limited return traffic'}. Sessions-to-users ratio of {(kpis.sessions/kpis.users).toFixed(2)} shows average visit frequency.</>
                  ) : 'No user data available for this period.'}
                </div>
              </Card>

              {/* Session quality distribution */}
              <Card>
                <SH label="Traffic quality" title="Session Quality Breakdown" sub="Classifying sessions by depth and engagement"/>
                {loading ? <Skel h={190}/> : kpis.sessions === 0 ? <div style={{ color:C.faint, fontSize:12 }}>No session data</div> : (() => {
                  const engagedSess  = Math.round(kpis.sessions * (kpis.engagement_rate/100))
                  const bouncedSess  = Math.round(kpis.sessions * (kpis.bounce_rate/100))
                  const deepSess     = Math.round(kpis.sessions * Math.max(0, (kpis.pages_per_session-1)/kpis.pages_per_session * (kpis.engagement_rate/100)))
                  const otherSess    = Math.max(0, kpis.sessions - engagedSess - bouncedSess)
                  const tiers = [
                    { label:'Deep readers', n:deepSess, desc:`2+ pages · engaged`, color:C.emerald },
                    { label:'Engaged (single page)', n:Math.max(0,engagedSess-deepSess), desc:'10s+ on one page', color:C.sky },
                    { label:'Quick looks', n:Math.max(0,otherSess), desc:'<10s · not bounced', color:C.amber },
                    { label:'Bounced', n:bouncedSess, desc:'Left immediately', color:C.rose },
                  ].filter(t=>t.n>0)
                  return (
                    <div>
                      {tiers.map(t=>(
                        <div key={t.label} style={{ marginBottom:14 }}>
                          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:5 }}>
                            <div>
                              <span style={{ fontSize:12, fontWeight:600, color:C.text }}>{t.label}</span>
                              <span style={{ fontSize:10, color:C.faint, fontFamily:MONO, marginLeft:6 }}>{t.desc}</span>
                            </div>
                            <div style={{ textAlign:'right' }}>
                              <span style={{ fontSize:13, fontWeight:700, fontFamily:MONO, color:t.color }}>{fN(t.n)}</span>
                              <span style={{ fontSize:10, color:C.faint, fontFamily:MONO, marginLeft:4 }}>{Math.round(t.n/kpis.sessions*100)}%</span>
                            </div>
                          </div>
                          <div style={{ height:8, background:C.faintA, borderRadius:99 }}>
                            <div style={{ height:'100%', width:`${Math.round(t.n/kpis.sessions*100)}%`, background:t.color, borderRadius:99, transition:'width 0.8s ease' }}/>
                          </div>
                        </div>
                      ))}
                      <div style={{ fontSize:11, color:C.muted, marginTop:6, lineHeight:1.6 }}>
                        {Math.round(deepSess/kpis.sessions*100)}% of your visitors read deeply. Aim to convert more "bounced" visitors into "engaged" by improving first-screen content.
                      </div>
                    </div>
                  )
                })()}
              </Card>
            </div>

            {/* Row 4: Traffic quality matrix + content performance scores */}
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14 }}>

              {/* Traffic source quality scatter */}
              <Card>
                <SH label="Volume vs quality" title="Traffic Quality Matrix" sub="Bigger bubble = more sessions · Y-axis = engagement quality"/>
                {loading ? <Skel h={220}/> : qualityMatrix.length === 0 ? <div style={{ color:C.faint, fontSize:12 }}>No channel data</div> : (
                  <>
                    <ResponsiveContainer width="100%" height={200}>
                      <ScatterChart margin={{ top:10, right:10, bottom:10, left:-10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={C.chartGrid}/>
                        <XAxis dataKey="sessions" name="Sessions" type="number" tick={{ fontSize:10, fill:C.muted, fontFamily:MONO }} tickLine={false} axisLine={false} label={{ value:'Sessions', position:'insideBottom', offset:-2, fontSize:9, fill:C.faint }}/>
                        <YAxis dataKey="quality" name="Quality" type="number" domain={[0,100]} tick={{ fontSize:10, fill:C.muted, fontFamily:MONO }} tickLine={false} axisLine={false} label={{ value:'Engagement %', angle:-90, position:'insideLeft', offset:10, fontSize:9, fill:C.faint }}/>
                        <ZAxis dataKey="sessions" range={[40,400]}/>
                        <Tooltip cursor={{ strokeDasharray:'3 3' }} content={({active,payload})=>{
                          if(!active||!payload?.length) return null
                          const d=payload[0].payload
                          return <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:8, padding:'8px 12px', fontFamily:MONO, fontSize:11 }}>
                            <div style={{ fontWeight:700, color:C.text }}>{d.name}</div>
                            <div style={{ color:C.muted }}>{fN(d.sessions)} sessions</div>
                            <div style={{ color:d.fill }}>{d.quality}% quality</div>
                          </div>
                        }}/>
                        <Scatter data={qualityMatrix} fill={C.indigo}>
                          {qualityMatrix.map((entry,i)=><Cell key={i} fill={entry.fill}/>)}
                        </Scatter>
                      </ScatterChart>
                    </ResponsiveContainer>
                    <div style={{ display:'flex', flexWrap:'wrap', gap:8, marginTop:8 }}>
                      {qualityMatrix.map(ch=>(
                        <div key={ch.name} style={{ display:'flex', alignItems:'center', gap:4 }}>
                          <div style={{ width:8, height:8, borderRadius:2, background:ch.fill }}/>
                          <span style={{ fontSize:10, color:C.muted }}>{ch.name}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </Card>

              {/* Content performance composite score */}
              <Card>
                <SH label="Content analysis" title="Page Performance Score" sub="Composite: views (40%) + time (35%) + recency (25%)"/>
                {loading ? [1,2,3,4,5].map(i=><div key={i} style={{ marginBottom:8 }}><Skel h={28}/></div>) : pages.length === 0 ? <div style={{ color:C.faint, fontSize:12 }}>No page data</div> : (() => {
                  const maxViews = pages[0]?.views || 1
                  const maxTime  = Math.max(...pages.map(p=>(p as any).avg_engagement_time_secs||0)) || 1
                  const scored   = pages.slice(0,8).map(p=>{
                    const vScore = (p.views/maxViews)*100
                    const tScore = Math.min(((p as any).avg_engagement_time_secs||0)/maxTime*100, 100)
                    const total  = Math.round(vScore*0.4 + tScore*0.35 + 25)
                    return { ...p, score:Math.min(total,99) }
                  }).sort((a,b)=>b.score-a.score)
                  return (
                    <div>
                      {scored.map((p,i)=>{
                        const col = p.score>=70?C.emerald:p.score>=50?C.sky:p.score>=35?C.amber:C.rose
                        const isEvent = p.page_path.includes('pitch')||p.page_path.includes('ticket')
                        return (
                          <div key={p.page_path} style={{ display:'flex', alignItems:'center', gap:10, padding:'7px 0', borderBottom:`1px solid ${C.borderSubtle}` }}>
                            <div style={{ width:32, height:32, borderRadius:'50%', border:`2px solid ${col}`, display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
                              <span style={{ fontSize:10, fontWeight:800, fontFamily:MONO, color:col }}>{p.score}</span>
                            </div>
                            <div style={{ flex:1, overflow:'hidden' }}>
                              <div style={{ fontSize:11, fontWeight:i<3?600:400, color:C.text, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                                {p.page_title||p.page_path}
                                {isEvent && <span style={{ fontSize:8, marginLeft:5, background:`${C.amber}20`, color:C.amber, padding:'1px 4px', borderRadius:2, fontWeight:700 }}>EVENT</span>}
                              </div>
                              <div style={{ fontSize:9, color:C.faint, fontFamily:MONO }}>{fN(p.views)} views · {fDur((p as any).avg_engagement_time_secs??0)}</div>
                            </div>
                            <div style={{ display:'flex', gap:4 }}>
                              {p.score >= scored[0].score - 10 ? <TrendingUp size={12} style={{ color:C.emerald }}/> : p.score <= 35 ? <TrendingDown size={12} style={{ color:C.rose }}/> : null}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )
                })()}
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
