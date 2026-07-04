from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable, Mapping

from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from utils.db import db


REASON_SLATE_COMPLETE = 'slate_complete'
REASON_NO_SCHEDULED_GAMES = 'no_scheduled_games'
REASON_SCHEDULE_MISSING = 'schedule_missing'
REASON_FINAL_GAMES_NOT_FULLY_INGESTED = 'final_games_not_fully_ingested'
REASON_POSTGAME_MARKERS_INCOMPLETE = 'postgame_markers_incomplete'
REASON_POSTGAME_MARKERS_FAILED = 'postgame_markers_failed'
REASON_PARTIAL_SYNC = 'partial_sync'
REASON_VALIDATIONS_FAILED = 'validations_failed'
REASON_COMPLETENESS_UNKNOWN = 'completeness_unknown'
REASON_SCHEDULED_GAMES_NOT_FINAL = 'scheduled_games_not_final'
REASON_SUSPENDED_GAMES_NOT_FINAL = 'suspended_games_not_final'

DIAGNOSTIC_MISSING_MARKER = 'missing_marker'
DIAGNOSTIC_INCOMPLETE_MARKER = 'incomplete_marker'
DIAGNOSTIC_FAILED_MARKER = 'failed_marker'


_OFFSEASON_MONTHS = {1, 2, 11, 12}
_SCHEDULE_CONTEXT_WINDOW_DAYS = 7

_REASON_MESSAGES = {
    REASON_SCHEDULE_MISSING: 'Scheduled game coverage is missing for this slate.',
    REASON_FINAL_GAMES_NOT_FULLY_INGESTED: (
        'Final games are not fully ingested for this slate.'
    ),
    REASON_POSTGAME_MARKERS_INCOMPLETE: (
        'One or more final games still have incomplete postgame processing markers.'
    ),
    REASON_POSTGAME_MARKERS_FAILED: (
        'One or more final games have failed postgame processing markers.'
    ),
    REASON_PARTIAL_SYNC: 'The latest sync completed partially and cannot prove slate completeness.',
    REASON_VALIDATIONS_FAILED: 'Slate coverage validations did not pass.',
    REASON_COMPLETENESS_UNKNOWN: 'Slate completeness cannot be proven from stored coverage.',
    REASON_SCHEDULED_GAMES_NOT_FINAL: 'Scheduled games on this slate are not final yet.',
    REASON_SUSPENDED_GAMES_NOT_FINAL: 'Suspended games on this slate are not final.',
}


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _unique(values):
    result = []
    seen = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _reason_messages(reason_codes):
    return [
        _REASON_MESSAGES[code]
        for code in reason_codes
        if code in _REASON_MESSAGES
    ]


def _iso_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _schedule_rows_for_date(slate_date):
    return (
        ScheduledGame.query
        .filter(ScheduledGame.game_date == slate_date)
        .all()
    )


def _has_schedule_material_near(slate_date):
    start = slate_date - timedelta(days=_SCHEDULE_CONTEXT_WINDOW_DAYS)
    end = slate_date + timedelta(days=_SCHEDULE_CONTEXT_WINDOW_DAYS)
    return (
        db.session.query(ScheduledGame.id)
        .filter(ScheduledGame.game_date >= start)
        .filter(ScheduledGame.game_date <= end)
        .first()
        is not None
    )


def _is_offseason_date(slate_date):
    return slate_date.month in _OFFSEASON_MONTHS


def _collapse_status(statuses):
    normalized = {status or ScheduledGame.STATE_OTHER for status in statuses}
    if normalized == {ScheduledGame.STATE_FINAL}:
        return ScheduledGame.STATE_FINAL
    if ScheduledGame.STATE_POSTPONED in normalized:
        return ScheduledGame.STATE_POSTPONED
    if ScheduledGame.STATE_SUSPENDED in normalized:
        return ScheduledGame.STATE_SUSPENDED
    if normalized == {ScheduledGame.STATE_SCHEDULED}:
        return ScheduledGame.STATE_SCHEDULED
    return ScheduledGame.STATE_OTHER


def _side_team_id(rows, side):
    for row in rows:
        if getattr(row, 'home_away', None) == side:
            team_id = getattr(row, 'team_id', None)
            if team_id is not None:
                return int(team_id)

    opposite_side = 'away' if side == 'home' else 'home'
    for row in rows:
        if getattr(row, 'home_away', None) == opposite_side:
            team_id = getattr(row, 'opponent_team_id', None)
            if team_id is not None:
                return int(team_id)
    return None


