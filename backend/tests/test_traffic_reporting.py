from datetime import datetime, timezone
from types import SimpleNamespace
import uuid

from flask import Flask
import pytest

from api.traffic import traffic_bp
from models.traffic_internal_visitor import TrafficInternalVisitor
from models.traffic_page_view import TrafficPageView
from services.traffic_reporting import build_traffic_summary
from utils.db import db


NOW = datetime(2026, 7, 14, 16, 0, tzinfo=timezone.utc)


@pytest.fixture
def reporting_app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TRAFFIC_INTERNAL_EMAILS='founder@example.com',
    )
    db.init_app(app)
    app.register_blueprint(traffic_bp, url_prefix='/api/traffic')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def add_view(occurred_at, visitor, session, *, surface='today', **values):
    row = TrafficPageView(
        view_id=str(uuid.uuid4()),
        visitor_id=visitor,
        session_id=session,
        occurred_at=occurred_at,
        route='/bullpen' if surface in {'bullpen_board', 'compare_bullpens', 'all_pitchers'} else '/',
        surface=surface,
        site_host=values.pop('site_host', 'baseballos.app'),
        device_class=values.pop('device_class', 'desktop'),
        is_bot=values.pop('is_bot', False),
        schema_version=1,
        created_at=occurred_at,
        **values,
    )
    db.session.add(row)
    return row


def seed_complete_report():
    add_view(datetime(2026, 7, 1, 15, 0), 'visitor-return', 'baseline-session')
    add_view(datetime(2026, 7, 3, 12, 0), 'visitor-prior', 'prior-session', surface='dashboard')
    add_view(
        datetime(2026, 7, 8, 12, 0), 'visitor-return', 'return-session',
        surface='dashboard', referrer_domain='example.com',
    )
    add_view(
        datetime(2026, 7, 8, 13, 0), 'visitor-return', 'return-session',
        surface='bullpen_board', view_mode='board', team_ref='NYY', pitcher_id=42,
    )
    add_view(
        datetime(2026, 7, 10, 12, 0), 'visitor-new', 'campaign-session',
        surface='stories', referrer_domain='search.example',
        utm_source='newsletter', utm_medium='email', utm_campaign='launch',
    )
    add_view(datetime(2026, 7, 11, 12, 0), 'visitor-new-2', 'direct-session')

    db.session.add(TrafficInternalVisitor(
        visitor_id='internal-visitor',
        registered_at=datetime(2026, 7, 1, 12, 0),
        registered_by_user_id=7,
        registration_source='authenticated_email_allowlist',
    ))
    add_view(datetime(2026, 7, 10, 13, 0), 'internal-visitor', 'internal-session')
    add_view(datetime(2026, 7, 10, 14, 0), 'bot-visitor', 'bot-session', is_bot=True)
    add_view(
        datetime(2026, 7, 10, 15, 0), 'preview-visitor', 'preview-session',
        site_host='baseballos.vercel.app',
    )
    db.session.commit()


