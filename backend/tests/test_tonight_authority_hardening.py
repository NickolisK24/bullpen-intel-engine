"""TN-00: Tonight authority hardening.

- Repair paths write Tonight only after the replacement trusted Dashboard
  publication has committed and proved it is serving; a failed publication
  leaves the stored Tonight payload untouched.
- The incremental rebuild resolves every frozen Tonight sidecar (Team State,
  workload, rotation, rest) from the one snapshot it is rebuilding against.
- Production trusted serving stays snapshot-only and fails closed.
- Every Tonight response carries the same structural shell.
"""

from datetime import date
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import event

import models.fatigue_score  # noqa: F401
import models.game_log  # noqa: F401
import models.pitcher  # noqa: F401
import models.prospect  # noqa: F401
import services.sync as sync_service
import services.tonight_intelligence_service as tonight_svc
import services.tonight_intelligence_snapshot as tonight_snap
from api.bullpen import bullpen_bp
from models.tonight_intelligence_snapshot import TonightIntelligenceSnapshot
from services import incremental_read_model_rebuild
from services import intraday_reconcile
from services import intraday_completed_game_repair
from services import intraday_repair
from services import public_serving_authority
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REF = date(2026, 9, 24)
ENVELOPE_KEYS = set(tonight_snap.TONIGHT_ENVELOPE_KEYS)
STORED = {
    'status': 'ok',
    'reference_date': REF.isoformat(),
    'cards': [],
    'card_count': 0,
    'games': [{'game_pk': 1}],
    'game_count': 1,
    'empty_reason': None,
    'limitations': [],
}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    monkeypatch.setattr(tonight_snap, 'product_current_date', lambda: REF)
    monkeypatch.setattr(intraday_repair, 'product_current_date', lambda: REF)
    monkeypatch.setattr(intraday_completed_game_repair, 'product_current_date', lambda: REF)
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    flask_app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _store_previous_tonight():
    tonight_snap.write_snapshot(dict(STORED), source='previous_publication')
    row = tonight_snap.read_snapshot_row(REF)
    return dict(row.response_json), row.source, row.generated_at


def _stored_tonight():
    row = tonight_snap.read_snapshot_row(REF)
    return dict(row.response_json), row.source, row.generated_at


def _wire_sync_metadata(monkeypatch, module, finished):
    guard = SimpleNamespace(release=lambda: None)
    monkeypatch.setattr(module.sync_metadata, 'acquire_sync_writer_guard',
                        lambda **_kwargs: guard)
    monkeypatch.setattr(module.sync_metadata, 'start_sync_run', lambda **_kwargs: 91)
    monkeypatch.setattr(module.sync_metadata, 'set_sync_stage',
                        lambda *_args, **_kwargs: None)

    def finish(sync_run_id, **kwargs):
        finished.append(kwargs.get('status'))
        return SimpleNamespace(id=sync_run_id)

    monkeypatch.setattr(module.sync_metadata, 'finish_sync_run', finish)


def _real_tonight_writer(calls):
    """The production Tonight builder shape: it builds and commits a row."""
    def build(reference_date, *, source):
        calls.append('tonight')
        response = dict(STORED, games=[{'game_pk': 2}], limitations=['rebuilt'])
        tonight_snap.write_snapshot(response, source=source)
        return response
    return build


def _publish(calls, *, fail=False):
    def complete(*_args, **_kwargs):
        calls.append('publish')
        if fail:
            raise RuntimeError('dashboard publication failed')
        return SimpleNamespace(id=91), SimpleNamespace(id=92)
    return complete


def _proof(calls, *, verified=True):
    def prove(*_args, **_kwargs):
        calls.append('proof')
        return {'verified': verified}
    return prove


def _no_change_roster_audit(**_kwargs):
    return {
        'status': 'success',
        'lanes': {
            intraday_reconcile.LANE_ROSTER_ASSIGNMENT: {
                'verification_status': 'complete',
                'differences': [],
            },
        },
    }


