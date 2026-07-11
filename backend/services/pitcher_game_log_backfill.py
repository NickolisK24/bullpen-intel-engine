from __future__ import annotations

from datetime import date

from models.game_log import GameLog
from models.pitcher import Pitcher
from services import pitcher_season_ledger_coverage
from services import sync as sync_service
from services.mlb_api import mlb_client
from utils.db import db


JOB_NAME = 'pitcher_game_log_backfill'
DEFAULT_SOURCE = 'starter_assignment_coverage'


def backfill_pitcher_game_logs(
    *,
    season: int,
    through_date: date,
    source: str = DEFAULT_SOURCE,
    apply: bool = False,
    pitcher_mlb_id: int | None = None,
    limit: int | None = None,
    session=None,
    client=mlb_client,
) -> dict:
    session = session or db.session
    query = session.query(Pitcher).order_by(Pitcher.id)
    if pitcher_mlb_id is not None:
        query = query.filter(Pitcher.mlb_id == int(pitcher_mlb_id))
    pitchers = query.all()
    if limit is not None:
        pitchers = pitchers[:int(limit)]

    season_opening = date(int(season), 1, 1)
    totals = {
        'mode': 'apply' if apply else 'dry_run',
        'season': int(season),
        'through_date': through_date.isoformat(),
        'source': source,
        'pitchers_total': len(pitchers),
        'pitchers_processed': 0,
        'fetch_failures': 0,
        'records_inserted': 0,
        'records_corrected': 0,
        'records_unchanged': 0,
        'records_skipped': 0,
        'records_failed': 0,
        'coverage_records_upserted': 0,
        'coverage_records_complete': 0,
        'coverage_records_incomplete': 0,
    }

    for pitcher in pitchers:
        try:
            splits = client.get_pitcher_game_logs(pitcher.mlb_id, season=season)
        except Exception:
            totals['fetch_failures'] += 1
            totals['records_failed'] += 1
            if apply:
                session.rollback()
            continue

        existing_by_key = {
            (row.pitcher_id, row.mlb_game_pk): row
            for row in (
                session.query(GameLog)
                .filter(
                    GameLog.pitcher_id == pitcher.id,
                    GameLog.game_date >= season_opening,
                    GameLog.game_date <= through_date,
                )
                .all()
            )
        }
        finality_cache = {}
        pitching_lines_cache = {}
        for split in splits or []:
            if not _split_in_scope(split, through_date=through_date):
                totals['records_skipped'] += 1
                continue
            try:
                result = sync_service._ingest_game_log_split(
                    pitcher,
                    split,
                    season_opening,
                    _team_abbr_map(session),
                    finality_cache=finality_cache,
                    existing_by_key=existing_by_key,
                    pitching_lines_cache=pitching_lines_cache,
                    job_name=JOB_NAME,
                    correction_source=source,
                )
            except Exception:
                totals['records_failed'] += 1
                continue
            status = result.get('status')
            if status == 'inserted':
                totals['records_inserted'] += 1
            elif status == 'corrected':
                totals['records_corrected'] += 1
            elif status == 'unchanged':
                totals['records_unchanged'] += 1
            elif status in ('unsafe', 'unresolved_finality'):
                totals['records_failed'] += 1
            else:
                totals['records_skipped'] += 1

        coverage = pitcher_season_ledger_coverage.reconcile_pitcher_season_coverage(
            pitcher,
            splits,
            season=season,
            through_date=through_date,
            finality_cache=finality_cache,
        )
        totals['coverage_records_upserted'] += coverage['coverage_records_upserted']
        totals['coverage_records_complete'] += coverage['coverage_records_complete']
        totals['coverage_records_incomplete'] += coverage['coverage_records_incomplete']
        totals['pitchers_processed'] += 1

        if apply:
            session.commit()

    if not apply:
        session.rollback()
    return totals


def _team_abbr_map(session):
    return dict(
        session.query(Pitcher.team_id, Pitcher.team_abbreviation)
        .filter(Pitcher.team_abbreviation.isnot(None))
        .distinct()
        .all()
    )


def _split_in_scope(split, *, through_date: date) -> bool:
    game_info = split.get('game') or {}
    if (game_info.get('gameType') or 'R') != 'R':
        return False
    try:
        game_date = date.fromisoformat(str(split.get('date')))
    except (TypeError, ValueError):
        return True
    return game_date <= through_date
