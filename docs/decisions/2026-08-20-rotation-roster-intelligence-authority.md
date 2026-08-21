# Rotation and Roster Intelligence Authority

Date: 2026-08-20
Status: Accepted for prospective publication

## Decision

BaseballOS treats Rotation Impact, official transaction chronology, current
roster context, and historical bullpen membership as related but distinct
governed reads. This package adds two current-state improvements and two
prospective comparison domains without creating a second history system.

## Gap #24: recent-series rotation burden

The historical phrase "recent-series rotation burden" is not a current
canonical metric. `scheduled_games` and `team_game_pitching_splits` retain
official opponent, `series_game_number`, and `games_in_series` facts, but they
do not retain a durable series identity that safely joins postponements,
resumptions, and makeup games into one historical publication claim.

The existing governed equivalent is the seven-calendar-day Rotation Impact
read. A literal recent-series read remains definition/authority blocked. The
system must not infer a series identifier by grouping display dates or opponent
strings.

## Gap #25: Rotation to Recent Relief Work receipts

The canonical Rotation Impact owner now carries a bounded handoff containing
the MLB game PK and game date for each analyzed rotation start. These identities
come from the same `team_game_pitching_splits` rows that authored the burden
claim. The Team Board presents a same-page handoff to the existing Recent
Relief Work section; it does not duplicate relief-work facts or match games by
display text.

## Gap #27: transaction descriptions

`public_recent_transactions.py` remains the owner of the reader-safe official
transaction chronology. Supported typed categories now author concise full
sentences from the verified player identity and structured category. Trade and
roster movement copy stays deliberately non-directional unless stored
authority proves direction. Unsupported categories, unresolved player identity,
or unverified team attribution remain withheld. The frontend renders the
backend description verbatim and performs no transaction-code interpretation.

## Gaps #28 and #34: bullpen churn and membership movement

Bullpen churn is defined descriptively as additions to and removals from the
represented default-visible active bullpen between compatible publications.
It is not the existing `bullpen_stability_v1` usage-pattern read and is not a
score, rating, percentile, or transaction count.

The frozen population is `trusted_team_boards.default_pitcher_ids`, authored
from the same-cycle `current_availability_records` population. Its carrier
retains public pitcher identity, membership reference date, Team Board package
contract, roster-authority version, population basis, and these versions:

- method: `team_board_default_bullpen_membership_v1`
- public contract: `bullpen_membership_snapshot_public_v1`
- carrier: `team_board_bullpen_membership_carrier_v1`

Compatible endpoints compare membership sets without requiring identical
pitcher IDs. Added and removed records carry identity only. A transaction
reason may be attached by a future reader package only when an independently
governed official event matches; absence of such an event never licenses an
inferred reason.

The eventual current-state placement for descriptive churn is a supporting
read within Recent Transactions, with roster movement also eligible for a
separate What Changed lane. Neither reader surface is activated by this package.

## Gap #33: rotation-transfer delta

"Rotation transfer" means movement in the complete canonical Rotation Impact
claim, whose primary exact facts include starter outs, short starts, and
bullpen outs required across its seven-day window. It does not mean a new
causal or qualitative metric.

The immutable Team Board package already copies the same-cycle
`rotation_support_pressure_v1` object. New sidecars retain that exact object and
the following authority:

- method: `2026-06-18.phase2`
- public contract: `rotation_support_pressure_public_v1`
- carrier: `team_board_rotation_impact_carrier_v1`
- population: official scheduled final team games with stored team-game
  pitching splits
- attribution: team and game identity from `team_game_pitching_splits`
- reference policy: `rotation_support_inclusive_reference_date_v1`

The comparison is descriptive. Increased or decreased bullpen outs do not
mean better, worse, healthier, or more vulnerable.

## Prospective delta architecture

The existing `team_board_delta` sidecar gains independent
`rotation_impact` and `bullpen_membership` domains. The handoff is:

trusted Team Board package
-> read-only carrier capture
-> `backend/services/share_artifact_generation.py`
-> immutable Team Board delta sidecar
-> version-aware comparison

A missing pre-package domain returns `domain_not_ready` for that domain only.
Rotation failure does not invalidate membership, workload, Team State, or Arm
Read, and membership failure does not invalidate rotation. Legitimate numeric
zero and an empty but governed membership set remain comparable values.

No public `/changes` lane is added. Activation requires merge and deployment,
a first natural sidecar, a second compatible natural sidecar, read-only
certification, and a separately reviewed reader package.

## Historical policy

No historical recomputation or backfill is authorized.

In particular, this decision prohibits replaying current rotation logic over
old games, applying the current roster to old dates, rebuilding old membership,
retro-stamping old sidecars, rewriting snapshots, or creating synthetic
transaction correlations. Only new publication lifecycles may carry the two
comparison domains.

## Protected neighboring domains

This package does not alter Team State (#30), Arm Read evidence (#29/#50),
Rest Status or its staged carrier (#31/#51), workload evidence (#32), role
movement (#35), `/changes`, or frontend What Changed behavior.

## Freeze authority

The only newly authorized frozen production path is
`backend/services/share_artifact_generation.py`. The exception is exact-path
and decision-linked. No API directory, frontend directory, wildcard, adjacent
Share Artifact service, or generic bypass is authorized.
