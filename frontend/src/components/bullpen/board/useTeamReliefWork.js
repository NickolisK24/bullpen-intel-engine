import { useCallback, useEffect, useRef, useState } from 'react'
import { getTeamReliefWork } from '../../../utils/api'

export function createLatestTeamReliefWorkLoader(fetchReliefWork = getTeamReliefWork) {
  let generation = 0

  return {
    async load(teamId) {
      const requestGeneration = ++generation
      try {
        const data = await fetchReliefWork(teamId)
        if (requestGeneration !== generation) return { current: false }
        return { current: true, data, error: null }
      } catch {
        if (requestGeneration !== generation) return { current: false }
        return { current: true, data: null, error: true }
      }
    },
    invalidate() {
      generation += 1
    },
  }
}

export function useTeamReliefWork(teamId, enabled = true) {
  const loader = useRef(null)
  if (loader.current === null) loader.current = createLatestTeamReliefWorkLoader()
  const [state, setState] = useState({
    teamId: null,
    data: null,
    loading: false,
    error: null,
  })

  const refetch = useCallback(async () => {
    if (!enabled || teamId === null || teamId === undefined || teamId === '') {
      loader.current.invalidate()
      setState({ teamId: null, data: null, loading: false, error: null })
      return
    }

    setState({ teamId, data: null, loading: true, error: null })
    const result = await loader.current.load(teamId)
    if (!result.current) return
    setState({
      teamId,
      data: result.data,
      loading: false,
      error: result.error,
    })
  }, [enabled, teamId])

  useEffect(() => {
    refetch()
    return () => loader.current.invalidate()
  }, [refetch])

  if (!enabled) {
    return { data: null, loading: false, error: null, refetch }
  }

  if (state.teamId !== teamId) {
    return {
      data: null,
      loading: teamId !== null && teamId !== undefined && teamId !== '',
      error: null,
      refetch,
    }
  }

  return { ...state, refetch }
}
