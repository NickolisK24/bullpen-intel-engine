"""
BaseballOS Fatigue Scoring Engine
----------------------------------
Calculates a 0-100 fatigue score for relief pitchers based on:

  1. Pitch Count Load     (30%) — Total pitches thrown in last 7 days
  2. Rest Days            (25%) — Days since last appearance
  3. Appearance Frequency (20%) — # of appearances in rolling 7 and 14-day windows
  4. Leverage Index       (15%) — High-leverage = more physiological/mental stress
  5. Innings Load         (10%) — Total innings in rolling window

Score interpretation:
  0–25   → LOW      (Fresh, readily available)
  26–50  → MODERATE (Some use, monitor)
  51–75  → HIGH     (Fatigued, use with caution)
  76–100 → CRITICAL (Rest required)

All thresholds are tunable via the WEIGHTS and THRESHOLDS dicts below.
"""

from datetime import date, timedelta
from models.fatigue_score import FatigueScore
from utils.db import db

# ─── Configuration ───────────────────────────────────────────────────────────

WEIGHTS = {
    'pitch_count':   0.30,
    'rest_days':     0.25,
    'appearances':   0.20,
    'leverage':      0.15,
    'innings':       0.10,
}

# Pitch count thresholds over last 7 days
PITCH_THRESHOLDS = {
    'max_fresh':    0,
    'moderate':     50,
    'high':         90,
    'critical':     120,
}

# Appearance count thresholds (7-day window)
APPEARANCE_THRESHOLDS = {
    'max_fresh':  0,
    'moderate':   2,
    'high':       4,
    'critical':   5,
}

# Bumped HIGH ceiling from 75 → 80 for a more realistic distribution
RISK_LEVELS = [
    (25,  'LOW'),
    (50,  'MODERATE'),
    (81,  'HIGH'),
    (101, 'CRITICAL'),
]

# ─── Scoring Functions ────────────────────────────────────────────────────────

def score_pitch_count(pitches_last_7: int) -> float:
    """Score 0-100 based on pitches thrown in last 7 days."""
    if pitches_last_7 <= PITCH_THRESHOLDS['max_fresh']:
        return 0.0
    elif pitches_last_7 >= PITCH_THRESHOLDS['critical']:
        return 100.0
    elif pitches_last_7 >= PITCH_THRESHOLDS['high']:
        ratio = (pitches_last_7 - PITCH_THRESHOLDS['high']) / \
                (PITCH_THRESHOLDS['critical'] - PITCH_THRESHOLDS['high'])
        return 50.0 + (ratio * 50.0)
    elif pitches_last_7 >= PITCH_THRESHOLDS['moderate']:
        ratio = (pitches_last_7 - PITCH_THRESHOLDS['moderate']) / \
                (PITCH_THRESHOLDS['high'] - PITCH_THRESHOLDS['moderate'])
        return ratio * 50.0
    else:
        ratio = pitches_last_7 / PITCH_THRESHOLDS['moderate']
        return ratio * 25.0


def score_rest_days(days_since_last: int) -> float:
    """
    Score 0-100 based on rest days since last appearance.
    Inverse: MORE rest = LOWER score.
    """
    if days_since_last is None or days_since_last >= 5:
        return 0.0   # 5+ days rest = fully recovered
    elif days_since_last == 0:
        return 100.0  # Pitched today
    elif days_since_last == 1:
        return 80.0
    elif days_since_last == 2:
        return 55.0
    elif days_since_last == 3:
        return 30.0
    else:  # 4 days
        return 10.0


def score_appearances(apps_last_7: int, apps_last_14: int) -> float:
    """Score based on appearance frequency."""
    weighted = (apps_last_7 * 0.7) + (apps_last_14 * 0.15)

    if weighted <= APPEARANCE_THRESHOLDS['max_fresh']:
        return 0.0
    elif weighted >= APPEARANCE_THRESHOLDS['critical']:
        return 100.0
    elif weighted >= APPEARANCE_THRESHOLDS['high']:
        ratio = (weighted - APPEARANCE_THRESHOLDS['high']) / \
                (APPEARANCE_THRESHOLDS['critical'] - APPEARANCE_THRESHOLDS['high'])
        return 60.0 + (ratio * 40.0)
    elif weighted >= APPEARANCE_THRESHOLDS['moderate']:
        ratio = (weighted - APPEARANCE_THRESHOLDS['moderate']) / \
                (APPEARANCE_THRESHOLDS['high'] - APPEARANCE_THRESHOLDS['moderate'])
        return ratio * 60.0
    else:
        return weighted * 15.0


