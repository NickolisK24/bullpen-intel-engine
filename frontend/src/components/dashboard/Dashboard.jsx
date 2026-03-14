import { useFetch } from '../../hooks/useFetch'
import { getBullpenOverview, getFatigueScores, getPipelineOverview } from '../../utils/api'
import { StatCard, LoadingPane, ErrorState, FatigueBar, RiskBadge, SectionHeader } from '../UI'
import { riskColor } from '../../utils/formatters'
import { Link } from 'react-router-dom'
import SeasonBanner from './SeasonBanner'

// Defined outside component so Tailwind scanner can see these classes
const RISK_CONFIG = {
  LOW:      { bg: '#10b981', text: 'text-emerald-400', dot: '#10b981' },
  MODERATE: { bg: '#fbbf24', text: 'text-amber-400',   dot: '#fbbf24' },
  HIGH:     { bg: '#fb923c', text: 'text-orange-400',  dot: '#fb923c' },
  CRITICAL: { bg: '#ef4444', text: 'text-red-400',     dot: '#ef4444' },
}

const LEVELS = ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']

export default function Dashboard() {
  const overview   = useFetch(getBullpenOverview)
  const topFatigue = useFetch(() => getFatigueScores({ limit: 8, risk_level: '' }))
  const pipeline   = useFetch(getPipelineOverview)

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Hero */}
      <div className="mb-10 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
        <div className="relative overflow-hidden rounded-xl border border-dirt bg-dugout p-8 bg-stadium-glow">
          <div className="absolute inset-0 bg-grid-lines bg-grid-lines opacity-100 pointer-events-none" />
          <div className="relative z-10">
            <div className="font-mono text-xs text-amber/60 uppercase tracking-widest mb-2">Command Center</div>
            <h1 className="font-display text-6xl tracking-wider text-chalk100 leading-none mb-3">
              BASEBALL<span className="text-gradient-amber">OS</span>
            </h1>
            <p className="text-chalk400 text-sm max-w-lg font-mono leading-relaxed">
              Bullpen fatigue modeling · Prospect pipeline tracking · Portfolio layer.<br/>
              Built to think like someone already in the room.
            </p>
            <div className="mt-4">
              <SeasonBanner season="2024" isLive={false} />
            </div>
          </div>
          <div className="absolute right-8 top-1/2 -translate-y-1/2 opacity-5">
            <div className="font-display text-[120px] tracking-widest text-white leading-none select-none">⚾</div>
          </div>
        </div>
      </div>

      {/* Overview stats */}
      {overview.loading ? (
        <LoadingPane label="Loading stats..." />
      ) : overview.error ? (
        <ErrorState message={overview.error} onRetry={overview.refetch} />
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
          <StatCard label="Active Pitchers" value={overview.data?.total_pitchers} icon="⚾" delay={100} />
          <StatCard label="Game Logs" value={overview.data?.total_game_logs?.toLocaleString()} icon="📋" delay={150} />
          <StatCard label="Avg Fatigue Score" value={overview.data?.avg_fatigue_score} sub="out of 100" accent delay={200} />
          <StatCard label="Critical / High" value={`${overview.data?.risk_breakdown?.CRITICAL ?? 0} / ${overview.data?.risk_breakdown?.HIGH ?? 0}`} icon="🔥" delay={250} />
        </div>
      )}

      {/* Risk breakdown bar */}
      {overview.data?.risk_breakdown && (
        <div className="card p-5 mb-8 animate-fade-up opacity-0 delay-3" style={{ animationFillMode: 'forwards' }}>
          <div className="text-chalk400 font-mono text-xs uppercase tracking-widest mb-4">Risk Distribution</div>

          {/* Bar — inline bg colors so Tailwind purge can't remove them */}
          <div className="flex h-3 rounded-full overflow-hidden w-full">
            {LEVELS.map((level) => {
              const count = overview.data.risk_breakdown[level] || 0
              const total = overview.data.scored_pitchers || 1
              const pct   = (count / total) * 100
              if (pct === 0) return null
              return (
                <div
                  key={level}
                  className="flex-none transition-all duration-700"
                  style={{ width: `${pct}%`, backgroundColor: RISK_CONFIG[level].bg }}
                  title={`${level}: ${count}`}
                />
              )
            })}
          </div>

          {/* Legend */}
          <div className="flex gap-5 mt-3">
            {LEVELS.map((level) => {
              const count = overview.data.risk_breakdown[level] || 0
              return (
                <div key={level} className="flex items-center gap-1.5">
                  <div
                    className="h-2 w-2 rounded-full flex-none"
                    style={{ backgroundColor: RISK_CONFIG[level].dot }}
                  />
                  <span className={`font-mono text-xs font-semibold ${RISK_CONFIG[level].text}`}>{count}</span>
                  <span className="text-chalk600 text-xs font-mono">{level}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Most fatigued pitchers */}
        <div className="card animate-fade-up opacity-0 delay-4" style={{ animationFillMode: 'forwards' }}>
          <div className="card-header">
            <span className="font-mono text-xs text-chalk400 uppercase tracking-widest">🔥 Most Fatigued</span>
            <Link to="/bullpen" className="text-amber text-xs font-mono hover:underline">View all →</Link>
          </div>
          <div className="p-0">
            {topFatigue.loading ? (
              <LoadingPane label="Loading..." />
            ) : topFatigue.error ? (
              <ErrorState message={topFatigue.error} />
            ) : !topFatigue.data?.length ? (
              <div className="p-6 text-chalk400 text-sm text-center font-mono">No data — run the seeder first</div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Pitcher</th>
                    <th>Team</th>
                    <th>Score</th>
                    <th>Risk</th>
                  </tr>
                </thead>
                <tbody>
                  {topFatigue.data.slice(0, 8).map((row) => (
                    <tr key={row.id}>
                      <td className="text-chalk200 font-medium">{row.pitcher?.full_name}</td>
                      <td className="text-chalk400 font-mono text-xs">{row.pitcher?.team_abbreviation}</td>
                      <td className="w-32">
                        <FatigueBar score={row.raw_score} showLabel height="h-1" />
                      </td>
                      <td><RiskBadge level={row.risk_level} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Pipeline snapshot */}
        <div className="card animate-fade-up opacity-0 delay-5" style={{ animationFillMode: 'forwards' }}>
          <div className="card-header">
            <span className="font-mono text-xs text-chalk400 uppercase tracking-widest">📈 Pipeline Snapshot</span>
            <Link to="/prospects" className="text-amber text-xs font-mono hover:underline">View all →</Link>
          </div>
          {pipeline.loading ? (
            <LoadingPane label="Loading..." />
          ) : pipeline.error ? (
            <ErrorState message={pipeline.error} />
          ) : (
            <div className="p-5">
              <div className="grid grid-cols-3 gap-3 mb-5">
                {['ROK','A','A+','AA','AAA','MLB'].map((lvl) => {
                  const count  = pipeline.data?.by_level?.[lvl] || 0
                  const colors = { ROK:'text-chalk400', A:'text-ice', 'A+':'text-sky-400', AA:'text-violet-400', AAA:'text-amber', MLB:'text-emerald-400' }
                  return (
                    <div key={lvl} className="bg-chalk/40 border border-dirt rounded p-3 text-center">
                      <div className={`font-mono font-semibold text-lg ${colors[lvl]}`}>{count}</div>
                      <div className="text-chalk600 text-xs font-mono mt-0.5">{lvl}</div>
                    </div>
                  )
                })}
              </div>

              <div className="text-chalk600 font-mono text-xs uppercase tracking-widest mb-3">Top Rated</div>
              <div className="space-y-2.5">
                {pipeline.data?.top_10?.slice(0, 5).map((p, i) => (
                  <div key={p.id} className="flex items-center gap-3">
                    <span className="font-mono text-xs text-chalk600 w-4">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-chalk200 text-sm font-medium truncate">{p.full_name}</div>
                      <div className="text-chalk600 text-xs font-mono">{p.team_abbreviation} · {p.position} · {p.current_level}</div>
                    </div>
                    <div className="font-mono text-amber font-semibold text-sm">{p.grades?.overall ?? '--'}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
        {[
          { to: '/bullpen', icon: '🔥', title: 'Bullpen Module', desc: 'Fatigue heatmap, team bullpens, pitcher detail' },
          { to: '/prospects', icon: '📈', title: 'Pipeline Module', desc: 'Prospect tracker, development arcs, comparisons' },
          { to: '/portfolio', icon: '⚙', title: 'Portfolio', desc: 'Methodology, projects, and contact' },
        ].map(({ to, icon, title, desc }, i) => (
          <Link key={to} to={to}
            className="card p-5 hover:border-amber/30 hover:bg-amber/5 transition-all duration-200 group animate-fade-up opacity-0"
            style={{ animationDelay: `${600 + i * 80}ms`, animationFillMode: 'forwards' }}
          >
            <div className="text-2xl mb-3">{icon}</div>
            <div className="font-display text-xl tracking-wider text-chalk100 group-hover:text-amber transition-colors">{title}</div>
            <div className="text-chalk400 text-xs font-mono mt-1">{desc}</div>
          </Link>
        ))}
      </div>
    </div>
  )
}