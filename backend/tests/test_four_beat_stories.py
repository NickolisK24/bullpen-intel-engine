import inspect
import re
from datetime import date, timedelta
from types import SimpleNamespace

import services.team_story_narrative as team_story_narrative
from services.availability import STATUS_AVAILABLE, STATUS_AVOID, STATUS_MONITOR
from services.bullpen_identity import (
    IDENTITY_LABELS,
    IDENTITY_LEVERAGE_HEAVY,
    IDENTITY_UNKNOWN,
    build_bullpen_identity,
)
from services.four_beat_stories import (
    BEAT_CONTEXT,
    LEAD_AVAILABILITY_DEEP,
    LEAD_AVAILABILITY_THIN,
    LEAD_CONCENTRATION_SHAPE,
    LEAD_DEEP_INTACT,
    LEAD_FATIGUE_LOAD,
    LEAD_TRUST_LANE_ABSENCE,
    LEAD_TRUST_LANE_DEPTH,
    LEAD_TRUST_LANE_SHALLOW,
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
    diversify_feed_story_order,
    evaluate_team_rules,
    four_beat_stories_enabled,
)
from services.story_evidence import (
    GENERIC_LANGUAGE_DENYLIST,
    INTERNAL_PROCESS_LANGUAGE_DENYLIST,
    PUBLIC_SCHEMA_LANGUAGE_DENYLIST,
    apply_story_evidence_framework,
    story_public_text,
    validate_story_evidence,
)
from services.story_observation_discovery import (
    DIFFERENTIATION_CAPABILITY,
    build_feed_observation_inventory,
    differentiate_observation_inventory,
    discover_story_observations,
    generate_observation_candidates,
    rank_observation_candidates,
    story_template_dependency_audit,
)
from services.story_observation_voice import (
    THROAT_CLEARING_CLOSERS,
    build_observation_voice,
    observation_prose_paths,
    validate_observation_voice,
)
from services.story_identity_integration import CAPABILITY as STORY_IDENTITY_CAPABILITY
from services.team_story_facts import (
    CAPABILITY as STORY_FACT_LAYER_CAPABILITY,
    DISCLOSURE_LIMITED_BULLPEN_PICTURE,
)
from services.team_story_narrative import (
    ARCHETYPE_CAPACITY_CONSTRAINT,
    ARCHETYPE_FLEXIBLE_BULLPEN,
    ARCHETYPE_MULTI_SOURCE_PRESSURE,
    ARCHETYPE_ROTATION_SPILLOVER,
    ARCHETYPE_RUN_PREVENTION_MASK,
    ARCHETYPE_STABILITY_EROSION,
    ARCHETYPE_STABILITY_RECOVERY,
    ARCHETYPE_THIN_TRUSTED_GROUP,
    ARCHETYPE_WORKLOAD_CONCENTRATION,
    FORBIDDEN_PUBLIC_LABELS,
    INTERNAL_TAXONOMY_TERMS,
    narrative_contains_forbidden_language,
    render_story_disclosure_note,
    render_story_narrative,
    select_story_archetype,
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
    'bullpen usage has moved across different relievers',
)

AWKWARD_RENDERER_PHRASES = (
    'one-lane bullpen story',
    'one-lane bullpen read',
    'run-prevention line',
    'workload trail',
    'usage trail',
    'surface result',
    'surface line',
    'carrying the read',
    'the same part of the bullpen keeps carrying the read',
    'this read starts with',
    'the first glance',
    'because the full bullpen picture is not completely settled',
    'the workload trail explains',
    'the usage trail explains',
    'the run-prevention line gives',
    'current relief shape is easy to see',
    'relief shape starts there',
    'changed bullpen mix',
    'bullpen mix has been shifting',
    'the bullpen is under pressure',
    'limited flexibility',
)

BANNED_CAVEAT_PHRASES = (
    'usage is the anchor',
    'usage drives this',
    'roster picture incomplete',
    'roster detail is limited',
    'the caveat is simple',
    'this stays tied to usage',
    'source limit',
    'source limitation',
    'roster context',
    'available evidence',
    'available information',
    'narrative scope',
    'observation scope',
    'signal strength',
    'validation state',
    'confidence state',
    'this read is tied',
    'this read stays',
    'stops at usage',
)

ENVIRONMENT_INTRO_MARKERS = (
    'this is not one clean issue',
    'more than one thing tightening the picture',
    'not just one part of the pen',
)

DISCLOSURE_BODY_MARKERS = (
    'bullpen workload',
    'usage read',
    'roster read',
    'recent innings tell',
    'cleanest part of the read',
    'clearest clue',
    'roster edges',
    'on the mound',
    'cleanest part of the picture',
)

INTERNAL_PROCESS_PUBLIC_MARKERS = (
    'source limit',
    'source limitation',
    'roster context',
    'model confidence',
    'available evidence',
    'available information',
    'current data limitation',
    'narrative scope',
    'observation scope',
    'signal strength',
    'validation state',
    'confidence state',
    'methodology',
    'this read is tied',
    'this read stays',
    'stops at usage',
)


def _narrative_has_disclosure_caveat(narrative: str) -> bool:
    lower = narrative.lower()
    return any(marker in lower for marker in DISCLOSURE_BODY_MARKERS)


def _ending_sentence_from_narrative(narrative: str) -> str:
    closing = narrative.split('\n\n')[-1].strip()
    sentences = re.findall(r'[^.!?]+[.!?]', closing)
    return sentences[-1].strip() if sentences else closing


def _ending_family_from_sentence(sentence: str) -> str:
    lower = sentence.lower()
    if sentence.endswith('?'):
        return 'question'
    if lower.startswith('the next ') or 'next few games' in lower or 'next turn through the rotation' in lower:
        return 'watch_statement'
    if lower.startswith((
        'the main takeaway',
        'the useful takeaway',
        'that gives the staff',
        'that is the useful part',
    )):
        return 'takeaway'
    if any(marker in lower for marker in (
        'little margin',
        'less margin',
        'every clean inning',
        'gap between',
        'pressure is not only',
        'does not erase',
        'keeps the strong results',
    )):
        return 'implication'
    return 'observation'


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


def _sentence_shape(text):
    shape = re.sub(r'\b[A-Z]{2,4} Arm \d+\b', '{arm}', text or '')
    shape = re.sub(
        r'\b(?:Atlanta|San Diego|Texas|Houston|Detroit) Test(?:\'s)?\b',
        '{team}',
        shape,
    )
    shape = re.sub(r'\b\d+(?:\.\d+)?%?\b', '{num}', shape)
    shape = re.sub(r'[^a-z{} ]+', ' ', shape.lower())
    return ' '.join(shape.split())


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
    pitchers = [_pitcher(idx, f'Relief Arm {idx}') for idx in range(1, 6)]
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


def _foundation_capacity_context(
    *,
    capacity_state='healthy',
    resource_state='moderate',
    active=8,
    clean=5,
    anchor=1,
    leverage=2,
    trusted=2,
    depth=2,
    trusted_group=5,
    top_available=1,
    hierarchy_confidence='high',
    trust_unavailable=0,
):
    restricted = max(active - clean, 0)
    return {
        1: {
            'capability': 'bullpen_capacity_intelligence_v1',
            'resource_health': {
                'capacity_state': capacity_state,
                'resource_health_state': resource_state,
                'active_reliever_count': active,
                'bullpen_capacity': {
                    'capacity_state': capacity_state,
                    'active_reliever_count': active,
                    'active_restricted_reliever_count': restricted,
                    'clean_active_reliever_count': clean,
                },
                'organizational_resource_health': {
                    'resource_health_state': resource_state,
                },
            },
            'trust_hierarchy': {
                'anchor_count': anchor,
                'leverage_count': leverage,
                'trusted_count': trusted,
                'depth_count': depth,
                'unknown_count': 0,
                'trusted_group_size': trusted_group,
                'top_trust_bucket_available_count': top_available,
                'hierarchy_confidence': hierarchy_confidence,
            },
            'capacity_loss': {
                'status': 'clear',
                'unavailable_capacity_pct': 0,
                'unknown_limited_read_capacity_pct': 0,
                'limitations': [],
            },
            'trust_capacity_loss': {
                'status': 'clear',
                'trust_arms_available': max(anchor + leverage - trust_unavailable, 0),
                'trust_arms_total': anchor + leverage,
                'trust_arms_unavailable': trust_unavailable,
                'trust_capacity_unavailable_pct': 0,
                'limitations': [],
            },
        }
    }


def _with_bullpen_identity(capacity_by_team, *, team_id=1, identity_updates=None):
    capacity = capacity_by_team[team_id]
    identity = build_bullpen_identity(capacity)
    if identity_updates:
        identity = {
            **identity,
            **identity_updates,
        }
    capacity['bullpen_identity'] = identity
    return capacity_by_team


def _broad_light_team_inputs(**kwargs):
    pitchers = [_pitcher(idx, f'Flexible Arm {idx}') for idx in range(1, 9)]
    records = [_record(pitcher, STATUS_AVAILABLE) for pitcher in pitchers]
    logs = {
        pitcher.id: [_log(pitcher.id, 1, 10)]
        for pitcher in pitchers
    }
    return _team_inputs(records, logs, **kwargs)


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


def _crowded_observation_feed():
    teams = [
        (701, 'Atlanta Test', 'ATL', [48, 42, 30, 18, 12, 8]),
        (702, 'San Diego Test', 'SD', [50, 40, 26, 16, 11, 9]),
        (703, 'Texas Test', 'TEX', [46, 43, 28, 17, 10, 8]),
        (704, 'Houston Test', 'HOU', [52, 38, 27, 16, 9, 8]),
        (705, 'Detroit Test', 'DET', [49, 41, 25, 18, 10, 7]),
    ]
    records = []
    log_groups = []
    bullpens = []
    for team_id, team_name, abbr, pitch_totals in teams:
        _, team_records, logs = _fixture_team(
            team_id,
            team_name,
            abbr,
            pitch_totals,
            available_count=4,
            high_risk_indices=(0, 1),
            trust_indices=(0, 1),
        )
        records.extend(team_records)
        log_groups.append(logs)
        bullpens.append(_bullpen_era(team_id, team_name, abbr, 2.75, earned_runs=18))
    return build_four_beat_story_feed(
        records,
        _merge_logs(*log_groups),
        reference_date=REF,
        season_era={'bullpens': bullpens},
    )


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
    assert 'leaning on it hard tonight' in sustainability['story']['beats'][0]['text']
    assert sustainability['story']['title'] == sustainability['story']['story_voice']['headline']
    assert sustainability['story']['story_prose']['prose_path']

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
    assert "tonight's usable depth is thin" in hidden['story']['beats'][0]['text']
    assert hidden['story']['title'] == hidden['story']['story_voice']['headline']
    assert hidden['story']['story_prose']['prose_path']
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
    assert facts['primary_observation'] == story['beats'][0]['text']
    assert facts['public_headline'] == story['title']
    assert story['title'] == story['story_voice']['headline']
    assert facts['supporting_context']
    assert facts['pressure_source']
    assert facts['workload_pattern']
    assert facts['capacity_context']
    assert facts['watch_question']
    assert facts['confidence'] == 'limited'
    assert facts['disclosure'] == DISCLOSURE_LIMITED_BULLPEN_PICTURE
    assert render_story_disclosure_note(facts) is None
    assert 'disclosure_note' not in story
    assert _narrative_has_disclosure_caveat(narrative) is False
    assert narrative.count('\n\n') == 2
    assert narrative.split('\n\n')[-1] == story['story_voice']['consequence_sentence']
    assert story['team_name'] in narrative
    assert facts['primary_observation'] not in narrative
    assert facts['watch_question'] not in narrative
    assert facts['disclosure'] not in narrative
    assert 'The pressure source is' not in narrative
    assert 'The thing to watch next is whether' not in narrative


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
        'preferred',
        'should use',
        'manager should',
        'fatigue score',
        'confidence score',
        'HIGH or CRITICAL',
        'pressure source',
        'workload pattern is',
        'the thing to watch next is whether',
    ):
        assert forbidden.lower() not in lower


