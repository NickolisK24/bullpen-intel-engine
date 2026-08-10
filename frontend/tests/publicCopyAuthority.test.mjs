// FE-001 / #591 — the frontend renders backend-authored public copy verbatim.
//
// The old contract was "the browser will clean this up." These tests assert the
// new one: whatever the backend published for State, Why and Evidence reaches
// the reader unchanged, the Why cannot vanish quietly, and no semantic
// vocabulary mapping is left in the frontend for the governed board path.

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

import { makeBoard } from './fixtures/bullpenBoardFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { toOperatingStateReadModel, getTeamOperatingStateContext } =
  await server.ssrLoadModule('/src/adapters/operatingStateReadModel.js')
const { default: BullpenOperatingStateCard } =
  await server.ssrLoadModule('/src/components/bullpen/BullpenOperatingStateCard.jsx')
const {
  getCopySuppressionCounts,
  getCopySuppressionTotal,
  recordCopySuppression,
  resetCopySuppressionCounts,
} = await server.ssrLoadModule('/src/utils/copySuppressionAccounting.js')

const currentFreshness = {
  data_through: '2026-06-26',
  last_successful_sync: '2026-06-26T10:04:00Z',
  is_current: true,
  sync_status: 'success',
}

// Deliberately awkward but entirely legal backend copy: an em dash, a comma
// splice, a percentage, a number that is not spelled out, and a trailing
// clause. Any rewrite layer — normalising punctuation, re-casing, re-wording —
// shows up as a diff here.
const UNUSUAL_BUT_VALID_WHY =
  'The bullpen is short on rested arms right now — 3 of 8 arms are limited or unavailable, and two more are close.'

