import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import {
  emptyBoard,
  makeBoard,
  populatedBoard,
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

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const visibleText = (html) => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const renderDistribution = (board) => renderToStaticMarkup(React.createElement(BullpenAvailabilityDistribution, { board }))

function renderBoard(boardPayload, { team } = {}) {
  const teamRecord = team || boardPayload?.team || { team_id: 1, team_name: 'Test Club', team_abbreviation: 'TST' }
  return renderToStaticMarkup(
    React.createElement(MemoryRouter, null,
      React.createElement(TonightsBullpenBoard, {
        teams: { loading: false, data: [teamRecord] },
        initialSelectedTeam: teamRecord.team_id,
        boardPayload,
        gameContextPayload: null,
        storyPayload: null,
        teamReliefWorkPayload: null,
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

test('the distribution shows all four public availability counts in order', () => {
  const text = visibleText(renderDistribution(populatedBoard))
  for (const label of ['Available', 'On Watch', 'Limited', 'Unavailable']) {
    assert.ok(htmlIncludes(text, label), `missing status: ${label}`)
  }
  // The internal Avoid tier is never surfaced separately.
  assert.equal(htmlIncludes(text, 'Avoid'), false)
})

test('distribution counts reconcile with the eligible reliever total', () => {
  const groups = view.getBoardGroups(populatedBoard)
  const totals = view.getBoardTotals(populatedBoard)
  const sum = groups.reduce((acc, group) => acc + group.count, 0)
  assert.equal(sum, totals.total)
  const text = visibleText(renderDistribution(populatedBoard))
  // Fixture: 2 Available, 1 On Watch, 1 Limited, 2 Unavailable = 6 eligible.
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
  // Team identity is shown in the answer zone.
  assert.ok(htmlIncludes(html, 'Detroit Tigers'))
})

test('the full bullpen board and its pitcher-lanes anchor remain visible (not collapsed)', () => {
  const html = renderBoard(populatedBoard)
  // The board anchor targeted by the operating card CTA is preserved.
  assert.ok(htmlIncludes(html, 'id="pitcher-lanes"'))
  assert.ok(htmlIncludes(html, "Tonight&#x27;s Bullpen Board"))
})

test('secondary story and game context move behind clear, labeled disclosures', () => {
  const html = renderBoard(populatedBoard)
  const storyTag = html.match(/<details[^>]*aria-label="Team story"[^>]*>/)?.[0] || ''
  const gameTag = html.match(/<details[^>]*aria-label="Recent game context"[^>]*>/)?.[0] || ''
  assert.ok(storyTag, 'team story is a disclosure')
  assert.ok(gameTag, 'game context is a disclosure')
  // Collapsed by default (native details, no `open`).
  assert.equal(storyTag.includes('open'), false)
  assert.equal(gameTag.includes('open'), false)
  // Descriptive controls, never a generic "More".
  assert.ok(htmlIncludes(html, 'Read the team story'))
  assert.ok(htmlIncludes(html, 'See recent game context'))
})

test('freshness and the current state stay visible without opening anything', () => {
  const html = renderBoard(populatedBoard)
  assert.ok(htmlIncludes(html, 'Current Bullpen State'))
  assert.ok(htmlIncludes(html, 'Freshness'))
  assert.ok(htmlIncludes(html, 'Bullpen data through'))
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
