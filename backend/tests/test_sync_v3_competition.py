from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3 import competition_calendar as competition
from sync_v3.discovery import competition_calendar_request


def game(pk, home, away, day, kind='R'):
    return {'gamePk': pk, 'officialDate': day, 'gameType': kind, 'season': '2024', 'gamesInSeries': 7,
            'status': {'abstractGameState': 'Final', 'detailedState': 'Final', 'statusCode': 'F'},
            'teams': {'home': {'team': {'id': home}, 'score': 4, 'isWinner': True},
                      'away': {'team': {'id': away}, 'score': 2, 'isWinner': False}}}


def season():
    teams = sorted(MLB_TEAM_IDS)
    day = '2024-09-29'
    regular = [game(i + 1, home, away, day) for i, (home, away) in enumerate(zip(teams[::2], teams[1::2]))]
    dates = [{'date': day, 'totalGames': 15, 'games': regular}]
    for n in range(4):
        day = f'2024-10-{22+n}'
        dates.append({'date': day, 'totalGames': 1, 'games': [game(100+n, 119, 147, day, 'W')]})
    return {'totalGames': 19, 'dates': dates}


def test_calendar_rejects_partial_and_conflicting_relistings():
    params = competition_calendar_request(2024).params()
    fixture = season()
    fixture['totalGames'] -= 1
    with pytest.raises(ValueError, match='coverage'):
        competition.calendar_games(params, fixture)
    fixture = season()
    extra = game(100, 119, 147, '2024-10-26', 'W')
    extra['gamesInSeries'] = 5
    fixture['dates'].append({'date': extra['officialDate'], 'totalGames': 1, 'games': [extra]})
    fixture['totalGames'] += 1
    with pytest.raises(ValueError, match='playoff format'):
        competition.calendar_games(params, fixture)


def test_world_series_requires_four_prior_compatible_official_wins(monkeypatch):
    from sync_v3 import evidence, workload

    fixture = season()
    monkeypatch.setattr(evidence, 'latest_qualified_source', lambda cur, ep, params: params.get('startDate', 99))
    by_day = {item['date']: item for item in fixture['dates']}
    monkeypatch.setattr(evidence, 'replay', lambda cur, source: SimpleNamespace(
        body=fixture if source == 99 else {'dates': [by_day[source]]}))
    winning_club = {100: 119, 101: 119, 102: 119, 103: 147}
    def final(cur, listing, day, source):
        pk = listing['gamePk']
        return ([{'team_id': winning_club[pk], 'win': True}], (source, source)), None
    monkeypatch.setattr(workload, '_game_workload', final)
    before = competition.competition_status(None, date(2024, 10, 25))
    assert len(before['decision_sources']) == 3 and before['clubs'][119]['status'] == 'active'
    assert before['reference_slate_source'] == '2024-10-25'
    after = competition.competition_status(None, date(2024, 10, 26))
    assert after['missing_decisions'] == [103]
    assert after['clubs'][119]['status'] == 'undetermined'
    winning_club[103] = 119
    result = competition.competition_status(None, date(2024, 10, 26))
    assert {item['basis'] for item in result['clubs'].values()} == {'world_series_decided'}
    assert len(result['clubs']) == 30 and len(result['decision_sources']) == 4
    assert result['retrospective']


def test_calendar_never_enqueues_season_of_daily_writers():
    from sync_v3.cycle import plan_children
    acquisition = SimpleNamespace(request=competition_calendar_request(2024))
    assert plan_children(None, 1, acquisition, 'historical', None, None) is None


def test_arm_requires_recent_game_identity_and_matching_work_including_prior_club():
    from sync_v3.readiness import _represented_arm

    reference = date(2024, 8, 8)
    split = {'game': {'gamePk': 9}, 'team': {'id': 133}, 'date': '2024-08-06',
             'stat': {'outs': 3, 'numberOfPitches': 14}}
    row = {'pitcher_mlb_id': 42, 'game_pk': 9, 'team_id': 133, 'game_date': '2024-08-06',
           'pitches_thrown': 14, 'outs_recorded': 3}
    arm, reason = _represented_arm(42, [split], [row], reference)
    assert reason is None and arm['games_compared'] == [9]
    assert arm['availability']['inputs']['days_rest'] == 2
    assert _represented_arm(42, [], [row], reference)[1] == 'game_log_and_final_population_conflict'
    assert _represented_arm(42, [split], [dict(row, pitches_thrown=None)], reference)[0] is None
    assert _represented_arm(42, [], [], reference)[1] == 'no_recent_verified_workload'


