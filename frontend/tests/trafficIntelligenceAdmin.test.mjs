import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => server.close())

const { APP_ROUTES } = await server.ssrLoadModule('/src/App.jsx')
const {
  TRAFFIC_EMPTY_COPY,
  TRAFFIC_ROBOTS_CONTENT,
  TrafficAccessState,
  TrafficIntelligenceAdminView,
  TrafficReport,
} = await server.ssrLoadModule('/src/components/admin/TrafficIntelligenceAdmin.jsx')
const {
  fetchTrafficSummary,
  TRAFFIC_REPORTING_PATH,
} = await server.ssrLoadModule('/src/utils/trafficReporting.js')
const { canonicalPage } = await server.ssrLoadModule('/src/utils/trafficMeasurement.js')

function render(element) {
  return renderToStaticMarkup(React.createElement(MemoryRouter, null, element))
}

function reportFixture(overrides = {}) {
  return {
    generated_at: '2026-07-14T16:00:00Z',
    timezone: 'America/New_York',
    selected_range: { key: '7d', label: 'Last 7 days' },
    measurement_start: '2026-07-01T15:00:00Z',
    definitions: {
      external_visitors: 'Distinct qualifying browser identities active in the selected period; these are not verified individual people.',
      sessions: 'Distinct qualifying browser sessions.',
      page_views: 'Canonical public page views.',
      returning_visitors: 'First qualifying view occurred before the period.',
      new_visitors: 'First qualifying view occurred in the period.',
      multi_page_sessions: 'Sessions with at least two page views.',
      pages_per_session: 'Page views divided by sessions.',
    },
    summary: {
      external_visitors: 12,
      sessions: 15,
      page_views: 24,
      returning_visitors: 4,
      new_visitors: 8,
      multi_page_sessions: 6,
      pages_per_session: 1.6,
    },
    comparison: {
      available: true,
      reason: null,
      changes: Object.fromEntries([
        'external_visitors', 'sessions', 'page_views', 'returning_visitors',
        'new_visitors', 'multi_page_sessions', 'pages_per_session',
      ].map(key => [key, { absolute: 1, percent: 10 }])),
    },
    daily: [{ date: '2026-07-14', visitors: 3, sessions: 4, page_views: 7 }],
    session_depth: { single_page_sessions: 9, multi_page_sessions: 6, pages_per_session: 1.6 },
    acquisition: {
      campaign: { sessions: 3, percentage: 20 },
      referral: { sessions: 4, percentage: 26.67 },
      direct_unknown: { sessions: 8, percentage: 53.33 },
    },
    top_referrers: [{ referrer_domain: 'example.com', sessions: 4 }],
    campaigns: [{ utm_source: 'newsletter', utm_medium: 'email', utm_campaign: 'launch', sessions: 3 }],
    landing_surfaces: [{ surface: 'today', sessions: 8 }],
    most_visited_surfaces: [{ surface: 'bullpen_board', page_views: 9 }],
    bullpen_exploration: {
      bullpen_board_views: 9,
      compare_bullpens_views: 3,
      all_pitchers_views: 2,
      team_contexts: [{ team_ref: 'NYY', page_views: 2 }],
      pitcher_context_page_views: 1,
    },
    measurement_health: {
      measurement_started_at: '2026-07-01T15:00:00Z',
      last_external_page_view_at: '2026-07-14T15:00:00Z',
      last_canonical_page_view_at: '2026-07-14T15:30:00Z',
      registered_internal_browser_ids: 2,
      selected_period: {
        canonical_page_views: 30,
        external_page_views: 24,
        excluded_internal_page_views: 4,
        excluded_bot_page_views: 2,
        unknown_device_external_page_views: 1,
      },
    },
    ...overrides,
  }
}

