import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AUTH_TOKEN_CHANGED_EVENT,
  clearAuthToken,
  getCurrentUser,
  getFollowedTeams,
  isAuthTokenStorageEvent,
  readAuthToken,
} from '../utils/api'
import { authStateForTokenCheck } from './useAuthState'
import {
  PREFERRED_TEAM_CHANGED_EVENT,
  clearPreferredTeamPreference,
  dismissPreferredTeamPrompt,
  isPreferredTeamStorageEvent,
  readPreferredTeamState,
  resolvePreferredTeam,
  savePreferredTeamPreference,
} from '../utils/preferredTeam'
import {
  claimLocalPreferredTeamOnSignIn,
  clearServerPreferredTeam,
  normalizeFollowedTeamsResponse,
  resolvePreferredTeamForAuthState,
  resolveServerPreferredTeam,
  setServerPreferredTeam,
} from '../utils/preferredTeamServerSync'

export function serverStateForPreferredTeamPreference(previous = {}, preferenceState = {}) {
  const preferredTeamId = preferenceState.team?.team_id ?? null
  if (preferredTeamId == null) return previous

  const previousTeams = Array.isArray(previous.teams) ? previous.teams : []
  const hasPrimary = previousTeams.some(team => team?.team_id === preferredTeamId)
  const nextTeams = [
    { team_id: preferredTeamId, is_primary: true },
    ...previousTeams
      .filter(team => team?.team_id !== preferredTeamId)
      .map(team => ({ ...team, is_primary: false })),
  ]

  if (
    previous.primary_team_id === preferredTeamId
    && hasPrimary
    && previousTeams.every((team, index) => team.is_primary === nextTeams[index]?.is_primary)
  ) {
    return previous
  }

  return {
    ...previous,
    teams: nextTeams,
    primary_team_id: preferredTeamId,
  }
}

