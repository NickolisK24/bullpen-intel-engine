import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
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
  default: RecommendationPitcherDetailSection,
} = await server.ssrLoadModule('/src/components/recommendations/RecommendationPitcherDetailSection.jsx')

const {
  buildRecommendationCandidateFromPitcherDetail,
  evaluatePitcherDetailRecommendation,
} = await server.ssrLoadModule('/src/components/recommendations/recommendationCandidate.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

const pitcherDetail = {
  pitcher: {
    id: 42,
    full_name: 'Example Pitcher',
    team_id: 7,
    team_name: 'Example Club',
  },
  current_fatigue: {
    raw_score: 24.5,
    risk_level: 'LOW',
    calculated_at: '2026-06-02T10:00:00Z',
  },
  availability: {
    availability_status: 'Available',
    confidence: 'high',
    data_state: 'fresh',
    inputs: {
      fatigue_score: 24.5,
      fatigue_risk_level: 'LOW',
      latest_game_date: '2026-06-01',
    },
    reasons: ['Trusted availability signal is present.'],
    limitations: ['Candidate-level output is not a final selection.'],
  },
}

const successResponse = {
  data: {
    outcome_code: 'RECOMMENDATION',
    confidence: {
      level: 'High',
      level_code: 'HIGH',
      reasons: [],
    },
    freshness: {
      state: 'Fresh',
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
        reasons: ['Requires bullpen-level context.'],
      },
    ],
    explanations: [
      {
        code: 'eligibility_passed',
        message: 'Candidate passed Recommendation Engine V1 eligibility gates.',
      },
    ],
    limitations: [
      {
        code: 'candidate_level_only',
        message: 'Candidate-level evaluation only.',
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

const cautionResponse = {
  ...successResponse,
  data: {
    ...successResponse.data,
    availability: {
      availability_status: 'Monitor',
      confidence: 'medium',
      data_state: 'fresh',
    },
    assigned_categories: [
      {
        category: 'use_with_caution',
        category_code: 'USE_WITH_CAUTION',
      },
    ],
    explanations: [
      {
        code: 'monitor_status',
        message: 'Monitor status requires caution before use.',
      },
    ],
    limitations: [
      {
        code: 'candidate_requires_caution',
        message: 'Candidate requires cautionary handling before any recommendation use.',
      },
    ],
  },
}

const refusalResponse = {
  ...successResponse,
  data: {
    ...successResponse.data,
    outcome_code: 'REFUSAL',
    assigned_categories: [],
    blocked_categories: [
      {
        category: 'best_available_arm',
        category_code: 'BEST_AVAILABLE_ARM',
        reasons: ['Freshness check failed.'],
      },
    ],
    explanations: [
      {
        code: 'stale_data',
        message: 'Freshness check failed for candidate evaluation.',
      },
    ],
    limitations: [
      {
        code: 'fail_closed',
        message: 'Recommendation output fails closed when trusted data is stale.',
      },
    ],
    refusal: {
      reason: 'Stale data',
      reason_code: 'STALE_DATA',
      message: 'Insufficient trusted data',
    },
  },
}

function renderSection(props = {}) {
  return renderToStaticMarkup(
    React.createElement(RecommendationPitcherDetailSection, {
      pitcherDetail,
      ...props,
    }),
  )
}

test('RecommendationPitcherDetailSection renders in the pitcher detail context', () => {
  const html = renderSection()

  assert.ok(htmlIncludes(html, 'Recommendation Engine V1'))
  assert.ok(htmlIncludes(html, 'Candidate Evaluation'))
  assert.ok(htmlIncludes(html, 'Evaluate Candidate'))
  assert.ok(htmlIncludes(html, 'aria-describedby="recommendation-detail-description"'))
  assert.ok(htmlIncludes(html, 'aria-controls="recommendation-detail-result"'))
  assert.ok(htmlIncludes(html, 'aria-label="Evaluate recommendation candidate for Example Pitcher"'))
  assert.ok(htmlIncludes(html, 'No Final Pitcher Selection Made'))
  assert.ok(htmlIncludes(html, 'No Bullpen Ranking Applied'))
  assert.ok(htmlIncludes(html, 'No candidate evaluation available'))
  assert.ok(htmlIncludes(html, 'Use Evaluate Candidate to inspect this pitcher without ranking the bullpen.'))
})

test('pitcher detail candidate mapper preserves one pitcher and availability state', () => {
  const candidate = buildRecommendationCandidateFromPitcherDetail(pitcherDetail)

  assert.equal(Array.isArray(candidate), false)
  assert.equal(candidate.pitcher_id, 42)
  assert.equal(candidate.pitcher_name, 'Example Pitcher')
  assert.equal(candidate.team_id, 7)
  assert.equal(candidate.team_name, 'Example Club')
  assert.equal(candidate.availability.availability_status, 'Available')
  assert.equal(candidate.availability.inputs.fatigue_score, 24.5)
  assert.equal(candidate.metadata.data_through, '2026-06-01')
})

test('pitcher detail recommendation helper sends one candidate request only', async () => {
  const calls = []
  const result = await evaluatePitcherDetailRecommendation(pitcherDetail, {
    evaluateCandidate: async (candidate, requestMetadata) => {
      calls.push({ candidate, requestMetadata })
      return successResponse
    },
  })

  assert.equal(result, successResponse)
  assert.equal(calls.length, 1)
  assert.equal(Array.isArray(calls[0].candidate), false)
  assert.equal(calls[0].candidate.pitcher_id, 42)
  assert.equal(calls[0].requestMetadata.source, 'pitcher_detail')
})

test('pitcher detail candidate mapper rejects multi-candidate payloads', () => {
  assert.throws(
    () => buildRecommendationCandidateFromPitcherDetail([pitcherDetail, pitcherDetail]),
    /one pitcher detail payload/,
  )
})

test('RecommendationPitcherDetailSection renders success response details', () => {
  const html = renderSection({ initialState: { response: successResponse } })

  assert.ok(htmlIncludes(html, 'data-recommendation-state="success"'))
  assert.ok(htmlIncludes(html, 'Eligible Categories'))
  assert.ok(htmlIncludes(html, 'Best Available Arm'))
  assert.ok(htmlIncludes(html, 'Blocked Categories'))
  assert.ok(htmlIncludes(html, 'Bullpen Stress Alert'))
  assert.ok(htmlIncludes(html, 'Candidate passed Recommendation Engine V1 eligibility gates.'))
  assert.ok(htmlIncludes(html, 'Candidate-level evaluation only.'))
})

test('RecommendationPitcherDetailSection renders caution state distinctly', () => {
  const html = renderSection({ initialState: { response: cautionResponse } })

  assert.ok(htmlIncludes(html, 'data-recommendation-state="caution"'))
  assert.ok(htmlIncludes(html, 'Use With Caution'))
  assert.ok(htmlIncludes(html, 'border-amber/35'))
  assert.ok(htmlIncludes(html, 'Caution reasons are shown in explanations and limitations below.'))
  assert.ok(htmlIncludes(html, 'Monitor status requires caution before use.'))
  assert.ok(htmlIncludes(html, 'Candidate requires cautionary handling before any recommendation use.'))
  assert.ok(htmlIncludes(html, 'Monitor'))
})

test('RecommendationPitcherDetailSection renders refusal output', () => {
  const html = renderSection({ initialState: { response: refusalResponse } })

  assert.ok(htmlIncludes(html, 'data-recommendation-state="refusal"'))
  assert.ok(htmlIncludes(html, 'Refusal Reason'))
  assert.ok(htmlIncludes(html, 'Insufficient trusted data'))
  assert.ok(htmlIncludes(html, 'Stale data'))
  assert.ok(htmlIncludes(html, 'border-red-500/30'))
  assert.ok(htmlIncludes(html, 'Freshness check failed.'))
  assert.ok(htmlIncludes(html, 'Recommendation output fails closed when trusted data is stale.'))
})

test('RecommendationPitcherDetailSection renders loading state', () => {
  const html = renderSection({ initialState: { isLoading: true } })

  assert.ok(htmlIncludes(html, 'Evaluating...'))
  assert.ok(htmlIncludes(html, 'Loading candidate evaluation'))
  assert.ok(htmlIncludes(html, 'aria-busy="true"'))
  assert.ok(htmlIncludes(html, 'data-recommendation-state="loading"'))
})

test('RecommendationPitcherDetailSection renders safe error state', () => {
  const html = renderSection({ initialState: { error: new Error('private transport details') } })

  assert.ok(htmlIncludes(html, 'Candidate evaluation could not be loaded.'))
  assert.ok(htmlIncludes(html, 'data-recommendation-state="error"'))
  assert.ok(!htmlIncludes(html, 'private transport details'))
})

test('RecommendationPitcherDetailSection keeps trust, freshness, availability, and metadata visible', () => {
  const html = renderSection({ initialState: { response: successResponse } })

  assert.ok(htmlIncludes(html, 'Confidence'))
  assert.ok(htmlIncludes(html, 'High'))
  assert.ok(htmlIncludes(html, 'Data Freshness'))
  assert.ok(htmlIncludes(html, 'Fresh · Data Through 2026-06-01'))
  assert.ok(htmlIncludes(html, 'Availability'))
  assert.ok(htmlIncludes(html, 'Available'))
  assert.ok(htmlIncludes(html, 'ranking_applied'))
  assert.ok(htmlIncludes(html, 'selection_made'))
  assert.ok(htmlIncludes(html, 'false'))
})

test('RecommendationPitcherDetailSection preserves mobile-safe layout structure', () => {
  const html = renderSection({ initialState: { response: successResponse } })

  assert.ok(htmlIncludes(html, 'recommendation-detail-panel'))
  assert.ok(htmlIncludes(html, 'recommendation-detail-panel__trust-grid'))
  assert.ok(htmlIncludes(html, 'recommendation-panel'))
  assert.ok(htmlIncludes(html, 'recommendation-panel--embedded'))
  assert.ok(htmlIncludes(html, 'recommendation-panel__layout'))
  assert.ok(htmlIncludes(html, 'recommendation-panel__layout--embedded'))
  assert.ok(htmlIncludes(html, 'recommendation-panel__trust-grid'))
  assert.ok(htmlIncludes(html, 'min-w-0'))
  assert.ok(htmlIncludes(html, 'max-w-full'))
  assert.ok(htmlIncludes(html, 'min-h-10'))
  assert.ok(htmlIncludes(html, 'w-full'))
  assert.ok(htmlIncludes(html, 'sm:w-auto'))
})

test('Bullpen selected-pitcher layout uses readable panel widths instead of cramped fixed splits', async () => {
  const [bullpenSource, panelSource, cssSource] = await Promise.all([
    readFile(new URL('../src/components/bullpen/Bullpen.jsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/recommendations/RecommendationPanel.jsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/index.css', import.meta.url), 'utf8'),
  ])

  assert.ok(bullpenSource.includes('2xl:flex-row'))
  assert.ok(bullpenSource.includes('max-w-[100rem]'))
  assert.ok(bullpenSource.includes('lg:w-full'))
  assert.ok(bullpenSource.includes('2xl:w-[36rem]'))
  assert.ok(!bullpenSource.includes('lg:w-[60%]'))
  assert.ok(!bullpenSource.includes('lg:w-[38%]'))
  assert.ok(panelSource.includes('recommendation-panel__layout'))
  assert.ok(panelSource.includes('recommendation-panel--embedded'))
  assert.ok(panelSource.includes('recommendation-panel__layout--embedded'))
  assert.ok(panelSource.includes('recommendation-panel__trust-grid'))
  assert.ok(!panelSource.includes('xl:grid-cols-[minmax(0,1.2fr)_minmax(20rem,0.8fr)]'))
  assert.ok(!panelSource.includes('xl:grid-cols-1'))
  assert.ok(cssSource.includes('.recommendation-detail-panel'))
  assert.ok(cssSource.includes('.recommendation-panel--embedded .recommendation-panel__layout'))
  assert.ok(cssSource.includes('.recommendation-panel--standalone .recommendation-panel__layout--standalone'))
  assert.ok(cssSource.includes('@container (min-width: 42rem)'))
  assert.ok(cssSource.includes('@container (min-width: 76rem)'))
})

test('RecommendationPitcherDetailSection keeps prohibited copy out of rendered states', () => {
  const renderedStates = [
    renderSection(),
    renderSection({ initialState: { isLoading: true } }),
    renderSection({ initialState: { error: new Error('hidden') } }),
    renderSection({ initialState: { response: successResponse } }),
    renderSection({ initialState: { response: cautionResponse } }),
    renderSection({ initialState: { response: refusalResponse } }),
  ].join('\n')

  const blockedCopy = [
    'Best Pitcher',
    ['A', 'I Pick'].join(''),
    'Guaranteed Option',
    'Manager Should Use',
    ['Final', 'Recommendation'].join(' '),
    ['Selected', 'Pitcher'].join(' '),
  ]

  for (const label of blockedCopy) {
    assert.ok(!htmlIncludes(renderedStates, label), `unexpected rendered copy: ${label}`)
  }
})
