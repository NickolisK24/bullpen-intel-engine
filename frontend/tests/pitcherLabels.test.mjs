import assert from 'node:assert/strict'
import test from 'node:test'

import {
  APPROVED_READ_LABELS,
  APPROVED_ROLE_LABELS,
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

test('definitions exist and keep role/read boundaries clear', () => {
  for (const label of [...Object.values(PITCHER_ROLE_LABELS), ...Object.values(PITCHER_READ_LABELS)]) {
    assert.ok(label.definition)
    assert.ok(label.definition.length > 20)
  }
  assert.match(PITCHER_READ_LABELS.REST_RESTRICTED.definition, /workload only/i)
  assert.match(PITCHER_ROLE_LABELS.DEPTH_ARM.definition, /usage label/i)
  assert.match(PITCHER_ROLE_LABELS.DEPTH_ARM.definition, /not a talent judgment/i)
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
