"""Trusted publication authority for public bullpen reader surfaces.

Acquisition tables are allowed to advance before publication finishes. Public
claim-bearing reads are not. This module freezes the source material needed by
Team Board/Compare into the candidate Dashboard snapshot and, in production,
serves those surfaces only from the latest trusted published snapshot.

It also makes Tonight snapshot-only in production: a browser cache miss never
rebuilds claim-bearing intelligence against mutable acquisition tables.

No prediction, ranking, recommendation, scoring threshold, or writer authority
is introduced here. This is a serving/publication boundary only.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from typing import Mapping

from flask import jsonify, request

from api.query_params import parse_positive_int_param, query_param_error_response, QueryParamError
from models.pitcher import Pitcher
from models.share_artifact import LIFECYCLE_PUBLISHED, ShareArtifact
from services import board_freshness
from services import dashboard_snapshot as dashboard_snapshot_service
from services import tonight_intelligence_snapshot
from services.availability_population import availability_with_eligibility, current_availability_records
from services.availability_reference_date import parse_reference_date, product_current_date
from services.availability_snapshot import (
    CURRENT_AVAILABILITY_MODE,
    classify_fatigue_rows,
    latest_fatigue_rows,
)
from services.bullpen_board import (
    REST_STATUS_METHOD_VERSION,
    REST_STATUS_PUBLIC_CONTRACT_VERSION,
    author_rest_status,
    build_board_payload,
    is_valid_rest_status_carrier,
    last_workload_appearance_from_logs,
)
from services.bullpen_population import eligible_bullpen_pitcher_contexts, usage_logs_by_pitcher
from services.bullpen_visibility import build_visibility_contract
from services.pitcher_role_authority import author_role_read_labels, role_logs_by_pitcher
from services.public_fatigue_view import public_workload_facts
from services.public_team_performance import (
    FROZEN_CONTRACT as TEAM_BOARD_PERFORMANCE_CONTRACT,
    build_frozen_team_performance_payload,
)
from services.public_roster_readiness import apply_public_roster_readiness, build_public_roster_readiness
from services.public_recent_transactions import build_public_recent_transactions_by_team
from services.public_team_relief_work import (
    DEPLOYMENT_PROFILE_CARRIER_CONTRACT,
    DEPLOYMENT_PROFILE_MEMBERSHIP_AUTHORITY,
    DEPLOYMENT_PROFILE_METHOD_VERSION,
    DEPLOYMENT_PROFILE_POPULATION_AUTHORITY,
    DEPLOYMENT_PROFILE_POPULATION_BASIS,
    DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION,
    DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY,
    RECENT_USAGE_REST_CONTRACT,
    RECENT_USAGE_REST_MEMBERSHIP_AUTHORITY,
    RECENT_USAGE_REST_METHOD_VERSION,
    RECENT_USAGE_REST_POPULATION_AUTHORITY,
    RECENT_USAGE_REST_POPULATION_BASIS,
    RECENT_USAGE_REST_PUBLIC_CONTRACT_VERSION,
    RECENT_USAGE_REST_REFERENCE_DATE_POLICY,
    WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY,
    WORKLOAD_WINDOWS_METHOD_VERSION,
    WORKLOAD_WINDOWS_POPULATION_AUTHORITY,
    WORKLOAD_WINDOWS_POPULATION_BASIS,
    WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION,
    WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY,
    WORKLOAD_WINDOWS_CARRIER_CONTRACT,
    WORKLOAD_OVERVIEW_CONTRACT,
    author_active_bullpen_workload_display,
    author_public_team_relief_authority,
    build_recent_usage_rest_coverage,
    extend_team_workload_coverage,
)
from services.roster_authority import build_roster_authority
from services.roster_authority import VERSION as ROSTER_AUTHORITY_VERSION
from services.rotation_support_pressure import (
    DELTA_CARRIER_CONTRACT as ROTATION_IMPACT_CARRIER_CONTRACT,
    MEMBERSHIP_AUTHORITY as ROTATION_IMPACT_MEMBERSHIP_AUTHORITY,
    POPULATION_AUTHORITY as ROTATION_IMPACT_POPULATION_AUTHORITY,
    POPULATION_BASIS as ROTATION_IMPACT_POPULATION_BASIS,
    PUBLIC_CONTRACT_VERSION as ROTATION_IMPACT_PUBLIC_CONTRACT_VERSION,
    REFERENCE_DATE_POLICY as ROTATION_IMPACT_REFERENCE_DATE_POLICY,
    RECENT_GAMES_CONTRACT as ROTATION_GAMES_CONTRACT,
    VERSION as ROTATION_IMPACT_METHOD_VERSION,
    frozen_recent_rotation_games_by_team,
)
from services.published_team_state import project_published_team_state_artifact
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE
from services.team_state_public_vocabulary import (
    TEAM_STATE_READINESS_UNAVAILABLE,
    team_state_unavailable,
)
from services.team_board_public_deployment_context import (
    CONTRACT as PUBLIC_DEPLOYMENT_CONTEXT_CONTRACT,
    METHOD_VERSION as PUBLIC_DEPLOYMENT_CONTEXT_METHOD_VERSION,
    author_public_deployment_context,
)
from services.team_board_roster_transactions import (
    CONTRACT as ROSTER_TRANSACTIONS_CONTRACT,
    author_frozen_roster_transactions,
)
from services.team_board_recent_relief_work import (
    CONTRACT as RECENT_RELIEF_WORK_CONTRACT,
    METHOD_VERSION as RECENT_RELIEF_WORK_METHOD_VERSION,
    author_frozen_recent_relief_work,
    load_final_game_authority,
    load_unresolved_current_roster_counts,
    valid_frozen_recent_relief_work,
)
from services.team_board_what_changed import (
    CONTRACT as WHAT_CHANGED_CONTRACT,
    EVENT_METHOD_VERSION as WHAT_CHANGED_EVENT_METHOD_VERSION,
    METHOD_VERSION as WHAT_CHANGED_METHOD_VERSION,
)
from services.mlb_club_directory import MLB_TEAM_IDS
from services.workload_concentration import summarize_recent_relief_workload
from utils.db import db


TEAM_BOARD_PACKAGE_KEY = 'trusted_team_boards'
TEAM_BOARD_PACKAGE_CONTRACT = 'trusted_team_board_publication_v1'
REST_STATUS_POPULATION_BASIS = 'represented_default_visible_active_bullpen'
REST_STATUS_POPULATION_AUTHORITY = 'trusted_team_boards.default_pitcher_ids'
REST_STATUS_MEMBERSHIP_AUTHORITY = 'eligible_bullpen_pitcher_contexts'
REST_STATUS_REFERENCE_DATE_POLICY = 'd055_availability_reference_date_v1'
PUBLICATION_AUTHORITY_CONTRACT = 'trusted_dashboard_publication_v1'
BULLPEN_MEMBERSHIP_METHOD_VERSION = 'team_board_default_bullpen_membership_v1'
BULLPEN_MEMBERSHIP_PUBLIC_CONTRACT_VERSION = 'bullpen_membership_snapshot_public_v1'
BULLPEN_MEMBERSHIP_CARRIER_CONTRACT = 'team_board_bullpen_membership_carrier_v1'
BULLPEN_MEMBERSHIP_POPULATION_BASIS = 'represented_default_visible_active_bullpen'
BULLPEN_MEMBERSHIP_POPULATION_AUTHORITY = 'trusted_team_boards.default_pitcher_ids'
BULLPEN_MEMBERSHIP_MEMBERSHIP_AUTHORITY = 'current_availability_records'
BULLPEN_MEMBERSHIP_REFERENCE_DATE_POLICY = 'team_board_membership_reference_date_v1'
TEAM_BOARD_UNAVAILABLE = 'trusted_team_board_unavailable'
TEAM_BOARD_PACKAGE_MISSING = 'trusted_team_board_package_missing'
TEAM_BOARD_TEAM_MISSING = 'trusted_team_board_team_missing'
TONIGHT_SNAPSHOT_UNAVAILABLE = 'trusted_tonight_snapshot_unavailable'
_SNAPSHOT_NOT_PROVIDED = object()

REST_STATUS_CARRIER_QUALIFIED = 'qualified'
REST_STATUS_CARRIER_SNAPSHOT_MISSING = 'snapshot_missing'
REST_STATUS_CARRIER_SNAPSHOT_NOT_PERSISTED = 'snapshot_not_persisted'
REST_STATUS_CARRIER_SNAPSHOT_NOT_READY = 'snapshot_not_ready'
REST_STATUS_CARRIER_SNAPSHOT_UNPUBLISHED = 'snapshot_unpublished'
REST_STATUS_CARRIER_PUBLICATION_IDENTITY_MISSING = 'publication_identity_missing'
REST_STATUS_CARRIER_PACKAGE_MISSING = 'team_board_package_missing'
REST_STATUS_CARRIER_PACKAGE_CONTRACT_INVALID = 'package_contract_invalid'
REST_STATUS_CARRIER_REPRESENTED_DATE_INVALID = 'represented_date_invalid'
REST_STATUS_CARRIER_REFERENCE_DATE_INVALID = 'reference_date_invalid'
REST_STATUS_CARRIER_TEAM_POPULATION_INVALID = 'team_population_invalid'
REST_STATUS_CARRIER_TEAM_MISSING = 'team_carrier_missing'
REST_STATUS_CARRIER_AUTHORITY_INVALID = 'team_carrier_authority_invalid'
REST_STATUS_CARRIER_VALUE_INVALID = 'team_carrier_value_invalid'


def _truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _iso(value):
    return value.isoformat() if value is not None else None


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def publication_authority(snapshot):
    """Serialize one trusted Dashboard snapshot's public authority context."""
    if snapshot is None:
        return None
    return {
        'contract': PUBLICATION_AUTHORITY_CONTRACT,
        'authority_type': 'dashboard_snapshot',
        'snapshot_id': snapshot.id,
        'sync_run_id': snapshot.sync_run_id,
        'data_through': _iso(snapshot.data_through),
        'availability_reference_date': _iso(snapshot.availability_reference_date),
        'snapshot_generated_at': _iso(snapshot.snapshot_generated_at),
        'published_at': _iso(snapshot.published_at),
    }


