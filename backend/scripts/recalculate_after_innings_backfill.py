import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import desc


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'

from app import app
from services import dashboard_snapshot as dashboard_snapshot_service  # noqa: E402
from services import sync as sync_service  # noqa: E402
from services import sync_metadata  # noqa: E402
from services.fatigue import calculate_fatigue  # noqa: E402
from services.availability_snapshot import (  # noqa: E402
    CURRENT_AVAILABILITY_MODE,
    classify_latest_fatigue_rows,
    latest_fatigue_rows as availability_latest_fatigue_rows,
)
from models.game_log import GameLog  # noqa: E402
from models.pitcher import Pitcher  # noqa: E402
from utils.db import db  # noqa: E402


def _latest_state(reference_date):
    rows = availability_latest_fatigue_rows()
    availability = classify_latest_fatigue_rows(
        rows,
        reference_date=reference_date,
        mode=CURRENT_AVAILABILITY_MODE,
    )
    availability_by_pitcher = {
        record['pitcher'].id: record['availability']['availability_status']
        for record in availability
    }
    return {
        pitcher.id: {
            'raw_score': float(score.raw_score or 0.0),
            'risk_level': score.risk_level,
            'availability_status': availability_by_pitcher.get(pitcher.id),
        }
        for score, pitcher in rows
    }


def _impact(before, after):
    changed_value = 0
    changed_risk = 0
    changed_availability = 0
    for pitcher_id, before_row in before.items():
        after_row = after.get(pitcher_id)
        if not after_row:
            continue
        if abs(before_row['raw_score'] - after_row['raw_score']) > 1e-9:
            changed_value += 1
        if before_row['risk_level'] != after_row['risk_level']:
            changed_risk += 1
        if before_row['availability_status'] != after_row['availability_status']:
            changed_availability += 1
    return {
        'pitchers_with_changed_fatigue_value': changed_value,
        'pitchers_with_changed_risk_tier': changed_risk,
        'pitchers_with_changed_availability_tier': changed_availability,
    }


def _has_current_window_logs(pitcher_id, reference_date):
    window_start = reference_date - timedelta(days=14)
    return GameLog.query.filter(
        GameLog.pitcher_id == pitcher_id,
        GameLog.game_date >= window_start,
        GameLog.game_date <= reference_date,
    ).first() is not None


def _recalculate_stale_latest_workload_scores(reference_date):
    updated = 0
    pitchers = Pitcher.query.all()
    for pitcher in pitchers:
        if pitcher.active and _has_current_window_logs(pitcher.id, reference_date):
            continue

        latest_game = (
            db.session.query(GameLog.game_date)
            .filter(GameLog.pitcher_id == pitcher.id)
            .order_by(desc(GameLog.game_date))
            .limit(1)
            .scalar()
        )
        if latest_game is None:
            continue

        historical_ref = latest_game + timedelta(days=1)
        historical_start = historical_ref - timedelta(days=14)
        logs = (
            GameLog.query
            .filter(
                GameLog.pitcher_id == pitcher.id,
                GameLog.game_date >= historical_start,
                GameLog.game_date <= historical_ref,
            )
            .order_by(desc(GameLog.game_date))
            .all()
        )
        if not logs:
            continue

        db.session.add(calculate_fatigue(pitcher, logs, reference_date=historical_ref))
        updated += 1

    db.session.commit()
    return updated


def main():
    parser = argparse.ArgumentParser(
        description='Recalculate fatigue after innings backfill and report impact.',
    )
    parser.add_argument(
        '--build-dashboard-snapshot',
        action='store_true',
        help='Store a fresh dashboard snapshot after recalculation.',
    )
    args = parser.parse_args()

    with app.app_context():
        reference_date = sync_metadata.canonical_fatigue_reference_date()
        before = _latest_state(reference_date)
        current_updated = sync_service.recalculate_all_fatigue(reference_date=reference_date)
        stale_updated = _recalculate_stale_latest_workload_scores(reference_date)
        after = _latest_state(reference_date)
        payload = {
            'reference_date': reference_date.isoformat(),
            'pitchers_recalculated': current_updated + stale_updated,
            'current_window_pitchers_recalculated': current_updated,
            'stale_latest_workload_pitchers_recalculated': stale_updated,
            **_impact(before, after),
        }
        if args.build_dashboard_snapshot:
            payload['dashboard_snapshot'] = dashboard_snapshot_service.build_bullpen_dashboard_snapshot_v2(
                source=dashboard_snapshot_service.SNAPSHOT_SOURCE_BUILDER_V2,
                publish=True,
            )

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
