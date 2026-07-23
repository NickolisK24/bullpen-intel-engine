"""Transitional read surface for artifact-backed Team State Share Cards
(Share Cards SC-03A cutover).

This narrow, transitional endpoint lets the existing Share Card entry points
consume the canonical immutable artifact instead of composing card intelligence
in the browser. It serves ONLY the published, integrity-verified immutable
artifact via the compatibility projection:

    published immutable Share Artifact -> integrity verification
      -> share_card_compatibility projection -> frontend

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

from flask import Blueprint, jsonify

from services.share_artifact_integrity import ShareArtifactIntegrityError


share_cards_bp = Blueprint('share_cards', __name__)


@share_cards_bp.route('/team-state/<int:team_id>', methods=['GET'])
def get_team_state_share_card(team_id):
    # Import lazily so app import never pulls the artifact graph at load time.
    from services.share_card_compatibility import get_team_state_card

    try:
        card = get_team_state_card(team_id)
    except ShareArtifactIntegrityError:
        # Fail closed: a tampered/unverifiable artifact is never served.
        return jsonify({'available': False, 'reason': 'integrity_unverified'}), 503
    except Exception:
        return jsonify({'available': False, 'reason': 'unavailable'}), 503

    if card is None:
        # No published artifact yet — controlled unavailable, never fabricated.
        return jsonify({'available': False, 'reason': 'no_published_artifact'}), 200

    return jsonify({'available': True, 'card': card}), 200
