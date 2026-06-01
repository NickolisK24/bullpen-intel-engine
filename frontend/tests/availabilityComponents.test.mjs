import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

import { availabilityFixtureRows } from './fixtures/availabilityStatusFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { default: AvailabilityBadge } = await server.ssrLoadModule('/src/components/bullpen/AvailabilityBadge.jsx')
const { default: AvailabilitySummary } = await server.ssrLoadModule('/src/components/bullpen/AvailabilitySummary.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

test('AvailabilityBadge renders every availability status label', () => {
  for (const row of availabilityFixtureRows) {
    const status = row.availability.availability_status
    const html = renderToStaticMarkup(
      React.createElement(AvailabilityBadge, { availability: row.availability, showDataState: true }),
    )

    assert.ok(htmlIncludes(html, status))
    assert.ok(htmlIncludes(html, `Availability status: ${status}`))
  }
})

test('AvailabilityBadge renders non-current data state when requested', () => {
  const staleFixture = availabilityFixtureRows.find(row => row.availability.data_state === 'stale')
  const html = renderToStaticMarkup(
    React.createElement(AvailabilityBadge, { availability: staleFixture.availability, showDataState: true }),
  )

  assert.ok(htmlIncludes(html, 'Monitor'))
  assert.ok(htmlIncludes(html, 'Data: Stale'))
})

test('AvailabilitySummary renders status, confidence, reasons, and limitations for every fixture', () => {
  for (const row of availabilityFixtureRows) {
    const status = row.availability.availability_status
    const confidence = `${row.availability.confidence.charAt(0).toUpperCase()}${row.availability.confidence.slice(1)}`
    const html = renderToStaticMarkup(
      React.createElement(AvailabilitySummary, { availability: row.availability }),
    )

    assert.ok(htmlIncludes(html, 'Availability Status'))
    assert.ok(htmlIncludes(html, status))
    assert.ok(htmlIncludes(html, 'Confidence'))
    assert.ok(htmlIncludes(html, confidence))
    assert.ok(htmlIncludes(html, 'Data Status'))
    assert.ok(htmlIncludes(html, 'Reasons'))
    assert.ok(htmlIncludes(html, 'Limitations'))

    for (const reason of row.availability.reasons) {
      assert.ok(htmlIncludes(html, reason))
    }
    for (const limitation of row.availability.limitations) {
      assert.ok(htmlIncludes(html, limitation))
    }
  }
})
