"""D-058 Package 1 dormant storage, authoring, and isolation proof."""

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
    PAYLOAD_CONTRACT,
    TeamPublicationConflict,
    TeamPublicationError,
    advance_pointer_compare_and_set,
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

    proof = TeamStatePublicationProof(
        snapshot_id=snapshot.id,
        sync_run_id=snapshot.sync_run_id + 99,
        data_through=snapshot.data_through,
        proof={
            'contract': 'team_state_vnext_production_proof_v1',
            'schema_version': '1.0.0',
            'publication': {
                'dashboard_snapshot_id': snapshot.id,
                'sync_run_id': snapshot.sync_run_id + 99,
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
