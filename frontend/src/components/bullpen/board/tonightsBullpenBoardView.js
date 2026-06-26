import {
  formatConfidence,
  getAvailabilityBadgeView,
  getDataStateView,
} from '../availabilityView'
import { completedGamesDataLine, fmtDataDate, fmtSyncDate } from '../../dashboard/syncStatusView'
import {
  compactWorkloadAppearanceLabel,
  dayAwareAppearanceReason,
  dayAwareAppearanceReasons,
  isWorkloadAppearance,
  platformDateFromFreshness,
} from '../../../utils/appearanceLanguage'
import { getPitcherLabels } from '../../../utils/pitcherLabels'

// Canonical group order, mirrored from the backend. Used only as a fallback
// when the payload is missing or malformed — the backend is the source of
// truth and we never re-sort pitchers on the client.
export const BOARD_GROUP_ORDER = [
  'Available',
  'Monitor',
  'Limited',
  'Avoid',
  'Unavailable',
]

export const BULLPEN_VIEW_MODE_ACTIVE = 'active'
export const BULLPEN_VIEW_MODE_ACTIVE_PLUS_UNAVAILABLE = 'active_plus_unavailable'
export const BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY = 'unavailable_only'
export const DEFAULT_BULLPEN_VIEW_MODE = BULLPEN_VIEW_MODE_ACTIVE

export const BULLPEN_VIEW_MODES = [
  {
    id: BULLPEN_VIEW_MODE_ACTIVE,
    label: 'Active',
    description: 'Show the relievers currently available for bullpen planning.',
  },
  {
    id: BULLPEN_VIEW_MODE_ACTIVE_PLUS_UNAVAILABLE,
    label: 'Active + Unavailable',
    description: 'Show the current bullpen plus arms out of the plan because of roster context.',
  },
  {
    id: BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY,
    label: 'Unavailable Only',
    description: 'Show only the relievers BaseballOS is not counting for the current bullpen plan.',
  },
]

const VALID_BULLPEN_VIEW_MODES = new Set(BULLPEN_VIEW_MODES.map(mode => mode.id))

const GROUP_FALLBACK_META = {
  Available: { label: 'Available', description: 'Recent usage leaves these arms in a clean spot for normal bullpen coverage.' },
  Monitor: { label: 'Monitor', description: 'Recent work should be checked before counting on a full late-game lane.' },
  Limited: { label: 'Limited', description: 'Recent usage narrows how comfortably these arms can be used.' },
  Avoid: { label: 'Avoid', description: 'Recent usage has tightened the margin enough that these arms should not be treated as normal options.' },
  Unavailable: { label: 'Unavailable Pitchers', description: "Roster or workload context keeps these pitchers out of tonight's bullpen plan." },
}

const EMPTY_GROUP_COPY = {
  Available: 'No relievers are fully clear of recent workload right now.',
  Monitor: 'No relievers need an extra workload check right now.',
  Limited: 'No relievers have a narrowed-use read right now.',
  Avoid: 'No relievers are carrying enough recent use to fall out of the normal plan.',
  Unavailable: 'No pitchers are currently hidden from the bullpen plan.',
}

export function getBoardGroups(board) {
  const groups = Array.isArray(board?.groups) ? board.groups : []
  if (groups.length) {
    return groups.map(group => normalizeGroup(group))
  }
  // Fallback: present every canonical group as empty so the board structure is
  // stable even if the payload omitted groups.
  return BOARD_GROUP_ORDER.map(status => normalizeGroup({ status, pitchers: [] }))
}

function normalizeGroup(group) {
  const status = group?.status
  const fallback = GROUP_FALLBACK_META[status] || { label: status || 'Unknown', description: '' }
  const pitchers = Array.isArray(group?.pitchers) ? group.pitchers : []
  return {
    status,
    label: group?.label || fallback.label,
    description: group?.description || fallback.description,
    count: typeof group?.count === 'number' ? group.count : pitchers.length,
    pitchers,
    emptyCopy: EMPTY_GROUP_COPY[status] || 'No pitchers in this group.',
    badge: getAvailabilityBadgeView(status),
  }
}

