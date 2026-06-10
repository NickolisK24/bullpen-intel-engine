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

const { HomeView } = await server.ssrLoadModule('/src/components/home/Home.jsx')
const {
  getHeroStory,
  getLeagueCards,
  getBullpenStories,
  getRankingsPreview,
  getTeamExplorerView,
  getMastheadView,
  STORIES_FALLBACK,
} = await server.ssrLoadModule('/src/components/home/homeIntelligenceView.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

// League dashboard payload shaped like /api/bullpen/dashboard.
const dashboard = {
  capability: 'bullpen_dashboard',
  ranking_applied: false,
  selection_made: false,
  context: {
    health: { state: 'strained', label: 'Several bullpens are working through heavy recent usage.', reasons: [] },
    metrics: {
      total_relievers: 64, available: 38, monitor: 14, restricted: 9,
      pct_available: 59, pct_restricted: 14,
    },
    confidence: 'high',
  },
  roles: { order: [], counts: {}, total: 64 },
  landscape: {
    capability: 'tonights_bullpen_landscape',
    reference_date: '2026-06-06',
    teams_evaluated: 8,
    games: { available: true, data_state: 'historical', today_count: 0, as_of_date: '2026-06-05', as_of_count: 6, is_today: false, message: null },
    constrained_bullpens: [
      { team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL', total_relievers: 8, available: 2, monitor: 2, restricted: 4, pct_available: 25, pct_restricted: 50 },
      { team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM', total_relievers: 8, available: 3, monitor: 2, restricted: 3, pct_available: 37, pct_restricted: 37 },
    ],
    available_bullpens: [
      { team_id: 120, team_name: 'Washington Nationals', team_abbreviation: 'WSH', total_relievers: 8, available: 6, monitor: 1, restricted: 1, pct_available: 75, pct_restricted: 12 },
      { team_id: 137, team_name: 'San Francisco Giants', team_abbreviation: 'SF', total_relievers: 8, available: 5, monitor: 2, restricted: 1, pct_available: 62, pct_restricted: 12 },
    ],
    monitoring_concentration: [
      { team_id: 141, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR', total_relievers: 8, available: 4, monitor: 4, restricted: 0, pct_available: 50, pct_restricted: 0 },
    ],
    notes: [],
  },
  freshness: { data_through: '2026-06-05', last_successful_sync: '2026-06-06T08:00:00Z', is_current: true, sync_status: 'success' },
  availability_summary: { statuses: {} },
}

const teams = [
  { team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL', pitcher_count: 8 },
  { team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM', pitcher_count: 8 },
  { team_id: 141, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR', pitcher_count: 8 },
  { team_id: 120, team_name: 'Washington Nationals', team_abbreviation: 'WSH', pitcher_count: 8 },
  { team_id: 112, team_name: 'Chicago Cubs', team_abbreviation: 'CHC', pitcher_count: 7 },
]

const observations = {
  contractState: 'available',
  observations: [
    {
      observation_id: 'obs-1', observation_type: 'workload_pressure', family: 'workload_pressure',
      severity: 'elevated', title: 'Bullpen workload pressure is elevated.',
      summary: 'Recent appearance density is elevated across several tracked bullpens.',
    },
  ],
}

// ── Hero story ──────────────────────────────────────────────────────────────

test('the hero leads with the most constrained bullpen', () => {
  const hero = getHeroStory(dashboard)
  assert.ok(hero.hasStory)
  assert.equal(hero.angle, 'stress')
  assert.equal(hero.team.teamName, 'Milwaukee Brewers')
  assert.ok(/4 of the pen/.test(hero.observation))
  assert.ok(hero.whyItMatters.length > 0)
})

test('the hero headline states what the data shows, not a forecast', () => {
  const hero = getHeroStory(dashboard)
  assert.match(hero.headline, /have baseball's most constrained bullpen today/)
  // No drama, no fortune-telling.
  for (const phrase of [/running out/i, /collapse/i, /will\s/i, /guarantee/i, /doomed/i]) {
    assert.ok(!phrase.test(hero.headline), `headline leaked: ${phrase}`)
  }
})

test('the hero falls back to the heaviest watch list, then the most rested pen', () => {
  const noStress = {
    ...dashboard,
    landscape: { ...dashboard.landscape, constrained_bullpens: [] },
  }
  const watchHero = getHeroStory(noStress)
  assert.equal(watchHero.angle, 'concentration')
  assert.equal(watchHero.team.teamName, 'Toronto Blue Jays')
  assert.match(watchHero.headline, /most concentrated bullpen workload today/)

  const restOnly = {
    ...dashboard,
    landscape: { ...dashboard.landscape, constrained_bullpens: [], monitoring_concentration: [] },
  }
  const restHero = getHeroStory(restOnly)
  assert.equal(restHero.angle, 'rest')
  assert.equal(restHero.team.teamName, 'Washington Nationals')
  assert.match(restHero.headline, /most rested bullpen into today/)
})

test('a quiet league day still produces a hero story', () => {
  const quiet = getHeroStory({})
  assert.equal(quiet.hasStory, false)
  assert.equal(quiet.angle, 'quiet')
  assert.ok(quiet.headline.length > 0)
  assert.ok(quiet.whyItMatters.length > 0)
})

// ── League intelligence cards ───────────────────────────────────────────────

test('all four league intelligence cards are derived from the landscape', () => {
  const cards = getLeagueCards(dashboard)
  const byKey = Object.fromEntries(cards.map(card => [card.key, card]))
  assert.equal(cards.length, 4)
  assert.equal(byKey['most-stressed'].team.abbr, 'MIL')
  assert.equal(byKey['most-rested'].team.abbr, 'WSH')
  assert.equal(byKey['bullpen-to-watch'].team.abbr, 'TOR')
  // Two constrained clubs → the trend card reads league-wide stress.
  assert.equal(byKey['biggest-trend'].stat, '2')
  assert.match(byKey['biggest-trend'].line, /Stress is not isolated to one club today/)
})

test('card copy reads like a hook, not a metric summary', () => {
  const cards = getLeagueCards(dashboard)
  const byKey = Object.fromEntries(cards.map(card => [card.key, card]))
  assert.equal(byKey['most-stressed'].line,
    'More arms need a breather here than anywhere else in baseball.')
  assert.equal(byKey['most-rested'].line,
    'This group brings the cleanest availability picture into today.')
  assert.equal(byKey['bullpen-to-watch'].line,
    'The surface is not alarming yet, but the recent workload is worth watching.')
})

test('cards degrade to quiet copy when the landscape is empty', () => {
  const cards = getLeagueCards({})
  assert.equal(cards.length, 4)
  for (const card of cards) {
    assert.equal(card.team, null)
    assert.ok(card.line.length > 0)
    assert.ok(card.href)
  }
})

// ── Bullpen stories ─────────────────────────────────────────────────────────

test('stories are derived from the landscape without repeating the hero club', () => {
  const stories = getBullpenStories(dashboard, null)
  assert.ok(stories.hasStories)
  const titles = stories.items.map(story => story.title).join(' | ')
  // Hero features Milwaukee; the stories pick up the other clubs.
  assert.ok(!/Milwaukee/.test(titles))
  assert.ok(/Toronto Blue Jays/.test(titles))
  assert.ok(/New York Mets/.test(titles))
  assert.ok(/Washington Nationals/.test(titles))
})

test('story titles read like a baseball writer, not a system', () => {
  const stories = getBullpenStories(dashboard, null)
  const titles = stories.items.map(story => story.title)
  // Toronto (4 monitor, 0 restricted) is the hidden-workload shape.
  assert.ok(titles.includes('The Toronto Blue Jays box score looks calm. The bullpen does not.'))
  assert.ok(titles.includes('A thin late-inning margin is forming for the New York Mets'))
})

test('governed observations are retold in editorial language, never verbatim', () => {
  const stories = getBullpenStories(dashboard, observations)
  const titles = stories.items.map(story => story.title)
  assert.ok(titles.includes('Bullpen work is running heavy around the league'))
  assert.ok(!titles.includes('Bullpen workload pressure is elevated.'))
})

test('observation families without an editorial translation are left off the page', () => {
  const unknownFamily = {
    contractState: 'available',
    observations: [
      { family: 'mystery_family', severity: 'monitor', title: 'Raw system text.', summary: 'Raw system summary.' },
    ],
  }
  const stories = getBullpenStories(dashboard, unknownFamily)
  const text = stories.items.map(story => `${story.title} ${story.body}`).join(' ')
  assert.ok(!text.includes('Raw system'))
})

test('unsafe or empty observation feeds are ignored', () => {
  const unsafe = { contractState: 'unavailable', observations: [{ title: 'X', summary: 'Y', family: 'trust', severity: 'monitor' }] }
  const stories = getBullpenStories(dashboard, unsafe)
  assert.ok(!stories.items.some(story => story.title === 'X'))
})

test('story list is capped and falls back gracefully', () => {
  const stories = getBullpenStories(dashboard, observations)
  assert.ok(stories.items.length <= 6)
  const empty = getBullpenStories({}, null)
  assert.equal(empty.hasStories, false)
  assert.equal(empty.fallback, STORIES_FALLBACK)
})

// ── Rankings preview ────────────────────────────────────────────────────────

test('rankings preview runs live boards from counts and marks movement boards as placeholders', () => {
  const rankings = getRankingsPreview(dashboard)
  const byKey = Object.fromEntries(rankings.boards.map(board => [board.key, board]))
  assert.equal(rankings.boards.length, 4)
  assert.equal(byKey.health.entries[0].abbr, 'WSH')
  assert.equal(byKey.health.entries[0].stat, '6/8 rested')
  assert.equal(byKey.stress.entries[0].abbr, 'MIL')
  assert.ok(byKey.risers.placeholder)
  assert.ok(byKey.fallers.placeholder)
  assert.ok(byKey.risers.placeholderCopy.length > 0)
})

test('rankings carry framing that separates bullpen shape from team quality', () => {
  const rankings = getRankingsPreview(dashboard)
  assert.match(rankings.framing, /workload and availability signals/)
  assert.match(rankings.framing, /not a talent ranking/)
  assert.match(rankings.updateNote, /update as new completed games/)
})

// ── Team explorer ───────────────────────────────────────────────────────────

test('the team explorer lists every tracked club with board deep-links', () => {
  const explorer = getTeamExplorerView(teams, dashboard)
  assert.equal(explorer.count, 5)
  const cubs = explorer.items.find(team => team.abbr === 'CHC')
  assert.ok(cubs)
  assert.ok(cubs.href.includes('/bullpen?'))
  assert.ok(cubs.href.includes('team=CHC'))
  assert.equal(cubs.tag, null)
})

test('clubs in the landscape carry story hooks, with stress taking priority', () => {
  const explorer = getTeamExplorerView(teams, dashboard)
  const byAbbr = Object.fromEntries(explorer.items.map(team => [team.abbr, team]))
  assert.equal(byAbbr.MIL.tag.label, 'Running Hot')
  assert.equal(byAbbr.TOR.tag.label, 'Watch List')
  assert.equal(byAbbr.WSH.tag.label, 'Well Rested')
})

test('clubs carrying storylines lead the explorer; the rest follow alphabetically', () => {
  const explorer = getTeamExplorerView(teams, dashboard)
  assert.deepEqual(
    explorer.items.map(team => team.abbr),
    ['MIL', 'NYM', 'TOR', 'WSH', 'CHC'],
  )
})

// ── Masthead ────────────────────────────────────────────────────────────────

test('the masthead reports the data window in plain language', () => {
  const masthead = getMastheadView(dashboard, new Date('2026-06-06T12:00:00Z'))
  assert.ok(/Built from completed games through Jun 5, 2026/.test(masthead.dataLine))
  assert.ok(masthead.editionDate.includes('2026'))
  const cold = getMastheadView({}, new Date('2026-06-06T12:00:00Z'))
  assert.equal(cold.dataLine, 'Waiting on the first completed games')
})

// ── Rendering & placement ───────────────────────────────────────────────────

test('the homepage renders all five sections in story-first order', () => {
  const html = render(React.createElement(HomeView, { dashboard, teams, observations }))
  const sections = [
    'What BaseballOS Sees Today',
    'Most Stressed Bullpen',
    'Bullpen Stories',
    'Bullpen Rankings',
    'Explore Every Bullpen',
  ]
  let lastIndex = -1
  for (const section of sections) {
    const index = html.indexOf(section)
    assert.ok(index >= 0, `missing section: ${section}`)
    assert.ok(index > lastIndex, `out of order: ${section}`)
    lastIndex = index
  }
})

test('the hero renders the flagship observation with Why It Matters', () => {
  const html = render(React.createElement(HomeView, { dashboard, teams, observations }))
  assert.ok(htmlIncludes(html, 'Why It Matters'))
  assert.ok(htmlIncludes(html, 'Milwaukee Brewers'))
  assert.ok(htmlIncludes(html, 'most constrained bullpen today'))
  assert.ok(htmlIncludes(html, 'Step inside the MIL pen'))
})

test('the rankings framing is visible on the page', () => {
  const html = render(React.createElement(HomeView, { dashboard, teams, observations }))
  assert.ok(htmlIncludes(html, 'not a talent ranking'))
  assert.ok(htmlIncludes(html, 'Rankings update as new completed games enter the system.'))
})

test('the homepage keeps a path to the original dashboard', () => {
  const html = render(React.createElement(HomeView, { dashboard, teams, observations }))
  assert.ok(htmlIncludes(html, 'href="/dashboard"'))
})

test('loading and error states render without data', () => {
  const loadingHtml = render(React.createElement(HomeView, { dashboard: null, teams: null, loading: true }))
  assert.ok(htmlIncludes(loadingHtml, 'bullpen report'))
  const errorHtml = render(React.createElement(HomeView, { dashboard: null, teams: null, error: 'API 500' }))
  assert.ok(htmlIncludes(errorHtml, 'API 500'))
})

// ── Guardrails: language stays descriptive and human ───────────────────────

test('the homepage avoids advisory, ranking, and prediction language', () => {
  const html = render(React.createElement(HomeView, { dashboard, teams, observations })).toLowerCase()
  for (const term of [
    'should use', 'best option', 'best bullpen', 'worst bullpen', 'best arm',
    'recommended', 'recommendation', 'strongest bullpen', 'weakest bullpen',
    'expected to win', 'likely to win', 'win probability', 'odds', 'projection',
    'prediction', 'preferred arm', 'will collapse', 'guaranteed', 'bet on',
    'betting', 'parlay', 'moneyline', 'injury', 'manager should',
  ]) {
    assert.ok(!html.includes(term), `leaked term: ${term}`)
  }
})

test('the homepage avoids raw system phrasing', () => {
  const html = render(React.createElement(HomeView, { dashboard, teams, observations })).toLowerCase()
  for (const term of [
    'availability inventory', 'readiness limitations', 'limitations are present',
    'trusted snapshot', 'snapshot', 'data state', 'data_state', 'contract',
    'fail closed', 'fail_closed', 'governance',
  ]) {
    assert.ok(!html.includes(term), `leaked system phrasing: ${term}`)
  }
})
