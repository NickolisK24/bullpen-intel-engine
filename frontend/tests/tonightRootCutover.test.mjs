import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes, Navigate } from 'react-router-dom'
import { createServer } from 'vite'
import { renderRouteEntryHtml } from '../scripts/generate-route-entry-pages.mjs'
import { productionPayload } from './fixtures/tonightV1Fixtures.mjs'

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
const { TonightPageView } = await server.ssrLoadModule('/src/components/tonight/TonightPage.jsx')
const { PRIMARY_NAV, SUPPORTING_NAV, isNavDestinationActive } = await server.ssrLoadModule('/src/utils/navigation.js')
const metadata = await server.ssrLoadModule('/src/utils/publicRouteMetadata.js')
const { canonicalPage } = await server.ssrLoadModule('/src/utils/trafficMeasurement.js')

const route = (path) => APP_ROUTES.find(item => item.path === path)
const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')
const vercel = JSON.parse(read('../vercel.json'))
const LEGACY_HOME_MARKERS = [
  'id="daily-edition"', 'id="since-yesterday"', 'id="bullpen-picture"',
  'id="explore-baseballos"', 'id="audience-signup"', 'Since Yesterday', 'Daily Edition',
  'Explore BaseballOS',
]

// Renders the route table the way AppRoutes does, with a view stand-in for the
// data-bound page so SSR shows the loaded Tonight content for a given path.
function renderPath(path, payload = productionPayload()) {
  const element = (entry) => {
    if (entry.redirectTo) return React.createElement(Navigate, { to: entry.redirectTo, replace: true })
    if (entry.Component === route('/').Component) return React.createElement(TonightPageView, { payload })
    return React.createElement('div', { 'data-route': entry.path })
  }
  return renderToStaticMarkup(React.createElement(
    MemoryRouter, { initialEntries: [path] },
    React.createElement(Routes, null, APP_ROUTES.map(entry => React.createElement(Route, {
      key: entry.path, path: entry.path, element: element(entry),
    }))),
  ))
}

// ── Routing ─────────────────────────────────────────────────────────────────

test('/ and /tonight render one shared TonightPage component', () => {
  assert.equal(route('/')?.Component?.name, 'TonightPage')
  assert.equal(route('/tonight')?.Component, route('/')?.Component)
  assert.equal(APP_ROUTES.filter(item => item.Component?.name === 'TonightPage').length, 2)
})

test('/today redirects to the canonical root in the client and on the host, without a loop', () => {
  assert.equal(route('/today')?.redirectTo, '/')
  assert.equal(route('/')?.redirectTo, undefined)
  const today = vercel.routes.find(item => item.src === '^/today/?$')
  assert.equal(today?.status, 308)
  assert.equal(today?.headers?.Location, '/')
  assert.equal(vercel.routes.some(item => item.src === '^/$' || item.headers?.Location === '/today'), false)
})

test('Home is unrouted and dormant; App no longer imports it', () => {
  const app = read('../src/App.jsx')
  assert.doesNotMatch(app, /components\/home\/Home/)
  assert.equal(APP_ROUTES.some(item => item.Component?.name === 'Home'), false)
  assert.equal(existsSync(new URL('../src/components/home/Home.jsx', import.meta.url)), true, 'kept for TN-11')
})

test('Matchup, Pitcher, Team Board and History routes are unchanged', () => {
  assert.equal(route('/matchup/:gameId')?.Component?.name, 'MatchupPage')
  assert.equal(route('/pitcher/:id')?.Component?.name, 'PitcherPage')
  assert.equal(route('/bullpen')?.Component?.name, 'BullpenRoute')
  assert.equal(route('/history/team/:abbr')?.Component?.name, 'TeamHistoryPage')
})

// ── Root content: Tonight, never a hybrid ──────────────────────────────────

test('/ renders the full Tonight page and no legacy Home content', () => {
  const html = renderPath('/')
  assert.match(html, /<h1[^>]*>Tonight in MLB Bullpens<\/h1>/)
  for (const id of ['tonight-lead', 'tonight-featured', 'tonight-slate', 'tonight-changes', 'tonight-go-deeper']) {
    assert.ok(html.includes(`data-testid="${id}"`), id)
  }
  for (const marker of LEGACY_HOME_MARKERS) {
    assert.equal(html.includes(marker), false, marker)
  }
})

test('/ and /tonight render equivalent Tonight content from the same payload', () => {
  const pick = (html) => ({
    lead: (html.match(/data-testid="tonight-lead"[\s\S]*?<\/section>/) || [''])[0],
    featured: [...(html.match(/data-testid="tonight-featured"[\s\S]*?<\/section>/) || [''])[0].matchAll(/data-game-pk="(\d+)"/g)].map(m => m[1]),
    slate: [...html.slice(html.indexOf('data-testid="tonight-slate"'), html.indexOf('data-testid="tonight-changes"')).matchAll(/data-game-pk="(\d+)"/g)].map(m => m[1]),
    changes: [...html.matchAll(/data-testid="tonight-change"/g)].length,
    links: [...html.matchAll(/data-link="[a-z-]+" href="([^"]+)"/g)].map(m => m[1]),
  })
  const root = pick(renderPath('/'))
  const tonight = pick(renderPath('/tonight'))
  assert.deepEqual(root, tonight)
  // 15 games; the one final game sits behind the collapsed Completed Games.
  assert.equal(root.slate.length, 14)
  assert.ok(root.lead.length > 0)
})

