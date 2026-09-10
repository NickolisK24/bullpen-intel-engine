// SEC-001 / #595 — no public frontend path depends on internal fatigue scoring.
//
// The backend stopped publishing the 0-100 composite, its component sub-scores,
// the internal risk tier, and the score row's database identifiers. Two things
// have to stay true on this side of the wire:
//
//   1. The public surfaces still render from the narrowed payload — the finder
//      rows, the pitcher detail, and the board cards all work with the removed
//      fields genuinely absent, not merely unused.
//   2. No score presentation, score-derived label, or score fallback creeps
//      back in. The UI was de-scored on purpose; the API contract now backs
//      that up, and this file is what keeps them aligned.

import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
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

const { getBoardCardView } = await server.ssrLoadModule(
  '/src/components/bullpen/board/tonightsBullpenBoardView.js',
)
const { sortRelieverRows } = await server.ssrLoadModule(
  '/src/components/bullpen/relieverFinderView.js',
)
const { PitcherDetailContent } = await server.ssrLoadModule(
  '/src/components/bullpen/PitcherDetail.jsx',
)

// The exact fields the public API no longer returns.
const REMOVED_API_FIELDS = [
  'raw_score',
  'fatigue_score',
  'avg_fatigue_score',
  'pitch_count_score',
  'rest_days_score',
  'appearances_score',
  'leverage_score',
  'innings_score',
  'risk_level',
  'fatigue_risk_level',
  'risk_breakdown',
]

// A narrowed GET /api/bullpen/fatigue row, exactly as the API now returns it.
const narrowedFinderRow = Object.freeze({
  calculated_at: '2026-06-05T11:00:00',
  days_since_last_appearance: 2,
  appearances_last_7: 3,
  appearances_last_14: 5,
  pitches_last_7_days: 41,
  innings_last_7_days: 3.0,
  pitcher: {
    id: 77,
    mlb_id: 605400,
    full_name: 'Narrowed Contract Arm',
    team_name: 'Detroit Tigers',
    team_abbreviation: 'DET',
    position: 'P',
    throws: 'R',
  },
  availability: {
    availability_status: 'Limited',
    confidence: 'high',
    data_state: 'fresh',
    reasons: ['29 pitches yesterday', '3 appearances in 5 days'],
    limitations: ['No injury information available'],
    inputs: {
      pitches_yesterday: 29,
      pitches_last_3_days: 41,
      pitches_last_5_days: 41,
      appearances_last_3_days: 2,
      appearances_last_5_days: 3,
      days_rest: 1,
      back_to_back: false,
      three_in_four: true,
      four_in_five: false,
      freshness_state: 'fresh',
      latest_game_date: '2026-06-04',
      reference_date: '2026-06-05',
    },
  },
})

// A narrowed GET /api/bullpen/teams/<id>/board card.
const narrowedBoardCard = Object.freeze({
  pitcher_id: 77,
  name: 'Narrowed Contract Arm',
  availability_status: 'Limited',
  confidence: 'high',
  short_reason: '29 pitches yesterday',
  last_appearance: { game_date: '2026-06-04', pitches: 29 },
  last_workload_appearance: { game_date: '2026-06-04', pitches: 29 },
  data_state: 'fresh',
  reasons: ['29 pitches yesterday'],
  limitations: ['No injury information available'],
  role: 'setup_bridge',
  pitcher_labels: {
    role: { kind: 'role', key: 'bridge_arm', label: 'Setup Arm', source: 'backend:test' },
    read: { kind: 'read', key: 'rest_restricted', label: 'Rest-Restricted', source: 'backend:test' },
  },
  public_role_read: { key: 'bridge_arm', label: 'Setup Arm', headline: 'Setup Arm' },
  eligibility: null,
  roster_status: null,
  visibility: { is_visible_by_default: true },
})

// A narrowed GET /api/bullpen/fatigue/<id> detail payload.
const narrowedPitcherDetail = Object.freeze({
  pitcher: narrowedFinderRow.pitcher,
  current_fatigue: {
    calculated_at: '2026-06-05T11:00:00',
    days_since_last_appearance: 2,
    appearances_last_7: 3,
    appearances_last_14: 5,
    pitches_last_7_days: 41,
    innings_last_7_days: 3.0,
  },
  availability: narrowedFinderRow.availability,
  workload_signal: narrowedFinderRow.availability,
  roster_status: { status: 'ACTIVE' },
  freshness: { data_through: '2026-06-04', availability_reference_date: '2026-06-05' },
  last_appearance: { game_date: '2026-06-04', pitches: 29 },
  last_workload_appearance: { game_date: '2026-06-04', pitches: 29 },
  recent_logs: [],
  fatigue_trend: [],
})

