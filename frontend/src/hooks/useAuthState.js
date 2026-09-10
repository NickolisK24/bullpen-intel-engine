import { useCallback, useEffect, useState } from 'react'
import {
  AUTH_TOKEN_CHANGED_EVENT,
  clearAuthToken,
  getCurrentUser,
  isAuthTokenStorageEvent,
  logoutAuth,
  readAuthToken,
} from '../utils/api'

function anonymousState(error = null) {
  return {
    loading: false,
    authenticated: false,
    user: null,
    error,
  }
}

export function initialAuthState() {
  return readAuthToken()
    ? {
      loading: true,
      authenticated: false,
      user: null,
      error: null,
    }
    : anonymousState()
}

export function normalizeAuthResponse(identity) {
  if (identity?.authenticated === true && identity.user) {
    return {
      loading: false,
      authenticated: true,
      user: identity.user,
      error: null,
    }
  }
  return anonymousState()
}

export function authStateForTokenCheck(previousState = null) {
  if (previousState?.authenticated && previousState.user) {
    return {
      ...previousState,
      loading: false,
      error: null,
    }
  }

  return {
    loading: true,
    authenticated: false,
    user: null,
    error: null,
  }
}

export async function signOutAuthState(logout = logoutAuth) {
  try {
    await logout()
  } catch {
    // Local token clearing is the important browser-side logout action.
  }
  return anonymousState()
}

export function useAuthState() {
  const [state, setState] = useState(() => initialAuthState())
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    const refresh = () => setRefreshKey(value => value + 1)
    const refreshForAuthStorage = (event) => {
      if (isAuthTokenStorageEvent(event)) refresh()
    }
    window.addEventListener(AUTH_TOKEN_CHANGED_EVENT, refresh)
    window.addEventListener('storage', refreshForAuthStorage)
    return () => {
      window.removeEventListener(AUTH_TOKEN_CHANGED_EVENT, refresh)
      window.removeEventListener('storage', refreshForAuthStorage)
    }
  }, [])

  useEffect(() => {
    let active = true
    const token = readAuthToken()

    if (!token) {
      setState(anonymousState())
      return () => {
        active = false
      }
    }

    setState(previous => authStateForTokenCheck(previous))

    getCurrentUser()
      .then((identity) => {
        if (!active) return
        const nextState = normalizeAuthResponse(identity)
        if (!nextState.authenticated) {
          clearAuthToken()
        }
        setState(nextState)
      })
      .catch((error) => {
        if (!active) return
        clearAuthToken()
        setState(anonymousState(error))
      })

    return () => {
      active = false
    }
  }, [refreshKey])

  const refresh = useCallback(() => {
    setRefreshKey(value => value + 1)
  }, [])

  const signOut = useCallback(async () => {
    const nextState = await signOutAuthState()
    setState(nextState)
    setRefreshKey(value => value + 1)
  }, [])

  return {
    ...state,
    refresh,
    signOut,
  }
}
