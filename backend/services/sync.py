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
import signal
import threading
import time
from pathlib import Path

from sqlalchemy import desc

from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.postgame_processed_game import PostgameProcessedGame
from models.sync_run import SyncRun
from models.sync_failure import SyncFailure
from services import dead_letter
from services import sync_metadata
from services.availability_reference_date import resolve_product_day
from services.completed_game_context_payload_adapter import build_completed_game_payload
from services.completed_game_context_service import (
    extract_completed_game_contexts,
    upsert_completed_game_context,
)
from services.fatigue import calculate_fatigue
from services.mlb_api import mlb_client
from services.roster_status import STATUS_ACTIVE
from services.roster_status_sync import sync_roster_statuses
from services.team_assignment_sync import sync_team_assignments
from utils.innings import (
    outs_to_decimal_innings,
    parse_mlb_innings_to_outs,
    validate_innings_outs,
)
from utils.games_started import parse_games_started
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)
PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE = 'pitcher_game_logs'
GAME_LOG_CORRECTION_FAILURE_ENTITY_TYPE = 'game_log_correction_attempt'
PITCHER_RESOLUTION_FAILURE_ENTITY_TYPE = 'pitcher_resolution'
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
POSTGAME_SNAPSHOT_DEFAULT_TIMEOUT_SECONDS = 120.0
DAILY_GAME_LOG_CORRECTION_SOURCE = 'daily_game_log'
POSTGAME_BOXSCORE_CORRECTION_SOURCE = 'postgame_boxscore'
POSTGAME_PITCHER_RESOLUTION_SOURCE = 'mlb_stats_api:postgame_boxscore_pitching_line'
POSTGAME_PITCHER_TEAM_ASSIGNMENT_STATUS = 'ASSIGNED'
POSTGAME_MARKER_STATUS_FULLY_PROCESSED = PostgameProcessedGame.STATUS_FULLY_PROCESSED
POSTGAME_MARKER_STATUS_INCOMPLETE = PostgameProcessedGame.STATUS_INCOMPLETE
POSTGAME_MARKER_STATUS_FAILED = PostgameProcessedGame.STATUS_FAILED
POSTGAME_MARKER_RETRY_LIMIT = 3

_REQUIRED_CORRECTION_STAT_KEYS = (
    'inningsPitched',
    'strikes',
    'hits',
    'runs',
    'earnedRuns',
    'baseOnBalls',
    'strikeOuts',
    'homeRuns',
)
_OPTIONAL_BOOL_STAT_FIELDS = (
    ('saveOpportunities', 'save_situation'),
    ('holds', 'hold'),
    ('blownSaves', 'blown_save'),
    ('wins', 'win'),
    ('losses', 'loss'),
    ('saves', 'save'),
)

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
    local = resolve_product_day(now).local_datetime
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


def _marker_processing_status(marker: PostgameProcessedGame | None) -> str | None:
    if marker is None:
        return None
    return marker.processing_status or POSTGAME_MARKER_STATUS_FULLY_PROCESSED


def _postgame_marker_retryable(marker: PostgameProcessedGame | None) -> bool:
    if marker is None:
        return True
    return (
        _marker_processing_status(marker) == POSTGAME_MARKER_STATUS_INCOMPLETE
        and (marker.attempt_count or 0) < POSTGAME_MARKER_RETRY_LIMIT
    )


def _unprocessed_completed_games(games: list[dict]) -> tuple[list[dict], dict]:
    game_pks = [pk for pk in (_game_pk(game) for game in games) if pk]
    if not game_pks:
        return [], {
            'fully_processed': 0,
            'retryable_incomplete': 0,
            'failed': 0,
        }
    markers = {
        marker.mlb_game_pk: marker
        for marker in (
            PostgameProcessedGame.query
            .filter(PostgameProcessedGame.mlb_game_pk.in_(game_pks))
            .all()
        )
    }
    counts = {
        'fully_processed': 0,
        'retryable_incomplete': 0,
        'failed': 0,
    }
    pending = []
    for game in games:
        game_pk = _game_pk(game)
        marker = markers.get(game_pk)
        if marker is None:
            pending.append(game)
            continue

        status = _marker_processing_status(marker)
        if status == POSTGAME_MARKER_STATUS_FULLY_PROCESSED:
            counts['fully_processed'] += 1
        elif _postgame_marker_retryable(marker):
            counts['retryable_incomplete'] += 1
            pending.append(game)
        else:
            counts['failed'] += 1

    return pending, counts


