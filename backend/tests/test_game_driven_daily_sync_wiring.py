"""Foundation 3C — publication-critical scope change in the daily sync.

These tests prove the scope correction the production evidence demanded: the
daily publication-critical lane is driven by relevant GAME coverage, and the
full-season-per-pitcher loop is demoted to governed best-effort repair.
"""

from datetime import date, datetime

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import game_driven_ingestion
from services import publication_criticality
from services import sync as sync_service
from utils.db import db


REFERENCE = date(2026, 7, 29)
GAME_PK = 930001


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


def _pitcher(mlb_id, *, roster_status='ACTIVE', position='P', active=True):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=f'Arm {mlb_id}',
        team_id=147,
        team_abbreviation='TST',
        position=position,
        active=active,
        roster_status=roster_status,
    )
    db.session.add(pitcher)
    return pitcher


def _schedule(game_pk, *, game_date=REFERENCE):
    for team_id, opponent_id, side in ((147, 111, 'home'), (111, 147, 'away')):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=game_pk, game_date=game_date,
            game_datetime=datetime(
                game_date.year, game_date.month, game_date.day, 19, 5,
            ),
            opponent_team_id=opponent_id, home_away=side, game_type='R',
            status_code='F', status_state=ScheduledGame.STATE_FINAL,
        ))


class _StubClient:
    """Counts exactly which MLB reads the pitcher loop performs."""

    def __init__(self, splits_by_pitcher=None):
        self.splits_by_pitcher = splits_by_pitcher or {}
        self.game_log_calls = []

    def get_pitcher_game_logs(self, mlb_id, season=None):
        self.game_log_calls.append(mlb_id)
        return list(self.splits_by_pitcher.get(mlb_id, ()))


def _split(game_pk, *, game_date=REFERENCE, innings='1.0'):
    return {
        'date': game_date.isoformat(),
        'game': {'gamePk': game_pk},
        'stat': {
            'inningsPitched': innings,
            'gamesStarted': 0,
            'earnedRuns': 0,
            'runs': 0,
            'hits': 0,
            'baseOnBalls': 0,
            'strikeOuts': 1,
            'homeRuns': 0,
            'battersFaced': 3,
            'numberOfPitches': 12,
        },
        'opponent': {'id': 111, 'name': 'Opponent'},
    }


# ── The demoted lane ────────────────────────────────────────────────────────


def test_best_effort_only_reports_no_publication_critical_pitcher_work(
    app, monkeypatch,
):
    with app.app_context():
        # The exact production shape: active starters and active-roster
        # non-pitchers that the old contract called publication-critical.
        _pitcher(7001)
        _pitcher(7002)
        _pitcher(7003, position='2B')
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', _StubClient())

        result = sync_service.sync_recent_logs(
            reference_date=REFERENCE, best_effort_only=True,
        )

        assert result['best_effort_only'] is True
        assert result['publication_critical_total'] == 0
        assert result['best_effort_total'] == 3


def test_the_roster_criticality_classifier_is_retained_not_deleted(app, monkeypatch):
    with app.app_context():
        _pitcher(7010, roster_status='ACTIVE')
        _pitcher(7011, roster_status='IL_15')
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', _StubClient())

        result = sync_service.sync_recent_logs(reference_date=REFERENCE)

        # Unchanged behaviour when the game lane is not authoritative.
        assert result['publication_critical_total'] == 1
        assert result['best_effort_total'] == 1
        assert publication_criticality.criticality_for_roster_status('ACTIVE') == (
            publication_criticality.CRITICALITY_PUBLICATION_CRITICAL
        )


def test_a_game_the_authoritative_lane_reconciled_is_not_rewritten(app, monkeypatch):
    with app.app_context():
        _schedule(GAME_PK)
        pitcher = _pitcher(7020)
        db.session.commit()
        client = _StubClient({7020: [_split(GAME_PK)]})
        monkeypatch.setattr(sync_service, 'mlb_client', client)

        result = sync_service.sync_recent_logs(
            reference_date=REFERENCE,
            skip_game_pks=[GAME_PK],
            best_effort_only=True,
        )

        assert result['splits_skipped_already_reconciled'] == 1
        assert result['new_logs_added'] == 0
        assert GameLog.query.filter_by(
            pitcher_id=pitcher.id, mlb_game_pk=GAME_PK
        ).count() == 0
        # The conflict-prevention skip must not make the lane look dead.
        assert result['lane_health'] != 'all_window_splits_dropped'


def test_without_the_skip_set_the_repair_lane_still_works(app, monkeypatch):
    with app.app_context():
        _schedule(GAME_PK)
        _pitcher(7030)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client', _StubClient({7030: [_split(GAME_PK)]}),
        )

        result = sync_service.sync_recent_logs(
            reference_date=REFERENCE, best_effort_only=True,
        )

        assert result['new_logs_added'] == 1


