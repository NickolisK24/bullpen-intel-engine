from datetime import date, timedelta
import json
import os
from pathlib import Path

import pytest

from sync_v3.deployment import club_role_movement
from sync_v3.rehearse import isolated_cluster
from sync_v3.replay import install, run_fixture


def test_candidate_uses_qualified_entry_events_and_preserves_conflicting_evidence():
    from sync_v3.deployment import qualified_entries

    game = {'gamePk': 1, 'gameType': 'R', 'teams': {
        'away': {'team': {'id': 111}, 'score': 1}, 'home': {'team': {'id': 147}, 'score': 2}}}
    def play(index, pitcher, half, inning, home, away):
        return {'about': {'atBatIndex': index, 'isComplete': True, 'inning': inning, 'halfInning': half},
                'matchup': {'pitcher': {'id': pitcher}, 'batter': {'id': 900 + index}},
                'result': {'homeScore': home, 'awayScore': away}}
    plays = [play(0, 10, 'top', 1, 0, 1), play(1, 20, 'bottom', 1, 2, 1),
             play(2, 11, 'top', 2, 2, 1)]
    lines = [{'team_id': club, 'pitcher_mlb_id': pitcher, 'batters_faced': 1}
             for club, pitcher in [(147, 10), (111, 20), (147, 11)]]
    day = date(2024, 8, 7)
    entries, reason = qualified_entries(game, day, lines, plays)
    assert reason is None and entries[147, 11] == (2, 1)
    assert qualified_entries(game, day, lines, plays[1:])[1] == 'incomplete_play_sequence'
    assert qualified_entries(game, day, lines, plays[:-1])[1] == 'play_batter_counts_differ_from_official_lines'
    plays[2]['playEvents'] = [{'isPitch': True}, {'details': {'eventType': 'pitching_substitution'}}]
    assert qualified_entries(game, day, lines, plays)[1] == 'pitching_change_during_plate_appearance'
    del plays[2]['playEvents']
    plays[2]['result']['awayScore'] = 2
    assert qualified_entries(game, day, lines, plays)[1] == 'final_score_mismatch'
    plays[2]['result']['homeScore'] = 3
    assert qualified_entries(game, day, lines, plays)[1] == 'inconsistent_play_order_or_score'


