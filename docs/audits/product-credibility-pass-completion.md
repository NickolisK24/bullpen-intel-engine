# Product Credibility Pass — Completion Audit

> Audit / planning pass only. No frontend implementation, no backend logic change,
> no COIN change, no endpoint-contract change, no data-generation change, no UI
> redesign. The question: is the Product Credibility Pass complete enough to close,
> and what is the next highest-value phase? Product language stays State → Why →
> Evidence → Freshness → Limitations; the product owns one lane — the daily
> operating picture for MLB bullpens.

Branch: `audit/product-credibility-pass-completion`
Base commit: `db9d990` (latest main; includes Stories trust signals, public-facing
Stories limitations, Team Board operating-report completeness, and the sync-cadence trim)

## 1. Executive decision

**Close the Product Credibility Pass.** Across all six surfaces the trust objectives
are met: each page has clear ownership, the major intelligence surfaces follow State →
Why → Evidence → Freshness → Limitations, freshness/date semantics are consistent and
correctly labeled, stale/empty/unavailable/review-only/sample states are honest,
internal-language guards are in place, nothing overclaims, and the Mets-case safety
principle holds (roster pressure is separated from active workload). The remaining items
are **polish/housekeeping, not correctness or trust blockers** — chiefly an orphaned
off-lane `/prospects` route still reachable by direct URL and one block of dead code in
`trust/`. The recommended next phase is a small **release-hardening / lane-purity
cleanup**, after which the product is ready for a limited public/demo review.

## 2. Current completed work summary (verified on main)

Confirmed present at `db9d990`, not just claimed:
- **Stories trust completeness** — `storiesCanonicalFeedView` now maps `freshness`,
  `limitations`, and quality status; `Stories.jsx` renders a trust strip
  (`FreshnessBadge` + "Bullpen data through" + last sync + **"Current MLB data" /
  "Review-only intelligence — not live MLB data"**), a page-level limitations scope
  note, and a per-card "Under review" marker. (Closes all three gaps from the Stories
  audit except the optional flagship cross-surface de-dup — see §14.)
- **Team Board operating-report completeness** — `BullpenOperatingStateCard` now renders
  a **Starter support** row (`view.starterSupportPressure`), alongside the three context
  reads (clean options, coverage safety, workload concentration) and roster pressure.
  (Closes the dropped-Starter-Support gap from the team-board audit.)
- **Operating-state read model adapter** shared across league/team via
  `BullpenOperatingStateCard` + `operatingStateReadModel`.
- **Freshness Everywhere**, homepage date-semantics clarification, Today front-door
  polish, Dashboard league-board polish, page-hierarchy de-dupe, Methodology / Data &
  Trust ownership cleanup, safe team context reads — all confirmed merged.
- **Internal-language guards** — `operatingStateReadModel` safeText filters, the Stories
  adapter's internal-token regex, and Methodology's `displayCopy()` sanitizer.

## 3. Page-by-page readiness assessment

- **Today (`/` → Home → IntelligenceSurface)** — front door. Lead read + Tonight watch
  items + compact league teaser + Explore CTAs (Dashboard/Bullpen/Stories/Trust/
  Methodology). Flagship carries its Limitations leg. **Ready.**
- **Dashboard (`/dashboard`)** — league operating board (landscape columns →
  team boards). Freshness pill links to Data & Trust. **Ready.**
- **Bullpen Team Board (`/bullpen`)** — team-level operating report via the shared card:
  State → Why → Evidence (active workload, roster pressure, starter support, clean
  options, coverage safety, workload concentration) → Freshness → Limitations, plus
  pitcher lanes. **Ready.**
- **Stories (`/stories`)** — selective developing feed from the canonical source; lane
  filters; per-card State→Why→Evidence blueprint; now with freshness strip, limitations
  scope note, and live/review-only signal. **Ready.**
- **Methodology (`/methodology`)** — definitions / how reads are computed; defers
  reliability checks and freshness to Data & Trust; `displayCopy()` sanitizes internal
  tokens. **Ready.**
- **Data & Trust (`/trust`)** — freshness, sync health, reliability (Operational
  Backtest), data limitations; explicit "Last checked / Latest data update / Data
  through" distinctions and layered stale fallbacks. **Ready** (one dead sibling file;
  §14).

## 4. State → Why → Evidence → Freshness → Limitations assessment

Honored on every surface where it applies. Today's flagship, the Team Board card, and
Stories cards each carry State, Why, and Evidence; Freshness and Limitations are present
(per-card on the operating-state card, page-level on Stories where all cards share one
slate). Methodology and Data & Trust are definitional/proof surfaces and correctly use a
documentation/evidence shape rather than the per-read contract. No surface asserts a
read without its evidence and limitations.

