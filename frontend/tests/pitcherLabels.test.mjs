import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
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
    role: 'Trusted Arm',
  },
  pitcher_labels: {
    role: {
      kind: 'role',
      key: 'trust_arm',
      label: 'Trusted Arm',
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
      read: { key: 'rest_restricted', label: 'Limited Rest', source: 'backend:availability_status' },
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

  assert.equal(labels.role.label, 'Role Unclear')
  assert.equal(labels.role.source, 'missing_backend_label')
  assert.equal(labels.read.label, 'Limited Read')
  assert.equal(labels.read.source, 'missing_backend_label')
})

test('unknown backend keys fail closed to each family fallback', () => {
  const labels = getPitcherLabels({
    pitcher_labels: {
      role: { key: 'closer_grade', label: 'Closer Grade', source: 'backend:test' },
      read: { key: 'freshest_arm', label: 'Freshest Arm', source: 'backend:test' },
    },
  })

  // Each family falls back to its OWN fallback, and the two are different
  // words: an unreadable role says the role is unclear, an unreadable read
  // says the read is limited.
  assert.equal(labels.role.label, 'Role Unclear')
  assert.equal(labels.role.source, 'backend:test')
  assert.equal(labels.read.label, 'Limited Read')
  assert.equal(labels.read.source, 'backend:test')
  assert.notEqual(labels.role.label, labels.read.label)
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
    'Role Unclear',
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

test('the frontend performs no semantic rewriting of governed labels', () => {
  // VOC-001 moved wording ownership to the backend. This file used to rewrite
  // authored labels on the way out (Trust Arm -> Trusted Arm,
  // Rest-Restricted -> Limited Rest, Monitor -> On Watch), which meant the
  // rendered chip was decided by two files. Those substitutions are gone, and
  // this proves it: whatever the backend authors for a valid key is what the
  // reader sees, verbatim, awkward or not.
  const awkward = [
    { catalog: 'role', key: 'trust_arm', authored: 'Trust Arm' },
    { catalog: 'role', key: 'bridge_arm', authored: 'Bridge Arm' },
    { catalog: 'role', key: 'depth_arm', authored: 'Depth Arm' },
    { catalog: 'read', key: 'rest_restricted', authored: 'Rest-Restricted' },
    { catalog: 'read', key: 'watch_arm', authored: 'Monitor' },
  ]
  for (const { catalog, key, authored } of awkward) {
    const labels = getPitcherLabels({
      pitcher_labels: { [catalog]: { kind: catalog, key, label: authored, source: 'backend:test' } },
    })
    assert.equal(labels[catalog].label, authored, `${key} must render verbatim`)
  }
})

test('the frontend source carries no label substitution table', () => {
  // A regression here would reintroduce the second owner rather than merely
  // producing a wrong string, so it is worth pinning at the source level.
  // Comments are allowed to name the retired wording — explaining what was
  // removed is the point. Executable lines are not.
  const code = readFileSync(new URL('../src/utils/pitcherLabels.js', import.meta.url), 'utf8')
    .split('\n')
    .filter(line => !line.trim().startsWith('//'))
    .join('\n')
  for (const retired of [
    'Rest-Restricted', 'Trust Arm', 'Bridge Arm', 'Depth Arm', 'Monitor',
  ]) {
    assert.equal(code.includes(retired), false, `leaked substitution: ${retired}`)
  }
  assert.equal(code.includes('.replace('), false)
  assert.equal(code.includes('publicLabel'), false)
})

test('an absent authored label falls back to the catalog wording', () => {
  const labels = getPitcherLabels({
    pitcher_labels: {
      role: { kind: 'role', key: 'coverage_arm', source: 'backend:test' },
      read: { kind: 'read', key: 'watch_arm', label: '   ', source: 'backend:test' },
    },
  })
  assert.equal(labels.role.label, 'Coverage Arm')
  assert.equal(labels.read.label, 'Watch Arm')
})

test('canonical role keys render their canonical labels', () => {
  const cases = [
    { key: 'trust_arm', expected: 'Trusted Arm' },
    { key: 'bridge_arm', expected: 'Setup Arm' },
    { key: 'depth_arm', expected: 'Middle Relief Arm' },
    { key: 'coverage_arm', expected: 'Coverage Arm' },
    { key: 'limited_read', expected: 'Role Unclear' },
  ]
  for (const { key, expected } of cases) {
    const labels = getPitcherLabels({
      pitcher_labels: { role: { kind: 'role', key, label: expected, source: 'backend:test' } },
    })
    assert.equal(labels.role.key, key)
    assert.equal(labels.role.label, expected)
  }
})

test('the frontend never maps one role key onto another role identity', () => {
  // The frontend's job is a KEYED LOOKUP, not a translation. Given a payload
  // whose authored wording contradicts its key, the frontend must not "fix" it
  // in either direction: it renders the authored text verbatim, and the
  // identity it attaches — key, tone, reader definition — stays the key's own.
  // The Setup Arm chip's styling and definition are never borrowed.
  const contradictory = getPitcherLabels({
    pitcher_labels: { role: { kind: 'role', key: 'depth_arm', label: 'Bridge Arm', source: 'backend:test' } },
  })
  assert.equal(contradictory.role.key, 'depth_arm')
  assert.equal(contradictory.role.label, 'Bridge Arm')
  assert.equal(contradictory.role.definition, PITCHER_ROLE_LABELS.DEPTH_ARM.definition)
  assert.deepEqual(contradictory.role.tone, PITCHER_ROLE_LABELS.DEPTH_ARM.tone)
  assert.notEqual(contradictory.role.definition, PITCHER_ROLE_LABELS.BRIDGE_ARM.definition)
  // And the governed backend cannot actually author this: its own contract
  // test (backend/tests/test_pitcher_public_labels.py) pins depth_arm to
  // 'Middle Relief Arm'.
})

test('role and read fallbacks are different words', () => {
  // The collision VOC-001 removed: both families used to fall back to
  // 'Limited Read', so two chips on one card could read identically while
  // meaning different things.
  assert.equal(PITCHER_ROLE_LABELS.LIMITED_READ.label, 'Role Unclear')
  assert.equal(PITCHER_READ_LABELS.LIMITED_READ.label, 'Limited Read')
  assert.notEqual(
    PITCHER_ROLE_LABELS.LIMITED_READ.label,
    PITCHER_READ_LABELS.LIMITED_READ.label,
  )
  assert.equal(APPROVED_ROLE_LABELS.includes('Limited Read'), false)
})

test('usage-role vocabulary contract matches the backend canonical table', () => {
  // Vocabulary drift guard, mirroring backend
  // tests/test_pitcher_public_labels.py::test_canonical_vocabulary_contract.
  const expected = {
    late_high_leverage: { key: 'trust_arm', label: 'Trusted Arm' },
    setup_bridge: { key: 'bridge_arm', label: 'Setup Arm' },
    middle_relief: { key: 'depth_arm', label: 'Middle Relief Arm' },
    long_multi_inning: { key: 'coverage_arm', label: 'Coverage Arm' },
    low_unclear: { key: 'limited_read', label: 'Role Unclear' },
    insufficient_data: { key: 'limited_read', label: 'Role Unclear' },
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
