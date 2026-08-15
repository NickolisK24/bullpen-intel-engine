import { useFetch } from '../../hooks/useFetch'
import { getBullpenDashboard } from '../../utils/api'
import { Disclosure, ErrorState, FreshnessStamp, LoadingPane, StaleDataNotice, UnavailableDataState } from '../UI'
import BullpenLandscape from './BullpenLandscape'
import {
  getInjuryIlContextSummary,
  normalizeInjuryIlContext,
} from './injuryIlContextView'
import { freshnessDataThrough } from './syncStatusView'
import {
  getRolesSummaryView,
} from '../bullpen/board/tonightsBullpenBoardView'

// Interim league bullpen orientation: backend-authored storylines and partial
// situation lanes lead, with roster and usage-role context kept secondary.
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
  const roles = data?.roles?.counts ? getRolesSummaryView(data.roles) : null
  const injuryIlContext = normalizeInjuryIlContext(data)

  const freshness = data?.freshness || {}
  const dataThroughSource = freshnessDataThrough(freshness)

  return (
    <div className="p-4 sm:p-5 lg:p-6 max-w-7xl mx-auto">
      {/* Section 1 — Hero */}
      <div className="mb-5 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
        <div className="relative overflow-hidden rounded-xl border border-dirt bg-dugout p-4 sm:p-5 bg-stadium-glow">
          <div className="absolute inset-0 bg-grid-lines opacity-100 pointer-events-none" />
          <div className="relative z-10">
            <div className="font-mono text-xs text-amber/60 uppercase tracking-widest mb-2">
              MLB Bullpen Overview
            </div>
            <h1 className="mb-2 font-display text-4xl leading-none tracking-wider text-chalk100 sm:text-5xl">
              MLB Bullpen Picture
            </h1>
            <p className="max-w-2xl text-sm leading-relaxed text-chalk400">
              Current published context across MLB bullpens. The situation lanes below are a partial view, not a complete ranking of all 30 clubs.
            </p>
            <FreshnessStamp freshness={freshness} className="mt-3" />
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

          {/* Interim published league context. */}
          <BullpenLandscape landscape={data.landscape} />

          <InjuryIlContextSection context={injuryIlContext} />

          {/* Section 4 — Usage Roles Summary */}
          <Section title="Usage Roles" subtitle="Observed role context across the bullpen arms represented in this published view — not assigned roles.">
            {!roles ? (
              <UnavailableDataState title="Role context unavailable" message="No published usage-role counts are available for this view." />
            ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {roles.rows.map(row => (
                <div key={row.key} className="card flex items-center justify-between gap-2 p-3" style={row.tone}>
                  <span className="font-mono text-[10px] uppercase tracking-wider">{row.label}</span>
                  <span className="font-mono text-xl">{row.count}</span>
                </div>
              ))}
            </div>
            )}
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
          <Disclosure label="Limits on this context" className="mt-3">
            <ul className="space-y-1">
              {context.limitations.map((limitation, index) => (
                <li key={index} className="text-[11px] leading-relaxed text-chalk500">• {limitation}</li>
              ))}
            </ul>
          </Disclosure>
        )}

        <p className="mt-3 text-[11px] leading-relaxed text-chalk500">
          <span className="text-chalk300">Why it matters:</span> Bullpen workload can become concentrated when active relief depth is reduced.
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
