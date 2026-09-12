from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from threading import Barrier

import pytest
from flask import Flask
from sqlalchemy import event

from models.atomic_publication import (
    AtomicPublication,
    AtomicPublicationArtifact,
    AtomicPublicationCacheHandoff,
    AtomicPublicationCurrent,
)
from models.canonical_impact import CanonicalImpactPlan
from models.derived_intelligence import DerivedCohortSnapshot, DerivedIntelligenceCohort
from models.sync_job import SyncJob
from services.atomic_publication import (
    PublicationStaleError,
    PublicationValidationError,
    get_current_publication,
    handoff_publication_cache,
    publish_derived_cohort,
    read_current_publication_bundle,
    run_atomic_publication_worker_once,
)
from services.atomic_publication_reads import (
    _database_artifact_reader,
    publication_reader_coverage,
    resolve_atomic_read_context,
)
from services.sync_jobs import JobScopeType, JobType, enqueue_job
from services.mlb_club_directory import MLB_TEAM_IDS
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


GAME_DATE = date(2026, 9, 9)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


@pytest.fixture
def storage_app(app, monkeypatch):
    """Isolate legacy SP-11 storage/race unit fixtures from reader admission.

    These deliberately contain internal-only payloads. The real admission path
    is exercised without this stub by reader-ready, R3, and full-chain tests.
    """
    monkeypatch.setattr(
        'services.atomic_publication._validate_reader_artifact_coverage',
        lambda *_args, **_kwargs: None,
    )
    return app


def _cohort(*, marker, authority='final', teams=(110,), pitchers=(10,), games=(777123,),
            completed=('game_context', 'pitcher_snapshot', 'team_snapshot'), status='complete'):
    plan = CanonicalImpactPlan(
        plan_fingerprint=(marker * 64)[:64], rules_version='canonical-impact-v1',
        authority_class=authority, baseball_date=GAME_DATE,
        correlation_id=f'publication-{marker}', affected_game_ids_json=list(games),
        affected_team_ids_json=list(teams), affected_pitcher_ids_json=list(pitchers),
        affected_domains_json=list(completed), source_observation_ids_json=[],
        status='dispatched', supersedes_live=False,
    )
    db.session.add(plan)
    db.session.flush()
    cohort = DerivedIntelligenceCohort(
        impact_plan_id=plan.id, cohort_fingerprint=(marker.upper() * 64)[:64],
        schema_version='derived-cohort-v1', authority_class=authority,
        baseball_date=GAME_DATE, correlation_id=plan.correlation_id, status=status,
        requested_domains_json=list(completed), execution_domains_json=list(completed),
        completed_domains_json=list(completed), withheld_domains_json=[],
        affected_game_ids_json=list(games), affected_team_ids_json=list(teams),
        affected_pitcher_ids_json=list(pitchers), input_manifest_json=[],
        method_versions_json={domain: 'test-v1' for domain in completed},
        completed_at=datetime(2026, 9, 9, 12, 0),
    )
    db.session.add(cohort)
    db.session.flush()
    for team_id in teams if 'team_snapshot' in completed else ():
        _snapshot(cohort, 'team', team_id, {'team_snapshot': {'marker': marker}})
    for pitcher_id in pitchers if 'pitcher_snapshot' in completed else ():
        _snapshot(cohort, 'pitcher', pitcher_id, {'pitcher_snapshot': {'marker': marker}})
    for game_pk in games if 'game_context' in completed else ():
        _snapshot(cohort, 'game', game_pk, {'game_context': {'marker': marker}})
    db.session.commit()
    return plan, cohort


def _snapshot(cohort, entity_type, entity_key, payload, *, snapshot_type=None):
    db.session.add(DerivedCohortSnapshot(
        cohort_id=cohort.id, entity_type=entity_type, entity_key=str(entity_key),
        snapshot_type=snapshot_type or f'{entity_type}_intelligence', baseball_date=GAME_DATE,
        authority_class=cohort.authority_class, payload_schema_version=1,
        payload_json=payload,
    ))


