from datetime import date, timedelta

import pytest

from sync_v3.performance import final_performance_counts, performance_line, performance_windows


THROUGH = date(2024, 8, 7)
STATS = {'hits': 1, 'strikeOuts': 2, 'baseOnBalls': 0, 'battersFaced': 4, 'earnedRuns': 0, 'homeRuns': 0,
         'inheritedRunners': 1, 'inheritedRunnersScored': 0}
FINAL = {'outs_recorded': 3, 'home_runs_allowed': 0, 'earned_runs': 0, 'hits_allowed': 1, 'walks': 0}


def test_missing_earlier_final_withholds_season_but_complete_recent_window_qualifies():
    verified = performance_line(THROUGH - timedelta(days=29), final_performance_counts(FINAL, STATS), STATS)
    missing = performance_line(THROUGH - timedelta(days=30), {}, STATS)
    windows = performance_windows(THROUGH, [missing, verified])
    assert windows['season']['outings'] == 2 and windows['recent']['outings'] == 1
    for metric in windows['season']['metrics'].values():
        assert metric['covered'] == 1 and metric['value'] is None and metric['denominator'] is None
    recent = windows['recent']['metrics']
    assert {k: m['value'] for k, m in recent.items()} == {
        'era': '0.00', 'whip': '1.00', 'k_bb_percent': '50.00', 'inherited': '0 of 1', 'hr9': '0.00'}


def test_conflicting_missing_and_impossible_measurements_are_withheld_independently():
    counts = final_performance_counts(dict(FINAL, home_runs_allowed=None), dict(STATS, inheritedRunnersScored=2))
    line = performance_line(THROUGH, counts, dict(STATS, strikeOuts=3, inheritedRunnersScored=2))
    assert line[0].source_conflicts == {'strikeouts': {'game_log': 3, 'boxscore': 2}}
    metrics = performance_windows(THROUGH, [line])['recent']['metrics']
    assert metrics['whip']['value'] == '1.00'
    for k in ('hr9', 'inherited', 'k_bb_percent'):
        assert metrics[k]['covered'] == 0 and metrics[k]['value'] is None
    counts = final_performance_counts(FINAL, dict(STATS, battersFaced=1))
    metrics = performance_windows(THROUGH, [performance_line(THROUGH, counts, {})])['recent']['metrics']
    assert metrics['k_bb_percent']['value'] is None


def test_group_uses_pooled_governed_thresholds_and_preserves_independent_metrics():
    from sync_v3.group_performance import _aggregate
    from services.performance_metrics import METRIC_CURRENT_ACTIVE_PEN_ERA, METRIC_CURRENT_ACTIVE_PEN_WHIP
    row = dict(innings_pitched_outs=3, earned_runs=1, hits_allowed=1, walks=0, strikeouts=1, batters_faced=4,
               home_runs_allowed=0, inherited_runners=1, inherited_runners_scored=0)
    assert _aggregate([dict(row, home_runs_allowed=1)] * 36)['descriptive_hr9'] == {
        'covered': 36, 'outs': 108, 'value': '9.00'}
    metrics = _aggregate([row] * 36)['metrics']
    assert metrics[METRIC_CURRENT_ACTIVE_PEN_ERA]['value'] == '9.00'
    assert metrics[METRIC_CURRENT_ACTIVE_PEN_WHIP]['value'] == '1.00'
    assert metrics['k_bb_percent']['value'] == '25.0%'
    assert metrics['inherited_runner_context']['value'] == '0 of 36 scored'
    metric = _aggregate([row] * 24)['metrics']['k_bb_percent']
    assert metric['value'] is None and metric['reason'] == 'below_minimum_batters_faced'
    partial = _aggregate([row] * 35 + [dict(row, batters_faced=None, hits_allowed=None)])['metrics']
    assert partial['k_bb_percent']['covered'] == 35 and partial['k_bb_percent']['value'] is None
    assert partial[METRIC_CURRENT_ACTIVE_PEN_WHIP]['value'] is None
    assert partial[METRIC_CURRENT_ACTIVE_PEN_ERA]['value'] == '9.00'
    assert _aggregate([row] * 35)['metrics'][METRIC_CURRENT_ACTIVE_PEN_ERA]['reason'] == 'below_minimum_sample'