test('internal route is registered but absent from public navigation', () => {
  assert.ok(APP_ROUTES.some(route => route.path === TRAFFIC_REPORTING_PATH))
  assert.equal(TRAFFIC_REPORTING_PATH, '/admin/product-intelligence')
  const sidebar = readFileSync('src/components/Sidebar.jsx', 'utf8')
  const footer = readFileSync('src/components/layout/Footer.jsx', 'utf8')
  assert.equal(sidebar.includes(TRAFFIC_REPORTING_PATH), false)
  assert.equal(footer.includes(TRAFFIC_REPORTING_PATH), false)
})

test('page declares noindex nofollow metadata and uses normal auth state', () => {
  const source = readFileSync('src/components/admin/TrafficIntelligenceAdmin.jsx', 'utf8')
  assert.equal(TRAFFIC_ROBOTS_CONTENT, 'noindex,nofollow')
  assert.ok(source.includes('meta[name="robots"]'))
  assert.ok(source.includes('useAuthState'))
})

test('access states distinguish checking, sign-in, and forbidden access', () => {
  const checking = render(React.createElement(TrafficAccessState, { state: 'checking' }))
  const unauthenticated = render(React.createElement(TrafficAccessState, { state: 'unauthenticated' }))
  const forbidden = render(React.createElement(TrafficAccessState, { state: 'forbidden' }))
  assert.ok(checking.includes('Checking access'))
  assert.ok(unauthenticated.includes('Sign in'))
  assert.ok(unauthenticated.includes('%2Fadmin%2Fproduct-intelligence'))
  assert.ok(forbidden.includes('not authorized'))
  assert.equal(forbidden.includes('>Sign in<'), false)
})

test('range controls expose 7, 30, 90, and All with selected state', () => {
  const html = render(React.createElement(TrafficIntelligenceAdminView, {
    data: reportFixture(),
    range: '30d',
  }))
  for (const label of ['>7<', '>30<', '>90<', '>All<']) assert.ok(html.includes(label))
  assert.match(html, /aria-pressed="true"[^>]*>30<\/button>/)
})

test('loading error restricted and honest empty states render', () => {
  const loading = render(React.createElement(TrafficIntelligenceAdminView, { loading: true }))
  const error = render(React.createElement(TrafficIntelligenceAdminView, { error: new Error('offline') }))
  const forbiddenError = new Error('forbidden')
  forbiddenError.status = 403
  const forbidden = render(React.createElement(TrafficIntelligenceAdminView, { error: forbiddenError }))
  const empty = render(React.createElement(TrafficIntelligenceAdminView, {
    data: reportFixture({ summary: { ...reportFixture().summary, page_views: 0 } }),
  }))
  assert.ok(loading.includes('Loading traffic intelligence'))
  assert.ok(error.includes('Traffic intelligence is unavailable'))
  assert.ok(error.includes('Retry'))
  assert.ok(forbidden.includes('Access Restricted'))
  assert.ok(empty.includes(TRAFFIC_EMPTY_COPY))
})

test('summary, comparison, reporting sections, and definitions render honestly', () => {
  const html = render(React.createElement(TrafficReport, { report: reportFixture() }))
  for (const text of [
    'External Visitors', 'Sessions', 'Page Views', 'Returning Visitors', 'New Visitors',
    'Multi-Page Sessions', 'Pages per Session', 'Daily Traffic', 'Acquisition',
    'Landing Surfaces', 'Most Visited Surfaces', 'Top Referrer Domains', 'Campaigns',
    'Bullpen Exploration', 'Measurement Health', 'Metric Definitions',
  ]) assert.ok(html.includes(text), text)
  assert.ok(html.includes('distinct browser identities, not confirmed individual people'))
  assert.equal(/engaged users/i.test(html), false)
})

test('acquisition renders session percentages and remains zero-safe', () => {
  const populated = render(React.createElement(TrafficReport, { report: reportFixture() }))
  for (const value of ['3 sessions · 20%', '4 sessions · 26.67%', '8 sessions · 53.33%']) {
    assert.ok(populated.includes(value), value)
  }

  const empty = reportFixture({
    acquisition: {
      campaign: { sessions: 0, percentage: null },
      referral: { sessions: 0, percentage: null },
      direct_unknown: { sessions: 0, percentage: null },
    },
  })
  const emptyHtml = render(React.createElement(TrafficReport, { report: empty }))
  assert.ok(emptyHtml.includes('Percentage unavailable'))
  assert.equal(emptyHtml.includes('NaN'), false)
  assert.equal(emptyHtml.includes('Infinity'), false)
})

