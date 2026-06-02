# Bullpen Availability Engine V1

## Phase 3 Purpose

The Bullpen Availability Engine is the next product layer for BaseballOS. The
current Bullpen Intelligence Engine explains workload through fatigue score,
rest, recent usage, and freshness-aware visibility. Availability V1 translates
that workload context into deterministic decision-support statuses that are
clear enough to use and transparent enough to audit.

The engine should help answer:

- Who is available?
- Who is at elevated workload risk?
- Why did the system assign that status?
- What changed since the last snapshot or appearance?
- What happens if this pitcher is used tonight?
- Can this number be trusted?

This is not a private clubhouse availability feed and not a medical model. V1
is a public-data workload framework built from BaseballOS data: MLB Stats API
game logs, existing fatigue scores, rest context, and data freshness state.

## Current State: June 2026

Availability Engine V1 is implemented as a completed trust foundation:

- Backend classification service is live and reusable outside route handlers.
- Fatigue, team bullpen, pitcher detail, and dashboard overview APIs expose
  additive availability output.
- Bullpen rows, filters, pitcher detail views, and dashboard summary surfaces
  present availability without reclassifying in the frontend.
- Explanations, confidence, data state, limitations, and deterministic inputs
  are part of the contract.
- Fixture coverage verifies all five statuses even when live local data does
  not naturally contain every status.
- Threshold audit, snapshot validation, boundary review, and tuning governance
  are documented and tested.
- The first governed threshold adoption raised the Unavailable three-day pitch
  threshold from 80 to 90 after audit and boundary review.

The next product milestone is not another threshold change. It is
Recommendation Engine V1 Policy: defining how BaseballOS should move from
availability intelligence to decision-support intelligence without implying
private team, medical, travel, or manager-intent knowledge.

## Availability Statuses

Availability labels are workload guidance, not commands. They should be shown
with reasons, confidence, and limitations every time.

### Available

**Meaning:** Workload signals are inside normal use ranges, recent data is
fresh, and no deterministic rule has raised a meaningful restriction.

**User interpretation:** This pitcher appears workload-available from public
game-log data. Normal baseball context still applies.

**Example reasoning:**

- Fatigue score is low or moderate.
- No appearance yesterday.
- No back-to-back usage.
- Pitch volume over the last three and five days is light.

**Trust and limitations:** Available does not mean guaranteed to pitch. It does
not account for injuries, illness, travel, bullpen roles, warm-up activity, or
manager preference.

### Monitor

**Meaning:** One or more workload signals deserve attention, but the pitcher is
not clearly constrained by recent usage.

**User interpretation:** This pitcher may be usable, but the user should review
the reasons before treating them as fully available.

**Example reasoning:**

- Moderate fatigue score.
- Pitched yesterday on a low pitch count.
- Two appearances in the last five days.
- One rest day after moderate use.

**Trust and limitations:** Monitor is an early warning label. It should avoid
overstating concern when the only signal is mild recent use.

### Limited

**Meaning:** Recent workload suggests the pitcher may be available only in a
restricted way, such as lower pitch exposure, lower leverage, or emergency use.

**User interpretation:** This pitcher should not be treated as a normal full-use
option without reviewing workload context.

**Example reasoning:**

- 25 to 34 pitches yesterday.
- Three appearances in four days.
- Elevated fatigue score with only one day of rest.
- Heavy five-day pitch load but no single extreme outing.

**Trust and limitations:** Limited should explain the workload path that created
the label. It should not imply the team has announced a restriction.

### Avoid

**Meaning:** Workload signals are high enough that using the pitcher would carry
a clear public-data workload concern.

**User interpretation:** Prefer other options if possible. If used, the decision
should be understood as accepting meaningful recent-workload risk.

**Example reasoning:**

- 35 or more pitches yesterday.
- Back-to-back appearances with meaningful pitch volume.
- Three appearances in four days plus elevated fatigue score.
- High five-day pitch load and no rest buffer.

**Trust and limitations:** Avoid is not "injured" or "unavailable." It is a
strong workload caution derived from public game-log history.

### Unavailable

**Meaning:** Deterministic workload rules indicate this pitcher should be treated
as unavailable for normal planning from public workload data.

**User interpretation:** Do not count this pitcher as a usable bullpen option
unless there is overriding real-world information outside BaseballOS.

**Example reasoning:**

- Very high pitch count yesterday.
- Extreme multi-day workload.
- Back-to-back heavy usage plus critical fatigue score.
- Three-in-four or four-in-five usage with high pitch volume.

**Trust and limitations:** Unavailable must only mean workload-unavailable based
on BaseballOS inputs. It must not imply injury, illness, roster inactivation, or
a team-reported decision.

