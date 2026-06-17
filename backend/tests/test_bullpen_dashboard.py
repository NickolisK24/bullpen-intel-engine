"""
Tests for the league-wide bullpen dashboard endpoint (GET /api/bullpen/dashboard).

It must reuse existing systems (availability summary, Team Context Layer, usage
roles) without ranking/selection, and stay resilient when empty.
"""

from datetime import date, datetime, timedelta
import json

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.sync as sync_service
from services.availability import ACTIVE_WINDOW_DAYS
from services.availability_population import CURRENT_AVAILABILITY_SCOPE, current_availability_records
from services.availability_snapshot import latest_fatigue_rows as availability_latest_fatigue_rows
from services.availability_summary import summarize_availability_records
from services.pitcher_role import ROLE_KEYS, ROLE_WINDOW_DAYS
from services.roster_status import STATUS_ACTIVE, STATUS_IL_15, STATUS_MINORS
from utils.db import db
from utils.innings import outs_to_decimal_innings, parse_mlb_innings_to_outs
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
import models.prospect  # noqa: F401
from api.bullpen import bullpen_bp


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _seed_pitcher(
    name, team_id, mlb_id, raw_score=10.0, innings=1.0, days_ago=1,
    roster_status=STATUS_ACTIVE, games_started=None, earned_runs=0,
):
    pitcher = Pitcher(mlb_id=mlb_id, full_name=name, team_id=team_id,
                      team_name=f'Team {team_id}', team_abbreviation=f'T{team_id}', active=True,
                      roster_status=roster_status,
                      roster_status_source='test_fixture' if roster_status else None,
                      roster_status_updated_at=datetime.utcnow() if roster_status else None)
    db.session.add(pitcher)
    db.session.commit()
    innings_values = innings if isinstance(innings, list) else [innings]
    day_values = days_ago if isinstance(days_ago, list) else list(range(days_ago, days_ago + len(innings_values)))
    games_started_values = (
        games_started if isinstance(games_started, list)
        else [games_started] * len(innings_values) if games_started is not None
        else None
    )
    earned_runs_values = (
        earned_runs if isinstance(earned_runs, list)
        else [earned_runs] * len(innings_values)
    )
    for idx, innings_pitched in enumerate(innings_values):
        innings_outs = parse_mlb_innings_to_outs(innings_pitched)
        start_flag = games_started_values[idx] if games_started_values is not None else (
            1 if innings_outs >= 9 else 0
        )
        db.session.add(GameLog(pitcher_id=pitcher.id, mlb_game_pk=mlb_id * 10 + idx,
                                game_date=date.today() - timedelta(days=day_values[idx]),
                                pitches_thrown=12,
                                innings_pitched=outs_to_decimal_innings(innings_outs),
                                innings_pitched_outs=innings_outs,
                                earned_runs=earned_runs_values[idx],
                                games_started=start_flag,
                                game_type='R'))
    db.session.add(FatigueScore(pitcher_id=pitcher.id, raw_score=raw_score,
                                risk_level='LOW', calculated_at=datetime.utcnow()))
    db.session.commit()
    return pitcher


def _landscape_entries_for_team(landscape, team_id):
    entries = []
    for key in ('constrained_bullpens', 'available_bullpens', 'monitoring_concentration'):
        entries.extend(
            entry for entry in landscape.get(key, [])
            if entry.get('team_id') == team_id
        )
    return entries


