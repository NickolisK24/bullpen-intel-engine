from datetime import date, datetime
from types import SimpleNamespace

from flask import Flask

from scripts.run_daily_sync import (
    PRODUCTION_DAILY_TRIGGER_REFUSAL,
    production_daily_trigger_refusal_reason,
)
from services import public_serving_authority as authority


def _production_env(**overrides):
    values = {
        'APP_ENV': 'production',
        'GITHUB_ACTIONS': 'true',
        'GITHUB_EVENT_NAME': 'schedule',
    }
    values.update(overrides)
    return values


def test_production_daily_runner_allows_scheduled_github_trigger():
    assert production_daily_trigger_refusal_reason(_production_env()) is None


def test_production_daily_runner_refuses_workflow_dispatch_before_app_import():
    assert production_daily_trigger_refusal_reason(
        _production_env(GITHUB_EVENT_NAME='workflow_dispatch')
    ) == PRODUCTION_DAILY_TRIGGER_REFUSAL


def test_production_daily_runner_refuses_local_production_invocation():
    assert production_daily_trigger_refusal_reason(
        {'APP_ENV': 'production'}
    ) == PRODUCTION_DAILY_TRIGGER_REFUSAL


def test_nonproduction_daily_runner_remains_available():
    assert production_daily_trigger_refusal_reason(
        {'APP_ENV': 'test', 'GITHUB_EVENT_NAME': 'workflow_dispatch'}
    ) is None


def _snapshot(team_package):
    return SimpleNamespace(
        id=901,
        sync_run_id=801,
        data_through=date(2026, 8, 7),
        availability_reference_date=date(2026, 8, 8),
        snapshot_generated_at=datetime(2026, 8, 8, 10, 30, 0),
        published_at=datetime(2026, 8, 8, 10, 31, 0),
        payload={
            authority.TEAM_BOARD_PACKAGE_KEY: {
                'contract': authority.TEAM_BOARD_PACKAGE_CONTRACT,
                'by_team_id': {'116': team_package},
            },
            'freshness': {
                'data_through': '2026-08-07',
                'availability_reference_date': '2026-08-08',
                'is_current': True,
                'limitations': [],
            },
        },
    )


def _record(pitcher_id, name, *, visible=True, unavailable_roster=False):
    return {
        'name': name,
        'pitcher_id': pitcher_id,
        'fatigue_score': 21.0,
        'availability': {
            'availability_status': 'Available',
            'confidence': 'high',
            'data_state': 'fresh',
            'reasons': [],
            'limitations': [],
            'inputs': {
                'appearances_last_5_days': 1,
                'pitches_last_5_days': 12,
            },
        },
        'last_appearance': {'game_date': '2026-08-07', 'pitches': 12},
        'last_workload_appearance': {'game_date': '2026-08-07', 'pitches': 12},
        'role': {},
        'pitcher_labels': {},
        'public_role_read': None,
        'eligibility': {},
        'roster_status': {},
        'visibility': {
            'is_visible_by_default': visible,
            'is_unavailable_roster_status': unavailable_roster,
        },
    }


def _team_package():
    return {
        'team': {
            'team_id': 116,
            'team_name': 'Detroit Tigers',
            'team_abbreviation': 'DET',
        },
        'records': [
            _record(1, 'Published Arm'),
            _record(2, 'Published IL Arm', visible=False, unavailable_roster=True),
        ],
        'default_pitcher_ids': [1],
        'roster_authority': {},
        'workload_concentration': {},
        'capacity_intelligence': {},
        'rotation_support_pressure': {},
        'bullpen_stability': {},
        'bullpen_environment': {},
    }


def test_board_serves_frozen_published_records(monkeypatch):
    snapshot = _snapshot(_team_package())
    monkeypatch.setattr(
        authority.dashboard_snapshot_service,
        'get_latest_valid_dashboard_snapshot',
        lambda: snapshot,
    )
    monkeypatch.setattr(
        authority.board_freshness,
        'published_snapshot_freshness_block',
        lambda: dict(snapshot.payload['freshness']),
    )
    monkeypatch.setattr(
        authority,
        '_published_team_state',
        lambda _snapshot, _team_id: {
            'contract': 'team_state_public_v1',
            'available': True,
            'public_state': 'fresh',
            'public_label': 'Fresh',
            'outcome': 'available',
            'unavailable_message': None,
            'reason_code': None,
            'data_through': '2026-08-07',
        },
    )

    board = authority.build_published_team_board(116)

    assert board['served_from'] == 'trusted_dashboard_snapshot'
    assert board['publication_authority']['snapshot_id'] == 901
    assert board['team_state']['public_label'] == 'Fresh'
    assert board['total_pitchers'] == 1
    names = [
        pitcher['name']
        for group in board['groups']
        for pitcher in group['pitchers']
    ]
    assert names == ['Published Arm']


def test_include_stale_uses_only_frozen_context(monkeypatch):
    snapshot = _snapshot(_team_package())
    monkeypatch.setattr(
        authority.dashboard_snapshot_service,
        'get_latest_valid_dashboard_snapshot',
        lambda: snapshot,
    )
    monkeypatch.setattr(
        authority.board_freshness,
        'published_snapshot_freshness_block',
        lambda: dict(snapshot.payload['freshness']),
    )
    monkeypatch.setattr(
        authority,
        '_published_team_state',
        lambda *_args: authority.team_state_unavailable(
            authority.TEAM_STATE_READINESS_UNAVAILABLE
        ),
    )

    board = authority.build_published_team_board(116, include_stale=True)
    names = sorted(
        pitcher['name']
        for group in board['groups']
        for pitcher in group['pitchers']
    )
    assert names == ['Published Arm', 'Published IL Arm']


def test_missing_frozen_package_fails_closed_instead_of_live_rebuild(monkeypatch):
    snapshot = _snapshot(_team_package())
    snapshot.payload.pop(authority.TEAM_BOARD_PACKAGE_KEY)
    monkeypatch.setattr(
        authority.dashboard_snapshot_service,
        'get_latest_valid_dashboard_snapshot',
        lambda: snapshot,
    )
    monkeypatch.setattr(
        authority.board_freshness,
        'published_snapshot_freshness_block',
        lambda: dict(snapshot.payload['freshness']),
    )

    board = authority.build_published_team_board(116)

    assert board['status'] == 'snapshot_unavailable'
    assert board['reason'] == authority.TEAM_BOARD_PACKAGE_MISSING
    assert board['total_pitchers'] == 0
    assert board['publication_authority']['snapshot_id'] == 901


def test_tonight_public_view_never_builds_on_cache_miss(monkeypatch):
    captured = {}

    def fake_serve(**kwargs):
        captured.update(kwargs)
        return {
            'status': 'empty',
            'reference_date': '2026-08-08',
            'cards': [],
            'card_count': 0,
            'empty_reason': authority.tonight_intelligence_snapshot.EMPTY_SNAPSHOT_BUILD_UNAVAILABLE,
            'limitations': [],
        }

    monkeypatch.setattr(
        authority.tonight_intelligence_snapshot,
        'serve_tonight_cached',
        fake_serve,
    )
    app = Flask(__name__)
    with app.test_request_context('/api/bullpen/intelligence/tonight?reference_date=2026-08-08'):
        response = authority.trusted_tonight_view()
        payload = response.get_json()

    assert captured['build_on_miss'] is False
    assert captured['persist'] is False
    assert payload['empty_reason'] == authority.TONIGHT_SNAPSHOT_UNAVAILABLE
    assert 'live rebuild is disabled' in payload['limitations'][0].lower()
