import {
  formatConfidence,
  getAvailabilityBadgeView,
  getAvailabilityStatusLabel,
} from '../components/bullpen/availabilityView'
import { NO_TEAM_STATE_TONE, readPublicTeamState } from './publicTeamState'
import { recordCopySuppression } from '../utils/copySuppressionAccounting'

const SNAPSHOT_ROWS = [
  { status: 'Available', label: 'Available', keys: ['available'], rawStatuses: ['Available'] },
  { status: 'Monitor', label: 'On Watch', keys: ['monitor'], rawStatuses: ['Monitor', 'On Watch'] },
  { status: 'Limited', label: 'Limited', keys: ['limited'], rawStatuses: ['Limited'] },
  { status: 'Unavailable', label: 'Unavailable', keys: ['avoid', 'unavailable'], rawStatuses: ['Avoid', 'Unavailable'] },
]

// Team State is backend-owned (UX-001). This adapter no longer holds a state
// dictionary: it does not translate an internal readiness or bullpen-health
// value into reader wording, does not infer a state from counts, stress, team
// shape, freshness, or `context.health`, and has no fallback label. It renders
// the canonical `team_state` block the payload carries, or nothing.
const DEFAULT_TONE = NO_TEAM_STATE_TONE
const LEAGUE_SCOPE_LIMITATION = 'This is a league-wide read, not a team-specific diagnosis. Availability classifications are workload-based only and do not include manager intent, bullpen phone activity, or private medical availability.'
const TEAM_SCOPE_LIMITATION = 'BaseballOS does not know manager intent, bullpen phone activity, private medical availability, unreported injuries, or final game-day availability decisions.'
const ROTATION_SUPPORT_MIN_ANALYZED_GAMES = 3
const ROTATION_SUPPORT_CAPABILITY = 'rotation_support_pressure_v1'
const ROTATION_SUPPORT_WINDOW_DAYS = 7
const ROTATION_SUPPORT_RECEIPTS_TARGET = '#team-relief-work'
const ROTATION_SUPPORT_RECEIPTS_LABEL = 'View game-level work'
const UNSUPPORTED_FIELDS = [
  'Trend Since Yesterday',
]

const TEAM_CONTEXT_READ_KEYS = ['cleanOptions', 'coverageSafety', 'workloadConcentration']

// The internal-vocabulary ban patterns that used to live here are gone. Public
// language is decided and guarded by the backend copy authority
// (backend/services/public_bullpen_copy.py). Re-checking it in the browser meant
// a guard failure silently deleted a governed sentence with no record anywhere.
const LIMITATION_COPY_PATTERN = /\b(workload-based only|does not include|not a team-specific|manager intent|bullpen phone activity|private medical|outside the active freshness window|may not reflect|treat this|limitation)\b/i

function normalizeStateKey(state) {
  return String(state || '').trim().toLowerCase().replace(/[\s-]+/g, '_')
}

function normalizeScope(scope) {
  return normalizeStateKey(scope) === 'team' ? 'team' : 'league'
}

function numericCount(value) {
  const number = Number(value)
  return Number.isFinite(number) && number > 0 ? number : 0
}

// Backend-authored copy is rendered as written. This trims surrounding
// whitespace and rejects a non-string; it does not rewrite, paraphrase, or
// translate a single word of governed public language. The vocabulary
// substitutions that used to live here are now backend decisions.
function safeText(value) {
  if (typeof value !== 'string') return null
  const text = value.trim()
  return text || null
}

function safeTextList(list) {
  return (Array.isArray(list) ? list : [])
    .map(safeText)
    .filter(Boolean)
}

// Team-context reads carry the same governed copy under a different key and get
// the same verbatim treatment. Kept as named aliases so the call sites still
// read as what they are.
const safeTeamContextText = safeText
const safeTeamContextTextList = safeTextList

// teamContextSummary() used to live here: nine hard-coded sentences chosen by
// substring-matching the backend label. The backend had already authored a
// sentence for every one of these reads and the browser threw it away and wrote
// its own. The authored sentence is now published as `summary`
// (backend/services/team_bullpen_shape.py) and is rendered verbatim.

function emptyTeamContextReads() {
  return {
    cleanOptions: null,
    coverageSafety: null,
    workloadConcentration: null,
  }
}

