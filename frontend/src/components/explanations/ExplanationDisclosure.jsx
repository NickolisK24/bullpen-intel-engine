import { useId, useState } from 'react'

import {
  humanizeLabel,
  isPlainObject,
  shouldShowTechnicalKey,
  summarizeDisplayValue,
  technicalJson,
} from '../../utils/displayText'

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

function displayValue(value) {
  if (value === false) return 'false'
  if (value === true) return 'true'
  if (value === 0) return '0'
  if (value === null || value === undefined || value === '') return 'Not provided'
  if (Array.isArray(value)) return value.length ? value.map(displayValue).join(', ') : 'None'
  if (typeof value === 'object') return summarizeDisplayValue(value)
  return String(value)
}

function titleCase(value) {
  return humanizeLabel(value)
}

function TechnicalKeyLine({ label = 'Technical key', value }) {
  if (!shouldShowTechnicalKey(value)) return null

  return (
    <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-chalk600">
      {label}: {value}
    </p>
  )
}

function ValueBlock({ value, unit = null }) {
  const isTechnicalValue = isPlainObject(value) || Array.isArray(value)

  return (
    <div className="mt-1 break-words font-mono text-xs text-chalk200">
      <div>{displayValue(value)}{unit ? ` ${unit}` : ''}</div>
      {isTechnicalValue && (
        <details className="mt-2 rounded border border-dirt/70 bg-dugout/70 p-2 text-chalk500">
          <summary className="cursor-pointer text-[10px] uppercase tracking-wider text-chalk600">
            Technical details
          </summary>
          <pre className="mt-2 whitespace-pre-wrap break-words text-[11px] leading-relaxed">
            {technicalJson(value)}
          </pre>
        </details>
      )}
    </div>
  )
}

function DetailSection({ title, children, initiallyOpen = false }) {
  return (
    <details
      className="rounded border border-dirt bg-dugout/60 p-3"
      open={initiallyOpen}
    >
      <summary className="cursor-pointer font-mono text-xs uppercase tracking-widest text-chalk300 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
        {title}
      </summary>
      <div className="mt-3">
        {children}
      </div>
    </details>
  )
}

