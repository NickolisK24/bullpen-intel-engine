# Decision: Readiness Freshness Uses the Serving Trusted Snapshot

- **Date:** 2026-07-25
- **Status:** Approved (founder decision) and implemented
- **Scope:** Team Operations Readiness freshness verdict for reads produced from a
  serving trusted daily snapshot (the Share Artifact batch). NOT an SC-02 change; no
  public vocabulary, threshold, coverage, or eligibility change.

## Context

The daily Share Artifact batch (source snapshot 271 / sync_run 467, product_date
2026-07-23) refused all 30 teams with `stale_snapshot` / `insufficient_trust` /
`unsupported_team_state` (`freshness_state:stale`, `data_state:stale`, `confidence:low`,
`status_code:data_limited`) even though the serving trusted snapshot published under the
publication-critical contract.

Investigation **disproved** the hypothesized `sync_status == 'partial'` coupling: the
readiness freshness path never keys off `partial`; `is_current` is purely date-based.
`data_state:stale` comes only from the source-stale gate in
`team_readiness_coverage.assess_team_coverage`, so it proves `source_current = False` —
the live `is_current` was False. The true defect is a **reference-date mismatch**: the
batch resolves active-bullpen membership / availability / appearance-ledger against the
data-derived availability reference, but resolves `is_current` against the wall-clock
`product_current_date()` and the global `max(GameLog.game_date)`. When the live
game-log recompute trails the schedule/appearance authority the serving snapshot
published on, `is_current` is False while coverage is complete — so every team is forced
stale.

## Decision

1. Overall `SyncRun` `partial` status does not (and never did) make published readiness
   stale; the coupling was never there.
2. A read produced from a serving trusted snapshot anchors its freshness **verdict** to
   that snapshot's authoritative `data_through`, not to a live global
   `max(GameLog.game_date)` recompute. A published, serving, trusted snapshot has
   already passed the publication-critical, finality, appearance-ledger, freshness, and
   provenance publish gates; within the freshness window it is current.
3. Only the freshness verdict is anchored. Active-bullpen membership, availability
   classification, and appearance-ledger completeness stay anchored to the data-derived
   reference, so per-team coverage still governs high / medium / low / unknown.
4. Fail closed: publication-critical incomplete (untrusted/unpublished snapshot),
   unknown / missing authority, a `data_through` outside the freshness window, a
   non-serving snapshot, or an unreadable trust verdict all keep the prior conservative
   live freshness. Best-effort deferred work alone no longer forces stale readiness.
5. SC-02 is unchanged — vocabulary, thresholds, coverage math, and the low /
   `data_limited` refusals are untouched. No snapshot is mutated; no historical artifact
   changes.

## Consequences

- A daily batch generating from a current serving trusted snapshot no longer refuses
  every team merely because the live game-log recompute trails the snapshot.
- A genuinely stale snapshot, a publication-critical failure, an unknown authority, or a
  team's own insufficient coverage still degrade or refuse, fail closed.
- The live `GET /api/team-operations/bullpen-readiness` path (no snapshot) is unchanged;
  the new `source_snapshot` argument defaults to `None` and reproduces prior behavior.

## Accepted caveat

Anchoring the freshness verdict to the snapshot's `data_through` presents a team as
current when the serving snapshot is current even if the per-pitcher game-log lane
trails it. This is safe because (a) the snapshot passed every publish gate, and (b) the
unchanged coverage classifier — which uses the ledger-confirmed-rest authority, not raw
game-log recency — still governs whether the team is high / medium / low. Approved on
that basis.

## References

- `docs/current/READINESS_FRESHNESS_SERVING_SNAPSHOT.md`
- `services/readiness_snapshot_freshness.py`,
  `services/share_artifact_generation.py::resolve_team_readiness_payload` /
  `generate_team_state_artifact`
- Trace anchors: `api/team_operations.py::_assess_active_bullpen_coverage` (source_current),
  `services/team_readiness_coverage.py::assess_team_coverage` (source-stale gate),
  `services/sync_metadata.py::determine_freshness_state` (date-based is_current)
- Tests: `tests/test_readiness_snapshot_freshness.py`,
  `tests/test_readiness_freshness_partial_sync.py`
