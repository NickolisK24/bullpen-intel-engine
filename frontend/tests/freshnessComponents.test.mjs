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
  DataThroughStamp,
  FreshnessBadge,
  LastSyncLabel,
  SlateDateStamp,
  StaleDataNotice,
  UnavailableDataState,
} = await server.ssrLoadModule('/src/components/UI/index.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(el)

test('freshness badge renders baseball-facing states', () => {
  const current = render(React.createElement(FreshnessBadge, { state: 'current' }))
  assert.ok(htmlIncludes(current, 'Freshness: Current'))

  const sample = render(React.createElement(FreshnessBadge, {
    freshness: { freshness_state: 'sample' },
  }))
  assert.ok(htmlIncludes(sample, 'Sample intelligence state'))
})

test('freshness metadata can downgrade an explicit current badge', () => {
  const sample = render(React.createElement(FreshnessBadge, {
    state: 'current',
    freshness: { freshness_state: 'sample', sample: true },
  }))
  assert.ok(htmlIncludes(sample, 'Sample intelligence state'))
  assert.equal(htmlIncludes(sample, 'Freshness: Current'), false)

  const stale = render(React.createElement(FreshnessBadge, {
    state: 'current',
    freshness: { freshness_state: 'stale', is_current: false, is_stale: true },
  }))
  assert.ok(htmlIncludes(stale, 'Refresh delayed'))
  assert.equal(htmlIncludes(stale, 'Freshness: Current'), false)

  const retainedSample = render(React.createElement(FreshnessBadge, {
    state: 'current',
    freshness: { status: 'static_sample' },
  }))
  assert.ok(htmlIncludes(retainedSample, 'Sample intelligence state'))
  assert.equal(htmlIncludes(retainedSample, 'Freshness: Current'), false)

  const camelSample = render(React.createElement(FreshnessBadge, {
    state: 'current',
    freshness: { freshnessState: 'sample', dataThrough: '2026-04-01' },
  }))
  assert.ok(htmlIncludes(camelSample, 'Sample intelligence state'))
  assert.equal(htmlIncludes(camelSample, 'Freshness: Current'), false)
})

test('freshness badge treats publishable live payloads as current', () => {
  const live = render(React.createElement(FreshnessBadge, {
    state: 'current',
    freshness: {
      data_through: '2026-07-05',
      is_current: false,
      freshness_state: 'incomplete',
      complete_enough_to_publish: true,
      validations_passed: true,
      slate_coverage: { complete_enough_to_publish: true, validations_passed: true },
    },
  }))

  assert.ok(htmlIncludes(live, 'Freshness: Current'))
  assert.equal(htmlIncludes(live, 'Refresh delayed'), false)
})

test('data-through and last-sync labels format trusted payload values', () => {
  const dataThrough = render(React.createElement(DataThroughStamp, {
    date: '2026-06-26',
  }))
  assert.ok(htmlIncludes(dataThrough, 'Data through Jun 26'))
  assert.equal(htmlIncludes(dataThrough, 'Jun 26, 2026'), false)

  const bullpenDataThrough = render(React.createElement(DataThroughStamp, {
    date: '2026-06-26',
    label: 'Bullpen data through',
  }))
  assert.ok(htmlIncludes(bullpenDataThrough, 'Bullpen data through Jun 26'))

  const slate = render(React.createElement(SlateDateStamp, {
    date: '2026-06-27',
  }))
  assert.ok(htmlIncludes(slate, 'Tonight slate: Jun 27'))
  assert.equal(htmlIncludes(slate, 'Data through Jun 27'), false)

  const lastSync = render(React.createElement(LastSyncLabel, {
    value: '2026-06-26T10:04:00Z',
  }))
  assert.ok(htmlIncludes(lastSync, 'Last synced 6:04 AM ET'))
})

test('stale and unavailable states avoid implementation storage language', () => {
  const stale = render(React.createElement(StaleDataNotice, {
    dataThrough: '2026-06-25',
  }))
  assert.ok(htmlIncludes(stale, 'Refresh delayed'))
  assert.ok(htmlIncludes(stale, 'showing last loaded data from Jun 25.'))
  assert.equal(htmlIncludes(stale, 'snapshot'), false)
  assert.equal(htmlIncludes(stale, 'endpoint'), false)

  const unavailable = render(React.createElement(UnavailableDataState))
  assert.ok(htmlIncludes(unavailable, 'No current bullpen read available.'))
})
