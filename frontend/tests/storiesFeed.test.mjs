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
const {
  DEFAULT_STORY_FILTER,
  FEED_EMPTY_COPY,
  FEED_EMPTY_SUPPORT_COPY,
  STORY_FILTERS,
  filterStoryFeed,
  getActiveStoryFilterLabel,
  getFeedEmptyState,
  getFilterCounts,
  getStoryFeed,
  getStoryFilterOption,
  normalizeStoryFilter,
} =
  await server.ssrLoadModule('/src/components/stories/storiesFeedView.js')
const { getHeroStory, getTodayWatchItems } =
  await server.ssrLoadModule('/src/components/home/homeIntelligenceView.js')
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
    {
      family: 'workload_pressure',
      severity: 'elevated',
      title: 'x',
      summary: 'y',
      evidence: [
        {
          label: 'Elevated workload record count',
          value: 3,
          source: 'test_observation_feed',
          source_type: 'trusted_platform_state',
          freshness_status: 'current',
        },
      ],
      freshness: { status: 'current' },
      confidence: { status: 'medium' },
    },
    {
      family: 'trust',
      severity: 'significant',
      title: 'x',
      summary: 'y',
      evidence: [
        {
          label: 'Trust limitation state',
          value: 'represented',
          source: 'test_observation_feed',
          source_type: 'trusted_platform_state',
          freshness_status: 'current',
        },
      ],
      freshness: { status: 'current' },
      confidence: { status: 'medium' },
    },
  ],
}

// ── Feed view-model ─────────────────────────────────────────────────────────

