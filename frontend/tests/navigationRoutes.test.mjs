import assert from 'node:assert/strict'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import { differingComparison } from './fixtures/bullpenComparisonFixtures.mjs'

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
const { default: Sidebar } = await server.ssrLoadModule('/src/components/Sidebar.jsx')
const { legacyPitcherDestination } = await server.ssrLoadModule('/src/components/bullpen/BullpenRoute.jsx')
const { MatchupPageView, historicalMatchupPayload } = await server.ssrLoadModule('/src/components/bullpen/MatchupPage.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))
const metaContent = (html, name) => {
  const match = html.match(new RegExp(`<meta (?:property|name)="${escapeRegExp(name)}" content="([^"]+)" />`))
  return match?.[1] || ''
}
const internalShareTitleLabels = [
  'Sustainability Question',
  'Pressure Distribution',
  'Stress Transfer',
  'Hidden Capacity Loss',
  'Thinning Trust Lane',
]
const publicProductRoutes = ['/', '/dashboard', '/bullpen', '/search', '/stories', '/methodology', '/trust']
const safeHeroDescription = 'See how every MLB bullpen enters tonight’s games: published Team State, rest, recent usage, and what changed, with the data date always shown.'
const blockedEvidenceCopyPatterns = [
  /see the evidence behind/i,
  /evidence behind (?:each|every) read/i,
]

function routeByPath(path) {
  return APP_ROUTES.find(route => route.path === path)
}

test('root HTML uses the public BaseballOS domain for canonical and social metadata', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8')

  assert.ok(htmlIncludes(html, '<title>BaseballOS | Tonight in MLB Bullpens</title>'))
  assert.ok(htmlIncludes(html, safeHeroDescription))
  assert.ok(htmlIncludes(html, '<link rel="canonical" href="https://baseballos.app/" />'))
  assert.ok(htmlIncludes(html, '<meta property="og:url" content="https://baseballos.app/" />'))
  assert.ok(htmlIncludes(html, '<meta property="og:image" content="https://baseballos.app/og/baseballos-card.png" />'))
  assert.ok(htmlIncludes(html, '<meta property="og:image:width" content="1200" />'))
  assert.ok(htmlIncludes(html, '<meta property="og:image:height" content="630" />'))
  assert.ok(htmlIncludes(html, '<meta property="og:image:type" content="image/png" />'))
  assert.ok(htmlIncludes(html, '<meta name="twitter:card" content="summary_large_image" />'))
  assert.ok(htmlIncludes(html, '<meta name="twitter:image" content="https://baseballos.app/og/baseballos-card.png" />'))
  assert.equal(htmlIncludes(html, 'baseballos-card.svg'), false)
  assert.equal(htmlIncludes(html, 'baseballos.vercel.app'), false)
})

test('public homepage and README copy do not imply evidence surfacing', () => {
  const publicCopy = [
    readFileSync(new URL('../index.html', import.meta.url), 'utf8'),
    // TN-11: the homepage is Tonight v1; the retired Home surface is gone.
    readFileSync(new URL('../src/components/tonight/TonightPage.jsx', import.meta.url), 'utf8'),
    readFileSync(new URL('../src/components/tonight/tonightView.js', import.meta.url), 'utf8'),
    readFileSync(new URL('../../README.md', import.meta.url), 'utf8'),
  ].join('\n')

  for (const pattern of blockedEvidenceCopyPatterns) {
    assert.equal(pattern.test(publicCopy), false, String(pattern))
  }
})

test('/ is Tonight, /today redirects to it, and the client catch-all renders not found', () => {
  assert.equal(routeByPath('/')?.Component?.name, 'TonightPage')
  assert.equal(routeByPath('/tonight')?.Component, routeByPath('/')?.Component)
  assert.equal(routeByPath('/today')?.redirectTo, '/')
  assert.equal(routeByPath('*')?.Component?.name, 'NotFound')
  assert.equal(routeByPath('*')?.redirectTo, undefined)
})

test('Pitcher Detail has a first-class standalone route', () => {
  assert.equal(routeByPath('/pitcher/:id')?.Component?.name, 'PitcherPage')
})

