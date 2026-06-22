# Story Adapter — Phase 1 Implementation Notes (June 2026)

**Companion plan:** `docs/design/story_consolidation_plan_june_2026.md` (Phase 1)
**Scope:** Purely additive backend canonical story adapter. No frontend behavior change, no removals, no engine changes.

---

## What was added

1. **`backend/services/story_feed.py`** — the canonical story adapter.
   - Wraps Story Intelligence V1 (`build_team_story`) as the structural base and maps each per-team payload to the canonical story contract.
   - `canonical_story_from_service_payload(...)` — pure mapper (one service payload → one canonical story).
   - `build_canonical_story_feed(teams, *, as_of_date, story_builder=…, freshness=…)` — assembles the ranked feed; available stories preserve input order, suppressed teams follow.
   - `story_id_for(team_id, date)` — stable `team_id:date` id.
   - References the four-beat feed only for team set/ordering (compatibility); all story content is Story Intelligence V1.

2. **`backend/api/bullpen.py`** — three additive edits inside `build_bullpen_dashboard_payload`:
   - Import `build_canonical_story_feed`.
   - New helper `_canonical_story_team_descriptors(payload, landscape)` — derives the ordered team set from the four-beat feed, falling back to landscape teams.
   - `payload['stories'] = build_canonical_story_feed(...)` added right after the four-beat block.

3. **Tests** — `backend/tests/test_story_feed.py` (14 unit tests) and one integration test in `backend/tests/test_bullpen_dashboard.py`.

The new dashboard field is exactly **`payload['stories']`**.

---

## What was intentionally NOT changed

- **No frontend edits.** Home, Stories, and Team Board continue to read their existing legacy fields. The frontend does not consume `stories` yet.
- **No legacy fields touched.** `four_beat_stories`, `story_context`, `continuity`, `what_changed_since_yesterday`, `story_continuity`, and the `/teams/<id>/story`, `/board`, `/changes` endpoints are unchanged. Verified by the integration test and by the existing story suites passing.
- **No engine changes.** Story Intelligence V1, the four-beat feed, observation engines, quality gates, and the voice library are untouched. No new metrics, ranking, availability, fatigue, or trust changes.
- **No snapshot version bump.** `DASHBOARD_PAYLOAD_VERSION` is unchanged. Adding a key is additive JSON: newly built snapshots and the live payload include `stories`; older cached snapshots remain valid and simply lack it until naturally rebuilt. This avoids invalidating unrelated snapshot behavior. (`test_dashboard_snapshot.py` passes unchanged.)
- **No public ranking exposure.** The feed conveys priority by item order only; no numeric rank/score field is exposed (governance: descriptive-only contract).

---

## Canonical contract shape

Per-item (each story in `payload['stories']['items']`):

| Field | Notes |
|---|---|
| `story_id` | Stable, deterministic: `"{team_id}:{date}"`. Excludes beat type (see Stable IDs). |
| `team_id`, `team_name`, `team_abbreviation` | Team identity (abbreviation is additive). |
| `date` | ISO `as_of_date`. |
| `story_available` | `true` published, `false` suppressed. |
| `suppression_reason` | `no_story_observations` / `no_valid_story_frame` / `story_unavailable` / `story_suppressed`; `null` when available. |
| `story_type` | Public beat (`coverage_pressure`, …); `null` when suppressed. |
| `category` / `tone` | `stressed/watch/rested` and `stress/watch/rest`, derived from the underlying observation read; `null` when suppressed. |
| `headline` | Verbatim from the writer; `null` when suppressed. |
| `narrative` | The four authored paragraphs joined by blank lines; `null` when suppressed. |
| `beats[]` | `{key,label,text}` for observation/baseline/cause/constraint. |
| `evidence[]` | The two evidentiary beats (baseline, cause). |
| `freshness`, `trust_metadata` | Passed through from the service. |
| `limitations[]` | Service limitations + the positive-beat flag when applicable. |
| `share_ready`, `share_title`, `share_summary` | Share-card readiness. |
| `source_engine` | `story_intelligence_service_v1`. |
| `quality_status` | `published` / `review` / `suppressed`. |

Feed envelope (`payload['stories']`): `capability`, `version`, `source_engine`, `as_of_date`, `generated_at`, `items[]`, `available_count`, `suppressed_count`, `suppression_reasons{}`, `fallback`, `freshness`, `limitations[]`.

### Stable IDs
`story_id = "{team_id}:{date}"` — beat type is intentionally excluded so share links and continuity survive an intraday beat change for the same team and date.

### Suppression
Suppressed teams return a neutral item — never an invented story: `story_available: false`, a `suppression_reason`, identity (`team_id`/`team_name`/`date`), `quality_status: "suppressed"`, and empty `headline`/`narrative`/`beats`/`evidence`.

---

## Known blocker — positive rest/depth beat parity

Story Intelligence V1 has **no true positive rest/depth public beat**. A positive read (`optionality_strength`) is mapped by the interpreter onto a pressure-framed beat (`sustainability_question`).

Phase 1 **does not** solve this, but it does not destroy the information either:
- The positive read is preserved in `tone: "rest"` / `category: "rested"`.
- The item is flagged with `quality_status: "review"` and `limitations` includes `positive_rest_depth_public_beat_not_yet_supported`.
- `source_engine` (`story_intelligence_service_v1`) discloses the authoring engine, and the feed-level `limitations` repeats the gap.
- The authored copy is left **verbatim** — no upbeat story is fabricated.

This must be resolved (a dedicated positive beat, or a positive writer path) before Home or Stories migrate, or rest stories will be reframed.

---

## Validation

Run with `PYTHONPATH=backend python -m pytest …` (test DB defaults to in-memory SQLite):

- `tests/test_story_feed.py` — **14 passed** (mapping, stable IDs, suppression, positive-beat flag, feed ordering/counts, resilience, dedupe).
- `tests/test_bullpen_dashboard.py` — **16 passed**, incl. the new `test_dashboard_includes_canonical_stories_and_keeps_legacy`. The 2 failures in that file (`…clean_trust_authority`, `…governed_authority`) are **pre-existing and unrelated** — they reproduce on the original code (date-sensitive availability classification).
- `tests/test_story_api_v1.py`, `test_story_intelligence_service_v1.py`, `test_four_beat_stories.py`, `test_story_quality.py` — **180 passed** (no regression).
- `tests/test_dashboard_snapshot.py` — **31 passed**; `tests/test_bullpen_intelligence_contracts.py` — **6 passed**.

---

## Next recommended phase

**Resolve the positive-beat blocker (plan Blocker B1), then Phase 2 (Home → canonical).** Add a positive `availability_depth` beat (or a positive writer path) so rest/depth stories publish natively; then move Home's "Three Things To Watch" to read the top of `payload['stories']` behind a feature flag, with the legacy client path as fallback. Broadening the canonical feed's team coverage beyond the four-beat set and introducing native cross-team ranking can follow.
