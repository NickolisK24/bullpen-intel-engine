"""CU-02 persisted, non-authoritative game change detection contracts."""

from copy import deepcopy
from datetime import date

import pytest
from flask import Flask

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.game_observation_state import GameObservationState
from models.play_by_play_foundation import GamePitchEvent
from models.share_artifact import ShareArtifact
from services import game_change_detection as detection
from services.mlb_api import MlbApiFetchError
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


GAME_PK = 823826


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


def _feed(*, timestamp='20260826_010000', status='Live', code='I', inning=8,
          outs=1, pitcher=687941, pitches=2, event_type='strikeout'):
    """Small real-shape capture based on MLB gamePk 823826 (ATL at MIA)."""
    events = [
        {'index': index, 'type': 'pitch', 'isPitch': True,
         'playId': f'real-play-{index}', 'details': {'eventType': 'pitch'}}
        for index in range(pitches)
    ]
    play = {
        'atBatIndex': 89,
        'about': {'inning': inning, 'halfInning': 'bottom', 'isComplete': False},
        'matchup': {'pitcher': {'id': pitcher}, 'batter': {'id': 640459}},
        'result': {'eventType': event_type},
        'playEvents': events,
    }
    return {
        'copyright': 'Copyright MLB Advanced Media, L.P.',
        'gamePk': GAME_PK,
        'metaData': {'wait': 10, 'timeStamp': timestamp},
        'gameData': {
            'datetime': {
                'dateTime': '2026-08-25T22:40:00Z',
                'originalDate': '2026-08-25',
                'officialDate': '2026-08-25',
            },
            'game': {'type': 'R', 'doubleHeader': 'N', 'gameNumber': 1},
            'status': {
                'abstractGameState': 'Final' if status == 'Final' else 'Live',
                'codedGameState': code,
                'detailedState': status,
                'statusCode': code,
            },
            'teams': {'away': {'id': 111}, 'home': {'id': 146}},
        },
        'liveData': {
            'linescore': {
                'currentInning': inning, 'currentInningOrdinal': f'{inning}th',
                'inningState': 'Middle', 'inningHalf': 'Bottom',
                'isTopInning': False, 'scheduledInnings': 9,
                'balls': 1, 'strikes': 2, 'outs': outs,
                'teams': {
                    'away': {'runs': 7, 'hits': 7, 'errors': 2},
                    'home': {'runs': 3, 'hits': 7, 'errors': 0},
                },
                'defense': {'pitcher': {'id': pitcher}},
                'offense': {'batter': {'id': 640459}},
            },
            'plays': {'allPlays': [play], 'currentPlay': play},
        },
    }


def test_first_identical_and_restart_replay_are_new_then_unchanged(app):
    payload = _feed()
    first = detection.observe_game_change(GAME_PK, payload=payload)
    row = GameObservationState.query.one()
    persisted_updated_at = row.updated_at
    second = detection.observe_game_change(GAME_PK, payload=deepcopy(payload))
    db.session.remove()  # process/application restart boundary
    third = detection.observe_game_change(GAME_PK, payload=deepcopy(payload))

    assert first.classification == detection.NEW_GAME and first.changed
    assert second.classification == third.classification == detection.UNCHANGED
    assert not second.changed and not third.changed
    assert GameObservationState.query.count() == 1
    assert GameObservationState.query.one().updated_at == persisted_updated_at
    assert second.affected_pitchers == second.affected_teams == ()


@pytest.mark.parametrize(
    ('changes', 'expected_path'),
    [
        ({'outs': 2}, 'linescore.outs'),
        ({'inning': 9}, 'linescore.inning'),
        ({'pitcher': 641729}, 'linescore.pitcher_id'),
        ({'pitches': 3}, 'play.pitch_event_count'),
    ],
)
def test_material_live_changes_are_detected(app, changes, expected_path):
    detection.observe_game_change(GAME_PK, payload=_feed())
    result = detection.observe_game_change(
        GAME_PK, payload=_feed(timestamp='20260826_010100', **changes)
    )
    assert result.classification == detection.CHANGED
    assert expected_path in result.differences
    assert result.downstream_work_triggered is False


def test_finality_transition_uses_canonical_finality_service(app):
    detection.observe_game_change(GAME_PK, payload=_feed())
    result = detection.observe_game_change(
        GAME_PK,
        payload=_feed(timestamp='20260826_020649', status='Final', code='F', inning=9),
    )
    assert result.classification == detection.FINALIZED
    assert result.finality_state == 'final_pending_data'


def test_newer_post_final_change_is_correction_and_replay_is_unchanged(app):
    final = _feed(timestamp='20260826_020649', status='Final', code='F', inning=9)
    detection.observe_game_change(GAME_PK, payload=final)
    corrected = _feed(
        timestamp='20260826_030000', status='Final', code='F', inning=9, pitches=3,
    )
    accepted = detection.observe_game_change(GAME_PK, payload=corrected)
    replay = detection.observe_game_change(GAME_PK, payload=deepcopy(corrected))
    assert accepted.classification == detection.CORRECTED
    assert replay.classification == detection.UNCHANGED


def test_stale_observation_is_rejected_before_and_after_restart(app):
    older = _feed(timestamp='20260826_010000')
    newer = _feed(timestamp='20260826_010100', outs=2)
    detection.observe_game_change(GAME_PK, payload=older)
    accepted = detection.observe_game_change(GAME_PK, payload=newer)
    fingerprint = GameObservationState.query.one().observation_fingerprint
    stale = detection.observe_game_change(GAME_PK, payload=older)
    db.session.remove()
    stale_after_restart = detection.observe_game_change(GAME_PK, payload=older)
    assert accepted.classification == detection.CHANGED
    assert stale.classification == stale_after_restart.classification == detection.STALE_OBSERVATION
    assert GameObservationState.query.one().observation_fingerprint == fingerprint
    assert stale.affected_pitchers == stale.affected_teams == ()