def _run_roster_repair(app, calls, **overrides):
    # A corrected transaction makes the repair publish without roster findings.
    kwargs = dict(
        audit_runner=_no_change_roster_audit,
        repair_transaction_roster_evidence=True,
        transaction_roster_repair=lambda **_kwargs: {
            'status': 'success', 'repair_candidates': 1,
            'roster_gets_attempted': 1, 'transactions_corrected': 1,
        },
        recent_log_sync=lambda **_kwargs: calls.append('logs') or {
            'errors': 0, 'records_failed': 0, 'new_logs_added': 0,
            'logs_corrected': 0,
        },
        fatigue_recalc=lambda **_kwargs: calls.append('fatigue') or 0,
        today_builder=lambda *_args, **_kwargs: {'status': 'ok'},
        tonight_builder=_real_tonight_writer(calls),
        complete_with_snapshot=_publish(calls),
        publication_proof_builder=_proof(calls),
    )
    kwargs.update(overrides)
    return intraday_repair.run_intraday_roster_repair(app, **kwargs)


def _run_completed_game_repair(app, calls, monkeypatch, **overrides):
    monkeypatch.setattr(
        intraday_completed_game_repair, 'build_schedule_repair_scope',
        lambda _audit: {
            'status': 'ready', 'repairable_findings': [],
            'completed_game_pks': [], 'slate_dates': [REF.isoformat()],
        },
    )
    monkeypatch.setattr(
        intraday_completed_game_repair, '_fetch_exact_completed_games',
        lambda _scope, client=None: {},
    )
    kwargs = dict(
        audit_runner=lambda **_kwargs: {'status': 'success', 'lanes': {}},
        schedule_writer=lambda _findings: calls.append('schedule') or {},
        today_builder=lambda *_args, **_kwargs: {'status': 'ok'},
        tonight_builder=_real_tonight_writer(calls),
        complete_with_snapshot=_publish(calls),
        publication_proof_builder=_proof(calls),
    )
    kwargs.update(overrides)
    return intraday_completed_game_repair.run_intraday_completed_game_repair(app, **kwargs)


# ── Invariants 1 and 2: publication precedes the Tonight write ──────────────

def test_intraday_repair_publishes_before_writing_tonight(app, monkeypatch):
    finished = []
    _wire_sync_metadata(monkeypatch, intraday_repair, finished)
    _store_previous_tonight()
    calls = []

    result = _run_roster_repair(app, calls)

    assert result['status'] == 'success'
    assert calls[-3:] == ['publish', 'proof', 'tonight']
    assert result['tonight_refresh'] == 'complete'
    assert _stored_tonight()[0]['limitations'] == ['rebuilt']


def test_intraday_publication_failure_leaves_tonight_unchanged(app, monkeypatch):
    finished = []
    _wire_sync_metadata(monkeypatch, intraday_repair, finished)
    before = _store_previous_tonight()
    calls = []

    result = _run_roster_repair(app, calls, complete_with_snapshot=_publish(calls, fail=True))

    assert result['status'] == 'failed'
    assert 'dashboard publication failed' in result['error']
    assert 'tonight' not in calls
    assert result['tonight_snapshot'] is None
    assert finished == ['failed']
    assert _stored_tonight() == before


def test_intraday_unverified_publication_never_writes_tonight(app, monkeypatch):
    _wire_sync_metadata(monkeypatch, intraday_repair, [])
    before = _store_previous_tonight()
    calls = []

    result = _run_roster_repair(app, calls, publication_proof_builder=_proof(calls, verified=False))

    assert result['status'] == 'failed'
    assert 'tonight' not in calls
    assert _stored_tonight() == before


def test_intraday_tonight_failure_after_publication_is_partial(app, monkeypatch):
    finished = []
    _wire_sync_metadata(monkeypatch, intraday_repair, finished)
    before = _store_previous_tonight()
    calls = []

    def failing_tonight(reference_date, *, source):
        calls.append('tonight')
        raise RuntimeError('tonight build failed')

    result = _run_roster_repair(app, calls, tonight_builder=failing_tonight)

    assert calls[-3:] == ['publish', 'proof', 'tonight']
    assert result['status'] == 'partial'
    assert result['tonight_refresh'] == 'retry_required'
    assert result['dashboard_snapshot_id'] == 92
    # The published run is not rewritten as failed, and Tonight keeps the
    # previous stored payload.
    assert 'failed' not in finished
    assert _stored_tonight() == before


