import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import {
  gameCard,
  leagueChanges,
  productionPayload,
  quietPayload,
  teamSide,
  unavailablePayload,
  withheldSide,
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
const { default: TonightGameCard } = await server.ssrLoadModule('/src/components/tonight/TonightGameCard.jsx')
const view = await server.ssrLoadModule('/src/components/tonight/tonightView.js')
const { metadataForLocation } = await server.ssrLoadModule('/src/utils/publicRouteMetadata.js')

const TONIGHT_DIR = new URL('../src/components/tonight/', import.meta.url)
const tonightSources = readdirSync(TONIGHT_DIR)
  .map(name => [name, readFileSync(new URL(name, TONIGHT_DIR), 'utf8')])

const render = (element) => renderToStaticMarkup(
  React.createElement(MemoryRouter, { initialEntries: ['/tonight'] }, element),
)
const renderPage = (props) => render(React.createElement(TonightPageView, props))
const renderGame = (game) => render(React.createElement(TonightGameCard, { game }))

const decode = (html) => html
  .replace(/&#x27;/g, "'")
  .replace(/&quot;/g, '"')
  .replace(/&amp;/g, '&')
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

const gamePksIn = (html) => [...html.matchAll(/data-testid="tonight-game-card" data-game-pk="(\d+)"/g)]
  .map(match => Number(match[1]))

function singleGame(overrides = {}, sides = {}) {
  return gameCard(
    900001,
    sides.away || teamSide(0),
    sides.home || teamSide(1),
    overrides,
  )
}

// ── 1–4 route, API method, no v5 fallback ─────────────────────────────────

test('1. /tonight is a first-class route rendered by TonightPage', () => {
  const route = APP_ROUTES.find(item => item.path === '/tonight')
  assert.equal(route?.Component?.name, 'TonightPage')
  assert.equal(route?.redirectTo, undefined)
})

test('2. / renders TonightPage (TN-10 cutover) and /today redirects to /', () => {
  assert.equal(APP_ROUTES.find(item => item.path === '/')?.Component?.name, 'TonightPage')
  assert.equal(APP_ROUTES.find(item => item.path === '/today')?.redirectTo, '/')
})

test('3. getTonightV1 requests contract=tonight_v1 exactly once with no client cache', async () => {
  const api = await server.ssrLoadModule('/src/utils/api.js')
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), options })
    return { ok: true, status: 200, json: async () => productionPayload() }
  }
  try {
    const first = await api.getTonightV1()
    const second = await api.getTonightV1()
    assert.equal(first.contract, 'tonight_v1')
    assert.equal(second.contract, 'tonight_v1')
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.equal(calls.length, 2, 'no client response cache: every load reaches the server')
  for (const call of calls) {
    const url = new URL(call.url, 'http://localhost')
    assert.equal(url.pathname.endsWith('/bullpen/intelligence/tonight'), true)
    assert.equal(url.searchParams.get('contract'), 'tonight_v1')
    assert.deepEqual([...url.searchParams.keys()], ['contract'])
  }
  const source = readFileSync(new URL('../src/utils/api.js', import.meta.url), 'utf8')
  const helper = source.slice(source.indexOf('export const getTonightV1'), source.indexOf('// Game context for one team'))
  assert.doesNotMatch(helper, /cachePolicy|tonight_v5/)
})

test('4. a non-v1 or v5-shaped body is never rendered as Tonight (no v5 fallback)', () => {
  const legacy = { contract: 'tonight_v5', games: productionPayload().games, edition: {} }
  assert.equal(view.classifyTonightResponse(legacy), 'unavailable')
  const html = renderPage({ payload: legacy })
  assert.match(textOf(html), /Tonight's trusted bullpen edition isn't available yet\./)
  assert.equal(gamePksIn(html).length, 0)
  for (const [name, source] of tonightSources) {
    assert.doesNotMatch(source, /getTonightIntelligence|getTodayIntelligence|tonight_v5/, name)
  }
})