def test_group_filters_official_club_and_fails_closed_on_population_conflicts(monkeypatch):
    from types import SimpleNamespace
    from sync_v3 import group_performance as group

    member = {'id': 12, 'status': 'A', 'position': '1', 'name': 'Test Arm'}
    facts = {'members': [member]}
    monkeypatch.setattr(group, 'roster_on', lambda *args: (facts, 1))
    profile = {'sources': {'gameLog': 2}, 'reason': None, 'facts': {'uncredited_games': [4]}}
    monkeypatch.setattr(group, 'pitcher_season_deployment', lambda *args: profile)
    splits = [{'game': {'gamePk': pk}, 'date': day.isoformat(), 'team': {'id': team},
               'stat': {**STATS, 'gamesStarted': 0, 'saves': 0, 'holds': 0, 'saveOpportunities': 0, 'outs': 3}}
              for pk, team, day in [(1, 111, THROUGH - timedelta(days=1)), (2, 118, THROUGH),
                                    (3, 118, THROUGH + timedelta(days=1))]]
    splits.append(dict(game={'gamePk': 4}, date=THROUGH.isoformat(), team={'id': 118}, stat={'gamesPitched': 0}))
    sources = {1: {'roster': [{'position': {'code': '1'}}]}, 2: {'stats': [{'splits': splits}]}}
    monkeypatch.setattr(group, 'replay', lambda cur, source: SimpleNamespace(body=sources[source]))
    official = {'team_id': 118, 'game_pk': 2, 'pitcher_mlb_id': 12, 'games_started': 0,
                'outs_recorded': 3, 'earned_runs': 0, 'hits_allowed': 1, 'walks': 0, 'home_runs_allowed': 0}
    finals = [official]
    monkeypatch.setattr(group, 'regular_day', lambda cur, day, team:
                        ({'official_lines': finals, 'sources': [7]}, None) if day == THROUGH else (None, 'missing'))
    facts['members'].extend([dict(member, id=13, position='O'), dict(member, id=14, position='I')])
    # This fixture exercises performance line filtering for an already qualified cohort.
    monkeypatch.setattr(group, 'represented_membership', lambda *args: dict(
        status='represented', basis='latest_ten_official_pitching_appearances', samples={12: dict(games=[1, 2], latest_workload=None)},
        candidate=[12], roles={12: 'Reliever'}))
    result = group.active_group_performance(None, 118, THROUGH)
    assert result['reason'] is None and result['windows']['season']['appearances'] == 1
    assert result['dates'][THROUGH.isoformat()]['outings'] == [[2, 12]]
    assert 'source_conflicts' not in result['dates'][THROUGH.isoformat()]
    official['batters_faced'] = 3
    result = group.active_group_performance(None, 118, THROUGH)
    assert result['dates'][THROUGH.isoformat()]['source_conflicts'] == [
        {'game_pk': 2, 'player': 12, 'fields': {'batters_faced': {'game_log': 4, 'boxscore': 3}}}]
    assert result['windows']['season']['metrics']['k_bb_percent']['value'] is None
    finals.append(dict(official, game_pk=4))
    assert group.active_group_performance(None, 118, THROUGH)['reason'] == 'official_game_log_and_final_population_conflict'
    sources[1]['roster'].append({'position': {'code': '10'}, 'twoWayEligible': True})
    assert group.active_group_performance(None, 118, THROUGH)['reason'] == 'two_way_role_evidence_unresolved'
    sources[1]['roster'][-1] = {'position': {'code': 'Y'}}
    assert group.active_group_performance(None, 118, THROUGH)['reason'] == 'two_way_role_evidence_unresolved'
    sources[1]['roster'].pop()
    member['status'] = None
    blocked = group.active_group_performance(None, 118, THROUGH)
    assert blocked['windows'] is None and blocked['reason'] == 'active_pitching_population_unresolved'


