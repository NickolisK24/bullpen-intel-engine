"""D-058 dormant storage, league bootstrap, and continuous shadow proof."""

from copy import deepcopy
from datetime import date, datetime, timedelta
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
from sqlalchemy.exc import IntegrityError

from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from models.team_publication import TeamPublicCurrentPointer, TeamPublicPublication
from models.team_state_publication_proof import TeamStatePublicationProof
from services.mlb_club_directory import MLB_CLUBS, MLB_TEAM_IDS
from services.public_serving_authority import (
    TEAM_BOARD_PACKAGE_CONTRACT,
    TEAM_BOARD_PACKAGE_KEY,
)
from services.team_publication_storage import (
    AUTHORITY_VERSION,
    CONTINUOUS_COHORT_CONTRACT,
    PAYLOAD_CONTRACT,
    TeamPublicationConflict,
    TeamPublicationError,
    advance_pointer_compare_and_set,
    author_continuous_team_publications_shadow,
    author_league_dashboard_team_publications,
    bootstrap_current_trusted_dashboard,
    canonical_json,
    compute_package_digest,
    inspect_team_publication_storage,
    validate_current_team_publication_cohort,
    validate_pointer,
    validate_publication,
)
from services.snapshot_read_guard import SnapshotReadUnavailable
import services.team_publication_storage as publication_storage
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


DATA_THROUGH = date(2026, 9, 3)
REFERENCE_DATE = date(2026, 9, 4)
GENERATED_AT = datetime(2026, 9, 4, 10, 0, 0)
PUBLISHED_AT = datetime(2026, 9, 4, 10, 1, 0)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _authority(method):
    return {'method_version': method}


def _team_board(club):
    return {
        'team': {
            'team_id': club.team_id,
            'team_name': club.team_name,
            'team_abbreviation': club.abbreviation,
        },
        'records': [{
            'pitcher_id': club.team_id * 10,
            'name': f'{club.abbreviation} Reliever',
            'workload_facts': {'pitches_last_7_days': 24},
            'last_appearance': {
                'game_pk': 800000 + club.team_id,
                'game_date': DATA_THROUGH.isoformat(),
            },
            'availability': {'status': 'available'},
        }],
        'default_pitcher_ids': [club.team_id * 10],
        'bullpen_membership_authority': _authority('membership-v1'),
        'roster_authority': {
            'contract': 'roster_authority_v1',
            'team_id': club.team_id,
            'reference_date': REFERENCE_DATE.isoformat(),
        },
        'workload_concentration': {'team_id': club.team_id, 'share': 0.42},
        'workload_windows': {'data_through': DATA_THROUGH.isoformat()},
        'workload_windows_authority': _authority('workload-v1'),
        'deployment_profile': {'data_through': DATA_THROUGH.isoformat()},
        'deployment_profile_authority': _authority('deployment-v1'),
        'rest_status': {'rested_arm_count': 5},
        'rest_status_authority': _authority('rest-v1'),
        'capacity_intelligence': {'team_id': club.team_id},
        'rotation_support_pressure': {'reference_date': DATA_THROUGH.isoformat()},
        'rotation_support_pressure_authority': _authority('rotation-v1'),
        'bullpen_stability': {'status': 'stable'},
        'bullpen_environment': {'status': 'normal'},
    }


def _proof_team(club):
    return {
        'team_id': club.team_id,
        'team_abbreviation': club.abbreviation,
        'team_name': club.team_name,
        'outcome': 'publication_candidate',
        'method_version_matches_expected': True,
        'contract_a_reproduction': {'reproduced': True},
        'partition_invariant_state': 'evaluated',
        'partition_invariant_holds': True,
        'evidence_complete': True,
        'reference_date_alignment': {'aligned': True},
        'final_team_state': {
            'published_public_state': 'Fresh',
            'readiness_status_code': 'operationally_stable',
            'public_state_matches_status_code': True,
        },
        'team_state_evidence': {
            'contract': 'team_state_contract_a',
            'method_version': 'v3_phase_5',
            'active_pitcher_count': 8,
            'decisive_rule': 'fresh_coverage',
        },
        'limitations': [],
    }


