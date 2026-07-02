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

const { default: BullpenLandscape } = await server.ssrLoadModule('/src/components/dashboard/BullpenLandscape.jsx')
const { getStorylines, STORYLINES_FALLBACK } = await server.ssrLoadModule('/src/components/dashboard/bullpenLandscapeView.js')

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
}

// ── getStorylines computation ──────────────────────────────────────────────

test('storylines are derived dynamically from the landscape counts', () => {
  const view = getStorylines(landscape)
  assert.ok(view.hasStorylines)
  assert.ok(view.items.length >= 3 && view.items.length <= 4)
  assert.ok(view.items.some(item => /Chicago Cubs has 4 relievers needing rest or unavailable, narrowing the late-game margin\./.test(item)))
  assert.ok(view.items.some(item => /Washington Nationals has 6 rested relievers, giving the manager more ways through the late innings\./.test(item)))
  assert.ok(view.items.some(item => /Toronto Blue Jays has 4 relievers on watch, so recent work may still be leaning on the same group\./.test(item)))
})

test('an elevated-stress count storyline appears when multiple clubs are constrained', () => {
  const view = getStorylines(landscape)
  // Two constrained clubs (Cubs, Mets) both carry restricted arms.
  assert.ok(view.items.some(item => /Two clubs have at least one reliever needing rest or unavailable, which can tighten late-game choices\./.test(item)))
})

test('storylines fall back gracefully when no notable situations exist', () => {
  const empty = getStorylines({
    constrained_bullpens: [],
    available_bullpens: [],
    monitoring_concentration: [],
  })
  assert.equal(empty.hasStorylines, false)
  assert.deepEqual(empty.items, [])
  assert.equal(empty.fallback, STORYLINES_FALLBACK)
})

test('zero-count entries do not produce empty or misleading storylines', () => {
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
  const html = render(React.createElement(BullpenLandscape, { landscape }))
  assert.ok(htmlIncludes(html, 'Storylines'))
  assert.ok(htmlIncludes(html, 'Chicago Cubs has 4 relievers needing rest or unavailable, narrowing the late-game margin.'))
  assert.ok(htmlIncludes(html, 'Washington Nationals has 6 rested relievers, giving the manager more ways through the late innings.'))
})

test('the storylines card sits above the individual situation columns', () => {
  const html = render(React.createElement(BullpenLandscape, { landscape }))
  assert.ok(html.indexOf('Storylines') < html.indexOf('Most Available'),
    'storylines should precede the situation columns')
})

test('the storylines fallback renders when the dataset is thin', () => {
  const html = render(React.createElement(BullpenLandscape, {
    landscape: { ...landscape, constrained_bullpens: [], available_bullpens: [], monitoring_concentration: [] },
  }))
  assert.ok(htmlIncludes(html, 'Storylines'))
  assert.ok(htmlIncludes(html, STORYLINES_FALLBACK))
})

// ── Guardrails: descriptive only ────────────────────────────────────────────

test('storylines avoid advisory, ranking, and prediction language', () => {
  const html = render(React.createElement(BullpenLandscape, { landscape })).toLowerCase()
  for (const term of [
    'should use', 'best option', 'best bullpen', 'worst bullpen', 'recommended',
    'recommendation', 'strongest bullpen', 'weakest bullpen', 'expected to win',
    'likely to win', 'win probability', 'odds', 'projection',
  ]) {
    assert.ok(!html.includes(term), `leaked term: ${term}`)
  }
})
