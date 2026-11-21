# WP-0.2 Branch Protection Plan

**Status:** Plan only. Repository protection was **not** changed. It needs founder approval.

## Current state (verified 2026-11-05)

- `main`: `"protected": false` (`list_branches`). No ruleset.
- The only collaborator is `NickolisK24` (admin).
- Human changes land as "Merge pull request #N" merge commits. WP-0.1 was merged as a locally built merge commit followed by a fast-forward push.
- Bot commits: about 1–2 a day from `BaseballOS Automation <baseballoshq@gmail.com>`.
  - Jobs: `baseballos-sync.yml` → `static-team-story-preview`, and `baseballos-generated-distribution.yml` → `deliver-generated-content`.
  - Mechanism: the job's `GITHUB_TOKEN`, with `contents: write`, runs `git push origin HEAD:refs/heads/main` as a fast-forward only.
  - Content is staged only from `frontend/public/team|share/**` and `404.html`.
- **Constraint:** a ruleset that requires pull requests blocks these pushes. `GITHUB_TOKEN` cannot be listed as a bypass actor, and the `github-actions` integration is not a selectable bypass app.

## Why not just "protect main"

Requiring pull requests today would stop preview publication the next day, because the bot push would be rejected. Granting the bot a permanent broad bypass would weaken protection exactly where it matters (EOS-013). The fix is to separate generated assets from application source.

## Staged plan

### Stage 1: now. Compatible with the bot, zero publishing risk.

Create a repository ruleset `main-integrity` targeting `refs/heads/main`:

| Rule | Setting |
|---|---|
| Restrict deletions | on |
| Block force pushes | on |
| Require linear history | **off** (merge commits are the convention) |
| Require pull request | **off** in Stage 1 |
| Bypass list | empty |

`gh` equivalent (an admin runs this; not executed by WP-0.2):

```bash
gh api -X POST repos/NickolisK24/bullpen-intel-engine/rulesets --input - <<'JSON'
{
  "name": "main-integrity",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
  "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}],
  "bypass_actors": []
}
JSON
```

The bot already pushes fast-forward only, so Stage 1 cannot break publishing. It removes the two irreversible failure modes: a deleted or force-rewritten `main`.

### Stage 2: after generated content leaves `main`'s protected path

Pick one, in order of preference:

- **A (preferred, the EOS-013 / DEC-05 direction).** The bot publishes generated pages to a separate branch, for example `generated-distribution`, and Vercel builds from `main` plus that content (or from an artifact). `main` then receives only reviewed application changes.
- **B (interim).** Move the bot's push credential to a dedicated GitHub App, installed only on this repository with `contents: write`, and list **only that App** as a bypass actor. The App's token is minted per run inside the two distribution jobs. A pre-push check in those jobs (already present: the staging allowlist and validated-tree comparison) keeps the App's commits limited to `frontend/public/**`.

Then extend the ruleset:

| Rule | Setting |
|---|---|
| Require a pull request before merging | on (0 required approvals while the founder is the only maintainer; raise later) |
| Required status checks | `backend-postgres-tests (shard 1/4)`, `(shard 2/4)`, `(shard 3/4)`, `(shard 4/4)`, `frontend-tests`, `browser-quality`, `postgres-migrations`, `dependency-audit`, `backend-collection-accounting` |
| Require branches to be up to date | on |
| Bypass | none (A), or the distribution App only (B) |

## Interaction risks

- **React Router acceptance expires 2026-11-13 (EOS-012).** From that date `dependency-audit` fails on every PR. If it is a required check, nothing can merge. Resolve WP-0.4, or a founder re-acceptance, **before** Stage 2.
- **Render auto-deploys `main`.** With Stage 2, a merged PR is still a production deploy. Branch protection does not add a deploy gate. A staging service would (none exists; see WP02_OPERATIONAL_HEALTH.md).

## Verification

- Stage 1: `git push --force origin <sha>:main` is rejected, and deleting `main` is rejected. The next bot preview commit still lands.
- Stage 2: a direct `git push origin HEAD:main` from a non-bypass actor is rejected, and a PR missing a required check cannot merge.
