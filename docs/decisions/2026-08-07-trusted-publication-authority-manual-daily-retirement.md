# D-051 — Trusted public serving authority and manual daily retirement

- **Date:** 2026-08-07
- **Status:** Approved founder decision; Team Board/Compare clauses amended by D-058;
  all trigger, league-publication, and Tonight boundaries remain in force
- **Scope:** Production full-daily trigger authority and the serving authority for Team Board, Compare, and Tonight. No scoring, Team State vocabulary, publication-gate, game-driven writer, backfill, or model-threshold change.

## Context

OPS-002 established that the full daily sync could exhaust its runtime budget before
publication-critical GameLog work completed. The bounded mitigation restored sufficient
runtime headroom, but controlled manual recovery run `31229140790` exposed a separate
serving-authority defect.

That run completed all 861 legacy GameLog fetches with `budget_exhausted_pitchers == 0`
and the game-driven shadow lane remained zero-write, but a publication-critical roster
snapshot team conflict for MLB person `670245` caused the candidate Dashboard snapshot to
be withheld. The previous trusted Dashboard snapshot correctly remained published.

The public Team Board/Compare path was not equally frozen. It used the published snapshot
for freshness and capped FatigueScore time, while rebuilding roster membership and Team
State from mutable current tables. A failed sync could therefore produce a mixed read:
old trusted freshness plus partially advanced roster/readiness state. Tonight had a
related cache-miss behavior: a public request could rebuild live against mutable tables.

The failure was therefore safe at the Dashboard publication gate but not sufficiently
isolated at every reader surface. A failed acquisition attempt must never become de facto
public authority merely because some canonical rows committed before the candidate was
withheld.

## Decision

1. **The production full-daily runner is schedule-only and first-attempt-only.** Ordinary
   `workflow_dispatch` execution of the authoritative daily command is retired. The
   external production daily runner refuses any non-scheduled invocation and any GitHub
   Actions rerun (`GITHUB_RUN_ATTEMPT != 1`) before Flask application import, database
   initialization, or writer execution. A manually re-run scheduled job is therefore not
   a recovery mechanism. There is no manual recovery override in this decision.

2. **The legacy production admin full-sync endpoint is retired.** Production
   `POST /api/bullpen/sync` returns an explicit refusal and cannot bypass the schedule-only
   command boundary. Development/test retain the endpoint only for isolated validation.

3. **Acquisition state and public authority are separate.** Canonical acquisition tables
   may advance during a sync so the operator can diagnose/reconcile work, but those writes
   do not change public claim authority. Public state advances only after a trusted
   publication succeeds.

4. **Team Board/Compare are bound to the trusted league Dashboard publication.** During
   candidate Dashboard construction, the backend freezes the JSON-safe Team Board source
   material needed to reproduce each club's board. That source package becomes usable
   only if the candidate becomes the trusted published Dashboard snapshot. Public Team
   Board and Compare render from that frozen package, not from mutable current Pitcher,
   roster, GameLog, FatigueScore, or readiness rows.

5. **Team State on Board/Compare is source-exact.** The Team State shown with a frozen
   league board is read from the immutable published Team State artifact authorized by
   that exact league Dashboard snapshot. The reader path does not recompute readiness
   live. If the matching artifact is absent or fails integrity verification, Team State
   fails closed to the governed unavailable block; it is not substituted from another
   date or authority.

6. **Production Tonight is snapshot-only at request time.** The public Tonight endpoint
   may serve an already-persisted Tonight snapshot, but a browser cache miss cannot run a
   live intelligence rebuild. A missing cache returns an honest unavailable/quiet state.
   Scheduled/postgame warming remains the controlled producer; no new writer authority is
   granted.

7. **Existing publication gates remain unchanged and cannot be weakened.** Slate
   finality, appearance-ledger integrity, roster/source authority, publication-critical
   accounting, Dashboard cache verification, and game-driven shadow zero-write behavior
   remain required exactly as before.

