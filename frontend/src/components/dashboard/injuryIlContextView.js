const asNumber = (value) => {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

const asArray = (value) => Array.isArray(value) ? value : []

const normalizeUnavailablePitcher = (pitcher) => {
  if (!pitcher || typeof pitcher !== 'object') return null
  const name = pitcher.name || pitcher.full_name || pitcher.player_name
  if (!name) return null
  return {
    playerId: pitcher.player_id || pitcher.mlb_id || pitcher.id || null,
    name,
    status: pitcher.status || null,
    statusLabel: pitcher.status_label || pitcher.label || pitcher.status || 'Roster status',
    statusGroup: pitcher.status_group || 'unknown',
  }
}

const normalizeFollowedTeam = (team) => {
  if (!team || typeof team !== 'object') return null
  const unavailablePitchers = asArray(team.unavailable_pitchers)
    .map(normalizeUnavailablePitcher)
    .filter(Boolean)
  return {
    teamId: team.team_id || null,
    teamName: team.team_name || team.name || 'Followed Team',
    injuredListCount: asNumber(team.injured_list_count),
    inactiveCount: asNumber(team.inactive_count),
    unavailablePitchers,
  }
}

export function normalizeInjuryIlContext(payload) {
  const source = payload?.injury_il_context || payload?.injuryIlContext || payload
  if (!source || typeof source !== 'object') return null
  if (!source.league || typeof source.league !== 'object') return null

  const league = {
    injuredListCount: asNumber(source.league.injured_list_count),
    inactiveCount: asNumber(source.league.inactive_count),
    teamsWithMultipleUnavailable: asNumber(source.league.teams_with_multiple_unavailable),
    trackedPitchersCount: asNumber(source.league.tracked_pitchers_count),
  }

  return {
    capability: source.capability || 'injury_il_context_v1',
    rankingApplied: source.ranking_applied === true,
    predictionApplied: source.prediction_applied === true,
    league,
    followedTeam: normalizeFollowedTeam(source.followed_team),
    limitations: asArray(source.limitations).filter(Boolean),
  }
}

export function getInjuryIlContextSummary(view) {
  const league = view?.league || {}
  const unavailable = (
    asNumber(league.injuredListCount)
    + asNumber(league.inactiveCount)
  )
  if (unavailable <= 0) {
    return 'No tracked bullpen arms are marked IL or inactive in this roster-status context.'
  }
  return `${unavailable} tracked bullpen arms are marked IL or inactive across the current roster-status context.`
}
