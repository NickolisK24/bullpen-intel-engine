import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import {
  allFinalPayload,
  mixedLifecyclePayload,
  productionPayload,
  quietPayload,
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
const { default: TonightSlate } = await server.ssrLoadModule('/src/components/tonight/TonightSlate.jsx')

const render = (element) => renderToStaticMarkup(React.createElement(MemoryRouter, null, element))
const renderPage = (props) => render(React.createElement(TonightPageView, props))
const decode = (html) => html.replace(/&#x27;/g, "'").replace(/&amp;/g, '&')
const textOf = (html) => decode(html.replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim()
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

const mixed = mixedLifecyclePayload()
const allFinal = allFinalPayload()
const pksWhere = (payload, states) => payload.games.filter(game => states.includes(game.state)).map(game => game.game_pk)
const game = (state, pk) => ({ ...productionPayload().games[0], game_pk: pk, state })

// ── 1–6, 38–40 mapping ─────────────────────────────────────────────────────

test('1–6. served game.state maps to exactly one lifecycle bucket', () => {
  const groups = view.groupGamesByLifecycle([
    game('live', 1), game('suspended', 2), game('scheduled', 3),
    game('uncertain', 4), game('postponed', 5), game('final', 6),
  ])
  assert.deepEqual(groups.inProgress.map(g => g.game_pk), [1, 2])
  assert.deepEqual(groups.upcoming.map(g => g.game_pk), [3, 4, 5])
  assert.deepEqual(groups.completed.map(g => g.game_pk), [6])
  assert.deepEqual({ ...view.LIFECYCLE_BY_STATE }, {
    live: 'inProgress', suspended: 'inProgress',
    scheduled: 'upcoming', uncertain: 'upcoming', postponed: 'upcoming',
    final: 'completed',
  })
})

test('38–39. postponed stays Upcoming and suspended stays In Progress, never Completed', () => {
  const html = renderPage({ payload: mixed })
  const postponed = mixed.games.find(g => g.state === 'postponed').game_pk
  const suspended = mixed.games.find(g => g.state === 'suspended').game_pk
  assert.ok(pks(region(html, 'tonight-slate-upcoming')).includes(postponed))
  assert.ok(pks(region(html, 'tonight-slate-in-progress')).includes(suspended))
})

test('40. an unknown state fails safe to Upcoming, never Completed, with no new label', () => {
  const groups = view.groupGamesByLifecycle([game('rain_delay', 7), game(undefined, 8), null])
  assert.deepEqual(groups.upcoming.map(g => g?.game_pk ?? null), [7, 8, null])
  assert.equal(groups.completed.length, 0)
  const html = render(React.createElement(TonightSlate, { games: [game('rain_delay', 7)] }))
  assert.match(html, /Status not confirmed/)
  assert.doesNotMatch(textOf(html), /Completed Games|rain_delay/, 'no new visible label')
})

// ── 7–10 ordering ─────────────────────────────────────────────────────────

test('7–10. backend order is preserved inside each bucket; buckets render in fixed order', () => {
  const html = renderPage({ payload: mixed, completedInitiallyExpanded: true })
  assert.deepEqual(pks(region(html, 'tonight-slate-in-progress')), pksWhere(mixed, ['live', 'suspended']))
  assert.deepEqual(pks(region(html, 'tonight-slate-upcoming')), pksWhere(mixed, ['scheduled', 'uncertain', 'postponed']))
  assert.deepEqual(pks(region(html, 'tonight-slate-completed')), pksWhere(mixed, ['final']))
  const at = (id) => html.indexOf(`data-testid="${id}"`)
  assert.ok(at('tonight-slate-in-progress') < at('tonight-slate-upcoming'))
  assert.ok(at('tonight-slate-upcoming') < at('tonight-slate-completed'))
  // Reversing the input reverses order inside each bucket: no hidden sort.
  const reversed = view.groupGamesByLifecycle([...mixed.games].reverse())
  assert.deepEqual(reversed.upcoming.map(g => g.game_pk), [...pksWhere(mixed, ['scheduled', 'uncertain', 'postponed'])].reverse())
})

// ── 11–13 empty headings ───────────────────────────────────────────────────

test('11–12. empty In Progress and Upcoming headings are omitted', () => {
  const upcomingOnly = render(React.createElement(TonightSlate, { games: [game('scheduled', 1), game('final', 2)] }))
  assert.doesNotMatch(upcomingOnly, /tonight-slate-in-progress|>In Progress</)
  assert.match(upcomingOnly, />Upcoming</)
  const liveOnly = render(React.createElement(TonightSlate, { games: [game('live', 1)] }))
  assert.doesNotMatch(liveOnly, /tonight-slate-upcoming|>Upcoming<|Completed Games/)
})

test('13, 31. a true quiet day renders no slate and no Completed Games (0)', () => {
  const html = renderPage({ payload: quietPayload() })
  assert.match(textOf(html), /No MLB games are on tonight's slate\./)
  assert.doesNotMatch(html, /tonight-slate|Completed Games/)
})

// ── 14–17 collapsed defaults ───────────────────────────────────────────────

test('14, 17, 22. mixed slate: Completed Games (7) collapsed with no completed cards mounted', () => {
  const html = renderPage({ payload: mixed })
  const completed = region(html, 'tonight-slate-completed')
  assert.match(completed, /Completed Games \(7\)/)
  assert.equal(pks(completed).length, 0)
  assert.equal(pks(region(html, 'tonight-slate')).length, 10)
  assert.match(completed, /aria-expanded="false"/)
  assert.doesNotMatch(html, /data-testid="tonight-all-final"/)
})

test('15–17. all-final slate: helper text, Completed Games (17), zero cards before expansion', () => {
  const html = renderPage({ payload: allFinal })
  const slate = region(html, 'tonight-slate')
  assert.match(textOf(slate), /All of tonight's games are complete\./)
  assert.match(slate, /Completed Games \(17\)/)
  assert.equal(pks(slate).length, 0)
  assert.doesNotMatch(slate, />In Progress<|>Upcoming</)
  for (const id of ['tonight-header', 'tonight-lead', 'tonight-featured', 'tonight-changes', 'tonight-go-deeper']) {
    assert.ok(html.includes(`data-testid="${id}"`), id)
  }
})

test('23, 25, 37. expanded completed cards use TonightGameCard and still read Final', () => {
  const html = renderPage({ payload: allFinal, completedInitiallyExpanded: true })
  const completed = region(html, 'tonight-slate-completed')
  assert.deepEqual(pks(completed), allFinal.games.map(g => g.game_pk))
  const statuses = [...completed.matchAll(/data-testid="tonight-game-status"[^>]*>([^<]*)</g)].map(m => m[1])
  assert.equal(statuses.length, 17)
  assert.ok(statuses.every(status => status === 'Final'))
  assert.match(completed, /<article class="card[^"]*"[^>]*data-testid="tonight-game-card"/)
  assert.match(completed, /aria-expanded="true"/)
  assert.match(completed, />Hide completed games</)
})

// ── 18–24 disclosure semantics ─────────────────────────────────────────────

test('20–21, 24. disclosure button has a name, aria-expanded and a valid aria-controls target', () => {
  const html = renderPage({ payload: mixed })
  const button = html.match(/<button[^>]*data-testid="tonight-completed-toggle"[^>]*>([^<]*)<\/button>/)
  assert.ok(button)
  assert.equal(button[1], 'Show completed games')
  const controls = button[0].match(/aria-controls="([^"]+)"/)[1]
  const target = html.match(new RegExp(`<div id="${controls}"([^>]*)>`))
  assert.ok(target, 'aria-controls references an element in the DOM')
  assert.match(target[1], /hidden=""/)
  // No completed links exist while collapsed, so none can be tabbed to.
  const completed = region(html, 'tonight-slate-completed')
  assert.equal((completed.match(/<a /g) || []).length, 0)
})

test('18–19. toggle source flips local state only: no fetch, URL or storage', () => {
  const source = readFileSync(new URL('../src/components/tonight/TonightSlate.jsx', import.meta.url), 'utf8')
  assert.match(source, /useState\(initiallyExpanded\)/)
  assert.match(source, /setExpanded\(open => !open\)/)
  assert.doesNotMatch(source, /localStorage|sessionStorage|useNavigate|useSearchParams|history\.|document\.cookie|getTonightV1|refetch/)
  assert.match(source, /\{expanded && \(/, 'completed cards mount only when expanded')
})

// ── 32–36 unchanged neighbours ─────────────────────────────────────────────

test('32–36. lead, featured, What Changed and handoff links are unchanged by lifecycle grouping', () => {
  const html = renderPage({ payload: mixed, completedInitiallyExpanded: true })
  const lead = region(html, 'tonight-lead')
  assert.match(lead, /data-testid="tonight-lead-pregame"/, 'lead keeps its served pregame marker')
  assert.deepEqual(pks(region(html, 'tonight-featured')), mixed.featured_game_pks, 'featured keeps final games')
  assert.equal((html.match(/data-testid="tonight-change"/g) || []).length, 12)
  for (const g of mixed.games) {
    const card = region(html, 'tonight-slate').match(new RegExp(`<article[^>]*data-game-pk="${g.game_pk}"[\\s\\S]*?</article>`))[0]
    const hrefs = [...card.matchAll(/data-link="[a-z-]+" href="([^"]+)"/g)].map(m => decode(m[1]))
    assert.deepEqual(hrefs, [g.links.away_team_board, g.links.home_team_board, g.links.matchup])
  }
})

test('heading order stays logical: h2 slate → h3 lifecycle groups → h4 cards', () => {
  const html = renderPage({ payload: mixed, completedInitiallyExpanded: true })
  const headings = [...html.matchAll(/<h([1-6])\b[^>]*>([\s\S]*?)<\/h\1>/g)]
  const levels = headings.map(m => Number(m[1]))
  levels.slice(1).forEach((level, i) => assert.ok(level - levels[i] <= 1, `heading skip at ${i}`))
  for (const [, , body] of headings) assert.ok(textOf(body).length > 0, 'no empty heading')
  const slate = region(html, 'tonight-slate')
  assert.match(slate, /<h3[^>]*>In Progress<\/h3>/)
  assert.match(slate, /<h3[^>]*>Upcoming<\/h3>/)
  assert.match(slate, /<h3[^>]*>Completed Games \(7\)<\/h3>/)
  assert.equal((slate.match(/<h4\b/g) || []).length, 17)
})

// ── 29–30 source of truth ─────────────────────────────────────────────────

test('29–30. lifecycle code maps state only: no sort, reverse, Math, score, rank, weight or time', () => {
  const tonightView = readFileSync(new URL('../src/components/tonight/tonightView.js', import.meta.url), 'utf8')
  const lifecycle = tonightView.slice(tonightView.indexOf('// Slate lifecycle presentation'))
  const slate = readFileSync(new URL('../src/components/tonight/TonightSlate.jsx', import.meta.url), 'utf8')
  for (const source of [lifecycle, slate]) {
    assert.doesNotMatch(source, /\.sort\(|\.reverse\(|Math\.|score|rank|weight|first_pitch|Date|getTime|inning/i)
  }
  assert.match(lifecycle, /for \(const game of list\(games\)\)/, 'single pass')
})
