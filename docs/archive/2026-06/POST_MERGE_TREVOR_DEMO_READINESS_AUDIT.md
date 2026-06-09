# BaseballOS — Post-Merge Trevor Demo Readiness Audit (Main)

*Final product-readiness checkpoint. Reviewed against the current `main` after the
bullpen board, team context, comparison, usage roles, dashboard realignment,
scope clarification, and Data & Trust separation all merged. Lens: a baseball
professional (Trevor May) opening the app today. Product- and baseball-focused —
not architecture or governance.*

---

## Headline

BaseballOS is now a **focused bullpen availability & workload tool**, and it
reads that way from the first screen. The prior audit's biggest problem — a
landing page that felt like an internal operations console — is **fixed**. The
dashboard leads with baseball, the bullpen board is the star, and the
governance/trust depth is tucked into its own page.

This is a real, demoable product. The remaining issues are **polish and friction**,
not identity. **Feature expansion should pause; the next wins are refinement.**

---

## 1. First impression

- **What it appears to do:** show which relievers are available across MLB
  bullpens tonight, how stressed each pen is, and what role each arm has been
  used in. That is now obvious within a few seconds of the landing page.
- **Strong:** the hero says "League-Wide Bullpen Overview" with a clear scope
  chip; the snapshot/health/roles read as baseball, not systems; the freshness
  pill is right there.