// Observed usage role (Pitcher Usage Role Separation V1). Descriptive only —
// neutral styling so a role never reads as "better" than another. Defined roles
// share one neutral tone; low/insufficient roles are muted.
const ROLE_SHORT_LABELS = {
  late_high_leverage: 'Trust Arm',
  setup_bridge: 'Bridge Arm',
  middle_relief: 'Bridge Arm',
  long_multi_inning: 'Coverage Arm',
  low_unclear: 'Limited Read',
  insufficient_data: 'Limited Read',
}

const ELIGIBILITY_LABELS = {
  inactive_bullpen_relevant: 'Outside Freshness Window',
  uncertain_bullpen_relevance: 'Bullpen Role Unclear',
  // Role Authority V1 caveats (surfaced when role authority drives the board).
  // Relievers and starters need no chip: relievers are the default population
  // and starters are excluded, so only the uncertain roles carry a caveat.
  role_ambiguous: 'Swing Role',
  role_unknown: 'Role Not Established',
}

const ROSTER_STATUS_LABELS = {
  ACTIVE: 'Active MLB',
  IL_10: '10-Day IL',
  IL_15: '15-Day IL',
  IL_60: '60-Day IL',
  MINORS: 'Optioned / Minors',
  OPTIONED: 'Optioned',
  DFA: 'DFA',
  NON_ROSTER: 'Non-Roster',
  '40_MAN_ONLY': '40-Man (not active)',
  BEREAVEMENT: 'Bereavement List',
  PATERNITY: 'Paternity List',
  SUSPENDED: 'Suspended List',
  RESTRICTED: 'Restricted List',
  UNKNOWN: 'Roster Unknown',
}

const INACTIVE_ROSTER_STATUSES = new Set([
  'IL_10',
  'IL_15',
  'IL_60',
  'MINORS',
  'OPTIONED',
  'DFA',
  'NON_ROSTER',
  '40_MAN_ONLY',
  'BEREAVEMENT',
  'PATERNITY',
  'SUSPENDED',
  'RESTRICTED',
])

export function normalizeBullpenViewMode(mode) {
  return VALID_BULLPEN_VIEW_MODES.has(mode) ? mode : DEFAULT_BULLPEN_VIEW_MODE
}

export function bullpenViewModeRequiresUnavailableContext(mode) {
  return normalizeBullpenViewMode(mode) !== BULLPEN_VIEW_MODE_ACTIVE
}

function rosterStatusFromCard(card) {
  return card?.roster_status || card?.availability?.roster_status || null
}

export function isRosterUnavailableCard(card) {
  const rosterStatus = rosterStatusFromCard(card)
  const visibility = card?.visibility || {}
  const hasInactiveRosterStatus = (
    rosterStatus?.is_inactive_context === true
    || INACTIVE_ROSTER_STATUSES.has(rosterStatus?.status)
  )

  return (
    hasInactiveRosterStatus
    || visibility.is_unavailable_roster_status === true
  )
}

export function isActiveRosterCard(card) {
  if (isRosterUnavailableCard(card)) return false

  const rosterStatus = rosterStatusFromCard(card)
  const visibility = card?.visibility || {}
  if (visibility.is_active_roster_option === false) return false
  if (visibility.is_active_roster_option === true) return true

  if (rosterStatus && typeof rosterStatus === 'object') {
    if (rosterStatus.is_active_mlb === true) return true
    if (
      rosterStatus.is_active_mlb === false
      || rosterStatus.is_authoritative === false
      || rosterStatus.status === 'UNKNOWN'
    ) {
      return false
    }
    return rosterStatus.status === 'ACTIVE'
  }

  return true
}

