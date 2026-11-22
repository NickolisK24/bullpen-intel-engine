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
    from sync_v3.generation import build_batch, freeze_generation, GenerationDateWithheld
    from sync_v3.schedule_context import club_schedule_context, retrospective_availability_date

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
                        incomplete = retrospective_availability_date(cur, ref, ref + timedelta(days=11))
                        assert incomplete['availability_reference'] is None
                        assert incomplete['gaps'] == {str(ref + timedelta(days=14)): 'missing_complete_schedule'}
            with db, db.cursor() as cur:
                context = club_schedule_context(cur, 111, ref)['context']
                before = ref - timedelta(days=3)
                assert retrospective_availability_date(cur, before, ref)['availability_reference'] == str(ref)
                played_gap = retrospective_availability_date(cur, before, ref + timedelta(days=1))
                assert played_gap['availability_reference'] == str(ref) and played_gap['dates'][str(ref)]['listed_games'] == 1
                assert context['games_today_count'] == 1
                assert context['next_off_day'] == (ref + timedelta(days=1)).isoformat()
            with pytest.raises(GenerationDateWithheld) as advanced:
                build_batch(db, before, 1, as_of=ref)
            decision = advanced.value.decision
            assert decision['availability_reference'] == str(ref)
            assert decision['basis'] == 'schedule_confirmed_as_of'
            assert decision['reason'] == 'generation_facts_require_recalculation_for_selected_date'
            with pytest.raises(GenerationDateWithheld) as incomplete:
                freeze_generation(db, ref, as_of=ref + timedelta(days=12))
            assert incomplete.value.decision['reason'] == 'schedule_evidence_incomplete'
            with db, db.cursor() as cur:
                cur.execute('SELECT count(*) FROM candidate.generations')
                assert cur.fetchone() == (0,)
                from sync_v3.readiness import review_availability_facts
                report = review_availability_facts(cur, before, ref)
                assert len(report['clubs']) == 30 and report['current_serving_eligible'] is False
                assert all(row['readiness']['reference_date'] == str(ref)
                           and row['readiness']['membership_date'] == str(before)
                           and row['status'] == 'withheld' for row in report['clubs'].values())
                report = review_availability_facts(cur, ref, ref + timedelta(days=12), pitcher=123)
                assert report['reason'] == 'schedule_evidence_incomplete' and 'rest' not in report
            # A quiet schedule with no later listing cannot establish another rest day.
            aligned = freeze_generation(db, ref, as_of=ref + timedelta(days=2))
            assert aligned == freeze_generation(db, ref)
            changed = json.loads(quiet.replace('2026-11-21', str(ref)))
            changed['observed_at'] = f'{ref + timedelta(days=3)}T23:00:00Z'
            path.write_text(json.dumps(changed))
            run_fixture(db, path)
            with db, db.cursor() as cur:
                report = club_schedule_context(cur, 111, ref)
                assert report['context'] is None
                assert report['gaps'] == {ref.isoformat(): 'previous_listing_requires_absence_proof'}
                removed = retrospective_availability_date(cur, before, ref)
                assert removed['availability_reference'] is None and removed['gaps'] == report['gaps']
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


def test_handoff_separates_last_starter_score_and_first_relief_score():
    from sync_v3.handoff import game_handoffs

    def play(i, pitcher, half, inning, home, away, outs, hand='R', bat='L'):
        return {'about': {'atBatIndex': i, 'inning': inning, 'halfInning': half, 'isComplete': True},
                'matchup': {'pitcher': {'id': pitcher}, 'pitchHand': {'code': hand}, 'batSide': {'code': bat}},
                'result': {'homeScore': home, 'awayScore': away}, 'count': {'outs': outs}}
    game = {'teams': {'home': {'team': {'id': 118}}, 'away': {'team': {'id': 111}}}}
    lines = [line(10, 1, 1, 3), line(10, 2, 0, 3), line(10, 3, 1, 3, club=111)]
    plays = [play(0, 1, 'top', 1, 0, 0, 3), play(1, 3, 'bottom', 1, 2, 0, 3),
             play(2, 2, 'top', 2, 2, 0, 1, 'L', 'S')]
    result = game_handoffs(game, lines, plays)
    assert result[118]['last_starter_pa']['runs_for'] == 0
    assert result[118]['last_starter_pa']['outs_after'] == 3
    assert result[118]['first_relief_pa']['runs_for_before'] == 2
    assert result[118]['first_relief_pa']['entry_bases'] is None
    assert result[118]['matchup_sides_by_pitcher'][2] == {'L/?': 1}
    assert result[111]['first_relief_pa'] is None
    plays[0]['count']['outs'] = 1
    assert game_handoffs(game, lines, plays)[118]['last_starter_pa']['outs_after'] is None


