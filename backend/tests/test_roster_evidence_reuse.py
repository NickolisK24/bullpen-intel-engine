"""
Same-run roster evidence reuse across the two governed roster consumers.

Team assignment and roster status derive different governed facts from the same
official MLB roster feeds. One daily run used to fetch all four roster views for
all thirty clubs twice — once per consumer — for 240 roster requests. These tests
pin that one run now fetches each view once and that both consumers reach exactly
the same conclusions from the shared evidence as from independent fetches,
including on fetch failure.

Every classification test runs twice: once with each consumer fetching for itself
(the historical shape) and once with both consumers reading one run's evidence.
The expectations are written once, so the two modes are proven equivalent.

These use fake MLB roster payloads and in-memory SQLite; no network calls.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.prospect  # noqa: F401
import services.sync as sync_service
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services import sync_metadata
from services.mlb_api import MlbApiFetchError, mlb_client
from services.roster_evidence import (
    CONSUMER_ROSTER_STATUS,
    CONSUMER_TEAM_ASSIGNMENT,
    ROSTER_TYPES,
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_FULL,
    ROSTER_TYPE_NON_ROSTER,
    build_run_roster_evidence,
)
from services.roster_status import (
    STATUS_40_MAN_ONLY,
    STATUS_ACTIVE,
    STATUS_DFA,
    STATUS_IL_15,
    STATUS_MINORS,
    STATUS_NON_ROSTER,
    STATUS_UNKNOWN,
)
from services.roster_status_sync import (
    ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
    ROSTER_STATUS_FETCH_ENTITY_TYPE,
    build_team_roster_status_index,
    sync_roster_statuses,
)
from services.team_assignment_sync import (
    MLB_TEAM_IDS,
    TEAM_ASSIGNMENT_ASSIGNED,
    TEAM_ASSIGNMENT_NO_ORGANIZATION,
    TEAM_ASSIGNMENT_UNKNOWN,
    build_team_assignment_index,
    sync_team_assignments,
)
from utils.db import db


REFERENCE_DATE = date(2026, 8, 15)
REFERENCE_TIME = datetime(2026, 8, 15, 12, 0, 0)

TEAM_FIXTURES = {
    113: ('Cincinnati Reds', 'CIN'),
    116: ('Detroit Tigers', 'DET'),
    135: ('San Diego Padres', 'SD'),
    141: ('Toronto Blue Jays', 'TOR'),
    143: ('Philadelphia Phillies', 'PHI'),
}


class CountingRosterClient:
    """Fake Stats API client that records every roster/team request it serves."""

    def __init__(self, rosters=None, player_info=None, teams=None):
        self.rosters = rosters or {}
        self.player_info = player_info or {}
        self.teams = teams if teams is not None else [
            {'id': team_id, 'name': name, 'abbreviation': abbreviation}
            for team_id, (name, abbreviation) in TEAM_FIXTURES.items()
        ]
        self.roster_calls = []
        self.team_calls = 0
        self.player_info_calls = []

    def get_all_teams(self):
        self.team_calls += 1
        if isinstance(self.teams, Exception):
            raise self.teams
        return list(self.teams)

    def get_team_roster(self, team_id, roster_type='pitchers', **_kwargs):
        self.roster_calls.append((team_id, roster_type))
        value = self.rosters.get((team_id, roster_type), [])
        if isinstance(value, Exception):
            raise value
        return list(value)

    def get_player_info(self, player_id):
        self.player_info_calls.append(player_id)
        value = self.player_info.get(player_id)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


@pytest.fixture(params=[False, True], ids=['independent_fetches', 'shared_run_evidence'])
def shares_evidence(request):
    """Run every equivalence test in both fetch shapes."""
    return request.param


def run_evidence(client, shares):
    """One run's shared evidence, or None when each consumer fetches for itself."""
    return build_run_roster_evidence(client=client) if shares else None


def roster_entry(player_id, name='Fixture Arm', status=None, two_way=None):
    entry = {
        'person': {'id': player_id, 'fullName': name},
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


def seed_pitcher(name, mlb_id, team_id=113):
    team_name, team_abbreviation = TEAM_FIXTURES.get(team_id, (f'Team {team_id}', f'T{team_id}'))
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=team_name,
        team_abbreviation=team_abbreviation,
        position='RP',
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=mlb_id * 10,
        game_date=REFERENCE_DATE - timedelta(days=1),
        pitches_thrown=12,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        games_started=0,
        game_type='R',
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        raw_score=10.0,
        risk_level='LOW',
        calculated_at=REFERENCE_TIME,
    ))
    db.session.commit()
    return pitcher


