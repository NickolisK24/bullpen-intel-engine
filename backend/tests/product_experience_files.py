"""The exact files UX-003 changes to migrate the public presentation layer.

The change guards protect `frontend/` — and `frontend/src/` in particular — from
incidental edits. The Product Experience Foundation migration is a presentation
change to reader-facing surfaces, so it cannot happen without touching protected
files.

Naming them is the point. This module exists so every guard allowlists the SAME
exact list instead of reaching for a `frontend/**`, `*.jsx`, or "visual changes"
exemption: only these paths are permitted, and adding one is a visible,
reviewable edit rather than a silent widening. Every other file under
`frontend/` still fails every guard.

What the change is, and is not
------------------------------
UX-003 is a presentation and migration authority only. It moves the public
surfaces onto the approved Product Experience visual system and the Today Daily
Edition hierarchy: shared presentation primitives, typography, spacing,
geometry, responsive behaviour, accessibility contrast, canonical public
navigation labels, freshness presentation, evidence presentation, and
presentation-only disambiguation of vocabulary canon already defines.

It moves no baseball meaning. No threshold, classification, derivation,
availability rule, roster authority, publication gate, Team State projection,
freshness computation, or engine key changed, and no internal key moved. The
backend remains the owner of what may be claimed; these files arrange and label
values it already governs.

Specifically, UX-003 does not authorize a Team State derivation, a bullpen tier,
a new availability computation, a prediction, a recommendation, a ranking, a
fatigue score, an invented backend claim, a fabricated baseball fact, a Today
lead-story claim family, or any backend API semantic change.
``test_product_experience_package.py`` proves those properties against this list
rather than merely asserting them here, and pairs it with an exactness proof so
the constant cannot silently drift away from the branch it describes.

Adding a surface
----------------
Each surface enters this list by an explicit amendment reviewed on its own
evidence. The list does not extend itself, and a surface is only ever added for
the files a pass actually changes.

  Pass 1 (D-054)  — the shared visual system, the presentation primitives, the
                    public navigation labels, and the Today Daily Edition.
  Pass 2 (D-055)  — the Team Board answer zone: the operating-state card's
                    compact variant and the availability distribution beneath
                    it.
  Pass 3 (D-056)  — approved foundation-token alignment and the remainder of
                    Team Board presentation: page chrome, team control, recent
                    bullpen work, current arm groups, search, and disclosures.
  Pass 4 (D-057)  — Foundations geometry and signatures across the shared shell,
                    footer, system states, Dashboard, Stories, Methodology, and
                    Data & Trust presentation.

Still NOT migrated and NOT listed: Dashboard content, Compare, Reliever Finder,
Stories, and Pitcher Detail. Those keep the older register inside their content
and require their own amendment.
"""

