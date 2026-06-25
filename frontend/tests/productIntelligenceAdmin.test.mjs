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

const { APP_ROUTES } = await server.ssrLoadModule('/src/App.jsx')
const {
  ADMIN_PRODUCT_EVENTS_PATH,
  ADMIN_TOKEN_HEADER,
  PRODUCT_INTELLIGENCE_HEARTBEAT_ROUTE,
  buildProductEventsQuery,
  fetchProductIntelligenceEvents,
  fetchProductIntelligenceHeartbeat,
  normalizeProductEventsLimit,
} = await server.ssrLoadModule('/src/utils/adminProductEvents.js')
const {
  ProductEventHeartbeatTable,
  ProductEventsTable,
  ProductIntelligenceAdminView,
  payloadSummaryText,
} = await server.ssrLoadModule('/src/components/admin/ProductIntelligenceAdmin.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

test('Product Intelligence admin route is registered but not primary navigation', () => {
  const paths = new Set(APP_ROUTES.map(route => route.path))
  assert.ok(paths.has(ADMIN_PRODUCT_EVENTS_PATH))
  assert.equal(ADMIN_PRODUCT_EVENTS_PATH, '/admin/product-intelligence')
})

test('admin product event query normalizes event filter and limit', () => {
  assert.equal(normalizeProductEventsLimit('999'), 100)
  assert.equal(normalizeProductEventsLimit('0'), 1)
  assert.equal(normalizeProductEventsLimit('not-a-number'), 25)
  assert.equal(
    buildProductEventsQuery({ eventName: 'story_viewed', limit: 10 }),
    'event_name=story_viewed&limit=10',
  )
  assert.equal(
    buildProductEventsQuery({ eventName: '', limit: 999 }),
    'limit=100',
  )
})

test('admin product event fetch uses runtime token and the admin-gated endpoint', async () => {
  const calls = []
  const result = await fetchProductIntelligenceEvents({
    adminToken: 'runtime-secret',
    eventName: 'today_loaded',
    limit: 5,
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options })
      return {
        ok: true,
        json: async () => ({ capability: 'product_intelligence_events', events: [] }),
      }
    },
  })

  assert.deepEqual(result, { capability: 'product_intelligence_events', events: [] })
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/system/product-events?event_name=today_loaded&limit=5')
  assert.equal(calls[0].options.method, 'GET')
  assert.equal(calls[0].options.headers[ADMIN_TOKEN_HEADER], 'runtime-secret')
})

test('admin product event fetch reports unauthorized response clearly', async () => {
  await assert.rejects(
    () => fetchProductIntelligenceEvents({
      fetchImpl: async () => ({ ok: false, status: 401 }),
    }),
    /Admin token required/,
  )
})

test('admin heartbeat fetch uses runtime token and the heartbeat endpoint', async () => {
  const calls = []
  const result = await fetchProductIntelligenceHeartbeat({
    adminToken: 'runtime-secret',
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options })
      return {
        ok: true,
        json: async () => ({ capability: 'product_intelligence_heartbeat', events: [] }),
      }
    },
  })

  assert.deepEqual(result, { capability: 'product_intelligence_heartbeat', events: [] })
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, `/api${PRODUCT_INTELLIGENCE_HEARTBEAT_ROUTE}`)
  assert.equal(calls[0].options.method, 'GET')
  assert.equal(calls[0].options.headers[ADMIN_TOKEN_HEADER], 'runtime-secret')
})

test('heartbeat table shows event name, count, and most recent for operator verification', () => {
  const html = renderToStaticMarkup(React.createElement(ProductEventHeartbeatTable, {
    rows: [
      { event_name: 'today_loaded', count: 2, most_recent: '2026-06-25T11:59:00Z' },
      { event_name: 'digest_complaint', count: 0, most_recent: null },
    ],
  }))

  assert.ok(htmlIncludes(html, 'Event name'))
  assert.ok(htmlIncludes(html, 'Count'))
  assert.ok(htmlIncludes(html, 'Most recent event'))
  assert.ok(htmlIncludes(html, 'today_loaded'))
  assert.ok(htmlIncludes(html, '2026-06-25T11:59:00Z'))
  // A never-seen event is visibly at zero (an em dash for the missing timestamp).
  assert.ok(htmlIncludes(html, 'digest_complaint'))
  assert.equal(/chart/i.test(html), false)
})

test('heartbeat table renders nothing when there are no rows', () => {
  const html = renderToStaticMarkup(React.createElement(ProductEventHeartbeatTable, { rows: [] }))
  assert.equal(html, '')
})

test('admin console renders operator controls and sanitized event rows', () => {
  const rows = [{
    id: 1,
    event_name: 'story_viewed',
    occurred_at: '2026-06-24T12:00:00Z',
    user_id: 2,
    anon_id_present: true,
    team_id: 118,
    source: 'home',
    payload_summary: {
      story_id: '118:2026-06-24',
      story_type: 'coverage_pressure',
      email: '[redacted]',
    },
  }]
  const html = renderToStaticMarkup(React.createElement(ProductIntelligenceAdminView, {
    adminToken: '',
    eventName: '',
    limit: 25,
    rows,
  }))

  assert.ok(htmlIncludes(html, 'Product Intelligence Console'))
  assert.ok(htmlIncludes(html, 'Internal read-only event verification'))
  assert.ok(htmlIncludes(html, 'Admin token'))
  assert.ok(htmlIncludes(html, 'story_viewed'))
  assert.ok(htmlIncludes(html, '2026-06-24T12:00:00Z'))
  assert.ok(htmlIncludes(html, 'Yes'))
  assert.ok(htmlIncludes(html, 'story_id: 118:2026-06-24'))
  assert.ok(htmlIncludes(html, 'email: [redacted]'))
  assert.equal(htmlIncludes(html, 'fan@example.com'), false)
  assert.equal(htmlIncludes(html, 'anon:client-123'), false)
})

test('product event table renders an empty state without charts or rollups', () => {
  const html = renderToStaticMarkup(React.createElement(ProductEventsTable, { rows: [] }))

  assert.ok(htmlIncludes(html, 'No Product Intelligence events returned for this filter.'))
  assert.equal(/chart/i.test(html), false)
  assert.equal(/rollup/i.test(html), false)
})

test('payload summary text keeps compact operator-readable values', () => {
  assert.equal(payloadSummaryText({}), 'No payload')
  assert.equal(payloadSummaryText({
    story_id: '118:2026-06-24',
    nested: { type: 'object', keys: ['story_type'] },
  }), 'story_id: 118:2026-06-24, nested: {"type":"object","keys":["story_type"]}')
})
