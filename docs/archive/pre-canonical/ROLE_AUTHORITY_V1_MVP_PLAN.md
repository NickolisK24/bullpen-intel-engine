# Role Authority V1 — MVP Plan

> **Type:** Planning / specification only. No code, schema, migration, branch,
> commit, PR, or documentation edit is produced here. Concrete signal bands below
> are **recommended starting calibration values for the build**, explicitly tunable
> — not code.
> **Objective:** the smallest *safe* slice that moves BaseballOS from innings-based
> bullpen eligibility to **`gamesStarted`-based Role Authority**, fixing the
> population foundation beneath the Board, Stress, What Changed, and Follow My Team.
> **Builds on:** the Eligibility Accuracy Audit, the Truth-Source Investigation, and
> the Role Authority V1 Design (Starter / Reliever / Ambiguous / Unknown;
> recency-weighted `gamesStarted` primary; confidence-bearing; fail-closed).

---

## 1. Executive Recommendation

**Ship the smallest possible slice: capture `gamesStarted` (one additive column),
backfill the recent window, classify role deterministically in a service, and plug
that role into the single shared population helper the surfaces already use — behind
a flag, with a read-only diagnostic first.**

Three facts make this small and safe:
1. **`gamesStarted` is already in the payload sync parses.** Sync reads
   `stat.get('saves')` / `stat.get('holds')` from the MLB gameLog `stat` object
   (`sync.py:135,139`); that same object carries `gamesStarted`. **Capturing it
   needs no new endpoint and no new API call** — one more field from data already
   fetched.
2. **There is already one shared population chokepoint.** `bullpen_population.py`
   (`eligible_bullpen_pitcher_contexts`) is the single definition the Board and What
   Changed consume. Role Authority plugs in **at exactly one place**, and every
   surface inherits the fix — no per-surface work, no drift.
3. **Role can be computed on the fly, exactly like eligibility is today.** No new
   role tables are required for MVP; role is derived deterministically from the
   (now-complete) game logs at request time, mirroring the existing eligibility
   pattern.

So the MVP is: **one nullable column + a partial backfill + one deterministic role
service + one wiring point + a minimal confidence chip + a diagnostic + a flag.**
Probable-pitcher ingestion, persisted role tables, and role history are **deferred**
— they improve the edges, not the foundation. **A migration is required, but it is
the smallest and safest kind: a single additive, nullable column.**

This unblocks trustworthy Bullpen Stress and future shareable reports by fixing the
population they are computed from — *before* those surfaces are amplified.

---

## 2. MVP Scope

**In scope:**
- Persist `GameLog.games_started` (additive nullable column).
- Capture `gamesStarted` in sync from the already-parsed `stat` object.
- Backfill `games_started` for the **recent/current-season window** by re-reading
  gameLog splits (same endpoint sync already uses).
- A deterministic **role classification service** → `Starter / Reliever / Ambiguous
  / Unknown` + **confidence**, with plain-language reason codes.
- A **minimal opener guard** (very-short "starts" lean Ambiguous).
- Wire role into the **shared population helper** so eligibility uses role instead of
  innings heuristics.
- **Minimal trust UI:** a role + confidence chip; an Ambiguous caveat; an Unknown
  "role not established" withholding note; a one-line Methodology update.
- A **read-only diagnostic** (league-wide role/eligibility diff) and a **feature
  flag**.
- The **validation replay suite** (§10).

**Out of MVP (deferred):** probable-pitcher ingestion, persisted role/confidence on
`Pitcher`, role-authority tables, role evidence snapshots/history, manual override,
opener sub-typing, full multi-season backfill. (See §12.)

---

## 3. Data Model Requirements