- **Confusing:** whether the data is **live tonight or a historical sample** is
  still the first thing a pro will wonder. The season banner ("End-of-Season
  Snapshot") is honest but easy to skim past.

## 2. Dashboard (league-wide)

Sections: League-Wide Bullpen Overview · Bullpen Snapshot · Bullpen Health ·
Usage Roles · Quick Actions.

- **Communicates purpose immediately?** Yes. The "League-Wide" framing + scope
  chip resolve the "which bullpen?" ambiguity the last audit flagged.
- **League-wide scope make sense?** Yes as an orientation layer, with Quick
  Actions drilling into a team. One caveat: on the current **sample data**, the
  aggregate health usually reads "manageable" and roles skew to
  Middle/Low/Insufficient — accurate, but low-drama.
- **Still operational/governance-heavy?** No. That content moved to Data & Trust.
- **What Trevor notices first:** the five snapshot counts and the one-line health
  statement. Good — those are the right things.

## 3. Bullpen workflow (team-specific)

Tabs: Tonight's Board · Compare Bullpens · All Pitchers · All Teams.

- **Tonight's Board** is the best screen in the product: five availability
  groups, plain-language cards, a usage-role chip with evidence, and a *Why?* on
  everything. Intuitive and genuinely useful.
- **Compare Bullpens** answers "how do these two pens stack up tonight?" cleanly,
  with both boards underneath.
- **Friction:**
  - **Four tabs, two stories.** The board + compare are the product; "All
    Pitchers" (fatigue table) and "All Teams" (30-team table) are older reference
    surfaces. They were just relabeled to stop reading as a second comparison,
    but they still split attention.
  - **No path from a board card to pitcher detail.** Cards expand to reasons/role,
    but a pitcher's fatigue *trend/detail* lives only in the All Pitchers table.
    A coach who likes an arm on the board can't click straight through to its
    history.
- **Still missing:** opponent/lineup context, handedness at a glance, and
  per-team health on the dashboard. None are blockers; all are descriptive
  additions that fit the philosophy.

## 4. Data & Trust

- **Accessible?** Yes — its own nav item and a dashboard link.
- **Too heavy?** The page itself is dense (operational readiness, V2 bullpen
  state, observations, exploratory study) and still speaks governance. But that
  is now **appropriately quarantined** — it no longer taxes the core workflow.
- **Appropriately separated?** Yes. This is the right call: summaries on the
  dashboard, depth one click away.

## 5. Recommended demo (10–15 min)

1. **Dashboard (45s):** "League-wide read — here's MLB bullpen availability
   tonight." Point at the five snapshot counts and the health line.
2. **Bullpen → Tonight's Board**, pick a team: the five availability groups.
3. **Expand one pitcher card:** availability reason + **usage role + evidence** +
   *Why?*. Emphasize that every label shows its numbers.
4. **Bullpen Health** on the board: "is this pen stressed?"
5. **Compare Bullpens** vs the opponent: side-by-side.
6. **Methodology (60s):** "every number is computed, not guessed."
7. **Data & Trust (30s):** "freshness, confidence, governance — here, not
   cluttering the workflow." Close on the honest sample-data caveat.

**Skip:** Pipeline (prototype), All Pitchers / All Teams tables, and the deep V2/
observations panels.
**Emphasize:** the board's readability, the *Why?* everywhere, and the honest
"it does not tell you who to use."

## 6. Product story

The clearest description today:

> **A bullpen availability & workload intelligence tool** — descriptive,
> transparent context for relief decisions (who's available, how stressed, how
> teams compare, what role each arm plays), explicitly **not** a recommendation
> or prediction engine.

It is no longer an "operational readiness platform." That is a win.

## 7. Remaining friction (product, not code)

- Live-vs-sample data ambiguity on first glance.
- Four bullpen tabs split focus; two are legacy reference tables.
- Board card → pitcher detail has no direct link.
- Fatigue score (0–100) has no at-a-glance legend ("higher = heavier workload").
- Data & Trust page is dense and still governance-worded (acceptable, since
  quarantined).
- Pipeline/Prospects in the nav is a distraction for a bullpen demo.

## 8. What Trevor would say

- **Praise:** "I can read this in seconds." The availability groups, the
  evidence-backed roles, and the honesty about limitations ("no injury data, no
  manager intent") land well with a pro.
- **Questions:** "Is this live or a sample?" · "What's a fatigue score — what's
  high?" · "Where do the availability thresholds come from?" · "Can I see one
  pitcher's recent trend?" · "Does it tell me who to bring in?" (No — frame as the
  point.)
- **Skepticism:** the dataset is a historical sample; coverage is modest; roles
  can read thin where save/hold/leverage data is sparse.
- **Challenge:** "Show me my team, not the league" — the dashboard is league-wide;
  per-team focus requires a click into Bullpen.

## 9. Readiness ratings

| Dimension | Rating | Why |
| --- | --- | --- |
| Portfolio readiness | **Ready** | Leads with baseball, the board is strong, methodology + trust are present and separated. Demos as a coherent product. |
| Trevor demo readiness | **Close** | Excellent with the recommended flow; held just short of Ready by the live-vs-sample framing, the four-tab split, and no board→pitcher-detail link. |
| Baseball operations usefulness | **Close** | Genuinely answers "who's available / how stressed / how do pens compare," but on sample data and without injury/role-from-real-usage depth, a working ops user sees a strong prototype. |
| Early collaboration readiness | **Ready** | The descriptive, transparent, bounded positioning is exactly right to start a real conversation. |

## 10. Top 10 remaining improvements (impact × effort)

| # | Improvement | Impact | Effort |
| --- | --- | --- | --- |
| 1 | Make live-vs-sample explicit and unmissable (a one-line "Sample data through <date> — not live" near the hero title). | High | Low |
| 2 | Link board pitcher cards → pitcher detail (fatigue trend). | High | Med |
| 3 | Consolidate the bullpen tabs: lead with Board + Compare; fold "All Pitchers"/"All Teams" under a single "Tables/Detail" affordance. | High | Med |
| 4 | Fatigue-score legend (one line wherever the score appears). | Med | Low |
| 5 | Add a "feature a team" selector on the dashboard so the league view can drill to one pen inline. | Med | Med |
| 6 | Seed a richer demo team so Bullpen Health isn't always "manageable." | Med | Med (data) |
| 7 | A short "What this is / isn't" line near the hero (descriptive, not recommendations). | Med | Low |
| 8 | Lighten the Data & Trust page: lead with plain freshness/confidence; push V2/observations lower. | Med | Med |
| 9 | Role-chip glossary/tooltip (Late / Setup / Middle / Long / Low / Insufficient). | Low–Med | Low |
| 10 | De-emphasize Pipeline in the demo nav (or tag it clearly as unrelated to bullpen). | Low–Med | Low |

Items 1–4 are the difference between a good demo and a clean one.

## 11. What should NOT be built next

- **Prediction engines** (win/save probability, injury forecast) — destroys the
  credible, honest positioning; indefensible on sample data.
- **Matchup / leverage advice** — crosses into telling a coach what to do, the
  one line the product deliberately holds.
- **Ranking / "best arm" / "closer of the night"** — already avoided by design;
  keep it descriptive.
- **Recommendation beyond current governance boundaries** — same reason.
- **League-wide analytics expansion / more governance surfaces** — scope creep
  that re-bloats the experience the realignment just cleaned up.

**Recommendation: pause feature expansion.** The product's identity is set and
strong. The next highest-leverage work is polish (items 1–4) and demo data, not
new engines.

## 12. Changes made in this audit (low-risk copy/labels only)

- `frontend/src/components/bullpen/Bullpen.jsx` — tab labels "Pitchers" → **"All
  Pitchers"**, "Team Summary" → **"All Teams"**, so the legacy reference tables
  stop reading as a second comparison surface alongside "Compare Bullpens."
- `frontend/src/components/methodology/Methodology.jsx` — subtitle "How every
  number on the dashboard was computed" → **"How every fatigue and availability
  number is computed"** (the product is no longer dashboard-only).

No behavior, data, routing, or component structure changed. The larger items
(board→detail link, tab consolidation, data framing) are left as ranked
recommendations, not implemented, to keep this an audit.

## 13. Bottom line

If Trevor opened BaseballOS today, he would understand it quickly, respect the
honesty, and lean into the bullpen board. He would ask whether it's live, want to
click from an arm on the board to its history, and notice the extra tables. None
of that is fundamental — it is finish work.

**Verdict: ready to demo with the recommended flow; one short polish pass (items
1–4) takes it from "Close" to "Ready" across the board. Hold new features.**
