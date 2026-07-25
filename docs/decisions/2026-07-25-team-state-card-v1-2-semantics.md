# Decision: Team State artifact v1.2 — semantic/trust correctness + card baseline scope

- **Date:** 2026-07-25
- **Status:** Implemented (founder-directed). Semantic/trust correctness fixes AND the
  approved card baseline (team-state-1.2.0, no performance metrics) implemented and
  validated; performance-context + ranks remain deferred by the data-authority audit.
- **Scope:** Public Team State Share Artifact semantics + the readiness trust contract's
  public copy + the LEAGUE readiness reference date. NOT an SC-02 change; no readiness
  threshold, public vocabulary, coverage-contract, or payload-envelope change.

## Context — production run 476

Progressive publication passed its first real production test (game 823196 SF/LAA →
2/2 generated, fatigue-before-progressive, league snapshot 275 published). But the
resulting public artifacts exposed semantic/trust defects, and the same run's LEAGUE
snapshot-275 batch refused all 30 teams.

## Investigation-first — data-authority audit (report before branching)

Four parallel read-only investigations traced the defects and the proposed card data.
The performance-context section of the approved card is **not truthfully supportable**
today, and per the founder's Phase-5 rule it is reported, not invented:

- **Bullpen ERA, blown saves, save conversion, inherited-runners-scored %** — the raw
  per-appearance fields exist on `GameLog`, but `GameLog` has **no team-at-appearance
  field**; team is resolved only via the pitcher's CURRENT `Pitcher.team_id`. Every
  season-to-date team aggregate therefore misattributes traded pitchers and drops
  departed relievers; there is no full-team-contributor aggregation and no season
  completeness gate (only a trailing 10-day window is enforced). **UNSUPPORTED** for a
  truthful team number.
- **30-team synchronized MLB rank** — no service computes any of these metrics for all
  30 teams on a common data-through date, and there is no rank computation anywhere.
  **UNSUPPORTED.**
- Readiness-summary metrics: **clean options, short-rest arms, LHP options** are
  supported from canonical authorities; **multi-use arms** is derivable but net-new
  (`ScheduledGame` ⋈ `GameLog`).
- A `team-state-1.2.0` payload contract needs **no DB migration** — `payload`/
  `trust_metadata` are `db.JSON`, a registry addition only; `SHARE_ARTIFACT_SCHEMA_VERSION`
  stays `1.0.0` and prior 1.0.0/1.1.0 artifacts stay valid.

**Founder decision:** build the card baseline WITHOUT the unsupported performance
context and ranks. The performance metrics require a new team-at-appearance authority
+ season aggregation + a synchronized 30-team rank service (a separate data-infra
project), and are deferred.

## Decision — semantic/trust correctness (implemented)

1. **Scope-aware label from the durable discriminator.** The public read projects a
   backend-owned `publication_scope` from `source_authority_type` (never the numeric
   `source_snapshot_id`): `team_progressive` → "Published Team Bullpen State"; league /
   NULL → "Published BaseballOS Snapshot", each with a scope-correct historical note. The
   page label and note branch on it; a numeric id collision cannot change scope.
2. **No transient runtime limitation is frozen.** The `latest_sync_running` limitation
   ("A sync is currently running…") is classified TRANSIENT and dropped at the artifact
   freeze point, so a momentary process state is never baked into an immutable artifact.
   Durable evidence limitations pass through; the LIVE surface still shows the banner;
   existing artifacts are unchanged.
3. **Trust/evidence reconciled in the public copy.** A high/medium-confidence read no
   longer surfaces the coarse whole-`Pitcher.active` `coverage_inventory` "N active
   bullpen records are missing current data" receipt beside its "verified / based on the
   current active bullpen" trust line. That count is a DIFFERENT population than the
   canonical active-bullpen coverage authority that sets confidence (high ⇒ unresolved
   == 0). The reconciliation is scoped to the public-copy authority only; the medium
   read still carries its precise bounded-coverage limitation, a low/unknown read (SC-02
   refuses it) keeps the caveat, and the shared readiness constraint contract + other
   surfaces (V4 explanations) are unchanged.
4. **League readiness anchored symmetrically.** The all-30-team LEAGUE refusal on run
   476 was the SAME slate/reference-date mismatch already fixed for the progressive read
   — the global availability reference date advances to the day after the slate while
   roster snapshots are dated at the slate. The reference-date slate anchor now applies
   to BOTH a team-progressive checkpoint AND a trusted/current league serving snapshot
   (guarded by the freshness verdict), so the league batch resolves the roster authority
   for the snapshot's slate. It still fails closed unchanged when the slate has no roster
   snapshot; league all-or-nothing publication is preserved.

## Card baseline — team-state-1.2.0 (implemented)

The approved card baseline WITHOUT performance metrics is now built on this branch. No
DB migration was required (`payload`/`trust_metadata` are `db.JSON`;
`SHARE_ARTIFACT_SCHEMA_VERSION` stays `1.0.0`; prior 1.0.0/1.1.0 artifacts are unchanged
and integrity-valid).