function GovernanceStrip({ governance }) {
  const data = asObject(governance)
  const rows = [
    ['Ranking', data.rankingApplied === false ? 'Not applied' : displayValue(data.rankingApplied)],
    ['Selection', data.selectionMade === false ? 'Not made' : displayValue(data.selectionMade)],
    ['Recommendation', data.recommendationMade === false ? 'Not made' : displayValue(data.recommendationMade)],
    ['Prediction', data.predictionMade === false ? 'Not made' : displayValue(data.predictionMade)],
    ['Decision scope', data.decisionScope === 'explanation_only' ? 'Explanation only' : displayValue(data.decisionScope)],
    ['Advice scope', data.adviceScope === 'none' ? 'No advice' : displayValue(data.adviceScope)],
  ]

  return (
    <div className="rounded border border-amber/35 bg-amber/10 p-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-amber">Explanation only</div>
      <p className="mt-1 text-xs leading-relaxed text-chalk400">
        No ranking, selection, recommendation, or prediction applied.
      </p>
      <dl className="mt-3 grid gap-2 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="rounded border border-dirt bg-field/50 px-2 py-1">
            <dt className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{label}</dt>
            <dd className="mt-0.5 break-words font-mono text-xs text-chalk200">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function ReasonList({ reasons }) {
  const items = asArray(reasons)
  if (!items.length) {
    return <p className="text-xs leading-relaxed text-chalk600">No primary reason returned for this explanation.</p>
  }

  return (
    <ul className="space-y-2">
      {items.map((reason, index) => {
        const item = asObject(reason)
        const labelSource = item.label || item.code || `reason ${index + 1}`
        return (
          <li key={`${item.code || item.label || index}`} className="rounded border border-dirt bg-field/60 p-3">
            <div className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
              {humanizeLabel(labelSource)}
            </div>
            {item.summary && <p className="mt-1 text-sm leading-relaxed text-chalk300">{item.summary}</p>}
            <TechnicalKeyLine value={item.code} />
          </li>
        )
      })}
    </ul>
  )
}

function EvidenceList({ evidence }) {
  const items = asArray(evidence)
  if (!items.length) {
    return <p className="text-xs leading-relaxed text-chalk600">No supporting evidence returned for this explanation.</p>
  }

  return (
    <ul className="space-y-2">
      {items.map((evidenceItem, index) => {
        const item = asObject(evidenceItem)
        const labelSource = item.label || item.evidence_type || `evidence ${index + 1}`
        return (
          <li key={`${item.evidence_id || item.label || index}`} className="rounded border border-dirt bg-field/60 p-3">
            <div className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
              {humanizeLabel(labelSource)}
            </div>
            <TechnicalKeyLine value={labelSource} />
            <ValueBlock value={item.value} unit={item.unit} />
            {item.impact && <p className="mt-1 text-xs leading-relaxed text-chalk500">{item.impact}</p>}
            {[item.source, item.trust_status].filter(Boolean).length > 0 && (
              <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-chalk600">
                {[item.source, item.trust_status].filter(Boolean).map(titleCase).join(' / ')}
              </p>
            )}
            <TechnicalKeyLine label="Source key" value={item.source} />
          </li>
        )
      })}
    </ul>
  )
}

function LimitationList({ limitations }) {
  const items = asArray(limitations)
  if (!items.length) {
    return <p className="text-xs leading-relaxed text-chalk600">No limitations returned for this explanation.</p>
  }

  return (
    <ul className="space-y-2">
      {items.map((limitation, index) => {
        const item = asObject(limitation)
        const labelSource = item.label || item.limitation_type || `limitation ${index + 1}`
        return (
          <li key={`${item.limitation_type || item.label || index}`} className="rounded border border-dirt bg-field/60 p-3">
            <div className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
              {humanizeLabel(labelSource)}
            </div>
            <p className="mt-1 text-sm leading-relaxed text-chalk300">
              {item.summary || 'Explanation limitation was returned without additional summary.'}
            </p>
            <TechnicalKeyLine value={item.limitation_type} />
            {item.severity && <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-chalk600">{titleCase(item.severity)}</p>}
          </li>
        )
      })}
    </ul>
  )
}

function MetadataGrid({ freshness, trust, confidence }) {
  const rows = [
    ['Freshness', asObject(freshness).status],
    ['Data Through', asObject(freshness).data_through],
    ['Last Sync', asObject(freshness).last_sync_at],
    ['Visibility', asObject(trust).status],
    ['Visibility Source', asObject(trust).source],
    ['Certification', asObject(trust).certification_status],
    ['Workload Read', asObject(confidence).level],
    ['Workload Read Summary', asObject(confidence).summary],
  ]

  return (
    <dl className="grid gap-2 sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label} className="rounded border border-dirt bg-field/60 p-2">
          <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{label}</dt>
          <dd className="mt-1 break-words font-mono text-xs text-chalk200">{displayValue(value)}</dd>
        </div>
      ))}
    </dl>
  )
}

function UnavailableExplanation({ explanationView }) {
  const refusal = asObject(explanationView.refusal)

  return (
    <div className="space-y-3">
      <div className="rounded border border-amber/35 bg-amber/10 p-3" role="status" aria-live="polite">
        <div className="font-mono text-xs uppercase tracking-widest text-amber">Explanation unavailable for this state.</div>
        <p className="mt-1 text-sm leading-relaxed text-chalk400">
          Required explanation inputs were unavailable for this request.
        </p>
        {refusal.reason_code && (
          <>
            <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-chalk600">
              {humanizeLabel(refusal.reason_code)}
            </p>
            <TechnicalKeyLine value={refusal.reason_code} />
          </>
        )}
      </div>
      <DetailSection title="Limitations" initiallyOpen>
        <LimitationList limitations={explanationView.limitations} />
      </DetailSection>
      <GovernanceStrip governance={explanationView.governance} />
    </div>
  )
}

