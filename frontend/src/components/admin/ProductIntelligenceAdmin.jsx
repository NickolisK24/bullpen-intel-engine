import { useEffect, useMemo, useState } from 'react'
import {
  PRODUCT_INTELLIGENCE_EVENT_NAMES,
  fetchProductIntelligenceEvents,
  fetchProductIntelligenceHeartbeat,
} from '../../utils/adminProductEvents'
import { ErrorState, LoadingPane, SectionHeader } from '../UI'

const ROBOTS_CONTENT = 'noindex,nofollow,noarchive'

function cleanValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function datePartsFor(date, { locale, timeZone } = {}) {
  const parts = new Intl.DateTimeFormat(locale, {
    ...(timeZone ? { timeZone } : {}),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date)
  const byType = Object.fromEntries(parts.map(part => [part.type, part.value]))
  return {
    year: Number(byType.year),
    month: Number(byType.month),
    day: Number(byType.day),
  }
}

function calendarDayIndex(parts) {
  if (!parts.year || !parts.month || !parts.day) return null
  return Math.floor(Date.UTC(parts.year, parts.month - 1, parts.day) / 86400000)
}

function localDateLabel(date, { locale, now, timeZone } = {}) {
  const eventIndex = calendarDayIndex(datePartsFor(date, { locale, timeZone }))
  const nowIndex = calendarDayIndex(datePartsFor(now, { locale, timeZone }))
  const diff = nowIndex === null || eventIndex === null ? null : nowIndex - eventIndex
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  return new Intl.DateTimeFormat(locale, {
    ...(timeZone ? { timeZone } : {}),
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date)
}

export function formatLocalEventTimestamp(value, {
  locale = undefined,
  now = new Date(),
  timeZone = undefined,
  includeTimeZone = true,
} = {}) {
  if (value === null || value === undefined || value === '') return '—'

  const date = new Date(value)
  const comparisonDate = new Date(now)
  if (Number.isNaN(date.getTime()) || Number.isNaN(comparisonDate.getTime())) return '—'

  const time = new Intl.DateTimeFormat(locale, {
    ...(timeZone ? { timeZone } : {}),
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    ...(includeTimeZone ? { timeZoneName: 'short' } : {}),
  }).format(date)
  return `${localDateLabel(date, { locale, now: comparisonDate, timeZone })} • ${time}`
}

export function payloadSummaryText(summary) {
  if (!summary || typeof summary !== 'object' || Array.isArray(summary)) return 'No payload'
  const entries = Object.entries(summary)
  if (entries.length === 0) return 'No payload'
  return entries
    .map(([key, value]) => `${key}: ${cleanValue(value)}`)
    .join(', ')
}

export function useNoindexRobotsMeta() {
  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    const existing = document.querySelector('meta[name="robots"]')
    const previousContent = existing?.getAttribute('content') || null
    const meta = existing || document.createElement('meta')
    meta.setAttribute('name', 'robots')
    meta.setAttribute('content', ROBOTS_CONTENT)
    if (!existing) document.head.appendChild(meta)

    return () => {
      if (existing) {
        if (previousContent) {
          existing.setAttribute('content', previousContent)
        } else {
          existing.removeAttribute('content')
        }
      } else {
        meta.remove()
      }
    }
  }, [])
}

export default function ProductIntelligenceAdmin() {
  useNoindexRobotsMeta()
  const [adminToken, setAdminToken] = useState('')
  const [eventName, setEventName] = useState('')
  const [limit, setLimit] = useState(25)
  const [data, setData] = useState(null)
  const [heartbeat, setHeartbeat] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const rows = useMemo(() => (
    Array.isArray(data?.events) ? data.events : []
  ), [data])
  const heartbeatRows = useMemo(() => (
    Array.isArray(heartbeat?.events) ? heartbeat.events : []
  ), [heartbeat])

  const handleSubmit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      // Load the recent rows and the heartbeat together. The heartbeat is a
      // best-effort companion: if it fails, the events view still renders.
      const [eventsResult, heartbeatResult] = await Promise.allSettled([
        fetchProductIntelligenceEvents({ adminToken, eventName, limit }),
        fetchProductIntelligenceHeartbeat({ adminToken }),
      ])
      if (eventsResult.status !== 'fulfilled') throw eventsResult.reason
      setData(eventsResult.value)
      setHeartbeat(heartbeatResult.status === 'fulfilled' ? heartbeatResult.value : null)
    } catch (err) {
      setError(err?.message || 'Product Intelligence events are unavailable.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ProductIntelligenceAdminView
      adminToken={adminToken}
      eventName={eventName}
      limit={limit}
      rows={rows}
      heartbeatRows={heartbeatRows}
      loading={loading}
      error={error}
      onAdminTokenChange={setAdminToken}
      onEventNameChange={setEventName}
      onLimitChange={setLimit}
      onSubmit={handleSubmit}
    />
  )
}

