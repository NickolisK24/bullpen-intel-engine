"""CORS allowed-origins and production-entrypoint safety tests.

The browser frontend calls the backend cross-origin, so the production
frontend domains must be on the backend's CORS allowlist or requests fail with
"Failed to fetch". These tests pin the canonical custom domain and the legacy
Vercel domain as allowed, confirm an unknown origin is not, and confirm the
CORS_ORIGINS env var can add origins without a code change.

D-051 also makes the external production full-daily runner schedule-only and
binds public Board/Compare/Tonight reads to trusted publication authority. The
boundary regressions live here with other application-environment tests so the
static CI shard manifest continues to own every collected test exactly once.
"""

import importlib
import os
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from flask import Flask


def _make_app(monkeypatch, cors_origins=None):
    monkeypatch.setenv('APP_ENV', 'test')
    if cors_origins is None:
        monkeypatch.delenv('CORS_ORIGINS', raising=False)
    else:
        monkeypatch.setenv('CORS_ORIGINS', cors_origins)
    # create_app reads the (possibly patched) env at call time.
    app_module = importlib.import_module('app')
    return app_module.create_app('test')


def _allow_origin_for(app, origin):
    client = app.test_client()
    resp = client.get('/api/health', headers={'Origin': origin})
    assert resp.status_code == 200
    return resp.headers.get('Access-Control-Allow-Origin')


@pytest.mark.parametrize('origin', [
    'https://baseballos.app',         # canonical custom domain (the fix)
    'https://baseballos.vercel.app',  # legacy domain, kept during transition
    'http://localhost:5173',          # local dev
])
def test_production_and_dev_origins_are_allowed(monkeypatch, origin):
    app = _make_app(monkeypatch)
    assert _allow_origin_for(app, origin) == origin


def test_unknown_origin_is_not_allowed(monkeypatch):
    app = _make_app(monkeypatch)
    assert _allow_origin_for(app, 'https://not-baseballos.example.com') is None


def test_cors_origins_env_var_extends_allowlist(monkeypatch):
    extra = 'https://preview-baseballos.example.com'
    app = _make_app(monkeypatch, cors_origins=extra)
    assert _allow_origin_for(app, extra) == extra
    # The baked-in production domain is still allowed alongside env additions.
    assert _allow_origin_for(app, 'https://baseballos.app') == 'https://baseballos.app'


# ── D-051 production full-daily trigger authority ────────────────────────────


def _production_daily_env(**overrides):
    values = {
        'APP_ENV': 'production',
        'GITHUB_ACTIONS': 'true',
        'GITHUB_EVENT_NAME': 'schedule',
        'GITHUB_RUN_ATTEMPT': '1',
    }
    values.update(overrides)
    return values


def test_scheduled_github_daily_is_authorized():
    from scripts.run_daily_sync import production_daily_trigger_refusal_reason

    assert production_daily_trigger_refusal_reason(_production_daily_env()) is None


def test_workflow_dispatch_daily_is_refused():
    from scripts.run_daily_sync import (
        PRODUCTION_DAILY_TRIGGER_REFUSAL,
        production_daily_trigger_refusal_reason,
    )

    assert production_daily_trigger_refusal_reason(
        _production_daily_env(GITHUB_EVENT_NAME='workflow_dispatch')
    ) == PRODUCTION_DAILY_TRIGGER_REFUSAL


def test_scheduled_daily_manual_rerun_is_refused():
    from scripts.run_daily_sync import (
        PRODUCTION_DAILY_TRIGGER_REFUSAL,
        production_daily_trigger_refusal_reason,
    )

    assert production_daily_trigger_refusal_reason(
        _production_daily_env(GITHUB_RUN_ATTEMPT='2')
    ) == PRODUCTION_DAILY_TRIGGER_REFUSAL