def test_completed_game_repair_publishes_before_writing_tonight(app, monkeypatch):
    _wire_sync_metadata(monkeypatch, intraday_completed_game_repair, [])
    _store_previous_tonight()
    calls = []

    result = _run_completed_game_repair(app, calls, monkeypatch)

    assert result['status'] == 'success'
    assert calls == ['schedule', 'publish', 'proof', 'tonight']
    assert result['tonight_refresh'] == 'complete'


def test_completed_game_publication_failure_leaves_tonight_unchanged(app, monkeypatch):
    finished = []
    _wire_sync_metadata(monkeypatch, intraday_completed_game_repair, finished)
    before = _store_previous_tonight()
    calls = []

    result = _run_completed_game_repair(
        app, calls, monkeypatch, complete_with_snapshot=_publish(calls, fail=True),
    )

    assert result['status'] == 'failed'
    assert 'tonight' not in calls
    assert finished == ['failed']
    assert _stored_tonight() == before


def test_completed_game_tonight_failure_after_publication_is_partial(app, monkeypatch):
    finished = []
    _wire_sync_metadata(monkeypatch, intraday_completed_game_repair, finished)
    before = _store_previous_tonight()
    calls = []

    result = _run_completed_game_repair(
        app, calls, monkeypatch,
        tonight_builder=lambda *_args, **_kwargs: {'status': 'error'},
    )

    assert result['status'] == 'partial'
    assert result['tonight_refresh'] == 'retry_required'
    assert 'failed' not in finished
    assert _stored_tonight() == before


# ── Invariant 3: one snapshot for every frozen sidecar ──────────────────────

def test_incremental_tonight_sidecars_resolve_from_one_snapshot(monkeypatch):
    shadow = SimpleNamespace(id='shadow-snapshot')
    seen = {}

    def recording(name):
        def listing(*, snapshot_resolver):
            seen[name] = snapshot_resolver()[0]
            return {'teams': []}
        return listing

    import services.published_team_rest_status_listing as rest_listing
    import services.published_team_rotation_listing as rotation_listing
    import services.published_team_workload_listing as workload_listing
    import services.schedule_context as schedule_context

    monkeypatch.setattr(workload_listing, 'build_published_team_workload_listing',
                        recording('workload'))
    monkeypatch.setattr(rotation_listing, 'build_published_team_rotation_listing',
                        recording('rotation'))
    monkeypatch.setattr(rest_listing, 'build_published_team_rest_status_listing',
                        recording('rest'))
    monkeypatch.setattr(schedule_context, 'build_schedule_contexts_for_date',
                        lambda _ref: [])

    def fake_serve(ref, **kwargs):
        seen['team_state'] = kwargs['team_state_listing_builder']()['snapshot']
        for key in ('workload_listing_builder', 'rotation_listing_builder',
                    'rest_status_listing_builder'):
            assert kwargs[key] is not None, key
            kwargs[key]()
        return {'games': []}

    monkeypatch.setattr(tonight_svc, 'serve_tonight', fake_serve)
    game = SimpleNamespace(game_date_et=REF, home_team_id=137, away_team_id=119)
    league_listing = {'snapshot': shadow, 'teams': []}

    incremental_read_model_rebuild._default_tonight_builder(
        game, shadow, {}, {}, league_listing,
    )

    assert seen == {
        'team_state': shadow,
        'workload': shadow,
        'rotation': shadow,
        'rest': shadow,
    }


def test_partially_injected_sidecars_never_fall_back_to_public_snapshot(monkeypatch):
    def forbidden():
        raise AssertionError('resolved the current public snapshot')

    for name in ('_default_team_state_listing_builder',
                 '_default_workload_listing_builder',
                 '_default_rotation_listing_builder',
                 '_default_rest_status_listing_builder',
                 '_default_publication_sidecar_builder'):
        monkeypatch.setattr(tonight_svc, name, forbidden)

    response = tonight_svc.serve_tonight(
        REF,
        schedule_contexts=[{'team_id': 137, 'is_playing_today': True}],
        slate_games=[],
        bullpen_context_builder=lambda _team_id, _ref: {'context_available': False},
        workload_listing_builder=lambda: {'teams': []},
    )

    assert set(response) >= ENVELOPE_KEYS


