"""TN-01: the trusted, publication-bound Tonight v1 read model.

Every fixture is a real trusted Dashboard publication built by the production
builder (frozen ``trusted_team_boards`` package), plus ``slate_games`` rows for
the publication's baseball date. Tonight must project exactly the Team Board
facts of that one snapshot, and read no FatigueScore or GameLog doing it.
"""

from copy import deepcopy
from datetime import datetime, timedelta
import importlib
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from models.dashboard_snapshot import DashboardSnapshot
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.slate_game import SlateGame
from models.sync_run import SyncRun
from models.tonight_intelligence_snapshot import TonightIntelligenceSnapshot
from models.tonight_publication import TonightPublication, TonightPublicationImmutable
from services import dashboard_snapshot
from services import public_serving_authority
from services import slate_coverage
from services import sync as sync_service
from services import tonight_intelligence_snapshot
from services import tonight_read_model
from services.fatigue import calculate_fatigue
from services.team_board_snapshot_team_state import CONTRACT as RECEIPT_CONTRACT
from services.team_state_vnext_production_proof import EXPECTED_METHOD_VERSION
from tests.db_config import (
    create_test_schema,
    drop_test_schema,
    test_database_url as _test_database_url,
)
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
from utils.db import db
from utils.time import utc_now_naive


SF, LAD, NYY, BOS, DET, MIN = 137, 119, 147, 111, 116, 142
TEAMS = {
    SF: ('SF', 'San Francisco Giants', 11),
    LAD: ('LAD', 'Los Angeles Dodgers', 4),
    NYY: ('NYY', 'New York Yankees', 4),
    BOS: ('BOS', 'Boston Red Sox', 4),
    DET: ('DET', 'Detroit Tigers', 4),
    MIN: ('MIN', 'Minnesota Twins', 4),
}
STATES = {SF: 'stretched', LAD: 'fresh', NYY: 'vulnerable', BOS: 'fresh',
          DET: 'stretched', MIN: 'fresh'}
RESOLVED = GameLog.APPEARANCE_TEAM_RESOLVED


def _complete_coverage(day, *_args, **_kwargs):
    return {
        'slate_date': day.isoformat(),
        'complete_enough_to_publish': True,
        'coverage_known': True,
        'validations_passed': True,
        'reason_codes': ['slate_complete'],
    }


def _dashboard_payload(reference_date):
    data_through = reference_date - timedelta(days=1)
    coverage = _complete_coverage(data_through)
    return {
        'capability': 'bullpen_dashboard',
        'generated_at': utc_now_naive().isoformat(),
        'ranking_applied': False,
        'selection_made': False,
        'scope': 'bullpen_eligible',
        'context': {},
        'roles': {'order': [], 'counts': {}, 'total': 0},
        'landscape': {},
        'freshness': {
            'data_through': data_through.isoformat(),
            'latest_workload_date': data_through.isoformat(),
            'availability_reference_date': reference_date.isoformat(),
            'reference_date': reference_date.isoformat(),
            'sync_status': 'success',
            'last_successful_sync': utc_now_naive().isoformat(),
            'slate_coverage': coverage,
            'validations_passed': True,
            'complete_enough_to_publish': True,
        },
        'availability_summary': {},
    }