| Candidate | MVP? | Rationale |
| --- | --- | --- |
| **`GameLog.games_started`** (nullable int 0/1, or `is_start` bool) | **Required** | The one unavoidable persistence; the authoritative per-appearance start bit. Smallest possible schema change. |
| Role fields on `Pitcher` (role/confidence) | **Defer** | Role is computed on the fly from logs at request time, exactly as eligibility is today. No persistence needed for correctness. |
| Separate role-authority table | **Defer** | Only needed for history/audit-trail/perf; not for the fix. |
| Confidence fields (persisted) | **Defer** | Computed alongside role on the fly. |
| Reason codes (persisted) | **Defer** | Emitted at request time with the role; not stored in MVP. |
| Role evidence snapshots | **Defer** | A history/trend feature, not foundational. |

**Answers:**
- **Required for MVP:** exactly one column — `GameLog.games_started`.
- **Deferrable:** all role/confidence/snapshot persistence (compute on the fly).
- **Migrations required?** **Yes — one**, additive and nullable (the safest class;
  no backfill-before-deploy ordering hazard, no NOT NULL constraint at create).
- **Smallest safe schema change:** add the single nullable `games_started` column;
  backfill afterward; never block on it (a null reads as "start unknown," handled by
  the role rules / Unknown).

---

## 4. Ingestion Requirements

| Input | Status today | MVP action |
| --- | --- | --- |
| **`gamesStarted` (per appearance)** | **Discarded** (in the parsed `stat`, not read) | **Capture now** — read `stat.get('gamesStarted')` alongside the saves/holds already read; store on `GameLog`. No new endpoint. |
| Saves / holds | Captured | Keep; reuse as relief confirmation in the role rules. |
| Appearances / game dates / innings | Captured | Keep; used for recency windows, evidence count, opener guard (innings as tie-breaker only). |
| Recent-window start pattern | Derivable once `games_started` exists | Compute in the role service (no new ingestion). |
| Season-window start pattern | Derivable once backfilled | Compute in the role service. |
| **Probable pitchers** | Not ingested | **Defer.** New endpoint + cadence; mainly resolves no-history rookies, which **Unknown safely withholds** in the interim. Fast-follow, not MVP. |

**Answers:**
- **Ingest now:** `gamesStarted` (the only new capture; zero new API surface).
- **Already exists:** saves, holds, innings, appearances, game dates.
- **Discarded today:** `gamesStarted` (the whole problem).
- **Deferred:** probable-pitcher ingestion.

---

## 5. Role Classification Rules (deterministic, MVP)

> Deterministic, explainable, no ML, no prediction. Inputs: per-appearance
> `games_started` over a **recent window** and a **season window**, appearance count
> (evidence), saves/holds (relief confirmation), and innings (opener tie-breaker
> only). **Bands below are recommended starting defaults — tunable at build time.**

Compute, over the recent window (recommended ≈ last 30–40 days or last ~8–10
appearances, whichever yields a usable sample) and the season window:
- `start_share = starts / appearances`
- `evidence = appearances in window`

**Classification (first match wins, recency-first):**

1. **Unknown** — `evidence` below a minimum (e.g., 0 recent appearances **and** no
   season starts/relief evidence). *No evidence → assert nothing.*
2. **Starter** — recent `start_share` high (≈ ≥ 0.80) with sufficient evidence,
   corroborated (not contradicted) by season pattern.
3. **Reliever** — recent `start_share` very low (≈ ≤ 0.20) with sufficient evidence,
   and/or relief confirmation (any saves/holds/games-finished). `gamesStarted ≈ 0`
   over the window is the spine here.
4. **Ambiguous** — any of:
   - middle `start_share` (≈ 0.20–0.80) over a real sample (**swingman**), or
   - strong **recent-vs-season disagreement** (conversion in progress), or
   - **opener guard:** "starts" that are consistently very short (e.g., ≤ ~2 IP) →
     treat as not-true-starts → Ambiguous rather than Starter.
5. **Unknown** (fallback) — sample too thin for any confident assertion.

**Determinism guarantees:** identical logs → identical role; a single outlier
appearance (one spot start, one short relief outing) cannot flip a well-evidenced
role (recency weighting + minimum-evidence guards). Every output carries reason
codes (§6).

