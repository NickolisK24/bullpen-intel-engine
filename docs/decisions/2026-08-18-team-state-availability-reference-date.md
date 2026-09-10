# D-056 — Team State availability reference date

- **Date:** 2026-08-18
- **Status:** Corrected in repository; awaiting corrected natural production publication
- **Scope:** The reference date the published Team State path classifies bullpen availability at, and the matching card read. No Contract A threshold, classifier, vocabulary, partition, artifact schema, roster-authority, or publication-authority change.

## Context

Team State vNext (`v3_phase_5`) published for the first time on a natural scheduled
run: workflow run 32126672100, sync run 774, dashboard snapshot 437, data through
2026-08-17, published 2026-08-18T10:30:09.693370Z. All 30 teams published. The
observed distribution was 0 Fresh / 13 Stretched / 17 Vulnerable.

A reader-visible contradiction surfaced on that publication: a team board showing
six clean arms and two limited arms alongside a published Team State of Stretched.
Under Contract A a 6 / 2 / 0 / 0 partition of eight active arms is Fresh
(`clean_share` 3/4, `clean_count` 6, `severe_count` 0) — and the strictly weaker
6 / 4 / 0 / 0 profile was already pinned Fresh by two passing fixtures. The
classifier was not wrong. Its inputs were.

`services.availability_reference_date.product_availability_reference_date` is the
canonical owner of the semantic: *a data set through June 7 describes the next
availability read on June 8*. Three surfaces honour it — the Team Board
(`api/bullpen.py::_public_availability_reference_date`,
`services/public_serving_authority.py::_candidate_reference_date`), the readiness
route (`api/team_operations.py::get_team_operations_bullpen_readiness`), and the
calibration shadow (`scripts/compare_team_state_populations.py`), whose locked
fixtures record real teams at six, seven, and nine clean arms.

`services/share_artifact_generation.py::resolve_team_readiness_payload` did not. It
resolved the canonical date into a local, then overwrote that same local with the
slate day (`data_through`) while anchoring the roster authority — a correct and
necessary repair for the run-471 progressive refusal and the run-476 all-30-team
league refusal — and passed the overwritten value on to
`classify_latest_fatigue_rows`. One variable was answering two questions.

The published artifact therefore classified arms a day early, while
`anchor_sync_status_to_serving_snapshot` stamped its freshness metadata with
`data_through + 1`. One immutable artifact stated one date and classified at
another. At the slate day an arm that pitched on `data_through - 1` still carries
`days_rest = 1` and still has its pitch count counted as "yesterday"; at the
canonical date that arm is normally Available. A second full game of used arms was
held out of the clean bucket league-wide.

## Decision

The two reference dates are separate governed values and are never collapsed:

- `membership_reference_date` = the trusted source's `data_through`. The roster
  authority only resolves for the date its roster snapshot covers. This is the
  run-476 repair and it is preserved exactly, including for the trust classifier.
- `availability_reference_date` = the canonical next-day availability reference,
  resolved by `services.availability_reference_date.trusted_slate_reference_dates`,
  which delegates to the existing `product_availability_reference_date` owner. No
  literal date arithmetic is introduced at the call sites.

`resolve_readiness_reference_dates` is the single authority that decides the pair
for one read, for both trusted sources (league serving snapshot and team-progressive
checkpoint). With no trusted source, both values remain the live global reference
date the unanchored read already used — prior behavior is unchanged.

`build_team_state_card_metrics` takes the same split: membership and the
three-team-game workload window stay on the slate; the classified availability
behind every reader-facing row label, and the rest days published beside it, move to
the availability reference date. The card and the authoritative verdict read one
bullpen on one date. Determinism is unchanged — both dates derive from the same
governed slate.

Production-proof instrumentation is added as an env-gated side-channel artifact
carrying, per team, the two reference dates actually used, and a
`reference_date_alignment` invariant that fails the proof if they ever diverge from
the governed pair again.

## What is explicitly unchanged

- **Contract A is untouched.** Thresholds (`clean_share_fresh_min` 3/5,
  `clean_count_fresh_min` 5, `severe_count_fresh_max` 1,
  `clean_count_vulnerable_max` 2, `severe_share_vulnerable_min` 1/3), precedence,
  the clean/moderate/severe/unknown map, `v3_phase_5` semantics, and the
  Fresh/Stretched/Vulnerable definitions are all as shipped. The freeze test pinning
  the classifier equal to the calibration contract is unmodified and green.
- **No recalibration.** The calibration shadow was run at the canonical availability
  date; recalibrating against a defective read would have baked the defect into the
  contract.
- **Historical publications remain immutable.** Snapshot 437 and its 30 artifacts
  are not rewritten, regenerated, superseded, or backfilled, and the generated
  preview pages it published stay as committed. It remains on the record as the
  affected first natural vNext publication. Correction is by forward publication.
- **No database migration and no Share Artifact schema or version change.**
  `TEAM_STATE_LATEST` stays `1.2.0`; the immutable document gains no field.
- **No frontend change.** The board, the readiness route, and the shadow were
  already correct; the frontend derives no Team State and is not implicated.
- **What Changed is untouched.** Both frozen modules are read, never modified, and
  no Team State change type is introduced.

## Frozen-surface exception

Three protected paths change, and one protected-prefix file is added:

| Path | Guard | Catalogue |
| --- | --- | --- |
| `backend/services/share_artifact_generation.py` | `test_appearance_team_authority.py::test_branch_touches_no_team_state_or_public_surface_files` | `SHARE_ARTIFACT_SERVICE_PREFIX` |
| `backend/services/team_state_card_metrics.py` | same | `TEAM_STATE_PATH_PREFIX` |
| `backend/services/team_state_vnext_production_proof.py` (new) | same | `TEAM_STATE_PATH_PREFIX` |
| `backend/services/dashboard_snapshot.py` | `test_qa_reconciliation_scenarios.py::test_phase0e_switches_and_legacy_public_files_not_modified` | `FROZEN_PHASE0E_LEGACY_PUBLIC_PATHS` |

The exception is `D056_TEAM_STATE_REFERENCE_DATE_PATHS` in
`backend/tests/freeze_policy.py`. It is exact-path and decision-linked. It grants no
directory exemption, no Contract A change, no vocabulary change, no publication-gate
change, and no permission for unrelated future edits. What the guards actually
protect is proved directly and on every run by
`test_team_state_vnext_contract_a.py` (thresholds, precedence, partition, method
version) and `test_team_state_reference_date_split.py` (both dates, metadata
agreement, roster authority preserved), which are stronger statements than a diff
check can make. As with the reviewed exceptions above it, these entries go inert
once the branch merges.

`backend/services/dashboard_snapshot.py` changes only to add the env-gated
post-publication proof capture, after the publication has already committed. The
capture cannot roll back, unpublish, or alter a publication, and with the
environment variable unset it does nothing at all.

## Consequences

- The next natural scheduled publication will move many teams' Team State. That
  movement is the correction landing, not a new defect. It will not surface as a
  public change, because What Changed structurally does not read Team State.
- Team State vNext is **not** production-proven by this branch. Only a corrected
  natural scheduled publication, with its proof artifact showing reference-date
  alignment for all 30 teams alongside the original proof requirements, can close it.
- The distribution is now reported with a `distribution_degenerate` diagnostic. A
  league-wide zero-Fresh result is surfaced for human review rather than tallied
  silently; it is not treated as a classifier failure and no baseball threshold is
  invented around it.
