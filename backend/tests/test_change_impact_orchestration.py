"""CU-03 change-to-impact orchestration contracts."""

from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest
from flask import Flask

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.game_observation_state import GameObservationState
from models.pitcher import Pitcher
from models.play_by_play_foundation import GamePitchEvent
from services import change_impact_orchestration as orchestration
from services import game_change_detection as detection
from services import game_driven_ingestion
from services import game_finality
from services import sync as sync_service
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.game_driven_fixtures import schedule_final_game
from tests.test_continuous_reliever_ingestion import (
    AWAY_TEAM,
    GAME_DATE,
    GAME_PK,
    HOME_TEAM,
    _boxscore,
    _play_by_play,
    _seed_pitchers,
)
from tests.test_game_change_detection import _feed
from utils.db import db


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


def _change(
    classification,
    *,
    differences=None,
    finality=game_finality.NOT_FINAL,
    reason='controlled real-shape observation',
):
    return detection.GameChangeResult(
        game_pk=GAME_PK,
        classification=classification,
        changed=classification in {
            detection.NEW_GAME, detection.CHANGED, detection.FINALIZED,
            detection.CORRECTED,
        },
        previous_observation_identity='previous',
        current_observation_identity='current',
        finality_state=finality,
        source_authority=detection.SOURCE_AUTHORITY,
        source_observed_at='2026-08-27T23:00:00',
        detected_at='2026-08-27T23:00:01',
        differences=differences or {},
        reason=reason,
        accepted=classification not in {
            detection.STALE_OBSERVATION, detection.AMBIGUOUS_OBSERVATION,
            detection.SOURCE_FAILURE,
        },
    )


@pytest.mark.parametrize(
    ('change', 'expected_decision', 'expected_reason'),
    [
        (_change(detection.UNCHANGED), orchestration.NO_ACTION, 'observation_unchanged'),
        (_change(detection.NEW_GAME), orchestration.NO_ACTION, 'first_observation_only'),
        (_change(detection.CHANGED), orchestration.NO_ACTION, 'no_final_canonical_action'),
        (_change(detection.CHANGED, differences={'linescore.pitcher_id': {}}),
         orchestration.DEFER_LIVE_CANONICAL,
         'cu01_final_game_only_live_bullpen_change'),
        (_change(detection.CHANGED, differences={'play.pitch_event_count': {}}),
         orchestration.DEFER_LIVE_CANONICAL,
         'cu01_final_game_only_live_bullpen_change'),
        (_change(
            detection.CHANGED, differences={'status.detailed': {}},
            finality=game_finality.POSTPONED,
        ), orchestration.NO_ACTION, 'no_final_canonical_action'),
        (_change(
            detection.CHANGED, differences={'status.status_code': {}},
            finality=game_finality.SUSPENDED,
        ), orchestration.NO_ACTION, 'no_final_canonical_action'),
        (_change(
            detection.CHANGED, differences={'play.all_play_count': {}},
            finality=game_finality.NOT_FINAL,
        ), orchestration.DEFER_LIVE_CANONICAL,
         'cu01_final_game_only_live_bullpen_change'),
        (_change(detection.STALE_OBSERVATION), orchestration.REJECT_OBSERVATION,
         detection.STALE_OBSERVATION),
        (_change(detection.AMBIGUOUS_OBSERVATION), orchestration.REJECT_OBSERVATION,
         detection.AMBIGUOUS_OBSERVATION),
        (_change(detection.STALE_OBSERVATION, reason='weaker source authority'),
         orchestration.REJECT_OBSERVATION, 'weaker_authority'),
        (_change(detection.SOURCE_FAILURE), orchestration.SOURCE_FAILURE,
         'detection_source_failure'),
    ],
)
def test_nonfinal_decision_matrix_never_calls_cu01(
    change, expected_decision, expected_reason,
):
    def forbidden(*args, **kwargs):
        raise AssertionError('CU-01 must not be invoked')

    result = orchestration.orchestrate_game_change(
        change,
        allow_canonical_write=True,
        expected_plan_fingerprint='reviewed',
        canonical_ingestor=forbidden,
    )

    assert result.decision == expected_decision
    assert result.reason_code == expected_reason
    assert result.cu01_invocations == 0
    assert result.canonical_mutation_performed is False
    assert result.affected_pitcher_ids == ()
    assert result.affected_team_ids == ()
    assert result.downstream_recomputation_triggered is False
    assert result.publication_affected is False


