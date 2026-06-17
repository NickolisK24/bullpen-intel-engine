import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { readFileSync } from 'node:fs'
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
  FOUR_BEAT_STORIES_FALLBACK,
  STORY_FILTERS,
  filterStoryFeed,
  getActiveStoryFilterLabel,
  getFourBeatStoryFeed,
  getFeedEmptyState,
  getFilterCounts,
  getStoryFilterOption,
  normalizeStoryFilter,
} =
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

const fourBeatDashboard = {
  ...dashboard,
  four_beat_stories: {
    capability: 'four_beat_story_template_v1',
    enabled: true,
    items: [
      {
        story_id: '141:stress_transfer',
        rule_key: 'stress_transfer',
        rule_label: 'Stress Transfer',
        team_id: 141,
        team_name: 'Toronto Blue Jays',
        team_abbreviation: 'TOR',
        kicker: 'Stress Transfer',
        tone: 'stress',
        category: 'stressed',
        title: 'The Toronto Blue Jays are transferring bullpen pressure onto a smaller group tonight.',
        body: 'The top 3 arms have carried 73% of recent relief pitches. That combination usually means the next close innings lean harder on the remaining clean late-inning path. Tonight, Chad Green is the clean Trust Arm path.',
        href: '/bullpen?view=board&team=TOR&source=four-beat-stories',
        cta: 'Open the team board',
        strength: 112,
        beats: [
          {
            key: 'signal',
            label: 'Signal',
            text: 'The Toronto Blue Jays are transferring bullpen pressure onto a smaller group tonight.',
          },
          {
            key: 'evidence',
            label: 'Evidence',
            text: 'The top 3 arms have carried 73% of recent relief pitches, while 2 of 8 bullpen arms are Available.',
          },
          {
            key: 'mechanism',
            label: 'Mechanism',
            text: 'That combination usually means the next close innings lean harder on the remaining clean late-inning path.',
          },
          {
            key: 'implication',
            label: 'Implication',
            text: 'Tonight, Chad Green is the clean Trust Arm path; 2 of 8 bullpen arms are clean options behind it.',
          },
        ],
      },
      {
        story_id: '120:pressure_distribution',
        rule_key: 'pressure_distribution',
        rule_label: 'Pressure Distribution',
        team_id: 120,
        team_name: 'Washington Nationals',
        team_abbreviation: 'WSH',
        kicker: 'Pressure Distribution',
        tone: 'rest',
        category: 'rested',
        title: 'The Washington Nationals have a broader bullpen path tonight.',
        body: 'Recent relief work has been spread across the group, leaving more clean ways through the late innings.',
        href: '/bullpen?view=board&team=WSH&source=four-beat-stories',
        cta: 'Open the team board',
        strength: 86,
        beats: [
          {
            key: 'signal',
            label: 'Signal',
            text: 'The Washington Nationals have a broader bullpen path tonight.',
          },
          {
            key: 'evidence',
            label: 'Evidence',
            text: 'Six bullpen arms have participated recently without one arm carrying the whole share.',
          },
          {
            key: 'mechanism',
            label: 'Mechanism',
            text: 'That shape gives the late innings more than one usable lane.',
          },
          {
            key: 'implication',
            label: 'Implication',
            text: 'The read is about distribution, not a team ranking.',
          },
        ],
      },
      {
        story_id: '137:workload_watch',
        rule_key: 'workload_watch',
        rule_label: 'Workload Watch',
        team_id: 137,
        team_name: 'San Francisco Giants',
        team_abbreviation: 'SF',
        kicker: 'Workload Watch',
        tone: 'watch',
        title: 'The San Francisco Giants are leaning on a familiar core.',
        body: 'The same relievers have carried the recent late-inning work.',
        href: '/bullpen?view=board&team=SF&source=four-beat-stories',
        cta: 'Open the team board',
        strength: 74,
        beats: [
          {
            key: 'signal',
            label: 'Signal',
            text: 'The San Francisco Giants are leaning on a familiar core.',
          },
          {
            key: 'evidence',
            label: 'Evidence',
            text: 'Three relievers account for most of the recent relief pitches.',
          },
          {
            key: 'mechanism',
            label: 'Mechanism',
            text: 'A narrow workload share can make the board look calm while the same arms keep appearing.',
          },
          {
            key: 'implication',
            label: 'Implication',
            text: 'The next useful read is whether clean support appears behind that group.',
          },
        ],
      },
      {
        story_id: 'league:context',
        rule_key: 'league_context',
        rule_label: 'League Context',
        team_id: null,
        team_name: null,
        team_abbreviation: null,
        kicker: 'League Context',
        tone: 'neutral',
        category: 'league',
        title: 'The league-wide bullpen picture is carrying mixed signals.',
        body: 'Some clubs have stress, some have room, and the feed separates those reads by lane.',
        href: '/dashboard',
        cta: 'See the league view',
        strength: 62,
        beats: [
          {
            key: 'signal',
            label: 'Signal',
            text: 'The league-wide bullpen picture is carrying mixed signals.',
          },
          {
            key: 'evidence',
            label: 'Evidence',
            text: 'Pressure, rest, and workload-watch stories all appear in the same feed.',
          },
          {
            key: 'mechanism',
            label: 'Mechanism',
            text: 'The lanes keep team-specific reads separate from the league picture.',
          },
          {
            key: 'implication',
            label: 'Implication',
            text: 'The full feed can stay browseable without returning to the old story path.',
          },
        ],
      },
    ],
  },
}

