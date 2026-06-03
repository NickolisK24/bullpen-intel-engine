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
  RECOMMENDATION_V2_BULLPEN_STATE_ROUTE,
  getRecommendationV2BullpenState,
  normalizeRecommendationV2BullpenStateResponse,
} = await server.ssrLoadModule('/src/utils/api.js')

const baseV2Response = {
  scope: 'bullpen_state',
  ranking_applied: false,
  selection_made: false,
  confidence: 'medium',
  data_state: 'complete',
  generated_at: '2026-06-02T12:00:00Z',
  freshness: {
    sync_timestamp: '2026-06-02T11:55:00Z',
    data_through: '2026-06-02',
    freshness_state: 'current',
    source_freshness_status: 'fresh',
    aggregate_v2_freshness_status: 'fresh',
    overall_sync_status: 'success',
    overall_sync_current: true,
    stale_warning: null,
    missing_data_warning: null,
  },
  status_metadata: {
    overall_sync_status: 'success',
    overall_sync_current: true,
    sync_timestamp: '2026-06-02T11:55:00Z',
    sync_data_through: '2026-06-02',
    source_freshness_status: 'fresh',
    aggregate_v2_freshness_status: 'fresh',
    fail_closed_state: 'passed',
    fail_closed_reason_code: null,
    reason_summary: 'No fail-closed refusal reason is active.',
    trust_status: 'passed',
    freshness_status: 'passed',
    trust_failed: false,
    freshness_failed: false,
    safe_partial_output_allowed: false,
    partial_context_safe: false,
    ranking_applied: false,
    selection_made: false,
  },
  limitations: [
    {
      limitation_id: 'no_manager_intent',
      message: 'BaseballOS does not know manager intent.',
      severity: 'informational',
      applies_to: 'team_context',
    },
  ],
  explanations: [
    {
      explanation_id: 'availability_inventory',
      level: 'bullpen',
      message: 'Bullpen inventory is summarized from current availability evidence.',
      evidence: ['Current availability classifications are present.'],
      applies_to: 'bullpen_state',
    },
  ],
  refusal_reasons: [],
  fail_closed: false,
  trust_metadata: {
    scope: 'bullpen_state',
    ranking_applied: false,
    selection_made: false,
    confidence: 'medium',
    data_state: 'complete',
    generated_at: '2026-06-02T12:00:00Z',
  },
  bullpen_state: {
    status: 'available_context',
    stress_level: 'normal',
    readiness_summary: 'Current availability inventory can be summarized.',
    inventory_summary: [
      {
        inventory_type: 'availability_inventory',
        label: 'Availability Inventory',
        count: 1,
        members: [
          {
            pitcher_id: 42,
            display_name: 'Example Pitcher',
          },
        ],
        evidence: ['Availability category is Available.'],
        limitations: [],
        freshness: {
          freshness_state: 'current',
        },
        confidence: 'medium',
      },
    ],
    candidate_groups: [
      {
        group_id: 'available_candidates',
        label: 'Available Candidates',
        description: 'Candidates grouped by current availability category.',
        eligibility_basis: ['availability_status_available'],
        candidate_count: 1,
        ordering: 'input_order_non_ranking',
        candidates: [
          {
            pitcher_id: 42,
            display_name: 'Example Pitcher',
          },
        ],
        explanations: [],
        limitations: [],
        confidence: 'medium',
        freshness: {
          freshness_state: 'current',
        },
        refusal_reasons: [],
      },
    ],
    team_context: {
      workload_distribution: {},
      availability_distribution: {
        Available: 1,
      },
      leverage_inventory: [],
      readiness_indicators: [],
      stress_indicators: [],
      explanations: [],
      limitations: [],
    },
    trust: {
      ranking_applied: false,
      selection_made: false,
    },
  },
}

