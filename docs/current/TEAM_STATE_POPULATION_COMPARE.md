# Team State Population Compare — Runbook

## Purpose

Measure, at one moment, whether the two populations Team State depends on are the
same set of arms:

| Population | Owner |
| --- | --- |
| **A — board** | the governed current-availability population that `services.public_serving_authority` freezes as `trusted_team_boards.default_pitcher_ids` |
| **B — readiness** | the canonical active bullpen `services.team_readiness_coverage.resolve_active_bullpen_membership` resolves, which `api.team_operations.resolve_readiness_population` feeds to the readiness distributions |

Historical membership is unrecoverable: the readiness path reads live `Pitcher`
rows, and `services.roster_status_sync` overwrites `pitcher.roster_status` in
place. A current, same-moment comparison is therefore the only honest one, and
this is the smallest job that can produce it.

This changes no product semantics — no Team State vocabulary, threshold,
classifier, population rule, publication behaviour, or frontend.

## Read-only guarantee

The comparator issues `SELECT` queries only. It never inserts, updates, deletes,
commits, publishes, recalculates, repairs, syncs, warms a cache, or calls a
source API. `backend/services/readiness_population_comparison.py` never touches a
session at all — it is arithmetic over sets and statuses.

The script asserts `db.session.new`, `db.session.dirty`, and `db.session.deleted`
are empty and rolls back before writing output; if anything staged a change it
exits non-zero with no artifact. A failed read is rolled back and reported by
exception class only, because a driver message can carry the SQL and the
connection string.

The GitHub workflow is `workflow_dispatch` only, declares no schedule, requests
`contents: read`, and uploads an artifact as its sole output.

## Same-moment design

Everything happens in one process, inside one `app_context()`, against one
database state.

`reference_date` is captured once and passed explicitly to both resolvers, so
neither can fall back to a different default. It is resolved exactly as the
production readiness route resolves it:
`product_availability_reference_date_from_sync_status(sync_status)` falling back
to `product_current_date()`.

Population A is built with the same two calls the canonical board builder uses —
`current_availability_records(latest_fatigue_rows(), reference_date=...)`, grouped
by `pitcher.team_id`. Nothing is persisted and no snapshot is created to obtain
it.

Population B is resolved through the real runtime entrypoint,
`resolve_readiness_population`, once per team. That single call returns both the
membership and the records the readiness pipeline actually consumes, so the
runtime contract is measured rather than assumed:
`runtime_population_consistent` asserts the consumed records are exactly the
board records inside the resolved membership.

### Why the published board is not Population A

The currently published `default_pitcher_ids` were frozen at an earlier moment.
Using them would break the same-moment guarantee. They are read as **reference
only** and reported under `published_board_reference`, with `used_as_population_a`
false. When the published snapshot's `availability_reference_date` matches the
current reference date, its per-team ids are carried alongside as
`published_board_pitcher_ids` and compared to the current candidate via
`published_board_matches_candidate`, so board volatility is measured instead of
asserted. When it does not match, the ids are `null` and the reason is recorded —
stale membership is never silently substituted.

## The readiness gate

Confirmed by running the resolver locally: when `public_roster_readiness` reports
`claims_available: false` it withholds `bullpen_arms`, the roster authority
publishes no arms, and `resolve_active_bullpen_membership` fails closed to an
empty set with `authority_complete` false.

The readiness population is therefore gated on `roster_status_snapshots` coverage
even though the membership list itself is built from live `Pitcher` rows. A team
in that state is emitted with `readiness_authority_incomplete`, never as a genuine
zero-arm bullpen. An inconclusive team must not read as a match.

## Shadow Contract A

For each population the artifact carries an offline Contract A state, so a
population difference can be judged for consequence rather than counted:

```
Vulnerable  if clean_count <= 2 or severe_share >= 1/3
Fresh       if not Vulnerable and clean_share >= 0.60
                              and clean_count >= 5
                              and severe_count <= 1
Stretched   otherwise
```

