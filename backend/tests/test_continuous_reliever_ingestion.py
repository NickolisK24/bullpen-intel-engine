from datetime import date, datetime

import pytest
from flask import Flask

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.play_by_play_foundation import GamePitchEvent, PlayByPlayProcessedGame
from models.sync_run import SyncRun
from services import continuous_reliever_ingestion as cu01
from services import game_driven_ingestion
from services import game_appearance_extraction as extraction
from services import play_by_play_foundation
from services import sync as sync_service
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.game_driven_fixtures import schedule_final_game
from utils.db import db


GAME_PK = 930001
GAME_DATE = date(2026, 8, 27)
HOME_TEAM = 147
AWAY_TEAM = 111


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


def _game():
    return {
        'gamePk': GAME_PK,
        'gameType': 'R',
        'officialDate': GAME_DATE.isoformat(),
        'status': {
            'statusCode': 'F',
            'detailedState': 'Final',
            'abstractGameState': 'Final',
        },
        'teams': {
            'home': {'team': {'id': HOME_TEAM, 'name': 'Home Club'}},
            'away': {'team': {'id': AWAY_TEAM, 'name': 'Away Club'}},
        },
    }


def _stats(*, innings, started, pitches, hit_batters=0, wild_pitches=0,
           omit=()):
    values = {
        'inningsPitched': innings,
        'gamesStarted': started,
        'numberOfPitches': pitches,
        'strikes': 10,
        'hits': 1,
        'runs': 0,
        'earnedRuns': 0,
        'baseOnBalls': 1,
        'strikeOuts': 2,
        'homeRuns': 0,
        'battersFaced': 5,
        'balls': 7,
        'gamesFinished': 1,
        'hitBatsmen': hit_batters,
        'wildPitches': wild_pitches,
        'inheritedRunners': 2,
        'inheritedRunnersScored': 1,
        'saveOpportunities': 1,
        'holds': 1,
        'blownSaves': 0,
        'wins': 0,
        'losses': 0,
        'saves': 0,
    }
    for key in omit:
        values.pop(key, None)
    return values


def _boxscore(*, missing_optional=False):
    lines = [
        (1001, 'home', _stats(innings='5.0', started=1, pitches=75)),
        (1002, 'home', _stats(
            innings='1.0', started=0, pitches=17, hit_batters=1,
            wild_pitches=1,
            omit=(
                'hitBatsmen', 'wildPitches', 'saveOpportunities', 'holds',
                'blownSaves', 'wins', 'losses', 'saves',
            ) if missing_optional else (),
        )),
        (2001, 'away', _stats(innings='4.0', started=1, pitches=68)),
        (2002, 'away', _stats(innings='1.1', started=0, pitches=22)),
    ]
    payload = {'teams': {}}
    for side, team_id in (('home', HOME_TEAM), ('away', AWAY_TEAM)):
        payload['teams'][side] = {
            'team': {'id': team_id, 'name': f'{side.title()} Club'},
            'pitchers': [],
            'players': {},
        }
    for mlb_id, side, stats in lines:
        payload['teams'][side]['pitchers'].append(mlb_id)
        payload['teams'][side]['players'][f'ID{mlb_id}'] = {
            'person': {'id': mlb_id, 'fullName': f'Pitcher {mlb_id}'},
            'position': {'code': '1', 'abbreviation': 'P', 'name': 'Pitcher'},
            'stats': {'pitching': stats},
        }
    return payload


