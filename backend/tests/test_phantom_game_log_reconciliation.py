"""Governed phantom GameLog reconciliation coverage."""

import ast
from datetime import date
from pathlib import Path

import pytest
from flask import Flask

import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import appearance_team_authority as ata
from services import phantom_game_log_reconciliation as reconciliation
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


GAME_DATE = date(2026, 6, 23)
GAME_PK = 824262
TARGET_MLB_ID = 445276
OTHER_MLB_ID = 518585
AWAY_TEAM = 147
HOME_TEAM = 116
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / '.github' / 'workflows' / 'phantom_game_log_reconciliation.yml'
SERVICE_PATH = REPO_ROOT / 'backend' / 'services' / 'phantom_game_log_reconciliation.py'


@pytest.fixture
def app(monkeypatch):
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    monkeypatch.setattr(
        reconciliation,
        '_migration_head',
        lambda session: [reconciliation.EXPECTED_MIGRATION_HEAD],
    )
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _pitching_line(pid, name, *, innings='1.0'):
    return {
        'person': {'id': pid, 'fullName': name},
        'stats': {'pitching': {
            'inningsPitched': innings,
            'hits': '0',
            'runs': '0',
            'earnedRuns': '0',
            'baseOnBalls': '0',
            'strikeOuts': '1' if innings != '0.0' else '0',
            'homeRuns': '0',
            'gamesStarted': '0',
        }},
    }


def _side(team_id, entries):
    return {
        'team': {'id': team_id, 'name': f'Team{team_id}'},
        'pitchers': [pid for pid, _, _ in entries],
        'players': {
            f'ID{pid}': _pitching_line(pid, name, innings=innings)
            for pid, name, innings in entries
        },
    }


def _boxscore(*, include_target=False, duplicate_target=False):
    away = [(OTHER_MLB_ID, 'Other Pitcher', '1.0')]
    if include_target:
        away.append((TARGET_MLB_ID, 'Kenley Jansen', '0.0'))
    if duplicate_target:
        away.append((TARGET_MLB_ID, 'Kenley Jansen Duplicate', '0.0'))
    return {
        'teams': {
            'away': _side(AWAY_TEAM, away),
            'home': _side(HOME_TEAM, [(663554, 'Home Pitcher', '6.0')]),
        }
    }


class _Client:
    def __init__(self, boxscore=None):
        self.boxscore = boxscore if boxscore is not None else _boxscore()
        self.calls = []

    def get_game_boxscore(self, game_pk):
        self.calls.append(game_pk)
        return self.boxscore


def _seed(*, nonzero=False, status=ata.STATUS_UNRESOLVED, team_id=None):
    pitcher = Pitcher(
        mlb_id=TARGET_MLB_ID,
        full_name='Kenley Jansen',
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
        games_started=0,
        innings_pitched=0.0,
        innings_pitched_outs=0,
        pitches_thrown=0,
        strikes=0,
        hits_allowed=1 if nonzero else 0,
        runs_allowed=0,
        earned_runs=0,
        walks=0,
        strikeouts=0,
        home_runs_allowed=0,
        batters_faced=0,
        balls=0,
        games_finished=0,
        inherited_runners=0,
        inherited_runners_scored=0,
        save_situation=False,
        hold=False,
        blown_save=False,
        win=False,
        loss=False,
        save=False,
        appearance_team_status=status,
        appearance_team_id=team_id,
        appearance_team_source=None,
        appearance_team_reason=ata.REASON_UNRESOLVED,
    )
    db.session.add(log)
    db.session.commit()
    return log


def _run(log, *, client=None, **kwargs):
    return reconciliation.run_reconciliation(
        game_log_id=log.id,
        expected_game_pk=GAME_PK,
        expected_game_date=GAME_DATE,
        expected_pitcher_mlb_id=TARGET_MLB_ID,
        client=client or _Client(),
        **kwargs,
    )


def test_dry_run_proves_zero_stat_row_absent_from_official_boxscore(app):
    log = _seed()
    result = _run(log)

    assert result['result'] == reconciliation.RESULT_PASS
    assert result['mode'] == 'dry_run'
    assert result['decision_reasons'] == ['verified_phantom_non_appearance_plan_ready']
    assert result['database_writes_performed'] is False
    assert result['rows_deleted'] == 0
    assert result['plan']['target']['pitcher_mlb_id'] == TARGET_MLB_ID
    assert result['plan']['official_evidence']['target_pitcher_present'] is False
    assert result['plan']['proposed_action'] == 'delete_phantom_game_log'
    assert len(result['plan']['fingerprint']) == 64
    assert db.session.get(GameLog, log.id) is not None