def test_first_publication_is_immutable_generation_and_advances_pointer(storage_app):
    _plan, cohort = _cohort(marker='a')
    result = publish_derived_cohort(cohort.id)
    assert result.created is True
    assert result.pointer_advanced is True
    assert result.publication.status == 'published'
    assert result.publication.predecessor_publication_id is None
    assert result.publication.artifact_created_count == 3
    assert result.publication.artifact_inherited_count == 0
    assert db.session.get(AtomicPublicationCurrent, 1).publication_id == result.publication.id
    assert result.cache_handoff.status == 'not_configured'
    bundle = read_current_publication_bundle()
    assert bundle['publication_id'] == result.publication.id
    assert {row['publication_id'] for row in bundle['artifacts']} == {result.publication.id}


def test_reader_coverage_rejects_internal_only_publication_artifacts(storage_app):
    _plan, cohort = _cohort(marker='z')
    publication = publish_derived_cohort(cohort.id).publication

    coverage = publication_reader_coverage(publication.id)

    assert coverage['complete'] is False
    assert coverage['ready_counts']['pitcher_current'] == 0
    assert coverage['ready_counts']['team_board_v2'] == 0
    assert coverage['ready_counts']['what_changed'] == 0


def _reader_payload(entity_type, entity_key, marker):
    if entity_type == 'team':
        return {
            'read_models': {
                'team_board': {'team_id': entity_key, 'marker': marker},
                'team_board_v2': {
                    'full': {
                        'team_id': entity_key, 'marker': marker,
                        'active_bullpen': {'arms': [{'pitcher_id': 10}]},
                    },
                    'core': {'team_id': entity_key, 'marker': marker},
                    'details': {'team_id': entity_key, 'marker': marker},
                },
                'league_row': {'team_id': entity_key, 'marker': marker},
            },
            'what_changed': {'team_id': entity_key, 'marker': marker},
        }
    if entity_type == 'pitcher':
        return {'read_models': {'pitcher_current': {'pitcher_id': entity_key, 'marker': marker}}}
    return {'read_models': {'matchup': {'game_pk': entity_key, 'marker': marker}}}


def test_reader_ready_method_requires_complete_coverage_before_pointer_switch(app):
    _plan, incomplete = _cohort(marker='y')
    incomplete.method_versions_json = {
        **incomplete.method_versions_json,
        'read_models': 'cu06-publication-artifacts-v2',
    }
    db.session.commit()

    with pytest.raises(PublicationValidationError, match='team_coverage_incomplete'):
        publish_derived_cohort(incomplete.id)
    assert db.session.get(AtomicPublicationCurrent, 1) is None

    _plan, complete = _cohort(
        marker='x', teams=tuple(MLB_TEAM_IDS), pitchers=(10,), games=(777123,),
    )
    complete.method_versions_json = {
        **complete.method_versions_json,
        'read_models': 'cu06-publication-artifacts-v2',
    }
    for snapshot in DerivedCohortSnapshot.query.filter_by(cohort_id=complete.id):
        payload = _reader_payload(snapshot.entity_type, int(snapshot.entity_key), 'x')
        if snapshot.entity_type == 'team':
            snapshot.payload_json = {'read_models': {
                'team_board': payload['read_models']['team_board'],
                'league_row': payload['read_models']['league_row'],
            }}
            _snapshot(complete, 'team', snapshot.entity_key, {
                'read_models': {'team_board_v2': payload['read_models']['team_board_v2']},
            }, snapshot_type='team_board_v2_publication')
            _snapshot(complete, 'team', snapshot.entity_key, {
                'what_changed': payload['what_changed'],
            }, snapshot_type='what_changed_publication')
        elif snapshot.entity_type == 'pitcher':
            snapshot.payload_json = {'pitcher_snapshot': {'marker': 'x'}}
            _snapshot(
                complete, 'pitcher', snapshot.entity_key, payload,
                snapshot_type='pitcher_current_publication',
            )
        else:
            snapshot.payload_json = payload
    db.session.commit()

    result = publish_derived_cohort(complete.id)
    coverage = publication_reader_coverage(result.publication.id)
    assert result.pointer_advanced is True
    assert coverage['complete'] is True
    assert coverage['ready_counts']['team_board_v2'] == 30
    assert coverage['ready_counts']['what_changed'] == 30
    assert coverage['ready_counts']['pitcher_current'] == 1

    statements = []
    event.listen(
        db.engine, 'before_cursor_execute',
        lambda _conn, _cursor, statement, _params, _context, _many: statements.append(statement),
    )
    rows = _database_artifact_reader.read_many(
        result.publication.id, 'team', tuple(map(str, MLB_TEAM_IDS)),
        'team_intelligence',
    )
    assert len(rows) == 30
    assert len(statements) == 2


