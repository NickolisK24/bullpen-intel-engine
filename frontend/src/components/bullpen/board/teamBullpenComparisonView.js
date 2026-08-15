import { formatConfidence, getAvailabilityBadgeView, getAvailabilityStatusLabel } from '../availabilityView'
import { fmtDataDate, fmtSyncDate } from '../../dashboard/syncStatusView'
import { getDataProvenance } from './tonightsBullpenBoardView'
import { readPublicTeamState } from '../../../adapters/publicTeamState'

// Snapshot rows shown in the side-by-side table, in the board's reading order.
// Counts are descriptive only — no scores, ranks, or grades.
const SNAPSHOT_ROWS = [
  { keys: ['available'], label: 'Available', status: 'Available' },
  { keys: ['monitor'], label: 'On Watch', status: 'Monitor' },
  { keys: ['limited'], label: 'Limited', status: 'Limited' },
  { keys: ['avoid', 'unavailable'], label: 'Unavailable', status: 'Unavailable' },
]

const LEADER_TONE = {
  A: { color: '#6ee7b7' },
  B: { color: '#93c5fd' },
  tie: { color: '#cbd5e1' },
}

function safeMetrics(metrics) {
  const m = metrics || {}
  const value = key => {
    if (m[key] == null || m[key] === '') return null
    const numeric = Number(m[key])
    return Number.isFinite(numeric) ? numeric : null
  }
  return {
    total_relievers: value('total_relievers'),
    available: value('available'),
    monitor: value('monitor'),
    limited: value('limited'),
    avoid: value('avoid'),
    unavailable: value('unavailable'),
    restricted: value('restricted'),
    pct_available: value('pct_available'),
    pct_unavailable: value('pct_unavailable'),
    // The public "Unavailable" row combines the Avoid and Unavailable groups
    // (getAvailabilityStatusLabel folds Avoid into Unavailable), so its matching
    // percentage is pct_restricted — the share of that same combined population.
    // pct_unavailable alone counts only the strict Unavailable group and would
    // read 0% next to a non-zero combined count.
    pct_restricted: value('pct_restricted'),
  }
}

// Comparison copy comes from the same guarded board context as the Team Board,
// so it is rendered as the backend published it. The substitution table that
// used to sit here is gone: public vocabulary is decided by
// backend/services/public_bullpen_copy.py (FE-001 / #591).
function displayPublicCopy(value) {
  return value
}

function sumMetrics(metrics, keys) {
  const values = keys.map(key => metrics?.[key]).filter(value => value != null)
  return values.length > 0 ? values.reduce((total, value) => total + value, 0) : null
}

function freshnessRow(freshness) {
  const f = freshness || {}
  const isCurrent = f.is_current !== false
  const provenance = getDataProvenance(f)
  return {
    isCurrent,
    isStale: !isCurrent,
    label: f.label || null,
    dataThroughRaw: f.data_through || null,
    dataThrough: fmtDataDate(f.data_through) || null,
    completedGamesLine: provenance.completedGamesLine,
    lastSync: fmtSyncDate(f.last_successful_sync) || null,
    healthLabel: provenance.label,
    provenanceDetail: provenance.detail,
    throughHint: provenance.throughHint,
    dot: provenance.tone.dot,
  }
}

export function getComparisonView(payload) {
  const comparison = payload?.comparison || null
  if (!comparison) {
    return { hasComparison: false }
  }

  const labelA = comparison.teams?.team_a?.label || 'Team A'
  const labelB = comparison.teams?.team_b?.label || 'Team B'
  const metricsA = safeMetrics(comparison.snapshot?.team_a)
  const metricsB = safeMetrics(comparison.snapshot?.team_b)

  const snapshot = SNAPSHOT_ROWS.map(row => ({
    label: getAvailabilityStatusLabel(row.label || row.status),
    badge: getAvailabilityBadgeView(row.status),
    valueA: sumMetrics(metricsA, row.keys),
    valueB: sumMetrics(metricsB, row.keys),
  }))

  const observations = (Array.isArray(comparison.observations) ? comparison.observations : []).map(o => ({
    dimension: o.dimension,
    statement: displayPublicCopy(o.statement),
    leader: o.leader,
    leaderTone: LEADER_TONE[o.leader] || LEADER_TONE.tie,
    reasons: Array.isArray(o.reasons) ? o.reasons.map(displayPublicCopy) : [],
  }))
  const confidence = comparison.confidence || 'high'

  return {
    hasComparison: true,
    labelA,
    labelB,
    metricsA,
    metricsB,
    snapshot,
    observations,
    confidence,
    confidenceLabel: formatConfidence(confidence),
    isDegraded: confidence === 'low' || confidence === 'none',
    showConfidence: !['high', ''].includes(String(confidence).toLowerCase()),
    limitations: Array.isArray(comparison.limitations) ? comparison.limitations.map(displayPublicCopy) : [],
    freshnessA: freshnessRow(comparison.freshness?.team_a),
    freshnessB: freshnessRow(comparison.freshness?.team_b),
    // Each side carries the same backend-owned Team State contract its own team
    // board carries. Nothing is combined, ranked, or inferred across the two: a
    // side whose state is fail-closed stays fail-closed on its own.
    teamStateA: readPublicTeamState(comparison.teams?.team_a?.team_state),
    teamStateB: readPublicTeamState(comparison.teams?.team_b?.team_state),
  }
}
