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
  getAvailabilityDashboardSummaryView,
} = await server.ssrLoadModule('/src/components/dashboard/availabilityDashboardSummaryView.js')
const {
  default: AvailabilityDashboardSummary,
} = await server.ssrLoadModule('/src/components/dashboard/AvailabilityDashboardSummary.jsx')

const staleDominantSummary = {
  mode: 'current_availability',
  is_current_availability: true,
  total_pitchers: 704,
  statuses: {
    Available: 0,
    Monitor: 704,
    Limited: 0,
    Avoid: 0,
    Unavailable: 0,
  },
  confidence: {
    high: 0,
    medium: 0,
    low: 704,
  },
  data_state: {
    fresh: 0,
    stale: 638,
    missing: 64,
    incomplete: 0,
    failed: 2,
  },
  notes: [
    'Recent usage information is missing for most pitchers, so most availability reads are less certain.',
    'Recent usage information is incomplete, so workload data must not be treated as current availability',
  ],
}

const inventorySummary = {
  ...staleDominantSummary,
  mode: 'scored_pitcher_inventory',
  is_current_availability: false,
  notes: [
    'Recent usage information is missing for most pitchers with workload reads, so inventory workload reads are less certain.',
    'Stale workload data is retained here as inventory context, not bullpen availability.',
  ],
}

const withheldSummary = {
  mode: 'current_availability',
  is_current_availability: true,
  total_pitchers: null,
  counts_withheld: true,
  statuses: {
    Available: null,
    Monitor: null,
    Limited: null,
    Unavailable: null,
    Avoid: null,
  },
  confidence: {
    high: null,
    medium: null,
    low: null,
  },
  data_state: {
    fresh: null,
    stale: null,
    missing: null,
    incomplete: null,
    failed: null,
  },
  roster_readiness: {
    capability: 'public_roster_readiness_v1',
    claims_available: false,
    counts_withheld: true,
    readiness_state: 'stale',
  },
  notes: [
    'Current active-roster coverage could not be verified.',
  ],
}

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const visibleText = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

test('formats current-mode availability summary distributions', () => {
  const view = getAvailabilityDashboardSummaryView(staleDominantSummary)

  assert.equal(view.mode, 'current_availability')
  assert.equal(view.modeLabel, 'Current availability')
  assert.equal(view.isCurrentAvailability, true)
  assert.equal(view.totalPitchers, 704)
  assert.equal(view.limitedByData, true)
  assert.equal(view.statusRows.find(row => row.label === 'On Watch').count, 704)
  assert.equal(view.statusTotal, 704)
  assert.equal(view.dominantStatus.label, 'On Watch')
  assert.equal(view.operationalSummary, 'Most current bullpen arms are in the On Watch lane.')
  assert.equal(view.confidenceRows.find(row => row.label === 'Unclear Read').count, 704)
  assert.equal(view.dataStateRows.find(row => row.label === 'Outside Freshness Window').count, 638)
  assert.equal(view.dataStateRows.find(row => row.label === 'No Workload Record').count, 64)
  assert.equal(view.dataStateRows.find(row => row.label === 'Fetch Failed').count, 2)
  assert.equal(view.primaryTrustNote, 'Some relievers have stale, missing, failed, or incomplete workload evidence, so the bullpen picture is less certain.')
})

test('renders dashboard summary without claiming stale data is current', () => {
  const html = renderToStaticMarkup(
    React.createElement(AvailabilityDashboardSummary, { summary: staleDominantSummary }),
  )

  assert.ok(htmlIncludes(html, 'Availability Summary'))
  assert.ok(htmlIncludes(html, 'Current availability'))
  assert.ok(htmlIncludes(html, '704 pitchers with a current read'))
  assert.ok(htmlIncludes(html, 'On Watch'))
  assert.ok(htmlIncludes(html, 'Unclear Read'))
  assert.ok(htmlIncludes(html, 'Outside Freshness Window'))
  assert.ok(htmlIncludes(html, 'No Workload Record'))
  assert.ok(htmlIncludes(html, 'Fetch Failed'))
  assert.ok(htmlIncludes(html, 'Some relievers have stale, missing, failed, or incomplete workload evidence, so the bullpen picture is less certain.'))
  assert.ok(htmlIncludes(html, 'Includes pitchers outside the freshness window, arms with no recent workload record, and arms whose latest workload data did not load.'))
  assert.doesNotMatch(html, /latest_workload_snapshot/)
})

