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
from services.bullpen_board import build_board_payload, last_workload_appearance_from_logs
from services.bullpen_comparison import build_team_comparison
from services.bullpen_population import eligible_bullpen_pitcher_contexts, usage_logs_by_pitcher
from services.bullpen_visibility import build_visibility_contract
from services.pitcher_role_authority import author_role_read_labels, role_logs_by_pitcher
from services.public_roster_readiness import apply_public_roster_readiness, build_public_roster_readiness
from services.roster_authority import build_roster_authority
from services.share_artifacts import verify_share_artifact_integrity
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE
from services.team_state_public_vocabulary import (
    TEAM_STATE_READINESS_UNAVAILABLE,
    public_team_state,
    team_state_unavailable,
)
from services.workload_concentration import summarize_recent_relief_workload
from utils.db import db


TEAM_BOARD_PACKAGE_KEY = 'trusted_team_boards'
TEAM_BOARD_PACKAGE_CONTRACT = 'trusted_team_board_publication_v1'
PUBLICATION_AUTHORITY_CONTRACT = 'trusted_dashboard_publication_v1'
TEAM_BOARD_UNAVAILABLE = 'trusted_team_board_unavailable'
TEAM_BOARD_PACKAGE_MISSING = 'trusted_team_board_package_missing'
TEAM_BOARD_TEAM_MISSING = 'trusted_team_board_team_missing'
TONIGHT_SNAPSHOT_UNAVAILABLE = 'trusted_tonight_snapshot_unavailable'


def _truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _iso(value):
    return value.isoformat() if value is not None else None


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _publication_authority(snapshot):
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
        workload_concentration = summarize_recent_relief_workload(
            role_logs,
            reference_date,
            pitcher_ids=set(default_ids),
        )
        by_team_id[str(team_id)] = {
            'team': deepcopy(team_info.get(team_id) or {'team_id': team_id}),
            'records': records,
            'default_pitcher_ids': default_ids,
            'roster_authority': deepcopy(roster_authority),
            'workload_concentration': deepcopy(workload_concentration),
            'capacity_intelligence': _support_for_team(payload, 'capacity_intelligence', team_id),
            'rotation_support_pressure': _support_for_team(payload, 'rotation_support_pressure', team_id),
            'bullpen_stability': _support_for_team(payload, 'bullpen_stability', team_id),
            'bullpen_environment': _support_for_team(payload, 'bullpen_environment', team_id),
        }

    freshness = payload.get('freshness') if isinstance(payload.get('freshness'), Mapping) else {}
    return {
        'contract': TEAM_BOARD_PACKAGE_CONTRACT,
        'generated_at': payload.get('generated_at') or datetime.now(timezone.utc).isoformat(),
        'data_through': freshness.get('data_through') or freshness.get('latest_workload_date'),
        'availability_reference_date': reference_date.isoformat(),
        'team_count': len(by_team_id),
        'by_team_id': by_team_id,
    }


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
    if artifact is None:
        return team_state_unavailable(
            TEAM_STATE_READINESS_UNAVAILABLE,
            data_through=_iso(snapshot.data_through),
            reason_code='published_team_state_artifact_missing',
        )
    try:
        verify_share_artifact_integrity(artifact)
    except Exception:
        return team_state_unavailable(
            TEAM_STATE_READINESS_UNAVAILABLE,
            data_through=_iso(snapshot.data_through),
            reason_code='published_team_state_artifact_integrity_failed',
        )
    document = artifact.payload if isinstance(artifact.payload, Mapping) else {}
    team_state = document.get('team_state') if isinstance(document.get('team_state'), Mapping) else {}
    authority = document.get('authority') if isinstance(document.get('authority'), Mapping) else {}
    status_code = team_state.get('status_code')
    readiness = {
        'contract_state': team_state.get('contract_state'),
        'readiness': {'status_code': status_code},
        'freshness': {
            'data_through': authority.get('data_through') or _iso(snapshot.data_through),
        },
    }
    return public_team_state(readiness)


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
    payload['publication_authority'] = _publication_authority(snapshot)
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
        'publication_authority': _publication_authority(snapshot),
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
