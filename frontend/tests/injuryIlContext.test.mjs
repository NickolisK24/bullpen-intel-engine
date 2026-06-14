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

const { DashboardView } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')
const {
  normalizeInjuryIlContext,
} = await server.ssrLoadModule('/src/components/dashboard/injuryIlContextView.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const inRouter = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

const board = makeBoard({
  cardsByStatus: {
    Available: Array.from({ length: 4 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
    Monitor: Array.from({ length: 2 }, (_, i) => ({ pitcher_id: 20 + i, name: `M${i}`, availability_status: 'Monitor' })),
    Limited: [],
    Avoid: [],
    Unavailable: [],
  },
})

const dashboardData = {
  capability: 'bullpen_dashboard',
  context: board.context,
  freshness: {
    data_through: '2026-06-04',
    last_successful_sync: '2026-06-04T12:00:00+00:00',
    is_current: true,
    sync_status: 'success',
  },
  roles: {
    order: ['late_high_leverage', 'setup_bridge', 'middle_relief', 'long_multi_inning', 'low_unclear', 'insufficient_data'],
    counts: { late_high_leverage: 1, setup_bridge: 2, middle_relief: 2, long_multi_inning: 1, low_unclear: 0, insufficient_data: 0 },
    total: 6,
  },
}

const injuryIlContext = {
  capability: 'injury_il_context_v1',
  ranking_applied: false,
  prediction_applied: false,
  selection_made: false,
  league: {
    injured_list_count: 9,
    inactive_count: 6,
    teams_with_multiple_unavailable: 4,
    tracked_pitchers_count: 240,
  },
  followed_team: {
    team_id: 135,
    team_name: 'Padres',
    injured_list_count: 1,
    inactive_count: 1,
    unavailable_pitchers: [
      { player_id: 1001, name: 'Padres IL Arm', status: 'IL_15', status_label: 'IL-15', status_group: 'injured_list' },
      { player_id: 1002, name: 'Padres Optioned Arm', status: 'OPTIONED', status_label: 'Optioned', status_group: 'inactive_roster' },
    ],
  },
  limitations: [
    'Roster status context is explanatory and does not change workload availability classifications.',
  ],
}

test('injury il context normalizes the dashboard payload', () => {
  const view = normalizeInjuryIlContext({
    injury_il_context: injuryIlContext,
  })

  assert.equal(view.league.injuredListCount, 9)
  assert.equal(view.league.inactiveCount, 6)
  assert.equal(view.league.teamsWithMultipleUnavailable, 4)
  assert.equal(view.league.trackedPitchersCount, 240)
  assert.equal(view.followedTeam.teamName, 'Padres')
  assert.equal(view.rankingApplied, false)
  assert.equal(view.predictionApplied, false)
})

test('dashboard renders compact league injury il context', () => {
  const html = inRouter(React.createElement(DashboardView, {
    data: { ...dashboardData, injury_il_context: injuryIlContext },
  }))

  assert.ok(htmlIncludes(html, 'Injury / IL Context'))
  assert.ok(htmlIncludes(html, 'Injured List'))
  assert.ok(htmlIncludes(html, 'Inactive Roster'))
  assert.ok(htmlIncludes(html, '2+ Unavailable'))
  assert.ok(htmlIncludes(html, '240 tracked arms'))
  assert.ok(htmlIncludes(html, 'Availability classifications are workload-based.'))
})

test('dashboard renders followed team unavailable pitcher context when present', () => {
  const html = inRouter(React.createElement(DashboardView, {
    data: { ...dashboardData, injury_il_context: injuryIlContext },
  }))

  assert.ok(htmlIncludes(html, 'Followed Team'))
  assert.ok(htmlIncludes(html, 'Padres'))
  assert.ok(htmlIncludes(html, 'Padres IL Arm'))
  assert.ok(htmlIncludes(html, 'Padres Optioned Arm'))
})

test('dashboard suppresses injury il section when payload is missing', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))

  assert.ok(!htmlIncludes(html, 'Injury / IL Context'))
  assert.ok(!htmlIncludes(html, 'Availability classifications are workload-based.'))
})

test('dashboard suppresses injury il section when league context is unusable', () => {
  const html = inRouter(React.createElement(DashboardView, {
    data: { ...dashboardData, injury_il_context: { capability: 'injury_il_context_v1' } },
  }))

  assert.ok(!htmlIncludes(html, 'Injury / IL Context'))
})