def test_story_context_adds_resource_pool_context_without_state_labels():
    team_inputs = _broad_light_team_inputs(
        capacity_by_team=_foundation_capacity_context(
            capacity_state='healthy',
            resource_state='strained',
            active=8,
            clean=5,
            anchor=1,
            leverage=2,
            trusted_group=5,
        ),
    )
    inputs = compute_team_story_inputs(team_inputs)
    story = assemble_story(RULE_PRESSURE_DISTRIBUTION, inputs)
    narrative = story['narrative']
    lower = narrative.lower()

    assert story['computed']['story_context_integration']['applied'] is True
    assert story['computed']['story_context_integration']['reason'] == (
        'top_structure_with_resource_strain'
    )
    context_text = story['story_facts']['bullpen_context'].lower()
    assert any(
        phrase in context_text
        for phrase in (
            'back-end shape',
            'familiar finish',
            'late innings',
        )
    )
    assert story['story_voice']['applied'] is True
    assert story['story_voice']['human_frame'] in narrative
    assert story['story_voice']['evidence_sentence'] in narrative
    assert story['story_voice']['consequence_sentence'] in narrative
    assert narrative_contains_forbidden_language(narrative) is False
    for leaked in (
        'capacity state',
        'resource health',
        'coverage safety',
        'trust hierarchy',
        'resource pool',
        'active count',
        'trusted lane',
        'role_change_detection',
        'ranking_applied',
        'selection_made',
        'prediction_applied',
    ):
        assert leaked not in lower


def test_story_context_adds_clean_trusted_lane_context_when_narrow():
    team_inputs = _thin_concentrated_team_inputs(
        capacity_by_team=_foundation_capacity_context(
            capacity_state='reduced',
            resource_state='moderate',
            active=7,
            clean=4,
            anchor=0,
            leverage=1,
            trusted=2,
            trusted_group=3,
            top_available=1,
        ),
    )
    inputs = compute_team_story_inputs(team_inputs)
    inputs['clean_options'] = [
        {'pitcher_id': idx, 'name': f'Clean Arm {idx}'}
        for idx in range(1, 5)
    ]
    inputs['clean_trust_options'] = [
        {'pitcher_id': 1, 'name': 'Clean Arm 1'}
    ]
    story = assemble_story(
        RULE_STRESS_TRANSFER,
        inputs,
        lead={
            'dimension': LEAD_TRUST_LANE_SHALLOW,
            'signal_skeleton_key': f'lead_signal:{LEAD_TRUST_LANE_SHALLOW}',
            'evidence_skeleton_key': f'lead_evidence:{LEAD_TRUST_LANE_SHALLOW}',
        },
    )
    narrative = story['narrative']
    lower = narrative.lower()

    assert story['computed']['story_context_integration']['applied'] is True
    assert story['computed']['story_context_integration']['reason'] == (
        'clean_trusted_lane_narrow'
    )
    context_text = story['story_facts']['bullpen_context'].lower()
    assert any(
        phrase in context_text
        for phrase in (
            'first few choices',
            'comfort drops fast',
            'first layer and the rest',
            'first few names',
        )
    )
    assert story['story_voice']['applied'] is True
    assert story['story_voice']['human_frame'] in narrative
    assert story['story_voice']['evidence_sentence'] in narrative
    assert story['story_voice']['consequence_sentence'] in narrative
    assert 'clean trusted lane' not in lower
    assert 'trusted lane' not in lower
    assert 'should pitch' not in lower
    assert 'recommend' not in lower
    assert narrative_contains_forbidden_language(narrative) is False


def test_story_context_ignores_insufficient_role_change_history_publicly():
    team_inputs = _broad_light_team_inputs(
        capacity_by_team=_foundation_capacity_context(
            capacity_state='healthy',
            resource_state='strained',
            active=8,
            clean=5,
            anchor=1,
            leverage=2,
            trusted_group=5,
        ),
    )
    inputs = compute_team_story_inputs(team_inputs)
    inputs['role_change_detection'] = {'status': 'insufficient_history'}
    story = assemble_story(RULE_PRESSURE_DISTRIBUTION, inputs)
    narrative = story['narrative']
    lower = narrative.lower()

    assert story['computed']['story_context_integration']['applied'] is True
    assert 'insufficient_history' not in lower
    assert 'insufficient history' not in lower
    assert 'role change' not in lower
    assert 'role_change_detection' not in lower


def test_story_context_renderer_still_works_without_new_intelligence_fields():
    team_inputs = _broad_light_team_inputs()
    inputs = compute_team_story_inputs(team_inputs)
    story = assemble_story(RULE_PRESSURE_DISTRIBUTION, inputs)

    assert story['story_facts']['bullpen_context'] is None
    assert story['computed']['story_context_integration']['applied'] is False
    assert story['narrative']
    assert narrative_contains_forbidden_language(story['narrative']) is False


def test_story_context_replaces_generic_middle_instead_of_appending_explanation():
    team_inputs = _broad_light_team_inputs(
        capacity_by_team=_foundation_capacity_context(
            capacity_state='healthy',
            resource_state='strained',
            active=8,
            clean=5,
            anchor=1,
            leverage=2,
            trusted_group=5,
        ),
    )
    story = assemble_story(
        RULE_PRESSURE_DISTRIBUTION,
        compute_team_story_inputs(team_inputs),
    )
    paragraphs = [item.strip() for item in story['narrative'].split('\n\n')]
    middle = paragraphs[1].lower()

    assert len(paragraphs) == 3
    assert story['story_voice']['applied'] is True
    assert paragraphs[0] == story['story_voice']['human_frame']
    assert paragraphs[1] == story['story_voice']['evidence_sentence']
    assert paragraphs[2] == story['story_voice']['consequence_sentence']
    assert 'there is room to maneuver because' not in middle
    assert 'flexibility shows up when' not in middle
    assert middle.count('.') <= 3


def test_identity_story_texture_metadata_stays_available_without_public_label_leak():
    team_inputs = _broad_light_team_inputs(
        capacity_by_team=_with_bullpen_identity(_foundation_capacity_context()),
    )
    story = assemble_story(
        RULE_PRESSURE_DISTRIBUTION,
        compute_team_story_inputs(team_inputs),
    )
    integration = story['computed']['story_identity_integration']
    narrative = story['narrative']
    lower = narrative.lower()

    assert integration['capability'] == STORY_IDENTITY_CAPABILITY
    assert integration['applied'] is True
    assert story['story_facts']['identity_story_context'] == integration['text']
    assert story['story_facts']['story_identity_integration'] == integration
    assert story['slot_sources']['story_identity_integration'] == 'bullpen_identity_v1'
    assert story['story_voice']['applied'] is True
    assert story['story_voice']['human_frame'] in narrative
    assert integration['text'] not in narrative
    for label in IDENTITY_LABELS.values():
        assert label not in narrative
    for forbidden in (
        'recommend',
        'prediction',
        'betting',
        'ranking',
        'should use',
        'manager should',
        'confidence score',
    ):
        assert forbidden not in lower
    assert narrative_contains_forbidden_language(narrative) is False


def test_identity_story_texture_does_not_change_rule_selection():
    base_team_inputs = _broad_light_team_inputs()
    identity_team_inputs = _broad_light_team_inputs(
        capacity_by_team=_with_bullpen_identity(_foundation_capacity_context()),
    )

    base_eval = evaluate_team_rules(base_team_inputs)
    identity_eval = evaluate_team_rules(identity_team_inputs)
    base_rules = [
        (item['rule_key'], item['status'], item['can_fire'], item.get('conditions'))
        for item in base_eval['evaluations']
    ]
    identity_rules = [
        (item['rule_key'], item['status'], item['can_fire'], item.get('conditions'))
        for item in identity_eval['evaluations']
    ]

    assert identity_rules == base_rules

    base_story = assemble_story(
        RULE_PRESSURE_DISTRIBUTION,
        compute_team_story_inputs(base_team_inputs),
    )
    identity_story = assemble_story(
        RULE_PRESSURE_DISTRIBUTION,
        compute_team_story_inputs(identity_team_inputs),
    )

    assert identity_story['story_id'] == base_story['story_id']
    assert identity_story['rule_key'] == base_story['rule_key']
    assert identity_story['strength'] == base_story['strength']
    assert identity_story['lead_fields'] == base_story['lead_fields']
    assert identity_story['computed']['story_identity_integration']['applied'] is True


def test_unknown_or_low_confidence_identity_does_not_force_identity_language():
    capacity_by_team = _with_bullpen_identity(
        _foundation_capacity_context(),
        identity_updates={
            'identity_key': IDENTITY_UNKNOWN,
            'identity_label': IDENTITY_LABELS[IDENTITY_UNKNOWN],
            'identity_summary': 'Existing bullpen intelligence is too incomplete to assign a stable structural identity.',
            'confidence': 'low',
        },
    )
    story = assemble_story(
        RULE_PRESSURE_DISTRIBUTION,
        compute_team_story_inputs(_broad_light_team_inputs(capacity_by_team=capacity_by_team)),
    )
    integration = story['computed']['story_identity_integration']
    narrative = story['narrative']

    assert integration['applied'] is False
    assert story['story_facts']['identity_story_context'] is None
    assert integration['text'] is None
    for phrase in (
        'usually survives by spreading innings',
        'recognizable backbone',
        'the challenge is not just tonight',
        'coverage comes less from one obvious answer',
    ):
        assert phrase not in narrative.lower()
    assert narrative_contains_forbidden_language(narrative) is False


