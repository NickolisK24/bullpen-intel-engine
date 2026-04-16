import { useState } from 'react'
import { useFetch } from '../../hooks/useFetch'
import { getProspectPipeline, getProspects } from '../../utils/api'
import { LoadingPane, ErrorState, SectionHeader, GradeBox, Divider } from '../UI'
import { levelColor, fmtAvg, fmtEra, gradeColor } from '../../utils/formatters'
import ProspectCard from './ProspectCard'

const LEVELS = ['ROK', 'A', 'A+', 'AA', 'AAA', 'MLB']

export default function Prospects() {
  const [selectedLevel, setSelectedLevel] = useState(null)
  const [selectedProspect, setSelected]   = useState(null)
  const [viewMode, setViewMode]           = useState('pipeline') // pipeline | list

  const pipeline = useFetch(getProspectPipeline)
  const all      = useFetch(() => getProspects({ limit: 200 }))

  const displayProspects = selectedLevel
    ? (pipeline.data?.pipeline?.[selectedLevel] ?? [])
    : (viewMode === 'list' ? (all.data ?? []) : null)

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <SectionHeader
        title="Pipeline"
        subtitle="Prospect development tracker · 20-80 scouting scale"
        action={
          <div className="flex gap-1 bg-chalk/30 p-1 rounded-lg border border-dirt">
            {['pipeline', 'list'].map(m => (
              <button key={m} onClick={() => setViewMode(m)}
                className={`px-3 py-1.5 rounded text-xs font-mono capitalize transition-all ${viewMode === m ? 'bg-chalk border-dirt text-chalk200 shadow' : 'text-chalk400 hover:text-chalk200'}`}
              >
                {m}
              </button>
            ))}
          </div>
        }
      />

      {pipeline.loading ? <LoadingPane message="Loading pipeline..." /> : pipeline.error ? <ErrorState message={pipeline.error} onRetry={pipeline.refetch} /> : (
        <>
          {/* Level selector */}
          <div className="grid grid-cols-6 gap-2 mb-8 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
            {LEVELS.map(lvl => {
              const count = pipeline.data?.pipeline?.[lvl]?.length ?? 0
              const isActive = selectedLevel === lvl
              return (
                <button
                  key={lvl}
                  onClick={() => setSelectedLevel(isActive ? null : lvl)}
                  className={`card p-4 text-center transition-all duration-200 hover:border-amber/30 ${isActive ? 'border-amber/50 bg-amber/5' : ''}`}
                >
                  <div className={`font-display text-3xl tracking-wider ${isActive ? 'text-amber' : levelColor(lvl)}`}>{lvl}</div>
                  <div className="font-mono text-xs text-chalk600 mt-1">{count} prospects</div>
                </button>
              )
            })}
          </div>

          {viewMode === 'pipeline' && !selectedLevel ? (
            // Full pipeline board view
            <div>
              {LEVELS.map((lvl, li) => {
                const prospects = pipeline.data?.pipeline?.[lvl] ?? []
                if (!prospects.length) return null
                return (
                  <div key={lvl} className="mb-8 animate-fade-up opacity-0" style={{ animationDelay: `${li * 80}ms`, animationFillMode: 'forwards' }}>
                    <div className="flex items-center gap-3 mb-4">
                      <span className={`font-display text-2xl tracking-widest ${levelColor(lvl)}`}>{lvl}</span>
                      <div className="flex-1 border-t border-dirt" />
                      <span className="font-mono text-xs text-chalk600">{prospects.length} players</span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                      {prospects.slice(0, 8).map(p => (
                        <ProspectMiniCard
                          key={p.id} prospect={p}
                          onClick={() => setSelected(selectedProspect?.id === p.id ? null : p)}
                          selected={selectedProspect?.id === p.id}
                        />
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            // Filtered / list view
            <div className="flex gap-6">
              <div className="flex-1">
                {selectedLevel && (
                  <div className="flex items-center gap-3 mb-5">
                    <span className={`font-display text-4xl tracking-wider ${levelColor(selectedLevel)}`}>{selectedLevel}</span>
                    <button onClick={() => setSelectedLevel(null)} className="text-chalk600 hover:text-chalk400 text-xs font-mono">← All Levels</button>
                  </div>
                )}
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                  {(displayProspects ?? []).map(p => (
                    <ProspectMiniCard
                      key={p.id} prospect={p}
                      onClick={() => setSelected(selectedProspect?.id === p.id ? null : p)}
                      selected={selectedProspect?.id === p.id}
                    />
                  ))}
                </div>
              </div>

              {selectedProspect && (
                <div className="hidden lg:block w-80 shrink-0">
                  <ProspectCard prospect={selectedProspect} onClose={() => setSelected(null)} />
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ProspectMiniCard({ prospect: p, onClick, selected }) {
  const pos = p.position
  const isPitcher = ['SP', 'RP', 'CL', 'P'].includes(pos)

  return (
    <div
      onClick={onClick}
      className={`card p-4 cursor-pointer hover:border-amber/30 transition-all duration-200 ${selected ? 'border-amber/40 bg-amber/5' : ''}`}
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="text-chalk200 font-medium text-sm">{p.full_name}</div>
          <div className="text-chalk600 font-mono text-xs mt-0.5">{p.team_abbreviation} · {pos}</div>
        </div>
        <div className={`font-display text-2xl tracking-wider ${gradeColor(p.grades?.overall)}`}>
          {p.grades?.overall ?? '--'}
        </div>
      </div>

      <div className={`font-mono text-xs ${levelColor(p.current_level)} mb-3`}>{p.current_level}</div>

      {/* Mini stat line */}
      <div className="flex gap-2 font-mono text-xs">
        {isPitcher ? (
          <>
            {p.stats?.era   != null && <span className="stat-chip">ERA {fmtEra(p.stats.era)}</span>}
            {p.stats?.whip  != null && <span className="stat-chip">WHIP {p.stats.whip?.toFixed(2)}</span>}
            {p.stats?.k_per_9 != null && <span className="stat-chip">K/9 {p.stats.k_per_9?.toFixed(1)}</span>}
          </>
        ) : (
          <>
            {p.stats?.batting_average != null && <span className="stat-chip">AVG {fmtAvg(p.stats.batting_average)}</span>}
            {p.stats?.ops != null && <span className="stat-chip">OPS {fmtAvg(p.stats.ops)}</span>}
            {p.stats?.home_runs != null && <span className="stat-chip">{p.stats.home_runs} HR</span>}
          </>
        )}
        {p.eta_year && <span className="stat-chip text-amber/70">ETA {p.eta_year}</span>}
      </div>
    </div>
  )
}
