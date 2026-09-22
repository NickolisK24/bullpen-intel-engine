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

- Team State and summary: the pre-trust, snapshot-bound Team State receipt in
  the trusted Team Board package for new publications; older snapshots retain
  their published-artifact compatibility read;
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

## TB-03 publication-bound read model

`team_board_recent_usage_rest_v1` is frozen inside each team's existing
`trusted_team_boards` package while the trusted Dashboard candidate is built.
It reuses the same set-based official `GameLog.appearance_team_id` query that
authors the public workload windows and deployment profile. That query includes
the frozen active pitcher IDs so the active source preserves an acquired
pitcher's recent work for a prior club; the existing team-at-appearance filter
continues to author team totals and separately preserves workload contributed
by a pitcher who is now off-active. The carrier is computed before Recent
Relief Work limits its display chronology to five game dates. It introduces no
current selector, table, migration, cache, writer, or publication authority.

The carrier uses the snapshot's `data_through` date as the inclusive end of
three calendar windows: `yesterday` is that one represented baseball date,
`last_3_days` begins two dates earlier, and `last_7_days` begins six dates
earlier. The snapshot's availability reference date must be exactly one day
after `data_through`; otherwise the carrier is unavailable. Each named pitcher
window carries appearances, pitches, and outs as `{value, status,
reason_codes}`. A missing pitch or outs value remains `unknown`; incomplete or
missing slate coverage never becomes zero.

The factual pattern contract is:

- `days_since_last_appearance`: the existing governed workload value for a
  frozen active pitcher, or a coverage-qualified historical calculation;
- `pitched_yesterday`: at least one relief appearance on `data_through`;
- `back_to_back`: the existing recent-window definition—at least one pair of
  consecutive relief-appearance dates in the five-day availability window;
- `three_in_four`: an appearance on `data_through` and appearances on at least
  three distinct dates in the inclusive four-day window;
- `four_in_six`: an appearance on `data_through` and appearances on at least
  four distinct dates in the inclusive six-day window;
- `recent_multi_inning`: at least one relief outing with four or more recorded
  outs in the inclusive seven-day window; and
- `high_pitch_outing`: at least one relief outing with 25 or more recorded
  pitches in the inclusive seven-day window.

These are descriptive completed-game observations. The carrier intentionally
does not publish `pitch_spike`, availability predictions, health meaning, or
manager-intent claims. Positive observations may be established from their
rows; a false value requires complete coverage and all required row fields.
The field states are `complete`, `partial`, `unknown`, and `unavailable`.

`active_pitchers` is sourced from the same frozen default-visible bullpen
membership as TB-02. Pitchers who represented the team during the seven-day
window but are not in that frozen active population appear separately under
`off_active_historical_contributors`; historical workload never changes
current roster membership.

The existing details endpoint exposes the carrier only after reconstructing
the exact snapshot named by `team_board_publication_identity_v1`. A mismatched
snapshot is still rejected by the shared HTTP 409 identity fence. Core does not
include or calculate this carrier, so TB-01 and TB-02 remain independent of
TB-03 hydration.

Composition retains one set-based appearance query per team; the carrier adds
no request-time database read. A local 12-pitcher/36-row component benchmark
measured 0.638 ms median composition (0.614-1.018 ms), 0.072 ms median JSON
serialization (0.070-0.165 ms), and an 18,044-byte compact payload. Publication
also resolves the six prior league-date coverage decisions once and shares
them across all teams; the admitted through-date decision is reused.

## TB-03 user-visible delivery

Recent Usage presents each active reliever's publication-bound Yesterday,
3 Days, and 7 Days appearances, pitches, and outs without recalculating those
windows in the browser. Rest / Usage Patterns renders only the carrier's
factual observations: Pitched yesterday, Back-to-back, 3 appearances in 4
days, 4 appearances in 6 days, Multi-inning outing, and 25+ pitch outing. It
does not present workload as an availability, fatigue, health, or manager-intent
prediction.

Field-level `complete`, `partial`, `unknown`, and `unavailable` states remain
visible at the smallest affected scope. Null facts render as unavailable
evidence rather than zero or false, while other supported facts for the same
pitcher remain visible. Active relievers remain the primary list; recent work
from pitchers outside the frozen active population appears in a separate,
subdued historical-contributor group.

TB-03 attaches only after the existing core/details identity fence succeeds.
The adapter also requires the carrier's `data_through` and `reference_date` to
match the core identity dates. A generation, date, or team mismatch rejects
TB-03 locally and preserves TB-01 and TB-02. Team switching clears the prior
carrier before the next team's details request can attach.

