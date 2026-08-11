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

  for (const id of [
    'team-state', 'arm-availability', 'pitcher-role', 'pitcher-current-read',
    'read-confidence', 'supporting-reads', 'freshness', 'using-reads',
  ]) {
    assert.ok(htmlIncludes(html, `id="${id}"`), id)
  }
})

test('footer links the guide pages without joining the sidebar', () => {
  const html = render(React.createElement(Footer))

  assert.ok(htmlIncludes(html, 'href="/about"'))
  assert.ok(htmlIncludes(html, 'href="/how-to-read"'))
  assert.ok(htmlIncludes(html, 'href="/methodology"'))
  assert.ok(htmlIncludes(html, 'href="/trust"'))
})


// ── VOC-001 / #638: the glossary is the reader-facing semantic map ──────────

test('every canonical semantic family appears on the page', () => {
  const html = decodeHtml(render(React.createElement(HowToRead)))
  for (const family of [
    'Team State',
    'Arm Availability',
    'Pitcher Role',
    'Pitcher Current Read',
    'Read Confidence',
    'Bullpen Supporting Reads',
    'Freshness & Data Status',
  ]) {
    assert.ok(html.includes(family), `missing family section: ${family}`)
  }
})

test('the Limited family is disambiguated rather than left to inference', () => {
  // Four labels share the word and answer four different questions. The page
  // must name the family each one belongs to, on the page, together.
  const html = decodeHtml(render(React.createElement(HowToRead)))
  for (const pairing of [
    'Limited — Arm Availability',
    'Limited Rest — Pitcher Current Read',
    'Limited Read — Pitcher Current Read / evidence limitation',
    'Role Unclear — Pitcher Role',
  ]) {
    assert.ok(html.includes(pairing), `missing disambiguation: ${pairing}`)
  }
  assert.ok(html.includes('different dimensions'))
})

test('every governed public label is defined somewhere on the page', () => {
  const html = decodeHtml(render(React.createElement(HowToRead)))
  const labels = [
    'Fresh', 'Stretched', 'Vulnerable',
    'Available', 'On Watch', 'Limited', 'Unavailable',
    'Trusted Arm', 'Setup Arm', 'Coverage Arm', 'Middle Relief Arm', 'Role Unclear',
    'Clean Option', 'Watch Arm', 'Limited Rest', 'Limited Read',
    'High', 'Medium', 'Low',
    'Late-Inning Availability', 'Rested Options', 'Late-Inning Pressure',
    'Workload Concentration', 'Coverage Safety', 'Depth Safety',
    'Late-Inning Options',
    'Data through', 'Last data update', 'Last checked',
    'Current', 'Partial Data', 'Stale', 'Data Unavailable',
    'Generated at', 'Published at',
  ]
  for (const label of labels) {
    assert.ok(html.includes(label), `undefined public label: ${label}`)
  }
})

test('supporting reads and read confidence are marked as not-Team-State', () => {
  const html = decodeHtml(render(React.createElement(HowToRead)))
  assert.ok(html.includes('They are not Team State'))
  assert.ok(html.includes('It is not Team State'))
})

test('retired vocabulary does not appear on the glossary', () => {
  const html = decodeHtml(render(React.createElement(HowToRead)))
  for (const retired of [
    'Trusted Arms', 'Healthy Rested Bullpen', 'Rest-Restricted',
    'Strong Read', 'Partial Read', 'Unclear Read', 'Unknown Read',
    'Not Current',
  ]) {
    assert.equal(html.includes(retired), false, `retired term on glossary: ${retired}`)
  }
})
