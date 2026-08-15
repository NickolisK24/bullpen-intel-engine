import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import {
  emptyBoard,
  failClosedTeamState,
  makeBoard,
  populatedBoard,
  publicTeamState,
  staleBoard,
} from './fixtures/bullpenBoardFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { default: TonightsBullpenBoard } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TonightsBullpenBoard.jsx',
)
const { default: BullpenAvailabilityDistribution } = await server.ssrLoadModule(
  '/src/components/bullpen/board/BullpenAvailabilityDistribution.jsx',
)
const view = await server.ssrLoadModule('/src/components/bullpen/board/tonightsBullpenBoardView.js')

const containerSource = readFileSync('src/components/bullpen/board/TonightsBullpenBoard.jsx', 'utf8')
const disclosureSource = readFileSync('src/components/UI/Disclosure.jsx', 'utf8')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const visibleText = (html) => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const renderDistribution = (board) => renderToStaticMarkup(React.createElement(BullpenAvailabilityDistribution, { board }))

function renderBoard(boardPayload, { team, workloadRows = [], storyPayload = null, gameContextPayload = null } = {}) {
  const teamRecord = team || boardPayload?.team || { team_id: 1, team_name: 'Test Club', team_abbreviation: 'TST' }
  return renderToStaticMarkup(
    React.createElement(MemoryRouter, null,
      React.createElement(TonightsBullpenBoard, {
        teams: { loading: false, data: [teamRecord] },
        initialSelectedTeam: teamRecord.team_id,
        boardPayload,
        gameContextPayload,
        storyPayload,
        teamReliefWorkPayload: null,
        workloadRows,
      }),
    ),
  )
}

const withheldBoard = (() => {
  const base = makeBoard({ cardsByStatus: { Available: [populatedBoard.groups[0].pitchers[0]] } })
  return {
    ...base,
    total_pitchers: null,
    roster_authority: {
      ...base.roster_authority,
      readiness: {
        capability: 'public_roster_readiness_v1',
        claims_available: false,
        counts_withheld: true,
        reader_limitations: ['Current active-roster coverage could not be verified.'],
      },
      counts: { bullpen_arms: null, inactive_roster_context_count: null, roster_unknown_count: null },
      population: { total_candidates: null, roster_status_coverage: null },
      evidence: { bullpen_arms: [], inactive_roster_context_count: [], roster_unknown_count: [] },
    },
  }
})()

// ── Availability distribution (the new answer-zone element) ─────────────────

test('the compact distribution shows the four public availability groups', () => {
  const text = visibleText(renderDistribution(populatedBoard))
  for (const label of [
    'Available',
    'On Watch',
    'Limited',
    'Unavailable',
  ]) {
    assert.ok(htmlIncludes(text, label), `missing group: ${label}`)
  }
  // The internal engine key is never surfaced as reader vocabulary.
  assert.equal(htmlIncludes(text, 'Avoid'), false)
})

test('distribution counts reconcile with the eligible reliever total', () => {
  const groups = view.getBoardGroups(populatedBoard)
  const totals = view.getBoardTotals(populatedBoard)
  const sum = groups.reduce((acc, group) => acc + group.count, 0)
  assert.equal(sum, totals.total)
  const text = visibleText(renderDistribution(populatedBoard))
  // Fixture: 2 Available, 1 On-Watch, 1 Limited, 1 Heavy, 1 Severe = 6 eligible.
  assert.ok(htmlIncludes(text, 'Eligible relievers 6'))
  assert.ok(htmlIncludes(text, 'Available 2'))
  assert.ok(htmlIncludes(text, 'On Watch 1'))
  assert.ok(htmlIncludes(text, 'Limited 1'))
  assert.ok(htmlIncludes(text, 'Unavailable 2'))
})

test('withheld counts render as unknown, never as zero', () => {
  const totals = view.getBoardTotals(withheldBoard)
  assert.equal(totals.countWithheld, true)
  assert.equal(totals.total, null)
  const text = visibleText(renderDistribution(withheldBoard))
  assert.ok(htmlIncludes(text, 'Eligible relievers: withheld'))
  assert.ok(htmlIncludes(text, '—'))
  assert.equal(htmlIncludes(text, 'Available 0'), false)
  assert.equal(htmlIncludes(text, 'Eligible relievers 0'), false)
})

