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
const { default: Bullpen } = await server.ssrLoadModule('/src/components/bullpen/Bullpen.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const inRouter = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

const board = makeBoard({
  cardsByStatus: {
    Available: Array.from({ length: 5 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
    Monitor: Array.from({ length: 3 }, (_, i) => ({ pitcher_id: 20 + i, name: `M${i}`, availability_status: 'Monitor' })),
    Limited: Array.from({ length: 2 }, (_, i) => ({ pitcher_id: 40 + i, name: `L${i}`, availability_status: 'Limited' })),
  },
})
const dashboardData = {
  capability: 'bullpen_dashboard',
  context: board.context,
  freshness: { data_through: '2026-06-04', last_successful_sync: '2026-06-04T12:00:00+00:00', is_current: true, sync_status: 'success' },
  roles: {
    order: ['late_high_leverage', 'setup_bridge', 'middle_relief', 'long_multi_inning', 'low_unclear', 'insufficient_data'],
    counts: { late_high_leverage: 2, setup_bridge: 3, middle_relief: 4, long_multi_inning: 1, low_unclear: 0, insufficient_data: 0 },
    total: 10,
  },
}

const renderDashboard = () => inRouter(React.createElement(DashboardView, { data: dashboardData }))

test('hero states the dashboard is a league-wide / MLB-wide view', () => {
  const html = renderDashboard()
  assert.ok(htmlIncludes(html, 'League-Wide Bullpen Overview'))
  assert.ok(htmlIncludes(html, 'All tracked MLB bullpens'))      // scope chip
  assert.ok(htmlIncludes(html, 'all tracked MLB bullpens'))      // subtitle
  // It points the user to the team-specific section for a single pen.
  assert.ok(htmlIncludes(html, 'for a single team'))
})

test('snapshot is scoped to all tracked MLB bullpens', () => {
  const html = renderDashboard()
  assert.ok(htmlIncludes(html, 'League-Wide Bullpen Snapshot'))
  assert.ok(htmlIncludes(html, 'relievers across all tracked MLB bullpens'))
})

test('bullpen health is clearly league-wide, not a single team', () => {
  const html = renderDashboard()
  assert.ok(htmlIncludes(html, 'League-Wide Bullpen Health'))
  assert.ok(htmlIncludes(html, 'not a single team'))
  // The aggregate statement itself carries a league-wide qualifier inline.
  assert.ok(htmlIncludes(html, 'League-Wide · Workload Read:'))
})

test('usage roles are described as a league-wide distribution', () => {
  const html = renderDashboard()
  assert.ok(htmlIncludes(html, 'League-Wide Usage Roles'))
  assert.ok(htmlIncludes(html, 'across all tracked MLB bullpens'))
})

test('quick actions reinforce the league -> team / matchup / pitcher hierarchy', () => {
  const html = renderDashboard()
  assert.ok(htmlIncludes(html, 'drill into a single team'))
  assert.ok(htmlIncludes(html, 'One team\'s bullpen tonight') || htmlIncludes(html, 'One team&#x27;s bullpen tonight'))
  assert.ok(htmlIncludes(html, 'Two teams, side-by-side'))
})

test('existing realignment headings remain (substrings preserved for stability)', () => {
  const html = renderDashboard()
  for (const heading of ['Bullpen Overview', 'Bullpen Snapshot', 'Bullpen Health', 'Usage Roles', 'Quick Actions']) {
    assert.ok(htmlIncludes(html, heading), `missing heading substring: ${heading}`)
  }
})

test('the Bullpen section is labelled team-specific to contrast with the dashboard', () => {
  const html = inRouter(React.createElement(Bullpen))
  assert.ok(htmlIncludes(html, 'Team-specific bullpen analysis'))
})
