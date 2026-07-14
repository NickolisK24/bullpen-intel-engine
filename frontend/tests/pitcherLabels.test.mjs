import assert from 'node:assert/strict'
import test from 'node:test'

import {
  APPROVED_READ_LABELS,
  APPROVED_ROLE_LABELS,
  PITCHER_LABEL_KEY_COPY,
  PITCHER_READ_LABELS,
  PITCHER_ROLE_LABELS,
  USAGE_ROLE_PUBLIC_ROLES,
  derivePitcherReadLabel,
  derivePitcherRoleLabel,
  getPitcherLabels,
} from '../src/utils/pitcherLabels.js'

const authoredCard = {
  pitcher_id: 1,
  name: 'Backend Arm',
  availability_status: 'Available',
  data_state: 'fresh',
  role: {
    role_key: 'late_high_leverage',
    role: 'Trust Arm',
  },
  pitcher_labels: {
    role: {
      kind: 'role',
      key: 'trust_arm',
      label: 'Trust Arm',
      source: 'backend:role_key:late_high_leverage',
    },
    read: {
      kind: 'read',
      key: 'clean_option',
      label: 'Clean Option',
      source: 'backend:availability_status',
    },
  },
}

test('pitcher labels consume backend-authored role and read chips', () => {
  const labels = getPitcherLabels(authoredCard)
  assert.equal(labels.role.label, 'Trusted Arm')
  assert.equal(labels.role.key, 'trust_arm')
  assert.equal(labels.role.source, 'backend:role_key:late_high_leverage')
  assert.equal(labels.read.label, 'Clean Option')
  assert.equal(labels.read.key, 'clean_option')
  assert.equal(labels.read.source, 'backend:availability_status')
})

test('frontend enriches backend-authored labels with presentation metadata', () => {
  const labels = getPitcherLabels(authoredCard)
  assert.equal(labels.role.definition, PITCHER_ROLE_LABELS.TRUST_ARM.definition)
  assert.deepEqual(labels.role.tone, PITCHER_ROLE_LABELS.TRUST_ARM.tone)
  assert.equal(labels.read.definition, PITCHER_READ_LABELS.CLEAN_OPTION.definition)
  assert.deepEqual(labels.read.tone, PITCHER_READ_LABELS.CLEAN_OPTION.tone)
})

test('camelCase backend labels are accepted', () => {
  const labels = getPitcherLabels({
    pitcherLabels: {
      role: { key: 'coverage_arm', label: 'Coverage Arm', source: 'backend:mixed_coverage' },
      read: { key: 'rest_restricted', label: 'Rest-Restricted', source: 'backend:availability_status' },
    },
  })

  assert.equal(labels.role.label, 'Coverage Arm')
  assert.equal(labels.read.label, 'Limited Rest')
})

test('raw role and availability fields no longer create frontend-authored labels', () => {
  const labels = getPitcherLabels({
    name: 'Raw Payload Arm',
    availability_status: 'Available',
    data_state: 'fresh',
    confidence: 'high',
    role: {
      role_key: 'late_high_leverage',
      confidence: 'high',
    },
  })

  assert.equal(labels.role.label, 'Limited Read')
  assert.equal(labels.role.source, 'missing_backend_label')
  assert.equal(labels.read.label, 'Limited Read')
  assert.equal(labels.read.source, 'missing_backend_label')
})

test('unknown backend keys fail closed to Limited Read', () => {
  const labels = getPitcherLabels({
    pitcher_labels: {
      role: { key: 'closer_grade', label: 'Closer Grade', source: 'backend:test' },
      read: { key: 'freshest_arm', label: 'Freshest Arm', source: 'backend:test' },
    },
  })

  assert.equal(labels.role.label, 'Limited Read')
  assert.equal(labels.role.source, 'backend:test')
  assert.equal(labels.read.label, 'Limited Read')
  assert.equal(labels.read.source, 'backend:test')
})