// ── Feed view-model ─────────────────────────────────────────────────────────

test('four-beat feed normalizes backend-authored stories and browse categories', () => {
  const feed = getFourBeatStoryFeed(fourBeatDashboard)

  assert.equal(feed.hasStories, true)
  assert.equal(feed.items.length, 4)
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
  assert.equal(feed.items[0].teamId, 141)
  assert.equal(feed.items[0].category, 'stressed')
  assert.equal(feed.items[0].beats.length, 4)
  assert.equal(feed.items[2].category, 'watch')
})

test('the live Stories path does not fetch observations or import the old story feed', () => {
  const storiesSource = readFileSync(new URL('../src/components/stories/Stories.jsx', import.meta.url), 'utf8')
  const feedSource = readFileSync(new URL('../src/components/stories/storiesFeedView.js', import.meta.url), 'utf8')

  assert.equal(storiesSource.includes('getBullpenObservations'), false)
  assert.equal(storiesSource.includes('observations.data'), false)
  assert.equal(storiesSource.includes('VITE_FOUR_BEAT_STORIES_ENABLED'), false)
  assert.equal(storiesSource.includes('getStoryFeed'), false)
  assert.equal(storiesSource.includes('StoryPathSwitch'), false)
  assert.equal(feedSource.includes('getBullpenStories'), false)
  assert.equal(feedSource.includes('export function getStoryFeed'), false)
})

