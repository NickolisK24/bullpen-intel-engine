import { useId, useState } from 'react'
import AvailabilityBadge from './AvailabilityBadge'
import ExplanationDisclosure from '../explanations/ExplanationDisclosure'
import {
  getAvailabilitySummary,
  getRosterStatusSummary,
  READ_CONFIDENCE_FIELD_LABEL,
  WORKLOAD_DATA_FIELD_LABEL,
} from './availabilityView'
import {
  dayAwareAppearanceReasons,
  platformDateFromFreshness,
} from '../../utils/appearanceLanguage'

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

function MetadataFact({ label, value, alert = false }) {
  return (
    <div className={`min-w-0 border-t pt-2 ${alert ? 'border-amber/40' : 'border-dirt/70'}`}>
      <dt className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{label}</dt>
      <dd className="mt-1 break-words font-mono text-xs font-semibold text-chalk200">{value}</dd>
    </div>
  )
}

export default function AvailabilitySummary({
  availability,
  workloadSignal = null,
  rosterStatus = null,
  freshness = null,
  lastAppearance = null,
  fetchExplanation = null,
  initialExplanation = null,
  initialDetailsOpen = false,
}) {
  const [detailsOpen, setDetailsOpen] = useState(initialDetailsOpen)
  const detailsId = `pitcher-availability-details-${useId().replace(/:/g, '')}`
  const summary = getAvailabilitySummary(availability)
  const platformDate = platformDateFromFreshness(freshness)
  const reasons = dayAwareAppearanceReasons(summary.reasons, lastAppearance, platformDate)
  const workloadSummary = workloadSignal ? getAvailabilitySummary(workloadSignal) : null
  const resolvedRosterStatus = getRosterStatusSummary(
    rosterStatus || availability?.roster_status,
  )
  // Keyed off the governed state, never the reader-facing text, so renaming a
  // label can never silently change the stale styling.
  const isCurrentData = summary.dataStateView.isCurrent === true

  return (
    <section className="rounded border border-dirt bg-chalk/30 p-4 sm:p-5" aria-labelledby="pitcher-availability-title">
      <div className="min-w-0">
        <h3 id="pitcher-availability-title" className="font-display text-base tracking-wider text-chalk100">
          Availability
        </h3>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <AvailabilityBadge availability={availability} ariaLabelPrefix="Final availability" />
        </div>
        <p className="mt-2 max-w-xl text-xs font-mono leading-relaxed text-chalk400">
          {summary.tone}
        </p>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3 sm:max-w-2xl">
        <MetadataFact label="Roster Status" value={resolvedRosterStatus?.label || 'Roster Unknown'} />
        <MetadataFact label={READ_CONFIDENCE_FIELD_LABEL} value={summary.confidenceLabel} />
        <MetadataFact
          label={WORKLOAD_DATA_FIELD_LABEL}
          value={summary.dataStateView.label}
          alert={!isCurrentData}
        />
      </dl>

      <button
        type="button"
        className="mt-3 inline-flex min-h-11 w-full items-center justify-between gap-3 rounded border border-dirt px-3 py-2 text-left font-mono text-xs font-semibold text-chalk300 hover:border-amber/60 hover:text-amber focus-visible:ring-2 focus-visible:ring-amber/70 sm:w-auto"
        aria-expanded={detailsOpen}
        aria-controls={detailsId}
        onClick={() => setDetailsOpen(current => !current)}
      >
        <span>{detailsOpen ? 'Hide availability details' : 'View availability details'}</span>
        <span aria-hidden="true">{detailsOpen ? '−' : '+'}</span>
      </button>

      <div
        id={detailsId}
        hidden={!detailsOpen}
        className="mt-4 space-y-4 border-t border-dirt pt-4"
      >
        {detailsOpen && (
          <>
            <div className={`rounded border px-3 py-2 text-xs font-mono leading-relaxed ${
              isCurrentData
                ? 'border-dirt bg-field/40 text-chalk400'
                : 'border-amber/30 bg-amber/5 text-chalk200'
            }`}>
              {summary.dataStateView.message}
            </div>

            {workloadSummary && (
              <div className="rounded border border-dirt bg-field/50 px-3 py-3">
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
          </>
        )}

        {typeof fetchExplanation === 'function' && (
          <div>
            {detailsOpen && (
              <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">Detailed Evidence</div>
            )}
            <ExplanationDisclosure
              embedded
              active={detailsOpen}
              fetchExplanation={fetchExplanation}
              initialExplanation={initialExplanation}
            />
          </div>
        )}
      </div>
    </section>
  )
}
