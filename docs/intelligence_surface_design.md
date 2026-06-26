# Intelligence Surface — Flagship Homepage Design

> **Status:** Design only. This document specifies the new BaseballOS homepage.
> Nothing here is built yet. No components, routes, or pages are changed by this
> document. Implementation is a separate, later decision.

---

## 1. Premise

BaseballOS is no longer primarily a bullpen dashboard. BaseballOS is an
intelligence platform. The homepage is the front door to that platform, and its
only job is to answer one question within five seconds:

**"What did BaseballOS see today?"**

The page is editorial, not operational. It reads like the front page of a
thoughtful publication that happens to be powered by a deterministic engine. It
leads with a single story that mattered most, supports that story with a small
amount of evidence, and then widens out to the rest of the league in decreasing
weight. A reader who only sees the top of the page should still come away
understanding what BaseballOS is and what it noticed today.

Guiding rule for every decision below:

> Metrics support stories. Stories do not support metrics.

If a design choice adds numbers without advancing a story, the choice is wrong.

### Feel

| Quality | What it means here |
| --- | --- |
| Editorial | One lead story, generous whitespace, a clear reading order. |
| Thoughtful | Each section earns its place; nothing is there because we have the data. |
| Calm | No live tickers, no flashing, no dense grids above the fold. |
| Trustworthy | Every claim is fact-backed and traceable to evidence. |
| Intentional | Visual weight maps exactly to editorial importance. |

What this page is **not**: noisy, metric-heavy, a table dump, a control panel, or
a configuration surface.

---

## 2. Reading Order

The page is designed to be read top to bottom, with weight decreasing as you go.

1. **What BaseballOS Sees** — a one-sentence statement of what the platform does.
2. **Today's Story** — the single bullpen story that mattered most, in full.
3. **Around Baseball** — three smaller secondary observations from the rest of the league.
4. **Today's Bullpen Picture** — the league-wide availability snapshot (most available, most constrained, worth watching).
5. **Explore** — quiet entry points into the deeper product (Teams, Compare, Trust, Methodology).

The hierarchy is strict: **nothing below Today's Story is ever visually larger or
heavier than Today's Story.** Around Baseball items are smaller than the lead.
The Bullpen Picture is a compact reference strip, not a featured block. Explore is
the lightest element on the page.

---

## 3. Wireframe

Desktop (single centered column, max readable width ~ 880–960px for prose, with
the Bullpen Picture allowed to span a slightly wider band):

```
┌──────────────────────────────────────────────────────────────────────┐
│  [ sidebar nav ]   (existing, unchanged)                               │
│                                                                        │
│   ┌──────────────────────────────────────────────────────────────┐    │
│   │  WHAT BASEBALLOS SEES                                          │    │  ← Section 1 (header)
│   │  Every morning BaseballOS watches every bullpen in baseball    │    │
│   │  and surfaces the bullpen story that mattered most.            │    │
│   └──────────────────────────────────────────────────────────────┘    │
│                                                                        │
│   ── Today's Story ───────────────────────────────────────────────    │  ← Section 2 (flagship)
│   ┌──────────────────────────────────────────────────────────────┐    │
│   │  HEADLINE (largest type on the page)                          │    │
│   │  Team · "after their most recent game" framing                │    │
│   │                                                                │    │
│   │  Story — two or three sentences of narrative prose.            │    │
│   │                                                                │    │
│   │  Why BaseballOS Sees It                                        │    │
│   │   • observation                                                │    │
│   │   • observation                                                │    │
│   │                                                                │    │
│   │  Evidence                                                      │    │
│   │   Starter · Largest lead · Bullpen entry · Late runs · …       │    │
│   │                                                                │    │
│   │  Bullpen Snapshot                                              │    │
│   │   Available arms · today's standing (one quiet line)           │    │
│   └──────────────────────────────────────────────────────────────┘    │
│                                                                        │
│   ── Around Baseball ─────────────────────────────────────────────    │  ← Section 3 (secondary)
│   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐             │
│   │ Obs. headline │  │ Obs. headline │  │ Obs. headline │             │
│   │ one-line ctx  │  │ one-line ctx  │  │ one-line ctx  │             │
│   └───────────────┘  └───────────────┘  └───────────────┘             │
│                                                                        │
│   ── Today's Bullpen Picture ─────────────────────────────────────    │  ← Section 4 (league reference)
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                │
│   │ Most         │  │ Most         │  │ Worth        │                │
│   │ Available    │  │ Constrained  │  │ Watching     │                │
│   │ team · team  │  │ team · team  │  │ team · team  │                │
│   └──────────────┘  └──────────────┘  └──────────────┘                │
│                                                                        │
│   ── Explore ─────────────────────────────────────────────────────    │  ← Section 5 (navigation)
│   [ Teams ]   [ Compare ]   [ Trust ]   [ Methodology ]                │
│                                                                        │
└──────────────────────────────────────────────────────────────────────┘
```

