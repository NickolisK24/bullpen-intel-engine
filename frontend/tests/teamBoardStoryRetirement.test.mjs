import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

// Phase 4B.6 — the legacy TeamBullpenStoryPanel is retired. The Team Board has
// exactly one story surface: the canonical StoryCard. This suite validates the
// end state and guards against the legacy panel coming back.

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
const { STORY_TYPE_DISPLAY } = await server.ssrLoadModule('/src/components/bullpen/board/storyCardView.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))
const readSrc = (relPath) => readFileSync(new URL(`../src/${relPath}`, import.meta.url), 'utf8')
const srcPath = (relPath) => new URL(`../src/${relPath}`, import.meta.url)

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

// ── Legacy panel is gone from source and runtime ─────────────────────────────
test('the retired legacy source files no longer exist', () => {
  for (const rel of [
    'components/bullpen/board/TeamBullpenStoryPanel.jsx',
    'components/bullpen/board/teamBullpenStoryView.js',
    'components/bullpen/board/teamBoardCanonicalView.js',
  ]) {
    assert.equal(existsSync(srcPath(rel)), false, rel)
  }
})

test('BullpenBoardView no longer references the legacy panel or its wiring', () => {
  const src = readSrc('components/bullpen/board/BullpenBoardView.jsx')
  assert.equal(src.includes('TeamBullpenStoryPanel'), false)
  assert.equal(src.includes('showStoryPanel'), false)
})

test('TonightsBullpenBoard keeps the canonical StoryCard and drops the retired flag module', () => {
  const src = readSrc('components/bullpen/board/TonightsBullpenBoard.jsx')
  assert.ok(src.includes('<StoryCard')) // the single story surface remains
  assert.equal(src.includes('teamBoardCanonicalView'), false)
  assert.equal(src.includes('shouldMountLegacyStoryPanel'), false)
  assert.equal(src.includes('VITE_USE_CANONICAL_TEAM_BOARD'), false)
  assert.equal(src.includes('TeamBullpenStoryPanel'), false)
})

test('the board view never renders the legacy panel marker', () => {
  const html = render(React.createElement(BullpenBoardView, { board: boardFixture(), compact: true }))
  assert.equal(htmlIncludes(html, LEGACY_PANEL_MARKER), false)
})

// ── Board data surfaces survive the retirement ───────────────────────────────
test('board data surfaces remain after the panel is retired', () => {
  const html = render(React.createElement(BullpenBoardView, { board: boardFixture(), compact: true }))
  assert.ok(htmlIncludes(html, 'Tonight&#x27;s Bullpen Board')) // heading
  assert.ok(htmlIncludes(html, 'pitcher')) // totals line
  assert.ok(htmlIncludes(html, 'Test Arm')) // pitcher group
  assert.ok(htmlIncludes(html, 'Pitcher Label Key')) // label key
  assert.ok(htmlIncludes(html, 'Available')) // availability surface
})

// ── The single canonical StoryCard still renders every supported beat ─────────
test('the canonical StoryCard renders the single coverage-pressure story', () => {
  const html = render(React.createElement(StoryCard, { story: storyPayload() }))
  assert.ok(htmlIncludes(html, 'Bullpen Note'))
  assert.ok(htmlIncludes(html, 'Kansas City is leaning on its setup arms'))
  assert.ok(htmlIncludes(html, 'Coverage Pressure'))
})

test('the canonical StoryCard preserves trust lane, bridge, and availability depth', () => {
  // Labels are still wired (preserved through the retirement).
  assert.equal(STORY_TYPE_DISPLAY.trust_lane.label, 'Trust Lane')
  assert.equal(STORY_TYPE_DISPLAY.bridge.label, 'Bridge Instability')
  assert.equal(STORY_TYPE_DISPLAY.availability_depth.label, 'More Options')

  for (const [storyType, label] of [
    ['trust_lane', 'Trust Lane'],
    ['bridge', 'Bridge Instability'],
    ['availability_depth', 'More Options'],
  ]) {
    const html = render(React.createElement(StoryCard, {
      story: storyPayload({ story_type: storyType, headline: `${label} headline for the bullpen` }),
    }))
    assert.ok(htmlIncludes(html, label), storyType)
    assert.equal(html.includes(storyType), false, storyType) // internal type not leaked
  }
})

// ── Home and Stories untouched by the retirement ─────────────────────────────
test('Home and Stories do not reference the retired panel or flag', () => {
  for (const rel of [
    'components/home/Home.jsx',
    'components/stories/Stories.jsx',
    'components/stories/storiesCanonicalFeedView.js',
  ]) {
    const src = readSrc(rel)
    assert.equal(src.includes('TeamBullpenStoryPanel'), false, rel)
    assert.equal(src.includes('VITE_USE_CANONICAL_TEAM_BOARD'), false, rel)
    assert.equal(src.includes('teamBoardCanonicalView'), false, rel)
  }
})