At 390px, each pitcher uses a stacked three-window comparison with wrapping
pattern labels; 768px and 1440px use progressively denser grids. Primary
information does not require horizontal scrolling. The deferred-wrapper mobile
overhang was removed with a local container-margin correction.

With immediate fixture responses in a local compiled preview, five warm runs
measured core DOM readiness at 164.4 ms median (161.1-198.0 ms), details
response at 147.0 ms median (142.8-151.4 ms), and TB-03 DOM readiness at
166.2 ms median (162.7-200.1 ms). TB-03 rendered 20.0 ms median after the
details response (17.7-53.1 ms). These measurements isolate browser rendering;
they are not production network measurements. TB-03 still arrives with the
full details response, whose existing production baseline is approximately
7.9 seconds. No production latency improvement is claimed.

## TB-04 frozen workload read model (backend only)

The trusted Team Board package now freezes `workload_windows.overview` from
the full, resolved official `GameLog.appearance_team_id` row set before any
five-date display truncation or current-roster filtering. This is the same
30-day set-based appearance query used by the existing relief-work and TB-03
carriers. The separate league-day slate coverage extension is shared by all
teams and uses at most two additional set-based source queries after TB-03's
seven-day decisions. No new selector, migration, or request-time TB-04
aggregation is involved.

The 30-day batch lives in `team_board_workload_coverage.py`, called only by
the trusted Team Board workload author. It reuses the existing daily slate
decision and its schedule-context width; it is not a second general coverage
authority. `slate_coverage.py` remains byte-identical to the protected base,
as required by the unchanged legacy What Changed freeze guard. This move
changes neither the carrier facts nor their evidence states.

The `team_board_workload_overview_v1` contract contains independent
`window_3`, `window_7`, `window_14`, and `window_30` facts. Each window starts
at publication `data_through - (days - 1)` and ends on `data_through`, both
inclusive. Pitches, relief appearances (not game dates), and official
`innings_pitched_outs` are separate `{value, status, reason_codes}` facts.
Complete slate coverage permits numeric totals, including a certified zero.
Incomplete coverage produces `partial`/null; missing or unknown coverage
produces `unavailable`/null; an ambiguous start/relief flag or absent official
pitch/outs value produces `unknown`/null for the dependent fact. A partial
30-day window does not invalidate a complete seven-day window.

Seven-day factual concentration uses that same appearance-team population:
all named contributors are ordered by pitches descending then pitcher ID,
with a top contributor, top three contributors, top-three pitch share (a
fraction of total team pitches), and count of pitchers with relief work.
Frozen active membership only labels and splits those contributions into
active-current and off-active pitches, appearances, and outs; it never filters
historical team work.
An acquired pitcher's earlier appearances for another club remain outside
this team's totals. A zero-pitch window has no share denominator and publishes
`top_3_share: null`, not a fabricated percentage. No trend is authored:
`trend_status: unavailable`.

The core/details identity fence is unchanged. Details serve the frozen facts
only when the selected trusted snapshot, Team Board package authority, and
carrier date agree. The existing 7/14-day presentation fields are projected
from the frozen legacy carrier for compatibility; the four-window contract is
attached as `workload_overview.frozen_team_workload` for the later TB-04
frontend package. TB-01/TB-02/TB-03 presentation remains untouched. Local
query-count tests assert one appearance query per team and at most two
additional set-based league coverage queries per publication. Older snapshots
without this new nested contract retain their prior 7/14-day presentation
behavior; they do not gain or synthesize TB-04 facts at request time.
An isolated local 30-row projection measured 0.169 ms aggregation, 0.032 ms
JSON serialization, and 2,593 serialized bytes; details projection measured
0.055 ms and 3,376 bytes including the legacy presentation shape. These are
local composition measurements, not production latency claims.

TB-04 now renders the nested frozen carrier as one compact, semantic table of
3/7/14/30 baseball-date windows, each with backend-authored pitches, relief
appearances, and official outs. Each cell renders its own complete, partial,
unknown, or unavailable state; only a complete numeric zero is displayed as
zero. The seven-day panel displays the backend's top-three pitch share and
ordered named contributors, plus current-active and off-active contributions.
It does not sum pitcher rows, infer a trend, or put off-active pitchers into
Active Bullpen. Prior-team appearances are excluded by the frozen backend
appearance-team authority, not by a frontend calculation.

