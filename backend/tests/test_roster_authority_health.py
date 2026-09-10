from datetime import date, datetime

import pytest
from flask import Flask

from services.daily_reconciliation import plan_morning_reconciliation
from services.roster_authority_health import roster_authority_coverage
from services.roster_transaction_authority import reconcile_team_roster
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db

import models.dashboard_snapshot  # noqa: F401
import models.prospect  # noqa: F401


DAY = date(2026, 9, 9)
NOW = datetime(2026, 9, 9, 15, 0)
TEAM_IDS = tuple(range(101, 131))


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


class Collection:
    def __init__(self, records, completeness='complete'):
        self.records = records
        self.completeness = completeness
        self.proof = {'record_count': len(records)}


class RosterClient:
    def __init__(self, partial_team_id=None):
        self.partial_team_id = partial_team_id

    def get_all_teams(self):
        return [{'id': value} for value in TEAM_IDS]

    def get_team_roster_with_completeness(
        self, team_id, roster_type='active', date=None, **_kwargs,
    ):
        mlb_id = 700000 + int(team_id)
        rows = [{
            'person': {'id': mlb_id, 'fullName': f'Pitcher {mlb_id}'},
            'position': {'abbreviation': 'P', 'type': 'Pitcher'},
        }]
        completeness = (
            'partial'
            if int(team_id) == self.partial_team_id and roster_type == 'active'
            else 'complete'
        )
        return Collection(rows, completeness)


def _seed(*, partial_team_id=None, through=30):
    client = RosterClient(partial_team_id=partial_team_id)
    plan = plan_morning_reconciliation(
        DAY,
        client=client,
        now=NOW,
        shadow_mode=True,
        publication_candidate_enabled=False,
        closure_checks_enabled=False,
    )
    for team_id in TEAM_IDS[:through]:
        reconcile_team_roster(
            team_id,
            DAY,
            client=client,
            timestamp=NOW,
            sync_run_id=plan.run_id,
            enqueue_downstream=False,
        )
    return plan


def test_roster_authority_report_requires_all_30_complete_current_teams(app):
    plan = _seed()
    report = roster_authority_coverage(DAY, now=NOW)

    assert report['status'] == 'complete'
    assert report['morning_sync_run_id'] == plan.run_id
    assert report['enumerated_teams'] == 30
    assert report['active_roster_coverage_count'] == 30
    assert report['forty_man_coverage_count'] == 30
    assert report['missing_team_ids'] == []
    assert all(row['active']['observation_id'] for row in report['teams'])
    assert all(row['active']['sync_run_id'] == plan.run_id for row in report['teams'])
    assert all(row['current_active_pitcher_intervals'] == 1 for row in report['teams'])


def test_roster_authority_report_fails_closed_at_29_of_30(app):
    _seed(through=29)
    report = roster_authority_coverage(DAY, now=NOW)

    assert report['status'] == 'incomplete'
    assert report['active_roster_coverage_count'] == 29
    assert report['missing_team_ids'] == [130]


def test_partial_roster_does_not_count_or_clear_prior_authority(app):
    _seed(partial_team_id=130)
    report = roster_authority_coverage(DAY, now=NOW)

    assert report['status'] == 'incomplete'
    assert report['active_roster_coverage_count'] == 29
    assert report['partial_team_ids'] == [130]