def test_summary_metrics_exclusions_acquisition_and_bullpen(reporting_app):
    seed_complete_report()
    report = build_traffic_summary('7d', now=NOW)

    assert report['timezone'] == 'America/New_York'
    assert report['selected_range']['start'] == '2026-07-08T04:00:00Z'
    assert report['summary'] == {
        'external_visitors': 3,
        'sessions': 3,
        'page_views': 4,
        'returning_visitors': 1,
        'new_visitors': 2,
        'multi_page_sessions': 1,
        'pages_per_session': 1.33,
    }
    assert report['session_depth'] == {
        'single_page_sessions': 2,
        'multi_page_sessions': 1,
        'pages_per_session': 1.33,
    }
    assert report['acquisition'] == {
        'campaign': {'sessions': 1, 'percentage': 33.33},
        'referral': {'sessions': 1, 'percentage': 33.33},
        'direct_unknown': {'sessions': 1, 'percentage': 33.33},
    }
    assert report['top_referrers'] == [
        {'referrer_domain': 'example.com', 'sessions': 1},
        {'referrer_domain': 'search.example', 'sessions': 1},
    ]
    assert report['campaigns'][0] == {
        'utm_source': 'newsletter', 'utm_medium': 'email', 'utm_campaign': 'launch', 'sessions': 1,
    }
    assert report['landing_surfaces'] == [
        {'surface': 'dashboard', 'sessions': 1},
        {'surface': 'stories', 'sessions': 1},
        {'surface': 'today', 'sessions': 1},
    ]
    assert report['bullpen_exploration']['bullpen_board_views'] == 1
    assert report['bullpen_exploration']['team_contexts'] == [{'team_ref': 'NYY', 'page_views': 1}]
    assert report['bullpen_exploration']['pitcher_context_page_views'] == 1
    health = report['measurement_health']
    assert health['measurement_started_at'] == '2026-07-01T15:00:00Z'
    assert health['last_external_page_view_at'] == '2026-07-11T12:00:00Z'
    assert health['last_canonical_page_view_at'] == '2026-07-11T12:00:00Z'
    assert health['registered_internal_browser_ids'] == 1
    assert health['selected_period']['external_page_views'] == 4
    assert health['selected_period']['excluded_internal_page_views'] == 1
    assert health['selected_period']['excluded_bot_page_views'] == 1


def test_daily_and_visited_surface_aggregates(reporting_app):
    seed_complete_report()
    report = build_traffic_summary('7d', now=NOW)
    july_eighth = next(row for row in report['daily'] if row['date'] == '2026-07-08')
    assert july_eighth == {'date': '2026-07-08', 'visitors': 1, 'sessions': 1, 'page_views': 2}
    assert report['most_visited_surfaces'][0] == {'surface': 'bullpen_board', 'page_views': 1}


def test_version_one_rows_remain_reportable_with_empty_context(reporting_app):
    add_view(datetime(2026, 7, 10, 12, 0), 'legacy-visitor', 'legacy-session')
    db.session.commit()
    report = build_traffic_summary('7d', now=NOW)
    assert report['summary']['page_views'] == 1
    assert report['evidence_exploration'] == {
        'team_read_views': 0,
        'team_relief_work_views': 0,
        'pitcher_lanes_views': 0,
        'pitcher_detail_views': 0,
        'comparison_read_views': 0,
        'comparison_evidence_views': 0,
        'team_contexts': [],
        'comparison_pairs': [],
        'entry_sources': [],
    }


def test_evidence_targets_team_contexts_and_entry_sources_aggregate(reporting_app):
    add_view(
        datetime(2026, 7, 10, 10, 0), 'visitor-one', 'session-one',
        surface='bullpen_board', view_mode='board', team_ref='BOS',
        evidence_target='team_read', entry_source='dashboard',
    )
    add_view(
        datetime(2026, 7, 10, 10, 1), 'visitor-one', 'session-one',
        surface='bullpen_board', view_mode='board', team_ref='BOS',
        evidence_target='team_relief_work', entry_source='dashboard',
    )
    add_view(
        datetime(2026, 7, 10, 11, 0), 'visitor-two', 'session-two',
        surface='bullpen_board', view_mode='board', team_ref='NYY', pitcher_id=42,
        evidence_target='pitcher_detail', entry_source='stories',
    )
    add_view(
        datetime(2026, 7, 10, 12, 0), 'visitor-three', 'session-three',
        surface='bullpen_board', view_mode='board', team_ref='NYY',
        evidence_target='pitcher_lanes',
    )
    db.session.commit()

    evidence = build_traffic_summary('7d', now=NOW)['evidence_exploration']
    assert evidence['team_read_views'] == 1
    assert evidence['team_relief_work_views'] == 1
    assert evidence['pitcher_lanes_views'] == 1
    assert evidence['pitcher_detail_views'] == 1
    assert evidence['team_contexts'] == [
        {'team_ref': 'BOS', 'page_views': 2},
        {'team_ref': 'NYY', 'page_views': 2},
    ]
    assert evidence['entry_sources'] == [
        {'entry_source': 'dashboard', 'page_views': 2, 'sessions': 1},
        {'entry_source': 'stories', 'page_views': 1, 'sessions': 1},
    ]


