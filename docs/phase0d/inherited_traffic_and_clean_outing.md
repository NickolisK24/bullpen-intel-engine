# Phase 0D-04 - Inherited Traffic And Clean/Traffic Outing Context

## Scope

This document defines the internal-only inherited-traffic and clean/traffic
outing evidence family for Phase 0D-04.

The family uses stored final boxscore-backed `game_logs` fields as authority.
It uses the current 0D-03 `appearance_entry_context` evidence object only for
timing corroboration. It does not read raw play-by-play JSON, does not import
play-by-play event models or services, does not reconstruct base state, and
does not publish any public API, payload, UI, or copy behavior.

No migration is expected for this branch. The family writes through the
existing `evidence_objects` and `evidence_citations` tables.

## Registered Rules

All rules are version `v1`, default to `internal_only`, and use
`subject_type=pitcher_appearance` with `subject_id={pitcher_id}:{mlb_game_pk}`.

1. `appearance_inherited_runners v1`
2. `appearance_inherited_runners_scored v1`
3. `appearance_inherited_traffic_outcome v1`
4. `appearance_inherited_entry_corroboration v1`
5. `outing_clean v1`
6. `outing_traffic v1`
7. `outing_context_unknown v1`

No bequeathed-traffic rule is registered.

### RULE 1 - appearance_inherited_runners v1

Definition:
The number of runners already on base when the pitcher entered, as recorded on
his stored final pitching line in `game_logs.inherited_runners`.

Known value:

- state the count, including zero

NULL:

- `UNKNOWN` by design
- never treat NULL as zero
- never infer from entry context
- never infer from play-by-play

This is a boxscore fact. Play-by-play carries no base-runner state and is never
used to derive inherited runners.

### RULE 2 - appearance_inherited_runners_scored v1

Definition:
Of the runners the pitcher inherited, how many scored, from
`game_logs.inherited_runners_scored`.

Emission:

- emit when `inherited_runners` is known and greater than zero
- if `inherited_runners_scored` is known, state k of n
- if `inherited_runners_scored` is NULL with known inherited runners, emit
  `UNKNOWN`

Contradictions:

- `inherited_runners_scored > inherited_runners` -> `CONFLICT`
- `inherited_runners_scored > 0` with `inherited_runners == 0` -> `CONFLICT`

Never correct or guess contradictions.

### RULE 3 - appearance_inherited_traffic_outcome v1

Definition:
The descriptive outcome of inherited traffic for an appearance with:

- `inherited_runners` known and greater than zero
- `inherited_runners_scored` known

Outcome values:

- `stranded_all` when 0 scored
- `allowed_some` when some but not all scored
- `allowed_all` when every inherited runner scored

This describes what happened to inherited runners. It is not a skill, quality,
pressure, or manager-intent judgment.

### RULE 4 - appearance_inherited_entry_corroboration v1

Definition:
The coherence between the boxscore inherited-runner count and the current 0D-03
`appearance_entry_context` evidence object.

Important:
0D-03 entry context corroborates timing only. It never derives runner state.

Corroboration states:

- coherent when a mid-inning entry accompanies any known inherited count,
  including zero
- coherent when a half-inning-start entry accompanies zero inherited runners
- coherent_extras_exception when a half-inning-start entry in an extra inning,
  10th or later, accompanies positive inherited runners
- `CONFLICT` when a half-inning-start entry in regulation accompanies positive
  inherited runners
- `UNKNOWN` when entry context is missing, unknown, duplicated-current, or
  itself in conflict

Extras exception limitation:
A half-inning-start entry in extras with a recorded inherited runner can reflect
the automatic placed runner. Treat it as `coherent_extras_exception` with an
automatic-runner limitation, not a contradiction.

Regulation conflict:
A half-inning-start entry in regulation with positive inherited runners is
`CONFLICT` and dead-lettered.

RULES 1-3 still emit their boxscore facts even when RULE 4 conflicts. The
boxscore remains the attribution authority. RULE 4 flags the disagreement; it
does not suppress the boxscore fact.

### RULE 5 - outing_clean v1

Definition:
A relief appearance in which every required component is known and zero.

Emit `outing_clean` only if all are true:

- `games_started == 0`
- `batters_faced` is non-NULL as the post-expansion sentinel
- `hits_allowed == 0` and known
- `walks == 0` and known
- `runs_allowed == 0` and known
- `inherited_runners` is known, any value
- `inherited_runners_scored == 0` and known

A pitcher who strands known inherited traffic can still qualify as clean if
`inherited_runners_scored == 0` and all other required components are known and
zero.

