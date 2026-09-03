import { useState, useEffect, useMemo } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import useEvidenceHashNavigation from '../../hooks/useEvidenceHashNavigation'
import { getRelieverFinder, getTeams } from '../../utils/api'
import {
  BULLPEN_VIEWS,
  buildAllPitchersHref,
  buildCanonicalBullpenHref,
  buildComparisonHref,
  buildPitcherHref,
  buildTeamBoardHref,
  readBullpenLocation,
  resolveTeamId,
  resolveTeamReference,
} from '../../utils/evidenceLinks'
import { LoadingPane, ErrorState, EmptyState, SectionHeader } from '../UI'
import TonightsBullpenBoard from './board/TonightsBullpenBoard'
import TeamBullpenComparison from './board/TeamBullpenComparison'
import { getBullpenEmptyState } from './emptyState'
import AvailabilityBadge from './AvailabilityBadge'
import {
  buildFinderRequestParams,
  computeFinderIntent,
  describeActiveSort,
  DEFAULT_FINDER_SORT,
  FINDER_MIN_QUERY_LENGTH,
  FINDER_PAGE_SIZE,
  formatRestDays,
  formatWorkloadCount,
  getAvailabilityFilterOptions,
  getTeamOptionLabel,
} from './relieverFinderView'

// The old "All Teams" score-table tab (30-team Avg Workload / risk-tier counts)
// was retired in phase-0-clarity/02: it competed with the Dashboard's league
// landscape and read as a score-forward leaderboard. The Dashboard is the only
// full league-board surface; /bullpen?view=teams deep-links fall back to the
// Team Board below.
const VIEW_MODES   = [
  { id: 'board',    label: 'Team Board' },
  { id: 'compare',  label: 'Compare Bullpens' },
  // The pitchers view lists the reliever-eligible population only, so its public
  // label is "Reliever Finder" — "All Pitchers" would overstate the population.
  { id: 'pitchers', label: 'Reliever Finder' },
]
const FINDER_DEBOUNCE_MS = 250

function useRelieverFinder(params) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [retryVersion, setRetryVersion] = useState(0)

  useEffect(() => {
    if (!params) {
      setData(null)
      setLoading(false)
      setError(null)
      return undefined
    }

    let current = true
    const controller = typeof AbortController === 'undefined' ? null : new AbortController()
    setLoading(true)
    setError(null)
    const timer = setTimeout(() => {
      getRelieverFinder(params, {
        ...(controller ? { signal: controller.signal } : {}),
        silent: true,
      })
        .then(result => {
          if (current) setData(result)
        })
        .catch(err => {
          if (current && err?.name !== 'AbortError') {
            setData(null)
            setError(err?.message || 'Failed to load relievers')
          }
        })
        .finally(() => {
          if (current) setLoading(false)
        })
    }, FINDER_DEBOUNCE_MS)

    return () => {
      current = false
      clearTimeout(timer)
      controller?.abort()
    }
  }, [params, retryVersion])

  return {
    data,
    loading,
    error,
    refetch: () => setRetryVersion(value => value + 1),
  }
}

// The page identity for the active /bullpen view.
//
// /bullpen hosts three canonically different surfaces (Product Experience
// Standard section 4), so the route — not any child view — owns the one H1 and
// answers the active view's own question. This is a presentation/routing
// concern only: it reads the resolved route state and the team list the shell
// already fetches, and never the board payload, Team State, freshness,
// availability, or the comparison response. That is what keeps the heading
// stable while a child view loads, errors, refetches, or remounts.
export function getBullpenPageIdentity(viewMode, teamList, urlState = {}) {
  if (viewMode === BULLPEN_VIEWS.PITCHERS) {
    return 'Reliever Finder'
  }

  if (viewMode === BULLPEN_VIEWS.COMPARE) {
    // A comparison exists only once two DIFFERENT teams resolve. One side, an
    // unknown reference, or the same club twice is still the generic identity —
    // naming half a comparison would claim something the page is not showing.
    const teamIdA = resolveTeamId(teamList, urlState.teamA)
    const teamIdB = resolveTeamId(teamList, urlState.teamB)
    const labelA = getTeamOptionLabel(resolveTeamReference(teamList, urlState.teamA))
    const labelB = getTeamOptionLabel(resolveTeamReference(teamList, urlState.teamB))
    if (teamIdA != null && teamIdB != null && teamIdA !== teamIdB && labelA && labelB) {
      return `${labelA} vs. ${labelB} Bullpen Comparison`
    }
    return 'Compare Bullpens'
  }

  // TB-01 moves the selected club identity into the v2-backed Answer Block.
  // The route shell now names the product surface once and does not repeat the
  // club directly above the block that owns the current team answer.
  return 'Team Board'
}