def test_comparison_pairs_aggregate_reverse_order_and_sort_deterministically(reporting_app):
    pairs = [
        ('NYY', 'BOS'), ('BOS', 'NYY'), ('SEA', 'BOS'), ('BOS', 'SEA'),
        ('BOS', 'NYY'), ('BOS', None), ('BOS', 'BOS'),
    ]
    for index, (team_a, team_b) in enumerate(pairs):
        add_view(
            datetime(2026, 7, 10, 10, index), f'visitor-{index}', f'session-{index}',
            surface='compare_bullpens', view_mode='compare', team_a_ref=team_a, team_b_ref=team_b,
            evidence_target=(
                'comparison_evidence' if index == 0
                else 'comparison_read' if team_a and team_b and team_a != team_b
                else None
            ),
        )
    db.session.commit()

    evidence = build_traffic_summary('7d', now=NOW)['evidence_exploration']
    assert evidence['comparison_read_views'] == 4
    assert evidence['comparison_evidence_views'] == 1
    assert evidence['comparison_pairs'] == [
        {'team_a_ref': 'BOS', 'team_b_ref': 'NYY', 'pair_key': 'BOS:NYY', 'page_views': 3},
        {'team_a_ref': 'BOS', 'team_b_ref': 'SEA', 'pair_key': 'BOS:SEA', 'page_views': 2},
    ]


def test_shared_link_landings_use_only_first_session_page_and_distinct_visitors(reporting_app):
    add_view(
        datetime(2026, 7, 9, 10, 0), 'shared-visitor', 'shared-session-one',
        surface='bullpen_board', entry_source='share_link',
    )
    add_view(
        datetime(2026, 7, 9, 10, 1), 'shared-visitor', 'shared-session-one',
        surface='bullpen_board', entry_source='dashboard',
    )
    add_view(
        datetime(2026, 7, 9, 11, 0), 'shared-visitor', 'shared-session-two',
        surface='compare_bullpens', entry_source='share_card',
    )
    add_view(datetime(2026, 7, 9, 12, 0), 'late-visitor', 'late-session', surface='today')
    add_view(
        datetime(2026, 7, 9, 12, 1), 'late-visitor', 'late-session',
        surface='bullpen_board', entry_source='share',
    )
    db.session.commit()

    shared = build_traffic_summary('7d', now=NOW)['shared_link_landings']
    assert shared == {
        'share_origin_sessions': 2,
        'share_origin_visitors': 1,
        'share_origin_page_views': 2,
    }


def test_evidence_depth_uses_external_bullpen_sessions_as_denominator(reporting_app):
    add_view(
        datetime(2026, 7, 10, 10, 0), 'deep-one', 'deep-session',
        surface='bullpen_board', evidence_target='team_read',
    )
    add_view(
        datetime(2026, 7, 10, 10, 1), 'deep-one', 'deep-session',
        surface='bullpen_board', evidence_target='team_relief_work',
    )
    add_view(
        datetime(2026, 7, 10, 11, 0), 'shallow-one', 'shallow-session',
        surface='compare_bullpens', evidence_target='comparison_read',
    )
    add_view(datetime(2026, 7, 10, 12, 0), 'non-bullpen', 'today-session')
    add_view(
        datetime(2026, 7, 10, 13, 0), 'bot-deep', 'bot-session',
        surface='bullpen_board', evidence_target='pitcher_detail', is_bot=True,
    )
    db.session.commit()

    depth = build_traffic_summary('7d', now=NOW)['evidence_depth']
    assert depth == {
        'sessions_opening_deeper_evidence': 1,
        'percentage_of_bullpen_sessions_opening_deeper_evidence': 50.0,
    }


