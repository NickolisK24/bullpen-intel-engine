"""
Tests for authoritative roster-status ingestion from MLB roster endpoints.

These use fake MLB roster payloads and in-memory SQLite; no network calls.
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.prospect  # noqa: F401
import services.sync as sync_service
from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_run import SyncRun
from services.roster_status import (
    STATUS_40_MAN_ONLY,
    STATUS_ACTIVE,
    STATUS_BEREAVEMENT,
    STATUS_DFA,
    STATUS_IL_15,
    STATUS_IL_60,
    STATUS_MINORS,
    STATUS_NON_ROSTER,
    STATUS_OPTIONED,
    STATUS_UNKNOWN,
)
from services.roster_status_sync import (
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_FULL,
    ROSTER_TYPE_NON_ROSTER,
    classify_roster_evidence,
    sync_roster_statuses,
)
from services.bullpen_eligibility import (
    STATUS_NON_PITCHER,
    evaluate_bullpen_eligibility,
)
from utils.db import db


class FakeRosterClient:
    def __init__(self, rosters):
        self.rosters = rosters
        self.calls = []

    def get_team_roster(self, team_id, roster_type='pitchers', **_kwargs):
        self.calls.append((team_id, roster_type))
        value = self.rosters.get((team_id, roster_type), [])
        if isinstance(value, Exception):
            raise value
        return list(value)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def roster_entry(player_id, name, position='P', status=None):
    entry = {
        'person': {'id': player_id, 'fullName': name},
        'position': {'abbreviation': position},
    }
    if status is not None:
        entry['status'] = status
    return entry


def seed_pitcher(name, mlb_id, team_id=113, days_ago=1, innings=1.0):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation='CIN' if team_id == 113 else f'T{team_id}',
        position='P',
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=mlb_id * 10,
        game_date=date.today() - timedelta(days=days_ago),
        pitches_thrown=12,
        innings_pitched=innings,
        innings_pitched_outs=round(innings * 3),
        games_started=1 if innings >= 3 else 0,
        game_type='R',
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        raw_score=10.0,
        risk_level='LOW',
        calculated_at=datetime.utcnow(),
    ))
    db.session.commit()
    return pitcher


def seed_successful_roster_sync_run(timestamp=None):
    timestamp = timestamp or datetime.utcnow()
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


def reds_rosters():
    return {
        (113, ROSTER_TYPE_ACTIVE): [
            roster_entry(11320, 'Reds Active Relief Context', status={'code': 'A', 'description': 'Active'}),
            roster_entry(668881, 'Hunter Greene', status={'code': 'A', 'description': 'Active'}),
            roster_entry(671096, 'Andrew Abbott', status={'code': 'A', 'description': 'Active'}),
            roster_entry(666157, 'Nick Lodolo', status={'code': 'A', 'description': 'Active'}),
            roster_entry(663903, 'Brady Singer', status={'code': 'A', 'description': 'Active'}),
        ],
        (113, ROSTER_TYPE_40_MAN): [
            roster_entry(11320, 'Reds Active Relief Context', status={'code': 'A', 'description': 'Active'}),
            roster_entry(668881, 'Hunter Greene', status={'code': 'A', 'description': 'Active'}),
            roster_entry(671096, 'Andrew Abbott', status={'code': 'A', 'description': 'Active'}),
            roster_entry(666157, 'Nick Lodolo', status={'code': 'A', 'description': 'Active'}),
            roster_entry(663903, 'Brady Singer', status={'code': 'A', 'description': 'Active'}),
            roster_entry(668933, 'Graham Ashcraft', status={'code': 'D60', 'description': '60-day IL'}),
            roster_entry(572955, 'Pierce Johnson', status={'code': 'D15', 'description': '15-day IL'}),
            roster_entry(641941, 'Emilio Pagan', status={'code': 'D15', 'description': '15-day IL'}),
            roster_entry(695076, 'Rhett Lowder', status='Optioned to minors'),
            roster_entry(663886, 'Brandon Williamson', status='Designated for assignment'),
            roster_entry(700002, '40-man Context Pitcher'),
        ],
        (113, ROSTER_TYPE_FULL): [
            roster_entry(11320, 'Reds Active Relief Context', status='Active'),
            roster_entry(668881, 'Hunter Greene', status='Active'),
            roster_entry(671096, 'Andrew Abbott', status='Active'),
            roster_entry(666157, 'Nick Lodolo', status='Active'),
            roster_entry(663903, 'Brady Singer', status='Active'),
            roster_entry(668933, 'Graham Ashcraft', status='60-day injured list'),
            roster_entry(572955, 'Pierce Johnson', status='15-day injured list'),
            roster_entry(641941, 'Emilio Pagan', status='15-day injured list'),
            roster_entry(683175, 'Connor Phillips'),
            roster_entry(683742, 'Jose Franco', status='Minors'),
            roster_entry(810001, 'Chase Burns'),
            roster_entry(695076, 'Rhett Lowder', status='Optioned to minors'),
            roster_entry(663886, 'Brandon Williamson', status='Designated for assignment'),
        ],
        (113, ROSTER_TYPE_NON_ROSTER): [
            roster_entry(700001, 'Non Roster Pitcher'),
        ],
    }


def test_classifies_merged_roster_evidence_by_precedence():
    assert classify_roster_evidence({
        'roster_types': {ROSTER_TYPE_ACTIVE, ROSTER_TYPE_FULL},
        'raw_statuses': [(ROSTER_TYPE_FULL, 'Minors')],
    })['status'] == STATUS_ACTIVE
    assert classify_roster_evidence({
        'roster_types': {ROSTER_TYPE_FULL},
        'raw_statuses': [],
    })['status'] == STATUS_MINORS
    full_roster_active = classify_roster_evidence({
        'roster_types': {ROSTER_TYPE_FULL},
        'raw_statuses': [(ROSTER_TYPE_FULL, 'Active')],
    })
    assert full_roster_active['status'] == STATUS_MINORS
    assert full_roster_active['source'] == 'mlb_stats_api:roster_sync:fullRoster'
    assert classify_roster_evidence({
        'roster_types': {ROSTER_TYPE_NON_ROSTER},
        'raw_statuses': [],
    })['status'] == STATUS_NON_ROSTER
    assert classify_roster_evidence({
        'roster_types': {ROSTER_TYPE_40_MAN},
        'raw_statuses': [],
    })['status'] == STATUS_40_MAN_ONLY
    bereavement = classify_roster_evidence({
        'roster_types': {ROSTER_TYPE_40_MAN},
        'raw_statuses': [(
            ROSTER_TYPE_40_MAN,
            {
                'raw_status': 'BRV',
                'raw_status_code': 'BRV',
                'raw_status_description': 'Bereavement List',
            },
        )],
    })
    assert bereavement['status'] == STATUS_BEREAVEMENT
    assert bereavement['raw_status_code'] == 'BRV'
    assert bereavement['raw_status_description'] == 'Bereavement List'


def test_roster_sync_corrects_position_player_pitching_identity_population(client):
    """Production-equivalent Vargas shape: a prior pitching appearance created
    a stale local ``P`` identity, while current official roster evidence says
    the active player is a first baseman.
    """
    with client.application.app_context():
        player = seed_pitcher('Ildemaro Vargas', 545121)
        rosters = {
            (113, ROSTER_TYPE_ACTIVE): [
                roster_entry(
                    545121, 'Ildemaro Vargas', position='1B',
                    status={'code': 'A', 'description': 'Active'},
                ),
            ],
            (113, ROSTER_TYPE_40_MAN): [
                roster_entry(
                    545121, 'Ildemaro Vargas', position='1B',
                    status={'code': 'A', 'description': 'Active'},
                ),
            ],
            (113, ROSTER_TYPE_FULL): [],
            (113, ROSTER_TYPE_NON_ROSTER): [],
        }

        result = sync_roster_statuses(
            team_ids=[113], client=FakeRosterClient(rosters),
        )

        db.session.refresh(player)
        assert result['errors'] == 0
        assert player.roster_status == STATUS_ACTIVE
        assert player.position == '1B'
        eligibility = evaluate_bullpen_eligibility(
            player, player.game_logs, reference_date=date.today(),
        )
        assert eligibility['eligible'] is False
        assert eligibility['status'] == STATUS_NON_PITCHER
        board = client.get('/api/bullpen/teams/113/board').get_json()
        assert all(
            card['pitcher_id'] != player.id
            for group in board['groups']
            for card in group['pitchers']
        )


def test_sync_persists_authoritative_roster_statuses(client):
    with client.application.app_context():
        seed_pitcher('Reds Active Relief Context', 11320)
        seed_pitcher('Hunter Greene', 668881)
        seed_pitcher('Andrew Abbott', 671096)
        seed_pitcher('Nick Lodolo', 666157)
        seed_pitcher('Brady Singer', 663903)
        seed_pitcher('Graham Ashcraft', 668933)
        seed_pitcher('Pierce Johnson', 572955)
        seed_pitcher('Emilio Pagan', 641941)
        seed_pitcher('Connor Phillips', 683175)
        seed_pitcher('Jose Franco', 683742)
        seed_pitcher('Chase Burns', 810001)
        seed_pitcher('Rhett Lowder', 695076)
        seed_pitcher('Brandon Williamson', 663886)
        seed_pitcher('Non Roster Pitcher', 700001)
        seed_pitcher('40-man Context Pitcher', 700002)
        seed_pitcher('Missing Roster Arm', 999999)

        result = sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient(reds_rosters()),
            timestamp=datetime(2026, 6, 7, 12, 0, 0),
        )

        by_name = {pitcher.full_name: pitcher for pitcher in Pitcher.query.all()}
        snapshot_by_mlb_id = {
            snapshot.mlb_id: snapshot
            for snapshot in RosterStatusSnapshot.query.all()
        }

    assert result['teams_processed'] == 1
    assert result['pitchers_refreshed'] == 16
    assert result['snapshots_created'] == 16
    assert len(snapshot_by_mlb_id) == 16
    assert result['by_status'][STATUS_ACTIVE] == 5
    assert result['by_status'][STATUS_IL_60] == 1
    assert result['by_status'][STATUS_IL_15] == 2
    assert result['by_status'][STATUS_MINORS] == 3
    assert result['by_status'][STATUS_OPTIONED] == 1
    assert result['by_status'][STATUS_DFA] == 1
    assert result['by_status'][STATUS_NON_ROSTER] == 1
    assert result['by_status'][STATUS_40_MAN_ONLY] == 1
    assert result['by_status'][STATUS_UNKNOWN] == 1
    assert by_name['Reds Active Relief Context'].roster_status == STATUS_ACTIVE
    assert by_name['Hunter Greene'].roster_status == STATUS_ACTIVE
    assert by_name['Andrew Abbott'].roster_status == STATUS_ACTIVE
    assert by_name['Nick Lodolo'].roster_status == STATUS_ACTIVE
    assert by_name['Brady Singer'].roster_status == STATUS_ACTIVE
    assert by_name['Graham Ashcraft'].roster_status == STATUS_IL_60
    assert by_name['Graham Ashcraft'].roster_status_raw_code == 'D60'
    assert by_name['Graham Ashcraft'].roster_status_raw_description == '60-day IL'
    assert by_name['Pierce Johnson'].roster_status == STATUS_IL_15
    assert by_name['Emilio Pagan'].roster_status == STATUS_IL_15
    assert by_name['Connor Phillips'].roster_status == STATUS_MINORS
    assert by_name['Jose Franco'].roster_status == STATUS_MINORS
    assert by_name['Chase Burns'].roster_status == STATUS_MINORS
    assert by_name['Rhett Lowder'].roster_status == STATUS_OPTIONED
    assert by_name['Brandon Williamson'].roster_status == STATUS_DFA
    assert by_name['Non Roster Pitcher'].roster_status == STATUS_NON_ROSTER
    assert by_name['40-man Context Pitcher'].roster_status == STATUS_40_MAN_ONLY
    assert by_name['Missing Roster Arm'].roster_status == STATUS_UNKNOWN
    assert by_name['Graham Ashcraft'].roster_status_source == 'mlb_stats_api:roster_sync:40Man'
    assert by_name['Missing Roster Arm'].roster_status_source == 'mlb_stats_api:roster_sync:unavailable'
    assert by_name['Graham Ashcraft'].roster_status_updated_at == datetime(2026, 6, 7, 12, 0, 0)
    assert snapshot_by_mlb_id[668933].roster_status == STATUS_IL_60
    assert snapshot_by_mlb_id[668933].source == 'mlb_stats_api:roster_sync:40Man'


def test_sync_preserves_bereavement_status_instead_of_collapsing_to_40_man(client):
    with client.application.app_context():
        pitcher = seed_pitcher('Mason Miller', 695243, team_id=135)
        result = sync_roster_statuses(
            team_ids=[135],
            client=FakeRosterClient({
                (135, ROSTER_TYPE_40_MAN): [
                    roster_entry(
                        695243,
                        'Mason Miller',
                        status={'code': 'BRV', 'description': 'Bereavement List'},
                    ),
                ],
            }),
            timestamp=datetime(2026, 6, 17, 21, 17, 16),
        )
        updated = db.session.get(Pitcher, pitcher.id)

    assert result['by_status'][STATUS_BEREAVEMENT] == 1
    assert updated.roster_status == STATUS_BEREAVEMENT
    assert updated.roster_status_source == 'mlb_stats_api:roster_sync:40Man'
    assert updated.roster_status_raw_code == 'BRV'
    assert updated.roster_status_raw_description == 'Bereavement List'


def test_roster_fetch_failure_preserves_prior_status(client):
    with client.application.app_context():
        pitcher = seed_pitcher('Reds Active Relief Context', 11320)
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
        snapshot_count = RosterStatusSnapshot.query.count()

    assert result['errors'] == 1
    assert result['pitchers_refreshed'] == 0
    assert snapshot_count == 0
    assert updated.roster_status == STATUS_ACTIVE
    assert updated.roster_status_source == 'prior_sync'


def test_roster_sync_feeds_default_board_filtering_and_context_labels(client):
    with client.application.app_context():
        seed_pitcher('Reds Active Relief Context', 11320)
        seed_pitcher('Graham Ashcraft', 668933)
        seed_pitcher('Pierce Johnson', 572955)
        seed_pitcher('Connor Phillips', 683175)
        seed_pitcher('Jose Franco', 683742)
        sync_run = seed_successful_roster_sync_run()
        sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient(reds_rosters()),
            sync_run_id=sync_run.id,
            snapshot_date=date.today(),
        )

    default_body = client.get('/api/bullpen/teams/113/board').get_json()
    default_cards = [card for group in default_body['groups'] for card in group['pitchers']]
    assert [card['name'] for card in default_cards] == ['Reds Active Relief Context']
    # 4 off-roster arms counted by Roster Authority (legacy roster_status summary retired CRC-10).
    assert default_body['roster_authority']['counts']['inactive_roster_context_count'] == 4

    context_body = client.get('/api/bullpen/teams/113/board?include_stale=true').get_json()
    context_cards = [card for group in context_body['groups'] for card in group['pitchers']]
    by_name = {card['name']: card for card in context_cards}

    assert by_name['Graham Ashcraft']['roster_status']['label'] == '60-Day IL'
    assert by_name['Pierce Johnson']['roster_status']['label'] == '15-Day IL'
    assert by_name['Connor Phillips']['roster_status']['label'] == 'Optioned / Minors'
    assert by_name['Jose Franco']['roster_status']['label'] == 'Optioned / Minors'
    assert all(card['availability_status'] != 'Available' for name, card in by_name.items() if name != 'Reds Active Relief Context')


# ── Pitcher projection fence (migration e3f6a9b2c5d8) ─────────────────────────
# Production PostgreSQL restores the OLD roster-status cache of a pitcher that
# has a current active/40-man roster_membership_intervals row unless the writing
# transaction declares baseballos.roster_owner for the pitcher's team. These
# tests run the real sync against the real migrated schema.

from sqlalchemy import text  # noqa: E402

import services.roster_status_sync as roster_status_sync_module  # noqa: E402
from services import public_roster_readiness, source_readiness  # noqa: E402
from tests.test_schedule_ingestion import fenced_app, fenced_database_url  # noqa: E402,F401

_FENCE_TIMESTAMP = datetime(2026, 9, 25, 15, 20, 0)


def _seed_adopted_pitcher(mlb_id, name, team_id):
    """A pitcher adopted by the sync-pipeline runtime: current active interval."""
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=name, team_id=team_id, position='P', active=True,
        roster_status=STATUS_ACTIVE, roster_status_source='mlb_stats_api:roster_sync:active',
        roster_status_raw_code='A', roster_status_raw_description='Active',
        roster_status_updated_at=_FENCE_TIMESTAMP - timedelta(days=2),
    )
    db.session.add(pitcher)
    db.session.flush()
    # The interval's evidence lineage is irrelevant to the trigger under test;
    # this disposable database drops that foreign key instead of fabricating
    # source-observation evidence.
    db.session.execute(text(
        'ALTER TABLE roster_membership_intervals DROP CONSTRAINT IF EXISTS '
        'roster_membership_intervals_opened_by_observation_id_fkey'
    ))
    db.session.execute(text(
        "INSERT INTO roster_membership_intervals (pitcher_id, player_mlb_id, team_id,"
        " membership_type, effective_start_date, authority_type, opened_by_observation_id,"
        " is_current_version, is_void, created_at, updated_at) "
        "VALUES (:pitcher, :mlb, :team, 'active_roster', '2026-09-01', 'official_roster',"
        " 1, true, false, now(), now())"
    ), {'pitcher': pitcher.id, 'mlb': mlb_id, 'team': team_id})
    db.session.commit()
    return pitcher.id


def _fenced_rosters():
    injured = {'code': 'D15', 'description': '15-day IL'}
    active = {'code': 'A', 'description': 'Active'}
    return {
        (108, ROSTER_TYPE_ACTIVE): [roster_entry(910801, 'Angels Active Arm', status=active)],
        (108, ROSTER_TYPE_40_MAN): [
            roster_entry(910801, 'Angels Active Arm', status=active),
            roster_entry(910802, 'Angels Injured Arm', status=injured),
        ],
        (109, ROSTER_TYPE_ACTIVE): [],
        (109, ROSTER_TYPE_40_MAN): [roster_entry(910901, 'Diamondbacks Injured Arm', status=injured)],
    }


def _stale_suppressed_pitcher_ids():
    return {
        int(key) for (key,) in db.session.execute(text(
            "SELECT resource_key FROM compatibility_write_events "
            "WHERE resource_type='pitcher_projection' AND outcome='stale_suppressed'"
        ))
    }


def _team_roster_claims_available(team_id):
    family = {
        'status': source_readiness.DEGRADED,
        'fail_closed': True,
        'reason_codes': ['roster_status_cache_divergence'],
    }
    readiness = public_roster_readiness.build_public_roster_readiness(
        team_id=team_id, family=family,
    )
    return public_roster_readiness.roster_claims_available(readiness)


def _run_fenced_sync():
    return sync_roster_statuses(
        team_ids=[108, 109],
        client=FakeRosterClient(_fenced_rosters()),
        timestamp=_FENCE_TIMESTAMP,
    )


def test_fenced_roster_sync_persists_official_status_for_adopted_pitchers(fenced_app):
    assert db.session.execute(text(
        "SELECT count(*) FROM pg_trigger WHERE tgname='baseballos_pitcher_projection_fence'"
    )).scalar() == 1
    active_id = _seed_adopted_pitcher(910801, 'Angels Active Arm', 108)
    injured_id = _seed_adopted_pitcher(910802, 'Angels Injured Arm', 108)
    other_id = _seed_adopted_pitcher(910901, 'Diamondbacks Injured Arm', 109)

    result = _run_fenced_sync()
    db.session.remove()

    assert result['errors'] == 0
    assert db.session.get(Pitcher, active_id).roster_status == STATUS_ACTIVE
    injured = db.session.get(Pitcher, injured_id)
    assert injured.roster_status == STATUS_IL_15
    assert injured.roster_status_raw_code == 'D15'
    assert db.session.get(Pitcher, other_id).roster_status == STATUS_IL_15
    assert _stale_suppressed_pitcher_ids() == set()
    assert roster_status_sync_module.roster_status_cache_divergences(team_ids=[108, 109]) == []
    assert _team_roster_claims_available(108) is True


def test_undeclared_fenced_roster_write_is_the_team_state_108_failure(fenced_app, monkeypatch):
    """Without the ownership declaration the fence reproduces production run 718."""
    _seed_adopted_pitcher(910801, 'Angels Active Arm', 108)
    injured_id = _seed_adopted_pitcher(910802, 'Angels Injured Arm', 108)
    monkeypatch.setattr(roster_status_sync_module, '_declare_roster_ownership', lambda _team_id: None)

    result = _run_fenced_sync()
    db.session.remove()

    # The ORM counted the write; the trigger silently restored the old cache.
    assert result['pitchers_changed'] >= 1
    assert db.session.get(Pitcher, injured_id).roster_status == STATUS_ACTIVE
    assert injured_id in _stale_suppressed_pitcher_ids()
    divergences = roster_status_sync_module.roster_status_cache_divergences(team_ids=[108])
    assert [row['pitcher_id'] for row in divergences] == [injured_id]
    assert _team_roster_claims_available(108) is False


def test_roster_ownership_declaration_is_scoped_to_one_team(fenced_app):
    other_id = _seed_adopted_pitcher(910901, 'Diamondbacks Injured Arm', 109)
    roster_status_sync_module._declare_roster_ownership(108)
    pitcher = db.session.get(Pitcher, other_id)
    pitcher.roster_status = STATUS_IL_15
    db.session.commit()
    db.session.remove()

    assert db.session.get(Pitcher, other_id).roster_status == STATUS_ACTIVE
    assert other_id in _stale_suppressed_pitcher_ids()
