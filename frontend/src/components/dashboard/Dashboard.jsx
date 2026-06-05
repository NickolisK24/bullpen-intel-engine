import { useState } from 'react'
import { useFetch } from '../../hooks/useFetch'
import {
  getBullpenOverview,
  getBullpenObservations,
  getFatigueScores,
  getPipelineOverview,
  getRecommendationV2BullpenState,
  getSyncStatus,
  getTeamOperationsBullpenReadiness,
} from '../../utils/api'
import { StatCard, LoadingPane, ErrorState, FatigueBar, RiskBadge, SectionHeader } from '../UI'
import { riskColor } from '../../utils/formatters'
import { Link } from 'react-router-dom'
import SeasonBanner from './SeasonBanner'
import { SyncStatusContent } from './SyncStatus'
import FatigueInsightCard from './FatigueInsightCard'
import AvailabilityDashboardSummary from './AvailabilityDashboardSummary'
import { getBullpenEmptyState } from '../bullpen/emptyState'
import OperationalReadinessSection from './OperationalReadinessSection'
import BullpenIntelligencePanel from '../observations/BullpenIntelligencePanel'

// Defined outside component so Tailwind scanner can see these classes
const RISK_CONFIG = {
  LOW:      { bg: '#10b981', text: 'text-emerald-400', dot: '#10b981' },
  MODERATE: { bg: '#fbbf24', text: 'text-amber-400',   dot: '#fbbf24' },
  HIGH:     { bg: '#fb923c', text: 'text-orange-400',  dot: '#fb923c' },
  CRITICAL: { bg: '#ef4444', text: 'text-red-400',     dot: '#ef4444' },
}

const LEVELS = ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// Format a 'YYYY-MM-DD' game date as "Sep 10, 2025" (no timezone drift).
const fmtThroughDate = (ymd) => {
  if (!ymd) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd)
  if (!m) return null
  return `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}`
}

function DashboardDisclosure({
  title,
  summary,
  children,
  initiallyExpanded = false,
}) {
  const [expanded, setExpanded] = useState(initiallyExpanded)
  const id = `${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-details`

  return (
    <section className="card mb-5 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="font-mono text-xs uppercase tracking-widest text-chalk400">{title}</h2>
          {summary && <p className="mt-1 text-xs leading-relaxed text-chalk600">{summary}</p>}
        </div>
        <button
          type="button"
          className="rounded border border-dirt bg-field/60 px-3 py-2 text-left font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus:ring-2 focus:ring-amber/60 focus:ring-offset-2 focus:ring-offset-dugout"
          aria-expanded={expanded}
          aria-controls={id}
          onClick={() => setExpanded(current => !current)}
        >
          {expanded ? `Hide ${title}` : `View ${title}`}
        </button>
      </div>
      {expanded && (
        <div id={id} className="mt-4">
          {children}
        </div>
      )}
    </section>
  )
}

