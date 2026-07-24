# Share Cards — Active-Bullpen Readiness Trust Contract (SC-03B-07)

A founder-approved **upstream readiness-contract correction**. It is NOT an SC-02
eligibility relaxation: SC-02 still refuses low / incomplete / `data_limited` and
remains the sole Team State eligibility/payload authority. The change is confined
to how **team-level** Team Operations Readiness trust is computed; the shared
per-pitcher availability classifier (`services/availability.py`) is unchanged, so
the live board/availability displays are unaffected.

## Why

Every MLB team was refused a Team State Share Artifact with
`incomplete_evidence` / `insufficient_trust` / `unsupported_team_state`
(`data_state:incomplete`, `confidence:low`, `status_code_unsupported:data_limited`),
because the old team-level trust:

- aggregated over the **whole `team_id` pitcher set** (including inactive / injured
  / optioned / stale records), and
- collapsed the entire team to `low` / `incomplete` if **any single** record was
  non-fresh (an `any()` collapse), and
- treated an active pitcher with no appearance in 14 days as `stale` even when the
  completed appearance ledger was current, and
- could never emit team-level `medium` even though it is approved vocabulary that
  SC-02 already accepts.

Result: a normal bullpen (which always has at least one rested / recently-recalled
/ incomplete-data arm) never qualified.

## The approved contract

### 1. Current active-bullpen scope
Team trust is computed from the **canonical current active bullpen only** —
active-roster relievers — via the existing authorities, never `Pitcher.team_id`
or `Pitcher.active` (which means "assigned to an org", true for IL/optioned):

- Membership: `api.bullpen.build_team_roster_authority(team_id, reference_date)`
  → `evidence['bullpen_arms']` (active roster via `roster_status.classify_roster_status`,
  reliever via Role Authority), gated by the public roster-readiness source. If the
  roster source is not READY, the authority is empty → **fail closed to `unknown`**
  (an unknown assignment is never silently treated as active).

### 2. Usable current record (rested ≠ stale)
An active-bullpen record is **usable** when its per-record `data_state` is `fresh`,
**or** it is rest-`stale` (no appearance in the active window) AND the completed
appearance ledger is provably complete through the product date
(`services.appearance_ledger.build_appearance_ledger(end_date).complete`) — then a
missing appearance is a **valid observed rest**, not stale source data. Otherwise
(missing / incomplete data, an unproven-rest stale record, or a fetch failure) the
record is **unresolved**. An incomplete ledger is never converted into observed zero.

### 3. Team confidence (deterministic, integer-only)
With `active` = active-bullpen count, `usable`, `unresolved = active − usable`:

- **high** — authority complete, source current, no conflict, `usable == active`.
- **medium** — authority complete, source current, no conflict, and bounded partial
  coverage: `usable*4 ≥ active*3` (≥75%) AND `usable ≥ 6` AND `unresolved ≤ 2`.
- **low** — authority complete but coverage below the medium bar, a material source
  conflict, an incomplete required window, or a stale source.
- **unknown** — no authoritative active bullpen (fail closed; never downgraded to
  low/medium).

Worked examples: 8 arms → 8 usable high; 6–7 usable medium; ≤5 low. 9 arms → 9
high; 7–8 medium; ≤6 low. 7 arms → 7 high; 6 usable/1 unresolved medium; ≤5 low.
5 arms → high only if all 5; never medium (six-usable minimum); else low.

### 4. Team data_state
`fresh` for high/medium (bounded partial coverage still "fresh" — the caveat rides
in the limitation); `incomplete` for coverage-insufficient low; `stale` for a
genuinely outdated source; `missing`/`unknown` when there is no authority.

### 5. Medium limitation
A medium read carries an explicit, guard-safe limitation stating record counts
only — never a pitcher identity, health claim, or intent:

> "Current readiness reflects 6 of 8 active bullpen pitchers; 2 have incomplete
> current workload records."

The structured form is `{code: partial_active_bullpen_coverage, active_bullpen_count,
usable_record_count, unresolved_record_count}`.

### 6. SC-02 unchanged
SC-02 still accepts only `high`/`medium` confidence and the three supported
`operationally_*` states; `data_limited` is never added to the supported registry;
low/incomplete/stale/missing still refuse. The readiness producer now correctly
yields high/medium-fresh for sufficient current active-bullpen coverage, so
legitimate teams reach a supported state without touching SC-02.

## Where it lives

- `services/team_readiness_coverage.py` — the pure, deterministic coverage
  contract (`assess_team_coverage` → high/medium/low/unknown + data_state + the
  structured limitation). Integer-only 75% math; no float drift.
