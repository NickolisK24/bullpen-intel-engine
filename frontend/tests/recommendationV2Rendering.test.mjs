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
  default: RecommendationV2BullpenStatePanel,
  getRecommendationV2BullpenStateView,
} = await server.ssrLoadModule('/src/components/recommendations/RecommendationV2BullpenStatePanel.jsx')
const { default: Dashboard } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')
const panelSource = await readFile(
  new URL('../src/components/recommendations/RecommendationV2BullpenStatePanel.jsx', import.meta.url),
  'utf8',
)
const cssSource = await readFile(
  new URL('../src/index.css', import.meta.url),
  'utf8',
)

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
        inventory_type: 'available_inventory',
        label: 'Available Inventory',
        count: 1,
        members: [
          {
            pitcher_id: 42,
            display_name: 'Inventory Member',
          },
        ],
        evidence: ['Availability category is Available.'],
        limitations: [],
        freshness: {
          freshness_state: 'current',
          data_through: '2026-06-02',
          sync_timestamp: '2026-06-02T11:55:00Z',
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
            display_name: 'Candidate Member',
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

  assert.ok(htmlIncludes(html, 'Bullpen Intelligence'))
  assert.ok(htmlIncludes(html, 'Bullpen Context'))
  assert.ok(htmlIncludes(html, 'Available'))
  assert.ok(htmlIncludes(html, 'Trust'))
  assert.ok(htmlIncludes(html, 'Freshness'))
  assert.ok(htmlIncludes(html, 'Limitations'))
  assert.ok(htmlIncludes(html, 'Explanations'))
  assert.ok(htmlIncludes(html, 'Inventory'))
  assert.ok(htmlIncludes(html, 'Team Context'))
  assert.ok(htmlIncludes(html, 'Neutral Candidate Groups'))
  assert.ok(htmlIncludes(html, 'Available Candidates'))
  assert.ok(htmlIncludes(html, '1 member'))
  assert.ok(htmlIncludes(html, 'Candidates grouped by current availability category.'))
  assert.ok(htmlIncludes(html, 'Team order'))
  assert.ok(htmlIncludes(html, 'Pitcher choice'))
  assert.ok(htmlIncludes(html, 'No ordering made'))
  assert.ok(htmlIncludes(html, 'No pitcher chosen'))
  assert.ok(htmlIncludes(html, 'neutral source order'))
  assert.ok(htmlIncludes(html, 'Bullpen inventory is summarized from current availability evidence.'))
  assert.ok(htmlIncludes(html, 'BaseballOS does not know manager intent or warm-up activity.'))
})

test('renders compact V2 bullpen intelligence with evidence collapsed and governance visible', () => {
  const html = renderPanel(availableState, { compact: true })

  assert.ok(htmlIncludes(html, 'Bullpen Intelligence'))
  assert.ok(htmlIncludes(html, 'Bullpen Context'))
  assert.ok(htmlIncludes(html, 'Team order'))
  assert.ok(htmlIncludes(html, 'Pitcher choice'))
  assert.ok(htmlIncludes(html, 'No ordering made'))
  assert.ok(htmlIncludes(html, 'No pitcher chosen'))
  assert.ok(htmlIncludes(html, 'View Evidence And Source Detail'))
  assert.ok(htmlIncludes(html, 'aria-expanded="false"'))
  assert.equal(htmlIncludes(html, 'Available Inventory'), false)
  assert.equal(htmlIncludes(html, 'Neutral Candidate Groups'), false)
  assert.equal(htmlIncludes(html, 'Bullpen inventory is summarized from current availability evidence.'), false)
})

