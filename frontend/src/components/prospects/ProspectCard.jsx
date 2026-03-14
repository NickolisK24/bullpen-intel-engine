import { GradeBox, Divider } from '../UI'
import { fmtAvg, fmtEra, levelColor } from '../../utils/formatters'

export default function ProspectCard({ prospect: p, onClose }) {
  if (!p) return null
  const isPitcher = ['SP', 'RP', 'CL', 'P'].includes(p.position)

  return (
    <div className="card sticky top-6 max-h-[calc(100vh-3rem)] overflow-y-auto">
      <div className="card-header">
        <div>
          <div className="text-chalk400 font-mono text-xs mb-1">{p.team_name}</div>
          <div className="font-display text-2xl tracking-wider text-chalk100">{p.full_name}</div>
          <div className="flex flex-wrap gap-2 mt-1.5 font-mono text-xs text-chalk400">
            <span>{p.position}</span>
            {p.bats && <><span>·</span><span>B: {p.bats}</span></>}
            {p.throws && <><span>·</span><span>T: {p.throws}</span></>}
            {p.age && <><span>·</span><span>Age {p.age}</span></>}
          </div>
        </div>
        <button onClick={onClose} className="text-chalk400 hover:text-chalk200 text-lg">✕</button>
      </div>

      <div className="p-5 space-y-5">
        {/* Level + ETA */}
        <div className="flex items-center gap-4">
          <div className={`font-display text-4xl tracking-wider ${levelColor(p.current_level)}`}>{p.current_level}</div>
          {p.eta_year && (
            <div className="bg-amber/10 border border-amber/30 rounded px-3 py-1.5">
              <div className="font-mono text-xs text-amber/70">MLB ETA</div>
              <div className="font-display text-xl tracking-wider text-amber">{p.eta_year}</div>
            </div>
          )}
          <div className="ml-auto">
            <div className="font-mono text-xs text-chalk600 mb-1">Overall</div>
            <div className="font-display text-5xl tracking-wider text-amber">{p.grades?.overall ?? '--'}</div>
          </div>
        </div>

        {/* Scouting grades */}
        <div>
          <div className="text-chalk600 font-mono text-xs uppercase tracking-widest mb-3">Scouting Grades (20-80)</div>
          <div className="flex flex-wrap gap-2">
            {isPitcher ? (
              <>
                <GradeBox grade={p.grades?.arm}   label="Arm" />
                <GradeBox grade={p.grades?.field} label="Fld" />
                <GradeBox grade={p.grades?.speed} label="Spd" />
              </>
            ) : (
              <>
                <GradeBox grade={p.grades?.hit}   label="Hit" />
                <GradeBox grade={p.grades?.power} label="Pwr" />
                <GradeBox grade={p.grades?.speed} label="Spd" />
                <GradeBox grade={p.grades?.field} label="Fld" />
                <GradeBox grade={p.grades?.arm}   label="Arm" />
              </>
            )}
          </div>
        </div>

        {/* Stats */}
        <Divider label="Current Season Stats" />
        {isPitcher ? (
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: 'ERA',   value: fmtEra(p.stats?.era) },
              { label: 'WHIP',  value: p.stats?.whip?.toFixed(2) ?? '---' },
              { label: 'K/9',   value: p.stats?.k_per_9?.toFixed(1) ?? '---' },
              { label: 'BB/9',  value: p.stats?.bb_per_9?.toFixed(1) ?? '---' },
              { label: 'IP',    value: p.stats?.innings_pitched?.toFixed(1) ?? '---' },
              { label: 'FIP',   value: p.stats?.fip?.toFixed(2) ?? '---' },
            ].map(({ label, value }) => (
              <div key={label} className="bg-chalk/40 border border-dirt rounded p-3">
                <div className="font-mono font-semibold text-chalk200">{value}</div>
                <div className="text-chalk600 text-xs font-mono mt-0.5">{label}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: 'AVG',   value: fmtAvg(p.stats?.batting_average) },
              { label: 'OBP',   value: fmtAvg(p.stats?.on_base_pct) },
              { label: 'SLG',   value: fmtAvg(p.stats?.slugging_pct) },
              { label: 'OPS',   value: fmtAvg(p.stats?.ops) },
              { label: 'HR',    value: p.stats?.home_runs ?? '---' },
              { label: 'RBI',   value: p.stats?.rbi ?? '---' },
              { label: 'SB',    value: p.stats?.stolen_bases ?? '---' },
              { label: 'K%',    value: p.stats?.strikeout_rate ? `${(p.stats.strikeout_rate * 100).toFixed(1)}%` : '---' },
            ].map(({ label, value }) => (
              <div key={label} className="bg-chalk/40 border border-dirt rounded p-3">
                <div className="font-mono font-semibold text-chalk200">{value}</div>
                <div className="text-chalk600 text-xs font-mono mt-0.5">{label}</div>
              </div>
            ))}
          </div>
        )}

        {p.notes && (
          <>
            <Divider label="Scout Notes" />
            <p className="text-chalk400 text-xs leading-relaxed font-mono">{p.notes}</p>
          </>
        )}
      </div>
    </div>
  )
}
