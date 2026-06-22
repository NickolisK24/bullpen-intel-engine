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

const {
  canonicalStoriesPageEnabled,
  hasUsableCanonicalStoriesFeed,
  getCanonicalStoryFeed,
} = await server.ssrLoadModule('/src/components/stories/storiesCanonicalFeedView.js')
const { StoriesView } = await server.ssrLoadModule('/src/components/stories/Stories.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

const POSITIVE_HEADLINE = 'The Giants bullpen has more rested options than most clubs today'
const PRESSURE_HEADLINE = 'The Brewers are carrying the late innings on a small group'
const LEAGUE_HEADLINE = "Today's bullpen pressure is concentrated in a small set of clubs."
// Apostrophe-free substring for HTML matching (renderToStaticMarkup escapes ').
const LEAGUE_HTML_MATCH = 'concentrated in a small set of clubs'
const FOUR_BEAT_TITLE = 'The Toronto Blue Jays are transferring bullpen pressure onto a smaller group tonight.'

function canonicalStories(overrides = {}) {
  return {
    capability: 'baseballos_canonical_story_v1',
    items: [
      {
        story_id: '137:2026-06-06', team_id: 137, team_name: 'San Francisco Giants', team_abbreviation: 'SF',
        date: '2026-06-06', story_available: true, story_type: 'availability_depth', category: 'rested', tone: 'rest',
        headline: POSITIVE_HEADLINE,
        narrative: 'Giants observation.\n\nGiants cause.',
        continuity: { state: 'new', reason: 'no_prior_canonical_story', compared: false },
      },
      {
        story_id: '158:2026-06-06', team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL',
        date: '2026-06-06', story_available: true, story_type: 'coverage_pressure', category: 'stressed', tone: 'stress',
        headline: PRESSURE_HEADLINE,
        narrative: 'Brewers observation.\n\nBrewers cause.',
        continuity: { state: 'ongoing', reason: 'story_type_persisted', compared: true },
      },
      {
        story_id: '121:2026-06-06', team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM',
        date: '2026-06-06', story_available: false, suppression_reason: 'no_story_observations',
        story_type: null, category: null, tone: null, headline: null, narrative: null,
        continuity: { state: 'unavailable', compared: true },
      },
    ],
    available_count: 2, suppressed_count: 1,
    league_context: {
      capability: 'baseballos_league_context_v1', mode: 'pressure_concentrated', day_class: 'low_story',
      headline: LEAGUE_HEADLINE,
      summary: 'Most bullpens are in normal shape; the meaningful workload pressure is contained to 3 clubs.',
      evidence: { constrained_team_count: 3, available_team_count: 10, watch_story_count: 0, pressure_story_count: 1, rest_story_count: 1 },
      generated: true, quality_status: 'published',
    },
    ...overrides,
  }
}

const fourBeatStories = {
  capability: 'four_beat_story_template_v1', enabled: true,
  items: [
    {
      story_id: '141:stress_transfer', rule_key: 'stress_transfer', rule_label: 'Stress Transfer',
      team_id: 141, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR',
      kicker: 'Stress Transfer', tone: 'stress', category: 'stressed',
      title: FOUR_BEAT_TITLE,
      narrative: `${FOUR_BEAT_TITLE}\n\nThe recent workload has clustered around the same late-inning group.`,
      href: '/bullpen?view=board&team=TOR&source=four-beat-stories', cta: 'Open the team board',
    },
  ],
}

function dashboardFixture({ stories, four_beat_stories } = {}) {
  return {
    context: { health: { state: 'strained', label: 'x', reasons: [] }, metrics: { total_relievers: 64, available: 38, monitor: 14, restricted: 9, pct_available: 59, pct_restricted: 14 } },
    landscape: {
      reference_date: '2026-06-06', teams_evaluated: 3,
      games: { available: true, data_state: 'historical', today_count: 0, as_of_date: '2026-06-05', as_of_count: 6, is_today: false, message: null },
      constrained_bullpens: [], available_bullpens: [], monitoring_concentration: [],
    },
    freshness: { data_through: '2026-06-05', sync_status: 'success', is_current: true },
    ...(stories ? { stories } : {}),
    ...(four_beat_stories ? { four_beat_stories } : {}),
  }
}

// ── Feature flag ─────────────────────────────────────────────────────────────
test('flag defaults off and only an explicit truthy value enables it', () => {
  assert.equal(canonicalStoriesPageEnabled({}), false)
  assert.equal(canonicalStoriesPageEnabled({ VITE_USE_CANONICAL_STORIES_PAGE: 'false' }), false)
  assert.equal(canonicalStoriesPageEnabled({ VITE_USE_CANONICAL_STORIES_PAGE: 'true' }), true)
  assert.equal(canonicalStoriesPageEnabled({ VITE_USE_CANONICAL_STORIES_PAGE: '1' }), true)
  assert.equal(canonicalStoriesPageEnabled({ VITE_USE_CANONICAL_STORIES_PAGE: true }), true)
})

test('hasUsableCanonicalStoriesFeed requires a present items array', () => {
  assert.equal(hasUsableCanonicalStoriesFeed(dashboardFixture({ stories: canonicalStories() })), true)
  assert.equal(hasUsableCanonicalStoriesFeed(dashboardFixture({ stories: { items: [] } })), true)
  assert.equal(hasUsableCanonicalStoriesFeed(dashboardFixture({ stories: { capability: 'x' } })), false)
  assert.equal(hasUsableCanonicalStoriesFeed(dashboardFixture({})), false)
})

// ── Adapter mapping ──────────────────────────────────────────────────────────
test('feed maps publishable team stories + a league card, excluding suppressed', () => {
  const feed = getCanonicalStoryFeed(dashboardFixture({ stories: canonicalStories() }))
  assert.equal(feed.hasStories, true)
  // 2 publishable team cards + 1 league card; the suppressed Mets story is excluded.
  assert.equal(feed.items.length, 3)
  const teams = feed.items.filter(i => i.teamId != null).map(i => i.teamId)
  assert.deepEqual(teams, [137, 158])
  const league = feed.items.find(i => i.category === 'league')
  assert.ok(league)
  assert.equal(league.title, LEAGUE_HEADLINE)
})

test('positive story maps to a rested card, not a warning', () => {
  const feed = getCanonicalStoryFeed(dashboardFixture({ stories: canonicalStories() }))
  const giants = feed.items.find(i => i.teamId === 137)
  assert.equal(giants.tone, 'rest')
  assert.equal(giants.category, 'rested')
  assert.equal(giants.kicker, 'More Options')
  assert.equal(giants.title, POSITIVE_HEADLINE)
})

test('no team story is rendered twice (no duplicate flagship/feed entry)', () => {
  const feed = getCanonicalStoryFeed(dashboardFixture({ stories: canonicalStories() }))
  const teamIds = feed.items.filter(i => i.teamId != null).map(i => i.teamId)
  assert.equal(new Set(teamIds).size, teamIds.length)
})

test('trust_lane story renders with the Trust Lane kicker in a safe lane (no break)', () => {
  const stories = {
    capability: 'baseballos_canonical_story_v1',
    items: [
      {
        story_id: '147:2026-06-06', team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY',
        date: '2026-06-06', story_available: true, story_type: 'trust_lane', category: 'trust_lane', tone: 'watch',
        headline: 'Yankees have arms available but a thin trusted lane',
        narrative: 'Yankees observation.\n\nYankees cause.',
        continuity: { state: 'new', reason: 'no_prior_canonical_story', compared: false },
      },
    ],
    available_count: 1, suppressed_count: 0,
    league_context: canonicalStories().league_context,
  }
  const feed = getCanonicalStoryFeed(dashboardFixture({ stories }))
  const card = feed.items.find(i => i.teamId === 147)
  assert.ok(card)
  assert.equal(card.kicker, 'Trust Lane')
  assert.equal(card.tone, 'watch')      // supported tone token, not a neutral fallback
  assert.equal(card.category, 'watch')  // unknown category renders in the safe watch lane
  assert.equal(card.title, 'Yankees have arms available but a thin trusted lane')
})

test('quiet day with no publishable team stories still yields the league card', () => {
  const feed = getCanonicalStoryFeed(dashboardFixture({ stories: { items: [], league_context: canonicalStories().league_context } }))
  assert.equal(feed.items.length, 1)
  assert.equal(feed.items[0].category, 'league')
  assert.equal(feed.items[0].title, LEAGUE_HEADLINE)
})

// ── Stories page integration behind the flag ─────────────────────────────────
test('flag enabled: Stories renders canonical stories + league context', () => {
  const html = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({ stories: canonicalStories(), four_beat_stories: fourBeatStories }),
    canonicalStoriesEnabled: true,
  }))
  assert.equal(htmlIncludes(html, POSITIVE_HEADLINE), true)
  assert.equal(htmlIncludes(html, PRESSURE_HEADLINE), true)
  assert.equal(htmlIncludes(html, LEAGUE_HTML_MATCH), true)
  // Legacy Four-Beat content is not used when canonical is active.
  assert.equal(htmlIncludes(html, FOUR_BEAT_TITLE), false)
})

test('flag disabled: Stories keeps legacy Four-Beat behavior', () => {
  const html = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({ stories: canonicalStories(), four_beat_stories: fourBeatStories }),
    canonicalStoriesEnabled: false,
  }))
  assert.equal(htmlIncludes(html, FOUR_BEAT_TITLE), true)
  assert.equal(htmlIncludes(html, POSITIVE_HEADLINE), false)
})

test('flag enabled but malformed payload: Stories falls back to Four-Beat safely', () => {
  const html = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({ stories: { capability: 'x' }, four_beat_stories: fourBeatStories }),
    canonicalStoriesEnabled: true,
  }))
  assert.equal(htmlIncludes(html, FOUR_BEAT_TITLE), true)
  assert.equal(htmlIncludes(html, POSITIVE_HEADLINE), false)
})

test('flag enabled, quiet day: Stories renders the league context cleanly', () => {
  const html = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({ stories: { items: [], league_context: canonicalStories().league_context } }),
    canonicalStoriesEnabled: true,
  }))
  assert.equal(htmlIncludes(html, LEAGUE_HTML_MATCH), true)
})