def score_leverage(avg_leverage: float) -> float:
    """
    Score based on average leverage index of recent appearances.
    LI: 0.0 = garbage time, 1.0 = average, 2.0+ = high leverage
    """
    if avg_leverage is None:
        return 20.0
    elif avg_leverage >= 2.5:
        return 100.0
    elif avg_leverage >= 2.0:
        return 80.0
    elif avg_leverage >= 1.5:
        return 60.0
    elif avg_leverage >= 1.0:
        return 40.0
    else:
        return 15.0


def score_innings(innings_last_7: float) -> float:
    """Score based on innings pitched in last 7 days."""
    if innings_last_7 <= 0:
        return 0.0
    elif innings_last_7 >= 6.0:
        return 100.0
    elif innings_last_7 >= 4.0:
        ratio = (innings_last_7 - 4.0) / 2.0
        return 50.0 + (ratio * 50.0)
    else:
        return (innings_last_7 / 4.0) * 50.0


def get_risk_level(score: float) -> str:
    for threshold, level in RISK_LEVELS:
        if score < threshold:
            return level
    return 'CRITICAL'


# ─── Main Calculator ──────────────────────────────────────────────────────────

def calculate_fatigue(pitcher, game_logs: list, reference_date: date = None) -> FatigueScore:
    """
    Calculate fatigue score for a pitcher given their recent game logs.

    Args:
        pitcher:        Pitcher model instance
        game_logs:      List of GameLog instances, ordered most recent first
        reference_date: The date to score relative to. Defaults to today.
                        Pass the pitcher's last game date when seeding historical
                        data so scores reflect end-of-season workload, not
                        months of offseason rest.

    Returns:
        FatigueScore model instance (not yet committed to DB)
    """
    # Use provided reference date or fall back to today (live mode)
    ref = reference_date if reference_date is not None else date.today()

    seven_days_ago  = ref - timedelta(days=7)
    fourteen_days_ago = ref - timedelta(days=14)

    # Filter logs to relevant windows relative to reference date
    logs_7  = [g for g in game_logs if g.game_date >= seven_days_ago  and g.game_date <= ref]
    logs_14 = [g for g in game_logs if g.game_date >= fourteen_days_ago and g.game_date <= ref]
    last_log = game_logs[0] if game_logs else None

    # Days since last appearance (relative to reference date)
    days_since_last = None
    if last_log:
        days_since_last = (ref - last_log.game_date).days

    pitches_last_7   = sum(g.pitches_thrown or 0   for g in logs_7)
    innings_last_7   = sum(g.innings_pitched or 0.0 for g in logs_7)
    appearances_7    = len(logs_7)
    appearances_14   = len(logs_14)

    leverage_values  = [g.leverage_index for g in logs_7 if g.leverage_index is not None]
    avg_leverage     = sum(leverage_values) / len(leverage_values) if leverage_values else 1.0

    # ── Score each component ──
    pc_score   = score_pitch_count(pitches_last_7)
    rest_score = score_rest_days(days_since_last)
    app_score  = score_appearances(appearances_7, appearances_14)
    lev_score  = score_leverage(avg_leverage)
    inn_score  = score_innings(innings_last_7)

    # ── Weighted aggregate ──
    raw = (
        pc_score   * WEIGHTS['pitch_count'] +
        rest_score * WEIGHTS['rest_days'] +
        app_score  * WEIGHTS['appearances'] +
        lev_score  * WEIGHTS['leverage'] +
        inn_score  * WEIGHTS['innings']
    )
    raw = max(0.0, min(100.0, raw))

    return FatigueScore(
        pitcher_id=pitcher.id,
        raw_score=raw,
        pitch_count_score=pc_score,
        rest_days_score=rest_score,
        appearances_score=app_score,
        leverage_score=lev_score,
        innings_score=inn_score,
        days_since_last_appearance=days_since_last,
        appearances_last_7=appearances_7,
        appearances_last_14=appearances_14,
        pitches_last_7_days=pitches_last_7,
        innings_last_7_days=innings_last_7,
        avg_leverage_last_7=avg_leverage,
        risk_level=get_risk_level(raw),
    )


def recalculate_all_fatigue(pitchers_with_logs: list) -> list:
    """Batch recalculate fatigue for all pitchers and persist to DB."""
    results = []
    for pitcher, logs in pitchers_with_logs:
        score = calculate_fatigue(pitcher, logs)
        db.session.add(score)
        results.append(score)
    db.session.commit()
    return results