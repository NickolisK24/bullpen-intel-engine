"""Descriptive monthly pitch measurements for a single pitcher's logged relief outings."""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from itertools import groupby
from math import isfinite

from sqlalchemy import and_, or_

from models.game_log import GameLog
from models.play_by_play_foundation import GamePitchEvent as Pitch, PlayByPlayProcessedGame as Game
from services.play_by_play_foundation import SOURCE
from utils.db import db


def _tenth(value, denominator):
    return float((value / denominator).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def pitch_type_summary(code, pitches, total, measured, speed_sum):
    mean = _tenth(speed_sum, pitches) if measured == pitches else None
    return {'type': code, 'pitches': pitches, 'mean_mph': mean,
            'mix_percent': _tenth(Decimal(100 * pitches), total)}


def summarized_pitch_types(speeds_by_type):
    total = sum(map(len, speeds_by_type.values()))
    values = []
    for code, speeds in sorted(speeds_by_type.items()):
        known = [v for v in speeds if v is not None and isfinite(v) and v > 0]
        speed_sum = sum((Decimal(str(v)) for v in known), Decimal(0))
        values.append(pitch_type_summary(code, len(speeds), total, len(known), speed_sum))
    return values


def season_pitch_characteristics(pitcher, through, *, appearance_team_id=None):
    """Count each retained current pitch once. Withhold incomplete calendar months."""
    if through is None:
        return None
    rows = (
        db.session.query(
            GameLog.game_date, GameLog.mlb_game_pk, GameLog.pitches_thrown,
            GameLog.appearance_team_status, GameLog.games_started, Pitch.pitch_type_code, Pitch.start_speed,
        ).select_from(GameLog)
        .outerjoin(Game, and_(
            Game.mlb_game_pk == GameLog.mlb_game_pk, Game.game_date == GameLog.game_date,
            Game.game_type == 'R', Game.source == SOURCE,
            Game.processing_status == Game.STATUS_FULLY_PROCESSED,
            Game.pitch_fingerprint.isnot(None), Game.current_pitch_count > 0,
            Game.current_pitch_count == Game.pitches_seen, Game.current_pitch_count == Game.pitches_stored,
        ))
        .outerjoin(Pitch, and_(
            Pitch.mlb_game_pk == Game.mlb_game_pk, Pitch.game_date == Game.game_date,
            Pitch.fielding_team_id == GameLog.appearance_team_id, Pitch.game_type == 'R',
            Pitch.pitcher_id == pitcher.id, Pitch.pitcher_mlb_id == pitcher.mlb_id,
            Pitch.source == SOURCE, Pitch.is_current.is_(True),
            Pitch.source_revision == Pitch.event_fingerprint,
        ))
        .filter(GameLog.pitcher_id == pitcher.id, or_(GameLog.games_started == 0, GameLog.games_started.is_(None)),
                GameLog.game_type == 'R', GameLog.game_date.between(through.replace(month=1, day=1), through))
        .order_by(GameLog.game_date, GameLog.mlb_game_pk)
    )
    if appearance_team_id is not None:
        rows = rows.filter(GameLog.appearance_team_status == GameLog.APPEARANCE_TEAM_RESOLVED,
                           GameLog.appearance_team_id == appearance_team_id)
    months = {}
    for (day, _game_pk), outing in groupby(rows, key=lambda r: (r.game_date, r.mlb_game_pk)):
        pitches = list(outing)
        first = pitches[0]
        month = months.setdefault(day.strftime('%Y-%m'), {
            'outings': 0, 'verified_outings': 0, 'types': defaultdict(list),
        })
        month['outings'] += 1
        if (first.games_started != 0 or first.appearance_team_status != GameLog.APPEARANCE_TEAM_RESOLVED
                or first.pitches_thrown != len(pitches) or not all(p.pitch_type_code for p in pitches)):
            continue
        month['verified_outings'] += 1
        for pitch in pitches:
            month['types'][pitch.pitch_type_code].append(pitch.start_speed)
    result = []
    for month, sample in months.items():
        types = sample.pop('types')
        values = summarized_pitch_types(types) if sample['verified_outings'] == sample['outings'] else []
        result.append({'month': month, **sample, 'types': values})
    return monthly_pitch_characteristics(through, result)


def monthly_pitch_characteristics(through, months):
    """Public chart fields from already qualified monthly relief samples."""
    rows = []
    for month in months:
        types = []
        if month['outings'] == month['verified_outings']:
            types = [{k: row[k] for k in ('type', 'pitches', 'mean_mph', 'mix_percent')} for row in month['types']]
        rows.append(dict(month=month['month'], outings=month['outings'],
                         verified_outings=month['verified_outings'], types=types))
    return {'method_version': 'monthly_recorded_relief_pitches_v1', 'source': SOURCE,
            'through': through.isoformat(), 'months': rows}


def published_pitcher_deployment(snapshot, pitcher):
    """Read only this club's frozen deployment fields from the selected publication."""
    from models.dashboard_snapshot import DashboardSnapshot
    from services import public_serving_authority as authority
    from services import role_movement
    from services.team_board_what_changed import _movement_read

    if getattr(snapshot, 'id', None) is None or pitcher.team_id is None:
        return None
    path = (authority.TEAM_BOARD_PACKAGE_KEY, 'by_team_id', str(pitcher.team_id))
    body = DashboardSnapshot.payload
    row = db.session.query(
        body[path + ('roles_deployment',)], body[path + ('roles_deployment_authority',)],
        body[(authority.TEAM_BOARD_PACKAGE_KEY, 'contract')],
        body[(authority.TEAM_BOARD_PACKAGE_KEY, 'data_through')],
    ).filter(DashboardSnapshot.id == snapshot.id, DashboardSnapshot.status == 'ready',
             DashboardSnapshot.is_published.is_(True),
             DashboardSnapshot.published_at.isnot(None)).one_or_none()
    if (not row or row[2] != authority.TEAM_BOARD_PACKAGE_CONTRACT
            or row[3] != snapshot.data_through.isoformat()):
        return None
    carrier = authority._frozen_roles_deployment_for_view(snapshot, {
        'roles_deployment': row[0], 'roles_deployment_authority': row[1],
    }, pitcher.team_id)
    if carrier is None:
        return None
    profiles = [p for p in carrier['profiles'] if p['pitcher_id'] == pitcher.id]
    if len(profiles) != 1:
        return None
    movement = carrier.get('role_movement') or {}
    shifts = []
    if (movement.get('method_version') == role_movement.METHOD_VERSION
            and movement.get('contract') == role_movement.CONTRACT
            and movement.get('game_types') == sorted(role_movement.GAME_TYPES)
            and movement.get('population_basis') == 'official_appearance_team_relief_appearances'
            and movement.get('data_through') == carrier['data_through']
            and movement.get('status') in ('complete', 'partial')):
        shifts = [p for p in movement.get('profiles') or []
                  if p.get('pitcher_id') == pitcher.id and _movement_read(p, snapshot.data_through)]
    return {'snapshot_id': snapshot.id, 'through': carrier['data_through'],
            'window_days': carrier['window_days'], 'context': profiles[0]['context'],
            'movement': shifts[0] if len(shifts) == 1 else None}
