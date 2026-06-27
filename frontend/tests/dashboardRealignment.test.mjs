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
}

test('dashboard leads with bullpen language, not operations/governance language', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(htmlIncludes(html, 'Bullpen Overview'))
  // The old operations/governance framing is gone from the landing.
  assert.ok(!htmlIncludes(html, 'Operational Readiness Dashboard'))
  assert.ok(!htmlIncludes(html, 'governed recommendation context'))
})

test('dashboard renders the five bullpen sections', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(htmlIncludes(html, 'Bullpen Read'))
  assert.ok(htmlIncludes(html, 'Bullpen State'))
  assert.ok(htmlIncludes(html, 'Usage Roles'))
  assert.ok(htmlIncludes(html, 'Quick Actions'))
})

test('bullpen read cards show the five availability counts', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  for (const label of ['Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable']) {
    assert.ok(htmlIncludes(html, label), `missing bullpen read label: ${label}`)
  }
})

test('bullpen state reuses the Team Context Layer statement and confidence', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(htmlIncludes(html, 'Scope'))
  assert.ok(htmlIncludes(html, 'League-Wide'))
  assert.ok(htmlIncludes(html, 'Stable Overall'))
  assert.ok(htmlIncludes(html, 'Open the Bullpen Board for a team-specific read.'))
  assert.equal(htmlIncludes(html, "Open Bullpen for one team's current state"), false)
  assert.ok(htmlIncludes(html, 'Bullpen workload appears manageable.'))
  assert.ok(htmlIncludes(html, 'Workload Read:'))
  assert.ok(htmlIncludes(html, 'of 12 relievers are classified Available.'))
  assert.ok(htmlIncludes(html, 'This is a league-wide read, not a team-specific diagnosis.'))
  assert.equal((html.match(/Availability classifications are workload-based only/g) || []).length, 1)
  assert.equal(htmlIncludes(html, 'Open Team Bullpen Board'), false)
  assert.ok(htmlIncludes(html, 'Open Bullpen Board'))
})

test('usage-roles summary shows distinct role composition counts', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(htmlIncludes(html, 'Trusted Arm'))
  assert.ok(htmlIncludes(html, 'Setup Arm'))
  assert.ok(htmlIncludes(html, 'Middle Relief Arm'))
  assert.ok(htmlIncludes(html, 'Coverage Arm'))
  assert.ok(htmlIncludes(html, 'Unclear Role'))
  assert.ok(htmlIncludes(html, 'Limited Read'))
  assert.equal((html.match(/Bridge Arm/g) || []).length, 0)
})

test('quick actions deep-link into the bullpen workflow and methodology', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board"'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=compare"'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=pitchers"'))
  assert.ok(htmlIncludes(html, 'href="/methodology"'))
})

test('dashboard links to the Data & Trust destination instead of exposing it inline', () => {
  const html = inRouter(React.createElement(DashboardView, { data: dashboardData }))
  assert.ok(htmlIncludes(html, 'href="/trust"'))
  // Governance/diagnostic panels are NOT inline on the dashboard.
  assert.ok(!htmlIncludes(html, 'Operational readiness partially unavailable'))
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
  assert.ok(htmlIncludes(html, 'Bullpen Read'))
})

test('Data & Trust page hosts the relocated trust and governance detail', () => {
  const html = inRouter(React.createElement(DataTrust))
  assert.ok(htmlIncludes(html, 'Data &amp; Trust') || htmlIncludes(html, 'Data & Trust'))
  assert.ok(htmlIncludes(html, 'Freshness'))
  assert.ok(htmlIncludes(html, 'Pitcher Workload Inventory'))
  assert.ok(htmlIncludes(html, 'Secondary Exploratory ERA Study'))
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
