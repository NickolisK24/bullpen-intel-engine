# Team Board 2.0 Foundation

Status: TB-01 Answer Block and TB-02 Active Bullpen foundation

Base: `d318aae706b83d360d78b30e31dc424f8f614877`

Public authority: `trusted_dashboard_publication_v1`

## Scope

This package establishes the product-facing Team Board foundation without
changing baseball semantics, sync writers, migrations, or publication
authority. The public page continues to read the trusted Dashboard package.
SP-10 cohorts and atomic publication are not Team Board authority.

## Delivery contract

`GET /api/bullpen/teams/<team_id>/board-v2/core` selects one trusted Dashboard
snapshot and returns the answer-first payload. Its
`team_board_publication_identity_v1` identity includes the team, Dashboard
snapshot and sync run, represented and availability dates, publication and
generation timestamps, payload version, Team Board contract versions, and the
governed method versions used by the frozen package.

`GET /api/bullpen/teams/<team_id>/board-v2/details` accepts that complete
identity. The backend resolves the named previously published snapshot,
rebuilds the selected team's trusted board from it, and returns HTTP 409 if any
identity field differs. The frontend repeats the same full-field comparison
before attaching details. A team switch cannot request details using the prior
team's retained core identity, and any identity-field change restarts the
deferred request.

The compatibility `/board-v2` route remains available. It is not used by the
normal Team Board page.

## TB-01 Answer Block

Core owns and delivers:

- team identity;
- backend-authored Team State and concise summary;
- data-through and currentness context;
- active bullpen count;
- frozen Rest Status when authoritative;
- governed off-active count;
- the compact seven-day workload carrier when present; and
- section-local partial or unavailable status.

The three-day recently-used count is intentionally deferred because its owner
is the official Recent Relief Work chronology. The browser does not infer that
count from per-arm rows. Until details arrive, the Answer Block withholds it
rather than substituting zero.

## TB-02 Active Bullpen

The active population is the existing
`current_scored_bullpen_eligible_pitchers` projection from the trusted Team
Board package. No second roster lookup or browser filter is used. Every arm is
rendered once in backend order with the backend-provided public role, current
read, last appearance, days since use, last-game pitches, seven-day
appearances, seven-day pitches, and governed back-to-back flag. Missing facts
render as withheld values, never zero. Each row routes to the canonical Pitcher
page.

Roster incompleteness remains explicit through the existing
`active_bullpen` section status. Available arms may remain visible beside one
scoped limitation; an unavailable population is not presented as an empty
population.

## Ownership boundary

Backend owners:

- Team State and summary: published Team State artifact frozen to the selected
  trusted Dashboard snapshot;
- active membership and roster context: trusted Team Board package and roster
  authority;
- role and current read: existing public role/read projections;
- workload facts and Rest Status: existing frozen workload/read models;
- freshness and partial/unavailable state: trusted Dashboard publication.

Frontend owners only layout, ordering, navigation, interaction, and formatting.
It does not classify Team State, roles, reads, rest, or workload.

## Phase 0 audit record

The core payload contains the publication identity, team, freshness, Team
State, summary, Active Bullpen, Rest Status, off-active count, compact workload,
roles, rotation carrier, roster context, operating-state disclosure carrier,
section statuses, and limitations. Details contains recent usage, the governed
recently-used count, detailed workload/deployment, game context, performance,
transactions, What Changed, and Recent Relief Work.

The normal page makes one teams-directory request, one team core request, and
one deferred details request. Share-card work remains lazy behind an explicit
interaction. The foundation does not add an N+1 read. The prior client retained
core data during a team switch; this package prevents that old identity from
starting an unnecessary details request for the new team.

Production BAL measurements on September 16, 2026:

| Resource | Before this package |
| --- | --- |
| Core | 0.505s, 0.616s, 1.091s |
| Details | 6.812s, 7.399s |

These are direct network observations, not server-only timings. This package
does not change either backend query path, so after-change production latency
requires deployment and is not claimed by local tests. Its performance change
is removal of the avoidable wrong-team details request during team switching.

The existing responsive layout uses one composed record per reliever below
768px, the denser table layout from 768px, and the full last-game/pattern columns
from 1024px. The Team Board shell caps content at 72rem. Primary baseball
content does not require horizontal scrolling at 390px, 768px, or 1440px.

## Deferred packages

TB-03 through TB-10 attach only through the same exact identity contract. This
package does not expand their semantics. Optional detail failure leaves TB-01
and TB-02 intact.

TB-09 What Changed must use the exact current/previous trusted Dashboard
snapshot pair. It must not claim atomic predecessor authority. R3-D remains
frozen unless a future product requirement explicitly adopts atomic publication
semantics.

## Known evidence limitations

- Rest Status may be unavailable when workload evidence is incomplete.
- Rotation may remain partial when trustworthy recent-game evidence is
  insufficient.
- Unverified transaction events remain withheld.
- The three-day recently-used count arrives with deferred Recent Relief Work,
  not the fast core.
- Deep details remain materially slower than core and should be optimized only
  inside the later product package that demonstrates the need.

## Frozen backend work

R3-B1.2-B/C, B2/B3/B4 sync closure, R3-C, standalone R3-D, SP-14 completion,
atomic cutover, new providers, credential redesign, writer expansion, and
cohort-manifest architecture remain outside this package.