test('the feed derives deeper observations and adds browse categories', () => {
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

test('the feed is deeper than Today and does not repeat the flagship club', () => {
  const hero = getHeroStory(dashboard)
  const today = getTodayWatchItems(dashboard)
  const feed = getStoryFeed(dashboard, observations)
  assert.ok(feed.items.length > today.items.length)
  assert.ok(!feed.items.some(item => item.teamId === hero.team.teamId))
  assert.ok(!feed.items.some(item => /Milwaukee Brewers/.test(`${item.title} ${item.body}`)))
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

test('filter metadata carries concise descriptions and active labels', () => {
  for (const { key, description } of STORY_FILTERS) {
    const option = getStoryFilterOption(key)
    assert.equal(option.description, description)
    assert.equal(option.description.split('.').filter(Boolean).length, 1)
    assert.ok(getActiveStoryFilterLabel(key, 2).includes('(2)'))
  }
  assert.equal(normalizeStoryFilter('unknown-lane'), DEFAULT_STORY_FILTER)
  assert.equal(getFeedEmptyState('unknown-lane').resetFilter, DEFAULT_STORY_FILTER)
})

test('missing and unknown categories degrade gracefully', () => {
  const feed = getStoryFeed(dashboard, observations)
  const withUnknown = [
    ...feed.items,
    { title: 'Unlabeled bullpen note' },
    { title: 'Unexpected bullpen note', category: 'mystery' },
  ]
  const counts = getFilterCounts(withUnknown)
  assert.equal(counts.all, withUnknown.length)
  assert.equal(
    counts.stressed + counts.rested + counts.watch + counts.league,
    feed.items.length,
  )
  assert.equal(filterStoryFeed(withUnknown, 'mystery').length, withUnknown.length)
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

test('the stories page renders as a feed-first surface beyond Today', () => {
  const html = render(React.createElement(StoriesView, { dashboard, observations }))
  assert.ok(htmlIncludes(html, 'STORIES'))
  assert.ok(htmlIncludes(html, 'What else BaseballOS is seeing today'))
  assert.ok(htmlIncludes(html, 'Observations, not predictions.'))
  assert.ok(htmlIncludes(html, 'Beyond Today'))
  assert.ok(htmlIncludes(html, 'What Else BaseballOS Is Seeing'))
  assert.ok(htmlIncludes(html, 'bullpen storylines in play today'))
  assert.ok(!htmlIncludes(html, 'Top Story'))
  assert.ok(!htmlIncludes(html, 'stretched thinner than any in baseball today'))
  assert.ok(!htmlIncludes(html, 'Step inside the MIL pen'))
})

test('stories is the feed, not a second homepage', () => {
  const html = render(React.createElement(StoriesView, { dashboard, observations }))
  // No giant Today hero: no Why It Matters box, no hero chips, no hero CTAs.
  assert.ok(!htmlIncludes(html, 'Why It Matters'))
  assert.ok(!htmlIncludes(html, 'Rested &amp; Ready'))
  assert.ok(!htmlIncludes(html, 'Browse every bullpen'))
  // No rankings on the feed.
  assert.ok(!htmlIncludes(html, 'Rankings Preview'))
  assert.ok(!htmlIncludes(html, 'Top Bullpen Health'))
  // No duplicated Today league card strip.
  for (const title of ['Highest Bullpen Pressure', 'Widest Recovery Window', 'Biggest Trend']) {
    assert.ok(!htmlIncludes(html, title), `duplicated card leaked: ${title}`)
  }
  assert.ok(!htmlIncludes(html, 'Around The League'))
  // The scope row leads into filters and feed cards.
  const scopeIndex = html.indexOf('Beyond Today')
  const filterIndex = html.indexOf('Story filters')
  const feedCardIndex = html.indexOf('box score looks calm')
  assert.ok(scopeIndex >= 0 && filterIndex >= 0 && feedCardIndex >= 0)
  assert.ok(scopeIndex < filterIndex, 'the feed scope should introduce the filters')
  assert.ok(filterIndex < feedCardIndex, 'filters should come before the feed cards')
})

test('the feed renders story cards with club identity and filter pills with counts', () => {
  const html = render(React.createElement(StoriesView, { dashboard, observations }))
  const counts = getFilterCounts(getStoryFeed(dashboard, observations).items)
  assert.ok(htmlIncludes(html, 'The Story Feed'))
  assert.ok(htmlIncludes(html, 'TOR · Toronto Blue Jays'))
  assert.ok(htmlIncludes(html, 'Around the league'))
  assert.ok(htmlIncludes(html, getActiveStoryFilterLabel('all', counts.all)))
  for (const { key, label, description } of STORY_FILTERS) {
    assert.ok(htmlIncludes(html, label), `missing filter: ${label}`)
    assert.ok(htmlIncludes(html, `(${counts[key]})`), `missing count for ${label}`)
    assert.ok(htmlIncludes(html, description), `missing description for ${label}`)
  }
})

test('each filter lane renders only its stories', () => {
  const counts = getFilterCounts(getStoryFeed(dashboard, observations).items)
  const stressed = render(React.createElement(StoriesView, { dashboard, observations, initialFilter: 'stressed' }))
  assert.ok(htmlIncludes(stressed, getActiveStoryFilterLabel('stressed', counts.stressed)))
  assert.ok(htmlIncludes(stressed, 'New York Mets'))
  assert.ok(!htmlIncludes(stressed, 'TOR · Toronto Blue Jays'))

  const rested = render(React.createElement(StoriesView, { dashboard, observations, initialFilter: 'rested' }))
  assert.ok(htmlIncludes(rested, getActiveStoryFilterLabel('rested', counts.rested)))
  assert.ok(htmlIncludes(rested, 'Washington Nationals'))
  assert.ok(!htmlIncludes(rested, 'New York Mets'))

  const watch = render(React.createElement(StoriesView, { dashboard, observations, initialFilter: 'watch' }))
  assert.ok(htmlIncludes(watch, getActiveStoryFilterLabel('watch', counts.watch)))
  assert.ok(htmlIncludes(watch, 'TOR · Toronto Blue Jays'))

  const league = render(React.createElement(StoriesView, { dashboard, observations, initialFilter: 'league' }))
  assert.ok(htmlIncludes(league, getActiveStoryFilterLabel('league', counts.league)))
  assert.ok(htmlIncludes(league, 'The workload underneath is worth watching'))
  assert.ok(!htmlIncludes(league, 'Workload is collecting below the headline'))
  assert.ok(!htmlIncludes(league, 'TOR · Toronto Blue Jays'))
})

test('empty filter lanes explain themselves and offer a reset', () => {
  const sparseByFilter = {
    stressed: {
      ...dashboard,
      landscape: { ...dashboard.landscape, constrained_bullpens: [] },
    },
    rested: {
      ...dashboard,
      landscape: { ...dashboard.landscape, available_bullpens: [] },
    },
    watch: {
      ...dashboard,
      landscape: { ...dashboard.landscape, monitoring_concentration: [] },
    },
    league: {
      ...dashboard,
      context: {
        ...dashboard.context,
        metrics: { total_relievers: 0, available: 0, monitor: 0, restricted: 0, pct_available: 0, pct_restricted: 0 },
      },
    },
  }
  const observationsByFilter = {
    stressed: null,
    rested: null,
    watch: null,
    league: null,
  }

  for (const key of ['stressed', 'rested', 'watch', 'league']) {
    const html = render(React.createElement(StoriesView, {
      dashboard: sparseByFilter[key],
      observations: observationsByFilter[key],
      initialFilter: key,
    }))
    assert.ok(htmlIncludes(html, FEED_EMPTY_COPY[key]), `missing empty copy for ${key}`)
    assert.ok(htmlIncludes(html, FEED_EMPTY_SUPPORT_COPY), `missing support copy for ${key}`)
    assert.ok(htmlIncludes(html, 'Show All Stories'), `missing reset CTA for ${key}`)
    assert.ok(htmlIncludes(html, 'data-reset-filter="all"'), `reset CTA should target all for ${key}`)
  }
})

test('all-feed empty state renders correctly when no stories are active', () => {
  const emptyDashboard = {
    ...dashboard,
    context: {
      ...dashboard.context,
      metrics: { total_relievers: 0, available: 0, monitor: 0, restricted: 0, pct_available: 0, pct_restricted: 0 },
    },
    landscape: {
      ...dashboard.landscape,
      constrained_bullpens: [],
      available_bullpens: [],
      monitoring_concentration: [],
    },
  }
  const html = render(React.createElement(StoriesView, {
    dashboard: emptyDashboard,
    observations: null,
    initialFilter: 'all',
  }))
  assert.ok(htmlIncludes(html, FEED_EMPTY_COPY.all))
  assert.ok(htmlIncludes(html, 'All Stories (0)'))
  assert.ok(htmlIncludes(html, 'Show All Stories'))
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
    // Mechanical phrasing the language layer exists to prevent.
    'register as', 'workload-restricted', 'availability context',
    'carrying workload concentration', 'limited recovery window',
  ]) {
    assert.ok(!html.includes(term), `leaked: ${term}`)
  }
})
