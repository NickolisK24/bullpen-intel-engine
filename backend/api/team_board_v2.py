"""Read-only Team Board v2 composition endpoint."""

from flask import Blueprint, current_app, jsonify

from api.bullpen import (
    _build_team_board,
    _freshness_reference_date,
    _rotation_support_for_team,
)
from services.game_context import build_team_game_context
from services.public_team_relief_work import (
    TeamNotFoundError,
    build_public_team_relief_work_payload,
)
from services.public_recent_transactions import build_public_recent_transactions
from services.team_board_v2 import build_team_board_v2_payload, unavailable_section


team_board_v2_bp = Blueprint('team_board_v2', __name__)


def _optional_failure(section, reason_code, operation):
    try:
        return operation(), None
    except Exception:
        current_app.logger.exception(
            'Team Board v2 optional section failed: section=%s.',
            section,
        )
        return None, unavailable_section(reason_code)


@team_board_v2_bp.route('/teams/<int:team_id>/board-v2', methods=['GET'])
def get_team_board_v2(team_id):
    section_errors = {}

    def rotation_builder(team, reference_date):
        rotation, error = _optional_failure(
            'rotation_impact',
            'rotation_impact_unavailable',
            lambda: _rotation_support_for_team(team, reference_date),
        )
        if error:
            section_errors['rotation_impact'] = error
        return rotation or {}

    board = _build_team_board(team_id, rotation_builder=rotation_builder)
    team = board.get('team') or {}
    if team.get('team_name') is None and team.get('team_abbreviation') is None:
        return jsonify({'error': 'team_not_found'}), 404

    try:
        relief_work = build_public_team_relief_work_payload(team_id)
    except TeamNotFoundError:
        return jsonify({'error': 'team_not_found'}), 404
    except Exception:
        current_app.logger.exception(
            'Team Board v2 optional section failed: section=recent_relief_work.'
        )
        relief_work = None
        section_errors['recent_relief_work'] = unavailable_section(
            'recent_relief_work_unavailable'
        )

    game_context, game_error = _optional_failure(
        'game_context',
        'game_context_unavailable',
        lambda: build_team_game_context(
            team_id,
            reference_date=_freshness_reference_date(board.get('freshness') or {}),
        ),
    )
    if game_error:
        section_errors['game_context'] = game_error

    recent_transactions, transactions_error = _optional_failure(
        'recent_transactions',
        'recent_transactions_unavailable',
        lambda: build_public_recent_transactions(
            team_id,
            reference_date=_freshness_reference_date(board.get('freshness') or {}),
        ),
    )
    if transactions_error:
        section_errors['recent_transactions'] = transactions_error

    return jsonify(build_team_board_v2_payload(
        board,
        recent_relief_work=relief_work,
        recent_transactions=recent_transactions,
        game_context=game_context,
        section_errors=section_errors,
    ))
