const DATA_THROUGH = '2026-06-04'

const teamState = (label, code, dataThrough = DATA_THROUGH) => ({
  contract: 'team_state_public_v1', available: true, public_state: code,
  public_label: label, summary: `${label} summary.`, outcome: 'available',
  unavailable_message: null, reason_code: null, data_through: dataThrough,
})
const count = (counts, ...keys) => keys.reduce((total, key) => total + (counts?.[key] || 0), 0)

function buildComparison(a = {}, b = {}, overrides = {}) {
  const teamA = a.team || { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' }
  const teamB = b.team || { team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA' }
  const countsA = a.counts || { Available: 6, Monitor: 2, Avoid: 1, Unavailable: 1 }
  const countsB = b.counts || { Available: 3, Monitor: 2, Avoid: 3, Unavailable: 2 }
  const dateA = a.freshness?.data_through || DATA_THROUGH
  const dateB = b.freshness?.data_through || DATA_THROUGH
  const sharedDate = dateA === dateB ? dateA : null
  const domains = {
    team_state: { status: sharedDate ? 'available' : 'withheld', reason_code: null, message: sharedDate ? null : 'Team State comparison is unavailable for this publication.', team_a: sharedDate ? teamState('Fresh', 'fresh', dateA) : null, team_b: sharedDate ? teamState('Stretched', 'stretched', dateB) : null },
    rest: { status: 'available', reason_code: null, message: null, team_a: { rested_options: 5, worked_yesterday: 2, back_to_back: 1 }, team_b: { rested_options: 2, worked_yesterday: 4, back_to_back: 2 } },
    workload: { status: 'available', reason_code: null, message: null, team_a: { window_days: 7, relief_appearances: 9, contributing_relievers: 6, pitches: 121 }, team_b: { window_days: 7, relief_appearances: 12, contributing_relievers: 7, pitches: 164 } },
    rotation: { status: 'available', reason_code: null, message: null, team_a: { window_days: 7, short_starts: 1, bullpen_innings: 11.1 }, team_b: { window_days: 7, short_starts: 3, bullpen_innings: 16.2 } },
    availability: {
      status: 'available', reason_code: null, message: null,
      team_a: { available: count(countsA, 'Available'), on_watch: count(countsA, 'Monitor'), limited: count(countsA, 'Limited'), unavailable: count(countsA, 'Avoid', 'Unavailable') },
      team_b: { available: count(countsB, 'Available'), on_watch: count(countsB, 'Monitor'), limited: count(countsB, 'Limited'), unavailable: count(countsB, 'Avoid', 'Unavailable') },
    },
  }
  const comparison = {
    capability: 'current_bullpen_comparison_v1', contract: 'current_bullpen_comparison_carrier_v1',
    status: sharedDate ? 'available' : 'partial', represented_date: sharedDate || dateA,
    ranking_applied: false, selection_made: false, prediction_applied: false,
    teams: {
      team_a: { ...teamA, team_board_href: `/bullpen?view=board&team=${teamA.team_abbreviation}&source=comparison` },
      team_b: { ...teamB, team_board_href: `/bullpen?view=board&team=${teamB.team_abbreviation}&source=comparison` },
    },
    domains,
    limitations: [],
    ...overrides,
  }
  return { capability: 'current_bullpen_comparison_v1', status: comparison.status, comparison }
}

export function makeComparison(a = {}, b) {
  if (b !== undefined || a?.team || a?.counts || a?.freshness) return buildComparison(a, b || {})
  return buildComparison({}, {}, a)
}

export const differingComparison = buildComparison()
export const similarComparison = buildComparison(
  { counts: { Available: 4, Monitor: 2, Limited: 1, Avoid: 1 } },
  { counts: { Available: 4, Monitor: 2, Limited: 1, Avoid: 1 } },
)
const staleBase = buildComparison(
  { freshness: { data_through: DATA_THROUGH } },
  { freshness: { data_through: '2026-04-01' } },
)
export const staleComparison = {
  ...staleBase,
  comparison: {
    ...staleBase.comparison,
    domains: {
      ...staleBase.comparison.domains,
      rotation: { status: 'withheld', reason_code: 'comparison_authority_mismatch', message: 'Rotation transfer comparison is unavailable for this publication.', team_a: null, team_b: null },
    },
  },
}
