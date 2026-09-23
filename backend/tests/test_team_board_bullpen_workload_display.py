"""Active Bullpen shows governed bullpen workload, not total pitching workload.

Physical workload (FatigueScore, availability, Team State) keeps counting every
pitching line. The Active Bullpen 7d App / 7d P / Last P columns count only the
appearances ``services.game_shape`` classifies as bullpen workload: relief lines
(including bulk followers) and openers in an opener/bulk game. A conventional
rotation start is excluded; an unclassifiable line withholds the value.
"""

from datetime import date, timedelta
import importlib
from types import SimpleNamespace

import pytest

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_run import SyncRun
from services import dashboard_snapshot
from services import game_shape
from services import public_serving_authority
from services import public_team_relief_work
from services import slate_coverage
from services import sync as sync_service
from services import team_board_v2
from services.fatigue import calculate_fatigue
from services.public_fatigue_view import public_workload_facts
from tests.db_config import (
    create_test_schema,
    drop_test_schema,
    test_database_url as _test_database_url,
)
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
from utils.db import db
from utils.time import utc_now_naive


SF = 137
OPP = 119
RESOLVED = GameLog.APPEARANCE_TEAM_RESOLVED
ANCHOR = date(2026, 9, 22)
REFERENCE = ANCHOR + timedelta(days=1)


def _line(pitcher_id, game_pk, game_date, *, games_started=0, outs=3,
          pitches=15, team=SF, status=RESOLVED):
    return SimpleNamespace(
        id=hash((pitcher_id, game_pk)),
        pitcher_id=pitcher_id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        games_started=games_started,
        innings_pitched_outs=outs,
        pitches_thrown=pitches,
        appearance_team_id=team,
        appearance_team_status=status,
    )


def _arm(pitcher_id, name):
    return SimpleNamespace(id=pitcher_id, full_name=name)


def _coverage(anchor=ANCHOR, days=7):
    return {
        (anchor - timedelta(days=offset)).isoformat(): {
            'slate_date': (anchor - timedelta(days=offset)).isoformat(),
            'complete_enough_to_publish': True,
            'coverage_known': True,
            'reason_codes': ['slate_complete'],
        }
        for offset in range(days)
    }


def _carrier(rows, arms, *, team_game_logs=None):
    by_id = {arm.id: arm for arm in arms}
    return public_team_relief_work.build_recent_usage_rest_carrier(
        [(row, by_id[row.pitcher_id]) for row in rows if row.pitcher_id in by_id],
        data_through=ANCHOR,
        reference_date=REFERENCE,
        active_pitchers={arm.id: {'name': arm.full_name} for arm in arms},
        coverage_by_date=_coverage(),
        # Production passes every stored line of each start's game.
        team_game_logs=rows if team_game_logs is None else team_game_logs,
    )


def _item(carrier, pitcher_id):
    return next(
        item for item in carrier['active_pitchers'] if item['pitcher_id'] == pitcher_id
    )


def _seven(item):
    window = item['windows']['last_7_days']
    return window['appearances']['value'], window['pitches']['value']


def _rotation_game(game_pk, game_date, starter_id, starter_outs, starter_pitches,
                   relief_outs=(3, 3, 3), first_reliever_id=900):
    rows = [_line(starter_id, game_pk, game_date, games_started=1,
                  outs=starter_outs, pitches=starter_pitches)]
    for offset, outs in enumerate(relief_outs):
        rows.append(_line(first_reliever_id + offset, game_pk, game_date,
                          outs=outs, pitches=outs * 5))
    return rows


# ── Governed appearance classification (services.game_shape) ────────────────

def test_relief_line_is_bullpen_workload_on_its_own_flag():
    relief = _line(1, 10, ANCHOR, outs=2)
    assert game_shape.bullpen_workload_appearance_class(relief, [relief]) == (
        game_shape.BULLPEN_WORKLOAD_RELIEF
    )


def test_opener_in_opener_bulk_game_is_bullpen_workload():
    opener = _line(1, 10, ANCHOR, games_started=1, outs=3, pitches=18)
    bulk = _line(2, 10, ANCHOR, outs=15, pitches=70)
    closer = _line(3, 10, ANCHOR, outs=9, pitches=30)
    game = [opener, bulk, closer]
    assert game_shape.classify_game_shape(game)['shape'] == game_shape.SHAPE_OPENER_BULK_GAME
    assert game_shape.bullpen_workload_appearance_class(opener, game) == (
        game_shape.BULLPEN_WORKLOAD_OPENER
    )
    assert game_shape.bullpen_workload_appearance_class(bulk, game) == (
        game_shape.BULLPEN_WORKLOAD_RELIEF
    )


