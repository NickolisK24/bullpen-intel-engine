"""Additive public Team Board v2 composition contract.

This module rearranges already-governed public read models for one Team Board
consumer. It does not query, classify, score, publish, or persist anything.
"""

from __future__ import annotations

from copy import deepcopy

from services.pitcher_public_labels import (
    PUBLIC_ROLE_COMPOSITION_KEYS,
    ROLE_PUBLIC_LABELS,
)


CAPABILITY = 'team_board_v2'
CONTRACT_VERSION = 'team-board-2.0.0'

STATUS_AVAILABLE = 'available'
STATUS_PARTIAL = 'partial'
STATUS_UNAVAILABLE = 'unavailable'

ACTIVE_BULLPEN_POPULATION_BASIS = 'current_scored_bullpen_eligible_pitchers'
RECENT_USAGE_POPULATION_BASIS = 'official_recent_team_relief_appearance_rows'
WORKLOAD_OVERVIEW_POPULATION_BASIS = (
    'official_team_relief_appearances_and_current_bullpen_eligible_pitchers'
)
WORKLOAD_WINDOW_POPULATION_BASIS = 'official_appearance_team_relief_appearances'
WORKLOAD_CONCENTRATION_POPULATION_BASIS = (
    'current_bullpen_eligible_pitchers_recent_relief_pitch_workload'
)
ROLES_DEPLOYMENT_POPULATION_BASIS = 'current_visible_active_bullpen_public_role_reads'
RECENT_RELIEF_WORK_POPULATION_BASIS = 'official_appearance_team_relief_appearances'
ROTATION_IMPACT_POPULATION_BASIS = 'stored_team_game_pitching_splits'

WORKLOAD_OVERVIEW_WINDOWS = (
    ('window_7', 7),
    ('window_14', 14),
)


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


def _roles_deployment(arms, represented_date, relief_work=None):
    """Combine governed role reads with observed public deployment evidence.

    The active-arm projection already carries the output of the one public role
    authority. This composition only counts its governed keys in that owner's
    stable display order. Deployment is copied from the canonical Recent Relief
    Work owner; this composer performs no appearance aggregation or role inference.
    """
    counts = {key: 0 for key in PUBLIC_ROLE_COMPOSITION_KEYS}
    missing_role_count = 0

    for arm in arms:
        public_role_read = arm.get('public_role_read') or {}
        key = public_role_read.get('key')
        if key not in counts:
            missing_role_count += 1
            continue
        counts[key] += 1

    roles = [
        {
            'role_key': key,
            'label': ROLE_PUBLIC_LABELS[key]['label'],
            'arm_count': counts[key],
        }
        for key in PUBLIC_ROLE_COMPOSITION_KEYS
        if counts[key] > 0
    ]
    deployment = (
        deepcopy(relief_work.get('deployment_profile'))
        if isinstance(relief_work, dict)
        and isinstance(relief_work.get('deployment_profile'), dict)
        else None
    )
    return {
        'population_basis': ROLES_DEPLOYMENT_POPULATION_BASIS,
        'arm_count': len(arms),
        'role_arm_count': len(arms) - missing_role_count,
        'missing_role_count': missing_role_count,
        'roles': roles,
        'deployment_profile': deployment,
        'represented_date': represented_date,
    }


def _roles_deployment_status(board, roles_deployment, represented_date):
    active_status = _active_status(board, represented_date)
    missing_role_count = roles_deployment['missing_role_count']
    deployment = roles_deployment.get('deployment_profile')
    deployment_available = (
        isinstance(deployment, dict)
        and deployment.get('status') == 'complete'
    )
    if (
        active_status['status'] == STATUS_AVAILABLE
        and missing_role_count == 0
        and deployment_available
        and not deployment.get('limitations')
    ):
        return _section_status(STATUS_AVAILABLE, represented_date=represented_date)

    limitations = list(active_status.get('limitations') or [])
    if missing_role_count:
        limitations.append('Some current arms do not have a public role read.')
    if not deployment_available:
        limitations.append('Observed deployment detail is unavailable.')
    elif deployment.get('limitations'):
        limitations.extend(deployment.get('limitations') or [])
    return _section_status(
        STATUS_PARTIAL,
        reason_code='role_composition_limited',
        limitations=limitations,
        represented_date=represented_date,
    )


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