def seed_sync_run(timestamp=REFERENCE_TIME):
    run = SyncRun(
        job_name='daily_sync',
        status='success',
        stage='complete',
        source='test_fixture',
        started_at=timestamp,
        completed_at=timestamp,
    )
    db.session.add(run)
    db.session.flush()
    return run


# ── One-run fetch count ──────────────────────────────────────


def test_one_run_fetches_each_roster_view_once_for_both_consumers(app):
    """30 teams x 4 roster views = 120 roster requests, not 240."""
    with app.app_context():
        for offset, team_id in enumerate(MLB_TEAM_IDS):
            seed_pitcher(f'Arm {team_id}', 800000 + offset, team_id=team_id)
        fake = CountingRosterClient(
            rosters={
                (team_id, ROSTER_TYPE_ACTIVE): [
                    roster_entry(800000 + offset, f'Arm {team_id}', status='Active'),
                ]
                for offset, team_id in enumerate(MLB_TEAM_IDS)
            },
            teams=[
                {'id': team_id, 'name': f'Team {team_id}', 'abbreviation': f'T{team_id}'}
                for team_id in MLB_TEAM_IDS
            ],
        )
        evidence = build_run_roster_evidence(client=fake)

        sync_team_assignments(client=fake, timestamp=REFERENCE_TIME, evidence=evidence)
        assignment_calls = len(fake.roster_calls)
        sync_roster_statuses(
            client=fake,
            timestamp=REFERENCE_TIME,
            snapshot_date=REFERENCE_DATE,
            evidence=evidence,
        )
        summary = evidence.summary()

    assert assignment_calls == 120
    assert len(fake.roster_calls) == 120
    assert len(set(fake.roster_calls)) == 120
    assert fake.team_calls == 1
    assert summary['teams_fetched'] == 30
    assert summary['roster_types_fetched'] == sorted(ROSTER_TYPES)
    assert summary['roster_requests'] == 120
    assert summary['fetch_failures'] == 0
    assert summary['consumers'] == [CONSUMER_TEAM_ASSIGNMENT, CONSUMER_ROSTER_STATUS]


def test_independent_fetches_still_issue_both_passes(app):
    """Without shared evidence each consumer fetches its own views, as before."""
    with app.app_context():
        seed_pitcher('Reds Arm', 800101, team_id=113)
        fake = CountingRosterClient(rosters={
            (113, ROSTER_TYPE_ACTIVE): [roster_entry(800101, 'Reds Arm', status='Active')],
        })

        sync_team_assignments(client=fake, timestamp=REFERENCE_TIME)
        assignment_calls = list(fake.roster_calls)
        sync_roster_statuses(client=fake, timestamp=REFERENCE_TIME, snapshot_date=REFERENCE_DATE)

    # Five fixture teams x four views for team assignment, then the stored
    # pitcher's team fetched a second time for roster status.
    assert len(assignment_calls) == 20
    assert len(fake.roster_calls) == 24
    assert fake.roster_calls.count((113, ROSTER_TYPE_ACTIVE)) == 2


# ── Team-assignment equivalence ──────────────────────────────


