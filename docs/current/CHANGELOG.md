# BaseballOS Changelog

This changelog summarizes major product, governance, rollout, and operational
milestones. It does not replace the detailed evidence records linked from
[docs/README.md](../README.md).

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
- Kept #590 open after merge because production still must prove one Fresh, one
  Stretched, and one Vulnerable team with matching backend payload, rendered
  frontend text, data-through context, and screenshots. Fail-closed outcomes
  remain label-less governed non-states.
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
  [GAME_824487_SOURCE_REVISION_AUDIT.md](GAME_824487_SOURCE_REVISION_AUDIT.md).
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
  shard registrations are removed; the workflow must not be dispatched again.
  Daily and postgame remain shadow, backfill remains off, the legacy writer
  remains authoritative, and writes and publication authority remain unapproved.

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