- `api/team_operations.py::_team_operations_trust_metadata` — resolves active-bullpen
  membership + per-record usability (ledger-aware rest) and calls the contract. The
  no-records path is unchanged (`unknown`/`missing`).
- `team_operations/bullpen_readiness.py::_readiness_status_code` — the team trust is
  now the canonical coverage authority, so the raw whole-active
  `coverage_inventory`/`handedness` gates no longer force `data_limited` for a
  high/medium team (they still fail closed for low/unknown and refine
  constrained/stressed). This is what lets bounded-partial (medium) coverage reach a
  supported status.

The shared canonical readiness source stays the only source — no Share-Card-specific
fork, no second roster registry, no second readiness engine.

## Live Team Operations consumer impact

`GET /api/team-operations/bullpen-readiness` is internal (`frontend_exposure=False`);
team-level `trust_metadata`/`status_code` never reaches the browser directly.
Backend explanation consumers (`explanations/readiness.py`, `availability.py`) and
the indirect V4 explanation / story-card frontend paths already handle `medium`
safely (`medium → 'limited'` / `'Partial Read'`). The intended live effect is that
teams with sufficient current active-bullpen coverage now report a supported state
(and generate artifacts) instead of universal `data_limited`. Teams without READY
roster-status coverage fail closed to `unknown`/`data_limited` — in production the
daily roster sync maintains this coverage.

## Verification

- `tests/test_team_readiness_coverage.py` — the pure contract (thresholds, worked
  examples, fail-closed unknown, integer determinism).
- `tests/test_active_bullpen_readiness_resolver.py` — REAL-resolver end-to-end (no
  fake resolver): a complete active bullpen → `high` + supported status; bounded
  partial (6/8) → `medium` + supported + limitation; insufficient (5/8) → `low` /
  `data_limited`.
- Full backend suite green (3800 passed, 3 skipped); frontend 822 passed; build ok;
  diff-freeze/QA-reconciliation guards green (`backend/api/team_operations.py`
  allowlisted).

## Real-resolver immutable-artifact proof (completion gate)

`tests/test_active_bullpen_artifact_publication.py` drives the **full** generation
flow with NO injected resolver and NO mocked eligibility/payload/generation — only
the trusted-snapshot authority is monkeypatched (external daily-publication infra):

- **High** (8/8 usable, plus an IL reliever and a starter on the team that do not
  collapse the read) → `generate_team_state_artifact` publishes an immutable
  artifact (published lifecycle, correct team/snapshot/product_date/version,
  integrity verified, `generated` audit); a rerun reuses the same `public_id` with
  no duplicate; the compatibility projection consumes it (`confidence=high`).
- **Medium** (6/8 usable) → publishes with `confidence=medium`, a supported status,
  and the structured partial-coverage limitation **preserved on the immutable
  document**; rerun reuses; the compatibility projection keeps `confidence=medium`
  (never converts to high).
- **Low** (5/8 usable) → refused, no artifact, durable audit preserves the exact
  reasons (`incomplete_evidence` / `insufficient_trust` / `unsupported_team_state`,
  `data_state:incomplete` / `confidence:low` / `status_code_unsupported:data_limited`).
- **Mixed real batch** (`generate_team_state_artifacts_batch` over high/medium/low)
  → generated / generated / refused, accounting invariant holds, `missing=0`, two
  published artifacts; rerun → reused / reused / refused, no duplicates.
- **Role Authority**: active-roster relievers included; a confirmed starter and an
  IL reliever excluded (neither counts toward nor collapses coverage); a team with
  no authoritative active-roster status fails closed → refused.

### Payload-builder completeness fix

The real-resolver medium test revealed a concrete integration defect: the SC-02
canonical document dropped the readiness `trust_metadata.limitations`, so a
published medium artifact lost its partial-coverage limitation. Fixed narrowly in
`services/team_state_payload.py` — the document's `trust.limitations` now preserves
the governed limitations deterministically (no threshold, vocabulary, immutability,
or dedup-semantics change; SC-02 gates unchanged).

## Production verification (required before relying on it)

After deploy: confirm the deployed commit; let the next trusted snapshot publish (or
invoke `POST /api/internal/share-artifacts/team-state/batch` for the latest
authoritative snapshot); refresh `/internal/share-artifacts/operations` and confirm
`accounted=30`, `missing=0`, `generated+reused ≥ 1`, `artifacts ≥ 1`, and record the
high/medium/low team distribution. Then verify one artifact (public_id, team,
snapshot, product_date, confidence, data_state, limitation if medium, integrity,
compatibility-projection load). Refusals remain acceptable for teams that genuinely
fail the approved coverage contract.

## SC-04 gate

Still blocked until at least one legitimate production artifact exists after this
change is deployed and verified.
