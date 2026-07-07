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
const countOccurrences = (html, text) => (html.match(new RegExp(escapeRegExp(text), 'g')) || []).length
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

test('site footer renders the centered brand card and trust copy', () => {
  const html = render(React.createElement(Footer))
  const text = visibleText(html)

  assert.ok(text.includes('BaseballOS'))
  assert.ok(text.includes('Public MLB bullpen intelligence'))
  assert.ok(text.includes('not affiliated with or endorsed by Major League Baseball or its clubs'))
  assert.ok(text.includes('Data is descriptive and drawn from public sources.'))
  assert.ok(text.includes('© 2026 BaseballOS — All rights reserved.'))
  assert.ok(htmlIncludes(html, 'href="mailto:baseballoshq@gmail.com"'))
  assert.equal(text.includes('@baseballoshq'), false)
  assert.equal(text.includes('baseballoshq@gmail.com'), false)
})

test('site footer links to the learn and trust pages', () => {
  const html = render(React.createElement(Footer))
  const text = visibleText(html)

  for (const [href, label] of [
    ['/about', 'About'],
    ['/how-to-read', 'How to Read'],
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

test('site footer keeps icon-only connect links and shell wiring intact', () => {
  const html = render(React.createElement(Footer))
  const appSource = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')
  const text = visibleText(html)
  assert.equal(text.includes('X: @baseballoshq'), false)
  assert.equal(text.includes('Instagram: @baseballoshq'), false)
  assert.equal(text.includes('Email: baseballoshq@gmail.com'), false)
  assert.ok(htmlIncludes(html, 'href="https://x.com/baseballoshq"'))
  assert.ok(htmlIncludes(html, 'aria-label="BaseballOS on X"'))
  assert.ok(htmlIncludes(html, 'href="https://instagram.com/baseballoshq"'))
  assert.ok(htmlIncludes(html, 'aria-label="BaseballOS on Instagram"'))
  assert.ok(htmlIncludes(html, 'href="mailto:baseballoshq@gmail.com"'))
  assert.ok(htmlIncludes(html, 'aria-label="Email BaseballOS"'))
  assert.equal(countOccurrences(html, '<svg'), 3)
  assert.equal(htmlIncludes(html, '>X</span>'), false)
  assert.ok(htmlIncludes(html, 'target="_blank"'))
  assert.ok(htmlIncludes(html, 'rel="noopener noreferrer"'))
  assert.ok(appSource.includes("import Footer from './components/layout/Footer'"))
  assert.ok(/<AppRoutes\s*\/>\s*<Footer\s*\/>/.test(appSource))
})