def _collapsed_field(rows, field_name):
    values = _unique(getattr(row, field_name, None) for row in rows)
    return values[0] if len(values) == 1 else None


def _scheduled_games(schedule_rows):
    grouped = defaultdict(list)
    for row in schedule_rows or []:
        game_pk = getattr(row, 'game_pk', None)
        if game_pk is None:
            continue
        grouped[int(game_pk)].append(row)

    games = []
    for game_pk, rows in grouped.items():
        status = _collapse_status(getattr(row, 'status_state', None) for row in rows)
        games.append({
            'game_pk': game_pk,
            'status_state': status,
            'status_code': _collapsed_field(rows, 'status_code'),
            'game_type': _collapsed_field(rows, 'game_type'),
            'home_team': _side_team_id(rows, 'home'),
            'away_team': _side_team_id(rows, 'away'),
            'row_count': len(rows),
        })
    games.sort(key=lambda item: item['game_pk'])
    return games


def _markers_by_game_pk(game_pks, markers=None):
    if markers is None:
        markers = (
            PostgameProcessedGame.query
            .filter(PostgameProcessedGame.mlb_game_pk.in_(list(game_pks)))
            .all()
            if game_pks
            else []
        )
    return {
        int(marker.mlb_game_pk): marker
        for marker in markers or []
        if getattr(marker, 'mlb_game_pk', None) is not None
    }


def _marker_status(marker):
    if marker is None:
        return None
    return (
        marker.processing_status
        or PostgameProcessedGame.STATUS_FULLY_PROCESSED
    )


def _postgame_blocker_reason(marker):
    status = _marker_status(marker)
    if marker is None:
        return DIAGNOSTIC_MISSING_MARKER
    if status == PostgameProcessedGame.STATUS_FAILED:
        return DIAGNOSTIC_FAILED_MARKER
    if status == PostgameProcessedGame.STATUS_FULLY_PROCESSED:
        return None
    return DIAGNOSTIC_INCOMPLETE_MARKER


def _postgame_blocker_diagnostic(ref, game, marker, reason_code):
    marker_status = _marker_status(marker) or 'missing'
    home_team = game.get('home_team')
    away_team = game.get('away_team')
    if marker is not None:
        home_team = getattr(marker, 'home_team_id', None) or home_team
        away_team = getattr(marker, 'away_team_id', None) or away_team

    return {
        'slate_date': ref.isoformat(),
        'mlb_game_pk': game['game_pk'],
        'away_team': away_team,
        'home_team': home_team,
        'game_status': game.get('status_code') or game.get('status_state'),
        'status_state': game.get('status_state'),
        'marker_status': marker_status,
        'incomplete_reason': (
            getattr(marker, 'incomplete_reason', None)
            if marker is not None
            else None
        ),
        'attempt_count': (
            getattr(marker, 'attempt_count', None) or 0
            if marker is not None
            else 0
        ),
        'pitching_lines_seen': (
            getattr(marker, 'pitching_lines_seen', None) or 0
            if marker is not None
            else 0
        ),
        'pitcher_resolution_failures': (
            getattr(marker, 'pitcher_resolution_failures', None) or 0
            if marker is not None
            else 0
        ),
        'correction_attempts_failed': (
            getattr(marker, 'correction_attempts_failed', None) or 0
            if marker is not None
            else 0
        ),
        'failed_at': (
            _iso_datetime(getattr(marker, 'failed_at', None))
            if marker is not None
            else None
        ),
        'last_attempted_at': (
            _iso_datetime(getattr(marker, 'last_attempted_at', None))
            if marker is not None
            else None
        ),
        'reason_code': reason_code,
    }


def _postgame_blocker_diagnostics(ref, final_games, markers):
    diagnostics = []
    for game in sorted(final_games, key=lambda item: item['game_pk']):
        marker = markers.get(game['game_pk'])
        reason_code = _postgame_blocker_reason(marker)
        if reason_code is None:
            continue
        diagnostics.append(_postgame_blocker_diagnostic(ref, game, marker, reason_code))
    return diagnostics


def _slate_diagnostics(ref, postgame_blockers=None):
    blockers = postgame_blockers or []
    return {
        'slate_date': ref.isoformat() if ref else None,
        'postgame_blocker_count': len(blockers),
        'postgame_blockers': blockers,
    }


