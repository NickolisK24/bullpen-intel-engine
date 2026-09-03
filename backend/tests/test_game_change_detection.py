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
from models.sync_job import SyncJob
from services import continuous_game_work
from services import game_change_detection as detection
from services import sync_jobs
from services.mlb_api import MlbApiFetchError
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


GAME_PK = 823826
BAL_COLORADO_GAME_PK = 824312


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


def _with_usable_boxscore(payload):
    payload = deepcopy(payload)
    payload['liveData']['boxscore'] = {
        'teams': {
            'away': {
                'pitchers': [111111],
                'players': {
                    'ID111111': {
                        'person': {'id': 111111, 'fullName': 'Away Pitcher'},
                        'stats': {'pitching': {
                            'inningsPitched': '1.0', 'hits': 0, 'runs': 0,
                            'earnedRuns': 0, 'baseOnBalls': 0, 'strikeOuts': 2,
                            'homeRuns': 0, 'numberOfPitches': 14, 'strikes': 10,
                        }},
                    },
                },
            },
            'home': {
                'pitchers': [222222],
                'players': {
                    'ID222222': {
                        'person': {'id': 222222, 'fullName': 'Home Pitcher'},
                        'stats': {'pitching': {
                            'inningsPitched': '1.0', 'hits': 1, 'runs': 0,
                            'earnedRuns': 0, 'baseOnBalls': 0, 'strikeOuts': 1,
                            'homeRuns': 0, 'numberOfPitches': 17, 'strikes': 11,
                        }},
                    },
                },
            },
        },
    }
    return payload


def _equal_timestamp_final_incident():
    """Production-shaped final feed pair where MLB retained one revision."""
    pending = _feed(
        timestamp='20260903_035400', status='Final', code='F', inning=9,
    )
    usable = _with_usable_boxscore(pending)
    return pending, usable


def _baltimore_colorado_older_revision():
    """Production-shaped authority order from BAL at COL game 824312."""
    stored = _feed(
        timestamp='20260902_224022', status='Final', code='F', inning=9,
    )
    stored['gamePk'] = BAL_COLORADO_GAME_PK
    stored['gameData']['datetime'].update({
        'dateTime': '2026-09-02T19:10:00Z',
        'originalDate': '2026-09-02',
        'officialDate': '2026-09-02',
    })
    stored['gameData']['teams'] = {
        'away': {'id': 110},
        'home': {'id': 115},
    }
    stored['liveData']['linescore']['teams'] = {
        'away': {'runs': 5, 'hits': 8, 'errors': 0},
        'home': {'runs': 6, 'hits': 10, 'errors': 0},
    }
    incoming = _with_usable_boxscore(stored)
    incoming['metaData']['timeStamp'] = '20260902_224009'
    return stored, incoming


def _invalidate_final_result_evidence(payload, defect):
    payload = deepcopy(payload)
    datetime_data = payload['gameData']['datetime']
    teams = payload['gameData']['teams']
    line_teams = payload['liveData']['linescore']['teams']

    if defect == 'missing_official_date':
        datetime_data.pop('officialDate', None)
        datetime_data.pop('originalDate', None)
    elif defect == 'malformed_official_date':
        datetime_data['officialDate'] = '2026-99-99'
    elif defect == 'missing_home_team':
        teams.pop('home', None)
    elif defect == 'missing_away_team':
        teams.pop('away', None)
    elif defect == 'nonpositive_home_team':
        teams['home']['id'] = 0
    elif defect == 'nonpositive_away_team':
        teams['away']['id'] = -1
    elif defect == 'malformed_home_team':
        teams['home']['id'] = 'not-an-id'
    elif defect == 'malformed_away_team':
        teams['away']['id'] = 'not-an-id'
    elif defect == 'fractional_home_team':
        teams['home']['id'] = 146.5
    elif defect == 'same_team_ids':
        teams['home']['id'] = teams['away']['id']
    elif defect == 'missing_home_score':
        line_teams['home'].pop('runs', None)
    elif defect == 'missing_away_score':
        line_teams['away'].pop('runs', None)
    elif defect == 'negative_home_score':
        line_teams['home']['runs'] = -1
    elif defect == 'negative_away_score':
        line_teams['away']['runs'] = -1
    elif defect == 'malformed_home_score':
        line_teams['home']['runs'] = 'three'
    elif defect == 'malformed_away_score':
        line_teams['away']['runs'] = 'three'
    elif defect == 'date_mismatch':
        datetime_data['officialDate'] = '2026-08-26'
    elif defect == 'team_mismatch':
        teams['home']['id'] = 147
    elif defect == 'score_mismatch':
        line_teams['home']['runs'] += 1
    elif defect == 'reversed_teams':
        teams['home'], teams['away'] = teams['away'], teams['home']
    else:
        raise AssertionError(f'unhandled evidence defect: {defect}')
    return payload


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