def test_same_cohort_retry_is_idempotent(storage_app):
    _plan, cohort = _cohort(marker='b')
    first = publish_derived_cohort(cohort.id)
    second = publish_derived_cohort(cohort.id)
    assert second.created is False
    assert second.publication.id == first.publication.id
    assert AtomicPublication.query.count() == 1
    assert AtomicPublicationArtifact.query.count() == 3


def test_corrected_generation_replaces_affected_and_inherits_unaffected(storage_app):
    _plan, first_cohort = _cohort(marker='c', teams=(110, 111), pitchers=(), games=(), completed=('team_snapshot',))
    first = publish_derived_cohort(first_cohort.id)
    _plan, corrected = _cohort(
        marker='d', authority='corrected_final', teams=(110,), pitchers=(), games=(),
        completed=('team_snapshot',),
    )
    second = publish_derived_cohort(corrected.id)
    assert second.publication.predecessor_publication_id == first.publication.id
    assert first.publication.status == 'superseded'
    assert second.publication.artifact_created_count == 1
    assert second.publication.artifact_inherited_count == 1
    rows = AtomicPublicationArtifact.query.filter_by(publication_id=second.publication.id).all()
    by_team = {row.entity_key: row for row in rows}
    assert by_team['110'].source_cohort_id == corrected.id
    assert by_team['110'].source_snapshot_id is not None
    assert by_team['111'].source_cohort_id == first_cohort.id
    assert by_team['111'].inherited_from_artifact_id is not None
    bundle = read_current_publication_bundle()
    assert {row['payload']['team_snapshot']['marker'] for row in bundle['artifacts']} == {'c', 'd'}


def test_roster_and_pregame_publications_keep_bounded_artifact_scope(storage_app):
    _plan, roster = _cohort(
        marker='v', authority='roster_authoritative', teams=(110,),
        pitchers=(), games=(), completed=('team_snapshot',),
    )
    roster_publication = publish_derived_cohort(roster.id).publication
    assert {
        (row.entity_type, row.entity_key)
        for row in AtomicPublicationArtifact.query.filter_by(
            publication_id=roster_publication.id,
        )
    } == {('team', '110')}

    _plan, pregame = _cohort(
        marker='w', authority='pregame_authoritative', teams=(),
        pitchers=(), games=(777123,), completed=('game_context',),
    )
    pregame_publication = publish_derived_cohort(pregame.id).publication
    rows = AtomicPublicationArtifact.query.filter_by(publication_id=pregame_publication.id).all()
    current = {(row.entity_type, row.entity_key): row for row in rows}
    assert current[('game', '777123')].source_cohort_id == pregame.id
    assert current[('team', '110')].source_cohort_id == roster.id


@pytest.mark.parametrize(('status', 'reason'), (('partial', 'cohort_not_complete'), ('stale', 'cohort_not_complete')))
def test_ineligible_cohort_cannot_move_pointer(storage_app, status, reason):
    _plan, current = _cohort(marker='e')
    current_publication = publish_derived_cohort(current.id).publication
    _plan, invalid = _cohort(marker=status[0], status=status)
    with pytest.raises(PublicationValidationError, match=reason):
        publish_derived_cohort(invalid.id)
    assert get_current_publication().id == current_publication.id


