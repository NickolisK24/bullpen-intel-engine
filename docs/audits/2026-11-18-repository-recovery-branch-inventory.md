# Repository Recovery: Branch Inventory (2026-11-18)

**Status:** Read-only classification of existing remote branches, not authorization to delete, merge, deploy, or change production.
**Repository:** NickolisK24/bullpen-intel-engine
**Baseline:** main at `7a5fde1e1ef56ee20934c5187911e7c6e23fa974`
**Owner:** Nickolis Kacludis
**Objective:** Recover a clean, intelligible repository and an accurate handoff baseline before selecting new product work.

## Inventory totals

- 65 pre-existing remote branches: 1 `main`, 46 verified ancestor branches with zero unique commits reachable from their heads versus `main`, and 18 branches with commits not reachable from `main`.
- This inventory branch was created **after** the baseline count and is not included in the 65.
- 2 open PRs: #909 and #911.
- No branch deletions or PR merges were performed during classification.
- "Ahead" is commit-graph reachability, not proof that equivalent changes are absent from `main` (cherry-picks and squashes can preserve changes with different SHAs).

## Category A: Zero-ahead branch heads (candidate for remote retirement)

These branches were individually compared with the baseline `main` and each reported `ahead_by=0`. Verify branch usage by automation, deployments, external references, and other worktrees before deletion. Preserve tags/PR history where useful.

- `audit/tonight-12-final-production-certification`
- `chore/tonight-11-7-legacy-backend-retirement`
- `chore/tonight-11-legacy-retirement`
- `feat/team-board-2-0-final-polish`
- `feat/team-board-2-0-foundation`
- `feat/team-board-2-0-performance`
- `feat/team-board-2-0-recent-relief-work`
- `feat/team-board-2-0-recent-usage-rest`
- `feat/team-board-2-0-roles-deployment`
- `feat/team-board-2-0-roster-transactions`
- `feat/team-board-2-0-rotation-impact`
- `feat/team-board-2-0-what-changed`
- `feat/team-board-2-0-workload-overview`
- `feat/tonight-00-authority-hardening`
- `feat/tonight-01-read-model`
- `feat/tonight-02-serving-delivery`
- `feat/tonight-03-game-state-overlay`
- `feat/tonight-04-matchup-context`
- `feat/tonight-06-featured-games`
- `feat/tonight-07-lead-development`
- `feat/tonight-08-frontend-page`
- `feat/tonight-09-hardening`
- `feat/tonight-10-root-cutover`
- `feat/tonight-11-5-slate-lifecycle`
- `feat/tonight-11-6-featured-lifecycle`
- `fix/api-startup-migration-recovery`
- `fix/cancelled-game-slate-coverage`
- `fix/daily-primary-canonical-team-filter`
- `fix/daily-primary-memory-peak`
- `fix/daily-primary-team-state-30-team-publication`
- `fix/daily-publication-team-authority`
- `fix/daily-schedule-finality-persistence`
- `fix/league-board-current-team-state-artifacts`
- `fix/league-team-state-artifact-generation-root-cause`
- `fix/phase0-wp01-current-read-integrity`
- `fix/production-lineage-reconciliation`
- `fix/publication-withhold-artifact-gate-order`
- `fix/static-preview-canonical-team-universe`
- `fix/supabase-egress-production`
- `fix/team-board-governed-relief-workload-display`
- `fix/tonight-11-8-date-rollover`
- `fix/trusted-publication-observation-integrity`
- `fix/wp01-competition-withheld-artifact-gate`
- `security/sec-01-supabase-rls-hardening`
- `test/tonight-v1-rehearsal-certification`
- `test/trusted-publication-rehearsal`

## Category B: Unique commit history (PRESERVE pending reconciliation)

Do not delete or auto-merge. Inspect patch equivalence, upstream PR status, operational dependencies, and branch intent.

- `audit/2026-end-of-season-platform-audit`
- `claude/baseballos-viability-audit-8ufhk9`
- `claude/upbeat-hawking-g0indq`
- `feat/sync-pipeline`
- `fix/audit-r1-roster-authority`
- `fix/audit-r2-writer-fencing`
- `fix/audit-r3-input-closure`
- `fix/audit-r3-integrity`
- `fix/audit-r3-selector-capture`
- `fix/daily-edition-context-handoff`
- `fix/evidence-quality-operating-state-separation`
- `fix/phase0-wp02-security-operations`
- `fix/production-migration-authority`
- `fix/r3b11-migration-lineage`
- `fix/r3b12a-migration-lineage`
- `fix/shadow-historical-dashboard-reuse`
- `fix/shadow-runner-peak-memory-and-info-telemetry`
- `fix/supabase-egress-p0`

Notable:
- `feat/sync-pipeline`: 135 ahead / 294 behind. This is a large divergent integration history; a merge is **not** implied.
- `fix/audit-r3-integrity`: 110 ahead / 294 behind, with related R1/R2/R3 branches also divergent.
- `claude/upbeat-hawking-g0indq`: 4 ahead / 0 behind; recent backtesting work with failing CI, no automatic disposition.
- `claude/baseballos-viability-audit-8ufhk9`: 1 ahead / 208 behind; contains a large viability-audit document.
- `audit/2026-end-of-season-platform-audit`: 1 ahead / 28 behind.
- `fix/evidence-quality-operating-state-separation`: PR #909, 3 ahead / 64 behind, GitHub mergeable=false.
- `fix/phase0-wp02-security-operations`: PR #911, 8 ahead / 11 behind, GitHub mergeable=true but explicitly requires founder review.
- `fix/daily-edition-context-handoff`: 2 ahead / 276 behind.
- `fix/r3b11-migration-lineage`: 2 ahead / 275 behind.
- `fix/r3b12a-migration-lineage`: 1 ahead / 274 behind.

## Verified operational findings

- `main` was unprotected with required status checks off at inspection.
- On Nov 18, GitHub Actions run `44281693317`: `public-sync` succeeded, `internal-enrichment` failed, and `shadow-activation-health` failed. This is **not** proof that the public publication failed.
- PR #911 describes reproductions and proposed repairs for the enrichment claim guard and shadow validator; these are not yet integrated.
- The root README and `docs/canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md` contain historical execution-state statements requiring reconciliation with the current `main`. The canonical roadmap is marked v5.16 (September 4, 2026); the founder's separately supplied August 17 v4.0 is an earlier edition, not evidence of current code state.
- The repo already has `docs/REPOSITORY_DOCUMENTATION_MAP.md`; retain its classification rules and update factual currency only after verification.
- No automated game-driven writer/publication authority transfer is authorized by this inventory.

## Cleanup execution gates

1. Confirm zero-ahead branches have no live operational references before remote deletion.
2. Compare unique branch patches against `main` and other branch tips to detect duplicated/cherry-picked changes.
3. Review PR #909 and #911 independently, including tests, migration/production effects, and founder sign-off.
4. Reconcile documentation to the actually integrated code and deployed authority; preserve audit history.
5. Verify main protection and a working developer handoff without changing production data or secrets.
6. Only after these gates pass, declare repository recovery complete and select the next single product objective.

**Safety:** No branch deletion, forced push, migration, secret rotation, PR merge, or production deployment is authorized by this record.