test('renders inventory summary cards collapsed by default with counts and metadata visible', () => {
  const html = renderPanel(availableState)

  assert.ok(htmlIncludes(html, 'Available Inventory'))
  assert.ok(htmlIncludes(html, '1 Available'))
  assert.ok(htmlIncludes(html, 'Availability category is Available.'))
  assert.ok(htmlIncludes(html, 'Workload Read'))
  assert.ok(htmlIncludes(html, 'medium'))
  assert.ok(htmlIncludes(html, 'Freshness'))
  assert.ok(htmlIncludes(html, 'current'))
  assert.ok(htmlIncludes(html, 'View Details'))
  assert.ok(htmlIncludes(html, 'aria-expanded="false"'))
  assert.ok(!htmlIncludes(html, 'Inventory Member'))
  assert.ok(!htmlIncludes(html, 'Members (1)'))
})

test('renders expanded inventory membership, evidence, trust, and freshness on demand', () => {
  const summaryHtml = renderPanel(availableState, {
    initialExpandedInventoryKeys: ['available-inventory'],
  })
  const html = renderPanel(availableState, {
    initialExpandedInventoryKeys: ['available-inventory'],
    initialExpandedInventoryDetailKeys: ['available-inventory:members', 'available-inventory:evidence'],
  })

  assert.ok(htmlIncludes(summaryHtml, 'aria-expanded="true"'))
  assert.ok(htmlIncludes(summaryHtml, 'Hide Details'))
  assert.ok(htmlIncludes(summaryHtml, 'Members (1)'))
  assert.ok(htmlIncludes(summaryHtml, 'View Members'))
  assert.ok(!htmlIncludes(summaryHtml, 'Inventory Member'))
  assert.ok(htmlIncludes(html, 'Inventory Member'))
  assert.ok(htmlIncludes(html, 'Hide Members'))
  assert.ok(htmlIncludes(html, 'Evidence'))
  assert.ok(htmlIncludes(html, 'Hide Evidence'))
  assert.ok(htmlIncludes(html, 'Availability category is Available.'))
  assert.ok(htmlIncludes(html, 'Inventory Freshness'))
  assert.ok(htmlIncludes(html, 'Data Through'))
  assert.ok(htmlIncludes(html, '2026-06-02'))
  assert.ok(htmlIncludes(html, 'Synced'))
  assert.ok(htmlIncludes(html, '2026-06-02T11:55:00Z'))
})

test('renders candidate groups collapsed by default with summaries and metadata visible', () => {
  const html = renderPanel(availableState)

  assert.ok(htmlIncludes(html, 'Available Candidates'))
  assert.ok(htmlIncludes(html, '1 member'))
  assert.ok(htmlIncludes(html, 'Candidates grouped by current availability category.'))
  assert.ok(htmlIncludes(html, 'Source order'))
  assert.ok(htmlIncludes(html, 'neutral source order'))
  assert.ok(htmlIncludes(html, 'Workload Read'))
  assert.ok(htmlIncludes(html, 'medium'))
  assert.ok(htmlIncludes(html, 'Freshness'))
  assert.ok(htmlIncludes(html, 'current'))
  assert.ok(htmlIncludes(html, 'View Details'))
  assert.ok(!htmlIncludes(html, 'Candidate Member'))
  assert.ok(!htmlIncludes(html, 'Group Members (1)'))
  assert.ok(!htmlIncludes(html, 'Eligibility Basis'))
})