def _seed_teams(reference_date):
    anchor = reference_date - timedelta(days=1)
    game_pk = [9_000_000]

    def add(pitcher, team_id, day, *, gs=0, outs=3, pitches=15, save=False, hold=False):
        game_pk[0] += 1
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=game_pk[0], game_date=day,
            game_type='R', games_started=gs, innings_pitched=outs / 3,
            innings_pitched_outs=outs, pitches_thrown=pitches,
            appearance_team_id=team_id, appearance_team_status=RESOLVED,
            appearance_team_source='boxscore_side',
            appearance_team_reason='appearance_team_resolved_boxscore',
            save=save, hold=hold,
        ))

    pitchers = {}
    for team_id, (abbreviation, name, arm_count) in TEAMS.items():
        long_index = 6 if team_id == SF else 3
        for index in range(arm_count):
            pitcher = Pitcher(
                mlb_id=team_id * 1000 + index, full_name=f'{abbreviation} Arm {index:02d}',
                team_id=team_id, team_name=name, team_abbreviation=abbreviation,
                position='P', active=True, roster_status='active',
                roster_status_source='test_fixture',
                roster_status_updated_at=utc_now_naive(),
            )
            db.session.add(pitcher)
            db.session.flush()
            pitchers.setdefault(team_id, []).append(pitcher)
            # Relief history keeps every arm bullpen-eligible; the first two
            # arms carry save and hold evidence for governed late-inning roles.
            for day in range(8, 30, 2):
                add(pitcher, team_id, anchor - timedelta(days=day),
                    save=index == 0, hold=index == 1,
                    # One long reliever per club keeps the coverage layer populated.
                    outs=9 if index == long_index else 3,
                    pitches=40 if index == long_index else 15)
    sf = pitchers[SF]
    # Two SF arms work back-to-back; one of them works three of the last four days.
    for day in (0, 1, 3):
        add(sf[2], SF, anchor - timedelta(days=day), pitches=22)
    for day in (0, 1):
        add(sf[3], SF, anchor - timedelta(days=day), pitches=18)
    add(sf[4], SF, anchor - timedelta(days=2), outs=6, pitches=35)
    # An SF swing arm made a conventional start: physical workload, not bullpen display.
    add(sf[5], SF, anchor - timedelta(days=4), gs=1, outs=17, pitches=82)
    for team_id in (LAD, NYY, BOS, DET, MIN):
        add(pitchers[team_id][2], team_id, anchor - timedelta(days=1), pitches=12)
    db.session.flush()

    for team_pitchers in pitchers.values():
        for pitcher in team_pitchers:
            logs = (
                GameLog.query.filter_by(pitcher_id=pitcher.id)
                .order_by(GameLog.game_date.desc()).all()
            )
            score = calculate_fatigue(pitcher, logs, reference_date=reference_date)
            score.calculated_at = utc_now_naive()
            db.session.add(score)
    db.session.commit()
    return pitchers


def _attach_receipts(snapshot, states=STATES):
    """Freeze Team State receipts the way the pre-trust proof does."""
    payload = deepcopy(snapshot.payload)
    package = payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY]
    represented = snapshot.data_through.isoformat()
    package['frozen_team_state_by_team_id'] = {
        str(team_id): {
            'contract': RECEIPT_CONTRACT,
            'team_id': team_id,
            'dashboard_snapshot_id': snapshot.id,
            'represented_date': represented,
            'method_version': EXPECTED_METHOD_VERSION,
            'value': {
                'available': True,
                'public_state': state,
                'public_label': state.capitalize(),
                'summary': f'{state} summary.',
                'outcome': 'available',
                'unavailable_message': None,
                'reason_code': None,
                'data_through': represented,
            },
        }
        for team_id, state in states.items()
    }
    snapshot.payload = payload
    db.session.commit()
    return snapshot


def _slate(reference_date):
    first = datetime(reference_date.year, reference_date.month, reference_date.day, 23, 5)
    rows = [
        # Deliberately out of first-pitch order.
        SlateGame(game_pk=801, game_date_et=reference_date, game_time_utc=first + timedelta(hours=2),
                  away_team_id=LAD, home_team_id=SF, normalized_state='upcoming',
                  status_detailed='Scheduled', game_number=1),
        SlateGame(game_pk=802, game_date_et=reference_date, game_time_utc=first,
                  away_team_id=BOS, home_team_id=NYY, normalized_state='cancelled',
                  status_detailed='Postponed', game_number=1),
        SlateGame(game_pk=804, game_date_et=reference_date, game_time_utc=first - timedelta(hours=5),
                  away_team_id=MIN, home_team_id=DET, normalized_state='upcoming',
                  status_detailed='Scheduled', game_number=2, doubleheader_flag='S'),
        SlateGame(game_pk=803, game_date_et=reference_date, game_time_utc=first - timedelta(hours=6),
                  away_team_id=MIN, home_team_id=DET, normalized_state='upcoming',
                  status_detailed='Scheduled', game_number=1, doubleheader_flag='S'),
        # A non-MLB organization never becomes a Tonight side.
        SlateGame(game_pk=805, game_date_et=reference_date, game_time_utc=first,
                  away_team_id=5555, home_team_id=SF, normalized_state='upcoming',
                  status_detailed='Scheduled', game_number=1),
        # Another day's game is not on tonight's slate.
        SlateGame(game_pk=806, game_date_et=reference_date + timedelta(days=1),
                  game_time_utc=first + timedelta(days=1),
                  away_team_id=SF, home_team_id=LAD, normalized_state='upcoming',
                  status_detailed='Scheduled', game_number=1),
    ]
    db.session.add_all(rows)
    db.session.commit()


