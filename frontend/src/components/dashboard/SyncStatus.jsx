import { useFetch } from '../../hooks/useFetch'
import { getSyncStatus } from '../../utils/api'

const STALE_HOURS = 36
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// Format an ISO datetime (a real sync timestamp) as "Jun 3 at 2:05 PM".
const fmtSyncTime = (iso) => {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const date = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  return `${date} at ${time}`
}

// Format a 'YYYY-MM-DD' game date as "Sep 10, 2025" without timezone drift.
const fmtSnapshotDate = (ymd) => {
  if (!ymd) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd)
  if (!m) return null
  const [, y, mm, dd] = m
  return `${MONTHS[Number(mm) - 1]} ${Number(dd)}, ${y}`
}

const Pill = ({ dot, style = {}, title, children }) => (
  <div
    className="inline-flex items-center gap-2 px-3 py-1 rounded-md border text-[11px] font-mono"
    style={{ borderColor: '#242b35', backgroundColor: 'rgba(26,31,38,0.4)', ...style }}
    title={title}
  >
    <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: dot }} />
    {children}
  </div>
)

export default function SyncStatus() {
  const { data, loading, error } = useFetch(getSyncStatus)

  if (loading) {
    return <Pill dot="#8899aa"><span className="animate-pulse">Checking sync…</span></Pill>
  }
  if (error) {
    return <Pill dot="#4a5568">Sync status unavailable</Pill>
  }

  const { last_sync, status, pitchers_updated } = data || {}
  const snapshotDate = data?.data?.latest_game_date
  const logCount     = data?.data?.game_logs

  // 1) A sync ran and failed.
  if (status === 'error') {
    return (
      <Pill dot="#ef4444" style={{ borderColor: '#ef444455', backgroundColor: '#ef444412', color: '#fca5a5' }}
            title={data?.message || undefined}>
        <span>Last sync failed{last_sync ? `: ${fmtSyncTime(last_sync)}` : ''}</span>
      </Pill>
    )
  }

  // 2) A sync succeeded — show the real timestamp (amber if stale).
  if (last_sync) {
    const ageHours = (Date.now() - new Date(last_sync).getTime()) / 3_600_000
    const stale = ageHours > STALE_HOURS
    const dot = stale ? '#f5a623' : '#10b981'
    return (
      <Pill dot={dot}
            title="Pitchers refreshed in the latest sync (those with games in the recent 14-day window)."
            style={stale ? { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' } : { color: '#d1dce8' }}>
        <span>
          Last synced: {fmtSyncTime(last_sync)}
          {stale && <span className="ml-1 opacity-80">· stale</span>}
        </span>
        {pitchers_updated != null && pitchers_updated > 0 && (
          <span className="text-chalk600 normal-case">· {pitchers_updated.toLocaleString()} refreshed</span>
        )}
      </Pill>
    )
  }

  // 3) No sync has run, but data is loaded → historical snapshot (not broken).
  if (logCount > 0 && snapshotDate) {
    return (
      <Pill dot="#f5a623"
            style={{ borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' }}
            title="Historical snapshot loaded — no live sync has run.">
        <span>Snapshot · through {fmtSnapshotDate(snapshotDate)}</span>
      </Pill>
    )
  }

  // 4) No sync and no data.
  return <Pill dot="#4a5568">No data loaded</Pill>
}
