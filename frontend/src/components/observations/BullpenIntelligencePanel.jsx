import { useState } from 'react'

import { ErrorState, LoadingPane } from '../UI'
import { formatConfidence } from '../bullpen/availabilityView'
import {
  OBSERVATION_EMPTY_COPY,
  OBSERVATION_GOVERNANCE_COPY,
} from '../../types/observations'

const DASHBOARD_OBSERVATION_LIMIT = 3

const STATUS_LABELS = {
  available: 'Available',
  empty: 'No Observations',
  fail_closed: 'Unavailable - output withheld',
  unavailable: 'Unavailable',
}

// Plain-language governance reassurance shown on the user-facing surface in
// place of raw contract fields. The underlying ranking_applied / selection_made
// values are preserved in the API payload, the normalized view model, and the
// contract tests — they just don't need to read like debug output here.
const GOVERNANCE_CONTEXT_COPY = 'Context only — not a ranking or selection.'

// Baseball-facing display labels for the governed trust_status vocabulary.
// The raw vocabulary values stay untouched in the payload and view model.
const VISIBILITY_LABELS = {
  supported: 'Clear Visibility',
  limited: 'Limited Visibility',
  data_limited: 'Limited Visibility',
  stale: 'Recent Usage Unknown',
  missing: 'Missing Recent Usage',
  refused: 'Output Withheld',
  fail_closed: 'Output Withheld',
  unsupported: 'Visibility Unknown',
}

function visibilityLabel(trustStatus) {
  const key = String(trustStatus || '').trim().toLowerCase()
  if (!key) return 'Visibility Unknown'
  return VISIBILITY_LABELS[key] || labelize(key)
}

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function labelize(value) {
  if (value === undefined || value === null || value === '') return 'Not provided'
  return String(value)
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, char => char.toUpperCase())
}

function displayValue(value, fallback = 'Not provided') {
  if (value === undefined || value === null || value === '') return fallback
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return value.toLocaleString()
  if (Array.isArray(value)) return value.map(item => displayValue(item)).join(', ')
  if (typeof value === 'object') {
    if (value.status) return displayValue(value.status)
    if (value.reason) return displayValue(value.reason)
    if (value.summary) return displayValue(value.summary)
    return Object.entries(value)
      .map(([key, item]) => `${labelize(key)}: ${displayValue(item)}`)
      .join(', ')
  }
  return String(value)
}

function itemSummary(item) {
  if (typeof item === 'string') return item
  if (!item || typeof item !== 'object') return displayValue(item)
  return item.summary || item.message || item.reason || item.label || displayValue(item)
}

function MetadataCell({ label, value, subtext }) {
  return (
    <div className="rounded border border-dirt bg-field/50 p-2 bullpen-intelligence-panel__text">
      <div className="font-mono text-[10px] uppercase tracking-wide text-chalk600">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-chalk200">{displayValue(value)}</div>
      {subtext && (
        <div className="mt-0.5 text-[11px] leading-snug text-chalk500">{subtext}</div>
      )}
    </div>
  )
}

function StatusChip({ label, value, detail }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1 rounded border border-dirt bg-dugout px-2 py-1 font-mono text-[11px] leading-none text-chalk500 bullpen-intelligence-panel__text">
      <span className="text-chalk600">{label}:</span>
      <span className="font-semibold text-chalk200">{displayValue(value)}</span>
      {detail && (
        <span className="truncate text-chalk600" title={detail}>
          {detail}
        </span>
      )}
    </span>
  )
}