## Initial Deterministic Rule Inputs

V1 should use only data BaseballOS currently stores or can reasonably derive
from MLB Stats API game logs.

### Existing Stored Inputs

- Current fatigue score.
- Current fatigue risk tier.
- Days since last appearance.
- Appearances in the last 7 and 14 days.
- Pitches in the last 7 days.
- Innings in the last 7 days.
- Pitcher active flag and team metadata.
- Latest game-log date.
- Fatigue-score calculation timestamp.
- Freshness metadata for current versus stale snapshots.

### Derived Game-Log Inputs

- Pitches yesterday.
- Pitches over the last 3 days.
- Pitches over the last 5 days.
- Appearances over the last 3 days.
- Appearances over the last 5 days.
- Days of rest.
- Back-to-back appearances.
- Three-in-four usage.
- Four-in-five usage.
- Last appearance date.
- Last appearance pitch count.
- Latest available team game date when needed to distinguish rest from missing
  same-day sync.

### Data Quality Inputs

- Freshness state: fresh, stale, historical snapshot, or unknown.
- Missing data state: no game logs, no fatigue score, incomplete game logs, or
  failed API load.
- Confidence state: high, medium, low, or unknown.
- Coverage notes: limited MLB data, recent call-up, role ambiguity, or team data
  not refreshed today.

### Candidate Rule Direction

Exact thresholds should be validated during implementation, but the first V1
classifier should be deterministic and precedence-based:

1. Data gates run first. Missing or stale data cannot produce a confident
   current availability label.
2. Extreme workload rules can promote a pitcher directly to Unavailable.
3. Heavy recent workload rules can promote a pitcher to Avoid.
4. Moderate workload combinations can promote a pitcher to Limited.
5. Mild workload signals can promote a pitcher to Monitor.
6. If no rule fires and data is fresh enough, the status is Available.

Example candidate rule families:

- Yesterday workload: no appearance, light use, moderate use, heavy use,
  extreme use.
- Multi-day workload: pitches over 3 days and 5 days.
- Appearance compression: back-to-back, three-in-four, four-in-five.
- Rest recovery: zero days, one day, two days, three or more days.
- Fatigue override: high or critical fatigue can increase restriction.
- Freshness gate: stale data suppresses current labels or lowers confidence.
- Missing data gate: missing inputs create unknown or low-confidence display,
  not a fake workload status.

### Implemented V1 Classification Framework

The initial backend implementation lives in `backend/services/availability.py`.
It is a pure classification layer used by API routes, not route-embedded logic.
The helper returns:

- `availability_status`
- `confidence`
- `data_state`
- `reasons`
- `limitations`
- `inputs`

The first API integration is additive: fatigue list, team bullpen, and pitcher
detail responses preserve existing fatigue fields and add an `availability`
object for each classified pitcher.

V1 uses `Monitor` with low confidence for stale, missing, or incomplete data
because the public status set is limited to Available, Monitor, Limited, Avoid,
and Unavailable. Consumers must use `data_state`, `confidence`, `reasons`, and
`limitations` to distinguish "workload concern" from "current availability is
uncertain."

Current threshold references:

| Rule input | Monitor | Limited | Avoid | Unavailable |
|------------|---------|---------|-------|-------------|
| Fatigue score | >= 40 | >= 60 | >= 75 | >= 85 with heavy yesterday workload |
| Pitches yesterday | >= 15 | >= 25 | >= 35 | >= 50 |
| Pitches over last 3 days | >= 30 | >= 45 | >= 60 | >= 90 |
| Pitches over last 5 days | n/a | >= 60 | >= 75 | >= 75 with 4+ appearances |
| Appearances over last 3 days | n/a | >= 2 | >= 3 | n/a |
| Appearances over last 5 days | >= 2 | >= 3 | >= 4 | >= 4 with 75+ pitches |
| Back-to-back appearances | Monitor or higher by context | Any back-to-back appearance sequence | Back-to-back plus 35+ pitches in 3 days | n/a |
| Freshness | n/a | n/a | n/a | Stale data returns Monitor with low confidence, not a current workload label |

The Unavailable three-day pitch threshold was adopted from Candidate C after
audit and boundary review. The governed adoption moved that value from 80 to 90,
allowing 80-89 pitches in 3 days to classify as Avoid unless another
Unavailable rule fires, while 90+ pitches in 3 days remains Unavailable.

These thresholds are centralized in `AvailabilityThresholds` so future tuning
can happen in one place with focused regression coverage.

### Implemented V1 UI Presentation