Clean = `Available`. Moderate = `Monitor` + `Limited`. Severe = `Avoid` +
`Unavailable`. **STATUS ONLY** — no raw score escalates or reclassifies anything.
Boundaries are compared as exact rationals, not floats, so `3/5` and `1/3` land
where they are supposed to.

This is written nowhere: no snapshot, no artifact of record, no table, no
response. The production classifier is not called and not modified.

A zero-arm population is reported as `shadow_state: null`. Contract A's clean-count
floor would nominally read it as Vulnerable, but publishing a state for a team
with no arms converts a data condition into a classification. That guard is
declared ahead of any production figure and applies only to the empty case.

## Pre-registered rules

Fixed before any production figure existed, and evaluated mechanically under
`rule_evaluation`. The script reports metrics; it does not authorise anything —
`declares_authorization` is always false.

| Rule | Condition |
| --- | --- |
| PASS A | ≥ 28/30 exact set matches, non-matching teams differ only by Monitor/Limited arms, no clean-axis mismatch |
| PASS B | every team differs by ≤ 1 arm, no clean-axis mismatch, no shadow-state mismatch |
| FAIL | clean-axis differences on ≥ 2 teams ("repeated/systematic"), or any shadow-state disagreement |

All three can be unmet at once — one clean-axis difference with no state
disagreement clears no PASS rule and trips no FAIL rule. That is reported as
`no_rule_met` and is a founder-review outcome, not a pass.

## Local usage

```
cd backend
python -m scripts.compare_team_state_populations \
  --output /tmp/team_state_population_comparison.json
```

Exit codes: `0` success, `2` a population could not be resolved fairly (or a read
failed), `3` the session unexpectedly staged ORM changes.

## Production execution

1. Actions → **Team State Population Compare** → *Run workflow*.
2. Download the `team-state-population-comparison` artifact (14-day retention).

There are no inputs: the comparison is always all 30 canonical clubs at the
current reference date.

The run fails loudly — never with an empty "successful" artifact — when database
configuration is absent, the canonical club directory does not resolve 30 clubs,
Population A resolves no records, Population B is empty for every club, an
eligible published board package has an unsupported shape, or the ORM session
becomes dirty.

## Output fields

Top level: `export_version`, `generated_at`, `comparison_started_at`,
`reference_date`, `repository_sha`, `read_only`, `board_population_source`,
`readiness_population_source`, `published_board_reference`, `shadow_contract`,
`team_count`, `summary`, `rule_evaluation`, `rows`.

Each row: `team_id`, `team_abbreviation`, `reference_date`,
`board_population_count`, `readiness_population_count`, `board_pitcher_ids`,
`readiness_pitcher_ids`, `intersection_pitcher_ids`, `only_in_board`,
`only_in_readiness`, `symmetric_difference_count`, `exact_match`, `count_match`,
`clean_axis_difference`, `clean_axis_difference_count`, `differing_arms`,
`board`, `readiness`, `shadow_state_match`, `readiness_authority_complete`,
`runtime_population_consistent`, `integrity`, `published_board_pitcher_ids`,
`published_board_matches_candidate`.

Each entry in `differing_arms`: `pitcher_id`, `difference_direction`,
`difference_class`, `membership_reason`, `availability_status`,
`availability_data_state`, `raw_score`, `active`, `team_id`, `roster_status`.
Arm facts are queried only for differing ids, so a matching team emits none.

`difference_class` is one of `CLEAN`, `MODERATE_MONITOR`, `MODERATE_LIMITED`,
`SEVERE_AVOID`, `SEVERE_UNAVAILABLE`, `UNKNOWN`. An arm with no governed status
is `UNKNOWN` and is never counted clean — a difference we cannot read must not be
dismissed as harmless.

## Prohibited uses

- Do not treat a shadow state as a published or proposed Team State.
- Do not use this artifact to authorise Team State vNext on its own; the gate
  decision is the founder's, from `rule_evaluation`.
- Do not fill an `UNKNOWN` status or a `null` arm fact with a current value.
- Do not wire the comparator into sync, publication, or any scheduled job.
