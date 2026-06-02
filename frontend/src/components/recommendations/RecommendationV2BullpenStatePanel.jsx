import { LoadingPane, ErrorState } from '../UI'

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

function hasForbiddenDisplayText(value) {
  if (typeof value === 'string') {
    if (/non[-_ ]?ranking|input[-_ ]?order[-_ ]?non[-_ ]?ranking/i.test(value)) {
      return false
    }
    return FORBIDDEN_DISPLAY_TERMS.some((pattern) => pattern.test(value))
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

function getDiagnosticCount(view = {}) {
  return (
    asArray(view.missingFields).length
    + asArray(view.malformedFields).length
    + asArray(view.forbiddenFieldPaths).length
  )
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

  return {
    contractState,
    isAvailable,
    isFailClosed,
    isUnavailable,
    title: 'V2 Bullpen Intelligence',
    statusLabel: isFailClosed ? 'Fail-Closed' : isUnavailable ? 'Unavailable' : 'Available',
    statusTone,
    hiddenUnsafeLanguage: unsafeVisibleLanguage,
    diagnosticCount: getDiagnosticCount(state) + (unsafeVisibleLanguage ? 1 : 0),
    governanceRows: [
      {
        label: 'Ordering applied',
        value: displayValue(state.governance?.rankingApplied, 'missing'),
        safe: state.governance?.rankingApplied === false,
      },
      {
        label: 'Automated decision made',
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
      { label: 'Freshness', value: displayValue(freshness.freshness_state) },
      { label: 'Data Through', value: displayValue(freshness.data_through) },
      { label: 'Synced', value: displayValue(freshness.sync_timestamp) },
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
  return (
    <div className="min-w-0 rounded border border-dirt bg-field/35 p-4">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">{title}</div>
      <div className="v2-governed-panel__metadata-grid gap-2">
        {rows.map((row) => (
          <div key={row.label} className="min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{row.label}</div>
            <div className="v2-governed-panel__text mt-0.5 font-mono text-xs text-chalk200">{row.value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function GovernanceRows({ rows }) {
  return (
    <div className="min-w-0 rounded border border-dirt bg-field/35 p-4">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">Governance</div>
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
    </div>
  )
}

function MessageList({ title, messages, emptyText }) {
  return (
    <div className="min-w-0 rounded border border-dirt bg-field/35 p-4">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">{title}</div>
      {messages.length ? (
        <ul className="space-y-2">
          {messages.map((message) => (
            <li key={message} className="v2-governed-panel__text rounded border border-dirt bg-chalk/20 px-3 py-2 text-sm leading-relaxed text-chalk300">
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

function InventorySummary({ inventory }) {
  return (
    <div className="min-w-0 rounded border border-dirt bg-field/35 p-4">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">Inventory</div>
      {inventory.length ? (
        <div className="v2-governed-panel__inventory-grid gap-3">
          {inventory.map((item) => (
            <div key={`${item.inventory_type || item.label}-${item.count}`} className="min-w-0 rounded border border-dirt bg-chalk/20 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="v2-governed-panel__text text-sm font-semibold text-chalk200">{item.label || toTitle(item.inventory_type)}</div>
                  <div className="v2-governed-panel__text mt-1 font-mono text-[11px] text-chalk500">{displayValue(item.confidence, 'confidence unavailable')}</div>
                </div>
                <div className="shrink-0 rounded border border-dirt bg-field/50 px-2 py-1 font-mono text-xs text-chalk200">
                  {displayValue(item.count, '0')}
                </div>
              </div>
              {asArray(item.members).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {asArray(item.members).map((member) => (
                    <span key={`${member.pitcher_id || member.display_name}`} className="rounded border border-dirt bg-field/50 px-2 py-1 font-mono text-[11px] text-chalk300">
                      {member.display_name || member.pitcher_id}
                    </span>
                  ))}
                </div>
              )}
              {asArray(item.limitations).length > 0 && (
                <div className="v2-governed-panel__text mt-3 text-xs text-chalk500">
                  {asArray(item.limitations).map(messageFrom).filter(Boolean).join(' · ')}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="font-mono text-xs text-chalk500">No inventory summary available.</div>
      )}
    </div>
  )
}

function CandidateGroups({ groups }) {
  return (
    <div className="min-w-0 rounded border border-dirt bg-field/35 p-4">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">Neutral Candidate Groups</div>
      {groups.length ? (
        <div className="grid gap-3">
          {groups.map((group) => (
            <div key={group.group_id || group.label} className="min-w-0 rounded border border-dirt bg-chalk/20 p-3">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="v2-governed-panel__text text-sm font-semibold text-chalk200">{group.label || toTitle(group.group_id)}</div>
                  {group.description && (
                    <div className="v2-governed-panel__text mt-1 text-xs leading-relaxed text-chalk500">{group.description}</div>
                  )}
                </div>
                <div className="shrink-0 rounded border border-dirt bg-field/50 px-2 py-1 font-mono text-xs text-chalk300">
                  {displayValue(group.candidate_count, asArray(group.candidates).length)}
                </div>
              </div>
              <div className="v2-governed-panel__text mt-2 font-mono text-[11px] text-chalk600">
                Ordering policy: {orderingPolicyLabel(group.ordering)}
              </div>
              {asArray(group.candidates).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {asArray(group.candidates).map((candidate) => (
                    <span key={`${candidate.pitcher_id || candidate.display_name}`} className="rounded border border-dirt bg-field/50 px-2 py-1 font-mono text-[11px] text-chalk300">
                      {candidate.display_name || candidate.pitcher_id}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="font-mono text-xs text-chalk500">No neutral groups available from the current contract state.</div>
      )}
    </div>
  )
}

function TeamContext({ context }) {
  const availabilityRows = getDistributionRows(context.availability_distribution)
  const workloadRows = getDistributionRows(context.workload_distribution)
  const readiness = asArray(context.readiness_indicators)
  const stress = asArray(context.stress_indicators)

  return (
    <div className="min-w-0 rounded border border-dirt bg-field/35 p-4">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">Team Context</div>
      <div className="v2-governed-panel__team-grid gap-4">
        <Distribution title="Availability" rows={availabilityRows} />
        <Distribution title="Workload" rows={workloadRows} />
      </div>
      <div className="v2-governed-panel__team-grid mt-4 gap-4">
        <SimpleItems title="Readiness" items={readiness} />
        <SimpleItems title="Stress" items={stress} />
      </div>
    </div>
  )
}

function Distribution({ title, rows }) {
  return (
    <div className="min-w-0">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-chalk600">{title}</div>
      {rows.length ? (
        <div className="space-y-2">
          {rows.map((row) => (
            <div key={row.key} className="flex min-w-0 items-center justify-between gap-3 rounded border border-dirt bg-chalk/20 px-3 py-2">
              <span className="v2-governed-panel__text font-mono text-xs text-chalk400">{row.label}</span>
              <span className="shrink-0 font-mono text-xs font-semibold text-chalk200">{displayValue(row.count)}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="font-mono text-xs text-chalk500">Unavailable</div>
      )}
    </div>
  )
}

function SimpleItems({ title, items }) {
  return (
    <div className="min-w-0">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-chalk600">{title}</div>
      {items.length ? (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={messageFrom(item) || JSON.stringify(item)} className="v2-governed-panel__text rounded border border-dirt bg-chalk/20 px-3 py-2 text-xs text-chalk300">
              {messageFrom(item) || displayValue(item)}
            </div>
          ))}
        </div>
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
}) {
  if (loading) {
    return (
      <section className="v2-governed-panel card mb-8 w-full min-w-0 max-w-full overflow-hidden">
        <LoadingPane message="Loading V2 bullpen intelligence..." />
      </section>
    )
  }

  if (error) {
    return (
      <section className="v2-governed-panel card mb-8 w-full min-w-0 max-w-full overflow-hidden">
        <ErrorState message="V2 bullpen intelligence could not be loaded." onRetry={onRetry} />
      </section>
    )
  }

  const view = getRecommendationV2BullpenStateView(state)

  return (
    <section className="v2-governed-panel card mb-8 w-full min-w-0 max-w-full overflow-hidden animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
      <div className="border-b border-dirt bg-chalk/20 p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="font-mono text-xs uppercase tracking-widest text-chalk400">{view.title}</div>
            <h2 className="mt-1 font-display text-2xl tracking-wider text-chalk100">Bullpen State</h2>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk500">
              Governed bullpen visibility from the V2 contract. This surface summarizes context and evidence only.
            </p>
          </div>
          <div className={`shrink-0 self-start rounded border px-3 py-2 font-mono text-xs uppercase tracking-widest ${view.statusTone}`}>
            {view.statusLabel}
          </div>
        </div>
      </div>

      <div className="space-y-5 p-4 sm:p-5 lg:p-6">
        {view.isUnavailable && (
          <div className="min-w-0 rounded border border-red-500/35 bg-red-500/5 p-4">
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
          <div className="min-w-0 rounded border border-amber/40 bg-amber/5 p-4">
            <div className="font-mono text-xs uppercase tracking-widest text-amber">Fail-Closed</div>
            <p className="v2-governed-panel__text mt-2 text-sm leading-relaxed text-chalk400">
              V2 declined full bullpen-state output and preserved refusal metadata for review.
            </p>
          </div>
        )}

        {view.bullpenState && (
          <div className="min-w-0 rounded border border-dirt bg-field/35 p-4">
            <div className="mb-3 font-mono text-[10px] uppercase tracking-widest text-chalk600">State</div>
            <div className="v2-governed-panel__state-grid gap-3">
              <StatusCell label="Status" value={view.bullpenState.status} />
              <StatusCell label="Stress" value={view.bullpenState.stress_level} />
              <StatusCell label="Readiness" value={view.bullpenState.readiness_summary} />
            </div>
          </div>
        )}

        <GovernanceRows rows={view.governanceRows} />
        <MetadataGrid title="Trust" rows={view.trustRows} />
        <MetadataGrid title="Freshness" rows={view.freshnessRows} />

        {!view.isUnavailable && (
          <>
            <InventorySummary inventory={view.inventory} />
            <TeamContext context={view.teamContext} />
            <CandidateGroups groups={view.candidateGroups} />
          </>
        )}

        <div className="v2-governed-panel__message-grid gap-4">
          <MessageList title="Limitations" messages={view.limitationMessages} emptyText="No limitations reported." />
          <MessageList title="Explanations" messages={view.explanationMessages} emptyText="No explanations reported." />
          <MessageList title="Refusal" messages={view.refusalMessages} emptyText="No refusal metadata reported." />
        </div>
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
