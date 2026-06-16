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
const { formatConfidence } = await server.ssrLoadModule('/src/components/bullpen/availabilityView.js')

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
  assert.ok(htmlIncludes(html, 'Data: Outside Freshness Window'))
})

test('AvailabilitySummary renders status, confidence, reasons, and limitations for every fixture', () => {
  for (const row of availabilityFixtureRows) {
    const status = row.availability.availability_status
    const confidence = formatConfidence(row.availability.confidence)
    const html = renderToStaticMarkup(
      React.createElement(AvailabilitySummary, { availability: row.availability }),
    )

    assert.ok(htmlIncludes(html, 'Final Availability'))
    assert.ok(htmlIncludes(html, status))
    assert.ok(htmlIncludes(html, 'Roster Status'))
    assert.ok(htmlIncludes(html, 'Workload Read'))
    assert.ok(htmlIncludes(html, confidence))
    assert.ok(htmlIncludes(html, 'Data Status'))
    assert.ok(htmlIncludes(html, 'Final Availability Reasons'))
    assert.ok(htmlIncludes(html, 'Limitations'))

    for (const reason of row.availability.reasons) {
      assert.ok(htmlIncludes(html, reason))
    }
    for (const limitation of row.availability.limitations) {
      assert.ok(htmlIncludes(html, limitation))
    }
  }
})

test('AvailabilitySummary separates roster-adjusted final availability from workload signal', () => {
  const finalAvailability = {
    availability_status: 'Unavailable',
    confidence: 'high',
    data_state: 'fresh',
    reasons: ['Roster status: IL-60.'],
    limitations: ['Unavailable due to roster status; not available for bullpen planning.'],
    roster_status: {
      status: 'IL_60',
      label: 'IL-60',
      confidence: 'high',
      is_authoritative: true,
      is_inactive_context: true,
    },
  }
  const workloadSignal = {
    availability_status: 'Available',
    confidence: 'high',
    data_state: 'fresh',
    reasons: ['Workload is light.'],
    limitations: ['No injury information available'],
  }

  const html = renderToStaticMarkup(
    React.createElement(AvailabilitySummary, {
      availability: finalAvailability,
      workloadSignal,
    }),
  )

  assert.ok(htmlIncludes(html, 'Final Availability'))
  assert.ok(htmlIncludes(html, 'Final availability: Unavailable'))
  assert.ok(htmlIncludes(html, 'Roster Status'))
  assert.ok(htmlIncludes(html, 'IL-60'))
  assert.ok(htmlIncludes(html, 'Workload Signal'))
  assert.ok(htmlIncludes(html, 'Workload signal: Available'))
  assert.ok(htmlIncludes(html, 'not available for bullpen planning'))
  assert.equal(htmlIncludes(html, 'Final availability: Available'), false)
})
