# Availability "All-Monitor" Diagnosis

Investigation date: 2026-06-05
Scope: Phase 1 audit remediation, Task 2. Diagnostic only.

## Question

`backend/reports/availability_threshold_audit.md` (generated 2026-06-02,
reference date 2026-06-01) shows **704 of 704 pitchers classified `Monitor`**
with `low` confidence. Is this a threshold defect, a data problem, or expected
fail-closed behavior?

## Finding

**This is correct fail-closed behavior on a stale dataset — not a threshold
defect.** No threshold change is warranted.

The evidence is inside the same audit report:

- Every one of the 704 "Monitor" rows has a **non-fresh data state**: 640
  `stale` + 64 `missing`. There are zero `fresh` rows in the current-availability
  section.
- The dominant reason is **"Latest workload data is outside the 14-day freshness
  window"** (640) and "Missing workload history or fatigue score" (64).
- The workload inputs are all zero for the current window:
  `pitches_yesterday`, `pitches_last_3_days`, `pitches_last_5_days` are
  min/median/max = 0 across all 704 pitchers.

That is exactly what `services/availability.py` is designed to do. When
`_data_state(...)` returns `stale` or `missing`, `classify_availability`
short-circuits to `Monitor` / `low` confidence and refuses to assert a
workload-driven status (`backend/services/availability.py:276-308`). It is
*supposed* to collapse to a single cautious status when it cannot trust the
data. This is the "no fake certainty / fail-closed" principle working.

## Proof the engine itself discriminates fine

The **same 704 pitchers**, evaluated in the report's *latest-workload snapshot*
mode (which anchors each pitcher to their own most recent game date instead of
"today"), produce a full, healthy spread:

| Status | Count |
| --- | ---: |
| Monitor | 268 |
| Limited | 174 |
| Avoid | 156 |
| Unavailable | 106 |

with 640 `fresh` / 64 `missing` data states. So the thresholds clearly separate
workload levels when the evaluation window actually contains games. The engine
is not broken.

## Root cause

The current-availability path always evaluates against `date.today()` and only
looks back a few days (`logs_for_availability_window` uses a 4-day window;
`_data_state` uses the 14-day `ACTIVE_WINDOW_DAYS`). The database used to
generate that audit had its most recent game logs **more than 14 days before the
run date**, so every pitcher's current window was empty and every row was
`stale`/`missing` → `Monitor`.

This is the *same root cause* as the freshness-reporting finding
(`data_freshness_validation_summary.md`): when data is not fresh relative to
"today," the current-availability surface correctly degrades. The production
backend, which had data through 2026-05-31 within the window, showed a healthy
fresh/stale split (428 fresh / 251 stale) in that same investigation — i.e. it
was *not* all-Monitor in production.

Contributing factor: the all-Monitor output is **indistinguishable to a casual
viewer from a real "everyone is borderline" signal**, because the stale reason
is only visible in per-row limitations. The fix is therefore about *visibility*,
not thresholds.

## Safest fix path (in priority order)

1. **Freshness visibility (done in Phase 1).** Make durable sync metadata
   authoritative so the dashboard clearly states "data through {date}" and
   whether it is current. When the data is stale, the all-Monitor result is then
   self-explanatory rather than alarming. (See Task 1.)
2. **Surface a staleness banner on availability lists.** When the active fatigue
   list is empty/all-stale, show a single explicit "Availability is paused —
   latest workload data is N days old" message instead of a wall of identical
   Monitor rows. (Low risk, UX-only; recommended for Phase 1.5/2.)
3. **Keep a fresh demo dataset.** For portfolio/demo environments, ensure the
   seeded/synced data is within the freshness window so the engine shows its
   real discrimination (the snapshot-mode spread above). This is an
   environment/ops action, not a code change.

## What must NOT be done

- **Do not loosen thresholds** to force non-Monitor statuses on stale data. That
  would manufacture fake certainty from data the engine has correctly flagged as
  untrustworthy — the exact opposite of the product principle.
- **Do not treat stale Monitor counts as workload-driven Monitor counts.** The
  audit report's own trust note already warns against this.

## Why no code fix shipped for the classifier in Phase 1

The classifier behaves correctly. The only justified, testable changes are in
freshness *reporting* (Task 1) and, optionally, an availability staleness banner
(deferred to a UX-scoped task). Changing classification logic here would be
unjustified and would regress the fail-closed guarantee.
