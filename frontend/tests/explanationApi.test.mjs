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
  EXPLANATION_AVAILABILITY_ROUTE_PREFIX,
  EXPLANATION_TEAM_READINESS_ROUTE,
  getAvailabilityExplanation,
  getTeamReadinessExplanation,
  normalizeV4ExplanationApiResponse,
} = await server.ssrLoadModule('/src/utils/api.js')

const clone = value => JSON.parse(JSON.stringify(value))

const governance = {
  ranking_applied: false,
  selection_made: false,
  recommendation_made: false,
  prediction_made: false,
  decision_scope: 'explanation_only',
  advice_scope: 'none',
}

const successEnvelope = {
  status: 'ok',
  explanation_type: 'team_readiness_explanation',
  certification_status: 'certified_with_non_blocking_observations',
  route_status: 'internal_uncertified_route',
  explanation: {
    capability: 'v4_evidence_and_explanation',
    contract: 'baseballos.v4.explanation.domain',
    contract_version: 'v4_phase_4',
    explanation_id: 'readiness_state_example',
    scope: 'readiness_state',
    subject_type: 'bullpen',
    subject_id: 'team:SEA',
    state_explained: 'operationally_stable',
    summary: 'This readiness state reflects workload, freshness, coverage, and trust evidence.',
    primary_reasons: [
      {
        code: 'READINESS_DEGRADED_BY_LIMITATIONS',
        scope: 'readiness_state',
        label: 'Readiness context reviewed',
        summary: 'Visible readiness context explains the current state.',
        display_safe: true,
        certification_required: true,
      },
    ],
    supporting_evidence: [
      {
        evidence_id: 'availability_distribution_total',
        evidence_type: 'count',
        label: 'Availability distribution total',
        value: 6,
        unit: 'pitchers',
        source: 'team_operations_readiness',
        freshness: {
          status: 'current',
          data_through: '2026-06-03',
          last_sync_at: '2026-06-03T11:45:00Z',
          source_updated_at: null,
          freshness_failure: null,
          summary: 'Freshness metadata is current.',
        },
        trust_status: 'trusted',
        impact: 'Supports team-level readiness context.',
        limitation: null,
      },
    ],
    limitations: [
      {
        limitation_type: 'insufficient_context',
        severity: 'informational',
        summary: 'Manager intent is not represented.',
        affected_scopes: ['readiness_state'],
        requires_refusal: false,
      },
    ],
    freshness: {
      status: 'current',
      data_through: '2026-06-03',
      last_sync_at: '2026-06-03T11:45:00Z',
      source_updated_at: null,
      freshness_failure: null,
      summary: 'Freshness metadata is current.',
    },
    trust: {
      status: 'trusted',
      source: 'team_operations_readiness',
      contract: 'baseballos.v4.explanation.domain',
      certification_status: 'certified_with_non_blocking_observations',
      trust_failure: null,
      summary: 'Trust metadata is represented.',
    },
    confidence: {
      level: 'medium',
      summary: 'Explanation confidence reflects current source evidence.',
    },
    governance,
    generated_at: '2026-06-03T12:00:00Z',
  },
  governance,
}

const failClosedEnvelope = {
  status: 'unavailable',
  explanation_type: 'team_readiness_explanation',
  certification_status: 'certified_with_non_blocking_observations',
  route_status: 'internal_uncertified_route',
  explanation: null,
  limitations: [
    {
      limitation_type: 'missing_data',
      label: 'Required explanation inputs are unavailable',
      summary: 'Team Operations readiness explanation cannot be generated because source records are unavailable.',
    },
  ],
  refusal: {
    refused: true,
    reason_code: 'missing_source_data',
    summary: 'Team Operations readiness explanation cannot be generated because source records are unavailable.',
  },
  governance,
}

test('normalizes certified successful explanation envelopes', () => {
  const view = normalizeV4ExplanationApiResponse(clone(successEnvelope))

  assert.equal(view.contractState, 'available')
  assert.equal(view.isContractSafe, true)
  assert.equal(view.isFailClosed, false)
  assert.equal(view.isCertifiedType, true)
  assert.equal(view.isInternalUncertified, true)
  assert.equal(view.explanationType, 'team_readiness_explanation')
  assert.equal(view.scope, 'readiness_state')
  assert.equal(view.summary, successEnvelope.explanation.summary)
  assert.equal(view.primaryReasons.length, 1)
  assert.equal(view.supportingEvidence.length, 1)
  assert.equal(view.limitations.length, 1)
  assert.equal(view.governance.rankingApplied, false)
  assert.equal(view.governance.selectionMade, false)
  assert.equal(view.governance.recommendationMade, false)
  assert.equal(view.governance.predictionMade, false)
  assert.equal(view.governance.decisionScope, 'explanation_only')
  assert.equal(view.governance.adviceScope, 'none')
  assert.deepEqual(view.missingFields, [])
  assert.deepEqual(view.malformedFields, [])
  assert.deepEqual(view.forbiddenFieldPaths, [])
  assert.deepEqual(view.forbiddenTextPaths, [])
  assert.equal(Object.hasOwn(view, 'rawResponse'), false)
})

