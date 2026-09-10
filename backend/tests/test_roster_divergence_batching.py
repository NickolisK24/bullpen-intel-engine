"""
Semantic equivalence and query-bound tests for the batched roster
cache-divergence scan.

The historical implementation issued one snapshot query per active pitcher.
The batched implementation must produce identical divergences from identical
data while holding the query count flat as the pitcher population grows.
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from sqlalchemy import event
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_run import SyncRun
from services.public_roster_readiness import build_public_roster_readiness
from services.roster_status import (
    STATUS_40_MAN_ONLY,
    STATUS_ACTIVE,
    STATUS_IL_15,
    STATUS_MINORS,
    STATUS_OPTIONED,
    STATUS_UNKNOWN,
)
from services.roster_status_sync import (
    _CACHE_FIELDS,
    latest_roster_status_snapshot_for_pitcher,
    latest_roster_status_snapshots_by_pitcher_id,
    roster_status_cache_divergences,
)
from utils.db import db


OFFICIAL_SOURCE = 'mlb_stats_api:roster_sync:active'
SNAPSHOT_DAY = date(2026, 7, 13)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def reference_roster_status_cache_divergences(team_ids=None):
    """
    Pre-batching reference implementation (one query per pitcher).

    Kept test-only so equivalence against the historical semantics stays
    provable without reintroducing the N+1 into production code.
    """
    query = Pitcher.query.filter(Pitcher.active == True)  # noqa: E712
    if team_ids:
        query = query.filter(Pitcher.team_id.in_(tuple(team_ids)))

    divergences = []
    for pitcher in query.all():
        snapshot = latest_roster_status_snapshot_for_pitcher(pitcher.id)
        if snapshot is None:
            continue
        mismatched = [
            cache_field
            for cache_field, snapshot_field in _CACHE_FIELDS
            if getattr(pitcher, cache_field) != getattr(snapshot, snapshot_field)
        ]
        if mismatched:
            divergences.append({
                'pitcher_id': pitcher.id,
                'mlb_id': pitcher.mlb_id,
                'team_id': pitcher.team_id,
                'snapshot_id': snapshot.id,
                'snapshot_date': snapshot.snapshot_date.isoformat(),
                'mismatched_fields': mismatched,
            })
    return divergences


def _sync_run():
    run = SyncRun(
        job_name='daily_sync',
        status='success',
        stage='published',
        source='github_actions',
        started_at=datetime(2026, 7, 13, 10, 54, 0),
        completed_at=datetime(2026, 7, 13, 11, 0, 0),
    )
    db.session.add(run)
    db.session.commit()
    return run


def _pitcher(
    mlb_id,
    *,
    team_id=142,
    active=True,
    roster_status=STATUS_ACTIVE,
    roster_status_source=OFFICIAL_SOURCE,
    raw_code=None,
    raw_description=None,
):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=f'Pitcher {mlb_id}',
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        position='P',
        active=active,
        roster_status=roster_status,
        roster_status_source=roster_status_source,
        roster_status_raw_code=raw_code,
        roster_status_raw_description=raw_description,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _snapshot(
    pitcher,
    *,
    snapshot_date=SNAPSHOT_DAY,
    roster_status=STATUS_ACTIVE,
    source=OFFICIAL_SOURCE,
    raw_code=None,
    raw_description=None,
    team_id=None,
    sync_run_id=None,
    updated_at=None,
    first_seen_at=None,
):
    timestamp = datetime(2026, 7, 13, 10, 55, 0)
    snapshot = RosterStatusSnapshot(
        pitcher_id=pitcher.id,
        mlb_id=pitcher.mlb_id,
        team_id=team_id if team_id is not None else pitcher.team_id,
        snapshot_date=snapshot_date,
        roster_status=roster_status,
        active_roster=roster_status == STATUS_ACTIVE,
        forty_man_roster=True,
        roster_status_raw_code=raw_code,
        roster_status_raw_description=raw_description,
        source=source,
        sync_run_id=sync_run_id,
        first_seen_at=first_seen_at or timestamp,
        updated_at=updated_at or timestamp,
    )
    db.session.add(snapshot)
    db.session.flush()
    return snapshot


def _matching_snapshot(pitcher, **kwargs):
    return _snapshot(
        pitcher,
        roster_status=pitcher.roster_status,
        source=pitcher.roster_status_source,
        raw_code=pitcher.roster_status_raw_code,
        raw_description=pitcher.roster_status_raw_description,
        **kwargs,
    )


def _normalized(divergences):
    return sorted(
        (
            item['pitcher_id'],
            item['snapshot_id'],
            item['snapshot_date'],
            tuple(item['mismatched_fields']),
        )
        for item in divergences
    )


def _assert_equivalent(team_ids=None):
    batched = roster_status_cache_divergences(team_ids=team_ids)
    reference = reference_roster_status_cache_divergences(team_ids=team_ids)
    assert _normalized(batched) == _normalized(reference)
    assert len(batched) == len(reference)
    return batched


def _seed_equivalence_population(run):
    day_before = SNAPSHOT_DAY - timedelta(days=1)

    # Clean match between cache and latest snapshot.
    clean = _pitcher(700001)
    _matching_snapshot(clean, sync_run_id=run.id)

    # Active cached pitcher with no snapshot at all: skipped, never divergent.
    _pitcher(700002)

    # Snapshot says active while the cache says inactive-family status.
    snapshot_active_cache_il = _pitcher(700003, roster_status=STATUS_IL_15)
    _snapshot(snapshot_active_cache_il, roster_status=STATUS_ACTIVE, sync_run_id=run.id)

    # Cache says active while the official snapshot says off-active statuses.
    for mlb_id, official_status in (
        (700004, STATUS_IL_15),
        (700005, STATUS_MINORS),
        (700006, STATUS_OPTIONED),
        (700007, STATUS_40_MAN_ONLY),
        (700008, STATUS_UNKNOWN),
    ):
        cache_active = _pitcher(mlb_id, roster_status=STATUS_ACTIVE)
        _snapshot(cache_active, roster_status=official_status, sync_run_id=run.id)

    # Traded player: cache already moved to the new team, snapshot rows exist
    # for both teams; only the latest snapshot participates.
    traded = _pitcher(700009, team_id=142)
    _snapshot(
        traded,
        snapshot_date=day_before,
        team_id=133,
        roster_status=STATUS_ACTIVE,
        sync_run_id=run.id,
    )
    _matching_snapshot(traded, sync_run_id=run.id)

    # Team reassignment where the latest snapshot still shows the old club and
    # a divergent status.
    reassigned = _pitcher(700010, team_id=142)
    _snapshot(
        reassigned,
        team_id=133,
        roster_status=STATUS_MINORS,
        sync_run_id=run.id,
    )

    # Multiple snapshots for the same pitcher across dates: latest date wins.
    multi = _pitcher(700011, roster_status=STATUS_ACTIVE)
    _snapshot(multi, snapshot_date=day_before, roster_status=STATUS_MINORS, sync_run_id=run.id)
    _matching_snapshot(multi, sync_run_id=run.id)

    # Same-day correction: two writes on the snapshot day resolved by
    # updated_at recency; the corrected row matches the cache.
    corrected = _pitcher(700012, roster_status=STATUS_ACTIVE)
    stale_write = _snapshot(
        corrected,
        roster_status=STATUS_MINORS,
        sync_run_id=run.id,
        updated_at=datetime(2026, 7, 13, 9, 0, 0),
    )
    # Same pitcher+date is unique, so the correction is an update in
    # production; emulate recency by touching updated_at upward.
    stale_write.roster_status = STATUS_ACTIVE
    stale_write.updated_at = datetime(2026, 7, 13, 11, 30, 0)
    db.session.flush()

    # Null provenance on the snapshot (source retained but no sync_run_id) and
    # a null-source cache mismatch.
    null_provenance = _pitcher(700013, roster_status=STATUS_ACTIVE)
    _snapshot(null_provenance, roster_status=STATUS_ACTIVE, sync_run_id=None)
    null_source_cache = _pitcher(700014, roster_status_source=None)
    _snapshot(null_source_cache, roster_status=STATUS_ACTIVE, sync_run_id=run.id)

    # Inactive pitcher never participates even when the snapshot diverges.
    inactive = _pitcher(700015, active=False, roster_status=STATUS_MINORS)
    _snapshot(inactive, roster_status=STATUS_ACTIVE, sync_run_id=run.id)

    db.session.commit()


def test_batched_divergences_match_reference_semantics(app):
    run = _sync_run()
    _seed_equivalence_population(run)

    batched = _assert_equivalent()

    # The seeded divergence surface is exactly the mismatching pitchers.
    divergent_mlb_ids = {
        db.session.get(Pitcher, item['pitcher_id']).mlb_id for item in batched
    }
    assert divergent_mlb_ids == {
        700003, 700004, 700005, 700006, 700007, 700008, 700010, 700014,
    }
    # Skipped-not-divergent: no-snapshot and inactive pitchers.
    assert 700002 not in divergent_mlb_ids
    assert 700015 not in divergent_mlb_ids


def test_batched_divergences_match_reference_when_team_scoped(app):
    run = _sync_run()
    _seed_equivalence_population(run)
    _assert_equivalent(team_ids=[142])
    _assert_equivalent(team_ids=[133])
    _assert_equivalent(team_ids=[999])


def test_batched_divergences_on_empty_database(app):
    assert roster_status_cache_divergences() == []
    assert reference_roster_status_cache_divergences() == []
    assert latest_roster_status_snapshots_by_pitcher_id([]) == {}


def test_batched_divergences_match_reference_on_large_multi_team_population(app):
    run = _sync_run()
    for index in range(120):
        team_id = 100 + (index % 30)
        pitcher = _pitcher(710000 + index, team_id=team_id)
        if index % 7 == 0:
            _snapshot(pitcher, roster_status=STATUS_MINORS, sync_run_id=run.id)
        elif index % 3 == 0:
            _pitcher(730000 + index, team_id=team_id)  # active, no snapshot
            _matching_snapshot(pitcher, sync_run_id=run.id)
        else:
            _matching_snapshot(pitcher, sync_run_id=run.id)
    db.session.commit()

    batched = _assert_equivalent()
    assert len(batched) == len([i for i in range(120) if i % 7 == 0])


def _seed_ready_population(pitcher_count, team_count=30):
    run = _sync_run()
    for index in range(pitcher_count):
        team_id = 100 + (index % team_count)
        pitcher = _pitcher(720000 + index, team_id=team_id)
        _matching_snapshot(pitcher, sync_run_id=run.id)
    db.session.commit()


def _count_queries(callable_under_test):
    statements = []

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _before_cursor_execute)
    try:
        result = callable_under_test()
    finally:
        event.remove(db.engine, 'before_cursor_execute', _before_cursor_execute)
    return result, len(statements)


READINESS_QUERY_BUDGET = 10


def _readiness_query_count(pitcher_count):
    _seed_ready_population(pitcher_count)
    readiness, query_count = _count_queries(
        lambda: build_public_roster_readiness(
            reference_date=SNAPSHOT_DAY,
            team_id=100,
            scope='team',
        )
    )
    assert readiness['claims_available'] is True
    assert readiness['readiness_state'] == 'ready'
    return query_count


def test_readiness_query_count_is_bounded_at_small_population(app):
    assert _readiness_query_count(10) <= READINESS_QUERY_BUDGET


def test_readiness_query_count_does_not_grow_with_population(app):
    query_count = _readiness_query_count(300)
    assert query_count <= READINESS_QUERY_BUDGET


def test_readiness_query_count_identical_across_population_sizes():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)

    counts = {}
    for population in (10, 300):
        with flask_app.app_context():
            create_test_schema(flask_app)
            try:
                counts[population] = _readiness_query_count(population)
            finally:
                db.session.remove()
                drop_test_schema(flask_app)

    assert counts[10] == counts[300]


def test_large_multi_team_readiness_stays_ready_and_bounded(app):
    _seed_ready_population(300, team_count=30)
    readiness, query_count = _count_queries(
        lambda: build_public_roster_readiness(
            reference_date=SNAPSHOT_DAY,
            scope='league',
        )
    )
    assert readiness['claims_available'] is True
    assert readiness['coverage']['teams_expected'] == 30
    assert readiness['coverage']['teams_covered'] == 30
    assert query_count <= READINESS_QUERY_BUDGET