def test_final_with_usable_pitching_boxscore_is_final_and_usable(app):
    payload = _with_usable_boxscore(
        _feed(timestamp='20260826_020649', status='Final', code='F', inning=9)
    )
    result = detection.observe_game_change(GAME_PK, payload=payload)
    assert result.classification == detection.NEW_GAME
    assert result.finality_state == 'final_and_usable'


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


def test_equal_timestamp_pending_final_can_upgrade_to_verified_usable_final(app):
    original, corrected = _equal_timestamp_final_incident()

    first = detection.observe_game_change(GAME_PK, payload=original)
    result = detection.observe_game_change(GAME_PK, payload=corrected)
    db.session.remove()
    replay = detection.observe_game_change(GAME_PK, payload=deepcopy(corrected))

    assert first.finality_state == 'final_pending_data'
    assert result.classification == detection.CORRECTED
    assert result.finality_state == 'final_and_usable'
    assert result.accepted is True
    assert result.changed is True
    assert result.reason == detection.EQUAL_REVISION_FINAL_VERIFIED
    assert set(result.differences) == {
        'finality.reason',
        'finality.state',
        'pitching_evidence.appearance_set_fingerprint',
    }
    assert replay.classification == detection.UNCHANGED
    assert replay.accepted is False
    assert GameObservationState.query.count() == 1
    assert GameObservationState.query.one().observation_fingerprint == result.current_observation_identity


@pytest.mark.parametrize('target', ['stored', 'incoming'])
@pytest.mark.parametrize(
    'defect',
    [
        'missing_official_date',
        'malformed_official_date',
        'missing_home_team',
        'missing_away_team',
        'nonpositive_home_team',
        'nonpositive_away_team',
        'malformed_home_team',
        'malformed_away_team',
        'fractional_home_team',
        'same_team_ids',
        'missing_home_score',
        'missing_away_score',
        'negative_home_score',
        'negative_away_score',
        'malformed_home_score',
        'malformed_away_score',
        'date_mismatch',
        'team_mismatch',
        'score_mismatch',
        'reversed_teams',
    ],
)
def test_equal_timestamp_upgrade_requires_complete_matching_final_result(
    app, target, defect,
):
    stored, incoming = _equal_timestamp_final_incident()
    if target == 'stored':
        stored = _invalidate_final_result_evidence(stored, defect)
    else:
        incoming = _invalidate_final_result_evidence(incoming, defect)

    first = detection.observe_game_change(GAME_PK, payload=stored)
    result = detection.observe_game_change(GAME_PK, payload=incoming)

    assert first.finality_state == detection.game_finality.FINAL_PENDING_DATA
    assert result.classification == detection.AMBIGUOUS_OBSERVATION
    assert result.accepted is False
    assert result.reason == 'equal_revision_with_different_material_content'
    row = GameObservationState.query.one()
    assert row.observation_fingerprint == first.current_observation_identity
    assert row.finality_state == detection.game_finality.FINAL_PENDING_DATA


@pytest.mark.parametrize(
    'defect',
    [
        'missing_official_date',
        'malformed_official_date',
        'missing_home_team',
        'missing_away_team',
        'nonpositive_home_team',
        'nonpositive_away_team',
        'malformed_home_team',
        'malformed_away_team',
        'fractional_home_team',
        'same_team_ids',
        'missing_home_score',
        'missing_away_score',
        'negative_home_score',
        'negative_away_score',
        'malformed_home_score',
        'malformed_away_score',
    ],
)
def test_equal_timestamp_upgrade_rejects_matching_invalid_final_result(app, defect):
    stored, incoming = _equal_timestamp_final_incident()
    stored = _invalidate_final_result_evidence(stored, defect)
    incoming = _invalidate_final_result_evidence(incoming, defect)

    first = detection.observe_game_change(GAME_PK, payload=stored)
    result = detection.observe_game_change(GAME_PK, payload=incoming)

    assert result.classification == detection.AMBIGUOUS_OBSERVATION
    assert result.accepted is False
    assert result.reason == 'equal_revision_with_different_material_content'
    assert GameObservationState.query.one().observation_fingerprint == (
        first.current_observation_identity
    )