export default function Bullpen() {
  const location = useLocation()
  const navigate = useNavigate()
  const urlState = useMemo(
    () => readBullpenLocation(location.search, location.hash),
    [location.hash, location.search],
  )
  const viewMode = urlState.view
  // The Reliever Finder opens on a neutral name A–Z order so it never reads as a
  // workload leaderboard; the pitches and rest orderings stay user-selectable.
  const [sortBy, setSortBy]               = useState(DEFAULT_FINDER_SORT)
  const [includeStale, setIncludeStale]   = useState(false)
  const [availabilityFilter, setAvailabilityFilter] = useState('ALL')
  const teams    = useFetch(getTeams)
  const teamList = teams.data || []
  const teamsReady = !teams.loading && !teams.error && teamList.length > 0
  const selectedTeam = resolveTeamId(teamList, urlState.team)
  const canonicalTeam = resolveTeamReference(teamList, urlState.team)
  const activeTeamRef = canonicalTeam || urlState.team
  useEvidenceHashNavigation(viewMode)

  useEffect(() => {
    const resolvedState = { ...urlState }
    if (teamsReady) {
      if (urlState.view === BULLPEN_VIEWS.COMPARE) {
        resolvedState.teamA = resolveTeamReference(teamList, urlState.teamA)
        resolvedState.teamB = resolveTeamReference(teamList, urlState.teamB)
      } else {
        resolvedState.team = resolveTeamReference(teamList, urlState.team)
      }
    }

    let canonicalHref = buildCanonicalBullpenHref(resolvedState)
    if (urlState.unsupportedHash) canonicalHref += `#${urlState.unsupportedHash}`
    const currentHref = `${location.pathname}${location.search}${location.hash}`
    if (canonicalHref !== currentHref) navigate(canonicalHref, { replace: true })
  }, [location.hash, location.pathname, location.search, navigate, teamList, teamsReady, urlState])

  const handleViewChange = (nextView) => {
    if (nextView === BULLPEN_VIEWS.COMPARE) {
      navigate(buildComparisonHref(urlState.teamA, urlState.teamB, { source: urlState.source }))
    } else if (nextView === BULLPEN_VIEWS.PITCHERS) {
      navigate(buildAllPitchersHref({ teamRef: activeTeamRef, source: urlState.source }))
    } else {
      navigate(buildTeamBoardHref(activeTeamRef, { source: urlState.source }))
    }
  }

  const handleTeamSelect = (teamId) => {
    const team = resolveTeamReference(teamList, teamId)
    navigate(buildTeamBoardHref(team, {
      source: urlState.source,
      section: urlState.section,
    }))
  }

  const handlePitcherSelect = (pitcherId, teamRef = activeTeamRef, source = urlState.source) => {
    navigate(buildPitcherHref(pitcherId, {
      teamRef,
      source,
      section: urlState.section,
    }))
  }

  const handleComparisonTeamChange = (side, teamId) => {
    const changedTeam = resolveTeamReference(teamList, teamId)
    const teamA = side === 'a' ? changedTeam : resolveTeamReference(teamList, urlState.teamA)
    const teamB = side === 'b' ? changedTeam : resolveTeamReference(teamList, urlState.teamB)
    navigate(buildComparisonHref(teamA, teamB, {
      source: urlState.source,
      section: urlState.section,
    }))
  }

  const handleAllPitchersTeamChange = (teamId) => {
    const team = resolveTeamReference(teamList, teamId)
    navigate(buildAllPitchersHref({ teamRef: team, source: urlState.source }))
  }

  const handleAllPitchersSelect = (row) => {
    const teamRef = row?.pitcher || resolveTeamReference(teamList, selectedTeam)
    // The reliever row addresses the pitcher through the pitcher object. The
    // fatigue payload no longer carries the score row's foreign key.
    handlePitcherSelect(row?.pitcher?.id, teamRef, 'all_pitchers')
  }

  return (
    <div className={viewMode === BULLPEN_VIEWS.BOARD
      ? 'team-board-shell'
      : 'p-4 sm:p-6 lg:p-8 mx-auto max-w-7xl'}>
      <SectionHeader
        as="h1"
        title={getBullpenPageIdentity(viewMode, teamList, urlState)}
        subtitle="Team-specific bullpen analysis from latest completed data - current availability, recent workload, and role context"
        action={
          <div className="flex items-center gap-3 flex-wrap">
            <div className={viewMode === BULLPEN_VIEWS.BOARD
              ? 'flex flex-wrap gap-1 border-b border-line-default'
              : 'flex flex-wrap gap-1 rounded-lg border border-dirt bg-chalk/30 p-1'}>
              {VIEW_MODES.map(m => (
                <button
                  key={m.id}
                  type="button"
                  aria-pressed={viewMode === m.id}
                  onClick={() => handleViewChange(m.id)}
                  className={viewMode === BULLPEN_VIEWS.BOARD
                    ? `min-h-11 rounded-sm border-b-2 px-3 py-2 font-board text-board-metadata focus:outline-none focus-visible:ring-2 focus-visible:ring-line-focus ${m.id === viewMode
                      ? 'border-brand-blue text-brand-blue'
                      : 'border-transparent text-text-tertiary hover:text-text-primary'}`
                    : `rounded px-3 py-1.5 font-mono text-xs transition-all ${m.id === viewMode
                      ? 'border-dirt bg-chalk text-chalk200 shadow'
                      : 'text-chalk400 hover:text-chalk200'}`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
        }
      />

      {viewMode === BULLPEN_VIEWS.BOARD ? (
        <>
          <TonightsBullpenBoard
            teams={teams}
            requestedTeam={urlState.team}
            requestedSection={urlState.section}
            onSelectTeam={handleTeamSelect}
            onSelectPitcher={handlePitcherSelect}
          />
        </>
      ) : viewMode === BULLPEN_VIEWS.COMPARE ? (
        <TeamBullpenComparison
          teams={teams}
          requestedTeamA={urlState.teamA}
          requestedTeamB={urlState.teamB}
          onTeamAChange={teamId => handleComparisonTeamChange('a', teamId)}
          onTeamBChange={teamId => handleComparisonTeamChange('b', teamId)}
        />
      ) : (
        <PitcherView
          teams={teams}
          selectedTeam={selectedTeam}
          onSelectTeam={handleAllPitchersTeamChange}
          onSelectPitcher={handleAllPitchersSelect}
          sortBy={sortBy}
          setSortBy={setSortBy}
          includeStale={includeStale}
          onToggleStale={() => setIncludeStale(v => !v)}
          availabilityFilter={availabilityFilter}
          setAvailabilityFilter={setAvailabilityFilter}
        />
      )}
    </div>
  )
}

function PitcherView({
  teams,
  selectedTeam, onSelectTeam,
  onSelectPitcher,
  sortBy, setSortBy,
  includeStale, onToggleStale,
  availabilityFilter, setAvailabilityFilter,
}) {
  const [page, setPage] = useState(1)
  const [searchTerm, setSearchTerm] = useState('')
  const finderParams = useMemo(() => buildFinderRequestParams({
    searchTerm,
    selectedTeam,
    availabilityFilter,
    includeStale,
    sortBy,
    page,
    limit: FINDER_PAGE_SIZE,
  }), [availabilityFilter, includeStale, page, searchTerm, selectedTeam, sortBy])
  // No request exists until finderParams carries real user intent. Superseded
  // requests are aborted and guarded so an older response cannot replace a
  // newer query.
  const allScores = useRelieverFinder(finderParams)

  const fatiguePayload = allScores.data
  const allRows = Array.isArray(fatiguePayload) ? fatiguePayload : (fatiguePayload?.data || [])
  const meta = Array.isArray(fatiguePayload) ? null : fatiguePayload?.meta
  const selectedTeamInfo = (teams.data || []).find(t => t.team_id === selectedTeam)
  const selectedTeamLabel = getTeamOptionLabel(selectedTeamInfo) || null

  // The finder is search-first: a broad reliever list appears only once the
  // visitor asks for something — a name, a team, or a public availability
  // status. Until then the surface stays a calm finder, not a league dump.
  const { hasIntent } = computeFinderIntent({ searchTerm, selectedTeam, availabilityFilter })

  // Filtering, ordering, and pagination are backend-owned. The browser renders
  // one bounded page exactly as returned.
  const totalRows = Number(meta?.total_results ?? allRows.length)
  const totalPages = Math.max(1, Number(meta?.total_pages || 1))
  const safePage = Math.min(Number(meta?.page || page), totalPages)
  const startIdx = totalRows === 0 ? 0 : (safePage - 1) * FINDER_PAGE_SIZE
  const endIdx = Math.min(startIdx + allRows.length, totalRows)
  const visible = allRows
  // The empty state only speaks once the visitor has expressed intent — it never
  // reports "no results" against the neutral opening view.
  const emptyState = getBullpenEmptyState({
    allRowsCount: allRows.length,
    visibleRowsCount: allRows.length,
    meta,
    includeStale,
    selectedTeam,
    selectedTeamLabel,
    availabilityFilter,
    searchTerm,
  })

  const availabilityOptions = getAvailabilityFilterOptions()

  // Reset page to 1 when filters change (so filtering doesn't drop you onto an empty page)
  useEffect(() => { setPage(1) }, [availabilityFilter, selectedTeam, sortBy, searchTerm, includeStale])

  const handleClear = () => {
    setSearchTerm('')
    setAvailabilityFilter('ALL')
    setSortBy(DEFAULT_FINDER_SORT)
    if (includeStale) onToggleStale?.()
    if (selectedTeam != null) onSelectTeam(null)
  }

  const sortDirection = key => (
    sortBy === key ? (key === 'pitches' ? 'descending' : 'ascending') : 'none'
  )

  const SortHeader = ({ column, label, arrow }) => (
    <th scope="col" aria-sort={sortDirection(column)}>
      <button
        type="button"
        onClick={() => setSortBy(column)}
        className={`min-h-11 select-none text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-amber/70 ${sortBy === column ? 'text-amber' : 'text-chalk400 hover:text-chalk200'}`}
      >
        {label} {sortBy === column && <span aria-hidden="true">{arrow}</span>}
      </button>
    </th>
  )

  return (
    <>
      {/* One coherent finder control area: search → team → availability →
          freshness window → clear. Every field can shrink (min-w-0) and the row
          wraps deliberately, so the whole group fits a 320px column. */}
      <section aria-label="Reliever finder controls" className="mb-6 rounded-lg border border-dirt bg-field/30 p-3 sm:p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="min-w-0 sm:col-span-2 lg:col-span-1">
            <label htmlFor="reliever-finder-search" className="block font-mono text-[11px] uppercase tracking-widest text-chalk500">
              Find a reliever
            </label>
            <input
              id="reliever-finder-search"
              type="search"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              aria-label="Search relievers by name"
              placeholder="Search reliever"
              aria-describedby="reliever-finder-search-help"
              className="mt-1 w-full min-w-0 rounded border border-dirt bg-field/70 px-3 py-2 font-mono text-xs text-chalk200 outline-none transition-colors placeholder:text-chalk600 focus:border-amber/50"
            />
            <p id="reliever-finder-search-help" className="mt-1 font-mono text-[10px] text-chalk600">
              Enter at least {FINDER_MIN_QUERY_LENGTH} characters.
            </p>
          </div>
          <div className="min-w-0">
            <label htmlFor="reliever-finder-team" className="block font-mono text-[11px] uppercase tracking-widest text-chalk500">
              Team
            </label>
            <select
              id="reliever-finder-team"
              value={selectedTeam != null ? String(selectedTeam) : ''}
              onChange={e => onSelectTeam(e.target.value ? Number(e.target.value) : null)}
              className="mt-1 w-full min-w-0 rounded border border-dirt bg-field/70 px-3 py-2 font-mono text-xs text-chalk200 outline-none transition-colors focus:border-amber/50"
            >
              <option value="">All teams</option>
              {(teams.data || []).map(t => (
                <option key={t.team_id} value={t.team_id}>{getTeamOptionLabel(t)}</option>
              ))}
            </select>
          </div>
          <div className="min-w-0">
            <label htmlFor="reliever-finder-availability" className="block font-mono text-[11px] uppercase tracking-widest text-chalk500">
              Availability
            </label>
            <select
              id="reliever-finder-availability"
              value={availabilityFilter}
              onChange={e => setAvailabilityFilter(e.target.value)}
              className="mt-1 w-full min-w-0 rounded border border-dirt bg-field/70 px-3 py-2 font-mono text-xs text-chalk200 outline-none transition-colors focus:border-amber/50"
            >
              {availabilityOptions.map(option => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
          <StaleToggle active={includeStale} onToggle={onToggleStale} />
          {hasIntent && (
            <button
              type="button"
              onClick={handleClear}
              className="shrink-0 rounded border border-dirt px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-chalk300 transition-colors hover:border-chalk400 hover:text-chalk100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
            >
              Clear filters
            </button>
          )}
        </div>
      </section>

      {!hasIntent ? (
        // Neutral opening view: one short instruction, no result list, no result
        // count, no ranked examples. It reads as an invitation, not an error.
        <div className="rounded-lg border border-dirt bg-field/30 p-6 text-center">
          {/* The page heading names this surface permanently now, so the panel
              no longer repeats "Reliever Finder" as a second visible title —
              and the name no longer disappears the moment a search begins. */}
          <p className="mx-auto max-w-md text-sm text-chalk300">
            Search for a reliever or choose a team to inspect recent workload.
          </p>
          <p className="mx-auto mt-1 max-w-md text-xs text-chalk500">
            You can also filter by public availability status: Available, On Watch, Limited, or Unavailable.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-6 2xl:flex-row 2xl:items-start">
          {/* Main table */}
          <div className="min-w-0 flex-1 card overflow-hidden transition-all duration-300">
            {allScores.loading ? (
              <LoadingPane message="Loading recent workload data..." />
            ) : allScores.error ? (
              <ErrorState message={allScores.error} onRetry={allScores.refetch} />
            ) : allRows.length === 0 ? (
              <div role="status" aria-live="polite">
                <EmptyState title={emptyState.title} subtitle={emptyState.subtitle} />
              </div>
            ) : (
              <>
                {/* Result summary + active order + column-abbreviation legend.
                    Wraps cleanly so nothing is clipped at 320px. */}
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-dirt bg-chalk/20 px-4 py-2">
                  <p className="min-w-0 font-mono text-[11px] text-chalk500" role="status" aria-live="polite">
                    <span className="text-chalk300">{totalRows}</span>{' '}
                    reliever{totalRows === 1 ? '' : 's'} · sorted by {describeActiveSort(sortBy)}
                  </p>
                  <p className="min-w-0 font-mono text-[10px] text-chalk600">
                    7d = last 7 days · Rest = days since last outing
                  </p>
                </div>
                <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <SortHeader column="name" label="Pitcher" arrow="↑" />
                      <th scope="col" className="text-chalk400">Team</th>
                      <th scope="col" className="text-chalk400">Availability</th>
                      <SortHeader column="pitches" label="Pitches (7d)" arrow="↓" />
                      <SortHeader column="rest" label="Rest" arrow="↑" />
                      <th scope="col" className="text-chalk400">Appearances (7d)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map(row => (
                      <tr key={row.pitcher?.id ?? row.pitcher?.mlb_id}>
                        <td className="font-medium">
                          {row.pitcher?.id ? (
                            <Link
                              to={buildPitcherHref(row.pitcher.id, { teamRef: row.pitcher, source: 'all_pitchers' })}
                              aria-label={`Open pitcher detail for ${row.pitcher?.full_name ?? 'pitcher'}`}
                              className="inline-flex min-h-11 items-center text-chalk200 underline decoration-transparent underline-offset-4 hover:text-amber hover:decoration-current focus-visible:ring-2 focus-visible:ring-amber/70"
                            >
                              {row.pitcher?.full_name ?? '—'}
                            </Link>
                          ) : '—'}
                        </td>
                        <td className="font-mono text-xs text-chalk400">{row.pitcher?.team_abbreviation ?? '—'}</td>
                        <td><AvailabilityBadge availability={row.availability} showDataState /></td>
                        <td className="font-mono text-xs text-chalk200">{formatWorkloadCount(row.pitches_last_7_days)}</td>
                        <td className="font-mono text-xs text-chalk400">{formatRestDays(row.days_since_last_appearance)}</td>
                        <td className="font-mono text-xs text-chalk200">{formatWorkloadCount(row.appearances_last_7)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
                {totalPages > 1 && (
                  <Pagination
                    page={safePage}
                    totalPages={totalPages}
                    startIdx={startIdx}
                    endIdx={endIdx}
                    totalRows={totalRows}
                    onPageChange={setPage}
                  />
                )}
              </>
            )}
          </div>

        </div>
      )}
    </>
  )
}

// Pagination controls — only renders when there's more than one page.
// Shows up to 5 page-number buttons centered on the current page,
// plus prev/next chevrons and a "Showing X-Y of Z" summary.
function Pagination({ page, totalPages, startIdx, endIdx, totalRows, onPageChange }) {
  // Compute a windowed range of page numbers around the current page.
  const window = 2  // pages to show on each side of current
  const start  = Math.max(1, page - window)
  const end    = Math.min(totalPages, page + window)
  const pages  = []
  for (let i = start; i <= end; i++) pages.push(i)

  const btnStyle = (active) =>
    `min-h-11 min-w-11 px-2 py-1 rounded font-mono text-xs transition-all ${
      active
        ? 'bg-amber/20 border border-amber/40 text-amber'
        : 'border border-dirt text-chalk400 hover:text-chalk200 hover:border-chalk400'
    }`

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-t border-dirt bg-chalk/20">
      <div className="text-chalk500 text-xs font-mono" aria-live="polite">
        Showing {startIdx + 1}–{endIdx} of {totalRows}
      </div>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page === 1}
          className={`${btnStyle(false)} disabled:opacity-30 disabled:cursor-not-allowed`}
          aria-label="Previous page"
        >
          ‹
        </button>
        {start > 1 && (
          <>
            <button onClick={() => onPageChange(1)} className={btnStyle(false)}>1</button>
            {start > 2 && <span className="text-chalk600 px-1">…</span>}
          </>
        )}
        {pages.map(p => (
          <button
            key={p}
            onClick={() => onPageChange(p)}
            className={btnStyle(p === page)}
          >
            {p}
          </button>
        ))}
        {end < totalPages && (
          <>
            {end < totalPages - 1 && <span className="text-chalk600 px-1">…</span>}
            <button onClick={() => onPageChange(totalPages)} className={btnStyle(false)}>{totalPages}</button>
          </>
        )}
        <button
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          disabled={page === totalPages}
          className={`${btnStyle(false)} disabled:opacity-30 disabled:cursor-not-allowed`}
          aria-label="Next page"
        >
          ›
        </button>
      </div>
    </div>
  )
}

// Inline hex colors so Tailwind purge can't drop the active state.
function StaleToggle({ active, onToggle }) {
  const ringColor   = active ? '#f59e0b66' : '#3a3a3a'
  const bgColor     = active ? '#f59e0b1a' : 'transparent'
  const labelColor  = active ? '#fbbf24' : '#a3a3a3'
  const boxBorder   = active ? '#fbbf24' : '#525252'
  const boxFill     = active ? '#fbbf24' : 'transparent'

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={active}
      className="w-full min-w-0 sm:w-auto sm:max-w-sm px-3 py-1.5 rounded border text-left transition-colors"
      style={{ borderColor: ringColor, backgroundColor: bgColor }}
    >
      <div className="flex items-start gap-2">
        <span
          className="mt-0.5 inline-flex shrink-0 items-center justify-center w-3 h-3 rounded-sm border"
          style={{ borderColor: boxBorder, backgroundColor: boxFill }}
        >
          {active && (
            <svg viewBox="0 0 12 12" className="w-2.5 h-2.5" aria-hidden="true">
              <path
                d="M2 6.5 L5 9.5 L10 3.5"
                fill="none"
                stroke="#1a1a1a"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </span>
        <span className="min-w-0 font-mono text-xs leading-snug" style={{ color: labelColor }}>
          Show pitchers outside the freshness window
        </span>
      </div>
      <div className="font-mono text-[10px] mt-0.5 ml-5 leading-snug text-chalk600">
        Includes pitchers outside the active freshness window
      </div>
    </button>
  )
}
