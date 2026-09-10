# SP-09 — Canonical Mutation & Impact Engine Consolidation

## 1. Objective

SP-09 gives every durable BaseballOS mutation one authority-aware route to a deterministic impact plan. It normalizes SP-05 roster/transaction facts, SP-06 pregame changes, SP-07 final facts, and SP-08 live facts; calculates exact affected entities and domains; persists the plan; and enqueues one bounded SP-10 handoff. It does not execute derived intelligence or publication.

## 2. Existing Infrastructure Reused

- SP-01 `SyncRun`, correlation IDs, scopes, stages, and outcome counters remain the execution envelope.
- SP-02 `SyncJob`, active dedupe, leases, fencing, retry, and one-shot workers remain the execution substrate.
- SP-05 through SP-08 mutation tables remain the immutable source facts. SP-09 stores references, not copies.
- CU-03/CU continuous execution remains intact. Its reviewed mutation-scoped team/pitcher sets are the parity baseline; no CU workload, Team State, read-model, or publication service is called by SP-09.
- Existing source observations remain provenance authority.

Reuse disposition: mutation models, runs, jobs, source observations, and CU affected-scope logic are **REUSE/WRAP**. SP-05 direct `REBUILD_TEAM` dispatch is **NORMALIZED** through `PROCESS_CANONICAL_IMPACT`. Existing CU execution is **DO NOT TOUCH** until later activation/parity work.

## 3. Mutation Sources

| Source | Durable input | SP-09 status |
|---|---|---|
| Roster membership | `roster_membership_mutations` | Integrated; SP-05 now dispatches canonical-impact work |
| Transaction correction | `player_transaction_versions` | Normalizable by version ID; direct dispatch remains deferred because roster membership evidence owns active membership effects |
| Pregame context | `pregame_context_mutations` | Integrated; SP-06 now dispatches one context cohort |
| Final game | `final_game_mutations` | Integrated through existing SP-07 job |
| Live game | `live_game_mutations` | Integrated through existing SP-08 job |
| Legacy CU | durable CU canonical-impact checkpoint | Preserved as parity/coexistence evidence; migration to plan rows is deferred |

## 4. Normalized Mutation Contract

`NormalizedMutation` contains source mutation ID, normalized family, original source subtype, authority class, baseball date, optional game/team/pitcher, source observation, old/new fact identity, correction flag, membership type, and any additional exact team/pitcher scope carried by a game- or transaction-level fact. Full source payloads are never copied.

The durable `canonical_impact_plan_mutations` association retains these identities and links every plan to its exact original rows.

## 5. Authority Classes

- `live`: provisional observation; never historical final authority.
- `final`: first official final authority.
- `corrected_final`: later official final correction.
- `roster_authoritative`: official roster or transaction authority.
- `pregame_authoritative`: official pregame context, not final participation authority.

Mixed-authority cohorts are rejected. A final version existing for every game suppresses late live dispatch.

## 6. Mutation Families

- `roster_membership`
- `roster_transaction`
- `pregame_context`
- `live_appearance`
- `final_appearance`
- `final_game_context`

The original subtype remains available, including `pitching_line_corrected`, `appearance_context_corrected`, `probable_starter_changed`, and the SP-05/SP-08 vocabularies.

## 7. Impact Domain Vocabulary

The controlled domains are `workload`, `workload_current`, `rest`, `arm_read`, `team_state`, `team_workload_current`, `deployment`, `role_movement`, `performance`, `rotation_transfer`, `roster_composition`, `organizational_depth`, `bullpen_churn`, `concentration`, `clean_options`, `what_changed`, `pitcher_snapshot`, `team_snapshot`, `game_context`, `matchup_context`, and `read_models`.

These are recomputation obligations, not results.

## 8. Impact Rule Matrix

| Mutation | Authority | Domains |
|---|---|---|
| Live appearance | live | current workload, current team workload, game context |
| Final starter/reliever/line | final/corrected final | workload, rest, arm read, Team State, deployment, role movement, performance, rotation transfer, concentration, snapshots, game context, What Changed, read models |
| Final appearance-context correction | corrected final | deployment, role movement, performance, game context, snapshots, What Changed, read models |
| Final game context | final/corrected final | rotation transfer, game context, team snapshot, What Changed, read models |
| Active roster membership | roster authoritative | roster composition, bullpen churn, clean options, Team State, snapshots, What Changed, read models |
| 40-man/organizational membership | roster authoritative | organizational depth, snapshots, What Changed |
| Transaction version | roster authoritative | roster composition/depth/churn and evidence snapshots; it does not independently assert active membership |
| Pregame context | pregame authoritative | game context, matchup context, read models |

## 9. Live vs Final Rules

Live work is deliberately narrow and provisional. It cannot schedule official performance, role history, daily closure, or final workload domains. Final work uses SP-07 authority and may schedule the full derived set. When final work follows live work, the final plan records `supersedes_live`, links the latest live plan, and marks it superseded. A late live cohort after current final authority produces a successful plan with no domains and no SP-10 job.

## 10. Roster Rules

Active membership opens/closes affect active bullpen composition and Team State inputs. Forty-man and other depth membership affects organizational depth without forcing Team State. Transaction versions remain evidence of movement; current membership still requires SP-05 authoritative roster reconciliation.

## 11. Pregame Rules

