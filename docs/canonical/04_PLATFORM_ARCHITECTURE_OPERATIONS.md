# BaseballOS Platform Architecture & Operations Manual

| Field | Value |
|---|---|
| Status | Canonical - system architecture, security, deployment, operations, and runbook authority |
| Version | 1.6 |
| Effective date | August 14, 2026 |
| Owner | Nickolis Kacludis |
| Repository | `NickolisK24/bullpen-intel-engine` |
| Production product | `baseballos.app` |
| Update rule | Revise when system boundaries, canonical entities, services, publication flow, APIs, deployment, security, monitoring, repair, or operational ownership changes |
| Review cadence | After every material infrastructure or publication change; monthly production review |

> **Architecture must make it structurally difficult for BaseballOS to publish something it cannot defend.**

## 1. Purpose

This Manual explains how BaseballOS acquires data, establishes canonical baseball records, derives bullpen state, publishes trusted reads, preserves immutable artifacts, serves public surfaces, and recovers from failure.

It owns technical delivery and operations. It does not redefine the product mission, intelligence contract, page missions, editorial voice, or roadmap sequence.

## 2. Architecture Objectives

The platform must be:

- evidence-first;
- fail-closed;
- reproducible;
- correction-aware;
- freshness-aware;
- observable;
- secure by default;
- inexpensive and understandable for one operator;
- modular enough to evolve without a rewrite project.

The preferred architecture is boring, explicit, testable, and recoverable.

## 3. Technology Stack

### Public application

- React
- Vite
- JavaScript/TypeScript where currently used
- Tailwind/CSS application styles
- Vercel frontend hosting

### Backend and data

- Python
- Flask
- SQLAlchemy
- Alembic migrations
- PostgreSQL
- Render backend hosting
- MLB Stats API as the principal public baseball source

### Automation and quality

- GitHub Actions scheduled and manual workflows
- pytest backend suites, installed from the development requirements rather than the runtime set
- Node-based frontend tests
- continuous dependency auditing of both runtime surfaces
- production smoke tests and operator audits
- immutable database records and typed refusal/accounting where required

A new framework, service, database, queue, or deployment layer requires a concrete trust, reliability, performance, or maintenance reason.

## 4. System Context

```text
MLB Stats API and public authorities
        |
        v
Acquisition and reconciliation
        |
        v
Canonical game / pitching line / roster / appearance records
        |
        v
Deterministic workload and bullpen intelligence services
        |
        v
Trusted snapshots and team-progressive publication
        |
        +---------------------------+
        |                           |
        v                           v
Public application            Immutable Share Artifacts
        |                           |
        v                           v
Evidence inspection           Permanent share pages / future rendered assets
        |
        v
Product Intelligence and operator diagnostics
```

## 5. Architectural Principles

1. Raw source responses are not public product models.
2. Meaning-bearing fields have one canonical owner.
3. Derived values never overwrite their authoritative inputs.
4. Unknown and conflicting values remain explicit.
5. Publication is a gated lifecycle, not a successful API request.
6. Historical and current state remain separate.
7. A renderer consumes a frozen contract; it does not calculate baseball meaning.
8. Failure removes dependent scope rather than silently substituting data.
9. Every mutation is bounded, auditable, and idempotent where practical.
10. Operations must be understandable by the founder after time away from the codebase.

## 6. Domain Boundaries

### Acquisition domain

Owns MLB source access, retry/backoff, caching where appropriate, endpoint response capture, source timestamps, and raw-to-canonical handoff.

It must not decide public copy or silently convert missing source values into product defaults.

### Schedule and finality domain

Owns `game_pk`, official schedule identity, game state, finality, slate dates, doubleheaders, first-pitch context, and completed-game eligibility.

A schedule row is contextual until finality permits completed-game publication.

### Appearance and pitching-line domain

Owns official starter designation, canonical recorded outs, appearance sequence, pitches, strikes, batters faced, relief designation, and game-team ownership.

Decimal innings are derived from canonical outs and never treated as an independent authority.

### Roster and team-assignment domain