def _candidate_reference_date(payload):
    freshness = payload.get('freshness') if isinstance(payload, Mapping) else {}
    freshness = freshness if isinstance(freshness, Mapping) else {}
    return (
        parse_reference_date(freshness.get('availability_reference_date'))
        or parse_reference_date(freshness.get('reference_date'))
        or product_current_date()
    )


def _support_for_team(payload, key, team_id):
    section = payload.get(key) if isinstance(payload, Mapping) else None
    if not isinstance(section, Mapping):
        return {}
    by_team = section.get('by_team_id')
    if not isinstance(by_team, Mapping):
        return {}
    value = by_team.get(str(team_id))
    if value is None:
        value = by_team.get(team_id)
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _mapping_value(value, key):
    return value.get(key) if isinstance(value, Mapping) else None


def _plain_board_record(record, role_logs, reference_date):
    pitcher = record.get('pitcher')
    score = record.get('score')
    if pitcher is None:
        return None
    role, labels, public_role_read = author_role_read_labels(record, role_logs, reference_date)
    logs = record.get('_population_logs') or []
    last_workload_appearance = last_workload_appearance_from_logs(logs)
    raw_score = getattr(score, 'raw_score', None) if score is not None else None
    return {
        'name': pitcher.full_name,
        'pitcher_id': pitcher.id,
        'fatigue_score': float(raw_score) if raw_score is not None else None,
        'workload_facts': deepcopy(public_workload_facts(score)),
        'availability': deepcopy(record.get('availability') or {}),
        'last_appearance': deepcopy(last_workload_appearance),
        'last_workload_appearance': deepcopy(last_workload_appearance),
        'role': deepcopy(role),
        'pitcher_labels': deepcopy(labels),
        'public_role_read': deepcopy(public_role_read),
        'eligibility': deepcopy(record.get('eligibility') or {}),
        'roster_status': deepcopy(record.get('roster_status') or {}),
        'visibility': deepcopy(record.get('visibility') or {}),
    }


def _frozen_roles_deployment_carrier(team_id, selected_records, deployment_profile, context):
    """Join existing public role reads and observed facts at publication only."""
    if not isinstance(context, Mapping) or context.get('contract') != PUBLIC_DEPLOYMENT_CONTEXT_CONTRACT:
        return None
    by_pitcher = {
        item.get('pitcher_id'): item for item in context.get('profiles') or []
        if isinstance(item, Mapping) and type(item.get('pitcher_id')) is int
    }
    factual = {
        item.get('pitcher_id'): item for item in (deployment_profile.get('profiles') or [])
        if isinstance(item, Mapping) and type(item.get('pitcher_id')) is int
    }
    profiles = []
    for record in selected_records:
        pitcher_id = record.get('pitcher_id')
        profiles.append({
            'pitcher_id': pitcher_id,
            'pitcher_name': record.get('name'),
            'team_id': team_id,
            'public_role_read': deepcopy(record.get('public_role_read')),
            'observed_profile': deepcopy(factual.get(pitcher_id)),
            'context': deepcopy(by_pitcher.get(pitcher_id)),
        })
    return {
        'contract': PUBLIC_DEPLOYMENT_CONTEXT_CONTRACT,
        'method_version': PUBLIC_DEPLOYMENT_CONTEXT_METHOD_VERSION,
        'team_id': team_id,
        'data_through': context.get('data_through'),
        'window_days': context.get('window_days'),
        'profiles': profiles,
        'deployment_profile': deepcopy(deployment_profile),
        'role_movement': {'status': 'unavailable', 'reason_code': 'not_published'},
    }


