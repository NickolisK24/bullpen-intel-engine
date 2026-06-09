# BaseballOS V2.5 Phase 19 - Prototype Surface Maintenance Review

## Decision

BaseballOS V2.5 Phase 19 is a maintenance and governance review of current
production, supported, prototype, experimental, legacy, and deprecated
surfaces.

This phase does not add recommendation behavior, change Recommendation Engine
V2, change fatigue formulas, expand API contracts, add ranking logic, add
selection logic, or add prediction logic.

Decision:

```text
PROTOTYPE_SURFACE_REVIEW_COMPLETE
```

## Surface Inventory

| Surface | Location | Classification | Reason |
| --- | --- | --- | --- |
| Dashboard | `/` / `frontend/src/components/dashboard/Dashboard.jsx` | PRODUCTION | Primary current product entry point for bullpen status, sync freshness, availability, V2 bullpen state, fatigue distribution, and reference/prototype links. |
| Bullpen | `/bullpen` / `frontend/src/components/bullpen/Bullpen.jsx` | PRODUCTION | Primary interactive bullpen workload surface with team filters, availability filters, fatigue state, pitcher detail, and embedded V1 candidate evaluation. |
| V2 Bullpen State Panel | `frontend/src/components/recommendations/RecommendationV2BullpenStatePanel.jsx` | PRODUCTION | Certified V2 display surface for governed bullpen-state intelligence with trust, freshness, refusal, fail-closed, and expansion controls. |
| V2 bullpen-state API | `GET /api/recommendations/v2/bullpen-state` | PRODUCTION | Certified V2 API endpoint with governance validation, trust metadata, freshness metadata, refusal handling, and forbidden-field fail-closed behavior. |
| V1 candidate API and panel | `POST /api/recommendations/candidate`; selected pitcher detail | PRODUCTION | Certified V1 candidate-level evaluation only, user-triggered, one pitcher at a time. |
| Bullpen fatigue APIs | `/api/bullpen/fatigue`, `/api/bullpen/fatigue/<id>` | PRODUCTION | Existing workload-score read surfaces used by Dashboard, Bullpen, and Pitcher Detail. |
| Bullpen read APIs | `/api/bullpen/pitchers`, `/api/bullpen/pitchers/<id>/logs`, `/api/bullpen/teams`, `/api/bullpen/teams/<id>/bullpen`, `/api/bullpen/stats/overview`, `/api/bullpen/sync/status`, `/api/health` | PRODUCTION | Current read-only product APIs for roster, workload, team, overview, sync, and health state. |
| Methodology | `/methodology`; `GET /api/methodology/` | SUPPORTED | Public reference surface for fatigue model explanation, limits, and transparency. It is not a recommendation or decision surface. |
| Admin sync and recalculation | `POST /api/bullpen/sync`, `POST /api/bullpen/fatigue/recalculate` | SUPPORTED | Admin-token gated operational endpoints for data refresh and recomputation. |
| Frontend API normalizers | `frontend/src/utils/api.js` | SUPPORTED | Shared frontend API client, including V2 forbidden-field detection and governance normalization. |
| Availability governance reports and scripts | `backend/reports/availability_*.md`, `backend/scripts/audit_availability_*.py`, `backend/scripts/review_unavailable_boundary_cases.py` | SUPPORTED | Governance and audit tooling for availability threshold and explanation review. |
| Prospect Pipeline UI | `/prospects`; `frontend/src/components/prospects/` | PROTOTYPE | Explicitly labeled early prototype using illustrative sample data, not a live minor-league feed and not part of Recommendation Engine governance. |
| Prospect APIs | `/api/prospects/*`; `backend/api/prospects.py`; `backend/models/prospect.py` | PROTOTYPE | Sample/prototype prospect data API with grade ordering and comparison helpers. It does not carry V2 trust/freshness/refusal metadata. |
| Dashboard Pipeline Snapshot | Dashboard prototype card backed by `/api/prospects/stats/overview` | PROTOTYPE | Small Dashboard preview of the prototype Prospect Pipeline. |
| Fatigue vs next-outing ERA insight | `/api/bullpen/insights/fatigue-era`; `FatigueInsightCard`; `backend/analysis/fatigue_era_analysis.py` | EXPERIMENTAL | Exploratory retrospective analysis with visible limitations and no causal or predictive claim. |
| Latest-workload snapshot mode | `GET /api/bullpen/fatigue/snapshot`; `backend/services/availability_snapshot.py` | EXPERIMENTAL | Admin/development validation-only endpoint for latest workload snapshots. It is not used by public frontend helpers. |
| MLB passthrough helpers | `GET /api/bullpen/mlb/teams`, `GET /api/bullpen/mlb/pitcher/<id>/logs` | EXPERIMENTAL | Low-maintenance external source helpers, not part of governed V2 output or current public UI workflows. |
| Availability threshold experiment tooling | `backend/services/availability_unavailable_experiment.py`, `backend/scripts/experiment_unavailable_thresholds.py` | EXPERIMENTAL | Offline threshold experiment and report generation tooling, not runtime product behavior. |
| Backward-compatible fatigue array response | `/api/bullpen/fatigue` without `with_meta=true` | LEGACY | Preserved compatibility shape for older consumers while newer surfaces use metadata-aware responses. |
| Standalone fatigue recalculation script | `backend/recalculate_fatigue.py` | LEGACY | Manual maintenance script retained from earlier workflow; the supported operational path is the admin-token gated recalculation endpoint. |
| Deprecated production surfaces | None discovered | DEPRECATED | No current route or frontend surface is formally marked deprecated. |