The fold (first viewport on a typical laptop, ~768–900px tall) lands inside or
just past Today's Story. So above the fold a reader sees: the statement of what
BaseballOS is, plus the headline and opening of today's single most important
story. That alone satisfies the five-second test.

---

## 4. Component Hierarchy

Proposed component tree for the page. Names are indicative; this is structure, not
an implementation contract. Existing UI primitives (`SectionHeader`, `Divider`,
`LoadingPane`, `ErrorState`, `StaleDataNotice`, `EmptyState`, `Card`) are reused
rather than reinvented.

```
IntelligenceSurfacePage                 (route component; orchestrates data + layout)
├── SeesHeader                          (static editorial statement — Section 1)
│
├── TodaysStory                         (flagship — Section 2)
│   ├── StoryHeadline                   (headline + team + safe-time framing)
│   ├── StoryNarrative                  (the prose body)
│   ├── StoryWhySees     → reuses observation list pattern ("Why BaseballOS Sees It")
│   ├── StoryEvidence    → reuses evidence list pattern  (ordered, capped)
│   └── BullpenSnapshot                 (available arms + one standing line)
│
├── AroundBaseball                      (Section 3)
│   └── ObservationCard × 3             (smaller than TodaysStory by construction)
│
├── BullpenPicture                      (Section 4)
│   ├── PictureColumn "Most Available"
│   ├── PictureColumn "Most Constrained"
│   └── PictureColumn "Worth Watching"
│
└── ExploreRow                          (Section 5)
    └── ExploreCard × 4                 (Teams · Compare · Trust · Methodology)
```

Each data-backed section owns its own loading / empty / error / stale states so a
slow or missing data source never blocks the rest of the page. The lead story is
the only section whose absence materially changes the page (see §11, graceful
degradation).

---

## 5. Visual Hierarchy

Weight is assigned to match editorial importance, descending down the page.

| Element | Type / weight | Relative emphasis |
| --- | --- | --- |
| "What BaseballOS Sees" header | Display font (Bebas Neue), restrained; one sentence in body type beneath | Orienting, not loud |
| Today's Story headline | Largest type on the page | **Dominant** |
| Today's Story narrative | Comfortable body (DM Sans), generous line height | High |
| Why BaseballOS Sees It | Body, list, muted bullet markers | Medium |
| Evidence | Mono (JetBrains Mono) for the digits, small, quiet | Low (supporting) |
| Bullpen Snapshot | One line, muted | Low |
| Around Baseball cards | Smaller headline, one line of context each | Secondary — never exceeds the lead |
| Today's Bullpen Picture | Compact three-column reference; team names as the only emphasis | Reference |
| Explore | Quiet cards/buttons, lightest weight on the page | Minimal |

Color discipline (existing tokens): the field/dugout dark grounds the page;
`chalk100` carries prose; **amber is rationed** — reserved for the single most
important accent (the lead headline or its rule), never sprinkled across every
section. Amber everywhere reads as noise; amber once reads as intent.

Whitespace is a primary tool. The gap between Today's Story and Around Baseball
should be the largest vertical break on the page, signalling "the most important
thing is now behind you."

---

## 6. Purpose of Every Section

**1. What BaseballOS Sees (header).**
Orients a first-time visitor in one sentence. Establishes that BaseballOS is an
observer of the whole league, every morning, surfacing what mattered. This is the
"what is this" answer that makes the rest of the page legible. Fixed copy:

> Every morning BaseballOS watches every bullpen in baseball and surfaces the
> bullpen story that mattered most.

**2. Today's Story (flagship).**
The heart of the page and the proof that BaseballOS is an intelligence platform.
It is one story — the single bullpen story that mattered most across the league
today — told in full: a headline, a short narrative, the reasons BaseballOS chose
it, the evidence behind it, and the resulting bullpen standing. It carries the
most visual weight by a clear margin. Sub-parts:

