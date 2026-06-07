"""
Bullpen roster eligibility for bullpen-specific surfaces.

This module is intentionally separate from availability and observed-role
classification. Availability answers "what workload state is this pitcher in?"
Role classification describes recent usage. Eligibility answers whether a
pitcher belongs on a default bullpen surface at all.

The rule is conservative: explicit relief positions and recent relief-length
usage are included; clear starter patterns and inactive/non-pitcher records are
excluded from default bullpen counts.
"""

from datetime import date, timedelta

from services.availability import ACTIVE_WINDOW_DAYS


SAMPLE_SIZE = 10
MIN_REGULAR_SEASON_SAMPLE = 2
STARTER_IP_THRESHOLD = 3.0
RELIEF_IP_THRESHOLD = 2.0

STATUS_BULLPEN_RELEVANT = 'bullpen_relevant'
STATUS_INACTIVE_BULLPEN_RELEVANT = 'inactive_bullpen_relevant'
STATUS_CLEAR_STARTER = 'clear_starter'
STATUS_INACTIVE = 'inactive'
STATUS_NON_PITCHER = 'non_pitcher'
STATUS_NO_USAGE = 'no_current_bullpen_relevance'
STATUS_UNCERTAIN = 'uncertain_bullpen_relevance'

PITCHING_POSITIONS = {'P', 'SP', 'RP', 'CL', 'LHP', 'RHP'}
RELIEF_POSITIONS = {'RP', 'CL'}


def _position(pitcher):
    return str(getattr(pitcher, 'position', '') or '').strip().upper()


def _is_regular_season(log):
    return str(getattr(log, 'game_type', '') or '').upper() == 'R'


def _log_date(log):
    return getattr(log, 'game_date', None) or date.min


def _sorted_logs(logs):
    return sorted(list(logs or []), key=_log_date, reverse=True)


def _analysis_logs(logs):
    ordered = _sorted_logs(logs)
    regular = [log for log in ordered if _is_regular_season(log)]
    if len(regular) >= MIN_REGULAR_SEASON_SAMPLE:
        return regular[:SAMPLE_SIZE], 'regular-season'
    return ordered[:SAMPLE_SIZE], 'recent'


def _inning_values(logs):
    values = []
    for log in logs:
        value = getattr(log, 'innings_pitched', None)
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def _has_relief_context(logs):
    return any(
        bool(getattr(log, 'save', False))
        or bool(getattr(log, 'hold', False))
        for log in logs
    )


def _limited_result(status, reason, evidence=None, limitations=None, confidence='low'):
    return {
        'eligible': False,
        'status': status,
        'confidence': confidence,
        'reason': reason,
        'evidence': list(evidence or []),
        'limitations': list(limitations or []),
    }


def _eligible_result(status, reason, evidence=None, limitations=None, confidence='medium'):
    return {
        'eligible': True,
        'status': status,
        'confidence': confidence,
        'reason': reason,
        'evidence': list(evidence or []),
        'limitations': list(limitations or []),
    }


def _with_inactive_context(result, latest_game_date, reference_date):
    if not result.get('eligible') or latest_game_date is None:
        return result

    if latest_game_date >= reference_date - timedelta(days=ACTIVE_WINDOW_DAYS):
        return result

    updated = dict(result)
    updated['status'] = STATUS_INACTIVE_BULLPEN_RELEVANT
    updated['confidence'] = 'low'
    limitations = list(updated.get('limitations') or [])
    limitation = 'No game logs inside the active freshness window; shown only when stale/context pitchers are included.'
    if limitation not in limitations:
        limitations.append(limitation)
    updated['limitations'] = limitations
    return updated


