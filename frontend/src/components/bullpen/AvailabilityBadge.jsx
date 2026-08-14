import {
  WORKLOAD_DATA_FIELD_LABEL,
  getAvailabilityBadgeView,
  getDataStateView,
} from './availabilityView'

export default function AvailabilityBadge({
  availability,
  showDataState = false,
  ariaLabelPrefix = 'Availability status',
}) {
  const badge = getAvailabilityBadgeView(availability)
  const dataState = String(availability?.data_state || 'unknown').toLowerCase()
  const showStateNote = showDataState && dataState && !['fresh', 'unknown'].includes(dataState)
  const stateView = showStateNote ? getDataStateView(dataState) : null

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <span
        className="inline-flex min-w-[6.75rem] items-center justify-center gap-1.5 rounded border px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-wide"
        style={badge.style}
        title={badge.tone}
        aria-label={`${ariaLabelPrefix}: ${badge.label}`}
      >
        <span className="h-1.5 w-1.5 rounded-full" style={badge.dotStyle} aria-hidden="true" />
        {badge.label}
      </span>
      {stateView && (
        // Named with the governed field label, not an invented "Data:". The
        // value belongs to the Workload Data family — one arm's workload
        // record — and is not the platform-level Data Status family.
        <span
          className="font-mono text-[10px] leading-none text-chalk400"
          title={stateView.message}
          aria-label={`${WORKLOAD_DATA_FIELD_LABEL}: ${stateView.label}`}
        >
          {WORKLOAD_DATA_FIELD_LABEL}: {stateView.label}
        </span>
      )}
    </span>
  )
}
