import assert from 'node:assert/strict'
import test, { after } from 'node:test'
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

const {
  toOperatingStateReadModel,
} = await server.ssrLoadModule('/src/adapters/operatingStateReadModel.js')

const currentFreshness = {
  data_through: '2026-06-26',
  last_successful_sync: '2026-06-26T10:04:00Z',
  is_current: true,
  sync_status: 'success',
}

const forbiddenTerms = [
  'backend',
  'endpoint',
  'snapshot',
  'COIN',
  'V2',
  'V3',
  'V4',
  'deterministic',
  'recommendation engine',
  'baseline distribution',
  'governance layer',
  'sample state',
]

function teamOperatingBoard(overrides = {}) {
  return makeBoard({
    team: { team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM' },
    cardsByStatus: {
      Available: Array.from({ length: 5 }, (_, i) => ({
        pitcher_id: i + 1,
        name: `Mets Available ${i}`,
        availability_status: 'Available',
      })),
      Monitor: [{ pitcher_id: 20, name: 'Mets Monitor', availability_status: 'Monitor' }],
    },
    rosterAuthority: {
      capability: 'roster_authority_v1',
      invariant: true,
      category_counts: { injured_list: 2 },
      counts: {
        bullpen_arms: 6,
        active_bullpen_arms: 6,
        inactive_roster_context_count: 3,
        roster_unknown_count: 0,
      },
      population: { total_candidates: 9, known_count: 9, unknown_count: 0, roster_status_coverage: 1 },
      evidence: {
        bullpen_arms: [],
        active_bullpen_arms: [],
        inactive_roster_context_count: [],
        roster_unknown_count: [],
      },
      limitations: ['Roster status reflects the latest loaded roster context.'],
    },
    ...overrides,
  })
}

function modelFor(payload, options = {}) {
  return toOperatingStateReadModel(payload, options)
}

function assertNoForbiddenLanguage(value) {
  const json = JSON.stringify(value)
  for (const term of forbiddenTerms) {
    assert.equal(new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i').test(json), false, `leaked ${term}`)
  }
}

function assertNoUndefined(value) {
  if (!value || typeof value !== 'object') return
  for (const [key, entry] of Object.entries(value)) {
    assert.notEqual(entry, undefined, `undefined leaked at ${key}`)
    if (entry && typeof entry === 'object') assertNoUndefined(entry)
  }
}

test('league payload returns baseball-facing state label and tone', () => {
  const board = makeBoard({
    cardsByStatus: {
      Available: Array.from({ length: 8 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
      Monitor: [{ pitcher_id: 20, name: 'M1', availability_status: 'Monitor' }],
      Limited: [{ pitcher_id: 30, name: 'L1', availability_status: 'Limited' }],
    },
    freshness: currentFreshness,
  })
  const model = modelFor(board, { scope: 'league' })

  assert.equal(model.scope, 'league')
  assert.equal(model.stateLabel, 'Stable Overall')
  assert.equal(model.stateSummary, 'Most bullpen-eligible arms remain usable, with limited league-wide pressure.')
  assert.equal(model.stateTone.dot, '#10b981')
  assertNoForbiddenLanguage(model)
})

test('team payload returns team identity and team scope', () => {
  const model = modelFor(teamOperatingBoard(), { scope: 'team' })

  assert.equal(model.scope, 'team')
  assert.equal(model.scopeLabel, 'Team')
  assert.equal(model.teamId, 121)
  assert.equal(model.teamName, 'New York Mets')
  assert.equal(model.teamAbbreviation, 'NYM')
})

test('stable league read preserves league-safe wording', () => {
  const model = modelFor(makeBoard({
    cardsByStatus: {
      Available: Array.from({ length: 5 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
    },
    freshness: currentFreshness,
  }), { scope: 'league' })

  assert.equal(model.stateLabel, 'Stable Overall')
  assert.equal(model.scopeLabel, 'Scope')
})

test('team manageable read stays team-safe and does not imply no injuries', () => {
  const model = modelFor(teamOperatingBoard(), { scope: 'team' })
  const json = JSON.stringify(model)

  assert.equal(model.stateLabel, 'Stable')
  assert.equal(model.primaryConcern.label, 'Active workload is usable')
  assert.equal(model.secondaryConcern.label, 'Roster pressure remains part of the story')
  assert.equal(/nobody is hurt|no injuries/i.test(json), false)
})

test('primary concern is derived from workload lanes', () => {
  const model = modelFor(teamOperatingBoard({
    cardsByStatus: {
      Available: Array.from({ length: 3 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
      Limited: [{ pitcher_id: 40, name: 'L1', availability_status: 'Limited' }],
      Avoid: [{ pitcher_id: 41, name: 'A1', availability_status: 'Avoid' }],
    },
  }), { scope: 'team' })

  assert.equal(model.primaryConcern.label, 'Not every arm is cleanly available')
  assert.match(model.primaryConcern.body, /Limited, Avoid, or Unavailable/)
})

test('roster pressure is built only from roster authority', () => {
  const model = modelFor(teamOperatingBoard({
    cardsByStatus: {
      Unavailable: [{ pitcher_id: 1, name: 'Unavailable Arm', availability_status: 'Unavailable' }],
    },
    rosterAuthority: {
      counts: { inactive_roster_context_count: 0, roster_unknown_count: 0 },
      category_counts: { injured_list: 0 },
      limitations: [],
    },
  }), { scope: 'team' })

  assert.equal(model.rosterPressure.hasPressure, false)
  assert.equal(model.secondaryConcern, null)
  assert.equal(model.evidence.some(item => /injured list|inactive or unavailable|unconfirmed roster/i.test(item)), false)
})

test('roster pressure can become secondary concern when workload is usable', () => {
  const model = modelFor(teamOperatingBoard(), { scope: 'team' })

  assert.equal(model.primaryConcern.label, 'Active workload is usable')
  assert.equal(model.secondaryConcern.label, 'Roster pressure remains part of the story')
  assert.ok(model.evidence.includes('2 bullpen arms are on the injured list.'))
  assert.ok(model.evidence.includes('3 bullpen arms are inactive or unavailable.'))
})

test('evidence contains factual statements only', () => {
  const model = modelFor(teamOperatingBoard(), { scope: 'team' })

  assert.ok(model.evidence.includes('5 of 6 relievers are classified Available.'))
  assert.equal(model.evidence.some(item => /workload-based only|manager intent|private medical|final game-day/i.test(item)), false)
})

test('limitations remain separate from evidence', () => {
  const model = modelFor(teamOperatingBoard(), { scope: 'team' })

  assert.ok(model.limitations.some(item => /does not know manager intent/i.test(item)))
  assert.ok(model.limitations.includes('Roster status reflects the latest loaded roster context.'))
  assert.equal(model.evidence.some(item => /does not know manager intent/i.test(item)), false)
})

test('freshness is attached to the read model', () => {
  const model = modelFor(teamOperatingBoard({ freshness: currentFreshness }), { scope: 'team' })

  assert.equal(model.freshness.dataThrough, '2026-06-26')
  assert.equal(model.freshness.lastSync, '2026-06-26T10:04:00Z')
  assert.equal(model.freshness.isCurrent, true)
  assert.equal(model.freshness.hasFreshness, true)
})

test('stale and fail-closed freshness carries degraded flags and limitations', () => {
  const model = modelFor(teamOperatingBoard({
    freshness: {
      data_through: '2026-06-01',
      last_successful_sync: '2026-06-01T10:04:00Z',
      is_current: false,
      is_stale: true,
      fail_closed: true,
      freshness_state: 'stale',
      limitations: ['Latest workload data is outside the active freshness window.'],
    },
  }), { scope: 'team' })

  assert.equal(model.freshness.isStale, true)
  assert.equal(model.freshness.failClosed, true)
  assert.ok(model.limitations.includes('Latest workload data is outside the active freshness window.'))
})

test('starter support is omitted when sample is insufficient', () => {
  const board = teamOperatingBoard()
  board.rotation_support_pressure = {
    status: 'limited_read',
    games_analyzed: 1,
    summary: 'Low-sample starter support should not render.',
    limitations: ['Rotation support sample is limited.'],
  }
  const model = modelFor(board, { scope: 'team' })

  assert.equal(model.starterSupportPressure, null)
  assert.equal(JSON.stringify(model).includes('Low-sample starter support should not render.'), false)
  assert.equal(JSON.stringify(model).includes('Rotation support sample is limited.'), false)
})

test('starter support renders when sample and status are safe', () => {
  const board = teamOperatingBoard()
  board.rotation_support_pressure = {
    status: 'neutral',
    games_analyzed: 3,
    summary: 'The rotation averaged 5.4 innings per start over the last 7 days.',
    limitations: ['Some recent team games are excluded because starter workload data is incomplete.'],
  }
  const model = modelFor(board, { scope: 'team' })

  assert.ok(model.starterSupportPressure)
  assert.ok(model.evidence.includes('Starter support: The rotation averaged 5.4 innings per start over the last 7 days.'))
  assert.ok(model.limitations.includes('Some recent team games are excluded because starter workload data is incomplete.'))
})

test('unsupported fields are named for awareness but not rendered as placeholders', () => {
  const model = modelFor(teamOperatingBoard(), { scope: 'team' })
  const visible = [...model.evidence, ...model.limitations].join(' ')

  for (const field of ['Clean Options', 'Coverage Safety', 'Workload Concentration', 'Trend Since Yesterday']) {
    assert.ok(model.unsupportedFields.includes(field))
    assert.equal(visible.includes(field), false)
  }
  assert.equal(/unknown|null placeholder|not available yet/i.test(visible), false)
})

test('adapter output is scrubbed of internal vocabulary', () => {
  const model = modelFor({
    context: {
      metrics: { total_relievers: 8, available: 5, monitor: 1, limited: 1, avoid: 1, unavailable: 0 },
      health: {
        state: 'manageable',
        label: 'backend COIN snapshot V2 deterministic endpoint',
        reasons: [
          'The existing snapshot moved after the latest completed games.',
          'COIN endpoint V4 detail should never render.',
          '5 of 8 relievers are classified Available.',
        ],
      },
      confidence: 'high',
      limitations: [
        'governance layer detail should never render.',
        'Latest workload data is outside the active freshness window, so this snapshot may not reflect current bullpen planning.',
      ],
    },
    freshness: currentFreshness,
  }, { scope: 'league' })

  assert.ok(model.evidence.includes('The existing bullpen read moved after the latest completed games.'))
  assert.ok(model.limitations.includes('Latest workload data is outside the active freshness window, so this bullpen read may not reflect current bullpen planning.'))
  assertNoForbiddenLanguage(model)
})

test('empty payload returns safe unavailable read model without undefined leaks', () => {
  const model = modelFor(null, { scope: 'team' })

  assert.equal(model.isUnavailable, true)
  assert.equal(model.teamName, 'Selected Team')
  assert.deepEqual(model.evidence, [])
  assert.deepEqual(model.limitations, [])
  assertNoUndefined(model)
  assert.equal(JSON.stringify(model).includes('undefined'), false)
})
