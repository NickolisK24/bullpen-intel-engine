# Current BaseballOS Operational Documentation

This directory contains active procedures, current subsystem support, and the
changelog. It is subordinate to the six canonical documents.

Start with:

1. [`SETUP.md`](SETUP.md) — local development and environment setup.
2. [`SYNC_PIPELINE.md`](SYNC_PIPELINE.md) — current sync/publication authority, trust gates, OPS-001 signal separation, and OPS-002 runtime reliability contract.
3. [`DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md`](DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md) — publication-critical daily behavior.
4. [`GAME_DRIVEN_DAILY_INGESTION.md`](GAME_DRIVEN_DAILY_INGESTION.md) — game-driven ingestion qualification subsystem; daily/postgame remain shadow.
5. [`INTRADAY_RECONCILIATION.md`](INTRADAY_RECONCILIATION.md) — audit/reconciliation subsystem.
6. [`DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md`](DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md) — current dependency-security boundary and its standing obligations.
7. [`TEAM_STATE_VNEXT_PRODUCTION_PROOF.md`](TEAM_STATE_VNEXT_PRODUCTION_PROOF.md) — the side-channel evidence artifact one natural publication produces, its eight invariants, and the closeout condition for Team State vNext.
8. [`CHANGELOG.md`](CHANGELOG.md) — milestone chronology.

Share Artifact support files in this directory remain implementation/operations
records for the immutable artifact domain.

## Authority Reminder

- The canonical library defines durable product, intelligence, experience,
  architecture, editorial, and roadmap meaning.
- Current runbooks define exact procedures within their scope.
- Audits prove point-in-time evidence.
- Decision records preserve rationale.
- Historical phase/project-state files belong in the archive, not here.

Repository-wide classification:
[`../REPOSITORY_DOCUMENTATION_MAP.md`](../REPOSITORY_DOCUMENTATION_MAP.md).

## Current Production Boundary

Unchanged: the legacy daily/postgame writer remains authoritative, game-driven
lanes remain shadow, backfill is off by default, the game `824487` repair is
retired, and fail-closed publication stays mandatory.

This directory does not own that list. Read it, with its evidence and decision
history, in
[`../canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md`](../canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md);
read the operating procedure in [`SYNC_PIPELINE.md`](SYNC_PIPELINE.md).

## Current Dependency-Security Boundary

Production installs `backend/requirements.txt` only, a standing read-only
`dependency-audit` CI job refuses unreviewed production dependency risk, and
three React Router advisories are an explicit acceptance expiring
**2026-11-13** — the first refused day, not the last accepted one — tracked by
#645. Weakening `safeVerifyRedirect()` or its regression tests voids that
acceptance.

Full boundary and standing obligations:
[`DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md`](DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md).
