import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import { makeBoard } from './fixtures/bullpenBoardFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { default: BullpenLandscape } = await server.ssrLoadModule('/src/components/dashboard/BullpenLandscape.jsx')
const { default: TeamGameContextCard } = await server.ssrLoadModule('/src/components/bullpen/board/TeamGameContextCard.jsx')
const { DashboardView } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

// Affirmative advisory phrasing that must never appear. (The required
// disclaimers legitimately negate "prediction"/"matchup advice", so those bare
// words are checked separately as disclaimers, not as advisory language.)
const FORBIDDEN_AFFIRMATIVE = [
  'best bullpen', 'worst bullpen', 'best arm', 'recommended', 'recommendation',
  'should use', 'expected winner', 'has the advantage', 'we recommend',
]
const noAffirmativeAdvisory = (html) => {
  const low = html.toLowerCase()
  return FORBIDDEN_AFFIRMATIVE.every(term => !low.includes(term))
}

const landscape = {
  capability: 'tonights_bullpen_landscape',
  ranking_applied: false,
  selection_made: false,
  reference_date: '2026-06-06',
  teams_evaluated: 3,
  games: { available: true, data_state: 'historical', today_count: 0, as_of_date: '2026-06-04', as_of_count: 5, is_today: false, message: null },
  constrained_bullpens: [{ team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE', total_relievers: 8, available: 2, monitor: 2, restricted: 4, pct_available: 25, pct_restricted: 50, health_state: 'constrained', health_label: 'The bullpen is short on clean options right now.' }],
  available_bullpens: [{ team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA', total_relievers: 8, available: 6, monitor: 1, restricted: 1, pct_available: 75, pct_restricted: 12, health_state: 'manageable', health_label: 'Bullpen workload appears manageable.' }],
  monitoring_concentration: [{ team_id: 3, team_name: 'Cubs', team_abbreviation: 'CHC', total_relievers: 8, available: 3, monitor: 4, restricted: 1, pct_available: 37, pct_restricted: 12, health_state: 'monitoring', health_label: 'Several relievers require monitoring.' }],
  notes: ['Descriptive groupings of bullpen situations only — this is bullpen context, not a league ranking or a game forecast.', 'Game context is from the latest stored game log, not a live schedule.'],
}

// ── Tonight's Bullpen Landscape ────────────────────────────────────────────

test('landscape renders canonical callout titles with descriptive subtitles', () => {
  const html = render(React.createElement(BullpenLandscape, { landscape }))
  assert.ok(htmlIncludes(html, 'Bullpen Landscape'))
  assert.ok(htmlIncludes(html, 'Most Stretched'))
  assert.ok(htmlIncludes(html, 'Most Available'))
  assert.ok(htmlIncludes(html, 'On Watch'))
  assert.ok(htmlIncludes(html, 'Fewest clean late-inning options'))
  assert.ok(htmlIncludes(html, 'Most room to maneuver'))
  assert.ok(htmlIncludes(html, 'Recent workload watch groups'))
  assert.ok(htmlIncludes(html, 'ACE'))
  assert.ok(htmlIncludes(html, 'BEA'))
  assert.ok(htmlIncludes(html, 'CHC'))
})

test('landscape shows the stored-games anchor honestly (not a live schedule)', () => {
  const html = render(React.createElement(BullpenLandscape, { landscape }))
  assert.ok(htmlIncludes(html, 'Bullpen data through Jun 4, 2026'))
  assert.equal(htmlIncludes(html, 'Tonight slate'), false)
  assert.equal(htmlIncludes(html, 'latest completed MLB slate'), false)
  assert.ok(htmlIncludes(html, 'not a game prediction'))   // required disclaimer
})

test('landscape renders nothing without data', () => {
  const html = render(React.createElement(BullpenLandscape, { landscape: null }))
  assert.equal(html, '')
})

test('landscape contains no affirmative advisory language', () => {
  const html = render(React.createElement(BullpenLandscape, { landscape }))
  assert.ok(noAffirmativeAdvisory(html), 'affirmative advisory language leaked')
})

test('dashboard surfaces the landscape section near the top', () => {
  const data = {
    capability: 'bullpen_dashboard',
    context: makeBoard({ cardsByStatus: { Available: [{ pitcher_id: 1, name: 'A', availability_status: 'Available' }] } }).context,
    roles: { order: [], counts: {}, total: 1 },
    freshness: { is_current: false, sync_status: 'metadata_unavailable', data_through: '2026-06-04' },
    landscape,
  }
  const html = render(React.createElement(DashboardView, { data }))
  assert.ok(htmlIncludes(html, 'Bullpen Landscape'))
  assert.ok(htmlIncludes(html, 'Most Stretched'))
  assert.ok(htmlIncludes(html, 'Fewest clean late-inning options'))
})

// ── Today's Game Context card ──────────────────────────────────────────────

const presentContext = {
  capability: 'team_game_context', available: true, state: 'stored_game_log', data_source: 'game_log',
  data_state: 'historical', source_label: 'Stored game-log context', confidence: 'medium',
  opponent: 'Rivals', opponent_abbreviation: 'RIV', game_date: '2026-06-04', home_away: null,
  scheduled_time: null, game_status: 'final', is_today: false, missing_fields: ['home_away', 'scheduled_time'],
}

test('game-context card shows opponent, date, and stored-context labelling', () => {
  const html = render(React.createElement(TeamGameContextCard, { gameContext: presentContext }))
  assert.ok(htmlIncludes(html, 'Most Recent Completed Game'))
  assert.ok(htmlIncludes(html, 'Stored game-log context'))
  assert.ok(htmlIncludes(html, 'Rivals'))
  assert.ok(htmlIncludes(html, 'Jun 4, 2026'))
  // Unavailable fields are stated, not fabricated.
  assert.ok(htmlIncludes(html, 'Home/away and Scheduled time unavailable in stored game-log data.'))
  assert.ok(htmlIncludes(html, 'does not provide matchup advice or game predictions'))
})

test('game-context card handles no stored game found', () => {
  const html = render(React.createElement(TeamGameContextCard, {
    gameContext: { capability: 'team_game_context', available: false, state: 'no_game_found',
      message: 'No game found in the stored game log for this date.', data_state: 'unavailable', confidence: 'none', missing_fields: [] },
  }))
  assert.ok(htmlIncludes(html, 'No stored game-log context found for this team yet.'))
})

test('game-context card handles unavailable context', () => {
  const html = render(React.createElement(TeamGameContextCard, {
    gameContext: { capability: 'team_game_context', available: false, state: 'unavailable',
      message: 'Schedule context unavailable.', data_state: 'unavailable', confidence: 'none', missing_fields: [] },
  }))
  assert.ok(htmlIncludes(html, 'Schedule context unavailable.'))
})

test('game-context card handles loading and missing context', () => {
  assert.ok(htmlIncludes(render(React.createElement(TeamGameContextCard, { loading: true })), 'Loading game context'))
  assert.ok(htmlIncludes(render(React.createElement(TeamGameContextCard, { gameContext: null })), 'Schedule data unavailable.'))
})

test('game-context card contains no affirmative advisory language', () => {
  const html = render(React.createElement(TeamGameContextCard, { gameContext: presentContext }))
  assert.ok(noAffirmativeAdvisory(html), 'affirmative advisory language leaked')
})