def evaluate_bullpen_eligibility(pitcher, logs, reference_date=None, respect_local_active=True):
    """
    Determine whether a pitcher belongs on default bullpen-specific surfaces.

    Returns a serializable dict with an eligibility boolean plus explanation
    fields safe to expose in API payloads.
    """
    ref = reference_date or date.today()
    pos = _position(pitcher)
    active = bool(getattr(pitcher, 'active', True))

    if respect_local_active and not active:
        return _limited_result(
            STATUS_INACTIVE,
            'Pitcher is not marked active in the local roster model.',
        )

    if pos and pos not in PITCHING_POSITIONS:
        return _limited_result(
            STATUS_NON_PITCHER,
            f'Roster position {pos} is not a pitching position.',
        )

    sample, sample_label = _analysis_logs(logs)
    latest_game_date = max((_log_date(log) for log in sample), default=None)
    latest_game_date = None if latest_game_date == date.min else latest_game_date
    innings = _inning_values(sample)
    evidence = []

    if pos in RELIEF_POSITIONS:
        result = _eligible_result(
            STATUS_BULLPEN_RELEVANT,
            f'Roster position {pos} is bullpen-specific.',
            evidence=[f'Roster position: {pos}.'],
            confidence='high',
        )
        return _with_inactive_context(result, latest_game_date, ref)

    if not innings:
        return _limited_result(
            STATUS_NO_USAGE,
            'No usable pitching workload logs are available to infer bullpen relevance.',
            limitations=['Bullpen eligibility could not be inferred from recent workload data.'],
            confidence='none',
        )

    total = len(innings)
    start_like = sum(1 for value in innings if value >= STARTER_IP_THRESHOLD)
    relief_like = sum(1 for value in innings if value <= RELIEF_IP_THRESHOLD)
    avg_ip = sum(innings) / total
    latest_two = innings[:2]
    latest_three = innings[:3]
    latest_two_start_like = len(latest_two) == 2 and all(value >= STARTER_IP_THRESHOLD for value in latest_two)
    recent_relief_streak = len(latest_three) >= 2 and all(value <= RELIEF_IP_THRESHOLD for value in latest_three)
    relief_context = _has_relief_context(sample)

    evidence.extend([
        f'{total} {sample_label} pitching appearance(s) evaluated.',
        f'{start_like} start-length outing(s) at or above {STARTER_IP_THRESHOLD:.1f} IP.',
        f'{relief_like} relief-length outing(s) at or below {RELIEF_IP_THRESHOLD:.1f} IP.',
        f'Average sampled IP: {avg_ip:.1f}.',
    ])
    if relief_context:
        evidence.append('Save or hold evidence is present.')

    if relief_context:
        result = _eligible_result(
            STATUS_BULLPEN_RELEVANT,
            'Recent usage includes bullpen-specific save or hold context.',
            evidence=evidence,
            confidence='high',
        )
        return _with_inactive_context(result, latest_game_date, ref)

    # A recent relief streak can override older starter-length history, which
    # covers pitchers who have moved into a bullpen role.
    if recent_relief_streak and relief_like >= 3 and start_like <= 2:
        result = _eligible_result(
            STATUS_BULLPEN_RELEVANT,
            'Most recent usage is relief-length, so the pitcher remains bullpen-relevant.',
            evidence=evidence,
            confidence='high' if start_like == 0 else 'medium',
        )
        return _with_inactive_context(result, latest_game_date, ref)

    clear_starter = (
        pos == 'SP'
        or latest_two_start_like
        or (start_like >= 3 and start_like / total >= 0.5)
        or (start_like >= 2 and avg_ip >= STARTER_IP_THRESHOLD)
    )
    if clear_starter:
        return _limited_result(
            STATUS_CLEAR_STARTER,
            'Recent usage has a clear starter-length pattern.',
            evidence=evidence,
            limitations=['Clear starters are excluded from default bullpen availability counts.'],
            confidence='high',
        )

    strong_relief_pattern = (
        start_like == 0 and relief_like >= 2
    ) or (
        relief_like >= 3 and relief_like / total >= 0.70 and start_like <= 1
    )
    if strong_relief_pattern:
        result = _eligible_result(
            STATUS_BULLPEN_RELEVANT,
            'Recent usage is primarily relief-length.',
            evidence=evidence,
            confidence='high',
        )
        return _with_inactive_context(result, latest_game_date, ref)

    limited_relief_sample = start_like <= 1 and relief_like >= 1 and total <= 3
    if limited_relief_sample:
        result = _eligible_result(
            STATUS_BULLPEN_RELEVANT,
            'Bullpen relevance is inferred from a limited relief-length sample.',
            evidence=evidence,
            limitations=['Bullpen eligibility is inferred from limited recent relief-length usage.'],
            confidence='low',
        )
        return _with_inactive_context(result, latest_game_date, ref)

    return _limited_result(
        STATUS_UNCERTAIN,
        'Usage pattern does not provide enough bullpen-specific evidence.',
        evidence=evidence,
        limitations=['Uncertain bullpen eligibility is withheld from default bullpen counts.'],
        confidence='low',
    )
