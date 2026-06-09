# V2 Production Fail-Closed Diagnosis

Investigation date: June 3, 2026

Conclusion:

```text
Fail-closed functioning correctly but UI communication insufficient
```

Remediation status:

```text
Implemented by docs/V2_PRODUCTION_FAIL_CLOSED_COMMUNICATION_AND_FRESHNESS_REMEDIATION.md
```

## 1. Investigation Purpose

This investigation determines why the certified Recommendation Engine V2
Bullpen Intelligence production surface displays `FAIL-CLOSED`, whether that
state is expected, and what remediation should be planned without changing
runtime behavior.

## 2. Scope

In scope:

- Recommendation V2 bullpen-state endpoint.
- Backend refusal handling and fail-closed handling.
- Trust, freshness, sync-status, source-evidence, and data-availability logic.
- Frontend V2 API normalization and Bullpen State rendering.
- Production endpoint evidence and local endpoint comparison.

Out of scope:

- Runtime fixes.
- API contract changes.
- Frontend behavior changes.
- Backend recommendation logic changes.
- Database schema changes.
- Governance changes.

## 3. Production Symptom Summary

The production Dashboard V2 Bullpen Intelligence surface displays
`FAIL-CLOSED`. A direct production request to:

```text
https://baseballos-api.onrender.com/api/recommendations/v2/bullpen-state?limit=750
```

returned HTTP 200 with a contract-safe payload. The relevant production
payload evidence was:

| Field | Production value |
| --- | --- |
| top-level `data_state` | `stale` |
| top-level `confidence` | `low` |
| `freshness.freshness_state` | `stale` |
| `freshness.data_through` | `2026-06-02` |
| `freshness.sync_timestamp` | `null` |
| `freshness.stale_warning` | `Some source evidence is stale.` |
| `fail_closed.state` | `degraded` |
| `fail_closed.failed_closed` | `true` |
| `fail_closed.critical_failure` | `false` |
| `fail_closed.safe_partial_output_allowed` | `true` |
| `fail_closed.reason_codes` | `["data_state_stale"]` |
| `fail_closed.source_evidence_state` | `represented` |
| `refusal_reasons[0].reason` | `data_state_stale` |
| `bullpen_state` | present |
| inventory summary count | 6 |
| candidate group count | 21 |
| `ranking_applied` | `false` |
| `selection_made` | `false` |

The same production response included a mixed source-freshness distribution:

| Source freshness group | Count |
| --- | ---: |
| fresh | 430 |
| stale | 249 |

## 4. Expected Fail-Closed Behavior

Recommendation Engine V2 is expected to fail closed or degrade when source
evidence cannot support full trust. The expected behavior is:

- malformed or unsupported trust metadata suppresses candidate output;
- unsafe query fields suppress candidate output;
- no source records suppress candidate output;
- stale, missing, incomplete, historical, or unknown data states create refusal
  metadata and a degraded fail-closed state;
- degraded fail-closed may still allow safe partial output when the failure is
  freshness-related rather than critical;
- every fail-closed response must preserve trust metadata, freshness metadata,
  refusal metadata, and governance metadata.

Repository evidence:

- `backend/recommendation/v2_assembly.py` adds data-state refusal reasons for
  `stale`, `missing`, `incomplete`, `historical`, and `unknown` source states.
- `backend/recommendation/v2_assembly.py` treats unsafe fields, absent records,
  and malformed or unsupported trust metadata as critical failures.
- `backend/recommendation/v2_assembly.py` classifies non-critical refusal states
  as `degraded` and allows safe partial output.
- `backend/api/recommendations.py` serializes `fail_closed`,
  `trust_metadata`, `freshness`, `refusal_reasons`, `ranking_applied`, and
  `selection_made` in the V2 public response.

## 5. Actual Fail-Closed Behavior

Production is not returning a critical failure. It is returning a degraded
fail-closed state:

```text
fail_closed.state: degraded
fail_closed.critical_failure: false
fail_closed.safe_partial_output_allowed: true
fail_closed.reason_codes: data_state_stale
```

The backend still returns a `bullpen_state` object, inventory summaries, team
context, candidate groups, limitations, and refusal metadata. That matches the
safe partial output path for a non-critical freshness refusal.

## 6. Backend Refusal-Path Review

The refusal path is firing because the assembled V2 context receives a stale
aggregate source-data state.

Repository evidence:

- `backend/api/recommendations.py` builds V2 candidates from
  `latest_fatigue_rows` and `classify_latest_fatigue_rows` before passing them
  to `assemble_v2_context`.
- `backend/services/availability.py` marks a pitcher stale when the latest
  game date is older than the active availability window.
- `backend/recommendation/v2_assembly.py` aggregates source data state using a
  worst-case order where `missing` and `stale` outrank `fresh`.
- `backend/recommendation/v2_assembly.py` adds a refusal reason named
  `data_state_stale` when aggregate source state is stale.

Production evidence:

```text
refusal_reasons[0].reason: data_state_stale
refusal_reasons[0].message: V2 context is degraded or refused because source data state is stale.
```

The refusal condition is firing intentionally from source freshness, not from a
ranking, selection, prediction, trust, or unsafe-query violation.

## 7. Backend Fail-Closed-Path Review

The backend fail-closed path is behaving according to the V2 assembly rules.

Repository evidence:

- `backend/recommendation/v2_assembly.py` sets `failed_closed` when refusal
  reasons exist.
- The fail-closed summary marks critical failure only for unsafe fields, absent
  records, or malformed/unsupported trust metadata.
- The fail-closed summary marks non-critical refusal states as `degraded`.
- The V2 API response suppresses `bullpen_state` only on critical failure.

Production evidence confirms:

```text
critical_failure: false
safe_partial_output_allowed: true
bullpen_state: present
```

This is a degraded fail-closed state, not a full critical output refusal.

## 8. Trust Metadata Review

Trust metadata is not failing in the observed production response.

Evidence:

- `fail_closed.source_evidence_state` is `represented`.
- No trust-validation error reason code is present.
- The response preserves top-level and trust-level governance flags.
- `ranking_applied` is `false`.
- `selection_made` is `false`.

The trust metadata path is therefore not the root cause of the production
`FAIL-CLOSED` display.

## 9. Freshness Metadata Review

Freshness metadata is the primary trigger and is also partially insufficient for
user-facing explanation.

Correct behavior:

- Production V2 freshness reports `freshness_state: stale`.
- Production V2 freshness reports `data_through: 2026-06-02`.
- Production V2 freshness includes the stale warning.
- Production V2 refusal metadata reports `data_state_stale`.

Insufficient behavior:

- Production V2 freshness reports `sync_timestamp: null`.
- The separate sync-status endpoint has a last successful sync timestamp.
- The V2 payload does not expose enough top-level context to show that the
  platform sync is current while part of the per-pitcher evidence set is stale.

This is not proof of stale global production sync. It is proof that the V2
freshness payload is aggregating per-pitcher source state and not carrying the
available sync-status timestamp.

## 10. Sync-Status Review

The production sync-status endpoint:

```text
https://baseballos-api.onrender.com/api/bullpen/sync/status
```

reported current global baseball data:

| Field | Production sync-status value |
| --- | --- |
| status | `success` |
| latest game date | `2026-06-02` |
| latest workload date | `2026-06-02` |
| latest fatigue calculated at | `2026-06-03T11:44:27.418579` |
| freshness current | `true` |
| freshness label | `Current baseball data through 2026-06-02.` |
| last successful sync | `2026-06-03T07:44:27.427608-04:00` |
| source | `legacy_status_file` |

This means production is not globally stale from the sync-status perspective.
The V2 fail-closed state is caused by the V2 source-evidence freshness
aggregate, where a subset of pitchers remains stale.