def test_complete_club_withholds_before_reading_a_roster(monkeypatch):
    from sync_v3 import readiness

    monkeypatch.setattr(readiness, 'competition_status', lambda cur, ref: {
        'calendar_source': 123, 'decision_sources': {}, 'missing_decisions': [], 'reference_slate_source': None,
        'clubs': {111: {'status': 'season_complete', 'basis': 'world_series_decided'}}})
    result = readiness.represented_readiness(None, 111, date(2024, 11, 29))
    assert result['reason'] == 'world_series_decided' and result['team_state'] is None and not result['arms']
    assert result['membership_date'] == '2024-11-29' and result['reference_date'] == '2024-11-30'
    assert result['current_serving_eligible'] is False


def test_missing_or_refused_latest_calendar_withholds_all_clubs(monkeypatch):
    from sync_v3 import evidence
    monkeypatch.setattr(evidence, 'latest_qualified_source', lambda cur, endpoint, params: None)
    result = competition.competition_status(None, date(2024, 11, 30))
    assert result['calendar_source'] is None and result['decision_sources'] == {}
    assert len(result['clubs']) == 30
    assert {club['status'] for club in result['clubs'].values()} == {'undetermined'}


def test_readiness_comparison_does_not_certify_a_withheld_or_misclassified_arm():
    from sync_v3.comparison import compare_readiness

    report = {'team_state': None, 'arms': {7: {'read': None}}}
    assert compare_readiness(report) == {'arm_statuses_compared': 0, 'team_states_compared': 0, 'withheld_arms': 1}
    report['arms'][7]['read'] = {'availability': {'data_state': 'fresh', 'availability_status': 'Available',
                                                'inputs': {'freshness_state': 'fresh', 'pitches_yesterday': 100}}}
    with pytest.raises(ValueError, match='arm status for 7'):
        compare_readiness(report)


def test_snapshot_recovers_missing_calendar_and_preserves_rejected_roster():
    from contextlib import closing
    from datetime import datetime, timedelta, timezone
    import os
    from sync_v3 import evidence, queue
    from sync_v3.cycle import enqueue_requests, plan_children
    from sync_v3.discovery import roster_requests
    from sync_v3.readiness_history import record_readiness, rebuild_readiness
    from sync_v3.rehearse import isolated_cluster
    from sync_v3.replay import install

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for an isolated PostgreSQL server')
    through = date(2024, 9, 29)
    epoch = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            def ingest(req, body, offset):
                at = epoch + timedelta(days=offset)
                with db, db.cursor() as cur:
                    enqueue_requests(cur, [req], at, budget='current', day=through)
                    claimed = queue.claim(cur, at)
                return evidence.execute(db, claimed, lambda *a, **kw: body, clock=lambda: at,
                                        on_received=lambda cur, oid, acq: plan_children(cur, oid, acq, 'current', at, through))

            original = record_readiness(db, 111, through)
            calendar = season()
            next_game = game(93, 111, 147, '2024-09-30')
            calendar['dates'].append({'date': '2024-09-30', 'totalGames': 1, 'games': [next_game]})
            calendar['totalGames'] += 1
            source, status = ingest(competition_calendar_request(2024), calendar, 0)
            assert status == 'received'
            successor, = rebuild_readiness(db, source)
            assert successor[1] == 2 and successor[2] != original[2]
            req = next(r for r in roster_requests(through, [111]) if r.params()['rosterType'] == 'active')
            refused, status = ingest(req, {}, 1)
            assert status == 'invalid'
            latest, = rebuild_readiness(db, refused)
            # A missing roster and a malformed one withhold the same baseball claim.
            # Their independently retained evidence differs.
            assert latest[1] == 3 and latest[2] == successor[2]
            assert record_readiness(db, 111, through) == latest
            with db, db.cursor() as cur:
                cur.execute("""SELECT predecessor,facts->>'reason',facts->>'current_serving_eligible'
                               FROM candidate.workload_history ORDER BY revision""")
                rows = cur.fetchall()
                assert rows[0][0] is None and rows[1][0] == original[0] and rows[2][0] == successor[0]
                assert rows[1][1] == rows[2][1] == 'missing_dated_active_roster'
                assert {row[2] for row in rows} == {'false'}
                cur.execute('SELECT 1 FROM candidate.workload_history_sources WHERE snapshot=%s AND source_id=%s',
                            (latest[0], refused))
                assert cur.fetchone() == (1,)


