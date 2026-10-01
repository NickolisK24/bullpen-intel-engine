"""Only MLB club rosters are MLB roster authority; affiliate rosters are context.

Daily SyncRun 93222 withheld candidate 4156 on one publication-critical
``roster_status_snapshot_conflict``. It was for one pitcher on 2026-10-01:
existing team 117 (an MLB club) against incoming team 5434. 5434 is
not an MLB club. It is one of the four affiliate IDs (484, 531, 534, 5434) that
production stores on pitcher rows (see docs/incidents/2026-09-12-daily-publication.md).

Mechanism. ``RunRosterEvidence.team_metadata`` overlays every team ID stored on
a pitcher row onto ``/teams``. Team assignment read that label map as its
roster universe, so it queried 30 clubs plus 4 affiliates (34 x 4 = 136 roster
requests). An optioned pitcher is on his club's 40-man (status Optioned) and on
the affiliate's *active* roster. Active outranks 40-man in assignment
precedence, so the affiliate became his "MLB team". Roster status then wrote
affiliate presence (ACTIVE) against the club's 40-man presence the same date.
Both were affirmative evidence, so the snapshot failed closed.

Fix. The roster authority universe is the governed MLB club registry. A pitcher
stored under an affiliate still gets a same-date snapshot, but the affiliate's
views classify as MINORS and never set the MLB active/40-man flags. MLB club
presence outranks affiliate presence, which outranks absence. Two MLB clubs
claiming the pitcher on one date remain a conflict.
"""

from datetime import date

import pytest

from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_failure import SyncFailure
from services import team_assignment_sync as team_assignment_module
from services.mlb_club_directory import MLB_TEAM_IDS
from services.roster_evidence import build_run_roster_evidence, is_mlb_club
from services.roster_status import STATUS_ACTIVE, STATUS_MINORS, STATUS_OPTIONED
from services.roster_status_sync import (
    AUTHORITY_ABSENT,
    AUTHORITY_AFFILIATE,
    AUTHORITY_MLB_CLUB,
    PRECEDENCE_CONFLICT,
    PRECEDENCE_RETAIN_EXISTING,
    PRECEDENCE_SUPERSEDE_EXISTING,
    ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_FULL,
    same_date_team_precedence,
    snapshot_authority_rank,
    sync_roster_statuses,
)
from services.team_assignment_sync import sync_team_assignments
from tests.test_roster_evidence_reuse import CountingRosterClient
from tests.test_roster_status_sync import client, roster_entry  # noqa: F401
from utils.db import db


CLUB, OTHER_CLUB = 117, 147
# Any team outside the MLB club registry; the production one was 5434.
AFFILIATE, OTHER_AFFILIATE = 5434, 531
SNAPSHOT_DATE = date(2026, 10, 1)
ACTIVE = {'code': 'A', 'description': 'Active'}
OPTIONED = {'code': 'O', 'description': 'Optioned'}


def _pitcher(mlb_id, team_id, active=True):
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=f'Arm {mlb_id}', team_id=team_id,
        team_name=f'Team {team_id}', team_abbreviation=f'T{team_id}',
        position='P', active=active,
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _entry(mlb_id, status):
    return roster_entry(mlb_id, f'Arm {mlb_id}', status=status)


def _optioned_topology(mlb_id):
    """Club 40-man (Optioned) + affiliate active/full roster, the same day."""
    return {
        (CLUB, ROSTER_TYPE_40_MAN): [_entry(mlb_id, OPTIONED)],
        (AFFILIATE, ROSTER_TYPE_ACTIVE): [_entry(mlb_id, ACTIVE)],
        (AFFILIATE, ROSTER_TYPE_FULL): [_entry(mlb_id, ACTIVE)],
    }


def _daily(rosters, player_info=None):
    """Team assignment then roster status on one shared evidence, as Daily does."""
    fake = CountingRosterClient(rosters=rosters, player_info=player_info or {})
    evidence = build_run_roster_evidence(client=fake)
    assignment = sync_team_assignments(client=fake, evidence=evidence)
    roster = sync_roster_statuses(
        client=fake, evidence=evidence, snapshot_date=SNAPSHOT_DATE,
    )
    return assignment, roster, evidence.summary(), fake


def _snapshot(pitcher_id):
    return RosterStatusSnapshot.query.filter_by(
        pitcher_id=pitcher_id, snapshot_date=SNAPSHOT_DATE,
    ).one()