# ── Publication-critical scope ──────────────────────────────────────────────


def _game_lane(completeness, *, report=None):
    return {
        'mode': game_driven_ingestion.MODE_AUTHORITATIVE,
        'authoritative': True,
        'report': report or {'best_effort_games_deferred': 0},
        'completeness': completeness,
        'completed_game_pks': (),
        'remaining_ingestion_budget_seconds': 0.0,
        'error_class': None,
    }


def _complete_proof(**overrides):
    proof = {
        'expected_final_games': 15,
        'completed_final_games': 15,
        'unresolved_final_games': 0,
        'terminal_failure_games': 0,
        'finality_conflicts': 0,
        'schedule_authority_missing': 0,
        'publication_complete': True,
        'decision_reasons': ['game_ingestion_complete'],
    }
    proof.update(overrides)
    return proof


def test_complete_game_coverage_publishes_even_with_a_best_effort_shortfall():
    result = sync_service._publication_critical_from_game_lane(
        game_lane=_game_lane(_complete_proof()),
        pull={'pitchers_total': 854, 'budget_exhausted_pitchers': 640},
        non_gamelog_critical_failed=0,
    )

    assert result['complete'] is True
    assert result['publication_critical_total'] == 15
    assert result['best_effort_deferred'] == 640


def test_one_unresolved_critical_game_withholds():
    result = sync_service._publication_critical_from_game_lane(
        game_lane=_game_lane(_complete_proof(
            publication_complete=False,
            unresolved_final_games=1,
            completed_final_games=14,
            decision_reasons=['unresolved_final_games'],
        )),
        pull={'pitchers_total': 854, 'budget_exhausted_pitchers': 0},
        non_gamelog_critical_failed=0,
    )

    assert result['complete'] is False
    assert 'unresolved_final_games' in result['reason_codes']


def test_a_withheld_proof_without_a_countable_cause_still_fails_closed():
    result = sync_service._publication_critical_from_game_lane(
        game_lane=_game_lane(_complete_proof(
            publication_complete=False,
            decision_reasons=['critical_appearance_rows_unreconciled'],
        )),
        pull={'pitchers_total': 0, 'budget_exhausted_pitchers': 0},
        non_gamelog_critical_failed=0,
    )

    assert result['complete'] is False


def test_a_missing_game_lane_result_is_never_complete():
    result = sync_service._publication_critical_from_game_lane(
        game_lane={
            'report': None, 'completeness': None, 'authoritative': True,
        },
        pull={'pitchers_total': 854, 'budget_exhausted_pitchers': 0},
        non_gamelog_critical_failed=0,
    )

    assert result['complete'] is False
    assert result['status'] == publication_criticality.PUBLICATION_CRITICAL_UNAVAILABLE


def test_a_non_gamelog_lane_failure_still_withholds():
    result = sync_service._publication_critical_from_game_lane(
        game_lane=_game_lane(_complete_proof()),
        pull={'pitchers_total': 854, 'budget_exhausted_pitchers': 0},
        non_gamelog_critical_failed=1,
    )

    assert result['complete'] is False


def test_a_finality_conflict_is_unknown_criticality_and_fails_closed():
    result = sync_service._publication_critical_from_game_lane(
        game_lane=_game_lane(_complete_proof(
            publication_complete=False,
            finality_conflicts=1,
            decision_reasons=['finality_conflict_unresolved'],
        )),
        pull={'pitchers_total': 0, 'budget_exhausted_pitchers': 0},
        non_gamelog_critical_failed=0,
    )

    assert result['complete'] is False
    assert result['unknown_criticality'] == 1


# ── Cost shape ──────────────────────────────────────────────────────────────


def test_the_critical_lane_cost_scales_with_games_not_pitchers(app):
    """The whole point of Foundation 3C, asserted directly.

    One fetch per planned game, no matter how large the pitcher universe is.
    """
    with app.app_context():
        _schedule(930010)
        _schedule(930011)
        for offset in range(40):
            _pitcher(7100 + offset)
        db.session.commit()

        fetched = []

        def _fetch(item):
            fetched.append(item.game_pk)
            return {'gamePk': item.game_pk}, {}

        def _extract(item, game_payload, boxscore):
            return [{
                'game_pk': item.game_pk, 'game_date': REFERENCE,
                'pitcher_mlb_id': 7100, 'team_id': 147, 'opponent_team_id': 111,
                'side': 'home', 'appearance_role': 'relief', 'games_started': 0,
                'is_starter': False, 'is_reliever': True, 'outs_recorded': 3,
                'innings_pitched': 1.0, 'earned_runs': 0, 'runs_allowed': 0,
                'hits_allowed': 0, 'walks': 0, 'strikeouts': 1,
                'home_runs_allowed': 0, 'batters_faced': 3,
                'pitches_thrown': 12, 'source_authority': 'test',
            }]

        original = game_driven_ingestion._resolve_handlers
        game_driven_ingestion._resolve_handlers = lambda *_args: {
            'fetch': _fetch, 'extract': _extract, 'persist': None,
        }
        try:
            report = game_driven_ingestion.run_game_driven_ingestion(
                REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
            )
        finally:
            game_driven_ingestion._resolve_handlers = original

        assert Pitcher.query.filter_by(active=True).count() == 40
        assert report['games_fetched'] == 2
        assert sorted(fetched) == [930010, 930011]


