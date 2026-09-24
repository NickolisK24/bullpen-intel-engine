"""TN-02: serving the stored tonight_v1 projection of the current trusted publication.

Fixtures are real trusted Dashboard publications (the TN-01 fixture) with
``tonight_publications`` rows written by the TN-01 generator. Serving must
resolve the current trusted snapshot first, return only the row bound to that
exact snapshot, pass its stored payload through unchanged, and never build,
write, or read baseball tables.
"""

from copy import deepcopy
import ast
import inspect

import pytest
from sqlalchemy import event

from models.slate_game import SlateGame
from models.tonight_intelligence_snapshot import TonightIntelligenceSnapshot
from models.tonight_publication import TonightPublication
from services import public_delivery
from services import tonight_read_model
from services import tonight_v1_serving
from tests.test_tonight_v1_read_model import (  # noqa: F401 - pytest fixtures
    _publish,
    mutable_reads,
    tonight_app,
)
from utils.db import db


V1_URL = '/api/bullpen/intelligence/tonight?contract=tonight_v1'
LEGACY_URL = '/api/bullpen/intelligence/tonight'


def _forbid_builds(monkeypatch):
    """Every live Tonight / bullpen builder raises if serving reaches it."""
    def forbidden(*_args, **_kwargs):
        raise AssertionError('tonight_v1 serving reached a builder')

    import services.bullpen_context as bullpen_context
    from api import bullpen as bullpen_api
    monkeypatch.setattr(tonight_read_model, 'build_tonight_v1', forbidden)
    monkeypatch.setattr(tonight_read_model, 'generate_tonight_v1_for_snapshot', forbidden)
    monkeypatch.setattr(tonight_read_model, 'generate_tonight_v1_after_publication', forbidden)
    monkeypatch.setattr(tonight_read_model, 'load_slate_games', forbidden)
    monkeypatch.setattr(bullpen_context, 'build_team_bullpen_context', forbidden)
    monkeypatch.setattr(bullpen_api, 'serve_tonight_cached', forbidden)


def _generate(snapshot):
    row, outcome = tonight_read_model.generate_tonight_v1_for_snapshot(snapshot)
    assert outcome == 'created'
    return row


def _get(env, url=V1_URL, **headers):
    return env.app.test_client().get(url, headers=headers)


def _assert_unavailable(response, reason_code):
    assert response.status_code == 200
    body = response.get_json()
    assert body['contract'] == 'tonight_v1'
    assert body['status'] == 'unavailable'
    assert body['reason'] == body['empty_reason'] == 'trusted_tonight_v1_publication_unavailable'
    assert body['reason_codes'] == [reason_code]
    assert body['edition'] is None
    assert body['games'] == [] and body['game_count'] == 0
    assert body['summary'] == {'game_count': 0}
    assert body['featured_game_pks'] == [] and body['league_changes'] == []
    assert body['lead'] is None
    assert len(body['limitations']) == 1
    assert response.headers['Cache-Control'] == public_delivery.NO_STORE_CACHE_CONTROL
    assert 'ETag' not in response.headers
    assert response.headers['X-BaseballOS-Contract'] == 'tonight_v1'
    return body


def _writes(statements):
    return [
        sql for sql in statements
        if sql.lstrip().startswith(('insert', 'update', 'delete'))
    ]


# ── 1. Current hit, headers, ETag ────────────────────────────────────────────

def test_current_v1_hit_serves_the_stored_row(tonight_app, monkeypatch):
    row = _generate(tonight_app.snapshot)
    stored = deepcopy(row.payload)

    _forbid_builds(monkeypatch)
    response = _get(tonight_app)

    assert response.status_code == 200
    body = response.get_json()
    assert body == stored
    publication = body['edition']['publication']
    assert publication['dashboard_snapshot_id'] == tonight_app.snapshot.id
    assert response.headers['ETag'] == f'"{row.content_sha256}"'
    assert response.headers['Cache-Control'] == public_delivery.CURRENT_ALIAS_CACHE_CONTROL
    assert TonightPublication.query.count() == 1


def test_delivery_headers_identify_the_served_publication(tonight_app, monkeypatch):
    _generate(tonight_app.snapshot)

    _forbid_builds(monkeypatch)
    response = _get(tonight_app)
    body = response.get_json()
    publication = body['edition']['publication']

    assert response.headers['X-BaseballOS-Snapshot-ID'] == str(publication['dashboard_snapshot_id'])
    assert response.headers['X-BaseballOS-Sync-Run-ID'] == str(publication['sync_run_id'])
    assert response.headers['X-BaseballOS-Data-Through'] == body['edition']['data_through']
    assert response.headers['X-BaseballOS-Contract'] == body['contract'] == 'tonight_v1'


