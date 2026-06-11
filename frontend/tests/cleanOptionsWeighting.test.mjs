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

const TIER = {
  'Very Thin Clean Options': 0,
  'Thin Clean Options': 1,
  'Healthy Clean Options': 2,
  'Deep Clean Options': 3,
}

const cleanOptions = cards => getTeamBullpenShape(cards).cleanOptions

// Scenario A — five clean Depth Arms, trust group restricted/unavailable.
const SCENARIO_A = [
  pitcher('Trust Arm', 'Rest-Restricted'),
  pitcher('Trust Arm', 'Unavailable'),
  pitcher('Depth Arm', 'Clean Option'),
  pitcher('Depth Arm', 'Clean Option'),
  pitcher('Depth Arm', 'Clean Option'),
  pitcher('Depth Arm', 'Clean Option'),
  pitcher('Depth Arm', 'Clean Option'),
]
// Scenario B — two clean Trust Arms plus a clean Bridge Arm.
const SCENARIO_B = [
  pitcher('Trust Arm', 'Clean Option'),
  pitcher('Trust Arm', 'Clean Option'),
  pitcher('Bridge Arm', 'Clean Option'),
  pitcher('Depth Arm', 'Rest-Restricted'),
  pitcher('Depth Arm', 'Rest-Restricted'),
  pitcher('Depth Arm', 'Rest-Restricted'),
  pitcher('Depth Arm', 'Rest-Restricted'),
]

test('Scenario A: raw count stays high but the read is not overly healthy', () => {
  const result = cleanOptions(SCENARIO_A)
  assert.equal(result.supportingCounts.cleanOptionCount, 5)
  assert.ok(
    TIER[result.label] <= TIER['Thin Clean Options'],
    `expected not-overly-healthy, got ${result.label}`,
  )
})

test('Scenario B reads stronger than Scenario A despite a lower raw count', () => {
  const a = cleanOptions(SCENARIO_A)
  const b = cleanOptions(SCENARIO_B)
  assert.equal(b.supportingCounts.cleanOptionCount, 3)
  assert.ok(b.supportingCounts.cleanOptionCount < a.supportingCounts.cleanOptionCount)
  assert.ok(
    TIER[b.label] > TIER[a.label],
    `expected B (${b.label}) stronger than A (${a.label})`,
  )
})

test('Scenario C: one clean trust arm with deep clean depth is middle ground', () => {
  const result = cleanOptions([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Rest-Restricted'),
  ])
  assert.equal(result.supportingCounts.cleanOptionCount, 6)
  assert.equal(result.label, 'Healthy Clean Options')
})

test('Scenario D: several clean trust arms earn the strongest interpretation', () => {
  const result = cleanOptions([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Coverage Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ])
  assert.equal(result.label, 'Deep Clean Options')
})

test('Scenario E: many clean arms but an unavailable trust group is downgraded', () => {
  const result = cleanOptions([
    pitcher('Trust Arm', 'Unavailable'),
    pitcher('Trust Arm', 'Unavailable'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ])
  assert.equal(result.supportingCounts.cleanOptionCount, 6)
  // Six clean arms would have been Deep on raw count; the lost trust core caps it.
  assert.ok(TIER[result.label] < TIER['Deep Clean Options'], result.label)
})

test('Scenario F: sparse data returns Limited Read', () => {
  const result = cleanOptions([
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Limited Read', 'Limited Read'),
    pitcher('Trust Arm', 'Clean Option'),
  ])
  assert.equal(result.label, 'Limited Read')
})

test('clean trust arms influence interpretation more than clean depth arms', () => {
  const trustLed = cleanOptions([
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Trust Arm', 'Clean Option'),
    pitcher('Bridge Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Unavailable'),
    pitcher('Depth Arm', 'Unavailable'),
    pitcher('Depth Arm', 'Unavailable'),
  ])
  const depthLed = cleanOptions([
    pitcher('Trust Arm', 'Unavailable'),
    pitcher('Trust Arm', 'Unavailable'),
    pitcher('Bridge Arm', 'Unavailable'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ])
  assert.ok(
    TIER[trustLed.label] > TIER[depthLed.label],
    `trust-led (${trustLed.label}) should outrank depth-led (${depthLed.label})`,
  )
})

test('high clean depth alone cannot reach the strongest interpretation', () => {
  const result = cleanOptions([
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
    pitcher('Depth Arm', 'Clean Option'),
  ])
  assert.equal(result.supportingCounts.cleanOptionCount, 6)
  assert.ok(TIER[result.label] <= TIER['Thin Clean Options'], result.label)
})

test('raw clean-option count is always preserved and visible in the explanation', () => {
  for (const cards of [SCENARIO_A, SCENARIO_B]) {
    const result = cleanOptions(cards)
    const raw = result.supportingCounts.cleanOptionCount
    assert.equal(typeof raw, 'number')
    assert.ok(result.explanation.includes(String(raw)), result.explanation)
  }
})

test('clean options always renders an approved public label with no weight values', () => {
  const samples = [SCENARIO_A, SCENARIO_B]
  for (const cards of samples) {
    const result = cleanOptions(cards)
    assert.ok(TEAM_BULLPEN_PUBLIC_LABELS.cleanOptions.includes(result.label), result.label)
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
