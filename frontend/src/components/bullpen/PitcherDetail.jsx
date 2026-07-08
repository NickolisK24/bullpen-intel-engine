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

export default function PitcherDetail({ pitcherId, onClose }) {
  const { data, loading, error, refetch } = useFetch(
    () => getPitcherFatigue(pitcherId),
    [pitcherId],
  )

  if (loading) return (
    <div className="card h-full"><LoadingPane message="Loading pitcher..." /></div>
  )
  if (error) return (
    <div className="card h-full"><ErrorState message={error} onRetry={refetch} /></div>
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
    <div className="card sticky top-6 w-full min-w-0 max-w-full max-h-[calc(100vh-3rem)] overflow-y-auto">
      {/* Header */}
      <div className="card-header gap-3">
        <div className="min-w-0">
          <div className="text-chalk400 font-mono text-xs mb-1">{pitcher?.team_name}</div>
          <div className="font-display text-2xl tracking-wider text-chalk100 break-words">{pitcher?.full_name}</div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 font-mono text-xs text-chalk400">
            <span>{pitcher?.position}</span>
            <span>·</span>
            <span>Throws {pitcher?.throws}</span>
            {pitcher?.age && <><span>·</span><span>Age {pitcher.age}</span></>}
            {pitcher?.jersey_number && <><span>·</span><span>#{pitcher.jersey_number}</span></>}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close selected pitcher detail"
          className="shrink-0 rounded px-2 py-1 text-lg leading-none text-chalk400 hover:text-chalk200 focus-visible:ring-2 focus-visible:ring-amber/70"
        >
          ✕
        </button>
      </div>

      {hasCurrentRead ? (
        <div className="min-w-0 p-4 space-y-5 sm:p-5">
          {availability ? (
            <AvailabilitySummary
              availability={availability}
              workloadSignal={workloadSignal}
              rosterStatus={rosterStatus}
              freshness={freshness}
              lastAppearance={mostRecentAppearance}
            />
          ) : (
            <section className="rounded border border-dirt bg-chalk/30 p-4 sm:p-5">
              <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Current Status</div>
              <p className="mt-2 text-sm font-mono leading-relaxed text-chalk400">
                Current availability is not available for this pitcher yet.
              </p>
            </section>
          )}

          {mostRecentAppearanceLabel && (
            <div className="rounded border border-dirt bg-field/50 p-3">
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
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {workloadFacts.map(({ label, value }) => (
                  <div key={label} className="bg-chalk/40 border border-dirt rounded p-2.5 text-center">
                    <div className="font-mono font-semibold text-chalk200">{value}</div>
                    <div className="text-chalk600 text-[10px] font-mono mt-0.5">{label}</div>
                  </div>
                ))}
              </div>
              <div className="rounded border border-dirt bg-field/40 px-3 py-2 text-xs font-mono leading-relaxed text-chalk400">
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
        <div className="p-8 text-center text-chalk400 font-mono text-sm">
          No recent workload read is available yet.
        </div>
      )}
    </div>
  )
}
