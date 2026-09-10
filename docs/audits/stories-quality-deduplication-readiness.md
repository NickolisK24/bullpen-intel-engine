# Stories Quality & Deduplication Readiness Audit

> Audit / planning pass only. No frontend implementation, no backend logic change,
> no COIN change, no endpoint-contract change, no data-generation change, no UI
> redesign. The question: can a first-time or returning user open **Stories** and
> understand what bullpen stories are developing, why each matters, the evidence,
> how fresh it is, whether it is live or review-only, how Stories differs from
> Today, and why these stories are worth showing — i.e. is Stories ready to be the
> deeper, selective, non-repetitive, trustworthy bullpen intelligence feed?

Branch: `audit/stories-quality-deduplication-readiness`
Base commit: `2e1d7a8` (latest main; includes the merged Team Board operating-report
completeness and sync-cadence trim)

## 1. Executive decision

**Stories is close to ready and is built on the right foundation, but it stops one
contract leg short and does not yet distinguish live from review-only data.** It
renders a single canonical story feed (`dashboard.stories`) that is already
selective server-side — suppressed and weak stories are filtered out, each team
yields at most one story, and a feed-level variety pass de-duplicates repeated
Evidence wording across cards. Each card carries a real State → Why → Evidence
teaching blueprint in descriptive, public-safe, baseball-facing language, with
honest loading/error/stale/empty states and a guaranteed league-note floor on quiet
days. **Three frontend-only gaps keep it from being fully ready, and the backend
already provides the data for the first two:**

1. **Per-story Freshness and Limitations are dropped by the frontend adapter.** The
   canonical payload carries `freshness`, `limitations`, and `quality_status` on
   every item, but `toFeedCard` discards them and hardcodes `disclosureNote: null`.
   Cards therefore complete State → Why → Evidence but omit **Freshness → Limitations**.
2. **No live-vs-review distinction is surfaced.** `getMastheadView` computes `isLive`
   but the Stories masthead never renders it, and `quality_status: 'review'` items
   look identical to published ones. The page cannot tell the user "this is live MLB
   data" vs "review-only."
3. **Today-vs-Stories overlap is real but unmanaged.** Stories' first cards are the
   same top stories Today shows as "Three Things To Watch" (same source, same order),
   and Today's flagship lead can reappear as a Stories card — risking "the same story
   twice" across surfaces.

None require new backend intelligence. Closing them is a small, frontend-only pass.

## 2. Current Stories inventory

Route `/stories` → `Stories.jsx` → `StoriesView`. Data: `getBullpenDashboard()`
(`/api/bullpen/dashboard`), read as `dashboard.stories`. Rendered order:

1. **Masthead header** — "The Bullpen Intelligence Feed" / "BASEBALLOS STORIES", a
   freshness chip (`masthead.dataLine`), a "Descriptive bullpen notes." badge, and a
   one-line purpose statement ("What else BaseballOS is seeing today…").
2. **FeedScope** ("What Else BaseballOS Is Seeing") — count of storylines, a "Back to
   Today" link, and lane chips (Pressure / Watch / Rest / League) with counts.
3. **Story Feed** — filter buttons (All / Pressure / Rest / Watch / League) with
   counts, an active-filter label + description, then a grid of `FeedStoryCard`s.
4. **Per-card** — tone bar, team label (or "Around the league"), a continuity read
   badge (New / Updated), a `TeamShareButton`, the headline, a collapsible
   `StoryBlueprint` (or flat narrative), a `StoryDisclosureNote`, and a Team Board CTA.
5. **Empty state** — honest per-filter copy with a "Show All Stories" reset.

## 3. Stories page purpose assessment

