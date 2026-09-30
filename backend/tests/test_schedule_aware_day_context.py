"""Schedule-aware baseball day context for bullpen rest semantics.

Production defect (2026-09-29, Chicago Cubs at San Diego Padres, data through
Sep 27, no games Sep 28): the matchup showed "Worked Yesterday: 2" for both
clubs. The availability reference date was always ``data_through + 1`` (Sep 28),
so Sep 27 appearances read as yesterday's work on Sep 29.

The canonical authority (``schedule_aware_availability_reference_date``) now
advances the reference date across schedule-confirmed no-game dates up to an
explicit as-of product day, and every rest fact (FatigueScore days since
appearance, availability inputs, D-055 Rest Status, Recent Usage & Rest)
derives from that one date. These tests pin the cases in the defect report,
synthetically, with no wall clock.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask

import services.sync as sync_service
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from services import availability_reference_date as reference_authority
from services import public_team_relief_work
from services import slate_coverage
from services import sync_metadata
from services import team_board_what_changed
from services.availability import (
    classify_availability,
    derive_workload_rest_inputs,
    entering_back_to_back,
)
from services.availability_reference_date import (
    schedule_aware_availability_reference_date,
    trusted_slate_reference_dates,
)
from services.bullpen_board import _board_workload_facts, build_rest_status
from services.fatigue import calculate_fatigue
from services.public_fatigue_view import public_workload_facts
from services.roster_status import STATUS_ACTIVE
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


SEP = {day: date(2026, 9, day) for day in range(20, 31)}
CHC, SD = 112, 135


def _row(day, state='final'):
    return SimpleNamespace(game_date=day, status_state=state)


def _resolve(coverage, as_of, rows):
    return schedule_aware_availability_reference_date(coverage, as_of, rows)


# ── The canonical reference date ─────────────────────────────────────────────

def test_case1_consecutive_games_reference_is_day_after_data():
    # Sep 27 and Sep 28 played, Sep 29 scheduled: data through Sep 28.
    rows = [_row(SEP[29], 'scheduled')]
    assert _resolve(SEP[28], SEP[29], rows) == SEP[29]


def test_case2_single_off_day_advances_reference_to_target_date():
    rows = [_row(SEP[29], 'scheduled'), _row(SEP[29], 'scheduled')]
    assert _resolve(SEP[27], SEP[29], rows) == SEP[29]


def test_case3_multiple_off_days_preserve_elapsed_recovery():
    rows = [_row(SEP[29], 'scheduled')]
    assert _resolve(SEP[25], SEP[29], rows) == SEP[29]


def test_case5_postponed_gap_game_is_not_workload_and_keeps_recovery():
    rows = [_row(SEP[28], 'postponed'), _row(SEP[29], 'scheduled')]
    assert _resolve(SEP[27], SEP[29], rows) == SEP[29]


def test_case6_rescheduled_game_uses_actual_played_date_and_status():
    # Postponed Sep 28, made up the same day and final but not yet ingested:
    # a played game sits in the gap, so no recovery day is claimed.
    rows = [_row(SEP[28], 'postponed'), _row(SEP[28], 'final'), _row(SEP[29], 'scheduled')]
    assert _resolve(SEP[27], SEP[29], rows) == SEP[28]
    # Rescheduled to a later date instead: Sep 28 is a real off-day.
    rows = [_row(SEP[28], 'postponed'), _row(SEP[30], 'scheduled')]
    assert _resolve(SEP[27], SEP[29], rows) == SEP[29]


def test_case8_data_lag_never_labels_older_usage_as_yesterday():
    # Data through Sep 26, but Sep 27 was played and is not ingested.
    rows = [_row(SEP[27], 'final'), _row(SEP[29], 'scheduled')]
    reference = _resolve(SEP[26], SEP[29], rows)
    assert reference == SEP[27]
    # The read keeps its own honest date; Sep 26 is "yesterday" only relative
    # to Sep 27, never relative to the Sep 29 target.
    assert reference != SEP[29]


def test_unconfirmed_schedule_fails_closed_to_day_after_data():
    # No schedule rows at all: an absent game is not proof of an off-day.
    assert _resolve(SEP[27], SEP[29], []) == SEP[28]
    # Rows stop at the gap: the window never proved Sep 28 was empty.
    assert _resolve(SEP[27], SEP[29], [_row(SEP[27])]) == SEP[28]


def test_case10_current_day_scheduled_or_live_game_does_not_move_rest():
    for state in ('scheduled', 'other', 'suspended', 'final'):
        rows = [_row(SEP[29], state)]
        assert _resolve(SEP[28], SEP[29], rows) == SEP[29]
        assert _resolve(SEP[27], SEP[29], rows) == SEP[29]
    # An unresolved game on a past gap date stops the advance.
    for state in ('scheduled', 'other', 'suspended'):
        rows = [_row(SEP[28], state), _row(SEP[29], 'scheduled')]
        assert _resolve(SEP[27], SEP[29], rows) == SEP[28]


def test_reference_never_moves_backward_or_past_as_of():
    rows = [_row(SEP[30], 'scheduled')]
    # A late postgame run before midnight: as-of earlier than the next day.
    assert _resolve(SEP[28], SEP[28], rows) == SEP[29]
    assert _resolve(SEP[27], None, rows) == SEP[28]
    assert _resolve(SEP[25], SEP[28], rows) == SEP[28]
    assert _resolve(None, SEP[29], rows) is None


def test_case7_historical_resolution_is_independent_of_wall_clock(monkeypatch):
    july = {day: date(2026, 7, day) for day in range(10, 20)}
    rows = [_row(july[15], 'scheduled')]
    monkeypatch.setattr(
        reference_authority, 'product_current_date', lambda *a, **k: SEP[29],
    )
    assert _resolve(july[13], july[15], [_row(july[14], 'postponed')] + rows) == july[15]
    assert _resolve(july[14], july[15], rows) == july[15]


def test_trusted_snapshot_reread_uses_the_published_reference_date():
    assert trusted_slate_reference_dates(SEP[27], SEP[29]) == (SEP[27], SEP[29])
    assert trusted_slate_reference_dates(SEP[27], None) == (SEP[27], SEP[28])
    # A published date that is not after the slate is ignored.
    assert trusted_slate_reference_dates(SEP[27], SEP[27]) == (SEP[27], SEP[28])
    assert trusted_slate_reference_dates('2026-09-27', '2026-09-29') == (SEP[27], SEP[29])


# ── Calendar rest semantics against the resolved date ───────────────────────

def _log(day, pitches=18, outs=3, game_pk=None):
    return GameLog(
        pitcher_id=1, mlb_game_pk=game_pk or int(day.strftime('%m%d')),
        game_date=day, pitches_thrown=pitches, innings_pitched_outs=outs,
        innings_pitched=outs / 3, game_type='R',
    )


def _score():
    return {'raw_score': 20.0, 'risk_level': 'LOW'}


def _inputs(logs, reference):
    return derive_workload_rest_inputs(_score(), logs, reference_date=reference)


def test_case2_and_11_previous_team_game_is_not_yesterday():
    # Worked the club's previous game (Sep 27); Sep 28 off; target Sep 29.
    schedule = [_row(SEP[27]), _row(SEP[29], 'scheduled')]
    reference = _resolve(SEP[27], SEP[29], schedule)
    logs = [_log(SEP[27], pitches=31)]
    inputs = _inputs(logs, reference)

    previous_team_game = max(r.game_date for r in schedule if r.status_state == 'final')
    worked_last_game = max(log.game_date for log in logs) == previous_team_game
    assert worked_last_game is True
    assert inputs['pitches_yesterday'] == 0          # worked_yesterday is False
    assert inputs['days_rest'] == 2                  # days since appearance
    assert inputs['back_to_back'] is False
    # One completed recovery day (Sep 28) before the Sep 29 game.
    assert inputs['days_rest'] - 1 == 1
    assert calculate_fatigue(SimpleNamespace(id=1), logs, reference).days_since_last_appearance == 2


def test_case1_consecutive_games_worked_yesterday():
    reference = _resolve(SEP[28], SEP[29], [_row(SEP[29], 'scheduled')])
    inputs = _inputs([_log(SEP[27]), _log(SEP[28], pitches=26)], reference)
    assert inputs['pitches_yesterday'] == 26
    assert inputs['days_rest'] == 1
    # The existing definition: appearances on consecutive calendar dates.
    assert inputs['back_to_back'] is True


def test_case12_back_to_back_is_calendar_not_consecutive_team_games():
    # Sep 25 and Sep 27 are the club's consecutive games around a Sep 26 off-day.
    inputs = _inputs([_log(SEP[25]), _log(SEP[27])], SEP[29])
    assert inputs['back_to_back'] is False
    # Sep 27 then the Sep 28 off-day: no back-to-back entering Sep 29.
    assert _inputs([_log(SEP[27])], SEP[29])['back_to_back'] is False


# ── Back-to-Back: entering the as-of date ───────────────────────────────────

def test_b2b_appeared_on_the_two_preceding_dates_is_back_to_back():
    inputs = _inputs([_log(SEP[27]), _log(SEP[28])], SEP[29])
    assert inputs['back_to_back'] is True
    assert entering_back_to_back({SEP[27], SEP[28]}, SEP[29]) is True


def test_b2b_does_not_survive_an_off_day():
    # Sep 26 + Sep 27, off Sep 28, target Sep 29: no longer back-to-back.
    reference = _resolve(SEP[27], SEP[29], [_row(SEP[29], 'scheduled')])
    inputs = _inputs([_log(SEP[26], pitches=28), _log(SEP[27], pitches=25)], reference)
    assert inputs['back_to_back'] is False
    assert inputs['pitches_yesterday'] == 0
    # The recent workload stays visible through rolling measures.
    assert inputs['consecutive_day_appearances_5d'] is True
    assert inputs['appearances_last_5_days'] == 2
    assert inputs['pitches_last_5_days'] == 53


def test_b2b_requires_both_preceding_dates():
    inputs = _inputs([_log(SEP[26]), _log(SEP[28])], SEP[29])
    assert inputs['back_to_back'] is False
    assert inputs['pitches_yesterday'] == 18


def test_b2b_doubleheader_on_one_date_is_not_back_to_back():
    dh = [_log(SEP[28], game_pk=1), _log(SEP[28], game_pk=2)]
    inputs = _inputs(dh, SEP[29])
    assert inputs['back_to_back'] is False
    assert inputs['consecutive_day_appearances_5d'] is False
    # A doubleheader yesterday plus the day before still is.
    assert _inputs(dh + [_log(SEP[27], game_pk=3)], SEP[29])['back_to_back'] is True


def test_b2b_historical_as_of_is_deterministic(monkeypatch):
    july = {day: date(2026, 7, day) for day in range(10, 20)}
    logs = [_log(july[13]), _log(july[14])]
    monkeypatch.setattr(
        reference_authority, 'product_current_date', lambda *a, **k: SEP[29],
    )
    assert _inputs(logs, july[15])['back_to_back'] is True
    assert _inputs(logs, july[16])['back_to_back'] is False


def test_classification_keeps_its_recent_consecutive_day_rule():
    # Status is unchanged by the label split: Sep 26 + 27 still weighs as
    # recent consecutive-day workload on Sep 29, without a Back-to-Back reason.
    result = classify_availability(
        _score(), [_log(SEP[26], pitches=12), _log(SEP[27], pitches=12)], reference_date=SEP[29],
    )
    assert result['availability_status'] == 'Limited'
    assert 'Back-to-back appearances' not in result['reasons']
    entering = classify_availability(
        _score(), [_log(SEP[27], pitches=12), _log(SEP[28], pitches=12)], reference_date=SEP[29],
    )
    assert 'Back-to-back appearances' in entering['reasons']


def test_case3_multiple_off_days_accumulate_rest():
    reference = _resolve(SEP[25], SEP[29], [_row(SEP[29], 'scheduled')])
    inputs = _inputs([_log(SEP[24]), _log(SEP[25], pitches=40)], reference)
    assert inputs['days_rest'] == 4
    assert inputs['pitches_yesterday'] == 0
    assert inputs['pitches_last_3_days'] == 0
    assert inputs['three_in_four'] is False


def test_case4_doubleheader_counts_appearances_not_extra_days():
    dh = [_log(SEP[28], pitches=12, game_pk=1), _log(SEP[28], pitches=14, game_pk=2)]
    inputs = _inputs(dh, SEP[29])
    assert inputs['days_rest'] == 1
    assert inputs['pitches_yesterday'] == 26
    assert inputs['appearances_last_3_days'] == 2
    assert inputs['back_to_back'] is False  # one calendar date
    # The same doubleheader followed by an off-day.
    reference = _resolve(SEP[27], SEP[29], [_row(SEP[29], 'scheduled')])
    dh = [_log(SEP[27], pitches=12, game_pk=1), _log(SEP[27], pitches=14, game_pk=2)]
    inputs = _inputs(dh, reference)
    assert inputs['days_rest'] == 2 and inputs['pitches_yesterday'] == 0


def test_case14_availability_reflects_off_day_recovery():
    # 34 pitches on Sep 27: "Limited" if that were yesterday.
    logs = [_log(SEP[27], pitches=34)]
    as_if_yesterday = classify_availability(_score(), logs, reference_date=SEP[28])
    after_off_day = classify_availability(_score(), logs, reference_date=SEP[29])
    assert as_if_yesterday['availability_status'] == 'Limited'
    assert '34 pitches yesterday' in as_if_yesterday['reasons']
    assert after_off_day['availability_status'] == 'Monitor'
    assert not any('yesterday' in reason for reason in after_off_day['reasons'])


def _card(days_since, back_to_back=False):
    return {
        'visibility': {'is_visible_by_default': True},
        'data_state': 'fresh',
        'workload_facts': {
            'days_since_last_appearance': days_since,
            'back_to_back': back_to_back,
        },
    }


def test_case9_mixed_schedules_differ_by_team():
    # League data through Sep 28 (Team A played); Team B was off Sep 28.
    reference = _resolve(SEP[28], SEP[29], [_row(SEP[29], 'scheduled')])
    team_a = [_inputs([_log(SEP[28])], reference), _inputs([_log(SEP[28])], reference)]
    team_b = [_inputs([_log(SEP[27])], reference), _inputs([_log(SEP[27])], reference)]
    rest_a = build_rest_status([_card(i['days_rest'], i['back_to_back']) for i in team_a])
    rest_b = build_rest_status([_card(i['days_rest'], i['back_to_back']) for i in team_b])
    assert rest_a['worked_yesterday_count'] == 2
    assert rest_b['worked_yesterday_count'] == 0
    assert rest_b['rested_arm_count'] == 2


# ── Recent Usage & Rest carrier across an off-day ────────────────────────────

def _coverage(through, days=10):
    return {
        (through - timedelta(days=offset)).isoformat(): {
            'complete_enough_to_publish': True, 'reason_codes': ['slate_complete'],
        }
        for offset in range(days)
    }


def _usage_row(pitcher, day, pitches=15, game_pk=1):
    return (
        SimpleNamespace(
            id=game_pk, pitcher_id=pitcher.id, mlb_game_pk=game_pk, game_date=day,
            games_started=0, pitches_thrown=pitches, innings_pitched_outs=3,
        ),
        pitcher,
    )


def _usage_carrier(rows, reference, pitchers):
    return public_team_relief_work.build_recent_usage_rest_carrier(
        rows,
        data_through=SEP[27],
        reference_date=reference,
        active_pitchers={p.id: {'name': p.full_name} for p in pitchers},
        coverage_by_date=_coverage(SEP[27]),
    )


def _usage_fixture():
    closer = SimpleNamespace(id=1, full_name='Closer')
    setup = SimpleNamespace(id=2, full_name='Setup')
    rows = [
        _usage_row(closer, SEP[25], game_pk=11),
        _usage_row(closer, SEP[26], game_pk=12),
        _usage_row(closer, SEP[27], game_pk=13),
        _usage_row(setup, SEP[27], pitches=28, game_pk=13),
    ]
    return rows, (closer, setup)


def test_recent_usage_rest_windows_are_calendar_relative_across_off_day():
    rows, pitchers = _usage_fixture()
    carrier = _usage_carrier(rows, SEP[29], pitchers)
    assert carrier['status'] == 'complete'
    assert carrier['data_through'] == '2026-09-27'
    assert carrier['reference_date'] == '2026-09-29'
    closer = {item['pitcher_id']: item for item in carrier['active_pitchers']}[1]
    assert closer['pitched_yesterday'] == {
        'value': False, 'status': 'complete', 'reason_codes': [],
    }
    assert closer['windows']['yesterday']['start_date'] == '2026-09-28'
    assert closer['windows']['yesterday']['appearances']['value'] == 0
    assert closer['windows']['last_3_days']['appearances']['value'] == 2
    assert closer['days_since_last_appearance']['value'] == 2
    assert closer['three_in_four']['value'] is False
    # Sep 26-27 before the Sep 28 off-day: not back-to-back entering Sep 29.
    assert closer['back_to_back']['value'] is False


def test_recent_usage_rest_consecutive_day_semantics_are_unchanged():
    rows, pitchers = _usage_fixture()
    carrier = _usage_carrier(rows, SEP[28], pitchers)
    closer = {item['pitcher_id']: item for item in carrier['active_pitchers']}[1]
    assert closer['pitched_yesterday']['value'] is True
    assert closer['windows']['yesterday']['through_date'] == '2026-09-27'
    assert closer['three_in_four']['value'] is True
    assert closer['back_to_back']['value'] is True  # Sep 26 and Sep 27
    assert closer['days_since_last_appearance']['value'] == 1


def test_case13_what_changed_across_off_day_manufactures_no_workload_change():
    rows, pitchers = _usage_fixture()
    before = {'recent_usage_rest': _usage_carrier(rows, SEP[28], pitchers)}
    after = {'recent_usage_rest': _usage_carrier(rows, SEP[29], pitchers)}
    events, domain = team_board_what_changed._workload_events(
        SimpleNamespace(id=1), SimpleNamespace(id=2), CHC, before, after,
    )
    assert events == []
    assert domain['status'] == 'complete'
    # Appearance totals never grow without a game.
    for item_before, item_after in zip(
        before['recent_usage_rest']['active_pitchers'],
        after['recent_usage_rest']['active_pitchers'],
    ):
        assert (
            item_after['windows']['last_7_days']['appearances']['value']
            <= item_before['windows']['last_7_days']['appearances']['value']
        )


# ── Production regression fixture (synthetic arms, observed schedule) ───────

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _pitcher(mlb_id, team_id, abbreviation):
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=f'{abbreviation} Reliever {mlb_id % 100}',
        team_id=team_id, team_name=abbreviation, team_abbreviation=abbreviation,
        position='RP', active=True, roster_status=STATUS_ACTIVE,
        roster_status_source='test_fixture',
        roster_status_updated_at=datetime(2026, 9, 27, 12, 0),
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _game_log(pitcher, day, game_pk, pitches):
    db.session.add(GameLog(
        pitcher_id=pitcher.id, mlb_game_pk=game_pk, game_date=day,
        pitches_thrown=pitches, innings_pitched=1.0, innings_pitched_outs=3,
        game_type='R',
    ))


def _schedule(team_id, opponent_id, game_pk, day, state):
    db.session.add(ScheduledGame(
        team_id=team_id, game_pk=game_pk, game_date=day,
        opponent_team_id=opponent_id, status_state=state,
    ))


def _seed_sep_29_matchup():
    """Cubs at Padres on Sep 29; both clubs last played Sep 27; no games Sep 28."""
    arms = {}
    for team_id, abbreviation, opponent in ((CHC, 'CHC', 158), (SD, 'SD', 119)):
        arms[team_id] = [_pitcher(team_id * 100 + index, team_id, abbreviation) for index in range(4)]
        base_pk = team_id * 1000
        # Three arms worked the Sep 27 finale: the arms once counted "yesterday".
        _game_log(arms[team_id][0], SEP[27], base_pk + 27, 24)
        _game_log(arms[team_id][1], SEP[27], base_pk + 27, 17)
        _game_log(arms[team_id][1], SEP[25], base_pk + 25, 15)
        _game_log(arms[team_id][2], SEP[26], base_pk + 26, 20)
        # Sep 26 + Sep 27, then the off-day: back-to-back entering Sep 28 only.
        _game_log(arms[team_id][2], SEP[27], base_pk + 27, 14)
        _game_log(arms[team_id][3], SEP[24], base_pk + 24, 30)
        for day in (24, 25, 26, 27):
            _schedule(team_id, opponent, base_pk + day, SEP[day], ScheduledGame.STATE_FINAL)
    _schedule(CHC, SD, 7_770_929, SEP[29], ScheduledGame.STATE_SCHEDULED)
    _schedule(SD, CHC, 7_770_929, SEP[29], ScheduledGame.STATE_SCHEDULED)
    db.session.add(SyncRun(
        job_name=sync_metadata.JOB_DAILY_SYNC, source='test', status='success',
        stage='published', started_at=datetime(2026, 9, 29, 12, 0),
        completed_at=datetime(2026, 9, 29, 12, 20),
    ))
    db.session.commit()
    return arms


def _team_rest(arms, reference):
    latest = {
        row.pitcher_id: row
        for row in FatigueScore.query.order_by(FatigueScore.calculated_at).all()
    }
    cards = []
    for pitcher in arms:
        score = latest[pitcher.id]
        logs = GameLog.query.filter_by(pitcher_id=pitcher.id).all()
        availability = classify_availability(score, logs, reference_date=reference)
        cards.append({
            'visibility': {'is_visible_by_default': True},
            'data_state': availability['data_state'],
            'workload_facts': _board_workload_facts(public_workload_facts(score), availability),
        })
    return build_rest_status(cards)


def _complete_coverage(day, *_args, **_kwargs):
    return {
        'slate_date': day.isoformat() if hasattr(day, 'isoformat') else day,
        'complete_enough_to_publish': True, 'coverage_known': True,
        'validations_passed': True, 'reason_codes': ['slate_complete'],
    }


def test_production_sep_29_cubs_at_padres_after_sep_28_off_day(app, monkeypatch):
    arms = _seed_sep_29_matchup()
    monkeypatch.setattr(slate_coverage, 'compute_slate_coverage', _complete_coverage)
    # The daily sync writes on Sep 29 (08:00 ET).
    monkeypatch.setattr(sync_service, 'utc_now_naive', lambda: datetime(2026, 9, 29, 12, 0))

    # Before: the old anchor (data_through + 1) described Sep 28.
    assert sync_metadata.canonical_fatigue_reference_date(as_of_date=SEP[28]) == SEP[28]

    assert sync_service.recalculate_all_fatigue() == 8
    status = sync_metadata.build_sync_status_payload()
    assert status['data']['latest_game_date'] == '2026-09-27'
    assert status['freshness']['availability_reference_date'] == '2026-09-29'
    reference = SEP[29]

    for team_id in (CHC, SD):
        rest = _team_rest(arms[team_id], reference)
        assert rest['available'] is True
        assert rest['worked_yesterday_count'] == 0
        assert rest['back_to_back_count'] == 0
        assert rest['rested_arm_count'] == 4
        # Sep 27 usage is previous-game usage two calendar days back.
        assert FatigueScore.query.filter_by(
            pitcher_id=arms[team_id][0].id,
        ).one().days_since_last_appearance == 2


def test_production_fixture_before_fix_counted_previous_game_as_yesterday(app, monkeypatch):
    arms = _seed_sep_29_matchup()
    # The pre-fix behaviour, reproduced by pinning the old anchor explicitly.
    old_reference = SEP[28]
    assert sync_service.recalculate_all_fatigue(reference_date=old_reference) == 8
    for team_id in (CHC, SD):
        rest = _team_rest(arms[team_id], old_reference)
        assert rest['worked_yesterday_count'] == 3
        # Entering Sep 28 off Sep 26 + Sep 27 really was back-to-back.
        assert rest['back_to_back_count'] == 1


def test_read_path_as_of_is_the_fatigue_write_day_not_the_wall_clock(app, monkeypatch):
    _seed_sep_29_matchup()
    monkeypatch.setattr(slate_coverage, 'compute_slate_coverage', _complete_coverage)
    monkeypatch.setattr(sync_service, 'utc_now_naive', lambda: datetime(2026, 9, 29, 12, 0))
    sync_service.recalculate_all_fatigue()
    # Reading much later (another season) resolves the same day.
    monkeypatch.setattr(
        sync_metadata, 'product_current_date', lambda *a, **k: date(2027, 5, 1),
    )
    status = sync_metadata.build_sync_status_payload()
    assert status['freshness']['availability_reference_date'] == '2026-09-29'


def test_scores_written_before_the_off_day_elapsed_keep_their_own_date(app, monkeypatch):
    _seed_sep_29_matchup()
    monkeypatch.setattr(slate_coverage, 'compute_slate_coverage', _complete_coverage)
    # Last recalculation ran on Sep 28 (the off-day itself): its scores say
    # Sep 28, so reads keep Sep 28 until the Sep 29 recalculation.
    monkeypatch.setattr(sync_service, 'utc_now_naive', lambda: datetime(2026, 9, 28, 12, 0))
    sync_service.recalculate_all_fatigue()
    status = sync_metadata.build_sync_status_payload()
    assert status['freshness']['availability_reference_date'] == '2026-09-28'


def test_case9_mixed_schedules_in_database(app, monkeypatch):
    arms = _seed_sep_29_matchup()
    # Another club played on Sep 28 (league data through Sep 28).
    played = [_pitcher(14_700 + index, 147, 'NYY') for index in range(2)]
    for pitcher in played:
        _game_log(pitcher, SEP[28], 147_028, 19)
    _schedule(147, 111, 147_028, SEP[28], ScheduledGame.STATE_FINAL)
    db.session.commit()
    monkeypatch.setattr(sync_service, 'utc_now_naive', lambda: datetime(2026, 9, 29, 12, 0))
    sync_service.recalculate_all_fatigue()

    assert _team_rest(played, SEP[29])['worked_yesterday_count'] == 2
    assert _team_rest(arms[CHC], SEP[29])['worked_yesterday_count'] == 0
    assert _team_rest(arms[SD], SEP[29])['worked_yesterday_count'] == 0
