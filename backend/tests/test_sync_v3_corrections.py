from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path

import pytest

from sync_v3.cycle import run_cycle
from sync_v3.rehearse import isolated_cluster
from sync_v3.replay import install
from sync_v3.comparison import compare_finals


def test_changed_final_only_invalidates_affected_pitcher_and_club():
    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    fixture = json.loads((Path(__file__).parent/'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime(2026,8,1,tzinfo=timezone.utc)
    sources = {(r['endpoint'],tuple(sorted(r['params'].items()))):r['body'] for r in fixture['responses']}
    def fetch(endpoint, params):
        return sources[endpoint,tuple(sorted(params.items()))]
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        db = connect()
        try:
            for i in range(4):
                box = sources['/game/12345/boxscore',()]
                if i == 1:
                    box['teams']['home']['players']['ID102']['stats']['pitching']['strikeOuts'] = 4
                if i == 3:
                    box['teams']['home']['teamStats']['pitching']['inningsPitched'] = '8.0'
                result = run_cycle(db, day, fetch, teams=[111], clock=lambda:at+timedelta(days=2*i))
                if i == 3:
                    assert [status for _,status in result].count('refused') == 1
                else:
                    assert all(status == 'received' for _,status in result)
                with db, db.cursor() as cur:
                    assert compare_finals(cur) == (1,3)
            with db, db.cursor() as cur:
                cur.execute("SELECT id,predecessor FROM candidate.revisions WHERE domain='final' ORDER BY revision")
                first,second = cur.fetchall()
                assert first[1] is None and second[1] == first[0]
                cur.execute('SELECT entity_type,entity_id FROM candidate.impacts WHERE revision_id=%s', (second[0],))
                assert set(cur) == {('pitcher',102),('team',147)}
        finally:
            db.close()


def test_missing_slate_is_unknown_and_a_proven_off_day_preserves_workload():
    from sync_v3.workload import load_calendar, pitcher_windows, team_workload
    from sync_v3.comparison import compare_team_workload

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    folder = Path(__file__).parent/'fixtures/sync_v3'
    fixture = json.loads((folder/'played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime(2026,8,1,tzinfo=timezone.utc)
    sources = {(r['endpoint'],r['params'].get('rosterType')):r['body'] for r in fixture['responses']}
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        worker = connect()
        try:
            for offset in range(3):
                if offset:
                    sources['/schedule',None] = {'totalGames':0,'dates':[]}
                statuses = run_cycle(worker, day+timedelta(days=offset),
                                     lambda endpoint,params:sources[endpoint,params.get('rosterType')],
                                     teams=[111], clock=lambda:at+timedelta(days=offset))
                assert all(status=='received' for _,status in statuses)
            with worker, worker.cursor() as cur:
                windows = pitcher_windows(cur, 102, day+timedelta(days=2))
                assert windows[3]['facts'] == {'appearances':1,'multi_inning':1,'high_pitch_outings':0,
                    'batters_faced':4,'outs_recorded':9,'pitches_thrown':15}
                through = day + timedelta(days=2)
                calendar = load_calendar(cur, through, team=147)
                team = team_workload(cur, calendar, 147, through)
                assert compare_team_workload(cur, calendar, team) == ['window_3']
                team['facts']['windows']['window_3']['pitches']['value'] += 1
                with pytest.raises(ValueError, match='Official club workload differs'):
                    compare_team_workload(cur, calendar, team)
                assert len(windows[3]['sources']) == 4
                assert windows[5]['facts'] is None and len(windows[5]['gaps'])==2
                assert pitcher_windows(cur, 999999, day+timedelta(days=2))[3]['facts'] is None
        finally:
            worker.close()


def test_candidate_counts_a_supported_opener_without_changing_his_official_start():
    from sync_v3.workload import workload_lines

    common = {'game_pk': 21, 'game_date': '2024-08-05', 'pitches_thrown': 18}
    def line(team, player, started, outs):
        return dict(common, team_id=team, pitcher_mlb_id=player, games_started=started,
                    is_reliever=not started, outs_recorded=outs)
    lines = list(workload_lines([line(111, 1, 1, 3), line(111, 2, 0, 18),
                                 line(147, 3, 1, 21), line(147, 4, 0, 6)]))
    assert [(row['pitcher_mlb_id'], row['workload_class']) for row in lines] == [
        (1, 'opener'), (2, 'relief'), (4, 'relief')]
    assert lines[0]['games_started'] == 1


def test_rest_patterns_use_distinct_dates_and_require_coverage():
    from sync_v3.workload import rest_from_calendar

    through = date(2024, 8, 5)
    def calendar(offsets):
        days = {through-timedelta(days=i): ({'lines': [], 'sources': [i]}, None) for i in range(30)}
        for game_pk, offset in enumerate(offsets, start=1):
            day = through-timedelta(days=offset)
            days[day][0]['lines'].append({'pitcher_mlb_id': 1, 'game_pk': game_pk,
                'game_date': day.isoformat(), 'outs_recorded': 2, 'pitches_thrown': 9,
                'workload_class': 'relief'})
        return days
    days = calendar([0,0,2,4])
    facts = rest_from_calendar(days, 1, through)['facts']
    assert facts['three_in_four']['value'] is False and facts['four_in_six']['value'] is False
    assert facts['last_bullpen_appearance']['value'] is None
    assert facts['days_since_last_appearance']['value'] == 1
    days = calendar([0,1,2,4])
    facts = rest_from_calendar(days, 1, through)['facts']
    assert all(facts[key]['value'] for key in ('back_to_back','three_straight','three_in_four','four_in_six'))
    days[through-timedelta(days=3)] = (None,'missing_complete_schedule')
    assert rest_from_calendar(days, 1, through)['facts']['three_in_four']['value'] is None
    days = calendar([12])
    assert rest_from_calendar(days, 1, through)['facts']['days_since_last_appearance']['value'] == 13
    days[through-timedelta(days=9)] = (None,'missing_complete_schedule')
    assert rest_from_calendar(days, 1, through)['facts']['days_since_last_appearance']['value'] is None


def test_team_workload_uses_game_side_and_dated_active_authority():
    from sync_v3.workload import team_from_calendar

    end = date(2024, 8, 5)
    calendar = {end-timedelta(days=i): ({'official_lines': [], 'sources': [i]}, None)
                for i in range(30)}
    def line(player, team, started, pitches):
        return {'pitcher_mlb_id': player, 'games_started': started,
                'team_id': team, 'outs_recorded': 3, 'pitches_thrown': pitches}
    calendar[end][0]['official_lines'] = [
        line(1, 111, 1, 15), line(2, 111, 0, 20), line(3, 111, 0, 10), line(3, 147, 0, 40)]
    roster = ({'members': [{'id': 2, 'name': 'Known member'}]}, 37)
    result = team_from_calendar(calendar, 111, end, roster)
    assert result['roster_source'] == 37
    concentration = result['facts']['concentration_7_day']
    assert concentration['total_pitches'] == 30
    assert concentration['on_dated_active_roster_contribution']['pitches'] == 20
    assert concentration['off_dated_active_roster_contribution']['pitches'] == 10
    missing = team_from_calendar(calendar, 111, end, None)['facts']['concentration_7_day']
    assert missing['total_pitches'] == 30 and missing['off_dated_active_roster_contribution'] is None
    assert all(row['on_dated_active_roster'] is None for row in missing['top_3_contributors'])
    calendar[end-timedelta(days=5)] = (None, 'missing_complete_schedule')
    incomplete = team_from_calendar(calendar, 111, end, roster)['facts']
    assert incomplete['windows']['window_3']['pitches']['value'] == 30
    assert incomplete['concentration_7_day']['total_pitches'] is None


def test_missing_official_innings_cannot_establish_a_zero_out_relief_line():
    from sync_v3.workload import regular_day

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime.fromisoformat(fixture['observed_at'])
    sources = {(r['endpoint'], tuple(sorted(r['params'].items()))): r['body'] for r in fixture['responses']}
    side = sources['/game/12345/boxscore', ()]['teams']['home']
    line = side['players']['ID102']['stats']['pitching']
    side['teamStats']['pitching']['inningsPitched'] = side['players']['ID100']['stats']['pitching']['inningsPitched']
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        worker = connect()
        try:
            for offset, reported in enumerate(('0.0', None, ' ')):
                line['inningsPitched'] = reported
                receipts = run_cycle(worker, day, lambda ep, params: sources[ep, tuple(sorted(params.items()))],
                                     teams=[111], clock=lambda: at + timedelta(days=2 * offset))
                with worker, worker.cursor() as cur:
                    observed, reason = regular_day(cur, day)
                    if offset == 0:
                        assert observed is not None and reason is None
                        assert compare_finals(cur) == (1, 3)
                    else:
                        assert any(status == 'refused' for _, status in receipts)
                        assert observed is None and reason == 'missing_compatible_final'
                        cur.execute("SELECT count(*) FROM candidate.revisions WHERE domain='final'")
                        assert cur.fetchone() == (1,)
        finally:
            worker.close()


def test_outing_pitch_comparison_preserves_sample_and_withholds_ambiguous_baselines():
    from sync_v3.workload import outing_pitch_comparison

    through = date(2024, 8, 7)
    calendar = {through-timedelta(days=i): ({'lines': [], 'sources': [i]}, None) for i in range(30)}
    def outing(game, pitches):
        return {'pitcher_mlb_id': 9, 'workload_class': 'relief', 'pitches_thrown': pitches, 'game_pk': game}
    prior = calendar[through-timedelta(days=1)][0]['lines']
    recent = calendar[through][0]['lines']
    recent.append(outing(3, 28))
    assert outing_pitch_comparison(calendar, 9, through)['reason'] == 'no_prior_outings_in_window'
    prior.extend([outing(1, 14), outing(2, 20)])
    assert outing_pitch_comparison(calendar, 9, through)['facts'] == {
        'last_outing_date': '2024-08-07', 'last_game_pk': 3, 'last_outing_pitches': 28,
        'prior_outings': 2, 'prior_total_pitches': 34, 'prior_max_pitches': 20,
        'difference_from_prior_max': 8,
    }
    recent.append(outing(4, 11))
    assert outing_pitch_comparison(calendar, 9, through)['reason'] == 'latest_outing_order_unknown'
    recent.pop()
    prior[0]['pitches_thrown'] = None
    assert outing_pitch_comparison(calendar, 9, through)['reason'] == 'pitch_count_unknown'
    calendar.pop(through-timedelta(days=29))
    assert outing_pitch_comparison(calendar, 9, through)['facts'] is None
