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
    stale: 640,
    missing: 64,
    incomplete: 0,
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
    'Recent usage information is missing for most scored pitchers, so inventory workload reads are less certain.',
    'Stale workload data is retained here as inventory context, not bullpen availability.',
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
  assert.equal(view.statusRows.find(row => row.label === 'Monitor').count, 704)
  assert.equal(view.statusTotal, 704)
  assert.equal(view.dominantStatus.label, 'Monitor')
  assert.equal(view.operationalSummary, 'Current availability is concentrated in Monitor status.')
  assert.equal(view.confidenceRows.find(row => row.label === 'Unclear Read').count, 704)
  assert.equal(view.dataStateRows.find(row => row.label === 'Recent Usage Unknown').count, 640)
  assert.equal(view.dataStateRows.find(row => row.label === 'Missing').count, 64)
  assert.equal(view.primaryTrustNote, 'Recent usage information is incomplete for many pitchers, so availability reads are less certain.')
})

test('renders dashboard summary without claiming stale data is current', () => {
  const html = renderToStaticMarkup(
    React.createElement(AvailabilityDashboardSummary, { summary: staleDominantSummary }),
  )

  assert.ok(htmlIncludes(html, 'Availability Summary'))
  assert.ok(htmlIncludes(html, 'Current availability'))
  assert.ok(htmlIncludes(html, '704 classified pitchers'))
  assert.ok(htmlIncludes(html, 'Monitor'))
  assert.ok(htmlIncludes(html, 'Unclear Read'))
  assert.ok(htmlIncludes(html, 'Recent Usage Unknown'))
  assert.ok(htmlIncludes(html, 'Recent usage information is incomplete for many pitchers, so availability reads are less certain.'))
  assert.ok(htmlIncludes(html, 'Show pitchers with unclear recent workload or refresh sync data'))
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
  assert.ok(htmlIncludes(collapsedHtml, 'Availability Distribution'))
  assert.ok(htmlIncludes(collapsedHtml, 'role="img"'))
  assert.ok(htmlIncludes(collapsedHtml, 'Current availability is concentrated in Monitor status.'))
  assert.ok(htmlIncludes(collapsedHtml, 'Available: 0'))
  assert.ok(htmlIncludes(collapsedHtml, 'Monitor: 704'))
  assert.ok(htmlIncludes(collapsedHtml, 'Limited: 0'))
  assert.ok(htmlIncludes(collapsedHtml, 'Avoid: 0'))
  assert.ok(htmlIncludes(collapsedHtml, 'Unavailable: 0'))
  assert.ok(htmlIncludes(collapsedHtml, '100%'))
  assert.ok(htmlIncludes(collapsedHtml, 'Monitor'))
  assert.ok(htmlIncludes(collapsedHtml, 'View Availability Evidence'))
  assert.ok(htmlIncludes(collapsedHtml, 'aria-expanded="false"'))
  assert.equal(htmlIncludes(collapsedHtml, 'Workload Read'), false)
  assert.equal(htmlIncludes(collapsedHtml, 'Data State'), false)
  assert.ok(htmlIncludes(expandedHtml, 'Hide Availability Evidence'))
  assert.ok(htmlIncludes(expandedHtml, 'Workload Read'))
  assert.ok(htmlIncludes(expandedHtml, 'Data State'))
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
  assert.equal(view.modeLabel, 'Scored pitcher inventory')
  assert.equal(view.isCurrentAvailability, false)
  assert.equal(view.title, 'Scored Pitcher Inventory')
  assert.equal(view.distributionTitle, 'Workload Status Distribution')
  assert.equal(view.totalLabel, 'scored pitchers')
  assert.equal(view.primaryTrustNote, 'Recent usage information is incomplete for many scored pitchers, so inventory workload reads are less certain.')
  assert.equal(view.operationalSummary, 'Scored pitcher inventory is concentrated in Monitor workload status.')

  assert.ok(htmlIncludes(html, 'Scored Pitcher Inventory'))
  assert.ok(htmlIncludes(html, 'Scored pitcher inventory · 704 scored pitchers'))
  assert.ok(htmlIncludes(html, 'Workload Status Distribution'))
  assert.equal(htmlIncludes(html, 'Current availability'), false)
  assert.equal(htmlIncludes(html, 'Availability Summary'), false)
})
