import {
  formatConfidence,
  getAvailabilityBadgeView,
  getAvailabilityStatusLabel,
  getDataStateView,
} from '../availabilityView'
import {
  getBoardContextView as getOperatingBoardContextView,
  getTeamOperatingStateContext as getOperatingTeamStateContext,
  teamOperatingStateFreshnessIsDegraded as operatingStateFreshnessIsDegraded,
} from '../../../adapters/operatingStateReadModel'
import {
  completedGamesDataLine,
  fmtDataDate,
  fmtSyncDate,
  freshnessDataThrough,
  freshnessIsCurrent,
} from '../../dashboard/syncStatusView'
import { isSampleFreshness } from '../../UI/Freshness'
import {
  compactWorkloadAppearanceLabel,
  currentUserBaseballDay,
  dayAwareAppearanceReason,
  dayAwareAppearanceReasons,
  isWorkloadAppearance,
} from '../../../utils/appearanceLanguage'
import { getPitcherLabels, PITCHER_ROLE_LABELS, USAGE_ROLE_PUBLIC_ROLES } from '../../../utils/pitcherLabels'

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
  Monitor: { label: 'On Watch', description: 'Recent work should be checked before counting on a full late-game lane.' },
  Limited: { label: 'Limited', description: 'Recent usage narrows how comfortably these arms can be used.' },
  Unavailable: { label: 'Unavailable', description: "Recent workload or roster context keeps these arms out of tonight's available group." },
}

const EMPTY_GROUP_COPY = {
  Available: 'No relievers are fully clear of recent workload right now.',
  Monitor: 'No relievers need an extra workload check right now.',
  Limited: 'No relievers have a narrowed-use read right now.',
  Unavailable: "No pitchers are currently out of tonight's available group.",
}

// The backend can send both a workload-based 'Avoid' group and a roster-based
// 'Unavailable' group. Publicly there is only one Unavailable read, so the two
// buckets merge into a single group before anything renders. Workload-based
// arms list first, matching the canonical backend order.
function rosterClaimNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function rosterCountsAreWithheld(board) {
  const readiness = board?.roster_authority?.readiness || board?.rosterReadiness || board?.roster_readiness || {}
  return readiness.counts_withheld === true || readiness.countsWithheld === true || readiness.claims_available === false || readiness.claimsAvailable === false
}

function mergePublicUnavailableGroups(groups, { countsWithheld = false } = {}) {
  const unavailableStatuses = new Set(['Avoid', 'Unavailable'])
  const toMerge = groups.filter(group => unavailableStatuses.has(group?.status))
  if (!toMerge.length) return groups

  const merged = {
    status: 'Unavailable',
    label: GROUP_FALLBACK_META.Unavailable.label,
    description: GROUP_FALLBACK_META.Unavailable.description,
    count: countsWithheld ? null : toMerge.reduce((sum, group) => sum + (group.count || 0), 0),
    countWithheld: countsWithheld || toMerge.some(group => group.countWithheld),
    pitchers: toMerge.flatMap(group => group.pitchers),
    emptyCopy: EMPTY_GROUP_COPY.Unavailable,
    badge: getAvailabilityBadgeView('Unavailable'),
  }

  const result = []
  let placed = false
  for (const group of groups) {
    if (unavailableStatuses.has(group?.status)) {
      if (!placed) {
        result.push(merged)
        placed = true
      }
      continue
    }
    result.push(group)
  }
  return result
}

export function getBoardGroups(board) {
  const groups = Array.isArray(board?.groups) ? board.groups : []
  const countsWithheld = rosterCountsAreWithheld(board)
  if (groups.length) {
    return mergePublicUnavailableGroups(
      groups.map(group => normalizeGroup(group, { countsWithheld })),
      { countsWithheld },
    )
  }
  // Fallback: present every canonical group as empty so the board structure is
  // stable even if the payload omitted groups.
  return mergePublicUnavailableGroups(
    BOARD_GROUP_ORDER.map(status => normalizeGroup({ status, pitchers: [] }, { countsWithheld })),
    { countsWithheld },
  )
}

