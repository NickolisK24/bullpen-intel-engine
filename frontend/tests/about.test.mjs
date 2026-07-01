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
const { default: About } = await server.ssrLoadModule('/src/components/about/About.jsx')
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

test('About page renders the product-first mission and trust CTAs', () => {
  const html = render(React.createElement(About))

  assert.ok(visibleIncludes(html, 'About BaseballOS'))
  assert.ok(visibleIncludes(html, 'Making bullpen context easier to understand.'))
  assert.ok(visibleIncludes(html, 'Read Methodology'))
  assert.ok(visibleIncludes(html, 'View Data & Trust'))
})

test('About route is registered without joining the sidebar nav', () => {
  const sidebarSource = readFileSync(new URL('../src/components/Sidebar.jsx', import.meta.url), 'utf8')

  assert.equal(routeByPath('/about')?.Component?.name, 'About')
  assert.equal(sidebarSource.includes("to: '/about'"), false)
})

test('footer exposes About as the first Learn link', () => {
  const html = render(React.createElement(Footer))
  const about = html.indexOf('href="/about"')
  const methodology = html.indexOf('href="/methodology"')
  const trust = html.indexOf('href="/trust"')

  assert.ok(about > -1)
  assert.ok(methodology > about)
  assert.ok(trust > methodology)
})
