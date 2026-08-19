"""Prospective, version-aware frozen inputs for future Team Board deltas.

This module does not author change events or reader-facing copy.  It freezes a
small comparison envelope next to each newly published Team State artifact and
later proves whether two such envelopes are semantically compatible.  Existing
dashboard snapshots and Share Artifacts are never modified or backfilled.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import logging
from types import MappingProxyType
from typing import Any, Mapping

from models.dashboard_snapshot import DashboardSnapshot
from services.team_state_public_vocabulary import PUBLIC_TEAM_STATE_CONTRACT
from team_operations import TEAM_STATE_METHOD_VERSION
from utils.db import db
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)

SNAPSHOT_TYPE = 'team_board_delta'
SNAPSHOT_SOURCE_PREFIX = 'tb_delta:team:'
SNAPSHOT_PAYLOAD_VERSION = 1
ENVELOPE_VERSION = 'team_board_delta_envelope_v1'
CAPABILITY = 'team_board_daily_delta_substrate'

COMPARABLE = 'comparable'
PREVIOUS_MISSING = 'previous_missing'
CURRENT_MISSING = 'current_missing'
METHOD_VERSION_MISSING = 'method_version_missing'
METHOD_VERSION_MISMATCH = 'method_version_mismatch'
POPULATION_BASIS_MISSING = 'population_basis_missing'
POPULATION_BASIS_MISMATCH = 'population_basis_mismatch'
CONTRACT_INCOMPATIBLE = 'contract_incompatible'
FRESHNESS_UNTRUSTED = 'freshness_untrusted'
REPRESENTED_DATE_INVALID = 'represented_date_invalid'
SOURCE_IDENTITY_MISSING = 'source_identity_missing'
TEAM_ID_MISMATCH = 'team_id_mismatch'
VALUE_MISSING = 'value_missing'
DOMAIN_NOT_READY = 'domain_not_ready'
DOMAIN_NOT_INCLUDED = 'domain_not_in_substrate'

READINESS_COMPARABLE_WHEN_STAMPED = 'comparable_when_stamped'
READINESS_NOT_YET_COMPARABLE = 'not_yet_comparable'
READINESS_NOT_PART_OF_SUBSTRATE = 'not_part_of_substrate'

# Domain readiness is explicit and deliberately conservative.  Adding a name
# here never makes it comparable: only a dedicated compatibility rule can do
# that.  Role movement remains withheld by the TB-05 governance boundary.
DOMAIN_READINESS = MappingProxyType({
    'team_state': READINESS_COMPARABLE_WHEN_STAMPED,
    'active_arm_count': READINESS_COMPARABLE_WHEN_STAMPED,
    'arm_read': READINESS_NOT_YET_COMPARABLE,
    'rest_status': READINESS_NOT_YET_COMPARABLE,
    'workload_7d': READINESS_NOT_YET_COMPARABLE,
    'workload_14d': READINESS_NOT_YET_COMPARABLE,
    'workload_concentration': READINESS_NOT_YET_COMPARABLE,
    'rotation_impact': READINESS_NOT_YET_COMPARABLE,
    'role_movement': READINESS_NOT_YET_COMPARABLE,
    'roster_transactions': READINESS_NOT_PART_OF_SUBSTRATE,
})


class DeltaStampError(ValueError):
    """A naturally generated read lacked safe prospective stamp inputs."""


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _as_date(value) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _mapping(value) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _artifact_public_state(artifact) -> Mapping[str, Any]:
    payload = _mapping(getattr(artifact, 'payload', None))
    team_state = _mapping(payload.get('team_state'))
    return {
        'public_state': team_state.get('public_state'),
        'public_label': team_state.get('public_label'),
    }


def build_prospective_envelope(*, source, readiness, artifact) -> dict:
    """Build metadata from the exact governed read frozen by ``artifact``.

    No classifier or historical service is called.  The method stamp is read
    from the canonical Team State evidence vector and must agree with the one
    canonical owner imported from ``team_operations``; disagreement fails
    closed instead of recording a second method identity.
    """
    readiness = _mapping(readiness)
    evidence = _mapping(readiness.get('team_state_evidence'))
    evidence_references = _mapping(evidence.get('evidence_references'))
    snapshot = getattr(source, 'snapshot', None)
    represented_date = getattr(snapshot, 'data_through', None)
    method_version = evidence.get('method_version')

    if method_version != TEAM_STATE_METHOD_VERSION:
        raise DeltaStampError('team_state_method_version_unproven')
    if not isinstance(represented_date, date):
        raise DeltaStampError('represented_date_missing')
    if getattr(snapshot, 'snapshot_id', None) is None:
        raise DeltaStampError('source_snapshot_identity_missing')
    if getattr(artifact, 'id', None) is None:
        raise DeltaStampError('source_artifact_identity_missing')
    if getattr(artifact, 'lifecycle_state', None) != 'published':
        raise DeltaStampError('source_artifact_not_published')

    population_basis = {
        'basis': evidence.get('basis'),
        'population_authority': evidence_references.get('population_authority'),
        'membership_authority': evidence_references.get('membership_authority'),
    }
    if any(value in (None, '') for value in population_basis.values()):
        raise DeltaStampError('team_state_population_basis_unproven')

    state = _artifact_public_state(artifact)
    if state.get('public_state') in (None, ''):
        raise DeltaStampError('team_state_value_missing')

    contract_version = readiness.get('contract_version')
    if contract_version in (None, ''):
        raise DeltaStampError('team_state_contract_version_missing')

    source_authority = (
        getattr(snapshot, 'subject_type', None) or 'dashboard_snapshot'
    )
    trusted = bool(
        getattr(snapshot, 'is_trusted', False)
        and getattr(artifact, 'published_at', None) is not None
        and readiness.get('contract_state') in {'available', 'degraded'}
    )

    domain_metadata = {
        'method_version': method_version,
        'contract_version': contract_version,
        'public_contract_version': PUBLIC_TEAM_STATE_CONTRACT,
        'population_basis': population_basis,
        'trust_state': evidence.get('trust_state'),
        'trust_data_state': evidence.get('trust_data_state'),
        'freshness_state': evidence.get('freshness_state'),
        'trusted': trusted,
    }
    return {
        'capability': CAPABILITY,
        'envelope_version': ENVELOPE_VERSION,
        'team_id': int(getattr(source, 'team_id')),
        'represented_date': represented_date.isoformat(),
        'source': {
            'frozen_value_source': 'team_state_share_artifact',
            'artifact_id': artifact.id,
            'artifact_payload_version': getattr(artifact, 'render_version', None),
            'snapshot_authority': source_authority,
            'snapshot_id': snapshot.snapshot_id,
            'sync_run_id': snapshot.sync_run_id,
            'subject_key': getattr(snapshot, 'subject_key', None),
        },
        'domains': {
            'team_state': deepcopy(domain_metadata),
            'active_arm_count': deepcopy(domain_metadata),
        },
        'values': {
            'team_state': state,
            # Null stays null.  It is never normalized to zero.
            'active_arm_count': evidence.get('active_pitcher_count'),
        },
    }


def stamp_prospective_snapshot(*, source, readiness, artifact, session=None):
    """Stage one append-only sidecar for a newly published Team State artifact."""
    session = session or db.session
    envelope = build_prospective_envelope(
        source=source,
        readiness=readiness,
        artifact=artifact,
    )
    represented_date = _as_date(envelope.get('represented_date'))
    row = DashboardSnapshot(
        snapshot_type=SNAPSHOT_TYPE,
        sync_run_id=(envelope.get('source') or {}).get('sync_run_id'),
        status='ready',
        is_published=False,
        # Durable proof that the sidecar was captured from a publication that
        # completed its immutable lifecycle transition.
        published_at=getattr(artifact, 'published_at', None),
        payload=deepcopy(envelope),
        payload_version=SNAPSHOT_PAYLOAD_VERSION,
        data_through=represented_date,
        availability_reference_date=None,
        snapshot_generated_at=utc_now_naive(),
        source=f'{SNAPSHOT_SOURCE_PREFIX}{envelope["team_id"]}',
    )
    session.add(row)
    session.flush()
    return row


def try_stamp_prospective_snapshot(*, source, readiness, artifact, session=None):
    """Capture a sidecar without making Share Artifact publication depend on it.

    The nested transaction confines any capture problem to this observational
    substrate.  Publication remains authoritative and succeeds; a missing row
    simply makes that date incomparable, which is the required fail-closed
    behavior.
    """
    session = session or db.session
    try:
        with session.begin_nested():
            return stamp_prospective_snapshot(
                source=source,
                readiness=readiness,
                artifact=artifact,
                session=session,
            )
    except Exception as exc:  # noqa: BLE001 - optional capture must not block publish
        logger.warning(
            'Team Board delta snapshot capture withheld team_id=%s artifact_id=%s reason=%s.',
            getattr(source, 'team_id', None),
            getattr(artifact, 'id', None),
            type(exc).__name__,
        )
        return None


def get_previous_snapshot(*, team_id, represented_date, session=None):
    """Return the nearest prior frozen team/date sidecar with one bounded query."""
    session = session or db.session
    represented_date = _as_date(represented_date)
    if represented_date is None:
        return None
    return (
        session.query(DashboardSnapshot)
        .filter(DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE)
        .filter(DashboardSnapshot.status == 'ready')
        .filter(DashboardSnapshot.payload_version == SNAPSHOT_PAYLOAD_VERSION)
        .filter(DashboardSnapshot.published_at.isnot(None))
        .filter(DashboardSnapshot.source == f'{SNAPSHOT_SOURCE_PREFIX}{int(team_id)}')
        .filter(DashboardSnapshot.data_through < represented_date)
        .order_by(
            DashboardSnapshot.data_through.desc(),
            DashboardSnapshot.id.desc(),
        )
        .limit(1)
        .one_or_none()
    )


def _payload(snapshot) -> Mapping[str, Any]:
    return _mapping(getattr(snapshot, 'payload', None))


def _domain_metadata(payload, domain) -> Mapping[str, Any]:
    return _mapping(_mapping(payload.get('domains')).get(domain))


def _withheld(domain, reason):
    return {
        'readiness': DOMAIN_READINESS[domain],
        'status': reason,
        'reason_code': reason,
    }


def _compatible_domain(previous, current, domain, value_key):
    if previous is None:
        return _withheld(domain, PREVIOUS_MISSING)
    if current is None:
        return _withheld(domain, CURRENT_MISSING)

    previous_payload = _payload(previous)
    current_payload = _payload(current)
    previous_envelope_version = previous_payload.get('envelope_version')
    current_envelope_version = current_payload.get('envelope_version')
    if (
        previous_envelope_version in (None, '')
        or current_envelope_version in (None, '')
        or previous_envelope_version != current_envelope_version
    ):
        return _withheld(domain, CONTRACT_INCOMPATIBLE)
    previous_team = previous_payload.get('team_id')
    current_team = current_payload.get('team_id')
    if previous_team is None or current_team is None or previous_team != current_team:
        return _withheld(domain, TEAM_ID_MISMATCH)

    previous_date = _as_date(previous_payload.get('represented_date'))
    current_date = _as_date(current_payload.get('represented_date'))
    if previous_date is None or current_date is None or previous_date >= current_date:
        return _withheld(domain, REPRESENTED_DATE_INVALID)

    previous_source = _mapping(previous_payload.get('source'))
    current_source = _mapping(current_payload.get('source'))
    for source in (previous_source, current_source):
        if (
            source.get('artifact_id') is None
            or source.get('snapshot_id') is None
            or source.get('snapshot_authority') in (None, '')
        ):
            return _withheld(domain, SOURCE_IDENTITY_MISSING)

    previous_metadata = _domain_metadata(previous_payload, domain)
    current_metadata = _domain_metadata(current_payload, domain)
    previous_method = previous_metadata.get('method_version')
    current_method = current_metadata.get('method_version')
    if previous_method in (None, '') or current_method in (None, ''):
        return _withheld(domain, METHOD_VERSION_MISSING)
    if previous_method != current_method:
        return _withheld(domain, METHOD_VERSION_MISMATCH)

    contract_fields = ('contract_version', 'public_contract_version')
    if any(
        previous_metadata.get(field) in (None, '')
        or current_metadata.get(field) in (None, '')
        or previous_metadata.get(field) != current_metadata.get(field)
        for field in contract_fields
    ):
        return _withheld(domain, CONTRACT_INCOMPATIBLE)

    previous_population = previous_metadata.get('population_basis')
    current_population = current_metadata.get('population_basis')
    if not isinstance(previous_population, Mapping) or not isinstance(
        current_population, Mapping
    ):
        return _withheld(domain, POPULATION_BASIS_MISSING)
    population_fields = ('basis', 'population_authority', 'membership_authority')
    if any(
        population.get(field) in (None, '')
        for population in (previous_population, current_population)
        for field in population_fields
    ):
        return _withheld(domain, POPULATION_BASIS_MISSING)
    if dict(previous_population) != dict(current_population):
        return _withheld(domain, POPULATION_BASIS_MISMATCH)

    if previous_metadata.get('trusted') is not True or current_metadata.get('trusted') is not True:
        return _withheld(domain, FRESHNESS_UNTRUSTED)

    previous_value = _mapping(previous_payload.get('values')).get(value_key)
    current_value = _mapping(current_payload.get('values')).get(value_key)
    if previous_value is None or current_value is None:
        return _withheld(domain, VALUE_MISSING)
    if domain == 'team_state' and (
        not isinstance(previous_value, Mapping)
        or not isinstance(current_value, Mapping)
        or previous_value.get('public_state') in (None, '')
        or current_value.get('public_state') in (None, '')
    ):
        return _withheld(domain, VALUE_MISSING)

    return {
        'readiness': DOMAIN_READINESS[domain],
        'status': COMPARABLE,
        'reason_code': None,
        'previous': deepcopy(previous_value),
        'current': deepcopy(current_value),
    }


def compare_snapshots(previous, current) -> dict:
    """Return raw values only for domains whose compatibility is proven."""
    previous_payload = _payload(previous)
    current_payload = _payload(current)
    domains = {
        'team_state': _compatible_domain(
            previous, current, 'team_state', 'team_state'
        ),
        'active_arm_count': _compatible_domain(
            previous, current, 'active_arm_count', 'active_arm_count'
        ),
    }
    for domain, readiness in DOMAIN_READINESS.items():
        if domain in domains:
            continue
        reason = (
            DOMAIN_NOT_READY
            if readiness == READINESS_NOT_YET_COMPARABLE
            else DOMAIN_NOT_INCLUDED
        )
        domains[domain] = _withheld(domain, reason)

    return {
        'capability': CAPABILITY,
        'envelope_version': ENVELOPE_VERSION,
        'comparison': {
            'team_id': current_payload.get('team_id') or previous_payload.get('team_id'),
            'from_represented_date': previous_payload.get('represented_date'),
            'to_represented_date': current_payload.get('represented_date'),
            'previous_delta_snapshot_id': getattr(previous, 'id', None),
            'current_delta_snapshot_id': getattr(current, 'id', None),
        },
        'domains': domains,
    }
