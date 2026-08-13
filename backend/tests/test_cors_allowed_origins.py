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
    'http://localhost:5173',          # local dev (Vite)
    'http://localhost:3000',          # local dev (alternate port)
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


# ── CORS request-path regression contract (#601) ─────────────────────────────
#
# The backend's CORS layer is a production request-path dependency: it decides
# which browser origins may read /api/*. The tests above pin the allowlist, but
# they only exercise simple GET on /api/health. That leaves the rest of the
# contract — preflight, credentials, wildcards, path scoping, Private Network
# Access — unasserted, so a dependency upgrade could change any of it and the
# suite would stay green.
#
# The cases below close that gap. Two of them (Private Network Access and
# request-path case sensitivity) deliberately assert CURRENT, KNOWN-INSECURE
# behaviour so the security upgrade has an executable before/after receipt.
# Those two are marked inline and are expected to be flipped — never deleted —
# when the dependency moves.

PROD_ORIGIN = 'https://baseballos.app'
LEGACY_ORIGIN = 'https://baseballos.vercel.app'
DEV_ORIGIN_5173 = 'http://localhost:5173'
DEV_ORIGIN_3000 = 'http://localhost:3000'
EVIL_ORIGIN = 'https://evil.example'

# Real routes, chosen because they exercise the genuine production CORS path
# without needing database schema:
#   * the public one answers 200 with no auth and no database read;
#   * the authenticated one answers 401 from the bearer-token check, which runs
#     before any database access. CORS headers are applied by the extension
#     regardless of the view's status, which is exactly what these assert.
PUBLIC_API_ROUTE = '/api/methodology/'
AUTHENTICATED_API_ROUTE = '/api/me/teams'
# Outside the r"/api/*" resource pattern. CORS scoping is decided from the
# request path, so whether this path routes to a view is irrelevant here.
NON_API_ROUTE = '/health'


def _request(app, method, path, origin=None, **extra_headers):
    headers = dict(extra_headers)
    if origin is not None:
        headers['Origin'] = origin
    return getattr(app.test_client(), method)(path, headers=headers)


def _preflight(app, path, origin, request_method='POST',
               request_headers='Authorization, Content-Type', **extra_headers):
    headers = {
        'Access-Control-Request-Method': request_method,
        'Access-Control-Request-Headers': request_headers,
    }
    headers.update(extra_headers)
    return _request(app, 'options', path, origin=origin, **headers)


def _acao(response):
    return response.headers.get('Access-Control-Allow-Origin')


# C1-C4 — every allowlisted origin is authorized. Covered by
# test_production_and_dev_origins_are_allowed above (all four origins).

# C5 — an arbitrary hostile origin receives no CORS authorization.
def test_hostile_origin_receives_no_cors_authorization(monkeypatch):
    app = _make_app(monkeypatch)
    assert _acao(_request(app, 'get', '/api/health', origin=EVIL_ORIGIN)) is None


# C6 — the opaque "null" origin (sandboxed iframe, file://, some redirects) is
# not an allowlist entry and must not be authorized.
def test_null_origin_receives_no_cors_authorization(monkeypatch):
    app = _make_app(monkeypatch)
    assert _acao(_request(app, 'get', '/api/health', origin='null')) is None


# C7 — preflight from an allowed origin is authorized, and the method/header
# negotiation the frontend depends on is governed rather than absent.
def test_preflight_from_allowed_origin_is_authorized(monkeypatch):
    app = _make_app(monkeypatch)
    resp = _preflight(app, PUBLIC_API_ROUTE, PROD_ORIGIN)

    assert _acao(resp) == PROD_ORIGIN

    allowed_methods = {
        method.strip().upper()
        for method in (resp.headers.get('Access-Control-Allow-Methods') or '').split(',')
        if method.strip()
    }
    # The requested method is granted, and the response enumerates a governed
    # method set rather than leaving it unset.
    assert 'POST' in allowed_methods
    assert 'GET' in allowed_methods
    assert allowed_methods

    allowed_headers = {
        header.strip().lower()
        for header in (resp.headers.get('Access-Control-Allow-Headers') or '').split(',')
        if header.strip()
    }
    # Both headers the browser client actually sends must survive preflight.
    assert 'authorization' in allowed_headers
    assert 'content-type' in allowed_headers


