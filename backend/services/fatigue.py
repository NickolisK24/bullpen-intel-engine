"""
BaseballOS Fatigue Scoring Engine
----------------------------------
Calculates a 0-100 fatigue score for relief pitchers based on four factors
the MLB Stats API exposes reliably:

  1. Pitch Count Load     (35%) — Total pitches thrown in last 7 days
  2. Rest Days            (30%) — Days since last appearance
  3. Appearance Frequency (20%) — # of appearances in rolling 7 and 14-day windows
  4. Innings Load         (15%) — Total innings in rolling window

NOTE on Leverage Index: an earlier version of the model included LI as a 5th
component (15%). The MLB Stats API gameLog endpoint does not expose LI — it's
a Fangraphs/Baseball Savant computed stat derived from play-by-play data we
don't ingest. Rather than fake the data with a constant default, we dropped
the component entirely and redistributed its weight across the four factors
we can measure. The `leverage_score` column on FatigueScore is preserved for
schema stability but is no longer used in the composite calculation.

Score interpretation:
  0–24   → LOW      (Fresh, readily available)
  25–49  → MODERATE (Some use, monitor)
  50–80  → HIGH     (Fatigued, use with caution)
  81–100 → CRITICAL (Rest required)

All thresholds are tunable via the WEIGHTS and THRESHOLDS dicts below.
"""

from datetime import date, timedelta
from models.fatigue_score import FatigueScore
from utils.db import db

# ─── Configuration ───────────────────────────────────────────────────────────

# Weights sum to 1.0 across the four factors we can reliably measure from
# the MLB Stats API. Leverage Index was originally a 5th component (15%)
# but MLB's gameLog endpoint does not expose LI — it's a Fangraphs/Savant-
# computed stat derived from play-by-play. Rather than fake the data, we
# dropped LI and redistributed its weight across the components we trust.
WEIGHTS = {
    'pitch_count': 0.35,
    'rest_days':   0.30,
    'appearances': 0.20,
    'innings':     0.15,
}

PITCH_THRESHOLDS = {
    'max_fresh':    0,
    'moderate':     50,
    'high':         90,
    'critical':     120,
}

APPEARANCE_THRESHOLDS = {
    'max_fresh':  0,
    'moderate':   2,
    'high':       4,
    'critical':   5,
}

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
        return 0.0
    elif days_since_last == 0:
        return 100.0
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
    ref = reference_date if reference_date is not None else date.today()

    seven_days_ago    = ref - timedelta(days=7)
    fourteen_days_ago = ref - timedelta(days=14)

    logs_7  = [g for g in game_logs if g.game_date >= seven_days_ago  and g.game_date <= ref]
    logs_14 = [g for g in game_logs if g.game_date >= fourteen_days_ago and g.game_date <= ref]
    last_log = game_logs[0] if game_logs else None

    days_since_last = None
    if last_log:
        days_since_last = (ref - last_log.game_date).days

    pitches_last_7  = sum(g.pitches_thrown or 0   for g in logs_7)
    innings_last_7  = sum(g.innings_pitched or 0.0 for g in logs_7)
    appearances_7   = len(logs_7)
    appearances_14  = len(logs_14)

    pc_score   = score_pitch_count(pitches_last_7)
    rest_score = score_rest_days(days_since_last)
    app_score  = score_appearances(appearances_7, appearances_14)
    inn_score  = score_innings(innings_last_7)

    raw = (
        pc_score   * WEIGHTS['pitch_count'] +
        rest_score * WEIGHTS['rest_days']   +
        app_score  * WEIGHTS['appearances'] +
        inn_score  * WEIGHTS['innings']
    )
    raw = max(0.0, min(100.0, raw))

    return FatigueScore(
        pitcher_id=pitcher.id,
        raw_score=raw,
        pitch_count_score=pc_score,
        rest_days_score=rest_score,
        appearances_score=app_score,
        leverage_score=0.0,         # deprecated component, retained for schema stability
        innings_score=inn_score,
        days_since_last_appearance=days_since_last,
        appearances_last_7=appearances_7,
        appearances_last_14=appearances_14,
        pitches_last_7_days=pitches_last_7,
        innings_last_7_days=innings_last_7,
        avg_leverage_last_7=None,   # no longer collected
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