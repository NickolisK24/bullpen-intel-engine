export const FOLLOWED_TEAM_STORAGE_KEY = 'baseballos.followedTeam'

function getBrowserStorage() {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage || null
  } catch {
    return null
  }
}

function cleanText(value) {
  const text = value == null ? '' : String(value).trim()
  return text || null
}

function cleanTeamId(value) {
  if (value == null || value === '') return null
  const id = Number(value)
  return Number.isInteger(id) ? id : null
}

export function normalizeFollowedTeam(team) {
  if (!team || typeof team !== 'object') return null

  const teamId = cleanTeamId(team.team_id ?? team.teamId)
  const teamAbbreviation = cleanText(team.team_abbreviation ?? team.teamAbbreviation)
  const teamName = cleanText(team.team_name ?? team.teamName)

  if (teamId == null && !teamAbbreviation && !teamName) return null

  return {
    team_id: teamId,
    team_abbreviation: teamAbbreviation,
    team_name: teamName,
  }
}

export function readFollowedTeamPreference(storage = getBrowserStorage()) {
  if (!storage) return null
  try {
    const raw = storage.getItem(FOLLOWED_TEAM_STORAGE_KEY)
    if (!raw) return null
    return normalizeFollowedTeam(JSON.parse(raw))
  } catch {
    return null
  }
}

export function saveFollowedTeamPreference(
  team,
  storage = getBrowserStorage(),
  now = () => new Date().toISOString(),
) {
  const normalized = normalizeFollowedTeam(team)
  if (!normalized) return null

  if (!storage) return normalized
  try {
    storage.setItem(FOLLOWED_TEAM_STORAGE_KEY, JSON.stringify({
      ...normalized,
      saved_at: now(),
    }))
  } catch {
    // The caller can still use the normalized preference in memory.
  }
  return normalized
}

export function clearFollowedTeamPreference(storage = getBrowserStorage()) {
  if (!storage) return false
  try {
    storage.removeItem(FOLLOWED_TEAM_STORAGE_KEY)
    return true
  } catch {
    return false
  }
}

export function resolveFollowedTeam(preference, teams = []) {
  const normalized = normalizeFollowedTeam(preference)
  if (!normalized) return null
  if (!Array.isArray(teams) || teams.length === 0) return normalized

  const byId = normalized.team_id == null
    ? null
    : teams.find(team => cleanTeamId(team?.team_id) === normalized.team_id)
  if (byId) return normalizeFollowedTeam(byId)

  const abbr = normalized.team_abbreviation?.toLowerCase()
  const byAbbr = abbr
    ? teams.find(team => cleanText(team?.team_abbreviation)?.toLowerCase() === abbr)
    : null
  if (byAbbr) return normalizeFollowedTeam(byAbbr)

  const name = normalized.team_name?.toLowerCase()
  const byName = name
    ? teams.find(team => cleanText(team?.team_name)?.toLowerCase() === name)
    : null
  return byName ? normalizeFollowedTeam(byName) : normalized
}

export function buildFollowedTeamHref(team) {
  const normalized = normalizeFollowedTeam(team)
  if (!normalized) return '/bullpen?view=board'

  const teamParam = normalized.team_abbreviation || (
    normalized.team_id != null ? String(normalized.team_id) : ''
  )
  if (!teamParam) return '/bullpen?view=board'

  const query = new URLSearchParams({
    view: 'board',
    team: teamParam,
    source: 'follow-my-team',
  })
  return `/bullpen?${query.toString()}`
}
