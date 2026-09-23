# Trusted publication proof lifecycle

## Purpose

Trusted Dashboard publication has one proof lifecycle. Publication admission is
decided before commit; post-commit observation verifies the immutable state that
was actually committed. Observation never recalculates Team State from current
roster, GameLog, or readiness rows.

## Execution map

| Stage | Process and entry point | Data access | Snapshot / Team State source | Credentials | Criticality |
|---|---|---|---|---|---|
| Public sync | `public-sync` -> `backend/scripts/run_daily_sync.py` -> `services.sync.run_daily_sync` | Production acquisition and publication reads/writes | Candidate selected by the governed daily coordinator | Production DB, secret key, admin/write credentials | Publication-critical |
| Pre-commit proof | `services.dashboard_snapshot.publish_dashboard_snapshot` -> `require_transactional_publication_proof` | Candidate payload, canonical club directory, governed readiness inputs; writes durable proof in the publication transaction | Candidate snapshot ID and 30 receipts frozen into `trusted_team_boards` | Same publication transaction | Publication-critical; failure rolls back |
| Commit | `publish_dashboard_snapshot` transaction commit | Writes ready snapshot/current pointer, proof row, frozen package | Exact admitted candidate | Same publication transaction | Publication-critical |
| Immediate observation | `run_post_commit_snapshot_publication` -> `observe_committed_publication_proof` | Read-only durable proof plus committed snapshot payload | Frozen receipt maps only | Existing publisher DB context | Adoption-critical; cannot undo an already committed publication |
| Optional artifact generation | `run_post_commit_snapshot_publication` -> `run_post_publication_generation` | Frozen proof inputs and frozen snapshot receipt | Frozen input captured before commit | Existing publisher DB context | Distribution consumer; not Team State proof authority |
| Proof export | `export_team_state_publication_proof.py` | Read-only current/explicit snapshot and durable proof row | Frozen proof plus committed receipts | `APP_ENV`, `DATABASE_URL` only | Adoption-critical for recovery evidence |
| Artifact scan/upload | `public-sync` workflow steps | Proof JSON and observation JSON on runner filesystem | Embedded snapshot identity | No DB or app credential | Adoption evidence retention |
| Validation | `team-state-vnext-proof` -> `validate_team_state_vnext_proof.py` | Downloaded artifact only | Embedded immutable proof and post-commit observation | None | Workflow adoption-critical |
| Static preview | `static-team-story-preview` -> distribution resolver and exporters | Read-only published snapshot/package | Explicit frozen publication identity | `APP_ENV`, `DATABASE_URL` only | Optional distribution/preview consumer |
| Shadow health | `shadow-activation-health` | Uploaded shadow handoff | Shadow cycle identity, never public Team State | No production credential | Observer only |

The current pointer moves only in the commit stage. Proof export, validation,
static preview, and shadow observation cannot move it.

## Equivalence contract

For each of the 30 IDs in `MLB_TEAM_IDS`, pre-commit admission persists the
exact receipt map and its deterministic digest. Post-commit observation compares
that map with `trusted_team_boards.frozen_team_state_by_team_id` for the committed
snapshot. The comparison covers:

- Dashboard snapshot ID;
- team ID and exact canonical team set;
- represented/data-through date;
- Team State method version;
- public Team State value, including eligibility/withholding fields carried by
  the receipt;
- deterministic receipt digest.

New proofs carry the admitted receipt map directly. Receipt-bearing publications
created immediately before this contract, including snapshot 3435, can reconstruct
the expected receipt only from their immutable pre-commit generation inputs. That
compatibility path does not query mutable baseball sources.

## Failure classification for recovery run 35858854297

- `proof_export_environment_invalid`: the proof exporter imported the full
  production API, which correctly required `ADMIN_API_TOKEN` because it exposes
  operational write routes. The exporter itself is read-only and should not have
  inherited that requirement.
- `proof_artifact_missing`: downstream consequence of the export bootstrap
  failure. It was not the root cause.
- Static preview failed independently at its read-only publication-resolution
  step for the same full-API initialization assumption.
- The reported Team State disagreement was not a receipt disagreement. The old
  observer compared failed optional Share Artifact generation results (30 failed
  generations) with the durable proof and labeled the mismatch as Team State.
  The receipt-to-receipt observer finds no semantic disagreement unless immutable
  fields actually differ.
