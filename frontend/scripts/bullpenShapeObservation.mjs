// Bullpen Shape Observation Harness
//
// Drives the frontend render normalizers over backend-authored representative
// bullpen profiles and prints the outputs. It builds nothing new and changes no
// behavior; the production team-shape authority lives on the backend.
//
// IMPORTANT HONESTY NOTE: this environment has no live MLB feed, so the profiles
// below are representative compositions standing in for each archetype (strong /
// weak / interesting), not live readings of any club's actual roster or today's
// workload. They validate how the engine maps a bullpen's shape to its reads.
// Live-roster validation against real slates is a separate step that requires
// production data; this script only checks how authored payloads render.
//
// Run: node scripts/bullpenShapeObservation.mjs

import { getTeamBullpenShape } from '../src/utils/teamBullpenScoring.js'
import { getPitcherLabels } from '../src/utils/pitcherLabels.js'

const ROLE_KEYS = {
  'Trust Arm': 'late_high_leverage',
  'Bridge Arm': 'setup_bridge',
  'Coverage Arm': 'long_multi_inning',
  'Depth Arm': 'depth',
  'Limited Read': 'insufficient_data',
}

const READ_STATUS = {
  'Clean Option': { status: 'Available', key: 'clean_option' },
  'Watch Arm': { status: 'Monitor', key: 'watch_arm' },
  'Rest-Restricted': { status: 'Limited', key: 'rest_restricted' },
  Unavailable: { status: 'Unavailable', key: 'unavailable' },
  'Limited Read': { status: 'Available', key: 'limited_read' },
}

const ROLE_LABEL_KEYS = {
  'Trust Arm': 'trust_arm',
  'Bridge Arm': 'bridge_arm',
  'Coverage Arm': 'coverage_arm',
  'Depth Arm': 'depth_arm',
  'Limited Read': 'limited_read',
}

let nextId = 1

