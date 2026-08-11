"""The exact files VOC-001 / #638 changes to give public wording one owner.

The change guards protect `frontend/src/` and the public backend surfaces from
incidental edits. Reader-facing wording lives inside those protected files, so
a vocabulary reconciliation cannot happen without touching them.

Naming them is the point. This module exists so every guard allowlists the SAME
exact list instead of reaching for a `frontend/**` or "wording changes"
exemption: only these paths are permitted, and adding one is a visible,
reviewable edit rather than a silent widening. Every other file under
`frontend/src/` still fails every guard.

What the change is, and is not
------------------------------
Pitcher role and read wording had two owners: the backend declared itself the
authority and the frontend rewrote the result on the way out. The backend now
emits the final wording and the frontend renders it verbatim. Alongside that,
three vocabulary collisions were removed — the role and read families no longer
share the fallback word 'Limited Read', read confidence stopped looking like a
second baseball read, and the data-status badges stopped borrowing baseball
words ('Limited', 'Healthy').

Strings only. No threshold, classification, derivation, availability rule,
roster authority, publication gate, Team State projection, freshness
computation, timestamp, or engine key changed, and every internal key is
byte-identical. Each guard pairs this list with its own purpose proof.
"""

# Backend: the declared owner of pitcher role/read public wording.
PUBLIC_VOCABULARY_BACKEND_FILES = (
    'backend/services/pitcher_public_labels.py',
)

# Frontend: the surfaces that stopped rewriting or stopped carrying a second
# vocabulary.
#
#   pitcherLabels.js        — the substitution table is deleted; what remains is
#                             a keyed lookup for tone and reader definition
#   availabilityView.js     — read confidence became an explicit High / Medium /
#                             Low / Unavailable scale
#   syncStatusView.js       — data status became Current / Partial Data / Stale /
#                             Data Unavailable
#   teamGameContextView.js  — the same data-status family on a second surface
#   tonightsBullpenBoardView.js — and on a third, so the product does not show
#                             two competing freshness dictionaries
PUBLIC_VOCABULARY_FRONTEND_FILES = (
    'frontend/src/utils/pitcherLabels.js',
    'frontend/src/components/bullpen/availabilityView.js',
    'frontend/src/components/dashboard/syncStatusView.js',
    'frontend/src/components/bullpen/board/teamGameContextView.js',
    'frontend/src/components/bullpen/board/tonightsBullpenBoardView.js',
)

PUBLIC_VOCABULARY_FILES = (
    PUBLIC_VOCABULARY_BACKEND_FILES + PUBLIC_VOCABULARY_FRONTEND_FILES
)