def test_local_production_daily_is_refused():
    from scripts.run_daily_sync import (
        PRODUCTION_DAILY_TRIGGER_REFUSAL,
        production_daily_trigger_refusal_reason,
    )

    assert production_daily_trigger_refusal_reason(
        {'APP_ENV': 'production'}
    ) == PRODUCTION_DAILY_TRIGGER_REFUSAL


def test_nonproduction_daily_runner_remains_available():
    from scripts.run_daily_sync import production_daily_trigger_refusal_reason

    assert production_daily_trigger_refusal_reason(
        {'APP_ENV': 'test', 'GITHUB_EVENT_NAME': 'workflow_dispatch'}
    ) is None


# ── D-051 trusted public serving authority ───────────────────────────────────


def _trusted_authority_snapshot(authority, team_package):
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


def _trusted_board_record(pitcher_id, name, *, visible=True, unavailable_roster=False):
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


def _trusted_team_package():
    return {
        'team': {
            'team_id': 116,
            'team_name': 'Detroit Tigers',
            'team_abbreviation': 'DET',
        },
        'records': [
            _trusted_board_record(1, 'Published Arm'),
            _trusted_board_record(
                2,
                'Published IL Arm',
                visible=False,
                unavailable_roster=True,
            ),
        ],
        'default_pitcher_ids': [1],
        'roster_authority': {},
        'workload_concentration': {},
        'capacity_intelligence': {},
        'rotation_support_pressure': {},
        'bullpen_stability': {},
        'bullpen_environment': {},
    }


def _stub_trusted_snapshot(monkeypatch, authority):
    snapshot = _trusted_authority_snapshot(authority, _trusted_team_package())
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
    return snapshot


def test_team_board_serves_frozen_published_records(monkeypatch):
    from services import public_serving_authority as authority

    snapshot = _stub_trusted_snapshot(monkeypatch, authority)
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
    assert board['publication_authority']['snapshot_id'] == snapshot.id
    assert board['team_state']['public_label'] == 'Fresh'
    assert board['total_pitchers'] == 1
    names = [
        pitcher['name']
        for group in board['groups']
        for pitcher in group['pitchers']
    ]
    assert names == ['Published Arm']


def test_team_board_include_stale_uses_only_frozen_context(monkeypatch):
    from services import public_serving_authority as authority

    _stub_trusted_snapshot(monkeypatch, authority)
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


def test_missing_frozen_board_package_fails_closed_without_live_rebuild(monkeypatch):
    from services import public_serving_authority as authority

    snapshot = _stub_trusted_snapshot(monkeypatch, authority)
    snapshot.payload.pop(authority.TEAM_BOARD_PACKAGE_KEY)

    board = authority.build_published_team_board(116)

    assert board['status'] == 'snapshot_unavailable'
    assert board['reason'] == authority.TEAM_BOARD_PACKAGE_MISSING
    assert board['total_pitchers'] == 0
    assert board['publication_authority']['snapshot_id'] == snapshot.id


def test_trusted_tonight_view_never_builds_on_cache_miss(monkeypatch):
    from services import public_serving_authority as authority

    captured = {}

    def fake_serve(**kwargs):
        captured.update(kwargs)
        return {
            'status': 'empty',
            'reference_date': '2026-08-08',
            'cards': [],
            'card_count': 0,
            'empty_reason': (
                authority.tonight_intelligence_snapshot.EMPTY_SNAPSHOT_BUILD_UNAVAILABLE
            ),
            'limitations': [],
        }

    monkeypatch.setattr(
        authority.tonight_intelligence_snapshot,
        'serve_tonight_cached',
        fake_serve,
    )
    app = Flask(__name__)
    with app.test_request_context(
        '/api/bullpen/intelligence/tonight?reference_date=2026-08-08'
    ):
        response = authority.trusted_tonight_view()
        payload = response.get_json()

    assert captured['build_on_miss'] is False
    assert captured['persist'] is False
    assert payload['empty_reason'] == authority.TONIGHT_SNAPSHOT_UNAVAILABLE
    assert 'live rebuild is disabled' in payload['limitations'][0].lower()