@pytest.mark.parametrize('starter_outs', [14, 17, 18])
def test_rotation_start_is_not_bullpen_workload(starter_outs):
    game = _rotation_game(10, ANCHOR, 1, starter_outs, 85)
    assert game_shape.bullpen_workload_appearance_class(game[0], game) == (
        game_shape.BULLPEN_WORKLOAD_ROTATION_START
    )


def test_unknown_start_flag_and_unclassifiable_game_stay_unknown():
    unknown = _line(1, 10, ANCHOR, games_started=None)
    assert game_shape.bullpen_workload_appearance_class(unknown, [unknown]) == (
        game_shape.BULLPEN_WORKLOAD_UNKNOWN
    )
    starter = _line(1, 11, ANCHOR, games_started=1, outs=12)
    other_starter = _line(2, 11, ANCHOR, games_started=1, outs=6)
    assert game_shape.bullpen_workload_appearance_class(
        starter, [starter, other_starter]
    ) == game_shape.BULLPEN_WORKLOAD_UNKNOWN
    # A start classified without its own line in the game group is not guessed.
    assert game_shape.bullpen_workload_appearance_class(starter, [other_starter]) == (
        game_shape.BULLPEN_WORKLOAD_UNKNOWN
    )


# ── Giants production shape (snapshot 3435, data_through 2026-09-22) ───────

PERDOMO, MARTE, MOLINA = 701, 702, 703


def _giants_rows():
    return (
        _rotation_game(823004, date(2026, 9, 16), MOLINA, 17, 82, relief_outs=(4, 3, 3))
        + _rotation_game(823898, date(2026, 9, 18), PERDOMO, 14, 83, relief_outs=(4, 3, 3, 3))
        + _rotation_game(823899, date(2026, 9, 19), MARTE, 14, 97, relief_outs=(4, 3, 3, 3))
        + _rotation_game(823166, date(2026, 9, 22), MOLINA, 18, 85, relief_outs=(3, 3, 3))
    )


def test_giants_conventional_starts_leave_the_bullpen_display():
    rows = _giants_rows()
    arms = [_arm(PERDOMO, 'Cesar Perdomo'), _arm(MARTE, 'Yunior Marte'),
            _arm(MOLINA, 'Anthony Molina')]
    carrier = _carrier(rows, arms)

    for pitcher_id in (PERDOMO, MARTE, MOLINA):
        item = _item(carrier, pitcher_id)
        assert _seven(item) == (0, 0)
        last = item['last_bullpen_appearance']
        assert last['value'] is None
        assert last['status'] == public_team_relief_work.RECENT_USAGE_REST_COMPLETE

    display = public_team_relief_work.author_active_bullpen_workload_display(
        carrier, [PERDOMO, MARTE, MOLINA],
    )
    for pitcher_id in (PERDOMO, MARTE, MOLINA):
        assert display[pitcher_id]['appearances_last_7'] == 0
        assert display[pitcher_id]['pitches_last_7_days'] == 0
        assert display[pitcher_id]['last_appearance'] is None


def test_giants_starts_still_count_as_physical_workload():
    """FatigueScore semantics are unchanged: a start is physical workload."""
    rows = _giants_rows()
    by_pitcher = {}
    for row in rows:
        by_pitcher.setdefault(row.pitcher_id, []).append(row)
    expected = {PERDOMO: (1, 83), MARTE: (1, 97), MOLINA: (2, 167)}
    for pitcher_id, (apps, pitches) in expected.items():
        logs = sorted(by_pitcher[pitcher_id], key=lambda log: log.game_date, reverse=True)
        score = calculate_fatigue(
            SimpleNamespace(id=pitcher_id), logs, reference_date=REFERENCE,
        )
        assert (score.appearances_last_7, score.pitches_last_7_days) == (apps, pitches)
        assert score.raw_score > 0


# ── Opener, bullpen game, bulk relief, mixed usage ──────────────────────────

def test_opener_counts_in_seven_day_workload_and_last_pitches():
    opener_id = 11
    rows = [
        _line(opener_id, 50, ANCHOR - timedelta(days=1), games_started=1, outs=3, pitches=19),
        _line(12, 50, ANCHOR - timedelta(days=1), outs=15, pitches=72),
        _line(13, 50, ANCHOR - timedelta(days=1), outs=9, pitches=31),
    ]
    carrier = _carrier(rows, [_arm(opener_id, 'Opener Arm')])
    item = _item(carrier, opener_id)
    assert _seven(item) == (1, 19)
    assert item['last_bullpen_appearance']['value'] == 19
    assert item['last_bullpen_appearance']['appearance_class'] == (
        game_shape.BULLPEN_WORKLOAD_OPENER
    )


