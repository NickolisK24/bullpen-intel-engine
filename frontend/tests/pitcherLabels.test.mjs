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