Owns current active/off-active separation, current organization/team, canonical status categories, transaction context, historical appearance ownership, and unknown/conflict state.

### Workload and arm-state domain

Owns deterministic rolling windows, rest, multi-day use, availability/internal status, public arm-read payloads, and evidence references.

It consumes canonical appearances and roster authority. It does not reinterpret source identity.

### Team intelligence domain

Owns team-level state, named bullpen reads, active-group composition, optionality/coverage/readiness evidence, and team explanation payloads.

It composes existing arm and source authorities. It does not create a second roster or appearance truth.

**Public Team State authority.** The public Team State a reader sees is projected from the governed Team Operations readiness result by one owner, `services/team_state_public_vocabulary`. Live board, comparison, and dashboard payloads carry that projection as a purpose-built `team_state` block; they never derive it from board group counts, the count-derived `context.health` state, landscape lane membership, availability percentages, or stress summaries, and they never hold a second copy of the mapping. Readiness derivation, thresholds, and status codes are unchanged by the projection — it only reads what readiness already decided. An outcome with no public Team State keeps its refusal or limitation metadata and receives a governed non-state message rather than a label.

**Team State population contract.** The records that derive Team State are the same records whose coverage authorizes the read: the canonical current active bullpen, resolved once per team from the Roster Authority and Role Authority and shared by the readiness distributions and the trust classifier. A pitcher who is on the team but not in that population — a starter, an injured-list arm, off-active organizational depth — carries workload and availability like any other and must never decide the bullpen's state; those arms remain visible as separate roster and off-active context. When the population authority is incomplete the membership is empty, trust reads `unknown`, and the status resolver refuses before any distribution is consulted. Deriving readiness from a wider pitcher set than the one the coverage contract judges is a defect: it lets a single arm outside the bullpen determine the team's public state.

### Performance intelligence domain

Owns every metric governed by the Current Active-Pen Performance Contract: active-group resolution for the represented date, qualifying-appearance selection, metric numerators and denominators, sample evaluation, refusal codes, evidence assembly, and method versions.

Rules:

- **Backend-owned.** The canonical performance authority computes the value. The frontend renders a governed contract and never recalculates, re-derives, re-rounds, or re-aggregates a performance value from raw fields.
- **One owner, many consumers.** Every surface reads the same authority. A public home owns presentation, not computation.
- **Fail-closed publication.** Below an approved minimum sample, or with an unresolved group, window, or appearance authority, the domain publishes no numeric value and returns a typed refusal. It never substitutes zero, a prior value, a league value, or an estimate.
- **Method and evidence ownership.** The domain owns the method version bound to each value and the evidence chain back to official completed pitching lines. A value without its method version and evidence route is not publishable.
- **Historical appearance ownership is upstream.** The domain consumes the appearance-team authority; it never attributes an appearance from a pitcher's current team.
- **Immutable artifacts freeze the read.** A published artifact stores the metric, group, sample, method version, represented date, evidence, and limitation as they were. It is never recomputed from live membership.

- **Arithmetic is exact.** Every metric's numerator and denominator are integers. No floating-point type participates in a governed metric calculation at any stage. The ratio is an exact decimal quotient, rounded `ROUND_HALF_UP` exactly once at the metric's declared precision, and stored as a fixed-precision string alongside its exact integer numerator and denominator. A value rounded more than once is not reproducible and is not publishable.
- **Sample thresholds are stated in the denominator's unit.** A rate over innings is gated on recorded outs, never on appearance count. The threshold, its unit, and its authority are carried with the value.
- **Two refusals stay distinct.** A zero denominator is a mathematical refusal, evaluated before any sample check. A below-sample result is a governance refusal. They never share a code.

The reusable metric registry is a governed definition set, not a new subsystem. Its required fields live in the Bullpen Intelligence Standard; concrete storage, services, routes, and caching are decided at implementation time against the existing repository, not specified here.

The reusable framework exists in the repository as a production-internal foundation. It is unwired: no route, no payload, and no surface consumes it, and every publication gate it reports is blocked. M-001's approved parameters are specified in the Bullpen Intelligence Standard Section 7C and are not yet set in the metric registry entry. Setting them is an implementation package that carries its own review; approving a parameter does not wire it.