def _pitch_play(at_bat_index, pitcher_id, half, *, rich=False, event_index=0):
    event = {
        'index': event_index,
        'isPitch': True,
        'pitchNumber': 1,
        'playId': f'pitch-{at_bat_index}-{event_index}',
        'details': {
            'code': 'C',
            'description': 'Called Strike',
            'isBall': False,
            'isStrike': True,
            'isInPlay': False,
            'isOut': False,
            'type': {'code': 'FF', 'description': 'Four-Seam Fastball'},
        },
        'count': {'balls': 0, 'strikes': 1, 'outs': 0},
    }
    if rich:
        event['details'].update({
            'code': 'X',
            'description': 'In play, out(s)',
            'isStrike': False,
            'isInPlay': True,
            'isOut': True,
        })
        event['pitchData'] = {
            'startSpeed': 97.2,
            'endSpeed': 89.1,
            'extension': 6.7,
            'plateTime': 0.39,
            'zone': 5,
            'strikeZoneTop': 3.45,
            'strikeZoneBottom': 1.55,
            'coordinates': {
                'pX': 0.15, 'pZ': 2.61,
                'x0': -1.8, 'y0': 50.0, 'z0': 5.9,
                'vX0': 4.1, 'vY0': -141.0, 'vZ0': -3.1,
                'aX': -8.2, 'aY': 29.0, 'aZ': -15.0,
                'pfxX': -0.55, 'pfxZ': 1.18,
            },
            'breaks': {
                'spinRate': 2488,
                'spinDirection': 205,
                'breakAngle': 31.2,
                'breakHorizontal': -5.4,
                'breakLength': 4.9,
                'breakVertical': -14.2,
                'breakVerticalInduced': 17.1,
            },
        }
        event['hitData'] = {
            'trajectory': 'ground_ball',
            'hardness': 'medium',
            'launchSpeed': 88.4,
            'launchAngle': -3.0,
            'totalDistance': 42.0,
            'location': '5',
        }
    return {
        'playId': f'play-{at_bat_index}',
        'about': {
            'atBatIndex': at_bat_index,
            'inning': 7,
            'halfInning': half,
            'outs': 0,
            'isComplete': True,
            'isScoringPlay': False,
        },
        'result': {'eventType': 'field_out', 'homeScore': 2, 'awayScore': 1},
        'matchup': {'pitcher': {'id': pitcher_id}, 'batter': {'id': 9000 + at_bat_index}},
        'playEvents': [event],
    }


def _play_by_play(*, corrected=False):
    plays = [
        _pitch_play(0, 1001, 'top'),
        _pitch_play(1, 1002, 'top', rich=True),
        _pitch_play(2, 2001, 'bottom'),
        _pitch_play(3, 2002, 'bottom'),
    ]
    if corrected:
        plays[1]['playEvents'][0]['pitchData']['startSpeed'] = 98.1
        plays[1]['playEvents'].append(
            _pitch_play(1, 1002, 'top', event_index=1)['playEvents'][0]
        )
    return {'allPlays': plays}


def _seed_pitchers():
    for mlb_id, team_id in (
        (1001, HOME_TEAM), (1002, HOME_TEAM),
        (2001, AWAY_TEAM), (2002, AWAY_TEAM),
    ):
        db.session.add(Pitcher(
            mlb_id=mlb_id,
            full_name=f'Pitcher {mlb_id}',
            team_id=team_id,
            team_abbreviation='HOM' if team_id == HOME_TEAM else 'AWY',
            active=True,
        ))
    db.session.commit()


def _ingest(boxscore=None):
    result = sync_service.process_completed_game_for_postgame_refresh(
        _game(), schedule_date=GAME_DATE, boxscore=boxscore or _boxscore(), force=True,
    )
    db.session.commit()
    return result


def _appearances(boxscore=None):
    payload = boxscore or _boxscore()
    return extraction.extract_game_appearances(
        game=_game(),
        pitching_lines=sync_service._extract_pitching_lines_from_boxscore(payload),
        pitcher_order=sync_service._pitcher_order_by_side(payload),
        game_date=GAME_DATE,
    )


def test_final_game_persists_complete_supported_lines_and_preserves_ownership(app):
    with app.app_context():
        _seed_pitchers()
        result = _ingest()
        rows = {row.pitcher.mlb_id: row for row in GameLog.query.all()}
        reliever = rows[1002]

        assert result['logs_added'] == 4
        assert reliever.games_started == 0
        assert reliever.innings_pitched_outs == 3
        assert reliever.pitches_thrown == 17
        assert reliever.strikes == 10
        assert reliever.batters_faced == 5
        assert reliever.hits_allowed == 1
        assert reliever.runs_allowed == 0
        assert reliever.earned_runs == 0
        assert reliever.walks == 1
        assert reliever.strikeouts == 2
        assert reliever.home_runs_allowed == 0
        assert reliever.hit_batters == 1
        assert reliever.wild_pitches == 1
        assert reliever.games_finished == 1
        assert reliever.inherited_runners == 2
        assert reliever.inherited_runners_scored == 1
        assert reliever.save_situation is True
        assert reliever.hold is True
        assert reliever.blown_save is False
        assert reliever.appearance_team_id == HOME_TEAM
        assert reliever.source_endpoint == f'/game/{GAME_PK}/boxscore'
        assert reliever.source_revision
        assert reliever.source_acquired_at is not None

        reliever.pitcher.team_id = AWAY_TEAM
        db.session.commit()
        _ingest()
        assert GameLog.query.filter_by(id=reliever.id).one().appearance_team_id == HOME_TEAM
        assert GameLog.query.count() == 4


