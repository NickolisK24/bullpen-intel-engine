# Decision: Publication-Critical vs Best-Effort Daily-Sync Work Contract

- **Date:** 2026-07-24
- **Status:** Approved (founder decision) and implemented
- **Scope:** Daily public sync trusted-snapshot publication gate. NOT an SC-02 change;
  no public vocabulary, prediction, ranking, or evidence-boundary change.

## Context

The daily public sync (GitHub Actions run `30124220074`, `SyncRun` 466, candidate
snapshot 270, `product_date` 2026-07-23) refreshed every public domain and produced a
candidate for a slate the appearance-ledger audit certified complete
(`Publish eligible: YES`, 96/96 games final, 825/825 appearances reconciled,
`errors = 0`), yet the trusted snapshot was withheld and the public surface kept serving
the prior day. This blocked SC-04B production verification.

Root cause (proven from code + the real Actions logs): `_complete_sync_phase` marks the
whole run `partial` on ANY dead-lettered record, and `compute_slate_coverage` forced
incompleteness whenever `sync_status == 'partial'` — regardless of current-slate
completeness. In run 466 the 234 `records_failed` were entirely budget-exhausted
best-effort game-log *corrections* for off-active-roster / historical arms; none were
required for the current public snapshot. The coarse rule could not distinguish "current
slate incomplete" from "a best-effort maintenance lane didn't finish."

## Decision

Adopt a **publication-critical vs best-effort work contract** for the daily sync:

1. **Publication-critical** work is REQUIRED to build the current public trusted
   snapshot: current active-MLB-roster pitchers' game logs, and every non-game-log
   publication lane (team assignments, roster statuses, transactions, schedule/finality
   preflight). Its completeness gates publication.
2. **Best-effort** work is historical / enrichment correction (off-active-roster,
   optioned, IL, minors, DFA arms; retroactive corrections). It may be deferred or
   dead-lettered without withholding the current snapshot.
3. **Unknown criticality fails closed** — anything not confidently classifiable is
   treated as publication-critical for the gate.
4. A trusted snapshot may publish under an overall `partial` `SyncRun` **only when every
   publication-critical requirement is complete**. `sync_status = partial` must NOT by
   itself mean the public snapshot coverage is incomplete.
5. **No trust gate is weakened.** Finality, appearance-ledger, freshness, provenance, and
   every current-slate game/marker/finality check are unchanged and still withhold a
   genuine gap. The relaxation is confined to a best-effort-only budget shortfall.
6. Criticality is read from each pitcher's already-synced canonical `roster_status` code
   (the canonical Roster Authority) **in memory**, adding zero pre-ingestion query cost —
   it must not worsen the starvation it fixes. The active MLB roster is a safe superset of
   the active bullpen, so an active-bullpen arm is never misclassified as best-effort.
7. Publication-critical work is **ingested first**; a budget shortfall can only defer
   best-effort work.

## Consequences

- A daily sync whose only shortfall is best-effort maintenance now publishes the current
  trusted snapshot instead of stranding the public surface on stale data.
- A publication-critical failure, an unknown-criticality item, or any genuine
  current-slate gap still withholds — fail-closed behavior is preserved.
- Every non-daily caller of `compute_slate_coverage` is unchanged: the new
  `publication_critical_complete` argument defaults to `None`, which reproduces the prior
  conservative `partial`-blocks behavior exactly.
- Snapshot 270 is **not mutated**; it remains historical evidence of the incident.
- The publication proof now explains why a `partial` run published (all
  publication-critical complete; only best-effort deferred).

## Deferred

- **Roster-fetch dedup (WS-H)** — a budget-headroom optimization, not required for this
  contract's correctness. Deferred with founder permission; independent follow-up.

## Accepted caveat

Game-log criticality is inferred from the current active-roster status rather than an
officially-stored active-bullpen partition (BaseballOS has none). Using the active MLB
roster as a safe superset is the conservative choice: it may front-load a few starters,
but it never defers a real active-bullpen arm. Approved on that basis.

## References

- `docs/current/DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md`
- `services/publication_criticality.py`,
  `services/sync.py` (`sync_recent_logs`, `_complete_sync_phase`,
  `complete_sync_run_with_snapshot`),
  `services/slate_coverage.py::compute_slate_coverage`,
  `services/dashboard_snapshot.py`,
  `services/sync_publication_proof.py`,
  `scripts/run_daily_sync.py`
- Tests: `tests/test_publication_criticality.py`,
  `tests/test_daily_sync_publication_budget.py`
