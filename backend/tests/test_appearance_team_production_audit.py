import argparse
import ast
from contextlib import nullcontext
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from types import ModuleType

from flask import Flask
import pytest
from sqlalchemy import text

from models.game_log import GameLog
from models.pitcher import Pitcher
from scripts import run_appearance_team_coverage_audit as cli
from services.appearance_team_authority import (
    REASON_CONFLICT,
    REASON_RESOLVED_BOXSCORE,
    REASON_UNRESOLVED,
    SOURCE_BOXSCORE,
    SOURCE_CONFLICT,
    STATUS_CONFLICT,
    STATUS_RESOLVED,
    STATUS_UNRESOLVED,
)
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db


SCRIPT = Path(cli.__file__)
CUTOVER = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest.fixture
def db_app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        db.session.execute(text(
            'CREATE TABLE IF NOT EXISTS alembic_version '
            '(version_num VARCHAR(32) NOT NULL PRIMARY KEY)'
        ))
        db.session.execute(text('DELETE FROM alembic_version'))
        db.session.execute(
            text('INSERT INTO alembic_version (version_num) VALUES (:head)'),
            {'head': cli.EXPECTED_MIGRATION_HEAD},
        )
        db.session.commit()
        try:
            yield flask_app
        finally:
            db.session.execute(text('DROP TABLE IF EXISTS alembic_version'))
            db.session.commit()
            db.session.remove()
            drop_test_schema(flask_app)


def _install_app_module(monkeypatch):
    module = ModuleType('app')

    class App:
        @staticmethod
        def app_context():
            return nullcontext()

    module.app = App()
    monkeypatch.setitem(sys.modules, 'app', module)


def _complete_payload(result=cli.RESULT_PASS):
    return {
        'capability': cli.CAPABILITY,
        'coverage_capability': cli.COVERAGE_CAPABILITY,
        'status': 'complete',
        'result': result,
        'mode': 'read_only',
        'database_writes_performed': False,
        'migration': {
            'expected_head': cli.EXPECTED_MIGRATION_HEAD,
            'current_heads': [cli.EXPECTED_MIGRATION_HEAD],
            'head_matches': True,
        },
        'coverage': {
            'total_game_logs': 2,
            'resolved': 1,
            'unresolved': 0,
            'conflict': 0,
            'null_legacy': 1,
            'by_source': {'boxscore_side': 1, 'null_legacy': 1},
            'by_season': {
                2026: {
                    'resolved': 1,
                    'unresolved': 0,
                    'conflict': 0,
                    'null_legacy': 1,
                },
            },
            'current_team_mismatch': 0,
        },
        'coverage_contract': {
            'status_total': 2,
            'source_total': 2,
            'season_total': 2,
            'totals_match': True,
        },
        'new_row_attribution': {
            'since_utc': '2026-07-26T00:00:00Z',
            'total': 1,
            'resolved': 1,
            'unresolved': 0,
            'conflict': 0,
            'null_legacy': 0,
            'status_recorded': 1,
        },
        'invalid_states': {'total': 0, 'counts': {}},
        'non_resolved': {
            'total': 1,
            'row_limit': 50,
            'returned': 1,
            'truncated': False,
            'rows': [],
        },
        'decision_reasons': ['post_cutover_rows_fully_resolved'],
    }


def _persist_pitcher():
    pitcher = Pitcher(
        mlb_id=990001,
        full_name='Audit Fixture',
        team_id=147,
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _log(pitcher, game_pk, *, created_at, status=None):
    source = None
    reason = None
    team_id = None
    if status == STATUS_RESOLVED:
        source = SOURCE_BOXSCORE
        reason = REASON_RESOLVED_BOXSCORE
        team_id = 147
    elif status == STATUS_UNRESOLVED:
        reason = REASON_UNRESOLVED
    elif status == STATUS_CONFLICT:
        source = SOURCE_CONFLICT
        reason = REASON_CONFLICT
    return GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=date(2026, 7, 26),
        innings_pitched=1.0,
        innings_pitched_outs=3,
        created_at=created_at,
        appearance_team_id=team_id,
        appearance_team_status=status,
        appearance_team_source=source,
        appearance_team_reason=reason,
    )


