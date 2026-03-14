import { fatigueBarColor, riskBadgeClass, riskColor } from '../utils/formatters'

// ── Loading ───────────────────────────────────────────────────
export function Spinner({ size = 'md' }) {
  const s = { sm: 'w-4 h-4', md: 'w-7 h-7', lg: 'w-10 h-10' }[size]
  return (
    <div className={`${s} border-2 border-dirt border-t-amber rounded-full animate-spin`} />
  )
}

export function LoadingPane({ label = 'Loading...' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-chalk400">
      <Spinner size="lg" />
      <span className="font-mono text-xs tracking-widest uppercase">{label}</span>
    </div>
  )
}

// ── Error / Empty ─────────────────────────────────────────────
export function ErrorState({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
      <div className="text-3xl">⚠️</div>
      <p className="text-chalk400 text-sm font-mono">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="px-4 py-2 bg-chalk border border-dirt rounded text-chalk200 text-xs font-mono hover:border-amber/40 transition-colors">
          Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ icon = '⚾', title, subtitle }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="text-4xl opacity-30">{icon}</div>
      {title && <p className="text-chalk200 font-medium">{title}</p>}
      {subtitle && <p className="text-chalk400 text-sm">{subtitle}</p>}
    </div>
  )
}

// ── Fatigue Bar ───────────────────────────────────────────────
export function FatigueBar({ score, showLabel = false, height = 'h-1.5' }) {
  const pct = Math.min(100, Math.max(0, score || 0))
  const color = fatigueBarColor(pct)
  return (
    <div className="flex items-center gap-2 w-full">
      <div className={`flex-1 fatigue-bar-track ${height}`}>
        <div
          className={`h-full ${color} rounded-full transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && (
        <span className="font-mono text-xs text-chalk400 w-7 text-right">{Math.round(pct)}</span>
      )}
    </div>
  )
}

// ── Risk Badge ────────────────────────────────────────────────
export function RiskBadge({ level }) {
  const cls = riskBadgeClass(level)
  const dots = { LOW: 1, MODERATE: 2, HIGH: 3, CRITICAL: 4 }[level] || 1
  return (
    <span className={cls}>
      {'●'.repeat(dots)}{'○'.repeat(4 - dots)} {level}
    </span>
  )
}

// ── Stat Card ─────────────────────────────────────────────────
export function StatCard({ label, value, sub, accent = false, delay = 0, icon }) {
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

// ── Section Header ────────────────────────────────────────────
export function SectionHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-end justify-between mb-6">
      <div>
        <h2 className="section-title">{title}</h2>
        {subtitle && <p className="text-chalk400 text-sm mt-1 font-mono">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

// ── Grade Box (20-80 scouting scale) ──────────────────────────
export function GradeBox({ grade, label }) {
  const color = !grade ? 'border-dirt text-chalk600'
    : grade >= 70 ? 'border-amber/50 text-amber bg-amber/10'
    : grade >= 60 ? 'border-emerald-500/40 text-emerald-400 bg-emerald-400/10'
    : grade >= 50 ? 'border-chalk400/30 text-chalk200 bg-chalk/50'
    : 'border-dirt text-chalk400'

  return (
    <div className={`flex flex-col items-center gap-0.5 border rounded p-2 min-w-[52px] ${color}`}>
      <span className="font-mono font-semibold text-lg leading-none">{grade ?? '--'}</span>
      <span className="text-[10px] uppercase tracking-wider opacity-70">{label}</span>
    </div>
  )
}

// ── Divider ───────────────────────────────────────────────────
export function Divider({ label }) {
  return (
    <div className="flex items-center gap-3 my-4">
      {label && <span className="text-chalk600 text-xs font-mono uppercase tracking-widest whitespace-nowrap">{label}</span>}
      <div className="flex-1 border-t border-dirt" />
    </div>
  )
}