def unknown_slate_coverage(slate_date=None, *, reason_code=REASON_COMPLETENESS_UNKNOWN):
    ref = _as_date(slate_date)
    reason_codes = _unique([reason_code, REASON_VALIDATIONS_FAILED])
    return {
        'slate_date': ref.isoformat() if ref else None,
        'games_scheduled': 0,
        'games_final': 0,
        'games_fully_ingested': 0,
        'games_incomplete': 0,
        'games_failed': 0,
        'games_postponed': 0,
        'games_suspended': 0,
        'games_included': 0,
        'validations_passed': False,
        'complete_enough_to_publish': False,
        'coverage_known': False,
        'reason_codes': reason_codes,
        'degradation_reasons': _reason_messages(reason_codes),
        'marker_counts': {
            'fully_processed': 0,
            'incomplete': 0,
            'failed': 0,
            'missing': 0,
        },
    }


def compute_slate_coverage(
    slate_date,
    *,
    sync_status=None,
    schedule_rows: Iterable[ScheduledGame] | None = None,
    postgame_markers: Iterable[PostgameProcessedGame] | None = None,
    schedule_material_available: bool | None = None,
    include_diagnostics: bool = False,
):
    ref = _as_date(slate_date)
    if ref is None:
        payload = unknown_slate_coverage(None)
        if include_diagnostics:
            payload['diagnostics'] = _slate_diagnostics(None)
        return payload

    rows = list(schedule_rows) if schedule_rows is not None else _schedule_rows_for_date(ref)
    games = _scheduled_games(rows)

    if schedule_material_available is None:
        schedule_material_available = bool(rows) or _has_schedule_material_near(ref)

    if not games:
        if schedule_material_available or _is_offseason_date(ref):
            partial_sync = sync_status == 'partial'
            reason_codes = [REASON_NO_SCHEDULED_GAMES]
            if partial_sync:
                reason_codes.extend([REASON_PARTIAL_SYNC, REASON_VALIDATIONS_FAILED])
            else:
                reason_codes.append(REASON_SLATE_COMPLETE)
            payload = {
                'slate_date': ref.isoformat(),
                'games_scheduled': 0,
                'games_final': 0,
                'games_fully_ingested': 0,
                'games_incomplete': 0,
                'games_failed': 0,
                'games_postponed': 0,
                'games_suspended': 0,
                'games_included': 0,
                'validations_passed': not partial_sync,
                'complete_enough_to_publish': not partial_sync,
                'coverage_known': True,
                'reason_codes': reason_codes,
                'degradation_reasons': _reason_messages(reason_codes),
                'marker_counts': {
                    'fully_processed': 0,
                    'incomplete': 0,
                    'failed': 0,
                    'missing': 0,
                },
            }
            if include_diagnostics:
                payload['diagnostics'] = _slate_diagnostics(ref)
            return payload
        payload = unknown_slate_coverage(ref, reason_code=REASON_SCHEDULE_MISSING)
        if include_diagnostics:
            payload['diagnostics'] = _slate_diagnostics(ref)
        return payload

    included_games = [
        game for game in games
        if game['status_state'] != ScheduledGame.STATE_POSTPONED
    ]
    final_games = [
        game for game in included_games
        if game['status_state'] == ScheduledGame.STATE_FINAL
    ]
    final_game_pks = {game['game_pk'] for game in final_games}
    markers = _markers_by_game_pk(final_game_pks, postgame_markers)

    marker_counts = {
        'fully_processed': 0,
        'incomplete': 0,
        'failed': 0,
        'missing': 0,
    }
    fully_ingested = 0
    failed_markers = 0
    incomplete_markers = 0
    missing_markers = 0

    for game_pk in final_game_pks:
        status = _marker_status(markers.get(game_pk))
        if status == PostgameProcessedGame.STATUS_FULLY_PROCESSED:
            marker_counts['fully_processed'] += 1
            fully_ingested += 1
        elif status == PostgameProcessedGame.STATUS_FAILED:
            marker_counts['failed'] += 1
            failed_markers += 1
        elif status == PostgameProcessedGame.STATUS_INCOMPLETE:
            marker_counts['incomplete'] += 1
            incomplete_markers += 1
        else:
            marker_counts['missing'] += 1
            missing_markers += 1

    scheduled_not_final = sum(
        1
        for game in included_games
        if game['status_state'] == ScheduledGame.STATE_SCHEDULED
    )
    suspended_not_final = sum(
        1
        for game in included_games
        if game['status_state'] == ScheduledGame.STATE_SUSPENDED
    )
    other_not_final = sum(
        1
        for game in included_games
        if game['status_state'] == ScheduledGame.STATE_OTHER
    )
    non_final_included = scheduled_not_final + suspended_not_final + other_not_final
    incomplete_games = max(len(included_games) - fully_ingested, 0)

    reason_codes = []
    if scheduled_not_final or other_not_final:
        reason_codes.append(REASON_SCHEDULED_GAMES_NOT_FINAL)
    if suspended_not_final:
        reason_codes.append(REASON_SUSPENDED_GAMES_NOT_FINAL)
    if len(final_games) > fully_ingested:
        reason_codes.append(REASON_FINAL_GAMES_NOT_FULLY_INGESTED)
    if incomplete_markers or missing_markers:
        reason_codes.append(REASON_POSTGAME_MARKERS_INCOMPLETE)
    if failed_markers:
        reason_codes.append(REASON_POSTGAME_MARKERS_FAILED)
    if non_final_included:
        reason_codes.append(REASON_COMPLETENESS_UNKNOWN)
    if sync_status == 'partial':
        reason_codes.append(REASON_PARTIAL_SYNC)

    validations_passed = not reason_codes
    if validations_passed:
        reason_codes.append(REASON_SLATE_COMPLETE)
    else:
        reason_codes.append(REASON_VALIDATIONS_FAILED)

    reason_codes = _unique(reason_codes)
    complete_enough = validations_passed and sync_status != 'partial'

    payload = {
        'slate_date': ref.isoformat(),
        'games_scheduled': len(games),
        'games_final': len(final_games),
        'games_fully_ingested': fully_ingested,
        'games_incomplete': incomplete_games,
        'games_failed': failed_markers,
        'games_postponed': sum(
            1 for game in games
            if game['status_state'] == ScheduledGame.STATE_POSTPONED
        ),
        'games_suspended': sum(
            1 for game in games
            if game['status_state'] == ScheduledGame.STATE_SUSPENDED
        ),
        'games_included': len(included_games),
        'validations_passed': validations_passed,
        'complete_enough_to_publish': complete_enough,
        'coverage_known': True,
        'reason_codes': reason_codes,
        'degradation_reasons': _reason_messages(reason_codes),
        'marker_counts': marker_counts,
    }
    if include_diagnostics:
        payload['diagnostics'] = _slate_diagnostics(
            ref,
            _postgame_blocker_diagnostics(ref, final_games, markers),
        )
    return payload


