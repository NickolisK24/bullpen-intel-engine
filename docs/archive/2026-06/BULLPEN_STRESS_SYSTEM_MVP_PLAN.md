# Bullpen Stress System — MVP Plan

> **Type:** Planning / specification only. No code, schema, migration, threshold,
> classification, or engine change is produced here.
> **Feature:** Bullpen Stress System — the storytelling layer that answers *"What
> shape is this bullpen in tonight, and why should I care?"*
> **Goal:** The smallest *trustworthy* bullpen-stress surface that turns existing
> BaseballOS data into a story users understand and share — descriptive, not
> predictive.
> **Grounding:** Verified against shipped code on `origin/dev`/`main`. The core of
> this feature **already exists** as `services/bullpen_board.py`
> `classify_bullpen_health` + `build_team_context`.

---

## 1. Executive Recommendation

**Do not build a stress engine. Promote the one that already exists.**

BaseballOS already computes, deterministically and on existing data, a team-level
bullpen condition: `build_team_context` returns a **health state**
(`manageable / monitoring / elevated / constrained / no_data`), full **metrics**
(available/monitor/limited/avoid/unavailable counts + percentages), a
**count-referencing explanation** (`health.reasons`), and an honest **confidence**
read that already degrades on stale data. That *is* a bullpen-stress model. It is
just not surfaced as a first-class, named, shareable "stress" story.

**The MVP is therefore a thin presentation + consistency layer**, not a new
engine:
1. A small **pure function** that maps the existing `health.state` → a user-facing
   **stress label**, a **severity tier** (for color), stable **reason codes**, and
   the already-computed reasons/confidence.
2. Surfaced as a **Bullpen Stress badge + summary** on the **Bullpen Board team
   header** and the **Follow My Team** card, both reading the **same** team-context
   payload.
3. **Label + explanation, no numeric score.** Reuse the existing reasons; add no
   new thresholds.

This works entirely on existing data, requires **no new tables, no migrations, no
new endpoint**, reuses the board's already-correct eligible-bullpen population (so
it cannot drift the way What Changed did), and directly feeds the future Daily
Bullpen Stress Report from the same payload.

**Confidence the MVP is buildable as specified: HIGH.** The hard part (the
deterministic condition model) is shipped and trusted; what remains is labeling,
copy, color, placement, and tests.

---

## 2. Bullpen Stress Definition (BaseballOS terms)

> **Bullpen stress is a descriptive, deterministic read of a team's *current*
> bullpen condition, derived from the distribution of availability statuses across
> its eligible relievers — how many arms are fresh vs. restricted, how concentrated
> the Monitor group is, and how much available depth remains.**

It answers "what shape is this pen in tonight?" using signals BaseballOS already
computes:
- **Availability distribution** (Available / Monitor / Limited / Avoid /
  Unavailable counts) — the spine.
- **Restricted share** (Avoid + Unavailable as a fraction of the pen).
- **Monitor concentration** (is Monitor the dominant group?).
- **Available depth** (how many arms are clear tonight).
- *(Later)* recent appearances / pitch load as supporting color.

**It is explicitly NOT:** win probability, save prediction, injury prediction,
best-arm selection, a betting signal, or a ranking of teams. It is a *condition
description*, the bullpen equivalent of "the roads are icy" — never "you will
crash."

---

## 3. Existing Data Audit