def test_input_drift_or_superseded_plan_cannot_publish(storage_app):
    plan, cohort = _cohort(marker='f')
    plan.status = 'superseded'
    db.session.commit()
    with pytest.raises(PublicationStaleError, match='impact_plan_superseded'):
        publish_derived_cohort(cohort.id)
    assert get_current_publication() is None


def test_older_overlapping_cohort_cannot_regress_newer_artifact(storage_app):
    _old_plan, old = _cohort(marker='g', teams=(110,), pitchers=(), games=(), completed=('team_snapshot',))
    _new_plan, new = _cohort(marker='h', teams=(110,), pitchers=(), games=(), completed=('team_snapshot',))
    publish_derived_cohort(new.id)
    with pytest.raises(PublicationStaleError, match='candidate_older_than_current_artifact'):
        publish_derived_cohort(old.id)
    assert get_current_publication().cohort_id == new.id


def test_failure_before_pointer_commit_rolls_back_generation(storage_app):
    _plan, first = _cohort(marker='i')
    current = publish_derived_cohort(first.id).publication
    _plan, candidate = _cohort(marker='j')

    def fail(point, _publication):
        if point == 'before_commit':
            raise RuntimeError('simulated crash')

    with pytest.raises(RuntimeError, match='simulated crash'):
        publish_derived_cohort(candidate.id, failure_hook=fail)
    db.session.rollback()
    assert get_current_publication().id == current.id
    assert AtomicPublication.query.count() == 1


def test_artifact_validation_failure_does_not_switch_pointer(storage_app):
    _plan, current_cohort = _cohort(marker='r')
    current = publish_derived_cohort(current_cohort.id).publication
    _plan, invalid = _cohort(marker='s')
    snapshot = DerivedCohortSnapshot.query.filter_by(cohort_id=invalid.id).first()
    snapshot.payload_json = {}
    db.session.commit()
    with pytest.raises(PublicationValidationError, match='artifact_payload_invalid'):
        publish_derived_cohort(invalid.id)
    assert get_current_publication().id == current.id


def test_invalid_current_artifact_falls_back_to_one_predecessor_generation(storage_app):
    _plan, first_cohort = _cohort(marker='t')
    first = publish_derived_cohort(first_cohort.id).publication
    _plan, second_cohort = _cohort(marker='u')
    second = publish_derived_cohort(second_cohort.id).publication
    current_artifact = AtomicPublicationArtifact.query.filter_by(
        publication_id=second.id,
    ).first()
    source = db.session.get(DerivedCohortSnapshot, current_artifact.source_snapshot_id)
    source.payload_json = {'tampered': True}
    db.session.commit()
    bundle = read_current_publication_bundle()
    assert bundle['publication_id'] == first.id
    assert bundle['degraded_from_publication_id'] == second.id
    assert bundle['fallback_reason'] == 'current_artifact_unavailable'
    assert {row['publication_id'] for row in bundle['artifacts']} == {first.id}


class RecordingCache:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def handoff(self, publication_id, bundle, keys):
        self.calls.append((publication_id, bundle, keys))
        if self.fail:
            raise RuntimeError('cache unavailable')


def test_cache_failure_does_not_rollback_publication_and_retry_converges(storage_app):
    _plan, cohort = _cohort(marker='k')
    published = publish_derived_cohort(cohort.id, cache_configured=True)
    assert get_current_publication().id == published.publication.id
    cache = RecordingCache(fail=True)
    with pytest.raises(RuntimeError, match='cache unavailable'):
        handoff_publication_cache(published.publication.id, cache)
    assert get_current_publication().id == published.publication.id
    handoff = AtomicPublicationCacheHandoff.query.filter_by(publication_id=published.publication.id).one()
    assert handoff.status == 'retry_wait'
    cache.fail = False
    handoff_publication_cache(published.publication.id, cache)
    assert handoff.status == 'complete'
    assert handoff.attempt_count == 2