def _publish(reference_date, *, source='tonight_v1_test'):
    run = SyncRun(
        job_name='tonight_v1_test',
        started_at=utc_now_naive() - timedelta(minutes=2),
        completed_at=utc_now_naive() - timedelta(minutes=1),
        status='success', stage='published', source='test',
        latest_game_date=reference_date - timedelta(days=1),
        latest_workload_date=reference_date - timedelta(days=1),
        latest_fatigue_calculated_at=utc_now_naive(),
    )
    db.session.add(run)
    db.session.flush()
    snapshot = dashboard_snapshot.build_bullpen_dashboard_snapshot(
        sync_run_id=run.id, source=source, publish=True, raise_errors=True,
    )
    assert snapshot.is_published is True, (snapshot.status, snapshot.error_message)
    return _attach_receipts(snapshot)


@pytest.fixture
def tonight_app(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', _test_database_url())
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = importlib.import_module('app').create_app('test')
    app.config['TRUSTED_PUBLIC_SERVING_ENABLED'] = True
    # Projection is exercised explicitly per test, not as a publish side effect.
    app.config['TONIGHT_V1_PROJECTION_ENABLED'] = False
    with app.app_context():
        create_test_schema(app)
        try:
            reference_date = public_serving_authority.product_current_date()
            pitchers = _seed_teams(reference_date)
            seed_roster_readiness_snapshots([reference_date])
            monkeypatch.setattr(slate_coverage, 'compute_slate_coverage', _complete_coverage)
            from api import bullpen as bullpen_api
            monkeypatch.setattr(
                bullpen_api, 'build_bullpen_dashboard_payload',
                lambda **_kwargs: _dashboard_payload(reference_date),
            )
            assert public_serving_authority.install_public_serving_authority(app) is True
            snapshot = _publish(reference_date)
            _slate(reference_date)
            yield SimpleNamespace(
                app=app, snapshot=snapshot, pitchers=pitchers,
                reference_date=reference_date,
            )
        finally:
            db.session.remove()
            drop_test_schema(app)


@pytest.fixture
def mutable_reads(tonight_app):
    reads = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        reads.append(statement.lower())

    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        yield reads
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)


def _build(env, snapshot=None):
    snapshot = snapshot or env.snapshot
    return tonight_read_model.build_tonight_v1(
        snapshot,
        tonight_read_model.load_slate_games(snapshot.availability_reference_date),
        generated_at=datetime(2026, 9, 24, 12, 0),
    )


def _games(payload):
    return {game['game_pk']: game for game in payload['games']}


def _side(payload, team_id):
    for game in payload['games']:
        for key in ('away', 'home'):
            if game[key]['team_id'] == team_id:
                return game[key]
    raise AssertionError(team_id)


def _variant(env, mutate):
    """A snapshot with the same identity whose frozen package is edited."""
    payload = deepcopy(env.snapshot.payload)
    mutate(payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY])
    snapshot = env.snapshot
    return SimpleNamespace(
        id=snapshot.id, sync_run_id=snapshot.sync_run_id,
        data_through=snapshot.data_through,
        availability_reference_date=snapshot.availability_reference_date,
        payload=payload,
    )


# ── Normal slate, schedule authority, summary ────────────────────────────────

