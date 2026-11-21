import { useFetch } from '../../hooks/useFetch'
import { getAvailabilityExplanation, getHistoricalPitcher, getPitcherFatigue } from '../../utils/api'
import { LoadingPane, ErrorState } from '../UI'
import {
  historicalPitcherWorkload,
  normalizeAppearance,
  productCurrentDateFromFreshness,
  workloadAppearanceDetailLabel,
} from '../../utils/appearanceLanguage'
import AvailabilitySummary from './AvailabilitySummary'
import RecentWorkPanel from './RecentWorkPanel'
import { PitcherPerformance, PitcherPublicationHistory } from './PitcherPerformanceHistory'
import HistoricalPitcherHistory from '../history/HistoricalPitcherHistory'
import { HistoricalPitcherChanges } from '../history/HistoricalChanges'
import HistoricalPitchHand from './HistoricalPitchHand'
import PitcherTrends from './PitcherTrends'
import WorkloadPatterns from './WorkloadPatterns'
import ObservedDeployment from './ObservedDeployment'
import { buildRehearsalTeamBoardHref, buildTeamBoardHref, parseRehearsalRevision } from '../../utils/evidenceLinks'
import { DATA_THROUGH_LABEL } from '../../utils/bullpenConcepts'

export function matchesPitcherEdition(page, pitcherId, revision, generation) {
  return page?.scope === 'isolated_historical_core' && page.current_serving_eligible === false
    && page.selection_revision === revision && /^[a-f0-9]{64}$/.test(page.generation)
    && (generation === null || page.generation === generation) && page.public_pitcher_id === pitcherId
    && page.pitcher?.id === pitcherId && page.identity?.public_id === pitcherId
    && Number.isSafeInteger(page.pitcher.mlb_id) && page.pitcher.mlb_id > 0 && page.pitcher.mlb_id === page.identity.mlb_id
}

function historicalBullpenTiming(data) {
  const competitive = data.competitive_weekly_workload?.value?.rest
  const rest = competitive ?? data.sections?.pitcher_rest?.value?.rest
  if (!rest || !data.data_through || !data.availability_reference ||
      rest.through !== data.data_through || rest.reference !== data.availability_reference ||
      !Number.isSafeInteger(rest.mlb_player_id) || rest.mlb_player_id !== data.pitcher?.mlb_id) return null
  const days = rest.facts?.days_since_last_appearance
  if (days?.status !== 'complete' || !Number.isSafeInteger(days.value) || days.value < 0 ||
      !days.last_appearance_date) return null
  const outing = rest.facts.last_bullpen_appearance
  const appearance = normalizeAppearance({
    game_date: days.last_appearance_date,
    pitches: outing?.status === 'complete' && outing.game_date === days.last_appearance_date ? outing.value : null,
  })
  return appearance ? { appearance, days: days.value } : null
}

export default function PitcherDetail({ pitcherId, revisionParam = null, repeated = false, generation = null }) {
  const { data, loading, error, refetch } = useFetch(
    async options => {
      const revision = parseRehearsalRevision(revisionParam, repeated)
      if (generation !== null && (!revision || !/^[a-f0-9]{64}$/.test(generation))) {
        throw new Error('Invalid historical rehearsal generation.')
      }
      if (revision === null) return getPitcherFatigue(pitcherId, options)
      const page = await getHistoricalPitcher(pitcherId, revision, options)
      if (!matchesPitcherEdition(page, pitcherId, revision, generation)) {
        throw new Error('The requested historical pitcher edition could not be verified.')
      }
      return page
    },
    [pitcherId, revisionParam, repeated, generation],
  )

  if (loading) return (
    <div className="card min-h-80">
      <h1 className="sr-only">Pitcher</h1>
      <LoadingPane message="Loading pitcher..." />
    </div>
  )
  if (error) return (
    <div className="card min-h-80">
      <h1 className="sr-only">Pitcher unavailable</h1>
      <ErrorState message={error} onRetry={refetch} />
    </div>
  )

  return <PitcherDetailContent data={data} pitcherId={pitcherId} />
}

