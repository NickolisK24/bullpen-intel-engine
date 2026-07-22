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

const { default: Sidebar } = await server.ssrLoadModule('/src/components/Sidebar.jsx')
const { IntelligenceSurfaceView } = await server.ssrLoadModule('/src/components/home/IntelligenceSurface.jsx')
const { PRIMARY_NAV, SUPPORTING_NAV, isNavDestinationActive } = await server.ssrLoadModule('/src/utils/navigation.js')

const sidebarSource = readFileSync(new URL('../src/components/Sidebar.jsx', import.meta.url), 'utf8')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const renderAt = (el, path = '/') => renderToStaticMarkup(
  React.createElement(MemoryRouter, { initialEntries: [path] }, el),
)

// ── Navigation config: destinations, order, labels, routes ─────────────────

test('primary navigation is the six core bullpen surfaces in order', () => {
  assert.deepEqual(
    PRIMARY_NAV.map(item => item.label),
    ['Today', 'League Board', 'Team Bullpens', 'Compare Bullpens', 'Reliever Finder', 'Stories'],
  )
})

test('supporting navigation keeps the trust and explainer pages', () => {
  assert.deepEqual(
    SUPPORTING_NAV.map(item => item.label),
    ['How to Read', 'Methodology', 'Data & Trust', 'About'],
  )
})

test('primary destinations map to the existing bullpen routes and query views', () => {
  const byLabel = Object.fromEntries(PRIMARY_NAV.map(item => [item.label, item.to]))
  assert.equal(byLabel['Today'], '/')
  assert.equal(byLabel['League Board'], '/dashboard')
  assert.equal(byLabel['Team Bullpens'], '/bullpen')
  assert.equal(byLabel['Compare Bullpens'], '/bullpen?view=compare')
  assert.equal(byLabel['Reliever Finder'], '/bullpen?view=pitchers')
  assert.equal(byLabel['Stories'], '/stories')
})

test('no primary label overstates the reliever population or uses the old ambiguous names', () => {
  const labels = [...PRIMARY_NAV, ...SUPPORTING_NAV].map(item => item.label)
  assert.equal(labels.includes('All Pitchers'), false)
  assert.equal(labels.includes('Dashboard'), false)
  assert.equal(labels.includes('Bullpen'), false)
})

test('every navigation destination is a unique route with a unique label', () => {
  const items = [...PRIMARY_NAV, ...SUPPORTING_NAV]
  const routes = items.map(item => item.to)
  const labels = items.map(item => item.label)
  assert.equal(new Set(routes).size, routes.length)
  assert.equal(new Set(labels).size, labels.length)
})

// ── Active-state behavior (bullpen views share one path) ───────────────────

function activeLabels(path) {
  const [pathname, search] = path.includes('?') ? [path.slice(0, path.indexOf('?')), path.slice(path.indexOf('?'))] : [path, '']
  const location = { pathname, search }
  return PRIMARY_NAV.filter(item => isNavDestinationActive(item, location)).map(item => item.label)
}

test('exactly one primary destination is active per route, including bullpen views', () => {
  assert.deepEqual(activeLabels('/'), ['Today'])
  assert.deepEqual(activeLabels('/dashboard'), ['League Board'])
  assert.deepEqual(activeLabels('/bullpen'), ['Team Bullpens'])
  assert.deepEqual(activeLabels('/bullpen?view=board'), ['Team Bullpens'])
  assert.deepEqual(activeLabels('/bullpen?view=compare'), ['Compare Bullpens'])
  assert.deepEqual(activeLabels('/bullpen?view=pitchers'), ['Reliever Finder'])
  assert.deepEqual(activeLabels('/stories'), ['Stories'])
})

test('Today only matches the root, never a deeper route', () => {
  const today = PRIMARY_NAV.find(item => item.label === 'Today')
  assert.equal(isNavDestinationActive(today, { pathname: '/', search: '' }), true)
  assert.equal(isNavDestinationActive(today, { pathname: '/dashboard', search: '' }), false)
})

// ── Sidebar rendering: accessible menu control + active state ──────────────