def _source(*, data_through=DATA_THROUGH, generated_at=GENERATED_AT,
            published_at=PUBLISHED_AT, publish=True):
    run = SyncRun(
        job_name='daily_sync',
        status='success',
        stage='complete',
        source='test',
        latest_game_date=data_through,
        latest_workload_date=data_through,
    )
    db.session.add(run)
    db.session.flush()
    board_by_team = {
        str(club.team_id): _team_board(club)
        for club in MLB_CLUBS
    }
    change_by_team = {
        str(club.team_id): {
            'team_id': club.team_id,
            'status': 'available',
            'changes': [],
        }
        for club in MLB_CLUBS
    }
    snapshot = DashboardSnapshot(
        snapshot_type='bullpen_dashboard',
        sync_run_id=run.id,
        status='ready',
        is_published=publish,
        published_at=published_at if publish else None,
        payload={
            'freshness': {
                'data_through': data_through.isoformat(),
                'availability_reference_date': (
                    data_through + timedelta(days=1)
                ).isoformat(),
                'slate_coverage': {
                    'slate_date': data_through.isoformat(),
                    'validations_passed': True,
                    'complete_enough_to_publish': True,
                },
            },
            TEAM_BOARD_PACKAGE_KEY: {
                'contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'generated_at': generated_at.isoformat(),
                'data_through': data_through.isoformat(),
                'availability_reference_date': (
                    data_through + timedelta(days=1)
                ).isoformat(),
                'team_count': 30,
                'by_team_id': board_by_team,
            },
            'what_changed_since_yesterday': {
                'version': '2026-06-19.v1',
                'status': 'available',
                'state': 'no_meaningful_changes',
                'comparison': {
                    'comparison_available': True,
                    'current_data_through': data_through.isoformat(),
                },
                'by_team_id': change_by_team,
            },
        },
        payload_version=1,
        data_through=data_through,
        availability_reference_date=data_through + timedelta(days=1),
        snapshot_generated_at=generated_at,
        source='test',
    )
    db.session.add(snapshot)
    db.session.flush()
    proof = TeamStatePublicationProof(
        snapshot_id=snapshot.id,
        sync_run_id=run.id,
        data_through=data_through,
        proof={
            'contract': 'team_state_vnext_production_proof_v1',
            'schema_version': '1.0.0',
            'publication': {
                'dashboard_snapshot_id': snapshot.id,
                'sync_run_id': run.id,
                'data_through': data_through.isoformat(),
            },
            'teams': [_proof_team(club) for club in MLB_CLUBS],
        },
        overall_verdict='PASS',
        captured_team_count=30,
        method_version='v3_phase_5',
        publication_source='test',
        generated_at=published_at,
    )
    db.session.add(proof)
    db.session.commit()
    return snapshot, proof


def _clone_publication(source, **overrides):
    values = {
        column.name: deepcopy(getattr(source, column.name))
        for column in TeamPublicPublication.__table__.columns
        if column.name not in {'id', 'created_at'}
    }
    values.update(overrides)
    return TeamPublicPublication(**values)