def test_equal_timestamp_upgrade_rejects_other_material_change(app):
    stored, _incoming = _equal_timestamp_final_incident()
    incoming = _with_usable_boxscore(
        _feed(
            timestamp='20260903_035400', status='Final', code='F', inning=9,
            pitches=3,
        )
    )

    first = detection.observe_game_change(GAME_PK, payload=stored)
    result = detection.observe_game_change(GAME_PK, payload=incoming)

    assert result.classification == detection.AMBIGUOUS_OBSERVATION
    assert result.accepted is False
    assert result.reason == 'equal_revision_with_different_material_content'
    assert GameObservationState.query.one().observation_fingerprint == (
        first.current_observation_identity
    )


def test_equal_timestamp_upgrade_rejects_different_game_identity(app):
    stored, incoming = _equal_timestamp_final_incident()
    incoming['gamePk'] = 999999

    first = detection.observe_game_change(GAME_PK, payload=stored)
    result = detection.observe_game_change(GAME_PK, payload=incoming)

    assert result.classification == detection.SOURCE_FAILURE
    assert result.accepted is False
    assert GameObservationState.query.one().observation_fingerprint == (
        first.current_observation_identity
    )


def test_equal_timestamp_final_change_without_usable_boxscore_remains_ambiguous(app):
    original = _feed(timestamp='20260903_035400', status='Final', code='F', inning=9, pitches=2)
    corrected = _feed(timestamp='20260903_035400', status='Final', code='F', inning=9, pitches=3)

    detection.observe_game_change(GAME_PK, payload=original)
    result = detection.observe_game_change(GAME_PK, payload=corrected)

    assert result.classification == detection.AMBIGUOUS_OBSERVATION
    assert result.accepted is False
    assert result.reason == 'equal_revision_with_different_material_content'


@pytest.mark.parametrize(
    ('incoming_timestamp', 'expected_reason'),
    [
        ('20260903_035400', detection.FINAL_EVIDENCE_REGRESSION),
        ('20260903_040000', detection.FINAL_EVIDENCE_REGRESSION),
    ],
)
def test_usable_final_cannot_regress_to_pending_final(
    app, incoming_timestamp, expected_reason,
):
    original = _with_usable_boxscore(
        _feed(timestamp='20260903_035400', status='Final', code='F', inning=9)
    )
    regressive = _feed(
        timestamp=incoming_timestamp, status='Final', code='F', inning=9,
    )

    first = detection.observe_game_change(GAME_PK, payload=original)
    row = GameObservationState.query.one()
    accepted_identity = (
        row.observation_fingerprint,
        row.source_observed_at,
        row.accepted_at,
        row.previous_observation_fingerprint,
    )
    result = detection.observe_game_change(GAME_PK, payload=regressive)

    assert result.classification == detection.AMBIGUOUS_OBSERVATION
    assert result.accepted is False
    assert result.reason == expected_reason
    row = GameObservationState.query.one()
    assert row.observation_fingerprint == first.current_observation_identity
    assert row.finality_state == detection.game_finality.FINAL_AND_USABLE
    assert (
        row.observation_fingerprint,
        row.source_observed_at,
        row.accepted_at,
        row.previous_observation_fingerprint,
    ) == accepted_identity


def test_newer_usable_final_correction_remains_governed_by_revision_order(app):
    original = _with_usable_boxscore(
        _feed(timestamp='20260903_035400', status='Final', code='F', inning=9)
    )
    corrected = _with_usable_boxscore(
        _feed(
            timestamp='20260903_040000', status='Final', code='F', inning=9,
            pitches=3,
        )
    )

    detection.observe_game_change(GAME_PK, payload=original)
    result = detection.observe_game_change(GAME_PK, payload=corrected)

    assert result.classification == detection.CORRECTED
    assert result.finality_state == detection.game_finality.FINAL_AND_USABLE
    assert result.accepted is True
    assert result.reason == 'newer_upstream_observation'