test('scheduled Matchup has a first-class standalone route', () => {
  assert.equal(routeByPath('/matchup/:gameId')?.Component?.name, 'MatchupPage')
})

test('Team State History has a first-class standalone route', () => {
  assert.equal(routeByPath('/history/team/:abbr')?.Component?.name, 'TeamHistoryPage')
})

test('standalone Matchup renders game identity around the shared comparison', () => {
  const payload = {
    capability: 'scheduled_game_matchup_v1',
    status: 'available',
    game: {
      game_pk: 900001,
      reference_date: '2026-08-25',
      game_time_utc: '2026-08-25T23:10:00Z',
      status: { detailed: 'Scheduled', normalized: 'upcoming' },
      doubleheader_flag: 'Y',
      game_number: 2,
      away: { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' },
      home: { team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA' },
    },
    comparison: differingComparison.comparison,
  }
  const html = render(React.createElement(MatchupPageView, { payload }))

  assert.ok(htmlIncludes(html, '<h1'))
  assert.ok(htmlIncludes(html, 'Aces at Bears'))
  assert.ok(htmlIncludes(html, 'Game 2 · 7:10 PM ET · Scheduled'))
  assert.ok(htmlIncludes(html, 'Away · Aces'))
  assert.ok(htmlIncludes(html, 'Home · Bears'))
  assert.ok(htmlIncludes(html, 'Rested Options'))
  assert.ok(htmlIncludes(html, 'Open the Aces board'))
  assert.ok(htmlIncludes(html, 'Open the Bears board'))
})

test('standalone Matchup keeps game identity when comparison is unavailable', () => {
  const payload = {
    status: 'partial',
    game: {
      game_pk: 900001,
      reference_date: '2026-08-25',
      away: { team_name: 'Aces' },
      home: { team_name: 'Bears' },
    },
    comparison: null,
  }
  const html = render(React.createElement(MatchupPageView, { payload }))
  assert.ok(htmlIncludes(html, 'Aces at Bears'))
  assert.ok(htmlIncludes(html, 'Bullpen comparison unavailable'))
})

test('historical Matchup binds comparison, game, teams, and dates to the selected edition', () => {
  const revision = 3, generation = 'a'.repeat(64), gameId = 10101
  const edition = { scope: 'isolated_historical_core', current_serving_eligible: false, selection_revision: revision, generation }
  const away = { team_id: 111 }, home = { team_id: 110 }
  const game = { game_pk: gameId, away, home, reference_date: '2024-08-07' }
  const comparison = { ...edition, game, status: 'partial', publication_authority: null,
    represented_date: '2024-08-06', availability_reference_date: game.reference_date, teams: { team_a: away, team_b: home } }
  const response = { ...edition, status: 'represented', games: [game], historical_comparison: comparison,
    availability_reference: game.reference_date, data_through: comparison.represented_date }
  const read = value => historicalMatchupPayload(value, gameId, revision, generation)
  assert.deepEqual(read(response), { game, comparison })
  for (const overrides of [{ selection_revision: 2 }, { generation: 'f'.repeat(64) }, { current_serving_eligible: true },
    { games: [] }, { games: [{...game, game_pk: gameId + 1}] }, { data_through: '2024-08-05' }]) {
    assert.throws(() => read({ ...response, ...overrides }), /could not be verified/)
  }
  for (const overrides of [{ publication_authority: {} }, { generation: 'f'.repeat(64) }, { selection_revision: 1 },
    { teams: { team_a: home, team_b: away } }, { game: { ...game, reference_date: '2024-08-08' } }]) {
    assert.throws(() => read({ ...response, historical_comparison: { ...comparison, ...overrides } }), /could not be verified/)
  }
})

test('historical Board rejects a different club, edition, or represented date', async () => {
  const { verifyHistoricalBoard } = await server.ssrLoadModule('/src/components/bullpen/board/HistoricalTeamBoard.jsx')
  const team = 111, revision = 3, generation = 'a'.repeat(64), through = '2024-08-07'
  const scope = { scope: 'isolated_historical_core', status: 'represented', current_serving_eligible: false,
    selection_revision: revision, generation }
  const row = { team_id: team, team_name: 'Boston Red Sox', team_state: { data_through: through } }
  const changes = { ...scope, team, represented: through }
  const board = { ...scope, team: row, what_changed: changes, active_bullpen: [],
    competitive_workload: { data_through: through }, data_through: through, availability_reference: '2024-08-08' }
  const read = item => verifyHistoricalBoard(item, team, revision, generation)
  assert.equal(read(board), board)
  for (const overrides of [{ generation: 'f'.repeat(64) }, { selection_revision: 1 }, { current_serving_eligible: true },
    { team: { ...row, team_id: 110 } }, { data_through: '2024-08-06' }, { what_changed: { ...changes, team: 110 } },
    { what_changed: { ...changes, selection_revision: 2 } }]) {
    assert.throws(() => read({ ...board, ...overrides }), /could not be verified/)
  }
})

test('historical group performance scopes qualified values and preserves a withheld window sample', async () => {
  const { HistoricalGroupPerformance } = await server.ssrLoadModule('/src/components/bullpen/board/HistoricalTeamBoard.jsx')
  const team = 111, through = '2017-08-28'
  const performance = { team, through, windows: {
    recent_30: { sample: { through, value: '5 active pitchers · 36 relief appearances' },
      home_runs_allowed: { label: 'HR allowed', value: '0' } },
    season: { sample: { through, value: '5 active pitchers · 108 relief appearances' } },
  } }
  const show = context => render(React.createElement(HistoricalGroupPerformance, { team, through, performance: context }))
  const html = show(performance)
  assert.ok(html.includes('HR allowed') && html.includes('>0<') && html.includes('108 relief appearances'))
  assert.equal((html.match(/No qualified performance metrics/g) || []).length, 1)
  assert.ok(!show({ ...performance, team: 114 }).includes('HR allowed'))
  assert.ok(!show({ ...performance, through: '2017-08-27' }).includes('HR allowed'))
})

test('historical throwing hand retains the MLB profile observation date', async () => {
  const { default: HistoricalPitchHand } = await server.ssrLoadModule('/src/components/bullpen/HistoricalPitchHand.jsx')
  const hand = { basis: 'official_person_attribute_at_retrieval', value: 'L', reason: null,
    citation: { facts_digest: 'e'.repeat(64) }, observed_at: '2026-11-21T23:12:00-05:00' }
  const show = props => render(React.createElement(HistoricalPitchHand, { hand: props }))
  assert.match(show(hand), /MLB profile observed .*2026-11-22/)
  for (const invalid of [{ basis: 'projected' }, { value: null }, { reason: 'conflict' },
    { observed_at: null }, { observed_at: 'unknown' }, { observed_at: '2026-11-21' }, { citation: null }]) {
    assert.equal(show({ ...hand, ...invalid }), '')
  }
})

test('dated roster listing counts preserve a verified empty comparison and withhold missing evidence', async () => {
  const { HistoricalRosterListings } = await server.ssrLoadModule('/src/components/bullpen/board/HistoricalTeamBoard.jsx')
  const team = 111, through = '2017-08-28'
  const roster = { team, represented: through, active_listed: 3, forty_man_listed: 3, forty_man_listed_outside_active: [] }
  const show = value => render(React.createElement(HistoricalRosterListings, { roster: value, team, through }))
  const rows = [{ mlb_id: 10, name: 'Active Starter' }, { mlb_id: 11, name: null }, { mlb_id: 12, name: 'Active Reliever' }]
  const list = outside => render(React.createElement(HistoricalRosterListings, {
    roster: { ...roster, forty_man_listed_outside_active: [45], status_codes: { 45: ['D60', 'RM'] } }, team, through,
    statusLabels: { 45: { D60: 'Injured 60-Day' } },
    listings: { active: rows, forty_man_only: outside },
  }))
  const named = list([{ mlb_id: 45, name: 'Reserve Pitcher' }])
  for (const text of ['Active Starter', 'MLB player 11', 'Reserve Pitcher']) assert.ok(named.includes(text))
  assert.ok(named.includes('Injured 60-Day (D60) / RM'))
  assert.ok(!named.includes('/pitcher/'))
  for (const id of [10, 46]) assert.ok(!list([{ mlb_id: id, name: 'Wrong member' }]).includes('Wrong member'))
  assert.ok(show(roster).includes('Listed on the 40-man roster only</dt><dd>0</dd>'))
  for (const overrides of [{ team: 141 }, { represented: '2017-08-29' }, { forty_man_listed_outside_active: null }]) {
    const html = show({ ...roster, ...overrides })
    assert.ok(html.includes('Roster comparison unavailable') && !html.includes('<dd>'))
  }
})

test('historical rotation separates recorded starts, nonrotation games, and missing coverage', async () => {
  const { HistoricalRotation } = await server.ssrLoadModule('/src/components/bullpen/board/HistoricalTeamBoard.jsx')
  const team = 111, through = '2017-08-28'
  const pressure = { games_analyzed: 4, games_in_window: 7, short_start_count: 0, starter_outs: 72,
    bullpen_outs_required: 34, opener_bulk_games: 1, bullpen_games: 1, games_excluded: 1 }
  const rotation = { team, through, windows: { 7: { gaps: {}, pressure }, 14: { gaps: { '2017-08-18': 'missing_schedule' }, pressure } } }
  const show = value => render(React.createElement(HistoricalRotation, { rotation: value, team, through }))
  const html = show(rotation)
  assert.match(html, /4 rotation starts in 7 club games/)
  assert.match(html, /Short starts<\/dt><dd>0</)
  assert.ok(html.includes('Opener and bulk-follower games · 1') && html.includes('Bullpen games · 1'))
  assert.ok(html.includes('Games with incomplete pitching evidence · 1'))
  assert.equal((html.match(/Rotation evidence unavailable/g) || []).length, 1)
  const idle = show({ ...rotation, windows: { 7: { gaps: {}, pressure: { games_in_window: 0, games_analyzed: 0 } } } })
  assert.ok(idle.includes('0 rotation starts in 0 club games.'))
  assert.equal(idle.includes('Relief outs after rotation starts'), false)
  assert.equal((show({ ...rotation, team: 141 }).match(/Rotation evidence unavailable/g) || []).length, 2)
  assert.equal((show({ ...rotation, through: '2017-08-29' }).match(/Rotation evidence unavailable/g) || []).length, 2)
})

test('historical relief games preserve doubleheaders, incomplete measures and missing dates', async () => {
  const { HistoricalReliefGames } = await server.ssrLoadModule('/src/components/bullpen/board/HistoricalTeamBoard.jsx')
  const through = '2024-07-27'
  const line = { game_date: through, opponent_abbreviation: 'COL', home_away: 'home', relief_appearances: 2,
    innings: '1.2', pitches_total: 0, scope: 'official_regular_season' }
  const ledger = { status: 'verified_games_only', through, regular_gaps: { '2024-07-24': 'missing_final' },
    postseason_gaps: {}, games: [{ ...line, mlb_game_pk: 745307, game_number: 1 },
      { ...line, mlb_game_pk: 745310, game_number: 2, innings: null, pitches_total: null }] }
  const show = value => render(React.createElement(HistoricalReliefGames, { ledger: value, through }))
  const html = show(ledger)
  for (const fact of ['Game 1', 'Game 2', 'gameday/745307', 'gameday/745310', '1.2', '>0<', 'Some dates have incomplete evidence.']) {
    assert.ok(html.includes(fact), fact)
  }
  assert.equal((html.match(/Unavailable/g) || []).length, 2)
  assert.ok(show({ ...ledger, games: [] }).includes('No verified relief games in the retained window.'))
  assert.ok(show({ ...ledger, through: '2024-07-28' }).includes('Relief game evidence unavailable.'))
})

test('standalone Matchup owns one eager request with no Team Board fan-out', () => {
  const page = readFileSync(new URL('../src/components/bullpen/MatchupPage.jsx', import.meta.url), 'utf8')
  const api = readFileSync(new URL('../src/utils/api.js', import.meta.url), 'utf8')
  assert.equal((page.match(/getScheduledGameMatchup\(gameId, options\)/g) || []).length, 1)
  assert.ok(page.includes('<BullpenComparisonView'))
  assert.ok(api.includes('request(`/bullpen/matchups/${encodeURIComponent(gameId)}`,'))
  assert.equal(page.includes('overflow-x-auto'), false)
  assert.equal(page.includes('min-w-['), false)
  assert.equal(page.includes('<Navigate'), false)
  for (const forbidden of ['getTeams', 'getTeamBoardV2', 'getTonightIntelligence', 'getTeamBullpenComparison']) {
    assert.equal(page.includes(forbidden), false, forbidden)
  }
})

test('route-bound public reads pass cancellation through the shared request lifecycle', () => {
  const matchup = readFileSync(new URL('../src/components/bullpen/MatchupPage.jsx', import.meta.url), 'utf8')
  const pitcher = readFileSync(new URL('../src/components/bullpen/PitcherDetail.jsx', import.meta.url), 'utf8')
  const search = readFileSync(new URL('../src/components/search/SearchPage.jsx', import.meta.url), 'utf8')

  assert.ok(matchup.includes('getScheduledGameMatchup(gameId, options)'))
  assert.ok(pitcher.includes('getPitcherFatigue(pitcherId, options)'))
  assert.ok(search.includes("typeof AbortController === 'undefined'"))
  assert.ok(search.includes('controller?.abort()'))
  assert.ok(search.includes('signal: controller.signal'))
})

test('standalone Matchup keeps loading and game-not-found states local', () => {
  const loading = render(React.createElement(MatchupPageView, { loading: true }))
  const missing = render(React.createElement(MatchupPageView, { error: 'Scheduled game not found' }))
  assert.ok(htmlIncludes(loading, 'Loading scheduled game matchup'))
  assert.ok(htmlIncludes(missing, 'Scheduled game not found'))
})

test('legacy Pitcher query URLs canonicalize without loops or unsafe return targets', () => {
  assert.equal(
    legacyPitcherDestination('?view=board&team=BOS&pitcher=123&source=stories'),
    '/pitcher/123',
  )
  assert.equal(legacyPitcherDestination('?view=board&team=BOS'), null)
  assert.equal(legacyPitcherDestination('?view=pitchers&pitcher=123'), null)
  assert.equal(legacyPitcherDestination('?view=board&pitcher=bad&return=https://example.com'), null)
})

test('standalone Pitcher shell owns one request and never mounts Team Board dependencies', () => {
  const page = readFileSync(new URL('../src/components/bullpen/PitcherPage.jsx', import.meta.url), 'utf8')
  const detail = readFileSync(new URL('../src/components/bullpen/PitcherDetail.jsx', import.meta.url), 'utf8')
  const route = readFileSync(new URL('../src/components/bullpen/BullpenRoute.jsx', import.meta.url), 'utf8')

  assert.equal((detail.match(/getPitcherFatigue\(pitcherId, options\)/g) || []).length, 1)
  for (const forbidden of ['getTeams', 'getTeamBoardV2', 'TonightsBullpenBoard', 'getPitcherRecentWork']) {
    assert.equal(page.includes(forbidden), false, forbidden)
  }
  assert.ok(page.includes('Pitcher unavailable'))
  assert.ok(page.includes('pitcherId={pitcherId} revisionParam={revisionParam} repeated={repeated}'))
  assert.ok(route.includes('<Navigate to={destination} replace />'))
})

test('standalone Pitcher hierarchy keeps one dominant answer and responsive supporting context', () => {
  const detail = readFileSync(new URL('../src/components/bullpen/PitcherDetail.jsx', import.meta.url), 'utf8')
  const availability = readFileSync(new URL('../src/components/bullpen/AvailabilitySummary.jsx', import.meta.url), 'utf8')
  const recentWork = readFileSync(new URL('../src/components/bullpen/RecentWorkPanel.jsx', import.meta.url), 'utf8')
  const patterns = readFileSync(new URL('../src/components/bullpen/WorkloadPatterns.jsx', import.meta.url), 'utf8')
  const deployment = readFileSync(new URL('../src/components/bullpen/ObservedDeployment.jsx', import.meta.url), 'utf8')

  assert.ok(detail.includes('border border-amber/30 bg-field/70'))
  assert.ok(detail.includes('lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]'))
  assert.ok(detail.includes('lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0'))
  assert.ok(availability.includes('border-b border-dirt/70 pb-5'))
  assert.ok(recentWork.includes('border-y border-dirt/70 py-3'))
  assert.ok(patterns.includes('className="min-w-0 py-1"'))
  assert.ok(deployment.includes('className="min-w-0 py-1"'))

  const sectionMounts = [
    '<AvailabilitySummary',
    '<RecentWorkPanel',
    '<WorkloadPatterns',
    '<ObservedDeployment',
  ].map(token => detail.indexOf(token))
  assert.ok(sectionMounts.every(index => index >= 0))
  assert.deepEqual([...sectionMounts].sort((a, b) => a - b), sectionMounts)

  for (const source of [detail, availability, recentWork, patterns, deployment]) {
    assert.equal(source.includes('overflow-x-auto'), false)
    assert.equal(source.includes('h-screen'), false)
    assert.equal(source.includes('fixed inset'), false)
  }
})

test('app startup clears stale preferred team launch storage', () => {
  const source = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')

  assert.ok(source.includes('cleanupLaunchPreferredTeamStorage'))
})

test('public product routes stay on the single bullpen operating lane', () => {
  const directProductRoutes = APP_ROUTES
    .filter(route => route.Component && publicProductRoutes.includes(route.path))
    .map(route => route.path)

  assert.deepEqual(directProductRoutes, publicProductRoutes)
  assert.equal(routeByPath('/prospects'), undefined)
})

test('hidden technical, auth, and internal routes stay outside primary product navigation', () => {
  for (const path of ['/signin', '/auth/verify', '/posts-bpen-7f3d9c', '/admin/product-intelligence']) {
    assert.ok(routeByPath(path)?.Component, `missing technical route: ${path}`)
  }
})

test('sidebar preserves public route order and excludes Prospects', () => {
  const html = render(React.createElement(Sidebar))
  // Primary destinations use plain baseball labels; the old ambiguous
  // "Dashboard"/"Bullpen" and population-overstating "All Pitchers" are gone.
  const primaryLabels = ['Tonight', 'League Board', 'Team Bullpens', 'Compare Bullpens', 'Search', 'Stories']
  const supportingLabels = ['How to Read', 'Methodology', 'Data &amp; Trust', 'About']
  const routeIndexes = publicProductRoutes.map(route => html.indexOf(`href="${route}"`))

  assert.ok(htmlIncludes(html, 'href="/"'))
  assert.deepEqual([...routeIndexes].sort((a, b) => a - b), routeIndexes)
  for (const label of [...primaryLabels, ...supportingLabels]) {
    assert.ok(htmlIncludes(html, label), label)
  }
  for (const route of publicProductRoutes) {
    assert.ok(htmlIncludes(html, `href="${route}"`), route)
  }
  // Compare Bullpens and unified Search are direct destinations from the menu.
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=compare"'))
  assert.ok(htmlIncludes(html, 'href="/search"'))
  // Ambiguous or population-overstating labels no longer appear.
  assert.equal(htmlIncludes(html, '>Dashboard<'), false)
  assert.equal(htmlIncludes(html, 'All Pitchers'), false)
  assert.equal(htmlIncludes(html, 'href="/prospects"'), false)
  assert.equal(htmlIncludes(html, 'Prospects'), false)
  assert.equal(htmlIncludes(html, 'Following'), false)
  assert.equal(htmlIncludes(html, 'Account'), false)
  assert.equal(htmlIncludes(html, 'Sign in'), false)
  assert.equal(htmlIncludes(html, 'href="/signin"'), false)
})

test('sidebar omits the permanent Data Freshness card', () => {
  const html = render(React.createElement(Sidebar))
  assert.equal(htmlIncludes(html, 'Data Freshness'), false)
})

test('xl shell keeps the navigation rail fixed while content scrolls', () => {
  const sidebarSource = readFileSync(new URL('../src/components/Sidebar.jsx', import.meta.url), 'utf8')
  const appSource = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')

  assert.ok(sidebarSource.includes('xl:fixed'))
  assert.ok(sidebarSource.includes('xl:inset-y-0'))
  assert.ok(sidebarSource.includes('xl:overflow-y-auto'))
  assert.ok(appSource.includes('xl:ml-56'))
  assert.equal(sidebarSource.includes('lg:fixed'), false)
  assert.equal(appSource.includes('lg:ml-56'), false)
})

test('Vercel serves canonical team preview files before the invalid-team 404', () => {
  const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))
  const routes = config.routes || []
  const teamRoot = new URL('../public/team/', import.meta.url)
  const teams = readdirSync(teamRoot, { withFileTypes: true })
    .filter(entry => entry.isDirectory())
    .map(entry => entry.name)
    .sort()
  const canonicalTeamSource = '^/team/(ATH|ATL|AZ|BAL|BOS|CHC|CIN|CLE|COL|CWS|DET|HOU|KC|LAA|LAD|MIA|MIL|MIN|NYM|NYY|PHI|PIT|SD|SEA|SF|STL|TB|TEX|TOR|WSH)$'

  const shareSlash = routes.find(route => route.src === '^/share/([A-Za-z0-9._-]{1,64})/$')
  const canonicalTeam = routes.find(route => route.src === canonicalTeamSource)
  const filesystem = routes.find(route => route.handle === 'filesystem')
  const invalidTeam = routes.find(route => route.src === '^/team/(.*)$')
  const unknown = routes.at(-1)

  assert.deepEqual(shareSlash, {
    src: '^/share/([A-Za-z0-9._-]{1,64})/$',
    headers: { Location: '/share/$1' },
    status: 308,
  })
  assert.deepEqual(canonicalTeam, {
    src: canonicalTeamSource,
    dest: '/team/$1/index.html',
  })
  assert.deepEqual(filesystem, { handle: 'filesystem' })
  assert.deepEqual(invalidTeam, {
    src: '^/team/(.*)$',
    dest: '/404.html',
    status: 404,
  })
  assert.deepEqual(unknown, {
    src: '^/(.*)$',
    dest: '/404.html',
    status: 404,
  })
  assert.equal(routes.indexOf(canonicalTeam) < routes.indexOf(filesystem), true)
  assert.equal(routes.indexOf(filesystem) < routes.indexOf(invalidTeam), true)
  assert.equal(routes.indexOf(invalidTeam) < routes.indexOf(unknown), true)

  const canonicalTeamPattern = new RegExp(canonicalTeamSource)
  assert.equal(teams.length, 30)
  for (const team of teams) {
    assert.equal(canonicalTeamPattern.test(`/team/${team}`), true, `${team} is missing from the canonical team rewrite`)
  }
  assert.equal(canonicalTeamPattern.test('/team/INVALID'), false)
})

