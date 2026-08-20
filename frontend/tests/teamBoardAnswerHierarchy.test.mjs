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
import { teamBoardV2Fixture } from './fixtures/teamBoardV2Fixtures.mjs'

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
const bullpenSource = readFileSync('src/components/bullpen/Bullpen.jsx', 'utf8')
const boardViewSource = readFileSync('src/components/bullpen/board/BullpenBoardView.jsx', 'utf8')
const restStatusSource = readFileSync('src/components/bullpen/board/TeamBoardRestStatus.jsx', 'utf8')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const visibleText = (html) => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const renderDistribution = (board) => renderToStaticMarkup(React.createElement(BullpenAvailabilityDistribution, { board }))

const reliefWorkPayload = {
  data_through: '2026-06-04',
  freshness: {
    data_through: '2026-06-04',
    freshness_state: 'current',
    is_current: true,
    label: 'Public bullpen data is current through June 4, 2026.',
  },
  scope_sentence: 'Covers appearances made for TST per official MLB game records.',
  windows: {
    window_7: {
      through: '2026-06-04',
      relief_appearances: 3,
      pitchers_in_relief: 2,
      pitches_total: 42,
      appearances_with_pitches: 3,
      start_relief_unknown: 0,
      sentence: '3 relief appearances in the 7 days through June 4.',
      pitchers_sentence: '2 pitchers appeared in relief in the 7 days through June 4.',
      pitches_sentence: '42 pitches across those 3 relief appearances.',
    },
    window_14: {
      through: '2026-06-04',
      relief_appearances: 5,
      pitchers_in_relief: 3,
      pitches_total: 70,
      appearances_with_pitches: 5,
      start_relief_unknown: 0,
      sentence: '5 relief appearances in the 14 days through June 4.',
      pitchers_sentence: '3 pitchers appeared in relief in the 14 days through June 4.',
      pitches_sentence: '70 pitches across those 5 relief appearances.',
    },
  },
  relief_by_date: [{
    game_date: '2026-06-04',
    sentence: 'June 4 — 2 relief appearances, 2.0 IP, 28 pitches.',
    appearances: [],
  }],
}