def test_team_assignment_classifications_are_equivalent(app, shares_evidence):
    with app.app_context():
        seed_pitcher('Reassigned Arm', 800201, team_id=116)
        seed_pitcher('Held Arm', 800202, team_id=113)
        seed_pitcher('Released Arm', 800203, team_id=143)
        seed_pitcher('Unknowable Arm', 800204, team_id=143)
        seed_pitcher('Player Info Arm', 800205, team_id=143)
        fake = CountingRosterClient(
            rosters={
                (141, ROSTER_TYPE_ACTIVE): [
                    roster_entry(800201, 'Reassigned Arm', status={'code': 'A', 'description': 'Active'}),
                ],
                (113, ROSTER_TYPE_ACTIVE): [
                    roster_entry(800202, 'Held Arm', status='Active'),
                ],
            },
            player_info={
                800203: {'status': {'description': 'Free Agent'}},
                800204: {'status': {'description': 'Unknown'}},
                800205: {'currentTeam': {'id': 135, 'name': 'San Diego Padres'}},
            },
        )

        result = sync_team_assignments(
            client=fake,
            timestamp=REFERENCE_TIME,
            evidence=run_evidence(fake, shares_evidence),
        )
        by_name = {pitcher.full_name: pitcher for pitcher in Pitcher.query.all()}
        reassigned = by_name['Reassigned Arm']
        released = by_name['Released Arm']
        unknowable = by_name['Unknowable Arm']
        from_player_info = by_name['Player Info Arm']

    assert result['by_status'] == {
        TEAM_ASSIGNMENT_ASSIGNED: 3,
        TEAM_ASSIGNMENT_NO_ORGANIZATION: 1,
        TEAM_ASSIGNMENT_UNKNOWN: 1,
    }
    assert result['reassigned_count'] == 2
    assert result['cleared_team_count'] == 2
    assert result['errors'] == 0

    assert reassigned.team_id == 141
    assert reassigned.team_name == 'Toronto Blue Jays'
    assert reassigned.team_abbreviation == 'TOR'
    assert reassigned.active is True
    assert reassigned.team_assignment_status == TEAM_ASSIGNMENT_ASSIGNED
    assert reassigned.team_assignment_source == 'mlb_stats_api:team_assignment_sync:active'

    assert by_name['Held Arm'].team_id == 113

    assert released.team_assignment_status == TEAM_ASSIGNMENT_NO_ORGANIZATION
    assert released.team_assignment_source == 'mlb_stats_api:team_assignment_sync:people:status'
    assert released.team_id is None
    assert released.active is False
    assert released.roster_status == STATUS_UNKNOWN

    assert unknowable.team_assignment_status == TEAM_ASSIGNMENT_UNKNOWN
    assert unknowable.team_assignment_source == 'mlb_stats_api:team_assignment_sync:unavailable'
    assert unknowable.team_id is None
    assert unknowable.active is False

    assert from_player_info.team_id == 135
    assert from_player_info.team_abbreviation == 'SD'
    assert from_player_info.team_assignment_source == (
        'mlb_stats_api:team_assignment_sync:people:currentTeam'
    )


def test_ambiguous_roster_evidence_is_equivalent_and_fails_closed(app, shares_evidence):
    with app.app_context():
        seed_pitcher('Ambiguous Arm', 800301, team_id=113)
        fake = CountingRosterClient(rosters={
            (113, ROSTER_TYPE_ACTIVE): [roster_entry(800301, 'Ambiguous Arm', status='Active')],
            (141, ROSTER_TYPE_ACTIVE): [roster_entry(800301, 'Ambiguous Arm', status='Active')],
        })

        result = sync_team_assignments(
            client=fake,
            timestamp=REFERENCE_TIME,
            evidence=run_evidence(fake, shares_evidence),
        )
        updated = Pitcher.query.filter_by(mlb_id=800301).one()

    assert result['unknown_count'] == 1
    assert result['cleared_team_count'] == 1
    assert updated.team_assignment_status == TEAM_ASSIGNMENT_UNKNOWN
    assert updated.team_assignment_source == 'mlb_stats_api:team_assignment_sync:ambiguous:active'
    assert updated.team_id is None
    assert updated.active is False
    assert fake.player_info_calls == []


def test_team_assignment_fetch_failure_is_equivalent_and_fails_closed(app, shares_evidence):
    with app.app_context():
        seed_pitcher('Unfetchable Arm', 800401, team_id=113)
        fake = CountingRosterClient(rosters={
            (113, ROSTER_TYPE_ACTIVE): RuntimeError('roster unavailable'),
        })

        result = sync_team_assignments(
            client=fake,
            timestamp=REFERENCE_TIME,
            evidence=run_evidence(fake, shares_evidence),
        )
        updated = Pitcher.query.filter_by(mlb_id=800401).one()

    assert result['errors'] == 1
    assert result['error_details'][0]['team_id'] == 113
    assert result['error_details'][0]['roster_type'] == ROSTER_TYPE_ACTIVE
    assert result['error_details'][0]['source'] == 'mlb_stats_api:team_assignment_sync:active'
    assert result['error_details'][0]['error'] == 'roster unavailable'
    assert result['pitchers_refreshed'] == 0
    assert updated.team_id == 113
    assert updated.active is True
    assert updated.team_assignment_status is None


