# Share Cards Cutover — SC-03A

Share Cards is one product. This note records the SC-03A step that moves card
**intelligence generation** onto the immutable Share Artifact architecture
(SC-01 domain + SC-02 eligibility/payload) **and** cuts the active frontend
Share Card surfaces over to reading that canonical artifact, so there is a single
source of truth for card content.

There is no "V2" and no user-facing version toggle. The immutable artifact is the
single authoritative content path today; the browser no longer composes card
intelligence. Only the presentational PNG renderer remains temporarily legacy
(replaced in SC-06/SC-07), and it now renders **only** artifact-backed data.

## Authoritative generation path

```
trusted published snapshot
  -> governed Team Operations readiness payload   (resolve_team_readiness_payload — reuses the existing pipeline)
  -> SC-02 gather_team_state_source
  -> SC-02 evaluate_team_state_eligibility
  -> SC-02 build_team_state_payload
  -> SC-01 immutable Share Artifact publication    (dedup + integrity verified)
  -> generation audit (durable, per attempt)
```

Entry point: `services/share_artifact_generation.generate_team_state_artifact`,
triggered internally via `POST /api/internal/share-artifacts/team-state/generate`
(admin-token gated). Every attempt — published / reused / refused / failed_closed
— is recorded in `share_artifact_generation_audits`. Generation stays internal:
there is no public generation endpoint, so the public frontend can never mint an
artifact.

## Authoritative read path (frontend cutover)

```
published immutable Share Artifact  (latest for team, lifecycle = published)
  -> verify_share_artifact_integrity                (fail closed on mismatch)
  -> build_share_card_compatibility_view / get_team_state_card   (pure projection)
  -> GET /api/share-cards/team-state/<team_id>      (governed public read)
  -> utils/shareCardArtifact.buildTeamShareCardFromArtifact       (pure adapter)
  -> existing EvidenceShareMenu / PNG renderer      (present only)
```

Read endpoint: `backend/api/share_cards.py` (`share_cards_bp`, mounted at
`/api/share-cards`). It serves **only** a published, integrity-verified artifact
projection and:

- returns `{ available: false, reason: 'no_published_artifact' }` (HTTP 200) when
  no published artifact backs the team — a controlled unavailable state, never a
  fabricated or legacy-composed card;
- **fails closed** with HTTP 503 `integrity_unverified` when integrity
  verification raises (`ShareArtifactIntegrityError`);
- never serves a withdrawn or superseded artifact as active (the repository query
  selects only the latest `published` lifecycle row);
- composes no intelligence and never falls back to a legacy client path.

It is public because the team-state read it exposes is already public via the
board, and the artifact-backed endpoint is strictly *more* governed than the
existing board read (published + eligibility-gated + integrity-verified). It adds
no admin/audit surface, and reuses the existing `get_team_state_card()` /
`build_share_card_compatibility_view()` projection with no new intelligence.

The adapter (`frontend/src/utils/shareCardArtifact.js`) accepts only a projection
tagged `source: 'immutable_share_artifact'`; anything else yields `null`, which
drives the share menu's controlled unavailable state. It intentionally omits
`cardVersion` / `storyAngle` so the existing share-action tracker (which rejects
unknown card versions) keeps recording share actions via caller context.

## Legacy audit classification

**KEEP_AND_ADAPT** — consume the canonical artifact; never compose intelligence.
- `frontend/src/components/share/EvidenceShareMenu.jsx`, `frontend/src/utils/shareActions.js`,
  `evidenceCardRenderer.js`, `evidenceCardText.js` (render/present only).
- Share-action tracking (`backend/models/traffic_share_action.py`,
  `backend/services/traffic_share_actions.py`, `traffic_reporting.py`,
  `backend/api/traffic.py`) — observational only; unchanged.

**CUT_OVER** — the three active entry points now read the canonical artifact and
no longer compose or fall back to client-side intelligence.
- `TonightsBullpenBoard.jsx` — the team card is
  `buildTeamShareCardFromArtifact(shareCard.data)` (fed by `getTeamShareCard`);
  when no artifact backs the team the card is `null` and the share menu shows its
  controlled unavailable state. No `|| buildTeamEvidenceCard(...)` fallback.
- `BullpenComparisonView.jsx` — a comparison Team State artifact does not exist in
  the immutable architecture yet, so `cardModel = null` (controlled unavailable);
  it never composes `buildComparisonEvidenceCard(...)`. Copy-exact-link stays.
- `Stories.jsx` — link-only surface; it now sources `EVIDENCE_CARD_ORIGIN` from
  the artifact adapter, so nothing here depends on the deprecated composer.

**DEPRECATED / REMOVE_LATER** — retained but no active Share Card entry point
imports or calls their composers; marked `DEPRECATED — REMOVE_LATER`. They are
deleted once the SC-06/SC-07 renderer consumes the canonical payload directly.
- `frontend/src/utils/evidenceCardModel.js` (`buildTeamEvidenceCard`,
  `buildComparisonEvidenceCard`). One pure *view-only* helper
  (`comparisonObservationCandidates`) is still used by the on-screen comparison
  table (`teamBullpenComparisonView.js`) for its featured-observation copy; that
  path never produced a shareable artifact and is not a competing source of truth
  for the Share Card. It moves out of this module when the comparison artifact lands.
- `frontend/src/utils/evidenceCardStory.js` (`selectTeamStory`,
  `selectComparisonStory`, card versions/angles). Its pure layout constants are
  still consumed by the existing PNG renderer (which now renders only
  artifact-backed data).
- `backend/services/team_story_previews.py` Open Graph composition (static team pages).

**OUT_OF_SCOPE_FOR_THIS_SPRINT** — public `/share/{public_id}` page, final public
artifact API, comparison-vs-shared, PNG/OG renderer redesign, share-action UX
redesign, public engagement analytics (later SC phases).

## Compatibility bridge (temporary — marked for removal)

`services/share_card_compatibility.py` projects a published immutable artifact
into the legacy card-view shape. It performs **no composition** — it is a pure,
deterministic projection of the frozen governed payload, tagged
`source: 'immutable_share_artifact'`. It exists only so the surface can consume
the canonical artifact instead of composing one, and it is deleted once the
SC-06/SC-07 renderer reads the canonical payload directly.

## What remains temporarily legacy

The only legacy piece still on the active path is the **presentational browser PNG
renderer** (`evidenceCardRenderer.js` / `evidenceCardText.js`) and the
`EvidenceShareMenu` controls that drive it — they render and present only the
artifact-backed projection (they compose no intelligence). Replacing them so they
read the canonical payload directly, and then deleting the deprecated composer
modules and the compatibility bridge, is SC-06/SC-07 scope. No new legacy or
duplicate generation path was added, and the browser no longer composes card
intelligence, so there is one authoritative content path today: the immutable
Share Artifact.
