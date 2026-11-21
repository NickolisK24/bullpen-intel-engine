import { SearchAnswer } from '../ResearchAnswer'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { searchDiscovery, searchRehearsalEdition } from '../../utils/api'
import {
  buildMatchupHref,
  buildRehearsalPitcherHref,
  buildRehearsalTeamBoardHref,
  buildPitcherHref,
  buildTeamBoardHref,
  parseRehearsalRevision,
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

function ResultLink({ result, edition }) {
  let href = buildDiscoveryResultHref(result)
  if (edition) {
    href = result.entity_type === 'pitcher' && result.metadata?.player_id === result.id
      ? buildRehearsalPitcherHref(result.id, edition.revision, edition.generation)
      : null
    if (result.entity_type === 'team' && Number.isSafeInteger(result.id) && result.id > 0
        && result.metadata?.team_id === result.id) {
      href = buildRehearsalTeamBoardHref(result.id, edition.revision, edition.generation)
    }
    if (result.entity_type === 'matchup' && Number.isSafeInteger(result.id) && result.id > 0
        && result.metadata?.game_pk === result.id) {
      href = `${buildMatchupHref(result.id)}?rehearsalRevision=${edition.revision}&rehearsalGeneration=${edition.generation}`
    }
  }
  if (!result?.primary_label || (!edition && !href)) return null
  const Element = href ? Link : 'div'
  const context = resultContext(result)
  return (
    <li>
      <Element
        {...(href ? { to: href, 'aria-label': `Open ${result.primary_label}` } : {})}
        className="block min-w-0 rounded-sm border border-dirt bg-field/45 px-3 py-3 transition-colors hover:border-amber/40 hover:bg-amber/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/70"
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
      </Element>
    </li>
  )
}

function SearchGroup({ group, edition }) {
  const label = GROUP_LABELS[group.entity_type] || 'Results'
  const headingId = `search-group-${group.entity_type}`
  return (
    <section aria-labelledby={headingId} className="min-w-0 border-t border-dirt pt-4 lg:border-t-0 lg:border-l lg:pl-5 first:lg:border-l-0 first:lg:pl-0">
      <div className="flex items-center justify-between gap-3">
        <h2 id={headingId} className="font-mono text-xs uppercase tracking-[0.18em] text-chalk300">
          {edition && group.entity_type === 'matchup' ? 'Matchups on this date' : label}
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
            <ResultLink key={`${result.entity_type}-${result.id}`} result={result} edition={edition} />
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
  historical = false,
  edition = null,
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
          {historical
            ? `Historical rehearsal${payload?.represented_date ? ` · ${payload.represented_date}` : ''}. Search team, reliever, and matchup evidence for this edition.`
            : "Find a team, reliever, or today's scheduled matchup and open its canonical BaseballOS destination."}
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
            {historical ? "No teams, relievers, or represented matchups match" : "No teams, relievers, or today's matchups match"} “{normalizedQuery}”.
          </p>
        ) : (
          <div className="grid min-w-0 gap-5 lg:grid-cols-3" aria-label="Search results">
            {groups.map(group => <SearchGroup key={group.entity_type} group={group} edition={edition} />)}
          </div>
        )}
      </div>
      {!historical && hasSearch && payload && !loading && !error && payload.status !== 'unavailable' && <SearchAnswer />}
    </div>
  )
}

export default function SearchPage({ searchFn = searchDiscovery }) {
  const [params] = useSearchParams()
  let revision
  try {
    revision = parseRehearsalRevision(params.get('rehearsalRevision'), params.getAll('rehearsalRevision').length > 1)
  } catch (error) {
    return <p role="alert">{error.message}</p>
  }
  return <SearchEdition key={revision ?? 'public'} revision={revision} publicSearch={searchFn} />
}

function SearchEdition({ revision, publicSearch }) {
  const searchFn = useCallback(async (params, options) => {
    if (revision === null) return { payload: await publicSearch(params, options), edition: null }
    const response = await searchRehearsalEdition(revision, params, options)
    if (response?.status !== 'represented' || response.selection_revision !== revision
      || response.current_serving_eligible !== false || typeof response.generation !== 'string'
      || !/^[a-f0-9]{64}$/.test(response.generation) || response.search?.query !== params.q) {
      throw new Error('The historical search edition could not be verified.')
    }
    return { payload: response.search, edition: { revision, generation: response.generation } }
  }, [revision, publicSearch])
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [retryVersion, setRetryVersion] = useState(0)
  const normalizedQuery = useMemo(() => query.trim(), [query])

  useEffect(() => {
    if (normalizedQuery.length < MIN_QUERY_LENGTH) {
      setResult(null)
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
          if (!cancelled) setResult({ query: normalizedQuery, ...response })
        })
        .catch(requestError => {
          if (!cancelled && requestError?.name !== 'AbortError') {
            setResult(null)
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
      historical={revision !== null}
      edition={result?.edition}
      query={query}
      payload={result?.query === normalizedQuery ? result.payload : null}
      loading={loading || (normalizedQuery.length >= MIN_QUERY_LENGTH && result?.query !== normalizedQuery && !error)}
      error={error}
      onQueryChange={setQuery}
      onRetry={() => setRetryVersion(value => value + 1)}
    />
  )
}
