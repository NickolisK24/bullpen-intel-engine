import assert from 'node:assert/strict'
import test from 'node:test'

import {
  APPROVED_READ_LABELS,
  APPROVED_ROLE_LABELS,
  PITCHER_LABEL_KEY_COPY,
  PITCHER_READ_LABELS,
  PITCHER_ROLE_LABELS,
  derivePitcherReadLabel,
  derivePitcherRoleLabel,
  getPitcherLabels,
} from '../src/utils/pitcherLabels.js'

const baseCard = (overrides = {}) => ({
  pitcher_id: 1,
  name: 'Example Arm',
  availability_status: 'Available',
  fatigue_score: 22,
  confidence: 'high',
  data_state: 'fresh',
  role: {
    role_key: 'late_high_leverage',
    role: 'Late / High-Leverage',
    confidence: 'high',
  },
  ...overrides,
})

const roleFixture = (overrides = {}) => ({
  role_key: 'late_high_leverage',
  role: 'Late / High-Leverage',
  confidence: 'high',
  sample_size: 4,
  evidence: ['4 appearances in the recent window'],
  ...overrides,
})

const validationFixtures = {
  clearTrust: baseCard({
    role: roleFixture({
      role_key: 'late_high_leverage',
      role: 'Late / High-Leverage Pattern',
      evidence: ['5 appearances in late high-leverage relief work'],
    }),
  }),
  clearBridge: baseCard({
    role: roleFixture({
      role_key: 'setup_bridge',
      role: 'Setup / Bridge Pattern',
      evidence: ['4 appearances in setup and bridge relief work'],
    }),
  }),
  clearCoverage: baseCard({
    role: roleFixture({
      role_key: 'long_multi_inning',
      role: 'Long Relief / Multi-Inning Pattern',
      evidence: ['4 appearances in long relief coverage'],
    }),
  }),
  clearDepth: baseCard({
    role: roleFixture({
      role_key: 'depth',
      role: 'Depth Usage Pattern',
      evidence: ['5 lower-leverage bullpen appearances'],
    }),
  }),
  lowSampleReliever: baseCard({
    role: roleFixture({
      role_key: 'setup_bridge',
      sample_size: 1,
      evidence: ['1 appearance in setup relief work'],
    }),
  }),
  mixedStarterRelieverAmbiguous: baseCard({
    eligibility: {
      status: 'role_ambiguous',
      reason: 'Mixed starter and reliever usage.',
    },
    role: roleFixture({
      role_key: 'late_high_leverage',
      role: 'Starter and reliever swing role',
      is_starter: true,
      is_reliever: true,
      evidence: ['2 starts and 3 relief appearances in the recent window'],
    }),
  }),
  openerLikeAmbiguous: baseCard({
    eligibility: {
      status: 'role_ambiguous',
      reason: 'Opener-like short starts mixed with relief appearances.',
    },
    role: roleFixture({
      role_key: 'opener',
      role: 'Opener / Short Start Pattern',
      is_starter: true,
      is_reliever: true,
      evidence: ['2 short starts and 2 relief appearances'],
    }),
  }),
  swingmanCoverage: baseCard({
    eligibility: {
      status: 'role_ambiguous',
      reason: 'Mixed starter and reliever usage with clear bulk relief work.',
    },
    role: roleFixture({
      role_key: 'long_multi_inning',
      role: 'Swingman / Bulk Relief Coverage',
      is_starter: true,
      is_reliever: true,
      evidence: ['5 appearances with bulk multi-inning relief coverage'],
    }),
  }),
  unavailableActiveLooking: baseCard({
    availability_status: 'Available',
    role: roleFixture({
      role_key: 'insufficient_data',
      role: 'Insufficient Data',
      confidence: 'none',
      sample_size: 0,
      evidence: [],
    }),
    roster_status: {
      status: 'IL_60',
      is_active_mlb: false,
      is_inactive_context: true,
    },
  }),
  committeeTrustA: baseCard({
    pitcher_id: 11,
    role: roleFixture({
      role_key: 'late_high_leverage',
      role: 'Late / High-Leverage Pattern',
      evidence: ['5 late high-leverage relief appearances'],
    }),
  }),
  committeeTrustB: baseCard({
    pitcher_id: 12,
    role: roleFixture({
      role_key: 'high_leverage',
      role: 'Shared High-Leverage Pattern',
      evidence: ['4 late high-leverage relief appearances'],
    }),
  }),
}

