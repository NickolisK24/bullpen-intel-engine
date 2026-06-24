import {
  deleteFollowedTeam,
  followTeam,
  setPrimaryTeam,
} from './api'
import {
  normalizePreferredTeam,
  preferredTeamSelectionValue,
  resolvePreferredTeam,
} from './preferredTeam'

const claimRequests = new Map()

function cleanTeamId(value) {
  if (value == null || value === '') return null
  const id = Number(value)
  return Number.isInteger(id) ? id : null
}

export function normalizeFollowedTeamsResponse(response = {}) {
  const teams = Array.isArray(response?.teams)
    ? response.teams
      .map(team => ({
        team_id: cleanTeamId(team?.team_id ?? team?.teamId),
        is_primary: team?.is_primary === true || team?.isPrimary === true,
      }))
      .filter(team => team.team_id != null)
    : []
  const primaryTeamId = cleanTeamId(response?.primary_team_id ?? response?.primaryTeamId)
    ?? teams.find(team => team.is_primary)?.team_id
    ?? null

  return {
    teams,
    primary_team_id: primaryTeamId,
  }
}

export function resolveServerPreferredTeam(serverResponse = {}, teamDirectory = []) {
  const normalized = normalizeFollowedTeamsResponse(serverResponse)
  if (normalized.primary_team_id == null) return null
  return resolvePreferredTeam({ team_id: normalized.primary_team_id }, teamDirectory)
}

export function resolvePreferredTeamForAuthState({
  authenticated = false,
  serverResponse = {},
  serverError = null,
  localPreference = null,
  teamDirectory = [],
} = {}) {
  const localTeam = resolvePreferredTeam(localPreference, teamDirectory)
  if (!authenticated || serverError) return localTeam
  const serverTeam = resolveServerPreferredTeam(serverResponse, teamDirectory)
  if (
    serverTeam?.team_id != null
    && localTeam?.team_id === serverTeam.team_id
  ) {
    return {
      ...serverTeam,
      team_abbreviation: serverTeam.team_abbreviation || localTeam.team_abbreviation,
      team_name: serverTeam.team_name || localTeam.team_name,
    }
  }
  return serverTeam || localTeam
}

export function shouldClaimLocalPreferredTeam(serverResponse = {}, localPreference = null, teamDirectory = []) {
  const serverState = normalizeFollowedTeamsResponse(serverResponse)
  if (serverState.teams.length > 0) return null

  const localTeam = resolvePreferredTeam(localPreference, teamDirectory)
  const teamId = cleanTeamId(localTeam?.team_id)
  return teamId == null ? null : { team_id: teamId }
}

export async function setServerPreferredTeam(team, clients = {}) {
  const normalized = normalizePreferredTeam(team)
  const teamId = cleanTeamId(normalized?.team_id)
  if (teamId == null) return null

  const follow = clients.followTeam || followTeam
  const setPrimary = clients.setPrimaryTeam || setPrimaryTeam
  await follow(teamId)
  return setPrimary(teamId)
}

export async function clearServerPreferredTeam(team, clients = {}) {
  const normalized = normalizePreferredTeam(team)
  const teamId = cleanTeamId(normalized?.team_id)
  if (teamId == null) return null

  const remove = clients.deleteFollowedTeam || deleteFollowedTeam
  return remove(teamId)
}

export async function claimLocalPreferredTeamOnSignIn({
  serverResponse = {},
  localPreference = null,
  teamDirectory = [],
  claimKey = '',
  clients = {},
} = {}) {
  const claim = shouldClaimLocalPreferredTeam(serverResponse, localPreference, teamDirectory)
  if (!claim) return normalizeFollowedTeamsResponse(serverResponse)

  const key = claimKey || preferredTeamSelectionValue(claim)
  if (!claimRequests.has(key)) {
    claimRequests.set(
      key,
      setServerPreferredTeam(claim, clients).finally(() => {
        claimRequests.delete(key)
      }),
    )
  }

  const response = await claimRequests.get(key)
  return normalizeFollowedTeamsResponse(response)
}
