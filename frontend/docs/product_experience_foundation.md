# BaseballOS Product Experience Foundation

Frontend-only reference for the shared visual system, the reusable intelligence
primitives, and the Today edition hierarchy. It records what exists and which
rules the components enforce; it does not define product policy. The canonical
authorities remain `docs/canonical/03_PRODUCT_EXPERIENCE_STANDARD.md` (surface
missions, hierarchy, vocabulary presentation, accessibility) and
`docs/canonical/02_BULLPEN_INTELLIGENCE_STANDARD.md` (what may be claimed).

## Layer A — design tokens

Tokens live in two mirrored places and must stay in sync:

- `tailwind.config.js` → `theme.extend` (utility classes)
- `src/index.css` → `:root` custom properties (`--bos-*`) and the `.bos-*`
  component classes

| Group | Tokens |
|---|---|
| Surfaces | `ink` (`#0B0F14`), `panel` (`#10161E`), `panel-2` (`#141C26`) |
| Borders | `line-quiet` (`#171E27`), `line` (`#232C38`), `line-strong` |
| Accents | `signal` (`#5B8CD6`), `brass` (`#C9A96A`), state hues |
| Focus | `focus` |
| Spacing | `4`, `8`, `12`, `18`, `26`, `36`, `44`; `24px` desktop gutter; `44px` desktop / `30px` mobile section rhythm |
| Radii | `edge`, `panel`, `control` (all square: `0`) |
| Shadows | `panel`, `edition` — both `none`; borders and surface contrast carry structure |
| Breakpoint | `xs: 390px`, alongside the existing Tailwind scale |

The legacy `field` / `dugout` / `chalk` / `dirt` / `amber` palette is unchanged.
The new tokens are additive so surfaces can migrate individually rather than in
one sweep.

Typographic levels (`src/index.css`): `.bos-eyebrow`, `.bos-kicker`,
`.bos-hero`, `.bos-lead-headline`, `.bos-section-title`, `.bos-card-title`,
`.bos-body`, `.bos-support`, `.bos-evidence`, `.bos-meta`, `.bos-micro`,
`.bos-value`.

Face assignment is the rule that keeps the product editorial rather than
operational:

- **Archivo Narrow** carries display levels — headlines, section titles, card
  titles, and short editorial marks.
- **IBM Plex Sans** carries body, support, evidence, buttons, and navigation.
- **IBM Plex Mono** is reserved for values that benefit from precision:
  `.bos-meta` and `.bos-value` (dates, times, counts, provenance, timestamps).
The font request matches the approved design reference directly. No component
owns an alternate typography system.

Structure classes: `.bos-page` / `.bos-page--reading` (frame and measure),
`.bos-section` (rhythm plus a hairline between sections), `.bos-open` and
`.bos-marker` (grouping without a container), `.bos-panel` (reserved for
discrete units), `.bos-rule`, `.bos-edition` / `.bos-edition-rule` and
`.bos-intelligence-rule` (the blue-to-gold signature rule), `.bos-action--primary` /
`--quiet`, `.bos-link`, and `.bos-skip-link`.

The outer shell is `1360px` maximum with `24px` desktop gutters. Reading
surfaces use a `1160px` maximum, prose uses `66ch`, and long definitions use
`76ch`. The public masthead is `62px` high. Mobile controls are at least `46px`.

### Flat surface discipline

Foundations has no decorative noise, radial glow, contour illustration, or
component shadow. `.bos-depth` remains as a compatibility class for migrated
callers but its pseudo-elements are disabled. Surface contrast, whitespace, and
one-pixel hairlines create hierarchy.

### Container discipline

Most regions have no container. A hairline plus spacing groups them. `bos-panel`
is used only where a boundary carries meaning: slate cards (discrete game
reads) and since-yesterday cards (comparison units). Non-loading quiet,
withheld, and unavailable states use a two-pixel left rule; only loading uses a
skeleton panel.

Motion is limited to state changes and is disabled entirely under
`prefers-reduced-motion: reduce`.

Contrast: `tests/accessibilityContrast.test.mjs` pins every text and accent
token at WCAG AA or better against every surface token.

## Layer B — intelligence primitives (`src/components/intel/`)

All of these render supplied values only. None derives a state, a score, a
ranking, or an explanation, and none rewrites backend-owned copy.

