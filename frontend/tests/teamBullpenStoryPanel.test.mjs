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

const { default: TeamBullpenStoryPanel } = await server.ssrLoadModule('/src/components/bullpen/board/TeamBullpenStoryPanel.jsx')
const { default: BullpenBoardView } = await server.ssrLoadModule('/src/components/bullpen/board/BullpenBoardView.jsx')
const { getTeamBullpenStoryView, deriveStoryFamily, STORY_FRAMING_LINE } =
  await server.ssrLoadModule('/src/components/bullpen/board/teamBullpenStoryView.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

// Board payloads shaped like /api/bullpen/teams/:id/board.
function makeBoard({ teamName, abbr, state, confidence = 'high', metrics }) {
  return {
    capability: 'team_bullpen_board',
    team: { team_id: 1, team_name: teamName, team_abbreviation: abbr },
    context: {
      health: { state, label: 'label', reasons: [] },
      metrics,
      confidence,
      limitations: [],
    },
    groups: [],
    freshness: {},
    roster_status: null,
    stress: null,
    total_pitchers: metrics.total_relievers,
  }
}

const constrainedBoard = makeBoard({
  teamName: 'Milwaukee Brewers', abbr: 'MIL', state: 'constrained',
  metrics: { total_relievers: 8, available: 2, monitor: 2, limited: 0, avoid: 3, unavailable: 1, pct_available: 25, pct_restricted: 50 },
})

const watchBoard = makeBoard({
  teamName: 'Toronto Blue Jays', abbr: 'TOR', state: 'manageable',
  metrics: { total_relievers: 8, available: 4, monitor: 4, limited: 0, avoid: 0, unavailable: 0, pct_available: 50, pct_restricted: 0 },
})

const restedBoard = makeBoard({
  teamName: 'Washington Nationals', abbr: 'WSH', state: 'manageable',
  metrics: { total_relievers: 8, available: 6, monitor: 1, limited: 0, avoid: 1, unavailable: 0, pct_available: 75, pct_restricted: 12 },
})

const balancedBoard = makeBoard({
  teamName: 'Chicago Cubs', abbr: 'CHC', state: 'manageable',
  metrics: { total_relievers: 8, available: 4, monitor: 1, limited: 1, avoid: 0, unavailable: 2, pct_available: 50, pct_restricted: 37 },
})

const dataLimitedBoard = makeBoard({
  teamName: 'Miami Marlins', abbr: 'MIA', state: 'no_data',
  metrics: { total_relievers: 0, available: 0, monitor: 0, limited: 0, avoid: 0, unavailable: 0, pct_available: 0, pct_restricted: 0 },
})

// ── Story family derivation ────────────────────────────────────────────────

test('each board shape lands in its story family', () => {
  assert.equal(deriveStoryFamily(constrainedBoard), 'constrained')
  assert.equal(deriveStoryFamily(watchBoard), 'watch')
  assert.equal(deriveStoryFamily(restedBoard), 'rested')
  assert.equal(deriveStoryFamily(balancedBoard), 'balanced')
  assert.equal(deriveStoryFamily(dataLimitedBoard), 'data_limited')
})

test('a constrained club gets constrained story copy with real counts', () => {
  const story = getTeamBullpenStoryView(constrainedBoard)
  assert.equal(story.label, 'Constrained Pen')
  assert.match(story.headline, /Milwaukee Brewers enter today with a thin late-inning margin/)
  assert.match(story.summary, /3 arms of 8 come in needing rest|3 arms/)
  assert.ok(story.workloadBullets.some(bullet => /2 arms of 8 come in rested and ready/.test(bullet)))
  assert.ok(story.workloadBullets.some(bullet => /3 arms are workload-restricted/.test(bullet)))
  assert.ok(story.watchBullets.length >= 2 && story.watchBullets.length <= 3)
})

test('a watch-list club reads calm surface, heavy workload', () => {
  const story = getTeamBullpenStoryView(watchBoard)
  assert.equal(story.label, 'Watch-List Pen')
  assert.match(story.headline, /look calm on the surface/)
  assert.match(story.summary, /4 arms of 8/)
  assert.match(story.summary, /nobody is workload-restricted yet/)
})

test('a rested club reads as the cleanest availability picture', () => {
  const story = getTeamBullpenStoryView(restedBoard)
  assert.equal(story.label, 'Rested Pen')
  assert.match(story.headline, /cleanest availability pictures into today/)
  assert.match(story.summary, /6 arms of 8 come in rested and ready/)
})

test('single-arm counts read grammatically', () => {
  const story = getTeamBullpenStoryView(restedBoard)
  assert.ok(story.workloadBullets.some(bullet => bullet === '1 arm is workload-restricted after its recent use.'),
    `got: ${story.workloadBullets.join(' | ')}`)
  assert.ok(story.workloadBullets.some(bullet => bullet === '1 arm carries enough recent work to sit on the watch list.'),
    `got: ${story.workloadBullets.join(' | ')}`)
})

test('a neutral club gets balanced story copy', () => {
  const story = getTeamBullpenStoryView(balancedBoard)
  assert.equal(story.label, 'Balanced Pen')
  assert.match(story.headline, /come in steady — no extreme bullpen signal today/)
})

test('a thin dataset gets an honest limited read', () => {
  const story = getTeamBullpenStoryView(dataLimitedBoard)
  assert.equal(story.label, 'Limited Read')
  assert.match(story.headline, /Not enough fresh data for a strong read/)
  assert.ok(story.workloadBullets.length >= 1)
})

test('no board means no story', () => {
  assert.equal(getTeamBullpenStoryView(null).hasStory, false)
  assert.equal(render(React.createElement(TeamBullpenStoryPanel, { board: null })), '')
})

// ── Panel rendering & placement ────────────────────────────────────────────

test('the panel renders headline, both bullet sections, and the framing line', () => {
  const html = render(React.createElement(TeamBullpenStoryPanel, { board: constrainedBoard }))
  assert.ok(htmlIncludes(html, 'Why BaseballOS Is Watching This Pen'))
  assert.ok(htmlIncludes(html, 'What The Workload Shape Says'))
  assert.ok(htmlIncludes(html, 'What To Watch On The Board'))
  assert.ok(htmlIncludes(html, STORY_FRAMING_LINE))
})

test('the board view mounts the story panel above the board only when asked', () => {
  const withPanel = render(React.createElement(BullpenBoardView, { board: constrainedBoard, showStoryPanel: true }))
  assert.ok(htmlIncludes(withPanel, 'Why BaseballOS Is Watching This Pen'))
  assert.ok(
    withPanel.indexOf('Why BaseballOS Is Watching This Pen') < withPanel.indexOf('Bullpen Board'),
    'story panel should sit above the board heading',
  )

  // Embedded uses (e.g. the side-by-side comparison) stay unchanged.
  const withoutPanel = render(React.createElement(BullpenBoardView, { board: constrainedBoard }))
  assert.ok(!htmlIncludes(withoutPanel, 'Why BaseballOS Is Watching This Pen'))
})

// ── Language guardrails ────────────────────────────────────────────────────

const allBoards = [constrainedBoard, watchBoard, restedBoard, balancedBoard, dataLimitedBoard]

test('the story panel never renders raw system phrasing', () => {
  for (const board of allBoards) {
    const html = render(React.createElement(TeamBullpenStoryPanel, { board })).toLowerCase()
    for (const term of [
      'availability inventory', 'readiness limitations', 'limitations are present',
      'snapshot', 'governance', 'classification', 'algorithm', 'data state',
      'contract', 'fail closed',
    ]) {
      assert.ok(!html.includes(term), `${board.team.team_abbreviation} leaked system phrasing: ${term}`)
    }
  }
})

test('the story panel avoids prediction, betting, injury, and recommendation language', () => {
  for (const board of allBoards) {
    // The required framing line ("— not a prediction.") is the one sanctioned
    // use of the word; everything else must stay clean.
    const html = render(React.createElement(TeamBullpenStoryPanel, { board }))
      .replace(new RegExp(escapeRegExp(STORY_FRAMING_LINE), 'g'), '')
      .toLowerCase()
    for (const term of [
      'will collapse', 'guaranteed', 'bet ', 'betting', 'odds', 'parlay',
      'injury', 'prediction', 'predict', 'recommended', 'recommendation',
      'should use', 'use this pitcher', 'manager should', 'best arm', 'best option',
    ]) {
      assert.ok(!html.includes(term), `${board.team.team_abbreviation} leaked: ${term}`)
    }
  }
})