def test_acquisition_uses_first_ever_page_in_active_session(reporting_app):
    add_view(datetime(2026, 7, 2, 12, 0), 'visitor-one', 'long-session', surface='about')
    add_view(
        datetime(2026, 7, 10, 12, 0), 'visitor-one', 'long-session',
        surface='stories', utm_source='late-campaign',
    )
    db.session.commit()
    report = build_traffic_summary('7d', now=NOW)
    assert report['summary']['sessions'] == 1
    assert report['acquisition'] == {
        'campaign': {'sessions': 0, 'percentage': 0.0},
        'referral': {'sessions': 0, 'percentage': 0.0},
        'direct_unknown': {'sessions': 1, 'percentage': 100.0},
    }
    assert report['landing_surfaces'] == [{'surface': 'about', 'sessions': 1}]


@pytest.mark.parametrize('owned_domain', [
    'baseballos.app',
    'www.baseballos.app',
    'baseballos.vercel.app',
])
def test_owned_domain_referrers_are_direct_not_external_referrals(reporting_app, owned_domain):
    add_view(
        datetime(2026, 7, 10, 12, 0), 'visitor-one', f'session-{owned_domain}',
        referrer_domain=owned_domain,
    )
    db.session.commit()

    report = build_traffic_summary('7d', now=NOW)

    assert report['acquisition']['referral'] == {'sessions': 0, 'percentage': 0.0}
    assert report['acquisition']['direct_unknown'] == {'sessions': 1, 'percentage': 100.0}
    assert report['top_referrers'] == []


def test_all_time_health_remains_available_when_selected_period_is_empty(reporting_app):
    db.session.add_all([
        TrafficInternalVisitor(
            visitor_id='internal-one',
            registered_at=datetime(2026, 6, 1, 9, 0),
            registered_by_user_id=7,
            registration_source='authenticated_email_allowlist',
        ),
        TrafficInternalVisitor(
            visitor_id='internal-two',
            registered_at=datetime(2026, 6, 1, 10, 0),
            registered_by_user_id=7,
            registration_source='authenticated_email_allowlist',
        ),
    ])
    add_view(datetime(2026, 6, 1, 12, 0), 'external-one', 'external-session')
    add_view(datetime(2026, 6, 2, 12, 0), 'internal-two', 'internal-session')
    add_view(datetime(2026, 6, 3, 12, 0), 'bot-one', 'bot-session', is_bot=True)
    db.session.commit()

    report = build_traffic_summary('7d', now=NOW)
    health = report['measurement_health']

    assert report['summary']['sessions'] == 0
    assert health['measurement_started_at'] == '2026-06-01T12:00:00Z'
    assert health['last_external_page_view_at'] == '2026-06-01T12:00:00Z'
    assert health['last_canonical_page_view_at'] == '2026-06-03T12:00:00Z'
    assert health['registered_internal_browser_ids'] == 2
    assert health['selected_period'] == {
        'canonical_page_views': 0,
        'external_page_views': 0,
        'excluded_bot_page_views': 0,
        'excluded_internal_page_views': 0,
        'unknown_device_external_page_views': 0,
    }


def test_complete_previous_period_and_zero_safe_changes(reporting_app):
    seed_complete_report()
    report = build_traffic_summary('7d', now=NOW)
    assert report['comparison']['available'] is True
    assert report['comparison']['previous']['page_views'] == 1
    assert report['comparison']['changes']['page_views']['percent'] == 300.0

    db.session.query(TrafficPageView).delete()
    add_view(datetime(2026, 7, 1, 12, 0), 'bot-baseline', 'bot-baseline-session', is_bot=True)
    add_view(datetime(2026, 7, 10, 12, 0), 'current', 'current-session')
    db.session.commit()
    zero_prior = build_traffic_summary('7d', now=NOW)
    assert zero_prior['comparison']['available'] is True
    assert zero_prior['comparison']['previous']['page_views'] == 0
    assert zero_prior['comparison']['changes']['page_views']['percent'] is None


