import { usePreferredTeamPreference } from './usePreferredTeamPreference'

export function useFollowedTeamPreference(teams = []) {
  const {
    preferredTeam,
    setPreferredTeam,
    clearPreferredTeam,
    loading,
    authLoading,
    authenticated,
    authError,
    serverSyncLoading,
    serverSyncError,
  } = usePreferredTeamPreference(teams)

  return {
    followedTeam: preferredTeam,
    setFollowedTeam: setPreferredTeam,
    clearFollowedTeam: clearPreferredTeam,
    loading,
    authLoading,
    authenticated,
    authError,
    serverSyncLoading,
    serverSyncError,
  }
}
