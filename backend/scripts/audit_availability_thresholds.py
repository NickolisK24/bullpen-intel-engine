"""
Generate an Availability Engine threshold audit from local database data.

The script applies services.availability.classify_availability to existing
fatigue/game-log rows and writes a Markdown or JSON report. It does not change
thresholds, fatigue scoring, API responses, or frontend output.
"""

from argparse import ArgumentParser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from models.fatigue_score import FatigueScore  # noqa: E402
from models.game_log import GameLog  # noqa: E402
from models.pitcher import Pitcher  # noqa: E402
from services.availability import ACTIVE_WINDOW_DAYS, classify_availability  # noqa: E402
from services.availability_threshold_audit import (  # noqa: E402
    render_json_report,
    render_markdown_report,
    summarize_records,
)
from utils.db import db  # noqa: E402


DEFAULT_OUTPUT = ROOT / 'reports' / 'availability_threshold_audit.md'


def parse_date(value):
    if value is None:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def latest_fatigue_rows():
    subq = (
        db.session.query(
            FatigueScore.pitcher_id,
            db.func.max(FatigueScore.calculated_at).label('max_calc'),
        )
        .group_by(FatigueScore.pitcher_id)
        .subquery()
    )

    return (
        db.session.query(FatigueScore, Pitcher)
        .join(
            subq,
            (FatigueScore.pitcher_id == subq.c.pitcher_id)
            & (FatigueScore.calculated_at == subq.c.max_calc),
        )
        .join(Pitcher, FatigueScore.pitcher_id == Pitcher.id)
        .order_by(Pitcher.team_abbreviation, Pitcher.full_name)
        .all()
    )


def latest_game_date_for(pitcher_id):
    return (
        db.session.query(db.func.max(GameLog.game_date))
        .filter(GameLog.pitcher_id == pitcher_id)
        .scalar()
    )


def logs_for_window(pitcher_id, reference_date):
    window_start = reference_date - timedelta(days=4)
    return (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_date >= window_start,
            GameLog.game_date <= reference_date,
        )
        .order_by(GameLog.game_date.desc())
        .all()
    )


def classify_rows(rows, reference_date, mode):
    records = []
    for score, pitcher in rows:
        latest_game_date = latest_game_date_for(pitcher.id)
        if mode == 'latest_workload_snapshot':
            ref = latest_game_date or reference_date
        else:
            ref = reference_date

        logs = logs_for_window(pitcher.id, ref)
        availability = classify_availability(
            score=score,
            game_logs=logs,
            reference_date=ref,
            latest_game_date=latest_game_date,
            active_window_days=ACTIVE_WINDOW_DAYS,
        )
        records.append({
            'pitcher_id': pitcher.id,
            'pitcher_name': pitcher.full_name,
            'team': pitcher.team_abbreviation,
            'availability': availability,
        })
    return records


def build_audit(reference_date=None, near_threshold_limit=12):
    ref = reference_date or date.today()
    rows = latest_fatigue_rows()
    current_records = classify_rows(rows, reference_date=ref, mode='current')
    snapshot_records = classify_rows(rows, reference_date=ref, mode='latest_workload_snapshot')
    return {
        'reference_date': ref,
        'current': summarize_records(current_records, near_threshold_limit=near_threshold_limit),
        'latest_workload_snapshot': summarize_records(snapshot_records, near_threshold_limit=near_threshold_limit),
    }


def write_report(report_text, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding='utf-8')


def print_summary(audit, output_path):
    current = audit['current']
    snapshot = audit['latest_workload_snapshot']
    print(f'Availability threshold audit written to {output_path}')
    print(f"Current total pitchers: {current['total_pitchers']}")
    print(f"Current status distribution: {current['status_distribution']}")
    print(f"Current data state distribution: {current['data_state_distribution']}")
    print(f"Latest-workload snapshot status distribution: {snapshot['status_distribution']}")
    print(f"Latest-workload snapshot data state distribution: {snapshot['data_state_distribution']}")


def main():
    parser = ArgumentParser(description='Audit Availability Engine threshold behavior.')
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT), help='Report path to write.')
    parser.add_argument('--format', choices=['markdown', 'json'], default='markdown', help='Report format.')
    parser.add_argument('--reference-date', help='YYYY-MM-DD date for current availability audit. Defaults to today.')
    parser.add_argument('--near-threshold-limit', type=int, default=12, help='Number of near-threshold examples per section.')
    args = parser.parse_args()

    reference_date = parse_date(args.reference_date)
    output_path = Path(args.output)

    app = create_app()
    with app.app_context():
        generated_at = datetime.now(timezone.utc)
        audit = build_audit(reference_date=reference_date, near_threshold_limit=args.near_threshold_limit)
        if args.format == 'json':
            report = render_json_report(
                audit['current'],
                snapshot_summary=audit['latest_workload_snapshot'],
                generated_at=generated_at,
                reference_date=audit['reference_date'],
            )
        else:
            report = render_markdown_report(
                audit['current'],
                snapshot_summary=audit['latest_workload_snapshot'],
                generated_at=generated_at,
                reference_date=audit['reference_date'],
            )
        write_report(report, output_path)
        print_summary(audit, output_path)


if __name__ == '__main__':
    main()