def test_if_none_match_returns_304_without_building(tonight_app, monkeypatch):
    row = _generate(tonight_app.snapshot)

    _forbid_builds(monkeypatch)
    response = _get(tonight_app, **{'If-None-Match': f'"{row.content_sha256}"'})

    assert response.status_code == 304
    assert response.get_data() == b''
    assert response.headers['ETag'] == f'"{row.content_sha256}"'
    assert _get(tonight_app, **{'If-None-Match': '"other"'}).status_code == 200


def test_new_publication_content_changes_the_etag(tonight_app):
    first = _generate(tonight_app.snapshot)
    game = db.session.get(SlateGame, 801)
    game.normalized_state = 'live'
    db.session.commit()
    newer = _publish(tonight_app.reference_date, source='tonight_v2_newer')
    second = _generate(newer)

    response = _get(tonight_app)

    assert second.content_sha256 != first.content_sha256
    assert response.headers['ETag'] == f'"{second.content_sha256}"'
    assert response.get_json()['edition']['publication']['dashboard_snapshot_id'] == newer.id


# ── 2-4. Missing, stale, same-date multiple snapshots ────────────────────────

def test_current_v1_missing_fails_closed(tonight_app, monkeypatch):
    _forbid_builds(monkeypatch)
    body = _assert_unavailable(_get(tonight_app), 'tonight_v1_publication_missing')

    assert body['current_publication']['dashboard_snapshot_id'] == tonight_app.snapshot.id
    assert body['limitations'] == [
        'The current trusted publication does not yet have a Tonight v1 projection.'
    ]
    assert TonightPublication.query.count() == 0


def test_stale_row_for_an_older_snapshot_is_never_current(tonight_app, monkeypatch):
    older_row = _generate(tonight_app.snapshot)
    newer = _publish(tonight_app.reference_date, source='tonight_v2_newer')
    assert newer.id > older_row.dashboard_snapshot_id

    _forbid_builds(monkeypatch)
    body = _assert_unavailable(_get(tonight_app), 'tonight_v1_publication_missing')

    assert body['current_publication']['dashboard_snapshot_id'] == newer.id
    assert TonightPublication.query.count() == 1


def test_same_date_multiple_snapshots_serve_only_the_trusted_one(tonight_app, monkeypatch):
    snapshot_a = tonight_app.snapshot
    row_a = _generate(snapshot_a)
    snapshot_b = _publish(tonight_app.reference_date, source='tonight_v2_b')
    # Generated out of order: row B is not the most recently created row.
    row_b = _generate(snapshot_b)
    assert row_a.reference_date == row_b.reference_date

    _forbid_builds(monkeypatch)
    response = _get(tonight_app)

    assert response.status_code == 200
    assert response.get_json()['edition']['publication']['dashboard_snapshot_id'] == snapshot_b.id
    assert response.headers['ETag'] == f'"{row_b.content_sha256}"'



# ── 5. Stored identity must match payload and snapshot ───────────────────────

def _store_tampered(env, mutate):
    good = tonight_read_model.build_tonight_v1(
        env.snapshot,
        tonight_read_model.load_slate_games(env.snapshot.availability_reference_date),
        generated_at=env.snapshot.snapshot_generated_at,
    )
    payload = deepcopy(good)
    row = TonightPublication(
        contract='tonight_v1',
        reference_date=env.snapshot.availability_reference_date,
        dashboard_snapshot_id=env.snapshot.id,
        sync_run_id=env.snapshot.sync_run_id,
        data_through=env.snapshot.data_through,
        availability_reference_date=env.snapshot.availability_reference_date,
        payload=payload,
        content_sha256=tonight_read_model.content_sha256(payload),
        generated_at=env.snapshot.snapshot_generated_at,
    )
    mutate(row, payload)
    db.session.add(row)
    db.session.commit()
    return row


