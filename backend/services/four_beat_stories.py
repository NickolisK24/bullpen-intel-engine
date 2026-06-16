"""Backend-authored four-beat bullpen stories.

This service is fill-only: it selects deterministic rules and fills fixed
sentence skeletons with computed slots. Unsupported slots suppress the beat.
"""

from __future__ import annotations

import os
import string
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from services.availability import (
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
)
from services.bullpen_context import BULLPEN_CONTEXT_WINDOW_DAYS
from services.pitcher_role_authority import author_role_read_labels
from utils.games_started import is_relief


CAPABILITY = 'four_beat_story_template_v1'
VERSION = '2026-06-16.live_rules'
FEATURE_FLAG = 'FOUR_BEAT_STORIES_ENABLED'

RULE_STRESS_TRANSFER = 'stress_transfer'
RULE_PRESSURE_DISTRIBUTION = 'pressure_distribution'
RULE_SUSTAINABILITY_QUESTION = 'sustainability_question'
RULE_HIDDEN_CAPACITY_LOSS = 'hidden_capacity_loss'
RULE_SPECIAL_SITUATION = 'special_situation'

BEAT_SIGNAL = 'signal'
BEAT_EVIDENCE = 'evidence'
BEAT_MECHANISM = 'mechanism'
BEAT_IMPLICATION = 'implication'

# Reasoned judgment defaults, not validated thresholds. They are intentionally
# centralized so a future tuning pass can change them without hunting literals.
RECENT_WORKLOAD_WINDOW_DAYS = BULLPEN_CONTEXT_WINDOW_DAYS
CONCENTRATED_TOP_ARM_COUNT = 3
CONCENTRATED_TOP_SHARE_MIN = 0.62
CONCENTRATION_DESCRIPTOR_MODERATE_MIN = CONCENTRATED_TOP_SHARE_MIN
CONCENTRATION_DESCRIPTOR_CONCENTRATED_MIN = 0.70
CONCENTRATION_DESCRIPTOR_SEVERE_MIN = 0.80
CONCENTRATION_DESCRIPTOR_MODERATE = 'some concentration'
CONCENTRATION_DESCRIPTOR_CONCENTRATED = 'a concentrated workload'
CONCENTRATION_DESCRIPTOR_SEVERE = 'a heavily concentrated workload'
CONCENTRATION_DESCRIPTOR_NONE = 'no concentration'
THIN_AVAILABLE_COUNT_MAX = 3
THIN_AVAILABLE_SHARE_MAX = 0.30
LIGHT_HIGH_RISK_LEVELS = {'HIGH', 'CRITICAL'}
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
        BEAT_SIGNAL: 'The {team_name} are transferring bullpen pressure onto a smaller group tonight.',
        BEAT_EVIDENCE: 'The top {top_arm_count} arms show {concentration_descriptor}, carrying {top_share_pct}% of recent relief pitches, while {available_count} of {total_bullpen_arms} bullpen arms are Available.',
        BEAT_MECHANISM: 'That combination usually means the next close innings lean harder on the remaining clean late-inning path.',
        'implication_with_clean_trust': 'Tonight, {clean_trust_names} {clean_trust_verb} the clean Trust Arm path; {clean_option_count} of {total_bullpen_arms} bullpen arms are clean options behind it.',
        'implication_without_clean_trust': 'Tonight, no Trust Arm is a clean option; {clean_option_count} of {total_bullpen_arms} bullpen arms are clean options outside that lane.',
    },
    RULE_PRESSURE_DISTRIBUTION: {
        BEAT_SIGNAL: 'The {team_name} have pressure spread across the pen tonight.',
        BEAT_EVIDENCE: '{participant_count} arms shared the last {window_days} days of relief work, with {per_arm_pitches} pitches per participating arm.',
        BEAT_MECHANISM: 'When recent work is light and spread out, the pen tends to have more room to maneuver tonight.',
        'implication_with_clean_trust': 'Tonight, {clean_trust_names} {clean_trust_verb} the clean Trust Arm path, and {clean_option_count} of {total_bullpen_arms} bullpen arms are clean options.',
        'implication_without_clean_trust': 'Tonight, the clean options are outside the Trust Arm lane; {clean_option_count} of {total_bullpen_arms} bullpen arms are clean options.',
    },
    RULE_SUSTAINABILITY_QUESTION: {
        BEAT_SIGNAL: 'The {team_name} bullpen has pitched well this year, but they are leaning on it hard tonight.',
        'evidence_with_high_risk': 'Their current bullpen group owns a {season_era} season ERA, {era_rank_ordinal} among the bullpens teams are carrying right now, while recent workload sits at {per_arm_pitches} pitches per participating arm with {high_risk_arm_count} {high_risk_arm_word} at HIGH or CRITICAL fatigue.',
        'evidence_without_high_risk': 'Their current bullpen group owns a {season_era} season ERA, {era_rank_ordinal} among the bullpens teams are carrying right now, while recent workload sits at {per_arm_pitches} pitches per participating arm over the last {window_days} days.',
        BEAT_MECHANISM: 'That does not say the results are changing; it does make tonight\'s clean innings feel more expensive to spend.',
        'implication_with_clean_trust': 'Tonight, {clean_trust_names} {clean_trust_verb} still the clean Trust Arm path, so the watch is how early that lane has to open.',
        'implication_without_clean_trust': 'Tonight, there is no clean Trust Arm path; the watch is whether {clean_option_count} clean options can cover leverage without stretching the same group.',
    },
    RULE_HIDDEN_CAPACITY_LOSS: {
        BEAT_SIGNAL: 'The {team_name} results are solid, but the usable depth underneath them is thin tonight.',
        'evidence_with_roster_gap': 'Their current bullpen group is carrying a {season_era} season ERA, {era_rank_ordinal} among the bullpens teams are carrying right now, with {available_count} of {total_bullpen_arms} arms Available and {roster_unavailable_count} {roster_unavailable_word} off the active lane.',
        'evidence_without_roster_gap': 'Their current bullpen group is carrying a {season_era} season ERA, {era_rank_ordinal} among the bullpens teams are carrying right now, with {available_count} of {total_bullpen_arms} arms Available tonight.',
        BEAT_MECHANISM: 'That does not make the results false; it means there is less margin behind them if tonight turns into a bullpen game.',
        'implication_with_clean_trust': 'Tonight, {clean_trust_names} {clean_trust_verb} the clean Trust Arm path, but the depth behind that lane is the watch point.',
        'implication_without_clean_trust': 'Tonight, the clean options are outside the Trust Arm lane; the depth behind those options is the watch point.',
    },
}