def test_slate_uses_game_date_et_and_orders_every_game(tonight_app):
    payload = _build(tonight_app)

    assert payload['contract'] == 'tonight_v1'
    assert [game['game_pk'] for game in payload['games']] == [803, 804, 802, 801]
    games = _games(payload)
    assert 805 not in games and 806 not in games
    assert tonight_read_model.REASON_NONCANONICAL_GAME in payload['limitations']
    assert (games[801]['away']['team_id'], games[801]['home']['team_id']) == (LAD, SF)
    assert games[801]['first_pitch_utc'].endswith('Z')
    assert games[801]['links'] == {
        'away_team_board': '/bullpen?view=board&team=LAD',
        'home_team_board': '/bullpen?view=board&team=SF',
        'matchup': '/matchup/801',
    }
    assert games[801]['featured'] is False
    assert games[801]['context'] == {
        'sentence': None, 'reason_codes': [], 'evidence_state': 'complete',
    }
    assert games[802]['state'] == 'postponed'
    # Doubleheader: two distinct cards for the same clubs.
    assert (games[803]['game_number'], games[804]['game_number']) == (1, 2)
    assert games[803]['home']['team_id'] == games[804]['home']['team_id'] == DET


def test_edition_is_bound_to_the_exact_publication(tonight_app):
    snapshot = tonight_app.snapshot
    edition = _build(tonight_app)['edition']

    assert edition['baseball_date'] == tonight_app.reference_date.isoformat()
    assert edition['baseball_date'] == snapshot.availability_reference_date.isoformat()
    assert edition['data_through'] == snapshot.data_through.isoformat()
    assert edition['publication'] == {
        'dashboard_snapshot_id': snapshot.id,
        'sync_run_id': snapshot.sync_run_id,
        'team_board_package_contract': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
    }
    assert edition['schedule_as_of'].endswith('Z')


def test_summary_counts_come_from_the_projected_payload(tonight_app):
    payload = _build(tonight_app)

    assert payload['summary'] == {
        'game_count': 4,
        'games_by_state': {
            'scheduled': 3, 'live': 0, 'final': 0,
            'postponed': 1, 'suspended': 0, 'uncertain': 0,
        },
        'team_state_counts': {'fresh': 3, 'stretched': 2, 'vulnerable': 1, 'withheld': 0},
        'clubs_with_back_to_back_arms': 1,
        'change_count': 0,
    }
    assert payload['lead'] is None
    assert payload['featured_game_pks'] == []
    assert payload['league_changes'] == []
    assert payload['quiet_day'] is False
    assert all(
        game[key]['change_refs'] == [] for game in payload['games'] for key in ('away', 'home')
    )


def test_off_day_is_an_empty_slate(tonight_app):
    payload = tonight_read_model.build_tonight_v1(
        tonight_app.snapshot, [], generated_at=datetime(2026, 9, 24, 12, 0),
    )
    assert payload['games'] == []
    assert payload['summary']['game_count'] == 0
    assert payload['summary']['team_state_counts'] == {
        'fresh': 0, 'stretched': 0, 'vulnerable': 0, 'withheld': 0,
    }
    assert payload['quiet_day'] is True


def test_missing_first_pitch_keeps_the_game_and_orders_it_last(tonight_app):
    rows = tonight_read_model.load_slate_games(tonight_app.reference_date)
    untimed = SimpleNamespace(
        game_pk=899, game_time_utc=None, away_team_id=BOS, home_team_id=NYY,
        normalized_state='upcoming', status_detailed='Scheduled', game_number=2,
        last_synced=None,
    )
    payload = tonight_read_model.build_tonight_v1(
        tonight_app.snapshot, list(rows) + [untimed],
        generated_at=datetime(2026, 9, 24, 12, 0),
    )
    last = payload['games'][-1]
    assert last['game_pk'] == 899
    assert last['first_pitch_utc'] is None
    assert last['context']['reason_codes'] == [tonight_read_model.REASON_TIME_UNCONFIRMED]


@pytest.mark.parametrize('normalized, detailed, expected', [
    ('upcoming', 'Scheduled', 'scheduled'),
    ('live', 'In Progress', 'live'),
    ('completed', 'Final', 'final'),
    ('cancelled', 'Postponed', 'postponed'),
    ('cancelled', 'Cancelled', 'uncertain'),
    ('uncertain', 'Suspended: Rain', 'suspended'),
    ('uncertain', 'Delayed: Rain', 'uncertain'),
    ('unexpected', None, 'uncertain'),
])
def test_game_state_mapping_is_centralised(normalized, detailed, expected):
    row = SimpleNamespace(normalized_state=normalized, status_detailed=detailed)
    assert tonight_read_model.game_state(row) == expected