@pytest.mark.parametrize('field, mutate', [
    ('dashboard_snapshot_id', lambda row, payload: payload['edition']['publication'].update(
        dashboard_snapshot_id=row.dashboard_snapshot_id + 1)),
    ('sync_run_id', lambda row, payload: payload['edition']['publication'].update(
        sync_run_id=987654)),
    ('data_through', lambda row, payload: payload['edition'].update(data_through='1999-01-01')),
    ('reference_date', lambda row, payload: payload['edition'].update(baseball_date='1999-01-02')),
    ('contract', lambda row, payload: payload.update(contract='tonight_v0')),
    ('content_sha256', lambda row, payload: setattr(row, 'content_sha256', 'not-a-digest')),
])
def test_identity_mismatch_fails_closed(tonight_app, field, mutate, caplog):
    row = _store_tampered(tonight_app, mutate)
    assert tonight_v1_serving.identity_mismatch(row, tonight_app.snapshot) == field

    with caplog.at_level('ERROR'):
        _assert_unavailable(_get(tonight_app), 'tonight_v1_publication_identity_mismatch')

    assert 'tonight_v1 authority integrity failure' in caplog.text
    stored = db.session.get(TonightPublication, row.id)
    assert stored.payload == row.payload  # not repaired on request


def test_consistent_row_has_no_identity_mismatch(tonight_app):
    row = _generate(tonight_app.snapshot)
    assert tonight_v1_serving.identity_mismatch(row, tonight_app.snapshot) is None


# ── 7-8. Contract negotiation and legacy default ─────────────────────────────

def test_default_request_still_serves_legacy_tonight_v5(tonight_app, monkeypatch):
    from api import bullpen as bullpen_api
    legacy = {
        'status': 'ok', 'reference_date': tonight_app.reference_date.isoformat(),
        'cards': [{'card_id': 'legacy'}], 'card_count': 1, 'games': [], 'game_count': 0,
        'empty_reason': None, 'limitations': [],
    }
    calls = []

    def fake_serve(reference_date=None, **_kwargs):
        calls.append(reference_date)
        return deepcopy(legacy)

    # The trusted override (installed by the fixture, as in production) and
    # the original view both keep calling the legacy tonight_v5 reader.
    from services import tonight_intelligence_snapshot
    monkeypatch.setattr(tonight_intelligence_snapshot, 'serve_tonight_cached', fake_serve)
    monkeypatch.setattr(bullpen_api, 'serve_tonight_cached', fake_serve)
    monkeypatch.setattr(
        tonight_v1_serving, 'serve_current_tonight_v1',
        lambda: (_ for _ in ()).throw(AssertionError('default reached tonight_v1')),
    )
    _generate(tonight_app.snapshot)

    for url in (LEGACY_URL, LEGACY_URL + '?contract=tonight_v5', LEGACY_URL + '?contract='):
        response = _get(tonight_app, url)
        assert response.status_code == 200
        assert response.get_json() == legacy
        assert 'X-BaseballOS-Contract' not in response.headers
        assert 'ETag' not in response.headers
    assert calls == [None, None, None]


def test_invalid_contract_is_a_stable_400(tonight_app, monkeypatch):
    _forbid_builds(monkeypatch)
    response = _get(tonight_app, LEGACY_URL + '?contract=garbage')

    assert response.status_code == 400
    body = response.get_json()
    assert body['status'] == 'error'
    assert body['reason_code'] == body['empty_reason'] == 'invalid_query_parameter'
    assert body['parameter'] == 'contract'
    assert body['cards'] == [] and body['games'] == []


@pytest.mark.parametrize('param', ['reference_date=2026-01-01', 'dashboard_snapshot_id=1'])
def test_v1_is_current_only(tonight_app, monkeypatch, param):
    _generate(tonight_app.snapshot)

    _forbid_builds(monkeypatch)
    response = _get(tonight_app, f'{V1_URL}&{param}')

    assert response.status_code == 400
    assert response.get_json()['parameter'] == param.split('=')[0]


# ── 9. Bounded reads, no writes ──────────────────────────────────────────────

def test_v1_hit_reads_no_baseball_tables_and_writes_nothing(
    tonight_app, mutable_reads, monkeypatch,
):
    _generate(tonight_app.snapshot)
    tonight_intelligence_snapshot_count = TonightIntelligenceSnapshot.query.count()
    del mutable_reads[:]

    _forbid_builds(monkeypatch)
    response = _get(tonight_app)

    assert response.status_code == 200
    assert not [sql for sql in mutable_reads if 'game_logs' in sql]
    assert not [sql for sql in mutable_reads if 'fatigue_scores' in sql]
    assert not [sql for sql in mutable_reads if 'slate_games' in sql or 'from pitchers' in sql]
    assert _writes(mutable_reads) == []
    print(f'TONIGHT_V1_SERVING_QUERY_COUNT={len(mutable_reads)}')
    # Trusted snapshot projection + publication row.
    assert len(mutable_reads) <= 2, mutable_reads
    assert TonightPublication.query.count() == 1
    assert TonightIntelligenceSnapshot.query.count() == tonight_intelligence_snapshot_count


