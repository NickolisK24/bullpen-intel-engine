"""Serve the stored tonight_v1 projection of the current trusted publication.

Serving never builds. The request path is:

    1. resolve the current trusted Dashboard snapshot (metadata + freshness
       only, the same selector the Home / League / Trust projections use);
    2. take its ``availability_reference_date`` as the Tonight baseball date;
    3. read the one ``tonight_publications`` row bound to exactly
       (reference_date, dashboard_snapshot_id, contract='tonight_v1');
    4. check the row's stored identity against its payload and the snapshot;
    5. overlay current game state from ``slate_games`` onto a copy of the
       stored payload (TN-03, see ``overlay_game_state``) and return it.

A row bound to any other snapshot, including an older one for the same date,
is never served as current. A missing or inconsistent row fails closed; the
caller that asked for tonight_v1 never receives legacy tonight_v5 instead.

Bullpen intelligence stays frozen to the stored row. Only schedule facts of
the stored games (state, first pitch, state_as_of) may change at serve time,
read in one bounded ``slate_games`` query; the stored context sentence is only
re-presented for that state (TN-04). The stored row is never mutated;
the overlay works on a copy. Nothing here reads GameLog, FatigueScore,
pitchers, or the Team Board package, and nothing writes.
"""

from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import json
import logging
import re

from models.slate_game import SlateGame
from models.tonight_publication import TonightPublication
from services import dashboard_snapshot as dashboard_snapshot_service
from services.tonight_read_model import (
    CONTRACT,
    GAME_STATES,
    game_state,
    present_matchup_context,
)


logger = logging.getLogger(__name__)

CONTRACT_PARAM = 'contract'
LEGACY_CONTRACT = 'tonight_v5'
SUPPORTED_CONTRACTS = (LEGACY_CONTRACT, CONTRACT)
# The current alias only. There is no immutable per-snapshot Tonight route yet.
UNSUPPORTED_V1_PARAMS = ('reference_date', 'dashboard_snapshot_id', 'snapshot_id')

STATUS_UNAVAILABLE = 'unavailable'
REASON_UNAVAILABLE = 'trusted_tonight_v1_publication_unavailable'
REASON_NO_TRUSTED_PUBLICATION = 'trusted_dashboard_publication_unavailable'
REASON_ROW_MISSING = 'tonight_v1_publication_missing'
REASON_IDENTITY_MISMATCH = 'tonight_v1_publication_identity_mismatch'

# TN-03 overlay limitations, added to the served ``limitations`` only when they occur.
REASON_OVERLAY_ROW_MISSING = 'schedule_overlay_row_missing'
REASON_OVERLAY_CONFLICT = 'schedule_overlay_conflict'
REASON_OVERLAY_DATE_MOVED = 'schedule_overlay_game_date_moved'

OVERLAY_VALIDATOR_CONTRACT = 'tonight_v1_served_overlay_v1'

# Stored (frozen) state -> current states the overlay may serve for the same
# game_pk. A current state outside the set is a conflict: the frozen state is
# served. Terminal states never regress; live and suspended never go back to
# scheduled or postponed; a postponement is not undone on the same game_pk.
ALLOWED_TRANSITIONS = {
    'scheduled': frozenset(GAME_STATES),
    'uncertain': frozenset(GAME_STATES),
    'live': frozenset({'live', 'final', 'suspended', 'uncertain'}),
    'suspended': frozenset({'suspended', 'live', 'final', 'uncertain'}),
    'postponed': frozenset({'postponed'}),
    'final': frozenset({'final'}),
}

_LIMITATIONS = {
    REASON_NO_TRUSTED_PUBLICATION: (
        'No current trusted Dashboard publication is available, so no Tonight v1 '
        'projection can be served.'
    ),
    REASON_ROW_MISSING: (
        'The current trusted publication does not yet have a Tonight v1 projection.'
    ),
    REASON_IDENTITY_MISMATCH: (
        'The stored Tonight v1 projection does not match the current trusted '
        'publication and is withheld.'
    ),
}

# Only the freshness domain is read: it is what trusted-snapshot validation
# needs. The Team Board package and the rest of the payload stay in the DB.
_SNAPSHOT_PAYLOAD_KEYS = ('freshness',)
_SHA256 = re.compile(r'^[0-9a-f]{64}$')


def unsupported_v1_param(args):
    """The first request parameter tonight_v1 current serving does not accept."""
    for name in UNSUPPORTED_V1_PARAMS:
        if args.get(name) not in (None, ''):
            return name
    return None


