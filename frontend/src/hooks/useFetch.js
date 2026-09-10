import { useState, useEffect, useCallback, useRef } from 'react'

export function createRequestGuard() {
  let activeRequest = 0

  return {
    begin() {
      activeRequest += 1
      return activeRequest
    },
    invalidate() {
      activeRequest += 1
    },
    isCurrent(request) {
      return request === activeRequest
    },
  }
}

export function getFetchStatus({ data, error, loading }) {
  const hasData = data !== null && data !== undefined
  const hasError = Boolean(error)
  return {
    hasData,
    noDataError: hasError && !hasData,
    staleWithError: hasError && hasData && !loading,
  }
}

export function isCanceledFetch(error) {
  return error?.name === 'AbortError' || error?.status === 'canceled'
}

export function useFetch(fetchFn, deps = []) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const requestGuardRef = useRef(null)
  const controllerRef = useRef(null)
  if (!requestGuardRef.current) requestGuardRef.current = createRequestGuard()

  const run = useCallback(async () => {
    controllerRef.current?.abort()
    const controller = typeof AbortController === 'undefined' ? null : new AbortController()
    controllerRef.current = controller
    const request = requestGuardRef.current.begin()
    setLoading(true)
    setError(null)
    try {
      const result = await fetchFn(controller ? { signal: controller.signal } : {})
      if (requestGuardRef.current.isCurrent(request)) setData(result)
    } catch (err) {
      if (requestGuardRef.current.isCurrent(request) && !isCanceledFetch(err)) {
        setError(err.message || 'Failed to load')
      }
    } finally {
      if (requestGuardRef.current.isCurrent(request)) setLoading(false)
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    run()
    return () => {
      requestGuardRef.current.invalidate()
      controllerRef.current?.abort()
      controllerRef.current = null
    }
  }, [run])

  return {
    data,
    loading,
    error,
    refetch: run,
    ...getFetchStatus({ data, error, loading }),
  }
}