def test_bullpen_game_lines_all_count():
    game_date = ANCHOR - timedelta(days=2)
    rows = [_line(20 + index, 60, game_date, outs=6, pitches=25) for index in range(5)]
    assert game_shape.classify_game_shape(rows)['shape'] == game_shape.SHAPE_BULLPEN_GAME
    carrier = _carrier(rows, [_arm(20, 'First Bullpen-Game Arm')])
    item = _item(carrier, 20)
    assert _seven(item) == (1, 25)
    assert item['last_bullpen_appearance']['value'] == 25


def test_bulk_follower_counts_in_full():
    bulk_id = 31
    game_date = ANCHOR - timedelta(days=3)
    rows = [
        _line(30, 70, game_date, games_started=1, outs=3, pitches=16),
        _line(bulk_id, 70, game_date, outs=16, pitches=78),
        _line(32, 70, game_date, outs=8, pitches=27),
    ]
    carrier = _carrier(rows, [_arm(bulk_id, 'Bulk Arm')])
    item = _item(carrier, bulk_id)
    assert _seven(item) == (1, 78)
    assert item['last_bullpen_appearance']['value'] == 78


def test_long_reliever_in_normal_game_counts_as_relief():
    long_id = 41
    rows = _rotation_game(80, ANCHOR - timedelta(days=1), 40, 12, 70,
                          relief_outs=(), first_reliever_id=0)
    rows.append(_line(long_id, 80, ANCHOR - timedelta(days=1), outs=12, pitches=61))
    carrier = _carrier(rows, [_arm(long_id, 'Long Arm')])
    assert _seven(_item(carrier, long_id)) == (1, 61)


def test_mixed_usage_start_is_excluded_but_relief_still_displays():
    swing_id = 51
    relief_day = ANCHOR - timedelta(days=5)
    rows = [_line(swing_id, 90, relief_day, outs=4, pitches=22)]
    rows += _rotation_game(91, ANCHOR - timedelta(days=1), swing_id, 16, 88)
    carrier = _carrier(rows, [_arm(swing_id, 'Swing Arm')])
    item = _item(carrier, swing_id)
    assert _seven(item) == (1, 22)
    last = item['last_bullpen_appearance']
    assert (last['value'], last['game_date']) == (22, relief_day.isoformat())

    logs = sorted([row for row in rows if row.pitcher_id == swing_id],
                  key=lambda log: log.game_date, reverse=True)
    score = calculate_fatigue(SimpleNamespace(id=swing_id), logs, reference_date=REFERENCE)
    assert (score.appearances_last_7, score.pitches_last_7_days) == (2, 110)
    assert score.days_since_last_appearance == 2


# ── Fail-closed evidence ────────────────────────────────────────────────────

def test_unknown_start_flag_withholds_windows_and_last_pitches():
    pitcher_id = 61
    rows = [
        _line(pitcher_id, 100, ANCHOR - timedelta(days=4), outs=3, pitches=14),
        _line(pitcher_id, 101, ANCHOR - timedelta(days=1), games_started=None, pitches=40),
    ]
    carrier = _carrier(rows, [_arm(pitcher_id, 'Unknown Flag Arm')])
    item = _item(carrier, pitcher_id)
    window = item['windows']['last_7_days']
    assert window['appearances']['value'] is None
    assert window['appearances']['status'] == public_team_relief_work.RECENT_USAGE_REST_UNKNOWN
    assert item['last_bullpen_appearance']['value'] is None
    assert item['last_bullpen_appearance']['status'] == (
        public_team_relief_work.RECENT_USAGE_REST_UNKNOWN
    )
    display = public_team_relief_work.author_active_bullpen_workload_display(
        carrier, [pitcher_id],
    )[pitcher_id]
    assert display['appearances_last_7'] is None
    assert display['pitches_last_7_days'] is None
    assert display['last_appearance'] is None