- **Headline** — the one-line claim.
- **Story** — two to three sentences of narrative prose.
- **Why BaseballOS Sees It** — the observations that made this the story (the
  "why this, why today").
- **Evidence** — the ordered, capped facts that back the story (starter, lead/
  deficit, bullpen entry, turning point, late runs, key relief).
- **Bullpen Snapshot** — where that bullpen now stands (available arms, one
  standing line). Connects yesterday's game to today's picture.

**3. Around Baseball (secondary observations).**
Three smaller stories from the rest of the league — the next most notable things
BaseballOS saw, in brief. Their role is breadth: they show the platform watched
everyone, not just the lead. By construction they are smaller and lighter than
Today's Story; they are headlines with a line of context, not full stories.

**4. Today's Bullpen Picture (league reference).**
A calm, factual league-wide snapshot answering "who's fresh, who's stretched, who
to keep an eye on." Three groupings — Most Available, Most Constrained, Worth
Watching — each a short ranked list of teams. This is the one explicitly
reference-style section, and it is deliberately compact so it reads as a strip,
not a featured block. It reuses existing league intelligence rather than computing
anything new.

**5. Explore (navigation).**
Quiet doors into the deeper product for the reader who now wants more: Teams,
Compare, Trust, Methodology. It is intentionally the lightest element so it never
competes with the editorial content above it. It is a launch pad, not a feature.

---

## 7. Expected Data Source & COIN Object Per Section

This maps each section to the backend source that should power it. Where the
current public API does not yet expose what the section needs, that gap is flagged
as required implementation work (this document does not build it).

### Section 1 — What BaseballOS Sees
- **Data source:** None. Static editorial copy shipped with the page.
- **COIN object:** None.
- **Notes:** Never dynamic. The sentence is a brand statement, not data.

### Section 2 — Today's Story (flagship)
- **Conceptual source:** The COIN story pipeline — `CompletedGameContext →
  NarrativeContext → NarrativeFeed → StoryOrchestrator/StoryPackage →
  StoryWriters`.
- **COIN object:** The **`StoryPackage`** for the chosen team/game, rendered by
  the **`TeamStoryWriter`** (`StoryDraft`). Specifically:
  - Headline → `StoryDraft.headline`
  - Story → `StoryDraft.body`
  - Why BaseballOS Sees It → `StoryDraft.observations`
  - Evidence → `StoryDraft.evidence` (already ordered + capped at 5 by the writer)
  - Bullpen Snapshot → `StoryPackage` bullpen state / available arms (the same
    optionality context the morning brief uses for "Available arms: …")
- **How "the story that mattered most" is chosen:** by `StoryPackage.story_priority`
  (CRITICAL > HIGH > MEDIUM > LOW) and `game_importance`, restricted to
  `publishable` packages, across all teams for the reference date. This selection
  is league-wide ranking logic.
- **⚠ Required backend work (flag, do not build here):**
  1. The existing public team story endpoint
     (`/api/bullpen/teams/<team_id>/story`) serves the **older** story payload
     (`_story_api_payload`), **not** the new COIN `StoryPackage` with
     `evidence_blocks` and writer `drafts`. A new endpoint (e.g.
     `/api/bullpen/today` or `/api/intelligence/today`) is needed that returns the
     league-leading publishable `StoryPackage` already rendered by the writers.
  2. The "pick the single most important story across the league" ranking does not
     have a public endpoint today. It must select among per-team packages by
     priority/importance and return one. This is the central new API for the page.
- **Determinism note:** because the writers are deterministic and fact-backed,
  the same reference date always yields the same lead story — important for a
  calm, trustworthy front page.

### Section 3 — Around Baseball (three secondary observations)
- **Data source:** `what_changed_since_yesterday_public.build_what_changed_public_payload(current, prior, *, limit=6, consequence_payload=None)`.
- **Object:** the returned **`items`** list. Each item already carries
  `public_headline`, `public_summary`, `public_context`, `team_name`, rested
  counts, and `workload_added` — exactly the shape an observation card needs.
- **Selection:** take the top 3 items, **excluding** the team/game already used by
  Today's Story so the lead is not repeated. `limit=6` gives headroom to drop the
  lead and any low-signal items and still fill three cards.
