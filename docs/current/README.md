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
7. [`CHANGELOG.md`](CHANGELOG.md) — milestone chronology.

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

## Current Production Boundary — August 13, 2026

- legacy daily/postgame writer remains authoritative;
- daily and postgame game-driven lanes are shadow;
- backfill is off by default;
- automated game-driven write/publication authority is unapproved;
- game `824487` repair is retired;
- OPS-002 (#620) is complete; its permanent work-reduction follow-up remains separate;
- generated content reaches `main` only through the self-gating publication job (D-053);
- fail-closed publication remains mandatory.

## Current Dependency-Security Boundary — August 13, 2026

- production installs `backend/requirements.txt` only; `backend/requirements-dev.txt` adds test dependencies for local work and test jobs;
- backend runtime dependencies carry no known advisories;
- a standing read-only `dependency-audit` CI job refuses unreviewed production dependency risk and never upgrades a dependency itself;
- three React Router advisories are an explicit acceptance expiring **2026-11-13** — the first refused day, not the last accepted one — tracked by #645;
- the acceptance depends on `safeVerifyRedirect()` and its regression tests; weakening them voids it.

Detail and standing obligations:
[`DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md`](DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md).
