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

const view = await server.ssrLoadModule('/src/components/bullpen/relieverFinderView.js')
const { filterRowsByAvailability } = await server.ssrLoadModule(
  '/src/components/bullpen/availabilityView.js',
)
const { default: Bullpen } = await server.ssrLoadModule('/src/components/bullpen/Bullpen.jsx')

const {
  computeFinderIntent,
  describeActiveSort,
  DEFAULT_FINDER_SORT,
  filterRelieverRowsBySearch,
  formatRestDays,
  formatWorkloadCount,
  getAvailabilityFilterOptions,
  getTeamOptionLabel,
  sortRelieverRows,
} = view

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

function mkRow({ id, name, team, status, p7, rest, app7 }) {
  const [teamName, teamAbbr] = team
  return {
    id,
    pitcher_id: id,
    pitcher: { full_name: name, team_name: teamName, team_abbreviation: teamAbbr },
    availability: { availability_status: status },
    pitches_last_7_days: p7,
    days_since_last_appearance: rest,
    appearances_last_7: app7,
  }
}

// Fixture population — a small role-authorized reliever set. "Mike Middle" is the
// internal Avoid tier and carries missing workload facts; "Cal Clean" carries a
// genuine zero, so null and 0 can be told apart.
const rows = [
  mkRow({ id: 1, name: 'Aaron Ace', team: ['Detroit Tigers', 'DET'], status: 'Available', p7: 12, rest: 2, app7: 3 }),
  mkRow({ id: 2, name: 'Zack Zephyr', team: ['New York Yankees', 'NYY'], status: 'Monitor', p7: 30, rest: 1, app7: 4 }),
  mkRow({ id: 3, name: 'Mike Middle', team: ['Detroit Tigers', 'DET'], status: 'Avoid', p7: null, rest: null, app7: null }),
  mkRow({ id: 4, name: 'Ben Bridge', team: ['Boston Red Sox', 'BOS'], status: 'Limited', p7: 5, rest: 4, app7: 1 }),
  mkRow({ id: 5, name: 'Cal Clean', team: ['Boston Red Sox', 'BOS'], status: 'Available', p7: 0, rest: 6, app7: 0 }),
]

// ── Intent gating ───────────────────────────────────────────────────────────

test('the finder has no intent until the visitor asks for something', () => {
  assert.equal(computeFinderIntent({}).hasIntent, false)
  assert.equal(
    computeFinderIntent({ searchTerm: '', selectedTeam: null, availabilityFilter: 'ALL' }).hasIntent,
    false,
  )
})

test('search, team, or a specific availability status each count as intent', () => {
  assert.equal(computeFinderIntent({ searchTerm: 'rivera' }).hasSearchIntent, true)
  assert.equal(computeFinderIntent({ searchTerm: 'rivera' }).hasIntent, true)
  assert.equal(computeFinderIntent({ selectedTeam: 118 }).hasTeamIntent, true)
  assert.equal(computeFinderIntent({ selectedTeam: 118 }).hasIntent, true)
  assert.equal(computeFinderIntent({ availabilityFilter: 'Available' }).hasAvailabilityIntent, true)
  assert.equal(computeFinderIntent({ availabilityFilter: 'Available' }).hasIntent, true)
  // Whitespace-only search is not intent.
  assert.equal(computeFinderIntent({ searchTerm: '   ' }).hasIntent, false)
})

// ── Neutral default sort ────────────────────────────────────────────────────

test('the default order is a neutral pitcher name A–Z, not workload', () => {
  assert.equal(DEFAULT_FINDER_SORT, 'name')
  const ordered = sortRelieverRows(rows).map(r => r.pitcher.full_name)
  assert.deepEqual(ordered, ['Aaron Ace', 'Ben Bridge', 'Cal Clean', 'Mike Middle', 'Zack Zephyr'])
  assert.equal(describeActiveSort(DEFAULT_FINDER_SORT), 'pitcher name (A–Z)')
})

test('an explicit workload sort ranks by real pitch counts, and missing stays last — never zero', () => {
  const ordered = sortRelieverRows(rows, 'pitches').map(r => r.pitcher.full_name)
  // 30 > 12 > 5 > 0, then the missing (null) value sorts to the very end.
  assert.deepEqual(ordered, ['Zack Zephyr', 'Aaron Ace', 'Ben Bridge', 'Cal Clean', 'Mike Middle'])
  // Cal Clean (0 pitches) sorts ahead of Mike Middle (unknown) — 0 is not null.
  assert.ok(ordered.indexOf('Cal Clean') < ordered.indexOf('Mike Middle'))
})

test('an explicit rest sort orders by days since last outing with unknown last', () => {
  const ordered = sortRelieverRows(rows, 'rest').map(r => r.pitcher.full_name)
  // rest days: Zack 1, Aaron 2, Ben 4, Cal 6, then Mike (null) last.
  assert.deepEqual(ordered, ['Zack Zephyr', 'Aaron Ace', 'Ben Bridge', 'Cal Clean', 'Mike Middle'])
})

// ── Honest unknown workload values ──────────────────────────────────────────