def serve_current_tonight_v1():
    """Return ``(body, delivery)`` for the current trusted tonight_v1 row.

    ``body`` is the stored payload with the current game-state overlay.
    ``delivery`` is ``None`` when unavailable; otherwise it holds the header
    identity of the frozen publication and the served-representation
    validator (see ``served_validator``). Database errors
    propagate to the caller's normal service-error handling.
    """
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot_projection(
        _SNAPSHOT_PAYLOAD_KEYS,
    )
    if snapshot is None:
        return unavailable_payload(REASON_NO_TRUSTED_PUBLICATION), None

    reference_date = snapshot.availability_reference_date
    row = TonightPublication.query.filter_by(
        contract=CONTRACT,
        dashboard_snapshot_id=snapshot.id,
        reference_date=reference_date,
    ).one_or_none()
    if row is None:
        return unavailable_payload(REASON_ROW_MISSING, snapshot=snapshot), None

    mismatch = identity_mismatch(row, snapshot)
    if mismatch is not None:
        logger.error(
            'tonight_v1 authority integrity failure: row withheld '
            'tonight_publication_id=%s dashboard_snapshot_id=%s field=%s',
            row.id, snapshot.id, mismatch,
        )
        return unavailable_payload(REASON_IDENTITY_MISMATCH, snapshot=snapshot), None

    served, overlay_identity = overlay_game_state(
        row.payload, _current_schedule_rows(row.payload),
    )
    return served, {
        'validator': served_validator(row.content_sha256, overlay_identity),
        'snapshot_id': row.dashboard_snapshot_id,
        'sync_run_id': row.sync_run_id,
        'data_through': _iso(row.data_through),
        'contract': row.contract,
    }


def _stored_game_pks(payload):
    return sorted({
        game.get('game_pk') for game in payload.get('games') or ()
        if isinstance(game, dict) and type(game.get('game_pk')) is int
    })


def _current_schedule_rows(payload):
    """One bounded read of the current slate_games facts for the stored games."""
    game_pks = _stored_game_pks(payload)
    if not game_pks:
        return {}
    rows = (
        SlateGame.query
        .with_entities(
            SlateGame.game_pk,
            SlateGame.game_date_et,
            SlateGame.game_time_utc,
            SlateGame.normalized_state,
            SlateGame.status_detailed,
            SlateGame.last_synced,
        )
        .filter(SlateGame.game_pk.in_(game_pks))
        .all()
    )
    return {row.game_pk: row for row in rows}


def overlay_game_state(payload, current_rows):
    """Return ``(served_payload, overlay_identity)`` without mutating ``payload``.

    For each stored game, the current ``slate_games`` row overlays only
    ``state``, ``first_pitch_utc`` and ``state_as_of``, and only when all of
    these hold:

    * the row exists and is still dated on the edition's baseball date;
    * its ``last_synced`` is strictly newer than the stored ``state_as_of``;
    * it changes the served state or first pitch;
    * the stored -> current state transition is in ``ALLOWED_TRANSITIONS``.

    Game membership and order, both TeamSides, links, lead, featured and every
    bullpen summary field stay exactly as stored. The stored context sentence
    is only re-presented for the served state (``present_matchup_context``):
    marked pregame when live, hidden when final, postponed or suspended.
    ``summary.games_by_state`` is recounted from the served games. The overlay
    identity lists every served difference; it is empty when the served body
    equals the stored one.
    """
    games = payload.get('games') if isinstance(payload, dict) else None
    if not isinstance(games, list) or not games:
        return payload, ()
    edition = payload.get('edition') if isinstance(payload.get('edition'), dict) else {}
    baseball_date = edition.get('baseball_date')

    served_games = []
    identity = []
    reasons = []
    for game in games:
        outcome, fields = _overlay_one(game, current_rows.get(game.get('game_pk')), baseball_date)
        if outcome == 'missing':
            reasons.append(REASON_OVERLAY_ROW_MISSING)
        elif outcome == 'moved':
            reasons.append(REASON_OVERLAY_DATE_MOVED)
        elif outcome == 'conflict':
            reasons.append(REASON_OVERLAY_CONFLICT)
        if outcome in ('missing', 'moved', 'conflict'):
            identity.append((game.get('game_pk'), outcome))
        if fields:
            game = {**game, **fields}
            context = game.get('context') or {}
            identity.append((
                game.get('game_pk'), 'overlaid',
                game['state'], game['first_pitch_utc'], game['state_as_of'],
                'context:' + ','.join(context.get('reason_codes') or ())
                + ('' if context.get('sentence') is not None else ':hidden'),
            ))
        served_games.append(game)

    if not identity:
        return payload, ()

    served = dict(payload)
    served['games'] = served_games
    summary = payload.get('summary')
    if isinstance(summary, dict) and isinstance(summary.get('games_by_state'), dict):
        by_state = {state: 0 for state in summary['games_by_state']}
        for game in served_games:
            by_state[game['state']] = by_state.get(game['state'], 0) + 1
        served['summary'] = {**summary, 'games_by_state': by_state}
    if reasons:
        limitations = list(payload.get('limitations') or [])
        served['limitations'] = list(dict.fromkeys(limitations + reasons))
    return served, tuple(sorted(identity, key=lambda item: (item[0] or 0, item[1:])))


