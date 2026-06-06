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
const { buildLandscapeTeamHref } = await server.ssrLoadModule('/src/components/dashboard/bullpenLandscapeView.js')
const { resolveTeamId } = await server.ssrLoadModule('/src/components/bullpen/board/TonightsBullpenBoard.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

const landscape = {
  capability: 'tonights_bullpen_landscape',
  reference_date: '2026-06-06',
  teams_evaluated: 3,
  games: { available: true, data_state: 'historical', today_count: 0, as_of_date: '2026-06-04', as_of_count: 5, is_today: false },
  constrained_bullpens: [{ team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE', total_relievers: 8, available: 2, monitor: 2, restricted: 4, pct_available: 25, pct_restricted: 50, health_label: 'Availability is constrained tonight.' }],
  available_bullpens: [{ team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA', total_relievers: 8, available: 6, monitor: 1, restricted: 1, pct_available: 75, pct_restricted: 12, health_label: 'Bullpen workload appears manageable.' }],
  monitoring_concentration: [{ team_id: 3, team_name: 'Cubs', team_abbreviation: 'CHC', total_relievers: 8, available: 3, monitor: 4, restricted: 1, pct_available: 37, pct_restricted: 12, health_label: 'Several relievers require monitoring.' }],
  notes: [],
}

const html = render(React.createElement(BullpenLandscape, { landscape }))

// ── Routing correctness: each callout team deep-links into its bullpen board ─

test('clicking a constrained team links to its bullpen board', () => {
  assert.ok(htmlIncludes(html, 'view=board'))
  assert.ok(htmlIncludes(html, 'team=ACE'))
  assert.ok(htmlIncludes(html, 'source=landscape'))
})

test('clicking an available team links to its bullpen board', () => {
  assert.ok(htmlIncludes(html, 'team=BEA'))
})

test('clicking a monitoring team links to its bullpen board', () => {
  assert.ok(htmlIncludes(html, 'team=CHC'))
})

test('rows render as accessible links (anchor + aria-label), keyboard reachable', () => {
  assert.ok(htmlIncludes(html, '<a'))
  assert.ok(htmlIncludes(html, 'Open the bullpen board for Aces'))
  assert.ok(htmlIncludes(html, 'Open the bullpen board for Bears'))
  assert.ok(htmlIncludes(html, 'Open the bullpen board for Cubs'))
})

test('rows carry an interactive affordance but are not buttons', () => {
  assert.ok(htmlIncludes(html, 'cursor-pointer'))
  assert.ok(htmlIncludes(html, 'hover:bg-amber/5'))
  // Informational rows: no role="button" / <button> styling.
  assert.ok(!htmlIncludes(html, 'role="button"'))
  assert.ok(!htmlIncludes(html, '<button'))
})

// ── buildLandscapeTeamHref ─────────────────────────────────────────────────

test('buildLandscapeTeamHref prefers abbreviation, falls back to id, else null', () => {
  assert.equal(buildLandscapeTeamHref({ team_abbreviation: 'SF', team_id: 1 }),
    '/bullpen?view=board&team=SF&source=landscape')
  assert.equal(buildLandscapeTeamHref({ team_id: 5 }),
    '/bullpen?view=board&team=5&source=landscape')
  assert.equal(buildLandscapeTeamHref({}), null)
})

// ── resolveTeamId (the deep-link target the bullpen board reads) ────────────

test('resolveTeamId matches abbreviation (case-insensitive), id, and name', () => {
  const teamList = [
    { team_id: 1, team_abbreviation: 'SF', team_name: 'San Francisco' },
    { team_id: 2, team_abbreviation: 'NYY', team_name: 'New York' },
  ]
  assert.equal(resolveTeamId(teamList, 'SF'), 1)
  assert.equal(resolveTeamId(teamList, 'sf'), 1)        // case-insensitive
  assert.equal(resolveTeamId(teamList, '2'), 2)         // numeric id
  assert.equal(resolveTeamId(teamList, 'New York'), 2)  // name
  assert.equal(resolveTeamId(teamList, 'ZZZ'), null)    // miss
  assert.equal(resolveTeamId(teamList, null), null)
  assert.equal(resolveTeamId([], 'SF'), null)
})

// ── Guardrail: navigation only, no advisory/ranking language ───────────────

test('drilldown adds no advisory or ranking language to the rows', () => {
  const low = html.toLowerCase()
  for (const term of ['best bullpen', 'worst bullpen', 'recommended', 'should use', 'advantage', 'rank #', 'ranked']) {
    assert.ok(!low.includes(term), `leaked term: ${term}`)
  }
})