### Observation and story domain

Owns eligible observations, story shapes, deterministic public-copy structures, suppression, evidence blocks, and destination bindings.

It may select and organize governed evidence. It may not invent facts.

### Publication domain

Owns trusted league snapshots, team-progressive publications, publish/refuse accounting, source snapshot identity, evidence revisions, and immutable artifacts.

### Presentation domain

Owns browser view models, route rendering, accessibility, metadata, and display components.

It receives purpose-built public contracts. It does not reconstruct business meaning from raw database fields.

### Product Intelligence domain

Owns operational coverage, generation/refusal diagnostics, evidence-inspection events, distribution events, and privacy-bounded aggregate reporting.

Analytics failure never blocks public intelligence.

## 7. Canonical Data and Persistence

### Persistence rules

- Store canonical observed records separately from derived state.
- Store durable source and sync identity for meaning-bearing records.
- Prefer integer recorded outs for innings authority.
- Preserve current roster assignment separately from historical appearance ownership.
- Use immutable daily or publication snapshots for historical claims.
- Version methodology and artifact contracts.
- Never rewrite published artifact meaning in place.
- Enforce uniqueness and idempotency at the database layer where practical.

### Core entity families

| Family | Purpose |
|---|---|
| teams, players, venues | Stable identity and display attributes |
| games / slate games | Completed and scheduled game identity, status, finality, context |
| game logs / appearances / pitching lines | Canonical completed pitching records |
| pitches | Pitch-level evidence where ingested |
| roster status / transactions / team assignment | Current and historical roster authority |
| arm state / workload snapshots | Deterministic daily reliever state |
| team state / bullpen snapshots | Deterministic team-level state and publication input |
| team-progressive publications | Team-scoped trusted authority after finality and evidence pass |
| evidence items / observations / stories | Structured support and public interpretation |
| share artifacts / assets / relations | Immutable public claim, rendering, and supersession lifecycle |
| methodology versions | Versioned definitions bound to derived records |
| sync runs / ledgers / suppression / repair records | Freshness, failure, correction, and operational history |
| product intelligence events | Privacy-bounded product and distribution measurement |

### Immutable daily-state direction

Daily arm/team snapshots should be written once per entity/product date and not updated in place. Corrections should create explicit revised authority or versioned replacement according to the domain contract.

This enables What Changed, timelines, archives, follow-up/calibration, and as-of reproducibility.

## 8. Sync and Publication Modes

Supported operational modes include scheduled daily sync, scheduled postgame reconciliation, focused repair or reconciliation, governed historical backfill on an explicit date, intraday source refresh, team-progressive publication, and controlled artifact generation.

**Authoritative manual daily execution is not a supported mode.** Under D-051 the production full-daily path is schedule-only and first-attempt-only: generic manual daily dispatch, local production daily invocation, the legacy admin daily writer route, and reruns of a scheduled daily job are non-authoritative and refused. Narrowly scoped operator work outside the authoritative daily path — governed backfill on an explicit date, read-only intraday audit, and separately authorized repair — retains its own contract and gains no daily-sync authority from this section.

Every mode records start/end time, requested date/window, source status, records attempted/created/updated/refused/failed, publication result, and durable error context.

### Current baseball-data authority

This is the platform-altitude answer. `docs/current/SYNC_PIPELINE.md` and `docs/current/GAME_DRIVEN_DAILY_INGESTION.md` carry the implementation detail and may not contradict it.

- The legacy daily/postgame path remains the authoritative baseball-data writer.
- The game-driven lane operates in `shadow` on the daily and postgame cycles, and `off` on the explicit backfill step.
- Shadow observation grants no durable write authority and no publication authority.
- Automated game-driven write mode and authoritative mode are unapproved.
- Backfill remains disabled as an automatic authority; it runs only on an explicit reviewed date.
- Acquisition authority and publication authority are separate: a write does not publish, and publication advances only through a trusted candidate that passed every gate.
- Any expansion of this authority requires an explicit Decision Ledger entry.