// ── 5–7 header and summary ───────────────────────────────────────────────

test('5. header shows the title, edition date and a subtle data-through line', () => {
  const html = renderPage({ payload: productionPayload() })
  const header = section(html, 'tonight-header')
  assert.match(header, /<h1[^>]*>Tonight in MLB Bullpens<\/h1>/)
  assert.match(textOf(header), /September 26, 2026/)
  assert.match(textOf(header), /Data through Sep 25, 2026/)
  assert.equal((html.match(/<h1\b/g) || []).length, 1)
})

test('6. summary is built only from game_count, team_state_counts, B2B clubs and change_count', () => {
  const payload = productionPayload()
  const s = payload.summary
  const summary = textOf(section(renderPage({ payload }), 'tonight-summary'))
  assert.match(summary, new RegExp(`${s.game_count} games`))
  assert.match(summary, new RegExp(`Team State: ${s.team_state_counts.fresh} Fresh · ${s.team_state_counts.stretched} Stretched · ${s.team_state_counts.vulnerable} Vulnerable`))
  assert.match(summary, new RegExp(`${s.clubs_with_back_to_back_arms} clubs with back-to-back arms`))
  assert.match(summary, new RegExp(`${s.change_count} bullpen changes`))
})

test('7. summary omits zero and unavailable values and never invents a count', () => {
  const items = view.summaryItems({
    game_count: 1,
    team_state_counts: { fresh: 0, stretched: 2, vulnerable: null, withheld: 0 },
    clubs_with_back_to_back_arms: 0,
    change_count: null,
  })
  assert.deepEqual(items.map(item => item.text), ['1 game', 'Team State: 2 Stretched'])
  assert.deepEqual(view.summaryItems({ game_count: 3, team_state_counts: { withheld: 6 } }).map(i => i.text), [
    '3 games', 'Team State: 6 withheld',
  ])
  assert.deepEqual(view.summaryItems(null), [])
})

// ── 8–10 lead ────────────────────────────────────────────────────────────

test('8. a null lead renders nothing', () => {
  const html = renderPage({ payload: { ...productionPayload(), lead: null } })
  assert.equal(html.includes('data-testid="tonight-lead"'), false)
  assert.doesNotMatch(textOf(html), /Lead development/)
})

test('9. the lead renders its frozen headline and detail verbatim', () => {
  const payload = productionPayload()
  const lead = textOf(section(renderPage({ payload }), 'tonight-lead'))
  assert.match(lead, /SEA moved into a Vulnerable bullpen state entering tonight\./)
  assert.match(lead, /SEA is scheduled to face HOU\./)
  assert.doesNotMatch(lead, /Pregame context/)
})

test('10. the lead shows a subtle Pregame context label when marked', () => {
  const payload = productionPayload()
  payload.lead = { ...payload.lead, reason_codes: ['team_state_to_vulnerable', 'pregame_context'] }
  const lead = section(renderPage({ payload }), 'tonight-lead')
  assert.match(lead, /data-testid="tonight-lead-pregame"[^>]*>Pregame context</)
})

// ── 11–14 featured and slate ─────────────────────────────────────────────

test('11. Games to Watch follows featured_game_pks order exactly', () => {
  const payload = productionPayload()
  const featured = section(renderPage({ payload }), 'tonight-featured')
  assert.match(featured, /<h2[^>]*>Games to Watch<\/h2>/)
  assert.deepEqual(gamePksIn(featured), payload.featured_game_pks)
})

test('12. no featured games renders no Games to Watch section', () => {
  const html = renderPage({ payload: { ...productionPayload(), featured_game_pks: [] } })
  assert.equal(html.includes('data-testid="tonight-featured"'), false)
})

