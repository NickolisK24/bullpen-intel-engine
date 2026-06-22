# Stories Page Migration to Canonical Feed — Phase 3 (June 2026)

**Companion docs:** `story_consolidation_plan_june_2026.md`, `quiet_day_strategy_phase_1_6.md`, `canonical_story_continuity_phase_1_7.md`, `home_canonical_stories_phase_2.md`
**Scope:** Stories page only, behind a feature flag. Home and Team Board untouched. No legacy engine removed; the Four-Beat path and API field stay.

---

## What changed

The Stories page can now render its feed from the **canonical backend feed** (`dashboard.stories`) instead of the legacy Four-Beat feed (`dashboard.four_beat_stories`). With Home (Phase 2) and Stories now on the same source, the two pages stop telling competing narratives. The migration is fully reversible via a feature flag.

| File | Change |
|---|---|
| `frontend/src/components/stories/storiesCanonicalFeedView.js` (new) | The canonical Stories adapter: reads the flag and maps `dashboard.stories` into the page's existing feed shape. |
| `frontend/src/components/stories/Stories.jsx` | `StoriesView` takes a `canonicalStoriesEnabled` flag (default reads the env flag) and swaps the feed source behind it. No layout change. |

The adapter is the single place canonical mapping lives. It only formats backend copy — it never invents story content.

> **File location note:** the brief suggested `frontend/src/features/bullpen/stories/…`; the codebase convention is `components/stories/*View.js` (e.g. `storiesFeedView.js`), so the adapter lives there for consistency (matching Phase 2).

---

## Feature flag behavior

- **Flag:** `VITE_USE_CANONICAL_STORIES_PAGE`
- **Default:** **off (safe).** Only an explicit truthy value (`true` / `1` / `on` / `yes`) enables it.
- **Disabled →** Stories uses the existing Four-Beat feed (`getFourBeatStoryFeed`).
- **Enabled →** Stories uses the canonical feed **when the payload is well-formed**; otherwise it falls back to Four-Beat (see Fallback rules).

`canonicalStoriesPageEnabled(env)` reads the flag (env injectable for tests). `StoriesView` accepts `canonicalStoriesEnabled` as a prop (defaulting to the flag) so the decision is testable without env plumbing.

---

## Canonical → Stories mapping

`getCanonicalStoryFeed(dashboard)` returns the page's existing feed shape `{ hasStories, items, fallback }`, where `items` are the cards the page already renders:

| Card field | Source |
|---|---|
| `teamId` / `teamName` / `abbr` | item `team_id` / `team_name` / `team_abbreviation` |
| `title` | item `headline` |
| `narrative` / `body` | item `narrative` |
| `tone` | item `tone` (stress / rest / watch / neutral) |
| `category` | item `category` (stressed / rested / watch) — drives the filter lanes |
| `kicker` | derived from `story_type` |
| `href` / `cta` | team board link |
| `read` (badge) | **continuity** — `new` → "New", `changed` → "Updated"; otherwise no badge |

Plus **one league-lane card** built from `stories.league_context` (`category: 'league'`, `title` ← league `headline`, `narrative` ← league `summary`, tone derived from league `mode`). It renders every day, including quiet days.

**Order / priority:** publishable team stories first, then the league card. **Suppressed stories are excluded** from the feed (no diagnostics surface is needed).

**Positive stories** render naturally: an `availability_depth` / `rested` story maps to `tone: rest` and a "More Options" kicker — never a warning. The filters, scope counts, team links, share buttons, and empty states all keep working because the card shape and `category` lanes are preserved.

---

## Fallback rules (flag enabled)

1. **Publishable canonical team stories** first.
2. **`league_context`** as the page-level league/quiet-day observation (always rendered as the league-lane card).
3. **Quiet/no-story days** still render cleanly — when no team story is publishable, the feed is just the league card.
4. **Legacy Four-Beat fallback** only if the canonical payload is **missing or malformed** (`dashboard.stories.items` not an array) — `hasUsableCanonicalStoriesFeed` is false. A present-but-empty feed (a real quiet day) is *usable* and handled by canonical.

No fabricated stories: with no publishable story, the page shows the honest backend league read, not an invented narrative.

---

## Duplication handling

The Stories page is a **flat feed with no separate hero/featured story**, so there is no flagship-vs-list duplication to resolve. The adapter still guarantees no duplicates: each canonical item maps to exactly one card, and the league context maps to exactly one league-lane card (tested: team ids in the feed are unique). If a featured slot is ever added, the league card and team cards remain distinct keys.

---

## Tests

`frontend/tests/storiesCanonicalFeed.test.mjs` (10 tests): flag default-off and truthy parsing; `hasUsableCanonicalStoriesFeed` (present / empty / malformed); feed maps publishable team stories + a league card and excludes suppressed; positive → rested card; no duplicate team; quiet-day league card; and `StoriesView` integration — **flag enabled renders canonical stories + league context, flag disabled keeps Four-Beat, malformed payload falls back to Four-Beat, quiet day renders the league card**. Full frontend suite: **512 passed** (incl. `homeIntelligence`, `homeCanonicalStories`, `storiesFeed`, `tonightsBullpenBoard`, `storyCard`, `teamBullpenStoryPanel`, `storyEngineV1`). Backend contract (`test_story_feed.py`): **43 passed**.

---

## What was intentionally not changed

- **Home** and **Team Board** — untouched (no changes to their files; their suites pass).
- **Legacy Four-Beat path** — `storiesFeedView.js` / `getFourBeatStoryFeed` kept in place; it is the flag-off and fallback path. **Four-Beat code not deleted.**
- **Backend** — no backend changes; `dashboard.four_beat_stories` remains in the API. The adapter consumes the existing Phase 1.5–1.7 contract.
- **UI layout** — data-source migration only; filters, cards, scope counts, team links, share actions, and empty states are unchanged.
- **Suppressed stories** are not surfaced (no new diagnostics UI was built).

---

## Next migration recommendation

- **Default-on rollout:** once Home and Stories are validated on canonical in staging/production, flip both flags on by default, then (a later phase) remove the legacy client story paths (`storyEngineV1.js`, the Four-Beat *rendering* path) — only after canonical has run in production.
- **Team Board** is the remaining surface. Per the coverage audit it needs new backend detectors (trust-lane, bridge-instability) before its client panel can fully migrate; the StoryCard already consumes the canonical `/story` endpoint.
- **Backend cleanup** (consolidation plan Phase 6) — retire the duplicate Four-Beat backend engine — should come only after all three pages are on canonical.
- **Optional polish:** surface continuity on more states; add a league-context day-over-day trend once wired.
