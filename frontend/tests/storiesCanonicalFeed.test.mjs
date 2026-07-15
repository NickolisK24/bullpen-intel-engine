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
  hasUsableCanonicalStoriesFeed,
  getCanonicalStoryFeed,
  STORIES_LIMITATIONS_FALLBACK,
  storiesTextHasInternalLanguage,
} = await server.ssrLoadModule('/src/components/stories/storiesCanonicalFeedView.js')
const { StoriesView } = await server.ssrLoadModule('/src/components/stories/Stories.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))
const visibleText = (html) => html
  .replace(/<style[\s\S]*?<\/style>/gi, ' ')
  .replace(/<script[\s\S]*?<\/script>/gi, ' ')
  .replace(/<[^>]+>/g, ' ')

const POSITIVE_HEADLINE = 'The Giants bullpen has more rested options than most clubs today'
const PRESSURE_HEADLINE = 'The Brewers are carrying the late innings on a small group'
const LEAGUE_HEADLINE = "Today's bullpen pressure is concentrated in a small set of clubs."
// Apostrophe-free substring for HTML matching (renderToStaticMarkup escapes ').
const LEAGUE_HTML_MATCH = 'concentrated in a small set of clubs'

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
        freshness: { data_through: '2026-06-25', is_current: true, sync_status: 'success' },
        limitations: ['Game-day availability can still change before first pitch.'],
        quality_status: 'published',
      },
      {
        story_id: '158:2026-06-06', team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL',
        date: '2026-06-06', story_available: true, story_type: 'coverage_pressure', category: 'stressed', tone: 'stress',
        headline: PRESSURE_HEADLINE,
        narrative: 'Brewers observation.\n\nBrewers cause.',
        continuity: { state: 'ongoing', reason: 'story_type_persisted', compared: true },
        freshness: { data_through: '2026-06-25', is_current: true, sync_status: 'success' },
        limitations: ['Late roster moves can change the read.'],
        quality_status: 'published',
      },
      {
        story_id: '121:2026-06-06', team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM',
        date: '2026-06-06', story_available: false, suppression_reason: 'no_story_observations',
        story_type: null, category: null, tone: null, headline: null, narrative: null,
        continuity: { state: 'unavailable', compared: true },
      },
    ],
    available_count: 2, suppressed_count: 1,
    freshness: {
      data_through: '2026-06-25',
      last_successful_sync: '2026-06-26T08:15:00Z',
      is_current: true,
      sync_status: 'success',
    },
    limitations: ['Stories reflect completed-game bullpen context, not private game-day decisions.'],
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

function dashboardFixture({ stories } = {}) {
  return {
    context: { health: { state: 'strained', label: 'x', reasons: [] }, metrics: { total_relievers: 64, available: 38, monitor: 14, restricted: 9, pct_available: 59, pct_restricted: 14 } },
    landscape: {
      reference_date: '2026-06-06', teams_evaluated: 3,
      games: { available: true, data_state: 'historical', today_count: 0, as_of_date: '2026-06-05', as_of_count: 6, is_today: false, message: null },
      constrained_bullpens: [], available_bullpens: [], monitoring_concentration: [],
    },
    freshness: {
      data_through: '2026-06-25',
      last_successful_sync: '2026-06-26T08:15:00Z',
      sync_status: 'success',
      is_current: true,
    },
    ...(stories ? { stories } : {}),
  }
}

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

