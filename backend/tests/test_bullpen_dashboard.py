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
import services.sync_metadata as sync_metadata
from services.availability import ACTIVE_WINDOW_DAYS
from services.availability_population import CURRENT_AVAILABILITY_SCOPE, current_availability_records
from services.availability_snapshot import latest_fatigue_rows as availability_latest_fatigue_rows
from services.availability_summary import summarize_availability_records
from services.pitcher_role import ROLE_KEYS, ROLE_WINDOW_DAYS
from services.bullpen_stability import (
    CAPABILITY as STABILITY_CAPABILITY,
    CURRENT_ASSIGNMENT_LIMITATION as STABILITY_CURRENT_ASSIGNMENT_LIMITATION,
    SMALL_DENOMINATOR_CHURN_LIMITATION as STABILITY_SMALL_DENOMINATOR_CHURN_LIMITATION,
)
from services.rotation_support_pressure import LIMITED_SAMPLE_LIMITATION as ROTATION_LIMITED_SAMPLE_LIMITATION
from services.roster_status import STATUS_ACTIVE, STATUS_IL_15, STATUS_MINORS
from utils.db import db
from utils.innings import outs_to_decimal_innings, parse_mlb_innings_to_outs
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
import models.prospect  # noqa: F401
import api.bullpen as bullpen_api
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
    reference_date=None,
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
    seed_reference_date = reference_date or date.today()
    for idx, innings_pitched in enumerate(innings_values):
        innings_outs = parse_mlb_innings_to_outs(innings_pitched)
        start_flag = games_started_values[idx] if games_started_values is not None else (
            1 if innings_outs >= 9 else 0
        )
        db.session.add(GameLog(pitcher_id=pitcher.id, mlb_game_pk=mlb_id * 10 + idx,
                                game_date=seed_reference_date - timedelta(days=day_values[idx]),
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
        assert body['role_change_detection']['capability'] == 'bullpen_role_change_detection_v1'
        assert body['role_change_detection']['status'] == 'unavailable'
        assert body['role_change_detection']['ranking_applied'] is False
        assert body['role_change_detection']['selection_made'] is False

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

    def test_dashboard_includes_canonical_stories_and_keeps_legacy(self, client, monkeypatch):
        # Canonical contract keys every story item must carry.
        required_keys = {
            'story_id', 'team_id', 'team_name', 'date', 'story_available',
            'suppression_reason', 'story_type', 'category', 'tone', 'headline',
            'narrative', 'beats', 'evidence', 'freshness', 'trust_metadata',
            'limitations', 'share_ready', 'share_title', 'share_summary',
            'source_engine', 'quality_status',
        }

        def fake_story_builder(team_id, as_of_date=None):
            if team_id == 1:
                return {
                    'team_id': 1, 'team_name': 'Team 1', 'team_abbreviation': 'T1',
                    'as_of_date': '2026-06-22',
                    'story_available': True,
                    'story_type': 'coverage_pressure',
                    'story_type_label': 'Coverage Pressure',
                    'selected_observation': {'type': 'rotation_pressure', 'severity': 'high'},
                    'construction_frame': {'observation_type': 'rotation_pressure'},
                    'public_story_beat': {
                        'story_type': 'coverage_pressure',
                        'story_type_label': 'Coverage Pressure',
                    },
                    'written_story': {
                        'headline': 'Team 1 leans on its setup arms',
                        'observation_paragraph': 'Observation text.',
                        'baseline_paragraph': 'Baseline text.',
                        'cause_paragraph': 'Cause text.',
                        'constraint_paragraph': 'Constraint text.',
                    },
                    'freshness': {'data_through': '2026-06-21'},
                    'trust_metadata': {'external_generation_used': False},
                    'limitations': [],
                }
            return {
                'team_id': team_id, 'team_name': f'Team {team_id}',
                'team_abbreviation': f'T{team_id}',
                'as_of_date': '2026-06-22',
                'story_available': False,
                'neutral_reason': 'no_story_observations',
                'freshness': {}, 'trust_metadata': {}, 'limitations': [],
            }

        monkeypatch.setattr(bullpen_api, 'build_story_intelligence_team_story', fake_story_builder)
        monkeypatch.setattr(
            bullpen_api,
            '_canonical_story_team_descriptors',
            lambda landscape: [
                {'team_id': 1, 'team_name': 'Team 1', 'team_abbreviation': 'T1'},
                {'team_id': 2, 'team_name': 'Team 2', 'team_abbreviation': 'T2'},
            ],
        )
        with client.application.app_context():
            _seed_pitcher('A One', team_id=1, mlb_id=7001)

        body = client.get('/api/bullpen/dashboard').get_json()

        # Canonical feed is present and shaped.
        stories = body['stories']
        assert stories['capability'] == 'baseballos_canonical_story_v1'
        assert stories['source_engine'] == 'story_intelligence_service_v1'
        assert stories['available_count'] == 1
        assert stories['suppressed_count'] == 1
        assert stories['suppression_reasons'] == {'no_story_observations': 1}
        assert len(stories['items']) == 2
        for item in stories['items']:
            assert required_keys.issubset(item.keys())

        # Available story first, with mapped content and a stable team+date id.
        available = stories['items'][0]
        assert available['team_id'] == 1
        assert available['story_available'] is True
        assert available['headline'] == 'Team 1 leans on its setup arms'
        assert available['narrative'].startswith('Observation text.')
        assert available['tone'] == 'stress'
        assert available['category'] == 'stressed'
        assert available['quality_status'] == 'published'
        assert available['story_id'] == f"1:{available['date']}"

        # Suppressed team carries a reason and no fabricated story.
        suppressed = stories['items'][1]
        assert suppressed['team_id'] == 2
        assert suppressed['story_available'] is False
        assert suppressed['suppression_reason'] == 'no_story_observations'
        assert suppressed['quality_status'] == 'suppressed'
        assert suppressed['headline'] is None

        # League context (quiet-day strategy) is present and quality-gated.
        league = stories['league_context']
        assert league['capability'] == 'baseballos_league_context_v1'
        assert league['mode']
        assert league['day_class']
        assert league['quality_status'] in ('published', 'neutral')
        assert league['continuity']['state'] in ('new', 'unchanged', 'changed')

        # Continuity metadata is present on every canonical item.
        for item in stories['items']:
            assert 'continuity' in item
            assert item['continuity']['state']

        # The legacy four-beat, story-context, and top-level continuity payloads
        # are all retired from the product dashboard payload (Phases 5E-5F). The
        # canonical per-story continuity asserted above is unaffected.
        assert 'four_beat_stories' not in body
        assert 'story_context' not in body
        assert 'continuity' not in body
        assert 'story_continuity' not in body
        # Governance posture unchanged.
        assert body['ranking_applied'] is False
        assert body['selection_made'] is False

    def test_dashboard_surfaces_public_what_changed_payload(self, client, monkeypatch):
        public_payload = {
            'capability': 'what_changed_since_yesterday_public_v1',
            'ranking_applied': False,
            'selection_made': False,
            'prediction_applied': False,
            'ordering_basis': 'team_abbreviation_then_team_name',
            'item_limit': 30,
            'comparison': {
                'current_data_through': '2026-06-19',
                'previous_data_through': '2026-06-18',
                'comparison_available': True,
            },
            'items': [
                {
                    'key': 'T1-what-changed',
                    'team_id': 1,
                    'team_name': 'Team 1',
                    'team_abbreviation': 'T1',
                    'public_headline': 'Team 1 bullpen moved from 2 to 5 rested relievers.',
                    'public_summary': 'Team 1 has 3 more rested relievers than it had yesterday.',
                    'public_context': 'The bullpen has more rested relievers than it had yesterday, creating more room for tonight.',
                    'yesterday_rested_count': 2,
                    'today_rested_count': 5,
                    'workload_added': [],
                },
            ],
            'item_count': 1,
            'limitations': [],
        }
        monkeypatch.setattr(
            bullpen_api,
            'build_what_changed_public_payload',
            lambda current, prior, **kwargs: public_payload,
        )
        with client.application.app_context():
            _seed_pitcher('A One', team_id=1, mlb_id=1001)

        body = client.get('/api/bullpen/dashboard').get_json()
        changes = body['what_changed_since_yesterday']
        encoded = json.dumps(changes).lower()

        assert changes == public_payload
        assert changes['capability'] == 'what_changed_since_yesterday_public_v1'
        assert changes['item_limit'] == 30
        for forbidden in (
            'change_type',
            'confidence',
            'supporting_facts',
            'copy_review_flags',
            'public_copy_generated',
            'identity_label',
            'score',
            'recommend',
            'prediction language',
            'ranking language',
        ):
            assert forbidden not in encoded

    def test_dashboard_surfaces_withheld_what_changed_reason_codes(self, client, monkeypatch):
        public_payload = {
            'capability': 'what_changed_since_yesterday_public_v1',
            'state': 'insufficient_context',
            'ranking_applied': False,
            'selection_made': False,
            'prediction_applied': False,
            'ordering_basis': 'team_abbreviation_then_team_name',
            'item_limit': 30,
            'comparison': {
                'current_data_through': '2026-06-19',
                'previous_data_through': '2026-06-18',
                'comparison_available': False,
                'reason_codes': [
                    'prior_slate_coverage_missing',
                    'comparison_withheld',
                ],
            },
            'items': [],
            'item_count': 0,
            'limitations': [
                'Prior snapshot does not include slate coverage metadata.',
            ],
            'reason_codes': [
                'prior_slate_coverage_missing',
                'comparison_withheld',
            ],
        }
        calls = {}

        def fake_public_payload(current, prior, **kwargs):
            calls['kwargs'] = kwargs
            return public_payload

        monkeypatch.setattr(
            bullpen_api,
            'build_what_changed_public_payload',
            fake_public_payload,
        )
        with client.application.app_context():
            _seed_pitcher('A One', team_id=1, mlb_id=1001)

        body = client.get('/api/bullpen/dashboard').get_json()
        changes = body['what_changed_since_yesterday']

        assert changes == public_payload
        assert calls['kwargs']['require_trusted_snapshots'] is True
        assert calls['kwargs']['current_snapshot_metadata']['trusted_current_payload'] is True

    def test_dashboard_surfaces_quiet_what_changed_contract(self, client, monkeypatch):
        public_payload = {
            'capability': 'what_changed_since_yesterday_public_v1',
            'state': 'no_meaningful_changes',
            'ranking_applied': False,
            'selection_made': False,
            'prediction_applied': False,
            'ordering_basis': 'team_abbreviation_then_team_name',
            'item_limit': 30,
            'comparison': {
                'current_data_through': '2026-06-19',
                'previous_data_through': '2026-06-18',
                'comparison_available': True,
                'reason_codes': [],
            },
            'items': [],
            'item_count': 0,
            'limitations': [],
            'reason_codes': [],
        }

        monkeypatch.setattr(
            bullpen_api,
            'build_what_changed_public_payload',
            lambda current, prior, **kwargs: public_payload,
        )
        with client.application.app_context():
            _seed_pitcher('A One', team_id=1, mlb_id=1001)

        body = client.get('/api/bullpen/dashboard').get_json()

        assert body['what_changed_since_yesterday'] == public_payload

    def test_dashboard_what_changed_workload_payload_lists_top_relief_pitch_counts(self, client):
        current = date.today()
        prior = current - timedelta(days=1)
        team_id = 7

        with client.application.app_context():
            seeded = [
                _seed_pitcher('Relief A', team_id=team_id, mlb_id=7001, days_ago=0, games_started=0),
                _seed_pitcher('Relief B', team_id=team_id, mlb_id=7002, days_ago=0, games_started=0),
                _seed_pitcher('Relief C', team_id=team_id, mlb_id=7003, days_ago=0, games_started=0),
                _seed_pitcher('Relief D', team_id=team_id, mlb_id=7004, days_ago=0, games_started=0),
                _seed_pitcher('Starter A', team_id=team_id, mlb_id=7005, days_ago=0, games_started=1),
                _seed_pitcher('Low Pitch Relief', team_id=team_id, mlb_id=7006, days_ago=0, games_started=0),
            ]
            pitch_counts = {
                'Relief A': 22,
                'Relief B': 31,
                'Relief C': 18,
                'Relief D': 27,
                'Starter A': 48,
                'Low Pitch Relief': 14,
            }
            for pitcher in seeded:
                log = GameLog.query.filter_by(pitcher_id=pitcher.id).one()
                log.game_date = current
                log.pitches_thrown = pitch_counts[pitcher.full_name]
            db.session.commit()

            payload = bullpen_api._dashboard_what_changed_workload_payload(
                current,
                prior,
                [{'pitcher': pitcher} for pitcher in seeded],
            )

        team_payload = payload['by_team_id'][str(team_id)]

        assert payload['meaningful_pitch_minimum'] == 15
        assert payload['item_limit'] == 3
        assert team_payload['workload_added'] == [
            {'pitcher_id': seeded[1].id, 'name': 'Relief B', 'pitches': 31},
            {'pitcher_id': seeded[3].id, 'name': 'Relief D', 'pitches': 27},
            {'pitcher_id': seeded[0].id, 'name': 'Relief A', 'pitches': 22},
        ]
        assert 'Starter A' not in json.dumps(team_payload)
        assert 'Low Pitch Relief' not in json.dumps(team_payload)

    def test_dashboard_does_not_emit_four_beat_stories(self, client):
        # The legacy four-beat feed was retired from the product dashboard
        # payload in Phase 5E; it is no longer emitted regardless of seeding.
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

        assert 'four_beat_stories' not in body

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

    def test_no_governance_or_ranking_fields_leak(self, client):
        with client.application.app_context():
            _seed_pitcher('Solo', team_id=1, mlb_id=1)
        body = client.get('/api/bullpen/dashboard').get_json()
        assert 'ranking_applied' not in body['context']
        assert 'selection_made' not in body['context']
        assert body['availability_summary']['total_pitchers'] >= 0

    def test_dashboard_attaches_league_workload_concentration_baselines(self, client):
        # Teams with recent relief workload feed a league distribution sample.
        # Baselines are backend infrastructure only — no UI or story consumes them.
        with client.application.app_context():
            for team_id, base in ((301, 30100), (302, 30200)):
                for idx in range(4):
                    _seed_pitcher(
                        f'Reliever {team_id}-{idx}',
                        team_id=team_id,
                        mlb_id=base + idx,
                        innings=1.0,
                        days_ago=1,
                        roster_status=STATUS_ACTIVE,
                        games_started=0,
                    )

        body = client.get('/api/bullpen/dashboard').get_json()

        baselines = body['baselines']
        assert baselines['capability'] == 'baseline_distribution_v1'
        family = baselines['families']['workload_concentration']
        assert family['metric_family'] == 'workload_concentration'
        assert family['window_days'] == 7
        assert family['sample_count'] >= 1
        for metric_key in ('top_share', 'top_one_share'):
            dist = family['metrics'][metric_key]
            assert dist['sample_count'] == family['sample_count']
            assert dist['mean'] is not None
            assert dist['median'] is not None
            for percentile in ('p10', 'p25', 'p75', 'p90'):
                assert percentile in dist
        # Infrastructure only: the baseline block leaks no ranking/selection.
        assert 'ranking_applied' not in baselines
        assert 'selection_made' not in baselines

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

    def test_current_availability_summary_uses_governed_authority(self, client, monkeypatch):
        reference_date = date(2026, 6, 24)
        monkeypatch.setattr(bullpen_api, 'product_current_date', lambda: reference_date)
        monkeypatch.setattr(sync_metadata, 'product_current_date', lambda: reference_date)

        with client.application.app_context():
            _seed_pitcher(
                'Governed Starter',
                team_id=1,
                mlb_id=12,
                innings=[6.0, 5.1, 6.0],
                days_ago=[1, 6, 11],
                games_started=[1, 1, 1],
                reference_date=reference_date,
            )
            _seed_pitcher(
                'Governed Reliever',
                team_id=2,
                mlb_id=13,
                innings=[1.0, 0.2, 1.0],
                days_ago=[1, 3, 5],
                games_started=[0, 0, 0],
                reference_date=reference_date,
            )
            authority_records = current_availability_records(
                availability_latest_fatigue_rows(),
                reference_date=reference_date,
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
        capacity = body['capacity_intelligence']['by_team_id']['1']['capacity_loss']
        resource_health = body['capacity_intelligence']['by_team_id']['1']['resource_health']
        trust_hierarchy = body['capacity_intelligence']['by_team_id']['1']['trust_hierarchy']
        assert body['capacity_intelligence']['capability'] == 'league_bullpen_capacity_intelligence_v1'
        assert capacity['total_bullpen_pitcher_count'] == 4
        assert capacity['unavailable_pitcher_count'] == 3
        assert capacity['inactive_roster_unavailable_pitcher_count'] == 3
        assert capacity['unavailable_capacity_pct'] == 75
        assert resource_health['capacity_state'] == 'depleted'
        assert resource_health['resource_health_state'] == 'depleted'
        assert resource_health['bullpen_capacity']['capacity_state'] == 'depleted'
        assert resource_health['organizational_resource_health']['resource_health_state'] == 'depleted'
        assert resource_health['active_reliever_count'] == 1
        assert resource_health['injured_reliever_count'] == 2
        assert resource_health['unavailable_reliever_count'] == 1
        assert resource_health['total_bullpen_resource_count'] == 4
        assert resource_health['resource_availability_ratio'] == 0.25
        assert trust_hierarchy['capability'] == 'bullpen_trust_hierarchy_v1'
        assert sum(trust_hierarchy['bucket_counts'].values()) == 4
        assert trust_hierarchy['unknown_count'] >= 3
        assert trust_hierarchy['ranking_applied'] is False
        assert trust_hierarchy['selection_made'] is False
        assert trust_hierarchy['prediction_applied'] is False
        assert 'pitchers' not in trust_hierarchy

    def test_dashboard_exposes_rotation_support_pressure_payload(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Dashboard Rotation Starter',
                team_id=177,
                mlb_id=17701,
                innings=[8.0],
                days_ago=[1],
                roster_status=STATUS_ACTIVE,
                games_started=[1],
            )

        body = client.get('/api/bullpen/dashboard').get_json()
        pressure = body['rotation_support_pressure']['by_team_id']['177']

        assert body['rotation_support_pressure']['capability'] == 'league_rotation_support_pressure_v1'
        assert pressure['capability'] == 'rotation_support_pressure_v1'
        assert pressure['team_id'] == 177
        assert pressure['games_analyzed'] == 1
        assert pressure['starter_outs'] == 24
        assert pressure['bullpen_outs_required'] == 0
        assert pressure['status'] == 'limited_read'
        assert ROTATION_LIMITED_SAMPLE_LIMITATION in pressure['limitations']

    def test_dashboard_exposes_bullpen_stability_payload(self, client):
        with client.application.app_context():
            _seed_pitcher(
                'Dashboard Stable Arm One',
                team_id=178,
                mlb_id=17801,
                innings=[1.0, 1.0],
                days_ago=[8, 2],
                roster_status=STATUS_ACTIVE,
                games_started=[0, 0],
            )
            _seed_pitcher(
                'Dashboard Stable Arm Two',
                team_id=178,
                mlb_id=17802,
                innings=[1.0, 1.0],
                days_ago=[7, 1],
                roster_status=STATUS_ACTIVE,
                games_started=[0, 0],
            )
            _seed_pitcher(
                'Dashboard New Arm',
                team_id=178,
                mlb_id=17803,
                innings=[1.0],
                days_ago=[1],
                roster_status=STATUS_ACTIVE,
                games_started=[0],
            )

        body = client.get('/api/bullpen/dashboard').get_json()
        stability = body['bullpen_stability']['by_team_id']['178']

        assert body['bullpen_stability']['capability'] == 'league_bullpen_stability_v1'
        assert stability['capability'] == STABILITY_CAPABILITY
        assert stability['team_id'] == 178
        assert stability['recently_used_bullpen_count'] == 3
        assert stability['stable_core_count'] == 2
        assert stability['new_or_reintroduced_arm_count'] == 1
        assert stability['status'] == 'stable'
        assert STABILITY_CURRENT_ASSIGNMENT_LIMITATION in stability['source_limitations']
        assert STABILITY_SMALL_DENOMINATOR_CHURN_LIMITATION in stability['limitations']
        assert stability['source'] == 'backend'

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
