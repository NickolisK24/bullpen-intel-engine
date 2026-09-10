from __future__ import annotations

from datetime import date
import hashlib
import json
from typing import Any

from sqlalchemy import asc

from models.game_log import GameLog
from models.pitcher_season_ledger_coverage import PitcherSeasonLedgerCoverage
from models.scheduled_game import ScheduledGame
from services.game_finality import (
    has_safe_final_status,
    scheduled_rows_have_unresolved_resumed_linkage,
)
from utils.db import db
from utils.games_started import InvalidGamesStartedValue, parse_games_started
from utils.time import utc_now_naive


_OPTIONAL_INPUT_NOT_PROVIDED = object()
COVERAGE_SCOPE_PITCHER_SEASON_TO_TARGET = (
    'pitcher_regular_season_through_target'
)
REGULAR_SEASON_GAME_TYPE = 'R'
STATUS_COMPLETE = PitcherSeasonLedgerCoverage.STATUS_COMPLETE
STATUS_INCOMPLETE = PitcherSeasonLedgerCoverage.STATUS_INCOMPLETE
STATUS_UNKNOWN = PitcherSeasonLedgerCoverage.STATUS_UNKNOWN

REASON_SOURCE_MISSING_IDENTITY = 'source_missing_identity'
REASON_SOURCE_INVALID_DATE = 'source_invalid_date'
REASON_SOURCE_UNKNOWN_GAMES_STARTED = 'source_unknown_games_started'
REASON_SOURCE_INVALID_GAMES_STARTED = 'source_invalid_games_started'
REASON_SOURCE_DUPLICATE_CONFLICT = 'source_duplicate_conflict'
REASON_SOURCE_FINALITY_UNKNOWN = 'source_finality_unknown'
REASON_SOURCE_NOT_FINAL = 'source_not_final'
REASON_STORED_MISSING_IDENTITY = 'stored_missing_identity'
REASON_STORED_UNKNOWN_GAMES_STARTED = 'stored_unknown_games_started'
REASON_MANIFEST_MISMATCH = 'source_stored_manifest_mismatch'
REASON_TARGET_NOT_IN_SOURCE = 'target_not_in_source_manifest'
REASON_STALE_STORED_MANIFEST = 'stored_manifest_changed_since_verification'


def reconcile_pitcher_season_coverage(
    pitcher,
    splits,
    *,
    season: int,
    through_date: date,
    sync_run_id=None,
    session=None,
    game_type: str = REGULAR_SEASON_GAME_TYPE,
    finality_cache: dict | None = None,
    stored_rows=None,
    target_game_pks=None,
) -> dict:
    """Persist target-game coverage records from one full-season split response."""
    session = session or db.session
    target_game_pk_set = _positive_int_set(target_game_pks)
    source_result = build_source_manifest(
        splits,
        through_date=through_date,
        game_type=game_type,
        finality_cache=finality_cache,
    )
    if stored_rows is None:
        stored_result = build_stored_manifest(
            pitcher_id=pitcher.id,
            season=season,
            through_date=through_date,
            game_type=game_type,
            session=session,
        )
    else:
        stored_result = build_stored_manifest_from_rows(
            row for row in stored_rows
            if (
                getattr(row, 'pitcher_id', None) == pitcher.id
                and getattr(row, 'game_type', None) == game_type
                and getattr(row, 'game_date', None) is not None
                and date(int(season), 1, 1) <= row.game_date <= through_date
            )
        )

    upserted = 0
    complete = 0
    incomplete = 0
    targets = [
        entry for entry in source_result['entries']
        if target_game_pk_set is None or entry['mlb_game_pk'] in target_game_pk_set
    ]
    existing_records = _coverage_records_by_target(
        session=session,
        pitcher_id=pitcher.id,
        season=season,
        game_type=game_type,
        target_game_pks=[target['mlb_game_pk'] for target in targets],
    )
    for target in targets:
        source_subset = _subset_through_target(source_result['entries'], target)
        stored_subset = _subset_through_target(stored_result['entries'], target)
        reason_codes = set(source_result['reason_codes'])
        reason_codes.update(stored_result['reason_codes'])

        if not _contains_entry(source_subset, target):
            reason_codes.add(REASON_TARGET_NOT_IN_SOURCE)

        source_fingerprint = manifest_fingerprint(source_subset)
        stored_fingerprint = manifest_fingerprint(stored_subset)
        source_count, source_starts = _manifest_counts(source_subset)
        stored_count, stored_starts = _manifest_counts(stored_subset)
        if source_fingerprint != stored_fingerprint:
            reason_codes.add(REASON_MANIFEST_MISMATCH)

        status = STATUS_COMPLETE if not reason_codes else STATUS_INCOMPLETE
        record = _upsert_coverage_record(
            session=session,
            pitcher=pitcher,
            season=season,
            game_type=game_type,
            target=target,
            source_count=source_count,
            source_starts=source_starts,
            stored_count=stored_count,
            stored_starts=stored_starts,
            source_fingerprint=source_fingerprint,
            stored_fingerprint=stored_fingerprint,
            status=status,
            reason_codes=sorted(reason_codes),
            sync_run_id=sync_run_id,
            existing_record=existing_records.get(target['mlb_game_pk']),
        )
        session.add(record)
        upserted += 1
        if status == STATUS_COMPLETE:
            complete += 1
        else:
            incomplete += 1

    return {
        'coverage_records_upserted': upserted,
        'coverage_records_complete': complete,
        'coverage_records_incomplete': incomplete,
        'source_entries': len(source_result['entries']),
        'stored_entries': len(stored_result['entries']),
        'target_entries': len(targets),
        'source_reason_codes': sorted(source_result['reason_codes']),
        'stored_reason_codes': sorted(stored_result['reason_codes']),
    }