test('renders expanded candidate group membership, evidence, freshness, and refusal metadata on demand', () => {
  const candidateDetailState = {
    ...availableState,
    bullpenState: {
      ...availableState.bullpenState,
      candidate_groups: [
        {
          ...availableState.bullpenState.candidate_groups[0],
          eligibility_basis: [
            'availability_status_available',
            'secondary eligibility detail remains inspectable.',
          ],
          explanations: ['Candidate grouping evidence remains inspectable.'],
          limitations: ['Candidate limitation remains inspectable.'],
          refusal_reasons: ['Candidate refusal metadata remains inspectable.'],
          freshness: {
            freshness_state: 'current',
            data_through: '2026-06-02',
            sync_timestamp: '2026-06-02T11:55:00Z',
          },
        },
      ],
    },
  }
  const html = renderPanel(candidateDetailState, {
    initialExpandedCandidateGroupKeys: ['available-candidates'],
    initialExpandedCandidateDetailKeys: [
      'available-candidates:members',
      'available-candidates:eligibility',
      'available-candidates:explanations',
      'available-candidates:limitations',
      'available-candidates:refusal',
    ],
  })
  const summaryHtml = renderPanel(candidateDetailState, {
    initialExpandedCandidateGroupKeys: ['available-candidates'],
  })

  assert.ok(htmlIncludes(summaryHtml, 'aria-expanded="true"'))
  assert.ok(htmlIncludes(summaryHtml, 'Hide Details'))
  assert.ok(htmlIncludes(summaryHtml, 'Group Members (1)'))
  assert.ok(htmlIncludes(summaryHtml, 'View Members'))
  assert.ok(!htmlIncludes(summaryHtml, 'Candidate Member'))
  assert.ok(!htmlIncludes(summaryHtml, 'secondary eligibility detail remains inspectable.'))
  assert.ok(htmlIncludes(html, 'Candidate Member'))
  assert.ok(htmlIncludes(html, 'Hide Members'))
  assert.ok(htmlIncludes(html, 'Eligibility Basis'))
  assert.ok(htmlIncludes(html, 'availability_status_available'))
  assert.ok(htmlIncludes(html, 'secondary eligibility detail remains inspectable.'))
  assert.ok(htmlIncludes(html, 'Hide Eligibility'))
  assert.ok(htmlIncludes(html, 'Group Freshness'))
  assert.ok(htmlIncludes(html, 'Data Through'))
  assert.ok(htmlIncludes(html, '2026-06-02'))
  assert.ok(htmlIncludes(html, 'Synced'))
  assert.ok(htmlIncludes(html, '2026-06-02T11:55:00Z'))
  assert.ok(htmlIncludes(html, 'Candidate grouping evidence remains inspectable.'))
  assert.ok(htmlIncludes(html, 'Candidate limitation remains inspectable.'))
  assert.ok(htmlIncludes(html, 'Candidate refusal metadata remains inspectable.'))
})

test('summarizes team context by default and expands distributions and indicators on demand', () => {
  const teamContextState = {
    ...availableState,
    bullpenState: {
      ...availableState.bullpenState,
      team_context: {
        ...availableState.bullpenState.team_context,
        availability_distribution: {
          green_lane: 2,
          amber_lane: 1,
        },
        workload_distribution: {
          fresh_workload: 1,
          watched_workload: 2,
        },
        readiness_indicators: [
          { message: 'Readiness summary one remains visible.' },
          { message: 'Readiness detail two remains inspectable.' },
        ],
        stress_indicators: [
          { message: 'Stress summary one remains visible.' },
          { message: 'Stress detail two remains inspectable.' },
        ],
      },
    },
  }

  const collapsedHtml = renderPanel(teamContextState)
  const expandedHtml = renderPanel(teamContextState, {
    initialExpandedTeamContextKeys: ['availability', 'workload', 'readiness', 'stress'],
  })

  assert.ok(htmlIncludes(collapsedHtml, '2 categories'))
  assert.ok(htmlIncludes(collapsedHtml, '3 total reported across availability context.'))
  assert.ok(htmlIncludes(collapsedHtml, 'Readiness summary one remains visible.'))
  assert.ok(htmlIncludes(collapsedHtml, 'Stress summary one remains visible.'))
  assert.ok(!htmlIncludes(collapsedHtml, 'Green Lane'))
  assert.ok(!htmlIncludes(collapsedHtml, 'Watched Workload'))
  assert.ok(!htmlIncludes(collapsedHtml, 'Readiness detail two remains inspectable.'))
  assert.ok(!htmlIncludes(collapsedHtml, 'Stress detail two remains inspectable.'))
  assert.ok(htmlIncludes(expandedHtml, 'Green Lane'))
  assert.ok(htmlIncludes(expandedHtml, 'Watched Workload'))
  assert.ok(htmlIncludes(expandedHtml, 'Readiness detail two remains inspectable.'))
  assert.ok(htmlIncludes(expandedHtml, 'Stress detail two remains inspectable.'))
})