function normalizeGroup(group, { countsWithheld = false } = {}) {
  const status = group?.status
  const fallback = GROUP_FALLBACK_META[status] || { label: status || 'Unknown', description: '' }
  const pitchers = Array.isArray(group?.pitchers) ? group.pitchers : []
  const countWithheld = countsWithheld || group?.count_withheld === true || group?.countWithheld === true
  return {
    status,
    label: getAvailabilityStatusLabel(group?.label || fallback.label),
    description: group?.description || fallback.description,
    count: countWithheld ? null : (typeof group?.count === 'number' ? group.count : pitchers.length),
    countWithheld,
    pitchers,
    emptyCopy: EMPTY_GROUP_COPY[status] || 'No pitchers in this group.',
    badge: getAvailabilityBadgeView(status),
  }
}

// Observed usage role (Pitcher Usage Role Separation V1). Descriptive only —
// neutral styling so a role never reads as "better" than another. Defined roles
// share one neutral tone; low/insufficient roles are muted.
// Role wording comes from the one canonical public role vocabulary in
// utils/pitcherLabels.js so the dashboard and the pitcher chips can never
// describe the same role key with different baseball meanings. low_unclear
// keeps its own presentation wording for the same limited-read meaning.
const ROLE_SHORT_LABELS = {
  ...Object.fromEntries(
    Object.entries(USAGE_ROLE_PUBLIC_ROLES).map(([key, role]) => [key, role.label]),
  ),
  low_unclear: 'Unclear Role',
}

// Final public role keys (backend public_role_read / dashboard composition)
// labeled from the same canonical catalog as the pitcher chips.
const PUBLIC_ROLE_SHORT_LABELS = Object.fromEntries(
  Object.values(PITCHER_ROLE_LABELS).map(role => [role.key, role.label]),
)

// Legacy-payload compatibility (payloads authored before public_role_read
// existed). Detailed observed-pattern wording per public role key, and the one
// raw classifier key each public key confirms. Used ONLY to resolve legacy
// cards safely — the frontend never reclassifies usage or invents evidence.
const PUBLIC_KEY_TO_PATTERN = {
  trust_arm: 'Late-Inning / High-Leverage Pattern',
  bridge_arm: 'Setup / Bridge Pattern',
  depth_arm: 'Middle Relief Pattern',
  coverage_arm: 'Long Relief / Multi-Inning Pattern',
}

const COMPATIBLE_RAW_ROLE_KEY = {
  trust_arm: 'late_high_leverage',
  bridge_arm: 'setup_bridge',
  depth_arm: 'middle_relief',
  coverage_arm: 'long_multi_inning',
}

const LIMITED_RAW_ROLE_KEYS = new Set(['low_unclear', 'insufficient_data'])

const GUARDED_PUBLIC_REASON = 'Recent usage does not support one clear bullpen role.'

const MUTED_ROLE_KEYS = new Set(['insufficient_data', 'low_unclear', 'limited_read'])

