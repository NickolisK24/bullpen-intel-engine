import { useEffect, useState, useCallback } from 'react'
import { getTeams, getTeamBullpen } from '../../utils/api'
import { LoadingPane, ErrorState, EmptyState } from '../UI'

// Risk tier → hex color. Inline styles only — Tailwind would purge
// any dynamically-constructed class names at build.
const RISK_COLORS = {
  LOW:      '#10b981',
  MODERATE: '#fbbf24',
  HIGH:     '#fb923c',
  CRITICAL: '#ef4444',
}

// Same thresholds the backend uses in services/fatigue.py so the
// UI label matches the stored risk_level even on empty/edge teams.
const scoreToTier = (score) => {
  if (score == null) return null
  if (score <= 25) return 'LOW'
  if (score <= 50) return 'MODERATE'
  if (score <= 80) return 'HIGH'
  return 'CRITICAL'
}

const SORT_KEYS = {
  avg:      { label: 'Avg Score', dir: 'desc' },
  team:     { label: 'Team',      dir: 'asc'  },
  critical: { label: 'CRITICAL',  dir: 'desc' },
  high:     { label: 'HIGH',      dir: 'desc' },
  moderate: { label: 'MODERATE',  dir: 'desc' },
  low:      { label: 'LOW',       dir: 'desc' },
}