## Production Surfaces

Production surfaces remain bounded to workload, availability, certified V1
candidate evaluation, certified V2 bullpen-state intelligence, sync/freshness
visibility, and Methodology reference visibility.

The certified V2 production surface remains:

- `GET /api/recommendations/v2/bullpen-state`
- Dashboard V2 Bullpen State panel
- trust metadata
- freshness metadata
- refusal metadata
- fail-closed visibility
- summary-first inventory and intelligence disclosure

No production V2 API expansion was added in this phase.

## Prototype Surfaces

The Prospect Pipeline remains the only user-visible prototype product surface.

Prototype facts:

- It is visibly labeled as a prototype in navigation, Dashboard, and the
  Pipeline page.
- It uses illustrative, hand-entered sample players.
- It does not consume Recommendation Engine V2 output.
- It does not return or render V2 trust metadata, freshness metadata, refusal
  metadata, or fail-closed metadata.
- It uses prospect grades and prototype grouping, which must not be promoted to
  production recommendation behavior without a separate contract and
  governance review.

Phase 19 applied a small presentation cleanup to reduce governance ambiguity:

- The Dashboard Pipeline card no longer uses `Top Rated` wording.
- The Dashboard Pipeline card no longer displays ordinal numbering for the
  sample grade highlights.

## Experimental Surfaces

Experimental surfaces are available for analysis, validation, or operational
inspection, but they are not certified Recommendation Engine surfaces.

### Fatigue vs Next-Outing ERA

The fatigue-to-ERA insight is exploratory and correlational. It remains
acceptable because the UI and analysis output state that it is not causal, not
controlled, not role-adjusted, and not a prediction.

Risk:

- If reused as a recommendation input without a new governance review, it could
  be mistaken for a predictive model.

Required boundary:

- Keep it framed as exploratory reference evidence only.
- Do not use it as ranking, selection, or prediction input without a new
  certification path.

### Snapshot Mode

The latest-workload snapshot endpoint is admin/development validation only.
Existing tests cover admin-token requirements and production rejection when the
admin token is missing.

Risk:

- If exposed to public UI without its validation-only framing, it could bypass
  current-mode freshness expectations.

Required boundary:

- Keep no public frontend helper for `/api/bullpen/fatigue/snapshot`.
- Preserve `is_current_availability=false` semantics.

### MLB Passthrough Helpers

The MLB passthrough endpoints are low-maintenance source helpers and do not
carry the BaseballOS trust, freshness, or refusal envelope.

Risk:

- If wired directly into public intelligence surfaces, they could bypass
  BaseballOS freshness and trust metadata.

Required boundary:

- Any promotion into production UI requires a governing contract, freshness
  metadata, and failure-state handling.

## Legacy Surfaces

Legacy surfaces are retained for compatibility or earlier maintenance workflows.

Phase 19 found one active legacy presentation issue in the Bullpen team view:
the tab and table header used ranking language even though the surface is a
workload summary, not Recommendation Engine output.

