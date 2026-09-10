# BaseballOS V2.5 Phase 18 Maintenance Warning Remediation Review

## Status

BaseballOS V2.5 Phase 18 Maintenance Warning Remediation Review is complete.

This is a maintenance and governance review. It does not add product
features, change Recommendation Engine behavior, change fatigue formulas,
change API contracts, add frontend feature work, add ranking logic, add
selection logic, or add prediction logic.

## Warning Inventory

Initial backend validation command:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-warning-review
```

Initial result:

```text
278 passed, 0 failed, 139 warnings
```

Warning categories observed:

| Category | Count | Source |
|----------|------:|--------|
| datetime UTC deprecation from SQLAlchemy model defaults | 116 | `datetime.utcnow` default callables on `DateTime` columns |
| datetime UTC deprecation from backend test fixtures | 22 | `datetime.utcnow()` in two backend test fixture helpers |
| SQLAlchemy legacy query API | 1 | `Pitcher.query.get_or_404()` in the bullpen pitcher detail route |
| pytest temp/cache permission warnings | local status only | `.pytest-tmp-*` and `.pytest_cache` permission noise in local git status |

No ranking, selection, prediction, recommendation, or API-contract warning
category was discovered.

## Warning Classification

| Category | Classification | Risk | Decision |
|----------|----------------|------|----------|
| datetime UTC deprecation from SQLAlchemy model defaults | remediation recommended | Future Python runtime behavior can become stricter; current timestamps remain naive UTC. | Fixed now with a naive UTC helper that preserves existing storage shape. |
| datetime UTC deprecation from backend test fixtures | remediation recommended | Test noise can hide real warnings and will worsen under stricter runtimes. | Fixed now with the same naive UTC helper. |
| SQLAlchemy legacy query API | remediation recommended | SQLAlchemy 2.x compatibility risk; current behavior is simple primary-key lookup plus 404. | Fixed now with `db.session.get()` and explicit `abort(404)`. |
| pytest temp/cache permission warnings | harmless | Local generated artifact permissions can affect `git status` output but not test behavior. | Deferred; do not stage temp/cache artifacts. |
| prototype Prospect API `get_or_404()` scan findings | monitor | Not emitted by the current backend warning run and not part of the certified V2 warning debt. | Deferred pending focused prototype route coverage or a separate maintenance task. |
| frontend generated/dependency drift | harmless if unstaged | Existing local generated/dependency drift can pollute commits. | Deferred; keep unstaged. |

## Safe Fixes Applied

Applied safe, low-risk warning fixes:

- Added `backend/utils/time.py` with `utc_now_naive()`.
- Replaced deprecated model default callables that used `datetime.utcnow` with
  `utc_now_naive()`.
- Replaced backend test fixture calls to `datetime.utcnow()` with
  `utc_now_naive()`.
- Updated sync metadata's internal clock helper to use `utc_now_naive()`.
- Replaced the bullpen pitcher detail route's `Pitcher.query.get_or_404()`
  with `db.session.get(Pitcher, pitcher_id)` plus explicit `abort(404)`.

The timestamp fix intentionally preserves the existing naive UTC `DateTime`
contract. It does not convert stored values to timezone-aware output, does not
change migrations, does not change serialized API timestamp shapes, and does
not change freshness or sync logic.

## Deferred Warning Fixes

Deferred items:

- Local `.pytest-tmp-*` and `.pytest_cache` permission warnings remain local
  environment hygiene items. They are generated artifacts and must not be
  staged in this phase.
- Existing `frontend/dist/**`, `frontend/node_modules/**`, and
  `frontend/package-lock.json` drift remains unrelated generated/dependency
  drift and must not be staged.
- Prototype Prospect API `get_or_404()` call sites remain deferred because
  they did not appear in the current backend warning output. They should be
  handled only with focused prospect route validation or a separate prototype
  maintenance review.

No warning fix was deferred because it was required for certified V2 behavior.

## Risk Assessment

Risk removed:

- The backend warning count decreased from 139 to 0 in the full backend test
  suite.
- Deprecated UTC call usage no longer appears in backend Python source.
- The observed SQLAlchemy legacy query warning is removed.

Residual maintenance risk:

- Future dependency upgrades may surface additional SQLAlchemy warnings outside
  the current backend test coverage.
- Local cache/temp permission noise can still appear in `git status`.
- Prototype routes outside certified V2 may still contain legacy query helpers
  until covered by a focused maintenance pass.

Risk controls:

- Keep using targeted staging.
- Keep generated output, dependency folders, package-lock drift, and pytest
  temp/cache artifacts out of commits.
- Re-run full backend tests after future warning-remediation patches.
- Run frontend tests only when frontend files are touched.

## Regression Validation

Post-fix backend validation command:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-warning-review
```

Post-fix result:

```text
278 passed, 0 failed, 0 warnings
```

Frontend tests were not required in Phase 18 because no frontend files were
touched.

## Governance Validation

The required V2 guarantees remain:

```text
ranking_applied === false
selection_made === false
```

Phase 18 did not change:

- Recommendation Engine behavior
- fatigue formulas
- API contracts
- frontend features
- ranking behavior
- selection behavior
- prediction behavior
- best/preferred/recommended behavior

The full backend regression suite continued to pass after the warning fixes,
including V2 API, trust metadata, refusal/fail-closed, no-ranking,
no-selection, and V1 regression tests.

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V2.5 Phase 19 Prototype Surface Maintenance Review
```

Phase 19 should review non-certified prototype surfaces and remaining local
maintenance hygiene separately from the certified Recommendation Engine V2
production boundary. It should not expand Recommendation Engine behavior.
