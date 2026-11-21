from datetime import date, timedelta

from sync_v3.rotation import club_rotation


END = date(2024, 8, 7)


def line(pk, player, start, outs, *, pitches=10, club=118):
    return {'game_pk': pk, 'pitcher_mlb_id': player, 'team_id': club, 'game_date': END.isoformat(),
            'games_started': start, 'outs_recorded': outs, 'pitches_thrown': pitches, 'batters_faced': 5}


def calendar(lines):
    result = {END - timedelta(days=i): ({'sources': [i + 1], 'official_lines': []}, None) for i in range(14)}
    result[END][0]['official_lines'] = lines
    return result


def test_doubleheader_opener_and_short_start_have_separate_rotation_attribution():
    cal = calendar([line(101, 1, 1, 3), line(101, 2, 0, 15), line(101, 3, 0, 9),
                    line(102, 4, 1, 12), line(102, 5, 0, 9), line(102, 6, 0, 6, pitches=None),
                    line(102, 9, 1, 24, club=147)])
    report = club_rotation(cal, 118, END)
    opener, short = report['dates'][END.isoformat()]['games']
    assert opener['credited_starter'] == 1 and opener['relief_outs'] == 24
    assert short['relief_pitchers'] == [5, 6] and short['relief_pitches'] is None
    for window in report['windows'].values():
        p = window['pressure']
        assert (p['games_in_window'], p['games_analyzed'], p['opener_bulk_games']) == (2, 1, 1)
        assert (p['starter_outs'], p['short_start_count'], p['bullpen_outs_required']) == (12, 1, 15)
    cal[END - timedelta(days=7)] = None, 'missing_compatible_final'
    windows = club_rotation(cal, 118, END)['windows']
    assert windows['7']['pressure'] and windows['14']['pressure'] is None


def test_shortened_final_keeps_official_work_but_excludes_rotation_assessment():
    report = club_rotation(calendar([line(4, 1, 1, 15)]), 118, END)
    game, = report['dates'][END.isoformat()]['games']
    assert game['shape_reason'] == 'incomplete_outs' and game['starter_outs'] == 15
    assert game['relief_pitchers'] == [] and game['relief_pitches'] == 0
    assert report['windows']['7']['pressure']['excluded_game_reasons'] == {'incomplete_outs': 1}


def test_calendar_gaps_and_disappearing_games_never_create_an_off_day(tmp_path):
    import json
    import os
    from pathlib import Path

    import pytest
    from sync_v3.rehearse import isolated_cluster
    from sync_v3.replay import install, run_fixture
    from sync_v3.schedule_context import club_schedule_context

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    templates = Path(__file__).parent / 'fixtures/sync_v3'
    quiet = (templates / 'quiet.json').read_text()
    played = json.loads((templates / 'played.json').read_text())
    ref = date.fromisoformat(played['baseball_date'])
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        db = connect()
        try:
            for offset in range(-10, 15):
                day = ref + timedelta(days=offset)
                fixture = played if not offset else json.loads(quiet.replace('2026-11-21', str(day)))
                path = tmp_path / f'{day}.json'
                path.write_text(json.dumps(fixture))
                run_fixture(db, path)
                if offset == 13:
                    with db, db.cursor() as cur:
                        gap = club_schedule_context(cur, 111, ref)
                        assert gap['context'] is None and len(gap['gaps']) == 1
            with db, db.cursor() as cur:
                context = club_schedule_context(cur, 111, ref)['context']
                assert context['games_today_count'] == 1
                assert context['next_off_day'] == (ref + timedelta(days=1)).isoformat()
            changed = json.loads(quiet.replace('2026-11-21', str(ref)))
            changed['observed_at'] = f'{ref + timedelta(days=3)}T23:00:00Z'
            path.write_text(json.dumps(changed))
            run_fixture(db, path)
            with db, db.cursor() as cur:
                report = club_schedule_context(cur, 111, ref)
                assert report['context'] is None
                assert report['gaps'] == {ref.isoformat(): 'previous_listing_requires_absence_proof'}
        finally:
            db.close()


def test_postponed_listing_uses_represented_day_without_counting_makeup_twice():
    from sync_v3.schedule_context import _club_rows
    from services.schedule_context import build_team_schedule_context
    prior = END - timedelta(days=1)
    game = {'gamePk': 746602, 'officialDate': END.isoformat(), 'teams': {
        'home': {'team': {'id': 114}}, 'away': {'team': {'id': 109}}},
        'status': {'abstractGameState': 'Final', 'detailedState': 'Postponed', 'statusCode': 'DR'}}
    withdrawn, reason = _club_rows([game], 114, prior)
    assert reason is None and withdrawn[0].game_date == prior and withdrawn[0].official_date == END
    game['status'] = {'abstractGameState': 'Final', 'detailedState': 'Final', 'statusCode': 'F'}
    played, reason = _club_rows([game], 114, END)
    assert reason is None
    report = build_team_schedule_context(114, END, rows=withdrawn + played, team_name_resolver=lambda _: None)
    assert report['games_today_count'] == 1 and report['games_played_last_3_days'] == 0
    game['resumedFromDate'] = prior.isoformat()
    assert _club_rows([game], 114, END)[1] == 'game_date_or_resumption_unresolved'
