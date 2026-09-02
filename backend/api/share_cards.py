"""Transitional read surface for artifact-backed Team State Share Cards
(Share Cards SC-03A cutover).

This narrow Team Board entry endpoint resolves the latest active immutable Team
State artifact and returns its canonical public projection. The legacy
compatibility projection remains additive for older consumers while the active
share UI reads ``artifact``:

    published immutable Share Artifact -> integrity verification
      -> canonical public projection -> frontend

It never composes intelligence, never falls back to legacy composition, never
mints an artifact, never serves a withdrawn/superseded artifact as active, and
exposes no admin/audit data. When no published artifact exists it returns a
controlled "unavailable" result rather than fabricating a card.

It reuses the existing public read pattern: the team operating-state data it
projects is already served publicly by the team board, and this endpoint is
strictly more governed (published + eligibility-gated + integrity-verified). It
is NOT the final public ``/share/{public_id}`` page or public artifact API
contract — those remain deferred.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from services.share_artifact_integrity import ShareArtifactIntegrityError


share_cards_bp = Blueprint('share_cards', __name__)


@share_cards_bp.route('/team-state/<int:team_id>', methods=['GET'])
def get_team_state_share_card(team_id):
    # Import lazily so app import never pulls the artifact graph at load time.
    from services.share_artifact_public import RESULT_OK, project_public_share_artifact
    from services.share_artifact_repository import get_latest_published_team_state_artifact
    from services.share_card_compatibility import build_share_card_compatibility_view

    try:
        artifact = get_latest_published_team_state_artifact(team_id)
        public_result = project_public_share_artifact(artifact)
        card = build_share_card_compatibility_view(artifact) if artifact is not None else None
    except ShareArtifactIntegrityError:
        # Fail closed: a tampered/unverifiable artifact is never served.
        return jsonify({'available': False, 'reason': 'integrity_unverified'}), 503
    except Exception:
        return jsonify({'available': False, 'reason': 'unavailable'}), 503

    if artifact is None or card is None or public_result.status != RESULT_OK:
        # No published artifact yet — controlled unavailable, never fabricated.
        return jsonify({'available': False, 'reason': 'no_published_artifact'}), 200

    return jsonify({
        'available': True,
        'artifact': public_result.view,
        # Transitional response field for any older client still consuming the
        # SC-03A shape. The active Team Board renderer uses ``artifact`` only.
        'card': card,
    }), 200


@share_cards_bp.route('/since-yesterday/<int:team_id>', methods=['GET'])
def get_since_yesterday_share_artifact(team_id):
    """Read one exact, immutable published bullpen-change citation."""
    from services.share_artifact_public import RESULT_OK, project_public_share_artifact
    from services.share_artifact_repository import (
        get_published_since_yesterday_change_artifact,
    )
    from services.what_changed_comparison_identity import normalize_comparison_identity

    comparison_identity = {
        'contract': request.args.get('comparison_contract'),
        'comparison_authority': request.args.get('comparison_authority'),
        'method_version': request.args.get('comparison_method_version'),
        'previous_snapshot_id': request.args.get('previous_snapshot_id'),
        'current_snapshot_id': request.args.get('current_snapshot_id'),
        'previous_sync_run_id': request.args.get('previous_sync_run_id'),
        'current_sync_run_id': request.args.get('current_sync_run_id'),
        'previous_payload_version': request.args.get('previous_payload_version'),
        'current_payload_version': request.args.get('current_payload_version'),
        'previous_data_through': request.args.get('previous_data_through'),
        'current_data_through': request.args.get('current_data_through'),
        'previous_publication_state': request.args.get('previous_publication_state'),
        'current_publication_state': request.args.get('current_publication_state'),
    }
    try:
        comparison_identity = normalize_comparison_identity(comparison_identity)
        artifact = get_published_since_yesterday_change_artifact(
            team_id,
            comparison_identity=comparison_identity,
        )
        result = project_public_share_artifact(artifact)
    except (TypeError, ValueError):
        return jsonify({'available': False, 'reason': 'comparison_identity_invalid'}), 200
    except Exception:
        return jsonify({'available': False, 'reason': 'unavailable'}), 503

    if artifact is None:
        return jsonify({'available': False, 'reason': 'no_published_artifact'}), 200
    if result.status != RESULT_OK:
        return jsonify({'available': False, 'reason': result.status}), 503
    return jsonify({'available': True, 'artifact': result.view}), 200
