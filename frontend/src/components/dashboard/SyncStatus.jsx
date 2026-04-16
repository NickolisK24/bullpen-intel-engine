import { useFetch } from '../../hooks/useFetch'
import { getSyncStatus } from '../../utils/api'

const STALE_HOURS = 36

const fmtStatusDate = (iso) => {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const date = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  return `${date} at ${time}`
}

export default function SyncStatus() {
  const { data, loading, error } = useFetch(getSyncStatus)

  if (loading) {
    return (
      <div className="inline-flex items-center gap-2 px-3 py-1 rounded-md border border-dirt bg-chalk/40 text-[11px] font-mono text-chalk600">
        <span className="h-1.5 w-1.5 rounded-full bg-chalk400 animate-pulse" />
        Checking sync…
      </div>
    )
  }

  if (error) {
    return (
      <div className="inline-flex items-center gap-2 px-3 py-1 rounded-md border border-dirt bg-chalk/40 text-[11px] font-mono text-chalk600">
        <span className="h-1.5 w-1.5 rounded-full bg-chalk600" />
        Sync status unavailable
      </div>
    )
  }

  const { last_sync, status, pitchers_updated } = data || {}
  const formatted = fmtStatusDate(last_sync)

  if (!last_sync) {
    return (
      <div className="inline-flex items-center gap-2 px-3 py-1 rounded-md border border-dirt bg-chalk/40 text-[11px] font-mono text-chalk600">
        <span className="h-1.5 w-1.5 rounded-full bg-chalk600" />
        Never synced
      </div>
    )
  }

  // Flag anything older than 36h in amber so the user notices.
  const ageHours = (Date.now() - new Date(last_sync).getTime()) / 3_600_000
  const stale    = ageHours > STALE_HOURS
  const failed   = status === 'error'

  const dotColor  = failed ? '#ef4444' : stale ? '#f5a623' : '#10b981'
  const textColor = failed
    ? { color: '#fca5a5' }
    : stale
      ? { color: '#f5a623' }
      : { color: '#d1dce8' }

  return (
    <div
      className="inline-flex items-center gap-2 px-3 py-1 rounded-md border text-[11px] font-mono"
      style={{
        borderColor: stale || failed ? `${dotColor}55` : '#242b35',
        backgroundColor: stale || failed ? `${dotColor}12` : 'rgba(26,31,38,0.4)',
        ...textColor,
      }}
      title={status === 'no_games' ? 'No games found — offseason skip.' : undefined}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: dotColor }}
      />
      <span>
        Last synced: {formatted}
        {stale && !failed && <span className="ml-1 opacity-80">· stale</span>}
        {failed && <span className="ml-1 opacity-80">· error</span>}
      </span>
      {pitchers_updated != null && pitchers_updated > 0 && (
        <span className="text-chalk600 normal-case">
          · {pitchers_updated} pitchers
        </span>
      )}
    </div>
  )
}
