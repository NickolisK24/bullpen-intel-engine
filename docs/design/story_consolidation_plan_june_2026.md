# BaseballOS Story Consolidation Plan — June 2026

**Type:** Implementation plan (design only — no code in this document)
**Companion audit:** `docs/audits/story_architecture_audit_june_2026.md`
**Objective:** Collapse the four current narrative generators into **one canonical backend story system**, with the browser doing presentation only.
**Status:** Plan for review. Do not implement from this document until the canonical engine and the open blockers (§9) are signed off.

---

## 1. Recommended Canonical Engine

**Build the canonical system on Story Intelligence V1 (Engine 3, `story_intelligence_service_v1.py`) and port the Four-Beat Feed's cross-team ranking onto it.**

This matches the stated preference and is supported by the contract evidence gathered for this plan:

- Engine 3's `/teams/<id>/story` response (`_story_api_payload`, `bullpen.py:1735-1770`) is already the most complete and most governed story contract in the codebase. It ships: `story_available`, `neutral_reason` (a real suppression signal), `story_type` (public beat), `headline` + four structured paragraphs, `freshness`, `trust_metadata`, `supporting_context`, and `limitations`.
- It is the newer, versioned, deterministic stack (`2026-06-21.v1`) with a clean coordinator (context → observation → construction frame → writer → public-beat interpreter), explicit per-team selection/suppression, and an existing offline QA harness.
- What it lacks is purely *additive*: stable IDs, `tone`/`category`, an assembled single-string `narrative`, a `beats[]` array, share-card fields, and a **feed/ranking mode** (it is single-team only today).

The Four-Beat Feed (Engine 2, `four_beat_stories.py`) contributes exactly one thing worth keeping: its **cross-team feed mechanics** — ranking by strength, one-story-per-team selection, duplicate-phrase suppression, and archetype/lead diversification. We extract that essence into the canonical feed builder and retire the rest of Engine 2's parallel observation/prose/gate stack.

The two browser engines (Engine 1 `storyEngineV1.js`, Engine 4 `teamBullpenStoryView.js`) are removed from runtime; the client renders canonical output.

---

## 2. Canonical Base — What Each UI Needs vs. What Engine 3 Provides

The canonical story object must be a **superset** of every field the three UIs read today, so migration is additive and reversible.

### 2.1 Field demand by surface (verified against source)

| Field the UI reads | Home (`BullpenStories.jsx`) | Stories (`storiesFeedView.js`) | Team Board (`storyCardView.js`) | In Engine 3 today? |
|---|:--:|:--:|:--:|---|
| `story_available` / suppression | — | — | ✅ (`:67`) | ✅ `story_available`, `neutral_reason` |
| `headline` / `title` | ✅ `title` | ✅ `title\|signal\|rule_label` | ✅ `headline` | ✅ `headline` (no `title` alias) |
| Narrative prose (single string) | ✅ `narrative\|story_body\|observation\|body` | ✅ `narrative\|story_body\|beats.join` | — (uses 4 paragraphs) | ⚠️ only as 4 separate paragraphs |
| 4 paragraphs (`observation/baseline/cause/constraint`) | — | — | ✅ (`:54-60`) | ✅ |
| `beats[]` `{key,label,text}` | — | ✅ (`:105-113`) | — | ❌ (must synthesize) |
| `story_type` (beat) | — | — | ✅ (`:69`) | ✅ |
| `tone` (stress/watch/rest) | ✅ | ✅ (`:120`) | — | ❌ (derive) |
| `category` (stressed/watch/rested/league) | — | ✅ (`:86-92`) | — | ❌ (derive) |
| `kicker` / `rule_label` | ✅ | ✅ (`:119`) | — | ❌ (derive) |
| `href` / `cta` | ✅ | ✅ (`:126-127`) | — | ❌ (derive, presentation) |
| `disclosure_note` | ✅ | ✅ (`:102`) | — | ⚠️ via `supporting_context`/`limitations` |
| `continuity_note` / `context_note` | ✅ | — | — | ⚠️ via `supporting_context` |
| `freshness`, `trust_metadata` | — | — | ✅ (`:65-66`) | ✅ |
| team id/name/abbr | ✅ | ✅ (`:96-98`) | ✅ | ✅ |

**Reading:** Engine 3 already covers the Team Board's needs. To also feed Stories and Home unchanged, the canonical contract must **add** `tone`, `category`, `kicker`, an assembled `narrative` string, `beats[]`, `href`/`cta`, and `disclosure_note`/`continuity_note`/`context_note` (folded from the supporting adapters). All derivable from data Engine 3 already exposes (notably `selected_observation` and `story_type`).