The first frontend implementation presents backend availability output without
reclassifying pitchers in the browser. Bullpen rows show a visible availability
badge beside the existing fatigue and risk signals, and the Bullpen page adds an
availability filter for Available, Monitor, Limited, Avoid, and Unavailable.

Pitcher detail views include an availability summary with:

- Availability status.
- Confidence.
- Data status.
- Ordered reasons.
- Limitations.

The UI treats `data_state` as part of the trust contract. Stale, missing,
incomplete, failed, or historical states must be displayed when returned by the
backend instead of being silently hidden behind a status badge. Freshness-aware
empty states remain distinct from availability, risk, team, and search filter
empty states so users can tell whether BaseballOS has no workload data, stale
data excluded by default, or current filters excluding visible pitchers.

Frontend code should continue to consume `availability_status`, `confidence`,
`data_state`, `reasons`, `limitations`, and `inputs` from the API. Thresholds
and classification rules remain owned by the backend availability service.

Frontend fixture coverage exists for all five statuses because live local
datasets may not naturally contain Available, Monitor, Limited, Avoid, and
Unavailable at the same time. These fixtures validate UI rendering, filtering,
confidence display, data-state visibility, reasons, and limitations only. They
are not threshold validation and must not be treated as production pitcher data.

### Threshold Audit

Availability thresholds should be tuned from evidence, not from one-off visual
inspection. The repeatable audit script is:

```powershell
cd backend
python scripts/audit_availability_thresholds.py
```

By default it writes `backend/reports/availability_threshold_audit.md`. The
report summarizes current classifier output, confidence and data-state
distributions, reason frequencies, workload inputs, and near-threshold
examples. It also separates current freshness-aware classifications from a
latest-workload snapshot so stale-data Monitor counts are not confused with
workload-driven Monitor counts.

The audit is allowed to inform future threshold review and test-case design. It
must not change backend thresholds, fatigue scoring, API response shape, or
frontend rendering. Any threshold changes should happen in a later branch after
the audit evidence is reviewed.

Threshold tuning governance is documented in
`docs/AVAILABILITY_THRESHOLD_TUNING_PLAN.md`. The current comparison baseline
is `backend/reports/availability_threshold_baseline.md`. Future tuning branches
should compare against that baseline, change one threshold variable at a time,
and include before/after audit evidence before review.

The first governed threshold adoption is documented in
`backend/reports/availability_threshold_adoption_candidate_c.md`. The supporting
experiment is `backend/reports/availability_unavailable_threshold_experiment.md`
and the boundary review is
`backend/reports/availability_unavailable_boundary_review.md`.

### Latest Workload Snapshot Validation Mode

Local historical datasets can make all public current-availability rows appear
stale even when useful workload examples exist. BaseballOS therefore includes a
development/admin validation mode that anchors each pitcher to their latest
known game-log date and reuses the same Availability Engine classifier.

This mode is exposed through the protected backend endpoint:

```powershell
GET /api/bullpen/fatigue/snapshot
```

The route is gated by the same `X-Admin-Token` / `ADMIN_API_TOKEN` guard used by
operational admin endpoints. Production access requires a configured
`ADMIN_API_TOKEN` and a matching `X-Admin-Token` request header. Local
development may allow the endpoint without a token when `ADMIN_API_TOKEN` is
unset, matching the existing admin-endpoint development convention. It is not a
public Bullpen UI mode and must not be presented as live availability.

Responses include explicit non-current metadata:

```json
{
  "mode": "latest_workload_snapshot",
  "snapshot_date": "2026-05-01",
  "reference_strategy": "per_pitcher_latest_game_date",
  "is_current_availability": false,
  "warning": "Historical workload snapshot for validation only. Do not treat as current bullpen availability."
}
```

Authorized responses also include defensive headers:

```text
X-BaseballOS-Data-Mode: latest_workload_snapshot
X-BaseballOS-Current-Availability: false
```

`snapshot_date` is the latest game-log date represented by the response. Each
pitcher row also carries its own evaluation date because the validation strategy
is per-pitcher latest workload, not a claim that every pitcher has current data
on the same date.

The threshold audit script uses this same shared snapshot path for its
latest-workload section. Snapshot output is allowed to support visual
validation, regression fixtures, and later threshold review. It is not allowed
to tune thresholds by itself, replace current-calendar freshness filtering, or
hide stale/missing data states.

Public frontend code must not consume this endpoint for current availability.
Use current-mode endpoints for public UI and reserve snapshot responses for
admin/development validation workflows.

### System-Level Availability Summary

The dashboard overview response includes a current-mode
`availability_summary` object that aggregates existing Availability Engine
outputs across scored pitchers. It counts status, confidence, and data-state
distributions and includes trust notes when stale, missing, or incomplete data
limits current availability confidence.

