# D-054 — Governed league Team State listing

- **Date:** 2026-08-15
- **Status:** Adopted
- **Scope:** Read-only public listing of already-published Team State artifacts for the authoritative 30 active MLB clubs. No Team State computation, ranking, prediction, selection, acquisition, or publication authority changes.

## Context

The final league Dashboard needs a complete club denominator without turning the
frontend into a second Team State authority. Existing public serving already reads
immutable Team State Share Artifacts from one trusted Dashboard snapshot and projects
their frozen status through the governed `team_state_public_v1` vocabulary. A league
listing may reuse that publication, but it must not infer clubs from Pitcher rows,
combine artifacts from different snapshots, or recalculate readiness from availability
counts.

## Decision

The league Dashboard may serve a listing of already-published Team State artifacts
pinned to the single current trusted Dashboard snapshot.

The expected MLB club universe is one sanctioned, immutable 30-club registry. The
registry owns denominator integrity and fallback identity only. Current identity from
the existing live team directory remains preferred when a row is available, but live
directory coverage never controls membership or the denominator.

The listing:

- introduces no Team State computation;
- introduces no ranking, scoring, grading, priority, prediction, or selection;
- does not order clubs by quality or severity;
- introduces no new public Team State vocabulary;
- reads published Team State artifacts for one snapshot in a single batch;
- preserves the existing deterministic winner order of `published_at` descending,
  then `id` descending;
- projects every selected artifact through the existing governed public Team State
  projection; and
- emits an explicit row for every club, including clubs with no Pitcher rows or no
  usable artifact.

### Existing freshness authority reuse

D-054 explicitly authorizes the narrow change to
`backend/services/board_freshness.py` required for snapshot-pinned serialization:

- a caller may supply the already-selected Dashboard snapshot explicitly;
- that caller may suppress the runtime sync overlay so the serialized listing stays
  pinned to one publication context;
- zero-argument and default callers retain their prior behavior;
- freshness calculations, stale gates, and fail-closed semantics do not change; and
- the listing reuses existing published-snapshot freshness rather than creating a new
  freshness authority.

When no trusted snapshot is servable, the listing uses the existing governed
`metadata_unavailable` freshness state and preserves the snapshot gate reason. D-054
does not introduce a `snapshot_unavailable` freshness-state vocabulary.

## Invariants

```text
represented + withheld = expected = 30
Fresh + Stretched + Vulnerable = represented
```

`Withheld` is a publication state, never a Team State. A missing, malformed,
unsupported, integrity-invalid, or publication-context-mismatched artifact withholds
only its club. No servable trusted snapshot withholds all 30 clubs while preserving the
denominator and the existing snapshot-gate reason. A connection-level snapshot read
failure remains an infrastructure failure and follows the existing HTTP 503 policy.

Every represented row relates to the same snapshot id, sync run id, data-through date,
and publication context. The response is ordered neutrally by team name, then team id.

## Rejected alternatives

- Deriving the expected club universe from Pitcher rows.
- Calling the live MLB `/teams` API on reader requests.
- Selecting the latest artifact independently for each team across snapshots.
- Deriving Team State in the frontend.
- Calling `canonical_team_state` or an equivalent per-team reader 30 times.
- Inferring Team State from availability counts.
- Restoring the withdrawn `league_state_board.py` prototype.

## Consequences

UX-2C may group the complete listing by the governed Team State already present in each
row while preserving alphabetical order within groups. The listing supplies no arm
counts and exposes no raw Monitor/Avoid vocabulary. Existing Team Board and trusted
Compare behavior remains unchanged because their per-team reader consumes the same
shared artifact projection.
