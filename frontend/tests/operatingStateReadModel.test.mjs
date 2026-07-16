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
  'source',
  'snapshot',
  'COIN',
  'V2',
  'V3',
  'V4',
  '2.0',
  'deterministic',
  'recommendation engine',
  'baseline distribution',
  'baseline',
  'governance layer',
  'governance',
  'coverageSafetyVersion',
  'capacityState',
  'resourceHealthState',
  'thresholds',
  'Trust Arms',
  'Depth Arms',
  'top trust bucket',
  'resource health',
  'trust structure',
  'active capacity',
  'sample state',
  'trustAvailability',
  'bullpenPressure',
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

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function forbiddenPattern(term) {
  const escaped = escapeRegExp(term)
  return /^[a-z0-9]+$/i.test(term)
    ? new RegExp(`\\b${escaped}\\b`, 'i')
    : new RegExp(escaped, 'i')
}

function assertNoForbiddenLanguage(value) {
  const json = JSON.stringify(value)
  for (const term of forbiddenTerms) {
    assert.equal(forbiddenPattern(term).test(json), false, `leaked ${term}`)
  }
}

function trustedTeamShape(overrides = {}) {
  return {
    source: 'backend:test_fixture',
    coverageSafetyVersion: 'V4',
    capacityState: 'available',
    resourceHealthState: 'strained',
    thresholds: { cleanOptions: 3 },
    supportingCounts: {
      cleanOptionCount: 2,
      activeBullpenArms: 7,
    },
    byKey: {
      cleanOptions: {
        key: 'cleanOptions',
        label: 'Thin Clean Options',
        explanation: '2 Clean Options out of 8 active bullpen arms - 1 Trust, 1 Bridge, 0 Coverage, 0 Depth. Interpretation weighs clean Trust Arms above clean Depth Arms.',
        reasons: [
          '2 clean options are available.',
          'Interpretation weighs clean Trust Arms above clean Depth Arms.',
        ],
        supportingCounts: { cleanOptionCount: 2 },
        source: 'backend',
      },
      coverageSafety: {
        key: 'coverageSafety',
        label: 'Stable Coverage Safety',
        explanation: 'Coverage margin combines active capacity, resource health, and trust structure.',
        reasons: ['The top trust bucket still has one available arm.'],
        supportingCounts: { coverageArms: 4 },
        source: 'backend',
      },
      workloadConcentration: {
        key: 'workloadConcentration',
        label: 'Some Workload Concentration',
        explanation: 'Recent workload concentration uses coverageSafetyVersion 2.0 thresholds.',
        reasons: ['capacityState and resourceHealthState should not render.'],
        supportingCounts: { topThreeShare: 0.58 },
        source: 'backend',
      },
      ...overrides,
    },
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
  assert.match(model.primaryConcern.body, /Limited or Unavailable/)
  assert.equal(model.primaryConcern.body.includes('Avoid'), false)
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

test('team context reads map safe labels, explanations, and reasons only', () => {
  const board = teamOperatingBoard({ freshness: currentFreshness })
  board.team_shape = trustedTeamShape()

  const model = modelFor(board, { scope: 'team' })

  assert.deepEqual(model.cleanOptions, {
    label: 'Thin Clean Options',
    summary: 'Cleanly available choices are thinner than raw availability may suggest.',
    reasons: ['2 Clean Options are available.'],
  })
  assert.deepEqual(model.coverageSafety, {
    label: 'Stable Coverage Safety',
    summary: 'The current group appears to have enough coverage for a normal game state.',
    reasons: [],
  })
  assert.deepEqual(model.workloadConcentration, {
    label: 'Some Workload Concentration',
    summary: 'Recent relief work has flowed through a smaller group of arms.',
    reasons: [],
  })
  assert.equal(JSON.stringify(model).includes('supportingCounts'), false)
  assert.equal(JSON.stringify(model).includes('team_shape'), false)
  assert.equal(Object.prototype.hasOwnProperty.call(model.cleanOptions, 'key'), false)
  assert.equal(JSON.stringify(model).includes('Interpretation weighs clean Trust Arms'), false)
  assert.equal(JSON.stringify(model).includes('active capacity'), false)
  assert.equal(JSON.stringify(model).includes('top trust bucket'), false)
  assertNoForbiddenLanguage(model)
})

test('team context reads can map direct team_shape fields with public summaries', () => {
  const board = teamOperatingBoard()
  board.team_shape = {
    cleanOptions: {
      key: 'cleanOptions',
      label: 'Healthy Clean Options',
      explanation: 'Enough arms are cleanly available right now.',
      reasons: ['5 clean options are available.'],
    },
  }

  const model = modelFor(board, { scope: 'team' })

  assert.deepEqual(model.cleanOptions, {
    label: 'Healthy Clean Options',
    summary: 'This bullpen has enough cleanly available choices for normal coverage.',
    reasons: ['5 Clean Options are available.'],
  })
  assert.equal(model.coverageSafety, null)
  assert.equal(model.workloadConcentration, null)
})

test('team context reads omit limited reads but keep safe labels when copy is filtered', () => {
  const board = teamOperatingBoard()
  board.team_shape = trustedTeamShape({
    cleanOptions: {
      key: 'cleanOptions',
      label: 'Limited Read',
      explanation: 'Backend team bullpen shape was not returned.',
      reasons: ['Backend team bullpen shape was not returned.'],
    },
    coverageSafety: {
      key: 'coverageSafety',
      label: 'Stable Coverage Safety',
      explanation: 'backend endpoint source snapshot V4 deterministic detail',
      reasons: ['COIN source detail should not render.'],
    },
    workloadConcentration: {
      key: 'workloadConcentration',
      label: 'Some Workload Concentration',
    },
  })

  const model = modelFor(board, { scope: 'team' })

  assert.equal(model.cleanOptions, null)
  assert.deepEqual(model.coverageSafety, {
    label: 'Stable Coverage Safety',
    summary: 'The current group appears to have enough coverage for a normal game state.',
    reasons: [],
  })
  assert.deepEqual(model.workloadConcentration, {
    label: 'Some Workload Concentration',
    summary: 'Recent relief work has flowed through a smaller group of arms.',
    reasons: [],
  })
  assertNoForbiddenLanguage(model)
})

test('missing team_shape leaves team context reads null without adding trend', () => {
  const model = modelFor(teamOperatingBoard(), { scope: 'team' })

  assert.equal(model.cleanOptions, null)
  assert.equal(model.coverageSafety, null)
  assert.equal(model.workloadConcentration, null)
  assert.equal(Object.prototype.hasOwnProperty.call(model, 'trendSinceYesterday'), false)
  assert.ok(model.unsupportedFields.includes('Trend Since Yesterday'))
  assertNoUndefined(model)
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

function assertNoStarterStatusLanguage(value) {
  const json = JSON.stringify(value)
  for (const term of ['supportive', 'neutral', 'moderate_pressure', 'heavy_pressure']) {
    assert.equal(json.includes(term), false, `leaked starter status ${term}`)
  }
}

test('starter support renders a quiet limited state when sample is insufficient', () => {
  const board = teamOperatingBoard()
  board.rotation_support_pressure = {
    capability: 'rotation_support_pressure_v1',
    status: 'limited_read',
    games_analyzed: 1,
    games_in_window: 4,
    window_days: 7,
    starter_outs: 14,
    starter_avg_innings: 4.8,
    bullpen_outs_required: 25,
    short_start_count: 1,
    limitation_reasons: ['insufficient_trustworthy_games', 'partial_source_coverage'],
    summary: 'Low-sample starter support should not render.',
    limitations: ['Rotation Support Pressure raw limitation should not render.'],
  }
  const model = modelFor(board, { scope: 'team' })

  assert.equal(model.starterSupportPressure.status, 'limited')
  assert.equal(model.starterSupportPressure.summary, 'Starter-length context is limited. 1 of 4 recent games can be analyzed.')
  assert.deepEqual(model.starterSupportPressure.reasons, [
    'The bullpen covered 8 1/3 innings after those analyzed starts.',
    'Not enough complete recent starts are available for a full starter-length read.',
    'The recent game window is partial, so this starter-length read is limited.',
  ])
  assert.deepEqual(model.starterSupportPressure.limitations, [
    'Not enough complete recent starts are available for a full starter-length read.',
    'The recent game window is partial, so this starter-length read is limited.',
  ])
  assert.equal(model.starterSupportPressure.receiptsHref, '#team-relief-work')
  assert.equal(model.starterSupportPressure.receiptsLabel, 'View game-level work')
  assert.equal(JSON.stringify(model).includes('Low-sample starter support should not render.'), false)
  assert.equal(JSON.stringify(model).includes('Rotation Support Pressure raw limitation should not render.'), false)
  assertNoStarterStatusLanguage(model)
})

test('starter support renders factual starter length and bullpen coverage', () => {
  const board = teamOperatingBoard()
  board.rotation_support_pressure = {
    capability: 'rotation_support_pressure_v1',
    status: 'heavy_pressure',
    games_in_window: 5,
    games_analyzed: 5,
    window_days: 7,
    starter_outs: 65,
    starter_avg_innings: 4.8,
    bullpen_outs_required: 63,
    short_start_count: 3,
    summary: 'The rotation averaged 4.8 innings per start over the last 7 days, requiring 21.0 bullpen innings.',
    limitations: ['Rotation Support Pressure should not render.'],
  }
  const model = modelFor(board, { scope: 'team' })

  assert.deepEqual(model.starterSupportPressure, {
    status: 'available',
    gamesAnalyzed: 5,
    label: null,
    summary: 'Across the seven-day window, starters averaged 4.1 innings per start. The bullpen covered 21 innings after those starts.',
    reasons: ['3 of 5 analyzed starts ended before five innings.'],
    evidence: [
      'Across the seven-day window, starters averaged 4.1 innings per start. The bullpen covered 21 innings after those starts.',
      '3 of 5 analyzed starts ended before five innings.',
    ],
    limitations: [],
    receiptsHref: '#team-relief-work',
    receiptsLabel: 'View game-level work',
  })
  assert.ok(model.evidence.includes('Across the seven-day window, starters averaged 4.1 innings per start. The bullpen covered 21 innings after those starts.'))
  assert.equal(JSON.stringify(model).includes('The rotation averaged 4.8 innings per start over the last 7 days'), false)
  assertNoStarterStatusLanguage(model)
})

test('starter average receipts preserve units, denominator, rounding, and fail-closed authority', () => {
  const rotationSupport = (overrides = {}) => ({
    capability: 'rotation_support_pressure_v1',
    status: 'moderate_pressure',
    games_in_window: 5,
    games_analyzed: 5,
    window_days: 7,
    starter_outs: 60,
    starter_avg_innings: 4.37,
    bullpen_outs_required: 63,
    short_start_count: 2,
    ...overrides,
  })
  const starterRead = (overrides = {}, boardOverrides = {}) => {
    const board = teamOperatingBoard(boardOverrides)
    board.rotation_support_pressure = rotationSupport(overrides)
    return modelFor(board, { scope: 'team' }).starterSupportPressure
  }

  for (const [starterOuts, analyzedStarts, expected] of [
    [60, 5, '4.0 innings per start'],
    [65, 5, '4.1 innings per start'],
    [70, 5, '4.2 innings per start'],
    [75, 5, '5.0 innings per start'],
    [66, 5, '4.1 innings per start'],
    [73, 5, '5.0 innings per start'],
    [54, 4, '4.2 innings per start'],
    [9, 3, '1.0 inning per start'],
    [0, 5, '0.0 innings per start'],
  ]) {
    const read = starterRead({ starter_outs: starterOuts, games_analyzed: analyzedStarts })
    assert.ok(
      read.summary.startsWith(`Across the seven-day window, starters averaged ${expected}.`),
      `${starterOuts} outs across ${analyzedStarts} starts produced: ${read.summary}`,
    )
    assert.match(read.summary, /averaged \d+\.[012] innings? per start\./)
    assert.equal(/starters averaged \d+(?:\.\d+)?\.$/.test(read.evidence[0]), false)
  }

  for (const overrides of [
    { starter_outs: null },
    { starter_outs: undefined },
    { starter_outs: '65' },
    { starter_outs: 65.5 },
    { starter_outs: -1 },
    { starter_outs: undefined, starter_avg_innings: 4.37 },
    { starter_outs: undefined, starter_avg_innings: 4.3 },
    { games_analyzed: 0 },
    { games_analyzed: undefined },
    { capability: undefined },
    { capability: 'unsupported_rotation_read' },
    { window_days: undefined },
    { window_days: 14 },
  ]) {
    const read = starterRead(overrides)
    assert.equal((read?.evidence || []).some(item => item.includes('starters averaged')), false)
    assert.equal(JSON.stringify(read).includes('4.4 innings per start'), false)
    assert.equal(JSON.stringify(read).includes('4.3 innings per start'), false)
  }

  const staleFreshness = {
    data_through: '2026-06-01',
    is_current: false,
    is_stale: true,
    fail_closed: true,
    freshness_state: 'stale',
  }
  assert.equal(starterRead({}, { freshness: staleFreshness }), null)
})

test('starter support renders factual copy without grading stable samples', () => {
  const board = teamOperatingBoard()
  board.rotation_support_pressure = {
    capability: 'rotation_support_pressure_v1',
    status: 'supportive',
    games_in_window: 4,
    games_analyzed: 4,
    window_days: 7,
    starter_outs: 72,
    starter_avg_innings: 6.1,
    bullpen_outs_required: 35,
    short_start_count: 0,
    summary: 'The rotation averaged 6.1 innings per start over the last 7 days.',
  }
  const model = modelFor(board, { scope: 'team' })

  assert.equal(model.starterSupportPressure.summary, 'Across the seven-day window, starters averaged 6.0 innings per start. The bullpen covered 11 2/3 innings after those starts.')
  assert.deepEqual(model.starterSupportPressure.reasons, ['None of the 4 analyzed starts ended before five innings.'])
  assertNoStarterStatusLanguage(model)
  assertNoForbiddenLanguage(model)
})

test('starter support ignores unsupported status vocabulary and unsafe backend summary copy', () => {
  const unsupportedBoard = teamOperatingBoard()
  unsupportedBoard.rotation_support_pressure = {
    capability: 'rotation_support_pressure_v1',
    status: 'experimental_status',
    games_in_window: 4,
    games_analyzed: 4,
    window_days: 7,
    starter_outs: 65,
    starter_avg_innings: 5.4,
    bullpen_outs_required: 44,
    short_start_count: 1,
    summary: 'The rotation averaged 5.4 innings per start.',
  }
  assert.equal(
    modelFor(unsupportedBoard, { scope: 'team' }).starterSupportPressure.summary,
    'Across the seven-day window, starters averaged 5.1 innings per start. The bullpen covered 14 2/3 innings after those starts.',
  )

  const unsafeBoard = teamOperatingBoard()
  unsafeBoard.rotation_support_pressure = {
    capability: 'rotation_support_pressure_v1',
    status: 'moderate_pressure',
    games_in_window: 4,
    games_analyzed: 4,
    window_days: 7,
    starter_outs: 65,
    starter_avg_innings: 5.4,
    bullpen_outs_required: 44,
    short_start_count: 1,
    summary: 'backend endpoint snapshot should not render.',
  }
  const unsafeModel = modelFor(unsafeBoard, { scope: 'team' })
  assert.equal(unsafeModel.starterSupportPressure.summary, 'Across the seven-day window, starters averaged 5.1 innings per start. The bullpen covered 14 2/3 innings after those starts.')
  assert.equal(JSON.stringify(unsafeModel).includes('backend endpoint snapshot should not render.'), false)
  assertNoStarterStatusLanguage(unsafeModel)
})

test('unsupported fields are named for awareness but not rendered as placeholders', () => {
  const model = modelFor(teamOperatingBoard(), { scope: 'team' })
  const visible = [...model.evidence, ...model.limitations].join(' ')

  assert.deepEqual(model.unsupportedFields, ['Trend Since Yesterday'])
  assert.equal(visible.includes('Trend Since Yesterday'), false)
  for (const field of ['Clean Options', 'Coverage Safety', 'Workload Concentration']) {
    assert.equal(model.unsupportedFields.includes(field), false)
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
