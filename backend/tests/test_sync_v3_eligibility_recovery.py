from contextlib import closing
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path

import pytest

from sync_v3 import eligibility_recovery as recovery, queue
from sync_v3.rehearse import isolated_cluster
from sync_v3.replay import install


@pytest.mark.parametrize('team_id,expected_box,interrupt', [(147, True, False), (112, False, False), (147, True, True)])
def test_dated_recovery_obeys_the_official_slate_and_leaves_other_jobs_pending(monkeypatch, team_id, expected_box, interrupt):
    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for isolated PostgreSQL')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime.fromisoformat(fixture['observed_at']) + timedelta(days=1)
    gap = dict(reason='eligibility_game_not_confirmed',
               evidence=dict(game_date=str(day), game_type='R', game_pk=12345, team_id=team_id))
    def readiness(cur, club, through):
        assert club == 111 and through == day
        return dict(reason='incomplete_eligibility_sample', eligibility_gaps={102: gap, 103: gap})
    monkeypatch.setattr(recovery, 'represented_readiness', readiness)
    calls = []
    def fetch(endpoint, params):
        calls.append(endpoint)
        return next(row['body'] for row in fixture['responses'] if row['endpoint'] == endpoint and row['params'] == params)

    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as worker, worker, worker.cursor() as cur:
            unrelated = queue.enqueue(cur, 'unrelated', dict(endpoint='/transactions', params={}),
                                      at, priority=200, budget='historical', product_date=day)
        if interrupt:
            def unavailable(endpoint, params):
                raise ConnectionError('fixture outage')
            with closing(connect()) as worker:
                failed = recovery.recover(worker, 111, day, max_jobs=1, fetch=unavailable, clock=lambda: at)
                assert failed['status'] == 'acquisition_failed'
                waiting = recovery.recover(worker, 111, day, max_jobs=1, fetch=fetch, clock=lambda: at)
                assert waiting['status'] == 'awaiting_retry_or_lease' and not calls
            at += timedelta(seconds=30)
            with closing(connect()) as other, other.cursor() as cur:
                assert queue.claim(cur, at, budget='historical', product_date=day)[0] == unrelated
                other.rollback()
        with closing(connect()) as worker:
            first = recovery.recover(worker, 111, day, max_jobs=1, fetch=fetch, clock=lambda: at)
            assert first['receipts'] == ['received'] and calls == ['/schedule']
        with closing(connect()) as worker:
            second = recovery.recover(worker, 111, day, max_jobs=3, fetch=fetch, clock=lambda: at)
            assert second['receipts'] == (['received'] if expected_box else [])
            assert second['status'] == 'withheld'
            assert calls == (['/schedule', '/game/12345/boxscore'] if expected_box else ['/schedule'])
            assert recovery.recover(worker, 111, day, max_jobs=3, fetch=fetch, clock=lambda: at)['receipts'] == []
            with worker, worker.cursor() as cur:
                cur.execute('SELECT state FROM candidate.jobs WHERE id=%s', (unrelated,))
                assert cur.fetchone() == ('pending',)
                cur.execute('SELECT count(*) FROM candidate.core_selections')
                assert cur.fetchone() == (0,)
        with pytest.raises(ValueError):
            recovery.recover(owner, 111, day, max_jobs=3, fetch=fetch, clock=lambda: at)


def test_uncredited_postseason_appearance_retains_the_required_round():
    from sync_v3.season_deployment import BaselineWithheld, _confirm_uncredited

    with pytest.raises(BaselineWithheld, match='uncredited_game_requires_official_final') as error:
        _confirm_uncredited(None, 102, 147, 12345, date(2024, 10, 18), 'L')
    assert error.value.game_evidence['game_type'] == 'L'


@pytest.mark.parametrize('reason,expected', [('world_series_decided', 'season_complete'),
                                             ('missing_competition_calendar', 'withheld')])
