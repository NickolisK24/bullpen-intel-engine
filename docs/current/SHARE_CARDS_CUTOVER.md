# Share Cards Cutover — SC-03A

Share Cards is one product. This note records the SC-03A step that moves card
**intelligence generation** onto the immutable Share Artifact architecture
(SC-01 domain + SC-02 eligibility/payload) and what remains temporarily legacy.

There is no "V2" and no user-facing version toggle. After cutover completes
(SC-06/SC-07), the immutable artifact is the single authoritative content path.

## Authoritative path (this sprint)

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
— is recorded in `share_artifact_generation_audits`.

## Legacy audit classification

**KEEP_AND_ADAPT** — consume the canonical artifact; never compose intelligence.
- `frontend/src/components/share/EvidenceShareMenu.jsx`, `frontend/src/utils/shareActions.js`,
  `evidenceCardRenderer.js`, `evidenceCardText.js` (render/present only).
- Share-action tracking (`backend/models/traffic_share_action.py`,
  `backend/services/traffic_share_actions.py`, `traffic_reporting.py`,
  `backend/api/traffic.py`) — observational only; unchanged.

**REPLACE** — these compose mutable, client-side card intelligence and are
superseded by the server generation path above.
- `frontend/src/utils/evidenceCardModel.js` (`buildTeamEvidenceCard`)
- `frontend/src/utils/evidenceCardStory.js` (`selectTeamStory`, card versions/angles)

**REMOVE_LATER** — cannot be deleted in a backend-only sprint without breaking
production, and their replacement requires the renderer to consume the canonical
payload (SC-06/SC-07).
- The client-side composition in the three entry points
  (`TonightsBullpenBoard.jsx`, `BullpenComparisonView.jsx`, `Stories.jsx`).
- `backend/services/team_story_previews.py` Open Graph composition (static team pages).

**OUT_OF_SCOPE_FOR_THIS_SPRINT** — public `/share/{public_id}` page, public
artifact API, comparison-vs-shared, PNG/OG renderer redesign, share-action UX
redesign, public engagement analytics (later SC phases).

## Compatibility bridge (temporary — marked for removal)

`services/share_card_compatibility.py` projects a published immutable artifact
into the legacy card-view shape. It performs **no composition** — it is a pure,
deterministic projection of the frozen governed payload, tagged
`source: 'immutable_share_artifact'`. It exists only so the surface can consume
the canonical artifact instead of composing one, and it is deleted once the
SC-06/SC-07 renderer reads the canonical payload directly.

## Why the frontend still composes for now

The legacy card is composed in the browser and rendered to PNG there. Switching
the three entry points to the server path requires the renderer to consume the
canonical payload, which is SC-06/SC-07 scope. SC-03A therefore establishes the
authoritative server path, the audit, the repository, and the compatibility
bridge, and defers the frontend switch — the escape hatch the Share Cards V1
spec permits. No new legacy generation path was added, and the backend never
composed card intelligence (it only tracked shares), so there is one
authoritative content path today: the immutable artifact.