def test_start_in_game_with_unresolved_side_stays_unknown():
    pitcher_id = 71
    game_date = ANCHOR - timedelta(days=2)
    start = _line(pitcher_id, 110, game_date, games_started=1, outs=3, pitches=20)
    follower = _line(72, 110, game_date, outs=15, pitches=70)
    unresolved = _line(73, 110, game_date, outs=3, pitches=12, team=None,
                       status='unresolved')
    carrier = _carrier([start], [_arm(pitcher_id, 'Opener Arm')],
                       team_game_logs=[start, follower, unresolved])
    window = _item(carrier, pitcher_id)['windows']['last_7_days']
    assert window['appearances']['status'] == public_team_relief_work.RECENT_USAGE_REST_UNKNOWN


def test_same_day_relief_outings_do_not_claim_one_last_outing():
    pitcher_id = 81
    game_date = ANCHOR - timedelta(days=1)
    rows = [
        _line(pitcher_id, 120, game_date, outs=3, pitches=14),
        _line(pitcher_id, 121, game_date, outs=3, pitches=17),
    ]
    carrier = _carrier(rows, [_arm(pitcher_id, 'Doubleheader Arm')])
    item = _item(carrier, pitcher_id)
    assert _seven(item) == (2, 31)
    last = item['last_bullpen_appearance']
    assert last['value'] is None
    assert last['reason_codes'] == [
        public_team_relief_work.RECENT_USAGE_REST_REASON_SAME_DAY_ORDER_UNKNOWN
    ]


def test_unavailable_carrier_never_falls_back_to_total_workload():
    carrier = public_team_relief_work.build_recent_usage_rest_carrier(
        [], data_through=ANCHOR, reference_date=ANCHOR,
    )
    display = public_team_relief_work.author_active_bullpen_workload_display(carrier, [5])
    assert display[5]['appearances_last_7'] is None
    assert display[5]['pitches_last_7_days'] is None
    assert display[5]['last_appearance'] is None


# ── Active Bullpen projection ───────────────────────────────────────────────

def _board(card):
    return {'groups': [{'pitchers': [card]}]}


def test_active_bullpen_arm_uses_frozen_bullpen_display():
    card = {
        'pitcher_id': PERDOMO,
        'name': 'Cesar Perdomo',
        'workload_facts': {
            'days_since_last_appearance': 5,
            'appearances_last_7': 1,
            'pitches_last_7_days': 83,
            'back_to_back': False,
        },
        'last_appearance': {'game_date': '2026-09-18', 'pitches': 83},
        'bullpen_workload_display': {
            'contract': public_team_relief_work.ACTIVE_BULLPEN_WORKLOAD_DISPLAY_CONTRACT,
            'appearances_last_7': 0,
            'pitches_last_7_days': 0,
            'last_appearance': None,
        },
    }
    arm = team_board_v2._active_arms(_board(card))[0]
    assert arm['workload']['appearances_last_7'] == 0
    assert arm['workload']['pitches_last_7_days'] == 0
    assert arm['last_appearance'] is None
    # Rest is physical and unchanged.
    assert arm['workload']['days_since_last_appearance'] == 5


def test_legacy_publication_without_display_keeps_its_frozen_values():
    card = {
        'pitcher_id': PERDOMO,
        'name': 'Cesar Perdomo',
        'workload_facts': {'appearances_last_7': 1, 'pitches_last_7_days': 83},
        'last_appearance': {'game_date': '2026-09-18', 'pitches': 83},
    }
    arm = team_board_v2._active_arms(_board(card))[0]
    assert arm['workload']['appearances_last_7'] == 1
    assert arm['last_appearance'] == {'game_date': '2026-09-18', 'pitches': 83}


# ── Trusted publication: frozen, route-served, physical workload unchanged ──

def _dashboard_payload(reference_date):
    data_through = reference_date - timedelta(days=1)
    coverage = {
        'slate_date': data_through.isoformat(),
        'complete_enough_to_publish': True,
        'coverage_known': True,
        'reason_codes': ['no_scheduled_games', 'slate_complete'],
        'validations_passed': True,
    }
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


