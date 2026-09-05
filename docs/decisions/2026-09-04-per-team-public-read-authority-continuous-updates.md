# D-058 — Per-Team Public Read Authority for Continuous Updates

- **Date:** 2026-09-04
- **Status:** Accepted architecture; implementation pending
- **Scope:** Team-scoped public publication authority for Team Board, team What
  Changed, and Team State Share Artifacts after governed continuous reconciliation.
  The complete-only league Dashboard, league surfaces, baseball semantics, source
  authority, and frontend interpretation boundaries do not change.
- **Amends:** D-051 clauses 4, 5, and 8 only, by permitting a complete immutable
  per-team package to become Team Board authority. D-051's scheduled-daily,
  acquisition/publication separation, league publication, and Tonight boundaries
  remain standing.

## Context

BaseballOS Continuous Updates proved the governed path through canonical mutation for
game 824424, Detroit at Cleveland. The accepted final observation created durable work;
canonical reconciliation inserted nine GameLogs and 300 pitches, identified seven
affected pitchers and two affected teams, and completed optional PBP processing.

The downstream publication attempt then correctly refused with
`dashboard_snapshot_slate_coverage_incomplete`. The September 4 slate contained 16
required games: game 824424 was the one final, fully ingested game, while 15 unrelated
games remained non-final. Five bounded publication-only retries preserved canonical
idempotency and then ended in inspectable terminal failure.

That incident exposed an authority gap, not a reason to weaken the Dashboard gate:

```text
continuous canonical state can be current for one team
→ only the complete-slate league Dashboard can currently authorize Team Board
→ Team Board remains intentionally stale until unrelated games finish
```

D-007 already permits an eligible team to publish progressively. The existing
`team_progressive_publications` authority applies that decision to immutable Team State
Share Artifacts. D-051 deliberately kept Team Board and Compare bound to one trusted
league Dashboard and required another explicit decision before either could consume
team-progressive authority. This is that decision.

## Decision

BaseballOS adopts a **Per-Team Public Read Authority** for continuously updated
team-level surfaces.

The implementation will introduce one immutable per-team publication family. Both a
trusted league Dashboard and a governed continuous final-game reconciliation may author
a package in that family:

- `league_dashboard_team_slice` — the exact team package authorized by a complete,
  trusted league Dashboard publication;
- `continuous_team` — the exact team package authorized after that team's completed
  game, canonical reconciliation, downstream recomputation, and team-scoped evidence
  gates succeed.

These are two source types inside one authority family, not competing current-state
authorities. One backend-owned current pointer per team identifies the sole package that
Team Board may serve. The browser never chooses, merges, or ranks authorities.

This decision approves architecture only. Until the staged cutover completes and is
production-proven, the existing D-051 Dashboard-backed read remains authoritative.

## Authority boundaries

| Public surface | Governing authority after cutover | Alignment rule |
| --- | --- | --- |
| Team Board core and details | Current valid per-team publication pointer | One complete frozen package |
| Team Board inline What Changed | Current package plus an explicitly compatible team predecessor | Team-local, identity-exact |
| Team State Share Artifact | Immutable projection of the same per-team publication | Same authority identity as Team Board source |
| Team History / retained team observations | Immutable per-team publication lineage and artifacts | Never reconstructed from mutable current state |
| Compare and scheduled Matchup comparison | Latest common compatible publication boundary | Both teams share one cohort and method boundary |
| Home bullpen landscape | Trusted league Dashboard | Complete-slate only |
| League Board / 30-team listing | Trusted league Dashboard | One common 30-team population |
| League-wide What Changed | Compatible trusted league Dashboard publications | Complete-slate only |
| Tonight and other league-slate products | Their existing trusted league/snapshot authority | No per-team overlay |
| Global ranking/grouping or population claims | Trusted league Dashboard | One common population identity |

Search, routing, and navigation may link to a current Team Board. They gain no baseball
authority from doing so.

## Immutable Team Board publication package

A trusted per-team publication is an append-only package whose required identity and
meaning-bearing content pass validation before its current pointer may advance.

