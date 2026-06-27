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

test('data-through and last-sync labels format trusted payload values', () => {
  const dataThrough = render(React.createElement(DataThroughStamp, {
    date: '2026-06-26',
  }))
  assert.ok(htmlIncludes(dataThrough, 'Data through Jun 26'))
  assert.equal(htmlIncludes(dataThrough, 'Jun 26, 2026'), false)

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