def _continuous_inputs(
    *, game_pk=824424, fingerprint='a' * 64, represented_date=date(2026, 9, 4),
    correction=False,
):
    team_ids = (114, 116)
    pitcher_ids_by_team = {
        114: (1140, 1141, 1142, 1143),
        116: (1160, 1161, 1162),
    }
    pitcher_ids = tuple(
        pitcher_id
        for team_id in team_ids
        for pitcher_id in pitcher_ids_by_team[team_id]
    )
    run = SyncRun(
        job_name='continuous_cycle', status='success', stage='complete',
        source='continuous', latest_game_date=represented_date,
        latest_workload_date=represented_date,
    )
    db.session.add(run)
    db.session.flush()
    boards = {}
    team_packages = {}
    team_states = {}
    workload_by_pitcher = {}
    availability = {}
    arm_reads = {}
    team_workload = {}
    for team_id in team_ids:
        team_pitcher_ids = pitcher_ids_by_team[team_id]
        club = next(club for club in MLB_CLUBS if club.team_id == team_id)
        state = {
            'public_state': 'Fresh',
            'status_code': 'operationally_stable',
            'data_through': represented_date.isoformat(),
        }
        boards[str(team_id)] = {
            'team': {'team_id': team_id, 'team_name': f'Team {team_id}'},
            'groups': [{
                'label': 'Available',
                'pitchers': [
                    {
                        'pitcher_id': pitcher_id,
                        'name': f'Arm {pitcher_id}',
                        'availability_status': 'available',
                        'workload_facts': {'pitches_last_7_days': 30},
                    }
                    for pitcher_id in team_pitcher_ids
                ],
            }],
            'roster_authority': {
                'contract': 'roster_authority_v1',
                'team_id': team_id,
                'reference_date': represented_date.isoformat(),
            },
            'team_state': deepcopy(state),
            'freshness': {'data_through': represented_date.isoformat()},
            'publication_method_versions': {
                'bullpen_membership': 'membership-v1',
                'rest_status': 'rest-v1',
                'workload_windows': 'workload-v1',
                'deployment_profile': 'deployment-v1',
                'rotation_impact': 'rotation-v1',
            },
            'publication_authority': {'dashboard_snapshot_id': 1},
            'served_from': 'trusted_dashboard_snapshot',
        }
        team_package = _team_board(club)
        team_package['records'] = []
        for pitcher_id in team_pitcher_ids:
            team_package['records'].append({
                'pitcher_id': pitcher_id,
                'name': f'Arm {pitcher_id}',
                'workload_facts': {'pitches_last_7_days': 30},
                'last_appearance': {
                    'game_pk': game_pk,
                    'game_date': represented_date.isoformat(),
                },
                'availability': {'status': 'available'},
            })
        team_package['default_pitcher_ids'] = list(team_pitcher_ids)
        team_package['workload_windows']['data_through'] = (
            represented_date.isoformat()
        )
        team_package['roster_authority'] = deepcopy(
            boards[str(team_id)]['roster_authority']
        )
        team_packages[str(team_id)] = team_package
        team_states[str(team_id)] = {
            'public_team_state': deepcopy(state),
            'team_state_evidence': {'method_version': 'v3_phase_5'},
        }
        for pitcher_id in team_pitcher_ids:
            workload_by_pitcher[str(pitcher_id)] = {
                'fatigue_workload': {'pitches_last_7_days': 30},
                'rest_workload_inputs': {'days_rest': 0},
            }
            availability[str(pitcher_id)] = {'availability_status': 'available'}
            arm_reads[str(pitcher_id)] = {
                'pitcher_id': pitcher_id,
                'read': 'Fresh',
            }
        team_workload[str(team_id)] = {
            'team_id': team_id, 'data_through': represented_date.isoformat(),
        }
    change = {
        'game_pk': game_pk,
        'current_observation_identity': fingerprint,
        'source_authority': 'mlb_live_feed',
        'source_observed_at': f'{represented_date.isoformat()}T22:10:00Z',
        'classification': 'corrected_observation' if correction else 'game_changed',
        'reason': 'completed_game_correction_recheck' if correction else 'game_changed',
    }
    impact = {
        'game_pk': game_pk,
        'canonical_mutation_performed': True,
        'canonical_source_revision': f'{represented_date.isoformat()}T22:10:00Z',
        'affected_pitcher_ids': list(pitcher_ids),
        'affected_team_ids': list(team_ids),
        'game_log_inserted': 9,
        'pitch_inserted': 300,
        'optional_pbp_status': 'complete',
    }
    workload = {
        'game_pk': game_pk, 'status': 'complete', 'parity_status': 'match',
        'data_through': represented_date.isoformat(),
        'availability_reference_date': represented_date.isoformat(),
        'pitchers_recomputed': list(pitcher_ids),
        'teams_recomputed': list(team_ids),
        'pitcher_results': deepcopy(workload_by_pitcher),
        'team_results': deepcopy(team_workload),
    }
    team_state = {
        'game_pk': game_pk, 'status': 'complete', 'parity_status': 'match',
        'data_through': represented_date.isoformat(),
        'availability_reference_date': represented_date.isoformat(),
        'arm_reads_recomputed': list(pitcher_ids),
        'teams_recomputed': list(team_ids),
        'team_state_results': team_states,
        'workload_rest_pitcher_results': workload_by_pitcher,
        'workload_rest_team_results': team_workload,
        'availability_results': availability,
        'arm_read_results': arm_reads,
    }
    read_models = {
        'game_pk': game_pk, 'status': 'complete', 'parity_status': 'match',
        'represented_date': represented_date.isoformat(),
        'requested_team_ids': list(team_ids),
        'team_boards_rebuilt': list(team_ids),
        'team_board_results': boards,
        'team_package_results': team_packages,
        'rebuild_performed': True,
    }
    return run, change, impact, workload, team_state, read_models


def _author_continuous(inputs, *, work_job_id=245):
    run, change, impact, workload, team_state, read_models = inputs
    return author_continuous_team_publications_shadow(
        change=change,
        canonical_impact=impact,
        workload_result=workload,
        team_state_result=team_state,
        read_model_result=read_models,
        source_sync_run_id=run.id,
        work_job_id=work_job_id,
    )


