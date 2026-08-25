import { readPublicTeamState } from '../../../adapters/publicTeamState'

const DOMAIN_DEFINITIONS = [
  { key: 'rest', label: 'Rest', rows: [['rested_options', 'Rested Options'], ['worked_yesterday', 'Worked Yesterday'], ['back_to_back', 'Back-to-Back']] },
  { key: 'workload', label: 'Recent Workload — 7 Days', rows: [['relief_appearances', 'Relief Appearances'], ['contributing_relievers', 'Contributing Relievers'], ['pitches', 'Pitches']] },
  { key: 'rotation', label: 'Rotation Transfer', rows: [['short_starts', 'Short Starts'], ['bullpen_innings', 'Bullpen Innings']] },
  { key: 'availability', label: 'Availability', rows: [['available', 'Available'], ['on_watch', 'On Watch'], ['limited', 'Limited'], ['unavailable', 'Unavailable']] },
]

const displayValue = value => value == null ? '—' : value

function domainView(domain, definition) {
  const value = domain || {}
  return {
    key: definition.key,
    label: definition.label,
    status: value.status || 'withheld',
    message: value.message || `${definition.label} comparison is unavailable.`,
    limitations: Array.isArray(value.limitations) ? value.limitations : [],
    rows: definition.rows.map(([key, label]) => ({
      key,
      label,
      valueA: displayValue(value.team_a?.[key]),
      valueB: displayValue(value.team_b?.[key]),
    })),
  }
}

export function getComparisonView(payload) {
  const comparison = payload?.comparison
  if (!comparison) return { hasComparison: false }

  const teamA = comparison.teams?.team_a || {}
  const teamB = comparison.teams?.team_b || {}
  const stateDomain = comparison.domains?.team_state || {}
  const availability = comparison.domains?.availability || {}
  const snapshot = [
    ['Available', 'available'],
    ['On Watch', 'on_watch'],
    ['Limited', 'limited'],
    ['Unavailable', 'unavailable'],
  ].map(([label, key]) => ({
    label,
    valueA: availability.team_a?.[key] ?? null,
    valueB: availability.team_b?.[key] ?? null,
  }))
  const isDegraded = comparison.status !== 'available'
  const freshness = {
    dataThroughRaw: comparison.represented_date || null,
    dataThrough: comparison.represented_date || null,
    isCurrent: !isDegraded,
    isStale: isDegraded,
  }
  return {
    hasComparison: true,
    status: comparison.status,
    representedDate: comparison.represented_date || null,
    teamA,
    teamB,
    labelA: teamA.team_name || teamA.team_abbreviation || 'Team A',
    labelB: teamB.team_name || teamB.team_abbreviation || 'Team B',
    teamStateStatus: stateDomain.status || 'withheld',
    teamStateMessage: stateDomain.message || 'Team State comparison is unavailable.',
    teamStateA: readPublicTeamState(stateDomain.team_a),
    teamStateB: readPublicTeamState(stateDomain.team_b),
    domains: DOMAIN_DEFINITIONS.map(definition => domainView(comparison.domains?.[definition.key], definition)),
    limitations: Array.isArray(comparison.limitations) ? comparison.limitations : [],
    // Retained for the existing immutable comparison share-artifact builder.
    // These rows are a direct projection of the backend-authored public
    // availability carrier; they do not reconstruct baseball meaning.
    snapshot,
    observations: [],
    isDegraded,
    freshnessA: freshness,
    freshnessB: freshness,
  }
}
