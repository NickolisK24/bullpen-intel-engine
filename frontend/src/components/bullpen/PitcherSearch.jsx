import { useEffect, useState } from 'react'
import { searchPitchers } from '../../utils/api'
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
  const teamParts = [
    result.team_abbreviation,
    result.team_name,
  ].filter(Boolean)

  return {
    id: result.player_id,
    name: result.player_name || 'Unknown pitcher',
    position: result.position || 'P',
    teamLabel: teamParts.length > 0 ? teamParts.join(' - ') : 'Team unavailable',
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
      className="mb-5 rounded border border-dirt bg-chalk/20 p-4"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <label className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="font-mono text-xs uppercase tracking-wide text-chalk400">
            Pitcher Search
          </span>
          <input
            type="search"
            value={query}
            onChange={event => onQueryChange(event.target.value)}
            aria-label="Search pitcher"
            placeholder="Kimbrel"
            className="w-full rounded border border-dirt bg-field/70 px-3 py-2 text-sm text-chalk200 outline-none transition-colors placeholder:text-chalk600 focus:border-amber/50"
          />
        </label>
      </div>

      {shouldShowResults && (
        <div className="mt-3">
          {loading ? (
            <div className="rounded border border-dirt bg-field/40 px-3 py-2 font-mono text-xs text-chalk400">
              Searching pitchers...
            </div>
          ) : error ? (
            <div className="rounded border border-red-400/35 bg-red-400/10 px-3 py-2 font-mono text-xs text-red-300">
              Search unavailable
            </div>
          ) : results.length === 0 ? (
            <div className="rounded border border-dirt bg-field/40 px-3 py-2 font-mono text-xs text-chalk400">
              No pitchers found.
            </div>
          ) : (
            <div className="grid gap-2">
              {results.map(result => {
                const view = getPitcherSearchResultView(result)
                return (
                  <button
                    key={view.id}
                    type="button"
                    onClick={() => onSelectPitcher(result)}
                    className="w-full rounded border border-dirt bg-field/60 px-3 py-3 text-left transition-colors hover:border-amber/40 hover:bg-amber/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/70"
                    aria-label={`Open pitcher detail for ${view.name}`}
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium text-chalk200">{view.name}</span>
                          <span className="rounded border border-dirt px-1.5 py-0.5 font-mono text-[10px] text-chalk400">
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
