from flask import Flask
import pytest

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.pitcher import Pitcher
from services import intraday_reconcile
from services.intraday_identity_repair import (
    IntradayIdentityRepairError,
    apply_intraday_identity_findings,
)
from services.intraday_repair import build_roster_repair_scope
from utils.db import db


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


class FakeClient:
    def __init__(self, people):
        self.people = people

    def get_player_info(self, player_id):
        return self.people.get(player_id)

    def get_all_teams(self):
        return [
            {'id': 143, 'name': 'Philadelphia Phillies', 'abbreviation': 'PHI'},
            {'id': 121, 'name': 'New York Mets', 'abbreviation': 'NYM'},
        ]


def _person(player_id, team_id, *, position='P', name='New Reliever'):
    return {
        'id': player_id,
        'fullName': name,
        'currentTeam': {'id': team_id},
        'primaryPosition': {'code': '1' if position == 'P' else '2', 'abbreviation': position},
    }


def _audit(findings):
    return {
        'status': intraday_reconcile.STATUS_SUCCESS,
        'lanes': {
            intraday_reconcile.LANE_ROSTER_ASSIGNMENT: {
                'verification_status': intraday_reconcile.LANE_COMPLETE,
                'differences': findings,
            }
        },
    }


def test_newly_discovered_pitcher_is_selected_for_identity_repair():
    finding = {
        'change_type': intraday_reconcile.CHANGE_NEWLY_DISCOVERED_ACTIVE,
        'severity': intraday_reconcile.SEVERITY_ACTIONABLE,
        'mlb_player_id': 777,
        'stored_pitcher_id': None,
        'observed_official_team_id': 143,
        'bullpen_population_effect': intraday_reconcile.EFFECT_ENTER,
    }
    scope = build_roster_repair_scope(_audit([finding]))
    assert scope['status'] == 'ready'
    assert scope['identity_findings'] == [finding]
    assert scope['affected_team_ids'] == [143]


def test_team_assignment_change_is_selected_for_identity_repair():
    finding = {
        'change_type': intraday_reconcile.CHANGE_TEAM_ASSIGNMENT_CHANGE,
        'severity': intraday_reconcile.SEVERITY_ACTIONABLE,
        'mlb_player_id': 200,
        'stored_pitcher_id': 5,
        'stored_team_id': 121,
        'observed_official_team_id': 143,
        'bullpen_population_effect': intraday_reconcile.EFFECT_ENTER,
    }
    scope = build_roster_repair_scope(_audit([finding]))
    assert scope['status'] == 'ready'
    assert scope['identity_findings'] == [finding]
    assert scope['affected_team_ids'] == [121, 143]


def test_conflicting_identity_remains_blocked():
    finding = {
        'change_type': intraday_reconcile.CHANGE_CONFLICTING_OFFICIAL_TEAM,
        'severity': intraday_reconcile.SEVERITY_REVIEW,
        'mlb_player_id': 555,
    }
    scope = build_roster_repair_scope(_audit([finding]))
    assert scope['status'] == 'blocked'
    assert scope['unsupported_findings'] == [finding]


def test_new_pitcher_is_created_from_numeric_identity_and_current_team(app):
    client = FakeClient({777: _person(777, 143, name='Verified Reliever')})
    finding = {
        'mlb_player_id': 777,
        'observed_official_team_id': 143,
        'source_player_name': 'Display Only',
    }
    with app.app_context():
        result = apply_intraday_identity_findings([finding], client=client)
        db.session.commit()
        pitcher = Pitcher.query.filter_by(mlb_id=777).one()
        assert result['created'] == 1
        assert pitcher.full_name == 'Verified Reliever'
        assert pitcher.team_id == 143
        assert pitcher.team_abbreviation == 'PHI'
        assert pitcher.active is True


def test_existing_pitcher_is_reassigned_only_when_current_team_agrees(app):
    with app.app_context():
        pitcher = Pitcher(
            mlb_id=200, full_name='Moved Reliever', team_id=121,
            team_name='New York Mets', team_abbreviation='NYM', position='P', active=True,
        )
        db.session.add(pitcher)
        db.session.commit()
        client = FakeClient({200: _person(200, 143, name='Moved Reliever')})
        result = apply_intraday_identity_findings([
            {'mlb_player_id': 200, 'observed_official_team_id': 143}
        ], client=client)
        db.session.commit()
        assert result['reassigned'] == 1
        assert pitcher.team_id == 143
        assert pitcher.team_abbreviation == 'PHI'


def test_non_pitcher_or_team_mismatch_fails_closed(app):
    with app.app_context():
        non_pitcher = FakeClient({888: _person(888, 143, position='C')})
        with pytest.raises(IntradayIdentityRepairError):
            apply_intraday_identity_findings([
                {'mlb_player_id': 888, 'observed_official_team_id': 143}
            ], client=non_pitcher)

        mismatch = FakeClient({999: _person(999, 121)})
        with pytest.raises(IntradayIdentityRepairError):
            apply_intraday_identity_findings([
                {'mlb_player_id': 999, 'observed_official_team_id': 143}
            ], client=mismatch)
