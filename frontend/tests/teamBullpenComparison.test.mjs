import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import { differingComparison, makeComparison, staleComparison } from './fixtures/bullpenComparisonFixtures.mjs'

const server = await createServer({ root: process.cwd(), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
after(async () => server.close())

const { default: BullpenComparisonView } = await server.ssrLoadModule('/src/components/bullpen/board/BullpenComparisonView.jsx')
const view = await server.ssrLoadModule('/src/components/bullpen/board/teamBullpenComparisonView.js')
const render = payload => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(BullpenComparisonView, { payload })))
const includes = (html, value) => html.includes(String(value))

test('renders the aligned current-state domains for both teams', () => {
  const html = render(differingComparison)
  for (const value of ['Current Bullpen Comparison', 'Aces', 'Bears', 'Fresh', 'Stretched', 'Rested Options', 'Worked Yesterday', 'Back-to-Back', 'Recent Workload', 'Relief Appearances', 'Contributing Relievers', 'Rotation Transfer', 'Short Starts', 'Bullpen Innings', 'Availability', 'On Watch', 'Unavailable']) {
    assert.ok(includes(html, value), `missing ${value}`)
  }
})

test('shared presentation accepts neutral away and home entry labels', () => {
  const html = renderToStaticMarkup(React.createElement(
    MemoryRouter,
    null,
    React.createElement(BullpenComparisonView, {
      payload: differingComparison,
      sideLabels: { teamA: 'Away · Aces', teamB: 'Home · Bears' },
      showShare: false,
    }),
  ))
  assert.ok(includes(html, 'Away · Aces'))
  assert.ok(includes(html, 'Home · Bears'))
  assert.equal(includes(html, 'Share'), false)
})

test('uses backend-authored public unavailable without frontend summation', () => {
  const v = view.getComparisonView(differingComparison)
  const availability = v.domains.find(domain => domain.key === 'availability')
  const unavailable = availability.rows.find(row => row.key === 'unavailable')
  assert.equal(unavailable.valueA, 2)
  assert.equal(unavailable.valueB, 5)
  const source = view.getComparisonView.toString()
  assert.equal(source.includes('avoid'), false)
  assert.equal(source.includes('reduce('), false)
})

test('valid zero remains zero while missing remains an em dash', () => {
  const domains = structuredClone(differingComparison.comparison.domains)
  domains.workload.team_a.pitches = 0
  domains.workload.team_b.pitches = null
  const v = view.getComparisonView(makeComparison({ domains }))
  const pitches = v.domains.find(domain => domain.key === 'workload').rows.find(row => row.key === 'pitches')
  assert.equal(pitches.valueA, 0)
  assert.equal(pitches.valueB, '—')
})

test('withheld domain stays local and does not remove healthy domains', () => {
  const html = render(staleComparison)
  assert.ok(includes(html, 'Rotation transfer comparison is unavailable'))
  assert.ok(includes(html, 'Rested Options'))
  assert.ok(includes(html, 'Relief Appearances'))
  assert.ok(includes(html, 'On Watch'))
})

test('links directly to both canonical Team Boards', () => {
  const html = render(differingComparison)
  assert.ok(includes(html, 'href="/bullpen?view=board&amp;team=ACE&amp;source=comparison"'))
  assert.ok(includes(html, 'href="/bullpen?view=board&amp;team=BEA&amp;source=comparison"'))
  assert.ok(includes(html, 'Open the Aces board'))
  assert.ok(includes(html, 'Open the Bears board'))
})

test('mobile is linear without a min-width or horizontal-scroll dependency', () => {
  const html = render(differingComparison)
  assert.ok(includes(html, 'md:hidden'))
  assert.ok(includes(html, 'hidden grid-cols-'))
  assert.equal(includes(html, 'overflow-x-auto'), false)
  assert.equal(includes(html, 'min-w-[38rem]'), false)
})

test('renders neutral facts with no leader or prediction treatment', () => {
  const html = render(differingComparison).toLowerCase()
  for (const term of ['leader', 'winner', 'advantage', 'edge', 'better bullpen', 'stronger bullpen', 'likely', 'recommend', 'rank']) {
    assert.equal(html.includes(term), false, `leaked ${term}`)
  }
})

test('empty payload renders a local unavailable state', () => {
  assert.ok(includes(render({}), 'Comparison unavailable'))
})

test('view preserves backend order and exact values', () => {
  const v = view.getComparisonView(differingComparison)
  assert.deepEqual(v.domains.map(domain => domain.key), ['rest', 'workload', 'rotation', 'availability'])
  assert.equal(v.labelA, 'Aces')
  assert.equal(v.labelB, 'Bears')
  assert.equal(v.representedDate, '2026-06-04')
})

test('request component retains one comparison request and no per-domain fan-out', async () => {
  const component = await import('node:fs/promises').then(fs => fs.readFile(new URL('../src/components/bullpen/board/TeamBullpenComparison.jsx', import.meta.url), 'utf8'))
  assert.equal((component.match(/getTeamBullpenComparison\(/g) || []).length, 1)
  for (const forbidden of ['/board-v2', 'recent-work', 'rotation', 'workload-pattern']) assert.equal(component.includes(forbidden), false)
})