- **Endpoint:** exposed today via the changes/what-changed path; confirm it is
  reachable league-wide (not only per-team) for the homepage. If only a per-team
  `changes` endpoint exists, a small league-wide aggregator endpoint is the
  required work.
- **COIN object:** This is adjacent COIN intelligence (public "what changed")
  rather than a full `StoryPackage`; it is intentionally lighter, matching its
  secondary weight.

### Section 4 — Today's Bullpen Picture (league reference)
- **Data source:** `game_context.build_landscape(records=None, reference_date=None, freshness=None, top_n=3)`.
- **Object fields:**
  - Most Available → `available_bullpens`
  - Most Constrained → `constrained_bullpens`
  - Worth Watching → `monitoring_concentration`
  - All three arrive **pre-sorted** as team lists; the page only renders them.
- **Endpoint:** `/api/bullpen/landscape` (exists today).
- **COIN object:** Landscape intelligence (not a `StoryPackage`). Reused as-is —
  the homepage computes nothing here.

### Section 5 — Explore
- **Data source:** None (static). Routes only.
- **Targets (existing routes):** Teams (`/bullpen` team list / `/teams`), Compare
  (`/teams/compare` view), Trust (`/trust`), Methodology (`/methodology`).
- **COIN object:** None.

### Source summary table

| Section | Powered by | Endpoint (today) | New work needed? |
| --- | --- | --- | --- |
| What BaseballOS Sees | static copy | — | No |
| Today's Story | COIN `StoryPackage` + `TeamStoryWriter` draft | none for new package; old `/teams/<id>/story` is the legacy payload | **Yes** — league "today's lead story" endpoint returning the rendered package |
| Around Baseball | `build_what_changed_public_payload().items` | what-changed/changes path | Maybe — confirm league-wide reach |
| Today's Bullpen Picture | `build_landscape()` available/constrained/monitoring | `/api/bullpen/landscape` | No |
| Explore | static routes | existing routes | No |

---

## 8. What Stays Below the Fold

Above the fold is reserved for "what BaseballOS is" + the lead story's headline
and opening. Everything else is deliberately below it:

- The remainder of Today's Story (full evidence list, bullpen snapshot).
- All of Around Baseball.
- All of Today's Bullpen Picture.
- All of Explore.
- **Never above the fold:** large tables, dense metric grids, multi-team
  comparisons, configuration, or anything resembling a control panel. The whole
  point of the page is defeated if the first screen looks like a dashboard.

Below-the-fold content is also where progressive disclosure lives: the lead story
shows narrative first, with evidence and snapshot beneath it for the reader who
wants the proof. The page rewards scrolling with detail, but never demands it for
comprehension.

---

## 9. Navigation Impact

