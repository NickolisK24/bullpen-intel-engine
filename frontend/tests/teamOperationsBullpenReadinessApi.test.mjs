import assert from 'node:assert/strict'
import test, { after } from 'node:test'
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
  TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE,
  getTeamOperationsBullpenReadiness,
  normalizeTeamOperationsBullpenReadinessResponse,
} = await server.ssrLoadModule('/src/utils/api.js')

const clone = value => JSON.parse(JSON.stringify(value))

const baseReadinessResponse = {
  capability: 'team_operations_bullpen_readiness',
  scope: 'team_bullpen_readiness',
  contract: 'team_operations_bullpen_readiness_api_contract',
  contract_version: 'v3_phase_4',
  contract_state: 'available',
  ranking_applied: false,
  selection_made: false,
  readiness: {
    status: 'Operationally Stable',
    status_code: 'operationally_stable',
    summary: 'Team-level bullpen readiness is operationally stable.',
    basis: [
      'availability_distribution',
      'workload_pressure',
      'freshness',
      'trust_metadata',
    ],
  },
  team: {
    team_id: 136,
    team_abbreviation: 'SEA',
    team_name: 'Seattle Mariners',
  },
  generated_at: '2026-06-03T12:00:00Z',
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
  workload_pressure: {
    pressure_level: 'low',
    summary: 'Workload pressure is low.',
    counts: {
      low: 5,
      moderate: 1,
      high: 0,
      unknown: 0,
    },
    basis: ['availability_classification', 'recent_workload'],
  },
  availability_distribution: {
    available: 5,
    monitor: 1,
    limited: 0,
    avoid: 0,
    unavailable: 0,
    unknown: 0,
  },
  coverage_inventory: {
    total_pitchers: 6,
    active_pitchers: 6,
    availability_present: 6,
    current_workload_present: 6,
    missing_workload: 0,
  },
  handedness_coverage: {
    right_handed: 4,
    left_handed: 2,
    unknown: 0,
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
  trust_metadata: {
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
  fail_closed: {
    failed_closed: false,
    state: 'not_failed_closed',
    reason_codes: [],
    critical_failure: false,
    safe_partial_output_allowed: false,
  },
  route_metadata: {
    route: '/api/team-operations/bullpen-readiness',
    surface: 'team_operations_bullpen_readiness_internal_route',
    exposure: 'internal',
    production_status: 'non_production',
    certification_status: 'uncertified',
    public_certified: false,
    frontend_exposure: false,
  },
}

test('normalizes successful Team Operations readiness payloads', () => {
  const view = normalizeTeamOperationsBullpenReadinessResponse(clone(baseReadinessResponse))

  assert.equal(view.endpoint, TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE)
  assert.equal(view.contractState, 'available')
  assert.equal(view.isContractSafe, true)
  assert.equal(view.isDegraded, false)
  assert.equal(view.isRefused, false)
  assert.equal(view.isFailClosed, false)
  assert.equal(view.isInternalUncertified, true)
  assert.equal(view.governance.rankingApplied, false)
  assert.equal(view.governance.selectionMade, false)
  assert.equal(view.governance.trustRankingApplied, false)
  assert.equal(view.governance.trustSelectionMade, false)
  assert.equal(view.governance.failClosedRankingApplied, undefined)
  assert.equal(view.governance.failClosedSelectionMade, undefined)
  assert.equal(view.readinessStatus, 'operationally_stable')
  assert.equal(view.readinessSummary, baseReadinessResponse.readiness.summary)
  assert.deepEqual(view.readiness, baseReadinessResponse.readiness)
  assert.deepEqual(view.availabilityDistribution, baseReadinessResponse.availability_distribution)
  assert.deepEqual(view.coverageInventory, baseReadinessResponse.coverage_inventory)
  assert.deepEqual(view.handednessCoverage, baseReadinessResponse.handedness_coverage)
  assert.deepEqual(view.trustMetadata, baseReadinessResponse.trust_metadata)
  assert.deepEqual(view.freshness, baseReadinessResponse.freshness)
  assert.deepEqual(view.refusal, baseReadinessResponse.refusal)
  assert.deepEqual(view.failClosed, baseReadinessResponse.fail_closed)
  assert.equal(view.routeStatus.exposure, 'internal')
  assert.equal(view.routeStatus.productionStatus, 'non_production')
  assert.equal(view.routeStatus.certificationStatus, 'uncertified')
  assert.equal(view.routeStatus.publicCertified, false)
  assert.equal(view.routeStatus.frontendExposure, false)
  assert.deepEqual(view.missingFields, [])
  assert.deepEqual(view.malformedFields, [])
  assert.deepEqual(view.forbiddenFieldPaths, [])
  assert.deepEqual(view.forbiddenTextPaths, [])
  assert.equal(Object.hasOwn(view, 'rawResponse'), false)
})

test('normalizes degraded readiness payloads without treating them as production certified', () => {
  const response = clone(baseReadinessResponse)
  response.contract_state = 'degraded'
  response.readiness.status = 'Data Limited'
  response.readiness.status_code = 'data_limited'
  response.readiness.summary = 'Team-level bullpen readiness is data limited.'
  response.trust_metadata.confidence = 'low'
  response.trust_metadata.data_state = 'partial'
  response.freshness.freshness_state = 'stale'
  response.freshness.stale_warning = 'Current workload evidence is stale.'
  response.fail_closed.state = 'degraded_safe_output'
  response.fail_closed.safe_partial_output_allowed = true

  const view = normalizeTeamOperationsBullpenReadinessResponse(response)

  assert.equal(view.contractState, 'degraded')
  assert.equal(view.isContractSafe, true)
  assert.equal(view.isDegraded, true)
  assert.equal(view.isRefused, false)
  assert.equal(view.isFailClosed, false)
  assert.equal(view.readinessStatus, 'data_limited')
  assert.equal(view.trustMetadata.confidence, 'low')
  assert.equal(view.freshness.freshness_state, 'stale')
  assert.equal(view.routeStatus.productionStatus, 'non_production')
})

test('normalizes refused fail-closed readiness payloads', () => {
  const response = clone(baseReadinessResponse)
  response.contract_state = 'refused'
  response.readiness = {
    status: 'Refused',
    status_code: 'refused',
    summary: 'Team-level bullpen readiness is refused because required evidence is unavailable.',
    basis: ['trust_metadata', 'freshness', 'fail_closed'],
  }
  response.refusal = {
    refused: true,
    refusal_id: 'missing_required_evidence',
    reason: 'missing_required_evidence',
    message: 'Required readiness evidence is unavailable.',
    applies_to: 'readiness',
    recovery_note: 'Refresh source evidence before retrying.',
  }
  response.fail_closed = {
    failed_closed: true,
    state: 'refused',
    reason_codes: ['missing_required_evidence'],
    critical_failure: true,
    safe_partial_output_allowed: false,
  }

  const view = normalizeTeamOperationsBullpenReadinessResponse(response)

  assert.equal(view.contractState, 'refused')
  assert.equal(view.isContractSafe, true)
  assert.equal(view.isRefused, true)
  assert.equal(view.isFailClosed, true)
  assert.equal(view.refusal.refused, true)
  assert.equal(view.failClosed.failed_closed, true)
  assert.equal(view.governance.rankingApplied, false)
  assert.equal(view.governance.selectionMade, false)
})

test('marks readiness payloads without trust metadata unavailable', () => {
  const response = clone(baseReadinessResponse)
  delete response.trust_metadata

  const view = normalizeTeamOperationsBullpenReadinessResponse(response)

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isContractSafe, false)
  assert.equal(view.governanceSafe, false)
  assert.ok(view.missingFields.includes('trust_metadata'))
  assert.ok(view.missingFields.includes('trust_metadata.ranking_applied'))
  assert.equal(view.trustMetadata, null)
})

test('marks readiness payloads without freshness metadata unavailable', () => {
  const response = clone(baseReadinessResponse)
  delete response.freshness

  const view = normalizeTeamOperationsBullpenReadinessResponse(response)

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isContractSafe, false)
  assert.ok(view.missingFields.includes('freshness'))
  assert.ok(view.missingFields.includes('freshness.freshness_state'))
  assert.equal(view.freshness, null)
})

