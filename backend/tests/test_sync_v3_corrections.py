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
    sources['/teams/111/roster', 'active']['roster'] = [
        {'person': {'id': 98765}, 'position': {'code': '1'}},
        {'person': {'id': 98766}, 'position': {'code': '6'}},
    ]
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
                from sync_v3.deployment import game_deployment
                deployment = game_deployment(cur, 12345, day)
                assert deployment['entry_reason'] == 'missing_complete_plays'
                arm, = deployment['relief_appearances']
                assert arm['mlb_player_id'] == 102 and arm['outs'] == 9 and arm['entry_inning'] is None
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
                # A candidate omission could otherwise make both totals agree at zero.
                incomplete_calendar = dict(calendar)
                day_facts = calendar[day][0]
                incomplete_calendar[day] = dict(day_facts, sources=[], official_lines=[]), None
                false_zero = team_workload(cur, incomplete_calendar, 147, through)
                with pytest.raises(ValueError, match='Official slate and cited boxscores differ'):
                    compare_team_workload(cur, incomplete_calendar, false_zero)
                assert team['facts']['windows']['window_3']['batters_faced']['value'] == 4
                assert len(windows[3]['sources']) == 4
                assert windows[5]['facts'] is None and len(windows[5]['gaps'])==2
                rookie = pitcher_windows(cur, 98765, through)
                assert rookie[3]['facts']['appearances'] == rookie[3]['facts']['pitches_thrown'] == 0
                assert len(rookie[3]['identity_sources']) == 1
                assert rookie[5]['facts'] is None
                assert pitcher_windows(cur, 98766, through)[3]['facts'] is None
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
    five = result['facts']['windows']['window_5']
    assert five['appearances']['value'] == 2 and five['pitches']['value'] == 30
    assert five['batters_faced']['value'] is None
    assert five['batters_faced']['reason_codes'] == ['bullpen_batters_faced_unknown']
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
    from sync_v3.workload import regular_day, load_club_calendars

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
                        clubs = load_club_calendars(cur, day)
                        assert len(clubs) == 30
                        assert {club for club, calendar in clubs.items() if calendar[day][1]} == {111, 147}
                        assert clubs[119][day][0]['official_lines'] == []
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


def test_representative_teams_are_scoped_to_the_official_all_star_matchup():
    from sync_v3.canonical import Refused, game_identity

    game = {'gamePk': 747298, 'officialDate': '2024-07-16', 'gameType': 'A', 'status': {},
            'teams': {'away': {'team': {'id': 160}}, 'home': {'team': {'id': 159}}}}
    assert game_identity(game)['gameType'] == 'A'
    for kind in ('R', 'W', 'I', 'E'):
        with pytest.raises(Refused, match='game sides'):
            game_identity(dict(game, gameType=kind))
    game['teams']['home']['team']['id'] = 111
    with pytest.raises(Refused, match='game sides'):
        game_identity(game)
    game['teams']['away']['team']['id'] = 147
    with pytest.raises(Refused, match='game type'):
        game_identity(dict(game, gameType='unrecognized'))


@pytest.mark.parametrize('represented,linkage', [
    ('2024-06-26', {'resumeDate': '2024-08-26T18:05:00Z', 'resumeGameDate': '2024-08-26'}),
    ('2024-08-26', {'resumedFrom': '2024-06-26T23:10:00Z', 'resumedFromDate': '2024-06-26'}),
    ('2024-06-26', {'resumeDate': '2024-06-27T01:00:00Z'}),
])
def test_a_combined_resumed_boxscore_cannot_date_individual_workload(represented, linkage):
    from sync_v3.workload import _game_workload

    game = {'officialDate': '2024-06-26', 'status': {'statusCode': 'F', 'detailedState': 'Final'}, **linkage}
    assert _game_workload(None, game, date.fromisoformat(represented), 1) == (
        None, 'resumed_game_workload_dates_unresolved')


def test_all_star_final_retains_lines_without_attributing_workload_to_an_mlb_club():
    from sync_v3.workload import regular_day

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime.fromisoformat(fixture['observed_at'])
    sources = {(r['endpoint'], tuple(sorted(r['params'].items()))): r['body'] for r in fixture['responses']}
    game = fixture['responses'][0]['body']['dates'][0]['games'][0]
    game['gameType'] = 'A'
    box = sources['/game/12345/boxscore', ()]
    for side, representative in [('away', 160), ('home', 159)]:
        game['teams'][side]['team']['id'] = representative
        box['teams'][side]['team']['id'] = representative
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        worker = connect()
        try:
            receipts = run_cycle(worker, day, lambda ep, params: sources[ep, tuple(sorted(params.items()))],
                                 teams=[111], clock=lambda: at)
            assert all(status == 'received' for _, status in receipts)
            with worker, worker.cursor() as cur:
                assert compare_finals(cur) == (1, 3)
                observed, reason = regular_day(cur, day)
                assert reason is None and observed['official_lines'] == []
                cur.execute("SELECT count(*) FROM candidate.impacts WHERE entity_type='team'")
                assert cur.fetchone() == (0,)
        finally:
            worker.close()


