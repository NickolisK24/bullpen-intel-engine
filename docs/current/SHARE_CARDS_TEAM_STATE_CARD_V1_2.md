# Share Cards — Team State Card v1.2 (code-rendered card baseline)

**Status:** Current. Ships the approved code-rendered Team State card WITHOUT
performance metrics (SC-04B v1.2). No DB migration — `payload` / `trust_metadata` are
`db.JSON`, `SHARE_ARTIFACT_SCHEMA_VERSION` stays `1.0.0`, and prior 1.0.0 / 1.1.0
artifacts are unchanged and integrity-valid. See the decision record
`docs/decisions/2026-07-25-team-state-card-v1-2-semantics.md`.

## Payload contract — `team-state-1.2.0`

Registered in `services/team_state_payload.py`; `TEAM_STATE_LATEST` points to it and
1.0.0 / 1.1.0 stay registered. It is built on the v1.1.0 document and adds one
backend-owned `card` block:

- `artifact_context` — `publication_scope`, `publication_label`, `historical_note`,
  `data_through`. Scope comes from the DURABLE `subject_type` discriminator via
  `services/share_artifact_scope.py`, never the numeric `source_snapshot_id`. The
  artifact's own `generated_at` / `published_at` are NOT frozen here (unknown at build
  time); the public read supplies them from columns.
- `team` — `team_id`, `canonical_name`, `abbreviation`.
- `state` — `public_state`, `public_label`, `headline`, `why` (reused from the
  deterministic public copy).
- `readiness_summary` — the four metrics below.
- `reliever_evidence` — the bounded, ordered rows below.
- `trust` — `confidence`, `coverage_statement`, `source_statement`.
- `limitations` — durable only (transient runtime states are never frozen).

The document is deterministic — no build-time clock — so the same governed slate yields
a byte-identical document (idempotent rerun; genuinely new evidence mints a new
artifact). It carries NO performance metric and NO league rank: both are UNSUPPORTED
without a team-at-appearance authority and are deferred.

## Card metrics authority — `services/team_state_card_metrics.py`

`build_team_state_card_metrics(team_id, *, reference_date)` composes existing canonical
authorities only; `reference_date` is the governed slate (`snapshot.data_through`).

- **CLEAN OPTIONS** — `{clean_count} of {active_count}` from the bullpen optionality
  authority + canonical active-bullpen membership.
- **MULTI-USE ARMS** — active arms appearing in ≥2 of the last **three completed TEAM
  games** (not three calendar days; off days never enter; a doubleheader is two distinct
  `game_pk` window entries; the just-completed trigger game is included).
- **SHORT-REST ARMS** — zero or one day of rest, measured to the slate.
- **LEFT-HANDED OPTIONS** — usable-option LHP of active-bullpen LHP (documented
  denominator; injured/inactive already outside membership; unavailable/unresolved
  excluded).

`reliever_evidence` rows carry: pitcher id (internal), display name, last-3-game
appearances, recorded outs (+ innings text), last appearance date, last opponent abbrev,
rest days, and a CANONICAL availability label (Available / Monitor / Limited / Avoid /
Unavailable — never a card-only Normal/Stressed/Tired label). Rows are bounded to six and
ordered by the governed selection order: more restrictive availability → more window
appearances → more recorded outs → more recent appearance → stable pitcher id / name. No
recommendation language.

## Public read + card component

`services/share_artifact_public.py` projects the frozen `card` block and enriches
`artifact_context` with the artifact's `generated_at` / `published_at` from columns. The
React `TeamStateArtifactCard` (`frontend/src/components/share/TeamStateArtifactCard.jsx`)
renders masthead header → hero → Bullpen at a Glance → Current Bullpen Evidence → trust
strip → footer in the existing BaseballOS design tokens — no fake progress bars,
gradients, generated logos, imagery, or mobile horizontal scroll. The public page renders
the card first for a 1.2.0 artifact and keeps the historical/immutable explanation and
methodology / Data & Trust / current-bullpen destinations; older artifacts keep their
existing components verbatim.

## Operations — league / progressive separation

The operator surface reports two SEPARATE summaries on one dashboard and never combines
their counts:

- **Latest League Batch** — `build_coverage_overview` (all-or-nothing league snapshot
  coverage), unchanged.
- **Latest Progressive Event** — `build_latest_progressive_event`: trigger game, game
  date, teams, checkpoint ids, attempted / generated / reused / refused / failed /
  missing, public ids, integrity, and timestamp for ONE progressive event.

Artifacts are scoped by the DURABLE `subject_type` discriminator; the progressive
`request_source` is only event/audit context. A missing progressive event returns
cleanly (`has_event=false`). Both summaries ride the same authenticated
`/operations/overview` response (`progressive_event` key) — one dashboard, one auth
boundary.

## Parity

Equivalent progressive and league evidence on the SAME slate yield equivalent readiness
(state / why / readiness_summary / reliever rows) with DISTINCT provenance, scope labels,
and identities.

## Tests

`backend/tests/test_team_state_card_v1_2.py`,
`backend/tests/test_share_artifact_operations_progressive.py`,
`backend/tests/test_team_state_card_semantics.py`,
`frontend/tests/teamStateArtifactCard.test.mjs`,
`frontend/tests/shareArtifactOperations.test.mjs`,
`frontend/tests/publicShareArtifact.test.mjs`.
