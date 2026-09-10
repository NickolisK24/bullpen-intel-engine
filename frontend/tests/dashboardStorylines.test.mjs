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

const { default: DashboardStorylines } = await server.ssrLoadModule('/src/components/dashboard/DashboardStorylines.jsx')
const { getStorylines } = await server.ssrLoadModule('/src/components/dashboard/bullpenLandscapeView.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

const landscape = {
  capability: 'tonights_bullpen_landscape',
  reference_date: '2026-06-06',
  teams_evaluated: 4,
  games: { available: true, data_state: 'historical', today_count: 0, as_of_date: '2026-06-04', as_of_count: 5, is_today: false, message: null },
  constrained_bullpens: [
    { team_id: 1, team_name: 'Chicago Cubs', team_abbreviation: 'CHC', total_relievers: 8, available: 2, monitor: 2, restricted: 4, pct_available: 25, pct_restricted: 50 },
    { team_id: 4, team_name: 'New York Mets', team_abbreviation: 'NYM', total_relievers: 8, available: 3, monitor: 2, restricted: 3, pct_available: 37, pct_restricted: 37 },
  ],
  available_bullpens: [
    { team_id: 2, team_name: 'Washington Nationals', team_abbreviation: 'WSH', total_relievers: 8, available: 6, monitor: 1, restricted: 1, pct_available: 75, pct_restricted: 12 },
  ],
  monitoring_concentration: [
    { team_id: 3, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR', total_relievers: 8, available: 3, monitor: 4, restricted: 1, pct_available: 37, pct_restricted: 12 },
  ],
  notes: [],
  storylines: [
    'Chicago Cubs have four relievers needing rest or unavailable.',
    { public_text: 'Washington Nationals have six rested relievers.' },
    { text: 'Toronto Blue Jays have four relievers on watch.' },
  ],
}

// ── getStorylines computation ──────────────────────────────────────────────

test('backend-authored storylines pass through verbatim', () => {
  const view = getStorylines(landscape)
  assert.ok(view.hasStorylines)
  assert.deepEqual(view.items, [
    'Chicago Cubs have four relievers needing rest or unavailable.',
    'Washington Nationals have six rested relievers.',
    'Toronto Blue Jays have four relievers on watch.',
  ])
})

test('storylines fail closed when backend-authored copy is absent', () => {
  const empty = getStorylines({ storylines: [] })
  assert.equal(empty.hasStorylines, false)
  assert.deepEqual(empty.items, [])
})

test('lane counts never generate client-side storylines', () => {
  const view = getStorylines({
    constrained_bullpens: [{ team_id: 1, team_name: 'Quiet Club', team_abbreviation: 'QC', restricted: 0 }],
    available_bullpens: [{ team_id: 2, team_name: 'Calm Club', team_abbreviation: 'CC', available: 0 }],
    monitoring_concentration: [{ team_id: 3, team_name: 'Steady Club', team_abbreviation: 'SC', monitor: 0 }],
  })
  assert.equal(view.hasStorylines, false)
  assert.deepEqual(view.items, [])
})

// ── Rendering & placement ──────────────────────────────────────────────────

test('the storylines card renders with its title and bullet observations', () => {
  const html = render(React.createElement(DashboardStorylines, { landscape }))
  assert.ok(htmlIncludes(html, 'Storylines'))
  assert.ok(htmlIncludes(html, 'Chicago Cubs have four relievers needing rest or unavailable.'))
  assert.ok(htmlIncludes(html, 'Washington Nationals have six rested relievers.'))
})

test('the storylines block is absent when backend copy is unavailable', () => {
  const html = render(React.createElement(DashboardStorylines, {
    landscape: { ...landscape, storylines: [] },
  }))
  assert.equal(htmlIncludes(html, 'Storylines'), false)
  assert.equal(html, '')
})

// ── Guardrails: descriptive only ────────────────────────────────────────────

test('storylines avoid advisory, ranking, and prediction language', () => {
  const html = render(React.createElement(DashboardStorylines, { landscape })).toLowerCase()
  for (const term of [
    'should use', 'best option', 'best bullpen', 'worst bullpen', 'recommended',
    'recommendation', 'strongest bullpen', 'weakest bullpen', 'expected to win',
    'likely to win', 'win probability', 'odds', 'projection',
  ]) {
    assert.ok(!html.includes(term), `leaked term: ${term}`)
  }
})
