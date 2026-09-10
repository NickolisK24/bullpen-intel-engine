"""Canonical source identity, immutable observation, and fetch-attempt service.

The source layer records what an external provider returned and whether the
material source content changed. It deliberately does not mutate canonical
baseball facts, calculate impact, retry jobs, or publish.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from sqlalchemy.exc import IntegrityError

from models.source_observation import (
    SourceFetchAttempt,
    SourceObservation,
    SourcePayloadArtifact,
    SourceSubject,
)
from services.sync_control_plane import SourceDomain
from utils.db import db
from utils.time import utc_now_naive


FINGERPRINT_ALGORITHM = 'sha256'
FINGERPRINT_VERSION = 'source-json-sha256-v1'
REQUEST_IDENTITY_VERSION = 'request-json-sha256-v1'


class _ValueEnum(str, Enum):
    def __str__(self):
        return self.value


class SourceProvider(_ValueEnum):
    MLB_STATS_API = 'mlb_stats_api'
    BASEBALL_SAVANT = 'baseball_savant'


class SourceSubjectType(_ValueEnum):
    LEAGUE = 'league'
    BASEBALL_DATE = 'baseball_date'
    DATE_RANGE = 'date_range'
    GAME = 'game'
    TEAM = 'team'
    PLAYER = 'player'
    PITCHER = 'pitcher'
    SOURCE_QUERY = 'source_query'


class ObservationCompleteness(_ValueEnum):
    COMPLETE = 'complete'
    PARTIAL = 'partial'
    UNKNOWN = 'unknown'
    FAILED = 'failed'


class ObservationOutcome(_ValueEnum):
    NEW = 'new'
    UNCHANGED = 'unchanged'
    CHANGED = 'changed'
    CORRECTED = 'corrected'
    PARTIAL = 'partial'
    EMPTY_VALID = 'empty_valid'
    FAILED = 'failed'


class PayloadKind(_ValueEnum):
    RAW_JSON = 'raw_json'
    NORMALIZED_JSON = 'normalized_json'


@dataclass(frozen=True)
class SourceIdentity:
    identity_key: str
    provider: str
    source_domain: str
    endpoint: str
    subject_type: str
    subject_key: str
    request_identity: str
    request_schema_version: int
    request_parameters: dict
    baseball_date: date | None
    range_start: date | None
    range_end: date | None


@dataclass(frozen=True)
class SourceObservationResult:
    subject: SourceSubject
    observation: SourceObservation | None
    fetch_attempt: SourceFetchAttempt
    outcome: str
    changed: bool
    created: bool


def stable_json_value(value: Any) -> Any:
    """Return a deterministic JSON-safe value without reordering sequences."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        normalized = value
        if normalized.tzinfo is not None:
            normalized = normalized.astimezone(timezone.utc).replace(tzinfo=None)
        return normalized.isoformat(timespec='microseconds')
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): stable_json_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [stable_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [stable_json_value(item) for item in value]
        return sorted(normalized, key=stable_json_dumps)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f'Unsupported JSON value type: {type(value).__name__}')