def test_club_movement_requires_both_slates_and_uses_only_recorded_leverage(tmp_path):
    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    template = (Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text()
    start = date(2024, 7, 25)
    end = start + timedelta(days=13)
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        worker = connect()
        try:
            for offset in range(14):
                day = start + timedelta(days=offset)
                # A distinct official game for each played date, with three
                # relief outings in each of the two complete team windows.
                fixture = json.loads(template.replace('2026-07-29', day.isoformat())
                                     .replace('12345', str(12345 + offset)))
                fixture['observed_at'] = f'{day + timedelta(days=1)}T01:00:00Z'
                for source in fixture['responses']:
                    if offset not in (0, 2, 4, 7, 9, 11) and source['endpoint'] == '/schedule':
                        source['body'] = {'dates': [], 'totalGames': 0}
                    if source['endpoint'].endswith('/boxscore'):
                        stats = source['body']['teams']['home']['players']['ID102']['stats']['pitching']
                        stats['leverageIndex'] = 1.6 if offset >= 7 else 0.6
                path = tmp_path / f'{day}.json'
                path.write_text(json.dumps(fixture))
                run_fixture(worker, path)
                if offset == 12:
                    with worker, worker.cursor() as cur:
                        missing = club_role_movement(cur, 147, end)
                        assert missing['gaps'] == {end.isoformat(): ['missing_complete_schedule']}
                        assert missing['profiles'] == []
            with worker, worker.cursor() as cur:
                report = club_role_movement(cur, 147, end)
                assert report['complete_game_coverage']
                arm, = report['profiles']
                assert arm['mlb_player_id'] == 102
                assert arm['movement'] == 'later_or_higher_leverage'
                assert arm['recent']['known_entry_appearances'] == 0
                assert arm['prior']['high_leverage_appearances'] == 0
                assert arm['recent']['high_leverage_appearances'] == 3
                assert len(report['sources']) == 14
                assert not club_role_movement(cur, 111, end)['profiles']
        finally:
            worker.close()


def test_season_baseline_reconciles_each_club_then_excludes_starts_and_future_games():
    from sync_v3.season_deployment import BaselineWithheld, season_deployment_facts

    def body(kind, splits):
        return {'stats': [{'type': {'displayName': kind}, 'group': {'displayName': 'pitching'}, 'splits': splits}]}
    def game(day, club, game_pk, start, outs, hold):
        return {'sport': {'id': 1}, 'player': {'id': 102}, 'game': {'gamePk': game_pk}, 'team': {'id': club},
                'gameType': 'R', 'season': '2024', 'date': day,
                'stat': {'gamesPitched': 1, 'gamesStarted': start, 'outs': outs,
                         'inningsPitched': f'{outs // 3}.{outs % 3}', 'saves': 0, 'holds': hold,
                         'gamesFinished': 0, 'saveOpportunities': 0}}
    start = game('2024-05-02', 111, 11, 1, 18, 0)
    relief = game('2024-08-07', 147, 12, 0, 3, 1)
    future = game('2024-09-01', 147, 13, 0, 4, 1)
    log = body('gameLog', [start, relief, future])
    overall = dict(relief['stat'], gamesStarted=1, gamesPitched=2, outs=21, inningsPitched='7.0')
    totals = body('byDateRange', [{'sport': {'id': 1}, 'team': start['team'], 'stat': dict(start['stat'])},
                                  {'sport': {'id': 1}, 'team': relief['team'], 'stat': dict(relief['stat'])},
                                  {'sport': {'id': 0}, 'team': relief['team'], 'stat': overall}])
    through = date(2024, 8, 7)
    season = season_deployment_facts(102, through, log, totals)
    assert season['season']['games'] == [12] and season['season']['official_starts_excluded'] == 1
    assert season['by_club'][111]['relief_appearances'] == 0
    assert season['recent_14']['holds'] == 1
    assert season['observed_role']['relief_appearances'] == 1
    assert season['observed_role']['recorded_li_appearances'] == 0
    totals['stats'][0]['splits'][0]['stat']['holds'] = 1
    with pytest.raises(BaselineWithheld, match='log_and_dated_totals_disagree'):
        season_deployment_facts(102, through, log, totals)
    log['stats'][0]['splits'].append(relief)
    with pytest.raises(BaselineWithheld, match='game_log_club_or_game_conflict'):
        season_deployment_facts(102, through, log, totals)


def test_pitcher_rehearsal_withholds_a_season_claim_that_conflicts_with_an_official_final(tmp_path):
    from sync_v3.discovery import pitcher_requests
    from sync_v3.season_deployment import pitcher_season_deployment

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    fixture['pitcher_ids'] = [102]
    # Both player endpoints agree on two innings; the official boxscore credits three.
    stats = {'gamesPitched': 1, 'gamesStarted': 0, 'outs': 6, 'inningsPitched': '2.0',
             'saves': 0, 'holds': 0, 'saveOpportunities': 0, 'gamesFinished': 0}
    for request in pitcher_requests(day, [102]):
        params = request.params()
        split = {'sport': {'id': 1}, 'stat': stats, 'team': {'id': 147}}
        if params['stats'] == 'gameLog':
            split.update(player={'id': 102}, date=day.isoformat(), season=str(day.year),
                         gameType='R', game={'gamePk': 12345})
        group = {'type': {'displayName': params['stats']}, 'group': {'displayName': 'pitching'}, 'splits': [split]}
        fixture['responses'].append({'endpoint': request.endpoint, 'params': params, 'body': {'stats': [group]}})
    filename = tmp_path / 'season.json'
    filename.write_text(json.dumps(fixture))
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        worker = connect()
        try:
            run_fixture(worker, filename)
            with worker, worker.cursor() as cur:
                report = pitcher_season_deployment(cur, 102, day)
                assert report['facts'] is None and report['reason'] == 'game_log_and_boxscore_line_conflict'
                assert all(report['sources'].values())
        finally:
            worker.close()


def test_deployment_change_requires_same_qualified_signal_on_adjacent_dates():
    from contextlib import closing
    from services import role_movement
    from services.team_board_public_deployment_context import movement_window_evidence
    from sync_v3.change_history import deployment_changes
    from sync_v3.history import _store
    from sync_v3.intelligence_history import DOMAINS

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated rehearsal')
    end = date(2024, 8, 7)

    def store(cur, day, late, leverage):
        a, b, c, d = role_movement.window_bounds(day)
        recent = movement_window_evidence([('R', 8 if late else 6, leverage)] * 3, a, b)
        prior = movement_window_evidence([('R', 6, leverage)] * 3, c, d)
        profile = dict(mlb_player_id=102, recent=recent, prior=prior,
                       **role_movement.classify_observed_role_movement(recent=recent, prior=prior))
        report = dict(contract=role_movement.CONTRACT, mlb_team_id=118, through=str(day),
                      complete_game_coverage=True, profiles=[profile])
        _store(cur, 'team', 118, day, DOMAINS['roles'][1], report, [])

    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db, db, db.cursor() as cur:
            store(cur, end - timedelta(days=1), False, None)
            store(cur, end, True, None)
            first = deployment_changes(cur, 118, end)
            assert first['status'] == 'complete'
            event, = first['events']
            assert (event['player'], event['previous'], event['current']) == (102, 'stable', 'later_or_higher_leverage')
            store(cur, end, True, 1.6)
            revised = deployment_changes(cur, 118, end)
            assert revised['events'] == [] and revised['status'] == 'partial_deployment_coverage'
            assert deployment_changes(cur, 118, end, revisions=(1, 1)) == first


def test_generation_game_comparison_recounts_official_side_and_outs():
    from sync_v3.cohort import _official_relief

    played = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    box = next(r['body'] for r in played['responses'] if r['endpoint'].endswith('/boxscore'))
    game = dict(game_pk=12345, home=147, away=111)
    facts = dict(game_pk=12345, relief_appearances=[dict(mlb_team_id=147, mlb_player_id=102, outs=9)])
    assert _official_relief(game, facts, box) == 'matched'
    facts['relief_appearances'][0]['outs'] = 8
    assert _official_relief(game, facts, box) == 'official_relief_lines_disagree'
    box['teams']['home']['players']['ID102']['stats']['pitching']['gamesPitched'] = 0
    assert _official_relief(game, facts, box) == 'unverified_relief_appearance'
