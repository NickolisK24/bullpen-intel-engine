import ast
import json
import re
import subprocess
from datetime import date
from pathlib import Path

import pytest
from flask import Flask

from api.team_recent_work import team_recent_work_bp
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import pitcher_season_ledger_coverage
from services import public_team_relief_work
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / 'backend/services/public_team_relief_work.py'
STARTER_ASSIGNMENT_PATH = (
    REPO_ROOT / 'backend/services/starter_assignment_context.py'
)
API_PATH = REPO_ROOT / 'backend/api/team_recent_work.py'
APP_PATH = REPO_ROOT / 'backend/app.py'
TEAM_ID = 110
FORBIDDEN_TERMS = (
    'evidence',
    'citation',
    'composed',
    'read',
    'completeness',
    'reason code',
    'recompute',
    'reconciliation',
    'audit',
    'internal',
    'clean',
    'traffic',
    'entry band',
    'inherited',
    'leverage',
    'pressure',
    'trust',
    'role',
    'setup',
    'closer',
    'availability',
    'available',
    'readiness',
    'fatigue',
    'confidence',
    'score',
    'grade',
    'rank',
    'tier',
    'injury',
    'health',
    'concentration',
    'distribution',
    'leaned',
    'fresh',
    'rested',
    'taxed',
    'gassed',
    'burned',
    'overexposed',
    'likely',
    'should',
    'will',
    'expect',
    'predict',
    'odds',
    'bet',
    'lock',
    'of the bullpen',
    'arms',
)


