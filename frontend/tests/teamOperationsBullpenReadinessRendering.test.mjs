import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { readFile } from 'node:fs/promises'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const {
  default: TeamOperationsBullpenReadinessPanel,
  getTeamOperationsBullpenReadinessView,
} = await server.ssrLoadModule('/src/components/teamOperations/TeamOperationsBullpenReadinessPanel.jsx')
const { default: Dashboard } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')
const dataTrustSource = await readFile(
  new URL('../src/components/trust/DataTrust.jsx', import.meta.url),
  'utf8',
)

const clone = value => JSON.parse(JSON.stringify(value))
const escapeRegExp = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const visibleText = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const sanitizedGovernanceText = html => visibleText(html)
  .replace(/Context only - no team ranking or pitcher selection\./g, '')
  .replace(/Team ranking Not applied Pitcher selection Not made Trust ranking Not applied Trust selection Not made/g, '')
  .replace(/ranking_applied/g, '')
  .replace(/selection_made/g, '')

const baseState = {
  endpoint: '/team-operations/bullpen-readiness',
  contractState: 'available',
  sourceContractState: 'available',
  isContractSafe: true,
  isDegraded: false,
  isRefused: false,
  isFailClosed: false,
  isInternal: true,
  isInternalUncertified: true,
  governanceSafe: true,
  governance: {
    rankingApplied: false,
    selectionMade: false,
    trustRankingApplied: false,
    trustSelectionMade: false,
    rankingAppliedIsFalse: true,
    selectionMadeIsFalse: true,
  },
  routeStatus: {
    route: '/api/team-operations/bullpen-readiness',
    surface: 'team_operations_bullpen_readiness_internal_route',
    exposure: 'internal',
    productionStatus: 'non_production',
    certificationStatus: 'uncertified',
    publicCertified: false,
    frontendExposure: false,
  },
  missingFields: [],
  malformedFields: [],
  forbiddenFieldPaths: [],
  forbiddenTextPaths: [],
  capability: 'team_operations_bullpen_readiness',
  scope: 'team_bullpen_readiness',
  contract: 'team_operations_bullpen_readiness_api_contract',
  contractVersion: 'v3_phase_4',
  readinessStatus: 'operationally_stable',
  readinessSummary: 'Team-level bullpen readiness looks steady from current public workload evidence.',
  readiness: {
    status: 'Operationally Stable',
    status_code: 'operationally_stable',
    summary: 'Team-level bullpen readiness looks steady from current public workload evidence.',
    basis: ['availability_distribution', 'workload_pressure', 'freshness', 'trust_metadata'],
  },
  team: {
    team_id: 136,
    team_abbreviation: 'SEA',
    team_name: 'Seattle Mariners',
  },
  generatedAt: '2026-06-03T12:00:00Z',
  constraints: [
    {
      constraint_id: 'coverage_current',
      category: 'coverage',
      severity: 'info',
      message: 'Coverage inventory is represented.',
      affected_area: 'coverage',
      evidence: ['Current availability classifications are present.'],
    },
  ],
  workloadPressure: {
    pressure_level: 'low',
    summary: 'Workload pressure is low at the team level.',
    counts: {
      low: 5,
      moderate: 1,
      high: 0,
      unknown: 0,
    },
    basis: ['availability_classification', 'recent_workload'],
  },
  availabilityDistribution: {
    available: 5,
    monitor: 1,
    limited: 0,
    avoid: 0,
    unavailable: 0,
    unknown: 0,
    total: 6,
  },
  coverageInventory: {
    total_pitchers: 6,
    active_pitchers: 6,
    availability_present: 6,
    current_workload_present: 6,
    missing_workload: 0,
  },
  handednessCoverage: {
    right_handed: 4,
    left_handed: 2,
    unknown_count: 0,
    coverage_state: 'represented',
  },
  explanations: [
    {
      explanation_id: 'team_context_assembled',
      level: 'team',
      message: 'Readiness context is assembled from current bullpen evidence.',
      applies_to: 'readiness',
    },
  ],
  limitations: [
    {
      limitation_id: 'no_manager_intent',
      message: 'Manager intent is not represented.',
      applies_to: 'readiness',
    },
  ],
  trustMetadata: {
    confidence: 'medium',
    confidence_reasons: ['current_availability_evidence'],
    data_state: 'complete',
    source_evidence_state: 'represented',
    governance_state: 'internal_uncertified',
    generated_at: '2026-06-03T12:00:00Z',
    limitations: [],
    explanations: [],
    refusal_reasons: [],
    trust_validation_errors: [],
    ranking_applied: false,
    selection_made: false,
  },
  freshness: {
    freshness_state: 'current',
    data_through: '2026-06-03',
    latest_workload_date: '2026-06-03',
    last_successful_sync: '2026-06-03T11:45:00Z',
    latest_sync_status: 'success',
    latest_fatigue_calculated_at: '2026-06-03T11:50:00Z',
    generated_at: '2026-06-03T12:00:00Z',
    stale_warning: null,
    missing_data_warning: null,
    limitations: [],
  },
  refusal: {
    refused: false,
    refusal_id: null,
    reason: null,
    message: null,
    applies_to: 'readiness',
    recovery_note: null,
  },
  failClosed: {
    failed_closed: false,
    state: 'not_failed_closed',
    reason_codes: [],
    critical_failure: false,
    safe_partial_output_allowed: false,
  },
}

