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

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const inRouter = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

const context = makeBoard({ cardsByStatus: { Available: [{ pitcher_id: 1, name: 'A', availability_status: 'Available' }] } }).context

const withFreshness = (freshness) => ({
  capability: 'bullpen_dashboard',
  context,
  roles: { order: [], counts: {}, total: 1 },
  freshness,
})

// The banner derives from authoritative (durable-backed) freshness only. These
// pin the user-facing symptom: healthy durable freshness => "Current", never a
// snapshot label, regardless of deploy-local state.

test('healthy durable freshness renders the current banner, not a snapshot', () => {
  const html = inRouter(React.createElement(DashboardView, {
    data: withFreshness({ is_current: true, sync_status: 'success', data_through: '2026-06-04', last_successful_sync: '2026-06-04T12:00:00Z' }),
  }))
  assert.ok(htmlIncludes(html, 'Current — 2026 Season'))
  assert.ok(!htmlIncludes(html, 'End-of-Season Read'))
})

test('non-current freshness renders the honest season snapshot label', () => {
  const html = inRouter(React.createElement(DashboardView, {
    data: withFreshness({ is_current: false, sync_status: 'metadata_unavailable', data_through: '2026-04-01', last_successful_sync: null }),
  }))
  assert.ok(htmlIncludes(html, '2026 Season Snapshot'))
  assert.ok(!htmlIncludes(html, 'End-of-Season Read'))
  assert.ok(!htmlIncludes(html, 'Current — 2026 Season'))
})

test('in-season July dashboard does not show end-of-season copy', () => {
  const html = inRouter(React.createElement(DashboardView, {
    data: withFreshness({ is_current: true, data_through: '2026-07-05', last_successful_sync: '2026-07-06T04:00:00Z' }),
  }))
  assert.ok(htmlIncludes(html, 'Current — 2026 Season'))
  assert.ok(!htmlIncludes(html, 'End-of-Season Read'))
})

test('publishable live dashboard freshness does not render as sample or snapshot', () => {
  const html = inRouter(React.createElement(DashboardView, {
    data: withFreshness({
      data_through: '2026-07-05',
      latest_workload_date: '2026-07-05',
      last_successful_sync: '2026-07-06T04:34:36Z',
      sync_status: 'success',
      complete_enough_to_publish: true,
      validations_passed: true,
      is_current: false,
      is_stale: false,
      freshness_state: 'incomplete',
      label: 'Baseball data through 2026-07-05 is incomplete and is not publishable as current.',
      limitations: ['Slate coverage validations did not pass.'],
      slate_coverage: {
        complete_enough_to_publish: true,
        validations_passed: true,
        games_final: 15,
        games_fully_ingested: 15,
      },
    }),
  }))

  assert.ok(htmlIncludes(html, 'Current — 2026 Season'))
  assert.ok(htmlIncludes(html, 'Published view current'))
  assert.ok(htmlIncludes(html, 'Updated after completed games through Jul 5, 2026'))
  assert.equal(htmlIncludes(html, 'Sample data'), false)
  assert.equal(htmlIncludes(html, '2026 Season Snapshot'), false)
  assert.equal(htmlIncludes(html, 'incomplete and is not publishable'), false)
})

test('a failed latest sync does not render as current even with a recent data date', () => {
  // status drives Current; a failed durable sync must not be painted healthy.
  const html = inRouter(React.createElement(DashboardView, {
    data: withFreshness({ is_current: true, sync_status: 'failed', data_through: '2026-06-04', last_successful_sync: '2026-06-01T12:00:00Z' }),
  }))
  assert.ok(!htmlIncludes(html, 'Current — 2026 Season'))
  assert.ok(!htmlIncludes(html, 'End-of-Season Read'))
})

test('running background lane does not make the dashboard look generally mid-sync', () => {
  const html = inRouter(React.createElement(DashboardView, {
    data: withFreshness({
      is_current: true,
      sync_status: 'success',
      data_through: '2026-07-03',
      last_successful_sync: '2026-07-04T12:00:00Z',
      served_consistency_state: 'previous_published_view',
      current_sync_status: 'running',
      current_sync_stage: 'workload_evidence',
    }),
  }))

  assert.ok(htmlIncludes(html, 'Published view; background refresh running'))
  assert.ok(htmlIncludes(html, 'Updated after completed games through Jul 3, 2026'))
  assert.equal(htmlIncludes(html, 'Sync in progress'), false)
})
