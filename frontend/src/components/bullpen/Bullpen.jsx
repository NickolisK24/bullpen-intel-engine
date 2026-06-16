import { useState, useEffect, useMemo, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getFatigueScores, getTeams, recalculateFatigue } from '../../utils/api'
import { LoadingPane, ErrorState, EmptyState, FatigueBar, RiskBadge, SectionHeader } from '../UI'
import { riskColor } from '../../utils/formatters'
import PitcherDetail from './PitcherDetail'
import TeamComparison from './TeamComparison'
import TonightsBullpenBoard from './board/TonightsBullpenBoard'
import TeamBullpenComparison from './board/TeamBullpenComparison'
import { getBullpenEmptyState } from './emptyState'
import AvailabilityBadge from './AvailabilityBadge'
import PitcherSearch from './PitcherSearch'
import {
  AVAILABILITY_FILTERS,
  filterRowsByAvailability,
  getAvailabilityFilterCounts,
  getRowAvailabilityStatus,
} from './availabilityView'

const RISK_FILTERS = ['ALL', 'CRITICAL', 'HIGH', 'MODERATE', 'LOW']
const VIEW_MODES   = [
  { id: 'board',    label: 'Team Board' },
  { id: 'compare',  label: 'Compare Bullpens' },
  { id: 'pitchers', label: 'All Pitchers' },
  { id: 'teams',    label: 'All Teams' },
]
const PAGE_SIZE = 50

const VALID_VIEWS = new Set(VIEW_MODES.map(m => m.id))