Legacy fabricated-zero guard:
Because `hits_allowed`, `walks`, and `runs_allowed` may carry legacy default
zeroes from pre-unknown-safe ingestion, `batters_faced` non-NULL is required
before a clean claim can emit. A sentinel-NULL row can never prove cleanliness.

If any required component is NULL or not safely known:

- do not emit `outing_clean`
- emit `outing_context_unknown` instead, with named reason

Limitation required on every clean object:
`Hit-by-pitch and reach-on-error are not stored and are outside this definition.`

Do not render clean as:

- perfect
- spotless
- no baserunners
- dominant
- shutdown

### RULE 6 - outing_traffic v1

Definition:
A relief appearance with three or more baserunners allowed by the pitcher,
counted as:

`hits_allowed + walks >= 3`

Threshold:

- `min_baserunners_allowed: 3`

The rendered claim must state:

- total baserunners by this definition
- hits
- walks
- outs recorded

Example style:
`Traffic outing: allowed 4 baserunners (3 hits, 1 walk) across 2 outs recorded,
at or above the registered 3-baserunner threshold.`

This is a descriptive appearance-level tag only. It asserts nothing about
pressure, fatigue, stuff, quality, readiness, trust, or availability.

Legacy caveat:
On rows where `batters_faced` is NULL, legacy missing values may be
indistinguishable from zero. Traffic can under-fire but cannot over-fire on
such rows. If a traffic flag emits from a sentinel-NULL row, include the legacy
under-fire caveat limitation.

Clean and traffic are mutually exclusive by construction.

### RULE 7 - outing_context_unknown v1

Allowed completeness:

`('unknown',)`

Definition:
An explicit record that an appearance's outing context cannot be assessed
because one or more required components are unknown.

Emit when:

- `inherited_runners` is NULL
- `inherited_runners_scored` is NULL where required
- `batters_faced` sentinel is NULL for a possible clean assessment
- `games_started` is NULL
- clean cannot be safely assessed due to unknown components

Reason must name the unknown component or components.

The absence of clean or traffic is never itself a claim.

## Authoritative Fields

| Area | Authoritative fields | Not used |
| --- | --- | --- |
| Inherited traffic | `game_logs.inherited_runners`, `game_logs.inherited_runners_scored` | raw play-by-play JSON, play-by-play event rows, base-state reconstruction |
| Clean/traffic | `game_logs.hits_allowed`, `game_logs.walks`, `game_logs.runs_allowed`, `game_logs.innings_pitched_outs`, `game_logs.batters_faced`, `game_logs.games_started` | hit-by-pitch, reach-on-error, pitch-level data, Statcast data |
| Corroboration | current non-superseded 0D-03 `appearance_entry_context` evidence object | raw play-by-play events, scoring-sequence reconstruction |

RULE 4 cites the 0D-03 evidence object with `source_table=evidence_objects` and
`citation_role=corroborating_evidence`.

## Clean Truth Table

| Condition | `outing_clean` | `outing_context_unknown` |
| --- | --- | --- |
| Relief row, `batters_faced` present, H=0, BB=0, R=0, IR known, IRS=0 | emit complete | no |
| Same row with IR > 0 and IRS=0 | emit complete | no |
| IRS > 0 | no | no unless another required component is unknown |
| `batters_faced` NULL with otherwise zero fields | no | `legacy_row_pre_expansion` |
| any required clean component NULL | no | named unknown reason |
| `games_started` NULL | no | `appearance_role_unknown` |
| `games_started == 1` | no | no 0D-04 object |

## Traffic Truth Table

| Hits + walks by this definition | `outing_traffic` |
| --- | --- |
| 0 | no |
| 1 | no |
| 2 | no |
| 3 | emit complete |
| greater than 3 | emit complete |

Traffic claims state hits, walks, total counted baserunners, outs recorded, and
the registered threshold. If `batters_faced` is NULL and traffic emits, the
legacy under-fire caveat is carried as a limitation.

## Inherited Runner Matrix

| `inherited_runners` | `inherited_runners_scored` | RULE 1 | RULE 2 | RULE 3 |
| --- | --- | --- | --- | --- |
| NULL | any | `UNKNOWN` | no | no |
| 0 | 0 | complete count | no | no |
| 0 | greater than 0 | complete count | `CONFLICT` | no |
| n > 0 | NULL | complete count | `UNKNOWN` | no |
| n > 0 | 0 | complete count | complete k of n | `stranded_all` |
| n > 0 | 0 < k < n | complete count | complete k of n | `allowed_some` |
| n > 0 | k == n | complete count | complete k of n | `allowed_all` |
| n > 0 | k > n | complete count | `CONFLICT` | no |

