import {
  PREFERRED_TEAM_STORAGE_KEY,
  buildPreferredTeamHref,
  clearPreferredTeamPreference,
  normalizePreferredTeam,
  readPreferredTeamPreference,
  resolvePreferredTeam,
  savePreferredTeamPreference,
} from './preferredTeam'

export const FOLLOWED_TEAM_STORAGE_KEY = PREFERRED_TEAM_STORAGE_KEY

export const normalizeFollowedTeam = normalizePreferredTeam
export const readFollowedTeamPreference = readPreferredTeamPreference
export const saveFollowedTeamPreference = savePreferredTeamPreference
export const clearFollowedTeamPreference = clearPreferredTeamPreference
export const resolveFollowedTeam = resolvePreferredTeam

export function buildFollowedTeamHref(team) {
  return buildPreferredTeamHref(team, 'follow-my-team')
}