def test_completed_club_requires_agreeing_competition_evidence(monkeypatch, reason, expected):
    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for isolated PostgreSQL')
    club = dict(team_id=111, status='season_complete', basis='world_series_decided')
    monkeypatch.setattr(recovery, 'represented_readiness', lambda cur, team, day:
                        dict(reason=reason, team_state=None, competition=club))

    with isolated_cluster(pg) as (owner, connect), closing(connect()) as worker:
        install(owner)
        def unexpected(endpoint, params):
            pytest.fail('No source request is supported for this club')
        report = recovery.recover(worker, 111, date(2024, 11, 15), max_jobs=1, fetch=unexpected)
        assert report['status'] == expected and report['receipts'] == []
        with worker, worker.cursor() as cur:
            cur.execute('SELECT count(*) FROM candidate.jobs')
            assert cur.fetchone() == (0,)


def test_workload_recovery_fetches_only_the_missing_schedule_and_official_final(monkeypatch):
    from sync_v3.workload import regular_day

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for isolated PostgreSQL')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime.fromisoformat(fixture['observed_at']) + timedelta(days=1)
    def readiness(cur, club, through):
        _, gap = regular_day(cur, day)
        return dict(reference_date=str(through + timedelta(days=1)), reason=gap, gap_date=str(day))
    monkeypatch.setattr(recovery, 'represented_readiness', readiness)
    calls = []
    def fetch(endpoint, params):
        calls.append(endpoint)
        return next(row['body'] for row in fixture['responses'] if row['endpoint'] == endpoint and row['params'] == params)
    with isolated_cluster(pg) as (owner, connect), closing(connect()) as worker:
        install(owner)
        def run(include, through=day):
            return recovery.recover(worker, 111, through, max_jobs=1, fetch=fetch, include_workload=include,
                                    clock=lambda: at + timedelta(days=30))
        assert run(False)['status'] == 'withheld'
        assert run(True, day + timedelta(days=recovery.ACTIVE_WINDOW_DAYS))['status'] == 'withheld'
        assert calls == []
        assert run(True)['status'] == 'batch_limit'
        assert calls == ['/schedule']
        assert run(True)['status'] == 'ready'
        assert run(True)['receipts'] == []
        assert calls == ['/schedule', '/game/12345/boxscore']
        with worker, worker.cursor() as cur:
            cur.execute('SELECT count(*) FROM candidate.core_selections')
            assert cur.fetchone() == (0,)


def test_readiness_recovery_limits_reference_acquisition_to_consulted_evidence(monkeypatch):
    from sync_v3.dependencies import consult
    from sync_v3.discovery import calendar_requests

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for isolated PostgreSQL')
    day = date(2024, 8, 10)
    reference = day + timedelta(days=1)
    request, _ = calendar_requests(reference)
    consulted = None
    def readiness(cur, club, through):
        if consulted is not None:
            consult(cur, consulted.endpoint, consulted.params())
        return dict(reference_date=str(reference), reason='unresolved_source_conflict')
    monkeypatch.setattr(recovery, 'represented_readiness', readiness)
    with isolated_cluster(pg) as (owner, connect), closing(connect()) as worker:
        install(owner)
        with worker, worker.cursor() as cur:
            for consulted in (None, calendar_requests(day)[0]):
                assert recovery._needed(cur, 111, day, True)[1] == []
            consulted = request
            expected = (reference, request.endpoint, tuple(sorted(request.params().items())))
            assert recovery._needed(cur, 111, day, True)[1] == [expected]
            assert recovery._needed(cur, 111, day, False)[1] == []


def test_performance_recovery_uses_only_the_dated_club_finals(monkeypatch):
    from copy import deepcopy
    from sync_v3.workload import regular_day

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for isolated PostgreSQL')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime.fromisoformat(fixture['observed_at']) + timedelta(days=1)
    calls = []
    def official(endpoint, params):
        calls.append(endpoint)
        body = deepcopy(next(row['body'] for row in fixture['responses']
                             if row['endpoint'] == endpoint and row['params'] == params))
        if endpoint == '/schedule':
            listing = body['dates'][0]
            other = deepcopy(listing['games'][0])
            other['gamePk'] += 1
            other['teams']['home']['team']['id'] = 109
            other['teams']['away']['team']['id'] = 112
            listing['games'].append(other)
            listing['totalGames'] = body['totalGames'] = 2
        return body

    conflict = True
    def represented(cur, team, through):
        assert team == 111 and through == day
        _, gap = regular_day(cur, day, team=team)
        due = dict(reason=gap, outings=[[12345, 102]])
        if conflict:
            due['source_conflicts'] = [{'fields': ['walks']}]
        return dict(reason=None, dates={str(day): due})

    monkeypatch.setattr(recovery, 'active_group_performance', represented)
    with isolated_cluster(pg) as (owner, connect), closing(connect()) as worker:
        install(owner)
        def run():
            return recovery.recover(worker, 111, day, fetch=official, max_jobs=1, performance=True, clock=lambda: at)
        assert run()['performance_reason'] == 'official_performance_source_conflict' and not calls
        conflict = False
        assert run()['status'] == 'batch_limit'
        assert run()['status'] == 'outing_finals_complete'
        assert run()['receipts'] == []
        assert calls == ['/schedule', '/game/12345/boxscore']
        with worker, worker.cursor() as cur:
            cur.execute('SELECT count(*) FROM candidate.core_selections')
            assert cur.fetchone() == (0,)