Repository evidence:

- `backend/api/bullpen.py` exposes sync status through the sync metadata
  service.
- `backend/api/recommendations.py` does not call that sync-status service while
  building the V2 bullpen-state response.
- Candidate metadata carries `last_successful_sync` only if it exists in
  availability metadata, but the availability classifier does not populate that
  field.

## 11. Frontend Rendering Review

The frontend is correctly interpreting the backend contract as fail-closed, but
the user-facing message is not specific enough for this degraded case.

Repository evidence:

- `frontend/src/utils/api.js` treats `fail_closed.state === "degraded"` as a
  fail-closed contract state.
- `frontend/src/utils/api.js` keeps fail-closed responses contract-safe when
  `ranking_applied === false` and `selection_made === false`.
- `frontend/src/components/recommendations/RecommendationV2BullpenStatePanel.jsx`
  renders the `Fail-Closed` badge and refusal metadata.
- The panel's fail-closed alert says V2 declined full bullpen-state output,
  even though the observed degraded response still includes `bullpen_state`.

The frontend rendering is not a contract bug. It is a communication gap: the
same visible `FAIL-CLOSED` label is used for degraded safe partial output and
could be interpreted as a full production failure.

## 12. Production vs Local Comparison

Local V2 endpoint evidence differs from production:

| Field | Production | Local |
| --- | --- | --- |
| top-level `data_state` | `stale` | `missing` |
| `freshness.freshness_state` | `stale` | `missing` |
| `freshness.data_through` | `2026-06-02` | `2026-05-01` |
| `freshness.sync_timestamp` | `null` | `null` |
| fail-closed state | `degraded` | `degraded` |
| reason code | `data_state_stale` | `data_state_missing` |
| critical failure | `false` | `false` |
| safe partial output | `true` | `true` |
| `bullpen_state` | present | present |
| `ranking_applied` | `false` | `false` |
| `selection_made` | `false` | `false` |

Local sync-status evidence:

- local data through `2026-05-01`;
- local last successful sync from legacy metadata;
- local durable `sync_runs` lookup could not be read because the relation was
  not present;
- local data is older and more incomplete than production.

Production and local both exercise the degraded fail-closed path, but for
different source-state reasons. Production is stale because a subset of
per-pitcher evidence is stale. Local is missing because the local data snapshot
has missing or incomplete source evidence.

## 13. Root Cause Analysis

Root cause:

```text
The production V2 fail-closed display is triggered by aggregate source-evidence
freshness. The V2 backend classifies the production bullpen-state context as
stale because 249 pitcher evidence records are stale, even though the global
production sync-status endpoint reports current baseball data through
2026-06-02.
```

Contributing factors:

- The V2 endpoint uses the latest fatigue rows available for the source set.
- The availability classifier marks individual pitcher evidence stale when the
  latest game evidence is outside the current availability window.
- V2 context assembly uses worst-case aggregate source-state semantics.
- Any stale aggregate V2 source state adds a refusal reason.
- Any refusal reason creates a fail-closed state.
- Non-critical freshness refusal creates a degraded fail-closed state with safe
  partial output.
- The V2 response does not propagate the separate sync-status last successful
  sync timestamp.
- The frontend fail-closed label does not distinguish degraded safe partial
  output from critical output suppression.

## 14. Correct or Incorrect Fail-Closed Determination

Determination:

```text
Fail-closed functioning correctly but UI communication insufficient
```

The fail-closed behavior is correct because production source evidence contains
stale per-pitcher records and the certified V2 path is designed to degrade when
source evidence is stale.

The user-facing communication is insufficient because the Dashboard displays a
general `FAIL-CLOSED` state without clearly explaining:

- the reason code is `data_state_stale`;
- the failure is non-critical;
- safe partial output is allowed;
- the platform sync-status endpoint is current;
- only part of the V2 source-evidence set is stale;
- `bullpen_state` is still intentionally present.

