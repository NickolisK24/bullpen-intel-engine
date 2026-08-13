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
    <div className="bos-page pb-12">
      <header className="pt-[1.875rem]">
        <div className="bos-eyebrow mb-2">League-Wide Bullpen Overview</div>
        <h1 className="bos-hero">League Bullpen Board</h1>
        <p className="bos-body mt-4 max-w-measure text-chalk300">
              A league-wide bullpen board from the latest completed data - who looks
              usable, which pens are stretched, and what kind of role each arm appears
              to fill.
              Open <span className="text-chalk200">Bullpen</span> for a single team's pen.
        </p>

        <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line pt-4">
              <span className="bos-meta uppercase text-brass">
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
                className="bos-link font-mono text-xs uppercase tracking-wider"
              >
                Data &amp; Trust details →
              </Link>
        </div>
        <div className="bos-intelligence-rule mt-5" aria-hidden="true" />
      </header>

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
            <div className="grid grid-cols-2 border-l border-t border-line sm:grid-cols-3 lg:grid-cols-6">
              {roles.rows.map(row => (
                <div key={row.key} className="flex min-h-20 items-center justify-between gap-2 border-b border-r border-line p-3">
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
      <div className="border-t border-line pt-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-widest text-amber/80">
              Explanatory Only
            </div>
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-chalk300">
              {getInjuryIlContextSummary(context)}
            </p>
          </div>
          <div className="shrink-0 font-mono text-[10px] uppercase tracking-widest text-chalk500">
            {context.countsWithheld
              ? 'Roster counts withheld'
              : `${context.league.bullpenPopulationCount} dashboard relievers`}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 border-l border-t border-line sm:grid-cols-3">
          {stats.map(stat => (
            <div key={stat.label} className="border-b border-r border-line p-3">
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
    <section className="bos-section">
      <div className="mb-4">
        <h2 className="bos-section-title">{title}</h2>
        {subtitle && <p className="bos-support mt-2 max-w-measure">{subtitle}</p>}
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
      className="border-l-2 py-0.5 pl-3 font-mono text-[11px] leading-relaxed"
      style={{ borderColor: provenance.tone.borderColor, color: provenance.tone.color }}
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
