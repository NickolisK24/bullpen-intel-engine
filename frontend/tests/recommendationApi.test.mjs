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
  RECOMMENDATION_CANDIDATE_ROUTE,
  buildRecommendationCandidateRequest,
  evaluateRecommendationCandidate,
  getRecommendationCandidateTrustFields,
} = await server.ssrLoadModule('/src/utils/api.js')

const candidate = {
  pitcher_id: 42,
  pitcher_name: 'Example Pitcher',
  availability: {
    availability_status: 'Available',
    confidence: 'high',
    data_state: 'fresh',
    inputs: {
      fatigue_score: 20,
    },
  },
  metadata: {
    data_through: '2026-06-01',
  },
}

const recommendationResponse = {
  data: {
    outcome_code: 'RECOMMENDATION',
    confidence: {
      level: 'high',
      level_code: 'HIGH',
      reasons: [],
    },
    freshness: {
      state: 'fresh',
      state_code: 'FRESH',
      data_through: '2026-06-01',
      limitations: [],
    },
    availability: {
      availability_status: 'Available',
      confidence: 'high',
      data_state: 'fresh',
    },
    assigned_categories: [
      {
        category: 'best_available_arm',
        category_code: 'BEST_AVAILABLE_ARM',
      },
    ],
    blocked_categories: [
      {
        category: 'bullpen_stress_alert',
        category_code: 'BULLPEN_STRESS_ALERT',
        reasons: ['requires_bullpen_context'],
      },
    ],
    explanations: [
      {
        code: 'eligibility_passed',
        message: 'Candidate passed Recommendation Engine V1 eligibility gates.',
        details: {},
      },
    ],
    limitations: [
      {
        code: 'builder_not_final_recommender',
        message: 'Candidate-level composition only.',
      },
    ],
    refusal: null,
  },
  meta: {
    ranking_applied: false,
    selection_made: false,
    selected_pitcher_id: null,
  },
}

test('builds the candidate-level recommendation request shape', () => {
  const payload = buildRecommendationCandidateRequest(candidate, {
    request_id: 'recommendation-client-test',
  })

  assert.deepEqual(payload, {
    candidate,
    request: {
      request_id: 'recommendation-client-test',
    },
  })
})

test('rejects multi-candidate arrays before calling the route', () => {
  assert.throws(
    () => buildRecommendationCandidateRequest([candidate]),
    /exactly one candidate/,
  )
})

test('rejects missing candidate input before calling the route', () => {
  assert.throws(
    () => buildRecommendationCandidateRequest(null),
    /candidate object/,
  )
})

test('rejects malformed request metadata before calling the route', () => {
  assert.throws(
    () => buildRecommendationCandidateRequest(candidate, ['bad-metadata']),
    /metadata must be an object/,
  )
})

test('exposes trust, freshness, refusal, and no-selection fields', () => {
  const fields = getRecommendationCandidateTrustFields({
    ...recommendationResponse,
    data: {
      ...recommendationResponse.data,
      refusal: {
        reason: 'stale_data',
        reason_code: 'STALE_DATA',
        message: 'Trusted current workload data is insufficient.',
      },
    },
  })

  assert.deepEqual(fields.explanations, recommendationResponse.data.explanations)
  assert.deepEqual(fields.limitations, recommendationResponse.data.limitations)
  assert.deepEqual(fields.confidence, recommendationResponse.data.confidence)
  assert.deepEqual(fields.freshness, recommendationResponse.data.freshness)
  assert.deepEqual(fields.availability, recommendationResponse.data.availability)
  assert.deepEqual(fields.assignedCategories, recommendationResponse.data.assigned_categories)
  assert.deepEqual(fields.blockedCategories, recommendationResponse.data.blocked_categories)
  assert.equal(fields.refusal.reason_code, 'STALE_DATA')
  assert.equal(fields.rankingApplied, false)
  assert.equal(fields.selectionMade, false)
  assert.equal(fields.selectedPitcherId, null)
})

test('posts one candidate to the recommendation route and returns parsed response', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  globalThis.fetch = async (url, options) => {
    assert.equal(url, `/api${RECOMMENDATION_CANDIDATE_ROUTE}`)
    assert.equal(options.method, 'POST')
    assert.deepEqual(JSON.parse(options.body), {
      candidate,
      request: {
        request_id: 'recommendation-client-test',
      },
    })

    return {
      ok: true,
      json: async () => recommendationResponse,
    }
  }

  const response = await evaluateRecommendationCandidate(candidate, {
    request_id: 'recommendation-client-test',
  })

  assert.deepEqual(response, recommendationResponse)
})
