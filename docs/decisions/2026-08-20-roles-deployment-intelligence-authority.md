# Roles and Deployment Intelligence Authority

**Date:** 2026-08-20
**Scope:** Gaps #18, #19, #20, #21, #22, and #35

## Decision

Team Board may publish descriptive 14-calendar-day deployment profiles from
official team-at-appearance relief rows. The population is
`official_appearance_team_relief_appearances`: `GameLog.appearance_team_id`
owns the historical club, current roster membership never rewrites an old
appearance, credited starts are excluded, and unresolved team or start/relief
authority is withheld.

The public profile is deliberately bounded to evidence that already has a
stable public meaning:

- relief appearances in `[D-13, D]`;
- saves and holds from their stored official flags;
- games finished only where nullable `games_finished` authority is present;
- multi-inning work when canonical recorded outs are at least four;
- frozen pitcher ID, MLB ID when present, display name, represented date,
  denominators, limitations, and backend-authored descriptive copy.

Zero is a governed value. Missing outs or games-finished authority reduces the
corresponding denominator and produces a limitation; it is never converted to
zero. No statistic is converted into closer, setup, fireman, long-reliever, or
manager-intent language.

## Explicitly Withheld Domains

Gap #18 remains definition/authority blocked for public use. Durable
`appearance_entry_context` and `appearance_entry_band` evidence exists, but
the governed entry-band family explicitly marks its distribution contract
internal-only. This package does not promote it.

Gap #19 remains definition-decision required. `appearance_leverage_v1` is an
existing story-oriented classifier using provider leverage index with a
save/hold fallback, but no current decision establishes it as Team Board public
authority. Late innings are not substituted for leverage.

## Public and Prospective Contracts

- method: `public_team_deployment_profile_v1`
- public contract: `public_team_deployment_profile_public_v1`
- carrier: `team_board_deployment_profile_carrier_v1`
- window: 14 calendar days, inclusive `[D-13, D]`
- population authority: `game_log.appearance_team_id_resolved`
- membership authority: `historical_appearance_team_not_current_roster`
- reference policy: `calendar_day_inclusive_through_date_v1`

The current Team Board v2 reader copies this backend-authored profile from the
canonical Recent Relief Work owner. The frontend renders names and summaries
verbatim and performs no baseball aggregation, rate calculation, role mapping,
or direction judgment.

Current serving builds workload and deployment from the one existing
team/window appearance query. Publication calls
`author_public_team_relief_authority` once per represented team and freezes both
workload windows and deployment from that single row set; there is no query per
pitcher or per metric.

New immutable Team Board packages also carry the exact same method-owned
profile. The existing Share Artifact lifecycle may copy that carrier into the
existing `team_board_delta` sidecar as `deployment_profile`. Capture performs
no GameLog query and no recalculation. Old publications and sidecars remain
untouched and report only this domain as not ready.

Compatible endpoints require matching team and publication identity, ordered
represented dates, trusted publication state, method, public and carrier
contracts, population basis, reference policy, and the 14-day window. A
deployment-domain failure does not invalidate Team State, Arm Read, workload,
rotation, membership, or Rest Status authority, and failures in those domains
do not invalidate a valid deployment comparison.

Profiles may be compared internally for exact observed-field movement, but no
reader-facing materiality rule is established here. Gap #22 is therefore
prospective deployment-profile movement authority rather than a historical
job-title migration. Gap #35 remains open until two natural compatible
sidecars exist, a read-only certification succeeds, materiality is separately
governed, and a separate `/changes` package is reviewed.

## Historical and Cross-Domain Policy

No historical replay or backfill is authorized. In particular, this decision
does not permit old GameLog replay, old classifier execution, sidecar rewrite,
current-roster reinterpretation, synthetic carrier insertion, or frozen-reader
migration. Existing Arm Read, Team State, workload, Rest Status, rotation, and
membership carriers retain their contracts and evidence clocks.

## Freeze Authority

The exact frozen production exceptions are:

- `backend/services/public_team_relief_work.py`
- `backend/services/share_artifact_generation.py`

The first owns the new public descriptive profile beside the relief-work
contract it already owns. The second performs only the read-only frozen-carrier
handoff. No wildcard, directory allowlist, public API route exception,
frontend exception, or generic bypass is granted.