def test_team_metadata_fetch_failure_is_equivalent(app, shares_evidence):
    with app.app_context():
        seed_pitcher('Metadata Arm', 800501, team_id=113)
        fake = CountingRosterClient(
            rosters={
                (113, ROSTER_TYPE_ACTIVE): [roster_entry(800501, 'Metadata Arm', status='Active')],
            },
            teams=RuntimeError('teams endpoint unavailable'),
        )

        result = sync_team_assignments(
            client=fake,
            timestamp=REFERENCE_TIME,
            evidence=run_evidence(fake, shares_evidence),
        )
        updated = Pitcher.query.filter_by(mlb_id=800501).one()

    assert result['errors'] == 1
    assert result['error_details'][0] == {
        'source': 'mlb_stats_api:team_assignment_sync:teams',
        'error': 'teams endpoint unavailable',
    }
    # Stored team identity still carries the run; ownership stays resolvable.
    assert result['teams_processed'] == 1
    assert updated.team_id == 113
    assert updated.team_abbreviation == 'CIN'


def test_player_info_fetch_failure_is_equivalent(app, shares_evidence):
    with app.app_context():
        seed_pitcher('People Failure Arm', 800601, team_id=113)
        fake = CountingRosterClient(player_info={
            800601: MlbApiFetchError('people endpoint failed', endpoint='/people/800601'),
        })

        result = sync_team_assignments(
            client=fake,
            timestamp=REFERENCE_TIME,
            evidence=run_evidence(fake, shares_evidence),
        )
        updated = Pitcher.query.filter_by(mlb_id=800601).one()

    assert result['lookup_errors'] == 1
    assert result['pitchers_refreshed'] == 0
    assert updated.team_id == 113
    assert updated.active is True
    assert updated.team_assignment_status is None


# ── Roster-status equivalence ────────────────────────────────


def reds_rosters():
    return {
        (113, ROSTER_TYPE_ACTIVE): [
            roster_entry(800701, 'Active Arm', status={'code': 'A', 'description': 'Active'}, two_way=True),
        ],
        (113, ROSTER_TYPE_40_MAN): [
            roster_entry(800701, 'Active Arm', status={'code': 'A', 'description': 'Active'}),
            roster_entry(800702, 'Injured Arm', status={'code': 'D15', 'description': '15-day IL'}),
            roster_entry(800703, 'Designated Arm', status='Designated for assignment'),
            roster_entry(800704, '40-man Arm'),
        ],
        (113, ROSTER_TYPE_FULL): [
            roster_entry(800701, 'Active Arm', status='Active'),
            roster_entry(800702, 'Injured Arm', status='15-day injured list'),
            roster_entry(800705, 'Minors Arm'),
        ],
        (113, ROSTER_TYPE_NON_ROSTER): [
            roster_entry(800706, 'Non Roster Arm'),
        ],
    }


