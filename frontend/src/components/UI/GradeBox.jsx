// 20-80 scouting scale grade display.
export default function GradeBox({ grade, label }) {
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
