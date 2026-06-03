"""Internal Team Operations API routes."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from services import sync as sync_service
from services import sync_metadata
from services.availability_snapshot import (
    CURRENT_AVAILABILITY_MODE,
    classify_latest_fatigue_rows,
    latest_fatigue_rows,
)
from team_operations import (
    assemble_bullpen_readiness,
)
from team_operations.contracts import require_team_operations_governance_safe


team_operations_bp = Blueprint('team_operations', __name__)

TEAM_OPERATIONS_READINESS_ENDPOINT = '/api/team-operations/bullpen-readiness'
TEAM_OPERATIONS_READINESS_DOCUMENT = (
    'docs/V3_PHASE_6_TEAM_OPERATIONS_BULLPEN_READINESS_INTERNAL_API_ROUTE_INTEGRATION.md'
)
TEAM_OPERATIONS_CONTRACT_DOCUMENT = (
    'docs/V3_PHASE_4_TEAM_OPERATIONS_BULLPEN_READINESS_API_CONTRACT_AND_CERTIFICATION_REQUIREMENTS.md'
)
TEAM_OPERATIONS_DEFAULT_LIMIT = 750
TEAM_OPERATIONS_ALLOWED_QUERY_FIELDS = frozenset(
    {
        'team_id',
        'team_abbreviation',
        'include_details',
    }
)
TEAM_OPERATIONS_PROHIBITED_QUERY_TOKENS = (
    'best',
    'recommend',
    'rank',
    'select',
    'matchup',
    'predict',
    'save',
    'injury',
    'performance',
)


@team_operations_bp.route('/bullpen-readiness', methods=['GET'])
def get_team_operations_bullpen_readiness():
    sync_status = _sync_status_payload()
    request_refusal = _request_refusal(request.args)
    team_id = request.args.get('team_id', type=int)
    team_abbreviation = request.args.get('team_abbreviation')

    if request_refusal:
        payload = assemble_bullpen_readiness(
            team=_team_payload_from_request(team_id, team_abbreviation),
            trust_metadata=_team_operations_trust_metadata(
                (),
                sync_status=sync_status,
                generated_at=_generated_at(()),
            ),
            freshness=_team_operations_freshness_metadata(
                (),
                sync_status=sync_status,
                generated_at=_generated_at(()),
            ),
            refusal=request_refusal,
            generated_at=_generated_at(()),
        )
        return jsonify(_route_payload(payload)), 400

    try:
        rows = tuple(latest_fatigue_rows(team_id=team_id, limit=TEAM_OPERATIONS_DEFAULT_LIMIT))
        records = tuple(
            _filter_records_by_team_abbreviation(
                classify_latest_fatigue_rows(
                    rows,
                    mode=CURRENT_AVAILABILITY_MODE,
                ),
                team_abbreviation=team_abbreviation,
            )
        )
    except Exception:
        payload = assemble_bullpen_readiness(
            team=_team_payload_from_request(team_id, team_abbreviation),
            trust_metadata=_team_operations_trust_metadata(
                (),
                sync_status=sync_status,
                generated_at=_generated_at(()),
            ),
            freshness=_team_operations_freshness_metadata(
                (),
                sync_status=sync_status,
                generated_at=_generated_at(()),
            ),
            refusal=_refusal(
                refusal_id='source_input_error',
                reason='source_input_error',
                message='Readiness output is refused because source inputs could not be assembled safely.',
            ),
            generated_at=_generated_at(()),
        )
        return jsonify(_route_payload(payload)), 503

    generated_at = _generated_at(rows)
    if not records:
        payload = assemble_bullpen_readiness(
            team=_team_payload_from_request(team_id, team_abbreviation),
            trust_metadata=_team_operations_trust_metadata(
                records,
                sync_status=sync_status,
                generated_at=generated_at,
            ),
            freshness=_team_operations_freshness_metadata(
                records,
                sync_status=sync_status,
                generated_at=generated_at,
            ),
            refusal=_refusal(
                refusal_id='source_inputs_missing',
                reason='source_inputs_missing',
                message='Readiness output is refused because no current source inputs are available.',
            ),
            generated_at=generated_at,
        )
        return jsonify(_route_payload(payload)), 503

    payload = assemble_bullpen_readiness(
        team=_team_payload_from_records(
            records,
            team_id=team_id,
            team_abbreviation=team_abbreviation,
        ),
        pitcher_records=tuple(_readiness_record(record) for record in records),
        trust_metadata=_team_operations_trust_metadata(
            records,
            sync_status=sync_status,
            generated_at=generated_at,
        ),
        freshness=_team_operations_freshness_metadata(
            records,
            sync_status=sync_status,
            generated_at=generated_at,
        ),
        generated_at=generated_at,
    )
    status_code = 503 if payload['contract_state'] == 'refused' else 200
    return jsonify(_route_payload(payload)), status_code


def _request_refusal(args):
    for key in args.keys():
        normalized_key = str(key).lower()
        if normalized_key not in TEAM_OPERATIONS_ALLOWED_QUERY_FIELDS:
            reason = (
                'forbidden_request_parameter'
                if _contains_prohibited_query_intent(normalized_key)
                else 'unsupported_request_parameter'
            )
            return _refusal(
                refusal_id=reason,
                reason=reason,
                message='Readiness output is refused because request parameters are not supported for this internal route.',
            )
        for value in args.getlist(key):
            if _contains_prohibited_query_intent(str(value).lower()):
                return _refusal(
                    refusal_id='forbidden_request_parameter',
                    reason='forbidden_request_parameter',
                    message='Readiness output is refused because request parameters are not supported for this internal route.',
                )

    if 'team_id' in args and args.get('team_id', type=int) is None:
        return _refusal(
            refusal_id='invalid_request_parameter',
            reason='invalid_request_parameter',
            message='Readiness output is refused because team_id must be an integer.',
        )

    if 'include_details' in args and str(args.get('include_details')).lower() not in {
        '0',
        '1',
        'false',
        'true',
        'no',
        'yes',
    }:
        return _refusal(
            refusal_id='invalid_request_parameter',
            reason='invalid_request_parameter',
            message='Readiness output is refused because include_details must be boolean-like.',
        )

    return None


def _contains_prohibited_query_intent(value):
    return any(token in value for token in TEAM_OPERATIONS_PROHIBITED_QUERY_TOKENS)


def _refusal(*, refusal_id, reason, message):
    return {
        'refused': True,
        'refusal_id': refusal_id,
        'reason': reason,
        'message': message,
        'applies_to': 'readiness',
        'recovery_note': 'Remove unsupported request parameters and refresh readiness evidence.',
    }


def _route_payload(payload):
    route_payload = dict(payload)
    route_payload['route_metadata'] = {
        'route': TEAM_OPERATIONS_READINESS_ENDPOINT,
        'surface': 'team_operations_bullpen_readiness_internal_route',
        'route_document': TEAM_OPERATIONS_READINESS_DOCUMENT,
        'contract_document': TEAM_OPERATIONS_CONTRACT_DOCUMENT,
        'exposure': 'internal',
        'production_status': 'non_production',
        'certification_status': 'uncertified',
        'public_certified': False,
        'frontend_exposure': False,
    }
    require_team_operations_governance_safe(route_payload)
    return route_payload


def _sync_status_payload():
    try:
        return sync_metadata.build_sync_status_payload(
            legacy_status=sync_service.read_status(),
        )
    except Exception:
        return {
            'status': sync_metadata.STATUS_METADATA_UNAVAILABLE,
            'last_sync': None,
            'last_successful_sync': None,
            'finished_at': None,
            'data': {
                'game_logs': None,
                'latest_game_date': None,
                'latest_workload_date': None,
                'latest_fatigue_calculated_at': None,
            },
            'freshness': {
                'is_current': False,
                'label': 'Sync metadata unavailable.',
                'limitations': ['Could not read sync status metadata.'],
            },
        }


def _generated_at(rows):
    timestamps = [
        score.calculated_at
        for score, _pitcher in rows
        if getattr(score, 'calculated_at', None) is not None
    ]
    if timestamps:
        return max(timestamps).replace(microsecond=0).isoformat()
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _filter_records_by_team_abbreviation(records, *, team_abbreviation=None):
    if not team_abbreviation:
        return tuple(records)
    normalized = str(team_abbreviation).upper()
    return tuple(
        record
        for record in records
        if str(getattr(record.get('pitcher'), 'team_abbreviation', '')).upper()
        == normalized
    )


def _team_payload_from_request(team_id, team_abbreviation):
    if team_id is None and not team_abbreviation:
        return None
    return {
        'team_id': team_id,
        'team_name': None,
        'team_abbreviation': team_abbreviation,
    }


def _team_payload_from_records(records, *, team_id=None, team_abbreviation=None):
    pitchers = [record.get('pitcher') for record in records if record.get('pitcher')]
    team_ids = {getattr(pitcher, 'team_id', None) for pitcher in pitchers}
    team_names = {getattr(pitcher, 'team_name', None) for pitcher in pitchers}
    team_abbreviations = {
        getattr(pitcher, 'team_abbreviation', None)
        for pitcher in pitchers
    }
    return {
        'team_id': team_id or _single_value(team_ids),
        'team_name': _single_value(team_names),
        'team_abbreviation': team_abbreviation or _single_value(team_abbreviations),
    }


def _single_value(values):
    values = {value for value in values if value is not None}
    return next(iter(values)) if len(values) == 1 else None


def _readiness_record(record):
    availability = dict(record.get('availability') or {})
    inputs = dict(availability.get('inputs') or {})
    pitcher = record.get('pitcher')
    return {
        'availability_status': availability.get('availability_status', 'unknown'),
        'workload_category': _workload_category(record),
        'throwing_hand': getattr(pitcher, 'throws', None) or 'unknown',
        'has_current_workload': availability.get('data_state') == 'fresh'
        and bool(record.get('latest_game_date') or inputs.get('latest_game_date')),
        'has_availability': bool(availability.get('availability_status')),
        'active': bool(getattr(pitcher, 'active', True)),
    }


def _workload_category(record):
    availability = dict(record.get('availability') or {})
    status = availability.get('availability_status')
    if status in {'Avoid', 'Unavailable'}:
        return 'elevated'
    if status in {'Monitor', 'Limited'}:
        return 'moderate'

    score = record.get('score')
    raw_value = getattr(score, 'raw_score', None)
    if raw_value is None:
        return 'unknown'
    if float(raw_value) >= 60:
        return 'elevated'
    if float(raw_value) >= 30:
        return 'moderate'
    return 'low'


def _team_operations_trust_metadata(records, *, sync_status, generated_at):
    records = tuple(records or ())
    availability_payloads = [dict(record.get('availability') or {}) for record in records]
    confidence_values = [payload.get('confidence') for payload in availability_payloads]
    data_states = [payload.get('data_state') for payload in availability_payloads]
    has_records = bool(records)
    has_low_confidence = any(value in {'low', 'unknown'} for value in confidence_values)
    has_non_fresh_data = any(value != 'fresh' for value in data_states)

    if not has_records:
        confidence = 'unknown'
        data_state = 'missing'
        reasons = ['source_inputs_missing']
    elif has_low_confidence or has_non_fresh_data:
        confidence = 'low'
        data_state = 'incomplete' if has_non_fresh_data else 'fresh'
        reasons = ['limited_availability_evidence']
    else:
        confidence = 'high'
        data_state = 'fresh'
        reasons = ['current_availability_evidence']

    return {
        'confidence': confidence,
        'confidence_reasons': reasons,
        'data_state': data_state,
        'source_evidence_state': 'represented' if has_records else 'missing',
        'governance_state': 'internal_uncertified',
        'generated_at': generated_at,
        'limitations': _trust_limitations(sync_status, has_records=has_records),
        'explanations': [],
        'refusal_reasons': [],
        'trust_validation_errors': [],
        'ranking_applied': False,
        'selection_made': False,
    }


def _trust_limitations(sync_status, *, has_records):
    limitations = []
    if not has_records:
        limitations.append('No readiness source records are available.')
    sync_freshness = dict(sync_status.get('freshness') or {})
    limitations.extend(sync_freshness.get('limitations') or [])
    return limitations


def _team_operations_freshness_metadata(records, *, sync_status, generated_at):
    records = tuple(records or ())
    sync_data = dict(sync_status.get('data') or {})
    sync_freshness = dict(sync_status.get('freshness') or {})
    latest_workload_date = sync_data.get('latest_workload_date')
    latest_game_date = sync_data.get('latest_game_date')
    latest_fatigue = sync_data.get('latest_fatigue_calculated_at')

    if not records:
        freshness_state = 'missing'
    elif sync_freshness.get('is_current') is True:
        freshness_state = 'current'
    elif latest_workload_date or latest_game_date:
        freshness_state = 'stale'
    else:
        freshness_state = 'missing'

    return {
        'freshness_state': freshness_state,
        'data_through': latest_game_date or latest_workload_date,
        'latest_workload_date': latest_workload_date,
        'last_successful_sync': sync_status.get('last_successful_sync'),
        'latest_sync_status': sync_status.get('status'),
        'latest_fatigue_calculated_at': latest_fatigue,
        'generated_at': generated_at,
        'stale_warning': (
            sync_freshness.get('label')
            if freshness_state in {'stale', 'historical'}
            else None
        ),
        'missing_data_warning': (
            'Required workload evidence is missing.'
            if freshness_state == 'missing'
            else None
        ),
        'limitations': list(sync_freshness.get('limitations') or []),
    }
