"""
BaseballOS — Fatigue Score Recalculator
----------------------------------------
Recalculates fatigue scores for all pitchers using each pitcher's
last game date as the reference point (not today's date).

This produces realistic end-of-season fatigue scores from historical data
instead of near-zero scores caused by months of offseason rest.

Run: python recalculate_fatigue.py
"""

from datetime import timedelta
from app import create_app
from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
from services.fatigue import calculate_fatigue

app = create_app()

def recalculate():
    pitchers = Pitcher.query.filter_by(active=True).all()
    print(f"Recalculating fatigue for {len(pitchers)} pitchers...")

    scored = 0
    skipped = 0

    for i, pitcher in enumerate(pitchers):
        if i % 50 == 0:
            print(f"  → {i}/{len(pitchers)}...")

        # Find the pitcher's most recent game
        latest_log = (
            GameLog.query
            .filter_by(pitcher_id=pitcher.id)
            .order_by(GameLog.game_date.desc())
            .first()
        )

        if not latest_log:
            skipped += 1
            continue

        # Use last game date as the reference point
        reference_date = latest_log.game_date

        # Pull logs from the 14-day window before that date
        window_start = reference_date - timedelta(days=14)
        logs = (
            GameLog.query
            .filter(
                GameLog.pitcher_id == pitcher.id,
                GameLog.game_date >= window_start,
                GameLog.game_date <= reference_date
            )
            .order_by(GameLog.game_date.desc())
            .all()
        )

        # Calculate with historical reference date
        score = calculate_fatigue(pitcher, logs, reference_date=reference_date)
        db.session.add(score)
        scored += 1

        # Commit in batches
        if i % 100 == 0 and i > 0:
            db.session.commit()

    db.session.commit()
    print(f"\n✅ Done! Scored: {scored} | Skipped (no logs): {skipped}")

    # Print risk distribution summary
    from sqlalchemy import func
    from sqlalchemy.orm import aliased

    subq = (
        db.session.query(
            FatigueScore.pitcher_id,
            func.max(FatigueScore.calculated_at).label('max_calc')
        )
        .group_by(FatigueScore.pitcher_id)
        .subquery()
    )
    latest_scores = (
        db.session.query(FatigueScore)
        .join(subq, (FatigueScore.pitcher_id == subq.c.pitcher_id) &
                    (FatigueScore.calculated_at == subq.c.max_calc))
        .all()
    )

    breakdown = {'LOW': 0, 'MODERATE': 0, 'HIGH': 0, 'CRITICAL': 0}
    total_score = 0
    for s in latest_scores:
        if s.risk_level in breakdown:
            breakdown[s.risk_level] += 1
        total_score += s.raw_score

    avg = total_score / len(latest_scores) if latest_scores else 0

    print(f"\n📊 Risk Distribution:")
    print(f"   LOW:      {breakdown['LOW']}")
    print(f"   MODERATE: {breakdown['MODERATE']}")
    print(f"   HIGH:     {breakdown['HIGH']}")
    print(f"   CRITICAL: {breakdown['CRITICAL']}")
    print(f"   Avg Score: {avg:.1f}")


if __name__ == '__main__':
    with app.app_context():
        recalculate()