export function ProductIntelligenceAdminView({
  adminToken = '',
  eventName = '',
  limit = 25,
  rows = [],
  heartbeatRows = [],
  loading = false,
  error = null,
  onAdminTokenChange = () => {},
  onEventNameChange = () => {},
  onLimitChange = () => {},
  onSubmit = () => {},
}) {
  return (
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">
      <SectionHeader
        title="Product Intelligence Console"
        subtitle="Internal read-only event verification"
      />

      <section className="mb-5 rounded-lg border border-amber/25 bg-amber/5 p-4">
        <div className="font-mono text-[10px] uppercase tracking-widest text-amber/80">
          Operator-only
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk400">
          Inspect recent Product Intelligence facts without querying SQL. This console is read-only,
          admin-token gated, and shows anonymous-id presence rather than raw anonymous identifiers.
        </p>
      </section>

      <form
        className="mb-5 grid grid-cols-1 gap-3 rounded-lg border border-dirt bg-dugout p-4 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_8rem_auto]"
        onSubmit={onSubmit}
      >
        <label className="block">
          <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Admin token
          </span>
          <input
            type="password"
            value={adminToken}
            onChange={(event) => onAdminTokenChange(event.target.value)}
            placeholder="Required in production"
            className="mt-2 w-full rounded border border-dirt bg-field px-3 py-2 font-mono text-xs text-chalk200 outline-none focus:border-amber/60"
          />
        </label>

        <label className="block">
          <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Event
          </span>
          <select
            value={eventName}
            onChange={(event) => onEventNameChange(event.target.value)}
            className="mt-2 w-full rounded border border-dirt bg-field px-3 py-2 font-mono text-xs text-chalk200 outline-none focus:border-amber/60"
          >
            <option value="">All events</option>
            {PRODUCT_INTELLIGENCE_EVENT_NAMES.map(name => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Limit
          </span>
          <input
            type="number"
            min="1"
            max="100"
            value={limit}
            onChange={(event) => onLimitChange(event.target.value)}
            className="mt-2 w-full rounded border border-dirt bg-field px-3 py-2 font-mono text-xs text-chalk200 outline-none focus:border-amber/60"
          />
        </label>

        <div className="flex items-end">
          <button
            type="submit"
            className="w-full rounded border border-amber/35 bg-amber/10 px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={loading}
          >
            {loading ? 'Loading' : 'Load events'}
          </button>
        </div>
      </form>

      {loading ? (
        <LoadingPane message="Loading Product Intelligence events..." />
      ) : error ? (
        <ErrorState message={error} />
      ) : (
        <>
          <ProductEventHeartbeatTable rows={heartbeatRows} />
          <ProductEventsTable rows={rows} />
        </>
      )}
    </div>
  )
}

export function ProductEventHeartbeatTable({ rows = [] }) {
  if (!rows.length) return null

  return (
    <section className="mb-5 overflow-hidden rounded-lg border border-dirt bg-dugout">
      <div className="border-b border-dirt px-4 py-3 font-mono text-[10px] uppercase tracking-widest text-chalk500">
        Event flow (count &amp; most recent)
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-dirt text-left text-xs">
          <thead className="bg-field/60 font-mono uppercase tracking-widest text-chalk500">
            <tr>
              <th className="px-3 py-2 font-normal">Event name</th>
              <th className="px-3 py-2 font-normal">Count</th>
              <th className="px-3 py-2 font-normal">Most recent event</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dirt">
            {rows.map(row => (
              <tr key={row.event_name} className="align-top">
                <td className="whitespace-nowrap px-3 py-2 font-mono text-chalk200">{cleanValue(row.event_name)}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono text-chalk300">{cleanValue(row.count)}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono text-chalk400">{formatLocalEventTimestamp(row.most_recent)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function ProductEventsTable({ rows = [] }) {
  if (!rows.length) {
    return (
      <section className="rounded-lg border border-dirt bg-dugout p-5">
        <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
          Recent events
        </div>
        <p className="mt-2 text-sm text-chalk400">
          No Product Intelligence events returned for this filter.
        </p>
      </section>
    )
  }

  return (
    <section className="overflow-hidden rounded-lg border border-dirt bg-dugout">
      <div className="border-b border-dirt px-4 py-3 font-mono text-[10px] uppercase tracking-widest text-chalk500">
        Recent events
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-dirt text-left text-xs">
          <thead className="bg-field/60 font-mono uppercase tracking-widest text-chalk500">
            <tr>
              <th className="px-3 py-2 font-normal">Event</th>
              <th className="px-3 py-2 font-normal">Occurred</th>
              <th className="px-3 py-2 font-normal">User</th>
              <th className="px-3 py-2 font-normal">Anon</th>
              <th className="px-3 py-2 font-normal">Team</th>
              <th className="px-3 py-2 font-normal">Source</th>
              <th className="px-3 py-2 font-normal">Payload summary</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dirt">
            {rows.map(row => (
              <tr key={row.id || `${row.event_name}-${row.occurred_at}`} className="align-top">
                <td className="whitespace-nowrap px-3 py-2 font-mono text-chalk200">{cleanValue(row.event_name)}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono text-chalk400">{formatLocalEventTimestamp(row.occurred_at)}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono text-chalk300">{cleanValue(row.user_id)}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono text-chalk300">{cleanValue(row.anon_id_present)}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono text-chalk300">{cleanValue(row.team_id)}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono text-chalk300">{cleanValue(row.source)}</td>
                <td className="min-w-[20rem] px-3 py-2 text-chalk400">{payloadSummaryText(row.payload_summary)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