### 2.2 tone / category derivation

`tone`/`category` must come from **both** the public beat and the underlying internal observation (`selected_observation.type`, already in the payload at `bullpen.py:1767`), because the four public beats are all pressure-framed:

| Internal observation (`story_observation_engine`) | Public beat | Canonical `tone` | Canonical `category` |
|---|---|---|---|
| `rotation_pressure` | coverage_pressure | stress | stressed |
| `concentration_pressure` | sustainability_question | stress | stressed |
| `depth_pressure` | depth_constraint | stress | stressed |
| `core_transition` | route_change | watch | watch |
| `stable_core` | route_change | watch | watch |
| `optionality_strength` | sustainability_question | **rest** | **rested** |
| _(no team)_ | _league note_ | neutral | league |

> ⚠️ See **Blocker B1 (§9)**: `optionality_strength` is the only path to a "rest/depth-positive" story, and Engine 3 currently frames it as a *sustainability question* and ranks it last. Without a dedicated positive beat, the "Arms To Spare / More Options" rest stories that Home and Stories show today will be reframed or buried.

---

## 3. Target API Contract

### 3.1 The canonical Story object (one shape, used per-team and in the feed)

```jsonc
{
  "story_id": "SF:2026-06-22",            // stable per team per day (league: "league:<slug>:<date>")
  "capability": "baseballos_story_v2",
  "as_of_date": "2026-06-22",

  "team": { "team_id": 137, "team_name": "Giants", "team_abbreviation": "SF" }, // null = league story

  // Publication / suppression
  "story_available": true,
  "contract_state": "available",          // "available" | "neutral"
  "suppression_reason": null,             // when neutral: no_story_observations | no_valid_story_frame | below_quality_threshold | duplicate_signature

  // Classification
  "story_type": "coverage_pressure",      // route_change | coverage_pressure | depth_constraint | sustainability_question | (proposed) availability_depth
  "tone": "stress",                       // stress | watch | rest | neutral
  "category": "stressed",                 // stressed | watch | rested | league
  "kicker": "Coverage Pressure",

  // Narrative
  "headline": "The Giants are asking their setup arms to carry the late innings",
  "narrative": "…full prose, paragraphs joined by \\n\\n…",
  "paragraphs": {
    "observation": "…", "baseline": "…", "cause": "…", "constraint": "…"
  },
  "beats": [
    { "key": "observation", "label": "What changed", "text": "…" },
    { "key": "baseline",    "label": "Comparison point", "text": "…" },
    { "key": "cause",       "label": "Why it happened", "text": "…" },
    { "key": "constraint",  "label": "What it creates", "text": "…" }
  ],

  // Evidence / context
  "evidence": { "named_arms": ["…"], "measurable_facts": ["…"] },
  "supporting_context": { "continuity_note": "…", "context_note": "…" },
  "disclosure_note": null,
  "limitations": [],

  // Quality status
  "quality": { "status": "pass", "score": 86, "failed_rules": [] },   // status: pass | hold | review

  // Continuity (feed-level decoration)
  "continuity": { "status": "ongoing", "consecutive_days": 3 },        // new | ongoing | returning | null

  // Share-card readiness
  "share": {
    "ready": true,
    "title": "Giants bullpen: coverage pressure",
    "description": "…≤200 chars…",
    "url": "/team/SF"
  },

  // Provenance / governance
  "freshness": { "data_through": "2026-06-21" },
  "trust_metadata": { "external_generation_used": false },

  // Navigation (presentation hint; client may override)
  "href": "/bullpen?view=board&team=SF",
  "cta": "Open the team board"
}
```

### 3.2 Endpoints

| Capability | Endpoint | Notes |
|---|---|---|
| **Per-team story** | `GET /api/bullpen/teams/<id>/story` | Existing route, **extended** to return the canonical object (adds `story_id`, `tone`, `category`, `narrative`, `beats`, `quality`, `continuity`, `share`; keeps all current keys during transition). |
| **Ranked league-wide feed** | `payload['stories']` inside `GET /api/bullpen/dashboard` (Phase 1), optionally promoted to standalone `GET /api/bullpen/stories` later | `{ capability, as_of_date, items: [Story…], fallback, freshness, suppressed: { count, reasons } }`. Items returned **in ranked order**; see governance note. |
| **Legacy (transitional)** | `payload['four_beat_stories']` | Kept alongside `payload['stories']` until Stories + Home migrate, then removed. |