export default function Dashboard() {
  const overview   = useFetch(getBullpenOverview)
  const topFatigue = useFetch(() => getFatigueScores({ limit: 8, risk_level: '', with_meta: true }))
  const pipeline   = useFetch(getPipelineOverview)
  const sync       = useFetch(getSyncStatus)
  const v2BullpenState = useFetch(() => getRecommendationV2BullpenState({ limit: 750 }))
  const teamOperationsReadiness = useFetch(() => getTeamOperationsBullpenReadiness({ include_details: true }))
  const bullpenObservations = useFetch(getBullpenObservations)
  const topFatigueRows = Array.isArray(topFatigue.data) ? topFatigue.data : (topFatigue.data?.data || [])
  const topFatigueMeta = Array.isArray(topFatigue.data) ? null : topFatigue.data?.meta
  const topFatigueEmpty = getBullpenEmptyState({
    allRowsCount: topFatigueRows.length,
    visibleRowsCount: topFatigueRows.length,
    meta: topFatigueMeta,
  })

  // Drive the SeasonBanner from real state. "Live" only after a clean sync;
  // otherwise treat it as a historical snapshot and label it with the actual
  // latest game-date year from the database (not a hardcoded year).
  const seasonInfo = (() => {
    const s = sync.data
    const syncedAt = s?.last_successful_sync || (s?.status === 'success' || s?.status === 'ok' ? s?.last_sync : null)
    if (syncedAt) {
      const d = new Date(syncedAt)
      if (!Number.isNaN(d.getTime())) {
        return { season: String(d.getFullYear()), isLive: true }
      }
    }
    const snap = s?.data?.latest_game_date
    if (snap && /^\d{4}-/.test(snap)) {
      return { season: snap.slice(0, 4), isLive: false }
    }
    return { season: '2024', isLive: false }
  })()

  return (
    <div className="p-4 sm:p-5 lg:p-6 max-w-7xl mx-auto">
      {/* Hero */}
      <div className="mb-5 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
        <div className="relative overflow-hidden rounded-xl border border-dirt bg-dugout p-4 sm:p-5 bg-stadium-glow">
          <div className="absolute inset-0 bg-grid-lines bg-grid-lines opacity-100 pointer-events-none" />
          <div className="relative z-10 grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(20rem,0.9fr)] lg:items-start">
            <div>
              <div className="font-mono text-xs text-amber/60 uppercase tracking-widest mb-2">Bullpen Availability &amp; Workload</div>
              <h1 className="font-display text-4xl sm:text-5xl tracking-wider text-chalk100 leading-none mb-2">
                BASEBALL<span className="text-gradient-amber">OS</span>
              </h1>
              <p className="text-chalk400 text-sm max-w-2xl font-mono leading-relaxed">
                See which relievers are available tonight and how stressed each bullpen is — with the data date and confidence shown.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <SeasonBanner season={seasonInfo.season} isLive={seasonInfo.isLive} />
              </div>
            </div>
            <div className="rounded-lg border border-dirt bg-field/65 p-3">
              <SyncStatusContent data={sync.data} loading={sync.loading} error={sync.error} />
            </div>
          </div>
        </div>
      </div>

      {/* Overview stats */}
      {overview.loading ? (
        <LoadingPane message="Loading stats..." />
      ) : overview.error ? (
        <ErrorState message={overview.error} onRetry={overview.refetch} />
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
          <StatCard label="Active Pitchers" value={overview.data?.total_pitchers}
            sub={overview.data?.scored_pitchers != null ? `${overview.data.scored_pitchers.toLocaleString()} with workload data` : undefined}
            icon="⚾" delay={100} />
          <StatCard label="Game Logs" value={overview.data?.total_game_logs?.toLocaleString()} icon="📋" delay={150} />
          <StatCard label="Avg Fatigue Score" value={overview.data?.avg_fatigue_score} sub="out of 100" accent delay={200} />
          <StatCard label="Critical / High" value={`${overview.data?.risk_breakdown?.CRITICAL ?? 0} / ${overview.data?.risk_breakdown?.HIGH ?? 0}`} icon="🔥" delay={250} />
        </div>
      )}

      <AvailabilityDashboardSummary summary={overview.data?.availability_summary} compact />

      <OperationalReadinessSection
        v2State={v2BullpenState.data}
        v2Loading={v2BullpenState.loading}
        v2Error={v2BullpenState.error}
        onRetryV2={v2BullpenState.refetch}
        readinessState={teamOperationsReadiness.data}
        readinessLoading={teamOperationsReadiness.loading}
        readinessError={teamOperationsReadiness.error}
        onRetryReadiness={teamOperationsReadiness.refetch}
      />

      <BullpenIntelligencePanel
        state={bullpenObservations.data}
        loading={bullpenObservations.loading}
        error={bullpenObservations.error}
        onRetry={bullpenObservations.refetch}
      />

      <section className="mb-5" aria-labelledby="operational-insights-heading">
        <div className="mb-3">
          <h2 id="operational-insights-heading" className="font-mono text-xs uppercase tracking-widest text-chalk400">
            Operational Insights
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-chalk600">
            Risk distribution, exploratory fatigue insight, and supporting snapshots remain available below the primary readiness summary.
          </p>
        </div>

        {/* Risk breakdown bar */}
        {overview.data?.risk_breakdown && (
          <div className="card p-4 mb-4 animate-fade-up opacity-0 delay-3" style={{ animationFillMode: 'forwards' }}>
            <div className="mb-3">
              <div className="text-chalk400 font-mono text-xs uppercase tracking-widest">Risk Distribution</div>
              {overview.data?.scored_pitchers != null && overview.data?.total_pitchers != null && (
                <div className="text-chalk600 font-mono text-[11px] mt-1 leading-relaxed">
                  <span className="text-chalk400">
                    {overview.data.total_pitchers.toLocaleString()}
                  </span>{' '}tracked ·{' '}
                  <span className="text-chalk400">
                    {overview.data.scored_pitchers.toLocaleString()}
                  </span>{' '}with workload data
                  {sync.data?.last_sync && sync.data?.pitchers_updated > 0 && (
                    <>
                      {' '}·{' '}
                      <span className="text-chalk400">{sync.data.pitchers_updated.toLocaleString()}</span>
                      {' '}refreshed in last sync
                    </>
                  )}
                  {fmtThroughDate(sync.data?.data?.latest_game_date) && (
                    <span> · data through {fmtThroughDate(sync.data.data.latest_game_date)}</span>
                  )}
                </div>
              )}
            </div>

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
            <div className="flex flex-wrap gap-x-4 gap-y-2 mt-3">
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

        {/* Fatigue → next-appearance ERA insight */}
        <DashboardDisclosure
          title="Exploratory Fatigue Insight"
          summary="Correlation study and sample-size detail remain available without dominating the operational dashboard."
        >
          <FatigueInsightCard embedded />
        </DashboardDisclosure>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* High fatigue snapshot */}
        <div className="card animate-fade-up opacity-0 delay-4" style={{ animationFillMode: 'forwards' }}>
          <div className="card-header">
            <span className="font-mono text-xs text-chalk400 uppercase tracking-widest">🔥 High Fatigue Snapshot</span>
            <Link to="/bullpen" className="text-amber text-xs font-mono hover:underline">View all →</Link>
          </div>
          <div className="p-0">
            {topFatigue.loading ? (
              <LoadingPane message="Loading..." />
            ) : topFatigue.error ? (
              <ErrorState message={topFatigue.error} onRetry={topFatigue.refetch} />
            ) : !topFatigueRows.length ? (
              <div className="p-6 text-center font-mono">
                <div className="text-chalk400 text-sm">{topFatigueEmpty.title}</div>
                <div className="text-chalk600 text-xs mt-1">{topFatigueEmpty.subtitle}</div>
              </div>
            ) : (
              <div className="overflow-x-auto">
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
                  {topFatigueRows.slice(0, 8).map((row) => (
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
              </div>
            )}
          </div>
        </div>

        {/* Pipeline snapshot */}
        <div className="card animate-fade-up opacity-0 delay-5" style={{ animationFillMode: 'forwards' }}>
          <div className="card-header">
            <span className="font-mono text-xs text-chalk400 uppercase tracking-widest">
              📈 Pipeline Snapshot
              <span className="ml-2 text-[10px] text-chalk600 normal-case tracking-normal">· prototype · sample data</span>
            </span>
            <Link to="/prospects" className="text-amber text-xs font-mono hover:underline">View all →</Link>
          </div>
          {pipeline.loading ? (
            <LoadingPane message="Loading..." />
          ) : pipeline.error ? (
            <ErrorState message={pipeline.error} onRetry={pipeline.refetch} />
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

              <div className="text-chalk600 font-mono text-xs uppercase tracking-widest mb-3">Sample Grade Highlights</div>
              <div className="space-y-2.5">
                {pipeline.data?.top_10?.slice(0, 5).map((p) => (
                  <div key={p.id} className="flex items-center gap-3">
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
      </section>

      {/* Quick links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-5">
        {[
          { to: '/bullpen', icon: '🔥', title: 'Bullpen Intelligence', desc: 'Fatigue scoring, team bullpens, pitcher detail', tag: 'Flagship' },
          { to: '/prospects', icon: '📈', title: 'Prospect Pipeline', desc: 'Development tracker — early prototype, sample data', tag: 'Prototype' },
          { to: '/methodology', icon: '📐', title: 'Methodology', desc: 'How every fatigue number is computed', tag: 'Reference' },
        ].map(({ to, icon, title, desc, tag }, i) => (
          <Link key={to} to={to}
            className="card p-5 hover:border-amber/30 hover:bg-amber/5 transition-all duration-200 group animate-fade-up opacity-0"
            style={{ animationDelay: `${600 + i * 80}ms`, animationFillMode: 'forwards' }}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="text-2xl">{icon}</div>
              <span className="font-mono text-[10px] uppercase tracking-widest text-chalk600 border border-dirt rounded px-1.5 py-0.5">{tag}</span>
            </div>
            <div className="font-display text-xl tracking-wider text-chalk100 group-hover:text-amber transition-colors">{title}</div>
            <div className="text-chalk400 text-xs font-mono mt-1">{desc}</div>
          </Link>
        ))}
      </div>
    </div>
  )
}
