"""Authenticated user surfaces (Phase D1D — server-side team following).

The /api/me/* routes require a valid bearer token (via require_authenticated_user)
and let a signed-in user durably follow teams. No frontend, onboarding,
notification, or preference surface is added here. Public endpoints are
untouched and remain anonymous-compatible.

Primary-team policy (deterministic, at most one primary per user):
  • the first team a user follows becomes primary;
  • following with is_primary=true (or PUT /primary-team) moves the primary;
  • deleting the primary promotes the earliest remaining follow, or clears the
    primary when no follows remain.
"""

from flask import Blueprint, g, jsonify, request

from models.user import UserFollowedTeam
from services.team_directory import is_valid_team_id
from utils.db import db
from utils.identity import require_authenticated_user
from utils.time import utc_now_naive


me_bp = Blueprint('me', __name__)


def _coerce_team_id(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ordered(user):
    """Follows in a stable, deterministic order (oldest first)."""
    return sorted(
        user.followed_teams,
        key=lambda follow: (follow.created_at or utc_now_naive(), follow.id or 0),
    )


def _set_primary(user, team_id):
    for follow in user.followed_teams:
        follow.is_primary = follow.team_id == team_id


def _ensure_single_primary(user):
    """Enforce exactly one primary among existing follows (deterministically)."""
    follows = _ordered(user)
    if not follows:
        return
    primaries = [follow for follow in follows if follow.is_primary]
    if len(primaries) == 1:
        return
    keep = primaries[0] if primaries else follows[0]
    for follow in follows:
        follow.is_primary = follow is keep


def _serialize(user):
    follows = _ordered(user)
    primary = next((follow.team_id for follow in follows if follow.is_primary), None)
    return {
        'teams': [follow.to_dict() for follow in follows],
        'primary_team_id': primary,
    }


@me_bp.route('/teams', methods=['GET'])
@require_authenticated_user
def list_followed_teams():
    """List the current user's followed teams and primary (empty when none)."""
    return jsonify(_serialize(g.current_user)), 200


@me_bp.route('/teams', methods=['POST'])
@require_authenticated_user
def follow_team():
    """Follow a team (idempotent). The first follow, or is_primary=true, sets primary."""
    user = g.current_user
    data = request.get_json(silent=True) or {}
    team_id = _coerce_team_id(data.get('team_id'))
    if team_id is None or not is_valid_team_id(team_id):
        return jsonify({'error': 'invalid_team_id'}), 400

    existing = next((f for f in user.followed_teams if f.team_id == team_id), None)
    first_follow = len(user.followed_teams) == 0
    if existing is None:
        user.followed_teams.append(
            UserFollowedTeam(team_id=team_id, created_at=utc_now_naive())
        )

    if bool(data.get('is_primary')) or first_follow:
        _set_primary(user, team_id)
    else:
        _ensure_single_primary(user)

    db.session.commit()
    return jsonify(_serialize(user)), 200


@me_bp.route('/teams/<int:team_id>', methods=['DELETE'])
@require_authenticated_user
def unfollow_team(team_id):
    """Unfollow a team (idempotent). Removing the primary promotes the earliest left."""
    user = g.current_user
    follow = next((f for f in user.followed_teams if f.team_id == team_id), None)
    if follow is not None:
        was_primary = follow.is_primary
        user.followed_teams.remove(follow)
        if was_primary:
            _ensure_single_primary(user)
        db.session.commit()
    return jsonify(_serialize(user)), 200


@me_bp.route('/primary-team', methods=['PUT'])
@require_authenticated_user
def set_primary_team():
    """Set the primary team, following it first if it is not already followed."""
    user = g.current_user
    data = request.get_json(silent=True) or {}
    team_id = _coerce_team_id(data.get('team_id'))
    if team_id is None or not is_valid_team_id(team_id):
        return jsonify({'error': 'invalid_team_id'}), 400

    existing = next((f for f in user.followed_teams if f.team_id == team_id), None)
    if existing is None:
        user.followed_teams.append(
            UserFollowedTeam(team_id=team_id, created_at=utc_now_naive())
        )
    _set_primary(user, team_id)
    db.session.commit()
    return jsonify(_serialize(user)), 200