## 9. Canonical Public Sync Order

The canonical order is:

1. create and persist the sync-run identity;
2. resolve product date and requested slate window;
3. acquire schedule and source coverage;
4. reconcile game identity, team participants, and finality;
5. acquire/repair completed pitching lines and appearance ledger;
6. reconcile official starters and semantic innings from recorded outs;
7. acquire current roster/team-assignment context;
8. recompute arm workload and availability/read payloads;
9. recompute team intelligence and evidence;
10. evaluate league trusted-snapshot gates;
11. evaluate eligible team-progressive publication gates;
12. generate or refuse immutable artifacts through the publication authority;
13. record complete accounting and operator diagnostics;
14. serve only trusted, current or explicitly historical authority.

A failure in one team or evidence family must not corrupt unrelated teams. A late unrelated game may not block an already complete team-progressive publication.

## 10. Appearance Ledger Gate

The appearance ledger is publication-critical.

Before downstream publication:

- completed games are final;
- participants and team sides are resolved;
- official starter designation agrees with completed pitching-line authority;
- canonical recorded outs are present and valid;
- decimal innings derive from outs;
- appearance identity and team ownership are stable;
- no duplicate equivalent record creates double counting;
- dependent workload calculations use the repaired authority;
- regression fixtures cover the incident class.

An incomplete or conflicting ledger blocks only the dependent publication scope and produces a typed reason.

## 11. League and Team Publication Authority

### League trusted snapshot

A league snapshot requires configured slate coverage, freshness, appearance completeness, roster/currentness rules, evidence sufficiency, and successful publication proof.

### Team-progressive publication

A team publication may become authoritative after that team's final game and team-scoped evidence pass even if unrelated league games remain unresolved.

Its durable identity includes team, product date, source snapshot/run, final game or evidence revision, and the canonical input fingerprint required for idempotency.

Repeated equivalent attempts return or reuse the existing authority. A changed evidence revision may create a new eligible publication without rewriting the old record.

## 12. Failure Isolation

The system must distinguish:

- no game yet final;
- source unavailable;
- source partial;
- identity conflict;
- appearance ledger incomplete;
- starter authority unresolved;
- roster/currentness unavailable;
- evidence insufficient;
- trust gate refused;
- duplicate equivalent;
- renderer unavailable;
- integrity mismatch;
- operational failure.

A refusal is not a technical failure. It is a governed product result and must be accounted for separately.

## 13. Immutable Share Artifact Architecture

### Generation flow

```text
Trusted published team state
+ governed evidence
        |
        v
Eligibility and copy guards
        |
        v
Canonical immutable artifact payload
        |
        +-> Public /share/{public_id}
        +-> Browser card presentation
        +-> Future server-rendered social asset
        +-> Open Graph / metadata
        +-> Product Intelligence events
```

Current live reads are fetched separately and never mutate the artifact.

### Required artifact fields

- opaque public ID;
- artifact type;
- schema, payload, and render versions;
- lifecycle status;
- generated/published timestamps;
- product date/data-through date;
- source snapshot and sync-run references;
- team identity;
- public state and explanation;
- ordered frozen evidence;
- freshness;
- confidence/trust profile;
- limitations;
- routes;
- canonical copy and alt text;
- integrity hash;
- deduplication/equivalence identity;
- supersede/withdraw relations where applicable.

### Write path

1. authenticate founder/admin generation request or system job;
2. resolve exact trusted source authority;
3. run eligibility, freshness, evidence, limitation, and copy guards;
4. build normalized payload from canonical services;
5. compute integrity/equivalence identity;
6. return existing equivalent when appropriate;
7. persist draft;
8. complete required presentation prerequisites;
9. publish only after the complete contract passes;
10. record generated/refused/failed accounting.

### Read path

1. resolve public ID;
2. verify lifecycle status;
3. verify payload integrity before serving meaning-bearing content;
4. return only whitelisted public fields;
5. serve historical artifact independently from current-state availability;
6. load optional current comparison separately when its contract ships;
7. emit non-blocking Product Intelligence events.