const MUTED_ROLE_TONE = { borderColor: 'rgba(148,163,184,0.30)', backgroundColor: 'rgba(148,163,184,0.08)', color: '#cbd5e1' }
const NEUTRAL_ROLE_TONE = { borderColor: 'rgba(129,140,248,0.40)', backgroundColor: 'rgba(129,140,248,0.12)', color: '#c7d2fe' }

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
  RESTRICTED: 'Roster Unavailable',
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
      count: rosterCountsAreWithheld(board) ? null : group.pitchers.length,
    }))
  const displayGroups = normalized === BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY
    ? filteredGroups.filter(group => group.status === 'Unavailable' || (group.count || 0) > 0)
    : filteredGroups
  const totalPitchers = rosterCountsAreWithheld(board)
    ? null
    : displayGroups.reduce((sum, group) => sum + group.count, 0)

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
  const readiness = authority.readiness || {}
  const readinessLimitations = Array.isArray(readiness.reader_limitations)
    ? readiness.reader_limitations
    : Array.isArray(readiness.readerLimitations)
      ? readiness.readerLimitations
      : []
  const countsWithheld = readiness.counts_withheld === true || readiness.claims_available === false
  const hasAuthority = Boolean(authority.capability || authority.counts || authority.population)

  const bullpenArms = rosterClaimNumber(counts.bullpen_arms)
  const offActiveRoster = rosterClaimNumber(counts.inactive_roster_context_count)
  const rosterStatusPending = rosterClaimNumber(counts.roster_unknown_count)
  const totalCandidates = rosterClaimNumber(population.total_candidates)
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
    : countsWithheld
      ? null
      : offRosterEvidence.filter(entry => entry.pitcherId != null && renderedIds.has(entry.pitcherId)).length

  const statusLabel = countsWithheld
    ? 'Roster status unverified'
    : coverage == null
    ? 'Roster status not loaded'
    : coverage >= 1
      ? 'Roster status confirmed'
      : coverage > 0
        ? 'Roster status partial'
        : 'Roster status unavailable'
  const isComplete = !countsWithheld && coverage != null && coverage >= 1 && rosterStatusPending === 0
  const mergedLimitations = [...limitations, ...readinessLimitations]

  return {
    hasAuthority,
    invariant: authority.invariant === true,
    shouldShow: hasAuthority && (
      countsWithheld || (totalCandidates || 0) > 0 || (offActiveRoster || 0) > 0 || (rosterStatusPending || 0) > 0 || mergedLimitations.length > 0
    ),
    isProminent: countsWithheld || !isComplete || (offActiveRoster || 0) > 0 || mergedLimitations.length > 0,
    countsWithheld,
    statusLabel,
    bullpenArms,
    offActiveRoster,
    shownOffActiveRoster,
    rosterStatusPending,
    coverage,
    coverageLabel: countsWithheld ? 'Withheld' : (coverage == null ? 'Not loaded' : `${Math.round(coverage * 100)}%`),
    evidence: {
      bullpenArms: bullpenEvidence,
      offActiveRoster: offRosterEvidence,
      rosterStatusPending: pendingEvidence,
    },
    limitations: mergedLimitations,
    tone: isComplete
      ? { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7' }
      : { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' },
  }
}

export function getRoleView(role) {
  if (!role) return null
  const key = role.role_key || 'insufficient_data'
  const muted = MUTED_ROLE_KEYS.has(key)
  return {
    key,
    label: role.role || ROLE_SHORT_LABELS[key] || 'Usage role',
    shortLabel: ROLE_SHORT_LABELS[key] || role.role || 'Usage role',
    confidence: role.confidence || 'none',
    confidenceLabel: formatConfidence(role.confidence),
    reason: role.short_reason || null,
    evidence: Array.isArray(role.evidence) ? role.evidence : [],
    limitations: Array.isArray(role.limitations) ? role.limitations : [],
    tone: muted ? MUTED_ROLE_TONE : NEUTRAL_ROLE_TONE,
  }
}

// Mirrors backend author_public_role_read for legacy payloads authored before
// public_role_read existed: the backend-authored public label is the verdict;
// the raw role only supplies compatible pattern wording, evidence, and
// limitations. A contradictory raw headline (or a raw reason that reads as the
// rejected verdict) is replaced by the canonical public wording.
function legacyPublicRoleRead(role, label) {
  const publicKey = String(label.key || '').trim().toLowerCase()
  const pattern = PUBLIC_KEY_TO_PATTERN[publicKey]
  const evidence = Array.isArray(role.evidence) ? role.evidence : []
  const limitations = Array.isArray(role.limitations) ? role.limitations : []

  if (pattern) {
    const compatible = COMPATIBLE_RAW_ROLE_KEY[publicKey] === role.role_key
    return {
      kind: 'public_role_read',
      key: publicKey,
      label: PUBLIC_ROLE_SHORT_LABELS[publicKey] || label.label,
      headline: compatible ? (role.role || pattern) : pattern,
      confidence: role.confidence,
      reason: compatible ? role.short_reason : null,
      evidence,
      limitations,
      source: label.source || 'backend',
    }
  }

  // limited_read (or an unrecognized key, which fails closed the same way):
  // never headline a concrete raw role the public authority did not confirm.
  const naturallyLimited = LIMITED_RAW_ROLE_KEYS.has(role.role_key)
  return {
    kind: 'public_role_read',
    key: 'limited_read',
    label: PUBLIC_ROLE_SHORT_LABELS.limited_read,
    headline: PUBLIC_ROLE_SHORT_LABELS.limited_read,
    confidence: naturallyLimited ? role.confidence : 'low',
    reason: naturallyLimited ? role.short_reason : GUARDED_PUBLIC_REASON,
    evidence,
    limitations,
    source: label.source || 'backend',
  }
}

// One resolver for the public role conclusion, in authority order:
//   1. public_role_read (modern payloads)
//   2. backend-authored pitcher_labels.role, resolved against the raw role
//      (legacy payloads authored before public_role_read)
//   3. raw role alone (historical payloads that predate both public fields)
// The raw role can never override or contradict an existing backend-authored
// public role label.
export function resolvePublicRoleRead(card) {
  if (card?.public_role_read) return getPublicRoleReadView(card.public_role_read)
  const labels = card?.pitcher_labels || card?.pitcherLabels || {}
  const label = labels.role
  const role = card?.role
  if (!label || typeof label !== 'object' || !label.key) return getRoleView(role)
  if (!role) return null
  return getPublicRoleReadView(legacyPublicRoleRead(role, label))
}

// Final backend-authored public role read. When present it is the ONE public
// conclusion for the card: the disclosure headline comes from the backend
// (`headline`), so the frontend never re-selects the raw classifier role after
// the public authority has rejected it.
export function getPublicRoleReadView(read) {
  if (!read) return null
  const key = read.key || 'limited_read'
  const muted = MUTED_ROLE_KEYS.has(key)
  return {
    key,
    label: read.headline || read.label || PUBLIC_ROLE_SHORT_LABELS[key] || 'Usage role',
    shortLabel: read.label || PUBLIC_ROLE_SHORT_LABELS[key] || 'Usage role',
    confidence: read.confidence || 'none',
    confidenceLabel: formatConfidence(read.confidence),
    reason: read.reason || null,
    evidence: Array.isArray(read.evidence) ? read.evidence : [],
    limitations: Array.isArray(read.limitations) ? read.limitations : [],
    tone: muted ? MUTED_ROLE_TONE : NEUTRAL_ROLE_TONE,
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
      const muted = MUTED_ROLE_KEYS.has(key)
      return {
        key,
        label: ROLE_SHORT_LABELS[key] || PUBLIC_ROLE_SHORT_LABELS[key] || key,
        count: Number(counts[key]) || 0,
        tone: muted ? MUTED_ROLE_TONE : NEUTRAL_ROLE_TONE,
      }
    }),
  }
}

