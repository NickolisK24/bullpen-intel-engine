"""Governed repair coverage for the single explicit unresolved 2026 appearance."""

from datetime import date
from pathlib import Path

import pytest
from flask import Flask

import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import appearance_team_authority as ata
from services import unresolved_appearance_team_repair_2026 as repair
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


GAME_DATE = date(2026, 6, 23)
GAME_PK = 824262
AWAY = 147
HOME = 116
PITCHER_MLB_ID = 700001
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / '.github' / 'workflows' / 'unresolved_appearance_team_repair_2026.yml'
SERVICE_PATH = REPO_ROOT / 'backend' / 'services' / 'unresolved_appearance_team_repair_2026.py'


@pytest.fixture
def app(monkeypatch):
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    monkeypatch.setattr(
        repair,
        '_migration_head',
        lambda session: [repair.EXPECTED_MIGRATION_HEAD],
    )
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _pitching_line(pid):
    return {
        'person': {'id': pid, 'fullName': f'P{pid}'},
        'stats': {'pitching': {
            'inningsPitched': '1.0',
            'earnedRuns': '0',
            'runs': '0',
            'hits': '0',
            'baseOnBalls': '0',
            'strikeOuts': '1',
            'homeRuns': '0',
            'numberOfPitches': '12',
            'strikes': '8',
        }},
    }


def _side(team_id, pitchers):
    return {
        'team': {'id': team_id, 'name': f'Team{team_id}'},
        'pitchers': list(pitchers),
        'players': {f'ID{pid}': _pitching_line(pid) for pid in pitchers},
    }


def _boxscore(include_target=True):
    away_pitchers = [PITCHER_MLB_ID] if include_target else [800001]
    return {
        'teams': {
            'away': _side(AWAY, away_pitchers),
            'home': _side(HOME, [800002]),
        }
    }


class _Client:
    def __init__(self, boxscore=None):
        self.boxscore = boxscore if boxscore is not None else _boxscore()
        self.calls = []

    def get_game_boxscore(self, game_pk):
        self.calls.append(game_pk)
        return self.boxscore


def _seed(current_team=999):
    pitcher = Pitcher(
        mlb_id=PITCHER_MLB_ID,
        full_name='Historical Pitcher',
        team_id=current_team,
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    db.session.add_all([
        ScheduledGame(
            team_id=HOME,
            game_pk=GAME_PK,
            game_date=GAME_DATE,
            status_state='final',
            home_away='home',
            opponent_team_id=AWAY,
        ),
        ScheduledGame(
            team_id=AWAY,
            game_pk=GAME_PK,
            game_date=GAME_DATE,
            status_state='final',
            home_away='away',
            opponent_team_id=HOME,
        ),
    ])
    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=GAME_PK,
        game_date=GAME_DATE,
        game_type='R',
        innings_pitched=1.0,
        innings_pitched_outs=3,
        appearance_team_status=ata.STATUS_UNRESOLVED,
        appearance_team_id=None,
        appearance_team_source=None,
        appearance_team_reason=ata.REASON_UNRESOLVED,
    )
    db.session.add(log)
    db.session.commit()
    return log


def _run(log, client=None, **kwargs):
    return repair.run_repair(
        game_log_id=log.id,
        expected_game_pk=GAME_PK,
        expected_game_date=GAME_DATE,
        client=client or _Client(),
        **kwargs,
    )


def test_dry_run_derives_official_boxscore_team_without_writing(app):
    log = _seed(current_team=HOME)
    result = _run(log)
    assert result['result'] == repair.RESULT_PASS
    assert result['mode'] == 'dry_run'
    assert result['database_writes_performed'] is False
    assert result['plan']['official_evidence'] == {
        'side': 'away', 'team_id': AWAY, 'opponent_team_id': HOME,
    }
    assert result['plan']['proposed'] == {
        'appearance_team_id': AWAY,
        'appearance_team_source': ata.SOURCE_BOXSCORE,
        'appearance_team_status': ata.STATUS_RESOLVED,
        'appearance_team_reason': ata.REASON_RESOLVED_BOXSCORE,
    }
    db.session.expire_all()
    stored = db.session.get(GameLog, log.id)
    assert stored.appearance_team_status == ata.STATUS_UNRESOLVED
    assert stored.appearance_team_id is None


def test_apply_requires_exact_confirmation_and_fingerprint(app):
    log = _seed()
    dry = _run(log)
    refused = _run(
        log,
        apply=True,
        confirmation='wrong',
        expected_fingerprint=dry['plan']['fingerprint'],
    )
    assert refused['result'] == repair.RESULT_REFUSED
    assert refused['database_writes_performed'] is False
    assert db.session.get(GameLog, log.id).appearance_team_status == ata.STATUS_UNRESOLVED


def test_apply_writes_only_approved_resolution(app):
    log = _seed(current_team=HOME)
    dry = _run(log)
    applied = _run(
        log,
        apply=True,
        confirmation=repair.CONFIRMATION_PHRASE,
        expected_fingerprint=dry['plan']['fingerprint'],
    )
    assert applied['result'] == repair.RESULT_PASS
    assert applied['rows_written'] == 1
    assert applied['database_writes_performed'] is True
    db.session.expire_all()
    stored = db.session.get(GameLog, log.id)
    assert stored.appearance_team_id == AWAY
    assert stored.appearance_team_status == ata.STATUS_RESOLVED
    assert stored.appearance_team_source == ata.SOURCE_BOXSCORE
    assert stored.appearance_team_reason == ata.REASON_RESOLVED_BOXSCORE
    assert stored.innings_pitched_outs == 3


def test_fingerprint_mismatch_refuses_without_write(app):
    log = _seed()
    refused = _run(
        log,
        apply=True,
        confirmation=repair.CONFIRMATION_PHRASE,
        expected_fingerprint='0' * 64,
    )
    assert refused['result'] == repair.RESULT_REFUSED
    assert 'fingerprint_mismatch' in refused['decision_reasons']
    assert db.session.get(GameLog, log.id).appearance_team_status == ata.STATUS_UNRESOLVED


def test_missing_official_pitching_line_fails_closed(app):
    log = _seed()
    result = _run(log, client=_Client(_boxscore(include_target=False)))
    assert result['result'] == repair.RESULT_FAIL
    assert result['decision_reasons'] == ['official_pitching_line_missing']
    assert result['database_writes_performed'] is False


def test_exact_identity_guard_fails_closed(app):
    log = _seed()
    result = repair.run_repair(
        game_log_id=log.id,
        expected_game_pk=GAME_PK + 1,
        expected_game_date=GAME_DATE,
        client=_Client(),
    )
    assert result['result'] == repair.RESULT_FAIL
    assert result['decision_reasons'] == ['target_identity_mismatch']


def test_service_never_uses_current_pitcher_team_as_authority():
    source = SERVICE_PATH.read_text(encoding='utf-8').lower()
    assert 'pitcher.team_id' not in source
    assert 'current_team' not in source


def test_workflow_is_manual_guarded_and_private():
    source = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in source
    for trigger in ('\n  push:', '\n  schedule:', '\n  pull_request:', '\n  repository_dispatch:'):
        assert trigger not in source
    assert 'contents: read' in source
    assert repair.CONFIRMATION_PHRASE in source
    assert 'expected_fingerprint' in source
    assert 'ADMIN_API_TOKEN: ${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}' in source
