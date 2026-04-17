import { fatigueBarColor } from '../../utils/formatters'

export default function FatigueBar({ score, showLabel = false, height = 'h-1.5' }) {
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
