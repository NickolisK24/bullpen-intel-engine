// UX-002 / #600 — every active /bullpen view has exactly one contextual H1.
//
// /bullpen hosts three canonically different surfaces behind one route. Before
// this change all three shared a single generic H2 reading "Bullpen" and the
// route rendered no H1 at all, in any of its twelve reachable states.
//
// Two layers of proof, because they answer different questions:
//   * the pure identity helper proves the WORDING for every route/team state,
//     including the resolved ones — a static render never resolves useFetch, so
//     the shell alone cannot reach a loaded team list;
//   * the rendered composition proves the STRUCTURE — one h1, its level, its
//     position relative to h2, and the absence of competing page titles.

import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import { populatedBoard } from './fixtures/bullpenBoardFixtures.mjs'
import { differingComparison } from './fixtures/bullpenComparisonFixtures.mjs'
import { teamBoardV2Fixture } from './fixtures/teamBoardV2Fixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { default: Bullpen, getBullpenPageIdentity } = await server.ssrLoadModule(
  '/src/components/bullpen/Bullpen.jsx',
)
const { default: SectionHeader } = await server.ssrLoadModule('/src/components/UI/SectionHeader.jsx')
const { default: TonightsBullpenBoard } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TonightsBullpenBoard.jsx',
)
const { default: BullpenComparisonView } = await server.ssrLoadModule(
  '/src/components/bullpen/board/BullpenComparisonView.jsx',
)
const { default: BullpenOperatingStateCard } = await server.ssrLoadModule(
  '/src/components/bullpen/BullpenOperatingStateCard.jsx',
)
const { toOperatingStateReadModel } = await server.ssrLoadModule(
  '/src/adapters/operatingStateReadModel.js',
)

