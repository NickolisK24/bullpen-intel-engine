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
The remaining public surfaces — Team Board, Dashboard content, Compare, Reliever
Finder, Stories, Pitcher Detail — are NOT migrated by UX-003 and are NOT listed
here. Migrating one is a new package or an explicitly amended UX-003 decision,
reviewed on its own evidence. This list does not extend itself.
"""

# Runtime surfaces: the presentation layer the migration rebuilt.
#
#   product_experience_foundation.md — the package's own design record: the
#                             token layer, the primitives, the Today hierarchy,
#                             and the deliberate non-goals
#   index.html              — the font request gained DM Sans 700 so the display
#                             levels have a real semibold; no meta claim changed
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
    'frontend/src/components/UI/Freshness.jsx',
    'frontend/src/components/UI/StaleDataNotice.jsx',
    'frontend/src/components/dashboard/bullpenLandscapeView.js',
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
    'frontend/src/components/trust/DataTrust.jsx',
    'frontend/src/utils/dateDisplay.js',
    'frontend/src/utils/navigation.js',
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
)

UX003_PRODUCT_EXPERIENCE_FRONTEND_FILES = (
    UX003_PRODUCT_EXPERIENCE_RUNTIME_FILES + UX003_PRODUCT_EXPERIENCE_TEST_FILES
)