def test_missing_supported_fields_remain_unknown(app):
    with app.app_context():
        _seed_pitchers()
        _ingest(_boxscore(missing_optional=True))
        pitcher_id = Pitcher.query.filter_by(mlb_id=1002).one().id
        row = GameLog.query.filter_by(pitcher_id=pitcher_id, mlb_game_pk=GAME_PK).one()
        assert row.hit_batters is None
        assert row.wild_pitches is None
        assert row.save_situation is None
        assert row.hold is None
        assert row.blown_save is None
        assert row.win is None
        assert row.loss is None
        assert row.save is None


def test_pitch_events_are_complete_idempotent_and_correction_aware(app):
    with app.app_context():
        _seed_pitchers()
        box = _boxscore()
        _ingest(box)

        first = play_by_play_foundation.process_final_play_by_play_foundation(
            _game(), boxscore=box, play_by_play=_play_by_play(), game_date=GAME_DATE,
            observation_sequence=1,
        )
        db.session.commit()
        second = play_by_play_foundation.process_final_play_by_play_foundation(
            _game(), boxscore=box, play_by_play=_play_by_play(), game_date=GAME_DATE,
            observation_sequence=1,
        )
        db.session.commit()

        assert first['pitch_rows']['inserted'] == 4
        assert second['pitch_rows']['inserted'] == 0
        assert second['pitch_rows']['updated'] == 0
        assert second['pitch_rows']['unchanged'] == 4
        assert GamePitchEvent.query.filter_by(mlb_game_pk=GAME_PK).count() == 4

        rich = GamePitchEvent.query.filter_by(
            mlb_game_pk=GAME_PK,
            pitcher_mlb_id=1002,
            at_bat_index=1,
            play_event_index=0,
        ).one()
        assert rich.pitch_type_code == 'FF'
        assert rich.start_speed == 97.2
        assert rich.spin_rate == 2488
        assert rich.pfx_x == -0.55
        assert rich.release_position_x == -1.8
        assert rich.extension == 6.7
        assert rich.zone == 5
        assert rich.plate_x == 0.15
        assert rich.call_description == 'In play, out(s)'
        assert rich.batted_ball_event_type == 'field_out'
        assert rich.launch_speed == 88.4
        assert rich.launch_angle == -3.0
        assert rich.batted_ball_trajectory == 'ground_ball'

        corrected = play_by_play_foundation.process_final_play_by_play_foundation(
            _game(), boxscore=box, play_by_play=_play_by_play(corrected=True),
            game_date=GAME_DATE, observation_sequence=2,
        )
        db.session.commit()
        assert corrected['corrected'] is True
        assert corrected['pitch_rows']['updated'] == 1
        assert corrected['pitch_rows']['inserted'] == 1
        assert GamePitchEvent.query.filter_by(
            mlb_game_pk=GAME_PK, is_current=True,
        ).count() == 5
        assert GamePitchEvent.query.filter_by(
            mlb_game_pk=GAME_PK, at_bat_index=1, play_event_index=0,
        ).one().start_speed == 98.1

        removed = play_by_play_foundation.process_final_play_by_play_foundation(
            _game(), boxscore=box, play_by_play=_play_by_play(), game_date=GAME_DATE,
            observation_sequence=3,
        )
        db.session.commit()
        assert removed['pitch_rows']['superseded'] == 1
        assert GamePitchEvent.query.filter_by(
            mlb_game_pk=GAME_PK, is_current=True,
        ).count() == 4
        assert GamePitchEvent.query.filter_by(mlb_game_pk=GAME_PK).count() == 5


def test_affected_entities_and_workload_shadow_comparison_are_explicit(app):
    with app.app_context():
        _seed_pitchers()
        _ingest()
        impact = cu01.build_game_impact(_appearances())

        assert impact['affected_pitcher_mlb_ids'] == [1002, 2002]
        assert impact['affected_team_ids'] == [AWAY_TEAM, HOME_TEAM]
        assert impact['relief_appearance_count'] == 2
        assert impact['publication_affected'] is False
        comparison = impact['workload_comparison']
        assert comparison['coverage_complete'] is True
        assert comparison['parity'] is True
        assert comparison['differing_fields'] == []
        assert set(comparison['equivalent_fields']) == {
            'appearance_team_id', 'game_date', 'games_started',
            'innings_pitched_outs', 'pitches_thrown',
        }
        assert 'hit_batters' in comparison['newly_captured_appearance_fields']
        assert 'velocity_spin_and_movement' in comparison['newly_captured_pitch_domains']
        assert 'innings_pitched' in comparison['derived_fields_excluded']


