"""Backend-authored four-beat bullpen stories.

This service is fill-only: it selects deterministic rules and fills fixed
sentence skeletons with computed slots. Unsupported slots suppress the beat.
"""

from __future__ import annotations

import os
import string
from dataclasses import dataclass
from typing import Any

from services.availability import (
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
)
from services.pitcher_role_authority import author_role_read_labels
from services.team_story_facts import build_story_facts
from services.team_story_narrative import render_story_disclosure_note, render_story_narrative
from services.workload_concentration import (
    CONCENTRATED_TOP_ARM_COUNT,
    CONCENTRATED_TOP_SHARE_MIN,
    CONCENTRATION_DESCRIPTOR_CONCENTRATED_MIN,
    CONCENTRATION_DESCRIPTOR_MODERATE_MIN,
    CONCENTRATION_DESCRIPTOR_SEVERE_MIN,
    RECENT_WORKLOAD_WINDOW_DAYS,
    summarize_recent_relief_workload,
)


CAPABILITY = 'four_beat_story_template_v1'
VERSION = '2026-06-18.narrative_renderer_v3'
FEATURE_FLAG = 'FOUR_BEAT_STORIES_ENABLED'

RULE_STRESS_TRANSFER = 'stress_transfer'
RULE_PRESSURE_DISTRIBUTION = 'pressure_distribution'
RULE_SUSTAINABILITY_QUESTION = 'sustainability_question'
RULE_HIDDEN_CAPACITY_LOSS = 'hidden_capacity_loss'
RULE_SPECIAL_SITUATION = 'special_situation'

BEAT_SIGNAL = 'signal'
BEAT_EVIDENCE = 'evidence'
BEAT_CONTEXT = 'context'
BEAT_MECHANISM = 'mechanism'
BEAT_IMPLICATION = 'implication'

LEAD_FATIGUE_LOAD = 'fatigue_load'
LEAD_TRUST_LANE_ABSENCE = 'trust_lane_absence'
LEAD_TRUST_LANE_SHALLOW = 'trust_lane_shallow'
LEAD_WORKLOAD_HIGH = 'workload_high'
LEAD_WORKLOAD_LIGHT = 'workload_light'
LEAD_AVAILABILITY_THIN = 'availability_thin'
LEAD_AVAILABILITY_DEEP = 'availability_deep'
LEAD_DEEP_INTACT = 'deep_intact'
LEAD_CONCENTRATION_SHAPE = 'concentration_shape'
LEAD_PARTICIPATION_NARROW = 'participation_narrow'
LEAD_PARTICIPATION_BROAD = 'participation_broad'
LEAD_ERA_ELITE = 'era_elite'
LEAD_ERA_ORDINARY = 'era_ordinary'
LEAD_TRUST_LANE_DEPTH = 'trust_lane_depth'

# Reasoned judgment defaults, not validated thresholds. They are intentionally
# centralized so a future tuning pass can change them without hunting literals.
THIN_AVAILABLE_COUNT_MAX = 3
THIN_AVAILABLE_SHARE_MAX = 0.30
LIGHT_HIGH_RISK_LEVELS = {'HIGH', 'CRITICAL'}
WHY_CONTEXT_PRESSURE_RULES = {
    RULE_STRESS_TRANSFER,
    RULE_SUSTAINABILITY_QUESTION,
    RULE_HIDDEN_CAPACITY_LOSS,
}
LIMITED_CONTEXT_STATUSES = {'limited_read', 'no_data', 'unknown'}
CAPACITY_PRESSURE_STATUSES = {'elevated', 'constrained', 'severe'}
ROTATION_PRESSURE_STATUSES = {'moderate_pressure', 'heavy_pressure'}
STABILITY_CONTEXT_STATUSES = {'moderate_churn', 'heavy_churn'}
STABILITY_CONTEXT_MIN_RECENT_USED = 4
CAPACITY_UNKNOWN_LIMITED_READ_BLOCK_PCT_MIN = 10
LIGHT_PER_ARM_PITCHES_MAX = 26.0
BROAD_PARTICIPATION_MIN_ARMS = 6
BROAD_SINGLE_ARM_SHARE_MAX = 0.30
PRESSURE_DISTRIBUTION_STRENGTH_OFFSET = 65
HIDDEN_CAPACITY_LOSS_STRENGTH_OFFSET = 50
SUSTAINABILITY_QUESTION_STRENGTH_OFFSET = 90
STRESS_TRANSFER_STRENGTH_OFFSET = 100
STRONG_SEASON_ERA_TOP_BULLPENS = 10
SOLID_SEASON_ERA_TOP_BULLPENS = 20
HEAVY_PER_ARM_PITCHES_MIN = 30.0
HEAVY_HIGH_RISK_ARM_MIN = 1
DEPLETED_AVAILABLE_COUNT_MAX = THIN_AVAILABLE_COUNT_MAX
DEPLETED_AVAILABLE_SHARE_MAX = THIN_AVAILABLE_SHARE_MAX
DEPLETED_ROSTER_UNAVAILABLE_MIN = 1
LEAD_WORKLOAD_SIMILAR_PITCHES = 2.0
LEAD_AVAILABILITY_SIMILAR_SHARE = 0.10
LEAD_CONCENTRATION_SIMILAR_SHARE = 0.05
LEAD_ERA_SIMILAR_RANKS = 2
LEAD_DIMENSION_TIE_BREAK_ORDER = (
    LEAD_FATIGUE_LOAD,
    LEAD_TRUST_LANE_ABSENCE,
    LEAD_TRUST_LANE_SHALLOW,
    LEAD_WORKLOAD_HIGH,
    LEAD_WORKLOAD_LIGHT,
    LEAD_AVAILABILITY_THIN,
    LEAD_AVAILABILITY_DEEP,
    LEAD_DEEP_INTACT,
    LEAD_CONCENTRATION_SHAPE,
    LEAD_PARTICIPATION_NARROW,
    LEAD_PARTICIPATION_BROAD,
    LEAD_ERA_ELITE,
    LEAD_ERA_ORDINARY,
    LEAD_TRUST_LANE_DEPTH,
)

PHRASE_VARIANTS = {
    'capacity_context_fallback': (
        "They're working with fewer usable arms than a normal night.",
        "There isn't as much bullpen room as there usually is.",
        'The bullpen looks thinner than it normally does.',
        'The available group is smaller than usual.',
        'There are fewer places to turn tonight than there normally would be.',
        'The bullpen is carrying less usable depth than usual.',
    ),
    'capacity_context_standard': (
        'The work is landing on the same arms while the bullpen is already short on usable arms.',
        'The same relievers are taking the ball while the available group is already thin.',
        'A smaller bullpen makes those repeat innings harder to spread around.',
        'The bullpen is already thin, and the heavy innings keep finding the same arms.',
    ),
    'rotation_context': (
        'The bullpen has been carrying more of the workload lately, which makes every clean inning a little harder to replace.',
        'Extra outs have been finding their way to the bullpen lately.',
        'The bullpen has been covering more of the game than usual.',
        'More of the game has been landing on the pen lately.',
    ),
    'stability_context': (
        'A few different relievers have been moving in and out of the picture lately.',
        'The bullpen group has not looked exactly the same from week to week.',
        'The innings have been moving around lately.',
        'The bullpen mix has been shifting lately.',
    ),
    'environment_intro': (
        'This is not one clean issue.',
        'There is more than one thing tightening the picture.',
        'It is not just one part of the pen.',
    ),
    'environment_capacity_label': (
        'the bullpen is short on usable arms',
        'there are fewer places to turn than usual',
        'the available group is smaller than normal',
    ),
    'environment_rotation_label': (
        'the recent workload picture is adding pressure',
        'extra outs have been finding their way to the pen',
        'the bullpen has been covering more of the game lately',
    ),
    'environment_stability_label': (
        'the group has not looked the same lately',
        'a few different relievers have been moving through the picture',
        'the bullpen mix has been shifting lately',
    ),
    'sustainability_mechanism': (
        "The results are not the issue; the cost of every clean inning is a little higher tonight.",
        "The challenge isn't getting outs. It's replacing them.",
        'The results have held up. The margin has gotten thinner.',
        "They're still getting outs, but the margin inside the game is tighter.",
        'Every clean inning carries a little more weight tonight.',
        'The bullpen is still effective, but there is less room for mistakes.',
    ),
    'clean_trust_late_route_clause': (
        '{clean_trust_names} {clean_trust_verb} still where the late innings point',
        'the late innings still run through {clean_trust_names}',
        'if the game gets tight late, it still points back toward {clean_trust_names}',
        '{clean_trust_names} {clean_trust_verb} still at the center of the late-inning picture',
    ),
    'clean_trust_late_sentence': (
        'The late innings still run through {clean_trust_names}.',
        'If the game gets tight late, it still points back toward {clean_trust_names}.',
        '{clean_trust_names} {clean_trust_verb} still at the center of the late-inning picture.',
        'Those late outs still point back toward {clean_trust_names}.',
    ),
    'workload_concentration_signal': (
        'The same few relievers keep getting the ball for the {team_name}.',
        'A small group has been carrying most of the {team_name} bullpen work.',
        'The workload keeps circling back to the same {team_name} relievers.',
        'The heavy innings have been landing on the same {team_name} arms.',
    ),
}

