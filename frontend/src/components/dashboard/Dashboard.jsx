import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getBullpenDashboard } from '../../utils/api'
import { LoadingPane, ErrorState } from '../UI'
import SeasonBanner from './SeasonBanner'
import { fmtSyncDate } from './syncStatusView'
import {
  getBoardContextView,
  getDataProvenance,
  getRolesSummaryView,
} from '../bullpen/board/tonightsBullpenBoardView'

// BaseballOS landing. Centered on the bullpen: availability, workload, health,
// and usage-role composition. Trust/freshness summaries are shown; the deep
// governance/diagnostic detail lives on the Data & Trust page.
export default function Dashboard() {
  const dash = useFetch(getBullpenDashboard)
  return (
    <DashboardView
      data={dash.data}
      loading={dash.loading}
      error={dash.error}
      onRetry={dash.refetch}
    />
  )
}

export function DashboardView({ data, loading = false, error = null, onRetry }) {
  const context = getBoardContextView(data || {})
  const roles = getRolesSummaryView(data?.roles)

  const freshness = data?.freshness || {}
  const lastSync = fmtSyncDate(freshness.last_successful_sync)
  const isCurrent = freshness.is_current !== false
  const season = (freshness.data_through || '').slice(0, 4) || '2024'
  const isLive = isCurrent && (freshness.sync_status === 'success' || freshness.sync_status === 'ok')

  return (
    <div className="p-4 sm:p-5 lg:p-6 max-w-7xl mx-auto">
      {/* Section 1 — Hero */}
      <div className="mb-6 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
        <div className="relative overflow-hidden rounded-xl border border-dirt bg-dugout p-4 sm:p-6 bg-stadium-glow">
          <div className="absolute inset-0 bg-grid-lines opacity-100 pointer-events-none" />
          <div className="relative z-10">
            <div className="font-mono text-xs text-amber/60 uppercase tracking-widest mb-2">
              League-Wide Bullpen Overview
            </div>
            <h1 className="font-display text-4xl sm:text-5xl tracking-wider text-chalk100 leading-none mb-2">
              BASEBALL<span className="text-gradient-amber">OS</span>
            </h1>
            <p className="text-chalk400 text-sm max-w-2xl font-mono leading-relaxed">
              Availability and workload across all tracked MLB bullpens tonight — who's
              available, how stressed each pen is, and what usage each arm appears suited for.
              Open <span className="text-chalk200">Bullpen</span> for a single team's pen.
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <span className="rounded border border-amber/30 bg-amber/5 px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest text-amber/80">
                League-Wide · All tracked MLB bullpens
              </span>
              <SeasonBanner season={season} isLive={isLive} />
              <FreshnessPill
                provenance={getDataProvenance(freshness)}
                lastSync={lastSync}
                confidenceLabel={context.confidenceLabel}
              />
              <Link
                to="/trust"
                className="rounded border border-dirt bg-field/60 px-3 py-2 font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
              >
                Data &amp; Trust details →
              </Link>
            </div>
          </div>
        </div>
      </div>

      {loading && !data ? (
        <LoadingPane message="Loading bullpen overview..." />
      ) : error && !data ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : !data ? null : (
        <>
          {/* Section 2 — Bullpen Snapshot */}
          <Section title="League-Wide Bullpen Snapshot" subtitle={`${context.metrics.total} relievers across all tracked MLB bullpens`}>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {context.snapshot.map(row => (
                <div key={row.status} className="card p-4">
                  <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-chalk500">
                    <span className="h-1.5 w-1.5 rounded-full" style={row.badge.dotStyle} aria-hidden="true" />
                    {row.label}
                  </div>
                  <div className="mt-1 font-mono text-3xl text-chalk100">{row.count}</div>
                </div>
              ))}
            </div>
          </Section>

          {/* Section 3 — Bullpen Health */}
          <Section
            title="League-Wide Bullpen Health"
            subtitle="Aggregated across all tracked MLB bullpens — not a single team. Open Bullpen for one team's health."
          >
            <div className="card p-4" style={context.tone} role="status" aria-live="polite">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="flex items-center gap-2 font-display text-lg tracking-wide">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: context.tone.dot }} aria-hidden="true" />
                  {context.label || 'Bullpen context unavailable.'}
                </h3>
                <span className="font-mono text-[10px] uppercase tracking-widest">
                  League-Wide · Confidence: {context.confidenceLabel}
                </span>
              </div>
              {context.isDegraded && (
                <p className="mt-2 font-mono text-[11px] uppercase tracking-wider">
                  Lower confidence — read this snapshot with caution.
                </p>
              )}
              {context.reasons.length > 0 && (
                <details className="mt-3 rounded border border-dirt/60 bg-dugout/50 p-2" open>
                  <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-chalk500">
                    Why?
                  </summary>
                  <ul className="mt-2 space-y-1">
                    {context.reasons.map((reason, index) => (
                      <li key={index} className="text-xs leading-relaxed text-chalk300">• {reason}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </Section>

          {/* Section 4 — Usage Roles Summary */}
          <Section
            title="League-Wide Usage Roles"
            subtitle="Observed usage-role distribution across all tracked MLB bullpens — not a single team, and not assigned roles."
          >
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {roles.rows.map(row => (
                <div key={row.key} className="card flex items-center justify-between gap-2 p-3" style={row.tone}>
                  <span className="font-mono text-[10px] uppercase tracking-wider">{row.label}</span>
                  <span className="font-mono text-xl">{row.count}</span>
                </div>
              ))}
            </div>
          </Section>

          {/* Section 5 — Quick Actions */}
          <Section
            title="Quick Actions"
            subtitle="From the league-wide view, drill into a single team, a matchup, or a pitcher."
          >
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <ActionCard to="/bullpen?view=board" icon="🔥" title="Tonight's Bullpen Board"
                desc="One team's bullpen tonight" />
              <ActionCard to="/bullpen?view=compare" icon="⚖️" title="Compare Bullpens"
                desc="Two teams, side-by-side" />
              <ActionCard to="/bullpen?view=pitchers" icon="📋" title="Pitcher Details"
                desc="One pitcher's fatigue & workload" />
              <ActionCard to="/methodology" icon="📐" title="Methodology"
                desc="How every number is computed" />
            </div>
          </Section>
        </>
      )}
    </div>
  )
}

function Section({ title, subtitle, children }) {
  return (
    <section className="mb-6">
      <div className="mb-3">
        <h2 className="font-mono text-xs uppercase tracking-widest text-chalk400">{title}</h2>
        {subtitle && <p className="mt-1 text-xs leading-relaxed text-chalk600">{subtitle}</p>}
      </div>
      {children}
    </section>
  )
}

function FreshnessPill({ provenance, lastSync, confidenceLabel }) {
  return (
    <div
      className="rounded border px-3 py-2 font-mono text-[11px]"
      style={{ borderColor: provenance.tone.borderColor, backgroundColor: provenance.tone.backgroundColor, color: provenance.tone.color }}
      title={provenance.throughHint}
    >
      <span className="uppercase tracking-widest">{provenance.label}</span>
      {provenance.detail && <span className="ml-2 text-chalk300">{provenance.detail}</span>}
      {lastSync && <span className="ml-2 text-chalk500">· Synced {lastSync}</span>}
      <span className="ml-2 text-chalk500">· Confidence {confidenceLabel}</span>
    </div>
  )
}

function ActionCard({ to, icon, title, desc }) {
  return (
    <Link
      to={to}
      className="card p-4 transition-all duration-200 hover:border-amber/30 hover:bg-amber/5 group"
    >
      <div className="text-2xl">{icon}</div>
      <div className="mt-2 font-display text-lg tracking-wide text-chalk100 group-hover:text-amber transition-colors">
        {title}
      </div>
      <div className="mt-1 text-xs font-mono text-chalk400">{desc}</div>
    </Link>
  )
}
