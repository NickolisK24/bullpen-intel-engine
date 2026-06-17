import assert from 'node:assert/strict'
import test from 'node:test'

import {
  TEAM_BULLPEN_PUBLIC_LABELS,
  getTeamBullpenReadKeys,
  getTeamBullpenScoring,
  getTeamBullpenShape,
} from '../src/utils/teamBullpenScoring.js'

const backendShape = Object.freeze({
  source: 'backend',
  reads: [
    {
      key: 'trustAvailability',
      label: 'Stable Trust Arm Availability',
      explanation: 'Two trust arms remain usable.',
      supportingCounts: { trustArms: 2, availableTrustArms: 2 },
      reasons: ['Two trust arms remain usable.'],
      source: 'backend',
    },
    {
      key: 'cleanOptions',
      label: 'Healthy Clean Options',
      explanation: 'Four clean options are available.',
      supportingCounts: { cleanOptionCount: 4, activeBullpenArms: 7 },
      reasons: ['Four clean options are available.'],
      source: 'backend',
    },
    {
      key: 'bullpenPressure',
      label: 'Elevated Bullpen Pressure',
      explanation: 'Trust and bridge stress are elevated.',
      supportingCounts: { watchArmCount: 2, restRestrictedCount: 1 },
      reasons: ['Trust and bridge stress are elevated.'],
      source: 'backend',
    },
    {
      key: 'workloadConcentration',
      label: 'Some Workload Concentration',
      explanation: 'The top three arms carried 62% of recent relief pitches.',
      supportingCounts: {
        topArmCount: 3,
        topSharePct: 62,
        concentrationDescriptor: 'some concentration',
      },
      reasons: ['The top three arms carried 62% of recent relief pitches.'],
      source: 'backend',
    },
    {
      key: 'coverageSafety',
      label: 'Thin Coverage Safety',
      explanation: 'One coverage arm remains usable.',
      supportingCounts: { coverageArms: 2, availableCoverageArms: 1 },
      reasons: ['One coverage arm remains usable.'],
      source: 'backend',
    },
    {
      key: 'depthSafety',
      label: 'Stable Depth Safety',
      explanation: 'Depth is stable behind the trust layer.',
      supportingCounts: { depthArms: 3, availableDepthArms: 2 },
      reasons: ['Depth is stable behind the trust layer.'],
      source: 'backend',
    },
  ],
  supportingCounts: {
    totalBullpenArms: 7,
    activeBullpenArms: 7,
    roleKnownCount: 7,
    readKnownCount: 7,
  },
})

test('team bullpen shape consumes backend-authored reads', () => {
  const result = getTeamBullpenShape({ team_shape: backendShape })

  assert.deepEqual(result.reads.map(read => read.key), getTeamBullpenReadKeys())
  assert.equal(result.source, 'backend')
  assert.equal(result.cleanOptions.label, 'Healthy Clean Options')
  assert.equal(result.workloadConcentration.label, 'Some Workload Concentration')
  assert.equal(result.cleanOptions.supportingCounts.cleanOptionCount, 4)
  assert.equal(result.bullpenPressure.explanation, 'Trust and bridge stress are elevated.')
  assert.equal(result.byKey.coverageSafety, result.coverageSafety)
  assert.deepEqual(result.supportingCounts, backendShape.supportingCounts)
})

test('camelCase teamShape payloads normalize the same way', () => {
  const result = getTeamBullpenScoring({ teamShape: backendShape })
  assert.equal(result.trustAvailability.label, 'Stable Trust Arm Availability')
  assert.equal(result.depthSafety.supportingCounts.depthArms, 3)
})

test('missing backend team shape fails closed to Limited Read instead of recomputing from pitchers', () => {
  const result = getTeamBullpenShape({
    groups: [
      {
        status: 'Available',
        pitchers: [
          {
            name: 'Client Should Not Infer',
            availability_status: 'Available',
            fatigue_score: 1,
            role: { role_key: 'late_high_leverage' },
          },
        ],
      },
    ],
  })

  for (const read of result.reads) {
    assert.equal(read.label, 'Limited Read', read.key)
    assert.equal(read.source, 'missing_backend_team_shape')
  }
})

test('unapproved backend labels fail closed to Limited Read', () => {
  const result = getTeamBullpenShape({
    team_shape: {
      reads: [
        {
          key: 'cleanOptions',
          label: 'Best Bullpen Grade',
          explanation: 'Invalid backend label.',
          supportingCounts: { cleanOptionCount: 9 },
        },
      ],
    },
  })

  assert.equal(result.cleanOptions.label, 'Limited Read')
  assert.equal(result.cleanOptions.explanation, 'Invalid backend label.')
})

test('public read labels remain constrained to approved sets', () => {
  const result = getTeamBullpenShape({ team_shape: backendShape })
  for (const read of result.reads) {
    assert.ok(TEAM_BULLPEN_PUBLIC_LABELS[read.key].includes(read.label), `${read.key}: ${read.label}`)
  }
})