function keyPathsMatching(value, names, path = '$') {
  if (Array.isArray(value)) {
    return value.flatMap((item, i) => keyPathsMatching(item, names, `${path}[${i}]`))
  }
  if (value && typeof value === 'object') {
    return Object.entries(value).flatMap(([key, child]) => {
      const here = `${path}.${key}`
      const hit = names.includes(key) ? [here] : []
      return [...hit, ...keyPathsMatching(child, names, here)]
    })
  }
  return []
}

// ── The fixtures really are narrowed ────────────────────────────────────────

test('the payload fixtures carry none of the removed API fields', () => {
  for (const [label, payload] of [
    ['finder row', narrowedFinderRow],
    ['board card', narrowedBoardCard],
    ['pitcher detail', narrowedPitcherDetail],
  ]) {
    assert.deepEqual(keyPathsMatching(payload, REMOVED_API_FIELDS), [], label)
  }
})

// ── Consumers work without the removed fields ───────────────────────────────

test('the board card view model renders from a card with no composite', () => {
  const view = getBoardCardView(narrowedBoardCard, { product_current_date: '2026-06-05' })

  assert.equal(view.name, 'Narrowed Contract Arm')
  assert.equal(view.status, 'Limited')
  assert.equal(view.pitcherId, 77)
  assert.equal(view.role.label, 'Setup Arm')
  assert.ok(view.badge)
  // No score survives into the view model, under any name.
  assert.equal('fatigueScore' in view, false)
  assert.equal('score' in view, false)
  assert.equal('riskLevel' in view, false)
})

test('the reliever finder orders narrowed rows by real workload facts', () => {
  const other = {
    ...narrowedFinderRow,
    pitches_last_7_days: 8,
    days_since_last_appearance: 5,
    pitcher: { ...narrowedFinderRow.pitcher, id: 78, full_name: 'Aaron Fresh' },
  }
  const rows = [narrowedFinderRow, other]

  assert.deepEqual(
    sortRelieverRows(rows, 'pitches').map(r => r.pitcher.full_name),
    ['Narrowed Contract Arm', 'Aaron Fresh'],
  )
  assert.deepEqual(
    sortRelieverRows(rows).map(r => r.pitcher.full_name),
    ['Aaron Fresh', 'Narrowed Contract Arm'],
  )
})

test('pitcher detail renders workload facts and availability from the narrowed payload', () => {
  const html = renderToStaticMarkup(
    React.createElement(PitcherDetailContent, {
      data: narrowedPitcherDetail,
      pitcherId: 77,
      onClose: () => {},
    }),
  )

  assert.ok(html.includes('Narrowed Contract Arm'))
  // Counted workload facts still render: pitches and appearances over 7 days.
  assert.ok(html.includes('41'))
  assert.ok(html.includes('Pitches / 7d'))
  assert.equal(html.includes('Recent Workload Snapshot'), false)
  // The 0-100 framing never appears.
  assert.equal(html.includes('0-100'), false)
  assert.equal(/\bWorkload Index\b/.test(html), false)
  assert.equal(/\bRisk\b/.test(html), false)
})

// ── No score plumbing left in the public sources ────────────────────────────

const SOURCE_FORBIDDEN = [
  'raw_score',
  'fatigue_score',
  'fatigueScore',
  'risk_level',
  'riskLevel',
  'RISK_TIERS',
  'RISK_BLURB',
  'FATIGUE_FACTORS',
  'avg_fatigue_score',
  'risk_breakdown',
]

async function sourceFiles(dir) {
  const entries = await readdir(new URL(dir, import.meta.url), { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const child = `${dir}${entry.name}${entry.isDirectory() ? '/' : ''}`
    if (entry.isDirectory()) {
      files.push(...await sourceFiles(child))
    } else if (/\.(js|jsx)$/.test(entry.name)) {
      files.push(child)
    }
  }
  return files
}

test('no frontend source reads a removed fatigue field', async () => {
  const files = await sourceFiles('../src/')
  assert.ok(files.length > 50, 'expected the source sweep to actually find files')

  const offenders = []
  for (const file of files) {
    const source = await readFile(new URL(file, import.meta.url), 'utf8')
    for (const token of SOURCE_FORBIDDEN) {
      if (source.includes(token)) offenders.push(`${file}: ${token}`)
    }
  }

  assert.deepEqual(offenders, [])
})

test('the frontend keeps no local mirror of the internal fatigue model', async () => {
  // src/utils/fatigueModel.js mirrored the backend composite's weights and risk
  // tiers for a score breakdown the UI no longer shows. It is deleted, and a
  // reintroduced copy would be a public score claim by another route.
  const utils = await sourceFiles('../src/utils/')
  assert.equal(utils.some(file => file.endsWith('fatigueModel.js')), false)
})