def build_source_manifest(
    splits,
    *,
    through_date: date,
    game_type: str = REGULAR_SEASON_GAME_TYPE,
    finality_cache: dict | None = None,
) -> dict:
    entries_by_pk = {}
    reason_codes = set()

    for split in splits or []:
        game_info = split.get('game') or {}
        raw_game_pk = game_info.get('gamePk')
        raw_game_date = split.get('date')
        raw_game_type = game_info.get('gameType') or REGULAR_SEASON_GAME_TYPE
        if raw_game_type != game_type:
            continue

        game_pk = _positive_int(raw_game_pk)
        if game_pk is None or not raw_game_date:
            reason_codes.add(REASON_SOURCE_MISSING_IDENTITY)
            continue
        try:
            game_date = date.fromisoformat(str(raw_game_date))
        except ValueError:
            reason_codes.add(REASON_SOURCE_INVALID_DATE)
            continue
        if game_date > through_date:
            continue

        stat = split.get('stat') or {}
        try:
            games_started = parse_games_started(stat.get('gamesStarted'))
        except InvalidGamesStartedValue:
            reason_codes.add(REASON_SOURCE_INVALID_GAMES_STARTED)
            continue
        if games_started is None:
            reason_codes.add(REASON_SOURCE_UNKNOWN_GAMES_STARTED)
            continue

        finality = _split_finality(game_info, game_pk, finality_cache)
        if finality == 'unknown':
            reason_codes.add(REASON_SOURCE_FINALITY_UNKNOWN)
            continue
        if finality != 'final':
            reason_codes.add(REASON_SOURCE_NOT_FINAL)
            continue

        entry = _manifest_entry(game_pk, game_date, games_started)
        existing = entries_by_pk.get(game_pk)
        if existing is None:
            entries_by_pk[game_pk] = entry
            continue
        if existing != entry:
            reason_codes.add(REASON_SOURCE_DUPLICATE_CONFLICT)

    return {
        'entries': _sorted_manifest(entries_by_pk.values()),
        'reason_codes': reason_codes,
    }


def build_stored_manifest(
    *,
    pitcher_id: int,
    season: int,
    through_date: date,
    game_type: str = REGULAR_SEASON_GAME_TYPE,
    session=None,
) -> dict:
    session = session or db.session
    season_opening = date(int(season), 1, 1)
    rows = (
        session.query(GameLog)
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_type == game_type,
            GameLog.game_date >= season_opening,
            GameLog.game_date <= through_date,
        )
        .order_by(asc(GameLog.game_date), asc(GameLog.mlb_game_pk))
        .all()
    )
    return build_stored_manifest_from_rows(rows)


