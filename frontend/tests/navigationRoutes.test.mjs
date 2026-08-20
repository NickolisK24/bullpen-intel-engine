import assert from 'node:assert/strict'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
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

const { APP_ROUTES } = await server.ssrLoadModule('/src/App.jsx')
const { default: Sidebar } = await server.ssrLoadModule('/src/components/Sidebar.jsx')

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
const publicProductRoutes = ['/', '/dashboard', '/bullpen', '/stories', '/methodology', '/trust']
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
  const primaryLabels = ['Today', 'League Board', 'Team Bullpens', 'Compare Bullpens', 'Reliever Finder', 'Stories']
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
  // Compare Bullpens and Reliever Finder are direct destinations from the menu.
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=compare"'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=pitchers"'))
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
