import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { default: TeamGameContextCard } = await server.ssrLoadModule('/src/components/bullpen/board/TeamGameContextCard.jsx')

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
  assert.equal(htmlIncludes(html, 'Stored game-log context'), false)
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