def build_stored_manifest_from_rows(rows) -> dict:
    entries = []
    reason_codes = set()
    for row in rows or []:
        game_pk = _positive_int(getattr(row, 'mlb_game_pk', None))
        game_date = getattr(row, 'game_date', None)
        if game_pk is None or game_date is None:
            reason_codes.add(REASON_STORED_MISSING_IDENTITY)
            continue
        try:
            games_started = parse_games_started(getattr(row, 'games_started', None))
        except InvalidGamesStartedValue:
            reason_codes.add(REASON_STORED_UNKNOWN_GAMES_STARTED)
            continue
        if games_started is None:
            reason_codes.add(REASON_STORED_UNKNOWN_GAMES_STARTED)
            continue
        entries.append(_manifest_entry(game_pk, game_date, games_started))

    return {
        'entries': _sorted_manifest(entries),
        'reason_codes': reason_codes,
    }


def history_coverage_for_game_log(starter_log, pitcher, *, session=None) -> dict | None:
    session = session or db.session
    target_date = getattr(starter_log, 'game_date', None)
    target_game_pk = _positive_int(getattr(starter_log, 'mlb_game_pk', None))
    pitcher_id = getattr(starter_log, 'pitcher_id', None)
    if target_date is None or target_game_pk is None or pitcher_id is None:
        return None
    game_type = getattr(starter_log, 'game_type', None) or REGULAR_SEASON_GAME_TYPE
    season = target_date.year
    record = (
        session.query(PitcherSeasonLedgerCoverage)
        .filter(
            PitcherSeasonLedgerCoverage.pitcher_id == pitcher_id,
            PitcherSeasonLedgerCoverage.season == season,
            PitcherSeasonLedgerCoverage.game_type == game_type,
            PitcherSeasonLedgerCoverage.target_game_pk == target_game_pk,
        )
        .one_or_none()
    )
    if record is None:
        return None
    if getattr(pitcher, 'mlb_id', None) != record.pitcher_mlb_id:
        return None

    current_manifest = build_stored_manifest(
        pitcher_id=pitcher_id,
        season=season,
        through_date=target_date,
        game_type=game_type,
        session=session,
    )
    current_subset = _subset_through_target(
        current_manifest['entries'],
        _manifest_entry(target_game_pk, target_date, 1),
    )
    current_fingerprint = manifest_fingerprint(current_subset)
    reason_codes = set(record.reason_codes or [])
    reason_codes.update(current_manifest['reason_codes'])
    if current_fingerprint != record.stored_manifest_fingerprint:
        reason_codes.add(REASON_STALE_STORED_MANIFEST)

    status = record.coverage_status
    if reason_codes or current_fingerprint != record.source_manifest_fingerprint:
        status = STATUS_INCOMPLETE

    return {
        'coverage_state': status,
        'coverage_scope': COVERAGE_SCOPE_PITCHER_SEASON_TO_TARGET,
        'pitcher_id': record.pitcher_id,
        'pitcher_mlb_id': record.pitcher_mlb_id,
        'season': record.season,
        'game_type': record.game_type,
        'target_game_pk': record.target_game_pk,
        'covered_through_date': (
            record.covered_through_date.isoformat()
            if record.covered_through_date else None
        ),
        'source_appearance_count': record.source_appearance_count,
        'source_games_started_count': record.source_games_started_count,
        'stored_appearance_count': record.stored_appearance_count,
        'stored_games_started_count': record.stored_games_started_count,
        'source_manifest_fingerprint': record.source_manifest_fingerprint,
        'stored_manifest_fingerprint': record.stored_manifest_fingerprint,
        'reason_codes': sorted(reason_codes),
    }


