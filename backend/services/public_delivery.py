"""HTTP delivery metadata for publication-backed public read models.

This module does not select publications or calculate baseball meaning.  It
only turns an already-selected resource identity into a stable validator and
applies the cache policy appropriate to either a current alias or an immutable
snapshot-keyed resource.
"""

from __future__ import annotations

from hashlib import sha256

from flask import request


DELIVERY_CONTRACT = 'public_delivery_v1'
CURRENT_ALIAS_CACHE_CONTROL = 'public, max-age=0, must-revalidate'
IMMUTABLE_CACHE_CONTROL = 'public, max-age=31536000, immutable'
NO_STORE_CACHE_CONTROL = 'no-store'


def _identity_value(identity, key):
    if not isinstance(identity, dict):
        return None
    return identity.get(key)


def publication_validator(resource, identity, *, contract_version=None):
    """Return a cheap stable validator from explicit publication identity."""
    snapshot_id = _identity_value(identity, 'snapshot_id')
    if snapshot_id is None:
        return None
    parts = (
        DELIVERY_CONTRACT,
        str(resource or ''),
        str(snapshot_id),
        str(_identity_value(identity, 'sync_run_id') or ''),
        str(_identity_value(identity, 'represented_date') or ''),
        str(contract_version or _identity_value(identity, 'payload_version') or ''),
        str(_identity_value(identity, 'source_revision') or ''),
    )
    return sha256('|'.join(parts).encode('utf-8')).hexdigest()


def apply_public_delivery_headers(
    response,
    *,
    resource,
    identity,
    contract_version=None,
    immutable=False,
    available=True,
):
    """Apply cache headers and a conditional 304 to one JSON response."""
    validator = publication_validator(
        resource,
        identity,
        contract_version=contract_version,
    ) if available else None
    if validator is None:
        response.headers['Cache-Control'] = NO_STORE_CACHE_CONTROL
        return response

    response.set_etag(validator)
    response.headers['Cache-Control'] = (
        IMMUTABLE_CACHE_CONTROL if immutable else CURRENT_ALIAS_CACHE_CONTROL
    )
    response.headers['X-BaseballOS-Snapshot-ID'] = str(identity['snapshot_id'])
    if request.if_none_match.contains(validator):
        response.status_code = 304
        response.set_data(b'')
    return response


__all__ = [
    'CURRENT_ALIAS_CACHE_CONTROL',
    'DELIVERY_CONTRACT',
    'IMMUTABLE_CACHE_CONTROL',
    'NO_STORE_CACHE_CONTROL',
    'apply_public_delivery_headers',
    'publication_validator',
]