## 15. User-Facing Messaging Sufficiency

Current messaging is not sufficient for production interpretation.

The UI should keep fail-closed visibility, but it should distinguish:

- critical fail-closed with output suppression;
- degraded fail-closed with safe partial output;
- stale source evidence;
- missing source evidence;
- trust metadata failure;
- sync metadata unavailable;
- global sync current but partial source evidence stale.

Without that distinction, the surface can look broken when the backend is
actually preserving the certified degraded-output contract.

## 16. Recommended Remediation Options

Option 1: UX messaging remediation.

- Keep the `FAIL-CLOSED` badge.
- Add degraded-state copy when `critical_failure === false`.
- Display `reason_codes`, `freshness_state`, `data_through`, and
  `safe_partial_output_allowed`.
- Make refusal messages prominent enough to explain why output is degraded.
- Avoid any language implying ranking, selection, prediction, best option,
  preferred option, or final recommendation behavior.

Option 2: V2 freshness metadata remediation.

- Carry available sync-status metadata into the V2 freshness payload.
- Preserve the distinction between global sync state and per-pitcher evidence
  state.
- Consider exposing a compact source-freshness distribution in the V2 response
  so the UI can show mixed freshness rather than only the worst-case aggregate.

Option 3: Aggregate-state naming and documentation remediation.

- Document that V2 `data_state` is a worst-case source-evidence aggregate.
- Consider naming or copy that distinguishes aggregate evidence staleness from
  global sync staleness.

Option 4: Production monitoring remediation.

- Track degraded fail-closed frequency.
- Track reason-code distribution.
- Track stale, missing, incomplete, and fresh source-evidence counts.
- Track whether production degraded state persists after normal daily sync.

Option 5: Local environment remediation planning.

- Verify local durable sync metadata migration state.
- Refresh or reseed local data if local comparison is needed for current-mode
  production parity.

## 17. Recommended Remediation Priority

Priority 1:

- UX messaging remediation for degraded fail-closed output.

Priority 2:

- V2 freshness metadata remediation so sync timestamp and source-evidence
  freshness can be explained together.

Priority 3:

- Production monitoring for degraded fail-closed reason-code and source-state
  distribution.

Priority 4:

- Local environment sync metadata and current-data parity cleanup.

## 18. Risks

Risks if remediated incorrectly:

- Weakening fail-closed behavior could hide stale evidence.
- Treating global sync current as proof of all V2 evidence current could
  misrepresent per-pitcher source coverage.
- Hiding the `FAIL-CLOSED` badge could reduce trust transparency.
- Relaxing aggregate-state behavior without certification could change the
  certified V2 contract.
- Adding new UI language without governance review could imply ranking,
  selection, prediction, best option, preferred option, or final recommendation
  behavior.

## 19. Recommended Next Milestone

Recommended next milestone:

```text
V2 Production Fail-Closed Communication and Freshness Metadata Remediation Plan
```

The milestone should be planning-first and should authorize only bounded
remediation design until separately approved. It should define the exact
frontend copy, metadata fields, tests, and validation needed to explain degraded
safe partial output without changing Recommendation Engine behavior.

Remediation update: the bounded communication and freshness metadata
remediation is complete. The follow-up record is:

- `docs/V2_PRODUCTION_FAIL_CLOSED_COMMUNICATION_AND_FRESHNESS_REMEDIATION.md`

## Governance Confirmation

This investigation does not authorize governance changes.

The certified V2 governance boundary remains:

```text
ranking_applied === false
selection_made === false
```

The investigation preserves:

- no ranking behavior;
- no selection behavior;
- no prediction behavior;
- no best behavior;
- no preferred behavior;
- no recommended behavior.

No backend recommendation logic, API contract, frontend runtime behavior,
database schema, or governance behavior is changed by this diagnosis.