def test_intelligence_versions_bind_each_domain_to_its_own_inputs():
    from contextlib import closing
    import json
    import os
    from pathlib import Path
    from sync_v3.intelligence_history import DOMAINS, preview_intelligence_rebuild, rebuild_intelligence, record_intelligence
    from sync_v3.rehearse import isolated_cluster
    from sync_v3.replay import install, run_fixture

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for an isolated PostgreSQL server')
    source = Path(__file__).parent / 'fixtures/sync_v3/played.json'
    day = date.fromisoformat(json.loads(source.read_text())['baseball_date'])
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            ids = {'team': 147, 'pitcher': 102, 'game': 12345}
            initial = {domain: record_intelligence(db, domain, ids[subject], day)
                       for domain, (subject, _, _) in DOMAINS.items()}
            with pytest.raises(ValueError, match='official MLB'):
                record_intelligence(db, 'rotation', 9999, day)
            run_fixture(db, source)
            with db, db.cursor() as cur:
                cur.execute("SELECT id FROM candidate.fetches WHERE endpoint='/schedule'")
                slate = cur.fetchone()[0]
            with closing(connect()) as reader:
                reader.set_session(readonly=True)
                first_page = preview_intelligence_rebuild(reader, slate)
                assert first_page['next_after_snapshot_id'] is None
                preview = first_page['scopes']
                assert {row['domain']: row['snapshot_id'] for row in preview} == {
                    domain: initial[domain][0] for domain in ('roles','schedule','game_deployment','rotation','pitcher_rest')}
                assert all(row['represented'] == day.isoformat() and row['revision'] == 1 for row in preview)
                subset = preview_intelligence_rebuild(reader, slate, domains=['rotation'])
                assert subset['scopes'] == [row for row in preview if row['domain'] == 'rotation']
                with pytest.raises(ValueError, match='Unknown receipt'):
                    preview_intelligence_rebuild(reader, 2**62)
            changes = rebuild_intelligence(db, slate)
            assert len(changes) == 5
            assert all(revision == 2 for _, revision, _ in changes)
            subsequent = preview_intelligence_rebuild(db, slate)
            assert {row['snapshot_id'] for row in subsequent['scopes']} == {row[0] for row in changes}
            assert rebuild_intelligence(db, slate) == changes
            with db, db.cursor() as cur:
                cur.execute("SELECT methodology,predecessor FROM candidate.workload_history WHERE revision=2")
                assert dict(cur) == {DOMAINS[d][1]: initial[d][0] for d in ('roles','schedule','game_deployment','rotation','pitcher_rest')}
                cur.execute("SELECT facts FROM candidate.workload_history WHERE subject='game' AND revision=2")
                facts, = cur.fetchone()
                assert facts['game_pk'] == 12345 and facts['relief_appearances'][0]['mlb_player_id'] == 102
                assert facts['reason'] is None and facts['entry_reason'] == 'missing_complete_plays'


def test_core_candidate_review_distinguishes_withholding_and_completed_comparison():
    from services.mlb_club_directory import MLB_TEAM_IDS
    from sync_v3.generation import review_core_candidate

    teams = sorted(MLB_TEAM_IDS)
    coverage = dict(readiness_status='represented_readiness_accounted', compared=teams, withheld={},
                    stale_inputs=[], stale_comparisons=[], missing_snapshot_count=0, slate_reason=None,
                    next_slate_reason=None, missing_active_populations=[])
    roster = dict(multiple_clubs={}, clubs={t: 'matched' for t in teams})
    games = dict(finals={123: 'matched'}, open_games=[])
    assert review_core_candidate(coverage, roster, games)['status'] == 'core_comparison_complete'
    assert review_core_candidate(coverage, roster, dict(games, open_games=[124])) == {
        'status': 'withheld', 'reason_codes': ['represented_slate_still_open']}
    offseason = dict(coverage, readiness_status='all_clubs_season_complete', compared=[], missing_snapshot_count=30)
    assert review_core_candidate(offseason, roster, games)['status'] == 'season_complete_withholding'
    assert review_core_candidate(dict(offseason, stale_inputs=[1]), roster, games)['status'] == 'withheld'