test('daily breakdown presents visitors sessions and page views for every date', () => {
  const html = render(React.createElement(TrafficReport, { report: reportFixture() }))
  assert.ok(html.includes('Daily visitors, sessions, and page views'))
  for (const heading of ['Date', 'Visitors', 'Sessions', 'Page Views']) assert.ok(html.includes(heading))
  assert.match(html, /2026-07-14[\s\S]*>3<[\s\S]*>4<[\s\S]*>7</)
})

test('measurement health renders all-time state and selected-period labels', () => {
  const html = render(React.createElement(TrafficReport, { report: reportFixture() }))
  for (const text of [
    'Measurement Started At', 'Last External Page View At', 'Last Canonical Page View At',
    'Registered Internal Browser IDs', 'Selected-Period Canonical Page Views',
    'Selected-Period External Page Views', 'Selected-Period Excluded Internal Page Views',
    'Selected-Period Excluded Bot Page Views', 'Selected-Period Unknown-Device External Page Views',
    '2026-07-01T15:00:00Z', '2026-07-14T15:30:00Z',
  ]) assert.ok(html.includes(text), text)
})

test('comparison unavailable reason is visible without invented percentage', () => {
  const report = reportFixture({
    comparison: { available: false, reason: 'incomplete_prior_period', previous: null, changes: null },
  })
  const html = render(React.createElement(TrafficReport, { report }))
  assert.ok(html.includes('Comparison unavailable'))
  assert.ok(html.includes('Incomplete Prior Period'))
  assert.equal(html.includes('Infinity'), false)
})

test('reporting fetch uses bearer auth and configured backend origin', async () => {
  const calls = []
  const result = await fetchTrafficSummary('30d', {
    authToken: 'normal-bearer',
    configuredBackendOrigin: 'https://api.baseballos.app',
    fetchImpl: async (url, options) => {
      calls.push({ url, options })
      return { ok: true, status: 200, json: async () => ({ summary: {} }) }
    },
  })
  assert.deepEqual(result, { summary: {} })
  assert.equal(calls[0].url, 'https://api.baseballos.app/api/traffic/internal/summary?range=30d')
  assert.equal(calls[0].options.headers.Authorization, 'Bearer normal-bearer')
  assert.deepEqual(Object.keys(calls[0].options.headers).sort(), ['Authorization', 'Content-Type'])
})

test('restricted fetch status is preserved for the page access state', async () => {
  await assert.rejects(
    () => fetchTrafficSummary('7d', {
      authToken: 'normal-bearer',
      fetchImpl: async () => ({ ok: false, status: 403 }),
    }),
    error => error.status === 403,
  )
})

test('dashboard renders no raw identifiers and uses no privileged browser token', () => {
  const report = reportFixture({
    visitor_id: 'visitor-secret',
    session_id: 'session-secret',
    view_id: 'view-secret',
    registered_by_user_id: 99,
    pitcher_id: 42,
  })
  const html = render(React.createElement(TrafficReport, { report }))
  for (const secret of ['visitor-secret', 'session-secret', 'view-secret']) {
    assert.equal(html.includes(secret), false)
  }
  const sources = [
    readFileSync('src/components/admin/TrafficIntelligenceAdmin.jsx', 'utf8'),
    readFileSync('src/utils/trafficReporting.js', 'utf8'),
  ].join('\n')
  assert.equal(sources.includes('ADMIN_API_TOKEN'), false)
  assert.equal(sources.includes('X-Admin-Token'), false)
})

test('admin route is excluded from traffic measurement', () => {
  assert.equal(canonicalPage('/admin/product-intelligence'), null)
})