function boardWith(why, { reasons = [], limitations = [] } = {}) {
  return makeBoard({
    team: { team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM' },
    cardsByStatus: {
      Available: [{ pitcher_id: 1, name: 'A1', availability_status: 'Available' }],
      Monitor: [{ pitcher_id: 2, name: 'M1', availability_status: 'Monitor' }],
    },
    freshness: currentFreshness,
    // Mirrors the real board/dashboard context block: the Why is
    // context.health.label and its evidence is context.health.reasons.
    context: {
      metrics: { total_relievers: 2, available: 1, monitor: 1, limited: 0, avoid: 0, unavailable: 0 },
      health: { state: 'constrained', label: why, reasons },
      confidence: 'high',
      limitations,
    },
  })
}

function renderCard(model, density = 'full') {
  return renderToStaticMarkup(
    React.createElement(BullpenOperatingStateCard, { readModel: model, density }),
  )
}

function visibleText(html) {
  return html.replace(/<[^>]*>/g, ' ').replace(/&#x27;/g, "'").replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&').replace(/&mdash;/g, '—').replace(/\s+/g, ' ').trim()
}

// ── E1: verbatim rendering ──────────────────────────────────────────────────

test('an unusual but valid backend Why survives the adapter character for character', () => {
  const model = toOperatingStateReadModel(boardWith(UNUSUAL_BUT_VALID_WHY), { scope: 'league' })

  assert.equal(model.why, UNUSUAL_BUT_VALID_WHY)
})

test('the backend Why reaches the rendered card unchanged', () => {
  const model = toOperatingStateReadModel(boardWith(UNUSUAL_BUT_VALID_WHY), { scope: 'league' })
  const text = visibleText(renderCard(model))

  assert.ok(text.includes(UNUSUAL_BUT_VALID_WHY), text.slice(0, 400))
})

test('backend evidence is rendered as published, not re-worded or re-ordered', () => {
  const reasons = [
    'Five relievers are available from the latest completed workload data.',
    'Two relievers are in the On Watch group.',
    'Availability classifications are workload-based only.',
  ]
  const model = toOperatingStateReadModel(
    boardWith('Bullpen workload is elevated.', { reasons }),
    { scope: 'league' },
  )

  // The methodology line is routed to limitations by design; the two evidence
  // sentences arrive intact and in published order.
  assert.deepEqual(
    model.evidence.filter(item => reasons.includes(item)),
    [reasons[0], reasons[1]],
  )
})

// ── E2 / E3 / E4: the Why cannot silently disappear ─────────────────────────

test('a valid payload always yields a Why on the read model', () => {
  const why = 'Bullpen workload appears manageable.'
  for (const scope of ['league', 'team']) {
    const model = toOperatingStateReadModel(boardWith(why), { scope })
    assert.equal(model.why, why, `scope ${scope}`)
  }
})

test('Dashboard renders State then Why then Evidence in order', () => {
  const why = 'The bullpen is short on rested arms right now.'
  const model = toOperatingStateReadModel(
    boardWith(why, { reasons: ['Two relievers are in the On Watch group.'] }),
    { scope: 'league' },
  )
  const text = visibleText(renderCard(model, 'full'))

  const whyAt = text.indexOf(why)
  const evidenceAt = text.indexOf('Evidence')

  assert.ok(whyAt > -1, 'Why is missing from the dashboard card')
  assert.ok(evidenceAt > -1, 'Evidence is missing from the dashboard card')
  assert.ok(whyAt < evidenceAt, 'Why must precede Evidence')
})

test('Team Board compact renders State then Why then Evidence in order', () => {
  // The regression this locks: Team Board uses compact density and the compact
  // card never rendered the Why, so the product showed State -> Evidence.
  const why = 'The bullpen is short on rested arms right now.'
  const board = boardWith(why, { reasons: ['Two relievers are in the On Watch group.'] })
  const model = getTeamOperatingStateContext(board)
  const html = renderCard(model, 'compact')
  const text = visibleText(html)

  assert.ok(html.includes('data-density="compact"'))
  assert.ok(text.includes(why), `compact card lost the Why: ${text.slice(0, 400)}`)

  const whyAt = text.indexOf(why)
  const evidenceAt = text.indexOf('Evidence')
  assert.ok(evidenceAt > -1, 'Evidence is missing from the compact card')
  assert.ok(whyAt < evidenceAt, 'Why must precede Evidence on the compact card')
})

test('compact evidence is capped by count, never by matching the words in a sentence', () => {
  const reasons = [
    'One reliever is available from the latest completed workload data.',
    'Two relievers are in the On Watch group.',
    'A sentence the old allow-list would have deleted outright.',
    'Another unmatched but perfectly valid backend evidence line.',
  ]
  const model = getTeamOperatingStateContext(boardWith('Bullpen workload is elevated.', { reasons }))
  const text = visibleText(renderCard(model, 'compact'))

  assert.ok(text.includes('A sentence the old allow-list would have deleted outright.'))
  assert.ok(text.includes('Another unmatched but perfectly valid backend evidence line.'))
})

// ── E5: no frontend semantic vocabulary mapping on the governed path ────────

test('the governed board path holds no Monitor to On Watch or Avoid to Unavailable mapping', async () => {
  const governed = [
    '../src/adapters/operatingStateReadModel.js',
    '../src/components/bullpen/BullpenOperatingStateCard.jsx',
    '../src/components/bullpen/board/teamBullpenComparisonView.js',
  ]

  for (const file of governed) {
    const source = await readFile(new URL(file, import.meta.url), 'utf8')
    // Semantic public-copy replacement: rewriting one governed word into
    // another. Structured field names and styling keys are untouched by this.
    const semanticReplacement =
      /\.replace\(\s*\/\\b(Monitor|Avoid|Restricted|restricted|Constrained|constrained|snapshot|recommendation engine)/i
    assert.equal(
      semanticReplacement.test(source),
      false,
      `${file} still rewrites governed public vocabulary`,
    )
  }
})

test('the adapter renders the backend availability label rather than deriving one', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/board/tonightsBullpenBoardView.js', import.meta.url),
    'utf8',
  )
  assert.ok(
    source.includes('availability_public_label'),
    'board cards must render the backend-published public availability label',
  )
})

// ── E7: suppression accounting ─────────────────────────────────────────────

test('a healthy payload produces zero copy-suppression events', () => {
  resetCopySuppressionCounts()

  const model = toOperatingStateReadModel(
    boardWith('Bullpen workload appears manageable.', {
      reasons: ['Two relievers are in the On Watch group.'],
    }),
    { scope: 'league' },
  )
  renderCard(model)

  assert.equal(getCopySuppressionTotal(), 0, JSON.stringify(getCopySuppressionCounts()))
})

test('a deliberate refusal is counted and named', () => {
  resetCopySuppressionCounts()

  // A payload with no context at all: a legitimate fail-closed outcome that must
  // still be visible to an operator rather than silently blank.
  const model = toOperatingStateReadModel(null, { scope: 'team' })

  assert.equal(model.isUnavailable, true)
  assert.equal(model.why, null)
  assert.equal(getCopySuppressionTotal(), 1)
  assert.deepEqual(
    Object.keys(getCopySuppressionCounts()),
    ['team-board.context.health.label.no_context_in_payload'],
  )
})

test('a team-context read with no backend sentence is withheld and recorded', () => {
  resetCopySuppressionCounts()

  const board = boardWith('Bullpen workload appears manageable.')
  board.team_shape = {
    byKey: {
      // Label but no authored sentence. The adapter used to invent one.
      cleanOptions: { key: 'cleanOptions', label: 'Thin Clean Options', reasons: [] },
    },
  }
  const model = toOperatingStateReadModel(board, { scope: 'team' })

  assert.equal(model.cleanOptions, null)
  assert.equal(
    getCopySuppressionCounts()['team-board.teamContext.cleanOptions.summary.backend_summary_missing'],
    1,
  )
})

test('the accounting helper counts per cause and warns once per cause', () => {
  resetCopySuppressionCounts()
  const warnings = []
  const originalWarn = console.warn
  console.warn = (...args) => warnings.push(args.join(' '))

  try {
    recordCopySuppression({ surface: 's', field: 'f', reason: 'r', sample: 'x'.repeat(200) })
    recordCopySuppression({ surface: 's', field: 'f', reason: 'r' })
    recordCopySuppression({ surface: 's', field: 'f', reason: 'other' })
  } finally {
    console.warn = originalWarn
  }

  assert.equal(getCopySuppressionCounts()['s.f.r'], 2)
  assert.equal(getCopySuppressionCounts()['s.f.other'], 1)
  assert.equal(warnings.length, 2, 'one warning per distinct cause')
  assert.ok(warnings[0].length < 200, 'sample must be truncated')
})