test('share preview routing resolves generated files before scoped and site-wide 404s', () => {
  const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))
  const routes = config.routes || []
  const slashRedirect = routes.find(route => route.src === '^/share/([A-Za-z0-9._-]{1,64})/$')
  const filesystem = routes.find(route => route.handle === 'filesystem')
  const invalidShare = routes.find(route => route.src === '^/share/([A-Za-z0-9._-]{1,64})$')
  const unknown = routes.at(-1)

  assert.deepEqual(filesystem, { handle: 'filesystem' })
  assert.deepEqual(invalidShare, {
    src: '^/share/([A-Za-z0-9._-]{1,64})$',
    dest: '/share-404.html',
    status: 404,
  })
  assert.deepEqual(slashRedirect, {
    src: '^/share/([A-Za-z0-9._-]{1,64})/$',
    headers: { Location: '/share/$1' },
    status: 308,
  })
  assert.equal(routes.indexOf(slashRedirect) < routes.indexOf(filesystem), true)
  assert.equal(routes.indexOf(filesystem) < routes.indexOf(invalidShare), true)
  assert.equal(routes.indexOf(invalidShare) < routes.indexOf(unknown), true)
  assert.equal(new RegExp(invalidShare.src).test('/share/abc123'), true)
  assert.equal(existsSync(new URL('../public/share-404.html', import.meta.url)), true)
})