function getTeamShape(payload) {
  if (payload?.team_shape && typeof payload.team_shape === 'object') return payload.team_shape
  if (payload?.teamShape && typeof payload.teamShape === 'object') return payload.teamShape
  return null
}

function getTeamShapeRead(shape, key) {
  if (!shape || typeof shape !== 'object') return null
  const byKey = shape.byKey && typeof shape.byKey === 'object'
    ? shape.byKey
    : shape.by_key && typeof shape.by_key === 'object'
      ? shape.by_key
      : null
  const byKeyRead = byKey?.[key]
  if (byKeyRead && typeof byKeyRead === 'object') return byKeyRead
  const directRead = shape[key]
  if (directRead && typeof directRead === 'object') return directRead
  const arrayRead = Array.isArray(shape.reads)
    ? shape.reads.find(read => read?.key === key)
    : null
  return arrayRead && typeof arrayRead === 'object' ? arrayRead : null
}

function buildTeamContextRead(key, read) {
  if (!read || typeof read !== 'object') return null
  const label = safeText(read.label)
  // A limited read is the backend saying it cannot make this call. That is a
  // governed refusal, not copy the frontend withheld, so it is not accounted.
  if (!label || normalizeStateKey(label) === 'limited_read') return null

  // The backend-authored sentence, rendered as written.
  const summary = safeText(read.summary) || safeText(read.explanation)
  const reasons = safeTeamContextTextList(read.reasons)
  if (!summary) {
    // The backend published a read with a label but no sentence. The frontend
    // no longer invents one, so the read is withheld — and said so out loud.
    recordCopySuppression({
      surface: 'team-board',
      field: `teamContext.${key}.summary`,
      reason: 'backend_summary_missing',
      sample: label,
    })
    return null
  }
  return { label, summary, reasons }
}

function buildTeamContextReads(payload, scope) {
  if (scope !== 'team') return emptyTeamContextReads()
  const shape = getTeamShape(payload)
  if (!shape) return emptyTeamContextReads()
  return Object.fromEntries(
    TEAM_CONTEXT_READ_KEYS.map(key => [key, buildTeamContextRead(key, getTeamShapeRead(shape, key))]),
  )
}

function isLimitationCopy(value) {
  return LIMITATION_COPY_PATTERN.test(String(value || ''))
}

function limitationKey(value) {
  const normalized = String(value || '').trim().replace(/\s+/g, ' ').toLowerCase()
  if (normalized.includes('availability classifications are workload-based only')) {
    return 'availability-classifications-workload-based-only'
  }
  if (normalized.includes('does not know manager intent')) {
    return 'team-workload-boundary'
  }
  return normalized
}

function uniqueTextList(list) {
  const seen = new Set()
  const result = []
  for (const item of list) {
    const text = safeText(item)
    const key = limitationKey(text)
    if (!text || !key || seen.has(key)) continue
    seen.add(key)
    result.push(text)
  }
  return result
}

function pluralRelievers(count) {
  return count === 1 ? 'reliever' : 'relievers'
}

function pluralArms(count) {
  return count === 1 ? 'arm' : 'arms'
}

function pluralGames(count) {
  return count === 1 ? 'game' : 'games'
}

function pluralStarts(count) {
  return count === 1 ? 'start' : 'starts'
}