def _open_conflicts():
    return SyncFailure.query.filter_by(
        entity_type=ROSTER_STATUS_CONFLICT_ENTITY_TYPE, resolved=False,
    ).count()


def _legacy_universe(team_ids, team_map):
    """The pre-fix universe: every label in the stored+``/teams`` team map."""
    if team_ids:
        return list(dict.fromkeys(team_ids))
    return sorted(team_map)


# ── 11. The production topology, before and after ─────────────


def _earlier_same_date_run(mlb_id):
    """Earlier on the snapshot date the pitcher was on the club's 40-man."""
    pitcher = _pitcher(mlb_id, CLUB)
    # Another arm stored under the affiliate is what pulled it into the
    # legacy universe.
    _pitcher(mlb_id + 1, AFFILIATE)
    sync_roster_statuses(
        team_ids=[CLUB],
        client=CountingRosterClient(rosters={
            (CLUB, ROSTER_TYPE_40_MAN): [_entry(mlb_id, OPTIONED)],
        }),
        snapshot_date=SNAPSHOT_DATE,
    )
    assert (_snapshot(pitcher.id).team_id, _snapshot(pitcher.id).roster_status) == (
        CLUB, STATUS_OPTIONED,
    )
    return pitcher


def test_legacy_universe_reproduces_the_production_conflict(client, monkeypatch):  # noqa: F811
    with client.application.app_context():
        pitcher = _earlier_same_date_run(669990)
        monkeypatch.setattr(team_assignment_module, '_team_ids_to_sync', _legacy_universe)
        monkeypatch.setattr(
            'services.roster_status_sync.same_date_team_precedence',
            _legacy_precedence,
        )

        assignment, roster, summary, fake = _daily(_optioned_topology(669990))

        # The stored affiliate entered the assignment universe, and its active
        # roster outranked the club 40-man: the wrong MLB team.
        assert (AFFILIATE, ROSTER_TYPE_ACTIVE) in fake.roster_calls
        assert db.session.get(Pitcher, pitcher.id).team_id == AFFILIATE
        assert roster['snapshot_conflicts'] == 1
        assert _open_conflicts() == 1
        assert _snapshot(pitcher.id).team_id == CLUB


def _legacy_precedence(existing, incoming):
    """#902 precedence: presence vs presence is a conflict whatever the team."""
    def evidenced(row):
        get = row.get if isinstance(row, dict) else (lambda k: getattr(row, k, None))
        return get('active_roster') is not None or get('forty_man_roster') is not None
    if evidenced(existing) and not evidenced(incoming):
        return PRECEDENCE_RETAIN_EXISTING
    if evidenced(incoming) and not evidenced(existing):
        return PRECEDENCE_SUPERSEDE_EXISTING
    return PRECEDENCE_CONFLICT