test('invalid team share fallback and generic OG card are static public assets', () => {
  const fallbackUrl = new URL('../public/team/index.html', import.meta.url)
  const cardUrl = new URL('../public/og/baseballos-card.png', import.meta.url)

  assert.equal(existsSync(fallbackUrl), true)
  assert.equal(existsSync(cardUrl), true)

  const card = readFileSync(cardUrl)
  assert.deepEqual([...card.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10])
  assert.equal(card.readUInt32BE(16), 1200)
  assert.equal(card.readUInt32BE(20), 630)

  const fallback = readFileSync(fallbackUrl, 'utf8')
  assert.ok(fallback.includes('<meta property="og:title" content="BaseballOS | Team Story Preview" />'))
  assert.ok(fallback.includes('<meta property="og:url" content="https://baseballos.app/team/" />'))
  assert.ok(fallback.includes('<meta name="twitter:title" content="BaseballOS | Team Story Preview" />'))
  assert.ok(fallback.includes('<meta name="twitter:description" content="Open BaseballOS for current bullpen availability and trust reads." />'))
  assert.equal(metaContent(fallback, 'og:image'), 'https://baseballos.app/og/baseballos-card.png')
  assert.equal(metaContent(fallback, 'og:image:width'), '1200')
  assert.equal(metaContent(fallback, 'og:image:height'), '630')
  assert.equal(metaContent(fallback, 'og:image:type'), 'image/png')
  assert.equal(metaContent(fallback, 'twitter:card'), 'summary_large_image')
  assert.equal(metaContent(fallback, 'twitter:image'), 'https://baseballos.app/og/baseballos-card.png')
  assert.equal(fallback.includes('baseballos-card.svg'), false)
  assert.ok(fallback.includes('window.location.replace("/")'))
  assert.equal(fallback.includes('<div id="root"></div>'), false)
})

