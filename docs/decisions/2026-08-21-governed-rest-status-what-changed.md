# Governed Rest Status What Changed

Date: 2026-08-21

## Decision

What Changed may publish a Rested Options movement only from two compatible,
trusted, actively published D-055 Rest Status carriers. The public lane compares
only `rested_arm_count`. `worked_yesterday_count` and `back_to_back_count` remain
frozen supporting evidence and are not separate public change lanes in this
slice.

The governed authority remains:

- method: `d055_rest_status_v1`
- public contract: `d055_rest_status_public_v1`
- trusted package: `trusted_team_board_publication_v1`
- population: `represented_default_visible_active_bullpen`
- population authority: `trusted_team_boards.default_pitcher_ids`
- membership authority: `eligible_bullpen_pitcher_contexts`
- reference policy: `d055_availability_reference_date_v1`

Both endpoints must have ordered represented dates, an availability reference
date exactly one day after the represented date, exact matching canonical
authority, trusted sidecar metadata, and actively published source Share
Artifacts. A missing, governed-unavailable, malformed, untrusted, withdrawn,
superseded, or incompatible endpoint withholds only the Rest Status lane.

## Materiality and copy

Any exact change in `rested_arm_count` is material because it represents at
least one current bullpen arm entering or leaving the governed rested-options
population. Equal counts remain quiet. Public copy is neutral and backend-owned:
"Rested options moved from 5 to 7." No improvement, decline, advantage, or
ranking claim is made.

## Historical integrity

New sidecars copy the same-cycle frozen D-055 carrier during Share Artifact
publication. Natural sidecars created after the D-055 writer rollout but before
this activation may read the exact carrier from their immutable source
Dashboard snapshot in one bounded batch query. That projection is read-only and
does not modify the source package or sidecar.

No historical Rest Status is recalculated or backfilled. No GameLog replay,
current-roster reinterpretation, package rewrite, sidecar rewrite, or
retroactive stamping is authorized.

## Reader and failure boundaries

`backend/services/team_changes.py` adds the compact Rested Options movement to
the existing What Changed contract. The frontend renders the backend-authored
transition and copy verbatim and performs no arithmetic. An unavailable Rest
Status lane cannot produce a definitive quiet-day claim, but it does not
suppress proven Team State, Arm Read, or appearance/workload movement.

The exact protected production paths authorized by this decision are:

- `backend/services/share_artifact_generation.py`
- `backend/services/team_changes.py`

No wildcard, directory, API-route, frontend, classifier, or generic bypass is
authorized. D-055 calculation, frozen reader behavior, Team State comparison,
workload calculation, and all other Team Board domains remain unchanged.
