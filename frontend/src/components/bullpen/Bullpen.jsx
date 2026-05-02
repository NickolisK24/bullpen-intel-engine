import { useState, useEffect, useMemo } from 'react'
import { useFetch } from '../../hooks/useFetch'
import { getFatigueScores, getTeams, getTeamBullpen, recalculateFatigue } from '../../utils/api'
import { LoadingPane, ErrorState, FatigueBar, RiskBadge, SectionHeader, StatCard, Divider } from '../UI'
import { riskColor, fmtIP, fmtDate, daysAgo } from '../../utils/formatters'
import PitcherDetail from './PitcherDetail'
import TeamComparison from './TeamComparison'

const RISK_FILTERS = ['ALL', 'CRITICAL', 'HIGH', 'MODERATE', 'LOW']
const VIEW_MODES   = [
  { id: 'pitchers', label: 'Pitchers' },
  { id: 'teams',    label: 'Team Rankings' },
]
const PAGE_SIZE = 50

export default function Bullpen() {
  const [viewMode, setViewMode]           = useState('pitchers')
  const [selectedTeam, setSelectedTeam]   = useState(null)
  const [riskFilter, setRiskFilter]       = useState('ALL')
  const [selectedPitcher, setSelected]    = useState(null)
  const [recalcing, setRecalcing]         = useState(false)
  const [sortBy, setSortBy]               = useState('score')
  const [includeStale, setIncludeStale]   = useState(false)

  const teams    = useFetch(getTeams)
  const allScores = useFetch(
    () => selectedTeam
      ? getTeamBullpen(selectedTeam, { include_stale: includeStale })
          .then(rows => rows.map(r => ({ ...r.fatigue, pitcher: r.pitcher })).filter(r => r && r.raw_score != null))
      : getFatigueScores({ limit: 750, include_stale: includeStale }),
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

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <SectionHeader
        title="Bullpen"
        subtitle="Relief pitcher fatigue scoring engine"
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

      {viewMode === 'teams' ? (
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
}) {
  const [page, setPage] = useState(1)

  // Filter by risk
  const rows = (allScores.data || []).filter(r => {
    if (riskFilter === 'ALL') return true
    return r.risk_level === riskFilter
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

  // Reset page to 1 when filters change (so filtering doesn't drop you onto an empty page)
  useEffect(() => { setPage(1) }, [riskFilter, selectedTeam, sortBy])

  // Risk counts (always use full filtered set, not paginated)
  const counts = { ALL: rows.length, CRITICAL: 0, HIGH: 0, MODERATE: 0, LOW: 0 }
  rows.forEach(r => { if (counts[r.risk_level] != null) counts[r.risk_level]++ })

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

      {/* Risk filter tabs */}
      <div className="flex gap-1 mb-5 bg-chalk/30 p-1 rounded-lg w-fit border border-dirt">
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

      <div className="flex gap-6">
        {/* Main table */}
        <div className={`flex-1 card overflow-hidden transition-all duration-300 ${selectedPitcher ? 'lg:flex-none lg:w-[60%]' : ''}`}>
          {allScores.loading ? (
            <LoadingPane message="Loading fatigue data..." />
          ) : allScores.error ? (
            <ErrorState message={allScores.error} onRetry={allScores.refetch} />
          ) : sorted.length === 0 ? (
            <div className="p-8 text-center">
              <div className="text-4xl mb-3 opacity-20">⚾</div>
              <p className="text-chalk400 font-mono text-sm">No pitchers found</p>
              <p className="text-chalk600 text-xs mt-1 font-mono">Run <span className="text-amber">python seed.py</span> in the backend to load data</p>
            </div>
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th className={thStyle('name')} onClick={() => setSortBy('name')}>Pitcher {sortBy === 'name' && '↑'}</th>
                    <th className="text-chalk400">Team</th>
                    <th className={thStyle('score')} onClick={() => setSortBy('score')}>Score {sortBy === 'score' && '↓'}</th>
                    <th className="text-chalk400 hidden md:table-cell">Fatigue</th>
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
                      onClick={() => setSelected(selectedPitcher?.pitcher_id === row.pitcher_id ? null : row)}
                      className={selectedPitcher?.pitcher_id === row.pitcher_id ? 'bg-amber/5 border-l-2 border-l-amber' : ''}
                    >
                      <td className="text-chalk200 font-medium">{row.pitcher?.full_name ?? '—'}</td>
                      <td className="font-mono text-xs text-chalk400">{row.pitcher?.team_abbreviation}</td>
                      <td className={`font-mono font-semibold ${riskColor(row.risk_level)}`}>{Math.round(row.raw_score ?? 0)}</td>
                      <td className="hidden md:table-cell w-28">
                        <FatigueBar score={row.raw_score} height="h-1" />
                      </td>
                      <td className="font-mono text-xs text-chalk200">{row.pitches_last_7_days ?? 0}</td>
                      <td className="font-mono text-xs text-chalk400">{row.days_since_last_appearance != null ? `${row.days_since_last_appearance}d` : '---'}</td>
                      <td className="font-mono text-xs text-chalk200">{row.appearances_last_7 ?? 0}</td>
                      <td><RiskBadge level={row.risk_level} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
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

        {/* Detail panel */}
        {selectedPitcher && (
          <div className="hidden lg:block lg:w-[38%]">
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
          Show inactive pitchers
        </span>
      </div>
      <div className="font-mono text-[10px] mt-0.5 ml-5 text-chalk600">
        Includes pitchers with no games in the last 14 days
      </div>
    </button>
  )
}