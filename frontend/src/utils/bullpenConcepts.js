// The BaseballOS vocabulary layer — four named reads that describe bullpen
// state in plain baseball language: Bullpen Pressure, Recovery Window,
// Workload Concentration, and Clean Options.
//
// These are descriptive product concepts, not metrics. Every label derives
// from the same availability counts the rest of the frontend already shows
// (rested / watch / needing-rest / total), with fixed, inspectable tiers —
// no scoring, no model, nothing the page can't explain in a sentence.

export const CONCEPT_DEFINITIONS = {
  pressure: {
    name: 'Bullpen Pressure',
    definition: 'How much workload strain the bullpen is carrying today.',
  },
  recovery: {
    name: 'Recovery Window',
    definition: 'How much clean rest the bullpen has available.',
  },
  concentration: {
    name: 'Workload Concentration',
    definition: 'Whether recent work is spread around or clustered on a few arms.',
  },
  cleanOptions: {
    name: 'Clean Options',
    definition: 'How many arms enter today without major recent workload restriction.',
  },
}

// Supporting glossary concepts. These are named on public surfaces (the team
// state card, How to Read) but are not derived reads — they carry no tiers
// here, only their one-line public definitions, so the whole product shares a
// single dictionary.
export const SUPPORTING_CONCEPT_DEFINITIONS = Object.freeze({
  coverageSafety: {
    name: 'Coverage Safety',
    definition: 'Whether the bullpen can cover the late innings if the game runs long.',
  },
  // VOC-001: renamed from 'Trusted Arms'. It was never the plural of the
  // pitcher ROLE 'Trusted Arm' — it mixes role with current workload and
  // roster context — and two different things must not share a name.
  // 'lean on' also implied manager intent, which is not observed.
  trustedArms: {
    name: 'Late-Inning Options',
    definition:
      'Current late-inning arms whose workload and roster context leave them '
      + 'usable in the represented read.',
  },
})

// Team state vocabulary (Fresh / Stretched / Vulnerable).
export const TEAM_STATE_DEFINITIONS = Object.freeze([
  Object.freeze({ name: 'Fresh', definition: 'The bullpen comes in mostly rested, with room to maneuver late.' }),
  Object.freeze({ name: 'Stretched', definition: 'The bullpen is thin on rested arms after recent work.' }),
  Object.freeze({ name: 'Vulnerable', definition: 'Little late-inning margin remains if the game runs long.' }),
])

// Per-arm availability vocabulary (the four public statuses).
export const ARM_AVAILABILITY_DEFINITIONS = Object.freeze([
  Object.freeze({ name: 'Available', definition: 'Rested enough to pitch today.' }),
  Object.freeze({ name: 'On Watch', definition: 'Usable, but recent work is worth watching.' }),
  Object.freeze({ name: 'Limited', definition: 'Available only in a reduced role after recent work.' }),
  Object.freeze({ name: 'Unavailable', definition: 'Not available today because of rest or roster status.' }),
])

// Freshness stamp vocabulary.
export const FRESHNESS_LABEL_DEFINITIONS = Object.freeze([
  Object.freeze({ name: 'Data through', definition: 'The latest completed MLB date included in the read.' }),
  Object.freeze({ name: 'Updated', definition: 'When BaseballOS last wrote new baseball data.' }),
])

export const LIMITED_READ_LABEL = 'Limited Read'

// VOC-001 / #638: the local bullpen tier-derivation engine that used to live
// below this line is gone. It computed its own pressure / recovery /
// concentration / clean-options tiers in the browser from raw counts — a
// second set of supporting reads competing with the backend-owned ones in
// services/team_bullpen_shape.py. It had no production caller: nothing in
// src/ imported getBullpenReads or getReadsForLandscapeEntry, and this
// module's only production importer is HowToRead.jsx, which takes the
// definitions above.
//
// What remains here is a glossary: canonical public definitions rendered by
// How to Read. This file must not compute a bullpen read again — the backend
// owns supporting-read tiers, and bullpenConcepts.test.mjs pins that.