def test_v1_missing_writes_nothing(tonight_app, mutable_reads, monkeypatch):
    del mutable_reads[:]
    _forbid_builds(monkeypatch)
    _get(tonight_app)
    assert _writes(mutable_reads) == []
    assert len(mutable_reads) <= 2, mutable_reads
    assert TonightPublication.query.count() == 0
    assert TonightIntelligenceSnapshot.query.count() == 0


def test_serving_module_cannot_build():
    source = inspect.getsource(tonight_v1_serving)
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(f'{node.module}.{alias.name}' for alias in node.names)
    for forbidden in (
        'build_tonight_v1', 'generate_tonight_v1_for_snapshot',
        'generate_tonight_v1_after_publication', 'load_slate_games',
        'build_team_bullpen_context', 'serve_tonight_cached', 'add', 'commit',
    ):
        assert forbidden not in names
    assert imported <= {
        'models.tonight_publication.TonightPublication',
        'services.dashboard_snapshot',
        'services.tonight_read_model.CONTRACT',
        '__future__.annotations',
        'datetime.date',
        'datetime.datetime',
    }


# ── 10-11. Off-day, postponed, doubleheader: stored payload passes through ───

def test_off_day_payload_serves_normally(tonight_app, monkeypatch):
    SlateGame.query.delete()
    db.session.commit()
    row = _generate(tonight_app.snapshot)

    _forbid_builds(monkeypatch)
    response = _get(tonight_app)

    body = response.get_json()
    assert response.status_code == 200
    assert body == row.payload
    assert body['games'] == [] and body['quiet_day'] is True
    assert 'status' not in body
    assert response.headers['ETag'] == f'"{row.content_sha256}"'


@pytest.fixture
def generated_row(tonight_app):
    return _generate(tonight_app.snapshot)


def test_postponed_and_doubleheader_pass_through_unchanged(
    tonight_app, generated_row, monkeypatch,
):
    _forbid_builds(monkeypatch)
    body = _get(tonight_app).get_json()

    assert body == generated_row.payload
    assert [game['game_pk'] for game in body['games']] == [
        game['game_pk'] for game in generated_row.payload['games']
    ]
    games = {game['game_pk']: game for game in body['games']}
    assert games[802]['state'] == 'postponed'
    assert {803, 804} <= set(games)


# ── 12. Schema or read failure ───────────────────────────────────────────────

def test_missing_table_is_a_503_service_error(tonight_app, monkeypatch):
    db.session.remove()
    TonightPublication.__table__.drop(db.engine)
    try:
        _forbid_builds(monkeypatch)
        response = _get(tonight_app)
    finally:
        db.session.remove()
        TonightPublication.__table__.create(db.engine)

    assert response.status_code == 503
    body = response.get_json()
    assert body['status'] == 'error'
    assert body['games'] == [] and body['cards'] == []
    assert response.headers['Cache-Control'] == public_delivery.NO_STORE_CACHE_CONTROL
    assert response.headers['X-BaseballOS-Contract'] == 'tonight_v1'


def test_no_trusted_publication_fails_closed(tonight_app, monkeypatch):
    _generate(tonight_app.snapshot)
    tonight_app.snapshot.is_published = False
    db.session.commit()

    _forbid_builds(monkeypatch)
    body = _assert_unavailable(_get(tonight_app), 'trusted_dashboard_publication_unavailable')

    assert body['current_publication'] is None


def test_original_view_negotiates_the_same_contracts(tonight_app, monkeypatch):
    """Outside production the un-overridden view selects contracts identically."""
    from api import bullpen as bullpen_api
    row = _generate(tonight_app.snapshot)
    _forbid_builds(monkeypatch)

    with tonight_app.app.test_request_context(V1_URL):
        response = bullpen_api.get_tonight_intelligence()
    assert response.get_json() == row.payload
    assert response.headers['ETag'] == f'"{row.content_sha256}"'

    with tonight_app.app.test_request_context(LEGACY_URL + '?contract=garbage'):
        response, status = bullpen_api.get_tonight_intelligence()
    assert status == 400
    assert response.get_json()['parameter'] == 'contract'
