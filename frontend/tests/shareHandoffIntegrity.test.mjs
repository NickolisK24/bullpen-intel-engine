import assert from 'node:assert/strict'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import test from 'node:test'

const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))

test('share routing has one no-slash canonical URL and excludes invalid IDs from SPA fallback', () => {
  const redirects = config.redirects || []
  const rewrites = config.rewrites || []
  const slashRedirect = redirects.find(rule => rule.source === '/share/:publicId/')
  const staticShare = rewrites.find(rule => rule.source === '^/share/([A-Za-z0-9._-]{1,64})$')
  const invalidShare = rewrites.find(rule => rule.source === '^/share/([^/]+)$')
  const spa = rewrites.find(rule => rule.destination === '/index.html')

  assert.deepEqual(slashRedirect, {
    source: '/share/:publicId/',
    destination: '/share/:publicId',
    permanent: true,
  })
  assert.deepEqual(staticShare, {
    source: '^/share/([A-Za-z0-9._-]{1,64})$',
    destination: '/share/$1/index.html',
  })
  assert.equal(invalidShare, undefined)
  assert.equal(new RegExp(spa.source).test('/share/missing-id'), false)
  assert.equal(new RegExp(spa.source).test('/dashboard'), true)
})

test('invalid share routes have a static 404 document with no artifact metadata', () => {
  const notFoundUrl = new URL('../public/404.html', import.meta.url)
  assert.equal(existsSync(notFoundUrl), true)
  const page = readFileSync(notFoundUrl, 'utf8')
  assert.match(page, /Shared artifact not found/i)
  assert.match(page, /noindex,nofollow/i)
  assert.doesNotMatch(page, /og:url|rel="canonical"|baseballos:public-id/i)
})

test('every checked-in immutable share page uses an ordinary non-self live handoff', () => {
  const shareRoot = new URL('../public/share/', import.meta.url)
  const pages = readdirSync(shareRoot, { withFileTypes: true })
    .filter(entry => entry.isDirectory())
    .map(entry => new URL(`../public/share/${entry.name}/index.html`, import.meta.url))

  assert.ok(pages.length > 0)
  for (const pageUrl of pages) {
    const page = readFileSync(pageUrl, 'utf8')
    assert.equal(page.includes('window.location'), false, pageUrl.pathname)
    assert.match(page, /<a href="\/bullpen\?view=board&amp;team=[A-Z0-9-]+&amp;source=share">Open the live BaseballOS bullpen view<\/a>/)
  }
})
