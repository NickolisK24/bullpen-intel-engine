# Backend Trust-Lane Story — Phase 4B.2 (June 2026)

**Companion docs:** `team_board_canonical_migration_audit.md` (Phase 4A), `team_board_storycard_parity_phase_4b_1.md` (Phase 4B.1), `positive_depth_story_beat_phase_1_5.md`
**Scope:** Add a canonical trust-lane story path to Story Intelligence V1, end to end. **No Team Board migration. `TeamBullpenStoryPanel` untouched. No bridge-instability detector. No new raw data.** Home and Stories only *receive* the new story type through their existing adapters.

---

## What trust-lane means

A bullpen can have **enough bodies available** while the **trusted late-game lane is narrow**: most of the "available" arms are pitching through recent workload, so the dependable, clean late-inning options are few. Raw arm count looks acceptable; the trusted path does not.

The Phase 4A audit found this is one of the two detector families that only the **client** `TeamBullpenStoryPanel` produced (archetypes `thinning_trust_lane`, `trust_dependency`, `thin_margin`, `pressure_building`), and that the canonical backend engine could not detect — a blocker to de-duplicating the Team Board. This phase adds the backend read so the canonical engine can publish it.

It is a distinct read from the existing beats:
- not **depth_constraint** (that is *inactive/injured* arms from `injury_context`),
- not **availability_depth** (the positive "more rested options" read), and
- not **route_change**.

---

## Evidence required (detector)

Read from the **same** `bullpen_optionality_context` (Layer 3) that powers `optionality_strength`, but keyed on the **clean** (no-workload-flag) subset rather than the blended practical-path count. The practical-path count *blends* `clean + 0.5 × secondary`, which can mask a thin trusted lane; trust-lane keys on `clean` directly.

`trust_lane_pressure` fires only when **all** hold:

| Gate | Threshold | Meaning |
|---|---|---|
| `context_available is True` | required | a real optionality read exists |
| `available_arms_count` | `>= 4` | the raw available board looks acceptable |
| `len(clean_workload_options)` | `<= 2` | the trusted/clean late lane is thin |
| `len(secondary_options)` | `>= 3` | several available/monitor arms carry workload flags (the gap is real, not synthetic) |

**Severity** is `high` when `clean <= 1` **and** flagged `>= 5` (a single trusted arm behind a full-looking board); otherwise `medium`.

The `context_available` gate is deliberate: it makes the detector **non-disruptive**. Every existing unit fixture builds a partial optionality dict *without* `context_available`, so the detector never fires on them — only the real Layer-3 builder (which always sets `context_available: True`) and the new trust-lane fixtures trigger it. No existing test changed behavior; the only test edits are additive enumerations (the seven-type observation→beat map) plus new tests.

No fabricated good or bad news: with weak evidence (few flagged arms, a genuinely deep clean board, or no optionality read) the detector returns nothing and the story stays neutral or positive.

---

## Public beat, copy, and contract