export function cardMatchesBullpenViewMode(card, mode) {
  const normalized = normalizeBullpenViewMode(mode)
  if (normalized === BULLPEN_VIEW_MODE_ACTIVE_PLUS_UNAVAILABLE) return true
  const rosterUnavailable = isRosterUnavailableCard(card)
  if (normalized === BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY) return rosterUnavailable
  return isActiveRosterCard(card)
}

export function filterBoardForViewMode(board, mode) {
  const normalized = normalizeBullpenViewMode(mode)
  if (!board || normalized === BULLPEN_VIEW_MODE_ACTIVE_PLUS_UNAVAILABLE) {
    return board
  }

  const sourceGroups = getBoardGroups(board)
  const filteredGroups = sourceGroups
    .map(group => ({
      ...group,
      pitchers: group.pitchers.filter(card => cardMatchesBullpenViewMode(card, normalized)),
    }))
    .map(group => ({
      ...group,
      count: group.pitchers.length,
    }))
  const displayGroups = normalized === BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY
    ? filteredGroups.filter(group => group.status === 'Unavailable' || group.count > 0)
    : filteredGroups
  const totalPitchers = displayGroups.reduce((sum, group) => sum + group.count, 0)

  return {
    ...board,
    groups: displayGroups,
    total_pitchers: totalPitchers,
    view_mode: normalized,
  }
}

export function getBullpenViewModeEmptyState(mode) {
  if (normalizeBullpenViewMode(mode) === BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY) {
    return {
      title: 'No relievers are out of the current bullpen plan.',
      subtitle: 'Active relievers are hidden in this view so roster-limited arms stay easy to audit.',
    }
  }
  return null
}

export function getEligibilityView(eligibility) {
  if (!eligibility) return null
  const status = eligibility.status || 'bullpen_relevant'
  const label = ELIGIBILITY_LABELS[status]
  if (!label) return null
  return {
    status,
    label,
    confidence: eligibility.confidence || 'low',
    confidenceLabel: formatConfidence(eligibility.confidence),
    reason: eligibility.reason || null,
    tone: {
      borderColor: 'rgba(245,166,35,0.45)',
      backgroundColor: 'rgba(245,166,35,0.10)',
      color: '#f5a623',
    },
  }
}

