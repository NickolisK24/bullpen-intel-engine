import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import { makeLeagueTeamStateListing } from './fixtures/leagueTeamStateListingFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => server.close())

const { getLeagueTeamStateListingView } = await server.ssrLoadModule('/src/components/dashboard/leagueTeamStateListingView.js')
const { default: LeagueTeamStateLandscape } = await server.ssrLoadModule('/src/components/dashboard/LeagueTeamStateLandscape.jsx')
const { DashboardView } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')
const { getLeagueTeamStates } = await server.ssrLoadModule('/src/utils/api.js')

const clone = value => structuredClone(value)
const render = element => renderToStaticMarkup(React.createElement(MemoryRouter, null, element))
const visibleText = html => html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()

test('narrow API client requests the governed league Team State endpoint', async () => {
  const originalFetch = globalThis.fetch
  let requestedUrl = null
  globalThis.fetch = async url => {
    requestedUrl = String(url)
    return { ok: true, json: async () => ({ capability: 'league_team_state_listing_v1' }) }
  }
  try {
    await getLeagueTeamStates()
    assert.equal(requestedUrl, '/api/bullpen/team-states')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('accepts only the governed capability with exactly 30 unique team identities', () => {
  const payload = makeLeagueTeamStateListing()
  const view = getLeagueTeamStateListingView(payload)
  assert.equal(view.valid, true)
  assert.equal(view.teamCount, 30)
  assert.equal(new Set(view.groups.flatMap(group => group.teams).map(team => team.teamId)).size, 30)

  assert.equal(getLeagueTeamStateListingView({ ...payload, capability: 'other' }).valid, false)
  assert.equal(getLeagueTeamStateListingView({ ...payload, teams: null }).valid, false)
  assert.equal(getLeagueTeamStateListingView({ ...payload, expected_team_count: null }).valid, false)
  assert.equal(getLeagueTeamStateListingView({ ...payload, team_count: null }).valid, false)
})

test('requires backend count equality and represented plus withheld coverage without repairing it', () => {
  const payload = makeLeagueTeamStateListing({ withheld: 1 })
  assert.equal(getLeagueTeamStateListingView(payload).valid, true)
  for (const mutation of [
    { expected_team_count: 29 },
    { team_count: 29 },
    { represented_team_count: 28 },
    { withheld_team_count: 0 },
  ]) {
    assert.equal(getLeagueTeamStateListingView({ ...payload, ...mutation }).valid, false)
  }
})

test('requires all three non-ranking contract flags to remain false', () => {
  const payload = makeLeagueTeamStateListing()
  for (const key of ['ranking_applied', 'selection_made', 'prediction_applied']) {
    assert.equal(getLeagueTeamStateListingView({ ...payload, [key]: true }).valid, false, key)
    assert.equal(getLeagueTeamStateListingView({ ...payload, [key]: null }).valid, false, key)
  }
})

test('groups canonical Fresh, Stretched, and Vulnerable reads only from the governed block', () => {
  const view = getLeagueTeamStateListingView(makeLeagueTeamStateListing())
  assert.deepEqual(view.groups.map(group => group.label), ['Fresh', 'Stretched', 'Vulnerable'])
  assert.deepEqual(view.groups.map(group => group.teams.length), [10, 10, 10])
  for (const group of view.groups) {
    assert.ok(group.teams.every(team => team.teamState.publicLabel === group.label))
  }
})

test('rejects noncanonical represented state and unavailable rows assigned a state', () => {
  const noncanonical = makeLeagueTeamStateListing()
  noncanonical.teams[0].team_state.public_state = 'dominant'
  noncanonical.teams[0].team_state.public_label = 'Dominant'
  assert.equal(getLeagueTeamStateListingView(noncanonical).valid, false)

  const assignedUnavailable = makeLeagueTeamStateListing({ withheld: 1 })
  assignedUnavailable.teams[29].team_state.public_state = 'fresh'
  assignedUnavailable.teams[29].team_state.public_label = 'Fresh'
  assert.equal(getLeagueTeamStateListingView(assignedUnavailable).valid, false)
})

test('sorts alphabetically by full name inside each state group, never by severity or source order', () => {
  const payload = makeLeagueTeamStateListing()
  payload.teams.reverse()
  const view = getLeagueTeamStateListingView(payload)
  for (const group of view.groups) {
    const names = group.teams.map(team => team.teamName)
    assert.deepEqual(names, [...names].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' })))
  }
  assert.deepEqual(view.groups.map(group => group.label), ['Fresh', 'Stretched', 'Vulnerable'])
})

test('29 represented and one withheld accounts for all 30 with a separate publication exception', () => {
  const view = getLeagueTeamStateListingView(makeLeagueTeamStateListing({ withheld: 1 }))
  assert.equal(view.valid, true)
  assert.equal(view.groups.flatMap(group => group.teams).length, 29)
  assert.equal(view.exceptions.length, 1)
  assert.equal(view.representedTeamCount + view.withheldTeamCount, view.expectedTeamCount)

  const html = render(React.createElement(LeagueTeamStateLandscape, { view }))
  assert.match(html, /Publication exceptions/)
  assert.match(html, /Washington Nationals/)
  assert.doesNotMatch(html, /Team State: (Withheld|Unavailable)/)
})

test('snapshot unavailable renders one honest league-level unavailable state without 30 repeated rows', () => {
  const view = getLeagueTeamStateListingView(makeLeagueTeamStateListing({ status: 'snapshot_unavailable' }))
  assert.equal(view.valid, true)
  assert.equal(view.globalUnavailable, true)
  const html = render(React.createElement(LeagueTeamStateLandscape, { view }))
  assert.equal((html.match(/The current league Team State view is unavailable\./g) || []).length, 1)
  assert.doesNotMatch(html, /Arizona Diamondbacks/)
  assert.doesNotMatch(html, /Publication exceptions/)
  assert.doesNotMatch(html, /30 MLB clubs · grouped by published Team State/)
})

test('duplicate IDs, malformed identities, and row omissions fail closed', () => {
  const duplicate = makeLeagueTeamStateListing()
  duplicate.teams[1].team_id = duplicate.teams[0].team_id
  assert.equal(getLeagueTeamStateListingView(duplicate).valid, false)

  const malformed = makeLeagueTeamStateListing()
  malformed.teams[0].team_name = ''
  assert.equal(getLeagueTeamStateListingView(malformed).valid, false)

  const omitted = makeLeagueTeamStateListing()
  omitted.teams.pop()
  assert.equal(getLeagueTeamStateListingView(omitted).valid, false)
})

test('rendered landscape is compact, uses full names and canonical Team Board links, and avoids ranking chrome', () => {
  const view = getLeagueTeamStateListingView(makeLeagueTeamStateListing())
  const html = render(React.createElement(LeagueTeamStateLandscape, { view }))
  const text = visibleText(html)
  assert.match(text, /Current Bullpen State/)
  assert.match(text, /30 MLB clubs · grouped by published Team State/)
  assert.match(text, /Los Angeles Dodgers/)
  assert.match(html, /href="\/bullpen\?view=board&amp;team=LAD&amp;source=dashboard"/)
  assert.equal(/\b(Most|Top|Best|Worst|score|rank|grade)\b/i.test(text), false)
  assert.doesNotMatch(text, /Rested & Available|On Watch|Needs Rest \/ Unavailable/)
  assert.doesNotMatch(text, /availability count|workload|confidence|evidence/)
  assert.match(html, /grid-cols-1/)
  assert.match(html, /lg:grid-cols-3/)
  assert.doesNotMatch(html, /overflow-x/)
})

test('zero-count groups remain visible at natural height without changing governed order or populated groups', () => {
  const payload = makeLeagueTeamStateListing()
  payload.teams.forEach((team, index) => {
    team.team_state.public_state = index < 14 ? 'stretched' : 'vulnerable'
    team.team_state.public_label = index < 14 ? 'Stretched' : 'Vulnerable'
  })
  const view = getLeagueTeamStateListingView(payload)
  const html = render(React.createElement(LeagueTeamStateLandscape, { view }))
  const text = visibleText(html)

  assert.equal(view.valid, true)
  assert.deepEqual(view.groups.map(group => group.label), ['Fresh', 'Stretched', 'Vulnerable'])
  assert.deepEqual(view.groups.map(group => group.teams.length), [0, 14, 16])
  assert.ok(text.indexOf('Fresh') < text.indexOf('Stretched'))
  assert.ok(text.indexOf('Stretched') < text.indexOf('Vulnerable'))
  assert.match(html, /Fresh<\/h3><span[^>]*>0<\/span>/)
  assert.match(html, /No published club reads in this group\./)
  assert.match(html, /class="grid min-w-0 grid-cols-1 items-start gap-3 lg:grid-cols-3"/)
  assert.equal((html.match(/source=dashboard/g) || []).length, 30)
  assert.match(html, /Arizona Diamondbacks/)
  assert.match(html, /Washington Nationals/)
  assert.doesNotMatch(html, /Publication exceptions/)
})

test('network and malformed-contract states fail closed without rendering fake groups', () => {
  const invalid = getLeagueTeamStateListingView({})
  for (const props of [
    { view: invalid, loading: true },
    { view: invalid, error: 'raw exception text' },
    { view: invalid },
  ]) {
    const html = render(React.createElement(LeagueTeamStateLandscape, props))
    assert.doesNotMatch(html, />Fresh</)
    assert.doesNotMatch(html, /raw exception text/)
    assert.doesNotMatch(html, /30 MLB clubs · grouped by published Team State/)
  }
})

test('retained league Team State data renders the stale notice and retry affordance', () => {
  const retry = () => {}
  const view = getLeagueTeamStateListingView(makeLeagueTeamStateListing())
  const html = render(React.createElement(LeagueTeamStateLandscape, {
    view,
    staleWithError: true,
    onRetry: retry,
  }))

  assert.match(html, /Refresh delayed/)
  assert.match(html, /showing last loaded data from Aug 14\./)
  assert.match(html, />Retry</)
  assert.match(html, /Arizona Diamondbacks/)
})

test('Dashboard has one H1, one listing-owned Data-through stamp, primary state before secondary context, and no generated timestamp wall', () => {
  const leagueTeamStates = makeLeagueTeamStateListing()
  const data = {
    roles: { counts: { late_high_leverage: 1 }, order: ['late_high_leverage'], total: 1 },
    freshness: { data_through: '2026-08-13', is_current: true },
  }
  const html = render(React.createElement(DashboardView, { data, leagueTeamStates }))
  const text = visibleText(html)
  assert.equal((html.match(/<h1/g) || []).length, 1)
  assert.equal((text.match(/Data through/g) || []).length, 1)
  assert.match(html, /dateTime="2026-08-14"/)
  assert.doesNotMatch(html, /dateTime="2026-08-13"/)
  assert.ok(text.indexOf('Current Bullpen State') < text.indexOf('Usage Roles'))
  assert.equal(/Generated|Published at|Last checked/.test(text), false)
})

test('Dashboard keeps backend Storylines optional and ahead of the governed league landscape', () => {
  const listing = makeLeagueTeamStateListing()
  const withoutStories = render(React.createElement(DashboardView, { data: {}, leagueTeamStates: listing }))
  assert.doesNotMatch(withoutStories, /Storylines/)

  const withStories = render(React.createElement(DashboardView, {
    data: { landscape: { storylines: ['Backend-authored league observation.'] } },
    leagueTeamStates: listing,
  }))
  assert.ok(withStories.indexOf('Storylines') < withStories.indexOf('Current Bullpen State'))
  assert.match(withStories, /Backend-authored league observation\./)
  assert.doesNotMatch(withStories, /Most of the league|lead the league/)
})
