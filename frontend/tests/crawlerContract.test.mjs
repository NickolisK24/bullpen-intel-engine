import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'
import { createServer } from 'vite'
import {
  PUBLIC_ORIGIN,
  PUBLIC_TEAM_ABBREVIATIONS,
  ROUTE_ENTRY_METADATA,
  canonicalBullpenPath,
  metadataForLocation,
} from '../src/utils/publicRouteMetadata.js'
import { renderRouteEntryHtml } from '../scripts/generate-route-entry-pages.mjs'

const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))

test('unknown public paths fail closed instead of falling through to the SPA', () => {
  const routes = config.routes || []
  const unknown = routes.at(-1)

  assert.deepEqual(unknown, {
    src: '^/(.*)$',
    dest: '/404.html',
    status: 404,
  })

  const notFound = readFileSync(new URL('../public/404.html', import.meta.url), 'utf8')
  assert.match(notFound, /Page not found/i)
  assert.match(notFound, /noindex,nofollow/i)
  assert.doesNotMatch(notFound, /rel="canonical"|property="og:url"/i)
})

test('crawler-critical resources are real static assets', () => {
  for (const path of [
    '../public/sitemap.xml',
    '../public/robots.txt',
    '../public/favicon.svg',
    '../public/manifest.webmanifest',
  ]) {
    assert.equal(existsSync(new URL(path, import.meta.url)), true, path)
  }

  const sitemap = readFileSync(new URL('../public/sitemap.xml', import.meta.url), 'utf8')
  assert.match(sitemap, /^<\?xml version="1\.0" encoding="UTF-8"\?>/)
  assert.match(sitemap, /<urlset xmlns="http:\/\/www\.sitemaps\.org\/schemas\/sitemap\/0\.9">/)
  const locations = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(match => match[1])
  const stablePaths = [
    '/', '/dashboard', '/bullpen', '/search', '/stories', '/how-to-read',
    '/methodology', '/trust', '/about',
  ]
  assert.equal(locations.length, stablePaths.length + PUBLIC_TEAM_ABBREVIATIONS.length)
  assert.deepEqual(
    locations.slice(0, stablePaths.length),
    stablePaths.map(path => `${PUBLIC_ORIGIN}${path}`),
  )
  assert.deepEqual(
    locations.slice(stablePaths.length),
    PUBLIC_TEAM_ABBREVIATIONS.map(abbr => `${PUBLIC_ORIGIN}/team/${abbr}`),
  )
  assert.doesNotMatch(sitemap, /\/admin\/|\/internal\/|\/auth\/verify|\/share\//)
  assert.doesNotMatch(sitemap, /<lastmod>/)

  const robots = readFileSync(new URL('../public/robots.txt', import.meta.url), 'utf8')
  assert.match(robots, /Sitemap: https:\/\/baseballos\.app\/sitemap\.xml/)
  for (const path of ['/admin/', '/internal/', '/posts-bpen-7f3d9c', '/auth/', '/signin']) {
    assert.match(robots, new RegExp(`Disallow: ${path.replace('/', '\\/')}`))
  }

  const manifest = JSON.parse(
    readFileSync(new URL('../public/manifest.webmanifest', import.meta.url), 'utf8'),
  )
  assert.equal(manifest.name, 'BaseballOS')
  assert.equal(manifest.display, 'browser')
  assert.equal(manifest.start_url, '/')

  const favicon = readFileSync(new URL('../public/favicon.svg', import.meta.url), 'utf8')
  assert.match(favicon, /^<svg\b/)
  assert.doesNotMatch(favicon, /<!doctype html>/i)
})

test('crawler-critical paths have explicit MIME contracts and never use the SPA shell', () => {
  const headerBySource = new Map((config.headers || []).map(entry => [entry.source, entry.headers]))
  const expected = new Map([
    ['/sitemap.xml', 'application/xml; charset=utf-8'],
    ['/robots.txt', 'text/plain; charset=utf-8'],
    ['/favicon.ico', 'image/svg+xml'],
    ['/favicon.svg', 'image/svg+xml'],
    ['/manifest.webmanifest', 'application/manifest+json; charset=utf-8'],
  ])
  for (const [path, contentType] of expected) {
    const headers = headerBySource.get(path)
    assert.equal(headers?.find(header => header.key === 'Content-Type')?.value, contentType)
  }
  assert.deepEqual(
    config.routes.find(route => route.src === '^/favicon.ico$'),
    { src: '^/favicon.ico$', dest: '/favicon.svg' },
  )
  assert.equal((config.routes || []).some(route => route.dest === '/index.html'), false)
})

test('important static route entries identify themselves without mutable baseball claims', () => {
  const byKey = new Map(ROUTE_ENTRY_METADATA.map(entry => [entry.key, entry]))
  for (const key of ['dashboard', 'search', 'stories', 'how-to-read', 'methodology', 'trust', 'about']) {
    const entry = byKey.get(key)
    const html = renderRouteEntryHtml(entry)
    assert.ok(html.includes(`<title>${entry.title.replaceAll('&', '&amp;')}</title>`))
    assert.match(html, new RegExp(`rel="canonical" href="${PUBLIC_ORIGIN}${entry.canonical}"`))
    assert.match(html, new RegExp(`property="og:url" content="${PUBLIC_ORIGIN}${entry.canonical}"`))
  }

  const bullpen = renderRouteEntryHtml(byKey.get('bullpen'))
  assert.doesNotMatch(bullpen, /rel="canonical"|property="og:url"/)
  assert.doesNotMatch(bullpen, /Fresh|Stretched|Vulnerable|Clean Option|Unavailable/)
})

test('Vite owns route-entry generation when hosting bypasses package scripts', () => {
  const viteConfig = readFileSync(new URL('../vite.config.js', import.meta.url), 'utf8')
  const packageConfig = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))

  assert.match(viteConfig, /import \{ writeRouteEntryPages \}/)
  assert.match(viteConfig, /command === 'build'/)
  assert.match(viteConfig, /if \(command === 'build'\) \{\s*await writeRouteEntryPages\(\)/)
  assert.equal(packageConfig.scripts.build, 'vite build')
  assert.equal(packageConfig.scripts.dev, 'vite')
})