def test_postseason_ledger_requires_a_frozen_verified_decision(tmp_path):
    from contextlib import closing
    from pathlib import Path
    import json
    import os

    from sync_v3.appearance_reads import appearance_ledger, postseason_appearances
    from sync_v3.history import record_workload
    from sync_v3.team_board_windows import board_workload_windows
    from tests.sync_v3_league_fixture import _fixture
    from sync_v3.generation import freeze_generation
    from sync_v3.intelligence_history import record_intelligence
    from sync_v3.rehearse import isolated_cluster
    from sync_v3.replay import install, run_fixture

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for an isolated PostgreSQL server')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    bodies = {r['endpoint']: r['body'] for r in fixture['responses']}
    final = bodies['/schedule']['dates'][0]['games'][0]
    final.update(gameType='W', season=str(day.year), gamesInSeries=7)
    for side, winner in [('home', True), ('away', False)]:
        final['teams'][side].update(isWinner=winner, score=2 if winner else 1)
    box = bodies['/game/12345/boxscore']
    box['teams']['home']['players']['ID100']['stats']['pitching']['wins'] = 1
    regular = season()['dates'][0]
    regular['date'] = '2026-07-26'
    for listing in regular['games']:
        listing.update(officialDate=regular['date'], season=str(day.year))
    postponed = dict(final, status={'abstractGameState': 'Final', 'detailedState': 'Postponed', 'statusCode': 'DR'})
    original_day = day - timedelta(days=1)
    calendar = dict(totalGames=17, dates=[regular, dict(date=str(original_day), totalGames=1, games=[postponed]),
                                          dict(date=str(day), totalGames=1, games=[final])])
    path = tmp_path / 'playoff.json'
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            for offset in (2, 1):
                listing_day = day - timedelta(days=offset)
                path.write_text(json.dumps(_fixture(listing_day, [postponed] if listing_day == original_day else [])))
                run_fixture(db, path)
            def freeze():
                path.write_text(json.dumps(fixture))
                run_fixture(db, path)
                record_workload(db, 'team', 147, day)
                record_intelligence(db, 'readiness', 147, day)
                return freeze_generation(db, day)

            before = freeze()
            fixture['competition'] = True
            fixture['responses'].append(dict(endpoint='/schedule', params=competition_calendar_request(day.year).params(),
                                              body=calendar))
            after = freeze()
            with db, db.cursor() as cur:
                cur.execute('SET TRANSACTION READ ONLY')
                assert postseason_appearances(cur, before, 'team', 147, day, 147)['appearances'] == []
                club = postseason_appearances(cur, after, 'team', 147, day, 147)
                assert club['status'] == 'verified_games_only'
                reliever, = club['appearances']
                assert (reliever['game_pk'], reliever['mlb_id']) == (12345, 102)
                assert len(reliever['boxscore_digests'][0]) == 64
                for generation, count in ((before, None), (after, 1)):
                    workload = appearance_ledger(cur, generation, 'team', 147, day)
                    playoff = postseason_appearances(cur, generation, 'team', 147, day, 147)
                    window = board_workload_windows(cur, generation, 147, day, workload, playoff)['windows']['window_3']
                    assert window['appearances']['value'] == count
                    if count is None:
                        assert 'missing_competition_calendar' in window['appearances']['reason_codes']
                    else:
                        assert window['pitches']['value'] == reliever['pitches_thrown']
                        assert window['outs']['value'] == reliever['innings_pitched_outs']
                starter, = postseason_appearances(cur, after, 'pitcher', 100, day, 147)['appearances']
                assert starter['game_pk'] == reliever['game_pk'] and starter['appearance_team_id'] == 147

            # A later season receipt lists a second final the dated slate and
            # boxes cannot confirm. The first game's verified lines still count.
            from copy import deepcopy
            revised = deepcopy(calendar)
            revised['dates'][-1]['games'].append(dict(final, gamePk=12346))
            revised['dates'][-1]['totalGames'] += 1
            revised['totalGames'] += 1
            fixture['responses'][-1]['body'] = revised
            from datetime import datetime
            fixture['observed_at'] = (datetime.fromisoformat(fixture['observed_at']) + timedelta(hours=1)).isoformat()
            partial = freeze()
            record_intelligence(db, 'readiness', 139, day)
            other = freeze_generation(db, day)
            with db, db.cursor() as cur:
                cur.execute('SET TRANSACTION READ ONLY')
                incomplete = postseason_appearances(cur, partial, 'team', 147, day, 147)
                assert incomplete['status'] == 'partial'
                assert incomplete['gaps'] == {str(day): 'missing_verified_postseason_decision'}
                assert incomplete['appearances'] == club['appearances']
                assert not postseason_appearances(cur, after, 'team', 147, day, 147)['gaps']
                assert not postseason_appearances(cur, other, 'team', 139, day, 139)['gaps']
                assert not postseason_appearances(cur, other, 'pitcher', 100, day, 139, club_only=True)['gaps']
                assert postseason_appearances(cur, other, 'pitcher', 100, day, 139)['gaps'] == incomplete['gaps']