test('normalizes governed fail-closed explanation envelopes', () => {
  const view = normalizeV4ExplanationApiResponse(clone(failClosedEnvelope))

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isContractSafe, true)
  assert.equal(view.isFailClosed, true)
  assert.equal(view.explanation, null)
  assert.equal(view.limitations.length, 1)
  assert.equal(view.refusal.reason_code, 'missing_source_data')
  assert.equal(view.governance.rankingApplied, false)
  assert.equal(view.governance.selectionMade, false)
})

test('marks missing governance metadata unsafe', () => {
  const response = clone(successEnvelope)
  delete response.governance

  const view = normalizeV4ExplanationApiResponse(response)

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isContractSafe, false)
  assert.equal(view.governanceSafe, false)
  assert.ok(view.missingFields.includes('governance'))
  assert.equal(view.explanation, null)
})

test('marks malformed governance metadata unsafe', () => {
  const response = clone(successEnvelope)
  response.governance.ranking_applied = 'false'

  const view = normalizeV4ExplanationApiResponse(response)

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isContractSafe, false)
  assert.equal(view.governanceSafe, false)
  assert.ok(view.malformedFields.includes('governance.ranking_applied'))
})

test('marks unsupported readiness scopes unsafe', () => {
  const response = clone(successEnvelope)
  response.explanation.scope = 'risk_distribution'

  const view = normalizeV4ExplanationApiResponse(response)

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isContractSafe, false)
  assert.equal(view.isUnsupportedScope, true)
})

test('does not call uncertified readiness scopes from the frontend client', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => {
    globalThis.fetch = originalFetch
  })
  globalThis.fetch = async () => {
    throw new Error('unsupported scope should not reach the network')
  }

  const view = await getTeamReadinessExplanation({ scope: 'risk_distribution' })

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isFailClosed, true)
  assert.equal(view.refusal.reason_code, 'unsupported_scope')
  assert.equal(view.governance.rankingApplied, false)
  assert.equal(view.governance.selectionMade, false)
})

test('fetches the certified default team readiness explanation route', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  globalThis.fetch = async (url, options) => {
    assert.equal(url, `/api${EXPLANATION_TEAM_READINESS_ROUTE}?team_id=7`)
    assert.equal(options.method, undefined)
    assert.equal(options.headers['Content-Type'], 'application/json')

    return {
      ok: true,
      json: async () => clone(successEnvelope),
    }
  }

  const view = await getTeamReadinessExplanation({ team_id: 7 })

  assert.equal(view.contractState, 'available')
  assert.equal(view.explanationType, 'team_readiness_explanation')
})

test('fetches certified scoped team readiness explanation routes', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  globalThis.fetch = async (url) => {
    assert.equal(url, `/api${EXPLANATION_TEAM_READINESS_ROUTE}/workload_state?team_abbreviation=SEA`)

    const response = clone(successEnvelope)
    response.explanation.scope = 'workload_state'
    return {
      ok: true,
      json: async () => response,
    }
  }

  const view = await getTeamReadinessExplanation({
    scope: 'workload_state',
    team_abbreviation: 'SEA',
  })

  assert.equal(view.contractState, 'available')
  assert.equal(view.scope, 'workload_state')
})

test('fetches certified availability explanation routes', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  globalThis.fetch = async (url) => {
    assert.equal(url, `/api${EXPLANATION_AVAILABILITY_ROUTE_PREFIX}/42`)

    const response = clone(successEnvelope)
    response.explanation_type = 'availability_explanation'
    response.explanation.scope = 'availability_state'
    response.explanation.subject_type = 'pitcher'
    response.explanation.subject_id = '42'
    response.explanation.state_explained = 'Monitor'
    return {
      ok: true,
      json: async () => response,
    }
  }

  const view = await getAvailabilityExplanation(42)

  assert.equal(view.contractState, 'available')
  assert.equal(view.explanationType, 'availability_explanation')
  assert.equal(view.scope, 'availability_state')
  assert.equal(view.subjectId, '42')
})

test('missing availability subject fails closed before a route call', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => {
    globalThis.fetch = originalFetch
  })
  globalThis.fetch = async () => {
    throw new Error('missing pitcher id should not reach the network')
  }

  const view = await getAvailabilityExplanation(null)

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.isFailClosed, true)
  assert.equal(view.refusal.reason_code, 'missing_subject')
  assert.equal(view.governance.recommendationMade, false)
})