test('valid direct-entry routes are bounded and invalid parameters reach the site 404', () => {
  const sources = (config.routes || []).map(route => route.src).filter(Boolean)
  for (const source of [
    '^/dashboard$', '^/bullpen$', '^/search$', '^/stories$', '^/about$',
    '^/how-to-read$', '^/methodology$', '^/trust$', '^/signin$', '^/auth/verify$',
    '^/pitcher/[1-9][0-9]*$', '^/matchup/[1-9][0-9]*$',
  ]) {
    assert.ok(sources.includes(source), source)
  }

  const validTeam = config.routes.find(route => route.src?.startsWith('^/team/(ATH|ATL|AZ'))
  assert.equal(validTeam?.dest, '/team/$1/index.html')
  assert.deepEqual(config.routes.find(route => route.src === '^/team/(.*)$'), {
    src: '^/team/(.*)$',
    dest: '/404.html',
    status: 404,
  })
  assert.equal(metadataForLocation('/pitcher/not-a-number'), null)
  assert.equal(metadataForLocation('/matchup/0'), null)
  assert.equal(metadataForLocation('/history/team/INVALID'), null)
})

test('ordinary slash redirects are permanent while the F-008 share policy remains exact', () => {
  assert.ok((config.routes || []).some(route => (
    route.src === '^/(dashboard|bullpen|search|stories|about|how-to-read|methodology|trust|signin|auth/verify)/$'
    && route.status === 308
    && route.headers?.Location === '/$1'
  )))
  assert.ok((config.routes || []).some(route => (
    route.src === '^/share/([A-Za-z0-9._-]{1,64})/$'
    && route.status === 308
    && route.headers?.Location === '/share/$1'
  )))
})

test('query-bearing Team Board identity is canonicalized without tracking parameters', () => {
  const search = '?source=email&team_b=NYY&view=compare&team=BOS&team_a=BOS'
  assert.equal(
    canonicalBullpenPath(search),
    '/bullpen?view=compare&team=BOS&team_a=BOS&team_b=NYY',
  )
  assert.equal(
    metadataForLocation('/bullpen', search)?.canonicalUrl,
    `${PUBLIC_ORIGIN}/bullpen?view=compare&team=BOS&team_a=BOS&team_b=NYY`,
  )
})

test('immutable share metadata remains owned by the F-008 artifact route', () => {
  assert.deepEqual(metadataForLocation('/share/abc123'), { externallyManaged: true })
  assert.equal(metadataForLocation('/share/not valid'), null)
})

test('generated team pages retain actual team identity and exact canonical metadata', () => {
  const html = readFileSync(new URL('../public/team/BOS/index.html', import.meta.url), 'utf8')
  assert.match(html, /<h1>Boston Red Sox Bullpen<\/h1>/)
  assert.match(html, /rel="canonical" href="https:\/\/baseballos\.app\/team\/BOS"/)
  assert.match(html, /property="og:url" content="https:\/\/baseballos\.app\/team\/BOS"/)
})

test('React owns a scoped not-found view rather than redirecting unknown routes Home', async () => {
  const server = await createServer({
    root: process.cwd(),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  })
  try {
    const { APP_ROUTES } = await server.ssrLoadModule('/src/App.jsx')
    const wildcard = APP_ROUTES.find(route => route.path === '*')
    assert.equal(wildcard?.Component?.name, 'NotFound')
    assert.equal(wildcard?.redirectTo, undefined)
    const notFoundSource = readFileSync(
      new URL('../src/components/NotFound.jsx', import.meta.url),
      'utf8',
    )
    assert.match(notFoundSource, /Page not found/)
    assert.match(notFoundSource, /to="\/"/)
    assert.doesNotMatch(notFoundSource, /bullpen state|Team State|Arm Read/i)
  } finally {
    await server.close()
  }
})
