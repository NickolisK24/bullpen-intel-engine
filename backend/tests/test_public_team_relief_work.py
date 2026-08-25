import ast
import json
import re
import subprocess
from datetime import date
from pathlib import Path

import pytest

import freeze_policy
from flask import Flask

from api.team_recent_work import team_recent_work_bp
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import pitcher_season_ledger_coverage
from services import public_team_relief_work
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.generated_team_pages import (
    GENERATED_TEAM_PAGE_ABBREVIATIONS,
    GENERATED_TEAM_PAGE_FILES,
)
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
            _log(
                other.id,
                9108,
                date(2026, 7, 3),
                pitches=99,
                appearance_team_id=111,
            ),
        ])
        db.session.commit()
        alpha_id = alpha.id
        beta_id = beta.id

    body = client.get(f'/api/bullpen/teams/{TEAM_ID}/relief-work').get_json()

    deployment = body.pop('deployment_profile')
    assert deployment['contract'] == 'team_board_deployment_profile_carrier_v1'
    assert deployment['status'] == 'complete'
    assert deployment['data_through'] == '2026-07-05'
    assert deployment['window_days'] == 14
    assert deployment['population_basis'] == 'official_appearance_team_relief_appearances'
    assert deployment['team_summary'] == {
        'represented_arm_count': 2,
        'pitchers_with_save_or_hold': 1,
        'pitchers_with_multi_inning_appearance': 2,
    }
    assert [item['pitcher_id'] for item in deployment['profiles']] == [alpha_id, beta_id]
    assert deployment['profiles'][0] == {
        'pitcher_id': alpha_id,
        'pitcher_mlb_id': 90001,
        'pitcher_name': 'Alpha Reliever',
        'appearances_analyzed': 2,
        'saves': 1,
        'holds': 1,
        'games_finished': 0,
        'appearances_with_games_finished': 0,
        'multi_inning_appearances': 1,
        'appearances_with_outs': 2,
        'most_recent_multi_inning_date': '2026-07-03',
        'limitations': [
            'Games-finished counts include only appearances with recorded finish authority.'
        ],
        'summary': (
            'Alpha Reliever recorded 1 save, 1 hold, and worked multiple innings '
            'in 1 of 2 relief appearances with recorded outs during the 14-day window.'
        ),
    }

    assert body == {
        'capability': 'public_team_relief_work',
        'team': {
            'team_id': TEAM_ID,
            'team_name': 'Test Club',
            'team_abbreviation': 'TST',
        },
        'data_through': '2026-07-05',
        'freshness': _freshness_block(),
        'scope_sentence': 'Covers appearances made for TST per official MLB game records.',
        'relief_by_date': [
            {
                'game_date': '2026-07-03',
                'relief_appearances': 2,
                'outs_total': 11,
                'pitches_total': 61,
                'appearances_with_pitches': 2,
                'game_pks': [9101, 9102],
                'game_count': 2,
                'sentence': (
                    'July 3 \u2014 2 relief appearances across 2 games, '
                    '3.2 IP, 61 pitches.'
                ),
                'appearances': [
                    {
                        'pitcher_id': alpha_id,
                        'pitcher_mlb_id': 90001,
                        'pitcher_full_name': 'Alpha Reliever',
                        'roster_status_sentence': 'On the active roster per MLB roster data.',
                        'mlb_game_pk': 9101,
                        'appearance_team_id': TEAM_ID,
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
                        'mlb_game_pk': 9102,
                        'appearance_team_id': TEAM_ID,
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
                'game_pks': [9103],
                'game_count': 1,
                'sentence': 'June 29 \u2014 1 relief appearance, 1.0 IP, 20 pitches.',
                'appearances': [
                    {
                        'pitcher_id': alpha_id,
                        'pitcher_mlb_id': 90001,
                        'pitcher_full_name': 'Alpha Reliever',
                        'roster_status_sentence': 'On the active roster per MLB roster data.',
                        'mlb_game_pk': 9103,
                        'appearance_team_id': TEAM_ID,
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
                'game_pks': [9104],
                'game_count': 1,
                'sentence': 'June 25 \u2014 1 relief appearance, 1.0 IP.',
                'appearances': [
                    {
                        'pitcher_id': beta_id,
                        'pitcher_mlb_id': 90002,
                        'pitcher_full_name': 'Beta Reliever',
                        'roster_status_sentence': 'On the active roster per MLB roster data.',
                        'mlb_game_pk': 9104,
                        'appearance_team_id': TEAM_ID,
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
        'scope_sentence': 'Covers appearances made for TST per official MLB game records.',
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
    assert body['deployment_profile']['profiles'] == []
    assert body['deployment_profile']['team_summary'] == {
        'represented_arm_count': 0,
        'pitchers_with_save_or_hold': 0,
        'pitchers_with_multi_inning_appearance': 0,
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


def test_deployment_profile_uses_team_at_appearance_and_outs_boundary(client):
    with client.application.app_context():
        current = _pitcher(name='Current Marker', mlb_id=90100)
        departed = _pitcher(
            name='Departed Reliever', mlb_id=90101, team_id=111, active=False
        )
        db.session.add_all([current, departed])
        db.session.flush()
        db.session.add_all([
            _log(
                departed.id, 9351, date(2026, 7, 5), outs=4,
                save=True, hold=True, games_finished=1,
                appearance_team_id=TEAM_ID,
            ),
            _log(
                departed.id, 9352, date(2026, 7, 4), outs=3,
                appearance_team_id=TEAM_ID,
            ),
        ])
        db.session.commit()

        carrier = public_team_relief_work.author_deployment_profile(
            TEAM_ID,
            data_through=date(2026, 7, 5),
        )

    profile = carrier['profiles'][0]
    assert profile['pitcher_name'] == 'Departed Reliever'
    assert profile['appearances_analyzed'] == 2
    assert profile['saves'] == 1
    assert profile['holds'] == 1
    assert profile['games_finished'] == 1
    assert profile['appearances_with_games_finished'] == 1
    assert profile['multi_inning_appearances'] == 1
    assert profile['appearances_with_outs'] == 2
    assert profile['most_recent_multi_inning_date'] == '2026-07-05'
    assert profile['limitations'] == [
        'Games-finished counts include only appearances with recorded finish authority.'
    ]


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
        relief_pitcher_ids = [reliever.id for reliever in relievers]

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
            'game_number': None,
            'appearance_team_id': TEAM_ID,
            'opponent': 'New York Yankees',
            'opponent_abbreviation': 'NYY',
            'game_shape': 'short_start',
            'context_label': 'Extended bullpen coverage',
            'starter_authority': 'official_completed_game_starter',
            'reconciled': True,
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
                'pitcher_ids': sorted(relief_pitcher_ids),
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
        'Covers appearances made for TST per official MLB game records.'
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
        'models.scheduled_game',
        'services',
        'utils.games_started',
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
    """Frozen public routes and their services stay byte-frozen on a branch.

    Exact paths only. The two directory clauses this guard used to carry --
    ``frontend/`` and ``backend/migrations/`` -- protected nothing named here
    and forced unrelated work into per-change allowlists; see
    backend/tests/freeze_policy.py. ``backend/api/system.py`` is frozen along
    with the public routes because the guard also pins its admin-gated internal
    routes, asserted below.
    """
    changed = _changed_files_vs_main()
    if not changed:
        pytest.skip('git diff against origin/main unavailable')

    # TEAM PREVIEW EVIDENCE SELECTION (H-7, cleanup/generated-copy-quality).
    #
    # The preview picked the board's FIRST governed reason, which is always the
    # available-count sentence. Three clubs in three different Team States
    # therefore published the same explanation, and that sentence is also the
    # one carrying provenance inside a baseball claim. It now ranks the reasons
    # the board already authored, most state-discriminating first.
    #
    # This is a reviewed reader-facing copy change, which is why it is named
    # here rather than waved through: the preview description now reads
    # "Two relievers are in the On Watch group." where it read "Five relievers
    # are available from the latest completed workload data."
    #
    # What did NOT change: no route, no payload shape, no count, no Team State,
    # no publication gate, no withheld/fail-closed path. Nothing is composed --
    # every candidate sentence is one bullpen_board already published, and
    # bullpen_board.py itself is untouched. Selection stays deterministic:
    # equal-rank reasons resolve to the board's own published order.
    #
    # Exact path only, never a directory exemption.
    approved_preview_evidence_selection = (
        'backend/services/team_story_previews.py',
    )
    moved = freeze_policy.protected_hits(
        changed,
        exact=freeze_policy.FROZEN_PUBLIC_ROUTE_PATHS,
        approved=(
            approved_preview_evidence_selection
            + freeze_policy.D054_LEAGUE_TEAM_STATE_LISTING_PATHS
            + freeze_policy.D055_TEAM_BOARD_WORKLOAD_CONTEXT_PATHS
            + freeze_policy.GAP51_REST_STATUS_CARRIER_PATHS
            + freeze_policy.GAP51_REST_STATUS_FROZEN_READER_PATHS
            + freeze_policy.GAP32_WORKLOAD_WINDOW_PATHS
            + freeze_policy.ROLES_DEPLOYMENT_INTELLIGENCE_PATHS
            + freeze_policy.PRE02_TEAM_BOARD_V2_PATHS
            + freeze_policy.PIT01_PITCHER_CURRENT_STATE_PATHS
        ),
    )
    assert moved == [], (
        f'frozen public route surfaces changed: {moved}. Changing reader-facing '
        'route behavior needs its own review.'
    )

    # Route registration is proved directly rather than inferred from a diff,
    # so it holds on every run instead of only when a comparison ref exists.
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

    # The internal routes stay admin-gated. Previously this only ran when the
    # branch diff happened to touch system.py and that change was allowlisted.
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


TEAM_PREVIEW_ROUTING_FILE = 'frontend/vercel.json'
CANONICAL_TEAM_REWRITE_SOURCE = (
    '^/team/(ATH|ATL|AZ|BAL|BOS|CHC|CIN|CLE|COL|CWS|DET|HOU|KC|LAA|LAD|MIA|'
    'MIL|MIN|NYM|NYY|PHI|PIT|SD|SEA|SF|STL|TB|TEX|TOR|WSH)$'
)
GENERIC_TEAM_FALLBACK_REWRITE = {
    'source': '/team/(.*)',
    'destination': '/team/index.html',
}
SPA_CATCH_ALL_REWRITE = {
    'source': '/(.*)',
    'destination': '/index.html',
}


def test_routed_team_preview_delivery_changes_routing_only():
    """The DIST-003 delivery allowance is an exemption from the path guard, not
    from its purpose.

    This guard freezes existing public route behavior. The routing table is
    allowed to change so the generated `/team/{ABBR}` pages stop resolving to
    the invalid-team fallback, so this proves what the exemption actually
    bought and, more importantly, what it did not: one exact-match rewrite is
    ADDED ahead of the generic fallback, and every route that already existed
    resolves exactly where it resolved before.

    ``frontend/tests/navigationRoutes.test.mjs`` owns the detailed frontend
    route-order contract and is not reproduced here. What is proved here is the
    governance question — that this frozen file changed for the #594 delivery
    correction and for nothing else.
    """
    config = json.loads(
        (REPO_ROOT / TEAM_PREVIEW_ROUTING_FILE).read_text(encoding='utf-8'),
    )
    rewrites = config['rewrites']
    sources = [rewrite['source'] for rewrite in rewrites]

    # (A) exact, and limited to the 30 supported abbreviations.
    assert CANONICAL_TEAM_REWRITE_SOURCE in sources
    canonical = rewrites[sources.index(CANONICAL_TEAM_REWRITE_SOURCE)]
    pattern = re.compile(CANONICAL_TEAM_REWRITE_SOURCE)
    assert len(GENERATED_TEAM_PAGE_ABBREVIATIONS) == 30
    for abbreviation in GENERATED_TEAM_PAGE_ABBREVIATIONS:
        assert pattern.fullmatch(f'/team/{abbreviation}'), abbreviation
        # ...and each one has the generated page this rewrite serves.
        assert (
            f'frontend/public/team/{abbreviation}/index.html'
            in GENERATED_TEAM_PAGE_FILES
        ), abbreviation

    # (B) the destination is exactly the generated file for the matched club.
    assert canonical['destination'] == '/team/$1/index.html'

    # (C) it resolves BEFORE the generic fallback, or every club path would
    # still reach the invalid-team page and the export would still be discarded.
    assert sources.index(CANONICAL_TEAM_REWRITE_SOURCE) < sources.index(
        GENERIC_TEAM_FALLBACK_REWRITE['source']
    )

    # (D) and (E) the two pre-existing routes survive unchanged, in order.
    assert GENERIC_TEAM_FALLBACK_REWRITE in rewrites
    assert SPA_CATCH_ALL_REWRITE in rewrites
    assert sources.index(GENERIC_TEAM_FALLBACK_REWRITE['source']) < sources.index(
        SPA_CATCH_ALL_REWRITE['source']
    )

    # (F) an unsupported abbreviation is NOT served a generated page; it keeps
    # falling through to the invalid-team fallback exactly as before.
    for unsupported in ('/team/INVALID', '/team/ath', '/team/ATHX', '/team/'):
        assert not pattern.fullmatch(unsupported), unsupported

    # (G) the change reaches no derivation, authority, or backend surface. A
    # rewrite table can only reach one by naming a destination that leaves the
    # static bundle, and none does.
    for rewrite in rewrites:
        assert rewrite['destination'].startswith('/')
        assert not rewrite['destination'].startswith('//')
        assert rewrite['destination'].endswith('.html')
        assert '/api/' not in rewrite['destination']

    source_text = (REPO_ROOT / TEAM_PREVIEW_ROUTING_FILE).read_text(
        encoding='utf-8',
    ).lower()
    for token in (
        'team_state', 'availability', 'fatigue', 'score', 'freshness',
        'roster', 'publication', 'prediction', 'recommendation', 'api',
        'backend', 'http',
    ):
        assert token not in source_text, token

    # And the diff itself: this file's only change vs main is inside the
    # rewrite table, adding the canonical rule. No header, no robots policy,
    # and no other route is touched.
    changed = {path.replace('\\', '/') for path in _changed_files_vs_main()}
    if TEAM_PREVIEW_ROUTING_FILE not in changed:
        return
    diff = _diff_vs_main(TEAM_PREVIEW_ROUTING_FILE)
    added = [
        line[1:].strip() for line in diff.splitlines()
        if line.startswith('+') and not line.startswith('+++')
    ]
    removed = [
        line[1:].strip() for line in diff.splitlines()
        if line.startswith('-') and not line.startswith('---')
    ]
    assert added, 'the routing file is in the diff but adds nothing'
    # Everything added belongs to the one canonical rewrite object.
    permitted_added = {
        '{',
        '},',
        '}',
        f'"source": "{CANONICAL_TEAM_REWRITE_SOURCE}",',
        '"destination": "/team/$1/index.html"',
    }
    assert not [line for line in added if line not in permitted_added], added
    # Nothing is removed but the brace the inserted object displaces.
    assert not [line for line in removed if line not in {'{', '},', '}'}], removed


BOARD_GROUP_VIEW_FILE = 'frontend/src/components/bullpen/board/tonightsBullpenBoardView.js'


def _backend_board_group_copy():
    """Every label and description the backend publishes for a board group."""
    tree = ast.parse(
        (REPO_ROOT / 'backend/services/bullpen_board.py').read_text(encoding='utf-8')
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == 'GROUP_META'
            for target in node.targets
        ):
            continue
        strings = set()
        for value in node.value.values:
            meta = ast.literal_eval(value)
            strings.add(meta['label'])
            strings.add(meta['description'])
        return strings
    raise AssertionError('backend GROUP_META not found')


def _frontend_board_group_copy():
    """The board's local fallback catalogue for the same groups."""
    source = (REPO_ROOT / BOARD_GROUP_VIEW_FILE).read_text(encoding='utf-8')
    block = source.split('const GROUP_FALLBACK_META = {', 1)[1].split('\n}', 1)[0]
    return {
        single or double
        for single, double in re.findall(
            r"""(?:label|description):\s*(?:'([^']*)'|"([^"]*)")""",
            block,
        )
    }


VOCABULARY_PARITY_FILES = (
    'frontend/src/utils/pitcherLabels.js',
    'frontend/src/components/bullpen/availabilityView.js',
    'frontend/src/components/dashboard/syncStatusView.js',
    'frontend/src/components/bullpen/board/teamGameContextView.js',
    'frontend/src/components/bullpen/board/tonightsBullpenBoardView.js',
)


def test_public_vocabulary_parity_changed_no_governed_logic():
    """The VOC-001 allowance is an exemption from the path guard, not its purpose.

    This guard freezes existing public route behavior. VOC-001 is allowed to
    touch reader-facing files because it changes what things are CALLED, never
    what the product decides. Rather than inspect the shape of the diff — a
    refactor that moves wording ownership legitimately changes non-string lines
    — this pins the invariants a wording change must not disturb: the raw values
    the API speaks, the variant keys that drive styling and logic, and the
    freshness authority itself.
    """
    root = REPO_ROOT / 'frontend/src'

    # The raw confidence values the API sends are untouched; only their display
    # strings moved. Every key still present, no key added.
    confidence = (root / 'components/bullpen/availabilityView.js').read_text(encoding='utf-8')
    block = confidence.split('const CONFIDENCE_READ_LABELS = {', 1)[1].split('}', 1)[0]
    assert sorted(re.findall(r'^\s*(\w+):', block, re.M)) == [
        'high', 'low', 'medium', 'none', 'unknown',
    ]

    # The data-status VARIANT keys drive styling and downstream logic and are
    # not reader-facing. They must survive a label change untouched.
    sync = (root / 'components/dashboard/syncStatusView.js').read_text(encoding='utf-8')
    for variant in (
        "variant: stale ? 'stale' : 'failed'",
        "variant: displayStale ? 'stale' : (limited ? 'limited' : 'synced')",
        "variant: 'metadata_unavailable'",
        "variant: 'empty'",
    ):
        assert variant in sync, variant

    # The freshness authority is not part of the vocabulary surface.
    assert 'export function freshnessIsCurrent(freshness) {' in sync
    freshness_diff = [
        line[1:].strip()
        for line in _diff_vs_main(
            'frontend/src/components/dashboard/syncStatusView.js'
        ).splitlines()
        if line.startswith(('+', '-')) and not line.startswith(('+++', '---'))
        and not line[1:].strip().startswith('//')
    ]
    assert not [line for line in freshness_diff if 'freshnessIsCurrent' in line]

    # The board's local group catalogue is a verbatim mirror of the backend's,
    # never a second vocabulary. Proving that first is what lets the word
    # 'threshold' through below: the only permitted occurrences are inside
    # backend-authored reader copy, quoted exactly as the backend publishes it.
    backend_group_copy = _backend_board_group_copy()
    assert _frontend_board_group_copy() == backend_group_copy

    # No threshold, window, or numeric tuning entered any of these files.
    comparison = re.compile(r'\S+\s*[<>]=?\s*-?\d+(?:\.\d+)?')
    for relative in VOCABULARY_PARITY_FILES:
        diff = _diff_vs_main(relative).splitlines()
        added = [
            line[1:] for line in diff
            if line.startswith('+') and not line.startswith('+++')
        ]
        carried_over = {
            found
            for line in diff
            if line.startswith('-') and not line.startswith('---')
            for found in comparison.findall(line[1:])
        }
        for line in added:
            body = line.strip()
            if body.startswith('//'):
                continue
            for found in comparison.findall(body):
                # A comparison is permitted only when it is carried over rather
                # than introduced: the identical expression must appear on a
                # line this same diff removed. Moving an existing non-empty test
                # is not tuning; a new number to compare against is.
                assert found in carried_over, (relative, body)
            if 'threshold' in body.lower():
                # Permitted only as backend copy reproduced byte for byte —
                # never as a tuning value the browser decides for itself.
                assert any(text in body for text in backend_group_copy), (relative, body)


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


def _final_game(team_id, game_pk, game_date):
    """Register official final-game authority for one team side, once."""
    seen = db.session.info.setdefault('_final_games', set())
    key = (team_id, game_pk)
    if key in seen:
        return
    seen.add(key)
    db.session.add(ScheduledGame(
        team_id=team_id,
        game_pk=game_pk,
        game_date=game_date,
        game_type='R',
        status_state=ScheduledGame.STATE_FINAL,
        status_code='F',
    ))


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
    games_finished=None,
    appearance_team_id=TEAM_ID,
    appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
    final_game=True,
):
    if final_game and appearance_team_id is not None:
        _final_game(appearance_team_id, game_pk, game_date)
    return GameLog(
        pitcher_id=pitcher_id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        opponent=opponent,
        opponent_abbreviation=opponent_abbreviation,
        games_started=games_started,
        appearance_team_id=appearance_team_id,
        appearance_team_status=appearance_team_status,
        appearance_team_source='boxscore_side',
        appearance_team_reason='appearance_team_resolved_boxscore',
        innings_pitched=(outs / 3 if outs is not None else None),
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
        games_finished=games_finished,
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