def test_production_topology_resolves_to_the_mlb_club(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _earlier_same_date_run(669991)
        # The dead letter the failed Daily left behind.
        db.session.add(SyncFailure(
            job_name='daily_sync', entity_type=ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
            entity_ref='669991', error='Roster snapshot team conflict for same pitcher/date',
            payload={'pitcher_id': pitcher.id, 'mlb_id': 669991,
                     'existing_team_id': CLUB, 'incoming_team_id': AFFILIATE},
            resolved=False,
        ))
        db.session.commit()

        assignment, roster, summary, fake = _daily(_optioned_topology(669991))

        moved = db.session.get(Pitcher, pitcher.id)
        assert moved.team_id == CLUB
        snapshot = _snapshot(pitcher.id)
        assert (snapshot.team_id, snapshot.roster_status) == (CLUB, STATUS_OPTIONED)
        assert snapshot.forty_man_roster is True and snapshot.active_roster is False
        assert roster['snapshot_conflicts'] == 0
        assert roster['records_failed'] == 0
        assert roster['true_mlb_roster_conflicts'] == 0
        # The governed reconciliation resolved the existing dead letter.
        assert roster['dead_letters_resolved']['conflict'] == 1
        assert _open_conflicts() == 0
        # Assignment never read the affiliate; only roster status did, for the
        # other arm stored under it.
        assert summary['mlb_teams_queried'] == 30
        assert summary['non_mlb_teams_queried'] == [AFFILIATE]
        assert summary['non_mlb_teams_seen'] == [AFFILIATE]


# ── 12. League-wide universe ──────────────────────────────────


def test_only_mlb_clubs_decide_team_assignment(client):  # noqa: F811
    with client.application.app_context():
        for index, team_id in enumerate((484, 531, 534, 5434)):
            _pitcher(880000 + index, team_id)
        fake = CountingRosterClient(rosters={})
        evidence = build_run_roster_evidence(client=fake)
        result = sync_team_assignments(client=fake, evidence=evidence)

        queried = {team_id for team_id, _ in fake.roster_calls}
        assert queried == set(MLB_TEAM_IDS)
        assert result['teams_processed'] == 30
        assert evidence.summary()['non_mlb_teams_seen'] == [484, 531, 534, 5434]
        assert all(not is_mlb_club(team_id) for team_id in (484, 531, 534, 5434, None, 'x'))


# ── 1, 2. MLB club evidence alone ─────────────────────────────


def test_mlb_active_roster_only(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(880101, OTHER_CLUB)
        _daily({(CLUB, ROSTER_TYPE_ACTIVE): [_entry(880101, ACTIVE)],
                (CLUB, ROSTER_TYPE_40_MAN): [_entry(880101, ACTIVE)]})
        snapshot = _snapshot(pitcher.id)
        assert db.session.get(Pitcher, pitcher.id).team_id == CLUB
        assert (snapshot.team_id, snapshot.roster_status, snapshot.active_roster) == (
            CLUB, STATUS_ACTIVE, True,
        )


def test_mlb_forty_man_only(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(880102, CLUB)
        _daily({(CLUB, ROSTER_TYPE_40_MAN): [_entry(880102, OPTIONED)]})
        snapshot = _snapshot(pitcher.id)
        assert (snapshot.roster_status, snapshot.forty_man_roster, snapshot.active_roster) == (
            STATUS_OPTIONED, True, False,
        )


# ── 3, 6, 7. Club and affiliate together ──────────────────────


def test_club_and_affiliate_presence_is_not_an_mlb_conflict(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(880103, CLUB)
        _pitcher(880104, AFFILIATE)
        _, roster, _, _ = _daily(_optioned_topology(880103))
        assert db.session.get(Pitcher, pitcher.id).team_id == CLUB
        assert _snapshot(pitcher.id).team_id == CLUB
        assert roster['snapshot_conflicts'] == 0


def test_affiliate_presence_cannot_overwrite_mlb_club_identity(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(880105, CLUB)
        sync_roster_statuses(
            team_ids=[CLUB],
            client=CountingRosterClient(rosters={
                (CLUB, ROSTER_TYPE_40_MAN): [_entry(880105, OPTIONED)],
            }),
            snapshot_date=SNAPSHOT_DATE,
        )
        # A stale projection still names the affiliate.
        pitcher.team_id = AFFILIATE
        db.session.commit()

        result = sync_roster_statuses(
            team_ids=[AFFILIATE],
            client=CountingRosterClient(rosters={
                (AFFILIATE, ROSTER_TYPE_ACTIVE): [_entry(880105, ACTIVE)],
            }),
            snapshot_date=SNAPSHOT_DATE,
        )

        assert _snapshot(pitcher.id).team_id == CLUB
        assert _snapshot(pitcher.id).roster_status == STATUS_OPTIONED
        assert result['snapshot_conflicts'] == 0
        assert result['affiliate_evidence_excluded_from_mlb_authority'] == 1
        assert _open_conflicts() == 0


def test_mlb_presence_supersedes_an_earlier_affiliate_row(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(880106, AFFILIATE)
        sync_roster_statuses(
            team_ids=[AFFILIATE],
            client=CountingRosterClient(rosters={
                (AFFILIATE, ROSTER_TYPE_ACTIVE): [_entry(880106, ACTIVE)],
            }),
            snapshot_date=SNAPSHOT_DATE,
        )
        pitcher.team_id = CLUB
        db.session.commit()

        result = sync_roster_statuses(
            team_ids=[CLUB],
            client=CountingRosterClient(rosters={
                (CLUB, ROSTER_TYPE_ACTIVE): [_entry(880106, ACTIVE)],
            }),
            snapshot_date=SNAPSHOT_DATE,
        )

        snapshot = _snapshot(pitcher.id)
        assert (snapshot.team_id, snapshot.roster_status, snapshot.active_roster) == (
            CLUB, STATUS_ACTIVE, True,
        )
        assert result['affiliate_evidence_excluded_from_mlb_authority'] == 1
        assert result['snapshot_conflicts'] == 0


def test_affiliate_absence_leaves_mlb_authority_unaffected(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(880107, CLUB)
        _pitcher(880108, AFFILIATE)
        _, roster, _, _ = _daily({
            (CLUB, ROSTER_TYPE_ACTIVE): [_entry(880107, ACTIVE)],
        })
        assert _snapshot(pitcher.id).roster_status == STATUS_ACTIVE
        assert roster['snapshot_conflicts'] == 0


# ── 4, 8, 10. Affiliate evidence kept, never MLB membership ───


def test_affiliate_only_presence_is_minors_not_active(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(880109, AFFILIATE)
        _, roster, _, _ = _daily({
            (AFFILIATE, ROSTER_TYPE_ACTIVE): [_entry(880109, ACTIVE)],
        }, player_info={880109: {'currentTeam': {'id': AFFILIATE, 'name': 'Affiliate'}}})

        snapshot = _snapshot(pitcher.id)
        # Organizational membership is preserved (stored team, raw status,
        # affiliate-scoped source) ...
        assert db.session.get(Pitcher, pitcher.id).team_id == AFFILIATE
        assert snapshot.team_id == AFFILIATE
        assert snapshot.roster_status_raw_code == 'A'
        assert snapshot.source.startswith('mlb_stats_api:roster_sync:affiliate:')
        # ... but never fabricated into MLB active-roster membership.
        assert snapshot.roster_status == STATUS_MINORS
        assert snapshot.active_roster is False and snapshot.forty_man_roster is False
        assert db.session.get(Pitcher, pitcher.id).roster_status == STATUS_MINORS
        assert roster['affiliate_evidence_rows'] == 1
        assert roster['non_mlb_teams_processed'] == [AFFILIATE]


def test_historical_affiliate_rows_are_preserved_and_ranked_as_affiliate(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(880110, CLUB)
        # A row written before this rule recorded the affiliate's active roster
        # as active_roster=True. It is not rewritten ...
        legacy = RosterStatusSnapshot(
            pitcher_id=pitcher.id, mlb_id=880110, team_id=AFFILIATE,
            snapshot_date=date(2026, 9, 29), roster_status=STATUS_ACTIVE,
            active_roster=True, forty_man_roster=False,
            source='mlb_stats_api:roster_sync:active',
        )
        db.session.add(legacy)
        db.session.commit()
        sync_roster_statuses(
            team_ids=[CLUB],
            client=CountingRosterClient(rosters={
                (CLUB, ROSTER_TYPE_40_MAN): [_entry(880110, OPTIONED)],
            }),
            snapshot_date=SNAPSHOT_DATE,
        )
        kept = RosterStatusSnapshot.query.filter_by(
            pitcher_id=pitcher.id, snapshot_date=date(2026, 9, 29),
        ).one()
        assert (kept.team_id, kept.roster_status, kept.active_roster) == (
            AFFILIATE, STATUS_ACTIVE, True,
        )
        # ... and still ranks below MLB club presence deterministically.
        assert snapshot_authority_rank(kept) == AUTHORITY_AFFILIATE
        assert snapshot_authority_rank(_snapshot(pitcher.id)) == AUTHORITY_MLB_CLUB


# ── 5, 13. Two MLB clubs still fail closed ────────────────────


def test_two_mlb_clubs_the_same_date_still_fail_closed(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(880111, CLUB)
        sync_roster_statuses(
            team_ids=[CLUB],
            client=CountingRosterClient(rosters={
                (CLUB, ROSTER_TYPE_ACTIVE): [_entry(880111, ACTIVE)],
            }),
            snapshot_date=SNAPSHOT_DATE,
        )
        pitcher.team_id = OTHER_CLUB
        db.session.commit()

        result = sync_roster_statuses(
            team_ids=[OTHER_CLUB],
            client=CountingRosterClient(rosters={
                (OTHER_CLUB, ROSTER_TYPE_ACTIVE): [_entry(880111, ACTIVE)],
            }),
            snapshot_date=SNAPSHOT_DATE,
        )

        assert _snapshot(pitcher.id).team_id == CLUB
        assert result['snapshot_conflicts'] == 1
        assert result['true_mlb_roster_conflicts'] == 1
        assert result['records_failed'] == 1
        failure = SyncFailure.query.filter_by(
            entity_type=ROSTER_STATUS_CONFLICT_ENTITY_TYPE, resolved=False,
        ).one()
        assert failure.payload['existing_authority_rank'] == AUTHORITY_MLB_CLUB
        assert failure.payload['incoming_authority_rank'] == AUTHORITY_MLB_CLUB


def test_two_mlb_club_active_rosters_leave_assignment_ambiguous(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(880112, CLUB)
        assignment, _, _, _ = _daily({
            (CLUB, ROSTER_TYPE_ACTIVE): [_entry(880112, ACTIVE)],
            (OTHER_CLUB, ROSTER_TYPE_ACTIVE): [_entry(880112, ACTIVE)],
        })
        refreshed = db.session.get(Pitcher, pitcher.id)
        assert refreshed.team_assignment_source.endswith('ambiguous:active')


def test_two_affiliates_the_same_date_fail_closed(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(880113, AFFILIATE)
        sync_roster_statuses(
            team_ids=[AFFILIATE],
            client=CountingRosterClient(rosters={
                (AFFILIATE, ROSTER_TYPE_ACTIVE): [_entry(880113, ACTIVE)],
            }),
            snapshot_date=SNAPSHOT_DATE,
        )
        pitcher.team_id = OTHER_AFFILIATE
        db.session.commit()
        result = sync_roster_statuses(
            team_ids=[OTHER_AFFILIATE],
            client=CountingRosterClient(rosters={
                (OTHER_AFFILIATE, ROSTER_TYPE_ACTIVE): [_entry(880113, ACTIVE)],
            }),
            snapshot_date=SNAPSHOT_DATE,
        )
        assert result['snapshot_conflicts'] == 1
        assert result['true_mlb_roster_conflicts'] == 0


# ── 9. Same-day move between MLB clubs ────────────────────────


def test_same_day_trade_between_clubs_follows_existing_rules(client):  # noqa: F811
    with client.application.app_context():
        pitcher = _pitcher(880114, CLUB)
        # Earlier: on CLUB's 40-man. Now absent from CLUB, active on OTHER_CLUB.
        sync_roster_statuses(
            team_ids=[CLUB],
            client=CountingRosterClient(rosters={}),
            snapshot_date=SNAPSHOT_DATE,
        )
        _daily({(OTHER_CLUB, ROSTER_TYPE_ACTIVE): [_entry(880114, ACTIVE)]})
        assert db.session.get(Pitcher, pitcher.id).team_id == OTHER_CLUB
        assert _snapshot(pitcher.id).team_id == OTHER_CLUB


# ── Precedence table ──────────────────────────────────────────


@pytest.mark.parametrize('existing, incoming, expected', [
    ((CLUB, True), (AFFILIATE, True), PRECEDENCE_RETAIN_EXISTING),
    ((AFFILIATE, True), (CLUB, True), PRECEDENCE_SUPERSEDE_EXISTING),
    ((AFFILIATE, True), (CLUB, None), PRECEDENCE_RETAIN_EXISTING),
    ((CLUB, None), (AFFILIATE, True), PRECEDENCE_SUPERSEDE_EXISTING),
    ((CLUB, True), (OTHER_CLUB, True), PRECEDENCE_CONFLICT),
    ((AFFILIATE, True), (OTHER_AFFILIATE, True), PRECEDENCE_CONFLICT),
    ((CLUB, None), (OTHER_CLUB, None), PRECEDENCE_CONFLICT),
    ((CLUB, True), (OTHER_CLUB, None), PRECEDENCE_RETAIN_EXISTING),
])
def test_authority_precedence_table(existing, incoming, expected):
    def row(team_id, presence):
        return {'team_id': team_id, 'active_roster': presence, 'forty_man_roster': presence}
    assert same_date_team_precedence(row(*existing), row(*incoming)) == expected


def test_authority_ranks():
    assert snapshot_authority_rank({'team_id': CLUB, 'active_roster': None,
                                    'forty_man_roster': None}) == AUTHORITY_ABSENT
    assert snapshot_authority_rank({'team_id': AFFILIATE, 'active_roster': False,
                                    'forty_man_roster': False}) == AUTHORITY_AFFILIATE
    assert snapshot_authority_rank({'team_id': CLUB, 'active_roster': False,
                                    'forty_man_roster': True}) == AUTHORITY_MLB_CLUB
