// Live Slate Validation Harness
//
// Intended purpose: read BaseballOS bullpen outputs for real current MLB clubs
// and judge whether they feel correct. THIS ENVIRONMENT HAS NO LIVE MLB FEED:
// outbound network is blocked (statsapi.mlb.com returns 403) and no seeded
// database is present, so today's rosters and day-of availability cannot be
// observed here. Inventing those reads would violate the branch's first rule.
//
// What this harness does instead, honestly: it exercises the fully-reconciled
// engine over each club's KNOWN bullpen CONSTRUCTION (role composition is stable
// baseball knowledge), at a rested baseline where every arm is a Clean Option.
// That isolates the role-composition-sensitive reads — Trust Arm Availability,
// Coverage Safety, Depth Safety, and the structure of Clean Options — and lets
// us check whether the engine reads each construction sensibly. It deliberately
// does NOT fabricate a workload, so Bullpen Pressure reads Low for everyone here;
// Pressure and the Clean/Watch/Rest-Restricted read layer can only be validated
// against a real slate, which this environment cannot provide.
//
// Run: node scripts/liveSlateValidation.mjs

import { getTeamBullpenShape } from '../src/utils/teamBullpenScoring.js'
import { getPitcherLabels } from '../src/utils/pitcherLabels.js'

const ROLE_KEYS = {
  'Trust Arm': 'late_high_leverage',
  'Bridge Arm': 'setup_bridge',
  'Coverage Arm': 'long_multi_inning',
  'Depth Arm': 'depth',
}

let nextId = 1
function clean(roleLabel) {
  return {
    pitcher_id: nextId++,
    name: `${roleLabel} ${nextId}`,
    fatigue_score: 20,
    role: { role_key: ROLE_KEYS[roleLabel], confidence: 'high', sample_size: 4, evidence: ['4 appearances'] },
    availability_status: 'Available',
    data_state: 'fresh',
    confidence: 'high',
  }
}

// [trust, bridge, coverage, depth] at a rested baseline. Compositions reflect
// each franchise's recent bullpen construction identity (knowledge through early
// 2026) — an archetype of how the pen is BUILT, not a live roster snapshot.
const CONSTRUCTIONS = [
  ['Dodgers (strong)', [3, 2, 1, 3]],
  ['Yankees (strong)', [2, 2, 1, 2]],
  ['Mariners (strong)', [2, 2, 1, 2]],
  ['Guardians (strong)', [3, 2, 1, 2]],
  ['Rockies (weak)', [1, 1, 1, 5]],
  ['Athletics (weak)', [1, 1, 1, 4]],
  ['Brewers (interesting)', [2, 2, 1, 2]],
  ['Mets (interesting/top-heavy)', [1, 2, 1, 3]],
  ['Rays (interesting/coverage-rich)', [1, 2, 3, 2]],
  ['Marlins (interesting/mixed)', [1, 1, 2, 3]],
]

function build([t, b, c, d]) {
  return [
    ...Array.from({ length: t }, () => clean('Trust Arm')),
    ...Array.from({ length: b }, () => clean('Bridge Arm')),
    ...Array.from({ length: c }, () => clean('Coverage Arm')),
    ...Array.from({ length: d }, () => clean('Depth Arm')),
  ]
}

const pad = (s, n) => String(s).padEnd(n)

console.log('REST-BASELINE CONSTRUCTION READS (no live workload — see header note)\n')
console.log(pad('Team', 32), pad('TrustAvail', 12), pad('CleanOpt', 10), pad('Pressure', 12), pad('Coverage', 10), pad('Depth', 10))

for (const [team, comp] of CONSTRUCTIONS) {
  const cards = build(comp)
  const s = getTeamBullpenShape(cards)
  // Confirm role labels map as constructed (sanity on the label taxonomy).
  const roleCounts = {}
  for (const card of cards) {
    const { role } = getPitcherLabels(card)
    roleCounts[role.label] = (roleCounts[role.label] || 0) + 1
  }
  const short = label => label.replace(/ (Trust Arm Availability|Clean Options|Bullpen Pressure|Coverage Safety|Depth Safety)$/, '')
  console.log(
    pad(team, 32),
    pad(short(s.trustAvailability.label), 12),
    pad(short(s.cleanOptions.label), 10),
    pad(short(s.bullpenPressure.label), 12),
    pad(short(s.coverageSafety.label), 10),
    pad(short(s.depthSafety.label), 10),
  )
}

console.log('\nConstruction-archetype engine behavior — NOT a live MLB reading.')
console.log('Pressure is Low for all because the baseline is fully rested; the read')
console.log('layer (Clean/Watch/Rest-Restricted) requires a real slate to validate.')