test('summarizes structured team context indicators without dumping count objects', () => {
  const structuredContextState = {
    ...availableState,
    bullpenState: {
      ...availableState.bullpenState,
      team_context: {
        ...availableState.bullpenState.team_context,
        readiness_indicators: {
          available_or_monitor_count: 704,
          limited_or_avoid_count: 0,
          confidence_counts: {
            high: 0,
            low: 704,
          },
        },
        stress_indicators: {
          stress_level: 'elevated',
          stale_missing_or_incomplete_count: 704,
          stress_basis: 'availability_status_data_state_and_workload_inputs',
        },
      },
    },
  }

  const collapsedHtml = renderPanel(structuredContextState)
  const expandedHtml = renderPanel(structuredContextState, {
    initialExpandedTeamContextKeys: ['readiness', 'stress'],
  })

  assert.ok(htmlIncludes(collapsedHtml, '3 indicators'))
  assert.ok(htmlIncludes(collapsedHtml, 'Available Or On Watch Count: 704'))
  assert.ok(htmlIncludes(collapsedHtml, 'Stress Level: elevated'))
  assert.ok(htmlIncludes(collapsedHtml, 'View Indicators'))
  assert.ok(!htmlIncludes(collapsedHtml, 'Confidence Counts Low: 704'))
  assert.ok(!htmlIncludes(collapsedHtml, 'Stress Basis: availability_status_data_state_and_workload_inputs'))
  assert.ok(htmlIncludes(expandedHtml, 'Confidence Counts Low: 704'))
  assert.ok(htmlIncludes(expandedHtml, 'Stress Basis: availability_status_data_state_and_workload_inputs'))
})

test('summarizes long limitation, explanation, and refusal lists until expanded', () => {
  const verboseMessageState = {
    ...availableState,
    limitations: [
      { message: 'Limitation summary one remains visible.' },
      { message: 'Limitation detail two remains inspectable.' },
    ],
    explanations: [
      { message: 'Explanation summary one remains visible.' },
      { message: 'Explanation detail two remains inspectable.' },
    ],
    refusalReasons: [
      { message: 'Refusal summary one remains visible.' },
      { message: 'Refusal detail two remains inspectable.' },
    ],
  }

  const collapsedHtml = renderPanel(verboseMessageState)
  const expandedHtml = renderPanel(verboseMessageState, {
    initialExpandedMessageSections: ['limitations', 'explanations', 'refusal'],
  })

  assert.ok(htmlIncludes(collapsedHtml, '2 entries. First: Limitation summary one remains visible.'))
  assert.ok(htmlIncludes(collapsedHtml, '2 entries. First: Explanation summary one remains visible.'))
  assert.ok(htmlIncludes(collapsedHtml, '2 entries. First: Refusal summary one remains visible.'))
  assert.ok(!htmlIncludes(collapsedHtml, 'Limitation detail two remains inspectable.'))
  assert.ok(!htmlIncludes(collapsedHtml, 'Explanation detail two remains inspectable.'))
  assert.ok(!htmlIncludes(collapsedHtml, 'Refusal detail two remains inspectable.'))
  assert.ok(htmlIncludes(expandedHtml, 'Limitation detail two remains inspectable.'))
  assert.ok(htmlIncludes(expandedHtml, 'Explanation detail two remains inspectable.'))
  assert.ok(htmlIncludes(expandedHtml, 'Refusal detail two remains inspectable.'))
})

