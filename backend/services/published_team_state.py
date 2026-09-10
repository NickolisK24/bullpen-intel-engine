"""Shared projection from one immutable artifact to governed public Team State.

The helper is intentionally database-free and batch-friendly. Callers own
artifact selection; this module verifies the selected artifact and re-projects
its frozen status through the one public Team State vocabulary owner.
"""

from __future__ import annotations

from typing import Mapping

from services.share_artifacts import verify_share_artifact_integrity
from services.team_state_public_vocabulary import (
    TEAM_STATE_READINESS_UNAVAILABLE,
    public_team_state,
    team_state_unavailable,
)


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def project_published_team_state_artifact(artifact, *, data_through=None) -> dict:
    """Project one selected published artifact, failing closed when unusable."""
    fallback_data_through = _iso(data_through)
    if artifact is None:
        return team_state_unavailable(
            TEAM_STATE_READINESS_UNAVAILABLE,
            data_through=fallback_data_through,
            reason_code='published_team_state_artifact_missing',
        )

    try:
        verify_share_artifact_integrity(artifact)
    except Exception:
        return team_state_unavailable(
            TEAM_STATE_READINESS_UNAVAILABLE,
            data_through=fallback_data_through,
            reason_code='published_team_state_artifact_integrity_failed',
        )

    document = artifact.payload if isinstance(artifact.payload, Mapping) else {}
    team_state = (
        document.get('team_state')
        if isinstance(document.get('team_state'), Mapping)
        else {}
    )
    authority = (
        document.get('authority')
        if isinstance(document.get('authority'), Mapping)
        else {}
    )
    readiness = {
        'contract_state': team_state.get('contract_state'),
        'readiness': {'status_code': team_state.get('status_code')},
        'freshness': {
            'data_through': authority.get('data_through') or fallback_data_through,
        },
    }
    return public_team_state(readiness)
