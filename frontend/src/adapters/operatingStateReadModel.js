import {
  formatConfidence,
  getAvailabilityBadgeView,
} from '../components/bullpen/availabilityView'

const SNAPSHOT_ROWS = [
  { status: 'Available', label: 'Available', key: 'available' },
  { status: 'Monitor', label: 'Monitor', key: 'monitor' },
  { status: 'Limited', label: 'Limited', key: 'limited' },
  { status: 'Avoid', label: 'Avoid', key: 'avoid' },
  { status: 'Unavailable', label: 'Unavailable', key: 'unavailable' },
]

const HEALTH_TONE = {
  manageable: { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7', dot: '#10b981' },
  monitoring: { borderColor: '#eab30855', backgroundColor: '#eab30812', color: '#fde047', dot: '#eab308' },
  elevated: { borderColor: '#f9731655', backgroundColor: '#f9731612', color: '#fdba74', dot: '#f97316' },
  constrained: { borderColor: '#ef444455', backgroundColor: '#ef444412', color: '#fca5a5', dot: '#ef4444' },
  no_data: { borderColor: 'rgba(148,163,184,0.32)', backgroundColor: 'rgba(148,163,184,0.09)', color: '#cbd5e1', dot: '#94a3b8' },
}

const STATE_META = {
  manageable: {
    label: 'Stable',
    summary: 'The current bullpen read shows enough usable coverage to avoid a clear pressure flag.',
    leagueLabel: 'Stable Overall',
    leagueSummary: 'Most bullpen-eligible arms remain usable, with limited league-wide pressure.',
    tone: HEALTH_TONE.manageable,
  },
  stable: {
    label: 'Stable',
    summary: 'The current bullpen read shows enough usable coverage to avoid a clear pressure flag.',
    leagueLabel: 'Stable Overall',
    leagueSummary: 'Most bullpen-eligible arms remain usable, with limited league-wide pressure.',
    tone: HEALTH_TONE.manageable,
  },
  usable: {
    label: 'Usable',
    summary: 'The bullpen still has playable coverage, with some context worth checking before first pitch.',
    tone: HEALTH_TONE.manageable,
  },
  monitoring: {
    label: 'Worth Watching',
    summary: 'The current read has enough yellow flags to keep this bullpen on the board.',
    tone: HEALTH_TONE.monitoring,
  },
  worth_watching: {
    label: 'Worth Watching',
    summary: 'The current read has enough yellow flags to keep this bullpen on the board.',
    tone: HEALTH_TONE.monitoring,
  },
  elevated: {
    label: 'Thin',
    summary: 'Cleanly available arms are limited right now.',
    leagueSummary: 'Fewer bullpen-eligible arms are cleanly available right now.',
    tone: HEALTH_TONE.elevated,
  },
  thin: {
    label: 'Thin',
    summary: 'Cleanly available arms are limited right now.',
    leagueSummary: 'Fewer bullpen-eligible arms are cleanly available right now.',
    tone: HEALTH_TONE.elevated,
  },
  constrained: {
    label: 'Constrained',
    summary: 'Clean options are limited in the current bullpen read.',
    tone: HEALTH_TONE.constrained,
  },
  stressed: {
    label: 'Stressed',
    summary: 'The current read shows a bullpen carrying meaningful availability pressure.',
    tone: HEALTH_TONE.constrained,
  },
  recovering: {
    label: 'Recovering',
    summary: 'The bullpen is moving back toward a cleaner read, but the latest context still matters.',
    tone: { borderColor: '#38bdf855', backgroundColor: '#38bdf812', color: '#bae6fd', dot: '#38bdf8' },
  },
}

const DEFAULT_TONE = { borderColor: '#94a3b855', backgroundColor: '#94a3b812', color: '#cbd5e1', dot: '#94a3b8' }
const LEAGUE_SCOPE_LIMITATION = 'This is a league-wide read, not a team-specific diagnosis. Availability classifications are workload-based only and do not include manager intent, bullpen phone activity, or private medical availability.'
const TEAM_SCOPE_LIMITATION = 'BaseballOS does not know manager intent, bullpen phone activity, private medical availability, unreported injuries, or final game-day availability decisions.'
const ROTATION_SUPPORT_MIN_ANALYZED_GAMES = 3
const ROTATION_SUPPORT_LIMITED_STATUSES = new Set(['limited_read', 'no_data'])
const UNSUPPORTED_FIELDS = [
  'Trend Since Yesterday',
]

const TEAM_CONTEXT_READ_KEYS = ['cleanOptions', 'coverageSafety', 'workloadConcentration']

const INTERNAL_COPY_PATTERN = /\b(COIN|V2|V3|V4|deterministic|endpoint|backend|source|snapshot|recommendation engine|baseline distribution|baseline|governance layer|sample state|coverageSafetyVersion|capacityState|resourceHealthState|thresholds)\b|2\.0/i
const TEAM_CONTEXT_INTERNAL_COPY_PATTERN = /\b(COIN|V2|V3|V4|deterministic|endpoint|backend|source|snapshot|recommendation engine|baseline distribution|baseline|governance layer|governance|coverageSafetyVersion|capacityState|resourceHealthState|thresholds|Trust Arms?|Depth Arms?|top trust bucket|resource health|trust structure|active capacity|Interpretation weighs)\b|2\.0|\b\d+\s+(Trust|Bridge|Depth)\b/i
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

function safeTeamContextText(value) {
  if (typeof value !== 'string') return null
  const text = value.trim()
  if (!text || TEAM_CONTEXT_INTERNAL_COPY_PATTERN.test(text)) return null
  return text
}

function safeTeamContextTextList(list) {
  return (Array.isArray(list) ? list : [])
    .map(safeTeamContextText)
    .filter(Boolean)
}

function teamContextSummary(key, label) {
  const labelKey = normalizeStateKey(label)
  if (key === 'cleanOptions') {
    if (labelKey.includes('deep') || labelKey.includes('healthy')) {
      return 'This bullpen has enough cleanly available choices for normal coverage.'
    }
    if (labelKey.includes('very_thin')) {
      return 'Available arms exist, but fewer options look clean from a workload and role standpoint.'
    }
    return 'Cleanly available choices are thinner than raw availability may suggest.'
  }
  if (key === 'coverageSafety') {
    if (labelKey.includes('strong') || labelKey.includes('stable')) {
      return 'The current group appears to have enough coverage for a normal game state.'
    }
    if (labelKey.includes('thin')) {
      return 'Coverage looks thinner than the raw active count suggests.'
    }
    return 'Coverage is usable, but the margin could tighten if the bullpen is needed early.'
  }
  if (key === 'workloadConcentration') {
    if (labelKey.includes('no_workload_concentration')) {
      return 'Recent bullpen work has been spread out enough to avoid a clear concentration flag.'
    }
    if (labelKey.includes('some_workload_concentration')) {
      return 'Recent relief work has flowed through a smaller group of arms.'
    }
    return 'A smaller group has handled a larger share of recent relief work.'
  }
  return null
}

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
  if (!label || normalizeStateKey(label) === 'limited_read') return null
  const summary = teamContextSummary(key, label)
  const reasons = safeTeamContextTextList(read.reasons)
  if (!summary) return null
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

function getWorkloadConcern(context, stateKey) {
  const counts = getCounts(context)
  if (!counts.total || !counts.hasRows) return null

  if (stateKey === 'constrained' || counts.available === 0) {
    return buildConcern(
      'Clean options are tight',
      `${counts.available} of ${counts.total} ${pluralRelievers(counts.total)} are classified Available.`,
    )
  }
  if (stateKey === 'elevated' || counts.narrowed > 0) {
    return buildConcern(
      'Not every arm is cleanly available',
      `${counts.narrowed} of ${counts.total} ${pluralRelievers(counts.total)} are Limited, Avoid, or Unavailable.`,
    )
  }
  if (stateKey === 'monitoring') {
    return buildConcern(
      'Several arms are worth watching',
      `${counts.monitor} of ${counts.total} ${pluralRelievers(counts.total)} are in the Monitor lane.`,
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
      `${counts.monitor} of ${counts.total} ${pluralRelievers(counts.total)} are in the Monitor lane.`,
    )
  }
  if (counts.unavailableOrAvoid > 0) {
    return buildConcern(
      'Some arms are out of the normal plan',
      `${counts.unavailableOrAvoid} of ${counts.total} ${pluralRelievers(counts.total)} are Avoid or Unavailable.`,
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
    /^No relievers? are marked Avoid or Unavailable\.$/i.test(text)
  )
}

function getWorkloadEvidence(context) {
  const counts = getCounts(context)
  if (!counts.total || !counts.hasRows) return []
  return [
    `${counts.available} of ${counts.total} ${pluralRelievers(counts.total)} are classified Available.`,
    counts.monitor > 0 ? `${counts.monitor} of ${counts.total} ${pluralRelievers(counts.total)} are in the Monitor group.` : null,
    counts.narrowed > 0 ? `${counts.narrowed} of ${counts.total} ${pluralRelievers(counts.total)} are Limited, Avoid, or Unavailable.` : null,
  ].filter(Boolean)
}

function buildRosterPressure(authority) {
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

function buildStarterSupportPressure(rotationSupport) {
  if (!rotationSupport || typeof rotationSupport !== 'object') return null
  const gamesAnalyzed = numericCount(rotationSupport.games_analyzed)
  const status = normalizeStateKey(rotationSupport.status)
  const summary = safeText(rotationSupport.summary)
  const shouldShow = (
    gamesAnalyzed >= ROTATION_SUPPORT_MIN_ANALYZED_GAMES &&
    summary &&
    !ROTATION_SUPPORT_LIMITED_STATUSES.has(status)
  )
  if (!shouldShow) return null
  return {
    status,
    gamesAnalyzed,
    summary,
    evidence: [`Starter support: ${summary}`],
    limitations: safeTextList(rotationSupport.limitations),
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
  const state = normalizeStateKey(context?.state || context?.health?.state || 'no_data')
  const rows = Array.isArray(context?.snapshot)
    ? context.snapshot
    : SNAPSHOT_ROWS.map(row => ({
      status: row.status,
      label: row.label,
      count: typeof context?.metrics?.[row.key] === 'number' ? context.metrics[row.key] : 0,
      badge: getAvailabilityBadgeView(row.status),
    }))
  const metrics = context?.metrics || {}
  const total = typeof metrics.total === 'number'
    ? metrics.total
    : typeof metrics.total_relievers === 'number'
      ? metrics.total_relievers
      : rows.reduce((sum, row) => sum + (Number(row.count) || 0), 0)
  const confidence = context?.confidence || 'high'

  return {
    hasContext: context?.hasContext !== false && Boolean(context),
    state,
    label: context?.label || context?.health?.label || null,
    reasons: Array.isArray(context?.reasons) ? context.reasons : Array.isArray(context?.health?.reasons) ? context.health.reasons : [],
    confidence,
    confidenceLabel: context?.confidenceLabel || formatConfidence(confidence),
    isDegraded: context?.isDegraded === true || confidence === 'low',
    limitations: Array.isArray(context?.limitations) ? context.limitations : [],
    metrics: {
      total,
      pctAvailable: typeof metrics.pctAvailable === 'number' ? metrics.pctAvailable : typeof metrics.pct_available === 'number' ? metrics.pct_available : 0,
      pctUnavailable: typeof metrics.pctUnavailable === 'number' ? metrics.pctUnavailable : typeof metrics.pct_unavailable === 'number' ? metrics.pct_unavailable : 0,
      pctRestricted: typeof metrics.pctRestricted === 'number' ? metrics.pctRestricted : typeof metrics.pct_restricted === 'number' ? metrics.pct_restricted : 0,
    },
    snapshot: rows.map(row => ({
      status: row.status,
      label: row.label,
      count: typeof row.count === 'number' ? row.count : 0,
      badge: row.badge || getAvailabilityBadgeView(row.status),
    })),
    tone: context?.tone || HEALTH_TONE[state] || HEALTH_TONE.no_data,
  }
}

export function getBoardContextView(board) {
  const context = board?.context || {}
  const metrics = context.metrics || {}
  const health = context.health || {}
  const state = health.state || 'no_data'
  const tone = HEALTH_TONE[state] || HEALTH_TONE.no_data
  const confidence = context.confidence || 'high'

  const snapshot = SNAPSHOT_ROWS.map(row => ({
    status: row.status,
    label: row.label,
    count: typeof metrics[row.key] === 'number' ? metrics[row.key] : 0,
    badge: getAvailabilityBadgeView(row.status),
  }))

  return {
    hasContext: Boolean(board?.context),
    state,
    label: health.label || null,
    reasons: Array.isArray(health.reasons) ? health.reasons : [],
    confidence,
    confidenceLabel: formatConfidence(confidence),
    isDegraded: confidence === 'low',
    limitations: Array.isArray(context.limitations) ? context.limitations : [],
    metrics: {
      total: typeof metrics.total_relievers === 'number' ? metrics.total_relievers : 0,
      pctAvailable: typeof metrics.pct_available === 'number' ? metrics.pct_available : 0,
      pctUnavailable: typeof metrics.pct_unavailable === 'number' ? metrics.pct_unavailable : 0,
      pctRestricted: typeof metrics.pct_restricted === 'number' ? metrics.pct_restricted : 0,
    },
    snapshot,
    tone,
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

function buildUnavailableReadModel({ scope, teamInfo, freshness, cta, density }) {
  const teamName = scope === 'team'
    ? teamInfo.teamName || teamInfo.teamAbbreviation || 'Selected Team'
    : 'League-Wide'
  return {
    scope,
    scopeLabel: scope === 'team' ? 'Team' : 'Scope',
    teamId: teamInfo.teamId,
    teamName,
    teamAbbreviation: teamInfo.teamAbbreviation,
    teamLabel: teamName,
    stateLabel: null,
    stateSummary: null,
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

export function toOperatingStateReadModel(payload, { scope = 'league', team = null, cta = null, density = 'full' } = {}) {
  const resolvedScope = normalizeScope(scope)
  const teamInfo = resolveTeam(payload, team)
  const freshness = buildFreshnessModel(payload?.freshness)
  const resolvedCta = resolveCta(cta)
  const context = resolveContext(payload)
  const stateKey = normalizeStateKey(context.state)
  const stateMeta = STATE_META[stateKey] || null
  const isUnavailable = !context.hasContext || stateKey === 'no_data' || !stateMeta

  if (isUnavailable) {
    return buildUnavailableReadModel({
      scope: resolvedScope,
      teamInfo,
      freshness,
      cta: resolvedCta,
      density,
    })
  }

  const isLeague = resolvedScope === 'league'
  const teamName = isLeague
    ? 'League-Wide'
    : teamInfo.teamName || teamInfo.teamAbbreviation || 'Selected Team'
  const stateLabel = isLeague && stateMeta.leagueLabel ? stateMeta.leagueLabel : stateMeta.label
  const stateSummary = isLeague && stateMeta.leagueSummary ? stateMeta.leagueSummary : stateMeta.summary
  const rosterPressure = resolvedScope === 'team' ? buildRosterPressure(payload?.roster_authority) : null
  const starterSupportPressure = resolvedScope === 'team' ? buildStarterSupportPressure(payload?.rotation_support_pressure) : null
  const teamContextReads = buildTeamContextReads(payload, resolvedScope)
  const primaryConcern = safeConcern(getWorkloadConcern(context, stateKey))
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
  const why = safeText(context.label) || 'BaseballOS is reading the current bullpen mix from available workload context.'
  const stateTone = {
    ...(stateMeta.tone || DEFAULT_TONE),
    ...(context.tone || {}),
  }

  return {
    scope: resolvedScope,
    scopeLabel: isLeague ? 'Scope' : 'Team',
    teamId: teamInfo.teamId,
    teamName,
    teamAbbreviation: teamInfo.teamAbbreviation,
    teamLabel: teamName,
    stateLabel,
    stateSummary,
    stateDetail: stateSummary,
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