test('keeps high-volume inventory short until mobile users expand details', () => {
  const makeMembers = (prefix, count) => Array.from({ length: count }, (_, index) => ({
    pitcher_id: `${prefix}-${index + 1}`,
    display_name: `${prefix} Pitcher ${String(index + 1).padStart(3, '0')}`,
  }))
  const highVolumeState = {
    ...availableState,
    bullpenState: {
      ...availableState.bullpenState,
      inventory_summary: [
        {
          inventory_type: 'available_inventory',
          label: 'Available Inventory',
          count: 266,
          members: makeMembers('Available', 266),
          evidence: ['Available inventory contains current availability evidence.'],
          limitations: [],
          freshness: { freshness_state: 'current', data_through: '2026-06-02' },
          confidence: 'medium',
        },
        {
          inventory_type: 'monitor_inventory',
          label: 'Monitor Inventory',
          count: 284,
          members: makeMembers('On Watch', 284),
          evidence: ['On Watch inventory contains current availability evidence.'],
          limitations: [],
          freshness: { freshness_state: 'current', data_through: '2026-06-02' },
          confidence: 'medium',
        },
        {
          inventory_type: 'limited_inventory',
          label: 'Limited Inventory',
          count: 88,
          members: makeMembers('Limited', 88),
          evidence: ['Limited inventory contains current availability evidence.'],
          limitations: [],
          freshness: { freshness_state: 'current', data_through: '2026-06-02' },
          confidence: 'medium',
        },
      ],
      candidate_groups: [],
    },
  }

  const collapsedText = visibleText(renderPanel(highVolumeState))
  const expandedText = visibleText(renderPanel(highVolumeState, {
    initialExpandedInventoryKeys: ['available-inventory', 'monitor-inventory', 'limited-inventory'],
    initialExpandedInventoryDetailKeys: [
      'available-inventory:members',
      'monitor-inventory:members',
      'limited-inventory:members',
    ],
  }))
  const outerExpandedText = visibleText(renderPanel(highVolumeState, {
    initialExpandedInventoryKeys: ['available-inventory', 'monitor-inventory', 'limited-inventory'],
  }))
  const reduction = 1 - (collapsedText.length / expandedText.length)

  assert.ok(htmlIncludes(collapsedText, '266 Available'))
  assert.ok(htmlIncludes(collapsedText, '284 On Watch'))
  assert.ok(htmlIncludes(collapsedText, '88 Limited'))
  assert.ok(!htmlIncludes(collapsedText, 'Available Pitcher 001'))
  assert.ok(htmlIncludes(outerExpandedText, 'View Members'))
  assert.ok(!htmlIncludes(outerExpandedText, 'Available Pitcher 001'))
  assert.ok(htmlIncludes(expandedText, 'Available Pitcher 001'))
  assert.ok(htmlIncludes(expandedText, 'On Watch Pitcher 284'))
  assert.ok(htmlIncludes(expandedText, 'Limited Pitcher 088'))
  assert.ok(reduction >= 0.8, `expected at least 80% initial inventory text reduction, got ${Math.round(reduction * 100)}%`)
})

