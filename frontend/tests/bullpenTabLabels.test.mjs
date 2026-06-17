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

const { default: Bullpen } = await server.ssrLoadModule('/src/components/bullpen/Bullpen.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
function renderBullpen(initialEntries = ['/bullpen']) {
  return renderToStaticMarkup(
    React.createElement(MemoryRouter, { initialEntries }, React.createElement(Bullpen)),
  )
}

const html = renderBullpen()

// The four Bullpen view tabs read as a clear hierarchy: the two new flagship
// surfaces first, then the full reference tables (renamed from "Pitchers" /
// "Team Summary" so they don't read as a second comparison surface).
test('bullpen tabs use the clarified labels', () => {
  // ("Tonight's Board" has an apostrophe React escapes to &#x27; — match the rest.)
  for (const label of ['Compare Bullpens', 'All Pitchers', 'All Teams']) {
    assert.ok(htmlIncludes(html, label), `missing tab label: ${label}`)
  }
  assert.ok(htmlIncludes(html, 'Board'))
})

test('bullpen section is framed as team-specific', () => {
  assert.ok(htmlIncludes(html, 'Team-specific bullpen analysis'))
})

test('all-pitchers view no longer exposes the public recalculate control', () => {
  const pitchersHtml = renderBullpen(['/bullpen?view=pitchers'])
  assert.ok(htmlIncludes(pitchersHtml, 'Show pitchers outside the freshness window'))
  assert.equal(htmlIncludes(pitchersHtml, 'Recalculate'), false)
})
