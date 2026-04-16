import { useFetch } from '../../hooks/useFetch'
import { getPortfolio } from '../../utils/api'
import { LoadingPane, ErrorState, SectionHeader, Divider } from '../UI'

export default function Portfolio() {
  const { data, loading, error } = useFetch(getPortfolio)

  if (loading) return <LoadingPane message="Loading portfolio..." />
  if (error)   return <div className="p-8"><ErrorState message={error} /></div>

  const p = data

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <SectionHeader title="Portfolio" subtitle="The work, the method, and the mission." />

      {/* Hero — About */}
      <div className="relative overflow-hidden rounded-xl border border-dirt bg-dugout p-8 mb-8 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
        <div className="absolute inset-0 bg-stadium-glow pointer-events-none" />
        <div className="absolute inset-0 bg-grid-lines bg-grid-lines opacity-100 pointer-events-none" />
        <div className="relative z-10">
          <div className="font-mono text-xs text-amber/60 uppercase tracking-widest mb-2">Builder</div>
          <h2 className="font-display text-5xl tracking-wider text-chalk100 mb-4">{p?.name}</h2>
          <p className="text-amber font-mono text-sm mb-5">{p?.title}</p>
          <div className="space-y-2">
            {p?.background?.map((line, i) => (
              <div key={i} className="flex items-start gap-3">
                <span className="text-amber mt-1 shrink-0">▸</span>
                <p className="text-chalk200 text-sm leading-relaxed">{line}</p>
              </div>
            ))}
          </div>
          <div className="mt-6 p-4 bg-amber/5 border border-amber/20 rounded-lg">
            <div className="text-amber font-mono text-xs uppercase tracking-widest mb-2">Mission</div>
            <p className="text-chalk200 text-sm leading-relaxed">{p?.goal}</p>
          </div>
        </div>
      </div>

      {/* Tech Stack */}
      <div className="card p-6 mb-6 animate-fade-up opacity-0 delay-1" style={{ animationFillMode: 'forwards' }}>
        <div className="font-mono text-xs text-chalk400 uppercase tracking-widest mb-4">Stack</div>
        <div className="flex flex-wrap gap-2">
          {p?.stack?.map(tech => (
            <span key={tech} className="px-3 py-1.5 bg-chalk border border-dirt rounded-full font-mono text-sm text-chalk200 hover:border-amber/40 transition-colors">
              {tech}
            </span>
          ))}
        </div>
      </div>

      {/* Projects */}
      <div className="mb-8 animate-fade-up opacity-0 delay-2" style={{ animationFillMode: 'forwards' }}>
        <div className="font-mono text-xs text-chalk400 uppercase tracking-widest mb-4">Projects</div>
        <div className="space-y-3">
          {p?.projects?.map((proj, i) => (
            <div key={i} className="card p-5 hover:border-amber/20 transition-colors">
              <div className="flex items-start justify-between mb-2">
                <div className="font-display text-xl tracking-wider text-chalk100">{proj.name}</div>
                <span className={`px-2 py-0.5 rounded border font-mono text-xs ${
                  proj.status === 'Active' ? 'bg-emerald-400/10 border-emerald-400/30 text-emerald-400' :
                  proj.status === 'In Progress' ? 'bg-amber/10 border-amber/30 text-amber' :
                  'bg-chalk border-dirt text-chalk400'
                }`}>{proj.status}</span>
              </div>
              <p className="text-chalk400 text-sm mb-3">{proj.description}</p>
              <div className="flex flex-wrap gap-1.5">
                {proj.tech?.map(t => <span key={t} className="stat-chip">{t}</span>)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Methodology — Fatigue Engine */}
      {p?.methodology?.fatigue_engine && (
        <div className="animate-fade-up opacity-0 delay-3" style={{ animationFillMode: 'forwards' }}>
          <div className="font-mono text-xs text-chalk400 uppercase tracking-widest mb-4">Methodology</div>
          <div className="card overflow-hidden">
            <div className="card-header bg-amber/5">
              <div>
                <div className="font-display text-2xl tracking-wider text-chalk100">{p.methodology.fatigue_engine.title}</div>
                <p className="text-chalk400 text-sm mt-1 max-w-2xl">{p.methodology.fatigue_engine.summary}</p>
              </div>
            </div>

            <div className="p-6 space-y-6">
              {/* Components table */}
              <div>
                <div className="font-mono text-xs text-chalk600 uppercase tracking-widest mb-3">Score Components</div>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Component</th>
                      <th>Weight</th>
                      <th>Rationale</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.methodology.fatigue_engine.components?.map(c => (
                      <tr key={c.name}>
                        <td className="text-amber font-mono text-xs font-medium">{c.name}</td>
                        <td className="font-display text-lg text-chalk100 tracking-wider">{c.weight}</td>
                        <td className="text-chalk400 text-xs">{c.rationale}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Divider label="Risk Tiers" />

              {/* Risk tiers */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {p.methodology.fatigue_engine.risk_tiers?.map(tier => {
                  const colors = {
                    LOW: { border: 'border-emerald-500/30', bg: 'bg-emerald-400/5', text: 'text-emerald-400' },
                    MODERATE: { border: 'border-amber-400/30', bg: 'bg-amber-400/5', text: 'text-amber-400' },
                    HIGH: { border: 'border-orange-400/30', bg: 'bg-orange-400/5', text: 'text-orange-400' },
                    CRITICAL: { border: 'border-red-500/30', bg: 'bg-red-500/5', text: 'text-red-400' },
                  }[tier.level]
                  return (
                    <div key={tier.level} className={`border rounded-lg p-4 ${colors.border} ${colors.bg}`}>
                      <div className={`font-mono text-xs font-semibold mb-1 ${colors.text}`}>{tier.level}</div>
                      <div className="font-display text-2xl tracking-wider text-chalk100 mb-1">{tier.range}</div>
                      <div className="text-chalk400 text-xs">{tier.interpretation}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Contact */}
      {p?.contact && (
        <div className="mt-8 card p-6 animate-fade-up opacity-0 delay-4" style={{ animationFillMode: 'forwards' }}>
          <div className="font-mono text-xs text-chalk400 uppercase tracking-widest mb-4">Contact</div>
          <div className="flex flex-wrap gap-3">
            {p.contact.github && (
              <a href={p.contact.github} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-2 px-4 py-2 bg-chalk border border-dirt rounded hover:border-amber/40 transition-colors text-chalk200 text-sm font-mono">
                <span>⬡</span> GitHub
              </a>
            )}
            {p.contact.linkedin && (
              <a href={p.contact.linkedin} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-2 px-4 py-2 bg-chalk border border-dirt rounded hover:border-amber/40 transition-colors text-chalk200 text-sm font-mono">
                <span>◈</span> LinkedIn
              </a>
            )}
            {p.contact.email && (
              <a href={`mailto:${p.contact.email}`}
                className="flex items-center gap-2 px-4 py-2 bg-amber/10 border border-amber/30 rounded hover:bg-amber/20 transition-colors text-amber text-sm font-mono">
                <span>✉</span> {p.contact.email}
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
