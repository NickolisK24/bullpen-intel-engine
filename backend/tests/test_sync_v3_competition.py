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
    from sync_v3.intelligence_history import DOMAINS, rebuild_intelligence, record_intelligence
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
            changes = rebuild_intelligence(db, slate)
            assert len(changes) == 5
            assert all(revision == 2 for _, revision, _ in changes)
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
    calendar = dict(totalGames=16, dates=[regular, dict(date=str(day), totalGames=1, games=[final])])
    path = tmp_path / 'playoff.json'
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            for offset in (2, 1):
                path.write_text(json.dumps(_fixture(day - timedelta(days=offset), [])))
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
