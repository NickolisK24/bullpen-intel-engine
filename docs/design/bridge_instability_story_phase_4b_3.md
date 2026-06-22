# Backend Bridge-Instability Story — Phase 4B.3 (June 2026)

**Companion docs:** `team_board_canonical_migration_audit.md` (Phase 4A), `team_board_storycard_parity_phase_4b_1.md` (4B.1), `trust_lane_story_phase_4b_2.md` (4B.2)
**Scope:** Add a canonical bridge-instability story path to Story Intelligence V1, end to end. **No Team Board migration. `TeamBullpenStoryPanel` untouched. No new raw data.** Home and Stories only *receive* the new story type through their existing adapters.

---

## What bridge-instability means

The **late-game core can be healthy** and the bullpen can have **enough total arms**, yet the **path between the starter and the trusted late-game route — the middle-innings handoff — is fragile**. The starter exits early, the bullpen is asked to cover a real bridge, and the arms that bridge into the settled late group are volatile (monitor/limited tier) and thin on clean options.

This is the second of the two detector families the Phase 4A audit found only in the **client** `TeamBullpenStoryPanel` (archetype `bridge_dependency`), and the last backend blocker to de-duplicating the Team Board. With Trust Lane shipped in 4B.2, this phase closes the remaining gap.

It is deliberately distinct from the existing beats:
- **coverage_pressure** — the bullpen carrying extra innings from a *short-start trend* (rotation pressure). Bridge does not require a negative starter trend; it requires a *settled late core* plus a volatile middle.
- **trust_lane** — an acceptable available board but few clean *late-game* options. Bridge is about the *middle path into* a healthy late group.
- **route_change** — the late-game core itself changed. Bridge **requires** a settled (`stable`) core.
- **depth_constraint** — *inactive/injured* arms from `injury_context`. Bridge reads active availability + handoff demand.

---

## Evidence required (detector)

Reuses three existing context layers — `rotation_context` (handoff demand), `role_stability_context` (a settled late core), and `bullpen_optionality_context` (a volatile, thin middle). **No new raw data.**

`bridge_instability` fires only when **all** hold:

| Gate | Threshold | Meaning |
|---|---|---|
| `role_stability_context.stability_band == 'stable'` | required | the late-game core is settled (else it's a route/core story) |
| `bullpen_optionality_context.context_available is True` | required | a real optionality read exists |
| `early_bullpen_entry_rate >= 35%` **or** `bullpen_coverage_ip_7d >= 3.8` | required | a real starter→bullpen handoff demand (the bridge is being used) |
| `monitor_arms_count + limited_arms_count >= 2` | required | the middle path leans on volatile arms |
| `len(clean_workload_options) <= 2` | required | the clean bridge options are thin |

**Severity** is `high` when `early_bullpen_entry_rate >= 50%` **and** the volatile-middle count `>= 4` (a long, unsteady bridge); otherwise `medium`.

The `stability_band == 'stable'` and `context_available is True` gates make the detector **non-disruptive**: existing unit fixtures default to `mostly_stable` and omit `context_available`, so the detector never fires on them. Only the real Layer-3/stability builders (settled core + real read) and the new bridge fixtures trigger it. The only test edits are additive enumerations (the eight-type observation→beat map) plus new tests.

No speculation: weak evidence (no handoff demand, an unsettled core, a healthy/clean middle, or no optionality read) returns nothing and the story stays neutral or positive. The service also gates publication on strength > 0.

---

## Public beat, copy, and contract

- **Observation type:** `bridge_instability`.
- **Public beat / `story_type`:** `bridge`, label **"Bridge Instability"**, question *"How fragile is the path from the starter to the trusted late-game arms?"*
- **Voice (`story_voice_library_v1`):** 10 approved measured openings, e.g. *"The bullpen's late-game options remain intact, but the route into those innings is thinner than it appears."* No predictions, betting, fantasy, internal scores, or dramatic wording (enforced by the writer's banned/robotic gates and the voice deny-lists).
- **Writer (`story_writer_v1`):** four evidence-backed paragraphs — a settled core reached through volatile middle arms → the thin-handoff comparison → early starter exits + the monitor-tier bridge → forward "if the starters keep exiting early…" constraint — degrading cleanly when core names or monitor counts are absent.

---

## Ranking behavior

Selection is strength-first (`story_intelligence_service_v1`). Bridge strength rewards a bigger handoff demand, a more volatile middle, and fewer clean bridge arms:

```
early_bullpen_entry_rate >= 50% → +2, >= 35% → +1
bullpen_coverage_ip_7d  >= 4.5  → +2, >= 3.8 → +1
volatile middle (monitor+limited) >= 4 → +2, >= 2 → +1
clean bridge options == 0 → +2, <= 1 → +1
```

The public-beat tiebreak now reads `coverage(0) < sustainability(1) < route(2) < depth(3) < bridge(4) < trust_lane(5) < availability_depth(6)`, giving the required order:

```
coverage pressure  ↓  bridge instability  ↓  trust lane  ↓  availability depth
```

- **Does not outrank acute coverage pressure:** a genuinely strong coverage story wins outright on strength; at equal strength coverage's tiebreak (0) beats bridge (4). (Tested: acute rotation pressure outranks a co-firing bridge read.)
- **Outranks trust-lane when stronger:** when both fire, the stronger bridge read wins (bridge tiebreak 4 < trust_lane 5 at equal strength), while trust-lane still competes. (Tested.)
- **Outranks the positive read:** a `stable` core co-fires the positive `stable_core → availability_depth` read; bridge outranks it because the fragile handoff is the more important truth, while the positive read still ranks as a candidate. (Tested.)

---

## Canonical adapter & surfaces

- **`story_feed.py`:** `bridge_instability` → **category `bridge`**, **tone `watch`** (a monitor-grade, fully supported tone token, mirroring the Trust-Lane choice so the story renders cleanly on every surface rather than falling back to neutral).
- **StoryCard (`storyCardView.js`):** label **"Bridge Instability"**, helper *"How fragile the path is from the starter to the trusted late-game arms."* Neutral shell, never framed as an error.
- **Home & Stories adapters:** each `KICKER_BY_STORY_TYPE` gains `bridge: 'Fragile Bridge'`. They otherwise tolerate the type through existing logic: tone `watch` is already valid; the new `category: 'bridge'` falls back to the safe `watch` filter lane (intentionally not added to the page filter set). No Home/Stories behavior changes beyond receiving the new type.
- **`api/bullpen.py`:** unchanged (the `/story` serializer already passes `story_type` through to the Team Board StoryCard; the league signal is landscape-derived).

---

## Relationship to Team Board migration & de-duplication benefit

Phase 4A identified two missing backend detectors before the duplicate client `TeamBullpenStoryPanel` could be removed:

1. **Trust Lane** — shipped in Phase 4B.2.
2. **Bridge Instability** — shipped here.

With both now canonical — detected, ranked, written, and mapped end to end — the canonical engine covers the story families that previously existed **only** in the client panel. **No remaining backend detector blockers** stand in the way of Team Board de-duplication.

Expected benefit: the Team Board can now move to a single canonical story (the StoryCard, already on the canonical `/story` endpoint) and **stop mounting `TeamBullpenStoryPanel`**, eliminating the two-competing-stories-on-one-screen problem the audit flagged — without losing trust-lane or bridge-instability coverage. That migration is the next phase and is **not** performed here; this phase only adds the missing capability.

---

## Tests

- **`test_story_observation_engine.py`** — fires on a fragile handoff; does not fire without a settled core, when the bridge is healthy (plenty of clean middle), without handoff demand, or without an available optionality context.
- **`test_story_writer_v1.py`** — bridge writer produces clean, valid, quality copy.
- **`test_story_intelligence_service_v1.py`** — publishes as `bridge`; outranks trust-lane when stronger; acute coverage still outranks bridge; weak evidence does not publish; a healthy bridge stays positive; the eight-type observation→beat map.
- **`test_story_feed.py`** — `bridge_instability`/`bridge` → tone `watch`, category `bridge`.
- **Frontend** — `storyCard.test.mjs` (seven-beat list + "Bridge Instability" label, internal type not leaked), `homeCanonicalStories.test.mjs` and `storiesCanonicalFeed.test.mjs` (render the new type with the "Fragile Bridge" kicker in a safe lane without breaking), `teamBullpenStoryPanel.test.mjs` (unchanged — panel still intact).

Results: backend **1,410 passed** (one pre-existing, date/DB-backend-sensitive failure in `test_availability_reference_date.py`, unrelated and confirmed on the base commit). Frontend **521 passed, 0 failed**.

---

## Next recommended phase

- **Phase 4B.4 — Team Board canonical migration:** behind `VITE_USE_CANONICAL_TEAM_BOARD`, render the single canonical story and stop mounting `TeamBullpenStoryPanel` (legacy kept on flag-off).
- **Phase 4B.5** — validate in production, then remove `TeamBullpenStoryPanel` + `teamBullpenStoryView.js`.
