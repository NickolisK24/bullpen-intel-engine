import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import { makeBoard } from './fixtures/bullpenBoardFixtures.mjs'
import { makeLeagueTeamStateListing } from './fixtures/leagueTeamStateListingFixtures.mjs'

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

const renderDashboard = () => inRouter(React.createElement(DashboardView, {
  data: dashboardData,
  leagueTeamStates: makeLeagueTeamStateListing(),
}))

test('hero states the dashboard is a league-wide / MLB-wide view', () => {
  const html = renderDashboard()
  assert.ok(htmlIncludes(html, 'MLB Bullpen Overview'))
  assert.ok(htmlIncludes(html, 'MLB Bullpen Picture'))
  assert.ok(htmlIncludes(html, 'already-published Team State reads for every expected club'))
  assert.equal(htmlIncludes(html, 'Bullpen-eligible MLB arms'), false)
})

test('the duplicate league count summary no longer renders', () => {
  // phase-0-clarity/02: the League-Wide Bullpen Read count tiles duplicated
  // the landscape lanes and the state card; the Dashboard now carries one
  // league summary.
  const html = renderDashboard()
  assert.equal(htmlIncludes(html, 'League-Wide Bullpen Read'), false)
  assert.equal(htmlIncludes(html, 'bullpen-eligible relievers in the current bullpen availability set'), false)
})

test('the governed all-club Team State landscape replaces the synthetic operating-state card', () => {
  const html = renderDashboard()
  assert.equal(htmlIncludes(html, 'League-Wide Bullpen State'), false)
  assert.ok(htmlIncludes(html, 'Current Bullpen State'))
  assert.ok(htmlIncludes(html, '30 MLB clubs · grouped by published Team State'))
  assert.equal(htmlIncludes(html, 'data-density="full"'), false)
})

test('usage roles are described as the represented published view', () => {
  const html = renderDashboard()
  assert.ok(htmlIncludes(html, 'Usage Roles'))
  assert.ok(htmlIncludes(html, 'represented in this published view'))
  assert.ok(htmlIncludes(html, 'Trusted Arm'))
  assert.ok(htmlIncludes(html, 'Setup Arm'))
  assert.ok(htmlIncludes(html, 'Middle Relief Arm'))
  assert.ok(htmlIncludes(html, 'Unclear Role'))
  assert.ok(htmlIncludes(html, 'Role Unclear'))
  assert.equal((html.match(/Bridge Arm/g) || []).length, 0)
})

test('quick actions no longer duplicate sidebar navigation', () => {
  const html = renderDashboard()
  assert.equal(htmlIncludes(html, 'Quick Actions'), false)
  assert.equal(htmlIncludes(html, 'drill into a single team'), false)
  assert.equal(htmlIncludes(html, 'Two teams, side-by-side'), false)
})

test('existing realignment headings remain (substrings preserved for stability)', () => {
  const html = renderDashboard()
  for (const heading of ['MLB Bullpen Overview', 'Usage Roles']) {
    assert.ok(htmlIncludes(html, heading), `missing heading substring: ${heading}`)
  }
})

test('the Bullpen section is labelled team-specific to contrast with the dashboard', () => {
  const html = inRouter(React.createElement(Bullpen))
  assert.ok(htmlIncludes(html, 'Team-specific bullpen analysis'))
})