Stories reads as the browseable, deeper feed, not a second front door: it explicitly
frames itself as "beyond the morning briefing," links back to Today, and lets the
user pick a lane or read everything. It is not a team deep-dive (cards link out to the
team board rather than embedding it), not a methodology page, and not a trust/status
page. The 30-second test is mostly met — a user sees what is developing, can filter by
lane, and reads State → Why → Evidence per story — but cannot see per-story freshness
or limitations, and cannot tell live data from review-only.

## 4. Story source / payload assessment

Single canonical source: `dashboard.stories`, mapped by
`storiesCanonicalFeedView.getCanonicalStoryFeed`. Home/Today read the **same** feed
via `homeCanonicalStoriesView` (top 3 as "Three Things To Watch"), so there is one
story source of truth, not two engines. The backend item shape (`services/story_feed.py`)
carries, per item: `story_available`, `story_type`, `category`, `tone`, `headline`,
`narrative`, `beats`, `blueprint` (5 teaching sections), `continuity`, **`freshness`**,
**`limitations`**, and **`quality_status`** (`published` / `review` / `suppressed` /
`neutral`), plus a feed-level `league_context` and `FEED_LIMITATIONS`. The frontend
adapter maps headline/narrative/blueprint/continuity/tone/category/team href — and
**drops `freshness`, `limitations`, and `quality_status`** (`disclosureNote` is always
`null`). The data needed to complete the contract is present in the payload; the UI
simply does not read it.

## 5. Section-by-section findings

- **Masthead** — descriptive framing and a "data through" chip; good. Does not surface
  `isLive` (computed but unused) or any live/review note.
- **FeedScope** — orienting counts + lane chips + Back-to-Today; clean, public-facing.
- **Filters** — All / Pressure / Rest / Watch / League map to `category`; counts and
  honest per-filter empty copy. Good.
- **FeedStoryCard** — State (`what_everyone_saw`) → Why (`what_baseballos_noticed`) →
  Evidence (`evidence`) → why-it-matters (+ "tomorrow") via the collapsible blueprint;
  continuity badge; team/league label; share + Team Board CTA. **No Freshness leg, no
  Limitations leg** (disclosure note is always null on canonical cards).
- **League note card** — renders every day (quiet-day floor); descriptive league read.
- **Empty/loading/error/stale** — honest and distinct (see §14).

## 6. State → Why → Evidence → Freshness → Limitations gap analysis

| Leg | Source | Rendered on Stories card? |
| --- | --- | --- |
| State (what everyone saw) | blueprint `what_everyone_saw` | ✔ |
| Why (what BaseballOS noticed) | blueprint `what_baseballos_noticed` | ✔ |
| Evidence | blueprint `evidence` (+ why_it_matters / tomorrow) | ✔ |
| Freshness | item `freshness` / dashboard `data_through` | **page masthead only; not per story** |
| Limitations | item `limitations` / `FEED_LIMITATIONS` | **MISSING (disclosureNote hardcoded null)** |

State → Why → Evidence is honored per card. Freshness exists only as a single
page-level "data through" chip, and Limitations are not surfaced at all despite being
in the payload. Because every card shares one slate, the cleanest fix is page-level
(one freshness stamp + one limitations strip) rather than repeating a line on every
card — see §20/§22.

## 7. Duplicate / repeated-story findings

Server-side de-duplication is already strong: (a) each team yields at most one story,
so the feed cannot show the same club twice; (b) suppressed/weak stories become neutral
items and are filtered out by `story_available === true`, so no duplicate or filler
team cards; (c) `services/story_feed_variety_v1.apply_feed_variety` de-duplicates the
Evidence "meaning" sentence and high-visibility phrasing across the ordered feed, so
repeated wording structures are actively reduced. The one residual is **cross-surface**:
the same stories appear on Today (top 3) and Stories (full), and Today's flagship lead
(separate endpoint) can also appear as a Stories card — see §8.

## 8. Today-vs-Stories separation assessment