export function PitcherDetailContent({ data, pitcherId }) {
  const {
    pitcher,
    current_fatigue: cf,
    arm_context: armContext,
    availability,
    workload_signal: representedWorkload,
    roster_status: rosterStatus,
    freshness,
    last_workload_appearance: lastWorkloadAppearance,
    pitcher_labels: pitcherLabels,
    recent_work: recentWork,
    recent_work_status: recentWorkStatus,
    deployment_context: deploymentContext,
  } = data || {}
  const historicalEdition = data?.scope === 'isolated_historical_core'
  const through = historicalEdition ? data.data_through : freshness?.data_through
  const current = !historicalEdition && armContext?.mode === 'current'
  const workloadSignal = current ? representedWorkload : null
  const productCurrentDate = productCurrentDateFromFreshness(freshness)
  const historicalTiming = historicalEdition ? historicalBullpenTiming(data) : null
  const mostRecentAppearance = historicalEdition ? historicalTiming?.appearance : normalizeAppearance(lastWorkloadAppearance)
  const mostRecentAppearanceLabel = workloadAppearanceDetailLabel(mostRecentAppearance, current ? productCurrentDate : null)
  const hasPitcherEvidence = Boolean(cf || availability || pitcherLabels || mostRecentAppearance || recentWork || deploymentContext)
  const teamReference = pitcher?.team_abbreviation || pitcher?.team_name
  const teamBoardHref = historicalEdition
    ? buildRehearsalTeamBoardHref(data.identity?.team_id === pitcher?.team_id ? pitcher?.team_id : null,
      data.selection_revision, data.generation)
    : teamReference && buildTeamBoardHref(teamReference)
  const rosterUnavailable = rosterStatus?.is_authoritative && rosterStatus.is_inactive_context
    && pitcherLabels?.read?.key === 'unavailable'
  const competitiveWeek = historicalEdition && data.competitive_weekly_workload?.scope === 'competitive_bullpen_workload'
  const week = historicalEdition
    ? (competitiveWeek ? data.competitive_weekly_workload.value : data.sections?.workload?.value?.windows?.['7'])
    : null
  const datedWorkload = historicalPitcherWorkload(week, through)
  const currentStateFacts = [
    { label: current ? 'Current Role' : 'Observed Role', value: pitcherLabels?.role?.label },
    { label: 'Current Read', value: current || rosterUnavailable ? pitcherLabels?.read?.label : 'Withheld' },
    { label: historicalEdition ? (data.competitive_weekly_workload?.value?.rest ? 'Last competitive bullpen outing' : 'Last regular-season bullpen outing') : 'Last Used', value: mostRecentAppearanceLabel },
    historicalEdition
      ? { label: 'Days since bullpen outing', value: historicalTiming && `${historicalTiming.days} as of ${data.availability_reference}` }
      : { label: 'Days Rest', value: current && armContext.days_rest != null ? `${armContext.days_rest}d` : null },
    { label: 'Appearances / 7d', value: historicalEdition ? datedWorkload?.appearances : cf?.appearances_last_7 },
    { label: 'Pitches / 7d', value: historicalEdition ? datedWorkload?.pitches_thrown : cf?.pitches_last_7_days },
  ]

  return (
    <article className="card w-full min-w-0 max-w-full">
      {/* Header */}
      <div className="card-header gap-3 bg-field/25">
        <div className="min-w-0">
          <div className="text-chalk400 font-mono text-xs mb-1">{historicalEdition && through ? [pitcher?.team_name, `Historical edition · ${through}`].filter(Boolean).join(' · ') : pitcher?.team_name}</div>
          <h1 className="font-display text-2xl tracking-wider text-chalk100 break-words">{pitcher?.full_name || (historicalEdition ? 'Pitcher identity unavailable' : null)}</h1>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 font-mono text-xs text-chalk400">
            <span>{pitcher?.position}</span>
            {historicalEdition ? <HistoricalPitchHand hand={data.pitch_hand} />
              : ['L', 'R', 'S', 'B'].includes(pitcher?.throws) && <><span>·</span><span>Throws {pitcher.throws}</span></>}
            {pitcher?.age && <><span>·</span><span>Age {pitcher.age}</span></>}
            {pitcher?.jersey_number && <><span>·</span><span>#{pitcher.jersey_number}</span></>}
          </div>
          {historicalEdition && data.identity_sources?.length > 0 && (
            <details className="mt-2 text-xs text-chalk400">
              <summary>Pitcher identity sources</summary>
              <p>MLB {pitcher.mlb_id} · BaseballOS {pitcher.id}</p>
              <ul>{data.identity_sources.map(source => (
                <li key={source.export_digest}>
                  {source.publication ? `BaseballOS snapshot ${source.publication.snapshot_id}` : 'BaseballOS pitcher identity export'}
                  {' · Observed '}{source.observed_at.slice(0, 10)}
                </li>
              ))}</ul>
            </details>
          )}
        </div>
      </div>

      {hasPitcherEvidence ? (
        <div className="min-w-0 p-4 sm:p-5 lg:p-6">
          <section
            className="rounded border border-amber/30 bg-field/70 p-3 shadow-sm sm:p-4"
            aria-labelledby="pitcher-current-state-title"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 id="pitcher-current-state-title" className="font-display text-lg tracking-wider text-chalk100">
                  {current ? 'Current Bullpen Situation' : 'Recorded Bullpen Workload'}
                </h2>
                <div className="mt-1 font-mono text-xs text-chalk400">
                  {rosterStatus?.label || 'Roster status unavailable'}
                </div>
              </div>
              {through && (
                <div className="font-mono text-[11px] text-chalk500">
                  {DATA_THROUGH_LABEL} <span className="text-chalk300">{through}</span>
                </div>
              )}
            </div>

            {!current && cf?.calculated_at && (
              <p className="mt-2 font-mono text-xs text-chalk400">Workload counts recorded {cf.calculated_at.slice(0, 10)}</p>
            )}

            <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-3">
              {currentStateFacts.map(({ label, value }) => (
                <div key={label} className="min-w-0 border-t border-dirt/70 pt-2">
                  <dt className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{label}</dt>
                  <dd className="mt-1 break-words font-mono text-sm font-semibold text-chalk200">
                    {value ?? '—'}
                  </dd>
                </div>
              ))}
            </dl>

            {historicalEdition && (
              <p className="mt-2 font-mono text-xs text-chalk400">
                Seven-day totals cover {competitiveWeek ? 'regular-season and postseason' : 'regular-season'} bullpen work, including qualifying openers.
              </p>
            )}

            {teamBoardHref && (
              <a
                href={teamBoardHref}
                className="mt-3 inline-flex min-h-11 items-center rounded border border-dirt px-3 font-mono text-xs font-semibold text-chalk300 hover:border-amber/60 hover:text-amber focus-visible:ring-2 focus-visible:ring-amber/70"
              >
                Open {pitcher?.team_name || pitcher?.team_abbreviation} Team Board
              </a>
            )}
          </section>

          <div className="mt-6 space-y-5 border-t border-dirt/70 pt-5 sm:mt-7 sm:space-y-6 sm:pt-6">
            {current && availability ? (
              <AvailabilitySummary
                availability={availability}
                workloadSignal={workloadSignal}
                rosterStatus={rosterStatus}
                freshness={freshness}
                lastAppearance={mostRecentAppearance}
                fetchExplanation={pitcherId ? () => getAvailabilityExplanation(pitcherId) : null}
              />
            ) : (
              <section className="border-b border-dirt/70 pb-5 sm:pb-6" aria-labelledby="pitcher-availability-title">
                <h2 id="pitcher-availability-title" className="font-display text-base tracking-wider text-chalk100">
                  Availability
                </h2>
                <p className="mt-2 text-sm font-mono leading-relaxed text-chalk400">
                  Current availability is not available for this pitcher yet.
                </p>
              </section>
            )}

            <RecentWorkPanel
              pitcherId={historicalEdition ? null : pitcherId}
              payload={recentWork}
              inningsLastSevenDays={cf?.innings_last_7_days}
              error={recentWorkStatus?.status === 'unavailable' ? 'recent_work_unavailable' : null}
            />
          </div>

          <PitcherTrends work={recentWork} pitches={data?.season_pitch_characteristics} deployment={data?.published_deployment ?? (historicalEdition ? data.historical_deployment : null)} />

          <div className="mt-7 grid min-w-0 gap-5 border-t border-dirt/70 pt-5 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] lg:gap-6 lg:pt-6">
            <WorkloadPatterns workloadSignal={workloadSignal} />
            <div className="min-w-0 border-t border-dirt/70 pt-5 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
              <ObservedDeployment context={deploymentContext} />
            </div>
          </div>
        </div>
      ) : (
        <div className="p-8 text-center text-chalk400 font-mono text-sm">
          No recent workload read is available yet.
        </div>
      )}
      {historicalEdition && <>
        <HistoricalPitcherChanges edition={data} />
        <HistoricalPitcherHistory key={data.generation + '/' + data.selection_revision + '/' + pitcherId} edition={data} />
      </>}
      <PitcherPerformance performance={data?.performance} />
      {!historicalEdition && pitcherId && <PitcherPublicationHistory
        key={`${pitcherId}-${freshness?.data_through}`} pitcherId={pitcherId} latest={freshness?.data_through}
      />}
    </article>
  )
}
