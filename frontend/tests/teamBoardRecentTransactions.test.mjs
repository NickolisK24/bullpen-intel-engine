import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent',
})
after(async () => server.close())
const { default: TeamBoardRecentTransactions, getRecentTransactionRows } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardRecentTransactions.jsx',
)

const transactions = {
  contract: 'team_board_roster_transactions_v1', teamId: 1, dataThrough: '2026-08-18',
  status: 'available', windowStart: '2026-08-11', windowEnd: '2026-08-18',
  limitations: [], currentGroup: { activeCount: 1 },
  events: [
    { eventId: 'newer', pitcherId: 9, name: 'A Very Long Reliever Name', date: '2026-08-18', type: 'recall', label: 'Recalled', direction: 'addition', currentRoster: { status: 'complete', membership: 'active', label: 'Active bullpen' } },
    { eventId: 'older', pitcherId: 7, name: 'Example Arm', date: '2026-08-16', type: 'option', label: 'Optioned', direction: 'removal', currentRoster: { status: 'complete', membership: 'off_active', label: 'Optioned' } },
  ],
  offActiveRecentContributors: {
    status: 'complete', contributors: [
      { pitcherId: 7, name: 'Example Arm', currentRoster: { status: 'complete', membership: 'off_active', label: 'Optioned' } },
    ],
  },
}
const read = { recentTransactions: transactions }
const render = props => renderToStaticMarkup(React.createElement(TeamBoardRecentTransactions, props))

test('frozen events retain backend order, type, date, and current roster state', () => {
  const rows = getRecentTransactionRows(transactions)
  const html = render({ read })
  assert.deepEqual(rows.map(row => row.eventId), ['newer', 'older'])
  assert.ok(html.indexOf('A Very Long Reliever Name') < html.indexOf('Example Arm'))
  assert.match(html, /Recent additions/)
  assert.match(html, /Recent removals/)
  assert.match(html, /Recalled/)
  assert.match(html, /Optioned/)
  assert.match(html, /dateTime="2026-08-18"/)
  assert.match(html, /Current roster: Active bullpen/)
  assert.match(html, /Current roster: Optioned/)
  assert.match(html, /Recent team workload, outside the active group/)
})

test('missing frozen publication is unavailable, never an empty or inferred event history', () => {
  const html = render({ read: { recentTransactions: null } })
  assert.match(html, /does not contain frozen transaction context/)
  assert.doesNotMatch(html, /No verified pitching moves/)
  assert.doesNotMatch(html, /Recalled/)
})

test('loading, partial, unavailable, and certified empty states remain distinct', () => {
  assert.match(render({ loading: true }), /recent-transactions-skeleton/)
  assert.match(render({ read: { recentTransactions: { ...transactions, status: 'partial', limitations: ['Some source events withheld.'] } } }), /Some source events withheld/)
  assert.match(render({ read: { recentTransactions: { ...transactions, status: 'unavailable', events: [], limitations: ['Official window unavailable.'] } } }), /Official window unavailable/)
  assert.match(render({ read: { recentTransactions: { ...transactions, events: [] } } }), /No verified pitching moves/)
  const html = render({ read, error: 'private exception' })
  assert.match(html, /could not be loaded/)
  assert.doesNotMatch(html, /private exception/)
})

test('pitcher handoff is keyboard-safe and section does not derive roster authority', async () => {
  const html = render({ read, onSelectPitcher: () => {} })
  const source = await readFile(new URL('../src/components/bullpen/board/TeamBoardRecentTransactions.jsx', import.meta.url), 'utf8')
  assert.match(html, /type="button"/)
  assert.match(html, /focus-visible:ring-line-focus/)
  for (const forbidden of ['.sort(', '.reduce(', 'is_active_mlb', 'normalized_category', 'will return', 'injury severity', 'manager intent']) {
    assert.equal(source.toLowerCase().includes(forbidden), false, forbidden)
  }
})

test('one details request retains final What Changed and rotation-to-transactions placement', async () => {
  const boardSource = await readFile(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')
  assert.equal((boardSource.match(/getTeamBoardDetails\(/g) || []).length, 1)
  assert.ok(boardSource.indexOf('<TeamBoardWhatChanged') < boardSource.indexOf('<TeamBoardRotationImpact'))
  assert.ok(boardSource.indexOf('<TeamBoardRotationImpact') < boardSource.indexOf('<TeamBoardRecentTransactions'))
})