def test_roster_status_classifications_are_equivalent(app, shares_evidence):
    with app.app_context():
        seed_pitcher('Active Arm', 800701)
        seed_pitcher('Injured Arm', 800702)
        seed_pitcher('Designated Arm', 800703)
        seed_pitcher('40-man Arm', 800704)
        seed_pitcher('Minors Arm', 800705)
        seed_pitcher('Non Roster Arm', 800706)
        seed_pitcher('Missing Arm', 800707)
        run = seed_sync_run()
        fake = CountingRosterClient(rosters=reds_rosters())

        result = sync_roster_statuses(
            team_ids=[113],
            client=fake,
            timestamp=REFERENCE_TIME,
            snapshot_date=REFERENCE_DATE,
            sync_run_id=run.id,
            evidence=run_evidence(fake, shares_evidence),
        )
        by_name = {pitcher.full_name: pitcher for pitcher in Pitcher.query.all()}
        snapshots = {
            snapshot.mlb_id: snapshot
            for snapshot in RosterStatusSnapshot.query.all()
        }

    assert result['by_status'] == {
        STATUS_40_MAN_ONLY: 1,
        STATUS_ACTIVE: 1,
        STATUS_DFA: 1,
        STATUS_IL_15: 1,
        STATUS_MINORS: 1,
        STATUS_NON_ROSTER: 1,
        STATUS_UNKNOWN: 1,
    }
    assert result['snapshots_created'] == 7
    assert result['missing_from_roster_sources'] == 1
    assert result['errors'] == 0

    assert by_name['Active Arm'].roster_status == STATUS_ACTIVE
    assert by_name['Active Arm'].roster_status_source == 'mlb_stats_api:roster_sync:active'
    assert by_name['Injured Arm'].roster_status == STATUS_IL_15
    assert by_name['Injured Arm'].roster_status_raw_code == 'D15'
    assert by_name['Injured Arm'].roster_status_raw_description == '15-day IL'
    assert by_name['Designated Arm'].roster_status == STATUS_DFA
    assert by_name['40-man Arm'].roster_status == STATUS_40_MAN_ONLY
    assert by_name['Minors Arm'].roster_status == STATUS_MINORS
    assert by_name['Non Roster Arm'].roster_status == STATUS_NON_ROSTER
    assert by_name['Missing Arm'].roster_status == STATUS_UNKNOWN
    assert by_name['Missing Arm'].roster_status_source == 'mlb_stats_api:roster_sync:unavailable'

    active_snapshot = snapshots[800701]
    assert active_snapshot.active_roster is True
    assert active_snapshot.forty_man_roster is True
    assert active_snapshot.position_code == '1'
    assert active_snapshot.position_name == 'Pitcher'
    assert active_snapshot.position_type == 'Pitcher'
    assert active_snapshot.two_way_eligible is True
    assert active_snapshot.sync_run_id is not None
    assert snapshots[800704].active_roster is False
    assert snapshots[800704].forty_man_roster is True
    assert snapshots[800707].active_roster is None
    assert snapshots[800707].forty_man_roster is None


def test_snapshot_created_corrected_and_unchanged_are_equivalent(app, shares_evidence):
    with app.app_context():
        pitcher = seed_pitcher('Snapshot Arm', 800801)
        run = seed_sync_run()
        active_only = {
            (113, ROSTER_TYPE_ACTIVE): [roster_entry(800801, 'Snapshot Arm', status='Active')],
        }
        corrected = {
            (113, ROSTER_TYPE_40_MAN): [
                roster_entry(800801, 'Snapshot Arm', status={'code': 'D15', 'description': '15-day IL'}),
            ],
        }

        # Each sync is its own run, so each gets its own run-scoped evidence.
        first_client = CountingRosterClient(rosters=active_only)
        first = sync_roster_statuses(
            team_ids=[113], client=first_client, timestamp=REFERENCE_TIME,
            snapshot_date=REFERENCE_DATE, sync_run_id=run.id,
            evidence=run_evidence(first_client, shares_evidence),
        )
        second_client = CountingRosterClient(rosters=active_only)
        second = sync_roster_statuses(
            team_ids=[113], client=second_client, timestamp=datetime(2026, 8, 15, 13, 0, 0),
            snapshot_date=REFERENCE_DATE, sync_run_id=run.id,
            evidence=run_evidence(second_client, shares_evidence),
        )
        third_client = CountingRosterClient(rosters=corrected)
        third = sync_roster_statuses(
            team_ids=[113], client=third_client, timestamp=datetime(2026, 8, 15, 14, 0, 0),
            snapshot_date=REFERENCE_DATE, sync_run_id=run.id,
            evidence=run_evidence(third_client, shares_evidence),
        )
        snapshot = RosterStatusSnapshot.query.one()
        updated = db.session.get(Pitcher, pitcher.id)

    assert (first['snapshots_created'], first['snapshots_corrected'], first['snapshots_unchanged']) == (1, 0, 0)
    assert (second['snapshots_created'], second['snapshots_corrected'], second['snapshots_unchanged']) == (0, 0, 1)
    assert (third['snapshots_created'], third['snapshots_corrected'], third['snapshots_unchanged']) == (0, 1, 0)
    assert snapshot.roster_status == STATUS_IL_15
    assert snapshot.correction_count == 1
    assert snapshot.correction_source == 'mlb_stats_api:roster_sync:40Man'
    assert snapshot.last_corrected_at == datetime(2026, 8, 15, 14, 0, 0)
    assert updated.roster_status == STATUS_IL_15


