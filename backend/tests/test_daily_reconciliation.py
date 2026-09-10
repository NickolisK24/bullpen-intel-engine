from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from threading import Barrier

import pytest
from flask import Flask

from models.daily_closure import BaseballDateClosure, BaseballDateClosureVersion
from models.derived_intelligence import DerivedIntelligenceCohort
from models.final_game_reconciliation import FinalGameMutation, FinalGameVersion
from models.player_transaction import PlayerTransactionSyncWindow
from models.scheduled_game import ScheduledGame
from models.source_observation import SourceObservation, SourceSubject
from models.sync_job import SyncJob
from models.atomic_publication import AtomicPublication
from services.daily_reconciliation import (
    EXPECTED_MLB_TEAMS, RESOLVED_STATES, check_baseball_date_closure,
    game_resolution_state, plan_morning_reconciliation,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


DAY = date(2026, 9, 9)


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


class TeamsClient:
    def get_all_teams(self):
        return [{'id': value} for value in range(101, 131)]


def _window(status='success'):
    row = PlayerTransactionSyncWindow(
        source='mlb_stats_api', source_endpoint='/transactions',
        source_query_start_date=DAY, source_query_end_date=DAY,
        attempted_at=datetime(2026, 9, 10, 6),
        successful_at=datetime(2026, 9, 10, 6) if status != 'failed' else None,
        status=status,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _game(game_pk, state, team=110, opponent=111):
    row = ScheduledGame(
        team_id=team, game_pk=game_pk, game_date=DAY,
        opponent_team_id=opponent, home_away='home', status_state=state,
        operational_state=state, source='test',
    )
    db.session.add(row)
    db.session.commit()
    return row


def _final(game_pk, version=1, fingerprint='a'):
    prior = FinalGameVersion.query.filter_by(game_pk=game_pk, is_current=True).first()
    if prior:
        prior.is_current = False
        prior.superseded_at = datetime(2026, 9, 10, 12)
    subject = SourceSubject.query.filter_by(subject_key=str(game_pk)).first()
    if subject is None:
        subject = SourceSubject(
            identity_key=f'{game_pk:064d}'[-64:], provider='mlb_stats_api',
            source_domain='boxscore', endpoint=f'/game/{game_pk}/boxscore',
            subject_type='game', subject_key=str(game_pk),
            request_identity=f'{game_pk:064d}'[-64:], request_schema_version=1,
            request_parameters={'game_pk': game_pk}, baseball_date=DAY,
        )
        db.session.add(subject)
        db.session.flush()
    observation = SourceObservation(
        source_subject_id=subject.id, version_number=version,
        dedupe_key=(f'{game_pk}:{version}:' + fingerprint * 64)[:64],
        fingerprint=(fingerprint * 64)[:64], fingerprint_algorithm='sha256',
        fingerprint_version='source-v1', payload_schema_version=1,
        completeness='complete', outcome='new' if version == 1 else 'corrected',
        is_change=version > 1, is_authoritative=True, record_count=1,
        observed_at=datetime(2026, 9, 10, 5),
    )
    db.session.add(observation)
    db.session.flush()
    row = FinalGameVersion(
        game_pk=game_pk, version_number=version,
        predecessor_version_id=prior.id if prior else None,
        baseball_date=DAY, home_team_id=110, away_team_id=111,
        fact_fingerprint=(fingerprint * 64)[:64], fingerprint_version='final-v1',
        core_completeness='complete', pbp_completeness='partial',
        finality_observation_id=observation.id,
        boxscore_observation_id=observation.id,
        is_current=True, observed_at=datetime(2026, 9, 10, 5),
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_morning_reconciliation_enumerates_all_30_and_dedupes_jobs(app):
    first = plan_morning_reconciliation(DAY, client=TeamsClient())
    assert len(first.team_ids) == EXPECTED_MLB_TEAMS == 30
    assert len([row for row in SyncJob.query.all() if row.job_name == 'fetch_roster']) == 30
    assert SyncJob.query.filter_by(job_name='fetch_schedule').count() == 1
    assert SyncJob.query.filter_by(job_name='fetch_transactions').count() == 1
    assert SyncJob.query.filter_by(job_name='check_baseball_date_closure').count() == 1
    total = SyncJob.query.count()
    second = plan_morning_reconciliation(DAY, client=TeamsClient())
    assert len(second.team_ids) == 30
    assert SyncJob.query.count() == total


def test_shadow_morning_plans_acquisition_but_suppresses_closure_and_publication(app):
    plan = plan_morning_reconciliation(
        DAY,
        client=TeamsClient(),
        shadow_mode=True,
        publication_candidate_enabled=False,
        closure_checks_enabled=False,
    )

    assert len(plan.team_ids) == 30
    assert SyncJob.query.filter_by(job_name='fetch_roster').count() == 30
    assert SyncJob.query.filter_by(job_name='fetch_transactions').count() == 1
    assert SyncJob.query.filter_by(job_name='check_baseball_date_closure').count() == 0
    assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 0
    assert any(
        row['job_type'] == 'check_baseball_date_closure'
        for row in plan.suppressed_obligations
    )


def test_morning_fails_closed_without_exact_team_denominator(app):
    client = TeamsClient()
    client.get_all_teams = lambda: [{'id': value} for value in range(101, 130)]
    with pytest.raises(RuntimeError, match='expected 30, received 29'):
        plan_morning_reconciliation(DAY, client=client)
    assert SyncJob.query.count() == 0


def test_morning_fails_closed_on_duplicate_team_identity(app):
    client = TeamsClient()
    client.get_all_teams = lambda: [
        *[{'id': value} for value in range(101, 131)],
        {'id': 101},
    ]
    with pytest.raises(RuntimeError, match='duplicate team IDs'):
        plan_morning_reconciliation(DAY, client=client)
    assert SyncJob.query.count() == 0


@pytest.mark.parametrize('state', sorted(RESOLVED_STATES))
def test_resolved_game_state_matrix(state, app):
    assert game_resolution_state(_game(800000 + len(state), state)) == 'resolved'


@pytest.mark.parametrize('state', ['scheduled', 'pregame', 'live', 'delayed', 'suspended', 'unknown'])
def test_blocking_game_state_matrix(state, app):
    assert game_resolution_state(_game(810000 + len(state), state)) == 'blocking'


def test_zero_game_date_closes_with_complete_empty_transaction_authority(app):
    _window()
    closure, decision = check_baseball_date_closure(DAY)
    assert decision.closable is True
    assert closure.status == 'closed'
    assert closure.expected_games == 0
    assert closure.current_version_number == 1
    assert BaseballDateClosureVersion.query.one().event_type == 'closed'


def test_suspended_game_blocks_and_schedules_slow_recheck(app):
    _window()
    _game(820001, 'suspended')
    now = datetime(2026, 9, 10, 6)
    closure, decision = check_baseball_date_closure(DAY, now=now)
    assert closure.status == 'blocked'
    assert any(row['blocker_type'] == 'unresolved_game' for row in decision.blockers)
    assert int((closure.next_check_at - now).total_seconds()) == 21600
    assert SyncJob.query.filter_by(job_name='check_baseball_date_closure').count() == 1


def test_postponed_and_cancelled_games_are_resolved_without_final_versions(app):
    _window()
    _game(820002, 'postponed')
    _game(820003, 'cancelled', team=112, opponent=113)
    closure, _decision = check_baseball_date_closure(DAY)
    assert closure.status == 'closed'
    assert closure.expected_games == 2
    assert closure.resolved_games == 2
    assert closure.final_games == 0


def test_final_without_sp07_authority_blocks_then_closes(app):
    _window()
    _game(820004, 'final')
    closure, decision = check_baseball_date_closure(DAY, schedule_recheck=False)
    assert closure.status == 'blocked'
    assert [row['blocker_type'] for row in decision.blockers] == ['final_reconciliation_missing']
    assert SyncJob.query.filter_by(job_name='reconcile_final_game').count() == 1
    _final(820004)
    closure, decision = check_baseball_date_closure(DAY, schedule_recheck=False)
    assert decision.closable is True
    assert closure.status == 'closed'
    assert closure.reconciled_final_games == 1
    assert closure.optional_enrichment_outstanding is True


def test_partial_transaction_authority_blocks_closure(app):
    _window('partial')
    closure, decision = check_baseball_date_closure(DAY, schedule_recheck=False)
    assert closure.status == 'blocked'
    assert closure.transaction_completeness == 'partial'
    assert any(row['blocker_type'] == 'transaction_partial' for row in decision.blockers)


def test_doubleheader_counts_by_game_pk(app):
    _window()
    _game(820005, 'final')
    _game(820006, 'final')
    _final(820005)
    _final(820006)
    closure, _decision = check_baseball_date_closure(DAY)
    assert closure.status == 'closed'
    assert closure.expected_games == closure.final_games == 2


def test_closed_date_reopens_on_correction_and_closes_again_with_history(app):
    _window()
    _game(820007, 'final')
    _final(820007, fingerprint='a')
    closure, _ = check_baseball_date_closure(DAY)
    original_fingerprint = closure.closure_fingerprint
    assert closure.status == 'closed'
    corrected = _final(820007, version=2, fingerprint='b')
    db.session.add(FinalGameMutation(
        mutation_key='correction:820007:v2', mutation_type='final_game_context_corrected',
        final_game_version_id=corrected.id, game_pk=820007, baseball_date=DAY,
        source_observation_id=corrected.boxscore_observation_id,
        details_json={'affected_team_ids': [110, 111]},
    ))
    db.session.commit()
    closure, decision = check_baseball_date_closure(DAY, schedule_recheck=False)
    assert closure.status == 'reopened'
    assert closure.closure_fingerprint != original_fingerprint
    assert decision.closable is False
    assert any(row['blocker_type'] == 'pending_impact' for row in decision.blockers)
    assert SyncJob.query.filter_by(job_name='process_canonical_impact').count() == 1
    # Simulate the bounded owner pipeline satisfying the correction obligation.
    from models.canonical_impact import CanonicalImpactPlan, CanonicalImpactPlanMutation
    plan = CanonicalImpactPlan(
        plan_fingerprint='c' * 64, rules_version='canonical-impact-v1',
        authority_class='corrected_final', baseball_date=DAY,
        affected_game_ids_json=[820007], affected_team_ids_json=[110, 111],
        affected_pitcher_ids_json=[], affected_domains_json=['game_context'],
        source_observation_ids_json=[corrected.boxscore_observation_id], status='dispatched',
        supersedes_live=False,
    )
    db.session.add(plan)
    db.session.flush()
    db.session.add(CanonicalImpactPlanMutation(
        impact_plan_id=plan.id, mutation_family='final_game_context',
        source_mutation_id=FinalGameMutation.query.one().id,
        source_mutation_type='final_game_context_corrected',
        authority_class='corrected_final', game_pk=820007,
        baseball_date=DAY, source_observation_id=corrected.boxscore_observation_id,
        is_correction=True,
    ))
    db.session.flush()
    cohort = DerivedIntelligenceCohort(
        impact_plan_id=plan.id, cohort_fingerprint='d' * 64,
        schema_version='derived-cohort-v1', authority_class='corrected_final',
        baseball_date=DAY, status='complete',
        requested_domains_json=['game_context'], execution_domains_json=['game_context'],
        completed_domains_json=['game_context'], withheld_domains_json=[],
        affected_game_ids_json=[820007], affected_team_ids_json=[110, 111],
        affected_pitcher_ids_json=[], input_manifest_json=[], method_versions_json={},
        completed_at=datetime(2026, 9, 10, 13),
    )
    db.session.add(cohort)
    db.session.flush()
    publication = AtomicPublication(
        publication_fingerprint='e' * 64, schema_version='publication-v1',
        cohort_id=cohort.id, impact_plan_id=plan.id, baseball_date=DAY,
        authority_class='corrected_final', status='published', completeness='complete',
        source_data_through=datetime(2026, 9, 10, 13),
        affected_game_ids_json=[820007], affected_team_ids_json=[110, 111],
        affected_pitcher_ids_json=[], completed_domains_json=['game_context'],
        withheld_domains_json=[], method_versions_json={},
        input_manifest_fingerprint='f' * 64, published_at=datetime(2026, 9, 10, 13),
    )
    db.session.add(publication)
    db.session.commit()
    closure, _ = check_baseball_date_closure(DAY, schedule_recheck=False)
    assert closure.status == 'closed'
    assert closure.publication_id == publication.id
    versions = BaseballDateClosureVersion.query.order_by(BaseballDateClosureVersion.version_number).all()
    assert [row.event_type for row in versions] == ['closed', 'reopened', 'closed']
    assert versions[1].predecessor_version_id == versions[0].id
    assert versions[2].predecessor_version_id == versions[1].id


def test_lease_fence_failure_rolls_back_closure_decision(app):
    _window()
    with pytest.raises(RuntimeError, match='stale'):
        check_baseball_date_closure(
            DAY, lease_fence=lambda: (_ for _ in ()).throw(RuntimeError('stale')),
        )
    db.session.rollback()
    assert BaseballDateClosure.query.count() == 0


def test_postgresql_same_date_closure_converges(app):
    if db.session.get_bind().dialect.name != 'postgresql':
        pytest.skip('PostgreSQL locking proof requires TEST_DATABASE_URL')
    _window()
    barrier = Barrier(2)

    def run():
        with app.app_context():
            barrier.wait()
            row, _ = check_baseball_date_closure(DAY)
            return row.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: run(), range(2)))
    assert len(set(ids)) == 1
    assert BaseballDateClosure.query.count() == 1
    assert BaseballDateClosureVersion.query.count() == 1