Safe cleanup applied:

- `Team Rankings` became `Team Summary`.
- `30-Team Bullpen Rankings` became `30-Team Bullpen Summary`.
- The team view now defaults to alphabetical order.
- The ordinal row column was removed.

The same fatigue metrics remain inspectable through the table.

The standalone recalculation script remains a legacy maintenance utility. The
supported operational endpoint is still admin-token gated.

## Deprecated Surfaces

No current production, supported, prototype, experimental, or legacy surface is
formally deprecated by this review.

Recommended future action:

- Create a deprecation policy before removing or hiding any route, UI, helper,
  or script.

## Governance Review

Required V2 governance state remains:

```text
ranking_applied === false
selection_made === false
```

Governance findings:

- Certified V2 output remains constrained to descriptive bullpen-state
  intelligence.
- V2 still exposes no final pitcher choice.
- V2 still exposes no pitcher winner.
- V2 still exposes no automated decision.
- V2 still fails closed when forbidden ranking, selection, prediction, or
  score-like source fields appear in governed output.
- V2 frontend rendering still hides unsafe display language and shows an
  unavailable governed state instead of rendering unsafe output.
- Prototype Prospect surfaces do not bypass V2 governance because they do not
  call V2, do not feed V2, and remain labeled as prototype.
- Experimental snapshot, passthrough, and analysis surfaces are not V2 outputs
  and must not be promoted into production intelligence without a separate
  governance contract.

## Risk Assessment

| Risk | Classification | Assessment | Action |
| --- | --- | --- | --- |
| Prospect Pipeline promoted without governance metadata | Moderate | Prototype APIs lack V2 trust, freshness, refusal, and fail-closed metadata. | Defer promotion until a prototype-promotion contract exists. |
| Experimental fatigue-to-ERA insight interpreted as prediction | Low | Current UI states exploratory, correlational, and not causal. | Keep limitations visible; do not use as recommendation input. |
| Snapshot endpoint used as public freshness source | Low | Endpoint is admin/development validation only and has test coverage. | Preserve admin guard and no public helper. |
| MLB passthrough helpers bypassing trust/freshness envelope | Low | No current frontend usage found. | Keep out of production UI unless wrapped by a governed contract. |
| Legacy team comparison rank-style wording | Remediated | Rank-style copy and ordinal presentation were present. | Phase 19 replaced with neutral summary language and alphabetical default. |
| Standalone recalculation script drift | Low | Script is outside current public product path. | Consider consolidating or retiring after a deprecation policy exists. |

## Cleanup Recommendations

Recommended cleanup path:

- Create a formal prototype-promotion and deprecation policy before any
  Prospect Pipeline production work.
- If the Prospect Pipeline moves beyond prototype, replace grade-ordered
  prototype summaries with a governed contract that includes data provenance,
  freshness, limitations, refusal, and fail-closed behavior.
- Replace remaining prototype `get_or_404()` route lookups with session-based
  lookups when the Prospect API receives maintenance attention.
- Keep `/api/bullpen/fatigue/snapshot` admin/development validation only.
- Keep MLB passthrough helpers out of production UI until they carry a
  BaseballOS trust/freshness envelope.
- Decide whether `backend/recalculate_fatigue.py` should remain supported or
  be deprecated after an explicit deprecation policy exists.

## Future Maintenance Recommendations

Future route and surface reviews should include:

- backend route inventory
- frontend route inventory
- API helper inventory
- prototype/experimental classification check
- trust/freshness/refusal/fail-closed envelope check
- rank-like wording and ordinal-layout scan
- admin/debug endpoint guard verification
- deprecation status review

The review should run before any prototype route is promoted, before any
experimental analysis is made user-facing as decision support, and before any
legacy utility is removed.

## Regression Validation

Validation completed for this phase:

```text
npm test
77 passed, 0 failed

.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-prototype-review
278 passed, 0 failed
```

Diff hygiene checks are required before commit:

```text
git diff --check
git diff --cached --check
```

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V2.5 Phase 20 Prototype Promotion and Deprecation Policy
```

Phase 20 should define the formal rules for promoting prototype surfaces,
retiring legacy surfaces, deprecating low-maintenance routes, and requiring
trust/freshness/refusal/fail-closed metadata before any prototype becomes part
of the production governance path.