test('feed maps freshness, limitations, and review status without exposing raw status fields', () => {
  const stories = canonicalStories({
    items: [
      {
        story_id: '137:2026-06-06', team_id: 137, team_name: 'San Francisco Giants', team_abbreviation: 'SF',
        date: '2026-06-06', story_available: true, story_type: 'availability_depth', category: 'rested', tone: 'rest',
        headline: POSITIVE_HEADLINE,
        narrative: 'Giants observation.',
        quality_status: 'published',
        freshness: { data_through: '2026-06-25', is_current: true, sync_status: 'success' },
        limitations: ['Public limitation stays readable.'],
      },
      {
        story_id: '158:2026-06-06', team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL',
        date: '2026-06-06', story_available: true, story_type: 'coverage_pressure', category: 'stressed', tone: 'stress',
        headline: PRESSURE_HEADLINE,
        narrative: 'Brewers observation.',
        quality_status: 'review',
        freshness: { data_through: '2026-06-25', is_current: true, sync_status: 'success' },
        limitations: ['Review limitation stays readable.'],
      },
      {
        story_id: '121:2026-06-06', team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM',
        date: '2026-06-06', story_available: true, story_type: 'coverage_pressure', category: 'stressed', tone: 'stress',
        headline: 'Mets suppressed story should not render',
        narrative: 'Suppressed narrative.',
        quality_status: 'suppressed',
        suppression_reason: 'raw_reason_not_for_ui',
      },
      {
        story_id: '147:2026-06-06', team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY',
        date: '2026-06-06', story_available: true, story_type: 'coverage_pressure', category: 'stressed', tone: 'stress',
        headline: 'Yankees neutral story should not render',
        narrative: 'Neutral narrative.',
        quality_status: 'neutral',
      },
    ],
  })
  const feed = getCanonicalStoryFeed(dashboardFixture({ stories }))

  assert.equal(feed.freshness.data_through, '2026-06-25')
  assert.equal(feed.limitationsSource, 'payload')
  assert.ok(feed.limitations.includes('Stories reflect completed-game bullpen context, not private game-day decisions.'))
  assert.equal(feed.items.some(item => item.title === 'Mets suppressed story should not render'), false)
  assert.equal(feed.items.some(item => item.title === 'Yankees neutral story should not render'), false)
  assert.equal(feed.items.find(item => item.teamId === 137).reviewNote, null)
  assert.equal(feed.items.find(item => item.teamId === 158).reviewNote.label, 'Under review')
  assert.equal(storiesTextHasInternalLanguage('quality_status'), true)
  assert.equal(storiesTextHasInternalLanguage('wraps_story_intelligence_v1_per_team'), true)
  assert.equal(storiesTextHasInternalLanguage('feed_team_set_and_order_mirror_four_beat_feed'), true)
  assert.equal(storiesTextHasInternalLanguage('Game-day availability can still change before first pitch.'), false)
})

