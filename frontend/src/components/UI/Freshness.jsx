import {
  formatDateOnly,
  formatUtcDateTimeEt,
} from '../../utils/dateDisplay'

const BADGE_TONE = {
  current: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  stale: 'border-amber/35 bg-amber/10 text-amber',
  limited: 'border-amber/35 bg-amber/10 text-amber',
  unavailable: 'border-dirt bg-field/60 text-chalk400',
  sample: 'border-sky-300/30 bg-sky-300/10 text-sky-100',
}

const BADGE_TEXT = {
  current: 'Freshness: Current',
  stale: 'Refresh delayed',
  limited: 'Freshness: Limited',
  unavailable: 'No current bullpen read available',
  sample: 'Sample intelligence state',
}

export function formatFreshnessDate(value, { includeYear = false } = {}) {
  const formatted = formatDateOnly(value, { month: 'short' })
  if (!formatted) return null
  return includeYear ? formatted : formatted.replace(/,\s*\d{4}$/, '')
}

function normalizeFreshnessState(state, freshness) {
  const explicit = String(state || '').toLowerCase()
  if (BADGE_TEXT[explicit]) return explicit
  if (!freshness || typeof freshness !== 'object') return null

  const freshnessState = String(
    freshness.freshness_state || freshness.state || '',
  ).toLowerCase()
  const syncStatus = String(freshness.sync_status || '').toLowerCase()

  if (freshness.sample === true || freshnessState === 'sample') return 'sample'
  if (
    freshness.is_stale === true ||
    freshness.is_current === false ||
    freshnessState === 'stale' ||
    freshnessState === 'historical'
  ) return 'stale'
  if (syncStatus === 'failed' || syncStatus === 'error') return 'limited'
  if (freshness.is_current === true || freshness.data_through || freshness.last_successful_sync) {
    return 'current'
  }
  return null
}

export function FreshnessBadge({
  state,
  freshness,
  label,
  className = '',
}) {
  const normalized = normalizeFreshnessState(state, freshness)
  if (!normalized && !label) return null
  const display = label || BADGE_TEXT[normalized]
  const tone = BADGE_TONE[normalized] || BADGE_TONE.limited

  return (
    <span
      className={`inline-flex min-h-7 items-center rounded border px-2.5 py-1 font-mono text-[11px] uppercase tracking-widest ${tone} ${className}`}
    >
      {display}
    </span>
  )
}

export function DataThroughStamp({
  date,
  label = 'Data through',
  includeYear = false,
  className = '',
}) {
  const formatted = formatFreshnessDate(date, { includeYear })
  if (!formatted) return null
  return (
    <span className={`inline-flex min-h-7 items-center rounded border border-dirt bg-field/50 px-2.5 py-1 font-mono text-[11px] uppercase tracking-widest text-chalk400 ${className}`}>
      {label} {formatted}
    </span>
  )
}

export function LastSyncLabel({
  value,
  label = 'Last synced',
  includeDate = false,
  className = '',
}) {
  const formatted = formatUtcDateTimeEt(value, { includeDate })
  if (!formatted) return null
  return (
    <span className={`inline-flex min-h-7 items-center rounded border border-dirt bg-field/50 px-2.5 py-1 font-mono text-[11px] uppercase tracking-widest text-chalk500 ${className}`}>
      {label} {formatted}
    </span>
  )
}

export function UnavailableDataState({
  title = 'No current bullpen read available.',
  message,
  detail,
  onRetry,
  className = '',
  titleClassName = 'font-display text-2xl leading-tight tracking-wide text-chalk100',
  messageClassName = 'mt-2 max-w-3xl text-sm leading-relaxed text-chalk500',
}) {
  return (
    <div
      className={`border border-dirt bg-dugout p-4 ${className}`}
      role="status"
      aria-live="polite"
    >
      <h3 className={titleClassName}>
        {title}
      </h3>
      {message && (
        <p className={messageClassName}>
          {message}
        </p>
      )}
      {detail && (
        <p className="mt-3 font-mono text-xs uppercase tracking-wider text-chalk500">
          {detail}
        </p>
      )}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded border border-dirt px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
        >
          Try Again
        </button>
      )}
    </div>
  )
}
