import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { searchDiscovery } from '../../utils/api'
import {
  buildMatchupHref,
  buildPitcherHref,
  buildTeamBoardHref,
} from '../../utils/evidenceLinks'
import { formatUtcDateTimeEt } from '../../utils/dateDisplay'
import { formatFreshnessDate } from '../UI/Freshness'


const MIN_QUERY_LENGTH = 2
const SEARCH_DEBOUNCE_MS = 250

const GROUP_LABELS = Object.freeze({
  team: 'Teams',
  pitcher: 'Relievers',
  matchup: "Today's Matchups",
})

export function buildDiscoveryResultHref(result = {}) {
  if (result.entity_type === 'team') {
    return buildTeamBoardHref(result.metadata || result.id, { source: 'search' })
  }
  if (result.entity_type === 'pitcher') {
    return buildPitcherHref(result.id, { source: 'search' })
  }
  if (result.entity_type === 'matchup') {
    return buildMatchupHref(result.id)
  }
  return null
}

function statusLabel(status = {}) {
  return status.detailed || status.normalized || status.abstract || null
}

function resultContext(result = {}) {
  const metadata = result.metadata || {}
  if (result.entity_type === 'pitcher') {
    return [
      metadata.team_name || 'Team unavailable',
      metadata.position,
      metadata.roster_status,
    ].filter(Boolean)
  }
  if (result.entity_type === 'matchup') {
    const gameLabel = metadata.doubleheader_flag && metadata.doubleheader_flag !== 'N' && metadata.game_number
      ? `Game ${metadata.game_number}`
      : null
    return [
      formatFreshnessDate(metadata.reference_date),
      gameLabel,
      formatUtcDateTimeEt(metadata.game_time_utc, { includeDate: false }),
      statusLabel(metadata.status),
    ].filter(Boolean)
  }
  return [result.secondary_label].filter(Boolean)
}

function ResultLink({ result }) {
  const href = buildDiscoveryResultHref(result)
  if (!href || !result?.primary_label) return null
  const context = resultContext(result)
  return (
    <li>
      <Link
        to={href}
        className="block min-w-0 rounded-sm border border-dirt bg-field/45 px-3 py-3 transition-colors hover:border-amber/40 hover:bg-amber/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/70"
        aria-label={`Open ${result.primary_label}`}
      >
        <span className="block break-words text-sm font-medium text-chalk100">
          {result.primary_label}
        </span>
        {context.length > 0 && (
          <span className="mt-1 flex flex-wrap gap-x-2 gap-y-1 font-mono text-[11px] uppercase tracking-wide text-chalk500">
            {context.map((value, index) => (
              <span key={`${value}-${index}`}>{value}</span>
            ))}
          </span>
        )}
      </Link>
    </li>
  )
}

function SearchGroup({ group }) {
  const label = GROUP_LABELS[group.entity_type] || 'Results'
  const headingId = `search-group-${group.entity_type}`
  return (
    <section aria-labelledby={headingId} className="min-w-0 border-t border-dirt pt-4 lg:border-t-0 lg:border-l lg:pl-5 first:lg:border-l-0 first:lg:pl-0">
      <div className="flex items-center justify-between gap-3">
        <h2 id={headingId} className="font-mono text-xs uppercase tracking-[0.18em] text-chalk300">
          {label}
        </h2>
        {group.status === 'available' && (
          <span className="font-mono text-[10px] text-chalk600">{group.results.length}</span>
        )}
      </div>
      {group.status === 'unavailable' ? (
        <p className="mt-3 text-sm text-chalk500">This result group is temporarily unavailable.</p>
      ) : group.results.length === 0 ? (
        <p className="mt-3 text-sm text-chalk500">No matches in this group.</p>
      ) : (
        <ul className="mt-3 grid gap-2">
          {group.results.map(result => (
            <ResultLink key={`${result.entity_type}-${result.id}`} result={result} />
          ))}
        </ul>
      )}
    </section>
  )
}