# C8 — the same preflight from an unapproved origin is not authorized.
def test_preflight_from_hostile_origin_is_not_authorized(monkeypatch):
    app = _make_app(monkeypatch)
    resp = _preflight(app, PUBLIC_API_ROUTE, EVIL_ORIGIN)

    assert _acao(resp) is None
    assert resp.headers.get('Access-Control-Allow-Methods') is None
    assert resp.headers.get('Access-Control-Allow-Headers') is None


# C9 — CRITICAL SECURITY INVARIANT. The API is not configured for credentialed
# cross-origin requests, so Access-Control-Allow-Credentials must never be
# emitted. Combined with the explicit allowlist, this is what keeps a permissive
# CORS response from being able to carry cookies or auth material.
def test_credentials_are_never_allowed_on_simple_request(monkeypatch):
    app = _make_app(monkeypatch)
    resp = _request(app, 'get', '/api/health', origin=PROD_ORIGIN)

    assert _acao(resp) == PROD_ORIGIN
    assert resp.headers.get('Access-Control-Allow-Credentials') is None


def test_credentials_are_never_allowed_on_preflight(monkeypatch):
    app = _make_app(monkeypatch)
    resp = _preflight(app, PUBLIC_API_ROUTE, PROD_ORIGIN)

    assert _acao(resp) == PROD_ORIGIN
    assert resp.headers.get('Access-Control-Allow-Credentials') is None


# C10 — the allowlist is echoed per-origin; a wildcard is never returned.
@pytest.mark.parametrize('origin', [
    PROD_ORIGIN,
    LEGACY_ORIGIN,
    DEV_ORIGIN_5173,
    DEV_ORIGIN_3000,
])
def test_allowed_origin_is_echoed_and_never_wildcarded(monkeypatch, origin):
    app = _make_app(monkeypatch)
    resp = _request(app, 'get', '/api/health', origin=origin)

    assert _acao(resp) == origin
    assert _acao(resp) != '*'


def test_preflight_never_returns_wildcard_origin(monkeypatch):
    app = _make_app(monkeypatch)
    assert _acao(_preflight(app, PUBLIC_API_ROUTE, PROD_ORIGIN)) != '*'


# C11 — *** PRE-UPGRADE BEHAVIOUR RECEIPT — EXPECTED TO BE FLIPPED. ***
#
# Flask-CORS 4.0.0 answers a Private Network Access preflight with
# Access-Control-Allow-Private-Network: true unconditionally, with no
# configuration option to disable it (CVE-2024-6221). This test freezes that
# observed pre-upgrade behaviour so the security upgrade can prove the
# transition rather than assert it.
#
# This is NOT an endorsement of the behaviour. It is a before-state receipt, and
# it is deliberately a hard assertion — not xfail, not skip — because a test
# that is allowed to pass either way proves nothing about the upgrade.
#
# When Flask-CORS moves to a version that fixes CVE-2024-6221, this expectation
# must be changed to assert the secure condition.
def test_private_network_access_current_flask_cors_4_behaviour(monkeypatch):
    app = _make_app(monkeypatch)
    resp = _preflight(
        app,
        '/api/health',
        PROD_ORIGIN,
        request_method='GET',
        **{'Access-Control-Request-Private-Network': 'true'},
    )

    assert _acao(resp) == PROD_ORIGIN
    assert resp.headers.get('Access-Control-Allow-Private-Network') == 'true'


# C12 — Private Network Access is still governed by the allowlist: a hostile
# origin gets nothing, on this version and every later one.
def test_private_network_access_from_hostile_origin_is_not_authorized(monkeypatch):
    app = _make_app(monkeypatch)
    resp = _preflight(
        app,
        '/api/health',
        EVIL_ORIGIN,
        request_method='GET',
        **{'Access-Control-Request-Private-Network': 'true'},
    )

    assert _acao(resp) is None
    assert resp.headers.get('Access-Control-Allow-Private-Network') is None


# C13 — the CORS policy is scoped to r"/api/*". Paths outside it are not
# authorized for cross-origin reads even from an allowlisted origin.
def test_non_api_path_receives_no_cors_authorization(monkeypatch):
    app = _make_app(monkeypatch)
    assert _acao(_request(app, 'get', NON_API_ROUTE, origin=PROD_ORIGIN)) is None


