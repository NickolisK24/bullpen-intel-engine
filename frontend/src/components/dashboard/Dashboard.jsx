import { Link } from 'react-router-dom'
import { toOperatingStateReadModel } from '../../adapters/operatingStateReadModel'
import { useFetch } from '../../hooks/useFetch'
import { getBullpenDashboard } from '../../utils/api'
import { LoadingPane, ErrorState, StaleDataNotice } from '../UI'
import SeasonBanner from './SeasonBanner'
import BullpenLandscape from './BullpenLandscape'
import DashboardOrientation from './DashboardOrientation'
import {
  getInjuryIlContextSummary,
  normalizeInjuryIlContext,
} from './injuryIlContextView'
import { FeedbackCTA } from '../feedback/FeedbackLink'
import { fmtSyncDate } from './syncStatusView'
import {
  getBoardContextView,
  getDataProvenance,
  getRolesSummaryView,
} from '../bullpen/board/tonightsBullpenBoardView'
import BullpenOperatingStateCard from '../bullpen/BullpenOperatingStateCard'

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
      staleWithError={dash.staleWithError}
      onRetry={dash.refetch}
    />
  )
}

export function DashboardView({ data, loading = false, error = null, staleWithError = false, onRetry }) {
  const context = getBoardContextView(data || {})
  const operatingStateRead = toOperatingStateReadModel(data || {}, {
    scope: 'league',
    cta: { href: '/bullpen?view=board', label: 'Open Bullpen Board' },
  })
  const roles = getRolesSummaryView(data?.roles)
  const injuryIlContext = normalizeInjuryIlContext(data)

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
              A league-wide bullpen board from the latest completed data - who looks
              usable, which pens are stretched, and what kind of role each arm appears
              to fill.
              Open <span className="text-chalk200">Bullpen</span> for a single team's pen.
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <span className="rounded border border-amber/30 bg-amber/5 px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest text-amber/80">
                League-Wide · Bullpen-eligible MLB arms
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

      {/* Orientation layer — what BaseballOS is + what to do next (always shown) */}
      <DashboardOrientation />

      {loading && !data ? (
        <LoadingPane message="Loading bullpen overview..." />
      ) : error && !data ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : !data ? null : (
        <>
          {staleWithError && (
            <StaleDataNotice
              dataThrough={freshness.data_through}
              onRetry={onRetry}
            />
          )}

          {/* Tonight's Bullpen Landscape — first-time league orientation */}
          <BullpenLandscape landscape={data.landscape} />

          {/* Section 2 — Bullpen State */}
          <Section
            title="League-Wide Bullpen State"
            subtitle="League-wide context across bullpen-eligible arms — not a single team. Open the Bullpen Board for a team-specific read."
          >
            <BullpenOperatingStateCard
              readModel={operatingStateRead}
              staleWithError={staleWithError}
              onRetry={onRetry}
            />
          </Section>

          <InjuryIlContextSection context={injuryIlContext} />

          {/* Section 3 — Bullpen Read */}
          <Section title="League-Wide Bullpen Read" subtitle={`${context.metrics.total} bullpen-eligible relievers in the current bullpen availability set`}>
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

          {/* Section 4 — Usage Roles Summary */}
          <Section
            title="League-Wide Usage Roles"
            subtitle="Observed usage-role distribution across bullpen-eligible MLB arms — not a single team, and not assigned roles."
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
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <ActionCard to="/bullpen?view=board" icon="🔥" title="Team Bullpen Board"
                desc="One team's current availability read" />
              <ActionCard to="/bullpen?view=compare" icon="⚖️" title="Compare Bullpens"
                desc="Two teams, side-by-side" />
              <ActionCard to="/bullpen?view=pitchers" icon="📋" title="Pitcher Details"
                desc="One pitcher's fatigue & workload" />
              <ActionCard to="/stories" icon="📰" title="Read bullpen stories"
                desc="Follow deeper bullpen trends and developing workload stories." />
              <ActionCard to="/methodology" icon="📐" title="Methodology"
                desc="How every number is computed" />
            </div>
          </Section>
        </>
      )}

      <FeedbackCTA
        compact
        className="mb-2"
        eyebrow="User Validation"
        title="Help shape BaseballOS"
        body="Share what is useful, unclear, or missing while BaseballOS is being tested with real users."
      />
    </div>
  )
}

