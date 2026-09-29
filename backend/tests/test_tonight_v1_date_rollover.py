"""TN-11.8: Tonight editions roll forward by baseball date.

Tonight identity is (reference_date, dashboard_snapshot_id, contract). The
trusted Dashboard snapshot answers "which bullpen state is authoritative"; the
reference date answers "which MLB day is presented". When the calendar rolls
forward while the trusted publication is still current (the Sep 28 off-day to
the Sep 29 Wild Card day in production), the same snapshot owns one immutable
edition per date. Serving presents today's edition only and fails closed when
it does not exist yet; the morning schedule refresh (natural or the governed
``recovery_morning``) creates it. The Dashboard is never republished or
re-dated, and older editions are never touched.
"""

from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from models.dashboard_snapshot import DashboardSnapshot
from models.slate_game import SlateGame
from models.sync_schedule_attempt import SyncScheduleAttempt
from models.tonight_publication import TonightPublication, TonightPublicationImmutable
from services import schedule_ingestion
from services import sync_due
from services import tonight_read_model
from services import tonight_v1_serving
from services.sync_execution_context import (
    MODE_MORNING,
    SOURCE_GITHUB_SCHEDULE,
    SOURCE_INCIDENT_RECOVERY,
    SyncExecutionAuthorizationError,
    validate_execution_context,
)
from tests.test_tonight_v1_read_model import (  # noqa: F401 - pytest fixtures
    BOS,
    DET,
    LAD,
    MIN,
    NYY,
    SF,
    _slate,
    tonight_app,
)
from utils.db import db


V1_URL = '/api/bullpen/intelligence/tonight?contract=tonight_v1'
DEFAULT_URL = '/api/bullpen/intelligence/tonight'
V5_URL = '/api/bullpen/intelligence/tonight?contract=tonight_v5'
CLE, MIL = 114, 158
WILD_CARD_PAIRS = ((DET, NYY), (MIN, BOS), (SF, LAD), (MIL, CLE))
REPO = Path(__file__).resolve().parents[2]


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def rollover(tonight_app, monkeypatch):
    """The production shape: a trusted snapshot whose own date is an off-day.

    ``day1`` is the snapshot's availability date (Sep 28 in production) with no
    games; ``day2`` is the next baseball day (the Sep 29 Wild Card day).
    Legacy Tonight builders and Dashboard publication are forbidden throughout.
    """
    tonight_app.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True
    SlateGame.query.delete()
    db.session.commit()
    day1 = tonight_app.reference_date
    assert tonight_app.snapshot.availability_reference_date == day1

    def forbidden(*_args, **_kwargs):
        raise AssertionError('date rollover reached a legacy or publication writer')

    import services.schedule_tonight_refresh as schedule_refresh
    import services.tonight_intelligence_snapshot as tonight_v5
    from services import dashboard_snapshot
    monkeypatch.setattr(tonight_v5, 'generate_tonight_snapshot_for_date', forbidden)
    monkeypatch.setattr(schedule_refresh, 'refresh_schedule_and_tonight', forbidden)
    monkeypatch.setattr(dashboard_snapshot, 'publish_dashboard_snapshot', forbidden)
    monkeypatch.setattr(dashboard_snapshot, 'build_bullpen_dashboard_snapshot', forbidden)
    monkeypatch.setattr(sync_due.sync_service, 'run_daily_sync', forbidden)
    monkeypatch.setattr(sync_due.sync_service, 'run_postgame_refresh', forbidden)

    schedule = {'games': []}
    monkeypatch.setattr(
        schedule_ingestion.mlb_client, 'get_schedule',
        lambda **_kwargs: deepcopy(schedule['games']),
    )
    today = {'date': day1}
    monkeypatch.setattr(tonight_v1_serving, 'product_current_date', lambda: today['date'])
    return SimpleNamespace(
        env=tonight_app, snapshot=tonight_app.snapshot, schedule=schedule, today=today,
        day1=day1, day2=day1 + timedelta(days=1), day3=day1 + timedelta(days=2),
    )


