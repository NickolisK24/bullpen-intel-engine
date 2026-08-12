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
const {
  SidebarDataFreshnessCard,
  sidebarFreshness,
  default: Sidebar,
} = await server.ssrLoadModule('/src/components/Sidebar.jsx')
const {
  MASTHEAD_NAV,
  PRIMARY_NAV,
  SUPPORTING_NAV,
} = await server.ssrLoadModule('/src/utils/navigation.js')

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
const safeHeroDescription = 'BaseballOS reads public MLB usage, rest, and roster context after every completed game, then explains how each bullpen is set up tonight — with the date and the evidence each read rests on.'
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
  // Primary destinations use the canonical public lane names from
  // docs/canonical/03_PRODUCT_EXPERIENCE_STANDARD.md section 5. The
  // population-overstating "All Pitchers" stays gone.
  const primaryLabels = ['Today', 'Dashboard', 'Bullpens', 'Compare Bullpens', 'Reliever Finder', 'Stories']
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
  // Population-overstating labels no longer appear. ("Dashboard" is canonical
  // public naming and is asserted present above.)
  assert.equal(htmlIncludes(html, 'All Pitchers'), false)
  assert.equal(htmlIncludes(html, 'href="/prospects"'), false)
  assert.equal(htmlIncludes(html, 'Prospects'), false)
  assert.equal(htmlIncludes(html, 'Following'), false)
  assert.equal(htmlIncludes(html, 'Account'), false)
  assert.equal(htmlIncludes(html, 'Sign in'), false)
  assert.equal(htmlIncludes(html, 'href="/signin"'), false)
})

test('Sidebar Data Freshness renders sync status timestamps in ET', () => {
  const freshness = sidebarFreshness({
    status: 'success',
    last_checked: '2026-06-24T10:00:00Z',
    last_sync: '2026-06-24T10:02:00Z',
    last_successful_sync: '2026-06-24T10:02:00Z',
    data_through: '2026-06-23',
    data: { game_logs: 1, latest_game_date: '2026-06-23' },
    freshness: {
      is_current: true,
      freshness_state: 'current',
      limitations: [],
      reason_codes: [],
    },
  }, false, null)

  const html = render(React.createElement(SidebarDataFreshnessCard, { freshness }))

  assert.ok(htmlIncludes(html, 'Data Freshness'))
  assert.ok(htmlIncludes(html, 'Page checked'))
  assert.ok(htmlIncludes(html, '6:00 AM ET'))
  assert.ok(htmlIncludes(html, 'Latest data update'))
  assert.ok(htmlIncludes(html, '6:02 AM ET'))
  assert.ok(htmlIncludes(html, 'Bullpen data through'))
  assert.equal(htmlIncludes(html, '>Data through<'), false)
  assert.ok(htmlIncludes(html, 'June 23, 2026'))
  assert.equal(htmlIncludes(html, 'Last Sync'), false)
  assert.equal(htmlIncludes(html, '10:02 AM ET'), false)
})

test('Sidebar Data Freshness keeps date-only data through values timezone-safe', () => {
  const freshness = sidebarFreshness({
    status: 'success',
    last_checked: '2026-06-01T00:30:00Z',
    last_sync: '2026-06-01T00:30:00Z',
    last_successful_sync: '2026-06-01T00:30:00Z',
    data_through: '2026-06-01',
    data: { game_logs: 1, latest_game_date: '2026-06-01' },
    freshness: {
      is_current: true,
      freshness_state: 'current',
      limitations: [],
      reason_codes: [],
    },
  }, false, null)

  assert.equal(freshness.lastChecked, '8:30 PM ET')
  assert.equal(freshness.lastDataUpdate, '8:30 PM ET')
  assert.equal(freshness.dataThrough, 'June 1, 2026')
  assert.notEqual(freshness.dataThrough, 'May 31, 2026')
})