function renderPanel(state, props = {}) {
  return renderToStaticMarkup(
    React.createElement(TeamOperationsBullpenReadinessPanel, { state, ...props }),
  )
}

test('renders successful Team Operations readiness payloads', () => {
  const html = renderPanel(baseState)

  assert.ok(htmlIncludes(html, 'Team Operations Bullpen Readiness'))
  assert.ok(htmlIncludes(html, 'Bullpen Readiness Context'))
  assert.ok(htmlIncludes(html, 'Internal / Limited Exposure'))
  assert.ok(htmlIncludes(html, 'Available'))
  assert.ok(htmlIncludes(html, 'Operationally Stable'))
  assert.ok(htmlIncludes(html, 'Team-level bullpen readiness looks steady from current public workload evidence.'))
  assert.ok(htmlIncludes(html, 'Workload Pressure'))
  assert.ok(htmlIncludes(html, 'Availability Distribution'))
  assert.ok(htmlIncludes(html, 'Coverage Inventory'))
  assert.ok(htmlIncludes(html, 'Handedness Coverage'))
})

test('renders degraded Team Operations readiness payloads', () => {
  const state = clone(baseState)
  state.contractState = 'degraded'
  state.sourceContractState = 'degraded'
  state.isDegraded = true
  state.readinessStatus = 'data_limited'
  state.readiness.status = 'Limited Visibility'
  state.readiness.summary = 'Team-level bullpen visibility is limited.'
  state.readinessSummary = state.readiness.summary
  state.trustMetadata.confidence = 'low'
  state.trustMetadata.data_state = 'partial'
  state.freshness.freshness_state = 'stale'
  state.freshness.stale_warning = 'Current workload evidence is stale.'
  state.failClosed.state = 'degraded_safe_output'
  state.failClosed.safe_partial_output_allowed = true

  const html = renderPanel(state, { initialExpandedSections: ['metadata'] })

  assert.ok(htmlIncludes(html, 'Degraded'))
  assert.ok(htmlIncludes(html, 'Limited Visibility'))
  assert.ok(htmlIncludes(html, 'Team-level bullpen visibility is limited.'))
  assert.ok(htmlIncludes(html, 'low'))
  assert.ok(htmlIncludes(html, 'partial'))
  assert.ok(htmlIncludes(html, 'Current workload evidence is stale.'))
  assert.ok(htmlIncludes(html, 'degraded_safe_output'))
})

