"""Dormant D-058 per-team publication authoring and integrity services.

Package 1 authors and activates league-derived rows. Package 2 appends validated
continuous shadow rows after CU-06 without moving pointers. Neither package serves
Team Board or alters share artifacts. ``TeamProgressivePublication`` remains the
independent Team State Share Artifact authority until a later convergence package.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from datetime import date, datetime
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
CONTINUOUS_COHORT_CONTRACT = 'continuous_team_mutation_cohort_v1'
CONTINUOUS_SOURCE_CONTRACT = 'continuous_team_shadow_source_v1'
CONTINUOUS_EQUIVALENCE_CONTRACT = 'continuous_team_equivalence_v1'
TRUSTED_PROOF_VERDICTS = {'PASS', 'PASS_WITH_INCONCLUSIVE'}
EXPECTED_TEAM_IDS = tuple(sorted(int(value) for value in MLB_TEAM_IDS))


class TeamPublicationError(ValueError):
    """Fail-closed dormant-authoring or integrity error."""


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


@dataclass(frozen=True)
class ContinuousTeamPublicationAuthoringResult:
    game_pk: int
    source_sync_run_id: int
    work_job_id: int
    cohort_id: str
    affected_team_ids: tuple[int, ...]
    packages_created: int
    packages_reused: int
    equivalent: int
    publication_ids: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            'event': 'team_publication_shadow',
            'status': 'complete',
            'game_pk': self.game_pk,
            'source_sync_run_id': self.source_sync_run_id,
            'work_job_id': self.work_job_id,
            'affected_team_ids': list(self.affected_team_ids),
            'cohort_id': self.cohort_id,
            'packages_attempted': len(self.affected_team_ids),
            'packages_created': self.packages_created,
            'packages_reused': self.packages_reused,
            'equivalent': self.equivalent,
            'validation_failures': 0,
            'equivalence_failures': 0,
            'pointers_advanced': 0,
            'publication_ids': list(self.publication_ids),
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


def _date_value(value) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _team_mapping(container, team_id) -> dict:
    values = _mapping(container)
    value = values.get(team_id)
    if value is None:
        value = values.get(str(team_id))
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _int_tuple(value) -> tuple[int, ...]:
    if isinstance(value, (str, bytes, Mapping)) or value is None:
        return ()
    values = []
    try:
        items = iter(value)
    except TypeError:
        return ()
    for item in items:
        parsed = _positive_int(item)
        if parsed is None:
            return ()
        values.append(parsed)
    return tuple(sorted(set(values)))


def _sha256(value) -> Optional[str]:
    if not isinstance(value, str) or len(value) != 64:
        return None
    try:
        int(value, 16)
    except ValueError:
        return None
    return value.lower()


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


def author_continuous_team_publications_shadow(
    *, change, canonical_impact, workload_result, team_state_result,
    read_model_result, source_sync_run_id, work_job_id, session=None,
    commit=True,
) -> ContinuousTeamPublicationAuthoringResult:
    """Author one atomic affected-team cohort without advancing public pointers.

    Lineage follows the latest valid immutable publication, rather than the
    current pointer. This deliberately permits validated shadow sequence 2+
    while the D-051-backed current pointer remains at its league-derived row.
    """
    session = session or db.session
    try:
        affected_team_ids = _int_tuple(
            _mapping(canonical_impact).get('affected_team_ids') or ()
        )
        if not affected_team_ids or len(affected_team_ids) > 2:
            raise TeamPublicationError('team_publication_continuous_team_scope_invalid')
        generated_at = utc_now_naive()
        sources_by_team = {}
        for team_id in affected_team_ids:
            try:
                sources_by_team[team_id] = _continuous_sources(
                    team_id=team_id,
                    change=_mapping(change),
                    canonical_impact=_mapping(canonical_impact),
                    workload_result=_mapping(workload_result),
                    team_state_result=_mapping(team_state_result),
                    read_model_result=_mapping(read_model_result),
                    source_sync_run_id=source_sync_run_id,
                    work_job_id=work_job_id,
                )
            except TeamPublicationError as exc:
                if str(exc).endswith(f':{team_id}'):
                    raise
                raise TeamPublicationError(f'{exc}:{team_id}') from exc
        exemplar = sources_by_team[affected_team_ids[0]]
        cohort_id = continuous_cohort_id(
            game_pk=exemplar['game_pk'],
            observation_fingerprint=exemplar['observation_fingerprint'],
            canonical_mutation_fingerprint=exemplar[
                'canonical_mutation_fingerprint'
            ],
            represented_date=exemplar['represented_date'],
        )
        if any(
            source['canonical_mutation_fingerprint']
            != exemplar['canonical_mutation_fingerprint']
            for source in sources_by_team.values()
        ):
            raise TeamPublicationError(
                'team_publication_continuous_cohort_identity_invalid'
            )

        publication_ids = {
            team_id: _continuous_publication_id(team_id, cohort_id)
            for team_id in affected_team_ids
        }
        existing_rows = (
            session.query(TeamPublicPublication)
            .filter(
                TeamPublicPublication.publication_id.in_(
                    tuple(publication_ids.values())
                )
            )
            .all()
        )
        existing = {row.team_id: row for row in existing_rows}
        if len(existing) != len(existing_rows):
            raise TeamPublicationError('team_publication_duplicate_source_rows')

        pointers = {
            pointer.team_id: pointer
            for pointer in (
                session.query(TeamPublicCurrentPointer)
                .filter(TeamPublicCurrentPointer.team_id.in_(affected_team_ids))
                .with_for_update()
                .all()
            )
        }
        if tuple(sorted(pointers)) != affected_team_ids:
            raise TeamPublicationError(
                'team_publication_continuous_current_pointer_missing'
            )
        pointer_identity_before = {
            team_id: (pointer.current_publication_id, pointer.sequence)
            for team_id, pointer in pointers.items()
        }

        latest = {}
        for team_id in affected_team_ids:
            latest[team_id] = (
                session.query(TeamPublicPublication)
                .filter(TeamPublicPublication.team_id == team_id)
                .order_by(TeamPublicPublication.sequence.desc())
                .with_for_update()
                .first()
            )
            if latest[team_id] is None:
                raise TeamPublicationError(
                    'team_publication_continuous_lineage_missing'
                )
            validate_publication(latest[team_id], session=session)

        created = 0
        reused = 0
        rows = {}
        for team_id in affected_team_ids:
            row = existing.get(team_id)
            if row is None:
                predecessor = latest[team_id]
                row = _build_continuous_publication(
                    team_id=team_id,
                    sequence=predecessor.sequence + 1,
                    predecessor=predecessor,
                    cohort_id=cohort_id,
                    sources=sources_by_team[team_id],
                    generated_at=generated_at,
                )
                session.add(row)
                created += 1
            else:
                reused += 1
            rows[team_id] = row

        session.flush()
        for team_id, row in rows.items():
            validate_publication(row, session=session)
            if (
                row.publication_id != publication_ids[team_id]
                or row.cohort_id != cohort_id
            ):
                raise TeamPublicationError(
                    'team_publication_continuous_existing_identity_conflict'
                )

        pointer_identity_after = {
            pointer.team_id: (pointer.current_publication_id, pointer.sequence)
            for pointer in (
                session.query(TeamPublicCurrentPointer)
                .filter(TeamPublicCurrentPointer.team_id.in_(affected_team_ids))
                .all()
            )
        }
        if pointer_identity_after != pointer_identity_before:
            raise TeamPublicationConflict(
                'team_publication_shadow_pointer_movement_forbidden'
            )
        persisted_sync_runs = {row.source_sync_run_id for row in rows.values()}
        persisted_work_jobs = {
            _mapping(row.payload).get('continuous_source', {}).get('work_job_id')
            for row in rows.values()
        }
        if len(persisted_sync_runs) != 1 or len(persisted_work_jobs) != 1:
            raise TeamPublicationError(
                'team_publication_continuous_cohort_provenance_mixed'
            )
        if commit:
            session.commit()
        return ContinuousTeamPublicationAuthoringResult(
            game_pk=exemplar['game_pk'],
            source_sync_run_id=next(iter(persisted_sync_runs)),
            work_job_id=next(iter(persisted_work_jobs)),
            cohort_id=cohort_id,
            affected_team_ids=affected_team_ids,
            packages_created=created,
            packages_reused=reused,
            equivalent=len(rows),
            publication_ids=tuple(
                rows[team_id].publication_id for team_id in affected_team_ids
            ),
        )
    except Exception:
        session.rollback()
        raise


def _board_team_id(board) -> Optional[int]:
    return _positive_int(_mapping(_mapping(board).get('team')).get('team_id')) \
        or _positive_int(_mapping(board).get('team_id'))


def _board_pitcher_ids(board) -> tuple[int, ...]:
    board = _mapping(board)
    records = board.get('records')
    if isinstance(records, list):
        return _int_tuple(
            record.get('pitcher_id')
            for record in records
            if isinstance(record, Mapping)
        )
    cards = []
    for group in board.get('groups') or ():
        if isinstance(group, Mapping):
            cards.extend(
                card for card in group.get('pitchers') or group.get('arms') or ()
                if isinstance(card, Mapping)
            )
    return _int_tuple(card.get('pitcher_id') for card in cards)


def _board_cards_by_pitcher(board) -> dict[int, dict]:
    result = {}
    for group in _mapping(board).get('groups') or ():
        if not isinstance(group, Mapping):
            continue
        for card in group.get('pitchers') or ():
            pitcher_id = _positive_int(_mapping(card).get('pitcher_id'))
            if pitcher_id is not None:
                result[pitcher_id] = deepcopy(dict(card))
    return result


def _continuous_method_versions(board) -> dict:
    delivery = _mapping(_mapping(board).get('publication_method_versions'))
    versions = {
        'continuous_team_package': CONTINUOUS_SOURCE_CONTRACT,
        'continuous_equivalence': CONTINUOUS_EQUIVALENCE_CONTRACT,
        'workload_rest': 'cu04_incremental_workload_rest_v1',
        'arm_read_team_state': 'cu05_incremental_arm_read_team_state_v1',
        'read_model': 'cu06_incremental_read_model_v1',
        **delivery,
    }
    required = (
        'bullpen_membership', 'rest_status', 'workload_windows',
        'deployment_profile', 'rotation_impact',
    )
    if any(versions.get(key) in (None, '') for key in required):
        raise TeamPublicationError('team_publication_method_version_missing')
    return versions


def _validate_continuous_team_package(team_id, package) -> None:
    package = _mapping(package)
    team = _mapping(package.get('team'))
    required_mappings = (
        'bullpen_membership_authority', 'roster_authority',
        'workload_concentration', 'workload_windows',
        'workload_windows_authority', 'deployment_profile',
        'deployment_profile_authority', 'rest_status',
        'rest_status_authority', 'capacity_intelligence',
        'rotation_support_pressure', 'rotation_support_pressure_authority',
        'bullpen_stability', 'bullpen_environment',
    )
    if (
        _positive_int(team.get('team_id')) != team_id
        or not isinstance(package.get('records'), list)
        or not isinstance(package.get('default_pitcher_ids'), list)
        or any(not isinstance(package.get(key), Mapping) for key in required_mappings)
    ):
        raise TeamPublicationError(
            f'team_publication_continuous_team_package_invalid:{team_id}'
        )


def _semantic_continuous_board(board, publication_id) -> dict:
    result = deepcopy(_mapping(board))
    result.pop('publication_authority', None)
    result.pop('served_from', None)
    result['publication_authority'] = {
        'authority_type': TeamPublicPublication.SOURCE_CONTINUOUS_TEAM,
        'authority_version': AUTHORITY_VERSION,
        'publication_id': publication_id,
    }
    result['served_from'] = 'continuous_team_shadow'
    return result


def _continuous_mutation_fingerprint(
    *, change, canonical_impact, workload_result, team_state_result,
    read_model_result,
) -> str:
    return _digest({
        'contract': CONTINUOUS_SOURCE_CONTRACT,
        'game_pk': canonical_impact.get('game_pk'),
        'observation_fingerprint': change.get('current_observation_identity'),
        'canonical_source_revision': canonical_impact.get(
            'canonical_source_revision'
        ),
        'affected_pitcher_ids': _int_tuple(
            canonical_impact.get('affected_pitcher_ids') or ()
        ),
        'affected_team_ids': _int_tuple(
            canonical_impact.get('affected_team_ids') or ()
        ),
        'canonical_impact': {
            key: deepcopy(canonical_impact.get(key))
            for key in (
                'game_pk', 'canonical_mutation_performed',
                'canonical_source_revision', 'affected_pitcher_ids',
                'affected_team_ids', 'game_log_inserted', 'game_log_updated',
                'pitch_inserted', 'pitch_updated', 'pitch_superseded',
                'optional_pbp_status',
            )
        },
        'workload_result': {
            key: deepcopy(workload_result.get(key))
            for key in (
                'game_pk', 'data_through', 'availability_reference_date',
                'pitchers_recomputed', 'teams_recomputed', 'pitcher_results',
                'team_results', 'parity_status',
            )
        },
        'team_state_result': {
            key: deepcopy(team_state_result.get(key))
            for key in (
                'game_pk', 'data_through', 'availability_reference_date',
                'arm_reads_recomputed', 'teams_recomputed', 'arm_read_results',
                'team_state_results', 'availability_results',
                'workload_rest_pitcher_results', 'workload_rest_team_results',
                'parity_status',
            )
        },
        'read_model_result': {
            key: deepcopy(read_model_result.get(key))
            for key in (
                'game_pk', 'represented_date', 'requested_team_ids',
                'team_boards_rebuilt', 'team_board_results',
                'team_package_results', 'parity_status',
            )
        },
    })


def continuous_cohort_id(
    *, game_pk, observation_fingerprint, canonical_mutation_fingerprint,
    represented_date,
) -> str:
    return _digest({
        'contract': CONTINUOUS_COHORT_CONTRACT,
        'game_pk': game_pk,
        'observation_fingerprint': observation_fingerprint,
        'canonical_mutation_fingerprint': canonical_mutation_fingerprint,
        'represented_date': _iso(represented_date),
    })


def _continuous_publication_id(team_id, cohort_id) -> str:
    return _digest({
        'authority_version': AUTHORITY_VERSION,
        'source_type': TeamPublicPublication.SOURCE_CONTINUOUS_TEAM,
        'team_id': team_id,
        'cohort_id': cohort_id,
    })


def _continuous_sources(
    *, team_id, change, canonical_impact, workload_result, team_state_result,
    read_model_result, source_sync_run_id, work_job_id,
) -> dict:
    game_pk = _positive_int(canonical_impact.get('game_pk'))
    if game_pk is None or game_pk != _positive_int(change.get('game_pk')):
        raise TeamPublicationError('team_publication_continuous_game_identity_invalid')
    observation_fingerprint = _sha256(change.get('current_observation_identity'))
    if observation_fingerprint is None:
        raise TeamPublicationError(
            'team_publication_continuous_observation_identity_invalid'
        )
    if (
        not str(change.get('source_authority') or '').strip()
        or not str(canonical_impact.get('canonical_source_revision') or '').strip()
        or _positive_int(source_sync_run_id) is None
        or _positive_int(work_job_id) is None
    ):
        raise TeamPublicationError('team_publication_continuous_provenance_invalid')

    affected_team_ids = _int_tuple(canonical_impact.get('affected_team_ids') or ())
    expected_team_ids = {
        _int_tuple(workload_result.get('teams_recomputed') or ()),
        _int_tuple(team_state_result.get('teams_recomputed') or ()),
        _int_tuple(read_model_result.get('team_boards_rebuilt') or ()),
    }
    if (
        not affected_team_ids
        or team_id not in affected_team_ids
        or affected_team_ids not in expected_team_ids
        or any(value not in EXPECTED_TEAM_IDS for value in affected_team_ids)
    ):
        raise TeamPublicationError('team_publication_continuous_team_scope_invalid')

    represented_date = _date_value(read_model_result.get('represented_date'))
    data_through = _date_value(workload_result.get('data_through'))
    state_data_through = _date_value(team_state_result.get('data_through'))
    availability_date = _date_value(
        team_state_result.get('availability_reference_date')
        or workload_result.get('availability_reference_date')
    )
    if (
        represented_date is None
        or represented_date != data_through
        or represented_date != state_data_through
        or availability_date is None
    ):
        raise TeamPublicationError('team_publication_continuous_date_identity_invalid')

    board = _team_mapping(read_model_result.get('team_board_results'), team_id)
    team_package = _team_mapping(
        read_model_result.get('team_package_results'), team_id
    )
    _validate_continuous_team_package(team_id, team_package)
    team_state = _team_mapping(team_state_result.get('team_state_results'), team_id)
    public_team_state = _mapping(team_state.get('public_team_state'))
    roster_authority = _mapping(board.get('roster_authority'))
    if (
        _board_team_id(board) != team_id
        or not isinstance(board.get('groups'), list)
        or _positive_int(roster_authority.get('team_id')) != team_id
        or not str(roster_authority.get('contract') or '').strip()
        or not public_team_state
        or _mapping(board.get('team_state')) != public_team_state
        or not _board_pitcher_ids(board)
        or _mapping(team_package.get('roster_authority')) != roster_authority
    ):
        raise TeamPublicationError(
            f'team_publication_continuous_equivalence_invalid:{team_id}'
        )
    versions = _continuous_method_versions(board)
    active_pitcher_ids = _board_pitcher_ids(board)
    affected_pitcher_ids = _int_tuple(
        canonical_impact.get('affected_pitcher_ids') or ()
    )
    evidence_pitcher_ids = tuple(
        pitcher_id for pitcher_id in active_pitcher_ids
        if pitcher_id in affected_pitcher_ids
    )
    pitcher_workload = _mapping(team_state_result.get('workload_rest_pitcher_results'))
    availability = _mapping(team_state_result.get('availability_results'))
    arm_reads = _mapping(team_state_result.get('arm_read_results'))
    team_workload = _team_mapping(
        team_state_result.get('workload_rest_team_results'), team_id
    )
    cards = _board_cards_by_pitcher(board)
    if not evidence_pitcher_ids or not team_workload:
        raise TeamPublicationError(
            f'team_publication_continuous_equivalence_invalid:{team_id}'
        )
    for pitcher_id in evidence_pitcher_ids:
        workload = _mapping(
            pitcher_workload.get(pitcher_id)
            or pitcher_workload.get(str(pitcher_id))
        )
        player_availability = _mapping(
            availability.get(pitcher_id) or availability.get(str(pitcher_id))
        )
        arm_read = _mapping(
            arm_reads.get(pitcher_id) or arm_reads.get(str(pitcher_id))
        )
        card = cards[pitcher_id]
        fatigue = _mapping(workload.get('fatigue_workload'))
        board_workload = _mapping(card.get('workload_facts'))
        overlapping_workload = set(fatigue).intersection(board_workload)
        if (
            not workload
            or not player_availability
            or not arm_read
            or not overlapping_workload
            or any(
                board_workload[key] != fatigue[key]
                for key in overlapping_workload
            )
            or (
                card.get('availability_status') is not None
                and player_availability.get('availability_status')
                != card.get('availability_status')
            )
        ):
            raise TeamPublicationError(
                f'team_publication_continuous_equivalence_invalid:{team_id}'
            )
    team_evidence = {
        'team_state': team_state,
        'active_pitcher_ids': list(active_pitcher_ids),
        'affected_pitcher_ids': list(evidence_pitcher_ids),
        'workload_rest': {
            str(pitcher_id): deepcopy(
                pitcher_workload.get(pitcher_id)
                or pitcher_workload.get(str(pitcher_id))
                or {}
            )
            for pitcher_id in evidence_pitcher_ids
        },
        'availability': {
            str(pitcher_id): deepcopy(
                availability.get(pitcher_id)
                or availability.get(str(pitcher_id))
                or {}
            )
            for pitcher_id in evidence_pitcher_ids
        },
        'arm_reads': {
            str(pitcher_id): deepcopy(
                arm_reads.get(pitcher_id)
                or arm_reads.get(str(pitcher_id))
                or {}
            )
            for pitcher_id in evidence_pitcher_ids
        },
        'team_workload': team_workload,
        'roster_authority': deepcopy(roster_authority),
    }
    canonical_mutation_fingerprint = _continuous_mutation_fingerprint(
        change=change,
        canonical_impact=canonical_impact,
        workload_result=workload_result,
        team_state_result=team_state_result,
        read_model_result=read_model_result,
    )
    return {
        'game_pk': game_pk,
        'observation_fingerprint': observation_fingerprint,
        'observation_authority': str(change.get('source_authority')).strip(),
        'source_revision': str(
            canonical_impact.get('canonical_source_revision')
        ).strip(),
        'source_sync_run_id': source_sync_run_id,
        'work_job_id': work_job_id,
        'represented_date': represented_date,
        'data_through': data_through,
        'availability_reference_date': availability_date,
        'board': board,
        'team_package': team_package,
        'team_evidence': team_evidence,
        'method_versions': versions,
        'canonical_mutation_fingerprint': canonical_mutation_fingerprint,
        'is_correction': bool(
            change.get('classification') == 'corrected_observation'
            or change.get('reason') == 'bounded_canonical_correction_recheck'
        ),
    }


def _build_continuous_publication(
    *, team_id, sequence, predecessor, cohort_id, sources, generated_at,
) -> TeamPublicPublication:
    publication_id = _continuous_publication_id(team_id, cohort_id)
    semantic_board_source = deepcopy(sources['board'])
    semantic_board_source.pop('publication_authority', None)
    semantic_board_source.pop('served_from', None)
    canonical_fingerprints = {
        'canonical_mutation': sources['canonical_mutation_fingerprint'],
        'team_board': _digest(semantic_board_source),
        'team_evidence': _digest(sources['team_evidence']),
        'team_package': _digest(sources['team_package']),
    }
    payload = {
        'contract': PAYLOAD_CONTRACT,
        'schema_version': PAYLOAD_SCHEMA_VERSION,
        'identity': {
            'authority_version': AUTHORITY_VERSION,
            'publication_id': publication_id,
            'team_id': team_id,
            'source_type': TeamPublicPublication.SOURCE_CONTINUOUS_TEAM,
            'sequence': sequence,
            'predecessor_publication_id': (
                predecessor.publication_id if predecessor is not None else None
            ),
            'cohort_id': cohort_id,
            'source_dashboard_snapshot_id': None,
            'source_sync_run_id': sources['source_sync_run_id'],
            'represented_date': _iso(sources['represented_date']),
            'data_through': _iso(sources['data_through']),
            'availability_reference_date': _iso(
                sources['availability_reference_date']
            ),
            'generated_at': _iso(generated_at),
            'source_published_at': _iso(generated_at),
            'payload_schema_version': PAYLOAD_SCHEMA_VERSION,
        },
        'team': deepcopy(_mapping(sources['board'].get('team'))),
        'team_board': _semantic_continuous_board(
            sources['board'], publication_id
        ),
        'team_package': deepcopy(sources['team_package']),
        'continuous_source': {
            'contract': CONTINUOUS_SOURCE_CONTRACT,
            'game_pk': sources['game_pk'],
            'observation_fingerprint': sources['observation_fingerprint'],
            'observation_authority': sources['observation_authority'],
            'source_revision': sources['source_revision'],
            'source_sync_run_id': sources['source_sync_run_id'],
            'work_job_id': sources['work_job_id'],
            'canonical_mutation_fingerprint': sources[
                'canonical_mutation_fingerprint'
            ],
        },
        'continuous_evidence': deepcopy(sources['team_evidence']),
        'continuous_equivalence': {
            'contract': CONTINUOUS_EQUIVALENCE_CONTRACT,
            'status': 'equivalent',
            'team_board_digest': canonical_fingerprints['team_board'],
            'team_evidence_digest': canonical_fingerprints['team_evidence'],
            'team_package_digest': canonical_fingerprints['team_package'],
        },
        'comparison_material': {
            'contract': 'team_publication_comparison_material_v1',
            'team_state': deepcopy(sources['team_evidence']['team_state']),
            'active_pitcher_ids': deepcopy(
                sources['team_evidence']['active_pitcher_ids']
            ),
            'affected_pitcher_ids': deepcopy(
                sources['team_evidence']['affected_pitcher_ids']
            ),
            'workload_rest': deepcopy(
                sources['team_evidence']['workload_rest']
            ),
            'roster_authority': deepcopy(
                sources['team_evidence']['roster_authority']
            ),
            'method_versions': deepcopy(sources['method_versions']),
        },
        'what_changed': None,
        'method_versions': deepcopy(sources['method_versions']),
        'canonical_fingerprints': deepcopy(canonical_fingerprints),
        'trust': {
            'status': TeamPublicPublication.TRUST_TRUSTED,
            'completeness': TeamPublicPublication.COMPLETENESS_COMPLETE,
            'equivalence_status': 'equivalent',
        },
        'source_game_pks': [sources['game_pk']],
        'source_observation_fingerprints': [sources['observation_fingerprint']],
        'limitations': [
            'shadow_only_not_current_public_authority',
            'team_what_changed_not_authored',
        ],
        'unsupported_domains': [
            'public_team_board_serving',
            'team_what_changed_serving',
            'share_artifact_convergence',
        ],
    }
    publication = TeamPublicPublication(
        publication_id=publication_id,
        authority_version=AUTHORITY_VERSION,
        team_id=team_id,
        source_type=TeamPublicPublication.SOURCE_CONTINUOUS_TEAM,
        sequence=sequence,
        predecessor_publication_id=(predecessor.id if predecessor else None),
        cohort_id=cohort_id,
        represented_date=sources['represented_date'],
        data_through=sources['data_through'],
        availability_reference_date=sources['availability_reference_date'],
        generated_at=generated_at,
        source_published_at=generated_at,
        source_sync_run_id=sources['source_sync_run_id'],
        source_dashboard_snapshot_id=None,
        source_game_pks=[sources['game_pk']],
        source_observation_fingerprints=[sources['observation_fingerprint']],
        payload_schema_version=PAYLOAD_SCHEMA_VERSION,
        method_versions=sources['method_versions'],
        canonical_fingerprints=canonical_fingerprints,
        trust_status=TeamPublicPublication.TRUST_TRUSTED,
        completeness_status=TeamPublicPublication.COMPLETENESS_COMPLETE,
        is_correction=sources['is_correction'],
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
        source = _mapping(payload.get('continuous_source'))
        evidence = _mapping(payload.get('continuous_evidence'))
        equivalence = _mapping(payload.get('continuous_equivalence'))
        game_pk = _positive_int(source.get('game_pk'))
        observation_fingerprint = _sha256(
            source.get('observation_fingerprint')
        )
        canonical_mutation_fingerprint = _sha256(
            source.get('canonical_mutation_fingerprint')
        )
        expected_cohort = (
            continuous_cohort_id(
                game_pk=game_pk,
                observation_fingerprint=observation_fingerprint,
                canonical_mutation_fingerprint=canonical_mutation_fingerprint,
                represented_date=publication.represented_date,
            )
            if game_pk and observation_fingerprint and canonical_mutation_fingerprint
            else None
        )
        source_board = deepcopy(_mapping(payload.get('team_board')))
        source_board.pop('publication_authority', None)
        source_board.pop('served_from', None)
        evidence_fingerprint = _digest(evidence)
        team_package = _mapping(payload.get('team_package'))
        team_package_fingerprint = _digest(team_package)
        if (
            publication.source_dashboard_snapshot_id is not None
            or game_pk is None
            or publication.source_game_pks != [game_pk]
            or observation_fingerprint is None
            or publication.source_observation_fingerprints
            != [observation_fingerprint]
            or source.get('contract') != CONTINUOUS_SOURCE_CONTRACT
            or source.get('source_sync_run_id') != publication.source_sync_run_id
            or _positive_int(source.get('work_job_id')) is None
            or not str(source.get('observation_authority') or '').strip()
            or not str(source.get('source_revision') or '').strip()
            or canonical_mutation_fingerprint is None
            or publication.cohort_id != expected_cohort
            or publication.publication_id
            != _continuous_publication_id(publication.team_id, publication.cohort_id)
            or equivalence.get('contract') != CONTINUOUS_EQUIVALENCE_CONTRACT
            or equivalence.get('status') != 'equivalent'
            or equivalence.get('team_board_digest') != _digest(source_board)
            or equivalence.get('team_evidence_digest') != evidence_fingerprint
            or publication.canonical_fingerprints.get('canonical_mutation')
            != canonical_mutation_fingerprint
            or publication.canonical_fingerprints.get('team_board')
            != equivalence.get('team_board_digest')
            or publication.canonical_fingerprints.get('team_evidence')
            != evidence_fingerprint
            or equivalence.get('team_package_digest')
            != team_package_fingerprint
            or publication.canonical_fingerprints.get('team_package')
            != team_package_fingerprint
            or _board_team_id(payload.get('team_board')) != publication.team_id
            or _positive_int(_mapping(team_package.get('team')).get('team_id'))
            != publication.team_id
            or _mapping(team_package.get('roster_authority'))
            != _mapping(payload.get('continuous_evidence')).get('roster_authority')
            or _mapping(payload.get('trust')).get('equivalence_status')
            != 'equivalent'
        ):
            raise TeamPublicationError('team_publication_source_identity_mismatch')

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
        latest = (
            session.query(TeamPublicPublication)
            .filter(TeamPublicPublication.team_id == pointer.team_id)
            .order_by(TeamPublicPublication.sequence.desc())
            .first()
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
        latest_digest_valid = False
        latest_equivalence_status = None
        if latest is not None:
            try:
                validate_publication(latest, session=session)
                latest_digest_valid = True
            except TeamPublicationError as exc:
                invalid.append({
                    'team_id': pointer.team_id,
                    'publication_id': latest.publication_id,
                    'reason': str(exc),
                })
            latest_equivalence_status = _mapping(
                _mapping(latest.payload).get('continuous_equivalence')
            ).get('status')
        teams.append({
            'team_id': pointer.team_id,
            'publication_id': check.get('publication_id'),
            'sequence': pointer.sequence,
            'current_sequence': pointer.sequence,
            'source_type': getattr(publication, 'source_type', None),
            'cohort_id': getattr(publication, 'cohort_id', None),
            'source_dashboard_snapshot_id': getattr(
                publication, 'source_dashboard_snapshot_id', None
            ),
            'source_sync_run_id': getattr(publication, 'source_sync_run_id', None),
            'data_through': _iso(getattr(publication, 'data_through', None)),
            'digest_valid': digest_valid,
            'predecessor_valid': predecessor_valid,
            'latest_publication_id': getattr(latest, 'publication_id', None),
            'latest_sequence': getattr(latest, 'sequence', None),
            'latest_source_type': getattr(latest, 'source_type', None),
            'latest_source_game_pk': (
                (latest.source_game_pks or [None])[0] if latest is not None else None
            ),
            'latest_digest_valid': latest_digest_valid,
            'latest_equivalence_status': latest_equivalence_status,
            'shadow_ahead': bool(
                latest is not None and latest.sequence > pointer.sequence
            ),
            'sequence_gap': (
                latest.sequence - pointer.sequence if latest is not None else None
            ),
        })
    present = {row['team_id'] for row in teams}
    return {
        'event': 'team_publication_storage_status',
        'status': 'valid' if not invalid and len(present) == 30 else 'invalid',
        'teams_expected': len(EXPECTED_TEAM_IDS),
        'current_pointer_count': len(pointers),
        'cohort_count': len(cohorts),
        'mixed_current_cohorts': len(cohorts) > 1,
        'shadow_ahead_count': sum(bool(row['shadow_ahead']) for row in teams),
        'missing_team_ids': sorted(set(EXPECTED_TEAM_IDS) - present),
        'invalid': invalid,
        'teams': teams,
    }


__all__ = [
    'AUTHORITY_VERSION',
    'COHORT_CONTRACT',
    'CONTINUOUS_COHORT_CONTRACT',
    'CONTINUOUS_EQUIVALENCE_CONTRACT',
    'CONTINUOUS_SOURCE_CONTRACT',
    'EXPECTED_TEAM_IDS',
    'PAYLOAD_CONTRACT',
    'PAYLOAD_SCHEMA_VERSION',
    'TeamPublicationAuthoringResult',
    'ContinuousTeamPublicationAuthoringResult',
    'TeamPublicationConflict',
    'TeamPublicationError',
    'advance_pointer_compare_and_set',
    'author_league_dashboard_team_publications',
    'author_continuous_team_publications_shadow',
    'bootstrap_current_trusted_dashboard',
    'canonical_json',
    'compute_package_digest',
    'continuous_cohort_id',
    'inspect_team_publication_storage',
    'league_cohort_id',
    'validate_pointer',
    'validate_publication',
    'validate_current_team_publication_cohort',
]
