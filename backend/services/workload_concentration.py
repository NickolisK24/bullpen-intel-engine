"""Shared workload concentration read used by stories and team shape."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from services.baseline_distribution import build_metric_distributions, field_extractor
from services.bullpen_context import BULLPEN_CONTEXT_WINDOW_DAYS
from services.game_shape import bulk_follower_appearance_keys
from utils.games_started import is_relief


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


def _value(obj: Any, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _int_or_none(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def concentration_descriptor(top_share):
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


def summarize_workload_concentration(pitch_by_pitcher):
    pitch_totals = {}
    unknown_pitchers = set()
    for pitcher_id, pitches in (pitch_by_pitcher or {}).items():
        parsed = _int_or_none(pitches)
        if parsed is None:
            unknown_pitchers.add(pitcher_id)
            pitch_totals[pitcher_id] = None
            continue
        pitch_totals[pitcher_id] = parsed

    if unknown_pitchers:
        return {
            'pitch_by_pitcher': pitch_totals,
            'unknown_pitch_count': True,
            'unknown_pitch_count_pitchers': len(unknown_pitchers),
            'total_pitches': None,
            'participant_count': None,
            'top_arm_count': None,
            'top_pitch_total': None,
            'top_share': None,
            'top_one_share': None,
            'concentration_level': 'unknown',
            'concentration_descriptor': 'unknown workload concentration',
            'per_arm_pitches': None,
        }

    totals = sorted(pitch_totals.values(), reverse=True)
    total_pitches = sum(totals)
    participant_count = len([value for value in totals if value > 0])
    top_total = sum(totals[:CONCENTRATED_TOP_ARM_COUNT])
    top_share = top_total / total_pitches if total_pitches > 0 else 0
    top_one_share = totals[0] / total_pitches if total_pitches > 0 and totals else 0
    per_arm = total_pitches / participant_count if participant_count else 0
    concentration = concentration_descriptor(top_share)

    return {
        'pitch_by_pitcher': pitch_totals,
        'unknown_pitch_count': False,
        'unknown_pitch_count_pitchers': 0,
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


def recent_relief_pitch_totals(logs_by_pitcher, reference_date, pitcher_ids=None):
    if reference_date is None:
        return {}

    allowed = set(pitcher_ids or (logs_by_pitcher or {}).keys())
    start = reference_date - timedelta(days=RECENT_WORKLOAD_WINDOW_DAYS - 1)

    # Planned bulk-follower outings in opener/bulk games are separated from
    # ordinary bullpen concentration. Detection is game-shape-aware: it needs the
    # game's opener line to be present, so when only relief lines are visible no
    # appearance is discounted (conservative — ordinary long relief is never
    # mislabeled). The real workload still counts in fatigue and availability.
    window_logs = []
    for pitcher_id in allowed:
        for log in (logs_by_pitcher or {}).get(pitcher_id, []) or []:
            game_date = _value(log, 'game_date')
            if game_date is None or game_date < start or game_date > reference_date:
                continue
            window_logs.append(log)
    bulk_keys = bulk_follower_appearance_keys(window_logs)

    pitch_by_pitcher = {}
    for pitcher_id in allowed:
        for log in (logs_by_pitcher or {}).get(pitcher_id, []) or []:
            game_date = _value(log, 'game_date')
            if game_date is None or game_date < start or game_date > reference_date:
                continue
            if not is_relief(log):
                continue
            if (pitcher_id, _value(log, 'mlb_game_pk')) in bulk_keys:
                continue
            pitches = _int_or_none(_value(log, 'pitches_thrown'))
            if pitches is None:
                pitch_by_pitcher[pitcher_id] = None
                continue
            if pitcher_id in pitch_by_pitcher and pitch_by_pitcher[pitcher_id] is None:
                continue
            pitch_by_pitcher[pitcher_id] = (
                pitch_by_pitcher.get(pitcher_id, 0)
                + pitches
            )
    return pitch_by_pitcher


def summarize_recent_relief_workload(logs_by_pitcher, reference_date, pitcher_ids=None):
    return summarize_workload_concentration(
        recent_relief_pitch_totals(
            logs_by_pitcher,
            reference_date,
            pitcher_ids=pitcher_ids,
        )
    )


# ── League-wide baseline aggregation (Baseline Intelligence C1B) ──────────────

WORKLOAD_CONCENTRATION_BASELINE_FAMILY = 'workload_concentration'
WORKLOAD_CONCENTRATION_BASELINE_METRIC_KEYS = ('top_share', 'top_one_share')


def league_relief_workload_by_team(team_to_pitcher_ids, logs_by_pitcher, reference_date):
    """Recent relief workload concentration for every team that has relief workload.

    ``team_to_pitcher_ids`` maps team_id -> the team's bullpen pitcher ids. Returns
    one summary per team that actually threw relief pitches in the window. Teams
    with no relief workload are excluded: their concentration is undefined, not a
    real ``top_share`` of 0, so including them would bias a league distribution low.
    """
    summaries = []
    for team_id, pitcher_ids in (team_to_pitcher_ids or {}).items():
        if team_id is None:
            continue
        summary = summarize_recent_relief_workload(
            logs_by_pitcher,
            reference_date,
            pitcher_ids=pitcher_ids,
        )
        if summary.get('unknown_pitch_count'):
            continue
        if summary['total_pitches'] <= 0:
            continue
        summaries.append({
            'team_id': team_id,
            'top_share': summary['top_share'],
            'top_one_share': summary['top_one_share'],
            'total_pitches': summary['total_pitches'],
            'participant_count': summary['participant_count'],
        })
    return summaries


def build_workload_concentration_baselines(per_team_concentration):
    """League baseline distributions for the workload-concentration metrics.

    Returns a metric-family block (sample count, window, and a distribution per
    metric) suitable for registration in the baseline payload container. No
    interpretation and no per-team ranking — only the league distribution.
    """
    items = [item for item in (per_team_concentration or []) if isinstance(item, dict)]
    extractors = {
        key: field_extractor(key)
        for key in WORKLOAD_CONCENTRATION_BASELINE_METRIC_KEYS
    }
    return {
        'metric_family': WORKLOAD_CONCENTRATION_BASELINE_FAMILY,
        'window_days': RECENT_WORKLOAD_WINDOW_DAYS,
        'sample_count': len(items),
        'metrics': build_metric_distributions(items, extractors),
    }
