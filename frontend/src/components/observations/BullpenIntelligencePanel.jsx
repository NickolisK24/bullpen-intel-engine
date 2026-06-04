import { ErrorState, LoadingPane } from '../UI'
import {
  OBSERVATION_EMPTY_COPY,
  OBSERVATION_GOVERNANCE_COPY,
} from '../../types/observations'

const STATUS_LABELS = {
  available: 'Available',
  empty: 'No Observations',
  fail_closed: 'Protected',
  unavailable: 'Unavailable',
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
    <div className="rounded border border-dirt bg-field/50 p-3 bullpen-intelligence-panel__text">
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{label}</div>
      <div className="mt-1 text-sm font-semibold text-chalk200">{displayValue(value)}</div>
      {subtext && (
        <div className="mt-1 text-[11px] leading-relaxed text-chalk500">{subtext}</div>
      )}
    </div>
  )
}

function ObservationEvidenceList({ evidence }) {
  const rows = asArray(evidence)
  if (!rows.length) {
    return <p className="text-xs text-chalk600">No evidence surfaced for this observation.</p>
  }

  return (
    <div className="space-y-2">
      {rows.map((item, index) => (
        <div
          key={item?.evidence_id || index}
          className="rounded border border-dirt/80 bg-chalk/25 p-3 bullpen-intelligence-panel__text"
        >
          <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="text-xs font-semibold text-chalk200">
                {displayValue(item?.label, `Evidence ${index + 1}`)}
              </div>
              <div className="mt-1 font-mono text-[11px] text-chalk500">
                Source: {displayValue(item?.source_type || item?.source)}
              </div>
            </div>
            <div className="font-mono text-xs text-amber">
              {displayValue(item?.value)}
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-2 font-mono text-[11px] text-chalk600">
            {item?.freshness_status && <span>Freshness: {displayValue(item.freshness_status)}</span>}
            {item?.data_through && <span>Data Through: {displayValue(item.data_through)}</span>}
            {item?.generated_at && <span>Generated: {displayValue(item.generated_at)}</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

function ObservationLimitations({ limitations }) {
  const rows = asArray(limitations)
  if (!rows.length) {
    return <p className="text-xs text-chalk600">No limitations surfaced for this observation.</p>
  }

  return (
    <ul className="space-y-2">
      {rows.map((item, index) => (
        <li
          key={item?.limitation_type || index}
          className="rounded border border-dirt/70 bg-field/40 p-3 text-xs leading-relaxed text-chalk400 bullpen-intelligence-panel__text"
        >
          <div>{itemSummary(item)}</div>
          <div className="mt-1 flex flex-wrap gap-2 font-mono text-[11px] text-chalk600">
            {item?.limitation_type && <span>Type: {labelize(item.limitation_type)}</span>}
            {item?.severity && <span>Severity: {labelize(item.severity)}</span>}
            {item?.source && <span>Source: {displayValue(item.source)}</span>}
          </div>
        </li>
      ))}
    </ul>
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
  return (
    <article className="rounded-lg border border-dirt bg-field/45 p-4 bullpen-intelligence-panel__text">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap gap-2 font-mono text-[10px] uppercase tracking-widest">
            <span className="rounded border border-dirt bg-dugout px-2 py-1 text-chalk500">
              {labelize(observation.family || observation.observation_type)}
            </span>
            <span className="rounded border border-amber/25 bg-amber/10 px-2 py-1 text-amber/90">
              {labelize(observation.severity)}
            </span>
          </div>
          <h3 className="mt-3 text-lg font-semibold leading-snug text-chalk100">
            {displayValue(observation.title)}
          </h3>
          <p className="mt-2 text-sm leading-relaxed text-chalk400">
            {displayValue(observation.summary)}
          </p>
        </div>
        <div className="rounded border border-dirt bg-dugout px-3 py-2 font-mono text-[11px] text-chalk500">
          Trust: {displayValue(observation.trust_status)}
        </div>
      </div>

      <div className="bullpen-intelligence-panel__metadata-grid mt-4 gap-3">
        <MetadataCell
          label="Freshness"
          value={observation.freshness?.status}
          subtext={observation.freshness?.data_through ? `Data through ${observation.freshness.data_through}` : null}
        />
        <MetadataCell
          label="Confidence"
          value={observation.confidence?.status}
          subtext={observation.confidence?.reason}
        />
      </div>

      <div className="mt-4 grid gap-4">
        <section aria-label={`${observation.title} evidence`}>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-chalk600">
            Evidence
          </div>
          <ObservationEvidenceList evidence={observation.evidence} />
        </section>

        <section aria-label={`${observation.title} limitations`}>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-chalk600">
            Limitations
          </div>
          <ObservationLimitations limitations={observation.limitations} />
        </section>
      </div>

      {observation.explanation_reference && (
        <div className="mt-4 rounded border border-dirt bg-dugout/80 p-3 font-mono text-[11px] leading-relaxed text-chalk500">
          Explanation Reference: {displayValue(observation.explanation_reference)}
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2 font-mono text-[11px] text-chalk600">
        <span>ranking_applied === {displayValue(observation.ranking_applied)}</span>
        <span>selection_made === {displayValue(observation.selection_made)}</span>
      </div>
    </article>
  )
}

function SafeUnavailableState({ state }) {
  const diagnostics = [
    ...asArray(state?.missingFields),
    ...asArray(state?.malformedFields),
    ...asArray(state?.forbiddenFieldPaths),
    ...asArray(state?.forbiddenTextPaths),
  ]

  return (
    <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4" role="alert" aria-live="assertive">
      <div className="font-mono text-xs uppercase tracking-widest text-red-300">
        Bullpen observations unavailable
      </div>
      <p className="mt-2 text-sm leading-relaxed text-chalk300">
        Observation details are withheld because the frontend contract guard did not verify the current payload.
      </p>
      <p className="mt-2 font-mono text-[11px] text-chalk600">
        Diagnostics detected: {diagnostics.length}
      </p>
    </div>
  )
}

export default function BullpenIntelligencePanel({
  state,
  loading = false,
  error = null,
  onRetry,
}) {
  const observations = asArray(state?.observations)
  const statusLabel = STATUS_LABELS[state?.contractState] || 'Not Loaded'
  const emptyOrProtected = Boolean(state?.isEmpty || state?.isFailClosed)

  return (
    <section
      className="card mb-5 bullpen-intelligence-panel"
      aria-labelledby="bullpen-intelligence-heading"
      aria-describedby="bullpen-intelligence-governance"
    >
      <div className="card-header flex-col items-start gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
            V5 Bullpen Intelligence
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
          GET /api/observations · {statusLabel}
        </div>
      </div>

      <div className="p-4">
        {loading ? (
          <LoadingPane message="Loading governed bullpen observations..." />
        ) : error ? (
          <ErrorState message="Bullpen observations could not be loaded safely." onRetry={onRetry} />
        ) : !state || state.contractState === 'unavailable' || !state.isContractSafe ? (
          <SafeUnavailableState state={state} />
        ) : (
          <div className="space-y-4">
            <div className="bullpen-intelligence-panel__metadata-grid gap-3">
              <MetadataCell label="Trust Status" value={state.trustStatus} />
              <MetadataCell
                label="Freshness"
                value={state.freshness?.status}
                subtext={state.freshness?.data_through ? `Data through ${state.freshness.data_through}` : null}
              />
              <MetadataCell
                label="Confidence"
                value={state.confidence?.status}
                subtext={state.confidence?.reason}
              />
              <MetadataCell
                label="Governance"
                value="Protected"
                subtext={`ranking_applied === ${displayValue(state.governance?.rankingApplied)}; selection_made === ${displayValue(state.governance?.selectionMade)}`}
              />
            </div>

            <CollectionLimitations limitations={state.limitations} />

            {emptyOrProtected ? (
              <div className="rounded-lg border border-dirt bg-field/45 p-6 text-center">
                <p className="text-sm text-chalk300">{OBSERVATION_EMPTY_COPY}</p>
                {state.suppressionReasons?.length > 0 && (
                  <p className="mt-2 font-mono text-[11px] text-chalk600">
                    Suppression reasons: {state.suppressionReasons.map(labelize).join(', ')}
                  </p>
                )}
              </div>
            ) : (
              <div className="bullpen-intelligence-panel__observation-grid gap-4">
                {observations.map(observation => (
                  <ObservationCard
                    key={observation.observation_id}
                    observation={observation}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
