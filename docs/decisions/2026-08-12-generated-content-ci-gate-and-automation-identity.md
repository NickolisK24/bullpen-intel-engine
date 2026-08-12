# D-053 — Generated-content CI gate, tree-exact validation, and the BaseballOS Automation identity

- **Date:** 2026-08-12
- **Status:** Approved founder decision; repository implementation tracked by CI-003 / #598. **Not production-verified.**
- **Scope:** CI validation, provenance, and permission scope for the automated routed-team preview publication path. No change to baseball semantics, publication authority, snapshot selection, Team State, D-051, D-052, or Vercel configuration.

## Context

The daily sync generates the routed `/team/{ABBR}` preview pages from one trusted
published dashboard snapshot and commits them directly to `main`. The Session 1 audit for
#598 established, from the repository and from read-only GitHub history, that this path
had four separate defects.

**No CI ever validated the generated commit.** The push is made with the default
`GITHUB_TOKEN`, and GitHub does not create workflow runs for pushes made with that token.
Eleven generated commits exist on `main` and none has a CI run. Between
2026-08-08T02:00Z and 2026-08-10T14:00Z `main` advanced exactly three times, all three
generated, and the CI workflow logged no run on the branch at all — roughly sixty
continuous hours in which every state of `main` was a commit no validation process had
seen.

**The job ran no frontend validation of its own.** It installed Python only. There was no
`actions/setup-node`, no `npm ci`, no `npm test`, and no `npm run build` anywhere on the
publication path. The gap was therefore not "validation of the wrong commit" — it was the
absence of any frontend validation at all.

**Automated history impersonated a human.** The commit step configured
`Nickolis Kacludis <nickoliskacludis@gmail.com>`, and GitHub attributed both author and
committer to the founder's account. The canonical Roadmap already records a generated
commit (`b328c917…`) as a human production-verification SHA, which is what that
indistinguishability produces over time.

**Write authority was wider than the work.** `contents: write` was granted at workflow
scope, so four jobs that never touch the repository carried a token that could.

A fifth, quieter defect: the change check `git diff --quiet -- <paths>` cannot see
untracked files, so a newly generated page — a relocated club, a changed abbreviation —
would have read as "no changes" and never been published.

## Decision

### 1. The generated-content job gates itself before the commit exists

Generated repository publication is permitted only through this sequence, in this order,
in one job:

```text
trusted publication
-> generate routed-team preview files
-> generated-delivery gate (fail closed)
-> npm ci
-> npm test
-> npm run build
-> stage exactly the generated delivery paths
-> record the validated tree identity
-> commit under the machine identity, with provenance
-> prove the commit's tree equals the validated tree
-> fast-forward push to main
```

The frontend commands and Node major are mirrored from the canonical CI workflow so the
gate and CI cannot drift into validating different things. No step on this path may carry
`continue-on-error`.

### 2. The guarantee is TREE-EXACT, and is stated as such

BaseballOS does not claim the generated commit SHA was tested before it existed. That
claim would be false: a SHA cannot be validated before it is created. The defensible
guarantee, and the one recorded here, is:

> The filesystem tree that passed the delivery gate, the frontend test suite, and the
> production build is byte-for-byte the tree the generated commit carries.

It is proven, not asserted. A sha256 digest of the generated files is taken before the
frontend gate and recomputed after it; the two must match. The tree object is then
computed from the index with `git write-tree` before any commit exists, and the commit's
`HEAD^{tree}` is compared against it after the commit and **before** the push. A mismatch
fails the job with nothing pushed.

### 3. Delivery integrity is verified; baseball meaning is not re-decided

`backend/scripts/verify_generated_team_previews.py` proves that the filesystem agrees
with what the exporter declared it published: every declared page present and non-empty,
the invalid-team fallback intact, no stale page left behind, receipts present on every
dated claim, one publication snapshot across the whole set, and the withheld set on disk
matching the declared one.

It decides no baseball meaning. It imports no service, no model, and no Flask
application, and a contract test asserts that against its import graph. Team State,
eligibility, snapshot selection, data-through authority, and public copy remain owned by
`export_team_story_pages.py` and `services/team_story_previews.py`. Moving any of them
into CI would create a second publication authority, which is exactly what #598 exists to
prevent.

### 4. Automated repository writes use an explicit machine identity

Automated generated-content commits are authored and committed as:

```text
BaseballOS Automation <baseballoshq@gmail.com>
```

This is a machine identity. It is truthful, it is not a person, it is not a vendor, and it
carries no AI, Claude, Anthropic, or Copilot attribution of any kind. It applies only to
the runtime commit made by the workflow. Human-authored repository work — branches,
implementation commits, documentation, pull requests — remains
`Nickolis Kacludis <nickoliskacludis@gmail.com>`, unchanged. No `.mailmap` exists and none
may be added: a mailmap that rewrote machine commits back to a human would restore the
exact defect this decision closes.

The generated commit additionally carries its own provenance, so `git show` explains the
commit without anyone having to guess:

```text
Workflow-Run, Workflow-Run-Attempt, Source-SHA, Validated-Tree, Snapshot-ID, Data-Through
```

Those values come from the exporter's structured result, never from scraping the rendered
HTML.

### 5. Repository write authority belongs to one job

The workflow default is `contents: read`. `contents: write` is granted to
`static-team-story-preview` and to no other job. No pull-request, actions, deployments,
packages, or id-token scope is requested anywhere.

### 6. Change detection compares the index, not the working tree

Detection happens after `git add` of exactly the generated delivery paths, via
`git diff --cached`. This sees additions, modifications, and deletions alike, closing the
untracked-file blind spot. Staging is never `git add .` or `git add -A`, and the job
refuses to publish if any path outside the generated scope is staged.
`frontend/public/og/baseballos-card.svg` is no longer staged: the generator never writes
it, and including it only widened the commit's blast radius. The file itself is unchanged.

### 7. Push safety is unchanged and remains fail-loud

The push is fast-forward only. There is no `--force`, no `--force-with-lease`, no
`reset --hard`, no automatic rebase, and no automatic merge anywhere on the path. If
`main` advanced while the run was generating, the push is refused and the job fails
loudly. The previously published pages then remain in place and continue to state the
baseball date they actually describe — which is honest, and is the correct outcome. Human
work is never overwritten to publish a preview.

### 8. No recursion mechanism is introduced

Option C gates itself precisely so that nothing has to make the `GITHUB_TOKEN` push
trigger a follow-up CI run. No PAT, no GitHub App, no `repository_dispatch`, no
`workflow_run`, and no self-triggering workflow is added for #598.

## Alternatives considered and rejected for current repository fit

**Option A — deployment artifact only.** The direction #598 states as preferred, and
rejected on evidence rather than preference. The generator requires production
`DATABASE_URL`, `SECRET_KEY`, and `ADMIN_API_TOKEN` and reads the published snapshot from
Postgres, so Vercel cannot build these pages during its own build; handing production
database credentials to a hosting provider's build step would be a materially worse
posture. The only viable shape is generating in Actions and deploying with a Vercel token
via `vercel deploy --prebuilt`, which requires disabling or filtering Git-integration
production deploys — otherwise every human merge would deploy a tree with no team pages
and remove `/team/{ABBR}` from production until the next daily run. That is a second
publication authority plus a new high-privilege credential, and it moves the entire
frontend deployment path into GitHub Actions. Revisit if a read-only Vercel verification
shows the project is already artifact- or CLI-deployed.

**Option B — generated branch and pull request.** Structurally broken here in its natural
form: a pull request opened with the default `GITHUB_TOKEN` does not trigger workflow runs
either, so the naive implementation reproduces the identical bypass wearing a PR-shaped
costume. Making it work needs a PAT or GitHub App, plus branch protection that does not
exist today (`main` is unprotected, so no check is required for any PR, human or machine),
plus auto-merge — that is, granting automation unattended merge authority over `main`,
which is a larger grant than the direct push it would replace. It also inserts daily
publication latency into a freshness-sensitive surface.

**Option C was not selected for being the smallest diff.** It was selected because it is
the only option that closes every #598 criterion without a new credential, without a
second publication authority, without a repository-settings dependency, and without
relying on a Vercel setting nobody has verified — and because tree-exact validation is a
stronger guarantee than the human path currently receives, where CI validates a merge
commit that is already the deployable tip of an unprotected `main`.

## What this decision does NOT change

- **D-051 is unchanged.** Production full-daily execution remains schedule-only and
  first-attempt-only. No manual, local, or legacy-admin daily execution is created,
  enabled, or normalized, and no GitHub Actions rerun authority is granted.
- **D-052 is unchanged.** No automated game-driven write authority, no game-driven
  publication authority, no backfill authority, and no legacy-writer retirement.
- No snapshot selection, Team State, eligibility, vocabulary, or public copy change.
- No Vercel configuration change of any kind.
- `/team/{ABBR}` remains a regenerating distribution surface, not an immutable historical
  Share Artifact. `/share/{public_id}` remains the only permanent citation authority.

## Revisit conditions

- A read-only Vercel verification proves the project already supports artifact or prebuilt
  deployment — Option A becomes worth re-costing.
- Branch protection with required checks is adopted for `main` on its own merits — the
  gate becomes platform-enforced rather than workflow-enforced, which strengthens this
  decision without changing its shape.
- The generated set stops being fully regenerable from trusted publication authority — the
  "repository history is not required" premise would no longer hold.

## Closeout requirement

Merging the implementation does **not** close #598. Closeout requires the next naturally
authorized scheduled run to reach `static-team-story-preview` and produce: a passing
delivery gate, passing `npm test`, a passing production build, a recorded validated tree
SHA, a generated commit authored by BaseballOS Automation whose tree equals that validated
tree, and a successful fast-forward push. The production routed page must then reflect the
expected trusted snapshot, and the Vercel deployment relationship must be verified
read-only. The production daily workflow must not be manually invoked to obtain this
evidence — D-051 forbids it, and manufactured evidence would not prove the scheduled path
works.
