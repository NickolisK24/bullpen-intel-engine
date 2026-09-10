from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import importlib.util
from pathlib import Path
from threading import Barrier

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
import sqlalchemy as sa

from models.canonical_impact import (
    CanonicalImpactPlan,
    CanonicalImpactPlanEntity,
    CanonicalImpactPlanMutation,
)
from models.final_game_reconciliation import FinalGameMutation, FinalGameVersion
from models.live_game_delta import LiveGameMutation
from models.pitcher import Pitcher
from models.pregame_context import GamePregameContextVersion, PregameContextMutation
from models.roster_membership import RosterMembershipInterval, RosterMembershipMutation
from models.source_observation import SourceObservation, SourceSubject
from models.sync_job import SyncJob
from services.canonical_impact import (
    AuthorityClass,
    IMPACT_RULES_VERSION,
    ImpactDomain,
    MutationFamily,
    execute_canonical_impact_job,
    impact_domains_for,
    normalize_mutation_cohort,
    plan_canonical_impact,
    run_canonical_impact_worker_once,
)
from services.continuous_execution import _canonical_impact_from_game_outcome
from services.sync_jobs import (
    JobScopeType, JobType, LeaseOwnershipError, claim_next_job, enqueue_job,
    heartbeat_job,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


GAME_DATE = date(2026, 9, 8)
GAME_PK = 777123


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


def _pitcher(mlb_id, team_id=110):
    row = Pitcher(
        mlb_id=mlb_id, full_name=f'Pitcher {mlb_id}', team_id=team_id,
        team_name='Team', team_abbreviation='T', active=True,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _observation(domain='boxscore', revision='1'):
    suffix = f'{domain}-{revision}'
    subject = SourceSubject(
        identity_key=(suffix + '-subject').ljust(64, '0')[:64],
        provider='mlb_stats_api', source_domain=domain, endpoint='/test',
        subject_type='game', subject_key=f'game:{GAME_PK}',
        request_identity=(suffix + '-request').ljust(64, '0')[:64],
        request_schema_version=1, request_parameters={}, baseball_date=GAME_DATE,
    )
    db.session.add(subject)
    db.session.flush()
    row = SourceObservation(
        source_subject_id=subject.id, version_number=1,
        dedupe_key=(suffix + '-dedupe').ljust(64, '0')[:64],
        fingerprint=(suffix + '-fingerprint').ljust(64, '0')[:64],
        fingerprint_algorithm='sha256', fingerprint_version='test-v1',
        payload_schema_version=1, completeness='complete', outcome='new',
        is_change=True, is_authoritative=True, record_count=1,
        observed_at=datetime(2026, 9, 8, 22, 0),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _final_game(observation, *, version=1):
    row = FinalGameVersion(
        game_pk=GAME_PK, version_number=version, baseball_date=GAME_DATE,
        home_team_id=110, away_team_id=111, fact_fingerprint=f'game-v{version}',
        fingerprint_version='test-v1', core_completeness='complete',
        pbp_completeness='unknown', finality_observation_id=observation.id,
        boxscore_observation_id=observation.id, is_current=True,
        observed_at=observation.observed_at,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _final_mutation(observation, game_version, pitcher, mutation_type, identity):
    row = FinalGameMutation(
        mutation_key=f'{GAME_PK}:{identity}', mutation_type=mutation_type,
        final_game_version_id=game_version.id, game_pk=GAME_PK,
        baseball_date=GAME_DATE, team_id=pitcher.team_id if pitcher else 110,
        pitcher_id=pitcher.id if pitcher else None,
        pitcher_mlb_id=pitcher.mlb_id if pitcher else None,
        source_observation_id=observation.id,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _live_mutation(observation, pitcher, identity='live-1'):
    row = LiveGameMutation(
        mutation_key=f'{GAME_PK}:{identity}', mutation_type='live_appearance_updated',
        game_pk=GAME_PK, baseball_date=GAME_DATE, team_id=pitcher.team_id,
        pitcher_id=pitcher.id, pitcher_mlb_id=pitcher.mlb_id,
        source_observation_id=observation.id, new_fingerprint=identity,
        authority_state='live', is_correction=False,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _payload(mutations, *, family, authority):
    return {
        'mutation_family': family,
        'authority_class': authority,
        'mutation_ids': [row.id for row in mutations],
        'game_pk': GAME_PK,
        'baseball_date': GAME_DATE,
    }


def test_final_mutations_coalesce_into_one_deterministic_plan(app):
    observation = _observation()
    pitcher_a, pitcher_b = _pitcher(1, 110), _pitcher(2, 111)
    game = _final_game(observation)
    rows = [
        _final_mutation(observation, game, None, 'final_game_ingested', 'game'),
        _final_mutation(observation, game, pitcher_a, 'starter_appearance_added', 'a'),
        _final_mutation(observation, game, pitcher_b, 'reliever_appearance_added', 'b'),
    ]
    payload = _payload(rows, family='final_game_context', authority='final')
    first = plan_canonical_impact(payload)
    second = plan_canonical_impact(payload)

    assert first.created is True
    assert second.created is False
    assert first.plan.id == second.plan.id
    assert first.plan.rules_version == IMPACT_RULES_VERSION
    assert first.plan.authority_class == AuthorityClass.FINAL.value
    assert first.plan.affected_game_ids_json == [GAME_PK]
    assert first.plan.affected_team_ids_json == [110, 111]
    assert first.plan.affected_pitcher_ids_json == [pitcher_a.id, pitcher_b.id]
    assert ImpactDomain.WORKLOAD.value in first.plan.affected_domains_json
    assert ImpactDomain.ROTATION_TRANSFER.value in first.plan.affected_domains_json
    assert CanonicalImpactPlan.query.count() == 1
    assert CanonicalImpactPlanMutation.query.count() == 3
    assert CanonicalImpactPlanEntity.query.count() == 5
    assert SyncJob.query.filter_by(job_name='process_derived_intelligence').count() == 1


def test_final_entity_scope_matches_existing_cu_mutation_scope(app):
    observation = _observation(revision='parity')
    pitchers = [_pitcher(value, 110 if value < 13 else 111) for value in range(8, 18)]
    game = _final_game(observation)
    rows = [
        _final_mutation(
            observation, game, pitcher, 'reliever_appearance_added',
            f'parity-{pitcher.id}',
        )
        for pitcher in pitchers
    ]
    plan = plan_canonical_impact(_payload(
        rows, family='final_appearance', authority='final',
    )).plan
    cu = _canonical_impact_from_game_outcome({
        'game_pk': GAME_PK,
        'inserted': len(rows),
        'impact': {
            'affected_pitcher_ids': [pitcher.id for pitcher in pitchers],
            'affected_pitcher_mlb_ids': [pitcher.mlb_id for pitcher in pitchers],
            'affected_team_ids': [110, 111],
        },
    })
    assert plan.affected_pitcher_ids_json == sorted(cu['affected_pitcher_ids'])
    assert plan.affected_team_ids_json == sorted(cu['affected_team_ids'])


def test_corrected_pitching_line_has_exact_scope_and_domains(app):
    observation = _observation(revision='correction')
    pitcher = _pitcher(3, 110)
    game = _final_game(observation, version=2)
    row = _final_mutation(observation, game, pitcher, 'pitching_line_corrected', 'corrected')
    result = plan_canonical_impact(_payload(
        [row], family='final_appearance', authority='corrected_final',
    ))
    assert result.plan.authority_class == AuthorityClass.CORRECTED_FINAL.value
    assert result.plan.affected_team_ids_json == [110]
    assert result.plan.affected_pitcher_ids_json == [pitcher.id]
    assert ImpactDomain.WORKLOAD.value in result.plan.affected_domains_json
    assert ImpactDomain.ROSTER_COMPOSITION.value not in result.plan.affected_domains_json


def test_live_plan_is_narrow_and_final_supersedes_it(app):
    live_observation = _observation('live_feed', 'live')
    pitcher = _pitcher(4, 110)
    live = _live_mutation(live_observation, pitcher)
    live_result = plan_canonical_impact(_payload(
        [live], family='live_appearance', authority='live',
    ))
    assert live_result.plan.affected_domains_json == sorted([
        'game_context', 'team_workload_current', 'workload_current',
    ])

    final_observation = _observation('boxscore', 'final')
    game = _final_game(final_observation)
    final = _final_mutation(final_observation, game, pitcher, 'pitching_line_corrected', 'final')
    final_result = plan_canonical_impact(_payload(
        [final], family='final_appearance', authority='corrected_final',
    ))
    assert final_result.plan.supersedes_live is True
    assert final_result.plan.supersedes_plan_id == live_result.plan.id
    assert live_result.plan.status == 'superseded'

    late_live = _live_mutation(live_observation, pitcher, 'late-live')
    late_result = plan_canonical_impact(_payload(
        [late_live], family='live_appearance', authority='live',
    ))
    assert late_result.stale_live_suppressed is True
    assert late_result.plan.status == 'superseded'
    assert late_result.plan.affected_domains_json == []
    assert late_result.downstream_job is None


def test_roster_and_pregame_rules_remain_bounded(app):
    roster_observation = _observation('roster', 'active')
    pitcher = _pitcher(5, 110)
    interval = RosterMembershipInterval(
        pitcher_id=pitcher.id, player_mlb_id=pitcher.mlb_id, team_id=110,
        membership_type='active_roster', effective_start_date=GAME_DATE,
        start_precision='date', authority_type='official',
        opened_by_observation_id=roster_observation.id, is_current_version=True,
    )
    db.session.add(interval); db.session.flush()
    roster = RosterMembershipMutation(
        interval_id=interval.id, pitcher_id=pitcher.id,
        player_mlb_id=pitcher.mlb_id, team_id=110,
        membership_type='active_roster', mutation_type='membership_opened',
        baseball_date=GAME_DATE, precision='date',
        source_observation_id=roster_observation.id,
    )
    db.session.add(roster); db.session.flush()
    roster_result = plan_canonical_impact({
        'mutation_family': 'roster_membership',
        'authority_class': 'roster_authoritative',
        'membership_mutation_ids': [roster.id], 'baseball_date': GAME_DATE,
    })
    assert 'team_state' in roster_result.plan.affected_domains_json
    assert 'workload' not in roster_result.plan.affected_domains_json

    depth_interval = RosterMembershipInterval(
        pitcher_id=pitcher.id, player_mlb_id=pitcher.mlb_id, team_id=110,
        membership_type='forty_man_roster', effective_start_date=GAME_DATE,
        start_precision='date', authority_type='official',
        opened_by_observation_id=roster_observation.id, is_current_version=True,
    )
    db.session.add(depth_interval); db.session.flush()
    depth = RosterMembershipMutation(
        interval_id=depth_interval.id, pitcher_id=pitcher.id,
        player_mlb_id=pitcher.mlb_id, team_id=110,
        membership_type='forty_man_roster', mutation_type='membership_opened',
        baseball_date=GAME_DATE, precision='date',
        source_observation_id=roster_observation.id,
    )
    db.session.add(depth); db.session.flush()
    depth_result = plan_canonical_impact({
        'mutation_family': 'roster_membership',
        'authority_class': 'roster_authoritative',
        'membership_mutation_ids': [depth.id], 'baseball_date': GAME_DATE,
    })
    assert 'organizational_depth' in depth_result.plan.affected_domains_json
    assert 'team_state' not in depth_result.plan.affected_domains_json

    pregame_observation = _observation('pregame', 'pregame')
    version = GamePregameContextVersion(
        game_pk=GAME_PK, version_number=1, baseball_date=GAME_DATE,
        home_team_id=110, away_team_id=111, context_fingerprint='pregame',
        fingerprint_version='test-v1', source_observation_id=pregame_observation.id,
        completeness='complete', observed_at=pregame_observation.observed_at,
    )
    db.session.add(version); db.session.flush()
    pregame = PregameContextMutation(
        context_version_id=version.id, game_pk=GAME_PK, baseball_date=GAME_DATE,
        team_id=110, side='home', mutation_type='probable_starter_changed',
        old_probable_pitcher_mlb_id=9, new_probable_pitcher_mlb_id=10,
        source_observation_id=pregame_observation.id,
    )
    db.session.add(pregame); db.session.flush()
    result = plan_canonical_impact({
        'mutation_family': 'pregame_context',
        'authority_class': 'pregame_authoritative',
        'pregame_context_mutation_ids': [pregame.id], 'baseball_date': GAME_DATE,
    })
    assert result.plan.affected_domains_json == [
        'game_context', 'matchup_context', 'read_models',
    ]
    assert 'team_state' not in result.plan.affected_domains_json


def test_worker_uses_queue_and_emits_only_plan_driven_job(app):
    observation = _observation()
    pitcher = _pitcher(6, 110)
    game = _final_game(observation)
    mutation = _final_mutation(observation, game, pitcher, 'reliever_appearance_added', 'worker')
    enqueue_job(
        job_type=JobType.PROCESS_CANONICAL_IMPACT,
        scope_type=JobScopeType.GAME, scope_key=str(GAME_PK), product_date=GAME_DATE,
        dedupe_key='test-impact-worker', payload_schema_version=1,
        payload=_payload([mutation], family='final_appearance', authority='final'),
    )
    result = run_canonical_impact_worker_once('impact-worker')
    assert result.status == 'succeeded'
    assert result.result_json['impact_plan_id']
    assert SyncJob.query.filter_by(job_name='process_derived_intelligence').count() == 1


def test_missing_mutation_fails_without_half_dispatch(app):
    with pytest.raises(ValueError, match='Missing FinalGameMutation'):
        plan_canonical_impact({
            'mutation_family': 'final_appearance',
            'authority_class': 'final',
            'mutation_ids': [999999],
            'baseball_date': GAME_DATE,
        })
    assert CanonicalImpactPlan.query.count() == 0
    assert SyncJob.query.filter_by(job_name='process_derived_intelligence').count() == 0


def test_stale_impact_worker_is_fenced_before_planning(app):
    observation = _observation(revision='stale-worker')
    pitcher = _pitcher(66, 110)
    game = _final_game(observation)
    mutation = _final_mutation(
        observation, game, pitcher, 'reliever_appearance_added', 'stale-worker',
    )
    start = datetime(2026, 9, 9, 1, 0)
    enqueue_job(
        job_type=JobType.PROCESS_CANONICAL_IMPACT,
        scope_type=JobScopeType.GAME, scope_key=str(GAME_PK),
        product_date=GAME_DATE, dedupe_key='stale-impact-worker',
        payload_schema_version=1,
        payload=_payload([mutation], family='final_appearance', authority='final'),
        available_at=start,
    )
    first = claim_next_job(
        'impact-a', job_types=[JobType.PROCESS_CANONICAL_IMPACT],
        lease_seconds=1, now=start,
    )
    stale_token = first.claim_token
    second = claim_next_job(
        'impact-b', job_types=[JobType.PROCESS_CANONICAL_IMPACT],
        lease_seconds=30, now=start + timedelta(seconds=2),
    )
    assert first.id == second.id
    with pytest.raises(LeaseOwnershipError):
        heartbeat_job(
            first.id, worker_id='impact-a', claim_token=stale_token,
            now=start + timedelta(seconds=3),
        )
    assert CanonicalImpactPlan.query.count() == 0


def test_concurrent_same_cohort_creates_one_plan_on_postgresql(app):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL canonical-impact concurrency contract')
    observation = _observation()
    pitcher = _pitcher(7, 110)
    game = _final_game(observation)
    mutation = _final_mutation(observation, game, pitcher, 'reliever_appearance_added', 'race')
    payload = _payload([mutation], family='final_appearance', authority='final')
    jobs = []
    for suffix in ('a', 'b'):
        jobs.append(enqueue_job(
            job_type=JobType.PROCESS_CANONICAL_IMPACT,
            scope_type=JobScopeType.GAME, scope_key=str(GAME_PK), product_date=GAME_DATE,
            dedupe_key=f'test-impact-race-{suffix}', payload_schema_version=1,
            payload=payload,
        ))
    claimed = [
        claim_next_job(f'worker-{suffix}', job_types=[JobType.PROCESS_CANONICAL_IMPACT])
        for suffix in ('a', 'b')
    ]
    ids = [row.id for row in claimed]
    barrier = Barrier(2)

    def execute(index):
        with app.app_context():
            job = db.session.get(SyncJob, ids[index])
            barrier.wait(timeout=10)
            result = execute_canonical_impact_job(job)
            db.session.remove()
            return result['impact_plan_id']

    with ThreadPoolExecutor(max_workers=2) as pool:
        plan_ids = list(pool.map(execute, (0, 1)))
    with app.app_context():
        assert plan_ids[0] == plan_ids[1]
        assert CanonicalImpactPlan.query.count() == 1
        assert SyncJob.query.filter_by(job_name='process_derived_intelligence').count() == 1


def test_migration_round_trip_preserves_prerequisite_rows():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    for name in ('sync_runs', 'sync_jobs', 'pitchers', 'source_observations'):
        sa.Table(name, metadata, sa.Column('id', sa.Integer(), primary_key=True))
    metadata.create_all(engine)
    path = Path(__file__).resolve().parents[1] / 'migrations' / 'versions' / 'c1d4e7a9b2f6_add_canonical_impact_plans.py'
    spec = importlib.util.spec_from_file_location('sp09_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.execute(sa.text('INSERT INTO sync_runs (id) VALUES (9)'))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert {
            'canonical_impact_plans', 'canonical_impact_plan_mutations',
            'canonical_impact_plan_entities',
        } <= set(sa.inspect(connection).get_table_names())
        assert connection.execute(sa.text('SELECT id FROM sync_runs')).scalar_one() == 9
        migration.downgrade()
        assert 'canonical_impact_plans' not in sa.inspect(connection).get_table_names()
        assert connection.execute(sa.text('SELECT id FROM sync_runs')).scalar_one() == 9
