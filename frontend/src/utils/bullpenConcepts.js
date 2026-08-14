// The BaseballOS vocabulary layer — three named reads that describe bullpen
// state in plain baseball language: Bullpen Pressure, Recovery Window, and
// Workload Concentration.
//
// A fourth entry, the team-level `Clean Options`, was retired here. The team
// read is `Rested Options` (SUPPORTING_CONCEPT_DEFINITIONS.restedOptions);
// `Clean Option` singular remains the PITCHER current read and is unaffected.
// The entry rendered nowhere — How to Read pulls only `concentration` from this
// object — but a test pinned its retired name, so CI was defending vocabulary
// the canonical standards had already replaced.
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
  lateInningAvailability: {
    name: 'Late-Inning Availability',
    definition: 'How much usable late-inning coverage the bullpen currently has.',
  },
  restedOptions: {
    name: 'Rested Options',
    definition:
      'How many current bullpen options enter the represented read without '
      + 'major recent-workload restriction.',
  },
  lateInningPressure: {
    name: 'Late-Inning Pressure',
    definition: 'How much recent workload is narrowing the late-game path.',
  },
  depthSafety: {
    name: 'Depth Safety',
    definition:
      'Whether usable options remain beyond the primary late-inning and '
      + 'bridge layers.',
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
  Object.freeze({ name: 'Available', definition: 'Recent workload leaves the pitcher inside the normal availability range.' }),
  Object.freeze({ name: 'On Watch', definition: 'The pitcher remains usable, but recent workload deserves attention.' }),
  Object.freeze({ name: 'Limited', definition: 'Recent workload materially narrows how fully the pitcher can be used tonight.' }),
  Object.freeze({ name: 'Unavailable', definition: 'Recent workload or current roster status takes the pitcher out of tonight’s bullpen options.' }),
])

// Freshness stamp vocabulary.
//
// H-11: these five names are the ONE reader-facing label for each temporal
// field, and every surface imports them from here rather than spelling its own
// variant. That is what stopped `data_through` from reading as "Data through" /
// "Bullpen data through" / "Published view through" on three surfaces at once,
// and it makes glossary drift impossible by construction: How to Read renders
// the same constants the product renders.
//
// These stay five SEPARATE labels because they are five separate clocks. A
// surface may add scope around a stamp (a heading, a section title); it may not
// rename the field or use one stamp to stand for another.
export const DATA_THROUGH_LABEL = 'Data through'
export const LAST_DATA_UPDATE_LABEL = 'Last data update'
export const LAST_CHECKED_LABEL = 'Last checked'
export const GENERATED_AT_LABEL = 'Generated at'
export const PUBLISHED_AT_LABEL = 'Published at'

export const FRESHNESS_LABEL_DEFINITIONS = Object.freeze([
  Object.freeze({ name: DATA_THROUGH_LABEL, definition: 'The latest completed baseball date represented by the public read.' }),
  Object.freeze({ name: LAST_DATA_UPDATE_LABEL, definition: 'When BaseballOS last successfully wrote new baseball data.' }),
  Object.freeze({ name: LAST_CHECKED_LABEL, definition: 'When BaseballOS most recently attempted or observed a refresh.' }),
])

// Provenance stamps. Separate concepts from the three above: they describe an
// artifact's lifecycle, never the baseball date the read represents.
export const PROVENANCE_LABEL_DEFINITIONS = Object.freeze([
  Object.freeze({ name: GENERATED_AT_LABEL, definition: 'When a historical or distribution artifact was created.' }),
  Object.freeze({ name: PUBLISHED_AT_LABEL, definition: 'When that artifact became the trusted public publication.' }),
])

// Workload Data — the state of ONE pitcher's stored workload record, shown on
// Pitcher Detail and on the Team Board pitcher cards. It is a different
// question from Data Status below: Data Status describes whether the published
// READ is current, this describes how complete and how recent the workload
// record behind a single arm is. The two are named differently so a reader is
// never asked to tell them apart from context. Owned by
// components/bullpen/availabilityView.js, which holds the value catalogue.
export const WORKLOAD_DATA_FAMILY = 'Workload Data'
export const WORKLOAD_DATA_DEFINITIONS = Object.freeze([
  Object.freeze({ name: 'Current', definition: "The arm's latest workload information is inside the active freshness window." }),
  Object.freeze({ name: 'Outside Freshness Window', definition: 'Workload history exists, but the latest appearance is older than the active freshness window.' }),
  Object.freeze({ name: 'No Workload Record', definition: 'No recent workload history is available for this pitcher.' }),
  Object.freeze({ name: 'Incomplete Workload Inputs', definition: 'Some workload inputs are incomplete, so the read should be treated cautiously.' }),
  Object.freeze({ name: 'Fetch Failed', definition: 'The latest workload fetch failed, so the read is unresolved until a refresh succeeds.' }),
  Object.freeze({ name: 'Historical', definition: 'The read is based on an older workload record.' }),
  Object.freeze({ name: 'Unavailable', definition: 'BaseballOS has no usable workload data state for this pitcher.' }),
])