def test_identity_story_texture_varies_deterministically_across_teams():
    teams = [
        (108, 'Los Angeles Angels', 'LAA'),
        (109, 'Arizona Diamondbacks', 'AZ'),
        (110, 'Baltimore Orioles', 'BAL'),
        (111, 'Boston Red Sox', 'BOS'),
        (112, 'Chicago Cubs', 'CHC'),
    ]
    first_pass = []
    second_pass = []

    for team_id, team_name, abbr in teams:
        capacity_by_team = _foundation_capacity_context()
        capacity_by_team[team_id] = capacity_by_team.pop(1)
        capacity_by_team = _with_bullpen_identity(capacity_by_team, team_id=team_id)
        team = {'team_id': team_id, 'team_name': team_name, 'team_abbreviation': abbr}
        inputs = compute_team_story_inputs(
            _broad_light_team_inputs(team=team, capacity_by_team=capacity_by_team)
        )
        first_pass.append(
            assemble_story(RULE_PRESSURE_DISTRIBUTION, inputs)['computed'][
                'story_identity_integration'
            ]['text']
        )
        second_pass.append(
            assemble_story(RULE_PRESSURE_DISTRIBUTION, inputs)['computed'][
                'story_identity_integration'
            ]['text']
        )

    assert first_pass == second_pass
    assert len(set(first_pass)) >= 2


def test_leverage_identity_story_texture_has_safe_deterministic_variation():
    teams = [
        (109, 'Arizona Diamondbacks', 'AZ'),
        (114, 'Cleveland Guardians', 'CLE'),
        (119, 'Los Angeles Dodgers', 'LAD'),
        (121, 'New York Mets', 'NYM'),
        (137, 'San Francisco Giants', 'SF'),
        (138, 'St. Louis Cardinals', 'STL'),
        (142, 'Minnesota Twins', 'MIN'),
    ]
    first_pass = []
    second_pass = []

    for team_id, team_name, abbr in teams:
        capacity_by_team = _foundation_capacity_context(
            anchor=1,
            leverage=5,
            trusted=1,
            depth=1,
            trusted_group=7,
        )
        capacity_by_team[team_id] = capacity_by_team.pop(1)
        capacity_by_team = _with_bullpen_identity(capacity_by_team, team_id=team_id)
        team = {'team_id': team_id, 'team_name': team_name, 'team_abbreviation': abbr}
        inputs = compute_team_story_inputs(
            _broad_light_team_inputs(team=team, capacity_by_team=capacity_by_team)
        )
        story = assemble_story(RULE_PRESSURE_DISTRIBUTION, inputs)
        first_pass.append(story['computed']['story_identity_integration']['text'])
        second_pass.append(
            assemble_story(RULE_PRESSURE_DISTRIBUTION, inputs)['computed'][
                'story_identity_integration'
            ]['text']
        )
        assert story['computed']['bullpen_identity']['identity_key'] == IDENTITY_LEVERAGE_HEAVY

    assert first_pass == second_pass
    assert len(set(first_pass)) >= 4
    blocked = (
        'best reliever',
        'should use',
        'must use',
        'projected',
        'expected',
        'ranked',
        'bet',
        'lock',
    )
    for phrase in first_pass:
        lower = phrase.lower()
        for blocked_phrase in blocked:
            assert blocked_phrase not in lower
        for label in IDENTITY_LABELS.values():
            assert label.lower() not in lower


def _sample_story_facts(
    team_id: int,
    team_name: str,
    abbr: str,
    *,
    disclosure: bool = True,
    watch_question: str | None = None,
    primary_observation: str | None = None,
    supporting_context: str | None = None,
    pressure_source: str | None = None,
    workload_pattern: str | None = None,
    capacity_context: str | None = None,
    rotation_context: str | None = None,
    stability_context: str | None = None,
    environment_context: str | None = None,
    bullpen_context: str | None = None,
    bullpen_context_reason: str | None = None,
) -> dict:
    return {
        'capability': STORY_FACT_LAYER_CAPABILITY,
        'version': 'test',
        'team': {
            'team_id': team_id,
            'team_name': team_name,
            'team_abbreviation': abbr,
        },
        'primary_observation': primary_observation or f'The {team_name} have a narrower bullpen path tonight.',
        'supporting_context': supporting_context or (
            'The recent workload has clustered around the top 3 relievers, '
            'who have handled 72% of relief pitches in the window, while 3 '
            'of 8 bullpen arms are available.'
        ),
        'pressure_source': pressure_source or 'The pressure source is recent work being concentrated around a smaller set of relievers.',
        'workload_pattern': workload_pattern or 'The workload pattern is narrow: the top 3 relievers have taken 72% of the recent relief work.',
        'capacity_context': capacity_context,
        'rotation_context': rotation_context,
        'stability_context': stability_context,
        'environment_context': environment_context,
        'bullpen_context': bullpen_context,
        'bullpen_context_integration': {
            'applied': bool(bullpen_context),
            'text': bullpen_context,
            'reason': bullpen_context_reason,
            'sources': [],
            'ranking_applied': False,
            'selection_made': False,
            'prediction_applied': False,
            'limitations': [],
        },
        'watch_question': (
            watch_question
            or 'The thing to watch next is whether the same relievers remain at the center of the workload.'
        ),
        'confidence': 'limited' if disclosure else 'supported',
        'disclosure': DISCLOSURE_LIMITED_BULLPEN_PICTURE if disclosure else None,
    }


def test_renderer_omits_internal_disclosure_language_deterministically():
    teams = [
        (108, 'Los Angeles Angels', 'LAA'),
        (109, 'Arizona Diamondbacks', 'ARI'),
        (111, 'Boston Red Sox', 'BOS'),
        (112, 'Chicago Cubs', 'CHC'),
        (113, 'Cincinnati Reds', 'CIN'),
        (114, 'Cleveland Guardians', 'CLE'),
        (115, 'Colorado Rockies', 'COL'),
        (116, 'Detroit Tigers', 'DET'),
    ]
    facts = [_sample_story_facts(team_id, team_name, abbr) for team_id, team_name, abbr in teams]

    first = [render_story_narrative(item) for item in facts]
    second = [render_story_narrative(item) for item in facts]
    notes = [render_story_disclosure_note(item) for item in facts]

    assert first == second
    assert notes == [render_story_disclosure_note(item) for item in facts]
    assert notes == [None] * len(facts)
    for narrative, note in zip(first, notes):
        lower = narrative.lower()
        assert DISCLOSURE_LIMITED_BULLPEN_PICTURE not in narrative
        assert narrative_contains_forbidden_language(narrative) is False
        assert note is None
        assert _narrative_has_disclosure_caveat(narrative) is False
        for marker in INTERNAL_PROCESS_PUBLIC_MARKERS:
            assert marker not in lower


def test_renderer_prefers_strong_endings_over_footer_meta_commentary():
    facts = [
        _sample_story_facts(team_id, team_name, abbr)
        for team_id, team_name, abbr in [
            (125, 'Miami Marlins', 'MIA'),
            (126, 'Milwaukee Brewers', 'MIL'),
            (127, 'New York Yankees', 'NYY'),
            (128, 'Baltimore Orioles', 'BAL'),
            (129, 'Chicago White Sox', 'CWS'),
        ]
    ]

    for item in facts:
        narrative = render_story_narrative(item)
        note = render_story_disclosure_note(item)
        closing = narrative.split('\n\n')[-1]
        combined = narrative.lower()

        assert note is None
        assert _narrative_has_disclosure_caveat(narrative) is False
        assert closing
        for phrase in AWKWARD_RENDERER_PHRASES:
            assert phrase not in combined
        for phrase in BANNED_CAVEAT_PHRASES:
            assert phrase not in combined
        for marker in INTERNAL_PROCESS_PUBLIC_MARKERS:
            assert marker not in combined


def test_renderer_uses_mixed_ending_families_across_sample_set():
    teams = [
        (117, 'Houston Astros', 'HOU'),
        (118, 'Kansas City Royals', 'KC'),
        (119, 'Los Angeles Dodgers', 'LAD'),
        (120, 'Washington Nationals', 'WSH'),
        (121, 'New York Mets', 'NYM'),
        (133, 'Oakland Athletics', 'ATH'),
        (134, 'Pittsburgh Pirates', 'PIT'),
        (135, 'San Diego Padres', 'SD'),
        (136, 'Seattle Mariners', 'SEA'),
        (137, 'San Francisco Giants', 'SF'),
    ]
    facts = [
        _sample_story_facts(team_id, team_name, abbr, disclosure=False)
        for team_id, team_name, abbr in teams
    ]

    narratives = [render_story_narrative(item) for item in facts]
    endings = [_ending_sentence_from_narrative(narrative) for narrative in narratives]
    families = [_ending_family_from_sentence(ending) for ending in endings]

    assert narratives == [render_story_narrative(item) for item in facts]
    assert len(set(endings)) >= 3
    assert len(set(families)) >= 2
    assert families.count('question') < len(families)
    for ending in endings:
        lower = ending.lower()
        assert not lower.startswith('the next question is')
        assert not lower.startswith('from here, the question is')
        assert 'worth watching to see whether' not in lower


def test_renderer_varies_openings_without_repeating_team_have_pattern():
    teams = [
        (138, 'St. Louis Cardinals', 'STL'),
        (139, 'Tampa Bay Rays', 'TB'),
        (140, 'Texas Rangers', 'TEX'),
        (141, 'Toronto Blue Jays', 'TOR'),
        (142, 'Minnesota Twins', 'MIN'),
        (143, 'Philadelphia Phillies', 'PHI'),
    ]
    facts = [
        _sample_story_facts(team_id, team_name, abbr, disclosure=False)
        for team_id, team_name, abbr in teams
    ]

    openers = [render_story_narrative(item).split('. ')[0] for item in facts]

    assert len(set(openers)) >= 4
    assert not all(opener.startswith('The ') for opener in openers)
    for (_, team_name, _), opener in zip(teams, openers):
        assert not opener.startswith(f'The {team_name} have')


