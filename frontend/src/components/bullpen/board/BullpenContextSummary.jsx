import { getBoardContextView } from './tonightsBullpenBoardView'

// Team Context Layer (Board V2). Sits between the freshness banner and the
// availability groups. Presents a deterministic, self-explaining read of
// bullpen shape — never a ranking, selection, or recommendation.
export default function BullpenContextSummary({ board, showHealthSummary = true }) {
  const view = getBoardContextView(board)
  if (!view.hasContext) return null

  return (
    <section className="mb-6" aria-label={showHealthSummary ? 'Team bullpen context' : 'Bullpen availability snapshot'}>
      {showHealthSummary && (
        <div className="rounded-lg border p-4" style={view.tone} role="status" aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 font-display text-lg tracking-wide">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: view.tone.dot }} aria-hidden="true" />
              {view.label || 'Bullpen context unavailable.'}
            </h3>
            <span className="font-mono text-[10px] uppercase tracking-widest">
              Workload Read: {view.confidenceLabel}
            </span>
          </div>

          {view.isDegraded && (
            <p className="mt-2 font-mono text-[11px] uppercase tracking-wider">
              Unclear read - treat this snapshot with caution.
            </p>
          )}

          {view.reasons.length > 0 && (
            <details className="mt-3 rounded border border-dirt/60 bg-dugout/50 p-2" open>
              <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-chalk500 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
                Why?
              </summary>
              <ul className="mt-2 space-y-1">
                {view.reasons.map((reason, index) => (
                  <li key={index} className="text-xs leading-relaxed text-chalk300">• {reason}</li>
                ))}
              </ul>
            </details>
          )}

          {view.limitations.length > 0 && (
            <ul className="mt-2 space-y-1">
              {view.limitations.map((limitation, index) => (
                <li key={index} className="text-xs leading-relaxed text-chalk400">• {limitation}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Bullpen Snapshot — descriptive counts only. */}
      <div className={showHealthSummary ? 'mt-4 card p-4' : 'card p-4'}>
        <div className="flex items-baseline justify-between">
          <h4 className="font-mono text-xs uppercase tracking-widest text-chalk400">Bullpen Snapshot</h4>
          <span className="font-mono text-[11px] text-chalk500">
            {view.metrics.total} reliever{view.metrics.total === 1 ? '' : 's'}
            {view.metrics.total > 0 ? ` · ${view.metrics.pctAvailable}% available` : ''}
          </span>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          {view.snapshot.map(row => (
            <div key={row.status} className="rounded border border-dirt bg-field/50 px-3 py-2">
              <dt className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-chalk500">
                <span className="h-1.5 w-1.5 rounded-full" style={row.badge.dotStyle} aria-hidden="true" />
                {row.label}
              </dt>
              <dd className="mt-1 font-mono text-2xl text-chalk100">{row.count}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}
