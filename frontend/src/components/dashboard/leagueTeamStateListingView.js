import { readPublicTeamState } from '../../adapters/publicTeamState'
import { buildTeamBoardHref } from '../../utils/evidenceLinks'

export const LEAGUE_TEAM_STATE_CAPABILITY = 'league_team_state_listing_v1'
export const LEAGUE_TEAM_STATE_GROUPS = Object.freeze([
  { key: 'fresh', label: 'Fresh' },
  { key: 'stretched', label: 'Stretched' },
  { key: 'vulnerable', label: 'Vulnerable' },
])

const INVALID_VIEW = Object.freeze({
  valid: false,
  unavailable: true,
  globalUnavailable: false,
  freshness: null,
  groups: [],
  exceptions: [],
  expectedTeamCount: null,
  teamCount: null,
  representedTeamCount: null,
  withheldTeamCount: null,
})

function integerOrNull(value) {
  return Number.isInteger(value) && value >= 0 ? value : null
}

function textOrNull(value) {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed || null
}

function compareTeams(a, b) {
  const byName = a.teamName.localeCompare(b.teamName, undefined, { sensitivity: 'base' })
  return byName || a.teamId - b.teamId
}

function normalizeRow(row) {
  if (!row || typeof row !== 'object') return null
  const teamId = integerOrNull(row.team_id)
  const teamName = textOrNull(row.team_name)
  const teamAbbreviation = textOrNull(row.team_abbreviation)
  const rawState = row.team_state
  if (!teamId || !teamName || !teamAbbreviation || !rawState || typeof rawState !== 'object') return null
  if (rawState.available !== true && rawState.available !== false) return null

  const teamState = readPublicTeamState(rawState)
  if (rawState.available === true && !teamState.available) return null
  if (rawState.available === false) {
    if (teamState.available) return null
    if (rawState.public_state != null || rawState.public_label != null) return null
  }

  return {
    teamId,
    teamName,
    teamAbbreviation,
    teamState,
    teamHref: buildTeamBoardHref(row, { source: 'dashboard' }),
  }
}

// This is presentation-contract validation, not a second governance engine. It
// checks that the backend-owned denominator and already-published states are
// internally coherent, then fails closed without repairing any value.
export function getLeagueTeamStateListingView(payload) {
  if (!payload || typeof payload !== 'object') return { ...INVALID_VIEW }
  if (payload.capability !== LEAGUE_TEAM_STATE_CAPABILITY) return { ...INVALID_VIEW }
  if (payload.ranking_applied !== false || payload.selection_made !== false || payload.prediction_applied !== false) {
    return { ...INVALID_VIEW }
  }
  if (!Array.isArray(payload.teams)) return { ...INVALID_VIEW }

  const expectedTeamCount = integerOrNull(payload.expected_team_count)
  const teamCount = integerOrNull(payload.team_count)
  const representedTeamCount = integerOrNull(payload.represented_team_count)
  const withheldTeamCount = integerOrNull(payload.withheld_team_count)
  if (
    expectedTeamCount !== 30
    || teamCount !== expectedTeamCount
    || payload.teams.length !== teamCount
    || representedTeamCount == null
    || withheldTeamCount == null
    || representedTeamCount + withheldTeamCount !== expectedTeamCount
  ) return { ...INVALID_VIEW }

  const rows = payload.teams.map(normalizeRow)
  if (rows.some(row => row == null)) return { ...INVALID_VIEW }
  if (new Set(rows.map(row => row.teamId)).size !== rows.length) return { ...INVALID_VIEW }

  const represented = rows.filter(row => row.teamState.available)
  const exceptions = rows.filter(row => !row.teamState.available)
  if (represented.length !== representedTeamCount || exceptions.length !== withheldTeamCount) {
    return { ...INVALID_VIEW }
  }

  const globalUnavailable = payload.status === 'snapshot_unavailable'
  if (globalUnavailable && (representedTeamCount !== 0 || withheldTeamCount !== expectedTeamCount)) {
    return { ...INVALID_VIEW }
  }
  if (!globalUnavailable && payload.status !== 'ok') return { ...INVALID_VIEW }

  // Group order is governed vocabulary order, never rank order. Within every
  // group the only presentation ordering is team_name then team_id.
  const groups = LEAGUE_TEAM_STATE_GROUPS.map(group => ({
    ...group,
    teams: represented
      .filter(row => row.teamState.publicState === group.key)
      .sort(compareTeams),
  }))
  if (groups.reduce((count, group) => count + group.teams.length, 0) !== representedTeamCount) {
    return { ...INVALID_VIEW }
  }

  return {
    valid: true,
    unavailable: globalUnavailable,
    globalUnavailable,
    freshness: payload.freshness && typeof payload.freshness === 'object' ? payload.freshness : null,
    groups,
    exceptions: exceptions.sort(compareTeams),
    expectedTeamCount,
    teamCount,
    representedTeamCount,
    withheldTeamCount,
  }
}