---

## 6. Confidence Model (MVP)

| Confidence | Criteria | User-facing meaning | Reason examples |
| --- | --- | --- | --- |
| **High** | Ample evidence **and** recent/season agree | "We're confident in this role." | "11 of 12 recent appearances were starts." / "No starts in 30 days; 7 relief appearances, 3 holds." / "Splits ~50/50 across 14 appearances → swing role." |
| **Medium** | Moderate sample, recent transition settling, or single strong source | "Likely, with some uncertainty." | "Recently moved to the rotation — 3 straight starts after a relief stretch." |
| **Low** | Thin sample, conflicting signals, or opener-guard trip | "Tentative read." | "One start against a relief history." / "Short 'starts' suggest an opener role." |
| **None** | No usable evidence | "Role not established." | "No recent appearances on record." |

Confidence is **confidence in the stated classification** — a clean swingman is
**Ambiguous (High)** ("confident it's a swing role"). Confidence is deterministic
(same inputs → same level) and always accompanies the role.

---

## 7. Bullpen Eligibility Behavior

Role Authority replaces the innings-heuristic gate inside the **shared population
helper** (`eligible_bullpen_pitcher_contexts`). Behavior by role:

| Role | Default bullpen population | Notes |
| --- | --- | --- |
| **Starter** | **Excluded** | The core fix (Burns/Lodolo/Lowder/Paddack, Cole/Rodón, etc.). |
| **Reliever** | **Included** | Includes long/multi-inning relievers (GS=0) that innings logic wrongly excluded. |
| **Ambiguous** | **Included with a visible caveat** | They do relieve; surfaced with a "swing role" chip. |
| **Unknown** | **Withheld** from default counts | Shown only on explicit request (e.g., an "include unestablished" toggle). Fail-closed. |

**Surface effects (all inherited through the one shared helper — no per-surface
logic):**
- **Bullpen Board:** population becomes role-correct; starters drop out, long
  relievers return, swing arms carry a caveat, unknowns are withheld.
- **Bullpen Stress:** computed over the corrected population; **Ambiguous arms count
  with a confidence discount or are shown distinctly** so swing pieces don't inflate
  depth.
- **What Changed:** reports changes only for the role-correct bullpen — rotation
  names stop leaking.
- **Follow My Team:** inherits the corrected population automatically.

Role stays **orthogonal** to roster status (active/IL) and availability (workload) —
three independent axes, as the codebase already separates the latter two.

---

## 8. Migration / Backfill Strategy

| Question | Answer |
| --- | --- |
| Can existing `game_logs` rows be backfilled with `gamesStarted`? | **Yes** — re-read the MLB gameLog splits (the same endpoint sync uses); `gamesStarted` is in each split's `stat`. Update existing rows by `(pitcher_id, mlb_game_pk)`. |
| Is MLB re-sync required? | **A targeted re-read, yes** — but via the existing sync path, not a new integration. |
| Full-season re-sync required? | **No.** A **partial backfill of the recent/current-season window** is sufficient because role reads are recency-weighted. |
| Can it be partial? | **Yes — recommended.** Backfill the window the role service actually consults; older rows can remain null (read as start-unknown → handled by Unknown). |
| What is safest? | **Additive nullable column → partial backfill → verify via the read-only diagnostic → flip eligibility behind the flag.** Backfill is idempotent (keyed upsert) and can run repeatedly without harm. |
| What before release? | Column live + recent-window backfilled + diagnostic reviewed, so the population change is **audited before** it goes live. |

**Ordering (safe):** add nullable column (deploy, no behavior change) → backfill
window → run diagnostic diff → enable role-based eligibility behind the flag. Each
step is independently reversible; nulls never break the rules (they degrade to
Unknown).

---

## 9. UI / Trust Surface Requirements (minimal)