| Source | Exists? | Role in MVP |
| --- | --- | --- |
| **Bullpen Board team context** (`build_team_context`: health state, metrics, reasons, confidence) | ✅ | **The model.** Stress is a relabeling/curation of this. |
| `classify_bullpen_health` (states + deterministic thresholds) | ✅ | Reused unchanged — the state source of truth. |
| Availability statuses (per pitcher, grouped) | ✅ | Inputs to the counts the state derives from. |
| Eligible-bullpen population (board's roster + starter filtering) | ✅ | Reused via the board's group counts → correct population for free. |
| Fatigue scores / recent appearances / pitch load | ✅ | Optional *Later* enrichment of the explanation. |
| Usage roles | ✅ | Not required for MVP (count-based); *Later* color. |
| What Changed endpoint | ✅ | Sibling surface; shares team context; not a dependency. |
| Freshness metadata (durable) | ✅ | Drives confidence + stale handling (already wired into `build_team_context`). |
| A persisted "stress" record / history | ❌ | Not needed for MVP; required only for *Later* stress-trend. |

**Direct answers:**
1. **What data already exists?** Everything the MVP needs: the health state,
   metrics, reasons, confidence, and the eligible population — all in
   `build_team_context`.
2. **What's missing?** Nothing for MVP. Stress *history/trend* would need
   persistence (Later).
3. **Can MVP ship without new tables?** **Yes.**
4. **Without migrations?** **Yes.**
5. **Can MVP reuse existing board/team-context logic?** **Yes — it should be built
   almost entirely on it.** Reusing the board's group counts also inherits the
   correct eligible-bullpen population, avoiding the drift bug that hit What
   Changed.

---

## 4. Recommended Stress Levels

**Recommendation: map the existing health states 1:1 to a stress vocabulary —
four active levels plus an explicit unknown state. Add no new thresholds in MVP.**

| Stress level (user-facing) | Existing state | Plain meaning | Criteria (already implemented) | Example | Failure/edge |
| --- | --- | --- | --- | --- | --- |
| **Manageable** | `manageable` | Plenty of arms, light restriction | None of the elevated/monitoring/constrained rules trip | 5 of 7 Available, 0 restricted | If counts are sparse, confidence drops (see §9) |
| **Monitoring** | `monitoring` | Several arms need a workload check | Monitor ≥ 40% of pen, or Monitor is the largest group | 4 of 7 in Monitor | Don't read as "bad" — it's a watch state |
| **Elevated** | `elevated` | Workload pressure is building | Avoid+Unavailable ≥ 20%, or Available < 40% | 2 of 7 restricted, 2 Available | — |
| **Constrained** | `constrained` | Availability is tight tonight | Avoid+Unavailable ≥ 40%, or nobody Available | 3 of 6 Avoid/Unavailable | Highest active severity in MVP |
| **No Read** | `no_data` | Can't summarize tonight | No relievers in the freshness window | Off-day / stale | Explicit unknown, never "Fresh" |

**On "Fresh" and "Severe" (the prompt's six-level example):** both are attractive
but each requires a **new presentation threshold** on top of the existing states
("Fresh" = a high-availability split of `manageable`; "Severe" = an extreme split
of `constrained`). To honor *"do not create another engine,"* keep MVP at the four
existing states and **defer Fresh/Severe to Later** as pure display splits on
already-computed metrics (`pct_available`, `pct_unavailable`). This keeps the MVP
threshold-free and fully backed by logic that is already tested and trusted. The
existing `constrained` already communicates "severely stressed"; the existing
`manageable` already communicates "in good shape."

---

## 5. Score vs. Label

**Recommendation: label + explanation. No visible numeric score. No hidden score
either — none is needed.**

| Option | Verdict | Why |
| --- | --- | --- |
| Visible numeric score ("Stress 73.4") | ❌ | False precision; invites ranking/betting reading; contradicts trust principles. |
| Hidden score → visible label | ❌ (unnecessary) | The state is already derived deterministically from counts; no intermediate score exists or is needed. |
| **Label + explanation** | ✅ **MVP** | "Bullpen workload is elevated" + the count-based reasons is exactly the right altitude. |
| Label only | ⚠️ | A label with no "why" is weaker and less shareable; include the reasons. |

Supporting **counts** may be shown as evidence ("3 of 7 are Avoid or Unavailable")
— those are facts, not a synthesized score. The product needs *"Bullpen workload
is elevated,"* not *"Stress Score: 73.4."*

---

## 6. Explanation / Reason Model

**Reuse `health.reasons` (already count-referencing and plain-English), framed for
the stress story.** Structure:

1. **Headline line** — the stress label as a sentence: *"Bullpen workload is
   elevated."* (from `HEALTH_LABELS`).
2. **2–4 evidence bullets** — the existing reasons, e.g.:
   - *"2 of 7 relievers are Avoid or Unavailable."*
   - *"3 of 7 relievers are in the Monitor group."*
   - *"4 of 7 relievers are Available tonight."*
3. **Methodology + caveat line** — the existing
   *"Availability classifications are workload-based only."* and any freshness
   note.

**Reason codes (new, thin):** alongside the human strings, emit **stable enum
codes** so the frontend stays dumb and tests are deterministic — e.g.
`restricted_share_high`, `monitor_group_dominant`, `low_available_depth`,
`freshness_limited`. These are derived from the *same* counts the state uses;
no new thresholds beyond what `classify_bullpen_health` already applies.

*(Later)* enrich with *"the bullpen threw N pitches over the last M days"* and
*"setup/closer arms pitched recently"* — both require pulling recent appearances/
roles, so they are out of the MVP's count-only scope.

Keep all copy descriptive and past/present-tense. No prediction, no advice.

---

## 7. Backend / API Recommendation

| Decision | Recommendation | Rationale |
| --- | --- | --- |
| New stress **engine**? | **No** | `classify_bullpen_health`/`build_team_context` already are the model. |
| New stress **presentation function**? | **Yes — one small pure function** | e.g. `build_bullpen_stress(team_context)` → `{ state, label, severity_rank, reason_codes, reasons, confidence }`. Deterministic, unit-testable. |
| Extend existing payload or new endpoint? | **Extend** the board's team-context payload with a `stress` block | The board already computes and returns team context; no new endpoint, no new query. |
| Team-scoped? | **Yes** | Matches board + Follow My Team. League-wide is Later. |
| Where does it read counts from? | **The board's existing group counts** (not a fresh pitcher query) | Inherits the correct eligible-bullpen population → cannot drift (the What Changed lesson). |
| How are reason codes exposed? | **Stable enums + human strings**, both in the `stress` block | Keeps the frontend dumb; tests assert codes. |

**Shape (illustrative):**
```jsonc
"stress": {
  "state": "elevated",
  "label": "Bullpen workload is elevated.",
  "severity_rank": 3,                  // 1 manageable … 4 constrained; 0 = no_read
  "confidence": "high",                // reused from team context
  "reason_codes": ["restricted_share_building", "monitor_group_present"],
  "reasons": [
    "2 of 7 relievers are Avoid or Unavailable.",
    "3 of 7 relievers are in the Monitor group.",
    "Availability classifications are workload-based only."
  ],
  "limitations": []
}
```

**Frontend stays dumb:** it renders `label`, picks a color from `severity_rank`,
lists `reasons`, and shows `limitations`. No client-side stress logic.

---

## 8. Frontend / UX Recommendation

**Components (two small, reused on both surfaces):**
- `BullpenStressBadge` — the stress `label` + a severity-colored dot (from
  `severity_rank`). Compact; used in the board team header and the Follow My Team
  card.
- `BullpenStressSummary` — the badge plus the `reasons` bullets, `confidence`, and
  any `limitations`. Used where there's room (board header expanded, card body).

**Placement (MVP):**
- **Bullpen Board team header** — the natural home; team context is already there.
- **Follow My Team card** — the retention surface; reads the same `stress` block.

(League-wide stress section, team-comparison, and the Daily Stress Report are
**Later** — all consume the same payload, so no rework.)

**Copy strategy:** lead with the plain stress sentence; reasons as short
count-based bullets; never use ranking/prediction/betting words. One voice across
both surfaces (driven by backend strings).

**Color/severity:** reuse existing availability color tokens on a calm ramp —
Manageable = green, Monitoring = amber, Elevated = orange, Constrained = red,
No-Read/stale = muted gray. Color comes from `severity_rank`, not client logic.

**Empty/stale/no-data:** see §9 — explicit muted states, never a fabricated
"Manageable/Fresh."

**Mobile:** the badge (label + dot) is the primary mobile unit; the summary's
reasons collapse behind a tap/expand. Do **not** redesign the dashboard — this is
an additive badge/summary.

---

## 9. Trust & Stale-Data Handling

Reuse the confidence/limitations `build_team_context` already produces; the stress
layer must **degrade, never fabricate.**

| Situation | Behavior |
| --- | --- |
| **Data stale** (`is_current = false`) | `confidence: low`; show the existing *"may not reflect tonight"* caveat; render the badge **muted** with a "data is N days old" note. Never present a crisp severity as a confident live read. |
| **Freshness metadata unavailable** | Treat as stale/unknown → **No Read** style state with a neutral "stress read paused" message. |
| **Bullpen population incomplete** | Lower confidence + add a limitation; never imply a confident "Manageable" from a thin pen. |
| **No recent game / `no_data`** | Explicit **No Read** ("No bullpen stress read available tonight"), never a default level. |
| **Roster status unknown** | Inherit the board's fail-closed roster handling (the reused population already excludes unresolved arms); note as a limitation if it materially thins the pen. |
| **Role/usage data limited** | No MVP impact (stress is count-based); flag only as a *Later*-enrichment caveat. |

**Prime directive:** when confidence is low or the population is unknown, show the
caveat prominently and **fall back to a muted/No-Read state** — fabricating
"Fresh/Manageable" on stale or empty data is the one unforgivable failure for a
trust-first surface.

---

## 10. MVP vs. Later vs. Do-Not-Build

### MVP (build now)
- `build_bullpen_stress(team_context)` pure function (state → label, severity,
  reason codes, reasons, confidence), reading the board's existing counts.
- Four levels (`manageable/monitoring/elevated/constrained`) + **No Read**
  (`no_data`); no new thresholds.
- **Label + explanation, no score.**
- `stress` block added to the existing team-context payload (no new endpoint).
- `BullpenStressBadge` + `BullpenStressSummary` on the **board header** and
  **Follow My Team** card.
- Full stale/no-data trust handling (reused confidence/limitations).

### Later (useful, not now)
- **Fresh** and **Severe** levels as presentation splits on `pct_available` /
  `pct_unavailable` (still no engine).
- Explanation enrichment: recent appearances, pitch load over N days, setup/closer
  recency (roles).
- **League-wide stress landscape** ("around the league tonight") and
  team-comparison stress.
- **Daily Bullpen Stress Report** + shareable stress card (same payload).
- **Stress trend** ("stress rising 3rd straight day") — needs persistence.

### Do Not Build (out of scope or harmful)
- A visible or hidden **numeric stress score**.
- A **new stress engine/model** parallel to `classify_bullpen_health`.
- **Predictions** of any kind (save/injury/win-probability/outcome).
- **Rankings** of "most stressed teams" framed competitively, or any **betting**
  signal/outcome language.
- New **thresholds** in MVP (defer Fresh/Severe).
- Duplicating the pitcher-population query (must reuse board counts to avoid
  drift).

---

## 11. Implementation Sequence

1. **`build_bullpen_stress(team_context)`** pure function + reason-code derivation
   (backend, fully unit-tested against fixed counts).
2. **Attach `stress`** to the board's team-context payload (no new query/endpoint).
3. **`BullpenStressBadge`** on the Bullpen Board team header (first visible win).
4. **`BullpenStressSummary`** + wire the **Follow My Team** card to the same block.
5. **Trust/stale states** (muted badge, No-Read, caveats) across both surfaces.
6. **Tests** alongside each step; finish with the full matrix (§11) green.

This front-loads the deterministic backseat function (highest confidence) and adds
UI on top of already-correct data.

---

## 12. Validation Strategy

> Deterministic fixtures over group counts + a stubbed freshness block, asserting
> the `stress` block from `build_bullpen_stress`. The engine internals are not
> re-tested (they already are).

- **State→label mapping:** each of the four states yields the correct label and
  `severity_rank`; `no_data` yields the **No Read** state.
- **Reason codes:** fixtures for restricted-heavy, monitor-dominant, low-available,
  and healthy pens emit the expected `reason_codes` (and human strings).
- **Population parity (anti-drift):** stress is computed from the **same counts**
  the board renders for the team (assert stress state == `build_team_context`
  health state for identical input) — locks against a divergent population.
- **No score / no precision:** payload and copy contain **no** numeric stress
  score and no ranking/prediction/betting vocabulary (string assertions).
- **Stale:** `is_current = false` → `confidence: low`, caveat present, badge muted;
  state never silently upgraded to Manageable/Fresh.
- **No-data:** zero relievers → **No Read** state + neutral message, not a level.
- **Confidence passthrough:** confidence/limitations match the source team context.
- **Frontend:** badge color derives only from `severity_rank`; summary renders
  reasons/limitations; mobile collapse works; stale/no-data render the muted states.

---

## 13. Risks & Limitations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| **Over-precision creep** (someone adds a score) | Med | §5/§13 non-goals; tests assert no numeric score. |
| **Population drift** (stress computed from a different pitcher set than the board) | High | Compute strictly from the board's group counts; parity test (§12). |
| **Stale data shown as confident** | High | Confidence gating + muted/No-Read fallback (§9); tests. |
| **Scope creep** into daily report / league-wide / trends | Med | §10 Later; MVP is two surfaces, one payload block. |
| **"Severe/Fresh" threshold temptation** | Med | Deferred as presentation-only splits; MVP stays at the four existing states. |
| **Copy drifting toward prediction/ranking** | Med | Backend owns all strings; vocabulary tests. |

**Inherent limitation to state honestly in-product:** stress describes
*workload-based availability* only — not injuries, manager intent, warm-up state,
or matchup. It reports the bullpen's shape from public workload data, as of the
latest games.

---

## 14. Explicit Non-Goals

- Not a numeric stress score (visible or hidden).
- Not a new engine — it reuses `classify_bullpen_health`/`build_team_context`.
- Not predictive (no save/injury/win-probability/outcome).
- Not a competitive ranking or betting signal.
- No new availability thresholds, fatigue scoring, or classification changes.
- No league-wide section, daily report, shareable card, or stress trend **in MVP**.
- No new tables, migrations, or endpoints.

---

## Founder Guidance (brutally honest)

**1. Is this feature ready for implementation?** **Yes — more than most.** The
model already exists and is trusted; the MVP is a presentation/consistency layer
plus copy and tests. There is no open modeling question blocking a build.

**2. Can the MVP be built without new database tables?** **Yes, completely.** It's
a pure function over the board's existing team-context counts. Persistence is only
needed for the *Later* stress-trend feature.

**3. What is the safest first implementation?** A deterministic
`build_bullpen_stress(team_context)` that maps the **existing** health state to a
label + severity + reason codes, surfaced first as a **badge on the Bullpen Board
team header** (where the data already lives), then reused on Follow My Team. No new
endpoint, no new query, no new thresholds.

**4. What should NOT be included in the MVP?** A numeric score; "Fresh"/"Severe"
new thresholds; any prediction; league-wide or daily-report surfaces; the
shareable card; stress trends; and any second pitcher-population query (reuse the
board's counts).

**5. Should implementation go to Claude or Codex?** Honestly, this is the **most
Codex-friendly** item in the roadmap so far — it's largely mechanical: a small
pure function, a payload field, two badges, and a deterministic test matrix over
an existing model. **Recommendation: Codex can own the build from this spec**, with
**one Claude (or careful human) review gate on the trust contract** — the
stale/no-data fallback copy and the "never fabricate Fresh/Manageable" rule (§9)
are the only parts where getting the wording and gating exactly right matters more
than mechanics. Keep whoever builds it from quietly turning the mapping into a new
scoring engine.

---

*Planning produced read-only. No application code, schema, migration, threshold,
classification, recommendation, governance, or certification artifact was created
or modified. The deliverable is this specification only.*