The existing core/details publication-identity comparison still gates the
attachment. The frontend also checks the nested carrier contract and
data-through date; a mismatched TB-04 carrier is withheld without replacing
valid TB-01/TB-02/TB-03 content. Core renders before details, while TB-04
shows a lightweight loading state. The table remains readable at 390, 768,
and 1440 pixels without horizontal scrolling; headings and exact values are
text-accessible. Local fixture readiness measurements are recorded separately
from core and details: a local browser fixture measured 224 ms to core answer,
210 ms to details response, and 232 ms to TB-04 readiness (22 ms after details
response). This is not an isolated React render profile or production latency
measurement. Older trusted
snapshots without the frozen carrier show a section-local unavailable state.

## TB-05 public deployment authority (backend carrier)

The existing public roles remain Trusted Arm, Setup Arm, Coverage Arm, Middle
Relief Arm, and Role Unclear. The 45-day role classifier and its guarded public
read are unchanged. A separate 14-baseball-day `[D-13, D]` publication-time
carrier now joins each current arm's already-authored public role with the
existing official appearance-team deployment profile and bounded observed
context. It does not label a closer or infer an intended bullpen order.

The [public deployment decision](../decisions/2026-09-21-team-board-public-deployment-context.md)
defines exact entry-inning counts, factual leading/tied/trailing score context
at entry, and explicit low/middle/high bins of *recorded appearance-level*
leverage index only. A save or hold never substitutes for a missing index.
Each domain carries its own complete, partial, unknown, or unavailable state
and known/total appearance denominators. Missing play-by-play, score, or LI
does not erase a supported save, hold, finish, or multi-inning fact. Extra
innings remain exact; entry base state and mid-inning context are not claimed.
Named-arm role movement remains `unavailable/not_published` because no public
materiality rule exists.

The carrier is frozen inside `trusted_team_boards` under the same
`trusted_dashboard_publication_v1` identity. The details reader validates its
team, represented date, contract, method, and package authority before
attachment; old packages stay readable but cannot acquire new context from
request-time rows. The assembly reuses the existing bounded official
appearance query, then makes at most one set-based processed-game marker and
one set-based play-by-play projection per represented team with qualifying
relief work. No migration, sync writer, or atomic authority changes are made.
The TB-05 section now renders the already-frozen active-arm profiles after
core/details identity attachment. The public role labels are unchanged; its
compact role mix precedes named-arm rows with factual saves, holds, games
finished, multi-inning appearances, exact inning-entry counts, leading/tied/
trailing entry counts, and low/middle/high recorded appearance-level leverage.
The section does not infer a closer, entry pattern, leverage-at-entry, role
movement, manager intent, or future usage. Entry, score, and leverage each
retain their own complete/partial/unknown/unavailable state and known-count
denominator. Old publications without this carrier retain the prior frozen
deployment summary, but cannot acquire the new context at request time.
Mismatch rejects the new section without discarding the answer core, Active
Bullpen, Recent Usage, or Workload Overview.

At 390 pixels, named-arm evidence stacks without horizontal overflow; 768 and
1440 pixels use compact cross-arm columns. Role and leverage meaning is textual,
with semantic headings and list/name-value structure. A local browser fixture
measured 227 ms to core answer, 210 ms to details response, and 239 ms to TB-05
readiness (29 ms after the details response). These are local fixture timings,
not production latency or an isolated React render profile. Named-arm role
movement remains unavailable until a separate public materiality rule exists.

## TB-06 frozen active-bullpen performance (backend carrier)

The [TB-06 v1 publication decision](../decisions/2026-09-22-team-board-performance-v1-publication.md)
freezes the existing Active Bullpen ERA and WHIP reads in
`trusted_team_boards.performance` at Dashboard publication. The group is the
represented default-visible active bullpen; the sample is official, completed
regular-season relief work for this team through the represented baseball
date. Appearance-team ownership excludes acquired arms' prior-team work;
off-active arms are not in this active-group read. Recorded outs, displayed
innings, relief appearances, active arms, and contributing arms accompany
the two independent metric qualifications and evidence states.

