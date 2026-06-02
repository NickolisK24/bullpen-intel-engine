import { useFetch } from '../../hooks/useFetch'
import { getSyncStatus } from '../../utils/api'
import { getSyncStatusView } from './syncStatusView'

const Metric = ({ label, value, muted = false }) => (
  <div className="min-w-0">
    <div className="text-[10px] uppercase tracking-widest text-chalk600">{label}:</div>
    <div className={`mt-1 break-words text-sm leading-snug ${muted ? 'text-chalk600' : 'text-chalk200'}`}>
      {value}
    </div>
  </div>
)

const TrustStrip = ({ dot, style = {}, title, status, metrics, helper }) => {
  const stripStyle = {
    borderColor: style.borderColor || '#242b35',
    backgroundColor: style.backgroundColor || 'rgba(26,31,38,0.44)',
    color: style.color || '#d1dce8',
  }

  return (
    <section
      className="w-full rounded-lg border px-4 py-3 sm:px-5 font-mono"
      style={stripStyle}
      title={title}
      aria-label="Dashboard data trust status"
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(180px,0.75fr)_2.25fr] lg:items-center">
        <div className="flex min-w-0 items-center gap-2">
          <span className="h-2 w-2 rounded-full flex-none" style={{ backgroundColor: dot }} />
          <div className="min-w-0 text-xs uppercase tracking-widest">
            <span className="text-chalk600">Data Status:</span>{' '}
            <span className="font-semibold">{status}</span>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          {metrics.map((metric) => (
            <Metric key={metric.label} {...metric} />
          ))}
        </div>
      </div>
      {helper && (
        <div className="mt-3 border-t border-dirt/70 pt-2 text-[11px] leading-relaxed text-chalk400">
          {helper}
        </div>
      )}
    </section>
  )
}

export function SyncStatusContent({ data, loading, error, now }) {
  if (loading) {
    return (
      <TrustStrip
        dot="#8899aa"
        status="Checking"
        metrics={[
          { label: 'Synced', value: 'Checking sync status', muted: true },
          { label: 'Data Through', value: 'Checking data coverage', muted: true },
          { label: 'Refresh Coverage', value: 'Checking refresh count', muted: true },
        ]}
      />
    )
  }
  if (error) {
    return (
      <TrustStrip
        dot="#4a5568"
        status="Limited"
        helper="Sync status unavailable."
        metrics={[
          { label: 'Synced', value: 'Unavailable', muted: true },
          { label: 'Data Through', value: 'Unavailable', muted: true },
          { label: 'Refresh Coverage', value: 'Unavailable', muted: true },
        ]}
      />
    )
  }

  const view = getSyncStatusView(data, now ? { now } : undefined)
  const title = [view.helper, ...view.limitations].filter(Boolean).join(' ')
  const syncValue = view.syncValue || (view.syncLabel === 'No data loaded' ? 'No data loaded' : 'Unavailable')
  const dataValue = view.dataValue || 'Unavailable'
  const coverageValue = view.coverageValue || 'Not reported'

  return (
    <TrustStrip
      dot={view.dot}
      style={view.style}
      title={title || undefined}
      status={view.healthLabel}
      helper={view.helper}
      metrics={[
        { label: view.syncLabel === 'No data loaded' ? 'Synced' : view.syncLabel, value: syncValue, muted: !view.syncValue },
        { label: view.dataLabel || 'Data Through', value: dataValue, muted: !view.dataValue },
        { label: 'Refresh Coverage', value: coverageValue, muted: !view.coverageValue },
      ]}
    />
  )
}

export default function SyncStatus() {
  const { data, loading, error } = useFetch(getSyncStatus)
  return <SyncStatusContent data={data} loading={loading} error={error} />
}