def build_frozen_team_board_package(dashboard_payload):
    """Build a JSON-safe per-team board source package for one candidate snapshot.

    This runs while the candidate Dashboard payload is assembled, before publish.
    It deliberately reads the candidate-time mutable tables once and captures the
    resulting public board inputs by value. Later requests never need those tables
    to reproduce the published Team Board/Compare claim.
    """
    payload = dashboard_payload if isinstance(dashboard_payload, Mapping) else {}
    reference_date = _candidate_reference_date(payload)

    scored_rows = list(latest_fatigue_rows())
    score_by_pitcher = {pitcher.id: score for score, pitcher in scored_rows}

    # The default-board population is the exact governed current-availability
    # population used by the live builder at candidate time.
    default_records = current_availability_records(scored_rows, reference_date=reference_date)
    default_ids_by_team = defaultdict(set)
    for record in default_records:
        pitcher = record.get('pitcher')
        if pitcher is not None and pitcher.team_id is not None:
            default_ids_by_team[int(pitcher.team_id)].add(int(pitcher.id))

    pitchers = (
        Pitcher.query
        .filter(
            Pitcher.active == True,
            Pitcher.team_id.in_(MLB_TEAM_IDS),
        )
        .order_by(Pitcher.team_id, Pitcher.full_name)
        .all()
    )
    pitcher_ids = [pitcher.id for pitcher in pitchers]

    # Population eligibility intentionally uses the complete/stale-aware log set,
    # while public observed-role labels use the bounded role window. These are the
    # same two authorities the existing board pipeline uses.
    population_logs = usage_logs_by_pitcher(
        pitcher_ids,
        include_stale=True,
        reference_date=reference_date,
    )
    role_logs = role_logs_by_pitcher(pitcher_ids, reference_date=reference_date)
    contexts = eligible_bullpen_pitcher_contexts(
        pitchers,
        include_stale=True,
        include_inactive_context=True,
        include_unknown_roster=True,
        reference_date=reference_date,
        logs_by_pitcher=population_logs,
    )
    context_by_pitcher = {context['pitcher'].id: context for context in contexts}

    availability_rows = [(score_by_pitcher.get(pitcher.id), pitcher) for pitcher in pitchers]
    classified = classify_fatigue_rows(
        availability_rows,
        reference_date=reference_date,
        mode=CURRENT_AVAILABILITY_MODE,
    )
    availability_by_pitcher = {
        record['pitcher_id']: record.get('availability')
        for record in classified
    }

    records_by_team = defaultdict(list)
    team_info = {}
    for pitcher in pitchers:
        context = context_by_pitcher.get(pitcher.id)
        if context is None:
            continue
        availability = availability_with_eligibility(
            availability_by_pitcher.get(pitcher.id),
            context.get('eligibility'),
            context.get('roster_status'),
        )
        working = {
            'pitcher': pitcher,
            'score': score_by_pitcher.get(pitcher.id),
            'availability': availability,
            'eligibility': context.get('eligibility'),
            'roster_status': context.get('roster_status'),
            'visibility': build_visibility_contract(
                context.get('eligibility'),
                context.get('roster_status'),
                context.get('logs') or [],
                reference_date,
            ),
            '_population_logs': context.get('logs') or [],
        }
        plain = _plain_board_record(working, role_logs, reference_date)
        if plain is None:
            continue
        team_id = int(pitcher.team_id)
        records_by_team[team_id].append(plain)
        team_info.setdefault(team_id, {
            'team_id': team_id,
            'team_name': pitcher.team_name,
            'team_abbreviation': pitcher.team_abbreviation,
        })

    freshness = payload.get('freshness') if isinstance(payload.get('freshness'), Mapping) else {}
    represented_data_through = (
        freshness.get('data_through') or freshness.get('latest_workload_date')
    )
    recent_usage_rest_coverage = build_recent_usage_rest_coverage(
        represented_data_through,
        anchor_coverage=(
            freshness.get('slate_coverage')
            if isinstance(freshness.get('slate_coverage'), Mapping)
            else None
        ),
    )
    workload_coverage = extend_team_workload_coverage(
        represented_data_through, recent_usage_rest_coverage,
    )
    rotation_game_carriers = frozen_recent_rotation_games_by_team(
        records_by_team,
        represented_date=parse_reference_date(represented_data_through),
    )
    transaction_reads = build_public_recent_transactions_by_team(
        records_by_team,
        reference_date=parse_reference_date(represented_data_through),
        include_event_direction=True,
    )
    final_games_by_team = load_final_game_authority(
        records_by_team,
        data_through=represented_data_through,
    )
    unresolved_relief_counts = load_unresolved_current_roster_counts(
        records_by_team,
        data_through=represented_data_through,
    )
    by_team_id = {}
    for team_id in sorted(records_by_team):
        records = sorted(
            records_by_team[team_id],
            key=lambda item: (str(item.get('name') or '').lower(), item.get('pitcher_id') or 0),
        )
        roster_authority = build_roster_authority(
            records,
            team=team_info.get(team_id),
            reference_date=reference_date,
        )
        roster_readiness = build_public_roster_readiness(
            reference_date=reference_date,
            team_id=team_id,
            scope='team',
        )
        roster_authority = apply_public_roster_readiness(
            roster_authority,
            roster_readiness,
        )
        default_ids = sorted(default_ids_by_team.get(team_id) or [])
        default_id_set = set(default_ids)
        workload_concentration = summarize_recent_relief_workload(
            role_logs,
            reference_date,
            pitcher_ids=default_id_set,
        )
        selected_records = [
            record for record in records
            if _as_int(record.get('pitcher_id')) in default_id_set
        ]
        rest_status = author_rest_status(
            records=selected_records,
            freshness=deepcopy(freshness),
            roster_authority=deepcopy(roster_authority),
        )
        relief_authority = author_public_team_relief_authority(
            team_id,
            data_through=represented_data_through,
            reference_date=reference_date,
            active_pitchers={
                record['pitcher_id']: {
                    'name': record.get('name'),
                    'days_since_last_appearance': _mapping_value(
                        record.get('workload_facts') or {},
                        'days_since_last_appearance',
                    ),
                }
                for record in selected_records
                if type(record.get('pitcher_id')) is int
            },
            coverage_by_date=workload_coverage,
            include_publication_rows=True,
        )
        workload_windows = relief_authority['workload_windows']
        frozen_roster_transactions = author_frozen_roster_transactions(
            team_id,
            data_through=represented_data_through,
            transaction_read=transaction_reads[team_id],
            records=records,
            active_pitcher_ids=default_ids,
            workload_overview=workload_windows.get('overview'),
            team_board_package_contract=TEAM_BOARD_PACKAGE_CONTRACT,
        )
        deployment_profile = relief_authority['deployment_profile']
        publication_rows = relief_authority.pop('_publication_team_rows', [])
        recent_relief_work = author_frozen_recent_relief_work(
            team_id,
            publication_rows,
            data_through=represented_data_through,
            final_games=final_games_by_team.get(team_id),
            unresolved_current_roster_count=unresolved_relief_counts.get(team_id, 0),
            active_pitcher_ids=default_ids,
            team_board_package_contract=TEAM_BOARD_PACKAGE_CONTRACT,
        )
        deployment_anchor = parse_reference_date(represented_data_through)
        deployment_context = (
            author_public_deployment_context(
                team_id, publication_rows, deployment_anchor, pitcher_ids=default_ids,
            )
            if deployment_anchor is not None else None
        )
        roles_deployment = _frozen_roles_deployment_carrier(
            team_id, selected_records, deployment_profile,
            deployment_context,
        )
        performance_records = [
            record for record in selected_records
            if (record.get('visibility') or {}).get('is_visible_by_default') is not False
        ]
        performance = build_frozen_team_performance_payload(
            team_id,
            records=performance_records,
            represented_date=represented_data_through,
            freshness=freshness,
        )
        recent_usage_rest = relief_authority['recent_usage_rest']
        # Active Bullpen 7d App / 7d P / Last P are bullpen workload, frozen from
        # the same carrier as Recent Usage. FatigueScore facts on the record stay
        # untouched: they remain the physical workload behind availability.
        workload_display = author_active_bullpen_workload_display(
            recent_usage_rest, default_ids,
        )
        for record in records:
            display = workload_display.get(_as_int(record.get('pitcher_id')))
            if display is not None:
                record['bullpen_workload_display'] = deepcopy(display)
        rotation_support_pressure = _support_for_team(
            payload, 'rotation_support_pressure', team_id
        )
        by_team_id[str(team_id)] = {
            'team': deepcopy(team_info.get(team_id) or {'team_id': team_id}),
            'records': records,
            'default_pitcher_ids': default_ids,
            'bullpen_membership_authority': {
                'method_version': BULLPEN_MEMBERSHIP_METHOD_VERSION,
                'public_contract_version': (
                    BULLPEN_MEMBERSHIP_PUBLIC_CONTRACT_VERSION
                ),
                'carrier_contract_version': BULLPEN_MEMBERSHIP_CARRIER_CONTRACT,
                'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'population_basis': {
                    'basis': BULLPEN_MEMBERSHIP_POPULATION_BASIS,
                    'population_authority': (
                        BULLPEN_MEMBERSHIP_POPULATION_AUTHORITY
                    ),
                    'membership_authority': (
                        BULLPEN_MEMBERSHIP_MEMBERSHIP_AUTHORITY
                    ),
                    'roster_authority_version': ROSTER_AUTHORITY_VERSION,
                },
                'reference_date_policy': (
                    BULLPEN_MEMBERSHIP_REFERENCE_DATE_POLICY
                ),
                'membership_reference_date': reference_date.isoformat(),
            },
            'roster_authority': deepcopy(roster_authority),
            'frozen_roster_transactions': frozen_roster_transactions,
            'frozen_roster_transactions_authority': {
                'method_version': ROSTER_TRANSACTIONS_CONTRACT,
                'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'data_through': represented_data_through,
            },
            'workload_concentration': deepcopy(workload_concentration),
            'workload_windows': deepcopy(workload_windows),
            'workload_windows_authority': {
                'method_version': WORKLOAD_WINDOWS_METHOD_VERSION,
                'public_contract_version': (
                    WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION
                ),
                'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'population_basis': {
                    'basis': WORKLOAD_WINDOWS_POPULATION_BASIS,
                    'population_authority': WORKLOAD_WINDOWS_POPULATION_AUTHORITY,
                    'membership_authority': WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY,
                },
                'reference_date_policy': WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY,
                'data_through': workload_windows.get('data_through'),
            },
            'deployment_profile': deepcopy(deployment_profile),
            'roles_deployment': deepcopy(roles_deployment),
            'performance': {
                'contract': TEAM_BOARD_PERFORMANCE_CONTRACT,
                'team_id': team_id,
                'data_through': represented_data_through,
                'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'population_pitcher_ids': sorted(
                    record['pitcher_id'] for record in performance_records
                    if type(record.get('pitcher_id')) is int
                ),
                'read': performance,
            },
            'roles_deployment_authority': {
                'method_version': PUBLIC_DEPLOYMENT_CONTEXT_METHOD_VERSION,
                'public_contract_version': PUBLIC_DEPLOYMENT_CONTEXT_CONTRACT,
                'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'data_through': roles_deployment.get('data_through') if roles_deployment else None,
            },
            'deployment_profile_authority': {
                'method_version': DEPLOYMENT_PROFILE_METHOD_VERSION,
                'public_contract_version': (
                    DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION
                ),
                'carrier_contract_version': DEPLOYMENT_PROFILE_CARRIER_CONTRACT,
                'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'population_basis': {
                    'basis': DEPLOYMENT_PROFILE_POPULATION_BASIS,
                    'population_authority': DEPLOYMENT_PROFILE_POPULATION_AUTHORITY,
                    'membership_authority': DEPLOYMENT_PROFILE_MEMBERSHIP_AUTHORITY,
                },
                'reference_date_policy': DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY,
                'data_through': deployment_profile.get('data_through'),
            },
            'recent_usage_rest': deepcopy(recent_usage_rest),
            'recent_relief_work': deepcopy(recent_relief_work),
            'recent_relief_work_authority': {
                'method_version': RECENT_RELIEF_WORK_METHOD_VERSION,
                'public_contract_version': RECENT_RELIEF_WORK_CONTRACT,
                'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'data_through': recent_relief_work.get('data_through'),
            },
            'recent_usage_rest_authority': {
                'method_version': RECENT_USAGE_REST_METHOD_VERSION,
                'public_contract_version': (
                    RECENT_USAGE_REST_PUBLIC_CONTRACT_VERSION
                ),
                'carrier_contract_version': RECENT_USAGE_REST_CONTRACT,
                'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'population_basis': {
                    'basis': RECENT_USAGE_REST_POPULATION_BASIS,
                    'population_authority': (
                        RECENT_USAGE_REST_POPULATION_AUTHORITY
                    ),
                    'membership_authority': (
                        RECENT_USAGE_REST_MEMBERSHIP_AUTHORITY
                    ),
                },
                'reference_date_policy': (
                    RECENT_USAGE_REST_REFERENCE_DATE_POLICY
                ),
                'data_through': recent_usage_rest.get('data_through'),
                'reference_date': recent_usage_rest.get('reference_date'),
            },
            'rest_status': deepcopy(rest_status),
            'rest_status_authority': {
                'method_version': REST_STATUS_METHOD_VERSION,
                'public_contract_version': REST_STATUS_PUBLIC_CONTRACT_VERSION,
                'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'population_basis': {
                    'basis': REST_STATUS_POPULATION_BASIS,
                    'population_authority': REST_STATUS_POPULATION_AUTHORITY,
                    'membership_authority': REST_STATUS_MEMBERSHIP_AUTHORITY,
                },
                'reference_date_policy': REST_STATUS_REFERENCE_DATE_POLICY,
                'availability_reference_date': reference_date.isoformat(),
            },
            'capacity_intelligence': _support_for_team(payload, 'capacity_intelligence', team_id),
            'rotation_support_pressure': deepcopy(rotation_support_pressure),
            'frozen_rotation_impact': deepcopy(rotation_game_carriers.get(team_id)),
            'frozen_rotation_impact_authority': {
                'method_version': ROTATION_GAMES_CONTRACT,
                'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'data_through': represented_data_through,
            },
            'rotation_support_pressure_authority': {
                'method_version': ROTATION_IMPACT_METHOD_VERSION,
                'public_contract_version': (
                    ROTATION_IMPACT_PUBLIC_CONTRACT_VERSION
                ),
                'carrier_contract_version': ROTATION_IMPACT_CARRIER_CONTRACT,
                'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'population_basis': {
                    'basis': ROTATION_IMPACT_POPULATION_BASIS,
                    'population_authority': ROTATION_IMPACT_POPULATION_AUTHORITY,
                    'membership_authority': ROTATION_IMPACT_MEMBERSHIP_AUTHORITY,
                },
                'reference_date_policy': ROTATION_IMPACT_REFERENCE_DATE_POLICY,
                'reference_date': rotation_support_pressure.get('reference_date'),
            },
            'bullpen_stability': _support_for_team(payload, 'bullpen_stability', team_id),
            'bullpen_environment': _support_for_team(payload, 'bullpen_environment', team_id),
        }

    from services.team_board_snapshot_team_state import build_team_accounting

    return {
        'contract': TEAM_BOARD_PACKAGE_CONTRACT,
        'generated_at': payload.get('generated_at') or datetime.now(timezone.utc).isoformat(),
        'data_through': freshness.get('data_through') or freshness.get('latest_workload_date'),
        'availability_reference_date': reference_date.isoformat(),
        'team_count': len(by_team_id),
        'team_accounting': build_team_accounting(by_team_id, MLB_TEAM_IDS),
        'by_team_id': by_team_id,
    }


