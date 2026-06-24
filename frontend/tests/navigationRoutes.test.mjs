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
  SidebarFollowingCard,
  default: Sidebar,
} = await server.ssrLoadModule('/src/components/Sidebar.jsx')

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

function routeByPath(path) {
  return APP_ROUTES.find(route => route.path === path)
}

test('/today redirects to the Today surface and catch-all routes home', () => {
  assert.equal(routeByPath('/')?.Component?.name, 'Home')
  assert.equal(routeByPath('/today')?.redirectTo, '/')
  assert.equal(routeByPath('*')?.redirectTo, '/')
})

test('existing primary routes remain registered, including direct Prospects URL access', () => {
  const paths = new Set(APP_ROUTES.map(route => route.path))
  for (const path of ['/', '/stories', '/dashboard', '/bullpen', '/prospects', '/methodology', '/trust']) {
    assert.ok(paths.has(path), `missing route: ${path}`)
  }
})

test('Pipeline is demoted from primary nav while Today remains the first destination', () => {
  const html = render(React.createElement(Sidebar))

  assert.ok(htmlIncludes(html, 'href="/"'))
  assert.ok(htmlIncludes(html, 'Today'))
  assert.ok(htmlIncludes(html, 'href="/stories"'))
  assert.ok(html.indexOf('Today') < html.indexOf('Stories'))
  assert.equal(htmlIncludes(html, 'href="/prospects"'), false)
  assert.equal(htmlIncludes(html, 'Pipeline'), false)
})

test('Sidebar Following card renders the resolved team name, not a generic placeholder', () => {
  const html = render(React.createElement(SidebarFollowingCard, {
    preferredTeam: {
      team_id: 118,
      team_name: 'Kansas City Royals',
      team_abbreviation: 'KC',
    },
  }))

  assert.ok(htmlIncludes(html, 'Following'))
  assert.ok(htmlIncludes(html, 'Kansas City Royals'))
  assert.equal(htmlIncludes(html, 'your team'), false)
  assert.equal(htmlIncludes(html, '>118<'), false)
})

test('Sidebar Following card falls back to a safe abbreviation label', () => {
  const html = render(React.createElement(SidebarFollowingCard, {
    preferredTeam: {
      team_id: 118,
      team_abbreviation: 'KC',
    },
  }))

  assert.ok(htmlIncludes(html, 'KC'))
  assert.equal(htmlIncludes(html, 'your team'), false)
  assert.equal(htmlIncludes(html, '>118<'), false)
})

test('desktop shell keeps the navigation rail fixed while content scrolls', () => {
  const sidebarSource = readFileSync(new URL('../src/components/Sidebar.jsx', import.meta.url), 'utf8')
  const appSource = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')

  assert.ok(sidebarSource.includes('lg:fixed'))
  assert.ok(sidebarSource.includes('lg:inset-y-0'))
  assert.ok(sidebarSource.includes('lg:overflow-y-auto'))
  assert.ok(appSource.includes('lg:ml-56'))
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
  assert.ok(fallback.includes('<meta property="og:url" content="https://baseballos.vercel.app/team" />'))
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
    assert.equal(ogUrl, `https://baseballos.vercel.app/team/${team}`)
    assert.equal(metaContent(html, 'twitter:title'), title)
    assert.equal(metaContent(html, 'twitter:description'), description)
    assert.equal(html.includes('<div id="root"></div>'), false)
  }
})
