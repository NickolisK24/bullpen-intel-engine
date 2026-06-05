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
