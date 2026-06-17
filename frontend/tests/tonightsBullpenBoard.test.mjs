import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

import {
  emptyBoard,
  makeBoard,
  populatedBoard,
  rosterContextBoard,
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

const { default: BullpenBoardView } = await server.ssrLoadModule(
  '/src/components/bullpen/board/BullpenBoardView.jsx',
)
const { default: TonightsBullpenBoard } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TonightsBullpenBoard.jsx',
)
const view = await server.ssrLoadModule(
  '/src/components/bullpen/board/tonightsBullpenBoardView.js',
)

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (board) => renderToStaticMarkup(React.createElement(BullpenBoardView, { board }))
const renderWithOptions = (props) => renderToStaticMarkup(React.createElement(BullpenBoardView, props))
const detailsTagFor = (html, ariaLabel) => (
  html.match(new RegExp(`<details[^>]*aria-label="${escapeRegExp(ariaLabel)}"[^>]*>`))?.[0] || ''
)
const pitcherNames = (board) => view.getBoardGroups(board).flatMap(group => (
  group.pitchers.map(card => card.name)
))

const mixedRosterBoard = makeBoard({
  cardsByStatus: {
    Available: populatedBoard.groups[0].pitchers,
    Monitor: staleBoard.groups[1].pitchers,
    Unavailable: [
      populatedBoard.groups[4].pitchers[0],
      ...rosterContextBoard.groups[4].pitchers,
    ],
  },
})

const staleActivatedMinorAssignmentCard = {
  ...rosterContextBoard.groups[4].pitchers[2],
  pitcher_id: 11,
  name: 'Valente Bellozo',
  short_reason: 'Roster status: Minors.',
  reasons: ['Roster status: Minors.'],
  roster_status: {
    ...rosterContextBoard.groups[4].pitchers[2].roster_status,
    raw_status: 'fullRoster',
    source: 'mlb_stats_api:team_assignment_sync:fullRoster',
    evidence: ['Current roster assignment: Minors.'],
  },
}

const staleActivatedAssignmentBoard = makeBoard({
  cardsByStatus: {
    Available: populatedBoard.groups[0].pitchers,
    Unavailable: [staleActivatedMinorAssignmentCard],
  },
})

test('renders all five availability groups in order', () => {
  const html = render(populatedBoard)
  for (const label of ['Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable Pitchers']) {
    assert.ok(htmlIncludes(html, label), `missing group: ${label}`)
  }
  // Available must appear before Unavailable Pitchers on the board.
  assert.ok(html.indexOf('Available') < html.lastIndexOf('Unavailable Pitchers'))
})

test('board view mode control defaults to Active and replaces show-unavailable copy', () => {
  const html = renderToStaticMarkup(React.createElement(TonightsBullpenBoard, {
    teams: {
      loading: false,
      data: [{ team_id: 1, team_name: 'Test Club', team_abbreviation: 'TST' }],
    },
  }))

  assert.ok(htmlIncludes(html, 'View'))
  assert.ok(htmlIncludes(html, 'Active'))
  assert.ok(htmlIncludes(html, 'Active + Unavailable'))
  assert.ok(htmlIncludes(html, 'Unavailable Only'))
  assert.ok(htmlIncludes(html, 'aria-pressed="true"'))
  assert.ok(!htmlIncludes(html, 'Show unavailable pitchers'))
})

test('renders bullpen stress from the backend payload', () => {
  const html = render(populatedBoard)

  assert.ok(htmlIncludes(html, 'Overall Availability: Elevated'))
  assert.ok(htmlIncludes(html, 'Overall bullpen availability is tighter than usual.'))
  assert.ok(htmlIncludes(html, 'Availability classifications are workload-based only.'))
  assert.ok(!htmlIncludes(html, 'Bullpen workload is elevated.'))
  assert.ok(!htmlIncludes(html, 'Stress Score'))
})

test('normal freshness, roster context, and pitcher label key are collapsed by default', () => {
  const html = render(populatedBoard)
  const freshnessTag = detailsTagFor(html, 'Data freshness details')
  const rosterTag = detailsTagFor(html, 'Roster status details')
  const labelKeyTag = detailsTagFor(html, 'Pitcher Label Key')

  assert.ok(freshnessTag)
  assert.ok(rosterTag)
  assert.ok(labelKeyTag)
  assert.ok(!freshnessTag.includes('open'))
  assert.ok(!rosterTag.includes('open'))
  assert.ok(!labelKeyTag.includes('open'))
  assert.ok(htmlIncludes(html, 'Data Freshness'))
  assert.ok(htmlIncludes(html, 'Roster Context'))
  assert.ok(htmlIncludes(html, 'Role and read definitions'))
})

test('renders pitcher cards with name, status, fatigue, confidence and short reason', () => {
  const html = render(populatedBoard)
  assert.ok(htmlIncludes(html, 'Larry Limited'))
  assert.ok(htmlIncludes(html, 'Availability status: Limited'))
  assert.ok(htmlIncludes(html, '29 pitches yesterday'))   // short reason
  assert.ok(htmlIncludes(html, 'Fatigue'))
  assert.ok(htmlIncludes(html, 'Workload Read'))
  assert.ok(htmlIncludes(html, 'Limited Read'))           // confidence formatted
})

