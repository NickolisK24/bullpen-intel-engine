export default function StatCard({ label, value, sub, accent = false, delay = 0, icon }) {
  return (
    <div
      className={`card p-5 animate-fade-up opacity-0 ${accent ? 'border-amber/30 bg-amber/5' : ''}`}
      style={{ animationDelay: `${delay}ms`, animationFillMode: 'forwards' }}
    >
      <div className="flex items-start justify-between mb-3">
        <span className="text-chalk400 font-mono text-xs uppercase tracking-widest">{label}</span>
        {icon && <span className="text-lg opacity-50">{icon}</span>}
      </div>
      <div className={`font-display text-4xl tracking-wider ${accent ? 'text-gradient-amber glow-amber' : 'text-chalk100'}`}>
        {value ?? '---'}
      </div>
      {sub && <div className="mt-1 text-chalk400 text-xs font-mono">{sub}</div>}
    </div>
  )
}
