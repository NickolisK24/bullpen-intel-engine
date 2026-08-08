"""Single-snapshot serving boundary for public bullpen comparison.

D-051 requires both comparison sides to describe the same trusted publication.
This adapter selects the published Dashboard snapshot exactly once per request and
renders both team boards from that immutable authority, so a publication that
lands mid-request cannot produce a mixed comparison.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Mapping

from flask import jsonify, request

from api.query_params import QueryParamError, parse_positive_int_param, query_param_error_response
from services import public_serving_authority as authority
from services.bullpen_board import build_board_payload
from services.bullpen_comparison import build_team_comparison


def _board_from_snapshot(snapshot, team_id, *, include_stale=False, freshness=None):
    team_package, reason = authority._team_package(snapshot, team_id)
    if team_package is None:
        return authority._unavailable_board(team_id, reason, snapshot=snapshot)

    freshness = dict(freshness or authority._trusted_board_freshness(snapshot))
    records = authority._records_for_view(team_package, include_stale)
    payload = build_board_payload(
        team=deepcopy(team_package.get('team') or {'team_id': team_id}),
        records=records,
        freshness=freshness,
        limitations=list(freshness.get('limitations') or []),
        roster_authority=deepcopy(team_package.get('roster_authority') or {}),
        generated_at=(
            snapshot.snapshot_generated_at.isoformat()
            if snapshot.snapshot_generated_at
            else None
        ),
        workload_concentration=deepcopy(
            team_package.get('workload_concentration') or {}
        ),
        capacity_intelligence=deepcopy(
            team_package.get('capacity_intelligence') or {}
        ),
        rotation_support_pressure=deepcopy(
            team_package.get('rotation_support_pressure') or {}
        ),
        bullpen_stability=deepcopy(team_package.get('bullpen_stability') or {}),
        bullpen_environment=deepcopy(team_package.get('bullpen_environment') or {}),
    )
    payload['team_state'] = authority._published_team_state(snapshot, team_id)
    payload['publication_authority'] = authority._publication_authority(snapshot)
    payload['served_from'] = 'trusted_dashboard_snapshot'
    return payload


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

    include_stale = authority._truthy(request.args.get('include_stale'))
    snapshot = authority.dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if snapshot is None:
        board_a = authority._unavailable_board(
            team_a, authority.TEAM_BOARD_UNAVAILABLE, snapshot=None
        )
        board_b = authority._unavailable_board(
            team_b, authority.TEAM_BOARD_UNAVAILABLE, snapshot=None
        )
        publication_authority = None
    else:
        # One freshness overlay and one snapshot selection for the whole response.
        # A new publication may land after this point, but this request remains a
        # coherent read of the authority it selected at entry.
        freshness = authority._trusted_board_freshness(snapshot)
        board_a = _board_from_snapshot(
            snapshot,
            team_a,
            include_stale=include_stale,
            freshness=freshness,
        )
        board_b = _board_from_snapshot(
            snapshot,
            team_b,
            include_stale=include_stale,
            freshness=freshness,
        )
        publication_authority = authority._publication_authority(snapshot)

    comparison = build_team_comparison(
        board_a,
        board_b,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    unavailable = (
        board_a.get('status') == 'snapshot_unavailable'
        or board_b.get('status') == 'snapshot_unavailable'
    )
    return jsonify({
        'capability': 'team_bullpen_comparison',
        'status': 'snapshot_unavailable' if unavailable else 'ok',
        'generated_at': comparison['generated_at'],
        'ranking_applied': False,
        'selection_made': False,
        'team_a': board_a,
        'team_b': board_b,
        'comparison': comparison,
        'publication_authority': publication_authority,
    })
