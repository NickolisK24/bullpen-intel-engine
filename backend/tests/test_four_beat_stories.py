from datetime import date, timedelta
from types import SimpleNamespace

from services.availability import STATUS_AVAILABLE, STATUS_AVOID, STATUS_MONITOR
from services.four_beat_stories import (
    RULE_HIDDEN_CAPACITY_LOSS,
    RULE_PRESSURE_DISTRIBUTION,
    RULE_SPECIAL_SITUATION,
    RULE_STRESS_TRANSFER,
    RULE_SUSTAINABILITY_QUESTION,
    TeamInputs,
    assemble_story,
    build_four_beat_story_feed,
    compute_team_story_inputs,
    evaluate_team_rules,
    four_beat_stories_enabled,
)


REF = date(2026, 6, 16)


def _pitcher(pid, name, team_id=1, team_name='Test Club', abbr='TST'):
    return SimpleNamespace(
        id=pid,
        full_name=name,
        team_id=team_id,
        team_name=team_name,
        team_abbreviation=abbr,
    )


def _score(pid, risk='LOW', raw=10):
    return SimpleNamespace(pitcher_id=pid, risk_level=risk, raw_score=raw)


def _availability(status):
    return {
        'availability_status': status,
        'confidence': 'high',
        'data_state': 'fresh',
        'reasons': [],
        'limitations': [],
    }


def _record(pitcher, status=STATUS_AVAILABLE, risk='LOW'):
    return {
        'pitcher': pitcher,
        'score': _score(pitcher.id, risk=risk),
        'availability': _availability(status),
        'eligibility': {'eligible': True, 'role': 'Reliever', 'limitations': []},
        'roster_status': {'status': 'ACTIVE', 'is_active_mlb': True},
    }


def _log(pid, days_ago, pitches, *, leverage_index=None):
    return SimpleNamespace(
        pitcher_id=pid,
        game_date=REF - timedelta(days=days_ago),
        pitches_thrown=pitches,
        games_started=0,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        leverage_index=leverage_index,
        save=False,
        hold=False,
        save_situation=False,
    )


def _team_inputs(records, logs_by_pitcher, team=None):
    return TeamInputs(
        team=team or {
            'team_id': 1,
            'team_name': 'Test Club',
            'team_abbreviation': 'TST',
        },
        records=records,
        logs_by_pitcher=logs_by_pitcher,
        reference_date=REF,
    )


def _rule_eval(result, key):
    return next(item for item in result['evaluations'] if item['rule_key'] == key)


def test_stress_transfer_fires_only_when_concentrated_and_thin():
    pitchers = [_pitcher(idx, f'Arm {idx}') for idx in range(1, 6)]
    records = [
        _record(pitchers[0], STATUS_AVAILABLE),
        _record(pitchers[1], STATUS_AVAILABLE),
        _record(pitchers[2], STATUS_MONITOR),
        _record(pitchers[3], STATUS_AVOID),
        _record(pitchers[4], STATUS_MONITOR),
    ]
    concentrated_logs = {
        pitchers[0].id: [_log(pitchers[0].id, 1, 25, leverage_index=1.8), _log(pitchers[0].id, 3, 15, leverage_index=1.8)],
        pitchers[1].id: [_log(pitchers[1].id, 1, 30, leverage_index=1.8)],
        pitchers[2].id: [_log(pitchers[2].id, 2, 20)],
        pitchers[3].id: [_log(pitchers[3].id, 2, 5)],
        pitchers[4].id: [_log(pitchers[4].id, 4, 5)],
    }

    fired = evaluate_team_rules(_team_inputs(records, concentrated_logs))
    assert _rule_eval(fired, RULE_STRESS_TRANSFER)['can_fire'] is True
    assert _rule_eval(fired, RULE_STRESS_TRANSFER)['story']['beats'][0]['key'] == 'signal'

    not_thin = evaluate_team_rules(_team_inputs([
        _record(pitchers[0], STATUS_AVAILABLE),
        _record(pitchers[1], STATUS_AVAILABLE),
        _record(pitchers[2], STATUS_AVAILABLE),
        _record(pitchers[3], STATUS_AVAILABLE),
        _record(pitchers[4], STATUS_MONITOR),
    ], concentrated_logs))
    assert _rule_eval(not_thin, RULE_STRESS_TRANSFER)['can_fire'] is False

    spread_logs = {
        pitcher.id: [_log(pitcher.id, 1, 20)]
        for pitcher in pitchers
    }
    not_concentrated = evaluate_team_rules(_team_inputs(records, spread_logs))
    assert _rule_eval(not_concentrated, RULE_STRESS_TRANSFER)['can_fire'] is False


def test_pressure_distribution_fires_only_when_light_and_broad():
    pitchers = [_pitcher(idx, f'Arm {idx}') for idx in range(1, 7)]
    records = [_record(pitcher, STATUS_AVAILABLE) for pitcher in pitchers]
    broad_logs = {
        pitcher.id: [_log(pitcher.id, 1, 10)]
        for pitcher in pitchers
    }

    fired = evaluate_team_rules(_team_inputs(records, broad_logs))
    assert _rule_eval(fired, RULE_PRESSURE_DISTRIBUTION)['can_fire'] is True
    story = _rule_eval(fired, RULE_PRESSURE_DISTRIBUTION)['story']
    assert any(beat['key'] == 'implication' for beat in story['beats'])

    heavy_records = [_record(pitcher, STATUS_AVAILABLE, risk='LOW') for pitcher in pitchers]
    heavy_records[0] = _record(pitchers[0], STATUS_AVAILABLE, risk='HIGH')
    not_light = evaluate_team_rules(_team_inputs(heavy_records, broad_logs))
    assert _rule_eval(not_light, RULE_PRESSURE_DISTRIBUTION)['can_fire'] is False

    narrow_logs = {
        pitcher.id: [_log(pitcher.id, 1, 10)]
        for pitcher in pitchers[:5]
    }
    not_broad = evaluate_team_rules(_team_inputs(records, narrow_logs))
    assert _rule_eval(not_broad, RULE_PRESSURE_DISTRIBUTION)['can_fire'] is False


