"""Derived team-game starter/bullpen split and calendar facts.

Phase 0C stores descriptive source-derived facts only. This module does not
interpret short starts, pressure, role, opener/bulk usage, or travel effects.
"""

from __future__ import annotations

from datetime import date, timedelta
import logging

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from models.team_game_pitching_split import TeamGamePitchingSplit
from services import dead_letter, sync_metadata
from services.game_finality import (
    FINAL_AND_USABLE,
    classify_game_finality,
    has_safe_final_status,
    scheduled_rows_have_unresolved_resumed_linkage,
)
from utils.db import db
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)

SOURCE = 'derived:game_logs_schedule'
CORRECTION_SOURCE = 'team_game_pitching_split_recompute'
TEAM_GAME_PITCHING_SPLIT_FAILURE_ENTITY_TYPE = 'team_game_pitching_split_derivation'

_SPLIT_VALUE_FIELDS = (
    'game_date',
    'game_type',
    'opponent_team_id',
    'home_away',
    'starter_pitcher_id',
    'starter_mlb_id',
    'starter_identity_status',
    'starter_outs_recorded',
    'starter_pitches_thrown',
    'starter_batters_faced',
    'starter_balls',
    'starter_games_started',
    'bullpen_outs_recorded',
    'bullpen_pitches_thrown',
    'bullpen_batters_faced',
    'bullpen_balls',
    'relievers_used_count',
    'total_team_outs',
    'total_team_pitches',
    'total_team_batters_faced',
    'total_team_balls',
    'split_completeness_status',
    'split_reason_codes',
    'off_day_before',
    'off_day_after',
    'consecutive_game_day_count_entering',
    'series_game_number',
    'games_in_series',
    'doubleheader_flag',
    'doubleheader_code',
    'game_number',
    'postponed_or_makeup_indicator',
    'suspended_resumed_linkage_status',
    'extra_inning_indicator',
    'calendar_context_status',
    'calendar_reason_codes',
    'source',
)


def recompute_team_game_pitching_splits_for_game(
    mlb_game_pk,
    *,
    game: dict | None = None,
    game_date: date | None = None,
    sync_run_id=None,
) -> dict:
    """Recompute stored split/calendar facts for one MLB game.

    Adds rows to the current DB session and flushes. The caller owns commit
    boundaries.
    """
    game_pk = _positive_int(mlb_game_pk)
    if game_pk is None:
        return _result(None, status='skipped', reason='missing_game_pk')

    scheduled_rows = _scheduled_rows_for_game(game_pk)
    final_gate = _final_gate(game_pk, scheduled_rows, game)
    if not final_gate['eligible']:
        return _result(game_pk, status='skipped', reason=final_gate['reason'])

    contexts = _team_contexts(
        game_pk=game_pk,
        scheduled_rows=scheduled_rows,
        game=game,
        fallback_game_date=game_date,
    )
    if not contexts:
        return _result(game_pk, status='skipped', reason='missing_team_identity')

    log_rows = _game_log_rows(game_pk)
    logs_by_team = _logs_by_team(log_rows)
    team_total_outs = {
        team_id: _nullable_sum([row['log'] for row in rows], 'innings_pitched_outs')
        for team_id, rows in logs_by_team.items()
    }
    extra_inning_indicator = _extra_inning_indicator(contexts, team_total_outs)
    schedule_ambiguous = final_gate['reason'] == 'suspended_resumed_ambiguous'

    inserted = 0
    corrected = 0
    unchanged = 0
    statuses = []
    calendar_statuses = []
    reason_codes = []
    for context in contexts:
        values = _split_values(
            context,
            logs_by_team.get(context['team_id'], []),
            schedule_ambiguous=schedule_ambiguous,
            extra_inning_indicator=extra_inning_indicator,
        )
        status = _upsert_split(values, sync_run_id=sync_run_id)
        if status == 'inserted':
            inserted += 1
        elif status == 'corrected':
            corrected += 1
        else:
            unchanged += 1
        statuses.append(values['split_completeness_status'])
        calendar_statuses.append(values['calendar_context_status'])
        reason_codes.extend(values.get('split_reason_codes') or [])
        reason_codes.extend(values.get('calendar_reason_codes') or [])

    db.session.flush()
    return {
        'game_pk': game_pk,
        'status': 'processed',
        'rows_inserted': inserted,
        'rows_corrected': corrected,
        'rows_unchanged': unchanged,
        'rows_total': len(contexts),
        'split_statuses': statuses,
        'calendar_statuses': calendar_statuses,
        'reason_codes': _dedupe(reason_codes),
    }