def test_cache_handoff_job_is_versioned_and_retryable(storage_app):
    _plan, cohort = _cohort(marker='n')
    published = publish_derived_cohort(cohort.id, cache_configured=True)
    cache_job = SyncJob.query.filter_by(job_name='handoff_publication_cache').one()
    assert cache_job.details_json['publication_id'] == published.publication.id
    assert all(str(published.publication.id) in key for key in published.cache_handoff.cache_keys_json)
    settled = run_atomic_publication_worker_once('sp11-cache-worker', cache_adapter=RecordingCache())
    assert settled.status == 'succeeded'
    assert settled.result_json['cache_handoff_status'] == 'complete'


def test_stale_worker_fence_prevents_pointer_transition(storage_app):
    _plan, cohort = _cohort(marker='o')
    calls = {'count': 0}

    def fence():
        calls['count'] += 1
        if calls['count'] == 3:
            raise RuntimeError('lease lost')

    with pytest.raises(RuntimeError, match='lease lost'):
        publish_derived_cohort(cohort.id, lease_fence=fence)
    db.session.rollback()
    assert get_current_publication() is None
    assert AtomicPublication.query.count() == 0


def test_one_shot_worker_consumes_sp10_handoff_without_recompute(storage_app):
    _plan, cohort = _cohort(marker='l')
    enqueue_job(
        job_type=JobType.PUBLISH_DERIVED_COHORT,
        scope_type=JobScopeType.BASEBALL_DATE,
        scope_key=GAME_DATE.isoformat(), product_date=GAME_DATE,
        dedupe_key=f'publish-test:{cohort.id}', payload_schema_version=1,
        payload={'cohort_id': cohort.id},
    )
    settled = run_atomic_publication_worker_once('sp11-worker')
    assert settled.status == 'succeeded'
    assert settled.result_json['publication_id'] == get_current_publication().id
    assert get_current_publication().sync_run_id is not None


def test_concurrent_same_cohort_creates_one_publication_postgresql(storage_app):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL publication concurrency contract')
    _plan, cohort = _cohort(marker='m')
    cohort_id = cohort.id
    barrier = Barrier(2)

    def publish(_index):
        with storage_app.app_context():
            barrier.wait(timeout=10)
            result = publish_derived_cohort(cohort_id)
            publication_id = result.publication.id
            db.session.remove()
            return publication_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(publish, (0, 1)))
    with storage_app.app_context():
        assert ids[0] == ids[1]
        assert AtomicPublication.query.count() == 1
        assert AtomicPublicationCurrent.query.count() == 1
        assert {row['publication_id'] for row in read_current_publication_bundle()['artifacts']} == {ids[0]}


def test_concurrent_distinct_cohorts_serialize_and_newer_wins_postgresql(storage_app):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL pointer-ordering contract')
    _plan, older = _cohort(marker='p', teams=(110,), pitchers=(), games=(), completed=('team_snapshot',))
    _plan, newer = _cohort(marker='q', teams=(110,), pitchers=(), games=(), completed=('team_snapshot',))
    ids = (older.id, newer.id)
    barrier = Barrier(2)

    def publish(cohort_id):
        with storage_app.app_context():
            barrier.wait(timeout=10)
            try:
                result = publish_derived_cohort(cohort_id)
                value = ('published', result.publication.id)
            except PublicationStaleError:
                db.session.rollback()
                value = ('stale', None)
            db.session.remove()
            return value

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(publish, ids))
    with storage_app.app_context():
        assert get_current_publication().cohort_id == newer.id
        assert sum(outcome[0] == 'published' for outcome in outcomes) >= 1
        assert {row['publication_id'] for row in read_current_publication_bundle()['artifacts']} == {
            get_current_publication().id,
        }