### Required identity

- publication family and schema version;
- immutable per-team publication ID;
- positive canonical team ID and frozen team abbreviation/name;
- source type: `league_dashboard_team_slice` or `continuous_team`;
- monotonic team publication sequence;
- immediate lineage predecessor publication ID, nullable only for the first package;
- publication cohort ID;
- source Dashboard snapshot ID when league-derived;
- source SyncRun ID;
- triggering game PKs and accepted observation/source fingerprints when continuous;
- represented baseball date;
- exact team `data_through`;
- availability reference date;
- generated-at and published-at timestamps;
- package payload version and immutable payload digest;
- method/version manifest;
- canonical evidence fingerprints;
- trust, completeness, correction, and limitation status.

The cohort ID is deterministic from its governing source. A league package uses the
trusted Dashboard identity. A continuous package uses the accepted final-game
observation/reconciliation identity shared by the two participating team packages. It
is never inferred from time proximity.

### Required frozen content

The package freezes every meaning-bearing field needed to render Team Board as one
coherent answer:

- team identity;
- Team State and its exact evidence;
- active-bullpen membership and roster authority identity;
- named Arm Reads and their evidence/limitations;
- workload and rest facts, including exact last-appearance identity;
- recently used arms and recent relief-work receipts;
- governed role/deployment fields;
- approved Team Board performance fields;
- rotation-impact and roster/transaction context where governed;
- core and details section availability/refusal states;
- comparison material required by the approved What Changed domains;
- all method versions, completeness flags, limitations, and source receipts required by
  those fields.

An optional section may be frozen as explicitly unavailable under its existing
smallest-dependent-scope rule. It may not be filled at request time from a different
authority. Missing publication-critical identity, membership, Team State, workload, or
trust evidence withholds the package.

### Roster and method coherence

Roster membership, active-bullpen identity, workload, Team State, roles, performance,
and comparison carriers must name the authority date and method version used to build
them. A package cannot combine a newly reconciled workload with an older unstamped
roster or a newer mutable role record. Builders may reuse existing governed services,
but they must freeze their outputs under one transactionally validated package identity.

Unknown remains unknown. No missing field is coerced to zero or borrowed from another
publication.

## Current-read selection rule

Team Board resolves current authority as follows:

1. Read the backend-owned current pointer for the requested team.
2. Load exactly the immutable package named by that pointer.
3. Validate team identity, publication state, payload digest, required contract
   versions, completeness, and pointer/package agreement.
4. Serve all meaning-bearing Team Board fields from that package.
5. If the pointer or package is missing, invalid, unsupported, or internally
   inconsistent, fail closed for per-team authority and use only the explicitly
   configured rollback authority: the latest valid trusted league Dashboard team slice.
6. If that league slice is also unavailable, return the governed Team Board unavailable
   response.

The selector never searches for "latest" by timestamp, never overlays individual
fields, and never falls back to mutable canonical tables.

### Supersession and precedence

There is no permanent preference for continuous over league-derived packages. The
current pointer is the authority.

Pointer advancement assigns the next monotonic sequence for that team and requires the
candidate's represented evidence not to regress the current package. A later complete
league Dashboard normally authors a newer league-derived package and advances the
pointer, thereby reconciling the team back into the common league boundary. A continuous
package may later supersede that league-derived package after another completed game or
correction. Both remain immutable in history.

Concurrent candidates use compare-and-set against the predecessor/current pointer. A
losing writer must revalidate and retry; it may not silently replace an authority it did
not build from.

## What Changed

Per-team lineage and comparison identity are related but distinct:

- `predecessor_publication_id` always names the immediately prior authoritative package
  in that team's immutable sequence;
- each governed comparison domain names an explicit `comparison_predecessor_id`, which
  is the nearest earlier publication proven compatible under that domain's existing
  method, population, source, and trust contract.

Rules:

1. The current side is the exact package selected by Team Board.
2. No domain compares unless both exact package IDs, represented dates, method versions,
   population authority, and source contracts are compatible.