def test_continuous_shadow_authors_two_team_cohort_without_pointer_movement(app):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    before = {
        row.team_id: (row.current_publication_id, row.sequence)
        for row in TeamPublicCurrentPointer.query.filter(
            TeamPublicCurrentPointer.team_id.in_((114, 116))
        ).all()
    }

    result = _author_continuous(_continuous_inputs())

    assert result.to_dict() == {
        'event': 'team_publication_shadow',
        'status': 'complete',
        'game_pk': 824424,
        'source_sync_run_id': result.source_sync_run_id,
        'work_job_id': 245,
        'affected_team_ids': [114, 116],
        'cohort_id': result.cohort_id,
        'packages_attempted': 2,
        'packages_created': 2,
        'packages_reused': 0,
        'equivalent': 2,
        'validation_failures': 0,
        'equivalence_failures': 0,
        'pointers_advanced': 0,
        'publication_ids': list(result.publication_ids),
    }
    rows = TeamPublicPublication.query.filter_by(
        source_type=TeamPublicPublication.SOURCE_CONTINUOUS_TEAM
    ).order_by(TeamPublicPublication.team_id).all()
    assert [(row.team_id, row.sequence) for row in rows] == [(114, 2), (116, 2)]
    assert {row.cohort_id for row in rows} == {result.cohort_id}
    assert all(row.predecessor_publication_id is not None for row in rows)
    assert all(row.source_dashboard_snapshot_id is None for row in rows)
    assert all(row.source_game_pks == [824424] for row in rows)
    assert all(validate_publication(row)['valid'] for row in rows)
    after = {
        row.team_id: (row.current_publication_id, row.sequence)
        for row in TeamPublicCurrentPointer.query.filter(
            TeamPublicCurrentPointer.team_id.in_((114, 116))
        ).all()
    }
    assert after == before


def test_continuous_shadow_retry_reuses_rows_without_sequence_inflation(app):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    inputs = _continuous_inputs()
    first = _author_continuous(inputs)
    inputs[3]['pitcher_recomputation_ms'] = 99.1
    inputs[4]['team_state_recomputation_ms'] = 88.2
    inputs[5]['rebuild_ms'] = 77.3
    second = _author_continuous(inputs)

    assert first.publication_ids == second.publication_ids
    assert second.packages_created == 0
    assert second.packages_reused == 2
    assert TeamPublicPublication.query.filter_by(
        source_type=TeamPublicPublication.SOURCE_CONTINUOUS_TEAM
    ).count() == 2
    assert {
        row.sequence for row in TeamPublicPublication.query.filter_by(
            source_type=TeamPublicPublication.SOURCE_CONTINUOUS_TEAM
        ).all()
    } == {2}


def test_continuous_shadow_atomic_commit_recovers_after_precommit_crash(app):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    inputs = _continuous_inputs()
    run, change, impact, workload, team_state, read_models = inputs
    result = author_continuous_team_publications_shadow(
        change=change, canonical_impact=impact, workload_result=workload,
        team_state_result=team_state, read_model_result=read_models,
        source_sync_run_id=run.id, work_job_id=245, commit=False,
    )
    assert result.packages_created == 2
    assert TeamPublicPublication.query.filter_by(
        source_type=TeamPublicPublication.SOURCE_CONTINUOUS_TEAM
    ).count() == 2
    db.session.rollback()
    assert TeamPublicPublication.query.filter_by(
        source_type=TeamPublicPublication.SOURCE_CONTINUOUS_TEAM
    ).count() == 0

    recovered = _author_continuous(inputs)

    assert recovered.packages_created == 2
    assert TeamPublicPublication.query.filter_by(
        source_type=TeamPublicPublication.SOURCE_CONTINUOUS_TEAM
    ).count() == 2
    assert all(
        pointer.sequence == 1
        for pointer in TeamPublicCurrentPointer.query.filter(
            TeamPublicCurrentPointer.team_id.in_((114, 116))
        ).all()
    )


def test_continuous_shadow_equivalence_failure_is_atomic(app):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    inputs = list(_continuous_inputs())
    inputs[5]['team_board_results']['116']['team_state']['public_state'] = 'Stretched'

    with pytest.raises(
        TeamPublicationError,
        match='team_publication_continuous_equivalence_invalid:116',
    ):
        _author_continuous(tuple(inputs))

    assert TeamPublicPublication.query.filter_by(
        source_type=TeamPublicPublication.SOURCE_CONTINUOUS_TEAM
    ).count() == 0
    assert TeamPublicCurrentPointer.query.filter(
        TeamPublicCurrentPointer.team_id.in_((114, 116)),
        TeamPublicCurrentPointer.sequence != 1,
    ).count() == 0


@pytest.mark.parametrize('domain', ('workload', 'roster', 'method_version'))
def test_continuous_shadow_fails_closed_on_incoherent_required_domain(app, domain):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    inputs = list(_continuous_inputs())
    board = inputs[5]['team_board_results']['116']
    if domain == 'workload':
        board['groups'][0]['pitchers'][0]['workload_facts'][
            'pitches_last_7_days'
        ] = 99
    elif domain == 'roster':
        board['roster_authority']['team_id'] = 114
    else:
        del board['publication_method_versions']['workload_windows']

    with pytest.raises(TeamPublicationError):
        _author_continuous(tuple(inputs))

    assert TeamPublicPublication.query.filter_by(
        source_type=TeamPublicPublication.SOURCE_CONTINUOUS_TEAM
    ).count() == 0


