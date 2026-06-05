"""
Tests for Tonight's Bullpen Board.

Two layers:
  * Pure grouping service (services/bullpen_board.py) — no DB/Flask/network.
  * GET /api/bullpen/teams/<id>/board endpoint — in-memory SQLite, no MLB.

The board is presentation only: it must never rank, select, recommend, or
predict, and it must preserve the trust metadata (confidence, reasons,
limitations, freshness) the Availability Engine already produces.
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask

import services.sync as sync_service
from services.bullpen_board import (
    BOARD_GROUP_ORDER,
    build_board_payload,
    build_card,
    group_cards,
    short_reason_for,
)
from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
import models.prospect  # noqa: F401  (register on db.metadata)
from api.bullpen import bullpen_bp


def availability(status, confidence='high', data_state='fresh', reasons=None, limitations=None, inputs=None):
    return {
        'availability_status': status,
        'confidence': confidence,
        'data_state': data_state,
        'reasons': reasons or [],
        'limitations': limitations or ['No injury information available'],
        'inputs': inputs or {},
    }


def record(name, pitcher_id, fatigue_score, status, **kwargs):
    return {
        'name': name,
        'pitcher_id': pitcher_id,
        'fatigue_score': fatigue_score,
        'availability': availability(status, **kwargs),
    }


# ── Pure grouping service ──────────────────────────────────────────────────

class TestGrouping:
    def test_groups_are_in_canonical_order_and_complete(self):
        groups = group_cards([])
        assert [g['status'] for g in groups] == BOARD_GROUP_ORDER
        # Every named group is always present, even when empty.
        assert all(g['count'] == 0 and g['pitchers'] == [] for g in groups)

    def test_pitchers_land_in_their_status_group(self):
        cards = [
            build_card('A', 1, 10, availability('Available')),
            build_card('B', 2, 50, availability('Monitor')),
            build_card('C', 3, 65, availability('Limited')),
            build_card('D', 4, 80, availability('Avoid')),
            build_card('E', 5, 90, availability('Unavailable')),
        ]
        groups = {g['status']: g for g in group_cards(cards)}
        assert [c['name'] for c in groups['Available']['pitchers']] == ['A']
        assert [c['name'] for c in groups['Monitor']['pitchers']] == ['B']
        assert [c['name'] for c in groups['Limited']['pitchers']] == ['C']
        assert [c['name'] for c in groups['Avoid']['pitchers']] == ['D']
        assert [c['name'] for c in groups['Unavailable']['pitchers']] == ['E']

    def test_within_group_ordering_is_alphabetical_not_by_score(self):
        # Higher fatigue first would be "ranking"; the board must not do that.
        cards = [
            build_card('Zane', 1, 95, availability('Available')),
            build_card('alan', 2, 10, availability('Available')),
            build_card('Mike', 3, 30, availability('Available')),
        ]
        groups = {g['status']: g for g in group_cards(cards)}
        assert [c['name'] for c in groups['Available']['pitchers']] == ['alan', 'Mike', 'Zane']

    def test_unknown_status_is_excluded_from_named_groups(self):
        cards = [build_card('Ghost', 1, None, availability('Bogus'))]
        groups = group_cards(cards)
        assert all(g['pitchers'] == [] for g in groups)

    def test_group_labels_have_no_governance_jargon(self):
        forbidden = ('ranking', 'selection', 'recommend', 'predict', 'contract', 'governance', 'best')
        for group in group_cards([]):
            text = f"{group['label']} {group['description']}".lower()
            assert not any(term in text for term in forbidden), text


class TestCard:
    def test_card_preserves_trust_metadata(self):
        card = build_card('A', 7, 63.4, availability(
            'Limited',
            confidence='medium',
            reasons=['29 pitches yesterday', '3 appearances in 5 days'],
            limitations=['No injury information available', 'No team-reported availability'],
        ))
        assert card['confidence'] == 'medium'
        assert card['data_state'] == 'fresh'
        assert card['reasons'] == ['29 pitches yesterday', '3 appearances in 5 days']
        assert 'No injury information available' in card['limitations']
        assert card['fatigue_score'] == 63.4

    def test_card_handles_missing_score(self):
        card = build_card('A', 7, None, availability('Monitor', data_state='missing'))
        assert card['fatigue_score'] is None


class TestShortReason:
    def test_available_uses_positive_plain_language(self):
        assert short_reason_for(availability('Available', inputs={'appearances_last_5_days': 0})) == 'Minimal recent usage'
        assert short_reason_for(availability('Available', inputs={'appearances_last_5_days': 1, 'pitches_last_5_days': 12})) == 'Low recent workload'
        assert short_reason_for(availability('Available', inputs={'appearances_last_5_days': 2, 'pitches_last_5_days': 40})) == 'Fresh workload profile'

    def test_non_available_uses_first_engine_reason(self):
        reason = short_reason_for(availability('Avoid', reasons=['42 pitches yesterday', 'Back-to-back appearances']))
        assert reason == '42 pitches yesterday'

    def test_stale_and_missing_read_as_data_caveats(self):
        assert short_reason_for(availability('Monitor', data_state='stale')) == 'Data freshness limits confidence'
        assert short_reason_for(availability('Monitor', data_state='missing')) == 'Limited recent workload data'


class TestPayload:
    def test_payload_is_governance_safe(self):
        payload = build_board_payload(
            team={'team_id': 1, 'team_name': 'Test', 'team_abbreviation': 'TST'},
            records=[record('A', 1, 10, 'Available')],
            generated_at='2026-06-05T00:00:00+00:00',
        )
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert payload['capability'] == 'tonights_bullpen_board'

    def test_payload_totals_and_freshness_preserved(self):
        freshness = {'data_through': '2026-06-04', 'is_current': True, 'limitations': ['x']}
        payload = build_board_payload(
            team={'team_id': 1, 'team_name': 'Test', 'team_abbreviation': 'TST'},
            records=[
                record('A', 1, 10, 'Available'),
                record('B', 2, 50, 'Monitor'),
            ],
            freshness=freshness,
            limitations=['x'],
            generated_at='2026-06-05T00:00:00+00:00',
        )
        assert payload['total_pitchers'] == 2
        assert payload['ungrouped_pitchers'] == 0
        assert payload['freshness'] == freshness
        assert payload['limitations'] == ['x']

    def test_empty_team_still_returns_all_groups(self):
        payload = build_board_payload(
            team={'team_id': 9, 'team_name': None, 'team_abbreviation': None},
            records=[],
            generated_at='2026-06-05T00:00:00+00:00',
        )
        assert payload['total_pitchers'] == 0
        assert [g['status'] for g in payload['groups']] == BOARD_GROUP_ORDER


# ── Endpoint integration ───────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        db.create_all()
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            db.drop_all()


def _seed_pitcher(full_name, team_id=1, team_abbr='TST', mlb_id=None, raw_score=10.0, risk='LOW', games=1):
    """Create a pitcher with a recent game log and a fatigue score."""
    pitcher = Pitcher(
        mlb_id=mlb_id if mlb_id is not None else abs(hash(full_name)) % 100000,
        full_name=full_name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=team_abbr,
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()
    today = date.today()
    for i in range(games):
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=(abs(hash(full_name)) % 100000) + i,
            game_date=today - timedelta(days=i + 1),
            pitches_thrown=12,
        ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        raw_score=raw_score,
        risk_level=risk,
        calculated_at=datetime.utcnow(),
    ))
    db.session.commit()
    return pitcher


class TestBoardEndpoint:
    def test_returns_grouped_board_for_team(self, client):
        with client.application.app_context():
            _seed_pitcher('Aaron Arm', team_id=1, raw_score=10.0)
            _seed_pitcher('Zed Zito', team_id=1, raw_score=15.0)

        res = client.get('/api/bullpen/teams/1/board')
        assert res.status_code == 200
        body = res.get_json()

        assert body['capability'] == 'tonights_bullpen_board'
        assert body['ranking_applied'] is False
        assert body['selection_made'] is False
        assert [g['status'] for g in body['groups']] == BOARD_GROUP_ORDER
        assert body['total_pitchers'] == 2
        assert body['team']['team_id'] == 1
        # Freshness block is present and carries a data-through anchor.
        assert 'freshness' in body
        assert 'data_through' in body['freshness']

    def test_board_excludes_other_teams(self, client):
        with client.application.app_context():
            _seed_pitcher('Home Arm', team_id=1, mlb_id=1)
            _seed_pitcher('Away Arm', team_id=2, mlb_id=2)

        body = client.get('/api/bullpen/teams/1/board').get_json()
        names = [c['name'] for g in body['groups'] for c in g['pitchers']]
        assert names == ['Home Arm']

    def test_empty_team_returns_all_groups_and_zero_total(self, client):
        body = client.get('/api/bullpen/teams/999/board').get_json()
        assert body['total_pitchers'] == 0
        assert [g['status'] for g in body['groups']] == BOARD_GROUP_ORDER

    def test_no_raw_governance_flags_leak_into_cards(self, client):
        with client.application.app_context():
            _seed_pitcher('Solo Arm', team_id=1)
        body = client.get('/api/bullpen/teams/1/board').get_json()
        for group in body['groups']:
            for card in group['pitchers']:
                assert 'ranking_applied' not in card
                assert 'selection_made' not in card
