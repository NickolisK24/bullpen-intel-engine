"""Single-snapshot serving boundary for public bullpen comparison.

D-051 requires both comparison sides to describe the same trusted publication.
This adapter selects the published Dashboard snapshot exactly once per request and
projects both teams into a compact read model from that immutable authority, so a
publication that lands mid-request cannot produce a mixed comparison.
"""

import logging

from flask import jsonify, request

from api.query_params import QueryParamError, parse_positive_int_param, query_param_error_response
from models.slate_game import SlateGame
from services import public_serving_authority as authority
from services.current_bullpen_comparison import build_current_bullpen_comparison
from services.team_directory import valid_team_directory


GAME_MATCHUP_CAPABILITY = 'scheduled_game_matchup_v1'
GAME_MATCHUP_CONTRACT = 'scheduled_game_matchup_entry_v1'
GAME_NOT_FOUND = 'scheduled_game_not_found'
GAME_COMPARISON_UNAVAILABLE = 'scheduled_game_comparison_unavailable'

logger = logging.getLogger(__name__)


def trusted_team_compare_view():
    team_a, error = parse_positive_int_param(request.args, 'team_a')
    if error:
        return query_param_error_response(error)
    team_b, error = parse_positive_int_param(request.args, 'team_b')
    if error:
        return query_param_error_response(error)
    if team_a is None or team_b is None:
        return query_param_error_response(
            QueryParamError(
                'team_a',
                'team_a and team_b query parameters are required.',
            )
        )

    snapshot = authority.dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if snapshot is None:
        return jsonify({
            'capability': 'current_bullpen_comparison_v1',
            'status': 'snapshot_unavailable',
            'reason_code': authority.TEAM_BOARD_UNAVAILABLE,
            'comparison': None,
            'publication_authority': None,
        })

    # The snapshot is selected once. Every domain below is projected from that
    # immutable publication; no Team Board is rebuilt or serialized.
    comparison, reason = build_current_bullpen_comparison(snapshot, team_a, team_b)
    if comparison is None:
        return jsonify({
            'capability': 'current_bullpen_comparison_v1',
            'status': 'snapshot_unavailable',
            'reason_code': reason,
            'comparison': None,
            'publication_authority': authority.publication_authority(snapshot),
        })
    return jsonify({
        'capability': 'current_bullpen_comparison_v1',
        'status': comparison['status'],
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'comparison': comparison,
        'publication_authority': authority.publication_authority(snapshot),
    })


def _game_team_identity(team_id, comparison_team, directory):
    identity = comparison_team if isinstance(comparison_team, dict) else {}
    fallback = directory.get(team_id) if isinstance(directory, dict) else {}
    fallback = fallback if isinstance(fallback, dict) else {}
    return {
        'team_id': team_id,
        'team_name': identity.get('team_name') or fallback.get('team_name'),
        'team_abbreviation': (
            identity.get('team_abbreviation')
            or fallback.get('team_abbreviation')
        ),
    }


def _scheduled_game_context(game, comparison, directory):
    source = game.to_dict() if hasattr(game, 'to_dict') else dict(game or {})
    teams = comparison.get('teams') if isinstance(comparison, dict) else {}
    teams = teams if isinstance(teams, dict) else {}
    away_team_id = source.get('away_team_id')
    home_team_id = source.get('home_team_id')
    return {
        'game_pk': source.get('game_pk'),
        'reference_date': source.get('game_date_et'),
        'game_time_utc': source.get('game_time_utc'),
        'status': dict(source.get('status') or {}),
        'doubleheader_flag': source.get('doubleheader_flag'),
        'game_number': source.get('game_number'),
        'away': _game_team_identity(
            away_team_id, teams.get('team_a'), directory,
        ),
        'home': _game_team_identity(
            home_team_id, teams.get('team_b'), directory,
        ),
    }


def build_scheduled_game_matchup_payload(game, snapshot, *, directory=None):
    """Compose game identity around the unchanged CMP-01 carrier."""
    source = game.to_dict() if hasattr(game, 'to_dict') else dict(game or {})
    away_team_id = source.get('away_team_id')
    home_team_id = source.get('home_team_id')
    comparison = None
    reason = GAME_COMPARISON_UNAVAILABLE
    if snapshot is not None and away_team_id is not None and home_team_id is not None:
        try:
            comparison, reason = build_current_bullpen_comparison(
                snapshot, away_team_id, home_team_id,
            )
        except Exception:  # noqa: BLE001 - comparison is optional to game identity
            logger.warning(
                'Scheduled game matchup comparison failed for game_pk=%s.',
                source.get('game_pk'),
                exc_info=True,
            )
    return {
        'capability': GAME_MATCHUP_CAPABILITY,
        'contract': GAME_MATCHUP_CONTRACT,
        'status': (
            comparison.get('status')
            if isinstance(comparison, dict)
            else 'partial'
        ),
        'reason_code': None if comparison is not None else reason,
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'game': _scheduled_game_context(game, comparison, directory or {}),
        'comparison': comparison,
        'publication_authority': (
            authority.publication_authority(snapshot) if snapshot is not None else None
        ),
    }


def trusted_game_matchup_view(game_pk):
    """Serve one scheduled game with the shared current comparison carrier."""
    game = SlateGame.query.filter_by(game_pk=game_pk).one_or_none()
    if game is None:
        return jsonify({
            'capability': GAME_MATCHUP_CAPABILITY,
            'contract': GAME_MATCHUP_CONTRACT,
            'status': 'not_found',
            'reason_code': GAME_NOT_FOUND,
            'game': None,
            'comparison': None,
        }), 404

    # The directory only supplies game-shell display identity when the comparison
    # domain is unavailable. It does not author or alter comparison facts.
    try:
        directory = valid_team_directory()
    except Exception:  # noqa: BLE001 - display identity can fall back to carrier ids
        logger.warning(
            'Scheduled game matchup team directory failed for game_pk=%s.',
            game_pk,
            exc_info=True,
        )
        directory = {}
    try:
        snapshot = authority.dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    except Exception:  # noqa: BLE001 - game identity remains independently useful
        logger.warning(
            'Scheduled game matchup snapshot read failed for game_pk=%s.',
            game_pk,
            exc_info=True,
        )
        snapshot = None
    return jsonify(build_scheduled_game_matchup_payload(
        game,
        snapshot,
        directory=directory,
    ))