export default function TeamComparison() {
  const [rows, setRows]       = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const [sortBy, setSortBy]   = useState('avg')
  const [sortDir, setSortDir] = useState('desc')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const teams = await getTeams()
      // Fan-out all 30 team requests in parallel
      const settled = await Promise.all(
        (teams || []).map(async (t) => {
          try {
            const bullpen = await getTeamBullpen(t.team_id)
            const scored  = (bullpen || [])
              .map(b => b.fatigue)
              .filter(f => f && f.raw_score != null)

            const counts = { LOW: 0, MODERATE: 0, HIGH: 0, CRITICAL: 0 }
            scored.forEach(f => {
              if (counts[f.risk_level] != null) counts[f.risk_level] += 1
            })

            const avg = scored.length
              ? scored.reduce((s, f) => s + (f.raw_score || 0), 0) / scored.length
              : null

            return {
              team_id:           t.team_id,
              team_name:         t.team_name,
              team_abbreviation: t.team_abbreviation,
              pitcher_count:     t.pitcher_count,
              scored_count:      scored.length,
              avg_score:         avg,
              avg_tier:          scoreToTier(avg),
              counts,
            }
          } catch (err) {
            return {
              team_id:           t.team_id,
              team_name:         t.team_name,
              team_abbreviation: t.team_abbreviation,
              pitcher_count:     t.pitcher_count,
              scored_count:      0,
              avg_score:         null,
              avg_tier:          null,
              counts:            { LOW: 0, MODERATE: 0, HIGH: 0, CRITICAL: 0 },
              _error:            err.message || 'Failed to load',
            }
          }
        })
      )
      setRows(settled)
    } catch (err) {
      setError(err.message || 'Failed to load teams')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleSort = (key) => {
    if (sortBy === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(key)
      setSortDir(SORT_KEYS[key]?.dir ?? 'desc')
    }
  }

  if (loading) return <LoadingPane message="Loading 30 team bullpens..." />
  if (error)   return <ErrorState message={error} onRetry={load} />
  if (!rows.length) return <EmptyState title="No teams found" subtitle="Run the seeder to load team data." />

  const sorted = [...rows].sort((a, b) => {
    const dir = sortDir === 'asc' ? 1 : -1
    let av, bv
    if (sortBy === 'team') {
      av = a.team_name || ''
      bv = b.team_name || ''
      return av.localeCompare(bv) * dir
    }
    if (sortBy === 'avg') {
      av = a.avg_score ?? -Infinity
      bv = b.avg_score ?? -Infinity
    } else {
      const level = sortBy.toUpperCase()
      av = a.counts[level] ?? 0
      bv = b.counts[level] ?? 0
    }
    return (av - bv) * dir
  })

  const arrow = (key) => {
    if (sortBy !== key) return ''
    return sortDir === 'asc' ? ' ↑' : ' ↓'
  }

  const headerCls = (key) =>
    `cursor-pointer select-none transition-colors ${
      sortBy === key ? 'text-amber' : 'text-chalk400 hover:text-chalk200'
    }`

  return (
    <div className="card overflow-hidden">
      <div className="card-header">
        <div>
          <span className="font-mono text-xs text-chalk400 uppercase tracking-widest">
            30-Team Bullpen Rankings
          </span>
          <div className="text-chalk600 text-[11px] font-mono mt-0.5">
            Sorted by average fatigue — click a header to re-sort
          </div>
        </div>
        <button
          onClick={load}
          className="px-3 py-1.5 bg-amber/10 border border-amber/30 rounded text-amber text-xs font-mono hover:bg-amber/20 transition-colors"
        >
          ⟳ Refresh
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th className="w-8 text-chalk600">#</th>
              <th className={headerCls('team')}      onClick={() => handleSort('team')}>Team{arrow('team')}</th>
              <th className={`text-right ${headerCls('avg')}`} onClick={() => handleSort('avg')}>Avg Fatigue{arrow('avg')}</th>
              <th className={`text-right ${headerCls('critical')}`} onClick={() => handleSort('critical')}>CRITICAL{arrow('critical')}</th>
              <th className={`text-right ${headerCls('high')}`}     onClick={() => handleSort('high')}>HIGH{arrow('high')}</th>
              <th className={`text-right ${headerCls('moderate')}`} onClick={() => handleSort('moderate')}>MODERATE{arrow('moderate')}</th>
              <th className={`text-right ${headerCls('low')}`}      onClick={() => handleSort('low')}>LOW{arrow('low')}</th>
              <th className="text-right text-chalk400">Scored</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => {
              const tierColor = row.avg_tier ? RISK_COLORS[row.avg_tier] : null
              return (
                <tr key={row.team_id}>
                  <td className="font-mono text-xs text-chalk600">{i + 1}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-chalk600 w-8 shrink-0">
                        {row.team_abbreviation}
                      </span>
                      <span className="text-chalk200 font-medium truncate">{row.team_name}</span>
                    </div>
                    {row._error && (
                      <div className="text-red-400/80 text-[10px] font-mono mt-0.5">
                        {row._error}
                      </div>
                    )}
                  </td>
                  <td className="text-right">
                    {row.avg_score != null ? (
                      <span
                        className="inline-flex items-center justify-center px-2.5 py-1 rounded font-mono font-semibold text-sm min-w-[56px]"
                        style={{
                          backgroundColor: `${tierColor}22`,
                          color: tierColor,
                          border: `1px solid ${tierColor}55`,
                        }}
                      >
                        {row.avg_score.toFixed(1)}
                      </span>
                    ) : (
                      <span className="text-chalk600 font-mono text-xs">---</span>
                    )}
                  </td>
                  <td className="text-right">
                    <CountCell count={row.counts.CRITICAL} color={RISK_COLORS.CRITICAL} />
                  </td>
                  <td className="text-right">
                    <CountCell count={row.counts.HIGH} color={RISK_COLORS.HIGH} />
                  </td>
                  <td className="text-right">
                    <CountCell count={row.counts.MODERATE} color={RISK_COLORS.MODERATE} />
                  </td>
                  <td className="text-right">
                    <CountCell count={row.counts.LOW} color={RISK_COLORS.LOW} />
                  </td>
                  <td className="text-right font-mono text-xs text-chalk400">
                    {row.scored_count}<span className="text-chalk600">/{row.pitcher_count ?? '—'}</span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CountCell({ count, color }) {
  if (!count) {
    return <span className="font-mono text-xs text-chalk600">0</span>
  }
  return (
    <span
      className="inline-flex items-center justify-center font-mono font-semibold text-xs rounded-full w-6 h-6"
      style={{
        backgroundColor: `${color}1f`,
        color,
        border: `1px solid ${color}55`,
      }}
    >
      {count}
    </span>
  )
}