test('renders refused fail-closed Team Operations readiness payloads', () => {
  const state = clone(baseState)
  state.contractState = 'refused'
  state.sourceContractState = 'refused'
  state.isRefused = true
  state.isFailClosed = true
  state.readinessStatus = 'refused'
  state.readiness = {
    status: 'Refused',
    status_code: 'refused',
    summary: 'Team-level bullpen readiness is refused because required evidence is unavailable.',
    basis: ['trust_metadata', 'freshness', 'fail_closed'],
  }
  state.readinessSummary = state.readiness.summary
  state.refusal = {
    refused: true,
    refusal_id: 'missing_required_evidence',
    reason: 'missing_required_evidence',
    message: 'Required readiness evidence is unavailable.',
    applies_to: 'readiness',
    recovery_note: 'Refresh source evidence before retrying.',
  }
  state.failClosed = {
    failed_closed: true,
    state: 'refused',
    reason_codes: ['missing_required_evidence'],
    critical_failure: true,
    safe_partial_output_allowed: false,
  }

  const html = renderPanel(state, { initialExpandedSections: ['metadata'] })

  assert.ok(htmlIncludes(html, 'Refused'))
  assert.ok(htmlIncludes(html, 'Team-level bullpen readiness is refused because required evidence is unavailable.'))
  assert.ok(htmlIncludes(html, 'Required readiness evidence is unavailable.'))
  assert.ok(htmlIncludes(html, 'Refresh source evidence before retrying.'))
  assert.ok(htmlIncludes(html, 'Fail Closed'))
  assert.ok(htmlIncludes(html, 'Critical Failure'))
})

test('keeps internal limited-exposure status visible', () => {
  const html = renderPanel(baseState)

  assert.ok(htmlIncludes(html, 'Internal / Limited Exposure'))
  assert.ok(htmlIncludes(html, 'Governed Output'))
  assert.ok(htmlIncludes(html, 'Team-level context only.'))
})

test('renders compact Team Operations summary with evidence collapsed and governance visible', () => {
  const html = renderPanel(baseState, { compact: true })

  assert.ok(htmlIncludes(html, 'Team Operations Bullpen Readiness'))
  assert.ok(htmlIncludes(html, 'Internal / Limited Exposure'))
  assert.ok(htmlIncludes(html, 'Context only - no team ranking or pitcher selection.'))
  assert.ok(htmlIncludes(html, 'View Context Details'))
  assert.ok(htmlIncludes(html, 'View Evidence'))
  assert.ok(htmlIncludes(html, 'View Metadata'))
  assert.equal(htmlIncludes(html, 'Coverage inventory is represented.'), false)
  assert.equal(htmlIncludes(html, 'Readiness context is assembled from current bullpen evidence.'), false)
})

test('renders governance flags and metadata', () => {
  const html = renderPanel(baseState, { initialExpandedSections: ['metadata'] })

  assert.ok(htmlIncludes(html, 'Governance Metadata'))
  assert.ok(htmlIncludes(html, 'Team ranking'))
  assert.ok(htmlIncludes(html, 'Pitcher selection'))
  assert.ok(htmlIncludes(html, 'Not applied'))
  assert.ok(htmlIncludes(html, 'Not made'))
  assert.ok(htmlIncludes(html, 'Trust Metadata'))
  assert.ok(htmlIncludes(html, 'Freshness Metadata'))
})

test('renders trust metadata when expanded', () => {
  const html = renderPanel(baseState, { initialExpandedSections: ['metadata'] })

  assert.ok(htmlIncludes(html, 'Workload Read'))
  assert.ok(htmlIncludes(html, 'medium'))
  assert.ok(htmlIncludes(html, 'Data State'))
  assert.ok(htmlIncludes(html, 'complete'))
  assert.ok(htmlIncludes(html, 'Source Evidence'))
  assert.ok(htmlIncludes(html, 'represented'))
})

test('humanizes readiness evidence keys while preserving technical keys', () => {
  const state = clone(baseState)
  state.constraints[0].evidence = [
    'coverage_inventory',
    'trust_metadata_limited',
    {
      affected_area: 'trust_metadata',
      category: 'trust',
      status_code: 'trust_metadata_limited',
    },
  ]

  const html = renderPanel(state, {
    compact: true,
    initialExpandedSections: ['context-details', 'metadata'],
  })

  assert.ok(htmlIncludes(html, 'Coverage Inventory'))
  assert.ok(htmlIncludes(html, 'Source key: coverage_inventory'))
  assert.ok(htmlIncludes(html, 'Trust Metadata Limited'))
  assert.ok(htmlIncludes(html, 'Source key: trust_metadata_limited'))
  assert.ok(htmlIncludes(html, 'Affected Area: Trust Metadata'))
  assert.ok(htmlIncludes(html, 'Technical details'))
  assert.ok(htmlIncludes(html, 'Context only - no team ranking or pitcher selection.'))
})

