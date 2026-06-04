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
  BULLPEN_INTELLIGENCE_OBSERVATIONS_ROUTE,
  getBullpenObservations,
  normalizeBullpenObservationsResponse,
} = await server.ssrLoadModule('/src/utils/api.js')
const {
  default: BullpenIntelligencePanel,
} = await server.ssrLoadModule('/src/components/observations/BullpenIntelligencePanel.jsx')
const { default: Dashboard } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')

const escapeRegExp = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const visibleText = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const withoutGovernanceCopy = html => visibleText(html)
  .replace(/Observations are descriptive only and do not rank, select, or recommend pitchers\./g, '')
  .replace(/ranking_applied === false/g, '')
  .replace(/selection_made === false/g, '')

const baseObservationResponse = {
  capability: 'v5_bullpen_intelligence_surface',
  contract: 'baseballos.v5.observation.domain',
  contract_version: 'v5_phase_4',
  status: 'ok',
  collection_id: 'bullpen-observations:frontend-test',
  generated_at: '2026-06-04T18:00:00Z',
  observation_count: 1,
  observations: [
    {
      capability: 'v5_bullpen_intelligence_surface',
      contract: 'baseballos.v5.observation.domain',
      contract_version: 'v5_phase_4',
      observation_id: 'inventory:test:2026-06-04',
      observation_type: 'inventory',
      family: 'inventory',
      severity: 'informational',
      title: 'Availability inventory contracted since the previous snapshot.',
      summary: 'Availability inventory changed based on trusted platform state.',
      evidence: [
        {
          evidence_id: 'inventory:evidence:2026-06-04',
          source: 'baseballos_v5_test_state',
          source_type: 'trusted_platform_state',
          label: 'Available inventory count',
          value: 5,
          freshness_status: 'current',
          data_through: '2026-06-04',
          generated_at: '2026-06-04T18:00:00Z',
          metadata: { field: 'available_count' },
        },
      ],
      limitations: [
        {
          limitation_type: 'deterministic_sample_state',
          summary: 'Observation is limited to deterministic supplied state.',
          severity: 'informational',
          source: 'v5_phase_7_frontend_surface',
        },
      ],
      confidence: {
        status: 'medium',
        reason: 'Trusted supplied state supports descriptive observation display.',
      },
      freshness: {
        status: 'current',
        data_through: '2026-06-04',
        generated_at: '2026-06-04T18:00:00Z',
      },
      trust_status: 'supported',
      explanation_reference: 'v5.observations.inventory',
      generated_at: '2026-06-04T18:00:00Z',
      ranking_applied: false,
      selection_made: false,
    },
  ],
  freshness: {
    status: 'current',
    data_through: '2026-06-04',
    generated_at: '2026-06-04T18:00:00Z',
  },
  confidence: {
    status: 'medium',
    reason: 'Deterministic sample observations satisfy the frontend contract.',
  },
  limitations: [
    {
      limitation_type: 'deterministic_sample_state',
      summary: 'The API uses deterministic sample state until separate runtime integration is authorized.',
      severity: 'informational',
      source: 'v5_phase_6_observation_api',
    },
  ],
  suppressed_count: 0,
  suppression_reasons: [],
  ranking_applied: false,
  selection_made: false,
  trust_status: 'supported',
  route_metadata: {
    route: '/api/observations',
    read_only: true,
    frontend_exposure: false,
    database_required: false,
  },
}

function renderPanel(state, props = {}) {
  return renderToStaticMarkup(
    React.createElement(BullpenIntelligencePanel, { state, ...props }),
  )
}

test('normalizes governed V5 observations without ranking or selection', () => {
  const view = normalizeBullpenObservationsResponse(baseObservationResponse)

  assert.equal(view.endpoint, BULLPEN_INTELLIGENCE_OBSERVATIONS_ROUTE)
  assert.equal(view.contractState, 'available')
  assert.equal(view.isContractSafe, true)
  assert.equal(view.governance.rankingApplied, false)
  assert.equal(view.governance.selectionMade, false)
  assert.equal(view.observations.length, 1)
  assert.equal(view.observations[0].title, 'Availability inventory contracted since the previous snapshot.')
  assert.deepEqual(view.missingFields, [])
  assert.deepEqual(view.malformedFields, [])
  assert.deepEqual(view.forbiddenFieldPaths, [])
  assert.deepEqual(view.forbiddenTextPaths, [])
})

test('fetches GET /api/observations and returns normalized observation data', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/observations')
    assert.equal(options.method, undefined)
    assert.equal(options.headers['Content-Type'], 'application/json')

    return {
      ok: true,
      json: async () => baseObservationResponse,
    }
  }

  const view = await getBullpenObservations()

  assert.equal(view.contractState, 'available')
  assert.equal(view.governance.rankingApplied, false)
  assert.equal(view.governance.selectionMade, false)
  assert.equal(view.observations[0].evidence[0].source_type, 'trusted_platform_state')
})

test('fails the frontend contract closed for unsafe observation language or fields', () => {
  const unsafeTextView = normalizeBullpenObservationsResponse({
    ...baseObservationResponse,
    observations: [
      {
        ...baseObservationResponse.observations[0],
        title: 'Use this pitcher tonight.',
      },
    ],
  })
  const unsafeFieldView = normalizeBullpenObservationsResponse({
    ...baseObservationResponse,
    selected_pitcher: { pitcher_id: 42 },
  })

  assert.equal(unsafeTextView.contractState, 'unavailable')
  assert.equal(unsafeTextView.isContractSafe, false)
  assert.equal(unsafeTextView.observations.length, 0)
  assert.deepEqual(unsafeTextView.forbiddenTextPaths, ['observations.0.title'])
  assert.equal(unsafeFieldView.contractState, 'unavailable')
  assert.deepEqual(unsafeFieldView.forbiddenFieldPaths, ['selected_pitcher'])
})

