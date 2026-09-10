export const TEAM_SHARE_ORIGIN = 'https://baseballos.app'

export function normalizeTeamShareAbbreviation(team) {
  const value = typeof team === 'string'
    ? team
    : team?.team_abbreviation
      ?? team?.teamAbbreviation
      ?? team?.abbr
      ?? team?.team?.team_abbreviation
      ?? team?.team?.teamAbbreviation
      ?? team?.team?.abbr
  const text = typeof value === 'string' ? value.trim().toUpperCase() : ''
  return text ? text.replace(/[^A-Z0-9-]/g, '') : ''
}

export function buildTeamSharePath(team) {
  const abbr = normalizeTeamShareAbbreviation(team)
  return abbr ? `/team/${encodeURIComponent(abbr)}` : ''
}

export function buildTeamShareUrl(team, origin = TEAM_SHARE_ORIGIN) {
  const path = buildTeamSharePath(team)
  if (!path) return ''
  return `${String(origin || TEAM_SHARE_ORIGIN).replace(/\/+$/, '')}${path}`
}