test('unsafe or missing story limitations fall back to the standard Stories caveat', () => {
  const unsafe = getCanonicalStoryFeed(dashboardFixture({
    stories: canonicalStories({
      limitations: [
        'wraps_story_intelligence_v1_per_team',
        'feed_team_set_and_order_mirror_four_beat_feed',
        'atomic_evidence_extraction_deferred',
        'no_new_prose_or_metrics_created',
      ],
    }),
  }))
  const missing = getCanonicalStoryFeed(dashboardFixture({
    stories: {
      items: [],
      league_context: canonicalStories().league_context,
    },
  }))

  assert.deepEqual(unsafe.limitations, [STORIES_LIMITATIONS_FALLBACK])
  assert.deepEqual(missing.limitations, [STORIES_LIMITATIONS_FALLBACK])
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

test('today flagship matching story is de-emphasized when team and story type are available', () => {
  const feed = getCanonicalStoryFeed(dashboardFixture({ stories: canonicalStories() }), {
    todayFlagship: { teamId: 137, storyType: 'availability_depth' },
  })

  assert.equal(feed.todayFlagshipDeemphasized, true)
  assert.notEqual(feed.items[0].teamId, 137)
  assert.equal(feed.items.some(item => item.teamId === 137 && item.storyType === 'availability_depth'), true)
  assert.equal(feed.items.some(item => item.category === 'league'), true)
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

test('bridge story renders with the Fragile Bridge kicker in a safe lane (no break)', () => {
  const stories = {
    capability: 'baseballos_canonical_story_v1',
    items: [
      {
        story_id: '111:2026-06-06', team_id: 111, team_name: 'Boston Red Sox', team_abbreviation: 'BOS',
        date: '2026-06-06', story_available: true, story_type: 'bridge', category: 'bridge', tone: 'watch',
        headline: 'Red Sox are settled at the back but fragile in the bridge',
        narrative: 'Red Sox observation.\n\nRed Sox cause.',
        continuity: { state: 'new', reason: 'no_prior_canonical_story', compared: false },
      },
    ],
    available_count: 1, suppressed_count: 0,
    league_context: canonicalStories().league_context,
  }
  const feed = getCanonicalStoryFeed(dashboardFixture({ stories }))
  const card = feed.items.find(i => i.teamId === 111)
  assert.ok(card)
  assert.equal(card.kicker, 'Fragile Bridge')
  assert.equal(card.tone, 'watch')      // supported tone token, not a neutral fallback
  assert.equal(card.category, 'watch')  // unknown category renders in the safe watch lane
  assert.equal(card.title, 'Red Sox are settled at the back but fragile in the bridge')
})

test('quiet day with no publishable team stories still yields the league card', () => {
  const feed = getCanonicalStoryFeed(dashboardFixture({ stories: { items: [], league_context: canonicalStories().league_context } }))
  assert.equal(feed.items.length, 1)
  assert.equal(feed.items[0].category, 'league')
  assert.equal(feed.items[0].title, LEAGUE_HEADLINE)
})

// ── Stories page integration (canonical-only) ────────────────────────────────
test('Stories renders canonical stories + league context', () => {
  const html = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({ stories: canonicalStories() }),
  }))
  assert.equal(htmlIncludes(html, POSITIVE_HEADLINE), true)
  assert.equal(htmlIncludes(html, PRESSURE_HEADLINE), true)
  assert.equal(htmlIncludes(html, LEAGUE_HTML_MATCH), true)
})

test('Stories renders page-level freshness, live state, limitations, and trust link', () => {
  const html = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({ stories: canonicalStories() }),
  }))

  assert.ok(htmlIncludes(html, 'Bullpen data through Jun 25'))
  assert.ok(htmlIncludes(html, 'Last synced 4:15 AM ET'))
  assert.ok(htmlIncludes(html, 'Freshness: Current'))
  assert.ok(htmlIncludes(html, 'Current MLB data'))
  assert.ok(htmlIncludes(html, 'Scope'))
  assert.ok(htmlIncludes(html, 'Stories reflect completed-game bullpen context, not private game-day decisions.'))
  assert.ok(htmlIncludes(html, 'href="/trust"'))
  assert.ok(htmlIncludes(html, 'Data &amp; Trust'))
  assert.equal(htmlIncludes(html, 'Tonight slate'), false)
})

test('Stories renders review-only live note when dashboard freshness is not current', () => {
  const fixture = dashboardFixture({ stories: canonicalStories({ freshness: null }) })
  const html = render(React.createElement(StoriesView, {
    dashboard: {
      ...fixture,
      freshness: {
        data_through: '2026-06-25',
        last_successful_sync: '2026-06-26T08:15:00Z',
        is_current: false,
        sync_status: 'success',
      },
    },
  }))

  assert.ok(htmlIncludes(html, 'Review-only intelligence — not live MLB data'))
})

test('Stories renders safe payload limitations and falls back when payload limitations are unsafe', () => {
  const safeHtml = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({ stories: canonicalStories() }),
  }))
  const unsafeHtml = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({
      stories: canonicalStories({
        limitations: [
          'wraps_story_intelligence_v1_per_team',
          'feed_team_set_and_order_mirror_four_beat_feed',
          'atomic_evidence_extraction_deferred',
          'no_new_prose_or_metrics_created',
        ],
      }),
    }),
  }))

  assert.ok(htmlIncludes(safeHtml, 'Stories reflect completed-game bullpen context, not private game-day decisions.'))
  assert.ok(htmlIncludes(unsafeHtml, STORIES_LIMITATIONS_FALLBACK))
  assert.equal(htmlIncludes(unsafeHtml, 'wraps_story_intelligence_v1_per_team'), false)
  assert.equal(htmlIncludes(unsafeHtml, 'feed_team_set_and_order_mirror_four_beat_feed'), false)
  assert.equal(htmlIncludes(unsafeHtml, 'atomic_evidence_extraction_deferred'), false)
  assert.equal(htmlIncludes(unsafeHtml, 'no_new_prose_or_metrics_created'), false)
})

