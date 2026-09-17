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
const { default: TeamBoardRestStatus } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardRestStatus.jsx',
)
const { readTeamBoardRecentUsageRest } = await server.ssrLoadModule(
  '/src/adapters/teamBoardV2.js',
)

const identity = {
  represented_date: '2026-08-16',
  availability_reference_date: '2026-08-17',
}

const fact = (value, status = 'complete', extras = {}) => ({
  value,
  status,
  reason_codes: status === 'complete' ? [] : ['fixture_incomplete'],
  ...extras,
})

const window = (days, appearances, pitches, outs, states = {}) => ({
  window_days: days,
  start_date: days === 1 ? '2026-08-16' : days === 3 ? '2026-08-14' : '2026-08-10',
  through_date: '2026-08-16',
  appearances: fact(appearances, states.appearances || 'complete'),
  pitches: fact(pitches, states.pitches || 'complete'),
  outs: fact(outs, states.outs || 'complete'),
})

const pitcher = ({ id, name, partial = false }) => ({
  pitcher_id: id,
  pitcher_name: name,
  roster_state: 'active',
  windows: partial ? {
    yesterday: window(1, 0, 0, 0),
    last_3_days: window(3, null, null, null, { appearances: 'partial', pitches: 'partial', outs: 'partial' }),
    last_7_days: window(7, null, null, null, { appearances: 'unknown', pitches: 'unknown', outs: 'unavailable' }),
  } : {
    yesterday: window(1, 1, 28, 3),
    last_3_days: window(3, 2, 45, 6),
    last_7_days: window(7, 4, 88, 13),
  },
  days_since_last_appearance: partial ? fact(null, 'unknown') : fact(1),
  pitched_yesterday: partial ? fact(false) : fact(true),
  back_to_back: partial ? fact(null, 'partial') : fact(true),
  three_in_four: partial ? fact(null, 'unknown') : fact(true),
  four_in_six: partial ? fact(null, 'unavailable') : fact(true),
  recent_multi_inning: partial ? fact(false) : fact(true, 'complete', { threshold: 4 }),
  high_pitch_outing: partial ? fact(null, 'unknown', { threshold: 25 }) : fact(true, 'complete', { threshold: 25 }),
})

const carrier = {
  contract: 'team_board_recent_usage_rest_v1',
  status: 'partial',
  reason_code: 'some_usage_rest_fields_incomplete',
  data_through: identity.represented_date,
  reference_date: identity.availability_reference_date,
  window_policy: 'calendar_day_inclusive_through_date_v1',
  population_basis: 'official_appearance_team_relief_appearances_and_frozen_active_bullpen',
  thresholds: {
    multi_inning_minimum_outs: 4,
    high_pitch_outing_minimum_pitches: 25,
  },
  active_pitchers: [
    pitcher({ id: 7, name: 'Alpha Reliever' }),
    pitcher({ id: 8, name: 'Bravo Reliever', partial: true }),
  ],
  off_active_historical_contributors: [{
    ...pitcher({ id: 9, name: 'Former Reliever' }),
    roster_state: 'off_active_historical',
  }],
}

const recentUsageRest = readTeamBoardRecentUsageRest(carrier, identity)
const read = {
  recentUsageRest,
  recentUsageRestRejected: false,
  restStatus: {
    available: true,
    active_arm_count: 8,
    rested_arm_count: 5,
    worked_yesterday_count: 2,
    back_to_back_count: 1,
    summary: '5 of 8 active bullpen arms have at least one full day of rest; 2 arms worked yesterday and 1 arm worked back-to-back.',
  },
  sectionStatus: {
    rest_status: { status: 'available', limitations: [] },
  },
}

const renderRecent = props => renderToStaticMarkup(React.createElement(TeamBoardRecentUsage, props))
const renderRest = props => renderToStaticMarkup(React.createElement(TeamBoardRestStatus, props))

test('Recent Usage renders named-arm yesterday, three-day, and seven-day facts', () => {
  const html = renderRecent({ read, onSelectPitcher: () => {} })
  const alpha = html.slice(html.indexOf('Alpha Reliever'), html.indexOf('Bravo Reliever'))

  for (const label of ['Yesterday', '3 Days', '7 Days']) assert.ok(alpha.includes(label), label)
  for (const value of ['>1<', '>28<', '>3<', '>2<', '>45<', '>6<', '>4<', '>88<', '>13<']) {
    assert.ok(alpha.includes(value), value)
  }
  assert.ok(html.includes('Published through Aug 16, 2026'))
})