# ── Team Board parity: same snapshot, same facts ─────────────────────────────

@pytest.mark.parametrize('team_id', [SF, LAD, NYY])
def test_team_side_equals_team_board_frozen_facts(tonight_app, team_id):
    side = _side(_build(tonight_app), team_id)
    client = tonight_app.app.test_client()
    core = client.get(f'/api/bullpen/teams/{team_id}/board-v2/core').get_json()
    board = public_serving_authority.build_published_team_board(
        team_id, snapshot_override=tonight_app.snapshot, include_recent_usage_rest=True,
    )

    assert core['publication_identity']['snapshot_id'] == tonight_app.snapshot.id
    assert side['team_state']['public_state'] == core['team_state']['public_state']
    assert side['team_state']['public_label'] == core['team_state']['public_label']
    rest = core['rest_status']
    assert side['rest'] == {
        'active_arm_count': rest['active_arm_count'],
        'rested_arm_count': rest['rested_arm_count'],
        'worked_yesterday_count': rest['worked_yesterday_count'],
        'back_to_back_count': rest['back_to_back_count'],
        'available': True,
        'reason_code': None,
    }
    assert side['rest']['active_arm_count'] == core['active_bullpen']['arm_count']
    window = board['workload_overview']['windows']['window_7']
    for name in ('appearances', 'pitches', 'outs'):
        assert side['workload_7d'][name] == window[name]['value']
    # 3-in-4 is only a count over the same frozen carrier's per-arm facts.
    arm_ids = {arm['pitcher_id'] for arm in core['active_bullpen']['arms']}
    expected = sum(
        1 for item in board['recent_usage_rest']['active_pitchers']
        if item['pitcher_id'] in arm_ids and item['three_in_four']['value'] is True
    )
    assert side['multi_day_usage']['three_in_four_count'] == expected


def test_sf_side_is_team_board_bullpen_truth_not_fatigue_score(tonight_app):
    side = _side(_build(tonight_app), SF)

    assert side['team_state']['public_label'] == 'Stretched'
    assert side['rest'] == {
        'active_arm_count': 11, 'rested_arm_count': 9, 'worked_yesterday_count': 2,
        'back_to_back_count': 2, 'available': True, 'reason_code': None,
    }
    assert side['multi_day_usage']['three_in_four_count'] == 1
    # Relief-only 7-day workload: 22x3 + 18x2 + 35. The swing arm's 82-pitch
    # start is physical workload in FatigueScore, never bullpen workload here.
    assert (side['workload_7d']['appearances'], side['workload_7d']['pitches'],
            side['workload_7d']['outs']) == (6, 137, 21)
    fatigue_pitches = sum(
        score.pitches_last_7_days or 0
        for score in FatigueScore.query.filter(
            FatigueScore.pitcher_id.in_([p.id for p in tonight_app.pitchers[SF]])
        )
    )
    assert fatigue_pitches == 137 + 82
    assert [(arm['name'], arm['role_key'], arm['pattern']) for arm in side['key_arms']] == [
        ('SF Arm 00', 'trust_arm', None),
        ('SF Arm 01', 'bridge_arm', None),
    ]
    assert side['rotation'] is None


# ── Evidence states: withheld, never zero ────────────────────────────────────

def test_missing_team_state_receipt_withholds_that_side(tonight_app):
    def drop_sf(package):
        del package['frozen_team_state_by_team_id'][str(SF)]
    payload = _build(tonight_app, _variant(tonight_app, drop_sf))
    side = _side(payload, SF)

    assert side['team_state'] == {
        'public_state': None, 'public_label': None, 'available': False,
        'reason_code': 'snapshot_team_state_receipt_missing',
    }
    assert payload['summary']['team_state_counts']['withheld'] == 1
    assert _games(payload)[801]['context']['evidence_state'] == 'withheld'


def test_package_without_receipts_never_falls_back(tonight_app):
    payload = _build(
        tonight_app,
        _variant(tonight_app, lambda package: package.pop('frozen_team_state_by_team_id')),
    )
    side = _side(payload, SF)
    assert side['team_state']['available'] is False
    assert side['team_state']['reason_code'] == (
        tonight_read_model.REASON_TEAM_STATE_RECEIPT_UNAVAILABLE
    )
    assert payload['summary']['team_state_counts']['withheld'] == 6


