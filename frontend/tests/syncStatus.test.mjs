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

test('renders distinct sync freshness fields when all values are available', () => {
  const data = {
    status: 'success',
    last_checked: '2026-06-23T11:07:33Z',
    last_sync: '2026-06-23T11:05:33Z',
    last_successful_sync: '2026-06-23T11:05:33Z',
    data_through: '2026-06-23',
    pitchers_updated: 428,
    data: {
      game_logs: 35768,
      latest_game_date: '2026-06-23',
      latest_workload_date: '2026-06-23',
      latest_fatigue_calculated_at: '2026-06-23T11:05:33Z',
    },
    freshness: {
      is_current: true,
      is_stale: false,
      freshness_state: 'current',
      reason_codes: [],
      label: 'Current baseball data through 2026-06-23.',
      limitations: [],
    },
  }

  const view = getSyncStatusView(data, { now })
  const html = renderToStaticMarkup(
    React.createElement(SyncStatusContent, { data, loading: false, error: null, now }),
  )

  assert.equal(view.syncLabel, 'Last data update')
  assert.equal(view.lastCheckedLabel, 'Last checked')
  assert.equal(view.lastCheckedValue, '7:07 AM ET')
  assert.equal(view.lastDataUpdateLabel, 'Last data update')
  assert.equal(view.lastDataUpdateValue, '7:05 AM ET')
  assert.equal(view.dataLabel, 'Data through')
  assert.equal(view.dataValue, 'June 23, 2026')
  assert.equal(view.healthLabel, 'Healthy')
  assert.equal(view.coverageValue, '428 Pitchers Refreshed')
  assert.ok(htmlIncludes(html, 'Data Status:'))
  assert.ok(htmlIncludes(html, 'Healthy'))
  assert.ok(htmlIncludes(html, 'Last checked:'))
  assert.ok(htmlIncludes(html, '7:07 AM ET'))
  assert.ok(htmlIncludes(html, 'Last data update:'))
  assert.ok(htmlIncludes(html, '7:05 AM ET'))
  assert.ok(htmlIncludes(html, 'Data through:'))
  assert.ok(htmlIncludes(html, 'June 23, 2026'))
  assert.equal(htmlIncludes(html, 'Refresh Coverage:'), false)
})

test('keeps date-only data-through values from shifting across ET boundaries', () => {
  const data = {
    status: 'success',
    last_checked: '2026-06-01T00:30:00Z',
    last_sync: '2026-06-01T00:30:00Z',
    last_successful_sync: '2026-06-01T00:30:00Z',
    data_through: '2026-06-01',
    data: {
      game_logs: 35768,
      latest_game_date: '2026-06-01',
    },
    freshness: {
      is_current: true,
      is_stale: false,
      freshness_state: 'current',
      reason_codes: [],
      label: 'Current baseball data through 2026-06-01.',
      limitations: [],
    },
  }

  const view = getSyncStatusView(data, { now })

  assert.equal(view.lastCheckedValue, '8:30 PM ET')
  assert.equal(view.dataValue, 'June 1, 2026')
  assert.notEqual(view.dataValue, 'May 31, 2026')
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
  assert.ok(htmlIncludes(html, 'Last checked:'))
  assert.ok(htmlIncludes(html, 'Unavailable'))
  assert.ok(htmlIncludes(html, 'Data through:'))
  assert.ok(htmlIncludes(html, 'May 31, 2026'))
})

