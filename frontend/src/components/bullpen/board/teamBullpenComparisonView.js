import { formatConfidence, getAvailabilityBadgeView } from '../availabilityView'
import { fmtDataDate, fmtSyncDate } from '../../dashboard/syncStatusView'
import { getDataProvenance } from './tonightsBullpenBoardView'

// Snapshot rows shown in the side-by-side table, in the board's reading order.
// Counts are descriptive only — no scores, ranks, or grades.
const SNAPSHOT_ROWS = [
  { key: 'available', label: 'Available', status: 'Available' },
  { key: 'monitor', label: 'Monitor', status: 'Monitor' },
  { key: 'limited', label: 'Limited', status: 'Limited' },
  { key: 'avoid', label: 'Avoid', status: 'Avoid' },
  { key: 'unavailable', label: 'Unavailable', status: 'Unavailable' },
]

const LEADER_TONE = {
  A: { color: '#6ee7b7' },
  B: { color: '#93c5fd' },
  tie: { color: '#cbd5e1' },
}

function safeMetrics(metrics) {
  const m = metrics || {}
  return {
    total_relievers: Number(m.total_relievers) || 0,
    available: Number(m.available) || 0,
    monitor: Number(m.monitor) || 0,
    limited: Number(m.limited) || 0,
    avoid: Number(m.avoid) || 0,
    unavailable: Number(m.unavailable) || 0,
    restricted: Number(m.restricted) || 0,
    pct_available: Number(m.pct_available) || 0,
    pct_unavailable: Number(m.pct_unavailable) || 0,
  }
}

function freshnessRow(freshness) {
  const f = freshness || {}
  const isCurrent = f.is_current !== false
  const provenance = getDataProvenance(f)
  return {
    isCurrent,
    isStale: !isCurrent,
    label: f.label || null,
    dataThrough: fmtDataDate(f.data_through) || null,
    completedGamesLine: provenance.completedGamesLine,
    lastSync: fmtSyncDate(f.last_successful_sync) || null,
    healthLabel: provenance.label,         // "Current stored data" / "Sample data"
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
    label: row.label,
    badge: getAvailabilityBadgeView(row.status),
    valueA: metricsA[row.key],
    valueB: metricsB[row.key],
  }))

  const observations = (Array.isArray(comparison.observations) ? comparison.observations : []).map(o => ({
    dimension: o.dimension,
    statement: o.statement,
    leader: o.leader,
    leaderTone: LEADER_TONE[o.leader] || LEADER_TONE.tie,
    reasons: Array.isArray(o.reasons) ? o.reasons : [],
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
    summary: {
      state: comparison.summary?.state || 'differ',
      statement: comparison.summary?.statement || null,
      reasons: Array.isArray(comparison.summary?.reasons) ? comparison.summary.reasons : [],
    },
    confidence,
    confidenceLabel: formatConfidence(confidence),
    isDegraded: confidence === 'low' || confidence === 'none',
    limitations: Array.isArray(comparison.limitations) ? comparison.limitations : [],
    freshnessA: freshnessRow(comparison.freshness?.team_a),
    freshnessB: freshnessRow(comparison.freshness?.team_b),
  }
}
