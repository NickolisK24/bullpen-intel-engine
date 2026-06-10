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

from sqlalchemy import desc

from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from services import sync_metadata
from services.fatigue import calculate_fatigue
from services.mlb_api import mlb_client
from services.roster_status_sync import sync_roster_statuses
from services.team_assignment_sync import sync_team_assignments


logger = logging.getLogger(__name__)

# ── Status file (written by the daily scheduler) ─────────────────────────────
_STATUS_DIR  = Path(__file__).resolve().parent.parent / 'logs'
STATUS_FILE  = _STATUS_DIR / 'sync_status.json'


def _ensure_logs_dir():
    _STATUS_DIR.mkdir(parents=True, exist_ok=True)


def _season_for(ref: date) -> int:
    """MLB seasons run roughly Feb–Nov. Use the calendar year of ref."""
    return ref.year


def sync_recent_logs(days_back: int = 7, reference_date: date | None = None):
    """
    Pull recent game logs from the MLB Stats API for every active pitcher
    and insert any that aren't already in the DB.

    Returns a dict suitable for API response / log line:
        {
          'new_logs_added':       int,
          'pitchers_touched':     int,
          'errors':               int,
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
    pitchers_touched = 0

    for pitcher in pitchers:
        try:
            splits = mlb_client.get_pitcher_game_logs(pitcher.mlb_id, season=season)
        except Exception as e:
            logger.warning('MLB fetch failed for %s (mlb_id=%s): %s',
                           pitcher.full_name, pitcher.mlb_id, e)
            errors += 1
            continue

        touched_this_pitcher = False

        for split in splits or []:
            game_info     = split.get('game', {})
            stat          = split.get('stat', {})
            game_pk       = game_info.get('gamePk')
            game_date_str = split.get('date')
            game_type     = game_info.get('gameType', 'R')

            if not game_pk or not game_date_str:
                continue

            try:
                game_date = datetime.strptime(game_date_str, '%Y-%m-%d').date()
            except ValueError:
                continue

            if game_date < cutoff:
                continue

            existing = GameLog.query.filter_by(
                pitcher_id=pitcher.id,
                mlb_game_pk=game_pk,
            ).first()
            if existing:
                continue

            opponent = split.get('opponent', {})

            log = GameLog(
                pitcher_id=pitcher.id,
                mlb_game_pk=game_pk,
                game_date=game_date,
                game_type=game_type,
                opponent=opponent.get('name'),
                opponent_abbreviation=team_abbr_map.get(opponent.get('id')),
                games_started=int(stat.get('gamesStarted', 0) or 0),
                innings_pitched=float(stat.get('inningsPitched', 0) or 0),
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
            new_logs += 1
            touched_this_pitcher = True

            # Backfill leverage index from the boxscore. A failed call or a
            # missing LI field just leaves the column as None — never crash
            # the sync. Sleep briefly so we don't hammer the MLB API.
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

            time.sleep(0.1)

        if touched_this_pitcher:
            pitchers_touched += 1

    db.session.commit()

    return {
        'new_logs_added':    new_logs,
        'pitchers_touched':  pitchers_touched,
        'errors':            errors,
        'days_back':         days_back,
        'season':            season,
        'cutoff':            cutoff.isoformat(),
    }


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
    updated  = 0

    for pitcher in pitchers:
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


def run_daily_sync(app, days_back: int = 7):
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
                source=sync_metadata.SOURCE_SCHEDULED,
                started_at=started_at.replace(tzinfo=None),
            )
            team_assignment = sync_team_assignments()
            run_logger.info(
                'Refreshed team assignment for %s pitchers (%s changed, %s reassigned, %s no org, %s unknown, %s errors)',
                team_assignment['pitchers_refreshed'],
                team_assignment['pitchers_changed'],
                team_assignment['reassigned_count'],
                team_assignment['no_organization_count'],
                team_assignment['unknown_count'],
                team_assignment['errors'],
            )
            roster = sync_roster_statuses()
            run_logger.info(
                'Refreshed roster status for %s pitchers (%s changed, %s unknown, %s errors)',
                roster['pitchers_refreshed'],
                roster['pitchers_changed'],
                roster['unknown_count'],
                roster['errors'],
            )
            pull = sync_recent_logs(days_back=days_back)
            run_logger.info(
                'Pulled %s new logs (touched %s pitchers, %s errors)',
                pull['new_logs_added'], pull['pitchers_touched'], pull['errors'],
            )
            status['new_logs_added'] = pull['new_logs_added']
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

            pitchers_updated = recalculate_all_fatigue()
            status['pitchers_updated'] = pitchers_updated
            run_logger.info('Recalculated fatigue for %s pitchers', pitchers_updated)
            sync_metadata.finish_sync_run(
                sync_run_id,
                status=sync_metadata.STATUS_SUCCESS,
                records_processed=pull['new_logs_added'],
                new_logs_added=pull['new_logs_added'],
                pitchers_updated=pitchers_updated,
                errors=pull['errors'] + roster['errors'] + team_assignment['errors'],
                error_message=status['message'] or None,
                source=sync_metadata.SOURCE_SCHEDULED,
                started_at=started_at.replace(tzinfo=None),
            )

    except Exception as e:
        status['status']  = sync_metadata.STATUS_FAILED
        status['message'] = str(e)
        run_logger.exception('Daily sync failed: %s', e)
        with app.app_context():
            sync_metadata.finish_sync_run(
                sync_run_id,
                status=sync_metadata.STATUS_FAILED,
                source=sync_metadata.SOURCE_SCHEDULED,
                started_at=started_at.replace(tzinfo=None),
                errors=1,
                error_message=str(e),
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