function InjuryIlContextSection({ context }) {
  if (!context) return null

  const stats = [
    {
      label: 'On Injured List',
      value: context.league.injuredListCount,
      detail: 'Bullpen arms with known IL status',
    },
    {
      label: 'Inactive Roster',
      value: context.league.inactiveCount,
      detail: 'Bullpen arms optioned, in the minors, or inactive',
    },
    {
      label: 'Clubs With 2+',
      value: context.league.teamsWithMultipleUnavailable,
      detail: 'Clubs with multiple unavailable bullpen arms',
    },
  ]
  const followed = context.followedTeam

  return (
    <Section
      title="Bullpen Availability Context"
      subtitle="Roster-status context for the dashboard bullpen population. Workload availability remains separate."
    >
      <div className="card p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-widest text-amber/80">
              Explanatory Only
            </div>
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-chalk300">
              {getInjuryIlContextSummary(context)}
            </p>
          </div>
          <div className="shrink-0 rounded border border-dirt bg-dugout/60 px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest text-chalk500">
            {context.league.bullpenPopulationCount} dashboard relievers
          </div>
        </div>

        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {stats.map(stat => (
            <div key={stat.label} className="rounded border border-dirt/70 bg-field/35 p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-chalk500">
                {stat.label}
              </div>
              <div className="mt-1 font-mono text-2xl text-chalk100">{stat.value}</div>
              <div className="mt-1 text-[11px] leading-relaxed text-chalk500">{stat.detail}</div>
            </div>
          ))}
        </div>

        {followed && (
          <div className="mt-3 rounded border border-dirt/70 bg-dugout/45 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                  Followed Team
                </div>
                <div className="mt-0.5 font-display text-base tracking-wide text-chalk100">
                  {followed.teamName}
                </div>
              </div>
              <div className="font-mono text-[11px] uppercase tracking-wider text-chalk400">
                {followed.injuredListCount} IL · {followed.inactiveCount} inactive
              </div>
            </div>
            {followed.unavailablePitchers.length > 0 && (
              <ul className="mt-2 grid gap-1 sm:grid-cols-2">
                {followed.unavailablePitchers.slice(0, 4).map(pitcher => (
                  <li key={`${pitcher.playerId || pitcher.name}-${pitcher.status}`} className="min-w-0 text-xs leading-relaxed text-chalk300">
                    <span className="break-words text-chalk200">{pitcher.name}</span>
                    <span className="text-chalk500"> - {pitcher.statusLabel}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <p className="mt-3 text-[11px] leading-relaxed text-chalk500">
          <span className="text-chalk300">Why it matters:</span> Bullpen workload can become concentrated when active relief depth is reduced.
        </p>

        <p className="mt-2 text-[11px] leading-relaxed text-chalk500">
          Availability classifications are workload-based. Roster status context is separate and does not change the availability model.
        </p>
      </div>
    </Section>
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
  const dataLine = provenance.completedGamesLine
    ? provenance.completedGamesLine
    : 'No completed MLB data loaded'
  return (
    <div
      className="rounded border px-3 py-2 font-mono text-[11px] leading-relaxed"
      style={{ borderColor: provenance.tone.borderColor, backgroundColor: provenance.tone.backgroundColor, color: provenance.tone.color }}
      title={provenance.throughHint}
    >
      <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <span>{provenance.label}</span>
        <span>{dataLine}</span>
        {lastSync && <span className="text-chalk500">· Latest data update: {lastSync}</span>}
        <span className="text-chalk500">· Workload Read: {confidenceLabel}</span>
      </span>
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