| Component | Purpose | Data authority |
|---|---|---|
| `EditionHeader` | Daily edition masthead: nameplate, dateline, governed fact bar | caller, from served application state; a fact with no value is omitted, and the dateline disappears when no represented date was served |
| `IntelSection` / `SectionHeading` | Section heading system (eyebrow, title, orientation line, aligned action) | none — layout only |
| `TeamStateChip` / `TeamStateRead` | Canonical Fresh / Stretched / Vulnerable presentation, as toned text with a dot rather than a filled pill | `adapters/publicTeamState.js` → backend Team State block |
| `EvidenceList` / `EvidenceRow` / `NamedArmReceipt` | Indexed `E1`, `E2` evidence receipts with a 22px index column, vertical hairline, and named-arm evidence | the contract that supplied the row; the index is presentation order only |
| `TrustStrip` / `TrustFact` | Ambient freshness and trust stamps | governed freshness block |
| `ConceptCard` / `ConceptGlossary` | BaseballOS vocabulary | `utils/bullpenConcepts.js` |
| `ConceptGlyph` | Abstract concept marks for the vocabulary | none — fixed geometry, decorative |
| `IntelNotice` / `IntelSkeleton` | Designed quiet, limited, unavailable, and loading states | caller-supplied governed copy |

Rules the primitives enforce:

- a Team State renders only when the backend block is `available` **and** the
  code/label pair is canonical; anything else falls closed to the governed
  non-state message and the neutral tone;
- state is always readable as text with a screen-reader `Team State:` prefix —
  colour is decoration;
- a trust fact with no value renders nothing rather than a placeholder;
- a concept card never carries a value, tier, or percentage;
- a concept glyph is fixed geometry with no numeric input, is `aria-hidden`, and
  is hand-authored inline SVG — no icon library, no bundle weight beyond the
  markup. It cannot become a gauge, meter, ring, or rating, and the concept name
  always carries the meaning as text.

## Layer C — application shell

The public shell is a **horizontal masthead**, not a left rail. A rail made the
product read as an internal analytics tool; a masthead reads as a publication
and gives the reading column the full page.

- `App.jsx` adds a skip link into `<main id="main-content">` and carries no
  content offset — nothing is inset for a side column.
- `components/Sidebar.jsx` (historical path; the component is the masthead)
  renders one low-profile bar: wordmark left, primary destinations centre, the
  ambient data-through stamp right, and a menu toggle below `lg`.
- The masthead is **not sticky**. Today is a finite daily edition read top to
  bottom, and a persistent bar would take vertical space on every scroll.
- `MASTHEAD_NAV` in `utils/navigation.js` selects the six destinations the
  desktop bar shows: Today, Dashboard, Bullpens, Stories, Methodology,
  Data & Trust — the canonical public lane names from
  `docs/canonical/03_PRODUCT_EXPERIENCE_STANDARD.md` section 5. Only the
  `label` changed; `key`, `to`, and the `view` query behaviour are untouched,
  so no URL moved. `masthead: false` on Compare and Reliever Finder, and
  `masthead: true` on Methodology and Data & Trust, are presentation flags only
  — no route is removed, and every destination is in the mobile menu sheet.
- Active destination: a thin blue underline plus `aria-current="page"`. Never a
  filled tab, never a pill, never colour alone.
- Below `lg`: a compact header plus a menu sheet holding every destination and
  the freshness card. Escape, route-change, and select-to-close all still close
  it.
- Navigation stays visually quiet — content is the product.

## Layer D — Today

Rendered order in `IntelligenceSurfaceView`:

1. Edition masthead (`EditionHeader`) — the single `<h1>`
2. Today's Bullpen Picture — league overview (`#bullpen-picture`)
3. What changed across MLB bullpens (`#since-yesterday`)
4. Tonight's Bullpen Watch (`#tonight`)
5. How BaseballOS describes a bullpen (`#vocabulary`)
6. How current this read is (`#data-and-trust`)
7. What BaseballOS is for (`#what-baseballos-is-for`)
8. Other views (`#continue-exploring`) — a `<nav>`, not a section

Those are the six landmark sections plus the brief and the closing row.
`tests/productExperienceFoundation.test.mjs` pins the list as a closed set, so
a seventh region cannot appear without a deliberate contract change. `#since-
yesterday` is the one region that withholds itself when the dashboard supplies
no comparison; every other section always renders.

Sections 2–4 keep the order and the data contracts they already had. The rest
are presentation over existing governed values.

### The masthead is a nameplate, not a hero

