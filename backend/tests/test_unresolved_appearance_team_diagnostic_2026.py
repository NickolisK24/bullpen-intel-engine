"""Read-only identity diagnostics for the unresolved 2026 appearance."""

from datetime import date
from pathlib import Path

import pytest
from flask import Flask

import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import appearance_team_authority as ata
from services import unresolved_appearance_team_diagnostic_2026 as diagnostic
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


GAME_DATE = date(2026, 6, 23)
GAME_PK = 824262
TARGET_MLB_ID = 700001
CANDIDATE_MLB_ID = 700099
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / '.github' / 'workflows' / 'unresolved_appearance_team_diagnostic_2026.yml'


@pytest.fixture
def app(monkeypatch):
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    monkeypatch.setattr(
        diagnostic,
        '_migration_head',
        lambda session: [diagnostic.EXPECTED_MIGRATION_HEAD],
    )
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _pitching_line(pid, name, *, ip='1.0', hits='0', runs='0', er='0', walks='0',
                   strikeouts='1', home_runs='0', games_started='0'):
    return {
        'person': {'id': pid, 'fullName': name},
        'stats': {'pitching': {
            'inningsPitched': ip,
            'hits': hits,
            'runs': runs,
            'earnedRuns': er,
            'baseOnBalls': walks,
            'strikeOuts': strikeouts,
            'homeRuns': home_runs,
            'gamesStarted': games_started,
        }},
    }


def _side(team_id, entries):
    ids = [pid for pid, _, _ in entries]
    players = {
        f'ID{pid}': _pitching_line(pid, name, **stats)
        for pid, name, stats in entries
    }
    return {
        'team': {'id': team_id, 'name': f'Team{team_id}'},
        'pitchers': ids,
        'players': players,
    }


def _boxscore(include_target=False, extra_count=0):
    away = [(CANDIDATE_MLB_ID, 'Matching Candidate', {})]
    if include_target:
        away.append((TARGET_MLB_ID, 'Stored Identity', {
            'ip': '2.0', 'strikeouts': '3',
        }))
    for index in range(extra_count):
        away.append((710000 + index, f'Extra {index}', {
            'ip': '0.1', 'strikeouts': '0',
        }))
    return {
        'teams': {
            'away': _side(147, away),
            'home': _side(116, [(800002, 'Home Pitcher', {
                'ip': '6.0', 'games_started': '1', 'strikeouts': '6',
            })]),
        },
    }


class _Client:
    def __init__(self, boxscore):
        self.boxscore = boxscore
        self.calls = []

    def get_game_boxscore(self, game_pk):
        self.calls.append(game_pk)
        return self.boxscore


def _seed():
    pitcher = Pitcher(
        mlb_id=TARGET_MLB_ID,
        full_name='Historical Stored Pitcher',
        team_id=999,
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=GAME_PK,
        game_date=GAME_DATE,
        game_type='R',
        innings_pitched=1.0,
        innings_pitched_outs=3,
        hits_allowed=0,
        runs_allowed=0,
        earned_runs=0,
        walks=0,
        strikeouts=1,
        home_runs_allowed=0,
        games_started=0,
        appearance_team_status=ata.STATUS_UNRESOLVED,
        appearance_team_id=None,
        appearance_team_source=None,
        appearance_team_reason=ata.REASON_UNRESOLVED,
    )
    db.session.add(log)
    db.session.commit()
    return log


def _run(log, boxscore):
    return diagnostic.run_diagnostic(
        game_log_id=log.id,
        expected_game_pk=GAME_PK,
        expected_game_date=GAME_DATE,
        client=_Client(boxscore),
    )


def test_missing_stored_mlb_identity_reports_bounded_official_candidates(app):
    log = _seed()
    result = _run(log, _boxscore(include_target=False))

    assert result['result'] == diagnostic.RESULT_PASS
    assert result['database_writes_performed'] is False
    assert result['target']['pitcher_mlb_id'] == TARGET_MLB_ID
    assert result['target']['pitcher_name'] == 'Historical Stored Pitcher'
    assert result['target_mlb_id_present'] is False
    assert result['target_mlb_id_match_count'] == 0
    assert result['exact_stat_match_count'] == 1
    assert result['exact_stat_matches'][0]['player_id'] == CANDIDATE_MLB_ID
    assert result['official_game_teams'] == [
        {'side': 'away', 'team_id': 147, 'team_name': 'Team147'},
        {'side': 'home', 'team_id': 116, 'team_name': 'Team116'},
    ]
    stored = db.session.get(GameLog, log.id)
    assert stored.appearance_team_status == ata.STATUS_UNRESOLVED
    assert stored.appearance_team_id is None


def test_present_stored_mlb_identity_is_reported_without_repair(app):
    log = _seed()
    result = _run(log, _boxscore(include_target=True))
    assert result['target_mlb_id_present'] is True
    assert result['target_mlb_id_match_count'] == 1
    assert result['database_writes_performed'] is False


def test_official_line_output_is_bounded_and_deterministic(app):
    log = _seed()
    result = _run(log, _boxscore(include_target=False, extra_count=25))
    assert result['official_pitching_line_count'] > diagnostic.MAX_OFFICIAL_LINES
    assert result['official_pitching_lines_returned'] == diagnostic.MAX_OFFICIAL_LINES
    assert result['official_pitching_lines_truncated'] is True
    assert len(result['official_pitching_lines']) == diagnostic.MAX_OFFICIAL_LINES


def test_identity_guard_fails_closed(app):
    log = _seed()
    result = diagnostic.run_diagnostic(
        game_log_id=log.id,
        expected_game_pk=GAME_PK + 1,
        expected_game_date=GAME_DATE,
        client=_Client(_boxscore()),
    )
    assert result['result'] == diagnostic.RESULT_FAIL
    assert result['decision_reasons'] == ['target_identity_mismatch']
    assert result['database_writes_performed'] is False


def test_workflow_is_manual_private_and_read_only():
    source = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in source
    for trigger in ('\n  push:', '\n  schedule:', '\n  pull_request:', '\n  repository_dispatch:'):
        assert trigger not in source
    assert 'contents: read' in source
    assert 'database_writes_performed' in source
    assert '--apply' not in source
    assert 'confirmation' not in source
    assert 'expected_fingerprint' not in source
    assert 'ADMIN_API_TOKEN: ${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}' in source