def _archetype_story_fact_samples() -> dict[str, dict]:
    return {
        ARCHETYPE_WORKLOAD_CONCENTRATION: _sample_story_facts(
            201,
            'Workload Club',
            'WLD',
            disclosure=False,
        ),
        ARCHETYPE_THIN_TRUSTED_GROUP: _sample_story_facts(
            202,
            'Trust Club',
            'TRU',
            disclosure=False,
            supporting_context=(
                'Recent relief work has been spread across 6 relievers, '
                'averaging 18 pitches per participating arm.'
            ),
            pressure_source=(
                'The pressure source is the trusted late-inning layer, where '
                'the usable group and the preferred group do not fully line up.'
            ),
            workload_pattern=(
                'The workload pattern is broad: 6 relievers have shared the work '
                'at 18 pitches per participating arm.'
            ),
            watch_question=(
                'The thing to watch next is whether the late-inning work can move '
                'through more than the same trusted lane.'
            ),
        ),
        ARCHETYPE_CAPACITY_CONSTRAINT: _sample_story_facts(
            203,
            'Capacity Club',
            'CAP',
            disclosure=False,
            supporting_context='The current read is built around recent relief usage and the available bullpen layer.',
            pressure_source='The pressure source is a thinner usable layer behind the late-inning plan.',
            workload_pattern='The workload pattern sits between those poles, with 5 relievers sharing 88 recent relief pitches.',
            capacity_context='The available group is already thin, leaving fewer usable arms than a normal night.',
            watch_question='The next useful read is whether one more bullpen-heavy game exposes the thin usable layer.',
        ),
        ARCHETYPE_ROTATION_SPILLOVER: _sample_story_facts(
            204,
            'Rotation Club',
            'ROT',
            disclosure=False,
            supporting_context='Recent relief usage has not centered on one narrow group.',
            pressure_source='The shape comes from workload distribution rather than one narrow lane.',
            workload_pattern='The workload pattern sits between those poles, with 5 relievers sharing 92 recent relief pitches.',
            rotation_context='The bullpen has been covering more of the game than usual.',
            watch_question='The next useful read is whether starters cover more innings before the bullpen takes over.',
        ),
        ARCHETYPE_STABILITY_EROSION: _sample_story_facts(
            205,
            'Churn Club',
            'CHN',
            disclosure=False,
            supporting_context='Recent relief usage has not centered on one narrow group.',
            pressure_source='The shape comes from workload distribution rather than one narrow lane.',
            workload_pattern='The workload pattern sits between those poles, with 5 relievers sharing 82 recent relief pitches.',
            stability_context='The bullpen group has not looked exactly the same from week to week.',
            watch_question='The thing to watch next is whether the recent usage pattern changes after the next completed game.',
        ),
        ARCHETYPE_STABILITY_RECOVERY: _sample_story_facts(
            206,
            'Recovery Club',
            'REC',
            disclosure=False,
            supporting_context=(
                'Recent relief work has been spread across 6 relievers, '
                'averaging 16 pitches per participating arm.'
            ),
            pressure_source='The shape comes from recent work being spread across more of the bullpen.',
            workload_pattern=(
                'The workload pattern is broad: 6 relievers have shared the work '
                'at 16 pitches per participating arm.'
            ),
            stability_context='The bullpen group has looked more settled, with the same group carrying recent innings.',
            watch_question='The next useful read is whether the work stays spread across the group.',
        ),
        ARCHETYPE_MULTI_SOURCE_PRESSURE: _sample_story_facts(
            207,
            'Layered Club',
            'LAY',
            disclosure=False,
            supporting_context='The recent workload has clustered around the top 3 relievers, who have handled 68% of relief pitches in the window, while 4 of 8 bullpen arms are available.',
            pressure_source='The pressure source is workload concentration meeting a smaller usable group.',
            workload_pattern='The workload pattern is narrow: the top 3 relievers have taken 68% of the recent relief work.',
            capacity_context='The available group is already thin.',
            rotation_context='Extra outs have been finding their way to the bullpen lately.',
            watch_question='The thing to watch next is whether the recent usage pattern changes after the next completed game.',
        ),
        ARCHETYPE_FLEXIBLE_BULLPEN: _sample_story_facts(
            208,
            'Flexible Club',
            'FLX',
            disclosure=False,
            supporting_context=(
                'Recent relief work has been spread across 7 relievers, '
                'averaging 14 pitches per participating arm.'
            ),
            pressure_source='The shape comes from a deeper usable layer behind the late-inning plan.',
            workload_pattern=(
                'The workload pattern is broad: 7 relievers have shared the work '
                'at 14 pitches per participating arm.'
            ),
            watch_question='The next useful read is whether that broad, usable shape still holds after the next completed game.',
        ),
        ARCHETYPE_RUN_PREVENTION_MASK: _sample_story_facts(
            209,
            'Results Club',
            'RES',
            disclosure=False,
            primary_observation='The Results Club bullpen has pitched well this year, but they are leaning on it hard tonight.',
            supporting_context='The season run prevention has been strong at a 2.75 ERA, but recent usage is averaging 34 pitches per participating reliever.',
            pressure_source='The season run-prevention line is part of the read, but it is not the whole bullpen picture.',
            workload_pattern='The workload pattern is narrow: the top 3 relievers have taken 64% of the recent relief work.',
            watch_question='The thing to watch next is whether the same relievers remain at the center of the workload.',
        ),
    }


def test_story_archetype_selection_is_deterministic():
    samples = _archetype_story_fact_samples()

    for expected, facts in samples.items():
        assert select_story_archetype(facts) == expected
        assert select_story_archetype(dict(facts)) == expected


def test_archetype_narratives_are_deterministic_and_structurally_distinct():
    samples = _archetype_story_fact_samples()
    narratives = {
        archetype: render_story_narrative(facts)
        for archetype, facts in samples.items()
    }

    assert narratives == {
        archetype: render_story_narrative(facts)
        for archetype, facts in samples.items()
    }
    assert len(set(narratives.values())) == len(samples)
    assert len({text.split('\n\n')[0] for text in narratives.values()}) >= 8
    assert len({text.split('\n\n')[1] for text in narratives.values()}) >= 8
    assert narratives[ARCHETYPE_WORKLOAD_CONCENTRATION].split('\n\n')[0] != narratives[ARCHETYPE_FLEXIBLE_BULLPEN].split('\n\n')[0]
    assert narratives[ARCHETYPE_CAPACITY_CONSTRAINT].split('\n\n')[1] != narratives[ARCHETYPE_ROTATION_SPILLOVER].split('\n\n')[1]


def test_same_archetype_uses_intelligence_angle_for_team_identity():
    late_structure = _sample_story_facts(
        119,
        'Los Angeles Dodgers',
        'LAD',
        disclosure=False,
        supporting_context=(
            'Recent relief work has been spread across 8 relievers, '
            'averaging 14 pitches per participating arm.'
        ),
        pressure_source='The shape comes from recent work being spread across more of the bullpen.',
        workload_pattern=(
            'The workload pattern is broad: 8 relievers have shared the work '
            'at 14 pitches per participating arm.'
        ),
        bullpen_context='The late innings still look pretty normal.',
        bullpen_context_reason='top_structure_with_resource_strain',
        watch_question='The next useful read is whether that broad, usable shape still holds.',
    )
    wide_routes = _sample_story_facts(
        109,
        'Arizona Diamondbacks',
        'AZ',
        disclosure=False,
        supporting_context=(
            'Recent relief work has been spread across 8 relievers, '
            'averaging 14 pitches per participating arm.'
        ),
        pressure_source='The shape comes from recent work being spread across more of the bullpen.',
        workload_pattern=(
            'The workload pattern is broad: 8 relievers have shared the work '
            'at 14 pitches per participating arm.'
        ),
        watch_question='The next useful read is whether that broad, usable shape still holds.',
    )

    assert select_story_archetype(late_structure) == ARCHETYPE_FLEXIBLE_BULLPEN
    assert select_story_archetype(wide_routes) == ARCHETYPE_FLEXIBLE_BULLPEN
    assert team_story_narrative._story_situation(late_structure, ARCHETYPE_FLEXIBLE_BULLPEN) == (
        team_story_narrative.SITUATION_LATE_INNINGS_STABLE_MIDDLE_TESTED
    )
    assert team_story_narrative._story_situation(wide_routes, ARCHETYPE_FLEXIBLE_BULLPEN) == (
        team_story_narrative.SITUATION_FLEXIBILITY_WORK_SPREAD_OUT
    )

    late_text = render_story_narrative(late_structure).lower()
    wide_text = render_story_narrative(wide_routes).lower()

    assert late_text != wide_text
    assert any(
        phrase in late_text
        for phrase in (
            'back-end shape',
            'familiar finish',
            'late innings',
        )
    )
    assert any(
        phrase in wide_text
        for phrase in (
            'several routes',
            'actually been part of the path',
            'few different paths',
            'work has been moving around',
            'more than one way through',
        )
    )
    for leaked in ('resource pool', 'trusted lane', 'active count', 'coverage safety'):
        assert leaked not in late_text
        assert leaked not in wide_text


def test_story_situation_framing_is_selected_deterministically():
    capacity_facts = _sample_story_facts(
        401,
        'Situation Club',
        'SIT',
        disclosure=False,
        supporting_context='The current read is built around recent relief usage and the available bullpen layer.',
        pressure_source='The pressure source is a thinner usable layer behind the late-inning plan.',
        workload_pattern='The workload pattern sits between those poles, with 5 relievers sharing 88 recent relief pitches.',
        capacity_context='The available group is already thin, leaving fewer usable arms than a normal night.',
        bullpen_context='Once the game gets past the obvious choices, there is not much room for error.',
        bullpen_context_reason='dependable_group_narrow',
    )

    archetype = select_story_archetype(capacity_facts)
    first = team_story_narrative._story_situation(capacity_facts, archetype)
    second = team_story_narrative._story_situation(dict(capacity_facts), archetype)
    narrative = render_story_narrative(capacity_facts).lower()

    assert archetype == ARCHETYPE_CAPACITY_CONSTRAINT
    assert first == second == team_story_narrative.SITUATION_FIRST_MOVE_OK_THEN_THIN
    assert any(
        phrase in narrative
        for phrase in (
            'first bullpen decision',
            'first relief move',
            'second relief decision',
            'second or third answer',
            'multiple turns from the pen',
        )
    )


def test_same_archetype_can_render_different_situations():
    close_game_questions = _sample_story_facts(
        402,
        'Full Board Club',
        'FBC',
        disclosure=False,
        supporting_context='The current read is built around recent relief usage and the available bullpen layer.',
        pressure_source='The pressure source is a thinner usable layer behind the late-inning plan.',
        workload_pattern='The workload pattern sits between those poles, with 5 relievers sharing 88 recent relief pitches.',
        capacity_context='The available group is smaller than usual, leaving fewer places to turn.',
        bullpen_context=(
            'On paper the bullpen still has names. The question is how many of those options you would really feel '
            'comfortable handing the game to.'
        ),
        bullpen_context_reason='thin_active_capacity_margin',
    )
    first_move_thin = _sample_story_facts(
        403,
        'Short Answer Club',
        'SAC',
        disclosure=False,
        supporting_context='The current read is built around recent relief usage and the available bullpen layer.',
        pressure_source='The pressure source is a thinner usable layer behind the late-inning plan.',
        workload_pattern='The workload pattern sits between those poles, with 5 relievers sharing 88 recent relief pitches.',
        capacity_context='The available group is already thin, leaving fewer usable arms than a normal night.',
        bullpen_context='Once the game gets past the obvious choices, there is not much room for error.',
        bullpen_context_reason='dependable_group_narrow',
    )

    assert select_story_archetype(close_game_questions) == ARCHETYPE_CAPACITY_CONSTRAINT
    assert select_story_archetype(first_move_thin) == ARCHETYPE_CAPACITY_CONSTRAINT
    assert team_story_narrative._story_situation(close_game_questions, ARCHETYPE_CAPACITY_CONSTRAINT) == (
        team_story_narrative.SITUATION_FULL_BOARD_CLOSE_GAME_QUESTIONS
    )
    assert team_story_narrative._story_situation(first_move_thin, ARCHETYPE_CAPACITY_CONSTRAINT) == (
        team_story_narrative.SITUATION_FIRST_MOVE_OK_THEN_THIN
    )
    assert render_story_narrative(close_game_questions) != render_story_narrative(first_move_thin)


