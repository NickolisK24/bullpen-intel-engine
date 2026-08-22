# Non-Material Rehab Assignment Authority

Date: 2026-08-22
Status: Accepted

## Decision

Raw transaction code `ASG` remains heterogeneous and remains normalized as
`unknown`. BaseballOS certifies only the narrower
`asg_pitcher_rehab_assignment_v1` subtype when all of these persisted,
transaction-time facts agree:

- the structured source code is `ASG`;
- the participant links to a canonical `Pitcher`;
- `from_team_id` is an MLB club;
- `to_team_id` is a non-MLB club whose season-specific `parentOrgId` equals
  `from_team_id`;
- the exact transaction-date roster snapshot belongs to `from_team_id`, has
  `active_roster == false`, and carries `IL_15` or `IL_60`.

Description text, mutable `Pitcher.team_id`, nearest-date roster evidence, and
absence of evidence have no role. Missing metadata or an exact snapshot leaves
certification unresolved. Conflicting team authority also fails closed.

## Materiality

A certified rehab assignment is governed `non_material` for Recent
Transactions. It remains off the public chronology and does not count as a
withheld bullpen event. It does not activate the pitcher, alter active-bullpen
membership, alter Off-Active Count, or authorize a health, readiness, or return
claim. Current Roster Context remains the IL/off-active authority; a later
recall or activation remains separately material.

Repeated certified assignments use the same treatment. BaseballOS does not
infer initial assignment, continuation, or reassignment.

## Persistence and acquisition

Ingestion acquires season-scoped team sport and parent-organization metadata in
one bounded source request and prefetches exact-date roster snapshots in one
bounded SELECT. The certified subtype, materiality, authority, reason, and
evidence are persisted on `PlayerTransaction`. The public reader independently revalidates
those stored facts and performs no network or roster lookup.

Legacy rows default to unresolved. Natural transaction resync may apply the
deterministic authority through the existing correction policy; no bespoke backfill or historical publication mutation is authorized.

## Fail-closed boundary

Generic `ASG`, no-source-to-MLB assignment, MLB-to-MLB assignment, missing or
nearest-date-only roster evidence, active/`40_MAN_ONLY` state, parent mismatch,
`SC`, `CLW`, `SFA`, malformed rows, and all other ambiguous events remain
unresolved. Proven non-pitcher exclusion remains an independent authority.

No public response field, frontend behavior, transaction taxonomy, historical
team ownership, current roster semantic, or other Team Board domain changes.