def _carrier_result(snapshot, *, qualified=False, reason_code, represented_team_count=0,
                    qualified_team_count=0, failed_team_id=None):
    return {
        'qualified': qualified,
        'reason_code': reason_code,
        'snapshot': publication_authority(snapshot),
        'represented_date': _iso(getattr(snapshot, 'data_through', None)),
        'represented_team_count': represented_team_count,
        'qualified_team_count': qualified_team_count,
        'failed_team_id': failed_team_id,
    }


def qualify_rest_status_carrier(snapshot):
    """Qualify one persisted publication's dormant D-055 carrier, read-only."""
    if snapshot is None:
        return _carrier_result(
            snapshot,
            reason_code=REST_STATUS_CARRIER_SNAPSHOT_MISSING,
        )
    if type(getattr(snapshot, 'id', None)) is not int or snapshot.id <= 0:
        return _carrier_result(
            snapshot,
            reason_code=REST_STATUS_CARRIER_SNAPSHOT_NOT_PERSISTED,
        )
    if (
        getattr(snapshot, 'snapshot_type', None)
        != dashboard_snapshot_service.SNAPSHOT_TYPE_BULLPEN_DASHBOARD
        or getattr(snapshot, 'status', None)
        != dashboard_snapshot_service.SNAPSHOT_STATUS_READY
    ):
        return _carrier_result(
            snapshot,
            reason_code=REST_STATUS_CARRIER_SNAPSHOT_NOT_READY,
        )
    if getattr(snapshot, 'is_published', False) is not True:
        return _carrier_result(
            snapshot,
            reason_code=REST_STATUS_CARRIER_SNAPSHOT_UNPUBLISHED,
        )
    if (
        type(getattr(snapshot, 'sync_run_id', None)) is not int
        or snapshot.sync_run_id <= 0
        or getattr(snapshot, 'published_at', None) is None
    ):
        return _carrier_result(
            snapshot,
            reason_code=REST_STATUS_CARRIER_PUBLICATION_IDENTITY_MISSING,
        )

    payload = snapshot.payload if isinstance(snapshot.payload, Mapping) else {}
    package = payload.get(TEAM_BOARD_PACKAGE_KEY)
    if not isinstance(package, Mapping):
        return _carrier_result(
            snapshot,
            reason_code=REST_STATUS_CARRIER_PACKAGE_MISSING,
        )
    if package.get('contract') != TEAM_BOARD_PACKAGE_CONTRACT:
        return _carrier_result(
            snapshot,
            reason_code=REST_STATUS_CARRIER_PACKAGE_CONTRACT_INVALID,
        )

    represented_date = package.get('data_through')
    if (
        not isinstance(represented_date, str)
        or represented_date != _iso(snapshot.data_through)
    ):
        return _carrier_result(
            snapshot,
            reason_code=REST_STATUS_CARRIER_REPRESENTED_DATE_INVALID,
        )
    reference_date = package.get('availability_reference_date')
    if (
        not isinstance(reference_date, str)
        or reference_date != _iso(snapshot.availability_reference_date)
    ):
        return _carrier_result(
            snapshot,
            reason_code=REST_STATUS_CARRIER_REFERENCE_DATE_INVALID,
        )

    by_team = package.get('by_team_id')
    team_count = package.get('team_count')
    if (
        not isinstance(by_team, Mapping)
        or not by_team
        or type(team_count) is not int
        or team_count != len(by_team)
    ):
        return _carrier_result(
            snapshot,
            reason_code=REST_STATUS_CARRIER_TEAM_POPULATION_INVALID,
        )

    expected_population = {
        'basis': REST_STATUS_POPULATION_BASIS,
        'population_authority': REST_STATUS_POPULATION_AUTHORITY,
        'membership_authority': REST_STATUS_MEMBERSHIP_AUTHORITY,
    }
    qualified_count = 0
    for raw_team_id in sorted(by_team, key=lambda value: str(value)):
        team = by_team.get(raw_team_id)
        team_id = _as_int(raw_team_id)
        if team_id is None:
            return _carrier_result(
                snapshot,
                reason_code=REST_STATUS_CARRIER_TEAM_POPULATION_INVALID,
                represented_team_count=team_count,
                qualified_team_count=qualified_count,
            )
        if not isinstance(team, Mapping) or 'rest_status' not in team:
            return _carrier_result(
                snapshot,
                reason_code=REST_STATUS_CARRIER_TEAM_MISSING,
                represented_team_count=team_count,
                qualified_team_count=qualified_count,
                failed_team_id=team_id,
            )
        authority = team.get('rest_status_authority')
        authority_valid = (
            isinstance(authority, Mapping)
            and authority.get('method_version') == REST_STATUS_METHOD_VERSION
            and authority.get('public_contract_version')
            == REST_STATUS_PUBLIC_CONTRACT_VERSION
            and authority.get('team_board_package_contract')
            == TEAM_BOARD_PACKAGE_CONTRACT
            and authority.get('population_basis') == expected_population
            and authority.get('reference_date_policy')
            == REST_STATUS_REFERENCE_DATE_POLICY
            and authority.get('availability_reference_date') == reference_date
        )
        if not authority_valid:
            return _carrier_result(
                snapshot,
                reason_code=REST_STATUS_CARRIER_AUTHORITY_INVALID,
                represented_team_count=team_count,
                qualified_team_count=qualified_count,
                failed_team_id=team_id,
            )
        if not is_valid_rest_status_carrier(team.get('rest_status')):
            return _carrier_result(
                snapshot,
                reason_code=REST_STATUS_CARRIER_VALUE_INVALID,
                represented_team_count=team_count,
                qualified_team_count=qualified_count,
                failed_team_id=team_id,
            )
        qualified_count += 1

    return _carrier_result(
        snapshot,
        qualified=True,
        reason_code=REST_STATUS_CARRIER_QUALIFIED,
        represented_team_count=team_count,
        qualified_team_count=qualified_count,
    )


