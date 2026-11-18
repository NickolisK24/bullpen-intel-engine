# BaseballOS Repository Handoff: Verified Recovery Baseline

**Snapshot:** November 18, 2026. **Status:** recovery in progress; not a certification of production health.
**Verified code basis:** `main` at `7a5fde1e1ef56ee20934c5187911e7c6e23fa974`.
**Active objective:** make the existing repository safe, understandable, and maintainable before choosing the next product initiative.

> This document is an onboarding and reconciliation index, **not** a seventh canonical product authority or a replacement roadmap. It reports only what has been inspected. Follow the canonical documents for durable rules, the live code/workflows for executable contracts, and the current incident/PR evidence for unmerged work.

## Start here

1. Root [README](../../README.md) for product scope, public routes, architecture, and local commands.
2. [Setup guide](../current/SETUP.md) for local PostgreSQL, Python/Flask, React/Vite, migrations and tests.
3. [Canonical documentation library](../canonical/README.md) for the six governing documents and precedence.
4. [Sync runbook](../current/SYNC_PIPELINE.md) and [production workflow](../../.github/workflows/baseballos-sync.yml) for exact scheduled execution and writer authority.
5. [Branch inventory](../audits/2026-11-18-repository-recovery-branch-inventory.md) and [workflow reference check](../audits/2026-11-18-repository-recovery-workflow-reference-check.md) for cleanup decisions.

## Architecture and authority

- Frontend: React/Vite/TailwindCSS; hosted on Vercel according to the root README.
- Backend: Python/Flask; hosted on Render according to the root README.
- Database: PostgreSQL, SQLAlchemy and Alembic.
- Public source acquisition: MLB Stats API.
- GitHub Actions participates in scheduled execution, tests, diagnostics and generated distribution.
- The current sync runbook says the **legacy daily/postgame writer is authoritative**; game-driven daily and postgame lanes are **shadow**; automated game-driven backfill is **off**; writer/publication authority transfer is **unapproved**. Do not infer a transfer from code or a feature branch.
- Current source and publication semantics are governed by the canonical intelligence/architecture documents, not frontend fallback guesses.
- Never run production migrations, replay, backfill, manual writer, secret rotation, or publication during repository cleanup.

## Reproducing a local environment

Follow `docs/current/SETUP.md`, using the checked-in `backend/.env.example` and `frontend/.env.example` as the environment-variable contracts. Use a disposable local PostgreSQL database. Backend: create a venv, install `backend/requirements-dev.txt`, set local `DATABASE_URL`, run `flask db upgrade` from `backend`, then `flask run`. Frontend: `npm install`, `npm run dev`; run `npm test` and `npm run build` for frontend validation. Run `python -m pytest backend/tests` for backend tests. **These commands are documented but were not executed as part of this remote-only repository inventory.**

## Live GitHub findings at this baseline

- Original inventory: 65 branches, including `main`; 46 zero-ahead branches are retirement candidates, 18 unique-history branches require reconciliation. A new recovery branch was created after the count.
- Existing open PRs at inspection: [#909](https://github.com/NickolisK24/bullpen-intel-engine/pull/909) and [#911](https://github.com/NickolisK24/bullpen-intel-engine/pull/911); the recovery inventory is [draft #913](https://github.com/NickolisK24/bullpen-intel-engine/pull/913).
- `main` had no branch protection and no enforced required status checks when checked.
- Nov 18 scheduled [GitHub Actions run 44281693317](https://github.com/NickolisK24/bullpen-intel-engine/actions/runs/44281693317): `public-sync` passed; `internal-enrichment` and `shadow-activation-health` failed. A failed composite workflow does not by itself prove that public sync failed.
- PR #911 describes fixes for both failing jobs, but has not been merged or validated against the latest `main`.
- PR #909 changes published Team State/evidence behavior, is non-mergeable against current `main`, and requires explicit correctness review and certification before any integration.
- The `claude/upbeat-hawking-g0indq` branch has new backtesting code and failing CI; it is not part of the approved recovery scope and must remain preserved, not silently integrated.
- The large `feat/sync-pipeline` and related R1/R2/R3 branches are divergent, with unique commits. Reachability alone cannot establish whether their effects are already present through cherry-picks.
- `docs/README.md` has an execution snapshot from August 25, while the repository canonical roadmap v5.16 has a September 4 basis. Treat those historical summaries as unverified for November until reconciled. Do not replace the roadmap with the founder's older August 17 v4.0 attachment.

## Open decisions, not hidden assumptions

| Item | Verified condition | Required disposition |
| --- | --- | --- |
| 46 zero-ahead branches | Ancestors of `main`; no exact branch-name references in the 27 workflow YAML files inspected | Check external Render/Vercel/other refs and local worktrees, then retire using supported branch deletion |
| 18 unique-history branches | Contain commits not reachable from `main` | Patch-equivalence review, then preserve, integrate, or archive with rationale |
| PR #909 | 3 ahead / 64 behind; non-mergeable; 50 changed files; no submitted reviews observed | Reconcile semantics, conflicts and tests before founder merge decision |
| PR #911 | 8 ahead / 11 behind; 24 changed files; no submitted reviews observed | Rebase/merge validation, production-security approval, then founder decision |
| GitHub branch safeguards | Main protection disabled at inspection | Apply a minimal safe rule only after checking automation's direct push behavior |
| Production sync failures | Public-sync passed, two downstream jobs failed | Reproduce and validate fixes; avoid claiming resolved before natural production proof |
| Documentation currency | Multiple current-state entry points are dated | Reconcile to verified integrated/deployed state without rewriting historical evidence |

## Recovery exit criteria

- Each branch has a documented disposition; no unreviewed unique commits are discarded.
- Obsolete remote refs are removed and branch inventory is verified again.
- Open PRs are explicitly merged, closed with rationale, or retained as named pending work.
- Main branch protection is compatible with verified automation, and CI remains functional.
- README, setup, sync runbook, canonical roadmap and this handoff index do not contradict known current behavior.
- A fresh developer can set up a local environment, identify authority boundaries, run tests, locate operational runbooks, and explain unresolved risks without a private conversation.
- All production claims are distinguished from code inspection and independently checked where access permits.

**Do not declare recovery complete until every exit criterion is evidenced.**
