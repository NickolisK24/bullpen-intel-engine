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

const { default: TeamBoardRecentUsage, getRecentUsageRows } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardRecentUsage.jsx',
)
const { default: TeamBoardRestStatus } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardRestStatus.jsx',
)

const recentUsage = {
  population_basis: 'official_recent_team_relief_appearance_rows',
  represented_date: '2026-08-16',
  appearances: [
    {
      pitcher_id: 8,
      pitcher_name: 'Zachary Very Long Reliever Name',
      game_date: '2026-08-16',
      opponent: 'Boston Red Sox',
      opponent_abbreviation: 'BOS',
      pitches_thrown: null,
      outs_recorded: 3,
      game_id: 9002,
    },
    {
      pitcher_id: 2,
      pitcher_name: 'Aaron Second',
      game_date: '2026-08-15',
      opponent: null,
      opponent_abbreviation: null,
      pitches_thrown: 0,
      outs_recorded: 2,
      game_id: 9001,
    },
  ],
  limitations: [],
}

const read = {
  recentUsage,
  restStatus: {
    available: true,
    active_arm_count: 8,
    rested_arm_count: 5,
    worked_yesterday_count: 2,
    back_to_back_count: 1,
    summary: '5 of 8 active bullpen arms have at least one full day of rest; 2 arms worked yesterday and 1 arm worked back-to-back.',
  },
  sectionStatus: {
    recent_usage: { status: 'available', limitations: [] },
    rest_status: { status: 'available', limitations: [] },
  },
}

const renderRecent = props => renderToStaticMarkup(React.createElement(TeamBoardRecentUsage, props))
const renderRest = props => renderToStaticMarkup(React.createElement(TeamBoardRestStatus, props))

test('Recent Usage preserves backend chronology and renders governed appearance facts', () => {
  const rows = getRecentUsageRows(recentUsage)
  const html = renderRecent({ read })

  assert.deepEqual(rows.map(row => row.pitcherName), [
    'Zachary Very Long Reliever Name',
    'Aaron Second',
  ])
  assert.ok(html.indexOf('Zachary Very Long Reliever Name') < html.indexOf('Aaron Second'))
  assert.ok(html.includes('<time dateTime="2026-08-16">Aug 16, 2026</time>'))
  assert.ok(html.includes('1.0 IP'))
  assert.ok(html.includes('0.2 IP · 0 pitches'))
  assert.ok(html.includes('vs. BOS'))
})

test('Recent Usage omits unknown pitches instead of rendering zero', () => {
  const html = renderRecent({ read })
  const first = html.slice(html.indexOf('Zachary Very Long Reliever Name'), html.indexOf('Aaron Second'))

  assert.ok(first.includes('1.0 IP'))
  assert.equal(first.includes('0 pitches'), false)
  assert.equal(first.includes('null'), false)
})

test('Recent Usage distinguishes loading, partial, unavailable, and empty states', () => {
  assert.ok(renderRecent({ loading: true }).includes('recent-usage-skeleton'))
  assert.ok(renderRecent({ read: {
    ...read,
    sectionStatus: { ...read.sectionStatus, recent_usage: { status: 'partial', limitations: ['One date is unavailable.'] } },
  } }).includes('One date is unavailable.'))
  assert.ok(renderRecent({ read: {
    ...read,
    sectionStatus: { ...read.sectionStatus, recent_usage: { status: 'unavailable' } },
  } }).includes('Recent appearance evidence is unavailable.'))
  assert.ok(renderRecent({ read: {
    ...read,
    recentUsage: { ...recentUsage, appearances: [] },
  } }).includes('No recent relief appearances'))
  assert.ok(renderRecent({ read, error: 'private exception' }).includes('Recent usage could not be loaded.'))
  assert.equal(renderRecent({ read, error: 'private exception' }).includes('private exception'), false)
})

test('Rest Status renders only backend-owned counts and summary', () => {
  const html = renderRest({ read })

  for (const value of ['Rested arms', '>5<', 'Worked yesterday', '>2<', 'Back-to-back', '>1<', read.restStatus.summary]) {
    assert.ok(html.includes(value), value)
  }
})

test('Rest Status preserves zero and fails closed on missing counts', () => {
  const zeroRead = {
    ...read,
    restStatus: {
      ...read.restStatus,
      rested_arm_count: 0,
      worked_yesterday_count: 0,
      back_to_back_count: 0,
      summary: '0 of 8 active bullpen arms have at least one full day of rest.',
    },
  }
  assert.ok(renderRest({ read: zeroRead }).includes('>0<'))
  assert.ok(renderRest({ read: {
    ...read,
    restStatus: { ...read.restStatus, rested_arm_count: null },
  } }).includes('Rest Status unavailable'))
  assert.ok(renderRest({ loading: true }).includes('rest-status-skeleton'))
})

test('production reuses one v2 request, retires legacy section mounts, and leaves later sections legacy', async () => {
  const boardSource = await readFile(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')
  const recentSource = await readFile(new URL('../src/components/bullpen/board/TeamBoardRecentUsage.jsx', import.meta.url), 'utf8')

  assert.equal((boardSource.match(/getTeamBoardV2\(/g) || []).length, 1)
  assert.equal((boardSource.match(/useTeamReliefWork\(/g) || []).length, 1)
  assert.ok(boardSource.includes('<TeamBoardRecentUsage'))
  assert.ok(boardSource.includes('<TeamBoardRestStatus'))
  assert.equal(boardSource.includes('<RecentUsage'), false)
  assert.equal(boardSource.includes('<RestStatus'), false)
  assert.ok(boardSource.includes('<WorkloadOverview'))
  assert.ok(boardSource.includes('<TeamReliefWorkPanel'))
  assert.ok(boardSource.indexOf('<TeamBoardActiveBullpen') < boardSource.indexOf('<TeamBoardRecentUsage'))
  assert.ok(boardSource.indexOf('<TeamBoardRecentUsage') < boardSource.indexOf('<TeamBoardRestStatus'))
  for (const forbidden of ['.sort(', '3_in_4', '4_in_5', '4_in_6', 'fatigue', 'workload_score', 'reason_code']) {
    assert.equal(recentSource.includes(forbidden), false, forbidden)
  }
})