def test_narratives_hide_metric_language_inside_baseball_observations():
    samples = [
        _sample_story_facts(
            301,
            'Short Board Club',
            'SBC',
            disclosure=False,
            supporting_context=(
                'The recent workload has clustered around the top 3 relievers, '
                'who have handled 72% of relief pitches in the window, while 3 '
                'of 8 bullpen arms are available.'
            ),
            pressure_source='The pressure source is a thinner usable layer behind the late-inning plan.',
            workload_pattern='The workload pattern is narrow: the top 3 relievers have taken 72% of the recent relief work.',
            capacity_context='The available group is already thin, leaving fewer usable arms than a normal night.',
        ),
        _sample_story_facts(
            302,
            'Wide Route Club',
            'WRC',
            disclosure=False,
            supporting_context=(
                'Recent relief work has been spread across 9 relievers, '
                'averaging 29.6 pitches per participating arm.'
            ),
            pressure_source='The shape comes from recent work being spread across more of the bullpen.',
            workload_pattern=(
                'The workload pattern is broad: 9 relievers have shared the work '
                'at 29.6 pitches per participating arm.'
            ),
        ),
        _sample_story_facts(
            303,
            'Same Few Club',
            'SFC',
            disclosure=False,
            supporting_context=(
                'The recent workload has clustered around the top 3 relievers, '
                'who have handled 72% of relief pitches in the window.'
            ),
            pressure_source='The pressure source is recent work being concentrated around a smaller set of relievers.',
            workload_pattern='The workload pattern is narrow: the top 3 relievers have taken 72% of the recent relief work.',
        ),
    ]
    narratives = [render_story_narrative(item).lower() for item in samples]

    for narrative in narratives:
        assert narrative_contains_forbidden_language(narrative) is False
        assert not re.search(r'\b\d+\s+of\s+\d+\b', narrative)
        assert '%' not in narrative
        for fragment in (
            'pitches per participating arm',
            'per participating reliever',
            'top 3 relievers',
            'spread across 9 relievers',
            '9 relievers',
            '29.6 pitches',
            '72%',
            'full bullpen count',
        ):
            assert fragment not in narrative

    combined = ' '.join(narratives)
    assert any(
        phrase in combined
        for phrase in (
            'choices get thin',
            'not many comfortable pivots',
            'shorter list of usable choices',
            'harder part is what comes after',
            'short board',
        )
    )
    assert 'different hands' in combined or 'same few names' in combined


def test_situation_specific_stories_avoid_state_labels_and_internal_language():
    samples = [
        *_archetype_story_fact_samples().values(),
        _sample_story_facts(
            404,
            'Role History Club',
            'RHC',
            disclosure=False,
            bullpen_context='The late innings still look pretty normal.',
            bullpen_context_reason='top_structure_with_resource_strain',
            supporting_context=(
                'Recent relief work has been spread across 8 relievers, '
                'averaging 14 pitches per participating arm.'
            ),
            pressure_source='The shape comes from recent work being spread across more of the bullpen.',
            workload_pattern=(
                'The workload pattern is broad: 8 relievers have shared the work '
                'at 14 pitches per participating arm.'
            ),
        ),
    ]

    for narrative in (render_story_narrative(facts).lower() for facts in samples):
        assert narrative_contains_forbidden_language(narrative) is False
        for phrase in (
            'the bullpen is thin',
            'the bullpen remains flexible',
            'limited comfortable options',
            'state is',
            'capacity state',
            'resource health',
            'coverage safety',
            'trust hierarchy',
            'resource pool',
            'trusted lane',
            'active count',
            'this indicates',
            'the data suggests',
            'role_change_detection',
            'ranking_applied',
            'selection_made',
            'prediction_applied',
            'should pitch',
            'recommend',
            'prediction',
        ):
            assert phrase not in narrative


def test_archetype_endings_use_distinct_family_mix():
    narratives = {
        archetype: render_story_narrative(facts)
        for archetype, facts in _archetype_story_fact_samples().items()
    }
    endings = {
        archetype: _ending_sentence_from_narrative(narrative)
        for archetype, narrative in narratives.items()
    }
    families = {
        archetype: _ending_family_from_sentence(ending)
        for archetype, ending in endings.items()
    }

    assert families == {
        archetype: _ending_family_from_sentence(_ending_sentence_from_narrative(render_story_narrative(facts)))
        for archetype, facts in _archetype_story_fact_samples().items()
    }
    assert len(set(families.values())) >= 4
    assert sum(ending.endswith('?') for ending in endings.values()) <= 4
    assert families[ARCHETYPE_WORKLOAD_CONCENTRATION] in {'question', 'implication'}
    assert families[ARCHETYPE_THIN_TRUSTED_GROUP] in {'question', 'implication'}
    assert families[ARCHETYPE_CAPACITY_CONSTRAINT] in {'observation', 'implication'}
    assert families[ARCHETYPE_ROTATION_SPILLOVER] in {'question', 'watch_statement'}
    assert families[ARCHETYPE_STABILITY_EROSION] in {'observation', 'question'}
    assert families[ARCHETYPE_STABILITY_RECOVERY] in {'observation', 'takeaway'}
    assert families[ARCHETYPE_MULTI_SOURCE_PRESSURE] in {'observation', 'implication'}
    assert families[ARCHETYPE_FLEXIBLE_BULLPEN] in {'takeaway', 'observation'}
    assert families[ARCHETYPE_RUN_PREVENTION_MASK] in {'question', 'implication'}


def test_archetype_narratives_avoid_forbidden_language_and_taxonomy():
    for narrative in [
        render_story_narrative(facts)
        for facts in _archetype_story_fact_samples().values()
    ]:
        lower = narrative.lower()

        assert narrative_contains_forbidden_language(narrative) is False
        for label in FORBIDDEN_PUBLIC_LABELS:
            assert label not in narrative
        for term in INTERNAL_TAXONOMY_TERMS:
            assert term.lower() not in lower
        for phrase in AWKWARD_RENDERER_PHRASES:
            assert phrase not in lower
        for phrase in BANNED_CAVEAT_PHRASES:
            assert phrase not in lower
        for forbidden in (
            'betting',
            'prediction',
            'recommendation',
            'preferred',
            'should use',
            'manager should',
            'fatigue score',
            'confidence score',
            'HIGH or CRITICAL',
            'pressure source',
            'workload pattern is',
            'the thing to watch next is whether',
            'the next question is',
            'from here, the question is',
            'worth watching to see whether',
            'injury',
            'transaction',
            'called up',
            'optioned',
            'dfa',
        ):
            assert forbidden.lower() not in lower


def test_renderer_phrase_pools_do_not_keep_banned_awkward_templates():
    source = inspect.getsource(team_story_narrative).lower()

    for phrase in AWKWARD_RENDERER_PHRASES + BANNED_CAVEAT_PHRASES:
        assert phrase not in source


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


def test_story_evidence_framework_surfaces_fact_name_and_consequence_in_narrative():
    pitchers, records, logs = _fixture_team(
        501,
        'Evidence Club',
        'EVC',
        [45, 35, 25, 5, 5],
        available_count=2,
        trust_indices=(0, 1),
    )

    feed = build_four_beat_story_feed(records, logs, reference_date=REF)

    assert feed['count'] == 1
    story = feed['items'][0]
    evidence = story['story_evidence']
    narrative = story['narrative']
    validation = validate_story_evidence(story)

    assert validation['passed'] is True
    assert story['story_evidence_framework']['passed'] is True
    assert evidence['evidence_statement'] in narrative
    assert evidence['consequence_statement'] in narrative
    assert any(name in narrative for name in evidence['pitcher_names'])
    assert re.search(r'\d', narrative)
    assert story_public_text(story).startswith(story['title'])
    assert pitchers


def test_observation_discovery_generates_ranked_candidates_before_story_generation():
    pitchers, records, logs = _fixture_team(
        601,
        'Discovery Club',
        'DSC',
        [44, 36, 24, 6, 5],
        available_count=2,
        trust_indices=(0, 1),
    )
    inputs = compute_team_story_inputs(_team_inputs(
        records,
        logs,
        team={
            'team_id': 601,
            'team_name': 'Discovery Club',
            'team_abbreviation': 'DSC',
        },
    ))

    raw_candidates = generate_observation_candidates(RULE_STRESS_TRANSFER, inputs)
    discovery = discover_story_observations(RULE_STRESS_TRANSFER, inputs)
    candidates = discovery['candidates']

    assert discovery['capability'] == 'observation_discovery_engine_v1'
    assert discovery['generated_before_story_generation'] is True
    assert discovery['ranking_applied'] is True
    assert discovery['selection_made'] is True
    assert len(raw_candidates) >= 2
    assert len(candidates) >= 2
    assert [candidate['rank'] for candidate in candidates] == list(range(1, len(candidates) + 1))
    assert candidates == sorted(candidates, key=lambda item: item['rank'])
    assert candidates[0] == discovery['selected_observation']
    assert all(candidate['editorial_test']['passed'] is True for candidate in candidates)
    assert all(any(name in candidate['text'] for name in candidate['pitcher_names']) for candidate in candidates)
    assert all(re.search(r'\d', candidate['text']) for candidate in candidates)
    assert pitchers


def test_observation_ranking_prefers_change_over_static_identity_on_ties():
    ranked = rank_observation_candidates([
        {
            'observation_id': 'identity',
            'observation_type': 'identity',
            'text': 'Static identity candidate with 6 usable relievers.',
            'score': 70,
        },
        {
            'observation_id': 'change',
            'observation_type': 'change',
            'text': 'Change candidate with 2 recently reintroduced relievers.',
            'score': 70,
        },
    ])

    assert [candidate['observation_type'] for candidate in ranked] == ['change', 'identity']
    assert [candidate['rank'] for candidate in ranked] == [1, 2]


def test_observation_marketplace_generates_inventory_before_feed_assignment():
    pitchers, records, logs = _fixture_team(
        606,
        'Marketplace Club',
        'MPC',
        [46, 34, 24, 4, 3],
        available_count=2,
        trust_indices=(0, 1),
    )
    inputs = compute_team_story_inputs(_team_inputs(
        records,
        logs,
        team={
            'team_id': 606,
            'team_name': 'Marketplace Club',
            'team_abbreviation': 'MPC',
        },
    ))
    story = assemble_story(RULE_STRESS_TRANSFER, inputs)

    inventory = build_feed_observation_inventory([{
        'story': story,
        'inputs': inputs,
    }])
    result = differentiate_observation_inventory(inventory)
    metadata = result['metadata']

    assert story
    assert metadata['capability'] == DIFFERENTIATION_CAPABILITY
    assert metadata['generated_inventory_before_story_assignment'] is True
    assert metadata['feed_awareness_applied'] is True
    assert metadata['inventory_count'] == 1
    assert inventory[0]['candidate_count'] >= 2
    assert len(inventory[0]['candidate_families']) >= 2
    assert result['assignments'][(606, RULE_STRESS_TRANSFER)]['selected_observation']['text']
    assert pitchers


