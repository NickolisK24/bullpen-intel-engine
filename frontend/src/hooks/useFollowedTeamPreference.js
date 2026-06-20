import { usePreferredTeamPreference } from './usePreferredTeamPreference'

export function useFollowedTeamPreference(teams = []) {
  const {
    preferredTeam,
    setPreferredTeam,
    clearPreferredTeam,
  } = usePreferredTeamPreference(teams)

  return {
    followedTeam: preferredTeam,
    setFollowedTeam: setPreferredTeam,
    clearFollowedTeam: clearPreferredTeam,
  }
}
