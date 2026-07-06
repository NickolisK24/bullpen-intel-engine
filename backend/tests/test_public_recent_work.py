import ast
import re
import subprocess
from datetime import date
from pathlib import Path

import pytest
from flask import Flask

from api.recent_work import recent_work_bp
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import public_recent_work
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / 'backend/services/public_recent_work.py'
API_PATH = REPO_ROOT / 'backend/api/recent_work.py'
APP_PATH = REPO_ROOT / 'backend/app.py'
FORBIDDEN_PUBLIC_COPY_TERMS = (
    'rested',
    'fresh',
    'available',
    'ready',
    'healthy',
    'injury-free',
    'fatigued',
    'workload risk',
    'clean',
    'messy',
    'heavy',
    'stressful',
    'efficient',
    'short rest',
    'back-to-back',
    '3-in-4',
    '4-in-6',
    'band',
    'observation',
    'leaned on',
    'trusted',
    'closer',
    'setup',
    'evidence',
    'citation',
    'confidence',
    'will',
    'should',
    'likely',
)


@pytest.fixture()
def client(monkeypatch):
    app = Flask('test_public_recent_work')
    configure_test_database(app)
    db.init_app(app)
    app.register_blueprint(recent_work_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        monkeypatch.setattr(
            public_recent_work.board_freshness,
            'board_freshness_block',
            lambda: _freshness_block(),
        )
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def test_recent_work_anchor_sourced_from_public_freshness_and_exact_payload(client):
    with client.application.app_context():
        pitcher = _pitcher()
        db.session.add(pitcher)
        db.session.flush()
        db.session.add_all([
            _log(
                pitcher.id,
                8001,
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
            _log(pitcher.id, 8002, date(2026, 7, 2), pitches=20),
            _log(pitcher.id, 8003, date(2026, 6, 29), pitches=17),
            _log(pitcher.id, 8004, date(2026, 6, 25), pitches=None),
            _log(pitcher.id, 8005, date(2026, 6, 22), pitches=10),
            _log(pitcher.id, 8006, date(2026, 6, 21), pitches=9),
            _log(pitcher.id, 8007, date(2026, 6, 6), pitches=12),
            _log(pitcher.id, 8008, date(2026, 6, 5), pitches=18),
        ])
        db.session.commit()
        pitcher_id = pitcher.id

    body = client.get(f'/api/bullpen/pitchers/{pitcher_id}/recent-work').get_json()

    assert set(body) == {
        'capability',
        'pitcher',
        'data_through',
        'freshness',
        'roster_status',
        'last_appearance',
        'recent_appearances',
        'workload',
    }
    assert body['capability'] == 'public_recent_work'
    assert body['data_through'] == '2026-07-05'
    assert body['freshness'] == _freshness_block()
    assert body['pitcher'] == {
        'id': pitcher_id,
        'mlb_id': 12345,
        'full_name': 'Test Reliever',
        'team_id': 110,
        'team_name': 'Test Club',
        'team_abbreviation': 'TST',
    }
    assert body['roster_status'] == {
        'status': 'Active',
        'source': 'mlb_roster_data',
        'sentence': 'On the active roster per MLB roster data.',
    }
    assert body['last_appearance'] == {
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
            'Last appearance: July 3 vs BOS \u2014 '
            '1.2 IP, 24 pitches, 2 K, 1 BB, 2 H, 1 R.'
        ),
        'timing_sentence': 'That appearance came 2 days before July 5.',
        'fact_sentences': [
            'Recorded a save (July 3).',
            'Recorded a hold (July 3).',
            'Charged with a blown save (July 3).',
            'Credited with the win (July 3).',
            'Charged with the loss (July 3).',
        ],
    }
    assert len(body['recent_appearances']) == 7
    assert body['recent_appearances'][0] == {
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
    }
    assert '2026-06-05' not in {
        line['game_date']
        for line in body['recent_appearances']
    }
    assert body['workload']['window_7'] == {
        'through': '2026-07-05',
        'appearances': 3,
        'pitches_total': 61,
        'appearances_with_pitches': 3,
        'sentence': '3 appearances in the 7 days through July 5.',
        'pitches_sentence': '61 pitches across those 3 appearances.',
    }
    assert body['workload']['window_14'] == {
        'through': '2026-07-05',
        'appearances': 5,
        'pitches_total': None,
        'appearances_with_pitches': 4,
        'sentence': '5 appearances in the 14 days through July 5.',
        'pitches_sentence': (
            'Pitch count unavailable for 1 of 5 appearances; '
            '71 pitches across the other 4.'
        ),
    }


def test_recent_work_last_appearance_same_day_omits_pitch_clause(client):
    with client.application.app_context():
        pitcher = _pitcher(mlb_id=12346)
        db.session.add(pitcher)
        db.session.flush()
        db.session.add(_log(
            pitcher.id,
            8101,
            date(2026, 7, 5),
            opponent_abbreviation='NYY',
            outs=3,
            pitches=None,
            strikeouts=1,
            walks=0,
        ))
        db.session.commit()
        pitcher_id = pitcher.id

    body = client.get(f'/api/bullpen/pitchers/{pitcher_id}/recent-work').get_json()

    assert body['last_appearance']['sentence'] == (
        'Last appearance: July 5 vs NYY \u2014 1.0 IP, 1 K, 0 BB.'
    )
    assert body['last_appearance']['timing_sentence'] == (
        'That appearance came on July 5.'
    )


def test_recent_work_no_anchor_omits_anchored_sections(client, monkeypatch):
    monkeypatch.setattr(
        public_recent_work.board_freshness,
        'board_freshness_block',
        lambda: {
            'data_through': None,
            'freshness_state': 'metadata_unavailable',
            'label': 'Public freshness metadata unavailable.',
        },
    )
    with client.application.app_context():
        pitcher = _pitcher(mlb_id=12347)
        db.session.add(pitcher)
        db.session.flush()
        db.session.add(_log(pitcher.id, 8201, date(2026, 7, 5), pitches=14))
        db.session.commit()
        pitcher_id = pitcher.id

    body = client.get(f'/api/bullpen/pitchers/{pitcher_id}/recent-work').get_json()

    assert set(body) == {
        'capability',
        'pitcher',
        'data_through',
        'freshness',
        'roster_status',
        'last_appearance',
        'recent_appearances',
    }
    assert body['data_through'] is None
    assert body['last_appearance'] is None
    assert body['recent_appearances'] == []
    assert 'workload' not in body
    assert 'absence_sentence' not in body


def test_recent_work_absence_and_zero_windows(client):
    with client.application.app_context():
        pitcher = _pitcher(mlb_id=12348)
        db.session.add(pitcher)
        db.session.commit()
        pitcher_id = pitcher.id

    body = client.get(f'/api/bullpen/pitchers/{pitcher_id}/recent-work').get_json()

    assert body['last_appearance'] is None
    assert body['recent_appearances'] == []
    assert body['absence_sentence'] == 'No appearances in the 30 days through July 5.'
    assert body['workload']['window_7'] == {
        'through': '2026-07-05',
        'appearances': 0,
        'pitches_total': 0,
        'appearances_with_pitches': 0,
        'sentence': '0 appearances in the 7 days through July 5.',
    }
    assert body['workload']['window_14'] == {
        'through': '2026-07-05',
        'appearances': 0,
        'pitches_total': 0,
        'appearances_with_pitches': 0,
        'sentence': '0 appearances in the 14 days through July 5.',
    }


def test_recent_work_boundaries_cap_and_doubleheader_count_per_appearance(client):
    with client.application.app_context():
        pitcher = _pitcher(mlb_id=12354)
        db.session.add(pitcher)
        db.session.flush()
        db.session.add_all([
            _log(pitcher.id, 8401, date(2026, 7, 5), pitches=8),
            _log(pitcher.id, 8402, date(2026, 7, 5), pitches=9),
            _log(pitcher.id, 8403, date(2026, 7, 4), pitches=10),
            _log(pitcher.id, 8404, date(2026, 7, 3), pitches=11),
            _log(pitcher.id, 8405, date(2026, 7, 2), pitches=12),
            _log(pitcher.id, 8406, date(2026, 7, 1), pitches=13),
            _log(pitcher.id, 8407, date(2026, 6, 30), pitches=14),
            _log(pitcher.id, 8408, date(2026, 6, 29), pitches=15),
            _log(pitcher.id, 8409, date(2026, 6, 28), pitches=16),
            _log(pitcher.id, 8410, date(2026, 6, 6), pitches=17),
            _log(pitcher.id, 8411, date(2026, 6, 5), pitches=18),
        ])
        db.session.commit()
        pitcher_id = pitcher.id

    body = client.get(f'/api/bullpen/pitchers/{pitcher_id}/recent-work').get_json()
    recent_dates = [line['game_date'] for line in body['recent_appearances']]

    assert len(body['recent_appearances']) == public_recent_work.RECENT_LINES_MAX
    assert recent_dates[:2] == ['2026-07-05', '2026-07-05']
    assert recent_dates == [
        '2026-07-05',
        '2026-07-05',
        '2026-07-04',
        '2026-07-03',
        '2026-07-02',
        '2026-07-01',
        '2026-06-30',
        '2026-06-29',
    ]
    assert body['workload']['window_7']['appearances'] == 8
    assert body['workload']['window_7']['sentence'] == (
        '8 appearances in the 7 days through July 5.'
    )
    assert body['workload']['window_14']['appearances'] == 9
    assert '2026-06-06' not in recent_dates
    assert '2026-06-05' not in recent_dates


def test_recent_work_roster_status_copy_variants(client):
    with client.application.app_context():
        active = _pitcher(mlb_id=12349, roster_status=None, active=True)
        inactive = _pitcher(
            mlb_id=12350,
            roster_status='Injured List',
            active=False,
        )
        missing = _pitcher(
            mlb_id=12351,
            roster_status=None,
            active=False,
        )
        db.session.add_all([active, inactive, missing])
        db.session.commit()
        active_id = active.id
        inactive_id = inactive.id
        missing_id = missing.id

    assert client.get(
        f'/api/bullpen/pitchers/{active_id}/recent-work'
    ).get_json()['roster_status']['sentence'] == (
        'On the active roster per MLB roster data.'
    )
    assert client.get(
        f'/api/bullpen/pitchers/{inactive_id}/recent-work'
    ).get_json()['roster_status']['sentence'] == (
        'Roster status: Injured List per MLB roster data.'
    )
    assert client.get(
        f'/api/bullpen/pitchers/{missing_id}/recent-work'
    ).get_json()['roster_status']['sentence'] == (
        'Roster status unavailable.'
    )


def test_recent_work_returns_404_for_unknown_pitcher(client):
    response = client.get('/api/bullpen/pitchers/999999/recent-work')
    assert response.status_code == 404
    assert response.get_json() == {'error': 'pitcher_not_found'}


def test_recent_work_freshness_block_reused_by_reference(client):
    freshness = {'data_through': '2026-07-05', 'freshness_state': 'current'}
    with client.application.app_context():
        pitcher = _pitcher(mlb_id=12352)
        db.session.add(pitcher)
        db.session.commit()

        original_helper = public_recent_work.board_freshness.board_freshness_block
        public_recent_work.board_freshness.board_freshness_block = lambda: freshness
        try:
            payload = public_recent_work.build_public_recent_work_payload(pitcher.id)
        finally:
            public_recent_work.board_freshness.board_freshness_block = original_helper

    assert payload['freshness'] is freshness


def test_recent_work_public_copy_uses_allowed_neutral_templates(client):
    with client.application.app_context():
        pitcher = _pitcher(mlb_id=12353)
        db.session.add(pitcher)
        db.session.flush()
        db.session.add(_log(
            pitcher.id,
            8301,
            date(2026, 7, 3),
            opponent_abbreviation='BOS',
            pitches=24,
            strikeouts=2,
            walks=1,
        ))
        db.session.commit()
        pitcher_id = pitcher.id

    body = client.get(f'/api/bullpen/pitchers/{pitcher_id}/recent-work').get_json()
    strings = list(_payload_strings(body))
    for value in strings:
        for term in FORBIDDEN_PUBLIC_COPY_TERMS:
            assert not re.search(
                rf'(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])',
                value,
                flags=re.I,
            ), (term, value)
    for key in ('window_7', 'window_14'):
        assert ' through July 5.' in body['workload'][key]['sentence']


def test_public_recent_work_import_guard_allows_only_public_sources():
    assert _import_modules(SERVICE_PATH) == {
        'datetime',
        'sqlalchemy',
        'models.game_log',
        'models.pitcher',
        'services',
    }
    assert _import_modules(API_PATH) == {
        'flask',
        'services.public_recent_work',
    }
    for path in (SERVICE_PATH, API_PATH):
        text = path.read_text(encoding='utf-8')
        assert not re.search(
            r'\b(evidence|composed_read|legacy_read|audit|reconciliation|internal_pitcher)\b',
            text,
            flags=re.I,
        )


def test_internal_evidence_read_audit_modules_do_not_import_public_recent_work():
    internal_files = set()
    for pattern in (
        'backend/services/*evidence*.py',
        'backend/services/*read*.py',
        'backend/services/*audit*.py',
        'backend/models/evidence_contract.py',
        'backend/models/composed_read.py',
        'backend/models/legacy_read_audit.py',
        'backend/api/system.py',
    ):
        internal_files.update(REPO_ROOT.glob(pattern))
    assert internal_files
    for path in internal_files:
        text = path.read_text(encoding='utf-8', errors='ignore')
        assert 'public_recent_work' not in text, path
        assert 'recent_work_bp' not in text, path
        assert '/recent-work' not in text, path


def test_recent_work_api_guard_compensating_assertions():
    _assert_recent_work_api_guard(API_PATH.read_text(encoding='utf-8'))


def test_recent_work_api_guard_rejects_second_route_decorator():
    source = (
        API_PATH.read_text(encoding='utf-8')
        + "\n\n@recent_work_bp.route('/other')\ndef other():\n    return {}\n"
    )
    with pytest.raises(AssertionError):
        _assert_recent_work_api_guard(source)


def test_app_factory_registers_recent_work_blueprint_static_contract():
    text = APP_PATH.read_text(encoding='utf-8')
    assert 'from api.recent_work import recent_work_bp' in text
    assert "app.register_blueprint(recent_work_bp, url_prefix='/api/bullpen')" in text


def test_legacy_public_logs_route_diff_clean_static_behavior_freeze():
    result = subprocess.run(
        ['git', 'diff', '--name-only', 'origin/main', '--', 'backend/api/bullpen.py'],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == ''


def _freshness_block():
    return {
        'data_through': '2026-07-05',
        'freshness_state': 'current',
        'is_current': True,
        'label': 'Public bullpen data is current through July 5, 2026.',
    }


def _pitcher(
    *,
    mlb_id=12345,
    roster_status='Active',
    active=True,
):
    return Pitcher(
        mlb_id=mlb_id,
        full_name='Test Reliever',
        team_id=110,
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


def _payload_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _payload_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _payload_strings(item)


def _import_modules(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module)
    return modules


def _assert_recent_work_api_guard(source):
    assert '/recent-work' in source
    assert source.count('@recent_work_bp.route') == 1
    assert not re.search(
        r'\b(evidence|composed_read|legacy_read|audit|reconciliation|internal_pitcher)\b',
        source,
        flags=re.I,
    )
