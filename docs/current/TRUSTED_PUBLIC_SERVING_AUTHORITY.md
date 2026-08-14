# Trusted Public Serving Authority

**Status:** Current operating contract after D-051  
**Authority:** Secondary to `docs/canonical/04_PLATFORM_ARCHITECTURE_OPERATIONS.md` and the D-051 entry in `docs/canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md`. This document owns the trusted-serving detail and the current OPS-002 criterion set.  
**Owner:** Nickolis Kacludis  
**Last reviewed:** August 14, 2026

BaseballOS separates acquisition from publication. A sync may write canonical source rows before the full candidate has passed every publication gate. Those writes are inspectable operational state; they are not automatically public authority.

## Production full daily

The external production full-daily runner is schedule-only and first-attempt-only. `backend/scripts/run_daily_sync.py` refuses a non-scheduled production invocation and refuses `GITHUB_RUN_ATTEMPT != 1` before importing the Flask application or initializing the database. An ordinary GitHub Actions `workflow_dispatch` daily attempt and a manually re-run scheduled daily therefore cannot become production writers.

Production `POST /api/bullpen/sync` is also retired and returns an explicit refusal, so the historical admin writer cannot bypass the schedule-only command boundary. Development/test retain that route only for isolated validation.

Scheduled daily remains the normal production-authoritative full reconciliation path. Postgame, backfill, intraday audit, game-driven shadow, and team-progressive authority retain their separately governed contracts; D-051 grants none of them new authority.

The Actions workflow may still display the historical `daily` workflow-dispatch choice until that long workflow UI is simplified. The choice is intentionally non-authoritative: selecting it reaches the runner guard and refuses before application/database initialization.

## Dashboard publication boundary

While a candidate Dashboard snapshot is being built, BaseballOS captures a JSON-safe `trusted_team_boards` package inside that candidate. The package contains the per-team board source material as it existed for that candidate: board records, default membership, roster authority, workload concentration, and supporting team context.

The package is not a public authority merely because it exists. It becomes servable only when the containing Dashboard snapshot becomes the latest valid published snapshot.

If the candidate is withheld, the previous published snapshot — and therefore the previous frozen Team Board package — remains authoritative.

## Team Board and Compare

Production Team Board and Compare do not reconstruct claim-bearing state from mutable current acquisition tables. They select the latest valid published Dashboard snapshot and render from its frozen `trusted_team_boards` package.

The current request may add a freshness overlay explaining that a newer sync is running or failed, but that overlay does not replace or recompute the frozen baseball claim.

Team State is source-exact. The board reads the immutable published Team State artifact tied to the same league Dashboard snapshot. A missing or integrity-failed exact artifact produces the governed Team State unavailable block. The reader path never substitutes a different date, a team-progressive artifact, or a live readiness recomputation.

A legacy published Dashboard snapshot created before D-051 has no frozen board package. In production the board fails closed until a D-051-capable snapshot publishes; it does not silently rebuild from newer mutable rows.

## Tonight

Production Tonight is snapshot-only at browser request time. The request path may serve the persisted Tonight snapshot for the resolved slate. If none exists, it returns an honest unavailable state and does not run an on-demand live intelligence build.

Controlled schedule/postgame warming remains the producer of Tonight snapshots. This change removes only the public-request live fallback; it does not grant a new writer or publication authority.

## Failure behavior

A failed or withheld daily attempt may leave canonical acquisition rows that help diagnose and reconcile the next governed run. Those rows cannot, by themselves, change the public Team Board, Compare, or Team State authority. The last trusted published view continues to govern until a new candidate passes publication.

This is the intended fail-closed behavior: **safe and explicitly dated rather than current-looking but partially advanced.**

## OPS-002 proof

D-051 retires the controlled-manual-daily recovery criterion because authoritative manual daily execution is intentionally prohibited. OPS-002 remains open and requires three consecutive scheduled, first-attempt full daily runs proving:

- `budget_exhausted_pitchers == 0`;
- `publication_critical_failed == 0`;
- the candidate is published, selected, and served;
- appearance-ledger proof passes;
- Dashboard-cache proof passes;
- game-driven shadow remains zero-write;
- Team Board and Compare serve trusted Dashboard publication authority;
- Tonight does not perform a public on-demand live build.

A manually re-run scheduled job is not eligible proof.

The runtime mitigation remains temporary headroom. Permanent GameLog candidate prefiltering and incremental roster/transaction synchronization remain separate follow-up work.