def test_matchup_requires_a_shared_qualified_season_metric_and_matching_window():
    from sync_v3.group_performance import _aggregate
    from sync_v3.product_reads import _performance_window, _aligned_performance
    row = dict(innings_pitched_outs=3, earned_runs=1, hits_allowed=1, walks=0, strikeouts=1, batters_faced=4,
               home_runs_allowed=0, inherited_runners=1, inherited_runners_scored=0)

    def side(rows, through=str(THROUGH)):
        return _performance_window(dict(members=[{'player': 7}], through=through, windows={
            'season': dict(start='2024-01-01', **_aggregate(rows))}), 'season')

    full = side([row] * 36)
    incomplete = side([row] * 35 + [dict(row, batters_faced=None)])
    result = _aligned_performance(full, incomplete)
    assert result['status'] == 'partial' and 'k_bb_percent' not in result['team_b']
    assert result['team_a']['k_bb_percent']['value'] == '25.0%'
    assert result['team_b']['active_bullpen_era']['value'] == '9.00'
    assert result['team_b']['sample']['relief_appearances'] == 36
    assert result['team_b']['sample']['value'] == f'1 active pitcher · 36 relief appearances · 2024-01-01 through {THROUGH}'
    assert 'descriptive_hr9' not in result['team_a']
    assert _aligned_performance(full, side([]))['status'] == 'withheld'
    assert _aligned_performance(full, side([row]*36, through='2024-08-08'))['status'] == 'withheld'


def test_historical_board_keeps_each_performance_window_and_its_declared_sample():
    from sync_v3.group_performance import _aggregate
    from sync_v3.product_reads import _performance_window

    row = dict(innings_pitched_outs=3, earned_runs=1, hits_allowed=1, walks=0, strikeouts=1,
               batters_faced=4, home_runs_allowed=0, inherited_runners=1, inherited_runners_scored=0)
    facts = dict(members=[{'player': 7}], through=str(THROUGH), windows={
        'season': dict(start='2024-01-01', **_aggregate([row] * 36 + [{}])),
        'recent_30': dict(start='2024-07-09', **_aggregate([row] * 36))})
    season, _ = _performance_window(facts, 'season')
    recent, _ = _performance_window(facts, 'recent_30')
    assert set(season) == {'sample'} and season['sample']['relief_appearances'] == 37
    assert recent['sample']['start'] == '2024-07-09' and recent['sample']['relief_appearances'] == 36
    assert recent['k_bb_percent']['value'] == '25.0%' and recent['home_runs_allowed']['value'] == '0'
    assert _performance_window(dict(facts, reason='two_way_role_evidence_unresolved'), 'recent_30') == (None, ())


def test_league_change_retains_the_board_event_identity_and_frozen_revision():
    from sync_v3.product_reads import _league_changes
    row = dict(team_id=118, team_abbreviation='KC', team_state=dict(public_label='Stretched'),
               orientation=dict(movement=dict(previous_label='Vulnerable', since='2024-08-06', event_id='stored-state-event')))
    citations = {118: {'changes': {'facts_digest':'change-digest'}}}
    change, = _league_changes([row], citations, [], 'frozen-generation', '2024-08-07')
    assert change['change_id'] == 'stored-state-event'
    assert change['source_ref'] == 'frozen-generation/change-digest'
    assert change['state_change'] == {'from':'Vulnerable', 'to':'Stretched'}
    row['orientation']['movement'] = None
    assert _league_changes([row], citations, [], 'frozen-generation', '2024-08-07') == []

    facts = {'starter_outs': 11, 'bullpen_outs': 16}
    event = dict(event_id='pinned-short-start', kind='new_short_start', game=712345, facts=facts)
    rotation = [(118, dict(status='partial_rotation_evidence', events=[event]), 'rotation-digest')]
    assert _league_changes([row], citations, rotation, 'generation', '2024-08-07') == []
    rotation[0][1]['status'] = 'complete'
    change, = _league_changes([row], citations, rotation, 'generation', '2024-08-07')
    assert change['change_id'] == event['event_id'] and change['game_pks'] == [712345]
    assert change['headline'] == 'KC recorded a 3.2-inning start.'
    assert change['detail'] == 'The bullpen recorded 5.1 innings.'
    assert change['source_ref'] == 'generation/rotation-digest'