3. An incompatible domain is withheld locally; another independently compatible domain
   may still render under its existing contract.
4. If the compatible predecessor is not the immediate lineage predecessor, the response
   exposes both identities and exact dates. It never implies adjacency.
5. Same-day publications may compare. The label is "Since last update" with exact
   publication context, not "Since yesterday."
6. The distinct Since Yesterday product compares the current package with the latest
   compatible authoritative package on an earlier represented baseball date. It uses
   "since yesterday" only when the dates are truly adjacent; otherwise it labels the
   exact interval or withholds under its existing contract.
7. Off-days create no synthetic baseball change. A later league-derived authority may
   advance publication identity without a visible change event.
8. A missing or incompatible predecessor yields an explicit unavailable comparison, not
   an inferred transition.

### Corrections

An official correction creates a new immutable per-team package with
`update_kind=correction`, the prior current package as lineage predecessor, and the
corrected canonical fingerprint. Prior publications and citations are never rewritten.
What Changed may describe only the governed field differences and must retain the
correction identity; it may not invent a baseball event or cause.

### Doubleheaders

Game 1 may create a per-team publication before Game 2. Game 2 creates another same-day
publication after its own reconciliation. The Game 2 package's lineage predecessor is
the Game 1 package when no intervening authority exists. `data_through` may be the same
calendar date; game PKs, team publication sequence, cohort ID, and source fingerprints
make the publications distinct. Inline What Changed may compare Game 1 to Game 2 as
"Since last update." The daily Since Yesterday lane does not mislabel that same-day
transition.

## Compare and Matchup decision

BaseballOS adopts **Model B — common-boundary comparison**.

Compare and scheduled Matchup comparison may not place two independently current but
temporally different per-team packages side by side as though they share one comparison
population. Exact timestamps beside each team are not sufficient to cure that semantic
implication.

The comparison selector must choose the newest cohort in which both teams have:

- the same cohort ID and represented boundary;
- compatible payload and domain method versions;
- compatible population/roster authority contracts;
- valid trusted publication state.

For ordinary teams that did not share a continuous cohort, this will normally be the
latest trusted league-Dashboard-derived package common to both. Two opponents may use
their shared continuous game cohort only if every compared domain passes the same
common-boundary contract. If no common compatible cohort exists, Compare fails closed.
It never stitches each team's individually newest package.

## Share Artifact convergence

New Team State Share Artifacts become immutable projections of the same per-team
publication selected by Team Board. The artifact retains its own public artifact ID,
lifecycle, integrity seal, and immutable payload, but its source-authority identity is
the exact per-team publication ID and digest. It does not independently decide current
Team State.

The existing `team_progressive_publications` records remain immutable. During migration
they act as legacy source checkpoints and evidence for existing artifacts; they are not
rewritten or guessed into full Team Board packages. Existing share links remain valid.
After cutover, new continuous and league-derived team artifacts converge on the unified
per-team publication family.

## Continuous publication lifecycle

After a real canonical mutation:

```text
accepted final observation
→ durable canonical work
→ canonical reconciliation committed
→ affected team read models recomputed
→ one complete immutable package built per affected team
→ package + predecessor + current pointer committed atomically
→ Team State Share Artifact projected from that exact package
→ team cache handoff
→ continuous work complete
```

The complete-slate Dashboard remains a separate league publication attempt. While its
slate is incomplete it reports `global_publication_not_eligible`, not a continuous-work
failure. The continuous durable work item is publicly complete when every required
affected-team package and required team cache handoff succeeds. It does not wait for
unrelated games or the league Dashboard.

A refused, incomplete, identity-conflicted, or failed team package is a real scoped
publication failure and remains retryable/terminal under the durable work policy. Global
ineligibility must not hide such a failure.

Suggested lifecycle reporting separates:

- `canonical_complete`;
- `team_publication_pending` / `team_publication_complete`;
- `team_cache_pending` / `team_cache_complete`;
- `global_publication_not_eligible` / `global_publication_complete`;
- `terminal_failure` with stage and reason.

