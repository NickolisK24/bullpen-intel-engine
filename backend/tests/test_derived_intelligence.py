from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from threading import Barrier

import pytest
from flask import Flask

from models.canonical_impact import CanonicalImpactPlan
from models.derived_intelligence import (
    DerivedCohortInput,
    DerivedCohortSnapshot,
    DerivedIntelligenceCohort,
    DerivedIntelligenceCohortDomain,
)
from models.final_game_reconciliation import FinalGameVersion, FinalPitchingAppearanceVersion
from models.pitcher import Pitcher
from models.pregame_context import GamePregameContextVersion
from models.source_observation import SourceObservation, SourceSubject
from models.sync_job import SyncJob
from services.derived_intelligence import (
    COHORT_SCHEMA_VERSION,
    CohortStatus,
    dependency_closure,
    execute_derived_intelligence_plan,
    run_derived_intelligence_worker_once,
)
from services.sync_jobs import JobScopeType, JobType, enqueue_job
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


GAME_DATE = date(2026, 9, 8)


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


def _plan(*, fingerprint='a' * 64, authority='final', domains=None,
          games=(777123,), teams=(110,), pitchers=(10,)):
    row = CanonicalImpactPlan(
        plan_fingerprint=fingerprint, rules_version='canonical-impact-v1',
        authority_class=authority, baseball_date=GAME_DATE,
        correlation_id='cohort-test', affected_game_ids_json=list(games),
        affected_team_ids_json=list(teams), affected_pitcher_ids_json=list(pitchers),
        affected_domains_json=list(domains or ('workload', 'rest', 'arm_read', 'team_state',
                                               'pitcher_snapshot', 'team_snapshot')),
        source_observation_ids_json=[], status='dispatched', supersedes_live=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _observation(suffix):
    subject = SourceSubject(
        identity_key=(suffix + '-subject').ljust(64, '0')[:64],
        provider='mlb_stats_api', source_domain='boxscore', endpoint='/test',
        subject_type='game', subject_key='game:777123',
        request_identity=(suffix + '-request').ljust(64, '0')[:64],
        request_schema_version=1, request_parameters={}, baseball_date=GAME_DATE,
    )
    db.session.add(subject)
    db.session.flush()
    observation = SourceObservation(
        source_subject_id=subject.id, version_number=1,
        dedupe_key=(suffix + '-dedupe').ljust(64, '0')[:64],
        fingerprint=(suffix + '-fingerprint').ljust(64, '0')[:64],
        fingerprint_algorithm='sha256', fingerprint_version='test-v1',
        payload_schema_version=1, completeness='complete', outcome='new',
        is_change=True, is_authoritative=True, record_count=1,
        observed_at=datetime(2026, 9, 8, 23, 0),
    )
    db.session.add(observation)
    db.session.flush()
    return observation


def _final_authority(observation, *, version, predecessor=None):
    pitcher = Pitcher.query.filter_by(mlb_id=9001).one_or_none()
    if pitcher is None:
        pitcher = Pitcher(
            mlb_id=9001, full_name='Test Pitcher', team_id=110,
            team_name='Team', team_abbreviation='T', active=True,
        )
        db.session.add(pitcher)
        db.session.flush()
    game = FinalGameVersion(
        game_pk=777123, version_number=version,
        predecessor_version_id=predecessor[0].id if predecessor else None,
        baseball_date=GAME_DATE, home_team_id=110, away_team_id=111,
        fact_fingerprint=f'game-{version}'.ljust(64, '0'),
        fingerprint_version='test-v1', core_completeness='complete',
        pbp_completeness='unknown', finality_observation_id=observation.id,
        boxscore_observation_id=observation.id, observed_at=observation.observed_at,
        is_current=True,
    )
    db.session.add(game)
    db.session.flush()
    appearance = FinalPitchingAppearanceVersion(
        final_game_version_id=game.id, game_pk=777123, baseball_date=GAME_DATE,
        pitcher_id=pitcher.id, pitcher_mlb_id=pitcher.mlb_id,
        team_id_at_appearance=110, side='home', appearance_role='reliever',
        version_number=version,
        predecessor_version_id=predecessor[1].id if predecessor else None,
        outs_recorded=3, pitches_thrown=10 + version,
        context_completeness='unknown',
        fact_fingerprint=f'appearance-{version}'.ljust(64, '0'),
        fingerprint_version='test-v1', boxscore_observation_id=observation.id,
        is_current=True,
    )
    db.session.add(appearance)
    db.session.flush()
    return game, appearance, pitcher


class RecordingExecutor:
    def __init__(self, *, fail=()):
        self.calls = []
        self.fail = set(fail)

    def __call__(self, domain, _snapshots):
        self.calls.append(domain)
        if domain in self.fail:
            raise RuntimeError(f'{domain} unavailable')
        return {
            'pitcher': {'10': {domain: {'value': domain}}},
            'team': {'110': {domain: {'value': domain}}},
            'game': {'777123': {domain: {'value': domain}}},
            'summary': {'domain': domain},
        }


def test_dependency_closure_is_ordered_and_pregame_does_not_expand_to_team_state():
    assert dependency_closure(['team_state']) == (
        'roster_composition', 'workload', 'rest', 'concentration',
        'arm_read', 'clean_options', 'team_state',
    )
    assert dependency_closure(['game_context', 'matchup_context', 'read_models']) == (
        'game_context', 'matchup_context', 'read_models',
    )


def test_final_plan_creates_one_coherent_candidate_cohort(app):
    plan = _plan()
    executor = RecordingExecutor()
    result = execute_derived_intelligence_plan(plan.id, domain_executor=executor)

    assert result.created is True
    assert result.cohort.status == CohortStatus.COMPLETE.value
    assert result.cohort.schema_version == COHORT_SCHEMA_VERSION
    assert result.cohort.requested_domains_json == sorted(plan.affected_domains_json)
    assert result.cohort.execution_domains_json == list(dependency_closure(plan.affected_domains_json))
    assert result.cohort.completed_domains_json == list(dependency_closure(plan.affected_domains_json))
    assert result.cohort.withheld_domains_json == []
    assert DerivedIntelligenceCohortDomain.query.filter_by(cohort_id=result.cohort.id).count() == len(executor.calls)
    assert DerivedCohortSnapshot.query.filter_by(cohort_id=result.cohort.id).count() == 3
    assert result.publication_job.job_name == 'publish_derived_cohort'
    assert result.publication_job.details_json['cohort_id'] == result.cohort.id
    assert result.publication_job.details_json['input_manifest'] == result.cohort.input_manifest_json


def test_shadow_execution_can_complete_cohort_without_publication_candidate(app):
    plan = _plan()
    result = execute_derived_intelligence_plan(
        plan.id,
        domain_executor=RecordingExecutor(),
        publication_candidate_enabled=False,
    )

    assert result.cohort.status == CohortStatus.COMPLETE.value
    assert result.publication_job is None
    assert result.cohort.publication_job_id is None
    assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 0


def test_duplicate_exact_plan_input_and_methods_reuses_cohort_and_job(app):
    plan = _plan()
    first = execute_derived_intelligence_plan(plan.id, domain_executor=RecordingExecutor())
    second = execute_derived_intelligence_plan(plan.id, domain_executor=RecordingExecutor())
    assert second.created is False
    assert second.cohort.id == first.cohort.id
    assert second.publication_job.id == first.publication_job.id
    assert DerivedIntelligenceCohort.query.count() == 1
    assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 1


def test_optional_failure_is_isolated_and_dependents_are_withheld(app):
    plan = _plan(domains=('performance', 'team_snapshot', 'what_changed'))
    result = execute_derived_intelligence_plan(
        plan.id, domain_executor=RecordingExecutor(fail=('performance', 'team_snapshot')),
    )
    statuses = {
        row.domain: row.status
        for row in DerivedIntelligenceCohortDomain.query.filter_by(cohort_id=result.cohort.id)
    }
    assert result.cohort.status == CohortStatus.PARTIAL.value
    assert statuses['performance'] == 'failed'
    assert statuses['team_snapshot'] == 'failed'
    assert statuses['what_changed'] == 'withheld'
    assert result.publication_job is None


def test_live_cohort_is_provisional_and_never_dispatched_for_publication(app):
    plan = _plan(
        authority='live', domains=('workload_current', 'team_workload_current', 'game_context'),
    )
    result = execute_derived_intelligence_plan(plan.id, domain_executor=RecordingExecutor())
    assert result.cohort.status == 'complete'
    assert result.cohort.authority_class == 'live'
    assert result.publication_job is None


def test_final_cohort_supersedes_matching_live_and_not_unrelated_live(app):
    live = _plan(
        fingerprint='b' * 64, authority='live', domains=('game_context',), games=(777123,),
    )
    live_result = execute_derived_intelligence_plan(live.id, domain_executor=RecordingExecutor())
    unrelated = _plan(
        fingerprint='c' * 64, authority='live', domains=('game_context',), games=(888888,),
    )
    unrelated_result = execute_derived_intelligence_plan(unrelated.id, domain_executor=RecordingExecutor())
    final = _plan(fingerprint='d' * 64, games=(777123,))
    final_result = execute_derived_intelligence_plan(final.id, domain_executor=RecordingExecutor())
    assert final_result.cohort.supersedes_cohort_id == live_result.cohort.id
    assert final_result.cohort.supersedes_cohort_id != unrelated_result.cohort.id


def test_input_drift_marks_cohort_stale_and_withholds_dispatch(app):
    plan = _plan()

    def supersede_plan():
        plan.status = 'superseded'

    result = execute_derived_intelligence_plan(
        plan.id, domain_executor=RecordingExecutor(), before_revalidate=supersede_plan,
    )
    assert result.cohort.status == 'stale'
    assert result.publication_job is None
    assert {
        row.status for row in DerivedIntelligenceCohortDomain.query.filter_by(cohort_id=result.cohort.id)
    } == {'stale'}


def test_lease_fence_failure_prevents_snapshot_and_publication(app):
    plan = _plan()
    calls = {'count': 0}

    def fence():
        calls['count'] += 1
        if calls['count'] == 2:
            raise RuntimeError('lease lost')

    with pytest.raises(RuntimeError, match='lease lost'):
        execute_derived_intelligence_plan(
            plan.id, domain_executor=RecordingExecutor(), lease_fence=fence,
        )
    db.session.rollback()
    assert DerivedCohortSnapshot.query.count() == 0
    assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 0


def test_zero_work_and_superseded_plan_are_successful_no_ops(app):
    plan = _plan(domains=[])
    plan.affected_domains_json = []
    db.session.commit()
    result = execute_derived_intelligence_plan(plan.id)
    assert result.zero_work is True
    assert result.cohort is None
    plan.status = 'superseded'
    plan.affected_domains_json = ['workload']
    db.session.commit()
    result = execute_derived_intelligence_plan(plan.id)
    assert result.zero_work is True
    assert DerivedIntelligenceCohort.query.count() == 0


def test_manifest_rows_are_queryable_and_scope_stays_bounded(app):
    plan = _plan(teams=(110,), pitchers=(10,))
    result = execute_derived_intelligence_plan(plan.id, domain_executor=RecordingExecutor())
    assert result.cohort.affected_team_ids_json == [110]
    assert result.cohort.affected_pitcher_ids_json == [10]
    assert DerivedCohortInput.query.filter_by(cohort_id=result.cohort.id).count() == 0
    assert all(row.entity_key in {'10', '110', '777123'} for row in DerivedCohortSnapshot.query.all())


def test_final_manifest_pins_current_versions_and_detects_real_version_drift(app):
    observation_v1 = _observation('v1')
    game_v1, appearance_v1, pitcher = _final_authority(observation_v1, version=1)
    plan = _plan(
        fingerprint='e' * 64, domains=('workload',), pitchers=(pitcher.id,),
    )
    plan.source_observation_ids_json = [observation_v1.id]
    db.session.commit()

    def correct_final():
        game_v1.is_current = False
        appearance_v1.is_current = False
        observation_v2 = _observation('v2')
        _final_authority(
            observation_v2, version=2,
            predecessor=(game_v1, appearance_v1),
        )

    result = execute_derived_intelligence_plan(
        plan.id, domain_executor=RecordingExecutor(), before_revalidate=correct_final,
    )
    assert result.cohort.status == 'stale'
    assert result.publication_job is None
    inputs = DerivedCohortInput.query.filter_by(cohort_id=result.cohort.id).all()
    assert {(row.input_type, row.input_version) for row in inputs} == {
        ('final_game', str(game_v1.id)),
        ('final_appearance', str(appearance_v1.id)),
        ('source_observation', str(observation_v1.id)),
    }


def test_concurrent_exact_cohort_creates_one_candidate_and_job_postgresql(app):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL derived-cohort concurrency contract')
    plan = _plan()
    plan_id = plan.id
    barrier = Barrier(2)

    def execute(_index):
        with app.app_context():
            barrier.wait(timeout=10)
            result = execute_derived_intelligence_plan(
                plan_id, domain_executor=RecordingExecutor(),
            )
            cohort_id = result.cohort.id
            db.session.remove()
            return cohort_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        cohort_ids = list(pool.map(execute, (0, 1)))
    with app.app_context():
        assert cohort_ids[0] == cohort_ids[1]
        assert DerivedIntelligenceCohort.query.count() == 1
        assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 1


def test_one_shot_worker_consumes_sp09_job_and_only_enqueues_sp11_handoff(app):
    observation = _observation('pregame-worker')
    context = GamePregameContextVersion(
        game_pk=777123, version_number=1, baseball_date=GAME_DATE,
        home_team_id=110, away_team_id=111,
        context_fingerprint='pregame-worker'.ljust(64, '0'),
        fingerprint_version='test-v1', source_observation_id=observation.id,
        completeness='complete', observed_at=observation.observed_at,
    )
    db.session.add(context)
    db.session.flush()
    plan = _plan(
        fingerprint='f' * 64, authority='pregame_authoritative',
        domains=('game_context', 'matchup_context', 'read_models'), pitchers=(),
    )
    plan.source_observation_ids_json = [observation.id]
    db.session.commit()
    enqueue_job(
        job_type=JobType.PROCESS_DERIVED_INTELLIGENCE,
        scope_type=JobScopeType.GAME, scope_key='777123', product_date=GAME_DATE,
        dedupe_key='sp10-worker-test', payload_schema_version=1,
        payload={
            'impact_plan_id': plan.id, 'rules_version': plan.rules_version,
            'authority_class': plan.authority_class,
            'baseball_date': GAME_DATE.isoformat(),
        },
    )
    settled = run_derived_intelligence_worker_once('sp10-worker')
    assert settled.status == 'succeeded'
    assert settled.result_json['cohort_status'] == 'complete'
    cohort = db.session.get(DerivedIntelligenceCohort, settled.result_json['cohort_id'])
    assert cohort.sync_run_id is not None
    assert cohort.publication_job_id is not None
    assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 1