test('keeps high-volume intelligence surfaces short until mobile users expand details', () => {
  const makeCandidates = (count) => Array.from({ length: count }, (_, index) => ({
    pitcher_id: `candidate-${index + 1}`,
    display_name: `Candidate Pitcher ${String(index + 1).padStart(3, '0')}`,
  }))
  const makeMessages = (prefix, count) => Array.from({ length: count }, (_, index) => ({
    message: `${prefix} detail ${String(index + 1).padStart(2, '0')} remains inspectable.`,
  }))
  const highVolumeState = {
    ...availableState,
    limitations: makeMessages('Limitation', 30),
    explanations: makeMessages('Explanation', 30),
    refusalReasons: makeMessages('Refusal', 30),
    bullpenState: {
      ...availableState.bullpenState,
      candidate_groups: [
        {
          ...availableState.bullpenState.candidate_groups[0],
          candidate_count: 160,
          candidates: makeCandidates(160),
          eligibility_basis: makeMessages('Eligibility', 25),
          explanations: makeMessages('Candidate explanation', 25),
          limitations: makeMessages('Candidate limitation', 25),
          refusal_reasons: makeMessages('Candidate refusal', 25),
        },
      ],
      team_context: {
        ...availableState.bullpenState.team_context,
        availability_distribution: {
          green_lane: 50,
          amber_lane: 40,
          slate_lane: 30,
          white_lane: 20,
        },
        workload_distribution: {
          fresh_workload: 60,
          watched_workload: 40,
          limited_workload: 20,
          unavailable_workload: 10,
        },
        readiness_indicators: makeMessages('Readiness', 20),
        stress_indicators: makeMessages('Stress', 20),
      },
    },
  }

  const collapsedText = visibleText(renderPanel(highVolumeState))
  const expandedText = visibleText(renderPanel(highVolumeState, {
    initialExpandedCandidateGroupKeys: ['available-candidates'],
    initialExpandedCandidateDetailKeys: [
      'available-candidates:members',
      'available-candidates:eligibility',
      'available-candidates:explanations',
      'available-candidates:limitations',
      'available-candidates:refusal',
    ],
    initialExpandedTeamContextKeys: ['availability', 'workload', 'readiness', 'stress'],
    initialExpandedMessageSections: ['limitations', 'explanations', 'refusal'],
  }))
  const outerExpandedText = visibleText(renderPanel(highVolumeState, {
    initialExpandedCandidateGroupKeys: ['available-candidates'],
  }))
  const reduction = 1 - (collapsedText.length / expandedText.length)

  assert.ok(htmlIncludes(collapsedText, '160 members'))
  assert.ok(htmlIncludes(collapsedText, '4 categories'))
  assert.ok(htmlIncludes(collapsedText, '30 entries. First: Limitation detail 01 remains inspectable.'))
  assert.ok(!htmlIncludes(collapsedText, 'Candidate Pitcher 001'))
  assert.ok(!htmlIncludes(collapsedText, 'Green Lane'))
  assert.ok(!htmlIncludes(collapsedText, 'Readiness detail 20 remains inspectable.'))
  assert.ok(!htmlIncludes(collapsedText, 'Refusal detail 30 remains inspectable.'))
  assert.ok(htmlIncludes(outerExpandedText, 'View Members'))
  assert.ok(htmlIncludes(outerExpandedText, 'View Eligibility'))
  assert.ok(htmlIncludes(outerExpandedText, 'View Refusal'))
  assert.ok(!htmlIncludes(outerExpandedText, 'Candidate Pitcher 001'))
  assert.ok(!htmlIncludes(outerExpandedText, 'Eligibility detail 25 remains inspectable.'))
  assert.ok(!htmlIncludes(outerExpandedText, 'Candidate refusal detail 25 remains inspectable.'))
  assert.ok(htmlIncludes(expandedText, 'Candidate Pitcher 001'))
  assert.ok(htmlIncludes(expandedText, 'Candidate Pitcher 160'))
  assert.ok(htmlIncludes(expandedText, 'Eligibility detail 25 remains inspectable.'))
  assert.ok(htmlIncludes(expandedText, 'Candidate refusal detail 25 remains inspectable.'))
  assert.ok(htmlIncludes(expandedText, 'Green Lane'))
  assert.ok(htmlIncludes(expandedText, 'Readiness detail 20 remains inspectable.'))
  assert.ok(htmlIncludes(expandedText, 'Refusal detail 30 remains inspectable.'))
  assert.ok(reduction >= 0.8, `expected at least 80% initial intelligence text reduction, got ${Math.round(reduction * 100)}%`)
})

test('uses container-aware V2 layout classes for desktop readability', () => {
  const html = renderPanel(availableState)

  assert.ok(htmlIncludes(html, 'v2-governed-panel'))
  assert.ok(htmlIncludes(html, 'v2-governed-panel__metadata-grid'))
  assert.ok(htmlIncludes(html, 'v2-governed-panel__message-grid'))
  assert.ok(htmlIncludes(html, 'v2-governed-panel__text'))
  assert.equal(panelSource.includes('lg:grid-cols-3'), false)
  assert.equal(panelSource.includes('lg:grid-cols-2'), false)
  assert.equal(panelSource.includes('md:grid-cols-2'), false)
  assert.equal(panelSource.includes('md:grid-cols-3'), false)
})