test('filters slice the four-beat feed by lane and the counts add up', () => {
  const feed = getFourBeatStoryFeed(fourBeatDashboard)
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
  const feed = getFourBeatStoryFeed(fourBeatDashboard)
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

test('every four-beat feed story keeps a valid existing destination', () => {
  const feed = getFourBeatStoryFeed(fourBeatDashboard)
  for (const item of feed.items) {
    assert.ok(
      item.href.startsWith('/bullpen?') || item.href === '/dashboard' || item.href === '/trust',
      `unexpected destination: ${item.href}`,
    )
  }
})

// ── Page rendering ──────────────────────────────────────────────────────────

test('the stories page renders four-beat as the feed-first surface beyond Today', () => {
  const html = render(React.createElement(StoriesView, { dashboard: fourBeatDashboard }))
  assert.ok(htmlIncludes(html, 'STORIES'))
  assert.ok(htmlIncludes(html, 'What else BaseballOS is seeing today'))
  assert.ok(htmlIncludes(html, 'Descriptive bullpen notes.'))
  assert.ok(htmlIncludes(html, 'Beyond Today'))
  assert.ok(htmlIncludes(html, 'What Else BaseballOS Is Seeing'))
  assert.ok(htmlIncludes(html, 'bullpen storylines in play today'))
  assert.ok(htmlIncludes(html, 'Signal'))
  assert.ok(htmlIncludes(html, 'Evidence'))
  assert.ok(htmlIncludes(html, 'Mechanism'))
  assert.ok(htmlIncludes(html, 'Implication'))
  assert.ok(!htmlIncludes(html, 'Top Story'))
  assert.ok(!htmlIncludes(html, 'thinnest late-inning margin in baseball today'))
  assert.ok(!htmlIncludes(html, 'Step inside the MIL pen'))
})

test('four-beat stories render by default without a story-path switch', () => {
  const html = render(React.createElement(StoriesView, {
    dashboard: fourBeatDashboard,
  }))

  assert.ok(!htmlIncludes(html, 'aria-label="Story path"'))
  assert.ok(!htmlIncludes(html, 'Current'))
  assert.ok(!htmlIncludes(html, 'Four Beat'))
  assert.ok(htmlIncludes(html, 'Signal'))
  assert.ok(htmlIncludes(html, 'Evidence'))
  assert.ok(htmlIncludes(html, 'Mechanism'))
  assert.ok(htmlIncludes(html, 'Implication'))
  assert.ok(htmlIncludes(html, 'The Toronto Blue Jays are transferring bullpen pressure onto a smaller group tonight.'))
  assert.ok(htmlIncludes(html, 'That combination usually means'))
  assert.ok(!htmlIncludes(html, 'causes'))
  assert.ok(!htmlIncludes(html, '{team_name}'))
})

test('stories is the feed, not a second homepage', () => {
  const html = render(React.createElement(StoriesView, { dashboard: fourBeatDashboard }))
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
  const feedCardIndex = html.indexOf('transferring bullpen pressure')
  assert.ok(scopeIndex >= 0 && filterIndex >= 0 && feedCardIndex >= 0)
  assert.ok(scopeIndex < filterIndex, 'the feed scope should introduce the filters')
  assert.ok(filterIndex < feedCardIndex, 'filters should come before the feed cards')
})

test('the feed renders story cards with club identity and filter pills with counts', () => {
  const html = render(React.createElement(StoriesView, { dashboard: fourBeatDashboard }))
  const counts = getFilterCounts(getFourBeatStoryFeed(fourBeatDashboard).items)
  assert.ok(htmlIncludes(html, 'The Story Feed'))
  assert.ok(htmlIncludes(html, 'TOR · Toronto Blue Jays'))
  assert.ok(htmlIncludes(html, 'aria-label="Share Toronto Blue Jays bullpen"'))
  assert.ok(htmlIncludes(html, 'data-share-url="https://baseballos.vercel.app/team/TOR"'))
  assert.ok(htmlIncludes(html, 'Around the league'))
  assert.ok(!htmlIncludes(html, 'Share Around the league bullpen'))
  assert.ok(htmlIncludes(html, getActiveStoryFilterLabel('all', counts.all)))
  for (const { key, label, description } of STORY_FILTERS) {
    assert.ok(htmlIncludes(html, label), `missing filter: ${label}`)
    assert.ok(htmlIncludes(html, `(${counts[key]})`), `missing count for ${label}`)
    assert.ok(htmlIncludes(html, description), `missing description for ${label}`)
  }
})

test('each filter lane renders only its stories', () => {
  const counts = getFilterCounts(getFourBeatStoryFeed(fourBeatDashboard).items)
  const stressed = render(React.createElement(StoriesView, { dashboard: fourBeatDashboard, initialFilter: 'stressed' }))
  assert.ok(htmlIncludes(stressed, getActiveStoryFilterLabel('stressed', counts.stressed)))
  assert.ok(htmlIncludes(stressed, 'TOR · Toronto Blue Jays'))
  assert.ok(!htmlIncludes(stressed, 'Washington Nationals'))

  const rested = render(React.createElement(StoriesView, { dashboard: fourBeatDashboard, initialFilter: 'rested' }))
  assert.ok(htmlIncludes(rested, getActiveStoryFilterLabel('rested', counts.rested)))
  assert.ok(htmlIncludes(rested, 'Washington Nationals'))
  assert.ok(!htmlIncludes(rested, 'Toronto Blue Jays'))

  const watch = render(React.createElement(StoriesView, { dashboard: fourBeatDashboard, initialFilter: 'watch' }))
  assert.ok(htmlIncludes(watch, getActiveStoryFilterLabel('watch', counts.watch)))
  assert.ok(htmlIncludes(watch, 'SF · San Francisco Giants'))
  assert.ok(htmlIncludes(watch, 'data-share-url="https://baseballos.vercel.app/team/SF"'))
  assert.ok(!htmlIncludes(watch, 'Washington Nationals'))

  const league = render(React.createElement(StoriesView, { dashboard: fourBeatDashboard, initialFilter: 'league' }))
  assert.ok(htmlIncludes(league, getActiveStoryFilterLabel('league', counts.league)))
  assert.ok(htmlIncludes(league, 'league-wide bullpen picture is carrying mixed signals'))
  assert.ok(!htmlIncludes(league, 'TOR · Toronto Blue Jays'))
})

test('empty filter lanes explain themselves and offer a reset', () => {
  const stressedOnly = {
    ...fourBeatDashboard,
    four_beat_stories: {
      ...fourBeatDashboard.four_beat_stories,
      items: fourBeatDashboard.four_beat_stories.items.filter(item => item.category === 'stressed'),
    },
  }

  for (const key of ['rested', 'watch', 'league']) {
    const html = render(React.createElement(StoriesView, {
      dashboard: stressedOnly,
      initialFilter: key,
    }))
    assert.ok(htmlIncludes(html, FEED_EMPTY_COPY[key]), `missing empty copy for ${key}`)
    assert.ok(htmlIncludes(html, FEED_EMPTY_SUPPORT_COPY), `missing support copy for ${key}`)
    assert.ok(htmlIncludes(html, 'Show All Stories'), `missing reset CTA for ${key}`)
    assert.ok(htmlIncludes(html, 'data-reset-filter="all"'), `reset CTA should target all for ${key}`)
  }
})

test('all-feed empty state renders correctly when no four-beat stories are active', () => {
  const emptyDashboard = {
    ...fourBeatDashboard,
    four_beat_stories: {
      ...fourBeatDashboard.four_beat_stories,
      items: [],
      fallback: FOUR_BEAT_STORIES_FALLBACK,
    },
  }
  const html = render(React.createElement(StoriesView, {
    dashboard: emptyDashboard,
    initialFilter: 'all',
  }))
  assert.ok(htmlIncludes(html, FOUR_BEAT_STORIES_FALLBACK))
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
  const html = render(React.createElement(StoriesView, { dashboard: fourBeatDashboard })).toLowerCase()
  for (const term of [
    'availability inventory', 'readiness limitations', 'limitations are present',
    'snapshot', 'governance', 'data_state', 'fail closed',
    'recommended', 'recommendation', 'betting', 'parlay', 'injury',
    'will collapse', 'guaranteed',
    // Mechanical phrasing the language layer exists to prevent.
    'register as', 'workload-restricted', 'availability context',
    'carrying workload concentration', 'limited recovery window',
    'fresh pen', 'fresh arms', 'fresher bullpen', 'freshest bullpen',
    'come in fresh',
  ]) {
    assert.ok(!html.includes(term), `leaked: ${term}`)
  }
})