### Lifecycle

- `draft`: not public;
- `published`: immutable and routable;
- `superseded`: original remains visible with replacement link and reason;
- `withdrawn`: preserve audit identity and reason; do not promote the claim.

### Current cutover state

The immutable artifact domain, generation/audit operations, team-progressive publication, public read API, and public historical share page are production foundations.

Current browser presentation may remain a transitional renderer. Canonical server-side social image/OG generation, complete copy/native-share/image-download actions, current-versus-shared comparison, and full distribution analytics remain separate gated capabilities.

## 14. API Boundaries

### Public APIs

Public endpoints expose purpose-built, whitelisted view models; stable public identifiers; freshness/lifecycle state; and honest 404/410/422/503 semantics as applicable.

They never expose internal database IDs where unnecessary, raw source responses, admin tokens, private notes, or mutable calculation objects.

### Internal browser surfaces

Internal browser routes require real server-side authorization, are absent from public navigation, use noindex/nofollow, do not place admin tokens in browser storage, do not rely on obscurity, and are read-only by default.

### Mutation safety

Every mutation requires explicit authorization, bounded scope, validation before write, transaction/rollback behavior, idempotency or duplicate protection, audit identity, post-commit verification, and an explicit confirmation step for dangerous actions.

## 15. Production Configuration Safety

Production must fail fast when required secrets or security boundaries are missing, including admin API credentials or equivalent operator authorization.

Secrets never enter the repository, frontend bundle, public logs, analytics payloads, or documentation examples.

## 16. Frontend Architecture

Frontend responsibilities:

- consume purpose-built public contracts;
- present answer-first hierarchy;
- render canonical public vocabulary;
- keep role/read/state/freshness layers distinct;
- route to exact evidence destinations;
- preserve honest loading/quiet/stale/error/integrity states;
- emit non-blocking Product Intelligence events;
- remain responsive and accessible.

Canonical frontend modules own public vocabulary and boundaries. Components may add presentation metadata, but may not reinterpret one canonical key into another baseball meaning.

Route metadata must distinguish historical share pages from current team pages, provide exact titles/descriptions, expose crawler-accessible metadata/assets when supported, and avoid falsely labeling an old artifact as current.

## 17. Performance and Resilience

- Public historical content should render without waiting for current comparison services.
- Frozen artifacts/assets use durable caching when safe.
- Current-state panels load independently.
- Analytics failure is invisible to the reader.
- Missing one evidence domain does not erase independent sections.
- Expensive generation is precomputed or founder-triggered rather than performed on every page request.
- Source retries use bounded backoff and do not create duplicate publications.

## 18. Local Development

### Prerequisites

- supported Python version;
- Node.js/npm;
- PostgreSQL;
- repository checkout;
- local environment variables from approved examples;
- no production secret reuse.

### Backend

Typical sequence:

```bash
python -m venv venv
source venv/bin/activate       # macOS/Linux
# venv\Scripts\activate       # Windows
pip install -r backend/requirements-dev.txt   # production installs backend/requirements.txt
# set local DATABASE_URL and FLASK_APP=app.py
flask db upgrade
pytest
```

Run exact repository commands from current setup/runbook documentation; this Manual owns the rules, not every shell variant.

### Frontend

```bash
cd frontend
npm install
npm run dev
npm test
npm run build
```

### Database migrations

- never edit an applied production migration;
- review upgrade and downgrade behavior;
- test against PostgreSQL, not only SQLite;
- preserve existing public artifacts and authority records;
- deploy migration before code that requires it;
- confirm production schema before enabling new generation paths.

## 19. Deployment Order

1. merge reviewed work through a branch/PR;
2. confirm tests and migration checks;
3. deploy backend/database contract first when compatibility requires it;
4. run migrations;
5. verify health and canonical public endpoints;
6. deploy frontend;
7. run production smoke tests;
8. verify trust/freshness and publication accounting;
9. enable scheduled/automatic behavior only after separately authorized, reviewed proof;
10. record completion in the Roadmap.

Never perform product expansion while a canonical source-authority incident is unresolved.

