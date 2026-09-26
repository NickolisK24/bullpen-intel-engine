import { TONIGHT_COPY, leadView } from './tonightView'

export default function LeadDevelopment({ lead }) {
  const view = leadView(lead)
  if (!view) return null
  return (
    <section
      className="mt-section min-w-0 rounded border border-amber/40 bg-dugout p-4 sm:p-5"
      aria-labelledby="tonight-lead-heading"
      data-testid="tonight-lead"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
        <h2 id="tonight-lead-heading" className="font-mono text-xs uppercase tracking-widest text-amber">
          Lead development
        </h2>
        {view.pregame && (
          <span className="font-mono text-[11px] uppercase tracking-wider text-chalk300" data-testid="tonight-lead-pregame">
            {TONIGHT_COPY.pregame}
          </span>
        )}
      </div>
      <p className="mt-2 break-words font-display text-2xl leading-tight tracking-wide text-chalk100 sm:text-3xl">
        {view.headline}
      </p>
      {view.detail && (
        <p className="mt-2 break-words text-sm leading-relaxed text-chalk300">{view.detail}</p>
      )}
    </section>
  )
}
