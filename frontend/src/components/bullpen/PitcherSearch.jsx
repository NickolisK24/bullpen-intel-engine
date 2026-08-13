import { useEffect, useState } from 'react'
import { searchPitchers } from '../../utils/api'
import { formatTeamLabel } from '../../utils/formatters'
import AvailabilityBadge from './AvailabilityBadge'
import { getRosterStatusSummary } from './availabilityView'

const MIN_QUERY_LENGTH = 2

export function getPitcherSearchResultView(result = {}) {
  const rosterStatus = getRosterStatusSummary({
    status: result.roster_status,
    label: result.roster_status_label,
    confidence: result.availability_confidence,
    is_inactive_context: result.availability === 'Unavailable',
  })
  return {
    id: result.player_id,
    name: result.player_name || 'Unknown pitcher',
    position: result.position || 'P',
    teamLabel: formatTeamLabel(result),
    rosterLabel: rosterStatus?.label || result.roster_status || 'Roster Unknown',
    availability: result.availability || 'Monitor',
    availabilityPayload: {
      availability_status: result.availability || 'Monitor',
      confidence: result.availability_confidence,
      data_state: result.availability_data_state,
    },
  }
}

export function PitcherSearchPanel({
  query,
  results = [],
  loading = false,
  error = '',
  minQueryLength = MIN_QUERY_LENGTH,
  onQueryChange,
  onSelectPitcher,
}) {
  const normalizedQuery = String(query || '').trim()
  const shouldShowResults = normalizedQuery.length >= minQueryLength

  return (
    <section
      aria-label="Pitcher Search"
      className="border-b border-line py-5"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <label className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="bos-micro">
            Pitcher Search
          </span>
          <input
            type="search"
            value={query}
            onChange={event => onQueryChange(event.target.value)}
            aria-label="Search pitcher"
            placeholder="Search pitchers..."
            className="min-h-11 w-full border border-line-strong bg-panel px-3 text-sm text-chalk200 outline-none transition-colors placeholder:text-chalk600 focus:border-signal"
          />
        </label>
      </div>

      {shouldShowResults && (
        <div className="mt-3">
          {loading ? (
            <div className="border-l border-line-strong py-2 pl-3 font-mono text-xs text-chalk400">
              Searching pitchers...
            </div>
          ) : error ? (
            <div className="border-l border-danger py-2 pl-3 font-mono text-xs text-red-300">
              Search unavailable
            </div>
          ) : results.length === 0 ? (
            <div className="border-l border-line-strong py-2 pl-3 font-mono text-xs text-chalk400">
              No pitchers found.
            </div>
          ) : (
            <div className="border-t border-line">
              {results.map(result => {
                const view = getPitcherSearchResultView(result)
                return (
                  <button
                    key={view.id}
                    type="button"
                    onClick={() => onSelectPitcher(result)}
                    className="min-h-11 w-full border-b border-line bg-transparent py-3 text-left transition-colors hover:bg-panel focus:outline-none focus-visible:ring-2 focus-visible:ring-signal/70"
                    aria-label={`Open pitcher detail for ${view.name}`}
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium text-chalk200">{view.name}</span>
                          <span className="border border-line px-1.5 py-0.5 font-mono text-[10px] text-chalk400">
                            {view.position}
                          </span>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-chalk400">
                          <span>{view.teamLabel}</span>
                          <span>{view.rosterLabel}</span>
                        </div>
                      </div>
                      <AvailabilityBadge availability={view.availabilityPayload} />
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

export default function PitcherSearch({
  onSelectPitcher,
  searchFn = searchPitchers,
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const normalizedQuery = query.trim()
    if (normalizedQuery.length < MIN_QUERY_LENGTH) {
      setResults([])
      setLoading(false)
      setError('')
      return undefined
    }

    let cancelled = false
    setLoading(true)
    setError('')

    searchFn({ q: normalizedQuery })
      .then(payload => {
        if (!cancelled) {
          setResults(Array.isArray(payload?.results) ? payload.results : [])
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResults([])
          setError('unavailable')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [query, searchFn])

  return (
    <PitcherSearchPanel
      query={query}
      results={results}
      loading={loading}
      error={error}
      onQueryChange={setQuery}
      onSelectPitcher={onSelectPitcher}
    />
  )
}