export function usePreferredTeamPreference(teams = []) {
  const [preferenceState, setPreferenceState] = useState(() => readPreferredTeamState())
  const teamDirectoryKey = useMemo(() => (
    (Array.isArray(teams) ? teams : [])
      .map(team => [
        team?.team_id ?? team?.teamId ?? '',
        team?.team_abbreviation ?? team?.teamAbbreviation ?? team?.teamAbbr ?? '',
        team?.team_name ?? team?.teamName ?? '',
      ].join(':'))
      .join('|')
  ), [teams])
  const [authRefreshKey, setAuthRefreshKey] = useState(0)
  const [authState, setAuthState] = useState(() => ({
    loading: readAuthToken() != null,
    authenticated: false,
    user: null,
    error: null,
  }))
  const [serverState, setServerState] = useState(() => ({
    loading: false,
    teams: [],
    primary_team_id: null,
    error: null,
  }))

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    const refresh = () => {
      const nextPreferenceState = readPreferredTeamState()
      setPreferenceState(nextPreferenceState)
      setServerState(previous => serverStateForPreferredTeamPreference(previous, nextPreferenceState))
    }
    const refreshForPreferredTeamStorage = (event) => {
      if (isPreferredTeamStorageEvent(event)) refresh()
    }
    window.addEventListener(PREFERRED_TEAM_CHANGED_EVENT, refresh)
    window.addEventListener('storage', refreshForPreferredTeamStorage)
    return () => {
      window.removeEventListener(PREFERRED_TEAM_CHANGED_EVENT, refresh)
      window.removeEventListener('storage', refreshForPreferredTeamStorage)
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    const refreshAuth = () => setAuthRefreshKey(value => value + 1)
    const refreshAuthForStorage = (event) => {
      if (isAuthTokenStorageEvent(event)) refreshAuth()
    }
    window.addEventListener(AUTH_TOKEN_CHANGED_EVENT, refreshAuth)
    window.addEventListener('storage', refreshAuthForStorage)
    return () => {
      window.removeEventListener(AUTH_TOKEN_CHANGED_EVENT, refreshAuth)
      window.removeEventListener('storage', refreshAuthForStorage)
    }
  }, [])

  useEffect(() => {
    let active = true
    const token = readAuthToken()

    if (!token) {
      setAuthState({
        loading: false,
        authenticated: false,
        user: null,
        error: null,
      })
      setServerState({
        loading: false,
        teams: [],
        primary_team_id: null,
        error: null,
      })
      return () => {
        active = false
      }
    }

    setAuthState(previous => authStateForTokenCheck(previous))

    getCurrentUser()
      .then((identity) => {
        if (!active) return
        if (identity?.authenticated === true && identity.user) {
          setAuthState({
            loading: false,
            authenticated: true,
            user: identity.user,
            error: null,
          })
          return
        }

        clearAuthToken()
        setAuthState({
          loading: false,
          authenticated: false,
          user: null,
          error: null,
        })
      })
      .catch((error) => {
        if (!active) return
        clearAuthToken()
        setAuthState({
          loading: false,
          authenticated: false,
          user: null,
          error,
        })
      })

    return () => {
      active = false
    }
  }, [authRefreshKey])

  useEffect(() => {
    let active = true

    if (!authState.authenticated) {
      setServerState({
        loading: false,
        teams: [],
        primary_team_id: null,
        error: null,
      })
      return () => {
        active = false
      }
    }

    setServerState(previous => ({
      ...previous,
      loading: true,
      error: null,
    }))

    getFollowedTeams()
      .then(async (response) => {
        let nextState = normalizeFollowedTeamsResponse(response)
        const localPreference = readPreferredTeamState().team
        const localClaim = resolvePreferredTeam(localPreference, teams)
        nextState = await claimLocalPreferredTeamOnSignIn({
          serverResponse: nextState,
          localPreference,
          teamDirectory: teams,
          claimKey: `${authState.user?.id || 'user'}:${localClaim?.team_id || 'none'}`,
        })

        if (!active) return
        setServerState({
          ...nextState,
          loading: false,
          error: null,
        })

        const serverPreferredTeam = resolveServerPreferredTeam(nextState, teams)
        if (serverPreferredTeam) {
          savePreferredTeamPreference(serverPreferredTeam)
        }
      })
      .catch((error) => {
        if (!active) return
        if (error?.status === 401) {
          clearAuthToken()
        }
        setServerState(previous => ({
          ...previous,
          loading: false,
          error,
        }))
      })

    return () => {
      active = false
    }
  }, [authState.authenticated, authState.user?.id, teamDirectoryKey])

  const preferredTeam = useMemo(
    () => resolvePreferredTeamForAuthState({
      authenticated: authState.authenticated,
      serverResponse: serverState,
      serverError: serverState.error,
      localPreference: preferenceState.team,
      teamDirectory: teams,
    }),
    [authState.authenticated, preferenceState.team, serverState, teams],
  )

  const setPreferredTeam = useCallback((team) => {
    const saved = savePreferredTeamPreference(team)
    setPreferenceState(readPreferredTeamState())
    if (authState.authenticated && saved?.team_id != null) {
      setServerState(previous => ({
        ...previous,
        loading: true,
        error: null,
      }))
      setServerPreferredTeam(saved)
        .then((response) => {
          const nextState = normalizeFollowedTeamsResponse(response)
          setServerState({
            ...nextState,
            loading: false,
            error: null,
          })
          const serverPreferredTeam = resolveServerPreferredTeam(nextState, teams)
          if (serverPreferredTeam) {
            savePreferredTeamPreference(serverPreferredTeam)
          }
        })
        .catch((error) => {
          if (error?.status === 401) clearAuthToken()
          setServerState(previous => ({
            ...previous,
            loading: false,
            error,
          }))
        })
    }
    return saved
  }, [authState.authenticated, teams])

  const clearPreferredTeam = useCallback(() => {
    const currentServerPreferredTeam = resolveServerPreferredTeam(serverState, teams)
    const currentTeam = currentServerPreferredTeam || resolvePreferredTeam(preferenceState.team, teams)
    clearPreferredTeamPreference()
    setPreferenceState(readPreferredTeamState())
    if (authState.authenticated && currentTeam?.team_id != null) {
      setServerState(previous => ({
        ...previous,
        loading: true,
        error: null,
      }))
      clearServerPreferredTeam(currentTeam)
        .then((response) => {
          const nextState = normalizeFollowedTeamsResponse(response)
          setServerState({
            ...nextState,
            loading: false,
            error: null,
          })
          const promotedPreferredTeam = resolveServerPreferredTeam(nextState, teams)
          if (promotedPreferredTeam) {
            savePreferredTeamPreference(promotedPreferredTeam)
          }
        })
        .catch((error) => {
          if (error?.status === 401) clearAuthToken()
          setServerState(previous => ({
            ...previous,
            loading: false,
            error,
          }))
        })
    }
  }, [authState.authenticated, preferenceState.team, serverState, teams])

  const dismissPrompt = useCallback(() => {
    dismissPreferredTeamPrompt()
    setPreferenceState(readPreferredTeamState())
  }, [])

  const preferenceLoading = authState.loading || (authState.authenticated && serverState.loading)
  const promptDismissed = (
    preferenceState.promptDismissed
    || authState.loading
    || (authState.authenticated && serverState.loading && !serverState.error)
  )

  return {
    preferredTeam,
    rawPreferredTeam: authState.authenticated
      ? (resolveServerPreferredTeam(serverState, teams) || preferenceState.team)
      : preferenceState.team,
    promptDismissed,
    setPreferredTeam,
    clearPreferredTeam,
    dismissPrompt,
    loading: preferenceLoading,
    authLoading: authState.loading,
    authenticated: authState.authenticated,
    authError: authState.error,
    serverSyncLoading: serverState.loading,
    serverSyncError: serverState.error,
  }
}