def attach_frozen_team_boards(dashboard_payload):
    """Return a Dashboard candidate payload carrying its frozen Team Board source."""
    result = dict(dashboard_payload or {})
    result[TEAM_BOARD_PACKAGE_KEY] = build_frozen_team_board_package(result)
    return result


def _team_package(snapshot, team_id):
    payload = snapshot.payload if snapshot is not None and isinstance(snapshot.payload, Mapping) else {}
    package = payload.get(TEAM_BOARD_PACKAGE_KEY)
    if not isinstance(package, Mapping) or package.get('contract') != TEAM_BOARD_PACKAGE_CONTRACT:
        return None, TEAM_BOARD_PACKAGE_MISSING
    by_team = package.get('by_team_id')
    if not isinstance(by_team, Mapping):
        return None, TEAM_BOARD_PACKAGE_MISSING
    team = by_team.get(str(team_id))
    if not isinstance(team, Mapping):
        return None, TEAM_BOARD_TEAM_MISSING
    return team, None


def _published_team_state(snapshot, team_id):
    """Read the pre-trust frozen value, with legacy artifact compatibility."""
    if snapshot is None:
        return team_state_unavailable(TEAM_STATE_READINESS_UNAVAILABLE)
    from services.team_board_snapshot_team_state import receipt_value
    receipt_present, frozen_value = receipt_value(snapshot, team_id)
    if receipt_present:
        # Prospective publications use the proof-flushed value that authorized
        # the pointer. A malformed receipt fails closed; it never falls back to
        # a post-commit calculation. Legacy snapshots retain artifact serving.
        return frozen_value
    artifact = (
        db.session.query(ShareArtifact)
        .filter(
            ShareArtifact.artifact_type == TEAM_STATE_ARTIFACT_TYPE,
            ShareArtifact.team_id == team_id,
            ShareArtifact.source_snapshot_id == snapshot.id,
            ShareArtifact.subject_type.is_(None),
            ShareArtifact.lifecycle_state == LIFECYCLE_PUBLISHED,
        )
        .order_by(ShareArtifact.published_at.desc(), ShareArtifact.id.desc())
        .first()
    )
    return project_published_team_state_artifact(
        artifact,
        data_through=snapshot.data_through,
    )


def _records_for_view(team_package, include_stale):
    records = [dict(item) for item in (team_package.get('records') or []) if isinstance(item, Mapping)]
    default_ids = {_as_int(value) for value in (team_package.get('default_pitcher_ids') or [])}
    default_ids.discard(None)
    selected = [record for record in records if _as_int(record.get('pitcher_id')) in default_ids]
    if not include_stale:
        return selected

    selected_ids = {_as_int(record.get('pitcher_id')) for record in selected}
    for record in records:
        pitcher_id = _as_int(record.get('pitcher_id'))
        if pitcher_id in selected_ids:
            continue
        visibility = record.get('visibility') if isinstance(record.get('visibility'), Mapping) else {}
        if visibility.get('is_visible_by_default'):
            continue
        if not visibility.get('is_unavailable_roster_status'):
            continue
        if record.get('fatigue_score') is None:
            continue
        selected.append(record)
    return selected


def _trusted_board_freshness(snapshot, *, prefer_snapshot=False):
    freshness = None
    if not prefer_snapshot:
        freshness = board_freshness.published_snapshot_freshness_block()
        if isinstance(freshness, Mapping):
            return dict(freshness)
    payload = snapshot.payload if snapshot is not None and isinstance(snapshot.payload, Mapping) else {}
    raw = payload.get('freshness')
    return dict(raw) if isinstance(raw, Mapping) else {}


