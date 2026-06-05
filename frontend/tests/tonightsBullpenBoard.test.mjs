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

const { default: BullpenBoardView } = await server.ssrLoadModule(
  '/src/components/bullpen/board/BullpenBoardView.jsx',
)
const view = await server.ssrLoadModule(
  '/src/components/bullpen/board/tonightsBullpenBoardView.js',
)

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (board) => renderToStaticMarkup(React.createElement(BullpenBoardView, { board }))

test('renders all five availability groups in order', () => {
  const html = render(populatedBoard)
  for (const label of ['Available Tonight', 'Monitor', 'Limited', 'Avoid', 'Unavailable']) {
    assert.ok(htmlIncludes(html, label), `missing group: ${label}`)
  }
  // Available Tonight must appear before Unavailable on the board.
  assert.ok(html.indexOf('Available Tonight') < html.indexOf('Unavailable'))
})

test('renders pitcher cards with name, status, fatigue, confidence and short reason', () => {
  const html = render(populatedBoard)
  assert.ok(htmlIncludes(html, 'Larry Limited'))
  assert.ok(htmlIncludes(html, 'Availability status: Limited'))
  assert.ok(htmlIncludes(html, '29 pitches yesterday'))   // short reason
  assert.ok(htmlIncludes(html, 'Fatigue'))
  assert.ok(htmlIncludes(html, 'Confidence'))
  assert.ok(htmlIncludes(html, 'Medium'))                 // confidence formatted
})

test('Why? disclosure surfaces engine reasons and limitations', () => {
  const html = render(populatedBoard)
  assert.ok(htmlIncludes(html, 'Why?'))
  assert.ok(htmlIncludes(html, '3 appearances in 5 days'))           // a reason
  assert.ok(htmlIncludes(html, 'No injury information available'))   // a limitation
})

test('empty board shows a friendly empty state, not a blank surface', () => {
  const html = render(emptyBoard)
  assert.ok(htmlIncludes(html, 'No pitchers to show for this team'))
})

test('groups with no pitchers render their own empty copy', () => {
  // Only the Available group is populated; the other four are empty.
  const board = makeBoard({
    cardsByStatus: { Available: populatedBoard.groups[0].pitchers },
  })
  const html = render(board)
  assert.ok(htmlIncludes(html, 'No arms are ruled out tonight.')) // Unavailable empty copy
})

test('stale data surfaces existing trust messaging', () => {
  const html = render(staleBoard)
  assert.ok(htmlIncludes(html, 'Stale'))
  assert.ok(htmlIncludes(html, 'outside the active freshness window'))
  assert.ok(htmlIncludes(html, 'Data freshness limits confidence'))
  assert.ok(htmlIncludes(html, 'Historical baseball data through 2026-04-01.'))
})

test('team switching reflects the selected team in the heading', () => {
  const angels = render(makeBoard({ team: { team_id: 1, team_name: 'Anaheim', team_abbreviation: 'ANA' } }))
  const yanks = render(makeBoard({ team: { team_id: 2, team_name: 'New York', team_abbreviation: 'NYY' } }))
  assert.ok(htmlIncludes(angels, 'Anaheim'))
  assert.ok(!htmlIncludes(angels, 'New York'))
  assert.ok(htmlIncludes(yanks, 'New York'))
})

test('does not expose raw governance fields or jargon on the baseball surface', () => {
  const html = render(populatedBoard).toLowerCase()
  for (const term of ['ranking_applied', 'selection_made', 'contract', 'governance', 'fail_closed', 'certified']) {
    assert.ok(!html.includes(term), `leaked governance term: ${term}`)
  }
})

test('view helpers group, total, and detect stale freshness deterministically', () => {
  const groups = view.getBoardGroups(populatedBoard)
  assert.deepEqual(groups.map(g => g.status), ['Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable'])

  const totals = view.getBoardTotals(populatedBoard)
  assert.equal(totals.total, 6)
  assert.equal(totals.isEmpty, false)
  assert.equal(view.getBoardTotals(emptyBoard).isEmpty, true)

  assert.equal(view.getBoardFreshnessView(populatedBoard.freshness).isStale, false)
  assert.equal(view.getBoardFreshnessView(staleBoard.freshness).isStale, true)
})