### Automated generated-content publication (D-053)

The order above governs human-authored work and is not weakened by this section. Reviewed
change still reaches production through a branch and a pull request.

There is exactly one exception, and it is a narrow one: the scheduled daily sync
regenerates the routed `/team/{ABBR}` preview pages from trusted publication authority and
commits them to `main` directly. That is permitted only because the job proves the tree
before the tree becomes public repository state:

```text
trusted publication
-> generate routed-team preview files
-> generated-delivery gate (fail closed)
-> canonical frontend tests and production build, against the generated tree
-> stage exactly the generated delivery paths
-> record the validated tree identity
-> commit under the machine identity, with run provenance
-> prove the commit's tree equals the validated tree
-> fast-forward push
```

Rules that make it defensible:

- the guarantee is **tree-exact, not commit-SHA-exact**. BaseballOS does not claim a SHA
  was tested before it existed; it claims, and proves, that the tree which passed
  validation is byte-for-byte the tree the commit carries;
- the frontend commands and Node major are mirrored from the canonical CI workflow, so the
  gate and CI cannot drift into validating different things;
- repository write authority belongs to that one job. Every other job in the workflow is
  read-only;
- automated commits are authored and committed as an explicit machine identity, never as a
  person. Automated history must remain separable from human history by
  `git log --format=%an` alone;
- staging is scoped to exact generated paths, never `git add .`, and change detection
  compares the index rather than the working tree so a newly generated file cannot be
  missed;
- the push is fast-forward only. A non-fast-forward push fails loudly rather than
  overwriting human work, and the previously published pages remain in place stating the
  baseball date they actually describe;
- no gate on this path may be soft-failed, and no PAT, GitHub App, or recursive workflow
  mechanism is used to make the automated push trigger a follow-up CI run.

Any future automated repository write must satisfy the same contract or it does not ship.

## 20. Production Smoke Tests

At minimum verify:

- application health;
- current product date and data-through date;
- schedule/finality for representative games;
- official starter and pitching-line agreement;
- decimal innings derived from recorded outs;
- roster/team assignment separation;
- team and pitcher evidence routes;
- Team State/public label consistency;
- trusted snapshot and team-progressive coverage;
- share artifact integrity and public page;
- auth refusal on internal routes;
- no silent stale/current fallback;
- monitoring and refusal accounting.

## 21. Testing and Shipping Gates

Required layers include pure domain tests, repository/migration tests, service tests, API contract tests, frontend tests, integration tests, deterministic fixture tests, production smoke tests, and regression tests for every material trust incident.

Critical fixtures include official starter mismatch, decimal-innings drift, traded player's historical appearance ownership, mixed starter/reliever ambiguity, incomplete ledger, stale/partial source, duplicate publication request, superseded artifact, integrity mismatch, historical page with current state unavailable, and unrelated late game not blocking team-progressive publication.

A release is not complete merely because tests are green. The public behavior, production authority, and operational accounting must also pass.

### Dependency audit gate

CI carries a standing `dependency-audit` job alongside the functional gates. It audits the backend runtime requirements file with a pinned scanner and checks frontend production findings against a reviewed accepted-risk contract. Development and build-time advisories are reported as information and never gate the build.

The gate is **read-only by design**. It never upgrades, pins, or edits a dependency, and no auto-upgrade or auto-merge path exists. Its only outputs are a report and a refusal; a human decides the remediation.

It refuses a build when a production advisory is unknown, expired, mismatched against the package it is attributed to, duplicated, or missing its required metadata — and also when an acceptance no longer corresponds to anything reported, so a solved advisory's exception must be deleted rather than left behind where it could silently suppress a recurrence. A scanner or network failure is distinguished from a clean audit rather than passing quietly.

Auditing declared requirements rather than the installed environment is deliberate: it measures what production actually ships instead of the CI runner's own tooling.

## 22. Observability

Operator-visible signals include:

- sync success/failure and duration;
- source coverage by domain/team/date;
- appearance-ledger completeness;
- official starter conflicts;
- trusted snapshot publish/refuse counts;
- team-progressive coverage and block reasons;
- artifact generated/reused/refused/failed/missing counts;
- render/integrity failures;
- public 404/410/error rates;
- stale/current state by surface;
- analytics delivery health;
- suppression reason distribution.

