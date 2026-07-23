"""Temporary Share Cards compatibility adapter (Share Cards SC-03A).

MARKED FOR REMOVAL — REMOVE_LATER.

This adapter exists only so the existing Share Cards surface can consume the
canonical immutable Share Artifact instead of composing card intelligence
itself. It performs **no composition**: it is a pure, deterministic projection
of a published artifact's frozen, governed payload into the shape the legacy
surface expects. It creates no free-form copy, no fallbacks, and no new
intelligence.

It is deliberately isolated in its own module and returns a ``source:
'immutable_share_artifact'`` provenance marker so the temporary boundary is
obvious. It will be deleted once the SC-06/SC-07 renderer consumes the canonical
payload directly. Until then it is the single bridge that keeps one authoritative
content path: the immutable artifact.
"""

from __future__ import annotations

from typing import Optional

from services.share_artifact_repository import get_latest_published_team_state_artifact
from services.share_artifacts import verify_share_artifact_integrity
from utils.db import db


COMPATIBILITY_SOURCE = 'immutable_share_artifact'


def build_share_card_compatibility_view(artifact) -> dict:
    """Project a published Team State artifact into the legacy card view shape.

    Verifies integrity first and fails closed on mismatch. Every field is read
    directly from the immutable payload — nothing is composed here.
    """
    verify_share_artifact_integrity(artifact)

    document = dict(artifact.payload or {})
    team = document.get('team') if isinstance(document.get('team'), dict) else {}
    team_state = document.get('team_state') if isinstance(document.get('team_state'), dict) else {}
    trust = document.get('trust') if isinstance(document.get('trust'), dict) else {}
    authority = document.get('authority') if isinstance(document.get('authority'), dict) else {}
    constraints = team_state.get('constraints') if isinstance(team_state.get('constraints'), list) else []

    return {
        'source': COMPATIBILITY_SOURCE,
        'public_id': artifact.public_id,
        'artifact_type': artifact.artifact_type,
        'render_version': artifact.render_version,
        'payload_version': document.get('payload_version'),
        'team': {
            'team_id': team.get('team_id'),
            'team_name': team.get('team_name'),
            'team_abbreviation': team.get('team_abbreviation'),
        },
        'headline': team_state.get('status_label'),
        'status_code': team_state.get('status_code'),
        'summary': team_state.get('summary'),
        'receipts': [
            {'category': item.get('category'), 'detail': item.get('message')}
            for item in constraints
            if isinstance(item, dict)
        ],
        'product_date': authority.get('data_through'),
        'trust': {
            'confidence': trust.get('confidence'),
            'freshness_state': trust.get('freshness_state'),
        },
    }


def get_team_state_card(team_id: int, *, session=None) -> Optional[dict]:
    """The canonical Team State card view for a team, or ``None`` if none exists.

    This is the cutover bridge: the existing entry point resolves its card from
    the latest published immutable artifact (integrity-verified) instead of
    composing one. Returns ``None`` when no published artifact exists — the
    surface must degrade honestly rather than fabricate a card.
    """
    session = session or db.session
    artifact = get_latest_published_team_state_artifact(team_id, session=session)
    if artifact is None:
        return None
    return build_share_card_compatibility_view(artifact)
