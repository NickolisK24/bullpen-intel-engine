# Home Migration to Canonical Stories — Phase 2 (June 2026)

**Companion docs:** `story_consolidation_plan_june_2026.md`, `positive_depth_story_beat_phase_1_5.md`, `quiet_day_strategy_phase_1_6.md`, `canonical_story_continuity_phase_1_7.md`
**Scope:** Home page only, behind a feature flag. Stories and Team Board untouched. No legacy engine removed (`storyEngineV1.js` stays).

---

## What changed

The Home page can now render its story surfaces — the flagship hero, the "Three Things To Watch" cards, and the league context — from the **canonical backend feed** (`dashboard.stories`) instead of generating competing client-side narratives from raw counts. The migration is fully reversible via a feature flag.

| File | Change |
|---|---|
| `frontend/src/components/home/homeCanonicalStoriesView.js` (new) | The canonical Home adapter: reads the flag and maps `dashboard.stories` into the exact shapes Home's existing components render. |
| `frontend/src/components/home/Home.jsx` | `HomeView` takes a `canonicalStoriesEnabled` flag (default reads the env flag) and swaps the hero / watch / league sources behind it. No layout change. |

The adapter is the **single** place canonical mapping lives (no mapping scattered across components). It only formats backend copy — it never invents story content.

> **File location note:** the brief suggested `frontend/src/features/bullpen/home/…`; the codebase convention is `components/home/*View.js` (e.g. `homeIntelligenceView.js`), so the adapter lives there for consistency.

---

## Feature flag behavior

- **Flag:** `VITE_USE_CANONICAL_HOME_STORIES`
- **Default:** **off (safe).** Only an explicit truthy value (`true` / `1` / `on` / `yes`) enables it.
- **Disabled →** Home uses the existing legacy behavior (`getHeroStory` / `getTodayWatchItems` / `getLeagueContext` + `storyEngineV1`).
- **Enabled →** Home uses canonical stories **when the payload is well-formed**; otherwise it falls back to legacy (see Fallback rules).

`canonicalHomeStoriesEnabled(env)` reads the flag (env injectable for tests). `HomeView` accepts `canonicalStoriesEnabled` as a prop (defaulting to the flag) so the decision is testable without env plumbing.

---

## Mapping: canonical contract → Home view model

| Home consumer | Source | Mapping |
|---|---|---|
| **Hero** (`HeroStory`) | the first publishable `stories.items[]`, else `stories.league_context` | `tone` ← item `tone`; `kicker` ← from `story_type`; `headline` ← item `headline`; `observation` ← observation+baseline+cause **beats**; `whyItMatters` ← **constraint** beat; `storyStatus` ← `continuity.state`; `chips`/`whatBaseballOSSaw` ← `[]`; `team` ← item team identity + board href. |
| **Watch cards** (`BullpenStories`) | publishable `stories.items[]` (top 3) | `title` ← `headline`; `narrative` ← item `narrative`; `tone` ← `tone`; `kicker` ← from `story_type`; `href`/`cta` ← team board link. |
| **League context** (`LeagueContext`) | `stories.league_context` | `summary` ← `headline` + `summary`; three `facts` ← `evidence` counts (constrained / watch / available clubs); `href` `/stories`. |

**Prose split:** the four authored beats map cleanly to the hero's two prose slots — observation/baseline/cause become the descriptive `observation`, and the constraint beat becomes the forward-looking `whyItMatters`. The watch cards render the full `narrative`.

**Positive stories** render naturally: an `availability_depth` / `rested` story maps to `tone: rest` and a "More Options" kicker — never a warning or pressure label.

**Continuity** is surfaced as the hero's Story Status badge (`new` → "New", `ongoing`/`unchanged` → "Ongoing", `changed` → "Updated"), and is carried on each card for future use. These are short, factual status labels — not invented baseball claims. `compared: false` (no prior baseline) renders no badge.

---

## Fallback rules (flag enabled)

Story source priority:
1. **Publishable canonical team stories** first (the hero + watch cards).
2. **`league_context`** when team stories are sparse/quiet (drives the hero on quiet/no-story days and the league card every day).
3. **Neutral league fallback** when no meaningful team story exists (`league_context` `mode` `broadly_stable` / `neutral`, `quality_status: neutral`).
4. **Legacy fallback** only if the canonical payload is **missing or malformed** (`dashboard.stories.items` not an array) — `hasUsableCanonicalStories` is false, so Home reverts to the legacy engine. A present-but-empty feed (a real quiet day) is *usable* and handled by canonical, not the legacy fallback.

No fabricated stories: when there is no publishable story, Home shows the honest backend league/quiet read, not an invented narrative.

---

## Tests

`frontend/tests/homeCanonicalStories.test.mjs` (10 tests): flag default-off and truthy parsing; `hasUsableCanonicalStories` (present / empty / malformed); positive story → rested card (not a warning); hero prose/why-it-matters split + continuity badge; quiet-day league/quiet hero; league-context mapping; and `HomeView` integration — **flag enabled renders the canonical positive story, flag disabled keeps legacy, malformed payload falls back to legacy, quiet day renders the league hero**. Full frontend suite: **502 passed**. Backend contract (`test_story_feed.py`): **43 passed**.

---

## What was intentionally not changed

- **Stories page** and **Team Board** — untouched (verified: no changes to their files; their suites pass).
- **`storyEngineV1.js`** and the legacy `homeIntelligenceView.js` story functions — kept in place; they are the flag-off path.
- **UI layout** — this is a data-source migration, not a redesign; Home looks substantially the same.
- **Backend** — no backend changes; the adapter consumes the existing Phase 1.5–1.7 contract.
- **Count chips** on the hero are omitted under canonical (the canonical item carries prose, not raw counts) — a minor, documented difference, not a layout change.

---

## Next migration recommendation

- **Default-on rollout:** once validated in staging, flip `VITE_USE_CANONICAL_HOME_STORIES` on by default, then (a later phase) remove the legacy Home story path and `storyEngineV1.js` from runtime — only after Home has run on canonical stories in production.
- **Then Stories**, then **Team Board** migrations (each its own flag), reusing this adapter pattern. Team Board additionally needs trust-lane and bridge-instability detectors (from the coverage audit) before it can fully migrate.
- **Optional polish:** surface canonical continuity in the "What Changed" surface; derive hero count chips from canonical evidence if a structured count is added to the contract.
