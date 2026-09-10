# Phase 0D Public Language Rules

## Purpose

These packages define eligibility language only. They do not flip posture,
create public evidence, or authorize a surface. Every eligible rule remains
`internal_only` until Phase 0B legal/source review is resolved and a later
approved surface phase explicitly adopts it.

## Allowed Principles

- counted, dated, past-tense facts
- k-of-n wording with definitions inline or one tap away
- thresholds displayed beside flags
- named pitchers only with cited rows
- roster and IL facts sourced as "per MLB transaction data"

## Shown Vs Supporting Contract

A public claim is showable only when its citations are exposable:

- rule text
- thresholds
- cited rows
- completeness state
- reason codes

A claim whose citations cannot resolve must not render.

## Degraded And Unknown Phrasing

- degraded windows never render bare numbers
- UNKNOWN renders what is missing and why
- withheld renders the floor or gate
- absence of a flag never renders

## Required Disclaimers

| Key | Required text |
| --- | --- |
| base-state unknown for entry context | Runners on base at entry are not stored in the current final play-by-play foundation. |
| HBP/ROE exclusion for clean/traffic | Clean/traffic counts use hits, walks, and hit batters; reached-on-error is not included in the current definition. |
| schedule-subject-to-change for off-day tomorrow | Tomorrow's schedule context is subject to schedule changes before first pitch. |
| appearances-not-distinct-arms | This is an appearance count, not a distinct-pitcher count. |
| pitchers-not-relievers for census | This is an active pitcher census, not a reliever count. |
| contributor-set denominator for compositions | This set is appearance-evidenced; the team's roster reliever count remains unknown by design. |
| no-public-IL-flag phrasing | No public IL flag is stored for this pitcher in the cited snapshot. |
| legacy under-fire caveats where sourced | Legacy row caveat: sourced true values remain cited, while unset false values can be undercounted. |

## Workload Recovery

Anchor: `workload-recovery`

Required package:

- render dates and window lengths next to every count
- render thresholds next to every flag
- render pitch and batters-faced subtotals with unknown-subtotal wording
- never turn days-of-rest counts into a current-state claim

## Appearance Entry Exit

Anchor: `appearance-entry-exit`

Required package:

- render entry and exit as stored timing facts
- include the base-state unknown disclaimer for entry context
- include play-granularity notes for exit context
- describe innings spanned as span, not out totals
- describe game phase as inning-band-only

## Inherited Traffic Clean Outing

Anchor: `inherited-traffic-clean-outing`

Required package:

- render inherited-runner facts as boxscore-sourced
- render clean and traffic definitions inline
- include the HBP/ROE exclusion text for clean/traffic
- keep `outing_context_unknown` as degraded supporting accounting

## Starter Exposure Calendar Density

Anchor: `starter-exposure-calendar-density`

Required package:

- render both sums for team bullpen share of outs
- render known-subtotal wording for pitch windows
- include the appearances-not-distinct-arms disclaimer
- display the 14-outs short-start definition
- include the schedule-subject-to-change disclaimer for off-day tomorrow
- keep calendar density componentized

## Roster Depth Churn

Anchor: `roster-depth-churn`

Required package:

- include the pitchers-not-relievers note for active pitcher census
- use exact safe phrasing for IL placement and activation context
- count public IL presence only
- never make statements about non-IL pitchers
- include coverage caveats for transaction churn
- require later review before public depth-delta or roster-change phrasing

## Roster Membership Context

Anchor: `roster-membership-context`

Required package:

- render only same-day snapshot facts
- use exact forms only:
  - `On the active roster per the <date> snapshot (team <id>).`
  - `Not on the active roster per the <date> snapshot.`
  - `Roster membership unknown: <reason>.`
- require `UNKNOWN` when the same-day snapshot is missing or stale
- add no conclusion beyond the cited roster row

## Entry Context Bands Usage Observations

Anchor: `entry-context-bands-usage-observations`

Required package:

- keep `appearance_entry_band` and `pitcher_entry_band_distribution` internal
- render finish context with legacy caveats where sourced
- render save/hold windows as counts only
- for eligible observations, re-render band-derived pieces as plain inning and
  margin facts
- display floors and k values where applicable

## Team Relief Contributor Composition

Anchor: `team-relief-contributor-composition`

Required package:

- carry the contributor-set denominator disclaimer verbatim
- inherit basis preconditions for every composition read
- show attribution exclusions and completeness state
- document 0D-04 emission-policy coupling for outing mix
- keep contributor counts distinct from any roster partition

## Forbidden Master List

The terms in this explicitly marked list are forbidden in public claim packages,
registered templates, rendered claims, and public copy except when quoted here
as forbidden examples:

- healthy
- injury-free
- full strength
- nobody is hurt
- cleared
- ready
- available
- unavailable
- fresh/tired/gassed/taxed/overworked as labels
- thin
- deep
- depleted
- short-handed
- trustworthy
- reliable
- shaky
- dominant
- workhorse
- go-to
- leaned on
- closer/setup/fireman/stopper/long man/committee and all role titles
- trusts/prefers/manager's choice
- pressure
- leverage
- high-leverage
- stress
- structure/hierarchy/pecking order
- will/should/expect/likely/projects
- odds/bet/lock/fade
- every score/grade/rank/percentile framing