def test_incomplete_baseline_and_all_time_comparison(reporting_app):
    add_view(datetime(2026, 7, 10, 12, 0), 'visitor-one', 'session-one')
    db.session.commit()
    report = build_traffic_summary('7d', now=NOW)
    assert report['comparison']['available'] is False
    assert report['comparison']['reason'] == 'incomplete_prior_period'
    all_time = build_traffic_summary('all', now=NOW)
    assert all_time['comparison']['available'] is False
    assert all_time['comparison']['reason'] == 'all_time_range_has_no_prior_equal_period'


def test_empty_state_response_and_invalid_range(reporting_app):
    report = build_traffic_summary('7d', now=NOW)
    assert report['summary']['external_visitors'] == 0
    assert report['summary']['sessions'] == 0
    assert report['summary']['page_views'] == 0
    assert report['summary']['pages_per_session'] is None
    assert report['acquisition'] == {
        'campaign': {'sessions': 0, 'percentage': None},
        'referral': {'sessions': 0, 'percentage': None},
        'direct_unknown': {'sessions': 0, 'percentage': None},
    }
    assert len(report['daily']) == 7
    assert report['shared_link_landings'] == {
        'share_origin_sessions': 0,
        'share_origin_visitors': 0,
        'share_origin_page_views': 0,
    }
    assert report['evidence_depth'] == {
        'sessions_opening_deeper_evidence': 0,
        'percentage_of_bullpen_sessions_opening_deeper_evidence': None,
    }
    with pytest.raises(ValueError, match='invalid_range'):
        build_traffic_summary('365d', now=NOW)


@pytest.mark.parametrize(('range_key', 'expected_days'), [('7d', 7), ('30d', 30), ('90d', 90)])
def test_fixed_ranges_use_new_york_calendar_boundaries(reporting_app, range_key, expected_days):
    report = build_traffic_summary(range_key, now=NOW)
    assert len(report['daily']) == expected_days
    assert report['selected_range']['key'] == range_key
    assert report['selected_range']['start'].endswith('04:00:00Z')


def test_endpoint_requires_authentication_and_allowlist(reporting_app, monkeypatch):
    import api.traffic as traffic_api

    client = reporting_app.test_client()
    monkeypatch.setattr(traffic_api, 'resolve_current_user', lambda: None)
    assert client.get('/api/traffic/internal/summary?range=7d').status_code == 401

    monkeypatch.setattr(
        traffic_api, 'resolve_current_user',
        lambda: SimpleNamespace(id=2, email='fan@example.com'),
    )
    assert client.get('/api/traffic/internal/summary?range=7d').status_code == 403

    monkeypatch.setattr(
        traffic_api, 'resolve_current_user',
        lambda: SimpleNamespace(id=1, email=' FOUNDER@example.com '),
    )
    for range_key in ('7d', '30d', '90d', 'all'):
        assert client.get(f'/api/traffic/internal/summary?range={range_key}').status_code == 200
    invalid = client.get('/api/traffic/internal/summary?range=365d')
    assert invalid.status_code == 400
    assert invalid.get_json()['allowed_ranges'] == ['7d', '30d', '90d', 'all']


def test_response_contains_no_raw_or_identity_fields(reporting_app):
    seed_complete_report()
    report = build_traffic_summary('7d', now=NOW)
    forbidden_keys = {
        'visitor_id', 'session_id', 'view_id', 'registered_by_user_id',
        'email', 'ip', 'user_agent', 'full_referrer', 'rows', 'pitcher_id',
    }

    def walk(value):
        if isinstance(value, dict):
            assert forbidden_keys.isdisjoint(value)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(report)
    assert 'visitor-return' not in str(report)
    assert 'return-session' not in str(report)
