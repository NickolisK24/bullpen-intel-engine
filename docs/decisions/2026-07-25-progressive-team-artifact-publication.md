# Decision: Progressive Team State Publication vs Slate-Scoped League Snapshot

- **Date:** 2026-07-25
- **Status:** Approved (founder decision) and implemented
- **Scope:** Team State Share Artifact publication path. NOT an SC-02 change; no public
  vocabulary, threshold, coverage, or league-snapshot trust-gate change.

## Context

Team State artifact generation fired only from the league dashboard snapshot's
post-publication hook, and the league snapshot withholds until the ENTIRE required
slate is final. So one late game between two other teams blocked Team State artifacts
for every team whose game had already ended (production run 469 / snapshot 272: the
league snapshot correctly stayed pending with 13 of 15 games not final, so no team got
an artifact).

## Decision

BaseballOS uses two distinct publication authorities:

1. A league-wide BaseballOS snapshot remains **synchronized and slate-scoped**
   (all-or-nothing). Every existing league trust gate is preserved. Snapshot 272 is
   not mutated.
2. An individual Team State Share Artifact may publish **progressively** after that
   team's own completed game and required evidence pass the canonical trust gates. An
   unrelated non-final game must not block it.

The team-scoped trusted source is a new immutable `team_progressive_publications`
checkpoint (migration `b3d9f1a7c2e5`) whose id supplies the artifact's non-null
`source_snapshot_id`. Its trust verdict is fail-closed and computed from that team's
own final-game evidence (game final + committed box score/appearance ledger + both
teams resolved), never from the league slate. A completed game evaluates its two teams
INDEPENDENTLY through the exact existing single-team path — no second readiness or
eligibility engine, no SC-02 change. One team may publish while its opponent refuses.

Fail-closed: no snapshot/checkpoint, unpublished/non-serving/untrusted source, missing
box score or appearance ledger, stale team `data_through`, insufficient team coverage,
low confidence, `data_limited`, unresolved provenance, or failed integrity all
withhold. Idempotency + corrections ride the existing `equivalence_key` (which includes
`source_snapshot_id`): the same evidence reuses; a corrected `evidence_revision` mints a
new immutable checkpoint and a new immutable artifact without rewriting the prior one.

## Chosen representation

Founder-selected: a **minimal immutable checkpoint table** (rather than overloading a
league snapshot id). It gives clean, queryable, durable provenance for a trust-critical
immutable publication. The migration is additive and independently reversible; existing
league snapshots and artifacts stay valid; `dashboard_snapshots` and its gates are
unchanged.

### Durable source-authority discriminator on the artifact

The checkpoint table supplies the artifact's non-null `source_snapshot_id`, but that
column is a bare integer that shares one integer space with `dashboard_snapshots.id` —
the two can collide. The trusted-source TYPE is therefore recorded DURABLY on the
artifact itself, in the immutable `subject_type` field (already part of the equivalence
+ integrity contract): a progressive artifact stamps `subject_type='team_progressive'`
plus a self-describing `subject_key`; a league artifact leaves `subject_type` NULL.
`source_snapshot_id` is never used alone to determine source type, and an audit row is
never the artifact's source identity. `source_authority_type` classifies an artifact
from this durable field. Because it reuses an existing immutable identity field, the
discriminator needs no additional migration and does not change any existing league or
legacy artifact's identity. The checkpoint additionally gains a DB unique constraint on
`(team_id, trigger_game_pk, evidence_revision)` so idempotency is enforced under a
concurrent race, and `evidence_revision` is a sorted, correction-sensitive digest of
the committed appearance ledger (row-order independent).

## Consequences

- A team receives a current Team State artifact after its own game, regardless of a
  later unrelated game — the SC-04B production blocker is removed.
- The league snapshot still waits for its full slate; the morning league run remains
  the reconciliation backstop; progressive artifacts are never deleted or duplicated
  unnecessarily.
- The postgame trigger reuses the existing scheduled postgame reconciliation, is gated
  by `SHARE_ARTIFACT_AUTOGENERATION_ENABLED`, and is fully fail-soft.

## References

- `docs/current/PROGRESSIVE_TEAM_ARTIFACT_PUBLICATION.md`
- `models/team_progressive_publication.py`,
  `migrations/versions/b3d9f1a7c2e5_add_team_progressive_publications.py`,
  `services/team_progressive_publication.py`,
  `services/team_state_source.py` (`gather_team_state_source` source_authority),
  `services/share_artifact_generation.py` (`generate_team_state_artifact` source_authority),
  `services/readiness_snapshot_freshness.py` (team-scoped freshness verdict),
  `services/sync.py` (`_safe_run_progressive_team_publication` postgame trigger)
- Tests: `tests/test_team_progressive_publication.py`