test('marks readiness payloads without governance metadata unavailable', () => {
  const response = clone(baseReadinessResponse)
  delete response.ranking_applied
  delete response.trust_metadata.selection_made

  const view = normalizeTeamOperationsBullpenReadinessResponse(response)

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isContractSafe, false)
  assert.equal(view.governance.rankingApplied, undefined)
  assert.equal(view.governance.trustSelectionMade, undefined)
  assert.ok(view.missingFields.includes('ranking_applied'))
  assert.ok(view.missingFields.includes('trust_metadata.selection_made'))
})

test('marks readiness payloads with malformed governance metadata unavailable', () => {
  const response = clone(baseReadinessResponse)
  response.ranking_applied = 'false'
  response.trust_metadata.selection_made = 'false'

  const view = normalizeTeamOperationsBullpenReadinessResponse(response)

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isContractSafe, false)
  assert.equal(view.governanceSafe, false)
  assert.ok(view.malformedFields.includes('ranking_applied'))
  assert.ok(view.malformedFields.includes('trust_metadata.selection_made'))
})

test('marks unknown readiness statuses unavailable', () => {
  const response = clone(baseReadinessResponse)
  response.readiness.status_code = 'pitcher_priority_mode'

  const view = normalizeTeamOperationsBullpenReadinessResponse(response)

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isContractSafe, false)
  assert.equal(view.unknownReadinessStatus, 'pitcher_priority_mode')
})

test('preserves internal non-production uncertified route metadata', () => {
  const view = normalizeTeamOperationsBullpenReadinessResponse(clone(baseReadinessResponse))

  assert.equal(view.isInternal, true)
  assert.equal(view.isInternalUncertified, true)
  assert.deepEqual(view.routeStatus, {
    route: '/api/team-operations/bullpen-readiness',
    surface: 'team_operations_bullpen_readiness_internal_route',
    exposure: 'internal',
    productionStatus: 'non_production',
    certificationStatus: 'uncertified',
    publicCertified: false,
    frontendExposure: false,
  })
})

test('does not introduce best preferred or recommended language', () => {
  const view = normalizeTeamOperationsBullpenReadinessResponse(clone(baseReadinessResponse))

  assert.equal(/\bbest\b|\bpreferred\b|\brecommended\b/i.test(JSON.stringify(view)), false)
  assert.equal(view.forbiddenTextPaths.length, 0)
})

test('fetches the internal Team Operations readiness endpoint and normalizes it', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  globalThis.fetch = async (url, options) => {
    assert.equal(url, `/api${TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE}?team_id=SEA`)
    assert.equal(options.method, undefined)
    assert.equal(options.headers['Content-Type'], 'application/json')

    return {
      ok: true,
      json: async () => clone(baseReadinessResponse),
    }
  }

  const view = await getTeamOperationsBullpenReadiness({
    team_id: 'SEA',
    empty: '',
    skip: null,
  })

  assert.equal(view.contractState, 'available')
  assert.equal(view.governance.rankingApplied, false)
  assert.equal(view.governance.selectionMade, false)
  assert.equal(view.routeStatus.exposure, 'internal')
})