test('Sidebar Data Freshness uses published freshness when sync checked an incomplete newer date', () => {
  const freshness = sidebarFreshness({
    status: 'success',
    last_checked: '2026-07-06T00:27:00Z',
    last_sync: '2026-07-06T00:27:00Z',
    last_successful_sync: '2026-07-06T00:27:00Z',
    data_through: '2026-07-05',
    data: { game_logs: 1, latest_game_date: '2026-07-05' },
    freshness: {
      is_current: false,
      freshness_state: 'limited',
      label: 'Baseball data through 2026-07-05 is incomplete and is not publishable as current.',
      limitations: ['Missing completed-game coverage for the checked date.'],
      reason_codes: ['slate_log_coverage_incomplete'],
    },
  }, false, null, {
    data_through: '2026-07-03',
    latest_workload_date: '2026-07-03',
    last_successful_sync: '2026-07-04T10:42:00Z',
    sync_status: 'success',
    is_current: true,
    is_stale: false,
    freshness_state: 'current',
    label: 'Current baseball data through 2026-07-03.',
    limitations: [],
  })

  assert.equal(freshness.dataThrough, 'July 3, 2026')
  assert.notEqual(freshness.dataThrough, 'July 5, 2026')
})

// The public shell is a horizontal masthead, not a left rail. The rail's fixed
// geometry and the matching content offset are both gone; nothing may
// reintroduce a viewport-anchored side column or a hard-coded content inset,
// because either one silently pushes the reading column off centre.
test('desktop shell is a horizontal masthead with no side rail or content offset', () => {
  const sidebarSource = readFileSync(new URL('../src/components/Sidebar.jsx', import.meta.url), 'utf8')
  const appSource = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')

  // The shell renders a masthead landmark using the shared page frame.
  assert.ok(sidebarSource.includes('bos-masthead'))
  assert.ok(sidebarSource.includes('<header'))
  assert.ok(sidebarSource.includes('bos-page'))

  // No fixed side rail survives, and the content is not inset for one.
  for (const railGeometry of ['lg:fixed', 'lg:inset-y-0', 'lg:w-56', 'lg:h-screen']) {
    assert.equal(sidebarSource.includes(railGeometry), false, railGeometry)
  }
  assert.equal(/lg:ml-\d/.test(appSource), false, 'no left content offset remains')
  assert.equal(/lg:flex-row/.test(appSource), false, 'the shell stacks rather than sitting beside a rail')

  // The masthead is not sticky: Today is a finite edition read top to bottom.
  assert.equal(/(sticky|fixed)/.test(sidebarSource), false)
})

test('the desktop masthead carries the six primary public destinations', () => {
  const html = render(React.createElement(Sidebar))
  const nav = html.slice(html.indexOf('aria-label="Primary"'), html.indexOf('aria-label="All destinations"'))

  assert.deepEqual(
    MASTHEAD_NAV.map(item => item.label),
    ['Today', 'Dashboard', 'Bullpens', 'Stories', 'Methodology', 'Data & Trust'],
  )
  const escapeHtml = value => value.replace(/&/g, '&amp;')
  for (const item of MASTHEAD_NAV) {
    assert.ok(htmlIncludes(nav, `>${escapeHtml(item.label)}<`), item.label)
  }
  // Secondary utilities are deliberately absent from the masthead...
  for (const label of ['Compare Bullpens', 'Reliever Finder', 'How to Read', 'About']) {
    assert.equal(htmlIncludes(nav, `>${escapeHtml(label)}<`), false, label)
  }
  // ...but every route stays reachable from the menu sheet.
  for (const item of [...PRIMARY_NAV, ...SUPPORTING_NAV]) {
    assert.ok(htmlIncludes(html, `href="${item.to.replace(/&/g, '&amp;')}"`), item.to)
  }
})

test('Vercel keeps shareable team URLs out of the SPA catch-all', () => {
  const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))
  const rewrites = config.rewrites || []

  assert.deepEqual(rewrites[0], {
    source: '/team/(.*)',
    destination: '/team/index.html',
  })
  assert.deepEqual(rewrites[1], {
    source: '/(.*)',
    destination: '/index.html',
  })
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