K-BB% and HR context have bounded source-field coverage counts but remain
`unavailable/not_published` until their publication-critical source contracts
are certified. Inherited-runner context remains explicitly unavailable for
uncertified completeness. No missing value is zero. The details route serves
only the exact frozen performance carrier; older packages lack TB-06 rather
than recomputing current GameLog rows. Team State is unchanged. The local
30-team PostgreSQL rehearsal measured one performance appearance query per
team (30 total), 27.793 ms across 30 performance compositions, 0.389 ms to
serialize all 30 carriers, and 93,711 serialized bytes in that small fixture.
These are local fixture measurements, not production latency or payload size.
No per-pitcher query or publication pointer movement occurred. This is the
publication-time cost baseline. The TB-06 section presents frozen ERA and
WHIP side by side with the backend-authored active-group, regular-season, and
recorded-innings sample summary. Each metric retains its own qualification:
a certified `0.00` displays, but a withheld value never becomes zero. A compact
native disclosure lists K-BB%, HR allowed, and inherited runners as not
published. The frontend does not calculate rates, grade results, predict
usage, or alter Team State. It attaches only when the existing core/details
identity matches and the frozen read's represented date matches; otherwise
TB-06 alone is withheld. Older publications do not synthesize TB-06. The
layout is a compact responsive pair at 390, 768, and 1440 pixels, with textual
values and a keyboard-accessible disclosure. A local browser fixture measured
204 ms to core answer, 189 ms to details response, and 210 ms to TB-06
readiness (21 ms after details). These are fixture timings, not production
latency or an isolated React render profile. The frozen carrier adds no request-time
performance query. Uncertified source completeness for the three deferred
capabilities is the known TB-06 v1 limitation.

## TB-07 recent rotation impact

The existing `rotation_support_pressure_v1` read governs the rotation-start
population, short-start rule, and aggregate context. TB-07 adds only the
game-level facts needed to explain that context: the official starter's name
where resolvable, starter outs/innings, and team bullpen outs/innings for
completed regular-season team games. A short start is the existing public
classifier's fewer-than-15 recorded starter outs (before five innings); an
innings figure is rendered from exact outs in baseball thirds (`4.2`, never
`4.7` for 14 outs). An
opener/bulk or bullpen game is not relabeled as a rotation start. The window
is seven inclusive baseball dates, `[data_through - 6, data_through]`, not
the availability reference date used by the older aggregate summary.

`trusted_team_boards.by_team_id[team].frozen_rotation_impact` is authored
during candidate publication from the stored team-game pitching splits and
scheduled-final team-game identities. Starter names are resolved in one
league-wide set query. Team-at-game ownership does not follow a starter's
current team, so a traded starter's historical start remains with the club
for which it occurred. Two source queries plus one name query cover the normal
30-team complete-split path; ambiguous game shapes may require the existing
classifier's verification read. No request-time source query or migration is added. The new read is
available only in Team Board details and attaches through the existing exact
core/details identity fence plus carrier team and represented-date checks.
Older snapshots lack the carrier and cannot synthesize it from current rows.

Each displayed start carries independent starter-length, bullpen-work, and
short-start evidence states. Only classified complete facts are displayed;
missing or ambiguous splits are counted as excluded and make the window
partial. Without scheduled-final game evidence, the window is unknown and
no split-only game is presented as final. Missing outs never display as zero
or as a negative short-start claim. A backend-authored subtotal summarizes
only the complete starts in the represented window. With the new carrier,
the section uses that summary and a small text-first recent-start list;
older snapshots retain the prior compact aggregate rather than mixing its
different availability-date window into the represented-date read. It does not infer
causation, predict usage, or repeat TB-04's 3/7/14/30 workload windows.
Names and game facts remain readable at 390, 768, and 1440 pixels without
horizontal scrolling; the layout uses semantic list and time elements.

The local disposable 30-team publication rehearsal measured 3 TB-07 source
queries, 2.624 ms for carrier composition, 0.055 ms serialization, and 9,203
serialized bytes across all teams in its sparse fixture. These are fixture
measurements, not production latency. Its candidate never moved a pointer.
The local browser fixture measured 234 ms to core readiness, 217 ms to details
response, and 248 ms to TB-07 readiness (31 ms after details); these are not
production measurements or an isolated React render profile. Incomplete
team-game split coverage, unavailable starter names, and the legacy aggregate's
different reference-date anchor remain explicit limitations.

## TB-08 roster and transactions

TB-02's frozen `default_pitcher_ids` and represented roster records remain the
only current active-bullpen authority. TB-08 freezes the existing public,
identity-qualified pitcher transaction projection into
`team_board_roster_transactions_v1` during trusted Dashboard assembly. The
authority audit found current membership, typed/qualified transaction dates,
recall/option/IL labels, and source-window status ready; off-active contributor
linkage is partial when seven-day workload evidence is incomplete; ambiguous
or unverified event claims are not governed for public display. The
source-owned latest transaction sync window is bounded by its recorded query
dates (normally the source end date and seven preceding baseball dates) and
clamped to the represented Team Board date. No request-time transaction query
fills an older package or an unavailable source window. Only events with
verified pitcher identity, typed public category, team endpoint, and explicit
explanatory eligibility are shown; partial windows and withheld events remain
limited, never certified empty.