def _wild_card_games(day):
    """MLB-shaped postseason (gameType F) schedule games for one ET date."""
    games = []
    for index, (away, home) in enumerate(WILD_CARD_PAIRS):
        first_pitch = datetime.combine(day, time(17 + 2 * index, 8))
        games.append({
            'gamePk': 813000 + index,
            'gameType': 'F',
            'seriesDescription': 'Wild Card Series',
            'officialDate': day.isoformat(),
            'gameDate': first_pitch.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'status': {
                'abstractGameState': 'Preview', 'codedGameState': 'S',
                'detailedState': 'Scheduled', 'statusCode': 'S',
            },
            'teams': {
                'away': {'team': {'id': away}},
                'home': {'team': {'id': home}},
            },
            'doubleHeader': 'N',
            'gameNumber': 1,
            'scheduledInnings': 9,
        })
    return games


def _context(day, *, source=SOURCE_INCIDENT_RECOVERY):
    recovery = source == SOURCE_INCIDENT_RECOVERY
    return validate_execution_context(
        mode=MODE_MORNING,
        source=source,
        scheduled_for=f'{day.isoformat()}T14:23:00Z',
        recovery_reason='Tonight still on the prior day' if recovery else None,
        recovery_confirmation='RECOVER' if recovery else None,
        operator='operator' if recovery else None,
        environ={'APP_ENV': 'test'},
    )


def _row(day, snapshot):
    return tonight_read_model.read_tonight_v1(day, snapshot.id)


def _frozen(row):
    return (row.id, row.content_sha256, deepcopy(row.payload), row.generated_at,
            row.reference_date, row.availability_reference_date, row.data_through)


def _published_ids():
    return [
        row.id for row in DashboardSnapshot.query.filter_by(
            snapshot_type='bullpen_dashboard', is_published=True,
        )
    ]


def _get(env, url=V1_URL, **headers):
    return env.app.test_client().get(url, headers=headers)


# ── Builder and generator ────────────────────────────────────────────────────

def test_explicit_date_builder_presents_the_requested_day(rollover):
    rollover.schedule['games'] = _wild_card_games(rollover.day2)
    schedule_ingestion.ingest_schedule(rollover.day2, rollover.day2)
    snapshot = rollover.snapshot

    payload = tonight_read_model.build_tonight_v1(
        snapshot, tonight_read_model.load_slate_games(rollover.day2),
        generated_at=datetime(2026, 9, 29, 14, 30), reference_date=rollover.day2,
    )

    edition = payload['edition']
    assert edition['baseball_date'] == rollover.day2.isoformat()
    # The bullpen authority is never re-dated.
    assert edition['availability_reference_date'] == rollover.day1.isoformat()
    assert edition['data_through'] == snapshot.data_through.isoformat()
    assert edition['publication']['dashboard_snapshot_id'] == snapshot.id
    assert payload['summary']['game_count'] == 4
    assert [game['game_pk'] for game in payload['games']] == [813000, 813001, 813002, 813003]


def test_publication_time_generator_still_uses_the_snapshot_date(rollover):
    snapshot = rollover.snapshot
    _slate(rollover.day1)
    generated_at = datetime(2026, 9, 28, 12, 0)
    implicit = tonight_read_model.build_tonight_v1(
        snapshot, tonight_read_model.load_slate_games(rollover.day1),
        generated_at=generated_at,
    )
    explicit = tonight_read_model.build_tonight_v1(
        snapshot, tonight_read_model.load_slate_games(rollover.day1),
        generated_at=generated_at, reference_date=rollover.day1,
    )
    assert implicit == explicit

    row, outcome = tonight_read_model.generate_tonight_v1_for_snapshot(snapshot)
    assert outcome == 'created'
    assert row.reference_date == row.availability_reference_date == rollover.day1
    assert row.payload['edition']['baseball_date'] == rollover.day1.isoformat()
    assert row.payload['edition']['availability_reference_date'] == rollover.day1.isoformat()


# ── ensure_tonight_v1_for_date ───────────────────────────────────────────────