def test_dormant_rules_and_special_situation_never_fire():
    pitchers = [_pitcher(idx, f'Arm {idx}') for idx in range(1, 7)]
    result = evaluate_team_rules(_team_inputs(
        [_record(pitcher, STATUS_AVAILABLE) for pitcher in pitchers],
        {pitcher.id: [_log(pitcher.id, 1, 10)] for pitcher in pitchers},
    ))
    for key in (
        RULE_SUSTAINABILITY_QUESTION,
        RULE_HIDDEN_CAPACITY_LOSS,
        RULE_SPECIAL_SITUATION,
    ):
        evaluation = _rule_eval(result, key)
        assert evaluation['status'] == 'dormant'
        assert evaluation['can_fire'] is False
        assert evaluation['reason'] == 'missing_input'
        assert evaluation['story'] is None


def test_beats_fill_slots_or_omit_and_mechanism_stays_associative():
    pitchers = [_pitcher(idx, f'Arm {idx}') for idx in range(1, 7)]
    result = evaluate_team_rules(_team_inputs(
        [_record(pitcher, STATUS_AVAILABLE) for pitcher in pitchers],
        {pitcher.id: [_log(pitcher.id, 1, 10)] for pitcher in pitchers},
    ))
    story = _rule_eval(result, RULE_PRESSURE_DISTRIBUTION)['story']

    for beat in story['beats']:
        assert '{' not in beat['text']
        assert '}' not in beat['text']
        assert beat['skeleton_key']

    mechanism = next(beat['text'] for beat in story['beats'] if beat['key'] == 'mechanism')
    assert 'tends to' in mechanism or 'usually means' in mechanism
    for causal in ('causes', 'proves', 'guarantees', 'will force'):
        assert causal not in mechanism.lower()

    inputs = compute_team_story_inputs(_team_inputs(
        [_record(pitcher, STATUS_AVAILABLE) for pitcher in pitchers],
        {pitcher.id: [_log(pitcher.id, 1, 10)] for pitcher in pitchers},
    ))
    inputs['workload']['participant_count'] = 5
    story_without_evidence = assemble_story(RULE_PRESSURE_DISTRIBUTION, inputs)
    assert story_without_evidence is not None
    assert not any(beat['key'] == 'evidence' for beat in story_without_evidence['beats'])


def test_description_only_teams_suppress_and_feed_count_is_variable_and_ranked():
    stress_pitchers = [_pitcher(idx, f'Stress Arm {idx}', team_id=10, team_name='Stress Club', abbr='STR') for idx in range(1, 6)]
    pressure_pitchers = [_pitcher(idx, f'Pressure Arm {idx}', team_id=20, team_name='Pressure Club', abbr='PRS') for idx in range(11, 17)]
    quiet_pitchers = [_pitcher(idx, f'Quiet Arm {idx}', team_id=30, team_name='Quiet Club', abbr='QUT') for idx in range(21, 26)]
    records = [
        _record(stress_pitchers[0], STATUS_AVAILABLE),
        _record(stress_pitchers[1], STATUS_AVAILABLE),
        *[_record(pitcher, STATUS_MONITOR) for pitcher in stress_pitchers[2:]],
        *[_record(pitcher, STATUS_AVAILABLE) for pitcher in pressure_pitchers],
        *[_record(pitcher, STATUS_AVAILABLE) for pitcher in quiet_pitchers],
    ]
    logs_by_pitcher = {
        stress_pitchers[0].id: [_log(stress_pitchers[0].id, 1, 40)],
        stress_pitchers[1].id: [_log(stress_pitchers[1].id, 1, 30)],
        stress_pitchers[2].id: [_log(stress_pitchers[2].id, 1, 20)],
        stress_pitchers[3].id: [_log(stress_pitchers[3].id, 1, 5)],
        stress_pitchers[4].id: [_log(stress_pitchers[4].id, 1, 5)],
        **{pitcher.id: [_log(pitcher.id, 1, 10)] for pitcher in pressure_pitchers},
        **{pitcher.id: [_log(pitcher.id, 1, 20)] for pitcher in quiet_pitchers},
    }

    feed = build_four_beat_story_feed(records, logs_by_pitcher, reference_date=REF)

    assert feed['count'] == 2
    assert [item['rule_key'] for item in feed['items']] == [
        RULE_STRESS_TRANSFER,
        RULE_PRESSURE_DISTRIBUTION,
    ]
    assert all(item['strength'] >= feed['items'][-1]['strength'] for item in feed['items'])
    assert 'Quiet Club' not in str(feed['items'])


def test_feature_flag_defaults_off():
    assert four_beat_stories_enabled({}) is False
    assert four_beat_stories_enabled({'FOUR_BEAT_STORIES_ENABLED': False}) is False
    assert four_beat_stories_enabled({'FOUR_BEAT_STORIES_ENABLED': True}) is True