test('Stories marks review stories subtly while published stories render normally', () => {
  const stories = canonicalStories({
    items: [
      {
        story_id: '137:2026-06-06', team_id: 137, team_name: 'San Francisco Giants', team_abbreviation: 'SF',
        date: '2026-06-06', story_available: true, story_type: 'availability_depth', category: 'rested', tone: 'rest',
        headline: POSITIVE_HEADLINE,
        narrative: 'Giants observation.',
        quality_status: 'published',
      },
      {
        story_id: '158:2026-06-06', team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL',
        date: '2026-06-06', story_available: true, story_type: 'coverage_pressure', category: 'stressed', tone: 'stress',
        headline: PRESSURE_HEADLINE,
        narrative: 'Brewers observation.',
        quality_status: 'review',
      },
    ],
  })
  const html = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({ stories }),
  }))

  assert.ok(htmlIncludes(html, POSITIVE_HEADLINE))
  assert.ok(htmlIncludes(html, PRESSURE_HEADLINE))
  assert.ok(htmlIncludes(html, 'Under review'))
  assert.ok(htmlIncludes(html, 'Shown as a developing read while BaseballOS continues checking the signal.'))
  assert.equal((html.match(/Under review/g) || []).length, 1)
})

test('Stories filter lanes, empty states, and CTAs remain intact', () => {
  const stressedHtml = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({ stories: canonicalStories() }),
    initialFilter: 'stressed',
  }))
  const emptyLeagueHtml = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({
      stories: {
        items: [],
        league_context: null,
      },
    }),
    initialFilter: 'league',
  }))

  assert.ok(htmlIncludes(stressedHtml, 'All'))
  assert.ok(htmlIncludes(stressedHtml, 'Pressure'))
  assert.ok(htmlIncludes(stressedHtml, 'Rest'))
  assert.ok(htmlIncludes(stressedHtml, 'Watch'))
  assert.ok(htmlIncludes(stressedHtml, 'League'))
  assert.ok(htmlIncludes(stressedHtml, PRESSURE_HEADLINE))
  assert.equal(htmlIncludes(stressedHtml, POSITIVE_HEADLINE), false)
  assert.ok(htmlIncludes(stressedHtml, 'href="/"'))
  assert.ok(htmlIncludes(stressedHtml, 'Back to Today'))
  assert.ok(htmlIncludes(stressedHtml, 'href="/bullpen?view=board&amp;team=MIL&amp;source=stories"'))
  assert.ok(htmlIncludes(emptyLeagueHtml, 'No league-wide bullpen movement stands out yet.'))
  assert.ok(htmlIncludes(emptyLeagueHtml, 'Show All Stories'))
})

test('Stories visible text avoids internal terms and prediction, betting, or fantasy language', () => {
  const html = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({ stories: canonicalStories() }),
  }))
  const text = visibleText(html)

  for (const term of [
    'COIN',
    'V2',
    'V3',
    'V4',
    'deterministic',
    'snapshot',
    'endpoint',
    'backend',
    'recommendation engine',
    'baseline distribution',
    'governance layer',
    'governance',
    'sample state',
    'review state',
    'sample intelligence',
    'story_intelligence',
    'raw feed',
    'canonical',
    'canonical feed',
    'model output',
    'atomic',
    'extraction',
    'deferred',
    'mirror',
    'feed_team_set',
    'no_new_prose',
    'metrics_created',
    'quality_status',
    'suppression_reason',
    'source',
    'prediction',
    'betting',
    'fantasy',
    'Trend Since Yesterday',
  ]) {
    assert.equal(new RegExp(escapeRegExp(term), 'i').test(text), false, term)
  }
})

test('malformed canonical payload renders a safe empty feed without crashing', () => {
  const html = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({ stories: { capability: 'x' } }),
  }))
  // No team story content; the page degrades to its empty/fallback state.
  assert.equal(htmlIncludes(html, POSITIVE_HEADLINE), false)
  assert.equal(htmlIncludes(html, 'No bullpen story has enough movement'), true)
})

test('quiet day: Stories renders the league context cleanly', () => {
  const html = render(React.createElement(StoriesView, {
    dashboard: dashboardFixture({ stories: { items: [], league_context: canonicalStories().league_context } }),
  }))
  assert.equal(htmlIncludes(html, LEAGUE_HTML_MATCH), true)
})
