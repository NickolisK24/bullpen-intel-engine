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
const { default: DataTrust } = await server.ssrLoadModule('/src/components/trust/DataTrust.jsx')
const { default: Sidebar } = await server.ssrLoadModule('/src/components/Sidebar.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const inRouter = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))
const visibleText = (html) => html
  .replace(/<style[\s\S]*?<\/style>/gi, ' ')
  .replace(/<script[\s\S]*?<\/script>/gi, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()

const forbiddenVisibleTerms =
  /\b(COIN|V2|V3|V4|deterministic|snapshot|endpoint|backend|recommendation engine|baseline distribution|governance layer|sample state)\b/i

// Dashboard payload: league-wide context + roles + freshness.
const board = makeBoard({
  cardsByStatus: {
    Available: Array.from({ length: 5 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
    Monitor: Array.from({ length: 3 }, (_, i) => ({ pitcher_id: 20 + i, name: `M${i}`, availability_status: 'Monitor' })),
    Limited: Array.from({ length: 2 }, (_, i) => ({ pitcher_id: 40 + i, name: `L${i}`, availability_status: 'Limited' })),
    Avoid: [{ pitcher_id: 60, name: 'Av', availability_status: 'Avoid' }],
    Unavailable: [{ pitcher_id: 70, name: 'Un', availability_status: 'Unavailable' }],
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
    counts: { late_high_leverage: 2, setup_bridge: 3, middle_relief: 5, long_multi_inning: 1, low_unclear: 1, insufficient_data: 0 },
    total: 12,
  },
  landscape: {
    capability: 'tonights_bullpen_landscape',
    reference_date: '2026-06-05',
    teams_evaluated: 3,
    games: { available: true, data_state: 'historical', today_count: 0, as_of_date: '2026-06-04', as_of_count: 5, is_today: false, message: null },
    constrained_bullpens: [
      { team_id: 1, team_name: 'Chicago Cubs', team_abbreviation: 'CHC', total_relievers: 8, available: 2, monitor: 2, restricted: 4 },
    ],
    available_bullpens: [
      { team_id: 2, team_name: 'Washington Nationals', team_abbreviation: 'WSH', total_relievers: 8, available: 6, monitor: 1, restricted: 1 },
    ],
    monitoring_concentration: [
      { team_id: 3, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR', total_relievers: 8, available: 3, monitor: 4, restricted: 1 },
    ],
    notes: [],
    storylines: ['Published bullpen storyline from the league context.'],
  },
}

test('dashboard leads with bullpen language, not operations/governance language', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(htmlIncludes(html, 'Bullpen Overview'))
  // The old operations/governance framing is gone from the landing.
  assert.ok(!htmlIncludes(html, 'Operational Readiness Dashboard'))
  assert.ok(!htmlIncludes(html, 'governed recommendation context'))
})

test('dashboard renders the core bullpen sections without duplicate league summaries', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(htmlIncludes(html, 'Storylines'))
  assert.ok(htmlIncludes(html, 'Published Situation Lanes'))
  assert.ok(htmlIncludes(html, 'Usage Roles'))
  assert.equal(htmlIncludes(html, 'League-Wide Bullpen Read'), false)
  assert.equal(htmlIncludes(html, 'League-Wide Bullpen State'), false)
  assert.equal(htmlIncludes(html, 'Quick Actions'), false)
})

test('dashboard landscape uses plain lane titles and keeps descriptive subtitles', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(htmlIncludes(html, 'Needs Rest / Unavailable'))
  assert.ok(htmlIncludes(html, 'Rested &amp; Available'))
  assert.ok(htmlIncludes(html, 'On Watch'))
  assert.ok(
    html.indexOf('Rested &amp; Available') < html.indexOf('On Watch') &&
    html.indexOf('On Watch') < html.indexOf('Needs Rest / Unavailable'),
    'landscape columns should render Rested & Available, On Watch, then Needs Rest / Unavailable',
  )
  assert.ok(htmlIncludes(html, 'Clubs shown with tighter late-inning options'))
  assert.ok(htmlIncludes(html, 'Clubs shown with rested, available depth'))
  assert.ok(htmlIncludes(html, 'Clubs shown with recent workload watch groups'))
})

test('dashboard landscape preserves team-board deep links and honest empty groups', () => {
  const emptyLandscapeData = {
    ...dashboardData,
    landscape: {
      ...dashboardData.landscape,
      constrained_bullpens: [],
    },
  }
  const html = inRouter(React.createElement(DashboardView, { data: emptyLandscapeData }))

  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=WSH&amp;source=landscape"'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=TOR&amp;source=landscape"'))
  assert.ok(htmlIncludes(html, 'Needs Rest / Unavailable'))
  assert.ok(htmlIncludes(html, 'None right now.'))
  assert.equal(htmlIncludes(html, 'CHC'), false)
})

test('dashboard uses completed-game freshness wording for the landscape', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(htmlIncludes(html, 'dateTime="2026-06-04">Jun 4'))
  assert.equal(htmlIncludes(html, 'Tonight slate'), false)
  assert.equal(htmlIncludes(html, "Tonight's Bullpen Landscape"), false)
  assert.equal(htmlIncludes(html, 'latest completed MLB slate'), false)
})

test('storylines lead the situation lanes and the synthetic state card stays absent', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(html.indexOf('Storylines') < html.indexOf('Published Situation Lanes'))
  assert.equal(htmlIncludes(html, 'League-Wide Bullpen State'), false)
})

test('dashboard does not synthesize availability status tiles from league counts', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.equal(htmlIncludes(html, 'Current Bullpen State'), false)
  assert.equal(htmlIncludes(html, 'of 12 relievers are classified Available.'), false)
  assert.equal(htmlIncludes(html, 'Avoid'), false)
})