function ObservationEvidenceList({ evidence }) {
  const rows = asArray(evidence)
  if (!rows.length) {
    return <p className="text-xs text-chalk600">No evidence surfaced for this observation.</p>
  }

  const primaryEvidence = rows[0]
  const primarySource = primaryEvidence?.source_type || primaryEvidence?.source

  return (
    <div className="rounded border border-dirt/80 bg-chalk/25 p-2 bullpen-intelligence-panel__text">
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-chalk500">
        <span>
          Primary evidence: {displayValue(primaryEvidence?.label || primaryEvidence?.source)}
        </span>
        <span>Evidence count: {rows.length}</span>
        <span>Evidence source: {displayValue(primarySource)}</span>
      </div>
      <div className="mt-2 space-y-1">
        {rows.map((item, index) => (
          <div
            key={item?.evidence_id || index}
            className="flex flex-wrap gap-x-3 gap-y-1 rounded border border-dirt/60 bg-field/35 px-2 py-1.5 text-xs leading-snug text-chalk500"
          >
            <span className="font-semibold text-chalk200">
              {displayValue(item?.label, `Evidence ${index + 1}`)}:
            </span>
            <span className="font-mono text-amber">{displayValue(item?.value)}</span>
            <span>Source: {displayValue(item?.source_type || item?.source)}</span>
            {item?.freshness_status && <span>Freshness: {displayValue(item.freshness_status)}</span>}
            {item?.data_through && <span>Data Through: {displayValue(item.data_through)}</span>}
            {item?.generated_at && <span>Generated: {displayValue(item.generated_at)}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

function ObservationLimitations({ limitations }) {
  const rows = asArray(limitations)
  if (!rows.length) {
    return <p className="text-xs text-chalk600">No limitations surfaced for this observation.</p>
  }

  const primarySource = rows[0]?.source

  return (
    <div className="rounded border border-dirt/70 bg-field/35 p-2 bullpen-intelligence-panel__text">
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-chalk500">
        <span>Limitation count: {rows.length}</span>
        <span>Limitation source: {displayValue(primarySource)}</span>
      </div>
      <ul className="mt-2 space-y-1">
        {rows.map((item, index) => (
          <li
            key={item?.limitation_type || index}
            className="flex flex-wrap gap-x-3 gap-y-1 rounded border border-dirt/60 bg-black/10 px-2 py-1.5 text-xs leading-snug text-chalk400 bullpen-intelligence-panel__text"
          >
            <span>{itemSummary(item)}</span>
            {item?.limitation_type && <span>Type: {labelize(item.limitation_type)}</span>}
            {item?.severity && <span>Severity: {labelize(item.severity)}</span>}
            {item?.source && <span>Source: {displayValue(item.source)}</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}

function CollectionLimitations({ limitations }) {
  const rows = asArray(limitations)
  if (!rows.length) return null

  return (
    <div
      className="rounded border border-amber/20 bg-amber/5 p-3"
      aria-labelledby="bullpen-intelligence-limitations"
    >
      <div
        id="bullpen-intelligence-limitations"
        className="font-mono text-[10px] uppercase tracking-widest text-amber/80"
      >
        Collection Limitations
      </div>
      <div className="mt-2 space-y-1">
        {rows.map((item, index) => (
          <p key={item?.limitation_type || index} className="text-xs leading-relaxed text-chalk400">
            {itemSummary(item)}
          </p>
        ))}
      </div>
    </div>
  )
}

function ObservationCard({ observation }) {
  const freshnessDetail = observation.freshness?.data_through
    ? `Data through ${displayValue(observation.freshness.data_through)}`
    : observation.freshness?.reason
  const confidenceDetail = observation.confidence?.reason

  return (
    <article className="rounded-lg border border-dirt bg-field/45 p-3 bullpen-intelligence-panel__text">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap gap-1.5 font-mono text-[10px] uppercase tracking-wide">
            <span className="rounded border border-dirt bg-dugout px-2 py-1 text-chalk500">
              {labelize(observation.family || observation.observation_type)}
            </span>
            <span className="rounded border border-amber/25 bg-amber/10 px-2 py-1 text-amber/90">
              {labelize(observation.severity)}
            </span>
          </div>
          <h3 className="mt-2 text-base font-semibold leading-snug text-chalk100">
            {displayValue(observation.title)}
          </h3>
          <p className="mt-1 text-sm leading-snug text-chalk400">
            {displayValue(observation.summary)}
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <StatusChip label="Visibility" value={visibilityLabel(observation.trust_status)} />
        <StatusChip
          label="Freshness"
          value={observation.freshness?.status}
          detail={freshnessDetail}
        />
        <StatusChip
          label="Workload Read"
          value={formatConfidence(observation.confidence?.status)}
          detail={confidenceDetail}
        />
      </div>

      <div className="mt-3 grid gap-3">
        <section aria-label={`${observation.title} evidence`}>
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-chalk600">
            Evidence
          </div>
          <ObservationEvidenceList evidence={observation.evidence} />
        </section>

        <section aria-label={`${observation.title} limitations`}>
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-chalk600">
            Limitations
          </div>
          <ObservationLimitations limitations={observation.limitations} />
        </section>
      </div>

      {observation.explanation_reference && (
        <div className="mt-3 rounded border border-dirt bg-dugout/80 p-2 font-mono text-[11px] leading-snug text-chalk500">
          Explanation Reference: {displayValue(observation.explanation_reference)}
        </div>
      )}

      <div className="mt-3 font-mono text-[11px] text-chalk600">
        {GOVERNANCE_CONTEXT_COPY}
      </div>
    </article>
  )
}

function SafeUnavailableState() {
  return (
    <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4" role="alert" aria-live="assertive">
      <div className="font-mono text-xs uppercase tracking-widest text-red-300">
        Bullpen observations unavailable
      </div>
      <p className="mt-2 text-sm leading-relaxed text-chalk300">
        Observation details are withheld until the latest data passes BaseballOS
        safety checks. Nothing is shown unless it can be trusted.
      </p>
    </div>
  )
}

export default function BullpenIntelligencePanel({
  state,
  loading = false,
  error = null,
  onRetry,
  observationLimit = DASHBOARD_OBSERVATION_LIMIT,
}) {
  const [showAllObservations, setShowAllObservations] = useState(false)
  const observations = asArray(state?.observations)
  const statusLabel = STATUS_LABELS[state?.contractState] || 'Not Loaded'
  const emptyOrWithheld = Boolean(state?.isEmpty || state?.isFailClosed)
  const hasObservationLimit =
    Number.isFinite(observationLimit) && observationLimit > 0 && observations.length > observationLimit
  const visibleObservations =
    hasObservationLimit && !showAllObservations
      ? observations.slice(0, observationLimit)
      : observations
  const hiddenObservationCount = Math.max(observations.length - visibleObservations.length, 0)

  return (
    <section
      className="card mb-5 bullpen-intelligence-panel"
      aria-labelledby="bullpen-intelligence-heading"
      aria-describedby="bullpen-intelligence-governance"
    >
      <div className="card-header flex-col items-start gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
            Bullpen Intelligence
          </div>
          <h2 id="bullpen-intelligence-heading" className="mt-1 text-xl font-semibold text-chalk100">
            Governed Observations
          </h2>
          <p
            id="bullpen-intelligence-governance"
            className="mt-1 max-w-3xl text-xs leading-relaxed text-chalk500"
          >
            {OBSERVATION_GOVERNANCE_COPY}
          </p>
        </div>
        <div
          className="rounded border border-dirt bg-field/55 px-3 py-2 font-mono text-[11px] text-chalk500"
          aria-live="polite"
          aria-atomic="true"
        >
          {statusLabel}
        </div>
      </div>

      <div className="p-4">
        {loading ? (
          <LoadingPane message="Loading governed bullpen observations..." />
        ) : error ? (
          <ErrorState message="Bullpen observations could not be loaded safely." onRetry={onRetry} />
        ) : !state || state.contractState === 'unavailable' || !state.isContractSafe ? (
          <SafeUnavailableState />
        ) : (
          <div className="space-y-4">
            <div className="bullpen-intelligence-panel__metadata-grid gap-3">
              <MetadataCell label="Bullpen Visibility" value={visibilityLabel(state.trustStatus)} />
              <MetadataCell
                label="Freshness"
                value={state.freshness?.status}
                subtext={state.freshness?.data_through ? `Data through ${state.freshness.data_through}` : null}
              />
              <MetadataCell
                label="Workload Read"
                value={formatConfidence(state.confidence?.status)}
                subtext={state.confidence?.reason}
              />
              <MetadataCell
                label="Governance"
                value="Context Only"
                subtext={GOVERNANCE_CONTEXT_COPY}
              />
            </div>

            <CollectionLimitations limitations={state.limitations} />

            {emptyOrWithheld ? (
              <div className="rounded-lg border border-dirt bg-field/45 p-6 text-center">
                <p className="text-sm text-chalk300">{OBSERVATION_EMPTY_COPY}</p>
                {state.suppressionReasons?.length > 0 && (
                  <p className="mt-2 font-mono text-[11px] text-chalk600">
                    Suppression reasons: {state.suppressionReasons.map(labelize).join(', ')}
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                {hasObservationLimit && (
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-dirt bg-field/45 px-3 py-2 font-mono text-[11px] text-chalk500">
                    <span>
                      Showing {visibleObservations.length} of {observations.length} governed observations.
                    </span>
                    {hiddenObservationCount > 0 ? (
                      <span className="flex flex-wrap items-center gap-2">
                        <span>+{hiddenObservationCount} additional observations available</span>
                        <button
                          type="button"
                          className="rounded border border-dirt bg-dugout px-2 py-1 text-[11px] font-semibold text-chalk300 transition hover:border-amber/40 hover:text-amber"
                          onClick={() => setShowAllObservations(true)}
                        >
                          View All Observations
                        </button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="rounded border border-dirt bg-dugout px-2 py-1 text-[11px] font-semibold text-chalk300 transition hover:border-amber/40 hover:text-amber"
                        onClick={() => setShowAllObservations(false)}
                      >
                        Show Fewer Observations
                      </button>
                    )}
                  </div>
                )}

                <div className="bullpen-intelligence-panel__observation-grid gap-3">
                  {visibleObservations.map(observation => (
                    <ObservationCard
                      key={observation.observation_id}
                      observation={observation}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
