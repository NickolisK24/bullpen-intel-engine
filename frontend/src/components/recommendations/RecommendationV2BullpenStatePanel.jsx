import { useState } from 'react'

import { LoadingPane, ErrorState } from '../UI'

const SUMMARY_TEXT_LIMIT = 180

const FORBIDDEN_DISPLAY_TERMS = [
  /\bbest\b/i,
  /\btop\b/i,
  /\bpreferred\b/i,
  /\brecommended\b/i,
  /\bwinner\b/i,
  /\bpicks?\b/i,
  /\bselection\b/i,
  /\branks?\b/i,
  /\bscore\b/i,
  /\bprojection\b/i,
  /\bforecast\b/i,
]

const SAFE_GOVERNANCE_DISCLAIMER_PATTERNS = [
  /\b(?:fatigue|workload)\s+score\b/ig,
  /\bnot\s+(?:a|an)?\s*[^.]*\b(?:forecast|projection|prediction)\b[^.]*\.?/ig,
  /\b(?:does not|do not|did not|must not|cannot|can't|should not|will not|without)\b[^.]*\b(?:rank|ranking|select|selection|recommend|recommended|prediction|predict|projection|project|forecast|score)\b[^.]*\.?/ig,
  /\bno\b[^.]*\b(?:rank|ranking|selection|select|recommendation|recommend|prediction|projection|forecast|score|winner|pick)\b[^.]*\.?/ig,
]

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

function toTitle(value) {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function displayValue(value, fallback = 'Unavailable') {
  if (value === false) return 'false'
  if (value === true) return 'true'
  if (value === 0) return '0'
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

function sectionId(label) {
  return `recommendation-v2-${String(label || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')}`
}

function orderingPolicyLabel(value) {
  if (!value) return 'neutral'
  const text = String(value)
  return /ranking|rank/i.test(text) ? 'neutral source order' : toTitle(text)
}

function messageFrom(item) {
  if (typeof item === 'string') return item
  if (!item || typeof item !== 'object') return null
  return item.message || item.reason || item.limitation_id || item.explanation_id || item.refusal_id || null
}

function compactText(value, maxLength = SUMMARY_TEXT_LIMIT) {
  const text = displayValue(value, '').replace(/\s+/g, ' ').trim()
  if (!text) return null
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength - 3).trim()}...`
}

function hasForbiddenDisplayText(value) {
  if (typeof value === 'string') {
    let text = String(value)
    if (/non[-_ ]?ranking|input[-_ ]?order[-_ ]?non[-_ ]?ranking/i.test(text)) {
      return false
    }
    SAFE_GOVERNANCE_DISCLAIMER_PATTERNS.forEach((pattern) => {
      text = text.replace(pattern, '')
    })
    return FORBIDDEN_DISPLAY_TERMS.some((pattern) => pattern.test(text))
  }
  if (Array.isArray(value)) {
    return value.some(hasForbiddenDisplayText)
  }
  if (value && typeof value === 'object') {
    return Object.values(value).some(hasForbiddenDisplayText)
  }
  return false
}

function getDistributionRows(distribution = {}) {
  return Object.entries(asObject(distribution))
    .map(([key, count]) => ({ key, label: toTitle(key), count }))
    .filter((row) => row.count !== null && row.count !== undefined)
}

function inventoryItemKey(item, index) {
  return String(item.inventory_type || item.label || `inventory-${index}`)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

function inventoryCategoryName(item) {
  const label = item.label || toTitle(item.inventory_type) || 'Inventory'
  return label.replace(/\s+inventory$/i, '').trim() || label
}

function inventoryCountLabel(item) {
  return `${displayValue(item.count, asArray(item.members).length)} ${inventoryCategoryName(item)}`
}

function inventorySummaryText(item) {
  const evidenceMessages = asArray(item.evidence).map(messageFrom).filter(Boolean)
  if (evidenceMessages.length) return evidenceMessages[0]

  const limitationMessages = asArray(item.limitations).map(messageFrom).filter(Boolean)
  if (limitationMessages.length) return limitationMessages[0]

  const freshness = asObject(item.freshness)
  const freshnessState = freshness.freshness_state || freshness.state || freshness.state_code
  if (freshnessState || item.confidence) {
    return `Freshness ${displayValue(freshnessState, 'unavailable')} | Confidence ${displayValue(item.confidence, 'unavailable')}`
  }

  return 'Inventory category reported by the V2 contract.'
}

function inventoryFreshnessRows(item) {
  const freshness = asObject(item.freshness)
  return [
    { label: 'Freshness', value: displayValue(freshness.freshness_state || freshness.state || freshness.state_code) },
    { label: 'Data Through', value: displayValue(freshness.data_through) },
    { label: 'Synced', value: displayValue(freshness.sync_timestamp) },
    { label: 'Stale Notice', value: displayValue(freshness.stale_warning, 'None') },
    { label: 'Missing Data Notice', value: displayValue(freshness.missing_data_warning, 'None') },
  ]
}

function stableDetailKey(value, fallback, index) {
  return String(value || fallback || `detail-${index}`)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

function candidateGroupKey(group, index) {
  return stableDetailKey(group.group_id || group.label, 'candidate-group', index)
}

function candidateGroupSummaryText(group) {
  if (group.description) return group.description

  const explanations = asArray(group.explanations).map(messageFrom).filter(Boolean)
  if (explanations.length) return explanations[0]

  const limitations = asArray(group.limitations).map(messageFrom).filter(Boolean)
  if (limitations.length) return limitations[0]

  const refusalReasons = asArray(group.refusal_reasons).map(messageFrom).filter(Boolean)
  if (refusalReasons.length) return refusalReasons[0]

  return 'Neutral group reported by the V2 contract.'
}

function candidateGroupFreshnessRows(group) {
  const freshness = asObject(group.freshness)
  return [
    { label: 'Freshness', value: displayValue(freshness.freshness_state || freshness.state || freshness.state_code) },
    { label: 'Data Through', value: displayValue(freshness.data_through) },
    { label: 'Synced', value: displayValue(freshness.sync_timestamp) },
    { label: 'Stale Notice', value: displayValue(freshness.stale_warning, 'None') },
    { label: 'Missing Data Notice', value: displayValue(freshness.missing_data_warning, 'None') },
  ]
}

function detailCountLabel(count, singular, plural = `${singular}s`) {
  return `${displayValue(count, '0')} ${count === 1 ? singular : plural}`
}

function messageSummary(messages) {
  if (!messages.length) return null
  if (messages.length === 1) return compactText(messages[0])
  return `${messages.length} entries. First: ${compactText(messages[0])}`
}

function sumRowCounts(rows) {
  return rows.reduce((total, row) => {
    const numeric = Number(row.count)
    return Number.isFinite(numeric) ? total + numeric : total
  }, 0)
}

function contextIndicatorMessages(value) {
  const arrayValue = asArray(value)
  if (arrayValue.length) {
    return arrayValue.map((item) => messageFrom(item) || displayValue(item)).filter(Boolean)
  }

  const objectValue = asObject(value)
  return Object.entries(objectValue).flatMap(([key, item]) => {
    if (Array.isArray(item)) {
      return [`${toTitle(key)}: ${detailCountLabel(item.length, 'entry', 'entries')}`]
    }
    if (item && typeof item === 'object') {
      return Object.entries(item).map(([nestedKey, nestedValue]) => (
        `${toTitle(key)} ${toTitle(nestedKey)}: ${displayValue(nestedValue)}`
      ))
    }
    return [`${toTitle(key)}: ${displayValue(item)}`]
  })
}

function getDiagnosticCount(view = {}) {
  return (
    asArray(view.missingFields).length
    + asArray(view.malformedFields).length
    + asArray(view.forbiddenFieldPaths).length
  )
}

function failClosedPrimaryReason(failClosed, statusMetadata) {
  return (
    failClosed.primary_reason_code
    || statusMetadata.fail_closed_reason_code
    || asArray(failClosed.reason_codes)[0]
    || 'Not reported'
  )
}

function failClosedAlertLabel(failClosed, statusMetadata) {
  return displayValue(
    failClosed.display_label || statusMetadata.display_label,
    'Fail-Closed',
  )
}

function failClosedStatusLabel(failClosed, statusMetadata) {
  const label = failClosedAlertLabel(failClosed, statusMetadata)
  if (/data freshness protection active/i.test(label)) {
    return 'Freshness Protected'
  }
  if (/trust protection active/i.test(label)) {
    return 'Trust Protected'
  }
  return label
}

function failClosedReasonSummary(failClosed, statusMetadata) {
  return displayValue(
    failClosed.reason_summary || statusMetadata.reason_summary,
    'V2 fail-closed protection is active and refusal metadata is preserved.',
  )
}

function failClosedWithheldSummary(failClosed, statusMetadata) {
  return displayValue(
    failClosed.withheld_summary || statusMetadata.withheld_summary,
    'Bullpen state output is controlled by the current V2 protection state.',
  )
}

function failClosedRows(failClosed, statusMetadata, freshness) {
  return [
    { label: 'Fail-closed state', value: displayValue(failClosed.state || statusMetadata.fail_closed_state) },
    { label: 'Reason code', value: displayValue(failClosedPrimaryReason(failClosed, statusMetadata)) },
    { label: 'Freshness failed', value: displayValue(failClosed.freshness_failed ?? statusMetadata.freshness_failed) },
    { label: 'Trust failed', value: displayValue(failClosed.trust_failed ?? statusMetadata.trust_failed) },
    { label: 'Partial context safe', value: displayValue(failClosed.partial_context_safe ?? statusMetadata.partial_context_safe) },
    { label: 'Source freshness', value: displayValue(freshness.source_freshness_status || statusMetadata.source_freshness_status) },
    { label: 'Aggregate freshness', value: displayValue(freshness.aggregate_v2_freshness_status || statusMetadata.aggregate_v2_freshness_status) },
    { label: 'Synced', value: displayValue(freshness.sync_timestamp || statusMetadata.sync_timestamp) },
  ]
}

export function getRecommendationV2BullpenStateView(state = null) {
  if (!state) {
    return {
      contractState: 'empty',
      isAvailable: false,
      isFailClosed: false,
      isUnavailable: true,
      title: 'V2 Bullpen Intelligence',
      statusLabel: 'Unavailable',
      statusTone: 'border-dirt bg-field/40 text-chalk400',
      failClosedLabel: null,
      failClosedReasonSummary: null,
      failClosedWithheldSummary: null,
      failClosedRows: [],
      trustRows: [],
      freshnessRows: [],
      diagnosticCount: 0,
      hiddenUnsafeLanguage: false,
      bullpenState: null,
      inventory: [],
      candidateGroups: [],
      teamContext: {},
      limitationMessages: [],
      explanationMessages: [],
      refusalMessages: [],
    }
  }

  const unsafeVisibleLanguage = hasForbiddenDisplayText([
    state.bullpenState,
    state.limitations,
    state.explanations,
    state.refusalReasons,
  ])
  const isContractSafe = state.isContractSafe === true && !unsafeVisibleLanguage
  const contractState = isContractSafe ? state.contractState : 'unavailable'
  const isFailClosed = contractState === 'fail_closed'
  const isAvailable = contractState === 'available'
  const isUnavailable = contractState === 'unavailable'
  const bullpenState = isContractSafe ? asObject(state.bullpenState) : null
  const exposeMessages = !unsafeVisibleLanguage

  const statusTone = isFailClosed
    ? 'border-amber/40 bg-amber/5 text-amber'
    : isUnavailable
      ? 'border-red-500/35 bg-red-500/5 text-red-300'
      : 'border-emerald-500/30 bg-emerald-500/5 text-emerald-300'

  const trustMetadata = asObject(state.trustMetadata)
  const freshness = asObject(state.freshness)
  const failClosed = asObject(state.failClosed)
  const statusMetadata = asObject(state.statusMetadata)
  const failClosedLabel = failClosedAlertLabel(failClosed, statusMetadata)

  return {
    contractState,
    isAvailable,
    isFailClosed,
    isUnavailable,
    title: 'V2 Bullpen Intelligence',
    statusLabel: isFailClosed ? failClosedStatusLabel(failClosed, statusMetadata) : isUnavailable ? 'Unavailable' : 'Available',
    statusTone,
    failClosedLabel,
    failClosedReasonSummary: failClosedReasonSummary(failClosed, statusMetadata),
    failClosedWithheldSummary: failClosedWithheldSummary(failClosed, statusMetadata),
    failClosedRows: isFailClosed ? failClosedRows(failClosed, statusMetadata, freshness) : [],
    hiddenUnsafeLanguage: unsafeVisibleLanguage,
    diagnosticCount: getDiagnosticCount(state) + (unsafeVisibleLanguage ? 1 : 0),
    governanceRows: [
      {
        label: 'ranking_applied',
        value: displayValue(state.governance?.rankingApplied, 'missing'),
        safe: state.governance?.rankingApplied === false,
      },
      {
        label: 'selection_made',
        value: displayValue(state.governance?.selectionMade, 'missing'),
        safe: state.governance?.selectionMade === false,
      },
    ],
    trustRows: [
      { label: 'Scope', value: displayValue(trustMetadata.scope || state.scope) },
      { label: 'Confidence', value: displayValue(trustMetadata.confidence || state.confidence) },
      { label: 'Data State', value: displayValue(trustMetadata.data_state || state.dataState) },
      { label: 'Generated', value: displayValue(trustMetadata.generated_at || state.generatedAt) },
    ],
    freshnessRows: [
      { label: 'Freshness', value: displayValue(freshness.freshness_state || freshness.state || freshness.state_code) },
      { label: 'Source Freshness', value: displayValue(freshness.source_freshness_status || statusMetadata.source_freshness_status) },
      { label: 'Aggregate V2 Freshness', value: displayValue(freshness.aggregate_v2_freshness_status || statusMetadata.aggregate_v2_freshness_status) },
      { label: 'Data Through', value: displayValue(freshness.data_through) },
      { label: 'Synced', value: displayValue(freshness.sync_timestamp) },
      { label: 'Overall Sync', value: displayValue(freshness.overall_sync_status || statusMetadata.overall_sync_status) },
      { label: 'Sync Current', value: displayValue(freshness.overall_sync_current ?? statusMetadata.overall_sync_current) },
      { label: 'Stale Notice', value: displayValue(freshness.stale_warning, 'None') },
      { label: 'Missing Data Notice', value: displayValue(freshness.missing_data_warning, 'None') },
    ],
    bullpenState,
    inventory: asArray(bullpenState?.inventory_summary),
    candidateGroups: asArray(bullpenState?.candidate_groups),
    teamContext: asObject(bullpenState?.team_context),
    limitationMessages: exposeMessages ? asArray(state.limitations).map(messageFrom).filter(Boolean) : [],
    explanationMessages: exposeMessages ? asArray(state.explanations).map(messageFrom).filter(Boolean) : [],
    refusalMessages: exposeMessages ? asArray(state.refusalReasons).map(messageFrom).filter(Boolean) : [],
  }
}

function MetadataGrid({ title, rows }) {
  const id = sectionId(title)

  return (
    <section className="min-w-0 rounded border border-dirt bg-field/35 p-4" aria-labelledby={id}>
      <h3 id={id} className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">{title}</h3>
      <div className="v2-governed-panel__metadata-grid gap-2">
        {rows.map((row) => (
          <div key={row.label} className="min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{row.label}</div>
            <div className="v2-governed-panel__text mt-0.5 font-mono text-xs text-chalk200">{row.value}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

function GovernanceRows({ rows }) {
  return (
    <section className="min-w-0 rounded border border-dirt bg-field/35 p-4" aria-labelledby="recommendation-v2-governance">
      <h3 id="recommendation-v2-governance" className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">Governance</h3>
      <div className="v2-governed-panel__metadata-grid gap-2">
        {rows.map((row) => (
          <div key={row.label} className="flex min-w-0 items-center justify-between gap-3 rounded border border-dirt bg-chalk/20 px-3 py-2">
            <span className="min-w-0 font-mono text-[11px] text-chalk400">{row.label}</span>
            <span className={`shrink-0 font-mono text-xs font-semibold ${row.safe ? 'text-emerald-300' : 'text-red-300'}`}>
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}

function detailExpansionKey(parentKey, detailKey) {
  return `${parentKey}:${detailKey}`
}

function hasInitialDetailExpansion(initialExpandedDetailKeys = [], parentKey, detailKey) {
  return initialExpandedDetailKeys.includes(detailExpansionKey(parentKey, detailKey))
}

function DetailToggleButton({
  expanded,
  controls,
  onClick,
  expandLabel = 'View Details',
  collapseLabel = 'Hide Details',
}) {
  return (
    <button
      type="button"
      className="mt-3 w-full rounded border border-dirt bg-field/60 px-3 py-2 text-left font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
      aria-expanded={expanded}
      aria-controls={controls}
      onClick={onClick}
    >
      {expanded ? collapseLabel : expandLabel}
    </button>
  )
}

function PanelDisclosure({
  title,
  summary,
  initiallyExpanded = false,
  children,
}) {
  const detailId = sectionId(`${title}-details`)
  const [expanded, setExpanded] = useState(initiallyExpanded)

  return (
    <section className="min-w-0 rounded border border-dirt bg-field/35 p-4" aria-labelledby={`${detailId}-heading`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 id={`${detailId}-heading`} className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{title}</h3>
          {summary && (
            <p className="v2-governed-panel__text mt-1 text-xs leading-relaxed text-chalk500">
              {summary}
            </p>
          )}
        </div>
        <button
          type="button"
          className="rounded border border-dirt bg-field/60 px-3 py-2 text-left font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus:ring-2 focus:ring-amber/60 focus:ring-offset-2 focus:ring-offset-dugout"
          aria-expanded={expanded}
          aria-controls={detailId}
          onClick={() => setExpanded(current => !current)}
        >
          {expanded ? `Hide ${title}` : `View ${title}`}
        </button>
      </div>
      {expanded && (
        <div id={detailId} className="mt-4 space-y-4">
          {children}
        </div>
      )}
    </section>
  )
}

function CollapsibleDetailBlock({
  title,
  detailId,
  countLabel = null,
  summary = null,
  emptyText = 'None reported.',
  children,
  initiallyExpanded = false,
  expandLabel = 'View Details',
  collapseLabel = 'Hide Details',
}) {
  const [expanded, setExpanded] = useState(initiallyExpanded)
  const hasChildren = Boolean(children)

  return (
    <div className="min-w-0 rounded border border-dirt bg-chalk/20 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{title}</div>
      {countLabel && (
        <div className="v2-governed-panel__text mt-1 font-mono text-[11px] text-chalk500">{countLabel}</div>
      )}
      <div className="v2-governed-panel__text mt-1 text-xs leading-relaxed text-chalk300">
        {summary || emptyText}
      </div>
      {hasChildren && (
        <>
          <DetailToggleButton
            expanded={expanded}
            controls={detailId}
            onClick={() => setExpanded((current) => !current)}
            expandLabel={expandLabel}
            collapseLabel={collapseLabel}
          />
          {expanded && (
            <div id={detailId} className="mt-3 min-w-0">
              {children}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function DetailMessageGroup({ title, messages, emptyText = 'None reported.' }) {
  return (
    <div className="min-w-0">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-chalk600">{title}</div>
      {messages.length ? (
        <ul className="space-y-2">
          {messages.map((message) => (
            <li key={message} className="v2-governed-panel__text rounded border border-dirt bg-chalk/30 px-3 py-2 text-xs leading-relaxed text-chalk300">
              {message}
            </li>
          ))}
        </ul>
      ) : (
        <div className="font-mono text-xs text-chalk500">{emptyText}</div>
      )}
    </div>
  )
}

function DetailRows({ title, rows }) {
  return (
    <div className="min-w-0">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-chalk600">{title}</div>
      {rows.length ? (
        <div className="grid gap-2">
          {rows.map((row) => (
            <div key={row.label} className="flex min-w-0 items-center justify-between gap-3 rounded border border-dirt bg-chalk/30 px-3 py-2">
              <span className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{row.label}</span>
              <span className="v2-governed-panel__text text-right font-mono text-xs text-chalk200">{row.value}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="font-mono text-xs text-chalk500">Unavailable</div>
      )}
    </div>
  )
}

function MessageList({ title, messages, emptyText, initiallyExpanded = false }) {
  const id = sectionId(title)
  const detailId = `${id}-details`
  const [expanded, setExpanded] = useState(initiallyExpanded)
  const summary = messageSummary(messages)

  return (
    <section className="min-w-0 rounded border border-dirt bg-field/35 p-4" aria-labelledby={id}>
      <h3 id={id} className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">{title}</h3>
      {messages.length ? (
        <>
          <div className="rounded border border-dirt bg-chalk/20 px-3 py-2">
            <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">
              {detailCountLabel(messages.length, 'entry', 'entries')}
            </div>
            <div className="v2-governed-panel__text mt-1 text-sm leading-relaxed text-chalk300">
              {summary}
            </div>
          </div>
          {messages.length > 1 && (
            <>
              <DetailToggleButton
                expanded={expanded}
                controls={detailId}
                onClick={() => setExpanded((current) => !current)}
              />
              {expanded && (
                <ul id={detailId} className="mt-3 space-y-2">
                  {messages.map((message) => (
                    <li key={message} className="v2-governed-panel__text rounded border border-dirt bg-chalk/20 px-3 py-2 text-sm leading-relaxed text-chalk300">
                      {message}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </>
      ) : (
        <div className="font-mono text-xs text-chalk500">{emptyText}</div>
      )}
    </section>
  )
}

function InventorySummary({
  inventory,
  initialExpandedInventoryKeys = [],
  initialExpandedInventoryDetailKeys = [],
}) {
  const [expandedInventoryKeys, setExpandedInventoryKeys] = useState(
    () => new Set(initialExpandedInventoryKeys),
  )

  const toggleInventory = (key) => {
    setExpandedInventoryKeys((current) => {
      const next = new Set(current)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  return (
    <section className="min-w-0 rounded border border-dirt bg-field/35 p-4" aria-labelledby="recommendation-v2-inventory">
      <h3 id="recommendation-v2-inventory" className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">Inventory</h3>
      {inventory.length ? (
        <div className="v2-governed-panel__inventory-grid gap-3">
          {inventory.map((item, index) => {
            const key = inventoryItemKey(item, index)
            const expanded = expandedInventoryKeys.has(key)
            const detailId = `recommendation-v2-inventory-${key}-details`
            const members = asArray(item.members)
            const evidence = asArray(item.evidence).map(messageFrom).filter(Boolean)
            const limitations = asArray(item.limitations).map(messageFrom).filter(Boolean)
            const memberDetailId = `${detailId}-members`
            const evidenceDetailId = `${detailId}-evidence`
            const limitationDetailId = `${detailId}-limitations`

            return (
              <div key={key} className="min-w-0 rounded border border-dirt bg-chalk/20 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="v2-governed-panel__text text-sm font-semibold text-chalk200">{item.label || toTitle(item.inventory_type)}</div>
                  <div className="v2-governed-panel__text mt-1 font-mono text-[11px] text-chalk500">{inventoryCountLabel(item)}</div>
                </div>
                <div className="shrink-0 rounded border border-dirt bg-field/50 px-2 py-1 font-mono text-xs text-chalk200">
                  {displayValue(item.count, '0')}
                </div>
              </div>
              <div className="v2-governed-panel__text mt-3 text-xs leading-relaxed text-chalk500">
                {inventorySummaryText(item)}
              </div>
              <div className="mt-3 grid gap-2">
                <div className="flex min-w-0 items-center justify-between gap-3 rounded border border-dirt bg-field/50 px-3 py-2">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-chalk600">Confidence</span>
                  <span className="v2-governed-panel__text text-right font-mono text-xs text-chalk200">
                    {displayValue(item.confidence, 'Unavailable')}
                  </span>
                </div>
                <div className="flex min-w-0 items-center justify-between gap-3 rounded border border-dirt bg-field/50 px-3 py-2">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-chalk600">Freshness</span>
                  <span className="v2-governed-panel__text text-right font-mono text-xs text-chalk200">
                    {displayValue(asObject(item.freshness).freshness_state || asObject(item.freshness).state || asObject(item.freshness).state_code)}
                  </span>
                </div>
              </div>
              <button
                type="button"
                className="mt-3 w-full rounded border border-dirt bg-field/60 px-3 py-2 text-left font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
                aria-expanded={expanded}
                aria-controls={detailId}
                onClick={() => toggleInventory(key)}
              >
                {expanded ? 'Hide Details' : 'View Details'}
              </button>
              {expanded && (
                <div id={detailId} className="mt-3 min-w-0 rounded border border-dirt bg-field/45 p-3">
                  <div className="grid gap-3">
                    <CollapsibleDetailBlock
                      title={`Members (${members.length})`}
                      detailId={memberDetailId}
                      countLabel={detailCountLabel(members.length, 'member')}
                      summary={members.length ? 'Full inventory membership remains available on demand.' : 'No members reported.'}
                      emptyText="No members reported."
                      expandLabel="View Members"
                      collapseLabel="Hide Members"
                      initiallyExpanded={hasInitialDetailExpansion(initialExpandedInventoryDetailKeys, key, 'members')}
                    >
                      {members.length ? (
                        <div className="flex flex-wrap gap-2">
                          {members.map((member) => (
                            <span key={`${member.pitcher_id || member.display_name}`} className="rounded border border-dirt bg-chalk/30 px-2 py-1 font-mono text-[11px] text-chalk300">
                              {member.display_name || member.pitcher_id}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </CollapsibleDetailBlock>

                    <CollapsibleDetailBlock
                      title="Evidence"
                      detailId={evidenceDetailId}
                      countLabel={detailCountLabel(evidence.length, 'entry', 'entries')}
                      summary={messageSummary(evidence) || 'No evidence reported.'}
                      emptyText="No evidence reported."
                      expandLabel="View Evidence"
                      collapseLabel="Hide Evidence"
                      initiallyExpanded={hasInitialDetailExpansion(initialExpandedInventoryDetailKeys, key, 'evidence')}
                    >
                      {evidence.length ? (
                        <ul className="space-y-2">
                          {evidence.map((message) => (
                            <li key={message} className="v2-governed-panel__text rounded border border-dirt bg-chalk/30 px-3 py-2 text-xs leading-relaxed text-chalk300">
                              {message}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </CollapsibleDetailBlock>

                    <div className="min-w-0">
                      <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-chalk600">Inventory Freshness</div>
                      <div className="grid gap-2">
                        {inventoryFreshnessRows(item).map((row) => (
                          <div key={row.label} className="flex min-w-0 items-center justify-between gap-3 rounded border border-dirt bg-chalk/30 px-3 py-2">
                            <span className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{row.label}</span>
                            <span className="v2-governed-panel__text text-right font-mono text-xs text-chalk200">{row.value}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {limitations.length > 0 && (
                      <CollapsibleDetailBlock
                        title="Limitations"
                        detailId={limitationDetailId}
                        countLabel={detailCountLabel(limitations.length, 'entry', 'entries')}
                        summary={messageSummary(limitations)}
                        emptyText="No limitations reported."
                        expandLabel="View Limitations"
                        collapseLabel="Hide Limitations"
                        initiallyExpanded={hasInitialDetailExpansion(initialExpandedInventoryDetailKeys, key, 'limitations')}
                      >
                        <ul className="space-y-2">
                          {limitations.map((message) => (
                            <li key={message} className="v2-governed-panel__text rounded border border-dirt bg-chalk/30 px-3 py-2 text-xs leading-relaxed text-chalk300">
                              {message}
                            </li>
                          ))}
                        </ul>
                      </CollapsibleDetailBlock>
                    )}
                  </div>
                </div>
              )}
            </div>
            )
          })}
        </div>
      ) : (
        <div className="font-mono text-xs text-chalk500">No inventory summary available.</div>
      )}
    </section>
  )
}

function CandidateGroups({
  groups,
  initialExpandedCandidateGroupKeys = [],
  initialExpandedCandidateDetailKeys = [],
}) {
  const [expandedGroupKeys, setExpandedGroupKeys] = useState(
    () => new Set(initialExpandedCandidateGroupKeys),
  )

  const toggleGroup = (key) => {
    setExpandedGroupKeys((current) => {
      const next = new Set(current)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  return (
    <section className="min-w-0 rounded border border-dirt bg-field/35 p-4" aria-labelledby="recommendation-v2-candidate-groups">
      <h3 id="recommendation-v2-candidate-groups" className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">Neutral Candidate Groups</h3>
      {groups.length ? (
        <div className="grid gap-3">
          {groups.map((group, index) => {
            const key = candidateGroupKey(group, index)
            const expanded = expandedGroupKeys.has(key)
            const detailId = `recommendation-v2-candidate-group-${key}-details`
            const candidates = asArray(group.candidates)
            const eligibility = asArray(group.eligibility_basis).map(messageFrom).filter(Boolean)
            const explanations = asArray(group.explanations).map(messageFrom).filter(Boolean)
            const limitations = asArray(group.limitations).map(messageFrom).filter(Boolean)
            const refusalReasons = asArray(group.refusal_reasons).map(messageFrom).filter(Boolean)
            const freshness = asObject(group.freshness)
            const memberDetailId = `${detailId}-members`
            const eligibilityDetailId = `${detailId}-eligibility`
            const explanationDetailId = `${detailId}-explanations`
            const limitationDetailId = `${detailId}-limitations`
            const refusalDetailId = `${detailId}-refusal`

            return (
              <div key={key} className="min-w-0 rounded border border-dirt bg-chalk/20 p-3">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="v2-governed-panel__text text-sm font-semibold text-chalk200">{group.label || toTitle(group.group_id)}</div>
                  <div className="v2-governed-panel__text mt-1 font-mono text-[11px] text-chalk500">
                    {detailCountLabel(group.candidate_count ?? candidates.length, 'member')}
                  </div>
                </div>
                <div className="shrink-0 rounded border border-dirt bg-field/50 px-2 py-1 font-mono text-xs text-chalk300">
                  {displayValue(group.candidate_count, asArray(group.candidates).length)}
                </div>
              </div>
              <div className="v2-governed-panel__text mt-3 text-xs leading-relaxed text-chalk500">
                {candidateGroupSummaryText(group)}
              </div>
              <div className="mt-3 grid gap-2">
                <div className="flex min-w-0 items-center justify-between gap-3 rounded border border-dirt bg-field/50 px-3 py-2">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-chalk600">Ordering</span>
                  <span className="v2-governed-panel__text text-right font-mono text-xs text-chalk200">
                    {orderingPolicyLabel(group.ordering)}
                  </span>
                </div>
                <div className="flex min-w-0 items-center justify-between gap-3 rounded border border-dirt bg-field/50 px-3 py-2">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-chalk600">Confidence</span>
                  <span className="v2-governed-panel__text text-right font-mono text-xs text-chalk200">
                    {displayValue(group.confidence, 'Unavailable')}
                  </span>
                </div>
                <div className="flex min-w-0 items-center justify-between gap-3 rounded border border-dirt bg-field/50 px-3 py-2">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-chalk600">Freshness</span>
                  <span className="v2-governed-panel__text text-right font-mono text-xs text-chalk200">
                    {displayValue(freshness.freshness_state || freshness.state || freshness.state_code)}
                  </span>
                </div>
              </div>
              <DetailToggleButton
                expanded={expanded}
                controls={detailId}
                onClick={() => toggleGroup(key)}
              />
              {expanded && (
                <div id={detailId} className="mt-3 min-w-0 rounded border border-dirt bg-field/45 p-3">
                  <div className="grid gap-3">
                    <CollapsibleDetailBlock
                      title={`Group Members (${candidates.length})`}
                      detailId={memberDetailId}
                      countLabel={detailCountLabel(candidates.length, 'member')}
                      summary={candidates.length ? 'Full group membership remains available on demand.' : 'No group members reported.'}
                      emptyText="No group members reported."
                      expandLabel="View Members"
                      collapseLabel="Hide Members"
                      initiallyExpanded={hasInitialDetailExpansion(initialExpandedCandidateDetailKeys, key, 'members')}
                    >
                      {candidates.length ? (
                        <div className="flex flex-wrap gap-2">
                          {candidates.map((candidate) => (
                            <span key={`${candidate.pitcher_id || candidate.display_name}`} className="rounded border border-dirt bg-chalk/30 px-2 py-1 font-mono text-[11px] text-chalk300">
                              {candidate.display_name || candidate.pitcher_id}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </CollapsibleDetailBlock>
                    <CollapsibleDetailBlock
                      title="Eligibility Basis"
                      detailId={eligibilityDetailId}
                      countLabel={detailCountLabel(eligibility.length, 'entry', 'entries')}
                      summary={messageSummary(eligibility) || 'No eligibility basis reported.'}
                      emptyText="No eligibility basis reported."
                      expandLabel="View Eligibility"
                      collapseLabel="Hide Eligibility"
                      initiallyExpanded={hasInitialDetailExpansion(initialExpandedCandidateDetailKeys, key, 'eligibility')}
                    >
                      {eligibility.length ? (
                        <DetailMessageGroup title="Eligibility Basis Details" messages={eligibility} emptyText="No eligibility basis reported." />
                      ) : null}
                    </CollapsibleDetailBlock>
                    <DetailRows title="Group Freshness" rows={candidateGroupFreshnessRows(group)} />
                    <CollapsibleDetailBlock
                      title="Explanations"
                      detailId={explanationDetailId}
                      countLabel={detailCountLabel(explanations.length, 'entry', 'entries')}
                      summary={messageSummary(explanations) || 'No explanations reported.'}
                      emptyText="No explanations reported."
                      expandLabel="View Explanations"
                      collapseLabel="Hide Explanations"
                      initiallyExpanded={hasInitialDetailExpansion(initialExpandedCandidateDetailKeys, key, 'explanations')}
                    >
                      {explanations.length ? (
                        <DetailMessageGroup title="Explanation Details" messages={explanations} emptyText="No explanations reported." />
                      ) : null}
                    </CollapsibleDetailBlock>
                    <CollapsibleDetailBlock
                      title="Limitations"
                      detailId={limitationDetailId}
                      countLabel={detailCountLabel(limitations.length, 'entry', 'entries')}
                      summary={messageSummary(limitations) || 'No limitations reported.'}
                      emptyText="No limitations reported."
                      expandLabel="View Limitations"
                      collapseLabel="Hide Limitations"
                      initiallyExpanded={hasInitialDetailExpansion(initialExpandedCandidateDetailKeys, key, 'limitations')}
                    >
                      {limitations.length ? (
                        <DetailMessageGroup title="Limitation Details" messages={limitations} emptyText="No limitations reported." />
                      ) : null}
                    </CollapsibleDetailBlock>
                    <CollapsibleDetailBlock
                      title="Refusal"
                      detailId={refusalDetailId}
                      countLabel={detailCountLabel(refusalReasons.length, 'entry', 'entries')}
                      summary={messageSummary(refusalReasons) || 'No refusal metadata reported.'}
                      emptyText="No refusal metadata reported."
                      expandLabel="View Refusal"
                      collapseLabel="Hide Refusal"
                      initiallyExpanded={hasInitialDetailExpansion(initialExpandedCandidateDetailKeys, key, 'refusal')}
                    >
                      {refusalReasons.length ? (
                        <DetailMessageGroup title="Refusal Details" messages={refusalReasons} emptyText="No refusal metadata reported." />
                      ) : null}
                    </CollapsibleDetailBlock>
                  </div>
                </div>
              )}
            </div>
            )
          })}
        </div>
      ) : (
        <div className="font-mono text-xs text-chalk500">No neutral groups available from the current contract state.</div>
      )}
    </section>
  )
}

function TeamContext({ context, initialExpandedTeamContextKeys = [] }) {
  const availabilityRows = getDistributionRows(context.availability_distribution)
  const workloadRows = getDistributionRows(context.workload_distribution)
  const readiness = contextIndicatorMessages(context.readiness_indicators)
  const stress = contextIndicatorMessages(context.stress_indicators)
  const [expandedContextKeys, setExpandedContextKeys] = useState(
    () => new Set(initialExpandedTeamContextKeys),
  )

  const toggleContext = (key) => {
    setExpandedContextKeys((current) => {
      const next = new Set(current)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  return (
    <section className="min-w-0 rounded border border-dirt bg-field/35 p-4" aria-labelledby="recommendation-v2-team-context">
      <h3 id="recommendation-v2-team-context" className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">Team Context</h3>
      <div className="v2-governed-panel__team-grid gap-4">
        <Distribution title="Availability" rows={availabilityRows} expanded={expandedContextKeys.has('availability')} onToggle={() => toggleContext('availability')} />
        <Distribution title="Workload" rows={workloadRows} expanded={expandedContextKeys.has('workload')} onToggle={() => toggleContext('workload')} />
      </div>
      <div className="v2-governed-panel__team-grid mt-4 gap-4">
        <SimpleItems title="Readiness" messages={readiness} expanded={expandedContextKeys.has('readiness')} onToggle={() => toggleContext('readiness')} />
        <SimpleItems title="Stress" messages={stress} expanded={expandedContextKeys.has('stress')} onToggle={() => toggleContext('stress')} />
      </div>
    </section>
  )
}

function Distribution({ title, rows, expanded, onToggle }) {
  const key = stableDetailKey(title, 'distribution', 0)
  const detailId = `recommendation-v2-team-context-${key}-details`
  const total = sumRowCounts(rows)

  return (
    <div className="min-w-0">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-chalk600">{title}</div>
      {rows.length ? (
        <>
          <div className="rounded border border-dirt bg-chalk/20 px-3 py-2">
            <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">
              {detailCountLabel(rows.length, 'category', 'categories')}
            </div>
            <div className="v2-governed-panel__text mt-1 text-sm leading-relaxed text-chalk300">
              {total > 0 ? `${displayValue(total)} total reported across ${title.toLowerCase()} context.` : `${title} context is available.`}
            </div>
          </div>
          <DetailToggleButton
            expanded={expanded}
            controls={detailId}
            onClick={onToggle}
            expandLabel="View Distribution"
            collapseLabel="Hide Distribution"
          />
          {expanded && (
            <div id={detailId} className="mt-3 space-y-2">
              {rows.map((row) => (
                <div key={row.key} className="flex min-w-0 items-center justify-between gap-3 rounded border border-dirt bg-chalk/20 px-3 py-2">
                  <span className="v2-governed-panel__text font-mono text-xs text-chalk400">{row.label}</span>
                  <span className="shrink-0 font-mono text-xs font-semibold text-chalk200">{displayValue(row.count)}</span>
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="font-mono text-xs text-chalk500">Unavailable</div>
      )}
    </div>
  )
}

function SimpleItems({ title, messages, expanded, onToggle }) {
  const key = stableDetailKey(title, 'items', 0)
  const detailId = `recommendation-v2-team-context-${key}-details`

  return (
    <div className="min-w-0">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-chalk600">{title}</div>
      {messages.length ? (
        <>
          <div className="rounded border border-dirt bg-chalk/20 px-3 py-2">
            <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">
              {detailCountLabel(messages.length, 'indicator')}
            </div>
            <div className="v2-governed-panel__text mt-1 text-sm leading-relaxed text-chalk300">
              {messageSummary(messages)}
            </div>
          </div>
          <DetailToggleButton
            expanded={expanded}
            controls={detailId}
            onClick={onToggle}
            expandLabel="View Indicators"
            collapseLabel="Hide Indicators"
          />
          {expanded && (
            <div id={detailId} className="mt-3 space-y-2">
              {messages.map((message) => (
                <div key={message} className="v2-governed-panel__text rounded border border-dirt bg-chalk/20 px-3 py-2 text-xs text-chalk300">
                  {message}
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="font-mono text-xs text-chalk500">Unavailable</div>
      )}
    </div>
  )
}

export default function RecommendationV2BullpenStatePanel({
  state,
  loading = false,
  error = null,
  onRetry,
  compact = false,
  initialExpandedInventoryKeys = [],
  initialExpandedInventoryDetailKeys = [],
  initialExpandedCandidateGroupKeys = [],
  initialExpandedCandidateDetailKeys = [],
  initialExpandedTeamContextKeys = [],
  initialExpandedMessageSections = [],
}) {
  if (loading) {
    return (
      <section
        className="v2-governed-panel card mb-8 w-full min-w-0 max-w-full overflow-hidden"
        role="status"
        aria-live="polite"
        aria-busy="true"
        aria-label="Loading V2 bullpen intelligence"
      >
        <LoadingPane message="Loading V2 bullpen intelligence..." />
      </section>
    )
  }

  if (error) {
    return (
      <section
        className="v2-governed-panel card mb-8 w-full min-w-0 max-w-full overflow-hidden"
        role="alert"
        aria-label="V2 bullpen intelligence unavailable"
      >
        <ErrorState message="V2 bullpen intelligence could not be loaded." onRetry={onRetry} />
      </section>
    )
  }

  const view = getRecommendationV2BullpenStateView(state)
  const evidenceSections = (
    <>
      <MetadataGrid title="Trust" rows={view.trustRows} />
      <MetadataGrid title="Freshness" rows={view.freshnessRows} />

      {!view.isUnavailable && (
        <>
          <InventorySummary
            inventory={view.inventory}
            initialExpandedInventoryKeys={initialExpandedInventoryKeys}
            initialExpandedInventoryDetailKeys={initialExpandedInventoryDetailKeys}
          />
          <TeamContext context={view.teamContext} initialExpandedTeamContextKeys={initialExpandedTeamContextKeys} />
          <CandidateGroups
            groups={view.candidateGroups}
            initialExpandedCandidateGroupKeys={initialExpandedCandidateGroupKeys}
            initialExpandedCandidateDetailKeys={initialExpandedCandidateDetailKeys}
          />
        </>
      )}

      <div className="v2-governed-panel__message-grid gap-4">
        <MessageList title="Limitations" messages={view.limitationMessages} emptyText="No limitations reported." initiallyExpanded={initialExpandedMessageSections.includes('limitations')} />
        <MessageList title="Explanations" messages={view.explanationMessages} emptyText="No explanations reported." initiallyExpanded={initialExpandedMessageSections.includes('explanations')} />
        <MessageList title="Refusal" messages={view.refusalMessages} emptyText="No refusal metadata reported." initiallyExpanded={initialExpandedMessageSections.includes('refusal')} />
      </div>
    </>
  )

  return (
    <section
      className={`${compact ? 'mb-5' : 'mb-8'} v2-governed-panel card w-full min-w-0 max-w-full overflow-hidden animate-fade-up opacity-0`}
      style={{ animationFillMode: 'forwards' }}
      aria-labelledby="recommendation-v2-heading"
      aria-describedby="recommendation-v2-description"
    >
      <div className={`${compact ? 'p-4' : 'p-5'} border-b border-dirt bg-chalk/20`}>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="font-mono text-xs uppercase tracking-widest text-chalk400">{view.title}</div>
            <h2 id="recommendation-v2-heading" className={`${compact ? 'text-xl' : 'text-2xl'} mt-1 font-display tracking-wider text-chalk100`}>Bullpen State</h2>
            <p id="recommendation-v2-description" className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk500">
              Governed bullpen visibility from the V2 contract. This surface summarizes context and evidence only.
            </p>
          </div>
          <div
            className={`shrink-0 self-start rounded border px-3 py-2 font-mono text-xs uppercase tracking-widest ${view.statusTone}`}
            aria-label={`V2 contract state: ${view.statusLabel}`}
          >
            {view.statusLabel}
          </div>
        </div>
      </div>

      <div className={`${compact ? 'space-y-4 p-4' : 'space-y-5 p-4 sm:p-5 lg:p-6'}`}>
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          {`V2 bullpen intelligence ${view.statusLabel}. ranking_applied ${displayValue(state?.governance?.rankingApplied, 'missing')}. selection_made ${displayValue(state?.governance?.selectionMade, 'missing')}.`}
        </div>

        {view.isUnavailable && (
          <div className="min-w-0 rounded border border-red-500/35 bg-red-500/5 p-4" role="alert" aria-live="assertive">
            <div className="font-mono text-xs uppercase tracking-widest text-red-300">Contract Unavailable</div>
            <p className="v2-governed-panel__text mt-2 text-sm leading-relaxed text-chalk400">
              Required V2 metadata is missing, malformed, or outside governed display boundaries.
              Bullpen state output is withheld from this surface.
            </p>
            {view.diagnosticCount > 0 && (
              <div className="mt-3 font-mono text-xs text-chalk500">
                Diagnostics detected: {view.diagnosticCount}
              </div>
            )}
          </div>
        )}

        {view.isFailClosed && (
          <div className="min-w-0 rounded border border-amber/40 bg-amber/5 p-4" role="alert" aria-live="assertive">
            <div className="font-mono text-xs uppercase tracking-widest text-amber">{view.failClosedLabel}</div>
            <p className="v2-governed-panel__text mt-2 text-sm leading-relaxed text-chalk400">
              {view.failClosedReasonSummary}
            </p>
            <p className="v2-governed-panel__text mt-2 text-sm leading-relaxed text-chalk500">
              {view.failClosedWithheldSummary}
            </p>
            <div className="v2-governed-panel__metadata-grid mt-3 gap-2">
              {view.failClosedRows.map((row) => (
                <div key={row.label} className="min-w-0">
                  <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{row.label}</div>
                  <div className="v2-governed-panel__text mt-0.5 font-mono text-xs text-chalk200">{row.value}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {view.bullpenState && (
          <section className="min-w-0 rounded border border-dirt bg-field/35 p-4" aria-labelledby="recommendation-v2-state">
            <h3 id="recommendation-v2-state" className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">State</h3>
            <div className="v2-governed-panel__state-grid gap-3">
              <StatusCell label="Status" value={view.bullpenState.status} />
              <StatusCell label="Stress" value={view.bullpenState.stress_level} />
              <StatusCell label="Readiness" value={view.bullpenState.readiness_summary} />
            </div>
          </section>
        )}

        <GovernanceRows rows={view.governanceRows} />

        {compact ? (
          <PanelDisclosure
            title="V2 Evidence And Metadata"
            summary="Trust, freshness, inventory, neutral groups, team context, explanations, limitations, and refusal details remain available on demand."
          >
            {evidenceSections}
          </PanelDisclosure>
        ) : evidenceSections}
      </div>
    </section>
  )
}

function StatusCell({ label, value }) {
  return (
    <div className="min-w-0 rounded border border-dirt bg-chalk/20 p-3">
      <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{label}</div>
      <div className="v2-governed-panel__text mt-1 text-sm text-chalk200">{displayValue(value)}</div>
    </div>
  )
}