@pytest.mark.parametrize(
    ('classification', 'decision'),
    [
        (detection.FINALIZED, orchestration.INGEST_FINAL_GAME),
        (detection.CORRECTED, orchestration.INSPECT_POST_FINAL_CORRECTION),
    ],
)
def test_final_actions_require_explicit_write_and_reviewed_plan(
    classification, decision,
):
    change = _change(
        classification, finality=game_finality.FINAL_AND_USABLE,
    )
    without_write = orchestration.orchestrate_game_change(change)
    without_fingerprint = orchestration.orchestrate_game_change(
        change, allow_canonical_write=True,
    )

    assert without_write.decision == decision
    assert without_write.orchestration_status == orchestration.STATUS_AUTHORIZATION_REQUIRED
    assert without_write.cu01_invocations == 0
    assert without_fingerprint.reason_code == 'reviewed_plan_fingerprint_required'
    assert without_fingerprint.cu01_invocations == 0


def _cu01_report(*, optional_status='fully_processed', inserted=2, pitches=3):
    return {
        'status': 'complete',
        'rows_inserted': inserted,
        'rows_updated': 0,
        'rows_unchanged': 2 if not inserted else 0,
        'pitcher_identity_mutations': 0,
        'affected_pitcher_mlb_ids': [1002, 2002] if inserted else [],
        'affected_team_ids': [AWAY_TEAM, HOME_TEAM] if inserted else [],
        'games': [{
            'impact': {'affected_pitcher_ids': [12, 22] if inserted else []},
            'optional_source_domains': {'final_play_by_play': {
                'processing_status': optional_status,
                'pitch_rows': {
                    'inserted': pitches if inserted else 0,
                    'updated': 0,
                    'unchanged': 0 if inserted else pitches,
                    'superseded': 0,
                },
            }},
        }],
    }


def test_finality_transition_invokes_cu01_once_and_uses_mutation_scoped_impact():
    calls = []

    def ingestor(change, *, expected_plan_fingerprint):
        calls.append((change.game_pk, expected_plan_fingerprint))
        return _cu01_report()

    result = orchestration.orchestrate_game_change(
        _change(detection.FINALIZED, finality=game_finality.FINAL_AND_USABLE),
        allow_canonical_write=True,
        expected_plan_fingerprint='reviewed-plan',
        canonical_ingestor=ingestor,
    )

    assert calls == [(GAME_PK, 'reviewed-plan')]
    assert result.cu01_invocations == 1
    assert result.game_log_inserted == 2
    assert result.pitch_inserted == 3
    assert result.canonical_mutation_performed is True
    assert result.affected_pitcher_mlb_ids == (1002, 2002)
    assert result.affected_pitcher_ids == (12, 22)
    assert result.affected_team_ids == (AWAY_TEAM, HOME_TEAM)
    assert result.publication_affected is False
    assert result.downstream_recomputation_triggered is False


def test_continuous_plan_fingerprint_is_derived_from_current_final_observation(
    app, monkeypatch,
):
    with app.app_context():
        db.session.add(GameObservationState(
            mlb_game_pk=GAME_PK,
            observation_fingerprint='a' * 64,
            observation={'identity': {'official_date': GAME_DATE.isoformat()}},
            source_authority=detection.SOURCE_AUTHORITY,
            source_endpoint='schedule-feed',
            finality_state=game_finality.FINAL_AND_USABLE,
            last_classification=detection.FINALIZED,
        ))
        db.session.commit()
        calls = []

        def plan(reference_date, **kwargs):
            calls.append((reference_date, kwargs))
            return {
                'status': 'complete',
                'complete_reconciliation_fingerprint': 'current-plan',
            }

        monkeypatch.setattr(
            orchestration.cu01, 'run_game_driven_ingestion', plan,
        )
        fingerprint = orchestration.derive_current_plan_fingerprint(
            _change(
                detection.FINALIZED,
                finality=game_finality.FINAL_AND_USABLE,
            )
        )

    assert fingerprint == 'current-plan'
    assert calls == [(
        GAME_DATE,
        {
            'mode': game_driven_ingestion.MODE_SHADOW,
            'only_game_pks': [GAME_PK],
        },
    )]


def test_idempotent_canonical_replay_returns_zero_impact():
    result = orchestration.orchestrate_game_change(
        _change(detection.CORRECTED, finality=game_finality.FINAL_AND_USABLE),
        allow_canonical_write=True,
        expected_plan_fingerprint='reviewed-noop',
        canonical_ingestor=lambda *args, **kwargs: _cu01_report(inserted=0, pitches=3),
    )

    assert result.cu01_invocations == 1
    assert result.canonical_mutation_performed is False
    assert result.affected_pitcher_mlb_ids == ()
    assert result.affected_pitcher_ids == ()
    assert result.affected_team_ids == ()
    assert result.game_log_unchanged == 2
    assert result.pitch_unchanged == 3