function ExplanationDetails({ explanationView }) {
  if (!explanationView?.isContractSafe || explanationView.isFailClosed) {
    return <UnavailableExplanation explanationView={explanationView || {}} />
  }

  return (
    <div className="space-y-3">
      <div className="rounded border border-dirt bg-field/60 p-3">
        <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
          {titleCase(explanationView.scope || explanationView.explanationType)}
        </div>
        <p className="mt-1 text-sm leading-relaxed text-chalk200">{explanationView.summary}</p>
        <div className="mt-2 flex flex-wrap gap-2 font-mono text-[10px] uppercase tracking-wider text-chalk600">
          <span>{titleCase(explanationView.stateExplained)}</span>
          <span>{titleCase(explanationView.subjectType)}</span>
          {explanationView.routeStatus && <span>{titleCase(explanationView.routeStatus)}</span>}
        </div>
      </div>

      <DetailSection title="Reasons" initiallyOpen>
        <ReasonList reasons={explanationView.primaryReasons} />
      </DetailSection>

      <DetailSection title="Evidence">
        <EvidenceList evidence={explanationView.supportingEvidence} />
      </DetailSection>

      <DetailSection title="Limitations">
        <LimitationList limitations={explanationView.limitations} />
      </DetailSection>

      <DetailSection title="Freshness / Visibility / Workload Read">
        <MetadataGrid
          freshness={explanationView.freshness}
          trust={explanationView.trust}
          confidence={explanationView.confidence}
        />
      </DetailSection>

      <DetailSection title="Governance">
        <GovernanceStrip governance={explanationView.governance} />
      </DetailSection>
    </div>
  )
}

export default function ExplanationDisclosure({
  buttonLabel = 'Why this state?',
  contextLabel = 'Explanation details',
  fetchExplanation,
  initialExplanation = null,
  initialOpen = false,
  disabled = false,
}) {
  const baseId = useId()
  const contentId = `${baseId}-explanation-details`
  const [open, setOpen] = useState(initialOpen)
  const [explanationView, setExplanationView] = useState(initialExplanation)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const loadExplanation = async () => {
    if (explanationView || loading || typeof fetchExplanation !== 'function') return
    setLoading(true)
    setError(null)
    try {
      setExplanationView(await fetchExplanation())
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  const handleToggle = async () => {
    const nextOpen = !open
    setOpen(nextOpen)
    if (nextOpen) {
      await loadExplanation()
    }
  }

  return (
    <section className="rounded border border-dirt bg-chalk/20 p-3" aria-label={contextLabel}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">Explanation</div>
          <p className="mt-1 text-xs leading-relaxed text-chalk500">
            Explanation only. Evidence remains on demand.
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center justify-center rounded border border-dirt bg-dugout px-3 py-2 font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus:ring-2 focus:ring-amber/60 focus:ring-offset-2 focus:ring-offset-dugout disabled:cursor-not-allowed disabled:opacity-60"
          aria-expanded={open}
          aria-controls={contentId}
          disabled={disabled}
          onClick={handleToggle}
        >
          {open ? 'Hide Explanation' : buttonLabel}
        </button>
      </div>

      {open && (
        <div id={contentId} className="mt-3">
          {loading ? (
            <div className="rounded border border-dirt bg-field/60 p-3 font-mono text-xs text-chalk400" role="status" aria-live="polite">
              Loading explanation...
            </div>
          ) : error ? (
            <UnavailableExplanation
              explanationView={{
                isContractSafe: false,
                isFailClosed: true,
                limitations: [
                  {
                    limitation_type: 'insufficient_context',
                    summary: 'Explanation details could not be loaded safely.',
                  },
                ],
                refusal: {
                  reason_code: 'frontend_fetch_error',
                },
                governance: {
                  rankingApplied: false,
                  selectionMade: false,
                  recommendationMade: false,
                  predictionMade: false,
                  decisionScope: 'explanation_only',
                  adviceScope: 'none',
                },
              }}
            />
          ) : explanationView ? (
            <ExplanationDetails explanationView={explanationView} />
          ) : (
            <div className="rounded border border-dirt bg-field/60 p-3 font-mono text-xs text-chalk400">
              Explanation details have not been requested.
            </div>
          )}
        </div>
      )}
    </section>
  )
}
