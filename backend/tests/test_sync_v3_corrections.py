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
            second = freeze_generation(db, end)
            with db, db.cursor() as cur:
                assert load(cur, second)['stale_comparisons'] == [['team', 118, 'candidate_readiness_changes_v1']]
                assert load(cur, first)['stale_comparisons'] == [] and load(cur, blank) == empty
            import psycopg2
            with pytest.raises(psycopg2.errors.RaiseException, match='provenance is sealed'), db, db.cursor() as cur:
                cur.execute("""INSERT INTO candidate.history_requests
                               SELECT min(id),'/schedule','{}'::jsonb FROM candidate.workload_history""")
            assert verify_generation(db, first)['snapshots'] == 2
            assert verify_generation(db, blank)['snapshots'] == 0
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
