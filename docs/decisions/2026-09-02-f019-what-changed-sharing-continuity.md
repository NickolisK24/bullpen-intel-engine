# F-019 What Changed Sharing Continuity

## Decision

The public Since Yesterday renderer and immutable share citation use one exact
backend-owned comparison identity. The identity names the prior and current
trusted Dashboard publications, their represented dates, sync runs, payload
versions, the governed What Changed capability, and its method version.

The identity is attached in `backend/services/dashboard_snapshot.py` before a
candidate publication becomes current. Its validation owner is
`backend/services/what_changed_comparison_identity.py`.

The bounded transport and citation paths are:

- `backend/api/bullpen.py`
- `backend/api/share_cards.py`
- `backend/services/share_artifact_repository.py`
- `backend/services/share_artifact_since_yesterday.py`
- `frontend/src/components/home/IntelligenceSurface.jsx`
- `frontend/src/utils/sinceYesterdayArtifact.js`

The share layer no longer selects a latest or approximate date pair. Missing,
forged, reversed, unpublished, team-mismatched, or version-incompatible
identity fails closed. Existing immutable artifacts are not rewritten.

## Preserved boundaries

This decision does not alter Team State, Arm Read, workload, roster, role,
performance, Landscape, Daily Edition, matchup, history, or prediction
semantics. It does not change the F-008 canonical share route or the F-016
crawler contract.