test('normalizes a successful V2 bullpen-state response without ranking or selection', () => {
  const view = normalizeRecommendationV2BullpenStateResponse(baseV2Response)

  assert.equal(view.endpoint, RECOMMENDATION_V2_BULLPEN_STATE_ROUTE)
  assert.equal(view.contractState, 'available')
  assert.equal(view.isContractSafe, true)
  assert.equal(view.isFailClosed, false)
  assert.equal(view.governance.rankingApplied, false)
  assert.equal(view.governance.selectionMade, false)
  assert.equal(view.governance.trustRankingApplied, false)
  assert.equal(view.governance.trustSelectionMade, false)
  assert.deepEqual(view.freshness, baseV2Response.freshness)
  assert.deepEqual(view.statusMetadata, baseV2Response.status_metadata)
  assert.deepEqual(view.limitations, baseV2Response.limitations)
  assert.deepEqual(view.explanations, baseV2Response.explanations)
  assert.deepEqual(view.refusalReasons, [])
  assert.deepEqual(view.trustMetadata, baseV2Response.trust_metadata)
  assert.equal(view.failClosed, false)
  assert.equal(view.bullpenState.candidate_groups[0].ordering, 'input_order_non_ranking')
  assert.deepEqual(view.missingFields, [])
  assert.deepEqual(view.malformedFields, [])
  assert.deepEqual(view.forbiddenFieldPaths, [])
  assert.equal(Object.hasOwn(view, 'selectedPitcher'), false)
  assert.equal(Object.hasOwn(view, 'rankedCandidates'), false)
  assert.equal(Object.hasOwn(view, 'rawResponse'), false)
})

test('preserves fail-closed refusal metadata as a contract-safe state', () => {
  const failClosedResponse = {
    ...baseV2Response,
    confidence: 'low',
    data_state: 'stale',
    fail_closed: true,
    refusal_reasons: [
      {
        refusal_id: 'stale_freshness',
        reason: 'freshness_stale',
        message: 'Current bullpen-state output is refused because data is stale.',
        applies_to: 'bullpen_state',
      },
    ],
    bullpen_state: null,
  }

  const view = normalizeRecommendationV2BullpenStateResponse(failClosedResponse)

  assert.equal(view.contractState, 'fail_closed')
  assert.equal(view.isContractSafe, true)
  assert.equal(view.isFailClosed, true)
  assert.equal(view.governance.rankingApplied, false)
  assert.equal(view.governance.selectionMade, false)
  assert.deepEqual(view.refusalReasons, failClosedResponse.refusal_reasons)
  assert.equal(view.failClosed, true)
  assert.equal(view.bullpenState, null)
})

test('accepts structured fail-closed metadata from the V2 bullpen-state contract', () => {
  const failClosedResponse = {
    ...baseV2Response,
    confidence: 'low',
    data_state: 'missing',
    freshness: {
      sync_timestamp: '2026-06-03T07:44:27',
      data_through: '2026-05-01',
      freshness_state: 'stale',
      source_freshness_status: 'stale',
      aggregate_v2_freshness_status: 'stale',
      overall_sync_status: 'success',
      overall_sync_current: true,
      state_code: 'STALE',
      stale_warning: 'Some source evidence is stale.',
      missing_data_warning: null,
    },
    status_metadata: {
      overall_sync_status: 'success',
      overall_sync_current: true,
      sync_timestamp: '2026-06-03T07:44:27',
      sync_data_through: '2026-06-02',
      source_freshness_status: 'stale',
      aggregate_v2_freshness_status: 'stale',
      fail_closed_state: 'degraded',
      fail_closed_reason_code: 'data_state_stale',
      reason_summary: 'Source freshness is stale. V2 is preserving fail-closed protection while displaying degraded context only.',
      trust_status: 'passed',
      freshness_status: 'failed',
      trust_failed: false,
      freshness_failed: true,
      safe_partial_output_allowed: true,
      partial_context_safe: true,
      withheld_summary: 'Current-state interpretation is withheld; degraded context remains visible with refusal metadata.',
      ranking_applied: false,
      selection_made: false,
    },
    fail_closed: {
      failed_closed: true,
      state: 'degraded',
      governance_state: 'failed_closed',
      ranking_applied: false,
      selection_made: false,
      reason_codes: ['data_state_stale'],
      primary_reason_code: 'data_state_stale',
      reason_summary: 'Source freshness is stale. V2 is preserving fail-closed protection while displaying degraded context only.',
      display_label: 'Data freshness protection active',
      withheld_summary: 'Current-state interpretation is withheld; degraded context remains visible with refusal metadata.',
      trust_failed: false,
      freshness_failed: true,
      safe_partial_output_allowed: true,
      partial_context_safe: true,
    },
    refusal_reasons: [
      {
        refusal_id: 'stale_data_state',
        reason: 'data_state_stale',
        message: 'V2 context is degraded or refused because source data state is stale.',
        applies_to: 'bullpen_state',
      },
    ],
  }

  const view = normalizeRecommendationV2BullpenStateResponse(failClosedResponse)

  assert.equal(view.contractState, 'fail_closed')
  assert.equal(view.isContractSafe, true)
  assert.equal(view.isFailClosed, true)
  assert.deepEqual(view.failClosed, failClosedResponse.fail_closed)
  assert.deepEqual(view.freshness, failClosedResponse.freshness)
  assert.deepEqual(view.statusMetadata, failClosedResponse.status_metadata)
  assert.deepEqual(view.refusalReasons, failClosedResponse.refusal_reasons)
  assert.deepEqual(view.malformedFields, [])
  assert.equal(view.governance.rankingApplied, false)
  assert.equal(view.governance.selectionMade, false)
})

