import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  PREFERRED_TEAM_CHANGED_EVENT,
  clearPreferredTeamPreference,
  dismissPreferredTeamPrompt,
  readPreferredTeamState,
  resolvePreferredTeam,
  savePreferredTeamPreference,
} from '../utils/preferredTeam'

export function usePreferredTeamPreference(teams = []) {
  const [preferenceState, setPreferenceState] = useState(() => readPreferredTeamState())

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    const refresh = () => setPreferenceState(readPreferredTeamState())
    window.addEventListener(PREFERRED_TEAM_CHANGED_EVENT, refresh)
    window.addEventListener('storage', refresh)
    return () => {
      window.removeEventListener(PREFERRED_TEAM_CHANGED_EVENT, refresh)
      window.removeEventListener('storage', refresh)
    }
  }, [])

  const preferredTeam = useMemo(
    () => resolvePreferredTeam(preferenceState.team, teams),
    [preferenceState.team, teams],
  )

  const setPreferredTeam = useCallback((team) => {
    const saved = savePreferredTeamPreference(team)
    setPreferenceState(readPreferredTeamState())
    return saved
  }, [])

  const clearPreferredTeam = useCallback(() => {
    clearPreferredTeamPreference()
    setPreferenceState(readPreferredTeamState())
  }, [])

  const dismissPrompt = useCallback(() => {
    dismissPreferredTeamPrompt()
    setPreferenceState(readPreferredTeamState())
  }, [])

  return {
    preferredTeam,
    rawPreferredTeam: preferenceState.team,
    promptDismissed: preferenceState.promptDismissed,
    setPreferredTeam,
    clearPreferredTeam,
    dismissPrompt,
  }
}