Each frozen event keeps its verified source and complete event-level evidence
state; the window may still be partial when other events are withheld. Public
labels reuse the existing typed vocabulary: recalled, optioned,
activated, injured-list placement/activation, traded, designated,
outrighted, released, claimed, and the other qualified roster-list moves.
Additions/removals require a matching team endpoint; ambiguous movement stays
in other moves. The dated event and current status are deliberately separate:
an old option does not override a later active roster read. Injured-list
wording states only the verified roster move, not severity or return timing.
Recent contributors outside the represented active bullpen may receive frozen
current-roster context from the same package, without copying TB-03/TB-04
workload values or changing appearance-team ownership. Acquired pitchers'
prior-team appearances remain with that prior team.

The section is a compact current-group summary plus dated additions/removals
and off-active context. It renders backend type, direction, dates, current
membership, and evidence state without browser roster inference. Exact
core/details identity and carrier team/date/active-group checks reject stale
attachment while earlier sections remain usable. The layout uses textual
status, semantic time/list elements, keyboard-operable pitcher handoffs, and
no horizontal table at 390, 768, or 1440 pixels. Old snapshots explicitly
lack TB-08. The local rehearsal measured one set-based transaction read for
30 teams, 6.089 ms to read, 0.193 ms to project all carriers, 0.090 ms to
serialize 21,030 bytes, and zero pointer moves. These fixture timings are not
production latency.
Natural publication confirmation remains asynchronous.
The local browser fixture measured 233 ms to core readiness, 212 ms to
details response, and 239 ms to TB-08 readiness (28 ms after details). This
does not isolate React render cost or predict production latency.

## Trusted publication rehearsal release gate

Run `python -m scripts.rehearse_trusted_publication` from `backend` with
`TEST_DATABASE_URL` set to a dedicated, disposable local PostgreSQL database
whose name contains `rehearsal_test`. The command rejects missing or
non-PostgreSQL targets, nonlocal hosts, a conflicting `DATABASE_URL`, and
production app mode. It creates representative rows for 30 teams, runs the
installed trusted Dashboard builder and Team Board package assembly, stores
the candidate with `publish=False`, and asserts that neither the published
snapshot pointer nor the SyncRun pointer moves. It checks the frozen TB-04
windows, evidence states, certified zero, concentration, off-active workload,
prior-team exclusion, core/details identity, mismatch rejection, and older
package compatibility. The candidate is disposable test evidence, never a
trusted production publication or a substitute for production admission.

Team Board packages may advance when targeted tests, hosted CI, this
deterministic rehearsal, and deployment health all pass. Waiting for the next
natural trusted publication is post-release confirmation, not a serial
development gate. When it arrives, verify the new carrier, exact identity,
representative values, and production rendering asynchronously. A failed
natural confirmation interrupts current product work for a demonstrated
correctness or currentness repair. No production publication pointer is moved
by rehearsal, and the existing trusted-publication admission rules remain
unchanged.

## Deferred packages

TB-04 through TB-10 attach only through the same exact identity contract. This
package does not expand their semantics. Optional detail failure leaves TB-01
and TB-02 intact.

TB-09 What Changed must use the exact current/previous trusted Dashboard
snapshot pair. It must not claim atomic predecessor authority. R3-D remains
frozen unless a future product requirement explicitly adopts atomic publication
semantics.

### Snapshot-bound Team State authority for TB-09

The mandatory pre-trust Team State publication proof resolves governed readiness
once for each of the 30 teams. In the same transaction, it binds one
`frozen_team_state` receipt per Team Board package to team id, Dashboard snapshot
id, represented date, and `v3_phase_5` method. The receipt uses the existing
Fresh/Stretched/Vulnerable public vocabulary and passes the same artifact
eligibility gate. The proof retains the frozen generation inputs so the
post-commit Share Artifact writer consumes the pre-commit evidence rather than
reading later mutable rows. A missing or ineligible team, proof failure, or
receipt persistence failure rolls back the trusted pointer movement.

For new snapshots, TB-01 reads the receipt directly; a later Share Artifact
write failure cannot change the served Team State. TB-09's backend comparison
reads those same receipts from the current snapshot and the *exact* governed
legacy predecessor. It emits a Team State transition only when both immutable
receipts are valid. If either older snapshot lacks a receipt, that comparison
domain is unavailable rather than reconstructed from mutable data. Existing
TB-01 artifact serving remains available for those older snapshots. This does
not add roster/workload/role/performance What Changed events or implement R3-D.

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
