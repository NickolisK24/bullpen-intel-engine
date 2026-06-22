# Quiet-Day & League-Context Strategy — Phase 1.6 (June 2026)

**Companion docs:** `story_coverage_audit_june_2026.md`, `positive_depth_story_beat_phase_1_5.md`, `story_adapter_phase_1_notes.md`
**Scope:** Backend-only. No frontend changes. No legacy system removed. No UI migrated (Home, Stories, Team Board untouched).

---

## What changed

The canonical story feed (`payload['stories']`) now carries a **`league_context`** section so the feed has an honest answer on quiet days, when few clubs have a publishable team story. It describes today's league-wide bullpen environment from **real counts**, or returns a truthful neutral fallback — it never fabricates a team-specific narrative and makes no predictions.

| File | Change |
|---|---|
| `services/story_feed.py` | Added `classify_story_day`, `build_league_context`, day-class and league-mode constants with documented thresholds, and a `league_context` key on the feed. `build_canonical_story_feed` accepts an optional `league_signal`. |
| `api/bullpen.py` | Added `_canonical_league_signal(landscape, availability_records)` (league-wide counts from the already-built landscape) and passes it into the canonical feed. |

---

## Detection rules

### Day class (story density)
By the number of **publishable** team stories in the feed. Thresholds map to the Home surfaces a future migration would fill ("Three Things To Watch" needs ~3 stories; the feed shows up to ~8):

| Day class | Rule | Meaning |
|---|---|---|
| `no_story` | publishable == 0 | No club has a publishable story. |
| `quiet` | 1–2 (`QUIET_STORY_MAX = 2`) | Too few to fill the watch strip. |
| `low_story` | 3–5 (`LOW_STORY_MAX = 5`) | A thin news day. |
| `normal` | ≥ 6 | A typical news day. |

### League environment (share of clubs with bullpen data, ~30 in season)
Selected in priority order; the first match wins. Shares use a real denominator (`team_count` = distinct clubs in the availability records).

| Mode | Rule | Rationale |
|---|---|---|
| `broadly_constrained` | constrained share ≥ **0.40** | ≥40% (~12 clubs) under real pressure is well above a normal day → widespread. |
| `pressure_concentrated` | pressure present and constrained share ≤ **0.25** (or, without a league signal, ≤ **3** pressure stories) | Pressure exists but is contained to a minority of clubs. |
| `depth_healthy` | available share ≥ **0.50** and not concentrated/widespread pressure | ≥50% of clubs with rested depth is a broadly healthy league. |
| `availability_tightening` / `availability_easing` | optional `availability_trend` signal only | Day-over-day direction, surfaced only when a real trend is supplied (never fabricated). |
| `broadly_stable` | quiet/no-story day with no clear signal | Honest "nothing unusual" read. |
| `neutral` | low/normal day with no dominant pattern | Truthful "no league-wide theme" observation. |

`broadly_stable` and `neutral` are the honest fallbacks: `generated: false`, `quality_status: "neutral"` (approved, non-dramatic). The substantive environment modes are `generated: true`, `quality_status: "published"`.

---

## League context contract

`payload['stories']['league_context']`:

```jsonc
{
  "capability": "baseballos_league_context_v1",
  "mode": "pressure_concentrated",      // see mode table
  "day_class": "low_story",             // normal | low_story | quiet | no_story
  "headline": "Today's bullpen pressure is concentrated in a small set of clubs.",
  "summary": "Most bullpens are in normal shape; the meaningful workload pressure is contained to 5 clubs.",
  "evidence": {
    "team_story_count": 9,
    "publishable_story_count": 6,
    "pressure_story_count": 4,
    "rest_story_count": 1,
    "watch_story_count": 1,
    "league_team_count": 30,
    "constrained_team_count": 5,
    "available_team_count": 8,
    "constrained_team_share": 0.167,
    "available_team_share": 0.267,
    "availability_trend": null
  },
  "generated": true,                    // false for honest neutral fallbacks
  "quality_status": "published",        // "published" | "neutral" (both displayable)
  "as_of_date": "2026-06-22",
  "limitations": [ "derived_from_published_team_stories_and_league_availability_counts", … ]
}
```

Every claim in `headline`/`summary` is backed by a count in `evidence` — the club number in the copy equals the evidence count, so there is no fabrication. Copy is measured and contains no prediction/betting/ranking language.

---

## Quiet-day examples

| Situation | Mode | Headline |
|---|---|---|
| 0 publishable stories | `broadly_stable` | "No major bullpen story is emerging today." |
| 2 watch-level stories | `broadly_stable` | "No major bullpen story is emerging today." |
| Few stories, 5 constrained clubs of 30 | `pressure_concentrated` | "Today's bullpen pressure is concentrated in a small set of clubs." |
| 18 of 30 clubs rested, none constrained | `depth_healthy` | "Most bullpens carry healthy late-inning depth today." |
| 14 of 30 clubs constrained | `broadly_constrained` | "Bullpen pressure is unusually widespread across the league today." |
| Low day, only watch-level reads | `neutral` | "No single bullpen pattern stands out across the league today." |

---

## Relationship to Home migration

The canonical feed now exposes, from **one backend contract**, everything Home needs to choose what to render on any day:

- **Team stories** — `stories.items` (available, with `tone`/`category`).
- **League story** — `stories.league_context` when `generated: true` (a substantive league observation, e.g. "The Other Side"-style depth note or a concentration read).
- **Quiet-day fallback** — `stories.league_context` when `quality_status: "neutral"` (a calm "League Check-In"-style read).

So Home can migrate to the canonical feed and still cover quiet days without client-side story generation. **This closes the quiet-day blocker from the coverage audit.** No Home code was changed in this phase.

---

## Known limitations

- **Day-over-day trend not wired.** `availability_tightening` / `availability_easing` are supported in the contract but only fire when a real `availability_trend` signal is supplied. Phase 1.6 passes `null` (the dashboard's day-over-day deltas are computed after the feed). Wiring a real trend is a small follow-up; until then the system describes *today's* environment, not a trend, and never fabricates direction.
- **Team set mirrors the four-beat feed.** `publishable_story_count` is drawn from the canonical feed, whose team set still mirrors the four-beat feed; league availability shares use the full landscape, so the environment read is league-wide even when the story set is a subset.
- **No frontend consumption yet.** Home/Stories/Team Board still read legacy fields; `league_context` is additive and unused by the UI until Phase 2.

---

## Next recommended phase

**Phase 2 — Home migration** (behind a feature flag): render `stories.items` for team cards, `stories.league_context` for the league/quiet-day read, with the legacy client path as fallback. Optional Phase 1.7: wire a real day-over-day `availability_trend` into the league signal, and key continuity (new/ongoing/returning) onto canonical `story_id`.
