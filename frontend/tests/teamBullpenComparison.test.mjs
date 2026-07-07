import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import {
  differingComparison,
  similarComparison,
  staleComparison,
} from './fixtures/bullpenComparisonFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { default: BullpenComparisonView } = await server.ssrLoadModule(
  '/src/components/bullpen/board/BullpenComparisonView.jsx',
)
const view = await server.ssrLoadModule(
  '/src/components/bullpen/board/teamBullpenComparisonView.js',
)

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (payload) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, React.createElement(BullpenComparisonView, { payload })),
)

test('renders side-by-side snapshot with both teams and their counts', () => {
  const html = render(differingComparison)
  assert.ok(htmlIncludes(html, 'Side-by-side Bullpen Read'))
  assert.ok(htmlIncludes(html, 'Aces'))
  assert.ok(htmlIncludes(html, 'Bears'))
  assert.ok(htmlIncludes(html, 'Available'))
  assert.ok(htmlIncludes(html, 'Total relievers'))
})

test('comparison snapshot shows one public Unavailable row with combined raw counts', () => {
  const v = view.getComparisonView(differingComparison)
  const unavailableRows = v.snapshot.filter(row => row.label === 'Unavailable')

  assert.deepEqual(v.snapshot.map(row => row.label), [
    'Available',
    'On Watch',
    'Limited',
    'Unavailable',
  ])
  assert.equal(unavailableRows.length, 1)
  assert.equal(unavailableRows[0].valueA, 2)
  assert.equal(unavailableRows[0].valueB, 5)
})

test('renders deterministic comparison observations naming the team with more', () => {
  const html = render(differingComparison)
  assert.ok(htmlIncludes(html, 'Aces currently has more relievers classified Available.'))
  assert.ok(htmlIncludes(html, 'Bears currently has more relievers marked Unavailable.'))
  assert.equal(htmlIncludes(html, 'Avoid or Unavailable'), false)
})

test('each observation explains itself with both raw counts', () => {
  const html = render(differingComparison)
  assert.ok(htmlIncludes(html, 'Why?'))
  assert.ok(htmlIncludes(html, 'Aces Available: 6.'))
  assert.ok(htmlIncludes(html, 'Bears Available: 3.'))
})

test('similar distributions read as similar, not as a winner', () => {
  const html = render(similarComparison)
  assert.ok(htmlIncludes(html, 'Both bullpens currently show similar availability distributions.'))
})

test('stale bullpen surfaces freshness limitations and degraded confidence', () => {
  const html = render(staleComparison)
  assert.ok(htmlIncludes(html, 'Recent workload unclear — read with caution'))
  assert.ok(htmlIncludes(html, 'Workload Read: Unclear Read'))
  assert.ok(htmlIncludes(html, 'one or both bullpens have degraded freshness'))
  // The board-level freshness limitation text now lives on the linked team
  // boards, not inside the comparison (the boards are no longer embedded).
})

test('links to both team boards instead of embedding two full boards', () => {
  const html = render(differingComparison)
  // phase-0-clarity/03: the comparison compares; the full boards live on the
  // Team Board tab behind links.
  assert.equal(htmlIncludes(html, 'Available group'), false)
  assert.equal(htmlIncludes(html, "Tonight's Bullpen Board"), false)
  assert.ok(htmlIncludes(html, 'Full Team Boards'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=ACE&amp;source=comparison"'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=BEA&amp;source=comparison"'))
  assert.ok(htmlIncludes(html, 'Open the Aces board'))
  assert.ok(htmlIncludes(html, 'Open the Bears board'))
})

test('empty payload prompts for two teams instead of crashing', () => {
  const html = render({})
  assert.ok(htmlIncludes(html, 'Pick two teams to compare'))
})

test('exposes no grading, ranking, or recommendation language', () => {
  const html = render(differingComparison).toLowerCase()
  for (const term of ['best', 'better', 'stronger', 'superior', 'recommend', 'win probability', 'team score', 'bullpen grade', 'ranking_applied']) {
    assert.ok(!html.includes(term), `leaked term: ${term}`)
  }
})

test('getComparisonView maps labels, observations, and degraded confidence', () => {
  const v = view.getComparisonView(differingComparison)
  assert.equal(v.hasComparison, true)
  assert.equal(v.labelA, 'Aces')
  assert.equal(v.observations.length, 3)
  assert.equal(v.observations[0].leader, 'A')

  assert.equal(view.getComparisonView(staleComparison).isDegraded, true)
  assert.equal(view.getComparisonView({}).hasComparison, false)
})
