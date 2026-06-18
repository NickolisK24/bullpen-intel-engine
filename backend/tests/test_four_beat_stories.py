from datetime import date, timedelta
from types import SimpleNamespace

from services.availability import STATUS_AVAILABLE, STATUS_AVOID, STATUS_MONITOR
from services.four_beat_stories import (
    BEAT_CONTEXT,
    LEAD_AVAILABILITY_DEEP,
    LEAD_AVAILABILITY_THIN,
    LEAD_CONCENTRATION_SHAPE,
    LEAD_DEEP_INTACT,
    LEAD_FATIGUE_LOAD,
    LEAD_TRUST_LANE_ABSENCE,
    LEAD_TRUST_LANE_DEPTH,
    LEAD_WORKLOAD_LIGHT,
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
from services.team_story_facts import CAPABILITY as STORY_FACT_LAYER_CAPABILITY
from services.team_story_narrative import (
    FORBIDDEN_PUBLIC_LABELS,
    INTERNAL_TAXONOMY_TERMS,
    narrative_contains_forbidden_language,
)
from services.team_bullpen_shape import build_team_bullpen_shape


REF = date(2026, 6, 16)

CAPACITY_CONTEXT_MARKERS = (
    'fewer usable arms',
    'bullpen room',
    'bullpen looks thinner',
    'available group is smaller',
    'fewer places to turn',
    'less usable depth',
    'short on usable arms',
    'already short on usable arms',
    'available group is already thin',
    'repeat innings',
    'heavy innings keep finding',
)

CAPACITY_FALLBACK_MARKERS = (
    'fewer usable arms',
    'bullpen room',
    'bullpen looks thinner',
    'available group is smaller',
    'fewer places to turn',
    'less usable depth',
)

ROTATION_CONTEXT_MARKERS = (
    'recent workload picture is adding pressure',
    'carrying more of the workload',
    'extra outs have been finding',
    'covering more of the game',
    'landing on the pen',
)

STABILITY_CONTEXT_MARKERS = (
    'group has not looked the same',
    'moving in and out of the picture',
    'not looked exactly the same',
    'innings have been moving around',
    'bullpen mix has been shifting',
)

ENVIRONMENT_INTRO_MARKERS = (
    'this is not one clean issue',
    'more than one thing tightening the picture',
    'not just one part of the pen',
)


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


def _record(pitcher, status=STATUS_AVAILABLE, risk='LOW', is_active_mlb=True):
    return {
        'pitcher': pitcher,
        'score': _score(pitcher.id, risk=risk),
        'availability': _availability(status),
        'eligibility': {'eligible': True, 'role': 'Reliever', 'limitations': []},
        'roster_status': {'status': 'ACTIVE' if is_active_mlb else 'IL_15', 'is_active_mlb': is_active_mlb},
    }


def _log(pid, days_ago, pitches, *, leverage_index=None, save=False, hold=False, save_situation=False):
    return SimpleNamespace(
        pitcher_id=pid,
        game_date=REF - timedelta(days=days_ago),
        pitches_thrown=pitches,
        games_started=0,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        leverage_index=leverage_index,
        save=save,
        hold=hold,
        save_situation=save_situation,
    )


def _team_inputs(
    records,
    logs_by_pitcher,
    team=None,
    season_era_by_team=None,
    capacity_by_team=None,
    rotation_support_by_team=None,
    bullpen_stability_by_team=None,
    bullpen_environment_by_team=None,
):
    return TeamInputs(
        team=team or {
            'team_id': 1,
            'team_name': 'Test Club',
            'team_abbreviation': 'TST',
        },
        records=records,
        logs_by_pitcher=logs_by_pitcher,
        reference_date=REF,
        season_era_by_team=season_era_by_team,
        capacity_by_team=capacity_by_team,
        rotation_support_by_team=rotation_support_by_team,
        bullpen_stability_by_team=bullpen_stability_by_team,
        bullpen_environment_by_team=bullpen_environment_by_team,
    )


def _rule_eval(result, key):
    return next(item for item in result['evaluations'] if item['rule_key'] == key)


def _story_text(story):
    return ' '.join([
        story['title'],
        *(beat['text'] for beat in story['beats'] if beat['key'] != 'signal'),
    ])


def _ranked_era(team_id=1, *, era=2.75, rank=5, total=30, strong=True, solid=True):
    return {
        team_id: {
            'team_id': team_id,
            'era': era,
            'innings_outs': 120,
            'earned_runs': 12,
            'rank': rank,
            'rank_total': total,
            'strong_results': strong,
            'solid_results': solid,
        }
    }


def _thin_concentrated_team_inputs(**kwargs):
    pitchers = [_pitcher(idx, f'Context Arm {idx}') for idx in range(1, 6)]
    records = [
        _record(pitchers[0], STATUS_AVAILABLE),
        _record(pitchers[1], STATUS_AVAILABLE),
        _record(pitchers[2], STATUS_MONITOR),
        _record(pitchers[3], STATUS_AVOID),
        _record(pitchers[4], STATUS_MONITOR),
    ]
    logs = {
        pitchers[0].id: [_log(pitchers[0].id, 1, 40)],
        pitchers[1].id: [_log(pitchers[1].id, 1, 30)],
        pitchers[2].id: [_log(pitchers[2].id, 1, 20)],
        pitchers[3].id: [_log(pitchers[3].id, 1, 5)],
        pitchers[4].id: [_log(pitchers[4].id, 1, 5)],
    }
    return _team_inputs(records, logs, **kwargs)


def _capacity_context(status='elevated', *, unavailable_pct=32, limitations=None, unknown_pct=0):
    return {
        1: {
            'capability': 'bullpen_capacity_intelligence_v1',
            'capacity_loss': {
                'status': status,
                'unavailable_capacity_pct': unavailable_pct,
                'unknown_limited_read_capacity_pct': unknown_pct,
                'limitations': list(limitations or []),
                'definitions': {
                    'available_capacity_pct': (
                        'Capacity not classified as fully unavailable; this is not the same as fully clean availability.'
                    ),
                },
            },
            'trust_capacity_loss': {
                'trust_arms_available': 2,
                'trust_arms_total': 3,
                'limitations': [],
            },
        }
    }


def _rotation_context(status='heavy_pressure', *, limitations=None, games_analyzed=5):
    return {
        1: {
            'capability': 'rotation_support_pressure_v1',
            'status': status,
            'games_analyzed': games_analyzed,
            'limitations': list(limitations or []),
            'source_limitations': [
                'Credited starters are used as recorded; opener/bulk-reliever roles are not separately inferred.',
            ],
        }
    }


def _stability_context(status='moderate_churn', *, limitations=None, recently_used=7):
    return {
        1: {
            'capability': 'bullpen_stability_v1',
            'status': status,
            'recently_used_bullpen_count': recently_used,
            'new_or_reintroduced_arm_count': 2,
            'limitations': list(limitations or []),
            'source_limitations': [
                'Bullpen stability is based on usage patterns and does not imply transaction activity.',
            ],
        }
    }


def _environment_context(status='multi_source_pressure', *, sources=None, limitations=None):
    return {
        1: {
            'capability': 'bullpen_environment_v1',
            'status': status,
            'primary_pressure_sources': sources or ['capacity_loss', 'rotation_support_pressure'],
            'context_flags': ['source_limitations_present'],
            'limitations': list(limitations or []),
            'source_limitations': [
                'Underlying source caveats remain attached to the source layers.',
            ],
        }
    }


def _split_pitch_total(total):
    first = total // 3
    second = total // 3
    return [first, second, total - first - second]


def _near_collision_stress_team(team_id, team_name, abbr, names, pitch_totals, available_count):
    pitchers = [
        _pitcher(team_id * 100 + idx, name, team_id=team_id, team_name=team_name, abbr=abbr)
        for idx, name in enumerate(names, start=1)
    ]
    records = [
        _record(
            pitcher,
            STATUS_AVAILABLE if idx < available_count else STATUS_MONITOR,
        )
        for idx, pitcher in enumerate(pitchers)
    ]

    logs_by_pitcher = {}
    for idx, (pitcher, total) in enumerate(zip(pitchers, pitch_totals)):
        if idx < 2:
            logs_by_pitcher[pitcher.id] = [
                _log(pitcher.id, days_ago + 1, pitches, leverage_index=1.8)
                for days_ago, pitches in enumerate(_split_pitch_total(total))
            ]
        else:
            logs_by_pitcher[pitcher.id] = [_log(pitcher.id, 1, total)]

    return _team_inputs(
        records,
        logs_by_pitcher,
        team={
            'team_id': team_id,
            'team_name': team_name,
            'team_abbreviation': abbr,
        },
    )


def _fixture_team(team_id, team_name, abbr, pitch_totals, *, available_count=None, high_risk_indices=(), trust_indices=()):
    pitchers = [
        _pitcher(team_id * 100 + idx, f'{abbr} Arm {idx}', team_id=team_id, team_name=team_name, abbr=abbr)
        for idx in range(1, len(pitch_totals) + 1)
    ]
    if available_count is None:
        available_count = len(pitchers)
    records = []
    for idx, pitcher in enumerate(pitchers):
        records.append(_record(
            pitcher,
            STATUS_AVAILABLE if idx < available_count else STATUS_MONITOR,
            risk='HIGH' if idx in high_risk_indices else 'LOW',
        ))

    logs_by_pitcher = {}
    for idx, (pitcher, total) in enumerate(zip(pitchers, pitch_totals)):
        if idx in trust_indices:
            first = total // 2
            logs_by_pitcher[pitcher.id] = [
                _log(pitcher.id, 1, first, leverage_index=1.8, save=True, save_situation=True),
                _log(pitcher.id, 3, total - first, leverage_index=1.7),
            ]
        else:
            logs_by_pitcher[pitcher.id] = [_log(pitcher.id, 1, total)]
    return pitchers, records, logs_by_pitcher


def _merge_logs(*groups):
    merged = {}
    for group in groups:
        merged.update(group)
    return merged


def _bullpen_era(team_id, team_name, abbr, era, earned_runs=20):
    innings_outs = max(1, round((earned_runs * 27) / era))
    return {
        'team_id': team_id,
        'team_name': team_name,
        'team_abbreviation': abbr,
        'era': era,
        'innings_outs': innings_outs,
        'earned_runs': earned_runs,
    }


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


def test_era_rules_are_live_but_fail_closed_without_era_and_special_situation_is_dormant():
    pitchers = [_pitcher(idx, f'Arm {idx}') for idx in range(1, 7)]
    result = evaluate_team_rules(_team_inputs(
        [_record(pitcher, STATUS_AVAILABLE) for pitcher in pitchers],
        {pitcher.id: [_log(pitcher.id, 1, 10)] for pitcher in pitchers},
    ))
    for key in (RULE_SUSTAINABILITY_QUESTION, RULE_HIDDEN_CAPACITY_LOSS):
        evaluation = _rule_eval(result, key)
        assert evaluation['status'] == 'live'
        assert evaluation['can_fire'] is False
        assert evaluation['story'] is None

    special = _rule_eval(result, RULE_SPECIAL_SITUATION)
    assert special['status'] == 'dormant'
    assert special['can_fire'] is False
    assert special['reason'] == 'missing_input'
    assert special['story'] is None


def test_sustainability_question_fires_only_when_strong_era_and_heavy_workload():
    pitchers = [_pitcher(idx, f'Heavy Arm {idx}') for idx in range(1, 7)]
    records = [_record(pitcher, STATUS_AVAILABLE) for pitcher in pitchers]
    heavy_logs = {
        pitcher.id: [_log(pitcher.id, 1, 35)]
        for pitcher in pitchers
    }

    fired = evaluate_team_rules(_team_inputs(
        records,
        heavy_logs,
        season_era_by_team=_ranked_era(rank=4, strong=True, solid=True),
    ))
    sustainability = _rule_eval(fired, RULE_SUSTAINABILITY_QUESTION)

    assert sustainability['can_fire'] is True
    assert sustainability['story']['rule_key'] == RULE_SUSTAINABILITY_QUESTION
    assert '2.75 season ERA' in _story_text(sustainability['story'])
    assert 'leaning on it hard tonight' in sustainability['story']['title']

    not_strong = evaluate_team_rules(_team_inputs(
        records,
        heavy_logs,
        season_era_by_team=_ranked_era(rank=12, strong=False, solid=True),
    ))
    assert _rule_eval(not_strong, RULE_SUSTAINABILITY_QUESTION)['can_fire'] is False

    light_logs = {
        pitcher.id: [_log(pitcher.id, 1, 10)]
        for pitcher in pitchers
    }
    not_heavy = evaluate_team_rules(_team_inputs(
        records,
        light_logs,
        season_era_by_team=_ranked_era(rank=4, strong=True, solid=True),
    ))
    assert _rule_eval(not_heavy, RULE_SUSTAINABILITY_QUESTION)['can_fire'] is False


def test_hidden_capacity_loss_fires_only_when_solid_era_and_depleted_depth():
    pitchers = [_pitcher(idx, f'Thin Arm {idx}') for idx in range(1, 8)]
    records = [
        _record(pitchers[0], STATUS_AVAILABLE),
        _record(pitchers[1], STATUS_AVAILABLE),
        *[_record(pitcher, STATUS_MONITOR) for pitcher in pitchers[2:]],
    ]
    spread_logs = {
        pitcher.id: [_log(pitcher.id, 1, 20)]
        for pitcher in pitchers[:5]
    }

    fired = evaluate_team_rules(_team_inputs(
        records,
        spread_logs,
        season_era_by_team=_ranked_era(rank=15, strong=False, solid=True),
    ))
    hidden = _rule_eval(fired, RULE_HIDDEN_CAPACITY_LOSS)

    assert hidden['can_fire'] is True
    assert hidden['story']['rule_key'] == RULE_HIDDEN_CAPACITY_LOSS
    assert "tonight's usable depth is thin" in hidden['story']['title']
    assert '2 of 7 arms Available' in _story_text(hidden['story'])

    not_solid = evaluate_team_rules(_team_inputs(
        records,
        spread_logs,
        season_era_by_team=_ranked_era(rank=21, strong=False, solid=False),
    ))
    assert _rule_eval(not_solid, RULE_HIDDEN_CAPACITY_LOSS)['can_fire'] is False

    not_depleted = evaluate_team_rules(_team_inputs(
        [_record(pitcher, STATUS_AVAILABLE) for pitcher in pitchers],
        spread_logs,
        season_era_by_team=_ranked_era(rank=15, strong=False, solid=True),
    ))
    assert _rule_eval(not_depleted, RULE_HIDDEN_CAPACITY_LOSS)['can_fire'] is False


def test_season_era_rank_uses_raw_components_not_display_rounded_era():
    tor_pitchers = [
        _pitcher(idx, f'Toronto Arm {idx}', team_id=141, team_name='Toronto Blue Jays', abbr='TOR')
        for idx in range(1, 7)
    ]
    cle_pitchers = [
        _pitcher(idx, f'Cleveland Arm {idx}', team_id=114, team_name='Cleveland Guardians', abbr='CLE')
        for idx in range(11, 17)
    ]
    records = [
        *[_record(pitcher, STATUS_AVAILABLE) for pitcher in tor_pitchers],
        *[_record(pitcher, STATUS_AVAILABLE) for pitcher in cle_pitchers],
    ]
    logs_by_pitcher = {
        pitcher.id: [_log(pitcher.id, 1, 35)]
        for pitcher in [*tor_pitchers, *cle_pitchers]
    }

    feed = build_four_beat_story_feed(
        records,
        logs_by_pitcher,
        reference_date=REF,
        season_era={
            'bullpens': [
                {
                    'team_id': 114,
                    'team_name': 'Cleveland Guardians',
                    'team_abbreviation': 'CLE',
                    'era': 3.14,
                    'innings_outs': 482,
                    'earned_runs': 56,
                },
                {
                    'team_id': 141,
                    'team_name': 'Toronto Blue Jays',
                    'team_abbreviation': 'TOR',
                    'era': 3.14,
                    'innings_outs': 663,
                    'earned_runs': 77,
                },
            ],
        },
    )

    stories = {
        item['team_abbreviation']: item
        for item in feed['items']
    }
    tor_text = _story_text(stories['TOR'])
    cle_text = _story_text(stories['CLE'])

    assert stories['TOR']['computed']['season_era']['rank'] == 1
    assert stories['CLE']['computed']['season_era']['rank'] == 2
    assert stories['TOR']['computed']['season_era']['era'] == 3.14
    assert stories['CLE']['computed']['season_era']['era'] == 3.14
    assert '1st among current pens' in tor_text
    assert '2nd among current pens' in cle_text


def test_pressure_distribution_wins_when_hidden_capacity_also_qualifies():
    pitchers = [_pitcher(idx, f'Light Thin Arm {idx}') for idx in range(1, 9)]
    records = [
        _record(pitchers[0], STATUS_AVAILABLE),
        _record(pitchers[1], STATUS_AVAILABLE),
        _record(pitchers[2], STATUS_AVAILABLE),
        *[_record(pitcher, STATUS_MONITOR) for pitcher in pitchers[3:]],
    ]
    logs_by_pitcher = {
        pitcher.id: [_log(pitcher.id, 1, 10)]
        for pitcher in pitchers
    }
    feed = build_four_beat_story_feed(
        records,
        logs_by_pitcher,
        reference_date=REF,
        season_era={
            'bullpens': [{
                'team_id': 1,
                'team_name': 'Test Club',
                'team_abbreviation': 'TST',
                'era': 3.10,
                'innings_outs': 120,
                'earned_runs': 12,
            }],
        },
    )

    assert feed['items'][0]['rule_key'] == RULE_PRESSURE_DISTRIBUTION
    rules = {
        rule['rule_key']: rule
        for rule in feed['evaluations'][0]['rules']
    }
    assert rules[RULE_PRESSURE_DISTRIBUTION]['can_fire'] is True
    assert rules[RULE_HIDDEN_CAPACITY_LOSS]['can_fire'] is True


def test_era_rule_mechanisms_stay_static_and_honest():
    heavy_pitchers = [_pitcher(idx, f'Heavy Arm {idx}') for idx in range(1, 7)]
    sustainability = _rule_eval(evaluate_team_rules(_team_inputs(
        [_record(pitcher, STATUS_AVAILABLE) for pitcher in heavy_pitchers],
        {pitcher.id: [_log(pitcher.id, 1, 35)] for pitcher in heavy_pitchers},
        season_era_by_team=_ranked_era(rank=3, strong=True, solid=True),
    )), RULE_SUSTAINABILITY_QUESTION)['story']

    thin_pitchers = [_pitcher(idx, f'Thin Arm {idx}', team_id=2, team_name='Thin Club', abbr='THN') for idx in range(1, 8)]
    hidden = _rule_eval(evaluate_team_rules(_team_inputs(
        [
            _record(thin_pitchers[0], STATUS_AVAILABLE),
            _record(thin_pitchers[1], STATUS_AVAILABLE),
            *[_record(pitcher, STATUS_MONITOR) for pitcher in thin_pitchers[2:]],
        ],
        {pitcher.id: [_log(pitcher.id, 1, 20)] for pitcher in thin_pitchers[:5]},
        team={'team_id': 2, 'team_name': 'Thin Club', 'team_abbreviation': 'THN'},
        season_era_by_team=_ranked_era(2, rank=16, strong=False, solid=True),
    )), RULE_HIDDEN_CAPACITY_LOSS)['story']

    for story in (sustainability, hidden):
        assert story is not None
        story_text = _story_text(story)
        assert 'among 30 bullpens' not in story_text
        assert 'among current pens' in story_text
        for beat in story['beats']:
            assert '{' not in beat['text']
            assert '}' not in beat['text']
        mechanism = next(beat['text'].lower() for beat in story['beats'] if beat['key'] == 'mechanism')
        for banned in ('slipping', 'starting to show', 'hasn\'t shown', 'haven\'t shown', 'yet'):
            assert banned not in mechanism


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
    assert 'more ways through the late innings' in mechanism or 'usually leaves' in mechanism
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


def test_public_four_beat_copy_avoids_robotic_voice_residue():
    pitchers = [_pitcher(idx, f'Voice Arm {idx}') for idx in range(1, 7)]
    records = [_record(pitcher, STATUS_AVAILABLE, risk='HIGH' if idx == 0 else 'LOW') for idx, pitcher in enumerate(pitchers)]
    logs = {pitcher.id: [_log(pitcher.id, 1, 35)] for pitcher in pitchers}
    story = _rule_eval(evaluate_team_rules(_team_inputs(
        records,
        logs,
        season_era_by_team=_ranked_era(rank=3, strong=True, solid=True),
    )), RULE_SUSTAINABILITY_QUESTION)['story']

    text = _story_text(story).lower()
    for phrase in (
        'story starts with',
        'the watch is',
        'watch point',
        'current bullpen group owns',
        'current group owns',
        'among the bullpens teams are carrying right now',
    ):
        assert phrase not in text


def test_story_fact_layer_and_narrative_are_added_without_breaking_beat_contract():
    story = _rule_eval(evaluate_team_rules(_thin_concentrated_team_inputs(
        capacity_by_team=_capacity_context(
            status='constrained',
            unavailable_pct=44,
            limitations=[
                'Capacity uses count-based weighting because one or more unavailable bullpen arms have limited relief workload history.',
            ],
        ),
    )), RULE_STRESS_TRANSFER)['story']

    facts = story['story_facts']
    narrative = story['narrative']

    assert story['body']
    assert story['beats']
    assert story['rule_key'] == RULE_STRESS_TRANSFER
    assert facts['capability'] == STORY_FACT_LAYER_CAPABILITY
    assert facts['primary_observation'] == story['title']
    assert facts['supporting_context']
    assert facts['pressure_source']
    assert facts['workload_pattern']
    assert facts['capacity_context']
    assert facts['watch_question']
    assert facts['confidence'] == 'limited'
    assert facts['disclosure'] == story['disclosure_note']
    assert narrative.count('\n\n') == 2
    assert facts['primary_observation'] in narrative
    assert facts['watch_question'] in narrative


def test_public_narrative_avoids_forbidden_labels_and_internal_taxonomy():
    story = _rule_eval(evaluate_team_rules(_thin_concentrated_team_inputs(
        season_era_by_team=_ranked_era(rank=3, strong=True, solid=True),
    )), RULE_STRESS_TRANSFER)['story']
    narrative = story['narrative']
    lower = narrative.lower()

    assert narrative_contains_forbidden_language(narrative) is False
    for label in FORBIDDEN_PUBLIC_LABELS:
        assert label not in narrative
    for term in INTERNAL_TAXONOMY_TERMS:
        assert term.lower() not in lower
    for forbidden in (
        'betting',
        'prediction',
        'recommendation',
        'should use',
        'manager should',
        'fatigue score',
        'confidence score',
        'HIGH or CRITICAL',
    ):
        assert forbidden.lower() not in lower


def test_story_narrative_output_is_deterministic():
    pitchers, records, logs = _fixture_team(
        141,
        'Toronto Blue Jays',
        'TOR',
        [38, 34, 29, 11, 9, 8, 6],
    )
    season_era = {
        'bullpens': [
            _bullpen_era(141, 'Toronto Blue Jays', 'TOR', 3.15),
        ],
    }

    first = build_four_beat_story_feed(records, logs, reference_date=REF, season_era=season_era)
    second = build_four_beat_story_feed(records, logs, reference_date=REF, season_era=season_era)

    assert [
        (item['team_abbreviation'], item['story_facts'], item['narrative'])
        for item in first['items']
    ] == [
        (item['team_abbreviation'], item['story_facts'], item['narrative'])
        for item in second['items']
    ]
    assert pitchers


def test_bullpen_stability_passes_through_computed_data_without_new_claims():
    pitchers = [_pitcher(idx, f'Arm {idx}') for idx in range(1, 7)]
    stability = {
        'capability': 'bullpen_stability_v1',
        'team_id': 1,
        'status': 'moderate_churn',
        'new_or_reintroduced_arm_count': 2,
    }
    inputs = compute_team_story_inputs(_team_inputs(
        [_record(pitcher, STATUS_AVAILABLE) for pitcher in pitchers],
        {pitcher.id: [_log(pitcher.id, 1, 10)] for pitcher in pitchers},
        bullpen_stability_by_team={1: stability},
    ))
    story = assemble_story(RULE_PRESSURE_DISTRIBUTION, inputs)

    assert inputs['bullpen_stability'] == stability
    assert story['computed']['bullpen_stability'] == stability
    assert story['slot_sources']['bullpen_stability'] == 'bullpen_stability_v1'
    assert 'churn' not in _story_text(story).lower()


def test_supported_environment_adds_single_backend_why_context():
    result = evaluate_team_rules(_thin_concentrated_team_inputs(
        capacity_by_team=_capacity_context(),
        rotation_support_by_team=_rotation_context(),
        bullpen_environment_by_team=_environment_context(),
    ))
    story = _rule_eval(result, RULE_STRESS_TRANSFER)['story']
    context = next(beat for beat in story['beats'] if beat['key'] == BEAT_CONTEXT)
    text = context['text'].lower()

    assert context['sources'] == ['bullpen_environment']
    assert story['computed']['why_context'] == {
        'applied': True,
        'sources': ['bullpen_environment'],
        'context_flags': ['source_limitations_present'],
        'source_limitations_present': True,
    }
    assert any(marker in text for marker in ENVIRONMENT_INTRO_MARKERS)
    assert any(marker in text for marker in CAPACITY_CONTEXT_MARKERS)
    assert any(marker in text for marker in ROTATION_CONTEXT_MARKERS)
    for unsupported in (
        'because',
        'caused',
        'due to',
        'recommend',
        'prediction',
        'betting',
        'multi_source_pressure',
        'heavy_pressure',
        'capacity_loss',
    ):
        assert unsupported not in text


def test_capacity_unknown_limited_read_and_rotation_excluded_games_block_context():
    limited_capacity_story = _rule_eval(evaluate_team_rules(_thin_concentrated_team_inputs(
        capacity_by_team=_capacity_context(
            limitations=['Some bullpen capacity is based on limited-read or unknown availability inputs.'],
            unknown_pct=33,
        ),
    )), RULE_STRESS_TRANSFER)['story']
    limited_rotation_story = _rule_eval(evaluate_team_rules(_thin_concentrated_team_inputs(
        rotation_support_by_team=_rotation_context(
            limitations=['Some recent team games are excluded because starter/relief workload data is incomplete or ambiguous.'],
        ),
    )), RULE_STRESS_TRANSFER)['story']

    assert not any(beat['key'] == BEAT_CONTEXT for beat in limited_capacity_story['beats'])
    assert not any(beat['key'] == BEAT_CONTEXT for beat in limited_rotation_story['beats'])
    assert limited_capacity_story['computed']['why_context']['applied'] is False
    assert limited_rotation_story['computed']['why_context']['applied'] is False
    assert 'fewer usable arms' not in _story_text(limited_capacity_story).lower()
    assert 'carrying more of the workload' not in _story_text(limited_rotation_story).lower()


def test_capacity_count_based_fallback_adds_soft_context_without_precision():
    story = _rule_eval(evaluate_team_rules(_thin_concentrated_team_inputs(
        capacity_by_team=_capacity_context(
            status='constrained',
            unavailable_pct=44,
            limitations=[
                'Capacity uses count-based weighting because one or more unavailable bullpen arms have limited relief workload history.',
            ],
        ),
    )), RULE_STRESS_TRANSFER)['story']
    context = next(beat for beat in story['beats'] if beat['key'] == BEAT_CONTEXT)
    text = context['text'].lower()

    assert context['sources'] == ['capacity_loss']
    assert story['computed']['why_context']['source_limitations_present'] is True
    assert any(marker in text for marker in CAPACITY_FALLBACK_MARKERS)
    assert '44' not in text
    assert '%' not in text
    for unsupported in ('because', 'caused', 'due to', 'recommend', 'prediction', 'betting'):
        assert unsupported not in text


def test_capacity_fallback_context_has_deterministic_phrase_variety_without_precision():
    capacity_payload = _capacity_context(
        status='constrained',
        unavailable_pct=44,
        limitations=[
            'Capacity uses count-based weighting because one or more unavailable bullpen arms have limited relief workload history.',
        ],
    )[1]
    texts = []

    for team_id in range(1, 8):
        story = _rule_eval(evaluate_team_rules(_thin_concentrated_team_inputs(
            team={
                'team_id': team_id,
                'team_name': f'Test Club {team_id}',
                'team_abbreviation': f'T{team_id}',
            },
            capacity_by_team={team_id: capacity_payload},
        )), RULE_STRESS_TRANSFER)['story']
        context = next(beat for beat in story['beats'] if beat['key'] == BEAT_CONTEXT)
        text = context['text'].lower()

        texts.append(text)
        assert any(marker in text for marker in CAPACITY_FALLBACK_MARKERS)
        assert '44' not in text
        assert '%' not in text

    assert len(set(texts)) >= 2


def test_unclassified_capacity_limitation_still_blocks_context():
    story = _rule_eval(evaluate_team_rules(_thin_concentrated_team_inputs(
        capacity_by_team=_capacity_context(
            status='constrained',
            limitations=[
                'Capacity uses count-based weighting because relief workload sample is limited.',
                'Capacity source quality requires manual review.',
            ],
        ),
    )), RULE_STRESS_TRANSFER)['story']

    assert not any(beat['key'] == BEAT_CONTEXT for beat in story['beats'])
    assert story['computed']['why_context']['applied'] is False


def test_capacity_and_rotation_context_can_appear_without_environment_synthesis():
    story = _rule_eval(evaluate_team_rules(_thin_concentrated_team_inputs(
        capacity_by_team=_capacity_context(),
        rotation_support_by_team=_rotation_context(),
    )), RULE_STRESS_TRANSFER)['story']
    context = next(beat for beat in story['beats'] if beat['key'] == BEAT_CONTEXT)
    text = context['text'].lower()

    assert context['sources'] == ['capacity_loss', 'rotation_support_pressure']
    assert story['computed']['why_context']['sources'] == ['capacity_loss', 'rotation_support_pressure']
    assert any(marker in text for marker in CAPACITY_CONTEXT_MARKERS)
    assert any(marker in text for marker in ROTATION_CONTEXT_MARKERS)
    for unsupported in ('because', 'caused', 'due to', 'recommend', 'prediction', 'betting'):
        assert unsupported not in text


def test_stability_usage_only_disclosure_stays_usage_based_without_transaction_claims():
    story = _rule_eval(evaluate_team_rules(_thin_concentrated_team_inputs(
        bullpen_stability_by_team=_stability_context(
            limitations=[
                'Bullpen stability uses usage patterns and does not imply transaction activity.',
            ],
        ),
    )), RULE_STRESS_TRANSFER)['story']
    context = next(beat for beat in story['beats'] if beat['key'] == BEAT_CONTEXT)
    text = context['text'].lower()

    assert context['sources'] == ['bullpen_stability']
    assert any(marker in text for marker in STABILITY_CONTEXT_MARKERS)
    assert 'usage pattern' not in text
    assert 'read cleanly' not in text
    for unsupported in ('transaction', 'recall', 'called up', 'optioned', 'dfa'):
        assert unsupported not in text


def test_stability_context_blocks_small_sample_denominator():
    story = _rule_eval(evaluate_team_rules(_thin_concentrated_team_inputs(
        bullpen_stability_by_team=_stability_context(recently_used=3),
    )), RULE_STRESS_TRANSFER)['story']

    assert not any(beat['key'] == BEAT_CONTEXT for beat in story['beats'])
    assert story['computed']['why_context']['applied'] is False


def test_environment_context_requires_two_eligible_source_contexts():
    story = _rule_eval(evaluate_team_rules(_thin_concentrated_team_inputs(
        capacity_by_team=_capacity_context(
            status='constrained',
            limitations=[
                'Capacity uses count-based weighting because relief workload sample is limited.',
            ],
        ),
        rotation_support_by_team=_rotation_context(
            limitations=['Some recent team games are excluded because starter/relief workload data is incomplete or ambiguous.'],
        ),
        bullpen_environment_by_team=_environment_context(),
    )), RULE_STRESS_TRANSFER)['story']
    context = next(beat for beat in story['beats'] if beat['key'] == BEAT_CONTEXT)

    assert context['sources'] == ['capacity_loss']
    assert story['computed']['why_context']['sources'] == ['capacity_loss']
    assert not any(marker in context['text'].lower() for marker in ENVIRONMENT_INTRO_MARKERS)


def test_environment_context_can_use_disclosure_limited_capacity_and_stability():
    story = _rule_eval(evaluate_team_rules(_thin_concentrated_team_inputs(
        capacity_by_team=_capacity_context(
            status='constrained',
            limitations=[
                'Capacity uses count-based weighting because relief workload sample is limited.',
            ],
        ),
        bullpen_stability_by_team=_stability_context(
            limitations=[
                'Bullpen stability uses usage patterns and does not imply transaction activity.',
            ],
        ),
        bullpen_environment_by_team=_environment_context(
            sources=['capacity_loss', 'bullpen_stability'],
        ),
    )), RULE_STRESS_TRANSFER)['story']
    context = next(beat for beat in story['beats'] if beat['key'] == BEAT_CONTEXT)
    text = context['text'].lower()

    assert context['sources'] == ['bullpen_environment']
    assert story['computed']['why_context']['source_limitations_present'] is True
    assert any(marker in text for marker in ENVIRONMENT_INTRO_MARKERS)
    assert any(marker in text for marker in CAPACITY_CONTEXT_MARKERS)
    assert any(marker in text for marker in STABILITY_CONTEXT_MARKERS)
    for unsupported in ('because', 'caused', 'due to', 'transaction', 'recall', 'called up', 'optioned', 'dfa'):
        assert unsupported not in text


def test_description_only_teams_suppress_and_feed_count_is_variable_and_ordered():
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


def test_team_shape_workload_concentration_matches_four_beat_descriptor():
    pitchers = [_pitcher(idx, f'Concentration Arm {idx}') for idx in range(1, 6)]
    records = [
        _record(pitchers[0], STATUS_AVAILABLE),
        _record(pitchers[1], STATUS_AVAILABLE),
        _record(pitchers[2], STATUS_MONITOR),
        _record(pitchers[3], STATUS_MONITOR),
        _record(pitchers[4], STATUS_MONITOR),
    ]
    logs_by_pitcher = {
        pitchers[0].id: [_log(pitchers[0].id, 1, 45)],
        pitchers[1].id: [_log(pitchers[1].id, 1, 25)],
        pitchers[2].id: [_log(pitchers[2].id, 1, 20)],
        pitchers[3].id: [_log(pitchers[3].id, 1, 5)],
        pitchers[4].id: [_log(pitchers[4].id, 1, 5)],
    }

    story_inputs = compute_team_story_inputs(_team_inputs(records, logs_by_pitcher))
    shape = build_team_bullpen_shape([], workload_concentration=story_inputs['workload'])
    concentration = shape['workloadConcentration']

    assert story_inputs['workload']['concentration_descriptor'] == 'a heavily concentrated workload'
    assert concentration['label'] == 'Heavily Concentrated Workload'
    assert concentration['supportingCounts']['concentrationDescriptor'] == (
        story_inputs['workload']['concentration_descriptor']
    )
    assert concentration['supportingCounts']['topShare'] == story_inputs['workload']['top_share']


def test_near_collision_stress_transfer_pens_surface_concentration_specifics():
    tampa_inputs = _near_collision_stress_team(
        139,
        'Tampa Bay Rays',
        'TB',
        [
            'Rowan Tide',
            'Cal Harbor',
            'Evan Shore',
            'Casey Break',
            'Nico Channel',
            'Drew Anchor',
            'Miles Current',
            'Theo Marker',
        ],
        [28, 22, 16, 8, 8, 7, 6, 5],
        available_count=3,
    )
    mets_inputs = _near_collision_stress_team(
        121,
        'New York Mets',
        'NYM',
        [
            'Marcus Slate',
            'Jon Borough',
            'Eli Queens',
            'Victor Line',
            'Sam Orchard',
            'Noah Transit',
            'Owen Crown',
            'Cole Hudson',
            'Reid Penn',
            'Liam Union',
            'Gabe Metro',
        ],
        [34, 28, 20, 3, 3, 3, 2, 2, 2, 2, 1],
        available_count=3,
    )

    tampa_eval = _rule_eval(evaluate_team_rules(tampa_inputs), RULE_STRESS_TRANSFER)
    mets_eval = _rule_eval(evaluate_team_rules(mets_inputs), RULE_STRESS_TRANSFER)

    assert tampa_eval['can_fire'] is True
    assert mets_eval['can_fire'] is True

    tampa_story = tampa_eval['story']
    mets_story = mets_eval['story']
    tampa_text = _story_text(tampa_story)
    mets_text = _story_text(mets_story)

    assert tampa_story['rule_key'] == RULE_STRESS_TRANSFER
    assert mets_story['rule_key'] == RULE_STRESS_TRANSFER
    assert tampa_text != mets_text

    assert 'Tampa Bay Rays' in tampa_text
    assert 'New York Mets' in mets_text
    assert '3 of 8' in tampa_text
    assert '3 of 11' in mets_text
    assert 'Rowan Tide and Cal Harbor' in tampa_text
    assert 'Marcus Slate and Jon Borough' in mets_text
    assert round(tampa_story['computed']['workload']['top_share'], 2) == 0.66
    assert round(mets_story['computed']['workload']['top_share'], 2) == 0.82
    assert tampa_story['computed']['workload']['concentration_level'] == 'moderate'
    assert mets_story['computed']['workload']['concentration_level'] == 'severe'
    assert tampa_story['computed']['availability']['total'] == 8
    assert mets_story['computed']['availability']['total'] == 11

    missing_concentration = []
    if 'some concentration' not in tampa_text:
        missing_concentration.append('Tampa Bay text missing "some concentration"')
    if 'concentrated' not in mets_text:
        missing_concentration.append('New York Mets text missing "concentrated"')
    assert not missing_concentration, (
        'Near-collision stress-transfer stories flattened concentration detail: '
        f"{'; '.join(missing_concentration)}\n"
        f'Tampa Bay: {tampa_text}\n'
        f'New York Mets: {mets_text}'
    )


def test_content_selective_leads_are_deterministic_and_surface_normalized_fields():
    mia_pitchers, mia_records, mia_logs = _fixture_team(
        146,
        'Miami Marlins',
        'MIA',
        [42, 38, 36, 35, 35, 35, 35],
        high_risk_indices=(0,),
        trust_indices=(1, 2, 3, 4),
    )
    az_pitchers, az_records, az_logs = _fixture_team(
        109,
        'Arizona Diamondbacks',
        'AZ',
        [50, 42, 38, 26, 25, 25, 25],
    )
    lad_pitchers, lad_records, lad_logs = _fixture_team(
        119,
        'Los Angeles Dodgers',
        'LAD',
        [34, 32, 31, 30, 30, 29, 29, 29],
        trust_indices=(0, 1, 2, 3),
    )
    records = [*mia_records, *az_records, *lad_records]
    logs = _merge_logs(mia_logs, az_logs, lad_logs)
    season_era = {
        'bullpens': [
            _bullpen_era(146, 'Miami Marlins', 'MIA', 3.35),
            _bullpen_era(109, 'Arizona Diamondbacks', 'AZ', 2.72),
            _bullpen_era(119, 'Los Angeles Dodgers', 'LAD', 3.28),
        ],
    }

    first = build_four_beat_story_feed(records, logs, reference_date=REF, season_era=season_era)
    second = build_four_beat_story_feed(records, logs, reference_date=REF, season_era=season_era)

    first_leads = [(item['team_abbreviation'], item['lead_dimension'], item['title']) for item in first['items']]
    second_leads = [(item['team_abbreviation'], item['lead_dimension'], item['title']) for item in second['items']]
    assert first_leads == second_leads

    stories = {item['team_abbreviation']: item for item in first['items']}
    assert stories['MIA']['lead_dimension'] == LEAD_FATIGUE_LOAD
    assert stories['AZ']['lead_dimension'] == LEAD_TRUST_LANE_ABSENCE
    assert stories['LAD']['lead_dimension'] in {
        LEAD_AVAILABILITY_DEEP,
        LEAD_DEEP_INTACT,
        LEAD_TRUST_LANE_DEPTH,
    }
    assert stories['MIA']['lead_fields']['high_risk_arm_count'] == 1
    assert stories['MIA']['lead_fields']['high_risk_arm_names'] == [mia_pitchers[0].full_name]
    assert stories['LAD']['lead_fields']['clean_trust_count'] >= 2
    assert set(stories['LAD']['lead_fields']['clean_trust_names'])
    assert len({stories['MIA']['title'], stories['AZ']['title'], stories['LAD']['title']}) == 3
    assert 'HIGH or CRITICAL fatigue' in next(
        beat['text'] for beat in stories['MIA']['beats'] if beat['key'] == 'evidence'
    )


def test_feed_wide_lead_collisions_resolve_on_grounded_secondary_dimensions():
    az_pitchers, az_records, az_logs = _fixture_team(
        109,
        'Arizona Diamondbacks',
        'AZ',
        [50, 42, 38, 26, 25, 25, 25],
    )
    lad_pitchers, lad_records, lad_logs = _fixture_team(
        119,
        'Los Angeles Dodgers',
        'LAD',
        [34, 32, 31, 30, 30, 29, 29, 29],
        trust_indices=(0, 1, 2, 3),
    )
    sd_pitchers, sd_records, sd_logs = _fixture_team(
        135,
        'San Diego Padres',
        'SD',
        [25, 25, 25, 25, 25, 25, 25, 25],
    )
    bos_pitchers, bos_records, bos_logs = _fixture_team(
        111,
        'Boston Red Sox',
        'BOS',
        [25, 25, 25, 25, 25, 25, 25, 25],
        trust_indices=(0, 1),
    )
    season_era = {
        'bullpens': [
            _bullpen_era(109, 'Arizona Diamondbacks', 'AZ', 2.72),
            _bullpen_era(135, 'San Diego Padres', 'SD', 3.11),
            _bullpen_era(119, 'Los Angeles Dodgers', 'LAD', 3.28),
            _bullpen_era(111, 'Boston Red Sox', 'BOS', 3.87),
        ],
    }

    def build(records):
        return build_four_beat_story_feed(
            records,
            _merge_logs(az_logs, lad_logs, sd_logs, bos_logs),
            reference_date=REF,
            season_era=season_era,
        )

    ordered_records = [*az_records, *lad_records, *sd_records, *bos_records]
    first = build(ordered_records)
    second = build(list(reversed(ordered_records)))
    first_leads = {
        item['team_abbreviation']: (
            item['lead_dimension'],
            item['title'],
            item['lead_dimension_detail'].get('feed_wide_replacement_for'),
        )
        for item in first['items']
    }
    second_leads = {
        item['team_abbreviation']: (
            item['lead_dimension'],
            item['title'],
            item['lead_dimension_detail'].get('feed_wide_replacement_for'),
        )
        for item in second['items']
    }

    assert first_leads == second_leads
    stories = {item['team_abbreviation']: item for item in first['items']}
    assert stories['AZ']['lead_dimension'] == LEAD_TRUST_LANE_ABSENCE
    assert stories['SD']['lead_dimension'] != LEAD_TRUST_LANE_ABSENCE
    assert stories['SD']['lead_dimension_detail']['feed_wide_replacement_for'] == LEAD_TRUST_LANE_ABSENCE
    assert stories['LAD']['lead_dimension'] == LEAD_DEEP_INTACT
    assert stories['BOS']['lead_dimension'] != LEAD_DEEP_INTACT
    assert stories['BOS']['lead_dimension_detail']['feed_wide_replacement_for'] == LEAD_DEEP_INTACT
    assert stories['SD']['lead_fields']['clean_trust_count'] == 0
    assert stories['SD']['computed']['season_era']['rank'] < stories['BOS']['computed']['season_era']['rank']
    assert stories['BOS']['computed']['season_era']['rank'] > stories['LAD']['computed']['season_era']['rank']
    assert stories['BOS']['computed']['availability']['available'] == stories['BOS']['computed']['availability']['total']

    normalized_titles = {}
    for story in first['items']:
        normalized = story['title'].replace(story['team_name'], '{team_name}')
        assert normalized not in normalized_titles, (
            f"{story['team_abbreviation']} collided with "
            f"{normalized_titles.get(normalized)} on {normalized!r}"
        )
        normalized_titles[normalized] = story['team_abbreviation']


def test_content_selective_leads_do_not_manufacture_difference_for_near_identical_pens():
    first_pitchers, first_records, first_logs = _fixture_team(
        701,
        'First Similar Club',
        'FSC',
        [12, 12, 12, 12, 12, 12],
    )
    second_pitchers, second_records, second_logs = _fixture_team(
        702,
        'Second Similar Club',
        'SSC',
        [12, 12, 12, 12, 12, 12],
    )
    feed = build_four_beat_story_feed(
        [*first_records, *second_records],
        _merge_logs(first_logs, second_logs),
        reference_date=REF,
    )

    stories = sorted(feed['items'], key=lambda item: item['team_abbreviation'])
    assert [story['rule_key'] for story in stories] == [
        RULE_PRESSURE_DISTRIBUTION,
        RULE_PRESSURE_DISTRIBUTION,
    ]
    assert stories[0]['lead_dimension'] == stories[1]['lead_dimension']
    assert stories[0]['beats'][0]['skeleton_key'] == stories[1]['beats'][0]['skeleton_key']
    assert stories[0]['title'].replace(stories[0]['team_name'], '{team_name}') == (
        stories[1]['title'].replace(stories[1]['team_name'], '{team_name}')
    )
    assert any(story['lead_dimension_detail'].get('honest_sameness') for story in stories)
    assert any(story['lead_dimension_detail'].get('feed_wide_honest_sameness') for story in stories)


def test_feed_wide_distinct_prose_guard_allows_only_honest_sameness():
    no_trust_pitchers, no_trust_records, no_trust_logs = _fixture_team(
        811,
        'No Trust Fixture',
        'NTF',
        [36, 34, 32, 31, 31, 31],
    )
    pressure_pitchers, pressure_records, pressure_logs = _fixture_team(
        812,
        'Pressure Fixture',
        'PFX',
        [24, 24, 24, 24, 24, 24, 24, 24],
    )
    twin_pitchers, twin_records, twin_logs = _fixture_team(
        813,
        'Twin Fixture',
        'TFX',
        [24, 24, 24, 24, 24, 24, 24, 24],
    )
    feed = build_four_beat_story_feed(
        [*no_trust_records, *pressure_records, *twin_records],
        _merge_logs(no_trust_logs, pressure_logs, twin_logs),
        reference_date=REF,
        season_era={
            'bullpens': [
                _bullpen_era(811, 'No Trust Fixture', 'NTF', 2.80),
                _bullpen_era(812, 'Pressure Fixture', 'PFX', 3.25),
                _bullpen_era(813, 'Twin Fixture', 'TFX', 3.25),
            ],
        },
    )

    seen = {}
    for story in feed['items']:
        normalized = story['title'].replace(story['team_name'], '{team_name}')
        if normalized in seen:
            assert story['lead_dimension_detail'].get('honest_sameness'), (
                f"{story['team_abbreviation']} collided with {seen[normalized]} without honest sameness"
            )
        else:
            seen[normalized] = story['team_abbreviation']


def test_same_rule_different_leads_produce_different_headlines_and_lead_beats():
    no_trust_pitchers, no_trust_records, no_trust_logs = _fixture_team(
        801,
        'No Trust Club',
        'NTC',
        [36, 34, 32, 31, 31, 31],
    )
    deep_pitchers, deep_records, deep_logs = _fixture_team(
        802,
        'Deep Trust Club',
        'DTC',
        [31, 31, 31, 31, 31, 31, 31, 31],
        trust_indices=(0, 1, 2),
    )
    feed = build_four_beat_story_feed(
        [*no_trust_records, *deep_records],
        _merge_logs(no_trust_logs, deep_logs),
        reference_date=REF,
        season_era={
            'bullpens': [
                _bullpen_era(801, 'No Trust Club', 'NTC', 2.90),
                _bullpen_era(802, 'Deep Trust Club', 'DTC', 3.10),
            ],
        },
    )

    stories = {item['team_abbreviation']: item for item in feed['items']}
    assert stories['NTC']['rule_key'] == RULE_SUSTAINABILITY_QUESTION
    assert stories['DTC']['rule_key'] == RULE_SUSTAINABILITY_QUESTION
    assert stories['NTC']['lead_dimension'] != stories['DTC']['lead_dimension']
    assert stories['NTC']['title'] != stories['DTC']['title']
    no_trust_evidence = next(beat for beat in stories['NTC']['beats'] if beat['key'] == 'evidence')
    deep_evidence = next(beat for beat in stories['DTC']['beats'] if beat['key'] == 'evidence')
    assert no_trust_evidence['skeleton_key'] != deep_evidence['skeleton_key']
    for story in stories.values():
        for beat in story['beats']:
            assert '{' not in beat['text']
            assert '}' not in beat['text']
            for banned in ('slipping', 'starting to show', 'hasn\'t shown', 'haven\'t shown', 'yet'):
                assert banned not in beat['text'].lower()


def test_content_selective_leads_cover_stress_transfer_and_hidden_capacity_fixtures():
    stress_pitchers, stress_records, stress_logs = _fixture_team(
        901,
        'Stress Fixture Club',
        'SFC',
        [40, 32, 25, 2, 1],
        available_count=2,
        trust_indices=(0, 1),
    )
    hidden_pitchers, hidden_records, hidden_logs = _fixture_team(
        902,
        'Hidden Fixture Club',
        'HFC',
        [30, 30, 30, 30, 30, 30, 30],
        available_count=2,
        trust_indices=(0,),
    )
    lower_era_bullpens = [
        _bullpen_era(1000 + idx, f'Lower ERA Club {idx}', f'L{idx}', 2.50 + (idx * 0.03))
        for idx in range(14)
    ]
    feed = build_four_beat_story_feed(
        [*stress_records, *hidden_records],
        _merge_logs(stress_logs, hidden_logs),
        reference_date=REF,
        season_era={
            'bullpens': [
                *lower_era_bullpens,
                _bullpen_era(901, 'Stress Fixture Club', 'SFC', 4.50),
                _bullpen_era(902, 'Hidden Fixture Club', 'HFC', 3.40),
            ],
        },
    )

    stories = {item['team_abbreviation']: item for item in feed['items']}
    assert stories['SFC']['rule_key'] == RULE_STRESS_TRANSFER
    assert stories['SFC']['lead_dimension'] in {LEAD_AVAILABILITY_THIN, LEAD_CONCENTRATION_SHAPE}
    assert stories['HFC']['rule_key'] == RULE_HIDDEN_CAPACITY_LOSS
    assert stories['HFC']['lead_dimension'] is not None
    assert all(story['beats'][0]['skeleton_key'].startswith('lead_signal:') for story in stories.values())


def test_feature_flag_defaults_on():
    assert four_beat_stories_enabled({}) is True
    assert four_beat_stories_enabled({'FOUR_BEAT_STORIES_ENABLED': False}) is False
    assert four_beat_stories_enabled({'FOUR_BEAT_STORIES_ENABLED': True}) is True