def safe_recompute_team_game_pitching_splits_for_game(
    mlb_game_pk,
    *,
    game: dict | None = None,
    game_date: date | None = None,
    sync_run_id=None,
    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
) -> dict:
    try:
        return recompute_team_game_pitching_splits_for_game(
            mlb_game_pk,
            game=game,
            game_date=game_date,
            sync_run_id=sync_run_id,
        )
    except Exception as exc:  # noqa: BLE001 - derived storage fails closed
        db.session.rollback()
        dead_letter.record_failure(
            TEAM_GAME_PITCHING_SPLIT_FAILURE_ENTITY_TYPE,
            exc,
            entity_ref=mlb_game_pk,
            payload={'game_pk': mlb_game_pk},
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        db.session.flush()
        logger.warning(
            'Team-game pitching split recompute failed for game_pk=%s: %s',
            mlb_game_pk,
            exc,
        )
        return _result(mlb_game_pk, status='failed', reason=str(exc))


def _final_gate(game_pk, scheduled_rows, game):
    if scheduled_rows:
        if scheduled_rows_have_unresolved_resumed_linkage(scheduled_rows):
            return {'eligible': True, 'reason': 'suspended_resumed_ambiguous'}
        if not all(row.status_state == ScheduledGame.STATE_FINAL for row in scheduled_rows):
            return {'eligible': False, 'reason': 'not_final'}
        return {'eligible': True, 'reason': None}

    if game is not None:
        finality = classify_game_finality(game)
        if finality.state == FINAL_AND_USABLE or has_safe_final_status(game):
            return {'eligible': True, 'reason': 'schedule_missing'}
    return {'eligible': False, 'reason': 'missing_final_schedule'}


def _team_contexts(*, game_pk, scheduled_rows, game, fallback_game_date):
    if scheduled_rows:
        return [
            {
                'team_id': row.team_id,
                'mlb_game_pk': game_pk,
                'game_date': row.game_date,
                'game_type': row.game_type,
                'opponent_team_id': row.opponent_team_id,
                'home_away': row.home_away,
                'scheduled_row': row,
                'calendar_available': True,
                'calendar_missing_reason': None,
            }
            for row in sorted(scheduled_rows, key=lambda item: (item.home_away or '', item.team_id))
        ]

    if not isinstance(game, dict):
        return []
    game_date = _game_date(game, fallback_game_date)
    contexts = []
    home_id = _game_team_id(game, 'home')
    away_id = _game_team_id(game, 'away')
    if home_id is not None:
        contexts.append({
            'team_id': home_id,
            'mlb_game_pk': game_pk,
            'game_date': game_date,
            'game_type': game.get('gameType'),
            'opponent_team_id': away_id,
            'home_away': 'home',
            'scheduled_row': None,
            'calendar_available': False,
            'calendar_missing_reason': 'schedule_missing',
        })
    if away_id is not None:
        contexts.append({
            'team_id': away_id,
            'mlb_game_pk': game_pk,
            'game_date': game_date,
            'game_type': game.get('gameType'),
            'opponent_team_id': home_id,
            'home_away': 'away',
            'scheduled_row': None,
            'calendar_available': False,
            'calendar_missing_reason': 'schedule_missing',
        })
    return [context for context in contexts if context['game_date'] is not None]


def _split_values(context, team_log_rows, *, schedule_ambiguous, extra_inning_indicator):
    row = context.get('scheduled_row')
    game_date = context['game_date']
    team_id = context['team_id']
    logs = [entry['log'] for entry in team_log_rows]
    pitchers = {entry['log'].pitcher_id: entry['pitcher'] for entry in team_log_rows}
    split_reasons = []

    if schedule_ambiguous:
        split_reasons.append('suspended_resumed_ambiguous')
        split_status = TeamGamePitchingSplit.STATUS_UNKNOWN
        starter_status = TeamGamePitchingSplit.STARTER_UNKNOWN
        starter = None
        relievers = []
    elif not logs:
        split_reasons.append('no_team_game_logs')
        split_status = TeamGamePitchingSplit.STATUS_UNKNOWN
        starter_status = TeamGamePitchingSplit.STARTER_UNKNOWN
        starter = None
        relievers = []
    else:
        starter_candidates = [log for log in logs if log.games_started == 1]
        unknown_start_flags = [log for log in logs if log.games_started is None]
        if len(starter_candidates) == 1:
            starter_status = TeamGamePitchingSplit.STARTER_KNOWN
            starter = starter_candidates[0]
            relievers = [log for log in logs if log.id != starter.id]
        elif len(starter_candidates) > 1:
            starter_status = TeamGamePitchingSplit.STARTER_AMBIGUOUS
            starter = None
            relievers = []
            split_reasons.append('starter_identity_ambiguous')
        else:
            starter_status = TeamGamePitchingSplit.STARTER_UNKNOWN
            starter = None
            relievers = []
            reason = 'starter_games_started_unknown' if unknown_start_flags else 'starter_identity_unknown'
            split_reasons.append(reason)

        split_status = TeamGamePitchingSplit.STATUS_PARTIAL

    total_team_outs = _nullable_sum(logs, 'innings_pitched_outs')
    total_team_pitches = _nullable_sum(logs, 'pitches_thrown')
    total_team_batters_faced = _nullable_sum(logs, 'batters_faced')
    total_team_balls = _nullable_sum(logs, 'balls')

    starter_pitcher = pitchers.get(starter.pitcher_id) if starter is not None else None
    values = {
        'team_id': team_id,
        'mlb_game_pk': context['mlb_game_pk'],
        'game_date': game_date,
        'game_type': context.get('game_type'),
        'opponent_team_id': context.get('opponent_team_id'),
        'home_away': context.get('home_away'),
        'starter_pitcher_id': starter.pitcher_id if starter is not None else None,
        'starter_mlb_id': starter_pitcher.mlb_id if starter_pitcher is not None else None,
        'starter_identity_status': starter_status,
        'starter_outs_recorded': getattr(starter, 'innings_pitched_outs', None),
        'starter_pitches_thrown': getattr(starter, 'pitches_thrown', None),
        'starter_batters_faced': getattr(starter, 'batters_faced', None),
        'starter_balls': getattr(starter, 'balls', None),
        'starter_games_started': getattr(starter, 'games_started', None),
        'bullpen_outs_recorded': _nullable_sum(relievers, 'innings_pitched_outs') if starter else None,
        'bullpen_pitches_thrown': _nullable_sum(relievers, 'pitches_thrown') if starter else None,
        'bullpen_batters_faced': _nullable_sum(relievers, 'batters_faced') if starter else None,
        'bullpen_balls': _nullable_sum(relievers, 'balls') if starter else None,
        'relievers_used_count': len(relievers) if starter else None,
        'total_team_outs': total_team_outs,
        'total_team_pitches': total_team_pitches,
        'total_team_batters_faced': total_team_batters_faced,
        'total_team_balls': total_team_balls,
        'source': SOURCE,
    }

    if logs:
        _append_unknown_reasons(values, split_reasons)
    if not split_reasons:
        split_status = TeamGamePitchingSplit.STATUS_COMPLETE
    values['split_completeness_status'] = split_status
    values['split_reason_codes'] = _dedupe(split_reasons)

    calendar_values = _calendar_values(
        context,
        schedule_ambiguous=schedule_ambiguous,
        extra_inning_indicator=extra_inning_indicator,
    )
    values.update(calendar_values)
    return values


def _append_unknown_reasons(values, reasons):
    checks = (
        ('starter_outs_recorded', 'starter_outs_unknown'),
        ('starter_pitches_thrown', 'starter_pitches_unknown'),
        ('starter_batters_faced', 'starter_batters_faced_unknown'),
        ('starter_balls', 'starter_balls_unknown'),
        ('bullpen_outs_recorded', 'bullpen_outs_unknown'),
        ('bullpen_pitches_thrown', 'bullpen_pitches_unknown'),
        ('bullpen_batters_faced', 'bullpen_batters_faced_unknown'),
        ('bullpen_balls', 'bullpen_balls_unknown'),
        ('total_team_outs', 'total_team_outs_unknown'),
        ('total_team_pitches', 'total_team_pitches_unknown'),
        ('total_team_batters_faced', 'total_team_batters_faced_unknown'),
        ('total_team_balls', 'total_team_balls_unknown'),
    )
    for field, reason in checks:
        if values.get(field) is None:
            reasons.append(reason)


def _calendar_values(context, *, schedule_ambiguous, extra_inning_indicator):
    row = context.get('scheduled_row')
    reasons = []
    if schedule_ambiguous:
        reasons.append('suspended_resumed_ambiguous')
    if not context.get('calendar_available'):
        reasons.append(context.get('calendar_missing_reason') or 'schedule_missing')

    if row is None:
        return {
            'off_day_before': None,
            'off_day_after': None,
            'consecutive_game_day_count_entering': None,
            'series_game_number': None,
            'games_in_series': None,
            'doubleheader_flag': None,
            'doubleheader_code': None,
            'game_number': None,
            'postponed_or_makeup_indicator': None,
            'suspended_resumed_linkage_status': TeamGamePitchingSplit.LINKAGE_NONE,
            'extra_inning_indicator': extra_inning_indicator,
            'calendar_context_status': TeamGamePitchingSplit.STATUS_UNKNOWN,
            'calendar_reason_codes': _dedupe(reasons),
        }

    game_dates = _playable_game_dates(row.team_id)
    same_day_count = _same_day_game_count(row.team_id, row.game_date)
    linkage_status = _linkage_status([row], schedule_ambiguous=schedule_ambiguous)
    if schedule_ambiguous:
        status = TeamGamePitchingSplit.STATUS_UNKNOWN
    else:
        status = TeamGamePitchingSplit.STATUS_COMPLETE
    return {
        'off_day_before': (row.game_date - timedelta(days=1)) not in game_dates,
        'off_day_after': (row.game_date + timedelta(days=1)) not in game_dates,
        'consecutive_game_day_count_entering': _consecutive_game_days_entering(
            row.team_id,
            row.game_date,
        ),
        'series_game_number': row.series_game_number,
        'games_in_series': row.games_in_series,
        'doubleheader_flag': _doubleheader_flag(row, same_day_count),
        'doubleheader_code': row.doubleheader,
        'game_number': row.game_number,
        'postponed_or_makeup_indicator': _postponed_or_makeup_indicator(row),
        'suspended_resumed_linkage_status': linkage_status,
        'extra_inning_indicator': extra_inning_indicator,
        'calendar_context_status': status,
        'calendar_reason_codes': _dedupe(reasons),
    }


def _upsert_split(values, *, sync_run_id):
    existing = TeamGamePitchingSplit.query.filter_by(
        team_id=values['team_id'],
        mlb_game_pk=values['mlb_game_pk'],
    ).first()
    now = utc_now_naive()
    if existing is None:
        row = TeamGamePitchingSplit(**values)
        row.sync_run_id = sync_run_id
        row.first_seen_at = now
        row.last_derived_at = now
        row.created_at = now
        row.updated_at = now
        db.session.add(row)
        return 'inserted'

    changed = any(_normalized_value(getattr(existing, field)) != _normalized_value(values.get(field))
                  for field in _SPLIT_VALUE_FIELDS)
    for field in _SPLIT_VALUE_FIELDS:
        setattr(existing, field, values.get(field))
    existing.sync_run_id = sync_run_id
    existing.last_derived_at = now
    existing.updated_at = now
    if changed:
        existing.correction_count = (existing.correction_count or 0) + 1
        existing.last_corrected_at = now
        existing.correction_source = CORRECTION_SOURCE
    db.session.add(existing)
    return 'corrected' if changed else 'unchanged'


def _scheduled_rows_for_game(game_pk):
    return (
        ScheduledGame.query
        .filter_by(game_pk=game_pk)
        .order_by(ScheduledGame.team_id.asc(), ScheduledGame.id.asc())
        .all()
    )


def _game_log_rows(game_pk):
    return [
        {'log': log, 'pitcher': pitcher}
        for log, pitcher in (
            db.session.query(GameLog, Pitcher)
            .join(Pitcher, GameLog.pitcher_id == Pitcher.id)
            .filter(GameLog.mlb_game_pk == game_pk)
            .all()
        )
    ]


def _logs_by_team(log_rows):
    grouped = {}
    for entry in log_rows:
        team_id = entry['pitcher'].team_id
        if team_id is None:
            continue
        grouped.setdefault(team_id, []).append(entry)
    return grouped


def _nullable_sum(records, field_name):
    records = list(records or [])
    if not records:
        return None
    values = [getattr(record, field_name, None) for record in records]
    if any(value is None for value in values):
        return None
    return sum(values)


def _extra_inning_indicator(contexts, team_total_outs):
    if not contexts:
        return None
    values = [team_total_outs.get(context['team_id']) for context in contexts]
    if any(value is None for value in values):
        return None
    return max(values or [0]) > 27


def _playable_game_dates(team_id):
    rows = (
        ScheduledGame.query
        .filter_by(team_id=team_id)
        .filter(ScheduledGame.status_state.in_(
            (ScheduledGame.STATE_FINAL, ScheduledGame.STATE_SCHEDULED)
        ))
        .all()
    )
    return {row.game_date for row in rows}


def _same_day_game_count(team_id, game_date):
    return int(
        ScheduledGame.query
        .filter_by(team_id=team_id, game_date=game_date)
        .filter(ScheduledGame.status_state.in_(
            (ScheduledGame.STATE_FINAL, ScheduledGame.STATE_SCHEDULED)
        ))
        .count()
        or 0
    )


def _consecutive_game_days_entering(team_id, game_date):
    dates = _playable_game_dates(team_id)
    count = 0
    cursor = game_date - timedelta(days=1)
    while cursor in dates:
        count += 1
        cursor -= timedelta(days=1)
    return count


def _doubleheader_flag(row, same_day_count):
    code = str(row.doubleheader or '').strip().upper()
    return (code not in ('', 'N')) or same_day_count > 1


def _postponed_or_makeup_indicator(row):
    original_dates = [
        row.original_game_date,
        row.original_product_date,
        row.resumed_game_date,
        row.resumed_product_date,
    ]
    if row.resumed_from_game_pk is not None or row.resumed_to_game_pk is not None:
        return True
    return any(value is not None and value != row.game_date for value in original_dates)


def _linkage_status(rows, *, schedule_ambiguous):
    if schedule_ambiguous:
        return TeamGamePitchingSplit.LINKAGE_AMBIGUOUS
    for row in rows:
        if any((
            row.original_game_date,
            row.original_product_date,
            row.resumed_game_date,
            row.resumed_product_date,
            row.resumed_from_game_pk,
            row.resumed_to_game_pk,
        )):
            return TeamGamePitchingSplit.LINKAGE_RESOLVED
    return TeamGamePitchingSplit.LINKAGE_NONE


def _game_team_id(game, side):
    return _positive_int(((((game or {}).get('teams') or {}).get(side) or {}).get('team') or {}).get('id'))


def _game_date(game, fallback):
    if isinstance(fallback, date):
        return fallback
    raw = (game or {}).get('officialDate') or str((game or {}).get('gameDate') or '')[:10]
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _positive_int(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalized_value(value):
    if isinstance(value, date):
        return value.isoformat()
    return value


def _dedupe(values):
    seen = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _result(game_pk, *, status, reason):
    return {
        'game_pk': game_pk,
        'status': status,
        'reason': reason,
        'rows_inserted': 0,
        'rows_corrected': 0,
        'rows_unchanged': 0,
        'rows_total': 0,
        'split_statuses': [],
        'calendar_statuses': [],
        'reason_codes': [reason] if reason else [],
    }
