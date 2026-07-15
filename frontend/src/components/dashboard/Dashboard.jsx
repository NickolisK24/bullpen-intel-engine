import { Link } from 'react-router-dom'
import { toOperatingStateReadModel } from '../../adapters/operatingStateReadModel'
import { useFetch } from '../../hooks/useFetch'
import { getBullpenDashboard } from '../../utils/api'
import { buildTeamBoardHref } from '../../utils/evidenceLinks'
import { LoadingPane, ErrorState, StaleDataNotice } from '../UI'
import SeasonBanner from './SeasonBanner'
import BullpenLandscape from './BullpenLandscape'
import {
  getInjuryIlContextSummary,
  normalizeInjuryIlContext,
} from './injuryIlContextView'
import { fmtSyncDate, freshnessDataThrough } from './syncStatusView'
import {
  getBoardContextView,
  getDataProvenance,
  getRolesSummaryView,
} from '../bullpen/board/tonightsBullpenBoardView'
import BullpenOperatingStateCard from '../bullpen/BullpenOperatingStateCard'

// The league bullpen board: the only full league-wide landscape surface.
// Centered on the bullpen landscape with one league state read, roster
// context, and usage-role composition. Trust/freshness summaries are shown;
// the deep governance/diagnostic detail lives on the Data & Trust page.
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
    cta: { href: buildTeamBoardHref(null, { source: 'dashboard' }), label: 'Open Bullpen Board' },
  })
  const roles = getRolesSummaryView(data?.roles)
  const injuryIlContext = normalizeInjuryIlContext(data)

  const freshness = data?.freshness || {}
  const provenance = getDataProvenance(freshness)
  const dataThroughSource = freshnessDataThrough(freshness)
  const lastSync = fmtSyncDate(freshness.last_successful_sync || freshness.lastSuccessfulSync)
  const season = (dataThroughSource || '').slice(0, 4) || '2024'
  const isLive = provenance.isLive

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
              League Bullpen Board
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
                provenance={provenance}
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
          {staleWithError && (
            <StaleDataNotice
              dataThrough={dataThroughSource}
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

        </>
      )}

    </div>
  )
}

function InjuryIlContextSection({ context }) {
  if (!context) return null
  const valueLabel = (value) => value == null ? 'Withheld' : value

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
            {context.countsWithheld
              ? 'Roster counts withheld'
              : `${context.league.bullpenPopulationCount} dashboard relievers`}
          </div>
        </div>

        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {stats.map(stat => (
            <div key={stat.label} className="rounded border border-dirt/70 bg-field/35 p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-chalk500">
                {stat.label}
              </div>
              <div className="mt-1 font-mono text-2xl text-chalk100">{valueLabel(stat.value)}</div>
              <div className="mt-1 text-[11px] leading-relaxed text-chalk500">{stat.detail}</div>
            </div>
          ))}
        </div>

        {context.limitations.length > 0 && (
          <ul className="mt-3 space-y-1">
            {context.limitations.map((limitation, index) => (
              <li key={index} className="text-[11px] leading-relaxed text-chalk500">• {limitation}</li>
            ))}
          </ul>
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
