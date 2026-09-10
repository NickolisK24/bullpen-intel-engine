from datetime import date, datetime

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.prospect  # noqa: F401
import models.fatigue_score  # noqa: F401
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services import source_readiness
from services.roster_status import (
    STATUS_ACTIVE,
    STATUS_IL_15,
    STATUS_MINORS,
    STATUS_UNKNOWN,
)
from services.roster_status_sync import (
    ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
    ROSTER_STATUS_FETCH_ENTITY_TYPE,
    ROSTER_STATUS_IDENTITY_ENTITY_TYPE,
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_FULL,
    roster_status_cache_divergence_count,
    sync_roster_statuses,
)
from utils.db import db


class FakeRosterClient:
    def __init__(self, rosters):
        self.rosters = rosters

    def get_team_roster(self, team_id, roster_type='pitchers', **_kwargs):
        value = self.rosters.get((team_id, roster_type), [])
        if isinstance(value, Exception):
            raise value
        return list(value)


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


def _run(started_at=datetime(2026, 6, 7, 12, 0, 0)):
    run = SyncRun(
        job_name='daily_sync',
        status='success',
        source='test',
        started_at=started_at,
        completed_at=started_at,
    )
    db.session.add(run)
    db.session.commit()
    return run


def _pitcher(name='Snapshot Arm', mlb_id=700001, team_id=113):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        position='P',
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _entry(player_id=700001, name='Snapshot Arm', *, status=None, two_way=None):
    entry = {
        'person': {
            'id': player_id,
            'fullName': name,
            'primaryPosition': {
                'code': '1',
                'abbreviation': 'P',
                'name': 'Pitcher',
                'type': 'Pitcher',
            },
        },
        'position': {
            'code': '1',
            'abbreviation': 'P',
            'name': 'Pitcher',
            'type': 'Pitcher',
        },
    }
    if status is not None:
        entry['status'] = status
    if two_way is not None:
        entry['person']['twoWayPlayer'] = two_way
    return entry


def _active_rosters(player_id=700001, *, two_way=None):
    return {
        (113, ROSTER_TYPE_ACTIVE): [
            _entry(player_id, status={'code': 'A', 'description': 'Active'}, two_way=two_way),
        ],
        (113, ROSTER_TYPE_40_MAN): [
            _entry(player_id, status={'code': 'A', 'description': 'Active'}, two_way=two_way),
        ],
        (113, ROSTER_TYPE_FULL): [
            _entry(player_id, status='Active', two_way=two_way),
        ],
    }


def test_successful_roster_sync_writes_dated_snapshot_with_provenance(app):
    with app.app_context():
        pitcher = _pitcher()
        run = _run()
        run_id = run.id

        result = sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient(_active_rosters(two_way=True)),
            timestamp=datetime(2026, 6, 7, 12, 0, 0),
            snapshot_date=date(2026, 6, 7),
            sync_run_id=run.id,
        )
        snapshot = RosterStatusSnapshot.query.one()
        updated = db.session.get(Pitcher, pitcher.id)

    assert result['snapshots_created'] == 1
    assert result['pitchers_refreshed'] == 1
    assert snapshot.snapshot_date == date(2026, 6, 7)
    assert snapshot.roster_status == STATUS_ACTIVE
    assert snapshot.active_roster is True
    assert snapshot.forty_man_roster is True
    assert snapshot.position_code == '1'
    assert snapshot.position_name == 'Pitcher'
    assert snapshot.position_type == 'Pitcher'
    assert snapshot.two_way_eligible is True
    assert snapshot.source == 'mlb_stats_api:roster_sync:active'
    assert snapshot.sync_run_id == run_id
    assert snapshot.first_seen_at == datetime(2026, 6, 7, 12, 0, 0)
    assert updated.roster_status == STATUS_ACTIVE
    assert updated.roster_status_source == snapshot.source
    assert 'roster_status_snapshots' not in updated.to_dict()