def _frozen_rest_status_for_view(snapshot, team_package):
    """Return a stamped D-055 carrier or an invalid/missing projection marker."""
    if 'rest_status' not in team_package:
        return None

    authority = team_package.get('rest_status_authority')
    if not isinstance(authority, Mapping):
        return {}
    expected_population = {
        'basis': REST_STATUS_POPULATION_BASIS,
        'population_authority': REST_STATUS_POPULATION_AUTHORITY,
        'membership_authority': REST_STATUS_MEMBERSHIP_AUTHORITY,
    }
    if (
        authority.get('method_version') != REST_STATUS_METHOD_VERSION
        or authority.get('public_contract_version')
        != REST_STATUS_PUBLIC_CONTRACT_VERSION
        or authority.get('team_board_package_contract')
        != TEAM_BOARD_PACKAGE_CONTRACT
        or authority.get('population_basis') != expected_population
        or authority.get('reference_date_policy')
        != REST_STATUS_REFERENCE_DATE_POLICY
        or authority.get('availability_reference_date')
        != _iso(getattr(snapshot, 'availability_reference_date', None))
    ):
        return {}
    return deepcopy(team_package.get('rest_status'))


def _frozen_recent_usage_rest_for_view(snapshot, team_package):
    """Return only a carrier frozen under this exact trusted team package."""
    carrier = team_package.get('recent_usage_rest')
    authority = team_package.get('recent_usage_rest_authority')
    if not isinstance(carrier, Mapping) or not isinstance(authority, Mapping):
        return None
    if (
        carrier.get('contract') != RECENT_USAGE_REST_CONTRACT
        or authority.get('method_version') != RECENT_USAGE_REST_METHOD_VERSION
        or authority.get('public_contract_version')
        != RECENT_USAGE_REST_PUBLIC_CONTRACT_VERSION
        or authority.get('carrier_contract_version') != RECENT_USAGE_REST_CONTRACT
        or authority.get('team_board_package_contract')
        != TEAM_BOARD_PACKAGE_CONTRACT
        or authority.get('reference_date_policy')
        != RECENT_USAGE_REST_REFERENCE_DATE_POLICY
        or carrier.get('data_through') != _iso(getattr(snapshot, 'data_through', None))
        or carrier.get('reference_date')
        != _iso(getattr(snapshot, 'availability_reference_date', None))
        or authority.get('data_through') != carrier.get('data_through')
        or authority.get('reference_date') != carrier.get('reference_date')
    ):
        return None
    return deepcopy(carrier)


def _frozen_workload_overview_for_view(snapshot, team_package):
    """Attach TB-04 only from the exact selected trusted team package."""
    carrier = team_package.get('workload_windows')
    authority = team_package.get('workload_windows_authority')
    if not isinstance(carrier, Mapping) or not isinstance(authority, Mapping):
        return None
    overview = carrier.get('overview')
    if not isinstance(overview, Mapping) or (
        carrier.get('contract') != WORKLOAD_WINDOWS_CARRIER_CONTRACT
        or overview.get('contract') != WORKLOAD_OVERVIEW_CONTRACT
        or authority.get('method_version') != WORKLOAD_WINDOWS_METHOD_VERSION
        or authority.get('public_contract_version') != WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION
        or authority.get('team_board_package_contract') != TEAM_BOARD_PACKAGE_CONTRACT
        or authority.get('reference_date_policy') != WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY
        or carrier.get('data_through') != _iso(getattr(snapshot, 'data_through', None))
        or overview.get('data_through') != carrier.get('data_through')
        or authority.get('data_through') != carrier.get('data_through')
    ):
        return None
    return deepcopy(overview)


def _frozen_rotation_impact_for_view(snapshot, team_package, team_id):
    """Attach only the game-level read frozen in this trusted team package."""
    carrier = team_package.get('frozen_rotation_impact')
    authority = team_package.get('frozen_rotation_impact_authority')
    represented = _iso(getattr(snapshot, 'data_through', None))
    if (
        not isinstance(carrier, Mapping)
        or not isinstance(authority, Mapping)
        or carrier.get('contract') != ROTATION_GAMES_CONTRACT
        or carrier.get('team_id') != team_id
        or carrier.get('data_through') != represented
        or carrier.get('window_days') != 7
        or authority.get('team_board_package_contract') != TEAM_BOARD_PACKAGE_CONTRACT
        or authority.get('method_version') != ROTATION_GAMES_CONTRACT
        or authority.get('data_through') != represented
        or not isinstance(carrier.get('starts'), list)
    ):
        return None
    return deepcopy(carrier)


def _frozen_roster_transactions_for_view(snapshot, team_package, team_id):
    """Attach TB-08 only from the exact selected trusted team package."""
    carrier = team_package.get('frozen_roster_transactions')
    authority = team_package.get('frozen_roster_transactions_authority')
    represented = _iso(getattr(snapshot, 'data_through', None))
    if not isinstance(carrier, Mapping) or not isinstance(authority, Mapping):
        return None
    group = carrier.get('current_group')
    if (
        carrier.get('contract') != ROSTER_TRANSACTIONS_CONTRACT
        or carrier.get('team_board_package_contract') != TEAM_BOARD_PACKAGE_CONTRACT
        or carrier.get('team_id') != team_id
        or carrier.get('data_through') != represented
        or authority.get('method_version') != ROSTER_TRANSACTIONS_CONTRACT
        or authority.get('team_board_package_contract') != TEAM_BOARD_PACKAGE_CONTRACT
        or authority.get('data_through') != represented
        or carrier.get('status') not in {'available', 'partial', 'unavailable'}
        or not isinstance(carrier.get('events'), list)
        or not isinstance(group, Mapping)
        or group.get('active_pitcher_ids') != sorted(team_package.get('default_pitcher_ids') or [])
        or group.get('active_count') != len(group['active_pitcher_ids'])
        or not isinstance(carrier.get('off_active_recent_contributors'), Mapping)
    ):
        return None
    if any(
        not isinstance(event, Mapping)
        or type(event.get('player_id')) is not int
        or event.get('direction') not in {'addition', 'removal', 'other'}
        or event.get('evidence_status') != 'complete'
        or not isinstance(event.get('source'), str)
        or not event['source']
        or not isinstance(event.get('current_roster'), Mapping)
        or not isinstance(event.get('date'), str)
        or event['date'] > represented
        for event in carrier['events']
    ):
        return None
    return deepcopy(carrier)


def _frozen_what_changed_for_view(snapshot, team_package, team_id):
    """Attach TB-09 only when its receipt matches this exact publication."""
    from services.what_changed_comparison_identity import comparison_identity_from_payload

    carrier = team_package.get('frozen_what_changed')
    if not isinstance(carrier, Mapping):
        return None
    represented = _iso(getattr(snapshot, 'data_through', None))
    embedded = comparison_identity_from_payload(getattr(snapshot, 'payload', None))
    if (
        carrier.get('contract') != WHAT_CHANGED_CONTRACT
        or carrier.get('method_version') != WHAT_CHANGED_METHOD_VERSION
        or carrier.get('team_id') != team_id
        or carrier.get('current_snapshot_id') != getattr(snapshot, 'id', None)
        or carrier.get('current_represented_date') != represented
        or carrier.get('comparison_identity') != embedded
        or carrier.get('comparison_status') not in {'complete', 'partial', 'unavailable'}
        or carrier.get('state') not in {'changes', 'quiet', 'unavailable'}
        or (carrier.get('state') != 'unavailable' and embedded is None)
        or not isinstance(carrier.get('domains'), Mapping)
        or not isinstance(carrier.get('events'), list)
    ):
        return None
    if embedded is not None and (
        carrier.get('previous_snapshot_id') != embedded['previous_snapshot_id']
        or carrier.get('previous_represented_date') != embedded['previous_data_through']
    ):
        return None
    if carrier.get('state') == 'quiet' and carrier.get('events'):
        return None
    if any(
        not isinstance(domain, Mapping)
        or domain.get('status') not in {'complete', 'partial', 'unavailable', 'not_comparable'}
        for domain in carrier['domains'].values()
    ):
        return None
    if any(
        not isinstance(event, Mapping)
        or event.get('domain') not in {
            'team_state', 'roster', 'workload_rest', 'transactions', 'rotation',
        }
        or event.get('evidence_status') != 'complete'
        or event.get('current_snapshot_id') != getattr(snapshot, 'id', None)
        or event.get('previous_snapshot_id') != carrier.get('previous_snapshot_id')
        or event.get('method_version') != WHAT_CHANGED_EVENT_METHOD_VERSION
        or not event.get('summary')
        for event in carrier['events']
    ):
        return None
    return deepcopy(carrier)