def test_observation_differentiation_uses_diversity_as_secondary_ranking():
    def candidate(observation_type, score, rank):
        return {
            'observation_id': observation_type,
            'observation_type': observation_type,
            'text': f'{observation_type} candidate {score}',
            'score': score,
            'rank': rank,
        }

    inventory = [
        {
            'key': (701, RULE_SUSTAINABILITY_QUESTION),
            'team_name': 'Alpha Club',
            'rule_key': RULE_SUSTAINABILITY_QUESTION,
            'candidate_families': ['run_prevention_stress', 'workload_concentration'],
            'candidates': [
                candidate('run_prevention_stress', 100, 1),
                candidate('workload_concentration', 99, 2),
            ],
        },
        {
            'key': (702, RULE_SUSTAINABILITY_QUESTION),
            'team_name': 'Beta Club',
            'rule_key': RULE_SUSTAINABILITY_QUESTION,
            'candidate_families': ['run_prevention_stress', 'workload_concentration'],
            'candidates': [
                candidate('run_prevention_stress', 98, 1),
                candidate('workload_concentration', 97, 2),
            ],
        },
        {
            'key': (703, RULE_SUSTAINABILITY_QUESTION),
            'team_name': 'Gamma Club',
            'rule_key': RULE_SUSTAINABILITY_QUESTION,
            'candidate_families': ['run_prevention_stress', 'workload_concentration'],
            'candidates': [
                candidate('run_prevention_stress', 96, 1),
                candidate('workload_concentration', 94, 2),
            ],
        },
    ]

    result = differentiate_observation_inventory(inventory, quality_band_points=5)
    gamma = result['assignments'][(703, RULE_SUSTAINABILITY_QUESTION)]

    assert result['metadata']['family_soft_cap'] == 2
    assert result['metadata']['initial_family_counts'] == {'run_prevention_stress': 3}
    assert result['metadata']['final_family_counts'] == {
        'workload_concentration': 1,
        'run_prevention_stress': 2,
    }
    assert gamma['selected_observation']['observation_type'] == 'workload_concentration'
    assert gamma['observation_differentiation']['selection_reason'] == (
        'feed_diversification_within_quality_band'
    )
    assert gamma['observation_differentiation']['score_delta_from_local_top'] == 2


def test_observation_differentiation_keeps_quality_primary_when_gap_is_large():
    def candidate(observation_type, score, rank):
        return {
            'observation_id': observation_type,
            'observation_type': observation_type,
            'text': f'{observation_type} candidate {score}',
            'score': score,
            'rank': rank,
        }

    inventory = [
        {
            'key': (711, RULE_SUSTAINABILITY_QUESTION),
            'team_name': 'Alpha Club',
            'rule_key': RULE_SUSTAINABILITY_QUESTION,
            'candidate_families': ['run_prevention_stress', 'trust_shape'],
            'candidates': [
                candidate('run_prevention_stress', 100, 1),
                candidate('trust_shape', 99, 2),
            ],
        },
        {
            'key': (712, RULE_SUSTAINABILITY_QUESTION),
            'team_name': 'Beta Club',
            'rule_key': RULE_SUSTAINABILITY_QUESTION,
            'candidate_families': ['run_prevention_stress', 'trust_shape'],
            'candidates': [
                candidate('run_prevention_stress', 98, 1),
                candidate('trust_shape', 97, 2),
            ],
        },
        {
            'key': (713, RULE_SUSTAINABILITY_QUESTION),
            'team_name': 'Gamma Club',
            'rule_key': RULE_SUSTAINABILITY_QUESTION,
            'candidate_families': ['run_prevention_stress', 'trust_shape'],
            'candidates': [
                candidate('run_prevention_stress', 96, 1),
                candidate('trust_shape', 80, 2),
            ],
        },
    ]

    result = differentiate_observation_inventory(inventory, quality_band_points=5)
    gamma = result['assignments'][(713, RULE_SUSTAINABILITY_QUESTION)]

    assert gamma['selected_observation']['observation_type'] == 'run_prevention_stress'
    assert gamma['observation_differentiation']['selection_reason'] == (
        'quality_protected_top_observation'
    )
    assert gamma['observation_differentiation']['feed_wide_alternative_selected'] is False
    assert result['metadata']['final_family_counts'] == {'run_prevention_stress': 3}


def test_daily_feed_observation_differentiation_broadens_crowded_story_families():
    feed = _crowded_observation_feed()
    metadata = feed['observation_differentiation']
    stories = feed['items']
    selected_families = [
        story['story_observation']['selected_observation']['observation_type']
        for story in stories
    ]

    assert feed['count'] == 5
    assert metadata['capability'] == DIFFERENTIATION_CAPABILITY
    assert metadata['generated_inventory_before_story_assignment'] is True
    assert metadata['initial_family_counts'] == {'run_prevention_stress': 5}
    assert metadata['final_family_counts'] == {
        'workload_concentration': 2,
        'run_prevention_stress': 3,
    }
    assert metadata['published_family_counts'] == metadata['final_family_counts']
    assert metadata['alternative_selection_count'] == 2
    assert len(set(selected_families)) == 2
    assert all(summary['candidate_count'] >= 2 for summary in metadata['team_summaries'])
    assert all(story['story_observation']['selection_source'] == 'feed_observation_differentiation' for story in stories)
    assert all(story['story_evidence_framework']['passed'] for story in stories)
    assert all(story['story_evidence']['evidence_statement'] in story['narrative'] for story in stories)
    assert any(
        story['observation_differentiation']['feed_wide_alternative_selected']
        for story in stories
    )


def test_editorial_polish_fixes_plural_team_and_single_reliever_grammar():
    padres_pitchers, padres_records, padres_logs = _fixture_team(
        901,
        'San Diego Padres',
        'SD',
        [50, 40, 26, 16, 11, 9],
        available_count=4,
        high_risk_indices=(0, 1),
        trust_indices=(0, 1),
    )
    marlins_pitchers, marlins_records, marlins_logs = _fixture_team(
        902,
        'Miami Marlins',
        'MIA',
        [50, 40, 26, 16, 11, 9],
        available_count=1,
        high_risk_indices=(0, 1),
        trust_indices=(0, 1),
    )

    feed = build_four_beat_story_feed(
        [*padres_records, *marlins_records],
        _merge_logs(padres_logs, marlins_logs),
        reference_date=REF,
        season_era={
            'bullpens': [
                _bullpen_era(901, 'San Diego Padres', 'SD', 2.75, earned_runs=18),
                _bullpen_era(902, 'Miami Marlins', 'MIA', 2.75, earned_runs=18),
            ],
        },
    )
    public_text = story_public_text({
        'title': '',
        'narrative': ' '.join(story_public_text(story) for story in feed['items']),
    })

    assert feed['count'] == 2
    assert 'Padres has' not in public_text
    assert 'Marlins has' not in public_text
    assert '1 relievers are' not in public_text
    assert '..' not in public_text
    assert all(story['story_evidence_framework']['passed'] for story in feed['items'])
    assert padres_pitchers and marlins_pitchers


def test_editorial_polish_diversifies_evidence_consequence_and_adjacent_families():
    feed = _crowded_observation_feed()
    stories = feed['items']
    families = [
        story['story_observation']['selected_observation']['observation_type']
        for story in stories
    ]
    evidence_shapes = {
        _sentence_shape(story['story_evidence']['evidence_statement'])
        for story in stories
    }
    consequence_shapes = {
        _sentence_shape(story['story_evidence']['consequence_statement'])
        for story in stories
    }
    run_prevention_stories = [
        story for story in stories
        if story['story_observation']['selected_observation']['observation_type'] == 'run_prevention_stress'
    ]
    run_prevention_consequence_shapes = {
        _sentence_shape(story['story_evidence']['consequence_statement'])
        for story in run_prevention_stories
    }

    assert feed['count'] == 5
    assert feed['feed_ordering_basis'] == 'story_strength_with_observation_family_spacing'
    assert feed['feed_order_diversification_count'] >= 1
    assert all(left != right for left, right in zip(families, families[1:]))
    assert len(evidence_shapes) >= 4
    assert len(consequence_shapes) >= 4
    assert len(run_prevention_consequence_shapes) >= 2


def test_feed_order_diversification_preserves_large_quality_gap():
    stories = [
        {
            'team_name': 'A Club',
            'strength': 100,
            'story_observation': {'selected_observation': {'observation_type': 'run_prevention_stress'}},
        },
        {
            'team_name': 'B Club',
            'strength': 99,
            'story_observation': {'selected_observation': {'observation_type': 'run_prevention_stress'}},
        },
        {
            'team_name': 'C Club',
            'strength': 80,
            'story_observation': {'selected_observation': {'observation_type': 'workload_concentration'}},
        },
    ]

    ordered, applied_count = diversify_feed_story_order(stories, quality_band_points=8)

    assert [story['team_name'] for story in ordered] == ['A Club', 'B Club', 'C Club']
    assert applied_count == 0


def test_identity_evidence_with_positive_depth_uses_stable_consequence():
    capacity_by_team = _with_bullpen_identity(
        _foundation_capacity_context(active=8, clean=7),
        identity_updates={
            'identity_summary': (
                'Flexible bullpen: enough trusted relievers are available to avoid forcing '
                'every important inning through the same arms.'
            ),
        },
    )
    inputs = compute_team_story_inputs(_broad_light_team_inputs(
        team={
            'team_id': 910,
            'team_name': 'Los Angeles Angels',
            'team_abbreviation': 'LAA',
        },
        capacity_by_team={910: capacity_by_team[1]},
    ))
    discovery = discover_story_observations(RULE_PRESSURE_DISTRIBUTION, inputs)
    identity = next(
        candidate
        for candidate in discovery['candidates']
        if candidate['observation_type'] == 'identity'
    )
    story = assemble_story(
        RULE_PRESSURE_DISTRIBUTION,
        inputs,
        selected_observation_override=identity,
    )

    assert story['story_evidence']['consequence_category'] == 'more_stable_bullpen_shape'
    assert 'That reduces flexibility' not in story['narrative']
    assert story['story_evidence_framework']['checks']['consequence_consistent_with_evidence'] is True


def test_story_evidence_rejects_contradictory_positive_depth_consequence():
    evidence_statement = (
        'Contradiction Arm sits at the front of Contradiction Club relief shape with '
        '7 usable relievers behind them because enough trusted relievers are available.'
    )
    story = {
        'story_id': 'contradiction:story',
        'team_id': 911,
        'team_name': 'Contradiction Club',
        'team_abbreviation': 'CNT',
        'rule_key': RULE_PRESSURE_DISTRIBUTION,
        'title': 'Contradiction Club has a relief shape issue.',
        'body': '',
        'narrative': (
            f'{evidence_statement}\n\n'
            'That reduces flexibility if the game moves away from the trusted group.'
        ),
        'story_evidence': {
            'pitcher_names': ['Contradiction Arm'],
            'evidence_statement': evidence_statement,
            'consequence_category': 'reduced_flexibility',
            'consequence_statement': (
                'That reduces flexibility if the game moves away from the trusted group.'
            ),
        },
        'story_observation': {
            'selected_observation': {
                'text': evidence_statement,
            },
        },
    }

    validation = validate_story_evidence(story)

    assert validation['passed'] is False
    assert 'consequence_consistent_with_evidence' in validation['fail_reasons']


