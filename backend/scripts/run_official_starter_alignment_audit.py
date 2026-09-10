"""Bound the blast radius of the official-starter alignment incident.

Read-only. The command opens one session, runs bounded aggregate and row-level
diagnostics over ``game_logs`` / ``scheduled_games``, and never writes, commits,
backfills, or exposes a route. It answers, for a date window:

  A. completed team-games whose published relief set would have differed from
     the official non-starter set under the current-roster join;
  B. team/date summaries that combine more than one game;
  C. appearances attributed to a team the pitcher no longer plays for, and the
     mirror case of a team-game missing its own starter's line;
  D. final team-games with zero, missing, or contradictory canonical starters;
  E. appearances whose official game side is unresolved.

Exit codes:
    0  CLEAN        — no affected identity found in the window.
    1  AFFECTED     — at least one affected identity found (details in output).
    2  ERROR        — the audit itself could not complete.

Only exception class names are reported; messages are discarded because
database errors can carry connection details.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Operator diagnostic command, not a web worker: never start background sync.
os.environ['AUTO_SYNC'] = 'false'

CAPABILITY = 'official_starter_alignment_audit_v1'
MODE = 'read_only'
RESULT_CLEAN = 'CLEAN'
RESULT_AFFECTED = 'AFFECTED'
RESULT_ERROR = 'ERROR'

DEFAULT_WINDOW_DAYS = 30
MAX_LISTED = 200

REGULAR_SEASON = 'R'


def _parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', default=None,
                        help='Last date in the window (YYYY-MM-DD). Defaults to today UTC.')
    parser.add_argument('--days', type=int, default=DEFAULT_WINDOW_DAYS,
                        help=f'Window length in days (default {DEFAULT_WINDOW_DAYS}).')
    parser.add_argument('--team-id', type=int, default=None,
                        help='Restrict the audit to one MLB team id.')
    parser.add_argument('--output', default=None,
                        help='Write the JSON result to this path.')
    return parser.parse_args(argv)


def _window(args):
    through = (
        date.fromisoformat(args.through)
        if args.through
        else datetime.now(timezone.utc).date()
    )
    days = max(1, int(args.days))
    return through - timedelta(days=days - 1), through


def _capped(values):
    items = list(values)
    return {
        'count': len(items),
        'listed': items[:MAX_LISTED],
        'truncated': len(items) > MAX_LISTED,
    }


def _run(args, app_factory=None):
    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from models.scheduled_game import ScheduledGame
    from utils.db import db
    from utils.games_started import RELIEF, START, games_started_state

    if app_factory is None:
        from app import create_app  # noqa: WPS433 — deferred: needs sys.path above

        app_factory = create_app

    start_date, through = _window(args)
    app = app_factory()
    with app.app_context():
        session = db.session

        log_query = (
            session.query(GameLog, Pitcher)
            .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
            .filter(GameLog.game_date >= start_date)
            .filter(GameLog.game_date <= through)
            .filter(GameLog.game_type == REGULAR_SEASON)
        )
        if args.team_id is not None:
            log_query = log_query.filter(
                (GameLog.appearance_team_id == args.team_id)
                | (Pitcher.team_id == args.team_id)
            )
        rows = log_query.all()

        game_pks = sorted({
            log.mlb_game_pk for log, _p in rows if log.mlb_game_pk is not None
        })
        final_sides = set()
        for chunk_start in range(0, len(game_pks), 1000):
            chunk = game_pks[chunk_start:chunk_start + 1000]
            for sched in (
                session.query(ScheduledGame)
                .filter(ScheduledGame.game_pk.in_(chunk))
                .all()
            ):
                if sched.status_state == ScheduledGame.STATE_FINAL:
                    final_sides.add((sched.team_id, sched.game_pk))

        # Official team-side cohorts, keyed by (appearance_team_id, game_pk).
        official = defaultdict(list)
        unresolved = []
        for log, pitcher in rows:
            status = log.appearance_team_status
            if status == GameLog.APPEARANCE_TEAM_RESOLVED and log.appearance_team_id:
                official[(log.appearance_team_id, log.mlb_game_pk)].append((log, pitcher))
            else:
                unresolved.append({
                    'pitcher_id': log.pitcher_id,
                    'pitcher_full_name': pitcher.full_name,
                    'mlb_game_pk': log.mlb_game_pk,
                    'game_date': log.game_date.isoformat(),
                    'appearance_team_status': status,
                    'current_team_id': pitcher.team_id,
                })

        # What the current-roster join WOULD have produced, per (roster team, date).
        roster_cohort = defaultdict(list)
        for log, pitcher in rows:
            if pitcher.team_id is not None:
                roster_cohort[(pitcher.team_id, log.game_date)].append((log, pitcher))

        starter_defects = []
        published_starter_differs = []
        relief_set_differs = []
        for (team_id, game_pk), cohort in sorted(official.items()):
            if (team_id, game_pk) not in final_sides:
                continue
            starters = [
                (log, p) for log, p in cohort
                if games_started_state(log.games_started) == START
            ]
            relief = [
                (log, p) for log, p in cohort
                if games_started_state(log.games_started) == RELIEF
            ]
            unknown = len(cohort) - len(starters) - len(relief)
            if len(starters) != 1 or unknown:
                starter_defects.append({
                    'team_id': team_id,
                    'mlb_game_pk': game_pk,
                    'game_date': cohort[0][0].game_date.isoformat(),
                    'official_starter_count': len(starters),
                    'unknown_start_flag_rows': unknown,
                    'pitcher_ids': sorted(log.pitcher_id for log, _p in cohort),
                })
                continue

            starter_log, starter_pitcher = starters[0]
            # Would the old current-roster join have named a different starter?
            roster_rows = roster_cohort.get((team_id, starter_log.game_date)) or []
            roster_same_game = [
                (log, p) for log, p in roster_rows if log.mlb_game_pk == game_pk
            ]
            roster_starters = [
                (log, p) for log, p in roster_same_game
                if games_started_state(log.games_started) == START
            ]
            if len(roster_starters) != 1 or roster_starters[0][0].pitcher_id != starter_log.pitcher_id:
                published_starter_differs.append({
                    'team_id': team_id,
                    'mlb_game_pk': game_pk,
                    'game_date': starter_log.game_date.isoformat(),
                    'official_starter_pitcher_id': starter_log.pitcher_id,
                    'official_starter_name': starter_pitcher.full_name,
                    'roster_join_starter_pitcher_ids': sorted(
                        log.pitcher_id for log, _p in roster_starters
                    ),
                })

            official_relief_ids = sorted(log.pitcher_id for log, _p in relief)
            roster_relief_ids = sorted(
                log.pitcher_id for log, _p in roster_same_game
                if games_started_state(log.games_started) == RELIEF
            )
            if official_relief_ids != roster_relief_ids:
                relief_set_differs.append({
                    'team_id': team_id,
                    'mlb_game_pk': game_pk,
                    'game_date': starter_log.game_date.isoformat(),
                    'official_relief_pitcher_ids': official_relief_ids,
                    'roster_join_relief_pitcher_ids': roster_relief_ids,
                })

        # Date/team summaries that silently combined more than one game.
        mixed_date_summaries = []
        for (team_id, game_date), cohort in sorted(roster_cohort.items()):
            relief_rows = [
                (log, p) for log, p in cohort
                if games_started_state(log.games_started) == RELIEF
            ]
            pks = sorted({log.mlb_game_pk for log, _p in relief_rows})
            if len(pks) > 1:
                mixed_date_summaries.append({
                    'team_id': team_id,
                    'game_date': game_date.isoformat(),
                    'mlb_game_pks': pks,
                    'relief_appearance_count': len(relief_rows),
                    'outs_total': sum(
                        (log.innings_pitched_outs or 0) for log, _p in relief_rows
                    ),
                })

        # Appearances whose historical owner differs from the current club.
        historical_owner_differs = []
        for log, pitcher in rows:
            if (
                log.appearance_team_status == GameLog.APPEARANCE_TEAM_RESOLVED
                and log.appearance_team_id is not None
                and pitcher.team_id is not None
                and log.appearance_team_id != pitcher.team_id
            ):
                historical_owner_differs.append({
                    'pitcher_id': log.pitcher_id,
                    'pitcher_full_name': pitcher.full_name,
                    'mlb_game_pk': log.mlb_game_pk,
                    'game_date': log.game_date.isoformat(),
                    'appearance_team_id': log.appearance_team_id,
                    'current_team_id': pitcher.team_id,
                })

        findings = {
            'published_starter_differs_from_official': _capped(published_starter_differs),
            'published_relief_set_differs_from_official': _capped(relief_set_differs),
            'date_summaries_combining_multiple_games': _capped(mixed_date_summaries),
            'appearance_owner_differs_from_current_club': _capped(historical_owner_differs),
            'final_games_without_one_official_starter': _capped(starter_defects),
            'appearances_with_unresolved_game_side': _capped(unresolved),
        }
        affected = any(section['count'] for section in findings.values())

        return {
            'capability': CAPABILITY,
            'mode': MODE,
            'result': RESULT_AFFECTED if affected else RESULT_CLEAN,
            'window': {
                'start_date': start_date.isoformat(),
                'through': through.isoformat(),
                'team_id': args.team_id,
            },
            'scanned': {
                'game_log_rows': len(rows),
                'official_team_game_sides': len(official),
                'final_team_game_sides': len(final_sides),
            },
            'max_listed_per_section': MAX_LISTED,
            'findings': findings,
        }


def main(argv=None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        result = _run(args)
    except Exception as exc:  # noqa: BLE001 — class name only, never the message
        result = {
            'capability': CAPABILITY,
            'mode': MODE,
            'result': RESULT_ERROR,
            'error_class': type(exc).__name__,
        }

    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(f'{text}\n', encoding='utf-8')
    print(text)

    return {
        RESULT_CLEAN: 0,
        RESULT_AFFECTED: 1,
        RESULT_ERROR: 2,
    }[result['result']]


if __name__ == '__main__':
    raise SystemExit(main())