# ── Invariant 4: production trusted serving stays snapshot-only ─────────────

@pytest.fixture
def trusted_client(app, monkeypatch):
    app.view_functions['bullpen.get_tonight_intelligence'] = (
        public_serving_authority.trusted_tonight_view
    )

    def no_live_build(*_args, **_kwargs):
        raise AssertionError('trusted Tonight serving attempted a live build')

    monkeypatch.setattr(tonight_snap, 'serve_tonight', no_live_build)
    monkeypatch.setattr(tonight_snap, '_run_live_build_with_timeout', no_live_build)
    return app.test_client()


@pytest.fixture
def mutable_reads(app):
    reads = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        sql = statement.lower()
        if 'game_logs' in sql or 'fatigue_scores' in sql:
            reads.append(sql)

    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        yield reads
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)


def test_trusted_tonight_serves_stored_payload_only(app, trusted_client, mutable_reads):
    tonight_snap.write_snapshot(dict(STORED), source='daily_sync')

    response = trusted_client.get('/api/bullpen/intelligence/tonight')

    assert response.status_code == 200
    body = response.get_json()
    assert {key: body[key] for key in STORED} == STORED
    assert body['snapshot']['served_from'] == tonight_snap.SERVED_FROM_SNAPSHOT
    assert mutable_reads == []


def test_trusted_tonight_miss_fails_closed(trusted_client, mutable_reads):
    response = trusted_client.get('/api/bullpen/intelligence/tonight')

    assert response.status_code == 200
    body = response.get_json()
    assert body['status'] == 'empty'
    assert body['empty_reason'] == public_serving_authority.TONIGHT_SNAPSHOT_UNAVAILABLE
    assert (
        'No trusted Tonight snapshot is published for this slate; live rebuild is disabled.'
        in body['limitations']
    )
    assert (body['games'], body['game_count'], body['cards'], body['card_count']) == (
        [], 0, [], 0,
    )
    assert TonightIntelligenceSnapshot.query.count() == 0
    assert mutable_reads == []


def test_trusted_tonight_bad_date_is_400_in_the_shell(trusted_client):
    response = trusted_client.get('/api/bullpen/intelligence/tonight?reference_date=nope')

    assert response.status_code == 400
    body = response.get_json()
    assert set(body) >= ENVELOPE_KEYS
    assert body['status'] == 'error'
    assert body['reason_code'] == 'invalid_query_parameter'
    assert body['parameter'] == 'reference_date'
    assert (body['games'], body['game_count'], body['cards'], body['card_count']) == (
        [], 0, [], 0,
    )


# ── Invariant 5: envelope parity ────────────────────────────────────────────

def test_every_tonight_envelope_shares_the_shell(app, monkeypatch):
    client = app.test_client()

    bad = client.get('/api/bullpen/intelligence/tonight?reference_date=nope')
    assert bad.status_code == 400
    assert set(bad.get_json()) >= ENVELOPE_KEYS

    def boom(**_kwargs):
        raise RuntimeError('read failed')

    import api.bullpen as bullpen_api
    monkeypatch.setattr(bullpen_api, 'serve_tonight_cached', boom)
    failure = client.get('/api/bullpen/intelligence/tonight')
    assert failure.status_code == 503
    assert set(failure.get_json()) >= ENVELOPE_KEYS
    assert failure.get_json()['empty_reason'] == 'schedule_data_unavailable'

    shells = [
        tonight_snap._unavailable_response(
            REF, tonight_snap.EMPTY_LIVE_BUILD_TIMEOUT,
            served_from=tonight_snap.SERVED_FROM_LIVE_TIMEOUT,
        ),
        tonight_snap._unavailable_response(
            REF, tonight_snap.EMPTY_SNAPSHOT_BUILD_UNAVAILABLE,
            served_from=tonight_snap.SERVED_FROM_LIVE_FAILED,
        ),
        tonight_svc._empty(REF, tonight_svc.EMPTY_NO_SIGNALS),
        dict(STORED),
    ]
    for shell in shells:
        assert set(shell) >= ENVELOPE_KEYS
        assert shell['game_count'] == len(shell['games'])
        assert shell['card_count'] == len(shell['cards'])
