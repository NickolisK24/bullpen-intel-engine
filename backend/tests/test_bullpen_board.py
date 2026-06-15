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
from tests.db_config import configure_test_database

import services.sync as sync_service
from services.availability import ACTIVE_WINDOW_DAYS
from services.bullpen_board import (
    BOARD_GROUP_ORDER,
    build_board_payload,
    build_card,
    group_cards,
    short_reason_for,
)
from services.roster_status import (
    ROSTER_STATUS_UNAVAILABLE_LIMITATION,
    STATUS_ACTIVE,
    STATUS_IL_15,
    STATUS_IL_60,
    STATUS_MINORS,
)
from services.team_assignment_sync import TEAM_ASSIGNMENT_ASSIGNED
from utils.db import db
from utils.innings import outs_to_decimal_innings, parse_mlb_innings_to_outs
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
        assert payload['stress']['state'] == payload['context']['health']['state']
        assert payload['stress']['label'] == 'Monitoring'
        assert 'score' not in payload['stress']
        assert payload['visibility'] == {
            'active_count': 2,
            'default_visible_count': 2,
            'hidden_unavailable_count': 0,
            'hidden_but_available_count': 0,
            'active_visible_count': 2,
            'active_hidden_count': 0,
            'hidden_active_pitchers': [],
        }

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
    configure_test_database(app)
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


