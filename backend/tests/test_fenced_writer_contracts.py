"""A canonical writer never reports a write the database fence discarded.

Each production ownership fence (migration ``e3f6a9b2c5d8``) reverts an
undeclared write inside PostgreSQL while the ORM still believes the row was
written. Three production incidents came from exactly that: schedule finality
(§15A), roster status (§15B) and team assignment (§15C). These tests run the
real writers against the real migrated schema, triggers included, and require
every one to either land its write or report it as suppressed.
"""

import ast
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import text

import services.schedule_ingestion as schedule_ingestion
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import fence_audit
from services.intraday_identity_repair import apply_intraday_identity_findings
from services.roster_status import STATUS_ACTIVE, STATUS_IL_15
from services.roster_status_sync import (
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_ACTIVE,
    sync_roster_statuses,
)
import services.roster_status_sync as roster_status_sync_module
import services.intraday_identity_repair as identity_module
from services.team_assignment_sync import TEAM_ASSIGNMENT_ASSIGNED
from tests.test_roster_status_sync import FakeRosterClient, roster_entry
from tests.test_schedule_ingestion import (  # noqa: F401
    _adopt_like_sync_pipeline,
    _game,
    fenced_app,
    fenced_database_url,
)
from tests.test_slate_coverage import app  # noqa: F401
from tests.test_team_assignment_authority_precedence import _adopt, _pitcher
from utils.db import db


BACKEND = Path(__file__).resolve().parents[1]
KC, ATH = 118, 133


class IdentityClient:
    def __init__(self, team_id):
        self.team_id = team_id

    def get_all_teams(self):
        return [{'id': KC, 'name': 'Kansas City Royals', 'abbreviation': 'KC'},
                {'id': ATH, 'name': 'Athletics', 'abbreviation': 'ATH'}]

    def get_player_info(self, mlb_id):
        return {'id': mlb_id, 'fullName': f'Arm {mlb_id}',
                'currentTeam': {'id': self.team_id},
                'primaryPosition': {'code': '1', 'abbreviation': 'P'}}


def _finding(mlb_id, team_id):
    return {'mlb_player_id': mlb_id, 'observed_official_team_id': team_id,
            'change_type': 'team_assignment_change'}


def _adopted_pitcher(mlb_id, team_id):
    pitcher = _pitcher(mlb_id, team_id, status=TEAM_ASSIGNMENT_ASSIGNED)
    _adopt(pitcher, team_id)
    db.session.commit()
    return pitcher.id


def test_intraday_identity_repair_lands_an_official_move_on_an_adopted_pitcher(fenced_app):
    pitcher_id = _adopted_pitcher(930001, KC)

    result = apply_intraday_identity_findings(
        [_finding(930001, ATH)], client=IdentityClient(ATH),
    )
    db.session.commit()
    db.session.remove()

    moved = db.session.get(Pitcher, pitcher_id)
    assert moved.team_id == ATH
    assert result['reassigned'] == 1
    assert result['fence_suppressed_writes'] == 0


def test_without_its_declaration_the_identity_repair_reports_the_suppression(
    fenced_app, monkeypatch,
):
    pitcher_id = _adopted_pitcher(930002, KC)
    monkeypatch.setattr(identity_module, '_declare_roster_ownership', lambda _team: None)

    result = apply_intraday_identity_findings(
        [_finding(930002, ATH)], client=IdentityClient(ATH),
    )
    db.session.commit()
    db.session.remove()

    # The writer counted a reassignment the database discarded; it now says so.
    assert result['reassigned'] == 1
    assert result['fence_suppressed_writes'] == 1
    assert db.session.get(Pitcher, pitcher_id).team_id == KC


