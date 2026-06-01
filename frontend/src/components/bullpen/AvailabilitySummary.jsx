import AvailabilityBadge from './AvailabilityBadge'
import { getAvailabilitySummary } from './availabilityView'

function FactList({ items, emptyText }) {
  if (!items.length) {
    return <div className="text-chalk600 text-xs font-mono leading-relaxed">{emptyText}</div>
  }

  return (
    <ul className="space-y-1.5">
      {items.map((item, index) => (
        <li key={`${item}-${index}`} className="flex gap-2 text-xs font-mono leading-relaxed text-chalk200">
          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber/70" aria-hidden="true" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

export default function AvailabilitySummary({ availability }) {
  const summary = getAvailabilitySummary(availability)

  return (
    <section className="rounded border border-dirt bg-chalk/30 p-4">
      <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Availability Status</div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <AvailabilityBadge availability={availability} />
            <span className="text-chalk400 text-xs font-mono leading-relaxed">{summary.tone}</span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:min-w-[12rem]">
          <div className="rounded border border-dirt bg-field/60 p-2">
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Confidence</div>
            <div className="mt-1 font-mono text-xs font-semibold text-chalk200">{summary.confidenceLabel}</div>
          </div>
          <div className="rounded border border-dirt bg-field/60 p-2">
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Data Status</div>
            <div className="mt-1 font-mono text-xs font-semibold text-chalk200">{summary.dataStateView.label}</div>
          </div>
        </div>
      </div>

      <div className="mb-4 rounded border border-dirt bg-field/40 px-3 py-2 text-xs font-mono leading-relaxed text-chalk400">
        {summary.dataStateView.message}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <div className="mb-2 text-chalk600 text-[10px] font-mono uppercase tracking-wider">Reasons</div>
          <FactList
            items={summary.reasons}
            emptyText="No workload restriction reasons were reported by the backend."
          />
        </div>
        <div>
          <div className="mb-2 text-chalk600 text-[10px] font-mono uppercase tracking-wider">Limitations</div>
          <FactList
            items={summary.limitations}
            emptyText="No additional limitations were reported by the backend."
          />
        </div>
      </div>
    </section>
  )
}