## 5. Freshness / date semantics assessment

Correct and consistent. The Sidebar shows "Page checked / Latest data update / Bullpen
data through"; Today separates slate (Tonight) from completed-game "Bullpen data
through"; Dashboard, Team Board, and Stories all stamp "Bullpen data through" with
completed-game dates; Data & Trust explicitly defines each term. Stale states thread
through (`StaleDataNotice` / `FreshnessBadge state="stale"`). No date is mislabeled, and
live-vs-review is now explicit on Stories. No action needed.

## 6. Page hierarchy / ownership assessment

The Sidebar nav is exactly the six canonical pages (Today, Dashboard, Bullpen, Stories,
Methodology, Data & Trust) in lane order — no extra nav items diluting the lane. Each
page owns a single job and links to (rather than duplicates) the others. Hierarchy is
test-covered (`navigationRoutes.test.mjs`, `pageHierarchyDedupe.test.mjs`,
`trustChromeRemoval.test.mjs`). Ownership is clean.

## 7. Duplicate / misplaced content assessment

No live duplication. Today→Stories is a legitimate teaser→full relationship on one
canonical source; Dashboard (league board) and Stories (feed) draw different shapes from
the same payload; Methodology (definitions) and Data & Trust (freshness/proof) are
cleanly separated with Methodology explicitly deferring reliability to Data & Trust. The
only residuals are non-rendered: a dead `DigestPreferencesCard.jsx` in `trust/` and
legacy code paths behind the Home wrapper (see §14).

## 8. Internal-language safety assessment

Clean in rendered output, with active guards rather than incidental cleanliness:
`operatingStateReadModel` runs strings through safeText filters; the Stories adapter
applies an internal-token regex (COIN/V2-4/deterministic/snapshot/endpoint/backend/
governance/quality_status/suppression_reason/source/…); Methodology's `displayCopy()`
rewrites backend tokens to product language. No user-visible internal label was found on
any of the six pages. Residual risk is only latent — newly surfaced fields must keep
using these whitelists/guards.

## 9. Overclaiming / public-trust assessment

Low across the board. All reads are descriptive and past/present-tense; Stories' "why it
matters tomorrow" is framed as continuation, not forecast; continuity badges are
structured story-type deltas, not predictions. No betting, fantasy, prospect-as-product,
injury, private-medical, manager-intent, or future-usage claims. Backtest/methodology
copy is bounded with caveats and sample sizes. Public/social copy on Stories is safe with
minimal editing.

## 10. Mets-case safety assessment

Holds. The operating-state read model builds roster pressure from roster authority
(injured-list / inactive / unknown) as a **separate** concern from the active-availability
counts that drive State and the primary concern, so an injured or inactive arm is never
silently counted as active coverage. Because Team Board and the league card share the
same card/adapter, the guard holds on both the team and league surfaces.

## 11. Sample / review-only exposure assessment

No surface mislabels sampled or review-only data as live production intelligence. Stories
now renders an explicit "Review-only intelligence — not live MLB data" note and a per-card
"Under review" marker driven by quality status; the diagnostic league-sample path is
backend-only and not user-navigable. The internal sample/review vocabulary is never shown
— only baseball-facing "Current MLB data" / "Review-only" / "Under review" labels. This is
a meaningful credibility win versus the start of the pass.

## 12. Release / demo readiness assessment

**Ready for a limited public/demo review after a small housekeeping pass.** The six
in-lane pages are trustworthy, consistent, and honest. The blockers to a clean demo are
not correctness issues but lane-purity issues: a stray off-lane `/prospects` page
reachable by direct URL, and dead code in `trust/`. Neither is navigable from the product,
but both should be cleared before inviting outside eyes so the "one lane: bullpens"
positioning is airtight.

## 13. Remaining blockers, if any

**No correctness or trust blockers.** Every credibility objective (ownership, the read
contract, freshness, honest states, internal-language guards, no overclaiming, Mets-case)
is satisfied on the in-lane surfaces. The items in §14 are housekeeping, and the product
is internally usable today.

## 14. Remaining polish follow-ups

1. **Orphaned `/prospects` route** — `App.jsx` mounts `/prospects` (Prospects component +
   `getProspects*` api helpers) though it is absent from the Sidebar and unlinked. It is
   reachable by direct URL and is off-lane. Remove the route/components (preferred) or
   hard-hide them so a demo cannot reach a prospects surface.
2. **Dead `DigestPreferencesCard.jsx`** in `components/trust/` — ~645 lines, exported but
   never imported/rendered. Delete or relocate; do not ship dead preferences UI.
