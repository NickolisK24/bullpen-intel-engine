# BaseballOS Story Coverage Audit — June 2026

**Type:** Read-only coverage audit (pre-migration gate)
**Companion docs:** `story_architecture_audit_june_2026.md`, `story_consolidation_plan_june_2026.md`, `story_adapter_phase_1_notes.md`
**Question:** If Home, Stories, and Team Board migrated to the canonical `payload["stories"]` engine **today**, which story types would be **preserved, weakened, reframed, or lost**?

---

## 1. Verdict

**Home cannot safely migrate yet, and neither can Stories or Team Board.** Story Intelligence V1 (the canonical base) is excellent at *pressure* stories and route changes, but it **systematically converts good news into worry or suppresses it**, and it has **no detector** for several classes the current surfaces depend on.

Classified against the four generators:

- **Preserved** (≈ same story, apt frame): workload concentration, same-few-arms, fatigue/workload pressure, availability constraint, **route change** (SI V1's native strength), and no-story/suppression (canonical actually *improves* this with an explicit suppression contract).
- **Reframed / Lost** (signal detected but inverted or dropped): **positive rest/depth** ("More Options", "Arms To Spare", clean depth), **stable core**.
- **Lost** (no detector at all): **thin trust lane**, **bridge instability**, **what-changed/delta**, **day-over-day continuity** (new/ongoing/returning), **league-wide notes**.

The single biggest blocker is the **positive rest/depth class** — and crucially it is **not a detection gap**. SI V1 *detects* depth (`optionality_strength`) and stability (`stable_core`); the contract, ranking, and copy then throw the positive read away.

---

## 2. Coverage Matrix

**Legend:** ✅ Preserved · 🟡 Weakened · 🟠 Reframed (detected, wrong frame) · ❌ Lost/none · ➖ not produced by that system.
Canonical = Story Intelligence V1 as exposed through `story_feed.py` (Phase 1 adapter).

| Story class | Home engine | Four-Beat (Stories) | Story Intel V1 | Team Board panel | **Canonical adapter** | Migration risk | Notes |
|---|:--:|:--:|:--:|:--:|:--:|:--:|---|
| **Positive rest / depth** (umbrella) | ✅ `recovery_window`, `deep_pen_advantage` | ✅ `pressure_distribution` rule + `availability_deep`/`deep_intact` leads + `flexibility` obs + `flexible_bullpen` archetype | 🟠 detects `optionality_strength`, maps→`sustainability_question`/`depth_constraint` | ✅ `clean_options_layer`, `depth_advantage`, `rested_flexibility` | **🟠/❌** | tone=rest preserved by adapter, but **copy is pressure-framed and the candidate is usually suppressed** (strength 0 + selectability gate). |
| **"Arms to spare"** | ✅ `team_depth` | ✅ `availability_deep`, `deep_intact` | ❌ | ✅ `depth_advantage` | **❌** | No positive beat; optionality scored 0 → `NEUTRAL_NO_VALID_FRAME`. |
| **More available options** | ✅ `team_recovery` "More Options" | ✅ `flexibility` obs, `participation_broad` | 🟠 → sustainability_question | ✅ `clean_options_layer` | **🟠** | Positive read published as "can this keep working?" |
| **Clean depth** | ✅ `deep_pen_advantage` | ✅ `deep_intact`, `depth_width` identity | 🟠 → `depth_constraint` if any arm unavailable | ✅ `depth_advantage` | **🟠** | Reroute to `depth_constraint` (`interpreter:215-223`) inverts "deep" into "thin". |
| **Stable core** | 🟡 (no direct kind) | ✅ `stability_recovery`, `leverage_backbone` | 🟠 `stable_core`→`route_change` | ✅ `stable_bullpen` | **🟠/❌** | Headline literally asserts "The route has changed" for a *settled* core; strength 0. Adapter doesn't even flag it (tone=watch). |
| **Thin trust lane** | ✅ `trust_arm_dependency` | ✅ `trust_lane_absence`/`shallow`, `thin_trusted_group`, `trust_shape` obs | ❌ **no trust detector** | ✅ `thinning_trust_lane`, `trust_dependency` | **❌** | SI V1 reads no trust layer at all (`interpreter:5` disclaims it). |
| **Bridge instability** | 🟡 `bridge_dependency` (explicit only) | ✅ `stability_erosion`, `thin_cover` identity | ❌ role-stability yes, **no bridge concept** | ✅ `bridge_dependency` | **❌** | Handoff/bridge signal not modeled. |
| **Workload concentration** | ✅ `concentrated_workload`, `heavy_lifting` | ✅ `stress_transfer`, `concentration_shape`, `workload_concentration` | ✅ `concentration_pressure`→sustainability_question | ✅ `concentrated_workload`, `heavy_lifting` | **✅** | Frame shifts to "sustainability question" but tone=stress preserved. |
| **Route / usage change** | ✅ `usage_shift` | ✅ `rotation_spillover`, `change` obs | ✅✅ `core_transition`→`route_change` | ✅ `usage_shift` | **✅** | SI V1's strongest class. Home's `usage_shift` rests on a *different* signal (usage_demand/rotation_length trend) — see note. |
| **Availability constraint** | ✅ `thin_margin`, `depth_constraint`, `coverage_gap` | ✅ `hidden_capacity_loss`, `availability_thin`, `resource_constraint` | ✅ `depth_pressure`→`depth_constraint`; `rotation_pressure`→`coverage_pressure` | ✅ `thin_margin`, `coverage_concern` | **🟡** | Preserved, but SI V1's depth read keys on `injury_context`, narrower than Home's landscape counts. |
| **Fatigue / workload pressure** | ✅ (sig. `bullpen_stress`) + `thin_margin` | ✅ `sustainability_question`, `fatigue_load`, `workload_high` | ✅ `rotation_pressure`/`concentration_pressure` | ✅ `pressure_building` | **✅** | Well covered. |
| **Same-few-arms** | ✅ `sameArms` headlines | ✅ `stress_transfer` "same_few_carrying" | ✅ `concentration_pressure` | ✅ `concentrated_workload` | **✅** | Preserved via concentration. |
| **What-changed / delta** | ✅ `watch_list_growth` + `what_changed` payload | ➖ (separate payload) | ❌ no day-over-day | ➖ | **❌** | Out of SI V1 scope; lives in `what_changed_since_yesterday`. Adapter carries no delta. |
| **Continuity (new/ongoing/returning)** | ✅ via `story_continuity` | ➖ (separate payload) | ❌ no continuity state | ➖ | **❌** | Adapter has no continuity field (Phase 1). `story_continuity` payload still exists but is keyed by signature, not `story_id`. |
| **No-story / suppression** | ✅ `getStorySuppressionReasons` | ✅ evidence/quality gates | ✅✅ fail-closed neutral + reasons | ✅ `data_limited` | **✅** | Canonical *improves* this: explicit `suppression_reason` + fail-closed (tested in Phase 1). |
| **League-wide notes** (no team) | ✅ `league_*` (Note / Other Side / Check-In) | ✅ league rollups | ❌ per-team only | ➖ | **❌** | `build_team_story` requires a team; no league synthesis. |

---

## 3. Per-Page Migration Risk (answers the primary question by surface)

The blocker set **differs by page** — this is the key planning insight.

### Home (`/`) — **NOT READY**
Home emits: hero (pressure→watch→rest priority), "Three Things To Watch" + feed (pressure, watch, **rest**, **depth**, **league notes**), plus a what-changed section and continuity decoration.
- **Lost/reframed today:** positive rest/depth ("More Options", "Arms To Spare", "The Other Side"), league note + quiet-day "League Check-In" hero fallback, continuity status.
- **Preserved:** pressure / watch / workload / route-change cards.
- **Not Home's problem:** thin trust lane and bridge instability are **not** emitted by the Home view (only the Team panel emits them) — so they are *not* Home blockers.

### Stories (`/stories`) — **NOT READY (largest gap)**
Stories renders the **entire** Four-Beat feed, whose taxonomy is the richest: 5 rules, 14 lead dimensions, 7 observation families, 9 archetypes — including the positive `pressure_distribution`/`flexibility`/`flexible_bullpen`/`stability_recovery` classes and league rollups. Migrating to canonical today would drop every positive lead/observation and the league lane, and collapse 30+ nuanced classes into 4 pressure beats. Highest breadth loss.

### Team Board (`/bullpen?view=board`) — **NOT READY (different gap)**
The client panel's 14 archetypes include **thin trust lane**, **trust dependency**, **bridge dependency**, **stable bullpen**, and three positive depth classes — exactly the classes SI V1 **does not detect or reframes**. Team Board migration additionally requires **new detectors** (trust shape, bridge), not just a positive beat.

---

## 4. Story-Class Gap List

**Reframed (detected, wrong frame) — fixable without new detection:**
1. Positive depth (`optionality_strength`) → published as `sustainability_question` ("can this keep working?") or `depth_constraint`.
2. Stable core (`stable_core`) → published as `route_change` ("the route has changed"), strength 0.

**Lost — missing detection:**
3. Thin trust lane — no trust-shape detector in SI V1.
4. Bridge instability — role *stability* is read, but no bridge/handoff concept.

**Lost — out of per-team observation scope (architecture):**
5. What-changed / delta — no day-over-day comparison; lives in `what_changed_since_yesterday`.
6. Continuity (new/ongoing/returning) — no continuity state machine; lives in `story_continuity`; adapter carries no continuity field.
7. League-wide notes — `build_team_story` is per-team only.

**Signal-mismatch caveat (weakened even where "preserved"):** Home/Four-Beat derive many classes from **dashboard landscape counts** (available/monitor/restricted/total per team), while SI V1 derives from **context-layer bands** (`rotation_context`, `bullpen_concentration_context`, `bullpen_optionality_context`, `role_stability_context`, `injury_context`). The same-named class can fire on different evidence and at different thresholds, so even "preserved" classes may shift which teams light up.

---

## 5. Positive / Depth Blocker — Diagnosis

**It is a combination — and notably NOT primarily a detection problem.** For the headline positive classes (`optionality_strength`, `stable_core`), the bands already fire. The failure is downstream:

| Layer | Problem? | Evidence |
|---|:--:|---|
| **Detection** | ✅ present | `optionality_strength` fires on `optionality_band ∈ {flexible,deep}` (`story_observation_engine.py:227-233`); `stable_core` on `stability_band == 'stable'` (`:263-267`). |
| **Contract** | ❌ broken | No positive public beat. All four beats are pressure/question/change. `optionality_strength → sustainability_question` (`interpreter:61`), reroute to `depth_constraint` if any arm unavailable (`:215-223`); `stable_core → route_change` (`:57`). |
| **Ranking** | ❌ broken | `_selection_strength_for_sustainability` returns 0 unless type is concentration (`service:418-419`); `_selection_strength_for_route` gives `stable` 0 (`:522-527`); `_candidate_is_publicly_selectable` actively drops `optionality_strength + sustainability_question + strength ≤ 0` (`:584-592`). Positive-only teams land in `NEUTRAL_NO_VALID_FRAME`. |
| **Copy** | ❌ broken | Beat copy is pressure-framed: "The route has changed…" for a stable core (`interpreter:273`); "If this workload pattern holds, the route remains narrow…" for optionality (`:251-254`). |

**Conclusion:** the positive/depth blocker = **contract + ranking + copy** (detection is already there and being wasted). By contrast, **thin trust lane** and **bridge instability** *are* detection problems (plus contract). What-changed/continuity/league are **architecture/scope** problems (separate payloads / per-team-only).

---

## 6. Recommended Minimum-Viable Parity Set (gate for **Home** migration)

Home can migrate with a **smaller** set than Stories or Team Board. Minimum to migrate Home safely:

1. **MUST — Positive depth/rest story class, end-to-end.** Add a positive public beat (e.g. `availability_depth` / `rested_options`) for `optionality_strength` (and a positive `settled_core` read for `stable_core`): (a) contract — new beat in `PUBLIC_BEATS` + `BASE_OBSERVATION_BEAT_MAP`, remove the optionality→sustainability/depth reroute; (b) ranking — positive selection strength + remove the selectability gate so positive-only teams publish; (c) copy — positive writer path + voice lines; (d) adapter — map the new beat → tone `rest`/category `rested`, and drop `quality_status: review` / `POSITIVE_BEAT_LIMITATION` once supported. *Covers "More Options", "Arms To Spare", clean depth, rested flexibility.*
2. **MUST — Empty/quiet-feed + league-note fallback.** The canonical feed can be entirely empty on a quiet day; Home's hero currently falls back to "League Check-In" and the feed shows league notes. Either synthesize a league/quiet note in the adapter, **or** keep Home's league/quiet fallback from landscape metrics and define hero behavior when `stories.items` is empty.
3. **SHOULD — Continuity decoration wired to `story_id`.** Keep using the `story_continuity` payload, but key it to canonical `story_id` so the flagship still shows new/ongoing/returning.
4. **KEEP SEPARATE — What-changed.** Leave Home's what-changed section on the existing `what_changed_since_yesterday` payload; it is a distinct surface, not a story-feed class. Not a migration blocker.

**Explicitly out of scope for Home (defer to Team Board phase):** thin-trust-lane and bridge-instability **detectors** — these gate Team Board, not Home.

---

## 7. Recommended Implementation Order

1. **Phase 1.5 — Positive depth/rest beat** (contract + ranking + copy + adapter). Unblocks the #1 class. *Backend only, additive, behind the existing canonical feed.*
2. **Phase 1.6 — Empty/quiet-feed + league fallback** decision and implementation (adapter-synthesized league note, or Home-retained).
3. **Phase 1.7 — Continuity wiring** to `story_id`.
4. **Phase 2 — Home migration** (consume `payload["stories"]` behind a flag) — only after 1.5–1.7.
5. *(Later, pre-Team-Board)* trust-shape + bridge detectors; *(pre-Stories)* league/positive feed breadth parity.

---

## 8. Files Likely Involved (for the parity work — not modified by this audit)

- `backend/services/story_four_beat_interpreter_v1.py` — add positive beat; remove optionality reroute.
- `backend/services/story_intelligence_service_v1.py` — positive selection strength; relax `_candidate_is_publicly_selectable`; `SERVICE_OBSERVATION_ORDER` / `PUBLIC_BEAT_TIEBREAK_PRIORITY`.
- `backend/services/story_writer_v1.py` — positive writer copy path.
- `backend/services/story_voice_library_v1.py` — positive beat voice lines (and ensure none trip banned-language).
- `backend/services/story_construction_engine.py` — frame/confidence for the positive beat.
- `backend/services/story_observation_engine.py` — likely fine (bands already fire); optionally split a cleaner positive band.
- `backend/services/story_feed.py` — map new positive beat → `rest`/`rested`; drop the positive-beat limitation/`review` once supported; (if chosen) league/quiet + continuity fields.
- `backend/api/bullpen.py` — only if league-note synthesis or continuity wiring is added to the feed.
- *(Phase 2, not parity)* `frontend/src/components/home/homeIntelligenceView.js`, `BullpenStories.jsx`, `Home.jsx`.

---

## 9. Tests That Would Be Required

- **Interpreter:** `optionality_strength` → positive beat (not `sustainability_question`); reroute-to-`depth_constraint` removed/guarded; `stable_core` positive read.
- **Selection:** a positive-only team now **publishes** (not `NEUTRAL_NO_VALID_FRAME`); positive selection strength > 0; `_candidate_is_publicly_selectable` no longer drops it.
- **Writer/voice:** positive copy generated, passes `validate_written_observation`, no banned-language/term leakage.
- **Adapter (`story_feed`):** positive team → `story_available: true`, `tone: rest`, `category: rested`, `quality_status: published` (not `review`), no `positive_rest_depth_public_beat_not_yet_supported` limitation.
- **Parity/golden:** a fixture team that Home renders "Arms To Spare" / "More Options" today yields an equivalent positive canonical story.
- **Empty/quiet feed:** empty `stories.items` → defined hero fallback (league/quiet) behaves.
- **Continuity:** `story_continuity` resolves against a canonical `story_id`.
- **Regression:** existing pressure stories and `route_change` unchanged; suppression still fail-closed; `payload['stories']` contract and the four legacy fields unchanged; no governance ranking-term leakage.

---

## 10. Bottom Line

- **Biggest migration blocker:** the **positive rest/depth class** — detected, then inverted by contract + ranking + copy and usually suppressed. Good-news-only teams currently publish *nothing* under the canonical engine.
- **Can Home migrate yet?** **No.** Not until the positive depth/rest beat exists and a quiet/empty-feed + league fallback is defined; migrating today would silently drop or invert Home's positive stories and break the hero's quiet-day fallback.
- **Recommended next implementation prompt:** *"Phase 1.5 — Add a positive depth/rest beat to Story Intelligence V1 (contract + ranking + copy + adapter mapping), plus the empty/quiet-feed and league-note fallback decision,"* additive and backend-only, before any Home UI migration.

---

*Prepared June 2026 · read-only audit · no application code modified.*