def _seed_pitcher(
    full_name,
    team_id=1,
    team_abbr='TST',
    mlb_id=None,
    raw_score=10.0,
    risk='LOW',
    games=1,
    innings=None,
    days_ago=None,
    active=True,
    position='P',
    roster_status=STATUS_ACTIVE,
    roster_status_source='test_fixture',
    roster_status_updated_at=None,
    team_assignment_status=None,
    team_assignment_source=None,
    team_assignment_updated_at=None,
    games_started=None,
):
    """Create a pitcher with a recent game log and a fatigue score."""
    pitcher = Pitcher(
        mlb_id=mlb_id if mlb_id is not None else abs(hash(full_name)) % 100000,
        full_name=full_name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=team_abbr,
        position=position,
        active=active,
        roster_status=roster_status,
        roster_status_source=roster_status_source if roster_status else None,
        roster_status_updated_at=(
            roster_status_updated_at
            if roster_status_updated_at is not None
            else datetime.utcnow() if roster_status else None
        ),
        team_assignment_status=team_assignment_status,
        team_assignment_source=team_assignment_source,
        team_assignment_updated_at=team_assignment_updated_at,
    )
    db.session.add(pitcher)
    db.session.commit()
    today = date.today()
    innings = list(innings) if innings is not None else [1.0] * games
    days_ago = list(days_ago) if days_ago is not None else list(range(1, len(innings) + 1))
    games_started_values = list(games_started) if games_started is not None else None
    base_game_pk = (mlb_id if mlb_id is not None else abs(hash(full_name)) % 100000) * 100
    for i, innings_pitched in enumerate(innings):
        innings_outs = parse_mlb_innings_to_outs(innings_pitched)
        start_flag = games_started_values[i] if games_started_values is not None else (
            1 if innings_outs >= 9 else 0
        )
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=base_game_pk + i,
            game_date=today - timedelta(days=days_ago[i]),
            pitches_thrown=12,
            innings_pitched=outs_to_decimal_innings(innings_outs),
            innings_pitched_outs=innings_outs,
            games_started=start_flag,
            game_type='R',
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
        # Board V2 context layer rides along on the same response.
        assert 'context' in body
        assert body['context']['metrics']['total_relievers'] == 2
        assert body['context']['health']['state'] in (
            'manageable', 'monitoring', 'elevated', 'constrained', 'no_data',
        )
        assert body['stress']['state'] == body['context']['health']['state']
        assert body['stress']['summary']

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

    def test_cards_carry_an_observed_usage_role(self, client):
        with client.application.app_context():
            _seed_pitcher('Role Arm', team_id=1)
        body = client.get('/api/bullpen/teams/1/board').get_json()
        cards = [card for group in body['groups'] for card in group['pitchers']]
        assert cards, 'expected at least one card'
        for card in cards:
            assert 'role' in card and card['role'] is not None
            assert 'role_key' in card['role']
            assert card['role']['confidence'] in ('high', 'medium', 'low', 'none')

    def test_reds_default_board_excludes_clear_starters_but_keeps_rested_relievers(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Reds Clear Starter',
                team_id=113,
                team_abbr='CIN',
                mlb_id=11301,
                innings=[6.0, 5.1, 6.0],
                days_ago=[1, 6, 11],
            )
            _seed_pitcher(
                'Reds Active Reliever',
                team_id=113,
                team_abbr='CIN',
                mlb_id=11302,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
            )
            _seed_pitcher(
                'Reds Rested Reliever',
                team_id=113,
                team_abbr='CIN',
                mlb_id=11303,
                innings=[1.0, 1.0, 0.2],
                days_ago=[ACTIVE_WINDOW_DAYS + 5, ACTIVE_WINDOW_DAYS + 7, ACTIVE_WINDOW_DAYS + 9],
            )

        body = client.get('/api/bullpen/teams/113/board').get_json()
        cards = [card for group in body['groups'] for card in group['pitchers']]
        by_name = {card['name']: card for card in cards}

        assert set(by_name) == {'Reds Active Reliever', 'Reds Rested Reliever'}
        assert by_name['Reds Rested Reliever']['data_state'] == 'stale'
        assert by_name['Reds Rested Reliever']['visibility']['is_visible_by_default'] is True
        assert by_name['Reds Rested Reliever']['visibility']['has_current_workload'] is False
        assert body['total_pitchers'] == 2
        assert body['context']['metrics']['total_relievers'] == 2
        assert body['visibility']['active_hidden_count'] == 0

    def test_inactive_toggle_labels_stale_bullpen_relevant_pitchers_without_adding_starters(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Reds Stale Starter',
                team_id=113,
                team_abbr='CIN',
                mlb_id=11304,
                innings=[6.0, 5.0, 6.1],
                days_ago=[ACTIVE_WINDOW_DAYS + 5, ACTIVE_WINDOW_DAYS + 10, ACTIVE_WINDOW_DAYS + 15],
            )
            _seed_pitcher(
                'Reds Stale Reliever',
                team_id=113,
                team_abbr='CIN',
                mlb_id=11305,
                innings=[1.0, 0.2, 1.0],
                days_ago=[ACTIVE_WINDOW_DAYS + 5, ACTIVE_WINDOW_DAYS + 6, ACTIVE_WINDOW_DAYS + 8],
            )

        body = client.get('/api/bullpen/teams/113/board?include_stale=true').get_json()
        cards = [card for group in body['groups'] for card in group['pitchers']]
        names = [card['name'] for card in cards]

        assert names == ['Reds Stale Reliever']
        assert cards[0]['eligibility']['status'] == 'role_reliever'
        assert cards[0]['data_state'] == 'stale'
        assert cards[0]['visibility']['has_current_workload'] is False

    def test_active_rested_relief_context_stays_visible_without_show_unavailable(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Tampa Current Relief',
                team_id=139,
                team_abbr='TB',
                mlb_id=13901,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
                roster_status=STATUS_ACTIVE,
            )
            _seed_pitcher(
                'Nick Martinez',
                team_id=139,
                team_abbr='TB',
                mlb_id=607259,
                innings=[1.0, 0.2, 1.0],
                days_ago=[ACTIVE_WINDOW_DAYS + 2, ACTIVE_WINDOW_DAYS + 4, ACTIVE_WINDOW_DAYS + 6],
                roster_status=STATUS_ACTIVE,
            )

        default_body = client.get('/api/bullpen/teams/139/board').get_json()
        default_cards = [card for group in default_body['groups'] for card in group['pitchers']]
        default_by_name = {card['name']: card for card in default_cards}
        assert set(default_by_name) == {'Nick Martinez', 'Tampa Current Relief'}
        assert default_body['total_pitchers'] == 2
        assert default_body['visibility'] == {
            'active_count': 2,
            'default_visible_count': 2,
            'hidden_unavailable_count': 0,
            'hidden_but_available_count': 0,
            'active_visible_count': 2,
            'active_hidden_count': 0,
            'hidden_active_pitchers': [],
        }
        assert default_by_name['Nick Martinez']['availability_status'] == 'Monitor'
        assert default_by_name['Nick Martinez']['data_state'] == 'stale'
        assert default_by_name['Nick Martinez']['visibility']['has_current_workload'] is False
        assert default_by_name['Nick Martinez']['visibility']['is_visible_by_default'] is True
        assert default_by_name['Nick Martinez']['visibility']['hidden_until_show_unavailable'] is False

        expanded_body = client.get('/api/bullpen/teams/139/board?include_stale=true').get_json()
        expanded_cards = [card for group in expanded_body['groups'] for card in group['pitchers']]
        by_name = {card['name']: card for card in expanded_cards}

        assert set(by_name) == {'Nick Martinez', 'Tampa Current Relief'}
        assert by_name['Tampa Current Relief']['visibility']['is_visible_by_default'] is True
        nick_visibility = by_name['Nick Martinez']['visibility']
        assert nick_visibility['is_visible_by_default'] is True
        assert nick_visibility['is_public_bullpen_option'] is True
        assert nick_visibility['hidden_until_show_unavailable'] is False
        assert nick_visibility['hidden_reasons'] == []
        assert expanded_body['visibility'] == {
            'active_count': 2,
            'default_visible_count': 2,
            'hidden_unavailable_count': 0,
            'hidden_but_available_count': 0,
            'active_visible_count': 2,
            'active_hidden_count': 0,
            'hidden_active_pitchers': [],
        }

    def test_active_bullpen_option_with_no_recent_workload_is_visible_by_default(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Fully Rested Relief Option',
                team_id=139,
                team_abbr='TB',
                mlb_id=13909,
                raw_score=0,
                innings=[],
                days_ago=[],
                position='RP',
                roster_status=STATUS_ACTIVE,
            )

        body = client.get('/api/bullpen/teams/139/board').get_json()
        cards = [card for group in body['groups'] for card in group['pitchers']]

        assert [card['name'] for card in cards] == ['Fully Rested Relief Option']
        assert cards[0]['availability_status'] == 'Monitor'
        assert cards[0]['data_state'] == 'missing'
        assert cards[0]['eligibility']['status'] == 'role_reliever'
        assert cards[0]['visibility']['is_visible_by_default'] is True
        assert cards[0]['visibility']['has_current_workload'] is False
        assert cards[0]['visibility']['hidden_until_show_unavailable'] is False
        assert body['visibility']['active_hidden_count'] == 0
        assert body['visibility']['hidden_active_pitchers'] == []

    def test_il_and_minors_pitchers_are_excluded_from_default_board_counts(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Reds Active Relief Context',
                team_id=113,
                team_abbr='CIN',
                mlb_id=11320,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
                roster_status=STATUS_ACTIVE,
            )
            _seed_pitcher(
                'Graham Ashcraft',
                team_id=113,
                team_abbr='CIN',
                mlb_id=668933,
                innings=[1.0, 1.0, 0.2],
                days_ago=[1, 3, 5],
                roster_status=STATUS_IL_60,
            )
            _seed_pitcher(
                'Pierce Johnson',
                team_id=113,
                team_abbr='CIN',
                mlb_id=572955,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 2, 4],
                roster_status=STATUS_IL_15,
            )
            _seed_pitcher(
                'Connor Phillips',
                team_id=113,
                team_abbr='CIN',
                mlb_id=683175,
                innings=[1.0, 1.0, 0.2],
                days_ago=[1, 3, 5],
                roster_status=STATUS_MINORS,
            )

        body = client.get('/api/bullpen/teams/113/board').get_json()
        cards = [card for group in body['groups'] for card in group['pitchers']]
        names = [card['name'] for card in cards]

        assert names == ['Reds Active Relief Context']
        assert body['total_pitchers'] == 1
        assert body['context']['metrics']['total_relievers'] == 1
        assert body['roster_status']['excluded_inactive_count'] == 3

    def test_current_minor_assignment_overrides_stale_activated_label_on_board(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Valente Bellozo',
                team_id=115,
                team_abbr='COL',
                mlb_id=678129,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
                roster_status=STATUS_ACTIVE,
                roster_status_source='mlb_stats_api:transactions:activated',
                roster_status_updated_at=datetime(2026, 4, 1, 12, 0, 0),
                team_assignment_status=TEAM_ASSIGNMENT_ASSIGNED,
                team_assignment_source='mlb_stats_api:team_assignment_sync:fullRoster',
                team_assignment_updated_at=datetime(2026, 4, 13, 12, 0, 0),
            )

        default_body = client.get('/api/bullpen/teams/115/board').get_json()
        default_names = [
            card['name']
            for group in default_body['groups']
            for card in group['pitchers']
        ]

        assert default_names == []
        assert default_body['roster_status']['excluded_inactive_count'] == 1

        expanded_body = client.get('/api/bullpen/teams/115/board?include_stale=true').get_json()
        expanded_cards = [
            card
            for group in expanded_body['groups']
            for card in group['pitchers']
        ]

        assert [card['name'] for card in expanded_cards] == ['Valente Bellozo']
        card = expanded_cards[0]
        assert card['availability_status'] == 'Unavailable'
        assert card['roster_status']['status'] == STATUS_MINORS
        assert card['roster_status']['label'] == 'Minors'
        assert card['roster_status']['source'] == 'mlb_stats_api:team_assignment_sync:fullRoster'
        assert card['roster_status']['is_active_mlb'] is False
        assert card['visibility']['is_unavailable_roster_status'] is True
        assert card['visibility']['is_active_roster_option'] is False

    def test_current_assignment_without_roster_tier_blocks_stale_activated_label_on_board(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Valente Bellozo',
                team_id=115,
                team_abbr='COL',
                mlb_id=678129,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
                roster_status=STATUS_ACTIVE,
                roster_status_source='mlb_stats_api:transactions:activated',
                roster_status_updated_at=datetime(2026, 4, 1, 12, 0, 0),
                team_assignment_status=TEAM_ASSIGNMENT_ASSIGNED,
                team_assignment_source='mlb_stats_api:team_assignment_sync:people:currentTeam',
                team_assignment_updated_at=datetime(2026, 4, 13, 12, 0, 0),
            )

        default_body = client.get('/api/bullpen/teams/115/board').get_json()
        default_cards = [
            card
            for group in default_body['groups']
            for card in group['pitchers']
        ]

        assert default_cards == []
        assert default_body['total_pitchers'] == 0
        assert default_body['roster_status']['unknown_count'] == 1
        assert default_body['roster_status']['active_mlb_count'] == 0

        expanded_body = client.get('/api/bullpen/teams/115/board?include_stale=true').get_json()
        expanded_cards = [
            card
            for group in expanded_body['groups']
            for card in group['pitchers']
        ]

        assert expanded_cards == []
        assert expanded_body['roster_status']['unknown_count'] == 1
        assert expanded_body['roster_status']['active_mlb_count'] == 0

    def test_full_roster_sync_active_label_is_not_active_mlb_on_board(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Valente Bellozo',
                team_id=115,
                team_abbr='COL',
                mlb_id=678129,
                innings=[1.0, 0.2, 1.0],
                days_ago=[
                    ACTIVE_WINDOW_DAYS + 2,
                    ACTIVE_WINDOW_DAYS + 4,
                    ACTIVE_WINDOW_DAYS + 6,
                ],
                roster_status=STATUS_ACTIVE,
                roster_status_source='mlb_stats_api:roster_sync:fullRoster',
                roster_status_updated_at=datetime(2026, 4, 13, 12, 0, 0),
            )

        default_body = client.get('/api/bullpen/teams/115/board').get_json()
        default_cards = [
            card
            for group in default_body['groups']
            for card in group['pitchers']
        ]

        assert default_cards == []
        assert default_body['total_pitchers'] == 0
        assert default_body['roster_status']['active_mlb_count'] == 0
        assert default_body['roster_status']['excluded_inactive_count'] == 1

        expanded_body = client.get('/api/bullpen/teams/115/board?include_stale=true').get_json()
        expanded_cards = [
            card
            for group in expanded_body['groups']
            for card in group['pitchers']
        ]

        assert [card['name'] for card in expanded_cards] == ['Valente Bellozo']
        card = expanded_cards[0]
        assert card['availability_status'] == 'Unavailable'
        assert card['roster_status']['status'] == STATUS_MINORS
        assert card['roster_status']['label'] == 'Minors'
        assert card['roster_status']['source'] == 'mlb_stats_api:roster_sync:fullRoster'
        assert card['roster_status']['is_active_mlb'] is False
        assert card['visibility']['is_active_roster_option'] is False
        assert card['visibility']['is_visible_by_default'] is False
        assert card['visibility']['hidden_until_show_unavailable'] is True

    def test_inactive_toggle_shows_roster_status_context_not_available(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Graham Ashcraft',
                team_id=113,
                team_abbr='CIN',
                mlb_id=668933,
                innings=[1.0, 1.0, 0.2],
                days_ago=[1, 3, 5],
                roster_status=STATUS_IL_60,
            )
            _seed_pitcher(
                'Pierce Johnson',
                team_id=113,
                team_abbr='CIN',
                mlb_id=572955,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 2, 4],
                roster_status=STATUS_IL_15,
            )
            _seed_pitcher(
                'Jose Franco',
                team_id=113,
                team_abbr='CIN',
                mlb_id=683742,
                innings=[1.0, 1.0, 0.2],
                days_ago=[1, 3, 5],
                roster_status=STATUS_MINORS,
            )

        body = client.get('/api/bullpen/teams/113/board?include_stale=true').get_json()
        cards = [card for group in body['groups'] for card in group['pitchers']]
        by_name = {card['name']: card for card in cards}

        assert set(by_name) == {'Graham Ashcraft', 'Jose Franco', 'Pierce Johnson'}
        assert by_name['Graham Ashcraft']['availability_status'] == 'Unavailable'
        assert by_name['Graham Ashcraft']['roster_status']['status'] == STATUS_IL_60
        assert by_name['Graham Ashcraft']['roster_status']['label'] == 'IL-60'
        assert by_name['Pierce Johnson']['roster_status']['label'] == 'IL-15'
        assert by_name['Jose Franco']['roster_status']['label'] == 'Minors'
        assert all(card['availability_status'] != 'Available' for card in cards)
        assert body['roster_status']['inactive_context_count'] == 3
        assert any('not counted as active bullpen options' in limitation for limitation in body['limitations'])

    def test_unknown_roster_status_surfaces_limitation_without_claiming_active(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Unknown Status Reliever',
                team_id=113,
                team_abbr='CIN',
                mlb_id=11321,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
                roster_status=None,
            )

        body = client.get('/api/bullpen/teams/113/board').get_json()
        cards = [card for group in body['groups'] for card in group['pitchers']]

        assert cards == []
        assert body['total_pitchers'] == 0
        assert ROSTER_STATUS_UNAVAILABLE_LIMITATION in body['limitations']
        assert body['roster_status']['authority'] == 'unavailable'
        assert body['roster_status']['unknown_count'] == 1
        assert body['roster_status']['included_unknown_count'] == 0
        assert body['roster_status']['active_mlb_count'] == 0

    def test_pitcher_detail_endpoint_includes_roster_status_without_500(self, client):
        with client.application.app_context():
            pitcher = _seed_pitcher(
                'Detail Active Reliever',
                team_id=113,
                team_abbr='CIN',
                mlb_id=11322,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
                roster_status=STATUS_ACTIVE,
            )
            pitcher_id = pitcher.id

        response = client.get(f'/api/bullpen/fatigue/{pitcher_id}')
        body = response.get_json()

        assert response.status_code == 200
        assert body['pitcher']['id'] == pitcher_id
        assert body['roster_status']['status'] == STATUS_ACTIVE
        assert body['availability']['availability_status']

    def test_default_bullpen_filtering_is_league_wide_not_reds_only(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Yankees Starter',
                team_id=147,
                team_abbr='NYY',
                mlb_id=14701,
                innings=[6.0, 5.0, 4.2],
                days_ago=[1, 6, 11],
            )
            _seed_pitcher(
                'Yankees Reliever',
                team_id=147,
                team_abbr='NYY',
                mlb_id=14702,
                innings=[1.0, 1.0, 0.2],
                days_ago=[1, 3, 5],
                roster_status=STATUS_ACTIVE,
            )
            _seed_pitcher(
                'Yankees Optioned Reliever',
                team_id=147,
                team_abbr='NYY',
                mlb_id=14703,
                innings=[1.0, 1.0, 0.2],
                days_ago=[1, 3, 5],
                roster_status=STATUS_MINORS,
            )

        body = client.get('/api/bullpen/teams/147/board').get_json()
        names = [card['name'] for group in body['groups'] for card in group['pitchers']]

        assert names == ['Yankees Reliever']
        assert body['total_pitchers'] == 1

    def test_all_pitchers_team_overview_still_shows_broader_population(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Reds Overview Starter',
                team_id=113,
                team_abbr='CIN',
                mlb_id=11306,
                innings=[6.0, 5.0, 6.0],
                days_ago=[1, 6, 11],
            )
            _seed_pitcher(
                'Reds Overview Reliever',
                team_id=113,
                team_abbr='CIN',
                mlb_id=11307,
                innings=[1.0, 1.0, 0.2],
                days_ago=[1, 3, 5],
            )

        body = client.get('/api/bullpen/teams/113/bullpen?include_stale=true').get_json()
        names = [row['pitcher']['full_name'] for row in body]

        assert set(names) == {'Reds Overview Starter', 'Reds Overview Reliever'}

    def test_uncertain_bullpen_eligibility_is_limited_on_cards(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Limited Sample Reliever',
                team_id=113,
                team_abbr='CIN',
                mlb_id=11308,
                innings=[1.0],
                days_ago=[1],
            )

        body = client.get('/api/bullpen/teams/113/board').get_json()
        cards = [card for group in body['groups'] for card in group['pitchers']]

        assert [card['name'] for card in cards] == ['Limited Sample Reliever']
        assert cards[0]['eligibility']['confidence'] == 'low'
        assert any(
            'limited recent relief-length sample' in limitation
            for limitation in cards[0]['eligibility']['limitations']
        )
