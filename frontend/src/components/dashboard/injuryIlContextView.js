const asNumber = (value) => {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

const asOptionalNumber = (value) => {
  if (value == null) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
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
  const readiness = source.roster_readiness || source.rosterReadiness || payload?.roster_readiness || payload?.rosterReadiness || null
  const countsWithheld = (
    source.counts_withheld === true
    || source.countsWithheld === true
    || readiness?.counts_withheld === true
    || readiness?.claims_available === false
    || !readiness
  )

  const league = {
    populationScope: source.league.population_scope || 'dashboard_bullpen_population',
    injuredListCount: countsWithheld ? null : asOptionalNumber(source.league.injured_list_count),
    inactiveCount: countsWithheld ? null : asOptionalNumber(source.league.inactive_count),
    teamsWithMultipleUnavailable: countsWithheld ? null : asOptionalNumber(source.league.teams_with_multiple_unavailable),
    bullpenPopulationCount: countsWithheld ? null : asOptionalNumber(
      source.league.bullpen_population_count ?? source.league.tracked_pitchers_count
    ),
    trackedPitchersCount: countsWithheld ? null : asOptionalNumber(source.league.tracked_pitchers_count),
  }

  return {
    capability: source.capability || 'injury_il_context_v1',
    rankingApplied: source.ranking_applied === true,
    predictionApplied: source.prediction_applied === true,
    countsWithheld,
    rosterReadiness: readiness,
    league,
    followedTeam: normalizeFollowedTeam(source.followed_team),
    limitations: [
      ...asArray(source.limitations),
      ...asArray(readiness?.reader_limitations || readiness?.readerLimitations),
    ].filter(Boolean),
  }
}

export function getInjuryIlContextSummary(view) {
  if (view?.countsWithheld) {
    return 'Current active-roster coverage could not be verified, so dashboard roster counts are withheld.'
  }
  const league = view?.league || {}
  const unavailable = (
    asNumber(league.injuredListCount)
    + asNumber(league.inactiveCount)
  )
  if (unavailable <= 0) {
    return 'No bullpen arms in the dashboard roster-status context are marked IL or inactive.'
  }
  const injured = asNumber(league.injuredListCount)
  const inactive = asNumber(league.inactiveCount)
  return `${injured} bullpen arms are currently on the injured list. ${inactive} bullpen arms are currently inactive.`
}