def test_roster_status_sync_reports_suppressed_writes(fenced_app, monkeypatch):
    pitcher_id = _adopted_pitcher(930003, KC)
    injured = roster_entry(930003, 'Arm', status={'code': 'D15', 'description': '15-day IL'})
    rosters = {(KC, ROSTER_TYPE_ACTIVE): [], (KC, ROSTER_TYPE_40_MAN): [injured]}

    clean = sync_roster_statuses(team_ids=[KC], client=FakeRosterClient(rosters))
    assert clean['fence_suppressed_writes'] == 0
    assert db.session.get(Pitcher, pitcher_id).roster_status == STATUS_IL_15

    roster_status_sync_module._declare_roster_ownership(KC)
    pitcher = db.session.get(Pitcher, pitcher_id)
    pitcher.roster_status = STATUS_ACTIVE
    db.session.commit()
    assert db.session.get(Pitcher, pitcher_id).roster_status == STATUS_ACTIVE
    monkeypatch.setattr(roster_status_sync_module, '_declare_roster_ownership', lambda _team: None)
    fenced = sync_roster_statuses(team_ids=[KC], client=FakeRosterClient(rosters))
    db.session.remove()
    # Counted as changed, discarded by the database, and reported as such.
    assert fenced['pitchers_changed'] >= 1
    assert fenced['fence_suppressed_writes'] >= 1
    assert db.session.get(Pitcher, pitcher_id).roster_status == STATUS_ACTIVE


def test_schedule_ingestion_reports_suppressed_rows(fenced_app, monkeypatch):
    game_pk = 931001
    schedule_ingestion.ingest_games([_game(game_pk, official_date='2026-10-01')])
    _adopt_like_sync_pipeline([game_pk])
    monkeypatch.setattr(schedule_ingestion, '_declare_schedule_ownership', lambda _pks: None)

    final = _game(game_pk, official_date='2026-10-01', status_code='F',
                  detailed_state='Final', abstract_state='Final')
    summary = schedule_ingestion.ingest_games([final])
    db.session.remove()

    assert summary['rows_updated'] >= 1
    assert summary['rows_suppressed'] >= 1
    states = {row.status_state for row in ScheduledGame.query.filter_by(game_pk=game_pk)}
    assert states == {ScheduledGame.STATE_SCHEDULED}


def test_declared_schedule_ingestion_suppresses_nothing(fenced_app):
    game_pk = 931002
    schedule_ingestion.ingest_games([_game(game_pk, official_date='2026-10-01')])
    _adopt_like_sync_pipeline([game_pk])
    final = _game(game_pk, official_date='2026-10-01', status_code='F',
                  detailed_state='Final', abstract_state='Final')
    summary = schedule_ingestion.ingest_games([final])
    assert summary['rows_suppressed'] == 0


def test_fence_observation_is_none_where_no_fence_exists(app):  # noqa: F811
    with app.app_context():
        assert fence_audit.suppressed_writes_since(datetime(2026, 10, 1)) is None


# ---------------------------------------------------------------------------
# Static contract: every main writer of fenced pitcher projection fields
# declares roster ownership.
# ---------------------------------------------------------------------------

FENCED_PITCHER_FIELDS = {
    'team_id', 'team_name', 'team_abbreviation', 'active',
    'team_assignment_status', 'team_assignment_source', 'team_assignment_updated_at',
}


def _assigns_fenced_pitcher_field(tree):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr in FENCED_PITCHER_FIELDS
                and isinstance(target.value, ast.Name)
                and target.value.id == 'pitcher'
            ):
                return True
    return False


def test_every_pitcher_projection_writer_declares_roster_ownership():
    writers = []
    for path in sorted((BACKEND / 'services').glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        if _assigns_fenced_pitcher_field(tree):
            writers.append(path.name)
    assert writers == ['intraday_identity_repair.py', 'team_assignment_sync.py']
    for name in writers:
        source = (BACKEND / 'services' / name).read_text(encoding='utf-8')
        assert '_declare_roster_ownership' in source, name


def test_fence_inventory_is_documented():
    doc = (BACKEND / 'services' / 'fence_audit.py').read_text(encoding='utf-8')
    for resource in ('pitcher_projection', 'roster_snapshot', 'schedule',
                     'final_compatibility', 'transaction', 'game_observation'):
        assert resource in doc
    migration = (BACKEND / 'migrations' / 'versions'
                 / 'e3f6a9b2c5d8_fence_compatibility_writers.py').read_text(encoding='utf-8')
    for setting in ('roster_owner', 'schedule_owners', 'final_game_owner',
                    'transaction_owner', 'observation_owner'):
        assert f'baseballos.{setting}' in migration
        assert setting in doc or setting == 'observation_owner'


@pytest.mark.parametrize('module_name', ['schedule_ingestion', 'roster_status_sync'])
def test_declaring_writers_route_through_one_declaration(module_name):
    source = (BACKEND / 'services' / f'{module_name}.py').read_text(encoding='utf-8')
    assert source.count("set_config('baseballos.") == 1
    assert text  # sqlalchemy text is the declaration mechanism
