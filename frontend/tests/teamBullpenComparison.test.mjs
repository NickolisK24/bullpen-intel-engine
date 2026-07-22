import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import {
  differingComparison,
  makeComparison,
  similarComparison,
  staleComparison,
} from './fixtures/bullpenComparisonFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { default: BullpenComparisonView } = await server.ssrLoadModule(
  '/src/components/bullpen/board/BullpenComparisonView.jsx',
)
const view = await server.ssrLoadModule(
  '/src/components/bullpen/board/teamBullpenComparisonView.js',
)

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (payload) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, React.createElement(BullpenComparisonView, { payload })),
)

test('renders side-by-side snapshot with both teams and their counts', () => {
  const html = render(differingComparison)
  assert.ok(htmlIncludes(html, 'Side-by-side Bullpen Read'))
  assert.ok(htmlIncludes(html, 'Aces'))
  assert.ok(htmlIncludes(html, 'Bears'))
  assert.ok(htmlIncludes(html, 'Available'))
  assert.ok(htmlIncludes(html, 'Total relievers'))
})

test('comparison snapshot shows one public Unavailable row with combined raw counts', () => {
  const v = view.getComparisonView(differingComparison)
  const unavailableRows = v.snapshot.filter(row => row.label === 'Unavailable')

  assert.deepEqual(v.snapshot.map(row => row.label), [
    'Available',
    'On Watch',
    'Limited',
    'Unavailable',
  ])
  assert.equal(unavailableRows.length, 1)
  assert.equal(unavailableRows[0].valueA, 2)
  assert.equal(unavailableRows[0].valueB, 5)
})

// ── Defect 1: Compare count/percentage consistency ─────────────────────────
// The public "Unavailable" row combines the Avoid and Unavailable groups, so
// its displayed percentage must describe that same combined population. Reading
// pct_unavailable (strict Unavailable only) produced a 0% cell next to a
// non-zero count (e.g. "1 Unavailable of 8, 0%"). Every availability row's
// percentage must reconcile with its displayed count and the total.

