import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
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
const { default: HowToRead } = await server.ssrLoadModule('/src/components/guide/HowToRead.jsx')
const { default: Footer } = await server.ssrLoadModule('/src/components/layout/Footer.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const decodeHtml = (html) => String(html)
  .replace(/&amp;/g, '&')
  .replace(/&#x27;/g, "'")
const visibleIncludes = (html, text) => htmlIncludes(decodeHtml(html), text)
const render = (element) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, element),
)

function routeByPath(path) {
  return APP_ROUTES.find(route => route.path === path)
}

test('How to Read page renders the guide terms and trust CTAs', () => {
  const html = render(React.createElement(HowToRead))

  assert.ok(visibleIncludes(html, 'How to Read BaseballOS'))
  assert.ok(visibleIncludes(html, 'Available'))
  assert.ok(visibleIncludes(html, 'On Watch'))
  assert.ok(visibleIncludes(html, 'Limited'))
  assert.ok(visibleIncludes(html, 'Unavailable'))
  assert.ok(visibleIncludes(html, 'Read Methodology'))
  assert.ok(visibleIncludes(html, 'View Data & Trust'))
})

test('How to Read route is registered without joining the sidebar nav', () => {
  const sidebarSource = readFileSync(new URL('../src/components/Sidebar.jsx', import.meta.url), 'utf8')

  assert.equal(routeByPath('/how-to-read')?.Component?.name, 'HowToRead')
  assert.equal(sidebarSource.includes("to: '/how-to-read'"), false)
})

test('How to Read page exposes the expected section anchors', () => {
  const html = render(React.createElement(HowToRead))

  for (const id of ['team-state', 'arm-availability', 'bullpen-reads', 'freshness', 'using-reads']) {
    assert.ok(htmlIncludes(html, `id="${id}"`), id)
  }
})

test('footer exposes How to Read between About and Methodology', () => {
  const html = render(React.createElement(Footer))
  const about = html.indexOf('href="/about"')
  const howToRead = html.indexOf('href="/how-to-read"')
  const methodology = html.indexOf('href="/methodology"')
  const trust = html.indexOf('href="/trust"')

  assert.ok(about > -1)
  assert.ok(howToRead > about)
  assert.ok(methodology > howToRead)
  assert.ok(trust > methodology)
})
