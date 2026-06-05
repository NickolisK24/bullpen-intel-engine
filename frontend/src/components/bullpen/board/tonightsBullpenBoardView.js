import {
  formatConfidence,
  getAvailabilityBadgeView,
  getDataStateView,
} from '../availabilityView'
import { fmtDataDate, fmtSyncDate } from '../../dashboard/syncStatusView'

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

const GROUP_FALLBACK_META = {
  Available: { label: 'Available Tonight', description: 'Workload signals are inside normal ranges.' },
  Monitor: { label: 'Monitor', description: 'Worth a look at recent workload before counting on these arms.' },
  Limited: { label: 'Limited', description: 'Recent workload suggests restricted use tonight.' },
  Avoid: { label: 'Avoid', description: 'Meaningful recent-use load on these arms.' },
  Unavailable: { label: 'Unavailable', description: "Should not be counted for tonight's planning." },
}

const EMPTY_GROUP_COPY = {
  Available: 'No arms are clear of recent workload right now.',
  Monitor: 'No arms need a workload check tonight.',
  Limited: 'No arms are workload-restricted tonight.',
  Avoid: 'No arms are carrying heavy recent use.',
  Unavailable: 'No arms are ruled out tonight.',
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
  late_high_leverage: 'Late / High-Leverage',
  setup_bridge: 'Setup / Bridge',
  middle_relief: 'Middle Relief',
  long_multi_inning: 'Long / Multi-Inning',
  low_unclear: 'Low / Unclear Usage',
  insufficient_data: 'Insufficient Data',
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

export function getBoardCardView(card) {
  const badge = getAvailabilityBadgeView(card?.availability_status)
  const dataState = String(card?.data_state || 'unknown').toLowerCase()
  const showDataNote = dataState && !['fresh', 'unknown'].includes(dataState)
  return {
    pitcherId: card?.pitcher_id,
    name: card?.name || '—',
    status: badge.status,
    badge,
    fatigueScore: card?.fatigue_score != null ? Math.round(card.fatigue_score) : null,
    confidenceLabel: formatConfidence(card?.confidence),
    shortReason: card?.short_reason || null,
    dataState,
    dataStateView: showDataNote ? getDataStateView(dataState) : null,
    reasons: Array.isArray(card?.reasons) ? card.reasons : [],
    limitations: Array.isArray(card?.limitations) ? card.limitations : [],
    role: getRoleView(card?.role),
  }
}

export function getBoardFreshnessView(freshness) {
  const f = freshness || {}
  const isCurrent = f.is_current !== false
  const limitations = Array.isArray(f.limitations) ? f.limitations : []
  return {
    isCurrent,
    isStale: !isCurrent,
    dataThrough: fmtDataDate(f.data_through) || null,
    lastSync: fmtSyncDate(f.last_successful_sync) || null,
    syncStatus: f.sync_status || null,
    label: f.label || null,
    limitations,
    healthLabel: isCurrent ? 'Current' : 'Stale',
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

// Snapshot rows mirror the board's five groups, in the same reading order.
const SNAPSHOT_ROWS = [
  { status: 'Available', label: 'Available Tonight', key: 'available' },
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
