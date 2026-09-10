# Decision: Active-Bullpen Readiness Trust Contract (SC-03B-07)

- **Date:** 2026-07-24
- **Status:** Approved (founder decision) and implemented
- **Scope:** Team Operations Readiness team-level trust (shared, live). NOT an SC-02
  change.

## Context

Under the prior contract, all 30 MLB teams were refused a Team State Share Artifact
because team-level readiness collapsed to `data_limited` whenever any single
rostered pitcher had a non-fresh/incomplete record. Diagnosis (SC-03B-05/06)
established the cause was upstream and under-specified: whole-roster scope + an
`any()` collapse + a rest-as-stale conflation + an unreachable team-level `medium`.
No approved contract defined a partial-coverage sufficiency threshold.

## Decision

Adopt an **active-bullpen coverage trust contract**:

1. **Scope** team trust to the canonical current active bullpen (active-roster
   relievers via `roster_status.classify_roster_status` + Role Authority), gated by
   the public roster-readiness source; fail closed to `unknown` when the roster
   authority is unavailable. Do not scope from raw `Pitcher.team_id`/`Pitcher.active`.
2. **Rest ≠ stale:** an active reliever with no appearance in the active window is a
   usable *observed rest* when the completed appearance ledger
   (`appearance_ledger.build_appearance_ledger`) is provably complete through the
   product date; otherwise unresolved. Never fabricate an observed zero from an
   incomplete ledger.
3. **Team confidence** high / medium / low / unknown, where **medium** = bounded
   partial coverage: ≥75% usable AND ≥6 usable AND ≤2 unresolved (deterministic
   integer math). high = all usable; low = below the bar / conflict / stale /
   incomplete window; unknown = no authority.
4. **data_state** = fresh for high/medium, incomplete for coverage-insufficient low,
   stale for outdated source, missing for no authority.
5. **Medium** carries an explicit, guard-safe limitation with record counts only.
6. **SC-02 unchanged** — still accepts only high/medium + `operationally_*`; still
   refuses low/incomplete/`data_limited`.

## Consequences

- Teams with sufficient current active-bullpen coverage now report a supported
  readiness state and can generate legitimate Team State Share Artifacts.
- The shared live Team Operations readiness output changes (internal route only;
  consumers audited medium-safe). Teams without READY roster-status coverage fail
  closed to `data_limited`.
- Trust remains conservative: no trust/evidence/freshness/limitation gate was
  weakened; `data_limited` was not added to the supported Team State registry.

## Accepted caveat

BaseballOS has no officially-stored reliever partition; the reliever narrowing of
the active bullpen uses the existing usage-derived Role Authority (the canonical
repo mechanism). Approved on that basis.

## References

- `docs/current/SHARE_CARDS_ACTIVE_BULLPEN_READINESS_TRUST.md`
- `services/team_readiness_coverage.py`,
  `api/team_operations.py::_team_operations_trust_metadata`,
  `team_operations/bullpen_readiness.py::_readiness_status_code`
- Tests: `tests/test_team_readiness_coverage.py`,
  `tests/test_active_bullpen_readiness_resolver.py`