- Shadow activation health was an independent observer failure. It did not affect
  snapshot 3435 admission and remains outside this repair unless caused by the
  shared read-only environment contract.

## Environment contract

| Responsibility | Required | Explicitly not required |
|---|---|---|
| Production API | `APP_ENV=production`, `DATABASE_URL`, strong `SECRET_KEY`, `ADMIN_API_TOKEN` | None; security guard remains mandatory |
| Daily Primary / `recovery_daily` | Production DB plus governed sync/write credentials and API security settings | No reduction in existing privileges |
| Proof export | `APP_ENV=production`, `DATABASE_URL` | `SECRET_KEY`, `ADMIN_API_TOKEN`, sync credentials |
| Proof validation | Proof artifact | Database and all secrets |
| Static preview resolution/export | `APP_ENV=production`, `DATABASE_URL` | `SECRET_KEY`, `ADMIN_API_TOKEN`, sync credentials |
| Shadow observer | Shadow handoff artifact | Production database and write credentials |

Read-only commands use `utils.read_only_app.create_read_only_app`, which registers
no HTTP routes, scheduler, sync service, or operational writes. The normal API
still fails startup without its admin token.

## Public MLB team universe

Every snapshot-bound public team distribution uses the exact canonical Team
Board accounting carried by that trusted snapshot. Stable names and
abbreviations come from `services.mlb_club_directory.MLB_CLUBS`, the same
immutable registry that defines `MLB_TEAM_IDS`.

Mutable player and roster rows are not a public-team denominator. Those sources
legitimately contain affiliates and other organizations, so `team_id IS NOT
NULL`, distinct player organization IDs, and roster-derived team lists must
never drive Team Story, preview, or share distribution. Exact accounting fails
closed on an extra, missing, duplicate, or substituted club. A canonical club
without an active player row remains accounted for; a noncanonical organization
never receives a public team page.

The static Team Story exporter uses snapshot accounting plus `MLB_CLUBS`.
League Share Artifact batch generation uses the same canonical distribution
helper. Share-page preview export iterates already-published immutable artifacts
and therefore performs no organization discovery. Administrative coverage and
team-following reads retain their separate contracts; they are not public page
denominators.

## Artifact lifecycle and statuses

`public-sync` exports `team-state-vnext-production-proof.json` and
`observation.json`, scans the directory, and uploads one deterministic artifact
named with the workflow run ID. The validator downloads and validates the proof.
When proof JSON is absent it reads the observation marker and reports the upstream
status rather than replacing it with a generic message.

Statuses are `publication_not_observed`, `export_failed`, `proof_disagreed`, and
`proof_valid`. Reason codes distinguish invalid export environment, export
failure, missing artifact/proof, snapshot mismatch, Team State disagreement,
team-count mismatch, noncanonical team, and missing receipt.

## Boundary audit

- **Safe:** exact-30 checks in Team State admission validate the canonical
  `MLB_TEAM_IDS` set and do not treat arbitrary non-null team IDs as MLB clubs.
- **Safe:** new post-commit proof and artifact generation use frozen receipts or
  frozen generation inputs; neither independently selects a team universe.
- **Fixed blocker:** static Team Story export derives its exact 30-team universe
  from the selected snapshot's canonical accounting and uses `MLB_CLUBS` only
  for stable display identity. Active `Pitcher.team_id` rows cannot expand or
  substitute the distribution denominator.
- **Fixed blocker:** proof export and current static/generated distribution
  readers no longer import the full write-capable API.
- **Fixed blocker:** optional artifact-generation failure can no longer masquerade
  as Team State semantic disagreement.
- **Safe:** downstream validation now distinguishes no publication, export
  failure, missing proof, identity mismatch, and semantic disagreement.
- **Real defect, deferred:** other one-off audits/backfills still import the full
  app. They either perform writes or are outside this publication/recovery path;
  each must be reviewed before independently removing credentials.
- **Real defect, deferred:** shadow activation health in run 35858854297 remains
  an observer-specific failure and does not establish a public publication defect.
- **Dead code:** the previous collector-based post-commit comparison is retained
  only for older proof helpers; it is no longer publication observation authority.

No migration, sync-pipeline expansion, or atomic publication authority change is
part of this repair.
