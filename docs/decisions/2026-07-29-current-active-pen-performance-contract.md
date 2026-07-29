# Decision: Current Active-Pen Performance Contract

- **Date:** July 29, 2026
- **Owner:** Nickolis Kacludis
- **Status:** Adopted
- **Resolves:** O-001
- **Canonical homes:** Bullpen Intelligence Standard Sections 7A and 7B; Product Experience Standard Section 14; Platform Architecture & Operations Manual Section 6; Editorial & Distribution Standard Section 12A; Product Roadmap & Decision Ledger D-021 and D-022

This record preserves the rationale and the repository evidence behind the decision. The canonical documents own the rules. This file does not restate them as a second manual.

## Decision

BaseballOS establishes one reusable performance-intelligence family, **Current Active-Pen Performance**, for metrics describing how the pitchers currently comprising a team's active bullpen have performed in official completed games.

Current Active-Pen ERA is the first planned metric under the contract. It is not the contract, and it is not implemented or public.

A metric family and a metric definition are separate governed objects. The family owns the baseball question and the common authority contract. Individually versioned metric registry entries inherit it. Adding an approved metric under an established family does not reopen O-001.

## Why a family contract rather than an ERA specification

The roadmap item that opened O-001 was written as a single metric. Specifying one metric would have produced the same problem again for WHIP, K%, BB%, K-BB%, HR/9, inherited-runner outcomes, and any later rate metric: each would need its own group definition, window, sample rule, date stamp, and evidence chain, and each would be free to answer a slightly different baseball question.

The group, window, date, evidence, and limitation questions are not ERA questions. They are family questions. Only the formula, numerator, denominator, minimum sample, and rounding are genuinely per-metric. Separating the two means the expensive decisions are made once.

## Why the group is defined by current membership and the appearances are not

The family answers one question: how have *today's* arms performed? That requires two different authorities evaluated at two different times, and conflating them is the failure mode the contract is built to prevent.

- **Who is in the group** is a current-roster question, evaluated as of the represented baseball date.
- **Which appearances qualify** is a historical question, owned by the official completed pitching line and the appearance-team authority for the game in which the appearance occurred.

D-009 already established that a historical appearance belongs to the team side for which the pitcher appeared. The contract preserves that and adds the converse: current membership decides who is in the group, and never which team owns an appearance. A pitcher acquired in July brings his qualifying appearances *for this team* into the group's window and leaves his appearances for his prior organization where they belong.

## Repository evidence considered

The contract was written against the current repository, not against an intended design. What exists today:

- `services/appearance_team_authority.py` and `GameLog.appearance_team_id` / `_source` / `_status` / `_reason` provide the resolved, fail-closed historical appearance-team authority, with the pitcher's current team explicitly forbidden as a source.
- `services/season_bullpen_aggregation_2026.py` is the canonical, production-internal, officially validated team-level season bullpen aggregation. It aggregates by `appearance_team_id`, classifies relief by official `games_started == 0`, uses integer outs, and reports exact ERA components with a governed `era_denominator_zero` refusal at a zero denominator.
- `services/availability_population.py`, `services/bullpen_population.py`, `services/bullpen_eligibility.py`, `services/roster_status.py`, and `services/role_authority.py` together produce the governed current-availability population that public bullpen surfaces already use.
- `services/roster_authority.py` is the intended canonical roster-context authority and is explicitly a foundation only: pure, unwired, attached to no payload.
- `services/pitcher_public_labels.py` owns the canonical public role and read label vocabulary, including a governed `limited_read` label.
- `utils/innings.py` and D-008 keep integer recorded outs as the innings authority, with decimal innings derived.

## Discrepancies recorded rather than hidden

These are current-code facts. This work package changes no code; it records what a later implementation must reconcile.

1. **Two different groups exist in code, and neither is the contract's group.**
   `season_bullpen_aggregation_2026` aggregates *all* relief appearances owned by a team side, regardless of who is on the roster now — that is team-season bullpen performance, not current active-pen performance. `season_era.py` aggregates the governed current bullpen population but groups by the pitcher's mutable current `Pitcher.team_id` and includes each pitcher's full regular-season line, which means appearances made for another organization are currently counted toward his current team. The contract permits neither behavior. Implementation must intersect current membership with team-side appearance ownership.