def test_optional_pbp_failure_does_not_discard_core_canonical_impact():
    result = orchestration.orchestrate_game_change(
        _change(detection.FINALIZED, finality=game_finality.FINAL_AND_USABLE),
        allow_canonical_write=True,
        expected_plan_fingerprint='reviewed-plan',
        canonical_ingestor=lambda *args, **kwargs: _cu01_report(
            optional_status='incomplete', pitches=0,
        ),
    )

    assert result.orchestration_status == orchestration.STATUS_RECONCILED
    assert result.game_log_inserted == 2
    assert result.optional_pbp_status == 'incomplete'
    assert result.affected_team_ids == (AWAY_TEAM, HOME_TEAM)


def test_core_source_failure_is_fail_closed_and_emits_no_impact():
    result = orchestration.orchestrate_game_change(
        _change(detection.FINALIZED, finality=game_finality.FINAL_PENDING_DATA),
        allow_canonical_write=True,
        expected_plan_fingerprint='reviewed-plan',
        canonical_ingestor=lambda *args, **kwargs: {
            'status': 'failed', 'failure_classes': {'boxscore_fetch_failed': 1},
        },
    )

    assert result.orchestration_status == orchestration.STATUS_CANONICAL_FAILED
    assert result.source_failure_state == 'boxscore_fetch_failed'
    assert result.canonical_mutation_performed is False
    assert result.affected_pitcher_ids == ()
    assert result.affected_team_ids == ()


def test_position_player_current_identity_is_not_rewritten_by_orchestration(app):
    with app.app_context():
        player = Pitcher(
            mlb_id=5555, full_name='Position Player', team_id=HOME_TEAM,
            team_abbreviation='HOM', active=True, position='CF',
        )
        db.session.add(player)
        db.session.commit()
        before = (player.team_id, player.position)

        report = _cu01_report()
        report['affected_pitcher_mlb_ids'] = [5555]
        result = orchestration.orchestrate_game_change(
            _change(detection.FINALIZED, finality=game_finality.FINAL_AND_USABLE),
            allow_canonical_write=True,
            expected_plan_fingerprint='reviewed-plan',
            canonical_ingestor=lambda *args, **kwargs: report,
        )

        db.session.refresh(player)
        assert result.affected_pitcher_mlb_ids == (5555,)
        assert (player.team_id, player.position) == before


def test_real_cu02_finality_handoff_to_reviewed_cu01_and_replay_stop(app, monkeypatch):
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
        sentinel = DashboardSnapshot(
            snapshot_type='cu03_sentinel', status='ready', is_published=False,
            payload={'immutable': 'before'}, data_through=GAME_DATE,
        )
        db.session.add(sentinel)
        db.session.commit()
        sentinel_id = sentinel.id
        monkeypatch.setattr(sync_service, 'mlb_client', Client())

        def observation(*, timestamp, status='Live', code='I', inning=8, outs=1):
            payload = deepcopy(_feed(
                timestamp=timestamp, status=status, code=code,
                inning=inning, outs=outs,
            ))
            payload['gamePk'] = GAME_PK
            payload['gameData']['datetime'].update({
                'dateTime': f'{GAME_DATE.isoformat()}T19:00:00Z',
                'originalDate': GAME_DATE.isoformat(),
                'officialDate': GAME_DATE.isoformat(),
            })
            payload['gameData']['teams'] = {
                'away': {'id': AWAY_TEAM}, 'home': {'id': HOME_TEAM},
            }
            return payload

        new_game = detection.observe_game_change(
            GAME_PK, payload=observation(timestamp='20260827_220000'),
        )
        change = detection.observe_game_change(
            GAME_PK,
            payload=observation(
                timestamp='20260827_230000', status='Final', code='F',
                inning=9, outs=3,
            ),
        )
        assert new_game.classification == detection.NEW_GAME
        assert change.classification == detection.FINALIZED

        shadow = game_driven_ingestion.run_game_driven_ingestion(
            GAME_DATE,
            mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[GAME_PK],
        )
        first = orchestration.orchestrate_game_change(
            change,
            allow_canonical_write=True,
            expected_plan_fingerprint=shadow['complete_reconciliation_fingerprint'],
        )

        assert first.cu01_invocations == 1
        assert first.game_log_inserted == 4
        assert first.pitch_inserted == 4
        assert first.affected_pitcher_mlb_ids == (1002, 2002)
        assert first.affected_team_ids == (AWAY_TEAM, HOME_TEAM)
        stored_sentinel = DashboardSnapshot.query.filter_by(id=sentinel_id).one()
        assert DashboardSnapshot.query.count() == 1
        assert stored_sentinel.payload == {'immutable': 'before'}
        assert stored_sentinel.is_published is False
        assert GameLog.query.filter_by(mlb_game_pk=GAME_PK).count() == 4
        assert GamePitchEvent.query.filter_by(mlb_game_pk=GAME_PK).count() == 4

        replay_shadow = game_driven_ingestion.run_game_driven_ingestion(
            GAME_DATE,
            mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[GAME_PK],
        )
        direct_replay = orchestration.orchestrate_game_change(
            change,
            allow_canonical_write=True,
            expected_plan_fingerprint=(
                replay_shadow['complete_reconciliation_fingerprint']
            ),
        )
        assert direct_replay.cu01_invocations == 1
        assert direct_replay.game_log_inserted == 0
        assert direct_replay.game_log_updated == 0
        assert direct_replay.pitch_inserted == 0
        assert direct_replay.pitch_updated == 0
        assert direct_replay.pitch_superseded == 0
        assert direct_replay.affected_pitcher_mlb_ids == ()
        assert direct_replay.affected_team_ids == ()

        unchanged = detection.observe_game_change(
            GAME_PK,
            payload=observation(
                timestamp='20260827_230000', status='Final', code='F',
                inning=9, outs=3,
            ),
        )
        assert unchanged.classification == detection.UNCHANGED
        second = orchestration.orchestrate_game_change(
            unchanged,
            allow_canonical_write=True,
            expected_plan_fingerprint='must-not-be-used',
            canonical_ingestor=lambda *args, **kwargs: pytest.fail('unexpected CU-01 call'),
        )
        db.session.remove()
        third = orchestration.orchestrate_game_change(
            unchanged,
            allow_canonical_write=True,
            expected_plan_fingerprint='must-not-be-used',
            canonical_ingestor=lambda *args, **kwargs: pytest.fail('unexpected CU-01 call'),
        )

        assert second.cu01_invocations == 0
        assert third.cu01_invocations == 0
        assert second.affected_team_ids == ()
        assert third.affected_team_ids == ()
        assert GameLog.query.filter_by(mlb_game_pk=GAME_PK).count() == 4
        assert GamePitchEvent.query.filter_by(mlb_game_pk=GAME_PK).count() == 4