def append_slate_coverage_to_freshness(freshness: Mapping | None, coverage: Mapping | None):
    result = dict(freshness or {})
    slate_coverage = dict(coverage or unknown_slate_coverage())
    result['slate_coverage'] = slate_coverage
    result['validations_passed'] = bool(slate_coverage.get('validations_passed'))
    result['complete_enough_to_publish'] = bool(
        slate_coverage.get('complete_enough_to_publish')
    )

    if slate_coverage.get('complete_enough_to_publish') is True:
        return result

    existing_state = result.get('freshness_state')
    if existing_state in {'missing', 'metadata_unavailable', 'snapshot_unavailable'}:
        result['is_current'] = False
        return result

    existing_reason_codes = list(result.get('reason_codes') or [])
    coverage_reason_codes = [
        code for code in slate_coverage.get('reason_codes') or []
        if code != REASON_SLATE_COMPLETE
    ]
    result['reason_codes'] = _unique(existing_reason_codes + coverage_reason_codes)
    result['limitations'] = _unique(
        list(result.get('limitations') or [])
        + list(slate_coverage.get('degradation_reasons') or [])
    )
    result['is_current'] = False
    result['freshness_state'] = 'incomplete'
    result['label'] = (
        f"Baseball data through {slate_coverage.get('slate_date') or 'the slate'} "
        'is incomplete and is not publishable as current.'
    )
    degradation = dict(result.get('degradation') or {})
    degradation['slate_coverage_state'] = 'incomplete'
    degradation['complete_enough_to_publish'] = False
    result['degradation'] = degradation
    return result