def test_ensure_for_date_creates_then_reuses_and_never_overwrites(rollover):
    rollover.schedule['games'] = _wild_card_games(rollover.day2)
    schedule_ingestion.ingest_schedule(rollover.day2, rollover.day2)

    first = tonight_read_model.ensure_tonight_v1_for_date(
        rollover.snapshot, rollover.day2, source='test',
    )
    assert first['status'] == 'created'
    assert first['game_count'] == 4
    assert first['reference_date'] == rollover.day2.isoformat()
    assert first['dashboard_snapshot_id'] == rollover.snapshot.id
    row = _row(rollover.day2, rollover.snapshot)
    stored = _frozen(row)

    # The schedule moves on; the stored edition must not.
    game = db.session.get(SlateGame, 813000)
    game.normalized_state = 'live'
    game.status_detailed = 'In Progress'
    game.game_time_utc = game.game_time_utc + timedelta(hours=1)
    db.session.add(SlateGame(
        game_pk=899999, game_date_et=rollover.day2,
        game_time_utc=datetime.combine(rollover.day2, time(23, 0)),
        away_team_id=NYY, home_team_id=BOS, normalized_state='upcoming',
        status_detailed='Scheduled', game_number=1,
    ))
    db.session.commit()

    second = tonight_read_model.ensure_tonight_v1_for_date(
        rollover.snapshot, rollover.day2, source='test',
    )
    assert second['status'] == 'reused'
    assert second['tonight_publication_id'] == row.id
    assert TonightPublication.query.filter_by(reference_date=rollover.day2).count() == 1
    db.session.expire_all()
    assert _frozen(db.session.get(TonightPublication, row.id)) == stored


def test_stored_edition_refuses_in_place_updates(rollover):
    tonight_read_model.ensure_tonight_v1_for_date(
        rollover.snapshot, rollover.day2, source='test',
    )
    row = _row(rollover.day2, rollover.snapshot)
    row.payload = {**row.payload, 'quiet_day': 'mutated'}
    with pytest.raises(TonightPublicationImmutable):
        db.session.commit()
    db.session.rollback()


def test_same_snapshot_owns_one_edition_per_date(rollover):
    publication = tonight_read_model.ensure_tonight_v1_for_publication(
        rollover.snapshot, source='test',
    )
    rolled = tonight_read_model.ensure_tonight_v1_for_date(
        rollover.snapshot, rollover.day2, source='test',
    )
    assert publication['status'] == rolled['status'] == 'created'
    rows = TonightPublication.query.order_by(TonightPublication.reference_date).all()
    assert [(row.reference_date, row.dashboard_snapshot_id) for row in rows] == [
        (rollover.day1, rollover.snapshot.id), (rollover.day2, rollover.snapshot.id),
    ]
    assert {row.data_through for row in rows} == {rollover.snapshot.data_through}
    assert {row.availability_reference_date for row in rows} == {rollover.day1}
    # The publication date's own ensure is the same identity: reused.
    again = tonight_read_model.ensure_tonight_v1_for_date(
        rollover.snapshot, rollover.day1, source='test',
    )
    assert again['status'] == 'reused'
    assert again['tonight_publication_id'] == rows[0].id


@pytest.mark.parametrize('case', ['unpublished', 'pending', 'no_date', 'disabled', 'missing'])
def test_ensure_for_date_skips_without_a_trusted_publication_or_date(rollover, case):
    snapshot = rollover.snapshot
    reference_date = rollover.day2
    if case == 'unpublished':
        snapshot = SimpleNamespace(**{**vars(snapshot), 'is_published': False})
    elif case == 'pending':
        snapshot = SimpleNamespace(
            id=snapshot.id, is_published=True, status='pending',
            data_through=snapshot.data_through,
            availability_reference_date=snapshot.availability_reference_date,
        )
    elif case == 'no_date':
        reference_date = None
    elif case == 'disabled':
        rollover.env.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = False
    else:
        snapshot = None

    result = tonight_read_model.ensure_tonight_v1_for_date(
        snapshot, reference_date, source='test',
    )

    assert result['status'] == 'skipped'
    assert result['reason'] == {
        'unpublished': 'publication_not_trusted',
        'pending': 'publication_not_trusted',
        'no_date': 'reference_date_missing',
        'disabled': 'tonight_v1_projection_disabled',
        'missing': 'trusted_publication_missing',
    }[case]
    assert TonightPublication.query.count() == 0


