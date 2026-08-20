import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
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

after(async () => server.close())

const { default: TeamBoardRecentTransactions, getRecentTransactionRows } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardRecentTransactions.jsx',
)

const recentTransactions = {
  capability: 'public_recent_transactions_v1',
  population_basis: 'explanatory_eligible_pitcher_transactions_touching_selected_team_in_latest_source_sync_window',
  status: 'available',
  events: [
    { event_id: 'newer', player_id: 9, player_name: 'A Very Long Reliever Name', date: '2026-08-18', type: 'recall', label: 'Recalled' },
    { event_id: 'older', player_id: 7, player_name: 'Example Arm', date: '2026-08-16', type: 'option', label: 'Optioned' },
  ],
  window_start_date: '2026-08-11',
  window_end_date: '2026-08-18',
  represented_date: '2026-08-18',
  limitations: [],
}

const rosterContext = {
  capability: 'roster_authority_v1',
  invariant: true,
  reference_date: '2026-08-18',
  population: { total_candidates: 2, roster_status_coverage: 1 },
  counts: {
    bullpen_arms: 1,
    inactive_roster_context_count: 1,
    roster_unknown_count: 0,
  },
  evidence: {
    bullpen_arms: [],
    inactive_roster_context_count: [{
      pitcher_id: 7,
      name: 'Example Arm',
      roster_status: 'OPTIONED',
      roster_status_label: 'Optioned',
      availability: null,
    }],
    roster_unknown_count: [],
  },
  readiness: {
    claims_available: true,
    counts_withheld: false,
    data_through: '2026-08-18',
    reader_limitations: [],
  },
  limitations: [],
}

const read = {
  recentTransactions,
  rosterContext,
  sectionStatus: {
    recent_transactions: { status: 'available', limitations: [], represented_date: '2026-08-18' },
  },
}

const renderTransactions = props => renderToStaticMarkup(React.createElement(TeamBoardRecentTransactions, props))


test('Recent Transactions preserves backend chronology, labels, identity, and dates', () => {
  const rows = getRecentTransactionRows(recentTransactions)
  const html = renderTransactions({ read })

  assert.deepEqual(rows.map(row => row.key), ['newer', 'older'])
  assert.ok(html.indexOf('A Very Long Reliever Name') < html.indexOf('Example Arm'))
  assert.ok(html.includes('Recalled'))
  assert.ok(html.includes('Optioned'))
  assert.match(html, /date(?:T|t)ime="2026-08-18"/)
  assert.match(html, /date(?:T|t)ime="2026-08-16"/)
  assert.ok(html.includes('Recent movement'))
})


test('missing transaction facts remain explicit and are not guessed', () => {
  const unknown = {
    ...recentTransactions,
    events: [{ event_id: 'unknown', player_id: null, player_name: null, date: null, type: null, label: null }],
  }
  const html = renderTransactions({ read: { ...read, recentTransactions: unknown, rosterContext: {} } })

  assert.ok(html.includes('Player unavailable'))
  assert.ok(html.includes('—'))
  assert.equal(html.includes('Recalled'), false)
  assert.equal(html.includes('Optioned'), false)
  assert.equal(html.includes('>0<'), false)
  assert.equal(html.includes('0 transactions'), false)
})


test('loading, partial, unavailable, error, and legitimate empty states are distinct', () => {
  assert.ok(renderTransactions({ loading: true }).includes('recent-transactions-skeleton'))
  assert.ok(renderTransactions({ read: {
    ...read,
    sectionStatus: { recent_transactions: { status: 'partial', limitations: ['One governed transaction limitation.'] } },
  } }).includes('One governed transaction limitation.'))
  assert.ok(renderTransactions({ read: {
    ...read,
    recentTransactions: { ...recentTransactions, status: 'unavailable', events: [] },
    sectionStatus: { recent_transactions: { status: 'unavailable', limitations: ['Official transaction source unavailable.'] } },
  } }).includes('Official transaction source unavailable.'))
  const errorHtml = renderTransactions({ read, error: 'private exception' })
  assert.ok(errorHtml.includes('Recent transaction records could not be loaded.'))
  assert.equal(errorHtml.includes('private exception'), false)
  assert.ok(renderTransactions({ read: {
    ...read,
    recentTransactions: { ...recentTransactions, events: [] },
  } }).includes('No recent transactions'))
})


test('Current roster status stays distinct from governed transaction movement', async () => {
  const html = renderTransactions({ read })
  const boardSource = await readFile(
    new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url),
    'utf8',
  )

  assert.ok(html.includes('Current roster status'))
  assert.ok(html.includes('Recent movement'))
  assert.ok(html.includes('Roster status confirmed'))
  assert.ok(html.includes('Off the active roster'))
  assert.match(html, /date(?:T|t)ime="2026-08-18"/)
  assert.equal(boardSource.includes('<RosterStatusBanner'), false)
  assert.equal(boardSource.includes("from './BullpenBoardView'"), false)
})


test('transaction and roster arms reuse the existing pitcher handoff', () => {
  const html = renderTransactions({ read, onSelectPitcher: () => {} })

  assert.ok(html.includes('type="button"'))
  assert.ok(html.includes('focus-visible:ring-line-focus'))
})


test('current roster state and churn never manufacture transaction events', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/board/TeamBoardRecentTransactions.jsx', import.meta.url),
    'utf8',
  )

  for (const forbidden of ['bullpen_stability', 'new_or_reintroduced', 'churn_share', '.sort(', '.reduce(']) {
    assert.equal(source.toLowerCase().includes(forbidden), false, forbidden)
  }
  assert.equal(getRecentTransactionRows({ events: [], roster_authority: rosterContext }).length, 0)
})


test('production reuses one v2 request, preserves placement, and does not start What Changed', async () => {
  const boardSource = await readFile(
    new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url),
    'utf8',
  )
  const componentSource = await readFile(
    new URL('../src/components/bullpen/board/TeamBoardRecentTransactions.jsx', import.meta.url),
    'utf8',
  )

  assert.equal((boardSource.match(/getTeamBoardV2\(/g) || []).length, 1)
  assert.ok(boardSource.indexOf('<TeamBoardRotationImpact') < boardSource.indexOf('<TeamBoardRecentTransactions'))
  assert.ok(boardSource.includes('<SectionPair label="Rotation and transactions">'))
  assert.ok(boardSource.indexOf('<TeamBoardRecentTransactions') < boardSource.indexOf('<TeamBoardWhatChanged'))
  assert.ok(boardSource.includes('<TeamReliefWorkPanel'))
  for (const forbidden of [
    'strengthens', 'fresh arm', 'leaves the bullpen thin', 'caused team state',
    'closer role', 'setup duties', 'manager intent', 'expected to', 'role impact',
    'team state impact', 'previous roster', 'snapshot comparison',
  ]) {
    assert.equal(componentSource.toLowerCase().includes(forbidden), false, forbidden)
  }
})
