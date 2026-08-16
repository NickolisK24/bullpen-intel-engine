import { getRestStatusView } from './tonightsBullpenBoardView'

export default function RestStatus({ restStatus }) {
  const view = getRestStatusView(restStatus)

  return (
    <section className="rounded-lg border border-dirt bg-field/40 p-3.5" aria-labelledby="rest-status-title">
      <h2 id="rest-status-title" className="font-display text-lg tracking-wide text-chalk100">Rest Status</h2>
      {!view.available ? (
        <p className="mt-2 text-xs text-chalk500">Rest status unavailable</p>
      ) : (
        <>
          <dl className="mt-2 grid grid-cols-3 gap-2 text-center">
            <div className="rounded border border-dirt/70 bg-dugout/50 px-2 py-2"><dt className="font-mono text-[9px] uppercase tracking-wide text-chalk500">Rested</dt><dd className="mt-1 font-display text-xl leading-none text-chalk100">{view.rested_arm_count}</dd></div>
            <div className="rounded border border-dirt/70 bg-dugout/50 px-2 py-2"><dt className="font-mono text-[9px] uppercase tracking-wide text-chalk500">Worked yesterday</dt><dd className="mt-1 font-display text-xl leading-none text-chalk100">{view.worked_yesterday_count}</dd></div>
            <div className="rounded border border-dirt/70 bg-dugout/50 px-2 py-2"><dt className="font-mono text-[9px] uppercase tracking-wide text-chalk500">Back-to-back</dt><dd className="mt-1 font-display text-xl leading-none text-chalk100">{view.back_to_back_count}</dd></div>
          </dl>
          <p className="mt-2 text-xs leading-relaxed text-chalk400">{view.summary}</p>
        </>
      )}
    </section>
  )
}