Operational dashboards explain the baseball/publication scope affected, not merely stack traces.

## 23. Incident and Repair Procedure

1. stop affected publication or distribution;
2. preserve source, logs, snapshots, and immutable history;
3. identify canonical authority and exact affected fields;
4. bound teams, games, dates, records, artifacts, and downstream evidence;
5. write a read-only repair plan and expected action counts;
6. verify rollback and idempotency;
7. apply through governed write paths;
8. run post-commit verification;
9. invalidate/rebuild dependent evidence;
10. republish through normal gates;
11. supersede/withdraw historical artifacts when meaning was wrong;
12. add regression coverage and update the relevant canonical document/runbook.

A repair is not closed until downstream public meaning is verified, not merely the database row.

### Proven operating shape

The July 2026 canonical-record incident closed through this shape, and it is now the standing
pattern for governed repair:

```text
governed repair -> independent closeout -> normal downstream work
```

Three properties made it terminal:

1. **The verifier is separate from the apply it verifies.** The closeout is a distinct read-only
   capability that performs no writes and cannot reapply the repair. An apply that grades its own
   homework proves nothing.
2. **Exact current reconciliation is the terminal proof.** Not "the repair ran" and not "no errors
   were raised" - the proof is that local and official records now agree exactly, with every
   governed check present, executed, and passed. Those are four separate facts; a check that could
   not run has not passed.
3. **A no-longer-needed one-action apply is not retried.** When a targeted, fingerprint-locked
   apply refuses because its reviewed manifest no longer regenerates, that is a correct terminal
   outcome. The capability is closed, not re-dispatched. A recurrence requires fresh diagnostic
   evidence and a new reviewed contract, never a repeat dispatch of an obsolete fingerprint.

## 24. Security and Privacy

- least privilege for tokens and operators;
- server-side auth for internal surfaces;
- no secrets in clients or logs;
- public IDs are identifiers, not access-control secrets;
- whitelist artifact/API fields;
- validate routes stored in artifacts;
- escape public copy;
- rate-limit expensive generation/comparison work;
- avoid raw IPs, sensitive data, and full user-agent strings in Product Intelligence;
- maintain non-affiliation and source attribution where appropriate;
- obtain rights/licensing review before commercial MLB-derived data use.

### Runtime dependency surface

The production dependency surface is kept deliberately smaller than the development one.

- `backend/requirements.txt` is the runtime set and is what production installs.
- `backend/requirements-dev.txt` pulls that set in and adds test-only packages, so a development environment is a superset of production rather than a different resolution.
- Test-only packages must not appear in the runtime set. Shipping one adds its advisories to the production surface for no runtime benefit.
- A declared frontend dependency with no import site is removed, not overridden. Deleting the package that carries an advisory is preferable to pinning around it.

Known dependency risk that cannot be removed today is accepted only as an explicit, revocable decision: exact advisory identifier, exact package, a hard expiry date, a tracking issue, and a written decision record that exists in the repository. Severity-level suppression, wildcard entries, and blanket ignore rules are not permitted, and an acceptance is invalid from 00:00 UTC on its expiry date. Where an acceptance depends on a compensating control in application code, that control's regression tests are part of the acceptance: weakening them voids it.

The dependency audit gate in §21 enforces this mechanically so an acceptance cannot outlive its review by being forgotten.

## 25. Operational Runbooks

Active detailed procedures remain under `docs/current/`, including setup, sync pipeline, intraday reconciliation, Share Cards operations, cutover, team-progressive publication, public artifact-page behavior, and the current dependency-security boundary.

Runbooks may be more detailed and may change more frequently. They do not override this Manual.

## 26. Known Technical Direction

Prioritized architecture work should follow product need:

- expand evidence payloads already held by the system;
- define and implement the first metric under the established Current Active-Pen Performance Contract;
- add canonical server-side share rendering and metadata;
- complete What Changed comparability;
- add pitch/leverage/rotation/depth domains in governed order;
- write durable daily state and observation memory;
- split large modules only when touched by approved work;
- avoid microservices, GraphQL, Kubernetes, or framework rewrites without a concrete incident or scale requirement.

## Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0 | July 29, 2026 | Nickolis Kacludis | Consolidated system architecture, domain boundaries, persistence, sync/publication order, team-progressive authority, immutable artifacts, APIs, security, deployment, testing, observability, and repair operations. |
| 1.1 | July 29, 2026 | Nickolis Kacludis | Recorded the proven governed-repair operating shape after the July 2026 canonical-record closeout: an independent verifier separate from the apply, exact current reconciliation as terminal proof, and a no-longer-needed one-action apply closed rather than retried. Removed completed appearance/starter repair hardening from prioritized technical direction. |
| 1.2 | July 29, 2026 | Nickolis Kacludis | Added the performance intelligence domain boundary establishing backend-owned canonical performance authority, no frontend recalculation, fail-closed publication below an approved sample, method-version and evidence ownership, upstream appearance-team attribution, immutable artifact freezing, and the metric registry as a governed definition set rather than a new subsystem. Updated prioritized technical direction now that the performance family contract is established. |
| 1.3 | July 30, 2026 | Nickolis Kacludis | Added exact-arithmetic, sample-unit, and refusal-distinctness rules to the performance intelligence domain: integer numerators and denominators, no floating point, a single ROUND_HALF_UP at the declared precision, thresholds stated in the denominator's unit, and a mathematical zero-denominator refusal kept separate from a governance below-sample refusal. Recorded that the merged framework is an unwired production-internal foundation whose approved parameters are not yet set. |
| 1.4 | August 12, 2026 | Nickolis Kacludis | Recorded the automated generated-content publication contract (D-053): generated repository writes are permitted only through a self-gating job that proves delivery integrity, runs the canonical frontend tests and production build against the exact generated tree, records that tree's identity, commits under an explicit machine identity with run provenance, proves the commit's tree equals the validated tree, and fast-forward pushes. Stated the guarantee as tree-exact rather than commit-SHA-exact, scoped repository write authority to that one job, and confirmed the ordinary branch/PR expectation for human-authored work is unchanged. |
| 1.6 | August 14, 2026 | Nickolis Kacludis | Absorbed D-051 into Section 8: removed generic manual founder/admin sync from the supported operational modes and stated explicitly that authoritative manual daily execution is not a supported mode, while preserving the separately governed operator paths — explicit-date backfill, read-only intraday audit, and separately authorized repair — that D-051 does not touch. Added a Current baseball-data authority subsection giving the platform-altitude answer that the subsystem runbooks previously answered alone: legacy writer authoritative, game-driven daily and postgame in `shadow` with backfill `off`, shadow granting no durable write or publication authority, automated write and authoritative modes unapproved, acquisition separated from publication, and any expansion requiring an explicit Decision Ledger entry. Reworded deployment step 9 so "manual proof" cannot be read as authorization for a manual daily run. Documentation reconciliation only: no sync mode, workflow, publication gate, write authority, schema, or dependency changed. |
| 1.5 | August 13, 2026 | Nickolis Kacludis | Recorded the runtime dependency surface as an architectural boundary: production installs the runtime requirements file only, development requirements are a superset that add test-only packages, test-only packages must not ship to production, and an unused frontend dependency is removed rather than overridden. Stated the accepted-risk standard for dependency advisories that cannot be removed today — exact advisory identifier, exact package, hard expiry, tracking issue, and an existing decision record, with no severity suppression, wildcards, or blanket ignores, and with any compensating control's regression tests forming part of the acceptance. Added the standing read-only dependency audit gate to the shipping gates: it audits declared requirements rather than the installed environment, treats development and build advisories as informational, distinguishes scanner failure from a clean audit, refuses unknown, expired, mismatched, duplicated, under-documented, or no-longer-reported entries, and never upgrades or edits a dependency itself. No baseball semantics, publication gate, sync mode, API, deployment process, or write authority changed. |
