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
const { MatchupPageView } = await server.ssrLoadModule('/src/components/bullpen/MatchupPage.jsx')

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
const safeHeroDescription = 'BaseballOS reads public MLB usage and workload after every game, so you can tell which pens are gassed and which are loaded — with the data date and confidence always shown.'
const blockedEvidenceCopyPatterns = [
  /see the evidence behind/i,
  /evidence behind (?:each|every) read/i,
]

function routeByPath(path) {
  return APP_ROUTES.find(route => route.path === path)
}

test('root HTML uses the public BaseballOS domain for canonical and social metadata', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8')

  assert.ok(htmlIncludes(html, '<title>BaseballOS | MLB Bullpen Intelligence</title>'))
  assert.ok(htmlIncludes(html, safeHeroDescription))
  assert.ok(htmlIncludes(html, '<link rel="canonical" href="https://baseballos.app/" />'))
  assert.ok(htmlIncludes(html, '<meta property="og:url" content="https://baseballos.app/" />'))
  assert.ok(htmlIncludes(html, '<meta property="og:image" content="https://baseballos.app/og/baseballos-card.svg" />'))
  assert.ok(htmlIncludes(html, '<meta name="twitter:image" content="https://baseballos.app/og/baseballos-card.svg" />'))
  assert.equal(htmlIncludes(html, 'baseballos.vercel.app'), false)
})

test('public homepage and README copy do not imply evidence surfacing', () => {
  const publicCopy = [
    readFileSync(new URL('../index.html', import.meta.url), 'utf8'),
    readFileSync(new URL('../src/components/home/IntelligenceSurface.jsx', import.meta.url), 'utf8'),
    readFileSync(new URL('../../README.md', import.meta.url), 'utf8'),
  ].join('\n')

  for (const pattern of blockedEvidenceCopyPatterns) {
    assert.equal(pattern.test(publicCopy), false, String(pattern))
  }
})

test('/today redirects to the Today surface and catch-all routes home', () => {
  assert.equal(routeByPath('/')?.Component?.name, 'Home')
  assert.equal(routeByPath('/today')?.redirectTo, '/')
  assert.equal(routeByPath('*')?.redirectTo, '/')
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

test('standalone Matchup owns one eager request with no Team Board fan-out', () => {
  const page = readFileSync(new URL('../src/components/bullpen/MatchupPage.jsx', import.meta.url), 'utf8')
  const api = readFileSync(new URL('../src/utils/api.js', import.meta.url), 'utf8')
  assert.equal((page.match(/getScheduledGameMatchup\(gameId\)/g) || []).length, 1)
  assert.ok(page.includes('<BullpenComparisonView'))
  assert.ok(api.includes('request(`/bullpen/matchups/${encodeURIComponent(gameId)}`)'))
  assert.equal(page.includes('overflow-x-auto'), false)
  assert.equal(page.includes('min-w-['), false)
  assert.equal(page.includes('<Navigate'), false)
  for (const forbidden of ['getTeams', 'getTeamBoardV2', 'getTonightIntelligence', 'getTeamBullpenComparison']) {
    assert.equal(page.includes(forbidden), false, forbidden)
  }
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

  assert.equal((detail.match(/getPitcherFatigue\(pitcherId\)/g) || []).length, 1)
  for (const forbidden of ['getTeams', 'getTeamBoardV2', 'TonightsBullpenBoard', 'getPitcherRecentWork']) {
    assert.equal(page.includes(forbidden), false, forbidden)
  }
  assert.ok(page.includes('Pitcher unavailable'))
  assert.ok(page.includes('<PitcherDetail pitcherId={pitcherId} />'))
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
  const primaryLabels = ['Today', 'League Board', 'Team Bullpens', 'Compare Bullpens', 'Search', 'Stories']
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

test('Vercel serves canonical team preview files before the invalid-team and SPA fallbacks', () => {
  const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))
  const rewrites = config.rewrites || []
  const teamRoot = new URL('../public/team/', import.meta.url)
  const teams = readdirSync(teamRoot, { withFileTypes: true })
    .filter(entry => entry.isDirectory())
    .map(entry => entry.name)
    .sort()
  const canonicalTeamSource = '^/team/(ATH|ATL|AZ|BAL|BOS|CHC|CIN|CLE|COL|CWS|DET|HOU|KC|LAA|LAD|MIA|MIL|MIN|NYM|NYY|PHI|PIT|SD|SEA|SF|STL|TB|TEX|TOR|WSH)$'

  assert.deepEqual(rewrites[0], {
    source: canonicalTeamSource,
    destination: '/team/$1/index.html',
  })
  assert.deepEqual(rewrites[1], {
    source: '/team/(.*)',
    destination: '/team/index.html',
  })
  assert.deepEqual(rewrites[2], {
    source: '/(.*)',
    destination: '/index.html',
  })

  const canonicalTeamPattern = new RegExp(canonicalTeamSource)
  assert.equal(teams.length, 30)
  for (const team of teams) {
    assert.equal(canonicalTeamPattern.test(`/team/${team}`), true, `${team} is missing from the canonical team rewrite`)
  }
  assert.equal(canonicalTeamPattern.test('/team/INVALID'), false)
})

test('invalid team share fallback and generic OG card are static public assets', () => {
  const fallbackUrl = new URL('../public/team/index.html', import.meta.url)
  const cardUrl = new URL('../public/og/baseballos-card.svg', import.meta.url)

  assert.equal(existsSync(fallbackUrl), true)
  assert.equal(existsSync(cardUrl), true)

  const fallback = readFileSync(fallbackUrl, 'utf8')
  assert.ok(fallback.includes('<meta property="og:title" content="BaseballOS | Team Story Preview" />'))
  assert.ok(fallback.includes('<meta property="og:url" content="https://baseballos.app/team/" />'))
  assert.ok(fallback.includes('<meta name="twitter:title" content="BaseballOS | Team Story Preview" />'))
  assert.ok(fallback.includes('<meta name="twitter:description" content="Open BaseballOS for current bullpen availability and trust reads." />'))
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
