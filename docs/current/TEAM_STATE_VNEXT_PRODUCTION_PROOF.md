# Team State vNext Production Proof — Runbook

## Purpose

Capture, from one natural scheduled publication, the evidence needed to decide
whether Team State vNext (`v3_phase_5`) can be marked production-proven.

The immutable Team State Share Artifact deliberately carries no
`team_state_evidence`, no `contract_version`, and no partition — that is the right
shape for a published document and the wrong shape for proving what the runtime
did. The evidence vector exists for the length of one generation call and is then
gone. Diagnosing the first natural publication (snapshot 437) required reading a
committed HTML preview page, because nothing else survived.

This mechanism observes the exact runtime objects of one publication and writes
them to a JSON file. It changes no artifact, no schema, and no publication
behavior.

## What it is not

- Not a second Team State computation. Nothing is re-derived from later pitcher
  rows, and no state is recalculated after publication.
- Not publication-critical. A proof assertion cannot fail the publication.
- Not on by default. With `TEAM_STATE_VNEXT_PROOF_PATH` unset — every process
  except one workflow step — the capture returns immediately and the unchanged
  generation call runs exactly as before.

## Capture seam

`services.dashboard_snapshot._maybe_generate_team_state_artifacts_after_publication`
→ `services.team_state_vnext_production_proof.capture_publication_proof`.

This is the one place holding both the already-committed published snapshot (its
id, sync-run id, `data_through`, `published_at`, and frozen
`what_changed_since_yesterday`) and the call into batch generation. The collector
installs through the `generator` seam
`share_artifact_publication_hook.run_post_publication_generation` already exposes,
so the batch service, the single-team service, and the classifier are unchanged
and unaware.

Because it runs after the publication transaction has committed, it structurally
cannot roll back, unpublish, or alter a publication. It never raises.

## Artifact

`artifacts/team-state-vnext-proof/team-state-vnext-production-proof.json`, written
by `utils.summary_output.write_summary` (atomic, sorted keys, deterministic).

Per team: team id, outcome, public id, snapshot/sync-run identity, published public
Team State, internal status code, `contract_version`,
`team_state_evidence.method_version`, active pitcher count, the full
clean/moderate/severe/unknown partition, the evaluated partition invariant, the
decisive rule and its inputs, the thresholds applied, the complete
`team_state_evidence` vector verbatim, and both reference dates.

League level: publication identity, batch outcomes, the Fresh/Stretched/Vulnerable
distribution read from the published artifacts, the historical inventory digests,
the What Changed scan, eight invariant verdicts, and one overall verdict.

## Invariants

| Invariant | Proves |
| --- | --- |
| `all_teams_published` | 30 teams, exactly once, no duplicates, none missing |
| `method_version_observed` | every team stamped `v3_phase_5` **and** its state re-derived from the recorded partition through the recorded thresholds |
| `partition_integrity` | `clean + moderate + severe + unknown == active_pitcher_count` |
| `team_state_evidence_complete` | every required evidence key present |
| `reference_date_alignment` | membership == `data_through`, availability == the canonical next-day reference (D-056) |
| `distribution_consistent` | each published public state matches its internal status code |
| `no_historical_rewrite` | prior published Team State artifacts unchanged across the publication |
| `no_false_cross_version_change` | no Team State change type or vocabulary in the published change payload |

`reference_date_alignment` exists because the first natural publication would have
passed the other seven while classifying the whole league a day early. A test
replays that exact condition and shows the other seven still passing.

Verdicts are `PASS`, `PASS_WITH_INCONCLUSIVE`, or `FAIL`. Any `FAIL` forces `FAIL`.
A missing or unrecognized invariant is an invalid artifact, never an implicit pass.

## Things the proof refuses to say quietly

- A refused team records a null partition by design. It is `not_applicable`, never
  `false`, and never counted as a pass.
- A publication that is not a method-version boundary reports
  `applicable: false` and resolves `INCONCLUSIVE`. The `v3_phase_4 → v3_phase_5`
  transition happened once, at snapshot 437; a later publication is
  `v3_phase_5 → v3_phase_5`. Snapshot 437's frozen What Changed block is carried
  read-only as `boundary_reference` instead. No prior publication's method version
  is persisted anywhere, and the artifact says so rather than guessing.
- A league in which no team is Fresh is flagged `distribution_degenerate` and
  downgrades the verdict for human review. It is not treated as a classifier
  failure, and no baseball threshold is invented around it.

## Historical immutability

Two bounded `SELECT`s of `(id, public_id, integrity_hash, lifecycle_state,
superseded_at)` over prior published Team State artifacts, taken immediately before
and after generation, digested with the repository's own canonicalizer and
compared. The stored `integrity_hash` is read, never recomputed — recomputing a
season of artifacts would not fit the daily final-phase budget. Today's own
artifacts are excluded: they are supposed to be new.

Scope is stated on the artifact: `window_scope` is
`daily_league_publication_hook`. The postgame progressive lane publishes on its own
schedule and is outside this window by design.

## Workflow

`baseballos-sync.yml`:

- **Emission** — `TEAM_STATE_VNEXT_PROOF_PATH` is set on the “Run direct daily
  sync” step only, never at job scope. It deliberately does not live under
  `artifacts/game-driven-shadow/`, which the shadow handoff step sweeps wholesale.
- **Preservation** — scanned by the shared forbidden-content scanner, then uploaded
  on `always()` with 30-day retention. Evidence when an assertion fails is the
  entire point.
- **Validation** — a dedicated `team-state-vnext-proof` observer job, modelled on
  `shadow-activation-health`, holding no production credential and running no
  production command. It downloads the artifact and runs
  `backend/scripts/validate_team_state_vnext_proof.py` (exit 0 valid and not FAIL,
  1 valid and FAIL, 3 the artifact itself is invalid).

The observer fails only itself. `internal-enrichment` and
`static-team-story-preview` gate on `public-sync` succeeding, so failing the
publication job on a proof assertion would suppress the static delivery for a run
whose sync, snapshot publication, appearance-ledger proof, and dashboard
verification all succeeded — and the publication has already committed by the time
the proof is written, so failing it protects nothing.

## Reading a run

1. Open the `team-state-vnext-proof-<run_id>` artifact and the observer job's step
   summary.
2. Check `overall_verdict`, then `failed_assertions` and `inconclusive_assertions`.
3. Check `distribution.distribution_degenerate`. If true, a human decides whether
   the league is genuinely that constrained before anything is called proven.
4. Record the run id, sync-run id, snapshot id, artifact name, and verdict in the
   Decision Ledger version history.

## Closeout condition

Team State vNext is **not** production-proven by the presence of this mechanism.
Only a corrected natural scheduled publication whose proof artifact shows
reference-date alignment across all 30 teams, alongside the original gate
requirements, can close it. See
[`../decisions/2026-08-18-team-state-availability-reference-date.md`](../decisions/2026-08-18-team-state-availability-reference-date.md).