const BREWERS = { team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL' }
const DODGERS = { team_id: 119, team_name: 'Los Angeles Dodgers', team_abbreviation: 'LAD' }
const TEAM_LIST = [BREWERS, DODGERS]

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const countH1 = (html) => (html.match(/<h1\b/g) || []).length

function renderBullpen(initialEntries = ['/bullpen']) {
  return renderToStaticMarkup(
    React.createElement(MemoryRouter, { initialEntries }, React.createElement(Bullpen)),
  )
}

function h1Text(html) {
  const match = html.match(/<h1\b[^>]*>([\s\S]*?)<\/h1>/)
  return match ? match[1].replace(/<[^>]*>/g, '').trim() : null
}

function renderBoard(boardPayload, team = BREWERS) {
  return renderToStaticMarkup(
    React.createElement(MemoryRouter, null,
      React.createElement(TonightsBullpenBoard, {
        teams: { loading: false, data: [team] },
        initialSelectedTeam: team.team_id,
        boardPayload,
        teamBoardV2Payload: teamBoardV2Fixture(boardPayload),
        gameContextPayload: null,
        storyPayload: null,
      }),
    ),
  )
}

// ── Page identity wording (AC-3), across every route/team state ─────────────

test('Team Board route identity stays stable while the answer block owns the club', () => {
  assert.equal(
    getBullpenPageIdentity('board', TEAM_LIST, { team: 'MIL' }),
    'Team Board',
  )
  // A team id and a full name resolve through the same shared helper.
  assert.equal(
    getBullpenPageIdentity('board', TEAM_LIST, { team: '158' }),
    'Team Board',
  )
  // No team, an unknown reference, and an unloaded team list all read the same.
  assert.equal(getBullpenPageIdentity('board', TEAM_LIST, {}), 'Team Board')
  assert.equal(getBullpenPageIdentity('board', TEAM_LIST, { team: 'ZZZ' }), 'Team Board')
  assert.equal(getBullpenPageIdentity('board', [], { team: 'MIL' }), 'Team Board')
})

test('the Team Board identity carries no state, freshness, or temporal claim', () => {
  const identity = getBullpenPageIdentity('board', TEAM_LIST, { team: 'MIL' })
  for (const banned of [
    'Fresh', 'Stretched', 'Vulnerable', 'Available', 'On Watch', 'Limited',
    'Unavailable', 'Current', 'Tonight', 'Today', 'right now', 'data through',
  ]) {
    assert.equal(
      new RegExp(escapeRegExp(banned), 'i').test(identity),
      false,
      `page identity must not claim "${banned}"`,
    )
  }
  // It is the club's identity, not an abbreviation.
  assert.equal(htmlIncludes(identity, 'MIL Bullpen'), false)
})

test('Compare names both clubs only once two different teams resolve', () => {
  assert.equal(
    getBullpenPageIdentity('compare', TEAM_LIST, { teamA: 'MIL', teamB: 'LAD' }),
    'Milwaukee Brewers vs. Los Angeles Dodgers Bullpen Comparison',
  )
  // Half a comparison is not a comparison.
  assert.equal(getBullpenPageIdentity('compare', TEAM_LIST, {}), 'Compare Bullpens')
  assert.equal(getBullpenPageIdentity('compare', TEAM_LIST, { teamA: 'MIL' }), 'Compare Bullpens')
  assert.equal(getBullpenPageIdentity('compare', TEAM_LIST, { teamB: 'LAD' }), 'Compare Bullpens')
  assert.equal(
    getBullpenPageIdentity('compare', TEAM_LIST, { teamA: 'MIL', teamB: 'MIL' }),
    'Compare Bullpens',
  )
  assert.equal(
    getBullpenPageIdentity('compare', TEAM_LIST, { teamA: 'MIL', teamB: 'ZZZ' }),
    'Compare Bullpens',
  )
})

test('Compare identity carries no winner, edge, or lean language', () => {
  const identity = getBullpenPageIdentity('compare', TEAM_LIST, { teamA: 'MIL', teamB: 'LAD' })
  for (const banned of ['winner', 'advantage', 'edge', 'lean', 'better', 'best', 'pick']) {
    assert.equal(new RegExp(banned, 'i').test(identity), false, banned)
  }
})

test('the Reliever Finder identity is exactly its public name', () => {
  assert.equal(getBullpenPageIdentity('pitchers', TEAM_LIST, {}), 'Reliever Finder')
  assert.equal(getBullpenPageIdentity('pitchers', [], { team: 'MIL' }), 'Reliever Finder')
})

// ── Rendered /bullpen composition (AC-1, AC-2) ─────────────────────────────

test('every /bullpen view renders exactly one h1', () => {
  const routes = [
    '/bullpen',
    '/bullpen?view=board&team=MIL',
    '/bullpen?view=board&team=MIL&pitcher=42',
    '/bullpen?view=compare',
    '/bullpen?view=compare&team_a=MIL',
    '/bullpen?view=compare&team_a=MIL&team_b=LAD',
    '/bullpen?view=pitchers',
    '/bullpen?view=pitchers&team=MIL',
    // An unknown view normalises to the board and must not lose its identity.
    '/bullpen?view=teams',
  ]
  for (const route of routes) {
    assert.equal(countH1(renderBullpen([route])), 1, route)
  }
})

test('the page identity survives the states a child view renders instead of content', () => {
  // A static render never resolves useFetch, so these routes exercise exactly
  // the case AC-7 cares about: the child view is showing an empty/loading
  // placeholder while the shell still owns the page identity.
  const html = renderBullpen(['/bullpen?view=board&team=MIL'])
  assert.equal(countH1(html), 1)
  assert.ok(htmlIncludes(html, 'Pick a team') || htmlIncludes(html, 'Building current bullpen board'))
  assert.ok(h1Text(html))
})

test('the h1 precedes the first h2 wherever a h2 is rendered', () => {
  for (const route of ['/bullpen', '/bullpen?view=compare', '/bullpen?view=pitchers']) {
    const html = renderBullpen([route])
    const h1 = html.indexOf('<h1')
    const h2 = html.indexOf('<h2')
    assert.ok(h1 > -1, route)
    if (h2 > -1) assert.ok(h1 < h2, `h2 precedes h1 on ${route}`)
    // Nothing jumps to h3 before the page has opened a h2.
    const h3 = html.indexOf('<h3')
    if (h3 > -1 && h2 > -1) assert.ok(h2 < h3, `h3 precedes the first h2 on ${route}`)
  }
})

test('the unresolved views render their generic identity verbatim', () => {
  assert.equal(h1Text(renderBullpen(['/bullpen'])), 'Team Board')
  assert.equal(h1Text(renderBullpen(['/bullpen?view=compare'])), 'Compare Bullpens')
  assert.equal(h1Text(renderBullpen(['/bullpen?view=compare&team_a=MIL'])), 'Compare Bullpens')
  assert.equal(h1Text(renderBullpen(['/bullpen?view=pitchers'])), 'Reliever Finder')
})

test('no view simulates a heading instead of using one', () => {
  for (const route of ['/bullpen', '/bullpen?view=compare', '/bullpen?view=pitchers']) {
    const html = renderBullpen([route])
    assert.equal(htmlIncludes(html, 'role="heading"'), false, route)
    assert.equal(htmlIncludes(html, 'aria-level'), false, route)
    // A responsive duplicate would be a second identity announced at one
    // breakpoint only; the bullpen tree renders one DOM at every width.
    assert.equal(/class="[^"]*\bsr-only\b/.test(html), false, route)
  }
})

// ── The Reliever Finder no longer states its name twice (AC-8) ─────────────