def test_ambiguous_different_content_is_rejected(app):
    accepted = _feed(timestamp='20260826_010000')
    detection.observe_game_change(GAME_PK, payload=accepted)
    same_revision = _feed(timestamp='20260826_010000', outs=2)
    missing_revision = _feed(timestamp=None, outs=2)
    assert detection.observe_game_change(
        GAME_PK, payload=same_revision
    ).classification == detection.AMBIGUOUS_OBSERVATION
    assert detection.observe_game_change(
        GAME_PK, payload=missing_revision
    ).classification == detection.AMBIGUOUS_OBSERVATION


def test_weaker_authority_cannot_supersede(app):
    detection.observe_game_change(GAME_PK, payload=_feed())
    result = detection.observe_game_change(
        GAME_PK, payload=_feed(timestamp='20260826_010100', outs=2),
        source_authority='captured_fixture_untrusted',
    )
    assert result.classification == detection.STALE_OBSERVATION
    assert result.reason == 'weaker_source_authority'


def test_irrelevant_payload_noise_does_not_change_material_fingerprint(app):
    original = _feed()
    noisy = deepcopy(original)
    noisy['copyright'] = 'different formatting noise'
    noisy['metaData']['wait'] = 120
    noisy['metaData']['gameEvents'] = ['unrelated_embedded_signal']
    detection.observe_game_change(GAME_PK, payload=original)
    result = detection.observe_game_change(GAME_PK, payload=noisy)
    assert result.classification == detection.UNCHANGED


@pytest.mark.parametrize(
    ('detailed', 'code'),
    [('Delayed', 'D'), ('Postponed', 'DR'), ('Suspended', 'U')],
)
def test_delayed_postponed_and_suspended_status_changes(detailed, code, app):
    detection.observe_game_change(GAME_PK, payload=_feed())
    payload = _feed(timestamp='20260826_010100', status=detailed, code=code)
    result = detection.observe_game_change(GAME_PK, payload=payload)
    assert result.classification == detection.CHANGED
    assert 'status.detailed' in result.differences


def test_source_failure_is_observable_and_nonmutating(app):
    class FailingClient:
        def get_game_live_feed(self, game_pk):
            raise MlbApiFetchError('controlled outage', endpoint='/feed/live')

    result = detection.observe_game_change(GAME_PK, client=FailingClient())
    assert result.classification == detection.SOURCE_FAILURE
    assert result.accepted is False
    assert GameObservationState.query.count() == 0


def test_detection_never_writes_canonical_or_publication_tables(app):
    sentinels_before = (
        GameLog.query.count(), GamePitchEvent.query.count(), ShareArtifact.query.count(),
    )
    result = detection.observe_game_change(GAME_PK, payload=_feed())
    sentinels_after = (
        GameLog.query.count(), GamePitchEvent.query.count(), ShareArtifact.query.count(),
    )
    assert sentinels_after == sentinels_before == (0, 0, 0)
    assert result.canonical_mutation_performed is False
    assert result.downstream_work_triggered is False


def test_fingerprint_is_stable_under_mapping_order(app):
    observation = detection.canonicalize_game_observation(_feed())
    reordered = dict(reversed(list(observation.items())))
    assert detection.observation_fingerprint(observation) == detection.observation_fingerprint(reordered)


def test_detector_is_not_wired_to_production_schedulers(app):
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    production_inputs = [
        root / '.github' / 'workflows' / 'baseballos-sync.yml',
        root / 'backend' / 'scripts' / 'run_due_sync.py',
        root / 'backend' / 'services' / 'sync.py',
    ]
    for path in production_inputs:
        text = path.read_text(encoding='utf-8')
        assert 'detect_game_changes' not in text
        assert 'game_change_detection' not in text
    detector_script = (
        root / 'backend' / 'scripts' / 'detect_game_changes.py'
    ).read_text(encoding='utf-8')
    assert detector_script.index("os.environ['AUTO_SYNC'] = 'false'") < detector_script.index(
        'from app import app'
    )


def test_bounded_cycle_selects_today_and_recent_final_without_polling(app):
    today = date(2026, 8, 25)
    games = [
        {'gamePk': GAME_PK, 'officialDate': '2026-08-25', 'status': {'statusCode': 'I', 'detailedState': 'In Progress'}},
        {'gamePk': 823800, 'officialDate': '2026-08-24', 'status': {'statusCode': 'F', 'detailedState': 'Final'}},
        {'gamePk': 700001, 'officialDate': '2026-08-22', 'status': {'statusCode': 'F', 'detailedState': 'Final'}},
    ]

    class Client:
        def __init__(self):
            self.feed_calls = []
        def get_schedule(self, **kwargs):
            return games
        def get_game_live_feed(self, game_pk):
            self.feed_calls.append(game_pk)
            payload = _feed()
            payload['gamePk'] = game_pk
            return payload

    client = Client()
    cycle = detection.detect_active_slate_changes(
        reference_date=today, correction_days=2, client=client,
    )
    assert cycle['candidate_game_pks'] == [823800, GAME_PK]
    assert client.feed_calls == [823800, GAME_PK]
    assert cycle['requests_expected'] == 3
    assert cycle['downstream_work_triggered'] is False