def test_ensure_for_date_never_raises(rollover, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError('builder failed')

    monkeypatch.setattr(tonight_read_model, 'build_tonight_v1', broken)
    result = tonight_read_model.ensure_tonight_v1_for_date(
        rollover.snapshot, rollover.day2, source='test',
    )
    assert result == {
        'status': 'failed', 'error': 'RuntimeError',
        'dashboard_snapshot_id': rollover.snapshot.id,
        'reference_date': rollover.day2.isoformat(),
        'data_through': rollover.snapshot.data_through.isoformat(),
        'availability_reference_date': rollover.day1.isoformat(),
    }
    assert TonightPublication.query.count() == 0


def test_ensure_for_date_logs_one_concise_line(rollover, caplog):
    import logging
    with caplog.at_level(logging.INFO, logger=tonight_read_model.logger.name):
        tonight_read_model.ensure_tonight_v1_for_date(
            rollover.snapshot, rollover.day2, source='morning_test',
        )
    lines = [r.getMessage() for r in caplog.records if 'date ensure' in r.getMessage()]
    assert len(lines) == 1
    assert lines[0].startswith(
        f'tonight_v1 date ensure source=morning_test snapshot_id={rollover.snapshot.id} '
        f'reference_date={rollover.day2.isoformat()} status=created '
    )
    assert lines[0].endswith('legacy_tonight_v5=not_generated')


# ── Production-shaped rollovers through the real morning path ────────────────

def test_off_day_to_wild_card_day_rolls_forward_without_republishing(rollover):
    """Sep 28 off-day (snapshot 4094, 0 games) -> Sep 29 Wild Card day."""
    env, snapshot = rollover.env, rollover.snapshot
    published_before = _published_ids()
    snapshots_before = DashboardSnapshot.query.count()

    # Day 1: the publication-date edition exists and is empty.
    day1 = tonight_read_model.ensure_tonight_v1_for_publication(snapshot, source='hook')
    assert day1['status'] == 'created'
    day1_row = _row(rollover.day1, snapshot)
    assert day1_row.payload['summary']['game_count'] == 0
    day1_frozen = _frozen(day1_row)
    body = _get(env).get_json()
    assert body['edition']['baseball_date'] == rollover.day1.isoformat()
    assert body['quiet_day'] is True

    # Day 2 begins: yesterday's edition is never served as today's.
    rollover.today['date'] = rollover.day2
    for url in (V1_URL, DEFAULT_URL):
        stale = _get(env, url).get_json()
        assert stale['status'] == 'unavailable'
        assert stale['reason_codes'] == [tonight_v1_serving.REASON_ROW_MISSING]
        assert stale['edition'] is None

    # The morning refresh ingests the Wild Card schedule and rolls forward.
    rollover.schedule['games'] = _wild_card_games(rollover.day2)
    result = sync_due.run_due_sync(env.app, _context(rollover.day2))

    assert result['status'] == 'executed'
    tonight = result['publication_proof']['tonight_v1']
    assert tonight['status'] == 'created'
    assert tonight['reference_date'] == rollover.day2.isoformat()
    assert tonight['dashboard_snapshot_id'] == snapshot.id
    assert tonight['game_count'] == 4
    edition = result['sync']['tonight_edition']
    assert edition == {
        'schedule_date': rollover.day2.isoformat(),
        'trusted_snapshot_id': snapshot.id,
        'tonight_publication_id': tonight['tonight_publication_id'],
        'reference_date': rollover.day2.isoformat(),
        'status': 'created',
        'game_count': 4,
    }
    assert result['sync']['legacy_tonight_v5'] == 'not_generated'

    day2_row = _row(rollover.day2, snapshot)
    assert day2_row.dashboard_snapshot_id == snapshot.id
    assert day2_row.data_through == snapshot.data_through
    assert day2_row.availability_reference_date == rollover.day1
    assert day2_row.payload['edition']['baseball_date'] == rollover.day2.isoformat()
    assert day2_row.payload['summary']['game_count'] == 4
    # Postseason games reached the edition through real schedule ingestion.
    assert {game['game_pk'] for game in day2_row.payload['games']} == {
        813000, 813001, 813002, 813003,
    }
    db.session.expire_all()
    assert _frozen(db.session.get(TonightPublication, day1_row.id)) == day1_frozen

    for url in (V1_URL, DEFAULT_URL):
        response = _get(env, url)
        served = response.get_json()
        assert served['edition']['baseball_date'] == rollover.day2.isoformat()
        assert served['edition']['data_through'] == snapshot.data_through.isoformat()
        assert served['summary']['game_count'] == 4
        assert response.headers['ETag'] == f'"{day2_row.content_sha256}"'
        assert response.headers['X-BaseballOS-Snapshot-Id'] == str(snapshot.id)

    # No Dashboard republish, no re-dating, no new snapshot.
    assert _published_ids() == published_before
    assert DashboardSnapshot.query.count() == snapshots_before
    db.session.refresh(snapshot)
    assert snapshot.availability_reference_date == rollover.day1


def test_wild_card_day_to_off_day_gets_an_empty_edition(rollover):
    rollover.schedule['games'] = _wild_card_games(rollover.day2)
    first = sync_due.run_due_sync(rollover.env.app, _context(rollover.day2))
    assert first['publication_proof']['tonight_v1']['game_count'] == 4
    day2_frozen = _frozen(_row(rollover.day2, rollover.snapshot))

    rollover.schedule['games'] = []
    second = sync_due.run_due_sync(rollover.env.app, _context(rollover.day3))

    tonight = second['publication_proof']['tonight_v1']
    assert tonight['status'] == 'created'
    assert tonight['game_count'] == 0
    day3_row = _row(rollover.day3, rollover.snapshot)
    assert day3_row.payload['quiet_day'] is True
    assert day3_row.dashboard_snapshot_id == rollover.snapshot.id
    db.session.expire_all()
    assert _frozen(_row(rollover.day2, rollover.snapshot)) == day2_frozen


def test_multi_day_jump_creates_only_the_requested_date(rollover):
    tonight_read_model.ensure_tonight_v1_for_publication(rollover.snapshot, source='hook')
    rollover.schedule['games'] = _wild_card_games(rollover.day3)

    sync_due.run_due_sync(rollover.env.app, _context(rollover.day3))

    dates = [row.reference_date for row in TonightPublication.query.order_by(
        TonightPublication.reference_date)]
    assert dates == [rollover.day1, rollover.day3]


def test_recovery_morning_is_idempotent_and_never_ingests_or_publishes(rollover):
    rollover.schedule['games'] = _wild_card_games(rollover.day2)
    published_before = _published_ids()

    first = sync_due.run_due_sync(rollover.env.app, _context(rollover.day2))
    row = _row(rollover.day2, rollover.snapshot)
    stored = _frozen(row)
    second = sync_due.run_due_sync(rollover.env.app, _context(rollover.day2))

    assert first['status'] == second['status'] == 'executed'
    assert first['publication_proof']['tonight_v1']['status'] == 'created'
    assert second['publication_proof']['tonight_v1']['status'] == 'reused'
    assert second['publication_proof']['tonight_v1']['tonight_publication_id'] == row.id
    assert TonightPublication.query.filter_by(reference_date=rollover.day2).count() == 1
    db.session.expire_all()
    assert _frozen(db.session.get(TonightPublication, row.id)) == stored
    # run_daily_sync / run_postgame_refresh / publication are forbidden by the
    # fixture: reaching any of them would have raised.
    assert _published_ids() == published_before
    attempts = SyncScheduleAttempt.query.filter_by(mode=MODE_MORNING).all()
    assert [attempt.source for attempt in attempts] == [SOURCE_INCIDENT_RECOVERY] * 2
    assert all(attempt.recovery_reason for attempt in attempts)


def test_recovery_morning_runs_after_a_satisfied_natural_morning(rollover):
    """The natural morning may have executed before the fix; recovery re-runs."""
    rollover.schedule['games'] = _wild_card_games(rollover.day2)
    natural = sync_due.run_due_sync(
        rollover.env.app, _context(rollover.day2, source=SOURCE_GITHUB_SCHEDULE),
    )
    assert natural['status'] == 'executed'
    assert natural['publication_proof']['tonight_v1']['status'] == 'created'
    row_id = natural['publication_proof']['tonight_v1']['tonight_publication_id']

    duplicate = sync_due.run_due_sync(
        rollover.env.app, _context(rollover.day2, source=SOURCE_GITHUB_SCHEDULE),
    )
    assert duplicate['status'] == 'already_satisfied'

    recovery = sync_due.run_due_sync(rollover.env.app, _context(rollover.day2))
    assert recovery['status'] == 'executed'
    assert recovery['publication_proof']['tonight_v1']['status'] == 'reused'
    assert recovery['publication_proof']['tonight_v1']['tonight_publication_id'] == row_id


# ── Serving: current date only, overlay and ETag preserved ───────────────────

def test_serving_selects_the_current_date_edition(rollover):
    publication = tonight_read_model.ensure_tonight_v1_for_publication(
        rollover.snapshot, source='hook',
    )
    rollover.schedule['games'] = _wild_card_games(rollover.day2)
    schedule_ingestion.ingest_schedule(rollover.day2, rollover.day2)
    rolled = tonight_read_model.ensure_tonight_v1_for_date(
        rollover.snapshot, rollover.day2, source='test',
    )

    rollover.today['date'] = rollover.day1
    body = _get(rollover.env).get_json()
    assert body['edition']['baseball_date'] == rollover.day1.isoformat()
    assert _get(rollover.env).headers['ETag'] == (
        f'"{db.session.get(TonightPublication, publication["tonight_publication_id"]).content_sha256}"'
    )

    rollover.today['date'] = rollover.day2
    body = _get(rollover.env).get_json()
    assert body['edition']['baseball_date'] == rollover.day2.isoformat()
    assert body['summary']['game_count'] == 4

    # A date with no edition fails closed; neither neighbor is served.
    rollover.today['date'] = rollover.day3
    body = _get(rollover.env).get_json()
    assert body['status'] == 'unavailable'
    assert body['reason_codes'] == [tonight_v1_serving.REASON_ROW_MISSING]
    assert rolled['status'] == 'created'


def test_rolled_forward_edition_keeps_the_game_state_overlay_and_etag(rollover):
    rollover.schedule['games'] = _wild_card_games(rollover.day2)
    schedule_ingestion.ingest_schedule(rollover.day2, rollover.day2)
    tonight_read_model.ensure_tonight_v1_for_date(
        rollover.snapshot, rollover.day2, source='test',
    )
    row = _row(rollover.day2, rollover.snapshot)
    stored = deepcopy(row.payload)
    rollover.today['date'] = rollover.day2

    game = db.session.get(SlateGame, 813000)
    game.normalized_state = 'live'
    game.status_detailed = 'In Progress'
    game.last_synced = game.last_synced + timedelta(minutes=30)
    db.session.commit()

    first = _get(rollover.env)
    second = _get(rollover.env)
    served = {g['game_pk']: g for g in first.get_json()['games']}
    assert served[813000]['state'] == 'live'
    assert served[813001]['state'] == 'scheduled'
    # Frozen TeamSide content is untouched by the overlay.
    stored_game = next(g for g in stored['games'] if g['game_pk'] == 813000)
    assert served[813000]['away'] == stored_game['away']
    assert served[813000]['home'] == stored_game['home']
    etag = first.headers['ETag']
    assert etag == second.headers['ETag'] != f'"{row.content_sha256}"'
    assert etag.startswith('"') and not etag.startswith('W/')
    assert _get(rollover.env, **{'If-None-Match': etag}).status_code == 304
    db.session.expire_all()
    assert db.session.get(TonightPublication, row.id).payload == stored


def test_v5_compatibility_is_unchanged_by_rollover(rollover):
    tonight_read_model.ensure_tonight_v1_for_date(
        rollover.snapshot, rollover.day2, source='test',
    )
    rollover.today['date'] = rollover.day2
    response = _get(rollover.env, V5_URL)
    assert response.status_code == 200
    assert response.headers['Deprecation'] == 'true'
    assert response.headers['X-BaseballOS-Contract'] == 'tonight_v5'
    assert response.get_json().get('contract') != 'tonight_v1'


def test_identity_check_rejects_a_row_for_another_date(rollover):
    tonight_read_model.ensure_tonight_v1_for_date(
        rollover.snapshot, rollover.day2, source='test',
    )
    row = _row(rollover.day2, rollover.snapshot)
    projection = SimpleNamespace(
        id=rollover.snapshot.id, sync_run_id=rollover.snapshot.sync_run_id,
        data_through=rollover.snapshot.data_through,
        availability_reference_date=rollover.snapshot.availability_reference_date,
    )
    assert tonight_v1_serving.identity_mismatch(
        row, projection, reference_date=rollover.day2,
    ) is None
    assert tonight_v1_serving.identity_mismatch(
        row, projection, reference_date=rollover.day3,
    ) == 'reference_date'
    moved = SimpleNamespace(**{**vars(projection), 'availability_reference_date': rollover.day2})
    assert tonight_v1_serving.identity_mismatch(
        row, moved, reference_date=rollover.day2,
    ) == 'reference_date'


# ── Date authority and governance ────────────────────────────────────────────

@pytest.mark.parametrize('scheduled_for, expected', [
    ('2026-09-29T14:23:00Z', '2026-09-29'),   # morning, 10:23 ET
    ('2026-09-29T10:05:00Z', '2026-09-29'),   # daily, 06:05 ET
    ('2026-09-30T02:11:00Z', '2026-09-29'),   # postgame, 22:11 ET the prior day
    ('2026-09-30T04:11:00Z', '2026-09-30'),   # postgame, 00:11 ET
])
def test_lane_reference_date_is_the_intended_eastern_date(scheduled_for, expected):
    context = SimpleNamespace(
        scheduled_for=datetime.fromisoformat(scheduled_for.replace('Z', '+00:00')),
    )
    assert sync_due.tonight_reference_date(context).isoformat() == expected


def _production_env(**overrides):
    return {
        'APP_ENV': 'production', 'GITHUB_ACTIONS': 'true',
        'GITHUB_EVENT_NAME': 'workflow_dispatch',
        'GITHUB_REF': 'refs/heads/main',
        'GITHUB_REPOSITORY': 'NickolisK24/bullpen-intel-engine',
        **overrides,
    }


@pytest.mark.parametrize('missing, reason', [
    ('recovery_reason', 'recovery_reason_required'),
    ('recovery_confirmation', 'recovery_confirmation_required'),
    ('operator', 'recovery_operator_required'),
])
def test_recovery_morning_keeps_recovery_governance(missing, reason):
    kwargs = {
        'mode': 'morning', 'source': SOURCE_INCIDENT_RECOVERY,
        'scheduled_for': '2026-09-29T15:00:00Z',
        'recovery_reason': 'Tonight still on Sep 28',
        'recovery_confirmation': 'RECOVER', 'operator': 'operator',
        'environ': _production_env(),
    }
    validate_execution_context(**kwargs)
    kwargs[missing] = ''
    with pytest.raises(SyncExecutionAuthorizationError) as error:
        validate_execution_context(**kwargs)
    assert error.value.reason == reason
    if missing == 'recovery_confirmation':
        # The confirmation is exact; a lowercase token is not consent.
        kwargs[missing] = 'recover'
        with pytest.raises(SyncExecutionAuthorizationError):
            validate_execution_context(**kwargs)


def test_workflow_dispatches_recovery_morning_on_the_morning_path_only():
    workflow = yaml.safe_load(
        (REPO / '.github/workflows/baseballos-sync.yml').read_text(encoding='utf-8'),
    )
    options = workflow[True]['workflow_dispatch']['inputs']['mode']['options']
    assert 'recovery_morning' in options
    steps = {step.get('name'): step for step in workflow['jobs']['public-sync']['steps']}
    morning = steps['Run morning slate schedule refresh']
    assert "inputs.mode == 'recovery_morning'" in morning['if']
    assert "github.event.schedule == '23 14 * * *'" in morning['if']
    assert morning['env']['EXECUTION_SOURCE'] == (
        "${{ github.event_name == 'schedule' && 'github_schedule' || 'incident_recovery' }}"
    )
    assert '--mode morning' in morning['run']
    assert '--confirm-recovery "$CONFIRM_RECOVERY"' in morning['run']
    assert '--recovery-reason "$RECOVERY_REASON"' in morning['run']
    for name in ('Run direct daily sync', 'Run direct postgame refresh', 'Run explicit backfill'):
        assert 'recovery_morning' not in steps[name]['if'], name
    for job_name, job in workflow['jobs'].items():
        if job_name == 'public-sync':
            continue
        assert 'recovery_morning' not in str(job.get('if', '')), job_name
