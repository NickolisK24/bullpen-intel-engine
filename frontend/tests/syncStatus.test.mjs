import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { readFile } from 'node:fs/promises'
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
const dataTrustSource = await readFile(
  new URL('../src/components/trust/DataTrust.jsx', import.meta.url),
  'utf8',
)

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
    freshness: {
      is_current: true,
      is_stale: false,
      freshness_state: 'current',
      reason_codes: [],
      label: 'Current baseball data through 2026-05-31.',
      limitations: [],
    },
  }

  const view = getSyncStatusView(data, { now })
  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, { data, loading: false, error: null, now }),
  )

  assert.equal(view.syncLabel, 'Last synced')
  assert.equal(view.syncValue, 'June 1, 2026')
  assert.equal(view.dataLabel, 'Data coverage')
  assert.equal(view.dataValue, 'Built from completed games through May 31, 2026')
  assert.equal(view.healthLabel, 'Healthy')
  assert.equal(view.coverageValue, '428 Pitchers Refreshed')
  assert.ok(htmlIncludes(html, 'Data Status:'))
  assert.ok(htmlIncludes(html, 'Healthy'))
  assert.ok(htmlIncludes(html, 'Last synced:'))
  assert.ok(htmlIncludes(html, 'June 1, 2026'))
  assert.ok(htmlIncludes(html, 'Data coverage:'))
  assert.ok(htmlIncludes(html, 'Built from completed games through May 31, 2026'))
  assert.ok(htmlIncludes(html, 'Refresh Coverage:'))
  assert.ok(htmlIncludes(html, '428 Pitchers Refreshed'))
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
      is_stale: false,
      freshness_state: 'current',
      reason_codes: ['durable_sync_metadata_unavailable'],
      label: 'Current baseball data through 2026-05-31.',
      limitations: ['Sync metadata unavailable; data coverage is based on game logs.'],
    },
  }

  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, { data, loading: false, error: null, now }),
  )

  const view = getSyncStatusView(data, { now })
  assert.equal(view.healthLabel, 'Limited')
  assert.ok(htmlIncludes(html, 'Sync metadata:'))
  assert.ok(htmlIncludes(html, 'Unavailable'))
  assert.ok(htmlIncludes(html, 'Data coverage:'))
  assert.ok(htmlIncludes(html, 'Built from completed games through May 31, 2026'))
})

test('does not mark current data stale from sync age alone', () => {
  const data = {
    status: 'success',
    last_sync: '2026-05-30T05:00:00',
    last_successful_sync: '2026-05-30T05:00:00',
    pitchers_updated: 429,
    data: {
      game_logs: 35768,
      latest_game_date: '2026-05-31',
      latest_workload_date: '2026-05-31',
      latest_fatigue_calculated_at: '2026-05-30T05:00:00',
    },
    freshness: {
      is_current: true,
      is_stale: false,
      freshness_state: 'current',
      reason_codes: [],
      label: 'Current baseball data through 2026-05-31.',
      limitations: [],
    },
  }

  const view = getSyncStatusView(data, { now })
  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, { data, loading: false, error: null, now }),
  )

  assert.equal(view.healthLabel, 'Healthy')
  assert.ok(htmlIncludes(html, 'Data Status:'))
  assert.ok(htmlIncludes(html, 'Healthy'))
  assert.ok(htmlIncludes(html, '429 Pitchers Refreshed'))
})

test('renders stale workload data from backend freshness reason codes', () => {
  const data = {
    status: 'success',
    last_sync: '2026-06-01T21:39:12',
    last_successful_sync: '2026-06-01T21:39:56',
    pitchers_updated: 428,
    data: {
      game_logs: 35768,
      latest_game_date: '2026-04-01',
      latest_workload_date: '2026-04-01',
      latest_fatigue_calculated_at: '2026-06-01T21:39:55',
    },
    freshness: {
      is_current: false,
      is_stale: true,
      freshness_state: 'stale',
      data_age_days: 62,
      reason_codes: ['workload_data_outside_active_window'],
      label: 'Stale baseball data through 2026-04-01.',
      limitations: ['Latest game date is outside the 14-day freshness window.'],
    },
  }

  const view = getSyncStatusView(data, { now })
  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, { data, loading: false, error: null, now }),
  )

  assert.equal(view.healthLabel, 'Not Current')
  assert.equal(view.reasonCodes[0], 'workload_data_outside_active_window')
  assert.ok(htmlIncludes(html, 'Data Status:'))
  assert.ok(htmlIncludes(html, 'Not Current'))
  assert.ok(htmlIncludes(html, 'Stale baseball data through 2026-04-01.'))
  assert.ok(htmlIncludes(html, 'Data coverage:'))
  assert.ok(htmlIncludes(html, 'Built from completed games through Apr 1, 2026'))
})