Today used to open with a value proposition as its `<h1>` ("See which bullpens
are fresh, stretched, or vulnerable tonight — and why."), a paragraph explaining
how the product works, and two calls to action. That is a landing page. It
argued for the product in the position where a daily edition states what day it
is and then reports the baseball, and on every viewport it pushed the League
Picture — the first real read — off the opening screen.

The masthead now carries only what a masthead owes the reader:

- **Nameplate** — "Today's Bullpen Edition", the `<h1>`, an identity rather than
  a claim.
- **Dateline** — the baseball date the edition represents, preferring the
  served slate date and falling back to the completed date the bullpen picture
  is built from. It is derived from a served value through
  `formatDateOnly(..., { weekday: true })` and a UTC instant, so no local
  timezone can shift the day.
- **Fact bar** — the governed freshness facts, full width beneath the dateline
  rather than as a right rail. With the left column reduced, the old two-column
  grid left a column of dead space the height of the rail before the first read.

Nothing on the Today path reads the clock: `tests/productExperienceFoundation
.test.mjs` pins that neither `new Date()` nor `Date.now()` appears in the
surface, the intel primitives, `utils/dateDisplay.js`, or `UI/Freshness.jsx`.
That is the defence that survives refactoring — there is no code path in which a
stale read can acquire a fresh-looking date.

The product statement keeps its own region further down the page, where it no
longer outranks the day's baseball. The two calls to action are gone: the league
board is reachable from the end of the League Picture and from the masthead, and
an anchor to the next section on the same page was not doing work the scroll was
not already doing.

### League lanes cannot impersonate a Team State

The three League Picture lanes were titled "Room to Maneuver", "On Watch", and
"Limited Late-Inning Margin" — short capitalised noun phrases, the same
grammatical shape as Fresh / Stretched / Vulnerable, rendered at heading weight
directly above a club name and that club's canonical state chip. Read quickly,
they were a fourth, fifth, and sixth team state.

Two changes, both in `components/dashboard/bullpenLandscapeView.js` and the
Today rendering:

- the titles are now descriptive clauses — "Where arms are rested", "Where
  recent work is worth watching", "Where late-inning margin is thin" — which
  cannot be mistaken for a state label;
- on Today the lane label renders in `.bos-micro`, the quietest text in the
  column, so the state chip is the only state-shaped thing in it.

"On Watch" remains canonical public vocabulary at the **arm** altitude and is
unchanged everywhere it describes an arm. It simply stops doubling as a league
lane title. The Dashboard inherits the renamed lanes from the same module, which
is the point — one lane vocabulary, not two.

Today used to carry two navigation blocks: a four-up "Where do you want to go
next?" grid between the league picture and what changed, and a four-up "Learn &
Explore BaseballOS" grid at the bottom. Both are removed. The first interrupted
the reading path at its strongest point — the reader had just been told what
the league looks like and was immediately asked to leave. The second duplicated
the footer. The masthead owns Today, Dashboard, Bullpens, Stories,
Methodology, and Data & Trust; the footer owns About, How to Read, Methodology,
and Data & Trust. Compare and Reliever Finder are the only working views
neither carries, so they are the whole of `#continue-exploring`: one labelled
`<nav>` with two text links, below the product statement, with no heading and
no grid.

Tonight's collapsed card is the answer only — club, headline, the supported
summary, and the watch point. Everything inspectable sits behind **one** native
`<details>`: the exact supplied evidence rows, verbatim and in order, then the
schedule sentence, Why It Matters, Key Note, and Starter Length. There is no
nested disclosure.

The disclosure label names the supplied evidence count ("View evidence and
context (2)"). That count is the length of the served evidence array and nothing
else — no evidence is summarized, ranked, or paraphrased, and with no evidence
the label falls back to "More on this read" rather than inventing a count.
Limitations, freshness, and the Team Board path always stay outside it.

What Changed is composed as an intelligence change log: inline summary counts,
then one low-emphasis tool row holding plain-text filters (a hairline under the
active one) and a borderless team search, then hairline-opened entries carrying club, backend-authored direction, the supplied
previous → current delta with its label rendered verbatim, the supported reason,
worked-yesterday receipts, and the evidence disclosure. No container.

The vocabulary section leads with the three canonical Team State words as a
plain definition list, then **three** concept features — Bullpen Pressure,
Recovery Window, Clean Options — each with its own abstract mark, a large
title, one definition, and a route deeper.

Three, not six. Workload Concentration, Coverage Safety, and Trusted Arms are
still canonical BaseballOS vocabulary: their definitions in
`utils/bullpenConcepts.js`, their glyphs, and `ConceptCard` are untouched, and
How to Read still teaches all six. They are simply not what a reader needs
mid-edition. Three concepts is the smallest set that explains a bullpen read —
how loaded the pen is, how it recovers, and what is usable tonight — and the
section carries exactly one path to the rest: "Explore all BaseballOS terms →"
to `/how-to-read`.

The descriptive-only boundary statement lives in the Data & Trust brief as fine
print, not in the opening reading path.

Section actions ("Explore all BaseballOS terms", "Open Data & Trust") are text links aligned
to the section title's baseline at the reading-column edge. A bordered button
flush against that edge read as unanchored; a link sits there naturally and
matches every other inspection path on the page.

League lane labels live in `components/dashboard/bullpenLandscapeView.js` and
are deliberately free of superlative framing, and deliberately phrased as
clauses rather than titles (see "League lanes cannot impersonate a Team State"
above). They describe the situation a backend-supplied list represents; they are
not a classification, and canonical Team State is never derived from the lane a
club sits in.

Today's data contracts are unchanged: `getTonightIntelligence`,
`getBullpenLandscape`, `getBullpenDashboard`, `getTeams`.

## Design freeze

Every Today region below is frozen: it is the public visual reference for the
rest of BaseballOS and should not be re-opened without a specific user-facing
defect. The information-architecture closeout changed *what appears and in what
order*, not how any surviving region looks; the visual system is unchanged.

| Region | Status |
|---|---|
| Edition masthead | FROZEN — nameplate, dateline, fact bar; no standfirst, no calls to action |
| League Picture | FROZEN |
| What Changed | FROZEN |
| Tonight's Bullpen Watch | FROZEN |
| BaseballOS Vocabulary | FROZEN — three concepts on Today, six in the system |
| Data & Trust | FROZEN |
| Product Positioning | FROZEN |
| Other views (`#continue-exploring`) | FROZEN — two links, never a section |
| Today's Lead | KNOWN FUTURE DEPENDENCY — #591, then founder authority |

The Today Lead insertion point is unchanged by this pass: it sits between the
Daily Intelligence Brief and the League Picture, and removing the navigation
block that used to follow the League Picture does not move it.

The Team Board page chrome, selector/search controls, answer, Recent Bullpen Work, Current Arm
Picture, and narrative disclosures now share this system. Dashboard, Pitcher
Detail, Stories, How to Read, Methodology, Data & Trust, About, Compare, and the
Reliever Finder content still require surface-level convergence beyond their
shared shell and tokens.

## Deliberate non-goals

### Today does not render a lead story

`/bullpen/intelligence/today` is live, and `getLeadStoryView` in
`components/home/IntelligenceSurface.jsx` reads it. Today still does not render
it, and that is a canon decision rather than an unfinished one:

- the **Bullpen Intelligence Standard** contains no public claim contract for
  the COIN lead story, and it is the document that "controls what claims and
  evidence the experience may present" (Product Experience Standard section 1);
- the **Decision Ledger** carries no entry authorising a public Today lead;
- **Phase 3 — Daily Habit and Consequence**, which owns "Today lead authority",
  is *Not started*, and sits tenth in Next Approved Work behind an open
  production incident (OPS-002), the #593 evidence checkpoint, #595, #591, #594,
  #600, the permanent daily-sync work reduction, Portable Intelligence, and
  M-001.

Publishing a claim family canon has not authorised is the thing fail-closed
exists to prevent, so the lead position stays empty of manufactured content
rather than being filled with either a story or a standing "nothing cleared the
bar" notice — which would imply an evaluation this surface did not run. The
insertion point is unchanged: between the masthead and the League Picture.

What did change is that the position can no longer be quietly filled by
accident. `getLeadStoryView` now enforces two rules that a later wiring
inherits:

1. **it never invents a headline.** A response the backend marked publishable
   but that carries no usable draft copy fails closed to no story with a reason.
   The old `'BaseballOS is watching this bullpen story.'` fallback is gone —
   that was exactly the "fallback invention" #591 targets.
2. **it never surfaces the selection internals.** `story_priority` and
   `confidence` are the engine's own ranking and certainty fields; they no
   longer leave the module at all.
- Stories keeps its own feed. Today links to it and does not duplicate it.
- Dashboard, Team Board, Compare, Stories, Methodology, and Data & Trust were
  not redesigned. They inherit the shell and the shared UI primitives only.
