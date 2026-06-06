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

const { default: DashboardOrientation } = await server.ssrLoadModule('/src/components/dashboard/DashboardOrientation.jsx')
const { DashboardView } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const inRouter = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

const orientation = inRouter(React.createElement(DashboardOrientation))

// ── Orientation content ────────────────────────────────────────────────────

test('orientation states what BaseballOS is', () => {
  assert.ok(htmlIncludes(orientation, 'Bullpen Availability'))
  assert.ok(htmlIncludes(orientation, 'Workload Intelligence'))
  assert.ok(htmlIncludes(orientation, 'BaseballOS helps you understand bullpen availability, workload, readiness, and'))
  assert.ok(htmlIncludes(orientation, 'Major League Baseball bullpens'))
})

test('orientation gives lightweight next-step guidance', () => {
  assert.ok(htmlIncludes(orientation, 'Start by'))
  assert.ok(htmlIncludes(orientation, 'Bullpen Landscape'))          // explore the landscape
  assert.ok(htmlIncludes(orientation, 'Select a team bullpen'))
  assert.ok(htmlIncludes(orientation, 'Compare bullpen conditions across teams'))
})

test('guidance reuses existing deep-link patterns', () => {
  assert.ok(htmlIncludes(orientation, 'href="/bullpen?view=board"'))
  assert.ok(htmlIncludes(orientation, 'href="/bullpen?view=compare"'))
})

test('orientation is shown on the dashboard even while data is loading', () => {
  const html = inRouter(React.createElement(DashboardView, { data: null, loading: true }))
  assert.ok(htmlIncludes(html, 'Bullpen Availability'))
  assert.ok(htmlIncludes(html, 'Loading bullpen overview'))   // still loading
})

// ── Guardrails ─────────────────────────────────────────────────────────────

test('no marketing / hype language', () => {
  const low = orientation.toLowerCase()
  for (const term of [
    'revolutionary', 'cutting edge', 'cutting-edge', 'ai-powered', 'ai powered',
    'powered by ai', 'smartest', 'world-class', 'game-changing', 'welcome to baseballos',
  ]) {
    assert.ok(!low.includes(term), `marketing term leaked: ${term}`)
  }
})

test('no recommendation / ranking / prediction language', () => {
  const low = orientation.toLowerCase()
  for (const term of [
    'recommended', 'recommendation', 'ranking', 'ranked', 'prediction', 'predict',
    'matchup advice', 'should use', 'best arm', 'best bullpen', 'win probability',
  ]) {
    assert.ok(!low.includes(term), `forbidden term leaked: ${term}`)
  }
})

test('reinforces transparent, trust-first vocabulary', () => {
  const low = orientation.toLowerCase()
  assert.ok(low.includes('transparent'))
  for (const word of ['availability', 'workload', 'readiness', 'constraint']) {
    assert.ok(low.includes(word), `missing identity word: ${word}`)
  }
})