test('the finder names itself once, and keeps naming itself after intent', () => {
  const neutral = renderBullpen(['/bullpen?view=pitchers'])
  assert.equal(h1Text(neutral), 'Reliever Finder')
  // The old eyebrow paragraph is gone: the only "Reliever Finder" strings left
  // are the page heading and the view tab.
  assert.equal((neutral.match(/Reliever Finder/g) || []).length, 2)
  assert.ok(htmlIncludes(neutral, 'Search for a reliever or choose a team'))

  // Selecting a team is finder intent, and the identity is unchanged by it.
  const withIntent = renderBullpen(['/bullpen?view=pitchers&team=MIL'])
  assert.equal(h1Text(withIntent), 'Reliever Finder')
  assert.equal(countH1(withIntent), 1)
})

// ── The Team Board stops repeating the club as a second title (AC-8) ───────

test('the answer block owns the selected club identity below the route heading', () => {
  const html = renderBoard(populatedBoard)
  const teamName = populatedBoard.team.team_name

  // No h1 inside the board subtree — the shell owns the only one.
  assert.equal(countH1(html), 0)
  assert.ok(new RegExp(`<h2[^>]*>\\s*${escapeRegExp(teamName)}\\s*</h2>`).test(html))
  assert.ok(htmlIncludes(html, 'data-testid="team-board-answer-block"'))
  // The board's own section heading keeps its level, its id, and its binding.
  assert.ok(htmlIncludes(html, '<h2 id="active-bullpen-title"'))
  assert.ok(htmlIncludes(html, 'aria-labelledby="active-bullpen-title"'))
  // The selected club is the Answer Block's visible h2; the migrated v2
  // Active Bullpen keeps its section heading and remains below it.
  assert.ok(htmlIncludes(html, 'Active Bullpen'))
  assert.ok(htmlIncludes(html, `<span class="sr-only"> — ${teamName}</span>`))
})

test('the operating card keeps its team heading everywhere else', () => {
  // The Dashboard renders the same card without opting in, and must be
  // unchanged: a shared component may not lose its title for every caller.
  const readModel = toOperatingStateReadModel(null, { scope: 'league' })
  const dashboardCard = renderToStaticMarkup(
    React.createElement(MemoryRouter, null,
      React.createElement(BullpenOperatingStateCard, { readModel }),
    ),
  )
  assert.ok(/<h3[^>]*>\s*League-Wide\s*<\/h3>/.test(dashboardCard))

  const optedIn = renderToStaticMarkup(
    React.createElement(MemoryRouter, null,
      React.createElement(BullpenOperatingStateCard, { readModel, titleOwnedByPage: true }),
    ),
  )
  assert.equal(/<h3[^>]*>\s*League-Wide\s*<\/h3>/.test(optedIn), false)
})

// ── Compare section levels (AC-2) ──────────────────────────────────────────

test('comparison keeps three reader-facing page sections and integrates state into headers', () => {
  const html = renderToStaticMarkup(
    React.createElement(MemoryRouter, null,
      React.createElement(BullpenComparisonView, { payload: differingComparison }),
    ),
  )
  for (const label of [
    'Side-by-side Bullpen Read', 'Comparison', 'Full Team Boards',
  ]) {
    assert.ok(
      new RegExp(`<h2[^>]*>${escapeRegExp(label)}</h2>`).test(html),
      `comparison section "${label}" is not a h2`,
    )
  }
  assert.equal(/<h2[^>]*>Team State<\/h2>/.test(html), false)
  assert.equal(/<h2[^>]*>Freshness<\/h2>/.test(html), false)
  assert.ok(htmlIncludes(html, 'Aces'))
  assert.ok(htmlIncludes(html, 'Bears'))
  // Nothing in the comparison body jumps to h3 ahead of those sections.
  const firstH2 = html.indexOf('<h2')
  const firstH3 = html.indexOf('<h3')
  assert.ok(firstH2 > -1)
  if (firstH3 > -1) assert.ok(firstH2 < firstH3)
})

// ── SectionHeader stays h2 for everyone who did not opt in ─────────────────

test('SectionHeader renders h2 by default and h1 only on request', () => {
  const byDefault = renderToStaticMarkup(
    React.createElement(SectionHeader, { title: 'Traffic Intelligence' }),
  )
  assert.ok(/<h2 class="section-title">Traffic Intelligence<\/h2>/.test(byDefault))
  assert.equal(countH1(byDefault), 0)

  const asPageIdentity = renderToStaticMarkup(
    React.createElement(SectionHeader, { title: 'Reliever Finder', as: 'h1' }),
  )
  assert.ok(/<h1 class="section-title">Reliever Finder<\/h1>/.test(asPageIdentity))
  // Same visual treatment; only the level changed.
  assert.ok(htmlIncludes(asPageIdentity, 'class="section-title"'))
})