class TestDashboardEndpoint:
    def test_empty_system_returns_stable_shape(self, client):
        body = client.get('/api/bullpen/dashboard').get_json()
        assert body['capability'] == 'bullpen_dashboard'
        assert body['ranking_applied'] is False
        assert body['selection_made'] is False
        assert body['context']['health']['state'] == 'no_data'
        assert body['roles']['total'] == 0
        assert set(body['roles']['counts']) == set(ROLE_KEYS)

    def test_aggregates_context_and_roles_across_teams(self, client):
        with client.application.app_context():
            _seed_pitcher('A One', team_id=1, mlb_id=1)
            _seed_pitcher('A Two', team_id=1, mlb_id=2)
            _seed_pitcher('B One', team_id=2, mlb_id=3)

        body = client.get('/api/bullpen/dashboard').get_json()
        # League-wide context comes from the availability summary counts.
        assert body['context']['metrics']['total_relievers'] >= 1
        assert body['context']['health']['state'] in (
            'manageable', 'monitoring', 'elevated', 'constrained', 'no_data',
        )
        # Roles sum to the scored-pitcher set.
        assert body['roles']['total'] == sum(body['roles']['counts'].values())
        # Freshness/data-through is present for the hero.
        assert 'data_through' in body['freshness']

    def test_four_beat_story_path_defaults_on(self, client):
        body = client.get('/api/bullpen/dashboard').get_json()

        assert body['four_beat_stories']['capability'] == 'four_beat_story_template_v1'
        assert body['four_beat_stories']['enabled'] is True
        assert body['four_beat_stories']['ranking_applied'] is True
        assert body['four_beat_stories']['ranking_basis'] == 'story_strength'
        assert body['four_beat_stories']['items'] == []

    def test_four_beat_story_path_can_be_disabled(self, client):
        client.application.config['FOUR_BEAT_STORIES_ENABLED'] = False
        with client.application.app_context():
            _seed_pitcher('A One', team_id=1, mlb_id=101)

        body = client.get('/api/bullpen/dashboard').get_json()

        assert 'four_beat_stories' not in body

    def test_four_beat_story_path_includes_items_by_default(self, client):
        with client.application.app_context():
            for idx in range(6):
                _seed_pitcher(
                    f'Fresh Arm {idx}',
                    team_id=101,
                    mlb_id=10100 + idx,
                    raw_score=10,
                    innings=1.0,
                    days_ago=1,
                    roster_status=STATUS_ACTIVE,
                    games_started=0,
                )

        body = client.get('/api/bullpen/dashboard').get_json()

        assert body['four_beat_stories']['capability'] == 'four_beat_story_template_v1'
        assert body['four_beat_stories']['ranking_applied'] is True
        assert body['four_beat_stories']['ranking_basis'] == 'story_strength'
        assert body['four_beat_stories']['selection_made'] is False
        assert body['four_beat_stories']['items']
        assert 'season_era' not in body['four_beat_stories']
        assert all('computed' in item for item in body['four_beat_stories']['items'])

    def test_dashboard_surfaces_backend_authored_season_era(self, client):
        with client.application.app_context():
            starter_reliever = _seed_pitcher(
                'Mixed Role Arm',
                team_id=501,
                mlb_id=50101,
                innings=[1.0, 1.0],
                days_ago=[1, 2],
                games_started=[0, 1],
                earned_runs=[1, 2],
            )
            starter_reliever_id = starter_reliever.id
            _seed_pitcher(
                'Pure Relief Arm',
                team_id=501,
                mlb_id=50102,
                innings=1.0,
                days_ago=1,
                games_started=0,
                earned_runs=0,
            )

        body = client.get('/api/bullpen/dashboard').get_json()
        season_era = body['season_era']
        pitcher_line = next(
            item for item in season_era['pitchers']
            if item['pitcher_id'] == starter_reliever_id
        )
        bullpen_line = next(
            item for item in season_era['bullpens']
            if item['team_id'] == 501
        )

        assert season_era['capability'] == 'season_era_v1'
        assert pitcher_line['earned_runs'] == 3
        assert pitcher_line['innings_outs'] == 6
        assert pitcher_line['era'] == 13.5
        assert bullpen_line['earned_runs'] == 1
        assert bullpen_line['innings_outs'] == 6
        assert bullpen_line['era'] == 4.5

    def test_four_beat_story_and_board_share_clean_trust_authority(self, client):
        client.application.config['FOUR_BEAT_STORIES_ENABLED'] = True
        team_id = 116
        with client.application.app_context():
            jansen = _seed_pitcher(
                'Kenley Jansen',
                team_id=team_id,
                mlb_id=11601,
                raw_score=10,
                innings=[1.0, 1.0, 1.0],
                days_ago=[2, 20, 31],
                roster_status=STATUS_ACTIVE,
                games_started=[0, 0, 0],
            )
            older_log = (
                GameLog.query
                .filter_by(pitcher_id=jansen.id)
                .order_by(GameLog.game_date.asc())
                .first()
            )
            older_log.save = True
            older_log.save_situation = True

            for idx in range(5):
                _seed_pitcher(
                    f'Detroit Clean Arm {idx}',
                    team_id=team_id,
                    mlb_id=11610 + idx,
                    raw_score=10,
                    innings=1.0,
                    days_ago=2,
                    roster_status=STATUS_ACTIVE,
                    games_started=0,
                )
            db.session.commit()

        dashboard = client.get('/api/bullpen/dashboard').get_json()
        story = next(
            item for item in dashboard['four_beat_stories']['items']
            if item['team_id'] == team_id
        )
        board = client.get(f'/api/bullpen/teams/{team_id}/board').get_json()
        board_clean_trust_names = [
            card['name']
            for group in board['groups']
            for card in group['pitchers']
            if (card['pitcher_labels']['read']['key'] == 'clean_option'
                and card['pitcher_labels']['role']['key'] == 'trust_arm')
        ]
        implication = next(
            beat for beat in story['beats']
            if beat['key'] == 'implication'
        )

        assert story['rule_key'] == 'pressure_distribution'
        assert story['computed']['clean_trust_count'] == 1
        assert board_clean_trust_names == ['Kenley Jansen']
        assert implication['slots']['clean_trust_names'] == 'Kenley Jansen'
        assert story['computed']['clean_trust_count'] == len(board_clean_trust_names)

    def test_no_governance_or_ranking_fields_leak(self, client):
        with client.application.app_context():
            _seed_pitcher('Solo', team_id=1, mlb_id=1)
        body = client.get('/api/bullpen/dashboard').get_json()
        assert 'ranking_applied' not in body['context']
        assert 'selection_made' not in body['context']
        assert body['availability_summary']['total_pitchers'] >= 0

    def test_dashboard_counts_exclude_clear_starters_league_wide(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'League Starter',
                team_id=1,
                mlb_id=10,
                innings=[6.0, 5.1, 6.0],
                days_ago=[1, 6, 11],
            )
            _seed_pitcher(
                'League Reliever',
                team_id=2,
                mlb_id=11,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
                roster_status=STATUS_ACTIVE,
            )

        body = client.get('/api/bullpen/dashboard').get_json()

        assert body['context']['metrics']['total_relievers'] == 1
        assert body['roles']['total'] == 1
        assert body['availability_summary']['total_pitchers'] == 1
        assert body['landscape']['teams_evaluated'] == 1

    def test_current_availability_summary_uses_governed_authority(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Governed Starter',
                team_id=1,
                mlb_id=12,
                innings=[6.0, 5.1, 6.0],
                days_ago=[1, 6, 11],
                games_started=[1, 1, 1],
            )
            _seed_pitcher(
                'Governed Reliever',
                team_id=2,
                mlb_id=13,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
                games_started=[0, 0, 0],
            )
            authority_records = current_availability_records(
                availability_latest_fatigue_rows(),
                reference_date=date.today(),
            )
            authority_summary = summarize_availability_records(authority_records)

        dashboard = client.get('/api/bullpen/dashboard').get_json()
        overview = client.get('/api/bullpen/stats/overview').get_json()

        assert dashboard['scope'] == CURRENT_AVAILABILITY_SCOPE
        assert dashboard['availability_summary']['is_current_availability'] is True
        assert dashboard['availability_summary']['total_pitchers'] == authority_summary['total_pitchers']
        assert dashboard['availability_summary']['statuses'] == authority_summary['statuses']
        assert dashboard['availability_summary']['total_pitchers'] == 1

        assert 'availability_summary' not in overview
        inventory = overview['scored_pitcher_inventory']
        assert inventory['mode'] == 'scored_pitcher_inventory'
        assert inventory['is_current_availability'] is False
        assert inventory['total_pitchers'] == 2

    def test_dashboard_counts_exclude_known_inactive_roster_statuses(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Active League Reliever',
                team_id=1,
                mlb_id=20,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
                roster_status=STATUS_ACTIVE,
            )
            _seed_pitcher(
                'IL League Reliever',
                team_id=1,
                mlb_id=21,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
                roster_status=STATUS_IL_15,
            )
            _seed_pitcher(
                'Minors League Reliever',
                team_id=1,
                mlb_id=22,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
                roster_status=STATUS_MINORS,
            )
            _seed_pitcher(
                'Stale IL League Reliever',
                team_id=1,
                mlb_id=23,
                innings=[1.0, 0.2, 1.0],
                days_ago=[ROLE_WINDOW_DAYS + 5, ROLE_WINDOW_DAYS + 7, ROLE_WINDOW_DAYS + 9],
                roster_status=STATUS_IL_15,
            )

        body = client.get('/api/bullpen/dashboard').get_json()

        assert body['context']['metrics']['total_relievers'] == 1
        assert body['roles']['total'] == 1
        assert body['availability_summary']['total_pitchers'] == 1
        assert body['landscape']['teams_evaluated'] == 1
        assert body['injury_il_context']['capability'] == 'injury_il_context_v1'
        assert body['injury_il_context']['ranking_applied'] is False
        assert body['injury_il_context']['prediction_applied'] is False
        assert body['injury_il_context']['league']['injured_list_count'] == 1
        assert body['injury_il_context']['league']['inactive_count'] == 1
        assert body['injury_il_context']['league']['teams_with_multiple_unavailable'] == 1
        assert body['injury_il_context']['league']['population_scope'] == 'dashboard_bullpen_population'
        assert body['injury_il_context']['league']['tracked_pitchers_count'] == body['availability_summary']['total_pitchers']
        assert body['injury_il_context']['league']['bullpen_population_count'] == body['availability_summary']['total_pitchers']

    def test_dashboard_counts_match_default_board_visible_population_for_rays_regression(self, client):
        with client.application.app_context():
            for idx in range(5):
                _seed_pitcher(
                    f'Tampa Available Arm {idx}',
                    team_id=139,
                    mlb_id=139100 + idx,
                    raw_score=10,
                    innings=[1.0, 0.2, 1.0],
                    days_ago=[6, 8, 10],
                    roster_status=STATUS_ACTIVE,
                )
            for idx in range(4):
                _seed_pitcher(
                    f'Tampa Monitor Arm {idx}',
                    team_id=139,
                    mlb_id=139200 + idx,
                    raw_score=45,
                    innings=[1.0, 0.2, 1.0],
                    days_ago=[6, 8, 10],
                    roster_status=STATUS_ACTIVE,
                )
            _seed_pitcher(
                'Nick Martinez',
                team_id=139,
                mlb_id=607259,
                raw_score=10,
                innings=[1.0, 0.2, 1.0],
                days_ago=[ACTIVE_WINDOW_DAYS + 2, ACTIVE_WINDOW_DAYS + 4, ACTIVE_WINDOW_DAYS + 6],
                roster_status=STATUS_ACTIVE,
            )

        default_board = client.get('/api/bullpen/teams/139/board').get_json()
        default_names = [
            card['name']
            for group in default_board['groups']
            for card in group['pitchers']
        ]
        expanded_board = client.get('/api/bullpen/teams/139/board?include_stale=true').get_json()
        expanded_names = [
            card['name']
            for group in expanded_board['groups']
            for card in group['pitchers']
        ]
        dashboard = client.get('/api/bullpen/dashboard').get_json()
        landscape_entries = _landscape_entries_for_team(dashboard['landscape'], 139)

        assert 'Nick Martinez' in default_names
        assert 'Nick Martinez' in expanded_names
        assert default_board['total_pitchers'] == 10
        assert expanded_board['total_pitchers'] == 10
        assert default_board['visibility']['hidden_but_available_count'] == 0
        assert expanded_board['visibility']['hidden_but_available_count'] == 0
        assert default_board['visibility']['active_hidden_count'] == 0
        assert expanded_board['visibility']['active_hidden_count'] == 0

        assert dashboard['context']['metrics']['total_relievers'] == 10
        assert dashboard['availability_summary']['total_pitchers'] == 10
        assert dashboard['availability_summary']['statuses']['Available'] == 5
        assert dashboard['availability_summary']['statuses']['Monitor'] == 5
        assert dashboard['roles']['total'] == 10
        assert dashboard['landscape']['teams_evaluated'] == 1
        assert landscape_entries
        assert all(entry['total_relievers'] == 10 for entry in landscape_entries)
        assert all(entry['available'] == 5 for entry in landscape_entries)
        assert all(entry['monitor'] == 5 for entry in landscape_entries)

    def test_dashboard_attaches_story_continuity_for_landscape_teams_only(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Core One',
                team_id=77,
                mlb_id=7701,
                raw_score=50,
                innings=[1.0, 1.0, 1.0, 1.0],
                days_ago=[1, 2, 4, 6],
                roster_status=STATUS_ACTIVE,
            )
            _seed_pitcher(
                'Core Two',
                team_id=77,
                mlb_id=7702,
                raw_score=50,
                innings=[1.0, 1.0, 1.0],
                days_ago=[1, 3, 5],
                roster_status=STATUS_ACTIVE,
            )
            _seed_pitcher(
                'Depth Arm',
                team_id=77,
                mlb_id=7703,
                raw_score=10,
                innings=[1.0],
                days_ago=[8],
                roster_status=STATUS_ACTIVE,
            )
            # Historical workload exists, but this team has no scored current
            # bullpen entry and should not be computed for dashboard continuity.
            db.session.add(Pitcher(
                mlb_id=8801,
                full_name='Unsurfaced Arm',
                team_id=88,
                team_name='Team 88',
                team_abbreviation='T88',
                active=True,
            ))
            db.session.commit()

        body = client.get('/api/bullpen/dashboard').get_json()

        assert body['continuity']['capability'] == 'bullpen_continuity_v1'
        assert set(body['continuity']['teams']) == {'77'}
        team = body['continuity']['teams']['77']
        assert team['continuity']['type'] == 'workload_concentration'
        assert team['by_type']['workload_concentration']['continuity_note']
        assert 'Narrative Memory' not in json.dumps(body['continuity'])