@pytest.mark.parametrize(
    ('result', 'expected_exit'),
    (
        (cli.RESULT_PASS, 0),
        (cli.RESULT_INCONCLUSIVE, 1),
        (cli.RESULT_FAIL, 2),
    ),
)
def test_cli_exit_contract_and_clean_artifact(
    monkeypatch,
    tmp_path,
    capsys,
    result,
    expected_exit,
):
    _install_app_module(monkeypatch)
    monkeypatch.setattr(
        cli,
        '_build_payload',
        lambda **_kwargs: _complete_payload(result),
    )
    output = tmp_path / 'appearance-team-production-audit.json'

    exit_code = cli.main([
        '--new-row-since',
        '2026-07-26T00:00:00Z',
        '--compact',
        '--quiet',
        '--output',
        str(output),
    ])

    assert exit_code == expected_exit
    artifact = json.loads(output.read_text(encoding='utf-8'))
    stdout = json.loads(capsys.readouterr().out)
    assert stdout == artifact
    assert artifact['result'] == result
    assert artifact['migration']['current_heads'] == [cli.EXPECTED_MIGRATION_HEAD]
    assert artifact['database_writes_performed'] is False


def test_cli_failure_artifact_reports_type_without_exception_message(
    monkeypatch,
    tmp_path,
    capsys,
):
    _install_app_module(monkeypatch)
    secret_bearing_message = 'postgresql://user:password@example.invalid/db'

    def fail_safely(**_kwargs):
        raise RuntimeError(secret_bearing_message)

    monkeypatch.setattr(cli, '_build_payload', fail_safely)
    output = tmp_path / 'appearance-team-production-audit.json'

    exit_code = cli.main([
        '--new-row-since',
        '2026-07-26T00:00:00Z',
        '--compact',
        '--quiet',
        '--output',
        str(output),
    ])

    assert exit_code == 2
    artifact_text = output.read_text(encoding='utf-8')
    artifact = json.loads(artifact_text)
    assert json.loads(capsys.readouterr().out) == artifact
    assert artifact == {
        'capability': cli.CAPABILITY,
        'coverage_capability': cli.COVERAGE_CAPABILITY,
        'status': 'failed',
        'result': cli.RESULT_FAIL,
        'mode': 'read_only',
        'database_writes_performed': False,
        'error_type': 'RuntimeError',
        'decision_reasons': ['audit_execution_failed'],
    }
    assert secret_bearing_message not in artifact_text


def test_real_audit_reports_head_totals_new_rows_and_bounded_non_resolved(
    db_app,
):
    pitcher = _persist_pitcher()
    db.session.add_all([
        _log(
            pitcher,
            7001,
            created_at=datetime(2026, 7, 25, 23, 0),
            status=None,
        ),
        _log(
            pitcher,
            7002,
            created_at=datetime(2026, 7, 26, 1, 0),
            status=STATUS_RESOLVED,
        ),
    ])
    db.session.commit()

    payload = cli._build_payload(
        session=db.session,
        new_row_since=CUTOVER,
        row_limit=1,
    )

    assert payload['result'] == cli.RESULT_PASS
    assert payload['migration'] == {
        'expected_head': cli.EXPECTED_MIGRATION_HEAD,
        'current_heads': [cli.EXPECTED_MIGRATION_HEAD],
        'head_matches': True,
    }
    assert payload['coverage']['total_game_logs'] == 2
    assert payload['coverage']['resolved'] == 1
    assert payload['coverage']['null_legacy'] == 1
    assert payload['coverage_contract']['totals_match'] is True
    assert payload['new_row_attribution'] == {
        'since_utc': '2026-07-26T00:00:00Z',
        'total': 1,
        'resolved': 1,
        'unresolved': 0,
        'conflict': 0,
        'null_legacy': 0,
        'status_recorded': 1,
    }
    assert payload['invalid_states']['total'] == 0
    assert payload['non_resolved']['total'] == 1
    assert payload['non_resolved']['row_limit'] == 1
    assert payload['non_resolved']['returned'] == 1
    assert payload['non_resolved']['truncated'] is False
    assert payload['non_resolved']['rows'][0]['mlb_game_pk'] == 7001


