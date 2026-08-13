import AvailabilityBadge from './AvailabilityBadge'
import { getAvailabilitySummary, getRosterStatusSummary } from './availabilityView'
import {
  dayAwareAppearanceReasons,
  platformDateFromFreshness,
} from '../../utils/appearanceLanguage'

function FactList({ items, emptyText, variant = 'reason' }) {
  if (!items.length) {
    return <div className="text-chalk600 text-xs font-mono leading-relaxed">{emptyText}</div>
  }

  return (
    <ol>
      {items.map((item, index) => (
        <li key={`${item}-${index}`} className={`grid gap-x-3 py-2 text-xs leading-relaxed text-chalk200 ${variant === 'limitation' ? 'grid-cols-[1px_minmax(0,1fr)]' : 'grid-cols-[22px_1px_minmax(0,1fr)]'}`}>
          {variant !== 'limitation' && <span className="font-mono text-[11px] text-brass-deep" aria-hidden="true">E{index + 1}</span>}
          <span className={`min-h-6 ${variant === 'limitation' ? 'bg-line-strong' : 'bg-line'}`} aria-hidden="true" />
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
  freshness = null,
  lastAppearance = null,
}) {
  const summary = getAvailabilitySummary(availability)
  const platformDate = platformDateFromFreshness(freshness)
  const reasons = dayAwareAppearanceReasons(summary.reasons, lastAppearance, platformDate)
  const workloadSummary = workloadSignal ? getAvailabilitySummary(workloadSignal) : null
  const resolvedRosterStatus = getRosterStatusSummary(
    rosterStatus || availability?.roster_status,
  )
  const isCurrentData = summary.dataStateView.label === 'Fresh'

  return (
    <section>
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
        <div className="grid grid-cols-2 border-l border-t border-line sm:max-w-xl">
          <div className="border-b border-r border-line p-3">
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Roster Status</div>
            <div className="mt-1 font-mono text-xs font-semibold text-chalk200">
              {resolvedRosterStatus?.label || 'Roster Unknown'}
            </div>
          </div>
          <div className="border-b border-r border-line p-3">
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Workload Read</div>
            <div className="mt-1 font-mono text-xs font-semibold text-chalk200">{summary.confidenceLabel}</div>
          </div>
          <div className="border-b border-r border-line p-3">
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Data Status</div>
            <div className="mt-1 font-mono text-xs font-semibold text-chalk200">{summary.dataStateView.label}</div>
          </div>
        </div>
      </div>

      <div className={`mb-5 border-l-2 py-1 pl-4 text-xs leading-relaxed ${isCurrentData ? 'border-line-strong text-chalk400' : 'border-brass text-chalk200'}`}>
        {summary.dataStateView.message}
      </div>

      {workloadSummary && (
        <div className="mb-5 border-t border-line pt-4">
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
            items={reasons}
            emptyText="No workload restriction reasons are available."
          />
        </div>
        <div>
          <div className="mb-2">
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Limitations</div>
            <div className="mt-0.5 text-chalk600 text-[10px] font-mono">Context BaseballOS does not claim to know.</div>
          </div>
          <FactList
            items={summary.limitations}
            emptyText="No additional limitations are available."
            variant="limitation"
          />
        </div>
      </div>
    </section>
  )
}
