"""Serve the stored tonight_v1 projection of the current trusted publication.

Serving never builds. The request path is:

    1. resolve the current trusted Dashboard snapshot (metadata + freshness
       only, the same selector the Home / League / Trust projections use);
    2. take its ``availability_reference_date`` as the Tonight baseball date;
    3. read the one ``tonight_publications`` row bound to exactly
       (reference_date, dashboard_snapshot_id, contract='tonight_v1');
    4. check the row's stored identity against its payload and the snapshot;
    5. return the stored payload unchanged.

A row bound to any other snapshot, including an older one for the same date,
is never served as current. A missing or inconsistent row fails closed; the
caller that asked for tonight_v1 never receives legacy tonight_v5 instead.
Nothing here reads GameLog, FatigueScore, slate_games, or the Team Board
package, and nothing writes.
"""

from __future__ import annotations

from datetime import date, datetime
import logging
import re

from models.tonight_publication import TonightPublication
from services import dashboard_snapshot as dashboard_snapshot_service
from services.tonight_read_model import CONTRACT


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

    ``delivery`` is ``None`` when unavailable; otherwise it holds the header
    identity and the stored ``content_sha256`` validator. Database errors
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

    return row.payload, {
        'validator': row.content_sha256,
        'snapshot_id': row.dashboard_snapshot_id,
        'sync_run_id': row.sync_run_id,
        'data_through': _iso(row.data_through),
        'contract': row.contract,
    }


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


__all__ = [
    'CONTRACT_PARAM',
    'LEGACY_CONTRACT',
    'REASON_IDENTITY_MISMATCH',
    'REASON_NO_TRUSTED_PUBLICATION',
    'REASON_ROW_MISSING',
    'REASON_UNAVAILABLE',
    'STATUS_UNAVAILABLE',
    'SUPPORTED_CONTRACTS',
    'identity_mismatch',
    'serve_current_tonight_v1',
    'unavailable_payload',
    'unsupported_v1_param',
]