def _overlay_one(game, row, baseball_date):
    """Classify one stored game against its current row; return (outcome, fields)."""
    if row is None:
        return 'missing', None
    if _iso(row.game_date_et) != baseball_date:
        return 'moved', None
    stored_as_of = _parse_utc(game.get('state_as_of'))
    if row.last_synced is None or (
        stored_as_of is not None and row.last_synced <= stored_as_of
    ):
        return 'stale', None
    current_state = game_state(row)
    first_pitch = _utc_iso(row.game_time_utc) or game.get('first_pitch_utc')
    if current_state == game.get('state') and first_pitch == game.get('first_pitch_utc'):
        return 'unchanged', None
    if current_state not in ALLOWED_TRANSITIONS.get(game.get('state'), frozenset()):
        return 'conflict', None
    fields = {
        'state': current_state,
        'first_pitch_utc': first_pitch,
        'state_as_of': _utc_iso(row.last_synced),
    }
    # TN-04: the stored pregame sentence is marked once live and hidden once
    # the game is over or off. The stored context itself is never changed.
    context = present_matchup_context(game.get('context'), current_state)
    if context != game.get('context'):
        fields['context'] = context
    return 'overlaid', fields


def served_validator(content_sha256, overlay_identity):
    """ETag of the served representation.

    With no overlay difference the served body is the stored body, so the
    stored ``content_sha256`` is the validator (unchanged from TN-02).
    Otherwise the validator hashes the stored digest together with the sorted
    overlay identity. The same logical overlay always yields the same value.
    """
    if not overlay_identity:
        return content_sha256
    body = json.dumps(
        [OVERLAY_VALIDATOR_CONTRACT, content_sha256, [list(item) for item in overlay_identity]],
        separators=(',', ':'),
    )
    return sha256(body.encode('utf-8')).hexdigest()


def identity_mismatch(row, snapshot):
    """Name the first identity field on which row, payload and snapshot disagree."""
    payload = row.payload if isinstance(row.payload, dict) else None
    if payload is None:
        return 'payload'
    edition = payload.get('edition') if isinstance(payload.get('edition'), dict) else {}
    publication = (
        edition.get('publication') if isinstance(edition.get('publication'), dict) else {}
    )
    reference_date = _iso(row.reference_date)
    checks = (
        ('contract', row.contract == CONTRACT and payload.get('contract') == CONTRACT),
        ('dashboard_snapshot_id', (
            row.dashboard_snapshot_id == snapshot.id
            and publication.get('dashboard_snapshot_id') == row.dashboard_snapshot_id
        )),
        ('sync_run_id', (
            row.sync_run_id == snapshot.sync_run_id
            and publication.get('sync_run_id') == row.sync_run_id
        )),
        ('data_through', (
            row.data_through == snapshot.data_through
            and edition.get('data_through') == _iso(row.data_through)
        )),
        ('reference_date', (
            row.reference_date == snapshot.availability_reference_date
            and row.availability_reference_date == row.reference_date
            and edition.get('baseball_date') == reference_date
            and edition.get('availability_reference_date') == reference_date
        )),
        ('content_sha256', bool(_SHA256.match(row.content_sha256 or ''))),
    )
    for field, ok in checks:
        if not ok:
            return field
    return None


def unavailable_payload(reason_code, *, snapshot=None):
    """Fail-closed tonight_v1 body: the v1 shape with no games and no edition."""
    return {
        'contract': CONTRACT,
        'status': STATUS_UNAVAILABLE,
        'reason': REASON_UNAVAILABLE,
        'empty_reason': REASON_UNAVAILABLE,
        'reason_codes': [reason_code],
        'edition': None,
        'current_publication': _publication_identity(snapshot),
        'summary': {'game_count': 0},
        'lead': None,
        'featured_game_pks': [],
        'games': [],
        'game_count': 0,
        'league_changes': [],
        'quiet_day': False,
        'limitations': [_LIMITATIONS[reason_code]],
    }


def _publication_identity(snapshot):
    if snapshot is None:
        return None
    return {
        'dashboard_snapshot_id': snapshot.id,
        'sync_run_id': snapshot.sync_run_id,
        'data_through': _iso(snapshot.data_through),
        'availability_reference_date': _iso(snapshot.availability_reference_date),
    }


def _iso(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _utc_iso(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat() + 'Z'
    return value


def _parse_utc(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip('Z'))
    except ValueError:
        return None


__all__ = [
    'CONTRACT_PARAM',
    'LEGACY_CONTRACT',
    'ALLOWED_TRANSITIONS',
    'REASON_IDENTITY_MISMATCH',
    'REASON_OVERLAY_CONFLICT',
    'REASON_OVERLAY_DATE_MOVED',
    'REASON_OVERLAY_ROW_MISSING',
    'REASON_NO_TRUSTED_PUBLICATION',
    'REASON_ROW_MISSING',
    'REASON_UNAVAILABLE',
    'STATUS_UNAVAILABLE',
    'SUPPORTED_CONTRACTS',
    'identity_mismatch',
    'overlay_game_state',
    'serve_current_tonight_v1',
    'served_validator',
    'unavailable_payload',
    'unsupported_v1_param',
]