test('every approved role label can be produced from existing role fields', () => {
  const cases = [
    ['late_high_leverage', 'Trust Arm'],
    ['setup_bridge', 'Bridge Arm'],
    ['long_multi_inning', 'Coverage Arm'],
    ['depth', 'Depth Arm'],
    ['insufficient_data', 'Limited Read'],
  ]

  for (const [roleKey, expected] of cases) {
    const label = derivePitcherRoleLabel(baseCard({ role: { role_key: roleKey } }))
    assert.equal(label.label, expected)
    assert.ok(APPROVED_ROLE_LABELS.includes(label.label))
  }
})

test('every approved read label can be produced from board availability fields', () => {
  const cases = [
    [{ availability_status: 'Available' }, 'Clean Option'],
    [{ availability_status: 'Monitor' }, 'Watch Arm'],
    [{ availability_status: 'Limited' }, 'Rest-Restricted'],
    [{ availability_status: 'Unavailable' }, 'Unavailable'],
    [{ availability_status: 'Available', data_state: 'missing' }, 'Limited Read'],
  ]

  for (const [overrides, expected] of cases) {
    const label = derivePitcherReadLabel(baseCard(overrides))
    assert.equal(label.label, expected)
    assert.ok(APPROVED_READ_LABELS.includes(label.label))
  }
})

test('sparse data falls back to Limited Read for both layers', () => {
  assert.equal(derivePitcherRoleLabel({ name: 'Sparse Arm' }).label, 'Limited Read')
  assert.equal(derivePitcherReadLabel({ name: 'Sparse Arm' }).label, 'Limited Read')
})

test('mixed starter and reliever context stays Limited Read', () => {
  const label = derivePitcherRoleLabel(baseCard({
    eligibility: {
      status: 'role_ambiguous',
      reason: 'Mixed starter and reliever usage.',
    },
    role: {
      role_key: 'late_high_leverage',
      role: 'Starter and reliever swing role',
      is_starter: true,
      is_reliever: true,
    },
  }))
  assert.equal(label.label, 'Limited Read')
  assert.equal(label.source, 'mixed_starter_reliever')
})

test('realistic bullpen role fixtures validate clear role shapes', () => {
  assert.equal(derivePitcherRoleLabel(validationFixtures.clearTrust).label, 'Trust Arm')
  assert.equal(derivePitcherRoleLabel(validationFixtures.clearBridge).label, 'Bridge Arm')
  assert.equal(derivePitcherRoleLabel(validationFixtures.clearCoverage).label, 'Coverage Arm')
  assert.equal(derivePitcherRoleLabel(validationFixtures.clearDepth).label, 'Depth Arm')
})

test('low-sample and ambiguous mixed-use profiles prefer Limited Read', () => {
  assert.equal(derivePitcherRoleLabel(validationFixtures.lowSampleReliever).label, 'Limited Read')
  assert.equal(derivePitcherRoleLabel(validationFixtures.mixedStarterRelieverAmbiguous).label, 'Limited Read')
  assert.equal(derivePitcherRoleLabel(validationFixtures.openerLikeAmbiguous).label, 'Limited Read')
})

test('swingman with clear bulk relief signal returns Coverage Arm', () => {
  const label = derivePitcherRoleLabel(validationFixtures.swingmanCoverage)
  assert.equal(label.label, 'Coverage Arm')
  assert.match(label.source, /^mixed_coverage:/)
})