def test_team_board_request_stays_on_frozen_generation_postgresql(storage_app):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL request-generation race contract')
    _plan, first_cohort = _cohort(
        marker='x', teams=(110,), pitchers=(), games=(),
        completed=('team_snapshot',),
    )
    first_snapshot = DerivedCohortSnapshot.query.filter_by(
        cohort_id=first_cohort.id, entity_type='team', entity_key='110',
    ).one()
    first_snapshot.payload_json = {'read_models': {
        'team_board': {'team': {'team_id': 110}, 'marker': 'N'},
        'league_row': {'team_id': 110, 'marker': 'N'},
    }}
    db.session.commit()
    first = publish_derived_cohort(first_cohort.id).publication
    frozen = resolve_atomic_read_context(
        env={'SYNC_PIPELINE_ATOMIC_READS_ENABLED': 'true'},
    )

    _plan, second_cohort = _cohort(
        marker='y', teams=(110,), pitchers=(), games=(),
        completed=('team_snapshot',),
    )
    second_snapshot = DerivedCohortSnapshot.query.filter_by(
        cohort_id=second_cohort.id, entity_type='team', entity_key='110',
    ).one()
    second_snapshot.payload_json = {'read_models': {
        'team_board': {'team': {'team_id': 110}, 'marker': 'N+1'},
        'league_row': {'team_id': 110, 'marker': 'N+1'},
    }}
    db.session.commit()
    second = publish_derived_cohort(second_cohort.id).publication

    assert first.id != second.id
    assert get_current_publication().id == second.id
    assert frozen.publication_id == first.id
    assert frozen.team_board(110)['marker'] == 'N'
    assert frozen.league((110,))['teams'][0]['marker'] == 'N'


def test_public_reader_families_stay_on_frozen_generation_postgresql(storage_app):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL specialized reader-generation race contract')

    def cohort_with_artifacts(marker):
        _plan, cohort = _cohort(
            marker=marker, teams=(110,), pitchers=(10,), games=(),
            completed=('team_snapshot', 'pitcher_snapshot'),
        )
        team = DerivedCohortSnapshot.query.filter_by(
            cohort_id=cohort.id, snapshot_type='team_intelligence',
        ).one()
        team.payload_json = {'read_models': {
            'team_board': {'marker': marker}, 'league_row': {'marker': marker},
        }}
        pitcher = DerivedCohortSnapshot.query.filter_by(
            cohort_id=cohort.id, snapshot_type='pitcher_intelligence',
        ).one()
        pitcher.payload_json = {'pitcher_snapshot': {'marker': marker}}
        _snapshot(cohort, 'team', 110, {'read_models': {'team_board_v2': {
            'full': {'marker': marker}, 'core': {}, 'details': {},
        }}}, snapshot_type='team_board_v2_publication')
        _snapshot(
            cohort, 'team', 110, {'what_changed': {'marker': marker}},
            snapshot_type='what_changed_publication',
        )
        _snapshot(cohort, 'pitcher', 10, {'read_models': {
            'pitcher_current': {'marker': marker},
        }}, snapshot_type='pitcher_current_publication')
        db.session.commit()
        return cohort

    first = publish_derived_cohort(cohort_with_artifacts('r').id).publication
    frozen = resolve_atomic_read_context(
        env={'SYNC_PIPELINE_ATOMIC_READS_ENABLED': 'true'},
    )
    second = publish_derived_cohort(cohort_with_artifacts('s').id).publication

    assert get_current_publication().id == second.id
    assert frozen.publication_id == first.id
    assert frozen.team_board_v2(110)['marker'] == 'r'
    assert frozen.pitcher(10)['marker'] == 'r'
    assert frozen.what_changed(110)['marker'] == 'r'