test('generated team share pages use absolute URLs and non-duplicated card text', () => {
  const teamRoot = new URL('../public/team/', import.meta.url)
  const teams = readdirSync(teamRoot, { withFileTypes: true })
    .filter(entry => entry.isDirectory())
    .map(entry => entry.name)
    .sort()

  assert.equal(teams.length, 30)

  for (const team of teams) {
    const html = readFileSync(new URL(`${team}/index.html`, teamRoot), 'utf8')
    const title = metaContent(html, 'og:title')
    const description = metaContent(html, 'og:description')
    const ogUrl = metaContent(html, 'og:url')

    assert.ok(title, `${team} is missing og:title`)
    assert.ok(description, `${team} is missing og:description`)
    assert.notEqual(title, description, `${team} title duplicates description`)
    assert.equal(metaContent(html, 'og:image'), 'https://baseballos.app/og/baseballos-card.png')
    assert.equal(metaContent(html, 'og:image:width'), '1200')
    assert.equal(metaContent(html, 'og:image:height'), '630')
    assert.equal(metaContent(html, 'og:image:type'), 'image/png')
    assert.equal(metaContent(html, 'twitter:card'), 'summary_large_image')
    assert.equal(metaContent(html, 'twitter:image'), 'https://baseballos.app/og/baseballos-card.png')
    assert.equal(html.includes('baseballos-card.svg'), false, team)
    for (const internalLabel of internalShareTitleLabels) {
      assert.equal(title.startsWith(`${internalLabel} —`), false, `${team} leaks ${internalLabel}`)
    }
    assert.equal(
      /^The .+ bullpen tonight - current availability and trust read$/.test(title),
      false,
      `${team} uses the old neutral share title`,
    )
    assert.equal(ogUrl, `https://baseballos.app/team/${team}`)
    assert.equal(metaContent(html, 'twitter:title'), title)
    assert.equal(metaContent(html, 'twitter:description'), description)
    assert.equal(html.includes('<div id="root"></div>'), false)
  }
})