test('dashboard keeps routine trust quiet and one authoritative freshness stamp', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.equal((html.match(/Data through/g) || []).length, 1)
  assert.equal(htmlIncludes(html, 'Read Confidence:'), false)
  assert.equal(htmlIncludes(html, 'Last data update'), false)
  assert.equal(htmlIncludes(html, 'Generated:'), false)
})

test('usage-roles summary shows distinct role composition counts', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(htmlIncludes(html, 'Trusted Arm'))
  assert.ok(htmlIncludes(html, 'Setup Arm'))
  assert.ok(htmlIncludes(html, 'Middle Relief Arm'))
  assert.ok(htmlIncludes(html, 'Coverage Arm'))
  assert.ok(htmlIncludes(html, 'Unclear Role'))
  assert.ok(htmlIncludes(html, 'Role Unclear'))
  assert.equal((html.match(/Bridge Arm/g) || []).length, 0)
})

test('dashboard keeps team deep links without a quick-actions nav block', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  // The landscape rows and the state card still route into the team board...
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board'))
  // ...but the sidebar-duplicating action cards are gone.
  assert.equal(htmlIncludes(html, 'Quick Actions'), false)
  assert.equal(htmlIncludes(html, 'Read bullpen stories'), false)
  assert.equal(htmlIncludes(html, 'href="/bullpen?view=pitchers"'), false)
})

test('dashboard links to the Data & Trust destination instead of exposing it inline', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(htmlIncludes(html, 'href="/trust"'))
  // Governance/diagnostic panels are NOT inline on the dashboard.
  assert.ok(!htmlIncludes(html, 'Operational readiness partially unavailable'))
})

test('dashboard avoids story-feed duplication, trend modules, and internal language', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  const text = visibleText(html)

  assert.equal(text.includes('What Changed Since Yesterday'), false)
  assert.equal(text.includes('Trend Since Yesterday'), false)
  assert.equal(forbiddenVisibleTerms.test(text), false)
})

test('dashboard renders the hero without data and does not crash', () => {
  const html = inRouter(React.createElement(DashboardView, { data: null, loading: true }))
  assert.ok(htmlIncludes(html, 'Bullpen Overview'))
  assert.ok(!htmlIncludes(html, 'Bullpen Read'))
})

test('dashboard labels retained data when the latest refresh failed', () => {
  const html = inRouter(React.createElement(DashboardView, {
    data: dashboardData,
    error: 'Network failed',
    staleWithError: true,
  }))

  assert.ok(htmlIncludes(html, 'Refresh delayed'))
  assert.ok(htmlIncludes(html, 'showing last loaded data from Jun 4.'))
  assert.ok(htmlIncludes(html, 'Published Situation Lanes'))
})

test('Data & Trust page hosts trust detail without duplicate operational sections', () => {
  const html = inRouter(React.createElement(DataTrust))
  assert.ok(htmlIncludes(html, 'Data &amp; Trust') || htmlIncludes(html, 'Data & Trust'))
  assert.ok(htmlIncludes(html, 'Freshness'))
  // The scored-pitcher inventory diagnostic was removed from the public page.
  assert.equal(htmlIncludes(html, 'Pitcher Workload Inventory'), false)
  assert.equal(htmlIncludes(html, 'Secondary Exploratory ERA Study'), false)
  assert.equal(htmlIncludes(html, 'Digest Preferences'), false)
  assert.equal(htmlIncludes(html, 'Bullpen State + Team Readiness'), false)
  // The Bullpen Intelligence surface fails closed without a live source, so it
  // is not mounted on the live Trust page until it is wired to live MLB data.
  assert.ok(!htmlIncludes(html, 'Bullpen Intelligence'))
  assert.ok(!htmlIncludes(html, 'Bullpen Observations'))
})

test('sidebar navigation includes a Data & Trust destination', () => {
  const html = inRouter(React.createElement(Sidebar))
  assert.ok(htmlIncludes(html, 'Data &amp; Trust') || htmlIncludes(html, 'Data & Trust'))
  assert.ok(htmlIncludes(html, 'href="/trust"'))
  // Core bullpen nav remains.
  assert.ok(htmlIncludes(html, 'href="/bullpen"'))
})
