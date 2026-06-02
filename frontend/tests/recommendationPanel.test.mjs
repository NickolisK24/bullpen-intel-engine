import assert from 'node:assert/strict'
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
  default: RecommendationPanel,
  getRecommendationPanelView,
} = await server.ssrLoadModule('/src/components/recommendations/RecommendationPanel.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

const candidate = {
  pitcher_id: 42,
  pitcher_name: 'Example Pitcher',
}

const baseResponse = {
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

function renderPanel(props = {}) {
  return renderToStaticMarkup(React.createElement(RecommendationPanel, props))
}

test('RecommendationPanel renders success state from a candidate response', () => {
  const html = renderPanel({ response: baseResponse, candidate })

  assert.ok(htmlIncludes(html, 'Recommendation Engine V1'))
  assert.ok(htmlIncludes(html, 'Candidate Evaluation'))
  assert.ok(htmlIncludes(html, 'Candidate Evaluation Ready'))
  assert.ok(htmlIncludes(html, 'Example Pitcher'))
  assert.ok(htmlIncludes(html, 'Eligible Categories'))
  assert.ok(htmlIncludes(html, 'Best Available Arm'))
  assert.ok(htmlIncludes(html, 'Explanation'))
  assert.ok(htmlIncludes(html, 'Candidate passed Recommendation Engine V1 eligibility gates.'))
  assert.ok(htmlIncludes(html, 'Limitation'))
  assert.ok(htmlIncludes(html, 'Candidate-level evaluation only.'))
})

test('RecommendationPanel renders caution state and caution reasons', () => {
  const cautionResponse = {
    ...baseResponse,
    data: {
      ...baseResponse.data,
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
          code: 'limited_confidence',
          message: 'Medium confidence must remain visible.',
        },
      ],
    },
  }

  const html = renderPanel({ response: cautionResponse, candidate })

  assert.ok(htmlIncludes(html, 'Use With Caution'))
  assert.ok(htmlIncludes(html, 'Caution reasons are shown in explanations and limitations below.'))
  assert.ok(htmlIncludes(html, 'Monitor status requires caution before use.'))
  assert.ok(htmlIncludes(html, 'Medium confidence must remain visible.'))
  assert.ok(htmlIncludes(html, 'Monitor'))
})

test('RecommendationPanel renders refusal state with refusal reason and explanations', () => {
  const refusalResponse = {
    ...baseResponse,
    data: {
      ...baseResponse.data,
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

  const html = renderPanel({ response: refusalResponse, candidate })

  assert.ok(htmlIncludes(html, 'Insufficient trusted data'))
  assert.ok(htmlIncludes(html, 'Stale data'))
  assert.ok(htmlIncludes(html, 'Blocked Categories'))
  assert.ok(htmlIncludes(html, 'Freshness check failed.'))
  assert.ok(htmlIncludes(html, 'Freshness check failed for candidate evaluation.'))
  assert.ok(htmlIncludes(html, 'Recommendation output fails closed when trusted data is stale.'))
})

test('RecommendationPanel renders loading state', () => {
  const html = renderPanel({ isLoading: true })

  assert.ok(htmlIncludes(html, 'Loading candidate evaluation'))
  assert.ok(htmlIncludes(html, 'No Bullpen Ranking Applied'))
  assert.ok(htmlIncludes(html, 'No Final Pitcher Selection Made'))
})

test('RecommendationPanel renders safe error state without stack traces', () => {
  const html = renderPanel({ error: new Error('private stack details') })

  assert.ok(htmlIncludes(html, 'Something went wrong'))
  assert.ok(htmlIncludes(html, 'Candidate evaluation could not be loaded.'))
  assert.ok(!htmlIncludes(html, 'private stack details'))
})

test('RecommendationPanel renders empty state', () => {
  const html = renderPanel()

  assert.ok(htmlIncludes(html, 'No candidate evaluation available'))
  assert.ok(htmlIncludes(html, 'No eligible categories available for this state.'))
  assert.ok(htmlIncludes(html, 'Pending candidate input'))
})

test('RecommendationPanel renders trust, freshness, availability, and metadata fields', () => {
  const html = renderPanel({ response: baseResponse, candidate })

  assert.ok(htmlIncludes(html, 'Confidence'))
  assert.ok(htmlIncludes(html, 'High'))
  assert.ok(htmlIncludes(html, 'Data Freshness'))
  assert.ok(htmlIncludes(html, 'Fresh · Data Through 2026-06-01'))
  assert.ok(htmlIncludes(html, 'Availability'))
  assert.ok(htmlIncludes(html, 'Available'))
  assert.ok(htmlIncludes(html, 'No Bullpen Ranking Applied'))
  assert.ok(htmlIncludes(html, 'No Final Pitcher Selection Made'))
  assert.ok(htmlIncludes(html, 'ranking_applied'))
  assert.ok(htmlIncludes(html, 'selection_made'))
  assert.ok(htmlIncludes(html, 'false'))
})

test('RecommendationPanel renders assigned and blocked categories', () => {
  const html = renderPanel({ response: baseResponse, candidate })

  assert.ok(htmlIncludes(html, 'Best Available Arm'))
  assert.ok(htmlIncludes(html, 'Blocked Categories'))
  assert.ok(htmlIncludes(html, 'Bullpen Stress Alert'))
  assert.ok(htmlIncludes(html, 'Requires bullpen-level context.'))
})

test('RecommendationPanel view model preserves no-ranking and no-selection flags', () => {
  const view = getRecommendationPanelView({ response: baseResponse, candidate })

  assert.equal(view.metadata.rankingApplied, false)
  assert.equal(view.metadata.selectionMade, false)
  assert.equal(view.trust.confidence, 'High')
  assert.equal(view.trust.freshness, 'Fresh · Data Through 2026-06-01')
  assert.equal(view.trust.availability, 'Available')
  assert.equal(view.assignedCategories[0].label, 'Best Available Arm')
  assert.equal(view.blockedCategories[0].label, 'Bullpen Stress Alert')
})

test('RecommendationPanel does not call the live recommendation route while rendering', () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = () => {
    throw new Error('RecommendationPanel render must not call the API')
  }

  try {
    const html = renderPanel({ response: baseResponse, candidate })
    assert.ok(htmlIncludes(html, 'Example Pitcher'))
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('RecommendationPanel keeps prohibited claims out of rendered states', () => {
  const renderedStates = [
    renderPanel(),
    renderPanel({ isLoading: true }),
    renderPanel({ error: new Error('hidden') }),
    renderPanel({ response: baseResponse, candidate }),
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