test('13. featured and slate use the same TonightGameCard markup', () => {
  const payload = productionPayload()
  const html = renderPage({ payload })
  const pk = payload.featured_game_pks[0]
  const cards = [...html.matchAll(new RegExp(`<article[^>]*data-game-pk="${pk}"[\\s\\S]*?</article>`, 'g'))]
    .map(match => match[0].replace(/(featured|slate)-\d+-heading/g, 'ID'))
  assert.equal(cards.length, 2)
  assert.equal(cards[0], cards[1])
})

test('14. Tonight\'s Slate renders every game in backend order, never re-sorted', () => {
  const payload = productionPayload()
  payload.games = [...payload.games].reverse()
  const slate = section(renderPage({ payload }), 'tonight-slate')
  assert.match(slate, /<h2[^>]*>Tonight&#x27;s Slate<\/h2>/)
  assert.deepEqual(gamePksIn(slate), payload.games.map(game => game.game_pk))
})

// ── 15–21 game state labels ──────────────────────────────────────────────

test('15. scheduled shows first pitch time in ET', () => {
  const html = renderGame(singleGame({ first_pitch_utc: '2026-09-26T23:05:00Z' }))
  assert.match(html, /data-testid="tonight-game-status"[^>]*>7:05 PM ET</)
})

test('16. scheduled without a first pitch time says so instead of guessing', () => {
  const html = renderGame(singleGame({ first_pitch_utc: null }))
  assert.match(html, />Start time not confirmed</)
})

test('17. uncertain shows conservative status text', () => {
  const html = renderGame(singleGame({ state: 'uncertain' }))
  assert.match(html, />Status not confirmed</)
  assert.doesNotMatch(html, /PM ET/)
})

test('18. live shows In progress', () => {
  assert.match(renderGame(singleGame({ state: 'live' })), />In progress</)
})

test('19. final shows Final', () => {
  assert.match(renderGame(singleGame({ state: 'final' })), />Final</)
})

test('20. postponed shows Postponed', () => {
  assert.match(renderGame(singleGame({ state: 'postponed' })), />Postponed</)
})

test('21. suspended shows Suspended; an unknown state stays conservative', () => {
  assert.match(renderGame(singleGame({ state: 'suspended' })), />Suspended</)
  assert.match(renderGame(singleGame({ state: 'rain_delay' })), />Status not confirmed</)
})

// ── 22–24 Team State ─────────────────────────────────────────────────────

test('22. Team State renders its canonical label as text, never color alone', () => {
  const html = renderGame(singleGame())
  assert.match(textOf(html), /Team State: Fresh/)
  assert.match(textOf(html), /Team State: Stretched/)
  assert.match(html, /data-team-state="fresh"/)
})

test('23. a withheld Team State is explicit', () => {
  const html = renderGame(singleGame({}, { away: withheldSide(0) }))
  assert.match(html, /data-team-state="withheld"[^>]*>Team State withheld</)
  assert.match(textOf(html), /Bullpen read unavailable for this club\./)
})

test('24. a non-canonical Team State fails closed to withheld', () => {
  const away = teamSide(0, {
    team_state: { public_state: 'gassed', public_label: 'Gassed', available: true, reason_code: null },
  })
  const html = renderGame(singleGame({}, { away }))
  assert.doesNotMatch(html, /Gassed/)
  assert.match(html, />Team State withheld</)
})

// ── 25–31 rest, patterns, key arms, rotation ─────────────────────────────

test('25. rested count is shown, including a known zero', () => {
  const away = teamSide(0)
  away.rest = { ...away.rest, rested_arm_count: 0 }
  const html = renderGame(singleGame({}, { away }))
  assert.match(html, /class="whitespace-nowrap" data-fact="rested">0 rested</)
})

test('26. unavailable rest is never rendered as zero', () => {
  const away = teamSide(0)
  away.rest = { ...away.rest, available: false, rested_arm_count: null, back_to_back_count: null }
  const html = renderGame(singleGame({}, { away }))
  const side = section(html, 'tonight-team-side')
  assert.doesNotMatch(side, /0 rested|0 B2B/)
  assert.match(side, /Rest read unavailable/)
})

test('27. B2B appears only when greater than zero', () => {
  const zero = teamSide(0)
  zero.rest = { ...zero.rest, back_to_back_count: 0 }
  assert.doesNotMatch(section(renderGame(singleGame({}, { away: zero })), 'tonight-team-side'), /data-fact="b2b"/)
  const two = teamSide(0)
  two.rest = { ...two.rest, back_to_back_count: 2 }
  assert.match(renderGame(singleGame({}, { away: two })), /class="whitespace-nowrap" data-fact="b2b">2 B2B</)
})

test('28. N in 3-in-4 appears only when greater than zero; null is never zero', () => {
  const one = teamSide(0, { multi_day_usage: { three_in_four_count: 1 } })
  assert.match(renderGame(singleGame({}, { away: one })), /class="whitespace-nowrap" data-fact="three_in_four">1 in 3-in-4</)
  for (const value of [0, null]) {
    const side = teamSide(0, { multi_day_usage: { three_in_four_count: value } })
    assert.doesNotMatch(renderGame(singleGame({}, { away: side })), /in 3-in-4/)
  }
})

test('29. key arms show name, role label and pattern', () => {
  const away = teamSide(1)
  const html = renderGame(singleGame({}, { away }))
  const arms = [...html.matchAll(/data-testid="tonight-key-arm">([\s\S]*?)<\/li>/g)].map(m => textOf(m[1]))
  assert.ok(arms.includes('BOS Trust Arm · Trust arm · B2B'))
  assert.ok(arms.includes('BOS Bridge Arm · Bridge arm'))
})

test('30. rotation renders only when present, in the compact form', () => {
  const away = teamSide(0, {
    rotation: { short_start_count: 1, bullpen_innings: '6.0', games_analyzed: 5, status: 'complete' },
  })
  assert.match(renderGame(singleGame({}, { away })), /data-testid="tonight-rotation">1 recent short start · 6.0 bullpen IP</)
  const two = teamSide(0, {
    rotation: { short_start_count: 2, bullpen_innings: '9.1', games_analyzed: 5, status: 'partial' },
  })
  assert.match(renderGame(singleGame({}, { away: two })), />2 recent short starts · 9.1 bullpen IP</)
})

test('31. a null rotation is omitted', () => {
  const html = renderGame(singleGame({}, {
    away: teamSide(0, { rotation: null }),
    home: teamSide(1, { rotation: null }),
  }))
  assert.equal(html.includes('tonight-rotation'), false)
})

// ── 32–35 context and links ──────────────────────────────────────────────

test('32. context.sentence renders verbatim when present', () => {
  const sentence = 'SEA enters tonight with a Vulnerable bullpen state, while HOU is Stretched.'
  const html = renderGame(singleGame({
    context: { sentence, reason_codes: ['team_state_vulnerable'], evidence_state: 'complete' },
  }))
  assert.match(textOf(section(html, 'tonight-context')), new RegExp(sentence.replace('.', '\\.')))
  assert.doesNotMatch(html, /Pregame context/)
})

test('33. a null context sentence renders no context block', () => {
  const html = renderGame(singleGame({
    context: { sentence: null, reason_codes: ['pregame_context_hidden'], evidence_state: 'complete' },
  }))
  assert.equal(html.includes('tonight-context'), false)
})

test('34. a live context carries the Pregame context marker', () => {
  const html = renderGame(singleGame({
    state: 'live',
    context: { sentence: 'NYY is Fresh entering tonight; BOS is Stretched.', reason_codes: ['team_state_contrast', 'pregame_context'], evidence_state: 'complete' },
  }))
  assert.match(html, /data-testid="tonight-context-pregame"[^>]*>Pregame context</)
})

test('35. card links are the backend-authored Team Board and Matchup links', () => {
  const game = singleGame()
  const html = renderGame(game)
  const hrefs = [...html.matchAll(/href="([^"]+)"/g)].map(m => decode(m[1]))
  assert.deepEqual(hrefs, [
    game.links.away_team_board,
    game.links.home_team_board,
    game.links.matchup,
  ])
  assert.match(textOf(html), /NYY Team Board/)
  assert.match(textOf(html), /BOS Team Board/)
  assert.match(textOf(html), /Matchup/)
})

// ── 36–37 What Changed ───────────────────────────────────────────────────

test('36. What Changed shows team, headline, detail, date and a Team Board link', () => {
  const changes = section(renderPage({ payload: productionPayload() }), 'tonight-changes')
  assert.match(changes, /<h2[^>]*>What Changed<\/h2>/)
  const items = [...changes.matchAll(/data-testid="tonight-change">([\s\S]*?)<\/li>/g)].map(m => textOf(m[1]))
  assert.equal(items[0], 'SEA · Sep 25, 2026 Team Board SEA moved from Stretched to Vulnerable.')
  assert.equal(items[1], 'NYY Team Board NYY Call-Up joined the active bullpen. Verified transaction: Recalled.')
  const hrefs = [...changes.matchAll(/href="([^"]+)"/g)].map(m => decode(m[1]))
  assert.deepEqual(hrefs, ['/bullpen?view=board&team=SEA', '/bullpen?view=board&team=NYY'])
  const order = [...changes.matchAll(/data-testid="tonight-change"/g)].length
  assert.equal(order, leagueChanges.length)
})

test('37. change_id and source_ref are never rendered', () => {
  const html = renderPage({ payload: productionPayload() })
  for (const change of leagueChanges) {
    assert.equal(html.includes(change.change_id), false)
    assert.equal(html.includes(change.source_ref), false)
  }
  assert.doesNotMatch(html, /team_board_what_changed_v1|#transaction:/)
})

// ── 38–40 page states ────────────────────────────────────────────────────

test('38. a quiet day says no MLB games are on tonight\'s slate', () => {
  const html = renderPage({ payload: quietPayload() })
  assert.match(textOf(html), /No MLB games are on tonight's slate\./)
  assert.match(html, /<h1[^>]*>Tonight in MLB Bullpens<\/h1>/)
  assert.equal(gamePksIn(html).length, 0)
  assert.doesNotMatch(textOf(section(html, 'tonight-summary')), /0 /)
})

test('39. an unavailable edition fails closed with the publication date when present', () => {
  const html = renderPage({ payload: unavailablePayload() })
  const text = textOf(html)
  assert.match(text, /Tonight's trusted bullpen edition isn't available yet\./)
  assert.match(text, /Latest publication: Sep 26, 2026/)
  assert.match(html, /<h1[^>]*>Tonight in MLB Bullpens<\/h1>/)
  const bare = textOf(renderPage({ payload: unavailablePayload({ withPublication: false }) }))
  assert.match(bare, /isn't available yet\./)
  assert.doesNotMatch(bare, /Latest publication/)
})

test('40. network error offers retry; loading renders skeletons', () => {
  let retried = 0
  const errorHtml = renderPage({ payload: null, error: 'API 503', onRetry: () => { retried += 1 } })
  assert.match(errorHtml, /role="alert"/)
  assert.match(textOf(errorHtml), /Tonight's bullpen view couldn't be loaded\./)
  assert.match(errorHtml, /<button type="button"[^>]*>Try again<\/button>/)
  assert.equal(retried, 0)

  const loadingHtml = renderPage({ payload: null, loading: true })
  assert.match(loadingHtml, /data-testid="tonight-loading"/)
  assert.match(loadingHtml, /aria-busy="true"/)
  assert.match(loadingHtml, /foundation-skeleton/)
  assert.match(textOf(loadingHtml), /Loading tonight's bullpen view/)
})

// ── production-shaped fixture and source of truth ────────────────────────

test('production-shaped 15-game edition renders every section in order', () => {
  const payload = productionPayload()
  const html = renderPage({ payload })
  const order = ['tonight-header', 'tonight-lead', 'tonight-featured', 'tonight-slate', 'tonight-changes', 'tonight-go-deeper']
    .map(id => html.indexOf(`data-testid="${id}"`))
  assert.ok(order.every(index => index >= 0), String(order))
  assert.deepEqual([...order].sort((a, b) => a - b), order)
  assert.equal(gamePksIn(section(html, 'tonight-slate')).length, 15)
  const slate = section(html, 'tonight-slate')
  assert.match(slate, new RegExp(`data-game-pk="${payload.games[2].game_pk}" data-game-state="live"`))
  assert.match(slate, new RegExp(`data-game-pk="${payload.games[3].game_pk}" data-game-state="final"`))
  const headings = [...html.matchAll(/<h([1-6])\b/g)].map(m => Number(m[1]))
  assert.equal(headings[0], 1)
  for (let i = 1; i < headings.length; i += 1) {
    assert.ok(headings[i] - headings[i - 1] <= 1, `heading level jump at ${i}`)
  }
})

test('source of truth: every rendered fact is the backend value, not a recomputation', () => {
  const payload = productionPayload()
  const html = renderPage({ payload })
  const slate = section(html, 'tonight-slate')
  const cards = [...slate.matchAll(/<article[\s\S]*?<\/article>/g)].map(m => m[0])
  assert.equal(cards.length, payload.games.length)
  cards.forEach((card, index) => {
    const game = payload.games[index]
    const sides = [...card.matchAll(/data-testid="tonight-team-side"[\s\S]*?(?=data-testid="tonight-team-side"|data-testid="tonight-context"|data-link="matchup"|$)/g)]
      .map(m => m[0])
    ;[game.away, game.home].forEach((side, sideIndex) => {
      const markup = sides[sideIndex]
      assert.match(markup, new RegExp(`data-team-state="${side.team_state.public_state}"`))
      assert.match(markup, new RegExp(`>${side.rest.rested_arm_count} rested<`))
      if (side.rest.back_to_back_count > 0) {
        assert.match(markup, new RegExp(`>${side.rest.back_to_back_count} B2B<`))
      } else {
        assert.doesNotMatch(markup, /B2B</)
      }
    })
    if (game.context.sentence) assert.ok(textOf(card).includes(game.context.sentence))
  })

  const combined = tonightSources.map(([, source]) => source).join('\n')
  assert.doesNotMatch(combined, /\.sort\(|\.reverse\(|Math\.|reduce\(/, 'no reordering or arithmetic over baseball facts')
  assert.doesNotMatch(combined, /getTeamBoard|getMatchup|getFatigue|getBullpen|getTodayIntelligence|getTonightIntelligence|setInterval|setTimeout/)
  const page = tonightSources.find(([name]) => name === 'TonightPage.jsx')[1]
  assert.equal((page.match(/getTonightV1\(/g) || []).length, 1)
  assert.doesNotMatch(combined, /TonightsBullpenBoard/)
})

test('route entry metadata describes /tonight without mutable baseball claims', () => {
  const meta = metadataForLocation('/tonight')
  // TN-10: /tonight is the same product as the root, so it shares the root
  // title and canonicalizes to / (no duplicate indexable page).
  assert.equal(meta?.title, 'BaseballOS | Tonight in MLB Bullpens')
  assert.equal(meta?.title, metadataForLocation('/')?.title)
  assert.equal(meta?.canonicalUrl, 'https://baseballos.app/')
  assert.doesNotMatch(meta.description, /\b\d+\b|Fresh|Stretched|Vulnerable/)
  const vercel = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))
  assert.ok(vercel.routes.some(route => route.src === '^/tonight$' && route.dest === '/route-entry/tonight.html'))
  const sitemap = readFileSync(new URL('../public/sitemap.xml', import.meta.url), 'utf8')
  assert.doesNotMatch(sitemap, /\/tonight/)
})
