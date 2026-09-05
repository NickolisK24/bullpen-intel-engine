"""Dormant D-058 per-team publication authoring and integrity services.

Package 1 authors only from one already-trusted league Dashboard publication.  It
does not serve Team Board, publish from continuous work, or alter share artifacts.
The existing ``TeamProgressivePublication`` checkpoint remains the independent source
for today's Team State Share Artifact path until D-058's later convergence package.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Mapping, Optional

from models.dashboard_snapshot import DashboardSnapshot
from models.team_publication import TeamPublicCurrentPointer, TeamPublicPublication
from models.team_state_publication_proof import TeamStatePublicationProof
from services import dashboard_snapshot as dashboard_snapshot_service
from services.mlb_club_directory import MLB_TEAM_IDS
from services.public_serving_authority import (
    TEAM_BOARD_PACKAGE_CONTRACT,
    TEAM_BOARD_PACKAGE_KEY,
)
from services.snapshot_read_guard import SnapshotReadUnavailable
from services.team_state_vnext_production_proof import (
    CONTRACT as TEAM_STATE_PROOF_CONTRACT,
    SCHEMA_VERSION as TEAM_STATE_PROOF_SCHEMA_VERSION,
)
from utils.db import db
from utils.time import utc_now_naive


AUTHORITY_VERSION = 'per_team_public_read_authority_v1'
PAYLOAD_CONTRACT = 'per_team_publication_package_v1'
PAYLOAD_SCHEMA_VERSION = 1
COHORT_CONTRACT = 'league_dashboard_team_cohort_v1'
TRUSTED_PROOF_VERDICTS = {'PASS', 'PASS_WITH_INCONCLUSIVE'}
EXPECTED_TEAM_IDS = tuple(sorted(int(value) for value in MLB_TEAM_IDS))


class TeamPublicationError(ValueError):
    """Fail-closed Package 1 authoring or integrity error."""


class TeamPublicationConflict(TeamPublicationError):
    """The expected per-team current pointer changed before advancement."""


@dataclass(frozen=True)
class TeamPublicationAuthoringResult:
    source_snapshot_id: int
    source_sync_run_id: int
    cohort_id: str
    teams_expected: int
    packages_created: int
    packages_reused: int
    pointers_advanced: int
    pointers_unchanged: int

    def to_dict(self) -> dict:
        return {
            'event': 'team_publication_bootstrap',
            'status': 'complete',
            'source_snapshot_id': self.source_snapshot_id,
            'source_sync_run_id': self.source_sync_run_id,
            'cohort_id': self.cohort_id,
            'teams_expected': self.teams_expected,
            'packages_created': self.packages_created,
            'packages_reused': self.packages_reused,
            'pointers_advanced': self.pointers_advanced,
            'pointers_unchanged': self.pointers_unchanged,
            'validation_failures': 0,
        }


def canonical_json(value) -> str:
    """Canonical, platform-independent JSON used for identity and digests."""
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TeamPublicationError('team_publication_value_not_canonical_json') from exc


def _digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def _iso(value):
    return value.isoformat() if value is not None else None


def _mapping(value) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _positive_int(value) -> Optional[int]:
    if type(value) is not int or value <= 0:
        return None
    return value


def _team_value(container, team_id):
    values = _mapping(container)
    value = values.get(str(team_id))
    if value is None:
        value = values.get(team_id)
    return deepcopy(value) if isinstance(value, Mapping) else None


def _validate_source_snapshot(snapshot, proof) -> tuple[dict, dict, dict]:
    if snapshot is None:
        raise TeamPublicationError('team_publication_dashboard_missing')
    if (
        snapshot.snapshot_type
        != dashboard_snapshot_service.SNAPSHOT_TYPE_BULLPEN_DASHBOARD
        or snapshot.status != dashboard_snapshot_service.SNAPSHOT_STATUS_READY
        or snapshot.is_published is not True
        or snapshot.published_at is None
        or _positive_int(snapshot.id) is None
        or _positive_int(snapshot.sync_run_id) is None
        or snapshot.data_through is None
        or snapshot.availability_reference_date is None
        or snapshot.snapshot_generated_at is None
        or not dashboard_snapshot_service.payload_version_valid(snapshot)
        or not isinstance(snapshot.payload, Mapping)
    ):
        raise TeamPublicationError('team_publication_dashboard_untrusted')

    frozen = _mapping(snapshot.payload).get(TEAM_BOARD_PACKAGE_KEY)
    frozen = _mapping(frozen)
    board_by_team = _mapping(frozen.get('by_team_id'))
    board_team_ids = _normalized_team_ids(board_by_team)
    if (
        frozen.get('contract') != TEAM_BOARD_PACKAGE_CONTRACT
        or frozen.get('team_count') != len(EXPECTED_TEAM_IDS)
        or board_team_ids != EXPECTED_TEAM_IDS
        or frozen.get('data_through') != _iso(snapshot.data_through)
        or frozen.get('availability_reference_date')
        != _iso(snapshot.availability_reference_date)
    ):
        raise TeamPublicationError('team_publication_dashboard_team_package_invalid')

    if proof is None:
        raise TeamPublicationError('team_publication_proof_missing')
    proof_payload = _mapping(proof.proof)
    proof_teams = proof_payload.get('teams')
    proof_teams = proof_teams if isinstance(proof_teams, list) else []
    proof_by_team = {
        item.get('team_id'): deepcopy(item)
        for item in proof_teams
        if isinstance(item, Mapping) and _positive_int(item.get('team_id')) is not None
    }
    if (
        proof.snapshot_id != snapshot.id
        or proof.sync_run_id != snapshot.sync_run_id
        or proof.data_through != snapshot.data_through
        or proof.overall_verdict not in TRUSTED_PROOF_VERDICTS
        or proof.captured_team_count != len(EXPECTED_TEAM_IDS)
        or tuple(sorted(proof_by_team)) != EXPECTED_TEAM_IDS
        or _mapping(proof_payload.get('publication')).get('dashboard_snapshot_id')
        != snapshot.id
        or _mapping(proof_payload.get('publication')).get('sync_run_id')
        != snapshot.sync_run_id
        or _mapping(proof_payload.get('publication')).get('data_through')
        != _iso(snapshot.data_through)
        or proof_payload.get('contract') != TEAM_STATE_PROOF_CONTRACT
        or proof_payload.get('schema_version') != TEAM_STATE_PROOF_SCHEMA_VERSION
    ):
        raise TeamPublicationError('team_publication_proof_identity_invalid')

    return frozen, board_by_team, proof_by_team


def _validate_team_sources(team_id, team_board, proof_team) -> None:
    team = _mapping(team_board.get('team'))
    required_mappings = (
        'bullpen_membership_authority',
        'roster_authority',
        'workload_concentration',
        'workload_windows',
        'workload_windows_authority',
        'deployment_profile',
        'deployment_profile_authority',
        'rest_status',
        'rest_status_authority',
        'capacity_intelligence',
        'rotation_support_pressure',
        'rotation_support_pressure_authority',
        'bullpen_stability',
        'bullpen_environment',
    )
    if (
        _positive_int(team.get('team_id')) != team_id
        or not isinstance(team_board.get('records'), list)
        or not isinstance(team_board.get('default_pitcher_ids'), list)
        or any(not isinstance(team_board.get(key), Mapping) for key in required_mappings)
        or _positive_int(proof_team.get('team_id')) != team_id
        or proof_team.get('evidence_complete') is not True
        or _mapping(proof_team.get('reference_date_alignment')).get('aligned') is not True
        or not isinstance(proof_team.get('final_team_state'), Mapping)
        or not isinstance(proof_team.get('team_state_evidence'), Mapping)
    ):
        raise TeamPublicationError(
            f'team_publication_team_source_invalid:{team_id}'
        )


def _normalized_team_ids(by_team) -> tuple[int, ...]:
    ids = []
    for raw in by_team:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return ()
        if value <= 0:
            return ()
        ids.append(value)
    return tuple(sorted(ids)) if len(ids) == len(set(ids)) else ()


def league_cohort_id(snapshot) -> str:
    material = {
        'contract': COHORT_CONTRACT,
        'source_dashboard_snapshot_id': snapshot.id,
        'source_sync_run_id': snapshot.sync_run_id,
        'dashboard_payload_version': snapshot.payload_version,
        'represented_date': _iso(snapshot.data_through),
        'source_published_at': _iso(snapshot.published_at),
    }
    return _digest(material)


def _method_versions(snapshot, team_board, proof_row, proof_team) -> dict:
    def method(authority_key):
        return _mapping(team_board.get(authority_key)).get('method_version')

    versions = {
        'dashboard_payload_version': snapshot.payload_version,
        'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
        'team_state_proof_method_version': proof_row.method_version,
        'team_state_method_version': _mapping(
            proof_team.get('team_state_evidence')
        ).get('method_version'),
        'bullpen_membership': method('bullpen_membership_authority'),
        'rest_status': method('rest_status_authority'),
        'workload_windows': method('workload_windows_authority'),
        'deployment_profile': method('deployment_profile_authority'),
        'rotation_impact': method('rotation_support_pressure_authority'),
    }
    if any(value in (None, '') for value in versions.values()):
        raise TeamPublicationError('team_publication_method_version_missing')
    return versions


def _team_what_changed(snapshot, team_id) -> dict:
    block = _mapping(_mapping(snapshot.payload).get('what_changed_since_yesterday'))
    team = _team_value(block.get('by_team_id'), team_id)
    return {
        'comparison': deepcopy(_mapping(block.get('comparison'))),
        'team': team,
        'status': block.get('status'),
        'state': block.get('state'),
        'method_version': block.get('version'),
    }


def _publication_id(snapshot, team_id, cohort_id) -> str:
    return _digest({
        'authority_version': AUTHORITY_VERSION,
        'source_type': TeamPublicPublication.SOURCE_LEAGUE_DASHBOARD,
        'team_id': team_id,
        'source_dashboard_snapshot_id': snapshot.id,
        'source_sync_run_id': snapshot.sync_run_id,
        'cohort_id': cohort_id,
    })


def _payload_for_team(
    snapshot,
    proof_row,
    team_id,
    team_board,
    proof_team,
    *,
    publication_id,
    sequence,
    predecessor_publication_id,
    cohort_id,
    method_versions,
    canonical_fingerprints,
) -> dict:
    return {
        'contract': PAYLOAD_CONTRACT,
        'schema_version': PAYLOAD_SCHEMA_VERSION,
        'identity': {
            'authority_version': AUTHORITY_VERSION,
            'publication_id': publication_id,
            'team_id': team_id,
            'source_type': TeamPublicPublication.SOURCE_LEAGUE_DASHBOARD,
            'sequence': sequence,
            'predecessor_publication_id': predecessor_publication_id,
            'cohort_id': cohort_id,
            'source_dashboard_snapshot_id': snapshot.id,
            'source_sync_run_id': snapshot.sync_run_id,
            'represented_date': _iso(snapshot.data_through),
            'data_through': _iso(snapshot.data_through),
            'availability_reference_date': _iso(snapshot.availability_reference_date),
            'generated_at': _iso(snapshot.snapshot_generated_at),
            'source_published_at': _iso(snapshot.published_at),
            'payload_schema_version': PAYLOAD_SCHEMA_VERSION,
        },
        'team': deepcopy(_mapping(team_board.get('team'))),
        'team_board': deepcopy(team_board),
        'team_state_publication_proof': deepcopy(proof_team),
        'what_changed': _team_what_changed(snapshot, team_id),
        'method_versions': deepcopy(method_versions),
        'canonical_fingerprints': deepcopy(canonical_fingerprints),
        'trust': {
            'status': TeamPublicPublication.TRUST_TRUSTED,
            'completeness': TeamPublicPublication.COMPLETENESS_COMPLETE,
            'source_proof_id': proof_row.id,
            'source_proof_verdict': proof_row.overall_verdict,
        },
        'source_game_pks': [],
        'source_observation_fingerprints': [],
        'limitations': list(proof_team.get('limitations') or []),
        'unsupported_domains': [
            'request_time_live_enrichment',
            'continuous_team_authoring',
        ],
    }


def _digest_material(publication) -> dict:
    return {
        'authority_version': publication.authority_version,
        'publication_id': publication.publication_id,
        'team_id': publication.team_id,
        'source_type': publication.source_type,
        'sequence': publication.sequence,
        'cohort_id': publication.cohort_id,
        'represented_date': _iso(publication.represented_date),
        'data_through': _iso(publication.data_through),
        'availability_reference_date': _iso(publication.availability_reference_date),
        'generated_at': _iso(publication.generated_at),
        'source_published_at': _iso(publication.source_published_at),
        'source_sync_run_id': publication.source_sync_run_id,
        'source_dashboard_snapshot_id': publication.source_dashboard_snapshot_id,
        'source_game_pks': publication.source_game_pks,
        'source_observation_fingerprints': publication.source_observation_fingerprints,
        'payload_schema_version': publication.payload_schema_version,
        'method_versions': publication.method_versions,
        'canonical_fingerprints': publication.canonical_fingerprints,
        'trust_status': publication.trust_status,
        'completeness_status': publication.completeness_status,
        'is_correction': bool(publication.is_correction),
        'payload': publication.payload,
    }


def compute_package_digest(publication) -> str:
    return _digest(_digest_material(publication))


def _build_publication(snapshot, proof_row, team_id, team_board, proof_team,
                       *, pointer, cohort_id, session) -> TeamPublicPublication:
    sequence = int(pointer.sequence) + 1 if pointer is not None else 1
    predecessor = None
    predecessor_public_id = None
    if pointer is not None:
        predecessor = session.get(
            TeamPublicPublication, pointer.current_publication_id
        )
        if predecessor is None or predecessor.team_id != team_id:
            raise TeamPublicationError('team_publication_pointer_predecessor_invalid')
        predecessor_public_id = predecessor.publication_id

    publication_id = _publication_id(snapshot, team_id, cohort_id)
    versions = _method_versions(snapshot, team_board, proof_row, proof_team)
    canonical_fingerprints = {
        'dashboard_payload': _digest(snapshot.payload),
        'team_board': _digest(team_board),
        'team_state_publication_proof': _digest(proof_team),
        'what_changed': _digest(_team_what_changed(snapshot, team_id)),
    }
    payload = _payload_for_team(
        snapshot,
        proof_row,
        team_id,
        team_board,
        proof_team,
        publication_id=publication_id,
        sequence=sequence,
        predecessor_publication_id=predecessor_public_id,
        cohort_id=cohort_id,
        method_versions=versions,
        canonical_fingerprints=canonical_fingerprints,
    )
    publication = TeamPublicPublication(
        publication_id=publication_id,
        authority_version=AUTHORITY_VERSION,
        team_id=team_id,
        source_type=TeamPublicPublication.SOURCE_LEAGUE_DASHBOARD,
        sequence=sequence,
        predecessor_publication_id=predecessor.id if predecessor is not None else None,
        cohort_id=cohort_id,
        represented_date=snapshot.data_through,
        data_through=snapshot.data_through,
        availability_reference_date=snapshot.availability_reference_date,
        generated_at=snapshot.snapshot_generated_at,
        source_published_at=snapshot.published_at,
        source_sync_run_id=snapshot.sync_run_id,
        source_dashboard_snapshot_id=snapshot.id,
        source_game_pks=[],
        source_observation_fingerprints=[],
        payload_schema_version=PAYLOAD_SCHEMA_VERSION,
        method_versions=versions,
        canonical_fingerprints=canonical_fingerprints,
        trust_status=TeamPublicPublication.TRUST_TRUSTED,
        completeness_status=TeamPublicPublication.COMPLETENESS_COMPLETE,
        is_correction=False,
        payload=payload,
    )
    publication.package_digest = compute_package_digest(publication)
    return publication


def validate_publication(publication, *, session=None) -> dict:
    session = session or db.session
    if publication is None:
        raise TeamPublicationError('team_publication_missing')
    if (
        _positive_int(publication.team_id) is None
        or publication.team_id not in EXPECTED_TEAM_IDS
        or _positive_int(publication.sequence) is None
        or publication.authority_version != AUTHORITY_VERSION
        or publication.source_type not in {
            TeamPublicPublication.SOURCE_LEAGUE_DASHBOARD,
            TeamPublicPublication.SOURCE_CONTINUOUS_TEAM,
        }
        or publication.payload_schema_version != PAYLOAD_SCHEMA_VERSION
        or publication.trust_status != TeamPublicPublication.TRUST_TRUSTED
        or publication.completeness_status
        != TeamPublicPublication.COMPLETENESS_COMPLETE
        or not isinstance(publication.payload, Mapping)
        or not isinstance(publication.method_versions, Mapping)
        or not isinstance(publication.canonical_fingerprints, Mapping)
        or not isinstance(publication.source_game_pks, list)
        or not isinstance(publication.source_observation_fingerprints, list)
    ):
        raise TeamPublicationError('team_publication_identity_invalid')

    payload = _mapping(publication.payload)
    identity = _mapping(payload.get('identity'))
    if (
        payload.get('contract') != PAYLOAD_CONTRACT
        or payload.get('schema_version') != PAYLOAD_SCHEMA_VERSION
        or identity.get('publication_id') != publication.publication_id
        or identity.get('authority_version') != publication.authority_version
        or identity.get('team_id') != publication.team_id
        or identity.get('source_type') != publication.source_type
        or identity.get('sequence') != publication.sequence
        or identity.get('cohort_id') != publication.cohort_id
        or identity.get('source_dashboard_snapshot_id')
        != publication.source_dashboard_snapshot_id
        or identity.get('source_sync_run_id') != publication.source_sync_run_id
        or identity.get('represented_date') != _iso(publication.represented_date)
        or identity.get('data_through') != _iso(publication.data_through)
        or identity.get('availability_reference_date')
        != _iso(publication.availability_reference_date)
        or identity.get('generated_at') != _iso(publication.generated_at)
        or identity.get('source_published_at') != _iso(publication.source_published_at)
        or identity.get('payload_schema_version') != publication.payload_schema_version
        or payload.get('method_versions') != publication.method_versions
        or payload.get('canonical_fingerprints') != publication.canonical_fingerprints
        or payload.get('source_game_pks') != publication.source_game_pks
        or payload.get('source_observation_fingerprints')
        != publication.source_observation_fingerprints
        or _positive_int(_mapping(payload.get('team')).get('team_id'))
        != publication.team_id
    ):
        raise TeamPublicationError('team_publication_payload_identity_mismatch')

    predecessor_public_id = identity.get('predecessor_publication_id')
    predecessor = None
    if publication.predecessor_publication_id is not None:
        with session.no_autoflush:
            predecessor = session.get(
                TeamPublicPublication, publication.predecessor_publication_id
            )
        if (
            predecessor is None
            or predecessor.id == publication.id
            or predecessor.team_id != publication.team_id
            or predecessor.sequence + 1 != publication.sequence
            or predecessor.publication_id != predecessor_public_id
        ):
            raise TeamPublicationError('team_publication_predecessor_invalid')
    elif publication.sequence != 1 or predecessor_public_id is not None:
        raise TeamPublicationError('team_publication_lineage_missing')

    if publication.source_type == TeamPublicPublication.SOURCE_LEAGUE_DASHBOARD:
        with session.no_autoflush:
            snapshot = session.get(
                DashboardSnapshot, publication.source_dashboard_snapshot_id
            )
            proof_row = (
                session.query(TeamStatePublicationProof)
                .filter(
                    TeamStatePublicationProof.snapshot_id
                    == publication.source_dashboard_snapshot_id
                )
                .one_or_none()
            )
        snapshot_payload = _mapping(getattr(snapshot, 'payload', None))
        frozen = _mapping(snapshot_payload.get(TEAM_BOARD_PACKAGE_KEY))
        source_board = _team_value(frozen.get('by_team_id'), publication.team_id)
        proof_payload = _mapping(getattr(proof_row, 'proof', None))
        proof_team = next((
            deepcopy(item)
            for item in (proof_payload.get('teams') or [])
            if isinstance(item, Mapping) and item.get('team_id') == publication.team_id
        ), None)
        expected_what_changed = (
            _team_what_changed(snapshot, publication.team_id)
            if snapshot is not None
            else None
        )
        expected_fingerprints = (
            {
                'dashboard_payload': _digest(snapshot.payload),
                'team_board': _digest(source_board),
                'team_state_publication_proof': _digest(proof_team),
                'what_changed': _digest(expected_what_changed),
            }
            if snapshot is not None and source_board is not None and proof_team is not None
            else None
        )
        if (
            snapshot is None
            or proof_row is None
            or snapshot.sync_run_id != publication.source_sync_run_id
            or snapshot.data_through != publication.data_through
            or snapshot.availability_reference_date
            != publication.availability_reference_date
            or snapshot.snapshot_generated_at != publication.generated_at
            or snapshot.published_at != publication.source_published_at
            or publication.cohort_id != league_cohort_id(snapshot)
            or publication.publication_id
            != _publication_id(snapshot, publication.team_id, publication.cohort_id)
            or publication.source_game_pks != []
            or publication.source_observation_fingerprints != []
            or expected_fingerprints != publication.canonical_fingerprints
            or _method_versions(snapshot, source_board, proof_row, proof_team)
            != publication.method_versions
            or payload.get('team_board') != source_board
            or payload.get('team_state_publication_proof') != proof_team
            or payload.get('what_changed') != expected_what_changed
        ):
            raise TeamPublicationError('team_publication_source_identity_mismatch')
    else:
        raise TeamPublicationError(
            'team_publication_continuous_authoring_not_enabled'
        )

    expected_digest = compute_package_digest(publication)
    if publication.package_digest != expected_digest:
        raise TeamPublicationError('team_publication_digest_mismatch')
    return {
        'valid': True,
        'publication_id': publication.publication_id,
        'team_id': publication.team_id,
        'sequence': publication.sequence,
        'cohort_id': publication.cohort_id,
        'digest': publication.package_digest,
    }


def validate_pointer(pointer, *, session=None) -> dict:
    session = session or db.session
    if pointer is None:
        raise TeamPublicationError('team_publication_pointer_missing')
    publication = session.get(TeamPublicPublication, pointer.current_publication_id)
    if (
        publication is None
        or pointer.team_id != publication.team_id
        or pointer.sequence != publication.sequence
        or pointer.authority_generation <= 0
    ):
        raise TeamPublicationError('team_publication_pointer_mismatch')
    validate_publication(publication, session=session)
    return {
        'valid': True,
        'team_id': pointer.team_id,
        'publication_id': publication.publication_id,
        'sequence': pointer.sequence,
        'cohort_id': publication.cohort_id,
    }


def validate_current_team_publication_cohort(
    *, expected_cohort_id=None, session=None
) -> dict:
    """Validate the complete 30-team current-pointer population as one cohort."""
    session = session or db.session
    pointers = session.query(TeamPublicCurrentPointer).order_by(
        TeamPublicCurrentPointer.team_id
    ).all()
    ids = tuple(pointer.team_id for pointer in pointers)
    if ids != EXPECTED_TEAM_IDS:
        raise TeamPublicationError('team_publication_pointer_population_incomplete')
    projections = [validate_pointer(pointer, session=session) for pointer in pointers]
    cohort_ids = {projection['cohort_id'] for projection in projections}
    if len(cohort_ids) != 1:
        raise TeamPublicationError('team_publication_current_cohort_mixed')
    cohort_id = next(iter(cohort_ids))
    if expected_cohort_id is not None and cohort_id != expected_cohort_id:
        raise TeamPublicationError('team_publication_current_cohort_unexpected')
    publications = [
        session.get(TeamPublicPublication, pointer.current_publication_id)
        for pointer in pointers
    ]
    source_snapshot_ids = {
        publication.source_dashboard_snapshot_id for publication in publications
    }
    source_sync_run_ids = {
        publication.source_sync_run_id for publication in publications
    }
    if len(source_snapshot_ids) != 1 or len(source_sync_run_ids) != 1:
        raise TeamPublicationError('team_publication_current_source_mixed')
    return {
        'valid': True,
        'team_count': len(pointers),
        'cohort_id': cohort_id,
        'source_dashboard_snapshot_id': next(iter(source_snapshot_ids)),
        'source_sync_run_id': next(iter(source_sync_run_ids)),
    }


def advance_pointer_compare_and_set(
    publication,
    *,
    expected_publication_id,
    session=None,
) -> bool:
    """Advance one pointer iff its current row matches the supplied predecessor."""
    session = session or db.session
    if publication.id is None:
        session.flush()
    validate_publication(publication, session=session)

    pointer = session.get(TeamPublicCurrentPointer, publication.team_id)
    if pointer is None:
        if expected_publication_id is not None:
            raise TeamPublicationConflict('team_publication_pointer_expected_missing')
        if publication.sequence != 1 or publication.predecessor_publication_id is not None:
            raise TeamPublicationConflict('team_publication_pointer_initial_lineage_invalid')
        session.add(TeamPublicCurrentPointer(
            team_id=publication.team_id,
            current_publication_id=publication.id,
            sequence=publication.sequence,
            authority_generation=1,
            updated_at=utc_now_naive(),
        ))
        session.flush()
        return True

    if pointer.current_publication_id == publication.id:
        if pointer.sequence != publication.sequence:
            raise TeamPublicationConflict('team_publication_pointer_sequence_mismatch')
        return False
    if pointer.current_publication_id != expected_publication_id:
        raise TeamPublicationConflict('team_publication_pointer_compare_and_set_failed')
    if (
        publication.predecessor_publication_id != expected_publication_id
        or publication.sequence != pointer.sequence + 1
    ):
        raise TeamPublicationConflict('team_publication_pointer_lineage_conflict')

    updated = (
        session.query(TeamPublicCurrentPointer)
        .filter(
            TeamPublicCurrentPointer.team_id == publication.team_id,
            TeamPublicCurrentPointer.current_publication_id == expected_publication_id,
            TeamPublicCurrentPointer.sequence == pointer.sequence,
        )
        .update({
            TeamPublicCurrentPointer.current_publication_id: publication.id,
            TeamPublicCurrentPointer.sequence: publication.sequence,
            TeamPublicCurrentPointer.authority_generation:
                pointer.authority_generation + 1,
            TeamPublicCurrentPointer.updated_at: utc_now_naive(),
        }, synchronize_session='fetch')
    )
    if updated != 1:
        raise TeamPublicationConflict('team_publication_pointer_compare_and_set_failed')
    session.flush()
    return True


def _existing_for_snapshot(session, snapshot_id) -> dict[int, TeamPublicPublication]:
    rows = (
        session.query(TeamPublicPublication)
        .filter(
            TeamPublicPublication.source_type
            == TeamPublicPublication.SOURCE_LEAGUE_DASHBOARD,
            TeamPublicPublication.source_dashboard_snapshot_id == snapshot_id,
        )
        .all()
    )
    result = {row.team_id: row for row in rows}
    if len(result) != len(rows):
        raise TeamPublicationError('team_publication_duplicate_source_rows')
    return result


def author_league_dashboard_team_publications(
    snapshot,
    *,
    session=None,
    commit=True,
) -> TeamPublicationAuthoringResult:
    """Atomically author and activate all 30 dormant league-derived packages."""
    session = session or db.session
    try:
        proof_row = (
            session.query(TeamStatePublicationProof)
            .filter(TeamStatePublicationProof.snapshot_id == getattr(snapshot, 'id', None))
            .one_or_none()
        )
        _frozen, board_by_team, proof_by_team = _validate_source_snapshot(
            snapshot, proof_row
        )
        cohort_id = league_cohort_id(snapshot)
        existing = _existing_for_snapshot(session, snapshot.id)
        pointers = {
            row.team_id: row
            for row in (
                session.query(TeamPublicCurrentPointer)
                .filter(TeamPublicCurrentPointer.team_id.in_(EXPECTED_TEAM_IDS))
                .with_for_update()
                .all()
            )
        }

        publications = {}
        created = 0
        reused = 0
        for team_id in EXPECTED_TEAM_IDS:
            board = _team_value(board_by_team, team_id)
            proof_team = proof_by_team.get(team_id)
            if board is None or proof_team is None:
                raise TeamPublicationError(
                    f'team_publication_team_source_missing:{team_id}'
                )
            _validate_team_sources(team_id, board, proof_team)
            row = existing.get(team_id)
            if row is None:
                row = _build_publication(
                    snapshot,
                    proof_row,
                    team_id,
                    board,
                    proof_team,
                    pointer=pointers.get(team_id),
                    cohort_id=cohort_id,
                    session=session,
                )
                validate_publication(row, session=session)
                session.add(row)
                created += 1
            else:
                validate_publication(row, session=session)
                pointer = pointers.get(team_id)
                expected_sequence = pointer.sequence + 1 if pointer is not None else 1
                expected_predecessor = (
                    pointer.current_publication_id if pointer is not None else None
                )
                if pointer is not None and pointer.current_publication_id == row.id:
                    expected_sequence = pointer.sequence
                    expected_predecessor = row.predecessor_publication_id
                if (
                    row.cohort_id != cohort_id
                    or row.sequence != expected_sequence
                    or row.predecessor_publication_id != expected_predecessor
                ):
                    raise TeamPublicationConflict(
                        f'team_publication_existing_lineage_conflict:{team_id}'
                    )
                reused += 1
            publications[team_id] = row

        session.flush()
        for row in publications.values():
            validate_publication(row, session=session)

        advanced = 0
        unchanged = 0
        for team_id in EXPECTED_TEAM_IDS:
            pointer = pointers.get(team_id)
            row = publications[team_id]
            moved = advance_pointer_compare_and_set(
                row,
                expected_publication_id=(
                    pointer.current_publication_id if pointer is not None else None
                ),
                session=session,
            )
            advanced += int(moved)
            unchanged += int(not moved)

        session.flush()
        validate_current_team_publication_cohort(
            expected_cohort_id=cohort_id,
            session=session,
        )
        if commit:
            session.commit()

        return TeamPublicationAuthoringResult(
            source_snapshot_id=snapshot.id,
            source_sync_run_id=snapshot.sync_run_id,
            cohort_id=cohort_id,
            teams_expected=len(EXPECTED_TEAM_IDS),
            packages_created=created,
            packages_reused=reused,
            pointers_advanced=advanced,
            pointers_unchanged=unchanged,
        )
    except Exception:
        session.rollback()
        raise


def bootstrap_current_trusted_dashboard(*, session=None, commit=True):
    """One-shot, explicit bootstrap from the existing D-051 serving authority."""
    session = session or db.session
    try:
        snapshot = dashboard_snapshot_service.get_latest_dashboard_snapshot_guarded()
    except SnapshotReadUnavailable as exc:
        raise TeamPublicationError(
            'team_publication_current_dashboard_unavailable'
        ) from exc
    if snapshot is None or dashboard_snapshot_service.snapshot_unavailable_reason(snapshot):
        raise TeamPublicationError('team_publication_current_dashboard_unavailable')
    return author_league_dashboard_team_publications(
        snapshot, session=session, commit=commit
    )


def inspect_team_publication_storage(*, session=None) -> dict:
    """Read-only, payload-free integrity and cohort observability."""
    session = session or db.session
    pointers = (
        session.query(TeamPublicCurrentPointer)
        .order_by(TeamPublicCurrentPointer.team_id)
        .all()
    )
    teams = []
    invalid = []
    cohorts = set()
    for pointer in pointers:
        publication = session.get(
            TeamPublicPublication, pointer.current_publication_id
        )
        try:
            check = validate_pointer(pointer, session=session)
            digest_valid = True
            predecessor_valid = True
        except TeamPublicationError as exc:
            check = {}
            digest_valid = False
            predecessor_valid = False
            invalid.append({'team_id': pointer.team_id, 'reason': str(exc)})
        if publication is not None:
            cohorts.add(publication.cohort_id)
        teams.append({
            'team_id': pointer.team_id,
            'publication_id': check.get('publication_id'),
            'sequence': pointer.sequence,
            'source_type': getattr(publication, 'source_type', None),
            'cohort_id': getattr(publication, 'cohort_id', None),
            'source_dashboard_snapshot_id': getattr(
                publication, 'source_dashboard_snapshot_id', None
            ),
            'source_sync_run_id': getattr(publication, 'source_sync_run_id', None),
            'data_through': _iso(getattr(publication, 'data_through', None)),
            'digest_valid': digest_valid,
            'predecessor_valid': predecessor_valid,
        })
    present = {row['team_id'] for row in teams}
    return {
        'event': 'team_publication_storage_status',
        'status': 'valid' if not invalid and len(present) == 30 else 'invalid',
        'teams_expected': len(EXPECTED_TEAM_IDS),
        'current_pointer_count': len(pointers),
        'cohort_count': len(cohorts),
        'mixed_current_cohorts': len(cohorts) > 1,
        'missing_team_ids': sorted(set(EXPECTED_TEAM_IDS) - present),
        'invalid': invalid,
        'teams': teams,
    }


__all__ = [
    'AUTHORITY_VERSION',
    'COHORT_CONTRACT',
    'EXPECTED_TEAM_IDS',
    'PAYLOAD_CONTRACT',
    'PAYLOAD_SCHEMA_VERSION',
    'TeamPublicationAuthoringResult',
    'TeamPublicationConflict',
    'TeamPublicationError',
    'advance_pointer_compare_and_set',
    'author_league_dashboard_team_publications',
    'bootstrap_current_trusted_dashboard',
    'canonical_json',
    'compute_package_digest',
    'inspect_team_publication_storage',
    'league_cohort_id',
    'validate_pointer',
    'validate_publication',
    'validate_current_team_publication_cohort',
]
