import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import {
  differingComparison,
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
