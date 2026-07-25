# Decision: Team State artifact v1.2 — semantic/trust correctness + card baseline scope

- **Date:** 2026-07-25
- **Status:** In progress (founder-directed). Semantic/trust correctness fixes implemented
  and validated; performance-context card baseline scoped by the data-authority audit.
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

## Deferred (next increment on this branch)

The `team-state-1.2.0` contract (artifact_context + readiness_summary + bounded reliever
evidence, no performance context), a code-rendered `TeamStateArtifactCard` component,
and the operations league/progressive summary separation are the identified next
increment (no migration required). The performance-context metrics + ranks remain
blocked on the missing data authorities above.

## Consequences

- Progressive and league artifacts are correctly labelled by scope; no artifact freezes
  a transient runtime state; a high-confidence read never contradicts itself; the league
  batch resolves instead of refusing all 30 teams.
- Existing immutable artifacts (Giants/Angels/Arizona and all 1.0.0/1.1.0) are unchanged
  and integrity-valid; snapshots 272/274/275 are untouched. SC-02, readiness thresholds,
  public vocabulary, and the payload envelope are unchanged. SC-05 remains blocked.

## References

- `services/share_artifact_public.py` (scope-aware public projection)
- `services/team_state_payload.py` + `services/sync_metadata.py` (transient-limitation filter)
- `services/team_state_public_copy.py` (trust/evidence reconciliation)
- `services/share_artifact_generation.py` (symmetric league/progressive slate anchor)
- `frontend/src/components/share/PublicShareArtifactPage.jsx` (scope-aware label + note)
- Tests: `tests/test_team_state_card_semantics.py`, `frontend/tests/publicShareArtifact.test.mjs`