THRESHOLDS = {
    'recent_workload_window_days': RECENT_WORKLOAD_WINDOW_DAYS,
    'concentrated_top_arm_count': CONCENTRATED_TOP_ARM_COUNT,
    'concentrated_top_share_min': CONCENTRATED_TOP_SHARE_MIN,
    'concentration_descriptor_moderate_min': CONCENTRATION_DESCRIPTOR_MODERATE_MIN,
    'concentration_descriptor_concentrated_min': CONCENTRATION_DESCRIPTOR_CONCENTRATED_MIN,
    'concentration_descriptor_severe_min': CONCENTRATION_DESCRIPTOR_SEVERE_MIN,
    'thin_available_count_max': THIN_AVAILABLE_COUNT_MAX,
    'thin_available_share_max': THIN_AVAILABLE_SHARE_MAX,
    'light_high_risk_levels': sorted(LIGHT_HIGH_RISK_LEVELS),
    'light_per_arm_pitches_max': LIGHT_PER_ARM_PITCHES_MAX,
    'broad_participation_min_arms': BROAD_PARTICIPATION_MIN_ARMS,
    'broad_single_arm_share_max': BROAD_SINGLE_ARM_SHARE_MAX,
    'strong_season_era_top_bullpens': STRONG_SEASON_ERA_TOP_BULLPENS,
    'solid_season_era_top_bullpens': SOLID_SEASON_ERA_TOP_BULLPENS,
    'heavy_per_arm_pitches_min': HEAVY_PER_ARM_PITCHES_MIN,
    'heavy_high_risk_arm_min': HEAVY_HIGH_RISK_ARM_MIN,
    'depleted_available_count_max': DEPLETED_AVAILABLE_COUNT_MAX,
    'depleted_available_share_max': DEPLETED_AVAILABLE_SHARE_MAX,
    'depleted_roster_unavailable_min': DEPLETED_ROSTER_UNAVAILABLE_MIN,
    'lead_dimension_tie_break_order': list(LEAD_DIMENSION_TIE_BREAK_ORDER),
    'lead_workload_similar_pitches': LEAD_WORKLOAD_SIMILAR_PITCHES,
    'lead_availability_similar_share': LEAD_AVAILABILITY_SIMILAR_SHARE,
    'lead_concentration_similar_share': LEAD_CONCENTRATION_SIMILAR_SHARE,
    'lead_era_similar_ranks': LEAD_ERA_SIMILAR_RANKS,
}

RULES = {
    RULE_STRESS_TRANSFER: {
        'key': RULE_STRESS_TRANSFER,
        'label': 'Stress Transfer',
        'status': 'live',
        'tone': 'stress',
        'category': 'stressed',
    },
    RULE_PRESSURE_DISTRIBUTION: {
        'key': RULE_PRESSURE_DISTRIBUTION,
        'label': 'Pressure Distribution',
        'status': 'live',
        'tone': 'rest',
        'category': 'rested',
    },
    RULE_SUSTAINABILITY_QUESTION: {
        'key': RULE_SUSTAINABILITY_QUESTION,
        'label': 'Sustainability Question',
        'status': 'live',
        'tone': 'stress',
        'category': 'stressed',
    },
    RULE_HIDDEN_CAPACITY_LOSS: {
        'key': RULE_HIDDEN_CAPACITY_LOSS,
        'label': 'Hidden Capacity Loss',
        'status': 'live',
        'tone': 'stress',
        'category': 'stressed',
    },
    RULE_SPECIAL_SITUATION: {
        'key': RULE_SPECIAL_SITUATION,
        'label': 'Special Situation',
        'status': 'dormant',
        'missing_inputs': ['forward_planned_start_input'],
    },
}

SKELETONS = {
    RULE_STRESS_TRANSFER: {
        BEAT_SIGNAL: "The {team_name} are running tonight's bullpen through a smaller group.",
        BEAT_EVIDENCE: 'The top {top_arm_count} arms have taken {top_share_pct}% of recent relief pitches ({concentration_descriptor}), and {available_count} of {total_bullpen_arms} bullpen arms are Available.',
        BEAT_MECHANISM: 'That usually leaves the next close innings pointed back toward the same usable arms.',
        'implication_with_clean_trust': 'Tonight, {clean_trust_late_route_clause}; {clean_option_count} of {total_bullpen_arms} bullpen arms are clean behind them.',
        'implication_without_clean_trust': 'Tonight, none of the usual trusted late arms are fully clean; {clean_option_count} of {total_bullpen_arms} usable arms sit outside that group.',
    },
    RULE_PRESSURE_DISTRIBUTION: {
        BEAT_SIGNAL: 'The {team_name} bullpen work is spread out tonight.',
        BEAT_EVIDENCE: '{participant_count} arms shared the last {window_days} days of relief work, averaging {per_arm_pitches} pitches each.',
        BEAT_MECHANISM: 'When recent work is light and spread out, the manager has more ways through the late innings.',
        'implication_with_clean_trust': 'Tonight, {clean_trust_names} {clean_trust_verb} fully clean, with {clean_option_count} of {total_bullpen_arms} bullpen arms clean behind them.',
        'implication_without_clean_trust': 'Tonight, the usable arms are outside the usual trusted late-inning group; {clean_option_count} of {total_bullpen_arms} bullpen arms are clean.',
    },
    RULE_SUSTAINABILITY_QUESTION: {
        BEAT_SIGNAL: 'The {team_name} bullpen has pitched well this year, but they are leaning on it hard tonight.',
        'evidence_with_high_risk': 'This bullpen has still run a {season_era} season ERA, {era_rank_ordinal} among current pens, but recent workload is {per_arm_pitches} pitches per participating arm with {high_risk_arm_count} {high_risk_arm_word} at HIGH or CRITICAL fatigue.',
        'evidence_without_high_risk': 'This bullpen has still run a {season_era} season ERA, {era_rank_ordinal} among current pens, but recent workload is {per_arm_pitches} pitches per participating arm over the last {window_days} days.',
        BEAT_MECHANISM: '{sustainability_mechanism_text}',
        'implication_with_clean_trust': '{clean_trust_late_sentence} The question is whether they have to go there before the eighth.',
        'implication_without_clean_trust': 'Tonight, there is no fully clean trusted late-inning arm; the question is whether {clean_option_count} usable arms can handle leverage without dragging the same group back in.',
    },
    RULE_HIDDEN_CAPACITY_LOSS: {
        BEAT_SIGNAL: "The {team_name} results are solid, but tonight's usable depth is thin.",
        'evidence_with_roster_gap': 'This bullpen has a {season_era} season ERA, {era_rank_ordinal} among current pens, with {available_count} of {total_bullpen_arms} arms Available and {roster_unavailable_count} {roster_unavailable_word} off the active roster.',
        'evidence_without_roster_gap': 'This bullpen has a {season_era} season ERA, {era_rank_ordinal} among current pens, with {available_count} of {total_bullpen_arms} arms Available tonight.',
        BEAT_MECHANISM: 'That does not make the results fake; it means there is less margin if tonight turns into a bullpen game.',
        'implication_with_clean_trust': '{clean_trust_late_sentence} The question is what happens if the game needs one more clean inning before then.',
        'implication_without_clean_trust': 'Tonight, the usable arms sit outside the usual trusted late-inning group; the question is what happens if the game needs one more clean inning.',
    },
}

LEAD_FRAGMENT_LIBRARY = {
    LEAD_FATIGUE_LOAD: {
        BEAT_SIGNAL: 'Fatigue is already part of the {team_name} bullpen picture: {high_risk_arm_names} {high_risk_arm_verb} running hot.',
        BEAT_EVIDENCE: 'This group has run a {season_era} ERA, {era_rank_ordinal} among current pens, but recent workload is {per_arm_pitches} pitches per participating arm with {high_risk_arm_count} {high_risk_arm_word} at HIGH or CRITICAL fatigue.',
    },
    LEAD_TRUST_LANE_ABSENCE: {
        BEAT_SIGNAL: 'The {team_name} have clean arms available, but not their usual trusted late-inning group.',
        BEAT_EVIDENCE: 'This group has run a {season_era} ERA, {era_rank_ordinal} among current pens, with {clean_option_count} usable arms and zero clean trusted late-inning arms.',
    },
    LEAD_TRUST_LANE_SHALLOW: {
        BEAT_SIGNAL: 'The {team_name} have room tonight, but the trusted late-inning group is thin.',
        BEAT_EVIDENCE: '{clean_trust_names} {clean_trust_verb} the only fully clean trusted late-inning option, with {clean_option_count} usable arms and a {season_era} ERA, {era_rank_ordinal} among current pens.',
    },
    LEAD_WORKLOAD_HIGH: {
        BEAT_SIGNAL: 'The {team_name} have pitched well, but the recent workload is the loud part.',
        BEAT_EVIDENCE: 'Recent workload is {per_arm_pitches} pitches per participating arm over the last {window_days} days, and this group has run a {season_era} ERA, {era_rank_ordinal} among current pens.',
    },
    LEAD_WORKLOAD_LIGHT: {
        BEAT_SIGNAL: 'The {team_name} have room because the recent work stayed light and spread out.',
        BEAT_EVIDENCE: '{participant_count} arms shared the last {window_days} days of relief work at {per_arm_pitches} pitches per participating arm, and this group has run a {season_era} ERA, {era_rank_ordinal} among current pens.',
    },
    LEAD_AVAILABILITY_THIN: {
        BEAT_SIGNAL: 'The {team_name} are short on clean depth tonight.',
        BEAT_EVIDENCE: '{available_count} of {total_bullpen_arms} bullpen arms are Available tonight, with {clean_option_count} usable arms and a {season_era} ERA, {era_rank_ordinal} among current pens.',
    },
    LEAD_AVAILABILITY_DEEP: {
        BEAT_SIGNAL: 'The {team_name} have real bullpen room tonight.',
        BEAT_EVIDENCE: '{available_count} of {total_bullpen_arms} bullpen arms are Available, with {clean_option_count} usable arms and a {season_era} ERA, {era_rank_ordinal} among current pens.',
    },
    LEAD_DEEP_INTACT: {
        BEAT_SIGNAL: 'The {team_name} still have trusted late-inning options behind the workload.',
        BEAT_EVIDENCE: '{clean_trust_names} {clean_trust_verb} fully clean trusted late-inning options, with {available_count} of {total_bullpen_arms} bullpen arms Available and a {season_era} ERA, {era_rank_ordinal} among current pens.',
    },
    LEAD_CONCENTRATION_SHAPE: {
        BEAT_SIGNAL: '{workload_concentration_signal}',
        BEAT_EVIDENCE: 'The top {top_arm_count} arms have taken {top_share_pct}% of recent relief pitches ({concentration_descriptor}), and this group has run a {season_era} ERA, {era_rank_ordinal} among current pens.',
    },
    LEAD_PARTICIPATION_NARROW: {
        BEAT_SIGNAL: 'The {team_name} have shared the work, but not across a deep group.',
        BEAT_EVIDENCE: '{participant_count} arms shared recent relief work at {per_arm_pitches} pitches per participating arm, with a {season_era} ERA, {era_rank_ordinal} among current pens.',
    },
    LEAD_PARTICIPATION_BROAD: {
        BEAT_SIGNAL: 'The {team_name} have used more than one corner of the pen.',
        BEAT_EVIDENCE: '{participant_count} arms shared recent relief work, with {per_arm_pitches} pitches per participating arm and a {season_era} ERA, {era_rank_ordinal} among current pens.',
    },
    LEAD_ERA_ELITE: {
        BEAT_SIGNAL: 'The {team_name} have run prevention working in their favor tonight.',
        BEAT_EVIDENCE: 'This bullpen has run a {season_era} ERA, {era_rank_ordinal} among current pens, with {available_count} of {total_bullpen_arms} arms Available.',
    },
    LEAD_ERA_ORDINARY: {
        BEAT_SIGNAL: 'The {team_name} are rested, but the edge is depth more than run prevention.',
        BEAT_EVIDENCE: 'This bullpen has run a {season_era} ERA, {era_rank_ordinal} among current pens, while {participant_count} arms shared recent work.',
    },
    LEAD_TRUST_LANE_DEPTH: {
        BEAT_SIGNAL: 'The {team_name} still have multiple trusted late-inning options tonight.',
        BEAT_EVIDENCE: '{clean_trust_names} {clean_trust_verb} clean trusted late-inning options, and this group has run a {season_era} ERA, {era_rank_ordinal} among current pens.',
    },
}