// The data-status family. It describes the state of the published READ, never a
// bullpen or an arm — which is why it borrows no baseball word.
export const DATA_STATUS_DEFINITIONS = Object.freeze([
  Object.freeze({ name: 'Current', definition: "The represented public data is current under the platform's freshness rules." }),
  Object.freeze({ name: 'Partial Data', definition: 'Some current data exists, but the public read carries a material data limitation.' }),
  Object.freeze({ name: 'Stale', definition: 'The represented public data is outside the current freshness window.' }),
  Object.freeze({ name: 'Data Unavailable', definition: 'BaseballOS does not currently have enough usable public data for the status.' }),
])

// Pitcher ROLE — how the arm has been used. Not availability, not quality.
export const PITCHER_ROLE_DEFINITIONS = Object.freeze([
  Object.freeze({ name: 'Trusted Arm', definition: 'Observed usage points to the primary late-inning trust role.' }),
  Object.freeze({ name: 'Setup Arm', definition: 'Observed usage points to the setup or handoff layer.' }),
  Object.freeze({ name: 'Coverage Arm', definition: 'Observed usage points to longer or multi-inning relief coverage.' }),
  Object.freeze({ name: 'Middle Relief Arm', definition: 'Observed usage points to lighter middle-relief work; this is not a talent judgment.' }),
  Object.freeze({ name: 'Role Unclear', definition: 'Observed usage does not support a reliable public bullpen-role classification.' }),
])

// Pitcher CURRENT READ — what tonight looks like for the arm. Distinct from role.
export const PITCHER_CURRENT_READ_DEFINITIONS = Object.freeze([
  Object.freeze({ name: 'Clean Option', definition: 'The pitcher is rested enough to be used freely tonight.' }),
  Object.freeze({ name: 'Watch Arm', definition: 'The pitcher remains usable, but recent workload deserves attention.' }),
  Object.freeze({ name: 'Limited Rest', definition: 'Recent workload leaves materially less rest than a Clean Option.' }),
  Object.freeze({ name: 'Unavailable', definition: 'Recent workload or current roster status takes the pitcher out of tonight’s bullpen options.' }),
  Object.freeze({ name: 'Limited Read', definition: 'BaseballOS does not have enough current evidence for a clear pitcher read.' }),
])

// READ CONFIDENCE — how clear the evidence is. Not a baseball conclusion.
// Re-exported from the value catalogue so the glossary and the product can
// never disagree on this field's name.
export { READ_CONFIDENCE_FIELD_LABEL as READ_CONFIDENCE_FAMILY } from '../components/bullpen/availabilityView'
export const READ_CONFIDENCE_DEFINITIONS = Object.freeze([
  Object.freeze({ name: 'High', definition: 'The evidence behind the read is complete and clear.' }),
  Object.freeze({ name: 'Medium', definition: 'The evidence supports the read with some gaps.' }),
  Object.freeze({ name: 'Low', definition: 'The evidence is thin enough that the read should be treated carefully.' }),
  Object.freeze({ name: 'Unavailable', definition: 'There is not enough evidence to state a confidence level.' }),
])
export const READ_CONFIDENCE_BOUNDARY =
  'Read confidence describes how complete or clear the evidence behind a read '
  + 'is. It is not Team State, not arm availability, not a pitcher role, not a '
  + 'quality grade, not a ranking, and not a prediction.'

// THE LIMITED FAMILY. Four labels share a word and answer four different
// questions; the page states the difference rather than leaving a reader to
// infer it from four separate cards.
export const LIMITED_FAMILY_DISAMBIGUATION = Object.freeze([
  Object.freeze({
    name: 'Limited',
    family: 'Arm Availability',
    definition: 'Recent workload materially narrows how fully the pitcher can be used.',
  }),
  Object.freeze({
    name: 'Limited Rest',
    family: 'Pitcher Current Read',
    definition: 'Recent workload leaves materially less rest than a Clean Option.',
  }),
  Object.freeze({
    name: 'Limited Read',
    family: 'Pitcher Current Read / evidence limitation',
    definition: 'BaseballOS does not have enough current evidence for a clear pitcher read.',
  }),
  Object.freeze({
    name: 'Role Unclear',
    family: 'Pitcher Role',
    definition: 'Observed usage does not support a reliable public bullpen-role classification.',
  }),
])
export const LIMITED_FAMILY_BOUNDARY =
  'These are different dimensions, not degrees of the same thing: one is how '
  + 'much of the arm is usable, one is how rested it is, one is how much '
  + 'evidence there is, and one is what kind of arm it is.'

export const SUPPORTING_READ_BOUNDARY =
  'Supporting reads explain one dimension of a bullpen. They are not Team State.'

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
