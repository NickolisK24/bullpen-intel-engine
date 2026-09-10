# Today Front-Door Readiness Audit

> Audit / planning pass only. No frontend implementation, no backend logic change,
> no COIN change, no endpoint-contract change, no data-generation change, no UI
> redesign. Goal: can a user open **Today** and, within ~30 seconds, understand
> what BaseballOS sees, why it matters, the evidence, the freshness, and where to
> go deeper? Product language stays State → Why → Evidence → Freshness → Limitations.

Branch: `audit/today-front-door-readiness`
Base commit: `5fb3f19` (latest main)

## 1. Executive decision

**Today is already close to a true front door** and is correctly scoped — it leads
with the single strongest daily bullpen read, shows pregame/Tonight watch items, a
compact league teaser, and CTAs, with no dashboard/methodology/trust bloat. The
slate-vs-data-through freshness fix landed, internal language is clean, and
overclaiming risk is low. **Two concrete gaps keep it from being fully front-door
ready, both frontend-only:**

1. The flagship **Today's Story** card renders **no Limitations** leg, while the
   Tonight cards do — the most prominent card breaks the State → Why → Evidence →
   Freshness → Limitations contract.
2. **Explore (the deeper-link row) omits Dashboard and Stories** — the front door
   never routes users to the league board or the feed.

A small third item: the landscape teaser links into team boards but not to the
full league board (Dashboard). Fixing these three is a small, frontend-only pass.

## 2. Current Today inventory

Route `/` → `Home.jsx` → `IntelligenceSurfacePage` (`IntelligenceSurface.jsx`).
Data: `getTodayIntelligence`, `getTonightIntelligence`, `getBullpenLandscape`,
`getBullpenDashboard` (shared freshness), `getTeams`. Rendered order
(`IntelligenceSurfaceView`):

1. **SeesHeader** — "What BaseballOS Sees" (orienting one-liner).
2. **Today's Story** — eyebrow/title "Today's Story", "The single bullpen story
   BaseballOS saw first." (lead read from `getTodayIntelligence`).
3. **Tonight** — "Bullpen situations BaseballOS is watching before first pitch."
   (pregame cards from `getTonightIntelligence`; **Around Baseball** is the
   fallback when Tonight is empty).
4. **Today's Bullpen Picture** — landscape teaser ("rested, constrained, or worth
   monitoring") from `getBullpenLandscape`.
5. **Explore** — deeper-link cards.

## 3. Today page purpose assessment

Today functions as a daily intelligence briefing, not a card dump: a clear reading
order (orient → lead read → tonight → league teaser → go deeper), one job per
section, and honest empty/stale handling. It does **not** contain a full stat
dashboard, a team deep-dive, methodology, a trust/status surface, or a story
archive. The 30-second test is mostly met: a user sees the lead read and why,
the tonight watch items, and a league snapshot — but the lead read lacks its
limitations line, and the "where to go deeper" row is incomplete (no Dashboard /
Stories).

## 4. Section-by-section findings