def test_newer_content_reversion_gets_a_distinct_durable_revision(app):
    live = _feed(timestamp='20260903_035300')
    revision_a = _with_usable_boxscore(
        _feed(timestamp='20260903_035400', status='Final', code='F', inning=9)
    )
    revision_b = deepcopy(revision_a)
    revision_b['metaData']['timeStamp'] = '20260903_035500'
    revision_b['liveData']['boxscore']['teams']['away']['players'][
        'ID111111'
    ]['stats']['pitching']['numberOfPitches'] = 15
    revision_a_again = deepcopy(revision_a)
    revision_a_again['metaData']['timeStamp'] = '20260903_035600'

    detection.observe_game_change(
        GAME_PK, payload=live, create_work_obligation=True,
    )
    accepted_a = detection.observe_game_change(
        GAME_PK, payload=revision_a, create_work_obligation=True,
    )
    job_a = SyncJob.query.filter_by(
        job_name=continuous_game_work.JOB_NAME,
    ).one()
    continuous_game_work.complete(job_a, outcome='test_checkpoint')
    accepted_b = detection.observe_game_change(
        GAME_PK, payload=revision_b, create_work_obligation=True,
    )
    job_b = SyncJob.query.filter_by(
        job_name=continuous_game_work.JOB_NAME,
        status=sync_jobs.STATUS_PENDING,
    ).one()
    continuous_game_work.complete(job_b, outcome='test_checkpoint')
    accepted_a_again = detection.observe_game_change(
        GAME_PK,
        payload=revision_a_again,
        create_work_obligation=True,
    )

    jobs = SyncJob.query.filter_by(
        job_name=continuous_game_work.JOB_NAME,
    ).order_by(SyncJob.id.asc()).all()
    assert accepted_a.classification == detection.FINALIZED
    assert accepted_b.classification == detection.CORRECTED
    assert accepted_a_again.classification == detection.CORRECTED
    assert accepted_a_again.accepted is True
    assert len(jobs) == 3
    assert len({job.scope_key for job in jobs}) == 3
    assert jobs[-1].status == sync_jobs.STATUS_PENDING


def test_equal_timestamp_usable_pitching_variant_remains_ambiguous(app):
    original = _with_usable_boxscore(
        _feed(timestamp='20260903_035400', status='Final', code='F', inning=9)
    )
    corrected = deepcopy(original)
    corrected['liveData']['boxscore']['teams']['away']['players'][
        'ID111111'
    ]['stats']['pitching']['numberOfPitches'] = 15

    first = detection.observe_game_change(GAME_PK, payload=original)
    result = detection.observe_game_change(GAME_PK, payload=corrected)
    accepted_identity = first.current_observation_identity

    assert first.finality_state == detection.game_finality.FINAL_AND_USABLE
    assert result.classification == detection.AMBIGUOUS_OBSERVATION
    assert result.accepted is False
    assert result.reason == 'equal_revision_with_different_material_content'
    assert GameObservationState.query.one().observation_fingerprint == (
        accepted_identity
    )


def test_cosmetic_boxscore_change_does_not_create_a_pitching_correction(app):
    original = _with_usable_boxscore(
        _feed(timestamp='20260903_035400', status='Final', code='F', inning=9)
    )
    cosmetic = deepcopy(original)
    cosmetic['liveData']['boxscore']['teams']['away']['players'][
        'ID111111'
    ]['person']['fullName'] = 'Display Name Corrected'

    detection.observe_game_change(GAME_PK, payload=original)
    result = detection.observe_game_change(GAME_PK, payload=cosmetic)

    assert result.classification == detection.UNCHANGED
    assert result.accepted is False


def test_equal_timestamp_upgrade_requires_canonical_appearance_evidence(app):
    pending, usable = _equal_timestamp_final_incident()
    usable['liveData']['boxscore']['teams']['away']['players'][
        'ID111111'
    ]['stats']['pitching']['inningsPitched'] = '0.4'

    first = detection.observe_game_change(GAME_PK, payload=pending)
    result = detection.observe_game_change(GAME_PK, payload=usable)

    assert first.finality_state == detection.game_finality.FINAL_PENDING_DATA
    assert result.classification == detection.AMBIGUOUS_OBSERVATION
    assert result.accepted is False
    assert GameObservationState.query.one().observation_fingerprint == (
        first.current_observation_identity
    )