@pytest.mark.parametrize('joined', [True, False])
def test_tonight_requires_bullpen_membership_on_the_roster_moves_present_date(joined):
    from sync_v3.product_reads import _league_changes

    club = dict(team_id=141, team_abbreviation='TOR', orientation=None, team_state=dict(public_label=None))
    event = dict(event_id='official-move', kind='active_roster_added' if joined else 'active_roster_removed',
                 current=joined, previous=not joined, player=599998, pitcher_name='Leonel Campos')
    day = date(2017, 8, 28 if joined else 27)

    def changes(observed, population, move=event):
        evidence = [(141, [move], 'roster-proof', 'bullpen-proof', observed, population)]
        return _league_changes([club], {}, [], 'edition', '2017-08-28', evidence)

    item, = changes(day, {'599998': {}})
    assert item['change_class'] == ('active_bullpen_joined' if joined else 'active_bullpen_left')
    assert item['change_id'] == 'official-move' and item['source_ref'] == 'edition/roster-proof/bullpen-proof'
    assert changes(day, {'453286': {}}) == []
    assert changes(date(2017, 8, 27 if joined else 28), {'599998': {}}) == []
    assert changes(day, {'599998': {}}, dict(event, previous=None)) == []


def test_tonight_patterns_follow_source_identity_and_eligible_start_classes():
    from sync_v3.product_reads import _slate_pitcher_patterns

    base = dict(kind='back_to_back_started', event_id='b2b', player=42, previous=False, current=True)
    events = [base, dict(base, kind='three_in_four_started', event_id='3in4'),
              dict(base, kind='high_pitch_outing_started', event_id='pitches'),
              dict(base, kind='four_in_six_started'), dict(base, kind='back_to_back_ended', current=False),
              dict(base, previous=None), dict(base, player=41)]

    class Rows(list):
        def execute(self, query, params):
            assert params == ('edition', '2017-08-28', 'edition', '2017-08-28')

    rows = Rows([(120, 42, events, 'pattern-input', 'cohort-input')])
    identities = {42: dict(team_id=120, name='Sammy Solís', public_id=None)}
    result = _slate_pitcher_patterns(rows, 'edition', '2017-08-28', identities)
    assert [r['change_id'] for r in result] == ['b2b', '3in4', 'pitches']
    assert all(r['source_ref'] == 'edition/pattern-input/cohort-input' for r in result)
    assert result[0]['headline'] == 'Sammy Solís now has back-to-back usage.'
    assert _slate_pitcher_patterns(rows, 'edition', '2017-08-28', {}) == []
    assert _slate_pitcher_patterns(rows, 'edition', '2017-08-28', {42: dict(team_id=141, name='Sammy Solís')}) == []


def test_transaction_qualification_preserves_dates_and_requires_independent_pitcher_evidence():
    from datetime import date
    from sync_v3.transaction_reads import _qualified_event

    day = date(2017, 8, 27)
    facts = dict(transaction_id=10, player_mlb_id=100, transaction_type_code='CU',
                 transaction_date=str(day), effective_date='2017-08-28', from_team_id=552, to_team_id=120)
    observation = dict(team_id=120, membership='active', represented=str(day), roster_digest='a' * 64)
    pitcher = dict(mlb_id=100, public_id=14, position='P', name='Fixture Pitcher',
                   team_id=120, roster_observation=observation)
    source = dict(acquired_at='2026-11-21T00:00:00+00:00')
    event = _qualified_event(facts, 2, pitcher, day, source)
    assert event['label'] == 'Recalled' and event['pitcher']['pitcher_id'] == 14
    assert event['transaction_date'] == str(day) and event['effective_date'] == '2017-08-28'
    assert event['transaction_revision'] == 2 and event['roster_digest'] == observation['roster_digest']
    for other in (dict(pitcher, public_id=None), dict(pitcher, mlb_id=101),
                  dict(pitcher, roster_observation=dict(observation, represented='2017-08-28')),
                  dict(pitcher, team_id=552, roster_observation=dict(observation, team_id=552)),
                  dict(pitcher, roster_observation=dict(observation, membership='affiliate'))):
        assert _qualified_event(facts, 2, other, day, source) is None
    for change in (dict(to_team_id=118), dict(transaction_type_code='UNKNOWN'),
                   dict(transaction_date='2017-08-26'), dict(participant_position_code='6')):
        assert _qualified_event(dict(facts, **change), 2, pitcher, day, source) is None
