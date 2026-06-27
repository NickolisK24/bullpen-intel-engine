"""
Shared sync service.

Consolidates the logic used by the /api/bullpen/sync endpoint and the
APScheduler daily job so both paths hit the same code. Keep this pure:
it only touches the DB and the MLB API — no Flask request objects,
no jsonify — so it can run from any context that has an app_context().
"""

from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import desc

from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.postgame_processed_game import PostgameProcessedGame
from models.sync_run import SyncRun
from models.sync_failure import SyncFailure
from services import dead_letter
from services import sync_metadata
from services.availability_reference_date import PRODUCT_TIMEZONE
from services.completed_game_context_payload_adapter import build_completed_game_payload
from services.completed_game_context_service import (
    extract_completed_game_contexts,
    upsert_completed_game_context,
)
from services.fatigue import calculate_fatigue
from services.mlb_api import mlb_client
from services.roster_status_sync import sync_roster_statuses
from services.team_assignment_sync import sync_team_assignments
from utils.innings import (
    outs_to_decimal_innings,
    parse_mlb_innings_to_outs,
    validate_innings_outs,
)
from utils.games_started import parse_games_started


logger = logging.getLogger(__name__)
PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE = 'pitcher_game_logs'
POSTGAME_GAME_FAILURE_ENTITY_TYPE = 'postgame_completed_game'
POSTGAME_CONTEXT_FAILURE_ENTITY_TYPE = 'postgame_completed_game_context'
POSTGAME_EARLY_MORNING_CUTOFF_HOUR = 6
FINAL_GAME_STATUS_CODES = frozenset({'F', 'O', 'FR', 'FT'})
FINAL_GAME_DETAILED_STATES = frozenset({
    'final',
    'game over',
    'completed early',
    'final: tied',
})

# ── Status file (written by the daily scheduler) ─────────────────────────────
_STATUS_DIR  = Path(__file__).resolve().parent.parent / 'logs'
STATUS_FILE  = _STATUS_DIR / 'sync_status.json'


def _ensure_logs_dir():
    _STATUS_DIR.mkdir(parents=True, exist_ok=True)


def _season_for(ref: date) -> int:
    """MLB seasons run roughly Feb–Nov. Use the calendar year of ref."""
    return ref.year