test('Why? disclosure surfaces engine reasons and limitations', () => {
  const html = render(populatedBoard)
  assert.ok(htmlIncludes(html, 'Why?'))
  assert.ok(htmlIncludes(html, '3 appearances in 5 days'))           // a reason
  assert.ok(htmlIncludes(html, 'No injury information available'))   // a limitation
})

test('empty board shows a friendly empty state, not a blank surface', () => {
  const html = render(emptyBoard)
  assert.ok(htmlIncludes(html, 'No pitchers to show for this team'))
})

test('groups with no pitchers render their own empty copy', () => {
  // Only the Available group is populated; the other four are empty.
  const board = makeBoard({
    cardsByStatus: { Available: populatedBoard.groups[0].pitchers },
  })
  const html = render(board)
  assert.ok(htmlIncludes(html, 'No unavailable pitchers are shown right now.'))
})

test('stale data surfaces existing trust messaging', () => {
  const html = render(staleBoard)
  assert.ok(htmlIncludes(html, 'Outside Freshness Window'))
  assert.ok(htmlIncludes(html, 'Overall Availability: No Read'))
  assert.ok(htmlIncludes(html, 'Overall availability read is limited by data freshness.'))
  assert.ok(htmlIncludes(html, 'Limited read - review freshness before treating this as current.'))
  assert.ok(htmlIncludes(html, 'Roster Unknown'))
  assert.ok(htmlIncludes(html, 'Roster status unavailable'))
  assert.ok(htmlIncludes(html, 'Bullpen Arms'))
  assert.ok(htmlIncludes(html, 'Roster Status Coverage'))
  assert.ok(htmlIncludes(html, 'outside the active freshness window'))
  assert.ok(htmlIncludes(html, 'Outside active freshness window'))
  assert.ok(htmlIncludes(html, 'Historical baseball data through 2026-04-01.'))
  assert.ok(!htmlIncludes(html, 'Inactive Context'))
})

test('unavailable roster pitchers render status labels without active availability', () => {
  const html = render(rosterContextBoard)
  assert.ok(htmlIncludes(html, 'Unavailable Pitchers'))
  assert.ok(htmlIncludes(html, 'Graham Ashcraft'))
  assert.ok(htmlIncludes(html, 'IL-60'))
  assert.ok(htmlIncludes(html, 'Jose Franco'))
  assert.ok(htmlIncludes(html, '40-Man Only'))
  assert.ok(htmlIncludes(html, 'Connor Phillips'))
  assert.ok(htmlIncludes(html, 'Minors'))
  assert.ok(htmlIncludes(html, 'Availability status: Unavailable'))
  assert.ok(htmlIncludes(html, 'not available for bullpen planning'))
  assert.ok(!htmlIncludes(html, 'Availability status: Available'))
  assert.ok(!htmlIncludes(html, 'Inactive Context'))
  assert.ok(!htmlIncludes(html, 'inactive context'))
})

test('Active view shows active relievers and hides roster-status unavailable relievers', () => {
  const filtered = view.filterBoardForViewMode(mixedRosterBoard, view.BULLPEN_VIEW_MODE_ACTIVE)
  const names = pitcherNames(filtered)

  assert.ok(names.includes('Zane Available'))
  assert.ok(names.includes('Uri Unavailable'))
  assert.ok(!names.includes('Stale Sam'))
  assert.ok(!names.includes('Graham Ashcraft'))
  assert.ok(!names.includes('Jose Franco'))
  assert.equal(view.getBoardTotals(filtered).total, 3)
})

test('Active + Unavailable view shows active and roster-status unavailable relievers', () => {
  const filtered = view.filterBoardForViewMode(
    mixedRosterBoard,
    view.BULLPEN_VIEW_MODE_ACTIVE_PLUS_UNAVAILABLE,
  )
  const names = pitcherNames(filtered)

  assert.ok(names.includes('Zane Available'))
  assert.ok(names.includes('Stale Sam'))
  assert.ok(names.includes('Graham Ashcraft'))
  assert.ok(names.includes('Jose Franco'))
  assert.equal(view.getBoardTotals(filtered).total, 7)
})

test('Unavailable Only view shows roster-status unavailable relievers only', () => {
  const filtered = view.filterBoardForViewMode(
    mixedRosterBoard,
    view.BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY,
  )
  const names = pitcherNames(filtered)

  assert.deepEqual(names, ['Graham Ashcraft', 'Jose Franco', 'Connor Phillips'])
  assert.equal(view.getBoardTotals(filtered).total, 3)
})

test('Unavailable Only does not treat active rested or workload-unavailable relievers as roster unavailable', () => {
  const staleOnly = view.filterBoardForViewMode(staleBoard, view.BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY)
  const workloadUnavailableOnly = view.filterBoardForViewMode(
    populatedBoard,
    view.BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY,
  )

  assert.deepEqual(pitcherNames(staleOnly), [])
  assert.deepEqual(pitcherNames(workloadUnavailableOnly), [])
})