8. **Team-progressive publication remains a distinct approved authority.** This decision
   does not remove or redefine immutable team-progressive Share Artifacts. Team Board and
   Compare remain league-aligned under this package so they cannot silently mix a newer
   team-scoped conclusion with an older league board. Any future Board cutover to
   team-progressive authority requires a separate explicit product/authority decision.

## OPS-002 acceptance reconciliation

The former controlled-manual-recovery criterion is retired when this implementation is
merged because the mechanism it required is intentionally prohibited. Historical manual
run evidence is preserved; it is not rewritten or presented as success.

OPS-002 production closeout becomes scheduled-only evidence:

1. Three consecutive scheduled, first-attempt full daily runs complete under the mitigated
   runtime budget. A GitHub Actions rerun is not eligible evidence.
2. Every run reports `budget_exhausted_pitchers == 0`.
3. Every run reports `publication_critical_failed == 0`.
4. Every run publishes, selects, and serves its new trusted Dashboard snapshot.
5. Appearance-ledger and Dashboard-cache proofs pass.
6. Game-driven shadow remains zero-write.
7. Team Board and Compare serve from trusted Dashboard publication authority and do not
   advance from a withheld candidate.
8. Tonight never performs an on-demand public live build.

A manual daily run is no longer evidence and does not substitute for any scheduled run.

## Consequences

- Failed daily attempts may leave diagnostic/acquisition rows that operators can inspect,
  but readers continue seeing the previous published authority instead of a mixed state.
- A pre-D-051 trusted snapshot that lacks the frozen Team Board package fails closed on
  Board/Compare until a D-051-capable snapshot publishes; the backend does not silently
  reconstruct it from newer mutable data.
- A missing Tonight cache is temporarily less available but more trustworthy: the public
  endpoint refuses to manufacture a current-looking claim from unpublished state.
- The historical `daily` workflow-dispatch choice may remain visible until the long
  workflow UI is simplified, but selecting it cannot initialize the app/database or run
  the writer. A GitHub Actions rerun is likewise refused.
- Manual full-daily execution can no longer become load-bearing recovery behavior.
- No schema migration is required; the frozen Board package is stored inside the existing
  DashboardSnapshot JSON payload.
- OPS-002 remains open until the three scheduled production runs prove the new operating
  contract.

## D-058 amendment

D-058 supplies the separate authority decision anticipated by clause 8. It permits Team
Board to move, through a staged and separately proven cutover, from a Dashboard-only
team slice to one complete immutable per-team public-read package selected by a
backend-owned current pointer. It does not permit field overlays or mutable request-time
reconstruction.

Compare remains common-boundary-only: it may use per-team packages only when both teams
share one compatible publication cohort; otherwise it continues using a common trusted
league boundary or fails closed. Home, League, Tonight, league-wide changes, and other
common-population surfaces retain their existing complete league/snapshot authority.

D-058 is architecture-only until its rollout gates pass. Therefore the production reader
implemented by PR #627 remains authoritative during migration, and accepting D-058 does
not itself change a serving path.

## References

- Issue #620 — OPS-002 daily-sync runtime-budget exhaustion and production proof
- PR #627 — trusted public serving authority and manual daily retirement
- Run `31229140790` — runtime mitigation succeeded; roster conflict withheld candidate
- `backend/scripts/run_daily_sync.py` — production scheduled-trigger/run-attempt guard
- `backend/services/public_serving_authority.py` — frozen Board/Compare authority and
  Tonight snapshot-only serving
- `backend/app.py` — production serving installation and retired admin sync endpoint
- `backend/services/dashboard_snapshot.py` — trusted Dashboard publication lifecycle
- `backend/models/share_artifact.py` — immutable Team State artifact authority
- `docs/decisions/2026-09-04-per-team-public-read-authority-continuous-updates.md`
  — D-058's bounded amendment and staged cutover contract
