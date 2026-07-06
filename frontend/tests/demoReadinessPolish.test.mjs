import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import { makeBoard, staleBoard } from './fixtures/bullpenBoardFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { default: BullpenBoardView } = await server.ssrLoadModule('/src/components/bullpen/board/BullpenBoardView.jsx')
const { DashboardView } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')
const { default: Bullpen } = await server.ssrLoadModule('/src/components/bullpen/Bullpen.jsx')
const view = await server.ssrLoadModule('/src/components/bullpen/board/tonightsBullpenBoardView.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const inRouter = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

const liveBoard = makeBoard({ cardsByStatus: { Available: [{ pitcher_id: 7, name: 'Ace Reliever', availability_status: 'Available' }] } })

// ── Priority 1: live vs sample clarity ─────────────────────────────────────

test('getDataProvenance distinguishes live, sample, and no-data', () => {
  assert.equal(view.getDataProvenance({ is_current: true, sync_status: 'success', data_through: '2026-06-04' }).label, 'Published view current')
  assert.equal(view.getDataProvenance({ is_current: true, data_through: '2026-07-05' }).label, 'Published view current')
  assert.equal(view.getDataProvenance({ is_current: false, sync_status: 'metadata_unavailable', data_through: '2026-04-01' }).label, 'Sample data')
  assert.equal(view.getDataProvenance({ is_current: true, freshness_state: 'sample', data_through: '2026-04-01' }).label, 'Sample data')
  assert.equal(view.getDataProvenance({
    is_current: true,
    sync_status: 'success',
    data_through: '2026-06-04',
    served_consistency_state: 'previous_published_view',
    current_sync_status: 'running',
  }).label, 'Published view; background refresh running')
  assert.equal(view.getDataProvenance({
    is_current: true,
    sync_status: 'success',
    data_through: '2026-06-04',
    served_consistency_state: 'previous_published_view',
    current_sync_status: 'failed',
  }).label, 'Last published view')
  assert.equal(view.getDataProvenance({ data_through: null }).label, 'No data loaded')
  // The through-date meaning is always explained.
  assert.ok(view.getDataProvenance({ is_current: false, data_through: '2026-04-01' }).throughHint.includes('most recent completed game'))
})

test('board banner states the latest completed MLB data date for current data', () => {
  const html = renderToStaticMarkup(React.createElement(BullpenBoardView, { board: liveBoard }))
  assert.ok(htmlIncludes(html, 'Updated after completed games through Jun 4, 2026'))
})

test('board banner flags historical data with the stale caution', () => {
  const html = renderToStaticMarkup(React.createElement(BullpenBoardView, { board: staleBoard }))
  assert.ok(htmlIncludes(html, 'Updated after completed games through'))
  assert.ok(htmlIncludes(html, 'read with caution'))
})

test('dashboard hero pill states data provenance plainly', () => {
  const data = {
    capability: 'bullpen_dashboard',
    context: liveBoard.context,
    roles: { order: [], counts: {}, total: 1 },
    freshness: { is_current: true, sync_status: 'success', data_through: '2026-06-04', last_successful_sync: '2026-06-04T12:00:00Z' },
  }
  const html = inRouter(React.createElement(DashboardView, { data }))
  assert.ok(htmlIncludes(html, 'Updated after completed games through Jun 4, 2026'))
  assert.ok(htmlIncludes(html, 'Latest data update:'))
})

// ── Priority 2: board → pitcher detail ─────────────────────────────────────

test('pitcher cards expose a View details affordance when navigation is wired', () => {
  const html = renderToStaticMarkup(React.createElement(BullpenBoardView, { board: liveBoard, onSelectPitcher: () => {} }))
  assert.ok(htmlIncludes(html, 'Open pitcher context'))
  assert.ok(htmlIncludes(html, 'View pitcher details for Ace Reliever'))
})

test('pitcher cards omit the View details affordance when no handler is provided', () => {
  const html = renderToStaticMarkup(React.createElement(BullpenBoardView, { board: liveBoard }))
  assert.ok(!htmlIncludes(html, 'Open pitcher context'))
})

// ── Priority 3: workload legend ────────────────────────────────────────────

test('board explains the recent workload scale', () => {
  const html = renderToStaticMarkup(React.createElement(BullpenBoardView, { board: liveBoard }))
  assert.ok(htmlIncludes(html, 'higher means heavier recent use'))
})

// ── Priority 4: clarified tab labels ───────────────────────────────────────

test('bullpen tabs read as a clear hierarchy', () => {
  const html = inRouter(React.createElement(Bullpen))
  for (const label of ['Compare Bullpens', 'All Pitchers', 'All Teams']) {
    assert.ok(htmlIncludes(html, label), `missing tab label: ${label}`)
  }
  assert.ok(!htmlIncludes(html, '>Team Summary<'))
})
