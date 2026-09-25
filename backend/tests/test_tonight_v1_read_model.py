"""TN-01: the trusted, publication-bound Tonight v1 read model.

Every fixture is a real trusted Dashboard publication built by the production
builder (frozen ``trusted_team_boards`` package), plus ``slate_games`` rows for
the publication's baseball date. Tonight must project exactly the Team Board
facts of that one snapshot, and read no FatigueScore or GameLog doing it.
"""

from copy import deepcopy
from datetime import date, datetime, timedelta
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
    # TN-06: SF has 2 back-to-back arms and a 3-in-4 arm. The postponed 802
    # (NYY Vulnerable) is not eligible, and 803/804 meet no rule.
    assert games[801]['featured'] is True
    assert games[801]['featured_reason_codes'] == [
        'multiple_back_to_back_arms', 'three_in_four_pressure',
    ]
    assert all(games[pk]['featured'] is False for pk in (802, 803, 804))
    # TN-04: one descriptive sentence authored from the frozen TeamSides.
    assert games[801]['context'] == {
        'sentence': 'SF has 2 bullpen arms coming off back-to-back usage.',
        'reason_codes': ['back_to_back_pressure'], 'evidence_state': 'complete',
    }
    # A game already postponed at build time never shows its pregame sentence.
    assert games[802]['context'] == {
        'sentence': None,
        'reason_codes': ['team_state_vulnerable', 'pregame_context_hidden'],
        'evidence_state': 'complete',
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
    assert payload['featured_game_pks'] == [801]
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
    # BOS Fresh vs NYY Vulnerable: the primary reason, then the time limitation.
    assert last['context']['reason_codes'] == [
        'team_state_vulnerable', tonight_read_model.REASON_TIME_UNCONFIRMED,
    ]


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
    # SF's Team State is unknown, so the lower-priority B2B sentence is partial.
    assert _games(payload)[801]['context'] == {
        'sentence': 'SF has 2 bullpen arms coming off back-to-back usage.',
        'reason_codes': ['back_to_back_pressure'], 'evidence_state': 'partial',
    }


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
    assert game['context']['evidence_state'] == 'partial'
    assert game['context']['reason_codes'] == ['back_to_back_pressure']
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


# ── TN-04: matchup context sentence ──────────────────────────────────────────
# Pure-helper matrix on TeamSide-shaped inputs, plus parity against real
# frozen TeamSides. The helper reads only the two sides it is given.

from services.editorial_voice_contract_v1 import find_editorial_violations  # noqa: E402

_LABELS = {'fresh': 'Fresh', 'stretched': 'Stretched', 'vulnerable': 'Vulnerable'}


def _ctx_side(abbr, state='fresh', *, b2b=0, rested=5, three=0, short=None,
              rotation_status='complete', team_state=True, rest=True, available=True):
    return {
        'team_id': 100, 'abbreviation': abbr, 'name': f'{abbr} Club', 'available': available,
        'team_state': {
            'public_state': state if team_state else None,
            'public_label': _LABELS.get(state) if team_state else None,
            'available': team_state, 'reason_code': None,
        },
        'rest': {
            'active_arm_count': 8 if rest else None,
            'rested_arm_count': rested if rest else None,
            'worked_yesterday_count': 1 if rest else None,
            'back_to_back_count': b2b if rest else None,
            'available': rest, 'reason_code': None if rest else 'withheld',
        },
        'multi_day_usage': {'three_in_four_count': three},
        'rotation': None if short is None else {
            'short_start_count': short, 'bullpen_innings': 11.2,
            'games_analyzed': 5, 'status': rotation_status,
        },
    }


def _ctx(away, home):
    return tonight_read_model.build_matchup_context(away, home)


def _assert_clean_copy(sentence):
    assert sentence and len(sentence) <= tonight_read_model.CONTEXT_SENTENCE_MAX_CHARS
    assert len(sentence.split()) <= 35
    assert find_editorial_violations(
        sentence, terms=tonight_read_model.CONTEXT_BANNED_TERMS,
    ) == []
    # The shared editorial voice contract accepts it too.
    assert find_editorial_violations(sentence) == []
    assert sentence.endswith('.') and sentence.count('. ') == 0


@pytest.mark.parametrize(('away', 'home', 'reason', 'sentence'), [
    (_ctx_side('SEA', 'vulnerable'), _ctx_side('HOU', 'stretched'),
     'team_state_vulnerable',
     'SEA enters tonight with a Vulnerable bullpen state, while HOU is Stretched.'),   # 1
    (_ctx_side('SEA', 'vulnerable'), _ctx_side('HOU', 'vulnerable'),
     'team_state_vulnerable',
     'SEA and HOU both enter tonight with Vulnerable bullpen states.'),                # 2
    (_ctx_side('SEA', b2b=3), _ctx_side('HOU', b2b=1),
     'back_to_back_pressure', 'SEA has 3 bullpen arms coming off back-to-back usage.'),  # 3
    (_ctx_side('SEA', b2b=2), _ctx_side('HOU', b2b=4),
     'back_to_back_pressure',
     'SEA has 2 bullpen arms coming off back-to-back usage; HOU has 4.'),              # 4
    (_ctx_side('SEA'), _ctx_side('HOU', three=1),
     'three_in_four_pressure', 'HOU has 1 reliever carrying a 3-in-4 workload pattern.'),  # 5
    (_ctx_side('SEA', three=2), _ctx_side('HOU', three=3),
     'three_in_four_pressure',
     'SEA has 2 relievers carrying a 3-in-4 workload pattern; HOU has 3.'),
    (_ctx_side('SEA', short=2), _ctx_side('HOU'),
     'short_start_transfer',
     "SEA's bullpen has absorbed 2 short starts in the recent rotation window."),      # 6
    (_ctx_side('SEA', 'fresh'), _ctx_side('HOU', 'stretched'),
     'team_state_contrast', 'SEA is Fresh entering tonight; HOU is Stretched.'),      # 7
    (_ctx_side('SEA', rested=6), _ctx_side('HOU', rested=1),
     'rested_arm_snapshot', 'SEA has 6 rested bullpen arms; HOU has 1.'),              # 8
])
def test_matchup_context_templates(away, home, reason, sentence):
    context = _ctx(away, home)
    assert context == {
        'sentence': sentence, 'reason_codes': [reason], 'evidence_state': 'complete',
    }
    _assert_clean_copy(context['sentence'])


def test_priority_is_deterministic_and_never_concatenates():
    away = _ctx_side('SEA', 'vulnerable', b2b=3, three=2, short=1)
    home = _ctx_side('HOU', 'fresh')
    first = _ctx(away, home)
    assert first['reason_codes'] == ['team_state_vulnerable']
    assert first['sentence'] == (
        'SEA enters tonight with a Vulnerable bullpen state, while HOU is Fresh.'
    )
    assert _ctx(away, home) == first
    # Remove Vulnerable: the next true condition, B2B, is selected alone.
    away = _ctx_side('SEA', 'stretched', b2b=3, three=2, short=1)
    second = _ctx(away, home)
    assert second['reason_codes'] == ['back_to_back_pressure']
    assert second['sentence'] == 'SEA has 3 bullpen arms coming off back-to-back usage.'
    for text in (first['sentence'], second['sentence']):
        assert '3-in-4' not in text and 'short start' not in text


def test_single_back_to_back_arm_is_not_context():
    context = _ctx(_ctx_side('SEA', b2b=1), _ctx_side('HOU', b2b=0, rested=4))
    assert context['reason_codes'] == ['rested_arm_snapshot']


def test_unavailable_team_state_is_never_used():  # 9
    context = _ctx(_ctx_side('SEA', 'vulnerable', team_state=False), _ctx_side('HOU', 'fresh'))
    assert 'Vulnerable' not in context['sentence']
    assert context['reason_codes'] == ['rested_arm_snapshot']
    # A Team State input was withheld, so the lower-priority line is partial.
    assert context['evidence_state'] == 'partial'
    one_sided = _ctx(_ctx_side('SEA', 'vulnerable'), _ctx_side('HOU', team_state=False))
    assert one_sided['sentence'] == 'SEA enters tonight with a Vulnerable bullpen state.'
    assert one_sided['evidence_state'] == 'partial'


def test_unavailable_rest_is_never_zero():  # 10
    context = _ctx(_ctx_side('SEA', b2b=3, rest=False), _ctx_side('HOU', rest=False))
    assert context == {'sentence': None, 'reason_codes': [], 'evidence_state': 'withheld'}
    side = _ctx_side('SEA', rest=False)
    side['rest']['back_to_back_count'] = 0  # a stray value behind available=False
    assert _ctx(side, _ctx_side('HOU'))['sentence'] is None


def test_unknown_three_in_four_is_never_zero():  # 11
    away = _ctx_side('SEA', three=None)
    context = _ctx(away, _ctx_side('HOU', three=None))
    assert context['reason_codes'] == ['rested_arm_snapshot']
    assert context['evidence_state'] == 'partial'
    assert '3-in-4' not in context['sentence']


def test_null_rotation_is_not_short_start_context():  # 12
    context = _ctx(_ctx_side('SEA', short=None), _ctx_side('HOU'))
    assert context['reason_codes'] == ['rested_arm_snapshot']
    partial = _ctx(_ctx_side('SEA', short=1, rotation_status='partial'), _ctx_side('HOU'))
    assert partial['sentence'] == (
        "SEA's bullpen has absorbed 1 short start in the recent rotation window."
    )
    assert partial['evidence_state'] == 'partial'


def test_no_authoritative_context_is_null():  # 13
    unavailable = {
        'team_id': 1, 'abbreviation': 'SEA', 'name': 'SEA', 'available': False,
        'team_state': {'public_state': None, 'public_label': None, 'available': False,
                       'reason_code': 'x'},
        'rest': {'available': False, 'back_to_back_count': None, 'rested_arm_count': None},
        'multi_day_usage': {'three_in_four_count': None}, 'rotation': None,
    }
    other = dict(unavailable, abbreviation='HOU')
    assert _ctx(unavailable, other) == {
        'sentence': None, 'reason_codes': [], 'evidence_state': 'unavailable',
    }


def test_singular_and_plural_grammar():  # 14
    assert _ctx(_ctx_side('SEA', three=1), _ctx_side('HOU'))['sentence'].startswith(
        'SEA has 1 reliever carrying'
    )
    assert _ctx(_ctx_side('SEA', short=1), _ctx_side('HOU'))['sentence'] == (
        "SEA's bullpen has absorbed 1 short start in the recent rotation window."
    )
    assert _ctx(_ctx_side('SEA', rested=1), _ctx_side('HOU', rested=1))['sentence'] == (
        'SEA has 1 rested bullpen arm; HOU has 1.'
    )


def test_team_order_is_away_then_home():  # 15
    assert _ctx(_ctx_side('SEA', b2b=2), _ctx_side('HOU', b2b=5))['sentence'].startswith('SEA')
    assert _ctx(_ctx_side('HOU', b2b=5), _ctx_side('SEA', b2b=2))['sentence'].startswith('HOU')
    assert _ctx(_ctx_side('SEA'), _ctx_side('HOU', 'vulnerable'))['sentence'].startswith('HOU')


def test_every_template_passes_the_banned_language_guard():  # 16
    sentences = [
        _ctx(_ctx_side('SEA', state), _ctx_side('HOU', other))['sentence']
        for state in _LABELS for other in _LABELS
    ]
    sentences += [
        _ctx(_ctx_side('SEA', b2b=n), _ctx_side('HOU', b2b=m))['sentence']
        for n in (2, 12) for m in (0, 11)
    ]
    sentences += [
        _ctx(_ctx_side('SEA', three=n, short=n), _ctx_side('HOU', three=n, short=n))['sentence']
        for n in (1, 10)
    ]
    sentences.append(_ctx(_ctx_side('SEA', short=3), _ctx_side('HOU', short=12))['sentence'])
    for sentence in filter(None, sentences):
        _assert_clean_copy(sentence)
    # The guard itself catches the forbidden concepts.
    assert find_editorial_violations(
        'SEA has the edge and will likely win', terms=tonight_read_model.CONTEXT_BANNED_TERMS,
    )


@pytest.mark.parametrize(('state', 'sentence_shown', 'marker'), [
    ('scheduled', True, None),
    ('uncertain', True, None),
    ('live', True, 'pregame_context'),
    ('final', False, 'pregame_context_hidden'),
    ('postponed', False, 'pregame_context_hidden'),
    ('suspended', False, 'pregame_context_hidden'),
])
def test_context_presentation_by_game_state(state, sentence_shown, marker):
    stored = _ctx(_ctx_side('SEA', b2b=2), _ctx_side('HOU'))
    frozen = deepcopy(stored)
    shown = tonight_read_model.present_matchup_context(stored, state)
    assert stored == frozen
    assert (shown['sentence'] == stored['sentence']) is sentence_shown
    assert shown['evidence_state'] == stored['evidence_state']
    expected = ['back_to_back_pressure'] + ([marker] if marker else [])
    assert shown['reason_codes'] == expected
    # Idempotent from any earlier presentation.
    assert tonight_read_model.present_matchup_context(shown, state) == shown


def test_context_parity_with_frozen_team_sides(tonight_app):
    """Every number and label in a stored sentence is its TeamSide field verbatim."""
    payload = _build(tonight_app)
    checked = 0
    for game in payload['games']:
        context = game['context']
        sides = (game['away'], game['home'])
        assert context == tonight_read_model.present_matchup_context(
            tonight_read_model.build_matchup_context(*sides), game['state'],
        )
        sentence = context['sentence']
        if sentence is None:
            continue
        _assert_clean_copy(sentence)
        reason = context['reason_codes'][0]
        if reason == 'back_to_back_pressure':
            side = next(s for s in sides if (s['rest']['back_to_back_count'] or 0) >= 2)
            assert f"{side['abbreviation']} has {side['rest']['back_to_back_count']} bullpen" in sentence
        elif reason == 'team_state_contrast':
            for side in sides:
                assert f"{side['abbreviation']} is {side['team_state']['public_label']}" in sentence
        checked += 1
    assert checked >= 3


def test_production_shaped_vulnerable_matchup():
    """Team A Vulnerable with 2 B2B and 1 3-in-4 arm; Team B Fresh: one line only."""
    away = _ctx_side('ATL', 'vulnerable', b2b=2, three=1)
    home = _ctx_side('PHI', 'fresh', b2b=0)
    context = _ctx(away, home)
    assert context == {
        'sentence': 'ATL enters tonight with a Vulnerable bullpen state, while PHI is Fresh.',
        'reason_codes': ['team_state_vulnerable'],
        'evidence_state': 'complete',
    }
    _assert_clean_copy(context['sentence'])


# ── TN-05: league What Changed aggregation ───────────────────────────────────
# Tonight only aggregates each team's frozen TB-09 What Changed events; it
# never compares snapshots. Synthetic carriers exercise the pure helper, and
# real TB-09 carriers built over an exact snapshot pair prove parity.

from services.team_board_snapshot_team_state import make_receipt  # noqa: E402
from services.team_board_what_changed import attach_frozen_what_changed  # noqa: E402
from services.team_state_vnext_production_proof import EXPECTED_METHOD_VERSION  # noqa: E402
from services.what_changed_comparison_identity import build_comparison_identity  # noqa: E402

_ABBR = {108: 'LAA', 109: 'AZ', 110: 'BAL', 111: 'BOS', 112: 'CHC', 113: 'CIN',
         114: 'CLE', 115: 'COL', 116: 'DET', 117: 'HOU', 118: 'KC', 119: 'LAD',
         120: 'WSH', 121: 'NYM', 133: 'ATH', 134: 'PIT'}


def _wc_event(team_id, event_type, *, subject_id=None, event_date=None, summary=None,
              previous_value=None, current_value=None, facts=None, domain=None):
    domains = {
        'team_state_changed': 'team_state', 'active_bullpen_joined': 'roster',
        'active_bullpen_left': 'roster', 'verified_transaction': 'transactions',
        'new_short_start': 'rotation',
    }
    return {
        'event_type': event_type,
        'domain': domain or domains.get(event_type, 'workload_rest'),
        'team_id': team_id, 'subject_id': subject_id, 'event_date': event_date,
        'previous_value': previous_value, 'current_value': current_value,
        'facts': facts or {}, 'summary': summary or f'Arm {subject_id} changed.',
        'evidence_status': 'complete', 'current_snapshot_id': 2,
        'previous_snapshot_id': 1, 'method_version': 'team_board_what_changed_event_v1',
    }


def _wc_carrier(team_id, events, *, state=None):
    return {'abbreviation': _ABBR[team_id], 'carrier': {
        'contract': 'team_board_what_changed_v1', 'team_id': team_id,
        'current_snapshot_id': 2, 'previous_snapshot_id': 1,
        'state': state or ('changes' if events else 'quiet'),
        'events': events,
    }}


def _state_change(team_id, previous='Fresh', current='Stretched'):
    return _wc_event(team_id, 'team_state_changed', previous_value=previous,
                     current_value=current,
                     summary=f'Team State changed from {previous} to {current}.')


def _joined(team_id, pitcher_id, name='Arm', transaction=None, date_=None):
    facts = {'pitcher_name': name}
    summary = f'{name} joined the active bullpen.'
    if transaction:
        facts['verified_transaction'] = {'transaction_id': transaction, 'label': 'Recalled',
                                         'direction': 'addition'}
        summary += ' Verified transaction: Recalled.'
    return _wc_event(team_id, 'active_bullpen_joined', subject_id=pitcher_id,
                     event_date=date_, current_value='active', summary=summary, facts=facts)


def _left(team_id, pitcher_id, name='Arm'):
    return _wc_event(team_id, 'active_bullpen_left', subject_id=pitcher_id,
                     previous_value='active', summary=f'{name} left the active bullpen.',
                     facts={'pitcher_name': name})


def _transaction(team_id, pitcher_id, transaction_id, label='Recalled', name='Arm',
                 date_='2026-09-24', direction='addition'):
    return _wc_event(team_id, 'verified_transaction', subject_id=pitcher_id, event_date=date_,
                     current_value=direction, summary=f'{name}: {label}.',
                     facts={'transaction_id': transaction_id, 'pitcher_name': name,
                            'label': label, 'direction': direction})


def _pattern(team_id, pitcher_id, key, label, date_='2026-09-24', name='Arm'):
    return _wc_event(team_id, f'{key}_started', subject_id=pitcher_id, event_date=date_,
                     previous_value=False, current_value=True,
                     summary=f'{name} now has {label}.',
                     facts={'pitcher_name': name, 'pattern': key, 'value': True,
                            'status': 'complete', 'most_recent_date': date_})


def _short_start(team_id, starter_id=42, game_pk=900, date_='2026-09-24'):
    return _wc_event(team_id, 'new_short_start', subject_id=starter_id, event_date=date_,
                     current_value=True,
                     summary='Starter worked 3.2 innings; the bullpen covered 5.1.',
                     facts={'mlb_game_pk': game_pk, 'game_date': date_})


def _league(*carriers, **caps):
    return tonight_read_model.build_league_changes(
        {team_id: entry for team_id, entry in carriers}, **caps,
    )


def _entry(team_id, events, **kwargs):
    return team_id, _wc_carrier(team_id, events, **kwargs)


def _assert_clean_change(item):
    for text in (item['headline'], item['detail']):
        if text:
            assert find_editorial_violations(
                text, terms=tuple(
                    term for term in tonight_read_model.LEAGUE_CHANGE_BANNED_TERMS
                    if term not in ('injured', 'hurt')
                ),
            ) == []


@pytest.mark.parametrize(('event', 'change_class', 'headline', 'detail'), [
    (_state_change(110), 'team_state_changed', 'BAL moved from Fresh to Stretched.', None),  # 1
    (_joined(110, 7, 'Arm 7'), 'active_bullpen_joined',
     'Arm 7 joined the active bullpen.', None),                                                # 2
    (_left(110, 8, 'Arm 8'), 'active_bullpen_left', 'Arm 8 left the active bullpen.', None),   # 3
    (_transaction(110, 9, 'tx-9', name='Arm 9'), 'verified_transaction',
     'Arm 9: Recalled.', None),                                                                # 4
    (_pattern(110, 7, 'back_to_back', 'back-to-back usage', name='Arm 7'),
     'back_to_back_started', 'Arm 7 now has back-to-back usage.', None),                       # 5
    (_pattern(110, 7, 'three_in_four', '3-in-4 usage', name='Arm 7'),
     'three_in_four_started', 'Arm 7 now has 3-in-4 usage.', None),                            # 6
    (_pattern(110, 7, 'high_pitch_outing', 'a qualifying high-pitch outing', name='Arm 7'),
     'high_pitch_outing_started', 'Arm 7 now has a qualifying high-pitch outing.', None),      # 7
    (_short_start(110), 'new_short_start',
     'Starter worked 3.2 innings; the bullpen covered 5.1.', None),                            # 8
])
def test_each_supported_change_class_maps_one_frozen_event(event, change_class, headline, detail):
    changes = _league(_entry(110, [event]))
    assert len(changes) == 1
    item = changes[0]
    assert set(item) == {
        'change_id', 'team_id', 'team_abbreviation', 'change_class', 'headline',
        'detail', 'occurred_on', 'evidence_state', 'source_ref', 'game_pks', 'state_change',
    }
    # TN-07 reads Team State leads from this frozen field, never from prose.
    assert item['state_change'] == (
        {'from': 'Fresh', 'to': 'Stretched'} if change_class == 'team_state_changed' else None
    )
    assert (item['team_id'], item['team_abbreviation']) == (110, 'BAL')
    assert (item['change_class'], item['headline'], item['detail']) == (change_class, headline, detail)
    assert item['occurred_on'] == event['event_date']
    assert item['evidence_state'] == 'complete'
    assert item['source_ref'].startswith('team_board_what_changed_v1:2:1:110')
    assert item['game_pks'] == ([900] if change_class == 'new_short_start' else [])
    _assert_clean_change(item)


def test_linked_membership_keeps_transaction_detail_and_trace():
    item = _league(_entry(111, [_joined(111, 5, 'Arm 5', transaction='tx-5')]))[0]
    assert item['headline'] == 'Arm 5 joined the active bullpen.'
    assert item['detail'] == 'Verified transaction: Recalled.'
    assert item['source_ref'] == 'team_board_what_changed_v1:2:1:111#transaction:tx-5'


def test_unsupported_malformed_and_noncanonical_are_excluded():  # 9, 11, 12
    unsupported = _pattern(110, 7, 'four_in_six', '4-in-6 usage')
    unknown = _wc_event(110, 'closer_changed', summary='Arm is the closer.')
    blank = _wc_event(110, 'back_to_back_started', subject_id=3, summary='  ')
    incomplete = dict(_pattern(110, 4, 'back_to_back', 'back-to-back usage'),
                      evidence_status='partial')
    other_team = _pattern(111, 4, 'back_to_back', 'back-to-back usage')
    no_labels = _wc_event(110, 'team_state_changed', summary='Team State changed.')
    assert _league(_entry(110, [unsupported, unknown, blank, incomplete, other_team, no_labels])) == []
    fake_team = (5555, {'abbreviation': 'XXX', 'carrier': {
        'team_id': 5555, 'state': 'changes',
        'events': [_pattern(5555, 1, 'back_to_back', 'back-to-back usage')],
    }})
    assert _league(fake_team) == []


def test_unavailable_or_quiet_frozen_what_changed_yields_no_item():  # 10, 23
    unavailable = _entry(110, [], state='unavailable')
    quiet = _entry(111, [])
    assert _league(unavailable, quiet) == []
    # Events on a carrier that is not in 'changes' state are never read.
    assert _league(_entry(112, [_state_change(112)], state='unavailable')) == []


def test_duplicate_source_event_is_deduped_by_identity():  # 13
    joined = _joined(111, 5, 'Arm 5', transaction='tx-5')
    same_move = _transaction(111, 5, 'tx-5', name='Arm 5')
    repeated = deepcopy(joined)
    changes = _league(_entry(111, [joined, same_move, repeated]))
    assert [item['change_class'] for item in changes] == ['active_bullpen_joined']


def test_same_copy_distinct_events_stay_distinct():  # 14
    first = _transaction(111, 5, 'tx-a', label='Recalled', name='Arm')
    second = _transaction(111, 6, 'tx-b', label='Recalled', name='Arm')
    changes = _league(_entry(111, [first, second]))
    assert [item['headline'] for item in changes] == ['Arm: Recalled.', 'Arm: Recalled.']
    assert len({item['change_id'] for item in changes}) == 2


def test_team_priority_and_team_cap_without_a_score():  # 15 + priority test
    events = [
        _short_start(110), _pattern(110, 7, 'high_pitch_outing', 'a qualifying high-pitch outing'),
        _pattern(110, 7, 'three_in_four', '3-in-4 usage'),
        _pattern(110, 7, 'back_to_back', 'back-to-back usage'),
        _transaction(110, 9, 'tx-9'), _joined(110, 8, 'Arm 8'), _state_change(110),
    ]
    changes = _league(_entry(110, events))
    assert [item['change_class'] for item in changes] == [
        'team_state_changed', 'active_bullpen_joined',
    ]
    assert len(_league(_entry(110, events), max_per_team=7)) == 7


def _many_teams():
    entries = []
    for index, team_id in enumerate(sorted(_ABBR)):
        entries.append(_entry(team_id, [
            _pattern(team_id, 1, 'back_to_back', 'back-to-back usage',
                     date_=f'2026-09-2{index % 5}'),
            _pattern(team_id, 2, 'three_in_four', '3-in-4 usage'),
            _pattern(team_id, 3, 'high_pitch_outing', 'a qualifying high-pitch outing'),
        ] + ([_state_change(team_id)] if index % 4 == 0 else [])))
    return entries


def test_league_cap_ordering_and_refs():  # 16, 18, 20, 21, 22
    entries = _many_teams()
    changes = _league(*entries)
    assert len(changes) == 12
    per_team = {}
    for item in changes:
        per_team[item['team_id']] = per_team.get(item['team_id'], 0) + 1
    assert max(per_team.values()) <= 2
    ranks = [tonight_read_model._LEAGUE_CHANGE_RANK[item['change_class']] for item in changes]
    assert ranks == sorted(ranks)
    assert changes[:4] == [item for item in changes if item['change_class'] == 'team_state_changed']
    b2b = [item for item in changes if item['change_class'] == 'back_to_back_started']
    keys = [(-date.fromisoformat(item['occurred_on']).toordinal(), item['team_abbreviation'])
            for item in b2b]
    assert keys == sorted(keys)
    # Deterministic: same input, same list.
    assert _league(*reversed(entries)) == changes
    sides = [{'team_id': team_id} for team_id in sorted(_ABBR)]
    tonight_read_model.attach_change_refs(sides, changes)
    retained = {item['change_id'] for item in changes}
    for side in sides:
        assert side['change_refs'] == [
            item['change_id'] for item in changes if item['team_id'] == side['team_id']
        ]
        assert set(side['change_refs']) <= retained
    capped_out = {
        item['change_id'] for item in _league(*entries, max_total=100)
    } - retained
    assert capped_out
    assert not capped_out & {ref for side in sides for ref in side['change_refs']}


def test_fewer_than_cap_is_not_padded():  # 17
    changes = _league(_entry(110, [_state_change(110)]), _entry(111, [_short_start(111)]))
    assert [item['team_abbreviation'] for item in changes] == ['BAL', 'BOS']


def test_change_id_is_deterministic_and_positional_free():  # 19
    event = _pattern(110, 7, 'back_to_back', 'back-to-back usage')
    first = _league(_entry(110, [event]))[0]['change_id']
    shuffled = _league(_entry(110, [_short_start(110), deepcopy(event)]), max_per_team=5)
    assert first in [item['change_id'] for item in shuffled]
    other_pair = _wc_carrier(110, [event])
    other_pair['carrier']['current_snapshot_id'] = 3
    assert tonight_read_model.build_league_changes({110: other_pair})[0]['change_id'] != first


def test_league_change_copy_guard():  # 24
    bad = _transaction(110, 9, 'tx-9', label='Pick up for a favorable edge')
    assert _league(_entry(110, [bad])) == []
    il = _transaction(110, 9, 'tx-10', label='Placed on the 15-day injured list')
    assert _league(_entry(110, [il]))[0]['headline'] == 'Arm: Placed on the 15-day injured list.'
    speculative = _pattern(110, 7, 'back_to_back', 'back-to-back usage')
    speculative['summary'] = 'Arm is gassed and will likely sit.'
    assert _league(_entry(110, [speculative])) == []


# Real TB-09 carriers over one exact snapshot pair (parity + production shape).

def _real_team(snapshot, team_id, state_code, pitcher_ids):
    readiness = {
        'readiness': {'status_code': state_code},
        'freshness': {'data_through': snapshot.data_through.isoformat()},
    }
    return {
        'team': {'team_id': team_id, 'team_abbreviation': _ABBR[team_id]},
        'default_pitcher_ids': list(pitcher_ids),
        'records': [{'pitcher_id': pid, 'name': f'Arm {pid}'} for pid in pitcher_ids],
        'frozen_team_state': make_receipt(
            snapshot, team_id, readiness, method_version=EXPECTED_METHOD_VERSION,
        ),
        'recent_usage_rest': {
            'status': 'complete',
            'active_pitchers': [{
                'pitcher_id': pid, 'pitcher_name': f'Arm {pid}',
                'back_to_back': _wc_fact(False), 'three_in_four': _wc_fact(False),
                'four_in_six': _wc_fact(False), 'high_pitch_outing': _wc_fact(False),
            } for pid in pitcher_ids],
            'off_active_historical_contributors': [],
        },
        'frozen_roster_transactions': {'status': 'available', 'events': []},
        'frozen_rotation_impact': {'status': 'complete', 'starts': []},
    }


def _wc_fact(value, most_recent_date=None):
    return {'value': value, 'status': 'complete', 'reason_codes': [],
            'most_recent_date': most_recent_date}


PRODUCTION_TEAMS = (110, 111, 112, 113, 114, 116)  # A..F


def _real_pair():
    def snap(snapshot_id, represented):
        return SimpleNamespace(
            id=snapshot_id, sync_run_id=snapshot_id + 1000,
            data_through=date.fromisoformat(represented), payload_version=1,
            snapshot_type='bullpen_dashboard', status='ready', is_published=True,
            published_at=datetime(2026, 9, 24, 12), payload={},
            availability_reference_date=date.fromisoformat(represented) + timedelta(days=1),
        )
    previous, current = snap(1, '2026-09-23'), snap(2, '2026-09-24')
    for snapshot in (previous, current):
        snapshot.payload = {'trusted_team_boards': {
            'contract': 'trusted_team_board_publication_v1',
            'data_through': snapshot.data_through.isoformat(), 'by_team_id': {},
        }}
    states = {110: ('operationally_stable', 'operationally_constrained')}
    for team_id in PRODUCTION_TEAMS:
        before, after = states.get(team_id, ('operationally_stable', 'operationally_stable'))
        prior_ids, now_ids = (7, 8), (7, 8)
        if team_id == 111:
            now_ids = (7, 8, 9)
        previous.payload['trusted_team_boards']['by_team_id'][str(team_id)] = _real_team(
            previous, team_id, before, prior_ids)
        current.payload['trusted_team_boards']['by_team_id'][str(team_id)] = _real_team(
            current, team_id, after, now_ids)
    teams = current.payload['trusted_team_boards']['by_team_id']
    usage = lambda team_id: teams[str(team_id)]['recent_usage_rest']['active_pitchers'][0]  # noqa: E731
    usage(110)['back_to_back'] = _wc_fact(True, '2026-09-24')                    # A: B2B
    teams['111']['frozen_roster_transactions']['events'] = [{                      # B: join + tx
        'event_id': 'tx-111-9', 'evidence_status': 'complete', 'player_id': 9,
        'player_name': 'Arm 9', 'date': '2026-09-24', 'label': 'Recalled',
        'direction': 'addition',
    }]
    usage(112)['three_in_four'] = _wc_fact(True, '2026-09-24')                   # C: 3-in-4
    usage(113)['high_pitch_outing'] = _wc_fact(True, '2026-09-23')               # D: high pitch
    teams['114']['frozen_rotation_impact']['starts'] = [{                          # E: short start
        'mlb_game_pk': 4401, 'status': 'complete', 'short_start': True,
        'short_start_evidence': {'status': 'complete'}, 'starter_pitcher_id': 42,
        'starter_name': 'Starter', 'starter_innings': '3.1',
        'bullpen_innings': '5.2', 'game_date': '2026-09-24',
    }]
    identity = build_comparison_identity(current, previous)
    current.payload['what_changed_since_yesterday'] = {'comparison': {'identity': identity}}
    attach_frozen_what_changed(current, previous)
    return previous, current


def test_production_shaped_league_changes_and_parity():
    _previous, current = _real_pair()
    package = current.payload['trusted_team_boards']
    carriers = tonight_read_model._frozen_what_changed_by_team(current, package)
    changes = tonight_read_model.build_league_changes(carriers)

    assert [(item['team_abbreviation'], item['change_class']) for item in changes] == [
        ('BAL', 'team_state_changed'),
        ('BOS', 'active_bullpen_joined'),
        ('BAL', 'back_to_back_started'),
        ('CHC', 'three_in_four_started'),
        ('CIN', 'high_pitch_outing_started'),
        ('CLE', 'new_short_start'),
    ]
    assert changes[0]['headline'] == 'BAL moved from Fresh to Stretched.'
    joined = changes[1]
    assert joined['detail'] == 'Verified transaction: Recalled.'
    assert joined['source_ref'].endswith('#transaction:tx-111-9')
    # The same move is not repeated as a standalone transaction item.
    assert not [item for item in changes if item['change_class'] == 'verified_transaction']
    assert changes[-1]['game_pks'] == [4401]
    assert 116 not in {item['team_id'] for item in changes}           # F: quiet
    for item in changes:
        _assert_clean_change(item)

    # Parity: every item is one event of that team's frozen carrier in this snapshot.
    for item in changes:
        carrier = package['by_team_id'][str(item['team_id'])]['frozen_what_changed']
        assert carrier['current_snapshot_id'] == current.id
        matches = [
            event for event in carrier['events']
            if event['event_type'] == item['change_class']
            and (event.get('event_date') == item['occurred_on'])
        ]
        assert len(matches) == 1, item
        if item['change_class'] != 'team_state_changed':
            assert matches[0]['summary'].startswith(item['headline'])
    assert tonight_read_model.build_league_changes(carriers) == changes


def test_build_populates_league_changes_refs_and_count_frozen():
    _previous, current = _real_pair()
    slate = [
        SimpleNamespace(game_pk=1, game_time_utc=datetime(2026, 9, 25, 23, 5),
                        away_team_id=110, home_team_id=111, normalized_state='upcoming',
                        status_detailed='Scheduled', game_number=1, last_synced=None),
        SimpleNamespace(game_pk=2, game_time_utc=datetime(2026, 9, 25, 23, 10),
                        away_team_id=116, home_team_id=114, normalized_state='upcoming',
                        status_detailed='Scheduled', game_number=1, last_synced=None),
    ]
    payload = tonight_read_model.build_tonight_v1(current, slate, generated_at=datetime(2026, 9, 25))
    changes = payload['league_changes']
    assert payload['summary']['change_count'] == len(changes) == 6
    ids = {item['team_id']: [c['change_id'] for c in changes if c['team_id'] == item['team_id']]
           for item in changes}
    games = {game['game_pk']: game for game in payload['games']}
    assert games[1]['away']['change_refs'] == ids[110] and len(ids[110]) == 2
    assert games[1]['home']['change_refs'] == ids[111]
    assert games[2]['away']['change_refs'] == []                       # quiet team
    assert games[2]['home']['change_refs'] == ids[114]
    # TN-04 context is authored from the TeamSides alone, independent of changes.
    for game in payload['games']:
        assert game['context'] == tonight_read_model.present_matchup_context(
            tonight_read_model.build_matchup_context(
                {**game['away'], 'change_refs': []}, {**game['home'], 'change_refs': []},
            ), game['state'],
        )
    again = tonight_read_model.build_tonight_v1(current, slate, generated_at=datetime(2026, 9, 26))
    assert tonight_read_model.content_sha256(again) == tonight_read_model.content_sha256(payload)


# ── TN-06: featured games ────────────────────────────────────────────────────
# Fixed rule priority over the frozen game cards and retained TN-05 changes.

import ast as _ast  # noqa: E402
import inspect as _inspect  # noqa: E402
import itertools as _itertools  # noqa: E402

_TEAM_IDS = _itertools.count(200)


def _fside(abbr, state='fresh', *, team_id=None, refs=(), **kwargs):
    side = _ctx_side(abbr, state, **kwargs)
    side['team_id'] = team_id if team_id is not None else next(_TEAM_IDS)
    side['change_refs'] = list(refs)
    return side


def _fgame(game_pk, away, home, *, state='scheduled', first_pitch='2026-09-25T23:05:00Z',
           game_number=1):
    return {
        'game_pk': game_pk, 'game_number': game_number, 'first_pitch_utc': first_pitch,
        'state': state, 'away': away, 'home': home,
        'context': {'sentence': None, 'reason_codes': [], 'evidence_state': 'complete'},
        'featured': False, 'featured_reason_codes': [],
    }


def _fchange(change_id, team_id, change_class):
    return {'change_id': change_id, 'team_id': team_id, 'change_class': change_class}


def _reasons(game, changes=()):
    return tonight_read_model.featured_reasons_for_game(
        game, {item['change_id']: item for item in changes},
    )


@pytest.mark.parametrize(('away', 'home', 'changes', 'expected'), [
    (_fside('SEA', 'vulnerable'), _fside('HOU'), (), ['vulnerable_team']),              # 1
    (_fside('SEA', 'vulnerable'), _fside('HOU', 'vulnerable'), (), ['vulnerable_team']),  # 2
    (_fside('SEA', team_id=150, refs=['c1']), _fside('HOU'),
     (_fchange('c1', 150, 'team_state_changed'),), ['team_state_change']),              # 3
    (_fside('SEA', b2b=2), _fside('HOU'), (), ['multiple_back_to_back_arms']),          # 4
    (_fside('SEA', b2b=1), _fside('HOU'), (), []),                                      # 5
    (_fside('SEA', three=1), _fside('HOU'), (), ['three_in_four_pressure']),            # 6
    (_fside('SEA', short=1), _fside('HOU'), (), ['short_start_transfer']),              # 7
    (_fside('SEA', team_id=151, refs=['j1']), _fside('HOU'),
     (_fchange('j1', 151, 'active_bullpen_joined'),), ['bullpen_membership_change']),   # 8
    (_fside('SEA', team_id=152, refs=['l1']), _fside('HOU'),
     (_fchange('l1', 152, 'active_bullpen_left'),), ['bullpen_membership_change']),     # 9
    (_fside('SEA', team_id=153, refs=['t1', 'b1']), _fside('HOU'),
     (_fchange('t1', 153, 'verified_transaction'),
      _fchange('b1', 153, 'back_to_back_started')), []),                                # 10
    (_fside('SEA', 'vulnerable', team_state=False), _fside('HOU'), (), []),             # 11
    (_fside('SEA', b2b=3, rest=False), _fside('HOU'), (), []),                          # 12
    (_fside('SEA', three=None), _fside('HOU', three=None), (), []),                     # 13
    (_fside('SEA', short=None), _fside('HOU'), (), []),                                 # 14
    (_fside('SEA'), _fside('HOU'), (), []),                                             # 15
])
def test_featured_rules_use_only_authoritative_frozen_facts(away, home, changes, expected):
    game = _fgame(1, away, home)
    assert _reasons(game, changes) == expected
    selected = tonight_read_model.select_featured_games([game], list(changes))
    assert selected == ([(1, expected)] if expected else [])


def test_unresolved_or_foreign_change_refs_never_qualify():
    side = _fside('SEA', team_id=160, refs=['missing', 'other-team'])
    changes = [_fchange('other-team', 999, 'team_state_changed')]
    assert _reasons(_fgame(1, side, _fside('HOU')), changes) == []


def test_all_applicable_reasons_are_retained_in_priority_order():  # 22
    away = _fside('SEA', 'vulnerable', team_id=161, refs=['s', 'j'], b2b=3, three=2, short=1)
    changes = [_fchange('s', 161, 'team_state_changed'), _fchange('j', 161, 'active_bullpen_left')]
    assert _reasons(_fgame(1, away, _fside('HOU')), changes) == list(
        tonight_read_model.FEATURED_RULE_PRIORITY
    )


@pytest.mark.parametrize('state', ['live', 'final', 'postponed', 'suspended'])
def test_only_pregame_states_are_eligible(state):  # 24
    game = _fgame(1, _fside('SEA', 'vulnerable'), _fside('HOU', b2b=4), state=state)
    assert _reasons(game) == []
    assert _reasons(_fgame(1, _fside('SEA', 'vulnerable'), _fside('HOU'), state='uncertain')) == [
        'vulnerable_team',
    ]


def test_priority_order_without_a_score():  # 23 + priority test
    a = _fgame(10, _fside('SEA', 'vulnerable', b2b=3, short=1), _fside('HOU'),
               first_pitch='2026-09-26T02:10:00Z')
    b_side = _fside('BOS', team_id=170, refs=['sb'])
    b = _fgame(11, b_side, _fside('NYY'), first_pitch='2026-09-25T17:05:00Z')
    c = _fgame(12, _fside('ATL', three=1), _fside('PHI'), first_pitch='2026-09-25T16:05:00Z')
    d_side = _fside('TEX', team_id=171, refs=['dj'])
    d = _fgame(13, d_side, _fside('KC'), first_pitch='2026-09-25T15:05:00Z')
    changes = [_fchange('sb', 170, 'team_state_changed'), _fchange('dj', 171, 'active_bullpen_joined')]
    games = [d, c, b, a]
    pks = tonight_read_model.apply_featured_games(games, changes)
    assert pks == [10, 11, 12, 13]
    assert a['featured_reason_codes'] == [
        'vulnerable_team', 'multiple_back_to_back_arms', 'short_start_transfer',
    ]


def test_cap_of_four_and_time_game_number_pk_tiebreaks():  # 16, 18, 19, 20, 21 + cap test
    games = [
        _fgame(20, _fside('A1', b2b=2), _fside('B1'), first_pitch=None),                       # unknown time
        _fgame(21, _fside('A2', b2b=2), _fside('B2'), first_pitch='2026-09-25T23:05:00Z', game_number=2),
        _fgame(22, _fside('A3', b2b=2), _fside('B3'), first_pitch='2026-09-25T23:05:00Z', game_number=1),
        _fgame(23, _fside('A4', b2b=2), _fside('B4'), first_pitch='2026-09-25T17:05:00Z'),
        _fgame(25, _fside('A5', three=1), _fside('B5'), first_pitch='2026-09-25T15:05:00Z'),
        _fgame(24, _fside('A6', three=1), _fside('B6'), first_pitch='2026-09-25T15:05:00Z'),
        _fgame(26, _fside('A7', short=1), _fside('B7'), first_pitch='2026-09-25T12:05:00Z'),
    ]
    pks = tonight_read_model.apply_featured_games(games, [])
    assert pks == [23, 22, 21, 20]
    assert len(pks) == tonight_read_model.FEATURED_MAX == 4
    assert [g['game_pk'] for g in games if g['featured']] == [20, 21, 22, 23]
    assert all(not g['featured'] and g['featured_reason_codes'] == [] for g in games[4:])
    # Same inputs in any order give the same selection.
    assert tonight_read_model.apply_featured_games(list(reversed(games)), []) == pks
    # game_pk breaks a full tie; fewer than four qualifying stays fewer.
    tied = [
        _fgame(31, _fside('X1', three=1), _fside('Y1')),
        _fgame(30, _fside('X2', three=1), _fside('Y2')),
        _fgame(32, _fside('X3'), _fside('Y3')),
    ]
    assert tonight_read_model.apply_featured_games(tied, []) == [30, 31]   # 17


def test_featured_selection_has_no_numeric_score():  # 25
    identifiers = set()
    for helper in (tonight_read_model.select_featured_games,
                   tonight_read_model.featured_reasons_for_game,
                   tonight_read_model.apply_featured_games):
        tree = _ast.parse(_inspect.getsource(helper))
        identifiers |= {node.id for node in _ast.walk(tree) if isinstance(node, _ast.Name)}
        identifiers |= {node.attr for node in _ast.walk(tree) if isinstance(node, _ast.Attribute)}
        identifiers |= {node.arg for node in _ast.walk(tree) if isinstance(node, _ast.arg)}
    assert not {name for name in identifiers
                if any(word in name.lower() for word in ('score', 'weight', 'rank'))}
    assert 'sum' not in identifiers
    games = [_fgame(1, _fside('SEA', 'vulnerable'), _fside('HOU'))]
    tonight_read_model.apply_featured_games(games, [])
    assert not any('score' in key for key in games[0])


def test_production_shaped_featured_games_and_parity():
    """Six games: TeamSide-shaped frozen facts plus real TB-09 league changes."""
    _previous, current = _real_pair()
    real = tonight_read_model.build_tonight_v1(current, [
        SimpleNamespace(game_pk=99, game_time_utc=datetime(2026, 9, 25, 12), away_team_id=110,
                        home_team_id=111, normalized_state='upcoming', status_detailed='Scheduled',
                        game_number=1, last_synced=None),
    ], generated_at=datetime(2026, 9, 25))
    league_changes = real['league_changes']
    bal_refs = real['games'][0]['away']['change_refs']
    assert [c['change_class'] for c in league_changes if c['team_id'] == 110][0] == 'team_state_changed'
    games = [
        _fgame(1, _fside('SEA', 'vulnerable'), _fside('HOU', 'fresh'),
               first_pitch='2026-09-26T02:10:00Z'),                                   # Vulnerable
        _fgame(2, _fside('BAL', team_id=110, refs=bal_refs), _fside('NYY'),
               first_pitch='2026-09-25T23:05:00Z'),                                   # Team State change
        _fgame(3, _fside('ATL', b2b=2), _fside('PHI'), first_pitch='2026-09-25T23:20:00Z'),
        _fgame(4, _fside('CHC', three=1), _fside('MIL'), first_pitch='2026-09-25T18:20:00Z'),
        _fgame(5, _fside('CLE', short=2), _fside('DET'), first_pitch='2026-09-25T17:10:00Z'),
        _fgame(6, _fside('TEX'), _fside('KC'), first_pitch='2026-09-25T16:05:00Z'),  # no condition
    ]
    stored_changes = deepcopy(league_changes)
    stored_refs = [deepcopy((g['away']['change_refs'], g['home']['change_refs'])) for g in games]
    pks = tonight_read_model.apply_featured_games(games, league_changes)

    assert pks == [1, 2, 3, 4]
    by_pk = {g['game_pk']: g for g in games}
    assert by_pk[1]['featured_reason_codes'] == ['vulnerable_team']
    assert by_pk[2]['featured_reason_codes'] == ['team_state_change']
    assert by_pk[3]['featured_reason_codes'] == ['multiple_back_to_back_arms']
    assert by_pk[4]['featured_reason_codes'] == ['three_in_four_pressure']
    # Game 5 qualifies (short start) but falls below the cap; game 6 does not qualify.
    assert tonight_read_model.featured_reasons_for_game(
        by_pk[5], {c['change_id']: c for c in league_changes}) == ['short_start_transfer']
    assert by_pk[5]['featured'] is False and by_pk[6]['featured'] is False
    # Parity: every reason is a frozen field of the stored card or a retained change.
    assert by_pk[1]['away']['team_state']['public_state'] == 'vulnerable'
    assert by_pk[1]['away']['team_state']['available'] is True
    ref = by_pk[2]['away']['change_refs'][0]
    assert next(c for c in league_changes if c['change_id'] == ref)['change_class'] == 'team_state_changed'
    assert by_pk[3]['away']['rest']['available'] is True
    assert by_pk[3]['away']['rest']['back_to_back_count'] == 2
    assert by_pk[4]['away']['multi_day_usage']['three_in_four_count'] == 1
    # Selection never changes league changes or refs.
    assert league_changes == stored_changes
    assert [(g['away']['change_refs'], g['home']['change_refs']) for g in games] == stored_refs


def test_build_features_from_the_same_frozen_payload():
    """The real builder marks cards and fills featured_game_pks from its own payload."""
    _previous, current = _real_pair()
    slate = [SimpleNamespace(
        game_pk=pk, game_time_utc=datetime(2026, 9, 25, 17 + pk), away_team_id=away,
        home_team_id=home, normalized_state='upcoming', status_detailed='Scheduled',
        game_number=1, last_synced=None,
    ) for pk, away, home in ((1, 110, 117), (2, 111, 118), (3, 116, 108))]
    payload = tonight_read_model.build_tonight_v1(current, slate, generated_at=datetime(2026, 9, 25))
    games = {game['game_pk']: game for game in payload['games']}
    changes = {item['change_id']: item for item in payload['league_changes']}
    assert payload['featured_game_pks'] == [1, 2]
    assert games[1]['featured_reason_codes'] == ['team_state_change']
    assert games[2]['featured_reason_codes'] == ['bullpen_membership_change']
    assert games[3]['featured'] is False and games[3]['featured_reason_codes'] == []
    for game in payload['games']:
        assert game['featured'] == (game['game_pk'] in payload['featured_game_pks'])
        if game['featured']:
            assert game['featured_reason_codes'] == tonight_read_model.featured_reasons_for_game(
                game, changes)
    again = tonight_read_model.build_tonight_v1(current, slate, generated_at=datetime(2026, 9, 26))
    assert tonight_read_model.content_sha256(again) == tonight_read_model.content_sha256(payload)


# ── TN-07: lead development ──────────────────────────────────────────────────
# Zero or one lead, strict rule priority, retained TN-05 changes only.

def _state_item(change_id, team_id, previous, current, occurred_on=None):
    return {
        'change_id': change_id, 'team_id': team_id, 'change_class': 'team_state_changed',
        'state_change': {'from': previous, 'to': current}, 'occurred_on': occurred_on,
        'evidence_state': 'complete',
    }


def _rotation(side, *, short=1, innings='6.0', status='complete'):
    side['rotation'] = {'short_start_count': short, 'bullpen_innings': innings,
                        'games_analyzed': 5, 'status': status}
    return side


def _lead(games, changes=()):
    return tonight_read_model.select_lead(games, list(changes))


def _team_game(game_pk, team_id, abbr, team_state='fresh', *, opp='OPP', state='scheduled',
               first_pitch='2026-09-25T23:05:00Z', **side_kwargs):
    return _fgame(game_pk, _fside(abbr, team_state, team_id=team_id, **side_kwargs),
                  _fside(opp), state=state, first_pitch=first_pitch)


@pytest.mark.parametrize(('previous', 'current', 'lead_type', 'headline'), [
    ('Fresh', 'Vulnerable', 'team_state_to_vulnerable',
     'SEA moved into a Vulnerable bullpen state entering tonight.'),        # 1
    ('Stretched', 'Vulnerable', 'team_state_to_vulnerable',
     'SEA moved into a Vulnerable bullpen state entering tonight.'),        # 2
    ('Fresh', 'Stretched', 'team_state_change',
     'SEA moved from Fresh to Stretched entering tonight.'),                # 3
    ('Vulnerable', 'Stretched', 'team_state_change',
     'SEA moved from Vulnerable to Stretched entering tonight.'),           # 4
])
def test_team_state_leads_use_the_retained_change(previous, current, lead_type, headline):
    game = _team_game(1, 300, 'SEA', opp='HOU')
    lead = _lead([game], [_state_item('s1', 300, previous, current)])
    assert lead == {
        'lead_type': lead_type, 'headline': headline,
        'detail': 'SEA is scheduled to face HOU.', 'team_ids': [300], 'game_pk': 1,
        'change_refs': ['s1'], 'reason_codes': [lead_type], 'evidence_state': 'complete',
    }


def test_heavy_back_to_back_threshold_is_three():  # 5, 6
    lead = _lead([_team_game(1, 301, 'SEA', b2b=3)])
    assert lead['lead_type'] == 'heavy_back_to_back_pressure'
    assert lead['headline'] == 'SEA has 3 bullpen arms coming off back-to-back usage tonight.'
    assert lead['change_refs'] == []
    assert _lead([_team_game(1, 302, 'SEA', b2b=2)]) is None


@pytest.mark.parametrize(('short', 'innings', 'expected'), [
    (1, '5.0', "SEA's bullpen has absorbed 5.0 innings after a recent short start."),  # 7
    (2, '6.1', "SEA's bullpen has absorbed 6.1 innings after 2 recent short starts."),
    (1, 5.0, "SEA's bullpen has absorbed 5.0 innings after a recent short start."),
    (1, '4.2', None),                                                                  # 8
    (1, 4.9, None),                                                                    # 8
    (0, '8.0', None),                                                                  # 9
])
def test_short_start_transfer_threshold(short, innings, expected):
    side = _rotation(_fside('SEA', team_id=303), short=short, innings=innings)
    lead = _lead([_fgame(1, side, _fside('HOU'))])
    assert (lead['headline'] if lead else None) == expected


@pytest.mark.parametrize('status', ['partial', 'unavailable'])
def test_incomplete_rotation_is_not_a_lead(status):  # 20
    side = _rotation(_fside('SEA', team_id=304), innings='9.0', status=status)
    assert _lead([_fgame(1, side, _fside('HOU'))]) is None
    missing = _fside('SEA', team_id=305)
    missing['rotation'] = None
    assert _lead([_fgame(1, missing, _fside('HOU'))]) is None


def test_other_conditions_never_lead():  # 10, 11, 12, 13
    changes = [
        _fchange('h', 306, 'high_pitch_outing_started'),
        _fchange('j', 306, 'active_bullpen_joined'),
        _fchange('t', 306, 'verified_transaction'),
    ]
    games = [
        _team_game(1, 306, 'SEA', three=3, refs=['h', 'j', 't']),         # 3-in-4, high pitch, membership
        _team_game(2, 307, 'BOS', 'vulnerable'),                            # Vulnerable, no change event
        _team_game(3, 308, 'NYY', b2b=1),
    ]
    tonight_read_model.apply_featured_games(games, changes)
    assert games[0]['featured'] is True
    assert _lead(games, changes) is None


def test_off_day_team_change_cannot_lead():  # 14
    game = _team_game(1, 309, 'SEA')
    assert _lead([game], [_state_item('s', 999, 'Fresh', 'Vulnerable')]) is None


@pytest.mark.parametrize('state', ['live', 'final', 'postponed', 'suspended'])
def test_only_pregame_games_can_lead(state):  # 15-18
    changes = [_state_item('s', 310, 'Fresh', 'Vulnerable')]
    assert _lead([_team_game(1, 310, 'SEA', state=state, b2b=5)], changes) is None
    assert _lead([_team_game(1, 310, 'SEA', state='uncertain')], changes)['game_pk'] == 1


def test_unavailable_rest_is_never_a_b2b_lead():  # 19
    assert _lead([_team_game(1, 311, 'SEA', b2b=6, rest=False)]) is None


def test_tie_breaks_date_first_pitch_then_team():  # 21, 22, 23
    games = [
        _team_game(1, 312, 'SEA', first_pitch='2026-09-25T17:05:00Z'),
        _team_game(2, 313, 'BOS', first_pitch='2026-09-25T23:05:00Z'),
        _team_game(3, 314, 'ATL', first_pitch='2026-09-25T23:05:00Z'),
    ]
    dated = [
        _state_item('a', 312, 'Fresh', 'Vulnerable', occurred_on='2026-09-23'),
        _state_item('b', 313, 'Fresh', 'Vulnerable', occurred_on='2026-09-24'),
    ]
    assert _lead(games, dated)['team_ids'] == [313]                    # newer date wins
    undated = [
        _state_item('a', 312, 'Fresh', 'Vulnerable'),
        _state_item('b', 313, 'Fresh', 'Vulnerable'),
    ]
    assert _lead(games, undated)['team_ids'] == [312]                  # earlier first pitch
    same_time = [
        _state_item('b', 313, 'Fresh', 'Vulnerable'),
        _state_item('c', 314, 'Fresh', 'Vulnerable'),
    ]
    assert _lead(games, same_time)['team_ids'] == [314]                # ATL before BOS
    assert _lead(list(reversed(games)), list(reversed(same_time))) == _lead(games, same_time)


def test_lead_copy_guard_and_lengths():  # 24, 25
    long_name = 'X' * 130
    side = _fside(long_name, team_id=315, b2b=4)
    assert _lead([_fgame(1, side, _fside('HOU'))]) is None
    headlines = []
    for rule_games, changes in (
        ([_team_game(1, 316, 'SEA')], [_state_item('s', 316, 'Fresh', 'Vulnerable')]),
        ([_team_game(1, 316, 'SEA')], [_state_item('s', 316, 'Vulnerable', 'Fresh')]),
        ([_team_game(1, 317, 'SEA', b2b=12)], []),
        ([_fgame(1, _rotation(_fside('SEA', team_id=318), short=3, innings='14.2'), _fside('HOU'))], []),
    ):
        lead = _lead(rule_games, changes)
        headlines.append(lead['lead_type'])
        for text, limit in ((lead['headline'], 120), (lead['detail'], 140)):
            assert len(text) <= limit
            assert find_editorial_violations(
                text, terms=tonight_read_model.LEAD_BANNED_TERMS) == []
            assert find_editorial_violations(text) == []
            assert text.endswith('.') and '. ' not in text
    assert headlines == list(tonight_read_model.LEAD_RULE_PRIORITY)
    assert find_editorial_violations(
        'SEA is the best game and will likely win', terms=tonight_read_model.LEAD_BANNED_TERMS)


def test_lead_selection_has_no_numeric_score():  # 26
    identifiers = set()
    for helper in (tonight_read_model.select_lead, tonight_read_model._lead_candidate,
                   tonight_read_model.present_lead):
        tree = _ast.parse(_inspect.getsource(helper))
        identifiers |= {node.id for node in _ast.walk(tree) if isinstance(node, _ast.Name)}
        identifiers |= {node.attr for node in _ast.walk(tree) if isinstance(node, _ast.Attribute)}
        identifiers |= {node.arg for node in _ast.walk(tree) if isinstance(node, _ast.arg)}
    assert not {name for name in identifiers
                if any(word in name.lower() for word in ('score', 'weight', 'rank('))}
    assert 'sum' not in identifiers and 'max' not in identifiers


def test_lead_priority_ladder_down_to_null():
    a = _team_game(1, 320, 'ATL', first_pitch='2026-09-26T02:05:00Z')
    b = _team_game(2, 321, 'BOS', first_pitch='2026-09-25T17:05:00Z')
    c = _team_game(3, 322, 'CHC', b2b=4, first_pitch='2026-09-25T16:05:00Z')
    d = _fgame(4, _rotation(_fside('DET', team_id=323), innings='6.0'), _fside('KC'),
               first_pitch='2026-09-25T15:05:00Z')
    changes = [_state_item('a', 320, 'Fresh', 'Vulnerable'), _state_item('b', 321, 'Fresh', 'Stretched')]
    games = [a, b, c, d]
    assert _lead(games, changes)['game_pk'] == 1                      # A
    assert _lead([b, c, d], changes)['game_pk'] == 2                  # B
    assert _lead([c, d], changes)['game_pk'] == 3                     # C
    assert _lead([d], changes)['game_pk'] == 4                        # D
    assert _lead([], changes) is None                                 # quiet: null


def test_capped_out_team_state_change_never_leads():
    """TN-05 drops the 13th Team State change; the lead must not reconstruct it."""
    team_ids = sorted(_ABBR, key=lambda team_id: _ABBR[team_id])[:12] + [120]  # WSH sorts last
    entries = [_entry(team_id, [_state_change(team_id, 'Fresh',
                                              'Vulnerable' if team_id == 120 else 'Stretched')])
               for team_id in team_ids]
    changes = _league(*entries)
    assert len(changes) == 12 and 120 not in {item['team_id'] for item in changes}
    raw = dict(entries)[120]['carrier']['events'][0]
    assert raw['current_value'] == 'Vulnerable'          # present in the raw carrier
    wsh_game = _team_game(1, 120, 'WSH', opp='NYM')
    assert _lead([wsh_game], changes) is None
    other = _team_game(2, team_ids[0], _ABBR[team_ids[0]])
    assert _lead([wsh_game, other], changes)['lead_type'] == 'team_state_change'


def test_production_shaped_lead_and_parity():
    changes = _league(
        _entry(110, [_state_change(110, 'Fresh', 'Vulnerable')]),
        _entry(111, [_state_change(111, 'Fresh', 'Stretched')]),
    )
    games = [
        _fgame(1, _fside('BAL', team_id=110), _fside('NYY', team_id=147),
               first_pitch='2026-09-25T23:05:00Z'),
        _fgame(2, _fside('BOS', team_id=111), _fside('TB', team_id=139),
               first_pitch='2026-09-25T22:05:00Z'),
        _fgame(3, _fside('ATL', team_id=144, b2b=3), _fside('PHI', team_id=143),
               first_pitch='2026-09-25T21:05:00Z'),
        _fgame(4, _rotation(_fside('CLE', team_id=114), innings='6.0'), _fside('DET', team_id=116),
               first_pitch='2026-09-25T20:05:00Z'),
        _fgame(5, _fside('CHC', team_id=112, three=1), _fside('MIL', team_id=158),
               first_pitch='2026-09-25T19:05:00Z'),
        _fgame(6, _fside('TEX', team_id=140), _fside('KC', team_id=118),
               first_pitch='2026-09-25T18:05:00Z'),
    ]
    tonight_read_model.attach_change_refs([g[k] for g in games for k in ('away', 'home')], changes)
    featured = tonight_read_model.apply_featured_games(games, changes)
    before = deepcopy((games, changes, featured))

    lead = _lead(games, changes)

    assert lead['lead_type'] == 'team_state_to_vulnerable'
    assert (lead['game_pk'], lead['team_ids']) == (1, [110])
    assert lead['headline'] == 'BAL moved into a Vulnerable bullpen state entering tonight.'
    assert lead['detail'] == 'BAL is scheduled to face NYY.'
    # Parity: the lead's change ref is a retained change whose frozen labels drive the rule.
    ref = next(item for item in changes if item['change_id'] == lead['change_refs'][0])
    assert ref['team_id'] == 110 and ref['state_change'] == {'from': 'Fresh', 'to': 'Vulnerable'}
    assert lead['change_refs'] == games[0]['away']['change_refs']
    # Selecting the lead changes nothing else.
    assert deepcopy((games, changes, featured)) == before
    # Parity for the lower rules: each is a frozen TeamSide field.
    assert _lead(games[2:], changes)['headline'] == (
        'ATL has 3 bullpen arms coming off back-to-back usage tonight.')
    assert games[2]['away']['rest'] == {**games[2]['away']['rest'], 'available': True,
                                        'back_to_back_count': 3}
    assert _lead(games[3:], changes)['headline'] == (
        "CLE's bullpen has absorbed 6.0 innings after a recent short start.")
    assert games[3]['away']['rotation']['bullpen_innings'] == '6.0'
    assert _lead(games[4:], changes) is None             # 3-in-4 featured only, and a quiet game


def test_present_lead_marks_pregame_without_reselection():
    lead = _lead([_team_game(1, 330, 'SEA', b2b=3)])
    frozen = deepcopy(lead)
    for state, marked in (('scheduled', False), ('uncertain', False), ('live', True),
                          ('final', True), ('postponed', True), ('suspended', True)):
        shown = tonight_read_model.present_lead(lead, state)
        assert {k: v for k, v in shown.items() if k != 'reason_codes'} == {
            k: v for k, v in frozen.items() if k != 'reason_codes'}
        assert shown['reason_codes'] == ['heavy_back_to_back_pressure'] + (
            ['pregame_context'] if marked else [])
        assert tonight_read_model.present_lead(shown, state) == shown
    assert lead == frozen
    assert tonight_read_model.present_lead(None, 'final') is None


def test_real_build_lead_from_tb09_pair():
    _previous, current = _real_pair()
    slate = [SimpleNamespace(
        game_pk=pk, game_time_utc=datetime(2026, 9, 25, 17 + pk), away_team_id=away,
        home_team_id=home, normalized_state='upcoming', status_detailed='Scheduled',
        game_number=1, last_synced=None,
    ) for pk, away, home in ((1, 110, 117), (2, 111, 118))]
    payload = tonight_read_model.build_tonight_v1(current, slate, generated_at=datetime(2026, 9, 25))
    lead = payload['lead']
    assert lead['lead_type'] == 'team_state_change'
    assert lead['headline'] == 'BAL moved from Fresh to Stretched entering tonight.'
    assert lead['change_refs'] == payload['games'][0]['away']['change_refs'][:1]
    assert lead['game_pk'] == 1 and lead['team_ids'] == [110]
    # BOS's joined change and BAL's B2B start never lead; only the retained state change does.
    assert payload['featured_game_pks'] == [1, 2]
    again = tonight_read_model.build_tonight_v1(current, slate, generated_at=datetime(2026, 9, 26))
    assert again['lead'] == lead
    quiet = tonight_read_model.build_tonight_v1(current, slate[1:], generated_at=datetime(2026, 9, 25))
    assert quiet['lead'] is None                                        # no filler