export function getRosterStatusView(rosterStatus) {
  if (!rosterStatus) return null
  const status = rosterStatus.status || 'UNKNOWN'
  const isInactive = INACTIVE_ROSTER_STATUSES.has(status)
  const isUnknown = status === 'UNKNOWN' || rosterStatus.is_authoritative === false
  const label = rosterStatus.label || ROSTER_STATUS_LABELS[status] || 'Roster status'
  return {
    status,
    label,
    isInactive,
    isUnknown,
    confidence: rosterStatus.confidence || (isUnknown ? 'low' : 'high'),
    confidenceLabel: formatConfidence(rosterStatus.confidence || (isUnknown ? 'low' : 'high')),
    source: rosterStatus.source || null,
    recentReliefAudit: rosterStatus.recent_relief_audit || null,
    limitations: Array.isArray(rosterStatus.limitations) ? rosterStatus.limitations : [],
    evidence: Array.isArray(rosterStatus.evidence) ? rosterStatus.evidence : [],
    tone: isInactive
      ? { borderColor: '#ef444455', backgroundColor: '#ef444412', color: '#fca5a5' }
      : isUnknown
        ? { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' }
        : { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7' },
  }
}

export function getRosterStatusSummaryView(summary) {
  const payload = summary || {}
  const limitations = Array.isArray(payload.limitations) ? payload.limitations : []
  const authority = payload.authority || 'none'
  const totalCandidates = Number(payload.total_candidates || 0)
  const knownCount = Number(payload.known_count || 0)
  const unknownCount = Number(payload.included_unknown_count ?? payload.unknown_count ?? 0)
  const inactiveContextCount = Number(payload.inactive_context_count || 0)
  const activeMlbCount = Number(payload.active_mlb_count || 0)
  const excludedInactiveCount = Number(payload.excluded_inactive_count || 0)
  // Every count the board shows must map to evidence a reader can open. Only the
  // roster-inactive arms shown on the board as cards (inactiveContextCount) have
  // that evidence, so the "Unavailable Pitchers" figure reflects exactly those.
  // Roster-inactive arms BaseballOS is aware of but does not list as cards
  // (excludedInactiveCount) are reported on their own line rather than folded in,
  // so a visible count never claims more pitchers than the cards behind it.
  const unavailablePitchersCount = inactiveContextCount
  const notShownRosterContextCount = excludedInactiveCount
  const rosterContextTotalCount = inactiveContextCount + excludedInactiveCount
  const coveragePct = totalCandidates > 0 ? Math.round((knownCount / totalCandidates) * 100) : null
  const shouldShow = (
    totalCandidates > 0
    || limitations.length > 0
    || unknownCount > 0
    || rosterContextTotalCount > 0
  )
  return {
    shouldShow,
    authority,
    label: authority === 'available'
      ? 'Roster context ready'
      : authority === 'partial'
        ? 'Roster context partial'
        : authority === 'unavailable'
          ? 'Roster context unavailable'
          : 'Roster context not loaded',
    activeMlbCount,
    unknownCount,
    inactiveContextCount,
    excludedInactiveCount,
    unavailablePitchersCount,
    notShownRosterContextCount,
    rosterContextTotalCount,
    coverageLabel: coveragePct == null ? 'Not loaded' : `${coveragePct}%`,
    limitations,
    tone: authority === 'available'
      ? { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7' }
      : { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' },
  }
}

// Map a canonical Roster Authority evidence list to a presentation-safe shape. Engine
// field names (is_active_mlb, is_inactive_context, status codes) never reach the UI — the
// board shows the human roster-status label, the availability read, and a plain reason.
function rosterAuthorityEvidenceList(list) {
  return (Array.isArray(list) ? list : []).map(entry => ({
    pitcherId: entry?.pitcher_id ?? null,
    name: entry?.name || '—',
    rosterStatusLabel: entry?.roster_status_label || 'Roster status',
    availability: entry?.availability || null,
    reason: entry?.reason || null,
  }))
}

// Canonical Roster Authority view-model for the board banner (CRC Phase 4 migration).
//
// The board no longer computes roster truth — it displays it. Every count here comes
// straight from the backend ``roster_authority`` object, which is invariant across the
// Active / Active+Unavailable / Unavailable views. The ONLY view-dependent value is
// ``shownOffActiveRoster`` (how many off-roster arms are rendered as cards in the current
// filter), derived from the supplied rendered cards — never from the canonical counts.
export function getRosterAuthorityView(rosterAuthority, { renderedCards = null } = {}) {
  const authority = rosterAuthority && typeof rosterAuthority === 'object' ? rosterAuthority : {}
  const counts = authority.counts || {}
  const population = authority.population || {}
  const evidence = authority.evidence || {}
  const limitations = Array.isArray(authority.limitations) ? authority.limitations : []
  const hasAuthority = Boolean(authority.capability || authority.counts || authority.population)

  const bullpenArms = Number(counts.bullpen_arms || 0)
  const offActiveRoster = Number(counts.inactive_roster_context_count || 0)
  const rosterStatusPending = Number(counts.roster_unknown_count || 0)
  const totalCandidates = Number(population.total_candidates || 0)
  const coverage = typeof population.roster_status_coverage === 'number'
    ? population.roster_status_coverage
    : null

  const offRosterEvidence = rosterAuthorityEvidenceList(evidence.inactive_roster_context_count)
  const pendingEvidence = rosterAuthorityEvidenceList(evidence.roster_unknown_count)
  const bullpenEvidence = rosterAuthorityEvidenceList(evidence.bullpen_arms)

  // Presentation-only: how many off-roster arms have a card in the current view.
  const renderedIds = Array.isArray(renderedCards)
    ? new Set(renderedCards.map(card => card?.pitcher_id).filter(id => id != null))
    : null
  const shownOffActiveRoster = renderedIds == null
    ? null
    : offRosterEvidence.filter(entry => entry.pitcherId != null && renderedIds.has(entry.pitcherId)).length

  const statusLabel = coverage == null
    ? 'Roster status not loaded'
    : coverage >= 1
      ? 'Roster status confirmed'
      : coverage > 0
        ? 'Roster status partial'
        : 'Roster status unavailable'
  const isComplete = coverage != null && coverage >= 1 && rosterStatusPending === 0

  return {
    hasAuthority,
    invariant: authority.invariant === true,
    shouldShow: hasAuthority && (
      totalCandidates > 0 || offActiveRoster > 0 || rosterStatusPending > 0 || limitations.length > 0
    ),
    isProminent: !isComplete || offActiveRoster > 0 || limitations.length > 0,
    statusLabel,
    bullpenArms,
    offActiveRoster,
    shownOffActiveRoster,
    rosterStatusPending,
    coverage,
    coverageLabel: coverage == null ? 'Not loaded' : `${Math.round(coverage * 100)}%`,
    evidence: {
      bullpenArms: bullpenEvidence,
      offActiveRoster: offRosterEvidence,
      rosterStatusPending: pendingEvidence,
    },
    limitations,
    tone: isComplete
      ? { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7' }
      : { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' },
  }
}

export function getRoleView(role) {
  if (!role) return null
  const key = role.role_key || 'insufficient_data'
  const muted = key === 'insufficient_data' || key === 'low_unclear'
  return {
    key,
    label: role.role || ROLE_SHORT_LABELS[key] || 'Usage role',
    shortLabel: ROLE_SHORT_LABELS[key] || role.role || 'Usage role',
    confidence: role.confidence || 'none',
    confidenceLabel: formatConfidence(role.confidence),
    reason: role.short_reason || null,
    evidence: Array.isArray(role.evidence) ? role.evidence : [],
    limitations: Array.isArray(role.limitations) ? role.limitations : [],
    tone: muted
      ? { borderColor: 'rgba(148,163,184,0.30)', backgroundColor: 'rgba(148,163,184,0.08)', color: '#cbd5e1' }
      : { borderColor: 'rgba(129,140,248,0.40)', backgroundColor: 'rgba(129,140,248,0.12)', color: '#c7d2fe' },
  }
}

// Bullpen-wide usage-role composition (counts per role), for the dashboard.
// Descriptive only — neutral tones, never ordered by "value".
export function getRolesSummaryView(roles) {
  const order = Array.isArray(roles?.order) && roles.order.length
    ? roles.order
    : Object.keys(ROLE_SHORT_LABELS)
  const counts = roles?.counts || {}
  const total = typeof roles?.total === 'number'
    ? roles.total
    : order.reduce((sum, key) => sum + (Number(counts[key]) || 0), 0)
  return {
    total,
    rows: order.map(key => {
      const muted = key === 'insufficient_data' || key === 'low_unclear'
      return {
        key,
        label: ROLE_SHORT_LABELS[key] || key,
        count: Number(counts[key]) || 0,
        tone: muted
          ? { borderColor: 'rgba(148,163,184,0.30)', backgroundColor: 'rgba(148,163,184,0.08)', color: '#cbd5e1' }
          : { borderColor: 'rgba(129,140,248,0.40)', backgroundColor: 'rgba(129,140,248,0.12)', color: '#c7d2fe' },
      }
    }),
  }
}

export function getBoardCardView(card, freshness = null) {
  const badge = getAvailabilityBadgeView(card?.availability_status)
  const dataState = String(card?.data_state || 'unknown').toLowerCase()
  const showDataNote = dataState && !['fresh', 'unknown'].includes(dataState)
  const platformDate = platformDateFromFreshness(freshness)
  const lastAppearance = [
    card?.last_workload_appearance,
    card?.lastWorkloadAppearance,
    card?.last_appearance,
    card?.lastAppearance,
  ].find(isWorkloadAppearance) || null
  const lastAppearanceLabel = compactWorkloadAppearanceLabel(lastAppearance, platformDate)
  return {
    pitcherId: card?.pitcher_id,
    name: card?.name || '—',
    status: badge.status,
    badge,
    fatigueScore: card?.fatigue_score != null ? Math.round(card.fatigue_score) : null,
    confidenceLabel: formatConfidence(card?.confidence),
    shortReason: lastAppearanceLabel || dayAwareAppearanceReason(card?.short_reason, lastAppearance, platformDate) || null,
    lastAppearance,
    lastAppearanceLabel,
    dataState,
    dataStateView: showDataNote ? getDataStateView(dataState) : null,
    reasons: dayAwareAppearanceReasons(card?.reasons, lastAppearance, platformDate),
    limitations: Array.isArray(card?.limitations) ? card.limitations : [],
    pitcherLabels: getPitcherLabels(card),
    role: getRoleView(card?.role),
    eligibility: getEligibilityView(card?.eligibility),
    rosterStatus: getRosterStatusView(card?.roster_status),
  }
}

export function getDataProvenance(freshness) {
  const f = freshness || {}
  const dataThrough = fmtDataDate(f.data_through)
  const completedGamesLine = completedGamesDataLine(f.data_through)
  const servedPreviousView = f.served_consistency_state === 'previous_published_view'
  const isLive = f.is_current === true && (f.sync_status === 'success' || f.sync_status === 'ok')
  const isStale = f.is_stale === true || f.freshness_state === 'stale'

  if (!dataThrough) {
    return {
      state: 'none',
      label: 'No data loaded',
      detail: null,
      dataThrough: null,
      completedGamesLine: null,
      throughHint: 'No completed MLB games are loaded yet.',
      isLive: false,
      tone: { borderColor: 'rgba(148,163,184,0.30)', backgroundColor: 'rgba(148,163,184,0.08)', color: '#cbd5e1', dot: '#94a3b8' },
    }
  }
  if (servedPreviousView) {
    const failed = f.current_sync_status === 'failed'
    return {
      state: failed ? 'previous_failed' : 'previous_running',
      label: failed ? 'Last published view' : 'Sync in progress',
      detail: `through ${dataThrough}`,
      dataThrough,
      completedGamesLine,
      throughHint: failed
        ? 'Latest sync failed before publish; serving the last fully published view.'
        : 'Sync is in progress; serving the last fully published view.',
      isLive: false,
      tone: { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623', dot: '#f5a623' },
    }
  }
  if (isStale) {
    return {
      state: 'stale',
      label: 'Outdated data',
      detail: `through ${dataThrough}`,
      dataThrough,
      completedGamesLine,
      throughHint: f.label || 'Completed-game coverage is outside the active freshness window.',
      isLive: false,
      tone: { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623', dot: '#f5a623' },
    }
  }
  if (isLive) {
    return {
      state: 'live',
      label: 'Current stored data',
      detail: `through ${dataThrough}`,
      dataThrough,
      completedGamesLine,
      throughHint: 'Data coverage uses the most recent completed game in the dataset, not necessarily today.',
      isLive: true,
      tone: { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7', dot: '#10b981' },
    }
  }
  return {
    state: 'sample',
    label: 'Sample data',
    detail: `through ${dataThrough}`,
    dataThrough,
    completedGamesLine,
    throughHint: 'Data coverage uses the most recent completed game in the dataset (historical snapshot, not live).',
    isLive: false,
    tone: { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623', dot: '#f5a623' },
  }
}

export function getBoardFreshnessView(freshness) {
  const f = freshness || {}
  const isCurrent = f.is_current !== false && f.is_stale !== true && f.freshness_state !== 'stale'
  const isStale = f.is_stale === true || f.freshness_state === 'stale' || !isCurrent
  const limitations = Array.isArray(f.limitations) ? f.limitations : []
  return {
    isCurrent,
    isStale,
    dataThrough: fmtDataDate(f.data_through) || null,
    lastSync: fmtSyncDate(f.last_successful_sync) || null,
    syncStatus: f.sync_status || null,
    freshnessState: f.freshness_state || null,
    reasonCodes: Array.isArray(f.reason_codes) ? f.reason_codes : [],
    dataAgeDays: f.data_age_days ?? null,
    label: f.label || null,
    limitations,
    healthLabel: isCurrent ? 'Current' : 'Not Current',
    tone: isCurrent
      ? { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7' }
      : { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' },
    dot: isCurrent ? '#10b981' : '#f5a623',
  }
}

// Health-state presentation. The state itself is computed deterministically on
// the backend; this only maps it to plain styling for the context summary.
const HEALTH_TONE = {
  manageable: { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7', dot: '#10b981' },
  monitoring: { borderColor: '#eab30855', backgroundColor: '#eab30812', color: '#fde047', dot: '#eab308' },
  elevated: { borderColor: '#f9731655', backgroundColor: '#f9731612', color: '#fdba74', dot: '#f97316' },
  constrained: { borderColor: '#ef444455', backgroundColor: '#ef444412', color: '#fca5a5', dot: '#ef4444' },
  no_data: { borderColor: 'rgba(148,163,184,0.32)', backgroundColor: 'rgba(148,163,184,0.09)', color: '#cbd5e1', dot: '#94a3b8' },
}

const STRESS_TONE = {
  manageable: HEALTH_TONE.manageable,
  monitoring: HEALTH_TONE.monitoring,
  elevated: HEALTH_TONE.elevated,
  constrained: HEALTH_TONE.constrained,
  muted: HEALTH_TONE.no_data,
}

export function getBullpenStressView(stress) {
  if (!stress) {
    return {
      hasStress: false,
      conceptLabel: 'Overall Availability',
      label: null,
      summary: null,
      reasons: [],
      limitations: [],
      confidenceLabel: formatConfidence(null),
      isLimited: true,
      tone: STRESS_TONE.muted,
    }
  }

  const tone = STRESS_TONE[stress.tone] || STRESS_TONE[stress.state] || STRESS_TONE.muted
  const reasons = Array.isArray(stress.reasons) ? stress.reasons : []
  const limitations = Array.isArray(stress.limitations) ? stress.limitations : []
  return {
    hasStress: true,
    conceptLabel: 'Overall Availability',
    state: stress.state || 'no_data',
    label: stress.label || 'No Read',
    summary: stress.summary || 'Not enough current bullpen data to assess stress.',
    reasons,
    limitations,
    reasonCodes: Array.isArray(stress.reason_codes) ? stress.reason_codes : [],
    confidenceLabel: formatConfidence(stress.confidence),
    isLimited: stress.is_stale === true || stress.label === 'No Read' || stress.confidence === 'low',
    tone,
  }
}

// Snapshot rows mirror the board's five groups, in the same reading order.
const SNAPSHOT_ROWS = [
  { status: 'Available', label: 'Available', key: 'available' },
  { status: 'Monitor', label: 'Monitor', key: 'monitor' },
  { status: 'Limited', label: 'Limited', key: 'limited' },
  { status: 'Avoid', label: 'Avoid', key: 'avoid' },
  { status: 'Unavailable', label: 'Unavailable', key: 'unavailable' },
]

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

export function getBoardTotals(board) {
  const groups = getBoardGroups(board)
  const total = typeof board?.total_pitchers === 'number'
    ? board.total_pitchers
    : groups.reduce((sum, group) => sum + group.count, 0)
  return {
    total,
    isEmpty: total === 0,
    countsByStatus: Object.fromEntries(groups.map(group => [group.status, group.count])),
  }
}