def _recent_transactions_status(recent_transactions, error, represented_date):
    if error:
        return deepcopy(error)
    if not isinstance(recent_transactions, dict):
        return unavailable_section('recent_transactions_unavailable')

    status = recent_transactions.get('status')
    if status == STATUS_UNAVAILABLE:
        return unavailable_section(
            'recent_transactions_unavailable',
            limitations=recent_transactions.get('limitations') or [],
        )
    if status not in (STATUS_AVAILABLE, STATUS_PARTIAL):
        return unavailable_section('recent_transactions_unavailable')
    return _section_status(
        status,
        reason_code='recent_transactions_limited' if status == STATUS_PARTIAL else None,
        limitations=recent_transactions.get('limitations') or [],
        represented_date=recent_transactions.get('represented_date') or represented_date,
    )


def _relief_work_status(relief_work, error, represented_date):
    if error:
        return deepcopy(error)
    if not isinstance(relief_work, dict):
        return unavailable_section('recent_relief_work_unavailable')
    groups = relief_work.get('relief_by_date') or []
    partial = bool(relief_work.get('unattributed_appearance_count')) or any(
        group.get('available') is False or group.get('unavailable') is True
        for group in groups if isinstance(group, dict)
    )
    return _section_status(
        STATUS_PARTIAL if partial else STATUS_AVAILABLE,
        reason_code='relief_work_reconciliation_limited' if partial else None,
        represented_date=relief_work.get('data_through') or represented_date,
    )


def _recent_usage(relief_work):
    """Project the existing bounded relief chronology without reclassification."""
    appearances = []
    limitations = []
    if not isinstance(relief_work, dict):
        return {
            'population_basis': RECENT_USAGE_POPULATION_BASIS,
            'appearances': appearances,
            'represented_date': None,
            'limitations': limitations,
        }

    for group in relief_work.get('relief_by_date') or []:
        if not isinstance(group, dict):
            continue
        if group.get('unavailable') is True or group.get('available') is False:
            if group.get('sentence'):
                limitations.append(group['sentence'])
            continue
        for appearance in group.get('appearances') or []:
            if not isinstance(appearance, dict):
                continue
            appearances.append({
                'pitcher_id': appearance.get('pitcher_id'),
                'pitcher_name': appearance.get('pitcher_full_name'),
                'game_date': appearance.get('game_date'),
                'opponent': appearance.get('opponent'),
                'opponent_abbreviation': appearance.get('opponent_abbreviation'),
                'pitches_thrown': appearance.get('pitches_thrown'),
                'outs_recorded': appearance.get('innings_pitched_outs'),
                'game_id': appearance.get('mlb_game_pk'),
            })

    if relief_work.get('unattributed_sentence'):
        limitations.append(relief_work['unattributed_sentence'])

    return {
        'population_basis': RECENT_USAGE_POPULATION_BASIS,
        'appearances': appearances,
        'represented_date': relief_work.get('data_through'),
        'limitations': limitations,
    }


def _recent_usage_status(relief_work, error, represented_date):
    if (
        error
        or not isinstance(relief_work, dict)
        or not relief_work.get('data_through')
    ):
        return unavailable_section('recent_usage_unavailable')
    read = _recent_usage(relief_work)
    limitations = read['limitations']
    return _section_status(
        STATUS_PARTIAL if limitations else STATUS_AVAILABLE,
        reason_code='recent_usage_reconciliation_limited' if limitations else None,
        limitations=limitations,
        represented_date=read['represented_date'] or represented_date,
    )


def _workload_overview(board, relief_work):
    """Project only the already-public relief windows and concentration read."""
    source_windows = (
        relief_work.get('windows') if isinstance(relief_work, dict) else {}
    )
    source_windows = source_windows if isinstance(source_windows, dict) else {}
    windows = []
    limitations = []

    for source_key, window_days in WORKLOAD_OVERVIEW_WINDOWS:
        source = source_windows.get(source_key)
        if not isinstance(source, dict):
            continue
        windows.append({
            'window_days': window_days,
            'through': source.get('through'),
            'relief_appearances': source.get('relief_appearances'),
            'pitchers_in_relief': source.get('pitchers_in_relief'),
            'pitches_total': source.get('pitches_total'),
        })
        if source.get('start_relief_unknown_sentence'):
            limitations.append(source['start_relief_unknown_sentence'])
        if (
            source.get('relief_appearances') is not None
            and source.get('appearances_with_pitches') is not None
            and source.get('appearances_with_pitches')
            < source.get('relief_appearances')
            and source.get('pitches_sentence')
        ):
            limitations.append(source['pitches_sentence'])

    source_concentration = (
        (board.get('team_shape') or {}).get('workloadConcentration')
        if isinstance(board, dict)
        else None
    )
    concentration = None
    if isinstance(source_concentration, dict):
        concentration = {
            'population_basis': WORKLOAD_CONCENTRATION_POPULATION_BASIS,
            'label': source_concentration.get('label'),
            'summary': source_concentration.get('summary'),
        }
        if (
            source_concentration.get('label') == 'Limited Read'
            and source_concentration.get('summary')
        ):
            limitations.append(source_concentration['summary'])

    return {
        'population_basis': WORKLOAD_OVERVIEW_POPULATION_BASIS,
        'window_population_basis': WORKLOAD_WINDOW_POPULATION_BASIS,
        'windows': windows,
        'concentration': concentration,
        'represented_date': (
            relief_work.get('data_through')
            if isinstance(relief_work, dict)
            else None
        ),
        'limitations': limitations,
    }


