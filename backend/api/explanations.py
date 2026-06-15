"""Governed explanation API routes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

from flask import Blueprint, jsonify, request
from sqlalchemy import desc

from explanations import (
    V4GovernancePayload,
    require_v4_governance_safe,
    serialize_availability_explanation,
    serialize_readiness_explanation,
)
from explanations.readiness import SUPPORTED_READINESS_EXPLANATION_SCOPES
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability import ACTIVE_WINDOW_DAYS, classify_availability
from services import sync_metadata
from services.availability_reference_date import (
    product_availability_reference_date_from_sync_status,
    product_current_date,
)
from services.availability_snapshot import (
    CURRENT_AVAILABILITY_MODE,
    classify_latest_fatigue_rows,
    latest_fatigue_rows,
)
from team_operations import assemble_bullpen_readiness
from utils.db import db

from api import team_operations as team_operations_api


explanations_bp = Blueprint('explanations', __name__)

AVAILABILITY_EXPLANATION_TYPE = 'availability_explanation'
TEAM_READINESS_EXPLANATION_TYPE = 'team_readiness_explanation'
CERTIFIED_EXPLANATION_TYPES = frozenset(
    {
        AVAILABILITY_EXPLANATION_TYPE,
        TEAM_READINESS_EXPLANATION_TYPE,
    }
)
EXPLANATION_CERTIFICATION_STATUS = 'certified_with_non_blocking_observations'
EXPLANATION_ROUTE_STATUS = 'internal_uncertified_route'
EXPLANATION_DEFAULT_LIMIT = 750

AVAILABILITY_ALLOWED_QUERY_FIELDS = frozenset()
TEAM_READINESS_ALLOWED_QUERY_FIELDS = frozenset(
    {
        'scope',
        'team_id',
        'team_abbreviation',
    }
)
PROHIBITED_QUERY_TOKENS = (
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


class ExplanationRouteError(Exception):
    """Controlled route-level failure for governed fail-closed responses."""

    def __init__(
        self,
        *,
        reason_code: str,
        summary: str,
        limitation_type: str = 'missing_data',
        status_code: int = 503,
    ):
        super().__init__(summary)
        self.reason_code = reason_code
        self.summary = summary
        self.limitation_type = limitation_type
        self.status_code = status_code


@explanations_bp.route('/availability/<int:pitcher_id>', methods=['GET'])
def get_availability_explanation(pitcher_id):
    query_error = _query_error(
        request.args,
        allowed_fields=AVAILABILITY_ALLOWED_QUERY_FIELDS,
    )
    if query_error:
        return _fail_closed_response(
            explanation_type=AVAILABILITY_EXPLANATION_TYPE,
            reason_code=query_error.reason_code,
            summary=query_error.summary,
            limitation_type=query_error.limitation_type,
            status_code=query_error.status_code,
        )

    try:
        explanation = _availability_explanation_payload(pitcher_id)
    except ExplanationRouteError as exc:
        return _fail_closed_response(
            explanation_type=AVAILABILITY_EXPLANATION_TYPE,
            reason_code=exc.reason_code,
            summary=exc.summary,
            limitation_type=exc.limitation_type,
            status_code=exc.status_code,
        )
    except Exception:
        return _fail_closed_response(
            explanation_type=AVAILABILITY_EXPLANATION_TYPE,
            reason_code='builder_validation_failed',
            summary='Availability explanation could not be generated safely.',
            limitation_type='insufficient_context',
            status_code=500,
        )

    return jsonify(_success_envelope(AVAILABILITY_EXPLANATION_TYPE, explanation))


@explanations_bp.route('/team-readiness', methods=['GET'])
def get_team_readiness_explanation():
    scope = request.args.get('scope') or 'readiness_state'
    return _team_readiness_response(scope)


@explanations_bp.route('/team-readiness/<scope>', methods=['GET'])
def get_team_readiness_explanation_for_scope(scope):
    return _team_readiness_response(scope)


@explanations_bp.route('/<explanation_type>', methods=['GET'])
def reject_uncertified_explanation_type(explanation_type):
    if explanation_type in CERTIFIED_EXPLANATION_TYPES:
        return _fail_closed_response(
            explanation_type=explanation_type,
            reason_code='unsupported_route_shape',
            summary='The requested explanation route shape is not supported.',
            limitation_type='insufficient_context',
            status_code=404,
        )

    return _fail_closed_response(
        explanation_type=str(explanation_type),
        reason_code='uncertified_explanation_type',
        summary='The requested explanation type is not available for API exposure.',
        limitation_type='uncertified_source',
        status_code=403,
    )


def _team_readiness_response(scope: str):
    query_error = _query_error(
        request.args,
        allowed_fields=TEAM_READINESS_ALLOWED_QUERY_FIELDS,
    )
    if query_error:
        return _fail_closed_response(
            explanation_type=TEAM_READINESS_EXPLANATION_TYPE,
            reason_code=query_error.reason_code,
            summary=query_error.summary,
            limitation_type=query_error.limitation_type,
            status_code=query_error.status_code,
        )

    if scope not in SUPPORTED_READINESS_EXPLANATION_SCOPES:
        return _fail_closed_response(
            explanation_type=TEAM_READINESS_EXPLANATION_TYPE,
            reason_code='unsupported_scope',
            summary='The requested readiness explanation scope is not available for API exposure.',
            limitation_type='uncertified_source',
            status_code=422,
        )

    try:
        readiness_payload = _team_readiness_payload_from_request()
        explanation = serialize_readiness_explanation(
            readiness_payload,
            scope=scope,
            generated_at=readiness_payload.get('generated_at'),
        )
    except ExplanationRouteError as exc:
        return _fail_closed_response(
            explanation_type=TEAM_READINESS_EXPLANATION_TYPE,
            reason_code=exc.reason_code,
            summary=exc.summary,
            limitation_type=exc.limitation_type,
            status_code=exc.status_code,
        )
    except Exception:
        return _fail_closed_response(
            explanation_type=TEAM_READINESS_EXPLANATION_TYPE,
            reason_code='builder_validation_failed',
            summary='Team Operations readiness explanation could not be generated safely.',
            limitation_type='insufficient_context',
            status_code=500,
        )

    return jsonify(_success_envelope(TEAM_READINESS_EXPLANATION_TYPE, explanation))


def _availability_explanation_payload(pitcher_id: int) -> dict[str, Any]:
    pitcher = db.session.get(Pitcher, pitcher_id)
    if pitcher is None:
        raise ExplanationRouteError(
            reason_code='unknown_subject',
            summary='Availability explanation cannot be generated because the pitcher was not found.',
            status_code=404,
        )

    latest_score = (
        FatigueScore.query
        .filter_by(pitcher_id=pitcher_id)
        .order_by(desc(FatigueScore.calculated_at))
        .first()
    )
    if latest_score is None:
        raise ExplanationRouteError(
            reason_code='missing_source_data',
            summary='Availability explanation cannot be generated because fatigue evidence is unavailable.',
            status_code=503,
        )

    sync_status = _sync_status_payload()
    reference_date = _availability_reference_date(sync_status)
    latest_game_date = (
        GameLog.query
        .filter_by(pitcher_id=pitcher_id)
        .with_entities(GameLog.game_date)
        .order_by(desc(GameLog.game_date))
        .limit(1)
        .scalar()
    )
    window_start = reference_date - timedelta(days=4)
    logs = (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_date >= window_start,
            GameLog.game_date <= reference_date,
        )
        .order_by(desc(GameLog.game_date))
        .all()
    )

    availability = classify_availability(
        score=latest_score,
        game_logs=logs,
        reference_date=reference_date,
        latest_game_date=latest_game_date,
        active_window_days=ACTIVE_WINDOW_DAYS,
    )
    return serialize_availability_explanation(
        availability,
        subject_id=pitcher.id,
        generated_at=_iso_timestamp(latest_score.calculated_at),
    )


def _team_readiness_payload_from_request() -> dict[str, Any]:
    team_id = request.args.get('team_id', type=int)
    if 'team_id' in request.args and team_id is None:
        raise ExplanationRouteError(
            reason_code='invalid_request_parameter',
            summary='Team Operations readiness explanation requires team_id to be an integer when supplied.',
            limitation_type='insufficient_context',
            status_code=400,
        )

    team_abbreviation = request.args.get('team_abbreviation')
    sync_status = team_operations_api._sync_status_payload()
    reference_date = _availability_reference_date(sync_status)

    try:
        rows = tuple(
            latest_fatigue_rows(
                team_id=team_id,
                limit=EXPLANATION_DEFAULT_LIMIT,
            )
        )
        records = tuple(
            team_operations_api._filter_records_by_team_abbreviation(
                classify_latest_fatigue_rows(
                    rows,
                    reference_date=reference_date,
                    mode=CURRENT_AVAILABILITY_MODE,
                ),
                team_abbreviation=team_abbreviation,
            )
        )
    except Exception as exc:
        raise ExplanationRouteError(
            reason_code='source_input_error',
            summary='Team Operations readiness explanation source inputs could not be assembled safely.',
            limitation_type='insufficient_context',
            status_code=503,
        ) from exc

    generated_at = team_operations_api._generated_at(rows)
    if not records:
        raise ExplanationRouteError(
            reason_code='missing_source_data',
            summary='Team Operations readiness explanation cannot be generated because source records are unavailable.',
            limitation_type='missing_data',
            status_code=503,
        )

    payload = assemble_bullpen_readiness(
        team=team_operations_api._team_payload_from_records(
            records,
            team_id=team_id,
            team_abbreviation=team_abbreviation,
        ),
        pitcher_records=tuple(
            team_operations_api._readiness_record(record)
            for record in records
        ),
        trust_metadata=team_operations_api._team_operations_trust_metadata(
            records,
            sync_status=sync_status,
            generated_at=generated_at,
        ),
        freshness=team_operations_api._team_operations_freshness_metadata(
            records,
            sync_status=sync_status,
            generated_at=generated_at,
        ),
        generated_at=generated_at,
    )
    if payload.get('contract_state') == 'refused':
        raise ExplanationRouteError(
            reason_code=str(
                (payload.get('refusal') or {}).get('reason')
                or 'source_payload_refused'
            ),
            summary='Team Operations readiness explanation source payload failed closed.',
            limitation_type='missing_data',
            status_code=503,
        )
    return payload


def _sync_status_payload():
    try:
        return sync_metadata.build_sync_status_payload()
    except Exception:
        return {
            'status': sync_metadata.STATUS_METADATA_UNAVAILABLE,
            'sync_authority': 'sync_runs',
            'metadata_source': 'none',
            'last_sync': None,
            'last_successful_sync': None,
            'finished_at': None,
            'data': {
                'game_logs': None,
                'latest_game_date': None,
                'latest_workload_date': None,
                'latest_fatigue_calculated_at': None,
            },
            'availability_reference_date': None,
            'freshness': {
                'is_current': False,
                'is_stale': False,
                'freshness_state': 'metadata_unavailable',
                'data_age_days': None,
                'reference_date': None,
                'availability_reference_date': None,
                'reason_codes': ['durable_sync_metadata_unavailable'],
                'label': 'Sync metadata unavailable.',
                'limitations': ['Could not read sync status metadata.'],
            },
        }


def _availability_reference_date(sync_status):
    return (
        product_availability_reference_date_from_sync_status(sync_status)
        or product_current_date()
    )


def _query_error(args, *, allowed_fields: frozenset[str]) -> ExplanationRouteError | None:
    for key in args.keys():
        normalized_key = str(key).lower()
        if normalized_key not in allowed_fields:
            reason = (
                'forbidden_request_parameter'
                if _contains_prohibited_query_intent(normalized_key)
                else 'unsupported_request_parameter'
            )
            return ExplanationRouteError(
                reason_code=reason,
                summary='Explanation output is refused because request parameters are not supported for this route.',
                limitation_type='insufficient_context',
                status_code=400,
            )

        for value in args.getlist(key):
            if _contains_prohibited_query_intent(str(value).lower()):
                return ExplanationRouteError(
                    reason_code='forbidden_request_parameter',
                    summary='Explanation output is refused because request parameters are not supported for this route.',
                    limitation_type='insufficient_context',
                    status_code=400,
                )
    return None


def _contains_prohibited_query_intent(value: str) -> bool:
    return any(token in value for token in PROHIBITED_QUERY_TOKENS)


def _success_envelope(
    explanation_type: str,
    explanation: Mapping[str, Any],
) -> dict[str, Any]:
    governance = dict(explanation.get('governance') or _governance_payload())
    envelope = {
        'status': 'ok',
        'explanation_type': explanation_type,
        'certification_status': EXPLANATION_CERTIFICATION_STATUS,
        'route_status': EXPLANATION_ROUTE_STATUS,
        'explanation': dict(explanation),
        'governance': governance,
    }
    require_v4_governance_safe(envelope)
    return envelope


def _fail_closed_response(
    *,
    explanation_type: str,
    reason_code: str,
    summary: str,
    limitation_type: str,
    status_code: int,
):
    payload = _fail_closed_envelope(
        explanation_type=explanation_type,
        reason_code=reason_code,
        summary=summary,
        limitation_type=limitation_type,
    )
    return jsonify(payload), status_code


def _fail_closed_envelope(
    *,
    explanation_type: str,
    reason_code: str,
    summary: str,
    limitation_type: str,
) -> dict[str, Any]:
    payload = {
        'status': 'unavailable',
        'explanation_type': explanation_type,
        'certification_status': EXPLANATION_CERTIFICATION_STATUS
        if explanation_type in CERTIFIED_EXPLANATION_TYPES
        else 'uncertified',
        'route_status': EXPLANATION_ROUTE_STATUS,
        'explanation': None,
        'limitations': [
            {
                'limitation_type': limitation_type,
                'label': _limitation_label(limitation_type),
                'summary': summary,
            }
        ],
        'refusal': {
            'refused': True,
            'reason_code': reason_code,
            'summary': summary,
        },
        'governance': _governance_payload(),
    }
    require_v4_governance_safe(payload)
    return payload


def _governance_payload() -> dict[str, Any]:
    return V4GovernancePayload().to_dict()


def _limitation_label(limitation_type: str) -> str:
    labels = {
        'missing_data': 'Required explanation inputs are unavailable',
        'stale_data': 'Required explanation inputs are stale',
        'partial_coverage': 'Required explanation inputs have partial coverage',
        'uncertified_source': 'Requested explanation scope is unavailable',
        'limited_confidence': 'Explanation confidence is limited',
        'insufficient_context': 'Explanation context is insufficient',
    }
    return labels.get(limitation_type, 'Explanation unavailable')


def _iso_timestamp(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat()
    if value is not None:
        return str(value)
    return None