def _frozen_roles_deployment_for_view(snapshot, team_package, team_id):
    """Reject a missing or mismatched TB-05 carrier without affecting other sections."""
    carrier = team_package.get('roles_deployment')
    authority = team_package.get('roles_deployment_authority')
    represented = _iso(getattr(snapshot, 'data_through', None))
    if (
        not isinstance(carrier, Mapping)
        or not isinstance(authority, Mapping)
        or carrier.get('contract') != PUBLIC_DEPLOYMENT_CONTEXT_CONTRACT
        or carrier.get('method_version') != PUBLIC_DEPLOYMENT_CONTEXT_METHOD_VERSION
        or carrier.get('team_id') != team_id
        or carrier.get('data_through') != represented
        or carrier.get('window_days') != 14
        or authority.get('method_version') != PUBLIC_DEPLOYMENT_CONTEXT_METHOD_VERSION
        or authority.get('public_contract_version') != PUBLIC_DEPLOYMENT_CONTEXT_CONTRACT
        or authority.get('team_board_package_contract') != TEAM_BOARD_PACKAGE_CONTRACT
        or authority.get('data_through') != represented
    ):
        return None
    profiles = carrier.get('profiles')
    if not isinstance(profiles, list) or any(
        not isinstance(item, Mapping)
        or item.get('team_id') != team_id
        or type(item.get('pitcher_id')) is not int
        or not isinstance(item.get('public_role_read'), Mapping)
        or not isinstance(item.get('context'), Mapping)
        or item['context'].get('pitcher_id') != item['pitcher_id']
        or (
            item.get('observed_profile') is not None
            and (
                not isinstance(item.get('observed_profile'), Mapping)
                or item['observed_profile'].get('pitcher_id') != item['pitcher_id']
            )
        )
        for item in profiles
    ):
        return None
    return deepcopy(carrier)


def _frozen_performance_for_view(snapshot, team_package, team_id):
    """Attach only the exact team/date performance read in the trusted package."""
    carrier = team_package.get('performance')
    if not isinstance(carrier, Mapping):
        return None
    represented = _iso(getattr(snapshot, 'data_through', None))
    read = carrier.get('read')
    default_ids = set(team_package.get('default_pitcher_ids') or [])
    expected_ids = sorted(
        record['pitcher_id'] for record in team_package.get('records') or []
        if isinstance(record, Mapping)
        and type(record.get('pitcher_id')) is int
        and record['pitcher_id'] in default_ids
        and (record.get('visibility') or {}).get('is_visible_by_default') is not False
    )
    if (
        carrier.get('contract') != TEAM_BOARD_PERFORMANCE_CONTRACT
        or carrier.get('team_board_package_contract') != TEAM_BOARD_PACKAGE_CONTRACT
        or carrier.get('team_id') != team_id
        or carrier.get('data_through') != represented
        or not isinstance(read, Mapping)
        or read.get('through') != represented
        or read.get('contract_version') != 'public_team_performance_v1'
        or read.get('population_basis') != 'represented_default_visible_active_bullpen'
        or (
            isinstance(read.get('window'), Mapping)
            and read['window'].get('through') != represented
        )
        or not isinstance(read.get('capabilities'), Mapping)
        or any(
            not isinstance(read['capabilities'].get(domain), Mapping)
            or read['capabilities'][domain].get('status') != 'unavailable'
            or read['capabilities'][domain].get('value') is not None
            for domain in ('k_bb_percent', 'home_runs_allowed', 'inherited_runner_context')
        )
        or (
            read.get('status') != 'unavailable'
            and [item.get('metric_id') for item in read.get('metrics') or []]
            != ['M-001', 'M-002']
        )
        or sorted(carrier.get('population_pitcher_ids') or []) != expected_ids
    ):
        return None
    return deepcopy(read)


def _frozen_recent_relief_work_for_view(snapshot, team_package, team_id):
    """Attach TB-10 only from this exact trusted team package."""
    carrier = team_package.get('recent_relief_work')
    authority = team_package.get('recent_relief_work_authority')
    represented = _iso(getattr(snapshot, 'data_through', None))
    if (
        not isinstance(carrier, Mapping)
        or not isinstance(authority, Mapping)
        or carrier.get('contract') != RECENT_RELIEF_WORK_CONTRACT
        or carrier.get('method_version') != RECENT_RELIEF_WORK_METHOD_VERSION
        or carrier.get('team_board_package_contract') != TEAM_BOARD_PACKAGE_CONTRACT
        or carrier.get('team_id') != team_id
        or carrier.get('data_through') != represented
        or carrier.get('status') not in {'complete', 'partial', 'unavailable'}
        or authority.get('method_version') != RECENT_RELIEF_WORK_METHOD_VERSION
        or authority.get('public_contract_version') != RECENT_RELIEF_WORK_CONTRACT
        or authority.get('team_board_package_contract') != TEAM_BOARD_PACKAGE_CONTRACT
        or authority.get('data_through') != represented
        or not valid_frozen_recent_relief_work(
            carrier,
            team_id=team_id,
            data_through=represented,
            team_board_package_contract=TEAM_BOARD_PACKAGE_CONTRACT,
        )
    ):
        return None
    return deepcopy(carrier)


def _frozen_legacy_deployment_profile_for_view(snapshot, team_package):
    """Keep old publications' already-frozen profile without mutable fallback."""
    if 'roles_deployment' in team_package:
        return None
    profile = team_package.get('deployment_profile')
    authority = team_package.get('deployment_profile_authority')
    represented = _iso(getattr(snapshot, 'data_through', None))
    if (
        not isinstance(profile, Mapping)
        or not isinstance(authority, Mapping)
        or profile.get('contract') != DEPLOYMENT_PROFILE_CARRIER_CONTRACT
        or profile.get('data_through') != represented
        or authority.get('method_version') != DEPLOYMENT_PROFILE_METHOD_VERSION
        or authority.get('public_contract_version') != DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION
        or authority.get('team_board_package_contract') != TEAM_BOARD_PACKAGE_CONTRACT
        or authority.get('data_through') != represented
    ):
        return None
    return deepcopy(profile)


