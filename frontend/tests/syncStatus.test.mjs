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

const {
  getSyncStatusView,
} = await server.ssrLoadModule('/src/components/dashboard/syncStatusView.js')
const {
  SyncStatusContent,
} = await server.ssrLoadModule('/src/components/dashboard/SyncStatus.jsx')

const htmlIncludes = (html, text) => html.includes(text)
const now = Date.parse('2026-06-02T12:00:00Z')

test('renders sync and data-through dates when both are available', () => {
  const data = {
    status: 'success',
    last_sync: '2026-06-01T21:39:12',
    last_successful_sync: '2026-06-01T21:39:56',
    pitchers_updated: 428,
    data: {
      game_logs: 35768,
      latest_game_date: '2026-05-31',
      latest_workload_date: '2026-05-31',
      latest_fatigue_calculated_at: '2026-06-01T21:39:55',
    },
    freshness: { is_current: true, label: 'Current baseball data through 2026-05-31.', limitations: [] },
  }

  const view = getSyncStatusView(data, { now })
  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, { data, loading: false, error: null, now }),
  )

  assert.equal(view.syncLabel, 'Synced')
  assert.equal(view.syncValue, 'June 1, 2026')
  assert.equal(view.dataLabel, 'Data Through')
  assert.equal(view.dataValue, 'May 31, 2026')
  assert.ok(htmlIncludes(html, 'Synced:'))
  assert.ok(htmlIncludes(html, 'June 1, 2026'))
  assert.ok(htmlIncludes(html, 'Data Through:'))
  assert.ok(htmlIncludes(html, 'May 31, 2026'))
})

test('renders sync metadata unavailable with data-through date', () => {
  const data = {
    status: 'metadata_unavailable',
    last_sync: null,
    last_successful_sync: null,
    data: {
      game_logs: 35768,
      latest_game_date: '2026-05-31',
    },
    freshness: {
      is_current: true,
      label: 'Current baseball data through 2026-05-31.',
      limitations: ['Sync metadata unavailable; data coverage is based on game logs.'],
    },
  }

  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, { data, loading: false, error: null, now }),
  )

  assert.ok(htmlIncludes(html, 'Sync metadata:'))
  assert.ok(htmlIncludes(html, 'Unavailable'))
  assert.ok(htmlIncludes(html, 'Data Through:'))
  assert.ok(htmlIncludes(html, 'May 31, 2026'))
})

test('renders failed sync while preserving data-through date', () => {
  const data = {
    status: 'failed',
    last_sync: '2026-06-02T10:00:00',
    last_successful_sync: '2026-06-01T21:39:56',
    message: 'MLB API unavailable',
    data: {
      game_logs: 35768,
      latest_game_date: '2026-05-31',
    },
    freshness: {
      is_current: true,
      label: 'Current baseball data through 2026-05-31.',
      limitations: ['The latest sync attempt failed; data may reflect an earlier successful sync.'],
    },
  }

  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, { data, loading: false, error: null, now }),
  )

  assert.ok(htmlIncludes(html, 'Last sync failed:'))
  assert.ok(htmlIncludes(html, 'June 2, 2026'))
  assert.ok(htmlIncludes(html, 'Data Through:'))
  assert.ok(htmlIncludes(html, 'May 31, 2026'))
})

test('renders no data loaded when metadata and data are unavailable', () => {
  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, {
      data: {
        status: 'never',
        last_sync: null,
        last_successful_sync: null,
        data: { game_logs: 0, latest_game_date: null },
        freshness: { is_current: false, label: 'No baseball workload data loaded.', limitations: [] },
      },
      loading: false,
      error: null,
      now,
    }),
  )

  assert.ok(htmlIncludes(html, 'No data loaded'))
})
