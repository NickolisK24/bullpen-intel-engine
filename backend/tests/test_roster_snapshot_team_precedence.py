"""Same-date roster snapshot team disagreements resolve by explicit precedence.

Daily SyncRun 93211 (the first Daily after #901) dead-lettered four
``roster_status_snapshot_conflict`` failures: "Roster snapshot team conflict
for same pitcher/date". They counted as non-game-log publication-critical
failures, so the run was ``partial`` with publication-critical work incomplete,
and slate coverage withheld the candidate as ``partial_sync``.

Topology: an earlier run on the same snapshot date classified the pitcher under
a stale stored team (team A). The pitcher was absent from every official roster
view of team A, so the row carried no roster evidence. After the corrected
assignment (team B, from B's official roster), the same-date row for team B was
refused as a conflict, although the two rows never contradicted each other: one
records absence from A, the other records presence on B.

Precedence: official roster presence outranks recorded absence. Two rows that
both record presence for different teams, or both record absence, are not
ordered by any authority and remain a fail-closed conflict.
"""

from datetime import date

from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_failure import SyncFailure
from services.roster_status import STATUS_ACTIVE, STATUS_UNKNOWN
from services.roster_status_sync import (
    PRECEDENCE_CONFLICT,
    PRECEDENCE_RETAIN_EXISTING,
    PRECEDENCE_SUPERSEDE_EXISTING,
    ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_ACTIVE,
    same_date_team_precedence,
    sync_roster_statuses,
)
from tests.test_roster_status_sync import (  # noqa: F401
    FakeRosterClient,
    client,
    roster_entry,
)
from utils.db import db


TEAM_A, TEAM_B = 141, 147
SNAPSHOT_DATE = date(2026, 10, 1)
ACTIVE = {'code': 'A', 'description': 'Active'}


def _pitcher(mlb_id, team_id):
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=f'Arm {mlb_id}', team_id=team_id,
        team_name=f'Team {team_id}', team_abbreviation=f'T{team_id}',
        position='P', active=True,
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _on_active_roster(mlb_id, team_id):
    entry = roster_entry(mlb_id, f'Arm {mlb_id}', status=ACTIVE)
    return {
        (team_id, ROSTER_TYPE_ACTIVE): [entry],
        (team_id, ROSTER_TYPE_40_MAN): [entry],
    }


def _sync(team_id, rosters):
    return sync_roster_statuses(
        team_ids=[team_id], client=FakeRosterClient(rosters), snapshot_date=SNAPSHOT_DATE,
    )


def _move(pitcher, team_id):
    """The corrected assignment, as #901's writer now persists it."""
    pitcher.team_id = team_id
    pitcher.team_name = f'Team {team_id}'
    pitcher.team_abbreviation = f'T{team_id}'
    db.session.commit()


def _snapshot(pitcher_id):
    return RosterStatusSnapshot.query.filter_by(
        pitcher_id=pitcher_id, snapshot_date=SNAPSHOT_DATE,
    ).one()


def _open_conflicts():
    return SyncFailure.query.filter_by(
        entity_type=ROSTER_STATUS_CONFLICT_ENTITY_TYPE, resolved=False,
    ).count()


