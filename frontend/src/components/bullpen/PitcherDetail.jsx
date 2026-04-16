import { useFetch } from '../../hooks/useFetch'
import { getPitcherFatigue } from '../../utils/api'
import { LoadingPane, ErrorState, FatigueBar, RiskBadge, Divider } from '../UI'
import { fmtIP, fmtDate, riskColor } from '../../utils/formatters'
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, Tooltip } from 'recharts'

export default function PitcherDetail({ pitcherId, onClose }) {
  const { data, loading, error } = useFetch(() => getPitcherFatigue(pitcherId), [pitcherId])

  if (loading) return (
    <div className="card h-full"><LoadingPane message="Loading pitcher..." /></div>
  )
  if (error) return (
    <div className="card h-full"><ErrorState message={error} /></div>
  )

  const { pitcher, current_fatigue: cf, recent_logs } = data || {}

  // Radar data for fatigue breakdown
  const radarData = cf ? [
    { component: 'Pitches',   value: Math.round(cf.pitch_count_score ?? 0)  },
    { component: 'Rest',      value: Math.round(cf.rest_days_score ?? 0)    },
    { component: 'Apps',      value: Math.round(cf.appearances_score ?? 0)  },
    { component: 'Leverage',  value: Math.round(cf.leverage_score ?? 0)     },
    { component: 'Innings',   value: Math.round(cf.innings_score ?? 0)      },
  ] : []

  // Detect spring training games — MLB API uses 'gameType: S' but we can
  // also catch it by the 'SIM' abbreviation that slips through on some logs
  const isSpringTraining = (log) =>
    log.game_type === 'S' ||
    log.opponent_abbreviation === 'SIM' ||
    log.opponent === 'Simulated'

  return (
    <div className="card sticky top-6 max-h-[calc(100vh-3rem)] overflow-y-auto">
      {/* Header */}
      <div className="card-header">
        <div>
          <div className="text-chalk400 font-mono text-xs mb-1">{pitcher?.team_name}</div>
          <div className="font-display text-2xl tracking-wider text-chalk100">{pitcher?.full_name}</div>
          <div className="flex gap-3 mt-1 font-mono text-xs text-chalk400">
            <span>{pitcher?.position}</span>
            <span>·</span>
            <span>Throws {pitcher?.throws}</span>
            {pitcher?.age && <><span>·</span><span>Age {pitcher.age}</span></>}
            {pitcher?.jersey_number && <><span>·</span><span>#{pitcher.jersey_number}</span></>}
          </div>
        </div>
        <button onClick={onClose} className="text-chalk400 hover:text-chalk200 text-lg leading-none">✕</button>
      </div>

      {cf ? (
        <div className="p-5 space-y-5">
          {/* Score + Risk */}
          <div className="flex items-center gap-4">
            <div className={`font-display text-6xl tracking-wider ${riskColor(cf.risk_level)}`}>
              {Math.round(cf.raw_score)}
            </div>
            <div>
              <RiskBadge level={cf.risk_level} />
              <div className="text-chalk400 text-xs font-mono mt-1">Fatigue Score</div>
            </div>
          </div>

          <FatigueBar score={cf.raw_score} height="h-2" />

          {/* Quick stats */}
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: 'Days Rest', value: cf.days_since_last_appearance != null ? `${cf.days_since_last_appearance}d` : '---' },
              { label: 'Pitches/7d', value: cf.pitches_last_7_days ?? 0 },
              { label: 'Apps/7d', value: cf.appearances_last_7 ?? 0 },
              { label: 'IP/7d', value: fmtIP(cf.innings_last_7_days) },
              { label: 'Apps/14d', value: cf.appearances_last_14 ?? 0 },
              { label: 'Avg LI', value: cf.avg_leverage_last_7 ? cf.avg_leverage_last_7.toFixed(2) : '---' },
            ].map(({ label, value }) => (
              <div key={label} className="bg-chalk/40 border border-dirt rounded p-2.5 text-center">
                <div className="font-mono font-semibold text-chalk200">{value}</div>
                <div className="text-chalk600 text-[10px] font-mono mt-0.5">{label}</div>
              </div>
            ))}
          </div>

          {/* Component breakdown */}
          <Divider label="Score Breakdown" />
          <div className="space-y-2.5">
            {[
              { label: 'Pitch Count Load', score: cf.pitch_count_score, weight: '30%' },
              { label: 'Rest Days',        score: cf.rest_days_score,   weight: '25%' },
              { label: 'Appearance Freq',  score: cf.appearances_score, weight: '20%' },
              { label: 'Leverage Index',   score: cf.leverage_score,    weight: '15%' },
              { label: 'Innings Load',     score: cf.innings_score,     weight: '10%' },
            ].map(({ label, score, weight }) => (
              <div key={label}>
                <div className="flex justify-between mb-1">
                  <span className="text-chalk400 text-xs font-mono">{label}</span>
                  <div className="flex gap-2">
                    <span className="text-chalk600 text-xs font-mono">{weight}</span>
                    <span className="text-chalk200 text-xs font-mono w-6 text-right">{Math.round(score ?? 0)}</span>
                  </div>
                </div>
                <FatigueBar score={score} height="h-1" />
              </div>
            ))}
          </div>

          {/* Radar chart */}
          {radarData.length > 0 && (
            <>
              <Divider label="Fatigue Profile" />
              <div className="h-44">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="#242b35" />
                    <PolarAngleAxis dataKey="component" tick={{ fill: '#8899aa', fontSize: 10, fontFamily: 'JetBrains Mono' }} />
                    <Radar dataKey="value" stroke="#f5a623" fill="#f5a623" fillOpacity={0.15} strokeWidth={2} />
                    <Tooltip
                      contentStyle={{ background: '#111418', border: '1px solid #242b35', borderRadius: '6px', fontFamily: 'JetBrains Mono', fontSize: '11px' }}
                      labelStyle={{ color: '#d1dce8' }}
                      itemStyle={{ color: '#f5a623' }}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </>
          )}

          {/* Recent logs */}
          {recent_logs?.length > 0 && (
            <>
              <Divider label="Recent Appearances" />
              <div className="space-y-2">
                {recent_logs.slice(0, 6).map(log => (
                  <div key={log.id} className="flex items-center justify-between bg-chalk/30 rounded px-3 py-2 text-xs font-mono">
                    <div className="flex items-center gap-2">
                      <span className="text-chalk200">{fmtDate(log.game_date)}</span>
                      {isSpringTraining(log) ? (
                        <>
                          <span className="text-chalk600">·</span>
                          <span className="px-1.5 py-0.5 rounded bg-amber/10 text-amber/70 text-[10px] font-mono tracking-wider">ST</span>
                          <span className="text-chalk600">Spring Training</span>
                        </>
                      ) : (
                        <span className="text-chalk600">vs {log.opponent_abbreviation ?? '---'}</span>
                      )}
                    </div>
                    <div className="flex gap-3 text-chalk400">
                      <span>{fmtIP(log.innings_pitched)} IP</span>
                      <span>{log.pitches_thrown ?? 0} P</span>
                      <span>{log.strikeouts ?? 0} K</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="p-8 text-center text-chalk400 font-mono text-sm">
          No fatigue data available yet.
        </div>
      )}
    </div>
  )
}