test('renders title, summary, evidence, limitations, metadata, and governance copy', () => {
  const state = normalizeBullpenObservationsResponse(baseObservationResponse)
  const html = renderPanel(state)

  assert.ok(htmlIncludes(html, 'V5 Bullpen Intelligence'))
  assert.ok(htmlIncludes(html, 'Governed Observations'))
  assert.ok(htmlIncludes(html, 'Availability inventory contracted since the previous snapshot.'))
  assert.ok(htmlIncludes(html, 'Availability inventory changed based on trusted platform state.'))
  assert.ok(htmlIncludes(html, 'Available inventory count'))
  assert.ok(htmlIncludes(html, 'trusted_platform_state'))
  assert.ok(htmlIncludes(html, 'Observation is limited to deterministic supplied state.'))
  assert.ok(htmlIncludes(html, 'Trust Status'))
  assert.ok(htmlIncludes(html, 'Freshness'))
  assert.ok(htmlIncludes(html, 'Confidence'))
  assert.ok(htmlIncludes(html, 'supported'))
  assert.ok(htmlIncludes(html, 'current'))
  assert.ok(htmlIncludes(html, 'medium'))
  assert.ok(htmlIncludes(html, 'Explanation Reference'))
  assert.ok(htmlIncludes(html, 'v5.observations.inventory'))
  assert.ok(htmlIncludes(html, 'Observations are descriptive only and do not rank, select, or recommend pitchers.'))
  assert.ok(htmlIncludes(html, 'ranking_applied === false'))
  assert.ok(htmlIncludes(html, 'selection_made === false'))
})

test('renders empty and fail-closed states with safe copy', () => {
  const failClosedState = normalizeBullpenObservationsResponse({
    ...baseObservationResponse,
    status: 'fail_closed',
    collection_id: 'bullpen-observations:fail-closed',
    observation_count: 0,
    observations: [],
    trust_status: 'fail_closed',
    freshness: {
      status: 'unavailable',
      reason_code: 'invalid_supplied_state',
      generated_at: '2026-06-04T18:00:00Z',
    },
    confidence: {
      status: 'low',
      reason: 'Observation output is withheld by the API fail-closed boundary.',
    },
    suppressed_count: 1,
    suppression_reasons: ['invalid_supplied_state'],
  })
  const html = renderPanel(failClosedState)

  assert.equal(failClosedState.contractState, 'fail_closed')
  assert.ok(htmlIncludes(html, 'No governed bullpen observations are available from the current trusted state.'))
  assert.ok(htmlIncludes(html, 'Trust Status'))
  assert.ok(htmlIncludes(html, 'fail_closed'))
  assert.ok(htmlIncludes(html, 'unavailable'))
  assert.ok(htmlIncludes(html, 'low'))
  assert.ok(!htmlIncludes(html, 'Availability inventory contracted since the previous snapshot.'))
})

test('handles loading, API failure, and unsafe contract states safely', () => {
  const loadingHtml = renderPanel(null, { loading: true })
  const errorHtml = renderPanel(null, { error: 'network details should not render' })
  const unsafeHtml = renderPanel(normalizeBullpenObservationsResponse({
    ...baseObservationResponse,
    ranking_applied: true,
  }))

  assert.ok(htmlIncludes(loadingHtml, 'Loading governed bullpen observations...'))
  assert.ok(htmlIncludes(loadingHtml, 'role="status"'))
  assert.ok(htmlIncludes(errorHtml, 'Bullpen observations could not be loaded safely.'))
  assert.ok(!htmlIncludes(errorHtml, 'network details should not render'))
  assert.ok(htmlIncludes(unsafeHtml, 'Bullpen observations unavailable'))
  assert.ok(htmlIncludes(unsafeHtml, 'Observation details are withheld'))
  assert.ok(!htmlIncludes(unsafeHtml, 'Availability inventory contracted since the previous snapshot.'))
})

test('does not render prohibited recommendation language or ranking and selection controls', () => {
  const html = renderPanel(normalizeBullpenObservationsResponse(baseObservationResponse))
  const text = withoutGovernanceCopy(html)

  assert.equal(/\bbest\b/i.test(text), false)
  assert.equal(/\bpreferred\b/i.test(text), false)
  assert.equal(/\brecommended arm\b/i.test(text), false)
  assert.equal(/\buse this pitcher\b/i.test(text), false)
  assert.equal(/\bmanager should\b/i.test(text), false)
  assert.equal(/\bmatchup advantage\b/i.test(text), false)
  assert.equal(/\bsetup choice\b/i.test(text), false)
  assert.equal(htmlIncludes(html, '<select'), false)
  assert.equal(htmlIncludes(html, 'Choose Pitcher'), false)
  assert.equal(htmlIncludes(html, 'Ranking Controls'), false)
  assert.equal(htmlIncludes(html, 'Selection Controls'), false)
})

test('Dashboard imports cleanly with the V5 Bullpen Intelligence surface dependency', () => {
  assert.equal(typeof Dashboard, 'function')
})
