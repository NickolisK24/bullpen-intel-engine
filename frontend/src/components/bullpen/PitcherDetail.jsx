import { useFetch } from '../../hooks/useFetch'
import { getAvailabilityExplanation, getPitcherFatigue } from '../../utils/api'
import { LoadingPane, ErrorState, Divider } from '../UI'
import { fmtIP, fmtDate } from '../../utils/formatters'
import {
  isWorkloadAppearance,
  latestWorkloadAppearanceFromLogs,
  normalizeAppearance,
  platformDateFromFreshness,
  workloadAppearanceDetailLabel,
} from '../../utils/appearanceLanguage'
import AvailabilitySummary from './AvailabilitySummary'
import RecentWorkPanel from './RecentWorkPanel'
import ExplanationDisclosure from '../explanations/ExplanationDisclosure'

// Spring-training detector — covers both the MLB gameType code and the
// "SIM"/"Simulated" opponent markers that sneak through on some feeds.
const isSpringTraining = (log) =>
  log?.game_type === 'S' ||
  log?.opponent_abbreviation === 'SIM' ||
  log?.opponent === 'Simulated'

function ClosePitcherDetailButton({ onClose }) {
  return (
    <button
      type="button"
      onClick={onClose}
      aria-label="Close selected pitcher detail"
      className="flex h-[2.875rem] w-[2.875rem] shrink-0 items-center justify-center border border-line text-lg leading-none text-chalk400 hover:border-signal hover:text-chalk200 focus-visible:ring-2 focus-visible:ring-signal"
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
    recent_logs,
  } = data || {}
  const platformDate = platformDateFromFreshness(freshness)
  const workloadAppearance = isWorkloadAppearance(lastWorkloadAppearance)
    ? normalizeAppearance(lastWorkloadAppearance)
    : null
  const legacyAppearance = isWorkloadAppearance(lastAppearance) ? normalizeAppearance(lastAppearance) : null
  const mostRecentAppearance = workloadAppearance || legacyAppearance || latestWorkloadAppearanceFromLogs(recent_logs)
  const mostRecentAppearanceLabel = workloadAppearanceDetailLabel(mostRecentAppearance, platformDate)
  const hasCurrentRead = Boolean(cf || availability)
  const workloadFacts = cf ? [
    { label: 'Days Rest',  value: cf.days_since_last_appearance != null ? `${cf.days_since_last_appearance}d` : '---' },
    { label: 'Pitches/7d', value: cf.pitches_last_7_days ?? 0 },
    { label: 'Apps/7d',    value: cf.appearances_last_7 ?? 0 },
    { label: 'IP/7d',      value: fmtIP(cf.innings_last_7_days) },
    { label: 'Apps/14d',   value: cf.appearances_last_14 ?? 0 },
  ] : []

  return (
    <div className="sticky top-6 w-full min-w-0 max-w-full max-h-[calc(100vh-3rem)] overflow-y-auto border border-line bg-ink">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-line p-4 sm:p-5">
        <div className="min-w-0">
          <div className="bos-eyebrow mb-2">{pitcher?.team_name}</div>
          <div className="break-words font-display text-[2rem] font-semibold leading-none text-chalk100">{pitcher?.full_name}</div>
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
      <div className="bos-intelligence-rule" aria-hidden="true" />

      {hasCurrentRead ? (
        <div className="min-w-0 space-y-6 p-4 sm:p-5">
          {availability ? (
            <AvailabilitySummary
              availability={availability}
              workloadSignal={workloadSignal}
              rosterStatus={rosterStatus}
              freshness={freshness}
              lastAppearance={mostRecentAppearance}
            />
          ) : (
            <section className="border-l-2 border-line-strong py-1 pl-4">
              <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Current Status</div>
              <p className="mt-2 text-sm font-mono leading-relaxed text-chalk400">
                Current availability is not available for this pitcher yet.
              </p>
            </section>
          )}

          {mostRecentAppearanceLabel && (
            <div className="border-t border-line pt-4">
              <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Most Recent Workload Appearance</div>
              <div className="mt-1 font-mono text-sm font-semibold text-chalk200">{mostRecentAppearanceLabel}</div>
            </div>
          )}

          <ExplanationDisclosure
            buttonLabel="Why this availability?"
            contextLabel="Availability explanation"
            disabled={!pitcherId}
            fetchExplanation={() => getAvailabilityExplanation(pitcherId)}
          />

          {workloadFacts.length > 0 && (
            <>
              <Divider label="Recent Workload Snapshot" />
              <div className="grid grid-cols-2 border-l border-t border-line sm:grid-cols-3">
                {workloadFacts.map(({ label, value }) => (
                  <div key={label} className="border-b border-r border-line p-3 text-left">
                    <div className="font-mono font-semibold text-chalk200">{value}</div>
                    <div className="text-chalk600 text-[10px] font-mono mt-0.5">{label}</div>
                  </div>
                ))}
              </div>
              <div className="border-l-2 border-line-strong py-1 pl-4 text-xs leading-relaxed text-chalk400">
                Workload units describe recent usage only; they do not describe injury status or future performance.
              </div>
            </>
          )}

          <RecentWorkPanel pitcherId={pitcherId} />

          {/* Recent logs — proper table */}
          {recent_logs?.length > 0 && (
            <>
              <Divider label="Recent Appearances" />
              <div className="overflow-x-auto -mx-1">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Opponent</th>
                      <th className="text-right">IP</th>
                      <th className="text-right">P</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent_logs.slice(0, 8).map(log => {
                      const st = isSpringTraining(log)
                      return (
                        <tr key={log.id}>
                          <td className="text-chalk200 font-mono text-xs whitespace-nowrap">{fmtDate(log.game_date)}</td>
                          <td className="font-mono text-xs">
                            {st ? (
                              <span className="inline-flex items-center gap-1.5">
                                <span
                                  className="px-1.5 py-0.5 rounded text-[10px] font-mono tracking-wider"
                                  style={{ backgroundColor: 'rgba(245,166,35,0.12)', color: '#f5a623', border: '1px solid rgba(245,166,35,0.3)' }}
                                >
                                  ST
                                </span>
                                <span className="text-chalk400">vs {log.opponent_abbreviation ?? log.opponent ?? 'SIM'}</span>
                              </span>
                            ) : (
                              <span className="text-chalk400">vs {log.opponent_abbreviation ?? log.opponent ?? '---'}</span>
                            )}
                          </td>
                          <td className="text-right font-mono text-xs text-chalk200">{fmtIP(log.innings_pitched, log.innings_pitched_outs)}</td>
                          <td className="text-right font-mono text-xs text-chalk200">{log.pitches_thrown ?? 0}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="m-5 border-l-2 border-line-strong py-1 pl-4 text-sm text-chalk400">
          No recent workload read is available yet.
        </div>
      )}
    </div>
  )
}