function numericValue(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function nonNegativeNumber(value) {
  const number = numericValue(value)
  return number != null && number >= 0 ? number : null
}

function nonNegativeCount(value) {
  const number = nonNegativeNumber(value)
  return number == null ? 0 : Math.floor(number)
}

function starterAverageReceipt(rotationSupport) {
  if (rotationSupport?.capability !== ROTATION_SUPPORT_CAPABILITY) return null
  if (rotationSupport?.window_days !== ROTATION_SUPPORT_WINDOW_DAYS) return null
  if (!Number.isSafeInteger(rotationSupport?.games_analyzed) || rotationSupport.games_analyzed <= 0) return null

  const starterOuts = rotationSupport?.starter_outs
  if (!Number.isSafeInteger(starterOuts) || starterOuts < 0) return null

  const averageOuts = starterOuts / rotationSupport.games_analyzed
  if (!Number.isFinite(averageOuts) || averageOuts < 0) return null
  // Outs are nonnegative, so floor(value + 0.5) is deterministic half-up rounding.
  const roundedOuts = Math.floor(averageOuts + 0.5)
  const wholeInnings = Math.floor(roundedOuts / 3)
  const remainingOuts = roundedOuts % 3
  if (remainingOuts < 0 || remainingOuts > 2) return null

  const formatted = `${wholeInnings}.${remainingOuts}`
  const unit = formatted === '1.0' ? 'inning' : 'innings'
  return `Across the seven-day window, starters averaged ${formatted} ${unit} per start.`
}

function formatOutsAsInnings(outs) {
  const number = nonNegativeNumber(outs)
  if (number == null) return null
  const roundedOuts = Math.round(number)
  const whole = Math.floor(roundedOuts / 3)
  const remainder = roundedOuts % 3
  const value = remainder === 0 ? `${whole}` : `${whole} ${remainder}/3`
  return `${value} ${whole === 1 && remainder === 0 ? 'inning' : 'innings'}`
}

function windowPhrase(days) {
  return days === 7 ? 'seven-day' : `${days}-day`
}

function rowCount(context, status) {
  const rows = Array.isArray(context?.snapshot) ? context.snapshot : []
  const row = rows.find(item => item?.status === status || item?.label === status)
  return typeof row?.count === 'number' ? row.count : 0
}

function metricCount(metrics, keys) {
  return keys.reduce((total, key) => total + (typeof metrics?.[key] === 'number' ? metrics[key] : 0), 0)
}

function sourceRowMatchesPublicRow(sourceRow, publicRow) {
  const rawStatus = sourceRow?.status
  const rawLabel = sourceRow?.label
  const publicLabel = getAvailabilityStatusLabel(rawLabel || rawStatus)
  return (
    publicRow.rawStatuses.includes(rawStatus) ||
    publicRow.rawStatuses.includes(rawLabel) ||
    publicRow.label === publicLabel
  )
}

function publicSnapshotRows(sourceRows = [], metrics = {}) {
  const rows = Array.isArray(sourceRows) ? sourceRows : []
  return SNAPSHOT_ROWS.map(row => {
    const matchingRows = rows.filter(item => sourceRowMatchesPublicRow(item, row))
    const count = matchingRows.length
      ? matchingRows.reduce((total, item) => total + (typeof item?.count === 'number' ? item.count : 0), 0)
      : metricCount(metrics, row.keys)
    return {
      status: row.status,
      label: row.label,
      count,
      badge: getAvailabilityBadgeView(row.status),
    }
  })
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

function buildConcern(label, body) {
  return { label: safeText(label), body: safeText(body) }
}

function safeConcern(concern) {
  if (!concern || typeof concern !== 'object') return null
  const label = safeText(concern.label)
  const body = safeText(concern.body)
  if (!label && !body) return null
  return { label, body }
}

// Concern copy describes the published availability counts and nothing else. It
// is not a Team State and is deliberately not keyed off any internal readiness
// or bullpen-health value.
function getWorkloadConcern(context) {
  const counts = getCounts(context)
  if (!counts.total || !counts.hasRows) return null

  if (counts.available === 0) {
    return buildConcern(
      'Rested Options are tight',
      `${counts.available} of ${counts.total} ${pluralRelievers(counts.total)} are classified Available.`,
    )
  }
  if (counts.narrowed > 0) {
    return buildConcern(
      'Not every arm is cleanly available',
      `${counts.narrowed} of ${counts.total} ${pluralRelievers(counts.total)} are Limited or Unavailable.`,
    )
  }
  return buildConcern(
    'Active workload is usable',
    `${counts.available} of ${counts.total} ${pluralRelievers(counts.total)} are classified Available.`,
  )
}

function getLeagueSecondaryConcern(context) {
  const counts = getCounts(context)
  if (!counts.total || !counts.hasRows) return null
  if (counts.monitor > 0) {
    return buildConcern(
      'Several arms are worth watching',
      `${counts.monitor} of ${counts.total} ${pluralRelievers(counts.total)} are in the On Watch lane.`,
    )
  }
  if (counts.unavailableOrAvoid > 0) {
    return buildConcern(
      'Some arms are out of the normal plan',
      `${counts.unavailableOrAvoid} of ${counts.total} ${pluralRelievers(counts.total)} are Unavailable.`,
    )
  }
  if (counts.limited > 0) {
    return buildConcern(
      'Some usage lanes are narrowed',
      `${counts.limited} of ${counts.total} ${pluralRelievers(counts.total)} are in the Limited lane.`,
    )
  }
  return null
}

function isLowValueZeroEvidence(item) {
  const text = String(item || '').trim()
  return (
    /^0 of \d+ relievers? are in (the )?Monitor( group| lane)?\.$/i.test(text) ||
    /^0 of \d+ relievers? are in (the )?On Watch( group| lane)?\.$/i.test(text) ||
    /^No relievers? are marked Unavailable\.$/i.test(text)
  )
}

function getWorkloadEvidence(context) {
  const counts = getCounts(context)
  if (!counts.total || !counts.hasRows) return []
  return [
    `${counts.available} of ${counts.total} ${pluralRelievers(counts.total)} are classified Available.`,
    counts.monitor > 0 ? `${counts.monitor} of ${counts.total} ${pluralRelievers(counts.total)} are in the On Watch group.` : null,
    counts.narrowed > 0 ? `${counts.narrowed} of ${counts.total} ${pluralRelievers(counts.total)} are Limited or Unavailable.` : null,
  ].filter(Boolean)
}

function buildRosterPressure(authority) {
  const readiness = authority?.readiness || {}
  const readinessLimitations = Array.isArray(readiness.reader_limitations)
    ? readiness.reader_limitations
    : Array.isArray(readiness.readerLimitations)
      ? readiness.readerLimitations
      : []
  if (readiness.counts_withheld === true || readiness.claims_available === false) {
    return {
      hasPressure: false,
      injuredList: null,
      inactive: null,
      unknown: null,
      concern: buildConcern(
        'Current roster depth is unverified',
        'Recent workload evidence is available, but current usable bullpen depth is withheld until roster status is verified.',
      ),
      evidence: [],
      limitations: safeTextList([
        ...safeTextList(authority?.limitations),
        ...readinessLimitations,
      ]),
    }
  }
  const counts = authority?.counts || {}
  const categories = authority?.category_counts || {}
  const injuredList = numericCount(categories.injured_list)
  const inactive = numericCount(counts.inactive_roster_context_count)
  const unknown = numericCount(counts.roster_unknown_count)
  const pressureCount = inactive || injuredList || unknown
  const evidence = []

  if (injuredList > 0) {
    evidence.push(`${injuredList} bullpen ${pluralArms(injuredList)} ${injuredList === 1 ? 'is' : 'are'} on the injured list.`)
  }
  if (inactive > 0) {
    evidence.push(`${inactive} bullpen ${pluralArms(inactive)} ${inactive === 1 ? 'is' : 'are'} inactive or unavailable.`)
  }
  if (unknown > 0) {
    evidence.push(`${unknown} bullpen ${pluralArms(unknown)} ${unknown === 1 ? 'has' : 'have'} unconfirmed roster status.`)
  }

  let concern = null
  if (pressureCount > 0) {
    const body = inactive > 0
      ? `${inactive} bullpen ${pluralArms(inactive)} ${inactive === 1 ? 'is' : 'are'} on the injured list or inactive.`
      : injuredList > 0
        ? `${injuredList} bullpen ${pluralArms(injuredList)} ${injuredList === 1 ? 'is' : 'are'} on the injured list.`
        : `${unknown} bullpen ${pluralArms(unknown)} ${unknown === 1 ? 'has' : 'have'} unconfirmed roster status.`
    concern = buildConcern('Roster pressure remains part of the story', body)
  }

  return {
    hasPressure: pressureCount > 0,
    injuredList,
    inactive,
    unknown,
    concern,
    evidence: safeTextList(evidence),
    limitations: safeTextList(authority?.limitations),
  }
}

function starterLengthLimitations(reasons, rotationSupport, gamesAnalyzed, gamesInWindow) {
  const reasonSet = new Set((Array.isArray(reasons) ? reasons : []).map(normalizeStateKey).filter(Boolean))
  const limitations = []
  const add = (value) => {
    if (value && !limitations.includes(value)) limitations.push(value)
  }
  if (reasonSet.has('no_recent_games')) {
    add('No recent completed games are available for this starter-length window.')
  }
  if (reasonSet.has('insufficient_trustworthy_games') || gamesAnalyzed < ROTATION_SUPPORT_MIN_ANALYZED_GAMES) {
    add('Not enough complete recent starts are available for a full starter-length read.')
  }
  if (reasonSet.has('incomplete_starter_identification')) {
    add('Some recent games cannot be included because the starter could not be identified cleanly.')
  }
  if (reasonSet.has('incomplete_historical_team_attribution')) {
    add('Some recent games cannot be included because the stored team-game starter and bullpen work is incomplete.')
  }
  if (reasonSet.has('partial_source_coverage')) {
    add('The recent game window is partial, so this starter-length read is limited.')
  }
  if (reasonSet.has('material_exclusion_share')) {
    add('Too many recent games are incomplete for a full starter-length read.')
  }
  if (reasonSet.has('opener_bulk_handling')) {
    add('Opener/bulk and bullpen games are separated only when the game shape can be verified.')
  }
  if (limitations.length === 0 && nonNegativeCount(rotationSupport?.games_excluded) > 0) {
    add('Some recent games cannot be included because starter and bullpen work is incomplete.')
  }
  return limitations
}

function buildStarterSupportPressure(rotationSupport, freshness) {
  if (!rotationSupport || typeof rotationSupport !== 'object') return null
  if (!freshness?.isCurrent || freshness?.isStale || freshness?.failClosed || freshness?.isSample) return null
  const gamesAnalyzed = nonNegativeCount(rotationSupport.games_analyzed)
  const gamesInWindow = nonNegativeCount(rotationSupport.games_in_window)
  const windowDays = nonNegativeCount(rotationSupport.window_days)
  const averageReceipt = starterAverageReceipt(rotationSupport)
  const bullpenInnings = formatOutsAsInnings(rotationSupport.bullpen_outs_required)
  const shortStartCount = nonNegativeCount(rotationSupport.short_start_count)
  const limitationReasons = Array.isArray(rotationSupport.limitation_reasons)
    ? rotationSupport.limitation_reasons.map(normalizeStateKey).filter(Boolean)
    : []
  const limitedByStatus = normalizeStateKey(rotationSupport.status) === 'limited_read'
  const limitations = starterLengthLimitations(limitationReasons, rotationSupport, gamesAnalyzed, gamesInWindow)
  const isLimited = limitedByStatus || limitations.length > 0
  const windowLabel = windowPhrase(windowDays)

  if (gamesAnalyzed <= 0 && gamesInWindow <= 0 && !isLimited) return null

  if (isLimited) {
    const sampleText = gamesInWindow > 0
      ? `${gamesAnalyzed} of ${gamesInWindow} recent ${pluralGames(gamesInWindow)} can be analyzed.`
      : `No recent completed games are available in the ${windowLabel} window.`
    const partialFacts = []
    if (gamesAnalyzed > 0 && bullpenInnings) {
      partialFacts.push(`The bullpen covered ${bullpenInnings} after those analyzed starts.`)
    }

    return {
      status: 'limited',
      gamesAnalyzed,
      label: null,
      summary: `Starter-length context is limited. ${sampleText}`,
      reasons: safeTextList([
        ...partialFacts,
        ...(limitations.length > 0 ? limitations : ['The recent starter-length sample is incomplete.']),
      ]),
      evidence: safeTextList(partialFacts),
      limitations: safeTextList(limitations),
      receiptsHref: ROTATION_SUPPORT_RECEIPTS_TARGET,
      receiptsLabel: ROTATION_SUPPORT_RECEIPTS_LABEL,
    }
  }

  if (!averageReceipt || !bullpenInnings || gamesAnalyzed < ROTATION_SUPPORT_MIN_ANALYZED_GAMES) return null

  const shortStartText = shortStartCount > 0
    ? `${shortStartCount} of ${gamesAnalyzed} analyzed ${pluralStarts(gamesAnalyzed)} ended before five innings.`
    : `None of the ${gamesAnalyzed} analyzed ${pluralStarts(gamesAnalyzed)} ended before five innings.`
  const summary = `${averageReceipt} The bullpen covered ${bullpenInnings} after those starts.`

  return {
    status: 'available',
    gamesAnalyzed,
    label: null,
    summary,
    reasons: safeTextList([
      shortStartText,
      gamesInWindow > gamesAnalyzed
        ? `${gamesAnalyzed} of ${gamesInWindow} recent ${pluralGames(gamesInWindow)} count toward this starter-length read.`
        : null,
    ]),
    evidence: safeTextList([
      summary,
      shortStartText,
    ]),
    limitations: [],
    receiptsHref: ROTATION_SUPPORT_RECEIPTS_TARGET,
    receiptsLabel: ROTATION_SUPPORT_RECEIPTS_LABEL,
  }
}

function freshnessIsLimited(freshness) {
  const state = normalizeStateKey(freshness?.freshness_state || freshness?.state)
  return Boolean(
    freshness?.is_stale === true ||
    freshness?.is_current === false ||
    freshness?.fail_closed === true ||
    state === 'stale' ||
    state === 'historical' ||
    state === 'failed'
  )
}

export function teamOperatingStateFreshnessIsDegraded(freshness) {
  return freshnessIsLimited(freshness)
}

function buildFreshnessModel(freshness) {
  const f = freshness && typeof freshness === 'object' ? freshness : {}
  const freshnessState = safeText(f.freshness_state || f.state) || null
  const syncStatus = safeText(f.sync_status) || null
  const stateKey = normalizeStateKey(freshnessState)
  const isSample = f.sample === true || stateKey === 'sample'
  const isStale = freshnessIsLimited(f)
  const hasFreshness = Boolean(
    f.data_through ||
    f.last_successful_sync ||
    freshnessState ||
    syncStatus ||
    isSample ||
    f.is_current != null ||
    f.is_stale != null
  )

  return {
    dataThrough: safeText(f.data_through) || null,
    data_through: safeText(f.data_through) || null,
    lastSync: safeText(f.last_successful_sync) || null,
    last_successful_sync: safeText(f.last_successful_sync) || null,
    isCurrent: f.is_current === true || (hasFreshness && f.is_current !== false && !isStale),
    is_current: f.is_current === true || (hasFreshness && f.is_current !== false && !isStale),
    isStale,
    is_stale: isStale,
    isSample,
    sample: isSample,
    failClosed: f.fail_closed === true,
    fail_closed: f.fail_closed === true,
    freshnessState,
    freshness_state: freshnessState,
    syncStatus,
    sync_status: syncStatus,
    limitations: safeTextList(f.limitations),
    hasFreshness,
  }
}

function resolveTeam(payload, team) {
  const source = team || payload?.team || {}
  const teamId = source?.team_id ?? source?.teamId ?? null
  const teamName = safeText(source?.team_name) || safeText(source?.teamName) || safeText(source?.name)
  const teamAbbreviation = safeText(source?.team_abbreviation) || safeText(source?.teamAbbreviation) || safeText(source?.abbreviation)
  return {
    teamId,
    teamName,
    teamAbbreviation,
  }
}

function normalizeContextView(context) {
  const metrics = context?.metrics || {}
  const rows = publicSnapshotRows(context?.snapshot, metrics)
  const total = typeof metrics.total === 'number'
    ? metrics.total
    : typeof metrics.total_relievers === 'number'
      ? metrics.total_relievers
      : rows.reduce((sum, row) => sum + (Number(row.count) || 0), 0)
  const confidence = context?.confidence || 'high'

  // `state` is intentionally absent: `context.health.state` is an internal,
  // count-derived bullpen-health value and is never the public Team State.
  return {
    hasContext: context?.hasContext !== false && Boolean(context),
    label: safeText(context?.label || context?.health?.label) || null,
    reasons: safeTextList(Array.isArray(context?.reasons) ? context.reasons : Array.isArray(context?.health?.reasons) ? context.health.reasons : []),
    confidence,
    confidenceLabel: context?.confidenceLabel || formatConfidence(confidence),
    isDegraded: context?.isDegraded === true || confidence === 'low',
    limitations: safeTextList(context?.limitations),
    metrics: {
      total,
      pctAvailable: typeof metrics.pctAvailable === 'number' ? metrics.pctAvailable : typeof metrics.pct_available === 'number' ? metrics.pct_available : 0,
      pctUnavailable: typeof metrics.pctUnavailable === 'number' ? metrics.pctUnavailable : typeof metrics.pct_unavailable === 'number' ? metrics.pct_unavailable : 0,
      pctRestricted: typeof metrics.pctRestricted === 'number' ? metrics.pctRestricted : typeof metrics.pct_restricted === 'number' ? metrics.pct_restricted : 0,
    },
    snapshot: rows,
  }
}

export function getBoardContextView(board) {
  const context = board?.context || {}
  const metrics = context.metrics || {}
  const health = context.health || {}
  const confidence = context.confidence || 'high'

  const snapshot = publicSnapshotRows([], metrics)

  // No `state` and no state-keyed tone: `context.health.state` stays internal.
  return {
    hasContext: Boolean(board?.context),
    label: safeText(health.label) || null,
    reasons: safeTextList(health.reasons),
    confidence,
    confidenceLabel: formatConfidence(confidence),
    isDegraded: confidence === 'low',
    limitations: safeTextList(context.limitations),
    metrics: {
      total: typeof metrics.total_relievers === 'number' ? metrics.total_relievers : 0,
      pctAvailable: typeof metrics.pct_available === 'number' ? metrics.pct_available : 0,
      pctUnavailable: typeof metrics.pct_unavailable === 'number' ? metrics.pct_unavailable : 0,
      pctRestricted: typeof metrics.pct_restricted === 'number' ? metrics.pct_restricted : 0,
    },
    snapshot,
  }
}

function resolveContext(payload) {
  if (payload?.hasContext != null || Array.isArray(payload?.snapshot)) {
    return normalizeContextView(payload)
  }
  return getBoardContextView(payload)
}

function resolveCta(cta) {
  if (!cta || typeof cta !== 'object') return null
  const href = typeof cta.href === 'string' ? cta.href : typeof cta.to === 'string' ? cta.to : null
  const label = safeText(cta.label) || 'Open Bullpen Board'
  return href ? { href, label } : null
}

function buildUnavailableReadModel({ scope, teamInfo, freshness, cta, density, teamState }) {
  const teamName = scope === 'team'
    ? teamInfo.teamName || teamInfo.teamAbbreviation || 'Selected Team'
    : 'League-Wide'
  // A payload with no context carries no Why to render. That is a legitimate
  // fail-closed outcome — the card shows the backend's governed non-state
  // message — but it is still a surface rendering without an explanation, so it
  // is recorded rather than passed over in silence.
  recordCopySuppression({
    surface: scope === 'team' ? 'team-board' : 'dashboard',
    field: 'context.health.label',
    reason: 'no_context_in_payload',
  })
  return {
    scope,
    scopeLabel: scope === 'team' ? 'Team' : 'Scope',
    teamId: teamInfo.teamId,
    teamName,
    teamAbbreviation: teamInfo.teamAbbreviation,
    teamLabel: teamName,
    stateLabel: null,
    stateSummary: null,
    stateUnavailableMessage: teamState?.unavailableMessage || null,
    stateTone: DEFAULT_TONE,
    tone: DEFAULT_TONE,
    isUnavailable: true,
    why: null,
    primaryConcern: null,
    secondaryConcern: null,
    rosterPressure: null,
    starterSupportPressure: null,
    ...emptyTeamContextReads(),
    evidence: [],
    freshness,
    hasFreshness: freshness.hasFreshness,
    isSample: freshness.isSample,
    limitations: [],
    cta,
    ctaHref: cta?.href || null,
    ctaLabel: cta?.label || 'Open Bullpen Board',
    density,
    unsupportedFields: UNSUPPORTED_FIELDS,
  }
}

export function toOperatingStateReadModel(payload, {
  scope = 'league',
  team = null,
  cta = null,
  density = 'full',
  includeRotationSupport = true,
} = {}) {
  const resolvedScope = normalizeScope(scope)
  const teamInfo = resolveTeam(payload, team)
  const freshness = buildFreshnessModel(payload?.freshness)
  const resolvedCta = resolveCta(cta)
  const context = resolveContext(payload)
  // The one source of Team State: the backend-owned `team_state` block. There is
  // no local fallback — an absent, unsupported, or fail-closed block leaves this
  // read model with no state label at all.
  //
  // Team State is defined per team, so a league-scope read never resolves one
  // even if a team-shaped block reaches this adapter. That is what retired the
  // league pseudo-state ("Stable Overall"); it is a refusal, not a derivation.
  const rawTeamState = payload?.team_state
  const teamState = normalizeScope(scope) === 'team'
    ? readPublicTeamState(rawTeamState)
    : readPublicTeamState({
      ...(rawTeamState && typeof rawTeamState === 'object' ? rawTeamState : {}),
      available: false,
    })

  if (!context.hasContext) {
    return buildUnavailableReadModel({
      scope: resolvedScope,
      teamInfo,
      freshness,
      cta: resolvedCta,
      density,
      teamState,
    })
  }

  const isLeague = resolvedScope === 'league'
  const teamName = isLeague
    ? 'League-Wide'
    : teamInfo.teamName || teamInfo.teamAbbreviation || 'Selected Team'
  // Rendered verbatim from the backend, or null. The adapter never title-cases an
  // internal enum, never substitutes a league-wide label, and never repairs a
  // missing one.
  const stateLabel = teamState.publicLabel
  const rosterPressure = resolvedScope === 'team' ? buildRosterPressure(payload?.roster_authority) : null
  const starterSupportPressure = resolvedScope === 'team' && includeRotationSupport
    ? buildStarterSupportPressure(payload?.rotation_support_pressure, freshness)
    : null
  const teamContextReads = buildTeamContextReads(payload, resolvedScope)
  const primaryConcern = safeConcern(getWorkloadConcern(context))
  const secondaryConcern = resolvedScope === 'team'
    ? safeConcern(rosterPressure?.concern)
    : safeConcern(getLeagueSecondaryConcern(context))
  const contextReasons = safeTextList(context.reasons)
  const evidence = uniqueTextList([
    ...contextReasons.filter(item => !isLimitationCopy(item) && !isLowValueZeroEvidence(item)),
    ...getWorkloadEvidence(context),
    ...(rosterPressure?.evidence || []),
    ...(starterSupportPressure?.evidence || []),
  ])
  const reasonLimitations = contextReasons.filter(isLimitationCopy)
  const limitations = uniqueTextList([
    isLeague ? LEAGUE_SCOPE_LIMITATION : TEAM_SCOPE_LIMITATION,
    ...safeTextList(context.limitations),
    ...reasonLimitations,
    ...(rosterPressure?.limitations || []),
    ...(starterSupportPressure?.limitations || []),
    ...freshness.limitations,
    ...safeTextList(payload?.limitations),
  ])
  // League context may keep its backend-authored board explanation. A team read
  // instead uses the canonical Team State summary from `team_state`; the
  // independently count-derived `context.health.label` is never its Why or a
  // fallback when Team State is unavailable.
  const why = isLeague ? safeText(context.label) : null
  if (isLeague && !why) {
    recordCopySuppression({
      surface: isLeague ? 'dashboard' : 'team-board',
      field: 'context.health.label',
      reason: 'backend_why_missing',
    })
  }
  // Tone is decoration keyed only by the canonical public state the backend
  // supplied, and neutral whenever there is no Team State to show.
  const stateTone = teamState.tone

  return {
    scope: resolvedScope,
    scopeLabel: isLeague ? 'Scope' : 'Team',
    teamId: teamInfo.teamId,
    teamName,
    teamAbbreviation: teamInfo.teamAbbreviation,
    teamLabel: teamName,
    stateLabel,
    publicState: teamState.publicState,
    // The summary is carried by the same backend projection as the canonical
    // public state. Missing summary stays missing; counts and legacy board
    // health copy are not substitutes.
    stateSummary: teamState.summary,
    stateDetail: teamState.summary,
    stateUnavailableMessage: teamState.unavailableMessage,
    stateTone,
    tone: stateTone,
    isUnavailable: false,
    why,
    primaryConcern,
    secondaryConcern,
    rosterPressure,
    starterSupportPressure,
    ...teamContextReads,
    evidence,
    freshness,
    hasFreshness: freshness.hasFreshness,
    isSample: freshness.isSample,
    limitations,
    cta: resolvedCta,
    ctaHref: resolvedCta?.href || null,
    ctaLabel: resolvedCta?.label || 'Open Bullpen Board',
    density,
    unsupportedFields: UNSUPPORTED_FIELDS,
  }
}

export function getTeamOperatingStateContext(board) {
  return toOperatingStateReadModel(board, {
    scope: 'team',
    team: board?.team,
    cta: { href: '#pitcher-lanes', label: 'Review pitcher lanes' },
    density: 'compact',
  })
}