@pytest.fixture()
def client(monkeypatch):
    app = Flask('test_public_team_relief_work')
    configure_test_database(app)
    db.init_app(app)
    app.register_blueprint(team_recent_work_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        monkeypatch.setattr(
            public_team_relief_work.board_freshness,
            'board_freshness_block',
            lambda: _freshness_block(),
        )
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def test_team_relief_work_anchor_from_public_freshness_and_exact_payload(client):
    with client.application.app_context():
        alpha = _pitcher(name='Alpha Reliever', mlb_id=90001)
        beta = _pitcher(name='Beta Reliever', mlb_id=90002)
        other = _pitcher(name='Other Pitcher', mlb_id=90003, team_id=111)
        db.session.add_all([alpha, beta, other])
        db.session.flush()
        db.session.add_all([
            _log(
                alpha.id,
                9101,
                date(2026, 7, 3),
                opponent='Boston Red Sox',
                opponent_abbreviation='BOS',
                outs=5,
                pitches=24,
                strikeouts=2,
                walks=1,
                hits=2,
                runs=1,
                save=True,
                hold=True,
                blown_save=True,
                win=True,
                loss=True,
            ),
            _log(beta.id, 9102, date(2026, 7, 3), outs=6, pitches=37, strikeouts=1),
            _log(alpha.id, 9103, date(2026, 6, 29), pitches=20),
            _log(beta.id, 9104, date(2026, 6, 25), pitches=None, strikeouts=1),
            _log(alpha.id, 9105, date(2026, 7, 2), games_started=1, outs=18, pitches=70),
            _log(beta.id, 9106, date(2026, 7, 1), games_started=None, pitches=15),
            _log(beta.id, 9107, date(2026, 6, 24), games_started=None, pitches=12),
            _log(other.id, 9108, date(2026, 7, 3), pitches=99),
        ])
        db.session.commit()
        alpha_id = alpha.id
        beta_id = beta.id

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()

    assert body == {
        'capability': 'public_team_relief_work',
        'team': {
            'team_id': TEAM_ID,
            'team_name': 'Test Club',
            'team_abbreviation': 'TST',
        },
        'data_through': '2026-07-05',
        'freshness': _freshness_block(),
        'scope_sentence': 'Covers pitchers currently on the TST roster per MLB roster data.',
        'relief_by_date': [
            {
                'game_date': '2026-07-03',
                'relief_appearances': 2,
                'outs_total': 11,
                'pitches_total': 61,
                'appearances_with_pitches': 2,
                'sentence': 'July 3 \u2014 2 relief appearances, 3.2 IP, 61 pitches.',
                'appearances': [
                    {
                        'pitcher_id': alpha_id,
                        'pitcher_mlb_id': 90001,
                        'pitcher_full_name': 'Alpha Reliever',
                        'roster_status_sentence': 'On the active roster per MLB roster data.',
                        'game_date': '2026-07-03',
                        'opponent': 'Boston Red Sox',
                        'opponent_abbreviation': 'BOS',
                        'innings_pitched': 5 / 3,
                        'innings_pitched_outs': 5,
                        'pitches_thrown': 24,
                        'strikeouts': 2,
                        'walks': 1,
                        'hits_allowed': 2,
                        'runs_allowed': 1,
                        'save': True,
                        'hold': True,
                        'blown_save': True,
                        'win': True,
                        'loss': True,
                        'save_situation': False,
                        'sentence': (
                            'Alpha Reliever \u2014 1.2 IP, 24 pitches, '
                            '2 K, 1 BB, 2 H, 1 R.'
                        ),
                    },
                    {
                        'pitcher_id': beta_id,
                        'pitcher_mlb_id': 90002,
                        'pitcher_full_name': 'Beta Reliever',
                        'roster_status_sentence': 'On the active roster per MLB roster data.',
                        'game_date': '2026-07-03',
                        'opponent': 'New York Yankees',
                        'opponent_abbreviation': 'NYY',
                        'innings_pitched': 2.0,
                        'innings_pitched_outs': 6,
                        'pitches_thrown': 37,
                        'strikeouts': 1,
                        'walks': 0,
                        'hits_allowed': 0,
                        'runs_allowed': 0,
                        'save': False,
                        'hold': False,
                        'blown_save': False,
                        'win': False,
                        'loss': False,
                        'save_situation': False,
                        'sentence': 'Beta Reliever \u2014 2.0 IP, 37 pitches, 1 K, 0 BB.',
                    },
                ],
            },
            {
                'game_date': '2026-06-29',
                'relief_appearances': 1,
                'outs_total': 3,
                'pitches_total': 20,
                'appearances_with_pitches': 1,
                'sentence': 'June 29 \u2014 1 relief appearance, 1.0 IP, 20 pitches.',
                'appearances': [
                    {
                        'pitcher_id': alpha_id,
                        'pitcher_mlb_id': 90001,
                        'pitcher_full_name': 'Alpha Reliever',
                        'roster_status_sentence': 'On the active roster per MLB roster data.',
                        'game_date': '2026-06-29',
                        'opponent': 'New York Yankees',
                        'opponent_abbreviation': 'NYY',
                        'innings_pitched': 1.0,
                        'innings_pitched_outs': 3,
                        'pitches_thrown': 20,
                        'strikeouts': 0,
                        'walks': 0,
                        'hits_allowed': 0,
                        'runs_allowed': 0,
                        'save': False,
                        'hold': False,
                        'blown_save': False,
                        'win': False,
                        'loss': False,
                        'save_situation': False,
                        'sentence': 'Alpha Reliever \u2014 1.0 IP, 20 pitches, 0 K, 0 BB.',
                    },
                ],
            },
            {
                'game_date': '2026-06-25',
                'relief_appearances': 1,
                'outs_total': 3,
                'pitches_total': None,
                'appearances_with_pitches': 0,
                'sentence': 'June 25 \u2014 1 relief appearance, 1.0 IP.',
                'appearances': [
                    {
                        'pitcher_id': beta_id,
                        'pitcher_mlb_id': 90002,
                        'pitcher_full_name': 'Beta Reliever',
                        'roster_status_sentence': 'On the active roster per MLB roster data.',
                        'game_date': '2026-06-25',
                        'opponent': 'New York Yankees',
                        'opponent_abbreviation': 'NYY',
                        'innings_pitched': 1.0,
                        'innings_pitched_outs': 3,
                        'pitches_thrown': None,
                        'strikeouts': 1,
                        'walks': 0,
                        'hits_allowed': 0,
                        'runs_allowed': 0,
                        'save': False,
                        'hold': False,
                        'blown_save': False,
                        'win': False,
                        'loss': False,
                        'save_situation': False,
                        'sentence': 'Beta Reliever \u2014 1.0 IP, 1 K, 0 BB.',
                    },
                ],
            },
        ],
        'windows': {
            'window_7': {
                'through': '2026-07-05',
                'relief_appearances': 3,
                'pitchers_in_relief': 2,
                'pitches_total': 81,
                'appearances_with_pitches': 3,
                'start_relief_unknown': 1,
                'sentence': '3 relief appearances in the 7 days through July 5.',
                'pitchers_sentence': (
                    '2 pitchers appeared in relief in the 7 days through July 5.'
                ),
                'pitches_sentence': '81 pitches across those 3 relief appearances.',
                'start_relief_unknown_sentence': (
                    'Start/relief status unavailable for 1 of 4 appearances in the '
                    '7 days through July 5; relief totals cover the other 3.'
                ),
            },
            'window_14': {
                'through': '2026-07-05',
                'relief_appearances': 4,
                'pitchers_in_relief': 2,
                'pitches_total': None,
                'appearances_with_pitches': 3,
                'start_relief_unknown': 2,
                'sentence': '4 relief appearances in the 14 days through July 5.',
                'pitchers_sentence': (
                    '2 pitchers appeared in relief in the 14 days through July 5.'
                ),
                'pitches_sentence': (
                    'Pitch count unavailable for 1 of 4 relief appearances; '
                    '81 pitches across the other 3.'
                ),
                'start_relief_unknown_sentence': (
                    'Start/relief status unavailable for 2 of 6 appearances in the '
                    '14 days through July 5; relief totals cover the other 4.'
                ),
            },
        },
    }


def test_team_relief_work_no_anchor_omits_anchored_sections(client, monkeypatch):
    monkeypatch.setattr(
        public_team_relief_work.board_freshness,
        'board_freshness_block',
        lambda: {
            'data_through': None,
            'freshness_state': 'metadata_unavailable',
            'label': 'Public freshness metadata unavailable.',
        },
    )
    with client.application.app_context():
        pitcher = _pitcher()
        db.session.add(pitcher)
        db.session.flush()
        db.session.add(_log(pitcher.id, 9201, date(2026, 7, 5), pitches=14))
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()

    assert body == {
        'capability': 'public_team_relief_work',
        'team': {
            'team_id': TEAM_ID,
            'team_name': 'Test Club',
            'team_abbreviation': 'TST',
        },
        'data_through': None,
        'freshness': {
            'data_through': None,
            'freshness_state': 'metadata_unavailable',
            'label': 'Public freshness metadata unavailable.',
        },
        'scope_sentence': 'Covers pitchers currently on the TST roster per MLB roster data.',
        'relief_by_date': [],
    }
    assert 'windows' not in body
    assert 'absence_sentence' not in body


def test_team_relief_work_absence_and_zero_windows(client):
    with client.application.app_context():
        pitcher = _pitcher()
        db.session.add(pitcher)
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()

    assert body['relief_by_date'] == []
    assert body['absence_sentence'] == (
        'No relief appearances in the 30 days through July 5.'
    )
    assert body['windows']['window_7'] == {
        'through': '2026-07-05',
        'relief_appearances': 0,
        'pitchers_in_relief': 0,
        'pitches_total': 0,
        'appearances_with_pitches': 0,
        'start_relief_unknown': 0,
        'sentence': '0 relief appearances in the 7 days through July 5.',
        'pitchers_sentence': '0 pitchers appeared in relief in the 7 days through July 5.',
        'pitches_sentence': '0 pitches across those 0 relief appearances.',
    }
    assert body['windows']['window_14'] == {
        'through': '2026-07-05',
        'relief_appearances': 0,
        'pitchers_in_relief': 0,
        'pitches_total': 0,
        'appearances_with_pitches': 0,
        'start_relief_unknown': 0,
        'sentence': '0 relief appearances in the 14 days through July 5.',
        'pitchers_sentence': '0 pitchers appeared in relief in the 14 days through July 5.',
        'pitches_sentence': '0 pitches across those 0 relief appearances.',
    }


def test_team_relief_work_known_subtotal_pitch_wording(client):
    with client.application.app_context():
        pitcher = _pitcher()
        db.session.add(pitcher)
        db.session.flush()
        db.session.add_all([
            _log(pitcher.id, 9301, date(2026, 7, 5), pitches=17),
            _log(pitcher.id, 9302, date(2026, 7, 4), pitches=None),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()

    assert body['windows']['window_7']['pitches_total'] is None
    assert body['windows']['window_7']['appearances_with_pitches'] == 1
    assert body['windows']['window_7']['pitches_sentence'] == (
        'Pitch count unavailable for 1 of 2 relief appearances; '
        '17 pitches across the other 1.'
    )


def test_team_relief_work_distinct_pitcher_count_and_no_denominator(client):
    with client.application.app_context():
        pitcher = _pitcher()
        db.session.add(pitcher)
        db.session.flush()
        db.session.add_all([
            _log(pitcher.id, 9401, date(2026, 7, 5), pitches=17),
            _log(pitcher.id, 9402, date(2026, 7, 4), pitches=18),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    serialized = json.dumps(body)

    assert body['windows']['window_7']['pitchers_in_relief'] == 1
    assert 'of the bullpen' not in serialized
    assert not re.search(r'of\s+\d+\s+arms', serialized)


def test_team_relief_work_date_groups_cap_and_ordering(client):
    with client.application.app_context():
        alpha = _pitcher(name='Alpha Reliever', mlb_id=94001)
        beta = _pitcher(name='Beta Reliever', mlb_id=94002)
        db.session.add_all([alpha, beta])
        db.session.flush()
        db.session.add_all([
            _log(beta.id, 9501, date(2026, 7, 5), pitches=8),
            _log(alpha.id, 9502, date(2026, 7, 5), pitches=9),
            _log(alpha.id, 9503, date(2026, 7, 4), pitches=10),
            _log(alpha.id, 9504, date(2026, 7, 3), pitches=11),
            _log(alpha.id, 9505, date(2026, 7, 2), pitches=12),
            _log(alpha.id, 9506, date(2026, 7, 1), pitches=13),
            _log(alpha.id, 9507, date(2026, 6, 30), pitches=14),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    groups = body['relief_by_date']

    assert len(groups) == public_team_relief_work.RECENT_GAME_DATES_MAX
    assert [group['game_date'] for group in groups] == [
        '2026-07-05',
        '2026-07-04',
        '2026-07-03',
        '2026-07-02',
        '2026-07-01',
    ]
    assert groups[0]['relief_appearances'] == 2
    assert [line['pitcher_full_name'] for line in groups[0]['appearances']] == [
        'Alpha Reliever',
        'Beta Reliever',
    ]


def test_team_relief_work_game_context_extended_bullpen_coverage(client):
    with client.application.app_context():
        starter = _pitcher(name='Delta Starter', mlb_id=95001)
        relievers = [
            _pitcher(name=f'Reliever {suffix}', mlb_id=95002 + index)
            for index, suffix in enumerate(['One', 'Two', 'Three', 'Four', 'Five', 'Six'])
        ]
        db.session.add_all([starter, *relievers])
        db.session.flush()
        db.session.add(_log(
            starter.id, 9601, date(2026, 7, 5), games_started=1, outs=6, pitches=35,
        ))
        for reliever, outs, pitches in zip(
            relievers,
            (3, 3, 3, 4, 4, 4),
            (15, 17, 18, 19, 19, 19),
        ):
            db.session.add(_log(
                reliever.id, 9601, date(2026, 7, 5), outs=outs, pitches=pitches,
            ))
        db.session.commit()
        starter_id = starter.id
        starter_pitcher_ids = {starter.id}

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    group = body['relief_by_date'][0]

    assert group['relief_appearances'] == 6
    assert group['outs_total'] == 21
    assert group['pitches_total'] == 107
    assert starter_pitcher_ids.isdisjoint(
        {line['pitcher_id'] for line in group['appearances']}
    )
    assert body['windows']['window_7']['relief_appearances'] == 6
    assert group['games'] == [
        {
            'mlb_game_pk': 9601,
            'opponent': 'New York Yankees',
            'opponent_abbreviation': 'NYY',
            'game_shape': 'short_start',
            'context_label': 'Extended bullpen coverage',
            'starter': {
                'pitcher_id': starter_id,
                'pitcher_mlb_id': 95001,
                'pitcher_full_name': 'Delta Starter',
                'outs': 6,
                'innings': '2.0',
                'pitches': 35,
            },
            'relief': {
                'pitcher_count': 6,
                'outs': 21,
                'innings': '7.0',
                'pitches': 107,
            },
            'total': {
                'pitcher_count': 7,
                'outs': 27,
                'innings': '9.0',
                'pitches': 142,
            },
            'context_sentences': [
                'Delta Starter started and recorded 6 outs (2.0 IP) on 35 pitches.',
                'Six relievers covered the remaining 21 outs (7.0 IP) on 107 pitches.',
                '7 pitchers combined for 27 outs (9.0 IP) and 142 pitches.',
            ],
        },
    ]


def test_team_relief_work_game_context_omitted_without_credited_start(client):
    with client.application.app_context():
        pitcher = _pitcher()
        db.session.add(pitcher)
        db.session.flush()
        db.session.add(_log(pitcher.id, 9611, date(2026, 7, 5), pitches=14))
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()

    assert 'games' not in body['relief_by_date'][0]


def test_team_relief_work_game_context_omitted_when_start_flag_unknown(client):
    with client.application.app_context():
        starter = _pitcher(name='Delta Starter', mlb_id=95001)
        reliever = _pitcher(name='Echo Reliever', mlb_id=95002)
        unknown = _pitcher(name='Foxtrot Unknown', mlb_id=95003)
        db.session.add_all([starter, reliever, unknown])
        db.session.flush()
        db.session.add_all([
            _log(starter.id, 9621, date(2026, 7, 5), games_started=1, outs=6, pitches=35),
            _log(reliever.id, 9621, date(2026, 7, 5), outs=21, pitches=90),
            _log(unknown.id, 9621, date(2026, 7, 5), games_started=None, outs=3, pitches=12),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()

    assert 'games' not in body['relief_by_date'][0]


def test_team_relief_work_game_context_normal_start_facts_without_label(client):
    with client.application.app_context():
        starter = _pitcher(name='Delta Starter', mlb_id=95001)
        first = _pitcher(name='Echo Reliever', mlb_id=95002)
        second = _pitcher(name='Foxtrot Reliever', mlb_id=95003)
        db.session.add_all([starter, first, second])
        db.session.flush()
        db.session.add_all([
            _log(starter.id, 9631, date(2026, 7, 5), games_started=1, outs=18, pitches=92),
            _log(first.id, 9631, date(2026, 7, 5), outs=5, pitches=20),
            _log(second.id, 9631, date(2026, 7, 5), outs=4, pitches=15),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    game = body['relief_by_date'][0]['games'][0]

    assert game['game_shape'] == 'normal_start'
    assert game['context_label'] is None
    assert game['total'] == {
        'pitcher_count': 3,
        'outs': 27,
        'innings': '9.0',
        'pitches': 127,
    }
    assert game['context_sentences'] == [
        'Delta Starter started and recorded 18 outs (6.0 IP) on 92 pitches.',
        'Two relievers covered the remaining 9 outs (3.0 IP) on 35 pitches.',
    ]
    assert 'starter_assignment' not in game
    assert 'Extended bullpen coverage' not in json.dumps(body)


def test_team_relief_work_game_context_missing_pitches_stay_null(client):
    with client.application.app_context():
        starter = _pitcher(name='Delta Starter', mlb_id=95001)
        relievers = [
            _pitcher(name=f'Reliever {suffix}', mlb_id=95002 + index)
            for index, suffix in enumerate(['One', 'Two', 'Three', 'Four', 'Five', 'Six'])
        ]
        db.session.add_all([starter, *relievers])
        db.session.flush()
        db.session.add(_log(
            starter.id, 9641, date(2026, 7, 5), games_started=1, outs=6, pitches=None,
        ))
        for reliever, outs, pitches in zip(
            relievers,
            (3, 3, 3, 4, 4, 4),
            (15, 17, 18, 19, 19, None),
        ):
            db.session.add(_log(
                reliever.id, 9641, date(2026, 7, 5), outs=outs, pitches=pitches,
            ))
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    group = body['relief_by_date'][0]
    game = group['games'][0]

    assert group['pitches_total'] is None
    assert game['context_label'] == 'Extended bullpen coverage'
    assert game['starter']['pitches'] is None
    assert game['relief']['pitches'] is None
    assert game['total']['pitches'] is None
    assert game['context_sentences'] == [
        'Delta Starter started and recorded 6 outs (2.0 IP).',
        'Six relievers covered the remaining 21 outs (7.0 IP).',
        '7 pitchers combined for 27 outs (9.0 IP).',
    ]


def test_team_relief_work_game_context_doubleheader_games_stay_separate(client):
    with client.application.app_context():
        first_starter = _pitcher(name='Delta Starter', mlb_id=95001)
        second_starter = _pitcher(name='Golf Starter', mlb_id=95002)
        first_reliever = _pitcher(name='Echo Reliever', mlb_id=95003)
        second_reliever = _pitcher(name='Foxtrot Reliever', mlb_id=95004)
        third_reliever = _pitcher(name='Hotel Reliever', mlb_id=95005)
        db.session.add_all([
            first_starter, second_starter,
            first_reliever, second_reliever, third_reliever,
        ])
        db.session.flush()
        db.session.add_all([
            _log(first_starter.id, 9651, date(2026, 7, 5), games_started=1, outs=6, pitches=30),
            _log(first_reliever.id, 9651, date(2026, 7, 5), outs=8, pitches=33),
            _log(second_reliever.id, 9651, date(2026, 7, 5), outs=7, pitches=29),
            _log(second_starter.id, 9652, date(2026, 7, 5), games_started=1, outs=15, pitches=77),
            _log(third_reliever.id, 9652, date(2026, 7, 5), outs=3, pitches=13),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    group = body['relief_by_date'][0]

    assert group['relief_appearances'] == 3
    assert [game['mlb_game_pk'] for game in group['games']] == [9651, 9652]
    assert group['games'][0]['context_label'] == 'Extended bullpen coverage'
    assert group['games'][0]['relief']['outs'] == 15
    assert group['games'][1]['context_label'] is None
    assert group['games'][1]['game_shape'] == 'normal_start'


def test_team_relief_work_game_context_label_thresholds_are_strict(client):
    with client.application.app_context():
        first_starter = _pitcher(name='Delta Starter', mlb_id=95001)
        second_starter = _pitcher(name='Golf Starter', mlb_id=95002)
        first_reliever = _pitcher(name='Echo Reliever', mlb_id=95003)
        second_reliever = _pitcher(name='Foxtrot Reliever', mlb_id=95004)
        db.session.add_all([
            first_starter, second_starter, first_reliever, second_reliever,
        ])
        db.session.flush()
        db.session.add_all([
            _log(first_starter.id, 9661, date(2026, 7, 4), games_started=1, outs=7, pitches=32),
            _log(first_reliever.id, 9661, date(2026, 7, 4), outs=21, pitches=88),
            _log(second_starter.id, 9662, date(2026, 7, 3), games_started=1, outs=6, pitches=28),
            _log(second_reliever.id, 9662, date(2026, 7, 3), outs=14, pitches=61),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    groups = {group['game_date']: group for group in body['relief_by_date']}

    assert groups['2026-07-04']['games'][0]['context_label'] is None
    assert groups['2026-07-03']['games'][0]['context_label'] is None
    assert 'Extended bullpen coverage' not in json.dumps(body)


def test_team_relief_work_starter_assignment_without_coverage_stays_silent(client):
    with client.application.app_context():
        starter = _pitcher(name='Delta Starter', mlb_id=95001)
        relievers = [
            _pitcher(name=f'Reliever {suffix}', mlb_id=95002 + index)
            for index, suffix in enumerate(['One', 'Two', 'Three', 'Four', 'Five', 'Six'])
        ]
        db.session.add_all([starter, *relievers])
        db.session.flush()
        db.session.add(_log(
            starter.id, 9700, date(2026, 5, 28), games_started=1, outs=15, pitches=80,
        ))
        for offset in range(15):
            db.session.add(_log(
                starter.id, 9701 + offset, date(2026, 6, 1 + offset),
                outs=3, pitches=14,
            ))
        db.session.add(_log(
            starter.id, 9716, date(2026, 7, 5), games_started=1, outs=6, pitches=35,
        ))
        for reliever, outs, pitches in zip(
            relievers,
            (3, 3, 3, 4, 4, 4),
            (15, 17, 18, 19, 19, 19),
        ):
            db.session.add(_log(
                reliever.id, 9716, date(2026, 7, 5), outs=outs, pitches=pitches,
            ))
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    group = next(
        entry for entry in body['relief_by_date']
        if entry['game_date'] == '2026-07-05'
    )
    game = group['games'][0]

    assert game['context_label'] == 'Extended bullpen coverage'
    assert 'starter_assignment' not in game
    assert game['context_sentences'] == [
        'Delta Starter started and recorded 6 outs (2.0 IP) on 35 pitches.',
        'Six relievers covered the remaining 21 outs (7.0 IP) on 107 pitches.',
        '7 pitchers combined for 27 outs (9.0 IP) and 142 pitches.',
    ]
    assert game['total'] == {
        'pitcher_count': 7,
        'outs': 27,
        'innings': '9.0',
        'pitches': 142,
    }
    assert group['relief_appearances'] == 6
    assert group['outs_total'] == 21


def test_team_relief_work_verified_blackburn_ledger_emits_assignment(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        public_team_relief_work.board_freshness,
        'board_freshness_block',
        lambda: {
            'data_through': '2026-07-09',
            'freshness_state': 'current',
            'is_current': True,
            'label': 'Public bullpen data is current through July 9, 2026.',
        },
    )
    appearance_dates = [
        (9700, date(2026, 5, 7), 1),
        (9701, date(2026, 5, 10), 0),
        (9702, date(2026, 5, 13), 0),
        (9703, date(2026, 5, 16), 0),
        (9704, date(2026, 5, 18), 0),
        (9705, date(2026, 5, 21), 0),
        (9706, date(2026, 5, 29), 0),
        (9707, date(2026, 6, 3), 0),
        (9708, date(2026, 6, 5), 0),
        (9709, date(2026, 6, 8), 0),
        (9710, date(2026, 6, 9), 0),
        (9711, date(2026, 6, 17), 0),
        (9712, date(2026, 6, 21), 0),
        (9713, date(2026, 6, 22), 0),
        (9714, date(2026, 6, 25), 0),
        (9715, date(2026, 6, 27), 0),
        (9716, date(2026, 6, 28), 0),
        (9717, date(2026, 7, 1), 0),
        (9718, date(2026, 7, 3), 0),
        (9719, date(2026, 7, 5), 0),
        (9720, date(2026, 7, 7), 0),
        (9900, date(2026, 7, 9), 1),
    ]
    with client.application.app_context():
        starter = _pitcher(name='Paul Blackburn', mlb_id=621112)
        relievers = [
            _pitcher(name=f'Reliever {suffix}', mlb_id=96002 + index)
            for index, suffix in enumerate(['One', 'Two', 'Three', 'Four', 'Five', 'Six'])
        ]
        db.session.add_all([starter, *relievers])
        db.session.flush()
        for game_pk, game_date, games_started in appearance_dates:
            db.session.add(_final_game(game_pk, game_date))
            db.session.add(_log(
                starter.id,
                game_pk,
                game_date,
                games_started=games_started,
                outs=6 if game_pk == 9900 else 3,
                pitches=35 if game_pk == 9900 else 12,
            ))
        for reliever, outs, pitches in zip(
            relievers,
            (3, 3, 3, 4, 4, 4),
            (15, 17, 18, 19, 19, 19),
        ):
            db.session.add(_log(
                reliever.id, 9900, date(2026, 7, 9), outs=outs, pitches=pitches,
            ))
        db.session.flush()
        pitcher_season_ledger_coverage.reconcile_pitcher_season_coverage(
            starter,
            [
                _source_split(game_pk, game_date, games_started)
                for game_pk, game_date, games_started in appearance_dates
            ],
            season=2026,
            through_date=date(2026, 7, 9),
        )
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    group = next(
        entry for entry in body['relief_by_date']
        if entry['game_date'] == '2026-07-09'
    )
    game = group['games'][0]

    assert group['relief_appearances'] == 6
    assert group['outs_total'] == 21
    assert group['pitches_total'] == 107
    assert game['starter_assignment'] == {
        'narrative_type': 'first_start_in_days_after_relief_run',
        'sentence': (
            'Paul Blackburn made his first start in 63 days after '
            '20 consecutive relief appearances.'
        ),
        'previous_start_date': '2026-05-07',
        'days_since_previous_start': 63,
        'consecutive_relief_appearances': 20,
    }
    assert game['context_sentences'] == [
        (
            'Paul Blackburn made his first start in 63 days after '
            '20 consecutive relief appearances.'
        ),
        'He recorded 6 outs (2.0 IP) on 35 pitches.',
        'Six relievers covered the remaining 21 outs (7.0 IP) on 107 pitches.',
    ]
    serialized = json.dumps(game)
    assert 'source_manifest_fingerprint' not in serialized
    assert 'stored_manifest_fingerprint' not in serialized
    assert 'coverage_status' not in serialized
    assert 'reason_codes' not in serialized


def test_team_relief_work_previous_start_history_without_coverage_stays_silent(client):
    with client.application.app_context():
        starter = _pitcher(name='Echo Starter', mlb_id=95001)
        first = _pitcher(name='Reliever One', mlb_id=95002)
        second = _pitcher(name='Reliever Two', mlb_id=95003)
        db.session.add_all([starter, first, second])
        db.session.flush()
        db.session.add_all([
            _log(starter.id, 9720, date(2026, 6, 1), outs=3, pitches=12),
            _log(starter.id, 9721, date(2026, 6, 2), outs=3, pitches=13),
            _log(starter.id, 9722, date(2026, 6, 20), games_started=1, outs=15, pitches=82),
            _log(starter.id, 9723, date(2026, 6, 25), outs=3, pitches=11),
            _log(starter.id, 9724, date(2026, 6, 28), outs=3, pitches=15),
            _log(starter.id, 9725, date(2026, 7, 1), outs=3, pitches=16),
            _log(starter.id, 9726, date(2026, 7, 3), outs=3, pitches=17),
            _log(starter.id, 9727, date(2026, 7, 5), games_started=1, outs=6, pitches=31),
            _log(first.id, 9727, date(2026, 7, 5), outs=8, pitches=34),
            _log(second.id, 9727, date(2026, 7, 5), outs=7, pitches=28),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    group = next(
        entry for entry in body['relief_by_date']
        if entry['game_date'] == '2026-07-05'
    )
    game = group['games'][0]

    assert game['context_label'] == 'Extended bullpen coverage'
    assert 'starter_assignment' not in game
    assert game['context_sentences'] == [
        'Echo Starter started and recorded 6 outs (2.0 IP) on 31 pitches.',
        'Two relievers covered the remaining 15 outs (5.0 IP) on 62 pitches.',
        '3 pitchers combined for 21 outs (7.0 IP) and 93 pitches.',
    ]


def test_team_relief_work_starter_assignment_short_gap_stays_silent(client):
    with client.application.app_context():
        starter = _pitcher(name='Delta Starter', mlb_id=95001)
        reliever = _pitcher(name='Reliever One', mlb_id=95002)
        db.session.add_all([starter, reliever])
        db.session.flush()
        db.session.add_all([
            _log(starter.id, 9730, date(2026, 6, 25), games_started=1, outs=15, pitches=88),
            _log(starter.id, 9731, date(2026, 6, 27), outs=3, pitches=12),
            _log(starter.id, 9732, date(2026, 6, 29), outs=3, pitches=13),
            _log(starter.id, 9733, date(2026, 7, 1), outs=3, pitches=14),
            _log(starter.id, 9734, date(2026, 7, 3), outs=3, pitches=15),
            _log(starter.id, 9735, date(2026, 7, 5), games_started=1, outs=6, pitches=30),
            _log(reliever.id, 9735, date(2026, 7, 5), outs=15, pitches=55),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    group = next(
        entry for entry in body['relief_by_date']
        if entry['game_date'] == '2026-07-05'
    )
    game = group['games'][0]

    assert game['context_label'] == 'Extended bullpen coverage'
    assert 'starter_assignment' not in game
    assert game['context_sentences'] == [
        'Delta Starter started and recorded 6 outs (2.0 IP) on 30 pitches.',
        'One reliever covered the remaining 15 outs (5.0 IP) on 55 pitches.',
        '2 pitchers combined for 21 outs (7.0 IP) and 85 pitches.',
    ]


def test_team_relief_work_starter_assignment_short_relief_run_stays_silent(client):
    with client.application.app_context():
        starter = _pitcher(name='Delta Starter', mlb_id=95001)
        reliever = _pitcher(name='Reliever One', mlb_id=95002)
        db.session.add_all([starter, reliever])
        db.session.flush()
        db.session.add_all([
            _log(starter.id, 9740, date(2026, 5, 28), games_started=1, outs=15, pitches=90),
            _log(starter.id, 9741, date(2026, 7, 1), outs=3, pitches=12),
            _log(starter.id, 9742, date(2026, 7, 3), outs=3, pitches=13),
            _log(starter.id, 9743, date(2026, 7, 5), games_started=1, outs=6, pitches=29),
            _log(reliever.id, 9743, date(2026, 7, 5), outs=15, pitches=58),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    group = next(
        entry for entry in body['relief_by_date']
        if entry['game_date'] == '2026-07-05'
    )

    assert 'starter_assignment' not in group['games'][0]


def test_team_relief_work_starter_assignment_unknown_flag_stays_silent(client):
    with client.application.app_context():
        starter = _pitcher(name='Delta Starter', mlb_id=95001)
        reliever = _pitcher(name='Reliever One', mlb_id=95002)
        db.session.add_all([starter, reliever])
        db.session.flush()
        db.session.add_all([
            _log(starter.id, 9750, date(2026, 5, 28), games_started=1, outs=15, pitches=85),
            _log(starter.id, 9751, date(2026, 6, 1), outs=3, pitches=12),
            _log(starter.id, 9752, date(2026, 6, 3), outs=3, pitches=13),
            _log(starter.id, 9753, date(2026, 6, 5), outs=3, pitches=14),
            _log(starter.id, 9754, date(2026, 6, 15), games_started=None, outs=3, pitches=15),
            _log(starter.id, 9757, date(2026, 7, 5), games_started=1, outs=6, pitches=33),
            _log(reliever.id, 9757, date(2026, 7, 5), outs=15, pitches=52),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    group = next(
        entry for entry in body['relief_by_date']
        if entry['game_date'] == '2026-07-05'
    )
    game = group['games'][0]

    assert game['context_label'] == 'Extended bullpen coverage'
    assert 'starter_assignment' not in game


def test_team_relief_work_first_start_of_season_without_coverage_stays_silent(client):
    with client.application.app_context():
        starter = _pitcher(name='Echo Starter', mlb_id=95001)
        reliever = _pitcher(name='Reliever One', mlb_id=95002)
        db.session.add_all([starter, reliever])
        db.session.flush()
        db.session.add(_log(
            starter.id, 9759, date(2025, 9, 20), games_started=1, outs=15, pitches=84,
        ))
        for offset in range(6):
            db.session.add(_log(
                starter.id, 9760 + offset, date(2026, 6, 1 + offset),
                outs=3, pitches=14,
            ))
        db.session.add_all([
            _log(starter.id, 9766, date(2026, 7, 5), games_started=1, outs=6, pitches=27),
            _log(reliever.id, 9766, date(2026, 7, 5), outs=15, pitches=57),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    group = next(
        entry for entry in body['relief_by_date']
        if entry['game_date'] == '2026-07-05'
    )
    game = group['games'][0]

    assert game['context_label'] == 'Extended bullpen coverage'
    assert 'starter_assignment' not in game
    assert game['context_sentences'] == [
        'Echo Starter started and recorded 6 outs (2.0 IP) on 27 pitches.',
        'One reliever covered the remaining 15 outs (5.0 IP) on 57 pitches.',
        '2 pitchers combined for 21 outs (7.0 IP) and 84 pitches.',
    ]
    serialized = json.dumps(body)
    assert 'major-league' not in serialized
    assert 'first start for' not in serialized


def test_team_relief_work_starter_assignment_few_season_relief_stays_silent(client):
    with client.application.app_context():
        starter = _pitcher(name='Echo Starter', mlb_id=95001)
        reliever = _pitcher(name='Reliever One', mlb_id=95002)
        db.session.add_all([starter, reliever])
        db.session.flush()
        for offset in range(4):
            db.session.add(_log(
                starter.id, 9770 + offset, date(2026, 6, 1 + offset),
                outs=3, pitches=14,
            ))
        db.session.add_all([
            _log(starter.id, 9776, date(2026, 7, 5), games_started=1, outs=6, pitches=26),
            _log(reliever.id, 9776, date(2026, 7, 5), outs=15, pitches=51),
        ])
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()
    group = next(
        entry for entry in body['relief_by_date']
        if entry['game_date'] == '2026-07-05'
    )

    assert 'starter_assignment' not in group['games'][0]


def test_team_relief_work_returns_404_for_unknown_team(client):
    response = client.get('/api/bullpen/teams/999999/relief-work')
    assert response.status_code == 404
    assert response.get_json() == {'error': 'team_not_found'}


def test_team_relief_work_freshness_block_reused_by_reference(client):
    freshness = {'data_through': '2026-07-05', 'freshness_state': 'current'}
    with client.application.app_context():
        pitcher = _pitcher()
        db.session.add(pitcher)
        db.session.commit()

        original_helper = (
            public_team_relief_work.board_freshness.board_freshness_block
        )
        public_team_relief_work.board_freshness.board_freshness_block = lambda: freshness
        try:
            payload = public_team_relief_work.build_public_team_relief_work_payload(TEAM_ID)
        finally:
            public_team_relief_work.board_freshness.board_freshness_block = (
                original_helper
            )

    assert payload['freshness'] is freshness


def test_team_relief_work_scope_sentence_present(client, monkeypatch):
    monkeypatch.setattr(
        public_team_relief_work.board_freshness,
        'board_freshness_block',
        lambda: {'data_through': None},
    )
    with client.application.app_context():
        pitcher = _pitcher()
        db.session.add(pitcher)
        db.session.commit()

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()

    assert body['scope_sentence'] == (
        'Covers pitchers currently on the TST roster per MLB roster data.'
    )


def test_team_relief_work_no_host_local_dates():
    for path in (SERVICE_PATH, STARTER_ASSIGNMENT_PATH, API_PATH):
        text = path.read_text(encoding='utf-8')
        for token in ('date.today', 'datetime.now', 'datetime.utcnow', 'utc_now'):
            assert token not in text


def test_team_relief_work_forbidden_vocabulary_lint():
    for path in (SERVICE_PATH, STARTER_ASSIGNMENT_PATH, API_PATH):
        text = path.read_text(encoding='utf-8')
        for term in FORBIDDEN_TERMS:
            assert not re.search(
                rf'(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])',
                text,
                flags=re.I,
            ), (path, term)


def test_public_team_relief_work_import_guard_allows_only_public_sources():
    assert _import_modules(SERVICE_PATH) == {
        'datetime',
        'sqlalchemy',
        'models.game_log',
        'models.pitcher',
        'services',
    }
    assert _import_modules(STARTER_ASSIGNMENT_PATH) == {
        'datetime',
        'sqlalchemy',
        'models.game_log',
        'services',
        'utils.games_started',
    }
    assert _import_modules(API_PATH) == {
        'flask',
        'services.public_team_relief_work',
    }


def test_internal_modules_do_not_import_public_team_relief_work():
    checked = set()
    for pattern in (
        'backend/services/internal_team_evidence.py',
        'backend/services/internal_pitcher_evidence.py',
        'backend/services/team_daily_read.py',
        'backend/services/reliever_daily_read.py',
        'backend/services/composed_read.py',
        'backend/services/legacy_read_*.py',
        'backend/services/sync.py',
        'backend/services/*evidence*.py',
    ):
        checked.update(REPO_ROOT.glob(pattern))
    assert checked
    for path in checked:
        text = path.read_text(encoding='utf-8', errors='ignore')
        assert 'public_team_relief_work' not in text, path
        assert 'team_recent_work' not in text, path
        assert '/relief-work' not in text, path


def test_team_relief_work_api_single_route_and_forbidden_terms():
    text = API_PATH.read_text(encoding='utf-8')
    assert '/relief-work' in text
    assert text.count('@team_recent_work_bp.route') == 1
    assert not re.search(
        r'\b(evidence|composed_read|legacy_read|audit|reconciliation|internal_team|internal_pitcher)\b',
        text,
        flags=re.I,
    )


def test_app_registers_team_relief_work_blueprint_static_contract():
    text = APP_PATH.read_text(encoding='utf-8')
    assert 'from api.team_recent_work import team_recent_work_bp' in text
    assert "app.register_blueprint(team_recent_work_bp, url_prefix='/api/bullpen')" in text


def test_existing_public_routes_behavior_freeze(monkeypatch):
    changed = _changed_files_vs_main()
    if not changed:
        pytest.skip('git diff against origin/main unavailable')

    changed = [path.replace('\\', '/') for path in changed]
    # backend/services/sync.py and backend/services/dashboard_snapshot.py were
    # removed from this freeze for the July 2026 appearance-ledger trust
    # incident (dead daily lane + missing publish gate). Their behavior is
    # pinned by dedicated regression suites (test_statusless_split_finality.py,
    # test_postgame_lookback.py, test_appearance_ledger.py).
    blocked_files = {
        'backend/api/bullpen.py',
        'backend/api/pitchers.py',
        'backend/api/recent_work.py',
        'backend/api/system.py',
        'backend/services/public_recent_work.py',
        'backend/services/board_freshness.py',
        'backend/services/team_story_previews.py',
    }
    allowed_internal_admin_files = {
        'backend/api/system.py',
    }
    allowed_phase_a_audience_signup_files = {
        'backend/migrations/versions/2f7b9c1a5d43_add_audience_subscribers.py',
        'frontend/src/components/home/IntelligenceSurface.jsx',
        'frontend/src/utils/api.js',
        'frontend/tests/intelligenceSurface.test.mjs',
    }
    allowed_bullpen_game_context_files = {
        'frontend/src/components/bullpen/TeamReliefWorkPanel.jsx',
        'frontend/tests/teamReliefWorkPanel.test.mjs',
    }
    allowed_pitcher_ledger_coverage_files = {
        'backend/migrations/versions/7c4d2e9f1a6b_add_pitcher_season_ledger_coverage.py',
    }
    allowed_public_what_changed_contract_files = {
        # Branch 1 public What Changed contract completion permits only the
        # dashboard storage condition and snapshot-unavailable fallback state.
        'backend/api/bullpen.py',
    }
    allowed_phase0i_roster_readiness_files = {
        'backend/api/bullpen.py',
        'frontend/src/adapters/operatingStateReadModel.js',
        'frontend/src/components/bullpen/board/BullpenBoardView.jsx',
            'frontend/src/components/bullpen/board/TonightsBullpenBoard.jsx',
            'frontend/src/components/bullpen/board/tonightsBullpenBoardView.js',
            'frontend/src/components/dashboard/Dashboard.jsx',
            'frontend/src/components/dashboard/AvailabilityDashboardSummary.jsx',
            'frontend/src/components/dashboard/availabilityDashboardSummaryView.js',
            'frontend/src/components/dashboard/injuryIlContextView.js',
            'frontend/tests/availabilityDashboardSummary.test.mjs',
            'frontend/tests/injuryIlContext.test.mjs',
            'frontend/tests/tonightsBullpenBoard.test.mjs',
        }
    allowed_public_role_vocabulary_files = {
        # fix/public-relief-role-consistency: one canonical public relief-role
        # vocabulary (middle_relief -> depth_arm -> Middle Relief Arm) across
        # the chip, disclosure, and dashboard surfaces.
        'frontend/src/utils/pitcherLabels.js',
        'frontend/src/components/bullpen/board/tonightsBullpenBoardView.js',
        'frontend/tests/fixtures/bullpenBoardFixtures.mjs',
        'frontend/tests/pitcherLabels.test.mjs',
        'frontend/tests/pitcherUsageRole.test.mjs',
    }
    allowed_relief_role_input_integrity_files = {
        # fix/relief-role-input-integrity: one backend-authored public role
        # read owns the chip and disclosure; Compare inherits it untransformed.
        'frontend/tests/teamBullpenComparison.test.mjs',
    }
    allowed_legacy_retirement_files = {
        'backend/api/system.py',
        'frontend/package-lock.json',
        'frontend/package.json',
        'frontend/src/App.jsx',
        'frontend/src/components/admin/ProductIntelligenceAdmin.jsx',
        'frontend/src/components/bullpen/Bullpen.jsx',
        'frontend/src/components/dashboard/BullpenLandscape.jsx',
        'frontend/src/components/home/IntelligenceSurface.jsx',
        'frontend/src/components/layout/Footer.jsx',
        'frontend/src/components/methodology/Methodology.jsx',
        'frontend/src/components/share/TeamShareButton.jsx',
        'frontend/src/components/stories/Stories.jsx',
        'frontend/src/components/trust/DataTrust.jsx',
        'frontend/src/hooks/useProductIntelligence.js',
        'frontend/src/utils/adminProductEvents.js',
        'frontend/src/utils/analytics.js',
        'frontend/src/utils/api.js',
        'frontend/src/utils/productIdentity.js',
        'frontend/src/utils/productIntelligence.js',
        'frontend/tests/analytics.test.mjs',
        'frontend/tests/authClient.test.mjs',
        'frontend/tests/intelligenceSurface.test.mjs',
        'frontend/tests/navigationRoutes.test.mjs',
        'frontend/tests/productIntelligence.test.mjs',
        'frontend/tests/productIntelligenceAdmin.test.mjs',
    }
    allowed_trusted_traffic_files = {
        'frontend/src/components/bullpen/Bullpen.jsx',
        'frontend/src/components/bullpen/board/BullpenComparisonView.jsx',
        'frontend/src/components/bullpen/board/TonightsBullpenBoard.jsx',
        'frontend/src/components/bullpen/board/teamBullpenComparisonView.js',
        'frontend/src/components/share/EvidenceShareMenu.jsx',
        'frontend/src/components/share/TeamShareButton.jsx',
        'frontend/src/components/stories/Stories.jsx',
        'frontend/src/utils/adminDateTime.js',
        'frontend/src/utils/evidenceCardModel.js',
        'frontend/src/utils/evidenceCardStory.js',
        'frontend/tests/canonicalEvidenceLinks.test.mjs',
        'frontend/src/utils/evidenceCardRenderer.js',
        'frontend/src/utils/evidenceCardText.js',
        'frontend/src/utils/shareActions.js',
        'frontend/src/utils/teamShare.js',
        'frontend/tests/evidenceCards.test.mjs',
        'frontend/tests/bullpenOperatingStateCard.test.mjs',
        'frontend/tests/operatingStateReadModel.test.mjs',
        'frontend/tests/fixtures/bullpenComparisonFixtures.mjs',
        'frontend/tests/shareActions.test.mjs',
        'frontend/tests/teamShare.test.mjs',
        'backend/migrations/versions/a9e4c7d2f1b6_add_trusted_external_traffic.py',
        'backend/migrations/versions/b2e7c4a9d1f3_add_traffic_evidence_context.py',
        'backend/migrations/versions/c4f8a2d6e9b3_add_traffic_share_actions.py',
        'backend/migrations/versions/d7e4f1a8c2b6_add_share_story_context.py',
        'frontend/src/components/TrafficRouteObserver.jsx',
        'frontend/src/components/admin/TrafficIntelligenceAdmin.jsx',
        'frontend/src/utils/trafficMeasurement.js',
        'frontend/src/utils/trafficReporting.js',
        'frontend/tests/trafficIntelligenceAdmin.test.mjs',
        'frontend/tests/trafficMeasurement.test.mjs',
    }
    allowed_wp42_schedule_files = {
        'backend/migrations/versions/e6b4c2a8d1f3_add_slate_games.py',
        'frontend/src/components/posts/PrivatePosts.jsx',
        'frontend/src/components/posts/privatePostsView.js',
        'frontend/tests/privatePosts.test.mjs',
        'backend/migrations/versions/f7c5d3b9a2e1_add_editorial_post_history.py',
        'backend/migrations/versions/a1d8e4c6b2f0_extend_editorial_post_history.py',
    }
    allowed_public_trust_consistency_files = {
        # fix/public-trust-consistency: the Data & Trust availability usage check
        # folds the internal Avoid tier into the single public Unavailable row so
        # the same public label never appears twice. Public vocabulary, sample
        # sizes, and conservative framing are unchanged.
        'frontend/src/components/trust/AvailabilityBacktestCard.jsx',
        'frontend/tests/availabilityBacktest.test.mjs',
    }
    allowed_mobile_navigation_first_use_files = {
        # feat/mobile-navigation-first-use-clarity: plain-language mobile menu with
        # primary bullpen destinations (Team Bullpens, Compare Bullpens, Reliever
        # Finder) and a compact first-use entry area on Today. Routes, query
        # behavior, and bullpen calculations are unchanged — labels and navigation
        # structure only.
        'frontend/src/components/Sidebar.jsx',
        'frontend/src/utils/navigation.js',
        'frontend/src/components/home/IntelligenceSurface.jsx',
        'frontend/src/components/bullpen/Bullpen.jsx',
        'frontend/tests/navigationRoutes.test.mjs',
        'frontend/tests/bullpenTabLabels.test.mjs',
        'frontend/tests/demoReadinessPolish.test.mjs',
        'frontend/tests/mobileNavigation.test.mjs',
        'frontend/tests/intelligenceSurface.test.mjs',
    }
    allowed_team_board_answer_hierarchy_files = {
        # feat/team-board-answer-hierarchy: the Team Board leads with the answer
        # (state, why, availability distribution, receipts, freshness) and moves
        # the secondary team story and game context behind clear disclosures. The
        # availability distribution reads the existing board count authority; no
        # bullpen calculation, availability classification, or role authority
        # changes.
        'frontend/src/components/bullpen/board/TonightsBullpenBoard.jsx',
        'frontend/src/components/bullpen/board/BullpenAvailabilityDistribution.jsx',
        'frontend/tests/teamBoardAnswerHierarchy.test.mjs',
    }
    allowed_reliever_finder_search_first_files = {
        # feat/reliever-finder-search-first: the Reliever Finder opens in a
        # neutral, search-first state (no broad reliever list until the visitor
        # searches, selects a team, or selects a public availability status),
        # defaults to a neutral name A-Z order, compacts the
        # search/team/availability/freshness controls into one responsive area
        # that fits a 320px column, and clarifies the workload column labels. No
        # bullpen calculation, availability classification, role authority, or
        # route/query changes.
        'frontend/src/components/bullpen/Bullpen.jsx',
        'frontend/src/components/bullpen/relieverFinderView.js',
        'frontend/tests/relieverFinder.test.mjs',
        'frontend/tests/phaseALaunchProtection.test.mjs',
    }
    allowed_methodology_public_first_files = {
        # feat/methodology-public-first-rewrite: the Methodology page explains the
        # public read process (evidence -> arm read -> team read -> freshness ->
        # limitations) in plain baseball language, with one fixed illustrative
        # worked example. It removes the composite-score/weight framing and no
        # longer fetches backend methodology data; it is presentation copy only.
        # No calculation, threshold, classification, or vocabulary changes.
        'frontend/src/components/methodology/Methodology.jsx',
        'frontend/tests/methodologyDescore.test.mjs',
        'frontend/tests/pageHierarchyDedupe.test.mjs',
    }
    allowed_data_trust_reader_first_files = {
        # feat/data-trust-reader-first-rewrite: the Data & Trust page leads with the
        # current public-data answer (served dashboard freshness authority), then
        # explains freshness/coverage, then the retrospective next-day usage check.
        # The usage-check formatting is made unknown-vs-zero honest (missing stays
        # em dash, incomplete merged Unavailable fails closed), the scored-pitcher
        # inventory diagnostic is removed, and Methodology/How to Read are linked.
        # Presentation only: no availability/usage-check calculation, threshold,
        # sync, snapshot, or API change.
        'frontend/src/components/trust/DataTrust.jsx',
        'frontend/src/components/trust/AvailabilityBacktestCard.jsx',
        'frontend/tests/availabilityBacktest.test.mjs',
        'frontend/tests/pageHierarchyDedupe.test.mjs',
        'frontend/tests/dashboardRealignment.test.mjs',
        'frontend/tests/syncStatus.test.mjs',
    }
    allowed_analytics_evidence_alignment_files = {
        # feat/analytics-evidence-alignment: align the existing privacy-bounded,
        # route-based traffic measurement with the evidence-first product. Adds the
        # bounded since_yesterday entry source for trusted-change links, a
        # consolidated "Evidence & Trust Use" reporting section (team read, recent
        # bullpen work, pitcher lane, reliever detail, comparison read/evidence,
        # reliever finder, methodology, data & trust views, since-yesterday opens,
        # deeper-evidence sessions and depth), and current internal display names.
        # Page views stay openings, not reading. No baseball intelligence,
        # classification, evidence, freshness, route, or public claim changes.
        'frontend/src/utils/evidenceLinks.js',
        'frontend/src/components/home/IntelligenceSurface.jsx',
        'frontend/src/components/admin/TrafficIntelligenceAdmin.jsx',
        'frontend/src/utils/trafficReporting.js',
        'frontend/tests/trafficMeasurement.test.mjs',
        'frontend/tests/trafficIntelligenceAdmin.test.mjs',
    }
    allowed_share_artifacts_domain_files = {
        # feature/share-artifacts-domain (Share Cards SC-01): the immutable share
        # artifact domain migration. Backend domain only — no rendering, routes,
        # or public runtime changes.
        'backend/migrations/versions/c1a7f4e2b9d6_add_share_artifacts.py',
        # feature/share-artifact-generation-cutover (Share Cards SC-03A): the
        # governed generation audit migration and the internal admin generation
        # endpoint. Backend orchestration/audit only — no public route or renderer.
        'backend/migrations/versions/e2b8d5a3c9f1_add_share_artifact_generation_audits.py',
        'backend/api/share_artifacts_admin.py',
    }
    assert not [
        path for path in changed
        if path not in allowed_share_artifacts_domain_files
        if path not in allowed_phase_a_audience_signup_files
        if path not in allowed_bullpen_game_context_files
        if path not in allowed_pitcher_ledger_coverage_files
        if path not in allowed_public_what_changed_contract_files
        if path not in allowed_phase0i_roster_readiness_files
        if path not in allowed_public_role_vocabulary_files
        if path not in allowed_relief_role_input_integrity_files
        if path not in allowed_legacy_retirement_files
        if path not in allowed_trusted_traffic_files
        if path not in allowed_wp42_schedule_files
        if path not in allowed_public_trust_consistency_files
        if path not in allowed_mobile_navigation_first_use_files
        if path not in allowed_team_board_answer_hierarchy_files
        if path not in allowed_reliever_finder_search_first_files
        if path not in allowed_methodology_public_first_files
        if path not in allowed_data_trust_reader_first_files
        if path not in allowed_analytics_evidence_alignment_files
        if (
            path in blocked_files and path not in allowed_internal_admin_files
        )
        or path.startswith('frontend/')
        or path.startswith('backend/migrations/')
    ]

    if (
        'backend/api/bullpen.py' in changed
        and 'backend/api/bullpen.py' not in allowed_phase0i_roster_readiness_files
    ):
        diff = _diff_vs_main('backend/api/bullpen.py')
        assert "payload['what_changed_since_yesterday'] = changes" in diff
        assert "'state': 'insufficient_context'" in diff
        assert "'reason_codes': [reason or 'dashboard_snapshot_unavailable']" in diff

    if (
        'backend/api/system.py' in changed
        and 'backend/api/system.py' not in allowed_legacy_retirement_files
    ):
        diff = _diff_vs_main('backend/api/system.py')
        assert '/internal/snapshot-audit' in diff
        assert '/internal/pitcher-evidence' in diff
        assert '@require_admin_token' in diff

        system_text = (REPO_ROOT / 'backend/api/system.py').read_text(encoding='utf-8')
        for route in (
            '/internal/team-evidence',
            '/internal/snapshot-audit',
            '/internal/pitcher-evidence',
        ):
            assert route in system_text
            assert re.search(
                rf"@system_bp\.route\('{re.escape(route)}', methods=\['GET'\]\)\s+@require_admin_token",
                system_text,
            )

    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('TEST_DATABASE_URL', 'sqlite:///:memory:')
    from app import create_app

    flask_app = create_app('test')
    rules = [str(rule) for rule in flask_app.url_map.iter_rules()]
    assert rules.count('/api/bullpen/teams/<int:team_id>/relief-work') == 1
    assert '/api/bullpen/pitchers/<int:pitcher_id>/recent-work' in rules
    assert '/api/bullpen/teams/<int:team_id>/bullpen' in rules
    assert '/api/system/internal/team-evidence' in rules


def _freshness_block():
    return {
        'data_through': '2026-07-05',
        'freshness_state': 'current',
        'is_current': True,
        'label': 'Public bullpen data is current through July 5, 2026.',
    }


def _pitcher(
    *,
    name='Test Reliever',
    mlb_id=90001,
    team_id=TEAM_ID,
    roster_status='Active',
    active=True,
):
    return Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name='Test Club',
        team_abbreviation='TST',
        active=active,
        roster_status=roster_status,
        roster_status_source='mlb_roster_data',
    )


def _log(
    pitcher_id,
    game_pk,
    game_date,
    *,
    games_started=0,
    opponent='New York Yankees',
    opponent_abbreviation='NYY',
    outs=3,
    pitches=10,
    strikeouts=0,
    walks=0,
    hits=0,
    runs=0,
    save=False,
    hold=False,
    blown_save=False,
    win=False,
    loss=False,
):
    return GameLog(
        pitcher_id=pitcher_id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        opponent=opponent,
        opponent_abbreviation=opponent_abbreviation,
        games_started=games_started,
        innings_pitched=outs / 3,
        innings_pitched_outs=outs,
        pitches_thrown=pitches,
        strikeouts=strikeouts,
        walks=walks,
        hits_allowed=hits,
        runs_allowed=runs,
        save=save,
        hold=hold,
        blown_save=blown_save,
        win=win,
        loss=loss,
    )


def _final_game(game_pk, game_date):
    return ScheduledGame(
        team_id=TEAM_ID,
        game_pk=game_pk,
        game_date=game_date,
        status_state=ScheduledGame.STATE_FINAL,
        status_code='F',
        game_type='R',
    )


def _source_split(game_pk, game_date, games_started):
    return {
        'game': {'gamePk': game_pk, 'gameType': 'R'},
        'date': game_date.isoformat(),
        'stat': {'gamesStarted': games_started, 'inningsPitched': '1.0'},
    }


def _import_modules(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module)
    return modules


def _changed_files_vs_main():
    try:
        tracked = subprocess.run(
            ['git', 'diff', '--name-only', 'origin/main'],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        untracked = subprocess.run(
            ['git', 'ls-files', '--others', '--exclude-standard'],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    values = tracked.stdout.splitlines() + untracked.stdout.splitlines()
    return [line.strip() for line in values if line.strip()]


def _diff_vs_main(path):
    try:
        result = subprocess.run(
            ['git', 'diff', 'origin/main', '--', path],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ''
    return result.stdout