def test_snapshot_team_conflict_is_equivalent(app, shares_evidence):
    with app.app_context():
        pitcher = seed_pitcher('Conflict Arm', 800901, team_id=113)
        run = seed_sync_run()
        first_client = CountingRosterClient(rosters={
            (113, ROSTER_TYPE_ACTIVE): [roster_entry(800901, 'Conflict Arm', status='Active')],
        })
        sync_roster_statuses(
            team_ids=[113], client=first_client, timestamp=REFERENCE_TIME,
            snapshot_date=REFERENCE_DATE, sync_run_id=run.id,
            evidence=run_evidence(first_client, shares_evidence),
        )
        pitcher.team_id = 135
        db.session.commit()

        second_client = CountingRosterClient(rosters={
            (135, ROSTER_TYPE_ACTIVE): [roster_entry(800901, 'Conflict Arm', status='Active')],
        })
        result = sync_roster_statuses(
            team_ids=[135], client=second_client, timestamp=datetime(2026, 8, 15, 13, 0, 0),
            snapshot_date=REFERENCE_DATE, sync_run_id=run.id,
            evidence=run_evidence(second_client, shares_evidence),
        )
        failure = SyncFailure.query.filter_by(
            entity_type=ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
            resolved=False,
        ).one()
        snapshot_count = RosterStatusSnapshot.query.count()

    assert result['snapshot_conflicts'] == 1
    assert result['records_failed'] == 1
    assert failure.payload['existing_team_id'] == 113
    assert failure.payload['incoming_team_id'] == 135
    assert snapshot_count == 1


# ── Shared failure semantics ─────────────────────────────────


def test_roster_fetch_failure_is_observed_by_both_consumers(app, shares_evidence):
    """A failed view stays a failure — never reused as an empty roster."""
    with app.app_context():
        seed_pitcher('Failure Arm', 801001, team_id=113)
        fake = CountingRosterClient(rosters={
            (113, ROSTER_TYPE_ACTIVE): RuntimeError('roster unavailable'),
            (113, ROSTER_TYPE_40_MAN): [
                roster_entry(801001, 'Failure Arm', status={'code': 'D15', 'description': '15-day IL'}),
            ],
        })
        evidence = run_evidence(fake, shares_evidence)

        assignment = sync_team_assignments(
            client=fake, timestamp=REFERENCE_TIME, evidence=evidence,
        )
        roster = sync_roster_statuses(
            team_ids=[113], client=fake, timestamp=REFERENCE_TIME,
            snapshot_date=REFERENCE_DATE, evidence=evidence,
        )
        updated = Pitcher.query.filter_by(mlb_id=801001).one()
        snapshot_count = RosterStatusSnapshot.query.count()
        failure = SyncFailure.query.filter_by(
            entity_type=ROSTER_STATUS_FETCH_ENTITY_TYPE,
            resolved=False,
        ).one()

    assert [
        (detail['team_id'], detail['roster_type'])
        for detail in assignment['error_details']
    ] == [(113, ROSTER_TYPE_ACTIVE)]
    assert roster['errors'] == 1
    assert roster['error_details'][0]['reason'] == 'fetch_failed'
    assert roster['error_details'][0]['roster_type'] == ROSTER_TYPE_ACTIVE
    assert roster['error_details'][0]['error'] == 'roster unavailable'
    assert roster['records_failed'] == 1
    assert roster['pitchers_refreshed'] == 0
    assert failure.payload['team_id'] == 113
    # Fail closed: no snapshot written and prior team assignment untouched.
    assert snapshot_count == 0
    assert updated.team_id == 113
    assert updated.active is True


def test_missing_shared_evidence_is_fetched_fresh_not_read_as_no_evidence(app):
    """
    A team the shared pass never covered is fetched, not treated as empty.

    Roster status sweeps the teams stored on active pitchers, which can include a
    club the team-assignment pass did not read (for example one resolved from the
    people endpoint). That team must still produce official evidence.
    """
    with app.app_context():
        seed_pitcher('Uncovered Arm', 801101, team_id=135)
        fake = CountingRosterClient(rosters={
            (135, ROSTER_TYPE_ACTIVE): [roster_entry(801101, 'Uncovered Arm', status='Active')],
        })
        evidence = build_run_roster_evidence(client=fake)
        # The shared pass only read team 113 this run.
        build_team_assignment_index(team_ids=[113], evidence=evidence)
        calls_after_assignment = list(fake.roster_calls)

        result = sync_roster_statuses(
            team_ids=[135], client=fake, timestamp=REFERENCE_TIME,
            snapshot_date=REFERENCE_DATE, evidence=evidence,
        )
        updated = Pitcher.query.filter_by(mlb_id=801101).one()

    assert (135, ROSTER_TYPE_ACTIVE) not in calls_after_assignment
    assert (135, ROSTER_TYPE_ACTIVE) in fake.roster_calls
    assert result['snapshots_created'] == 1
    assert updated.roster_status == STATUS_ACTIVE


