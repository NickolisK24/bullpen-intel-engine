# Positive Depth / Rest Story Beat — Phase 1.5 (June 2026)

**Companion docs:** `story_coverage_audit_june_2026.md`, `story_consolidation_plan_june_2026.md`, `story_adapter_phase_1_notes.md`
**Scope:** Backend-only. No frontend changes. No engine removed. No UI migrated (Home, Stories, Team Board untouched).

---

## What changed

A new positive public beat, **`availability_depth`** ("Availability Depth"), was added to the Story Intelligence V1 pipeline so a genuinely good-news bullpen can publish a positive depth/rest story instead of being reframed into a worry beat or suppressed.

| File | Change |
|---|---|
| `services/story_voice_library_v1.py` | Added `BEAT_AVAILABILITY_DEPTH` + ten measured, non-predictive opening templates (avoid every denied/banned phrase). |
| `services/story_four_beat_interpreter_v1.py` | Added the beat to `PUBLIC_BEATS` (positive question). Remapped `optionality_strength → availability_depth` and `stable_core → availability_depth` (was `sustainability_question` / `route_change`). Removed the optionality→`depth_constraint`/`sustainability_question` reroute. Added a positive forward clause. Updated `observation_public_beat_map`. |
| `services/story_writer_v1.py` | Pointed the `_optionality_strength` and `_stable_core` headline voice at `availability_depth` (their bodies were already positive). |
| `services/story_intelligence_service_v1.py` | Added `_selection_strength_for_availability_depth` + reasons; a profile branch; the beat to `PUBLIC_BEAT_TIEBREAK_PRIORITY` (lowest priority); and a selectability gate (publish only when strength > 0). |
| `services/story_feed.py` | Mapped the beat and `stable_core` to `tone: rest` / `category: rested`; valid positive stories now publish as `quality_status: published` with **no** review flag/limitation; removed the resolved blanket feed limitation. |

The four public beats are now five: `route_change`, `coverage_pressure`, `depth_constraint`, `sustainability_question`, **`availability_depth`**.

### Copy direction
Positive openings are measured and trust-first, e.g. *"The bullpen has more rested options than most clubs today"*, *"{possessive} late-inning plan can lean on more than one rested group"*. They are never hype (no "elite", "dominate", "no issues") and never predictive/betting (validated against `BANNED_TERMS`/`ROBOTIC_TERMS`/`DENIED_PUBLIC_PHRASES`).

---

## Why Home migration was blocked before this

The Story Coverage Audit found Story Intelligence V1 **detected** the positive signals (`optionality_strength`, `stable_core`) but then lost them in three downstream layers:

1. **Contract** — both mapped to pressure/change beats (`sustainability_question` / `route_change`); there was no positive beat.
2. **Ranking** — positive reads scored **0** selection strength, and `optionality_strength + sustainability_question + strength ≤ 0` was actively dropped by `_candidate_is_publicly_selectable`, so a positive-only team landed in `NEUTRAL_NO_VALID_FRAME`.
3. **Copy** — the beat copy was worry-framed ("If this workload pattern holds, the route remains narrow…").

Net effect: **good-news-only teams published nothing** under the canonical engine, so Home's "More Options" / "Arms To Spare" stories would have silently disappeared on migration. Phase 1.5 fixes all three layers so those teams now publish a positive story.

---

## How positive stories are selected

1. **Detection (unchanged):** `optionality_strength` fires on `optionality_band ∈ {flexible, deep}`; `stable_core` on `stability_band == 'stable'`. These are the evidence gate — the engine only sees a positive read when the bands genuinely say so.
2. **Frame:** the construction frame must carry the supporting numbers (optionality needs `optionality_band` + `practical_close_game_paths_count`; stable needs current/previous core + `core_stability_pct`). An incomplete frame is invalid → no story (no fabrication).
3. **Beat:** the interpreter maps the observation to `availability_depth` and keeps the writer's positive copy.
4. **Strength:** `_selection_strength_for_availability_depth` scores the read — optionality by band (`deep` +3 / `flexible` +1), close-game paths, clean options, and available arms (max 6); stable core by stable band, retention, and zero changes (max 4). These ranges sit **below** the pressure scorers' maxima (7–10).
5. **Selection:** candidates sort by strength first. A **stronger pressure story always wins**; on equal strength, the tiebreak demotes `availability_depth` so pressure/change is preferred. A positive story is published when it is the best honest read — typically when no pressure story qualifies.
6. **Selectability:** `availability_depth` publishes only when `strength > 0`, so a borderline read does not produce a fabricated positive.

**Canonical adapter:** a published positive story surfaces as `story_available: true`, `tone: rest`, `category: rested`, `quality_status: published`, with no positive-beat limitation. (A positive observation that is ever *still* reframed into a non-positive beat is flagged `review` defensively.)

---

## What is still out of scope

- **No UI migration.** Home, Stories, and Team Board still read their existing fields. The `/story` endpoint and the dashboard `stories` feed now *can* return `availability_depth`; the Team Board `StoryCard` renders it with a generic label until Team Board is migrated (no frontend changes were made).
- **No new detection.** Thin trust lane, bridge instability, what-changed/delta, day-over-day continuity (new/ongoing/returning), and league-wide/no-team notes remain undetected by Story Intelligence V1 — they gate Stories/Team Board parity, not Home.
- **No empty/quiet-feed fallback yet.** When the canonical feed is empty on a quiet day, the hero/quiet-day and league-note behavior still needs a decision (Phase 1.6).
- **Legacy engines untouched.** The four-beat feed and the frontend client generators are unchanged.

---

## Validation

Run with `PYTHONPATH=backend python -m pytest …` (test DB defaults to in-memory SQLite). New/updated tests:

- `tests/test_story_intelligence_service_v1.py`: `optionality_strength` publishes `availability_depth`; `stable_core` publishes `availability_depth`; **pressure outranks positive when pressure is stronger**; weak/incomplete positive evidence stays neutral (no fabrication); updated the public-beat map test.
- `tests/test_story_feed.py`: published positive story → `rest`/`rested`, `published`, no review flag; stable-core positive → rested; reframed positive still flagged (defensive); existing suppression/legacy tests unchanged.

Suites run green: `test_story_intelligence_service_v1`, `test_story_feed`, `test_story_writer_v1`, `test_story_voice_library_v1`, `test_four_beat_stories`, `test_story_audit_preview_v1`, `test_four_beat_real_quality_audit`, `test_story_api_v1`, `test_story_quality`, `test_story_construction_engine`, `test_bullpen_intelligence_contracts`, `test_dashboard_snapshot`, and the dashboard canonical-stories integration test. The only failures (`…clean_trust_authority`, `…governed_authority` in `test_bullpen_dashboard.py`) are **pre-existing and unrelated** — they reproduce on the committed baseline with these changes stashed (date-sensitive availability classification).

---

## Next recommended phase

**Phase 1.6 — empty/quiet-feed + league-note fallback**, then **Phase 2 — Home migration** behind a feature flag. With the positive beat in place, the remaining Home blockers are (a) a defined hero/quiet-day behavior when the canonical feed is empty, plus a league-note path, and (b) continuity (new/ongoing/returning) wired to canonical `story_id`. Trust-lane and bridge detectors remain deferred to the Team Board phase.
