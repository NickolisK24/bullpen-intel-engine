"""
Tests for Team Bullpen Comparison V1.

Two layers:
  * Pure comparison service (services/bullpen_comparison.py) — no DB/Flask.
  * GET /api/bullpen/teams/compare endpoint — in-memory SQLite, no MLB.

The comparison is descriptive: it names which bullpen currently has more of a
given availability group, keeps exact counts in structured fields, and renders
public copy in baseball language. It must never grade, rank, score, or recommend
a team, and it must be deterministic and self-explaining.
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots

import services.sync as sync_service
from services.bullpen_board import build_board_payload
from services.bullpen_comparison import build_team_comparison
from services.editorial_voice_contract_v1 import (
    contains_editorial_banned_language,
    raw_count_matches,
)
from services.roster_status import STATUS_ACTIVE
from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
import models.prospect  # noqa: F401
from api.bullpen import bullpen_bp


def board(team_name, abbr, cards_by_status, freshness=None):
    """Build a real board payload from simple status counts."""
    records = []
    pid = 1
    for status, count in cards_by_status.items():
        for _ in range(count):
            records.append({
                'name': f'{abbr}{pid}',
                'pitcher_id': pid,
                'fatigue_score': 20,
                'availability': {
                    'availability_status': status,
                    'confidence': 'high',
                    'data_state': 'fresh',
                    'reasons': [],
                    'limitations': [],
                },
            })
            pid += 1
    return build_board_payload(
        team={'team_id': abs_hash(abbr), 'team_name': team_name, 'team_abbreviation': abbr},
        records=records,
        freshness=freshness or {'is_current': True},
        generated_at='2026-06-05T00:00:00+00:00',
    )


def abs_hash(value):
    return abs(hash(value)) % 1000


def public_comparison_copy(comp):
    parts = [comp['summary']['statement']]
    parts.extend(comp['summary'].get('reasons') or [])
    for observation in comp['observations']:
        parts.append(observation['statement'])
        parts.extend(observation.get('reasons') or [])
    return [part for part in parts if part]


# ── Pure comparison service ────────────────────────────────────────────────

class TestObservations:
    def test_names_team_with_more_available(self):
        a = board('Aces', 'AAA', {'Available': 6, 'Monitor': 2, 'Avoid': 2})
        b = board('Bears', 'BBB', {'Available': 3, 'Monitor': 2, 'Avoid': 2})
        comp = build_team_comparison(a, b)
        available = next(o for o in comp['observations'] if o['dimension'] == 'available')
        assert available['leader'] == 'A'
        assert available['statement'].startswith(
            'Aces has the clearer late-inning coverage because '
        )
        assert 'Aces has six available arms' in available['statement']
        assert 'Bears has three available arms' in available['statement']
        assert 'That ' in available['statement']
        assert available['team_a_value'] == 6
        assert available['team_b_value'] == 3

    def test_transparency_reasons_keep_both_counts_in_baseball_language(self):
        a = board('Aces', 'AAA', {'Available': 6})
        b = board('Bears', 'BBB', {'Available': 3})
        comp = build_team_comparison(a, b)
        available = next(o for o in comp['observations'] if o['dimension'] == 'available')
        assert available['reasons'] == [
            'Aces has six available arms ready.',
            'Bears has three available arms ready.',
        ]
        assert available['team_a_value'] == 6
        assert available['team_b_value'] == 3
        assert raw_count_matches(' '.join(available['reasons'])) == []

    def test_restricted_dimension_combines_avoid_and_unavailable(self):
        a = board('Aces', 'AAA', {'Available': 5, 'Avoid': 1, 'Unavailable': 1})
        b = board('Bears', 'BBB', {'Available': 5, 'Avoid': 3, 'Unavailable': 2})
        comp = build_team_comparison(a, b)
        restricted = next(o for o in comp['observations'] if o['dimension'] == 'restricted')
        assert restricted['leader'] == 'B'  # Bears have 5 restricted vs 2
        assert restricted['statement'].startswith('Bears has less rested late-inning cover because ')
        assert 'Bears has five restricted arms' in restricted['statement']
        assert 'Aces has both restricted arms' in restricted['statement']
        assert restricted['team_a_value'] == 2
        assert restricted['team_b_value'] == 5

    def test_monitor_dimension_uses_workload_language_not_caution(self):
        a = board('Aces', 'AAA', {'Available': 5, 'Monitor': 3})
        b = board('Bears', 'BBB', {'Available': 5, 'Monitor': 1})
        comp = build_team_comparison(a, b)
        monitor = next(o for o in comp['observations'] if o['dimension'] == 'monitor')
        text = ' '.join(public_comparison_copy(comp)).lower()

        assert monitor['leader'] == 'A'
        assert 'carrying recent workload' in monitor['statement']
        assert 'fewer workload flags' in comp['summary']['statement']
        assert 'carrying caution' not in text

    def test_uses_neutral_language_no_grading_terms(self):
        a = board('Aces', 'AAA', {'Available': 6, 'Avoid': 1})
        b = board('Bears', 'BBB', {'Available': 3, 'Avoid': 4})
        comp = build_team_comparison(a, b)
        blob = ' '.join(o['statement'] for o in comp['observations']) + ' ' + comp['summary']['statement']
        for term in ('best', 'better', 'stronger', 'superior', 'recommend', 'win', 'grade', 'score'):
            assert term not in blob.lower(), term

    def test_compare_public_copy_passes_shared_banned_language_scan(self):
        a = board('Aces', 'AAA', {'Available': 6, 'Monitor': 1, 'Avoid': 1})
        b = board('Bears', 'BBB', {'Available': 3, 'Monitor': 2, 'Unavailable': 2})
        comp = build_team_comparison(a, b)

        for text in public_comparison_copy(comp):
            assert not contains_editorial_banned_language(text), text

    def test_raw_zero_counts_do_not_leak_into_public_copy(self):
        a = board('Aces', 'AAA', {'Avoid': 2})
        b = board('Bears', 'BBB', {'Available': 4})
        comp = build_team_comparison(a, b)
        copy = public_comparison_copy(comp)

        assert any('not one available arm' in text for text in copy)
        for text in copy:
            assert raw_count_matches(text) == [], text


class TestSummary:
    def test_tie_across_all_dimensions_reads_as_similar(self):
        a = board('Aces', 'AAA', {'Available': 4, 'Monitor': 2, 'Avoid': 1, 'Unavailable': 1})
        b = board('Bears', 'BBB', {'Available': 4, 'Monitor': 2, 'Avoid': 1, 'Unavailable': 1})
        comp = build_team_comparison(a, b)
        assert comp['summary']['state'] == 'similar'
        assert comp['summary']['statement'].startswith('The side-by-side bullpen read is even because ')
        assert 'availability distribution' not in comp['summary']['statement'].lower()
        assert all(o['leader'] == 'tie' for o in comp['observations'])

    def test_difference_reads_as_differ(self):
        a = board('Aces', 'AAA', {'Available': 6})
        b = board('Bears', 'BBB', {'Available': 2, 'Avoid': 4})
        comp = build_team_comparison(a, b)
        assert comp['summary']['state'] == 'differ'
        assert comp['summary']['statement'].startswith(
            'Aces has the clearer late-inning coverage because '
        )

    def test_both_empty_reads_as_no_data(self):
        a = board('Aces', 'AAA', {})
        b = board('Bears', 'BBB', {})
        comp = build_team_comparison(a, b)
        assert comp['summary']['state'] == 'no_data'
        assert 'not one current bullpen arm' in ' '.join(comp['summary']['reasons'])
        assert raw_count_matches(' '.join(public_comparison_copy(comp))) == []

    def test_tie_observation_shows_shared_count(self):
        a = board('Aces', 'AAA', {'Available': 4})
        b = board('Bears', 'BBB', {'Available': 4})
        comp = build_team_comparison(a, b)
        available = next(o for o in comp['observations'] if o['dimension'] == 'available')
        assert available['leader'] == 'tie'
        assert 'four available arms' in available['statement']
        assert raw_count_matches(available['statement']) == []


class TestFreshnessAndConfidence:
    def test_stale_team_degrades_overall_confidence(self):
        a = board('Aces', 'AAA', {'Available': 5}, freshness={'is_current': True})
        b = board('Bears', 'BBB', {'Available': 5}, freshness={'is_current': False})
        comp = build_team_comparison(a, b)
        assert comp['team_confidence']['team_a'] == 'high'
        assert comp['team_confidence']['team_b'] == 'low'
        assert comp['confidence'] == 'low'
        assert any('Bears' in limitation for limitation in comp['limitations'])

    def test_both_current_is_high_confidence(self):
        a = board('Aces', 'AAA', {'Available': 5})
        b = board('Bears', 'BBB', {'Available': 4})
        comp = build_team_comparison(a, b)
        assert comp['confidence'] == 'high'
        assert comp['limitations'] == []

    def test_governance_flags_are_false(self):
        a = board('Aces', 'AAA', {'Available': 5})
        b = board('Bears', 'BBB', {'Available': 4})
        comp = build_team_comparison(a, b)
        assert comp['ranking_applied'] is False
        assert comp['selection_made'] is False


# ── Endpoint integration ───────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')

    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')

    @app.before_request
    def _seed_ready_roster_snapshots_for_comparison_tests():
        seed_roster_readiness_snapshots()

    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _seed_pitcher(full_name, team_id, mlb_id, raw_score=10.0):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=full_name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        active=True,
        roster_status=STATUS_ACTIVE,
        roster_status_source='test_fixture',
        roster_status_updated_at=datetime.utcnow(),
    )
    db.session.add(pitcher)
    db.session.commit()
    today = date.today()
    db.session.add(GameLog(
        pitcher_id=pitcher.id, mlb_game_pk=mlb_id * 10,
        game_date=today - timedelta(days=1), pitches_thrown=12,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        games_started=0,
        game_type='R',
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id, raw_score=raw_score, risk_level='LOW',
        calculated_at=datetime.utcnow(),
    ))
    db.session.commit()
    return pitcher


class TestCompareEndpoint:
    def test_returns_two_boards_and_a_comparison(self, client):
        with client.application.app_context():
            _seed_pitcher('A One', team_id=1, mlb_id=1)
            _seed_pitcher('A Two', team_id=1, mlb_id=2)
            _seed_pitcher('B One', team_id=2, mlb_id=3)

        res = client.get('/api/bullpen/teams/compare?team_a=1&team_b=2')
        assert res.status_code == 200
        body = res.get_json()

        assert body['capability'] == 'team_bullpen_comparison'
        assert body['ranking_applied'] is False
        assert body['selection_made'] is False
        # Both full boards ride along for the UI to render below the comparison.
        assert body['team_a']['capability'] == 'tonights_bullpen_board'
        assert body['team_b']['capability'] == 'tonights_bullpen_board'
        # Snapshot counts come from the boards.
        assert body['comparison']['snapshot']['team_a']['total_relievers'] == 2
        assert body['comparison']['snapshot']['team_b']['total_relievers'] == 1
        assert len(body['comparison']['observations']) == 3

    def test_compare_embeds_the_same_public_role_read_as_the_team_board(self, client):
        # Compare renders the same board payloads; a guarded Limited Read card
        # must inherit the identical public role conclusion with no
        # independent role transformation.
        with client.application.app_context():
            pitcher = _seed_pitcher('Guard A', team_id=1, mlb_id=11)
            today = date.today()
            db.session.add(GameLog(
                pitcher_id=pitcher.id, mlb_game_pk=999901,
                game_date=today - timedelta(days=4), pitches_thrown=80,
                innings_pitched=5.0, innings_pitched_outs=15,
                games_started=1, game_type='R',
            ))
            db.session.add(GameLog(
                pitcher_id=pitcher.id, mlb_game_pk=999902,
                game_date=today - timedelta(days=9), pitches_thrown=80,
                innings_pitched=5.0, innings_pitched_outs=15,
                games_started=1, game_type='R',
            ))
            db.session.add(GameLog(
                pitcher_id=pitcher.id, mlb_game_pk=999903,
                game_date=today - timedelta(days=2), pitches_thrown=15,
                innings_pitched=1.0, innings_pitched_outs=3,
                games_started=0, game_type='R', save=True, save_situation=True,
            ))
            db.session.add(GameLog(
                pitcher_id=pitcher.id, mlb_game_pk=999904,
                game_date=today - timedelta(days=6), pitches_thrown=15,
                innings_pitched=1.0, innings_pitched_outs=3,
                games_started=0, game_type='R', hold=True,
            ))
            db.session.commit()
            _seed_pitcher('B One', team_id=2, mlb_id=12)

        board = client.get('/api/bullpen/teams/1/board').get_json()
        board_card = next(
            card for group in board['groups'] for card in group['pitchers']
            if card['name'] == 'Guard A'
        )
        compare = client.get('/api/bullpen/teams/compare?team_a=1&team_b=2').get_json()
        compare_card = next(
            card for group in compare['team_a']['groups'] for card in group['pitchers']
            if card['name'] == 'Guard A'
        )

        assert compare_card['public_role_read'] == board_card['public_role_read']
        assert compare_card['pitcher_labels']['role'] == board_card['pitcher_labels']['role']
        assert compare_card['public_role_read']['key'] == 'limited_read'
        assert compare_card['public_role_read']['headline'] == 'Limited Read'

    def test_missing_team_param_is_a_400(self, client):
        assert client.get('/api/bullpen/teams/compare?team_a=1').status_code == 400

    def test_no_team_grading_fields_leak(self, client):
        with client.application.app_context():
            _seed_pitcher('A One', team_id=1, mlb_id=1)
            _seed_pitcher('B One', team_id=2, mlb_id=2)
        comp = client.get('/api/bullpen/teams/compare?team_a=1&team_b=2').get_json()['comparison']
        for observation in comp['observations']:
            assert 'score' not in observation
            assert 'rank' not in observation
            assert observation['leader'] in ('A', 'B', 'tie')