- **This page becomes the new Home (`/`).** The current Home ("The Morning Bullpen
  Report") is replaced by the Intelligence Surface as the route `/` landing. The
  old report's content is not deleted by this design — its data already lives in
  other routes — but `/` no longer renders it.
- **Sidebar nav (`Sidebar.jsx`) is preserved**, sidebar-only, unchanged in
  structure. The first item ("Today") points at `/` and now lands on the
  Intelligence Surface. No new top-level nav item is required for the homepage
  itself.
- **Explore (Section 5) is a secondary, in-page navigation aid**, not a
  replacement for the sidebar. It surfaces four high-intent destinations
  (Teams, Compare, Trust, Methodology) inline for readers who scrolled the whole
  page. These targets already exist as routes; Explore just links to them.
- **No routes are removed.** Stories, Dashboard, Bullpen, Prospects, Methodology,
  Trust all remain reachable from the sidebar exactly as today.
- **Deep links:** Today's Story should link through to that team's full bullpen /
  story page; each Around Baseball card links to its team; each Bullpen Picture
  team links to that team. The homepage is an index into the platform, so every
  named entity is a door.

---

## 10. Mobile Considerations

The layout is single-column by nature, which makes mobile a graceful reflow rather
than a redesign. Existing breakpoint convention (`lg:` ≈ 1024px, hamburger below)
is honored.

- **Sidebar** collapses to the existing mobile hamburger; the page content is the
  full-width column.
- **Stacking order is the reading order** — sections stack top to bottom exactly
  as specified (§2), so editorial priority survives on a phone.
- **Today's Story** stays the visual anchor; its headline scales down but remains
  the largest type. Evidence (mono) wraps to its own lines and stays compact.
- **Around Baseball** three cards stack vertically (1-up), still smaller than the
  lead.
- **Today's Bullpen Picture** three columns stack vertically (1-up) into three
  short labeled lists. No horizontal scrolling, no wide tables.
- **Explore** four cards become a 2×2 grid or a vertical stack of full-width
  buttons.
- **Touch targets** for every link/card meet comfortable tap sizing; team names
  are tappable.
- **Performance:** sections load independently; on a phone connection the lead
  story should render first and not be blocked by the landscape or what-changed
  calls.

---

## 11. Accessibility Considerations

- **Semantic landmarks & order:** the DOM order equals the visual/reading order, so
  screen-reader and keyboard users traverse the page in the intended priority. Use
  a single `<h1>` (the "What BaseballOS Sees" intent or the page title), `<h2>` per
  section, `<h3>` for the lead headline and card headlines — a clean heading
  outline that lets assistive tech jump section to section.
- **Each section is a labeled region** (`<section aria-labelledby=…>`) so "Today's
  Story," "Around Baseball," "Today's Bullpen Picture," and "Explore" are
  navigable as regions.
- **Color is never the only signal:** amber accent and dark grounds must clear
  WCAG AA contrast for body and large text; the lead story is distinguished by
  size, position, and a heading — not color alone. Constrained vs. available in
  the Bullpen Picture is conveyed by its column label and text, not just hue.
- **Evidence in mono** must remain real text (not an image), legible at its small
  size, and meet contrast against the dark ground.
- **Links have discernible names:** "Read more about the Giants," not "read more";
  card links announce the team and what the link does.
- **Loading / empty / error / stale states** are announced politely
  (`aria-live="polite"`), reusing the existing `LoadingPane` / `ErrorState` /
  `EmptyState` / `StaleDataNotice` primitives so status is perceivable without
  sight.
- **Graceful degradation = accessible degradation:** if the lead story is
  unavailable (no publishable package today), the page shows an honest, readable
  fallback ("BaseballOS is still watching today's games") rather than an empty
  hero — never a silent blank. Secondary sections that fail independently collapse
  to their empty states without breaking the page.
- **Focus management & motion:** keyboard focus is visible on every interactive
  element; any transition is subtle and respects `prefers-reduced-motion`
  (consistent with the "calm" mandate — there should be little motion to begin
  with).

---

## 12. Potential Future Expansion

The page is designed so the platform can grow without redesigning the front door.

- **More than bullpens.** "What BaseballOS Sees" is intentionally broader than
  relief pitching. As the engine gains rotation, lineup, or roster intelligence,
  Today's Story can draw from any domain while the page structure holds. The
  header copy can generalize ("watches every bullpen" → "watches every team")
  when that day comes.
- **Personalization.** A signed-in reader could see "your team's story" promoted
  into or alongside the league lead, without changing the section model.
- **Story archive / "On this date."** Because stories are deterministic and
  fact-backed, a date picker could let readers walk back through past lead stories
  — a natural "Stories" archive seeded by the same `StoryPackage` history.
- **Depth on demand.** Today's Story could expand inline to reveal the full
  `evidence_blocks` and the dashboard/morning-brief renderings of the same package
  — multiple voices of one story — for readers who want to go deeper.
- **More secondary lanes.** Around Baseball could gain a toggle (e.g. "biggest
  swings" vs. "quietest nights") drawing on different `what_changed` slices,
  staying within its secondary weight.
- **Richer Bullpen Picture.** The landscape strip could gain a fourth lane or a
  small sparkline of league-wide freshness over recent days — still reference, not
  featured.
- **Editorial cadence.** A future "evening edition" could re-rank the lead after
  the day's games complete, reusing the same selection logic with a later
  reference time, never breaking the safe-time framing the writers already
  enforce.

The invariant across all expansion: **one lead story, decreasing weight beneath
it, metrics in service of stories.** New capability is added by feeding the same
structure, not by crowding it.

---

## 13. Out of Scope (for this document)

- No components are built. No routes are changed. No existing page is redesigned.
- The new "today's lead story" league endpoint and any league-wide what-changed
  aggregator are **flagged as required work**, not implemented here.
- Visual design tokens are referenced (existing Tailwind theme) but no new tokens,
  fonts, or CSS are introduced.

Next step after approval: a separate implementation plan that begins with the
backend endpoint for Today's Story (the one genuine gap), then the page shell, then
each section against its confirmed data source.