def test_failed_view_is_not_refetched_as_success_within_a_run(app):
    with app.app_context():
        fake = CountingRosterClient(rosters={
            (113, ROSTER_TYPE_ACTIVE): RuntimeError('roster unavailable'),
        })
        evidence = build_run_roster_evidence(client=fake)

        build_team_assignment_index(team_ids=[113], evidence=evidence)
        _index, errors = build_team_roster_status_index(113, evidence=evidence)
        summary = evidence.summary()

    assert [error['reason'] for error in errors] == ['fetch_failed']
    assert errors[0]['error'] == 'roster unavailable'
    assert fake.roster_calls.count((113, ROSTER_TYPE_ACTIVE)) == 1
    assert summary['fetch_failures'] == 1
    assert summary['fetch_failure_details'][0]['team_id'] == 113


# ── Mutation isolation ───────────────────────────────────────


def test_one_consumer_cannot_mutate_evidence_seen_by_the_other(app):
    with app.app_context():
        source_entry = roster_entry(801201, 'Shared Arm', status='Active')
        fake = CountingRosterClient(rosters={
            (113, ROSTER_TYPE_ACTIVE): [source_entry],
        })
        evidence = build_run_roster_evidence(client=fake)

        first = evidence.roster_view(113, ROSTER_TYPE_ACTIVE)
        first.entries[0]['person']['id'] = 999999
        first.entries[0]['status'] = 'Mutated'
        first.entries[0]['position']['name'] = 'Mutated'

        second = evidence.roster_view(113, ROSTER_TYPE_ACTIVE)
        metadata = evidence.team_metadata()
        metadata.team_map[113] = {'id': 113, 'name': 'Mutated', 'abbreviation': 'XXX'}

    assert second.entries[0]['person']['id'] == 801201
    assert second.entries[0]['status'] == 'Active'
    assert second.entries[0]['position']['name'] == 'Pitcher'
    assert second.entries is not first.entries
    # The raw official response is untouched too.
    assert source_entry['person']['id'] == 801201
    assert evidence.team_metadata().team_map[113]['name'] == 'Cincinnati Reds'


def test_evidence_is_run_scoped_and_not_shared_across_runs(app):
    with app.app_context():
        fake = CountingRosterClient(rosters={
            (113, ROSTER_TYPE_ACTIVE): [roster_entry(801301, 'Run Scoped Arm', status='Active')],
        })
        first_run = build_run_roster_evidence(client=fake)
        first_run.roster_view(113, ROSTER_TYPE_ACTIVE)
        second_run = build_run_roster_evidence(client=fake)
        second_run.roster_view(113, ROSTER_TYPE_ACTIVE)

    assert fake.roster_calls == [(113, ROSTER_TYPE_ACTIVE), (113, ROSTER_TYPE_ACTIVE)]


# ── Daily sync integration ───────────────────────────────────