test('Rest and usage patterns render backend facts with factual wording', () => {
  const html = renderRecent({ read })
  const alpha = html.slice(html.indexOf('Alpha Reliever'), html.indexOf('Bravo Reliever'))

  for (const label of [
    'Pitched yesterday',
    'Back-to-back',
    '3 appearances in 4 days',
    '4 appearances in 6 days',
    'Multi-inning outing',
    '25+ pitch outing',
  ]) assert.ok(alpha.includes(label), label)

  for (const forbidden of ['pitch spike', 'gassed', 'needs rest', 'likely out', 'should not pitch']) {
    assert.equal(html.toLowerCase().includes(forbidden), false, forbidden)
  }
})

test('partial, unknown, and unavailable facts stay withheld instead of becoming zero or false', () => {
  const html = renderRecent({ read })
  const bravo = html.slice(html.indexOf('Bravo Reliever'), html.indexOf('Recent workload from pitchers no longer active'))

  assert.ok(bravo.includes('aria-label="Appearances: partial"'))
  assert.ok(bravo.includes('aria-label="Pitches: unknown"'))
  assert.ok(bravo.includes('aria-label="Outs: unavailable"'))
  assert.ok(bravo.includes('>—<'))
  assert.ok(bravo.includes('Evidence incomplete: Back-to-back, 3 appearances in 4 days, 4 appearances in 6 days, 25+ pitch outing.'))
  assert.equal(bravo.includes('>null<'), false)
  assert.ok(bravo.includes('aria-label="Appearances: 0"'))
})

test('active pitchers and off-active historical contributors stay in separate groups exactly once', () => {
  const html = renderRecent({ read })
  const offActiveHeading = html.indexOf('Recent workload from pitchers no longer active')

  assert.ok(offActiveHeading > html.indexOf('Bravo Reliever'))
  assert.ok(html.indexOf('Former Reliever') > offActiveHeading)
  for (const name of ['Alpha Reliever', 'Bravo Reliever', 'Former Reliever']) {
    assert.equal((html.match(new RegExp(`>${name}<`, 'g')) || []).length, 1, name)
  }
})

test('Recent Usage distinguishes loading, outage, carrier mismatch, and unavailable publication states', () => {
  assert.ok(renderRecent({ loading: true }).includes('recent-usage-skeleton'))
  assert.ok(renderRecent({ read, error: 'private exception' }).includes('Recent usage and rest patterns could not be loaded.'))
  assert.equal(renderRecent({ read, error: 'private exception' }).includes('private exception'), false)
  assert.ok(renderRecent({ read: { ...read, recentUsageRest: null, recentUsageRestRejected: true } }).includes('does not match this Team Board publication'))
  assert.ok(renderRecent({ read: { ...read, recentUsageRest: null } }).includes('publication-bound recent usage and rest read is not available'))
})

test('Rest Status retains the existing backend-owned aggregate read', () => {
  const html = renderRest({ read })
  for (const value of ['Rested arms', '>5<', 'Worked yesterday', '>2<', 'Back-to-back', '>1<', read.restStatus.summary]) {
    assert.ok(html.includes(value), value)
  }
})

test('TB-03 frontend consumes the carrier without baseball calculation or predictive copy', async () => {
  const boardSource = await readFile(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')
  const recentSource = await readFile(new URL('../src/components/bullpen/board/TeamBoardRecentUsage.jsx', import.meta.url), 'utf8')
  const adapterSource = await readFile(new URL('../src/adapters/teamBoardV2.js', import.meta.url), 'utf8')

  assert.ok(boardSource.includes('<TeamBoardRecentUsage'))
  assert.ok(recentSource.includes('read?.recentUsageRest'))
  assert.ok(adapterSource.includes('details.recent_usage_rest'))
  assert.ok(adapterSource.includes('carrier.data_through !== publicationIdentity.represented_date'))
  assert.ok(adapterSource.includes('carrier.reference_date !== publicationIdentity.availability_reference_date'))
  for (const forbidden of ['Math.', '.reduce(', '/ 3', 'Date(', 'pitch_spike', 'fatigue', 'likely unavailable']) {
    assert.equal(recentSource.includes(forbidden), false, forbidden)
    assert.equal(adapterSource.includes(forbidden), false, forbidden)
  }
  assert.equal((boardSource.match(/getTeamBoardCore\(/g) || []).length, 1)
  assert.equal((boardSource.match(/getTeamBoardDetails\(/g) || []).length, 1)
  assert.equal(recentSource.includes('overflow-x'), false)
  assert.ok(recentSource.includes('grid-cols-3'))
  assert.ok(recentSource.includes('flex-wrap'))
})