def _workload_overview_status(board, relief_work, error, represented_date):
    read = _workload_overview(board, relief_work)
    windows = read['windows']
    concentration = read['concentration']
    has_concentration = bool(
        isinstance(concentration, dict)
        and concentration.get('label')
        and concentration.get('summary')
    )
    if not windows and not has_concentration:
        return unavailable_section('workload_overview_unavailable')

    partial = bool(
        error
        or len(windows) != len(WORKLOAD_OVERVIEW_WINDOWS)
        or not has_concentration
        or concentration.get('label') == 'Limited Read'
        or read['limitations']
    )
    return _section_status(
        STATUS_PARTIAL if partial else STATUS_AVAILABLE,
        reason_code='workload_overview_limited' if partial else None,
        limitations=read['limitations'],
        represented_date=read['represented_date'] or represented_date,
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


def _performance_status(performance, error, represented_date):
    if error:
        return deepcopy(error)
    if not isinstance(performance, dict):
        return unavailable_section('performance_unavailable')
    status = performance.get('status')
    if status not in (STATUS_AVAILABLE, STATUS_PARTIAL):
        return unavailable_section(
            performance.get('reason_code') or 'performance_unavailable',
            limitations=performance.get('limitations') or [],
        )
    return _section_status(
        status,
        reason_code=performance.get('reason_code'),
        limitations=performance.get('limitations') or [],
        represented_date=performance.get('through') or represented_date,
    )


def build_team_board_v2_payload(
    board,
    *,
    recent_relief_work=None,
    recent_transactions=None,
    game_context=None,
    performance=None,
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
    relief_work = deepcopy(recent_relief_work) if isinstance(recent_relief_work, dict) else None
    roles_deployment = _roles_deployment(arms, represented_date, relief_work)
    rotation = deepcopy(board.get('rotation_support_pressure') or {})
    context = deepcopy(game_context) if isinstance(game_context, dict) else None
    performance_read = deepcopy(performance) if isinstance(performance, dict) else None

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
        'recent_usage': _recent_usage_status(
            relief_work,
            errors.get('recent_relief_work'),
            represented_date,
        ),
        'workload_overview': _workload_overview_status(
            board,
            relief_work,
            errors.get('recent_relief_work'),
            represented_date,
        ),
        'roles_deployment': _roles_deployment_status(board, roles_deployment, represented_date),
        'rotation_impact': _rotation_status(rotation, errors.get('rotation_impact'), represented_date),
        'recent_transactions': _recent_transactions_status(
            recent_transactions,
            errors.get('recent_transactions'),
            represented_date,
        ),
        'recent_relief_work': _relief_work_status(relief_work, errors.get('recent_relief_work'), represented_date),
        'game_context': _game_context_status(context, errors.get('game_context'), represented_date),
        'performance': _performance_status(
            performance_read,
            errors.get('performance'),
            represented_date,
        ),
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
        'recent_usage': _recent_usage(relief_work),
        'workload_overview': _workload_overview(board, relief_work),
        'roles_deployment': roles_deployment,
        'rotation_impact': {
            'population_basis': ROTATION_IMPACT_POPULATION_BASIS,
            'read': rotation,
        },
        'roster_context': deepcopy(board.get('roster_authority') or {}),
        'recent_transactions': deepcopy(recent_transactions) if isinstance(recent_transactions, dict) else None,
        'recent_relief_work': {
            'population_basis': RECENT_RELIEF_WORK_POPULATION_BASIS,
            'read': relief_work,
        },
        'game_context': context,
        'performance': performance_read,
        'section_status': section_status,
        'limitations': deepcopy(board.get('limitations') or []),
    }


__all__ = [
    'ACTIVE_BULLPEN_POPULATION_BASIS',
    'CAPABILITY',
    'CONTRACT_VERSION',
    'RECENT_USAGE_POPULATION_BASIS',
    'ROLES_DEPLOYMENT_POPULATION_BASIS',
    'WORKLOAD_OVERVIEW_POPULATION_BASIS',
    'RECENT_RELIEF_WORK_POPULATION_BASIS',
    'ROTATION_IMPACT_POPULATION_BASIS',
    'build_team_board_v2_payload',
    'unavailable_section',
]
