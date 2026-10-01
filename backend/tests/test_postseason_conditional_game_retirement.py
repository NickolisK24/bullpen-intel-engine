"""Postseason "if necessary" games retire when MLB's schedule stops listing them.

Production, Oct 1, 2026: BaseballOS presented four Wild Card Game 3s after
three series had ended 2-0. The Daily slate schedule refresh logs show MLB
dropped those games from ``/schedule`` rather than returning them Cancelled.
The Sep 29 refresh (Sep 28..Oct 2) saw 12 games and the Sep 30 refresh
(Sep 29..Oct 3) saw 16, so Oct 1 had all four Game 3s listed. The Oct 1
refresh (Sep 30..Oct 4) saw 11, which only fits one Oct 1 game still being
listed, and a returned game counts in ``games_seen`` whatever its status.
Schedule ingestion only upserts returned games, so the three vanished Game 3s
stayed ``scheduled`` in both schedule tables.

These tests replay that topology generically (no team or series outcome is
encoded) through the real ingestion writer, the real ``/schedule`` response
shape, and every reader the incident touched.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from models.scheduled_game import ScheduledGame
from models.slate_game import SlateGame
from services import ledger_confirmed_rest, schedule_absence, schedule_ingestion, slate_coverage
from services.schedule_absence import SCHEDULE_RETIRED_STATUS_CODE
from services.mlb_api import MLBApiClient, ScheduleGames, schedule_response_shape
from services.schedule_context import build_team_schedule_context
from services.trusted_compare_authority import build_scheduled_game_matchup_payload
from services.tonight_read_model import build_tonight_v1
from services.tonight_v1_serving import overlay_game_state
from tests.test_schedule_ingestion import (  # noqa: F401  (fenced PostgreSQL fixtures)
    _adopt_like_sync_pipeline,
    fenced_app,
    fenced_database_url,
)
from tests.test_slate_coverage import _marker, app  # noqa: F401
from utils.db import db


SLATE = date(2026, 10, 1)
T0 = datetime(2026, 10, 1, 10, 30)
LATER = T0 + timedelta(minutes=schedule_absence.ABSENCE_CONFIRMATION_MINUTES + 1)
SCHEDULED = ('S', 'Scheduled', 'Preview')
FINAL = ('F', 'Final', 'Final')
CANCELLED = ('C', 'Cancelled', 'Final')
POSTPONED = ('DR', 'Postponed', 'Preview')

# Four best-of-3 series; their Game 3s share one date. Generic gamePks and
# clubs: which series ended is a fact the source supplies, never this code.
WILD_CARD_GAME_3S = (
    (990301, 135, 112),
    (990302, 144, 143),
    (990303, 117, 145),
    (990304, 147, 111),
)


def _mlb_game(game_pk, home, away, *, on=SLATE, status=SCHEDULED, game_type='F',
              series_game=3, games_in_series=3, if_necessary=None, hour=20,
              game_number=1, doubleheader='N'):
    code, detailed, abstract = status
    game = {
        'gamePk': game_pk,
        'gameType': game_type,
        'officialDate': on.isoformat(),
        'gameDate': f'{on.isoformat()}T{hour:02d}:08:00Z',
        'doubleHeader': doubleheader,
        'gameNumber': game_number,
        'seriesGameNumber': series_game,
        'gamesInSeries': games_in_series,
        'status': {'statusCode': code, 'detailedState': detailed, 'abstractGameState': abstract},
        'teams': {'home': {'team': {'id': home}}, 'away': {'team': {'id': away}}},
    }
    if if_necessary is not None:
        game['ifNecessary'] = if_necessary
    return game


def _response(start, end, games, *, team_id=None, data=None):
    """``games`` exactly as ``MLBApiClient.get_schedule`` returns them."""
    if data is None:
        by_date = {}
        for game in games:
            by_date.setdefault(game['officialDate'], []).append(game)
        data = {
            'totalGames': len(games),
            'dates': [
                {'date': day, 'totalGames': len(listed), 'games': listed}
                for day, listed in sorted(by_date.items())
            ],
        }
    result = ScheduleGames()
    for entry in data.get('dates') or []:
        result.extend(entry.get('games') or [])
    result.response_shape = schedule_response_shape(
        data, start_date=start.isoformat(), end_date=end.isoformat(), team_id=team_id,
    )
    return result


def _window(games, *, start=SLATE - timedelta(days=1), end=SLATE + timedelta(days=3)):
    return _response(start, end, games)


def _ingest(response, *, now):
    original = schedule_ingestion.utc_now_naive
    schedule_ingestion.utc_now_naive = lambda: now
    try:
        return schedule_ingestion.ingest_games(response, source='daily_slate_schedule')
    finally:
        schedule_ingestion.utc_now_naive = original


def _all_game_3s():
    return [_mlb_game(pk, home, away) for pk, home, away in WILD_CARD_GAME_3S]


def _states(game_pk):
    rows = ScheduledGame.query.filter_by(game_pk=game_pk).all()
    slate = db.session.get(SlateGame, game_pk)
    return (
        sorted({(row.status_state, row.status_code) for row in rows}),
        (slate.normalized_state, slate.status_code) if slate else None,
    )


RETIRED = ([('other', SCHEDULE_RETIRED_STATUS_CODE)], ('cancelled', SCHEDULE_RETIRED_STATUS_CODE))
STILL_SCHEDULED = ([('scheduled', 'S')], ('upcoming', 'S'))


def _seed_and_drop(games, dropped_pks, *, start=None, end=None, extra=()):
    """Run 1 lists every game; runs 2 and 3 omit ``dropped_pks``."""
    kwargs = {}
    if start is not None:
        kwargs['start'] = start
    if end is not None:
        kwargs['end'] = end
    _ingest(_window(list(games) + list(extra), **kwargs), now=T0 - timedelta(hours=12))
    remaining = [g for g in games if g['gamePk'] not in dropped_pks] + list(extra)
    first = _ingest(_window(remaining, **kwargs), now=T0)
    second = _ingest(_window(remaining, **kwargs), now=LATER)
    return first, second


# ── 11 / 12. The Oct 1 topology ──────────────────────────────────────────────

def test_production_topology_three_unneeded_game_3s_retire_one_remains(app):
    with app.app_context():
        kept = WILD_CARD_GAME_3S[1][0]
        dropped = {pk for pk, _h, _a in WILD_CARD_GAME_3S if pk != kept}
        # BEFORE: all four stored as scheduled.
        _ingest(_window(_all_game_3s()), now=T0 - timedelta(hours=12))
        assert all(_states(pk) == STILL_SCHEDULED for pk, _h, _a in WILD_CARD_GAME_3S)

        remaining = [g for g in _all_game_3s() if g['gamePk'] == kept]
        first = _ingest(_window(remaining), now=T0)
        # One response is never enough: the absence is only observed.
        assert first['games_retired'] == 0
        assert first['absence_reconciliation']['status'] == 'reconciled'
        assert {g['action'] for g in first['absence_reconciliation']['absent_games']} == {
            'absence_observed'}
        assert all(_states(pk) == STILL_SCHEDULED for pk in dropped)

        second = _ingest(_window(remaining), now=LATER)
        db.session.commit()
        assert second['games_retired'] == 3
        assert sorted(second['game_pks_retired']) == sorted(dropped)
        assert second['absence_reconciliation']['retirement_reason'] == (
            'postseason_conditional_game_removed_from_schedule')
        for pk in dropped:
            assert _states(pk) == RETIRED
        assert _states(kept) == STILL_SCHEDULED

        # AFTER: tonight's slate holds exactly the legitimate game.
        payload = build_tonight_v1(
            _snapshot(), SlateGame.query.filter_by(game_date_et=SLATE).all(),
            generated_at=LATER,
        )
        assert [game['game_pk'] for game in payload['games']] == [kept]
        assert payload['summary']['game_count'] == 1


def test_mlb_client_records_the_response_shape(monkeypatch):
    data = {'totalGames': 1, 'dates': [{'date': '2026-10-01', 'totalGames': 1,
                                        'games': [_mlb_game(990301, 135, 112)]}]}
    client = MLBApiClient()
    monkeypatch.setattr(client, '_get', lambda endpoint, params=None: data)
    games = client.get_schedule(start_date='2026-09-30', end_date='2026-10-04')
    assert list(games) == data['dates'][0]['games']
    assert schedule_absence.response_integrity(games)['consistent'] is True
    assert games.response_shape['requested_start'] == '2026-09-30'


# ── 1. Still listed ──────────────────────────────────────────────────────────

def test_a_conditional_game_mlb_still_lists_stays_scheduled(app):
    with app.app_context():
        first, second = _seed_and_drop(_all_game_3s(), set())
        assert second['absence_reconciliation']['status'] == 'nothing_absent'
        assert all(_states(pk) == STILL_SCHEDULED for pk, _h, _a in WILD_CARD_GAME_3S)


# ── 2, 13, 14, 15. Every postseason round ────────────────────────────────────

@pytest.mark.parametrize('game_type, games_in_series, series_game', [
    ('F', 3, 3),                         # Wild Card Game 3
    ('D', 5, 4), ('D', 5, 5),            # Division Series Games 4-5
    ('L', 7, 5), ('L', 7, 6), ('L', 7, 7),   # Championship Series Games 5-7
    ('W', 7, 5), ('W', 7, 6), ('W', 7, 7),   # World Series Games 5-7
])
def test_an_unneeded_game_of_every_round_retires(app, game_type, games_in_series, series_game):
    with app.app_context():
        game = _mlb_game(991000 + series_game, 147, 141, game_type=game_type,
                         games_in_series=games_in_series, series_game=series_game)
        _, second = _seed_and_drop([game], {game['gamePk']})
        assert second['game_pks_retired'] == [game['gamePk']]
        assert _states(game['gamePk']) == RETIRED


@pytest.mark.parametrize('game_type, games_in_series, series_game', [
    ('F', 3, 2), ('D', 5, 3), ('L', 7, 4), ('W', 7, 1),
])
def test_a_game_every_series_plays_is_never_retired(app, game_type, games_in_series, series_game):
    with app.app_context():
        game = _mlb_game(992000 + series_game, 147, 141, game_type=game_type,
                         games_in_series=games_in_series, series_game=series_game)
        _, second = _seed_and_drop([game], {game['gamePk']})
        assert second['games_retired'] == 0
        assert second['absence_reconciliation']['status'] == 'fail_closed_unexplained_absence'
        assert _states(game['gamePk']) == STILL_SCHEDULED


def test_mlb_if_necessary_flag_decides_when_present(app):
    with app.app_context():
        flagged = _mlb_game(993001, 147, 141, game_type='L', games_in_series=7,
                            series_game=5, if_necessary='Y')
        _, second = _seed_and_drop([flagged], {993001})
        assert _states(993001) == RETIRED
        assert second['absence_reconciliation']['absent_games'][0]['basis'] == (
            'mlb_if_necessary_flag')

    with app.app_context():
        not_flagged = _mlb_game(993002, 147, 141, game_type='L', games_in_series=7,
                                series_game=5, if_necessary='N')
        _, second = _seed_and_drop([not_flagged], {993002})
        assert second['games_retired'] == 0
        assert _states(993002) == STILL_SCHEDULED


# ── 3, 39. A failed fetch changes nothing ────────────────────────────────────

def test_failed_fetch_never_retires_or_reverses(app, monkeypatch):
    with app.app_context():
        game = _mlb_game(990301, 135, 112)
        _seed_and_drop([game, _mlb_game(990302, 144, 143)], {990301})
        assert _states(990301) == RETIRED

        def failing(**_kwargs):
            raise RuntimeError('MLB API fetch failed for /schedule: status 503')

        monkeypatch.setattr(schedule_ingestion.mlb_client, 'get_schedule', failing)
        with pytest.raises(RuntimeError):
            schedule_ingestion.ingest_schedule(SLATE, SLATE + timedelta(days=3))
        db.session.rollback()
        assert _states(990301) == RETIRED
        assert _states(990302) == STILL_SCHEDULED


# ── 4, 27. Structurally unsound or suspect responses ────────────────────────

def _absence_status(response, *, now):
    summary = _ingest(response, now=now)
    return summary['absence_reconciliation']


@pytest.mark.parametrize('mutate, reason', [
    (lambda d: d['dates'][0].update(totalGames=9), 'date_entry_count_mismatch'),
    (lambda d: d.update(totalGames=7), 'total_games_mismatch'),
    (lambda d: d.pop('totalGames'), 'total_games_undeclared'),
    (lambda d: d['dates'].append(dict(d['dates'][0])), 'duplicate_date_entry'),
    (lambda d: d['dates'][0].update(date='2026-12-25'), 'date_entry_outside_range'),
])
def test_an_unsound_response_reconciles_nothing(app, mutate, reason):
    with app.app_context():
        _ingest(_window(_all_game_3s()), now=T0 - timedelta(hours=12))
        kept = [_mlb_game(990302, 144, 143)]
        for now in (T0, LATER):
            data = {'totalGames': 1, 'dates': [
                {'date': SLATE.isoformat(), 'totalGames': 1, 'games': list(kept)}]}
            mutate(data)
            response = _response(SLATE - timedelta(days=1), SLATE + timedelta(days=3),
                                 [], data=data)
            status = _absence_status(response, now=now)
            assert status['status'] == 'not_evaluated'
            assert status['response_integrity_reason'] == reason
        assert _states(990301) == STILL_SCHEDULED


def test_a_plain_list_or_team_scoped_fetch_proves_nothing(app):
    with app.app_context():
        _ingest(_window(_all_game_3s()), now=T0 - timedelta(hours=12))
        listed = [_mlb_game(990302, 144, 143)]
        for now in (T0, LATER):
            assert _absence_status(listed, now=now)['response_integrity_reason'] == (
                'no_response_shape')
        team_scoped = _response(SLATE, SLATE + timedelta(days=3), listed, team_id=144)
        assert _absence_status(team_scoped, now=LATER)['response_integrity_reason'] == (
            'team_scoped_fetch')
        assert _states(990301) == STILL_SCHEDULED


def test_a_consistent_but_partial_response_is_caught_by_any_other_missing_game(app):
    # A truncated response whose own counts still add up. It drops a Game 1
    # (always played) as well as a Game 3: the missing Game 1 cannot be
    # explained, so the whole response is suspect and nothing is retired.
    with app.app_context():
        game_1 = _mlb_game(994001, 119, 121, on=SLATE + timedelta(days=2),
                           game_type='D', games_in_series=5, series_game=1)
        game_3 = _mlb_game(990301, 135, 112)
        _, second = _seed_and_drop([game_1, game_3], {994001, 990301})
        assert second['absence_reconciliation']['status'] == 'fail_closed_unexplained_absence'
        assert second['games_retired'] == 0
        assert _states(990301) == STILL_SCHEDULED
        assert _states(994001) == STILL_SCHEDULED


def test_one_partial_response_alone_only_observes(app):
    # Undetectable by inspection (it omits only conditional games); the
    # second-observation rule is what stops a one-off partial response.
    with app.app_context():
        _ingest(_window(_all_game_3s()), now=T0 - timedelta(hours=12))
        partial = _ingest(_window([_mlb_game(990302, 144, 143)]), now=T0)
        assert partial['games_retired'] == 0
        _ingest(_window(_all_game_3s()), now=LATER)   # MLB lists them again
        assert all(_states(pk) == STILL_SCHEDULED for pk, _h, _a in WILD_CARD_GAME_3S)
        assert {row.schedule_absent_since for row in ScheduledGame.query.all()} == {None}


def test_confirmation_must_come_from_a_later_response(app):
    with app.app_context():
        _ingest(_window(_all_game_3s()), now=T0 - timedelta(hours=12))
        remaining = [_mlb_game(990302, 144, 143)]
        _ingest(_window(remaining), now=T0)
        too_soon = _ingest(_window(remaining), now=T0 + timedelta(minutes=1))
        assert too_soon['games_retired'] == 0
        assert {g['action'] for g in too_soon['absence_reconciliation']['absent_games']} == {
            'awaiting_confirmation'}


# ── 5. An empty response ─────────────────────────────────────────────────────

def test_an_empty_response_retires_only_conditional_games(app):
    with app.app_context():
        game = _mlb_game(990301, 135, 112)
        _seed_and_drop([game], {990301})
        assert _states(990301) == RETIRED

    with app.app_context():
        regular = _mlb_game(995001, 116, 118, game_type='R', series_game=2, games_in_series=3)
        _, second = _seed_and_drop([regular], {995001})
        assert second['absence_reconciliation']['status'] == 'fail_closed_unexplained_absence'
        assert _states(995001) == STILL_SCHEDULED


# ── 6, 34. Regular season: reported, preserved, never retired ───────────────

def test_a_vanished_regular_season_game_is_reported_and_kept(app):
    with app.app_context():
        regular = _mlb_game(995002, 116, 118, game_type='R', series_game=3, games_in_series=3)
        _, second = _seed_and_drop([regular], {995002})
        absent = second['absence_reconciliation']['absent_games']
        assert absent == [{'game_pk': 995002, 'game_date': SLATE.isoformat(),
                           'action': 'not_postseason_conditional',
                           'basis': 'not_postseason', 'unexplained': True}]
        assert _states(995002) == STILL_SCHEDULED
        assert ScheduledGame.query.filter_by(game_pk=995002).first().schedule_absent_since is None


def test_an_unexplained_absence_blocks_every_retirement_in_the_response(app):
    with app.app_context():
        regular = _mlb_game(995003, 116, 118, game_type='R', series_game=1, games_in_series=3)
        conditional = _mlb_game(990301, 135, 112)
        _, second = _seed_and_drop([regular, conditional], {995003, 990301})
        assert second['absence_reconciliation']['status'] == 'fail_closed_unexplained_absence'
        assert second['games_retired'] == 0
        assert _states(990301) == STILL_SCHEDULED


# ── 7, 30. An explicit MLB cancellation keeps MLB's own status ──────────────

def test_an_explicit_cancellation_is_stored_as_mlb_sent_it(app):
    with app.app_context():
        game = _mlb_game(990301, 135, 112)
        _ingest(_window([game]), now=T0)
        cancelled = _mlb_game(990301, 135, 112, status=CANCELLED)
        summary = _ingest(_window([cancelled]), now=LATER)
        assert summary['games_retired'] == 0
        assert _states(990301) == ([('other', 'C')], ('cancelled', 'C'))
        payload = build_tonight_v1(
            _snapshot(), SlateGame.query.filter_by(game_date_et=SLATE).all(), generated_at=LATER,
        )
        assert payload['games'] == []
        matchup = build_scheduled_game_matchup_payload(db.session.get(SlateGame, 990301), None)
        assert (matchup['status'], matchup['reason_code']) == (
            'not_upcoming', 'scheduled_game_cancelled')


# ── 8, 9. Postponed and suspended games ──────────────────────────────────────

def test_a_postponed_game_mlb_still_lists_is_not_retired(app):
    with app.app_context():
        game = _mlb_game(990301, 135, 112)
        postponed = _mlb_game(990301, 135, 112, status=POSTPONED)
        _ingest(_window([game]), now=T0)
        summary = _ingest(_window([postponed]), now=LATER)
        assert summary['games_retired'] == 0
        assert _states(990301) == ([('postponed', 'DR')], ('cancelled', 'DR'))
        payload = build_tonight_v1(
            _snapshot(), SlateGame.query.filter_by(game_date_et=SLATE).all(), generated_at=LATER,
        )
        assert [(g['game_pk'], g['state']) for g in payload['games']] == [(990301, 'postponed')]


def test_a_suspended_game_that_vanishes_fails_closed(app):
    with app.app_context():
        suspended = _mlb_game(990301, 135, 112, status=('U', 'Suspended', 'Live'))
        _, second = _seed_and_drop([suspended], {990301})
        assert second['absence_reconciliation']['status'] == 'fail_closed_unexplained_absence'
        assert second['absence_reconciliation']['absent_games'][0]['action'] == (
            'stored_state_not_scheduled')


# ── 10. Doubleheaders ────────────────────────────────────────────────────────

def test_one_game_vanishing_never_touches_its_doubleheader_partner(app):
    with app.app_context():
        game_1 = _mlb_game(995011, 116, 118, game_type='R', doubleheader='S', game_number=1,
                           series_game=1)
        game_2 = _mlb_game(995012, 116, 118, game_type='R', doubleheader='S', game_number=2,
                           series_game=2, hour=23)
        _, second = _seed_and_drop([game_1, game_2], {995012})
        assert second['games_retired'] == 0
        assert _states(995011) == STILL_SCHEDULED
        assert _states(995012) == STILL_SCHEDULED


def test_two_same_day_conditional_games_retire_independently_of_a_listed_one(app):
    with app.app_context():
        _, second = _seed_and_drop(_all_game_3s(), {990301})
        assert second['game_pks_retired'] == [990301]
        assert all(_states(pk) == STILL_SCHEDULED for pk in (990302, 990303, 990304))


# ── 11. #897 participant settlement in the same response ────────────────────

def test_participant_settlement_and_retirement_in_one_response(app):
    with app.app_context():
        placeholder = _mlb_game(996001, 4619, 4945, on=SLATE + timedelta(days=2),
                                game_type='D', games_in_series=5, series_game=1)
        _ingest(_window([placeholder] + _all_game_3s()), now=T0 - timedelta(hours=12))
        settled = _mlb_game(996001, 135, 112, on=SLATE + timedelta(days=2),
                            game_type='D', games_in_series=5, series_game=1)
        remaining = [settled] + [g for g in _all_game_3s() if g['gamePk'] != 990301]
        _ingest(_window(remaining), now=T0)
        second = _ingest(_window(remaining), now=LATER)
        assert second['game_pks_retired'] == [990301]
        assert {row.team_id for row in ScheduledGame.query.filter_by(game_pk=996001)} == {135, 112}


# ── 16, 31, 32. Restoration ──────────────────────────────────────────────────

@pytest.mark.parametrize('status, expected', [
    (SCHEDULED, STILL_SCHEDULED),
    (FINAL, ([('final', 'F')], ('completed', 'F'))),
])
def test_a_retired_game_mlb_lists_again_is_restored(app, status, expected):
    with app.app_context():
        _seed_and_drop(_all_game_3s(), {990301})
        assert _states(990301) == RETIRED
        relisted = _all_game_3s()
        relisted[0] = _mlb_game(990301, 135, 112, status=status)
        summary = _ingest(_window(relisted), now=LATER + timedelta(hours=1))
        assert summary['game_pks_restored'] == [990301]
        assert _states(990301) == expected
        assert {row.schedule_absent_since for row in
                ScheduledGame.query.filter_by(game_pk=990301)} == {None}
        assert {row.source for row in ScheduledGame.query.filter_by(game_pk=990301)} == {
            'daily_slate_schedule'}


# ── 26. Moved, not removed ───────────────────────────────────────────────────

def test_a_game_listed_under_another_date_is_moved_not_retired(app):
    with app.app_context():
        game = _mlb_game(990301, 135, 112)
        moved = _mlb_game(990301, 135, 112, on=SLATE + timedelta(days=1))
        _ingest(_window([game]), now=T0 - timedelta(hours=12))
        for now in (T0, LATER):
            summary = _ingest(_window([moved]), now=now)
            assert summary['absence_reconciliation']['status'] == 'nothing_absent'
        rows = ScheduledGame.query.filter_by(game_pk=990301).all()
        assert {row.game_date for row in rows} == {SLATE + timedelta(days=1)}
        assert _states(990301) == STILL_SCHEDULED


def test_a_window_ending_near_the_game_date_waits(app):
    with app.app_context():
        _, second = _seed_and_drop(_all_game_3s(), {990301},
                                   start=SLATE - timedelta(days=1), end=SLATE)
        assert second['games_retired'] == 0
        assert {g['action'] for g in second['absence_reconciliation']['absent_games']} == {
            'awaiting_reschedule_guard'}


# ── 28. Outside the requested window ─────────────────────────────────────────

def test_a_game_outside_the_requested_window_is_untouched(app):
    with app.app_context():
        far = _mlb_game(997001, 147, 141, on=SLATE + timedelta(days=10),
                        game_type='L', games_in_series=7, series_game=7)
        _ingest(_response(SLATE, SLATE + timedelta(days=12), [far]), now=T0 - timedelta(hours=12))
        for now in (T0, LATER):
            summary = _ingest(_window([]), now=now)
            assert summary['absence_reconciliation']['status'] == 'nothing_absent'
        assert _states(997001) == STILL_SCHEDULED


# ── 29. Unreliable series metadata ───────────────────────────────────────────

@pytest.mark.parametrize('games_in_series, series_game', [
    (None, 3), (3, None), (4, 4), (3, 4), (9, 9),
])
def test_unreliable_series_metadata_fails_closed(app, games_in_series, series_game):
    with app.app_context():
        game = _mlb_game(998001, 147, 141, games_in_series=games_in_series,
                         series_game=series_game)
        _, second = _seed_and_drop([game], {998001})
        assert second['games_retired'] == 0
        assert second['absence_reconciliation']['absent_games'][0]['basis'] == (
            'series_metadata_unreliable')


# ── 33, 38. Several at once; reruns are idempotent ──────────────────────────

def test_several_conditional_games_retire_together_and_reruns_change_nothing(app):
    with app.app_context():
        dropped = {990301, 990303, 990304}
        _, second = _seed_and_drop(_all_game_3s(), dropped)
        assert sorted(second['game_pks_retired']) == sorted(dropped)
        snapshot = {
            (row.game_pk, row.team_id): (row.status_state, row.status_code, row.source,
                                         row.schedule_absent_since)
            for row in ScheduledGame.query.all()
        }
        remaining = [g for g in _all_game_3s() if g['gamePk'] not in dropped]
        rerun = _ingest(_window(remaining), now=LATER + timedelta(hours=2))
        assert rerun['games_retired'] == 0
        assert rerun['absence_reconciliation']['status'] == 'nothing_absent'
        assert {
            (row.game_pk, row.team_id): (row.status_state, row.status_code, row.source,
                                         row.schedule_absent_since)
            for row in ScheduledGame.query.all()
        } == snapshot


def test_ingest_errors_block_retirement(app, monkeypatch):
    with app.app_context():
        _ingest(_window(_all_game_3s()), now=T0 - timedelta(hours=12))
        remaining = [g for g in _all_game_3s() if g['gamePk'] != 990301]
        _ingest(_window(remaining), now=T0)
        real = schedule_ingestion._upsert_row

        def flaky(team_id, *args, **kwargs):
            if team_id == 144:
                raise RuntimeError('write failed')
            return real(team_id, *args, **kwargs)

        monkeypatch.setattr(schedule_ingestion, '_upsert_row', flaky)
        summary = _ingest(_window(remaining), now=LATER)
        assert summary['errors'] == 1
        assert summary['absence_reconciliation']['status'] == 'fail_closed_ingest_errors'
        assert _states(990301) == STILL_SCHEDULED


# ── Multi-table atomicity ────────────────────────────────────────────────────

def test_a_failure_while_retiring_leaves_both_tables_unchanged(app, monkeypatch):
    with app.app_context():
        _ingest(_window(_all_game_3s()), now=T0 - timedelta(hours=12))
        remaining = [g for g in _all_game_3s() if g['gamePk'] != 990301]
        _ingest(_window(remaining), now=T0)

        real_apply = schedule_absence.apply_plan

        def crash_between_tables(plan, *, now):
            for row in ScheduledGame.query.filter_by(game_pk=990301).all():
                row.status_code = SCHEDULE_RETIRED_STATUS_CODE
            db.session.flush()
            raise RuntimeError('crash before slate_games was written')

        monkeypatch.setattr(schedule_absence, 'apply_plan', crash_between_tables)
        with pytest.raises(RuntimeError):
            _ingest(_window(remaining), now=LATER)
        db.session.rollback()
        assert _states(990301) == STILL_SCHEDULED
        monkeypatch.setattr(schedule_absence, 'apply_plan', real_apply)
        _ingest(_window(remaining), now=LATER)
        assert _states(990301) == RETIRED


def test_retirement_lands_through_the_schedule_ownership_fence(fenced_app):  # noqa: F811
    _ingest(_window(_all_game_3s()), now=T0 - timedelta(hours=12))
    db.session.commit()
    _adopt_like_sync_pipeline([pk for pk, _h, _a in WILD_CARD_GAME_3S])
    remaining = [g for g in _all_game_3s() if g['gamePk'] != 990301]
    _ingest(_window(remaining), now=T0)
    second = _ingest(_window(remaining), now=LATER)
    db.session.remove()
    assert second['game_pks_retired'] == [990301]
    assert second['rows_suppressed'] == 0
    assert _states(990301) == RETIRED


# ── 17, 19, 20, #900. Readers ────────────────────────────────────────────────

def _snapshot():
    return SimpleNamespace(
        id=4157, sync_run_id=93231, payload={},
        availability_reference_date=SLATE, data_through=SLATE - timedelta(days=1),
    )


def test_slate_coverage_does_not_wait_for_a_retired_game(app):
    with app.app_context():
        final = _mlb_game(990302, 144, 143, status=FINAL)
        _ingest(_window(_all_game_3s()), now=T0 - timedelta(hours=12))
        remaining = [final]
        for pk in (990303, 990304):
            remaining.append(_mlb_game(pk, *dict((p, (h, a)) for p, h, a in WILD_CARD_GAME_3S)[pk],
                                       status=FINAL))
        _ingest(_window(remaining), now=T0)
        _ingest(_window(remaining), now=LATER)
        for pk in (990302, 990303, 990304):
            _marker(pk, SLATE)
        db.session.commit()
        coverage = slate_coverage.compute_slate_coverage(SLATE, sync_status='success',
                                                         publication_critical_complete=True)
        assert coverage['complete_enough_to_publish'] is True
        assert coverage['games_incomplete'] == 0
        assert coverage['games_cancelled'] == 1
        assert coverage['games_final'] == 3


def test_schedule_context_reads_a_retired_game_day_as_an_off_day(app):
    with app.app_context():
        _seed_and_drop(_all_game_3s(), {990301})
        context = build_team_schedule_context(135, SLATE, team_name_resolver=lambda _id: None)
        assert context['is_playing_today'] is False
        assert context['games_today_count'] == 0


def test_ledger_rest_does_not_wait_for_a_retired_game(app):
    with app.app_context():
        _seed_and_drop(_all_game_3s(), {990301})
        db.session.commit()
        assert ledger_confirmed_rest._team_has_unsettled_game(135, SLATE + timedelta(days=1)) is False
        assert ledger_confirmed_rest._team_has_unsettled_game(144, SLATE + timedelta(days=1)) is True


# ── 18, 37. Matchup ──────────────────────────────────────────────────────────

def test_matchup_marks_a_retired_game_not_upcoming(app):
    with app.app_context():
        _seed_and_drop(_all_game_3s(), {990301})
        payload = build_scheduled_game_matchup_payload(db.session.get(SlateGame, 990301), None)
        assert payload['status'] == 'not_upcoming'
        assert payload['reason_code'] == 'scheduled_game_removed_from_mlb_schedule'
        assert payload['comparison'] is None
        assert payload['game']['game_pk'] == 990301
        assert payload['game']['status']['normalized'] == 'cancelled'
        listed = build_scheduled_game_matchup_payload(db.session.get(SlateGame, 990302), None)
        assert listed['status'] != 'not_upcoming'


# ── 35, 36. Tonight ──────────────────────────────────────────────────────────

def test_a_published_edition_serves_the_retired_game_as_cancelled(app):
    with app.app_context():
        _ingest(_window(_all_game_3s()), now=T0 - timedelta(hours=12))
        stored = build_tonight_v1(
            _snapshot(), SlateGame.query.filter_by(game_date_et=SLATE).all(),
            generated_at=T0 - timedelta(hours=11),
        )
        assert stored['summary']['game_count'] == 4

        remaining = [g for g in _all_game_3s() if g['gamePk'] == 990302]
        _ingest(_window(remaining), now=T0)
        _ingest(_window(remaining), now=LATER)
        current = {row.game_pk: row for row in SlateGame.query.all()}
        served, identity = overlay_game_state(stored, current)

        # The stored edition is immutable: same games, same order.
        assert [g['game_pk'] for g in served['games']] == [g['game_pk'] for g in stored['games']]
        assert stored['summary']['game_count'] == 4
        states = {g['game_pk']: g['state'] for g in served['games']}
        assert states == {990301: 'cancelled', 990302: 'scheduled',
                          990303: 'cancelled', 990304: 'cancelled'}
        assert served['summary']['game_count'] == 1
        assert served['summary']['games_by_state']['cancelled'] == 3
        assert identity

        rebuilt = build_tonight_v1(
            _snapshot(), SlateGame.query.filter_by(game_date_et=SLATE).all(),
            generated_at=LATER,
        )
        assert [g['game_pk'] for g in rebuilt['games']] == [990302]
        assert 'cancelled' not in rebuilt['summary']['games_by_state']
