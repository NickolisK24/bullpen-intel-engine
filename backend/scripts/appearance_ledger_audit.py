"""
Appearance Ledger Audit — prove the appearance ledger is complete.

Reconciles scheduled finals, stored appearance rows, and postgame ingest
markers over a trailing window and renders a publish-eligibility verdict.
Exit code 0 = publish eligible, 1 = deficits found (fail-closed), 2 = the
audit itself could not run.

Usage:
    python backend/scripts/appearance_ledger_audit.py
    python backend/scripts/appearance_ledger_audit.py --end-date 2026-07-05 --days 10
    python backend/scripts/appearance_ledger_audit.py --deep       # fetch boxscores
    python backend/scripts/appearance_ledger_audit.py --json       # machine-readable

--deep resolves WHO is missing: for every deficit game it fetches the MLB
boxscore, diffs the pitching lines against stored rows, and reports each
affected player whose latest stored appearance now provably lags MLB.
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Audit the appearance ledger.')
    parser.add_argument('--end-date', type=_parse_date, default=None,
                        help='Last slate date of the window (default: product today).')
    parser.add_argument('--days', type=int, default=None,
                        help='Window size in days (default: APPEARANCE_LEDGER_WINDOW_DAYS or 10).')
    parser.add_argument('--deep', action='store_true',
                        help='Fetch boxscores for deficit games to name affected players.')
    parser.add_argument('--json', action='store_true', dest='as_json',
                        help='Emit the raw ledger dict as JSON.')
    return parser.parse_args(argv)


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f'invalid date {value!r}: use YYYY-MM-DD') from exc


def _deficit_game_pks(ledger):
    pks = [entry['game_pk'] for entry in ledger['missing_games']]
    pks += [entry['game_pk'] for entry in ledger['count_deficit_games']]
    pks += [entry['game_pk'] for entry in ledger['incomplete_marker_games']]
    return sorted(set(pks))


def _deep_inspect(ledger):
    """Fetch boxscores for deficit games; name missing players and their
    latest-appearance mismatches. Network failures degrade to unknowns —
    the verdict never improves because deep inspection failed."""
    from sqlalchemy import func

    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from services.mlb_api import mlb_client
    from services.sync import _extract_pitching_lines_from_boxscore
    from utils.db import db

    mismatches = []
    unfetchable = []
    for game_pk in _deficit_game_pks(ledger):
        try:
            boxscore = mlb_client.get_game_boxscore(game_pk)
        except Exception as exc:  # noqa: BLE001 — audit must finish
            unfetchable.append({'game_pk': game_pk, 'error': str(exc)})
            continue
        lines = _extract_pitching_lines_from_boxscore(boxscore)
        stored_pitcher_mlb_ids = {
            mlb_id
            for (mlb_id,) in (
                db.session.query(Pitcher.mlb_id)
                .join(GameLog, GameLog.pitcher_id == Pitcher.id)
                .filter(GameLog.mlb_game_pk == game_pk)
                .all()
            )
        }
        for line in lines:
            player_id = line.get('player_id')
            if player_id in stored_pitcher_mlb_ids:
                continue
            pitcher = Pitcher.query.filter_by(mlb_id=player_id).first()
            latest_stored = None
            if pitcher is not None:
                latest_stored = (
                    db.session.query(func.max(GameLog.game_date))
                    .filter(GameLog.pitcher_id == pitcher.id)
                    .scalar()
                )
            mismatches.append({
                'game_pk': game_pk,
                'player_id': player_id,
                'name': line.get('name'),
                'team': line.get('team'),
                'latest_stored_appearance': (
                    latest_stored.isoformat() if latest_stored else None
                ),
                'tracked': pitcher is not None,
            })
    return mismatches, unfetchable


def _render(ledger, mismatches, unfetchable, deep):
    bar = '=' * 80
    lines = [bar, '', 'APPEARANCE LEDGER AUDIT', '']
    lines.append(f"Window: {ledger['window_start']} .. {ledger['window_end']} "
                 f"({ledger['window_days']} day(s))")
    lines.append('')
    lines.append(f"Completed games expected:      {ledger['expected_games']}")
    lines.append(f"Completed games represented:   {ledger['represented_games']}")
    lines.append(f"Expected reliever appearances: {ledger['expected_appearances']} "
                 '(pitching lines seen by completed-game ingests; includes starters)')
    lines.append(f"Stored appearances:            {ledger['stored_appearances']}")

    if deep:
        lines.append(f"Latest appearance mismatches:  {len(mismatches)}")
        players = sorted({
            f"{entry['name'] or 'unknown'} ({entry['player_id']}, "
            f"last stored: {entry['latest_stored_appearance'] or 'never'})"
            for entry in mismatches
        })
        lines.append(f"Players affected:              {len(players)}")
        for player in players:
            lines.append(f'  - {player}')
        for entry in unfetchable:
            lines.append(f"  ! boxscore unavailable for game {entry['game_pk']}: "
                         f"{entry['error']}")
    else:
        deficits = _deficit_game_pks(ledger)
        lines.append('Latest appearance mismatches:  not inspected '
                     f'(run with --deep){" — " + str(len(deficits)) + " deficit game(s) to inspect" if deficits else ""}')
        lines.append('Players affected:              not inspected (run with --deep)')

    missing = [str(entry['game_pk']) for entry in ledger['missing_games']]
    count_deficit = [str(entry['game_pk']) for entry in ledger['count_deficit_games']]
    incomplete = [str(entry['game_pk']) for entry in ledger['incomplete_marker_games']]
    lines.append(f"Missing game_pks:              {', '.join(missing) or 'none'}")
    if count_deficit:
        lines.append(f"Count-deficit game_pks:        {', '.join(count_deficit)}")
    if incomplete:
        lines.append(f"Incomplete-marker game_pks:    {', '.join(incomplete)}")

    incomplete_dates = [
        f"{slate} ({entry['represented']}/{entry['expected']})"
        for slate, entry in ledger['per_date'].items()
        if entry['missing_game_pks']
    ]
    if incomplete_dates:
        lines.append(f"Dates with holes:              {', '.join(incomplete_dates)}")

    lines.append('')
    lines.append('Publish eligible:')
    lines.append('')
    lines.append('YES' if ledger['complete'] else 'NO')
    if not ledger['complete']:
        lines.append('')
        lines.append('Reasons: ' + ', '.join(ledger['reasons']))
    lines.append('')
    lines.append(bar)
    return '\n'.join(lines)


def main(argv=None):
    args = _parse_args(argv)

    from app import app
    from services import appearance_ledger

    with app.app_context():
        try:
            ledger = appearance_ledger.build_appearance_ledger(
                end_date=args.end_date,
                window_days=args.days,
            )
        except Exception as exc:  # noqa: BLE001 — report, exit fail-closed
            print(f'APPEARANCE LEDGER AUDIT could not run: {exc}', file=sys.stderr)
            return 2

        mismatches, unfetchable = ([], [])
        if args.deep:
            mismatches, unfetchable = _deep_inspect(ledger)

        if args.as_json:
            print(json.dumps({
                'ledger': ledger,
                'latest_appearance_mismatches': mismatches,
                'unfetchable_games': unfetchable,
                'publish_eligible': ledger['complete'],
            }, indent=2, sort_keys=True, default=str))
        else:
            print(_render(ledger, mismatches, unfetchable, args.deep))

    return 0 if ledger['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