test('root states carry over: unavailable, error and quiet day', () => {
  const unavailable = renderToStaticMarkup(React.createElement(MemoryRouter, null,
    React.createElement(TonightPageView, { payload: { contract: 'tonight_v1', status: 'unavailable', edition: null } })))
  assert.match(unavailable, /Tonight&#x27;s trusted bullpen edition isn&#x27;t available yet\./)
  const error = renderToStaticMarkup(React.createElement(MemoryRouter, null,
    React.createElement(TonightPageView, { payload: null, error: 'x', onRetry: () => {} })))
  assert.match(error, /role="alert"/)
  const legacy = renderToStaticMarkup(React.createElement(MemoryRouter, null,
    React.createElement(TonightPageView, { payload: { contract: 'tonight_v5', games: productionPayload().games } })))
  assert.doesNotMatch(legacy, /data-testid="tonight-game-card"/, 'a v5 body never renders at /')
})

// ── Navigation ──────────────────────────────────────────────────────────────

test('primary nav leads with Tonight at / and has no duplicate daily destination', () => {
  assert.equal(PRIMARY_NAV[0].label, 'Tonight')
  assert.equal(PRIMARY_NAV[0].to, '/')
  const daily = PRIMARY_NAV.filter(item => ['/', '/tonight', '/today'].includes(item.to))
  assert.equal(daily.length, 1)
  assert.equal([...PRIMARY_NAV, ...SUPPORTING_NAV].some(item => /^(Home|Today)$/.test(item.label)), false)
  assert.equal(PRIMARY_NAV.find(item => item.key === 'team-bullpens')?.to, '/bullpen')
  assert.equal(PRIMARY_NAV.find(item => item.key === 'league-board')?.to, '/dashboard')
})

test('Tonight is active (aria-current) on / and /tonight only', () => {
  const tonight = PRIMARY_NAV[0]
  for (const [pathname, active] of [['/', true], ['/tonight', true], ['/today', false], ['/dashboard', false], ['/bullpen', false], ['/matchup/1', false]]) {
    assert.equal(isNavDestinationActive(tonight, { pathname, search: '' }), active, pathname)
  }
  for (const path of ['/', '/tonight']) {
    const html = renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: [path] }, React.createElement(Sidebar)))
    const current = [...html.matchAll(/<a [^>]*aria-current="page"[^>]*>[\s\S]*?<\/a>/g)].map(m => m[0])
    assert.equal(current.length, 1, path)
    assert.match(current[0], />Tonight</)
  }
})

test('brand links to / with an accessible name and is not a nav destination', () => {
  const html = renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: ['/dashboard'] }, React.createElement(Sidebar)))
  const brand = html.match(/<a [^>]*data-testid="brand-home-link"[^>]*>/)?.[0] || ''
  assert.match(brand, /href="\/"/)
  assert.match(brand, /aria-label="BaseballOS home"/)
  assert.doesNotMatch(brand, /aria-current/)
})

// ── Metadata, canonical, sitemap, hosting ──────────────────────────────────

test('root and /tonight share one title and description, canonical to /', () => {
  const root = metadata.metadataForLocation('/')
  const tonight = metadata.metadataForLocation('/tonight')
  assert.equal(root.title, 'BaseballOS | Tonight in MLB Bullpens')
  assert.equal(tonight.title, root.title)
  assert.equal(tonight.description, root.description)
  assert.equal(root.canonicalUrl, 'https://baseballos.app/')
  assert.equal(tonight.canonicalUrl, 'https://baseballos.app/')
  assert.doesNotMatch(root.description, /predict|edge|rank|bet|fantasy|gassed|\b\d+\b|Fresh|Stretched|Vulnerable/i)
})

test('index.html and the /tonight route entry carry the new root identity', () => {
  const index = read('../index.html')
  assert.match(index, /<title>BaseballOS \| Tonight in MLB Bullpens<\/title>/)
  assert.match(index, /<link rel="canonical" href="https:\/\/baseballos\.app\/" \/>/)
  assert.ok(index.includes(metadata.ROOT_DESCRIPTION))
  assert.doesNotMatch(index, /MLB Bullpen Intelligence<\/title>|gassed/)
  const entry = metadata.ROUTE_ENTRY_METADATA.find(item => item.key === 'tonight')
  const html = renderRouteEntryHtml(entry)
  assert.match(html, /rel="canonical" href="https:\/\/baseballos\.app\/"/)
  assert.match(html, /property="og:url" content="https:\/\/baseballos\.app\/"/)
})

test('sitemap lists / once and never /tonight or /today', () => {
  const sitemap = read('../public/sitemap.xml')
  const locations = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => m[1])
  assert.equal(locations.filter(loc => loc === 'https://baseballos.app/').length, 1)
  assert.equal(locations.some(loc => /\/(tonight|today)$/.test(loc)), false)
})

test('host routing: /tonight direct entry and trailing-slash redirect remain', () => {
  assert.ok(vercel.routes.some(item => item.src === '^/tonight$' && item.dest === '/route-entry/tonight.html'))
  assert.ok(vercel.routes.some(item => item.status === 308 && item.src?.includes('|tonight|') && item.headers?.Location === '/$1'))
  assert.equal(vercel.routes.some(item => item.dest === '/index.html'), false, 'root still served by the filesystem index')
})

test('pageviews: / keeps its existing surface; /tonight adds no second pageview mapping', () => {
  assert.deepEqual(canonicalPage('/'), { route: '/', surface: 'today' })
  assert.equal(canonicalPage('/tonight'), null)
})

test('source-of-truth: the cutover adds no data path to Tonight', () => {
  const page = read('../src/components/tonight/TonightPage.jsx')
  assert.equal((page.match(/getTonightV1\(/g) || []).length, 1)
  const app = read('../src/App.jsx')
  assert.doesNotMatch(app, /getTonight|tonight_v5|getTodayIntelligence/)
})