**Contract guarantees the canonical service must satisfy (maps to the task's required capabilities):**

1. **Ranked league-wide feed** — `items` ordered by internal strength; one story per team; deduped; archetype-diversified.
2. **Per-team story** — same object shape, single team.
3. **Story evidence/context** — `evidence` + `supporting_context`.
4. **Story quality status** — `quality.status` / `quality.score` / `quality.failed_rules`.
5. **Suppression reason** — `contract_state: "neutral"` + `suppression_reason` when nothing should publish (and per-feed `suppressed.reasons`).
6. **Stable story IDs** — `story_id` deterministic, stable within a day even if the beat changes (one canonical story per team per day).
7. **Share-card readiness** — `share.ready` + `share.{title,description,url}`.

> **Governance note (see Blocker B3):** the feed conveys priority through *order only*. Do **not** expose numeric `rank`/`significance` as public fields — the product's descriptive-only contract bans ranking language (`api.js` governance gates; `storyCardHasBannedLanguage` blocks "ranked"/"ranking", `storyCardView.js:113-137`). Keep ranking scores in an internal/diagnostic block gated behind the existing snapshot/debug token, not in the public payload.

---

## 4. Migration Plan — Files & Logic

### 4.1 Files that STAY (the canonical core)

| File | Role after consolidation |
|---|---|
| `services/story_intelligence_service_v1.py` | **Canonical engine.** Extended with a feed mode + canonical field mapping. |
| `services/story_observation_engine.py` | Canonical observation model (single taxonomy). |
| `services/story_construction_engine.py` | Canonical story frames. |
| `services/story_writer_v1.py` | Canonical prose writer. |
| `services/story_four_beat_interpreter_v1.py` | Canonical beat vocabulary (extended with a positive beat — Blocker B1). |
| `services/story_voice_library_v1.py` | The one shared voice/template library. |
| `services/story_quality.py` | The **single** quality gate/scorer; absorbs `story_evidence`'s unique checks. |
| `services/bullpen_board.py` | Board data (not a story engine; unchanged). |
| `services/narrative_memory.py` | Workload-continuity **compute** layer feeding the one continuity path. |
| **NEW** `services/story_feed.py` (or a feed mode inside the service) | Canonical feed builder: iterate teams → canonical stories → ported ranking/dedupe/diversification → attach continuity. |
| `StoryCard.jsx` / `storyCardView.js`, `storiesFeedView.js`, `BullpenStories.jsx` | **Dumb renderers** of canonical output (kept, simplified). |

### 4.2 Files DEPRECATED → removed from runtime (Pipeline A prose/observation stack)

Superseded by Engine 3 once parity is proven:

- `services/four_beat_stories.py` — **extract** its feed ranking/dedupe/diversification into `story_feed.py`, then deprecate.
- `services/story_observation_discovery.py`
- `services/story_observation_voice.py`
- `services/story_evidence.py` — fold unique checks into `story_quality.py`.
- `services/team_story_facts.py`
- `services/team_story_narrative.py`
- `services/story_context_integration.py` — fold output into canonical `supporting_context`.
- `services/story_identity_integration.py` — fold output into canonical `supporting_context`.
- Dashboard payload key `four_beat_stories` — removed after Stories + Home migrate to `stories`.

### 4.3 Files REMOVED from runtime (browser story generation)

- `frontend/src/components/home/storyEngineV1.js` — **delete** (a generator, not a formatter).
- `frontend/src/components/home/homeIntelligenceView.js` — **strip** all narrative generation (`getBullpenStories`, hero/candidate builders, inline copy banks, `STORY_NARRATIVE_TEMPLATES` usage). Keep only masthead/formatting helpers (`getMastheadView`, `homeTone`) that the Stories header also imports.
- `frontend/src/components/bullpen/board/teamBullpenStoryView.js` — **delete**.
- `frontend/src/components/bullpen/board/TeamBullpenStoryPanel.jsx` — **delete**; `StoryCard` (canonical `/story`) becomes the board's single story. Update `BullpenBoardView.jsx:451` to drop the panel mount.

### 4.4 Files CONSOLIDATED (continuity / context → one each)

- `services/story_continuity.py` — retain as the **feed-level** New/Ongoing/Returning decorator, repointed at canonical stories; merge with the continuity half of `narrative_memory_story.py` so there is one continuity authority.
- `services/narrative_memory_story.py` — continuity notes fold into canonical `supporting_context`; its near-twin scaffolding with `bullpen_context_story` collapses to one note adapter.
- `services/bullpen_context_story.py` — context notes fold into canonical `supporting_context`.

### 4.5 Files to REMOVE or deliberately REVIVE (dormant)

- `api/observations.py`, `observations/api_assembly.py`, `frontend/.../BullpenIntelligencePanel.jsx` (V5 Observations) — **remove** (fails closed, unmounted) unless intentionally folded into the canonical engine.

### 4.6 OFFLINE / QA (retain, repoint to canonical)

- `services/team_story_previews.py` — repoint share/OG generation to consume canonical `story.share`.
- `services/four_beat_real_quality_audit.py`, `services/story_audit_preview_v1.py` — repoint at canonical output or archive.

### 4.7 ADJACENT — explicitly OUT OF SCOPE (track separately)

- `what_changed_since_yesterday_public.py` + inline workload payload, and `team_changes.py` — the "What Changed" surfaces overlap conceptually but are a **distinct feature**, not the story engine. Note the duplication; do **not** bundle into this consolidation. File a separate follow-up.

### 4.8 How the three pages consume the SAME output

| Page | Before | After |
|---|---|---|
| **Home `/`** | `homeIntelligenceView.getBullpenStories` (built from landscape counts) → `storyEngineV1` rank/select/suppress | Render **top-3 of `payload.stories.items`** (by canonical order) for "Three Things To Watch"; flagship/hero = `items[0]` + `continuity`. No client generation. |
| **Stories `/stories`** | `storiesFeedView.getFourBeatStoryFeed` reads `dashboard.four_beat_stories` | Read **`payload.stories.items`** (full feed); filters ride canonical `category`. |
| **Team Board `/bullpen?view=board`** | `StoryCard` (Engine 3) **and** `TeamBullpenStoryPanel` (Engine 4, client) | `StoryCard` renders canonical `GET /teams/<id>/story` only; the second panel is removed. One story per team. |

Net: one `Story` shape, one source of truth. The Team Board shows that team's canonical story; Stories shows the whole canonical feed; Home shows the top of it.

### 4.9 UI-safety strategy (no broken pages mid-migration)

1. **Additive first.** Add canonical fields/keys alongside legacy ones; never remove a field a live consumer still reads until that consumer has migrated.
2. **Dual-publish.** The dashboard payload emits `stories` (canonical) **and** `four_beat_stories` (legacy) simultaneously during transition.
3. **Per-page feature flags** (config/env): `STORY_CANONICAL_HOME`, `STORY_CANONICAL_STORIES`, `STORY_CANONICAL_BOARD`. Default off; flip one per phase; fall back to the legacy path when the flag is off or `payload.stories` is absent.
4. **Alias-friendly fields.** Canonical output uses the alias keys the existing normalizers already accept (`team_id`/`teamId`, `narrative`/`story_body`, `disclosure_note`/`disclosureNote`), so renderers need minimal change.
5. **Golden-snapshot regression.** Before each page migration, capture the current rendered story text (Home top-3, Stories feed, Board card) as fixtures; diff after the switch and review intentional changes.
6. **Snapshot/caching coordination.** `dashboard_snapshot.py` precomputes and serves the dashboard payload (`build_bullpen_dashboard_payload` is called by `/dashboard`, the snapshot builder, **and** `/story-quality/diagnostic`). Bump the snapshot schema version to include `stories`, rebuild snapshots as part of the phase, and serve canonical only when present.

---

## 5. Migration Phases

Each phase is independently shippable, flag-guarded, and reversible.

### Phase 0 — Prep & contract freeze *(no behavior change)*
- Freeze the §3 canonical contract; add a JSON schema fixture.
- Add the three feature flags (all default off).
- Capture golden snapshots of current Home/Stories/Board story output.
- Resolve **Blocker B1** (positive beat) and **B3** (governance/ranking exposure) on paper.
- **Exit:** contract + flags merged; snapshots recorded; blockers decided.

### Phase 1 — Canonical backend adapter *(no UI change)*
- Build `story_feed.py` (or feed mode in the service): per-team canonical mapping + ported cross-team ranking/dedupe/diversification extracted from `four_beat_stories.py`.
- Extend `_story_api_payload` and `build_team_story` to emit the canonical fields (additive).
- Add `payload['stories']` to the dashboard payload **next to** `four_beat_stories`; bump snapshot schema.
- **Exit:** `payload.stories` and the extended `/story` exist and validate; all legacy fields unchanged; UI untouched.

### Phase 2 — Home → canonical
- Home renders top-3 of `payload.stories` behind `STORY_CANONICAL_HOME`; flagship from `items[0]` + `continuity`.
- Keep the legacy client path as flag-off fallback.
- **Exit:** flag-on Home matches golden snapshot within reviewed deltas; flag-off unchanged; no `storyEngineV1` call when flag on.

### Phase 3 — Stories → canonical
- `storiesFeedView` reads `payload.stories` behind `STORY_CANONICAL_STORIES`; filters use canonical `category`.
- **Exit:** filter counts and feed render match snapshot within reviewed deltas; flag-off unchanged.

### Phase 4 — Team Board → canonical
- `StoryCard` consumes the extended canonical `/story`; **remove `TeamBullpenStoryPanel`** behind `STORY_CANONICAL_BOARD`.
- **Exit:** board shows exactly one story; counts/board still render; deep-link selection works; flag-off unchanged.

### Phase 5 — Remove browser story generation from runtime
- Delete runtime imports/usages of `storyEngineV1.js`, the narrative bank in `homeIntelligenceView.js`, `teamBullpenStoryView.js`, `TeamBullpenStoryPanel.jsx`.
- Remove the per-page legacy fallbacks (flags become permanent-on, then retired).
- **Exit:** import-graph test proves no runtime module imports the client generators; bundle shrinks; all pages green.

### Phase 6 — Delete/archive dead backend code *(after tests pass)*
- Remove the deprecated Pipeline A stack (§4.2), the `four_beat_stories` dashboard key, the consolidated continuity/context twins (§4.4), and the dormant V5 Observations system (§4.5).
- Repoint or archive offline QA (§4.6).
- **Exit:** full suite green; dead-import scan clean; endpoint contract tests pass; deleted-module tests removed.

---

## 6. Tests Per Phase

**Phase 0:** canonical JSON-schema validator; golden-snapshot fixtures for Home/Stories/Board; flag-plumbing unit tests (default off).

**Phase 1:**
- Contract tests: every canonical field present and typed; `story_id` deterministic & stable across repeated builds for the same date.
- Parity tests: canonical per-team `headline`/paragraphs equal current `/story` output for a fixture set.
- Feed tests: ranking is deterministic; one story per team; duplicate phrases suppressed; `suppressed.reasons` populated; neutral teams carry `suppression_reason`.
- Regression: legacy `four_beat_stories` payload byte-identical (snapshot) — proves additivity.
- Snapshot schema: v-bump round-trips; old snapshots still served.

**Phase 2 (Home):** flag-on renders 3 canonical cards; flag-off renders legacy; flagship = `items[0]`; `storyEngineV1` not invoked under flag-on (spy/import test); golden diff reviewed.

**Phase 3 (Stories):** flag-on feed parity (per-`category` counts, item count, empty/fallback states); user filters operate on canonical `category`; flag-off unchanged.

**Phase 4 (Board):** exactly one story rendered; `TeamBullpenStoryPanel` absent under flag-on; board counts/game-context intact; deep-link `?team=SF` resolves; neutral team shows the StoryCard neutral state with `suppression_reason`.

**Phase 5:** import-graph/dead-import test (no runtime import of `storyEngineV1`/`teamBullpenStoryView`); bundle-size assertion; full page smoke tests; governance lint (no banned ranking terms in output).

**Phase 6:** full backend+frontend suite green; removed modules have no references (grep-guard test); `/teams/<id>/story`, `payload.stories`, share-card, and quality-status contract tests still pass; offline QA repointed and runs.

**Cross-cutting (every phase):** governance contract tests (no `ranked`/`ranking`/recommendation language or fields in public responses); freshness/trust metadata preserved end to end.

---

## 7. Highest-Risk Files

| File | Lines | Why it's high-risk |
|---|---|---|
| `backend/api/bullpen.py` | 2,848 | The merge hub. `build_bullpen_dashboard_payload` feeds **all three pages**; the `/story` serializer feeds the board. Highest blast radius — every phase touches it. |
| `backend/services/four_beat_stories.py` | 2,557 | Extracting feed ranking/diversification without regressing the Stories feed; it currently powers `payload.four_beat_stories`. |
| `frontend/.../home/homeIntelligenceView.js` | 1,273 | Stripping generation while preserving the masthead/format helpers that `Stories.jsx` also imports — easy to over-delete. |
| `frontend/.../home/storyEngineV1.js` | 1,430 | Removing the most-viewed page's narrative source; must be fully replaced before deletion. |
| `backend/services/story_intelligence_service_v1.py` | 836 | Extending to feed mode + adding fields **without** breaking the existing `/story` contract or per-team selection. |
| `backend/services/story_quality.py` | 1,058 | Becoming the single gate (absorbing `story_evidence`); threshold/behavior changes can suppress or release stories across all surfaces. |
| `backend/services/dashboard_snapshot.py` | — | Precomputed snapshot schema must add `stories` and be rebuilt; a stale snapshot serves the wrong shape to every page. |
| `frontend/.../board/teamBullpenStoryView.js` + `TeamBullpenStoryPanel.jsx` | 878 + 99 | Removing the second board story; must confirm `StoryCard` covers every state the panel handled (incl. `data_limited`). |

---

## 8. First Implementation Branch

**Start with Phase 1 only**, on a branch named for the work, e.g. **`canonical-story-adapter`**.

- Scope: `story_feed.py` (new) + canonical field mapping in `story_intelligence_service_v1.py`/`_story_api_payload` + additive `payload['stories']` + snapshot schema bump + the Phase 1 test suite.
- **No UI changes, no deletions** — purely additive backend, fully behind the absence of UI wiring.
- Smallest reversible step that makes the canonical contract real and testable in isolation, and it unblocks Phases 2–4 to proceed independently.
- Do Phase 0 (contract freeze + flags + golden snapshots + blocker decisions) as the opening commits on this same branch, or as a short preceding branch if blocker sign-off needs its own review.

---

## 9. Blockers & Open Decisions

| ID | Blocker / decision | Impact | Recommendation |
|---|---|---|---|
| **B1** | **No positive "rest/depth" public beat.** Engine 3 maps `optionality_strength → sustainability_question` and ranks it last (`story_four_beat_interpreter_v1.py:55-62`, `story_observation_engine.py:49-55`). Home & Stories show upbeat "More Options / Arms To Spare" rest stories today. | **High** — migrating Home/Stories as-is reframes or buries rest stories (product regression). | Add a fifth public beat (e.g. `availability_depth`) for `optionality_strength`/`stable_core`, **or** derive `tone:rest`/`category:rested` from the internal observation and give the writer a positive copy path. Decide in Phase 0; blocks Phases 2–3. |
| **B2** | **Engine 3 is single-team; feed mode is new.** Cross-team ranking, dedupe, and diversification live only in `four_beat_stories.py`. | **Med** — the canonical feed is net-new code. | Reuse Engine 3's existing per-story selection strength (`_selection_strength_for_*`) as the ranking signal; port only the *cross-team* concerns (order, one-per-team, dedupe, diversify). Spike in Phase 1. |
| **B3** | **Governance vs. ranking exposure.** The product's descriptive-only contract bans ranking language/fields (`storyCardView.js:113-137`, `api.js` governance gates), yet the task asks for a "ranked feed." | **Med** — exposing `rank`/`significance` could trip governance tests. | Convey priority by **order only**; keep numeric rank/score in an internal/diagnostic block gated by the snapshot/debug token, never in the public payload. Confirm with governance owner in Phase 0. |
| **B4** | **Snapshot caching.** Dashboard payload is precomputed/cached; schema change needs a coordinated rebuild and version handling. | **Med** | Version the snapshot, dual-read (serve canonical when present, recompute otherwise), rebuild as part of Phase 1 rollout. |
| **B5** | **Stable story IDs vs. intraday beat changes.** If `story_type` shifts as data updates, an ID keyed on the beat churns, breaking share links and continuity. | **Low/Med** | Key `story_id` on `team + as_of_date` (one canonical story per team per day); carry `story_type` as an attribute, not part of the ID. |
| **B6** | **Quality-gate unification behavior.** Folding `story_evidence` into `story_quality` and using one threshold may change which stories publish across all surfaces. | **Med** | Run both gates in shadow during Phase 1; diff suppression sets; tune the single threshold to match or intentionally improve current behavior before flipping any UI flag. |
| **B7** | **"What Changed" overlap.** `what_changed_*_public` vs `team_changes` duplicate a concept but are out of this scope. | **Low** | Track as a separate follow-up; do not expand this plan. |

---

*Prepared June 2026 · design plan only · no application code modified · no implementation performed.*
