# BaseballOS Changelog

This changelog summarizes major product, governance, rollout, and operational
milestones. It does not replace the detailed evidence records linked from
[docs/README.md](../README.md).

## August 14, 2026 - One Team Page, One Bullpen Claim (H-8)

- A `/team/{ABBR}` page publishes two projections of one publication: the social
  unfurl a crawler stores and the small body a scriptless reader sees. They were
  selected independently — the metadata from a canonical story, the body from
  the published Team Board — under one shared snapshot receipt, with nothing
  comparing them. A page could therefore tell a social platform the bullpen was
  "Fresh with seven close-game options" while telling the reader "Vulnerable, 5
  relievers are Unavailable", both stamped with the same snapshot id, and a
  story representing an earlier date could sit beneath a later data-through
  stamp. Both were reproduced from deterministic fixtures before any fix.
- The published Team Board now owns the page's claim. Every receipt field, the
  Team State and the baseball point come from it. A canonical story may still
  word the unfurl (DIST-003 / #594), but only when it agrees with that claim:
  the story must be for this team, represent this data-through date, and name no
  Team State other than the one published. When it disagrees the page falls back
  to the board's own governed wording and records why — `story_team_mismatch`,
  `story_represented_date_mismatch`, or `story_team_state_conflict` — rather
  than withholding a valid dated read from the reader.
- Made the agreement checkable on the artifact, not just in the generator. Each
  dated page now declares the one Team State it publishes, the body element
  carries the state it rendered, and the fail-closed delivery gate proves both
  projections against that single declaration before anything reaches `main`.
  Honest limit: unfurl copy that names no Team State is permitted, because
  canonical story sentences often name none, so the gate catches contradiction
  rather than silence.
- Verified across a 30-team publication covering every Team State, limited
  reads, agreeing stories, contradicting stories, stale-dated stories,
  cross-team stories, and teams with no story. No production run was performed
  and no daily workflow was triggered; the corpus is synthesized fixtures.
- No threshold, Team State formula, availability, Read Confidence, pitcher
  classification, roster-authority, story-eligibility, or publication-gate
  change. Determinism unchanged: repeated renders of one publication are
  byte-identical, and `generated_at` moves without touching the baseball claim.

## August 14, 2026 - Generated Bullpen Copy Made Evidence-Specific (H-7 / H-9)

- Team previews now select the evidence that explains the state. The board
  publishes its governed reasons in a fixed order whose first entry is always
  the available-count sentence, and the preview took that first entry — so
  three clubs in three different Team States all read "3 available", and the
  chosen sentence was also the one carrying provenance inside a baseball claim.
  The preview ranks the reasons the board already authored, most
  state-discriminating first: a stated Unavailable count, then On Watch, then
  the meaningful zero, then the bare available count. Nothing is composed, no
  count is recomputed, and no new metric was added. Ties resolve to the board's
  own published order, so selection stays deterministic.
- Fixed the story time framing. One prefix served both in-game narratives and
  post-game state, which made "After their most recent game, Merrill Kelly
  worked 6.0 innings" — he worked them in the game. In-game sentences take an
  in-game framing, and a sentence that already names the starter and his
  innings carries no prefix at all, because it has located the game itself.
  Measured across 72 rendered stories, the share opening with one identical
  clause fell from 61% to 11% and distinct openers rose from 8 to 25. The same
  anchoring rule applies to the morning brief's one-sentence recap, which names
  the club and the outcome and so locates the game by itself.
- Fixed the What Changed context sentence. Its secondary phrases are
  independent clauses ("coverage also stabilized"), so they could not follow
  "including", which needs a noun phrase — that produced "...including coverage
  also stabilized." The multi-item frame introduces the clause with a colon
  instead. The frame is chosen to fit the phrase's grammatical shape; the
  rendered sentence is not repaired afterwards.
- **No randomness was introduced.** Variant selection remains hash-of-evidence
  based, and a structural test refuses `random` in the writers. Determinism is
  proved directly: identical input yields byte-identical bodies, headlines and
  What Changed context across repeated runs.
- No threshold, Team State, availability, confidence, roster-authority,
  publication-gate, or schema change. No immutable artifact was regenerated.

## August 13, 2026 - Public Copy Follows Canonical Ownership (H-5 / H-6)

- Removed the frontend's public-copy rewriting. Three components carried chained
  regex tables that rewrote already-authored public sentences on their way to
  the reader — `Monitor` to `On Watch`, `Avoid` to `Unavailable`,
  `deterministically` to `consistently`, `endpoint` to `data feed`, and more.
  That made the browser a second author of BaseballOS claims, and on the
  availability usage-check card it meant the blocked-framing guard scanned copy
  the browser had already repaired.
- Moved each sentence to its semantic owner, with the reader-visible wording
  unchanged: the landscape grouping note is authored in
  `services/game_context.py`, the Today watch note reads `stretched` rather than
  the engine's `constrained` in `services/tonight_candidate_selection.py`, and
  the usage-check framing uses the public `Unavailable` label and drops the
  `Backtest` tooling word in `services/availability_backtest.py`. A repository
  sweep confirmed these were the only public *sentences* carrying engine
  vocabulary; every other match is a structured engine key, which
  `services/public_bullpen_copy.py` already documents as legitimately exempt.
- Kept every fail-closed guard. Prohibited framing — prediction, betting,
  accuracy, ranking, internal tooling — is still detected and **withheld**, and
  the guards are now stronger because they inspect exactly what the backend
  published instead of a browser-repaired copy.
- Humanized internal language that was reaching readers: "no bullpen situation
  cleared the BaseballOS publication standard" became "no bullpen read is ready
  to publish yet", and the completed-game-context empty states became plain
  baseball sentences. Removed the dead `governance metadata` display mapping,
  which invented the internal-sounding label "decision boundary detail" for a
  key no backend module emits.
- Corrected glossary drift. `Clean Option` no longer defines itself with the
  word "clean", and the availability definitions drop "current workload
  classification" and "governed roster context". The surface label `Workload
  Read` is now `Read Confidence` across all eight surfaces, matching the family
  the Product Experience Standard names and requires to appear under its own
  field label; readers previously saw a label the glossary never defined.
- No threshold, Team State, pitcher-read, availability, or generated-copy
  behavior changed, and no layout changed.

## August 13, 2026 - Freeze Guards Narrowed To Protected Surfaces (H-1)

- Narrowed the four branch-diff behaviour-freeze guards so they refuse the
  surfaces they name instead of two whole directories. No product code, public
  copy, vocabulary, schema, migration, or authority posture changed; this is a
  change to what CI permits, not to what the platform does.
- Removed the blanket `frontend/` and `backend/migrations/` path clauses, and
  the substring matching in the appearance-team guard. A directory is not an
  invariant: the prefixes swept in files no freeze owned, and the only way past
  was a hand-maintained allowlist. Thirty-four had accumulated in one guard.
  Two failures made the cost concrete — deleting five UI components that
  nothing imported required editing four backend allowlists, and archiving
  `docs/phase0g/public_team_relief_work_panel.md` tripped a *runtime surface*
  guard because a markdown filename contained a protected service's name.
- The protected catalogues now live in `backend/tests/freeze_policy.py` as
  exact paths plus `backend/api/`, which is a public-surface boundary in its
  own right. Matching is whole-path or anchored path-prefix, never substring.
- Deleted every historical allowlist. Each existed because some past branch
  changed a protected path; all of those branches merged, so the paths are in
  `origin/main` and can no longer appear in a future branch diff. They were
  protecting nothing forward-looking.
- Every real invariant is preserved and several are now stronger. The frozen
  legacy What Changed paths, the frozen public routes, the Phase 0E legacy
  public surface, and Team State / Share Artifact ownership all still fail
  closed — including `WhatChangedCard.jsx`, the one genuinely frozen frontend
  file. Route registration and the admin gating of the internal system routes
  are now asserted on every run rather than only when a branch diff happened to
  touch them and that change was allowlisted.
- Pinned the result both ways in `backend/tests/test_freeze_policy.py` and
  `backend/tests/test_freeze_guard_behavior.py`: unrelated frontend files,
  unrelated migrations, and archived filename collisions are accepted, while
  frozen paths are still refused. A regression test refuses to let
  `frontend/`, `frontend/src/`, `frontend/public/` or `backend/migrations/`
  return as a protected prefix.

## August 13, 2026 - Dependency Remediation And Standing Audit Gate (DEP-001)

- Closed DEP-001 (#601) across four bounded slices, verified on `main` at
  `e3ad8bd` by CI run `31729458591`. No baseball semantics, publication gate,
  source authority, runtime configuration, production data, or game-driven
  authority posture changed.
- Upgraded the advisory-bearing backend request-path packages in one reviewed
  pass (PR #643): Flask 3.0.0 → 3.1.3, Flask-CORS 4.0.0 → 6.0.5, gunicorn
  21.2.0 → 23.0.0, requests 2.31.0 → 2.34.2, python-dotenv 1.0.0 → 1.2.2.
  CORS behaviour was pinned by regression tests **before** the upgrade and
  re-verified after it. The origin allowlist is unchanged and
  `supports_credentials` remains disabled — credentials were never enabled,
  which is what bounded the Flask-CORS advisory class in the first place.
- Removed `pytest` from the production runtime (PR #644). `backend/requirements.txt`
  is now the runtime set and `backend/requirements-dev.txt` pulls it in and adds
  `pytest`, so a development environment is a superset of production rather than
  a different resolution. Nothing under `backend/` imports `pytest` outside
  `backend/tests/`. Production had been installing a test-only package, and its
  advisories, for no runtime benefit.
- Removed the unused frontend packages `recharts` and `clsx` and patched
  `react-router-dom` to 6.30.4 (PR #646). Both removed packages had zero import
  sites; deleting `recharts` removed the only **high**-severity production
  advisory, because `lodash` entered the graph solely through it. **No override
  and no direct pin was added** — the dependency carrying the advisory was
  deleted instead. `npm audit --omit=dev` went from 4 advisory rows to 2.
- Recorded the three residual React Router advisories — GHSA-wrjc-x8rr-h8h6,
  GHSA-jjmj-jmhj-qwj2, and GHSA-337j-9hxr-rhxg — as an explicit, **time-boxed**
  acceptance expiring **2026-11-13**, tracked by issue #645. None has a fix in
  the 6.x line; npm's only offered remediation is a breaking major version, and
  the v7 migration is blocked on the frontend test harness rather than on the
  router. The SSR-hydration advisory does not apply to this client-only SPA, and
  the open-redirect classes are bounded at the single URL-derived navigation
  sink by `safeVerifyRedirect()`. **Its regression tests are part of the
  acceptance: deleting or weakening them voids it.**
- Added a standing `dependency-audit` CI job (PR #647). It audits the backend
  runtime requirements file with a pinned scanner and checks frontend production
  findings against `.github/dependency-audit-accepted.json`. Dev/build advisories
  are informational and never gate the build.
- The gate refuses a build when a production advisory is unknown, expired,
  mismatched against the package npm attributes it to, duplicated, or missing
  required metadata — and **also when an acceptance no longer corresponds to
  anything reported**, so a solved advisory's exception must be deleted rather
  than left behind where it would silently suppress a recurrence. Scanner and
  network failures are distinguished from a clean audit rather than passing
  quietly.
- **The gate is read-only.** It never upgrades, pins, or edits a dependency, and
  no auto-upgrade or auto-merge path was created. It reports and refuses; a
  human decides the remediation. Its behaviour is covered by
  `backend/tests/test_dependency_audit_gate.py`, which tests the evaluator
  directly and asserts the workflow contract, so the job cannot be quietly
  weakened without a failing test.
- Auditing declared requirements rather than the installed environment is
  deliberate: it measures what production actually ships instead of the CI
  runner's own tooling.
- The current boundary and its standing obligations are recorded in
  `docs/current/DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md`; the accepted-risk
  reasoning is in
  `docs/decisions/2026-08-13-react-router-v7-security-defer.md`.

## August 2026 - Daily Sync Runtime-Budget Incident (OPS-002)

- Merged the daily-sync runtime-budget incident investigation through PR #619.
  Four full daily syncs on August 6 were examined from their original job logs.
  Three dead-lettered publication-critical GameLog work — 746, 741, and 732
  pitchers of 861 — and the one that succeeded behaved as a warm second pass 30
  minutes after a failure. Corrected root cause: five upstream stages consume
  612–628 seconds before the combined ingestion pool is calculated, the pool
  that remains is 151–168 seconds, the game-driven shadow observer consumes part
  of it, and the legacy GameLog writer received **112.7–124.6 seconds** for work
  whose corrected cold-equivalent upper bound is **767–895 seconds**. Roster
  statuses and transactions alone are ~77 % of the cold upstream block, and
  roster work is duplicated across two stages at 240 endpoint calls per run.
- Recorded that fail-closed publication behaved **correctly** throughout.
  Candidates `359`, `361`, and `362` were withheld; snapshot `358` and then
  `360` remained the trusted served snapshot. The platform was safe but frozen,
  and the changelog states that distinction rather than reporting it as healthy:
  Dashboard freshness froze, Team Board and Compare live reads degraded against
  incomplete rows, and Tonight did not refresh on any failed run.
- Implemented the bounded OPS-002 immediate mitigation (#620). The daily
  internal budget rises 1080 → 2200 seconds, the shell timeout 20m → 40m, the
  `public-sync` job timeout 40 → 60 minutes, and the combined ingestion cap
  720 → 1500 seconds. **The 300-second final-phase reserve is unchanged** — the
  final phase genuinely needs it. At the maximum observed upstream this yields a
  combined pool of 1271.5 seconds and a conservative legacy GameLog floor of
  **953.625 seconds** against a 950-second requirement. The 1500-second cap is a
  safety ceiling above the derived pool, not a promised GameLog allocation, and
  it does not bind under any observed upstream timing.
- Added an explicit five-quantity runtime reporting contract, because one field
  had been carrying three meanings and that ambiguity produced a materially
  wrong first reading of the incident. The daily status, the durable
  `daily-sync-summary.json`, and one log line emitted immediately before the
  legacy writer now report the configured cap, the combined pool, the shadow
  lane's configured allocation, its **actual** elapsed time, and the resulting
  legacy GameLog remainder as five distinct values. Every pre-existing budget
  field is retained unchanged.
- Corrected the shadow lane's exception-path accounting. A lane that raised
  previously returned the untouched pool, so the legacy writer could be told it
  had time the run had already spent. Its measured wall clock is now charged.
  The failure remains fail-soft: it does not abort `public-sync`, does not by
  itself fail publication, writes nothing, advances no checkpoint, and changes
  no authority.
- Added focused runtime tests for the mitigation formula, the 950-second floor,
  five-quantity separation, unused-time return, the lane-off path, the exception
  path, and the non-negative guarantee; and replaced the pinned 20m/40-minute
  workflow invariants with OPS-002 invariants that additionally prove no cron,
  mode, concurrency, permission, postgame-timeout, backfill, advisory-step, or
  retry change rode along.
- **No cron, manual mode, concurrency, permission, migration, schema,
  publication-gate, mode, or authority change.** No retry and no continuation
  mechanism was introduced. Daily and postgame lanes remain shadow, backfill
  remains off, and the legacy writer remains authoritative.
- **Production proof is pending.** Merging the mitigation is not proof. OPS-002
  (#620) remains open until one separately authorized controlled manual recovery
  run and then three consecutive scheduled daily runs each complete with zero
  budget exhaustion, zero publication-critical failures, a published, selected,
  and served candidate, passing appearance-ledger and dashboard-cache proofs,
  and shadow still zero-write. The permanent work-reduction correction —
  candidate prefiltering, incremental roster sync, incremental transaction
  sync — is deliberately **not** implemented and remains separate follow-up
  work; this mitigation masks the inefficiency rather than removing it.
- Paused the #593 scheduled observation window without closing, weakening, or
  absorbing it. Its separation behaved correctly during the incident; the pause
  exists because failed runs skip `internal-enrichment` and
  `static-team-story-preview`, polluting the evidence it needs.

## August 2026 - Authority, CI, And Public Vocabulary Closeout

- Completed PROD-001 (#592) after PR #588 and scheduled production run
  `30921186222` proved the full
  `github_actions_morning:schedule_coherence` provenance value persists and
  reads back correctly. The 14:00 UTC lane completed, Tonight verification
  passed, the appearance ledger reconciled 120 of 120 completed games and
  1,029 of 1,029 appearances with zero mismatches, and the dashboard snapshot
  cache verified successfully.
- Separated trusted `public-sync` success from experimental shadow activation
  health through PR #602. Issue #593 is implemented, but remains open until its
  required scheduled observation window proves the separated signals remain
  useful in normal production operation.
- Corrected D-044 publication scope so shadow-only missing work items remain an
  observation backlog rather than a baseball publication blocker. Genuine
  finality, schedule-authority, appearance-row, and material-correction deficits
  remain fail-closed. Daily and postgame remain shadow, backfill remains off,
  and production write/publication authority has not transferred.
- Partitioned the complete backend PostgreSQL confidence gate into four
  deterministic isolated shards through PR #609, with checked-in ownership and
  collection accounting proving every backend test is assigned exactly once.
- Completed CI-001 (#599) through PR #610. Frontend CI now installs from the
  committed lockfile with `npm ci`, keeps the lockfile unchanged, runs the full
  frontend test suite, and requires the production Vite build. Trust-critical
  behavior-freeze tests now receive full Git history so they execute instead of
  silently skipping when `origin/main` is unavailable.
- Merged UX-001 (#590) through PR #611 at merge commit
  `8a528efec1affcdaf98fa1e87f9090d105db4248`. Dashboard, Team Board, Compare,
  and named Dashboard landscape entries now consume the backend-owned Team State
  contract for exactly Fresh, Stretched, and Vulnerable. The frontend validates
  and renders the supplied contract rather than deriving a competing state from
  counts, lanes, or `context.health`.
- Kept #590 open after that merge pending production proof. Production then
  exposed a further defect and the issue was closed only after the correction
  below; this line records the state at PR #611, not the terminal status.
- Preserved the issue boundaries: #591 still owns frontend rewriting or dropping
  backend-authored Why copy, and #594 still owns routed/static team-page
  ownership, metadata, and freshness. PR #611 does not complete either issue.
- Closed the obsolete simulation-output README issue #5 as not planned because
  BaseballOS is a bullpen-intelligence product, not the former simulation
  direction described by that issue.
- Added a manual, exact-scope, read-only audit package for the game 824487
  source-revision mismatch observed between scheduled daily runs `30902544622`
  and `30999087370` (D-047). The production audit was executed on August 5, 2026
  as run `31044299167`, returning
  `COMPLETE_SCOPE_AND_MATERIALITY_IDENTIFIED_FIELD_DELTA_UNAVAILABLE` at exit 0
  with no failed and no unproven reasons: root condition
  `official_appearance_set_changed`, current materiality
  `non_material_to_canonical_writer_target`, checkpoint state
  `checkpoint_stale_relative_to_current_source`. The audit identified the
  condition and authorized no repair of its own. See
  [GAME_824487_SOURCE_REVISION_AUDIT.md](../archive/2026-08/GAME_824487_SOURCE_REVISION_AUDIT.md).
- Corrected and terminally closed the game 824487 source-revision checkpoint
  through PR #615 at merge commit
  `b29b1f0e41fffb0a58db9d276a506ae6613dfcce`, then retired the single-purpose
  capability (D-048). Three production runs completed the operation: verify run
  `31065643787` returned `VERIFIED_REPAIR_REQUIRED_AND_SAFE` with no mutation;
  apply run `31065894573` returned `REPAIR_APPLIED`, moving
  `game_ingestion_work_items` row `id = 103` (`mlb_game_pk = 824487`) from
  source revision `90213dc8…d138b804a0` to `a0fe2dbc…f97f241ecf4` — exactly one
  row, exactly one governed column plus the automatic `updated_at` bookkeeping
  timestamp; and run `31066123772`, whose **selected operation was `apply`**,
  returned `REPAIR_NOT_REQUIRED` at exit 0 with the apply gate closed, zero
  commits, and zero durable write attempts, because the already-applied safety
  gate resolved it before the writable path opened. No GameLog row changed, no
  other work item changed, no migration was added, and no mode or authority
  moved. The workflow, runner, service, tests, implementation document, and CI
  shard registrations were removed by PR #616, merged August 6, 2026; the
  capability is retired and the workflow must not be dispatched again.
  Daily and postgame remain shadow, backfill remains off, the legacy writer
  remains authoritative, and writes and publication authority remain unapproved.
- **Closed UX-001 (#590) on August 6, 2026.** Production validation after PR
  #611 showed every supported team collapsing to `Vulnerable` across materially
  different Dashboard lanes — Detroit read `Vulnerable` while showing eight
  rested and available arms. The vocabulary contract was correct; the
  population was not. Readiness distributions were built from every pitcher
  carrying a fatigue row and flagged active, including starters and
  injured-list arms, while the trust metadata authorizing the same read used
  the canonical current active bullpen, so a single arm outside the bullpen
  forced the whole club stressed. PR #617, merged at
  `d5ddb5fd56651203edf75de40d7f3f0d2630fa4b`, resolves active-bullpen
  membership once and uses it for both the distributions and the coverage
  check. Corrected production run `31097712768` published, selected, and served
  snapshot `360` with data through August 5, 2026: publication-critical work
  418 / 418, best-effort 443 / 443, appearance ledger 124 / 124 completed games
  and 1,049 / 1,049 appearances with zero mismatches, and dashboard cache
  verification passed. Team Board showed Los Angeles Dodgers and Houston Astros
  `Stretched`, New York Mets `Vulnerable`, and Colorado Rockies rendering the
  governed unavailable presentation with no invented fourth Team State; Compare
  showed Atlanta Braves `Stretched` beside New York Mets `Vulnerable`, both
  `Published View Current` through August 5. No team naturally qualified as
  Fresh after all 30 clubs played that day, so under D-049 no current Fresh
  screenshot exists and none was manufactured — the automated contracts remain
  the proof that `operationally_stable` maps to `Fresh` and that the public set
  contains exactly three labels. A future natural Fresh capture is supplemental
  evidence. The daily lane stayed shadow with zero writes, commits, checkpoint
  advances, or publication authority, and no threshold, formula, mapping,
  schema, mode, writer, or publication authority changed. #591, #593, and #594
  retain their independent acceptance criteria.

## July 2026 - Canonical Trust And Ingestion Foundation

- Established the six-document canonical library covering Constitution,
  Bullpen Intelligence, Product Experience, Architecture and Operations,
  Product Roadmap and Decision Ledger, and Editorial and Distribution.
- Closed Foundation 3A / Phase 0 after independent production proof of official
  pitching-line completeness, unique starter authority, recorded-outs
  authority, appearance-team history, and exact 30-team reconciliation.
- Established the Current Active-Pen Performance family and fully specified
  M-001 Active Bullpen ERA, including the 108-recorded-out sample gate, exact
  integer-outs formula, two-decimal half-up rendering, below-sample wording,
  group membership, contributing-arm counts, and four evidence levels. Public
  implementation remains paused behind higher-priority trust and product
  correctness work.
- Completed the Foundation 3C governed ingestion bootstrap and rollout closeout,
  reconciling 109 governed final games and 946 appearance rows without granting
  automated write or publication authority.

## June 2026 - Bullpen Trust And Data Quality Cleanup

- Fixed default bullpen roster composition so clear starters are excluded from
  default bullpen planning.
- Added roster-status authority from MLB Stats API roster endpoints and
  normalized current roster states into BaseballOS vocabulary.
- Added MLB team-assignment authority and stale ownership correction so
  reassigned, released, no-organization, or unresolved pitchers do not remain
  attached to stale team boards.
- Separated unavailable pitchers from active bullpen arms and replaced old
  inactive/context wording with roster reasons.
- Aligned Player Detail final availability with Bullpen Board cards while
  keeping workload signal visible separately.
- Added Pitcher Search V1 as database-backed, team-agnostic pitcher discovery
  by name, using stored current team assignment, roster status, and final
  availability without rankings, recommendations, or predictions.
- Documented current limitations: transaction-event lineage is not yet
  persisted, real-world roster state can move between syncs, and bullpen
  eligibility can still use role/usage evidence where explicit role authority is
  unavailable.

## June 2026 - Documentation Structure Refactor

- Refactored README into a concise project front page.
- Added [docs/README.md](../README.md) as the documentation hub.
- Added [docs/ROADMAP.md](ROADMAP.md) for planning context.
- Added this changelog for historical milestone summaries.
- Added [governance/CERTIFICATION_LEDGER.md](../governance/CERTIFICATION_LEDGER.md)
  for certification and rollout status.
- Added [operations/OPERATIONAL_REVIEWS.md](../governance/OPERATIONAL_REVIEWS.md)
  for operational review and monitoring evidence summaries.

## V5 - Bullpen Intelligence Surface

- Phase 1 approved the Bullpen Intelligence Surface capability definition as a
  planning-only governed observation layer.
- Phase 1 recorded allowed observation scope, prohibited outputs, trusted
  source requirements, freshness and confidence requirements, fail-closed
  requirements, certification requirements, rollout sequence, and readiness for
  Phase 2 observation taxonomy planning.
- Phase 2 approved the observation taxonomy, including authorized observation
  families, approved inputs, future output requirements, governance boundary
  matrix, language rules, fail-closed requirements, and readiness for Phase 3
  architecture definition.
- Phase 3 approved the architecture definition, including the observation
  lifecycle, domain architecture, builder architecture, evidence architecture,
  trust architecture, severity architecture, fail-closed architecture,
  frontend surface architecture, governance protection layer, and readiness for
  Phase 4 observation domain and contracts.
- Phase 4 implemented the backend observation domain and contract foundation,
  including governed enum vocabularies, dataclass contracts, serialization
  helpers, contract validators, prohibited-language safeguards, collection
  serialization, and focused backend tests.
- Phase 5 implemented deterministic backend observation builders, static
  supplied-state inputs, fail-closed suppression, evidence propagation, trust
  and freshness propagation, collection assembly, and focused backend tests.
- Phase 6 implemented the backend read-only observation API surface, including
  `GET /api/observations`, `POST /api/observations/preview`, deterministic
  supplied-state assembly, fail-closed API responses, governed serialization,
  route registration, and focused API tests.
- Phase 7 implemented the frontend read-only Bullpen Intelligence surface,
  including `GET /api/observations` client normalization, Dashboard panel
  rendering, evidence, limitations, trust, freshness, confidence, explanation
  references, empty/protected states, API failure handling, and focused
  frontend tests.
- Phase 8 certified the combined V5 governance boundary across contracts,
  builders, read-only API, frontend surface, documentation, fail-closed
  behavior, trust, freshness, confidence, and prohibited behavior safeguards.
- Phase 9 approved controlled rollout for the certified V5 Bullpen
  Intelligence Surface after reviewing contracts, builders, read-only API,
  frontend rendering, documentation, tests, fail-closed behavior, trust,
  freshness, confidence, and preserved governance flags.
- V5 Phase 9 keeps full production rollout unapproved and does not authorize
  backend decision logic, database migrations, live runtime integration,
  runtime observation generation from MLB data, ranking, selection, pitcher
  recommendations, matchup advice, best-arm language, role advice, prediction,
  or automated decision-making.
- Phase 10 completed production rollout review and retained full production
  rollout as not approved because retained controlled-rollout monitoring,
  production browser, accessibility smoke, fail-closed, governance-copy, and
  preserved false-flag evidence is incomplete.
- Phase 11 retained manual production evidence for API behavior, frontend
  rendering, governance copy, accessibility smoke, fail-closed behavior,
  controlled rollout observation, and preserved false governance flags. Phase
  11 clears the Phase 10 production evidence blocker and records readiness for
  Phase 12 full production rollout approval review without approving full
  production rollout.
- Phase 12 approved full production rollout for the certified V5 Bullpen
  Intelligence Surface after reviewing Phase 8 governance certification, Phase
  9 controlled rollout approval, Phase 10 production review, and Phase 11
  retained production evidence. Future runtime integration, observation-family
  expansion, ranking, selection, prediction, pitcher advice, matchup advice,
  manager advice, and automated decision-making remain outside the approval.

## V4 - Evidence And Explanation Layer

- Phases 1 through 8 defined, implemented, reviewed, and certified internal
  backend Availability Explanation Integration.
- Phases 9 through 13 defined, implemented, reviewed, and certified internal
  backend Team Operations Readiness Explanations.
- Phases 14 through 17 planned, implemented, reviewed, and certified the
  internal backend Explanation API layer for certified explanation types.
- Phases 18 through 21 planned, implemented, reviewed, and certified governed
  frontend explanation surfaces.
- Phases 22 through 26 planned controlled rollout, retained observation
  evidence, reassessed production readiness, and approved full production
  rollout for certified V4 frontend explanation surfaces.

## V3 - Team Operations Bullpen Readiness

- Phase 1 completed neutral product capability review and selected Team
  Operations Bullpen Readiness as the next product direction.
- Phases 2 through 4 defined the capability, implementation plan, API contract,
  certification requirements, allowed outputs, prohibited outputs, and
  governance boundaries.
- Phase 5 implemented the backend domain foundation with deterministic
  readiness assembly, metadata contracts, fail-closed behavior, and tests.
- Phase 6 added the internal, non-production readiness route with governed
  request validation.
- Phase 7 reviewed the internal route and classified it as ready for frontend
  integration planning.
- Phase 8 planned governed dashboard integration.
- Phase 9 added frontend client normalization and contract tests without
  dashboard rendering.
- Phase 10 added the internal dashboard panel with summary-first rendering,
  metadata visibility, and expand-on-demand evidence.
- Phase 11 reviewed dashboard UI certification readiness.
- Phase 12 created the formal certification plan and rollout prerequisites.
- Phase 13 completed formal certification review and classified the feature as
  certified with non-blocking operational gaps while withholding rollout
  approval.
- Phase 14 created controlled rollout planning and monitoring artifact format.
- Phase 15 retained smoke-review evidence and kept rollout blocked pending
  manual evidence.
- Phase 16 retained local smoke evidence and kept rollout blocked pending
  deployed/manual evidence.
- Phase 17 retained deployed API/frontend shell evidence and identified a
  deployment configuration blocker.
- Phase 18 cleared the deployment configuration blocker but kept rollout blocked
  pending manual review evidence.
- Phase 19 retained maintainer-confirmed manual, responsive, accessibility,
  protected endpoint, and governance evidence and approved controlled rollout
  while keeping full production rollout unapproved.

## Operational Review And Verification

- Operational Review 1 investigated deployed backend health reporting
  development/debug state and concluded deployment configuration was incorrect.
- Operational Remediation 1 defined the production configuration correction and
  verified the local production-mode health path.
- Operational Verification 1 retained deployed Render health evidence showing
  production environment and debug disabled, clearing the deployment
  configuration blocker.

## V2.5 Governance Hardening

- Phase 14 improved inventory presentation.
- Phase 15 improved intelligence presentation.
- Phase 16 approved certified V2 Dashboard rollout within implemented scope.
- Phase 17 established post-rollout monitoring and boundary review.
- Phase 18 remediated backend warning debt without changing certified behavior.
- Phase 19 inventoried production, supported, prototype, experimental, legacy,
  and deprecated surfaces.
- Phase 20 established prototype promotion and deprecation policy.
- Phase 21 created lifecycle enforcement checklists.
- Phase 22 created lifecycle review logs and adoption audit.
- Phase 23 created evidence backfill and owner assignment planning.
- Phase 24 created lifecycle evidence packet templates and initial stubs.
- Phase 25 reviewed evidence packets and readiness classifications.
- Phase 26 performed citation backfill and stewardship review.
- Phase 27 created section-level citation maps.
- Phase 28 assigned evidence ownership, retention cadence, monitoring artifact
  format, and test mapping.
- Phase 29 closed governance hardening and cleared V3 product capability
  planning as appropriate under existing boundaries.

## Recommendation Engine V2

- Strategy, governance, architecture, API, frontend, certification, and
  implementation planning records were completed before implementation.
- Phases 1 through 7 built backend domain, context, neutral intelligence,
  inventory, team context, trust metadata, and refusal/fail-closed behavior.
- Phase 8 exposed the governed bullpen-state API contract.
- Phase 9 added frontend client integration.
- Phase 10 rendered the governed Dashboard V2 surface.
- Phases 10A and 10B remediated desktop and selected-pitcher layout issues.
- Phase 11 completed mobile and accessibility validation.
- Phase 12 completed certification readiness validation.
- Phase 13 formally certified the implemented and governed V2 scope.
- V2 production fail-closed diagnosis and remediation improved freshness,
  trust, and degraded-state communication.

## Recommendation Engine V1

- V1 completed candidate-level policy, implementation planning, API contract,
  frontend contract, UI implementation planning, dashboard integration planning,
  and completion certification.
- V1 remains candidate-level only and does not rank a bullpen or select the
  final pitcher.

## Foundational Product Work

- Bullpen Intelligence, Fatigue Engine, Availability Engine V1,
  explainability, trust layer, freshness transparency, protected operational
  endpoints, sync metadata, and methodology documentation form the completed
  product foundation.
- Prospect Pipeline remains a prototype and is not a promoted production data
  product.