// A team with a single Avoid arm (folded into the public Unavailable row) and
// no strict-Unavailable arm — the exact shape that read "1 of 8, 0%".
const countPctComparison = makeComparison(
  { team: { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' }, counts: { Available: 7, Avoid: 1 } },
  { team: { team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA' }, counts: { Available: 6, Avoid: 2 } },
)

function reconcileRows(payload) {
  const v = view.getComparisonView(payload)
  const unavailable = v.snapshot.find(row => row.label === 'Unavailable')
  const available = v.snapshot.find(row => row.label === 'Available')
  return {
    totalA: v.metricsA.total_relievers,
    totalB: v.metricsB.total_relievers,
    unavailableCountA: unavailable.valueA,
    unavailableCountB: unavailable.valueB,
    availableCountA: available.valueA,
    pctUnavailableA: v.metricsA.pct_restricted,
    pctUnavailableB: v.metricsB.pct_restricted,
    pctAvailableA: v.metricsA.pct_available,
  }
}

test('Defect 1: the % Unavailable cell reconciles with the combined Unavailable count (1 of 8)', () => {
  const r = reconcileRows(countPctComparison)
  assert.equal(r.totalA, 8)
  assert.equal(r.unavailableCountA, 1)
  // 1 of 8 rounds to a non-zero percentage — never the 0% the strict
  // pct_unavailable field produced next to a count of 1.
  assert.equal(r.pctUnavailableA, Math.round((1 / 8) * 100))
  assert.notEqual(r.pctUnavailableA, 0)
})

test('Defect 1: rendered % Unavailable shows the reconciled percentage, not 0%', () => {
  const r = reconcileRows(countPctComparison)
  const html = render(countPctComparison)
  // Aces: 1 of 8; Bears: 2 of 8 → 25%. The pre-fix cell showed 0% for both.
  assert.ok(htmlIncludes(html, `${r.pctUnavailableA}%`))
  assert.ok(htmlIncludes(html, `${r.pctUnavailableB}%`))
  assert.equal(htmlIncludes(html, '0%'), false)
})

test('Defect 1: every availability percentage reconciles with its count and total', () => {
  // 0 of 8, 3 of 8 (a non-even fraction), and a fully clean side.
  const payload = makeComparison(
    { team: { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' }, counts: { Available: 5, Avoid: 2, Unavailable: 1 } },
    { team: { team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA' }, counts: { Available: 8 } },
  )
  const r = reconcileRows(payload)
  // Team A: 3 of 8 combined Unavailable → round(37.5) = 38.
  assert.equal(r.totalA, 8)
  assert.equal(r.unavailableCountA, 3)
  assert.equal(r.pctUnavailableA, Math.round((3 / 8) * 100))
  assert.equal(r.pctAvailableA, Math.round((5 / 8) * 100))
  // Team B: 0 of 8 → 0%, and the count is 0, not an invented value.
  assert.equal(r.totalB, 8)
  assert.equal(r.unavailableCountB, 0)
  assert.equal(r.pctUnavailableB, 0)
})

test('Defect 1: an empty (no-data) comparison never shows a count without a matching percentage', () => {
  const payload = makeComparison(
    { team: { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' }, counts: {} },
    { team: { team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA' }, counts: {} },
  )
  const r = reconcileRows(payload)
  assert.equal(r.totalA, 0)
  assert.equal(r.unavailableCountA, 0)
  assert.equal(r.pctUnavailableA, 0)
  // Fail-closed: no relievers means no availability claim, not a fabricated split.
  assert.equal(r.availableCountA, 0)
  assert.equal(r.pctAvailableA, 0)
})

test('renders deterministic comparison observations naming the team with more', () => {
  const html = render(differingComparison)
  assert.ok(htmlIncludes(html, 'The Aces currently have more relievers classified Available.'))
  assert.ok(htmlIncludes(html, 'The Bears currently have more relievers marked Unavailable.'))
  assert.equal(htmlIncludes(html, 'Avoid or Unavailable'), false)
})

test('each observation explains itself with both raw counts', () => {
  const html = render(differingComparison)
  assert.ok(htmlIncludes(html, 'Why?'))
  assert.ok(htmlIncludes(html, 'Aces Available: 6.'))
  assert.ok(htmlIncludes(html, 'Bears Available: 3.'))
})

test('similar distributions read as similar, not as a winner', () => {
  const html = render(similarComparison)
  assert.ok(htmlIncludes(html, 'The bullpens match across every availability group in the current read.'))
})

test('stale bullpen surfaces freshness limitations and degraded confidence', () => {
  const html = render(staleComparison)
  assert.ok(htmlIncludes(html, 'Recent workload unclear — read with caution'))
  assert.ok(htmlIncludes(html, 'Workload Read: Unclear Read'))
  assert.ok(htmlIncludes(html, 'one or both bullpens have degraded freshness'))
  // The board-level freshness limitation text now lives on the linked team
  // boards, not inside the comparison (the boards are no longer embedded).
})

test('links to both team boards instead of embedding two full boards', () => {
  const html = render(differingComparison)
  // phase-0-clarity/03: the comparison compares; the full boards live on the
  // Team Board tab behind links.
  assert.equal(htmlIncludes(html, 'Available group'), false)
  assert.equal(htmlIncludes(html, "Tonight's Bullpen Board"), false)
  assert.ok(htmlIncludes(html, 'Full Team Boards'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=ACE&amp;source=comparison"'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=BEA&amp;source=comparison"'))
  assert.ok(htmlIncludes(html, 'Open the Aces board'))
  assert.ok(htmlIncludes(html, 'Open the Bears board'))
})

test('empty payload prompts for two teams instead of crashing', () => {
  const html = render({})
  assert.ok(htmlIncludes(html, 'Pick two teams to compare'))
})

test('exposes no grading, ranking, or recommendation language', () => {
  const html = render(differingComparison).toLowerCase()
  for (const term of ['best', 'better', 'stronger', 'superior', 'recommend', 'win probability', 'team score', 'bullpen grade', 'ranking_applied']) {
    assert.ok(!html.includes(term), `leaked term: ${term}`)
  }
})

test('getComparisonView maps labels, observations, and degraded confidence', () => {
  const v = view.getComparisonView(differingComparison)
  assert.equal(v.hasComparison, true)
  assert.equal(v.labelA, 'Aces')
  assert.equal(v.observations.length, 3)
  assert.equal(v.observations[0].leader, 'A')

  assert.equal(view.getComparisonView(staleComparison).isDegraded, true)
  assert.equal(view.getComparisonView({}).hasComparison, false)
})

test('a guarded card inherits one Limited Read conclusion through Compare', async () => {
  const { makeBoard } = await import('./fixtures/bullpenBoardFixtures.mjs')
  const boardView = await server.ssrLoadModule(
    '/src/components/bullpen/board/tonightsBullpenBoardView.js',
  )
  const guardedCard = {
    pitcher_id: 51,
    name: 'Paul Conflict',
    availability_status: 'Available',
    role: {
      role_key: 'late_high_leverage',
      role: 'Late-Inning / High-Leverage Pattern',
      confidence: 'high',
      short_reason: 'Recent usage shows late-inning, high-leverage outings.',
      evidence: ['17 appearances in the recent window'],
      limitations: [],
    },
    pitcher_labels: {
      role: { kind: 'role', key: 'limited_read', label: 'Limited Read', source: 'backend:mixed_starter_reliever' },
      read: { kind: 'read', key: 'clean_option', label: 'Rested', source: 'backend:availability_status' },
    },
  }
  const payload = {
    ...differingComparison,
    team_a: makeBoard({
      team: { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' },
      cardsByStatus: { Available: [guardedCard] },
    }),
  }

  // Compare embeds board cards untransformed: the same view adapter resolves
  // the same one public conclusion for the embedded card.
  const embedded = payload.team_a.groups
    .flatMap(group => group.pitchers)
    .find(card => card.name === 'Paul Conflict')
  assert.ok(embedded.public_role_read)
  assert.equal(embedded.public_role_read.key, 'limited_read')
  const cardView = boardView.getBoardCardView(embedded)
  assert.equal(cardView.role.label, 'Limited Read')
  assert.equal(cardView.pitcherLabels.role.label, 'Limited Read')

  // The Compare surface itself introduces no concrete role wording.
  const html = render(payload)
  assert.equal(htmlIncludes(html, 'Late-Inning / High-Leverage Pattern'), false)
  for (const label of ['Trusted Arm', 'Setup Arm', 'Middle Relief Arm', 'Coverage Arm']) {
    assert.equal(htmlIncludes(html, label), false, `Compare leaked ${label}`)
  }
})

test('a legacy guarded card resolves the same safe Limited Read through Compare', async () => {
  const { makeBoard } = await import('./fixtures/bullpenBoardFixtures.mjs')
  const boardView = await server.ssrLoadModule(
    '/src/components/bullpen/board/tonightsBullpenBoardView.js',
  )
  // Legacy payload: guarded chip + conflicting raw role, no public_role_read.
  const legacyGuardedCard = {
    pitcher_id: 52,
    name: 'Legacy Conflict',
    availability_status: 'Available',
    role: {
      role_key: 'late_high_leverage',
      role: 'Late-Inning / High-Leverage Pattern',
      confidence: 'medium',
      short_reason: 'Recent usage shows late-inning, high-leverage outings.',
      evidence: ['17 appearances in the recent window'],
      limitations: [],
    },
    pitcher_labels: {
      role: { kind: 'role', key: 'limited_read', label: 'Limited Read', source: 'backend:mixed_starter_reliever' },
    },
    public_role_read: null,
  }
  const payload = {
    ...differingComparison,
    team_a: makeBoard({
      team: { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' },
      cardsByStatus: { Available: [legacyGuardedCard] },
    }),
  }

  const embedded = payload.team_a.groups
    .flatMap(group => group.pitchers)
    .find(card => card.name === 'Legacy Conflict')
  assert.equal(embedded.public_role_read, null)
  // The same board adapter Compare relies on resolves the same safe verdict.
  const cardView = boardView.getBoardCardView(embedded)
  assert.equal(cardView.role.key, 'limited_read')
  assert.equal(cardView.role.label, 'Limited Read')
  assert.equal(cardView.pitcherLabels.role.label, 'Limited Read')

  const html = render(payload)
  assert.equal(htmlIncludes(html, 'Late-Inning / High-Leverage Pattern'), false)
})
