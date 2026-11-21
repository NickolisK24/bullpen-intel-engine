import { useSearchParams } from 'react-router-dom'
import { parseRehearsalRevision } from '../../utils/evidenceLinks'
import { useFetch } from '../../hooks/useFetch'
import { getLeagueProjection, getRehearsalLeague } from '../../utils/api'
import { Disclosure, ErrorState, FreshnessStamp, LoadingPane, UnavailableDataState } from '../UI'
import DashboardStorylines from './DashboardStorylines'
import LeagueTeamStateLandscape from './LeagueTeamStateLandscape'
import { getLeagueTeamStateListingView, historicalLeagueView } from './leagueTeamStateListingView'
import {
  getInjuryIlContextSummary,
  normalizeInjuryIlContext,
} from './injuryIlContextView'
import {
  getRolesSummaryView,
} from '../bullpen/board/tonightsBullpenBoardView'

// Final league bullpen orientation: one governed all-club Team State listing
// leads, while backend-authored storylines and independent context stay intact.
export default function Dashboard() {
  const [params] = useSearchParams()
  if (!params.has('rehearsalRevision') && !params.has('rehearsalGeneration')) return <PublicDashboard />
  try {
    const revision = parseRehearsalRevision(params.get('rehearsalRevision'), params.getAll('rehearsalRevision').length > 1)
    const generation = params.get('rehearsalGeneration')
    if (!revision || (generation !== null && (!/^[a-f0-9]{64}$/.test(generation) || params.getAll('rehearsalGeneration').length > 1))) {
      throw new Error('Invalid historical League edition.')
    }
    return <HistoricalLeague key={JSON.stringify([revision, generation])} revision={revision} generation={generation} />
  } catch (error) {
    return <ErrorState message={error.message} />
  }
}

function HistoricalLeague({ revision, generation }) {
  const league = useFetch(async options => {
    const page = await getRehearsalLeague(revision, options)
    const view = historicalLeagueView(page, revision, generation)
    if (!view) throw new Error('The requested historical League edition could not be verified.')
    return view
  }, [revision, generation])
  if (league.loading) return <LoadingPane message="Loading historical League…" />
  if (league.error) return <ErrorState message={league.error} onRetry={league.refetch} />
  return <main className="mx-auto max-w-7xl p-6">
    <h1 className="mb-4 font-display text-3xl">Historical League · Revision {revision}</h1>
    <LeagueTeamStateLandscape view={league.data} historical />
  </main>
}

function PublicDashboard() {
  const league = useFetch(getLeagueProjection)
  return (
    <DashboardView
      data={league.data}
      loading={league.loading}
      error={league.error}
      staleWithError={league.staleWithError}
      onRetry={league.refetch}
      leagueTeamStates={league.data?.team_states}
      leagueTeamStatesLoading={league.loading}
      leagueTeamStatesError={league.error}
      leagueTeamStatesStaleWithError={league.staleWithError}
      onRetryLeagueTeamStates={league.refetch}
    />
  )
}
export function DashboardView({
  data,
  error = null,
  staleWithError = false,
  onRetry,
  leagueTeamStates = null,
  leagueTeamStatesLoading = false,
  leagueTeamStatesError = null,
  leagueTeamStatesStaleWithError = false,
  onRetryLeagueTeamStates,
}) {
  const roles = data?.roles?.counts ? getRolesSummaryView(data.roles) : null
  const injuryIlContext = normalizeInjuryIlContext(data)
  const leagueView = getLeagueTeamStateListingView(leagueTeamStates)

  return (
    <div className="p-4 sm:p-5 lg:p-6 max-w-7xl mx-auto">
      {/* Section 1 — Hero */}
      <div className="mb-5 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
        <div className="relative overflow-hidden rounded-xl border border-dirt bg-dugout p-4 sm:p-5 bg-stadium-glow">
          <div className="absolute inset-0 bg-grid-lines opacity-100 pointer-events-none" />
          <div className="relative z-10">
            <div className="font-mono text-xs text-metadata-accent uppercase tracking-widest mb-2">
              MLB Bullpen Overview
            </div>
            <h1 className="mb-2 font-display text-4xl leading-none tracking-wider text-chalk100 sm:text-5xl">
              MLB Bullpen Picture
            </h1>
            <p className="max-w-2xl text-sm leading-relaxed text-chalk400">
              The current bullpen picture across MLB, using already-published Team State reads for every expected club.
            </p>
            <FreshnessStamp freshness={leagueView.freshness} className="mt-3" />
          </div>
        </div>
      </div>

      <DashboardStorylines landscape={data?.landscape} />

      <LeagueTeamStateLandscape
        view={leagueView}
        loading={leagueTeamStatesLoading}
        error={leagueTeamStatesError}
        staleWithError={leagueTeamStatesStaleWithError}
        onRetry={onRetryLeagueTeamStates}
      />

      {error && !data ? (
        <Section
          title="Secondary Dashboard Context"
          subtitle="Roster-status and usage-role context remain separate from the published league Team State view."
        >
          <UnavailableDataState
            title="Secondary context unavailable"
            message="Roster-status and usage-role context could not be loaded."
            onRetry={onRetry}
            className="bg-field/25"
            titleClassName="font-mono text-xs uppercase tracking-widest text-chalk300"
            messageClassName="mt-2 text-xs leading-relaxed text-chalk500"
          />
        </Section>
      ) : data && (
        <>
          {staleWithError && (
            <p className="mb-4 text-xs leading-relaxed text-chalk500">
              Secondary Dashboard context refresh is delayed; showing the last loaded context.
              {onRetry && <button type="button" onClick={onRetry} className="ml-1 underline hover:text-amber">Retry</button>}
            </p>
          )}
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
            <div className="font-mono text-[10px] uppercase tracking-widest text-metadata-accent">
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