1. **`team-state-1.2.0` payload contract.** A new registry contract, built on v1.1.0,
   adds a single backend-owned `card` block: a frozen `artifact_context` (scope +
   `data_through`), the canonical `team` identity, the public `state` (public state +
   headline + why, reused from the deterministic public copy), a four-metric
   `readiness_summary`, a bounded `reliever_evidence` table, a reader-facing `trust`
   triplet, and durable-only `limitations`. `TEAM_STATE_LATEST` now points to it; 1.0.0
   and 1.1.0 stay registered. It carries NO performance metric and NO league rank — both
   remain UNSUPPORTED per the audit above. The document is deterministic (no build-time
   clock); an identical governed slate yields a byte-identical document, so a rerun
   reuses and genuinely new evidence mints a new artifact.
2. **Card-metrics authority (`services/team_state_card_metrics.py`).** Composes existing
   canonical authorities only. CLEAN OPTIONS from the bullpen optionality authority
   (`{clean_count} of {active_count}`); MULTI-USE ARMS = active arms appearing in ≥2 of
   the last THREE COMPLETED TEAM GAMES (not three calendar days; off days never enter;
   a doubleheader is two distinct `game_pk` window entries; the just-completed trigger
   game is included); SHORT-REST ARMS on zero/one day rest, measured to the slate;
   LEFT-HANDED OPTIONS = usable-option LHP of active-bullpen LHP (documented
   denominator; unavailable/unresolved excluded). Reliever rows are bounded to six and
   ordered by the governed selection order (more restrictive availability → more window
   appearances → more recorded outs → more recent appearance → stable id/name). Every
   row carries a CANONICAL availability label — never a card-only Normal/Stressed/Tired
   label — and no recommendation language.
3. **Public read + code-rendered card.** The public read projects the frozen `card`
   block, enriching `artifact_context` with the artifact's own `generated_at` /
   `published_at` from columns (not frozen). The React `TeamStateArtifactCard` renders
   masthead header → hero → Bullpen at a Glance → Current Bullpen Evidence → trust strip
   → footer, in the existing BaseballOS design tokens, with no fake progress bars,
   gradients, generated logos, imagery, or mobile horizontal scroll. The public page
   renders the card first for a 1.2.0 artifact and keeps the historical/immutable
   explanation and destinations; older artifacts keep their existing components verbatim.
4. **Operations league/progressive separation.** The operator surface now reports two
   SEPARATE summaries on one dashboard and never combines their counts: the all-or-
   nothing LEAGUE batch coverage, and a LATEST PROGRESSIVE EVENT (trigger game, date,
   teams, checkpoint ids, attempted/generated/reused/refused/failed/missing, public ids,
   integrity, timestamp). Artifacts are scoped by the DURABLE `subject_type`
   discriminator; the progressive `request_source` is only event/audit context. A
   missing progressive event returns cleanly.
5. **Parity.** Equivalent progressive and league evidence on the SAME slate yield
   equivalent readiness (state/why/readiness-summary/reliever rows) with DISTINCT
   provenance, scope labels, and identities.

The scope-label authority was centralized (`services/share_artifact_scope.py`) and is
reused by both the public read and the immutable card payload, so a frozen artifact and
its public read describe the same scope in the same words.

## Still deferred

The performance-context metrics + 30-team synchronized ranks remain blocked on the
missing data authorities (a team-at-appearance authority + season aggregation + a
synchronized 30-team rank service — a separate data-infra project). SC-05 remains
blocked.

## Consequences

- Progressive and league artifacts are correctly labelled by scope; no artifact freezes
  a transient runtime state; a high-confidence read never contradicts itself; the league
  batch resolves instead of refusing all 30 teams.
- Existing immutable artifacts (Giants/Angels/Arizona and all 1.0.0/1.1.0) are unchanged
  and integrity-valid; snapshots 272/274/275 are untouched. SC-02, readiness thresholds,
  public vocabulary, and the payload envelope are unchanged. SC-05 remains blocked.

## References

- `services/share_artifact_public.py` (scope-aware public projection + v1.2 card projection)
- `services/share_artifact_scope.py` (centralized scope-label authority)
- `services/team_state_card_metrics.py` (readiness_summary + bounded reliever_evidence)
- `services/team_state_payload.py` (team-state-1.2.0 contract) + `services/sync_metadata.py`
  (transient-limitation filter)
- `services/team_state_public_copy.py` (trust/evidence reconciliation)
- `services/share_artifact_generation.py` (symmetric league/progressive slate anchor)
- `services/share_artifact_operations.py` + `api/share_artifact_operations_api.py`
  (league/progressive summary separation)
- `frontend/src/components/share/TeamStateArtifactCard.jsx` (the code-rendered card)
- `frontend/src/components/share/PublicShareArtifactPage.jsx` (v1.2 card-first + scope note)
- `frontend/src/components/admin/ShareArtifactOperations.jsx` (two separate summaries)
- Tests: `tests/test_team_state_card_v1_2.py`, `tests/test_team_state_card_semantics.py`,
  `tests/test_share_artifact_operations_progressive.py`,
  `frontend/tests/teamStateArtifactCard.test.mjs`,
  `frontend/tests/publicShareArtifact.test.mjs`, `frontend/tests/shareArtifactOperations.test.mjs`
