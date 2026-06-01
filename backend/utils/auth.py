"""
Lightweight admin-token guard for operational/admin endpoints.

This is intentionally NOT a user auth system — no accounts, sessions, or OAuth.
It is a single shared admin token used to gate routes that mutate data, trigger
expensive work (sync, recalculation), or expose validation-only data so a
public/hosted demo can't be driven or inspected by anonymous callers.

Behavior (token comes from app.config['ADMIN_API_TOKEN'], set from the
ADMIN_API_TOKEN env var):

  • Token configured + matching `X-Admin-Token` header → request proceeds.
  • Token configured + missing/incorrect header        → 401 Unauthorized.
  • Token NOT configured, development                  → allowed, with a warning
                                                         (keeps local dev painless).
  • Token NOT configured, production                   → 403 (defensive — in
                                                         practice production fails
                                                         fast at startup, see
                                                         ProductionConfig).
"""

import hmac
from functools import wraps

from flask import current_app, jsonify, request

ADMIN_TOKEN_HEADER = 'X-Admin-Token'


def _expected_token():
    return current_app.config.get('ADMIN_API_TOKEN')


def require_admin_token(view):
    """Decorator that gates a route behind the ADMIN_API_TOKEN admin token."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        expected = _expected_token()
        provided = request.headers.get(ADMIN_TOKEN_HEADER)
        env = current_app.config.get('APP_ENV', 'development')

        if not expected:
            if env == 'production':
                # Should be unreachable — ProductionConfig fails fast when the
                # token is unset — but never silently expose the endpoint.
                return jsonify({
                    'error': 'This endpoint is disabled: ADMIN_API_TOKEN is not configured.',
                }), 403
            current_app.logger.warning(
                '%s allowed without a token: ADMIN_API_TOKEN is unset (development). '
                'Set ADMIN_API_TOKEN to require the %s header.',
                request.path, ADMIN_TOKEN_HEADER,
            )
            return view(*args, **kwargs)

        if not provided or not hmac.compare_digest(provided, expected):
            return jsonify({
                'error': f'Unauthorized: a valid {ADMIN_TOKEN_HEADER} header is required.',
            }), 401

        return view(*args, **kwargs)

    return wrapper
