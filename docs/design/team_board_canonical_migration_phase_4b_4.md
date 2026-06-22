# Team Board Canonical Migration — Phase 4B.4 (June 2026)

**Companion docs:** `team_board_canonical_migration_audit.md` (Phase 4A), `team_board_storycard_parity_phase_4b_1.md` (4B.1), `trust_lane_story_phase_4b_2.md` (4B.2), `bridge_instability_story_phase_4b_3.md` (4B.3)
**Scope:** Team Board only, behind a feature flag. **No legacy code removed. `TeamBullpenStoryPanel` not deleted. Home and Stories untouched.**

---

## What changed

The Phase 4A audit found the Team Board renders **two competing team stories** on one screen:

1. **`StoryCard`** — the **canonical** story, already consuming `GET /api/bullpen/teams/<id>/story` (Story Intelligence V1).
2. **`TeamBullpenStoryPanel`** — a **client-generated** duplicate.

The duplicate could not be removed until the canonical engine reached parity. Trust Lane (4B.2) and Bridge Instability (4B.3) closed that gap, so this phase migrates the Team Board to the single canonical story behind a flag.

| File | Change |
|---|---|
| `frontend/src/components/bullpen/board/teamBoardCanonicalView.js` (new) | Flag reader + the mount decision: `canonicalTeamBoardEnabled`, `canonicalTeamStoryUnavailable`, `shouldMountLegacyStoryPanel`. |
| `frontend/src/components/bullpen/board/TonightsBullpenBoard.jsx` | Computes `showStoryPanel` from the flag (+ fallback) instead of always-on. The canonical `StoryCard` rendering is unchanged. |
| `frontend/.env.example` | Documents the flag (default off, commented). |

The change is intentionally minimal: the board already mounts the legacy panel only when `BullpenBoardView` receives `showStoryPanel`, so the migration just drives that one prop from the flag. No story content, board data surface, or component layout was redesigned.

---

## Feature flag behavior

- **Flag:** `VITE_USE_CANONICAL_TEAM_BOARD`
- **Default:** **off (safe).** Only an explicit truthy value (`true` / `1` / `on` / `yes`) enables it.

| State | Canonical `StoryCard` | Legacy `TeamBullpenStoryPanel` | Result |
|---|---|---|---|
| **Flag off** (default) | renders | mounts (existing condition) | current behavior — both stories |
| **Flag on**, canonical story usable | renders | **not mounted** | one canonical story |
| **Flag on**, canonical story **unavailable** | renders (its error/quiet state) | mounts (fallback) | legacy fallback — board still has a story |

`canonicalTeamBoardEnabled(env)` reads the flag (env injectable for tests). The canonical `StoryCard` above the board is rendered in **all** states — the flag only governs whether the *duplicate* legacy panel also mounts.

---

## Migration strategy

The Team Board's single story source is the existing canonical `StoryCard` (already on the canonical `/story` endpoint — no new story system was created). The migration removes the *duplicate narrative surface* only:

`shouldMountLegacyStoryPanel({ enabled, storyUnavailable, baseShouldShow })`

- `baseShouldShow` — the pre-existing condition for the panel (e.g. not the unavailable-only view mode). Always respected, so embedded/unavailable-only contexts are unchanged.
- **Flag off →** mount the legacy panel (current behavior).
- **Flag on →** hide it (canonical-only), unless the canonical story is unavailable.

Because the flag only flips one prop, the migration is fully reversible and carries no risk to the rest of the board.

---

## Fallback behavior

`canonicalTeamStoryUnavailable(story)` treats the canonical story as unavailable **only on a real failure** — the fetch errored or returned nothing. A **neutral/quiet** canonical story (`story_available: false`) is a *valid* canonical response (the `StoryCard` renders that state cleanly), not a failure. When the canonical story is genuinely unavailable and the flag is on, the legacy `TeamBullpenStoryPanel` returns as a safe fallback, so **the board is never left without a story**.

---

## Preserved Team Board data surfaces

Only the story duplication is removed. Everything else on the board is untouched and verified by tests:

- bullpen snapshot / context cards, pitcher groups, per-pitcher availability explanations,
- freshness banner, roster status, game context, board totals, and the pitcher label key.

---

## What remains legacy

- **`TeamBullpenStoryPanel`** and **`teamBullpenStoryView.js`** are **kept in place** — they are the flag-off path and the canonical-unavailable fallback. **Not deleted.**
- The legacy client story engine is still imported by `BullpenBoardView` (gated by `showStoryPanel`).
- Removal happens only after the flag has run in production (next phase).

---

## Tests

`frontend/tests/teamBoardCanonicalMigration.test.mjs` (15 tests): flag default-off and truthy parsing; `canonicalTeamStoryUnavailable` (failure vs neutral vs loading); the `shouldMountLegacyStoryPanel` matrix (flag off → mount; flag on + usable → hide; flag on + unavailable → fallback; base-off → never); `BullpenBoardView` mounts the panel with `showStoryPanel: true` and hides it with `false`; **board data surfaces remain** when the panel is hidden; the canonical `StoryCard` renders the single story incl. `trust_lane` ("Trust Lane") and `bridge` ("Bridge Instability"); `TonightsBullpenBoard` wires the flag into `showStoryPanel`; and **Home/Stories do not reference the Team Board flag** (unchanged). Full frontend suite: **536 passed, 0 failed** (incl. `teamBullpenStoryPanel`, `tonightsBullpenBoard`, `storyCard`, `homeCanonicalStories`, `storiesCanonicalFeed`). No backend changes.

---

## What was intentionally not changed

- **Legacy code not removed** — `TeamBullpenStoryPanel` / `teamBullpenStoryView.js` stay as the flag-off path and fallback.
- **Home** and **Stories** — untouched (no file changes; their suites pass; a guard test asserts they never reference the Team Board flag).
- **Backend** — no changes; the canonical `/story` endpoint already serves the StoryCard.
- **Component layout / data surfaces** — story-duplication removal only.

---

## Next recommended phase

- **Phase 4B.5 — Legacy panel retirement:** once the flag has been validated on in production (one canonical story, all surfaces intact), flip it on by default, then remove `TeamBullpenStoryPanel` and `teamBullpenStoryView.js` (and their tests), leaving the canonical `StoryCard` as the sole Team Board story.
- **Backend cleanup** (consolidation plan): with Home, Stories, and the Team Board all on canonical, retire the duplicate client/Four-Beat story paths — only after canonical has run in production.
