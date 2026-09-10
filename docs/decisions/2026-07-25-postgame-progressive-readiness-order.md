# Decision: Postgame progressive readiness order + expected active-slate exit semantics

- **Date:** 2026-07-25
- **Status:** Approved (founder decision) and implemented
- **Scope:** Postgame refresh ordering + the team-progressive readiness reference date +
  the postgame CLI exit semantics. NOT an SC-02 change; no public vocabulary, threshold,
  coverage, league-snapshot trust-gate, or payload change.

## Context — production run 471

A completed game (game_pk 824573, teams 117 and 145) ran through the postgame
progressive publisher and BOTH teams refused with:

```
data_state = missing
confidence = unknown
status_code = data_limited
```

Progressive accounting was otherwise clean (attempted=2, accounted=2, missing=0), the
unrelated live game (823196) never entered the event, and the league snapshot correctly
stayed pending (candidate 274, `dashboard_snapshot_slate_coverage_incomplete`). The
postgame command nonetheless exited 1 because the league candidate was unverified.

## Investigation (traced + reproduced) — the premise was wrong

The obvious hypothesis was an ordering defect: progressive publication ran before
fatigue recalculation (sync.py: progressive at the ingestion tail, fatigue after). But
the exact refusal signature is produced only by `team_readiness_coverage.assess_team_coverage`
**branch 1** (`if not authority_complete or active <= 0`) — the **active-bullpen ROSTER
AUTHORITY** resolving zero arms. That is roster-status-snapshot / reference-date driven,
**not** fatigue driven; stale/absent fatigue yields a *different* signature
(`readiness_evidence_missing`, or `low`/`incomplete`), never `data_state=missing`.

A production-shaped probe confirmed it:

- roster readiness absent + fatigue present → the EXACT run-471 signature (refused);
- fatigue absent → a different signature (`readiness_evidence_missing`);
- a roster snapshot at the game's SLATE date → both teams publish;
- with a slate-dated roster snapshot, `_active_bullpen_membership` resolves **only** when
  the reference date equals the slate (`authority_complete=True`, arms>0); at slate+1,
  slate+2, … it returns empty.

Root cause: once a game is final, the GLOBAL availability reference date advances to the
day AFTER it ("tonight's availability"), while that team's roster snapshot is dated at
the slate day. The active-bullpen authority is then queried for a date its roster
snapshot does not cover → empty → `data_state=missing` → `data_limited` → refused.

## Decision

1. **Anchor the team-progressive readiness read to the completed game's slate.** When a
   Team State read is produced from a team-progressive checkpoint authority
   (`subject_type='team_progressive'`), the availability reference date used for the
   active-bullpen membership and per-record classification is the checkpoint's slate
   (`data_through`), not the global (advanced) availability reference date. The active-
   bullpen authority then resolves for the exact slate the checkpoint attests to. It
   still fails closed unchanged when that slate genuinely has no roster snapshot. League
   and global reads are untouched.
2. **Run progressive publication after fatigue recalculation commits.** The postgame lane
   now recalculates + commits fatigue/workload evidence, then publishes progressively, so
   the readiness the generation path reads is current and committed. A fatigue failure
   fails the run closed and never reaches progressive (no publication on partial
   evidence). The newly-completed game_pks collected during ingestion are handed off to
   this later point unchanged; equivalent reruns stay idempotent.
3. **Separate postgame job success from league publication result.** The publication
   proof now classifies `league_publication_status` from the DETAILED slate-coverage
   object: `expected_pending_active_slate` only when the schedule is known, every final
   game is fully ingested (no failed/incomplete/missing markers), and the sole reason the
   slate is incomplete is that non-final games remain; any genuine
   schedule/ingestion/marker/trust gap stays `failed`. The postgame command exits 0 for an
   expected active-slate pending candidate while still reporting it honestly
   (`verified=false`, `candidate_is_published=false`). The daily sync is unchanged — it
   still requires a verified published trusted snapshot.

## Consequences

- During an active evening slate, a completed game's two teams publish progressively
  using the roster authority as of their slate, instead of refusing as authority-missing.
- A clean postgame refresh no longer reports workflow failure just because the league
  snapshot is expected-pending; genuine failures still exit non-zero.
- The league snapshot stays all-or-nothing; snapshots 272 and 274 are untouched; SC-02,
  thresholds, public vocabulary, the payload contract, and artifact identity/integrity are
  unchanged. SC-05 remains blocked and not started.

## References

- `services/share_artifact_generation.py` (`resolve_team_readiness_payload` slate anchor)
- `services/sync.py` (`run_postgame_refresh` progressive-after-fatigue ordering)
- `services/sync_publication_proof.py` (`league_publication_status` classification)
- `scripts/run_postgame_refresh.py` (expected-active-slate exit semantics)
- Tests: `tests/test_postgame_progressive_readiness_order.py`
- `docs/current/POSTGAME_PROGRESSIVE_READINESS_ORDER.md`
