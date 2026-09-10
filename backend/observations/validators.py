"""Validation helpers for governed V5 observation contracts."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Mapping

from observations.enums import (
    ALLOWED_OBSERVATION_FAMILIES,
    ALLOWED_OBSERVATION_SEVERITIES,
    ALLOWED_OBSERVATION_TRUST_STATUSES,
    ALLOWED_OBSERVATION_TYPES,
)


NO_RANKING_APPLIED = False
NO_SELECTION_MADE = False

REQUIRED_OBSERVATION_FIELDS = frozenset(
    {
        'observation_id',
        'observation_type',
        'family',
        'severity',
        'title',
        'summary',
        'evidence',
        'freshness',
        'confidence',
        'trust_status',
        'ranking_applied',
        'selection_made',
    }
)

ALLOWED_GOVERNANCE_FIELD_NAMES = frozenset(
    {
        'ranking_applied',
        'selection_made',
    }
)

FORBIDDEN_OBSERVATION_FIELD_NAMES = frozenset(
    {
        'rank',
        'ranking',
        'winner',
        'priority',
        'priority_score',
        'score_ordering',
        'selected_pitcher',
        'selected_pitcher_id',
        'selected_candidate',
        'selected_candidate_id',
        'recommended_pitcher',
        'recommended_pitcher_id',
        'recommended_option',
        'preferred_pitcher',
        'preferred_option',
        'use_this_pitcher',
        'best_arm',
        'best_candidate',
        'best_pitcher',
        'top_candidate',
        'top_option',
        'pitcher_choice',
        'matchup',
        'matchup_advice',
        'matchup_advantage',
        'prediction',
        'predicted_performance',
        'performance_prediction',
        'performance_forecast',
        'predicted_injury',
        'injury_prediction',
        'predicted_saves',
        'save_prediction',
        'game_prediction',
        'game_outcome_prediction',
        'outcome_prediction',
        'projected_outcome',
        'projected_performance',
        'hidden_priority_ordering',
    }
)

PROHIBITED_LANGUAGE_PATTERNS = (
    (re.compile(r'\buse\b', re.IGNORECASE), 'use'),
    (re.compile(r'\bbest\b', re.IGNORECASE), 'best'),
    (re.compile(r'\bpreferred\b', re.IGNORECASE), 'preferred'),
    (re.compile(r'\bshould\s+close\b', re.IGNORECASE), 'should close'),
    (re.compile(r'\bmanager\s+should\b', re.IGNORECASE), 'manager should'),
    (re.compile(r'\brecommend\w*\b', re.IGNORECASE), 'recommend'),
    (re.compile(r'\bpick\b', re.IGNORECASE), 'pick'),
    (re.compile(r'\bchoose\b', re.IGNORECASE), 'choose'),
    (re.compile(r'\bstart\s+him\b', re.IGNORECASE), 'start him'),
    (re.compile(r'\bsit\s+him\b', re.IGNORECASE), 'sit him'),
    (
        re.compile(r'\bmatchup\s+advantage\b', re.IGNORECASE),
        'matchup advantage',
    ),
)


def required_text(value: str | None, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field_name} is required.')
    return value


def enum_value(value: str | Enum, allowed: frozenset[str], field_name: str) -> str:
    raw_value = value.value if isinstance(value, Enum) else value
    if raw_value not in allowed:
        raise ValueError(f'{field_name} uses unsupported vocabulary.')
    return str(raw_value)


def validate_observation_type(value: str | Enum) -> str:
    return enum_value(value, ALLOWED_OBSERVATION_TYPES, 'observation_type')


def validate_observation_family(value: str | Enum) -> str:
    return enum_value(value, ALLOWED_OBSERVATION_FAMILIES, 'family')


def validate_observation_severity(value: str | Enum) -> str:
    return enum_value(value, ALLOWED_OBSERVATION_SEVERITIES, 'severity')


def validate_observation_trust_status(value: str | Enum) -> str:
    return enum_value(value, ALLOWED_OBSERVATION_TRUST_STATUSES, 'trust_status')


def prohibited_language_errors(text: str | None, path: str) -> list[str]:
    if not isinstance(text, str):
        return [f'{path} is required.']

    errors: list[str] = []
    for pattern, label in PROHIBITED_LANGUAGE_PATTERNS:
        if pattern.search(text):
            errors.append(f'{path} contains prohibited language: {label}.')
    return errors


def _field_name_is_forbidden(field_name: str) -> bool:
    normalized = field_name.lower()
    if normalized in ALLOWED_GOVERNANCE_FIELD_NAMES:
        return False
    return normalized in FORBIDDEN_OBSERVATION_FIELD_NAMES


def observation_governance_errors(
    payload: Any,
    path: str = 'payload',
) -> list[str]:
    """Return unsafe V5 observation field names or governance values."""

    errors: list[str] = []

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            key_path = f'{path}.{key_text}'
            if _field_name_is_forbidden(key_text):
                errors.append(f'{key_path} uses a forbidden V5 observation field name.')
            if key_text == 'ranking_applied' and value is not NO_RANKING_APPLIED:
                errors.append(f'{key_path} must be false.')
            if key_text == 'selection_made' and value is not NO_SELECTION_MADE:
                errors.append(f'{key_path} must be false.')
            errors.extend(observation_governance_errors(value, key_path))
        return errors

    if isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            errors.extend(observation_governance_errors(item, f'{path}[{index}]'))

    return errors


def require_observation_governance_safe(payload: Any) -> None:
    errors = observation_governance_errors(payload)
    if errors:
        raise ValueError(' '.join(errors))


def observation_payload_errors(
    payload: Mapping[str, Any] | None,
    path: str = 'observation',
) -> list[str]:
    errors: list[str] = []

    if not isinstance(payload, Mapping):
        return [f'{path} is missing.']

    missing = sorted(REQUIRED_OBSERVATION_FIELDS.difference(payload.keys()))
    for field_name in missing:
        errors.append(f'{path} is missing required field {field_name}.')

    if payload.get('observation_type') not in ALLOWED_OBSERVATION_TYPES:
        errors.append(f'{path}.observation_type uses unsupported vocabulary.')
    if payload.get('family') not in ALLOWED_OBSERVATION_FAMILIES:
        errors.append(f'{path}.family uses unsupported vocabulary.')
    if payload.get('severity') not in ALLOWED_OBSERVATION_SEVERITIES:
        errors.append(f'{path}.severity uses unsupported vocabulary.')
    if payload.get('trust_status') not in ALLOWED_OBSERVATION_TRUST_STATUSES:
        errors.append(f'{path}.trust_status uses unsupported vocabulary.')

    if not isinstance(payload.get('title'), str) or not payload.get('title', '').strip():
        errors.append(f'{path}.title is required.')
    else:
        errors.extend(prohibited_language_errors(payload.get('title'), f'{path}.title'))

    if not isinstance(payload.get('summary'), str) or not payload.get('summary', '').strip():
        errors.append(f'{path}.summary is required.')
    else:
        errors.extend(
            prohibited_language_errors(payload.get('summary'), f'{path}.summary')
        )

    evidence = payload.get('evidence')
    if not isinstance(evidence, list) or not evidence:
        errors.append(f'{path}.evidence must include at least one item.')

    freshness = payload.get('freshness')
    if not isinstance(freshness, Mapping) or not freshness:
        errors.append(f'{path}.freshness is required.')

    confidence = payload.get('confidence')
    if not isinstance(confidence, Mapping) or not confidence:
        errors.append(f'{path}.confidence is required.')

    if payload.get('ranking_applied') is not NO_RANKING_APPLIED:
        errors.append(f'{path}.ranking_applied must be false.')
    if payload.get('selection_made') is not NO_SELECTION_MADE:
        errors.append(f'{path}.selection_made must be false.')

    errors.extend(observation_governance_errors(payload, path))
    return errors


def require_observation_payload_valid(payload: Mapping[str, Any] | None) -> None:
    errors = observation_payload_errors(payload)
    if errors:
        raise ValueError(' '.join(errors))


def collection_payload_errors(
    payload: Mapping[str, Any] | None,
    path: str = 'collection',
) -> list[str]:
    errors: list[str] = []

    if not isinstance(payload, Mapping):
        return [f'{path} is missing.']

    if not isinstance(payload.get('collection_id'), str) or not payload.get(
        'collection_id',
        '',
    ).strip():
        errors.append(f'{path}.collection_id is required.')

    observations = payload.get('observations')
    if not isinstance(observations, list):
        errors.append(f'{path}.observations must be represented as a list.')
    else:
        for index, observation in enumerate(observations):
            errors.extend(
                observation_payload_errors(
                    observation,
                    f'{path}.observations[{index}]',
                )
            )

    if payload.get('ranking_applied') is not NO_RANKING_APPLIED:
        errors.append(f'{path}.ranking_applied must be false.')
    if payload.get('selection_made') is not NO_SELECTION_MADE:
        errors.append(f'{path}.selection_made must be false.')

    errors.extend(observation_governance_errors(payload, path))
    return errors


def require_collection_payload_valid(payload: Mapping[str, Any] | None) -> None:
    errors = collection_payload_errors(payload)
    if errors:
        raise ValueError(' '.join(errors))