export function getBoardCardView(card, freshness = null, now = new Date()) {
  const badge = getAvailabilityBadgeView(card?.availability_status)
  const dataState = String(card?.data_state || 'unknown').toLowerCase()
  const showDataNote = dataState && !['fresh', 'unknown'].includes(dataState)
  // "Today" / "Yesterday" on a workload label are relative to the user's actual current day,
  // NOT the platform data-through date (which can lag behind the real day after a morning sync).
  // The platform date stays separate, in the Data Freshness / "Data through" provenance below.
  const userDay = currentUserBaseballDay(now)
  const lastAppearance = [
    card?.last_workload_appearance,
    card?.lastWorkloadAppearance,
    card?.last_appearance,
    card?.lastAppearance,
  ].find(isWorkloadAppearance) || null
  const lastAppearanceLabel = compactWorkloadAppearanceLabel(lastAppearance, userDay)
  return {
    pitcherId: card?.pitcher_id,
    name: card?.name || '—',
    status: badge.status,
    badge,
    fatigueScore: card?.fatigue_score != null ? Math.round(card.fatigue_score) : null,
    confidenceLabel: formatConfidence(card?.confidence),
    shortReason: lastAppearanceLabel || dayAwareAppearanceReason(card?.short_reason, lastAppearance, userDay) || null,
    lastAppearance,
    lastAppearanceLabel,
    dataState,
    dataStateView: showDataNote ? getDataStateView(dataState) : null,
    reasons: dayAwareAppearanceReasons(card?.reasons, lastAppearance, userDay),
    limitations: Array.isArray(card?.limitations) ? card.limitations : [],
    pitcherLabels: getPitcherLabels(card),
    // The one public role conclusion, resolved in authority order:
    // public_role_read -> pitcher_labels.role (legacy) -> raw role (historical).
    role: resolvePublicRoleRead(card),
    eligibility: getEligibilityView(card?.eligibility),
    rosterStatus: getRosterStatusView(card?.roster_status),
  }
}