def test_cu01_does_not_publish_or_mutate_historical_snapshot(app):
    with app.app_context():
        _seed_pitchers()
        run = SyncRun(
            source='scheduled_sync',
            job_name='daily_sync',
            started_at=datetime(2026, 8, 27, 9, 59, 0),
            completed_at=datetime(2026, 8, 27, 10, 1, 0),
            status='success',
            stage='published',
        )
        db.session.add(run)
        db.session.flush()
        snapshot = DashboardSnapshot(
            snapshot_type='bullpen_dashboard',
            sync_run_id=run.id,
            status='ready',
            is_published=True,
            payload={'immutable': 'historical'},
            payload_version=1,
            data_through=date(2026, 8, 26),
            availability_reference_date=date(2026, 8, 27),
            snapshot_generated_at=datetime(2026, 8, 27, 10, 0, 0),
            published_at=datetime(2026, 8, 27, 10, 1, 0),
            source='scheduled_sync',
        )
        db.session.add(snapshot)
        db.session.commit()
        snapshot_id = snapshot.id

        _ingest()
        impact = cu01.build_game_impact(_appearances())

        stored = DashboardSnapshot.query.filter_by(id=snapshot_id).one()
        assert DashboardSnapshot.query.count() == 1
        assert stored.payload == {'immutable': 'historical'}
        assert stored.is_published is True
        assert impact['publication_affected'] is False
        assert PlayByPlayProcessedGame.query.count() == 0


def test_game_driven_write_exposes_affected_entities_and_optional_pitch_evidence(
    app, monkeypatch,
):
    class Client:
        def get_game_boxscore(self, game_pk):
            assert game_pk == GAME_PK
            return _boxscore()

        def get_game_play_by_play(self, game_pk):
            assert game_pk == GAME_PK
            return _play_by_play()

    with app.app_context():
        _seed_pitchers()
        schedule_final_game(GAME_PK, game_date=GAME_DATE)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', Client())

        report = game_driven_ingestion.run_game_driven_ingestion(
            GAME_DATE, mode=game_driven_ingestion.MODE_WRITE,
        )

        assert report['status'] == 'complete'
        assert report['affected_pitcher_mlb_ids'] == [1002, 2002]
        assert report['affected_team_ids'] == [AWAY_TEAM, HOME_TEAM]
        assert report['games'][0]['impact']['workload_comparison']['parity'] is True
        optional = report['games'][0]['optional_source_domains']['final_play_by_play']
        assert optional['processing_status'] == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED
        assert optional['pitch_rows']['inserted'] == 4
        assert optional['publication_affected'] is False
        assert game_driven_ingestion.publication_authoritative(
            game_driven_ingestion.MODE_WRITE
        ) is False
        assert GamePitchEvent.query.filter_by(
            mlb_game_pk=GAME_PK, is_current=True,
        ).count() == 4


def test_optional_pitch_failure_is_observable_without_blocking_canonical_lines(
    app, monkeypatch,
):
    class Client:
        def get_game_boxscore(self, game_pk):
            assert game_pk == GAME_PK
            return _boxscore()

        def get_game_play_by_play(self, game_pk):
            assert game_pk == GAME_PK
            raise TimeoutError('optional play-by-play unavailable')

    with app.app_context():
        _seed_pitchers()
        schedule_final_game(GAME_PK, game_date=GAME_DATE)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', Client())

        report = game_driven_ingestion.run_game_driven_ingestion(
            GAME_DATE, mode=game_driven_ingestion.MODE_WRITE,
        )

        assert report['status'] == 'complete'
        assert GameLog.query.filter_by(mlb_game_pk=GAME_PK).count() == 4
        optional = report['games'][0]['optional_source_domains']['final_play_by_play']
        assert optional['processing_status'] == PlayByPlayProcessedGame.STATUS_INCOMPLETE
        assert optional['reason'] == 'play_by_play_fetch_failed'
        assert optional['publication_affected'] is False
        assert GamePitchEvent.query.filter_by(mlb_game_pk=GAME_PK).count() == 0


