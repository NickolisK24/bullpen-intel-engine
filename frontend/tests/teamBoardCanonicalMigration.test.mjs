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

const { default: BullpenBoardView } = await server.ssrLoadModule('/src/components/bullpen/board/BullpenBoardView.jsx')
const { default: StoryCard } = await server.ssrLoadModule('/src/components/bullpen/board/StoryCard.jsx')
const {
  CANONICAL_TEAM_BOARD_FLAG,
  canonicalTeamBoardEnabled,
  canonicalTeamStoryUnavailable,
  shouldMountLegacyStoryPanel,
} = await server.ssrLoadModule('/src/components/bullpen/board/teamBoardCanonicalView.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))
const readSrc = (relPath) => readFileSync(new URL(`../src/${relPath}`, import.meta.url), 'utf8')

const LEGACY_PANEL_MARKER = 'What BaseballOS Sees About This Bullpen'

function boardFixture() {
  return {
    capability: 'team_bullpen_board',
    team: { team_id: 1, team_name: 'Kansas City Royals', team_abbreviation: 'KC' },
    context: {
      health: { state: 'strained', label: 'Several arms are working through recent usage.', reasons: [] },
      metrics: { total_relievers: 8, available: 5, monitor: 2, restricted: 1, pct_available: 62, pct_restricted: 12 },
      confidence: 'high',
      limitations: [],
    },
    groups: [
      {
        status: 'Available', label: 'Available', count: 1,
        pitchers: [{ pitcher_id: 11, name: 'Test Arm', availability_status: 'Available', confidence: 'high', data_state: 'fresh' }],
      },
    ],
    freshness: { data_through: '2026-06-20' },
    roster_status: null,
    stress: null,
    total_pitchers: 1,
  }
}

function storyPayload(overrides = {}) {
  return {
    capability: 'story_intelligence_api_v1',
    contract_state: 'available',
    team_id: 118,
    team_name: 'Kansas City Royals',
    team_abbreviation: 'KC',
    as_of_date: '2026-06-20',
    state: 'story_available',
    story_available: true,
    neutral_reason: null,
    story_type: 'coverage_pressure',
    headline: 'Kansas City is leaning on its setup arms',
    observation: 'The setup group has handled the important outs.',
    baseline: 'That is above the recent baseline.',
    cause: 'Short starts have pushed innings onto the bullpen.',
    constraint: 'If the same game shape repeats, the route stays narrow.',
    freshness: { data_through: '2026-06-20' },
    trust_metadata: { external_generation_used: false },
    limitations: [],
    ...overrides,
  }
}

// ── Feature flag ─────────────────────────────────────────────────────────────
test('flag name is VITE_USE_CANONICAL_TEAM_BOARD and defaults off', () => {
  assert.equal(CANONICAL_TEAM_BOARD_FLAG, 'VITE_USE_CANONICAL_TEAM_BOARD')
  assert.equal(canonicalTeamBoardEnabled({}), false)
  assert.equal(canonicalTeamBoardEnabled({ VITE_USE_CANONICAL_TEAM_BOARD: '' }), false)
  assert.equal(canonicalTeamBoardEnabled({ VITE_USE_CANONICAL_TEAM_BOARD: 'false' }), false)
})

test('flag enables only on an explicit truthy value', () => {
  for (const raw of ['true', '1', 'on', 'yes', true]) {
    assert.equal(canonicalTeamBoardEnabled({ VITE_USE_CANONICAL_TEAM_BOARD: raw }), true, String(raw))
  }
})

// ── Canonical-story availability ─────────────────────────────────────────────
test('canonical story is unavailable only on a real failure, not a neutral read', () => {
  assert.equal(canonicalTeamStoryUnavailable({ data: storyPayload(), loading: false, error: null }), false)
  assert.equal(canonicalTeamStoryUnavailable({ data: { story_available: false }, loading: false, error: null }), false) // neutral is valid
  assert.equal(canonicalTeamStoryUnavailable({ data: null, loading: true, error: null }), false) // still loading
  assert.equal(canonicalTeamStoryUnavailable({ data: null, loading: false, error: 'API 500' }), true)
  assert.equal(canonicalTeamStoryUnavailable({ data: null, loading: false, error: null }), true)
  assert.equal(canonicalTeamStoryUnavailable(null), true)
})

// ── Mount decision ───────────────────────────────────────────────────────────
test('flag off keeps the legacy panel (current behavior)', () => {
  assert.equal(shouldMountLegacyStoryPanel({ enabled: false, storyUnavailable: false, baseShouldShow: true }), true)
})

test('flag on hides the legacy panel when the canonical story is usable', () => {
  assert.equal(shouldMountLegacyStoryPanel({ enabled: true, storyUnavailable: false, baseShouldShow: true }), false)
})

test('flag on falls back to the legacy panel when the canonical story is unavailable', () => {
  assert.equal(shouldMountLegacyStoryPanel({ enabled: true, storyUnavailable: true, baseShouldShow: true }), true)
})

test('the panel never mounts when the base condition is off (e.g. unavailable-only mode)', () => {
  assert.equal(shouldMountLegacyStoryPanel({ enabled: false, storyUnavailable: false, baseShouldShow: false }), false)
  assert.equal(shouldMountLegacyStoryPanel({ enabled: true, storyUnavailable: true, baseShouldShow: false }), false)
})

// ── Panel mounting through the board view ────────────────────────────────────
test('flag-off path mounts TeamBullpenStoryPanel (showStoryPanel true)', () => {
  const html = render(React.createElement(BullpenBoardView, { board: boardFixture(), showStoryPanel: true }))
  assert.ok(htmlIncludes(html, LEGACY_PANEL_MARKER))
})

test('flag-on path hides TeamBullpenStoryPanel (showStoryPanel false)', () => {
  const html = render(React.createElement(BullpenBoardView, { board: boardFixture(), showStoryPanel: false }))
  assert.equal(htmlIncludes(html, LEGACY_PANEL_MARKER), false)
})

// ── Board data surfaces survive the migration ────────────────────────────────
test('board data surfaces remain when the legacy panel is hidden', () => {
  const html = render(React.createElement(BullpenBoardView, { board: boardFixture(), showStoryPanel: false }))
  assert.equal(htmlIncludes(html, LEGACY_PANEL_MARKER), false) // panel gone
  assert.ok(htmlIncludes(html, 'Tonight&#x27;s Bullpen Board')) // board heading
  assert.ok(htmlIncludes(html, 'pitcher')) // board totals line
  assert.ok(htmlIncludes(html, 'Test Arm')) // pitcher group surface
  assert.ok(htmlIncludes(html, 'Pitcher Label Key')) // label key surface
  assert.ok(htmlIncludes(html, 'Available')) // group / availability surface
})

// ── The single canonical story (StoryCard) still renders, incl. new beats ─────
test('the canonical StoryCard renders the single story', () => {
  const html = render(React.createElement(StoryCard, { story: storyPayload() }))
  assert.ok(htmlIncludes(html, 'Bullpen Note'))
  assert.ok(htmlIncludes(html, 'Kansas City is leaning on its setup arms'))
  assert.ok(htmlIncludes(html, 'Coverage Pressure'))
})

test('the canonical StoryCard renders a trust_lane story', () => {
  const html = render(React.createElement(StoryCard, {
    story: storyPayload({ story_type: 'trust_lane', headline: 'Arms available, trusted lane thin' }),
  }))
  assert.ok(htmlIncludes(html, 'Trust Lane'))
  assert.equal(html.includes('trust_lane'), false)
})

test('the canonical StoryCard renders a bridge story', () => {
  const html = render(React.createElement(StoryCard, {
    story: storyPayload({ story_type: 'bridge', headline: 'Settled at the back, fragile in the bridge' }),
  }))
  assert.ok(htmlIncludes(html, 'Bridge Instability'))
  assert.equal(html.includes('bridge_instability'), false)
})

// ── Wiring: TonightsBullpenBoard drives the panel from the flag ───────────────
test('TonightsBullpenBoard wires the flag into showStoryPanel', () => {
  const src = readSrc('components/bullpen/board/TonightsBullpenBoard.jsx')
  assert.ok(src.includes("from './teamBoardCanonicalView'"))
  assert.ok(src.includes('canonicalTeamBoardEnabled('))
  assert.ok(src.includes('shouldMountLegacyStoryPanel('))
  assert.ok(src.includes('showStoryPanel={mountLegacyStoryPanel}'))
  // The canonical StoryCard is still rendered (the single story source).
  assert.ok(src.includes('<StoryCard'))
})

// ── Home and Stories are untouched by this migration ─────────────────────────
test('Home and Stories do not reference the Team Board flag (unchanged)', () => {
  for (const rel of [
    'components/home/Home.jsx',
    'components/home/homeCanonicalStoriesView.js',
    'components/stories/Stories.jsx',
    'components/stories/storiesCanonicalFeedView.js',
  ]) {
    const src = readSrc(rel)
    assert.equal(src.includes('VITE_USE_CANONICAL_TEAM_BOARD'), false, rel)
    assert.equal(src.includes('teamBoardCanonicalView'), false, rel)
  }
})