def build_published_team_board(
    team_id, *, include_stale=False, snapshot_override=_SNAPSHOT_NOT_PROVIDED,
    team_state_override=None, include_delivery_identity=False,
    include_recent_usage_rest=False,
):
    snapshot = (
        snapshot_override
        if snapshot_override is not _SNAPSHOT_NOT_PROVIDED
        else dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    )
    if snapshot is None:
        return _unavailable_board(team_id, TEAM_BOARD_UNAVAILABLE, snapshot=None)
    team_package, reason = _team_package(snapshot, team_id)
    if team_package is None:
        return _unavailable_board(team_id, reason, snapshot=snapshot)

    freshness = _trusted_board_freshness(
        snapshot, prefer_snapshot=snapshot_override is not _SNAPSHOT_NOT_PROVIDED,
    )
    records = _records_for_view(team_package, include_stale)
    payload = build_board_payload(
        team=deepcopy(team_package.get('team') or {'team_id': team_id}),
        records=records,
        freshness=freshness,
        limitations=list(freshness.get('limitations') or []),
        roster_authority=deepcopy(team_package.get('roster_authority') or {}),
        generated_at=(snapshot.snapshot_generated_at.isoformat() if snapshot.snapshot_generated_at else None),
        workload_concentration=deepcopy(team_package.get('workload_concentration') or {}),
        capacity_intelligence=deepcopy(team_package.get('capacity_intelligence') or {}),
        rotation_support_pressure=deepcopy(team_package.get('rotation_support_pressure') or {}),
        bullpen_stability=deepcopy(team_package.get('bullpen_stability') or {}),
        bullpen_environment=deepcopy(team_package.get('bullpen_environment') or {}),
        frozen_rest_status=_frozen_rest_status_for_view(snapshot, team_package),
    )
    payload['team_state'] = (
        deepcopy(team_state_override)
        if team_state_override is not None
        else _published_team_state(snapshot, team_id)
    )
    if include_recent_usage_rest:
        payload['recent_usage_rest'] = _frozen_recent_usage_rest_for_view(
            snapshot, team_package
        )
        payload['workload_overview'] = _frozen_workload_overview_for_view(
            snapshot, team_package
        )
        payload['frozen_roles_deployment'] = _frozen_roles_deployment_for_view(
            snapshot, team_package, team_id,
        )
        payload['frozen_performance'] = _frozen_performance_for_view(
            snapshot, team_package, team_id,
        )
        payload['frozen_rotation_impact'] = _frozen_rotation_impact_for_view(
            snapshot, team_package, team_id,
        )
        payload['frozen_roster_transactions'] = _frozen_roster_transactions_for_view(
            snapshot, team_package, team_id,
        )
        payload['frozen_what_changed'] = _frozen_what_changed_for_view(
            snapshot, team_package, team_id,
        )
        payload['frozen_recent_relief_work'] = _frozen_recent_relief_work_for_view(
            snapshot, team_package, team_id,
        )
        payload['frozen_legacy_deployment_profile'] = (
            _frozen_legacy_deployment_profile_for_view(snapshot, team_package)
        )
        payload['workload_windows'] = (
            deepcopy((team_package.get('workload_windows') or {}).get('windows'))
            if payload['workload_overview'] is not None else None
        )
    payload['publication_authority'] = publication_authority(snapshot)
    if include_delivery_identity:
        payload['publication_method_versions'] = {
            'bullpen_membership': _mapping_value(
                team_package.get('bullpen_membership_authority'), 'method_version'
            ),
            'rest_status': _mapping_value(
                team_package.get('rest_status_authority'), 'method_version'
            ),
            'workload_windows': _mapping_value(
                team_package.get('workload_windows_authority'), 'method_version'
            ),
            'deployment_profile': _mapping_value(
                team_package.get('deployment_profile_authority'), 'method_version'
            ),
            'recent_usage_rest': _mapping_value(
                team_package.get('recent_usage_rest_authority'), 'method_version'
            ),
            'rotation_impact': _mapping_value(
                team_package.get('rotation_support_pressure_authority'), 'method_version'
            ),
        }
    payload['served_from'] = 'trusted_dashboard_snapshot'
    return payload


def _unavailable_board(team_id, reason, *, snapshot):
    freshness = _trusted_board_freshness(snapshot) if snapshot is not None else {}
    payload = build_board_payload(
        team={'team_id': team_id, 'team_name': None, 'team_abbreviation': None},
        records=[],
        freshness=freshness,
        limitations=list(freshness.get('limitations') or []),
        roster_authority={},
        generated_at=(snapshot.snapshot_generated_at.isoformat() if snapshot and snapshot.snapshot_generated_at else None),
        frozen_rest_status=None,
    )
    payload.update({
        'status': 'snapshot_unavailable',
        'reason': reason,
        'team_state': team_state_unavailable(
            TEAM_STATE_READINESS_UNAVAILABLE,
            data_through=_iso(snapshot.data_through) if snapshot else None,
            reason_code=reason,
        ),
        'publication_authority': publication_authority(snapshot),
        'served_from': 'trusted_dashboard_snapshot_unavailable',
    })
    return payload


def trusted_team_board_view(team_id):
    include_stale = _truthy(request.args.get('include_stale'))
    return jsonify(build_published_team_board(team_id, include_stale=include_stale))


def trusted_team_compare_view():
    team_a, error = parse_positive_int_param(request.args, 'team_a')
    if error:
        return query_param_error_response(error)
    team_b, error = parse_positive_int_param(request.args, 'team_b')
    if error:
        return query_param_error_response(error)
    if team_a is None or team_b is None:
        return query_param_error_response(
            QueryParamError('team_a', 'team_a and team_b query parameters are required.')
        )
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if snapshot is None:
        return jsonify({
            'capability': 'current_bullpen_comparison_v1',
            'status': 'snapshot_unavailable',
            'reason_code': TEAM_BOARD_UNAVAILABLE,
            'comparison': None,
            'publication_authority': None,
        })

    # Import lazily to keep the frozen-package builder free of a module cycle.
    from services.current_bullpen_comparison import build_current_bullpen_comparison
    comparison, reason = build_current_bullpen_comparison(snapshot, team_a, team_b)
    if comparison is None:
        return jsonify({
            'capability': 'current_bullpen_comparison_v1',
            'status': 'snapshot_unavailable',
            'reason_code': reason,
            'comparison': None,
            'publication_authority': publication_authority(snapshot),
        })
    return jsonify({
        'capability': 'current_bullpen_comparison_v1',
        'status': comparison['status'],
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'comparison': comparison,
        'publication_authority': publication_authority(snapshot),
    })


def trusted_tonight_view():
    # Import the existing parser lazily so request validation remains byte-for-byte
    # compatible without importing the bullpen API while this module is loaded.
    from api.bullpen import (
        _tonight_reference_date_from_request,
        tonight_query_error_response,
    )

    reference_date, error = _tonight_reference_date_from_request()
    if error:
        return tonight_query_error_response(error)
    payload = tonight_intelligence_snapshot.serve_tonight_cached(
        reference_date=reference_date,
        persist=False,
        build_on_miss=False,
    )
    if payload.get('status') == 'empty' and payload.get('empty_reason') == tonight_intelligence_snapshot.EMPTY_SNAPSHOT_BUILD_UNAVAILABLE:
        payload = dict(payload)
        payload['empty_reason'] = TONIGHT_SNAPSHOT_UNAVAILABLE
        limitations = list(payload.get('limitations') or [])
        message = 'No trusted Tonight snapshot is published for this slate; live rebuild is disabled.'
        if message not in limitations:
            limitations.append(message)
        payload['limitations'] = limitations
    return jsonify(payload)


def install_public_serving_authority(app):
    """Install production-only publication-bound serving and candidate capture."""
    if app.config.get('APP_ENV') != 'production' and not _truthy(app.config.get('TRUSTED_PUBLIC_SERVING_ENABLED')):
        return False
    if app.extensions.get('baseballos_trusted_public_serving_installed'):
        return True

    # Dashboard snapshot construction imports this attribute lazily, so wrapping
    # it here guarantees the frozen board package is assembled before the payload
    # is stored/published, not after publication.
    from api import bullpen as bullpen_api

    original_dashboard_builder = bullpen_api.build_bullpen_dashboard_payload

    def trusted_dashboard_builder(*args, **kwargs):
        payload = original_dashboard_builder(*args, **kwargs)
        return attach_frozen_team_boards(payload)

    bullpen_api.build_bullpen_dashboard_payload = trusted_dashboard_builder

    # Replace only public reader endpoints. Internal builders remain available to
    # candidate generation and diagnostics; they simply stop being public serving
    # authority in production.
    app.view_functions['bullpen.get_team_bullpen_board'] = trusted_team_board_view
    app.view_functions['bullpen.compare_team_bullpens'] = trusted_team_compare_view
    app.view_functions['bullpen.get_tonight_intelligence'] = trusted_tonight_view
    app.extensions['baseballos_trusted_public_serving_installed'] = True
    return True
