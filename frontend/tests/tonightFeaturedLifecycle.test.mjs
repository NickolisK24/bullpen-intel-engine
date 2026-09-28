import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import {
  allFinalFeaturedPayload,
  lateNightFeaturedPayload,
  productionPayload,
} from './fixtures/tonightV1Fixtures.mjs'

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
const { TonightPageView } = await server.ssrLoadModule('/src/components/tonight/TonightPage.jsx')

const renderPage = (props) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, React.createElement(TonightPageView, props)),
)
const decode = (html) => html.replace(/&#x27;/g, "'").replace(/&amp;/g, '&')
const pks = (html) => [...html.matchAll(/data-testid="tonight-game-card" data-game-pk="(\d+)"/g)].map(m => Number(m[1]))

function region(html, testId) {
  const start = html.indexOf(`data-testid="${testId}"`)
  if (start < 0) return ''
  const open = html.lastIndexOf('<', start)
  const tag = html.slice(open + 1, html.indexOf(' ', open))
  let depth = 0
  const re = new RegExp(`<(/?)${tag}\\b[^>]*>`, 'g')
  re.lastIndex = open
  let match
  while ((match = re.exec(html))) {
    depth += match[1] ? -1 : 1
    if (depth === 0) return html.slice(open, re.lastIndex)
  }
  return html.slice(open)
}

const base = productionPayload().games[0]
const game = (pk, state) => ({ ...base, game_pk: pk, state, featured: true })
const visiblePks = (games, featuredPks) => view.getVisibleFeaturedGames(games, featuredPks).map(g => g.game_pk)

// ── 1–8 visibility rule ────────────────────────────────────────────────────

test('1–6. only state === final is hidden; scheduled, uncertain, live, suspended, postponed stay', () => {
  const games = [
    game(1, 'scheduled'), game(2, 'uncertain'), game(3, 'live'),
    game(4, 'suspended'), game(5, 'postponed'), game(6, 'final'),
  ]
  assert.deepEqual(visiblePks(games, [1, 2, 3, 4, 5, 6]), [1, 2, 3, 4, 5])
})

test('7. an unknown or missing state stays visible (fail-open; only final hides)', () => {
  const games = [game(1, 'rain_delay'), game(2, undefined), game(3, 'FINAL'), game(4, 'final')]
  assert.deepEqual(visiblePks(games, [1, 2, 3, 4]), [1, 2, 3])
})

test('8. a featured pk with no served game is skipped', () => {
  assert.deepEqual(visiblePks([game(1, 'scheduled')], [99, 1, 98]), [1])
  assert.deepEqual(visiblePks(null, [1]), [])
  assert.deepEqual(visiblePks([game(1, 'scheduled')], null), [])
})

// ── 9–14 ordering and no replacement ───────────────────────────────────────

test('9, ordering proof. featured_game_pks order is authority: [8,3,12,5] → [3,12]', () => {
  const games = [game(3, 'scheduled'), game(5, 'final'), game(8, 'final'), game(12, 'live')]
  assert.deepEqual(visiblePks(games, [8, 3, 12, 5]), [3, 12], 'not sorted by state or pk')
  assert.deepEqual(visiblePks(games, [12, 3]), [12, 3])
})

test('10–12. all final → empty; 3 final + 1 live → live; 2 final + scheduled + postponed → both in order', () => {
  assert.deepEqual(visiblePks([game(1, 'final'), game(2, 'final')], [1, 2]), [])
  assert.deepEqual(visiblePks([game(1, 'final'), game(2, 'live'), game(3, 'final'), game(4, 'final')], [1, 2, 3, 4]), [2])
  assert.deepEqual(visiblePks(
    [game(100, 'final'), game(101, 'postponed'), game(102, 'final'), game(103, 'scheduled')],
    [100, 101, 102, 103],
  ), [101, 103])
})

test('13–14. no replacement: non-featured games never enter, even when all featured are final', () => {
  const games = [game(1, 'final'), game(2, 'scheduled'), game(3, 'live')]
  assert.deepEqual(visiblePks(games, [1]), [])
  assert.deepEqual(visiblePks(games, [1, 3]), [3])
})

// ── Production-shaped late-night fixture ───────────────────────────────────

const late = lateNightFeaturedPayload()
const uncertainPk = late.games.find(g => g.state === 'uncertain').game_pk
const finalFeaturedPks = late.featured_game_pks.filter(pk => pk !== uncertainPk)

test('late night: Games to Watch has exactly the one uncertain featured game', () => {
  const html = renderPage({ payload: late })
  const featured = region(html, 'tonight-featured')
  assert.match(featured, /<h2[^>]*>Games to Watch<\/h2>/)
  assert.deepEqual(pks(featured), [uncertainPk])
  for (const pk of finalFeaturedPks) assert.equal(pks(featured).includes(pk), false)
  // A lone card gets one comfortable column, not half of a two-column row.
  assert.match(featured, /data-featured-count="1"/)
  assert.doesNotMatch(featured, /desktop:grid-cols-2/)
  const two = region(renderPage({ payload: productionPayload() }), 'tonight-featured')
  assert.match(two, /desktop:grid-cols-2/)
})

test('late night: Upcoming holds the same uncertain game; Completed Games (14) is collapsed', () => {
  const html = renderPage({ payload: late })
  assert.deepEqual(pks(region(html, 'tonight-slate-upcoming')), [uncertainPk])
  const completed = region(html, 'tonight-slate-completed')
  assert.match(completed, /Completed Games \(14\)/)
  assert.equal(pks(completed).length, 0)
})

test('15–16. final featured games stay in Completed Games with featured=true data', () => {
  const html = renderPage({ payload: late, completedInitiallyExpanded: true })
  const completed = pks(region(html, 'tonight-slate-completed'))
  for (const pk of finalFeaturedPks) assert.ok(completed.includes(pk), `${pk} in Completed`)
  assert.equal(completed.length, 14)
  for (const pk of late.featured_game_pks) {
    assert.equal(late.games.find(g => g.game_pk === pk).featured, true, 'frozen marker untouched')
  }
  // The helper returns served objects as-is; it never copies or strips fields.
  const [shown] = view.getVisibleFeaturedGames(late.games, late.featured_game_pks)
  assert.equal(shown, late.games.find(g => g.game_pk === uncertainPk))
})

// ── All-final fixture ─────────────────────────────────────────────────────

test('10. all-final featured: section, heading and container are absent; no manufactured copy', () => {
  const payload = allFinalFeaturedPayload()
  const html = renderPage({ payload })
  assert.equal(html.includes('data-testid="tonight-featured"'), false)
  assert.doesNotMatch(html, /Games to Watch|No featured games|Previously featured|Featured earlier/)
  assert.match(region(html, 'tonight-slate'), /Completed Games \(15\)/)
  const expanded = renderPage({ payload, completedInitiallyExpanded: true })
  assert.deepEqual(pks(region(expanded, 'tonight-slate-completed')), payload.games.map(g => g.game_pk))
})

// ── 17–19, 25 neighbours and order ─────────────────────────────────────────

test('17–19, 25. lead, full slate and What Changed unchanged; section order intact', () => {
  const html = renderPage({ payload: late })
  assert.match(region(html, 'tonight-lead'), /data-testid="tonight-lead-pregame"/)
  assert.equal((html.match(/data-testid="tonight-change"/g) || []).length, late.league_changes.length)
  const order = ['tonight-header', 'tonight-lead', 'tonight-featured', 'tonight-slate', 'tonight-changes', 'tonight-go-deeper']
    .map(id => html.indexOf(`data-testid="${id}"`))
  assert.ok(order.every(index => index >= 0))
  assert.deepEqual([...order].sort((a, b) => a - b), order)
  const levels = [...html.matchAll(/<h([1-6])\b/g)].map(m => Number(m[1]))
  levels.slice(1).forEach((level, i) => assert.ok(level - levels[i] <= 1, `heading skip at ${i}`))
})

test('visible featured cards keep backend handoff links', () => {
  const html = renderPage({ payload: late })
  const card = region(html, 'tonight-featured')
  const g = late.games.find(x => x.game_pk === uncertainPk)
  const hrefs = [...card.matchAll(/data-link="[a-z-]+" href="([^"]+)"/g)].map(m => decode(m[1]))
  assert.deepEqual(hrefs, [g.links.away_team_board, g.links.home_team_board, g.links.matchup])
})

test('production (all-unfinished featured) fixture still shows every featured game in order', () => {
  const payload = productionPayload()
  assert.deepEqual(pks(region(renderPage({ payload }), 'tonight-featured')), payload.featured_game_pks)
})

// ── 20–24 guards ──────────────────────────────────────────────────────────

test('21–23. featured lifecycle code: no sort, score or baseball inspection; no toggle or fetch', () => {
  const tonightView = readFileSync(new URL('../src/components/tonight/tonightView.js', import.meta.url), 'utf8')
  const start = tonightView.indexOf('// Featured lifecycle presentation')
  const helper = tonightView.slice(start, tonightView.indexOf('\n}\n', start) + 3)
  const component = readFileSync(new URL('../src/components/tonight/FeaturedGames.jsx', import.meta.url), 'utf8')
  for (const source of [helper, component]) {
    assert.doesNotMatch(source, /\.sort\(|\.reverse\(|Math\.|score|rank|weight|recommend|first_pitch|Date|standing|team_state|teamState|workload|rest\b|key_arms|rotation/i)
    assert.doesNotMatch(source, /useState|useEffect|localStorage|sessionStorage|getTonight|fetch\(|refetch/)
  }
  assert.match(helper, /state !== 'final'/)
  assert.match(helper, /for \(const pk of list\(featuredGamePks\)\)/)
})