@pytest.mark.parametrize('method', [None, 'depth-v1', 'cu06-publication-artifacts-v2'])
def test_r3_incomplete_candidate_never_bypasses_reader_gate(app, method):
    _plan, cohort = _cohort(marker='r3-invalid')
    if method:
        cohort.method_versions_json = {**cohort.method_versions_json, 'read_models': method}
        db.session.commit()
    for _attempt in range(2):
        with pytest.raises(PublicationValidationError, match='team_coverage_incomplete'):
            publish_derived_cohort(cohort.id)
        assert AtomicPublication.query.count() == 0
        assert db.session.get(AtomicPublicationCurrent, 1) is None


def test_r3_candidate_report_rejects_internal_only_without_writes(app):
    from services.atomic_publication_cutover import inspect_publication_cohort
    _plan, cohort = _cohort(marker='r3-report')
    report = inspect_publication_cohort(cohort.id)['cohort']
    assert report['eligible'] is False
    assert 'team_coverage_incomplete' in report['ineligible_reason']
    assert AtomicPublication.query.count() == 0
    assert db.session.get(AtomicPublicationCurrent, 1) is None


def test_r3_affected_game_requires_its_own_matchup(app):
    _plan, cohort = _cohort(marker='r3-game', teams=tuple(MLB_TEAM_IDS), games=(1, 2))
    for snapshot in DerivedCohortSnapshot.query.filter_by(cohort_id=cohort.id):
        snapshot.payload_json = _reader_payload(snapshot.entity_type, int(snapshot.entity_key), 'ready')
        if snapshot.entity_type == 'game' and snapshot.entity_key == '2':
            snapshot.payload_json = {'read_models': {'context_version_id': 20,
                'home_probable_pitcher_id': None, 'away_probable_pitcher_id': None}}
    db.session.commit()
    with pytest.raises(PublicationValidationError, match='game_coverage_incomplete'):
        publish_derived_cohort(cohort.id)
    assert db.session.get(AtomicPublicationCurrent, 1) is None


def _reader_ready_cohort(marker, *, games=(777123,)):
    _plan, cohort = _cohort(marker=marker, teams=tuple(MLB_TEAM_IDS), games=games)
    for snapshot in DerivedCohortSnapshot.query.filter_by(cohort_id=cohort.id).all():
        payload = _reader_payload(snapshot.entity_type, int(snapshot.entity_key), marker)
        if snapshot.entity_type == 'team':
            snapshot.payload_json = {'read_models': {
                'team_board': payload['read_models']['team_board'],
                'league_row': payload['read_models']['league_row'],
            }}
            _snapshot(cohort, 'team', snapshot.entity_key, {
                'read_models': {'team_board_v2': payload['read_models']['team_board_v2']},
            }, snapshot_type='team_board_v2_publication')
            _snapshot(cohort, 'team', snapshot.entity_key, {
                'what_changed': payload['what_changed'],
            }, snapshot_type='what_changed_publication')
        elif snapshot.entity_type == 'pitcher':
            _snapshot(cohort, 'pitcher', snapshot.entity_key, payload,
                      snapshot_type='pitcher_current_publication')
        else:
            snapshot.payload_json = payload
    db.session.commit()
    return cohort


def test_r3_complete_generation_without_marker_and_retry_are_valid(app):
    from services.atomic_publication_cutover import inspect_publication_cohort
    cohort = _reader_ready_cohort('r3-valid')
    assert inspect_publication_cohort(cohort.id)['cohort']['eligible'] is True
    first = publish_derived_cohort(cohort.id)
    retry = publish_derived_cohort(cohort.id)
    assert first.pointer_advanced is True
    assert retry.created is False
    assert retry.publication.id == first.publication.id
    assert publication_reader_coverage(first.publication.id)['complete'] is True
    assert AtomicPublication.query.count() == 1


