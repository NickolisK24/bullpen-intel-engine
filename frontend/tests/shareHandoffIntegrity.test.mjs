import assert from 'node:assert/strict'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import test from 'node:test'

const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))

test('share routing resolves share files before the ordinary SPA fallback', () => {
  const redirects = config.redirects || []
  const routes = config.routes || []
  const slashRedirect = redirects.find(rule => rule.source === '/share/:publicId/')
  const filesystem = routes.find(rule => rule.handle === 'filesystem')
  const invalidShare = routes.find(rule => rule.src === '^/share/([A-Za-z0-9._-]{1,64})$')
  const spa = routes.find(rule => rule.dest === '/index.html')

  assert.deepEqual(slashRedirect, {
    source: '/share/:publicId/',
    destination: '/share/:publicId',
    permanent: true,
  })
  assert.deepEqual(filesystem, { handle: 'filesystem' })
  assert.deepEqual(invalidShare, {
    src: '^/share/([A-Za-z0-9._-]{1,64})$',
    dest: '/404.html',
    status: 404,
  })
  assert.equal(routes.indexOf(filesystem) < routes.indexOf(invalidShare), true)
  assert.equal(routes.indexOf(invalidShare) < routes.indexOf(spa), true)
  assert.equal(new RegExp(invalidShare.src).test('/share/missing-id'), true)
  assert.equal(new RegExp(spa.src).test('/bullpen'), true)
  assert.equal(new RegExp(spa.src).test('/dashboard'), true)
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
