import assert from 'node:assert/strict'
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

after(async () => {
  await server.close()
})

const { default: TeamGameContextCard } = await server.ssrLoadModule('/src/components/bullpen/board/TeamGameContextCard.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const detailsTagFor = (html, ariaLabel) => (
  html.match(new RegExp(`<details[^>]*aria-label="${escapeRegExp(ariaLabel)}"[^>]*>`))?.[0] || ''
)
const render = (props) => renderToStaticMarkup(React.createElement(TeamGameContextCard, props))

const present = {
  capability: 'team_game_context', available: true, state: 'stored_game_log', data_source: 'game_log',
  data_state: 'historical', source_label: 'Stored game-log context', confidence: 'medium',
  team: { team_id: 1, team_name: 'Arizona Diamondbacks', team_abbreviation: 'AZ' },
  opponent: 'Los Angeles Dodgers', opponent_abbreviation: 'LAD', game_date: '2026-06-04',
  home_away: null, scheduled_time: null, game_status: 'final', is_today: false,
  missing_fields: ['home_away', 'scheduled_time'],
}

// ── Matchup is the hero ────────────────────────────────────────────────────

test('the matchup (team vs opponent) is rendered prominently', () => {
  const html = render({ gameContext: present })
  assert.ok(htmlIncludes(html, 'Arizona Diamondbacks'))
  assert.ok(htmlIncludes(html, 'Los Angeles Dodgers'))
  assert.ok(htmlIncludes(html, '>vs<'))
  // The opponent carries the hero emphasis (display-size, amber gradient).
  assert.ok(/text-gradient-amber[^>]*>\s*Los Angeles Dodgers/.test(html), 'opponent is the hero element')
})

test('the opponent reads before the trust metadata (hierarchy)', () => {
  const html = render({ gameContext: present })
  assert.ok(html.indexOf('Los Angeles Dodgers') < html.indexOf('Historical Game Log'),
    'matchup should dominate, metadata follows')
})

// ── Trust metadata is preserved (visible, subordinate) ─────────────────────

test('trust metadata stays visible: data state, confidence, status, missing fields', () => {
  const html = render({ gameContext: present })
  assert.ok(htmlIncludes(html, 'Historical Game Log'))
  assert.ok(htmlIncludes(html, 'Limited Read'))
  assert.ok(htmlIncludes(html, 'Final'))
  assert.ok(htmlIncludes(html, 'Stored game-log context'))
  assert.ok(htmlIncludes(html, 'Home/away and Scheduled time unavailable in stored game-log data.'))
  assert.ok(htmlIncludes(html, '2026'))   // game date present
})

test('the context banner / disclaimer is present', () => {
  const html = render({ gameContext: present })
  const contextNoteTag = detailsTagFor(html, 'Game context note')

  assert.ok(contextNoteTag)
  assert.ok(!contextNoteTag.includes('open'))
  assert.ok(htmlIncludes(html, 'Game context note'))
  assert.ok(htmlIncludes(html, 'Game context helps explain bullpen workload and availability'))
  assert.ok(htmlIncludes(html, 'does not provide matchup advice or game predictions'))
})

// ── States ─────────────────────────────────────────────────────────────────

test('no_game_found renders a clear, non-technical empty state', () => {
  const html = render({ gameContext: { capability: 'team_game_context', available: false, state: 'no_game_found',
    message: 'No game found in the stored game log for this date.', data_state: 'unavailable', confidence: 'none', missing_fields: [] } })
  assert.ok(htmlIncludes(html, 'No stored game-log context found for this team yet.'))
  assert.ok(htmlIncludes(html, 'Game context helps explain bullpen workload'))  // banner still shown
})

test('unavailable and loading and null states are clear', () => {
  assert.ok(htmlIncludes(render({ gameContext: { state: 'unavailable', available: false, message: 'Schedule context unavailable.' } }), 'Schedule context unavailable.'))
  assert.ok(htmlIncludes(render({ loading: true }), 'Loading game context'))
  assert.ok(htmlIncludes(render({ gameContext: null }), 'Schedule data unavailable.'))
})

test('opponent-missing present state degrades gracefully', () => {
  const html = render({ gameContext: { ...present, opponent: null } })
  assert.ok(htmlIncludes(html, 'Opponent unavailable'))
})

// ── Guardrails: contextual framing only, never a scoreboard ─────────────────

test('no scoreboard / advisory / prediction language is introduced', () => {
  const html = render({ gameContext: present }).toLowerCase()
  for (const term of [
    'best bullpen', 'worst bullpen', 'recommended', 'should use', 'advantage',
    'win probability', 'standings', 'betting', 'odds', 'projection', 'projected',
    'expected outcome', 'expected winner', 'final score', 'box score',
  ]) {
    assert.ok(!html.includes(term), `leaked term: ${term}`)
  }
})
