"""Additive public Team Board v2 composition contract.

This module rearranges already-governed public read models for one Team Board
consumer. It does not query, classify, score, publish, or persist anything.
"""

from __future__ import annotations

from copy import deepcopy


CAPABILITY = 'team_board_v2'
CONTRACT_VERSION = 'team-board-2.0.0'

STATUS_AVAILABLE = 'available'
STATUS_PARTIAL = 'partial'
STATUS_UNAVAILABLE = 'unavailable'

ACTIVE_BULLPEN_POPULATION_BASIS = 'current_scored_bullpen_eligible_pitchers'
RECENT_RELIEF_WORK_POPULATION_BASIS = 'official_appearance_team_relief_appearances'
ROTATION_IMPACT_POPULATION_BASIS = 'stored_team_game_pitching_splits'


def unavailable_section(reason_code, *, limitations=None):
    return {
        'status': STATUS_UNAVAILABLE,
        'reason_code': reason_code,
        'limitations': list(limitations or []),
        'represented_date': None,
    }


def _section_status(status, *, reason_code=None, limitations=None, represented_date=None):
    return {
        'status': status,
        'reason_code': reason_code,
        'limitations': list(limitations or []),
        'represented_date': represented_date,
    }


def _active_arms(board):
    arms = []
    for group in board.get('groups') or []:
        for card in group.get('pitchers') or []:
            visibility = card.get('visibility') or {}
            if visibility.get('is_visible_by_default') is False:
                continue
            facts = card.get('workload_facts') or {}
            arms.append({
                'pitcher_id': card.get('pitcher_id'),
                'name': card.get('name'),
                'public_role_read': deepcopy(card.get('public_role_read')),
                'public_labels': deepcopy(card.get('pitcher_labels')),
                'availability': {
                    'status': card.get('availability_status'),
                    'label': card.get('availability_public_label'),
                    'confidence': card.get('confidence'),
                    'data_state': card.get('data_state'),
                    'short_reason': card.get('short_reason'),
                    'reasons': deepcopy(card.get('reasons') or []),
                    'limitations': deepcopy(card.get('limitations') or []),
                },
                'last_appearance': deepcopy(card.get('last_appearance')),
                'workload': {
                    'days_since_last_appearance': facts.get('days_since_last_appearance'),
                    'appearances_last_7': facts.get('appearances_last_7'),
                    'pitches_last_7_days': facts.get('pitches_last_7_days'),
                    'back_to_back': facts.get('back_to_back'),
                },
                'roster_status': deepcopy(card.get('roster_status')),
                'visibility': deepcopy(card.get('visibility')),
            })
    return arms


def _active_status(board, represented_date):
    freshness = board.get('freshness') or {}
    roster = board.get('roster_authority') or {}
    readiness = roster.get('readiness') or {}
    if (
        freshness.get('fail_closed') is True
        or freshness.get('degradation_state') == 'unavailable'
        or board.get('total_pitchers') is None
    ):
        return _section_status(
            STATUS_PARTIAL,
            reason_code='current_population_counts_withheld',
            limitations=(roster.get('limitations') or board.get('limitations') or []),
            represented_date=represented_date,
        )
    if readiness.get('current_roster_claims_available') is False:
        return _section_status(
            STATUS_PARTIAL,
            reason_code='roster_context_unavailable',
            limitations=readiness.get('reader_limitations') or roster.get('limitations') or [],
            represented_date=represented_date,
        )
    return _section_status(STATUS_AVAILABLE, represented_date=represented_date)


def _rotation_status(rotation, error, represented_date):
    if error:
        return deepcopy(error)
    if not isinstance(rotation, dict) or not rotation:
        return unavailable_section('rotation_impact_unavailable')
    limitations = rotation.get('limitations') or []
    status = STATUS_PARTIAL if limitations or rotation.get('status') == 'limited_read' else STATUS_AVAILABLE
    return _section_status(
        status,
        reason_code=(rotation.get('limitation_reasons') or [None])[0],
        limitations=limitations,
        represented_date=rotation.get('reference_date') or represented_date,
    )


