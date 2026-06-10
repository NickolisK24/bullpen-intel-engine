import { getBullpenStressView } from './tonightsBullpenBoardView'

export default function BullpenStressSummary({ stress, compact = false }) {
  const view = getBullpenStressView(stress)
  if (!view.hasStress) return null

  const visibleReasons = compact ? view.reasons.slice(0, 2) : view.reasons

  return (
    <section
      className={compact ? 'rounded border p-3' : 'mb-5 rounded-lg border p-4'}
      style={view.tone}
      aria-label="Bullpen Stress"
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: view.tone.dot }} aria-hidden="true" />
          <span className="font-mono text-[10px] uppercase tracking-widest">
            Bullpen Stress: {view.label}
          </span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest">
          Workload Read: {view.confidenceLabel}
        </span>
      </div>

      <p className="mt-2 text-sm leading-relaxed">{view.summary}</p>

      {view.isLimited && (
        <p className="mt-2 font-mono text-[11px] uppercase tracking-wider">
          Limited read - review freshness before treating this as current.
        </p>
      )}

      {visibleReasons.length > 0 && (
        <ul className={compact ? 'mt-2 list-disc space-y-1 pl-4' : 'mt-3 list-disc space-y-1 pl-4'}>
          {visibleReasons.map((reason, index) => (
            <li key={index} className="text-xs leading-relaxed text-chalk300">{reason}</li>
          ))}
        </ul>
      )}

      {view.limitations.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-4">
          {view.limitations.map((limitation, index) => (
            <li key={index} className="text-xs leading-relaxed text-chalk400">{limitation}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