This summary is current availability only. It does not use latest-workload
snapshot mode and must not turn historical validation output into public
current availability. Dashboard presentation should make stale/missing-data
dominance visible so users can distinguish a workload-heavy bullpen from a
system that lacks fresh workload context.

## Explainability Contract

Every status must be explainable by a small set of ordered reasons. Reasons are
not decorative text; they are part of the product contract.

The eventual API shape can change, but V1 should preserve these concepts:

```json
{
  "pitcher_id": 123,
  "status": "Limited",
  "data_state": "fresh",
  "confidence": "medium",
  "reasons": [
    "29 pitches yesterday",
    "3 appearances in 4 days",
    "Only 1 day of rest"
  ],
  "limitations": [
    "No injury data available",
    "No team-reported availability data available"
  ],
  "inputs": {
    "fatigue_score": 62.4,
    "pitches_yesterday": 29,
    "pitches_last_3_days": 48,
    "pitches_last_5_days": 63,
    "appearances_last_3_days": 2,
    "appearances_last_5_days": 3,
    "days_rest": 1,
    "back_to_back": false,
    "three_in_four": true,
    "freshness_state": "fresh"
  }
}
```

Recommended fields:

- `status`: one of Available, Monitor, Limited, Avoid, or Unavailable when data
  is sufficient and current.
- `data_state`: fresh, stale, missing, incomplete, failed, or historical.
- `confidence`: high, medium, low, or unknown.
- `reasons`: ordered human-readable facts that caused the status.
- `limitations`: missing context the user must understand.
- `inputs`: the key deterministic values used to classify the pitcher.
- `changed_since`: optional future summary of what changed since the prior
  snapshot.
- `if_used_tonight`: optional future scenario showing how a hypothetical
  appearance would affect tomorrow's status.

## Explanation Quality Standards

Availability explanations must read as factual workload observations, not raw
debug output or unsupported recommendations. The wording rules live in
`backend/services/availability_explanations.py` so classifier output, tests, and
audit reports share the same vocabulary.

Reasons and limitations have different jobs:

- Reasons describe deterministic workload or data-state facts that contributed
  to the status.
- Limitations describe context BaseballOS does not know, such as injury status,
  team-reported availability, or whether stale data can be trusted as current.

Reason wording should stay short, specific, and ordered by signal family:

1. Pitch volume, such as `42 pitches yesterday`, `54 pitches in 3 days`, or
   `75 pitches in 5 days`.
2. Appearance frequency, such as `2 appearances in 3 days`,
   `3 appearances in 4 days`, `4 appearances in 5 days`, or
   `Back-to-back appearances`.
3. Rest context, such as `No rest since last appearance` or
   `Only 1 day of rest`.
4. Fatigue context, such as `Fatigue score is 55.3`.
5. Data-state context, such as
   `Latest workload data is outside the 14-day freshness window`,
   `Missing workload history or fatigue score`, or `Incomplete workload inputs`.

Rules for explanation text:

- Do not use black-box phrases when a concrete input is available.
- Do not duplicate the same exact reason in one pitcher response.
- Do not mix limitations into reasons.
- Do not present stale or missing data as a workload-driven current status.
- Do not imply injury, medical status, manager intent, or private clubhouse
  availability.
- Keep text stable enough that downstream UI tests can assert it directly.

The repeatable explanation audit script is:

```powershell
cd backend
python scripts/audit_availability_explanations.py
```

By default it writes `backend/reports/availability_explanation_audit.md`. The
report lists the possible reason catalog, observed reason frequencies, observed
limitation frequencies, and grouped reason categories for both current
availability output and latest-workload snapshot output. It is allowed to guide
wording cleanup and test coverage. It must not change thresholds, status
outcomes, fatigue scoring, or API structure.

## Trust Rules

These rules are non-negotiable for V1:

- No black-box availability labels.
- Every status must expose reasons.
- Every reason must map to a concrete input or rule.
- Missing data must reduce confidence, alter display, or block a current label.
- Stale data must not be presented as current availability.
- The system must distinguish workload-unavailable from unknown due to missing,
  incomplete, stale, or failed data.
- Recommendation wording must avoid pretending BaseballOS has private
  clubhouse, injury, medical, travel, or manager-intent knowledge.
- "Unavailable" must be explicitly framed as workload-unavailable.
- "Available" must not imply a guaranteed real-world appearance.
- If a status changes, the UI should be able to show what input changed.
- If same-day sync has not run, the system must say so rather than infer today's
  team availability from yesterday's snapshot.

## Edge Cases