def test_observation_led_story_references_selected_observation_directly():
    pitchers, records, logs = _fixture_team(
        602,
        'Observation Club',
        'OBS',
        [48, 32, 22, 4, 3],
        available_count=2,
        trust_indices=(0, 1),
    )

    feed = build_four_beat_story_feed(records, logs, reference_date=REF)
    story = feed['items'][0]
    selected = story['story_observation']['selected_observation']
    voice = story['story_voice']
    paragraphs = story['narrative'].split('\n\n')

    assert selected['rank'] == 1
    assert story['story_facts']['selected_observation'] == selected
    assert story['story_facts']['evidence_statement'] == selected['text']
    assert story['story_evidence']['evidence_statement'] == selected['text']
    assert voice['applied'] is True
    assert voice['human_frame'] == paragraphs[0]
    assert paragraphs[1] == selected['text']
    assert selected['text'] in story['narrative']
    assert story['story_evidence_framework']['checks']['selected_observation_referenced'] is True
    assert pitchers


def test_observation_voice_layer_adds_supported_frame_before_evidence():
    pitchers, records, logs = _fixture_team(
        603,
        'Voice Club',
        'VOC',
        [50, 34, 20, 5, 3],
        available_count=2,
        trust_indices=(0, 1),
    )

    feed = build_four_beat_story_feed(records, logs, reference_date=REF)
    story = feed['items'][0]
    voice = story['story_voice']
    narrative = story['narrative']
    selected = story['story_observation']['selected_observation']
    evidence = story['story_evidence']

    assert voice['capability'] == 'observation_voice_layer_v1'
    assert voice['applied'] is True
    assert voice['validation']['passed'] is True
    assert voice['validation']['checks']['human_frame_supported'] is True
    assert voice['human_frame'] == narrative.split('\n\n')[0]
    assert voice['evidence_sentence'] == selected['text']
    assert voice['evidence_sentence'] in narrative
    assert voice['consequence_sentence'] in narrative
    assert evidence['evidence_statement'] == selected['text']
    assert any(name in narrative for name in evidence['pitcher_names'])
    assert re.search(r'\d', narrative)
    assert pitchers


def test_observation_voice_layer_rejects_empty_fluff_frame():
    selected_text = 'Named Reliever has handled 70% of Fluff Club recent relief pitches.'
    voice = {
        'capability': 'observation_voice_layer_v1',
        'version': 'test',
        'observation_type': 'workload_concentration',
        'selected_observation_text': selected_text,
        'human_frame': 'The bullpen picture remains stable.',
        'evidence_sentence': selected_text,
        'consequence_sentence': 'That leaves less coverage margin.',
        'pitcher_names': ['Named Reliever'],
    }

    validation = validate_observation_voice(voice)

    assert validation['passed'] is False
    assert 'generic_frame_absent' in validation['fail_reasons']
    assert 'human_frame_supported' in validation['fail_reasons']
    assert validation['generic_frame_hits'] == ['the bullpen picture remains stable', 'bullpen picture remains stable']


def test_observation_voice_layer_builds_public_safe_supported_frames():
    selected_observation = {
        'observation_id': 'workload_concentration',
        'observation_type': 'workload_concentration',
        'text': 'Frame Arm and Bridge Arm have handled 78% of Voice Safety Club recent relief pitches.',
        'pitcher_names': ['Frame Arm', 'Bridge Arm'],
        'consequence_category': 'heavier_workload_concentration',
        'consequence_statement': (
            'That keeps heavier workload concentration in play if the next tight inning '
            'has to move back through Frame Arm and Bridge Arm.'
        ),
    }
    voice = build_observation_voice({
        'team': {
            'team_id': 604,
            'team_name': 'Voice Safety Club',
            'team_abbreviation': 'VSC',
        },
        'selected_observation': selected_observation,
        'named_pitchers': selected_observation['pitcher_names'],
        'evidence_statement': selected_observation['text'],
        'consequence_statement': selected_observation['consequence_statement'],
        'consequence_category': selected_observation['consequence_category'],
    })

    assert voice['applied'] is True
    assert voice['validation']['passed'] is True
    assert voice['validation']['checks']['public_language_safe'] is True
    assert voice['prose_path'] in observation_prose_paths('workload_concentration')
    assert voice['headline']
    assert voice['headline_shape'] == f"workload_concentration:{voice['prose_path']}"
    assert voice['body_shape'] == f"workload_concentration:{voice['prose_path']}"
    assert voice['evidence_sentence'] == selected_observation['text']
    assert voice['consequence_sentence'] == selected_observation['consequence_statement']


def test_observation_voice_avoids_generic_identity_and_change_phrases():
    weak_phrases = (
        'current relief shape is easy to see',
        'relief shape starts there',
        'current relief shape',
        'changed bullpen mix',
        'bullpen mix has been shifting',
        'the bullpen is under pressure',
        'limited flexibility',
        'current usage read',
    )
    identity = {
        'observation_id': 'identity',
        'observation_type': 'identity',
        'text': (
            'Frame Arm and Bridge Arm sit at the front of Voice Identity Club bullpen, '
            'with 6 usable relievers behind them.'
        ),
        'pitcher_names': ['Frame Arm', 'Bridge Arm'],
        'consequence_category': 'more_stable_bullpen_shape',
        'consequence_statement': (
            'That gives Voice Identity Club a front group while still leaving the manager '
            'more than one path through the late innings.'
        ),
    }
    change = {
        'observation_id': 'change',
        'observation_type': 'change',
        'text': (
            'Voice Change Club has 2 recently reintroduced relievers, but Frame Arm and '
            'Bridge Arm still anchor the current late-game route.'
        ),
        'pitcher_names': ['Frame Arm', 'Bridge Arm'],
        'consequence_category': 'more_stable_bullpen_shape',
        'consequence_statement': (
            'For Voice Change Club, that gives the manager one more way to cover innings '
            'without moving the leverage center away from the familiar group.'
        ),
    }

    for selected_observation, team_name, prose_paths in (
        (identity, 'Voice Identity Club', ('current_mix', 'named_dependency', 'alternatives_short')),
        (change, 'Voice Change Club', ('current_mix', 'named_dependency', 'game_route')),
    ):
        for prose_path in prose_paths:
            voice = build_observation_voice({
                'team': {
                    'team_id': 610,
                    'team_name': team_name,
                    'team_abbreviation': 'VOC',
                },
                'selected_observation': selected_observation,
                'named_pitchers': selected_observation['pitcher_names'],
                'evidence_statement': selected_observation['text'],
                'consequence_statement': selected_observation['consequence_statement'],
                'consequence_category': selected_observation['consequence_category'],
                'forced_prose_path': prose_path,
            })
            public_text = ' '.join(
                piece for piece in (
                    voice['headline'],
                    voice['human_frame'],
                    voice['evidence_sentence'],
                    voice['consequence_sentence'],
                )
                if piece
            ).lower()

            assert voice['applied'] is True
            assert voice['validation']['passed'] is True
            for phrase in weak_phrases:
                assert phrase not in public_text
            assert any(marker in public_text for marker in (
                'late innings',
                'late-game route',
                'manager',
                'leverage center',
                'usable relievers',
            ))


def test_observation_voice_supports_multiple_prose_paths_for_same_observation():
    selected_observation = {
        'observation_id': 'workload_concentration',
        'observation_type': 'workload_concentration',
        'text': 'Frame Arm and Bridge Arm have handled 78% of Voice Safety Club recent relief pitches.',
        'pitcher_names': ['Frame Arm', 'Bridge Arm'],
        'consequence_category': 'heavier_workload_concentration',
        'consequence_statement': (
            'That keeps heavier workload concentration in play if the next tight inning '
            'has to move back through Frame Arm and Bridge Arm.'
        ),
    }
    voices = [
        build_observation_voice({
            'team': {
                'team_id': 604,
                'team_name': 'Voice Safety Club',
                'team_abbreviation': 'VSC',
            },
            'selected_observation': selected_observation,
            'named_pitchers': selected_observation['pitcher_names'],
            'evidence_statement': selected_observation['text'],
            'consequence_statement': selected_observation['consequence_statement'],
            'consequence_category': selected_observation['consequence_category'],
            'prose_path': prose_path,
        })
        for prose_path in observation_prose_paths('workload_concentration')
    ]

    assert len(voices) >= 4
    assert all(voice['applied'] for voice in voices)
    assert all(voice['validation']['passed'] for voice in voices)
    assert {voice['prose_path'] for voice in voices} == set(observation_prose_paths('workload_concentration'))
    assert len({voice['headline_shape'] for voice in voices}) == len(voices)
    assert len({voice['human_frame'] for voice in voices}) == len(voices)
    assert {voice['evidence_sentence'] for voice in voices} == {selected_observation['text']}
    assert {voice['consequence_sentence'] for voice in voices} == {
        selected_observation['consequence_statement']
    }


def test_observation_voice_rejects_empty_or_throat_clearing_closing():
    selected_text = 'Named Reliever has handled 70% of Closing Club recent relief pitches.'
    base_voice = {
        'capability': 'observation_voice_layer_v1',
        'version': 'test',
        'observation_type': 'workload_concentration',
        'selected_observation_text': selected_text,
        'human_frame': 'Closing Club is carrying a narrow recent workload, with the relief pitches clustered around one arm.',
        'evidence_sentence': selected_text,
        'pitcher_names': ['Named Reliever'],
    }

    empty_validation = validate_observation_voice({
        **base_voice,
        'consequence_sentence': '',
    })
    throat_validation = validate_observation_voice({
        **base_voice,
        'consequence_sentence': 'Usage provides the strongest signal here.',
    })

    assert empty_validation['passed'] is False
    assert 'consequence_sentence_present' in empty_validation['fail_reasons']
    assert 'consequence_sentence_informational' in empty_validation['fail_reasons']
    assert throat_validation['passed'] is False
    assert 'consequence_sentence_informational' in throat_validation['fail_reasons']
    assert throat_validation['closing_language_hits'] == ['usage provides the strongest signal here']


def test_story_evidence_rejects_schema_language_and_throat_clearing_closers():
    story = {
        'story_id': 'schema:story',
        'team_id': 907,
        'team_name': 'Schema Club',
        'team_abbreviation': 'SCH',
        'title': 'Schema Club active capacity story.',
        'body': '',
        'narrative': (
            'Schema Arm has handled 70% of Schema Club recent relief pitches.\n\n'
            'That leaves less coverage margin if Schema Club needs another clean inning.\n\n'
            'There are still roster questions around the edges.'
        ),
        'story_evidence': {
            'pitcher_names': ['Schema Arm'],
            'evidence_statement': 'Schema Arm has handled 70% of Schema Club recent relief pitches.',
            'consequence_category': 'less_coverage_margin',
            'consequence_statement': (
                'That leaves less coverage margin if Schema Club needs another clean inning.'
            ),
        },
    }

    validation = validate_story_evidence(story)

    assert validation['passed'] is False
    assert 'public_schema_language_absent' in validation['fail_reasons']
    assert 'closing_language_informational' in validation['fail_reasons']
    assert 'active capacity' in validation['schema_language_hits']
    assert validation['closing_language_hits'] == ['there are still roster questions around the edges']
    assert set(THROAT_CLEARING_CLOSERS) >= set(validation['closing_language_hits'])
    assert 'active capacity' in PUBLIC_SCHEMA_LANGUAGE_DENYLIST


