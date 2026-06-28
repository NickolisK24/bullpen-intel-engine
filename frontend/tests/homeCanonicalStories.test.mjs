import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
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
  hasUsableCanonicalStories,
  getCanonicalHomeStories,
  getCanonicalHeroStory,
  getCanonicalLeagueContext,
} = await server.ssrLoadModule('/src/components/home/homeCanonicalStoriesView.js')
const { HomeView } = await server.ssrLoadModule('/src/components/home/LegacyMorningBullpenReport.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

const POSITIVE_HEADLINE = 'The Giants bullpen has more rested options than most clubs today'
const METS_HEADLINE = 'Mets bridge arms changed after last night'
const YANKEES_HEADLINE = 'Yankees lead the league story today'
const metsTeam = { team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM' }

function canonicalFeed(overrides = {}) {
  return {
    capability: 'baseballos_canonical_story_v1',
    items: [
      {
        story_id: '137:2026-06-06', team_id: 137, team_name: 'San Francisco Giants', team_abbreviation: 'SF',
        date: '2026-06-06', story_available: true, suppression_reason: null,
        story_type: 'availability_depth', category: 'rested', tone: 'rest',
        headline: POSITIVE_HEADLINE,
        narrative: 'Observation sentence.\n\nBaseline sentence.\n\nCause sentence.\n\nConstraint sentence.',
        beats: [
          { key: 'observation', label: 'What changed', text: 'Observation sentence.' },
          { key: 'baseline', label: 'Comparison point', text: 'Baseline sentence.' },
          { key: 'cause', label: 'Why it happened', text: 'Cause sentence.' },
          { key: 'constraint', label: 'What it creates', text: 'Constraint sentence.' },
        ],
        share_summary: 'Observation sentence.',
        continuity: { state: 'new', reason: 'no_prior_canonical_story', compared: false },
        quality_status: 'published',
      },
      {
        story_id: '158:2026-06-06', team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL',
        date: '2026-06-06', story_available: false, suppression_reason: 'no_story_observations',
        story_type: null, category: null, tone: null, headline: null, narrative: null, beats: [],
        continuity: { state: 'unavailable', reason: 'no_publishable_story_today', compared: true },
        quality_status: 'suppressed',
      },
    ],
    available_count: 1,
    suppressed_count: 1,
    league_context: {
      capability: 'baseballos_league_context_v1',
      mode: 'pressure_concentrated', day_class: 'low_story',
      headline: "Today's bullpen pressure is concentrated in a small set of clubs.",
      summary: 'Most bullpens are in normal shape; the meaningful workload pressure is contained to 3 clubs.',
      evidence: {
        team_story_count: 4, publishable_story_count: 1, pressure_story_count: 1, rest_story_count: 1,
        watch_story_count: 0, league_team_count: 30, constrained_team_count: 3, available_team_count: 10,
      },
      generated: true, quality_status: 'published',
      continuity: { state: 'unchanged', previous_mode: 'pressure_concentrated' },
    },
    ...overrides,
  }
}

function dashboardFixture(stories) {
  return {
    capability: 'bullpen_dashboard',
    context: {
      health: { state: 'strained', label: 'Several bullpens are working through heavy recent usage.', reasons: [] },
      metrics: { total_relievers: 64, available: 38, monitor: 14, restricted: 9, pct_available: 59, pct_restricted: 14 },
    },
    roles: { order: [], counts: {}, total: 64 },
    landscape: {
      capability: 'tonights_bullpen_landscape', reference_date: '2026-06-06', teams_evaluated: 4,
      games: { available: true, data_state: 'historical', today_count: 0, as_of_date: '2026-06-05', as_of_count: 6, is_today: false, message: null },
      constrained_bullpens: [
        { team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL', total_relievers: 8, available: 2, monitor: 2, restricted: 4, pct_available: 25, pct_restricted: 50 },
      ],
      available_bullpens: [
        { team_id: 137, team_name: 'San Francisco Giants', team_abbreviation: 'SF', total_relievers: 8, available: 6, monitor: 1, restricted: 1, pct_available: 75, pct_restricted: 12 },
      ],
      monitoring_concentration: [],
    },
    freshness: { data_through: '2026-06-05', sync_status: 'success', is_current: true },
    stories,
  }
}

function teamStory({
  teamId,
  teamName,
  teamAbbr,
  headline,
  storyType = 'route_change',
  category = 'watch',
  tone = 'watch',
}) {
  return {
    story_id: `${teamId}:2026-06-06`,
    team_id: teamId,
    team_name: teamName,
    team_abbreviation: teamAbbr,
    date: '2026-06-06',
    story_available: true,
    suppression_reason: null,
    story_type: storyType,
    category,
    tone,
    headline,
    narrative: `${headline} observation.\n\n${headline} baseline.\n\n${headline} cause.\n\n${headline} constraint.`,
    beats: [
      { key: 'observation', label: 'What changed', text: `${headline} observation.` },
      { key: 'baseline', label: 'Comparison point', text: `${headline} baseline.` },
      { key: 'cause', label: 'Why it happened', text: `${headline} cause.` },
      { key: 'constraint', label: 'What it creates', text: `${headline} constraint.` },
    ],
    share_summary: `${headline} observation.`,
    continuity: { state: 'new', reason: 'no_prior_canonical_story', compared: false },
    quality_status: 'published',
  }
}

function makeChanges(overrides = {}) {
  return {
    state: 'changes',
    comparison: {
      anchor_game_date: '2026-06-06',
      current_game_date: '2026-06-07',
      global_latest_game_date: '2026-06-07',
      label: 'Compared with NYM: Jun 6 -> Jun 7',
      is_current: true,
      team_data_behind_league: false,
    },
    team_summary: null,
    pitcher_changes: [
      {
        type: 'appearance',
        pitcher_id: 1,
        pitcher_name: 'Mets Relief Arm',
        game_date: '2026-06-07',
        pitches: 19,
        summary: 'Mets Relief Arm pitched Sunday - 19 pitches.',
      },
    ],
    freshness: {
      latest_workload_date: '2026-06-07',
      is_current: true,
    },
    ...overrides,
  }
}

// ── Canonical payload shape ──────────────────────────────────────────────────
test('hasUsableCanonicalStories requires a present items array', () => {
  assert.equal(hasUsableCanonicalStories(dashboardFixture(canonicalFeed())), true)
  assert.equal(hasUsableCanonicalStories(dashboardFixture({ items: [] })), true) // quiet day is usable
  assert.equal(hasUsableCanonicalStories(dashboardFixture({ capability: 'x' })), false) // malformed
  assert.equal(hasUsableCanonicalStories({}), false)
})

// ── Adapter mapping ──────────────────────────────────────────────────────────
test('positive story maps to a rested card, not a warning', () => {
  const result = getCanonicalHomeStories(dashboardFixture(canonicalFeed()))
  assert.equal(result.hasStories, true)
  assert.equal(result.items.length, 1) // suppressed item excluded
  const card = result.items[0]
  assert.equal(card.tone, 'rest')
  assert.equal(card.kicker, 'More Options')
  assert.equal(card.title, POSITIVE_HEADLINE)
  assert.equal(card.narrative.includes('Observation sentence.'), true)
})

test('Home tolerates and renders a trust_lane story (Trust Lane kicker, watch tone)', () => {
  const feed = canonicalFeed({
    items: [
      {
        story_id: '147:2026-06-06', team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY',
        date: '2026-06-06', story_available: true, suppression_reason: null,
        story_type: 'trust_lane', category: 'trust_lane', tone: 'watch',
        headline: 'Yankees have arms available but a thin trusted lane',
        narrative: 'Observation sentence.\n\nCause sentence.',
        beats: [
          { key: 'observation', label: 'What changed', text: 'Observation sentence.' },
          { key: 'constraint', label: 'What it creates', text: 'Constraint sentence.' },
        ],
        continuity: { state: 'new', reason: 'no_prior_canonical_story', compared: false },
        quality_status: 'published',
      },
    ],
  })
  const result = getCanonicalHomeStories(dashboardFixture(feed))
  assert.equal(result.hasStories, true)
  const card = result.items[0]
  assert.equal(card.kicker, 'Trust Lane')   // received through the existing adapter map
  assert.equal(card.tone, 'watch')          // supported tone, not a neutral fallback
  assert.equal(card.storyKind, 'team_story')
  assert.equal(card.title, 'Yankees have arms available but a thin trusted lane')
})

test('Home tolerates and renders a bridge story (Fragile Bridge kicker, watch tone)', () => {
  const feed = canonicalFeed({
    items: [
      {
        story_id: '111:2026-06-06', team_id: 111, team_name: 'Boston Red Sox', team_abbreviation: 'BOS',
        date: '2026-06-06', story_available: true, suppression_reason: null,
        story_type: 'bridge', category: 'bridge', tone: 'watch',
        headline: 'Red Sox are settled at the back but fragile in the bridge',
        narrative: 'Observation sentence.\n\nCause sentence.',
        beats: [
          { key: 'observation', label: 'What changed', text: 'Observation sentence.' },
          { key: 'constraint', label: 'What it creates', text: 'Constraint sentence.' },
        ],
        continuity: { state: 'new', reason: 'no_prior_canonical_story', compared: false },
        quality_status: 'published',
      },
    ],
  })
  const result = getCanonicalHomeStories(dashboardFixture(feed))
  assert.equal(result.hasStories, true)
  const card = result.items[0]
  assert.equal(card.kicker, 'Fragile Bridge')  // received through the existing adapter map
  assert.equal(card.tone, 'watch')             // supported tone, not a neutral fallback
  assert.equal(card.storyKind, 'team_story')
  assert.equal(card.title, 'Red Sox are settled at the back but fragile in the bridge')
})

test('hero takes the lead publishable story and splits prose from why-it-matters', () => {
  const hero = getCanonicalHeroStory(dashboardFixture(canonicalFeed()))
  assert.equal(hero.hasStory, true)
  assert.equal(hero.tone, 'rest')
  assert.equal(hero.headline, POSITIVE_HEADLINE)
  // Descriptive prose excludes the constraint beat, which becomes whyItMatters.
  assert.equal(hero.observation.includes('Cause sentence.'), true)
  assert.equal(hero.observation.includes('Constraint sentence.'), false)
  assert.equal(hero.whyItMatters, 'Constraint sentence.')
  assert.equal(hero.storyStatus, null) // continuity.compared === false
  assert.deepEqual(hero.chips, [])
})

test('preferred team story becomes the Home flagship when available', () => {
  const dashboard = dashboardFixture(canonicalFeed({
    items: [
      teamStory({
        teamId: 147,
        teamName: 'New York Yankees',
        teamAbbr: 'NYY',
        headline: YANKEES_HEADLINE,
        storyType: 'coverage_pressure',
        category: 'stressed',
        tone: 'stress',
      }),
      teamStory({
        teamId: 121,
        teamName: 'New York Mets',
        teamAbbr: 'NYM',
        headline: METS_HEADLINE,
      }),
    ],
  }))

  const hero = getCanonicalHeroStory(dashboard, { preferredTeam: metsTeam })

  assert.equal(hero.headline, METS_HEADLINE)
  assert.equal(hero.team.abbr, 'NYM')
})

test('preferred team hero falls back to generic flagship when no team story exists', () => {
  const dashboard = dashboardFixture(canonicalFeed({
    items: [
      teamStory({
        teamId: 147,
        teamName: 'New York Yankees',
        teamAbbr: 'NYY',
        headline: YANKEES_HEADLINE,
        storyType: 'coverage_pressure',
        category: 'stressed',
        tone: 'stress',
      }),
      {
        story_id: '121:2026-06-06',
        team_id: 121,
        team_name: 'New York Mets',
        team_abbreviation: 'NYM',
        date: '2026-06-06',
        story_available: false,
        suppression_reason: 'no_story_observations',
        story_type: null,
        category: null,
        tone: null,
        headline: null,
        narrative: null,
        beats: [],
        continuity: { state: 'unavailable', reason: 'no_publishable_story_today', compared: true },
        quality_status: 'suppressed',
      },
    ],
  }))

  const hero = getCanonicalHeroStory(dashboard, { preferredTeam: metsTeam })

  assert.equal(hero.headline, YANKEES_HEADLINE)
  assert.equal(hero.team.abbr, 'NYY')
})

test('quiet day with no publishable story falls to a league/quiet hero', () => {
  const hero = getCanonicalHeroStory(dashboardFixture({ items: [], league_context: canonicalFeed().league_context }))
  assert.equal(hero.hasStory, false)
  assert.equal(hero.kicker, 'League Check-In')
  assert.equal(hero.headline, "Today's bullpen pressure is concentrated in a small set of clubs.")
})

test('league context maps backend read and evidence counts', () => {
  const ctx = getCanonicalLeagueContext(dashboardFixture(canonicalFeed()))
  assert.equal(ctx.summary.includes('concentrated in a small set of clubs'), true)
  assert.equal(ctx.facts.length, 3)
  const pressure = ctx.facts.find(f => f.key === 'pressure')
  assert.equal(pressure.value, '3') // constrained_team_count
  assert.equal(pressure.tone, 'stress')
  assert.equal(ctx.href, '/stories')
})

// ── Home integration (canonical-only) ────────────────────────────────────────
test('Home renders the canonical positive story', () => {
  const html = render(React.createElement(HomeView, {
    dashboard: dashboardFixture(canonicalFeed()),
  }))
  assert.equal(htmlIncludes(html, POSITIVE_HEADLINE), true)
  assert.equal(htmlIncludes(html, 'More Options'), true)
  // The positive story is not framed as a pressure warning.
  assert.equal(htmlIncludes(html, 'Stretched Thin'), false)
})

test('preferred team Home renders What Changed before the bullpen picture and team flagship', () => {
  const html = render(React.createElement(HomeView, {
    dashboard: dashboardFixture(canonicalFeed({
      items: [
        teamStory({
          teamId: 147,
          teamName: 'New York Yankees',
          teamAbbr: 'NYY',
          headline: YANKEES_HEADLINE,
          storyType: 'coverage_pressure',
          category: 'stressed',
          tone: 'stress',
        }),
        teamStory({
          teamId: 121,
          teamName: 'New York Mets',
          teamAbbr: 'NYM',
          headline: METS_HEADLINE,
        }),
      ],
    })),
    preferredTeam: metsTeam,
    preferredTeamChanges: makeChanges(),
  }))

  assert.equal(htmlIncludes(html, 'My Team'), true)
  assert.equal(htmlIncludes(html, 'What Changed Since Last Game'), true)
  assert.equal(htmlIncludes(html, 'Mets Relief Arm pitched Sunday - 19 pitches.'), true)
  assert.equal(htmlIncludes(html, 'Tonight&#x27;s Bullpen Picture'), true)
  assert.equal(htmlIncludes(html, METS_HEADLINE), true)
  assert.equal(htmlIncludes(html, 'League Context'), true)
  assert.equal(htmlIncludes(html, 'Three Things To Watch'), true)

  assert.ok(html.indexOf('What Changed Since Last Game') < html.indexOf('Tonight&#x27;s Bullpen Picture'))
  assert.ok(html.indexOf('Tonight&#x27;s Bullpen Picture') < html.indexOf('What BaseballOS Sees Today'))
  assert.ok(html.indexOf(METS_HEADLINE) < html.indexOf('Three Things To Watch'))
})

test('preferred team Home falls back to generic flagship while preserving league discovery', () => {
  const html = render(React.createElement(HomeView, {
    dashboard: dashboardFixture(canonicalFeed()),
    preferredTeam: metsTeam,
    preferredTeamChanges: makeChanges({ state: 'no_changes', pitcher_changes: [] }),
  }))

  assert.equal(htmlIncludes(html, 'What Changed Since Last Game'), true)
  assert.equal(htmlIncludes(html, 'You&#x27;re caught up on New York Mets.'), true)
  assert.equal(htmlIncludes(html, 'here&#x27;s the current picture.'), true)
  assert.equal(htmlIncludes(html, 'Tonight&#x27;s Bullpen Picture'), true)
  assert.equal(htmlIncludes(html, POSITIVE_HEADLINE), true)
  assert.equal(htmlIncludes(html, METS_HEADLINE), false)
  assert.equal(htmlIncludes(html, 'Three Things To Watch'), true)
  assert.equal(htmlIncludes(html, 'League Context'), true)
})

test('anonymous Home flow keeps picker, generic flagship, watch cards, and league context', () => {
  const html = render(React.createElement(HomeView, {
    dashboard: dashboardFixture(canonicalFeed()),
    teams: [metsTeam],
    preferredTeam: null,
    preferredTeamPromptDismissed: false,
  }))

  assert.equal(htmlIncludes(html, 'Pick Your Team'), true)
  assert.equal(htmlIncludes(html, 'Make Today open around your bullpen'), true)
  assert.equal(htmlIncludes(html, POSITIVE_HEADLINE), true)
  assert.equal(htmlIncludes(html, 'Three Things To Watch'), true)
  assert.equal(htmlIncludes(html, 'League Context'), true)
  assert.equal(htmlIncludes(html, 'What Changed Since Last Game'), false)
  assert.ok(html.indexOf('Pick Your Team') < html.indexOf('What BaseballOS Sees Today'))
})

test('quiet day: Home renders the league/quiet hero without crashing', () => {
  const html = render(React.createElement(HomeView, {
    dashboard: dashboardFixture({ items: [], league_context: canonicalFeed().league_context }),
  }))
  assert.equal(htmlIncludes(html, 'League Check-In'), true)
  assert.equal(htmlIncludes(html, 'bullpen pressure is concentrated in a small set of clubs.'), true)
  assert.equal(htmlIncludes(html, 'League Context'), true)
})

test('malformed dashboard.stories still renders a neutral Home without blanking', () => {
  const html = render(React.createElement(HomeView, {
    dashboard: dashboardFixture({ capability: 'baseballos_canonical_story_v1' }), // no items array
  }))
  assert.equal(htmlIncludes(html, 'League Check-In'), true)
  assert.equal(htmlIncludes(html, 'A quiet morning across baseball'), true)
  assert.equal(htmlIncludes(html, 'League Context'), true)
  assert.equal(htmlIncludes(html, 'The league context is waiting on a complete bullpen dashboard.'), true)
  assert.equal(htmlIncludes(html, POSITIVE_HEADLINE), false)
})

test('missing dashboard.stories still renders a neutral Home without throwing', () => {
  const dashboard = dashboardFixture(undefined)
  delete dashboard.stories
  const html = render(React.createElement(HomeView, { dashboard }))
  assert.equal(htmlIncludes(html, 'League Check-In'), true)
  assert.equal(htmlIncludes(html, 'A quiet morning across baseball'), true)
  assert.equal(htmlIncludes(html, 'Three Things To Watch'), true)
  assert.equal(htmlIncludes(html, 'League Context'), true)
})

test('Home reuses the existing team changes API contract', () => {
  const apiSource = readFileSync(new URL('../src/utils/api.js', import.meta.url), 'utf8')
  const homeSource = readFileSync(new URL('../src/components/home/LegacyMorningBullpenReport.jsx', import.meta.url), 'utf8')

  assert.match(apiSource, /export const getTeamChanges = \(teamId\) => request\(`\/bullpen\/teams\/\$\{teamId\}\/changes`\)/)
  assert.match(homeSource, /getTeamChanges\(activeTeamId\)/)
  assert.doesNotMatch(homeSource, /\/bullpen\/teams\/\$\{activeTeamId\}\/changes/)
})