def test_unavailable_rest_status_is_withheld_not_zero(tonight_app):
    def withhold(package):
        package['by_team_id'][str(SF)]['rest_status'] = {
            'available': False, 'active_arm_count': None, 'rested_arm_count': None,
            'worked_yesterday_count': None, 'back_to_back_count': None,
            'summary': None, 'reason_code': 'current_population_counts_withheld',
        }
    payload = _build(tonight_app, _variant(tonight_app, withhold))
    rest = _side(payload, SF)['rest']
    assert rest == {
        'active_arm_count': None, 'rested_arm_count': None,
        'worked_yesterday_count': None, 'back_to_back_count': None,
        'available': False, 'reason_code': 'current_population_counts_withheld',
    }
    assert payload['summary']['clubs_with_back_to_back_arms'] == 0


def test_invalid_rest_authority_is_withheld(tonight_app):
    payload = _build(tonight_app, _variant(
        tonight_app, lambda package: package['by_team_id'][str(SF)].pop('rest_status_authority'),
    ))
    rest = _side(payload, SF)['rest']
    assert rest['available'] is False
    assert rest['rested_arm_count'] is None


def test_partial_workload_keeps_its_evidence_state(tonight_app):
    def partial(package):
        window = package['by_team_id'][str(SF)]['workload_windows']['overview']['windows']['window_7']
        window['pitches'] = {
            'value': None, 'status': 'partial', 'reason_codes': ['slate_coverage_incomplete'],
        }
    workload = _side(_build(tonight_app, _variant(tonight_app, partial)), SF)['workload_7d']
    assert workload['pitches'] is None
    assert workload['appearances'] == 6
    assert workload['status'] == 'partial'
    assert workload['reason_codes'] == ['slate_coverage_incomplete']


def test_incomplete_usage_fact_withholds_three_in_four_count(tonight_app):
    def unknown(package):
        items = package['by_team_id'][str(SF)]['recent_usage_rest']['active_pitchers']
        items[0]['three_in_four'] = {'value': None, 'status': 'unknown', 'reason_codes': []}
    side = _side(_build(tonight_app, _variant(tonight_app, unknown)), SF)
    assert side['multi_day_usage']['three_in_four_count'] is None


def test_missing_team_package_keeps_the_game_with_an_unavailable_side(tonight_app):
    payload = _build(
        tonight_app,
        _variant(tonight_app, lambda package: package['by_team_id'].pop(str(LAD))),
    )
    game = _games(payload)[801]
    away = game['away']
    assert (away['team_id'], away['abbreviation'], away['name']) == (
        LAD, 'LAD', 'Los Angeles Dodgers',
    )
    assert away['available'] is False
    assert away['reason_code'] == tonight_read_model.REASON_TEAM_PACKAGE_UNAVAILABLE
    assert away['rest']['rested_arm_count'] is None
    assert away['workload_7d']['status'] == 'unavailable'
    assert away['key_arms'] == []
    assert game['context']['evidence_state'] == 'withheld'
    assert tonight_read_model.REASON_TEAM_PACKAGE_UNAVAILABLE in payload['limitations']
    assert game['home']['available'] is True


# ── Key arms and rotation are projections, not new rankings ─────────────────

def _arm(pitcher_id, name, role, *, b2b=False):
    return {
        'pitcher_id': pitcher_id,
        'name': name,
        'public_role_read': {'key': role, 'label': role.title()},
        'workload': {'days_since_last_appearance': 1, 'back_to_back': b2b},
    }


def test_key_arms_use_governed_roles_in_fixed_order():
    arms = [
        _arm(5, 'Zed', 'bridge_arm'),
        _arm(4, 'Amy', 'depth_arm'),
        _arm(3, 'Cal', 'trust_arm'),
        _arm(2, 'Bea', 'bridge_arm', b2b=True),
        _arm(1, 'Abe', 'trust_arm'),
        _arm(6, 'Dan', 'coverage_arm'),
    ]
    usage = {
        pitcher_id: {'three_in_four': {'value': pitcher_id == 3, 'status': 'complete'}}
        for pitcher_id in range(1, 7)
    }
    selected = tonight_read_model._key_arms(arms, usage)
    assert [(arm['name'], arm['role_key'], arm['pattern']) for arm in selected] == [
        ('Abe', 'trust_arm', None),
        ('Cal', 'trust_arm', '3-in-4'),
        ('Bea', 'bridge_arm', 'B2B'),
    ]