def postgame_schedule_date(now: datetime | None = None) -> date:
    """
    Resolve the MLB schedule date a postgame refresh should inspect.

    Evening GitHub Actions runs are UTC, while most MLB games complete late in
    the Eastern time window. Before the morning boundary, keep checking the
    prior baseball date so 1-3 AM ET cleanup runs do not accidentally scan the
    next empty slate.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    try:
        product_timezone = ZoneInfo(PRODUCT_TIMEZONE)
    except ZoneInfoNotFoundError:
        product_timezone = timezone.utc
    local = current.astimezone(product_timezone)
    if local.hour < POSTGAME_EARLY_MORNING_CUTOFF_HOUR:
        return local.date() - timedelta(days=1)
    return local.date()


def _status_value(game: dict, key: str):
    status = game.get('status') or {}
    return status.get(key)


def is_completed_game(game: dict) -> bool:
    """Return True for MLB schedule games that are final/completed."""
    if not (game or {}).get('gamePk'):
        return False
    status_code = str(_status_value(game, 'statusCode') or '').upper()
    detailed_state = str(_status_value(game, 'detailedState') or '').strip().lower()
    abstract_state = str(_status_value(game, 'abstractGameState') or '').strip().lower()
    return (
        status_code in FINAL_GAME_STATUS_CODES
        or abstract_state == 'final'
        or detailed_state in FINAL_GAME_DETAILED_STATES
        or detailed_state.startswith('final')
    )


def completed_games_for_postgame_refresh(schedule_date: date) -> list[dict]:
    games = mlb_client.get_schedule(
        start_date=schedule_date.isoformat(),
        end_date=schedule_date.isoformat(),
    )
    return [game for game in (games or []) if is_completed_game(game)]


def _game_pk(game: dict):
    return (game or {}).get('gamePk')


def _game_team(game: dict, side: str) -> dict:
    return (((game or {}).get('teams') or {}).get(side) or {}).get('team') or {}


def _game_team_id(game: dict, side: str):
    return _game_team(game, side).get('id')


def _game_team_name(game: dict, side: str):
    return _game_team(game, side).get('name')


def _game_date(game: dict, fallback: date) -> date:
    raw = (game or {}).get('officialDate') or str((game or {}).get('gameDate') or '')[:10]
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return fallback


def _unprocessed_completed_games(games: list[dict]) -> tuple[list[dict], int]:
    game_pks = [pk for pk in (_game_pk(game) for game in games) if pk]
    if not game_pks:
        return [], 0
    processed_pks = {
        row[0]
        for row in (
            db.session.query(PostgameProcessedGame.mlb_game_pk)
            .filter(PostgameProcessedGame.mlb_game_pk.in_(game_pks))
            .all()
        )
    }
    pending = [game for game in games if _game_pk(game) not in processed_pks]
    return pending, len(game_pks) - len(pending)


def _int_stat(stats: dict, key: str, default: int = 0) -> int:
    try:
        return int(stats.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _positive_stat(stats: dict, key: str) -> bool:
    return _int_stat(stats, key) > 0


def _pitcher_order_by_side(boxscore: dict) -> dict[str, list[int]]:
    teams = (boxscore or {}).get('teams') or {}
    return {
        side: list(((teams.get(side) or {}).get('pitchers') or []))
        for side in ('home', 'away')
    }


def _extract_pitching_lines_from_boxscore(boxscore: dict) -> list[dict]:
    pitchers = []
    for side in ('home', 'away'):
        team_data = ((boxscore or {}).get('teams') or {}).get(side) or {}
        team_info = team_data.get('team') or {}
        player_data = team_data.get('players') or {}
        for pitcher_id in team_data.get('pitchers') or []:
            player = player_data.get(f'ID{pitcher_id}') or {}
            stats = ((player.get('stats') or {}).get('pitching') or {})
            if stats:
                pitchers.append({
                    'player_id': pitcher_id,
                    'name': (player.get('person') or {}).get('fullName'),
                    'team': team_info.get('name'),
                    'team_id': team_info.get('id'),
                    'stats': stats,
                    'side': side,
                })
    return pitchers


def _line_games_started(line: dict, pitcher_order: dict[str, list[int]]) -> int:
    stats = line.get('stats') or {}
    parsed = parse_games_started(stats.get('gamesStarted'))
    if parsed is not None:
        return parsed
    side_pitchers = pitcher_order.get(line.get('side')) or []
    return 1 if side_pitchers and side_pitchers[0] == line.get('player_id') else 0


def _opponent_for_line(game: dict, line: dict, team_abbr_map: dict) -> tuple[str | None, str | None]:
    opponent_side = 'away' if line.get('side') == 'home' else 'home'
    opponent_id = _game_team_id(game, opponent_side)
    return _game_team_name(game, opponent_side), team_abbr_map.get(opponent_id)


def _ingest_boxscore_pitching_line(
    pitcher,
    line: dict,
    game: dict,
    *,
    game_date: date,
    team_abbr_map: dict,
    pitcher_order: dict[str, list[int]],
) -> bool:
    game_pk = _game_pk(game)
    if not game_pk:
        return False

    existing = GameLog.query.filter_by(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
    ).first()
    if existing:
        return False

    stats = line.get('stats') or {}
    opponent, opponent_abbreviation = _opponent_for_line(game, line, team_abbr_map)
    innings_pitched_outs = validate_innings_outs(
        parse_mlb_innings_to_outs(stats.get('inningsPitched', '0.0'))
    )
    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        game_type=(game or {}).get('gameType', 'R'),
        opponent=opponent,
        opponent_abbreviation=opponent_abbreviation,
        games_started=_line_games_started(line, pitcher_order),
        innings_pitched=outs_to_decimal_innings(innings_pitched_outs),
        innings_pitched_outs=innings_pitched_outs,
        pitches_thrown=_int_stat(stats, 'numberOfPitches'),
        strikes=_int_stat(stats, 'strikes'),
        hits_allowed=_int_stat(stats, 'hits'),
        runs_allowed=_int_stat(stats, 'runs'),
        earned_runs=_int_stat(stats, 'earnedRuns'),
        walks=_int_stat(stats, 'baseOnBalls'),
        strikeouts=_int_stat(stats, 'strikeOuts'),
        home_runs_allowed=_int_stat(stats, 'homeRuns'),
        save_situation=_positive_stat(stats, 'saveOpportunities'),
        hold=_positive_stat(stats, 'holds'),
        blown_save=_positive_stat(stats, 'blownSaves'),
        win=_positive_stat(stats, 'wins'),
        loss=_positive_stat(stats, 'losses'),
        save=_positive_stat(stats, 'saves'),
    )
    for li_key in ('leverageIndex', 'avgLeverageIndex', 'avgLI'):
        raw_li = stats.get(li_key)
        if raw_li is not None:
            try:
                log.leverage_index = float(raw_li)
            except (TypeError, ValueError):
                pass
            break
    db.session.add(log)
    return True


def process_completed_game_for_postgame_refresh(
    game: dict,
    *,
    schedule_date: date,
    sync_run_id=None,
) -> dict:
    game_pk = _game_pk(game)
    if not game_pk:
        return {
            'game_pk': None,
            'logs_added': 0,
            'pitchers_touched': 0,
            'skipped': True,
            'reason': 'missing_game_pk',
        }

    existing_marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=game_pk).first()
    if existing_marker is not None:
        return {
            'game_pk': game_pk,
            'logs_added': 0,
            'pitchers_touched': 0,
            'skipped': True,
            'reason': 'already_processed',
        }

    boxscore = mlb_client.get_game_boxscore(game_pk)
    pitching_lines = _extract_pitching_lines_from_boxscore(boxscore)
    pitcher_order = _pitcher_order_by_side(boxscore)
    player_ids = [line.get('player_id') for line in pitching_lines if line.get('player_id')]
    local_pitchers = {
        pitcher.mlb_id: pitcher
        for pitcher in (
            Pitcher.query
            .filter(Pitcher.active == True)
            .filter(Pitcher.mlb_id.in_(player_ids or [-1]))
            .all()
        )
    }
    team_abbr_map = dict(
        db.session.query(Pitcher.team_id, Pitcher.team_abbreviation)
        .filter(Pitcher.team_abbreviation.isnot(None))
        .distinct()
        .all()
    )
    game_date = _game_date(game, schedule_date)
    logs_added = 0
    touched_pitcher_ids = set()
    for line in pitching_lines:
        pitcher = local_pitchers.get(line.get('player_id'))
        if pitcher is None:
            continue
        if _ingest_boxscore_pitching_line(
            pitcher,
            line,
            game,
            game_date=game_date,
            team_abbr_map=team_abbr_map,
            pitcher_order=pitcher_order,
        ):
            logs_added += 1
            touched_pitcher_ids.add(pitcher.id)

    marker = PostgameProcessedGame(
        mlb_game_pk=game_pk,
        game_date=game_date,
        game_type=(game or {}).get('gameType'),
        home_team_id=_game_team_id(game, 'home'),
        away_team_id=_game_team_id(game, 'away'),
        final_state=_status_value(game, 'detailedState'),
        logs_added=logs_added,
        pitchers_touched=len(touched_pitcher_ids),
        sync_run_id=sync_run_id,
    )
    db.session.add(marker)
    db.session.flush()

    return {
        'game_pk': game_pk,
        'logs_added': logs_added,
        'pitchers_touched': len(touched_pitcher_ids),
        'skipped': False,
        'reason': None,
        # Passed back so completed-game context can reuse the boxscore that was
        # already fetched, without a second API call. Not persisted.
        'boxscore': boxscore,
    }


def generate_completed_game_context(
    game: dict,
    *,
    boxscore: dict | None,
    game_date: date,
) -> dict:
    """Derive and upsert per-team Completed Game Context for one completed game.

    Consumes linescore and play-by-play transiently (raw responses are never
    stored), normalizes them with the boxscore into the service payload, and
    upserts one derived row per team keyed by (team_id, game_pk). Adds rows to
    the current session but does not commit — the caller owns the transaction.

    Network failures for the optional context endpoints degrade gracefully:
    a missing linescore/play-by-play simply lowers confidence rather than
    failing the game.
    """
    game_pk = _game_pk(game)
    linescore = None
    play_by_play = None
    if game_pk:
        try:
            linescore = mlb_client.get_game_linescore(game_pk)
        except Exception as exc:  # noqa: BLE001 — optional input, degrade not fail
            logger.warning('Linescore fetch failed for game_pk=%s: %s', game_pk, exc)
        try:
            play_by_play = mlb_client.get_game_play_by_play(game_pk)
        except Exception as exc:  # noqa: BLE001 — optional input, degrade not fail
            logger.warning('Play-by-play fetch failed for game_pk=%s: %s', game_pk, exc)

    payload = build_completed_game_payload(
        game,
        boxscore=boxscore,
        linescore=linescore,
        play_by_play=play_by_play,
        game_date=game_date,
    )
    if not payload:
        return {'contexts_upserted': 0, 'confidences': [], 'reason': 'no_payload'}

    contexts = extract_completed_game_contexts(payload)
    for context in contexts:
        upsert_completed_game_context(context)
    return {
        'contexts_upserted': len(contexts),
        'confidences': [c.get('confidence') for c in contexts],
        'reason': None,
    }


def _safe_generate_completed_game_context(
    game: dict,
    *,
    boxscore: dict | None,
    schedule_date: date,
    sync_run_id=None,
    status: dict,
    run_logger,
) -> None:
    """Run completed-game context generation without ever breaking the refresh.

    Fail-closed wrapper: commits the derived rows on success; on any failure it
    rolls back only the context work (the game logs are already committed),
    records a dead-letter entry, and lets the refresh continue.
    """
    game_pk = _game_pk(game)
    try:
        result = generate_completed_game_context(
            game,
            boxscore=boxscore,
            game_date=_game_date(game, schedule_date),
        )
        db.session.commit()
        status['completed_game_contexts_upserted'] += result['contexts_upserted']
        if result['contexts_upserted']:
            run_logger.info(
                'Completed-game context for game %s: %s row(s) %s.',
                game_pk,
                result['contexts_upserted'],
                '/'.join(result['confidences']) or 'none',
            )
    except Exception as exc:  # noqa: BLE001 — context is best-effort, never fatal
        db.session.rollback()
        status['completed_game_context_errors'] += 1
        dead_letter.record_failure(
            POSTGAME_CONTEXT_FAILURE_ENTITY_TYPE,
            exc,
            entity_ref=game_pk,
            payload={
                'game_pk': game_pk,
                'schedule_date': schedule_date.isoformat(),
            },
            sync_run_id=sync_run_id,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        )
        db.session.commit()
        run_logger.warning(
            'Completed-game context failed for game_pk=%s: %s', game_pk, exc
        )


def _safe_generate_intelligence_surface_snapshot(schedule_date, *, status, run_logger):
    """Refresh the Intelligence Surface snapshot for a slate without ever
    breaking the refresh.

    Fail-closed wrapper around the homepage cache: rebuilds the stored
    GET /api/bullpen/intelligence/today response from the completed-game contexts
    just derived for ``schedule_date``. The completed-game contexts are already
    committed, so a snapshot failure here costs only a stale homepage cache (the
    endpoint falls back to live generation) and never undoes context work or
    fails the postgame refresh.
    """
    try:
        from services.intelligence_surface_snapshot import generate_snapshot_for_date

        response = generate_snapshot_for_date(
            schedule_date, source='postgame_refresh')
        status['intelligence_snapshot'] = response.get('status') or 'generated'
        run_logger.info(
            'Intelligence surface snapshot refreshed for %s: status=%s, publishable=%s.',
            schedule_date,
            response.get('status'),
            response.get('publishable_candidates'),
        )
    except Exception as exc:  # noqa: BLE001 — snapshot is best-effort, never fatal
        db.session.rollback()
        status['intelligence_snapshot'] = 'failed'
        run_logger.warning(
            'Intelligence surface snapshot failed for schedule_date=%s: %s',
            schedule_date, exc,
        )


def sync_recent_logs(
    days_back: int = 7,
    reference_date: date | None = None,
    sync_run_id=None,
    job_name=sync_metadata.JOB_DAILY_SYNC,
):
    """
    Pull recent game logs from the MLB Stats API for every active pitcher
    and insert any that aren't already in the DB.

    Partial-failure semantics: a single pitcher whose fetch fails, or a single
    malformed game-log record, is dead-lettered (recorded in sync_failures with
    enough payload to retry) and skipped — it never aborts the rest of the
    batch. ``records_failed`` counts dead-lettered entities so the caller can
    mark the run 'partial'.

    Returns a dict suitable for API response / log line:
        {
          'new_logs_added':       int,
          'pitchers_touched':     int,
          'errors':               int,
          'records_failed':       int,
          'days_back':            int,
          'season':               int,
          'cutoff':               'YYYY-MM-DD',
        }
    """
    reference_date = reference_date or date.today()
    cutoff         = reference_date - timedelta(days=days_back)
    season         = _season_for(reference_date)

    # Build a team_id -> abbreviation map from existing pitcher rows.
    # MLB's gameLog endpoint returns the opponent's id and name but NOT the
    # abbreviation, so we resolve it ourselves. Falls back to None if a team
    # somehow isn't represented in the pitchers table.
    team_abbr_map = dict(
        db.session.query(Pitcher.team_id, Pitcher.team_abbreviation)
        .filter(Pitcher.team_abbreviation.isnot(None))
        .distinct()
        .all()
    )

    pitchers        = Pitcher.query.filter_by(active=True).all()
    new_logs        = 0
    errors          = 0
    records_failed  = 0
    pitchers_touched = 0

    for pitcher in pitchers:
        try:
            splits = mlb_client.get_pitcher_game_logs(pitcher.mlb_id, season=season)
        except Exception as e:
            # A per-pitcher fetch failure is dead-lettered with enough payload
            # to retry, then skipped — the rest of the league still syncs.
            logger.warning('MLB fetch failed for %s (mlb_id=%s): %s',
                           pitcher.full_name, pitcher.mlb_id, e)
            errors += 1
            records_failed += 1
            dead_letter.record_failure(
                PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE,
                e,
                entity_ref=pitcher.mlb_id,
                payload={
                    'pitcher_id': pitcher.id,
                    'mlb_id': pitcher.mlb_id,
                    'season': season,
                    'days_back': days_back,
                },
                sync_run_id=sync_run_id,
                job_name=job_name,
            )
            continue

        dead_letter.resolve_entity_failures(
            PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE,
            pitcher.mlb_id,
            job_name=job_name,
        )

        touched_this_pitcher = False

        for split in splits or []:
            game_info     = split.get('game', {})
            game_pk       = game_info.get('gamePk')
            game_date_str = split.get('date')

            if not game_pk or not game_date_str:
                continue

            # Process one record in isolation: a single poisoned record is
            # dead-lettered and skipped rather than aborting this pitcher or the
            # whole batch.
            try:
                added = _ingest_game_log_split(
                    pitcher, split, cutoff, team_abbr_map,
                )
            except Exception as e:
                logger.warning(
                    'Malformed game-log record for %s (mlb_id=%s, game_pk=%s): %s',
                    pitcher.full_name, pitcher.mlb_id, game_pk, e,
                )
                records_failed += 1
                dead_letter.record_failure(
                    'game_log_record',
                    e,
                    entity_ref=game_pk,
                    payload={
                        'pitcher_id': pitcher.id,
                        'mlb_id': pitcher.mlb_id,
                        'game_pk': game_pk,
                        'game_date': game_date_str,
                        'season': season,
                    },
                    sync_run_id=sync_run_id,
                    job_name=job_name,
                )
                continue

            if added:
                new_logs += 1
                touched_this_pitcher = True
                time.sleep(0.1)

        if touched_this_pitcher:
            pitchers_touched += 1

    db.session.commit()

    return {
        'new_logs_added':    new_logs,
        'pitchers_touched':  pitchers_touched,
        'errors':            errors,
        'records_failed':    records_failed,
        'days_back':         days_back,
        'season':            season,
        'cutoff':            cutoff.isoformat(),
    }


def _ingest_game_log_split(pitcher, split, cutoff, team_abbr_map):
    """
    Insert a single game-log split for a pitcher.

    Returns True if a new GameLog row was added, False if the split was a
    legitimate skip (before cutoff, malformed-but-empty key, or already stored).
    Raises on a genuinely poisoned record so the caller can dead-letter it.
    """
    game_info     = split.get('game', {})
    stat          = split.get('stat', {})
    game_pk       = game_info.get('gamePk')
    game_date_str = split.get('date')
    game_type     = game_info.get('gameType', 'R')

    if not game_pk or not game_date_str:
        return False

    game_date = datetime.strptime(game_date_str, '%Y-%m-%d').date()

    if game_date < cutoff:
        return False

    existing = GameLog.query.filter_by(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
    ).first()
    if existing:
        return False

    opponent = split.get('opponent', {})
    innings_pitched_outs = validate_innings_outs(
        parse_mlb_innings_to_outs(stat.get('inningsPitched', '0.0'))
    )

    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        game_type=game_type,
        opponent=opponent.get('name'),
        opponent_abbreviation=team_abbr_map.get(opponent.get('id')),
        games_started=parse_games_started(stat.get('gamesStarted')),
        innings_pitched=outs_to_decimal_innings(innings_pitched_outs),
        innings_pitched_outs=innings_pitched_outs,
        pitches_thrown=int(stat.get('numberOfPitches', 0) or 0),
        strikes=int(stat.get('strikes', 0) or 0),
        hits_allowed=int(stat.get('hits', 0) or 0),
        runs_allowed=int(stat.get('runs', 0) or 0),
        earned_runs=int(stat.get('earnedRuns', 0) or 0),
        walks=int(stat.get('baseOnBalls', 0) or 0),
        strikeouts=int(stat.get('strikeOuts', 0) or 0),
        home_runs_allowed=int(stat.get('homeRuns', 0) or 0),
        save_situation=stat.get('saveOpportunities', 0) > 0,
        hold=stat.get('holds', 0) > 0,
        blown_save=stat.get('blownSaves', 0) > 0,
        win=stat.get('wins', 0) > 0,
        loss=stat.get('losses', 0) > 0,
        save=stat.get('saves', 0) > 0,
    )
    db.session.add(log)

    # Backfill leverage index from the boxscore. A failed call or a missing LI
    # field just leaves the column as None — never crash the sync.
    try:
        pitching_lines = mlb_client.get_game_pitching_lines(game_pk)
    except Exception as e:
        logger.warning('Boxscore fetch failed for game_pk=%s: %s', game_pk, e)
        pitching_lines = []

    for line in pitching_lines or []:
        if line.get('player_id') == pitcher.mlb_id:
            stats_block = line.get('stats') or {}
            for li_key in ('leverageIndex', 'avgLeverageIndex', 'avgLI'):
                raw_li = stats_block.get(li_key)
                if raw_li is not None:
                    try:
                        log.leverage_index = float(raw_li)
                    except (TypeError, ValueError):
                        pass
                    break
            break

    return True


def recalculate_all_fatigue(reference_date: date | None = None):
    """
    Recalculate fatigue scores for every active pitcher against a SINGLE
    canonical availability reference date — the latest completed MLB workload
    date + 1 day ("tonight's availability"), resolved by
    ``sync_metadata.canonical_fatigue_reference_date``.

    This is the one production authority. The scheduled APScheduler sync, the
    GitHub Actions / manual sync endpoint, and the recalculate endpoint all flow
    through here, so the same game logs always yield the same fatigue scores no
    matter which path last ran. It replaces the previous split where the daily
    job scored each pitcher at their own last game date while the sync endpoint
    scored against the host's runtime "today" — a divergence that let one
    database tell two different league-wide stories.

    Pass ``reference_date`` only to pin the anchor explicitly (e.g. in tests);
    production callers leave it None so the canonical date is derived from
    durable workload metadata. Returns the count of pitchers updated.
    """
    ref = sync_metadata.canonical_fatigue_reference_date(reference_date)
    if ref is None:
        # No workload data at all → nothing to anchor against.
        return 0

    window_start = ref - timedelta(days=14)
    pitchers = Pitcher.query.filter_by(active=True).all()
    failed_fetch_refs = {
        row[0]
        for row in (
            db.session.query(SyncFailure.entity_ref)
            .filter(SyncFailure.entity_type == PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE)
            .filter(SyncFailure.resolved.is_(False))
            .all()
        )
    }
    updated  = 0

    for pitcher in pitchers:
        if str(pitcher.mlb_id) in failed_fetch_refs:
            continue
        logs = (
            GameLog.query
            .filter(
                GameLog.pitcher_id == pitcher.id,
                GameLog.game_date  >= window_start,
                GameLog.game_date  <= ref,
            )
            .order_by(desc(GameLog.game_date))
            .all()
        )
        if not logs:
            continue

        score = calculate_fatigue(pitcher, logs, reference_date=ref)
        db.session.add(score)
        updated += 1

    db.session.commit()
    return updated


def record_sync_error_details(
    entity_type,
    error_details,
    sync_run_id=None,
    job_name=sync_metadata.JOB_DAILY_SYNC,
):
    """Persist fetch-domain error details from sub-syncs as dead letters."""
    count = 0
    for detail in error_details or []:
        payload = dict(detail)
        entity_ref = (
            payload.get('pitcher_mlb_id')
            or payload.get('team_id')
            or payload.get('source')
        )
        failure = dead_letter.record_failure(
            entity_type,
            payload.get('error') or 'MLB API fetch failed',
            entity_ref=entity_ref,
            payload=payload,
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        if failure is not None:
            count += 1
    return count


def complete_sync_run_with_snapshot(
    sync_run_id,
    *,
    final_status,
    completed_at=None,
    records_processed=0,
    records_failed=0,
    new_logs_added=0,
    pitchers_updated=0,
    errors=0,
    api_calls_made=0,
    retries_used=0,
    error_message=None,
    source=sync_metadata.SOURCE_MANUAL,
    started_at=None,
    snapshot_source='sync_completion',
    job_name=sync_metadata.JOB_DAILY_SYNC,
):
    from services import dashboard_snapshot as dashboard_snapshot_service

    completed_at = completed_at or datetime.now(timezone.utc).replace(tzinfo=None)
    sync_metadata.set_sync_stage(
        sync_run_id,
        sync_metadata.STAGE_DASHBOARD_SNAPSHOT,
    )
    try:
        run = sync_metadata.finish_sync_run(
            sync_run_id,
            status=final_status,
            completed_at=completed_at,
            records_processed=records_processed,
            records_failed=records_failed,
            new_logs_added=new_logs_added,
            pitchers_updated=pitchers_updated,
            errors=errors,
            api_calls_made=api_calls_made,
            retries_used=retries_used,
            error_message=error_message,
            source=source,
            started_at=started_at,
            job_name=job_name,
            stage=sync_metadata.STAGE_DASHBOARD_SNAPSHOT,
            commit=False,
            rollback_before=False,
        )
        snapshot = dashboard_snapshot_service.build_bullpen_dashboard_snapshot(
            sync_run_id=run.id if run is not None else sync_run_id,
            source=snapshot_source,
            publish=True,
            commit=False,
            raise_errors=True,
        )
        if run is not None:
            run.stage = sync_metadata.STAGE_PUBLISHED
            run.published_dashboard_snapshot_id = snapshot.id
        db.session.commit()
        return run, snapshot
    except Exception as exc:
        db.session.rollback()
        sync_metadata.finish_sync_run(
            sync_run_id,
            status=sync_metadata.STATUS_FAILED,
            completed_at=completed_at,
            records_processed=records_processed,
            records_failed=records_failed,
            new_logs_added=new_logs_added,
            pitchers_updated=pitchers_updated,
            errors=(errors or 0) + 1,
            api_calls_made=api_calls_made,
            retries_used=retries_used,
            error_message=str(exc),
            source=source,
            started_at=started_at,
            job_name=job_name,
            stage=sync_metadata.STAGE_FAILED,
            failed_stage=sync_metadata.STAGE_DASHBOARD_SNAPSHOT,
        )
        raise


def run_postgame_refresh(
    app,
    schedule_date: date | None = None,
    source: str = sync_metadata.SOURCE_GITHUB_ACTIONS,
):
    """
    Lightweight completed-game refresh.

    This job checks one MLB schedule date, finds completed games not yet marked
    as processed, fetches only those games' boxscores, and ingests pitching
    lines for tracked active pitchers. It leaves the full morning sync path
    intact: no roster refresh, no full-league game-log sweep.
    """
    _ensure_logs_dir()
    log_file = _STATUS_DIR / 'postgame_refresh.log'
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s  %(levelname)-7s  %(message)s'
    ))
    run_logger = logging.getLogger('baseballos.postgame_refresh')
    if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == str(log_file)
               for h in run_logger.handlers):
        run_logger.addHandler(file_handler)
    run_logger.setLevel(logging.INFO)

    started_at = datetime.now(timezone.utc)
    schedule_date = schedule_date or postgame_schedule_date(started_at)
    sync_run_id = None
    status = {
        'last_sync': started_at.isoformat(),
        'status': sync_metadata.STATUS_SUCCESS,
        'job_name': sync_metadata.JOB_POSTGAME_REFRESH,
        'schedule_date': schedule_date.isoformat(),
        'completed_games_found': 0,
        'newly_completed_games': 0,
        'games_already_processed': 0,
        'games_processed': 0,
        'new_logs_added': 0,
        'pitchers_touched': 0,
        'pitchers_updated': 0,
        'errors': 0,
        'records_failed': 0,
        'completed_game_contexts_upserted': 0,
        'completed_game_context_errors': 0,
        'intelligence_snapshot': 'skipped',
        'message': '',
    }
    run_logger.info('── Postgame refresh starting (schedule_date=%s) ──', schedule_date)

    try:
        with app.app_context():
            sync_run_id = sync_metadata.start_sync_run(
                source=source,
                started_at=started_at.replace(tzinfo=None),
                job_name=sync_metadata.JOB_POSTGAME_REFRESH,
            )
            mlb_client.metrics.reset()
            sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_LOG_INGESTION)

            completed_games = completed_games_for_postgame_refresh(schedule_date)
            unprocessed_games, already_processed = _unprocessed_completed_games(completed_games)
            status['completed_games_found'] = len(completed_games)
            status['newly_completed_games'] = len(unprocessed_games)
            status['games_already_processed'] = already_processed
            run_logger.info(
                'Found %s completed game(s); %s already processed, %s pending.',
                len(completed_games),
                already_processed,
                len(unprocessed_games),
            )

            for game in unprocessed_games:
                game_pk = _game_pk(game)
                try:
                    result = process_completed_game_for_postgame_refresh(
                        game,
                        schedule_date=schedule_date,
                        sync_run_id=sync_run_id,
                    )
                    db.session.commit()
                    if result.get('skipped'):
                        continue
                    status['games_processed'] += 1
                    status['new_logs_added'] += result['logs_added']
                    status['pitchers_touched'] += result['pitchers_touched']
                    run_logger.info(
                        'Processed completed game %s: %s log(s), %s pitcher(s).',
                        game_pk,
                        result['logs_added'],
                        result['pitchers_touched'],
                    )
                    # Derive completed-game context in its own transaction so a
                    # context failure can never undo the committed game logs.
                    _safe_generate_completed_game_context(
                        game,
                        boxscore=result.get('boxscore'),
                        schedule_date=schedule_date,
                        sync_run_id=sync_run_id,
                        status=status,
                        run_logger=run_logger,
                    )
                except Exception as exc:
                    db.session.rollback()
                    status['errors'] += 1
                    status['records_failed'] += 1
                    dead_letter.record_failure(
                        POSTGAME_GAME_FAILURE_ENTITY_TYPE,
                        exc,
                        entity_ref=game_pk,
                        payload={
                            'game_pk': game_pk,
                            'schedule_date': schedule_date.isoformat(),
                            'status': game.get('status') if isinstance(game, dict) else None,
                        },
                        sync_run_id=sync_run_id,
                        job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                    )
                    db.session.commit()
                    run_logger.warning('Postgame processing failed for game_pk=%s: %s', game_pk, exc)

            if status['new_logs_added'] > 0:
                sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_FATIGUE_RECALCULATION)
                pitchers_updated = recalculate_all_fatigue()
                status['pitchers_updated'] = pitchers_updated
                run_logger.info('Recalculated fatigue for %s pitchers', pitchers_updated)

            # Refresh the Intelligence Surface homepage cache from the freshly
            # derived contexts. Best-effort: it never blocks or fails the refresh.
            if status['completed_game_contexts_upserted'] > 0:
                _safe_generate_intelligence_surface_snapshot(
                    schedule_date, status=status, run_logger=run_logger)

            if status['records_failed']:
                status['status'] = (
                    sync_metadata.STATUS_FAILED
                    if status['games_processed'] == 0 and status['newly_completed_games'] > 0
                    else sync_metadata.STATUS_PARTIAL
                )
                status['message'] = (
                    f"{status['records_failed']} completed game(s) could not be processed."
                )
            elif status['new_logs_added'] > 0:
                status['message'] = 'Updated after completed games.'
            elif status['newly_completed_games'] == 0:
                status['message'] = 'No newly completed games to process.'
            else:
                status['message'] = 'Completed games were checked; no tracked pitcher workload changed.'

            api_metrics = mlb_client.metrics.snapshot()
            if status['new_logs_added'] > 0:
                completed_run, snapshot = complete_sync_run_with_snapshot(
                    sync_run_id,
                    final_status=status['status'],
                    records_processed=status['new_logs_added'],
                    records_failed=status['records_failed'],
                    new_logs_added=status['new_logs_added'],
                    pitchers_updated=status['pitchers_updated'],
                    errors=status['errors'],
                    api_calls_made=api_metrics['api_calls'],
                    retries_used=api_metrics['retries'],
                    error_message=status['message'] or None,
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    snapshot_source='postgame_refresh',
                    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                )
                status['dashboard_snapshot_id'] = snapshot.id
            else:
                sync_metadata.finish_sync_run(
                    sync_run_id,
                    status=status['status'],
                    records_processed=0,
                    records_failed=status['records_failed'],
                    new_logs_added=0,
                    pitchers_updated=0,
                    errors=status['errors'],
                    api_calls_made=api_metrics['api_calls'],
                    retries_used=api_metrics['retries'],
                    error_message=status['message'] or None,
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                    stage=(
                        sync_metadata.STAGE_FAILED
                        if status['status'] == sync_metadata.STATUS_FAILED
                        else sync_metadata.STAGE_PUBLISHED
                    ),
                )
    except Exception as e:
        status['status'] = sync_metadata.STATUS_FAILED
        status['message'] = str(e)
        status['errors'] = max(1, status.get('errors', 0))
        run_logger.exception('Postgame refresh failed: %s', e)
        try:
            api_metrics = mlb_client.metrics.snapshot()
        except Exception:
            api_metrics = {'api_calls': 0, 'retries': 0}
        with app.app_context():
            existing_run = db.session.get(SyncRun, sync_run_id) if sync_run_id else None
            if existing_run is None or existing_run.status != sync_metadata.STATUS_FAILED:
                sync_metadata.finish_sync_run(
                    sync_run_id,
                    status=sync_metadata.STATUS_FAILED,
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    errors=status['errors'],
                    api_calls_made=api_metrics['api_calls'],
                    retries_used=api_metrics['retries'],
                    error_message=str(e),
                    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                    stage=sync_metadata.STAGE_FAILED,
                    failed_stage=existing_run.stage if existing_run is not None else None,
                )

    status['finished_at'] = datetime.now(timezone.utc).isoformat()
    write_status(status)
    run_logger.info('── Postgame refresh finished: %s ──', status['status'])
    run_logger.removeHandler(file_handler)
    file_handler.close()
    return status


def run_daily_sync(app, days_back: int = 7, source: str = sync_metadata.SOURCE_SCHEDULED):
    """
    Full daily refresh — pulls new logs, recalculates fatigue using each
    pitcher's last game date, and records durable sync_runs metadata for
    /api/bullpen/sync/status.

    Safe to call repeatedly. Gracefully handles the offseason (when MLB
    returns no recent games) by writing a status of 'no_games' instead
    of raising.

    Meant to run inside an app context — we push one here if needed.
    """
    _ensure_logs_dir()
    log_file = _STATUS_DIR / 'daily_sync.log'

    # File-based logger so the schedule leaves an audit trail even if the
    # process is headless (APScheduler background thread).
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s  %(levelname)-7s  %(message)s'
    ))
    run_logger = logging.getLogger('baseballos.daily_sync')
    # Avoid stacking handlers across repeated runs.
    if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == str(log_file)
               for h in run_logger.handlers):
        run_logger.addHandler(file_handler)
    run_logger.setLevel(logging.INFO)

    started_at = datetime.now(timezone.utc)
    sync_run_id = None
    run_logger.info('── Daily sync starting (days_back=%s) ──', days_back)

    status = {
        'last_sync':        started_at.isoformat(),
        'status':           sync_metadata.STATUS_SUCCESS,
        'pitchers_updated': 0,
        'new_logs_added':   0,
        'errors':           0,
        'message':          '',
    }

    try:
        with app.app_context():
            sync_run_id = sync_metadata.start_sync_run(
                source=source,
                started_at=started_at.replace(tzinfo=None),
            )
            # Fresh API metrics for this run so api_calls_made / retries_used
            # reflect only this sync's activity.
            mlb_client.metrics.reset()
            sync_metadata.set_sync_stage(
                sync_run_id,
                sync_metadata.STAGE_TEAM_ASSIGNMENTS,
            )
            team_assignment = sync_team_assignments()
            team_assignment_records_failed = record_sync_error_details(
                'team_assignment_fetch',
                team_assignment.get('error_details'),
                sync_run_id=sync_run_id,
            )
            run_logger.info(
                'Refreshed team assignment for %s pitchers (%s changed, %s reassigned, %s no org, %s unknown, %s errors)',
                team_assignment['pitchers_refreshed'],
                team_assignment['pitchers_changed'],
                team_assignment['reassigned_count'],
                team_assignment['no_organization_count'],
                team_assignment['unknown_count'],
                team_assignment['errors'],
            )
            sync_metadata.set_sync_stage(
                sync_run_id,
                sync_metadata.STAGE_ROSTER_STATUS,
            )
            roster = sync_roster_statuses()
            roster_records_failed = record_sync_error_details(
                'roster_status_fetch',
                roster.get('error_details'),
                sync_run_id=sync_run_id,
            )
            run_logger.info(
                'Refreshed roster status for %s pitchers (%s changed, %s unknown, %s errors)',
                roster['pitchers_refreshed'],
                roster['pitchers_changed'],
                roster['unknown_count'],
                roster['errors'],
            )
            sync_metadata.set_sync_stage(
                sync_run_id,
                sync_metadata.STAGE_LOG_INGESTION,
            )
            pull = sync_recent_logs(days_back=days_back, sync_run_id=sync_run_id)
            run_logger.info(
                'Pulled %s new logs (touched %s pitchers, %s errors, %s dead-lettered)',
                pull['new_logs_added'], pull['pitchers_touched'], pull['errors'],
                pull['records_failed'],
            )
            records_failed = (
                pull['records_failed']
                + team_assignment_records_failed
                + roster_records_failed
            )
            status['new_logs_added'] = pull['new_logs_added']
            status['records_failed'] = records_failed
            status['errors']         = pull['errors'] + roster['errors'] + team_assignment['errors']
            status['team_assignments_refreshed'] = team_assignment['pitchers_refreshed']
            status['team_assignments_changed'] = team_assignment['pitchers_changed']
            status['team_assignments_reassigned'] = team_assignment['reassigned_count']
            status['team_assignment_no_organization'] = team_assignment['no_organization_count']
            status['team_assignment_unknown'] = team_assignment['unknown_count']
            status['roster_statuses_refreshed'] = roster['pitchers_refreshed']
            status['roster_statuses_changed'] = roster['pitchers_changed']
            status['roster_status_unknown'] = roster['unknown_count']

            if pull['new_logs_added'] == 0 and pull['pitchers_touched'] == 0:
                # Nothing to score against that's new — treat as offseason if
                # we also have no recent logs anywhere in the DB window.
                recent_any = GameLog.query.filter(
                    GameLog.game_date >= (date.today() - timedelta(days=days_back))
                ).first()
                if recent_any is None:
                    status['message'] = 'No games found — offseason skip.'
                    run_logger.info('No games found — offseason skip.')

            sync_metadata.set_sync_stage(
                sync_run_id,
                sync_metadata.STAGE_FATIGUE_RECALCULATION,
            )
            pitchers_updated = recalculate_all_fatigue()
            status['pitchers_updated'] = pitchers_updated
            run_logger.info('Recalculated fatigue for %s pitchers', pitchers_updated)

            sync_metadata.set_sync_stage(
                sync_run_id,
                sync_metadata.STAGE_BACKTEST_REFRESH,
            )
            try:
                from services.availability_backtest import refresh_availability_backtest
                backtest = refresh_availability_backtest()
                status['availability_backtest_status'] = backtest.get('status')
                status['availability_backtest_computed_at'] = backtest.get('computed_at')
                run_logger.info(
                    'Refreshed availability backtest (%s)',
                    backtest.get('computed_at') or backtest.get('status'),
                )
            except Exception as exc:
                db.session.rollback()
                status['availability_backtest_status'] = 'failed'
                status['availability_backtest_error'] = str(exc)
                run_logger.warning('Availability backtest refresh failed: %s', exc)

            # Partial when records were dead-lettered but the run still
            # refreshed its domains; otherwise success.
            final_status = (
                sync_metadata.STATUS_PARTIAL if records_failed
                else sync_metadata.STATUS_SUCCESS
            )
            status['status'] = final_status
            if records_failed and not status['message']:
                status['message'] = (
                    f'{records_failed} record(s) dead-lettered; see sync_failures.'
                )
            api_metrics = mlb_client.metrics.snapshot()
            completed_run, snapshot = complete_sync_run_with_snapshot(
                sync_run_id,
                final_status=final_status,
                records_processed=pull['new_logs_added'],
                records_failed=records_failed,
                new_logs_added=pull['new_logs_added'],
                pitchers_updated=pitchers_updated,
                errors=pull['errors'] + roster['errors'] + team_assignment['errors'],
                api_calls_made=api_metrics['api_calls'],
                retries_used=api_metrics['retries'],
                error_message=status['message'] or None,
                source=source,
                started_at=started_at.replace(tzinfo=None),
                snapshot_source='scheduled_sync',
            )
            status['dashboard_snapshot_id'] = snapshot.id
    except Exception as e:
        status['status']  = sync_metadata.STATUS_FAILED
        status['message'] = str(e)
        run_logger.exception('Daily sync failed: %s', e)
        # Snapshot whatever API activity occurred before the crash so a failed
        # run still records its retry pressure.
        try:
            api_metrics = mlb_client.metrics.snapshot()
        except Exception:
            api_metrics = {'api_calls': 0, 'retries': 0}
        with app.app_context():
            existing_run = db.session.get(SyncRun, sync_run_id) if sync_run_id else None
            if existing_run is None or existing_run.status != sync_metadata.STATUS_FAILED:
                sync_metadata.finish_sync_run(
                    sync_run_id,
                    status=sync_metadata.STATUS_FAILED,
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    errors=1,
                    api_calls_made=api_metrics['api_calls'],
                    retries_used=api_metrics['retries'],
                    error_message=str(e),
                    stage=sync_metadata.STAGE_FAILED,
                    failed_stage=existing_run.stage if existing_run is not None else None,
                )

    status['finished_at'] = datetime.now(timezone.utc).isoformat()

    write_status(status)

    run_logger.info('── Daily sync finished: %s ──', status['status'])
    # Detach the handler so it doesn't leak on the next run.
    run_logger.removeHandler(file_handler)
    file_handler.close()

    return status

def write_status(status: dict) -> None:
    """
    Persist a diagnostic sync status dict to STATUS_FILE.

    Public freshness reporting reads durable sync_runs metadata instead of this
    local cache file.
    """
    # Best-effort cache only. This file must NEVER gate the durable sync_runs
    # write — a read-only filesystem (mkdir/open failure) here is non-fatal and
    # is swallowed so it can never break or precede the durable record.
    try:
        _ensure_logs_dir()
        with open(STATUS_FILE, 'w', encoding='utf-8') as fh:
            json.dump(status, fh, indent=2)
    except OSError as e:
        # Non-fatal — sync itself succeeded, we just couldn't persist the cache.
        logging.getLogger('baseballos.sync').warning(
            'Could not write status file: %s', e
        )

def read_status():
    """Return the most recent sync status, or a sentinel if none exists."""
    if not STATUS_FILE.exists():
        return {
            'last_sync':        None,
            'pitchers_updated': 0,
            'status':           'never',
            'message':          'No sync has run yet.',
        }
    try:
        with open(STATUS_FILE, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        return {
            'last_sync':        None,
            'pitchers_updated': 0,
            'status':           'error',
            'message':          f'Could not read status file: {e}',
        }