## Atomicity and cache ordering

Canonical mutation commits before public-package construction; publication never makes
uncommitted canonical state public. The per-team publication transaction must atomically:

1. validate the expected predecessor/current pointer and captured source fingerprints;
2. insert the complete immutable package;
3. record lineage/comparison identity;
4. advance the current pointer.

If any step fails, neither package authority nor pointer advances. A current pointer can
never name a missing or incomplete package.

Cache handoff occurs after the authority transaction commits. The durable work receipt
records the publication ID before cache mutation. If required cache handoff fails or the
process dies, restart performs cache-only retry against that exact publication; it does
not rebuild or republish. Cache entries carry the publication identity and are rejected
on mismatch. Work completes only after a required cache handoff succeeds.

## Migration and cutover

No big-bang cutover is authorized.

1. **Contract and storage.** Add the immutable per-team publication, current pointer,
   lineage, digest, and uniqueness constraints. Add validation and writer tests. Do not
   serve it publicly.
2. **League authoring.** Make successful trusted Dashboard publication author the same
   per-team packages for its team slices. Existing Team Board serving remains unchanged.
3. **Current bootstrap.** Create one current league-derived package per team from the
   exact current trusted Dashboard. Do not backfill or rewrite historical publications.
4. **Continuous shadow authoring.** Build continuous packages after canonical mutation
   without advancing public pointers. Verify completeness, identity, retry, correction,
   doubleheader, and no-mixed-field behavior against production-shaped evidence.
5. **Shadow read.** Resolve the would-be per-team package beside the D-051 reader and
   compare identities and meaning-bearing output. Public responses remain D-051-backed.
6. **Team Board cutover.** After independent authority review and production-shaped
   proof, enable the backend current-pointer selector for Team Board core and details as
   one package. Retain explicit rollback to league authority.
7. **Team What Changed cutover.** Enable exact lineage and per-domain comparison
   identities only after natural predecessor, same-day, off-day, correction, and
   doubleheader proof.
8. **Compare/Matchup cutover.** Enable only the common-cohort selector. Asynchronous
   newest-per-team comparison remains prohibited.
9. **Share convergence.** Author new Team State artifacts from the exact per-team
   publication. Preserve all existing artifact URLs and history.
10. **Closeout.** Require exact-head CI, deployment identity, natural final-game proof,
    rollback drill, and observability before declaring implementation complete.

## Rollback

Rollback disables continuous pointer advancement and selects the latest valid trusted
league Dashboard team slice for Team Board. It does not delete packages, move or rewrite
history, alter share artifacts, or infer a replacement predecessor.

The response must identify `league_dashboard_team_slice` during rollback. Cached
continuous packages cannot be served under a league identity. Re-enablement resumes
from the preserved immutable lineage after validating the then-current authority.

## Observability and service objectives

Required internal telemetry:

- current authority type, publication ID, sequence, data-through, and source SyncRun for
  every team;
- final-and-usable to per-team-publication latency;
- current pointer/package/digest validation;
- publication and cache outcome by team, game, cohort, and durable job;
- predecessor and per-domain comparison compatibility;
- league-versus-team publication divergence age;
- global Dashboard eligibility and exact blocking games, separately from team success.

Bounded initial objectives after cutover:

- accepted final evidence to affected Team Board publication within one or two
  continuous cycles, subject to required evidence availability;
- all 30 teams have inspectable current authority;
- zero mixed-authority Team Boards;
- zero pointer/package mismatches;
- zero false What Changed transitions;
- zero duplicate packages for one team/source revision;
- bounded retries with inspectable terminal failure.

No new MLB call, broad rescan, cron, public mutation endpoint, or request-time
reconstruction is authorized by this decision.

## Security and governance

- Backend publication services exclusively build, validate, and advance authority.
- Public GET requests and browser actions never publish or mutate.
- The frontend renders supplied identity and semantics; it does not choose authority.
- Publication and cache operations remain inside existing writer/lock boundaries.
- Immutable history, evidence receipts, and correction supersession remain mandatory.
- The decision changes publication scope, not Team State, Arm Read, workload, roster,
  role, performance, or What Changed baseball meaning.

