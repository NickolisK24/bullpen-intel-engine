"""One bounded, evidence-driven repair before a withheld publication stands.

The real sync-completion path, the real publication transaction and the real
Team State proof run here (see ``test_publication_failure_evidence``). Slate
coverage is computed from the stored schedule and postgame markers, so a
repair that lands canonical ingestion is what lets the rebuilt candidate pass.
"""

from datetime import date

import pytest

from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from services import dashboard_snapshot, publication_reconciliation, slate_coverage
from services import sync as sync_service
from services import sync_metadata
from services.publication_reconciliation import Reconciler, plan_repair, reingest_final_games
from tests.test_publication_failure_evidence import (  # noqa: F401
    DATA_THROUGH,
    _game,
    app,
    daily_candidate,
)
from utils.db import db


def _gate_on_stored_slate(monkeypatch):
    """Withhold exactly when the stored slate for data_through is incomplete."""
    def reason(_payload):
        coverage = slate_coverage.compute_slate_coverage(DATA_THROUGH)
        if coverage.get('complete_enough_to_publish') is not True:
            return dashboard_snapshot.DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE
        return None
    monkeypatch.setattr(dashboard_snapshot, '_payload_slate_coverage_unavailable_reason', reason)
    monkeypatch.setattr(dashboard_snapshot, 'run_post_commit_snapshot_publication', lambda _s: None)


def _appearance(game_pk, game_date=DATA_THROUGH):
    pitcher = Pitcher.query.filter_by(mlb_id=950000).one_or_none()
    if pitcher is None:
        pitcher = Pitcher(mlb_id=950000, full_name='Ledger Arm', team_id=141,
                          position='P', active=True)
        db.session.add(pitcher)
        db.session.flush()
    db.session.add(GameLog(
        pitcher_id=pitcher.id, mlb_game_pk=game_pk, game_date=game_date,
        innings_pitched=1.0, innings_pitched_outs=3, pitches_thrown=15,
    ))


def _final_ingested(game_pk, teams=(141, 147)):
    _game(game_pk, ScheduledGame.STATE_FINAL, teams=teams,
          marker=PostgameProcessedGame.STATUS_FULLY_PROCESSED)
    _appearance(game_pk)


class FakeSchedule:
    def __init__(self, *game_pks, state='Final', code='F'):
        self.games = [
            {'gamePk': pk, 'officialDate': DATA_THROUGH.isoformat(),
             'status': {'statusCode': code, 'detailedState': state,
                        'abstractGameState': 'Final' if code == 'F' else 'Live'},
             'teams': {'home': {'team': {'id': 141}}, 'away': {'team': {'id': 147}}}}
            for pk in game_pks
        ]
        self.calls = 0

    def get_schedule(self, start_date, end_date):
        self.calls += 1
        return list(self.games)


def _processor(calls, *, completes=True):
    def process(game, *, schedule_date, sync_run_id=None, force=False):
        calls.append((game['gamePk'], force))
        if completes:
            _appearance(game['gamePk'], schedule_date)
            db.session.add(PostgameProcessedGame(
                mlb_game_pk=game['gamePk'], game_date=schedule_date,
                processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
            ))
            return {'processing_status': 'fully_processed', 'logs_added': 0}
        return {'processing_status': 'incomplete', 'logs_added': 0}
    return process


def _reconciler(client, calls, **kwargs):
    def repair(plan, *, sync_run_id=None):
        return reingest_final_games(
            plan, sync_run_id=sync_run_id, client=client,
            processor=_processor(calls, **kwargs), fatigue_recalc=lambda: None,
        )
    return Reconciler(repair=repair)


def _complete(run_id, reconciler, **kwargs):
    return sync_service.complete_sync_run_with_snapshot(
        run_id, final_status=sync_metadata.STATUS_SUCCESS, reconciler=reconciler, **kwargs,
    )


def _outcome(run_id):
    db.session.expire_all()
    return db.session.get(SyncRun, run_id).publication_outcome