@dataclass(frozen=True)
class TeamInputs:
    team: dict[str, Any]
    records: list[dict[str, Any]]
    logs_by_pitcher: dict[int, list[Any]]
    reference_date: Any
    season_era_by_team: dict[int, dict[str, Any]] | None = None
    capacity_by_team: dict[int, dict[str, Any]] | None = None
    rotation_support_by_team: dict[int, dict[str, Any]] | None = None
    bullpen_stability_by_team: dict[int, dict[str, Any]] | None = None
    bullpen_environment_by_team: dict[int, dict[str, Any]] | None = None


def _truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def four_beat_stories_enabled(config=None):
    if config is not None:
        return _truthy(config.get(FEATURE_FLAG, True))
    return _truthy(os.environ.get(FEATURE_FLAG, 'true'))


def _value(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _pct(value):
    return int(round(float(value or 0) * 100))


def _format_decimal(value):
    number = round(float(value or 0), 1)
    return str(int(number)) if number.is_integer() else f'{number:.1f}'


def _format_era(value):
    if value is None:
        return None
    return f'{float(value):.2f}'


def _era_rank_value(item):
    outs = int(item.get('innings_outs') or 0)
    earned_runs = item.get('earned_runs')
    if outs > 0 and earned_runs is not None:
        return (float(earned_runs) * 27.0) / outs
    return float(item.get('era'))


def _ordinal(value):
    number = int(value or 0)
    suffix = 'th'
    if number % 100 not in (11, 12, 13):
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return f'{number}{suffix}'


def _plural(value, singular, plural=None):
    return singular if int(value or 0) == 1 else (plural or f'{singular}s')


def _join_names(names):
    clean = [str(name).strip() for name in names or [] if str(name or '').strip()]
    if not clean:
        return ''
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f'{clean[0]} and {clean[1]}'
    return f'{", ".join(clean[:-1])}, and {clean[-1]}'


def _fill_skeleton(skeleton, slots):
    if not skeleton:
        return None
    required = [
        field_name
        for _literal, field_name, _format_spec, _conversion in string.Formatter().parse(skeleton)
        if field_name
    ]
    if any(slots.get(name) in (None, '') for name in required):
        return None
    try:
        return skeleton.format(**slots)
    except (KeyError, ValueError):
        return None


def _team_key(record):
    pitcher = record.get('pitcher')
    if pitcher is None:
        return None
    return _value(pitcher, 'team_id')


def _team_identity(record):
    pitcher = record.get('pitcher')
    return {
        'team_id': _value(pitcher, 'team_id'),
        'team_name': _value(pitcher, 'team_name'),
        'team_abbreviation': _value(pitcher, 'team_abbreviation'),
    }


def _ranked_era_by_team(season_era):
    bullpens = (season_era or {}).get('bullpens') or []
    eligible = [
        item for item in bullpens
        if item.get('team_id') is not None
        and item.get('era') is not None
        and int(item.get('innings_outs') or 0) > 0
    ]
    eligible.sort(key=lambda item: (
        _era_rank_value(item),
        item.get('team_abbreviation') or '',
        item.get('team_id') or 0,
    ))
    total = len(eligible)
    if total <= 0:
        return {}
    strong_cutoff = min(STRONG_SEASON_ERA_TOP_BULLPENS, total)
    solid_cutoff = min(SOLID_SEASON_ERA_TOP_BULLPENS, total)
    ranked = {}
    for rank, item in enumerate(eligible, start=1):
        team_id = item.get('team_id')
        ranked[team_id] = {
            **item,
            'rank': rank,
            'rank_total': total,
            'strong_results': rank <= strong_cutoff,
            'solid_results': rank <= solid_cutoff,
        }
    return ranked


def _season_era_summary(team_inputs):
    team_id = team_inputs.team.get('team_id')
    if team_id is None:
        return {
            'available': False,
            'era': None,
            'rank': None,
            'rank_total': None,
            'strong_results': False,
            'solid_results': False,
        }
    item = (team_inputs.season_era_by_team or {}).get(team_id)
    if not item:
        return {
            'available': False,
            'era': None,
            'rank': None,
            'rank_total': None,
            'strong_results': False,
            'solid_results': False,
        }
    return {
        'available': True,
        'era': item.get('era'),
        'innings_outs': item.get('innings_outs'),
        'earned_runs': item.get('earned_runs'),
        'rank': item.get('rank'),
        'rank_total': item.get('rank_total'),
        'strong_results': bool(item.get('strong_results')),
        'solid_results': bool(item.get('solid_results')),
    }


def _status_counts(records):
    counts = {
        STATUS_AVAILABLE: 0,
        STATUS_MONITOR: 0,
        STATUS_LIMITED: 0,
        STATUS_AVOID: 0,
        STATUS_UNAVAILABLE: 0,
    }
    for record in records:
        status = (record.get('availability') or {}).get('availability_status')
        if status in counts:
            counts[status] += 1
    return counts


def _workload_summary(team_inputs):
    pitcher_ids = {
        _value(record.get('pitcher'), 'id')
        for record in team_inputs.records
        if _value(record.get('pitcher'), 'id') is not None
    }
    return summarize_recent_relief_workload(
        team_inputs.logs_by_pitcher,
        team_inputs.reference_date,
        pitcher_ids=pitcher_ids,
    )


def _availability_summary(records):
    counts = _status_counts(records)
    total = sum(counts.values())
    available = counts[STATUS_AVAILABLE]
    available_share = available / total if total else 0
    return {
        'counts': counts,
        'total': total,
        'available': available,
        'available_share': available_share,
    }


def _high_risk_options(records):
    arms = []
    for record in records:
        risk = str(_value(record.get('score'), 'risk_level') or '').upper()
        if risk in LIGHT_HIGH_RISK_LEVELS:
            pitcher = record.get('pitcher')
            pitcher_id = _value(pitcher, 'id')
            name = _value(pitcher, 'full_name')
            arms.append({
                'pitcher_id': pitcher_id,
                'name': name,
                'risk_level': risk,
            })
    arms.sort(key=lambda item: (item.get('name') or '', item.get('pitcher_id') or 0))
    return arms


def _roster_unavailable_count(records):
    count = 0
    for record in records:
        roster_status = record.get('roster_status') or {}
        if roster_status.get('is_active_mlb') is False:
            count += 1
    return count


def _clean_options(records, logs_by_pitcher, reference_date):
    clean = []
    clean_trust = []
    for record in records:
        pitcher = record.get('pitcher')
        pitcher_id = _value(pitcher, 'id')
        if pitcher_id is None:
            continue
        _role, labels = author_role_read_labels(
            record,
            logs_by_pitcher,
            reference_date,
        )
        read_key = ((labels.get('read') or {}).get('key') or '')
        if read_key != 'clean_option':
            continue
        name = _value(pitcher, 'full_name')
        role_key = ((labels.get('role') or {}).get('key') or '')
        item = {
            'pitcher_id': pitcher_id,
            'name': name,
            'role_key': role_key,
            'read_key': read_key,
        }
        clean.append(item)
        if role_key == 'trust_arm':
            clean_trust.append(item)
    return clean, clean_trust


def compute_team_story_inputs(team_inputs):
    workload = _workload_summary(team_inputs)
    availability = _availability_summary(team_inputs.records)
    season_era = _season_era_summary(team_inputs)
    team_id = team_inputs.team.get('team_id')
    capacity_intelligence = (team_inputs.capacity_by_team or {}).get(team_id) or {}
    rotation_support_pressure = (team_inputs.rotation_support_by_team or {}).get(team_id) or {}
    bullpen_stability = (team_inputs.bullpen_stability_by_team or {}).get(team_id) or {}
    bullpen_environment = (team_inputs.bullpen_environment_by_team or {}).get(team_id) or {}
    clean, clean_trust = _clean_options(
        team_inputs.records,
        team_inputs.logs_by_pitcher,
        team_inputs.reference_date,
    )
    high_risk_options = _high_risk_options(team_inputs.records)
    high_risk = len(high_risk_options)
    roster_unavailable = _roster_unavailable_count(team_inputs.records)

    concentration = (
        workload['total_pitches'] > 0
        and workload['top_arm_count'] == CONCENTRATED_TOP_ARM_COUNT
        and workload['top_share'] >= CONCENTRATED_TOP_SHARE_MIN
    )
    thin = (
        availability['total'] > 0
        and (
            availability['available'] <= THIN_AVAILABLE_COUNT_MAX
            or availability['available_share'] <= THIN_AVAILABLE_SHARE_MAX
        )
    )
    light = (
        high_risk == 0
        and workload['participant_count'] > 0
        and workload['per_arm_pitches'] <= LIGHT_PER_ARM_PITCHES_MAX
    )
    broad = (
        workload['participant_count'] >= BROAD_PARTICIPATION_MIN_ARMS
        and workload['top_one_share'] <= BROAD_SINGLE_ARM_SHARE_MAX
    )
    heavy = (
        high_risk >= HEAVY_HIGH_RISK_ARM_MIN
        or (
            workload['participant_count'] > 0
            and workload['per_arm_pitches'] >= HEAVY_PER_ARM_PITCHES_MIN
        )
    )
    depleted = (
        availability['total'] > 0
        and (
            availability['available'] <= DEPLETED_AVAILABLE_COUNT_MAX
            or availability['available_share'] <= DEPLETED_AVAILABLE_SHARE_MAX
            or roster_unavailable >= DEPLETED_ROSTER_UNAVAILABLE_MIN
        )
    )

    return {
        'team': team_inputs.team,
        'workload': workload,
        'availability': availability,
        'capacity_intelligence': capacity_intelligence,
        'rotation_support_pressure': rotation_support_pressure,
        'bullpen_stability': bullpen_stability,
        'bullpen_environment': bullpen_environment,
        'season_era': season_era,
        'clean_options': clean,
        'clean_trust_options': clean_trust,
        'high_risk_arms': high_risk,
        'high_risk_arm_options': high_risk_options,
        'roster_unavailable_arms': roster_unavailable,
        'conditions': {
            'workload_concentrated': concentration,
            'availability_thin': thin,
            'workload_light': light,
            'broad_participation': broad,
            'season_era_strong': season_era['strong_results'],
            'season_era_solid': season_era['solid_results'],
            'heavy_recent_workload': heavy,
            'depleted_depth': depleted,
        },
    }


def _base_slots(inputs):
    team = inputs['team']
    workload = inputs['workload']
    availability = inputs['availability']
    season_era = inputs['season_era']
    clean_options = inputs['clean_options']
    clean_trust = inputs['clean_trust_options']
    clean_trust_names = _join_names([item['name'] for item in clean_trust])
    clean_trust_verb = 'is' if len(clean_trust) == 1 else 'are'
    high_risk = inputs['high_risk_arms']
    high_risk_options = inputs.get('high_risk_arm_options') or []
    high_risk_names = _join_names([item['name'] for item in high_risk_options])
    roster_unavailable = inputs['roster_unavailable_arms']
    return {
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
        'team_id': team.get('team_id'),
        'window_days': RECENT_WORKLOAD_WINDOW_DAYS,
        'top_arm_count': workload['top_arm_count'],
        'top_share_pct': _pct(workload['top_share']),
        'top_one_share_pct': _pct(workload['top_one_share']),
        'total_recent_pitches': workload['total_pitches'],
        'concentration_descriptor': workload['concentration_descriptor'],
        'participant_count': workload['participant_count'],
        'per_arm_pitches': _format_decimal(workload['per_arm_pitches']),
        'available_count': availability['available'],
        'available_share_pct': _pct(availability['available_share']),
        'total_bullpen_arms': availability['total'],
        'season_era': _format_era(season_era.get('era')),
        'era_rank': season_era.get('rank'),
        'era_rank_ordinal': _ordinal(season_era.get('rank')),
        'era_rank_total': season_era.get('rank_total'),
        'high_risk_arm_count': high_risk,
        'high_risk_arm_word': _plural(high_risk, 'arm'),
        'high_risk_arm_names': high_risk_names,
        'high_risk_arm_verb': 'is' if high_risk == 1 else 'are',
        'roster_unavailable_count': roster_unavailable,
        'roster_unavailable_word': _plural(roster_unavailable, 'arm'),
        'clean_option_count': len(clean_options),
        'clean_trust_count': len(clean_trust),
        'clean_trust_names': clean_trust_names,
        'clean_trust_verb': clean_trust_verb,
        'clean_trust_late_route_clause': _story_phrase(
            'clean_trust_late_route_clause',
            inputs,
            clean_trust_names,
            clean_trust_verb,
            clean_trust_names=clean_trust_names,
            clean_trust_verb=clean_trust_verb,
        ),
        'clean_trust_late_sentence': _story_phrase(
            'clean_trust_late_sentence',
            inputs,
            clean_trust_names,
            clean_trust_verb,
            clean_trust_names=clean_trust_names,
            clean_trust_verb=clean_trust_verb,
        ),
        'sustainability_mechanism_text': _story_phrase(
            'sustainability_mechanism',
            inputs,
        ),
        'workload_concentration_signal': _story_phrase(
            'workload_concentration_signal',
            inputs,
            team_name=team.get('team_name'),
        ),
    }


def _story_href(team):
    key = team.get('team_abbreviation') or team.get('team_id')
    if key is None:
        return None
    return f'/bullpen?view=board&team={key}&source=four-beat-stories'


def _strength(rule_key, inputs):
    workload = inputs['workload']
    availability = inputs['availability']
    season_era = inputs['season_era']
    if rule_key == RULE_STRESS_TRANSFER:
        concentration_points = max(0, workload['top_share'] - CONCENTRATED_TOP_SHARE_MIN) * 100
        thin_count_points = max(0, THIN_AVAILABLE_COUNT_MAX - availability['available']) * 5
        thin_share_points = max(0, THIN_AVAILABLE_SHARE_MAX - availability['available_share']) * 100
        return round(STRESS_TRANSFER_STRENGTH_OFFSET + concentration_points + thin_count_points + thin_share_points, 1)
    if rule_key == RULE_PRESSURE_DISTRIBUTION:
        breadth_points = max(0, workload['participant_count'] - BROAD_PARTICIPATION_MIN_ARMS) * 3
        spread_points = max(0, BROAD_SINGLE_ARM_SHARE_MAX - workload['top_one_share']) * 100
        load_points = max(0, LIGHT_PER_ARM_PITCHES_MAX - workload['per_arm_pitches'])
        return round(PRESSURE_DISTRIBUTION_STRENGTH_OFFSET + breadth_points + spread_points + load_points, 1)
    if rule_key == RULE_SUSTAINABILITY_QUESTION:
        rank_points = max(0, STRONG_SEASON_ERA_TOP_BULLPENS - int(season_era.get('rank') or 0) + 1)
        workload_points = max(0, workload['per_arm_pitches'] - HEAVY_PER_ARM_PITCHES_MIN)
        risk_points = inputs['high_risk_arms'] * 5
        return round(SUSTAINABILITY_QUESTION_STRENGTH_OFFSET + rank_points + workload_points + risk_points, 1)
    if rule_key == RULE_HIDDEN_CAPACITY_LOSS:
        rank_points = max(0, SOLID_SEASON_ERA_TOP_BULLPENS - int(season_era.get('rank') or 0) + 1) * 0.5
        thin_count_points = max(0, DEPLETED_AVAILABLE_COUNT_MAX - availability['available']) * 5
        thin_share_points = max(0, DEPLETED_AVAILABLE_SHARE_MAX - availability['available_share']) * 100
        roster_points = inputs['roster_unavailable_arms'] * 5
        return round(HIDDEN_CAPACITY_LOSS_STRENGTH_OFFSET + rank_points + thin_count_points + thin_share_points + roster_points, 1)
    return 0


def _beat(rule_key, beat_key, skeleton_key, slots):
    skeleton = SKELETONS[rule_key].get(skeleton_key)
    text = _fill_skeleton(skeleton, slots)
    if not text:
        return None
    return {
        'key': beat_key,
        'label': beat_key.capitalize(),
        'text': text,
        'skeleton_key': skeleton_key,
        'slots': {
            key: slots[key]
            for key in sorted(slots)
            if key in (skeleton or '')
        },
    }


def _evidence_skeleton_key(rule_key, inputs):
    if rule_key == RULE_SUSTAINABILITY_QUESTION:
        if inputs['high_risk_arms'] >= HEAVY_HIGH_RISK_ARM_MIN:
            return 'evidence_with_high_risk'
        return 'evidence_without_high_risk'
    if rule_key == RULE_HIDDEN_CAPACITY_LOSS:
        if inputs['roster_unavailable_arms'] >= DEPLETED_ROSTER_UNAVAILABLE_MIN:
            return 'evidence_with_roster_gap'
        return 'evidence_without_roster_gap'
    return BEAT_EVIDENCE


def _evidence_notable(rule_key, inputs):
    workload = inputs['workload']
    availability = inputs['availability']
    season_era = inputs['season_era']
    if rule_key == RULE_STRESS_TRANSFER:
        return (
            workload['top_arm_count'] == CONCENTRATED_TOP_ARM_COUNT
            and workload['top_share'] >= CONCENTRATED_TOP_SHARE_MIN
            and availability['total'] > 0
            and (
                availability['available'] <= THIN_AVAILABLE_COUNT_MAX
                or availability['available_share'] <= THIN_AVAILABLE_SHARE_MAX
            )
        )
    if rule_key == RULE_PRESSURE_DISTRIBUTION:
        return (
            workload['participant_count'] >= BROAD_PARTICIPATION_MIN_ARMS
            and workload['per_arm_pitches'] <= LIGHT_PER_ARM_PITCHES_MAX
            and workload['top_one_share'] <= BROAD_SINGLE_ARM_SHARE_MAX
        )
    if rule_key == RULE_SUSTAINABILITY_QUESTION:
        return (
            season_era['strong_results']
            and inputs['conditions']['heavy_recent_workload']
        )
    if rule_key == RULE_HIDDEN_CAPACITY_LOSS:
        return (
            season_era['solid_results']
            and inputs['conditions']['depleted_depth']
        )
    return False


def _rule_conditions_hold(rule_key, inputs):
    conditions = inputs['conditions']
    if rule_key == RULE_STRESS_TRANSFER:
        return conditions['workload_concentrated'] and conditions['availability_thin']
    if rule_key == RULE_PRESSURE_DISTRIBUTION:
        return conditions['workload_light'] and conditions['broad_participation']
    if rule_key == RULE_SUSTAINABILITY_QUESTION:
        return conditions['season_era_strong'] and conditions['heavy_recent_workload']
    if rule_key == RULE_HIDDEN_CAPACITY_LOSS:
        return conditions['season_era_solid'] and conditions['depleted_depth']
    return False


def _limited_status(status):
    return str(status or '').strip().lower() in LIMITED_CONTEXT_STATUSES


def _has_blocking_limitations(layer):
    return bool((layer or {}).get('limitations'))


def _has_source_limitations(layer):
    return bool((layer or {}).get('source_limitations'))


def _limitation_texts(layer):
    return [
        str(limitation or '').strip().lower()
        for limitation in (layer or {}).get('limitations') or []
        if str(limitation or '').strip()
    ]


def _limitation_matches(layer, fragments):
    texts = _limitation_texts(layer)
    return any(
        fragment in text
        for text in texts
        for fragment in fragments
    )


def _text_matches(text, fragments):
    return any(fragment in text for fragment in fragments)


def _capacity_has_count_based_disclosure(capacity_loss):
    return _limitation_matches(capacity_loss, (
        'capacity uses count-based weighting',
        'relief workload sample is limited',
        'limited relief workload history',
    ))


def _capacity_unknown_limited_read_blocks(capacity_loss):
    unknown_pct = _number_or_none(
        capacity_loss.get('unknown_limited_read_capacity_pct')
    )
    has_unknown_limitation = _limitation_matches(capacity_loss, (
        'limited-read or unknown availability inputs',
        'unknown availability inputs',
        'unknown capacity',
    ))
    if not has_unknown_limitation and not unknown_pct:
        return False
    if unknown_pct is None:
        return True
    return unknown_pct >= CAPACITY_UNKNOWN_LIMITED_READ_BLOCK_PCT_MIN


def _capacity_limitation_is_disclosure(text, capacity_loss):
    if _text_matches(text, (
        'capacity uses count-based weighting',
        'relief workload sample is limited',
        'limited relief workload history',
    )):
        return True
    if _text_matches(text, (
        'limited-read or unknown availability inputs',
        'unknown availability inputs',
        'unknown capacity',
    )):
        unknown_pct = _number_or_none(
            capacity_loss.get('unknown_limited_read_capacity_pct')
        )
        return (
            unknown_pct is not None
            and unknown_pct < CAPACITY_UNKNOWN_LIMITED_READ_BLOCK_PCT_MIN
        )
    return False


def _capacity_limitations_block(capacity_loss):
    texts = _limitation_texts(capacity_loss)
    if not texts:
        return False
    if _capacity_unknown_limited_read_blocks(capacity_loss):
        return True
    return any(
        not _capacity_limitation_is_disclosure(text, capacity_loss)
        for text in texts
    )


def _stability_limitations_block(stability):
    texts = _limitation_texts(stability)
    if not texts:
        return False
    return any(
        not _text_matches(text, (
            'usage patterns',
            'does not imply transaction',
            'roster-move data is not used',
            'roster move data is not used',
        ))
        for text in texts
    )


def _environment_limitations_block(environment):
    if not (environment or {}).get('limitations'):
        return False
    return _limitation_matches(environment, (
        'limited read',
        'limited or uncertain',
        'incomplete starter/relief workload data',
        'unknown availability inputs',
    ))


def _has_pressure_story_conditions(inputs):
    conditions = inputs.get('conditions') or {}
    return any(
        conditions.get(key)
        for key in (
            'workload_concentrated',
            'availability_thin',
            'depleted_depth',
            'heavy_recent_workload',
        )
    )


def _number_or_none(value):
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy_count(value):
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False


def _phrase_index(parts, count):
    if count <= 1:
        return 0
    key = '|'.join(str(part or '') for part in parts)
    return sum((idx + 1) * ord(char) for idx, char in enumerate(key)) % count


def _story_phrase(pool_key, inputs, *extra_parts, **values):
    variants = PHRASE_VARIANTS.get(pool_key) or ()
    if not variants:
        return ''
    team = (inputs or {}).get('team') or {}
    parts = (
        pool_key,
        team.get('team_abbreviation') or '',
        team.get('team_id') or '',
        *extra_parts,
    )
    template = variants[_phrase_index(parts, len(variants))]
    return template.format(**values)


def _why_context_item(source, text, layer=None, flags=None, disclosure_limitations=False):
    return {
        'source': source,
        'text': text,
        'context_flags': list(flags or []),
        'source_limitations_present': (
            _has_source_limitations(layer) or bool(disclosure_limitations)
        ),
    }


def _context_list_text(labels):
    clean = [label for label in labels if label]
    if len(clean) == 2:
        text = f'{clean[0]}, and {clean[1]}.'
        return f'{text[:1].upper()}{text[1:]}'
    if len(clean) > 2:
        text = f'{", ".join(clean[:-1])}, and {clean[-1]}.'
        return f'{text[:1].upper()}{text[1:]}'
    if clean:
        text = f'{clean[0]}.'
        return f'{text[:1].upper()}{text[1:]}'
    return ''


def _environment_context_item(inputs, eligible_items_by_source):
    environment = inputs.get('bullpen_environment') or {}
    if not environment:
        return None
    status = str(environment.get('status') or '').strip().lower()
    sources = [
        str(source or '').strip()
        for source in environment.get('primary_pressure_sources') or []
        if str(source or '').strip()
    ]
    if (
        status != 'multi_source_pressure'
        or len(sources) < 2
        or _limited_status(status)
        or _environment_limitations_block(environment)
    ):
        return None

    eligible_sources = [
        source for source in sources
        if source in eligible_items_by_source
    ]
    if len(eligible_sources) < 2:
        return None

    label_by_source = {
        'capacity_loss': _story_phrase(
            'environment_capacity_label',
            inputs,
            'capacity_loss',
        ),
        'rotation_support_pressure': _story_phrase(
            'environment_rotation_label',
            inputs,
            'rotation_support_pressure',
        ),
        'bullpen_stability': _story_phrase(
            'environment_stability_label',
            inputs,
            'bullpen_stability',
        ),
    }
    labels = [label_by_source.get(source) for source in eligible_sources]
    detail = _context_list_text(labels)
    if not detail:
        return None
    intro = _story_phrase('environment_intro', inputs, '+'.join(eligible_sources))
    disclosure_limitations = any(
        (eligible_items_by_source[source] or {}).get('source_limitations_present')
        for source in eligible_sources
    )
    return _why_context_item(
        'bullpen_environment',
        f'{intro} {detail}',
        environment,
        flags=environment.get('context_flags') or [],
        disclosure_limitations=disclosure_limitations,
    )


def _capacity_context_item(inputs):
    capacity_intelligence = inputs.get('capacity_intelligence') or {}
    capacity_loss = capacity_intelligence.get('capacity_loss') or {}
    status = str(capacity_loss.get('status') or '').strip().lower()
    unavailable_pct = _number_or_none(capacity_loss.get('unavailable_capacity_pct'))
    if (
        not capacity_loss
        or _limited_status(status)
        or _capacity_limitations_block(capacity_loss)
        or unavailable_pct is None
        or (status not in CAPACITY_PRESSURE_STATUSES and unavailable_pct < 20)
    ):
        return None
    has_count_based_disclosure = _capacity_has_count_based_disclosure(capacity_loss)
    text = _story_phrase(
        'capacity_context_fallback' if has_count_based_disclosure else 'capacity_context_standard',
        inputs,
        'fallback' if has_count_based_disclosure else 'standard',
    )
    return _why_context_item(
        'capacity_loss',
        text,
        capacity_loss,
        disclosure_limitations=has_count_based_disclosure,
    )


def _rotation_context_item(inputs):
    rotation = inputs.get('rotation_support_pressure') or {}
    status = str(rotation.get('status') or '').strip().lower()
    if (
        not rotation
        or status not in ROTATION_PRESSURE_STATUSES
        or _limited_status(status)
        or _has_blocking_limitations(rotation)
        or not _truthy_count(rotation.get('games_analyzed'))
    ):
        return None
    return _why_context_item(
        'rotation_support_pressure',
        _story_phrase('rotation_context', inputs),
        rotation,
    )


def _stability_context_item(inputs):
    stability = inputs.get('bullpen_stability') or {}
    status = str(stability.get('status') or '').strip().lower()
    if (
        not stability
        or status not in STABILITY_CONTEXT_STATUSES
        or _limited_status(status)
        or _stability_limitations_block(stability)
        or not _truthy_count(stability.get('recently_used_bullpen_count'))
        or int(stability.get('recently_used_bullpen_count') or 0) < STABILITY_CONTEXT_MIN_RECENT_USED
    ):
        return None
    return _why_context_item(
        'bullpen_stability',
        _story_phrase('stability_context', inputs),
        stability,
        flags=[status],
    )


def _why_context_items(rule_key, inputs):
    if rule_key not in WHY_CONTEXT_PRESSURE_RULES or not _has_pressure_story_conditions(inputs):
        return []

    source_items = [
        item
        for item in (
            _capacity_context_item(inputs),
            _rotation_context_item(inputs),
            _stability_context_item(inputs),
        )
        if item
    ]
    items_by_source = {
        item['source']: item
        for item in source_items
    }

    environment = _environment_context_item(inputs, items_by_source)
    if environment:
        return [environment]

    return source_items[:2]


def _why_context_beat(rule_key, inputs):
    items = _why_context_items(rule_key, inputs)
    if not items:
        return None
    sources = [item['source'] for item in items]
    flags = []
    for item in items:
        flags.extend(item.get('context_flags') or [])
    return {
        'key': BEAT_CONTEXT,
        'label': 'Context',
        'text': ' '.join(item['text'] for item in items),
        'skeleton_key': f"why_context:{'+'.join(sources)}",
        'sources': sources,
        'context_flags': sorted(set(flags)),
        'source_limitations_present': any(item.get('source_limitations_present') for item in items),
        'items': [
            {
                'source': item.get('source'),
                'text': item.get('text'),
                'source_limitations_present': bool(item.get('source_limitations_present')),
                'disclosure_limitations': bool(item.get('disclosure_limitations')),
                'context_flags': item.get('context_flags') or [],
            }
            for item in items
        ],
        'slots': {},
    }


def _lead_priority(dimension):
    try:
        return LEAD_DIMENSION_TIE_BREAK_ORDER.index(dimension)
    except ValueError:
        return len(LEAD_DIMENSION_TIE_BREAK_ORDER)


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rank(value, default=999):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _unique_sorted(values):
    return sorted(set(values))


def _max_gap(value, values):
    unique = _unique_sorted(values)
    if not unique or value != unique[-1]:
        return 0
    if len(unique) == 1:
        return 0
    return value - unique[-2]


def _min_gap(value, values):
    unique = _unique_sorted(values)
    if not unique or value != unique[0]:
        return 0
    if len(unique) == 1:
        return 0
    return unique[1] - value


def _lead_candidate(dimension, score, value, reason, direction=None):
    return {
        'dimension': dimension,
        'score': round(float(score), 3),
        'value': value,
        'reason': reason,
        'direction': direction,
        'tie_break_order': _lead_priority(dimension),
        'signal_skeleton_key': f'lead_signal:{dimension}',
        'evidence_skeleton_key': f'lead_evidence:{dimension}',
    }


def _team_story_key(record):
    story = record.get('story') or {}
    return (story.get('team_id'), story.get('rule_key'))


def _story_feed_order_key(record):
    story = record.get('story') or {}
    return (
        -_number(story.get('strength')),
        story.get('team_abbreviation') or '',
        story.get('team_name') or '',
        story.get('team_id') or 0,
        story.get('rule_key') or '',
    )


def _team_lead_candidates(record, cluster):
    inputs = record['inputs']
    rule_key = (record.get('story') or {}).get('rule_key')
    workload = inputs['workload']
    availability = inputs['availability']
    season_era = inputs['season_era']
    clean_trust_count = len(inputs['clean_trust_options'])
    clean_option_count = len(inputs['clean_options'])
    high_risk_count = inputs['high_risk_arms']
    candidates = []

    per_arm = _number(workload.get('per_arm_pitches'))
    top_share = _number(workload.get('top_share'))
    participant_count = int(workload.get('participant_count') or 0)
    available_share = _number(availability.get('available_share'))
    available_count = int(availability.get('available') or 0)
    era_rank = _rank(season_era.get('rank'))

    cluster_per_arm = [_number(item['inputs']['workload'].get('per_arm_pitches')) for item in cluster]
    cluster_top_share = [_number(item['inputs']['workload'].get('top_share')) for item in cluster]
    cluster_participants = [int(item['inputs']['workload'].get('participant_count') or 0) for item in cluster]
    cluster_available_share = [_number(item['inputs']['availability'].get('available_share')) for item in cluster]
    cluster_available_count = [int(item['inputs']['availability'].get('available') or 0) for item in cluster]
    cluster_clean_trust = [len(item['inputs']['clean_trust_options']) for item in cluster]
    cluster_era_ranks = [_rank(item['inputs']['season_era'].get('rank')) for item in cluster]
    cluster_high_risk = [item['inputs']['high_risk_arms'] for item in cluster]

    if high_risk_count > 0:
        gap = _max_gap(high_risk_count, cluster_high_risk)
        candidates.append(_lead_candidate(
            LEAD_FATIGUE_LOAD,
            1000 + high_risk_count * 20 + gap * 30,
            high_risk_count,
            'highest HIGH/CRITICAL fatigue count in the same-rule cluster',
            'max',
        ))

    if clean_trust_count == 0 and (len(cluster) == 1 or max(cluster_clean_trust) > 0):
        candidates.append(_lead_candidate(
            LEAD_TRUST_LANE_ABSENCE,
            900 + max(cluster_clean_trust) * 10,
            clean_trust_count,
            'no clean trusted late-inning path while same-rule peers have one',
            'min',
        ))

    positive_trust = [value for value in cluster_clean_trust if value > 0]
    if clean_trust_count == 1 and (len(positive_trust) == 1 or max(positive_trust) > 1):
        candidates.append(_lead_candidate(
            LEAD_TRUST_LANE_SHALLOW,
            760 + max(positive_trust or [1]) * 5,
            clean_trust_count,
            'only one clean trusted late-inning path',
            'min_positive',
        ))

    high_workload_gap = _max_gap(per_arm, cluster_per_arm)
    if (
        (len(cluster) == 1 and per_arm >= HEAVY_PER_ARM_PITCHES_MIN)
        or high_workload_gap >= LEAD_WORKLOAD_SIMILAR_PITCHES
    ):
        candidates.append(_lead_candidate(
            LEAD_WORKLOAD_HIGH,
            720 + max(0, per_arm - HEAVY_PER_ARM_PITCHES_MIN) + high_workload_gap,
            per_arm,
            'highest or heavy recent workload in the same-rule cluster',
            'max',
        ))

    low_workload_gap = _min_gap(per_arm, cluster_per_arm)
    if (
        rule_key == RULE_PRESSURE_DISTRIBUTION
        and (len(cluster) == 1 or low_workload_gap >= LEAD_WORKLOAD_SIMILAR_PITCHES)
    ):
        candidates.append(_lead_candidate(
            LEAD_WORKLOAD_LIGHT,
            710 + max(0, LIGHT_PER_ARM_PITCHES_MAX - per_arm) + low_workload_gap,
            per_arm,
            'lightest recent workload in the same-rule cluster',
            'min',
        ))

    low_availability_gap = _min_gap(available_share, cluster_available_share)
    if (
        availability['total'] > 0
        and (
            inputs['conditions'].get('availability_thin')
            or low_availability_gap >= LEAD_AVAILABILITY_SIMILAR_SHARE
            or _min_gap(available_count, cluster_available_count) >= 2
        )
    ):
        candidates.append(_lead_candidate(
            LEAD_AVAILABILITY_THIN,
            680 + low_availability_gap * 100 + max(0, THIN_AVAILABLE_COUNT_MAX - available_count) * 10,
            available_share,
            'thinnest availability or a thin-availability gate',
            'min',
        ))

    high_availability_gap = _max_gap(available_share, cluster_available_share)
    if availability['total'] > 0 and (high_availability_gap >= LEAD_AVAILABILITY_SIMILAR_SHARE or available_share >= 0.85):
        candidates.append(_lead_candidate(
            LEAD_AVAILABILITY_DEEP,
            660 + high_availability_gap * 100 + max(0, clean_option_count - available_count),
            available_share,
            'deepest availability in the same-rule cluster',
            'max',
        ))

    if available_share >= 0.70 and clean_trust_count > 0 and clean_option_count >= max(1, available_count - 1):
        candidates.append(_lead_candidate(
            LEAD_DEEP_INTACT,
            650 + available_share * 20 + clean_trust_count * 4,
            (available_share, clean_trust_count),
            'deep availability with a clean trusted late-inning path',
            'max',
        ))

    concentration_gap = _max_gap(top_share, cluster_top_share)
    if workload.get('concentration_level') != 'none' or concentration_gap >= LEAD_CONCENTRATION_SIMILAR_SHARE:
        candidates.append(_lead_candidate(
            LEAD_CONCENTRATION_SHAPE,
            620 + top_share * 100 + concentration_gap * 100,
            top_share,
            'most concentrated workload shape in the same-rule cluster',
            'max',
        ))

    participant_low_gap = _min_gap(participant_count, cluster_participants)
    if participant_low_gap >= 1:
        candidates.append(_lead_candidate(
            LEAD_PARTICIPATION_NARROW,
            590 + participant_low_gap * 20,
            participant_count,
            'narrowest participation breadth in the same-rule cluster',
            'min',
        ))

    participant_high_gap = _max_gap(participant_count, cluster_participants)
    if participant_high_gap >= 1:
        candidates.append(_lead_candidate(
            LEAD_PARTICIPATION_BROAD,
            580 + participant_high_gap * 20,
            participant_count,
            'broadest participation breadth in the same-rule cluster',
            'max',
        ))

    best_rank_gap = _min_gap(era_rank, cluster_era_ranks)
    if season_era.get('available') and (era_rank <= 3 or best_rank_gap >= LEAD_ERA_SIMILAR_RANKS):
        candidates.append(_lead_candidate(
            LEAD_ERA_ELITE,
            560 + max(0, STRONG_SEASON_ERA_TOP_BULLPENS - era_rank + 1) + best_rank_gap,
            era_rank,
            'best or elite current-pen ERA rank in the same-rule cluster',
            'min',
        ))

    worst_rank_gap = _max_gap(era_rank, cluster_era_ranks)
    if season_era.get('available') and (era_rank > STRONG_SEASON_ERA_TOP_BULLPENS or worst_rank_gap >= LEAD_ERA_SIMILAR_RANKS):
        candidates.append(_lead_candidate(
            LEAD_ERA_ORDINARY,
            540 + max(0, era_rank - STRONG_SEASON_ERA_TOP_BULLPENS) + worst_rank_gap,
            era_rank,
            'least elite current-pen ERA rank in the same-rule cluster',
            'max',
        ))

    trust_depth_gap = _max_gap(clean_trust_count, cluster_clean_trust)
    if clean_trust_count >= 2 and trust_depth_gap >= 1:
        candidates.append(_lead_candidate(
            LEAD_TRUST_LANE_DEPTH,
            520 + clean_trust_count * 6 + trust_depth_gap * 10,
            clean_trust_count,
            'deepest clean trusted late-inning path in the same-rule cluster',
            'max',
        ))

    return sorted(
        candidates,
        key=lambda candidate: (-candidate['score'], candidate['tie_break_order'], str(candidate['dimension'])),
    )


def _lead_values_similar(first, second):
    if first['dimension'] != second['dimension']:
        return False
    dimension = first['dimension']
    first_value = first.get('value')
    second_value = second.get('value')
    if dimension in {LEAD_FATIGUE_LOAD, LEAD_TRUST_LANE_ABSENCE, LEAD_TRUST_LANE_SHALLOW, LEAD_TRUST_LANE_DEPTH}:
        return first_value == second_value
    if dimension in {LEAD_WORKLOAD_HIGH, LEAD_WORKLOAD_LIGHT}:
        return abs(_number(first_value) - _number(second_value)) <= LEAD_WORKLOAD_SIMILAR_PITCHES
    if dimension in {LEAD_AVAILABILITY_THIN, LEAD_AVAILABILITY_DEEP}:
        return abs(_number(first_value) - _number(second_value)) <= LEAD_AVAILABILITY_SIMILAR_SHARE
    if dimension == LEAD_DEEP_INTACT:
        first_share, first_trust = first_value
        second_share, second_trust = second_value
        return (
            abs(_number(first_share) - _number(second_share)) <= LEAD_AVAILABILITY_SIMILAR_SHARE
            and first_trust == second_trust
        )
    if dimension == LEAD_CONCENTRATION_SHAPE:
        return abs(_number(first_value) - _number(second_value)) <= LEAD_CONCENTRATION_SIMILAR_SHARE
    if dimension in {LEAD_PARTICIPATION_NARROW, LEAD_PARTICIPATION_BROAD}:
        return abs(int(first_value or 0) - int(second_value or 0)) <= 1
    if dimension in {LEAD_ERA_ELITE, LEAD_ERA_ORDINARY}:
        return abs(_rank(first_value) - _rank(second_value)) <= LEAD_ERA_SIMILAR_RANKS
    return first_value == second_value


def _lead_signal_text(record, lead):
    if not lead:
        return None
    skeleton = (LEAD_FRAGMENT_LIBRARY.get(lead.get('dimension')) or {}).get(BEAT_SIGNAL)
    if not skeleton:
        return None
    return _fill_skeleton(skeleton, _base_slots(record['inputs']))


def _lead_fragment_signature(record, lead):
    text = _lead_signal_text(record, lead)
    if not text:
        return None
    team = (record.get('story') or {}).get('team_name') or ''
    normalized = text
    if team:
        normalized = normalized.replace(team, '{team_name}')
    return (
        lead.get('dimension'),
        ' '.join(normalized.split()).lower(),
    )


def _lead_collides(record, lead, assigned_records):
    signature = _lead_fragment_signature(record, lead)
    if signature is None:
        return False
    return any(
        signature == _lead_fragment_signature(existing_record, existing_lead)
        for existing_record, existing_lead in assigned_records
    )


def _cluster_lead_dimensions(story_records):
    by_rule = {}
    for record in story_records:
        story = record.get('story') or {}
        by_rule.setdefault(story.get('rule_key'), []).append(record)

    selected = {}
    candidates_by_team = {}
    for _rule_key, cluster in by_rule.items():
        cluster_candidates = {}
        for record in cluster:
            key = _team_story_key(record)
            candidates = _team_lead_candidates(record, cluster)
            cluster_candidates[key] = candidates
            candidates_by_team[key] = candidates
        order = sorted(
            cluster,
            key=lambda record: (
                -(cluster_candidates[_team_story_key(record)][0]['score']
                  if cluster_candidates[_team_story_key(record)]
                  else 0),
                record['story'].get('team_name') or '',
                record['story'].get('team_id') or 0,
            ),
        )
        assigned = []
        for record in order:
            key = _team_story_key(record)
            candidates = cluster_candidates.get(key) or []
            choice = None
            for candidate in candidates:
                if not any(_lead_values_similar(candidate, existing) for existing in assigned):
                    choice = candidate
                    break
            if choice is None and candidates:
                choice = {**candidates[0], 'honest_sameness': True}
            if choice is not None:
                selected[key] = choice
                assigned.append(choice)
    return selected, candidates_by_team


def _resolve_feed_wide_lead_collisions(story_records, selected, candidates_by_team):
    resolved = {}
    assigned = []
    for record in sorted(story_records, key=_story_feed_order_key):
        key = _team_story_key(record)
        candidates = candidates_by_team.get(key) or []
        cluster_choice = selected.get(key)
        if cluster_choice is None:
            continue

        if not _lead_collides(record, cluster_choice, assigned):
            resolved[key] = cluster_choice
            assigned.append((record, cluster_choice))
            continue

        if cluster_choice.get('honest_sameness'):
            honest_choice = {
                **cluster_choice,
                'feed_wide_honest_sameness': True,
                'feed_wide_collision_unresolved': True,
            }
            resolved[key] = honest_choice
            assigned.append((record, honest_choice))
            continue

        replacement = None
        for candidate in candidates:
            if candidate.get('dimension') == cluster_choice.get('dimension'):
                continue
            if not _lead_collides(record, candidate, assigned):
                replacement = {
                    **candidate,
                    'feed_wide_replacement_for': cluster_choice.get('dimension'),
                    'feed_wide_replacement_reason': (
                        'resolved a feed-wide lead-fragment collision on a grounded secondary dimension'
                    ),
                }
                break

        if replacement is None:
            replacement = {
                **cluster_choice,
                'honest_sameness': True,
                'feed_wide_honest_sameness': True,
                'feed_wide_collision_unresolved': True,
            }

        resolved[key] = replacement
        assigned.append((record, replacement))
    return resolved


def select_lead_dimensions(story_records):
    selected, candidates_by_team = _cluster_lead_dimensions(story_records)
    return _resolve_feed_wide_lead_collisions(story_records, selected, candidates_by_team)


def _lead_beat(rule_key, beat_key, lead, slots):
    if not lead:
        return None
    skeleton = (LEAD_FRAGMENT_LIBRARY.get(lead.get('dimension')) or {}).get(beat_key)
    if not skeleton:
        return None
    text = _fill_skeleton(skeleton, slots)
    if not text:
        return None
    skeleton_key = lead['signal_skeleton_key'] if beat_key == BEAT_SIGNAL else lead['evidence_skeleton_key']
    return {
        'key': beat_key,
        'label': beat_key.capitalize(),
        'text': text,
        'skeleton_key': skeleton_key,
        'lead_dimension': lead.get('dimension'),
        'slots': {
            key: slots[key]
            for key in sorted(slots)
            if key in skeleton
        },
    }


def assemble_story(rule_key, inputs, lead=None):
    rule = RULES[rule_key]
    slots = _base_slots(inputs)
    beats = []
    for beat_key in (BEAT_SIGNAL,):
        beat = _lead_beat(rule_key, beat_key, lead, slots) or _beat(rule_key, beat_key, beat_key, slots)
        if beat:
            beats.append(beat)
    if _evidence_notable(rule_key, inputs):
        beat = (
            _lead_beat(rule_key, BEAT_EVIDENCE, lead, slots)
            or _beat(rule_key, BEAT_EVIDENCE, _evidence_skeleton_key(rule_key, inputs), slots)
        )
        if beat:
            beats.append(beat)
    if _rule_conditions_hold(rule_key, inputs):
        beat = _why_context_beat(rule_key, inputs)
        if beat:
            beats.append(beat)
        beat = _beat(rule_key, BEAT_MECHANISM, BEAT_MECHANISM, slots)
        if beat:
            beats.append(beat)
        implication_key = (
            'implication_with_clean_trust'
            if slots['clean_trust_count'] > 0
            else 'implication_without_clean_trust'
        )
        beat = _beat(rule_key, BEAT_IMPLICATION, implication_key, slots)
        if beat:
            beats.append(beat)

    beat_keys = {beat['key'] for beat in beats}
    if not ({BEAT_MECHANISM, BEAT_IMPLICATION} & beat_keys):
        return None
    signal = next((beat for beat in beats if beat['key'] == BEAT_SIGNAL), None)
    body = ' '.join(
        beat['text'] for beat in beats
        if beat['key'] in {BEAT_EVIDENCE, BEAT_CONTEXT, BEAT_MECHANISM, BEAT_IMPLICATION}
    )
    team = inputs['team']
    why_context = next((beat for beat in beats if beat['key'] == BEAT_CONTEXT), None)
    why_context_meta = {
        'applied': bool(why_context),
        'sources': (why_context or {}).get('sources') or [],
        'context_flags': (why_context or {}).get('context_flags') or [],
        'source_limitations_present': bool((why_context or {}).get('source_limitations_present')),
    }
    story_facts = build_story_facts(rule_key, inputs, beats, lead=lead)
    story_context_meta = story_facts.get('bullpen_context_integration') or {}
    story_identity_meta = story_facts.get('story_identity_integration') or {}
    narrative = render_story_narrative(story_facts)
    story = {
        'story_id': f"{team.get('team_id')}:{rule_key}",
        'rule_key': rule_key,
        'rule_label': rule['label'],
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
        'kicker': rule['label'],
        'tone': rule['tone'],
        'category': rule['category'],
        'title': signal['text'] if signal else rule['label'],
        'body': body,
        'narrative': narrative,
        'story_facts': story_facts,
        'beats': beats,
        'strength': _strength(rule_key, inputs),
        'href': _story_href(team),
        'cta': 'Open the team board',
        'source': 'backend',
        'lead_dimension': lead.get('dimension') if lead else None,
        'lead_dimension_detail': lead,
        'lead_fields': {
            'high_risk_arm_count': inputs['high_risk_arms'],
            'high_risk_arm_names': [
                item['name'] for item in inputs.get('high_risk_arm_options') or []
                if item.get('name')
            ],
            'clean_trust_count': len(inputs['clean_trust_options']),
            'clean_trust_names': [
                item['name'] for item in inputs['clean_trust_options']
                if item.get('name')
            ],
        },
        'slot_sources': {
            'workload': 'game_logs.relief_pitches',
            'availability': 'current_availability_records',
            'season_era': 'season_era.bullpens',
            'capacity_intelligence': 'bullpen_capacity_intelligence_v1',
            'bullpen_identity': 'bullpen_identity_v1',
            'story_identity_integration': 'bullpen_identity_v1',
            'rotation_support_pressure': 'rotation_support_pressure_v1',
            'bullpen_stability': 'bullpen_stability_v1',
            'bullpen_environment': 'bullpen_environment_v1',
            'why_context': 'backend_bullpen_intelligence_context',
            'clean_options': 'governed_board_pitcher_labels',
            'high_risk_arms': 'current_availability_records.fatigue_score',
        },
        'computed': {
            'conditions': inputs['conditions'],
            'why_context': why_context_meta,
            'workload': {
                key: value
                for key, value in inputs['workload'].items()
                if key != 'pitch_by_pitcher'
            },
            'availability': {
                'available': inputs['availability']['available'],
                'available_share': round(inputs['availability']['available_share'], 3),
                'total': inputs['availability']['total'],
            },
            'season_era': {
                'available': inputs['season_era']['available'],
                'era': inputs['season_era']['era'],
                'rank': inputs['season_era']['rank'],
                'rank_total': inputs['season_era']['rank_total'],
                'strong_results': inputs['season_era']['strong_results'],
                'solid_results': inputs['season_era']['solid_results'],
            },
            'capacity_intelligence': inputs.get('capacity_intelligence') or {},
            'bullpen_identity': (inputs.get('capacity_intelligence') or {}).get('bullpen_identity') or {},
            'rotation_support_pressure': inputs.get('rotation_support_pressure') or {},
            'bullpen_stability': inputs.get('bullpen_stability') or {},
            'bullpen_environment': inputs.get('bullpen_environment') or {},
            'story_context_integration': story_context_meta,
            'story_identity_integration': story_identity_meta,
            'high_risk_arms': inputs['high_risk_arms'],
            'high_risk_arm_count': inputs['high_risk_arms'],
            'high_risk_arm_names': [
                item['name'] for item in inputs.get('high_risk_arm_options') or []
                if item.get('name')
            ],
            'roster_unavailable_arms': inputs['roster_unavailable_arms'],
            'clean_trust_count': len(inputs['clean_trust_options']),
            'clean_trust_names': [
                item['name'] for item in inputs['clean_trust_options']
                if item.get('name')
            ],
            'clean_option_count': len(inputs['clean_options']),
        },
    }
    if story_facts.get('disclosure'):
        disclosure_note = render_story_disclosure_note(story_facts)
        if disclosure_note:
            story['disclosure_note'] = disclosure_note
    return story


def evaluate_team_rules(team_inputs):
    inputs = compute_team_story_inputs(team_inputs)
    conditions = inputs['conditions']
    evaluations = []

    live_checks = {
        RULE_STRESS_TRANSFER: {
            'can_fire': conditions['workload_concentrated'] and conditions['availability_thin'],
            'conditions': {
                'workload_concentrated': conditions['workload_concentrated'],
                'availability_thin': conditions['availability_thin'],
            },
        },
        RULE_PRESSURE_DISTRIBUTION: {
            'can_fire': conditions['workload_light'] and conditions['broad_participation'],
            'conditions': {
                'workload_light': conditions['workload_light'],
                'broad_participation': conditions['broad_participation'],
            },
        },
        RULE_SUSTAINABILITY_QUESTION: {
            'can_fire': conditions['season_era_strong'] and conditions['heavy_recent_workload'],
            'conditions': {
                'season_era_strong': conditions['season_era_strong'],
                'heavy_recent_workload': conditions['heavy_recent_workload'],
            },
        },
        RULE_HIDDEN_CAPACITY_LOSS: {
            'can_fire': conditions['season_era_solid'] and conditions['depleted_depth'],
            'conditions': {
                'season_era_solid': conditions['season_era_solid'],
                'depleted_depth': conditions['depleted_depth'],
            },
        },
    }
    for rule_key, check in live_checks.items():
        story = assemble_story(rule_key, inputs) if check['can_fire'] else None
        evaluations.append({
            'rule_key': rule_key,
            'rule_label': RULES[rule_key]['label'],
            'status': 'live',
            'can_fire': check['can_fire'],
            'conditions': check['conditions'],
            'story': story,
        })

    for rule_key in (RULE_SPECIAL_SITUATION,):
        rule = RULES[rule_key]
        evaluations.append({
            'rule_key': rule_key,
            'rule_label': rule['label'],
            'status': 'dormant',
            'can_fire': False,
            'reason': 'missing_input',
            'missing_inputs': list(rule['missing_inputs']),
            'story': None,
        })

    return {
        'team': inputs['team'],
        'inputs': inputs,
        'evaluations': evaluations,
    }


def _team_inputs_from_records(
    availability_records,
    logs_by_pitcher,
    reference_date,
    season_era=None,
    capacity_by_team=None,
    rotation_support_by_team=None,
    bullpen_stability_by_team=None,
    bullpen_environment_by_team=None,
):
    season_era_by_team = _ranked_era_by_team(season_era)
    by_team = {}
    for record in availability_records or []:
        key = _team_key(record)
        if key is None:
            continue
        bucket = by_team.setdefault(key, {
            'team': _team_identity(record),
            'records': [],
        })
        bucket['records'].append(record)

    return [
        TeamInputs(
            team=bucket['team'],
            records=bucket['records'],
            logs_by_pitcher=logs_by_pitcher or {},
            reference_date=reference_date,
            season_era_by_team=season_era_by_team,
            capacity_by_team=capacity_by_team or {},
            rotation_support_by_team=rotation_support_by_team or {},
            bullpen_stability_by_team=bullpen_stability_by_team or {},
            bullpen_environment_by_team=bullpen_environment_by_team or {},
        )
        for bucket in by_team.values()
    ]


def build_four_beat_story_feed(
    availability_records,
    logs_by_pitcher,
    reference_date=None,
    freshness=None,
    season_era=None,
    capacity_by_team=None,
    rotation_support_by_team=None,
    bullpen_stability_by_team=None,
    bullpen_environment_by_team=None,
):
    team_inputs = _team_inputs_from_records(
        availability_records,
        logs_by_pitcher,
        reference_date,
        season_era=season_era,
        capacity_by_team=capacity_by_team,
        rotation_support_by_team=rotation_support_by_team,
        bullpen_stability_by_team=bullpen_stability_by_team,
        bullpen_environment_by_team=bullpen_environment_by_team,
    )
    evaluations = [evaluate_team_rules(team) for team in team_inputs]
    story_records = []
    for team_eval in evaluations:
        team_story_records = [
            {
                'story': evaluation['story'],
                'inputs': team_eval['inputs'],
            }
            for evaluation in team_eval['evaluations']
            if evaluation.get('story') is not None
        ]
        if not team_story_records:
            continue
        team_story_records.sort(key=lambda item: (
            -item['story']['strength'],
            item['story']['team_name'] or '',
            item['story']['rule_key'],
        ))
        story_records.append(team_story_records[0])

    selected_leads = select_lead_dimensions(story_records)
    stories = []
    for record in story_records:
        story = record['story']
        lead = selected_leads.get((story.get('team_id'), story.get('rule_key')))
        stories.append(assemble_story(story['rule_key'], record['inputs'], lead=lead))
    stories.sort(key=lambda story: (-story['strength'], story['team_name'] or '', story['rule_key']))

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'enabled': True,
        'source': 'backend',
        'feed_ordering_applied': True,
        'feed_ordering_basis': 'story_strength',
        'selection_made': False,
        'reference_date': reference_date.isoformat() if reference_date else None,
        'freshness': freshness or {},
        'thresholds': THRESHOLDS,
        'rules': {
            'live': [
                RULES[RULE_STRESS_TRANSFER],
                RULES[RULE_SUSTAINABILITY_QUESTION],
                RULES[RULE_HIDDEN_CAPACITY_LOSS],
                RULES[RULE_PRESSURE_DISTRIBUTION],
            ],
            'dormant': [
                RULES[RULE_SPECIAL_SITUATION],
            ],
        },
        'items': stories,
        'count': len(stories),
        'suppressed_count': max(len(team_inputs) - len({story['team_id'] for story in stories}), 0),
        'evaluations': [
            {
                'team': team_eval['team'],
                'rules': [
                    {
                        key: value
                        for key, value in evaluation.items()
                        if key != 'story'
                    }
                    for evaluation in team_eval['evaluations']
                ],
            }
            for team_eval in evaluations
        ],
    }


__all__ = [
    'CAPABILITY',
    'BEAT_CONTEXT',
    'FEATURE_FLAG',
    'RULE_HIDDEN_CAPACITY_LOSS',
    'RULE_PRESSURE_DISTRIBUTION',
    'RULE_SPECIAL_SITUATION',
    'RULE_STRESS_TRANSFER',
    'RULE_SUSTAINABILITY_QUESTION',
    'TeamInputs',
    'assemble_story',
    'build_four_beat_story_feed',
    'compute_team_story_inputs',
    'evaluate_team_rules',
    'four_beat_stories_enabled',
    'select_lead_dimensions',
]
