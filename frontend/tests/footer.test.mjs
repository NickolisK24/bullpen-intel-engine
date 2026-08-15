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

const { default: Footer } = await server.ssrLoadModule('/src/components/layout/Footer.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const decodeHtml = (html) => String(html)
  .replace(/&amp;/g, '&')
  .replace(/&#x27;/g, "'")
const visibleText = (html) => decodeHtml(html)
  .replace(/<style[\s\S]*?<\/style>/gi, ' ')
  .replace(/<script[\s\S]*?<\/script>/gi, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()
const render = (element) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, element),
)

test('site footer renders the compact trust statement from the product reference', () => {
  const html = render(React.createElement(Footer))
  const text = visibleText(html)

  assert.ok(text.includes('not affiliated with or endorsed by Major League Baseball or its clubs'))
  assert.ok(text.includes('Reads describe observable present conditions drawn from public sources.'))
  assert.equal(htmlIncludes(html, 'mailto:'), false)
})

test('site footer links to the learn and trust pages', () => {
  const html = render(React.createElement(Footer))
  const text = visibleText(html)

  for (const [href, label] of [
    ['/about', 'About'],
    ['/how-to-read', 'Start Here'],
    ['/methodology', 'Methodology'],
    ['/trust', 'Data & Trust'],
  ]) {
    assert.ok(htmlIncludes(html, `href="${href}"`), href)
    assert.ok(text.includes(label), label)
  }
  // The footer stays a learn/trust rail — the sidebar owns product navigation.
  for (const href of ['/dashboard', '/bullpen', '/stories']) {
    assert.equal(htmlIncludes(html, `href="${href}"`), false, href)
  }
})

test('site footer stays a compact trust rail and shell wiring remains intact', () => {
  const html = render(React.createElement(Footer))
  const appSource = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')
  assert.equal(htmlIncludes(html, '<svg'), false)
  assert.equal(htmlIncludes(html, 'target="_blank"'), false)
  assert.ok(appSource.includes("import Footer from './components/layout/Footer'"))
  assert.ok(/<AppRoutes\s*\/>\s*<Footer\s*\/>/.test(appSource))
})