def manifest_fingerprint(entries) -> str:
    payload = json.dumps(
        _sorted_manifest(entries),
        sort_keys=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _upsert_coverage_record(
    *,
    session,
    pitcher,
    season,
    game_type,
    target,
    source_count,
    source_starts,
    stored_count,
    stored_starts,
    source_fingerprint,
    stored_fingerprint,
    status,
    reason_codes,
    sync_run_id,
    existing_record=_OPTIONAL_INPUT_NOT_PROVIDED,
):
    if existing_record is _OPTIONAL_INPUT_NOT_PROVIDED:
        record = (
            session.query(PitcherSeasonLedgerCoverage)
            .filter(
                PitcherSeasonLedgerCoverage.pitcher_id == pitcher.id,
                PitcherSeasonLedgerCoverage.season == season,
                PitcherSeasonLedgerCoverage.game_type == game_type,
                PitcherSeasonLedgerCoverage.target_game_pk == target['mlb_game_pk'],
            )
            .one_or_none()
        )
    else:
        record = existing_record
    if record is None:
        record = PitcherSeasonLedgerCoverage(
            pitcher_id=pitcher.id,
            pitcher_mlb_id=pitcher.mlb_id,
            season=season,
            game_type=game_type,
            target_game_pk=target['mlb_game_pk'],
        )

    record.pitcher_mlb_id = pitcher.mlb_id
    record.covered_through_date = _entry_game_date(target)
    record.source_appearance_count = source_count
    record.source_games_started_count = source_starts
    record.stored_appearance_count = stored_count
    record.stored_games_started_count = stored_starts
    record.source_manifest_fingerprint = source_fingerprint
    record.stored_manifest_fingerprint = stored_fingerprint
    record.coverage_status = status
    record.reason_codes = list(reason_codes)
    record.verified_at = utc_now_naive()
    record.sync_run_id = sync_run_id
    return record


def _coverage_records_by_target(
    *,
    session,
    pitcher_id: int,
    season: int,
    game_type: str,
    target_game_pks,
) -> dict[int, PitcherSeasonLedgerCoverage]:
    target_game_pk_set = _positive_int_set(target_game_pks) or set()
    if not target_game_pk_set:
        return {}
    rows = (
        session.query(PitcherSeasonLedgerCoverage)
        .filter(
            PitcherSeasonLedgerCoverage.pitcher_id == pitcher_id,
            PitcherSeasonLedgerCoverage.season == season,
            PitcherSeasonLedgerCoverage.game_type == game_type,
            PitcherSeasonLedgerCoverage.target_game_pk.in_(target_game_pk_set),
        )
        .all()
    )
    return {row.target_game_pk: row for row in rows}


def _split_finality(game_info, game_pk, finality_cache):
    if _split_has_own_status(game_info):
        return 'final' if has_safe_final_status(game_info) else 'not_final'
    if finality_cache is not None and game_pk in finality_cache:
        return finality_cache[game_pk]

    rows = ScheduledGame.query.filter_by(game_pk=game_pk).all()
    if not rows:
        state = 'unknown'
    elif scheduled_rows_have_unresolved_resumed_linkage(rows):
        state = 'not_final'
    elif any(row.status_state == ScheduledGame.STATE_FINAL for row in rows):
        state = 'final'
    else:
        state = 'not_final'
    if finality_cache is not None:
        finality_cache[game_pk] = state
    return state


def _split_has_own_status(game_info: dict) -> bool:
    status = (game_info or {}).get('status')
    if not isinstance(status, dict):
        return False
    return any(
        status.get(key) not in (None, '')
        for key in ('statusCode', 'detailedState', 'abstractGameState')
    )


def _manifest_entry(game_pk: int, game_date: date, games_started: int) -> dict:
    return {
        'mlb_game_pk': int(game_pk),
        'game_date': game_date.isoformat() if isinstance(game_date, date) else str(game_date),
        'games_started': int(games_started),
    }


def _entry_game_date(entry) -> date:
    raw_game_date = entry['game_date']
    if isinstance(raw_game_date, date):
        return raw_game_date
    return date.fromisoformat(str(raw_game_date))


def _sorted_manifest(entries) -> list[dict]:
    return sorted(
        [dict(entry) for entry in entries or []],
        key=lambda entry: (entry['game_date'], entry['mlb_game_pk']),
    )


def _subset_through_target(entries, target) -> list[dict]:
    target_date = target['game_date']
    target_game_pk = target['mlb_game_pk']
    return [
        entry for entry in _sorted_manifest(entries)
        if (
            entry['game_date'] < target_date
            or (
                entry['game_date'] == target_date
                and entry['mlb_game_pk'] <= target_game_pk
            )
        )
    ]


def _contains_entry(entries, target) -> bool:
    return any(entry == target for entry in entries or [])


def _manifest_counts(entries) -> tuple[int, int]:
    manifest = list(entries or [])
    return len(manifest), sum(1 for entry in manifest if entry['games_started'] == 1)


def _positive_int(raw: Any) -> int | None:
    if raw is None or raw == '' or isinstance(raw, bool):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _positive_int_set(values) -> set[int] | None:
    if values is None:
        return None
    result = set()
    for raw in values:
        value = _positive_int(raw)
        if value is not None:
            result.add(value)
    return result
