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

const { default: TeamBoardRecentUsage } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardRecentUsage.jsx',
)
const { getRecentUsageView } = await server.ssrLoadModule(
  '/src/components/bullpen/board/recentUsageView.js',
)
const { default: TeamBoardRestStatus } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardRestStatus.jsx',
)

const reliefWork = {
  data_through: '2026-08-16',
  windows: {
    window_7: {
      through: '2026-08-16',
      relief_appearances: 3,
      pitchers_in_relief: 2,
      pitches_total: null,
      appearances_with_pitches: 2,
      start_relief_unknown: 0,
      sentence: '3 relief appearances in the 7 days through Aug 16.',
      pitchers_sentence: '2 pitchers appeared in relief in the 7 days through Aug 16.',
      pitches_sentence: 'Pitch count unavailable for 1 of 3 relief appearances; 41 pitches across the other 2.',
    },
    window_14: {
      through: '2026-08-16',
      relief_appearances: 0,
      pitchers_in_relief: 0,
      pitches_total: 0,
      appearances_with_pitches: 0,
      start_relief_unknown: 0,
      sentence: '0 relief appearances in the 14 days through Aug 16.',
      pitchers_sentence: '0 pitchers appeared in relief in the 14 days through Aug 16.',
      pitches_sentence: '0 pitches across those 0 relief appearances.',
    },
  },
  relief_by_date: [{
    game_date: '2026-08-16',
    available: true,
    sentence: 'Aug 16 — 2 relief appearances, 2.0 IP, 41 published pitches.',
    appearances: [
      { pitcher_id: 8, pitcher_full_name: 'Zachary Very Long Reliever Name' },
      { pitcher_id: 2, pitcher_full_name: 'Aaron Second' },
    ],
  }],
}

const read = {
  recentReliefWork: {
    population_basis: 'official_appearance_team_relief_appearances',
    read: reliefWork,
  },
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

test('Recent Usage renders governed windows and preserves latest-date arm order', () => {
  const view = getRecentUsageView(reliefWork)
  const html = renderRecent({ read, onSelectPitcher: () => {} })

  assert.deepEqual(view.windows.map(row => row.days), [7, 14])
  assert.deepEqual(view.latestGroup.arms.map(arm => arm.name), [
    'Zachary Very Long Reliever Name',
    'Aaron Second',
  ])
  assert.ok(html.includes(reliefWork.windows.window_7.sentence))
  assert.ok(html.includes(reliefWork.windows.window_14.sentence))
  assert.ok(html.indexOf('Zachary Very Long Reliever Name') < html.indexOf('Aaron Second'))
  assert.ok(html.includes('<time dateTime="2026-08-16">Aug 16, 2026</time>'))
  assert.equal(html.includes('Yesterday'), false)
})

test('Recent Usage keeps withheld pitches distinct from a published zero', () => {
  const html = renderRecent({ read })
  const sevenDay = html.slice(html.indexOf('Last 7 days'), html.indexOf('Last 14 days'))
  const fourteenDay = html.slice(html.indexOf('Last 14 days'))

  assert.ok(sevenDay.includes('>—<'))
  assert.ok(sevenDay.includes(reliefWork.windows.window_7.pitches_sentence))
  assert.equal(sevenDay.includes('>0<'), false)
  assert.ok(fourteenDay.includes('>0<'))
  assert.equal(html.includes('null'), false)
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
  } }).includes('Recent usage evidence is unavailable.'))
  assert.ok(renderRecent({ read: {
    ...read,
    recentReliefWork: { ...read.recentReliefWork, read: { windows: {}, relief_by_date: [] } },
  } }).includes('A recent usage read is not available.'))
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
  const viewSource = await readFile(new URL('../src/components/bullpen/board/recentUsageView.js', import.meta.url), 'utf8')

  assert.equal((boardSource.match(/getTeamBoardV2\(/g) || []).length, 1)
  assert.equal((boardSource.match(/useTeamReliefWork\(/g) || []).length, 0)
  assert.equal(boardSource.includes('getTeamReliefWork'), false)
  assert.ok(boardSource.includes('<TeamBoardRecentUsage'))
  assert.ok(boardSource.includes('<TeamBoardRestStatus'))
  assert.equal(boardSource.includes('<RecentUsage'), false)
  assert.equal(boardSource.includes('<RestStatus'), false)
  assert.ok(boardSource.includes('<TeamBoardWorkloadOverview'))
  assert.ok(boardSource.includes('<TeamReliefWorkPanel'))
  assert.ok(boardSource.indexOf('<TeamBoardActiveBullpen') < boardSource.indexOf('<TeamBoardRecentUsage'))
  assert.ok(boardSource.indexOf('<TeamBoardRecentUsage') < boardSource.indexOf('<TeamBoardRestStatus'))
  assert.ok(boardSource.indexOf('<TeamBoardRestStatus') < boardSource.indexOf('<TeamBoardWorkloadOverview'))
  for (const forbidden of ['.sort(', '3_in_4', '4_in_5', '4_in_6', 'fatigue', 'workload_score', 'reason_code']) {
    assert.equal(recentSource.includes(forbidden), false, forbidden)
    assert.equal(viewSource.includes(forbidden), false, forbidden)
  }
  assert.equal(recentSource.includes('getTeamBoardV2'), false)
  assert.equal(viewSource.includes('window_3'), false)
  assert.ok(recentSource.includes('tablet:grid'))
  assert.ok(recentSource.includes('flex-wrap'))
  assert.equal(recentSource.includes('overflow-x'), false)
  assert.equal(recentSource.includes('text-[9px]'), false)
  assert.equal(recentSource.includes('text-[10px]'), false)
  assert.equal(recentSource.includes('text-[11px]'), false)
})
