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

function pitcher(roleLabel, readLabel) {
  const limitedRole = roleLabel === 'Limited Read'
  return {
    pitcher_id: nextPitcherId++,
    name: `${roleLabel} ${readLabel} ${nextPitcherId}`,
    fatigue_score: 20,
    role: {
      role_key: ROLE_KEYS[roleLabel],
      confidence: limitedRole ? 'none' : 'high',
      sample_size: limitedRole ? 0 : 4,
      evidence: limitedRole ? [] : ['4 appearances in the recent window'],
    },
    ...READ_STATUS[readLabel],
  }
}

const shape = cards => getTeamBullpenShape(cards)
const depthLabel = cards => shape(cards).depthSafety.label

const TIER = {
  'Limited Depth Safety': 0,
  'Thin Depth Safety': 1,
  'Stable Depth Safety': 2,
  'Strong Depth Safety': 3,
}

test('Scenario A: deep volume with no usable trust arm and high pressure does not read Strong', () => {
  // Seven Depth Arms, both trusted arms restricted/unavailable.
  const cards = [
    pitcher('Trust Arm', 'Rest-Restricted'),
    pitcher('Trust Arm', 'Unavailable'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ]
  const result = shape(cards)
  assert.equal(result.bullpenPressure.label, 'High Bullpen Pressure')
  assert.ok(TIER[result.depthSafety.label] < TIER['Strong Depth Safety'], result.depthSafety.label)
  assert.equal(result.depthSafety.supportingCounts.anchoredByTrust, false)
})

test('Scenario B: deep volume with a healthy trust group keeps Strong', () => {
  const cards = [
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Watch Arm'),
    pitcher('Depth Arm', 'Clean Option'),
  ]
  assert.equal(depthLabel(cards), 'Strong Depth Safety')
})

test('Scenario C: a small bullpen with a strong trust core can stay limited on depth', () => {
  const cards = [
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ]
  assert.ok(TIER[depthLabel(cards)] <= TIER['Thin Depth Safety'], depthLabel(cards))
})

test('Scenario D: a balanced bullpen reads Stable', () => {
  const cards = [
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Watch Arm'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Rest-Restricted'),
  ]
  assert.equal(depthLabel(cards), 'Stable Depth Safety')
})

test('Scenario E: sparse data returns Limited Read', () => {
  const cards = [
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Trust Arm', 'Clean Option'),
  ]
  assert.equal(depthLabel(cards), 'Limited Read')
})

test('the trust-anchor guardrail flips Strong to Stable on trust availability alone', () => {
  // Identical depth composition; only the trust arms differ (usable vs not).
  const depthBlock = [
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Watch Arm'),
  ]
  const anchored = depthLabel([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    ...depthBlock.map(c => ({ ...c, pitcher_id: nextPitcherId++ })),
  ])
  const unanchored = depthLabel([
    pitcher('Trust Arm', 'Rest-Restricted'),
    pitcher('Trust Arm', 'Unavailable'),
    ...depthBlock.map(c => ({ ...c, pitcher_id: nextPitcherId++ })),
  ])
  assert.equal(anchored, 'Strong Depth Safety')
  assert.equal(unanchored, 'Stable Depth Safety')
})

test('the capped read explains why it is only Stable', () => {
  const result = shape([
    pitcher('Trust Arm', 'Unavailable'),
    pitcher('Trust Arm', 'Unavailable'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Watch Arm'),
    pitcher('Depth Arm', 'Clean Option'),
  ]).depthSafety
  assert.equal(result.label, 'Stable Depth Safety')
  assert.match(result.explanation, /no usable trust arm/i)
})

test('weighting only guards — Trust Arm influence never inflates the depth count', () => {
  // A trust-rich but depth-thin pen must not be lifted to Strong by trust.
  const cards = [
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ]
  assert.ok(TIER[depthLabel(cards)] < TIER['Strong Depth Safety'], depthLabel(cards))
})

test('the other four team reads are unchanged by the depth guardrail', () => {
  // Reads that should not move when only Depth Safety logic changed. Compares a
  // deep, trust-gassed pen against the labels the other reads independently
  // produce from the same composition.
  const cards = [
    pitcher('Trust Arm', 'Rest-Restricted'),
    pitcher('Trust Arm', 'Rest-Restricted'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ]
  const result = shape(cards)
  assert.equal(result.trustAvailability.label, 'Limited Trust Arm Availability')
  assert.equal(result.bullpenPressure.label, 'High Bullpen Pressure')
  assert.equal(result.cleanOptions.label, 'Healthy Clean Options')
  assert.ok(TEAM_BULLPEN_PUBLIC_LABELS.coverageSafety.includes(result.coverageSafety.label))
  // And the depth read is the one that was reconciled.
  assert.equal(result.depthSafety.label, 'Stable Depth Safety')
})