# Runtime surfaces: the presentation layer the migration rebuilt.
#
#   product_experience_foundation.md — the package's own design record: the
#                             token layer, the primitives, the Today hierarchy,
#                             and the deliberate non-goals
#   index.html              — the approved Archivo Narrow / IBM Plex font
#                             request; no meta claim changed
#   tailwind.config.js      — the additive `bos-*` token scale (colour, spacing,
#                             radii, shadow, the 390px breakpoint)
#   index.css               — the same tokens as custom properties plus the
#                             `.bos-*` typographic and structural classes
#   App.jsx                 — skip link into the `main` landmark; the content
#                             offset for a left rail is gone
#   Sidebar.jsx             — the historical path of the shell component, now a
#                             horizontal masthead rather than a rail
#   UI/Freshness.jsx        — formatting options for the represented date. It
#                             renders governed freshness values and computes no
#                             freshness state
#   UI/StaleDataNotice.jsx  — the stale notice restyled onto the token system
#   dashboard/bullpenLandscapeView.js
#                           — league lane labels became descriptive clauses so a
#                             lane cannot present as a fourth Team State
#   home/IntelligenceSurface.jsx
#                           — the Today Daily Edition: masthead, league picture,
#                             what changed, tonight, vocabulary, trust
#   components/intel/*      — the shared presentation primitives. Each renders
#                             supplied values only; none derives a state, a
#                             score, a ranking, or an explanation
#   methodology/Methodology.jsx, trust/DataTrust.jsx
#                           — one public navigation label each, matching the
#                             canonical lane naming. No methodology or trust
#                             content changed
#   utils/dateDisplay.js    — an optional weekday on a supplied calendar date,
#                             derived through a UTC instant. It reads no clock
#   utils/navigation.js     — public lane labels only; every `key`, route, and
#                             `view` query is byte-unchanged, so no URL moved
UX003_PRODUCT_EXPERIENCE_RUNTIME_FILES = (
    'frontend/docs/product_experience_foundation.md',
    'frontend/index.html',
    'frontend/tailwind.config.js',
    'frontend/src/index.css',
    'frontend/src/App.jsx',
    'frontend/src/components/Sidebar.jsx',
    'frontend/src/components/layout/Footer.jsx',
    'frontend/src/components/UI/Freshness.jsx',
    'frontend/src/components/UI/StaleDataNotice.jsx',
    'frontend/src/components/dashboard/bullpenLandscapeView.js',
    'frontend/src/components/dashboard/Dashboard.jsx',
    'frontend/src/components/home/IntelligenceSurface.jsx',
    'frontend/src/components/intel/ConceptCard.jsx',
    'frontend/src/components/intel/ConceptGlyph.jsx',
    'frontend/src/components/intel/EditionHeader.jsx',
    'frontend/src/components/intel/EvidenceReceipt.jsx',
    'frontend/src/components/intel/IntelNotice.jsx',
    'frontend/src/components/intel/IntelSection.jsx',
    'frontend/src/components/intel/TeamStateChip.jsx',
    'frontend/src/components/intel/TrustStrip.jsx',
    'frontend/src/components/intel/index.js',
    'frontend/src/components/methodology/Methodology.jsx',
    'frontend/src/components/stories/Stories.jsx',
    'frontend/src/components/trust/DataTrust.jsx',
    'frontend/src/utils/dateDisplay.js',
    'frontend/src/utils/navigation.js',
    # Pass 2 — the Team Board answer zone. The Team Board owns one question:
    # what is this bullpen's observable current state, which arms are carrying
    # it, and why. These two files are where the first part of that answer is
    # composed, and Pass 2 reorders and restyles them without touching what they
    # are allowed to say.
    #
    #   BullpenOperatingStateCard.jsx
    #                           — the answer zone. The compact (Team Board)
    #                             variant is recomposed in reading order: team
    #                             identity, then the canonical backend Team
    #                             State at reading size, then the backend Why,
    #                             then evidence receipts, then freshness, then
    #                             limitations. The state stopped being a corner
    #                             badge and the panel stopped taking its
    #                             background from the state tone. The full
    #                             variant, which the Dashboard renders, is
    #                             deliberately unchanged.
    #   BullpenAvailabilityDistribution.jsx
    #                           — the four published availability counts under
    #                             that answer, recomposed from five bordered
    #                             tiles into a quiet count row so the
    #                             distribution supports the state instead of
    #                             competing with it. It already renders the
    #                             backend's group labels verbatim (VOC-001) and
    #                             still does; only the layout changed.
    #
    # Neither file gained a derivation. Team State still arrives validated from
    # `adapters/publicTeamState.js` through the operating-state read model, the
    # Why is still backend copy or absent, and a withheld count is still
    # "Withheld" rather than a zero.
    'frontend/src/components/bullpen/BullpenOperatingStateCard.jsx',
    'frontend/src/components/bullpen/board/BullpenAvailabilityDistribution.jsx',
    # Pass 3 — the Team Board becomes one visual product from its page identity
    # through its deepest governed evidence. These paths only change layout,
    # typography, controls, responsive composition, and disclosure treatment.
    # They continue to consume the existing board, relief-work, story, and game
    # context contracts verbatim; no browser-owned baseball meaning is added.
    'frontend/src/components/bullpen/Bullpen.jsx',
    'frontend/src/components/bullpen/AvailabilitySummary.jsx',
    'frontend/src/components/bullpen/PitcherDetail.jsx',
    'frontend/src/components/bullpen/PitcherSearch.jsx',
    'frontend/src/components/bullpen/RecentWorkPanel.jsx',
    'frontend/src/components/bullpen/TeamReliefWorkPanel.jsx',
    'frontend/src/components/bullpen/board/BullpenBoardView.jsx',
    'frontend/src/components/bullpen/board/TonightsBullpenBoard.jsx',
)

# Test surfaces: the contracts the migration asserts, and the existing suites
# whose expectations moved with the public labels they were pinning. These
# change no product behavior, and one guard already excludes test paths
# entirely; they are listed because the snapshot-trust freeze covers all of
# `frontend/`.
UX003_PRODUCT_EXPERIENCE_TEST_FILES = (
    'frontend/tests/productExperienceFoundation.test.mjs',
    'frontend/tests/accessibilityContrast.test.mjs',
    'frontend/tests/intelligenceSurface.test.mjs',
    'frontend/tests/mobileNavigation.test.mjs',
    'frontend/tests/navigationRoutes.test.mjs',
    'frontend/tests/dashboardRealignment.test.mjs',
    'frontend/tests/dashboardStorylines.test.mjs',
    'frontend/tests/bullpenLandscapeAndGameContext.test.mjs',
    # Pass 2: the Team Board answer-zone contract — reading order, state
    # prominence, the neutral panel, no fourth state, no fabricated why, no
    # prediction or internal score, the subordinate distribution, and the
    # absence of the still-reserved M-001 metric.
    'frontend/tests/teamBoardAnswerHierarchy.test.mjs',
    'frontend/tests/bullpenPageIdentity.test.mjs',
    'frontend/tests/teamReliefWorkPanel.test.mjs',
    'frontend/tests/bullpenTabLabels.test.mjs',
    'frontend/tests/canonicalEvidenceLinks.test.mjs',
    'frontend/tests/dashboardScopeClarification.test.mjs',
    'frontend/tests/pitcherUsageRole.test.mjs',
    'frontend/tests/teamBoardStoryRetirement.test.mjs',
    'frontend/tests/teamShare.test.mjs',
    'frontend/tests/tonightsBullpenBoard.test.mjs',
)

UX003_PRODUCT_EXPERIENCE_FRONTEND_FILES = (
    UX003_PRODUCT_EXPERIENCE_RUNTIME_FILES + UX003_PRODUCT_EXPERIENCE_TEST_FILES
)