def test_an_off_roster_pitcher_appearing_in_a_final_game_is_still_ingested(app):
    """Roster movement never decides whether an appearance is ingested.

    Game evidence does. An optioned or IL arm that pitched in a newly final
    game is reconciled from that game, which the old roster-code contract
    classified as best-effort and deferred.
    """
    with app.app_context():
        _schedule(930020)
        optioned = _pitcher(7200, roster_status='OPTIONED', active=False)
        db.session.commit()

        record = {
            'game_pk': 930020, 'game_date': REFERENCE, 'pitcher_mlb_id': 7200,
            'team_id': 147, 'opponent_team_id': 111, 'side': 'home',
            'appearance_role': 'relief', 'games_started': 0, 'is_starter': False,
            'is_reliever': True, 'outs_recorded': 3, 'innings_pitched': 1.0,
            'earned_runs': 0, 'runs_allowed': 0, 'hits_allowed': 0, 'walks': 0,
            'strikeouts': 1, 'home_runs_allowed': 0, 'batters_faced': 3,
            'pitches_thrown': 12, 'source_authority': 'test',
        }

        def _persist(item, game_payload, boxscore, *, sync_run_id=None):
            db.session.add(GameLog(
                pitcher_id=optioned.id, mlb_game_pk=item.game_pk,
                game_date=REFERENCE, innings_pitched=1.0,
                innings_pitched_outs=3, games_started=0,
            ))
            db.session.flush()
            return {
                'inserted': 1, 'updated': 0, 'unsafe': 0,
                'unresolved_pitchers': 0,
            }

        original = game_driven_ingestion._resolve_handlers
        game_driven_ingestion._resolve_handlers = lambda *_args: {
            'fetch': lambda item: ({'gamePk': item.game_pk}, {}),
            'extract': lambda item, game, box: [record],
            'persist': _persist,
        }
        try:
            report = game_driven_ingestion.run_game_driven_ingestion(
                REFERENCE, mode=game_driven_ingestion.MODE_WRITE,
            )
        finally:
            game_driven_ingestion._resolve_handlers = original

        assert report['games_completed'] == 1
        assert GameLog.query.filter_by(mlb_game_pk=930020).count() == 1
        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=930020).one()
        assert item.relief_rows_reconciled == 1


# ── Correction re-check must not destabilise the postgame marker ────────────


def _boxscore(pitcher_mlb_id, *, innings='1.0', earned_runs=0, degraded=False):
    if degraded:
        # The realistic transient shape: the box score answers, but carries no
        # pitching section at all (`empty_pitching_data`).
        return {
            'teams': {
                'home': {'team': {'id': 147, 'name': 'Home'}, 'pitchers': [],
                         'players': {}},
                'away': {'team': {'id': 111, 'name': 'Away'}, 'pitchers': [],
                         'players': {}},
            },
        }
    person = {'id': pitcher_mlb_id, 'fullName': f'Arm {pitcher_mlb_id}'}
    return {
        'teams': {
            'home': {
                'team': {'id': 147, 'name': 'Home', 'abbreviation': 'HOM'},
                'pitchers': [pitcher_mlb_id],
                'players': {
                    f'ID{pitcher_mlb_id}': {
                        'person': person,
                        'position': {'abbreviation': 'P', 'code': '1', 'name': 'Pitcher'},
                        'stats': {'pitching': {
                            'inningsPitched': innings,
                            'gamesStarted': 0,
                            'earnedRuns': earned_runs,
                            'runs': earned_runs,
                            'hits': 1,
                            'baseOnBalls': 0,
                            'strikeOuts': 2,
                            'homeRuns': 0,
                            'strikes': 10,
                            'battersFaced': 4,
                            'numberOfPitches': 15,
                        }},
                    },
                },
            },
            'away': {
                'team': {'id': 111, 'name': 'Away', 'abbreviation': 'AWY'},
                'pitchers': [],
                'players': {},
            },
        },
    }


class _BoxscoreClient(_StubClient):
    def __init__(self, boxscores):
        super().__init__()
        self.boxscores = boxscores
        self.boxscore_calls = []

    def get_game_boxscore(self, game_pk):
        self.boxscore_calls.append(game_pk)
        return self.boxscores[game_pk]


