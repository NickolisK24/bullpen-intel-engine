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
from services import public_team_relief_work
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / 'backend/services/public_team_relief_work.py'
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
    for path in (SERVICE_PATH, API_PATH):
        text = path.read_text(encoding='utf-8')
        for token in ('date.today', 'datetime.now', 'datetime.utcnow', 'utc_now'):
            assert token not in text


def test_team_relief_work_forbidden_vocabulary_lint():
    for path in (SERVICE_PATH, API_PATH):
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
    assert not [
        path for path in changed
        if (path in blocked_files and path not in allowed_internal_admin_files)
        or path.startswith('frontend/')
        or path.startswith('backend/migrations/')
    ]

    if 'backend/api/system.py' in changed:
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