def test_prior_snapshots_remain_historical_and_latest_snapshot_wins_cache(app):
    with app.app_context():
        pitcher = _pitcher()
        first_run = _run(datetime(2026, 6, 7, 12, 0, 0))
        second_run = _run(datetime(2026, 6, 8, 12, 0, 0))
        sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient(_active_rosters()),
            timestamp=datetime(2026, 6, 7, 12, 0, 0),
            snapshot_date=date(2026, 6, 7),
            sync_run_id=first_run.id,
        )
        sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient({
                (113, ROSTER_TYPE_FULL): [_entry(status='Minors')],
            }),
            timestamp=datetime(2026, 6, 8, 12, 0, 0),
            snapshot_date=date(2026, 6, 8),
            sync_run_id=second_run.id,
        )
        snapshots = RosterStatusSnapshot.query.order_by(
            RosterStatusSnapshot.snapshot_date
        ).all()
        updated = db.session.get(Pitcher, pitcher.id)

    assert [snapshot.roster_status for snapshot in snapshots] == [
        STATUS_ACTIVE,
        STATUS_MINORS,
    ]
    assert updated.roster_status == STATUS_MINORS
    assert updated.roster_status_source == 'mlb_stats_api:roster_sync:fullRoster'


def test_repeated_same_day_sync_is_idempotent_without_duplicate_snapshot(app):
    with app.app_context():
        _pitcher()
        run = _run()
        first = sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient(_active_rosters()),
            timestamp=datetime(2026, 6, 7, 12, 0, 0),
            snapshot_date=date(2026, 6, 7),
            sync_run_id=run.id,
        )
        second = sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient(_active_rosters()),
            timestamp=datetime(2026, 6, 7, 13, 0, 0),
            snapshot_date=date(2026, 6, 7),
            sync_run_id=run.id,
        )
        snapshot = RosterStatusSnapshot.query.one()
        snapshot_count = RosterStatusSnapshot.query.count()

    assert first['snapshots_created'] == 1
    assert second['snapshots_created'] == 0
    assert second['snapshots_unchanged'] == 1
    assert snapshot_count == 1
    assert snapshot.correction_count == 0


def test_conflicting_same_day_status_corrects_snapshot_with_provenance(app):
    with app.app_context():
        pitcher = _pitcher()
        run = _run()
        sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient(_active_rosters()),
            timestamp=datetime(2026, 6, 7, 12, 0, 0),
            snapshot_date=date(2026, 6, 7),
            sync_run_id=run.id,
        )
        result = sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient({
                (113, ROSTER_TYPE_40_MAN): [
                    _entry(status={'code': 'D15', 'description': '15-day IL'}),
                ],
            }),
            timestamp=datetime(2026, 6, 7, 13, 0, 0),
            snapshot_date=date(2026, 6, 7),
            sync_run_id=run.id,
        )
        snapshot = RosterStatusSnapshot.query.one()
        updated = db.session.get(Pitcher, pitcher.id)

    assert result['snapshots_corrected'] == 1
    assert snapshot.roster_status == STATUS_IL_15
    assert snapshot.correction_count == 1
    assert snapshot.last_corrected_at == datetime(2026, 6, 7, 13, 0, 0)
    assert snapshot.correction_source == 'mlb_stats_api:roster_sync:40Man'
    assert updated.roster_status == STATUS_IL_15