def test_stale_reviewed_plan_is_rejected_by_cu01_before_canonical_mutation(
    app, monkeypatch,
):
    class Client:
        def __init__(self):
            self.boxscore = _boxscore()

        def get_game_boxscore(self, game_pk):
            assert game_pk == GAME_PK
            return self.boxscore

        def get_game_play_by_play(self, game_pk):
            pytest.fail('PBP must not be fetched before plan authorization')

    with app.app_context():
        _seed_pitchers()
        schedule_final_game(GAME_PK, game_date=GAME_DATE)
        db.session.add(GameObservationState(
            mlb_game_pk=GAME_PK,
            observation_fingerprint='accepted-final-observation',
            observation={'identity': {'official_date': GAME_DATE.isoformat()}},
            source_authority=detection.SOURCE_AUTHORITY,
            source_endpoint=detection.SOURCE_ENDPOINT.format(game_pk=GAME_PK),
            source_observed_at=datetime(2026, 8, 27, 23, 0),
            finality_state=game_finality.FINAL_PENDING_DATA,
            last_classification=detection.FINALIZED,
        ))
        db.session.commit()
        client = Client()
        monkeypatch.setattr(sync_service, 'mlb_client', client)

        reviewed = game_driven_ingestion.run_game_driven_ingestion(
            GAME_DATE,
            mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[GAME_PK],
        )
        client.boxscore['teams']['home']['players']['ID1002']['stats']['pitching'][
            'numberOfPitches'
        ] = 18

        result = orchestration.orchestrate_game_change(
            _change(
                detection.FINALIZED,
                finality=game_finality.FINAL_PENDING_DATA,
            ),
            allow_canonical_write=True,
            expected_plan_fingerprint=(
                reviewed['complete_reconciliation_fingerprint']
            ),
        )

        assert result.cu01_invocations == 1
        assert result.orchestration_status == orchestration.STATUS_CANONICAL_FAILED
        assert result.source_failure_state == 'plan_fingerprint_mismatch'
        assert result.canonical_mutation_performed is False
        assert result.affected_pitcher_ids == ()
        assert result.affected_team_ids == ()
        assert GameLog.query.count() == 0
        assert GamePitchEvent.query.count() == 0


def test_script_is_non_scheduled_and_disables_auto_sync_before_app_import():
    source = (
        Path(__file__).resolve().parents[1] / 'scripts/orchestrate_game_change.py'
    ).read_text(encoding='utf-8')
    assert source.index("os.environ['AUTO_SYNC'] = 'false'") < source.index('from app import app')
    assert 'while True' not in source
    assert 'apscheduler' not in source.lower()
    assert 'threading' not in source.lower()