def test_legitimate_zero_out_official_pitching_line_is_preserved(app):
    log = _seed()
    result = _run(log, client=_Client(_boxscore(include_target=True)))

    assert result['result'] == reconciliation.RESULT_INCONCLUSIVE
    assert result['decision_reasons'] == ['official_pitching_line_present']
    assert result['database_writes_performed'] is False
    assert db.session.get(GameLog, log.id) is not None


def test_nonzero_row_is_never_a_phantom_candidate(app):
    log = _seed(nonzero=True)
    result = _run(log)

    assert result['result'] == reconciliation.RESULT_FAIL
    assert result['decision_reasons'] == ['target_not_all_zero_non_appearance_candidate']
    assert db.session.get(GameLog, log.id) is not None


def test_duplicate_official_identity_fails_closed(app):
    log = _seed()
    result = _run(log, client=_Client(_boxscore(include_target=True, duplicate_target=True)))

    assert result['result'] == reconciliation.RESULT_FAIL
    assert result['decision_reasons'] == ['official_pitching_identity_contradictory']
    assert db.session.get(GameLog, log.id) is not None


def test_apply_requires_confirmation_and_approved_fingerprint(app):
    log = _seed()
    dry = _run(log)
    refused = _run(
        log,
        apply=True,
        confirmation='wrong',
        expected_fingerprint=dry['plan']['fingerprint'],
    )

    assert refused['result'] == reconciliation.RESULT_REFUSED
    assert refused['database_writes_performed'] is False
    assert db.session.get(GameLog, log.id) is not None


def test_apply_deletes_only_verified_phantom_row(app):
    log = _seed()
    dry = _run(log)
    applied = _run(
        log,
        apply=True,
        confirmation=reconciliation.CONFIRMATION_PHRASE,
        expected_fingerprint=dry['plan']['fingerprint'],
    )

    assert applied['result'] == reconciliation.RESULT_PASS
    assert applied['decision_reasons'] == ['verified_phantom_non_appearance_deleted']
    assert applied['database_writes_performed'] is True
    assert applied['rows_deleted'] == 1
    assert db.session.get(GameLog, log.id) is None
    assert db.session.query(Pitcher).filter_by(mlb_id=TARGET_MLB_ID).one() is not None


def test_stale_fingerprint_refuses_after_target_change(app):
    log = _seed()
    dry = _run(log)
    log.pitches_thrown = 1
    db.session.commit()

    refused = _run(
        log,
        apply=True,
        confirmation=reconciliation.CONFIRMATION_PHRASE,
        expected_fingerprint=dry['plan']['fingerprint'],
    )
    assert refused['result'] == reconciliation.RESULT_FAIL
    assert refused['decision_reasons'] == ['target_not_all_zero_non_appearance_candidate']
    assert db.session.get(GameLog, log.id) is not None


def test_exact_pitcher_identity_guard_fails_closed(app):
    log = _seed()
    result = reconciliation.run_reconciliation(
        game_log_id=log.id,
        expected_game_pk=GAME_PK,
        expected_game_date=GAME_DATE,
        expected_pitcher_mlb_id=999999,
        client=_Client(),
    )
    assert result['result'] == reconciliation.RESULT_FAIL
    assert result['decision_reasons'] == ['target_pitcher_identity_mismatch']


def test_service_never_reads_pitcher_team_id_as_authority():
    tree = ast.parse(SERVICE_PATH.read_text(encoding='utf-8'))
    forbidden = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Attribute)
            and node.attr == 'team_id'
            and isinstance(node.value, ast.Name)
            and node.value.id == 'pitcher'
        )
    ]
    assert forbidden == []


def test_workflow_is_manual_guarded_and_private():
    source = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in source
    for trigger in ('\n  push:', '\n  schedule:', '\n  pull_request:', '\n  repository_dispatch:'):
        assert trigger not in source
    assert 'contents: read' in source
    assert reconciliation.CONFIRMATION_PHRASE in source
    assert 'expected_fingerprint' in source
    assert 'ADMIN_API_TOKEN: ${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}' in source