// arm('Trust Arm', 'Clean Option', { fatigue_score: 78 })
function arm(roleLabel, readLabel, overrides = {}) {
  const limitedRole = roleLabel === 'Limited Read'
  const read = READ_STATUS[readLabel] || READ_STATUS['Limited Read']
  return {
    pitcher_id: nextId++,
    name: `${roleLabel} ${readLabel} ${nextId}`,
    availability_status: read.status,
    fatigue_score: overrides.fatigue_score ?? 20,
    role: {
      role_key: ROLE_KEYS[roleLabel],
      confidence: limitedRole ? 'none' : 'high',
      sample_size: limitedRole ? 0 : 4,
      evidence: limitedRole ? [] : ['4 appearances in the recent window'],
    },
    data_state: read.key === 'limited_read' ? 'missing' : 'fresh',
    confidence: read.key === 'limited_read' ? 'low' : 'high',
    pitcher_labels: {
      role: {
        kind: 'role',
        key: ROLE_LABEL_KEYS[roleLabel] || 'limited_read',
        label: roleLabel,
        source: 'backend:fixture',
      },
      read: {
        kind: 'read',
        key: read.key,
        label: readLabel,
        source: 'backend:fixture',
      },
    },
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
    note: 'Most arms lack a clear current read in the authored fixture payload.',
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

function shapeRead(key, label, supportingCounts) {
  return {
    key,
    label,
    explanation: `${label}.`,
    supportingCounts,
    reasons: [`${label}.`],
    source: 'backend:fixture',
  }
}

function buildAuthoredShape(cards) {
  const withRole = key => cards.filter(card => card.pitcher_labels.role.key === key)
  const withRead = key => cards.filter(card => card.pitcher_labels.read.key === key)
  const trust = withRole('trust_arm')
  const bridge = withRole('bridge_arm')
  const coverage = withRole('coverage_arm')
  const depth = withRole('depth_arm')
  const clean = withRead('clean_option')
  const watch = withRead('watch_arm')
  const restricted = withRead('rest_restricted')
  const unavailable = withRead('unavailable')
  const countRead = (items, key) => items.filter(card => card.pitcher_labels.read.key === key).length
  const trustCounts = {
    trustArms: trust.length,
    availableTrustArms: countRead(trust, 'clean_option') + countRead(trust, 'watch_arm'),
    cleanTrustArms: countRead(trust, 'clean_option'),
    watchTrustArms: countRead(trust, 'watch_arm'),
    restRestrictedTrustArms: countRead(trust, 'rest_restricted'),
    unavailableTrustArms: countRead(trust, 'unavailable'),
  }
  const cleanCounts = {
    cleanOptionCount: clean.length,
    activeBullpenArms: Math.max(0, cards.length - unavailable.length),
    cleanTrustArms: countRead(trust, 'clean_option'),
    cleanBridgeArms: countRead(bridge, 'clean_option'),
    cleanCoverageArms: countRead(coverage, 'clean_option'),
    cleanDepthArms: countRead(depth, 'clean_option'),
  }
  const pressureCounts = {
    watchArmCount: watch.length,
    restRestrictedCount: restricted.length,
    unavailableCount: unavailable.length,
    highFatigueArms: cards.filter(card => card.fatigue_score >= 70).length,
    cleanTrustArms: countRead(trust, 'clean_option'),
    restrictedTrustArms: countRead(trust, 'rest_restricted'),
    unavailableTrustArms: countRead(trust, 'unavailable'),
    usableTrustArms: countRead(trust, 'clean_option') + countRead(trust, 'watch_arm'),
    stressedBridgeArms: countRead(bridge, 'rest_restricted') + countRead(bridge, 'unavailable'),
    stressedCoverageArms: countRead(coverage, 'rest_restricted') + countRead(coverage, 'unavailable'),
  }
  const coverageCounts = {
    coverageArms: coverage.length,
    availableCoverageArms: countRead(coverage, 'clean_option') + countRead(coverage, 'watch_arm'),
    cleanCoverageArms: countRead(coverage, 'clean_option'),
    watchCoverageArms: countRead(coverage, 'watch_arm'),
    restRestrictedCoverageArms: countRead(coverage, 'rest_restricted'),
    unavailableCoverageArms: countRead(coverage, 'unavailable'),
    substituteCoverageApplied: false,
  }
  const depthCounts = {
    depthArms: depth.length,
    availableDepthArms: countRead(depth, 'clean_option') + countRead(depth, 'watch_arm'),
    cleanDepthArms: countRead(depth, 'clean_option'),
    watchDepthArms: countRead(depth, 'watch_arm'),
    restRestrictedDepthArms: countRead(depth, 'rest_restricted'),
    unavailableDepthArms: countRead(depth, 'unavailable'),
    anchoredByTrust: pressureCounts.usableTrustArms > 0,
  }
  const reads = [
    shapeRead('trustAvailability', trustCounts.availableTrustArms >= 2 ? 'Stable Trust Arm Availability' : 'Limited Trust Arm Availability', trustCounts),
    shapeRead('cleanOptions', clean.length >= 5 ? 'Deep Clean Options' : clean.length >= 3 ? 'Healthy Clean Options' : 'Thin Clean Options', cleanCounts),
    shapeRead('bullpenPressure', pressureCounts.restrictedTrustArms + pressureCounts.unavailableTrustArms >= 2 ? 'High Bullpen Pressure' : pressureCounts.watchArmCount + pressureCounts.restRestrictedCount >= 3 ? 'Elevated Bullpen Pressure' : 'Low Bullpen Pressure', pressureCounts),
    shapeRead('coverageSafety', coverageCounts.availableCoverageArms >= 2 ? 'Stable Coverage Safety' : coverageCounts.availableCoverageArms >= 1 ? 'Thin Coverage Safety' : 'Limited Coverage Safety', coverageCounts),
    shapeRead('depthSafety', depthCounts.availableDepthArms >= 2 && depthCounts.anchoredByTrust ? 'Strong Depth Safety' : depthCounts.availableDepthArms >= 1 ? 'Stable Depth Safety' : 'Limited Depth Safety', depthCounts),
  ]
  const byKey = Object.fromEntries(reads.map(read => [read.key, read]))
  return {
    source: 'backend:fixture',
    reads,
    byKey,
    supportingCounts: {
      totalBullpenArms: cards.length,
      activeBullpenArms: Math.max(0, cards.length - unavailable.length),
    },
  }
}

function line(label, value) {
  return `    ${label.padEnd(24)} ${value}`
}

for (const profile of PROFILES) {
  const shape = getTeamBullpenShape({ team_shape: buildAuthoredShape(profile.cards) })
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
}

console.log('\n(Representative backend-authored fixture profiles — frontend normalization audit, not live MLB readings.)')