def test_classification_contract():
    migration = {'head_matches': True}
    coverage = {'totals_match': True}
    valid = {'total': 0}
    resolved = {
        'total': 1,
        'resolved': 1,
        'unresolved': 0,
        'conflict': 0,
        'null_legacy': 0,
    }

    assert cli._classify(
        migration=migration,
        coverage_contract=coverage,
        new_rows=resolved,
        invalid_states=valid,
    ) == (cli.RESULT_PASS, ['post_cutover_rows_fully_resolved'])

    no_rows = {**resolved, 'total': 0, 'resolved': 0}
    assert cli._classify(
        migration=migration,
        coverage_contract=coverage,
        new_rows=no_rows,
        invalid_states=valid,
    )[0] == cli.RESULT_INCONCLUSIVE

    unresolved = {**resolved, 'resolved': 0, 'unresolved': 1}
    assert cli._classify(
        migration=migration,
        coverage_contract=coverage,
        new_rows=unresolved,
        invalid_states=valid,
    )[0] == cli.RESULT_INCONCLUSIVE

    null_new = {**resolved, 'resolved': 0, 'null_legacy': 1}
    assert cli._classify(
        migration=migration,
        coverage_contract=coverage,
        new_rows=null_new,
        invalid_states=valid,
    )[0] == cli.RESULT_FAIL

    assert cli._classify(
        migration={'head_matches': False},
        coverage_contract=coverage,
        new_rows=resolved,
        invalid_states=valid,
    )[0] == cli.RESULT_FAIL
    assert cli._classify(
        migration=migration,
        coverage_contract={'totals_match': False},
        new_rows=resolved,
        invalid_states=valid,
    )[0] == cli.RESULT_FAIL
    assert cli._classify(
        migration=migration,
        coverage_contract=coverage,
        new_rows=resolved,
        invalid_states={'total': 1},
    )[0] == cli.RESULT_FAIL


def test_command_source_contains_no_database_mutation_calls_or_dml():
    source = SCRIPT.read_text(encoding='utf-8')
    tree = ast.parse(source)
    forbidden_methods = {
        'add',
        'add_all',
        'bulk_insert_mappings',
        'bulk_save_objects',
        'commit',
        'delete',
        'execute_update',
        'flush',
        'merge',
        'rollback',
        'update',
    }
    mutation_calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden_methods
    ]
    assert mutation_calls == []

    sql_literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and 'alembic_version' in node.value
    ]
    assert sql_literals
    assert all(value.strip().upper().startswith('SELECT ') for value in sql_literals)


def test_timestamp_and_row_limit_are_bounded():
    assert cli._utc_timestamp('2026-07-26T00:00:00Z') == CUTOVER
    assert cli._bounded_row_limit('1') == 1
    assert cli._bounded_row_limit(str(cli.MAX_ROW_LIMIT)) == cli.MAX_ROW_LIMIT
    with pytest.raises(argparse.ArgumentTypeError):
        cli._utc_timestamp('2026-07-26T00:00:00')
    with pytest.raises(argparse.ArgumentTypeError):
        cli._bounded_row_limit('0')
    with pytest.raises(argparse.ArgumentTypeError):
        cli._bounded_row_limit(str(cli.MAX_ROW_LIMIT + 1))
