from __future__ import annotations

import json
from pathlib import Path

from models.game_log import GameLog
from models.pitcher import Pitcher
from services import dead_letter
from services.mlb_api import mlb_client
from utils.games_started import InvalidGamesStartedValue, parse_games_started
from utils.db import db


DEFAULT_CHECKPOINT_PATH = (
    Path(__file__).resolve().parents[1]
    / 'logs'
    / 'games_started_backfill_checkpoint.json'
)
JOB_NAME = 'games_started_backfill'


def _load_checkpoint(path):
    path = Path(path)
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return set()
    return {int(value) for value in payload.get('completed_pitcher_ids', [])}


def _write_checkpoint(path, completed):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'completed_pitcher_ids': sorted(int(value) for value in completed),
    }
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _null_rows_for_pitcher(session, pitcher_id):
    return (
        session.query(GameLog)
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.games_started.is_(None),
        )
        .order_by(GameLog.game_date, GameLog.mlb_game_pk)
        .all()
    )


def _candidate_pitchers(session):
    return (
        session.query(Pitcher)
        .join(GameLog, GameLog.pitcher_id == Pitcher.id)
        .filter(GameLog.games_started.is_(None))
        .distinct()
        .order_by(Pitcher.id)
        .all()
    )


def _game_started_map(splits):
    mapped = {}
    invalid = []
    for split in splits or []:
        game_pk = (split.get('game') or {}).get('gamePk')
        if game_pk is None:
            continue
        stat = split.get('stat') or {}
        if 'gamesStarted' not in stat:
            continue
        try:
            value = parse_games_started(stat.get('gamesStarted'))
        except InvalidGamesStartedValue as exc:
            invalid.append({'game_pk': game_pk, 'error': str(exc)})
            continue
        if value is not None:
            mapped[int(game_pk)] = value
    return mapped, invalid


def backfill_games_started(
    *,
    session=None,
    client=mlb_client,
    checkpoint_path=DEFAULT_CHECKPOINT_PATH,
    apply=False,
    limit=None,
):
    session = session or db.session
    completed = _load_checkpoint(checkpoint_path)
    total_null_before = (
        session.query(db.func.count(GameLog.id))
        .filter(GameLog.games_started.is_(None))
        .scalar()
        or 0
    )
    pitchers = _candidate_pitchers(session)
    if limit is not None:
        pitchers = pitchers[:int(limit)]

    rows_resolved = 0
    rows_unresolved = 0
    rows_examined = 0
    pitchers_processed = 0
    pitchers_skipped_checkpoint = 0
    fetch_failures = []
    invalid_values = []

    for pitcher in pitchers:
        if pitcher.id in completed:
            pitchers_skipped_checkpoint += 1
            continue

        rows = _null_rows_for_pitcher(session, pitcher.id)
        if not rows:
            completed.add(pitcher.id)
            if apply:
                _write_checkpoint(checkpoint_path, completed)
            continue

        pitchers_processed += 1
        rows_examined += len(rows)
        seasons = sorted({row.game_date.year for row in rows if row.game_date is not None})
        by_game_pk = {}
        failed = False

        for season in seasons:
            try:
                splits = client.get_pitcher_game_logs(pitcher.mlb_id, season=season)
            except Exception as exc:
                failed = True
                fetch_failures.append({
                    'pitcher_id': pitcher.id,
                    'mlb_id': pitcher.mlb_id,
                    'season': season,
                    'error': str(exc),
                })
                if apply:
                    dead_letter.record_failure(
                        'games_started_backfill_pitcher',
                        exc,
                        entity_ref=pitcher.mlb_id,
                        payload={
                            'pitcher_id': pitcher.id,
                            'mlb_id': pitcher.mlb_id,
                            'season': season,
                        },
                        job_name=JOB_NAME,
                    )
                    session.commit()
                break

            mapped, invalid = _game_started_map(splits)
            by_game_pk.update(mapped)
            if invalid:
                invalid_values.extend([
                    {
                        'pitcher_id': pitcher.id,
                        'mlb_id': pitcher.mlb_id,
                        'season': season,
                        **item,
                    }
                    for item in invalid
                ])

        if failed:
            continue

        for row in rows:
            value = by_game_pk.get(int(row.mlb_game_pk))
            if value is None:
                rows_unresolved += 1
                continue
            rows_resolved += 1
            if apply:
                row.games_started = value

        completed.add(pitcher.id)
        if apply:
            session.commit()
            _write_checkpoint(checkpoint_path, completed)

    if not apply:
        session.rollback()

    rows_still_null_after = (
        session.query(db.func.count(GameLog.id))
        .filter(GameLog.games_started.is_(None))
        .scalar()
        or 0
    )

    return {
        'mode': 'apply' if apply else 'dry_run',
        'total_null_before': int(total_null_before),
        'rows_examined': int(rows_examined),
        'rows_resolved': int(rows_resolved),
        'rows_unresolved': int(rows_unresolved),
        'rows_still_null_after': int(rows_still_null_after),
        'distinct_pitchers_with_nulls': len(pitchers),
        'pitchers_processed': int(pitchers_processed),
        'pitchers_skipped_checkpoint': int(pitchers_skipped_checkpoint),
        'fetch_failures': fetch_failures,
        'fetch_failure_count': len(fetch_failures),
        'invalid_games_started_values': invalid_values,
        'invalid_games_started_value_count': len(invalid_values),
        'checkpoint_path': str(checkpoint_path),
    }
