import { useEffect, useState } from 'react'
import { Disclosure } from '../UI'

import {
  explanationLabel,
  summarizeDisplayValue,
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

// No titleCase helper here any more. Turning a raw backend enum into public
// text is exactly the inference this surface is not entitled to do.

function ValueBlock({ value, unit = null }) {
  return (
    <div className="mt-1 break-words font-mono text-xs text-chalk200">
      <div>{displayValue(value)}{unit ? ` ${unit}` : ''}</div>
    </div>
  )
}

function DetailSection({ title, children, initiallyOpen = false }) {
  return (
    <Disclosure label={title} defaultOpen={initiallyOpen} contentClassName="mt-1">
      <div className="mt-2">
        {children}
      </div>
    </Disclosure>
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
        const label = explanationLabel(item)
        return (
          <li key={`${item.code || item.label || index}`} className="rounded border border-dirt bg-field/60 p-3">
            {label && (
              <div className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
                {label}
              </div>
            )}
            {item.summary && <p className="mt-1 text-sm leading-relaxed text-chalk300">{item.summary}</p>}
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
        const label = explanationLabel(item)
        return (
          <li key={`${item.evidence_id || item.label || index}`} className="rounded border border-dirt bg-field/60 p-3">
            {label && (
              <div className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
                {label}
              </div>
            )}
            <ValueBlock value={item.value} unit={item.unit} />
            {item.impact && <p className="mt-1 text-xs leading-relaxed text-chalk500">{item.impact}</p>}
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
        const label = explanationLabel(item)
        return (
          <li key={`${item.limitation_type || item.label || index}`} className="rounded border border-dirt bg-field/60 p-3">
            {label && (
              <div className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
                {label}
              </div>
            )}
            <p className="mt-1 text-sm leading-relaxed text-chalk300">
              {item.summary || 'Explanation limitation was returned without additional summary.'}
            </p>
            {/* `severity` is the explanation engine's own priority word
                (informational / significant), not governed public vocabulary,
                and the limitation's own label and summary already say what is
                limited. */}
          </li>
        )
      })}
    </ul>
  )
}

function MetadataGrid({ freshness, trust, confidence }) {
  const routine = new Set(['', 'current', 'high', 'complete', 'available', 'trusted'])
  const rows = [
    ['Freshness', asObject(freshness).status],
    ['Visibility', asObject(trust).status],
    ['Read Confidence', asObject(confidence).level],
    ['Read Confidence Summary', asObject(confidence).summary],
  ].filter(([, value]) => value != null && !routine.has(String(value).trim().toLowerCase()))

  return (
    <div>
      {rows.length > 0 && (
        <dl className="grid gap-2 sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label} className="rounded border border-amber/25 bg-amber/5 p-2">
              <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{label}</dt>
              <dd className="mt-1 break-words text-xs text-chalk200">{displayValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      <a href="/trust" className="mt-2 inline-block text-xs text-chalk500 underline-offset-2 hover:text-amber hover:underline">
        Freshness and methodology
      </a>
    </div>
  )
}

function UnavailableExplanation({ explanationView }) {
  return (
    <div className="space-y-3">
      <div className="rounded border border-amber/35 bg-amber/10 p-3" role="status" aria-live="polite">
        <div className="font-mono text-xs uppercase tracking-widest text-amber">Explanation unavailable for this state.</div>
        <p className="mt-1 text-sm leading-relaxed text-chalk400">
          Required explanation inputs were unavailable for this request.
        </p>
      </div>
      <DetailSection title="Limitations" initiallyOpen>
        <LimitationList limitations={explanationView.limitations} />
      </DetailSection>
    </div>
  )
}

function ExplanationDetails({ explanationView }) {
  if (!explanationView?.isContractSafe || explanationView.isFailClosed) {
    return <UnavailableExplanation explanationView={explanationView || {}} />
  }

  return (
    <div className="space-y-3">
      {/* The envelope's scope, state_explained, subject_type and route_status
          were title-cased into this header and chip row, which turned engine
          enums into reader copy with no semantic owner: `readiness_state` read
          as "Readiness State", `operationally_stable` as "Operationally
          Stable", `internal_uncertified_route` as "Internal Uncertified
          Route". None of them answered a reader question. Scope and subject are
          already established by the surface that opens this disclosure;
          state_explained is the internal readiness code whose public name is a
          Team State published elsewhere; route_status is which internal route
          served the request. The summary carries the explanation. */}
      <div className="rounded border border-dirt bg-field/60 p-3">
        <p className="text-sm leading-relaxed text-chalk200">{explanationView.summary}</p>
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

      <DetailSection title="Freshness / Visibility / Read Confidence">
        <MetadataGrid
          freshness={explanationView.freshness}
          trust={explanationView.trust}
          confidence={explanationView.confidence}
        />
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
  embedded = false,
  active = false,
}) {
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

  useEffect(() => {
    if (disabled || !embedded || !active || explanationView || typeof fetchExplanation !== 'function') return undefined

    let cancelled = false
    setLoading(true)
    setError(null)
    fetchExplanation()
      .then(value => {
        if (!cancelled) setExplanationView(value)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [active, disabled, embedded, explanationView, fetchExplanation])

  const handleToggle = async (event) => {
    const nextOpen = event.currentTarget.open
    setOpen(nextOpen)
    if (nextOpen) {
      await loadExplanation()
    }
  }

  const explanationContent = loading ? (
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
      }}
    />
  ) : explanationView ? (
    <ExplanationDetails explanationView={explanationView} />
  ) : (
    <div className="rounded border border-dirt bg-field/60 p-3 font-mono text-xs text-chalk400">
      Explanation details have not been requested.
    </div>
  )

  if (embedded) {
    return active ? <div className="mt-2">{explanationContent}</div> : null
  }

  return (
    <Disclosure
      label={buttonLabel}
      hint="Evidence and limitations"
      open={open}
      onToggle={handleToggle}
      disabled={disabled}
      ariaLabel={contextLabel}
      className="bg-chalk/20"
    >
      {open && <div className="mt-2">{explanationContent}</div>}
    </Disclosure>
  )
}