test('Unavailable Only does not show corrected current-minors assignment as active', () => {
  const activeOnly = view.filterBoardForViewMode(
    staleActivatedAssignmentBoard,
    view.BULLPEN_VIEW_MODE_ACTIVE,
  )
  const unavailableOnly = view.filterBoardForViewMode(
    staleActivatedAssignmentBoard,
    view.BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY,
  )

  assert.ok(!pitcherNames(activeOnly).includes('Valente Bellozo'))
  assert.deepEqual(pitcherNames(unavailableOnly), ['Valente Bellozo'])
  assert.equal(view.isActiveRosterCard(staleActivatedMinorAssignmentCard), false)

  const html = render(unavailableOnly)
  assert.ok(htmlIncludes(html, 'Minors'))
  assert.ok(!htmlIncludes(html, 'Active MLB'))
})

test('Unavailable Only empty state appears without showing active relievers', () => {
  const filtered = view.filterBoardForViewMode(
    populatedBoard,
    view.BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY,
  )
  const html = renderWithOptions({
    board: filtered,
    emptyState: view.getBullpenViewModeEmptyState(view.BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY),
  })

  assert.ok(htmlIncludes(html, 'No unavailable relievers found for this bullpen.'))
  assert.ok(!htmlIncludes(html, 'Zane Available'))
  assert.ok(!htmlIncludes(html, 'Uri Unavailable'))
})

test('team switching reflects the selected team in the heading', () => {
  const angels = render(makeBoard({ team: { team_id: 1, team_name: 'Anaheim', team_abbreviation: 'ANA' } }))
  const yanks = render(makeBoard({ team: { team_id: 2, team_name: 'New York', team_abbreviation: 'NYY' } }))
  assert.ok(htmlIncludes(angels, 'Anaheim'))
  assert.ok(!htmlIncludes(angels, 'New York'))
  assert.ok(htmlIncludes(yanks, 'New York'))
})

test('does not expose raw governance fields or jargon on the baseball surface', () => {
  const html = render(populatedBoard).toLowerCase()
  for (const term of ['ranking_applied', 'selection_made', 'contract', 'governance', 'fail_closed', 'certified']) {
    assert.ok(!html.includes(term), `leaked governance term: ${term}`)
  }
})

test('view helpers group, total, and detect stale freshness deterministically', () => {
  const groups = view.getBoardGroups(populatedBoard)
  assert.deepEqual(groups.map(g => g.status), ['Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable'])

  const totals = view.getBoardTotals(populatedBoard)
  assert.equal(totals.total, 6)
  assert.equal(totals.isEmpty, false)
  assert.equal(view.getBoardTotals(emptyBoard).isEmpty, true)

  assert.equal(view.getBoardFreshnessView(populatedBoard.freshness).isStale, false)
  assert.equal(view.getBoardFreshnessView(staleBoard.freshness).isStale, true)
  assert.equal(view.getBullpenStressView(populatedBoard.stress).label, 'Elevated')
  assert.equal(view.getBullpenStressView(staleBoard.stress).label, 'No Read')
  assert.equal(view.getBullpenStressView(staleBoard.stress).isLimited, true)
  assert.equal(view.getBoardCardView(staleBoard.groups[1].pitchers[0]).eligibility.label, 'Outside Freshness Window')
  assert.equal(view.getBoardCardView(staleBoard.groups[1].pitchers[0]).rosterStatus.label, 'Roster Unknown')
  assert.equal(view.getBoardCardView(staleBoard.groups[1].pitchers[0]).pitcherLabels.read.label, 'Limited Read')
  assert.equal(view.getBoardCardView(rosterContextBoard.groups[4].pitchers[0]).rosterStatus.label, 'IL-60')
  assert.equal(view.getBoardCardView(rosterContextBoard.groups[4].pitchers[0]).pitcherLabels.read.label, 'Unavailable')
  assert.equal(view.getBoardCardView(rosterContextBoard.groups[4].pitchers[1]).rosterStatus.label, '40-Man Only')
  assert.equal(view.getRosterStatusSummaryView(staleBoard.roster_status).label, 'Roster status unavailable')
  assert.equal(view.getRosterStatusSummaryView(rosterContextBoard.roster_status).unavailablePitchersCount, 3)
  assert.equal(view.getRosterStatusSummaryView(rosterContextBoard.roster_status).coverageLabel, '100%')
})

test('role authority eligibility caveats render plain labels', () => {
  // Role Authority V1: only the uncertain roles carry a board caveat.
  assert.equal(view.getEligibilityView({ status: 'role_ambiguous', confidence: 'high' }).label, 'Swing Role')
  assert.equal(view.getEligibilityView({ status: 'role_unknown', confidence: 'none' }).label, 'Role Not Established')
  // Relievers are the default population and need no caveat chip.
  assert.equal(view.getEligibilityView({ status: 'role_reliever', confidence: 'high' }), null)
})
