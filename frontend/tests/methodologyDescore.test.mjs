import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
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

const { MethodologyView } = await server.ssrLoadModule('/src/components/methodology/Methodology.jsx')

const render = (element) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, element),
)
const visibleText = (html) => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const htmlIncludes = (html, text) => html.includes(text)

const methodologyData = {
  fatigue_engine: {
    title: 'Bullpen Recent Workload Read',
    summary: (
      'BaseballOS combines four recent-workload inputs: pitch count load (35%), '
      + 'rest days (30%), appearance frequency (20%), and innings load (15%). '
      + 'Public pages show baseball-language availability and workload context rather than a numeric grade.'
    ),
    components: [
      {
        name: 'Pitch Count Load',
        weight: '35%',
        rationale: 'Pitch totals show recent arm volume in the workload window.',
      },
      {
        name: 'Rest Days',
        weight: '30%',
        rationale: 'Days since last appearance are the primary recovery signal.',
      },
      {
        name: 'Appearance Frequency',
        weight: '20%',
        rationale: 'Repeated appearances can narrow bullpen choices even when individual outings are short.',
      },
      {
        name: 'Innings Load',
        weight: '15%',
        rationale: 'Innings pitched add context beyond the raw number of appearances.',
      },
    ],
    interpretation: [
      'More rest and lighter recent work generally support availability.',
      'Repeated appearances, elevated pitch counts, and limited recovery increase workload concern.',
      'The final public read is explained with recent-work evidence rather than a numeric grade.',
    ],
    risk_tiers: [
      { level: 'LOW', range: '0-24', interpretation: 'Fresh and available.' },
      { level: 'MODERATE', range: '25-49', interpretation: 'Some recent use. Monitor.' },
      { level: 'HIGH', range: '50-80', interpretation: 'Heavy recent workload. Use with caution.' },
      { level: 'CRITICAL', range: '81-100', interpretation: 'Recent usage strongly points toward rest.' },
    ],
    excluded: {
      name: 'Leverage Index',
      reason: 'Leverage Index is excluded because the public game log feed does not reliably expose it.',
    },
  },
  insights: {
    title: 'Recent Workload vs. Next-Outing ERA (Exploratory, Secondary)',
    summary: 'Grouped by Low / Moderate / High / Critical score tiers.',
    finding: 'HIGH and CRITICAL workload reads showed a tier-based finding.',
    samples: { LOW: 0, MODERATE: 16385, HIGH: 14495, CRITICAL: 6 },
  },
  data_sources: [
    {
      name: 'MLB Stats API',
      url: 'https://example.test/mlb',
      use: 'Primary source for rosters, game logs, and box scores.',
    },
  ],
  stack: ['React', 'Vite'],
}

test('Methodology route content renders with workload inputs and baseball-unit explanations', () => {
  const html = render(React.createElement(MethodologyView, { data: methodologyData }))
  const text = visibleText(html)

  assert.ok(text.includes('Methodology'))
  assert.ok(text.includes('Bullpen Recent Workload Read'))
  assert.ok(text.includes('Reliability Check'))

  for (const required of [
    'Pitch Count Load',
    '35%',
    'Pitch totals',
    'Rest Days',
    '30%',
    'Days since last appearance',
    'Appearance Frequency',
    '20%',
    'Repeated appearances',
    'Innings Load',
    '15%',
    'Innings pitched',
    'Public Read',
    'Data Sources',
    'Known Limitations',
    'Leverage Index',
  ]) {
    assert.ok(text.includes(required), required)
  }

  assert.ok(htmlIncludes(html, 'id="methodology"'))
  assert.ok(htmlIncludes(html, 'id="data-sources"'))
  assert.ok(htmlIncludes(html, 'id="known-limitations"'))
})

test('Methodology does not render public workload score ranges or risk-tier cards', () => {
  const html = render(React.createElement(MethodologyView, { data: methodologyData }))
  const text = visibleText(html)

  for (const forbidden of [
    '0 to 100 workload index',
    '0–100',
    '0-100',
    '0–24',
    '0-24',
    '25–49',
    '25-49',
    '50–80',
    '50-80',
    '81–100',
    '81-100',
    'Risk Tiers',
    'LOW',
    'MODERATE',
    'HIGH',
    'CRITICAL',
  ]) {
    assert.equal(text.includes(forbidden), false, forbidden)
  }

  assert.equal(/Low\s+0[-–]24/i.test(text), false)
  assert.equal(/Moderate\s+25[-–]49/i.test(text), false)
  assert.equal(/High\s+50[-–]80/i.test(text), false)
  assert.equal(/Critical\s+81[-–]100/i.test(text), false)
})

test('Methodology does not render the exploratory ERA section or hidden tier framing', () => {
  const html = render(React.createElement(MethodologyView, { data: methodologyData }))
  const text = visibleText(html)

  for (const forbidden of [
    'Recent Workload vs. Next-Outing ERA',
    'Exploratory, Secondary',
    'Sample sizes:',
    'Grouped by Low / Moderate / High / Critical score tiers.',
    'tier-based finding',
    'LOW n=',
    'MODERATE n=',
    'HIGH n=',
    'CRITICAL n=',
  ]) {
    assert.equal(text.includes(forbidden), false, forbidden)
  }
})
