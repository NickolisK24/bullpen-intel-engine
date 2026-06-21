"""Shared workload-appearance helpers.

Raw MLB game-log rows are preserved for audit/detail views, but BaseballOS
workload calculations require evidence of actual pitching work. Rows with
0 IP and 0 pitches can come through the public feeds as boxscore/game-log
artifacts and should not read as normal workload appearances.
"""


def _value(log, name, default=None):
    if isinstance(log, dict):
        return log.get(name, default)
    return getattr(log, name, default)


def workload_pitch_count(log):
    """Return a trusted positive pitch count for workload use, or None."""
    try:
        pitches = int(_value(log, 'pitches_thrown', 0) or 0)
    except (TypeError, ValueError):
        return None
    return pitches if pitches > 0 else None


def workload_out_count(log):
    """Return positive recorded outs for workload use, or None."""
    try:
        outs = int(_value(log, 'innings_pitched_outs', 0) or 0)
    except (TypeError, ValueError):
        outs = 0
    if outs > 0:
        return outs

    try:
        innings = float(_value(log, 'innings_pitched', 0) or 0)
    except (TypeError, ValueError):
        return None
    return 1 if innings > 0 else None


def is_workload_appearance_log(log):
    """True when a game-log row is valid for workload calculations."""
    return (
        _value(log, 'game_date') is not None
        and (
            workload_pitch_count(log) is not None
            or workload_out_count(log) is not None
        )
    )


def is_pitch_count_workload_log(log):
    """True when a row can support pitch-count workload display text."""
    return _value(log, 'game_date') is not None and workload_pitch_count(log) is not None


def workload_appearance_logs(logs):
    """Filter raw game logs down to actual workload appearances."""
    return [log for log in (logs or []) if is_workload_appearance_log(log)]


def pitch_count_workload_logs(logs):
    """Filter raw game logs down to displayable pitch-count appearances."""
    return [log for log in (logs or []) if is_pitch_count_workload_log(log)]