def test_board_window_coverage_requires_matching_schedules_and_verified_playoff_finals():
    from sync_v3.team_board_windows import _coverage_reason

    day = date(2026, 9, 30)
    game = (147, 111, 'F', day.isoformat(), 'final')
    final = {849848: game}

    def reason(daily, season, *, receipts=('daily',), verified=(), year=2026):
        return _coverage_reason(day, year, 'season', receipts, daily, season, set(verified))

    assert reason({}, {}) is None
    assert reason({}, {}, receipts=()) == 'club_calendars_unconfirmed'
    assert reason(final, {}, verified=final) == 'club_calendars_unconfirmed'
    assert reason({}, final) == 'club_calendars_unconfirmed'
    assert reason(final, final, receipts=('a', 'b'), verified=final) == 'club_calendars_unconfirmed'
    assert reason(final, final) == 'club_game_unresolved'
    assert reason(final, final, verified=final) is None
    assert reason({}, {}, year=2027) == 'missing_competition_calendar'
    resumed = {849848: (*game[:3], '2026-09-29', 'final')}
    assert reason(resumed, resumed, verified=final) == 'club_game_unresolved'


@pytest.mark.parametrize(('year', 'round_type', 'admitted'), [
    (2011, 'F', False), (2012, 'F', True), (2017, 'F', True), (2019, 'F', True),
    (2020, 'F', False), (2021, 'F', True), (2022, 'F', False), (2017, 'W', False),
])
def test_historical_single_game_format_is_scoped_by_season_and_round(year, round_type, admitted):
    fixture = season()
    for slate in fixture['dates']:
        slate['date'] = slate['date'].replace('2024', str(year))
        for item in slate['games']:
            item.update(season=str(year), officialDate=slate['date'])
    wild_card = fixture['dates'][1]['games'][0]
    wild_card.update(gameType=round_type, gamesInSeries=1)
    params = competition_calendar_request(year).params()
    if not admitted:
        with pytest.raises(ValueError):
            competition.calendar_games(params, fixture)
        return
    assert competition.calendar_games(params, fixture)[100][1]['games_in_series'] == 1
    fixture['dates'][2]['games'][0].update(gameType='F', gamesInSeries=1)
    with pytest.raises(ValueError, match='Conflicting historical Wild Card games'):
        competition.calendar_games(params, fixture)
    for index, clubs in [(2, (109, 115)), (3, (142, 111))]:
        other = fixture['dates'][index]['games'][0]
        other.update(gameType='F', gamesInSeries=1)
        for side, team in zip(('home', 'away'), clubs):
            other['teams'][side]['team']['id'] = team
    with pytest.raises(ValueError, match='Conflicting historical Wild Card participants'):
        competition.calendar_games(params, fixture)


