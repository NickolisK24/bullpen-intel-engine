import { useFetch } from '../../hooks/useFetch'
import { getPitcherFatigue } from '../../utils/api'
import { LoadingPane, ErrorState, FatigueBar, RiskBadge, Divider } from '../UI'
import { fmtIP, fmtDate, riskColor } from '../../utils/formatters'
import {
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
  LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine,
  ResponsiveContainer, Tooltip,
} from 'recharts'

// Spring-training detector — covers both the MLB gameType code and the
// "SIM"/"Simulated" opponent markers that sneak through on some feeds.
const isSpringTraining = (log) =>
  log?.game_type === 'S' ||
  log?.opponent_abbreviation === 'SIM' ||
  log?.opponent === 'Simulated'

// Short date label for the trend chart — "Apr 16"
const trendDateFmt = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

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

  const {
    pitcher,
    current_fatigue: cf,
    recent_logs,
    fatigue_trend,
  } = data || {}

  // Radar — component breakdown
  const radarData = cf ? [
    { component: 'Pitches',  value: Math.round(cf.pitch_count_score ?? 0) },
    { component: 'Rest',     value: Math.round(cf.rest_days_score ?? 0)   },
    { component: 'Apps',     value: Math.round(cf.appearances_score ?? 0) },
    { component: 'Leverage', value: Math.round(cf.leverage_score ?? 0)    },
    { component: 'Innings',  value: Math.round(cf.innings_score ?? 0)     },
  ] : []

  // Trend — sorted ascending by date for a clean left-to-right line
  const trendData = (fatigue_trend ?? [])
    .filter(s => s?.calculated_at && s?.raw_score != null)
    .map(s => ({
      date:  trendDateFmt(s.calculated_at),
      score: Math.round(s.raw_score),
      iso:   s.calculated_at,
      risk:  s.risk_level,
    }))
    .sort((a, b) => new Date(a.iso) - new Date(b.iso))

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
              { label: 'Days Rest',  value: cf.days_since_last_appearance != null ? `${cf.days_since_last_appearance}d` : '---' },
              { label: 'Pitches/7d', value: cf.pitches_last_7_days ?? 0 },
              { label: 'Apps/7d',    value: cf.appearances_last_7 ?? 0 },
              { label: 'IP/7d',      value: fmtIP(cf.innings_last_7_days) },
              { label: 'Apps/14d',   value: cf.appearances_last_14 ?? 0 },
              { label: 'Avg LI',     value: cf.avg_leverage_last_7 ? cf.avg_leverage_last_7.toFixed(2) : '---' },
            ].map(({ label, value }) => (
              <div key={label} className="bg-chalk/40 border border-dirt rounded p-2.5 text-center">
                <div className="font-mono font-semibold text-chalk200">{value}</div>
                <div className="text-chalk600 text-[10px] font-mono mt-0.5">{label}</div>
              </div>
            ))}
          </div>

          {/* Component breakdown — horizontal bars with weights */}
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

          {/* Radar — component profile */}
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

          {/* Trend chart — fatigue_trend from API */}
          {trendData.length > 1 && (
            <>
              <Divider label="Fatigue Trend" />
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
                    <CartesianGrid stroke="#242b35" strokeDasharray="3 3" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: '#8899aa', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                      tickLine={{ stroke: '#242b35' }}
                      axisLine={{ stroke: '#242b35' }}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tick={{ fill: '#8899aa', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                      tickLine={{ stroke: '#242b35' }}
                      axisLine={{ stroke: '#242b35' }}
                      width={30}
                    />
                    <ReferenceLine
                      y={81}
                      stroke="#dc2626"
                      strokeDasharray="4 4"
                      label={{
                        value: 'CRITICAL',
                        position: 'insideTopRight',
                        fill: '#f87171',
                        fontFamily: 'JetBrains Mono',
                        fontSize: 10,
                        fontWeight: 600,
                      }}
                    />
                    <Tooltip
                      contentStyle={{ background: '#111418', border: '1px solid #242b35', borderRadius: '6px', fontFamily: 'JetBrains Mono', fontSize: '11px' }}
                      labelStyle={{ color: '#d1dce8' }}
                      itemStyle={{ color: '#f5a623' }}
                      formatter={(value) => [`${value}`, 'Score']}
                    />
                    <Line
                      type="monotone"
                      dataKey="score"
                      stroke="#f5a623"
                      strokeWidth={2}
                      dot={{ r: 3, fill: '#f5a623', stroke: '#f5a623' }}
                      activeDot={{ r: 5, fill: '#f5a623', stroke: '#111418', strokeWidth: 2 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </>
          )}

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
                      <th className="text-right">LI</th>
                      <th>Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent_logs.slice(0, 8).map(log => {
                      const st = isSpringTraining(log)
                      const li = log.leverage_index
                      const highLev = li != null && li > 1.5
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
                          <td className="text-right font-mono text-xs text-chalk200">{fmtIP(log.innings_pitched)}</td>
                          <td className="text-right font-mono text-xs text-chalk200">{log.pitches_thrown ?? 0}</td>
                          <td className="text-right font-mono text-xs">
                            {li != null ? (
                              <span className={highLev ? 'text-amber font-semibold' : 'text-chalk400'}>
                                {li.toFixed(2)}
                              </span>
                            ) : (
                              <span className="text-chalk600">---</span>
                            )}
                          </td>
                          <td className="font-mono text-[10px]">
                            {highLev ? (
                              <span
                                className="px-1.5 py-0.5 rounded uppercase tracking-wider"
                                style={{ backgroundColor: 'rgba(245,166,35,0.12)', color: '#f5a623', border: '1px solid rgba(245,166,35,0.3)' }}
                              >
                                High Leverage
                              </span>
                            ) : (
                              <span className="text-chalk600">—</span>
                            )}
                          </td>
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
          No fatigue data available yet.
        </div>
      )}
    </div>
  )
}