test('mobile menu toggle exposes expanded state, controls the nav, and has an open label', () => {
  const html = renderAt(React.createElement(Sidebar))
  assert.ok(htmlIncludes(html, 'aria-controls="primary-navigation"'))
  assert.ok(htmlIncludes(html, 'aria-expanded="false"'))
  assert.ok(htmlIncludes(html, 'aria-label="Open navigation menu"'))
  assert.ok(htmlIncludes(html, 'id="primary-navigation"'))
})

test('sidebar renders primary destinations before the supporting group', () => {
  const html = renderAt(React.createElement(Sidebar))
  const lastPrimary = html.indexOf('>Stories<')
  const firstSupporting = html.indexOf('>How to Read<')
  assert.ok(lastPrimary > -1 && firstSupporting > -1)
  assert.ok(lastPrimary < firstSupporting)
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=compare"'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=pitchers"'))
})

// Returns the <a> tag that links to `href`, or '' if none.
function anchorFor(html, href) {
  const match = html.match(new RegExp(`<a[^>]*\\shref="${escapeRegExp(href)}"[^>]*>`))
  return match ? match[0] : ''
}

test('the current route receives an active state on the matching destination', () => {
  const comparePage = renderAt(React.createElement(Sidebar), '/bullpen?view=compare')
  // The Compare link is current; Team Bullpens (same path, different view) is not.
  assert.ok(anchorFor(comparePage, '/bullpen?view=compare').includes('aria-current="page"'))
  assert.equal(anchorFor(comparePage, '/bullpen').includes('aria-current="page"'), false)

  const todayPage = renderAt(React.createElement(Sidebar), '/')
  assert.ok(anchorFor(todayPage, '/').includes('aria-current="page"'))

  const relieverPage = renderAt(React.createElement(Sidebar), '/bullpen?view=pitchers')
  assert.ok(anchorFor(relieverPage, '/bullpen?view=pitchers').includes('aria-current="page"'))
  assert.equal(anchorFor(relieverPage, '/bullpen').includes('aria-current="page"'), false)
})

// ── Menu close behavior wiring (no interactive DOM harness in this suite) ───

test('mobile menu wires close-on-select, close-on-route-change, escape, and a close label', () => {
  // Close control / destination selection both close via the shared handler.
  assert.ok(sidebarSource.includes('closeMenu'))
  assert.ok(sidebarSource.includes('onNavigate={closeMenu}'))
  // A distinct accessible label for the open menu's close control.
  assert.ok(sidebarSource.includes("'Close navigation menu'"))
  // Route changes close the menu so browser navigation never strands it open.
  assert.ok(sidebarSource.includes('useLocation'))
  assert.ok(sidebarSource.includes('[location.pathname, location.search]'))
  assert.ok(sidebarSource.includes('setOpen(false)'))
  // Escape closes the menu.
  assert.ok(sidebarSource.includes("event.key === 'Escape'"))
})

// ── First-use entry path on Today ──────────────────────────────────────────

test('the first-use entry area offers the four primary actions with existing routes', () => {
  const html = renderAt(React.createElement(IntelligenceSurfaceView, {}))
  // ("Today's" has an apostrophe React escapes to &#x27;, so match the rest.)
  for (const title of ['Bullpen Read', 'Find a Team', 'Compare Two Bullpens', 'Find a Reliever']) {
    assert.ok(htmlIncludes(html, title), `missing action: ${title}`)
  }
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=compare"'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=pitchers"'))
  assert.ok(htmlIncludes(html, 'href="/bullpen"'))
})

test('the entry area sits after the daily read and does not replace it', () => {
  const html = renderAt(React.createElement(IntelligenceSurfaceView, {}))
  const dailyRead = html.indexOf('id="bullpen-picture"')
  const entryArea = html.indexOf('id="explore-baseballos"')
  assert.ok(dailyRead > -1, 'primary daily read is still rendered')
  assert.ok(entryArea > -1, 'first-use entry area is rendered')
  assert.ok(dailyRead < entryArea, 'entry area follows the daily read')
})
