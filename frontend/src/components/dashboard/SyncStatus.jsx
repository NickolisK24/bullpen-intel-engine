import {
  DATA_THROUGH_LABEL,
  LAST_CHECKED_LABEL,
  LAST_DATA_UPDATE_LABEL,
} from '../../utils/bullpenConcepts'
import { useFetch } from '../../hooks/useFetch'
import { getSyncStatus } from '../../utils/api'
import {
  DATA_STATUS_LABELS,
  freshnessIsCurrent,
  getFreshnessAuthorityStatusView,
  getSyncStatusView,
} from './syncStatusView'

const Metric = ({ label, value, muted = false }) => (
  <div className="min-w-0">
    <div className="text-[10px] uppercase tracking-widest text-chalk600">{label}:</div>
    <div className={`mt-1 break-words text-sm leading-snug ${muted ? 'text-chalk600' : 'text-chalk200'}`}>
      {value}
    </div>
  </div>
)

const TrustStrip = ({ dot, style = {}, title, status, metrics, helper, governed = true }) => {
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
      aria-label="Dashboard data status"
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(180px,0.75fr)_2.25fr] lg:items-center">
        <div className="flex min-w-0 items-center gap-2">
          <span className="h-2 w-2 rounded-full flex-none" style={{ backgroundColor: dot }} />
          <div className="min-w-0 text-xs uppercase tracking-widest">
            {governed ? (
              <>
                <span className="text-chalk600">Data Status:</span>{' '}
                <span className="font-semibold">{status}</span>
              </>
            ) : status}
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

export function SyncStatusContent({
  data,
  loading,
  error,
  now,
  freshnessAuthority,
  freshnessLoading = false,
  freshnessError = null,
}) {
  const hasFreshnessAuthority = freshnessAuthority !== undefined && freshnessAuthority !== null
  const authorityIsCurrent = hasFreshnessAuthority && freshnessIsCurrent(freshnessAuthority)
  const authorityView = hasFreshnessAuthority
    ? getFreshnessAuthorityStatusView(freshnessAuthority, authorityIsCurrent)
    : null

  if (freshnessLoading || (loading && !hasFreshnessAuthority)) {
    return (
      <TrustStrip
        dot="#8899aa"
        status="Checking data status"
        governed={false}
        metrics={[
          { label: LAST_CHECKED_LABEL, value: 'Checking sync status', muted: true },
          { label: LAST_DATA_UPDATE_LABEL, value: 'Checking data update', muted: true },
          { label: DATA_THROUGH_LABEL, value: 'Checking data coverage', muted: true },
        ]}
      />
    )
  }
  if (error) {
    return (
      <TrustStrip
        dot={authorityView?.dot || '#4a5568'}
        style={authorityView?.style}
        status={authorityView?.healthLabel || DATA_STATUS_LABELS.UNAVAILABLE}
        helper={authorityView?.healthLabel === DATA_STATUS_LABELS.CURRENT
          ? 'The published view remains current. Refresh status is unavailable.'
          : 'Refresh status unavailable.'}
        metrics={[
          { label: LAST_CHECKED_LABEL, value: 'Unavailable', muted: true },
          { label: LAST_DATA_UPDATE_LABEL, value: 'Unavailable', muted: true },
          { label: DATA_THROUGH_LABEL, value: 'Unavailable', muted: true },
        ]}
      />
    )
  }

  if (loading) {
    return (
      <TrustStrip
        dot={authorityView.dot}
        style={authorityView.style}
        status={authorityView.healthLabel}
        helper="Published data status is available while refresh details are checked."
        metrics={[
          { label: LAST_CHECKED_LABEL, value: 'Checking sync status', muted: true },
          { label: LAST_DATA_UPDATE_LABEL, value: 'Checking data update', muted: true },
          { label: DATA_THROUGH_LABEL, value: 'Checking data coverage', muted: true },
        ]}
      />
    )
  }

  if (freshnessError && !hasFreshnessAuthority) {
    return (
      <TrustStrip
        dot="#4a5568"
        status={DATA_STATUS_LABELS.UNAVAILABLE}
        helper="The published data status could not be confirmed."
        metrics={[
          { label: LAST_CHECKED_LABEL, value: 'Unavailable', muted: true },
          { label: LAST_DATA_UPDATE_LABEL, value: 'Unavailable', muted: true },
          { label: DATA_THROUGH_LABEL, value: 'Unavailable', muted: true },
        ]}
      />
    )
  }

  const view = getSyncStatusView(data, { now, freshnessAuthority })
  const title = [view.helper, ...view.limitations].filter(Boolean).join(' ')
  const lastCheckedValue = view.lastCheckedValue || 'Unavailable'
  const lastDataUpdateValue = view.lastDataUpdateValue || (
    view.syncLabel === 'No data loaded' ? 'No data loaded' : 'Unavailable'
  )
  const dataValue = view.dataValue || 'Unavailable'

  return (
    <TrustStrip
      dot={view.dot}
      style={view.style}
      title={title || undefined}
      status={view.healthLabel}
      helper={view.helper}
      metrics={[
        { label: view.lastCheckedLabel || LAST_CHECKED_LABEL, value: lastCheckedValue, muted: !view.lastCheckedValue },
        { label: view.lastDataUpdateLabel || LAST_DATA_UPDATE_LABEL, value: lastDataUpdateValue, muted: !view.lastDataUpdateValue },
        { label: view.dataLabel || DATA_THROUGH_LABEL, value: dataValue, muted: !view.dataValue },
      ]}
    />
  )
}

export default function SyncStatus() {
  const { data, loading, error } = useFetch(getSyncStatus)
  return <SyncStatusContent data={data} loading={loading} error={error} />
}
