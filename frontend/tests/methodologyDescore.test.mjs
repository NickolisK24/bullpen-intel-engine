import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
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

const forbiddenPublicMethodologyTerms = [
  '0 to 100',
  '0–100',
  '0-100',
  '[0, 100]',
  '0d=',
  '1d=',
  'thresholds at',
  '0–24',
  '0-24',
  '25–49',
  '25-49',
  '50–80',
  '50-80',
  '81–100',
  '81-100',
]

const methodologyData = {
  fatigue_engine: {
    title: 'Bullpen Recent Workload Read',
    summary: (
      'A weighted composite read that turns recent reliever usage into a '
      + '0 to 100 workload index. Each component returns a 0–100 sub-read; '
      + 'the final index is the weighted sum, clamped to the [0, 100] range.'
    ),
    components: [
      {
        name: 'Pitch Count Load',
        weight: '35%',
        rationale: 'Sub-score scales linearly across thresholds at 50, 90, and 120 pitches.',
      },
      {
        name: 'Rest Days',
        weight: '30%',
        rationale: 'Discrete mapping: 0d=100, 1d=80, 2d=55, 3d=30, 4d=10, 5+d=0.',
      },
      {
        name: 'Appearance Frequency',
        weight: '20%',
        rationale: 'Blends 7-day and 14-day windows (70/15 weighted).',
      },
      {
        name: 'Innings Load',
        weight: '15%',
        rationale: 'Scales linearly across 4 IP and 6 IP thresholds in a 7-day window.',
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
    'Recent pitch volume',
    'Rest Days',
    '30%',
    'Time since the most recent appearance',
    'Appearance Frequency',
    '20%',
    'Repeated use can narrow bullpen flexibility',
    'Innings Load',
    '15%',
    'Recent innings provide a second volume check',
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
    ...forbiddenPublicMethodologyTerms,
    'Risk Tiers',
    'LOW',
    'MODERATE',
    'HIGH',
    'CRITICAL',
  ]) {
    assert.equal(text.includes(forbidden), false, forbidden)
  }

  assert.equal(text.includes('sub-read'), false)
  assert.equal(text.includes('weighted sum'), false)
  assert.equal(text.includes('50, 90, and 120'), false)
  assert.equal(text.includes('2d=55'), false)
  assert.equal(text.includes('70/15 weighted'), false)
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

test('public Methodology payload source has no score construction details', async () => {
  const source = await readFile(
    new URL('../../backend/api/methodology.py', import.meta.url),
    'utf8',
  )

  for (const forbidden of [
    ...forbiddenPublicMethodologyTerms,
    'sub-read',
    'Sub-score',
    'weighted score',
    'weighted sum',
    '50, 90, and 120',
    '2d=55',
    '70/15 weighted',
    'risk_tiers',
    'Recent Workload vs. Next-Outing ERA',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})