def _reviewed_game_driven_run():
    shadow = game_driven_ingestion.run_game_driven_ingestion(
        GAME_DATE, mode=game_driven_ingestion.MODE_SHADOW,
    )
    return game_driven_ingestion.run_game_driven_ingestion(
        GAME_DATE,
        mode=game_driven_ingestion.MODE_WRITE,
        expected_plan_fingerprint=shadow['complete_reconciliation_fingerprint'],
    )


def test_affected_entities_are_mutation_scoped_across_replay_and_restart(
    app, monkeypatch,
):
    class Client:
        def __init__(self):
            self.boxscore = _boxscore()
            self.pbp_fails = False

        def get_game_boxscore(self, game_pk):
            return self.boxscore

        def get_game_play_by_play(self, game_pk):
            if self.pbp_fails:
                raise TimeoutError('controlled optional failure')
            return _play_by_play()

    with app.app_context():
        _seed_pitchers()
        schedule_final_game(GAME_PK, game_date=GAME_DATE)
        db.session.commit()
        client = Client()
        monkeypatch.setattr(sync_service, 'mlb_client', client)

        first = _reviewed_game_driven_run()
        assert first['affected_pitcher_mlb_ids'] == [1002, 2002]
        assert first['affected_team_ids'] == [AWAY_TEAM, HOME_TEAM]

        second = _reviewed_game_driven_run()
        assert second['rows_inserted'] == 0
        assert second['rows_updated'] == 0
        assert second['affected_pitcher_mlb_ids'] == []
        assert second['affected_team_ids'] == []

        db.session.remove()
        third = _reviewed_game_driven_run()
        assert third['rows_inserted'] == 0
        assert third['rows_updated'] == 0
        assert third['affected_pitcher_mlb_ids'] == []
        assert third['affected_team_ids'] == []

        home_reliever = Pitcher.query.filter_by(mlb_id=1002).one()
        home_reliever.team_id = AWAY_TEAM
        client.boxscore = _boxscore()
        client.boxscore['teams']['home']['players']['ID1002']['stats']['pitching'][
            'numberOfPitches'
        ] = 18
        db.session.commit()
        correction = _reviewed_game_driven_run()
        assert correction['affected_pitcher_mlb_ids'] == [1002]
        assert correction['affected_team_ids'] == [HOME_TEAM]
        assert GameLog.query.filter_by(
            pitcher_id=home_reliever.id, mlb_game_pk=GAME_PK,
        ).one().appearance_team_id == HOME_TEAM

        client.pbp_fails = True
        failure_replay = _reviewed_game_driven_run()
        assert failure_replay['affected_pitcher_mlb_ids'] == []
        assert failure_replay['affected_team_ids'] == []
        assert failure_replay['games'][0]['optional_source_domains'][
            'final_play_by_play'
        ]['reason'] == 'play_by_play_fetch_failed'