def test_continuous_shadow_lineage_extends_latest_immutable_and_corrections(app):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    first = _author_continuous(_continuous_inputs())
    second_inputs = _continuous_inputs(
        game_pk=824717, fingerprint='b' * 64,
    )
    second = _author_continuous(second_inputs, work_job_id=246)
    correction_inputs = _continuous_inputs(
        game_pk=824717, fingerprint='c' * 64, correction=True,
    )
    correction = _author_continuous(correction_inputs, work_job_id=247)

    assert first.cohort_id != second.cohort_id != correction.cohort_id
    for team_id in (114, 116):
        rows = TeamPublicPublication.query.filter_by(team_id=team_id).order_by(
            TeamPublicPublication.sequence
        ).all()
        assert [row.sequence for row in rows] == [1, 2, 3, 4]
        assert rows[2].predecessor_publication_id == rows[1].id
        assert rows[3].predecessor_publication_id == rows[2].id
        assert rows[3].is_correction is True
        pointer = db.session.get(TeamPublicCurrentPointer, team_id)
        assert pointer.sequence == 1


def test_continuous_shadow_digest_tampering_and_observability(app):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    result = _author_continuous(_continuous_inputs())
    status = inspect_team_publication_storage()
    cle = next(item for item in status['teams'] if item['team_id'] == 114)
    assert cle == {
        **cle,
        'current_sequence': 1,
        'latest_sequence': 2,
        'latest_source_type': TeamPublicPublication.SOURCE_CONTINUOUS_TEAM,
        'latest_source_game_pk': 824424,
        'latest_digest_valid': True,
        'latest_equivalence_status': 'equivalent',
        'shadow_ahead': True,
        'sequence_gap': 1,
    }
    row = TeamPublicPublication.query.filter_by(
        publication_id=result.publication_ids[0]
    ).one()
    db.session.expunge(row)
    tampered = _clone_publication(row)
    tampered.payload['continuous_evidence']['team_state']['public_team_state'][
        'public_state'
    ] = 'Vulnerable'
    with pytest.raises(TeamPublicationError):
        validate_publication(tampered)


def test_bootstrap_authors_exact_30_team_cohort_and_equivalent_payloads(app):
    snapshot, _proof = _source()
    result = author_league_dashboard_team_publications(snapshot)

    assert result.to_dict() == {
        'event': 'team_publication_bootstrap',
        'status': 'complete',
        'source_snapshot_id': snapshot.id,
        'source_sync_run_id': snapshot.sync_run_id,
        'cohort_id': result.cohort_id,
        'teams_expected': 30,
        'packages_created': 30,
        'packages_reused': 0,
        'pointers_advanced': 30,
        'pointers_unchanged': 0,
        'validation_failures': 0,
    }
    rows = TeamPublicPublication.query.order_by(TeamPublicPublication.team_id).all()
    pointers = TeamPublicCurrentPointer.query.order_by(
        TeamPublicCurrentPointer.team_id
    ).all()
    assert len(rows) == len(pointers) == 30
    assert {row.cohort_id for row in rows} == {result.cohort_id}
    assert {row.source_dashboard_snapshot_id for row in rows} == {snapshot.id}
    assert {row.source_sync_run_id for row in rows} == {snapshot.sync_run_id}
    assert {row.sequence for row in rows} == {1}
    assert all(row.predecessor_publication_id is None for row in rows)
    assert len({row.package_digest for row in rows}) == 30
    assert all(validate_publication(row)['valid'] for row in rows)
    assert all(validate_pointer(pointer)['valid'] for pointer in pointers)
    assert validate_current_team_publication_cohort() == {
        'valid': True,
        'team_count': 30,
        'cohort_id': result.cohort_id,
        'source_dashboard_snapshot_id': snapshot.id,
        'source_sync_run_id': snapshot.sync_run_id,
    }

    cle = next(row for row in rows if row.team_id == 114)
    source_cle = snapshot.payload[TEAM_BOARD_PACKAGE_KEY]['by_team_id']['114']
    assert cle.payload['team_board'] == source_cle
    assert cle.payload['team'] == source_cle['team']
    assert cle.payload['team_state_publication_proof']['final_team_state'][
        'published_public_state'
    ] == 'Fresh'
    assert cle.payload['team_state_publication_proof']['team_state_evidence'][
        'decisive_rule'
    ] == 'fresh_coverage'
    assert cle.payload['what_changed']['team']['team_id'] == 114
    assert cle.payload['contract'] == PAYLOAD_CONTRACT
    assert cle.authority_version == AUTHORITY_VERSION


