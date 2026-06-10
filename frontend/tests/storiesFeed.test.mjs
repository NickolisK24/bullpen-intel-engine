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

const { StoriesView } = await server.ssrLoadModule('/src/components/stories/Stories.jsx')
const { getStoryFeed, filterStoryFeed, getFilterCounts, STORY_FILTERS, FEED_EMPTY_COPY } =
  await server.ssrLoadModule('/src/components/stories/storiesFeedView.js')
const { default: Sidebar } = await server.ssrLoadModule('/src/components/Sidebar.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

// League dashboard payload shaped like /api/bullpen/dashboard.
const dashboard = {
  context: {
    health: { state: 'strained', label: 'Several bullpens are working through heavy recent usage.', reasons: [] },
    metrics: { total_relievers: 64, available: 38, monitor: 14, restricted: 9, pct_available: 59, pct_restricted: 14 },
    confidence: 'high',
  },
  landscape: {
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
}

const observations = {
  contractState: 'available',
  observations: [
    { family: 'workload_pressure', severity: 'elevated', title: 'x', summary: 'y' },
    { family: 'trust', severity: 'monitor', title: 'x', summary: 'y' },
  ],
}

// ── Feed view-model ─────────────────────────────────────────────────────────

test('the feed reuses the Today stories and adds browse categories', () => {
  const feed = getStoryFeed(dashboard, observations)
  assert.ok(feed.hasStories)
  const categories = new Set(feed.items.map(item => item.category))
  assert.ok(categories.has('stressed'))
  assert.ok(categories.has('rested'))
  assert.ok(categories.has('watch'))
  assert.ok(categories.has('league'))
  for (const item of feed.items) {
    if (item.teamId != null) {
      assert.ok(item.abbr, `team story missing abbr: ${item.title}`)
      assert.ok(item.teamName, `team story missing teamName: ${item.title}`)
    }
  }
})

test('filters slice the feed by lane and the counts add up', () => {
  const feed = getStoryFeed(dashboard, observations)
  const counts = getFilterCounts(feed.items)
  assert.equal(counts.all, feed.items.length)
  assert.equal(
    counts.stressed + counts.rested + counts.watch + counts.league,
    counts.all,
  )
  for (const { key } of STORY_FILTERS) {
    const sliced = filterStoryFeed(feed.items, key)
    assert.equal(sliced.length, counts[key])
    if (key !== 'all') {
      assert.ok(sliced.every(item => item.category === key), `mixed lane in ${key}`)
    }
  }
})

test('every feed story keeps a valid existing destination', () => {
  const feed = getStoryFeed(dashboard, observations)
  for (const item of feed.items) {
    assert.ok(
      item.href.startsWith('/bullpen?') || item.href === '/dashboard' || item.href === '/trust',
      `unexpected destination: ${item.href}`,
    )
  }
})

// ── Page rendering ──────────────────────────────────────────────────────────

test('the stories page renders header, framing, compact top story, and league cards', () => {
  const html = render(React.createElement(StoriesView, { dashboard, observations }))
  assert.ok(htmlIncludes(html, 'STORIES'))
  assert.ok(htmlIncludes(html, 'The bullpen stories BaseballOS is watching today'))
  assert.ok(htmlIncludes(html, 'Observations, not predictions.'))
  // The lede is a compact Top Story module carrying the Today flagship.
  assert.ok(htmlIncludes(html, 'Top Story'))
  assert.ok(htmlIncludes(html, 'most constrained bullpen today'))
  assert.ok(htmlIncludes(html, 'Step inside the MIL pen'))
  // League intelligence cards remain, linking as they do from Today.
  for (const title of ['Most Stressed Bullpen', 'Most Rested Bullpen', 'Biggest Trend', 'Bullpen To Watch']) {
    assert.ok(htmlIncludes(html, title), `missing card: ${title}`)
  }
})

test('stories is the feed, not a second homepage', () => {
  const html = render(React.createElement(StoriesView, { dashboard, observations }))
  // No giant Today hero: no Why It Matters box, no hero chips, no hero CTAs.
  assert.ok(!htmlIncludes(html, 'Why It Matters'))
  assert.ok(!htmlIncludes(html, 'Rested &amp; Ready'))
  assert.ok(!htmlIncludes(html, 'Browse every bullpen'))
  // No rankings on the feed.
  assert.ok(!htmlIncludes(html, 'Bullpen Rankings'))
  assert.ok(!htmlIncludes(html, 'Top Bullpen Health'))
  // Filters sit with the feed, ahead of the demoted league strip.
  const filterIndex = html.indexOf('Story filters')
  const feedCardIndex = html.indexOf('box score looks calm')
  const leagueStripIndex = html.indexOf('Around The League')
  assert.ok(filterIndex >= 0 && feedCardIndex >= 0 && leagueStripIndex >= 0)
  assert.ok(filterIndex < feedCardIndex, 'filters should come before the feed cards')
  assert.ok(feedCardIndex < leagueStripIndex, 'the feed should come before the league strip')
})

test('the feed renders story cards with club identity and filter pills with counts', () => {
  const html = render(React.createElement(StoriesView, { dashboard, observations }))
  assert.ok(htmlIncludes(html, 'The Story Feed'))
  assert.ok(htmlIncludes(html, 'TOR · Toronto Blue Jays'))
  assert.ok(htmlIncludes(html, 'Around the league'))
  for (const { label } of STORY_FILTERS) {
    assert.ok(htmlIncludes(html, label), `missing filter: ${label}`)
  }
})

test('each filter lane renders only its stories', () => {
  const stressed = render(React.createElement(StoriesView, { dashboard, observations, initialFilter: 'stressed' }))
  assert.ok(htmlIncludes(stressed, 'New York Mets'))
  assert.ok(!htmlIncludes(stressed, 'TOR · Toronto Blue Jays'))

  const rested = render(React.createElement(StoriesView, { dashboard, observations, initialFilter: 'rested' }))
  assert.ok(htmlIncludes(rested, 'Washington Nationals'))
  assert.ok(!htmlIncludes(rested, 'New York Mets pen'))

  const watch = render(React.createElement(StoriesView, { dashboard, observations, initialFilter: 'watch' }))
  assert.ok(htmlIncludes(watch, 'TOR · Toronto Blue Jays'))

  const league = render(React.createElement(StoriesView, { dashboard, observations, initialFilter: 'league' }))
  assert.ok(htmlIncludes(league, 'Bullpen work is running heavy around the league'))
  assert.ok(!htmlIncludes(league, 'TOR · Toronto Blue Jays'))
})

test('an empty lane explains itself instead of going blank', () => {
  const noWatch = {
    ...dashboard,
    landscape: { ...dashboard.landscape, monitoring_concentration: [] },
  }
  const html = render(React.createElement(StoriesView, { dashboard: noWatch, observations: null, initialFilter: 'watch' }))
  assert.ok(htmlIncludes(html, FEED_EMPTY_COPY.watch))
})

test('loading and error states render without data', () => {
  const loadingHtml = render(React.createElement(StoriesView, { dashboard: null, loading: true }))
  assert.ok(htmlIncludes(loadingHtml, 'bullpen stories'))
  const errorHtml = render(React.createElement(StoriesView, { dashboard: null, error: 'API 500' }))
  assert.ok(htmlIncludes(errorHtml, 'API 500'))
})

// ── Navigation ──────────────────────────────────────────────────────────────

test('the sidebar carries Stories right after Today', () => {
  const html = render(React.createElement(Sidebar))
  assert.ok(htmlIncludes(html, 'href="/stories"'))
  assert.ok(htmlIncludes(html, 'Stories'))
  assert.ok(html.indexOf('Today') < html.indexOf('Stories'))
  assert.ok(html.indexOf('Stories') < html.indexOf('Dashboard'))
})

// ── Language guardrails ─────────────────────────────────────────────────────

test('the stories page stays in baseball language', () => {
  const html = render(React.createElement(StoriesView, { dashboard, observations })).toLowerCase()
  for (const term of [
    'availability inventory', 'readiness limitations', 'limitations are present',
    'snapshot', 'governance', 'data_state', 'fail closed',
    'recommended', 'recommendation', 'betting', 'parlay', 'injury',
    'will collapse', 'guaranteed',
  ]) {
    assert.ok(!html.includes(term), `leaked: ${term}`)
  }
})