def _seed_giants(reference_date):
    anchor = reference_date - timedelta(days=1)
    pitchers = {}
    for mlb_id, name in ((6700001, 'Cesar Perdomo'), (6700002, 'Yunior Marte'),
                         (6700003, 'Anthony Molina'), (6700004, 'Opener Arm'),
                         (6700005, 'Middle Arm')):
        pitcher = Pitcher(
            mlb_id=mlb_id, full_name=name, team_id=SF,
            team_name='San Francisco Giants', team_abbreviation='SF',
            position='P', active=True, roster_status='active',
            roster_status_source='test_fixture',
            roster_status_updated_at=utc_now_naive(),
        )
        db.session.add(pitcher)
        db.session.flush()
        pitchers[name] = pitcher

    def add(pitcher, game_pk, game_date, *, gs=0, outs=3, pitches=15):
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=game_pk, game_date=game_date,
            game_type='R', games_started=gs, innings_pitched=outs / 3,
            innings_pitched_outs=outs, pitches_thrown=pitches,
            appearance_team_id=SF, appearance_team_status=RESOLVED,
            appearance_team_source='boxscore_side',
            appearance_team_reason='appearance_team_resolved_boxscore',
        ))

    # Earlier relief history keeps every arm bullpen-eligible (start share <= 0.2).
    for index in range(8):
        for offset, name in enumerate(pitchers):
            add(pitchers[name], 7000000 + index * 10 + offset,
                anchor - timedelta(days=20 + index), outs=3, pitches=14)

    middle = pitchers['Middle Arm']
    for game_pk, day, starter, outs, pitches in (
        (823004, 6, 'Anthony Molina', 17, 82),
        (823898, 4, 'Cesar Perdomo', 14, 83),
        (823899, 3, 'Yunior Marte', 14, 97),
        (823166, 0, 'Anthony Molina', 18, 85),
    ):
        add(pitchers[starter], game_pk, anchor - timedelta(days=day),
            gs=1, outs=outs, pitches=pitches)
        add(middle, game_pk, anchor - timedelta(days=day),
            outs=27 - outs, pitches=(27 - outs) * 4)
    # Opener game: the opener is bullpen workload, the bulk arm is relief.
    add(pitchers['Opener Arm'], 823500, anchor - timedelta(days=2), gs=1, outs=3, pitches=21)
    add(middle, 823500, anchor - timedelta(days=2), outs=24, pitches=88)
    db.session.flush()

    scores = {}
    for name, pitcher in pitchers.items():
        logs = (
            GameLog.query.filter_by(pitcher_id=pitcher.id)
            .order_by(GameLog.game_date.desc()).all()
        )
        score = calculate_fatigue(pitcher, logs, reference_date=reference_date)
        score.calculated_at = utc_now_naive()
        db.session.add(score)
        scores[name] = score
    db.session.commit()
    return pitchers, scores


@pytest.fixture
def giants_app(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', _test_database_url())
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = importlib.import_module('app').create_app('test')
    app.config['TRUSTED_PUBLIC_SERVING_ENABLED'] = True
    with app.app_context():
        create_test_schema(app)
        try:
            reference_date = public_serving_authority.product_current_date()
            pitchers, scores = _seed_giants(reference_date)
            monkeypatch.setattr(
                slate_coverage, 'compute_slate_coverage',
                lambda day, *args, **kwargs: {
                    'slate_date': day.isoformat(),
                    'complete_enough_to_publish': True,
                    'coverage_known': True,
                    'reason_codes': ['slate_complete'],
                },
            )
            seed_roster_readiness_snapshots([reference_date])
            from api import bullpen as bullpen_api

            monkeypatch.setattr(
                bullpen_api, 'build_bullpen_dashboard_payload',
                lambda **_kwargs: _dashboard_payload(reference_date),
            )
            assert public_serving_authority.install_public_serving_authority(app) is True
            run = SyncRun(
                job_name='giants_bullpen_display_test',
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
                sync_run_id=run.id, source='giants_bullpen_display_test',
                publish=True, raise_errors=True,
            )
            assert snapshot.is_published is True
            yield {
                'app': app, 'snapshot': snapshot, 'pitchers': pitchers,
                'scores': scores, 'reference_date': reference_date,
            }
        finally:
            db.session.remove()
            drop_test_schema(app)


def _core_arms(client):
    body = client.get(f'/api/bullpen/teams/{SF}/board-v2/core').get_json()
    return {arm['name']: arm for arm in body['active_bullpen']['arms']}, body


def test_published_giants_board_shows_bullpen_workload_only(giants_app):
    arms, body = _core_arms(giants_app['app'].test_client())
    assert body['publication_identity']['snapshot_id'] == giants_app['snapshot'].id

    for name in ('Cesar Perdomo', 'Yunior Marte', 'Anthony Molina'):
        arm = arms[name]
        assert arm['workload']['appearances_last_7'] == 0, name
        assert arm['workload']['pitches_last_7_days'] == 0, name
        assert arm['last_appearance'] is None, name

    opener = arms['Opener Arm']
    assert (opener['workload']['appearances_last_7'],
            opener['workload']['pitches_last_7_days']) == (1, 21)
    assert opener['last_appearance']['pitches'] == 21

    middle = arms['Middle Arm']
    assert middle['workload']['appearances_last_7'] == 5
    assert middle['workload']['pitches_last_7_days'] == (
        (27 - 17) * 4 + (27 - 14) * 4 + (27 - 14) * 4 + (27 - 18) * 4 + 88
    )
    assert middle['last_appearance']['pitches'] == (27 - 18) * 4


def test_published_giants_physical_workload_is_unchanged(giants_app):
    snapshot = giants_app['snapshot']
    package = snapshot.payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY]
    records = {
        record['name']: record for record in package['by_team_id'][str(SF)]['records']
    }
    expected = {'Cesar Perdomo': (1, 83), 'Yunior Marte': (1, 97),
                'Anthony Molina': (2, 167)}
    for name, (apps, pitches) in expected.items():
        score = giants_app['scores'][name]
        assert records[name]['workload_facts'] == public_workload_facts(score)
        facts = records[name]['workload_facts']
        assert (facts['appearances_last_7'], facts['pitches_last_7_days']) == (apps, pitches)
        # The frozen display differs from physical workload only by the starts.
        display = records[name]['bullpen_workload_display']
        assert (display['appearances_last_7'], display['pitches_last_7_days']) == (0, 0)
    assert FatigueScore.query.count() == len(giants_app['scores'])