### No Recent Appearances

A pitcher with no recent appearances and fresh roster/log coverage may be
Available from workload data. If the pitcher has no MLB logs at all, the status
should be low-confidence or unknown rather than automatically Available.

### Opener and Bulk Reliever Ambiguity

Game logs alone may not identify role cleanly. A pitcher used as an opener or
bulk reliever can have starter-like workload. V1 should classify the workload it
sees and include a limitation that role context is not yet modeled.

### Position Players Pitching

Position-player pitching appearances can distort bullpen workload views. V1
should either exclude non-pitchers from bullpen availability or mark them as
out-of-scope when position metadata indicates they are not pitchers.

### Minor League Call-Ups With Limited MLB Data

Recent call-ups may have little or no MLB game-log history. V1 should surface
limited coverage and avoid presenting high-confidence availability from an empty
MLB sample.

### Pitchers With Stale Data

Stale pitchers should remain inspectable when inactive/stale data is included,
but stale data must not be shown as current availability. The display should say
that the status is based on an old snapshot or withhold current status.

### Doubleheaders

Doubleheaders can create multiple team games in one day and unusual rest
pressure. V1 should compute pitcher workload from actual appearances and avoid
assuming one game per calendar day when deriving same-day or yesterday context.

### Suspended or Postponed Games

Suspended and postponed games can shift official game dates or create partial
records. V1 should rely on completed pitching lines where possible and mark
incomplete or ambiguous logs as a confidence limitation.

### Same-Day Sync Not Yet Run

If today's games may have occurred but the latest sync predates them, the system
must show that the snapshot may not include today's workload. It should not
silently treat the stale snapshot as current.

### Incomplete Game Logs

If pitches, innings, or game dates are missing for relevant appearances, the
status should become low-confidence or unknown. Missing workload values must not
be treated as zero unless the source field explicitly means zero.

## V1 Non-Goals

V1 deliberately defers:

- Injury or news scraping.
- Private team availability data.
- Team-reported medical, rest, or usage plans.
- Stuff+, pitch quality, or command modeling.
- Statcast or Hawk-Eye biomechanics.
- Paid licensing integrations.
- A fully automated manager recommendation engine.
- A predictive rest-of-series simulator.
- Role-aware starter versus reliever modeling beyond simple limitations.
- Warm-up tracking or bullpen phone activity.
- Travel, weather, and personal availability context.

## V1 Foundation Sequence And Future Compatibility

The V1 foundation was built in small reviewable branches. Completed foundation
work:

1. **Backend status classification helper**
   - Add a pure deterministic helper that accepts fatigue score, game-log
     windows, freshness state, and data-quality flags.
   - Return status, confidence, reasons, limitations, and inputs.
   - Cover rule precedence with focused unit tests.

2. **Backend API response extension**
   - Extend fatigue list and pitcher detail responses with availability data.
   - Preserve existing fatigue fields and endpoint compatibility.
   - Include freshness and data-quality states in responses.

3. **Frontend availability badges**
   - Add status badges to bullpen tables and pitcher detail.
   - Keep fatigue score visible beside availability status.
   - Make stale or unknown status visually distinct from workload-unavailable.

4. **Explanation panel**
   - Show ordered reasons, limitations, and key inputs.
   - Add a "what changed" area once prior snapshots are available.

5. **Tests and regression coverage**
   - Add backend rule fixtures for each status.
   - Add stale, missing, call-up, and doubleheader edge-case coverage.
   - Add frontend tests for labels, reasons, and stale/unknown display.

6. **Documentation updates**
   - Update setup/product docs with the status definitions and trust framing.
   - Link to methodology once the engine is implemented.

Future compatibility work remains:

7. **Future simulator compatibility**
   - Keep the classifier input shape compatible with hypothetical usage
     scenarios, such as "if used for 20 pitches tonight."
   - Do not build the simulator in V1.

## Current V1 Foundation Completion Criteria

The V1 trust foundation is complete when:

- The five workload statuses are defined.
- Initial deterministic inputs are listed.
- The backend classifier returns status, confidence, data state, reasons,
  limitations, and inputs.
- API availability output is additive and backward-compatible.
- Bullpen and pitcher detail UI display status, confidence, data state,
  reasons, and limitations.
- Dashboard availability summary makes stale/missing-data dominance visible.
- Explanation quality standards are documented and audited.
- Trust rules are documented.
- Edge cases are documented.
- V1 non-goals are explicit.
- Threshold governance and baseline artifacts exist.
- The first governed threshold adoption is documented.
- Durable sync metadata and dashboard trust-strip documentation distinguish
  `Synced` from `Data Through`.