def test_historical_wild_card_decision_requires_a_verified_game_and_prior_official_winner():
    from services.club_competition_status import classify_club_competition_status

    game_day = date(2017, 10, 3)
    row = dict(game_type='F', game_pk=526475, games_in_series=1, status_state='final',
               game_date=game_day, team_id=142, opponent_team_id=147)
    def outcome(reference, winners, verified=frozenset()):
        return classify_club_competition_status(142, reference, schedule_rows=[row], winner_by_game=winners,
                                                historical_wild_cards=verified).status
    next_day = game_day + timedelta(days=1)
    verified = frozenset([526475])
    assert outcome(next_day, {526475: 147}) == 'undetermined'
    assert outcome(next_day, {}, verified) == 'undetermined'
    assert outcome(game_day, {526475: 147}, verified) == 'active'
    assert outcome(next_day, {526475: 147}, verified) == 'season_complete'
    assert outcome(next_day, {526475: 142}, verified) == 'active'


def test_mixed_postseason_window_binds_off_days_and_both_stages(monkeypatch):
    from sync_v3 import competitive_workload as workload

    through = date(2026, 10, 3)
    games = [game(91, 111, 147, '2026-09-27'), game(92, 111, 147, '2026-10-02', 'F')]
    slates = {g['officialDate']: [{'date': g['officialDate'], 'games': [g]}] for g in games}
    calendar = {'dates': [r for rows in slates.values() for r in rows]}
    missing = set()
    monkeypatch.setattr(workload, 'latest_qualified_source',
                        lambda cur, endpoint, params: None if params['startDate'] in missing else params['startDate'])
    monkeypatch.setattr(workload, 'replay', lambda cur, receipt: SimpleNamespace(
        body=calendar if receipt == 'season' else {'dates': slates.get(receipt, [])}))
    monkeypatch.setattr(workload, '_game_workload', lambda cur, g, day, receipt:
                        (([{'game_pk': g['gamePk']}], [receipt]), None))
    season_data = dict(calendar_source='season', decision_sources={92: [12, 13]})
    full = workload.competitive_window(None, through, season_data)
    assert full['rounds'] == {'R', 'F'}
    assert {r['game_pk']: r['round'] for r in full['lines']} == {91: 'R', 92: 'F'}
    assert len(full['sources']['dates']) == 14 and full['sources']['decisions'] == {92: [12, 13]}
    assert workload.competitive_window(None, through, dict(season_data, decision_sources={})) == {
        'reason': 'verified_postseason_final_required', 'game_pk': 92}
    missing.add('2026-10-01')
    assert workload.competitive_window(None, through, season_data) == {
        'reason': 'missing_dated_schedule', 'gap_date': '2026-10-01'}
    missing.clear()
    slates.pop('2026-09-27')
    assert workload.competitive_window(None, through, season_data) == {
        'reason': 'competitive_calendars_disagree', 'gap_date': '2026-09-27'}


def test_playoff_pitcher_week_qualifies_each_game_side_and_keeps_quiet_arms():
    from sync_v3.competitive_workload import competitive_pitcher_weeks

    through = date(2026, 10, 19)
    dates = {str(through - timedelta(days=i)): i+1 for i in range(14)}

    def line(day, game_pk, team, player, starter, outs, pitches):
        return dict(game_date=str(day), game_pk=game_pk, team_id=team, pitcher_mlb_id=player,
                    games_started=starter, outs_recorded=outs, pitches_thrown=pitches, batters_faced=6)

    # One player was a rotation starter for a prior club, then an opener and a reliever.
    lines = [line(through, 1, 139, 22, 1, 3, 16), line(through, 1, 139, 33, 0, 12, 42),
             line(through-timedelta(days=1), 2, 158, 22, 1, 18, 83),
             line(through-timedelta(days=1), 2, 158, 44, 0, 3, 22),
             line(through-timedelta(days=6), 3, 139, 22, 0, 3, 17),
             line(through-timedelta(days=7), 4, 139, 22, 0, 3, 27)]
    weeks = competitive_pitcher_weeks(dict(sources=dict(dates=dates), lines=lines), [22, 99], through, 123)
    assert weeks[22]['through'] == str(through) and weeks[22]['first'] == '2026-10-13'
    assert weeks[22]['facts']['appearances'] == 2 and weeks[22]['facts']['pitches_thrown'] == 33
    assert weeks[99]['player_observed'] and weeks[99]['facts']['appearances'] == 0
    rest = weeks[22]['rest']
    assert (rest['mlb_player_id'], rest['reference']) == (22, '2026-10-20')
    assert rest['facts']['days_since_last_appearance']['value'] == 1
    assert rest['facts']['last_bullpen_appearance']['value'] == 16
    assert weeks[99]['rest']['facts']['days_since_last_appearance']['value'] is None
    uncertain = [dict(lines[0], games_started=None), *lines[1:]]
    assert competitive_pitcher_weeks(dict(sources=dict(dates=dates), lines=uncertain), [22], through, 123)[22]['facts'] is None