Today and Stories share `dashboard.stories`: Today shows the **top 3** as "Three Things
To Watch" with a "Open Stories for more observations" CTA; Stories shows the **full**
feed with filters. That is a legitimate teaser → full relationship and the right
single-source design. Two overlap risks: (1) the first three Stories cards are exactly
Today's three watch cards (same order), so a user arriving from Today sees the same
three first; (2) Today's flagship "Today's Story" comes from a **different** endpoint
(`/intelligence/today`) and is not de-duplicated against the canonical feed, so the same
team/angle can appear as both Today's flagship and a Stories card ("same story twice").
Recommend a light client-side de-emphasis (skip or down-rank a Stories card that matches
the flagship team + story type) — no backend change, the IDs/teams are already present.

## 9. Dashboard-vs-Stories separation assessment

No meaningful duplication. Dashboard renders the league operating board (landscape
columns of team availability state); Stories renders narrative storylines. They draw
different shapes from the same dashboard payload — Dashboard the league board, Stories
the `stories` feed — and serve different jobs (operating board vs developing feed).
Stories does not reproduce the landscape columns or team-state tiles. No action needed.

## 10. Story eligibility assessment

Eligibility is enforced server-side and is appropriately conservative. A team only
yields a rendered card when `story_available` is true; otherwise the engine emits a
neutral, clearly-suppressed item (with a `suppression_reason`) that the frontend does
not render. Positive rest/depth beats that are not yet supported in public voice are
flagged `quality_status: 'review'` with a `POSITIVE_BEAT_LIMITATION` rather than shown
as confident claims. The league note provides a guaranteed non-empty floor so the page
is useful on quiet days without forcing weak team cards. This is the right model — the
page does not force a card per team.

## 11. Story quality gate assessment

A real multi-stage gate exists: suppression (no story → neutral/filtered), quality
status (`published` / `review` / `suppressed` / `neutral`), per-item `limitations`,
feed-level variety de-duplication, and an editorial review log
(`editorial_review_v1.review_canonical_feed`, fault-isolated). The gap is that the gate's
**review** signal does not reach the UI: a `review` item renders identically to a
`published` one, so a not-yet-trusted story is presented with full confidence. Surfacing
the published-vs-review distinction (in baseball-facing language) is the main quality-gate
follow-up — and it is a render of an existing field, not new intelligence.

## 12. Public-language safety assessment