def test_daily_sync_builds_roster_evidence_once_for_both_consumers(app, monkeypatch):
    """The daily orchestrator issues one roster pass, not two."""
    with app.app_context():
        seed_pitcher('Daily Arm', 801401, team_id=113)

    fake = CountingRosterClient(
        rosters={
            (team_id, ROSTER_TYPE_ACTIVE): (
                [roster_entry(801401, 'Daily Arm', status='Active')] if team_id == 113 else []
            )
            for team_id in MLB_TEAM_IDS
        },
        teams=[
            {'id': team_id, 'name': f'Team {team_id}', 'abbreviation': f'T{team_id}'}
            for team_id in MLB_TEAM_IDS
        ],
    )
    monkeypatch.setattr(mlb_client, 'get_all_teams', fake.get_all_teams)
    monkeypatch.setattr(mlb_client, 'get_team_roster', fake.get_team_roster)
    monkeypatch.setattr(mlb_client, 'get_player_info', fake.get_player_info)
    monkeypatch.setattr(sync_service, '_sync_schedule_finality_preflight_enabled', lambda: False)
    monkeypatch.setattr(sync_service, 'resolve_product_day', lambda started: SimpleNamespace(
        calendar_date=REFERENCE_DATE,
        limitations=(),
    ))
    monkeypatch.setattr(sync_service, 'sync_transactions', lambda **_kwargs: {
        'records_fetched': 0, 'records_stored': 0, 'unknown_type_count': 0,
        'records_failed': 0, 'errors': 0, 'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **_kwargs: {
        'new_logs_added': 0, 'logs_corrected': 0, 'logs_unchanged': 0,
        'pitchers_touched': 0, 'pitchers_total': 1, 'errors': 0, 'records_failed': 0,
        'correction_attempts_failed': 0, 'unresolved_finality': 0, 'splits_seen': 0,
        'splits_skipped': {}, 'lane_health': 'ok', 'budget_exhausted_pitchers': 0,
        'fetch_seconds': 0.1, 'process_seconds': 0.1,
    })
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 1)
    monkeypatch.setattr(sync_service, 'complete_sync_run_with_snapshot',
                        lambda *args, **kwargs: (SimpleNamespace(id=1), SimpleNamespace(id=88)))

    status = sync_service.run_daily_sync(
        app,
        days_back=7,
        include_internal_enrichment=False,
    )

    with app.app_context():
        snapshot_count = RosterStatusSnapshot.query.count()

    assert status['status'] == sync_metadata.STATUS_SUCCESS
    assert fake.team_calls == 1
    assert len(fake.roster_calls) == 120
    assert len(set(fake.roster_calls)) == 120
    assert sorted({roster_type for _, roster_type in fake.roster_calls}) == sorted(ROSTER_TYPES)
    # Both consumers still did their work off the single pass.
    assert snapshot_count == 1


def test_daily_sync_passes_the_same_evidence_object_to_both_consumers(app, monkeypatch):
    observed = {}

    def fake_assignments(**kwargs):
        observed['team_assignment'] = kwargs.get('evidence')
        return {
            'pitchers_refreshed': 0, 'pitchers_changed': 0, 'reassigned_count': 0,
            'no_organization_count': 0, 'unknown_count': 0, 'errors': 0,
            'by_status': {}, 'error_details': [],
        }

    def fake_roster(**kwargs):
        observed['roster_status'] = kwargs.get('evidence')
        return {
            'pitchers_refreshed': 0, 'pitchers_changed': 0, 'unknown_count': 0,
            'snapshots_created': 0, 'snapshots_corrected': 0, 'snapshots_unchanged': 0,
            'records_failed': 0, 'errors': 0, 'error_details': [],
        }

    monkeypatch.setattr(sync_service, '_sync_schedule_finality_preflight_enabled', lambda: False)
    monkeypatch.setattr(sync_service, 'resolve_product_day', lambda started: SimpleNamespace(
        calendar_date=REFERENCE_DATE,
        limitations=(),
    ))
    monkeypatch.setattr(sync_service, 'sync_team_assignments', fake_assignments)
    monkeypatch.setattr(sync_service, 'sync_roster_statuses', fake_roster)
    monkeypatch.setattr(sync_service, 'sync_transactions', lambda **_kwargs: {
        'records_fetched': 0, 'records_stored': 0, 'unknown_type_count': 0,
        'records_failed': 0, 'errors': 0, 'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **_kwargs: {
        'new_logs_added': 0, 'logs_corrected': 0, 'logs_unchanged': 0,
        'pitchers_touched': 0, 'pitchers_total': 0, 'errors': 0, 'records_failed': 0,
        'correction_attempts_failed': 0, 'unresolved_finality': 0, 'splits_seen': 0,
        'splits_skipped': {}, 'lane_health': 'ok', 'budget_exhausted_pitchers': 0,
        'fetch_seconds': 0.1, 'process_seconds': 0.1,
    })
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 0)
    monkeypatch.setattr(sync_service, 'complete_sync_run_with_snapshot',
                        lambda *args, **kwargs: (SimpleNamespace(id=1), SimpleNamespace(id=88)))

    sync_service.run_daily_sync(app, days_back=7, include_internal_enrichment=False)

    assert observed['team_assignment'] is not None
    assert observed['roster_status'] is observed['team_assignment']
