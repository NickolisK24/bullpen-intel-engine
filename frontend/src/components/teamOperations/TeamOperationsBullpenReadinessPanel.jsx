import { useId, useState } from 'react'
import { ErrorState, LoadingPane } from '../UI'

const DEFAULT_VIEW = {
  contractState: 'unavailable',
  isContractSafe: false,
  isDegraded: false,
  isRefused: false,
  isFailClosed: false,
  isInternal: false,
  isInternalUncertified: false,
  governance: {},
  routeStatus: {},
  missingFields: [],
  malformedFields: [],
  forbiddenFieldPaths: [],
  forbiddenTextPaths: [],
  readinessStatus: null,
  readinessSummary: null,
  readiness: null,
  constraints: [],
  explanations: [],
  limitations: [],
  trustMetadata: null,
  freshness: null,
  refusal: null,
  failClosed: null,
}

const STATE_COPY = {
  available: {
    label: 'Available',
    tone: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-300',
  },
  degraded: {
    label: 'Degraded',
    tone: 'border-amber/40 bg-amber/10 text-amber',
  },
  refused: {
    label: 'Refused',
    tone: 'border-red-400/40 bg-red-400/10 text-red-300',
  },
  unavailable: {
    label: 'Unavailable',
    tone: 'border-chalk600 bg-chalk/40 text-chalk300',
  },
}

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

