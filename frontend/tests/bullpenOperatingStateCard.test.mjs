import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import { makeBoard } from './fixtures/bullpenBoardFixtures.mjs'

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
  default: BullpenOperatingStateCard,
  getBullpenOperatingStateView,
} = await server.ssrLoadModule('/src/components/bullpen/BullpenOperatingStateCard.jsx')
const { getBoardContextView } = await server.ssrLoadModule('/src/components/bullpen/board/tonightsBullpenBoardView.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (props) => renderToStaticMarkup(
  React.createElement(
    MemoryRouter,
    null,
    React.createElement(BullpenOperatingStateCard, props),
  ),
)

const currentFreshness = {
  data_through: '2026-06-26',
  last_successful_sync: '2026-06-26T10:04:00Z',
  is_current: true,
  sync_status: 'success',
}

function contextFor(cardsByStatus) {
  return getBoardContextView(makeBoard({ cardsByStatus }))
}

test('renders the current bullpen state in baseball-facing language', () => {
  const context = contextFor({
    Available: Array.from({ length: 8 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
    Monitor: [{ pitcher_id: 20, name: 'M1', availability_status: 'Monitor' }],
  })

  const html = render({
    teamLabel: 'League-Wide',
    context,
    freshness: currentFreshness,
    ctaHref: '/bullpen?view=board',
  })

  assert.ok(htmlIncludes(html, 'Team'))
  assert.ok(htmlIncludes(html, 'League-Wide'))
  assert.ok(htmlIncludes(html, 'Current Bullpen State'))
  assert.ok(htmlIncludes(html, 'Stable'))
  assert.ok(htmlIncludes(html, 'Primary Concern'))
  assert.ok(htmlIncludes(html, 'No clear pressure point'))
  assert.ok(htmlIncludes(html, 'Why BaseballOS Sees This'))
  assert.ok(htmlIncludes(html, 'Bullpen workload appears manageable.'))
  assert.ok(htmlIncludes(html, 'Evidence'))
  assert.ok(htmlIncludes(html, '8 of 9 relievers are classified Available.'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board"'))
})

test('handles missing bullpen data with an honest unavailable state', () => {
  const html = render({ context: null, freshness: null })

  assert.ok(htmlIncludes(html, 'No current bullpen read available.'))
  assert.ok(htmlIncludes(html, 'BaseballOS will show this card when enough current bullpen context is available.'))
  assert.ok(htmlIncludes(html, 'Freshness unavailable'))
})

test('omits concern rows when count fields are missing', () => {
  const html = render({
    context: {
      hasContext: true,
      state: 'manageable',
      label: 'Bullpen workload appears manageable.',
      reasons: ['Availability read is present, but lane counts were not included.'],
      limitations: [],
    },
    freshness: currentFreshness,
  })

  assert.ok(htmlIncludes(html, 'Current Bullpen State'))
  assert.ok(htmlIncludes(html, 'Stable'))
  assert.ok(!htmlIncludes(html, 'Primary Concern'))
  assert.ok(!htmlIncludes(html, 'Secondary Concern'))
})

test('renders trusted freshness values without inventing per-card freshness', () => {
  const context = contextFor({
    Available: Array.from({ length: 4 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
  })
  const html = render({ context, freshness: currentFreshness })

  assert.ok(htmlIncludes(html, 'Freshness: Current'))
  assert.ok(htmlIncludes(html, 'Data through Jun 26'))
  assert.ok(htmlIncludes(html, 'Last synced 6:04 AM ET'))
})

test('renders stale and sample freshness as distinct trust states', () => {
  const context = contextFor({
    Available: Array.from({ length: 3 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
    Limited: [{ pitcher_id: 50, name: 'L1', availability_status: 'Limited' }],
  })

  const stale = render({
    context,
    freshness: {
      data_through: '2026-06-25',
      last_successful_sync: '2026-06-25T10:04:00Z',
      is_current: false,
      is_stale: true,
      sync_status: 'failed',
    },
    staleWithError: true,
  })
  assert.ok(htmlIncludes(stale, 'Refresh delayed'))
  assert.ok(htmlIncludes(stale, 'showing last loaded data from Jun 25.'))

  const sample = render({
    context,
    freshness: {
      data_through: '2026-06-24',
      freshness_state: 'sample',
      sample: true,
    },
  })
  assert.ok(htmlIncludes(sample, 'Sample intelligence state'))
  assert.ok(htmlIncludes(sample, 'Not live MLB data.'))
})

test('omits internal language from visible card copy', () => {
  const context = {
    hasContext: true,
    state: 'manageable',
    label: 'backend COIN snapshot V2 deterministic endpoint',
    reasons: [
      'The existing snapshot moved after the latest completed games.',
      'COIN endpoint V4 detail should never render.',
      '5 of 8 relievers are classified Available.',
    ],
    limitations: [
      'governance layer detail should never render.',
      'Latest workload data is outside the active freshness window, so this snapshot may not reflect current bullpen planning.',
    ],
    metrics: { total: 8 },
    snapshot: [
      { status: 'Available', label: 'Available', count: 5 },
      { status: 'Monitor', label: 'Monitor', count: 1 },
      { status: 'Limited', label: 'Limited', count: 1 },
      { status: 'Avoid', label: 'Avoid', count: 1 },
      { status: 'Unavailable', label: 'Unavailable', count: 0 },
    ],
  }

  const html = render({ context, freshness: currentFreshness })

  assert.ok(htmlIncludes(html, 'BaseballOS is reading the current bullpen mix from available workload context.'))
  assert.ok(htmlIncludes(html, 'existing bullpen read moved'))
  assert.ok(htmlIncludes(html, '5 of 8 relievers are classified Available.'))
  assert.ok(htmlIncludes(html, 'this bullpen read may not reflect current bullpen planning.'))

  for (const term of [
    'COIN',
    'V2',
    'V3',
    'V4',
    'deterministic',
    'snapshot',
    'endpoint',
    'backend',
    'recommendation engine',
    'baseline distribution',
    'governance layer',
  ]) {
    assert.equal(new RegExp(escapeRegExp(term), 'i').test(html), false, `leaked ${term}`)
  }
})

test('view model exposes only supported operating state labels', () => {
  const view = getBullpenOperatingStateView({
    context: contextFor({
      Available: [{ pitcher_id: 1, name: 'A1', availability_status: 'Available' }],
      Avoid: Array.from({ length: 3 }, (_, i) => ({ pitcher_id: i + 20, name: `X${i}`, availability_status: 'Avoid' })),
    }),
    freshness: currentFreshness,
  })

  assert.equal(view.stateLabel, 'Constrained')
  assert.equal(view.primaryConcern.label, 'Clean options are tight')
})