def test_rotation_projects_only_meaningful_short_start_context():
    base = {'status': 'complete', 'games_analyzed': 6, 'bullpen_innings': '21.1'}
    assert tonight_read_model._rotation({**base, 'short_start_count': 0}) is None
    assert tonight_read_model._rotation({**base, 'status': 'unknown', 'short_start_count': 2}) is None
    assert tonight_read_model._rotation(None) is None
    assert tonight_read_model._rotation({**base, 'short_start_count': 2}) == {
        'short_start_count': 2, 'bullpen_innings': '21.1', 'games_analyzed': 6,
        'status': 'complete',
    }


def test_rotation_reads_the_validated_frozen_carrier(tonight_app):
    def short_starts(package):
        carrier = package['by_team_id'][str(SF)]['frozen_rotation_impact']
        carrier.update({
            'status': 'complete', 'games_analyzed': 5, 'short_start_count': 2,
            'bullpen_innings': '19.2',
        })
    rotation = _side(_build(tonight_app, _variant(tonight_app, short_starts)), SF)['rotation']
    assert rotation == {
        'short_start_count': 2, 'bullpen_innings': '19.2', 'games_analyzed': 5,
        'status': 'complete',
    }


# ── No second bullpen engine; bounded reads ─────────────────────────────────

def test_builder_reads_no_fatigue_or_game_logs_and_no_legacy_context(
    tonight_app, mutable_reads, monkeypatch,
):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('tonight_v1 used a live bullpen engine')

    import services.availability_population as availability_population
    import services.bullpen_context as bullpen_context
    import services.tonight_candidate_selection as candidate_selection
    monkeypatch.setattr(bullpen_context, 'build_team_bullpen_context', forbidden)
    monkeypatch.setattr(availability_population, 'current_availability_records', forbidden)
    monkeypatch.setattr(candidate_selection, 'build_tonight_candidates', forbidden)
    del mutable_reads[:]

    row, outcome = tonight_read_model.generate_tonight_v1_for_snapshot(tonight_app.snapshot)

    assert outcome == 'created'
    assert not [sql for sql in mutable_reads if 'game_logs' in sql or 'fatigue_scores' in sql]
    assert not [sql for sql in mutable_reads if 'from pitchers' in sql]
    # Slate read, identity lookup, insert: no per-team or per-game reads.
    print(f'TONIGHT_V1_QUERY_COUNT={len(mutable_reads)}')
    assert len(mutable_reads) <= 4, mutable_reads