- **SeesHeader** — good front-door framing; product-facing copy.
- **Today's Story** — State (headline) → Why ("Why BaseballOS Sees It" =
  observations) → Evidence ("Evidence", mono) → "Bullpen Read" block → Freshness
  ("Bullpen data through"). CTAs: team board (`story.team.href`) + "/stories".
  **Missing: a Limitations section.** Empty state honest ("No lead bullpen story
  has cleared the bar yet." / "BaseballOS is still reviewing … will only surface a
  lead story when the evidence is strong enough.").
- **Tonight** — cards follow State (signal) → Why (summary) → Evidence →
  Limitations → Freshness. Slate freshness row shows **Tonight slate** (slate
  date) separate from **Bullpen data through** (completed-game date) — correct.
  Empty/error states honest. Around Baseball fallback is distinct from the Stories
  feed.
- **Today's Bullpen Picture** — compact teaser; entries link to team boards
  (`/bullpen`/teamHref). Freshness row. Empty state honest. **Does not link to the
  full league board (Dashboard).**
- **Explore** — links: Teams (`/bullpen`), Compare (`/bullpen?view=compare`),
  Trust (`/trust`), Methodology (`/methodology`). **No Dashboard, no Stories.**

## 5. State → Why → Evidence → Freshness → Limitations gap analysis

| Card | State | Why | Evidence | Freshness | Limitations |
| --- | --- | --- | --- | --- | --- |
| Today's Story (flagship) | ✔ headline | ✔ observations | ✔ evidence | ✔ Bullpen data through | **MISSING** |
| Tonight cards | ✔ signal | ✔ summary | ✔ evidence | ✔ slate + data-through | ✔ limitations |
| Today's Bullpen Picture | ✔ rested/constrained/watch | ~ implicit | ~ counts | ✔ data-through | ~ teaser-level |

The flagship card is the one that breaks the contract. `getLeadStoryView`
(IntelligenceSurface.jsx ~302) maps `headline`, `body`, `observations`,
`evidence`, `snapshot`, `referenceDate`, `metadata` — but **not** `limitations`,
and the render has no Limitations block. Tonight's card view does map
`limitations`. Recommended fix: render a Limitations leg on the lead story — map
`draft.limitations` if the payload provides it; otherwise show the standard,
honest scope caveat already used elsewhere ("BaseballOS does not know manager
intent, bullpen phone activity, private medical availability, unreported injuries,
or final game-day decisions"). This is a true scope statement, not invented data —
frontend-only, no backend change.

## 6. Freshness / date semantics assessment

**Resolved.** The earlier slate-vs-data-through confusion is fixed: a dedicated
slate-aware freshness row renders `SlateDateStamp` ("Tonight slate") on Tonight,
separate from `DataThroughStamp` labeled "Bullpen data through", plus a Last Sync
label. Today's Story and Today's Bullpen Picture use "Bullpen data through" with
completed-game dates. No date is mislabeled. Stale state threads through
(`staleWithError` → `FreshnessBadge state="stale"`). No action needed.

## 7. Duplicate / misplaced content findings

- No methodology, trust/sync diagnostics, or full league dashboard render on Today
  (correct).
- "Around Baseball" is a **fallback** within Tonight (only when Tonight is empty)
  and shows league movement items — distinct from the Stories feed. Acceptable.
- "Today's Bullpen Picture" (teaser) vs Dashboard's full landscape is a legitimate
  teaser → full relationship; the only issue is the teaser does not link to
  Dashboard (see CTA findings).
- No duplication of Stories' feed (Today shows one lead story + a "/stories" link).

## 8. Internal-language / overclaiming findings

- **Internal language: clean.** No user-visible COIN / V2 / deterministic /
  snapshot / endpoint / backend / baseline / governance terms. The lead "Bullpen
  Read" block uses product-facing wording; `snapshot` appears only as a code
  identifier (`story.snapshot`), never as a rendered label.
- **Overclaiming: low.** Tonight cards are descriptive pregame reads (no
  predictions/betting/fantasy); the lead story is evidence-backed with no
  future-tense claims; the landscape teaser is descriptive (rested/constrained/
  worth monitoring); empty-state copy is honest about thresholds. No injury,
  manager-intent, or future-usage overclaims observed. (The one place to reinforce
  this is the missing lead-story Limitations line in §5.)

## 9. Recommended Today ownership model

Today owns: (a) the single strongest daily bullpen read (full State → Why →
Evidence → Freshness → Limitations), (b) Tonight/pregame watch items, (c) a compact
league landscape teaser, and (d) CTAs into the deeper surfaces. Today **links to,
never duplicates**: Dashboard (full league board), Bullpen (team deep-dive),
Stories (feed), Data & Trust (freshness/reliability), Methodology (definitions).
Today does not host the full dashboard, team deep-dive, methodology, trust, or the
story archive.

## 10. Recommended content to keep

SeesHeader, Today's Story, Tonight (+ Around Baseball fallback), Today's Bullpen
Picture teaser, Explore. The reading order and the slate/data-through freshness
handling stay as-is.

## 11. Recommended content to move

Nothing needs to move off Today — it is correctly scoped. (The page-hierarchy
audit already addressed cross-page placement.)

## 12. Recommended content to remove / defer

Nothing to remove. Defer: no new sections; do not add a Trend Since Yesterday card
(no trusted day-over-day state delta) and do not add team deep-dive content.

## 13. Recommended CTAs / deeper-link changes

- Add a **Dashboard** CTA (the league operating board) to Explore — currently
  absent; the front door must route to the league board.
- Add a **Stories** CTA to Explore (Today's Story links to /stories inline, but the
  deeper-link row should include it).
- Consolidate the two Bullpen links (Teams + Compare) so Explore covers all four
  destinations: Dashboard, Bullpen, Stories, Data & Trust (Methodology optional).
- On Today's Bullpen Picture, add a "full league board → Dashboard" link so the
  teaser leads to the owner of the full landscape.

## 14. Recommended next Codex implementation branch

`feature/today-front-door-polish` (frontend-only, small):

- Render a **Limitations** leg on the lead story (map `draft.limitations` when
  present; else the shared honest scope caveat). No invented facts.
- Add **Dashboard** + **Stories** CTAs to Explore (consolidate the Bullpen links);
  add the Dashboard link on the Bullpen Picture teaser.
- Tests: lead story renders a Limitations section; Explore links include Dashboard,
  Bullpen, Stories, Data & Trust; slate vs "Bullpen data through" labels
  (regression); no internal-language leak; empty/stale states unchanged.

## 15. Suggested implementation phases

- **Phase A (honesty):** add the lead-story Limitations leg (closes the State → Why
  → Evidence → Freshness → Limitations gap on the flagship card).
- **Phase B (navigation):** complete the Explore CTAs (Dashboard + Stories) and add
  the Dashboard link on the landscape teaser.
Both ship in one small branch; Phase A first.

## 16. Out of scope (do not build)

No full stat dashboard, team deep-dive, methodology, trust/status, or story archive
on Today. No predictions, betting, fantasy, prospects, or general MLB stats. No new
backend intelligence (the lead-story Limitations is an honest scope caveat /
existing-field mapping, not a new field). No new endpoints, no UI redesign, no COIN
or data-generation changes. Do not add a Trend Since Yesterday card.

## 17. Risks if this is not cleaned up

- The most prominent card (Today's Story) silently omits Limitations, undermining
  the product's honesty principle exactly where it is most visible.
- Without Dashboard/Stories CTAs, the front door strands users — there is no path
  from Today to the league board or the feed, so Today reads as a dead end rather
  than a hub.
- The landscape teaser dead-ends into team boards without offering the full league
  view, weakening the teaser → full relationship.

## Validation / status checks

- Branch starts from latest main (`5fb3f19`). ✔
- No frontend implementation made (audit doc only). ✔
- No backend logic changed. ✔
- No COIN changes. ✔
- No endpoint contract changes. ✔
- `git diff --check` / `git diff --cached --check` clean; only the audit doc staged. ✔

## Decision

Today is a genuine, correctly-scoped front door that already meets most of the
30-second test, with the slate/data-through freshness fix and clean internal
language in place. Close two frontend-only gaps to make it fully front-door ready:
add the Limitations leg to the flagship Today's Story card, and complete the
deeper-link CTAs (Dashboard + Stories, plus a Dashboard link on the landscape
teaser). No backend, COIN, contract, or data changes.

ready for Codex implementation: YES (one small frontend branch, Phase A then B).
ready to merge: this audit doc is docs-only and safe to merge; no code changed.