test('renders successful sync without a data-through date', () => {
  const data = {
    status: 'success',
    last_sync: '2026-06-01T21:39:12',
    last_successful_sync: '2026-06-01T21:39:56',
    pitchers_updated: 0,
    data: {
      game_logs: 0,
      latest_game_date: null,
      latest_workload_date: null,
      latest_fatigue_calculated_at: null,
    },
    freshness: {
      is_current: false,
      is_stale: false,
      freshness_state: 'missing',
      reason_codes: ['workload_data_missing'],
      label: 'No baseball workload data loaded.',
      limitations: ['No game logs are available.'],
    },
  }

  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, { data, loading: false, error: null, now }),
  )

  assert.ok(htmlIncludes(html, 'Last synced:'))
  assert.ok(htmlIncludes(html, 'June 1, 2026'))
  assert.ok(htmlIncludes(html, 'Data coverage:'))
  assert.ok(htmlIncludes(html, 'Unavailable'))
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
      is_stale: false,
      freshness_state: 'current',
      reason_codes: ['latest_sync_failed'],
      label: 'Current baseball data through 2026-05-31.',
      limitations: ['The latest sync attempt failed; data may reflect an earlier successful sync.'],
    },
  }

  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, { data, loading: false, error: null, now }),
  )

  assert.ok(htmlIncludes(html, 'Last sync failed:'))
  assert.ok(htmlIncludes(html, 'June 2, 2026'))
  assert.ok(htmlIncludes(html, 'Data coverage:'))
  assert.ok(htmlIncludes(html, 'Built from completed games through May 31, 2026'))
})

test('served freshness authority wins when sync data is ahead of publish', () => {
  const data = {
    status: 'success',
    last_sync: '2026-06-17T11:39:12',
    last_successful_sync: '2026-06-17T11:39:56',
    pitchers_updated: 428,
    data: {
      game_logs: 36000,
      latest_game_date: '2026-06-17',
      latest_workload_date: '2026-06-17',
      latest_fatigue_calculated_at: '2026-06-17T11:39:55',
    },
    freshness: {
      is_current: true,
      is_stale: false,
      freshness_state: 'current',
      reason_codes: [],
      label: 'Current baseball data through 2026-06-17.',
      limitations: [],
    },
  }
  const servedFreshness = {
    data_through: '2026-06-16',
    is_current: true,
    sync_status: 'success',
  }

  const view = getSyncStatusView(data, { now, freshnessAuthority: servedFreshness })
  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, {
      data,
      loading: false,
      error: null,
      now,
      freshnessAuthority: servedFreshness,
    }),
  )

  assert.equal(view.dataValue, 'Built from completed games through Jun 16, 2026')
  assert.ok(htmlIncludes(html, 'Built from completed games through Jun 16, 2026'))
  assert.equal(htmlIncludes(html, 'Jun 17, 2026'), false)
})

test('renders no data loaded when metadata and data are unavailable', () => {
  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, {
      data: {
        status: 'never',
        last_sync: null,
        last_successful_sync: null,
        data: { game_logs: 0, latest_game_date: null },
        freshness: {
          is_current: false,
          is_stale: false,
          freshness_state: 'missing',
          reason_codes: ['workload_data_missing'],
          label: 'No baseball workload data loaded.',
          limitations: [],
        },
      },
      loading: false,
      error: null,
      now,
    }),
  )

  assert.ok(htmlIncludes(html, 'No data loaded'))
})

test('Data & Trust page reuses its sync status request for the trust strip', () => {
  // The freshness/sync detail relocated from the Dashboard to the Data & Trust
  // page; it still renders via the shared SyncStatusContent (no duplicate
  // self-fetching <SyncStatus /> instance).
  assert.ok(dataTrustSource.includes('SyncStatusContent'))
  assert.ok(dataTrustSource.includes('getBullpenDashboard'))
  assert.ok(dataTrustSource.includes('freshnessAuthority={servedFreshness}'))
  assert.equal(dataTrustSource.includes('sync.data?.data?.latest_game_date'), false)
  assert.equal(dataTrustSource.includes('<SyncStatus />'), false)
})
