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
| Surfaces | `ink`, `panel`, `panel-2` |
| Borders | `line`, `line-strong` |
| Accents | `signal`, `signal-deep`, `signal-well`, `brass`, `brass-deep` |
| Focus | `focus` |
| Spacing | `--bos-space-1` … `--bos-space-8`; named Tailwind steps `gutter`, `rhythm`, `section` |
| Radii | `edge` (2px), `panel` (4px), `control` (6px) |
| Shadows | `panel`, `edition` — near-invisible; borders carry the structure |
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

- **DM Sans** carries every reading level — headlines, section titles, card
  titles, body, support, evidence, buttons, and navigation.
- **JetBrains Mono** is reserved for values that benefit from precision:
  `.bos-meta` and `.bos-value` (dates, times, counts, provenance, timestamps).
- **Bebas Neue** survives only as `.bos-kicker` — a short condensed accent for
  team-name kickers and the wordmark. It is never a page statement, a button,
  a paragraph, or a section title.

No font family was added. DM Sans 700 was added to the existing Google Fonts
request so display levels have a proper semibold/bold weight.

Structure classes: `.bos-page` / `.bos-page--reading` (frame and measure),
`.bos-section` (rhythm plus a hairline between sections), `.bos-open` and
`.bos-marker` (grouping without a container), `.bos-panel` (reserved for
discrete units), `.bos-rule`, `.bos-edition` / `.bos-edition-rule` (the
signature masthead), `.bos-depth` (background depth), `.bos-action--primary` /
`--quiet`, `.bos-link`, and `.bos-skip-link`.

### Background depth

`.bos-depth` draws two non-interactive layers behind its content: a wide radial
lift and a set of analytical contour paths as an inline SVG data URI. Both are
`pointer-events: none` at `z-index: -1`, neither animates, and neither adds a
network request or a dependency. It is applied to the edition masthead and the
product-positioning statement only.

### Container discipline

Most regions have no container. A hairline plus spacing groups them. `bos-panel`
is used only where a boundary carries meaning: slate cards (discrete game
reads), since-yesterday cards (comparison units), and withheld/limited reads.

Motion is limited to state changes and is disabled entirely under
`prefers-reduced-motion: reduce`.

Contrast: `tests/accessibilityContrast.test.mjs` pins every text and accent
token at WCAG AA or better against every surface token.

## Layer B — intelligence primitives (`src/components/intel/`)

All of these render supplied values only. None derives a state, a score, a
ranking, or an explanation, and none rewrites backend-owned copy.

| Component | Purpose | Data authority |
|---|---|---|
| `EditionHeader` | Daily Intelligence Brief masthead: edition identity, lead statement, governed fact rail | caller, from served application state; a fact with no value is omitted |
| `IntelSection` / `SectionHeading` | Section heading system (eyebrow, title, orientation line, aligned action) | none — layout only |
| `TeamStateChip` / `TeamStateRead` | Canonical Fresh / Stretched / Vulnerable presentation, as toned text with a dot rather than a filled pill | `adapters/publicTeamState.js` → backend Team State block |
| `EvidenceList` / `EvidenceRow` / `NamedArmReceipt` | Evidence receipts and named-arm evidence | the contract that supplied the row |
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
  desktop bar shows: Today, League Board, Team Bullpens, Stories, Methodology,
  Data & Trust. `masthead: false` on Compare and Reliever Finder, and
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

1. Daily Intelligence Brief (`EditionHeader`) — the single `<h1>`
2. Today's Bullpen Picture — league overview (`#bullpen-picture`)
3. Where do you want to go next? (`#explore-baseballos`)
4. What changed across MLB bullpens (`#since-yesterday`)
5. Tonight's Bullpen Watch (`#tonight`)
6. How BaseballOS describes a bullpen (`#vocabulary`)
7. How current this read is (`#data-and-trust`)
8. What BaseballOS is for (`#what-baseballos-is-for`)
9. Learn & Explore BaseballOS (`#explore`)

Sections 2–5 keep the order and the data contracts they already had. Sections
1 and 6–8 are presentation over existing governed values.

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
plain definition list, then six concept features, each with its own abstract
mark, a large title, one definition, and a route deeper.

The descriptive-only boundary statement lives in the Data & Trust brief as fine
print, not in the opening reading path.

Section actions ("Read every term", "Open Data & Trust") are text links aligned
to the section title's baseline at the reading-column edge. A bordered button
flush against that edge read as unanchored; a link sits there naturally and
matches every other inspection path on the page.

League lane labels live in `components/dashboard/bullpenLandscapeView.js` and
are deliberately free of superlative framing. They describe the situation a
backend-supplied list represents; they are not a classification, and canonical
Team State is never derived from the lane a club sits in.

Today's data contracts are unchanged: `getTonightIntelligence`,
`getBullpenLandscape`, `getBullpenDashboard`, `getTeams`.

## Design freeze

Every Today region below is frozen: it is the public visual reference for the
rest of BaseballOS and should not be re-opened without a specific user-facing
defect.

| Region | Status |
|---|---|
| Daily Intelligence Brief | FROZEN |
| League Picture | FROZEN |
| What Changed | FROZEN |
| Tonight's Bullpen Watch | FROZEN |
| BaseballOS Vocabulary | FROZEN |
| Data & Trust | FROZEN |
| Product Positioning | FROZEN |
| Today's Lead | KNOWN FUTURE DEPENDENCY — #591, then founder authority |

The remaining public surfaces (Dashboard, Bullpens, Compare, Reliever Finder,
Stories, How to Read, Methodology, Data & Trust, About) still use the older
amber / Bebas register inside their content. They inherit the masthead and the
shared UI primitives only. Migrating them is the next visual-system package, not
a Today refinement.

## Deliberate non-goals

- Today does not render a story lead. The lead-story contract is not currently
  served on this surface and the canonical roadmap defers Today lead authority;
  the brief occupies the lead position instead.
- Stories keeps its own feed. Today links to it and does not duplicate it.
- Dashboard, Team Board, Compare, Stories, Methodology, and Data & Trust were
  not redesigned. They inherit the shell and the shared UI primitives only.