export function getDataProvenance(freshness) {
  const f = freshness || {}
  const dataThroughSource = freshnessDataThrough(f)
  const dataThrough = fmtDataDate(dataThroughSource)
  const completedGamesLine = completedGamesDataLine(dataThroughSource)
  const servedPreviousView = (
    f.served_consistency_state === 'previous_published_view'
    || f.servedConsistencyState === 'previous_published_view'
  )
  const syncStatus = String(f.sync_status || f.syncStatus || '').toLowerCase()
  const freshnessState = String(f.freshness_state || f.freshnessState || f.state || '').toLowerCase()
  const isExplicitSample = isSampleFreshness(f)
  const isExplicitFailure = syncStatus === 'failed' || syncStatus === 'error'
  const isStale = f.is_stale === true || f.isStale === true || freshnessState === 'stale'
  const isLive = freshnessIsCurrent(f) && !isExplicitSample && !isExplicitFailure && !isStale

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
    const failed = (f.current_sync_status || f.currentSyncStatus) === 'failed'
    return {
      state: failed ? 'previous_failed' : 'previous_running',
      label: failed ? 'Last published view' : 'Published view; background refresh running',
      detail: `through ${dataThrough}`,
      dataThrough,
      completedGamesLine,
      throughHint: failed
        ? 'Latest sync failed before publish; serving the last fully published view.'
        : 'A background refresh is still running; serving the last fully published view.',
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
  if (isExplicitSample) {
    return {
      state: 'sample',
      label: 'Sample data',
      detail: `through ${dataThrough}`,
      dataThrough,
      completedGamesLine,
      throughHint: 'Data coverage uses the most recent completed game in the dataset (historical data, not live).',
      isLive: false,
      tone: { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623', dot: '#f5a623' },
    }
  }
  if (isLive) {
    return {
      state: 'live',
      label: 'Published view current',
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
    throughHint: 'Data coverage uses the most recent completed game in the dataset (historical data, not live).',
    isLive: false,
    tone: { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623', dot: '#f5a623' },
  }
}

export function getBoardFreshnessView(freshness) {
  const f = freshness || {}
  const isCurrent = freshnessIsCurrent(f)
  const freshnessState = String(f.freshness_state || f.freshnessState || f.state || '').toLowerCase()
  const isStale = f.is_stale === true || f.isStale === true || freshnessState === 'stale' || !isCurrent
  const limitations = Array.isArray(f.limitations) ? f.limitations : []
  return {
    isCurrent,
    isStale,
    dataThrough: fmtDataDate(freshnessDataThrough(f)) || null,
    lastSync: fmtSyncDate(f.last_successful_sync || f.lastSuccessfulSync) || null,
    syncStatus: f.sync_status || f.syncStatus || null,
    freshnessState: f.freshness_state || f.freshnessState || f.state || null,
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

const IMPLIED_COMPARISON_STRESS_COPY = /\b(less room than usual|than usual|normal board|baseline|clean room|expected)\b/i

function getCurrentStateStressSummary(summary, state) {
  const text = typeof summary === 'string' ? summary.trim() : ''
  if (!IMPLIED_COMPARISON_STRESS_COPY.test(text)) return text

  if (state === 'manageable') {
    return 'This pen has usable coverage right now.'
  }
  if (state === 'monitoring') {
    return 'This pen is usable, but a few arms are already in the yellow.'
  }
  if (state === 'constrained') {
    return 'Clean Options are tight right now.'
  }
  return 'Cleanly available options are limited right now.'
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
    summary: getCurrentStateStressSummary(stress.summary, stress.state) || 'Not enough current bullpen data to assess stress.',
    reasons,
    limitations,
    reasonCodes: Array.isArray(stress.reason_codes) ? stress.reason_codes : [],
    confidenceLabel: formatConfidence(stress.confidence),
    isLimited: stress.is_stale === true || stress.label === 'No Read' || stress.confidence === 'low',
    tone,
  }
}

export function getBoardContextView(board) {
  return getOperatingBoardContextView(board)
}

export function teamOperatingStateFreshnessIsDegraded(freshness) {
  return operatingStateFreshnessIsDegraded(freshness)
}

export function getTeamOperatingStateContext(board) {
  return getOperatingTeamStateContext(board)
}

export function getBoardTotals(board) {
  const groups = getBoardGroups(board)
  const countsWithheld = rosterCountsAreWithheld(board)
  const total = countsWithheld
    ? null
    : typeof board?.total_pitchers === 'number'
    ? board.total_pitchers
    : groups.reduce((sum, group) => sum + group.count, 0)
  return {
    total,
    countWithheld: countsWithheld,
    isEmpty: !countsWithheld && total === 0,
    countsByStatus: Object.fromEntries(groups.map(group => [group.status, group.count])),
  }
}
