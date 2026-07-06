import {
  formatDateOnly,
  formatUtcDateTimeEt,
} from '../../utils/dateDisplay'
import {
  freshnessDataThrough,
  freshnessIsCurrent,
} from '../dashboard/syncStatusView'

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

const NON_LIVE_FRESHNESS_STATES = new Set([
  'sample',
  'sample_state',
  'static_sample',
  'demo',
  'demo_state',
  'deterministic_sample',
  'deterministic_sample_state',
])

export function formatFreshnessDate(value, { includeYear = false } = {}) {
  const formatted = formatDateOnly(value, { month: 'short' })
  if (!formatted) return null
  return includeYear ? formatted : formatted.replace(/,\s*\d{4}$/, '')
}

function normalizedText(value) {
  return String(value || '').trim().toLowerCase().replace(/[-\s]+/g, '_')
}

export function isSampleFreshness(freshness) {
  if (!freshness || typeof freshness !== 'object') return false
  if (
    freshness.sample === true ||
    freshness.demo === true ||
    freshness.is_demo === true ||
    freshness.isDemo === true ||
    freshness.non_live === true ||
    freshness.nonLive === true ||
    freshness.is_live === false ||
    freshness.isLive === false
  ) return true

  const state = normalizedText(freshness.freshness_state || freshness.freshnessState || freshness.state)
  if (NON_LIVE_FRESHNESS_STATES.has(state)) return true

  for (const key of [
    'status',
    'source',
    'data_source',
    'dataSource',
    'metadata_source',
    'metadataSource',
    'mode',
    'served_from',
    'servedFrom',
    'collection_id',
    'collectionId',
  ]) {
    const value = normalizedText(freshness[key])
    if (NON_LIVE_FRESHNESS_STATES.has(value)) return true
    if (/(^|_)(sample|demo)($|_)/.test(value)) return true
  }

  return false
}

function normalizeFreshnessMetadata(freshness) {
  if (!freshness || typeof freshness !== 'object') return null

  const freshnessState = String(
    freshness.freshness_state || freshness.freshnessState || freshness.state || '',
  ).toLowerCase()
  const syncStatus = String(freshness.sync_status || freshness.syncStatus || '').toLowerCase()

  if (isSampleFreshness(freshness)) return 'sample'
  if (freshnessIsCurrent(freshness)) return 'current'
  if (
    freshness.fail_closed === true ||
    freshness.failClosed === true ||
    freshness.is_stale === true ||
    freshness.isStale === true ||
    freshness.is_current === false ||
    freshness.isCurrent === false ||
    freshnessState === 'stale' ||
    freshnessState === 'historical'
  ) return 'stale'
  if (syncStatus === 'failed' || syncStatus === 'error') return 'limited'
  if (
    freshness.is_current === true ||
    freshness.isCurrent === true ||
    freshnessDataThrough(freshness) ||
    freshness.last_successful_sync ||
    freshness.lastSuccessfulSync
  ) {
    return 'current'
  }
  return null
}

function normalizeFreshnessState(state, freshness) {
  const explicit = String(state || '').toLowerCase()
  const fromFreshness = normalizeFreshnessMetadata(freshness)
  if (fromFreshness && (!BADGE_TEXT[explicit] || explicit === 'current')) {
    return fromFreshness
  }
  if (BADGE_TEXT[explicit]) return explicit
  return fromFreshness
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

export function SlateDateStamp({
  date,
  label = 'Tonight slate',
  includeYear = false,
  className = '',
}) {
  const formatted = formatFreshnessDate(date, { includeYear })
  if (!formatted) return null
  return (
    <span className={`inline-flex min-h-7 items-center rounded border border-dirt bg-field/50 px-2.5 py-1 font-mono text-[11px] uppercase tracking-widest text-chalk400 ${className}`}>
      {label}: {formatted}
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