## Alternatives considered

### A. Keep Team Board league-only — rejected

Safe but incompatible with the continuous-update product contract. A correctly
reconciled game cannot reach its affected Team Boards until unrelated games finish.

### B. Overlay newer Team State onto an older Team Board — rejected

Creates mixed authority: new conclusion, old workload/roster/arm evidence, and false
comparison identity.

### C. Permit a partial global Dashboard — rejected

Weakens complete-slate population truth for Home, League, landscape, and comparisons.

### D. Immutable per-team Team Board publications — accepted

Makes team currentness independent while retaining one coherent package, immutable
history, and the complete-only league boundary.

### E. Live request-time Team Board reconstruction — rejected

Violates compute-once/serve-many, makes request time an implicit writer/authority, and
cannot guarantee reproducible identity or history.

### F. Asynchronous newest-per-team Compare — rejected

Displaying timestamps does not remove the implied side-by-side comparison boundary.
Compare remains common-cohort-only.

## Acceptance criteria for implementation

Implementation is not complete until all of the following are independently proven:

- a Team Board response contains one validated package identity and no mixed fields;
- a natural completed game advances both affected Team Boards before Postgame Primary;
- an unrelated active game does not block affected-team publication;
- the global Dashboard remains withheld until full-slate gates pass;
- current pointer and package persist atomically;
- cache retry never republishes;
- correction and doubleheader publications append without rewriting history;
- What Changed emits only compatible, identity-exact differences;
- Compare never uses asynchronous newest-per-team packages;
- rollback serves a coherent league-derived package;
- no public GET, frontend code, or untrusted worker can advance authority.

## Consequences

- Team Boards can become fresher than Home and League while each surface remains honest
  about its own authority and data-through.
- Operators must observe per-team and league currentness separately.
- Storage and reader selection become more explicit, but duplicated ad hoc authority is
  reduced: Team Board and new Team State artifacts share one source publication.
- Compare may intentionally show an older common boundary than either team's Team Board.
- D-051 remains the active production read contract until the staged cutover proves and
  enables D-058. Decision acceptance must not be reported as implementation completion.

## First implementation package

The first package is storage and dormant authoring only:

- add the immutable per-team publication model and current-pointer model;
- define schema/version, sequence, lineage, cohort, identity, digest, and uniqueness;
- author league-derived per-team packages from a successful trusted Dashboard;
- bootstrap current packages from the one current trusted Dashboard in a governed,
  idempotent operation;
- add validation, atomicity, idempotency, malformed-payload, correction, and rollback
  tests;
- expose internal read-only observability;
- do not change Team Board, What Changed, Compare, Share, or continuous public serving.

Every later phase requires its own reviewed implementation package and evidence.

## References

- BaseballOS Constitution, Sections 9, 10, and 15
- BaseballOS Bullpen Intelligence Standard, public read, evidence, publication, and
  correction contracts
- BaseballOS Product Experience Standard, answer-first and failure-state contracts
- BaseballOS Platform Architecture and Operations Manual, Sections 8, 9, 11, 13, 14,
  17, and 22
- BaseballOS Product Roadmap & Decision Ledger, D-006, D-007, D-011, D-012, D-051,
  D-054, D-055, D-056, and D-057
- BaseballOS Frontend Design & Migration Specification, Parts III, VII, VIII, and IX
- D-058 ledger entry in `docs/canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md`
- `docs/decisions/2026-07-25-progressive-team-artifact-publication.md`
- `docs/decisions/2026-08-07-trusted-publication-authority-manual-daily-retirement.md`
- `docs/decisions/2026-08-18-versioned-daily-delta-substrate.md`
- `docs/decisions/2026-08-20-governed-team-state-what-changed.md`
- `docs/decisions/2026-08-21-governed-rest-status-what-changed.md`
- `docs/decisions/2026-09-02-f019-what-changed-sharing-continuity.md`
- Production incident: game 824424 / SyncRun 4127
