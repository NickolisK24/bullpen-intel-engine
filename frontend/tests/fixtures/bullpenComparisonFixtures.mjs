// Fixtures mirroring GET /api/bullpen/teams/compare. Builds two real board
// payloads with makeBoard and a comparison block matching the backend shape.

import { makeBoard } from './bullpenBoardFixtures.mjs'

const DIMENSIONS = [
  { key: 'available', metric: 'available', descriptor: 'classified Available', reasonLabel: 'Available' },
  { key: 'restricted', metric: 'restricted', descriptor: 'marked Avoid or Unavailable', reasonLabel: 'Avoid or Unavailable' },
  { key: 'monitor', metric: 'monitor', descriptor: 'in the Monitor group', reasonLabel: 'Monitor' },
]

function cardsFor(counts) {
  const out = {}
  let id = 0
  for (const [status, n] of Object.entries(counts)) {
    out[status] = Array.from({ length: n }, () => ({ pitcher_id: ++id + status.length * 1000, name: `${status}${id}`, availability_status: status }))
  }
  return out
}

function observation(dim, labelA, labelB, a, b) {
  let leader = 'tie'
  let statement = `Both bullpens currently have the same number of relievers ${dim.descriptor} (${a}).`
  if (a > b) {
    leader = 'A'
    statement = `${labelA} currently has more relievers ${dim.descriptor}.`
  } else if (a < b) {
    leader = 'B'
    statement = `${labelB} currently has more relievers ${dim.descriptor}.`
  }
  return {
    dimension: dim.key,
    reason_label: dim.reasonLabel,
    statement,
    leader,
    team_a_value: a,
    team_b_value: b,
    reasons: [`${labelA} ${dim.reasonLabel}: ${a}.`, `${labelB} ${dim.reasonLabel}: ${b}.`],
  }
}

export function makeComparison(a, b) {
  const boardA = makeBoard({ team: a.team, cardsByStatus: cardsFor(a.counts), freshness: a.freshness })
  const boardB = makeBoard({ team: b.team, cardsByStatus: cardsFor(b.counts), freshness: b.freshness })
  const labelA = a.team?.team_name || 'Team A'
  const labelB = b.team?.team_name || 'Team B'
  const mA = boardA.context.metrics
  const mB = boardB.context.metrics

  const observations = DIMENSIONS.map(d => observation(d, labelA, labelB, mA[d.metric], mB[d.metric]))
  const allTied = observations.every(o => o.leader === 'tie')
  const bothEmpty = mA.total_relievers === 0 && mB.total_relievers === 0

  let summary
  if (bothEmpty) summary = { state: 'no_data', statement: 'Neither bullpen has relievers in the current freshness window.', reasons: [] }
  else if (allTied) summary = { state: 'similar', statement: 'Both bullpens currently show similar availability distributions.', reasons: observations.map(o => o.statement) }
  else summary = { state: 'differ', statement: 'These bullpens currently show different availability profiles.', reasons: observations.map(o => o.statement) }

  const confA = boardA.context.confidence
  const confB = boardB.context.confidence
  const confSet = new Set([confA, confB])
  let confidence = 'high'
  if (confSet.size === 1 && confSet.has('none')) confidence = 'none'
  else if (confSet.has('none') || confSet.has('low')) confidence = 'low'

  const limitations = []
  for (const [label, board] of [[labelA, boardA], [labelB, boardB]]) {
    for (const lim of board.context.limitations || []) limitations.push(`${label}: ${lim}`)
  }

  const comparison = {
    capability: 'team_bullpen_comparison',
    generated_at: '2026-06-05T00:00:00+00:00',
    ranking_applied: false,
    selection_made: false,
    teams: {
      team_a: { label: labelA, team: boardA.team },
      team_b: { label: labelB, team: boardB.team },
    },
    snapshot: { team_a: mA, team_b: mB },
    observations,
    summary,
    confidence,
    team_confidence: { team_a: confA, team_b: confB },
    freshness: {
      team_a: { is_current: boardA.freshness.is_current, label: boardA.freshness.label, data_through: boardA.freshness.data_through, last_successful_sync: boardA.freshness.last_successful_sync },
      team_b: { is_current: boardB.freshness.is_current, label: boardB.freshness.label, data_through: boardB.freshness.data_through, last_successful_sync: boardB.freshness.last_successful_sync },
    },
    limitations,
  }

  return {
    capability: 'team_bullpen_comparison',
    generated_at: '2026-06-05T00:00:00+00:00',
    ranking_applied: false,
    selection_made: false,
    team_a: boardA,
    team_b: boardB,
    comparison,
  }
}

// Aces clearly more available; Bears more restricted.
export const differingComparison = makeComparison(
  { team: { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' }, counts: { Available: 6, Monitor: 2, Avoid: 1, Unavailable: 1 } },
  { team: { team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA' }, counts: { Available: 3, Monitor: 2, Avoid: 3, Unavailable: 2 } },
)

// Identical distributions → similar.
export const similarComparison = makeComparison(
  { team: { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' }, counts: { Available: 4, Monitor: 2, Avoid: 1, Unavailable: 1 } },
  { team: { team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA' }, counts: { Available: 4, Monitor: 2, Avoid: 1, Unavailable: 1 } },
)

// Bears bullpen is stale → degraded confidence.
export const staleComparison = makeComparison(
  { team: { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' }, counts: { Available: 5, Monitor: 1 } },
  {
    team: { team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA' },
    counts: { Monitor: 1 },
    freshness: { data_through: '2026-04-01', is_current: false, label: 'Historical baseball data through 2026-04-01.', last_successful_sync: null, limitations: ['Latest game date is outside the 14-day freshness window.'] },
  },
)
