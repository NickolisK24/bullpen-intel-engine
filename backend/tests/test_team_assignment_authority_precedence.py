"""Team-assignment authority precedence under the pitcher projection fence.

Production Daily SyncRun 93203 (2026-10-01) withheld candidate 4153. KC, ATH
and TEX each had three active-bullpen relievers with no fatigue score whose
ledger-confirmed rest was refused with ``team_assignment_unconfirmed``: the
pitcher rows carried the team and ``active`` but no ``ASSIGNED`` status.

Those pitchers were adopted by the sync-pipeline runtime (a current
``active_roster`` / ``forty_man_roster`` membership interval), which wrote their
team and roster fields but never an assignment status. On adopted pitchers the
``baseballos_pitcher_projection_fence`` trigger reverts every update of the
team, assignment and roster fields unless the session declared
``baseballos.roster_owner`` for the row's team. ``sync_roster_statuses`` was
fixed for this on September 25; ``sync_team_assignments`` never declared it, so
every official active-roster confirmation it wrote for these pitchers was
silently reverted, run after run, while the ORM counted it as a change.

The first group of tests runs the real writer against the real migrated
PostgreSQL schema (trigger included). The second group pins the precedence
rules on SQLite, where adoption is supplied explicitly.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import text

import services.team_assignment_sync as assignment_module
from models.pitcher import Pitcher
from services import ledger_confirmed_rest
from services.mlb_api import MlbApiFetchError
from services.roster_status import STATUS_ACTIVE
from services.roster_status_sync import ROSTER_TYPE_40_MAN, ROSTER_TYPE_ACTIVE
from services.team_assignment_sync import (
    TEAM_ASSIGNMENT_ASSIGNED,
    TEAM_ASSIGNMENT_NO_ORGANIZATION,
    TEAM_ASSIGNMENT_UNKNOWN,
    sync_team_assignments,
)
from tests.test_schedule_ingestion import fenced_app, fenced_database_url  # noqa: F401
from tests.test_team_assignment_sync import (  # noqa: F401
    FakeAssignmentClient,
    client,
    roster_entry,
)
from utils.db import db


KC, ATH, TEX = 118, 133, 140
TEAMS = [
    {'id': KC, 'name': 'Kansas City Royals', 'abbreviation': 'KC'},
    {'id': ATH, 'name': 'Athletics', 'abbreviation': 'ATH'},
    {'id': TEX, 'name': 'Texas Rangers', 'abbreviation': 'TEX'},
]
ABBR = {team['id']: team['abbreviation'] for team in TEAMS}
TIMESTAMP = datetime(2026, 10, 1, 10, 25)
ACTIVE = {'code': 'A', 'description': 'Active'}

# Generalized production shapes: three unscored active relievers per club, one
# with an old MLB appearance. Identifiers are synthetic.
PRODUCTION_SHAPES = {
    KC: (920001, 920002, 920003),
    ATH: (920011, 920012, 920013),
    TEX: (920021, 920022, 920023),
}


def _pitcher(mlb_id, team_id, *, status=None, source=None, active=True):
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=f'Arm {mlb_id}', position='P', active=active,
        team_id=team_id, team_name=f'Team {team_id}',
        team_abbreviation=ABBR.get(team_id), roster_status=STATUS_ACTIVE,
        roster_status_source='mlb_stats_api:roster_sync:active',
        team_assignment_status=status, team_assignment_source=source,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _adopt(pitcher, team_id, membership_type='active_roster'):
    """Adopt a pitcher the way the sync-pipeline runtime does: an open interval."""
    db.session.execute(text(
        'ALTER TABLE roster_membership_intervals DROP CONSTRAINT IF EXISTS '
        'roster_membership_intervals_opened_by_observation_id_fkey'
    ))
    db.session.execute(text(
        "INSERT INTO roster_membership_intervals (pitcher_id, player_mlb_id, team_id,"
        " membership_type, effective_start_date, authority_type, opened_by_observation_id,"
        " is_current_version, is_void, created_at, updated_at) "
        "VALUES (:pitcher, :mlb, :team, :kind, '2026-09-01', 'official_roster',"
        " 1, true, false, now(), now())"
    ), {'pitcher': pitcher.id, 'mlb': pitcher.mlb_id, 'team': team_id, 'kind': membership_type})


def _runtime_adopted_production_shapes():
    """Every production shape: adopted, team and active set, never ASSIGNED."""
    ids = {}
    for team_id, mlb_ids in PRODUCTION_SHAPES.items():
        for mlb_id in mlb_ids:
            pitcher = _pitcher(mlb_id, team_id)
            _adopt(pitcher, team_id)
            ids[mlb_id] = pitcher.id
    db.session.commit()
    return ids


def _active_rosters(placements):
    """``{(team, roster_type): [entries]}`` with each pitcher on active + 40-man."""
    rosters = {}
    for mlb_id, team_id in placements.items():
        entry = roster_entry(mlb_id, f'Arm {mlb_id}', status=ACTIVE)
        rosters.setdefault((team_id, ROSTER_TYPE_ACTIVE), []).append(entry)
        rosters.setdefault((team_id, ROSTER_TYPE_40_MAN), []).append(entry)
    return rosters


def _suppressed_ids():
    return {
        int(key) for (key,) in db.session.execute(text(
            "SELECT resource_key FROM compatibility_write_events "
            "WHERE resource_type='pitcher_projection' AND outcome='stale_suppressed'"
        ))
    }


def _placements():
    return {
        mlb_id: team_id
        for team_id, mlb_ids in PRODUCTION_SHAPES.items()
        for mlb_id in mlb_ids
    }


def _run(rosters, player_info=None):
    return sync_team_assignments(
        client=FakeAssignmentClient(rosters=rosters, player_info=player_info or {}, teams=TEAMS),
        team_ids=[KC, ATH, TEX], timestamp=TIMESTAMP,
    )


def _unscored_reason(pitcher_id, team_id):
    return ledger_confirmed_rest.evaluate_unscored_rest(
        [pitcher_id], team_id=team_id, reference_date=date(2026, 10, 1),
        ledger_complete=True,
    )[pitcher_id]


# ---------------------------------------------------------------------------
# Real trigger, real migrated schema.
# ---------------------------------------------------------------------------


def test_case_l_official_active_roster_confirms_every_adopted_production_shape(fenced_app):
    ids = _runtime_adopted_production_shapes()

    result = _run(_active_rosters(_placements()))
    db.session.remove()

    for mlb_id, team_id in _placements().items():
        pitcher = db.session.get(Pitcher, ids[mlb_id])
        assert pitcher.team_assignment_status == TEAM_ASSIGNMENT_ASSIGNED
        assert pitcher.team_assignment_source == 'mlb_stats_api:team_assignment_sync:active'
        assert (pitcher.team_id, pitcher.active) == (team_id, True)
        # The roster-status cache is not the assignment writer's to touch.
        assert pitcher.roster_status == STATUS_ACTIVE
        # The downstream proof now sees confirmed assignment authority.
        assert _unscored_reason(pitcher.id, team_id) == 'ledger_confirmed_no_recent_workload'
    assert _suppressed_ids() == set()
    assert result['fence_suppressed_writes'] == 0
    assert result['outcomes'] == {'confirmed_assigned': 9}
    assert result['ownership_declared_teams'] == 3


def test_without_the_ownership_declaration_the_fence_reproduces_syncrun_93203(
    fenced_app, monkeypatch,
):
    """The regression: the writer as it was. Every confirmation is reverted."""
    ids = _runtime_adopted_production_shapes()
    monkeypatch.setattr(assignment_module, '_declare_roster_ownership', lambda _team: None)

    result = _run(_active_rosters(_placements()))
    db.session.remove()

    # The ORM counted nine changes; the database kept none of them.
    assert result['pitchers_changed'] == 9
    assert result['fence_suppressed_writes'] == 9
    assert _suppressed_ids() == set(ids.values())
    for mlb_id, team_id in _placements().items():
        pitcher = db.session.get(Pitcher, ids[mlb_id])
        assert pitcher.team_assignment_status is None
        assert (pitcher.team_id, pitcher.active) == (team_id, True)
        assert _unscored_reason(pitcher.id, team_id) == 'team_assignment_unconfirmed'


def test_case_d_official_active_roster_moves_an_adopted_pitcher(fenced_app):
    pitcher = _pitcher(921001, KC, status=TEAM_ASSIGNMENT_ASSIGNED,
                       source='mlb_stats_api:team_assignment_sync:active')
    _adopt(pitcher, KC)
    db.session.commit()
    pitcher_id = pitcher.id

    result = _run(_active_rosters({921001: ATH}))
    db.session.remove()

    moved = db.session.get(Pitcher, pitcher_id)
    assert (moved.team_id, moved.team_assignment_status) == (ATH, TEAM_ASSIGNMENT_ASSIGNED)
    assert result['outcomes'] == {'confirmed_reassigned': 1}
    assert result['reassigned_count'] == 1
    assert _suppressed_ids() == set()


@pytest.mark.parametrize('player_info, outcome', [
    ({}, 'lookup_missing'),
    ({921002: {'fullName': 'Arm', 'status': {'description': 'Unknown'}}},
     'preserved_strong_assignment'),
    ({921002: MlbApiFetchError('people endpoint failed', endpoint='/people/921002')},
     'lookup_failed'),
])
def test_cases_a_b_j_weak_or_absent_evidence_never_erases_adopted_membership(
    fenced_app, player_info, outcome,
):
    pitcher = _pitcher(921002, KC, status=TEAM_ASSIGNMENT_ASSIGNED,
                       source='mlb_stats_api:team_assignment_sync:active')
    _adopt(pitcher, KC)
    db.session.commit()
    pitcher_id = pitcher.id

    result = _run({}, player_info)
    db.session.remove()

    kept = db.session.get(Pitcher, pitcher_id)
    assert (kept.team_id, kept.active, kept.team_assignment_status) == (
        KC, True, TEAM_ASSIGNMENT_ASSIGNED,
    )
    assert result['outcomes'] == {outcome: 1}
    # Preserved explicitly, not written and silently reverted.
    assert result['fence_suppressed_writes'] == 0
    assert _suppressed_ids() == set()


def test_case_h_assignment_writes_never_touch_dated_roster_history(fenced_app):
    ids = _runtime_adopted_production_shapes()
    tables = ('roster_status_snapshots', 'roster_membership_intervals')
    before = {
        table: db.session.execute(text(f'SELECT count(*), max(updated_at) FROM {table}')).one()
        for table in tables
    }

    _run(_active_rosters(_placements()))
    db.session.remove()

    after = {
        table: db.session.execute(text(f'SELECT count(*), max(updated_at) FROM {table}')).one()
        for table in tables
    }
    assert after == before
    assert len(ids) == 9


# ---------------------------------------------------------------------------
# Precedence rules (SQLite; adoption supplied explicitly).
# ---------------------------------------------------------------------------


@pytest.fixture
def adopted(monkeypatch):
    adopted_ids = {}
    monkeypatch.setattr(assignment_module, '_adopted_pitcher_teams', lambda: adopted_ids)
    return adopted_ids


def _sqlite_run(rosters=None, player_info=None):
    return sync_team_assignments(
        client=FakeAssignmentClient(
            rosters=rosters or {}, player_info=player_info or {}, teams=TEAMS,
        ),
        team_ids=[KC, ATH, TEX], timestamp=TIMESTAMP,
    )


def test_case_c_and_i_official_roster_confirms_a_call_up_with_no_person_team(client, adopted):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(922001, None, active=False)
        db.session.commit()
        result = _sqlite_run(
            _active_rosters({922001: TEX}),
            {922001: {'fullName': 'Call Up'}},
        )
        updated = db.session.get(Pitcher, pitcher.id)
        assert (updated.team_id, updated.active, updated.team_assignment_status) == (
            TEX, True, TEAM_ASSIGNMENT_ASSIGNED,
        )
        assert result['outcomes'] == {'confirmed_assigned': 1}


def test_case_e_optioned_player_stays_with_his_organization(client, adopted):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(922002, KC, status=TEAM_ASSIGNMENT_ASSIGNED)
        adopted[pitcher.id] = {KC}
        db.session.commit()
        optioned = roster_entry(922002, 'Optioned', status={'code': 'MIN', 'description': 'Optioned'})
        _sqlite_run({(KC, ROSTER_TYPE_40_MAN): [optioned]})
        updated = db.session.get(Pitcher, pitcher.id)
        assert (updated.team_id, updated.team_assignment_status) == (KC, TEAM_ASSIGNMENT_ASSIGNED)
        assert updated.team_assignment_source == 'mlb_stats_api:team_assignment_sync:40Man'


def test_case_f_confirmed_release_clears_an_unadopted_assignment(client, adopted):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(922003, ATH, status=TEAM_ASSIGNMENT_ASSIGNED)
        db.session.commit()
        result = _sqlite_run(player_info={
            922003: {'fullName': 'Released', 'status': {'description': 'Released'}},
        })
        updated = db.session.get(Pitcher, pitcher.id)
        assert updated.team_assignment_status == TEAM_ASSIGNMENT_NO_ORGANIZATION
        assert (updated.team_id, updated.active) == (None, False)
        assert result['outcomes'] == {'no_organization': 1}


def test_case_g_conflicting_official_rosters_fail_closed(client, adopted):  # noqa: F811
    with client.application.app_context():
        loose = _pitcher(922004, KC, status=TEAM_ASSIGNMENT_ASSIGNED)
        held = _pitcher(922005, KC, status=TEAM_ASSIGNMENT_ASSIGNED)
        adopted[held.id] = {KC}
        db.session.commit()
        rosters = {}
        for mlb_id in (922004, 922005):
            for team_id in (KC, ATH):
                rosters.setdefault((team_id, ROSTER_TYPE_ACTIVE), []).append(
                    roster_entry(mlb_id, f'Arm {mlb_id}', status=ACTIVE),
                )
        result = _sqlite_run(rosters)
        # Never last-writer-wins: the unadopted row fails closed, and the
        # adopted row keeps the membership the runtime already proved.
        assert db.session.get(Pitcher, loose.id).team_assignment_status == TEAM_ASSIGNMENT_UNKNOWN
        assert db.session.get(Pitcher, loose.id).team_id is None
        assert db.session.get(Pitcher, held.id).team_id == KC
        assert result['outcomes'] == {'authority_conflict': 2}


def test_case_j_an_empty_person_lookup_preserves_an_unadopted_assignment(client, adopted):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(922006, TEX, status=TEAM_ASSIGNMENT_ASSIGNED)
        db.session.commit()
        result = _sqlite_run(player_info={922006: None})
        updated = db.session.get(Pitcher, pitcher.id)
        assert (updated.team_id, updated.team_assignment_status) == (TEX, TEAM_ASSIGNMENT_ASSIGNED)
        assert result['outcomes'] == {'lookup_missing': 1}
        assert result['pitchers_refreshed'] == 0


def test_case_k_a_genuine_unknown_stays_unknown(client, adopted):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(922007, None, active=False)
        db.session.commit()
        result = _sqlite_run(player_info={
            922007: {'fullName': 'Nobody', 'status': {'description': 'Unknown'}},
        })
        updated = db.session.get(Pitcher, pitcher.id)
        assert updated.team_assignment_status == TEAM_ASSIGNMENT_UNKNOWN
        assert (updated.team_id, updated.active) == (None, False)
        assert result['outcomes'] == {'genuine_unknown': 1}
        assert result['unknown_count'] == 1


def test_a_weak_person_team_never_overwrites_an_adopted_assignment(client, adopted):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(922008, KC, status=TEAM_ASSIGNMENT_ASSIGNED)
        adopted[pitcher.id] = {KC}
        db.session.commit()
        result = _sqlite_run(player_info={
            922008: {'fullName': 'Arm', 'currentTeam': {'id': ATH}},
        })
        assert db.session.get(Pitcher, pitcher.id).team_id == KC
        assert result['outcomes'] == {'preserved_strong_assignment': 1}
