"""Browser-safe authenticated Share Artifact operations reads (SC-03B-03B).

The internal operator page runs in the browser, which must NEVER receive or send
the privileged admin secret. These endpoints therefore reuse the repository's
existing, production-proven browser-safe internal gate — a signed-in user's
magic-link Bearer session (`resolve_current_user`) plus a founder/internal email
allowlist — exactly as the existing internal Traffic admin surface does. No
privileged admin secret is required from, or delivered to, the browser.

They are read-only, invoke no generation, mutate nothing, and delegate to the
same shared operations response builders the admin-token API uses, so the two
authorization boundaries share one operational read service, one view-model, one
set of validation/pagination rules, and one status vocabulary. Authenticated
responses are marked no-store so operational data is never publicly cached.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from api.share_artifact_operations_api import (
    build_artifacts_response,
    build_audits_response,
    build_overview_response,
)
from services.traffic_measurement import parse_internal_emails
from utils.auth_tokens import normalize_email
from utils.identity import resolve_current_user


share_artifact_operations_browser_bp = Blueprint(
    'share_artifact_operations_browser', __name__,
)


def _internal_email_allowlist():
    """The founder/internal email allowlist for the operator surface.

    Reuses the existing production-proven internal allowlist (``TRAFFIC_INTERNAL_EMAILS``)
    by default; a dedicated ``SHARE_ARTIFACT_OPERATIONS_EMAILS`` may override it
    without introducing a new authentication mechanism.
    """
    configured = (
        current_app.config.get('SHARE_ARTIFACT_OPERATIONS_EMAILS')
        or current_app.config.get('TRAFFIC_INTERNAL_EMAILS', '')
    )
    return parse_internal_emails(configured)


def _authorize_internal_operator():
    """Fail-closed browser auth: (user, None) on success, (None, response) on denial.

    Distinguishes authentication (no valid session -> 401) from authorization
    (valid session, not on the internal allowlist -> 403). Enforced entirely
    server-side; no admin token is involved.
    """
    user = resolve_current_user()
    if user is None:
        return None, (jsonify({'error': 'authentication_required'}), 401)
    if normalize_email(getattr(user, 'email', None)) not in _internal_email_allowlist():
        return None, (jsonify({'error': 'operations_forbidden'}), 403)
    return user, None


def _no_store(result):
    """Mark an authenticated operations response private + no-store."""
    response, status = result
    response.headers['Cache-Control'] = 'no-store, private'
    response.headers['Pragma'] = 'no-cache'
    return response, status


@share_artifact_operations_browser_bp.route('/operations/overview', methods=['GET'])
def operations_overview():
    _user, denied = _authorize_internal_operator()
    if denied is not None:
        return denied
    return _no_store(build_overview_response())


@share_artifact_operations_browser_bp.route('/operations/artifacts', methods=['GET'])
def operations_artifacts():
    _user, denied = _authorize_internal_operator()
    if denied is not None:
        return denied
    return _no_store(build_artifacts_response(request.args))


@share_artifact_operations_browser_bp.route('/operations/audits', methods=['GET'])
def operations_audits():
    _user, denied = _authorize_internal_operator()
    if denied is not None:
        return denied
    return _no_store(build_audits_response(request.args))
