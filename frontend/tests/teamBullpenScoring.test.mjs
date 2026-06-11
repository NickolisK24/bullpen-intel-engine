import assert from 'node:assert/strict'
import test from 'node:test'

import {
  TEAM_BULLPEN_PUBLIC_LABELS,
  getTeamBullpenReadKeys,
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

function shape(cards, extra = {}) {
  return getTeamBullpenShape({
    groups: [
      { status: 'Available', pitchers: cards.filter(card => card.availability_status === 'Available') },
      { status: 'Monitor', pitchers: cards.filter(card => card.availability_status === 'Monitor') },
      { status: 'Limited', pitchers: cards.filter(card => card.availability_status === 'Limited') },
      { status: 'Avoid', pitchers: cards.filter(card => card.availability_status === 'Avoid') },
      { status: 'Unavailable', pitchers: cards.filter(card => card.availability_status === 'Unavailable') },
    ],
    total_pitchers: cards.length,
    ...extra,
  })
}

const balancedFoundationCards = () => [
  pitcher('Trust Arm', 'Clean Option'),
  pitcher('Trust Arm', 'Watch Arm'),
  pitcher('Bridge Arm', 'Clean Option'),
  pitcher('Coverage Arm', 'Clean Option'),
  pitcher('Coverage Arm', 'Watch Arm'),
  pitcher('Depth Arm', 'Clean Option'),
  pitcher('Depth Arm', 'Watch Arm'),
  pitcher('Depth Arm', 'Rest-Restricted'),
]

test('every aggregate team bullpen read is produced with approved public labels', () => {
  const result = shape(balancedFoundationCards())
  assert.deepEqual(result.reads.map(read => read.key), getTeamBullpenReadKeys())
  for (const read of result.reads) {
    assert.ok(TEAM_BULLPEN_PUBLIC_LABELS[read.key].includes(read.label), `${read.key}: ${read.label}`)
    assert.equal(result.byKey[read.key], read)
  }
})

test('strong trust availability scenario uses Trust Arm read counts', () => {
  const result = shape([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Watch Arm'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Watch Arm'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Rest-Restricted'),
  ])
  assert.equal(result.trustAvailability.label, 'Strong Trust Arm Availability')
  assert.equal(result.trustAvailability.supportingCounts.trustArms, 3)
  assert.equal(result.trustAvailability.supportingCounts.cleanTrustArms, 2)
})

test('thin trust availability scenario reflects restricted and unavailable Trust Arms', () => {
  const result = shape([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Rest-Restricted'),
    pitcher('Trust Arm', 'Unavailable'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Watch Arm'),
  ])
  assert.equal(result.trustAvailability.label, 'Thin Trust Arm Availability')
  assert.equal(result.trustAvailability.supportingCounts.availableTrustArms, 1)
  assert.equal(result.trustAvailability.supportingCounts.unavailableTrustArms, 1)
})

test('deep clean options scenario is count-led and public-label only', () => {
  const result = shape([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Watch Arm'),
    pitcher('Depth Arm', 'Rest-Restricted'),
  ])
  assert.equal(result.cleanOptions.label, 'Deep Clean Options')
  assert.equal(result.cleanOptions.supportingCounts.cleanOptionCount, 6)
})

test('thin clean options scenario avoids over-reading a shallow clean group', () => {
  const result = shape([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Watch Arm'),
    pitcher('Coverage Arm', 'Watch Arm'),
    pitcher('Coverage Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Unavailable'),
    pitcher('Depth Arm', 'Rest-Restricted'),
  ])
  assert.equal(result.cleanOptions.label, 'Thin Clean Options')
  assert.equal(result.cleanOptions.supportingCounts.cleanOptionCount, 2)
})

test('high bullpen pressure scenario weights watch, restricted, unavailable, and fatigue load', () => {
  const result = shape([
    pitcher('Trust Arm', 'Watch Arm', { fatigue_score: 75 }),
    pitcher('Trust Arm', 'Rest-Restricted'),
    pitcher('Bridge Arm', 'Watch Arm'),
    pitcher('Coverage Arm', 'Rest-Restricted'),
    pitcher('Coverage Arm', 'Unavailable'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ])
  assert.equal(result.bullpenPressure.label, 'High Bullpen Pressure')
  assert.equal(result.bullpenPressure.supportingCounts.watchArmCount, 2)
  assert.equal(result.bullpenPressure.supportingCounts.restRestrictedCount, 2)
  assert.equal(result.bullpenPressure.supportingCounts.unavailableCount, 1)
  assert.equal(result.bullpenPressure.supportingCounts.highFatigueArms, 1)
})

test('low bullpen pressure scenario stays descriptive without scores', () => {
  const result = shape([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Watch Arm'),
  ])
  assert.equal(result.bullpenPressure.label, 'Low Bullpen Pressure')
  assert.equal(result.bullpenPressure.supportingCounts.restRestrictedCount, 0)
  assert.equal(result.bullpenPressure.supportingCounts.unavailableCount, 0)
})

test('strong coverage safety scenario requires clean available Coverage Arms', () => {
  const result = shape([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Watch Arm'),
  ])
  assert.equal(result.coverageSafety.label, 'Strong Coverage Safety')
  assert.equal(result.coverageSafety.supportingCounts.coverageArms, 2)
  assert.equal(result.coverageSafety.supportingCounts.cleanCoverageArms, 2)
})

test('limited coverage safety scenario reflects unavailable coverage options', () => {
  const result = shape([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Rest-Restricted'),
    pitcher('Coverage Arm', 'Unavailable'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Watch Arm'),
  ])
  assert.equal(result.coverageSafety.label, 'Limited Coverage Safety')
  assert.equal(result.coverageSafety.supportingCounts.availableCoverageArms, 0)
})

test('strong depth safety scenario requires enough available fallback depth', () => {
  const result = shape([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Watch Arm'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Watch Arm'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Watch Arm'),
  ])
  assert.equal(result.depthSafety.label, 'Strong Depth Safety')
  assert.equal(result.depthSafety.supportingCounts.depthArms, 3)
  assert.equal(result.depthSafety.supportingCounts.availableDepthArms, 3)
})

test('limited depth safety scenario handles missing fallback depth', () => {
  const result = shape([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Watch Arm'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Watch Arm'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Watch Arm'),
  ])
  assert.equal(result.depthSafety.label, 'Limited Depth Safety')
  assert.equal(result.depthSafety.supportingCounts.depthArms, 0)
})

test('sparse data returns Limited Read instead of false certainty', () => {
  const result = shape([
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Limited Read', 'Limited Read'),
  ])
  for (const read of result.reads) {
    assert.equal(read.label, 'Limited Read', read.key)
  }
})

test('every public read is explainable from supporting counts', () => {
  const result = shape(balancedFoundationCards())
  for (const read of result.reads) {
    assert.ok(read.explanation.length > 20, read.key)
    assert.ok(Object.keys(read.supportingCounts).length > 0, read.key)
    assert.ok(Array.isArray(read.reasons) && read.reasons.length > 0, read.key)
    const numericCounts = Object.values(read.supportingCounts).filter(value => typeof value === 'number')
    assert.ok(numericCounts.some(value => read.explanation.includes(String(value))), read.key)
  }
})

test('public output exposes no numeric score or ranking fields', () => {
  const result = shape(balancedFoundationCards())
  const visit = (value, path = []) => {
    if (Array.isArray(value)) {
      value.forEach((item, index) => visit(item, [...path, String(index)]))
      return
    }
    if (!value || typeof value !== 'object') return
    for (const [key, child] of Object.entries(value)) {
      assert.equal(/score|rank|leaderboard/i.test(key), false, [...path, key].join('.'))
      if (typeof child === 'string') {
        assert.equal(/score:|ranking|leaderboard/i.test(child), false, [...path, key].join('.'))
      }
      visit(child, [...path, key])
    }
  }
  visit(result)
})