3. **Legacy Home/morning-report code** behind the `/` wrapper — prior page-hierarchy audit
   flagged dead legacy paths; confirm and prune what is no longer mounted.
4. **Stories flagship cross-surface de-dup (Stories audit Phase C)** — not observed in the
   current adapter; Today's flagship can still reappear as a Stories card. Low-priority
   presentation tweak (down-rank the matching team+story-type card).
5. **Methodology sample-composition footnote** — backtest sample sizes render without a
   one-line "based on N relievers over M completed games" context; optional clarity nit.

## 15. Recommended next phase

**Release hardening — a "lane-purity & cleanup" pass** (small, frontend-only). This is the
highest-value next step: it removes the only things that could undercut credibility in a
public/demo review (off-lane orphan route, dead code) without adding scope. It is higher
value right now than team-page expansion, Data & Trust hardening, or further story
follow-ups, because those add surface area while the cleanup removes risk ahead of outside
review. Main Page Final Shape can fold into the same pass if desired, but the layout itself
is not blocking trust.

## 16. Recommended next Codex branch, if any

`chore/lane-purity-cleanup` (frontend-only, small):
- Remove the `/prospects` route + `prospects/` components + unused `getProspects*` helpers
  (or gate behind a clearly non-public, non-nav path).
- Delete `components/trust/DigestPreferencesCard.jsx` (or relocate out of `trust/`).
- Prune confirmed-dead legacy Home/morning-report code.
- Update/extend `navigationRoutes.test.mjs` + `pageHierarchyDedupe.test.mjs` to assert the
  nav/route set is exactly the six in-lane pages (+ auth/admin), and that `/prospects` is
  gone. No backend, no contract, no data changes.

## 17. Recommended next Claude audit, if any

A short **release / demo-readiness inventory** audit that enumerates every mounted route,
component, and api helper and classifies each as in-lane / auth-admin / orphan-to-remove —
a definitive cleanup checklist before public review. (Optionally fold in a quick check of
whether Stories Phase C de-dup is worth doing.) No deeper product audit is needed before
closing this pass.

## 18. Out of scope (do not build)

No prediction engines, betting, fantasy, prospect surfaces (in fact, remove the orphan),
social automation, public-posting workflows, or general MLB stat pages. No new backend
intelligence (every recommendation is removal or a render of existing fields). No large
redesign (the layout does not block trust). No Trend Since Yesterday state card — there is
no trusted day-over-day **state** delta; the descriptive continuity badge stays as-is and
is not escalated into better/worse-than-yesterday language. No endpoint-contract, COIN, or
data-generation changes.

## 19. Risks if moving on too early

- Inviting a public/demo review while `/prospects` is reachable by URL undercuts the
  single-lane positioning and invites off-topic questions.
- Shipping dead `DigestPreferencesCard.jsx` / legacy code raises maintenance confusion and
  the chance a future change accidentally re-mounts an unreviewed surface.
- Jumping to team-page expansion or new surfaces now adds area to keep credible before the
  base is locked, increasing regression surface right when the trust story is finally
  coherent.
- Skipping the test-alignment step means the nav/route guarantees aren't enforced, so the
  lane can quietly drift again.

## 20. Final decision: close or keep open

**Close the Product Credibility Pass.** Its objectives are met on every in-lane surface and
verified on main. Track the residual housekeeping under a new, clearly-scoped release-
hardening phase rather than holding the credibility pass open — keeping it open would
conflate "trust is credible" (done) with "cleanup is done" (a separate, smaller effort).

## Validation / status checks

- Branch starts from latest main (`db9d990`). ✔
- No frontend implementation made (audit doc only). ✔
- No backend logic changed. ✔
- No COIN changes. ✔
- No endpoint contract changes. ✔
- No data-generation changes. ✔
- `git diff --check` / `git diff --cached --check` clean; only the audit doc staged. ✔

## Decision

The Product Credibility Pass is complete enough to close: clear page ownership, the
State → Why → Evidence → Freshness → Limitations contract honored across the intelligence
surfaces, correct and consistent freshness, honest stale/empty/review/sample states,
working internal-language guards, no overclaiming, and the Mets-case guard intact — all
verified on main. Remaining items are polish/housekeeping (orphan `/prospects`, dead
`DigestPreferencesCard.jsx`, legacy code, optional Stories Phase C). Open a small
`chore/lane-purity-cleanup` release-hardening phase next, then proceed to a limited
public/demo review.

ready for Codex implementation: YES (one small frontend cleanup branch).
ready to merge: this audit doc is docs-only and safe to merge; no code changed.