def test_series_burden_requires_matching_clubs_unbroken_sequence_and_dated_coverage():
    from sync_v3.rotation import _series_burden
    def game(pk, n, opp=111, order=1):
        return {'game_pk': pk, 'series': {'number': n, 'length': 3, 'home': 118, 'away': opp, 'game_number': order},
                'starter_outs': 15, 'relief_outs': 12, 'relief_pitches': None, 'relief_batters_faced': 16}
    days = {'2024-08-07': {'reason': None, 'games': [game(3, 3, order=2), game(2, 2)]},
            '2024-08-06': {'reason': None, 'games': [game(1, 1)]}}
    result = _series_burden(days)
    series, = result['complete_series']
    assert series['games'] == [1, 2, 3] and series['relief_outs'] == 36 and series['relief_pitches'] is None
    days['2024-08-06']['reason'] = 'missing_compatible_final'
    assert _series_burden(days)['complete_series'] == []
    days['2024-08-06'] = {'reason': None, 'games': [game(1, 1, 147)]}
    assert _series_burden(days)['games_without_complete_series'] == [1, 2, 3]


def test_game_events_keep_doubleheader_appearances_distinct_and_withhold_ambiguous_starts():
    import os
    from contextlib import closing
    from datetime import date, timedelta
    import pytest
    from sync_v3.change_history import game_changes
    from sync_v3.history import _store
    from sync_v3.intelligence_history import DOMAINS
    from sync_v3.rehearse import isolated_cluster
    from sync_v3.replay import install

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for an isolated PostgreSQL server')
    team, end = 118, date(2024, 8, 7)
    prior = end - timedelta(days=1)

    def freeze(cur, day, games, reason=None):
        facts = {'team': team, 'through': day.isoformat(), 'dates': {day.isoformat(): {
            'reason': reason, 'games': games}}}
        return _store(cur, 'team', team, day, DOMAINS['rotation'][1], facts, [])

    game = dict(game_pk=123, relief_pitchers=[102], credited_starter=101, shape_reason=None,
                rotation=dict(short_start=True, starter_outs=12, bullpen_outs_required=15))
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db, db, db.cursor() as cur:
            freeze(cur, prior, [])
            freeze(cur, end, [game, dict(game, game_pk=124, rotation=None, shape_reason='incomplete_outs')])
            first = game_changes(cur, team, end)
            assert first['status'] == 'partial_rotation_evidence'
            assert [(e['kind'], e['game'], e['player']) for e in first['events']] == [
                ('relief_appearance', 123, 102), ('new_short_start', 123, 101), ('relief_appearance', 124, 102)]
            assert len({e['event_id'] for e in first['events']}) == 3
            freeze(cur, prior, [game])
            revised = game_changes(cur, team, end)
            assert [e['game'] for e in revised['events']] == [124]
            freeze(cur, end, [], 'missing_complete_schedule')
            assert game_changes(cur, team, end)['status'] == 'missing_complete_schedule'
            assert game_changes(cur, team, end, revisions=(1, 1)) == first


def test_moved_postponement_cannot_alone_confirm_the_gap(monkeypatch):
    from types import SimpleNamespace
    from sync_v3 import schedule_context as calendar

    first = date(2026, 7, 29)
    as_of = first + timedelta(days=2)
    moved = dict(gamePk=1, officialDate=str(as_of), teams={'home': {'team': {'id': 111}},
                 'away': {'team': {'id': 147}}}, status={'detailedState': 'Postponed', 'statusCode': 'DR'})
    games = {str(first + timedelta(days=1)): [moved]}
    monkeypatch.setattr(calendar, 'latest_qualified_source', lambda cur, ep, params: params.get('startDate'))
    monkeypatch.setattr(calendar, 'missing_listings', lambda *a: {})
    monkeypatch.setattr(calendar, 'replay', lambda cur, day: SimpleNamespace(
        body={'dates': [{'games': games.get(day, [])}]}, retrieved_at=as_of))
    uncertain = calendar.retrospective_availability_date(None, first, as_of)
    assert uncertain['availability_reference'] is None
    assert uncertain['gaps'] == {str(first + timedelta(days=1)): 'postponed_listing_date_unresolved'}
    games[str(as_of)] = [dict(moved, gamePk=2, status={'detailedState': 'Final', 'statusCode': 'F'})]
    confirmed = calendar.retrospective_availability_date(None, first, as_of)
    assert confirmed['availability_reference'] == str(as_of) and confirmed['gaps'] == {}
    from sync_v3 import competition_calendar
    monkeypatch.setattr(calendar, 'latest_qualified_source', lambda cur, ep, params: params.get('startDate', 12))
    monkeypatch.setattr(competition_calendar, 'calendar_games', lambda *_: {
        10: (first + timedelta(days=1), dict(status_state='final'), {})})
    conflict = calendar.retrospective_availability_date(None, first, as_of)
    assert conflict['availability_reference'] is None
    assert conflict['gaps'] == {str(first + timedelta(days=1)): 'competition_calendar_disagrees_with_off_day'}
