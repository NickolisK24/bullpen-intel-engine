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

after(async () => server.close())

const { DashboardView } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')
const { default: DataTrust } = await server.ssrLoadModule('/src/components/trust/DataTrust.jsx')
const { default: Sidebar } = await server.ssrLoadModule('/src/components/Sidebar.jsx')

const render = element => renderToStaticMarkup(React.createElement(MemoryRouter, null, element))
const visibleText = html => html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
const findElement = (node, predicate) => {
  if (!React.isValidElement(node)) return null
  if (predicate(node)) return node
  for (const child of React.Children.toArray(node.props.children)) {
    const match = findElement(child, predicate)
    if (match) return match
  }
  return null
}

const board = makeBoard({ cardsByStatus: {
  Available: Array.from({ length: 5 }, (_, index) => ({ pitcher_id: index + 1, name: `A${index}`, availability_status: 'Available' })),
} })
const dashboardData = {
  capability: 'bullpen_dashboard',
  context: board.context,
  freshness: { data_through: '2026-06-04', is_current: true, sync_status: 'success' },
  roles: {
    order: ['late_high_leverage', 'setup_bridge', 'middle_relief', 'long_multi_inning', 'low_unclear', 'insufficient_data'],
    counts: { late_high_leverage: 2, setup_bridge: 3, middle_relief: 5, long_multi_inning: 1, low_unclear: 1, insufficient_data: 0 },
    total: 12,
  },
  landscape: { storylines: ['Published bullpen storyline from the league context.'] },
}
const listing = makeLeagueTeamStateListing()
const renderDashboard = (props = {}) => render(React.createElement(DashboardView, {
  data: dashboardData,
  leagueTeamStates: listing,
  ...props,
}))

test('dashboard leads with baseball language and one governed all-club picture', () => {
  const html = renderDashboard()
  assert.match(html, /MLB Bullpen Overview/)
  assert.match(html, /MLB Bullpen Picture/)
  assert.match(html, /Current Bullpen State/)
  assert.match(html, /30 MLB clubs · grouped by published Team State/)
  assert.doesNotMatch(html, /Operational Readiness Dashboard|League-Wide Bullpen State|Quick Actions/)
})

test('backend Storylines lead the all-club state landscape and secondary context', () => {
  const html = renderDashboard()
  assert.ok(html.indexOf('Storylines') < html.indexOf('Current Bullpen State'))
  assert.ok(html.indexOf('Current Bullpen State') < html.indexOf('Usage Roles'))
  assert.match(html, /Published bullpen storyline from the league context\./)
})

test('retired partial Dashboard lanes and their metric copy are absent', () => {
  const text = visibleText(renderDashboard())
  for (const retired of [
    'Published Situation Lanes', 'Rested & Available', 'On Watch',
    'Needs Rest / Unavailable', 'Clubs shown with rested, available depth',
  ]) assert.equal(text.includes(retired), false, retired)
})

test('all-club rows keep canonical Dashboard Team Board deep links', () => {
  const html = renderDashboard()
  assert.match(html, /href="\/bullpen\?view=board&amp;team=ARI&amp;source=dashboard"/)
  assert.match(html, /href="\/bullpen\?view=board&amp;team=WSH&amp;source=dashboard"/)
  assert.doesNotMatch(html, /source=landscape/)
})

test('dashboard uses one listing-owned Data-through stamp and keeps routine trust quiet', () => {
  const html = renderDashboard()
  assert.equal((html.match(/Data through/g) || []).length, 1)
  assert.match(html, /dateTime="2026-08-14">Aug 14/)
  assert.doesNotMatch(html, /dateTime="2026-06-04"/)
  assert.doesNotMatch(html, /Read Confidence:|Last data update|Generated:|Published at|Last checked/)
  assert.match(html, /href="\/trust"/)
})

test('usage-role summary remains secondary and uses its existing vocabulary', () => {
  const html = renderDashboard()
  for (const label of ['Trusted Arm', 'Setup Arm', 'Middle Relief Arm', 'Coverage Arm', 'Unclear Role', 'Role Unclear']) {
    assert.match(html, new RegExp(label))
  }
})

test('league endpoint failure does not fall back to partial or derived Team State', () => {
  const html = renderDashboard({ leagueTeamStates: null, leagueTeamStatesError: 'raw network exception' })
  assert.match(html, /The current league Team State view is unavailable\./)
  assert.doesNotMatch(html, /raw network exception|Published Situation Lanes|Rested &amp; Available/)
  assert.match(html, /Usage Roles/)
})

test('secondary Dashboard context failure is explicit without replacing the primary league view', () => {
  const retry = () => {}
  const html = renderDashboard({ data: null, error: 'raw secondary exception', onRetry: retry })
  assert.match(html, /Current Bullpen State/)
  assert.match(html, /30 MLB clubs · grouped by published Team State/)
  assert.match(html, /Secondary Dashboard Context/)
  assert.match(html, /Secondary context unavailable/)
  assert.match(html, /Roster-status and usage-role context could not be loaded\./)
  assert.match(html, /Try Again/)
  assert.doesNotMatch(html, /raw secondary exception|Something went wrong/)
})

test('secondary Dashboard context retains delayed-refresh copy and retry wiring with usable data', () => {
  const retry = () => {}
  const view = DashboardView({
    data: dashboardData,
    staleWithError: true,
    onRetry: retry,
    leagueTeamStates: listing,
  })
  const retryButton = findElement(view, element => element.type === 'button' && element.props.children === 'Retry')
  const html = render(view)

  assert.match(html, /Secondary Dashboard context refresh is delayed; showing the last loaded context\./)
  assert.ok(retryButton)
  assert.equal(retryButton.props.onClick, retry)
})

test('Dashboard avoids ranking, generated conclusions, and internal reader leakage', () => {
  const text = visibleText(renderDashboard())
  assert.equal(/\b(Most|Top|Best|Worst|score|rank|grade)\b/i.test(text), false)
  assert.doesNotMatch(text, /What Changed Since Yesterday|Trend Since Yesterday|deterministic|endpoint|backend|governance layer/)
})

test('Data & Trust and sidebar destinations remain intact', () => {
  const trustHtml = render(React.createElement(DataTrust))
  assert.match(trustHtml, /Data &amp; Trust|Data & Trust/)
  assert.match(trustHtml, /Freshness/)

  const sidebarHtml = render(React.createElement(Sidebar))
  assert.match(sidebarHtml, /href="\/trust"/)
  assert.match(sidebarHtml, /href="\/bullpen"/)
})