def test_legacy_pending_observation_can_bootstrap_governed_pitching_evidence(app):
    pending, usable = _equal_timestamp_final_incident()
    legacy_observation = detection.canonicalize_game_observation(
        pending,
        expected_game_pk=GAME_PK,
    )
    legacy_observation.pop('pitching_evidence')
    legacy_fingerprint = detection.observation_fingerprint(legacy_observation)
    db.session.add(GameObservationState(
        mlb_game_pk=GAME_PK,
        observation_fingerprint=legacy_fingerprint,
        observation=legacy_observation,
        source_authority=detection.SOURCE_AUTHORITY,
        source_endpoint=detection.SOURCE_ENDPOINT.format(game_pk=GAME_PK),
        source_observed_at=detection.parse_source_timestamp(
            pending['metaData']['timeStamp']
        ),
        finality_state=detection.game_finality.FINAL_PENDING_DATA,
        last_classification=detection.FINALIZED,
    ))
    db.session.commit()

    result = detection.observe_game_change(GAME_PK, payload=usable)

    assert result.classification == detection.CORRECTED
    assert result.accepted is True
    assert result.reason == detection.EQUAL_REVISION_FINAL_VERIFIED
    assert set(result.differences) == {
        'finality.reason',
        'finality.state',
        'pitching_evidence.source_authority',
        'pitching_evidence.appearance_set_fingerprint',
    }


def test_equal_timestamp_usable_final_cannot_oscillate_to_another_usable_variant(app):
    original = _with_usable_boxscore(
        _feed(timestamp='20260903_035400', status='Final', code='F', inning=9, pitches=2)
    )
    alternate = _with_usable_boxscore(
        _feed(timestamp='20260903_035400', status='Final', code='F', inning=9, pitches=3)
    )

    first = detection.observe_game_change(GAME_PK, payload=original)
    result = detection.observe_game_change(GAME_PK, payload=alternate)

    assert first.finality_state == 'final_and_usable'
    assert result.classification == detection.AMBIGUOUS_OBSERVATION
    assert result.accepted is False


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


def test_older_final_revision_remains_stale_even_with_usable_boxscore(app):
    newer = _with_usable_boxscore(
        _feed(timestamp='20260903_040000', status='Final', code='F', inning=9, pitches=3)
    )
    older = _with_usable_boxscore(
        _feed(timestamp='20260903_035400', status='Final', code='F', inning=9, pitches=2)
    )

    detection.observe_game_change(GAME_PK, payload=newer)
    result = detection.observe_game_change(GAME_PK, payload=older)

    assert result.classification == detection.STALE_OBSERVATION
    assert result.accepted is False
    assert result.reason == 'older_upstream_observation'


def test_baltimore_colorado_older_usable_revision_remains_stale(app):
    stored, incoming = _baltimore_colorado_older_revision()

    first = detection.observe_game_change(BAL_COLORADO_GAME_PK, payload=stored)
    result = detection.observe_game_change(BAL_COLORADO_GAME_PK, payload=incoming)

    assert first.finality_state == detection.game_finality.FINAL_PENDING_DATA
    assert result.classification == detection.STALE_OBSERVATION
    assert result.accepted is False
    assert result.reason == 'older_upstream_observation'
    row = GameObservationState.query.one()
    assert row.mlb_game_pk == BAL_COLORADO_GAME_PK
    assert row.observation_fingerprint == first.current_observation_identity
    assert row.finality_state == detection.game_finality.FINAL_PENDING_DATA


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


def test_bounded_cap_prioritizes_current_live_game_over_recent_finals(app):
    today = date(2026, 8, 25)
    games = [
        {'gamePk': 700001, 'officialDate': '2026-08-24', 'status': {'statusCode': 'F', 'detailedState': 'Final'}},
        {'gamePk': GAME_PK, 'officialDate': '2026-08-25', 'status': {'statusCode': 'I', 'detailedState': 'In Progress'}},
        {'gamePk': 700002, 'officialDate': '2026-08-25', 'status': {'statusCode': 'S', 'detailedState': 'Scheduled'}},
    ]

    class Client:
        def get_schedule(self, **kwargs):
            return games

        def get_game_live_feed(self, game_pk):
            payload = _feed()
            payload['gamePk'] = game_pk
            return payload

    cycle = detection.detect_active_slate_changes(
        reference_date=today, correction_days=2, client=Client(), max_games=1,
    )
    assert cycle['candidate_game_pks'] == [GAME_PK]