# C14 — *** PRE-UPGRADE BEHAVIOUR RECEIPT — EXPECTED TO BE FLIPPED. ***
#
# Flask-CORS 4.0.0 matches the r"/api/*" resource pattern case-insensitively
# (CVE-2024-6866), so an uppercase /API/... path is treated as in-scope and
# receives CORS headers. BaseballOS declares a single resource policy, so this
# grants no additional origin access today — but it is still incorrect matching,
# and it is fixed by the upgrade.
#
# Frozen here as a hard assertion for the same reason as C11: the upgrade must
# demonstrate the change, not quietly absorb it.
def test_uppercase_api_path_current_flask_cors_4_behaviour(monkeypatch):
    app = _make_app(monkeypatch)
    resp = _request(app, 'get', '/API/health', origin=PROD_ORIGIN)

    assert _acao(resp) == PROD_ORIGIN


# C15 — covered by test_cors_origins_env_var_extends_allowlist above: an extra
# configured origin is accepted without displacing the baked-in production
# origins.

# C16 — CORS_ORIGINS parsing tolerates surrounding whitespace and ignores empty
# entries, so a hand-edited environment variable cannot silently authorize an
# empty origin or drop a valid one.
def test_cors_origins_parsing_handles_whitespace_and_empty_entries(monkeypatch):
    app = _make_app(
        monkeypatch,
        cors_origins=' https://a.example , , https://b.example ',
    )

    # Surrounding whitespace is stripped: the configured ' https://a.example '
    # authorizes the exact origin a browser actually sends.
    assert _allow_origin_for(app, 'https://a.example') == 'https://a.example'
    assert _allow_origin_for(app, 'https://b.example') == 'https://b.example'
    # The baked-in production origins survive the env addition.
    assert _allow_origin_for(app, PROD_ORIGIN) == PROD_ORIGIN
    assert _allow_origin_for(app, LEGACY_ORIGIN) == LEGACY_ORIGIN
    # The empty entry between the commas is dropped rather than widening the
    # allowlist: a hostile origin is still refused, and a whitespace-only origin
    # never matches the stripped empty entry.
    assert _acao(_request(app, 'get', '/api/health', origin=EVIL_ORIGIN)) is None
    assert _acao(_request(app, 'get', '/api/health', origin='   ')) is None


# A request that carries no Origin header at all is not a cross-origin browser
# request, and the extension answers it with a default allowlisted origin rather
# than a wildcard or a caller-supplied value. Pinned so the fallback can never
# silently widen: it must stay inside the allowlist and never become "*".
def test_request_without_origin_header_falls_back_inside_the_allowlist(monkeypatch):
    app = _make_app(monkeypatch)
    resp = app.test_client().get('/api/health')

    allowlisted = {PROD_ORIGIN, LEGACY_ORIGIN, DEV_ORIGIN_5173, DEV_ORIGIN_3000}
    assert _acao(resp) != '*'
    assert _acao(resp) in allowlisted
    assert resp.headers.get('Access-Control-Allow-Credentials') is None


# C17 — a real public, unauthenticated API route follows the same policy as
# /api/health; the contract is not special-cased to the health endpoint.
def test_public_api_route_follows_the_same_cors_policy(monkeypatch):
    app = _make_app(monkeypatch)

    allowed = _request(app, 'get', PUBLIC_API_ROUTE, origin=PROD_ORIGIN)
    assert _acao(allowed) == PROD_ORIGIN
    assert allowed.headers.get('Access-Control-Allow-Credentials') is None

    hostile = _request(app, 'get', PUBLIC_API_ROUTE, origin=EVIL_ORIGIN)
    assert _acao(hostile) is None


# C18 — an authenticated/internal route is not MORE permissive than a public
# one. No production token is used: the route answers 401 without credentials,
# and CORS headers are applied independently of that, which is precisely the
# property under test.
def test_authenticated_api_route_is_not_more_permissive(monkeypatch):
    app = _make_app(monkeypatch)

    hostile = _request(app, 'get', AUTHENTICATED_API_ROUTE, origin=EVIL_ORIGIN)
    assert _acao(hostile) is None
    assert hostile.headers.get('Access-Control-Allow-Credentials') is None

    hostile_preflight = _preflight(app, AUTHENTICATED_API_ROUTE, EVIL_ORIGIN)
    assert _acao(hostile_preflight) is None

    # The allowlisted origin is authorized on the same route, so the assertion
    # above is about the origin being rejected rather than the route being
    # unreachable.
    allowed = _request(app, 'get', AUTHENTICATED_API_ROUTE, origin=PROD_ORIGIN)
    assert _acao(allowed) == PROD_ORIGIN
    assert allowed.headers.get('Access-Control-Allow-Credentials') is None


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
