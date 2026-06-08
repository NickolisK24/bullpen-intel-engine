import { useCallback, useState } from 'react'
import {
  clearFollowedTeamPreference,
  readFollowedTeamPreference,
  saveFollowedTeamPreference,
} from '../utils/followedTeamPreference'

export function useFollowedTeamPreference() {
  const [followedTeam, setFollowedTeamState] = useState(() => readFollowedTeamPreference())

  const setFollowedTeam = useCallback((team) => {
    const saved = saveFollowedTeamPreference(team)
    setFollowedTeamState(saved)
    return saved
  }, [])

  const clearFollowedTeam = useCallback(() => {
    clearFollowedTeamPreference()
    setFollowedTeamState(null)
  }, [])

  return {
    followedTeam,
    setFollowedTeam,
    clearFollowedTeam,
  }
}
