// Bullpen Shape Observation Harness
//
// Drives the real interpretation engine (team reads, weighting foundation, and
// pitcher labels) over a set of documented, representative bullpen profiles and
// prints the outputs. It builds nothing new and changes no behavior — it only
// exercises the existing modules so their reads can be audited side by side.
//
// IMPORTANT HONESTY NOTE: this environment has no live MLB feed, so the profiles
// below are representative compositions standing in for each archetype (strong /
// weak / interesting), not live readings of any club's actual roster or today's
// workload. They validate how the engine maps a bullpen's shape to its reads.
// Live-roster validation against real slates is a separate step that requires
// production data.
//
// Run: node scripts/bullpenShapeObservation.mjs

import { getTeamBullpenShape } from '../src/utils/teamBullpenScoring.js'
import { getTeamWeightingFoundation } from '../src/utils/teamWeighting.js'
import { getPitcherLabels } from '../src/utils/pitcherLabels.js'

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

let nextId = 1

// arm('Trust Arm', 'Clean Option', { fatigue_score: 78 })
function arm(roleLabel, readLabel, overrides = {}) {
  const limitedRole = roleLabel === 'Limited Read'
  return {
    pitcher_id: nextId++,
    name: `${roleLabel} ${readLabel} ${nextId}`,
    fatigue_score: overrides.fatigue_score ?? 20,
    role: {
      role_key: ROLE_KEYS[roleLabel],
      confidence: limitedRole ? 'none' : 'high',
      sample_size: limitedRole ? 0 : 4,
      evidence: limitedRole ? [] : ['4 appearances in the recent window'],
    },
    ...READ_STATUS[readLabel],
    ...overrides,
  }
}

// Build a pitcher list from a compact spec: [count, role, read, overrides].
function pen(spec) {
  return spec.flatMap(([count, roleLabel, readLabel, overrides]) =>
    Array.from({ length: count }, () => arm(roleLabel, readLabel, overrides)),
  )
}

// ── Representative profiles ────────────────────────────────────────────────
// Each profile is annotated with the shape it is meant to represent and the
// behavior we expect the engine to produce, so the printed output can be
// checked against intent.

const PROFILES = [
  // STRONG: deep pens, multiple trusted high-leverage arms, mostly clean.
  {
    team: 'Strong A (e.g. Dodgers archetype)',
    note: 'Two trusted late arms clean, full bridge/coverage/depth, lightly used.',
    cards: pen([
      [2, 'Trust Arm', 'Clean Option'],
      [2, 'Bridge Arm', 'Clean Option'],
      [1, 'Coverage Arm', 'Clean Option'],
      [2, 'Depth Arm', 'Clean Option'],
      [1, 'Depth Arm', 'Watch Arm'],
    ]),
  },
  {
    team: 'Strong B (e.g. Guardians archetype)',
    note: 'Elite trusted trio, one watched after recent use; deep behind them.',
    cards: pen([
      [2, 'Trust Arm', 'Clean Option'],
      [1, 'Trust Arm', 'Watch Arm'],
      [1, 'Bridge Arm', 'Clean Option'],
      [1, 'Coverage Arm', 'Clean Option'],
      [2, 'Depth Arm', 'Clean Option'],
    ]),
  },
  // WEAK: few/none trusted, depth-heavy, more fatigue and restriction.
  {
    team: 'Weak A (e.g. Rockies archetype)',
    note: 'No clean trusted arm, depth-heavy with several tired arms.',
    cards: pen([
      [1, 'Trust Arm', 'Rest-Restricted'],
      [1, 'Bridge Arm', 'Watch Arm'],
      [1, 'Coverage Arm', 'Rest-Restricted'],
      [3, 'Depth Arm', 'Clean Option'],
      [2, 'Depth Arm', 'Rest-Restricted'],
    ]),
  },
  {
    team: 'Weak B (e.g. Athletics archetype)',
    note: 'Thin overall, one trusted arm already overworked, depth gassed.',
    cards: pen([
      [1, 'Trust Arm', 'Unavailable'],
      [1, 'Bridge Arm', 'Rest-Restricted'],
      [4, 'Depth Arm', 'Clean Option'],
      [1, 'Depth Arm', 'Unavailable'],
    ]),
  },
  // INTERESTING: mixed shapes that stress the reconciliation logic.
  {
    team: 'Interesting A (trust-rich, depth-thin)',
    note: 'Elite trusted core, almost no usable depth behind it.',
    cards: pen([
      [2, 'Trust Arm', 'Clean Option'],
      [1, 'Bridge Arm', 'Clean Option'],
      [1, 'Coverage Arm', 'Rest-Restricted'],
      [3, 'Depth Arm', 'Unavailable'],
    ]),
  },
  {
    team: 'Interesting B (depth-rich, trust gassed)',
    note: 'Five clean depth bodies but both trusted arms restricted.',
    cards: pen([
      [2, 'Trust Arm', 'Rest-Restricted'],
      [1, 'Bridge Arm', 'Clean Option'],
      [5, 'Depth Arm', 'Clean Option'],
    ]),
  },
  {
    team: 'Interesting C (high-fatigue overuse)',
    note: 'Trusted arms clean on the board but carrying heavy fatigue scores.',
    cards: pen([
      [2, 'Trust Arm', 'Clean Option', { fatigue_score: 78 }],
      [1, 'Bridge Arm', 'Watch Arm', { fatigue_score: 72 }],
      [2, 'Coverage Arm', 'Clean Option'],
      [2, 'Depth Arm', 'Clean Option'],
    ]),
  },
  {
    team: 'Interesting D (sparse / early-season read)',
    note: 'Most arms lack a clear current read — should refuse confident output.',
    cards: pen([
      [1, 'Trust Arm', 'Clean Option'],
      [4, 'Limited Read', 'Limited Read'],
      [1, 'Depth Arm', 'Limited Read'],
    ]),
  },
]

function roleReadBreakdown(cards) {
  const counts = {}
  for (const card of cards) {
    const { role, read } = getPitcherLabels(card)
    const key = `${role.label} / ${read.label}`
    counts[key] = (counts[key] || 0) + 1
  }
  return counts
}

function line(label, value) {
  return `    ${label.padEnd(24)} ${value}`
}

for (const profile of PROFILES) {
  const shape = getTeamBullpenShape(profile.cards)
  const weighting = getTeamWeightingFoundation(profile.cards)
  console.log(`\n=== ${profile.team} ===`)
  console.log(`  shape: ${profile.note}`)
  console.log(`  arms: ${profile.cards.length}`)
  console.log('  role / read composition:')
  for (const [key, count] of Object.entries(roleReadBreakdown(profile.cards))) {
    console.log(`      ${count}x ${key}`)
  }
  console.log('  team reads:')
  console.log(line('Trust Arm Availability', shape.trustAvailability.label))
  console.log(line('Clean Options', shape.cleanOptions.label))
  console.log(line('Bullpen Pressure', shape.bullpenPressure.label))
  console.log(line('Coverage Safety', shape.coverageSafety.label))
  console.log(line('Depth Safety', shape.depthSafety.label))
  console.log('  internal weighting (not public):')
  console.log(line('meaningful options', weighting.meaningfulOptions.band))
  console.log(line('coverage usability', weighting.coverage.band))
}

console.log('\n(Representative profiles — engine logic audit, not live MLB readings.)')
