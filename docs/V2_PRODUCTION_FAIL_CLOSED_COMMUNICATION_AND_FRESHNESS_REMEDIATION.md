# V2 Production Fail-Closed Communication and Freshness Metadata Remediation

Remediation date: June 3, 2026

Status:

```text
Complete
```

## 1. Remediation Purpose

This remediation makes the certified Recommendation Engine V2 production
fail-closed surface understandable when stale source freshness triggers a
degraded fail-closed state. It keeps fail-closed protection active while giving
the frontend enough metadata to explain sync status, source freshness,
aggregate V2 freshness, trust status, refusal reason, and safe partial-output
state.

## 2. Scope

In scope:

- V2 bullpen-state response metadata.
- V2 fail-closed reason communication.
- V2 freshness metadata exposed to the Dashboard.
- Dashboard V2 fail-closed/degraded-state copy and metadata rows.
- Backend and frontend tests for stale source freshness protection.
- Documentation status alignment.

Out of scope:

- Recommendation logic changes.
- Candidate grouping changes.
- Ranking behavior.
- Selection behavior.
- Prediction behavior.
- Fatigue formula changes.
- Fail-closed weakening.
- Pitcher-level advice.
- Matchup advice.

## 3. Relationship To Diagnosis

This remediation implements the bounded next milestone recommended by:

- `docs/V2_PRODUCTION_FAIL_CLOSED_DIAGNOSIS.md`

The diagnosis concluded:

```text
Fail-closed functioning correctly but UI communication insufficient
```

That conclusion remains valid. The backend fail-closed path was correct; the
needed work was to make the degraded freshness-protection state clear to users.

## 4. Root Cause Summary

Production V2 entered degraded fail-closed because aggregate source evidence
was stale:

```text
data_state_stale
```

Production sync status could still be current while a subset of per-pitcher
source evidence was stale. Before this remediation, the V2 response did not
clearly expose the available sync timestamp alongside the aggregate V2
freshness state, and the Dashboard used generic fail-closed language that could
make intentional protection look like a broken surface.

## 5. Backend Metadata Changes

`backend/api/recommendations.py` now exposes bounded communication metadata in
the V2 bullpen-state response.

Freshness metadata now distinguishes:

- `sync_timestamp`
- `overall_sync_status`
- `overall_sync_current`
- `overall_sync_label`
- `overall_sync_data_through`
- `source_freshness_status`
- `aggregate_v2_freshness_status`
- `freshness_failed`

Fail-closed metadata now distinguishes:

- `state`
- `critical_failure`
- `safe_partial_output_allowed`
- `partial_context_safe`
- `reason_codes`
- `primary_reason_code`
- `reason_summary`
- `display_label`
- `withheld_summary`
- `trust_failed`
- `freshness_failed`

The response also includes top-level `status_metadata` so the frontend can read
the production state without inferring it from scattered fields.

The backend reads existing sync-status metadata through the same sync metadata
builder used by `/api/bullpen/sync/status`. When a last successful sync is
known, the V2 freshness payload can expose it as `sync_timestamp`.

The backend does not change:

- source-data freshness criteria;
- refusal criteria;
- fail-closed criteria;
- candidate grouping;
- recommendation logic;
- fatigue formulas.

## 6. Frontend Communication Changes

`frontend/src/utils/api.js` now preserves V2 `status_metadata` during response
normalization.

`frontend/src/components/recommendations/RecommendationV2BullpenStatePanel.jsx`
now renders degraded freshness fail-closed output as a protection state instead
of a generic failure state.

When stale source freshness triggers degraded fail-closed, the Dashboard can
show:

- `Data freshness protection active`;
- fail-closed state;
- reason code such as `data_state_stale`;
- plain-English reason summary;
- what is withheld;
- source freshness status;
- aggregate V2 freshness status;
- sync timestamp;
- trust failure status;
- freshness failure status;
- partial-context safety status;
- visible `ranking_applied` and `selection_made` governance flags.

The frontend keeps V2 details visible only when the contract remains safe.
Critical failures still withhold bullpen-state output.

## 7. Testing Coverage

Backend coverage:

- `backend/tests/test_recommendation_v2_api_contract.py` verifies stale source
  evidence remains fail-closed.
- The same test verifies trust passing plus freshness failing is distinguishable.
- The same test verifies sync timestamp exposure when a successful sync is
  available.
- The same test verifies `ranking_applied` and `selection_made` remain false.
- Existing forbidden-field coverage continues to guard against ranking,
  selection, prediction, and decision-style fields.

Frontend coverage:

- `frontend/tests/recommendationV2Api.test.mjs` verifies `status_metadata`
  normalization.
- `frontend/tests/recommendationV2Rendering.test.mjs` verifies the Dashboard
  renders the freshness-protection label, reason code, explanation, sync
  timestamp, trust/freshness failure flags, partial-context safety, and
  governance flags.
- Existing rendering coverage continues to verify prohibited decision language
  is not displayed.

## 8. Governance Preservation

This remediation explicitly preserves:

```text
ranking_applied === false
selection_made === false
```

It does not introduce:

- ranking behavior;
- selection behavior;
- prediction behavior;
- best behavior;
- preferred behavior;
- recommended behavior;
- hidden priority ordering;
- pitcher-level advice;
- matchup advice.

Fail-closed behavior remains intact. Stale source freshness still produces a
degraded fail-closed state.

## 9. Remaining Risks

Remaining risks:

- Production may still enter degraded fail-closed when source evidence remains
  stale, which is expected protection behavior.
- Users may still need operational context if source freshness remains stale
  after normal sync.
- Older deployed frontend builds would not show the improved communication
  until redeployed.
- Local environments without current sync metadata can still differ from
  production.

## 10. Recommended Next Milestone

Recommended next milestone:

```text
V2 Production Fail-Closed Monitoring and Source-Freshness Distribution Review
```

That milestone should monitor how often production enters degraded fail-closed,
which reason codes fire, and how many source records are fresh, stale, missing,
or incomplete after normal sync.
