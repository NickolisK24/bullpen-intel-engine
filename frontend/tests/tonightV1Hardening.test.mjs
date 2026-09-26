import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import {
  LONG_CHANGE_DETAIL,
  LONG_CHANGE_HEADLINE,
  LONG_CONTEXT,
  LONG_PLAYER_NAME,
  LONG_ROLE_LABEL,
  LONG_TEAM_NAME,
  MAX_LEAD_DETAIL,
  MAX_LEAD_HEADLINE,
  productionPayload,
  quietPayload,
  stressPayload,
  unavailablePayload,
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

const { APP_ROUTES } = await server.ssrLoadModule('/src/App.jsx')
const { TonightPageView } = await server.ssrLoadModule('/src/components/tonight/TonightPage.jsx')

const TONIGHT_DIR = new URL('../src/components/tonight/', import.meta.url)
const tonightSources = readdirSync(TONIGHT_DIR)
  .map(name => [name, readFileSync(new URL(name, TONIGHT_DIR), 'utf8')])

const renderPage = (props) => renderToStaticMarkup(
  React.createElement(MemoryRouter, { initialEntries: ['/tonight'] }, React.createElement(TonightPageView, props)),
)
const decode = (html) => html.replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, '&')
const textOf = (html) => decode(html.replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim()

function section(html, testId) {
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

const cards = (html, testId) => [...section(html, testId).matchAll(/<article[\s\S]*?<\/article>/g)].map(m => m[0])
const stress = stressPayload()
// Completed games are collapsed by default (TN-11.5); inspect every card with
// the disclosure open and look cards up by game_pk.
const stressHtml = renderPage({ payload: stress, completedInitiallyExpanded: true })
const slateCards = cards(stressHtml, 'tonight-slate')
const pkOf = (card) => Number(card.match(/data-game-pk="(\d+)"/)[1])
const cardByPk = new Map(slateCards.map(card => [pkOf(card), card]))
const cardFor = (index) => cardByPk.get(stress.games[index].game_pk)
const LIFECYCLE_STATES = [['live', 'suspended'], ['scheduled', 'uncertain', 'postponed'], ['final']]
const lifecycleOrder = (games) => LIFECYCLE_STATES.flatMap(states => games.filter(game => states.includes(game.state)))

test('stress edition renders 17 games, 4 featured and 12 changes in backend order', () => {
  assert.equal(slateCards.length, 17)
  const pk = pkOf
  assert.deepEqual(slateCards.map(pk), lifecycleOrder(stress.games).map(game => game.game_pk))
  assert.deepEqual(cards(stressHtml, 'tonight-featured').map(pk), stress.featured_game_pks)
  const headlines = [...section(stressHtml, 'tonight-changes').matchAll(/<p class="-mt-1[^"]*">([\s\S]*?)<\/p>/g)].map(m => decode(m[1]))
  assert.deepEqual(headlines, stress.league_changes.map(change => change.headline))
})

test('every served game state has its label across the stress slate', () => {
  const labels = stress.games.map((_, index) => textOf(cardFor(index).match(/data-testid="tonight-game-status"[^>]*>([^<]*)</)[1]))
  const byState = {}
  stress.games.forEach((game, index) => { (byState[game.state] ||= new Set()).add(labels[index]) })
  assert.deepEqual([...byState.live], ['In progress'])
  assert.deepEqual([...byState.final], ['Final'])
  assert.deepEqual([...byState.postponed], ['Postponed'])
  assert.deepEqual([...byState.suspended], ['Suspended'])
  assert.deepEqual([...byState.uncertain], ['Status not confirmed'])
  assert.ok(labels.includes('Start time not confirmed'), 'scheduled game with no first pitch')
})

test('long team and player names, roles, context and change copy render in full', () => {
  const first = textOf(cardFor(0))
  assert.ok(first.includes(`${LONG_TEAM_NAME} at Boston Red Sox`))
  assert.ok(first.includes(LONG_PLAYER_NAME))
  assert.ok(first.includes(LONG_ROLE_LABEL))
  assert.ok(first.includes(LONG_CONTEXT))
  const changes = textOf(section(stressHtml, 'tonight-changes'))
  assert.ok(changes.includes(LONG_CHANGE_HEADLINE))
  assert.ok(changes.includes(LONG_CHANGE_DETAIL))
  for (const [name, source] of tonightSources) {
    assert.doesNotMatch(source, /\btruncate\b|line-clamp|text-ellipsis|overflow-hidden/, `${name} never clips copy`)
  }
})

test('maximum-length lead headline and detail render verbatim with a Matchup handoff', () => {
  const lead = section(stressHtml, 'tonight-lead')
  assert.equal(MAX_LEAD_HEADLINE.length, 120)
  assert.equal(MAX_LEAD_DETAIL.length, 140)
  assert.ok(textOf(lead).includes(MAX_LEAD_HEADLINE))
  assert.ok(textOf(lead).includes(MAX_LEAD_DETAIL))
  const leadGame = stress.games.find(game => game.game_pk === stress.lead.game_pk)
  assert.match(lead, new RegExp(`data-link="lead-matchup" href="${leadGame.links.matchup}"`))
})

test('a lead whose game is missing renders without a handoff link', () => {
  const payload = productionPayload()
  payload.lead = { ...payload.lead, game_pk: 1 }
  const lead = section(renderPage({ payload }), 'tonight-lead')
  assert.ok(lead.length > 0)
  assert.doesNotMatch(lead, /lead-matchup/)
})

test('withheld, zero-rested and null-rested sides keep their meaning', () => {
  assert.match(cardFor(1), /data-team-state="withheld"[^>]*>Team State withheld</)
  assert.match(cardFor(2), /data-fact="rested">0 rested</)
  const restLimited = cardFor(5).match(/data-testid="tonight-team-side"[\s\S]*?(?=data-testid="tonight-team-side")/)[0]
  assert.match(restLimited, /Rest read unavailable/)
  assert.doesNotMatch(restLimited, /\d+ rested|B2B<|in 3-in-4/)
})

test('large counts, three key arms and wrapping rotation render as frozen', () => {
  const card = cardFor(0)
  assert.match(card, /data-fact="rested">12 rested</)
  assert.match(card, /data-fact="b2b">11 B2B</)
  assert.match(card, /data-fact="three_in_four">10 in 3-in-4</)
  const away = card.match(/data-testid="tonight-team-side"[\s\S]*?(?=data-testid="tonight-team-side")/)[0]
  assert.equal((away.match(/data-testid="tonight-key-arm"/g) || []).length, 3)
  assert.match(card, /data-testid="tonight-rotation">12 recent short starts · 41.2 bullpen IP</)
})

test('only Team State reads as a badge; usage facts are plain text', () => {
  const side = cardFor(0).match(/data-testid="tonight-team-side"[\s\S]*?(?=data-testid="tonight-team-side")/)[0]
  const bordered = [...side.matchAll(/<(?:span|li|p)[^>]*class="[^"]*\bborder\b[^"]*"/g)]
  assert.equal(bordered.length, 1, 'one bordered element per side: the Team State badge')
  assert.match(bordered[0][0], /min-h-8/)
  assert.doesNotMatch(side, /data-fact="[^"]+"[^>]*class="[^"]*border/)
})

test('each card has one action row: away Team Board, home Team Board, Matchup, with distinct names', () => {
  for (const [index, game] of stress.games.entries()) {
    const card = cardFor(index)
    const row = card.match(/data-testid="tonight-card-actions"[\s\S]*$/)[0]
    const links = [...row.matchAll(/<a [^>]*aria-label="([^"]+)"[^>]*href="([^"]+)"/g)].map(m => [decode(m[1]), decode(m[2])])
    assert.deepEqual(links.map(([, href]) => href), [
      game.links.away_team_board, game.links.home_team_board, game.links.matchup,
    ])
    assert.equal(new Set(links.map(([label]) => label)).size, 3)
    assert.equal((card.match(/data-link="team-board"/g) || []).length, 2)
  }
})

test('null context consumes no space; pregame marker only on live context', () => {
  stress.games.forEach((game, index) => {
    const card = cardFor(index)
    if (game.context.sentence) {
      assert.match(card, /data-testid="tonight-context"/)
    } else {
      assert.doesNotMatch(card, /tonight-context/)
    }
    assert.equal(card.includes('tonight-context-pregame'), game.state === 'live')
  })
})

test('lead null, no featured section and no changes section render cleanly', () => {
  const payload = { ...productionPayload(), lead: null, featured_game_pks: [], league_changes: [] }
  const html = renderPage({ payload })
  for (const id of ['tonight-lead', 'tonight-featured', 'tonight-changes']) {
    assert.equal(html.includes(`data-testid="${id}"`), false, id)
  }
  // 15 games, one final: 14 mounted, the final one behind Completed Games (1).
  assert.equal(cards(html, 'tonight-slate').length, 14)
  assert.match(html, /Completed Games \(1\)/)
})

test('quiet day with backend changes keeps the edition header and What Changed', () => {
  const payload = { ...quietPayload(), league_changes: stress.league_changes.slice(0, 5) }
  const html = renderPage({ payload })
  assert.match(textOf(html), /No MLB games are on tonight's slate\./)
  assert.match(html, /data-testid="tonight-date"/)
  assert.equal((html.match(/data-testid="tonight-change"/g) || []).length, 5)
  assert.match(section(html, 'tonight-quiet'), /role="status"/)
})

test('unavailable is a status without retry; error is an alert with exactly one retry', () => {
  const unavailable = renderPage({ payload: unavailablePayload() })
  const block = section(unavailable, 'tonight-unavailable')
  assert.match(block, /role="status"/)
  assert.doesNotMatch(unavailable, /role="alert"|<button/)
  assert.match(textOf(block), /Latest publication: Sep 26, 2026/)

  const error = renderPage({ payload: null, error: 'API 503', onRetry: () => {} })
  const alert = section(error, 'tonight-error')
  assert.match(alert, /role="alert"/)
  assert.equal((error.match(/<button/g) || []).length, 1)
  assert.doesNotMatch(error, /role="status"/)
})

test('one stable h1 with tabindex=-1 in every state; no empty or skipped headings', () => {
  const states = {
    loaded: stressHtml,
    loading: renderPage({ payload: null, loading: true }),
    error: renderPage({ payload: null, error: 'x', onRetry: () => {} }),
    unavailable: renderPage({ payload: unavailablePayload() }),
    quiet: renderPage({ payload: quietPayload() }),
  }
  for (const [name, html] of Object.entries(states)) {
    const h1s = [...html.matchAll(/<h1\b([^>]*)>([\s\S]*?)<\/h1>/g)]
    assert.equal(h1s.length, 1, name)
    assert.match(h1s[0][1], /tabindex="-1"/, name)
    assert.equal(textOf(h1s[0][2]), 'Tonight in MLB Bullpens', name)
    const headings = [...html.matchAll(/<h([1-6])\b[^>]*>([\s\S]*?)<\/h\1>/g)]
    for (const [, , body] of headings) assert.ok(textOf(body).length > 0, `${name}: empty heading`)
    const levels = headings.map(m => Number(m[1]))
    levels.slice(1).forEach((level, i) => assert.ok(level - levels[i] <= 1, `${name}: heading skip`))
  }
})

test('loading skeleton is shape-only: busy status, sr-only label, no baseball values', () => {
  const html = renderPage({ payload: null, loading: true })
  const loading = section(html, 'tonight-loading')
  assert.match(loading, /role="status"/)
  assert.match(loading, /aria-busy="true"/)
  const visible = loading.replace(/<span class="sr-only">[^<]*<\/span>/, '')
  assert.equal(textOf(visible), '')
  assert.match(section(html, 'tonight-header'), /data-testid="tonight-header-skeleton"/)
  assert.doesNotMatch(html, /tonight-quiet|tonight-unavailable|tonight-error/)
})

test('source of truth: hardening adds no sorting, arithmetic, timers or extra data calls', () => {
  const combined = tonightSources.map(([, source]) => source).join('\n')
  assert.doesNotMatch(combined, /\.sort\(|\.reverse\(|Math\.|reduce\(|\.toFixed\(|parseFloat|parseInt/)
  assert.doesNotMatch(combined, /setInterval|setTimeout|requestAnimationFrame|\bfetch\(/)
  assert.doesNotMatch(combined, /getTeamBoard|getMatchup|getFatigue|getBullpen|getTodayIntelligence|getTonightIntelligence|getSyncStatus/)
  const page = tonightSources.find(([name]) => name === 'TonightPage.jsx')[1]
  assert.equal((page.match(/getTonightV1\(/g) || []).length, 1)
  assert.deepEqual(
    tonightSources.filter(([, source]) => /from ['"]\.\.\/\.\.\/utils\/api['"]/.test(source)).map(([name]) => name),
    ['TonightPage.jsx'],
  )
})

test('root routing (TN-10): / and /tonight are TonightPage, /today redirects to /', () => {
  assert.equal(APP_ROUTES.find(route => route.path === '/')?.Component?.name, 'TonightPage')
  assert.equal(APP_ROUTES.find(route => route.path === '/today')?.redirectTo, '/')
  assert.equal(APP_ROUTES.find(route => route.path === '/tonight')?.Component?.name, 'TonightPage')
  const vercel = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))
  assert.ok(vercel.routes.some(route => route.src === '^/today/?$' && route.headers?.Location === '/'))
  assert.ok(vercel.routes.some(route => route.src?.includes('|tonight|') && route.status === 308))
})
