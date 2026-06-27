import { Link } from 'react-router-dom'
import {
  DataThroughStamp,
  FreshnessBadge,
  LastSyncLabel,
  StaleDataNotice,
  UnavailableDataState,
} from '../UI'

const STATE_META = {
  manageable: {
    label: 'Stable',
    detail: 'The current bullpen read shows enough usable coverage to avoid a clear pressure flag.',
    leagueLabel: 'Stable Overall',
    leagueDetail: 'Most bullpen-eligible arms remain usable, with limited league-wide pressure.',
    tone: { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7', dot: '#10b981' },
  },
  stable: {
    label: 'Stable',
    detail: 'The current bullpen read shows enough usable coverage to avoid a clear pressure flag.',
    leagueLabel: 'Stable Overall',
    leagueDetail: 'Most bullpen-eligible arms remain usable, with limited league-wide pressure.',
    tone: { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7', dot: '#10b981' },
  },
  usable: {
    label: 'Usable',
    detail: 'The bullpen still has playable coverage, with some context worth checking before first pitch.',
    tone: { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7', dot: '#10b981' },
  },
  monitoring: {
    label: 'Worth Watching',
    detail: 'The current read has enough yellow flags to keep this bullpen on the board.',
    tone: { borderColor: '#eab30855', backgroundColor: '#eab30812', color: '#fde047', dot: '#eab308' },
  },
  worth_watching: {
    label: 'Worth Watching',
    detail: 'The current read has enough yellow flags to keep this bullpen on the board.',
    tone: { borderColor: '#eab30855', backgroundColor: '#eab30812', color: '#fde047', dot: '#eab308' },
  },
  elevated: {
    label: 'Thin',
    detail: 'Cleanly available arms are limited right now.',
    leagueDetail: 'Fewer bullpen-eligible arms are cleanly available right now.',
    tone: { borderColor: '#f9731655', backgroundColor: '#f9731612', color: '#fdba74', dot: '#f97316' },
  },
  thin: {
    label: 'Thin',
    detail: 'Cleanly available arms are limited right now.',
    leagueDetail: 'Fewer bullpen-eligible arms are cleanly available right now.',
    tone: { borderColor: '#f9731655', backgroundColor: '#f9731612', color: '#fdba74', dot: '#f97316' },
  },
  constrained: {
    label: 'Constrained',
    detail: 'Clean options are limited in the current bullpen read.',
    tone: { borderColor: '#ef444455', backgroundColor: '#ef444412', color: '#fca5a5', dot: '#ef4444' },
  },
  stressed: {
    label: 'Stressed',
    detail: 'The current read shows a bullpen carrying meaningful availability pressure.',
    tone: { borderColor: '#ef444455', backgroundColor: '#ef444412', color: '#fca5a5', dot: '#ef4444' },
  },
  recovering: {
    label: 'Recovering',
    detail: 'The bullpen is moving back toward a cleaner read, but the latest context still matters.',
    tone: { borderColor: '#38bdf855', backgroundColor: '#38bdf812', color: '#bae6fd', dot: '#38bdf8' },
  },
}

const DEFAULT_TONE = { borderColor: '#94a3b855', backgroundColor: '#94a3b812', color: '#cbd5e1', dot: '#94a3b8' }

const INTERNAL_COPY_PATTERN = /\b(COIN|V2|V3|V4|deterministic|endpoint|backend|recommendation engine|baseline distribution|governance layer)\b/i
const LEAGUE_SCOPE_LIMITATION = 'This is a league-wide read, not a team-specific diagnosis. Availability classifications are workload-based only and do not include manager intent, bullpen phone activity, or private medical availability.'
const LIMITATION_COPY_PATTERN = /\b(workload-based only|does not include|not a team-specific|manager intent|bullpen phone activity|private medical|outside the active freshness window|may not reflect|treat this|limitation)\b/i

function normalizeStateKey(state) {
  return String(state || '').trim().toLowerCase().replace(/[\s-]+/g, '_')
}

function safeText(value) {
  if (typeof value !== 'string') return null
  const softened = value.trim().replace(/\bsnapshot\b/gi, 'bullpen read')
  if (!softened) return null
  if (INTERNAL_COPY_PATTERN.test(softened)) return null
  return softened
}

function safeTextList(list) {
  return (Array.isArray(list) ? list : [])
    .map(safeText)
    .filter(Boolean)
}

function isLimitationCopy(value) {
  return LIMITATION_COPY_PATTERN.test(String(value || ''))
}

function limitationKey(value) {
  const normalized = String(value || '').trim().replace(/\s+/g, ' ').toLowerCase()
  if (normalized.includes('availability classifications are workload-based only')) {
    return 'availability-classifications-workload-based-only'
  }
  return normalized
}

function uniqueList(list) {
  const seen = new Set()
  return list.filter(item => {
    const key = limitationKey(item)
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function rowCount(context, status) {
  const rows = Array.isArray(context?.snapshot) ? context.snapshot : []
  const row = rows.find(item => item?.status === status || item?.label === status)
  return typeof row?.count === 'number' ? row.count : 0
}

function getCounts(context) {
  const rows = Array.isArray(context?.snapshot) ? context.snapshot : []
  const hasRows = rows.length > 0
  const available = rowCount(context, 'Available')
  const monitor = rowCount(context, 'Monitor')
  const limited = rowCount(context, 'Limited')
  const avoid = rowCount(context, 'Avoid')
  const unavailable = rowCount(context, 'Unavailable')
  const rowTotal = available + monitor + limited + avoid + unavailable
  const metricTotal = typeof context?.metrics?.total === 'number' ? context.metrics.total : 0
  const total = metricTotal || rowTotal

  return {
    available,
    monitor,
    limited,
    avoid,
    unavailable,
    total,
    hasRows,
    narrowed: limited + avoid + unavailable,
    unavailableOrAvoid: avoid + unavailable,
  }
}

function pluralRelievers(count) {
  return count === 1 ? 'reliever' : 'relievers'
}

function buildConcern(label, body) {
  return { label, body }
}

function getConcernRows(context, stateKey) {
  const counts = getCounts(context)
  if (!counts.total || !counts.hasRows) return []

  const rows = []
  if (stateKey === 'constrained' || counts.available === 0) {
    rows.push(buildConcern(
      'Clean options are tight',
      `${counts.available} of ${counts.total} ${pluralRelievers(counts.total)} are classified Available.`,
    ))
  } else if (stateKey === 'elevated' || counts.narrowed > 0) {
    rows.push(buildConcern(
      'Not every arm is cleanly available',
      `${counts.narrowed} of ${counts.total} ${pluralRelievers(counts.total)} are Limited, Avoid, or Unavailable.`,
    ))
  } else {
    rows.push(buildConcern(
      'No clear pressure point',
      `${counts.available} of ${counts.total} ${pluralRelievers(counts.total)} are classified Available.`,
    ))
  }

  if (counts.monitor > 0) {
    rows.push(buildConcern(
      'Several arms are worth watching',
      `${counts.monitor} of ${counts.total} ${pluralRelievers(counts.total)} are in the Monitor lane.`,
    ))
  } else if (counts.unavailableOrAvoid > 0) {
    rows.push(buildConcern(
      'Some arms are out of the normal plan',
      `${counts.unavailableOrAvoid} of ${counts.total} ${pluralRelievers(counts.total)} are Avoid or Unavailable.`,
    ))
  } else if (counts.limited > 0) {
    rows.push(buildConcern(
      'Some usage lanes are narrowed',
      `${counts.limited} of ${counts.total} ${pluralRelievers(counts.total)} are in the Limited lane.`,
    ))
  }

  return rows.slice(0, 2)
}

function hasFreshnessValues(freshness) {
  return Boolean(
    freshness &&
    (
      freshness.data_through ||
      freshness.last_successful_sync ||
      freshness.freshness_state ||
      freshness.state ||
      freshness.sync_status ||
      freshness.sample === true ||
      freshness.is_current != null ||
      freshness.is_stale != null
    ),
  )
}

function isSampleFreshness(freshness) {
  const state = String(freshness?.freshness_state || freshness?.state || '').toLowerCase()
  return freshness?.sample === true || state === 'sample'
}

export function getBullpenOperatingStateView({
  team,
  teamLabel,
  scope,
  scopeLabel,
  context,
  freshness,
  ctaHref,
  ctaLabel,
} = {}) {
  const resolvedTeam = safeText(teamLabel) || safeText(team?.team_name) || safeText(team?.name) || 'League-Wide'
  const isLeagueWide = normalizeStateKey(scope) === 'league' || normalizeStateKey(resolvedTeam) === 'league_wide'
  const resolvedScopeLabel = safeText(scopeLabel) || (isLeagueWide ? 'Scope' : 'Team')
  const stateKey = normalizeStateKey(context?.state)
  const stateMeta = STATE_META[stateKey] || null
  const stateLabel = isLeagueWide && stateMeta?.leagueLabel ? stateMeta.leagueLabel : stateMeta?.label
  const stateDetail = isLeagueWide && stateMeta?.leagueDetail ? stateMeta.leagueDetail : stateMeta?.detail
  const hasContext = context?.hasContext !== false && Boolean(context)
  const isNoData = !hasContext || stateKey === 'no_data' || !stateMeta
  const why = safeText(context?.label) || (
    hasContext && !isNoData
      ? 'BaseballOS is reading the current bullpen mix from available workload context.'
      : null
  )
  const reasonCopy = safeTextList(context?.reasons)
  const evidence = reasonCopy.filter(item => !isLimitationCopy(item))
  const reasonLimitations = reasonCopy.filter(isLimitationCopy)
  const contextLimitations = safeTextList(context?.limitations)
  const limitations = uniqueList([
    ...(isLeagueWide ? [LEAGUE_SCOPE_LIMITATION] : []),
    ...contextLimitations,
    ...reasonLimitations,
  ])
  const concerns = isNoData ? [] : getConcernRows(context, stateKey)
  const tone = {
    ...(stateMeta?.tone || DEFAULT_TONE),
    ...(context?.tone || {}),
  }

  return {
    teamLabel: resolvedTeam,
    scopeLabel: resolvedScopeLabel,
    stateLabel: stateLabel || null,
    stateDetail: stateDetail || null,
    why,
    evidence,
    limitations,
    primaryConcern: concerns[0] || null,
    secondaryConcern: concerns[1] || null,
    freshness: freshness || null,
    hasFreshness: hasFreshnessValues(freshness),
    isSample: isSampleFreshness(freshness),
    isUnavailable: isNoData,
    tone,
    ctaHref,
    ctaLabel: ctaLabel || 'Open Bullpen Board',
  }
}

export default function BullpenOperatingStateCard({
  team,
  teamLabel,
  scope,
  scopeLabel,
  context,
  freshness,
  staleWithError = false,
  onRetry,
  ctaHref,
  ctaLabel,
  className = '',
}) {
  const view = getBullpenOperatingStateView({
    team,
    teamLabel,
    scope,
    scopeLabel,
    context,
    freshness,
    ctaHref,
    ctaLabel,
  })

  return (
    <article
      className={`card p-4 ${className}`}
      style={{
        borderColor: view.tone.borderColor,
        backgroundColor: view.tone.backgroundColor,
      }}
      role="region"
      aria-label={`${view.teamLabel} bullpen operating state`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            {view.scopeLabel}
          </div>
          <h3 className="mt-1 break-words font-display text-2xl leading-tight tracking-wide text-chalk100">
            {view.teamLabel}
          </h3>
        </div>
        {view.stateLabel && (
          <div
            className="inline-flex min-h-8 max-w-full items-center gap-2 rounded border px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest"
            style={{ borderColor: view.tone.borderColor, color: view.tone.color }}
          >
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: view.tone.dot }} aria-hidden="true" />
            <span className="min-w-0 break-words">Current Bullpen State: {view.stateLabel}</span>
          </div>
        )}
      </div>

      {view.isUnavailable ? (
        <UnavailableDataState
          title="No current bullpen read available."
          message="BaseballOS will show this card when enough current bullpen context is available."
          onRetry={onRetry}
          className="mt-4 border-dirt/70 bg-field/35"
          titleClassName="font-display text-xl leading-tight tracking-wide text-chalk100"
        />
      ) : (
        <>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <OperatingStateRow
              label="Current Bullpen State"
              title={view.stateLabel}
              body={view.stateDetail}
            />
            {view.primaryConcern && (
              <OperatingStateRow
                label="Primary Concern"
                title={view.primaryConcern.label}
                body={view.primaryConcern.body}
              />
            )}
            {view.secondaryConcern && (
              <OperatingStateRow
                label="Secondary Concern"
                title={view.secondaryConcern.label}
                body={view.secondaryConcern.body}
              />
            )}
            {view.why && (
              <OperatingStateRow
                label="Why BaseballOS Sees This"
                title={view.why}
              />
            )}
          </div>

          {view.evidence.length > 0 && (
            <section className="mt-4 border-t border-dirt/70 pt-3">
              <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                Evidence
              </div>
              <ul className="mt-2 space-y-1.5">
                {view.evidence.map((item, index) => (
                  <li key={`${index}-${item}`} className="text-xs leading-relaxed text-chalk300">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <section className="mt-4 border-t border-dirt/70 pt-3">
        <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
          Freshness
        </div>
        {staleWithError && (
          <div className="mt-2">
            <StaleDataNotice
              dataThrough={view.freshness?.data_through}
              onRetry={onRetry}
              compact
            />
          </div>
        )}
        <div className="mt-2 flex flex-wrap gap-2">
          {view.hasFreshness ? (
            <>
              <FreshnessBadge freshness={view.freshness} />
              <DataThroughStamp date={view.freshness?.data_through} />
              <LastSyncLabel
                label="Dashboard read synced"
                value={view.freshness?.last_successful_sync}
              />
            </>
          ) : (
            <FreshnessBadge state="unavailable" label="Freshness unavailable" />
          )}
        </div>
        {view.isSample && (
          <p className="mt-2 text-xs leading-relaxed text-chalk500">
            Not live MLB data.
          </p>
        )}
      </section>

      {view.limitations.length > 0 && (
        <section className="mt-4 border-t border-dirt/70 pt-3">
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Limitations
          </div>
          <ul className="mt-2 space-y-1.5">
            {view.limitations.map((item, index) => (
              <li key={`${index}-${item}`} className="text-xs leading-relaxed text-chalk400">
                {item}
              </li>
            ))}
          </ul>
        </section>
      )}

      {view.ctaHref && (
        <div className="mt-4 border-t border-dirt/70 pt-3">
          <Link
            to={view.ctaHref}
            className="inline-flex min-h-9 items-center justify-center rounded border border-dirt bg-field/60 px-3 py-2 font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
          >
            {view.ctaLabel}
          </Link>
        </div>
      )}
    </article>
  )
}

function OperatingStateRow({ label, title, body }) {
  if (!title && !body) return null
  return (
    <div className="border-t border-dirt/70 pt-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
        {label}
      </div>
      {title && (
        <div className="mt-1 break-words font-display text-lg leading-tight tracking-wide text-chalk100">
          {title}
        </div>
      )}
      {body && (
        <p className="mt-1 text-xs leading-relaxed text-chalk400">
          {body}
        </p>
      )}
    </div>
  )
}