test('renders mobile and accessibility anchors for governed V2 metadata', () => {
  const html = renderPanel(availableState)

  assert.ok(htmlIncludes(html, 'aria-labelledby="recommendation-v2-heading"'))
  assert.ok(htmlIncludes(html, 'aria-describedby="recommendation-v2-description"'))
  assert.ok(htmlIncludes(html, 'id="recommendation-v2-heading"'))
  assert.ok(htmlIncludes(html, 'id="recommendation-v2-governance"'))
  assert.ok(htmlIncludes(html, 'id="recommendation-v2-trust"'))
  assert.ok(htmlIncludes(html, 'id="recommendation-v2-freshness"'))
  assert.ok(htmlIncludes(html, 'id="recommendation-v2-limitations"'))
  assert.ok(htmlIncludes(html, 'id="recommendation-v2-explanations"'))
  assert.ok(htmlIncludes(html, 'id="recommendation-v2-refusal"'))
  assert.ok(htmlIncludes(html, 'aria-label="Bullpen intelligence state: Available"'))
  assert.ok(htmlIncludes(html, 'aria-live="polite"'))
  assert.ok(htmlIncludes(html, 'aria-atomic="true"'))
  assert.ok(cssSource.includes('button:focus-visible'))
  assert.ok(cssSource.includes('[tabindex]:focus-visible'))
  assert.ok(cssSource.includes('.v2-governed-panel__metadata-grid > *'))
})