| Element | MVP? | Notes |
| --- | --- | --- |
| **Role chip** (Starter/Reliever/Swing/Unknown) | **Yes** | On pitcher cards/detail; plain baseball words ("Swing role," not "Ambiguous-Low"). |
| **Confidence indicator** | **Yes (compact)** | A small qualifier on the chip; full reasons in detail/disclosure. |
| **Ambiguity caveat** | **Yes** | One line on swing arms shown in the pen. |
| **Unknown withholding reason** | **Yes** | When a pitcher is withheld/optional: "Role not yet established." |
| **Methodology update** | **Yes (one section)** | Document the `gamesStarted` authority + role/confidence model, mirroring the existing methodology transparency. |
| Role badges everywhere / dashboards / role analytics | **No** | Overbuild; defer. |

Keep it to a chip + caveat + a methodology paragraph. The trust value is in the role
being *right* and *explained on demand*, not in heavy new UI.

---

## 10. Validation Strategy

Deterministic fixtures + a league-wide replay, asserting the corrected population:

- **Reds audit replay:** Burns, Lodolo, Lowder, Paddack classify **Starter →
  excluded** from the bullpen population.
- **Yankees starters:** Cole, Rodón (and Schlittler if start-evidenced) **excluded**.
- **Known relievers remain included** (closers/setup with GS=0 + saves/holds).
- **Multi-inning / long relievers remain included** (GS=0 despite ≥3 IP) — the
  reversed false-negative.
- **Rookie starters:** with start evidence → **Starter (excluded)**; with no history
  and no probable → **Unknown (withheld)** — safe either way.
- **Ambiguous / swingmen:** classify **Ambiguous**, included **with caveat**.
- **Unknown / no-evidence pitchers:** **withheld** from default counts.
- **Determinism:** identical logs → identical role + confidence (repeatable).
- **Cross-surface parity:** Bullpen Stress, What Changed, and Follow My Team all use
  the corrected population (assert they read the shared helper, not a re-derived
  set).
- **Diagnostic diff review:** the read-only league-wide before/after report is sane
  (no mass unexpected exclusions/inclusions) **before** the flag flips.

---

## 11. Rollout Strategy (trust-protecting)

1. **Read-only diagnostics first.** Ship the column + backfill + role service, and
   produce a **league-wide role/eligibility diff report** *without* changing the live
   board. Audit who moves in/out. This is the single most important trust safeguard —
   never silently change the board population.
2. **Behind a flag.** Gate role-based eligibility so it can be toggled per
   environment and rolled back instantly.
3. **Surface confidence immediately once live.** When the flag flips, show role +
   confidence — the transparency *is* the trust story; don't hide it.
4. **Protect the storytelling surfaces.** Do **not** build/expand shareable Daily
   Stress Reports until role authority is live; the existing Stress surface
   benefits automatically through the shared helper once the flag is on. Landing
   this is the precondition for amplifying anything built on the population.

---

## 12. MVP vs. Later vs. Do Not Build

### MVP (build now)
- `GameLog.games_started` column + sync capture + recent-window backfill.
- Deterministic role service (Starter/Reliever/Ambiguous/Unknown + confidence +
  reason codes) with a minimal opener guard.
- Wire role into the shared population helper (eligibility).
- Minimal role/confidence chip + caveat + Methodology paragraph.
- Read-only diagnostic + feature flag + validation suite.

### Later (useful, not required)
- **Probable-pitcher ingestion** (resolve no-history rookies → Starter instead of
  Unknown).
- Persisted role/confidence on `Pitcher` + a role-authority table (perf/audit/trend).
- Role evidence snapshots and **role-trend** ("moved to the pen 2 weeks ago").
- **Manual override** layer for the irreducible tail.
- Explicit **Opener** sub-type tag.
- Full multi-season backfill for early-season prior-year backstop.

### Do Not Build (out of scope / harmful)
- Any **ML / predictive** role model.
- A **third-party role feed** as the primary authority.
- Persisting derived **narrative** as authority.
- A **governance/certification** project around role (this is a focused fix, not a
  program).
