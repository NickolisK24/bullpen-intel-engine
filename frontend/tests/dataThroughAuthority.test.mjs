import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import { makeBoard } from './fixtures/bullpenBoardFixtures.mjs'
import { makeComparison } from './fixtures/bullpenComparisonFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { DashboardView } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')
const { IntelligenceSurfaceView } = await server.ssrLoadModule('/src/components/home/IntelligenceSurface.jsx')
const { StoriesView } = await server.ssrLoadModule('/src/components/stories/Stories.jsx')
const { DataTrustView } = await server.ssrLoadModule('/src/components/trust/DataTrust.jsx')
const { SidebarDataFreshnessCard, sidebarFreshness } = await server.ssrLoadModule('/src/components/Sidebar.jsx')
const { default: BullpenBoardView } = await server.ssrLoadModule('/src/components/bullpen/board/BullpenBoardView.jsx')
const { default: BullpenComparisonView } = await server.ssrLoadModule('/src/components/bullpen/board/BullpenComparisonView.jsx')

const render = (element) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, element),
)

const fetchState = (data) => ({
  data,
  loading: false,
  error: null,
  staleWithError: false,
  refetch: () => {},
})

const servedFreshness = {
  data_through: '2026-06-16',
  latest_workload_date: '2026-06-16',
  last_successful_sync: '2026-06-17T11:42:26.740902',
  sync_status: 'success',
  is_current: true,
  is_stale: false,
  freshness_state: 'current',
  label: 'Current baseball data through 2026-06-16.',
  limitations: [],
}

const syncAhead = {
  status: 'success',
  last_sync: '2026-06-17T12:00:00',
  last_successful_sync: '2026-06-17T12:00:00',
  pitchers_updated: 428,
  data: {
    game_logs: 36000,
    latest_game_date: '2026-06-17',
    latest_workload_date: '2026-06-17',
    latest_fatigue_calculated_at: '2026-06-17T12:00:00',
  },
  freshness: {
    is_current: true,
    is_stale: false,
    freshness_state: 'current',
    label: 'Current baseball data through 2026-06-17.',
    limitations: [],
  },
}

const syncAheadIncomplete = {
  ...syncAhead,
  freshness: {
    is_current: false,
    is_stale: false,
    freshness_state: 'limited',
    label: 'Baseball data through 2026-06-17 is incomplete and is not publishable as current.',
    limitations: ['Missing completed-game coverage for the checked date.'],
    reason_codes: ['slate_log_coverage_incomplete'],
  },
}

const dashboard = {
  capability: 'bullpen_dashboard',
  context: makeBoard({
    cardsByStatus: {
      Available: [{ pitcher_id: 1, name: 'Clean Arm', availability_status: 'Available' }],
    },
    freshness: servedFreshness,
  }).context,
  roles: { order: [], counts: {}, total: 1 },
  freshness: servedFreshness,
  landscape: { teams_evaluated: 0, games: {}, constrained_bullpens: [], available_bullpens: [], monitoring_concentration: [] },
  four_beat_stories: { capability: 'four_beat_story_template_v1', enabled: true, items: [], fallback: 'No bullpen stories today.' },
}

const board = makeBoard({
  cardsByStatus: {
    Available: [{ pitcher_id: 2, name: 'Board Arm', availability_status: 'Available' }],
  },
  freshness: servedFreshness,
})

const comparison = makeComparison(
  {
    team: { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' },
    counts: { Available: 2 },
    freshness: servedFreshness,
  },
  {
    team: { team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA' },
    counts: { Available: 2 },
    freshness: servedFreshness,
  },
)

const expectedLine = 'Updated after completed games through Jun 16, 2026'
const syncAheadLine = 'Updated after completed games through Jun 17, 2026'
const todayExpectedLine = 'Published view through Jun 16'
const todaySyncAheadLine = 'Published view through Jun 17'

function assertUsesServedFreshness(surface, html) {
  assert.ok(html.includes(expectedLine), `${surface} did not show served freshness data-through`)
  assert.equal(html.includes(syncAheadLine), false, `${surface} leaked raw sync data-through`)
}

test('user-facing data-through surfaces use served freshness when sync is ahead of publish', () => {
  const surfaces = {
    'Data & Trust': render(React.createElement(DataTrustView, {
      backtest: fetchState(null),
      dashboard: fetchState(dashboard),
      overview: fetchState(null),
      sync: fetchState(syncAhead),
      v2BullpenState: fetchState(null),
      teamOperationsReadiness: fetchState(null),
    })),
    Dashboard: render(React.createElement(DashboardView, { data: dashboard })),
    Today: render(React.createElement(IntelligenceSurfaceView, {
      intelligence: {
        status: 'empty',
        reference_date: servedFreshness.data_through,
        empty_reason: 'lead_story_unavailable',
      },
      dashboard,
      landscape: dashboard.landscape,
    })),
    Stories: render(React.createElement(StoriesView, { dashboard })),
    Bullpen: render(React.createElement(BullpenBoardView, { board })),
    Comparison: render(React.createElement(BullpenComparisonView, { payload: comparison })),
    Sidebar: render(React.createElement(SidebarDataFreshnessCard, {
      freshness: sidebarFreshness(syncAhead, false, null, servedFreshness),
    })),
  }

  for (const [surface, html] of Object.entries(surfaces)) {
    if (surface === 'Today') {
      assert.ok(html.includes('Published view current'), `${surface} did not label the published view as current`)
      assert.equal(html.includes('Freshness: Current'), false, `${surface} used generic current freshness copy`)
      assert.ok(html.includes(todayExpectedLine), `${surface} did not show served freshness data-through`)
      assert.equal(html.includes(todaySyncAheadLine), false, `${surface} leaked raw sync data-through`)
    } else if (surface === 'Sidebar') {
      assert.ok(html.includes('Bullpen data through'), `${surface} did not label public data-through`)
      assert.ok(html.includes('June 16, 2026'), `${surface} did not show served freshness data-through`)
      assert.equal(html.includes('June 17, 2026'), false, `${surface} leaked raw sync data-through`)
    } else {
      assertUsesServedFreshness(surface, html)
    }
  }
})

test('Data & Trust separates public data-through from a newer incomplete checked date', () => {
  const html = render(React.createElement(DataTrustView, {
    backtest: fetchState(null),
    dashboard: fetchState(dashboard),
    overview: fetchState(null),
    sync: fetchState(syncAheadIncomplete),
    v2BullpenState: fetchState(null),
    teamOperationsReadiness: fetchState(null),
  }))

  assert.ok(html.includes('June 16, 2026'), 'public data-through date was not rendered')
  assert.ok(html.includes('Public bullpen data remains through June 16, 2026.'))
  assert.ok(html.includes('Latest checked baseball date June 17, 2026 is not publishable yet.'))
  assert.ok(html.includes('Baseball data through 2026-06-17 is incomplete and is not publishable as current.'))
})
