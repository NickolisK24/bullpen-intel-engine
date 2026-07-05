# Phase 0D - Evidence Contract And Language Rules

## Charter

Phase 0D turns the Phase 0C source foundation into internal evidence objects.
It does not publish new product surfaces. The phase exists to define how
BaseballOS can interpret stored facts without guessing, overstating source
certainty, or hiding limitations.

All Phase 0D output remains `internal_only` during Phase 0D unless a later
approved branch explicitly changes posture for a registered evidence family.

## Phase 0D Branch Map

- 0D-01: evidence contract and language rules. Complete.
- 0D-02: workload and recovery evidence. Complete.
- 0D-03: entry and exit appearance context. Complete.
- 0D-04: inherited traffic and clean/traffic outing context. Complete.
- 0D-05: starter exposure and calendar density evidence. Active/completed in
  this branch.
- 0D-06: roster, IL, and transaction context.
- 0D-07: pressure proxy feasibility and limits.
- 0D-08: role usage observations and team bullpen structure reads.
- 0D-09: integration, public-candidate review, and Phase 0D exit.

The branch map is sequencing only. Branch 0D-01 implements no production
evidence family. Branch 0D-02 adds the first production evidence family as
internal-only workload and recovery facts. Branch 0D-03 adds internal-only
appearance entry and exit context facts from stored final play-by-play and
game-log rows. Branch 0D-04 adds internal-only boxscore-authoritative
inherited-runner, clean outing, and traffic outing facts with 0D-03 entry
context used only for timing corroboration. Branch 0D-05 adds internal-only
team-level starter-exposure and calendar-density facts from stored
team-game pitching split rows.

## Binding Interpretation Rules

- Finality first.
- Live or in-progress data is never public evidence.
- Unknown stays unknown.
- Nullable arithmetic fails closed.
- Roster snapshots are current-state authority.
- Transactions explain context but do not decide current roster state.
- Absence of an IL or injury flag is not proof of health.
- No free-text injury descriptions.
- No raw PBP JSON.
- No raw transaction JSON.
- No pitch-level or Statcast interpretation.
- No betting, odds, or projection framing.
- No manager-intent certainty.
- No public fatigue, confidence, trust, or pressure scores.
- No unsupported health claims.
- No black-box scoring.
- All 0D output remains internal-only during Phase 0D.

## Evidence Chassis

The generic evidence chassis stores:

- evidence type
- subject type and subject identity
- product date
- claim template id
- rendered claim
- rule id and rule version
- typed cited inputs that resolve to stored provenance-carrying rows
- serializable human-readable computation trace
- completeness state
- reason codes
- limitations
- posture
- source provenance
- correction and recompute metadata

The chassis intentionally has no generic score, rank, grade, or color-state
field. Typed values, counts, and labels can appear only through registered
rules.

## Rule Registry

Every evidence rule must be registered before it can emit evidence. A rule
requires:

- `rule_id`
- `rule_version`
- `evidence_type`
- plain-language definition
- required source-readiness families
- required cited fields
- allowed completeness states
- default posture
- threshold values only when the values appear in the plain-language definition

Rules without plain-language definitions fail registration. Unregistered rules
cannot emit evidence.

## Completeness States

- `complete`: required inputs are ready, cited, non-null, and non-conflicting.
- `partial`: reserved for later registered rules that explicitly allow partial
  evidence and define the limitation.
- `unknown`: required cited input is unavailable or null.
- `conflict`: cited inputs contradict each other and both sides remain cited.
- `withheld`: source posture, readiness, or rule constraints prevent a claim.

## Posture States

- `internal_only`: default for every 0D object.
- `public_candidate`: allowed only for later explicitly registered rules.

No 0D-01 rule uses `public_candidate`.

## Reason Codes

Reason codes explain non-complete states. Current chassis codes include:

- `source_posture_uncleared`
- `source_family_unready:<family>`
- `required_input_unknown:<family.field>`
- `contradictory_inputs`
- `completeness_not_allowed_by_rule`

Later evidence families may add rule-specific reason codes only when documented
in their rule definitions and tests.

## Citation Format

Each citation records:

- source family
- source table
- source row identity
- cited field names
- citation role
- cited values
- source provenance, including source and sync run where available

Claims cannot render without citations.

## Trace Format

The computation trace is serializable JSON with:

- rule id
- rule version
- ordered human-readable steps
- notes or limitations used during the build

The trace explains how the object was built. It is not a public claim.

## Language Lint

Claim templates and rendered claims are linted before evidence can be emitted.
See `docs/phase0d/language_rules.md` for safe and forbidden language.

## Correction And Recompute

Evidence objects and citations are registered with the correction-policy
framework. Upstream source corrections can mark dependent evidence rows
`recompute_needed` in bounded batches, preserving provenance and the rule
version that produced the original object.

Rule version changes are visible on each evidence row. They must not silently
rewrite history.
