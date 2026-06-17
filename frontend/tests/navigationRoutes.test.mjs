import assert from 'node:assert/strict'
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