test('marks responses with missing governance fields unavailable without defaults', () => {
  const unsafeResponse = {
    ...baseV2Response,
    trust_metadata: {
      ...baseV2Response.trust_metadata,
    },
  }
  delete unsafeResponse.ranking_applied
  delete unsafeResponse.trust_metadata.selection_made

  const view = normalizeRecommendationV2BullpenStateResponse(unsafeResponse)

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isContractSafe, false)
  assert.equal(view.governance.rankingApplied, undefined)
  assert.equal(view.governance.selectionMade, false)
  assert.ok(view.missingFields.includes('ranking_applied'))
  assert.ok(view.missingFields.includes('trust_metadata.selection_made'))
  assert.equal(view.bullpenState, null)
  assert.equal(view.confidence, unsafeResponse.confidence)
  assert.deepEqual(view.refusalReasons, unsafeResponse.refusal_reasons)
})

test('rejects forbidden ranking and selection response fields', () => {
  const unsafeResponse = {
    ...baseV2Response,
    ranked_candidates: [],
    bullpen_state: {
      ...baseV2Response.bullpen_state,
      selected_pitcher: {
        pitcher_id: 42,
      },
    },
  }

  const view = normalizeRecommendationV2BullpenStateResponse(unsafeResponse)

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isContractSafe, false)
  assert.deepEqual(
    view.forbiddenFieldPaths.sort(),
    ['bullpen_state.selected_pitcher', 'ranked_candidates'],
  )
  assert.equal(view.bullpenState, null)
  assert.equal(Object.hasOwn(view, 'selectedPitcher'), false)
  assert.equal(Object.hasOwn(view, 'rankedCandidates'), false)
  assert.equal(Object.hasOwn(view, 'rawResponse'), false)
})

test('fetches the approved V2 bullpen-state endpoint and returns normalized contract data', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  globalThis.fetch = async (url, options) => {
    assert.equal(url, `/api${RECOMMENDATION_V2_BULLPEN_STATE_ROUTE}?team_id=SEA&limit=25`)
    assert.equal(options.method, undefined)
    assert.equal(options.headers['Content-Type'], 'application/json')

    return {
      ok: true,
      json: async () => baseV2Response,
    }
  }

  const view = await getRecommendationV2BullpenState({
    team_id: 'SEA',
    limit: 25,
    empty: '',
    skip: null,
  })

  assert.equal(view.contractState, 'available')
  assert.equal(view.governance.rankingApplied, false)
  assert.equal(view.governance.selectionMade, false)
  assert.deepEqual(view.trustMetadata, baseV2Response.trust_metadata)
})

test('deduplicates concurrent identical V2 bullpen-state GET requests', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  let callCount = 0
  globalThis.fetch = async (url, options) => {
    callCount += 1
    assert.equal(url, `/api${RECOMMENDATION_V2_BULLPEN_STATE_ROUTE}?limit=25`)
    assert.equal(options.method, undefined)

    return {
      ok: true,
      json: async () => baseV2Response,
    }
  }

  const [first, second] = await Promise.all([
    getRecommendationV2BullpenState({ limit: 25 }),
    getRecommendationV2BullpenState({ limit: 25 }),
  ])

  assert.equal(callCount, 1)
  assert.equal(first.governance.rankingApplied, false)
  assert.equal(second.governance.selectionMade, false)
})
