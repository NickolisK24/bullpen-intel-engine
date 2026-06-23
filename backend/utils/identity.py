"""Identity utility scaffolding (Phase D1B).

This is the seam where Phase D1C magic-link authentication will live. For now it
only knows how to READ a bearer token off the request; it does NOT issue, sign,
or verify tokens, so every request resolves to the anonymous user. Keeping the
seam here means D1C can add token verification in one place without changing any
endpoint that already calls ``resolve_current_user()``.
"""

from flask import request


AUTH_HEADER = 'Authorization'
BEARER_PREFIX = 'Bearer '


def bearer_token(req=None):
    """Return the bearer token from the Authorization header, or None."""
    req = req or request
    header = req.headers.get(AUTH_HEADER, '') or ''
    if header.startswith(BEARER_PREFIX):
        token = header[len(BEARER_PREFIX):].strip()
        return token or None
    return None


def resolve_current_user(req=None):
    """Resolve the authenticated user for this request, or None (anonymous).

    A valid, unexpired bearer token whose embedded user id still matches a stored
    user resolves that user; a missing, malformed, or expired token resolves to
    anonymous. This never raises, so anonymous-safe endpoints stay anonymous-safe.
    """
    token = bearer_token(req)
    if not token:
        return None

    from utils.auth_tokens import verify_bearer_token

    claims = verify_bearer_token(token)
    if not claims or claims.get('uid') is None:
        return None

    from utils.db import db
    from models.user import User

    user = db.session.get(User, claims.get('uid'))
    if user is None:
        return None
    # Defensive: the token's email must still match the stored row.
    if claims.get('email') and user.email != claims.get('email'):
        return None
    return user


def anonymous_identity():
    """The identity payload for an unauthenticated request."""
    return {
        'authenticated': False,
        'user': None,
    }


def identity_for(user):
    """Serialize an identity payload — anonymous when ``user`` is None."""
    if user is None:
        return anonymous_identity()
    return {
        'authenticated': True,
        'user': user.to_dict(),
    }