test('renders freshness metadata when expanded', () => {
  const html = renderPanel(baseState, { initialExpandedSections: ['metadata'] })

  assert.ok(htmlIncludes(html, 'Freshness'))
  assert.ok(htmlIncludes(html, 'current'))
  assert.ok(htmlIncludes(html, 'Data Through'))
  assert.ok(htmlIncludes(html, '2026-06-03'))
  assert.ok(htmlIncludes(html, 'Last Sync'))
  assert.ok(htmlIncludes(html, '2026-06-03T11:45:00Z'))
})

test('supports keyboard-operable expand and collapse controls', () => {
  const collapsedHtml = renderPanel(baseState)
  const expandedHtml = renderPanel(baseState, {
    initialExpandedSections: ['context-details', 'evidence', 'metadata'],
  })

  assert.ok(htmlIncludes(collapsedHtml, 'View Context Details'))
  assert.ok(htmlIncludes(collapsedHtml, 'aria-expanded="false"'))
  assert.ok(!htmlIncludes(collapsedHtml, 'Coverage inventory is represented.'))
  assert.ok(htmlIncludes(expandedHtml, 'Hide Context Details'))
  assert.ok(htmlIncludes(expandedHtml, 'Hide Evidence'))
  assert.ok(htmlIncludes(expandedHtml, 'Hide Metadata'))
  assert.ok(htmlIncludes(expandedHtml, 'aria-expanded="true"'))
  assert.ok(htmlIncludes(expandedHtml, 'Coverage inventory is represented.'))
  assert.ok(htmlIncludes(expandedHtml, 'Readiness context is assembled from current bullpen evidence.'))
})

test('does not render best preferred or recommended language', () => {
  const html = renderPanel(baseState, {
    initialExpandedSections: ['context-details', 'evidence', 'metadata'],
  })
  const text = visibleText(html)

  assert.equal(/\bbest\b|\bpreferred\b|\brecommended\b/i.test(text), false)
})

test('does not render unsafe guidance language outside required governance flags', () => {
  const html = renderPanel(baseState, {
    initialExpandedSections: ['context-details', 'evidence', 'metadata'],
  })
  const text = sanitizedGovernanceText(html)

  assert.equal(/\bmatchup advice\b|\bpitcher-level advice\b|\bpredict\b|\bprediction\b|\bforecast\b/i.test(text), false)
  assert.equal(/\brank\b|\branking\b|\bselect\b|\bselection\b/i.test(text), false)
})

test('Data & Trust page wires the Team Operations readiness panel and V2 state', () => {
  // The operational readiness / governance panel relocated from the Dashboard
  // to the Data & Trust page during the dashboard realignment. The Dashboard
  // still loads as a component; the panel wiring now lives on Data & Trust.
  assert.equal(typeof Dashboard, 'function')
  assert.ok(dataTrustSource.includes('OperationalReadinessSection'))
  assert.ok(dataTrustSource.includes('getTeamOperationsBullpenReadiness'))
  assert.ok(dataTrustSource.includes('getRecommendationV2BullpenState'))
})

test('derives unavailable view state for unsafe normalized payloads', () => {
  const state = clone(baseState)
  state.isContractSafe = false
  state.missingFields = ['trust_metadata']
  state.malformedFields = ['ranking_applied']

  const view = getTeamOperationsBullpenReadinessView(state)
  const html = renderPanel(state)

  assert.equal(view.contractState, 'unavailable')
  assert.ok(htmlIncludes(html, 'Unavailable'))
  assert.ok(htmlIncludes(html, 'Unavailable Contract State'))
  assert.ok(htmlIncludes(html, 'Missing fields'))
  assert.ok(htmlIncludes(html, 'Malformed fields'))
})