def test_fetch_failure_degrades_readiness_without_marking_cache_fresh(app):
    with app.app_context():
        pitcher = _pitcher()
        pitcher.roster_status = STATUS_ACTIVE
        pitcher.roster_status_source = 'prior_sync'
        db.session.commit()

        result = sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient({
                (113, ROSTER_TYPE_ACTIVE): RuntimeError('roster unavailable'),
            }),
            timestamp=datetime(2026, 6, 7, 12, 0, 0),
        )
        updated = db.session.get(Pitcher, pitcher.id)
        readiness = source_readiness.source_readiness_payload(
            reference_date=date(2026, 6, 7),
        )['families']['roster_status_snapshots']
        failure_count = SyncFailure.query.filter_by(
            entity_type=ROSTER_STATUS_FETCH_ENTITY_TYPE,
            resolved=False,
        ).count()

    assert result['errors'] == 1
    assert result['records_failed'] == 1
    assert result['pitchers_refreshed'] == 0
    assert updated.roster_status == STATUS_ACTIVE
    assert updated.roster_status_source == 'prior_sync'
    assert failure_count == 1
    assert readiness['status'] == source_readiness.UNAVAILABLE
    assert 'source_unavailable' in readiness['reason_codes']


def test_unknown_player_identity_dead_letters_and_fails_closed(app):
    with app.app_context():
        _pitcher()
        result = sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient({
                (113, ROSTER_TYPE_ACTIVE): [
                    {'person': {'fullName': 'No Identity'}, 'position': {'code': '1'}},
                ],
            }),
            timestamp=datetime(2026, 6, 7, 12, 0, 0),
            snapshot_date=date(2026, 6, 7),
        )
        failure = SyncFailure.query.filter_by(
            entity_type=ROSTER_STATUS_IDENTITY_ENTITY_TYPE,
            resolved=False,
        ).one()
        snapshot = RosterStatusSnapshot.query.one()

    assert result['records_failed'] == 1
    assert failure.payload['reason'] == 'missing_player_identity'
    assert snapshot.roster_status == STATUS_UNKNOWN
    assert snapshot.active_roster is None


def test_conflicting_same_day_team_snapshot_dead_letters_without_cache_update(app):
    with app.app_context():
        pitcher = _pitcher(team_id=113)
        run = _run()
        sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient(_active_rosters()),
            timestamp=datetime(2026, 6, 7, 12, 0, 0),
            snapshot_date=date(2026, 6, 7),
            sync_run_id=run.id,
        )
        pitcher.team_id = 135
        db.session.commit()

        result = sync_roster_statuses(
            team_ids=[135],
            client=FakeRosterClient({
                (135, ROSTER_TYPE_ACTIVE): [_entry()],
            }),
            timestamp=datetime(2026, 6, 7, 13, 0, 0),
            snapshot_date=date(2026, 6, 7),
            sync_run_id=run.id,
        )
        failure = SyncFailure.query.filter_by(
            entity_type=ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
            resolved=False,
        ).one()
        updated = db.session.get(Pitcher, pitcher.id)
        snapshot_count = RosterStatusSnapshot.query.count()

    assert result['snapshot_conflicts'] == 1
    assert result['records_failed'] == 1
    assert failure.payload['existing_team_id'] == 113
    assert failure.payload['incoming_team_id'] == 135
    assert updated.roster_status == STATUS_ACTIVE
    assert snapshot_count == 1


def test_stale_snapshot_and_cache_divergence_degrade_readiness(app):
    with app.app_context():
        pitcher = _pitcher()
        run = _run(datetime(2026, 6, 1, 12, 0, 0))
        sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient(_active_rosters()),
            timestamp=datetime(2026, 6, 1, 12, 0, 0),
            snapshot_date=date(2026, 6, 1),
            sync_run_id=run.id,
        )
        stale = source_readiness.source_readiness_payload(
            reference_date=date(2026, 6, 3),
        )['families']['roster_status_snapshots']

        pitcher.roster_status = STATUS_UNKNOWN
        db.session.commit()
        divergent = source_readiness.source_readiness_payload(
            reference_date=date(2026, 6, 1),
        )['families']['roster_status_snapshots']

    assert stale['status'] == source_readiness.STALE
    assert 'source_stale' in stale['reason_codes']
    assert roster_status_cache_divergence_count() == 1
    assert divergent['status'] == source_readiness.DEGRADED
    assert 'roster_status_cache_divergence' in divergent['reason_codes']
