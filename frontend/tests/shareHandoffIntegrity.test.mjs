import assert from 'node:assert/strict'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import test from 'node:test'

const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))

test('share routing resolves share files before the scoped and site-wide 404s', () => {
  const routes = config.routes || []
  const slashRedirect = routes.find(rule => rule.src === '^/share/([A-Za-z0-9._-]{1,64})/$')
  const filesystem = routes.find(rule => rule.handle === 'filesystem')
  const invalidShare = routes.find(rule => rule.src === '^/share/([A-Za-z0-9._-]{1,64})$')
  const unknown = routes.at(-1)

  assert.deepEqual(slashRedirect, {
    src: '^/share/([A-Za-z0-9._-]{1,64})/$',
    headers: { Location: '/share/$1' },
    status: 308,
  })
  assert.equal(routes.indexOf(slashRedirect) < routes.indexOf(filesystem), true)
  assert.deepEqual(filesystem, { handle: 'filesystem' })
  assert.deepEqual(invalidShare, {
    src: '^/share/([A-Za-z0-9._-]{1,64})$',
    dest: '/share-404.html',
    status: 404,
  })
  assert.equal(routes.indexOf(filesystem) < routes.indexOf(invalidShare), true)
  assert.equal(routes.indexOf(invalidShare) < routes.indexOf(unknown), true)
  assert.equal(new RegExp(invalidShare.src).test('/share/missing-id'), true)
})

test('invalid share routes have a static 404 document with no artifact metadata', () => {
  const notFoundUrl = new URL('../public/share-404.html', import.meta.url)
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
    assert.doesNotMatch(page, /<script\b/i, pageUrl.pathname)
    assert.match(page, /<link rel="stylesheet" href="\/share-preview\.css" \/>/)
    assert.match(page, /Published BaseballOS observation/)
    assert.match(page, /<h1>[^<]+<\/h1>/)
    assert.match(page, /Frozen historical observation/)
    assert.match(
      page,
      /<a class="share-live-cta" href="\/bullpen\?view=board&amp;team=[A-Z0-9-]+&amp;source=share">Open current [^<]+ bullpen<span aria-hidden="true">→<\/span><\/a>/,
    )
  }
})
