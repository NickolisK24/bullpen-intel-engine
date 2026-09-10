# Decision — Canonical public Team State vocabulary + deterministic backend-owned Share Card copy

- Status: Accepted
- Date: 2026-07-24
- Sprint: BaseballOS Share Cards SC-04B (Canonical Baseball Voice + Public Share Page Production Polish)
- Supersedes/relates: SC-04 (public Share Artifact API + page), SC-02 (canonical payload builder), SC-03B-07 (active-bullpen readiness trust)

## Context

The deployed SC-04 public citation page (`/share/{public_id}`) rendered a real,
integrity-verified immutable artifact but exposed internal Team Operations
language to the public: the state label `Operationally Stressed`, the engine why
sentence "Team-level bullpen readiness is stressed by current workload or
availability constraints.", raw internal evidence enums (`availability_distribution`,
`coverage_inventory`, `handedness_coverage`, `workload_pressure`), and raw ISO
timestamps.

The Product Vision Specification (`docs/product/product-vision-specification.md`,
§2 "The vocabulary is the interface") defines the canonical public Team State
dictionary as **Fresh / Stretched / Vulnerable**. The implemented public labels
(`Operationally Stable/Constrained/Stressed`, from the explicitly internal
`team_operations/contracts.py::READINESS_STATUSES`) conflicted with it, and no
authoritative internal→public mapping existed. Per the SC-04B Workstream A STOP
rule, this vocabulary-authority conflict was surfaced for a founder decision
rather than resolved silently.

## Decision (founder, final)

1. The public Team State vocabulary is exactly: **Fresh / Stretched / Vulnerable**.
2. The one canonical deterministic mapping is:
   - `operationally_stable` → **Fresh**
   - `operationally_constrained` → **Stretched**
   - `operationally_stressed` → **Vulnerable**
3. `data_limited` is not publicly published (it remains an internal fail-closed
   state; SC-02 eligibility already refuses it).
4. `refused` is never publicly published as a Team State artifact.
5. No fourth public Team State is introduced. Growth of the public dictionary is
   a separate reviewed product decision.
6. Public labels come from an explicit canonical mapping, never by title-casing an
   internal enum.
7. Share Artifact public copy is **deterministic and backend-owned**. The
   immutable artifact — not the page and not the renderer — owns the public state,
   headline, why sentence, evidence display labels/copy, freshness language, trust
   language, limitation copy, alt text, and platform-neutral description.
8. **No AI-generated baseball analysis** is permitted; the copy authority calls no
   external language service and produces byte-identical copy for identical
   governed input.
9. Internal engine vocabulary may not leak into public artifact copy. A fail-closed
   banned-language guard runs before publication.

## Consequences / implementation

- New public-language owner: `backend/services/team_state_public_vocabulary.py`
  (state map, evidence display labels, banned-language guard) and the copy
  authority `backend/services/team_state_public_copy.py`.
- Payload contract `team-state-1.1.0` adds a `public_copy` block to the immutable
  document (registered alongside `team-state-1.0.0`; the generation path publishes
  the latest). Meaning-bearing copy lives in the payload, so it participates in the
  existing equivalence + integrity hashes automatically. `schema_version` and the
  Share Artifact table are unchanged; `render_version` tracks `payload_version` by
  the existing convention.
- Legacy `team-state-1.0.0` artifacts remain immutable, integrity-valid, and
  publicly readable. The public read service maps their coded state label and
  coded evidence families to reader-facing presentation (version-aware display of
  coded metadata) while preserving the original stored why sentence verbatim.
- `data_limited` / `refused` were already excluded from publication by SC-02
  eligibility (`SUPPORTED_TEAM_STATE_CODES`); the copy authority additionally fails
  closed if asked to build public copy for an unmapped internal state.

## Explicitly not done

- No retroactive rewrite of any published artifact (the Arizona production artifact
  and all legacy artifacts are untouched and remain immutable).
- Not "Share Cards V2": the artifact type is unchanged; this is the smallest valid
  backward-compatible payload-version increment.
- No SC-05 current-versus-shared, no renderer replacement, no PNG/Open Graph, no
  share/download controls, no live/current-state lookup.
