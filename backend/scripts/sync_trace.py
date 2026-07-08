"""
Sync Trace — follow one player's appearance through every pipeline stage.

Usage:
    python backend/scripts/sync_trace.py --player 696519 --date 2026-07-04
    python backend/scripts/sync_trace.py --player 696519 --date 2026-07-04 --game-pk 824600
    python backend/scripts/sync_trace.py --player 696519 --date 2026-07-04 --no-network

Prints one PASS / FAIL / SKIP line per stage:

    schedule discovered → game final → boxscore fetched → appearance parsed
    → database row → aggregation → snapshot → frontend endpoint

Exit code 0 when every evaluated stage passes, 1 otherwise.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'

PASS, FAIL, SKIP = 'PASS', 'FAIL', 'SKIP'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Trace one player/date through the sync pipeline.'
    )
    parser.add_argument('--player', type=int, required=True,
                        help='MLB player id (pitchers.mlb_id).')
    parser.add_argument('--date', type=_parse_date, required=True,
                        help='Slate date to trace (YYYY-MM-DD).')
    parser.add_argument('--game-pk', type=int, default=None,
                        help='Restrict the trace to one game.')
    parser.add_argument('--no-network', action='store_true',
                        help='Skip MLB API stages (boxscore fetch/parse).')
    return parser.parse_args(argv)


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f'invalid date {value!r}: use YYYY-MM-DD') from exc


class Trace:
    def __init__(self):
        self.failed = False

    def stage(self, name, verdict, detail=''):
        if verdict == FAIL:
            self.failed = True
        arrow = '  ↓'
        print(f'[{verdict:<4}] {name}{": " + detail if detail else ""}')
        print(arrow)

    def final(self, name, verdict, detail=''):
        if verdict == FAIL:
            self.failed = True
        print(f'[{verdict:<4}] {name}{": " + detail if detail else ""}')


def main(argv=None):
    args = _parse_args(argv)

    from sqlalchemy import func

    from app import app
    from models.game_log import GameLog
    from models.fatigue_score import FatigueScore
    from models.pitcher import Pitcher
    from models.postgame_processed_game import PostgameProcessedGame
    from models.scheduled_game import ScheduledGame
    from services import dashboard_snapshot, sync as sync_service
    from services.mlb_api import mlb_client
    from utils.db import db

    trace = Trace()
    print(f'SYNC TRACE  player={args.player}  date={args.date}  '
          f'game_pk={args.game_pk or "auto"}')
    print('=' * 78)

    with app.app_context():
        # ── Stage 0: pitcher record ─────────────────────────────────────────
        pitcher = Pitcher.query.filter_by(mlb_id=args.player).first()
        if pitcher is None:
            trace.stage('pitcher record', FAIL,
                        f'no pitchers row with mlb_id={args.player} — the daily '
                        'lane never fetches unknown pitchers; only the postgame '
                        'boxscore lane creates them')
        else:
            trace.stage('pitcher record', PASS,
                        f'id={pitcher.id} {pitcher.full_name!r} team={pitcher.team_abbreviation} '
                        f'active={pitcher.active} roster_status={pitcher.roster_status}')

        # ── Stage 1: schedule discovered ────────────────────────────────────
        schedule_query = ScheduledGame.query.filter(ScheduledGame.game_date == args.date)
        if args.game_pk:
            schedule_query = schedule_query.filter(ScheduledGame.game_pk == args.game_pk)
        elif pitcher is not None and pitcher.team_id:
            schedule_query = schedule_query.filter(ScheduledGame.team_id == pitcher.team_id)
        schedule_rows = schedule_query.order_by(ScheduledGame.game_pk).all()
        game_pks = sorted({row.game_pk for row in schedule_rows})
        if game_pks:
            trace.stage('schedule discovered', PASS,
                        f'{len(game_pks)} game(s) in scheduled_games: {game_pks}')
        else:
            trace.stage('schedule discovered', FAIL,
                        'no scheduled_games rows match — schedule ingestion never '
                        'covered this slate (daily-lane finality is unresolvable here)')

        # ── Stage 2: game final ─────────────────────────────────────────────
        final_pks = []
        for game_pk in game_pks:
            finality = sync_service.resolve_scheduled_game_finality(game_pk)
            states = sorted({
                row.status_state for row in schedule_rows if row.game_pk == game_pk
            })
            if finality == sync_service.SPLIT_FINALITY_FINAL:
                final_pks.append(game_pk)
                trace.stage(f'game final ({game_pk})', PASS, f'status_state={states}')
            else:
                trace.stage(f'game final ({game_pk})', FAIL,
                            f'finality={finality} status_state={states}')
        if not game_pks:
            trace.stage('game final', SKIP, 'no games discovered')

        # ── Stage 3 + 4: boxscore fetched / appearance parsed ───────────────
        parsed_lines = {}
        if args.no_network:
            trace.stage('boxscore fetched', SKIP, '--no-network')
            trace.stage('appearance parsed', SKIP, '--no-network')
        elif not final_pks:
            trace.stage('boxscore fetched', SKIP, 'no final games to fetch')
            trace.stage('appearance parsed', SKIP, 'no boxscore')
        else:
            for game_pk in final_pks:
                try:
                    boxscore = mlb_client.get_game_boxscore(game_pk)
                except Exception as exc:  # noqa: BLE001 — trace, don't crash
                    trace.stage(f'boxscore fetched ({game_pk})', FAIL, str(exc))
                    continue
                lines = sync_service._extract_pitching_lines_from_boxscore(boxscore)
                trace.stage(f'boxscore fetched ({game_pk})', PASS,
                            f'{len(lines)} pitching line(s)')
                line = next(
                    (entry for entry in lines if entry.get('player_id') == args.player),
                    None,
                )
                if line is None:
                    trace.stage(f'appearance parsed ({game_pk})', FAIL,
                                f'player {args.player} not in this boxscore\'s '
                                'pitching lines')
                else:
                    parsed_lines[game_pk] = line
                    stats = line.get('stats') or {}
                    trace.stage(
                        f'appearance parsed ({game_pk})', PASS,
                        f"IP={stats.get('inningsPitched')} "
                        f"pitches={stats.get('numberOfPitches')} "
                        f"K={stats.get('strikeOuts')} team={line.get('team')}",
                    )

        # ── Stage 5: database row ───────────────────────────────────────────
        stored_rows = []
        if pitcher is None:
            trace.stage('database row', FAIL, 'no pitcher record, so no game_logs row')
        else:
            row_query = GameLog.query.filter(
                GameLog.pitcher_id == pitcher.id,
                GameLog.game_date == args.date,
            )
            if args.game_pk:
                row_query = GameLog.query.filter(
                    GameLog.pitcher_id == pitcher.id,
                    GameLog.mlb_game_pk == args.game_pk,
                )
            stored_rows = row_query.all()
            if stored_rows:
                detail = '; '.join(
                    f'game_pk={row.mlb_game_pk} IP={row.innings_pitched} '
                    f'pitches={row.pitches_thrown} corrections={row.stat_correction_count}'
                    for row in stored_rows
                )
                trace.stage('database row', PASS, detail)
            else:
                latest = (
                    db.session.query(func.max(GameLog.game_date))
                    .filter(GameLog.pitcher_id == pitcher.id)
                    .scalar()
                )
                trace.stage('database row', FAIL,
                            f'no game_logs row for {args.date}; latest stored '
                            f'appearance is {latest or "never"}')
            for game_pk in (game_pks or []):
                marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=game_pk).first()
                if marker is None:
                    trace.stage(f'postgame marker ({game_pk})', FAIL,
                                'no postgame_processed_games row — the game was '
                                'never postgame-processed')
                else:
                    verdict = PASS if marker.processing_status == (
                        PostgameProcessedGame.STATUS_FULLY_PROCESSED
                    ) else FAIL
                    trace.stage(f'postgame marker ({game_pk})', verdict,
                                f'status={marker.processing_status} '
                                f'lines_seen={marker.pitching_lines_seen} '
                                f'attempts={marker.attempt_count} '
                                f'reason={marker.incomplete_reason}')

        # ── Stage 6: aggregation ────────────────────────────────────────────
        if pitcher is None or not stored_rows:
            trace.stage('aggregation', SKIP, 'no stored row to aggregate')
        else:
            score = (
                FatigueScore.query
                .filter_by(pitcher_id=pitcher.id)
                .order_by(FatigueScore.calculated_at.desc())
                .first()
            )
            workload_visible = any(
                (row.pitches_thrown or 0) > 0 or (row.innings_pitched_outs or 0) > 0
                for row in stored_rows
            )
            if score is None:
                trace.stage('aggregation', FAIL,
                            'no FatigueScore row — pitcher never scored '
                            '(active=False pitchers are skipped)')
            else:
                fresh = score.calculated_at is not None and (
                    score.calculated_at.date() >= args.date
                )
                trace.stage(
                    'aggregation', PASS if (fresh and workload_visible) else FAIL,
                    f'latest fatigue calculated_at={score.calculated_at} '
                    f'(covers {args.date}: {fresh}); '
                    f'workload-visible row: {workload_visible}',
                )

        # ── Stage 7: snapshot ───────────────────────────────────────────────
        snapshot = dashboard_snapshot.get_latest_dashboard_snapshot()
        if snapshot is None:
            trace.stage('snapshot', FAIL, 'no published dashboard snapshot')
        else:
            covers = snapshot.data_through is not None and snapshot.data_through >= args.date
            payload_text = str(snapshot.payload or '')
            mentioned = str(args.player) in payload_text or (
                pitcher is not None and (pitcher.full_name or '') in payload_text
            )
            trace.stage(
                'snapshot',
                PASS if covers else FAIL,
                f'snapshot_id={snapshot.id} data_through={snapshot.data_through} '
                f'covers {args.date}: {covers}; player referenced in payload: {mentioned}',
            )

        # ── Stage 8: frontend endpoint ──────────────────────────────────────
        if pitcher is None:
            trace.final('frontend endpoint', FAIL, 'no pitcher record to serve')
        else:
            recent_window_start = args.date - timedelta(days=14)
            served = bool(stored_rows)
            trace.final(
                'frontend endpoint',
                PASS if served else FAIL,
                f'GET /api/bullpen/fatigue/{pitcher.id} and '
                f'/api/bullpen/pitchers/{pitcher.id}/recent-work read game_logs '
                f'live; row present for {args.date}: {served} '
                f'(recent-work window starts {recent_window_start})',
            )

    print('=' * 78)
    print('TRACE RESULT:', 'FAIL' if trace.failed else 'PASS')
    return 1 if trace.failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
