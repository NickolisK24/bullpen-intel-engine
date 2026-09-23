"""Answer-first, publication-identified Team Board delivery endpoints."""

from flask import Blueprint, current_app, jsonify, request

from api.bullpen import _freshness_reference_date
from services import dashboard_snapshot as dashboard_snapshot_service
from services.game_context import build_team_game_context
from services.public_serving_authority import build_published_team_board
from services.public_team_relief_work import (
    TeamNotFoundError,
    build_public_team_relief_work_payload,
)
from services.public_delivery import apply_public_delivery_headers
from services.team_board_delivery import (
    TeamBoardIdentityMismatch,
    build_team_board_identity,
    require_matching_team_board_identity,
    resolve_team_board_snapshot,
)
from services.team_board_v2 import (
    build_team_board_core_payload,
    build_team_board_details_payload,
    build_team_board_v2_payload,
    unavailable_section,
)
from utils.db import db


team_board_v2_bp = Blueprint('team_board_v2', __name__)


def _optional_failure(section, reason_code, operation):
    try:
        return operation(), None
    except Exception:
        current_app.logger.exception(
            'Team Board optional section failed: section=%s.', section,
        )
        return None, unavailable_section(reason_code)


def _team_missing(board):
    team = board.get('team') or {}
    return team.get('team_name') is None and team.get('team_abbreviation') is None


def _select_core_board(team_id, *, include_recent_usage_rest=False):
    """Select the trusted publication once and keep it for every core field."""
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if snapshot is None:
        return None, build_published_team_board(
            team_id, snapshot_override=snapshot,
        ), None
    board_kwargs = {
        'snapshot_override': snapshot,
        'include_delivery_identity': True,
    }
    if include_recent_usage_rest:
        board_kwargs['include_recent_usage_rest'] = True
    board = build_published_team_board(team_id, **board_kwargs)
    identity = build_team_board_identity(snapshot, board)
    return snapshot, board, identity


def _identity_from_request():
    return {key: request.args.get(key) for key in (
        'contract', 'team_id', 'team_abbreviation', 'snapshot_id',
        'sync_run_id', 'represented_date', 'availability_reference_date',
        'published_at', 'snapshot_generated_at', 'dashboard_payload_version',
        'publication_authority_contract', 'team_board_package_contract',
        'team_board_contract_version', 'team_state_contract',
        'bullpen_membership_method_version', 'rest_status_method_version',
        'workload_windows_method_version', 'deployment_profile_method_version',
        'rotation_impact_method_version',
    )}


def _build_deferred_sections(team_id, board, snapshot):
    section_errors = {}
    represented_date = snapshot.data_through
    freshness = board.get('freshness') or {}

    # TB-10 is frozen with the selected trusted package. The legacy read is
    # retained only as an older-snapshot input for TB-03/TB-04 compatibility;
    # it is never exposed as the new TB-10 ledger.
    relief_work = board.get('frozen_recent_relief_work')
    legacy_relief_work = None
    if relief_work is None or board.get('workload_overview') is None:
        try:
            legacy_relief_work = build_public_team_relief_work_payload(
                team_id,
                data_through=represented_date,
                freshness=freshness,
            )
        except TeamNotFoundError:
            raise
        except Exception:
            current_app.logger.exception(
                'Team Board compatibility section failed: section=legacy_relief_work.'
            )

    reference_date = _freshness_reference_date(freshness)
    game_context, game_error = _optional_failure(
        'game_context', 'game_context_unavailable',
        lambda: build_team_game_context(team_id, reference_date=reference_date),
    )
    if game_error:
        section_errors['game_context'] = game_error

    # TB-08 is attached only from the selected trusted package. Older packages
    # lack the carrier; mutable transaction rows cannot fill that gap.
    recent_transactions = board.get('frozen_roster_transactions')

    # New trusted packages carry this read by value. An older package simply
    # lacks TB-06; mutable GameLog rows must not synthesize it at request time.
    performance = board.get('frozen_performance')

    # TB-09 is authored during trusted publication. Older packages intentionally
    # lack it; mutable rows must not synthesize a comparison at request time.
    what_changed = board.get('frozen_what_changed')

    return {
        'recent_relief_work': relief_work,
        'legacy_relief_work': legacy_relief_work,
        'recent_transactions': recent_transactions,
        'game_context': game_context,
        'performance': performance,
        'what_changed': what_changed,
        'section_errors': section_errors,
    }


@team_board_v2_bp.route('/teams/<int:team_id>/board-v2/core', methods=['GET'])
def get_team_board_core(team_id):
    snapshot, board, identity = _select_core_board(team_id)
    if _team_missing(board):
        return jsonify({'error': 'team_not_found'}), 404
    if snapshot is None or identity is None:
        response = jsonify({
            'capability': 'team_board_answer_core',
            'status': 'snapshot_unavailable',
            'reason_code': 'trusted_team_board_unavailable',
            'publication_identity': None,
        })
        response.status_code = 503
        return apply_public_delivery_headers(
            response,
            resource='team_board_answer_core',
            identity=None,
            available=False,
        )
    payload = build_team_board_core_payload(
        board, publication_identity=identity,
    )
    return apply_public_delivery_headers(
        jsonify(payload),
        resource='team_board_answer_core',
        identity=identity,
        contract_version=payload.get('contract_version'),
    )


@team_board_v2_bp.route('/teams/<int:team_id>/board-v2/details', methods=['GET'])
def get_team_board_details(team_id):
    requested_identity = _identity_from_request()
    try:
        snapshot, normalized = resolve_team_board_snapshot(
            requested_identity, team_id=team_id, session=db.session,
        )
        board = build_published_team_board(
            team_id,
            snapshot_override=snapshot,
            include_delivery_identity=True,
            include_recent_usage_rest=True,
        )
        require_matching_team_board_identity(normalized, snapshot, board)
    except TeamBoardIdentityMismatch as exc:
        response = jsonify({
            'capability': 'team_board_deferred_details',
            'status': 'identity_mismatch',
            'reason_code': str(exc),
            'publication_identity': None,
        })
        response.status_code = 409
        return apply_public_delivery_headers(
            response,
            resource='team_board_deferred_details',
            identity=None,
            available=False,
        )

    if _team_missing(board):
        return jsonify({'error': 'team_not_found'}), 404
    try:
        sections = _build_deferred_sections(team_id, board, snapshot)
    except TeamNotFoundError:
        return jsonify({'error': 'team_not_found'}), 404
    payload = build_team_board_details_payload(
        board, publication_identity=normalized, **sections,
    )
    return apply_public_delivery_headers(
        jsonify(payload),
        resource='team_board_deferred_details',
        identity=normalized,
        contract_version=payload.get('contract_version'),
    )


@team_board_v2_bp.route('/teams/<int:team_id>/board-v2', methods=['GET'])
def get_team_board_v2(team_id):
    """Compatibility composition using one selected publication identity."""
    snapshot, board, identity = _select_core_board(
        team_id, include_recent_usage_rest=True,
    )
    if _team_missing(board):
        return jsonify({'error': 'team_not_found'}), 404
    if snapshot is None or identity is None:
        return jsonify(build_team_board_v2_payload(
            board, publication_identity=None,
        ))
    try:
        sections = _build_deferred_sections(team_id, board, snapshot)
    except TeamNotFoundError:
        return jsonify({'error': 'team_not_found'}), 404
    return jsonify(build_team_board_v2_payload(
        board, publication_identity=identity, **sections,
    ))
