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

// The three Bullpen view tabs read as a clear hierarchy: the flagship team
// board and comparison first, then the full pitcher reference table. The old
// "All Teams" league score table was retired in phase-0-clarity/02 — the
// Dashboard owns the league view.
test('bullpen tabs use the clarified labels', () => {
  // The reliever-only view is publicly labeled "Reliever Finder", never the
  // population-overstating "All Pitchers".
  for (const label of ['Compare Bullpens', 'Reliever Finder']) {
    assert.ok(htmlIncludes(html, label), `missing tab label: ${label}`)
  }
  assert.ok(htmlIncludes(html, 'Board'))
  assert.equal(htmlIncludes(html, 'All Pitchers'), false)
  assert.equal(htmlIncludes(html, '>All Teams<'), false)
})

test('bullpen section is framed as team-specific', () => {
  assert.ok(htmlIncludes(html, 'Team-specific bullpen analysis'))
})

test('all-pitchers view no longer exposes the public recalculate control', () => {
  const pitchersHtml = renderBullpen(['/bullpen?view=pitchers'])
  assert.ok(htmlIncludes(pitchersHtml, 'Show pitchers outside the freshness window'))
  assert.equal(htmlIncludes(pitchersHtml, 'Recalculate'), false)
})
