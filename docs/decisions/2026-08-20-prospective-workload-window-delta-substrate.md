# Prospective workload-window delta substrate

- **Date:** 2026-08-20
- **Status:** Prospective implementation; natural compatible evidence required
- **Scope:** Gap #32, governed 7-day and 14-day team relief-work windows only

## Decision

Gap #32 means comparison of the complete backend-authored 7-day and 14-day
workload window objects owned by `backend/services/public_team_relief_work.py`.
It is not a pitch-only metric. Each frozen window retains relief appearances,
distinct pitchers in relief, pitch total and pitch-coverage count, unclassified
start/relief count, represented-through date, and the existing public sentences.

The windows cover official appearances attributed to the represented team side
by `GameLog.appearance_team_id`; current roster membership is not the
population. Each interval is calendar-day inclusive through the publication's
represented date: `[D-6, D]` for seven days and `[D-13, D]` for fourteen days.
Workload concentration, Rest Status, Arm Read, Team State, the 30-day daily
series, and appearance chronology remain separate domains.

## Existing-authority finding

Before this package, Team Board v2 calculated these windows at reader request
time. Neither the immutable Dashboard publication nor the Team Board delta
sidecar preserved the exact published window objects. Historical comparison
would therefore require applying today's calculation to old rows, which is not
authorized.

Gap #32 consequently uses prospective freezing rather than publishing a reader
delta now.

## Prospective authority

During immutable Dashboard publication, the existing canonical relief-work
owner authors each represented team's windows against the candidate's explicit
represented date. The complete result is stored by value in that team's
`trusted_team_boards` package with:

- method version `public_team_relief_work_windows_v1`;
- public contract version `public_team_relief_work_windows_public_v1`;
- carrier contract `team_board_workload_windows_carrier_v1`;
- the existing Team Board package contract;
- population basis `official_appearance_team_relief_appearances`;
- appearance-team and non-current-roster population authority;
- reference-date policy `calendar_day_inclusive_through_date_v1`; and
- the exact represented-through date.

The post-publication Team State lifecycle may copy that exact carrier into the
existing append-only `team_board_delta` sidecar. It performs no workload query
or calculation. Artifact reuse does not create or backfill a sidecar, and
same-publication re-entry preserves the existing immutable row.

Old Dashboard packages and old sidecars remain valid for Team State, Arm Read,
and active-arm-count domains. Their workload domains report `domain_not_ready`.
No historical GameLog replay or backfill is authorized, and no old publication
or sidecar may be rewritten.

## Comparison contract

The 7-day and 14-day domains are independently comparable only when both
endpoints prove:

- the same team and strictly ordered represented dates;
- immutable publication and source identities;
- matching method, public-contract, carrier/package, population, attribution,
  and reference-date authority;
- trusted publication state; and
- structurally complete frozen window objects whose `through` dates match their
  containing endpoints.

The carrier contract version is copied explicitly from the immutable Team Board
carrier into each workload domain's sidecar metadata. A missing carrier version
or a mismatch between endpoints is contract-incompatible and fails both workload
domains closed because the carrier is their shared transport/storage authority.
Missing or invalid frozen value data remains domain-local: one workload window
may be unavailable while its valid sibling still compares.

Legitimate numeric zero is preserved. A missing window or authority stamp is
not zero and fails closed. A null pitch total remains the existing governed
partial pitch-coverage statement; appearances and the coverage count remain
frozen rather than being discarded. Changed fields are descriptive only and
carry no improved/worsened interpretation.

## Activation boundary

`/changes` and the Team Board What Changed frontend are unchanged. Gap #32
remains open until this prospective substrate is merged and deployed, two
natural compatible workload-bearing sidecars exist, and a separate read-only
certification authorizes a reader-facing publication package.

Gap #51 Phase 1 remains a separate Rest Status carrier rollout. Gap #31 Rested
Options, Gap #29 Arm Read activation, Gap #30 Team State movement, and Gap #50
Arm Read freezing are unchanged.

## Freeze authority

The only frozen production paths authorized by this decision are:

- `backend/services/public_team_relief_work.py`
- `backend/services/share_artifact_generation.py`

The first exposes the existing calculation at an explicit publication date;
the second copies an already-frozen carrier into the existing optional sidecar
path. No API route, frontend path, directory, wildcard, or generic bypass is
authorized.
