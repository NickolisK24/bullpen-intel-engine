import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthState } from '../../hooks/useAuthState'
import {
  fetchTrafficSummary,
  TRAFFIC_REPORTING_PATH,
  TRAFFIC_REPORTING_RANGES,
} from '../../utils/trafficReporting'
import { ErrorState, LoadingPane, SectionHeader } from '../UI'

export const TRAFFIC_ROBOTS_CONTENT = 'noindex,nofollow'
export const TRAFFIC_EMPTY_COPY = 'No external traffic has been recorded in this period. Internal browsers and known bots are excluded.'

const RANGE_LABELS = { '7d': '7', '30d': '30', '90d': '90', all: 'All' }
const METRIC_LABELS = {
  external_visitors: 'External Visitors',
  sessions: 'Sessions',
  page_views: 'Page Views',
  returning_visitors: 'Returning Visitors',
  new_visitors: 'New Visitors',
  multi_page_sessions: 'Multi-Page Sessions',
  pages_per_session: 'Pages per Session',
}

function formatValue(value) {
  if (value === null || value === undefined) return '—'
  return typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value)
}

function formatSurface(value) {
  return String(value || 'Unknown').replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())
}

function formatPercentage(value) {
  if (value === null || value === undefined) return 'Percentage unavailable'
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`
}

function comparisonText(comparison, metric) {
  if (!comparison?.available) return 'Comparison unavailable'
  const change = comparison.changes?.[metric]
  if (!change || change.percent === null) return 'No percentage from prior zero'
  const prefix = change.percent > 0 ? '+' : ''
  return `${prefix}${formatValue(change.percent)}% vs prior period`
}

export function useTrafficRobotsMeta() {
  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    const existing = document.querySelector('meta[name="robots"]')
    const previousContent = existing?.getAttribute('content') || null
    const meta = existing || document.createElement('meta')
    meta.setAttribute('name', 'robots')
    meta.setAttribute('content', TRAFFIC_ROBOTS_CONTENT)
    if (!existing) document.head.appendChild(meta)
    return () => {
      if (existing) {
        if (previousContent) existing.setAttribute('content', previousContent)
        else existing.removeAttribute('content')
      } else {
        meta.remove()
      }
    }
  }, [])
}

export default function TrafficIntelligenceAdmin() {
  useTrafficRobotsMeta()
  const auth = useAuthState()
  if (auth.loading) return <TrafficAccessState state="checking" />
  if (!auth.authenticated) return <TrafficAccessState state="unauthenticated" />
  return <TrafficDashboardController />
}

function TrafficDashboardController() {
  const [range, setRange] = useState('7d')
  const [retryKey, setRetryKey] = useState(0)
  const [state, setState] = useState({ data: null, loading: true, error: null })

  useEffect(() => {
    let active = true
    setState(previous => ({ ...previous, loading: true, error: null }))
    fetchTrafficSummary(range)
      .then(data => {
        if (active) setState({ data, loading: false, error: null })
      })
      .catch(error => {
        if (active) setState(previous => ({ ...previous, loading: false, error }))
      })
    return () => {
      active = false
    }
  }, [range, retryKey])

  return (
    <TrafficIntelligenceAdminView
      {...state}
      range={range}
      onRangeChange={setRange}
      onRetry={() => setRetryKey(value => value + 1)}
    />
  )
}

export function TrafficAccessState({ state = 'unauthenticated' }) {
  const checking = state === 'checking'
  const forbidden = state === 'forbidden'
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-3xl items-center p-4 sm:p-6" data-traffic-access={state}>
      <div className="w-full border border-dirt bg-dugout p-5">
        {checking ? (
          <LoadingPane message="Checking access..." />
        ) : (
          <>
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">Internal reporting</div>
            <h1 className="mt-2 font-display text-3xl leading-none tracking-wider text-chalk100">Access Restricted</h1>
            <p className="mt-3 text-sm leading-relaxed text-chalk400">
              {forbidden
                ? 'This account is not authorized to view traffic reporting.'
                : 'Sign in with an authorized account to view traffic reporting.'}
            </p>
            {!forbidden && (
              <Link
                to={`/signin?next=${encodeURIComponent(TRAFFIC_REPORTING_PATH)}`}
                className="mt-4 inline-flex border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-amber"
              >
                Sign in
              </Link>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export function TrafficIntelligenceAdminView({
  data = null,
  range = '7d',
  loading = false,
  error = null,
  onRangeChange = () => {},
  onRetry = () => {},
}) {
  if (error?.status === 401) return <TrafficAccessState state="unauthenticated" />
  if (error?.status === 403) return <TrafficAccessState state="forbidden" />

  const empty = !loading && data?.summary?.page_views === 0
  return (
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8" data-traffic-dashboard>
      <SectionHeader title="Traffic Intelligence" subtitle="Internal view of external discovery, exploration, and return activity" />
      <section className="mb-5 border border-dirt bg-dugout p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">Reporting timezone</div>
            <div className="mt-1 text-sm text-chalk300">{data?.timezone || 'America/New_York'}</div>
          </div>
          <div className="flex gap-2" aria-label="Traffic reporting range">
            {TRAFFIC_REPORTING_RANGES.map(option => (
              <button
                type="button"
                key={option}
                aria-pressed={range === option}
                onClick={() => onRangeChange(option)}
                className={`border px-3 py-2 font-mono text-[10px] uppercase tracking-widest ${range === option ? 'border-amber/60 bg-amber/10 text-amber' : 'border-dirt text-chalk500'}`}
              >
                {RANGE_LABELS[option]}
              </button>
            ))}
          </div>
        </div>
      </section>

      {loading && !data ? (
        <LoadingPane message="Loading traffic intelligence..." />
      ) : error ? (
        <div>
          <ErrorState message="Traffic intelligence is unavailable." />
          <button type="button" onClick={onRetry} className="mt-3 border border-amber/40 px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-amber">Retry</button>
        </div>
      ) : data ? (
        <>
          {empty && (
            <div className="mb-5 border border-dirt bg-dugout p-5 text-sm leading-relaxed text-chalk400">{TRAFFIC_EMPTY_COPY}</div>
          )}
          <TrafficReport report={data} />
        </>
      ) : null}
    </div>
  )
}

export function TrafficReport({ report }) {
  const summaryEntries = Object.keys(METRIC_LABELS)
  return (
    <>
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Traffic summary">
        {summaryEntries.map(metric => (
          <article key={metric} className="border border-dirt bg-dugout p-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{METRIC_LABELS[metric]}</div>
            <div className="mt-2 font-display text-3xl text-chalk100">{formatValue(report.summary?.[metric])}</div>
            <div className="mt-2 text-xs text-chalk500">{comparisonText(report.comparison, metric)}</div>
          </article>
        ))}
      </section>

      {!report.comparison?.available && (
        <p className="mt-3 text-xs text-chalk500">Comparison unavailable: {formatSurface(report.comparison?.reason)}</p>
      )}

      <DailyTrafficChart rows={report.daily || []} />
      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
        <AcquisitionSection data={report.acquisition || {}} />
        <CountSection title="Session Depth" rows={[
          ['Single-Page Sessions', report.session_depth?.single_page_sessions],
          ['Multi-Page Sessions', report.session_depth?.multi_page_sessions],
          ['Pages per Session', report.session_depth?.pages_per_session],
        ]} />
        <RankedSection title="Landing Surfaces" rows={report.landing_surfaces} labelKey="surface" valueKey="sessions" />
        <RankedSection title="Most Visited Surfaces" rows={report.most_visited_surfaces} labelKey="surface" valueKey="page_views" />
        <RankedSection title="Top Referrer Domains" rows={report.top_referrers} labelKey="referrer_domain" valueKey="sessions" />
        <CampaignSection rows={report.campaigns || []} />
        <BullpenSection data={report.bullpen_exploration || {}} />
        <HealthSection data={report.measurement_health || {}} />
      </div>
      <MetricDefinitions definitions={report.definitions || {}} />
    </>
  )
}

export function DailyTrafficChart({ rows = [] }) {
  const max = useMemo(() => Math.max(1, ...rows.map(row => row.page_views || 0)), [rows])
  return (
    <section className="mt-5 border border-dirt bg-dugout p-4" aria-label="Daily traffic">
      <h2 className="font-display text-xl tracking-wide text-chalk100">Daily Traffic</h2>
      <div className="mt-4 flex h-40 items-end gap-1" role="img" aria-label="Daily page views chart">
        {rows.map(row => (
          <div key={row.date} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1" title={`${row.date}: ${row.page_views} page views`}>
            <div className="w-full bg-amber/60" style={{ height: `${Math.max(2, (row.page_views / max) * 120)}px` }} />
            <span className="hidden font-mono text-[8px] text-chalk600 sm:block">{row.date.slice(5)}</span>
          </div>
        ))}
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">Daily visitors, sessions, and page views</caption>
          <thead><tr className="border-b border-dirt font-mono text-[10px] uppercase tracking-widest text-chalk500"><th className="py-2 pr-3">Date</th><th className="px-3 py-2 text-right">Visitors</th><th className="px-3 py-2 text-right">Sessions</th><th className="py-2 pl-3 text-right">Page Views</th></tr></thead>
          <tbody>{rows.map(row => <tr key={row.date} className="border-b border-dirt/60 last:border-0"><th scope="row" className="py-2 pr-3 font-normal text-chalk400">{row.date}</th><td className="px-3 py-2 text-right font-mono text-chalk200">{formatValue(row.visitors)}</td><td className="px-3 py-2 text-right font-mono text-chalk200">{formatValue(row.sessions)}</td><td className="py-2 pl-3 text-right font-mono text-chalk200">{formatValue(row.page_views)}</td></tr>)}</tbody>
        </table>
      </div>
    </section>
  )
}

function SectionShell({ title, children }) {
  return <section className="border border-dirt bg-dugout p-4"><h2 className="font-display text-xl tracking-wide text-chalk100">{title}</h2><div className="mt-3">{children}</div></section>
}

function CountSection({ title, rows }) {
  return <SectionShell title={title}><dl className="space-y-2">{rows.map(([label, value]) => <div key={label} className="flex justify-between gap-3 text-sm"><dt className="text-chalk500">{label}</dt><dd className="font-mono text-chalk200">{formatValue(value)}</dd></div>)}</dl></SectionShell>
}

function AcquisitionSection({ data }) {
  return <SectionShell title="Acquisition"><dl className="space-y-2">{[
    ['Campaign', data.campaign],
    ['Referral', data.referral],
    ['Direct / Unknown', data.direct_unknown],
  ].map(([label, value]) => <div key={label} className="flex justify-between gap-3 text-sm"><dt className="text-chalk500">{label}</dt><dd className="text-right font-mono text-chalk200">{formatValue(value?.sessions)} sessions · {formatPercentage(value?.percentage)}</dd></div>)}</dl></SectionShell>
}

function RankedSection({ title, rows = [], labelKey, valueKey }) {
  return <SectionShell title={title}>{rows.length ? <ol className="space-y-2">{rows.map((row, index) => <li key={`${row[labelKey]}-${index}`} className="flex justify-between gap-3 text-sm"><span className="truncate text-chalk400">{labelKey === 'surface' ? formatSurface(row[labelKey]) : row[labelKey]}</span><span className="font-mono text-chalk200">{formatValue(row[valueKey])}</span></li>)}</ol> : <p className="text-sm text-chalk600">No data in this period.</p>}</SectionShell>
}

function CampaignSection({ rows }) {
  return <SectionShell title="Campaigns">{rows.length ? <div className="space-y-3">{rows.map((row, index) => <div key={`${row.utm_source}-${row.utm_medium}-${row.utm_campaign}-${index}`} className="border-b border-dirt pb-2 text-sm last:border-0"><div className="text-chalk300">{row.utm_source || 'Unknown source'} / {row.utm_medium || 'Unknown medium'}</div><div className="mt-1 text-xs text-chalk600">{row.utm_campaign || 'No campaign name'} · {formatValue(row.sessions)} sessions</div></div>)}</div> : <p className="text-sm text-chalk600">No campaign-attributed sessions.</p>}</SectionShell>
}

function BullpenSection({ data }) {
  return <SectionShell title="Bullpen Exploration"><dl className="space-y-2">{[
    ['Bullpen Board Views', data.bullpen_board_views],
    ['Compare Bullpens Views', data.compare_bullpens_views],
    ['All Pitchers Views', data.all_pitchers_views],
    ['Pitcher Context Page Views', data.pitcher_context_page_views],
  ].map(([label, value]) => <div key={label} className="flex justify-between text-sm"><dt className="text-chalk500">{label}</dt><dd className="font-mono text-chalk200">{formatValue(value)}</dd></div>)}</dl><div className="mt-3"><RankedList rows={data.team_contexts || []} labelKey="team_ref" valueKey="page_views" /></div></SectionShell>
}

function RankedList({ rows, labelKey, valueKey }) {
  return rows.length ? <ol className="space-y-1">{rows.map(row => <li key={row[labelKey]} className="flex justify-between text-xs"><span className="text-chalk500">{row[labelKey]}</span><span className="font-mono text-chalk300">{formatValue(row[valueKey])}</span></li>)}</ol> : <p className="text-xs text-chalk600">No team context recorded.</p>
}

function HealthSection({ data }) {
  const selected = data.selected_period || {}
  return <SectionShell title="Measurement Health"><dl className="space-y-2">{[
    ['Measurement Started At', data.measurement_started_at],
    ['Last External Page View At', data.last_external_page_view_at],
    ['Last Canonical Page View At', data.last_canonical_page_view_at],
    ['Registered Internal Browser IDs', data.registered_internal_browser_ids],
    ['Selected-Period Canonical Page Views', selected.canonical_page_views],
    ['Selected-Period External Page Views', selected.external_page_views],
    ['Selected-Period Excluded Internal Page Views', selected.excluded_internal_page_views],
    ['Selected-Period Excluded Bot Page Views', selected.excluded_bot_page_views],
    ['Selected-Period Unknown-Device External Page Views', selected.unknown_device_external_page_views],
  ].map(([label, value]) => <div key={label} className="flex justify-between gap-3 text-sm"><dt className="text-chalk500">{label}</dt><dd className="break-all text-right font-mono text-chalk200">{formatValue(value)}</dd></div>)}</dl></SectionShell>
}

function MetricDefinitions({ definitions }) {
  return <section className="mt-5 border border-dirt bg-field/60 p-4"><h2 className="font-display text-xl tracking-wide text-chalk100">Metric Definitions</h2><p className="mt-2 text-sm font-semibold text-chalk300">External Visitors represents distinct browser identities, not confirmed individual people.</p><dl className="mt-4 space-y-3">{Object.entries(METRIC_LABELS).map(([key, label]) => <div key={key}><dt className="font-mono text-[10px] uppercase tracking-widest text-chalk500">{label}</dt><dd className="mt-1 text-sm leading-relaxed text-chalk500">{definitions[key] || 'Definition unavailable.'}</dd></div>)}</dl></section>
}