def _final_game(game_pk):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': REFERENCE.isoformat(),
        'status': {
            'statusCode': 'F', 'detailedState': 'Final',
            'abstractGameState': 'Final',
        },
        'teams': {
            'home': {'team': {'id': 147, 'name': 'Home'}},
            'away': {'team': {'id': 111, 'name': 'Away'}},
        },
    }


def test_a_correction_recheck_does_not_burn_the_postgame_retry_budget(
    app, monkeypatch,
):
    from models.postgame_processed_game import PostgameProcessedGame

    with app.app_context():
        _pitcher(7300)
        db.session.commit()
        game_pk = 930100
        client = _BoxscoreClient({game_pk: _boxscore(7300)})
        monkeypatch.setattr(sync_service, 'mlb_client', client)

        sync_service.process_completed_game_for_postgame_refresh(
            _final_game(game_pk), schedule_date=REFERENCE,
        )
        db.session.commit()
        first = PostgameProcessedGame.query.filter_by(mlb_game_pk=game_pk).one()
        assert first.processing_status == (
            PostgameProcessedGame.STATUS_FULLY_PROCESSED
        )
        assert first.attempt_count == 1

        # Seven daily correction re-checks inside the horizon.
        for _ in range(7):
            sync_service.process_completed_game_for_postgame_refresh(
                _final_game(game_pk), schedule_date=REFERENCE, force=True,
            )
            db.session.commit()

        marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=game_pk).one()
        assert marker.attempt_count == 1
        assert marker.processing_status == (
            PostgameProcessedGame.STATUS_FULLY_PROCESSED
        )


def test_a_degraded_recheck_never_demotes_a_proven_marker(app, monkeypatch):
    from models.postgame_processed_game import PostgameProcessedGame

    with app.app_context():
        _pitcher(7310)
        db.session.commit()
        game_pk = 930101
        client = _BoxscoreClient({game_pk: _boxscore(7310)})
        monkeypatch.setattr(sync_service, 'mlb_client', client)

        sync_service.process_completed_game_for_postgame_refresh(
            _final_game(game_pk), schedule_date=REFERENCE,
        )
        db.session.commit()

        # A transient degraded read during the correction re-check.
        client.boxscores[game_pk] = _boxscore(7310, degraded=True)
        result = sync_service.process_completed_game_for_postgame_refresh(
            _final_game(game_pk), schedule_date=REFERENCE, force=True,
        )
        db.session.commit()

        marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=game_pk).one()
        # The appearance-ledger publication gate reads this marker; a blip in a
        # re-read must not turn a proven game into a ledger hole.
        assert marker.processing_status == (
            PostgameProcessedGame.STATUS_FULLY_PROCESSED
        )
        assert marker.processed_at is not None
        assert result['retry_exhausted'] is False


def test_a_first_read_that_is_degraded_still_fails_closed(app, monkeypatch):
    from models.postgame_processed_game import PostgameProcessedGame

    with app.app_context():
        _pitcher(7320)
        db.session.commit()
        game_pk = 930102
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            _BoxscoreClient({game_pk: _boxscore(7320, degraded=True)}),
        )

        sync_service.process_completed_game_for_postgame_refresh(
            _final_game(game_pk), schedule_date=REFERENCE, force=True,
        )
        db.session.commit()

        marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=game_pk).one()
        assert marker.processing_status != (
            PostgameProcessedGame.STATUS_FULLY_PROCESSED
        )
        assert marker.incomplete_reason is not None


def test_force_lets_a_completed_game_be_reread_for_corrections(app, monkeypatch):
    with app.app_context():
        _pitcher(7330)
        db.session.commit()
        game_pk = 930103
        client = _BoxscoreClient({game_pk: _boxscore(7330, earned_runs=1)})
        monkeypatch.setattr(sync_service, 'mlb_client', client)

        sync_service.process_completed_game_for_postgame_refresh(
            _final_game(game_pk), schedule_date=REFERENCE,
        )
        db.session.commit()

        # Without force the marker short-circuits and the correction is missed.
        client.boxscores[game_pk] = _boxscore(7330, earned_runs=3)
        skipped = sync_service.process_completed_game_for_postgame_refresh(
            _final_game(game_pk), schedule_date=REFERENCE,
        )
        assert skipped['skipped'] is True
        assert GameLog.query.filter_by(mlb_game_pk=game_pk).one().earned_runs == 1

        forced = sync_service.process_completed_game_for_postgame_refresh(
            _final_game(game_pk), schedule_date=REFERENCE, force=True,
        )
        db.session.commit()

        assert forced['skipped'] is False
        assert forced['logs_corrected'] == 1
        assert GameLog.query.filter_by(mlb_game_pk=game_pk).count() == 1
        assert GameLog.query.filter_by(mlb_game_pk=game_pk).one().earned_runs == 3