test('an empty bullpen reports honest zeros, not fabricated evidence', () => {
  const text = visibleText(renderDistribution(emptyBoard))
  assert.ok(htmlIncludes(text, 'Eligible relievers 0'))
  assert.ok(htmlIncludes(text, 'Available 0'))
})

test('the distribution introduces no score, ranking, or recommendation language', () => {
  const text = visibleText(renderDistribution(populatedBoard)).toLowerCase()
  for (const term of ['score', 'rank', 'grade', 'best', 'worst', 'recommend', 'winner', 'prediction']) {
    assert.equal(text.includes(term), false, `leaked term: ${term}`)
  }
})

// ── Answer-zone hierarchy in the Team Board container ───────────────────────

test('the answer comes first: identity/state, then availability, then the deep board', () => {
  const detroitBoard = { ...populatedBoard, team: { team_id: 1, team_name: 'Detroit Tigers', team_abbreviation: 'DET' } }
  const html = renderBoard(detroitBoard)
  const operatingCard = html.indexOf('bullpen operating state')
  const distribution = html.indexOf('aria-label="Bullpen availability distribution"')
  const board = html.indexOf('id="pitcher-lanes"')
  assert.ok(operatingCard > -1 && distribution > -1 && board > -1)
  assert.ok(operatingCard < distribution, 'state card precedes the distribution')
  assert.ok(distribution < board, 'distribution precedes the full board')
  // Team identity reaches the answer zone. Since UX-002 the /bullpen page
  // heading owns the visible club name, so within the board itself identity
  // travels on the operating card's region label and the board section heading
  // rather than a second card title. bullpenPageIdentity.test.mjs pins that
  // split; this only asserts the team is still identified here at all.
  assert.ok(htmlIncludes(html, 'Detroit Tigers'))
})

test('the full bullpen board and its pitcher-lanes anchor remain visible (not collapsed)', () => {
  const html = renderBoard(populatedBoard)
  // The board anchor targeted by the operating card CTA is preserved.
  assert.ok(htmlIncludes(html, 'id="pitcher-lanes"'))
  assert.ok(htmlIncludes(html, 'Active Bullpen'))
})

test('meaningful what-changed content is promoted while absent game context stays out of the way', () => {
  const html = renderBoard(populatedBoard, { storyPayload: {
    story_available: true,
    headline: 'The late-inning path changed',
    observation: 'Two rested arms returned to the active group.',
  } })
  assert.ok(htmlIncludes(html, 'What Changed'))
  assert.equal(htmlIncludes(html, 'Game Context'), false)
})

test('freshness and the current state stay visible without opening anything', () => {
  const html = renderBoard(populatedBoard)
  assert.ok(htmlIncludes(html, 'Current Bullpen State'))
  assert.ok(htmlIncludes(html, 'Data through'))
})

test('normal trust chrome is quiet and one page-level data-through stamp remains', () => {
  const allHigh = {
    ...populatedBoard,
    groups: populatedBoard.groups.map(group => ({
      ...group,
      pitchers: group.pitchers.map(card => ({ ...card, confidence: 'high', data_state: 'fresh' })),
    })),
  }
  const text = visibleText(renderBoard(allHigh))
  assert.equal(htmlIncludes(text, 'Read Confidence'), false)
  assert.equal(htmlIncludes(text, 'Workload Data'), false)
  assert.equal((text.match(/Data through/g) || []).length, 1)
  for (const competing of ['Freshness: Current', 'Bullpen data through', 'Bullpen read synced', 'Data Currency', 'Last checked', 'Last data update', 'Generated at', 'Published at']) {
    assert.equal(htmlIncludes(text, competing), false, `competing freshness chrome leaked: ${competing}`)
  }
})