def test_shifted_regular_readiness_recalculates_arm_window_without_changing_membership(monkeypatch):
    from sync_v3 import readiness
    from sync_v3.comparison import compare_readiness

    through = date(2024, 8, 5)
    reference = through + timedelta(days=2)
    first = through - timedelta(days=13)
    calls = []
    lines = [dict(pitcher_mlb_id=7, team_id=111, game_pk=pk, game_date=str(day),
                  pitches_thrown=20, outs_recorded=3) for pk, day in enumerate((first, through), 1)]
    splits = [dict(date=row['game_date'], game=dict(gamePk=row['game_pk']), team=dict(id=111),
                   stat=dict(outs=3, numberOfPitches=20)) for row in lines]

    def population(cur, team, cutoff, *, roster_day):
        assert cutoff == through
        calls.append(roster_day)
        return dict(roster_source=1, profiles={}, reason=None, members=[dict(player=7)],
                    latest_membership_work={7: None}), {7: splits}

    def regular_day(cur, day):
        daily = [row for row in lines if row['game_date'] == str(day)]
        return dict(lines=daily, official_lines=daily, sources=[day.toordinal()]), None

    monkeypatch.setattr(readiness, 'active_group_population', population)
    monkeypatch.setattr(readiness, 'regular_day', regular_day)
    competition = dict(clubs={111: dict(status='active', last_final_game_type='R')},
                       calendar_source=1, decision_sources={}, missing_decisions=[],
                       reference_slate_source=2, postseason_started=False)
    result = readiness._club_readiness(None, 111, through, reference, competition)
    assert calls == [through] and result['reference_date'] == str(reference)
    arm = result['arms'][7]['read']
    assert arm['games_compared'] == [2]
    assert arm['availability']['inputs']['pitches_yesterday'] == 0
    assert arm['availability']['inputs']['days_rest'] == 2
    assert compare_readiness(result)['arm_statuses_compared'] == 1


def test_recovery_only_requests_scoped_dated_postseason_evidence(monkeypatch):
    from copy import deepcopy
    from sync_v3 import eligibility_recovery as recovery

    calendar = season()
    schedule_day = date(2024, 10, 22)
    unrelated = game(140, 111, 108, '2024-10-05', 'D')
    unrelated['gamesInSeries'] = 5
    calendar['dates'].append({'date': '2024-10-05', 'totalGames': 1, 'games': [unrelated]})
    calendar['totalGames'] += 1
    original = calendar['dates'][1]['games'][0]
    daily = deepcopy(original)
    captured = {1: SimpleNamespace(request=competition_calendar_request(2024), body=calendar),
                2: SimpleNamespace(body={'dates': [{'games': [daily]}]})}
    monkeypatch.setattr(recovery.evidence, 'replay', lambda cur, oid: captured[oid])
    monkeypatch.setattr(recovery.evidence, 'latest_qualified_source', lambda *a: 2)
    report = dict(calendar_source=1, missing_decisions=[100, 101, 140])
    requests = []

    def missing(day, endpoint, params):
        if endpoint == '/schedule':
            return False
        requests.append((day, endpoint))
        return True

    recovery._missing_postseason_decisions(None, 147, schedule_day, report, missing)
    assert requests == [(schedule_day, '/game/100/boxscore')]
    daily['teams']['home']['score'] += 1
    requests.clear()
    recovery._missing_postseason_decisions(None, 147, schedule_day, report, missing)
    assert not requests