test('renders compact availability summary with secondary evidence collapsed', () => {
  const collapsedHtml = renderToStaticMarkup(
    React.createElement(AvailabilityDashboardSummary, { summary: staleDominantSummary, compact: true }),
  )
  const expandedHtml = renderToStaticMarkup(
    React.createElement(AvailabilityDashboardSummary, { summary: staleDominantSummary, compact: true, initialDetailsOpen: true }),
  )

  assert.ok(htmlIncludes(collapsedHtml, 'Availability Summary'))
  assert.ok(htmlIncludes(collapsedHtml, 'Bullpen Availability Mix'))
  assert.ok(htmlIncludes(collapsedHtml, 'role="img"'))
  assert.ok(htmlIncludes(collapsedHtml, 'Bullpen availability mix. Most current bullpen arms are in the On Watch lane.'))
  assert.ok(htmlIncludes(collapsedHtml, 'On Watch: 704 (100%)'))
  assert.ok(htmlIncludes(collapsedHtml, 'Most current bullpen arms are in the On Watch lane.'))
  assert.ok(htmlIncludes(collapsedHtml, 'Available: 0'))
  assert.ok(htmlIncludes(collapsedHtml, 'On Watch: 704'))
  assert.ok(htmlIncludes(collapsedHtml, 'Limited: 0'))
  assert.ok(htmlIncludes(collapsedHtml, 'Unavailable: 0'))
  assert.equal(htmlIncludes(collapsedHtml, 'Avoid: 0'), false)
  assert.ok(htmlIncludes(collapsedHtml, '100%'))
  assert.ok(htmlIncludes(collapsedHtml, 'On Watch'))
  assert.ok(htmlIncludes(collapsedHtml, 'View Availability Detail'))
  assert.ok(htmlIncludes(collapsedHtml, 'aria-expanded="false"'))
  assert.equal(htmlIncludes(collapsedHtml, 'Workload Read'), false)
  assert.equal(htmlIncludes(collapsedHtml, 'Data State'), false)
  assert.ok(htmlIncludes(expandedHtml, 'Hide Availability Detail'))
  assert.ok(htmlIncludes(expandedHtml, 'Workload Read'))
  assert.ok(htmlIncludes(expandedHtml, 'Data State'))
})

test('renders withheld dashboard counts without zero substitution', () => {
  const view = getAvailabilityDashboardSummaryView(withheldSummary)
  const html = renderToStaticMarkup(
    React.createElement(AvailabilityDashboardSummary, { summary: withheldSummary, compact: true }),
  )
  const text = visibleText(html)

  assert.equal(view.countsWithheld, true)
  assert.equal(view.totalPitchers, null)
  assert.equal(view.statusTotal, null)
  assert.equal(view.dominantStatus, null)
  assert.equal(view.statusRows.find(row => row.label === 'Available').count, null)
  assert.equal(
    view.operationalSummary,
    'Current active-roster coverage could not be verified, so dashboard availability counts are withheld.',
  )
  assert.ok(htmlIncludes(html, 'Withheld pitchers with a current read'))
  assert.ok(htmlIncludes(html, 'Withheld status records'))
  assert.ok(htmlIncludes(html, 'Available: Withheld'))
  assert.ok(htmlIncludes(html, 'On Watch: Withheld'))
  assert.ok(htmlIncludes(html, 'Current active-roster coverage could not be verified, so dashboard availability counts are withheld.'))
  assert.equal(/Available:\s*0/.test(text), false)
  assert.equal(/On Watch:\s*0/.test(text), false)
  assert.equal(/0 status records/.test(text), false)
})

test('availability distribution summary avoids recommendation language', () => {
  const html = renderToStaticMarkup(
    React.createElement(AvailabilityDashboardSummary, { summary: staleDominantSummary, compact: true }),
  )
  const text = visibleText(html)

  assert.equal(/\buse\b|\bbest\b|\bpreferred\b|\brecommended\b|\bmanager should\b/i.test(text), false)
})

test('renders scored pitcher inventory without current availability labeling', () => {
  const view = getAvailabilityDashboardSummaryView(inventorySummary)
  const html = renderToStaticMarkup(
    React.createElement(AvailabilityDashboardSummary, { summary: inventorySummary, compact: true }),
  )

  assert.equal(view.mode, 'scored_pitcher_inventory')
  assert.equal(view.modeLabel, 'Pitcher workload inventory')
  assert.equal(view.isCurrentAvailability, false)
  assert.equal(view.title, 'Pitcher Workload Inventory')
  assert.equal(view.distributionTitle, 'Workload Read Mix')
  assert.equal(view.totalLabel, 'pitchers with workload reads')
  assert.equal(view.primaryTrustNote, 'Some pitchers have stale, missing, failed, or incomplete workload evidence, so the depth picture is less certain.')
  assert.equal(view.operationalSummary, 'Most stored pitcher workload reads are in the On Watch lane.')

  assert.ok(htmlIncludes(html, 'Pitcher Workload Inventory'))
  assert.ok(htmlIncludes(html, 'Pitcher workload inventory · 704 pitchers with workload reads'))
  assert.ok(htmlIncludes(html, 'Workload Read Mix'))
  assert.equal(htmlIncludes(html, 'Current availability'), false)
  assert.equal(htmlIncludes(html, 'Availability Summary'), false)
})