def test_r3_inherited_other_game_cannot_hide_partial_pregame_contract(app):
    from services.atomic_publication_cutover import inspect_publication_cohort
    first = publish_derived_cohort(_reader_ready_cohort('r3-parent').id)
    _plan, candidate = _cohort(marker='r3-pregame', authority='pregame_authoritative',
                              teams=(), pitchers=(), games=(888,), completed=('game_context',))
    snapshot = DerivedCohortSnapshot.query.filter_by(cohort_id=candidate.id).one()
    snapshot.payload_json = {'read_models': {'context_version_id': 20,
        'home_probable_pitcher_id': None, 'away_probable_pitcher_id': None}}
    db.session.commit()
    report = inspect_publication_cohort(candidate.id)['cohort']
    assert report['eligible'] is False
    assert report['ineligible_reason'] == 'publication_reader_game_coverage_incomplete'
    for _attempt in range(2):
        with pytest.raises(PublicationValidationError, match='game_coverage_incomplete'):
            publish_derived_cohort(candidate.id)
        assert get_current_publication().id == first.publication.id
        assert AtomicPublication.query.count() == 1
    assert snapshot.payload_json['read_models']['home_probable_pitcher_id'] is None


def test_r3_historical_incomplete_game_coverage_is_rejected_on_read(storage_app):
    # Deliberately model an immutable generation admitted by the pre-R3 gate.
    cohort = _reader_ready_cohort('r3-historical', games=(1, 2))
    bad = DerivedCohortSnapshot.query.filter_by(cohort_id=cohort.id,
                                               entity_type='game', entity_key='2').one()
    bad.payload_json = {'read_models': {'context_version_id': 20}}
    db.session.commit()
    publication = publish_derived_cohort(cohort.id).publication
    coverage = publication_reader_coverage(publication.id)
    assert coverage['complete'] is False
    assert coverage['required_counts']['games'] == 2
    assert coverage['missing_game_ids'] == ['2']
    assert bad.payload_json == {'read_models': {'context_version_id': 20}}


def test_r3_real_admission_concurrent_retry_and_request_freeze_postgresql(app):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL pointer serialization')
    first = publish_derived_cohort(_reader_ready_cohort('r3-race-first').id)
    frozen = resolve_atomic_read_context(env={'SYNC_PIPELINE_ATOMIC_READS_ENABLED': 'true'})
    candidate_id = _reader_ready_cohort('r3-race-next').id
    barrier = Barrier(2)
    def publish():
        with app.app_context():
            try:
                barrier.wait(timeout=10)
                return publish_derived_cohort(candidate_id).publication.id
            finally:
                db.session.remove()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _value: publish(), range(2)))
    db.session.expire_all()
    assert len(set(results)) == 1
    assert AtomicPublication.query.count() == 2
    assert get_current_publication().id == results[0]
    assert frozen.publication_id == first.publication.id
    assert frozen.team_board_v2(110)['marker'] == 'r3-race-first'
    assert frozen.what_changed(110)['marker'] == 'r3-race-first'


def test_r3_candidate_coverage_batches_direct_snapshots(app):
    from services.atomic_publication import validated_publication_artifacts
    cohort = _reader_ready_cohort('r3-batch')
    statements = []
    def capture(_conn, _cursor, statement, _params, _context, _many):
        if 'FROM derived_cohort_snapshots' in statement:
            statements.append(statement)
    event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        specs, inherited = validated_publication_artifacts(cohort)
    finally:
        event.remove(db.engine, 'before_cursor_execute', capture)
    assert len(specs) == 93
    assert inherited == []
    assert len(statements) == 2


def test_r3_first_baseline_report_requires_public_pitcher_family(app):
    from services.atomic_publication import first_publication_baseline_report
    cohort = _reader_ready_cohort('r3-baseline')
    DerivedCohortSnapshot.query.filter_by(
        cohort_id=cohort.id, snapshot_type='pitcher_current_publication',
    ).delete()
    db.session.commit()
    report = first_publication_baseline_report(cohort)
    assert report['complete'] is False
    assert report['reason'] == 'publication_reader_pitcher_coverage_incomplete'
    assert db.session.get(AtomicPublicationCurrent, 1) is None