- **Observation type:** `trust_lane_pressure` (parallels `depth_pressure` / `rotation_pressure`).
- **Public beat / `story_type`:** `trust_lane`, label **"Trust Lane"**, question *"How many rested, trusted arms does the late-game plan actually lean on?"*
- **Voice (`story_voice_library_v1`):** 10 approved measured openings, e.g. *"The bullpen has arms available, but the trusted late-game lane is thinner than the roster count suggests."* No hype, predictions, betting, fantasy, internal scores, or overclaiming (validated by the writer's banned/robotic gates and the voice deny-lists).
- **Writer (`story_writer_v1`):** four evidence-backed paragraphs (board vs clean count → trusted-lane comparison → who carries the dependable work → forward "if the game tightens…" constraint), degrading cleanly when there are zero clean arms.

---

## Ranking behavior

Selection is strength-first (`story_intelligence_service_v1`). Trust-lane strength rewards a thinner clean lane, a wider flagged gap, and corroborating concentration:

```
clean == 0 → +4, clean == 1 → +3, clean == 2 → +2
secondary (flagged) >= 5 → +2, >= 3 → +1
top-three workload share >= 85% → +2, >= 75% → +1
concentration band 'narrow' → +1
```

Two guardrails place it correctly:
1. **Below acute pressure:** the public-beat tiebreak is `coverage(0) < sustainability(1) < route(2) < depth(3) < trust_lane(4) < availability_depth(5)`. On equal strength, an acute coverage/availability-pressure story still wins; a genuinely **stronger** pressure story wins outright on strength. Weak trust-lane never beats stronger pressure.
2. **Above generic positive depth:** when a `flexible`/`deep` board co-fires the positive `optionality_strength` read, a **strong** trust-lane read outranks it (the thin trusted lane is the more important truth), while the positive read still competes as a ranked candidate. Trust-lane must clear a strength > 0 bar to publish.

Worked examples (tested): `available 6 / clean 1 / flagged 5` → trust-lane publishes and outranks the co-firing positive read; add strong rotation pressure → coverage_pressure wins and trust-lane ranks below it; `available 8 / clean 4` → healthy, positive `availability_depth` publishes and trust-lane does not fire.

---

## Canonical adapter & surfaces

- **`story_feed.py`:** `trust_lane_pressure` → **category `trust_lane`**, **tone `watch`**. Category is new and distinct (so the feed can surface "bodies available, trusted lane thin" on its own); tone uses the **supported `watch` token** rather than a new `monitor` string so every surface renders it cleanly instead of falling back to neutral. (`watch` is a monitor-grade signal and is already a valid tone across StoryCard, Home, and Stories.)
- **StoryCard (`storyCardView.js`):** label **"Trust Lane"**, helper *"How few rested, trusted arms the late-game plan really leans on."* StoryCard has no per-type severity styling, so it renders in the same neutral shell — never framed as an error.
- **Home & Stories adapters:** each `KICKER_BY_STORY_TYPE` gains `trust_lane: 'Trust Lane'`. They otherwise **tolerate** the type through existing logic: tone `watch` is already valid; the new `category: 'trust_lane'` falls back to the safe `watch` filter lane (it is intentionally *not* added to the page filter set, which would risk an unrendered lane). No Home/Stories behavior changes beyond receiving the new type.
- **`api/bullpen.py`:** unchanged. The `/story` serializer already passes `story_type` through (so the label reaches the Team Board StoryCard), and the league signal is landscape-derived, so the new category needs no wiring there.

---

## Why this unblocks Team Board migration

Phase 4A identified **two** backend detectors missing before the duplicate client `TeamBullpenStoryPanel` could be removed: **trust-lane** and **bridge-instability**. Trust-lane backed the larger gap (four client archetypes). With it now canonical — detected, ranked, written, and mapped end to end — the only remaining backend blocker is the bridge-instability detector.

This phase does **not** migrate the Team Board or remove the client panel; it adds the missing canonical capability so a later phase can.

---

## Remaining Team Board blocker

- **Bridge-instability detector** — no handoff/bridge observation in the canonical engine (the existing `role_stability` signals describe the late-inning *core*, not the *bridge*; client archetype `bridge_dependency`). It needs the same five layers built here (observation → construction frame → interpreter beat → service strength/selection → writer/voice → `story_feed` mapping).

Until it exists, the duplicate client panel cannot be removed without losing bridge-instability stories.

---

## Tests

- **`test_story_observation_engine.py`** — detector fires on a thin trusted lane; publishes even when available arms look acceptable; does **not** fire when trusted depth is healthy, when the flagged population is too small, or when the context is unavailable.
- **`test_story_writer_v1.py`** — trust-lane writer produces clean, valid, quality copy; handles zero clean arms.
- **`test_story_intelligence_service_v1.py`** — publishes as `trust_lane`; outranks positive depth when strong; stronger acute pressure still outranks it; healthy depth stays positive; no fabricated story when evidence is missing; the seven-type observation→beat map.
- **`test_story_feed.py`** — `trust_lane_pressure`/`trust_lane` → tone `watch`, category `trust_lane`.
- **Frontend** — `storyCard.test.mjs` (six-beat list + "Trust Lane" label, internal type not leaked), `homeCanonicalStories.test.mjs` and `storiesCanonicalFeed.test.mjs` (render the new type with the "Trust Lane" kicker in a safe lane without breaking), `teamBullpenStoryPanel.test.mjs` (unchanged — panel still intact).

Results: backend **1,397 passed** (one pre-existing, date/DB-backend-sensitive failure in `test_availability_reference_date.py`, unrelated and confirmed on the base commit). Frontend **518 passed, 0 failed**.

---

## Next recommended phase

- **Phase 4B.3 — backend bridge-instability detector** (same five layers, with tests).
- **Phase 4B.4** — behind `VITE_USE_CANONICAL_TEAM_BOARD`, render the single canonical story and stop mounting `TeamBullpenStoryPanel` (legacy kept on flag-off).
- **Phase 4B.5** — validate in production, then remove `TeamBullpenStoryPanel` + `teamBullpenStoryView.js`.
