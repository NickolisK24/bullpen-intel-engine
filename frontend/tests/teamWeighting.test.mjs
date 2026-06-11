import assert from 'node:assert/strict'
import test from 'node:test'

import {
  MEANINGFUL_OPTION_BANDS,
  READ_USABILITY,
  ROLE_INFLUENCE,
  coverageUsability,
  getTeamWeightingFoundation,
  meaningfulOptionsBand,
  summarizeWeightedBullpen,
} from '../src/utils/teamWeighting.js'
import { getTeamBullpenShape } from '../src/utils/teamBullpenScoring.js'

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

test('role influence hierarchy orders trust above bridge and coverage above depth', () => {
  assert.ok(ROLE_INFLUENCE.trust_arm.weight > ROLE_INFLUENCE.bridge_arm.weight)
  assert.ok(ROLE_INFLUENCE.bridge_arm.weight > ROLE_INFLUENCE.depth_arm.weight)
  assert.ok(ROLE_INFLUENCE.coverage_arm.weight > ROLE_INFLUENCE.depth_arm.weight)
  assert.equal(ROLE_INFLUENCE.limited_read.weight, 0)
  assert.equal(READ_USABILITY.clean_option, 1)
  assert.equal(READ_USABILITY.rest_restricted, 0)
  assert.equal(READ_USABILITY.unavailable, 0)
})

test('a clean trust arm contributes more usable influence than a clean depth arm', () => {
  const trustOnly = summarizeWeightedBullpen([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Rest-Restricted'),
    pitcher('Coverage Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
  ])
  const depthOnly = summarizeWeightedBullpen([
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Rest-Restricted'),
    pitcher('Coverage Arm', 'Rest-Restricted'),
    pitcher('Trust Arm', 'Rest-Restricted'),
  ])
  assert.ok(trustOnly.usableInfluence > depthOnly.usableInfluence)
})

test('losing a trust arm raises weighted pressure more than losing a depth arm', () => {
  const trustLost = summarizeWeightedBullpen([
    pitcher('Trust Arm', 'Rest-Restricted'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ])
  const depthLost = summarizeWeightedBullpen([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Rest-Restricted'),
  ])
  assert.ok(trustLost.weightedPressure > depthLost.weightedPressure)
  assert.ok(trustLost.trustPressure > 0)
  assert.equal(depthLost.trustPressure, 0)
})

test('product question: five clean depth arms do not read broader than a clean trust core', () => {
  // Example A — 5 Clean Depth Arms, 0 Clean Trust Arms (trust arms restricted).
  const exampleA = meaningfulOptionsBand([
    pitcher('Trust Arm', 'Rest-Restricted'),
    pitcher('Trust Arm', 'Unavailable'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ])
  // Example B — 2 Clean Trust Arms, 1 Clean Bridge Arm, no depth.
  const exampleB = meaningfulOptionsBand([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Unavailable'),
  ])
  assert.ok(MEANINGFUL_OPTION_BANDS.includes(exampleA.band))
  assert.ok(MEANINGFUL_OPTION_BANDS.includes(exampleB.band))
  // The two bullpens must not receive identical reads, and the trust-led pen
  // must read at least as usable as the depth-led pen.
  const rank = band => MEANINGFUL_OPTION_BANDS.indexOf(band)
  assert.ok(rank(exampleB.band) < rank(exampleA.band),
    `expected trust-led (${exampleB.band}) to read broader than depth-led (${exampleA.band})`)
})

test('a bullpen with no usable trust influence cannot read broad on depth volume', () => {
  const result = meaningfulOptionsBand([
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ])
  assert.equal(result.band, 'narrow')
})

test('fully clean trust arms protect the read from collapsing on depth fatigue alone', () => {
  const result = meaningfulOptionsBand([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
  ])
  assert.equal(result.band, 'workable')
})

test('coverage usability is led by coverage arms, not trust arms', () => {
  const coverageClean = coverageUsability([
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
  ])
  const trustClean = coverageUsability([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
  ])
  assert.equal(coverageClean.band, 'broad')
  assert.ok(trustClean.usableCoverageInfluence < coverageClean.usableCoverageInfluence)
  assert.notEqual(trustClean.band, 'broad')
})

test('depth arms contribute partial fallback coverage influence', () => {
  const withDepth = coverageUsability([
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
  ])
  const withoutDepth = coverageUsability([
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Trust Arm', 'Clean Option'),
  ])
  assert.ok(withDepth.usableCoverageInfluence > withoutDepth.usableCoverageInfluence)
})

test('sparse or tiny bullpens return limited_read instead of a confident band', () => {
  const empty = meaningfulOptionsBand([])
  assert.equal(empty.band, 'limited_read')

  const tiny = meaningfulOptionsBand([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ])
  assert.equal(tiny.band, 'limited_read')

  const unreadable = getTeamWeightingFoundation([
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Limited Read', 'Limited Read'),
  ])
  assert.equal(unreadable.meaningfulOptions.band, 'limited_read')
  assert.equal(unreadable.coverage.band, 'limited_read')
  assert.equal(unreadable.summary.limitedRead, true)
})

test('weighting foundation does not alter existing public team reads', () => {
  const cards = [
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Watch Arm'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Watch Arm'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Watch Arm'),
    pitcher('Depth Arm', 'Rest-Restricted'),
  ]
  const before = getTeamBullpenShape(cards)
  getTeamWeightingFoundation(cards)
  const after = getTeamBullpenShape(cards)
  assert.deepEqual(
    after.reads.map(read => [read.key, read.label]),
    before.reads.map(read => [read.key, read.label]),
  )
})

test('internal output exposes no ranking, leaderboard, or grade vocabulary', () => {
  const result = getTeamWeightingFoundation([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Watch Arm'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Rest-Restricted'),
    pitcher('Depth Arm', 'Clean Option'),
  ])
  const visit = (value, path = []) => {
    if (Array.isArray(value)) {
      value.forEach((item, index) => visit(item, [...path, String(index)]))
      return
    }
    if (!value || typeof value !== 'object') return
    for (const [key, child] of Object.entries(value)) {
      assert.equal(/rank|leaderboard|grade/i.test(key), false, [...path, key].join('.'))
      visit(child, [...path, key])
    }
  }
  visit(result)
})