def test_active_bullpen_and_recent_usage_agree(giants_app):
    client = giants_app['app'].test_client()
    core_arms, _core = _core_arms(client)
    full = client.get(f'/api/bullpen/teams/{SF}/board-v2').get_json()
    carrier = full['recent_usage_rest']
    assert carrier['appearance_policy'] == (
        public_team_relief_work.RECENT_USAGE_REST_APPEARANCE_POLICY
    )
    assert len(carrier['active_pitchers']) == len(full['active_bullpen']['arms'])
    for item in carrier['active_pitchers']:
        arm = next(arm for arm in full['active_bullpen']['arms']
                   if arm['pitcher_id'] == item['pitcher_id'])
        window = item['windows']['last_7_days']
        assert arm['workload']['appearances_last_7'] == window['appearances']['value']
        assert arm['workload']['pitches_last_7_days'] == window['pitches']['value']
        last = item['last_bullpen_appearance']
        assert (arm['last_appearance'] or {}).get('pitches') == last['value']
        # Core and full compositions serve the same frozen arm.
        assert arm == core_arms[arm['name']]


def test_incomplete_coverage_withholds_instead_of_total_workload(giants_app, monkeypatch):
    monkeypatch.setattr(
        slate_coverage, 'compute_slate_coverage',
        lambda day, *args, **kwargs: {
            'slate_date': day.isoformat(),
            'complete_enough_to_publish': False,
            'coverage_known': True,
            'reason_codes': ['final_games_not_fully_ingested'],
        },
    )
    reference_date = giants_app['reference_date']
    run = SyncRun(
        job_name='giants_bullpen_display_test', started_at=utc_now_naive(),
        completed_at=utc_now_naive(), status='success', stage='published',
        source='test', latest_game_date=reference_date - timedelta(days=1),
        latest_workload_date=reference_date - timedelta(days=1),
        latest_fatigue_calculated_at=utc_now_naive(),
    )
    db.session.add(run)
    db.session.flush()
    snapshot = dashboard_snapshot.build_bullpen_dashboard_snapshot(
        sync_run_id=run.id, source='giants_bullpen_display_test',
        publish=True, raise_errors=True,
    )
    board = public_serving_authority.build_published_team_board(
        SF, snapshot_override=snapshot,
    )
    arms = {arm['name']: arm for arm in team_board_v2._active_arms(board)}
    arm = arms['Cesar Perdomo']
    assert arm['workload']['appearances_last_7'] is None
    assert arm['workload']['pitches_last_7_days'] is None
    assert arm['last_appearance'] is None


def test_frozen_display_survives_later_game_log_changes(giants_app):
    snapshot = giants_app['snapshot']
    molina = giants_app['pitchers']['Anthony Molina']
    row = GameLog.query.filter_by(pitcher_id=molina.id, mlb_game_pk=823166).one()
    row.games_started = 0
    db.session.commit()
    arms, _body = _core_arms(giants_app['app'].test_client())
    assert arms['Anthony Molina']['workload']['appearances_last_7'] == 0
    assert snapshot.id == _body['publication_identity']['snapshot_id']