test('degraded arm trust stays visible while observed rest and seven-day pitches are promoted', () => {
  const html = renderBoard(populatedBoard, {
    workloadRows: [{
      pitcher: { id: 3, full_name: 'Marty Monitor' },
      days_since_last_appearance: 1,
      pitches_last_7_days: 34,
    }],
  })
  assert.ok(htmlIncludes(html, 'Read Confidence'))
  assert.ok(htmlIncludes(html, 'Days rest'))
  assert.ok(htmlIncludes(html, 'Pitches / 7d'))
  assert.match(html, /Days rest<\/span>\s*<span[^>]*>1<\/span>/)
  assert.ok(htmlIncludes(html, '>34<'))
})

test('missing arm facts render unavailable and never become zero', () => {
  const board = makeBoard({ cardsByStatus: {
    Available: [{ pitcher_id: 91, name: 'Unknown Work Arm', availability_status: 'Available', confidence: 'high', data_state: 'fresh' }],
  } })
  const html = renderBoard(board)
  const card = html.slice(html.indexOf('Unknown Work Arm'), html.indexOf('Open pitcher context', html.indexOf('Unknown Work Arm')))
  for (const label of ['Last outing', 'Days rest', 'Pitches / 7d']) assert.ok(htmlIncludes(card, label))
  assert.ok((card.match(/Unavailable/g) || []).length >= 3)
  assert.equal(/Days rest<\/span>\s*<span[^>]*>0<\/span>/.test(card), false)
  assert.equal(/Pitches \/ 7d<\/span>\s*<span[^>]*>0<\/span>/.test(card), false)
})

test('incomplete workload evidence and unavailable reads remain explicit', () => {
  const board = makeBoard({ cardsByStatus: {
    Unavailable: [{
      pitcher_id: 92,
      name: 'Incomplete Arm',
      availability_status: 'Unavailable',
      availability_public_label: 'Unavailable',
      confidence: 'low',
      data_state: 'incomplete',
      limitations: ['Pitch history is incomplete for this arm.'],
    }],
  } })
  const html = renderBoard(board)
  assert.ok(htmlIncludes(html, 'Availability status: Unavailable'))
  assert.ok(htmlIncludes(html, 'Read Confidence'))
  assert.ok(htmlIncludes(html, 'Workload Data'))
  assert.ok(htmlIncludes(html, 'Pitch history is incomplete for this arm.'))
})

test('sample boards remain clearly identified', () => {
  const sampleBoard = {
    ...populatedBoard,
    freshness: {
      ...populatedBoard.freshness,
      freshness_state: 'sample',
      sync_status: 'metadata_unavailable',
      is_current: false,
    },
  }
  assert.ok(htmlIncludes(renderBoard(sampleBoard), 'Sample data — not live MLB data.'))
})

test('Team State stays canonical and fail-closed state remains unavailable', () => {
  for (const [key, label] of [['fresh', 'Fresh'], ['stretched', 'Stretched'], ['vulnerable', 'Vulnerable']]) {
    const html = renderBoard({ ...populatedBoard, team_state: publicTeamState(key) })
    assert.ok(htmlIncludes(html, label), `missing canonical Team State ${label}`)
  }
  const unavailable = renderBoard({ ...populatedBoard, team_state: failClosedTeamState() })
  assert.ok(htmlIncludes(unavailable, 'A current Team State read is not available'))
  assert.equal(htmlIncludes(unavailable, 'Team State 0'), false)
})

test('opponent context appears before Active Bullpen when governed data exists', () => {
  const html = renderBoard(populatedBoard, { gameContextPayload: {
    capability: 'team_game_context',
    available: true,
    state: 'stored_game_log',
    data_source: 'game_log',
    team: populatedBoard.team,
    opponent: 'Rival Club',
    opponent_abbreviation: 'RIV',
    game_date: '2026-06-04',
    freshness: populatedBoard.freshness,
  } })
  assert.ok(html.indexOf('Rival Club') > -1)
  assert.ok(html.indexOf('Rival Club') < html.indexOf('Active Bullpen'))
})