def test_builder_module_does_not_import_legacy_engines():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(tonight_read_model))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module)
            imported.update(f'{node.module}.{alias.name}' for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    for forbidden in (
        'models.fatigue_score', 'models.game_log', 'services.bullpen_context',
        'services.tonight_candidate_selection', 'services.availability_population',
        'services.tonight_intelligence_service',
    ):
        assert not any(name == forbidden or name.startswith(forbidden + '.') for name in imported)


# ── Immutable, publication-bound storage ─────────────────────────────────────

def test_storage_is_immutable_and_publication_bound(tonight_app):
    snapshot = tonight_app.snapshot
    legacy = tonight_intelligence_snapshot.write_snapshot(
        {'status': 'empty', 'reference_date': tonight_app.reference_date.isoformat(),
         'cards': [], 'card_count': 0, 'games': [], 'game_count': 0,
         'empty_reason': 'no_tonight_signals', 'limitations': []},
        source='legacy_test',
    )
    legacy_before = dict(TonightIntelligenceSnapshot.query.one().response_json)

    # A. First build creates the row with its exact identity.
    row, outcome = tonight_read_model.generate_tonight_v1_for_snapshot(snapshot)
    assert outcome == 'created'
    assert (row.contract, row.reference_date, row.dashboard_snapshot_id, row.sync_run_id,
            row.data_through, row.availability_reference_date) == (
        'tonight_v1', snapshot.availability_reference_date, snapshot.id, snapshot.sync_run_id,
        snapshot.data_through, snapshot.availability_reference_date,
    )
    assert row.content_sha256 == tonight_read_model.content_sha256(row.payload)
    first_id, first_hash = row.id, row.content_sha256

    # B. A deterministic rebuild of the same publication reuses the row.
    again, outcome = tonight_read_model.generate_tonight_v1_for_snapshot(
        snapshot, generated_at=datetime(2030, 1, 1),
    )
    assert (outcome, again.id) == ('reused', first_id)

    # C. Same identity, different content: refused, stored row unchanged.
    game = db.session.get(SlateGame, 801)
    game.normalized_state = 'live'
    db.session.commit()
    with pytest.raises(tonight_read_model.TonightPublicationConflict):
        tonight_read_model.generate_tonight_v1_for_snapshot(snapshot)
    stored = db.session.get(TonightPublication, first_id)
    assert stored.content_sha256 == first_hash
    assert _games(stored.payload)[801]['state'] == 'scheduled'

    # The row itself refuses in-place updates.
    stored.payload = {'contract': 'tampered'}
    with pytest.raises(TonightPublicationImmutable):
        db.session.commit()
    db.session.rollback()

    # D. A new trusted snapshot for the same date gets its own row.
    newer = _publish(tonight_app.reference_date, source='tonight_v1_newer')
    assert newer.id != snapshot.id
    newer_row, outcome = tonight_read_model.generate_tonight_v1_for_snapshot(newer)
    assert outcome == 'created' and newer_row.id != first_id
    assert _games(newer_row.payload)[801]['state'] == 'live'
    assert db.session.get(TonightPublication, first_id).content_sha256 == first_hash
    assert TonightPublication.query.count() == 2
    assert tonight_read_model.read_tonight_v1(
        snapshot.availability_reference_date, snapshot.id,
    ).id == first_id

    # E. Legacy tonight_v5 storage is untouched.
    assert legacy is not None
    assert TonightIntelligenceSnapshot.query.count() == 1
    assert TonightIntelligenceSnapshot.query.one().response_json == legacy_before


# ── Publication integration ──────────────────────────────────────────────────

def test_post_publication_hook_projects_the_committed_snapshot(tonight_app):
    tonight_app.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True
    dashboard_snapshot.run_post_commit_snapshot_publication(tonight_app.snapshot)

    row = tonight_read_model.read_tonight_v1(
        tonight_app.snapshot.availability_reference_date, tonight_app.snapshot.id,
    )
    assert row is not None
    assert row.payload['edition']['publication']['dashboard_snapshot_id'] == (
        tonight_app.snapshot.id
    )


def test_post_publication_hook_failure_never_touches_the_publication(
    tonight_app, monkeypatch,
):
    tonight_app.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True

    def boom(*_args, **_kwargs):
        raise RuntimeError('projection failed')

    monkeypatch.setattr(tonight_read_model, 'build_tonight_v1', boom)
    result = tonight_read_model.generate_tonight_v1_after_publication(tonight_app.snapshot)
    dashboard_snapshot.run_post_commit_snapshot_publication(tonight_app.snapshot)

    assert result == {'status': 'failed', 'error': 'RuntimeError'}
    assert TonightPublication.query.count() == 0
    snapshot = db.session.get(DashboardSnapshot, tonight_app.snapshot.id)
    assert snapshot.is_published is True
    assert dashboard_snapshot.get_latest_valid_dashboard_snapshot().id == snapshot.id


def test_post_publication_hook_is_off_unless_enabled(tonight_app):
    dashboard_snapshot.run_post_commit_snapshot_publication(tonight_app.snapshot)
    assert TonightPublication.query.count() == 0


def test_real_publication_creates_its_bound_tonight_row(tonight_app):
    tonight_app.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True
    newer = _publish(tonight_app.reference_date, source='tonight_v1_hooked')

    row = tonight_read_model.read_tonight_v1(newer.availability_reference_date, newer.id)
    assert row is not None
    assert row.dashboard_snapshot_id == newer.id
    assert row.payload['summary']['game_count'] == 4
    # The projection is a post-commit step: it never moves the trusted pointer.
    assert dashboard_snapshot.get_latest_valid_dashboard_snapshot().id == newer.id