export function SearchPageView({
  query,
  payload = null,
  loading = false,
  error = '',
  onQueryChange,
  onRetry,
}) {
  const normalizedQuery = String(query || '').trim()
  const hasSearch = normalizedQuery.length >= MIN_QUERY_LENGTH
  const groups = Array.isArray(payload?.groups) ? payload.groups : []

  const handleKeyDown = event => {
    if (event.key === 'Escape' && query) {
      event.preventDefault()
      onQueryChange('')
    }
  }

  return (
    <div className="mx-auto min-h-[70vh] max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="border-b border-dirt pb-5">
        <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-metadata-accent">Search / Discovery</p>
        <h1 className="mt-2 font-display text-3xl tracking-wide text-chalk100 sm:text-4xl">Search BaseballOS</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-chalk400">
          Find a team, reliever, or today&apos;s scheduled matchup and open its canonical BaseballOS destination.
        </p>
      </header>

      <div className="mt-6">
        <label htmlFor="global-discovery-search" className="block font-mono text-xs uppercase tracking-widest text-chalk400">
          Team, reliever, or matchup
        </label>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <input
            id="global-discovery-search"
            type="search"
            value={query}
            onChange={event => onQueryChange(event.target.value)}
            onKeyDown={handleKeyDown}
            autoComplete="off"
            aria-describedby="global-discovery-search-help"
            placeholder="Try Red Sox, Kimbrel, or BOS NYY"
            className="min-h-11 min-w-0 flex-1 rounded-sm border border-dirt bg-field/70 px-4 py-2 text-base text-chalk100 outline-none placeholder:text-chalk600 focus:border-amber/60 focus:ring-2 focus:ring-amber/20"
          />
          {query && (
            <button
              type="button"
              onClick={() => onQueryChange('')}
              className="min-h-11 rounded-sm border border-dirt px-4 py-2 font-mono text-xs uppercase tracking-wider text-chalk300 hover:border-chalk400 hover:text-chalk100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/70"
            >
              Clear
            </button>
          )}
        </div>
        <p id="global-discovery-search-help" className="mt-2 text-xs text-chalk600">
          Enter at least two characters. Escape clears the search; Tab and Enter open results.
        </p>
      </div>

      <div className="mt-7" aria-live="polite">
        {!hasSearch ? (
          <p className="rounded-sm border border-dirt bg-field/30 px-4 py-5 text-sm text-chalk400">
            Results stay empty until you enter at least two characters.
          </p>
        ) : loading ? (
          <p className="rounded-sm border border-dirt bg-field/30 px-4 py-5 text-sm text-chalk400">
            Searching BaseballOS…
          </p>
        ) : error || payload?.status === 'unavailable' ? (
          <div className="rounded-sm border border-red-400/35 bg-red-400/10 px-4 py-5">
            <p className="text-sm text-red-200">Search is temporarily unavailable.</p>
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 min-h-11 rounded-sm border border-red-300/40 px-3 py-2 font-mono text-xs uppercase tracking-wide text-red-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-200"
            >
              Retry search
            </button>
          </div>
        ) : payload?.result_count === 0 && payload?.status !== 'partial' ? (
          <p className="rounded-sm border border-dirt bg-field/30 px-4 py-5 text-sm text-chalk400">
            No teams, relievers, or today&apos;s matchups match “{normalizedQuery}”.
          </p>
        ) : (
          <div className="grid min-w-0 gap-5 lg:grid-cols-3" aria-label="Search results">
            {groups.map(group => <SearchGroup key={group.entity_type} group={group} />)}
          </div>
        )}
      </div>
    </div>
  )
}

export default function SearchPage({ searchFn = searchDiscovery }) {
  const [query, setQuery] = useState('')
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [retryVersion, setRetryVersion] = useState(0)
  const normalizedQuery = useMemo(() => query.trim(), [query])

  useEffect(() => {
    if (normalizedQuery.length < MIN_QUERY_LENGTH) {
      setPayload(null)
      setLoading(false)
      setError('')
      return undefined
    }

    let cancelled = false
    const controller = typeof AbortController === 'undefined' ? null : new AbortController()
    const timer = window.setTimeout(() => {
      setLoading(true)
      setError('')
      searchFn(
        { q: normalizedQuery },
        controller ? { signal: controller.signal, silent: true } : { silent: true },
      )
        .then(response => {
          if (!cancelled) setPayload(response)
        })
        .catch(requestError => {
          if (!cancelled && requestError?.name !== 'AbortError') {
            setPayload(null)
            setError('unavailable')
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }, SEARCH_DEBOUNCE_MS)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
      controller?.abort()
    }
  }, [normalizedQuery, retryVersion, searchFn])

  return (
    <SearchPageView
      query={query}
      payload={payload}
      loading={loading}
      error={error}
      onQueryChange={setQuery}
      onRetry={() => setRetryVersion(value => value + 1)}
    />
  )
}
