"""
Backfill GameLog.games_started from MLB game logs (Role Authority V1).

Re-reads the same MLB pitching game-log splits the sync pipeline already uses
and populates the authoritative ``gamesStarted`` signal on existing rows. This
is the MVP-approved *recent-window* backfill — it does NOT rebuild full history.

Idempotent: re-running only writes rows whose stored value differs. Safe to run
before flipping role authority on; rows it does not reach simply stay null
(read as "start unknown" → Unknown, which is withheld, never a wrong role).

Usage (from backend/):
    python -m scripts.backfill_games_started [--days-back 120] [--season 2026] [--dry-run]
"""

from argparse import ArgumentParser
from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from models.game_log import GameLog  # noqa: E402
from models.pitcher import Pitcher  # noqa: E402
from services.mlb_api import mlb_client  # noqa: E402
from utils.db import db  # noqa: E402


def _season_for(reference_date):
    return reference_date.year


def backfill(days_back=120, season=None, reference_date=None, dry_run=False):
    """
    Populate games_started for active pitchers' recent game logs.

    Returns a summary dict: pitchers scanned, rows examined, rows updated,
    fetch errors.
    """
    ref = reference_date or date.today()
    season = season or _season_for(ref)
    cutoff = ref - timedelta(days=days_back)

    pitchers = Pitcher.query.filter_by(active=True).all()
    rows_examined = 0
    rows_updated = 0
    fetch_errors = 0

    for pitcher in pitchers:
        try:
            splits = mlb_client.get_pitcher_game_logs(pitcher.mlb_id, season=season)
        except Exception:
            fetch_errors += 1
            continue

        gs_by_game_pk = {}
        for split in splits or []:
            game_pk = (split.get('game') or {}).get('gamePk')
            if game_pk is None:
                continue
            stat = split.get('stat') or {}
            gs_by_game_pk[game_pk] = int(stat.get('gamesStarted', 0) or 0)

        rows = (
            GameLog.query
            .filter(GameLog.pitcher_id == pitcher.id, GameLog.game_date >= cutoff)
            .all()
        )
        for row in rows:
            rows_examined += 1
            value = gs_by_game_pk.get(row.mlb_game_pk)
            if value is None:
                continue
            if row.games_started != value:
                row.games_started = value
                rows_updated += 1

        if not dry_run:
            db.session.commit()

    if dry_run:
        db.session.rollback()

    return {
        'pitchers': len(pitchers),
        'rows_examined': rows_examined,
        'rows_updated': rows_updated,
        'fetch_errors': fetch_errors,
        'days_back': days_back,
        'season': season,
        'dry_run': dry_run,
    }


def main():
    parser = ArgumentParser(description='Backfill GameLog.games_started (recent window).')
    parser.add_argument('--days-back', type=int, default=120)
    parser.add_argument('--season', type=int, default=None)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        summary = backfill(
            days_back=args.days_back,
            season=args.season,
            dry_run=args.dry_run,
        )
    print(summary)


if __name__ == '__main__':
    main()
