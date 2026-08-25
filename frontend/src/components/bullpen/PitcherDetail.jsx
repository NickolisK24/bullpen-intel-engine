import { useFetch } from '../../hooks/useFetch'
import { getAvailabilityExplanation, getPitcherFatigue } from '../../utils/api'
import { LoadingPane, ErrorState } from '../UI'
import {
  isWorkloadAppearance,
  latestWorkloadAppearanceFromLogs,
  normalizeAppearance,
  platformDateFromFreshness,
  workloadAppearanceDetailLabel,
} from '../../utils/appearanceLanguage'
import AvailabilitySummary from './AvailabilitySummary'
import RecentWorkPanel from './RecentWorkPanel'
import { buildTeamBoardHref } from '../../utils/evidenceLinks'
import { DATA_THROUGH_LABEL } from '../../utils/bullpenConcepts'

function ClosePitcherDetailButton({ onClose }) {
  return (
    <button
      type="button"
      onClick={onClose}
      aria-label="Close selected pitcher detail"
      className="shrink-0 rounded px-2 py-1 text-lg leading-none text-chalk400 hover:text-chalk200 focus-visible:ring-2 focus-visible:ring-amber/70"
    >
      ✕
    </button>
  )
}

export default function PitcherDetail({ pitcherId, onClose }) {
  const { data, loading, error, refetch } = useFetch(
    () => getPitcherFatigue(pitcherId),
    [pitcherId],
  )

  if (loading) return (
    <div className="card h-full">
      <div className="flex justify-end border-b border-dirt p-2"><ClosePitcherDetailButton onClose={onClose} /></div>
      <LoadingPane message="Loading pitcher..." />
    </div>
  )
  if (error) return (
    <div className="card h-full">
      <div className="flex justify-end border-b border-dirt p-2"><ClosePitcherDetailButton onClose={onClose} /></div>
      <ErrorState message={error} onRetry={refetch} />
    </div>
  )

  return <PitcherDetailContent data={data} pitcherId={pitcherId} onClose={onClose} />
}

export function PitcherDetailContent({ data, pitcherId, onClose }) {
  const {
    pitcher,
    current_fatigue: cf,
    availability,
    workload_signal: workloadSignal,
    roster_status: rosterStatus,
    freshness,
    last_appearance: lastAppearance,
    last_workload_appearance: lastWorkloadAppearance,
    pitcher_labels: pitcherLabels,
    recent_work: recentWork,
    recent_work_status: recentWorkStatus,
    recent_logs,
  } = data || {}
  const platformDate = platformDateFromFreshness(freshness)
  const workloadAppearance = isWorkloadAppearance(lastWorkloadAppearance)
    ? normalizeAppearance(lastWorkloadAppearance)
    : null
  const legacyAppearance = isWorkloadAppearance(lastAppearance) ? normalizeAppearance(lastAppearance) : null
  const mostRecentAppearance = workloadAppearance || legacyAppearance || latestWorkloadAppearanceFromLogs(recent_logs)
  const mostRecentAppearanceLabel = workloadAppearanceDetailLabel(mostRecentAppearance, platformDate)
  const hasCurrentRead = Boolean(cf || availability || pitcherLabels)
  const teamReference = pitcher?.team_abbreviation || pitcher?.team_name
  const teamBoardHref = teamReference ? buildTeamBoardHref(teamReference) : null
  const currentStateFacts = [
    { label: 'Current Role', value: pitcherLabels?.role?.label },
    { label: 'Current Read', value: pitcherLabels?.read?.label },
    { label: 'Last Used', value: mostRecentAppearanceLabel },
    { label: 'Days Rest', value: cf?.days_since_last_appearance != null ? `${cf.days_since_last_appearance}d` : null },
    { label: 'Appearances / 7d', value: cf?.appearances_last_7 },
    { label: 'Pitches / 7d', value: cf?.pitches_last_7_days },
  ]

  return (
    <div className="card sticky top-6 w-full min-w-0 max-w-full max-h-[calc(100vh-3rem)] overflow-y-auto">
      {/* Header */}
      <div className="card-header gap-3">
        <div className="min-w-0">
          <div className="text-chalk400 font-mono text-xs mb-1">{pitcher?.team_name}</div>
          <h2 className="font-display text-2xl tracking-wider text-chalk100 break-words">{pitcher?.full_name}</h2>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 font-mono text-xs text-chalk400">
            <span>{pitcher?.position}</span>
            <span>·</span>
            <span>Throws {pitcher?.throws}</span>
            {pitcher?.age && <><span>·</span><span>Age {pitcher.age}</span></>}
            {pitcher?.jersey_number && <><span>·</span><span>#{pitcher.jersey_number}</span></>}
          </div>
        </div>
        <ClosePitcherDetailButton onClose={onClose} />
      </div>

      {hasCurrentRead ? (
        <div className="min-w-0 p-4 space-y-5 sm:p-5">
          <section
            className="rounded border border-dirt bg-field/55 p-3 sm:p-4"
            aria-labelledby="pitcher-current-state-title"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h3 id="pitcher-current-state-title" className="font-display text-base tracking-wider text-chalk100">
                  Current Bullpen Situation
                </h3>
                <div className="mt-1 font-mono text-xs text-chalk400">
                  {rosterStatus?.label || 'Roster status unavailable'}
                </div>
              </div>
              {freshness?.data_through && (
                <div className="font-mono text-[11px] text-chalk500">
                  {DATA_THROUGH_LABEL} <span className="text-chalk300">{freshness.data_through}</span>
                </div>
              )}
            </div>

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

            {teamBoardHref && (
              <a
                href={teamBoardHref}
                className="mt-3 inline-flex min-h-11 items-center rounded border border-dirt px-3 font-mono text-xs font-semibold text-chalk300 hover:border-amber/60 hover:text-amber focus-visible:ring-2 focus-visible:ring-amber/70"
              >
                Open {pitcher?.team_name || pitcher?.team_abbreviation} Team Board
              </a>
            )}
          </section>

          {availability ? (
            <AvailabilitySummary
              availability={availability}
              workloadSignal={workloadSignal}
              rosterStatus={rosterStatus}
              freshness={freshness}
              lastAppearance={mostRecentAppearance}
              fetchExplanation={pitcherId ? () => getAvailabilityExplanation(pitcherId) : null}
            />
          ) : (
            <section className="rounded border border-dirt bg-chalk/30 p-4 sm:p-5">
              <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Current Status</div>
              <p className="mt-2 text-sm font-mono leading-relaxed text-chalk400">
                Current availability is not available for this pitcher yet.
              </p>
            </section>
          )}

          <RecentWorkPanel
            pitcherId={pitcherId}
            payload={recentWork}
            inningsLastSevenDays={cf?.innings_last_7_days}
            error={recentWorkStatus?.status === 'unavailable' ? 'recent_work_unavailable' : null}
          />
        </div>
      ) : (
        <div className="p-8 text-center text-chalk400 font-mono text-sm">
          No recent workload read is available yet.
        </div>
      )}
    </div>
  )
}
