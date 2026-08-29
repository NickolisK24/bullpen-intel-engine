# CU-06 Main Merge Report

## Verdict

**MERGED SAFELY**

This report records the bounded repository integration of CU-06. The feature
remains shadow-only and cannot publish, invalidate production caches, or change
scheduled authority.

## Repository state

- Feature branch: `feat/incremental-read-models`
- Accepted CU-06 commit: `f21e77ddbc7b326c8bd97a5896c9ce12b49e8a5c`
- Pre-push `origin/main`: `cfa09692a9ef0a32f8179732c80304da7ccd1d33`
- Upstream drift: none; the branch was zero commits behind and one commit ahead
- Remote accepted feature head: `f21e77ddbc7b326c8bd97a5896c9ce12b49e8a5c`
- Pull request: [#773](https://github.com/NickolisK24/bullpen-intel-engine/pull/773)
- Schema changes: none
- Alembic head: one head, `c6d8e1f3a5b7`

The unrelated untracked `BASEBALLOS_DATA_ENGINEERING_INTERVIEW_AUDIT.md`
remained untouched.

## Final local validation

The accepted implementation and the final pre-push pass produced:

- bounded Team Board, League, Matchup, Tonight, CU-05, and scheduling coverage:
  288 passed
- frozen Team Board authority coverage with a disposable SQLite database:
  33 passed
- publication, governance, and scheduling coverage with the same qualified
  database: 487 passed, 1 known Windows shell-path case deselected
- frontend tests: 1,210 passed
- frontend production build: passed
- CI shard verification: 398 files and 9,070 collected tests, each assigned
  exactly once
- Python compilation: passed
- migration-head guard: passed with `c6d8e1f3a5b7`
- tracked diff and whitespace checks: passed

The first publication/governance selection reproduced only the established
Windows `bash -n` path behavior and inherited remote-database safety refusal.
The working-directory-qualified rerun passed. The full backend suite was not
run and is not claimed as green.

## Parity and bounded rebuild audit

The exact accepted 15-game proof was rerun before push:

| Surface | Rebuilt | Mismatches | Result |
|---|---:|---:|---|
| Team Board | 30 | 0 | MATCH |
| League row | 30 | 0 | MATCH |
| Matchup | 15 | 0 | MATCH |
| Tonight entry | 15 | 0 | MATCH |
| **Total** | **90** | **0** | **100%** |

The coupled CU-05 regression comparison remained 3,006 / 3,006. The proof
recomputed 113 Arm Reads and 30 Team States without semantic drift.

The final call graph remains bounded:

- one affected team produces one Team Board and one League-row rebuild
- both teams in one game deduplicate to one Matchup and one Tonight rebuild
- no affected entities produce zero CU-06 calls
- broad builders are used only as separated parity baselines

An unrelated team/game sentinel remained unchanged. No full historical corpus,
all-Team-Board, or broad production rebuild is invoked by the incremental path.

## Surface and authority diff audit

- **Team Board:** the incremental path calls the current frozen Team Board
  authority with additive shadow overrides; default production behavior and
  payload semantics are unchanged.
- **League:** the bounded row and broad listing share the same authoritative row
  projector; ordering and team identity remain unchanged.
- **Matchup:** the current scheduled-game Matchup and bullpen-comparison builders
  remain authoritative; affected games are deduplicated by `gamePk`.
- **Tonight:** the existing read-only Tonight composer remains authoritative;
  CU-06 supplies only bounded shadow inputs and extracts the affected entry.

The PR adds no duplicate baseball calculator and no frontend-derived semantics.
Represented date, data-through date, roster/current membership, currentness, and
partial-data behavior continue to come from the accepted CU-05 result and the
current broad builders. Build time never replaces represented baseball time.

## Hard-stop and safety audit

Static call-boundary and before/after sentinel tests prove that CU-06 stops after
in-memory read-model parity. It does not call or mutate:

- publication or current-public pointer advancement
- current or historical public snapshots
- share artifacts or public serving identities
- What Changed generation or notification delivery
- Redis/CDN/cache-tag invalidation, route revalidation, or object-version rollover
- frontend code or public payload contracts
- Render configuration, cron expressions, GitHub production schedules, polling,
  workers, or daemons

The PR contains no frontend, workflow, Render, migration, or scheduler file.
Existing scheduled publication remains production authority, and CU-06 remains
dormant unless invoked explicitly through proof/developer code.

## Hosted validation

Hosted validation on the final feature head passed:

- PostgreSQL migrations: PASS in both push and pull-request workflow runs
- PostgreSQL backend shards: PASS for all four shards in both runs
- collection/shard accounting: PASS in both runs
- frontend tests and production build: PASS in both runs
- dependency audit: PASS in both runs
- Vercel preview and preview comments: PASS
- Supabase Preview: skipped by its integration, not treated as PostgreSQL proof

The first final-head shard 4 run exposed one historical branch-diff freeze: the
appearance-team guard had no reviewed exception for CU-06's intentional edit to
`bullpen_context.py`. Product tests were green (1,765 passed in that shard), and
the failure named only the changed path. The bounded repair adds the repository's
established exact-path, branch-inert CU-06 approval; it changes no runtime code.
The guard and all 13 CU-06 focused tests then passed together, and the 90 / 90
parity proof remained exact. Both complete hosted reruns then passed shard 4.

## Merge record

- Strategy required: normal merge commit
- Accepted commit ancestry: must remain preserved
- PR merge commit: `4ce99cd508eed68742662834dbbc7056b13777a2`
- Resulting CU-06 `main` head: `4ce99cd508eed68742662834dbbc7056b13777a2`
- Accepted CU-06 ancestry: PASS
- Final feature-head ancestry: PASS
- Remote feature branch retained at:
  `39c9c28d3a79b2102770cc0e758a85df2f0188f4`

PR #773 used a normal two-parent merge commit. No rebase, squash, cherry-pick,
force push, or authorship rewrite occurred.

Post-merge `main` CI run
[33233151548](https://github.com/NickolisK24/bullpen-intel-engine/actions/runs/33233151548)
passed PostgreSQL migrations, all four PostgreSQL shards, collection accounting,
frontend tests/build, and dependency audit. Existing Vercel automation deployed
the merge successfully; no manual deployment or configuration change occurred.

## Evidence boundary and remaining risks

Natural evidence covers the exact 15-game canonical dataset. Current roster and
current-serving composition use controlled real-shape evidence where historical
captures cannot reproduce current roster state. Natural production propagation,
atomic serving replacement, cache handoff, Team Board v2 What Changed generation,
and public Pitcher detail rebuilding remain unproven and outside CU-06.

## Final verdict and action

**MERGED SAFELY.** Leave CU-06 dormant and retain existing scheduled publication
as production authority. The next engineering slice may be CU-07, but it is not
part of this task.