def test_persisted_observation_order_rejects_stale_ambiguous_and_weaker_inputs(app):
    with app.app_context():
        _seed_pitchers()
        box = _boxscore()
        _ingest(box)
        appearances = _appearances(box)
        first = play_by_play_foundation.process_final_play_by_play_foundation(
            _game(), boxscore=box, play_by_play=_play_by_play(),
            game_date=GAME_DATE, observation_sequence=1,
        )
        db.session.commit()
        identical = play_by_play_foundation.process_final_play_by_play_foundation(
            _game(), boxscore=box, play_by_play=_play_by_play(),
            game_date=GAME_DATE, observation_sequence=1,
        )
        corrected_payload = _play_by_play(corrected=True)
        newer = play_by_play_foundation.process_final_play_by_play_foundation(
            _game(), boxscore=box, play_by_play=corrected_payload,
            game_date=GAME_DATE, observation_sequence=2,
        )
        db.session.commit()
        canonical = GamePitchEvent.query.filter_by(
            mlb_game_pk=GAME_PK, at_bat_index=1, play_event_index=0,
        ).one()
        canonical_fingerprint = canonical.event_fingerprint
        stale = play_by_play_foundation.process_final_play_by_play_foundation(
            _game(), boxscore=box, play_by_play=_play_by_play(),
            game_date=GAME_DATE, observation_sequence=1,
        )
        ambiguous = play_by_play_foundation.process_final_play_by_play_foundation(
            _game(), boxscore=box, play_by_play=_play_by_play(), game_date=GAME_DATE,
        )
        weaker = play_by_play_foundation.process_final_play_by_play_foundation(
            _game(), boxscore=box, play_by_play=corrected_payload,
            game_date=GAME_DATE, observation_sequence=3,
            source_authority='captured_fixture:unreviewed',
        )
        db.session.commit()

        assert first['observation_order_status'] == 'initial_accepted'
        assert identical['observation_order_status'] == 'identical'
        assert newer['observation_order_status'] == 'newer_accepted'
        assert stale['observation_order_status'] == 'stale_rejected'
        assert ambiguous['observation_order_status'] == 'ambiguous_rejected'
        assert weaker['observation_order_status'] == 'weaker_authority_rejected'
        assert canonical.start_speed == 98.1
        assert canonical.event_fingerprint == canonical_fingerprint
        assert cu01.build_game_impact(
            appearances, appearance_mutations=[],
            pitch_mutations=newer['pitch_rows'],
        )['affected_pitcher_mlb_ids'] == [1002]
        assert cu01.build_game_impact(
            appearances, appearance_mutations=[],
            pitch_mutations=stale['pitch_rows'],
        )['affected_pitcher_mlb_ids'] == []

        db.session.remove()
        stale_after_restart = (
            play_by_play_foundation.process_final_play_by_play_foundation(
                _game(), boxscore=box, play_by_play=_play_by_play(),
                game_date=GAME_DATE, observation_sequence=1,
            )
        )
        assert stale_after_restart['observation_order_status'] == 'stale_rejected'
        assert GamePitchEvent.query.filter_by(
            mlb_game_pk=GAME_PK, at_bat_index=1, play_event_index=0,
        ).one().event_fingerprint == canonical_fingerprint


def test_batted_ball_facts_belong_only_to_the_owning_pitch(app):
    with app.app_context():
        _seed_pitchers()
        box = _boxscore()
        _ingest(box)
        payload = _play_by_play()
        plate_appearance = payload['allPlays'][1]
        ball = _pitch_play(1, 1002, 'top', event_index=0)['playEvents'][0]
        ball['details'].update({
            'code': 'B', 'description': 'Ball', 'isBall': True,
            'isStrike': False,
        })
        foul = _pitch_play(1, 1002, 'top', event_index=1)['playEvents'][0]
        foul['details'].update({'code': 'F', 'description': 'Foul'})
        owner = _pitch_play(
            1, 1002, 'top', rich=True, event_index=2,
        )['playEvents'][0]
        plate_appearance['playEvents'] = [ball, foul, owner]
        payload['allPlays'][0]['result']['eventType'] = 'strikeout'
        payload['allPlays'][2]['result']['eventType'] = 'walk'
        payload['allPlays'][3]['result']['eventType'] = 'hit_by_pitch'
        home_run = _pitch_play(4, 1002, 'top', rich=True)
        home_run['result']['eventType'] = 'home_run'
        payload['allPlays'].append(home_run)

        result = play_by_play_foundation.process_final_play_by_play_foundation(
            _game(), boxscore=box, play_by_play=payload,
            game_date=GAME_DATE, observation_sequence=1,
        )
        db.session.commit()
        rows = GamePitchEvent.query.filter_by(
            mlb_game_pk=GAME_PK, at_bat_index=1,
        ).order_by(GamePitchEvent.play_event_index).all()
        assert result['pitch_rows']['inserted'] == 7
        assert [row.batted_ball_event_type for row in rows] == [None, None, 'field_out']
        assert [row.launch_speed for row in rows] == [None, None, 88.4]
        assert all(
            row.batted_ball_event_type is None
            for row in GamePitchEvent.query.filter(
                GamePitchEvent.mlb_game_pk == GAME_PK,
                GamePitchEvent.at_bat_index.in_([0, 2, 3]),
            ).all()
        )
        assert GamePitchEvent.query.filter_by(
            mlb_game_pk=GAME_PK, at_bat_index=4,
        ).one().batted_ball_event_type == 'home_run'

        replay = play_by_play_foundation.process_final_play_by_play_foundation(
            _game(), boxscore=box, play_by_play=payload,
            game_date=GAME_DATE, observation_sequence=1,
        )
        assert replay['pitch_rows']['updated'] == 0
        assert replay['pitch_rows']['unchanged'] == 7