@dataclass(frozen=True)
class TeamInputs:
    team: dict[str, Any]
    records: list[dict[str, Any]]
    logs_by_pitcher: dict[int, list[Any]]
    reference_date: Any
    season_era_by_team: dict[int, dict[str, Any]] | None = None


def _truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def four_beat_stories_enabled(config=None):
    if config is not None:
        return _truthy(config.get(FEATURE_FLAG, False))
    return _truthy(os.environ.get(FEATURE_FLAG))


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


def _concentration_descriptor(top_share):
    share = float(top_share or 0)
    if share >= CONCENTRATION_DESCRIPTOR_SEVERE_MIN:
        return {
            'level': 'severe',
            'descriptor': CONCENTRATION_DESCRIPTOR_SEVERE,
        }
    if share >= CONCENTRATION_DESCRIPTOR_CONCENTRATED_MIN:
        return {
            'level': 'concentrated',
            'descriptor': CONCENTRATION_DESCRIPTOR_CONCENTRATED,
        }
    if share >= CONCENTRATION_DESCRIPTOR_MODERATE_MIN:
        return {
            'level': 'moderate',
            'descriptor': CONCENTRATION_DESCRIPTOR_MODERATE,
        }
    return {
        'level': 'none',
        'descriptor': CONCENTRATION_DESCRIPTOR_NONE,
    }


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


def _recent_relief_logs(team_inputs):
    ref = team_inputs.reference_date
    if ref is None:
        return []
    start = ref - timedelta(days=RECENT_WORKLOAD_WINDOW_DAYS - 1)
    logs = []
    pitcher_ids = {
        _value(record.get('pitcher'), 'id')
        for record in team_inputs.records
        if _value(record.get('pitcher'), 'id') is not None
    }
    for pitcher_id in pitcher_ids:
        for log in team_inputs.logs_by_pitcher.get(pitcher_id, []) or []:
            game_date = _value(log, 'game_date')
            if game_date is None or game_date < start or game_date > ref:
                continue
            if is_relief(log):
                logs.append(log)
    return logs