test('Why this read stays closed after roster context while evidence remains reachable', () => {
  const html = renderBoard(populatedBoard)
  const labelIndex = html.indexOf('<span>Why this read?</span>')
  const detailsStart = html.lastIndexOf('<details', labelIndex)
  const disclosureTag = html.slice(detailsStart, html.indexOf('>', detailsStart) + 1)
  assert.ok(labelIndex > -1 && detailsStart > -1)
  assert.equal(/\sopen(?:=|\s|>)/.test(disclosureTag), false)
  assert.ok(labelIndex > html.indexOf('Active Bullpen'))
  assert.ok(htmlIncludes(html, 'Evidence'))
  assert.ok(htmlIncludes(html, 'Methodology'))
})

test('a material team limitation stays visible before the deferred trust disclosure', () => {
  const board = makeBoard({
    cardsByStatus: { Available: [populatedBoard.groups[0].pitchers[0]] },
    limitations: ['Current roster evidence is incomplete for one named reliever.'],
  })
  const html = renderBoard(board)
  const limitationIndex = html.indexOf('Current roster evidence is incomplete for one named reliever.')
  assert.ok(limitationIndex > -1)
  assert.ok(limitationIndex < html.indexOf('Why this read?'))
  assert.ok(htmlIncludes(html, 'Limited read'))
})

test('team selection is a single accessible control and arm explanations use native disclosure', () => {
  const html = renderBoard(populatedBoard)
  assert.match(html, /<select[^>]*aria-label="Select team for Team Board"/)
  assert.match(html, /<label[^>]*for="team-board-selector"[^>]*>Team<\/label>/)
  assert.ok(containerSource.includes('min-h-11'))
  assert.match(html, /<summary[^>]*>[\s\S]*?<span>Why\?<\/span>/)
  assert.ok(disclosureSource.includes("event.key !== 'Enter' && event.key !== ' '"))
  assert.ok(disclosureSource.includes('focus-visible:ring-2'))
  assert.equal(htmlIncludes(visibleText(html), 'Pitcher Search'), false)
})

test('stale data keeps its trust warning visible in the answer zone', () => {
  const html = renderBoard(staleBoard)
  assert.ok(htmlIncludes(html, 'Bullpen availability distribution'))
  // The operating card and board both keep the stale messaging visible.
  assert.ok(htmlIncludes(html, 'Outside Freshness Window') || htmlIncludes(html, 'outside the active freshness window'))
})

test('withheld roster context does not show a completed distribution', () => {
  const html = renderBoard(withheldBoard, { team: { team_id: 1, team_name: 'Test Club', team_abbreviation: 'TST' } })
  assert.ok(htmlIncludes(html, 'Eligible relievers: withheld'))
  assert.equal(htmlIncludes(html, 'Eligible relievers 0'), false)
})

// ── States and team switching ──────────────────────────────────────────────

test('no team selected shows the picker, not a stale answer zone', () => {
  const html = renderToStaticMarkup(
    React.createElement(MemoryRouter, null,
      React.createElement(TonightsBullpenBoard, {
        teams: { loading: false, data: [{ team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' }] },
      }),
    ),
  )
  assert.ok(htmlIncludes(html, 'Pick a team'))
  assert.equal(htmlIncludes(html, 'Bullpen availability distribution'), false)
})

test('the success answer zone is keyed by team so a switch cannot retain prior data', () => {
  // The keyed wrapper remounts on team change; assert two teams render only
  // their own identity, and the source keys the success content by team.
  assert.ok(containerSource.includes('key={selectedTeam}'))
  const tigers = renderBoard({ ...populatedBoard, team: { team_id: 1, team_name: 'Detroit Tigers', team_abbreviation: 'DET' } })
  const yankees = renderBoard({ ...populatedBoard, team: { team_id: 2, team_name: 'New York Yankees', team_abbreviation: 'NYY' } })
  assert.ok(htmlIncludes(tigers, 'Detroit Tigers'))
  assert.equal(htmlIncludes(tigers, 'New York Yankees'), false)
  assert.ok(htmlIncludes(yankees, 'New York Yankees'))
  assert.equal(htmlIncludes(yankees, 'Detroit Tigers'), false)
})
