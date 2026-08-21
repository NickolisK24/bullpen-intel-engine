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
from services.bullpen_comparison import build_team_comparison
from services.bullpen_population import eligible_bullpen_pitcher_contexts, usage_logs_by_pitcher
from services.bullpen_visibility import build_visibility_contract
from services.pitcher_role_authority import author_role_read_labels, role_logs_by_pitcher
from services.public_fatigue_view import public_workload_facts
from services.public_roster_readiness import apply_public_roster_readiness, build_public_roster_readiness
from services.public_team_relief_work import (
    WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY,
    WORKLOAD_WINDOWS_METHOD_VERSION,
    WORKLOAD_WINDOWS_POPULATION_AUTHORITY,
    WORKLOAD_WINDOWS_POPULATION_BASIS,
    WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION,
    WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY,
    author_workload_windows,
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
    VERSION as ROTATION_IMPACT_METHOD_VERSION,
)
from services.published_team_state import project_published_team_state_artifact
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE
from services.team_state_public_vocabulary import (
    TEAM_STATE_READINESS_UNAVAILABLE,
    team_state_unavailable,
)
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
        .filter(Pitcher.active == True, Pitcher.team_id.isnot(None))
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
        workload_windows = author_workload_windows(
            team_id,
            data_through=(
                freshness.get('data_through')
                or freshness.get('latest_workload_date')
            ),
        )
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

    return {
        'contract': TEAM_BOARD_PACKAGE_CONTRACT,
        'generated_at': payload.get('generated_at') or datetime.now(timezone.utc).isoformat(),
        'data_through': freshness.get('data_through') or freshness.get('latest_workload_date'),
        'availability_reference_date': reference_date.isoformat(),
        'team_count': len(by_team_id),
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
    """Read Team State from the immutable league artifact for this exact snapshot."""
    if snapshot is None:
        return team_state_unavailable(TEAM_STATE_READINESS_UNAVAILABLE)
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


def _trusted_board_freshness(snapshot):
    freshness = board_freshness.published_snapshot_freshness_block()
    if isinstance(freshness, Mapping):
        return dict(freshness)
    payload = snapshot.payload if snapshot is not None and isinstance(snapshot.payload, Mapping) else {}
    raw = payload.get('freshness')
    return dict(raw) if isinstance(raw, Mapping) else {}


def build_published_team_board(team_id, *, include_stale=False):
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if snapshot is None:
        return _unavailable_board(team_id, TEAM_BOARD_UNAVAILABLE, snapshot=None)
    team_package, reason = _team_package(snapshot, team_id)
    if team_package is None:
        return _unavailable_board(team_id, reason, snapshot=snapshot)

    freshness = _trusted_board_freshness(snapshot)
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
    )
    payload['team_state'] = _published_team_state(snapshot, team_id)
    payload['publication_authority'] = publication_authority(snapshot)
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
    include_stale = _truthy(request.args.get('include_stale'))
    board_a = build_published_team_board(team_a, include_stale=include_stale)
    board_b = build_published_team_board(team_b, include_stale=include_stale)
    generated_at = datetime.now(timezone.utc).isoformat()
    comparison = build_team_comparison(board_a, board_b, generated_at=generated_at)
    same_authority = (
        (board_a.get('publication_authority') or {}).get('snapshot_id')
        == (board_b.get('publication_authority') or {}).get('snapshot_id')
    )
    status = 'ok' if same_authority and board_a.get('status') != 'snapshot_unavailable' and board_b.get('status') != 'snapshot_unavailable' else 'snapshot_unavailable'
    return jsonify({
        'capability': 'team_bullpen_comparison',
        'status': status,
        'generated_at': comparison['generated_at'],
        'ranking_applied': False,
        'selection_made': False,
        'team_a': board_a,
        'team_b': board_b,
        'comparison': comparison,
        'publication_authority': board_a.get('publication_authority') if same_authority else None,
    })


def trusted_tonight_view():
    # Import the existing parser lazily so request validation remains byte-for-byte
    # compatible without importing the bullpen API while this module is loaded.
    from api.bullpen import _tonight_reference_date_from_request

    reference_date, error = _tonight_reference_date_from_request()
    if error:
        return query_param_error_response(error)
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
