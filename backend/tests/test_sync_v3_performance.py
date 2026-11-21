from datetime import date, timedelta

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
    monkeypatch.setattr(group, 'pitcher_season_deployment', lambda *args: {'sources': {'gameLog': 2}, 'reason': None})
    splits = [{'game': {'gamePk': pk}, 'date': day.isoformat(), 'team': {'id': team},
               'stat': {**STATS, 'gamesStarted': 0, 'saves': 0, 'holds': 0, 'saveOpportunities': 0, 'outs': 3}}
              for pk, team, day in [(1, 111, THROUGH - timedelta(days=1)), (2, 118, THROUGH),
                                    (3, 118, THROUGH + timedelta(days=1))]]
    sources = {1: {'roster': [{'position': {'code': '1'}}]}, 2: {'stats': [{'splits': splits}]}}
    monkeypatch.setattr(group, 'replay', lambda cur, source: SimpleNamespace(body=sources[source]))
    official = {'team_id': 118, 'game_pk': 2, 'pitcher_mlb_id': 12, 'games_started': 0,
                'outs_recorded': 3, 'earned_runs': 0, 'hits_allowed': 1, 'walks': 0, 'home_runs_allowed': 0}
    finals = [official]
    monkeypatch.setattr(group, 'regular_day', lambda cur, day, team:
                        ({'official_lines': finals, 'sources': [7]}, None) if day == THROUGH else (None, 'missing'))
    facts['members'].extend([dict(member, id=13, position='O'), dict(member, id=14, position='I')])
    result = group.active_group_performance(None, 118, THROUGH)
    assert result['reason'] is None and result['windows']['season']['appearances'] == 1
    assert result['dates'][THROUGH.isoformat()]['outings'] == [[2, 12]]
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
    from sync_v3.product_reads import _season_comparison, _aligned_performance
    row = dict(innings_pitched_outs=3, earned_runs=1, hits_allowed=1, walks=0, strikeouts=1, batters_faced=4,
               home_runs_allowed=0, inherited_runners=1, inherited_runners_scored=0)

    def side(rows, through=str(THROUGH)):
        return _season_comparison(dict(members=[{'player': 7}], through=through, windows={
            'season': dict(start='2024-01-01', **_aggregate(rows))}))

    full = side([row] * 36)
    incomplete = side([row] * 35 + [dict(row, batters_faced=None)])
    result = _aligned_performance(full, incomplete)
    assert result['status'] == 'partial' and 'k_bb_percent' not in result['team_b']
    assert result['team_a']['k_bb_percent']['value'] == '25.0%'
    assert result['team_b']['active_bullpen_era']['value'] == '9.00'
    assert result['team_b']['sample']['relief_appearances'] == 36
    assert 'descriptive_hr9' not in result['team_a']
    assert _aligned_performance(full, side([]))['status'] == 'withheld'
    assert _aligned_performance(full, side([row]*36, through='2024-08-08'))['status'] == 'withheld'


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
