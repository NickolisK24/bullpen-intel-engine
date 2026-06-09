import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

import {
  emptyBoard,
  makeBoard,
  populatedBoard,
  rosterContextBoard,
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
  for (const label of ['Available Tonight', 'Monitor', 'Limited', 'Avoid', 'Unavailable Pitchers']) {
    assert.ok(htmlIncludes(html, label), `missing group: ${label}`)
  }
  // Available Tonight must appear before Unavailable Pitchers on the board.
  assert.ok(html.indexOf('Available Tonight') < html.lastIndexOf('Unavailable Pitchers'))
})

test('renders bullpen stress from the backend payload', () => {
  const html = render(populatedBoard)

  assert.ok(htmlIncludes(html, 'Bullpen Stress: Elevated'))
  assert.ok(htmlIncludes(html, 'Bullpen workload pressure is elevated.'))
  assert.ok(htmlIncludes(html, 'Availability classifications are workload-based only.'))
  assert.ok(!htmlIncludes(html, 'Bullpen workload is elevated.'))
  assert.ok(!htmlIncludes(html, 'Stress Score'))
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
  assert.ok(htmlIncludes(html, 'No unavailable pitchers are shown right now.'))
})

test('stale data surfaces existing trust messaging', () => {
  const html = render(staleBoard)
  assert.ok(htmlIncludes(html, 'Stale'))
  assert.ok(htmlIncludes(html, 'Bullpen Stress: No Read'))
  assert.ok(htmlIncludes(html, 'Bullpen stress read is limited by data freshness.'))
  assert.ok(htmlIncludes(html, 'Limited read - review freshness before treating this as current.'))
  assert.ok(htmlIncludes(html, 'Stale Workload'))
  assert.ok(htmlIncludes(html, 'Roster Unknown'))
  assert.ok(htmlIncludes(html, 'Roster status unavailable'))
  assert.ok(htmlIncludes(html, 'Bullpen Arms'))
  assert.ok(htmlIncludes(html, 'Roster Status Coverage'))
  assert.ok(htmlIncludes(html, 'outside the active freshness window'))
  assert.ok(htmlIncludes(html, 'Data freshness limits confidence'))
  assert.ok(htmlIncludes(html, 'Historical baseball data through 2026-04-01.'))
  assert.ok(!htmlIncludes(html, 'Inactive Context'))
})

test('unavailable roster pitchers render status labels without active availability', () => {
  const html = render(rosterContextBoard)
  assert.ok(htmlIncludes(html, 'Unavailable Pitchers'))
  assert.ok(htmlIncludes(html, 'Graham Ashcraft'))
  assert.ok(htmlIncludes(html, 'IL-60'))
  assert.ok(htmlIncludes(html, 'Jose Franco'))
  assert.ok(htmlIncludes(html, '40-Man Only'))
  assert.ok(htmlIncludes(html, 'Connor Phillips'))
  assert.ok(htmlIncludes(html, 'Minors'))
  assert.ok(htmlIncludes(html, 'Availability status: Unavailable'))
  assert.ok(htmlIncludes(html, 'not available for bullpen planning'))
  assert.ok(!htmlIncludes(html, 'Availability status: Available'))
  assert.ok(!htmlIncludes(html, 'Inactive Context'))
  assert.ok(!htmlIncludes(html, 'inactive context'))
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
  assert.equal(view.getBullpenStressView(populatedBoard.stress).label, 'Elevated')
  assert.equal(view.getBullpenStressView(staleBoard.stress).label, 'No Read')
  assert.equal(view.getBullpenStressView(staleBoard.stress).isLimited, true)
  assert.equal(view.getBoardCardView(staleBoard.groups[1].pitchers[0]).eligibility.label, 'Stale Workload')
  assert.equal(view.getBoardCardView(staleBoard.groups[1].pitchers[0]).rosterStatus.label, 'Roster Unknown')
  assert.equal(view.getBoardCardView(rosterContextBoard.groups[4].pitchers[0]).rosterStatus.label, 'IL-60')
  assert.equal(view.getBoardCardView(rosterContextBoard.groups[4].pitchers[1]).rosterStatus.label, '40-Man Only')
  assert.equal(view.getRosterStatusSummaryView(staleBoard.roster_status).label, 'Roster status unavailable')
  assert.equal(view.getRosterStatusSummaryView(rosterContextBoard.roster_status).unavailablePitchersCount, 3)
  assert.equal(view.getRosterStatusSummaryView(rosterContextBoard.roster_status).coverageLabel, '100%')
})
