import { useState } from 'react'
import { useFetch } from '../../hooks/useFetch'
import { getFatigueScores, getTeams, getTeamBullpen, recalculateFatigue } from '../../utils/api'
import { LoadingPane, ErrorState, FatigueBar, RiskBadge, SectionHeader, StatCard, Divider } from '../UI'
import { riskColor, fmtIP, fmtDate, daysAgo } from '../../utils/formatters'
import PitcherDetail from './PitcherDetail'

const RISK_FILTERS = ['ALL', 'CRITICAL', 'HIGH', 'MODERATE', 'LOW']

export default function Bullpen() {
  const [selectedTeam, setSelectedTeam]   = useState(null)
  const [riskFilter, setRiskFilter]       = useState('ALL')
  const [selectedPitcher, setSelected]    = useState(null)
  const [recalcing, setRecalcing]         = useState(false)
  const [sortBy, setSortBy]               = useState('score')

  const teams    = useFetch(getTeams)
  const allScores = useFetch(
    () => selectedTeam
      ? getTeamBullpen(selectedTeam).then(rows => rows.map(r => ({ ...r.fatigue, pitcher: r.pitcher })).filter(r => r && r.raw_score != null))
      : getFatigueScores({ limit: 200 }),
    [selectedTeam]
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

  // Filter by risk
  const rows = (allScores.data || []).filter(r => {
    if (riskFilter === 'ALL') return true
    return r.risk_level === riskFilter
  })

  // Sort
  const sorted = [...rows].sort((a, b) => {
    if (sortBy === 'score')  return b.raw_score - a.raw_score
    if (sortBy === 'name')   return a.pitcher?.full_name?.localeCompare(b.pitcher?.full_name)
    if (sortBy === 'rest')   return (a.days_since_last_appearance ?? 99) - (b.days_since_last_appearance ?? 99)
    if (sortBy === 'pitches') return b.pitches_last_7_days - a.pitches_last_7_days
    return 0
  })

  // Risk counts
  const counts = { ALL: rows.length, CRITICAL: 0, HIGH: 0, MODERATE: 0, LOW: 0 }
  rows.forEach(r => { if (counts[r.risk_level] != null) counts[r.risk_level]++ })

  const thStyle = (key) =>
    `cursor-pointer select-none ${sortBy === key ? 'text-amber' : 'text-chalk400'} hover:text-chalk200 transition-colors`

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <SectionHeader
        title="Bullpen"
        subtitle="Relief pitcher fatigue scoring engine"
        action={
          <button
            onClick={handleRecalculate}
            disabled={recalcing}
            className="px-4 py-2 bg-amber/10 border border-amber/30 rounded text-amber text-xs font-mono hover:bg-amber/20 transition-colors disabled:opacity-40"
          >
            {recalcing ? '⟳ Recalculating...' : '⟳ Recalculate'}
          </button>
        }
      />

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
                {sorted.map(row => (
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
          )}
        </div>

        {/* Detail panel */}
        {selectedPitcher && (
          <div className="hidden lg:block lg:w-[38%]">
            <PitcherDetail pitcherId={selectedPitcher.pitcher_id} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>
    </div>
  )
}