function displayValue(value) {
  if (value === false) return 'false'
  if (value === true) return 'true'
  if (value === null || value === undefined || value === '') return 'Not provided'
  if (Array.isArray(value)) {
    return value.length ? value.map(displayValue).join(', ') : 'None'
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function titleCase(value) {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, char => char.toUpperCase())
}

function countValue(value) {
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : displayValue(value)
}

function getStatusLabel(view) {
  return titleCase(view.readiness?.status || view.readinessStatus || view.contractState)
}

function getContractState(view) {
  if (!view?.isContractSafe) return 'unavailable'
  if (view.isRefused || view.isFailClosed) return 'refused'
  if (view.isDegraded) return 'degraded'
  return 'available'
}

function getSummary(view) {
  if (!view?.isContractSafe) {
    return 'Team-level readiness context is unavailable because required contract metadata is missing, malformed, or unsafe.'
  }
  return (
    view.readinessSummary
    || view.readiness?.summary
    || view.refusal?.message
    || 'Team-level readiness context is available.'
  )
}

function buildRows(source, entries) {
  const value = asObject(source)
  return entries.map(([label, keys]) => {
    const keyList = Array.isArray(keys) ? keys : [keys]
    const foundKey = keyList.find(key => Object.prototype.hasOwnProperty.call(value, key))
    return {
      label,
      value: foundKey ? value[foundKey] : null,
    }
  })
}

function MetricRow({ label, value }) {
  return (
    <div className="flex min-h-9 items-center justify-between gap-3 border-b border-dirt/70 py-2 last:border-b-0">
      <dt className="font-mono text-[11px] uppercase tracking-widest text-chalk600">{label}</dt>
      <dd className="text-right font-mono text-xs text-chalk200 break-words">{displayValue(value)}</dd>
    </div>
  )
}

function MetricList({ rows }) {
  return (
    <dl>
      {rows.map(row => (
        <MetricRow key={row.label} label={row.label} value={row.value} />
      ))}
    </dl>
  )
}

function CountGrid({ title, summary, rows }) {
  return (
    <div className="rounded border border-dirt bg-chalk/30 p-4">
      <h4 className="font-mono text-xs uppercase tracking-widest text-chalk400">{title}</h4>
      {summary && <p className="mt-2 text-xs leading-relaxed text-chalk600">{summary}</p>}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {rows.map(row => (
          <div key={row.label} className="rounded border border-dirt/80 bg-dugout/70 p-3">
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{row.label}</div>
            <div className="mt-1 font-mono text-sm font-semibold text-chalk200">{countValue(row.value)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function MessageList({ items, emptyLabel = 'No additional evidence provided.' }) {
  const rows = asArray(items)
  if (!rows.length) {
    return <p className="text-xs text-chalk600">{emptyLabel}</p>
  }

  return (
    <ul className="space-y-2">
      {rows.map((item, index) => {
        const value = asObject(item)
        const message = value.message || value.summary || displayValue(item)
        const subtext = [
          value.category,
          value.severity,
          value.applies_to,
          value.affected_area,
        ].filter(Boolean).map(titleCase).join(' / ')
        return (
          <li key={`${message}-${index}`} className="rounded border border-dirt bg-dugout/70 p-3">
            <p className="text-sm leading-relaxed text-chalk200">{message}</p>
            {subtext && <p className="mt-1 font-mono text-[11px] uppercase tracking-widest text-chalk600">{subtext}</p>}
            {Array.isArray(value.evidence) && value.evidence.length > 0 && (
              <ul className="mt-2 space-y-1">
                {value.evidence.map((evidence, evidenceIndex) => (
                  <li key={`${evidence}-${evidenceIndex}`} className="text-xs leading-relaxed text-chalk500">
                    {displayValue(evidence)}
                  </li>
                ))}
              </ul>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function ToggleSection({ title, summary, sectionKey, initialExpandedSections, children }) {
  const baseId = useId()
  const [expanded, setExpanded] = useState(initialExpandedSections.includes(sectionKey))
  const contentId = `${baseId}-${sectionKey}`

  return (
    <section className="rounded border border-dirt bg-chalk/20 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="font-mono text-xs uppercase tracking-widest text-chalk300">{title}</h3>
          {summary && <p className="mt-1 text-xs leading-relaxed text-chalk600">{summary}</p>}
        </div>
        <button
          type="button"
          className="inline-flex items-center justify-center rounded border border-dirt bg-dugout px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-chalk300 transition-colors hover:border-amber/50 hover:text-amber focus:outline-none focus:ring-2 focus:ring-amber/60 focus:ring-offset-2 focus:ring-offset-dugout"
          aria-expanded={expanded}
          aria-controls={contentId}
          onClick={() => setExpanded(current => !current)}
        >
          {expanded ? `Hide ${title}` : `View ${title}`}
        </button>
      </div>
      {expanded && (
        <div id={contentId} className="mt-4 space-y-4">
          {children}
        </div>
      )}
    </section>
  )
}

function RouteStatusBadge({ view }) {
  const routeStatus = asObject(view.routeStatus)
  const labels = [
    routeStatus.exposure === 'internal' ? 'Internal' : titleCase(routeStatus.exposure || 'internal'),
    routeStatus.productionStatus === 'non_production' ? 'Non-production' : titleCase(routeStatus.productionStatus || 'non production'),
    routeStatus.certificationStatus === 'uncertified' ? 'Uncertified' : titleCase(routeStatus.certificationStatus || 'uncertified'),
  ].filter(Boolean)

  return (
    <span className="inline-flex rounded border border-amber/35 bg-amber/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest text-amber">
      {labels.join(' / ') || 'Internal / Non-production / Uncertified'}
    </span>
  )
}

function ContractWarnings({ view }) {
  if (view.isContractSafe) return null

  const missingCount = asArray(view.missingFields).length
  const malformedCount = asArray(view.malformedFields).length
  const unsafeFieldCount = asArray(view.forbiddenFieldPaths).length
  const unsafeTextCount = asArray(view.forbiddenTextPaths).length

  return (
    <div className="rounded border border-amber/35 bg-amber/10 p-3" role="status" aria-live="polite">
      <p className="font-mono text-xs uppercase tracking-widest text-amber">Unavailable Contract State</p>
      <p className="mt-1 text-sm leading-relaxed text-chalk300">
        The panel withheld readiness details because the normalized payload did not satisfy the governed internal contract.
      </p>
      <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ['Missing fields', missingCount],
          ['Malformed fields', malformedCount],
          ['Unsafe fields', unsafeFieldCount],
          ['Unsafe text', unsafeTextCount],
        ].map(([label, value]) => (
          <div key={label} className="rounded border border-dirt bg-dugout/70 p-2">
            <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{label}</dt>
            <dd className="mt-1 font-mono text-sm text-chalk200">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function buildAvailabilityRows(view) {
  return buildRows(view.availabilityDistribution, [
    ['Available', 'available'],
    ['Monitor', 'monitor'],
    ['Limited', 'limited'],
    ['Avoid', 'avoid'],
    ['Unavailable', 'unavailable'],
    ['Unknown', 'unknown'],
    ['Total', 'total'],
  ])
}

function buildWorkloadRows(view) {
  const workload = asObject(view.workloadPressure)
  const counts = asObject(workload.counts)
  return [
    { label: 'State', value: workload.pressure_state || workload.pressure_level || null },
    { label: 'Low', value: workload.low_count ?? counts.low ?? null },
    { label: 'Moderate', value: workload.moderate_count ?? counts.moderate ?? null },
    { label: 'Elevated', value: workload.elevated_count ?? workload.high_count ?? counts.elevated ?? counts.high ?? null },
    { label: 'Unknown', value: workload.unknown_count ?? counts.unknown ?? null },
    { label: 'Latest Workload', value: workload.latest_workload_date || null },
  ]
}

function buildCoverageRows(view) {
  return buildRows(view.coverageInventory, [
    ['Active Pitchers', ['active_pitcher_count', 'active_pitchers']],
    ['Current Workload Data', ['current_workload_data_count', 'current_workload_present']],
    ['Missing Workload Data', ['missing_workload_data_count', 'missing_workload']],
    ['Availability Covered', ['availability_covered_count', 'availability_present']],
    ['Availability Missing', 'availability_missing_count'],
    ['Coverage State', 'coverage_state'],
  ])
}

function buildHandednessRows(view) {
  return buildRows(view.handednessCoverage, [
    ['Left Handed', ['left_handed_count', 'left_handed']],
    ['Right Handed', ['right_handed_count', 'right_handed']],
    ['Unknown', 'unknown_count'],
    ['Coverage State', 'coverage_state'],
    ['Limitations', 'limitations'],
  ])
}

function buildTrustRows(view) {
  return buildRows(view.trustMetadata, [
    ['Confidence', 'confidence'],
    ['Data State', 'data_state'],
    ['Source Evidence', 'source_evidence_state'],
    ['Governance State', 'governance_state'],
    ['Generated', 'generated_at'],
  ])
}

function buildFreshnessRows(view) {
  return buildRows(view.freshness, [
    ['Freshness', 'freshness_state'],
    ['Data Through', 'data_through'],
    ['Latest Workload', 'latest_workload_date'],
    ['Last Sync', 'last_successful_sync'],
    ['Sync Status', 'latest_sync_status'],
    ['Calculated At', 'latest_fatigue_calculated_at'],
    ['Stale Notice', 'stale_warning'],
    ['Missing Data Notice', 'missing_data_warning'],
  ])
}

function buildRefusalRows(view) {
  return buildRows(view.refusal, [
    ['Refused', 'refused'],
    ['Reason', 'reason'],
    ['Message', 'message'],
    ['Recovery Note', 'recovery_note'],
  ])
}

function buildFailClosedRows(view) {
  return buildRows(view.failClosed, [
    ['Fail Closed', 'failed_closed'],
    ['State', 'state'],
    ['Reason Codes', 'reason_codes'],
    ['Critical Failure', 'critical_failure'],
    ['Safe Partial Output', 'safe_partial_output_allowed'],
  ])
}

function buildGovernanceRows(view) {
  const governance = asObject(view.governance)
  return [
    { label: 'ranking_applied', value: governance.rankingApplied },
    { label: 'selection_made', value: governance.selectionMade },
    { label: 'trust ranking_applied', value: governance.trustRankingApplied },
    { label: 'trust selection_made', value: governance.trustSelectionMade },
  ]
}

function getTeamName(view) {
  const team = asObject(view.team)
  return team.team_name || team.team_abbreviation || team.team_id || 'All bullpen context'
}

export function getTeamOperationsBullpenReadinessView(state = null) {
  const view = { ...DEFAULT_VIEW, ...(state || {}) }
  const contractState = getContractState(view)

  return {
    ...view,
    contractState,
    statusCopy: STATE_COPY[contractState] || STATE_COPY.unavailable,
    statusLabel: getStatusLabel(view),
    summary: getSummary(view),
    teamLabel: getTeamName(view),
    workloadRows: buildWorkloadRows(view),
    availabilityRows: buildAvailabilityRows(view),
    coverageRows: buildCoverageRows(view),
    handednessRows: buildHandednessRows(view),
    trustRows: buildTrustRows(view),
    freshnessRows: buildFreshnessRows(view),
    refusalRows: buildRefusalRows(view),
    failClosedRows: buildFailClosedRows(view),
    governanceRows: buildGovernanceRows(view),
  }
}

export default function TeamOperationsBullpenReadinessPanel({
  state,
  loading = false,
  error = null,
  onRetry,
  initialExpandedSections = [],
}) {
  const view = getTeamOperationsBullpenReadinessView(state)

  return (
    <section
      className="card mb-8 animate-fade-up opacity-0 delay-3"
      style={{ animationFillMode: 'forwards' }}
      aria-labelledby="team-operations-bullpen-readiness-title"
    >
      <div className="card-header gap-3">
        <div>
          <div className="font-mono text-xs uppercase tracking-widest text-chalk400">
            Team Operations Bullpen Readiness
          </div>
          <h2 id="team-operations-bullpen-readiness-title" className="mt-1 font-display text-2xl tracking-wider text-chalk100">
            Bullpen Readiness Context
          </h2>
        </div>
        <RouteStatusBadge view={view} />
      </div>

      {loading ? (
        <LoadingPane message="Loading team operations readiness..." />
      ) : error ? (
        <div className="p-5">
          <ErrorState message={error} onRetry={onRetry} />
        </div>
      ) : (
        <div className="space-y-5 p-5">
          <div className="rounded border border-dirt bg-dugout/70 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="font-mono text-[11px] uppercase tracking-widest text-chalk600">
                  {view.teamLabel}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span className={`inline-flex rounded border px-2.5 py-1 font-mono text-[11px] uppercase tracking-widest ${view.statusCopy.tone}`}>
                    {view.statusCopy.label}
                  </span>
                  <span className="font-mono text-xs text-chalk300">{view.statusLabel}</span>
                </div>
                <p className="mt-3 max-w-3xl text-sm leading-relaxed text-chalk300">
                  {view.summary}
                </p>
              </div>
              <div className="rounded border border-dirt bg-chalk/30 p-3 text-left sm:min-w-56">
                <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">Governed Output</div>
                <p className="mt-1 text-xs leading-relaxed text-chalk400">
                  Team-level context only. The user remains responsible for bullpen decisions.
                </p>
              </div>
            </div>
          </div>

          <ContractWarnings view={view} />

          {view.isContractSafe && (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <CountGrid
                title="Workload Pressure"
                summary={asObject(view.workloadPressure).summary}
                rows={view.workloadRows}
              />
              <CountGrid
                title="Availability Distribution"
                rows={view.availabilityRows}
              />
              <CountGrid
                title="Coverage Inventory"
                rows={view.coverageRows}
              />
              <CountGrid
                title="Handedness Coverage"
                rows={view.handednessRows}
              />
            </div>
          )}

          <ToggleSection
            title="Context Details"
            summary="Constraint and coverage details are available on demand."
            sectionKey="context-details"
            initialExpandedSections={initialExpandedSections}
          >
            <div>
              <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Constraints</h4>
              <MessageList items={view.isContractSafe ? view.constraints : []} emptyLabel="No constraint details provided." />
            </div>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="rounded border border-dirt bg-dugout/70 p-3">
                <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Workload Pressure</h4>
                <MetricList rows={view.workloadRows} />
              </div>
              <div className="rounded border border-dirt bg-dugout/70 p-3">
                <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Availability Distribution</h4>
                <MetricList rows={view.availabilityRows} />
              </div>
            </div>
          </ToggleSection>

          <ToggleSection
            title="Evidence"
            summary="Explanations and limitations are visible without changing the team-level scope."
            sectionKey="evidence"
            initialExpandedSections={initialExpandedSections}
          >
            <div>
              <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Explanations</h4>
              <MessageList items={view.isContractSafe ? view.explanations : []} emptyLabel="No explanation details provided." />
            </div>
            <div>
              <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Limitations</h4>
              <MessageList items={view.isContractSafe ? view.limitations : []} emptyLabel="No limitation details provided." />
            </div>
          </ToggleSection>

          <ToggleSection
            title="Metadata"
            summary="Trust, freshness, refusal, fail-closed, route, and governance metadata are preserved."
            sectionKey="metadata"
            initialExpandedSections={initialExpandedSections}
          >
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="rounded border border-dirt bg-dugout/70 p-3">
                <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Trust Metadata</h4>
                <MetricList rows={view.trustRows} />
              </div>
              <div className="rounded border border-dirt bg-dugout/70 p-3">
                <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Freshness Metadata</h4>
                <MetricList rows={view.freshnessRows} />
              </div>
              <div className="rounded border border-dirt bg-dugout/70 p-3">
                <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Refusal Metadata</h4>
                <MetricList rows={view.refusalRows} />
              </div>
              <div className="rounded border border-dirt bg-dugout/70 p-3">
                <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Fail-Closed Metadata</h4>
                <MetricList rows={view.failClosedRows} />
              </div>
              <div className="rounded border border-dirt bg-dugout/70 p-3 lg:col-span-2">
                <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Governance Metadata</h4>
                <MetricList rows={view.governanceRows} />
              </div>
            </div>
          </ToggleSection>
        </div>
      )}
    </section>
  )
}
