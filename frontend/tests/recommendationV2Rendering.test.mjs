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
  default: RecommendationV2BullpenStatePanel,
  getRecommendationV2BullpenStateView,
} = await server.ssrLoadModule('/src/components/recommendations/RecommendationV2BullpenStatePanel.jsx')
const { default: Dashboard } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const visibleText = (html) => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

const forbiddenDisplayTerms = [
  /\bBest\b/i,
  /\bTop\b/i,
  /\bPreferred\b/i,
  /\bRecommended\b/i,
  /\bWinner\b/i,
  /\bPick\b/i,
  /\bSelection\b/i,
  /\bRank\b/i,
  /\bScore\b/i,
  /\bProjection\b/i,
  /\bForecast\b/i,
]

const availableState = {
  endpoint: '/recommendations/v2/bullpen-state',
  contractState: 'available',
  isContractSafe: true,
  isFailClosed: false,
  governance: {
    rankingApplied: false,
    selectionMade: false,
    trustRankingApplied: false,
    trustSelectionMade: false,
    rankingAppliedIsFalse: true,
    selectionMadeIsFalse: true,
  },
  missingFields: [],
  malformedFields: [],
  forbiddenFieldPaths: [],
  scope: 'bullpen_state',
  confidence: 'medium',
  dataState: 'complete',
  generatedAt: '2026-06-02T12:00:00Z',
  freshness: {
    sync_timestamp: '2026-06-02T11:55:00Z',
    data_through: '2026-06-02',
    freshness_state: 'current',
    stale_warning: null,
    missing_data_warning: null,
  },
  limitations: [
    {
      limitation_id: 'no_manager_intent',
      message: 'BaseballOS does not know manager intent or warm-up activity.',
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
  refusalReasons: [],
  trustMetadata: {
    scope: 'bullpen_state',
    ranking_applied: false,
    selection_made: false,
    confidence: 'medium',
    data_state: 'complete',
    generated_at: '2026-06-02T12:00:00Z',
  },
  bullpenState: {
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
      workload_distribution: {
        rested: 1,
      },
      availability_distribution: {
        Available: 1,
      },
      leverage_inventory: [],
      readiness_indicators: [
        {
          message: 'Readiness context is available from current workload evidence.',
        },
      ],
      stress_indicators: [
        {
          message: 'Stress context is normal from current workload evidence.',
        },
      ],
      explanations: [],
      limitations: [],
    },
    trust: {
      ranking_applied: false,
      selection_made: false,
    },
  },
}

function renderPanel(state, props = {}) {
  return renderToStaticMarkup(
    React.createElement(RecommendationV2BullpenStatePanel, { state, ...props }),
  )
}

test('renders governed V2 bullpen intelligence in available state', () => {
  const html = renderPanel(availableState)

  assert.ok(htmlIncludes(html, 'V2 Bullpen Intelligence'))
  assert.ok(htmlIncludes(html, 'Bullpen State'))
  assert.ok(htmlIncludes(html, 'Available'))
  assert.ok(htmlIncludes(html, 'Trust'))
  assert.ok(htmlIncludes(html, 'Freshness'))
  assert.ok(htmlIncludes(html, 'Limitations'))
  assert.ok(htmlIncludes(html, 'Explanations'))
  assert.ok(htmlIncludes(html, 'Inventory'))
  assert.ok(htmlIncludes(html, 'Team Context'))
  assert.ok(htmlIncludes(html, 'Neutral Candidate Groups'))
  assert.ok(htmlIncludes(html, 'Example Pitcher'))
  assert.ok(htmlIncludes(html, 'Ordering applied'))
  assert.ok(htmlIncludes(html, 'Automated decision made'))
  assert.ok(htmlIncludes(html, 'neutral source order'))
  assert.ok(htmlIncludes(html, 'Bullpen inventory is summarized from current availability evidence.'))
  assert.ok(htmlIncludes(html, 'BaseballOS does not know manager intent or warm-up activity.'))
})

test('renders fail-closed state with refusal metadata visible', () => {
  const failClosedState = {
    ...availableState,
    contractState: 'fail_closed',
    isFailClosed: true,
    confidence: 'low',
    dataState: 'stale',
    bullpenState: null,
    refusalReasons: [
      {
        refusal_id: 'stale_freshness',
        reason: 'freshness_stale',
        message: 'Current bullpen-state output is refused because data is stale.',
        applies_to: 'bullpen_state',
      },
    ],
  }

  const html = renderPanel(failClosedState)

  assert.ok(htmlIncludes(html, 'Fail-Closed'))
  assert.ok(htmlIncludes(html, 'Refusal'))
  assert.ok(htmlIncludes(html, 'Current bullpen-state output is refused because data is stale.'))
  assert.ok(htmlIncludes(html, 'No inventory summary available.'))
  assert.ok(htmlIncludes(html, 'No neutral groups available from the current contract state.'))
})

test('renders unavailable state without rendering withheld bullpen details', () => {
  const unavailableState = {
    ...availableState,
    contractState: 'unavailable',
    isContractSafe: false,
    missingFields: ['ranking_applied'],
    malformedFields: ['freshness'],
    forbiddenFieldPaths: ['bullpen_state.selected_pitcher'],
  }

  const html = renderPanel(unavailableState)

  assert.ok(htmlIncludes(html, 'Contract Unavailable'))
  assert.ok(htmlIncludes(html, 'Diagnostics detected: 3'))
  assert.ok(htmlIncludes(html, 'Bullpen state output is withheld from this surface.'))
  assert.ok(!htmlIncludes(html, 'Example Pitcher'))
  assert.ok(!htmlIncludes(html, 'Availability Inventory'))
})

test('view model with unsafe display language becomes unavailable', () => {
  const unsafeState = {
    ...availableState,
    bullpenState: {
      ...availableState.bullpenState,
      candidate_groups: [
        {
          ...availableState.bullpenState.candidate_groups[0],
          label: 'Best Available Candidates',
        },
      ],
    },
  }

  const view = getRecommendationV2BullpenStateView(unsafeState)

  assert.equal(view.contractState, 'unavailable')
  assert.equal(view.hiddenUnsafeLanguage, true)
  assert.equal(view.bullpenState, null)
})

test('rendered V2 panel avoids prohibited decision language', () => {
  const text = visibleText(renderPanel(availableState))

  for (const term of forbiddenDisplayTerms) {
    assert.equal(term.test(text), false, `unexpected governed V2 display term: ${term}`)
  }
})

test('renders loading and error states without exposing unsafe claims', () => {
  const loadingHtml = renderPanel(null, { loading: true })
  const errorHtml = renderPanel(null, { error: 'network unavailable' })

  assert.ok(htmlIncludes(loadingHtml, 'Loading V2 bullpen intelligence...'))
  assert.ok(htmlIncludes(errorHtml, 'V2 bullpen intelligence could not be loaded.'))
  assert.ok(!htmlIncludes(errorHtml, 'network unavailable'))
})

test('Dashboard imports cleanly with the governed V2 panel dependency', () => {
  assert.equal(typeof Dashboard, 'function')
})