Probable-starter/context changes affect only game, matchup, and read-model context. They never trigger workload, rest, roster, or Team State by themselves.

## 12. Final Game Rules

Final appearance facts have exact game/team/pitcher scope. Game-level facts recover both official teams from the referenced final-game version. PBP mutations retain their source-provided affected scope. One game with many appearance mutations becomes one plan and one downstream job.

## 13. Corrected Final Rules

`pitching_line_corrected` recalculates line-dependent workload/performance/team domains but never roster composition. Context-only corrections avoid workload. Only entities present on changed mutation rows, plus required game-level teams, are included.

## 14. Impact Plan Model

`canonical_impact_plans` stores a unique SHA-256 plan fingerprint, rules version, authority, baseball date, correlation, deterministic JSON arrays of affected entities/domains/source observations, status, live-supersession metadata, run, dispatched job, and timestamps. `canonical_impact_plan_entities` supplies indexed game/team/pitcher lookup. Status is `planned`, `dispatched`, or `superseded`.

## 15. Cohort / Coalescing

One incoming job is one logical mutation cohort: final-game generation, live observation, roster observation, or pregame context version. Entity and domain sets are sorted unions. Duplicate mutations and entities collapse. A final game therefore cannot enqueue one team rebuild per pitcher.

## 16. Affected Entity Contract

Affected games, teams, and pitchers come from durable mutation rows and referenced canonical versions—not current roster inference. Corrected pitcher lines remain one-pitcher/one-team/one-game scope. Association rows make operator lookup queryable without JSON operators.

## 17. Rules Version / Fingerprint

Rules version is `canonical-impact-v1`. The fingerprint hashes the rule version, authority, sorted `(family, mutation ID, subtype)` inputs, sorted entity sets, and sorted domains. The unique database constraint makes plan creation idempotent and concurrency-safe. A future replay under changed rules must use a new explicit rules version.

## 18. Queue Flow

Input job: `process_canonical_impact`, payload schema 1, deduped by the producer's logical observation/version cohort.

Output job: `process_derived_intelligence`, payload schema 1, priority 60, deduped by plan fingerprint. It carries plan ID, rules version, authority, affected games/teams/pitchers/domains, baseball date, and correlation ID. Plan creation and enqueue occur in one transaction. Empty or stale-live plans enqueue nothing.

## 19. CU Parity / Coexistence

CU remains operationally unchanged. SP-09 reuses its core invariant: canonical reconciliation reports mutation-scoped pitcher/team IDs, and downstream work must consume only those sets. Tests compare a many-reliever final cohort with CU's `_canonical_impact_from_game_outcome` projection and require equivalent team/pitcher scope. SP-09 intentionally differs by retaining authority, mutation references, domain intent, and one durable plan; CU continues to own its existing execution chain until later migration.

## 20. Out-of-Order / Supersession

Before dispatching live work, SP-09 queries current SP-07 `FinalGameVersion` authority for every game. Current final authority is the per-game watermark. Late provisional work is retained as a superseded zero-domain plan, so it cannot regress final truth. Final plans link and supersede the latest related live plan.

## 21. Failure / Concurrency

Source mutations are never rolled back by impact failure. Plan insertion uses a unique fingerprint inside a savepoint; concurrent workers converge on one plan. SP-02 claim-token heartbeats fence the job immediately before planning and again before commit, so a stale owner cannot dispatch. Plan creation, references, entity scope, and downstream enqueue commit together; retry is safe.

## 22. Database / Index Design

Migration `c1d4e7a9b2f6` adds only the three SP-09 tables. Indexes cover date, authority, correlation, SyncRun, source mutation, observation, and entity lookup. Bounded sorted arrays remain JSON because they are read as a plan payload; query-critical entity membership is normalized. The migration is additive, preserves existing mutations, performs no guessed backfill, and downgrades cleanly.

## 23. Explicit Non-Goals

SP-09 does not compute workload, rest, arm reads, Team State, deployment, roles, performance, rotation transfer, snapshots, What Changed content, read models, or publication. It does not alter acquisition, production scheduling, frontend/API behavior, or broad Statcast scope.

## 24. SP-10 Handoff

SP-10 consumes only `process_derived_intelligence` and loads the durable plan. It receives exact entities, domain obligations, authority, baseball date, correlation, and rules version without needing source-specific mutation-table knowledge. SP-10 must execute dependencies coherently, replace provisional inputs with final truth, and preserve existing governed baseball semantics.

## 25. Acceptance Checklist

- [x] One normalized, authority-aware mutation contract covers SP-05 through SP-08.
- [x] Original mutation subtypes and source provenance remain durable.
- [x] One versioned rule matrix produces controlled domain obligations.
- [x] Entity scope is exact, deduplicated, deterministic, and queryable.
- [x] Multiple mutations coalesce into one idempotent plan and one SP-10 job.
- [x] Live, final, corrected final, roster, and pregame boundaries are distinct.
- [x] Current final authority suppresses stale live dispatch.
- [x] SP-05 and SP-06 now enter the common impact route.
- [x] CU scope parity is tested and CU execution remains untouched.
- [x] PostgreSQL uniqueness, downstream dedupe, and worker fencing use SP-02 contracts.
- [x] No derived calculation, publication, scheduler, frontend, or public semantic change is included.
