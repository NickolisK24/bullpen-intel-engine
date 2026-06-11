import assert from 'node:assert/strict'
import test from 'node:test'

import {
  TEAM_BULLPEN_PUBLIC_LABELS,
  getTeamBullpenShape,
} from '../src/utils/teamBullpenScoring.js'

const ROLE_KEYS = {
  'Trust Arm': 'late_high_leverage',
  'Bridge Arm': 'setup_bridge',
  'Coverage Arm': 'long_multi_inning',
  'Depth Arm': 'depth',
  'Limited Read': 'insufficient_data',
}

const READ_STATUS = {
  'Clean Option': { availability_status: 'Available', data_state: 'fresh', confidence: 'high' },
  'Watch Arm': { availability_status: 'Monitor', data_state: 'fresh', confidence: 'high' },
  'Rest-Restricted': { availability_status: 'Limited', data_state: 'fresh', confidence: 'high' },
  Unavailable: { availability_status: 'Unavailable', data_state: 'fresh', confidence: 'high' },
  'Limited Read': { availability_status: 'Available', data_state: 'missing', confidence: 'low' },
}

let nextPitcherId = 1

function pitcher(roleLabel, readLabel, overrides = {}) {
  const roleKey = ROLE_KEYS[roleLabel]
  const readFields = READ_STATUS[readLabel]
  const limitedRole = roleLabel === 'Limited Read'
  return {
    pitcher_id: nextPitcherId++,
    name: `${roleLabel} ${readLabel} ${nextPitcherId}`,
    fatigue_score: 20,
    role: {
      role_key: roleKey,
      confidence: limitedRole ? 'none' : 'high',
      sample_size: limitedRole ? 0 : 4,
      evidence: limitedRole ? [] : ['4 appearances in the recent window'],
    },
    ...readFields,
    ...overrides,
  }
}

const pressureLabel = cards => getTeamBullpenShape(cards).bullpenPressure.label

const PRESSURE_RANK = {
  'Low Bullpen Pressure': 0,
  'Manageable Bullpen Pressure': 1,
  'Elevated Bullpen Pressure': 2,
  'High Bullpen Pressure': 3,
}

// A baseline of clean depth that keeps a bullpen readable (>=4 arms, >=50%
// labeled) without itself adding pressure.
const cleanDepthFiller = (n) => Array.from({ length: n }, () => pitcher('Depth Arm', 'Clean Option'))

test('trust arm restriction increases pressure more than the same depth restriction', () => {
  const trustRestricted = pressureLabel([
    pitcher('Trust Arm', 'Rest-Restricted'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    ...cleanDepthFiller(4),
  ])
  const depthRestricted = pressureLabel([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    ...cleanDepthFiller(3),
  ])
  assert.ok(
    PRESSURE_RANK[trustRestricted] > PRESSURE_RANK[depthRestricted],
    `trust-restricted (${trustRestricted}) should outrank depth-restricted (${depthRestricted})`,
  )
})

test('bridge arm restriction matters more than the same depth restriction', () => {
  const base = [
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    ...cleanDepthFiller(3),
  ]
  const bridgeRestricted = pressureLabel([...base, pitcher('Bridge Arm', 'Rest-Restricted')])
  const depthRestricted = pressureLabel([...base, pitcher('Depth Arm', 'Rest-Restricted')])
  assert.ok(
    PRESSURE_RANK[bridgeRestricted] > PRESSURE_RANK[depthRestricted],
    `bridge-restricted (${bridgeRestricted}) should outrank depth-restricted (${depthRestricted})`,
  )
})

test('coverage loss influences pressure but reads differently than the same trust loss', () => {
  const base = [
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ]
  const coverageLost = pressureLabel([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Unavailable'),
    pitcher('Coverage Arm', 'Unavailable'),
    ...base,
  ])
  const trustLost = pressureLabel([
    pitcher('Trust Arm', 'Unavailable'),
    pitcher('Trust Arm', 'Unavailable'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    ...base,
  ])
  // Coverage loss is felt (above Low)...
  assert.ok(PRESSURE_RANK[coverageLost] >= PRESSURE_RANK['Elevated Bullpen Pressure'])
  // ...but an identical loss among Trust Arms reads heavier.
  assert.ok(
    PRESSURE_RANK[trustLost] > PRESSURE_RANK[coverageLost],
    `trust loss (${trustLost}) should outrank coverage loss (${coverageLost})`,
  )
})

test('a healthy trust group suppresses overreaction to tired depth arms', () => {
  // 2 clean Trust Arms with four Rest-Restricted Depth Arms. The old role-blind
  // model read this High (4 restricted); with weighting the intact trust core
  // holds it at Elevated rather than High.
  const label = pressureLabel([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
  ])
  assert.equal(label, 'Elevated Bullpen Pressure')
})

test('trust arms heavily restricted drive pressure to High', () => {
  const label = pressureLabel([
    pitcher('Trust Arm', 'Rest-Restricted'),
    pitcher('Trust Arm', 'Rest-Restricted'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    ...cleanDepthFiller(3),
  ])
  assert.equal(label, 'High Bullpen Pressure')
})

test('a bullpen with no usable trust option cannot read Low even when fully rested', () => {
  const label = pressureLabel([
    pitcher('Bridge Arm', 'Clean Option'),
    ...cleanDepthFiller(5),
  ])
  assert.ok(
    PRESSURE_RANK[label] >= PRESSURE_RANK['Elevated Bullpen Pressure'],
    `trustless rested pen should be at least Elevated, got ${label}`,
  )
})

test('a deep bullpen with a healthy trust group reads Low', () => {
  const label = pressureLabel([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Watch Arm'),
  ])
  assert.equal(label, 'Low Bullpen Pressure')
})

test('sparse data still returns Limited Read for bullpen pressure', () => {
  const label = pressureLabel([
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Trust Arm', 'Clean Option'),
  ])
  assert.equal(label, 'Limited Read')
})

test('bullpen pressure always renders an approved public label and no weight values', () => {
  const samples = [
    [pitcher('Trust Arm', 'Rest-Restricted'), pitcher('Trust Arm', 'Unavailable'), ...cleanDepthFiller(5)],
    [pitcher('Trust Arm', 'Clean Option'), pitcher('Trust Arm', 'Clean Option'), pitcher('Coverage Arm', 'Unavailable'), pitcher('Coverage Arm', 'Unavailable'), ...cleanDepthFiller(3)],
    [pitcher('Bridge Arm', 'Clean Option'), ...cleanDepthFiller(5)],
  ]
  for (const cards of samples) {
    const result = getTeamBullpenShape(cards).bullpenPressure
    assert.ok(
      TEAM_BULLPEN_PUBLIC_LABELS.bullpenPressure.includes(result.label),
      `unexpected label: ${result.label}`,
    )
    // No role weight values (3 / 2 / 1) or band/score vocabulary leak into the
    // public payload.
    const visit = (value) => {
      if (Array.isArray(value)) return value.forEach(visit)
      if (!value || typeof value !== 'object') return
      for (const [key, child] of Object.entries(value)) {
        assert.equal(/weight|score|rank|leaderboard|band/i.test(key), false, key)
        if (typeof child === 'string') {
          assert.equal(/weight:|score:|ranking|leaderboard/i.test(child), false, key)
        }
        visit(child)
      }
    }
    visit(result)
  }
})