function renderBoard(boardPayload, {
  team,
  changesPayload = null,
  gameContextPayload = null,
  teamReliefWorkPayload = reliefWorkPayload,
  teamBoardV2Payload = teamBoardV2Fixture(boardPayload),
} = {}) {
  const teamRecord = team || boardPayload?.team || { team_id: 1, team_name: 'Test Club', team_abbreviation: 'TST' }
  const resolvedTeamBoardV2Payload = {
    ...teamBoardV2Payload,
    recent_relief_work: {
      population_basis: 'official_appearance_team_relief_appearances',
      read: teamReliefWorkPayload,
    },
    section_status: {
      ...teamBoardV2Payload.section_status,
      recent_relief_work: {
        status: teamReliefWorkPayload ? 'available' : 'unavailable',
        reason_code: teamReliefWorkPayload ? null : 'recent_relief_work_unavailable',
        limitations: [],
        represented_date: teamReliefWorkPayload?.data_through || null,
      },
    },
  }
  return renderToStaticMarkup(
    React.createElement(MemoryRouter, null,
      React.createElement(TonightsBullpenBoard, {
        teams: { loading: false, data: [teamRecord] },
        initialSelectedTeam: teamRecord.team_id,
        boardPayload,
        teamBoardV2Payload: resolvedTeamBoardV2Payload,
        gameContextPayload,
        changesPayload,
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

test('the v2 answer comes first, followed by the unchanged deep board', () => {
  const detroitBoard = { ...populatedBoard, team: { team_id: 1, team_name: 'Detroit Tigers', team_abbreviation: 'DET' } }
  const html = renderBoard(detroitBoard)
  const answer = html.indexOf('data-testid="team-board-answer-block"')
  const board = html.indexOf('id="pitcher-lanes"')
  assert.ok(answer > -1 && board > -1)
  assert.ok(answer < board, 'v2 answer precedes the legacy board')
  assert.ok(htmlIncludes(html, 'Detroit Tigers'))
  assert.equal(htmlIncludes(html, 'Bullpen availability distribution'), false)
})

test('the full bullpen board and its pitcher-lanes anchor remain visible (not collapsed)', () => {
  const html = renderBoard(populatedBoard)
  // The board anchor targeted by the operating card CTA is preserved.
  assert.ok(htmlIncludes(html, 'id="pitcher-lanes"'))
  assert.ok(htmlIncludes(html, 'Active Bullpen'))
})

test('meaningful structured changes are promoted while absent game context stays out of the way', () => {
  const html = renderBoard(populatedBoard, { changesPayload: {
    capability: 'what_changed_since_last_game',
    state: 'changes',
    comparison: { anchor_game_date: '2026-06-03', current_game_date: '2026-06-04' },
    pitcher_changes: [{
      type: 'appearance', pitcher_id: 1, pitcher_name: 'Test Reliever',
      game_date: '2026-06-04', pitches: 18, summary: 'Pitched Thursday - 18 pitches.',
    }],
    limitations: [],
  } })
  assert.ok(htmlIncludes(html, 'What Changed'))
  assert.equal(htmlIncludes(html, 'Game Context'), false)
  assert.ok(html.indexOf('Active Bullpen') < html.indexOf('What Changed'))
  assert.ok(html.indexOf('Active Bullpen') < html.indexOf('Recent Usage'))
  assert.ok(html.indexOf('Recent Usage') < html.indexOf('What Changed'))
  assert.ok(html.indexOf('What Changed') < html.indexOf('Recent Relief Work'))
})

test('Recent Usage owns governed window summaries and the latest published arm list', () => {
  const teamReliefWorkPayload = {
    ...reliefWorkPayload,
    relief_by_date: [{
      ...reliefWorkPayload.relief_by_date[0],
      appearances: [{ pitcher_id: 91, pitcher_full_name: 'Chronology Reliever' }],
    }],
  }
  const html = renderBoard(populatedBoard, { teamReliefWorkPayload })
  const recentStart = html.indexOf('Recent Usage')
  const detailStart = html.indexOf('Recent Relief Work')
  const recentSection = html.slice(recentStart, detailStart)

  assert.ok(htmlIncludes(recentSection, 'Chronology Reliever'))
  assert.ok(htmlIncludes(recentSection, 'Jun 4, 2026'))
  assert.ok(htmlIncludes(recentSection, reliefWorkPayload.windows.window_7.sentence))
  assert.ok(htmlIncludes(recentSection, reliefWorkPayload.windows.window_14.sentence))
  assert.equal(htmlIncludes(recentSection, 'Yesterday'), false)
  for (const group of populatedBoard.groups) {
    for (const card of group.pitchers) {
      assert.equal(htmlIncludes(recentSection, card.name), false)
    }
  }
})

test('freshness and the current state stay visible without opening anything', () => {
  const html = renderBoard(populatedBoard)
  assert.ok(htmlIncludes(html, 'Team State'))
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

test('backend arm read and authorized workload facts stay visible in the migrated row', () => {
  const board = {
    ...populatedBoard,
    groups: populatedBoard.groups.map(group => ({
      ...group,
      pitchers: group.pitchers.map(card => card.pitcher_id === 3 ? {
        ...card,
        workload_facts: {
          days_since_last_appearance: 1,
          appearances_last_7: 3,
          pitches_last_7_days: 34,
          back_to_back: true,
        },
      } : card),
    })),
  }
  const html = renderBoard(board)
  const start = html.indexOf('Marty Monitor')
  const end = html.indexOf('Open pitcher', start)
  const card = html.slice(start, end)
  assert.ok(htmlIncludes(card, 'Watch Arm'))
  assert.ok(htmlIncludes(card, '1d rest'))
  assert.ok(htmlIncludes(card, '34 p (7d)'))
  assert.ok(htmlIncludes(card, '3 app'))
  assert.ok(htmlIncludes(card, 'B2B'))
  assert.equal(htmlIncludes(card, 'Read Confidence'), false)
})

test('missing arm facts are withheld and never become zero', () => {
  const board = makeBoard({ cardsByStatus: {
    Available: [{ pitcher_id: 91, name: 'Unknown Work Arm', availability_status: 'Available', confidence: 'high', data_state: 'fresh' }],
  } })
  const html = renderBoard(board)
  const card = html.slice(html.indexOf('Unknown Work Arm'), html.indexOf('Open pitcher', html.indexOf('Unknown Work Arm')))
  assert.ok(htmlIncludes(card, '— rest'))
  assert.ok(htmlIncludes(card, '— app'))
  assert.ok(htmlIncludes(card, '— p (7d)'))
  assert.equal(htmlIncludes(card, '0 pitches'), false)
  assert.equal(htmlIncludes(card, '0 app'), false)
})

test('false and null back-to-back facts stay quiet', () => {
  for (const backToBack of [false, null]) {
    const board = makeBoard({ cardsByStatus: {
      Available: [{
        pitcher_id: 93,
        name: 'Quiet Work Arm',
        availability_status: 'Available',
        confidence: 'high',
        data_state: 'fresh',
        workload_facts: {
          days_since_last_appearance: 2,
          appearances_last_7: 1,
          pitches_last_7_days: 12,
          back_to_back: backToBack,
        },
      }],
    } })
    assert.equal(htmlIncludes(renderBoard(board), 'Worked back-to-back'), false)
  }
})

test('Team Board owns no fatigue request or fatigue-row join while Finder retains its request', () => {
  assert.equal(containerSource.includes('workloadRows'), false)
  assert.equal(boardViewSource.includes('workloadRows'), false)
  assert.equal(boardViewSource.includes('workloadByPitcher'), false)
  assert.equal(containerSource.includes('getFatigueScores'), false)
  assert.ok(bullpenSource.indexOf('getFatigueScores(params)') > bullpenSource.indexOf('function PitcherView'))
})

test('summary, Rest Status, and Workload Overview use governed board reads', () => {
  const board = {
    ...populatedBoard,
    rest_status: {
      available: true,
      active_arm_count: 6,
      rested_arm_count: 3,
      worked_yesterday_count: 2,
      back_to_back_count: 1,
      summary: '3 of 6 active bullpen arms have at least one full day of rest; 2 arms worked yesterday and 1 arm worked back-to-back.',
      reason_code: null,
    },
    team_shape: {
      cleanOptions: { label: 'Stable Rested Options', summary: 'Several rested options remain available.', reasons: [] },
      workloadConcentration: { label: 'Shared Recent Work', summary: 'Recent relief work is spread across the bullpen.', reasons: [] },
    },
  }
  const html = renderBoard(board)
  for (const copy of [
    'Rest Status',
    '3 of 6 active bullpen arms have at least one full day of rest',
    'Workload Overview',
    'Shared Recent Work',
    'Recent relief work is spread across the bullpen.',
  ]) assert.ok(htmlIncludes(html, copy), `missing governed copy: ${copy}`)
  assert.equal(htmlIncludes(html, 'Resource Health'), false)
})

test('unavailable and malformed Rest Status fail closed without zero counts or reason codes', () => {
  assert.equal(restStatusSource.includes('getBoardGroups'), false)
  assert.equal(restStatusSource.includes('.reduce('), false)
  for (const rest_status of [
    { available: false, active_arm_count: null, rested_arm_count: null, worked_yesterday_count: null, back_to_back_count: null, summary: null, reason_code: 'workload_evidence_incomplete' },
    { available: true, active_arm_count: 6, rested_arm_count: null, worked_yesterday_count: 0, back_to_back_count: 0, summary: 'Malformed.' },
    { available: true, active_arm_count: 6, rested_arm_count: 3, worked_yesterday_count: 0, back_to_back_count: 0, summary: null },
  ]) {
    const html = renderBoard({ ...populatedBoard, rest_status })
    const start = html.indexOf('Rest Status')
    const end = html.indexOf('Workload Overview', start)
    const section = html.slice(start, end)
    assert.ok(htmlIncludes(section, 'Rest Status unavailable'))
    assert.equal(htmlIncludes(section, '>0<'), false)
    assert.equal(htmlIncludes(section, 'workload_evidence_incomplete'), false)
  }
})

test('incomplete workload evidence and Limited Read remain explicit', () => {
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
  assert.ok(htmlIncludes(html, 'Unavailable'))
  assert.ok(htmlIncludes(html, 'Limited Read'))
  assert.match(html, /active-arm-read__marker--ring/)
  assert.equal(htmlIncludes(html, 'Read Confidence'), false)
  assert.equal(htmlIncludes(html, 'Workload Data'), false)
  assert.equal(htmlIncludes(html, 'Pitch history is incomplete for this arm.'), false)
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

test('Why this read stays closed in the header while evidence remains reachable', () => {
  const html = renderBoard(populatedBoard)
  const labelIndex = html.indexOf('<span>Why this read?</span>')
  const detailsStart = html.lastIndexOf('<details', labelIndex)
  const disclosureTag = html.slice(detailsStart, html.indexOf('>', detailsStart) + 1)
  assert.ok(labelIndex > -1 && detailsStart > -1)
  assert.equal(/\sopen(?:=|\s|>)/.test(disclosureTag), false)
  assert.ok(labelIndex < html.indexOf('Bullpen Summary'))
  assert.ok(labelIndex < html.indexOf('Active Bullpen'))
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

test('team selection is accessible and per-pitcher Why disclosures are retired', () => {
  const html = renderBoard(populatedBoard)
  assert.match(html, /<select[^>]*aria-label="Select team for Team Board"/)
  assert.match(html, /<label[^>]*for="team-board-selector"[^>]*>Team<\/label>/)
  assert.ok(containerSource.includes('min-h-11'))
  assert.equal(/<summary[^>]*>[\s\S]*?<span>Why\?<\/span>/.test(html), false)
  assert.match(html, /<button[^>]*aria-label="Open pitcher context for /)
  assert.equal(htmlIncludes(visibleText(html), 'Pitcher Search'), false)
})

test('stale data keeps its trust warning visible in the answer zone', () => {
  const html = renderBoard(staleBoard)
  assert.ok(htmlIncludes(html, 'Limited read'))
  assert.ok(htmlIncludes(html, 'Limited read'))
})

test('withheld roster context does not show a completed distribution', () => {
  const html = renderBoard(withheldBoard, { team: { team_id: 1, team_name: 'Test Club', team_abbreviation: 'TST' } })
  assert.ok(htmlIncludes(html, 'Limited read'))
  assert.ok(visibleText(html).includes('Active arms — Not published'))
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
