"""SP-10-owned immutable public read-model candidate builders."""

from __future__ import annotations

from copy import deepcopy

from services.availability_reference_date import parse_reference_date, product_current_date
from services.game_context import build_team_game_context
from services.public_pitcher_current import build_public_pitcher_current_payload
from services.public_recent_transactions import build_public_recent_transactions
from services.public_team_performance import build_public_team_performance_payload
from services.public_team_relief_work import build_public_team_relief_work_payload
from services.team_board_v2 import (
    build_team_board_core_payload,
    build_team_board_details_payload,
    build_team_board_v2_payload,
    unavailable_section,
)
from services.team_changes import build_team_changes_payload
from services.what_changed_comparison_identity import comparison_identity_from_payload


TEAM_BOARD_VERSION = 'team-board-v2-publication-v1'
WHAT_CHANGED_VERSION = 'what-changed-publication-v1'


def _optional(reason, callback):
    try:
        return callback(), None
    except Exception:
        return None, unavailable_section(reason)


def build_what_changed_candidate(team_id, *, board, snapshot, predecessor_cohort_id=None):
    """Freeze the governed comparison read; never resolve it again at request time."""
    freshness = board.get('freshness') or {}
    comparison_identity = comparison_identity_from_payload(
        getattr(snapshot, 'payload', None)
    )
    payload = build_team_changes_payload(
        int(team_id), freshness=freshness, generated_at=board.get('generated_at'),
        comparison_source_snapshot_id=getattr(snapshot, 'id', None),
        through_date=getattr(snapshot, 'data_through', None),
        comparison_identity=comparison_identity,
    )
    payload['artifact_contract_version'] = WHAT_CHANGED_VERSION
    payload['predecessor_cohort_id'] = predecessor_cohort_id
    if comparison_identity is None:
        payload['publication_comparison_state'] = 'no_predecessor_baseline'
    else:
        payload['publication_comparison_state'] = 'frozen_predecessor_context'
        payload['predecessor_source_snapshot_id'] = comparison_identity.get(
            'previous_snapshot_id'
        )
        payload['current_source_snapshot_id'] = comparison_identity.get(
            'current_snapshot_id'
        )
    return payload


def build_team_board_v2_candidate(
    team_id, *, board, snapshot, what_changed, publication_identity,
):
    """Freeze the existing Team Board v2 composition under one candidate identity."""
    freshness = board.get('freshness') or {}
    represented_date = getattr(snapshot, 'data_through', None)
    reference_date = (
        parse_reference_date(freshness.get('reference_date')) or product_current_date()
    )
    errors = {}
    relief, error = _optional(
        'recent_relief_work_unavailable',
        lambda: build_public_team_relief_work_payload(
            int(team_id), data_through=represented_date, freshness=freshness,
        ),
    )
    if error:
        errors['recent_relief_work'] = error
    transactions, error = _optional(
        'recent_transactions_unavailable',
        lambda: build_public_recent_transactions(int(team_id), reference_date=reference_date),
    )
    if error:
        errors['recent_transactions'] = error
    game_context, error = _optional(
        'game_context_unavailable',
        lambda: build_team_game_context(int(team_id), reference_date=reference_date),
    )
    if error:
        errors['game_context'] = error
    performance, error = _optional(
        'performance_unavailable',
        lambda: build_public_team_performance_payload(int(team_id), board=board),
    )
    if error:
        errors['performance'] = error
    full = build_team_board_v2_payload(
        board,
        recent_relief_work=relief,
        recent_transactions=transactions,
        game_context=game_context,
        performance=performance,
        what_changed=what_changed,
        section_errors=errors,
        publication_identity=deepcopy(publication_identity),
    )
    core = build_team_board_core_payload(
        board, publication_identity=deepcopy(publication_identity),
    )
    details = build_team_board_details_payload(
        board,
        publication_identity=deepcopy(publication_identity),
        recent_relief_work=relief,
        recent_transactions=transactions,
        game_context=game_context,
        performance=performance,
        what_changed=what_changed,
        section_errors=errors,
    )
    return {
        'artifact_contract_version': TEAM_BOARD_VERSION,
        'full': full,
        'core': core,
        'details': details,
    }


__all__ = [
    'TEAM_BOARD_VERSION', 'WHAT_CHANGED_VERSION',
    'build_public_pitcher_current_payload', 'build_team_board_v2_candidate',
    'build_what_changed_candidate',
]