def test_authoring_is_idempotent_and_digest_is_deterministic(app):
    snapshot, _proof = _source()
    first = author_league_dashboard_team_publications(snapshot)
    before = {
        row.team_id: (row.id, row.sequence, row.package_digest)
        for row in TeamPublicPublication.query.all()
    }
    second = author_league_dashboard_team_publications(snapshot)
    after = {
        row.team_id: (row.id, row.sequence, row.package_digest)
        for row in TeamPublicPublication.query.all()
    }

    assert first.packages_created == 30
    assert second.packages_created == 0
    assert second.packages_reused == 30
    assert second.pointers_advanced == 0
    assert second.pointers_unchanged == 30
    assert before == after
    assert TeamPublicPublication.query.count() == 30


def test_canonical_json_and_digest_change_only_with_meaning(app):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    row = TeamPublicPublication.query.first()
    assert canonical_json({'b': 2, 'a': 1}) == canonical_json({'a': 1, 'b': 2})
    assert compute_package_digest(row) == row.package_digest

    row.payload = {**row.payload, 'meaningful_test_value': 1}
    assert compute_package_digest(row) != row.package_digest
    with pytest.raises(TeamPublicationError, match='digest_mismatch'):
        validate_publication(row)
    db.session.rollback()


def test_source_snapshot_fingerprint_mismatch_fails_integrity_validation(app):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    row = TeamPublicPublication.query.filter_by(team_id=114).one()
    payload = deepcopy(snapshot.payload)
    payload[TEAM_BOARD_PACKAGE_KEY]['by_team_id']['114']['rest_status'] = {
        'rested_arm_count': 4,
    }
    snapshot.payload = payload
    db.session.commit()

    with pytest.raises(TeamPublicationError, match='source_identity_mismatch'):
        validate_publication(row)


def test_invalid_source_type_duplicate_sequence_and_duplicate_source_are_rejected(app):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    source = TeamPublicPublication.query.order_by(TeamPublicPublication.team_id).first()

    invalid = _clone_publication(
        source,
        publication_id='f' * 64,
        team_id=999,
        source_type='invented',
        source_dashboard_snapshot_id=None,
    )
    db.session.add(invalid)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    duplicate_sequence = _clone_publication(
        source,
        publication_id='e' * 64,
        source_dashboard_snapshot_id=None,
        source_type=TeamPublicPublication.SOURCE_CONTINUOUS_TEAM,
    )
    db.session.add(duplicate_sequence)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    duplicate_source = _clone_publication(
        source,
        publication_id='d' * 64,
        sequence=2,
        predecessor_publication_id=source.id,
    )
    db.session.add(duplicate_source)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_pointer_uniqueness_and_cross_team_pointer_validation(app):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    source = TeamPublicPublication.query.filter_by(team_id=108).one()
    pointer = TeamPublicCurrentPointer.query.filter_by(team_id=109).one()
    original = pointer.current_publication_id
    pointer.current_publication_id = source.id
    pointer.sequence = source.sequence
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    assert TeamPublicCurrentPointer.query.filter_by(team_id=109).one().current_publication_id == original


def test_immutable_publication_rejects_update_and_delete(app):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    row = TeamPublicPublication.query.first()
    row.trust_status = 'trusted'
    row.payload = {**row.payload, 'mutated': True}
    with pytest.raises(ValueError, match='immutable'):
        db.session.commit()
    db.session.rollback()

    row = TeamPublicPublication.query.first()
    db.session.delete(row)
    with pytest.raises(ValueError, match='immutable'):
        db.session.commit()
    db.session.rollback()


def test_one_invalid_team_rolls_back_all_30_packages_and_pointers(app):
    snapshot, _proof = _source()
    payload = deepcopy(snapshot.payload)
    del payload[TEAM_BOARD_PACKAGE_KEY]['by_team_id']['147'][
        'rest_status_authority'
    ]['method_version']
    snapshot.payload = payload
    db.session.commit()

    with pytest.raises(TeamPublicationError, match='method_version_missing'):
        author_league_dashboard_team_publications(snapshot)
    assert TeamPublicPublication.query.count() == 0
    assert TeamPublicCurrentPointer.query.count() == 0


def test_pointer_activation_failure_rolls_back_packages_and_prior_pointer_moves(
    app, monkeypatch
):
    snapshot, _proof = _source()
    real_advance = publication_storage.advance_pointer_compare_and_set
    calls = {'count': 0}

    def fail_during_activation(*args, **kwargs):
        calls['count'] += 1
        if calls['count'] == 16:
            raise TeamPublicationConflict('injected_pointer_activation_failure')
        return real_advance(*args, **kwargs)

    monkeypatch.setattr(
        publication_storage,
        'advance_pointer_compare_and_set',
        fail_during_activation,
    )
    with pytest.raises(TeamPublicationConflict, match='injected'):
        author_league_dashboard_team_publications(snapshot)
    assert TeamPublicPublication.query.count() == 0
    assert TeamPublicCurrentPointer.query.count() == 0


