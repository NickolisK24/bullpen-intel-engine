import { useState, useEffect, useCallback } from 'react'

export function getFetchStatus({ data, error, loading }) {
  const hasData = data !== null && data !== undefined
  const hasError = Boolean(error)
  return {
    hasData,
    noDataError: hasError && !hasData,
    staleWithError: hasError && hasData && !loading,
  }
}

export function useFetch(fetchFn, deps = []) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchFn()
      setData(result)
    } catch (err) {
      setError(err.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { run() }, [run])

  return {
    data,
    loading,
    error,
    refetch: run,
    ...getFetchStatus({ data, error, loading }),
  }
}