def _int_stat(stats: dict, key: str, default: int = 0) -> int:
    try:
        return int(stats.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _int_stat_or_none(stats: dict, key: str) -> int | None:
    raw = (stats or {}).get(key)
    if raw is None or raw == '':
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _positive_stat(stats: dict, key: str) -> bool:
    return _int_stat(stats, key) > 0


def _correction_source_state(stats: dict) -> tuple[bool, str | None, list[str]]:
    if not stats:
        return False, 'empty_source_line', []
    missing = [
        key for key in _REQUIRED_CORRECTION_STAT_KEYS
        if key not in stats or stats.get(key) in (None, '')
    ]
    if missing:
        return False, 'partial_source_line', missing
    return True, None, []


def _extract_leverage_index(stats: dict):
    for li_key in ('leverageIndex', 'avgLeverageIndex', 'avgLI'):
        raw_li = (stats or {}).get(li_key)
        if raw_li is not None:
            try:
                return float(raw_li)
            except (TypeError, ValueError):
                return None
    return None


def _game_log_values_from_stats(
    *,
    stats: dict,
    pitcher,
    game_pk: int,
    game_date: date,
    game_type: str,
    opponent: str | None,
    opponent_abbreviation: str | None,
    games_started,
    include_leverage_index: bool = False,
) -> dict:
    innings_pitched_outs = validate_innings_outs(
        parse_mlb_innings_to_outs(stats.get('inningsPitched', '0.0'))
    )
    values = {
        'pitcher_id': pitcher.id,
        'mlb_game_pk': game_pk,
        'game_date': game_date,
        'game_type': game_type,
        'opponent': opponent,
        'opponent_abbreviation': opponent_abbreviation,
        'games_started': games_started,
        'innings_pitched': outs_to_decimal_innings(innings_pitched_outs),
        'innings_pitched_outs': innings_pitched_outs,
        'pitches_thrown': _int_stat_or_none(stats, 'numberOfPitches'),
        'strikes': _int_stat(stats, 'strikes'),
        'hits_allowed': _int_stat(stats, 'hits'),
        'runs_allowed': _int_stat(stats, 'runs'),
        'earned_runs': _int_stat(stats, 'earnedRuns'),
        'walks': _int_stat(stats, 'baseOnBalls'),
        'strikeouts': _int_stat(stats, 'strikeOuts'),
        'home_runs_allowed': _int_stat(stats, 'homeRuns'),
        'save_situation': _positive_stat(stats, 'saveOpportunities'),
        'hold': _positive_stat(stats, 'holds'),
        'blown_save': _positive_stat(stats, 'blownSaves'),
        'win': _positive_stat(stats, 'wins'),
        'loss': _positive_stat(stats, 'losses'),
        'save': _positive_stat(stats, 'saves'),
    }
    if include_leverage_index:
        values['leverage_index'] = _extract_leverage_index(stats)
    return values


def _authoritative_correction_fields(values: dict, stats: dict, *, include_leverage_index: bool) -> list[str]:
    fields = [
        'game_date',
        'game_type',
        'innings_pitched',
        'innings_pitched_outs',
        'pitches_thrown',
        'strikes',
        'hits_allowed',
        'runs_allowed',
        'earned_runs',
        'walks',
        'strikeouts',
        'home_runs_allowed',
    ]
    for field in ('opponent', 'opponent_abbreviation', 'games_started'):
        if values.get(field) is not None:
            fields.append(field)
    for source_key, model_field in _OPTIONAL_BOOL_STAT_FIELDS:
        if source_key in (stats or {}) and (stats or {}).get(source_key) not in (None, ''):
            fields.append(model_field)
    if include_leverage_index and values.get('leverage_index') is not None:
        fields.append('leverage_index')
    return fields


def _record_unsafe_correction_attempt(
    *,
    pitcher,
    game_pk,
    reason,
    missing_keys=None,
    stats=None,
    source,
    sync_run_id=None,
    job_name='daily_sync',
):
    dead_letter.record_failure(
        GAME_LOG_CORRECTION_FAILURE_ENTITY_TYPE,
        f'unsafe correction source: {reason}',
        entity_ref=game_pk,
        payload={
            'pitcher_id': pitcher.id,
            'mlb_id': pitcher.mlb_id,
            'game_pk': game_pk,
            'source': source,
            'reason': reason,
            'missing_keys': list(missing_keys or []),
            'stat_keys': sorted((stats or {}).keys()),
        },
        sync_run_id=sync_run_id,
        job_name=job_name,
    )


def _upsert_game_log_from_authoritative_values(
    *,
    pitcher,
    game_pk,
    values,
    stats,
    source,
    sync_run_id=None,
    job_name='daily_sync',
    include_leverage_index=False,
):
    existing = GameLog.query.filter_by(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
    ).first()
    if existing is None:
        log = GameLog(**values)
        db.session.add(log)
        return {
            'status': 'inserted',
            'log': log,
            'changed_fields': [],
        }

    safe, reason, missing = _correction_source_state(stats)
    if not safe:
        _record_unsafe_correction_attempt(
            pitcher=pitcher,
            game_pk=game_pk,
            reason=reason,
            missing_keys=missing,
            stats=stats,
            source=source,
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        return {
            'status': 'unsafe',
            'log': existing,
            'changed_fields': [],
            'reason': reason,
        }

    changed_fields = []
    for field in _authoritative_correction_fields(
        values,
        stats,
        include_leverage_index=include_leverage_index,
    ):
        new_value = values[field]
        if getattr(existing, field) != new_value:
            setattr(existing, field, new_value)
            changed_fields.append(field)

    if not changed_fields:
        return {
            'status': 'unchanged',
            'log': existing,
            'changed_fields': [],
        }

    existing.stat_correction_count = (existing.stat_correction_count or 0) + 1
    existing.last_stat_correction_at = utc_now_naive()
    existing.last_stat_correction_source = source
    existing.last_stat_correction_sync_run_id = sync_run_id
    db.session.add(existing)
    return {
        'status': 'corrected',
        'log': existing,
        'changed_fields': changed_fields,
    }


def _positive_external_id(raw):
    if isinstance(raw, bool) or raw in (None, ''):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _position_value(position):
    if not isinstance(position, dict):
        return position
    return (
        position.get('abbreviation')
        or position.get('code')
        or position.get('type')
        or position.get('name')
    )


def _normalized_position(value):
    raw = _position_value(value)
    return str(raw).strip().upper() if raw not in (None, '') else None


def _team_abbreviation_from(team: dict | None):
    team = team or {}
    return (
        team.get('abbreviation')
        or team.get('teamCode')
        or team.get('fileCode')
    )


def _resolve_pitching_line_team(game: dict, line: dict) -> tuple[dict | None, str | None]:
    side = line.get('side')
    if side not in {'home', 'away'}:
        return None, 'missing_or_invalid_team_side'

    game_team_id = _positive_external_id(_game_team_id(game, side))
    line_team_id = _positive_external_id(line.get('team_id'))
    if game_team_id and line_team_id and game_team_id != line_team_id:
        return None, 'conflicting_team_assignment'

    team_id = line_team_id or game_team_id
    if team_id is None:
        return None, 'missing_team_assignment'

    game_team = _game_team(game, side)
    return {
        'team_id': team_id,
        'team_name': line.get('team') or game_team.get('name'),
        'team_abbreviation': (
            line.get('team_abbreviation')
            or _team_abbreviation_from(game_team)
        ),
    }, None


def _record_pitcher_resolution_failure(
    *,
    line,
    game,
    reason,
    source=POSTGAME_PITCHER_RESOLUTION_SOURCE,
    sync_run_id=None,
    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
):
    game_pk = _game_pk(game)
    dead_letter.record_failure(
        PITCHER_RESOLUTION_FAILURE_ENTITY_TYPE,
        f'unresolvable pitcher line: {reason}',
        entity_ref=game_pk,
        payload={
            'game_pk': game_pk,
            'source': source,
            'reason': reason,
            'player_id': line.get('player_id'),
            'person_id': line.get('person_id'),
            'name': line.get('name'),
            'side': line.get('side'),
            'team_id': line.get('team_id'),
            'team': line.get('team'),
            'stat_keys': sorted((line.get('stats') or {}).keys()),
        },
        sync_run_id=sync_run_id,
        job_name=job_name,
    )


def _pitcher_resolution_failure(
    *,
    line,
    game,
    reason,
    sync_run_id=None,
    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
) -> dict:
    _record_pitcher_resolution_failure(
        line=line,
        game=game,
        reason=reason,
        sync_run_id=sync_run_id,
        job_name=job_name,
    )
    return {
        'status': 'unresolved',
        'pitcher': None,
        'reason': reason,
        'created': False,
        'reactivated': False,
    }


def _apply_pitcher_authority_from_line(pitcher, line: dict, team: dict, timestamp):
    before_active = bool(pitcher.active)
    before_team = (pitcher.team_id, pitcher.team_name, pitcher.team_abbreviation)
    before_roster = pitcher.roster_status

    line_name = line.get('name')
    if line_name and not pitcher.full_name:
        pitcher.full_name = line_name

    desired = {
        'active': True,
        'position': pitcher.position or 'P',
        'team_id': team['team_id'],
        'team_name': team.get('team_name') or pitcher.team_name,
        'team_abbreviation': team.get('team_abbreviation') or pitcher.team_abbreviation,
        'team_assignment_status': POSTGAME_PITCHER_TEAM_ASSIGNMENT_STATUS,
        'team_assignment_source': POSTGAME_PITCHER_RESOLUTION_SOURCE,
        'roster_status': STATUS_ACTIVE,
        'roster_status_source': POSTGAME_PITCHER_RESOLUTION_SOURCE,
        'roster_status_raw_code': STATUS_ACTIVE,
        'roster_status_raw_description': 'Final-game pitching line',
    }
    changed = False
    for attr, value in desired.items():
        if getattr(pitcher, attr) != value:
            setattr(pitcher, attr, value)
            changed = True

    if changed or pitcher.team_assignment_updated_at is None:
        pitcher.team_assignment_updated_at = timestamp
    if changed or pitcher.roster_status_updated_at is None:
        pitcher.roster_status_updated_at = timestamp

    return {
        'reactivated': not before_active,
        'team_changed': before_team != (
            pitcher.team_id,
            pitcher.team_name,
            pitcher.team_abbreviation,
        ),
        'roster_changed': before_roster != pitcher.roster_status,
        'changed': changed,
    }


def resolve_pitcher_for_authoritative_line(
    line: dict,
    game: dict,
    *,
    local_pitchers=None,
    sync_run_id=None,
    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
):
    """
    Resolve or create a pitcher from a completed-game pitching line.

    The boxscore pitching line provides the authoritative player id, name, and
    team side for Branch 04. If any of those identity anchors conflict or are
    absent, the line is dead-lettered instead of being silently skipped.
    """
    player_id = _positive_external_id(line.get('player_id'))
    if player_id is None:
        return _pitcher_resolution_failure(
            line=line,
            game=game,
            reason='missing_or_invalid_player_id',
            sync_run_id=sync_run_id,
            job_name=job_name,
        )

    person_id = _positive_external_id(line.get('person_id'))
    if person_id is not None and person_id != player_id:
        return _pitcher_resolution_failure(
            line=line,
            game=game,
            reason='conflicting_player_identity',
            sync_run_id=sync_run_id,
            job_name=job_name,
        )

    team, team_error = _resolve_pitching_line_team(game, line)
    if team_error:
        return _pitcher_resolution_failure(
            line=line,
            game=game,
            reason=team_error,
            sync_run_id=sync_run_id,
            job_name=job_name,
        )

    line_position = _normalized_position(line.get('position'))
    if line_position is not None and line_position not in {'P', 'PITCHER'}:
        return _pitcher_resolution_failure(
            line=line,
            game=game,
            reason='non_pitcher_position',
            sync_run_id=sync_run_id,
            job_name=job_name,
        )

    local_pitchers = local_pitchers if local_pitchers is not None else {}
    pitcher = local_pitchers.get(player_id)
    if pitcher is None:
        pitcher = Pitcher.query.filter_by(mlb_id=player_id).first()

    timestamp = utc_now_naive()
    if pitcher is None:
        line_name = line.get('name')
        if not line_name:
            return _pitcher_resolution_failure(
                line=line,
                game=game,
                reason='missing_player_name',
                sync_run_id=sync_run_id,
                job_name=job_name,
            )
        pitcher = Pitcher(
            mlb_id=player_id,
            full_name=line_name,
            position='P',
        )
        _apply_pitcher_authority_from_line(pitcher, line, team, timestamp)
        db.session.add(pitcher)
        db.session.flush()
        local_pitchers[player_id] = pitcher
        return {
            'status': 'created',
            'pitcher': pitcher,
            'created': True,
            'reactivated': False,
            'reason': None,
        }

    existing_position = _normalized_position(pitcher.position)
    if existing_position is not None and existing_position not in {'P', 'PITCHER'}:
        return _pitcher_resolution_failure(
            line=line,
            game=game,
            reason='local_record_not_pitcher',
            sync_run_id=sync_run_id,
            job_name=job_name,
        )

    changes = _apply_pitcher_authority_from_line(pitcher, line, team, timestamp)
    if changes['changed']:
        db.session.add(pitcher)
    db.session.flush()
    local_pitchers[player_id] = pitcher
    status = 'reactivated' if changes['reactivated'] else 'resolved'
    return {
        'status': status,
        'pitcher': pitcher,
        'created': False,
        'reactivated': changes['reactivated'],
        'reason': None,
    }


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
        candidates = [
            (pitcher_id, f'ID{pitcher_id}')
            for pitcher_id in (team_data.get('pitchers') or [])
        ]
        candidate_keys = {key for _pitcher_id, key in candidates}
        for player_key, player in player_data.items():
            stats = ((player.get('stats') or {}).get('pitching') or {})
            if stats and player_key not in candidate_keys:
                person = player.get('person') or {}
                candidates.append((person.get('id'), player_key))

        for pitcher_id, player_key in candidates:
            player = player_data.get(player_key) or {}
            person = player.get('person') or {}
            position = (
                player.get('position')
                or person.get('primaryPosition')
                or {}
            )
            stats = ((player.get('stats') or {}).get('pitching') or {})
            if stats:
                pitchers.append({
                    'player_id': pitcher_id,
                    'person_id': person.get('id'),
                    'name': person.get('fullName'),
                    'team': team_info.get('name'),
                    'team_id': team_info.get('id'),
                    'team_abbreviation': _team_abbreviation_from(team_info),
                    'position': _position_value(position),
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
    sync_run_id=None,
    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
) -> dict:
    game_pk = _game_pk(game)
    if not game_pk:
        return {'status': 'skipped', 'reason': 'missing_game_pk'}

    stats = line.get('stats') or {}
    opponent, opponent_abbreviation = _opponent_for_line(game, line, team_abbr_map)
    values = _game_log_values_from_stats(
        stats=stats,
        pitcher=pitcher,
        game_pk=game_pk,
        game_date=game_date,
        game_type=(game or {}).get('gameType', 'R'),
        opponent=opponent,
        opponent_abbreviation=opponent_abbreviation,
        games_started=_line_games_started(line, pitcher_order),
        include_leverage_index=True,
    )
    return _upsert_game_log_from_authoritative_values(
        pitcher=pitcher,
        game_pk=game_pk,
        values=values,
        stats=stats,
        source=POSTGAME_BOXSCORE_CORRECTION_SOURCE,
        sync_run_id=sync_run_id,
        job_name=job_name,
        include_leverage_index=True,
    )


def _postgame_incomplete_reason(
    *,
    pitching_lines_seen: int,
    pitcher_resolution_failures: int,
    correction_attempts_failed: int,
) -> str | None:
    if pitching_lines_seen <= 0:
        return 'empty_pitching_data'
    if pitcher_resolution_failures:
        return 'pitcher_resolution_failures'
    if correction_attempts_failed:
        return 'unsafe_correction_attempts'
    return None


def _postgame_processing_status_for_attempt(reason: str | None, attempt_count: int) -> str:
    if reason is None:
        return POSTGAME_MARKER_STATUS_FULLY_PROCESSED
    if attempt_count >= POSTGAME_MARKER_RETRY_LIMIT:
        return POSTGAME_MARKER_STATUS_FAILED
    return POSTGAME_MARKER_STATUS_INCOMPLETE


def _record_postgame_retry_exhausted_failure(
    *,
    marker: PostgameProcessedGame,
    game: dict,
    reason: str,
    pitching_lines_seen: int,
    pitcher_resolution_failures: int,
    correction_attempts_failed: int,
    sync_run_id=None,
):
    dead_letter.record_failure(
        POSTGAME_GAME_FAILURE_ENTITY_TYPE,
        f'postgame processing retry limit reached: {reason}',
        entity_ref=marker.mlb_game_pk,
        payload={
            'game_pk': marker.mlb_game_pk,
            'schedule_game_status': game.get('status') if isinstance(game, dict) else None,
            'attempt_count': marker.attempt_count,
            'retry_limit': POSTGAME_MARKER_RETRY_LIMIT,
            'processing_status': marker.processing_status,
            'incomplete_reason': reason,
            'pitching_lines_seen': pitching_lines_seen,
            'pitcher_resolution_failures': pitcher_resolution_failures,
            'correction_attempts_failed': correction_attempts_failed,
        },
        sync_run_id=sync_run_id,
        job_name=sync_metadata.JOB_POSTGAME_REFRESH,
    )


def _upsert_postgame_processed_marker(
    *,
    existing_marker: PostgameProcessedGame | None,
    game: dict,
    game_date: date,
    logs_added: int,
    pitchers_touched: int,
    pitching_lines_seen: int,
    pitcher_resolution_failures: int,
    correction_attempts_failed: int,
    sync_run_id=None,
) -> tuple[PostgameProcessedGame, bool]:
    attempted_at = utc_now_naive()
    attempt_count = (existing_marker.attempt_count if existing_marker else 0) or 0
    attempt_count += 1
    incomplete_reason = _postgame_incomplete_reason(
        pitching_lines_seen=pitching_lines_seen,
        pitcher_resolution_failures=pitcher_resolution_failures,
        correction_attempts_failed=correction_attempts_failed,
    )
    previous_status = _marker_processing_status(existing_marker)
    processing_status = _postgame_processing_status_for_attempt(
        incomplete_reason,
        attempt_count,
    )

    marker = existing_marker or PostgameProcessedGame(mlb_game_pk=_game_pk(game))
    marker.game_date = game_date
    marker.game_type = (game or {}).get('gameType')
    marker.home_team_id = _game_team_id(game, 'home')
    marker.away_team_id = _game_team_id(game, 'away')
    marker.final_state = _status_value(game, 'detailedState')
    marker.logs_added = logs_added
    marker.pitchers_touched = pitchers_touched
    marker.sync_run_id = sync_run_id
    marker.processing_status = processing_status
    marker.attempt_count = attempt_count
    marker.last_attempted_at = attempted_at
    marker.incomplete_reason = incomplete_reason
    marker.pitching_lines_seen = pitching_lines_seen
    marker.pitcher_resolution_failures = pitcher_resolution_failures
    marker.correction_attempts_failed = correction_attempts_failed

    if processing_status == POSTGAME_MARKER_STATUS_FULLY_PROCESSED:
        marker.processed_at = attempted_at
        marker.failed_at = None
    elif processing_status == POSTGAME_MARKER_STATUS_FAILED:
        marker.processed_at = None
        marker.failed_at = marker.failed_at or attempted_at
    else:
        marker.processed_at = None
        marker.failed_at = None

    db.session.add(marker)
    retry_exhausted = (
        processing_status == POSTGAME_MARKER_STATUS_FAILED
        and previous_status != POSTGAME_MARKER_STATUS_FAILED
        and incomplete_reason is not None
    )
    if retry_exhausted:
        _record_postgame_retry_exhausted_failure(
            marker=marker,
            game=game,
            reason=incomplete_reason,
            pitching_lines_seen=pitching_lines_seen,
            pitcher_resolution_failures=pitcher_resolution_failures,
            correction_attempts_failed=correction_attempts_failed,
            sync_run_id=sync_run_id,
        )
    return marker, retry_exhausted


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
            'logs_corrected': 0,
            'correction_attempts_failed': 0,
            'pitcher_resolution_failures': 0,
            'pitchers_created': 0,
            'pitchers_reactivated': 0,
            'pitchers_touched': 0,
            'pitching_lines_seen': 0,
            'processing_status': None,
            'incomplete_reason': 'missing_game_pk',
            'attempt_count': 0,
            'retry_exhausted': False,
            'skipped': True,
            'reason': 'missing_game_pk',
        }

    existing_marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=game_pk).first()
    if existing_marker is not None and not _postgame_marker_retryable(existing_marker):
        processing_status = _marker_processing_status(existing_marker)
        return {
            'game_pk': game_pk,
            'logs_added': 0,
            'logs_corrected': 0,
            'correction_attempts_failed': 0,
            'pitcher_resolution_failures': 0,
            'pitchers_created': 0,
            'pitchers_reactivated': 0,
            'pitchers_touched': 0,
            'pitching_lines_seen': existing_marker.pitching_lines_seen or 0,
            'processing_status': processing_status,
            'incomplete_reason': existing_marker.incomplete_reason,
            'attempt_count': existing_marker.attempt_count or 0,
            'retry_exhausted': False,
            'skipped': True,
            'reason': (
                'already_processed'
                if processing_status == POSTGAME_MARKER_STATUS_FULLY_PROCESSED
                else 'retry_limit_reached'
            ),
        }

    boxscore = mlb_client.get_game_boxscore(game_pk)
    pitching_lines = _extract_pitching_lines_from_boxscore(boxscore)
    pitcher_order = _pitcher_order_by_side(boxscore)
    player_ids = sorted({
        player_id
        for player_id in (
            _positive_external_id(line.get('player_id'))
            for line in pitching_lines
        )
        if player_id is not None
    })
    local_pitchers = {
        pitcher.mlb_id: pitcher
        for pitcher in (
            Pitcher.query
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
    logs_corrected = 0
    correction_attempts_failed = 0
    pitcher_resolution_failures = 0
    pitchers_created = 0
    pitchers_reactivated = 0
    touched_pitcher_ids = set()
    for line in pitching_lines:
        resolution = resolve_pitcher_for_authoritative_line(
            line,
            game,
            local_pitchers=local_pitchers,
            sync_run_id=sync_run_id,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        )
        pitcher = resolution['pitcher']
        if pitcher is None:
            pitcher_resolution_failures += 1
            continue
        if resolution['created']:
            pitchers_created += 1
        if resolution['reactivated']:
            pitchers_reactivated += 1
        if pitcher.team_id and pitcher.team_abbreviation:
            team_abbr_map[pitcher.team_id] = pitcher.team_abbreviation
        result = _ingest_boxscore_pitching_line(
            pitcher,
            line,
            game,
            game_date=game_date,
            team_abbr_map=team_abbr_map,
            pitcher_order=pitcher_order,
            sync_run_id=sync_run_id,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        )
        if result['status'] == 'inserted':
            logs_added += 1
            touched_pitcher_ids.add(pitcher.id)
        elif result['status'] == 'corrected':
            logs_corrected += 1
            touched_pitcher_ids.add(pitcher.id)
        elif result['status'] == 'unsafe':
            correction_attempts_failed += 1

    marker, retry_exhausted = _upsert_postgame_processed_marker(
        existing_marker=existing_marker,
        game=game,
        game_date=game_date,
        logs_added=logs_added,
        pitchers_touched=len(touched_pitcher_ids),
        pitching_lines_seen=len(pitching_lines),
        pitcher_resolution_failures=pitcher_resolution_failures,
        correction_attempts_failed=correction_attempts_failed,
        sync_run_id=sync_run_id,
    )
    db.session.flush()

    return {
        'game_pk': game_pk,
        'logs_added': logs_added,
        'logs_corrected': logs_corrected,
        'correction_attempts_failed': correction_attempts_failed,
        'pitcher_resolution_failures': pitcher_resolution_failures,
        'pitchers_created': pitchers_created,
        'pitchers_reactivated': pitchers_reactivated,
        'pitchers_touched': len(touched_pitcher_ids),
        'pitching_lines_seen': len(pitching_lines),
        'processing_status': marker.processing_status,
        'incomplete_reason': marker.incomplete_reason,
        'attempt_count': marker.attempt_count or 0,
        'retry_exhausted': retry_exhausted,
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


def _postgame_snapshot_refresh_enabled() -> bool:
    """Whether the postgame refresh rebuilds the homepage lead-story cache.

    On by default. Set POSTGAME_REFRESH_SNAPSHOT to a falsey value to skip the
    in-refresh rebuild — an operational lever for the case where this optional
    tail is the slow/hanging step. Skipping it never affects correctness: the
    completed-game data is already committed, the homepage endpoint falls back to
    live generation, and the daily warm still refreshes the cache.
    """
    raw = os.environ.get('POSTGAME_REFRESH_SNAPSHOT')
    if raw is None:
        return True
    return raw.strip().lower() not in {'0', 'false', 'no', 'off', ''}


class _PostgameSnapshotTimeout(TimeoutError):
    """Raised when the optional postgame snapshot tail exceeds its time budget."""


def _postgame_snapshot_timeout_seconds() -> float | None:
    raw = os.environ.get('POSTGAME_REFRESH_SNAPSHOT_TIMEOUT_SECONDS')
    if raw is None:
        return POSTGAME_SNAPSHOT_DEFAULT_TIMEOUT_SECONDS

    value = raw.strip().lower()
    if value in {'0', 'false', 'no', 'off', ''}:
        return None

    try:
        seconds = float(value)
    except ValueError:
        return POSTGAME_SNAPSHOT_DEFAULT_TIMEOUT_SECONDS

    return seconds if seconds > 0 else None


def _snapshot_timeout_supported() -> bool:
    return (
        threading.current_thread() is threading.main_thread()
        and hasattr(signal, 'SIGALRM')
        and hasattr(signal, 'setitimer')
        and hasattr(signal, 'ITIMER_REAL')
    )


def _run_intelligence_surface_snapshot_with_timeout(
    schedule_date,
    *,
    timeout_seconds,
    run_logger,
):
    from services.intelligence_surface_snapshot import generate_snapshot_for_date

    if timeout_seconds is None:
        return generate_snapshot_for_date(
            schedule_date,
            source='postgame_refresh',
            step_logger=run_logger,
        )

    if not _snapshot_timeout_supported():
        run_logger.warning(
            'Intelligence surface snapshot timeout unavailable on this runtime; '
            'continuing without a hard bound (timeout_seconds=%s).',
            timeout_seconds,
        )
        return generate_snapshot_for_date(
            schedule_date,
            source='postgame_refresh',
            step_logger=run_logger,
        )

    previous_handler = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(_signum, _frame):
        raise _PostgameSnapshotTimeout(
            f'Intelligence surface snapshot exceeded {timeout_seconds:g}s')

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return generate_snapshot_for_date(
            schedule_date,
            source='postgame_refresh',
            step_logger=run_logger,
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _safe_generate_intelligence_surface_snapshot(schedule_date, *, status, run_logger):
    """Refresh the Intelligence Surface snapshot for a slate without ever
    breaking the refresh.

    Fail-soft wrapper around the homepage cache: rebuilds the stored
    GET /api/bullpen/intelligence/today response from the completed-game contexts
    just derived for ``schedule_date``. The completed-game contexts are already
    committed, so a snapshot failure here costs only a stale homepage cache (the
    endpoint falls back to live generation) and never undoes context work or
    fails the postgame refresh.

    This is the most expensive optional tail of the refresh (it rebuilds the
    lead-story for every team with a completed-game context). It logs a start
    line and an elapsed_ms so a slow build is visible in the job log instead of
    appearing as a silent gap. It can be skipped via POSTGAME_REFRESH_SNAPSHOT
    and bounded via POSTGAME_REFRESH_SNAPSHOT_TIMEOUT_SECONDS.
    """
    if not _postgame_snapshot_refresh_enabled():
        status['intelligence_snapshot'] = 'skipped_by_config'
        run_logger.info(
            'Intelligence surface snapshot skipped for %s '
            '(POSTGAME_REFRESH_SNAPSHOT disabled); homepage uses live fallback.',
            schedule_date,
        )
        return

    timeout_seconds = _postgame_snapshot_timeout_seconds()
    started = time.perf_counter()
    status.pop('intelligence_snapshot_error', None)
    run_logger.info(
        'Intelligence surface snapshot refresh starting for %s '
        '(timeout_seconds=%s).',
        schedule_date,
        timeout_seconds if timeout_seconds is not None else 'disabled',
    )
    try:
        response = _run_intelligence_surface_snapshot_with_timeout(
            schedule_date,
            timeout_seconds=timeout_seconds,
            run_logger=run_logger,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        status['intelligence_snapshot'] = response.get('status') or 'generated'
        run_logger.info(
            'Intelligence surface snapshot refresh completed for %s: status=%s, '
            'publishable=%s, elapsed_ms=%s.',
            schedule_date,
            response.get('status'),
            response.get('publishable_candidates'),
            elapsed_ms,
        )
    except _PostgameSnapshotTimeout as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        db.session.rollback()
        status['intelligence_snapshot'] = 'timed_out'
        status['intelligence_snapshot_error'] = str(exc)
        run_logger.warning(
            'Intelligence surface snapshot refresh timed out for '
            'schedule_date=%s after %ss (elapsed_ms=%s); postgame refresh will '
            'continue.',
            schedule_date,
            timeout_seconds,
            elapsed_ms,
        )
    except Exception as exc:  # noqa: BLE001 — snapshot is best-effort, never fatal
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        db.session.rollback()
        status['intelligence_snapshot'] = 'failed'
        status['intelligence_snapshot_error'] = str(exc)
        run_logger.warning(
            'Intelligence surface snapshot refresh failed for schedule_date=%s '
            '(elapsed_ms=%s); postgame refresh will continue: %s',
            schedule_date, elapsed_ms, exc,
        )


def sync_recent_logs(
    days_back: int = 7,
    reference_date: date | None = None,
    sync_run_id=None,
    job_name=sync_metadata.JOB_DAILY_SYNC,
):
    """
    Pull recent game logs from the MLB Stats API for every active pitcher,
    insert missing logs, and correct existing logs when MLB revises an
    authoritative stat line.

    Partial-failure semantics: a single pitcher whose fetch fails, or a single
    malformed game-log record, is dead-lettered (recorded in sync_failures with
    enough payload to retry) and skipped — it never aborts the rest of the
    batch. ``records_failed`` counts dead-lettered entities so the caller can
    mark the run 'partial'.

    Returns a dict suitable for API response / log line:
        {
          'new_logs_added':       int,
          'logs_corrected':       int,
          'pitchers_touched':     int,
          'errors':               int,
          'records_failed':       int,
          'correction_attempts_failed': int,
          'days_back':            int,
          'season':               int,
          'cutoff':               'YYYY-MM-DD',
        }
    """
    product_day = resolve_product_day(datetime.now(timezone.utc))
    timezone_limitations = ()
    if reference_date is None:
        reference_date = product_day.calendar_date
        timezone_limitations = product_day.limitations
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
    corrected_logs  = 0
    errors          = 0
    records_failed  = 0
    correction_attempts_failed = 0
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
                result = _ingest_game_log_split(
                    pitcher,
                    split,
                    cutoff,
                    team_abbr_map,
                    sync_run_id=sync_run_id,
                    job_name=job_name,
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

            if result['status'] == 'inserted':
                new_logs += 1
                touched_this_pitcher = True
                time.sleep(0.1)
            elif result['status'] == 'corrected':
                corrected_logs += 1
                touched_this_pitcher = True
            elif result['status'] == 'unsafe':
                records_failed += 1
                correction_attempts_failed += 1

        if touched_this_pitcher:
            pitchers_touched += 1

    db.session.commit()

    result = {
        'new_logs_added':    new_logs,
        'logs_corrected':    corrected_logs,
        'pitchers_touched':  pitchers_touched,
        'errors':            errors,
        'records_failed':    records_failed,
        'correction_attempts_failed': correction_attempts_failed,
        'days_back':         days_back,
        'season':            season,
        'reference_date':    reference_date.isoformat(),
        'cutoff':            cutoff.isoformat(),
    }
    if timezone_limitations:
        result['limitations'] = list(timezone_limitations)
    return result


def _ingest_game_log_split(
    pitcher,
    split,
    cutoff,
    team_abbr_map,
    *,
    sync_run_id=None,
    job_name=sync_metadata.JOB_DAILY_SYNC,
):
    """
    Insert or correct a single game-log split for a pitcher.

    Returns a result dict with status inserted, corrected, unchanged, unsafe,
    or skipped. Skipped covers before-cutoff and malformed-but-empty keys.
    Raises on a genuinely poisoned record so the caller can dead-letter it.
    """
    game_info     = split.get('game', {})
    stat          = split.get('stat', {})
    game_pk       = game_info.get('gamePk')
    game_date_str = split.get('date')
    game_type     = game_info.get('gameType', 'R')

    if not game_pk or not game_date_str:
        return {'status': 'skipped', 'reason': 'missing_key'}

    if not is_completed_game(game_info):
        return {'status': 'skipped', 'reason': 'not_completed'}

    game_date = datetime.strptime(game_date_str, '%Y-%m-%d').date()

    if game_date < cutoff:
        return {'status': 'skipped', 'reason': 'before_cutoff'}

    opponent = split.get('opponent', {})
    values = _game_log_values_from_stats(
        stats=stat,
        pitcher=pitcher,
        game_pk=game_pk,
        game_date=game_date,
        game_type=game_type,
        opponent=opponent.get('name'),
        opponent_abbreviation=team_abbr_map.get(opponent.get('id')),
        games_started=parse_games_started(stat.get('gamesStarted')),
    )
    result = _upsert_game_log_from_authoritative_values(
        pitcher=pitcher,
        game_pk=game_pk,
        values=values,
        stats=stat,
        source=DAILY_GAME_LOG_CORRECTION_SOURCE,
        sync_run_id=sync_run_id,
        job_name=job_name,
    )

    # Backfill leverage index from the boxscore. A failed call or a missing LI
    # field just leaves the column as None — never crash the sync.
    if result['status'] != 'inserted':
        return result
    log = result['log']

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

    return result


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
        'games_retryable_incomplete': 0,
        'games_failed_markers': 0,
        'games_processed': 0,
        'games_incomplete': 0,
        'games_skipped': 0,
        'new_logs_added': 0,
        'logs_corrected': 0,
        'pitchers_touched': 0,
        'pitchers_updated': 0,
        'errors': 0,
        'records_failed': 0,
        'correction_attempts_failed': 0,
        'pitcher_resolution_failures': 0,
        'postgame_retry_exhausted': 0,
        'pitchers_created': 0,
        'pitchers_reactivated': 0,
        'completed_game_contexts_upserted': 0,
        'completed_game_context_errors': 0,
        'intelligence_snapshot': 'skipped',
        'message': '',
    }
    run_logger.info('── Postgame refresh starting (schedule_date=%s) ──', schedule_date)
    refresh_started = time.perf_counter()

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
            unprocessed_games, marker_counts = _unprocessed_completed_games(completed_games)
            status['completed_games_found'] = len(completed_games)
            status['newly_completed_games'] = len(unprocessed_games)
            status['games_already_processed'] = marker_counts['fully_processed']
            status['games_retryable_incomplete'] = marker_counts['retryable_incomplete']
            status['games_failed_markers'] = marker_counts['failed']
            run_logger.info(
                'Found %s completed game(s); %s fully processed, '
                '%s retryable incomplete, %s failed, %s pending.',
                len(completed_games),
                marker_counts['fully_processed'],
                marker_counts['retryable_incomplete'],
                marker_counts['failed'],
                len(unprocessed_games),
            )

            for game in unprocessed_games:
                game_pk = _game_pk(game)
                game_started = time.perf_counter()
                outcome = 'processed'
                try:
                    result = process_completed_game_for_postgame_refresh(
                        game,
                        schedule_date=schedule_date,
                        sync_run_id=sync_run_id,
                    )
                    db.session.commit()
                    if result.get('skipped'):
                        status['games_skipped'] += 1
                        outcome = 'skipped'
                        continue
                    fully_processed = (
                        result['processing_status']
                        == POSTGAME_MARKER_STATUS_FULLY_PROCESSED
                    )
                    if fully_processed:
                        status['games_processed'] += 1
                    else:
                        status['games_incomplete'] += 1
                        if result['processing_status'] == POSTGAME_MARKER_STATUS_FAILED:
                            status['games_failed_markers'] += 1
                        outcome = result['processing_status']
                    status['new_logs_added'] += result['logs_added']
                    status['logs_corrected'] += result['logs_corrected']
                    status['correction_attempts_failed'] += result['correction_attempts_failed']
                    status['pitcher_resolution_failures'] += result['pitcher_resolution_failures']
                    if result['retry_exhausted']:
                        status['postgame_retry_exhausted'] += 1
                    status['pitchers_created'] += result['pitchers_created']
                    status['pitchers_reactivated'] += result['pitchers_reactivated']
                    game_failure_count = (
                        result['correction_attempts_failed']
                        + result['pitcher_resolution_failures']
                    )
                    if fully_processed:
                        status['records_failed'] += game_failure_count
                    else:
                        status['records_failed'] += max(1, game_failure_count)
                    status['pitchers_touched'] += result['pitchers_touched']
                    run_logger.info(
                        'Postgame attempt for game %s: status=%s reason=%s '
                        'attempt=%s lines=%s; %s inserted, %s corrected, '
                        '%s unsafe correction(s), %s pitcher resolution failure(s), '
                        '%s pitcher(s).',
                        game_pk,
                        result['processing_status'],
                        result['incomplete_reason'],
                        result['attempt_count'],
                        result['pitching_lines_seen'],
                        result['logs_added'],
                        result['logs_corrected'],
                        result['correction_attempts_failed'],
                        result['pitcher_resolution_failures'],
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
                    outcome = 'failed'
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
                finally:
                    run_logger.info(
                        'postgame_refresh game_done game_pk=%s outcome=%s elapsed_ms=%s',
                        game_pk,
                        outcome,
                        round((time.perf_counter() - game_started) * 1000, 1),
                    )

            run_logger.info(
                'Postgame ingestion complete for %s: processed=%s skipped=%s '
                'incomplete=%s failed=%s contexts=%s logs_added=%s logs_corrected=%s '
                'pitchers_created=%s pitchers_reactivated=%s.',
                schedule_date,
                status['games_processed'],
                status['games_skipped'],
                status['games_incomplete'],
                status['records_failed'],
                status['completed_game_contexts_upserted'],
                status['new_logs_added'],
                status['logs_corrected'],
                status['pitchers_created'],
                status['pitchers_reactivated'],
            )

            changed_log_count = status['new_logs_added'] + status['logs_corrected']
            if changed_log_count > 0:
                sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_FATIGUE_RECALCULATION)
                fatigue_started = time.perf_counter()
                run_logger.info(
                    'Fatigue recalculation starting after postgame ingestion.'
                )
                pitchers_updated = recalculate_all_fatigue()
                status['pitchers_updated'] = pitchers_updated
                run_logger.info(
                    'Fatigue recalculation complete: pitchers_updated=%s '
                    'elapsed_ms=%s.',
                    pitchers_updated,
                    round((time.perf_counter() - fatigue_started) * 1000, 1),
                )
            else:
                run_logger.info(
                    'Fatigue recalculation skipped: no postgame logs changed.'
                )

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
                    f"{status['records_failed']} postgame record(s) incomplete or failed."
                )
            elif changed_log_count > 0:
                status['message'] = 'Updated after completed games.'
            elif status['newly_completed_games'] == 0:
                status['message'] = 'No newly completed games to process.'
            else:
                status['message'] = 'Completed games were checked; no tracked pitcher workload changed.'

            api_metrics = mlb_client.metrics.snapshot()
            if changed_log_count > 0:
                completed_run, snapshot = complete_sync_run_with_snapshot(
                    sync_run_id,
                    final_status=status['status'],
                    records_processed=changed_log_count,
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
    status['elapsed_ms'] = round((time.perf_counter() - refresh_started) * 1000, 1)
    write_status(status)
    run_logger.info(
        'postgame_refresh completed status=%s games_found=%s already_processed=%s '
        'processed=%s skipped=%s failed=%s logs_corrected=%s contexts=%s '
        'snapshot=%s elapsed_ms=%s',
        status['status'],
        status['completed_games_found'],
        status['games_already_processed'],
        status['games_processed'],
        status['games_skipped'],
        status['records_failed'],
        status['logs_corrected'],
        status['completed_game_contexts_upserted'],
        status['intelligence_snapshot'],
        status['elapsed_ms'],
    )
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
    product_day = resolve_product_day(started_at)
    sync_run_id = None
    run_logger.info('── Daily sync starting (days_back=%s) ──', days_back)

    status = {
        'last_sync':        started_at.isoformat(),
        'status':           sync_metadata.STATUS_SUCCESS,
        'pitchers_updated': 0,
        'new_logs_added':   0,
        'logs_corrected':   0,
        'errors':           0,
        'message':          '',
    }
    if product_day.limitations:
        status['limitations'] = list(product_day.limitations)

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
            pull = sync_recent_logs(
                days_back=days_back,
                reference_date=product_day.calendar_date,
                sync_run_id=sync_run_id,
            )
            logs_corrected = pull.get('logs_corrected', 0)
            correction_attempts_failed = pull.get('correction_attempts_failed', 0)
            run_logger.info(
                'Pulled %s new logs, corrected %s logs (touched %s pitchers, '
                '%s errors, %s dead-lettered)',
                pull['new_logs_added'], logs_corrected, pull['pitchers_touched'], pull['errors'],
                pull['records_failed'],
            )
            records_failed = (
                pull['records_failed']
                + team_assignment_records_failed
                + roster_records_failed
            )
            status['new_logs_added'] = pull['new_logs_added']
            status['logs_corrected'] = logs_corrected
            status['records_failed'] = records_failed
            status['correction_attempts_failed'] = correction_attempts_failed
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
                recent_cutoff = product_day.calendar_date - timedelta(days=days_back)
                recent_any = GameLog.query.filter(
                    GameLog.game_date >= recent_cutoff
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
            changed_log_count = pull['new_logs_added'] + logs_corrected
            completed_run, snapshot = complete_sync_run_with_snapshot(
                sync_run_id,
                final_status=final_status,
                records_processed=changed_log_count,
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
