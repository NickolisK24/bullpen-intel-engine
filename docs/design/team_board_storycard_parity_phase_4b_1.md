# Team Board StoryCard Canonical Parity — Phase 4B.1 (June 2026)

**Companion docs:** `team_board_canonical_migration_audit.md` (Phase 4A), `positive_depth_story_beat_phase_1_5.md`
**Scope:** Team Board `StoryCard` label parity only. No Team Board migration. No backend changes. `TeamBullpenStoryPanel` untouched.

---

## What changed

The Team Board's `StoryCard` (the "Bullpen Note") already consumes the canonical engine (Story Intelligence V1 via `GET /api/bullpen/teams/<id>/story`). Since Phase 1.5 that engine can emit the positive `availability_depth` beat, but `StoryCard` had no display mapping for it, so positive stories rendered with the generic **"Bullpen story"** label and no helper line.

This phase adds the missing display mapping:

| File | Change |
|---|---|
| `frontend/src/components/bullpen/board/storyCardView.js` | Added `availability_depth` to `STORY_TYPE_DISPLAY` → label **"More Options"**, helper *"How much rested late-inning depth the bullpen has to work with."* |
| `frontend/tests/storyCard.test.mjs` | Updated the beat-list test (four → five public beats) and added parity tests. |

**Label choice:** "More Options" matches what the canonical feed surfaces already show for `availability_depth` (Home `homeCanonicalStoriesView.js` and Stories `storiesCanonicalFeedView.js` both map it to "More Options"), so the positive beat now reads consistently across Home, Stories, and the Team Board.

**Positive styling:** `StoryCard` has **no per-story-type severity/tone styling** — every available story renders in the same neutral shell (`StoryShell` default `bg-dugout/75`); only the load-error state uses amber. So the positive `availability_depth` story is already not framed as a warning; no tone change was needed (verified by test).

**Everything else preserved:** the four existing beats (`route_change`, `coverage_pressure`, `depth_constraint`, `sustainability_question`), the neutral/suppressed state, loading/error states, and the "old internal type → generic fallback" behavior are unchanged.

---

## Why full Team Board migration is deferred

The Phase 4A audit found the Team Board renders **two** competing team stories on the same screen:
1. `StoryCard` — the backend canonical story (this surface).
2. `TeamBullpenStoryPanel` — a **client-generated** story from `/board` counts, with 14 archetypes.

Collapsing to the single canonical story would remove `TeamBullpenStoryPanel`, but that panel is the **only** source of **trust-lane** and **bridge-instability** stories, and the canonical engine detects neither (its observation engine has six types: rotation/concentration/depth pressure, core-transition, stable-core, optionality-strength). Removing the panel today would be a user-facing regression. So full migration waits on backend detector work; this phase ships only the safe, additive label fix.

`TeamBullpenStoryPanel` therefore **remains mounted and unchanged** (guarded by a test that `BullpenBoardView` still imports and renders it).

---

## Remaining Team Board blockers

1. **Trust-lane detector** — Story Intelligence V1 has no trust-lane observation. Needs: observation type + public beat + selection strength + writer copy + `story_feed` adapter mapping. (Backs 4 of the client panel's archetypes — the larger gap.)
2. **Bridge-instability detector** — no handoff/bridge observation (the existing `role_stability` signals describe the late-inning core, not the bridge). Needs the same five layers.

Until both exist in the canonical engine, the duplicate client panel cannot be removed without losing those story types.

---

## Validation

`frontend/tests/storyCard.test.mjs` — **12 passed** (incl. the new: `availability_depth` → "More Options"; positive story not framed as a warning; `TeamBullpenStoryPanel` still mounted; updated five-beat list). Team Board + canonical suites (`teamBullpenStoryPanel`, `tonightsBullpenBoard`, `tonightsBullpenBoardContext`, `homeCanonicalStories`, `storiesCanonicalFeed`) — **77 passed**. Full frontend suite — **515 passed, 0 failed**. No backend changes.

---

## Next recommended phase

- **Phase 4B.2 — Backend trust-lane detector** (then **4B.3 — bridge-instability detector**), each end-to-end (observation engine → interpreter beat → service selection → writer/voice → `story_feed` mapping) with tests.
- **Phase 4B.4** — behind `VITE_USE_CANONICAL_TEAM_BOARD`, render the single canonical story and stop mounting `TeamBullpenStoryPanel` (legacy kept on flag-off).
- **Phase 4B.5** — validate in production, then remove `TeamBullpenStoryPanel` + `teamBullpenStoryView.js`.

The board's data/context/provenance/explanation surfaces (stress, snapshot, freshness, roster, game context, per-pitcher cards and availability explanation) remain Team Board-specific and out of story-migration scope.
