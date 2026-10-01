import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import { productionPayload } from './fixtures/tonightV1Fixtures.mjs'

// A Tonight edition is immutable: its stored game list never changes after
// publication. A game MLB later cancels, or whose postseason "if necessary"
// game MLB stops listing, is served with state 'cancelled' by the schedule
// overlay. It will not be played, so it is not presented on the slate.

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const view = await server.ssrLoadModule('/src/components/tonight/tonightView.js')
const { default: LeadDevelopment } = await server.ssrLoadModule('/src/components/tonight/LeadDevelopment.jsx')
const { MatchupPageView } = await server.ssrLoadModule('/src/components/bullpen/MatchupPage.jsx')

const render = (element) => renderToStaticMarkup(React.createElement(MemoryRouter, null, element))
const base = productionPayload().games[0]
const game = (state, pk) => ({ ...base, game_pk: pk, state })

test('a cancelled game is left out of every slate lifecycle bucket', () => {
  const groups = view.groupGamesByLifecycle([
    game('scheduled', 1), game('cancelled', 2), game('final', 3), game('cancelled', 4),
  ])
  assert.deepEqual(groups.upcoming.map(g => g.game_pk), [1])
  assert.deepEqual(groups.completed.map(g => g.game_pk), [3])
  assert.deepEqual(groups.inProgress, [])
})

test('a cancelled featured game is hidden; the others keep their order', () => {
  const games = [game('scheduled', 1), game('cancelled', 2), game('live', 3)]
  assert.deepEqual(view.getVisibleFeaturedGames(games, [2, 3, 1]).map(g => g.game_pk), [3, 1])
})

test('a cancelled game reads as Cancelled, never as an upcoming time', () => {
  assert.equal(view.gameStatusLabel(game('cancelled', 9)), 'Cancelled')
})

test('a lead about a cancelled game is not presented', () => {
  const lead = { headline: 'A bullpen to watch tonight.', reason_codes: [], game_pk: 2 }
  const cancelled = render(React.createElement(LeadDevelopment, {
    lead, games: [game('cancelled', 2)],
  }))
  assert.equal(cancelled, '')
  const scheduled = render(React.createElement(LeadDevelopment, {
    lead, games: [game('scheduled', 2)],
  }))
  assert.match(scheduled, /tonight-lead/)
})

function matchupPayload(status, reasonCode) {
  return {
    status,
    reason_code: reasonCode,
    comparison: null,
    game: {
      game_pk: 777001,
      reference_date: '2026-10-01',
      game_time_utc: '2026-10-01T22:08:00Z',
      status: { detailed: 'Cancelled: removed from MLB schedule', normalized: 'cancelled' },
      away: { team_name: 'Away Club' },
      home: { team_name: 'Home Club' },
    },
  }
}

test('Matchup presents a removed postseason game as not played', () => {
  const html = render(React.createElement(MatchupPageView, {
    payload: matchupPayload('not_upcoming', 'scheduled_game_removed_from_mlb_schedule'),
  }))
  assert.match(html, /Not Played/)
  assert.match(html, /This game will not be played/)
  assert.match(html, /no longer on MLB/)
  assert.doesNotMatch(html, /Scheduled Matchup/)
  assert.match(html, /Away Club at Home Club/)
})

test('Matchup presents an MLB cancellation as not played', () => {
  const html = render(React.createElement(MatchupPageView, {
    payload: matchupPayload('not_upcoming', 'scheduled_game_cancelled'),
  }))
  assert.match(html, /MLB cancelled it/)
})

test('an ordinary scheduled Matchup is unchanged', () => {
  const payload = matchupPayload('partial', 'scheduled_game_comparison_unavailable')
  payload.game.status = { detailed: 'Scheduled', normalized: 'upcoming' }
  const html = render(React.createElement(MatchupPageView, { payload }))
  assert.match(html, /Scheduled Matchup/)
  assert.match(html, /Bullpen comparison unavailable/)
})