def test_rolling_snapshots_keep_predecessors_and_scope_a_final_correction(monkeypatch):
    from contextlib import closing
    from sync_v3.history import affected_workload, rebuild_for_final, rebuild_for_observation, record_workload

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    fixtures = Path(__file__).parent / 'fixtures/sync_v3'
    fixture = json.loads((fixtures / 'played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    sources = {(r['endpoint'], r['params'].get('rosterType')): r['body'] for r in fixture['responses']}
    def fetch(endpoint, params):
        if endpoint == '/schedule' and params['startDate'] != day.isoformat():
            return {'totalGames': 0, 'dates': []}
        return sources[endpoint, params.get('rosterType')]
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            end = day + timedelta(days=2)
            missing = record_workload(db, 'pitcher', 98765, end)
            for offset in range(3):
                run_cycle(db, day + timedelta(days=offset), fetch, teams=[111], clock=lambda: at + timedelta(days=offset))
            with db, db.cursor() as cur:
                cur.execute("SELECT id FROM candidate.revisions WHERE domain='final' AND revision=1")
                initial_final = cur.fetchone()[0]
            recovered, = rebuild_for_final(db, initial_final)
            assert recovered[1] == 2 and recovered[2] != missing[2]
            from concurrent.futures import ThreadPoolExecutor
            from threading import Barrier
            ready = Barrier(2)
            def simultaneous_build():
                with closing(connect()) as other:
                    ready.wait(timeout=10)
                    return record_workload(other, 'pitcher', 102, end)
            with ThreadPoolExecutor(max_workers=2) as pool:
                builds = [pool.submit(simultaneous_build) for _ in range(2)]
                first, duplicate = (build.result(timeout=30) for build in builds)
            assert first == duplicate and first[1] == 1
            assert record_workload(db, 'pitcher', 102, end) == first
            team = record_workload(db, 'team', 147, end)
            record_workload(db, 'team', 111, end)
            record_workload(db, 'pitcher', 102, day + timedelta(days=30))
            source = sources['/game/12345/boxscore', None]
            source['teams']['home']['players']['ID102']['stats']['pitching']['numberOfPitches'] = 24
            run_cycle(db, day, fetch, teams=[111], clock=lambda: at + timedelta(days=4))
            with db, db.cursor() as cur:
                cur.execute("SELECT id FROM candidate.revisions WHERE domain='final' AND revision=2")
                revision = cur.fetchone()[0]
                affected = affected_workload(cur, revision)
            assert affected == [('pitcher', 102, end), ('team', 147, end)]
            from sync_v3 import history
            append = history._append
            def fail_second(cur, subject, mlb_id, through):
                if subject == 'team':
                    raise RuntimeError('injected after pitcher rebuild')
                return append(cur, subject, mlb_id, through)
            with monkeypatch.context() as patch:
                patch.setattr(history, '_append', fail_second)
                with pytest.raises(RuntimeError, match='injected'):
                    rebuild_for_final(db, revision)
            with db, db.cursor() as cur:
                cur.execute('SELECT count(*) FROM candidate.workload_history WHERE revision=2 AND mlb_id IN (102,147)')
                assert cur.fetchone() == (0,)
            rebuilt = rebuild_for_final(db, revision)
            assert rebuild_for_final(db, revision) == rebuilt
            assert rebuilt[0][1] == rebuilt[1][1] == 2
            assert rebuilt[0][2] != first[2] and rebuilt[1][2] != team[2]
            with db, db.cursor() as cur:
                cur.execute("""SELECT predecessor,facts->'windows'->'3'->'facts'->'pitches_thrown'
                               FROM candidate.workload_history WHERE id=ANY(%s) ORDER BY revision""",
                            ([first[0], rebuilt[0][0]],))
                assert cur.fetchall() == [(None, 15), (first[0], 24)]
                cur.execute('SELECT count(*) FROM candidate.workload_history_sources WHERE snapshot=%s', (first[0],))
                assert cur.fetchone()[0] > 0
            source['teams']['home']['teamStats']['pitching']['inningsPitched'] = '8.0'
            run_cycle(db, day, fetch, teams=[111], clock=lambda: at + timedelta(days=6))
            with db, db.cursor() as cur:
                cur.execute("SELECT max(id) FROM candidate.fetches WHERE endpoint='/game/12345/boxscore'")
                refused_box = cur.fetchone()[0]
            rebuild_for_observation(db, refused_box)
            with db, db.cursor() as cur:
                cur.execute("""SELECT facts->'windows'->'3'->'facts', facts->'coverage_gaps'->>%s
                               FROM candidate.workload_history WHERE subject='pitcher' AND mlb_id=102 AND represented=%s
                               ORDER BY revision DESC LIMIT 1""", (day.isoformat(), end))
                assert cur.fetchone() == (None, 'missing_compatible_final')


def test_changed_bulk_follower_also_invalidates_the_unchanged_opener():
    from services.game_shape import BULK_FOLLOWER_MIN_OUTS
    from sync_v3.canonical import final_impacts

    day = '2024-08-05'
    common = {'game_date': day, 'team_id': 111, 'pitches_thrown': 15}
    start = dict(common, pitcher_mlb_id=1, games_started=1, is_reliever=False, outs_recorded=3)
    follower = dict(common, pitcher_mlb_id=2, games_started=0, is_reliever=True, outs_recorded=BULK_FOLLOWER_MIN_OUTS)
    assert final_impacts([start, follower], [start, dict(follower, outs_recorded=BULK_FOLLOWER_MIN_OUTS-1)]) == {
        ('pitcher', 1, day), ('pitcher', 2, day), ('team', 111, day)}


def test_disappearing_final_withholds_affected_workload_and_retains_both_schedules(tmp_path):
    from contextlib import closing
    from sync_v3.history import rebuild_for_observation, record_workload
    from sync_v3.replay import run_fixture
    from sync_v3.workload import regular_day

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    base = Path(__file__).parent / 'fixtures/sync_v3'
    played = json.loads((base / 'played.json').read_text())
    day = date.fromisoformat(played['baseball_date'])
    quiet = json.loads((base / 'quiet.json').read_text().replace('2026-11-21', day.isoformat()))
    quiet['observed_at'] = '2026-08-03T10:00:00Z'
    changed = tmp_path / 'quiet.json'
    changed.write_text(json.dumps(quiet))
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            run_fixture(db, base / 'played.json')
            original = record_workload(db, 'team', 147, day)
            run_fixture(db, changed)
            with db, db.cursor() as cur:
                cur.execute("SELECT max(id) FROM candidate.fetches WHERE endpoint='/schedule'")
                receipt = cur.fetchone()[0]
            replacement, = rebuild_for_observation(db, receipt)
            assert replacement[1] == 2 and replacement[2] != original[2]
            assert rebuild_for_observation(db, receipt) == [replacement]
            with db, db.cursor() as cur:
                from sync_v3.deployment import club_role_movement
                movement = club_role_movement(cur, 147, day)
                assert movement['gaps'][day.isoformat()] == ['previous_listing_requires_absence_proof']
                assert movement['profiles'] == []
                for scope in (None, 111, 147):
                    assert regular_day(cur, day, team=scope) == (None, 'previous_listing_requires_absence_proof')
                assert regular_day(cur, day, team=118)[1] is None
            identifier, _, _ = record_workload(db, 'team', 147, day)
            with db, db.cursor() as cur:
                cur.execute("""SELECT count(*) FROM candidate.workload_history_sources s
                               JOIN candidate.fetches f ON f.id=s.source_id
                               WHERE s.snapshot=%s AND f.endpoint='/schedule'""", (identifier,))
                assert cur.fetchone() == (2,)


def test_active_roster_revision_rebuilds_identity_after_last_outing_leaves_window(tmp_path):
    from contextlib import closing
    from sync_v3.history import rebuild_for_observation, record_workload
    from sync_v3.replay import run_fixture

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    base = Path(__file__).parent / 'fixtures/sync_v3/quiet.json'
    fixture = json.loads(base.read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            roster = next(r for r in fixture['responses'] if r['params'].get('rosterType') == 'active')
            roster['body']['roster'] = [{'person': {'id': 98765}, 'position': {'code': '1'}}]
            copied = tmp_path / 'roster.json'
            copied.write_text(json.dumps(fixture))
            run_fixture(db, copied)
            first = record_workload(db, 'pitcher', 98765, day)
            fixture['observed_at'] = '2026-11-23T12:00:00Z'
            roster['body']['roster'][0]['person']['id'] = 98766
            copied.write_text(json.dumps(fixture))
            run_fixture(db, copied)
            with db, db.cursor() as cur:
                cur.execute("SELECT max(id) FROM candidate.fetches WHERE parameters->>'rosterType'='active'")
                receipt = cur.fetchone()[0]
            revised, = rebuild_for_observation(db, receipt)
            assert revised[1] == 2 and revised[2] != first[2]
            with db, db.cursor() as cur:
                cur.execute("""SELECT facts->'windows'->'3'->'player_observed' FROM candidate.workload_history
                               WHERE id=ANY(%s) ORDER BY revision""", ([first[0], revised[0]],))
                assert cur.fetchall() == [(True,), (False,)]
                cur.execute('SELECT 1 FROM candidate.workload_history_sources WHERE snapshot=%s AND source_id=%s',
                            (revised[0], receipt))
                assert cur.fetchone() == (1,)


def test_late_postponed_listing_cannot_overrule_another_dates_final(tmp_path):
    from contextlib import closing
    from sync_v3.replay import run_fixture
    from sync_v3.workload import regular_day

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for an isolated PostgreSQL server')
    base = Path(__file__).parent / 'fixtures/sync_v3'
    played = json.loads((base / 'played.json').read_text())
    final_day = date.fromisoformat(played['baseball_date'])
    earlier = final_day - timedelta(days=1)
    postponed = json.loads((base / 'quiet.json').read_text().replace('2026-11-21', earlier.isoformat()))
    postponed['observed_at'] = '2026-08-05T12:00:00Z'
    slate = next(row['body'] for row in played['responses'] if row['endpoint'] == '/schedule')
    slate['dates'][0]['date'] = earlier.isoformat()
    slate['dates'][0]['games'][0]['status'] = {
        'abstractGameState': 'Final', 'statusCode': 'DR', 'detailedState': 'Postponed'}
    next(row for row in postponed['responses'] if row['endpoint'] == '/schedule')['body'] = slate
    file = tmp_path / 'postponed.json'
    file.write_text(json.dumps(postponed))
    for order in ((file, base / 'played.json'), (base / 'played.json', file)):
        with isolated_cluster(pg) as (owner, connect):
            install(owner)
            with closing(connect()) as db:
                for fixture in order:
                    run_fixture(db, fixture)
                with db, db.cursor() as cur:
                    assert compare_finals(cur) == (1, 3)
                    before, reason = regular_day(cur, earlier, team=147)
                    assert reason is None and before['lines'] == []
                    closed, reason = regular_day(cur, final_day, team=147)
                    assert reason is None and [r['pitcher_mlb_id'] for r in closed['lines']] == [102]
                    cur.execute("""SELECT f.parameters->>'startDate' FROM candidate.revisions r
                                   JOIN candidate.fetches f ON f.id=r.context_id WHERE r.domain='final'""")
                    assert cur.fetchall() == [(final_day.isoformat(),)]


def test_candidate_changes_reproduce_prior_revision_and_withhold_unknown_reads():
    from contextlib import closing
    from sync_v3.change_history import readiness_changes
    from sync_v3.history import _store
    from sync_v3.intelligence_history import DOMAINS

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for an isolated PostgreSQL server')
    end = date(2024, 8, 7)

    def freeze(cur, day, key):
        arm = {'arm_read': {'key': key}} if key else None
        facts = dict(team=118, membership_date=day.isoformat(), reference_date=(day + timedelta(days=1)).isoformat(),
                     arms={'102': {'read': arm}}, team_state={'public_code': 'stretched'},
                     comparison={'team_states_compared': 1})
        return _store(cur, 'team', 118, day, DOMAINS['readiness'][1], facts, [])

    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db, db, db.cursor() as cur:
            freeze(cur, end, 'watch_arm')
            assert readiness_changes(cur, 118, end)['status'] == 'missing_snapshot'
            freeze(cur, end - timedelta(days=1), 'clean_option')
            first = readiness_changes(cur, 118, end)
            assert first['status'] == 'complete'
            assert [e['kind'] for e in first['events']] == ['arm_read_changed', 'clean_option_count_changed']
            assert first['events'][0]['player'] == 102
            freeze(cur, end, None)
            revised = readiness_changes(cur, 118, end)
            assert revised['status'] == 'partial_arm_coverage' and revised['events'] == []
            assert revised['lineage'][1]['revision'] == 2
            assert readiness_changes(cur, 118, end, revisions=(1, 1)) == first
            assert readiness_changes(cur, 118, end, revisions=(3, 1))['status'] == 'missing_snapshot'


def test_candidate_event_set_retains_exact_inputs_after_correction():
    from contextlib import closing
    from sync_v3.change_history import record_changes
    from sync_v3.history import _store
    from sync_v3.intelligence_history import DOMAINS

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    end = date(2024, 8, 7)
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            empty = record_changes(db, 'readiness', 118, end)
            for day in (end - timedelta(days=1), end):
                with db, db.cursor() as cur:
                    facts = dict(team=118, membership_date=str(day), reference_date=str(day + timedelta(days=1)),
                                 arms={}, team_state=None, comparison={'team_states_compared': 0})
                    _store(cur, 'team', 118, day, DOMAINS['readiness'][1], facts, [])
            second = record_changes(db, 'readiness', 118, end)
            assert second[1] == 2 and record_changes(db, 'readiness', 118, end) == second
            with db, db.cursor() as cur:
                cur.execute("""SELECT h.predecessor,h.facts->>'status', count(i.input_snapshot)
                               FROM candidate.workload_history h LEFT JOIN candidate.change_inputs i
                               ON i.change_snapshot=h.id WHERE h.id=ANY(%s)
                               GROUP BY h.id ORDER BY h.revision""", ([empty[0], second[0]],))
                assert cur.fetchall() == [(None, 'missing_snapshot', 0), (empty[0], 'incomparable_readiness', 2)]


def test_pitcher_patterns_end_only_with_complete_negative_evidence():
    from contextlib import closing
    from services.team_board_what_changed import PATTERNS
    from sync_v3.change_history import pattern_changes
    from sync_v3.history import _store
    from sync_v3.intelligence_history import DOMAINS

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    end = date(2024, 8, 7)

    def store(cur, day, value, status):
        facts = {key: {'value': False, 'status': 'complete'} for key, _ in PATTERNS}
        facts['back_to_back'] = {'value': value, 'status': status}
        report = {'rest': dict(mlb_player_id=102, through=str(day), reference=str(day+timedelta(days=1)), facts=facts)}
        _store(cur, 'pitcher', 102, day, DOMAINS['pitcher_rest'][1], report, [])

    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db, db, db.cursor() as cur:
            store(cur, end - timedelta(days=1), True, 'complete')
            store(cur, end, False, 'complete')
            first = pattern_changes(cur, 102, end)
            assert [event['kind'] for event in first['events']] == ['back_to_back_ended']
            store(cur, end, False, 'partial')
            changed = pattern_changes(cur, 102, end)
            assert changed['status'] == 'partial_rest_coverage' and changed['events'] == []


def test_generation_keeps_all_clubs_and_pins_immutable_event_inputs():
    from contextlib import closing
    from sync_v3.change_history import record_changes
    from sync_v3.generation import freeze_generation, verify_generation
    from sync_v3.history import _store
    from sync_v3.intelligence_history import DOMAINS

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    end = date(2024, 8, 7)

    def store(cur, day, reason):
        facts = dict(team=118, competition=dict(team_id=118, reference_date=str(day+timedelta(days=1)),
                                                status='undetermined', basis=reason),
                     mode='retrospective_candidate', current_serving_eligible=False,
                     membership_date=str(day), reference_date=str(day+timedelta(days=1)),
                     team_state=None, reason=reason, arms={},
                     comparison={'team_states_compared': 0, 'arm_statuses_compared': 0, 'withheld_arms': 0})
        _store(cur, 'team', 118, day, DOMAINS['readiness'][1], facts, [])

    def load(cur, digest):
        cur.execute('SELECT manifest FROM candidate.generations WHERE digest=%s', (digest,))
        return cur.fetchone()[0]

    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            blank = freeze_generation(db, end)
            with db, db.cursor() as cur:
                empty = load(cur, blank)
                assert len({club['team'] for club in empty['clubs']}) == 30
                assert empty['members'] == [] and empty['missing'] and not empty['current_serving_eligible']
                for day in (end-timedelta(days=1), end):
                    store(cur, day, 'missing_official_decision')
            record_changes(db, 'readiness', 118, end)
            first = freeze_generation(db, end)
            assert first != blank and freeze_generation(db, end) == first
            with db, db.cursor() as cur:
                assert load(cur, first)['stale_comparisons'] == []
                # Simulate a corrected input whose derived event set has not yet been rebuilt.
                store(cur, end-timedelta(days=1), 'postseason_participation_unresolved')
            frozen = verify_generation(db, first, compare_latest=True)
            assert frozen['selection_review']['reason_codes'] == ['superseded_generation']
            with db, db.cursor() as cur:
                cur.execute('SELECT count(*) FROM candidate.generations')
                assert cur.fetchone() == (2,)
            second = freeze_generation(db, end)
            assert frozen['selection_review']['latest_inventory_digest'] == second
            assert verify_generation(db, second, compare_latest=True)['selection_review']['status'] == 'withheld'
            with db, db.cursor() as cur:
                assert load(cur, second)['stale_comparisons'] == [['team', 118, 'candidate_readiness_changes_v1']]
                assert load(cur, first)['stale_comparisons'] == [] and load(cur, blank) == empty
            import psycopg2
            with pytest.raises(psycopg2.errors.RaiseException, match='provenance is sealed'), db, db.cursor() as cur:
                cur.execute("""INSERT INTO candidate.history_requests
                               SELECT min(id),'/schedule','{}'::jsonb FROM candidate.workload_history""")
            assert verify_generation(db, first)['snapshots'] == 2
            assert verify_generation(db, blank)['snapshots'] == 0
            # A valid content hash alone cannot certify omitted scopes or an invented empty slate.
            from hashlib import sha256
            from psycopg2.extras import Json
            from sync_v3.evidence import encode_json
            for altered, error in (
                (dict(empty, missing=[]), 'scope coverage'),
                (dict(empty, availability_reference=str(end)), 'scope coverage'),
                (dict(empty, slate=dict(empty['slate'], games=[], reason=None)), 'pinned successful receipt'),
            ):
                digest = sha256(encode_json(altered)).hexdigest()
                with db, db.cursor() as cur:
                    cur.execute('INSERT INTO candidate.generations (digest,represented,manifest) VALUES (%s,%s,%s)',
                                (digest, end, Json(altered)))
                with pytest.raises(ValueError, match=error):
                    verify_generation(db, digest)
            with pytest.raises(psycopg2.errors.RaiseException, match='membership is sealed'), db, db.cursor() as cur:
                cur.execute('INSERT INTO candidate.generation_inputs SELECT %s,min(id) FROM candidate.workload_history',
                            (blank,))
            assert verify_generation(db, blank)['snapshots'] == 0



def test_generation_batches_resume_on_another_connection_without_repeating_completed_scopes():
    from contextlib import closing
    from sync_v3.generation import build_batch

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    day = date(2024, 8, 7)
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            with pytest.raises(ValueError):
                build_batch(db, day, 0)
            first = build_batch(db, day, 2)
        with closing(connect()) as db:
            second = build_batch(db, day, 1)
            assert second['before'] == first['after']
            assert len(first['processed']) == 2 and len(second['processed']) == 1
            assert set(first['processed']).isdisjoint(second['processed'])
            with db, db.cursor() as cur:
                cur.execute("SELECT manifest FROM candidate.generations WHERE digest=%s", (second['after'],))
                manifest = cur.fetchone()[0]
                assert len(manifest['members']) == 3 and not manifest['current_serving_eligible']


def test_older_same_day_schedule_can_confirm_only_an_identical_unrevised_listing(tmp_path):
    from contextlib import closing
    from sync_v3.replay import ReplayWithheld, run_fixture

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    played = Path(__file__).parent / 'fixtures/sync_v3/played.json'
    data = json.loads(played.read_text())
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            run_fixture(db, played)
            data['observed_at'] = '2026-07-30T00:45:00Z'
            copy = tmp_path / 'same.json'
            copy.write_text(json.dumps(data))
            run_fixture(db, copy)
            with db, db.cursor() as cur:
                cur.execute("SELECT count(*),count(DISTINCT revision_id) FROM candidate.confirmations WHERE domain='schedule'")
                assert cur.fetchone() == (2, 1)
                assert compare_finals(cur) == (1, 3)
            data['observed_at'] = '2026-07-30T00:30:00Z'
            schedule = next(r for r in data['responses'] if r['endpoint'] == '/schedule')
            schedule['body']['dates'][0]['games'][0]['teams']['home']['score'] = 9
            copy.write_text(json.dumps(data))
            with pytest.raises(ReplayWithheld, match='Official final schedule'):
                run_fixture(db, copy)
            with db, db.cursor() as cur:
                cur.execute("SELECT count(*) FROM candidate.confirmations WHERE domain='schedule'")
                assert cur.fetchone() == (2,)
                assert compare_finals(cur) == (1, 3)


def test_generation_link_failure_rolls_back_manifest_and_keeps_previous_generation():
    from contextlib import closing
    import psycopg2
    from sync_v3.generation import freeze_generation, verify_generation
    from sync_v3.intelligence_history import record_intelligence

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    day = date(2024, 8, 7)
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            first = freeze_generation(db, day)
            record_intelligence(db, 'readiness', 118, day)
            with owner, owner.cursor() as cur:
                cur.execute("""CREATE FUNCTION candidate.rehearsal_failure() RETURNS trigger LANGUAGE plpgsql AS $$
                               BEGIN RAISE EXCEPTION 'fixture interruption'; END; $$""")
                cur.execute("""CREATE TRIGGER rehearsal_failure BEFORE INSERT ON candidate.generation_inputs
                               FOR EACH ROW EXECUTE FUNCTION candidate.rehearsal_failure()""")
            with pytest.raises(psycopg2.errors.RaiseException, match='fixture interruption'):
                freeze_generation(db, day)
            assert verify_generation(db, first)['snapshots'] == 0
            with db, db.cursor() as cur:
                cur.execute('SELECT digest FROM candidate.generations')
                assert cur.fetchall() == [(first,)]
            with owner, owner.cursor() as cur:
                cur.execute('DROP TRIGGER rehearsal_failure ON candidate.generation_inputs')
            second = freeze_generation(db, day)
            assert verify_generation(db, second)['snapshots'] == 1


def test_generation_event_build_reuses_qualified_inputs_and_revisits_new_receipts(monkeypatch):
    from contextlib import closing
    from sync_v3 import history
    from sync_v3.generation import _build_change_set
    from sync_v3.replay import run_fixture

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    day = date(2026, 11, 21)
    quiet = Path(__file__).parent / 'fixtures/sync_v3/quiet.json'
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            for d in (day-timedelta(days=1), day):
                history.record_workload(db, 'team', 111, d)
            builds = []
            original = history._append
            def counted(cur, subject, entity, represented):
                builds.append(represented)
                return original(cur, subject, entity, represented)
            monkeypatch.setattr(history, '_append', counted)
            old = history._transaction(db, _build_change_set, 'team', 'team', 111, day)
            assert not builds
            run_fixture(db, quiet)
            new = history._transaction(db, _build_change_set, 'team', 'team', 111, day)
            assert builds == [day] and new[1] == old[1] + 1
            assert history._transaction(db, _build_change_set, 'team', 'team', 111, day) == new
            assert builds == [day]


@pytest.mark.parametrize('identity_mode', ['absent', 'incomplete', 'complete'])
def test_isolated_core_selection_and_recovery(tmp_path, identity_mode):
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import closing
    from threading import Barrier
    import psycopg2

    from sync_v3.generation import build_batch, freeze_generation
    from sync_v3.replay import run_fixture
    from sync_v3.selection import SelectionWithheld, select_generation
    from sync_v3.product_reads import read_league, preview_league, read_team_events, read_search, read_game_cards
    from sync_v3.product_reads import read_team_board, read_pitcher, read_team_history, read_pitcher_history
    from sync_v3.editorial_reads import preview_trust, read_event_evidence, read_story_observations, read_trust
    from tests.sync_v3_league_fixture import league_fixtures

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    day, fixtures = league_fixtures(boston_starter=True)
    from copy import deepcopy
    prior_day = day - timedelta(days=1)
    prior = next(f for f in fixtures if f['baseball_date'] == str(prior_day))
    played = next(f for f in fixtures if f['baseball_date'] == str(day))
    prior['team_ids'] = [111]
    for original in played['responses']:
        if original['endpoint'] != '/teams/111/roster' or 'hydrate' in original['params']:
            continue
        if original['params']['rosterType'] == '40Man':
            reserve = deepcopy(original['body']['roster'][0])
            reserve['person'] = dict(id=701235, fullName='Reserve Pitcher')
            retained = deepcopy(reserve)
            retained['person'] = dict(id=701234, fullName='Former Boston Reliever')
            original['body']['roster'].extend([reserve, retained])
        receipt = deepcopy(original)
        receipt['params']['date'] = str(prior_day)
        if receipt['params']['rosterType'] == 'active':
            departed = deepcopy(receipt['body']['roster'][0])
            departed['person'] = dict(id=701234, fullName='Former Boston Reliever')
            receipt['body']['roster'].append(departed)
            transferred = deepcopy(departed)
            transferred['person'] = dict(id=11001, fullName='Rehearsal Arm 11001')
            receipt['body']['roster'].append(transferred)
        prior['responses'].append(receipt)
    def settle(db):
        for _ in range(15):
            batch = build_batch(db, day, 75)
            if not batch['processed']:
                return batch['after']
        pytest.fail('Synthetic league did not settle')

    with isolated_cluster(pg) as (owner, connect):
        source = None
        if identity_mode != 'absent':
            from services.mlb_club_directory import MLB_TEAM_IDS
            from sync_v3.public_identities import load_reference
            with owner, owner.cursor() as cur:
                cur.execute('CREATE TABLE public.pitchers(id integer PRIMARY KEY,mlb_id integer UNIQUE NOT NULL)')
                cur.executemany('INSERT INTO public.pitchers VALUES (%s,%s)',
                                [(team + 9000, team * 100 + 1) for team in MLB_TEAM_IDS])
                cur.execute('INSERT INTO public.pitchers VALUES (8999,701234),(8998,701235),(8997,11100)')
            with owner, owner.cursor() as cur:
                cur.execute('SET TRANSACTION READ ONLY')
                cur.execute('SELECT id,mlb_id FROM public.pitchers ORDER BY id')
                rows = [dict(id=pid, mlb_id=mlb) for pid, mlb in cur]
            source = dict(source='BaseballOS.pitchers', observed_at='2026-08-01T00:00:00+00:00',
                          rows=rows if identity_mode == 'complete' else rows[:-1])
        install(owner, identity_export=source)
        if source:
            with pytest.raises(ValueError, match='Ambiguous'), owner, owner.cursor() as cur:
                load_reference(cur, dict(source, rows=source['rows'][:1] * 2))

        with closing(connect()) as worker, closing(connect(reviewer=True)) as reviewer:
            assert read_league(worker)['status'] == 'no_selected_generation'
            with pytest.raises(psycopg2.errors.InsufficientPrivilege), worker, worker.cursor() as cur:
                cur.execute('DELETE FROM candidate.public_pitcher_ids')
            with pytest.raises(psycopg2.errors.InsufficientPrivilege), reviewer, reviewer.cursor() as cur:
                cur.execute('DELETE FROM candidate.public_identity_export')
            blank = freeze_generation(worker, day)
            preview = preview_league(worker, blank)
            assert len(preview['teams']) == 30 and preview['status'] == 'candidate_preview'
            assert not any(row['team_state']['available'] for row in preview['teams'])
            assert {row['team_state']['reason_code'] for row in preview['teams']} == {'missing_readiness'}
            assert preview['selection_revision'] is None and preview['current_serving_eligible'] is False
            empty = preview_trust(worker, blank)
            assert empty['status'] == 'candidate_preview' and empty['selection_revision'] is None
            assert empty['coverage']['withheld'] == {row['team_id']: 'missing_readiness' for row in preview['teams']}
            assert empty['comparison'] == preview['core_candidate_review']
            assert empty['methods'] == empty['sources'] == []
            assert read_trust(worker)['status'] == 'no_selected_generation'
            assert read_trust(worker, revision=1)['status'] == 'unknown_revision'
            with pytest.raises(ValueError, match='Unknown candidate generation'):
                preview_trust(worker, '0' * 64)
            with pytest.raises(SelectionWithheld):
                select_generation(reviewer, blank, expected_revision=0)
            with pytest.raises(PermissionError):
                select_generation(worker, blank, expected_revision=0)
            with pytest.raises(psycopg2.errors.InsufficientPrivilege), worker, worker.cursor() as cur:
                cur.execute("SELECT candidate.record_core_selection(0,%s,'select')", (blank,))
            with pytest.raises(psycopg2.errors.RaiseException, match='Ineligible'), reviewer, reviewer.cursor() as cur:
                cur.execute("SELECT candidate.record_core_selection(0,%s,'select')", (blank,))
            with pytest.raises(psycopg2.errors.InsufficientPrivilege), reviewer, reviewer.cursor() as cur:
                cur.execute('DELETE FROM candidate.core_selections')
            with reviewer, reviewer.cursor() as cur:
                cur.execute("SELECT has_schema_privilege('public','USAGE'),has_table_privilege('candidate.jobs','UPDATE')")
                assert cur.fetchone() == (False, False)
            path = tmp_path / 'synthetic-day.json'
            for fixture in fixtures:
                path.write_text(json.dumps(fixture))
                run_fixture(worker, path)
            from sync_v3.intelligence_history import record_intelligence
            record_intelligence(worker, 'depth', 111, prior_day)
            first = settle(worker)
            assert select_generation(reviewer, first, expected_revision=0) == 1

            league = read_league(worker)
            assert league['generation'] == first and league['selection_revision'] == 1
            assert len(league['teams']) == len(league['citations']) == 30
            for row in league['teams']:
                assert row['team_state']['available'] and row['team_state']['data_through'] == str(day)
                assert row['orientation']['rest'] == dict(rested_arm_count=0, worked_yesterday_count=1, back_to_back_count=0)
                assert row['orientation']['movement'] is None
            discovery = read_search(worker, 'Boston')
            assert discovery['generation'] == first
            assert discovery['search']['status'] == ('partial' if identity_mode == 'absent' else 'available')
            teams, pitchers, matchups = discovery['search']['groups']
            assert teams['results'][0]['id'] == 111
            if identity_mode == 'complete':
                from unittest.mock import patch

                def broken_directory(cur, generation):
                    cur.execute('SELECT 1 / 0')

                with patch('sync_v3.product_reads._pitcher_directory', broken_directory):
                    partial = read_search(worker, 'Boston')
                results = partial['search']['groups']
                assert partial['pitcher_identity_status'] == 'pitcher_directory_unavailable'
                assert partial['search']['status'] == 'partial' and results[1]['status'] == 'unavailable'
                assert results[0] == teams and results[2] == matchups and matchups['results']
            if identity_mode != 'absent':
                arm = read_search(worker, 'Rehearsal Arm 11101')['search']['groups'][1]['results']
                assert len(arm) == 1 and arm[0]['id'] == 9111 and arm[0]['metadata']['team_id'] == 111
                assert arm[0]['metadata']['position'] == 'P' and arm[0]['metadata']['roster_status'] == 'ACTIVE'
                starter, = read_search(worker, 'Rehearsal Arm 11100')['search']['groups'][1]['results']
                assert starter['id'] == 8997 and starter['metadata']['roster_status'] == 'ACTIVE'
                detail = read_pitcher(worker, starter['id'])
                assert detail['status'] == 'dated_active_pitcher' and detail['sections'] == {}
                assert detail['identity']['team_id'] == 111
                start, = detail['recent_work']['appearances']
                assert start['role'] == 'start' and start['innings_pitched_outs'] == 12
                observation = detail['identity']['roster_observation']
                assert observation['membership'] == 'active' and observation['represented'] == str(day)
                assert len(observation['roster_digest']) == 64
                dated = read_pitcher_history(worker, starter['id'], through_revision=1)['rows'][0]
                assert dated['identity'] == detail['identity'] and dated['events'] == []
            else:
                assert pitchers['status'] == 'unavailable' and pitchers['results'] == []
            assert matchups['status'] == 'available' and len(matchups['results']) == 1
            game = matchups['results'][0]
            assert game['id'] == 10101 and game['metadata']['home']['team_id'] == 110
            assert game['metadata']['away']['team_id'] == 111
            assert game['metadata']['reference_date'] == str(day + timedelta(days=1))
            slate = read_game_cards(worker)
            assert slate['quiet_day'] is False and len(slate['games']) == 15
            assert slate['summary']['game_count'] == 15
            assert 10101 in slate['featured_game_pks'] and slate['lead'] is None
            boston = next(card for card in slate['games'] if card['game_pk'] == 10101)
            assert boston['away']['rotation']['status'] == 'partial'
            assert boston['away']['rotation']['bullpen_innings'] == '5.0'
            from sync_v3.rehearse import verify_slate_matchups
            assert [item['game']['game_pk'] for item in verify_slate_matchups(worker, slate)] == [
                card['game_pk'] for card in slate['games']]
            altered = dict(slate['games'][-1], home=slate['games'][-1]['away'])
            with pytest.raises(RuntimeError, match='selected slate'):
                list(verify_slate_matchups(worker, dict(slate, games=[altered])))
            matchup = read_game_cards(worker, game_pk=game['id'])
            assert matchup['games'] == [next(row for row in slate['games'] if row['game_pk'] == game['id'])]
            assert matchup['generation'] == discovery['generation']
            assert matchup['games'][0]['away']['rest']['worked_yesterday_count'] == 1
            historical = matchup['games'][0]['historical_availability']
            assert historical['status'] == 'available' and matchup['current_serving_eligible'] is False
            assert historical['generation'] == first and historical['current_serving_eligible'] is False
            assert historical['data_through'] == str(day) and historical['reference_date'] == game['metadata']['reference_date']
            assert sum(historical['team_a'].values()) == sum(historical['team_b'].values()) == 1
            comparison = matchup['historical_comparison']
            assert set(comparison['domains']) == {'rest','team_state','availability','workload','rotation','performance','role_rest'}
            assert comparison['domains']['availability'] == historical
            assert comparison['generation'] == first and comparison['selection_revision'] == 1
            assert comparison['status'] == 'partial' and comparison['publication_authority'] is None
            assert comparison['current_serving_eligible'] is False
            assert comparison['game']['game_pk'] == game['id']
            assert comparison['game']['away']['team_id'] == comparison['teams']['team_a']['team_id'] == 111
            assert comparison['game']['home']['team_id'] == comparison['teams']['team_b']['team_id'] == 110
            assert comparison['game']['reference_date'] == comparison['availability_reference_date']
            assert comparison['represented_date'] == str(day)
            rotation_read = matchup['games'][0]['rotation']
            assert rotation_read['status'] == 'partial' and rotation_read['limitations']
            assert rotation_read['team_a']['short_starts'] == 1 and rotation_read['team_a']['bullpen_innings'] == 5.0
            assert rotation_read['team_b']['short_starts'] == 0 and rotation_read['team_b']['bullpen_innings'] == 3.0
            states = matchup['games'][0]['team_state']
            assert states['status'] == 'available'
            for key, club in [('team_a', 111), ('team_b', 110)]:
                assert states[key] == next(row['team_state'] for row in league['teams'] if row['team_id'] == club)
            rest_comparison = matchup['games'][0]['rest']
            assert rest_comparison['status'] == 'available'
            assert rest_comparison['team_a'] == rest_comparison['team_b'] == dict(
                rested_options=0, worked_yesterday=1, back_to_back=0)
            weekly = matchup['games'][0]['workload']
            assert weekly['status'] == 'available'
            assert weekly['team_a'] == dict(window_days=7, relief_appearances=1, pitches=15,
                                            contributing_relievers=1, innings='5.0')
            assert weekly['team_b']['innings'] == '3.0'
            named = matchup['games'][0]['role_rest']
            if identity_mode != 'absent':
                assert named['team_a']['save_work'][0]['pitcher_id'] == 9111
                assert named['team_a']['save_work'][0]['days_since_last_appearance'] == 1
            else:
                assert named['status'] == 'withheld'
            assert read_game_cards(worker, game_pk=9999)['status'] == 'game_outside_represented_slate'
            history = read_team_events(worker, 111)
            assert history['generation'] == league['generation'] and history['represented'] == str(day)
            assert history['pitcher_pattern_population_status'] == 'missing_comparable_bullpen'
            assert any(e['event']['kind'] == 'relief_appearance' for e in history['events'])
            assert all(e['team'] == 111 and len(e['citation']['lineage']) == 2 for e in history['events'])
            boston_change, = (item for item in slate['league_changes']
                              if item['team_id'] == 111 and item['change_class'] == 'new_short_start')
            board_event, = (item for item in history['events'] if item['event']['event_id'] == boston_change['change_id'])
            assert boston_change['source_ref'] == first + '/' + board_event['citation']['facts_digest']
            assert boston_change['game_pks'] == [board_event['event']['game']]
            assert boston_change['change_id'] in boston['away']['change_refs']
            removal, = (item for item in history['events'] if item['event']['kind'] == 'active_roster_removed' and item['event']['player'] == 701234)
            if identity_mode != 'absent':
                old, = read_search(worker, 'Former Boston')['search']['groups'][1]['results']
                assert old['metadata']['historical_departure'] == removal
                assert old['metadata']['position'] == 'P'
                assert old['id'] == 8999 and old['metadata']['team_id'] is None
                assert old['metadata']['roster_status'] == 'UNKNOWN'
                traded = read_pitcher(worker, 9110)
                assert traded['status'] == 'represented' and traded['identity']['team_id'] == 110
                origin = traded['identity']['historical_departure']
                new_club, = read_search(worker, traded['identity']['name'])['search']['groups'][1]['results']
                assert new_club['metadata']['team_id'] == 110
                assert new_club['metadata']['historical_departure'] == origin
                assert origin['team'] == 111 and origin in traded['represented_events'] and origin in history['events']
                assert origin in read_pitcher_history(worker, 9110, through_revision=1)['rows'][0]['events']
                reserve, = read_search(worker, 'Reserve Pitcher')['search']['groups'][1]['results']
                assert reserve['id'] == 8998 and reserve['metadata']['roster_status'] == 'UNKNOWN'
                assert reserve['metadata']['team_id'] is None
                reserve_page = read_pitcher(worker, reserve['id'])
                assert reserve_page['status'] == 'dated_roster_identity' and reserve_page['sections'] == {}
                observation = reserve_page['identity']['roster_observation']
                assert (observation['team_id'], observation['membership'], observation['represented']) == (111, '40Man', str(day))
                assert reserve['metadata']['roster_observation'] == observation
                assert len(observation['roster_digest']) == 64
                historical = read_pitcher_history(worker, 8998, through_revision=1)['rows'][0]
                assert historical['identity'] == reserve_page['identity'] and historical['events'] == []
                departed_page = read_pitcher(worker, old['id'])
                assert departed_page['status'] == 'historical_roster_departure' and departed_page['sections'] == {}
                assert departed_page['identity']['historical_departure'] == removal
                assert departed_page['identity']['roster_observation']['membership'] == '40Man'
                assert departed_page['identity']['team_id'] is None
                assert departed_page['identity']['position'] == old['metadata']['position']
                assert read_pitcher_history(worker, old['id'], through_revision=1)['rows'][0]['events'] == [removal]
            board = read_team_board(worker, 111)
            assert board['what_changed'] == history and board['team'] == next(r for r in league['teams'] if r['team_id'] == 111)
            assert board['active_bullpen'][0]['name'] == 'Rehearsal Arm 11101'
            from sync_v3.rehearse import verify_board_history, verify_editorial_evidence
            journey = verify_board_history(worker, board)
            event = board['what_changed']['events'][0]
            forged = dict(event, citation=dict(event['citation'], input_digest='0' * 64))
            with pytest.raises(RuntimeError, match='History citation'):
                verify_editorial_evidence(worker, board, [forged])
            assert journey['editorial']['event_citations'] == len(board['what_changed']['events'])
            assert journey['editorial']['story_qualification'] == 'game_lines_compared'
            assert journey['editorial']['story_observations'] > 0
            unknown = read_event_evidence(worker, 111, event['event']['event_id'], revision=100)
            assert unknown['status'] == 'unknown_revision' and unknown['evidence'] is None
            assert unknown['selection_revision'] is None
            missing = read_event_evidence(worker, 111, 'unobserved', revision=1)
            assert missing['status'] == 'missing_event' and missing['evidence'] is None
            if identity_mode == 'absent':
                assert journey['verified_pitcher_routes'] == [] and journey['withheld_pitcher_mlb_ids'] == [11101]
            else:
                assert journey['verified_pitcher_routes'] == [dict(mlb_id=11101, public_pitcher_id=9111)]
                assert journey['withheld_pitcher_mlb_ids'] == []
                wrong = dict(board['active_bullpen'][0], mlb_id=11100)
                with pytest.raises(RuntimeError, match='disagrees with the selected Board'):
                    verify_board_history(worker, dict(board, active_bullpen=[wrong]))
                wrong_read = dict(board['active_bullpen'][0], display_read=None)
                with pytest.raises(RuntimeError, match='evidence disagrees'):
                    verify_board_history(worker, dict(board, active_bullpen=[wrong_read]))
            with pytest.raises(RuntimeError, match='Board and History disagree'):
                verify_board_history(worker, dict(board, what_changed=dict(board['what_changed'], events=[])))
            displayed_arm = board['active_bullpen'][0]
            assert displayed_arm['arm_context'] == dict(mode='historical', data_through=str(day), days_rest=None)
            assert displayed_arm['display_read']['key'] == 'limited_read'
            assert displayed_arm['read']['arm_read']['key'] == 'watch_arm'
            hand = displayed_arm['pitch_hand']
            assert hand['value'] == 'L' and hand['basis'] == 'official_person_attribute_at_retrieval'
            assert hand['observed_at'].startswith(str(day + timedelta(days=1)))
            other_hand = read_team_board(worker, 110)['active_bullpen'][0]['pitch_hand']
            assert other_hand['value'] is None and other_hand['reason'] == 'missing_hydrated_profile'
            ledger = board['recent_relief']
            line, = ledger['appearances']
            assert ledger['status'] == 'partial' and len(ledger['gaps']) == 16
            assert set(ledger['gaps'].values()) == {'missing_complete_schedule'}
            assert line['appearance_team_id'] == 111 and line['mlb_id'] == 11101
            windows = board['competitive_workload']['windows']
            assert windows['window_3']['appearances']['value'] == 1
            assert windows['window_3']['outs']['value'] == 15
            assert windows['window_30']['pitches']['value'] is None
            assert 'missing_complete_schedule' in windows['window_30']['pitches']['reason_codes']
            concentration = board['competitive_workload']['concentration_7_day']
            if identity_mode != 'absent':
                assert concentration['top_contributor']['pitcher_id'] == 9111
                assert concentration['top_contributor']['name'] == 'Rehearsal Arm 11101'
                assert concentration['active_current_contribution']['outs'] == 15
                assert concentration['top_3_share'] == 1
            else:
                assert concentration['reason_codes'] == ['contributor_identity_unresolved']
                assert concentration['unresolved_contributor_mlb_ids'] == [11101]
                assert concentration['top_contributor'] is None
            games = board['recent_relief_games']
            assert games['status'] == 'verified_games_only' and games['regular_gaps'] == ledger['gaps']
            game, = games['games']
            assert (game['mlb_game_pk'], game['relief_appearances'], game['innings']) == (line['game_pk'], 1, '5.0')
            assert game['pitches_total'] == line['pitches_thrown'] and game['boxscore_digests'] == line['boxscore_digests']
            assert line['blown_save'] is None and line['strikeouts'] == 2
            assert line['innings_pitched_outs'] == 15 and len(line['boxscore_digests'][0]) == 64
            event = history['events'][0]
            share_input = read_event_evidence(worker, 111, event['event']['event_id'], revision=1)
            assert share_input['evidence'] == event and share_input['trusted_snapshot_id'] is None
            stories = read_story_observations(worker, 111)
            assert stories['qualification'] == 'game_lines_compared' and len(stories['source_games']) == 1
            kinds = {item['type'] for item in stories['observations']['observations']}
            assert {'rotation_pressure', 'concentration_pressure'} <= kinds
            assert stories['coverage']['bullpen_optionality_context'] == 'complete_dated_arm_reads'
            assert stories['coverage']['role_stability_context'] == 'incomplete_comparison_calendar'
            assert stories['coverage']['bullpen_concentration_context'] == 'complete_calendar'
            assert stories['coverage']['league_concentration'] == 'complete_league_calendar'
            assert len(stories['league_concentration_citation']['clubs']) == 30
            pressure, = (item for item in stories['observations']['observations'] if item['type'] == 'concentration_pressure')
            assert pressure['baseline_inputs']['league_team_count_10d'] == 30
            assert pressure['baseline_inputs']['league_top_three_workload_share_10d'] == 100
            pk, = stories['source_games']
            boxscore = next(item['body'] for fixture in fixtures for item in fixture['responses']
                            if item['endpoint'] == f'/game/{pk}/boxscore')
            from hashlib import sha256
            from sync_v3.evidence import encode_json
            assert stories['boxscore_digests'] == {str(pk): [sha256(encode_json(boxscore)).hexdigest()]}
            other = read_story_observations(worker, 110)['observations']
            other_kinds = {item['type'] for item in other['observations']}
            assert 'concentration_pressure' in other_kinds and 'rotation_pressure' not in other_kinds
            trust = read_trust(worker, revision=1)
            assert trust['generation'] == board['generation'] and trust['comparison']['status'] == 'core_comparison_complete'
            assert sum(group['receipts'] for group in trust['sources']) > len(league['teams'])
            assert trust['current_serving_eligible'] is False and trust['trusted_snapshot_id'] is None
            pitcher = read_pitcher(worker, 9111)
            assert pitcher['generation'] == board['generation']
            if identity_mode != 'absent':
                assert board['active_bullpen'][0]['public_pitcher_id'] == 9111
                assert pitcher['identity']['mlb_id'] == 11101 and pitcher['identity']['name'] == arm[0]['primary_label']
                assert pitcher['arm_context'] == displayed_arm['arm_context']
                assert pitcher['display_read'] == displayed_arm['display_read']
                assert pitcher['pitcher'] == dict(id=9111, mlb_id=11101, full_name=arm[0]['primary_label'],
                                                 position='P', team_id=111, team_name='Boston Red Sox',
                                                 team_abbreviation='BOS', throws='L')
                assert pitcher['performance'] == pitcher['sections']['pitcher_profile']['value']['performance']['windows']
                assert pitcher['performance']['recent']['outings'] == 1
                assert pitcher['pitch_hand'] == hand
                work = pitcher['recent_work']
                assert work['appearances'] == ledger['appearances']
                assert work['recent_appearances'] == work['appearances']
                assert work['workload_series'] == [dict(date=str(day), game_pk=pk, pitches=15,
                                                        opponent=line['opponent_abbreviation'])]
                assert 'incomplete evidence' in work['workload_series_note'] and 'absence_sentence' not in work
                deployment = pitcher['historical_deployment']
                assert deployment['generation'] == pitcher['generation'] and deployment['current_serving_eligible'] is False
                assert deployment['context']['pitcher_id'] == 9111 and deployment['through'] == str(day)
                assert deployment['context']['entry_inning']['appearances'] == 1
                assert deployment['context']['entry_inning']['known_appearances'] == 0 and deployment['movement'] is None
                chart = pitcher['season_pitch_characteristics']
                assert chart['through'] == str(day) and chart['months'][0]['outings'] == 1
                assert chart['months'][0]['verified_outings'] == 0 and chart['months'][0]['types'] == []
                assert set(pitcher['sections']) == {'pitcher_profile','pitcher_rest','workload'}
                assert all(e in history['events'] for e in pitcher['represented_events'])
                missing = read_pitcher(worker, 11101)['status']
                assert missing == ('outside_represented_bullpens' if identity_mode == 'complete' else 'public_id_mapping_incomplete')
                if identity_mode == 'incomplete':
                    unmapped = rows[-1]
                    assert read_pitcher(worker, unmapped['id'])['status'] == missing
                    for query in (f"Rehearsal Arm {unmapped['mlb_id']}", 'Rehearsal Arm'):
                        group = read_search(worker, query)['search']['groups'][1]
                        assert group['status'] == 'unavailable' and group['results'] == []
            else:
                assert pitcher['status'] == discovery['pitcher_identity_status']
            refreshed = dict(fixtures[-1], observed_at=f'{day + timedelta(days=3)}T12:00:00Z')
            path.write_text(json.dumps(refreshed))
            run_fixture(worker, path)
            second = settle(worker)
            assert first != second
            with pytest.raises(SelectionWithheld, match='superseded_generation'):
                select_generation(reviewer, first, expected_revision=1)

            # Both reviewers submit the same predecessor: the second sees the committed retry.
            ready = Barrier(2)
            def attempt():
                with closing(connect(reviewer=True)) as other:
                    ready.wait(timeout=15)
                    return select_generation(other, second, expected_revision=1)
            with ThreadPoolExecutor(max_workers=2) as pool:
                attempts = [pool.submit(attempt) for _ in range(2)]
                assert [f.result(timeout=90) for f in attempts] == [2, 2]

            with pytest.raises(RuntimeError, match='History citation'):
                verify_editorial_evidence(worker, dict(board, selection_revision=2), [event])
            assert verify_editorial_evidence(worker, board, [event])['event_citations'] == 1

            with pytest.raises(ValueError, match='predecessor'):
                select_generation(reviewer, first, expected_revision=0, rollback=True)
            with pytest.raises(psycopg2.errors.RaiseException, match='exact previous'):
                select_generation(reviewer, None, expected_revision=2, rollback=True)
            # A database failure after the append must leave readers on generation two.
            with pytest.raises(psycopg2.errors.DivisionByZero), reviewer, reviewer.cursor() as cur:
                cur.execute("SELECT candidate.record_core_selection(2,%s,'rollback')", (first,))
                with worker, worker.cursor() as reader:
                    reader.execute('SELECT generation FROM candidate.core_selections ORDER BY revision DESC LIMIT 1')
                    assert reader.fetchone() == (second,)
                cur.execute('SELECT 1/0')
            assert select_generation(reviewer, first, expected_revision=2, rollback=True) == 3
            assert select_generation(reviewer, first, expected_revision=2, rollback=True) == 3
            recovered = read_league(worker)
            assert dict(recovered, selection_revision=1) == league
            assert dict(read_team_events(worker, 111), selection_revision=1) == history
            page = read_team_history(worker, 111, through_revision=3, limit=2)
            assert [r['action'] for r in page['rows']] == ['rollback', 'select']
            assert [r['generation'] for r in page['rows']] == [first, second]
            assert page['rows'][0]['events'] == history['events'] and page['next_revision'] == 1
            context = page['rows'][0]['calendar_context']
            assert context == page['rows'][1]['calendar_context']
            game_event, = context['events']
            assert game_event['workload'] == dict(starter_outs=12, bullpen_outs=15, short_start=True)
            assert game_event['week'] == dict(final_games=1, verified_games=1, bullpen_outs=15)
            assert game_event['extra_innings'] is None
            older = read_team_history(worker, 111, through_revision=page['next_revision'])
            assert older['rows'][0]['events'] == history['events'] and older['next_revision'] is None
            timeline = read_pitcher_history(worker, 9111, through_revision=3, limit=2)
            assert [item['generation'] for item in timeline['rows']] == [first, second]
            if identity_mode != 'absent':
                restored = timeline['rows'][0]
                assert restored['identity'] == pitcher['identity'] and restored['events'] == pitcher['represented_events']
                assert restored['arm']['read'] == board['active_bullpen'][0]['read']
                assert restored['role']['through'] == str(day) and restored['role']['reference'] == restored['availability_reference']
                assert len(restored['citations']) == 2
            else:
                assert all(item['status'] == discovery['pitcher_identity_status'] for item in timeline['rows'])
            assert read_league(worker, revision=2)['generation'] == second
            assert read_league(worker, revision=20)['status'] == 'unknown_revision'
            with worker, worker.cursor() as cur:
                cur.execute('SELECT revision,predecessor,action,generation FROM candidate.core_selections ORDER BY revision')
                assert cur.fetchall() == [(1,None,'select',first), (2,1,'select',second), (3,2,'rollback',first)]
            assert select_generation(reviewer, second, expected_revision=3) == 4
            path.write_text(json.dumps(dict(refreshed, observed_at=f'{day + timedelta(days=4)}T12:00:00Z')))
            run_fixture(worker, path)
            third = settle(worker)
            ready = Barrier(2)
            def compete(digest, rollback):
                with closing(connect(reviewer=True)) as other:
                    ready.wait(timeout=15)
                    try:
                        return select_generation(other, digest, expected_revision=4, rollback=rollback)
                    except ValueError as exc:
                        assert 'predecessor changed' in str(exc)
                        return None
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(compete, third, False), pool.submit(compete, first, True)]
                assert {f.result(timeout=90) for f in futures} == {5, None}
            with worker, worker.cursor() as cur:
                cur.execute('SELECT count(*),max(revision) FROM candidate.core_selections')
                assert cur.fetchone() == (5,5)


def test_selected_off_day_has_no_games_and_preserves_the_league(tmp_path):
    from contextlib import closing
    from sync_v3.editorial_reads import read_story_observations
    from sync_v3.generation import build_batch
    from sync_v3.product_reads import read_game_cards, read_league, read_pitcher, read_pitcher_history, read_search
    from sync_v3.replay import run_fixture
    from sync_v3.selection import select_generation
    from tests.sync_v3_league_fixture import league_fixtures

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    day, fixtures = league_fixtures(idle_next_day=True)
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as worker, closing(connect(reviewer=True)) as reviewer:
            def assert_empty_reads(requested, expected, decision):
                search = read_search(worker, 'Boston', revision=requested)
                pitcher = read_pitcher(worker, 9111, revision=requested)
                stories = read_story_observations(worker, 111, revision=requested)
                assert search['status'] == pitcher['status'] == stories['qualification'] == expected
                for result in (search, pitcher, stories):
                    assert result['selection_revision'] == decision
                    assert result['generation'] is None and result['current_serving_eligible'] is False
                assert search['search'] is None and stories['observations'] is None

            assert_empty_reads(None, 'no_selected_generation', None)
            assert_empty_reads(1, 'unknown_revision', None)
            path = tmp_path / 'day.json'
            for fixture in fixtures:
                path.write_text(json.dumps(fixture))
                run_fixture(worker, path)
            for _ in range(15):
                batch = build_batch(worker, day, 75)
                if not batch['processed']:
                    break
            else:
                pytest.fail('Off-day candidate did not settle')
            revision = select_generation(reviewer, batch['after'], expected_revision=0)
            league = read_league(worker, revision=revision)
            slate = read_game_cards(worker, revision=revision)
            assert len(league['teams']) == 30 and league['generation'] == slate['generation']
            assert slate['status'] == 'represented' and slate['quiet_day'] is True and slate['games'] == []
            assert read_game_cards(worker, game_pk=10101)['status'] == 'game_outside_represented_slate'
            group = read_search(worker, 'Boston', revision=revision)['search']['groups'][2]
            assert group['results'] == [] and group['status'] != 'unavailable'
            recovered = select_generation(reviewer, None, expected_revision=revision, rollback=True)
            assert_empty_reads(None, 'no_selected_generation', recovered)
            assert_empty_reads(recovered, 'no_selected_generation', recovered)
            assert_empty_reads(recovered + 1, 'unknown_revision', None)
            page = read_pitcher_history(worker, 9111, through_revision=recovered, limit=1)
            assert page['rows'][0]['selection_revision'] == recovered and page['next_revision'] == revision
            assert page['rows'][0]['status'] == 'no_selected_generation'
            assert read_pitcher_history(worker, 9111, through_revision=recovered + 1)['status'] == 'unknown_revision'
            assert read_game_cards(worker, revision=revision) == slate


def test_updated_identity_export_cannot_reassign_a_public_route_or_rewrite_an_older_generation():
    from contextlib import closing
    import psycopg2
    from sync_v3.generation import freeze_generation
    from sync_v3.public_identities import load_reference, verify_reference

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    base = dict(source='BaseballOS.pitchers', observed_at='2024-08-02T10:00:00Z', rows=[dict(mlb_id=12, id=34)])
    newer = dict(base, observed_at='2024-08-03T10:00:00Z', rows=[*base['rows'], dict(mlb_id=13, id=35)])
    day = date(2024, 8, 1)
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            with owner, owner.cursor() as cur:
                original = load_reference(cur, base)
            first = freeze_generation(db, day)
            with owner, owner.cursor() as cur:
                updated = load_reference(cur, newer)
                assert load_reference(cur, dict(newer, rows=list(reversed(newer['rows'])))) == updated
                load_reference(cur, dict(base, observed_at='2024-08-01T10:00:00Z'))
            for row in [dict(mlb_id=12, id=35), dict(mlb_id=14, id=34)]:
                with pytest.raises(psycopg2.errors.ForeignKeyViolation), owner, owner.cursor() as cur:
                    load_reference(cur, dict(newer, observed_at='2024-08-04T10:00:00Z', rows=[row]))
            with pytest.raises(psycopg2.errors.UniqueViolation), owner, owner.cursor() as cur:
                load_reference(cur, dict(newer, rows=base['rows']))
            second = freeze_generation(db, day)
            assert first != second
            with db, db.cursor() as cur:
                cur.execute("SELECT digest,manifest->>'public_identity_export' FROM candidate.generations")
                assert dict(cur) == {first:original, second:updated}
                verify_reference(cur, original)
                verify_reference(cur, updated)


def test_pitcher_chart_preserves_individual_outings_and_missing_counts():
    from sync_v3.appearance_reads import pitcher_recent_work
    from services.public_recent_work import RECENT_LINES_MAX

    def line(n):
        return dict(mlb_id=17, game_pk=900+n, game_number=n if n < 3 else 1,
                    game_date=f'2026-09-{max(2,n):02}', pitches_thrown=None if n == 1 else n,
                    opponent_abbreviation='BOS')

    window = dict(start='2026-09-01', through='2026-09-30', population='all_pitching_appearances', gaps={})
    regular = dict(window, appearances=[line(n) for n in reversed(range(1, 9))])
    postseason = dict(window, appearances=[line(9)])
    work = pitcher_recent_work(regular, postseason)
    assert [r['game_pk'] for r in work['workload_series']] == list(range(901, 910))
    assert work['workload_series'][0]['pitches'] is None
    assert len(work['recent_appearances']) == RECENT_LINES_MAX and work['recent_appearances'][0] == line(9)
    with pytest.raises(ValueError, match='Conflicting'):
        pitcher_recent_work(regular, dict(postseason, appearances=[line(2)]))
    with pytest.raises(ValueError, match='different pitchers'):
        pitcher_recent_work(regular, dict(postseason, appearances=[dict(line(9), mlb_id=18)]))
    empty = pitcher_recent_work(dict(regular, appearances=[], gaps={'2026-09-01': 'missing_complete_schedule'}),
                                dict(postseason, appearances=[]))
    assert empty['workload_series'] == [] and 'No verified outings' in empty['absence_sentence']
    assert 'workload' not in empty


def test_team_relief_games_keep_doubleheaders_missing_measures_and_club_ownership():
    from sync_v3.appearance_reads import team_relief_games

    regular = dict(start='2026-09-01', through='2026-09-30', population='game_side_relief',
                   scope='official_regular_season', gaps={}, appearances=[])
    postseason = dict(regular, scope='verified_postseason_finals', appearances=[])
    for day in range(1, 7):
        regular['appearances'].append(dict(game_pk=day, game_date=f'2026-09-{day:02}', game_number=1,
            opponent_team_id=147, opponent_abbreviation='NYY', home_away='away', appearance_team_id=111,
            final_revision=1, boxscore_digests=['box'],
            mlb_id=123, innings_pitched_outs=2, pitches_thrown=10))
    second = dict(regular['appearances'][-1], game_pk=7, game_number=2, pitches_thrown=None)
    regular['appearances'].append(second)
    games = team_relief_games(111, regular, postseason)['games']
    assert [g['mlb_game_pk'] for g in games] == [6, 7, 5, 4, 3, 2]
    assert games[1]['evidence_status'] == 'partial' and games[1]['pitches_total'] is None
    assert games[1]['innings'] == '0.2' and games[1]['outs_total'] == 2
    with pytest.raises(ValueError, match='another club'):
        team_relief_games(147, regular, postseason)
    with pytest.raises(ValueError, match='Conflicting game'):
        team_relief_games(111, regular, dict(postseason, appearances=[second]))


def test_board_concentration_keeps_a_transferred_pitchers_appearance_with_his_old_club():
    from sync_v3.team_board_windows import board_concentration

    day = date(2026, 7, 29)
    seven = dict(start='2026-07-23', through=str(day), pitches=dict(status='complete', value=40))
    population = dict(team=111, through=str(day), members=[dict(player=100)], reason=None)
    names = {100: dict(public_id=9, name='Active pitcher', team_id=111),
             200: dict(public_id=7, name='Transferred pitcher', team_id=147)}
    lines = [dict(mlb_id=player, appearance_team_id=111, game_date=str(day), pitches_thrown=20,
                  innings_pitched_outs=outs) for player, outs in [(200, None), (100, 3)]]
    result = board_concentration(day, seven, lines, names, population)
    assert [p['pitcher_id'] for p in result['contributors']] == [7, 9]
    assert result['off_active_contribution'] == dict(pitches=20, appearances=1, outs=None)
    assert result['active_current_contribution'] == dict(pitches=20, appearances=1, outs=3)
    disputed = board_concentration(day, seven, lines, names, dict(population, members=[dict(player=200)]))
    assert disputed['reason_codes'] == ['bullpen_membership_unconfirmed']
    assert disputed['active_current_contribution'] is None

    for order in (lines, list(reversed(lines))):
        unresolved = board_concentration(day, seven, order, {}, population)
        assert unresolved['unresolved_contributor_mlb_ids'] == [100, 200]
        assert unresolved['contributors'] == [] and unresolved['top_3_share'] is None


def test_editorial_citation_withholds_ambiguous_events(monkeypatch):
    from sync_v3 import editorial_reads

    evidence = dict(event=dict(event_id='repeated'), citation=dict(input_digest='first'))
    history = dict(status='represented', represented='2026-07-29', generation='edition', selection_revision=1,
                   events=[evidence, dict(evidence, citation=dict(input_digest='second'))])
    monkeypatch.setattr(editorial_reads, 'read_team_events', lambda *args, **kwargs: history)
    receipt = editorial_reads.read_event_evidence(None, 111, 'repeated', revision=1)
    assert receipt['status'] == 'ambiguous_event' and receipt['evidence'] is None
    assert receipt['trusted_snapshot_id'] is None and receipt['current_serving_eligible'] is False


def test_trust_reports_acquisition_only_for_retained_response_bodies():
    from contextlib import closing
    from sync_v3.editorial_reads import preview_trust
    from sync_v3.generation import freeze_generation

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    day = date(2024, 10, 30)
    stamp = datetime(2026, 11, 21, tzinfo=timezone.utc)

    def missing(endpoint, params):
        raise TimeoutError()

    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            run_cycle(db, day, missing, teams=[], clock=lambda: stamp)
            first = freeze_generation(db, day)
            failed = preview_trust(db, first)
            assert failed['sources'] == [dict(outcome='failed', refusal_reason='TimeoutError', receipts=1,
                                              earliest_acquisition=None, latest_acquisition=None)]
            later = stamp + timedelta(days=1)
            run_cycle(db, day, lambda *a, **kw: {}, teams=[], clock=lambda: later)
            invalid = preview_trust(db, freeze_generation(db, day))
            receipt, = invalid['sources']
            assert receipt['outcome'] == 'invalid'
            assert receipt['earliest_acquisition'] == receipt['latest_acquisition'] == later.isoformat()
            assert preview_trust(db, first) == failed
