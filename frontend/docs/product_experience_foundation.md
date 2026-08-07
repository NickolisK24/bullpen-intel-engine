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
| `IntelNotice` / `IntelSkeleton` | Designed quiet, limited, unavailable, and loading states | caller-supplied governed copy |

Rules the primitives enforce:

- a Team State renders only when the backend block is `available` **and** the
  code/label pair is canonical; anything else falls closed to the governed
  non-state message and the neutral tone;
- state is always readable as text with a screen-reader `Team State:` prefix —
  colour is decoration;
- a trust fact with no value renders nothing rather than a placeholder;
- a concept card never carries a value, tier, or percentage.

## Layer C — application shell

- `App.jsx` adds a skip link into `<main id="main-content">`.
- `Sidebar.jsx` keeps every route, label, and active-state rule; the wordmark now
  returns to Today, the active destination is a blue rail plus `aria-current`
  (never colour alone), and spacing/typography use the token scale.
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

Tonight's cards show the answer first — club, headline, schedule context, the
watching sentence, the watch point, and the usage notes — and move the
supporting rows the backend also authored behind one native `<details>`.
Freshness and limitations are never placed behind that disclosure.

League lane labels live in `components/dashboard/bullpenLandscapeView.js` and
are deliberately free of superlative framing. They describe the situation a
backend-supplied list represents; they are not a classification, and canonical
Team State is never derived from the lane a club sits in.

Today's data contracts are unchanged: `getTonightIntelligence`,
`getBullpenLandscape`, `getBullpenDashboard`, `getTeams`.

## Deliberate non-goals

- Today does not render a story lead. The lead-story contract is not currently
  served on this surface and the canonical roadmap defers Today lead authority;
  the brief occupies the lead position instead.
- Stories keeps its own feed. Today links to it and does not duplicate it.
- Dashboard, Team Board, Compare, Stories, Methodology, and Data & Trust were
  not redesigned. They inherit the shell and the shared UI primitives only.
