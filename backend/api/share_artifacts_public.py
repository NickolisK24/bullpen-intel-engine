"""Public, unauthenticated, read-only Share Artifact API (Share Cards SC-04).

A purpose-built PUBLIC boundary — it is not an admin/internal endpoint with auth
removed. It exposes exactly one GET route that delegates to the canonical public
read service and returns a lifecycle-aware, integrity-verified, whitelisted view.
No authentication, no generation, no mutation, no current-state lookup, no admin
metadata, no raw payload dump, no audit exposure.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, make_response, request

from services.share_artifact_public import (
    RESULT_INTEGRITY_ERROR,
    RESULT_NOT_FOUND,
    RESULT_OK,
    RESULT_SUPERSEDED,
    RESULT_WITHDRAWN,
    load_public_share_artifact,
)


share_artifacts_public_bp = Blueprint('share_artifacts_public', __name__)

# Published immutable artifacts never change in place → safe long-lived caching.
_PUBLISHED_CACHE = 'public, max-age=3600, s-maxage=86400, immutable'
# Superseded content is frozen too, but its replacement pointer may appear → revalidate.
_SUPERSEDED_CACHE = 'public, max-age=300, must-revalidate'
# Never let a withdrawn/gone or a transient failure be cached as a successful artifact.
_NO_STORE = 'no-store'
_SHORT_CACHE = 'public, max-age=60'


def _respond(body, status_code, cache_control, *, etag=None):
    response = make_response(jsonify(body), status_code)
    response.headers['Cache-Control'] = cache_control
    if etag:
        response.headers['ETag'] = etag
    return response


@share_artifacts_public_bp.route('/<public_id>', methods=['GET'])
def get_public_share_artifact(public_id):
    """GET /api/share-artifacts/<public_id> — the permanent public artifact read."""
    result = load_public_share_artifact(public_id)

    if result.status == RESULT_OK:
        return _respond(
            {'status': RESULT_OK, 'artifact': result.view},
            200, _PUBLISHED_CACHE, etag=(result.view or {}).get('public_id'),
        )
    if result.status == RESULT_SUPERSEDED:
        return _respond(
            {'status': RESULT_SUPERSEDED, 'artifact': result.view},
            200, _SUPERSEDED_CACHE,
        )
    if result.status == RESULT_WITHDRAWN:
        return _respond({'status': RESULT_WITHDRAWN, 'artifact': result.view}, 410, _NO_STORE)
    if result.status == RESULT_INTEGRITY_ERROR:
        # Fail closed: no meaning-bearing content, no raw mismatch detail, not cached.
        return _respond({'status': RESULT_INTEGRITY_ERROR, 'error': 'integrity_unverified'}, 503, _NO_STORE)
    # not_found (draft / unknown / malformed) — a draft is never publicly discoverable.
    return _respond({'status': RESULT_NOT_FOUND, 'error': 'not_found'}, 404, _SHORT_CACHE)