def test_production_topology_absence_then_presence_reconciles(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(687900, TEAM_A)
        # Earlier same-date run: stale team A, absent from A's official rosters.
        first = _sync(TEAM_A, {})
        assert first['snapshot_conflicts'] == 0
        assert _snapshot(pitcher.id).team_id == TEAM_A
        assert _snapshot(pitcher.id).roster_status == STATUS_UNKNOWN

        _move(pitcher, TEAM_B)
        second = _sync(TEAM_B, _on_active_roster(687900, TEAM_B))

        snapshot = _snapshot(pitcher.id)
        assert (snapshot.team_id, snapshot.roster_status) == (TEAM_B, STATUS_ACTIVE)
        assert snapshot.active_roster is True
        assert snapshot.correction_count == 1
        assert second['snapshot_conflicts'] == 0
        assert second['records_failed'] == 0
        assert second['snapshots_superseded'] == 1
        assert _open_conflicts() == 0
        assert db.session.get(Pitcher, pitcher.id).roster_status == STATUS_ACTIVE


def test_a_dead_letter_from_the_failed_run_is_resolved_by_reconciliation(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(687901, TEAM_A)
        _sync(TEAM_A, {})
        db.session.add(SyncFailure(
            job_name='daily_sync', entity_type=ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
            entity_ref='687901', error='Roster snapshot team conflict for same pitcher/date',
            payload={'pitcher_id': pitcher.id, 'mlb_id': 687901,
                     'existing_team_id': TEAM_A, 'incoming_team_id': TEAM_B},
            resolved=False,
        ))
        db.session.commit()
        _move(pitcher, TEAM_B)

        result = _sync(TEAM_B, _on_active_roster(687901, TEAM_B))

        assert result['dead_letters_resolved']['conflict'] == 1
        assert _open_conflicts() == 0


def test_presence_is_retained_over_a_later_absence_claim(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(687902, TEAM_B)
        _sync(TEAM_B, _on_active_roster(687902, TEAM_B))
        _move(pitcher, TEAM_A)

        result = _sync(TEAM_A, {})

        snapshot = _snapshot(pitcher.id)
        assert (snapshot.team_id, snapshot.roster_status) == (TEAM_B, STATUS_ACTIVE)
        assert result['snapshot_conflicts'] == 0
        assert result['snapshots_retained_over_absence'] == 1
        assert _open_conflicts() == 0


def test_presence_on_two_teams_the_same_date_fails_closed(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(687903, TEAM_A)
        _sync(TEAM_A, _on_active_roster(687903, TEAM_A))
        _move(pitcher, TEAM_B)

        result = _sync(TEAM_B, _on_active_roster(687903, TEAM_B))

        assert _snapshot(pitcher.id).team_id == TEAM_A
        assert result['snapshot_conflicts'] == 1
        assert result['records_failed'] == 1
        assert _open_conflicts() == 1


def test_absence_from_two_teams_the_same_date_fails_closed(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(687904, TEAM_A)
        _sync(TEAM_A, {})
        _move(pitcher, TEAM_B)

        result = _sync(TEAM_B, {})

        assert _snapshot(pitcher.id).team_id == TEAM_A
        assert result['snapshot_conflicts'] == 1
        assert _open_conflicts() == 1


def test_an_earlier_date_is_never_rewritten(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(687905, TEAM_A)
        sync_roster_statuses(
            team_ids=[TEAM_A], client=FakeRosterClient({}), snapshot_date=date(2026, 9, 30),
        )
        _move(pitcher, TEAM_B)
        _sync(TEAM_B, _on_active_roster(687905, TEAM_B))

        rows = {
            row.snapshot_date: row.team_id
            for row in RosterStatusSnapshot.query.filter_by(pitcher_id=pitcher.id)
        }
        assert rows == {date(2026, 9, 30): TEAM_A, SNAPSHOT_DATE: TEAM_B}


def test_precedence_table_is_explicit():
    present = {'active_roster': True, 'forty_man_roster': True}
    full_roster_only = {'active_roster': False, 'forty_man_roster': False}
    absent = {'active_roster': None, 'forty_man_roster': None}
    assert same_date_team_precedence(absent, present) == PRECEDENCE_SUPERSEDE_EXISTING
    assert same_date_team_precedence(absent, full_roster_only) == PRECEDENCE_SUPERSEDE_EXISTING
    assert same_date_team_precedence(present, absent) == PRECEDENCE_RETAIN_EXISTING
    assert same_date_team_precedence(present, present) == PRECEDENCE_CONFLICT
    assert same_date_team_precedence(full_roster_only, present) == PRECEDENCE_CONFLICT
    assert same_date_team_precedence(absent, absent) == PRECEDENCE_CONFLICT