test('missing workload values render as an em dash, a real zero renders as zero', () => {
  assert.equal(formatWorkloadCount(null), '—')
  assert.equal(formatWorkloadCount(undefined), '—')
  assert.equal(formatWorkloadCount(0), 0)
  assert.equal(formatWorkloadCount(14), 14)
  assert.equal(formatRestDays(null), '—')
  assert.equal(formatRestDays(0), '0d')
  assert.equal(formatRestDays(3), '3d')
})

// ── Team and availability controls ──────────────────────────────────────────

test('the team option label is the full, unambiguous team name', () => {
  assert.equal(getTeamOptionLabel({ team_name: 'Detroit Tigers', team_abbreviation: 'DET' }), 'Detroit Tigers')
  assert.equal(getTeamOptionLabel(null), '')
})

test('the availability control exposes only the four public statuses plus all', () => {
  const options = getAvailabilityFilterOptions()
  assert.deepEqual(options.map(o => o.value), ['ALL', 'Available', 'Monitor', 'Limited', 'Unavailable'])
  assert.deepEqual(options.map(o => o.label), ['All statuses', 'Available', 'On Watch', 'Limited', 'Unavailable'])
  // The internal Avoid tier is never an option.
  assert.equal(options.some(o => o.label === 'Avoid'), false)
})

test('the internal Avoid tier folds into the public Unavailable filter', () => {
  const unavailable = filterRowsByAvailability(rows, 'Unavailable')
  assert.equal(unavailable.some(r => r.pitcher.full_name === 'Mike Middle'), true)
})

// ── Search matching ─────────────────────────────────────────────────────────

test('search is case-insensitive and matches partial names', () => {
  assert.deepEqual(
    filterRelieverRowsBySearch(rows, 'AARON').map(r => r.pitcher.full_name),
    ['Aaron Ace'],
  )
  assert.deepEqual(
    filterRelieverRowsBySearch(rows, 'ace').map(r => r.pitcher.full_name),
    ['Aaron Ace'],
  )
})

test('search matches team and public availability wording, and empty returns all', () => {
  assert.deepEqual(
    filterRelieverRowsBySearch(rows, 'tigers').map(r => r.pitcher.full_name).sort(),
    ['Aaron Ace', 'Mike Middle'],
  )
  assert.deepEqual(
    filterRelieverRowsBySearch(rows, 'on watch').map(r => r.pitcher.full_name),
    ['Zack Zephyr'],
  )
  assert.equal(filterRelieverRowsBySearch(rows, '').length, rows.length)
})

// ── Component shell (neutral opening view) ──────────────────────────────────

function renderPitchersView() {
  return renderToStaticMarkup(
    React.createElement(MemoryRouter, { initialEntries: ['/bullpen?view=pitchers'] },
      React.createElement(Bullpen),
    ),
  )
}

test('the finder opens on a neutral instruction, not a result list or a count', () => {
  const html = renderPitchersView()
  assert.ok(htmlIncludes(html, 'Search for a reliever or choose a team to inspect recent workload'))
  // No result table and no result/summary count in the neutral state.
  assert.equal(htmlIncludes(html, 'data-table'), false)
  assert.equal(htmlIncludes(html, 'sorted by'), false)
  assert.equal(htmlIncludes(html, 'No pitchers match'), false)
  assert.equal(htmlIncludes(html, '0 results'), false)
})

test('the surface is the Reliever Finder, never All Pitchers', () => {
  const html = renderPitchersView()
  assert.ok(htmlIncludes(html, 'Reliever Finder'))
  assert.equal(htmlIncludes(html, 'All Pitchers'), false)
})

test('the search control comes before team and the result region', () => {
  const html = renderPitchersView()
  const search = html.indexOf('id="reliever-finder-search"')
  const team = html.indexOf('id="reliever-finder-team"')
  const availability = html.indexOf('id="reliever-finder-availability"')
  const neutral = html.indexOf('Search for a reliever or choose a team')
  assert.ok(search > -1 && team > -1 && availability > -1 && neutral > -1)
  assert.ok(search < team, 'search precedes team')
  assert.ok(team < availability, 'team precedes availability')
  assert.ok(availability < neutral, 'controls precede the result region')
})

test('the team and availability controls are compact selects with the right options', () => {
  const html = renderPitchersView()
  // Compact selects, not a 30-pill wall.
  assert.ok(htmlIncludes(html, 'id="reliever-finder-team"'))
  assert.ok(htmlIncludes(html, 'id="reliever-finder-availability"'))
  assert.ok(htmlIncludes(html, '>All teams<'))
  for (const status of ['All statuses', 'Available', 'On Watch', 'Limited', 'Unavailable']) {
    assert.ok(htmlIncludes(html, `>${status}<`), status)
  }
  assert.equal(htmlIncludes(html, '>Avoid<'), false)
})

test('the freshness window control stays available and the clear action hides until intent', () => {
  const html = renderPitchersView()
  assert.ok(htmlIncludes(html, 'Show pitchers outside the freshness window'))
  // No intent yet, so no clear action is shown.
  assert.equal(htmlIncludes(html, 'Clear filters'), false)
})