test('renders fail-closed state with refusal metadata visible', () => {
  const failClosedState = {
    ...availableState,
    contractState: 'fail_closed',
    isFailClosed: true,
    confidence: 'low',
    dataState: 'stale',
    freshness: {
      sync_timestamp: '2026-06-03T07:44:27',
      data_through: '2026-06-02',
      freshness_state: 'stale',
      source_freshness_status: 'stale',
      aggregate_v2_freshness_status: 'stale',
      overall_sync_status: 'success',
      overall_sync_current: true,
      stale_warning: 'Some source evidence is stale.',
      missing_data_warning: null,
    },
    statusMetadata: {
      overall_sync_status: 'success',
      overall_sync_current: true,
      sync_timestamp: '2026-06-03T07:44:27',
      sync_data_through: '2026-06-02',
      source_freshness_status: 'stale',
      aggregate_v2_freshness_status: 'stale',
      fail_closed_state: 'degraded',
      fail_closed_reason_code: 'data_state_stale',
      reason_summary: 'Source freshness is stale. Full output is withheld while degraded context remains visible.',
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
    failClosed: {
      failed_closed: true,
      state: 'degraded',
      critical_failure: false,
      safe_partial_output_allowed: true,
      partial_context_safe: true,
      reason_codes: ['data_state_stale'],
      primary_reason_code: 'data_state_stale',
      reason_summary: 'Source freshness is stale. Full output is withheld while degraded context remains visible.',
      display_label: 'Unavailable - freshness failed',
      withheld_summary: 'Current-state interpretation is withheld; degraded context remains visible with refusal metadata.',
      trust_failed: false,
      freshness_failed: true,
    },
    bullpenState: null,
    refusalReasons: [
      {
        refusal_id: 'stale_freshness',
        reason: 'data_state_stale',
        message: 'Context is degraded or refused because source data state is stale.',
        applies_to: 'bullpen_state',
      },
    ],
  }

  const view = getRecommendationV2BullpenStateView(failClosedState)
  const html = renderPanel(failClosedState)

  assert.equal(view.statusLabel, 'Unavailable - freshness failed')
  assert.ok(htmlIncludes(html, 'Unavailable - freshness failed'))
  assert.ok(htmlIncludes(html, 'Withheld state'))
  assert.ok(htmlIncludes(html, 'degraded'))
  assert.ok(htmlIncludes(html, 'Source reason'))
  assert.ok(htmlIncludes(html, 'data_state_stale'))
  assert.ok(htmlIncludes(html, 'Source freshness is stale.'))
  assert.ok(htmlIncludes(html, '2026-06-03T07:44:27'))
  assert.ok(htmlIncludes(html, 'Source Freshness'))
  assert.ok(htmlIncludes(html, 'Bullpen Freshness'))
  assert.ok(htmlIncludes(html, 'Overall Sync'))
  assert.ok(htmlIncludes(html, 'Visibility check'))
  assert.ok(htmlIncludes(html, 'false'))
  assert.ok(htmlIncludes(html, 'Freshness check'))
  assert.ok(htmlIncludes(html, 'true'))
  assert.ok(htmlIncludes(html, 'Partial context'))
  assert.ok(htmlIncludes(html, 'Team order'))
  assert.ok(htmlIncludes(html, 'Pitcher choice'))
  assert.ok(htmlIncludes(html, 'No ordering made'))
  assert.ok(htmlIncludes(html, 'No pitcher chosen'))
  assert.ok(htmlIncludes(html, 'Some source evidence is stale.'))
  assert.ok(htmlIncludes(html, 'role="alert"'))
  assert.ok(htmlIncludes(html, 'aria-live="assertive"'))
  assert.ok(htmlIncludes(html, 'Refusal'))
  assert.ok(htmlIncludes(html, 'Context is degraded or refused because source data state is stale.'))
  assert.ok(htmlIncludes(html, 'No inventory summary available.'))
  assert.ok(htmlIncludes(html, 'No neutral groups are available from the current bullpen context.'))
  assert.ok(!htmlIncludes(html, 'V2 declined full bullpen-state output'))
  assert.ok(!htmlIncludes(html, 'broken'))
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

  assert.ok(htmlIncludes(html, 'Bullpen Context Withheld'))
  assert.ok(htmlIncludes(html, 'role="alert"'))
  assert.ok(htmlIncludes(html, 'aria-live="assertive"'))
  assert.ok(htmlIncludes(html, 'Diagnostics detected: 3'))
  assert.ok(htmlIncludes(html, 'The bullpen context is withheld from this surface.'))
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

test('view model allows negative governance disclaimers in metadata', () => {
  const disclaimerState = {
    ...availableState,
    limitations: [
      ...availableState.limitations,
      {
        limitation_id: 'not_performance_forecast',
        message: 'Not a performance forecast.',
        severity: 'informational',
        applies_to: 'recommendation_context',
      },
    ],
    explanations: [
      ...availableState.explanations,
      {
        explanation_id: 'no_automated_decision',
        message: 'Context was assembled from existing evidence without ranking or selection.',
        applies_to: 'bullpen_state',
      },
      {
        explanation_id: 'missing_workload_history',
        message: 'Missing recent workload history.',
        applies_to: 'bullpen_state',
      },
    ],
  }

  const view = getRecommendationV2BullpenStateView(disclaimerState)
  const html = renderPanel(disclaimerState, {
    initialExpandedMessageSections: ['limitations', 'explanations'],
  })

  assert.equal(view.contractState, 'available')
  assert.equal(view.hiddenUnsafeLanguage, false)
  assert.ok(htmlIncludes(html, 'Not a performance forecast.'))
  assert.ok(htmlIncludes(html, 'without ranking or selection.'))
  assert.ok(htmlIncludes(html, 'Missing recent workload history.'))
  assert.ok(htmlIncludes(html, 'Trust'))
  assert.ok(htmlIncludes(html, 'Freshness'))
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

  assert.ok(htmlIncludes(loadingHtml, 'Loading bullpen intelligence...'))
  assert.ok(htmlIncludes(loadingHtml, 'role="status"'))
  assert.ok(htmlIncludes(loadingHtml, 'aria-busy="true"'))
  assert.ok(htmlIncludes(errorHtml, 'Bullpen intelligence could not be loaded.'))
  assert.ok(htmlIncludes(errorHtml, 'role="alert"'))
  assert.ok(!htmlIncludes(errorHtml, 'network unavailable'))
})

test('Dashboard imports cleanly with the governed V2 panel dependency', () => {
  assert.equal(typeof Dashboard, 'function')
})
