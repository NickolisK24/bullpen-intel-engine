import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

import {
  emptyBoard,
  fortyManShownBoard,
  makeBoard,
  populatedBoard,
  rosterContextBoard,
  rosterContextExcludedBoard,
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
const tonightsBullpenBoardSource = readFileSync('src/components/bullpen/board/TonightsBullpenBoard.jsx', 'utf8')
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
  short_reason: 'Roster status: Optioned / Minors.',
  reasons: ['Roster status: Optioned / Minors.'],
  roster_status: {
    ...rosterContextBoard.groups[4].pitchers[2].roster_status,
    raw_status: 'fullRoster',
    source: 'mlb_stats_api:team_assignment_sync:fullRoster',
    evidence: ['Current roster assignment: Optioned / Minors.'],
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
  assert.ok(htmlIncludes(html, 'id="pitcher-lanes"'))
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

test('team board uses compact operating card density', () => {
  assert.ok(tonightsBullpenBoardSource.includes('<BullpenOperatingStateCard'))
  assert.ok(tonightsBullpenBoardSource.includes('density="compact"'))
  assert.ok(tonightsBullpenBoardSource.includes("href: '#pitcher-lanes'"))
})

test('renders bullpen stress from the backend payload', () => {
  const html = render(populatedBoard)

  assert.ok(htmlIncludes(html, 'Overall Availability: Elevated'))
  assert.ok(htmlIncludes(html, 'This pen has less room than usual.'))
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
  // "Today" / "Yesterday" workload labels are relative to the user's current day, injected here
  // for a deterministic test (the populated fixture dates its workloads relative to June 4).
  const html = renderWithOptions({ board: populatedBoard, now: new Date(2026, 5, 4) })
  assert.ok(htmlIncludes(html, 'Larry Limited'))
  assert.ok(htmlIncludes(html, 'Availability status: Limited'))
  assert.ok(htmlIncludes(html, 'Last workload: Today (18 pitches)'))
  assert.ok(htmlIncludes(html, 'Last workload: Yesterday (29 pitches)'))
  assert.ok(htmlIncludes(html, 'Last workload: May 30 (42 pitches)'))
  assert.ok(!htmlIncludes(html, '18 pitches yesterday'))
  assert.ok(htmlIncludes(html, 'Recent Load'))
  assert.ok(htmlIncludes(html, 'Workload Read'))
  assert.ok(htmlIncludes(html, 'Limited Read'))           // confidence formatted
})

test('compact card skips zero-pitch rows for last workload context', () => {
  const cardView = view.getBoardCardView({
    pitcher_id: 44,
    name: 'Taylor Clarke',
    availability_status: 'Available',
    fatigue_score: 12,
    confidence: 'high',
    short_reason: '0 pitches yesterday',
    last_workload_appearance: { game_date: '2026-06-19', pitches: 0 },
    last_appearance: { game_date: '2026-06-17', pitches: 14 },
  }, {
    data_through: '2026-06-20',
  }, new Date(2026, 5, 20))

  assert.equal(cardView.lastAppearanceLabel, 'Last workload: Jun 17 (14 pitches)')
  assert.equal(cardView.shortReason, 'Last workload: Jun 17 (14 pitches)')
  assert.notEqual(cardView.shortReason, 'Last workload: Yesterday (0 pitches)')
})

// Day-aware workload labels (the reported bug): the "Today" / "Yesterday" anchor is the user's
// ACTUAL current day, never the platform data-through date. Scenario: synced at 6am ET on
// June 26 with data through completed games on June 25.
test('last-workload label reads Yesterday for a June 25 workload viewed on June 26', () => {
  const card = {
    pitcher_id: 1,
    name: 'Jane Reliever',
    availability_status: 'Available',
    last_workload_appearance: { game_date: '2026-06-25', pitches: 22 },
  }
  // The platform data-through date is June 25 (it lags one day behind the user's real day).
  // Anchoring on it would wrongly read "Today"; anchoring on the user day (June 26) reads Yesterday.
  const view26 = view.getBoardCardView(card, { data_through: '2026-06-25' }, new Date(2026, 5, 26))
  assert.equal(view26.lastAppearanceLabel, 'Last workload: Yesterday (22 pitches)')
  assert.notEqual(view26.lastAppearanceLabel, 'Last workload: Today (22 pitches)')
})

test('last-workload label reads Today for a June 26 workload viewed on June 26', () => {
  const card = {
    pitcher_id: 2,
    name: 'Joe Reliever',
    availability_status: 'Available',
    last_workload_appearance: { game_date: '2026-06-26', pitches: 15 },
  }
  const cardView = view.getBoardCardView(card, { data_through: '2026-06-25' }, new Date(2026, 5, 26))
  assert.equal(cardView.lastAppearanceLabel, 'Last workload: Today (15 pitches)')
})

test('last-workload label shows a stable date for workloads older than yesterday', () => {
  const card = {
    pitcher_id: 3,
    name: 'Old Reliever',
    availability_status: 'Available',
    last_workload_appearance: { game_date: '2026-06-24', pitches: 31 },
  }
  const cardView = view.getBoardCardView(card, { data_through: '2026-06-25' }, new Date(2026, 5, 26))
  assert.equal(cardView.lastAppearanceLabel, 'Last workload: Jun 24 (31 pitches)')
})

test('the data-through provenance still shows the platform date, not the user current day', () => {
  // The fix changes only the workload-label anchor; the "Data through" provenance is unchanged
  // and continues to reflect the platform data date (June 25), independent of the user's day.
  const provenance = view.getDataProvenance({
    data_through: '2026-06-25', is_current: true, sync_status: 'success',
  })
  assert.ok(/Jun 25|2026-06-25|25/.test(provenance.dataThrough))
  assert.ok(!/Jun 26|June 26/.test(provenance.dataThrough))
})

test('Why? disclosure surfaces engine reasons and limitations', () => {
  const html = renderWithOptions({ board: populatedBoard, now: new Date(2026, 5, 4) })
  assert.ok(htmlIncludes(html, 'Why?'))
  assert.ok(htmlIncludes(html, '18 pitches today'))
  assert.ok(htmlIncludes(html, '29 pitches yesterday'))
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
  assert.ok(htmlIncludes(html, 'No pitchers are currently hidden from the bullpen plan.'))
})

test('stale data surfaces existing trust messaging', () => {
  const html = render(staleBoard)
  assert.ok(htmlIncludes(html, 'Outside Freshness Window'))
  assert.ok(htmlIncludes(html, 'Overall Availability: No Read'))
  assert.ok(htmlIncludes(html, 'Availability note is limited by data freshness.'))
  assert.ok(htmlIncludes(html, 'Limited read - review freshness before treating this as current.'))
  assert.ok(htmlIncludes(html, 'Roster Status Pending'))
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
  assert.ok(htmlIncludes(html, '60-Day IL'))
  assert.ok(htmlIncludes(html, 'Jose Franco'))
  assert.ok(htmlIncludes(html, '40-Man (not active)'))
  assert.ok(htmlIncludes(html, 'Connor Phillips'))
  assert.ok(htmlIncludes(html, 'Optioned / Minors'))
  assert.ok(htmlIncludes(html, 'Availability status: Unavailable'))
  assert.ok(htmlIncludes(html, 'not available for bullpen planning'))
  assert.ok(!htmlIncludes(html, 'Availability status: Available'))
  assert.ok(!htmlIncludes(html, 'Inactive Context'))
  assert.ok(!htmlIncludes(html, 'inactive context'))
})

test('STL-like: broad roster-context count is separated from the shown unavailable cards', () => {
  // The shown count maps exactly to the inspectable Unavailable cards on the board (1); the
  // broader off-roster total (7) lives on Roster Authority. The legacy roster_status summary
  // and getRosterStatusSummaryView that used to carry the shown/not-shown split were retired in CRC-10.
  const unavailableGroup = view.getBoardGroups(rosterContextExcludedBoard)
    .find(group => group.status === 'Unavailable')
  assert.equal(unavailableGroup.pitchers.length, 1)

  // CRC Phase 4: the migrated banner is driven by Roster Authority. It shows ONE
  // invariant "Off the Active Roster" count (7) with a view-only "showing 1 of 7 here",
  // and every one of the seven arms is inspectable in the evidence list.
  const html = render(rosterContextExcludedBoard)
  assert.ok(htmlIncludes(html, 'Off the Active Roster'))
  assert.ok(htmlIncludes(html, 'showing 1 of 7 here'))
  for (const name of [
    'Ike Injured', 'Cal Optioned', 'Dom Designated', 'Ned Nonroster',
    'Saul Suspended', 'Pat Paternity', 'Rex Restricted',
  ]) {
    assert.ok(htmlIncludes(html, name), `evidence missing ${name}`)
  }
  // The legacy "(not shown)" framing is gone — one canonical count plus a view note.
  assert.ok(!htmlIncludes(html, 'Off Roster (not shown)'))
})

test('NYY-like: 40-man (not active) arms shown as cards back the unavailable count', () => {
  // Both inactive arms are shown as cards and are inspectable in the canonical banner; no
  // separate "not shown" line is needed. (The legacy getRosterStatusSummaryView was retired in CRC-10.)
  const html = render(fortyManShownBoard)
  assert.ok(htmlIncludes(html, 'Unavailable Pitchers'))
  assert.ok(htmlIncludes(html, '40-Man (not active)'))
  assert.ok(htmlIncludes(html, 'Milo Marquez'))
  assert.ok(htmlIncludes(html, 'Nate Nunez'))
  assert.ok(!htmlIncludes(html, 'Off Roster (not shown)'))
})

// ── CRC Phase 4: Roster Authority drives the board banner ─────────────────────

test('Roster Authority counts are invariant across board views; only "shown" changes', () => {
  const modes = [
    view.BULLPEN_VIEW_MODE_ACTIVE,
    view.BULLPEN_VIEW_MODE_ACTIVE_PLUS_UNAVAILABLE,
    view.BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY,
  ]
  const authViews = modes.map(mode => {
    const filtered = view.filterBoardForViewMode(rosterContextBoard, mode)
    const rendered = view.getBoardGroups(filtered).flatMap(group => group.pitchers)
    return view.getRosterAuthorityView(filtered.roster_authority, { renderedCards: rendered })
  })

  // Canonical roster counts are byte-identical across every view — filters never move them.
  for (const av of authViews) {
    assert.equal(av.offActiveRoster, 3)
    assert.equal(av.bullpenArms, 0)
    assert.equal(av.rosterStatusPending, 0)
    assert.equal(av.coverageLabel, '100%')
  }
  // The ONLY value that changes with the view is how many off-roster arms are shown.
  assert.equal(authViews[0].shownOffActiveRoster, 0)   // Active hides off-roster cards
  assert.equal(authViews[1].shownOffActiveRoster, 3)   // Active + Unavailable
  assert.equal(authViews[2].shownOffActiveRoster, 3)   // Unavailable Only
})

test('Roster Authority evidence lists match the displayed counts and are inspectable', () => {
  const av = view.getRosterAuthorityView(rosterContextExcludedBoard.roster_authority)
  assert.equal(av.evidence.offActiveRoster.length, av.offActiveRoster)        // 7 == 7
  assert.equal(av.evidence.rosterStatusPending.length, av.rosterStatusPending)
  // The rendered banner exposes every off-roster arm behind the count.
  const html = render(rosterContextExcludedBoard)
  for (const entry of av.evidence.offActiveRoster) {
    assert.ok(htmlIncludes(html, entry.name), `evidence missing ${entry.name}`)
  }
})

test('the board ships no legacy roster_status and the banner reads only Roster Authority', () => {
  // CRC-10: the legacy roster_status board summary is retired. The board carries only the
  // canonical roster_authority, which here describes 1 active arm.
  const board = makeBoard({
    cardsByStatus: { Available: [populatedBoard.groups[0].pitchers[0]] },
  })
  assert.ok(!('roster_status' in board))
  // The banner reflects the AUTHORITY (1 active arm).
  assert.equal(view.getRosterAuthorityView(board.roster_authority).bullpenArms, 1)
  const html = render(board)
  assert.ok(!htmlIncludes(html, '999'))
  assert.ok(htmlIncludes(html, 'Bullpen Arms'))
})

test('getRosterAuthorityView derives shown-in-view without changing canonical counts', () => {
  const onlyIkeRendered = view.getRosterAuthorityView(rosterContextExcludedBoard.roster_authority, {
    renderedCards: [{ pitcher_id: 21 }],
  })
  assert.equal(onlyIkeRendered.offActiveRoster, 7)          // canonical, invariant
  assert.equal(onlyIkeRendered.shownOffActiveRoster, 1)     // view-dependent presentation

  const noCardsSupplied = view.getRosterAuthorityView(rosterContextExcludedBoard.roster_authority)
  assert.equal(noCardsSupplied.offActiveRoster, 7)
  assert.equal(noCardsSupplied.shownOffActiveRoster, null)
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
  assert.ok(htmlIncludes(html, 'Optioned / Minors'))
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

  assert.ok(htmlIncludes(html, 'No relievers are out of the current bullpen plan.'))
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
  assert.equal(view.getBoardCardView(rosterContextBoard.groups[4].pitchers[0]).rosterStatus.label, '60-Day IL')
  assert.equal(view.getBoardCardView(rosterContextBoard.groups[4].pitchers[0]).pitcherLabels.read.label, 'Unavailable')
  assert.equal(view.getBoardCardView(rosterContextBoard.groups[4].pitchers[1]).rosterStatus.label, '40-Man (not active)')
})

test('role authority eligibility caveats render plain labels', () => {
  // Role Authority V1: only the uncertain roles carry a board caveat.
  assert.equal(view.getEligibilityView({ status: 'role_ambiguous', confidence: 'high' }).label, 'Swing Role')
  assert.equal(view.getEligibilityView({ status: 'role_unknown', confidence: 'none' }).label, 'Role Not Established')
  // Relievers are the default population and need no caveat chip.
  assert.equal(view.getEligibilityView({ status: 'role_reliever', confidence: 'high' }), null)
})