def test_second_league_publication_advances_all_lineages_coherently(app):
    first_snapshot, _proof = _source()
    first = author_league_dashboard_team_publications(first_snapshot)
    first_ids = {
        row.team_id: row.id for row in TeamPublicPublication.query.all()
    }
    first_snapshot.is_published = False
    db.session.commit()
    second_snapshot, _proof = _source(
        data_through=DATA_THROUGH + timedelta(days=1),
        generated_at=GENERATED_AT + timedelta(days=1),
        published_at=PUBLISHED_AT + timedelta(days=1),
    )

    second = author_league_dashboard_team_publications(second_snapshot)
    current = TeamPublicCurrentPointer.query.all()
    latest = {
        row.team_id: db.session.get(TeamPublicPublication, row.current_publication_id)
        for row in current
    }
    assert first.cohort_id != second.cohort_id
    assert second.packages_created == second.pointers_advanced == 30
    assert TeamPublicPublication.query.count() == 60
    assert {row.sequence for row in latest.values()} == {2}
    assert {
        team_id: row.predecessor_publication_id for team_id, row in latest.items()
    } == first_ids
    assert {row.cohort_id for row in latest.values()} == {second.cohort_id}


def test_pointer_compare_and_set_rejects_wrong_expected_predecessor(app):
    first_snapshot, _proof = _source()
    author_league_dashboard_team_publications(first_snapshot)
    first_ids = {
        row.team_id: row.id for row in TeamPublicPublication.query.all()
    }
    first_snapshot.is_published = False
    db.session.commit()
    second_snapshot, _proof = _source(
        data_through=DATA_THROUGH + timedelta(days=1),
        generated_at=GENERATED_AT + timedelta(days=1),
        published_at=PUBLISHED_AT + timedelta(days=1),
    )
    author_league_dashboard_team_publications(second_snapshot)
    candidate = TeamPublicPublication.query.filter_by(
        team_id=108, source_dashboard_snapshot_id=second_snapshot.id
    ).one()
    pointer = TeamPublicCurrentPointer.query.filter_by(team_id=108).one()
    pointer.current_publication_id = first_ids[108]
    pointer.sequence = 1
    pointer.authority_generation = 1
    db.session.commit()

    with pytest.raises(TeamPublicationConflict, match='compare_and_set_failed'):
        advance_pointer_compare_and_set(
            candidate, expected_publication_id=999999
        )
    db.session.rollback()


def test_bootstrap_recovers_preinserted_packages_without_duplicate_rows(app):
    snapshot, _proof = _source()
    first = author_league_dashboard_team_publications(snapshot)
    TeamPublicCurrentPointer.query.delete()
    db.session.commit()

    recovered = author_league_dashboard_team_publications(snapshot)
    assert first.packages_created == 30
    assert recovered.packages_created == 0
    assert recovered.packages_reused == 30
    assert recovered.pointers_advanced == 30
    assert TeamPublicPublication.query.count() == 30
    assert TeamPublicCurrentPointer.query.count() == 30


def test_bootstrap_recovers_partial_preinserted_package_set(app):
    snapshot, _proof = _source()
    author_league_dashboard_team_publications(snapshot)
    keep = set(MLB_TEAM_IDS[:10])
    db.session.execute(sa.delete(TeamPublicCurrentPointer))
    db.session.execute(
        sa.delete(TeamPublicPublication).where(
            TeamPublicPublication.team_id.notin_(keep)
        )
    )
    db.session.commit()

    recovered = author_league_dashboard_team_publications(snapshot)
    assert recovered.packages_created == 20
    assert recovered.packages_reused == 10
    assert recovered.pointers_advanced == 30
    assert TeamPublicPublication.query.count() == 30
    assert validate_current_team_publication_cohort()['valid'] is True


def test_bootstrap_resolver_and_observability_are_bounded(app, monkeypatch):
    snapshot, _proof = _source()
    monkeypatch.setattr(
        'services.team_publication_storage.dashboard_snapshot_service.'
        'get_latest_dashboard_snapshot_guarded',
        lambda: snapshot,
    )
    result = bootstrap_current_trusted_dashboard()
    status = inspect_team_publication_storage()
    assert result.packages_created == 30
    assert status['status'] == 'valid'
    assert status['current_pointer_count'] == 30
    assert status['cohort_count'] == 1
    assert status['mixed_current_cohorts'] is False
    assert status['missing_team_ids'] == []
    assert status['invalid'] == []
    assert len(status['teams']) == 30
    assert all(team['digest_valid'] for team in status['teams'])


