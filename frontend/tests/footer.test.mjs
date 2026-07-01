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
const render = (element) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, element),
)

test('site footer renders brand, trust, and contact copy', () => {
  const html = render(React.createElement(Footer))

  assert.ok(htmlIncludes(html, 'BaseballOS'))
  assert.ok(htmlIncludes(html, 'Public MLB bullpen intelligence'))
  assert.ok(htmlIncludes(html, 'Making bullpen context easier to understand.'))
  assert.ok(htmlIncludes(html, 'not affiliated with or endorsed by Major League Baseball or its clubs'))
  assert.ok(htmlIncludes(html, 'Data is descriptive and drawn from public sources.'))
  assert.ok(htmlIncludes(html, '© 2026 BaseballOS · All rights reserved.'))
  assert.ok(htmlIncludes(html, 'href="mailto:baseballoshq@gmail.com"'))
  assert.ok(htmlIncludes(html, 'baseballoshq@gmail.com'))
})

test('site footer keeps internal, social, and shell wiring intact', () => {
  const html = render(React.createElement(Footer))
  const appSource = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')

  for (const href of ['/', '/dashboard', '/bullpen', '/stories', '/methodology', '/trust']) {
    assert.ok(htmlIncludes(html, `href="${href}"`), href)
  }
  assert.ok(htmlIncludes(html, 'href="https://x.com/baseballoshq"'))
  assert.ok(htmlIncludes(html, 'aria-label="BaseballOS on X"'))
  assert.ok(htmlIncludes(html, 'href="https://instagram.com/baseballoshq"'))
  assert.ok(htmlIncludes(html, 'aria-label="BaseballOS on Instagram"'))
  assert.ok(htmlIncludes(html, 'target="_blank"'))
  assert.ok(htmlIncludes(html, 'rel="noopener noreferrer"'))
  assert.ok(appSource.includes("import Footer from './components/layout/Footer'"))
  assert.ok(/<AppRoutes\s*\/>\s*<Footer\s*\/>/.test(appSource))
})
