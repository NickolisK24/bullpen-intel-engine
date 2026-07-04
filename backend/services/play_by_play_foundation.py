"""Final play-by-play foundation storage.

This module stores normalized final play-by-play facts only. It does not
interpret entry context, inherited traffic, leverage, role, or public evidence.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime

from models.pitcher import Pitcher
from models.play_by_play_foundation import (
    GamePlayByPlayEvent,
    PlayByPlayProcessedGame,
)
from services import dead_letter, sync_metadata
from services.game_finality import FINAL_AND_USABLE, classify_game_finality
from utils.db import db
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)

SOURCE = 'mlb_stats_api:final_play_by_play'
SOURCE_ENDPOINT = '/game/{gamePk}/playByPlay'
CORRECTION_SOURCE = 'final_play_by_play_rebuild'
RETRY_LIMIT = 3

FINAL_PBP_FETCH_ENTITY_TYPE = 'final_pbp_fetch'
FINAL_PBP_SHAPE_ENTITY_TYPE = 'final_pbp_shape'
FINAL_PBP_RECONCILIATION_ENTITY_TYPE = 'final_pbp_reconciliation'
FINAL_PBP_IDENTITY_ENTITY_TYPE = 'final_pbp_identity'
FINAL_PBP_FAILURE_ENTITY_TYPES = (
    FINAL_PBP_FETCH_ENTITY_TYPE,
    FINAL_PBP_SHAPE_ENTITY_TYPE,
    FINAL_PBP_RECONCILIATION_ENTITY_TYPE,
    FINAL_PBP_IDENTITY_ENTITY_TYPE,
)

EVENT_TYPE_PLATE_APPEARANCE = 'plate_appearance'
EVENT_TYPE_PITCHING_CHANGE = 'pitching_change'
EVENT_TYPE_SCORING_PLAY = 'scoring_play'
EVENT_TYPE_MOUND_VISIT = 'mound_visit'
EVENT_TYPE_UNKNOWN = 'unknown'

_PITCHING_CHANGE_CODES = frozenset({
    'pitching_substitution',
    'defensive_substitution',
    'substitution',
})
_MOUND_VISIT_CODES = frozenset({
    'mound_visit',
    'manager_visit',
})


def process_final_play_by_play_foundation(
    game: dict,
    *,
    boxscore: dict | None,
    play_by_play: dict | None,
    play_by_play_error=None,
    game_date: date | None = None,
    sync_run_id=None,
    job_name: str = sync_metadata.JOB_POSTGAME_REFRESH,
) -> dict:
    """Store normalized PBP events for one finality-certified game.

    The caller owns commit boundaries. Controlled source/shape/reconciliation
    failures are represented by the marker and dead-letter rows, not exceptions.
    """
    game_pk = _positive_int((game or {}).get('gamePk'))
    if game_pk is None:
        _record_failure(
            FINAL_PBP_IDENTITY_ENTITY_TYPE,
            'missing_game_pk',
            entity_ref=None,
            payload={'reason': 'missing_game_pk'},
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        return _result(None, 'skipped', reason='missing_game_pk')

    finality = classify_game_finality(game, boxscore=boxscore, require_boxscore=True)
    if finality.state != FINAL_AND_USABLE:
        return _result(
            game_pk,
            'skipped',
            reason=finality.reason,
            finality_state=finality.state,
        )

    resolved_game_date = _game_date(game, game_date)
    if resolved_game_date is None:
        _record_failure(
            FINAL_PBP_IDENTITY_ENTITY_TYPE,
            'missing_game_date',
            entity_ref=game_pk,
            payload={'game_pk': game_pk, 'reason': 'missing_game_date'},
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        marker = _upsert_marker(
            game_pk=game_pk,
            game=game,
            game_date=date.today(),
            finality_state=finality.state,
            status=PlayByPlayProcessedGame.STATUS_INCOMPLETE,
            reason='missing_game_date',
            events_seen=0,
            events_stored=0,
            pitcher_events_seen=0,
            unresolved_pitcher_count=0,
            reconciliation_mismatch_count=0,
            event_fingerprint=None,
            sync_run_id=sync_run_id,
        )
        return _result_from_marker(marker)

    home_team_id = _game_team_id(game, 'home')
    away_team_id = _game_team_id(game, 'away')
    if home_team_id is None or away_team_id is None:
        return _failure_marker(
            game_pk=game_pk,
            game=game,
            game_date=resolved_game_date,
            finality_state=finality.state,
            status=PlayByPlayProcessedGame.STATUS_INCOMPLETE,
            reason='missing_team_identity',
            entity_type=FINAL_PBP_IDENTITY_ENTITY_TYPE,
            payload={'home_team_id': home_team_id, 'away_team_id': away_team_id},
            sync_run_id=sync_run_id,
            job_name=job_name,
        )

    if play_by_play_error is not None:
        return _failure_marker(
            game_pk=game_pk,
            game=game,
            game_date=resolved_game_date,
            finality_state=finality.state,
            status=PlayByPlayProcessedGame.STATUS_INCOMPLETE,
            reason='play_by_play_fetch_failed',
            entity_type=FINAL_PBP_FETCH_ENTITY_TYPE,
            payload={'error': str(play_by_play_error)},
            sync_run_id=sync_run_id,
            job_name=job_name,
        )

    all_plays = (play_by_play or {}).get('allPlays') if isinstance(play_by_play, dict) else None
    if not isinstance(all_plays, list) or not all_plays:
        return _failure_marker(
            game_pk=game_pk,
            game=game,
            game_date=resolved_game_date,
            finality_state=finality.state,
            status=PlayByPlayProcessedGame.STATUS_ABSENT,
            reason='play_by_play_absent',
            entity_type=FINAL_PBP_SHAPE_ENTITY_TYPE,
            payload={'reason': 'play_by_play_absent'},
            sync_run_id=sync_run_id,
            job_name=job_name,
        )

    normalized = _normalize_events(
        all_plays,
        game_pk=game_pk,
        game_date=resolved_game_date,
        game_type=(game or {}).get('gameType'),
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        sync_run_id=sync_run_id,
    )
    if normalized['status'] != 'ok':
        return _failure_marker(
            game_pk=game_pk,
            game=game,
            game_date=resolved_game_date,
            finality_state=finality.state,
            status=PlayByPlayProcessedGame.STATUS_AMBIGUOUS,
            reason=normalized['reason'],
            entity_type=FINAL_PBP_SHAPE_ENTITY_TYPE,
            payload={
                'reason': normalized['reason'],
                'event_index': normalized.get('event_index'),
            },
            sync_run_id=sync_run_id,
            job_name=job_name,
        )

    events = normalized['events']
    if not events:
        return _failure_marker(
            game_pk=game_pk,
            game=game,
            game_date=resolved_game_date,
            finality_state=finality.state,
            status=PlayByPlayProcessedGame.STATUS_AMBIGUOUS,
            reason='play_by_play_no_complete_events',
            entity_type=FINAL_PBP_SHAPE_ENTITY_TYPE,
            payload={'reason': 'play_by_play_no_complete_events'},
            sync_run_id=sync_run_id,
            job_name=job_name,
        )

    reconciliation = _reconcile_pitchers(boxscore, events)
    event_fingerprint = _event_fingerprint(events)
    marker_status = PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED
    reason = None
    failure_entity_type = None
    failure_payload = None
    if reconciliation['unresolved_pitcher_count']:
        marker_status = PlayByPlayProcessedGame.STATUS_INCOMPLETE
        reason = 'unknown_pitcher_identity'
        failure_entity_type = FINAL_PBP_IDENTITY_ENTITY_TYPE
        failure_payload = {
            'unresolved_pitcher_count': reconciliation['unresolved_pitcher_count'],
        }
    elif reconciliation['reconciliation_mismatch_count']:
        marker_status = PlayByPlayProcessedGame.STATUS_INCOMPLETE
        reason = 'pitcher_reconciliation_mismatch'
        failure_entity_type = FINAL_PBP_RECONCILIATION_ENTITY_TYPE
        failure_payload = {
            'missing_boxscore_pitcher_ids': reconciliation['missing_boxscore_pitcher_ids'],
        }

    marker = _existing_marker(game_pk)
    if marker is not None and _marker_processing_status(marker) == PlayByPlayProcessedGame.STATUS_FAILED:
        if (marker.attempt_count or 0) >= RETRY_LIMIT:
            return _result_from_marker(marker, skipped=True, reason='retry_limit_reached')

    corrected = bool(
        marker is not None
        and marker.event_fingerprint
        and marker.event_fingerprint != event_fingerprint
    )
    rows_rebuilt = _replace_event_rows_if_needed(
        game_pk=game_pk,
        events=events,
        event_fingerprint=event_fingerprint,
        corrected=corrected,
        correction_count=((marker.correction_count or 0) + 1 if marker and corrected else 0),
        sync_run_id=sync_run_id,
    )

    marker = _upsert_marker(
        game_pk=game_pk,
        game=game,
        game_date=resolved_game_date,
        finality_state=finality.state,
        status=marker_status,
        reason=reason,
        events_seen=len(all_plays),
        events_stored=len(events),
        pitcher_events_seen=reconciliation['pitcher_events_seen'],
        unresolved_pitcher_count=reconciliation['unresolved_pitcher_count'],
        reconciliation_mismatch_count=reconciliation['reconciliation_mismatch_count'],
        event_fingerprint=event_fingerprint,
        sync_run_id=sync_run_id,
        corrected=corrected,
    )
    if failure_entity_type:
        _record_failure(
            failure_entity_type,
            reason,
            entity_ref=game_pk,
            payload={'game_pk': game_pk, **(failure_payload or {})},
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
    elif marker.processing_status == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED:
        for entity_type in FINAL_PBP_FAILURE_ENTITY_TYPES:
            dead_letter.resolve_entity_failures(entity_type, game_pk, job_name=job_name)

    result = _result_from_marker(marker)
    result['rows_rebuilt'] = rows_rebuilt
    result['corrected'] = corrected
    return result


def _failure_marker(
    *,
    game_pk,
    game,
    game_date,
    finality_state,
    status,
    reason,
    entity_type,
    payload,
    sync_run_id,
    job_name,
):
    marker = _upsert_marker(
        game_pk=game_pk,
        game=game,
        game_date=game_date,
        finality_state=finality_state,
        status=status,
        reason=reason,
        events_seen=0,
        events_stored=0,
        pitcher_events_seen=0,
        unresolved_pitcher_count=0,
        reconciliation_mismatch_count=0,
        event_fingerprint=None,
        sync_run_id=sync_run_id,
    )
    _record_failure(
        entity_type,
        reason,
        entity_ref=game_pk,
        payload={'game_pk': game_pk, **(payload or {})},
        sync_run_id=sync_run_id,
        job_name=job_name,
    )
    return _result_from_marker(marker)


def _normalize_events(
    all_plays,
    *,
    game_pk,
    game_date,
    game_type,
    home_team_id,
    away_team_id,
    sync_run_id,
):
    events = []
    prev_total_score = -1
    current_pitcher_by_fielding_team = {}
    pitcher_ids = _pitcher_ids_for_events(all_plays)
    local_pitcher_ids = _local_pitcher_ids(pitcher_ids)

    for index, play in enumerate(all_plays):
        if not isinstance(play, dict):
            return {'status': 'ambiguous', 'reason': 'non_object_play', 'event_index': index}

        about = play.get('about') or {}
        result = play.get('result') or {}
        matchup = play.get('matchup') or {}
        if about.get('isComplete') is False:
            continue

        inning = _positive_int(about.get('inning'), allow_zero=False)
        half_inning = _half_inning(about.get('halfInning'))
        home_score = _int_or_none(result.get('homeScore'))
        away_score = _int_or_none(result.get('awayScore'))
        if inning is None or half_inning is None or home_score is None or away_score is None:
            return {
                'status': 'ambiguous',
                'reason': 'missing_required_play_state',
                'event_index': index,
            }

        total_score = home_score + away_score
        if total_score < prev_total_score:
            return {
                'status': 'ambiguous',
                'reason': 'non_monotonic_score',
                'event_index': index,
            }
        prev_total_score = total_score

        pitcher_mlb_id = _positive_int(((matchup.get('pitcher') or {}).get('id')))
        batter_mlb_id = _positive_int(((matchup.get('batter') or {}).get('id')))
        is_top = half_inning == 'top'
        batting_team_id = away_team_id if is_top else home_team_id
        fielding_team_id = home_team_id if is_top else away_team_id
        event_code = _normalized_code(result.get('eventType'))
        is_score_event = bool(about.get('isScoringPlay')) or _score_increased(events, total_score)
        code_pitching_change = (
            event_code in _PITCHING_CHANGE_CODES
            or (event_code is not None and 'substitution' in event_code)
        )
        prior_pitcher = current_pitcher_by_fielding_team.get(fielding_team_id)
        sequence_pitching_change = (
            pitcher_mlb_id is not None
            and prior_pitcher is not None
            and prior_pitcher != pitcher_mlb_id
        )
        if pitcher_mlb_id is not None:
            current_pitcher_by_fielding_team[fielding_team_id] = pitcher_mlb_id
        is_pitching_change = code_pitching_change or sequence_pitching_change
        is_mound_visit = (
            event_code in _MOUND_VISIT_CODES
            or (event_code is not None and 'mound_visit' in event_code)
        )
        event_type = _event_type(
            is_pitching_change=is_pitching_change,
            is_mound_visit=is_mound_visit,
            is_scoring_play=is_score_event,
            at_bat_index=_int_or_none(about.get('atBatIndex')),
        )
        events.append({
            'mlb_game_pk': game_pk,
            'event_index': index,
            'source_play_id': _source_play_id(play, about),
            'at_bat_index': _int_or_none(about.get('atBatIndex')),
            'game_date': game_date,
            'game_type': game_type,
            'home_team_id': home_team_id,
            'away_team_id': away_team_id,
            'event_type': event_type,
            'event_type_code': event_code,
            'inning': inning,
            'half_inning': half_inning,
            'is_top_inning': is_top,
            'outs_at_event': _int_or_none(about.get('outs')),
            'home_score_at_event': home_score,
            'away_score_at_event': away_score,
            'pitcher_mlb_id': pitcher_mlb_id,
            'pitcher_id': local_pitcher_ids.get(pitcher_mlb_id),
            'batter_mlb_id': batter_mlb_id,
            'batting_team_id': batting_team_id,
            'fielding_team_id': fielding_team_id,
            'is_pitching_change': is_pitching_change,
            'is_scoring_play': is_score_event,
            'is_mound_visit': is_mound_visit,
            'source': SOURCE,
            'source_endpoint': SOURCE_ENDPOINT.format(gamePk=game_pk),
            'sync_run_id': sync_run_id,
        })

    return {'status': 'ok', 'events': events}


def _replace_event_rows_if_needed(
    *,
    game_pk,
    events,
    event_fingerprint,
    corrected,
    correction_count,
    sync_run_id,
) -> bool:
    existing_marker = _existing_marker(game_pk)
    existing_count = GamePlayByPlayEvent.query.filter_by(mlb_game_pk=game_pk).count()
    unchanged = (
        existing_marker is not None
        and existing_marker.event_fingerprint == event_fingerprint
        and existing_count == len(events)
    )
    if unchanged:
        return False

    GamePlayByPlayEvent.query.filter_by(mlb_game_pk=game_pk).delete(
        synchronize_session=False,
    )
    now = utc_now_naive()
    for event_values in events:
        row_values = dict(event_values)
        row_values['sync_run_id'] = sync_run_id
        row_values['created_at'] = now
        row_values['updated_at'] = now
        row_values['first_seen_at'] = now
        if corrected:
            row_values['correction_count'] = correction_count
            row_values['last_corrected_at'] = now
            row_values['correction_source'] = CORRECTION_SOURCE
        db.session.add(GamePlayByPlayEvent(**row_values))
    return True


def _upsert_marker(
    *,
    game_pk,
    game,
    game_date,
    finality_state,
    status,
    reason,
    events_seen,
    events_stored,
    pitcher_events_seen,
    unresolved_pitcher_count,
    reconciliation_mismatch_count,
    event_fingerprint,
    sync_run_id,
    corrected=False,
):
    marker = _existing_marker(game_pk) or PlayByPlayProcessedGame(mlb_game_pk=game_pk)
    previous_status = _marker_processing_status(marker)
    attempt_count = (marker.attempt_count or 0) + 1
    final_status = _status_for_attempt(status, attempt_count)
    now = utc_now_naive()

    marker.game_date = game_date
    marker.game_type = (game or {}).get('gameType')
    marker.home_team_id = _game_team_id(game, 'home')
    marker.away_team_id = _game_team_id(game, 'away')
    marker.final_state = finality_state
    marker.processing_status = final_status
    marker.attempt_count = attempt_count
    marker.last_attempted_at = now
    marker.incomplete_reason = None if final_status == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED else reason
    marker.events_seen = events_seen
    marker.events_stored = events_stored
    marker.pitcher_events_seen = pitcher_events_seen
    marker.unresolved_pitcher_count = unresolved_pitcher_count
    marker.reconciliation_mismatch_count = reconciliation_mismatch_count
    marker.event_fingerprint = event_fingerprint
    marker.source = SOURCE
    marker.source_endpoint = SOURCE_ENDPOINT.format(gamePk=game_pk)
    marker.sync_run_id = sync_run_id
    if final_status == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED:
        marker.processed_at = now
        marker.failed_at = None
    elif final_status == PlayByPlayProcessedGame.STATUS_FAILED:
        marker.processed_at = None
        marker.failed_at = marker.failed_at or now
    else:
        marker.processed_at = None
        marker.failed_at = None
    if corrected:
        marker.correction_count = (marker.correction_count or 0) + 1
        marker.last_corrected_at = now
        marker.correction_source = CORRECTION_SOURCE
    elif previous_status is None:
        marker.first_seen_at = marker.first_seen_at or now

    db.session.add(marker)
    return marker


def _status_for_attempt(status, attempt_count):
    if status == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED:
        return status
    if attempt_count >= RETRY_LIMIT:
        return PlayByPlayProcessedGame.STATUS_FAILED
    return status


def _marker_processing_status(marker):
    return getattr(marker, 'processing_status', None) if marker is not None else None


def _existing_marker(game_pk):
    return PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=game_pk).first()


def _reconcile_pitchers(boxscore, events):
    boxscore_pitchers = _boxscore_pitcher_ids(boxscore)
    pbp_pitchers = {event['pitcher_mlb_id'] for event in events if event.get('pitcher_mlb_id')}
    unresolved = sum(1 for event in events if event.get('pitcher_mlb_id') is None)
    missing = sorted(boxscore_pitchers - pbp_pitchers)
    return {
        'pitcher_events_seen': len(pbp_pitchers),
        'unresolved_pitcher_count': unresolved,
        'reconciliation_mismatch_count': len(missing),
        'missing_boxscore_pitcher_ids': missing,
    }


def _boxscore_pitcher_ids(boxscore):
    ids = set()
    teams = (boxscore or {}).get('teams') or {}
    for side in ('home', 'away'):
        side_data = teams.get(side) or {}
        players = side_data.get('players') or {}
        for raw_id in side_data.get('pitchers') or []:
            pitcher_id = _positive_int(raw_id)
            if pitcher_id is None:
                continue
            player = players.get(f'ID{pitcher_id}') or {}
            stats = ((player.get('stats') or {}).get('pitching') or {})
            if stats:
                ids.add(pitcher_id)
    return ids


def _event_fingerprint(events):
    payload = [
        {
            key: _fingerprint_value(event.get(key))
            for key in (
                'mlb_game_pk',
                'event_index',
                'source_play_id',
                'at_bat_index',
                'game_date',
                'game_type',
                'home_team_id',
                'away_team_id',
                'event_type',
                'event_type_code',
                'inning',
                'half_inning',
                'is_top_inning',
                'outs_at_event',
                'home_score_at_event',
                'away_score_at_event',
                'pitcher_mlb_id',
                'pitcher_id',
                'batter_mlb_id',
                'batting_team_id',
                'fielding_team_id',
                'is_pitching_change',
                'is_scoring_play',
                'is_mound_visit',
            )
        }
        for event in events
    ]
    data = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def _fingerprint_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _record_failure(entity_type, error, *, entity_ref, payload, sync_run_id, job_name):
    return dead_letter.record_failure(
        entity_type,
        error,
        entity_ref=entity_ref,
        payload=payload,
        sync_run_id=sync_run_id,
        job_name=job_name,
    )


def _pitcher_ids_for_events(all_plays):
    ids = set()
    for play in all_plays:
        if not isinstance(play, dict):
            continue
        pitcher_id = _positive_int((((play.get('matchup') or {}).get('pitcher') or {}).get('id')))
        if pitcher_id is not None:
            ids.add(pitcher_id)
    return ids


def _local_pitcher_ids(pitcher_ids):
    if not pitcher_ids:
        return {}
    return {
        pitcher.mlb_id: pitcher.id
        for pitcher in Pitcher.query.filter(Pitcher.mlb_id.in_(sorted(pitcher_ids))).all()
    }


def _score_increased(events, total_score):
    if not events:
        return total_score > 0
    previous = events[-1]['home_score_at_event'] + events[-1]['away_score_at_event']
    return total_score > previous


def _event_type(*, is_pitching_change, is_mound_visit, is_scoring_play, at_bat_index):
    if is_pitching_change:
        return EVENT_TYPE_PITCHING_CHANGE
    if is_mound_visit:
        return EVENT_TYPE_MOUND_VISIT
    if is_scoring_play:
        return EVENT_TYPE_SCORING_PLAY
    if at_bat_index is not None:
        return EVENT_TYPE_PLATE_APPEARANCE
    return EVENT_TYPE_UNKNOWN


def _source_play_id(play, about):
    value = play.get('playId') or about.get('playId') or about.get('eventId')
    if value in (None, ''):
        return None
    return str(value)[:80]


def _normalized_code(value):
    if value in (None, ''):
        return None
    return str(value).strip().lower().replace(' ', '_')[:40]


def _half_inning(value):
    normalized = str(value or '').strip().lower()
    return normalized if normalized in {'top', 'bottom'} else None


def _game_date(game, fallback):
    if isinstance(fallback, date):
        return fallback
    raw = (game or {}).get('officialDate') or str((game or {}).get('gameDate') or '')[:10]
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _game_team_id(game, side):
    return _positive_int(((((game or {}).get('teams') or {}).get(side) or {}).get('team') or {}).get('id'))


def _positive_int(value, *, allow_zero=False):
    parsed = _int_or_none(value)
    if parsed is None:
        return None
    if allow_zero:
        return parsed if parsed >= 0 else None
    return parsed if parsed > 0 else None


def _int_or_none(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _result(game_pk, status, *, reason=None, finality_state=None):
    return {
        'game_pk': game_pk,
        'processing_status': status,
        'reason': reason,
        'finality_state': finality_state,
        'events_seen': 0,
        'events_stored': 0,
        'pitcher_events_seen': 0,
        'unresolved_pitcher_count': 0,
        'reconciliation_mismatch_count': 0,
        'attempt_count': 0,
        'skipped': status == 'skipped',
    }


def _result_from_marker(marker, *, skipped=False, reason=None):
    return {
        'game_pk': marker.mlb_game_pk,
        'processing_status': marker.processing_status,
        'reason': reason or marker.incomplete_reason,
        'finality_state': marker.final_state,
        'events_seen': marker.events_seen or 0,
        'events_stored': marker.events_stored or 0,
        'pitcher_events_seen': marker.pitcher_events_seen or 0,
        'unresolved_pitcher_count': marker.unresolved_pitcher_count or 0,
        'reconciliation_mismatch_count': marker.reconciliation_mismatch_count or 0,
        'attempt_count': marker.attempt_count or 0,
        'skipped': skipped,
    }