@pytest.mark.parametrize('resolved', [None, SnapshotReadUnavailable('x', 'y', 1)])
def test_bootstrap_refuses_missing_or_failed_trusted_dashboard(app, monkeypatch, resolved):
    def resolver():
        if isinstance(resolved, Exception):
            raise resolved
        return resolved

    monkeypatch.setattr(
        'services.team_publication_storage.dashboard_snapshot_service.'
        'get_latest_dashboard_snapshot_guarded',
        resolver,
    )
    with pytest.raises(
        TeamPublicationError, match='current_dashboard_unavailable'
    ):
        bootstrap_current_trusted_dashboard()


def test_missing_proof_source_identity_and_partial_population_fail_closed(app):
    snapshot, proof = _source()
    db.session.delete(proof)
    db.session.commit()
    with pytest.raises(TeamPublicationError, match='proof_missing'):
        author_league_dashboard_team_publications(snapshot)
    assert TeamPublicPublication.query.count() == 0

    wrong_run = SyncRun(
        job_name='daily_sync',
        status='success',
        stage='complete',
        source='test-wrong-source',
        latest_game_date=snapshot.data_through,
        latest_workload_date=snapshot.data_through,
    )
    db.session.add(wrong_run)
    db.session.flush()
    proof = TeamStatePublicationProof(
        snapshot_id=snapshot.id,
        sync_run_id=wrong_run.id,
        data_through=snapshot.data_through,
        proof={
            'contract': 'team_state_vnext_production_proof_v1',
            'schema_version': '1.0.0',
            'publication': {
                'dashboard_snapshot_id': snapshot.id,
                'sync_run_id': wrong_run.id,
                'data_through': snapshot.data_through.isoformat(),
            },
            'teams': [_proof_team(club) for club in MLB_CLUBS],
        },
        overall_verdict='PASS',
        captured_team_count=30,
        method_version='v3_phase_5',
        generated_at=PUBLISHED_AT,
    )
    db.session.add(proof)
    db.session.commit()
    with pytest.raises(TeamPublicationError, match='proof_identity_invalid'):
        author_league_dashboard_team_publications(snapshot)
    assert TeamPublicCurrentPointer.query.count() == 0

    proof.sync_run_id = snapshot.sync_run_id
    proof.proof = {
        **proof.proof,
        'publication': {
            **proof.proof['publication'],
            'sync_run_id': snapshot.sync_run_id,
        },
    }
    payload = deepcopy(snapshot.payload)
    payload[TEAM_BOARD_PACKAGE_KEY]['by_team_id'].pop('158')
    payload[TEAM_BOARD_PACKAGE_KEY]['team_count'] = 29
    snapshot.payload = payload
    db.session.commit()
    with pytest.raises(TeamPublicationError, match='team_package_invalid'):
        author_league_dashboard_team_publications(snapshot)


def test_existing_team_board_and_share_readers_do_not_import_new_authority():
    root = Path(__file__).resolve().parents[1]
    readers = (
        root / 'api' / 'team_board_v2.py',
        root / 'services' / 'public_serving_authority.py',
        root / 'services' / 'team_board_delivery.py',
    )
    for path in readers:
        source = path.read_text(encoding='utf-8')
        assert 'models.team_publication' not in source
        assert 'team_publication_storage' not in source
    progressive = (root / 'services' / 'team_progressive_publication.py').read_text(
        encoding='utf-8'
    )
    assert 'models.team_publication' not in progressive
    assert 'team_publication_storage' not in progressive
    for relative in (
        ('services', 'dashboard_snapshot.py'),
        ('scripts', 'run_continuous_cycle.py'),
        ('scripts', 'render_start.sh'),
    ):
        source = root.joinpath(*relative).read_text(encoding='utf-8')
        assert 'bootstrap_team_publications' not in source
        assert 'team_publication_storage' not in source


def test_migration_round_trip_and_constraints():
    path = (
        Path(__file__).resolve().parents[1]
        / 'migrations' / 'versions'
        / 'e8a4c2f9b1d6_add_team_public_publications.py'
    )
    spec = importlib.util.spec_from_file_location('team_publication_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(sa.text(
            'CREATE TABLE sync_runs (id INTEGER PRIMARY KEY)'
        ))
        connection.execute(sa.text(
            'CREATE TABLE dashboard_snapshots (id INTEGER PRIMARY KEY)'
        ))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = sa.inspect(connection)
        assert {
            'team_public_publications', 'team_public_current_pointers'
        } <= set(inspector.get_table_names())
        publication_uniques = {
            tuple(item['column_names'])
            for item in inspector.get_unique_constraints('team_public_publications')
        }
        assert ('team_id', 'sequence') in publication_uniques
        assert (
            'team_id', 'source_type', 'source_dashboard_snapshot_id'
        ) in publication_uniques
        migration.downgrade()
        assert 'team_public_publications' not in sa.inspect(connection).get_table_names()