Copy is backend-authored and descriptive; the page badge ("Descriptive bullpen notes.")
sets non-prediction framing. Kickers are baseball-facing ("Carrying The Load", "Same Few
Arms", "Thin Margin", "Fragile Bridge", "More Options", "Route Change"). Continuity reads
are factual ("New" / "Updated"). No COIN / V2 / deterministic / snapshot / endpoint /
backend / baseline / governance terms render. Two items to verify in implementation:
(a) the **"Trust Lane"** kicker / trust-lane category should be confirmed to read as
baseball language and not engine jargon (the Team Board audit deliberately kept
"Trust Arm / Trust-Lane Pressure" off the public card); (b) if per-item `limitations`
are surfaced, render only the public-safe limitation text, never `quality_status` raw
values or `suppression_reason`. With those guards, public/social copy is safe with
minimal editing.

## 13. Freshness / date semantics assessment

The masthead shows a single completed-games "data through" line (`completedGamesDataLine`),
which is correct and not mislabeled. But freshness is **page-level only** — individual
cards carry no freshness leg even though the payload provides per-item `freshness`. Since
all cards share one dashboard slate, a single prominent freshness stamp (data-through +
last-sync + a live/not-live note) is sufficient and preferable to per-card repetition.
No date is mislabeled; the gap is completeness (no live/review note) and the missing
per-story contract leg, not incorrect semantics.

## 14. Empty / stale / unavailable / sample-state assessment

Honest and layered: `LoadingPane` while first loading, `ErrorState` (with retry) when
there is no data, a `StaleDataNotice` banner when `staleWithError`, and distinct
per-filter empty copy (`FEED_EMPTY_COPY`) with a reset to All. The league-note floor
keeps "All" useful on quiet days. The missing piece is **sample/review state**: there is
no baseball-facing "Not live MLB data" / review-only note when the data is sampled or a
story is `review` quality. `isLive` is computed in the masthead view-model but never
rendered. Surfacing a single honest live/not-live note closes this.

## 15. Internal-language / overclaiming findings

- **Internal language: clean** in what renders. The risk is in the *unrendered* fields
  if they are surfaced carelessly — `quality_status` (`review`/`suppressed`),
  `suppression_reason`, and `source` must never be shown raw; surface only public-safe
  `limitations` text and a baseball-facing review note. "Trust Lane" to be confirmed.
- **Overclaiming: low.** Stories are descriptive and past/present-tense; the blueprint's
  "why it matters tomorrow" is framed as continuation, not a forecast; continuity is a
  structured day-over-day **story-type** delta, not a predicted outcome. No betting,
  fantasy, injury, medical-availability, manager-intent, or future-usage claims. The
  engine conservatively flags unsupported positive beats for review rather than asserting
  them. Keep the "why it matters tomorrow" copy descriptive when surfaced.

## 16. Recommended Stories ownership model

Stories owns the **selective, evidence-backed developing bullpen feed**: the full set of
publishable storylines (one per team, plus the league note), browseable by lane, each
with State → Why → Evidence → Freshness → Limitations and a clear live/review signal,
linking out to the team board. Stories **links to, never duplicates**: Today (front
door / flagship), Dashboard (league board), Bullpen (team deep-dive), Data & Trust
(freshness/reliability), Methodology (definitions). Stories does not host the landscape,
the flagship lead selection, team deep-dive content, methodology, or trust/status.

## 17. Recommended content to keep

The canonical single-source feed, the lane filters + counts, the FeedScope orientation,
the collapsible State→Why→Evidence blueprint, the continuity badge, the team-board CTA,
the share button, the league-note floor, and all current empty/stale/error handling.
The reading order (orient → filter → feed) stays.

## 18. Recommended content to move

Nothing needs to move off Stories. The flagship lead stays owned by Today (Stories
should de-emphasize the matching card, not adopt the flagship). Team deep-dive stays on
the team board (cards link out, correctly).

## 19. Recommended content to remove / defer

- **Defer** any "Trend Since Yesterday" *state* card: there is no trusted day-over-day
  **state** delta. The existing continuity badge (New/Updated/Ongoing) is a descriptive
  **story-type** delta and is acceptable as-is — do not escalate it into better/worse-than-
  yesterday state language.
- **Remove** nothing currently rendered. (Do not strip the league note — it is the
  quiet-day floor.)
- Do **not** add per-card repeated freshness lines; prefer one page-level stamp (§20).

## 20. Recommended duplicate suppression model

Keep and rely on the existing server-side model (one story per team; suppressed items
filtered; `apply_feed_variety` for wording). Add one **cross-surface** client guard:
when rendering Stories, down-rank or skip a team card whose `teamId` + `storyType`
matches Today's flagship lead, so the same story does not headline Today and also lead
Stories. This is a presentation-order tweak using fields already on the cards — no new
backend, no change to the feed contract.

## 21. Recommended story eligibility model

No change to the backend eligibility logic (it is correctly conservative). The only
frontend addition is to **honor `quality_status`**: render `published` stories normally
and visually mark `review`-quality stories with a small, baseball-facing "still
reviewing" note (and continue to omit `suppressed`/`neutral`). This makes the existing
gate visible instead of flattening review into published.

## 22. Recommended CTA / deeper-link changes

- Keep the per-card **Team Board** CTA and the **Back to Today** link.
- Add a single page-level **freshness stamp** (data-through + last-sync + a live/not-live
  note) near the masthead, reusing the shared Freshness primitives.
- Add a single page-level **Limitations strip** ("What these notes don't include …")
  sourced from the feed's public limitations, so the page closes the contract without
  per-card clutter.
- Optionally add a **Data & Trust** link from the freshness stamp (freshness/reliability
  owner), consistent with the rest of the platform.

## 23. Recommended next Codex implementation branch

`feature/stories-feed-trust-completeness` (frontend-only, small):

- Map `freshness` and `limitations` through the canonical adapter (stop hardcoding
  `disclosureNote: null`); render a page-level freshness stamp + limitations strip.
- Surface a baseball-facing **live / not-live** note from `masthead.isLive` (and the
  freshness `sample` flag), and a small **"still reviewing"** marker for
  `quality_status === 'review'` stories.
- Add the cross-surface de-emphasis of the card matching Today's flagship lead.
- Tests: cards show freshness + limitations; review stories are marked and published are
  not; live/not-live note renders from freshness; flagship not duplicated as the lead
  Stories card; no internal-language leak (assert against COIN/V2/quality_status/
  suppression_reason/source); empty/stale unchanged.

## 24. Suggested implementation phases

- **Phase A (honesty/contract):** map freshness + limitations and render the page-level
  freshness stamp and limitations strip — closes the State→Why→Evidence→**Freshness→
  Limitations** gap.
- **Phase B (trust signal):** surface live/not-live and the review marker (`quality_status`).
- **Phase C (separation):** de-emphasize the Stories card matching Today's flagship.
Ship A→B→C in one small branch; Phase A first.

## 25. Out of scope (do not build)

No new backend story intelligence (every recommendation renders an existing payload
field). No social automation, no public-posting workflow, no scheduling. No Trend Since
Yesterday state card (no trusted state delta). No predictions, betting, fantasy,
prospect, medical, manager-intent, or generic-MLB-news content. No new endpoints, no
endpoint-contract change, no data-generation change, no COIN change, no UI redesign.
Stories must not become a second Today, a Dashboard clone, a team deep-dive, a
methodology page, a trust/status page, or an automated pile of every possible story.

## 26. Risks if this is not cleaned up

- **Honesty gap on the deepest surface:** cards assert State → Why → Evidence with no
  freshness or limitations, exactly where the product promises "show your work."
- **Live vs review ambiguity:** a `review`-quality story renders with full confidence,
  and sampled data is not flagged — the page can imply more certainty than the data
  supports.
- **"Same story twice":** Today's flagship reappearing as the lead Stories card makes the
  feed feel redundant rather than deeper.
- **Latent internal-language leak:** the moment limitations/quality are surfaced without a
  whitelist, `quality_status` / `suppression_reason` / `source` could leak — must be
  guarded in the same pass.
- None are correctness failures (the feed is selective, de-duplicated, and descriptive);
  they are trust-completeness gaps that keep Stories from feeling fully selective,
  non-repetitive, and trustworthy.

## Validation / status checks

- Branch starts from latest main (`2e1d7a8`). ✔
- No frontend implementation made (audit doc only). ✔
- No backend logic changed. ✔
- No COIN changes. ✔
- No endpoint contract changes. ✔
- No data-generation changes. ✔
- `git diff --check` / `git diff --cached --check` clean; only the audit doc staged. ✔

## Decision

Stories is built on the right foundation to be the deeper bullpen intelligence feed: a
single canonical, server-side-selective, de-duplicated feed with per-card State → Why →
Evidence, descriptive public-safe copy, and honest empty/stale states. Close three
frontend-only gaps — surface per-story Freshness + Limitations (already in the payload),
distinguish live from review-only, and de-emphasize the card that duplicates Today's
flagship — to make it feel selective, non-repetitive, and trustworthy. No backend, COIN,
contract, or data changes.

ready for Codex implementation: YES (one small frontend branch, Phase A → B → C).
ready to merge: this audit doc is docs-only and safe to merge; no code changed.
