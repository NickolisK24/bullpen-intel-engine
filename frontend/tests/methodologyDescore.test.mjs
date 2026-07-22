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

const render = () => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, React.createElement(MethodologyView)),
)
const decodeEntities = (value) => value
  .replace(/&#x27;/g, "'").replace(/&#39;/g, "'").replace(/&apos;/g, "'")
  .replace(/&mdash;/g, '—').replace(/&ndash;/g, '–')
  .replace(/&middot;/g, '·').replace(/&bull;/g, '•')
  .replace(/&rsquo;/g, '’').replace(/&lsquo;/g, '‘')
  .replace(/&ldquo;/g, '“').replace(/&rdquo;/g, '”')
  .replace(/&amp;/g, '&')
const visibleText = (html) => decodeEntities(html.replace(/<[^>]*>/g, ' ')).replace(/\s+/g, ' ').trim()
const html = render()
const text = visibleText(html)

// The worked example is anchored to the canonical availability rule proven by
// backend/tests/test_availability.py::TestAvailabilityClassification
// ::test_monitor_for_light_yesterday_workload — one 16-pitch appearance
// yesterday classifies as STATUS_MONITOR, whose public label is "On Watch".
const EXAMPLE_PITCHES = '16 pitches'
const EXAMPLE_STATUS = 'On Watch'

test('Methodology stays the /methodology route and leads with the public read, not a formula', async () => {
  const app = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8')
  assert.ok(app.includes("path: '/methodology'"))

  // Exactly one primary heading, and it frames the reading of a bullpen.
  assert.equal((html.match(/<h1\b/g) || []).length, 1)
  assert.match(html, /<h1[^>]*>How BaseballOS reads a bullpen<\/h1>/)

  // The opening names the evidence it examines before any mechanism detail.
  const intro = text.indexOf('reads recent workload, rest, role and roster')
  const examines = text.indexOf('The evidence behind a read')
  assert.ok(intro > -1)
  assert.ok(examines > intro)
})

test('Methodology uses the canonical public vocabulary and no implementation-first artifacts', () => {
  for (const status of ['Available', 'On Watch', 'Limited', 'Unavailable']) {
    assert.ok(text.includes(status), status)
  }
  for (const state of ['Fresh', 'Stretched', 'Vulnerable']) {
    assert.ok(text.includes(state), state)
  }
  // The internal Avoid tier is never surfaced as a public status.
  assert.equal(/\bAvoid\b/.test(text), false)

  const forbidden = [
    '0-100', '0–100', '0 to 100', '[0, 100]',
    '35%', '30%', '20%', '15%',
    '35 / 30 / 20 / 15', 'weighted sum', 'sub-read', 'composite',
    'LOW', 'MODERATE', 'HIGH', 'CRITICAL',
    'Risk Tier', 'risk score', 'fatigue score', 'Fatigue Score',
    'Leverage Index', 'radar', 'Stack',
    'V1', 'V2', 'V3', 'V4', 'COIN',
    'algorithm', 'proprietary', 'black box', 'optimal', 'Recommended',
    'reason_code', 'reason code', 'raw_score', 'endpoint',
  ]
  for (const term of forbidden) {
    assert.equal(text.includes(term), false, term)
  }
})

test('Methodology explains workload, rest, role, and roster evidence with honest boundaries', () => {
  // Workload evidence: recent appearances, pitch counts, windows.
  assert.ok(text.includes('Pitch counts'))
  assert.ok(text.includes('Recent appearances'))
  // Rest evidence.
  assert.ok(text.includes('Days since the last appearance'))
  // Observed role/eligibility — usage, described without a manager-intent claim.
  assert.ok(text.includes('Observed relief usage and eligibility'))
  assert.ok(text.includes('not a manager’s plan'))
  // Roster context is not a health claim.
  assert.ok(text.includes('Roster context describes'))
  assert.ok(text.includes('The absence of a public flag is not a health claim.'))
  // Unknown and zero are different.
  assert.ok(text.includes('never treated as zero'))
  assert.ok(text.includes('stays partly unknown'))
  // Workload is not quality; team state is not a ranking.
  assert.ok(text.includes('not a measure of pitcher quality'))
  assert.ok(text.includes('not a ranking'))
})

test('Methodology worked example is illustrative and follows State -> Why -> Evidence -> Freshness -> Limitations', () => {
  assert.ok(text.includes('Illustrative example'))
  assert.ok(text.includes('not current MLB data'))
  assert.ok(text.includes('Example Reliever'))
  assert.ok(text.includes(EXAMPLE_STATUS))
  assert.ok(text.includes(EXAMPLE_PITCHES))

  // Order is checked within the worked-example block so unrelated occurrences of
  // these words elsewhere on the page cannot satisfy the sequence.
  const start = text.indexOf('Illustrative example')
  const end = text.indexOf('When BaseballOS publishes')
  const block = end > start ? text.slice(start, end) : text.slice(start)
  let previous = -1
  for (const label of ['Illustrative example', 'State', 'Why', 'Evidence', 'Freshness', 'Limitations']) {
    const index = block.indexOf(label)
    assert.ok(index > previous, label)
    previous = index
  }

  // No prediction, health, manager-intent, or live-data claim in the example.
  assert.ok(text.includes('does not predict whether he will appear'))
  assert.ok(text.includes('not live tracking'))
})

test('Methodology explains freshness, publication gates, and refusals without duplicating other pages', () => {
  assert.ok(text.includes('data-through date'))
  assert.ok(text.includes('Stale data is labeled'))
  assert.ok(text.includes('may publish no read'))
  assert.ok(text.includes('not real-time'))
  assert.ok(text.includes('does not predict whether a pitcher will appear'))

  // Refusals render from the canonical boundary module.
  assert.ok(text.includes("No predictions. It describes today's context, not tomorrow's outcome."))
  assert.ok(text.includes('No betting advice. It is not a wagering or odds product.'))
  assert.ok(text.includes('Quiet or withheld output is intentional.'))
})

test('Methodology links the live product and canonical pages, and exposes no admin or internal targets', () => {
  const hrefs = [...html.matchAll(/href="([^"]+)"/g)].map(m => m[1])
  for (const target of ['/how-to-read', '/trust', '/bullpen', '/bullpen?view=compare', '/bullpen?view=pitchers']) {
    assert.ok(hrefs.includes(target), target)
  }
  // Descriptive labels, never generic.
  assert.ok(text.includes('How to Read'))
  assert.ok(text.includes('Data & Trust'))
  assert.ok(text.includes('Reliever Finder'))
  assert.equal(/Learn more|View details|Read more|Click here/i.test(text), false)
  // No admin surfaces or internal docs from the public page.
  assert.equal(hrefs.some(href => /\/admin|\/docs|token=|\.md$/.test(href)), false)
})

test('Methodology preserves the inbound Data & Trust anchors and a semantic heading order', () => {
  for (const id of ['methodology', 'data-sources', 'known-limitations']) {
    assert.ok(html.includes(`id="${id}"`), id)
  }
  // h1 precedes the first h2.
  const h1 = html.indexOf('<h1')
  const h2 = html.indexOf('<h2')
  assert.ok(h1 > -1 && h2 > h1)
})

test('public Methodology payload source still carries no score construction details', async () => {
  const source = await readFile(
    new URL('../../backend/api/methodology.py', import.meta.url),
    'utf8',
  )
  for (const forbidden of [
    '0 to 100', '0–100', '0-100', '[0, 100]',
    'sub-read', 'Sub-score', 'weighted score', 'weighted sum',
    '50, 90, and 120', '2d=55', '70/15 weighted',
    'risk_tiers', 'Recent Workload vs. Next-Outing ERA',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})