def _workload_summary(team_inputs):
    pitch_by_pitcher = {}
    for log in _recent_relief_logs(team_inputs):
        pitcher_id = _value(log, 'pitcher_id')
        if pitcher_id is None:
            continue
        pitch_by_pitcher[pitcher_id] = pitch_by_pitcher.get(pitcher_id, 0) + int(_value(log, 'pitches_thrown', 0) or 0)

    totals = sorted(pitch_by_pitcher.values(), reverse=True)
    total_pitches = sum(totals)
    participant_count = len([value for value in totals if value > 0])
    top_total = sum(totals[:CONCENTRATED_TOP_ARM_COUNT])
    top_share = top_total / total_pitches if total_pitches > 0 else 0
    top_one_share = totals[0] / total_pitches if total_pitches > 0 and totals else 0
    per_arm = total_pitches / participant_count if participant_count else 0
    concentration = _concentration_descriptor(top_share)

    return {
        'pitch_by_pitcher': pitch_by_pitcher,
        'total_pitches': total_pitches,
        'participant_count': participant_count,
        'top_arm_count': min(CONCENTRATED_TOP_ARM_COUNT, participant_count),
        'top_pitch_total': top_total,
        'top_share': top_share,
        'top_one_share': top_one_share,
        'concentration_level': concentration['level'],
        'concentration_descriptor': concentration['descriptor'],
        'per_arm_pitches': per_arm,
    }


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


def _high_risk_count(records):
    count = 0
    for record in records:
        risk = str(_value(record.get('score'), 'risk_level') or '').upper()
        if risk in LIGHT_HIGH_RISK_LEVELS:
            count += 1
    return count


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
    clean, clean_trust = _clean_options(
        team_inputs.records,
        team_inputs.logs_by_pitcher,
        team_inputs.reference_date,
    )
    high_risk = _high_risk_count(team_inputs.records)
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
        'season_era': season_era,
        'clean_options': clean,
        'clean_trust_options': clean_trust,
        'high_risk_arms': high_risk,
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
    high_risk = inputs['high_risk_arms']
    roster_unavailable = inputs['roster_unavailable_arms']
    return {
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
        'team_id': team.get('team_id'),
        'window_days': RECENT_WORKLOAD_WINDOW_DAYS,
        'top_arm_count': workload['top_arm_count'],
        'top_share_pct': _pct(workload['top_share']),
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
        'roster_unavailable_count': roster_unavailable,
        'roster_unavailable_word': _plural(roster_unavailable, 'arm'),
        'clean_option_count': len(clean_options),
        'clean_trust_count': len(clean_trust),
        'clean_trust_names': clean_trust_names,
        'clean_trust_verb': 'is' if len(clean_trust) == 1 else 'are',
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


def assemble_story(rule_key, inputs):
    rule = RULES[rule_key]
    slots = _base_slots(inputs)
    beats = []
    for beat_key in (BEAT_SIGNAL,):
        beat = _beat(rule_key, beat_key, beat_key, slots)
        if beat:
            beats.append(beat)
    if _evidence_notable(rule_key, inputs):
        beat = _beat(rule_key, BEAT_EVIDENCE, _evidence_skeleton_key(rule_key, inputs), slots)
        if beat:
            beats.append(beat)
    if _rule_conditions_hold(rule_key, inputs):
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
        if beat['key'] in {BEAT_EVIDENCE, BEAT_MECHANISM, BEAT_IMPLICATION}
    )
    team = inputs['team']
    return {
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
        'beats': beats,
        'strength': _strength(rule_key, inputs),
        'href': _story_href(team),
        'cta': 'Open the team board',
        'source': 'backend',
        'slot_sources': {
            'workload': 'game_logs.relief_pitches',
            'availability': 'current_availability_records',
            'season_era': 'season_era.bullpens',
            'clean_options': 'governed_board_pitcher_labels',
        },
        'computed': {
            'conditions': inputs['conditions'],
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
            'high_risk_arms': inputs['high_risk_arms'],
            'roster_unavailable_arms': inputs['roster_unavailable_arms'],
            'clean_trust_count': len(inputs['clean_trust_options']),
            'clean_option_count': len(inputs['clean_options']),
        },
    }


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


def _team_inputs_from_records(availability_records, logs_by_pitcher, reference_date, season_era=None):
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
        )
        for bucket in by_team.values()
    ]


def build_four_beat_story_feed(
    availability_records,
    logs_by_pitcher,
    reference_date=None,
    freshness=None,
    season_era=None,
):
    team_inputs = _team_inputs_from_records(
        availability_records,
        logs_by_pitcher,
        reference_date,
        season_era=season_era,
    )
    evaluations = [evaluate_team_rules(team) for team in team_inputs]
    stories = []
    for team_eval in evaluations:
        team_stories = [
            evaluation['story']
            for evaluation in team_eval['evaluations']
            if evaluation.get('story') is not None
        ]
        if not team_stories:
            continue
        team_stories.sort(key=lambda story: (-story['strength'], story['team_name'] or '', story['rule_key']))
        stories.append(team_stories[0])
    stories.sort(key=lambda story: (-story['strength'], story['team_name'] or '', story['rule_key']))

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'enabled': True,
        'source': 'backend',
        'ranking_applied': True,
        'ranking_basis': 'story_strength',
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
]
