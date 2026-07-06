import { formatConfidence, getAvailabilityBadgeView, getAvailabilityStatusLabel } from '../availabilityView'
import { fmtDataDate, fmtSyncDate } from '../../dashboard/syncStatusView'
import { getDataProvenance } from './tonightsBullpenBoardView'

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

function displayPublicCopy(value) {
  if (typeof value !== 'string') return value
  return value
    .replace(/\bMonitor\b/g, 'On Watch')
    .replace(/\brestricted\b/g, 'limited')
    .replace(/\bRestricted\b/g, 'Limited')
    .replace(/\bAvoid\s+or\s+Unavailable\b/g, 'Unavailable')
    .replace(/\bAvoid\b/g, 'Unavailable')
    .replace(/\bconstrained\b/g, 'stretched')
    .replace(/\bConstrained\b/g, 'Stretched')
    .replace(/\bsnapshot\b/gi, 'read')
    .replace(/\brecommendation engine\b/gi, 'BaseballOS read')
}

function sumMetrics(metrics, keys) {
  return keys.reduce((total, key) => total + (Number(metrics?.[key]) || 0), 0)
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
    summary: {
      state: comparison.summary?.state || 'differ',
      statement: displayPublicCopy(comparison.summary?.statement) || null,
      reasons: Array.isArray(comparison.summary?.reasons) ? comparison.summary.reasons.map(displayPublicCopy) : [],
    },
    confidence,
    confidenceLabel: formatConfidence(confidence),
    isDegraded: confidence === 'low' || confidence === 'none',
    limitations: Array.isArray(comparison.limitations) ? comparison.limitations.map(displayPublicCopy) : [],
    freshnessA: freshnessRow(comparison.freshness?.team_a),
    freshnessB: freshnessRow(comparison.freshness?.team_b),
  }
}
