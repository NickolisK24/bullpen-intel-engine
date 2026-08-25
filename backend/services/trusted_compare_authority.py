"""Single-snapshot serving boundary for public bullpen comparison.

D-051 requires both comparison sides to describe the same trusted publication.
This adapter selects the published Dashboard snapshot exactly once per request and
projects both teams into a compact read model from that immutable authority, so a
publication that lands mid-request cannot produce a mixed comparison.
"""

from flask import jsonify, request

from api.query_params import QueryParamError, parse_positive_int_param, query_param_error_response
from services import public_serving_authority as authority
from services.current_bullpen_comparison import build_current_bullpen_comparison


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