def test_story_evidence_rejects_public_internal_process_language():
    story = {
        'story_id': 'process:story',
        'team_id': 908,
        'team_name': 'Process Club',
        'team_abbreviation': 'PRC',
        'title': 'Process Club needs more than the same relief pocket.',
        'body': '',
        'narrative': (
            'Process Arm has handled 70% of Process Club recent relief pitches.\n\n'
            'That leaves less coverage margin if Process Club needs another clean inning.\n\n'
            'The source limit keeps the conclusion on usage and availability.'
        ),
        'story_evidence': {
            'pitcher_names': ['Process Arm'],
            'evidence_statement': 'Process Arm has handled 70% of Process Club recent relief pitches.',
            'consequence_category': 'less_coverage_margin',
            'consequence_statement': (
                'That leaves less coverage margin if Process Club needs another clean inning.'
            ),
        },
    }

    validation = validate_story_evidence(story)

    assert validation['passed'] is False
    assert 'internal_process_language_absent' in validation['fail_reasons']
    assert validation['internal_process_language_hits'] == ['source limit']
    assert 'source limit' in INTERNAL_PROCESS_LANGUAGE_DENYLIST


def test_repeated_observation_voice_frames_are_suppressed_across_teams():
    def story(team_id, team_name, abbr, pitcher_name, pct):
        frame = 'The bullpen is not really spreading bullpen work right now; it is leaning on two arms.'
        evidence_statement = (
            f'{pitcher_name} has handled {pct}% of {team_name} recent relief pitches.'
        )
        consequence_statement = (
            f'That leaves less coverage margin if {team_name} needs another clean inning.'
        )
        return {
            'story_id': f'{team_id}:story',
            'team_id': team_id,
            'team_name': team_name,
            'team_abbreviation': abbr,
            'rule_key': RULE_STRESS_TRANSFER,
            'title': f'{team_name} bullpen workload is concentrated.',
            'narrative': f'{frame}\n\n{evidence_statement}\n\n{consequence_statement}',
            'story_evidence': {
                'pitcher_names': [pitcher_name],
                'evidence_statement': evidence_statement,
                'consequence_statement': consequence_statement,
                'consequence_category': 'less_coverage_margin',
            },
            'story_observation': {
                'selected_observation': {
                    'text': evidence_statement,
                },
            },
            'story_voice': {
                'capability': 'observation_voice_layer_v1',
                'version': 'test',
                'applied': True,
                'observation_type': 'workload_concentration',
                'selected_observation_text': evidence_statement,
                'human_frame': frame,
                'evidence_sentence': evidence_statement,
                'consequence_sentence': consequence_statement,
                'pitcher_names': [pitcher_name],
            },
        }

    published, suppressed = apply_story_evidence_framework([
        story(605, 'First Voice Club', 'FVC', 'First Voice Arm', 72),
        story(606, 'Second Voice Club', 'SVC', 'Second Voice Arm', 69),
    ])

    assert [item['team_abbreviation'] for item in published] == ['FVC']
    assert suppressed == [{
        'team_id': 606,
        'team_name': 'Second Voice Club',
        'team_abbreviation': 'SVC',
        'rule_key': RULE_STRESS_TRANSFER,
        'story_id': '606:story',
        'reasons': [
            'duplicate_voice_frame',
        ],
    }]


def test_observation_voice_narrative_does_not_expose_internal_labels():
    pitchers, records, logs = _fixture_team(
        607,
        'Label Safety Club',
        'LSC',
        [46, 35, 24, 5, 3],
        available_count=2,
        trust_indices=(0, 1),
    )

    feed = build_four_beat_story_feed(records, logs, reference_date=REF)
    story = feed['items'][0]
    public_text = story_public_text(story).lower()

    for internal_label in (
        'observation_voice_layer_v1',
        'observation_discovery_engine_v1',
        'story_prose_detemplating_v1',
        'selected_observation',
        'human_frame',
        'workload_concentration',
        'ranking_applied',
        'selection_made',
        'active capacity',
        'trusted-group breadth',
        'clean options',
        'coverage safety',
        'resource health',
        'bullpen identity',
        'trust hierarchy',
    ):
        assert internal_label not in public_text
    for marker in INTERNAL_PROCESS_PUBLIC_MARKERS:
        assert marker not in public_text
    assert 'disclosure_note' not in story
    assert story['story_evidence_framework']['checks']['internal_process_language_absent'] is True
    assert pitchers


def test_generic_narrative_only_story_fails_selected_observation_validation():
    story = {
        'story_id': 'generic:story',
        'team_id': 2,
        'team_name': 'Generic Club',
        'team_abbreviation': 'GEN',
        'rule_key': RULE_STRESS_TRANSFER,
        'title': 'Generic Club bullpen story.',
        'narrative': (
            'The trusted group continues carrying the workload. '
            'The shape of the bullpen remains stable. '
            'The back end still gives the night structure.'
        ),
        'story_evidence': {
            'pitcher_names': ['Named Reliever'],
            'evidence_statement': 'Named Reliever has handled 70% of recent relief pitches.',
            'consequence_statement': 'That leaves less coverage margin.',
            'consequence_category': 'less_coverage_margin',
        },
        'story_observation': {
            'selected_observation': {
                'text': 'Named Reliever has handled 70% of recent relief pitches.',
            },
        },
    }

    validation = validate_story_evidence(story)

    assert validation['passed'] is False
    assert 'selected_observation_referenced' in validation['fail_reasons']
    assert 'generic_language_absent' in validation['fail_reasons']


def test_template_dependency_audit_documents_reduction_strategy():
    audit = story_template_dependency_audit()

    assert audit['capability'] == 'observation_discovery_engine_v1'
    assert audit['status'] == 'template_dependency_reduced'
    assert 'legacy_beat_skeletons' in audit['fixed_structure_surfaces']
    assert 'open_public_narrative_with_selected_observation' in audit['reduction_strategy']


def test_story_evidence_framework_fail_closed_for_invalid_story():
    story = {
        'story_id': 'bad:story',
        'team_id': 1,
        'team_name': 'Bad Story Club',
        'team_abbreviation': 'BAD',
        'rule_key': RULE_STRESS_TRANSFER,
        'title': 'The bullpen picture is changing.',
        'narrative': 'The shape of the picture is changing. It still sits in a workable spot.',
        'story_evidence': {
            'pitcher_names': ['Named Reliever'],
            'evidence_statement': None,
            'consequence_statement': None,
            'consequence_category': None,
        },
    }

    published, suppressed = apply_story_evidence_framework([story])

    assert published == []
    assert suppressed == [{
        'team_id': 1,
        'team_name': 'Bad Story Club',
        'team_abbreviation': 'BAD',
        'rule_key': RULE_STRESS_TRANSFER,
        'story_id': 'bad:story',
        'reasons': [
            'evidence_presence',
            'name_presence',
            'consequence_presence',
            'generic_language_absent',
        ],
    }]
    assert set(GENERIC_LANGUAGE_DENYLIST) & {
        'shape of the picture',
        'still sits in a workable spot',
    }


def test_story_evidence_framework_suppresses_exact_repeated_constructions():
    def story(team_id, team_name, abbr, pitcher_name, pct):
        evidence_statement = (
            f'{pitcher_name} has handled {pct}% of recent relief pitches for {team_name}.'
        )
        consequence_statement = 'That leaves less coverage margin if the game needs another clean inning.'
        return {
            'story_id': f'{team_id}:story',
            'team_id': team_id,
            'team_name': team_name,
            'team_abbreviation': abbr,
            'rule_key': RULE_STRESS_TRANSFER,
            'title': f'{team_name} bullpen workload is concentrated.',
            'narrative': (
                f'The bullpen has a copied opening sentence. {evidence_statement}\n\n'
                f'{consequence_statement}'
            ),
            'story_evidence': {
                'pitcher_names': [pitcher_name],
                'evidence_statement': evidence_statement,
                'consequence_statement': consequence_statement,
                'consequence_category': 'less_coverage_margin',
            },
        }

    published, suppressed = apply_story_evidence_framework([
        story(1, 'First Club', 'FST', 'First Reliever', 71),
        story(2, 'Second Club', 'SND', 'Second Reliever', 64),
    ])

    assert [item['team_abbreviation'] for item in published] == ['FST']
    assert suppressed == [{
        'team_id': 2,
        'team_name': 'Second Club',
        'team_abbreviation': 'SND',
        'rule_key': RULE_STRESS_TRANSFER,
        'story_id': '2:story',
        'reasons': [
            'duplicate_consequence_construction',
            'duplicate_opening_construction',
        ],
    }]


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
    assert 'carrying heavy recent workload' in next(
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
    assert stories[0]['title'].replace(stories[0]['team_name'], '{team_name}') != (
        stories[1]['title'].replace(stories[1]['team_name'], '{team_name}')
    )
    assert stories[0]['story_voice']['prose_path'] != stories[1]['story_voice']['prose_path']
    assert any(story['lead_dimension_detail'].get('honest_sameness') for story in stories)
    assert any(story['lead_dimension_detail'].get('feed_wide_honest_sameness') for story in stories)


def test_adjacent_similar_story_cards_force_prose_diversification():
    alpha_pitchers, alpha_records, alpha_logs = _fixture_team(
        800,
        'Alpha Similar Club',
        'ASC',
        [12, 12, 12, 12, 12, 12],
    )
    beta_pitchers, beta_records, beta_logs = _fixture_team(
        801,
        'Beta Similar Club',
        'BSC',
        [12, 12, 12, 12, 12, 12],
    )
    feed = build_four_beat_story_feed(
        [*alpha_records, *beta_records],
        _merge_logs(alpha_logs, beta_logs),
        reference_date=REF,
    )

    stories = sorted(feed['items'], key=lambda item: item['team_abbreviation'])
    assert feed['count'] == 2
    assert {story['story_voice']['observation_type'] for story in stories} == {'flexibility'}
    assert any(story['story_prose']['adjacent_diversification_applied'] for story in stories)
    assert len({story['story_voice']['headline_shape'] for story in stories}) == 2
    assert len({story['story_voice']['body_shape'] for story in stories}) == 2
    assert len({story['title'].replace(story['team_name'], '{team_name}') for story in stories}) == 2
    assert all(story['story_evidence_framework']['passed'] for story in stories)
    assert alpha_pitchers and beta_pitchers


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
