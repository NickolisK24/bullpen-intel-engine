import AvailabilityBadge from './AvailabilityBadge'
import { getAvailabilitySummary, getRosterStatusSummary } from './availabilityView'

function FactList({ items, emptyText, variant = 'reason' }) {
  if (!items.length) {
    return <div className="text-chalk600 text-xs font-mono leading-relaxed">{emptyText}</div>
  }

  const bulletClass = variant === 'limitation'
    ? 'border border-chalk600 text-chalk400'
    : 'bg-amber/15 text-amber'

  return (
    <ol className="space-y-2">
      {items.map((item, index) => (
        <li key={`${item}-${index}`} className="flex gap-2 text-xs font-mono leading-relaxed text-chalk200">
          <span
            className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${bulletClass}`}
            aria-hidden="true"
          >
            {variant === 'limitation' ? '!' : index + 1}
          </span>
          <span>{item}</span>
        </li>
      ))}
    </ol>
  )
}

export default function AvailabilitySummary({
  availability,
  workloadSignal = null,
  rosterStatus = null,
}) {
  const summary = getAvailabilitySummary(availability)
  const workloadSummary = workloadSignal ? getAvailabilitySummary(workloadSignal) : null
  const resolvedRosterStatus = getRosterStatusSummary(
    rosterStatus || availability?.roster_status,
  )
  const isCurrentData = summary.dataStateView.label === 'Fresh'

  return (
    <section className="rounded border border-dirt bg-chalk/30 p-4 sm:p-5">
      <div className="mb-4 flex flex-col gap-4">
        <div className="min-w-0">
          <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Final Availability</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <AvailabilityBadge availability={availability} ariaLabelPrefix="Final availability" />
          </div>
          <p className="mt-3 max-w-xl text-xs font-mono leading-relaxed text-chalk400">
            {summary.tone}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:max-w-xl">
          <div className="rounded border border-dirt bg-field/60 p-2">
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Roster Status</div>
            <div className="mt-1 font-mono text-xs font-semibold text-chalk200">
              {resolvedRosterStatus?.label || 'Roster Unknown'}
            </div>
          </div>
          <div className="rounded border border-dirt bg-field/60 p-2">
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Confidence</div>
            <div className="mt-1 font-mono text-xs font-semibold text-chalk200">{summary.confidenceLabel}</div>
          </div>
          <div className={`rounded border bg-field/60 p-2 ${isCurrentData ? 'border-dirt' : 'border-amber/40'}`}>
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Data Status</div>
            <div className="mt-1 font-mono text-xs font-semibold text-chalk200">{summary.dataStateView.label}</div>
          </div>
        </div>
      </div>

      <div className={`mb-4 rounded border px-3 py-2 text-xs font-mono leading-relaxed ${
        isCurrentData
          ? 'border-dirt bg-field/40 text-chalk400'
          : 'border-amber/30 bg-amber/5 text-chalk200'
      }`}>
        {summary.dataStateView.message}
      </div>

      {workloadSummary && (
        <div className="mb-4 rounded border border-dirt bg-field/50 px-3 py-3">
          <div className="mb-2 text-chalk600 text-[10px] font-mono uppercase tracking-wider">Workload Signal</div>
          <div className="flex flex-wrap items-center gap-3">
            <AvailabilityBadge availability={workloadSignal} ariaLabelPrefix="Workload signal" />
            <div className="max-w-xl text-xs font-mono leading-relaxed text-chalk400">
              Workload-only signal before roster-status adjustment.
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <div className="mb-2">
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Final Availability Reasons</div>
            <div className="mt-0.5 text-chalk600 text-[10px] font-mono">Roster and workload signals behind this final status.</div>
          </div>
          <FactList
            items={summary.reasons}
            emptyText="No workload restriction reasons were reported by the backend."
          />
        </div>
        <div>
          <div className="mb-2">
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Limitations</div>
            <div className="mt-0.5 text-chalk600 text-[10px] font-mono">Context BaseballOS does not claim to know.</div>
          </div>
          <FactList
            items={summary.limitations}
            emptyText="No additional limitations were reported by the backend."
            variant="limitation"
          />
        </div>
      </div>
    </section>
  )
}