- Dropping **Ambiguous/Unknown** to force a binary.
- Exposing a raw numeric **"role score."**

---

## 13. Risks & Tradeoffs

| Risk | Severity | Mitigation |
| --- | --- | --- |
| **Silent population change in prod** | High | Read-only diagnostic diff **before** the flag flips; flag-gated rollout. |
| **Backfill completeness** (thin/missing rows → Unknown) | Med | Partial recent-window backfill covers active arms; nulls degrade to Unknown (safe), not to a wrong role. |
| **Opener edge** (GS=1 but reliever) | Med | Minimal opener guard (short-start → Ambiguous); accept residual imperfection; full opener tagging deferred. |
| **Rookie under-inclusion without probables** | Low–Med | Unknown withholds them honestly; probables fast-follow resolves it. A missing arm a user can add back beats a wrong one. |
| **Threshold calibration** (bands) | Med | Deterministic + diagnostic-reviewed; start conservative; tune from the diff report. |
| **On-the-fly compute cost** | Low | Same pattern/cost as today's eligibility; monitor; persist later if needed. |
| **Migration risk** | Low | Single additive nullable column — the safest migration class. |

**Core tradeoff:** MVP intentionally trades the rookie-precision that probables would
add for a much smaller, safer slice; Unknown makes that tradeoff honest (withhold,
don't guess).

---

## 14. Founder Guidance (brutally honest)

**1. Is Role Authority V1 ready to implement after this plan?**
**Yes.** The authority signal is already in the ingested payload, the wiring point
already exists (`bullpen_population.py`), and the classification + fail-safes are
specified. There is no open design question blocking a build.

**2. Does MVP require a database migration?**
**Yes — exactly one**, and it's the safest kind: a single additive, **nullable**
`GameLog.games_started` column. It cannot be avoided without re-fetching MLB on every
request (too slow/fragile) or deriving from innings (the very bug). Don't pretend it's
migration-free; it's migration-*minimal*.

**3. What is the smallest safe MVP?**
The column + a recent-window backfill + a deterministic role service + wiring it into
the one shared population helper + a minimal confidence chip — shipped **diagnostic-
first, behind a flag.** Nothing else is required to fix the foundation.

**4. What is the biggest implementation risk?**
**Silently changing the live board population.** Mitigate by computing the
league-wide diff in read-only mode and auditing it *before* flipping the flag. The
second risk is the **opener edge** and **threshold calibration** — both contained by
the opener guard, conservative defaults, and the diagnostic.

**5. What should not be included in MVP?**
Probable-pitcher ingestion, persisted role tables/snapshots, role trends, manual
override, opener sub-typing, full-history backfill, any ML, and any heavy role UI.
All are real *Later*, none are foundational.

**6. Should implementation go to Claude or Codex?**
**Split, Claude-led.** The mechanical parts — the additive column, the backfill job,
the UI chip, and the test scaffolding — are **Codex-friendly**. But the **role
classification service, the Ambiguous/Unknown fail-safes, the opener guard, and the
read-only diagnostic** carry the trust contract ("withhold, don't guess; never
silently change the board") and should be **owned/reviewed by Claude**. Whoever builds
it must not collapse Ambiguous/Unknown back into a binary or let role drift outside
the shared helper.

**7. Does this unblock Bullpen Stress and future Daily Stress Reports?**
**Yes — it is the precondition.** Landing Role Authority V1 makes the bullpen
population trustworthy, so Stress (already wired through the shared helper) is
corrected automatically, and shareable Daily Stress Reports can be built and amplified
**without baking the contamination into public artifacts.** Build this *before* you
amplify.

---

*Planning only. No code, schema, migration, branch, commit, PR, or documentation edit
was produced. Signal bands and windows are recommended starting calibration values
for the eventual build, explicitly tunable; they are not an implementation.*