test('committee late-inning usage can produce multiple Trust Arms', () => {
  const labels = [
    derivePitcherRoleLabel(validationFixtures.committeeTrustA).label,
    derivePitcherRoleLabel(validationFixtures.committeeTrustB).label,
  ]
  assert.deepEqual(labels, ['Trust Arm', 'Trust Arm'])
})

test('unavailable status overrides optimistic workload fields', () => {
  const label = derivePitcherReadLabel(baseCard({
    availability_status: 'Available',
    roster_status: {
      status: 'IL_60',
      is_active_mlb: false,
      is_inactive_context: true,
    },
  }))
  assert.equal(label.label, 'Unavailable')
})

test('unavailable active-looking pitcher stays unavailable and avoids role certainty when usage is unreliable', () => {
  const labels = getPitcherLabels(validationFixtures.unavailableActiveLooking)
  assert.equal(labels.role.label, 'Limited Read')
  assert.equal(labels.read.label, 'Unavailable')
})

test('definitions exist and keep role/read boundaries clear', () => {
  for (const label of [...Object.values(PITCHER_ROLE_LABELS), ...Object.values(PITCHER_READ_LABELS)]) {
    assert.ok(label.definition)
    assert.ok(label.definition.length > 20)
  }
  assert.match(PITCHER_READ_LABELS.REST_RESTRICTED.definition, /workload only/i)
  assert.match(PITCHER_ROLE_LABELS.DEPTH_ARM.definition, /usage label/i)
  assert.match(PITCHER_ROLE_LABELS.DEPTH_ARM.definition, /not a talent judgment/i)
  assert.match(PITCHER_LABEL_KEY_COPY.roleSummary, /usage shape/i)
})

test('labels are constrained to approved label sets', () => {
  const cards = [
    baseCard({ role: { role_key: 'late_high_leverage' }, availability_status: 'Available' }),
    baseCard({ role: { role_key: 'setup_bridge' }, availability_status: 'Monitor' }),
    baseCard({ role: { role_key: 'long_multi_inning' }, availability_status: 'Limited' }),
    baseCard({ role: { role_key: 'depth' }, availability_status: 'Unavailable' }),
    baseCard({ role: { role_key: 'unknown' }, data_state: 'missing' }),
  ]

  for (const card of cards) {
    const labels = getPitcherLabels(card)
    assert.ok(APPROVED_ROLE_LABELS.includes(labels.role.label), labels.role.label)
    assert.ok(APPROVED_READ_LABELS.includes(labels.read.label), labels.read.label)
  }
})

test('public label sets remain unchanged', () => {
  assert.deepEqual(APPROVED_ROLE_LABELS, [
    'Trust Arm',
    'Bridge Arm',
    'Coverage Arm',
    'Depth Arm',
    'Limited Read',
  ])
  assert.deepEqual(APPROVED_READ_LABELS, [
    'Clean Option',
    'Watch Arm',
    'Rest-Restricted',
    'Unavailable',
    'Limited Read',
  ])
})

test('role labels read as usage shape rather than rankings', () => {
  const copy = JSON.stringify({ PITCHER_ROLE_LABELS, PITCHER_LABEL_KEY_COPY }).toLowerCase()
  assert.ok(copy.includes('usage'))
  assert.equal(/\brank\b|\branking\b|\branked\b/.test(copy), false)
})

test('label copy avoids advisory and speculative language', () => {
  const copy = JSON.stringify({ PITCHER_ROLE_LABELS, PITCHER_READ_LABELS }).toLowerCase()
  for (const term of [
    'injur',
    'predict',
    'betting',
    'wager',
    'odds',
    'recommended',
    'recommendation',
    'should pitch',
    'best arm',
    'best option',
  ]) {
    assert.equal(copy.includes(term), false, `leaked term: ${term}`)
  }
})
