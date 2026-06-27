import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
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
const render = (payload) => renderToStaticMarkup(React.createElement(BullpenComparisonView, { payload }))

test('renders side-by-side snapshot with both teams and their counts', () => {
  const html = render(differingComparison)
  assert.ok(htmlIncludes(html, 'Side-by-side Bullpen Read'))
  assert.ok(htmlIncludes(html, 'Aces'))
  assert.ok(htmlIncludes(html, 'Bears'))
  assert.ok(htmlIncludes(html, 'Available'))
  assert.ok(htmlIncludes(html, 'Total relievers'))
})

test('renders deterministic comparison observations naming the team with more', () => {
  const html = render(differingComparison)
  assert.ok(htmlIncludes(html, 'Aces currently has more relievers classified Available.'))
  assert.ok(htmlIncludes(html, 'Bears currently has more relievers marked Avoid or Unavailable.'))
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
  assert.ok(htmlIncludes(html, 'outside the 14-day freshness window'))
})

test('renders both full bullpen boards beneath the comparison', () => {
  const html = render(differingComparison)
  // Board section labels come from BullpenBoardView's groups.
  assert.ok(htmlIncludes(html, 'Available group'))
  // Both team headings present.
  const acesIdx = html.indexOf('Aces')
  const bearsBoardIdx = html.lastIndexOf('Bears')
  assert.ok(acesIdx > -1 && bearsBoardIdx > -1)
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
