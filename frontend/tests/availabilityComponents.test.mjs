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
const { formatConfidence, getAvailabilityStatusLabel } = await server.ssrLoadModule('/src/components/bullpen/availabilityView.js')
const { CURRENT_READ_AVAILABILITY_RELATIONSHIP } = await server.ssrLoadModule('/src/utils/bullpenConcepts.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

test('AvailabilityBadge renders every availability status label', () => {
  for (const row of availabilityFixtureRows) {
    const status = row.availability.availability_status
    const label = getAvailabilityStatusLabel(status)
    const html = renderToStaticMarkup(
      React.createElement(AvailabilityBadge, { availability: row.availability, showDataState: true }),
    )

    assert.ok(htmlIncludes(html, label))
    assert.ok(htmlIncludes(html, `Availability status: ${label}`))
  }
})

test('AvailabilityBadge renders non-current data state when requested', () => {
  const staleFixture = availabilityFixtureRows.find(row => row.availability.data_state === 'stale')
  const html = renderToStaticMarkup(
    React.createElement(AvailabilityBadge, { availability: staleFixture.availability, showDataState: true }),
  )

  assert.ok(htmlIncludes(html, 'On Watch'))
  assert.ok(htmlIncludes(html, 'Data: Outside Freshness Window'))
})

test('AvailabilitySummary keeps the canonical answer and metadata compact by default', () => {
  for (const row of availabilityFixtureRows) {
    const status = row.availability.availability_status
    const label = getAvailabilityStatusLabel(status)
    const confidence = formatConfidence(row.availability.confidence)
    const html = renderToStaticMarkup(
      React.createElement(AvailabilitySummary, { availability: row.availability }),
    )

    assert.ok(htmlIncludes(html, 'Availability'))
    assert.ok(htmlIncludes(html, CURRENT_READ_AVAILABILITY_RELATIONSHIP))
    assert.ok(htmlIncludes(html, label))
    assert.ok(htmlIncludes(html, 'Roster Status'))
    assert.ok(htmlIncludes(html, 'Read Confidence'))
    assert.ok(htmlIncludes(html, confidence))
    // H-11: the per-pitcher workload-record family is named Workload Data;
    // 'Data Status' is the separate platform-wide public family.
    assert.ok(htmlIncludes(html, 'Workload Data'))
    assert.equal(htmlIncludes(html, 'Data Status'), false)
    assert.ok(htmlIncludes(html, 'View availability details'))
    assert.ok(htmlIncludes(html, 'aria-expanded="false"'))
    assert.equal(htmlIncludes(html, 'Final Availability Reasons'), false)
    assert.equal(htmlIncludes(html, 'Limitations'), false)
    assert.equal((html.match(/Final availability:/g) || []).length, 1)

    for (const reason of row.availability.reasons) {
      assert.equal(htmlIncludes(html, reason), false)
    }
    for (const limitation of row.availability.limitations) {
      assert.equal(htmlIncludes(html, limitation), false)
    }
  }
})

test('AvailabilitySummary disclosure preserves exact reason order and limitations', () => {
  const availability = {
    availability_status: 'Limited',
    confidence: 'medium',
    data_state: 'fresh',
    reasons: ['First governed reason.', 'Second governed reason.', 'Third governed reason.'],
    limitations: ['No injury information available.', 'No team-reported availability data available.'],
  }
  const html = renderToStaticMarkup(
    React.createElement(AvailabilitySummary, { availability, initialDetailsOpen: true }),
  )

  assert.ok(htmlIncludes(html, 'Hide availability details'))
  assert.ok(htmlIncludes(html, 'aria-expanded="true"'))
  assert.ok(htmlIncludes(html, 'Final Availability Reasons'))
  assert.ok(htmlIncludes(html, 'Limitations'))
  assert.ok(html.indexOf('First governed reason.') < html.indexOf('Second governed reason.'))
  assert.ok(html.indexOf('Second governed reason.') < html.indexOf('Third governed reason.'))
  for (const limitation of availability.limitations) assert.ok(htmlIncludes(html, limitation))
})

test('AvailabilitySummary separates roster-adjusted final availability from workload signal', () => {
  const finalAvailability = {
    availability_status: 'Unavailable',
    confidence: 'high',
    data_state: 'fresh',
    reasons: ['Roster status: 60-Day IL.'],
    limitations: ['Unavailable due to roster status; not available for bullpen planning.'],
    roster_status: {
      status: 'IL_60',
      label: '60-Day IL',
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
      initialDetailsOpen: true,
    }),
  )

  assert.ok(htmlIncludes(html, 'Final Availability'))
  assert.ok(htmlIncludes(html, 'Final availability: Unavailable'))
  assert.ok(htmlIncludes(html, 'Roster Status'))
  assert.ok(htmlIncludes(html, '60-Day IL'))
  assert.ok(htmlIncludes(html, 'Workload Signal'))
  assert.ok(htmlIncludes(html, 'Workload signal: Available'))
  assert.ok(htmlIncludes(html, 'not available for bullpen planning'))
  assert.equal(htmlIncludes(html, 'Final availability: Available'), false)
})
