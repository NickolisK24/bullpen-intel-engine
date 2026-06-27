import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

import {
  emptyBoard,
  makeBoard,
  populatedBoard,
  staleBoard,
} from './fixtures/bullpenBoardFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { default: BullpenContextSummary } = await server.ssrLoadModule(
  '/src/components/bullpen/board/BullpenContextSummary.jsx',
)
const { default: BullpenBoardView } = await server.ssrLoadModule(
  '/src/components/bullpen/board/BullpenBoardView.jsx',
)
const view = await server.ssrLoadModule(
  '/src/components/bullpen/board/tonightsBullpenBoardView.js',
)

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const firstDetailsTag = (html) => html.match(/<details[^>]*>/)?.[0] || ''
const renderSummary = (board) => renderToStaticMarkup(React.createElement(BullpenContextSummary, { board }))
const renderBoard = (board) => renderToStaticMarkup(React.createElement(BullpenBoardView, { board }))

test('summary renders a health statement and the bullpen read counts', () => {
  // 5 available, 3 monitor, 2 limited → manageable.
  const board = makeBoard({
    cardsByStatus: {
      Available: Array.from({ length: 5 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
      Monitor: Array.from({ length: 3 }, (_, i) => ({ pitcher_id: 20 + i, name: `M${i}`, availability_status: 'Monitor' })),
      Limited: Array.from({ length: 2 }, (_, i) => ({ pitcher_id: 40 + i, name: `L${i}`, availability_status: 'Limited' })),
    },
  })
  const html = renderSummary(board)
  assert.ok(htmlIncludes(html, 'Bullpen workload appears manageable.'))
  assert.ok(htmlIncludes(html, 'Bullpen Read'))
  assert.ok(htmlIncludes(html, 'Available'))
  assert.ok(htmlIncludes(html, 'Unavailable'))
  assert.ok(htmlIncludes(html, '10 relievers'))
  assert.ok(htmlIncludes(html, '50% available'))
})

test('every context statement explains itself with real counts', () => {
  const html = renderSummary(populatedBoard) // elevated: 2 avail / 6, 2 restricted / 6
  const detailsTag = firstDetailsTag(html)

  assert.ok(htmlIncludes(html, 'Why?'))
  assert.ok(detailsTag)
  assert.ok(!detailsTag.includes('open'))
  assert.ok(htmlIncludes(html, '2 of 6 relievers are classified Available.'))
  assert.ok(htmlIncludes(html, '2 of 6 relievers are Avoid or Unavailable.'))
  assert.ok(htmlIncludes(html, 'Availability classifications are workload-based only.'))
})

test('stale data degrades confidence and communicates limitations', () => {
  const html = renderSummary(staleBoard)
  assert.ok(htmlIncludes(html, 'Workload Read: Unclear Read'))
  assert.ok(htmlIncludes(html, 'treat this bullpen read with caution'))
  assert.ok(htmlIncludes(html, 'outside the active freshness window'))
})

test('empty bullpen renders the no-data context without implying availability', () => {
  const html = renderSummary(emptyBoard)
  assert.ok(htmlIncludes(html, 'No bullpen availability to summarize from the latest completed data.'))
  assert.ok(htmlIncludes(html, 'Workload Read: No Read'))
  assert.ok(htmlIncludes(html, 'Bullpen Read'))
})

test('summary renders nothing when the board carries no context', () => {
  const html = renderSummary({ groups: [], team: {} })
  assert.equal(html, '')
})

test('context summary appears above the availability groups on the full board', () => {
  const html = renderBoard(populatedBoard)
  const summaryIdx = html.indexOf('Bullpen Read')
  const groupIdx = html.indexOf('Available group')
  assert.ok(summaryIdx > -1 && groupIdx > -1)
  assert.ok(summaryIdx < groupIdx, 'bullpen read should render before the groups')
})

test('full board uses stress read instead of a duplicate health statement', () => {
  const html = renderBoard(populatedBoard)
  assert.ok(htmlIncludes(html, 'Overall Availability: Elevated'))
  assert.ok(htmlIncludes(html, 'Bullpen Read'))
  assert.ok(htmlIncludes(html, '2 of 6 relievers are classified Available.'))
  assert.ok(!htmlIncludes(html, 'Bullpen workload is elevated.'))
})

test('context surface exposes no scores, rankings, or governance jargon', () => {
  const html = renderSummary(populatedBoard).toLowerCase()
  for (const term of [
    'ranking_applied', 'selection_made', 'readiness score', 'quality score',
    'composite', 'best option', 'top arm', 'recommend', 'priority score',
  ]) {
    assert.ok(!html.includes(term), `leaked term: ${term}`)
  }
})

test('getBoardContextView maps state, metrics, and degraded confidence', () => {
  const manageable = view.getBoardContextView(makeBoard({
    cardsByStatus: { Available: [{ pitcher_id: 1, name: 'A', availability_status: 'Available' }] },
  }))
  assert.equal(manageable.state, 'manageable')
  assert.equal(manageable.metrics.total, 1)
  assert.equal(manageable.isDegraded, false)
  assert.equal(manageable.snapshot.length, 5)

  const stale = view.getBoardContextView(staleBoard)
  assert.equal(stale.isDegraded, true)
  assert.equal(stale.state, 'constrained')

  assert.equal(view.getBoardContextView({}).hasContext, false)
})