def stable_json_dumps(value: Any) -> str:
    return json.dumps(
        stable_json_value(value),
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_record_collection(records) -> list:
    """Normalize an order-insensitive endpoint record collection."""
    normalized = [stable_json_value(record) for record in (records or [])]
    return sorted(normalized, key=stable_json_dumps)


def source_fingerprint(payload: Any, *, version=FINGERPRINT_VERSION) -> str:
    if _text(version, 'fingerprint_version') != FINGERPRINT_VERSION:
        raise ValueError(f'Unsupported fingerprint version {version!r}')
    return _sha256(stable_json_dumps(payload))


def build_source_identity(
    *,
    provider,
    source_domain,
    endpoint,
    subject_type,
    subject_key,
    request_parameters=None,
    request_schema_version=1,
    baseball_date=None,
    range_start=None,
    range_end=None,
) -> SourceIdentity:
    provider_value = _enum_value(provider, SourceProvider)
    domain_value = _enum_value(source_domain, SourceDomain)
    subject_type_value = _enum_value(subject_type, SourceSubjectType)
    endpoint_value = _text(endpoint, 'endpoint')
    subject_key_value = _text(subject_key, 'subject_key')
    request_schema_version = _positive_int(
        request_schema_version, 'request_schema_version'
    )
    parameters = stable_json_value(request_parameters or {})
    if not isinstance(parameters, dict):
        raise ValueError('request_parameters must be an object')
    baseball_date = _date_value(baseball_date, 'baseball_date')
    range_start = _date_value(range_start, 'range_start')
    range_end = _date_value(range_end, 'range_end')
    if range_start is not None and range_end is not None and range_start > range_end:
        raise ValueError('range_start must not be after range_end')

    request_identity = _sha256(stable_json_dumps({
        'version': REQUEST_IDENTITY_VERSION,
        'schema_version': request_schema_version,
        'parameters': parameters,
    }))
    identity_key = _sha256(stable_json_dumps({
        'provider': provider_value,
        'source_domain': domain_value,
        'endpoint': endpoint_value,
        'subject_type': subject_type_value,
        'subject_key': subject_key_value,
        'request_identity': request_identity,
        'baseball_date': baseball_date,
        'range_start': range_start,
        'range_end': range_end,
    }))
    return SourceIdentity(
        identity_key=identity_key,
        provider=provider_value,
        source_domain=domain_value,
        endpoint=endpoint_value,
        subject_type=subject_type_value,
        subject_key=subject_key_value,
        request_identity=request_identity,
        request_schema_version=request_schema_version,
        request_parameters=parameters,
        baseball_date=baseball_date,
        range_start=range_start,
        range_end=range_end,
    )


def record_source_observation(
    *,
    identity: SourceIdentity,
    payload,
    fingerprint_payload=None,
    completeness=ObservationCompleteness.COMPLETE,
    payload_schema_version=1,
    payload_kind=PayloadKind.NORMALIZED_JSON,
    retain_payload=True,
    record_count=None,
    empty_valid=False,
    correction=False,
    source_updated_at=None,
    source_revision=None,
    source_etag=None,
    observed_at=None,
    sync_run_id=None,
    sync_job_id=None,
    attempt_started_at=None,
    http_status=200,
    http_retry_count=0,
    duration_ms=None,
    response_bytes=None,
    fingerprint_version=FINGERPRINT_VERSION,
    commit=True,
) -> SourceObservationResult:
    """Record one complete/partial source result without duplicating a replay."""
    if not isinstance(identity, SourceIdentity):
        raise ValueError('identity must be a SourceIdentity')
    completeness_value = _enum_value(completeness, ObservationCompleteness)
    if completeness_value == ObservationCompleteness.FAILED.value:
        raise ValueError('failed fetches must use record_source_fetch_failure')
    payload_schema_version = _positive_int(
        payload_schema_version, 'payload_schema_version'
    )
    payload_kind_value = _enum_value(payload_kind, PayloadKind)
    record_count = _nonnegative_int(record_count, 'record_count', nullable=True)
    http_retry_count = _nonnegative_int(http_retry_count, 'http_retry_count')
    duration_ms = _nonnegative_int(duration_ms, 'duration_ms', nullable=True)
    response_bytes = _nonnegative_int(
        response_bytes, 'response_bytes', nullable=True
    )
    if empty_valid and (
        completeness_value != ObservationCompleteness.COMPLETE.value
        or record_count != 0
    ):
        raise ValueError('empty_valid requires complete evidence and record_count=0')

    normalized_payload = stable_json_value(payload)
    material_payload = (
        normalized_payload
        if fingerprint_payload is None
        else stable_json_value(fingerprint_payload)
    )
    fingerprint = source_fingerprint(
        material_payload, version=fingerprint_version
    )
    observed_at = _datetime_value(observed_at or utc_now_naive(), 'observed_at')
    source_updated_at = _datetime_value(
        source_updated_at, 'source_updated_at', nullable=True
    )
    attempt_started_at = _datetime_value(
        attempt_started_at or observed_at, 'attempt_started_at'
    )
    if duration_ms is None:
        duration_ms = max(
            0, int((observed_at - attempt_started_at).total_seconds() * 1000)
        )
    encoded_payload = stable_json_dumps(normalized_payload).encode('utf-8')
    if response_bytes is None:
        response_bytes = len(encoded_payload)

    subject = _locked_subject(identity)
    previous = latest_authoritative_observation(subject, lock=False)

    if (
        completeness_value == ObservationCompleteness.COMPLETE.value
        and previous is not None
        and previous.fingerprint_version == fingerprint_version
        and previous.fingerprint == fingerprint
    ):
        attempt = _fetch_attempt(
            subject=subject,
            observation=previous,
            status='succeeded',
            outcome=ObservationOutcome.UNCHANGED.value,
            completeness=completeness_value,
            started_at=attempt_started_at,
            completed_at=observed_at,
            http_status=http_status,
            http_retry_count=http_retry_count,
            duration_ms=duration_ms,
            response_bytes=response_bytes,
            record_count=record_count,
            sync_run_id=sync_run_id,
            sync_job_id=sync_job_id,
        )
        _finish(commit)
        return SourceObservationResult(
            subject, previous, attempt, ObservationOutcome.UNCHANGED.value,
            False, False,
        )

    if completeness_value != ObservationCompleteness.COMPLETE.value:
        existing = _matching_non_authoritative(
            subject=subject,
            predecessor=previous,
            fingerprint=fingerprint,
            fingerprint_version=fingerprint_version,
            completeness=completeness_value,
        )
        if existing is not None:
            attempt = _fetch_attempt(
                subject=subject,
                observation=existing,
                status='partial',
                outcome=ObservationOutcome.PARTIAL.value,
                completeness=completeness_value,
                started_at=attempt_started_at,
                completed_at=observed_at,
                http_status=http_status,
                http_retry_count=http_retry_count,
                duration_ms=duration_ms,
                response_bytes=response_bytes,
                record_count=record_count,
                sync_run_id=sync_run_id,
                sync_job_id=sync_job_id,
            )
            _finish(commit)
            return SourceObservationResult(
                subject, existing, attempt, ObservationOutcome.PARTIAL.value,
                False, False,
            )

    version_number = _next_version(subject)
    if completeness_value != ObservationCompleteness.COMPLETE.value:
        outcome = ObservationOutcome.PARTIAL.value
        is_authoritative = False
        changed = False
    elif empty_valid:
        outcome = ObservationOutcome.EMPTY_VALID.value
        is_authoritative = True
        changed = previous is None or previous.fingerprint != fingerprint
    elif previous is None:
        outcome = ObservationOutcome.NEW.value
        is_authoritative = True
        changed = True
    elif correction:
        outcome = ObservationOutcome.CORRECTED.value
        is_authoritative = True
        changed = True
    else:
        outcome = ObservationOutcome.CHANGED.value
        is_authoritative = True
        changed = True

    predecessor_id = previous.id if previous is not None else None
    dedupe_key = _observation_dedupe_key(
        subject.id,
        predecessor_id,
        fingerprint,
        fingerprint_version,
        completeness_value,
        is_authoritative,
    )
    existing = SourceObservation.query.filter_by(dedupe_key=dedupe_key).one_or_none()
    created = existing is None
    if created:
        artifact = (
            _payload_artifact(
                normalized_payload,
                payload_schema_version=payload_schema_version,
                payload_kind=payload_kind_value,
                encoded_payload=encoded_payload,
            )
            if retain_payload else None
        )
        try:
            with db.session.begin_nested():
                observation = SourceObservation(
                    source_subject_id=subject.id,
                    version_number=version_number,
                    dedupe_key=dedupe_key,
                    fingerprint=fingerprint,
                    fingerprint_algorithm=FINGERPRINT_ALGORITHM,
                    fingerprint_version=fingerprint_version,
                    payload_schema_version=payload_schema_version,
                    payload_artifact_id=artifact.id if artifact is not None else None,
                    completeness=completeness_value,
                    outcome=outcome,
                    is_change=changed,
                    is_authoritative=is_authoritative,
                    record_count=record_count,
                    source_updated_at=source_updated_at,
                    source_revision=_optional_text(source_revision),
                    source_etag=_optional_text(source_etag),
                    predecessor_observation_id=predecessor_id,
                    sync_run_id=sync_run_id,
                    sync_job_id=sync_job_id,
                    observed_at=observed_at,
                )
                db.session.add(observation)
                db.session.flush()
        except IntegrityError:
            # The subject row lock serializes PostgreSQL writers. This fallback
            # also resolves a database-enforced duplicate when a caller uses a
            # transaction/isolation arrangement that observed the same parent.
            subject = _locked_subject(identity)
            observation = SourceObservation.query.filter_by(
                dedupe_key=dedupe_key
            ).one()
            created = False
            changed = False
            outcome = ObservationOutcome.UNCHANGED.value
    else:
        observation = existing
        changed = False
        outcome = ObservationOutcome.UNCHANGED.value

    attempt_status = (
        'partial'
        if completeness_value != ObservationCompleteness.COMPLETE.value
        else 'succeeded'
    )
    attempt = _fetch_attempt(
        subject=subject,
        observation=observation,
        status=attempt_status,
        outcome=outcome,
        completeness=completeness_value,
        started_at=attempt_started_at,
        completed_at=observed_at,
        http_status=http_status,
        http_retry_count=http_retry_count,
        duration_ms=duration_ms,
        response_bytes=response_bytes,
        record_count=record_count,
        sync_run_id=sync_run_id,
        sync_job_id=sync_job_id,
    )
    _finish(commit)
    return SourceObservationResult(
        subject, observation, attempt, outcome, changed, created
    )


def record_source_fetch_failure(
    *,
    identity: SourceIdentity,
    error,
    observed_at=None,
    attempt_started_at=None,
    http_status=None,
    http_retry_count=0,
    duration_ms=None,
    sync_run_id=None,
    sync_job_id=None,
    commit=True,
) -> SourceObservationResult:
    """Record a failed external request without creating/superseding content."""
    if not isinstance(identity, SourceIdentity):
        raise ValueError('identity must be a SourceIdentity')
    completed_at = _datetime_value(observed_at or utc_now_naive(), 'observed_at')
    started_at = _datetime_value(
        attempt_started_at or completed_at, 'attempt_started_at'
    )
    if duration_ms is None:
        duration_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))
    subject = _locked_subject(identity)
    attempt = _fetch_attempt(
        subject=subject,
        observation=None,
        status='failed',
        outcome=ObservationOutcome.FAILED.value,
        completeness=ObservationCompleteness.FAILED.value,
        started_at=started_at,
        completed_at=completed_at,
        http_status=http_status,
        http_retry_count=_nonnegative_int(http_retry_count, 'http_retry_count'),
        duration_ms=_nonnegative_int(duration_ms, 'duration_ms'),
        response_bytes=None,
        record_count=None,
        sync_run_id=sync_run_id,
        sync_job_id=sync_job_id,
        error_class=type(error).__name__ if isinstance(error, BaseException) else 'source',
        error_message=str(error),
    )
    _finish(commit)
    return SourceObservationResult(
        subject, None, attempt, ObservationOutcome.FAILED.value, False, False
    )