2. **`services/season_era.py` carries a stale limitation.** Its documented limitation states that game logs do not store team-at-appearance, so bullpen ERA is grouped by current team assignment. The appearance-team authority now exists and is backfilled. The statement was true when written and is false now. A test (`test_season_era_reader_is_not_migrated_in_this_step`) deliberately pins both the current-team grouping and the stale limitation string, so correcting the module is a governed migration, not an edit.

3. **A `season_era` block is present in a public API response.** `GET /api/bullpen/dashboard` includes a `season_era` key built by `build_season_era_payload`. No public frontend surface renders it; the only consumer is the private posts view at an unlisted route. So no public *presentation* of current-pen ERA exists, but the value is reachable in a public payload. The contract's fail-closed and evidence requirements are not satisfied by that block, and it must not be treated as the metric shipping.

4. **`services/team_state_card_metrics.py` carries a stale parenthetical.** Its docstring justifies computing no performance metric partly on the grounds that none is truthfully supportable without a team-at-appearance authority. That authority now exists. The module's decision to compute no performance metric remains correct under this contract, but the stated reason is out of date.

5. **`public_reader_gate` is computed, not hardcoded, in one place.** Most capabilities emit `blocked` literally. `season_bullpen_aggregation_2026._gates` returns `ready_for_review` for `public_reader_gate` when official validation passes, while `share_card_performance_gate` stays `blocked`. `ready_for_review` is not open and authorizes no publication, but it is the one gate value in the repository that moves on its own. No gate was changed by this work package.

6. **Public read-label drift between documents and code.** The canonical documents list the arm-read catalog as Clean Option, Watch Arm, Limited Rest, Unavailable, Limited Read. `pitcher_public_labels.READ_PUBLIC_LABELS` renders `clean_option` as "Rested" and `rest_restricted` as "Rest-Restricted". This is outside O-001 and is not corrected here; it is a vocabulary-alignment work package. It matters to this contract only because it shows that public wording is code-owned, which is why the contract refuses to invent a below-sample label.

## What is deliberately not decided

- **M-001's formula approval, minimum sample, and denominator.** No canonical source currently contains an approved ERA minimum sample. `baseline_engine.MIN_SAMPLE_COUNT` (10) governs baseline-distribution interpretation and `bullpen_eligibility` constants govern roster eligibility; neither authorizes a performance threshold. Inventing one here would have created exactly the kind of unexplained number the Constitution prohibits. The only below-sample behavior authorized by canonical code today is refusal at a zero denominator.
- **Final public wording for a below-sample read.** `Limited Read` is a governed arm-read label and has never been authorized as a team-level performance label. Reusing it, or choosing other wording, is an implementation-time decision owned by the canonical public-label authority.
- **Concrete storage, services, endpoints, cache keys, migrations, and classes.** These require repository implementation discovery, not a documentation decision.

## Consequences

- The Team Board is the canonical public home for current active-pen performance and owns the presentation and evidence path. It is not the computational owner; every surface reads the same backend-owned authority.
- State and Why stay above performance on the Team Board. Performance is added evidence inside the page's existing question, never a second page mission and never a team score.
- Compare may show aligned team values only when product date, method version, freshness, and group contract are comparable on both sides.
- Historical Share Artifacts freeze the metric, group, method, sample, date, evidence, and limitation as published, and never recalculate from live membership.
- Editorial copy may not earn a quality adjective or ranking verdict from a performance metric alone, and may not publish a performance value without its group, sample, and represented date.
- SC-05, `public_reader_gate`, `team_state_performance_gate`, and `share_card_performance_gate` remain blocked. This contract opens no gate and authorizes no publication.

## Reversal Standard

Reversing this decision requires a new Decision Record identifying which baseball question the family contract cannot answer, and demonstrating that per-metric group, window, sample, date, and evidence definitions would reduce rather than increase the risk of two surfaces publishing different answers to the same question.