@pytest.mark.parametrize('represented,reason', [
    ('2025-08-01', 'missing_compatible_final'),
    ('2026-08-01', 'missing_complete_schedule'),
    ('2026-07-29', 'previous_listing_requires_absence_proof'),
])
def test_performance_recovery_leaves_unsupported_refusals_intact(represented, reason):
    def unexpected(*args):
        pytest.fail('No recovery request is supported for this scope')
    result = dict(reason=None, dates={represented: dict(reason=reason, outings=[[12345, 102]])})
    through = date(2026, 7, 29)
    assert recovery._performance_gaps(None, 111, through, result, unexpected) == reason
    assert recovery._performance_gaps(None, 111, through, dict(reason=None, dates={}), unexpected) == 'no_supported_relief_outings'


def test_source_disagreement_preserves_recovery_for_independent_outings(monkeypatch):

    recovered_days = []
    def capture(cur, day, missing, *, team):
        recovered_days.append((day, team))
    monkeypatch.setattr(recovery, '_missing_day_finals', capture)
    through = date(2017, 8, 28)
    report = dict(reason=None, dates={
        '2017-05-01': dict(reason=None, source_conflicts=[{'fields': ['batters_faced']}]),
        '2017-06-02': dict(reason='missing_compatible_final', outings=[[456, 102]]),
    })
    assert recovery._performance_gaps(None, 112, through, report, None) == 'official_performance_source_conflict'
    assert recovered_days == [(date(2017, 6, 2), 112)]


def test_board_arrival_recovers_earlier_season_only_from_qualified_dated_membership(monkeypatch):
    from sync_v3 import evidence
    from sync_v3.discovery import pitcher_requests

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for isolated PostgreSQL')
    through = date(2017, 8, 28)
    old = date(2016, 12, 31)
    at = datetime.fromisoformat('2017-08-30T12:00:00+00:00')
    base = dict(team=141, reason=None, reference_date='2017-08-29')
    qualified_staff = None
    monkeypatch.setattr(recovery, 'represented_readiness', lambda *args: base)

    def board_population(cur, report, cutoff):
        assert report is base and cutoff == through
        if qualified_staff is None:
            return None, None
        for request in pitcher_requests(old, [474463]):
            if evidence.latest_qualified_source(cur, request.endpoint, request.params()) is None:
                gap = dict(reason='missing_eligibility_stats', evidence=dict(year=2016, round='R'))
                return qualified_staff, dict(reason='incomplete_eligibility_sample', eligibility_gaps={474463: gap})
        return qualified_staff, dict(reason=None)

    monkeypatch.setattr(recovery, 'availability_day_population', board_population)
    calls = []

    def fetch(endpoint, params):
        calls.append((endpoint, params))
        return {'stats': []}

    with isolated_cluster(pg) as (owner, connect), closing(connect()) as worker:
        install(owner)
        def run():
            return recovery.recover(worker, 141, through, fetch=fetch, board_rest=True, max_jobs=1, clock=lambda: at)
        assert run()['board_rest_reason'] == 'missing_qualified_board_roster' and not calls
        qualified_staff = {474463}
        assert run()['status'] == 'batch_limit'
        assert run()['status'] == 'board_eligibility_complete'
        assert run()['receipts'] == []
        assert len(calls) == 2 and all(ep == '/people/474463/stats' and p['season'] == 2016 for ep, p in calls)
        with worker, worker.cursor() as cur:
            cur.execute('SELECT count(*) FROM candidate.core_selections')
            assert cur.fetchone() == (0,)