Contradictions dead-letter with `entity_type=inherited_traffic_contradiction`.

## Corroboration Matrix

| 0D-03 entry context | IR state | RULE 4 result |
| --- | --- | --- |
| missing current object | IR known | `UNKNOWN`, `entry_context_unavailable` |
| multiple current objects | IR known | `UNKNOWN`, `entry_context_incoherent`, dead-letter |
| entry object `UNKNOWN` or `WITHHELD` | IR known | `UNKNOWN`, `entry_context_unavailable` |
| entry object `CONFLICT` | IR known | `UNKNOWN`, `entry_context_incoherent` |
| complete mid-inning entry | IR known, including zero | coherent |
| complete half-inning-start entry, inning 1-9 | IR == 0 | coherent |
| complete half-inning-start entry, inning 1-9 | IR > 0 | `CONFLICT`, `inherited_exceeds_context`, dead-letter |
| complete half-inning-start entry, inning >= 10 | IR > 0 | `coherent_extras_exception`, `extras_automatic_runner` |
| any entry context | IR NULL | no RULE 4 object |

RULE 4 reads only the current, non-superseded 0D-03
`appearance_entry_context` object for the same `subject_type`, `subject_id`,
`product_date`, and evidence type. It does not choose silently when duplicate
current objects exist.

## Reason Codes

- `inherited_fields_unknown`
- `inherited_scored_unknown`
- `outing_component_unknown`
- `legacy_row_pre_expansion`
- `appearance_role_unknown`
- `entry_context_unavailable`
- `entry_context_incoherent`
- `inherited_exceeds_context`
- `extras_automatic_runner`

## Citations Required

Every object cites its `game_logs` row with the exact fields used, selected from:

- `inherited_runners`
- `inherited_runners_scored`
- `hits_allowed`
- `walks`
- `runs_allowed`
- `innings_pitched_outs`
- `batters_faced`
- `games_started`

RULE 4 additionally cites the current 0D-03 `appearance_entry_context` evidence
object when one current object exists:

- `source_family=final_play_by_play`
- `source_table=evidence_objects`
- `citation_role=corroborating_evidence`

No object emits without a game-log citation.

## Computation Trace

Trace payloads must be enough for a reviewer to replay the derivation. They
record:

- field reads
- known and NULL checks
- threshold comparisons
- inherited contradiction checks
- clean component checks
- traffic threshold math
- mutual-exclusion checks
- RULE 4 entry-context lookup and values consulted
- reason for unknown or conflict states

## Limitations

Clean and traffic objects carry:

`Hit-by-pitch and reach-on-error are not stored and are outside this definition.`

Traffic objects from sentinel-NULL rows carry:

`Legacy row caveat: this row predates the post-expansion sentinel, so missing
hit/walk values may appear as zero; this traffic flag can under-fire but not
over-fire.`

Extras exception corroboration carries:

`Extra-inning automatic runner may explain a half-inning-start entry with
inherited traffic; BaseballOS records this as a timing-coherence exception, not
PBP-derived base state.`

Suspended/resumed games carry the resumed-game limitation where applicable,
consistent with 0D-03.

## Bequeathed-Traffic Deferral

This branch does not implement bequeathed traffic.

Bequeathed traffic is deferred because the available derivation would join a
predecessor appearance to a successor's `inherited_runners` through 0D-03
succession. That would turn corroboration into derivation-by-join and is
polluted by:

- extra-innings automatic runner
- multi-change innings
- successor NULL inherited fields

The decision is deferred to 0D-09 alongside the base-state addendum decision.

## Explicit Non-Claims

This family makes no claims about:

- inherited-runner reconstruction from play-by-play
- per-inning clean/traffic granularity
- bequeathed-traffic implementation
- pressure or leverage
- role usage observations
- manager intent
- availability, fatigue, readiness, or health conclusions
- quality judgments
- public payload, API, UI, or copy changes
- score, rank, or grade
- prediction
- pitch-level or Statcast data

## Sync And Recompute

The existing fail-soft Phase 0D evidence stage builds this family after the
0D-03 appearance context family when `PHASE0D_EVIDENCE_BUILD` is enabled.
Exceptions are dead-lettered and logged while sync continues.

Corrections to cited `game_logs` rows mark dependent 0D-04 evidence with
`mark_dependent_evidence_for_recompute`. Supersession of a cited 0D-03
`appearance_entry_context` evidence object marks RULE 4 dependents. Rebuilds
refresh only marked evidence keys and preserve prior rendered-claim provenance
in the computation trace.