export default function Bullpen() {
  const location = useLocation()
  const navigate = useNavigate()
  // Allow deep-links to a specific tab and team, e.g. the dashboard Quick Actions
  // (/bullpen?view=compare) and the landscape team drilldown
  // (/bullpen?view=board&team=SF). Defaults to Tonight's Board.
  const searchParams = new URLSearchParams(location.search)
  const requestedView = searchParams.get('view')
  const requestedTeam = searchParams.get('team')
  const requestedPitcher = searchParams.get('pitcher')
  const requestedPitcherId = Number.parseInt(requestedPitcher || '', 10)
  const hasRequestedPitcher = Number.isFinite(requestedPitcherId) && requestedPitcherId > 0
  const [viewMode, setViewMode]           = useState(VALID_VIEWS.has(requestedView) ? requestedView : 'board')
  const [selectedTeam, setSelectedTeam]   = useState(null)
  const [riskFilter, setRiskFilter]       = useState('ALL')
  const [selectedPitcher, setSelected]    = useState(null)
  const [recalcing, setRecalcing]         = useState(false)
  const [sortBy, setSortBy]               = useState('score')
  const [includeStale, setIncludeStale]   = useState(false)
  const [availabilityFilter, setAvailabilityFilter] = useState('ALL')
  const boardDetailRegionRef = useRef(null)
  const showBoardDetail = viewMode === 'board' && selectedPitcher

  const teams    = useFetch(getTeams)
  const allScores = useFetch(
    () => {
      const params = { limit: 750, include_stale: includeStale, with_meta: true }
      if (selectedTeam) params.team_id = selectedTeam
      return getFatigueScores(params)
    },
    [selectedTeam, includeStale]
  )

  const handleRecalculate = async () => {
    setRecalcing(true)
    try {
      await recalculateFatigue()
      await allScores.refetch()
    } finally {
      setRecalcing(false)
    }
  }

  useEffect(() => {
    if (
      viewMode === 'board'
      && hasRequestedPitcher
      && selectedPitcher?.pitcher_id !== requestedPitcherId
    ) {
      setSelected({ pitcher_id: requestedPitcherId })
    }
  }, [hasRequestedPitcher, requestedPitcherId, selectedPitcher?.pitcher_id, viewMode])

  useEffect(() => {
    if (showBoardDetail) {
      boardDetailRegionRef.current?.focus()
    }
  }, [showBoardDetail, selectedPitcher?.pitcher_id])

  const handlePitcherSearchSelect = (result) => {
    if (!result?.player_id) return
    const nextSearchParams = new URLSearchParams(location.search)
    nextSearchParams.set('view', 'board')
    nextSearchParams.set('pitcher', String(result.player_id))
    setSelected({
      pitcher_id: result.player_id,
      pitcher: {
        full_name: result.player_name,
        team_name: result.team_name,
        team_abbreviation: result.team_abbreviation,
      },
    })
    navigate(`${location.pathname}?${nextSearchParams.toString()}`)
  }

  const closeSelectedPitcher = () => {
    const nextSearchParams = new URLSearchParams(location.search)
    nextSearchParams.delete('pitcher')
    const nextQuery = nextSearchParams.toString()
    setSelected(null)
    navigate(`${location.pathname}${nextQuery ? `?${nextQuery}` : ''}`, { replace: true })
  }

  return (
    <div className={`p-4 sm:p-6 lg:p-8 mx-auto ${selectedPitcher ? 'max-w-[100rem]' : 'max-w-7xl'}`}>
      <SectionHeader
        title="Bullpen"
        subtitle="Team-specific bullpen analysis from latest completed data - current availability, stress, and role context"
        action={
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex gap-1 bg-chalk/30 p-1 rounded-lg border border-dirt">
              {VIEW_MODES.map(m => (
                <button
                  key={m.id}
                  onClick={() => setViewMode(m.id)}
                  className={`px-3 py-1.5 rounded text-xs font-mono transition-all ${
                    viewMode === m.id
                      ? 'bg-chalk border-dirt text-chalk200 shadow'
                      : 'text-chalk400 hover:text-chalk200'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
            {viewMode === 'pitchers' && (
              <StaleToggle
                active={includeStale}
                onToggle={() => setIncludeStale(v => !v)}
              />
            )}
            {viewMode === 'pitchers' && (
              <button
                onClick={handleRecalculate}
                disabled={recalcing}
                className="px-4 py-2 bg-amber/10 border border-amber/30 rounded text-amber text-xs font-mono hover:bg-amber/20 transition-colors disabled:opacity-40"
              >
                {recalcing ? '⟳ Recalculating...' : '⟳ Recalculate'}
              </button>
            )}
          </div>
        }
      />

      {viewMode === 'board' ? (
        <>
          <PitcherSearch onSelectPitcher={handlePitcherSearchSelect} />
          <TonightsBullpenBoard teams={teams} requestedTeam={requestedTeam} />
          {showBoardDetail && (
            <div
              ref={boardDetailRegionRef}
              tabIndex={-1}
              role="region"
              aria-label={`Selected pitcher detail for ${selectedPitcher.pitcher?.full_name ?? 'pitcher'}`}
              className="fixed inset-0 z-40 overflow-y-auto bg-field/95 p-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-amber/70 lg:p-6"
            >
              <div className="mx-auto max-w-5xl">
                <PitcherDetail pitcherId={selectedPitcher.pitcher_id} onClose={closeSelectedPitcher} />
              </div>
            </div>
          )}
        </>
      ) : viewMode === 'compare' ? (
        <TeamBullpenComparison teams={teams} />
      ) : viewMode === 'teams' ? (
        <TeamComparison />
      ) : (
        <PitcherView
          teams={teams}
          allScores={allScores}
          selectedTeam={selectedTeam}
          setSelectedTeam={setSelectedTeam}
          riskFilter={riskFilter}
          setRiskFilter={setRiskFilter}
          selectedPitcher={selectedPitcher}
          setSelected={setSelected}
          sortBy={sortBy}
          setSortBy={setSortBy}
          includeStale={includeStale}
          availabilityFilter={availabilityFilter}
          setAvailabilityFilter={setAvailabilityFilter}
        />
      )}
    </div>
  )
}

function PitcherView({
  teams, allScores,
  selectedTeam, setSelectedTeam,
  riskFilter, setRiskFilter,
  selectedPitcher, setSelected,
  sortBy, setSortBy,
  includeStale,
  availabilityFilter, setAvailabilityFilter,
}) {
  const [page, setPage] = useState(1)
  const [searchTerm, setSearchTerm] = useState('')
  const detailRegionRef = useRef(null)

  // Compute counts from the full dataset, BEFORE filtering — tab labels
  // describe what's available, not what's currently shown.
  const fatiguePayload = allScores.data
  const allRows = Array.isArray(fatiguePayload) ? fatiguePayload : (fatiguePayload?.data || [])
  const meta = Array.isArray(fatiguePayload) ? null : fatiguePayload?.meta
  const counts = { ALL: allRows.length, CRITICAL: 0, HIGH: 0, MODERATE: 0, LOW: 0 }
  allRows.forEach(r => { if (counts[r.risk_level] != null) counts[r.risk_level]++ })
  const availabilityCounts = getAvailabilityFilterCounts(allRows)
  const selectedTeamInfo = (teams.data || []).find(t => t.team_id === selectedTeam)
  const selectedTeamLabel = selectedTeamInfo?.team_abbreviation || selectedTeamInfo?.team_name
  const normalizedSearch = searchTerm.trim().toLowerCase()

  // Filter by risk/search for actual display. Team and freshness are applied
  // by the backend so metadata can explain when those filters exclude data.
  const availabilityRows = filterRowsByAvailability(allRows, availabilityFilter)
  const rows = availabilityRows.filter(r => {
    if (riskFilter !== 'ALL' && r.risk_level !== riskFilter) return false
    if (!normalizedSearch) return true
    const haystack = [
      r.pitcher?.full_name,
      r.pitcher?.team_name,
      r.pitcher?.team_abbreviation,
      r.risk_level,
      getRowAvailabilityStatus(r),
    ].filter(Boolean).join(' ').toLowerCase()
    return haystack.includes(normalizedSearch)
  })

  // Sort
  const sorted = useMemo(() => [...rows].sort((a, b) => {
    if (sortBy === 'score')   return b.raw_score - a.raw_score
    if (sortBy === 'name')    return a.pitcher?.full_name?.localeCompare(b.pitcher?.full_name)
    if (sortBy === 'rest')    return (a.days_since_last_appearance ?? 99) - (b.days_since_last_appearance ?? 99)
    if (sortBy === 'pitches') return b.pitches_last_7_days - a.pitches_last_7_days
    return 0
  }), [rows, sortBy])

  // Pagination math
  const totalRows  = sorted.length
  const totalPages = Math.max(1, Math.ceil(totalRows / PAGE_SIZE))
  const safePage   = Math.min(page, totalPages)
  const startIdx   = (safePage - 1) * PAGE_SIZE
  const endIdx     = Math.min(startIdx + PAGE_SIZE, totalRows)
  const visible    = sorted.slice(startIdx, endIdx)
  const emptyState = getBullpenEmptyState({
    allRowsCount: allRows.length,
    visibleRowsCount: sorted.length,
    meta,
    includeStale,
    selectedTeam,
    selectedTeamLabel,
    riskFilter,
    availabilityFilter,
    searchTerm,
  })

  // Reset page to 1 when filters change (so filtering doesn't drop you onto an empty page)
  useEffect(() => { setPage(1) }, [riskFilter, availabilityFilter, selectedTeam, sortBy, searchTerm, includeStale])

  useEffect(() => {
    if (selectedPitcher) {
      detailRegionRef.current?.focus()
    }
  }, [selectedPitcher])

  const toggleSelectedPitcher = (row) => {
    setSelected(selectedPitcher?.pitcher_id === row.pitcher_id ? null : row)
  }

  const handlePitcherRowKeyDown = (event, row) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggleSelectedPitcher(row)
    }
  }

  const thStyle = (key) =>
    `cursor-pointer select-none ${sortBy === key ? 'text-amber' : 'text-chalk400'} hover:text-chalk200 transition-colors`

  return (
    <>
      {/* Team filter pills */}
      <div className="flex flex-wrap gap-2 mb-6 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
        <button
          onClick={() => setSelectedTeam(null)}
          className={`px-3 py-1.5 rounded border text-xs font-mono transition-all ${!selectedTeam ? 'bg-amber/10 border-amber/40 text-amber' : 'border-dirt text-chalk400 hover:border-chalk400'}`}
        >
          All Teams
        </button>
        {(teams.data || []).map(t => (
          <button
            key={t.team_id}
            onClick={() => setSelectedTeam(t.team_id)}
            className={`px-3 py-1.5 rounded border text-xs font-mono transition-all ${selectedTeam === t.team_id ? 'bg-amber/10 border-amber/40 text-amber' : 'border-dirt text-chalk400 hover:border-chalk400'}`}
          >
            {t.team_abbreviation}
          </button>
        ))}
      </div>

      {/* Risk/search filters */}
      <div className="flex flex-col gap-3 mb-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-1 bg-chalk/30 p-1 rounded-lg w-fit border border-dirt">
          {RISK_FILTERS.map(f => (
            <button
              key={f}
              onClick={() => setRiskFilter(f)}
              className={`px-3 py-1.5 rounded text-xs font-mono transition-all ${riskFilter === f ? 'bg-chalk border-dirt text-chalk200 shadow' : 'text-chalk400 hover:text-chalk200'}`}
            >
              {f} <span className="opacity-60">({counts[f] ?? 0})</span>
            </button>
          ))}
        </div>
        <input
          type="search"
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          aria-label="Search pitchers"
          placeholder="Search pitcher"
          className="w-full sm:w-64 rounded border border-dirt bg-field/70 px-3 py-2 font-mono text-xs text-chalk200 outline-none transition-colors placeholder:text-chalk600 focus:border-amber/50"
        />
      </div>

      {/* Availability filter */}
      <div className="mb-5 flex flex-wrap gap-1 rounded-lg border border-dirt bg-chalk/30 p-1 w-fit max-w-full">
        {AVAILABILITY_FILTERS.map(f => (
          <button
            key={f}
            onClick={() => setAvailabilityFilter(f)}
            className={`px-3 py-1.5 rounded text-xs font-mono transition-all ${
              availabilityFilter === f
                ? 'bg-chalk border-dirt text-chalk200 shadow'
                : 'text-chalk400 hover:text-chalk200'
            }`}
          >
            {f === 'ALL' ? 'All' : f}{' '}
            <span className="opacity-60">({availabilityCounts[f] ?? 0})</span>
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-6 2xl:flex-row 2xl:items-start">
        {/* Main table */}
        <div className="min-w-0 flex-1 card overflow-hidden transition-all duration-300">
          {allScores.loading ? (
            <LoadingPane message="Loading fatigue data..." />
          ) : allScores.error ? (
            <ErrorState message={allScores.error} onRetry={allScores.refetch} />
          ) : sorted.length === 0 ? (
            <EmptyState title={emptyState.title} subtitle={emptyState.subtitle} />
          ) : (
            <>
              <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th className={thStyle('name')} onClick={() => setSortBy('name')}>Pitcher {sortBy === 'name' && '↑'}</th>
                    <th className="text-chalk400">Team</th>
                    <th className={thStyle('score')} onClick={() => setSortBy('score')}>Score {sortBy === 'score' && '↓'}</th>
                    <th className="text-chalk400 hidden md:table-cell">Fatigue</th>
                    <th className="text-chalk400">Availability</th>
                    <th className={thStyle('pitches')} onClick={() => setSortBy('pitches')}>P/7d {sortBy === 'pitches' && '↓'}</th>
                    <th className={thStyle('rest')} onClick={() => setSortBy('rest')}>Rest {sortBy === 'rest' && '↑'}</th>
                    <th className="text-chalk400">App/7d</th>
                    <th className="text-chalk400">Risk</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map(row => (
                    <tr
                      key={row.id || row.pitcher_id}
                      onClick={() => toggleSelectedPitcher(row)}
                      onKeyDown={(event) => handlePitcherRowKeyDown(event, row)}
                      tabIndex={0}
                      aria-selected={selectedPitcher?.pitcher_id === row.pitcher_id}
                      aria-label={`Open pitcher detail for ${row.pitcher?.full_name ?? 'pitcher'}`}
                      className={`${selectedPitcher?.pitcher_id === row.pitcher_id ? 'bg-amber/5 border-l-2 border-l-amber' : ''} focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-amber/70`}
                    >
                      <td className="text-chalk200 font-medium">{row.pitcher?.full_name ?? '—'}</td>
                      <td className="font-mono text-xs text-chalk400">{row.pitcher?.team_abbreviation}</td>
                      <td className={`font-mono font-semibold ${riskColor(row.risk_level)}`}>{Math.round(row.raw_score ?? 0)}</td>
                      <td className="hidden md:table-cell w-28">
                        <FatigueBar score={row.raw_score} height="h-1" />
                      </td>
                      <td><AvailabilityBadge availability={row.availability} showDataState /></td>
                      <td className="font-mono text-xs text-chalk200">{row.pitches_last_7_days ?? 0}</td>
                      <td className="font-mono text-xs text-chalk400">{row.days_since_last_appearance != null ? `${row.days_since_last_appearance}d` : '---'}</td>
                      <td className="font-mono text-xs text-chalk200">{row.appearances_last_7 ?? 0}</td>
                      <td><RiskBadge level={row.risk_level} /></td>
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

        {/* Detail panel — side column on desktop, full-screen overlay on mobile
            so selecting a pitcher always reveals the detail (it was hidden
            below the lg breakpoint before). PitcherDetail's header ✕ closes it. */}
        {selectedPitcher && (
          <div
            ref={detailRegionRef}
            tabIndex={-1}
            role="region"
            aria-label={`Selected pitcher detail for ${selectedPitcher.pitcher?.full_name ?? 'pitcher'}`}
            className="fixed inset-0 z-40 overflow-y-auto bg-field/95 p-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-amber/70 lg:static lg:inset-auto lg:z-auto lg:w-full lg:max-w-none lg:overflow-visible lg:bg-transparent lg:p-0 2xl:w-[36rem] 2xl:shrink-0"
          >
            <PitcherDetail pitcherId={selectedPitcher.pitcher_id} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>
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
    `min-w-[2rem] px-2 py-1 rounded font-mono text-xs transition-all ${
      active
        ? 'bg-amber/20 border border-amber/40 text-amber'
        : 'border border-dirt text-chalk400 hover:text-chalk200 hover:border-chalk400'
    }`

  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-dirt bg-chalk/20">
      <div className="text-chalk600 text-xs font-mono">
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
      className="px-3 py-1.5 rounded border text-left transition-colors"
      style={{ borderColor: ringColor, backgroundColor: bgColor }}
    >
      <div className="flex items-center gap-2">
        <span
          className="inline-flex items-center justify-center w-3 h-3 rounded-sm border"
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
        <span className="font-mono text-xs" style={{ color: labelColor }}>
          Show pitchers with unclear recent workload
        </span>
      </div>
      <div className="font-mono text-[10px] mt-0.5 ml-5 text-chalk600">
        Includes pitchers outside the active freshness window
      </div>
    </button>
  )
}