def latest_authoritative_observation(subject_or_id, *, lock=False):
    subject_id = (
        subject_or_id.id
        if isinstance(subject_or_id, SourceSubject)
        else int(subject_or_id)
    )
    query = (
        SourceObservation.query
        .filter_by(source_subject_id=subject_id, is_authoritative=True)
        .order_by(SourceObservation.version_number.desc())
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def _locked_subject(identity):
    subject = SourceSubject.query.filter_by(
        identity_key=identity.identity_key
    ).one_or_none()
    if subject is None:
        try:
            with db.session.begin_nested():
                subject = SourceSubject(
                    identity_key=identity.identity_key,
                    provider=identity.provider,
                    source_domain=identity.source_domain,
                    endpoint=identity.endpoint,
                    subject_type=identity.subject_type,
                    subject_key=identity.subject_key,
                    request_identity=identity.request_identity,
                    request_schema_version=identity.request_schema_version,
                    request_parameters=identity.request_parameters,
                    baseball_date=identity.baseball_date,
                    range_start=identity.range_start,
                    range_end=identity.range_end,
                )
                db.session.add(subject)
                db.session.flush()
        except IntegrityError:
            subject = SourceSubject.query.filter_by(
                identity_key=identity.identity_key
            ).one()
    return (
        SourceSubject.query
        .filter_by(id=subject.id)
        .with_for_update()
        .one()
    )


def _payload_artifact(
    payload,
    *,
    payload_schema_version,
    payload_kind,
    encoded_payload,
):
    content_hash = _sha256(encoded_payload)
    filters = {
        'content_hash': content_hash,
        'payload_schema_version': payload_schema_version,
        'payload_kind': payload_kind,
    }
    artifact = SourcePayloadArtifact.query.filter_by(**filters).one_or_none()
    if artifact is not None:
        return artifact
    try:
        with db.session.begin_nested():
            artifact = SourcePayloadArtifact(
                **filters,
                hash_algorithm=FINGERPRINT_ALGORITHM,
                storage_format='json',
                payload_json=payload,
                payload_bytes=len(encoded_payload),
            )
            db.session.add(artifact)
            db.session.flush()
    except IntegrityError:
        artifact = SourcePayloadArtifact.query.filter_by(**filters).one()
    return artifact


def _matching_non_authoritative(
    *, subject, predecessor, fingerprint, fingerprint_version, completeness,
):
    predecessor_id = predecessor.id if predecessor is not None else None
    query = SourceObservation.query.filter_by(
        source_subject_id=subject.id,
        predecessor_observation_id=predecessor_id,
        fingerprint=fingerprint,
        fingerprint_version=fingerprint_version,
        completeness=completeness,
        is_authoritative=False,
    )
    return query.order_by(SourceObservation.version_number.desc()).first()


def _next_version(subject):
    latest = (
        SourceObservation.query
        .filter_by(source_subject_id=subject.id)
        .order_by(SourceObservation.version_number.desc())
        .first()
    )
    return (latest.version_number if latest is not None else 0) + 1


def _observation_dedupe_key(
    subject_id, predecessor_id, fingerprint, fingerprint_version,
    completeness, is_authoritative,
):
    return _sha256(stable_json_dumps({
        'subject_id': subject_id,
        'predecessor_id': predecessor_id,
        'fingerprint': fingerprint,
        'fingerprint_version': fingerprint_version,
        'completeness': completeness,
        'is_authoritative': is_authoritative,
    }))


def _fetch_attempt(
    *,
    subject,
    observation,
    status,
    outcome,
    completeness,
    started_at,
    completed_at,
    http_status,
    http_retry_count,
    duration_ms,
    response_bytes,
    record_count,
    sync_run_id,
    sync_job_id,
    error_class=None,
    error_message=None,
):
    attempt = SourceFetchAttempt(
        source_subject_id=subject.id,
        source_observation_id=(observation.id if observation is not None else None),
        sync_run_id=sync_run_id,
        sync_job_id=sync_job_id,
        status=status,
        outcome=outcome,
        completeness=completeness,
        started_at=started_at,
        completed_at=completed_at,
        http_status=http_status,
        http_retry_count=http_retry_count,
        duration_ms=duration_ms,
        response_bytes=response_bytes,
        record_count=record_count,
        error_class=error_class,
        error_message=error_message,
    )
    db.session.add(attempt)
    db.session.flush()
    return attempt


def _enum_value(value, enum_type):
    raw = value.value if isinstance(value, enum_type) else str(value)
    try:
        return enum_type(raw).value
    except ValueError as exc:
        allowed = ', '.join(item.value for item in enum_type)
        raise ValueError(
            f'Unsupported {enum_type.__name__} {raw!r}; expected one of: {allowed}'
        ) from exc


def _text(value, field):
    text = str(value).strip() if value is not None else ''
    if not text:
        raise ValueError(f'{field} must be non-empty')
    return text


def _optional_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_int(value, field):
    if isinstance(value, bool):
        raise ValueError(f'{field} must be a positive integer')
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field} must be a positive integer') from exc
    if result <= 0:
        raise ValueError(f'{field} must be a positive integer')
    return result


def _nonnegative_int(value, field, *, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        raise ValueError(f'{field} must be a non-negative integer')
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field} must be a non-negative integer') from exc
    if result < 0:
        raise ValueError(f'{field} must be a non-negative integer')
    return result


def _date_value(value, field):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field} must be an ISO date') from exc


def _datetime_value(value, field, *, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, datetime):
        raise ValueError(f'{field} must be a datetime')
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _sha256(value):
    raw = value if isinstance(value, bytes) else str(value).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _finish(commit):
    if commit:
        db.session.commit()
    else:
        db.session.flush()
