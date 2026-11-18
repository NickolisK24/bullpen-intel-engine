# Repository Recovery: Workflow Reference Verification (2026-11-18)

**Scope:** Read-only inspection of all 27 workflow YAML files present under `.github/workflows/` on baseline `main` (`7a5fde1`). This is a continuation of the [branch inventory](2026-11-18-repository-recovery-branch-inventory.md).

## Findings

1. None of the 46 zero-ahead retirement candidates is referenced **by its exact branch name** in the 27 workflow YAML files inspected.
2. `baseballos-sync.yml` and `baseballos-generated-distribution.yml` contain explicit `main` checkout/push references. The production maintenance workflow also gates certain work on `refs/heads/main`.
3. `ci.yml` has `branches: ['**']`; this runs CI for branches but does not establish that a particular branch is a production dependency.
4. Several diagnostic workflows gate execution to `main`, and others use the triggering commit SHA or ref rather than a named feature branch.
5. The repository tree at `main` contained 27 workflow YAML files. This inspection did **not** include external Render/Vercel configuration, external automation, local clones/worktrees, historical workflow versions, or dynamically computed branch references.

## Retirement decision

**Eligible for final dependency review, not yet deleted:** the 46 zero-ahead branches listed in the branch inventory. Their commit history is reachable from `main`, but external references have not been independently verified.

**Hold:** all 18 unique-history branches, including the two open-PR heads. Do not delete, force-push, merge, or rewrite these merely to reduce branch count.

## Operational constraints

- The current GitHub connector offers branch creation, comparison and ref updates, but no branch-ref deletion action. Do not emulate deletion by force-moving refs or editing unrelated files.
- A human or tool with explicit branch deletion capability must perform final remote retirement after dependency review.
- No production deployment, PR merge, or branch deletion was executed in this verification.

## Next gate

Verify external deployment and branch references where accessible, then carry out explicit deletion of the safe candidate set using a supported branch deletion mechanism. Re-query branch inventory and record the post-deletion count and exact names.