def test_scenario_11_a_final_game_with_incomplete_ingestion_is_repaired_and_published(
    app, daily_candidate, monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(sys_module(), 'FAILING', ())
        _gate_on_stored_slate(monkeypatch)
        _final_ingested(9201)
        _game(9202, ScheduledGame.STATE_FINAL, teams=(108, 109))
        db.session.commit()
        calls = []
        client = FakeSchedule(9202)

        run, snapshot = _complete(daily_candidate['run_id'], _reconciler(client, calls))

        outcome = _outcome(daily_candidate['run_id'])
        assert outcome['status'] == 'published'
        assert outcome['published_snapshot_id'] == snapshot.id
        assert outcome['recovery_attempted'] is True
        recovery = outcome['recovery_result']
        assert recovery['repair_class'] == 'final_game_reingest'
        assert recovery['result'] == 'repaired'
        assert recovery['stop_reason'] is None
        assert [entity['game_pk'] for entity in recovery['affected_entities']] == [9202]
        assert calls == [(9202, True)]
        # The first, withheld candidate stays as pending evidence.
        first = db.session.get(DashboardSnapshot, recovery['first_candidate_snapshot_id'])
        assert first is not None and first.is_published is False
        assert recovery['rebuilt_candidate_snapshot_id'] == snapshot.id


def test_scenario_12_a_failed_repair_runs_once_and_the_withhold_stands(
    app, daily_candidate, monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(sys_module(), 'FAILING', ())
        _gate_on_stored_slate(monkeypatch)
        _game(9211, ScheduledGame.STATE_FINAL)
        db.session.commit()
        calls = []

        with pytest.raises(sync_service.DashboardSnapshotPublicationWithheld):
            _complete(daily_candidate['run_id'],
                      _reconciler(FakeSchedule(9211), calls, completes=False))

        outcome = _outcome(daily_candidate['run_id'])
        assert outcome['status'] == 'withheld'
        assert outcome['affected_game_pks'] == [9211]
        assert outcome['recovery_attempted'] is True
        assert outcome['recovery_result']['result'] == 'repair_incomplete'
        assert outcome['recovery_result']['stop_reason'] == 'still_withheld_after_repair'
        assert calls == [(9211, True)]
        assert DashboardSnapshot.query.filter_by(is_published=True).count() == 1


def test_a_repair_that_raises_is_recorded_and_never_rebuilt(app, daily_candidate, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(sys_module(), 'FAILING', ())
        _gate_on_stored_slate(monkeypatch)
        _game(9221, ScheduledGame.STATE_FINAL)
        db.session.commit()

        def explode(plan, *, sync_run_id=None):
            raise ConnectionError('schedule unavailable')

        before = DashboardSnapshot.query.count()
        with pytest.raises(sync_service.DashboardSnapshotPublicationWithheld):
            _complete(daily_candidate['run_id'], Reconciler(repair=explode))
        outcome = _outcome(daily_candidate['run_id'])
        assert outcome['recovery_result']['result'] == 'repair_failed'
        assert outcome['recovery_result']['error'] == 'ConnectionError'
        assert outcome['recovery_result']['stop_reason'] == 'repair_failed'
        assert DashboardSnapshot.query.count() == before + 1


@pytest.mark.parametrize('state, blocker', [
    (ScheduledGame.STATE_SCHEDULED, 'not_final'),
    (ScheduledGame.STATE_OTHER, 'not_final'),
    (ScheduledGame.STATE_SUSPENDED, 'suspended'),
])
def test_scenarios_5_and_6_live_and_suspended_games_are_never_repaired(
    app, daily_candidate, monkeypatch, state, blocker,
):
    with app.app_context():
        monkeypatch.setattr(sys_module(), 'FAILING', ())
        _gate_on_stored_slate(monkeypatch)
        _game(9231, ScheduledGame.STATE_FINAL)
        _game(9232, state, teams=(108, 109))
        db.session.commit()
        calls = []
        client = FakeSchedule(9231, 9232)

        with pytest.raises(sync_service.DashboardSnapshotPublicationWithheld):
            _complete(daily_candidate['run_id'], _reconciler(client, calls))

        outcome = _outcome(daily_candidate['run_id'])
        assert outcome['recovery_attempted'] is False
        assert outcome['recovery_result']['stop_reason'] == 'non_repairable_games'
        assert {'game_pk': 9232, 'game_date': DATA_THROUGH.isoformat(), 'blocker': blocker} in (
            outcome['recovery_result']['affected_entities']
        )
        assert calls == [] and client.calls == 0


def test_a_publication_critical_withhold_is_not_repaired(app, daily_candidate, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(sys_module(), 'FAILING', ())
        _gate_on_stored_slate(monkeypatch)
        _game(9241, ScheduledGame.STATE_FINAL)
        db.session.commit()
        calls = []
        with pytest.raises(sync_service.DashboardSnapshotPublicationWithheld):
            _complete(daily_candidate['run_id'], _reconciler(FakeSchedule(9241), calls),
                      publication_critical_complete=False)
        outcome = _outcome(daily_candidate['run_id'])
        assert outcome['recovery_attempted'] is False
        assert outcome['recovery_result']['stop_reason'] == 'publication_critical_incomplete'
        assert calls == []


def test_scenario_10_an_already_publishable_candidate_does_no_reconciliation_work(
    app, daily_candidate, monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(sys_module(), 'FAILING', ())
        _gate_on_stored_slate(monkeypatch)
        _final_ingested(9251)
        db.session.commit()
        calls = []
        client = FakeSchedule()
        run, snapshot = _complete(daily_candidate['run_id'], _reconciler(client, calls))
        outcome = _outcome(daily_candidate['run_id'])
        assert outcome['status'] == 'published'
        assert outcome['recovery_attempted'] is False
        assert outcome['recovery_result'] is None
        assert calls == [] and client.calls == 0


def test_a_team_state_failure_is_not_a_repair_candidate(app, daily_candidate, monkeypatch):
    with app.app_context():
        calls = []
        client = FakeSchedule()
        with pytest.raises(ValueError):
            _complete(daily_candidate['run_id'], _reconciler(client, calls))
        outcome = _outcome(daily_candidate['run_id'])
        assert outcome['status'] == 'failed'
        assert outcome['failed_authority'] == 'team_state_eligibility'
        assert calls == []


def test_classification_table():
    def outcome(games, authority='slate_coverage', critical=True, reasons=()):
        return {'failed_authority': authority, 'publication_critical_complete': critical,
                'gate_evidence': {'games': games, 'reason_codes': list(reasons)}}
    marker = {'game_pk': 1, 'game_date': '2026-09-29', 'blocker': 'final_marker_missing'}
    live = {'game_pk': 2, 'game_date': '2026-09-29', 'blocker': 'not_final'}
    ledger = {'game_pk': 3, 'game_date': '2026-09-28',
              'blocker': 'final_game_without_appearance_rows'}
    assert plan_repair(outcome([marker]))['repairable'] is True
    assert plan_repair(outcome([ledger], 'appearance_ledger'))['repairable'] is True
    assert plan_repair(outcome([marker, live]))['stop_reason'] == 'non_repairable_games'
    assert plan_repair(outcome([]))['stop_reason'] == 'no_repairable_entities'
    assert plan_repair(outcome([], reasons=['partial_sync']))['stop_reason'] == (
        'publication_critical_incomplete'
    )
    assert plan_repair(outcome([marker], critical=False))['stop_reason'] == (
        'publication_critical_incomplete'
    )
    assert plan_repair(outcome([marker], 'team_state_eligibility'))['stop_reason'] == (
        'authority_not_repairable:team_state_eligibility'
    )
    many = [dict(marker, game_pk=pk) for pk in range(
        publication_reconciliation.MAX_REPAIR_GAMES + 1)]
    assert plan_repair(outcome(many))['stop_reason'] == 'repair_scope_exceeds_bound'


def sys_module():
    import sys
    return sys.modules['tests.test_publication_failure_evidence']