def _relief_work_status(relief_work, error, represented_date):
    if error:
        return deepcopy(error)
    if not isinstance(relief_work, dict):
        return unavailable_section('recent_relief_work_unavailable')
    groups = relief_work.get('relief_by_date') or []
    partial = bool(relief_work.get('unattributed_appearance_count')) or any(
        group.get('available') is False for group in groups if isinstance(group, dict)
    )
    return _section_status(
        STATUS_PARTIAL if partial else STATUS_AVAILABLE,
        reason_code='relief_work_reconciliation_limited' if partial else None,
        represented_date=relief_work.get('data_through') or represented_date,
    )


def _game_context_status(game_context, error, represented_date):
    if error:
        return deepcopy(error)
    if not isinstance(game_context, dict) or game_context.get('available') is not True:
        reason = game_context.get('state') if isinstance(game_context, dict) else None
        return unavailable_section(reason or 'game_context_unavailable')
    return _section_status(
        STATUS_AVAILABLE,
        represented_date=game_context.get('reference_date') or represented_date,
    )


def build_team_board_v2_payload(
    board,
    *,
    recent_relief_work=None,
    game_context=None,
    section_errors=None,
):
    """Compose existing public read models without mutating their payloads."""
    if not isinstance(board, dict):
        raise ValueError('canonical board payload is required')

    errors = dict(section_errors or {})
    team_state = deepcopy(board.get('team_state') or {})
    freshness = deepcopy(board.get('freshness') or {})
    represented_date = (
        team_state.get('data_through')
        or freshness.get('data_through')
        or freshness.get('latest_workload_date')
    )
    arms = _active_arms(board)
    rotation = deepcopy(board.get('rotation_support_pressure') or {})
    relief_work = deepcopy(recent_relief_work) if isinstance(recent_relief_work, dict) else None
    context = deepcopy(game_context) if isinstance(game_context, dict) else None

    section_status = {
        'team_state': _section_status(
            STATUS_AVAILABLE if team_state.get('available') is True else STATUS_UNAVAILABLE,
            reason_code=team_state.get('reason_code'),
            limitations=[team_state.get('unavailable_message')] if team_state.get('unavailable_message') else [],
            represented_date=team_state.get('data_through') or represented_date,
        ),
        'active_bullpen': _active_status(board, represented_date),
        'rest_status': _section_status(
            STATUS_AVAILABLE if (board.get('rest_status') or {}).get('available') is True else STATUS_UNAVAILABLE,
            reason_code=(board.get('rest_status') or {}).get('reason_code'),
            represented_date=represented_date,
        ),
        'rotation_impact': _rotation_status(rotation, errors.get('rotation_impact'), represented_date),
        'recent_relief_work': _relief_work_status(relief_work, errors.get('recent_relief_work'), represented_date),
        'game_context': _game_context_status(context, errors.get('game_context'), represented_date),
    }

    return {
        'capability': CAPABILITY,
        'contract_version': CONTRACT_VERSION,
        'team': deepcopy(board.get('team') or {}),
        'represented_date': represented_date,
        'generated_at': board.get('generated_at'),
        'freshness': freshness,
        'team_state': team_state,
        'summary': team_state.get('summary'),
        'active_bullpen': {
            'population_basis': ACTIVE_BULLPEN_POPULATION_BASIS,
            'arm_count': board.get('total_pitchers'),
            'arms': arms,
        },
        'rest_status': deepcopy(board.get('rest_status') or {}),
        'rotation_impact': {
            'population_basis': ROTATION_IMPACT_POPULATION_BASIS,
            'read': rotation,
        },
        'roster_context': deepcopy(board.get('roster_authority') or {}),
        'recent_relief_work': {
            'population_basis': RECENT_RELIEF_WORK_POPULATION_BASIS,
            'read': relief_work,
        },
        'game_context': context,
        'section_status': section_status,
        'limitations': deepcopy(board.get('limitations') or []),
    }


__all__ = [
    'ACTIVE_BULLPEN_POPULATION_BASIS',
    'CAPABILITY',
    'CONTRACT_VERSION',
    'RECENT_RELIEF_WORK_POPULATION_BASIS',
    'ROTATION_IMPACT_POPULATION_BASIS',
    'build_team_board_v2_payload',
    'unavailable_section',
]