test('individual helpers read the same backend-authored payload', () => {
  assert.equal(derivePitcherRoleLabel(authoredCard).label, 'Trusted Arm')
  assert.equal(derivePitcherReadLabel(authoredCard).label, 'Clean Option')
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

test('public label sets remain unchanged', () => {
  assert.deepEqual(APPROVED_ROLE_LABELS, [
    'Trusted Arm',
    'Setup Arm',
    'Coverage Arm',
    'Middle Relief Arm',
    'Limited Read',
  ])
  assert.deepEqual(APPROVED_READ_LABELS, [
    'Clean Option',
    'Watch Arm',
    'Limited Rest',
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

test('retired backend role wording is rewritten to the canonical public set', () => {
  const cases = [
    { key: 'trust_arm', label: 'Trust Arm', expected: 'Trusted Arm' },
    { key: 'bridge_arm', label: 'Bridge Arm', expected: 'Setup Arm' },
    { key: 'depth_arm', label: 'Depth Arm', expected: 'Middle Relief Arm' },
  ]
  for (const { key, label, expected } of cases) {
    const labels = getPitcherLabels({
      pitcher_labels: { role: { kind: 'role', key, label, source: 'backend:test' } },
    })
    assert.equal(labels.role.label, expected)
  }
})

test('canonical role keys render their canonical labels', () => {
  const cases = [
    { key: 'trust_arm', expected: 'Trusted Arm' },
    { key: 'bridge_arm', expected: 'Setup Arm' },
    { key: 'depth_arm', expected: 'Middle Relief Arm' },
    { key: 'coverage_arm', expected: 'Coverage Arm' },
    { key: 'limited_read', expected: 'Limited Read' },
  ]
  for (const { key, expected } of cases) {
    const labels = getPitcherLabels({
      pitcher_labels: { role: { kind: 'role', key, label: expected, source: 'backend:test' } },
    })
    assert.equal(labels.role.key, key)
    assert.equal(labels.role.label, expected)
  }
})

test('a backend-authored depth_arm role can never render as Setup Arm', () => {
  // The role KEY is the authority: even a malformed payload that carries
  // another role's wording must render the key's canonical label, so one
  // baseball role can never be reinterpreted as another.
  const malformed = getPitcherLabels({
    pitcher_labels: { role: { kind: 'role', key: 'depth_arm', label: 'Bridge Arm', source: 'backend:test' } },
  })
  assert.equal(malformed.role.key, 'depth_arm')
  assert.equal(malformed.role.label, 'Middle Relief Arm')
  assert.notEqual(malformed.role.label, 'Setup Arm')
})

test('usage-role vocabulary contract matches the backend canonical table', () => {
  // Vocabulary drift guard, mirroring backend
  // tests/test_pitcher_public_labels.py::test_canonical_vocabulary_contract.
  const expected = {
    late_high_leverage: { key: 'trust_arm', label: 'Trusted Arm' },
    setup_bridge: { key: 'bridge_arm', label: 'Setup Arm' },
    middle_relief: { key: 'depth_arm', label: 'Middle Relief Arm' },
    long_multi_inning: { key: 'coverage_arm', label: 'Coverage Arm' },
    low_unclear: { key: 'limited_read', label: 'Limited Read' },
    insufficient_data: { key: 'limited_read', label: 'Limited Read' },
  }
  assert.deepEqual(Object.keys(USAGE_ROLE_PUBLIC_ROLES).sort(), Object.keys(expected).sort())
  for (const [roleKey, { key, label }] of Object.entries(expected)) {
    assert.equal(USAGE_ROLE_PUBLIC_ROLES[roleKey].key, key, `usage role ${roleKey} public key`)
    assert.equal(USAGE_ROLE_PUBLIC_ROLES[roleKey].label, label, `usage role ${roleKey} public label`)
  }
  // middle_relief must never collapse into the setup/bridge slot.
  assert.notEqual(USAGE_ROLE_PUBLIC_ROLES.middle_relief.key, 'bridge_arm')
  assert.notEqual(USAGE_ROLE_PUBLIC_ROLES.middle_relief.label, 'Setup Arm')
})