test('does not mark current data stale from sync age alone', () => {
  const data = {
    status: 'success',
    last_checked: '2026-05-30T05:00:00Z',
    last_sync: '2026-05-30T05:00:00Z',
    last_successful_sync: '2026-05-30T05:00:00Z',
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
  assert.equal(view.coverageValue, '429 Pitchers Refreshed')
})

test('renders stale workload data from backend freshness reason codes', () => {
  const data = {
    status: 'success',
    last_checked: '2026-06-01T21:39:12Z',
    last_sync: '2026-06-01T21:39:12Z',
    last_successful_sync: '2026-06-01T21:39:56Z',
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
  assert.ok(htmlIncludes(html, 'Data through:'))
  assert.ok(htmlIncludes(html, 'April 1, 2026'))
})

test('renders successful sync without a data-through date', () => {
  const data = {
    status: 'success',
    last_checked: '2026-06-01T21:39:12Z',
    last_sync: '2026-06-01T21:39:12Z',
    last_successful_sync: '2026-06-01T21:39:56Z',
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

  assert.ok(htmlIncludes(html, 'Last checked:'))
  assert.ok(htmlIncludes(html, 'Last data update:'))
  assert.ok(htmlIncludes(html, 'Data through:'))
  assert.ok(htmlIncludes(html, 'Unavailable'))
})

test('renders failed sync while preserving data-through date', () => {
  const data = {
    status: 'failed',
    last_checked: '2026-06-02T10:00:00Z',
    last_sync: '2026-06-02T10:00:00Z',
    last_successful_sync: '2026-06-01T21:39:56Z',
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

  assert.ok(htmlIncludes(html, 'Last checked:'))
  assert.ok(htmlIncludes(html, '6:00 AM ET'))
  assert.ok(htmlIncludes(html, 'Last data update:'))
  assert.ok(htmlIncludes(html, '5:39 PM ET'))
  assert.ok(htmlIncludes(html, 'Data through:'))
  assert.ok(htmlIncludes(html, 'May 31, 2026'))
})

test('served freshness authority wins when sync data is ahead of publish', () => {
  const data = {
    status: 'success',
    last_checked: '2026-06-17T11:39:12Z',
    last_sync: '2026-06-17T11:39:12Z',
    last_successful_sync: '2026-06-17T11:39:56Z',
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

  assert.equal(view.dataValue, 'June 16, 2026')
  assert.ok(htmlIncludes(html, 'June 16, 2026'))
  assert.equal(htmlIncludes(html, 'June 17, 2026'), false)
})

test('current served freshness suppresses stale raw sync helper copy', () => {
  const data = {
    status: 'success',
    last_checked: '2026-07-06T04:00:00Z',
    last_sync: '2026-07-06T04:00:00Z',
    last_successful_sync: '2026-07-06T04:00:00Z',
    pitchers_updated: 454,
    data: {
      game_logs: 36000,
      latest_game_date: '2026-07-05',
      latest_workload_date: '2026-07-05',
    },
    freshness: {
      is_current: true,
      is_stale: false,
      freshness_state: 'current',
      reason_codes: ['scheduled_games_not_final', 'completeness_unknown'],
      label: 'Baseball data through 2026-07-05 is incomplete and is not publishable as current.',
      limitations: [],
    },
  }
  const servedFreshness = {
    data_through: '2026-07-05',
    is_current: true,
    is_stale: false,
    freshness_state: 'current',
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

  assert.equal(view.healthLabel, 'Healthy')
  assert.equal(view.helper, 'Public bullpen data is current through July 5, 2026.')
  assert.equal(view.reasonCodes.length, 0)
  assert.ok(htmlIncludes(html, 'Healthy'))
  assert.ok(htmlIncludes(html, 'Public bullpen data is current through July 5, 2026.'))
  assert.equal(htmlIncludes(html, 'incomplete and is not publishable'), false)
})

test('publishable served freshness suppresses stale incomplete dashboard label', () => {
  const data = {
    status: 'success',
    last_checked: '2026-07-06T05:25:31Z',
    last_sync: '2026-07-06T05:25:31Z',
    last_successful_sync: '2026-07-06T05:25:33Z',
    pitchers_updated: 0,
    data: {
      game_logs: 36000,
      latest_game_date: '2026-07-05',
      latest_workload_date: '2026-07-05',
    },
    freshness: {
      is_current: true,
      is_stale: false,
      freshness_state: 'current',
      reason_codes: [],
      label: 'Current baseball data through 2026-07-05.',
      limitations: [],
    },
  }
  const servedFreshness = {
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
    limitations: [
      'Scheduled games on this slate are not final yet.',
      'Slate completeness cannot be proven from stored coverage.',
    ],
    reason_codes: ['scheduled_games_not_final', 'completeness_unknown'],
    slate_coverage: {
      complete_enough_to_publish: true,
      validations_passed: true,
      games_final: 15,
      games_fully_ingested: 15,
      games_incomplete: 0,
      reason_codes: ['slate_complete'],
    },
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

  assert.equal(view.healthLabel, 'Healthy')
  assert.equal(view.helper, 'Public bullpen data is current through July 5, 2026.')
  assert.equal(view.reasonCodes.length, 0)
  assert.equal(view.freshnessState, 'current')
  assert.ok(htmlIncludes(html, 'Healthy'))
  assert.ok(htmlIncludes(html, 'Public bullpen data is current through July 5, 2026.'))
  assert.equal(htmlIncludes(html, 'incomplete and is not publishable'), false)
})

test('non-publishable limited served freshness preserves incomplete copy', () => {
  const data = {
    status: 'success',
    last_checked: '2026-07-06T05:25:31Z',
    last_sync: '2026-07-06T05:25:31Z',
    last_successful_sync: '2026-07-06T05:25:33Z',
    data: {
      latest_game_date: '2026-07-05',
    },
    freshness: {
      is_current: false,
      is_stale: false,
      freshness_state: 'limited',
      reason_codes: ['scheduled_games_not_final'],
      label: 'Baseball data through 2026-07-05 is incomplete and is not publishable as current.',
      limitations: ['Slate coverage validations did not pass.'],
    },
  }
  const servedFreshness = {
    data_through: '2026-07-05',
    sync_status: 'success',
    complete_enough_to_publish: false,
    validations_passed: false,
    is_current: false,
    is_stale: false,
    freshness_state: 'incomplete',
    label: 'Baseball data through 2026-07-05 is incomplete and is not publishable as current.',
    limitations: ['Slate coverage validations did not pass.'],
    reason_codes: ['validations_failed'],
  }

  const view = getSyncStatusView(data, { now, freshnessAuthority: servedFreshness })

  assert.equal(view.healthLabel, 'Limited')
  assert.ok(view.helper.includes('incomplete and is not publishable'))
  assert.ok(view.limitations.includes('Slate coverage validations did not pass.'))
})

test('uses stable freshness labels across sync job types', () => {
  const postgame = {
    status: 'success',
    last_checked: '2026-06-21T03:15:00Z',
    last_sync: '2026-06-21T03:15:00Z',
    last_successful_sync: '2026-06-21T03:15:30Z',
    last_successful_sync_run: { job_name: 'postgame_refresh' },
    pitchers_updated: 12,
    data: {
      game_logs: 35770,
      latest_game_date: '2026-06-20',
    },
    freshness: {
      is_current: true,
      is_stale: false,
      freshness_state: 'current',
      reason_codes: [],
      label: 'Current baseball data through 2026-06-20.',
      limitations: [],
    },
  }
  const morning = {
    ...postgame,
    last_successful_sync_run: { job_name: 'daily_sync' },
  }

  assert.equal(getSyncStatusView(postgame, { now }).lastCheckedLabel, 'Last checked')
  assert.equal(getSyncStatusView(postgame, { now }).lastDataUpdateLabel, 'Last data update')
  assert.equal(getSyncStatusView(morning, { now }).lastCheckedLabel, 'Last checked')
  assert.equal(getSyncStatusView(morning, { now }).lastDataUpdateLabel, 'Last data update')
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
  assert.ok(dataTrustSource.includes('Last checked means BaseballOS ran.'))
  assert.equal(dataTrustSource.includes('sync.data?.data?.latest_game_date'), false)
  assert.equal(dataTrustSource.includes('<SyncStatus />'), false)
})
