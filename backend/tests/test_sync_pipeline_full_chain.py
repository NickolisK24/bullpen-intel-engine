"""One transactional SP-03 through SP-14 certification fixture."""

from datetime import date, datetime

import pytest
from flask import Flask

from models.atomic_publication import AtomicPublication
from models.daily_closure import BaseballDateClosureVersion
from models.final_game_reconciliation import FinalGameVersion
from models.player_transaction import PlayerTransactionSyncWindow
from models.sync_job import SyncJob
from services.atomic_publication import publish_derived_cohort, read_current_publication_bundle
from services.canonical_impact import plan_canonical_impact
from services.daily_reconciliation import check_baseball_date_closure
from services.derived_intelligence import execute_derived_intelligence_plan
from services.final_game_reconciliation import reconcile_final_game
from services.mlb_club_directory import MLB_TEAM_IDS
from services.repair_orchestration import plan_repair_request, submit_repair_request
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.test_final_game_reconciliation import (
    GAME_DATE, GAME_PK, _boxscore, _bundle, _seed_schedule,
)
from utils.db import db


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


def _domain_executor(plan):
    def execute(domain, _snapshots):
        team_ids = (
            MLB_TEAM_IDS
            if domain in ('team_snapshot', 'read_models', 'what_changed')
            else plan.affected_team_ids_json
        )
        if domain == 'read_models':
            pitcher_id = plan.affected_pitcher_ids_json[0]
            return {
                'pitcher': {
                    str(value): {'read_models': {'pitcher_current': {
                        'pitcher': {'id': value},
                    }}}
                    for value in plan.affected_pitcher_ids_json
                },
                'team': {
                    str(value): {'read_models': {
                        'team_board': {'team_id': value},
                        'league_row': {'team_id': value},
                        'team_board_v2': {
                            'full': {'active_bullpen': {'arms': [
                                {'pitcher_id': pitcher_id},
                            ]}},
                            'core': {}, 'details': {},
                        },
                    }}
                    for value in team_ids
                },
                'game': {
                    str(value): {'read_models': {'matchup': {'game_pk': value}}}
                    for value in plan.affected_game_ids_json
                },
                'summary': {'domain': domain},
            }
        if domain == 'what_changed':
            return {
                'team': {
                    str(value): {'what_changed': {'team_id': value}}
                    for value in team_ids
                },
                'summary': {'domain': domain},
            }
        return {
            'pitcher': {
                str(value): {domain: {'value': domain}}
                for value in plan.affected_pitcher_ids_json
            },
            'team': {
                str(value): {domain: {'value': domain}}
                for value in team_ids
            },
            'game': {
                str(value): {domain: {'value': domain}}
                for value in plan.affected_game_ids_json
            },
            'summary': {'domain': domain},
        }
    return execute


def _process_mutations(mutations):
    impact = plan_canonical_impact({
        'mutation_ids': [row.id for row in mutations],
        'authority_class': 'final',
        'baseball_date': GAME_DATE,
    })
    cohort = execute_derived_intelligence_plan(
        impact.plan.id, domain_executor=_domain_executor(impact.plan),
    )
    publication = publish_derived_cohort(cohort.cohort.id)
    for job in SyncJob.query.filter(
        SyncJob.product_date == GAME_DATE,
        SyncJob.status.in_(('pending', 'running', 'retry_wait')),
    ):
        job.status = 'succeeded'
        job.completed_at = datetime(2026, 9, 9, 23, 59)
    db.session.commit()
    return impact.plan, cohort.cohort, publication.publication


def _complete_transaction_window():
    db.session.add(PlayerTransactionSyncWindow(
        source='mlb_stats_api', source_endpoint='/transactions',
        source_query_start_date=GAME_DATE, source_query_end_date=GAME_DATE,
        attempted_at=datetime(2026, 9, 9, 23),
        successful_at=datetime(2026, 9, 9, 23), status='success',
    ))
    db.session.commit()


def test_final_publish_close_correction_repair_and_reclose(app):
    _seed_schedule()
    _complete_transaction_window()

    first = reconcile_final_game(_bundle())
    assert first.game_version.finality_observation_id
    assert first.game_version.boxscore_observation_id
    first_plan, first_cohort, first_publication = _process_mutations(first.mutations)
    closure, decision = check_baseball_date_closure(GAME_DATE, schedule_recheck=False)
    assert decision.closable is True, decision.blockers
    assert closure.publication_id == first_publication.id
    assert read_current_publication_bundle()['publication_id'] == first_publication.id

    correction = reconcile_final_game(_bundle(
        box=_boxscore(home_reliever_pitches=19), correction=True,
    ))
    assert correction.game_version.version_number == 2
    assert correction.game_version.predecessor_version_id == first.game_version.id
    assert len(correction.mutations) == 1
    closure, blocked = check_baseball_date_closure(GAME_DATE, schedule_recheck=False)
    assert closure.status == 'reopened'
    assert any(row['blocker_type'] == 'pending_impact' for row in blocked.blockers)

    second_plan, second_cohort, second_publication = _process_mutations(correction.mutations)
    closure, decision = check_baseball_date_closure(GAME_DATE, schedule_recheck=False)
    assert decision.closable is True, decision.blockers
    assert closure.status == 'closed'
    assert closure.publication_id == second_publication.id
    assert second_publication.predecessor_publication_id == first_publication.id
    assert second_cohort.predecessor_cohort_id == first_cohort.id
    assert second_plan.id != first_plan.id
    assert FinalGameVersion.query.count() == 2
    assert [row.event_type for row in BaseballDateClosureVersion.query.order_by(
        BaseballDateClosureVersion.version_number,
    )] == ['closed', 'reopened', 'closed']

    dry_run = submit_repair_request(
        mode='targeted_repair', source_domain='final_game',
        baseball_date_start=GAME_DATE, scope={'game_pk': GAME_PK},
        reason='certification dry run', dry_run=True, enqueue=False,
    )
    request = plan_repair_request(dry_run.request.id)
    assert request.status == 'completed'
    assert request.outcome_json['mutations_performed'] == 0
    assert AtomicPublication.query.count() == 2
