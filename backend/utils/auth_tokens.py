"""Signed, stateless auth tokens (Phase D1C).

Magic-link tokens (short-lived) prove control of an email; bearer tokens
(longer-lived) authenticate API requests. Both are signed with itsdangerous
using purpose-specific salts, so a token minted for one purpose can never be
accepted for the other. Nothing is stored server-side — there is no sessions
table — so verification is pure signature + age checking. No passwords.
"""

from __future__ import annotations

from flask import current_app
from itsdangerous import BadData, URLSafeTimedSerializer


MAGIC_LINK_SALT = 'baseballos.auth.magic-link.v1'
BEARER_TOKEN_SALT = 'baseballos.auth.bearer.v1'

_DEFAULT_MAGIC_LINK_TTL = 900
_DEFAULT_BEARER_TTL = 2592000


def normalize_email(value):
    """Lowercase/trim an email and apply minimal structural validation.

    Returns the normalized address or None. This is not an RFC validator — it
    only rejects values that obviously are not an address so callers can treat
    None as "not a usable email".
    """
    if value is None:
        return None
    email = str(value).strip().lower()
    if not email or ' ' in email:
        return None
    if email.count('@') != 1:
        return None
    local, _, domain = email.partition('@')
    if not local or not domain or '.' not in domain:
        return None
    return email


def _secret():
    return current_app.config.get('USER_AUTH_SECRET') or current_app.config.get('SECRET_KEY')


def _serializer():
    secret = _secret()
    if not secret:
        raise RuntimeError(
            'USER_AUTH_SECRET (or SECRET_KEY) must be configured to sign auth tokens.'
        )
    return URLSafeTimedSerializer(secret)


def _magic_link_ttl():
    return int(current_app.config.get('MAGIC_LINK_TTL_SECONDS', _DEFAULT_MAGIC_LINK_TTL))


def _bearer_ttl():
    return int(current_app.config.get('AUTH_TOKEN_TTL_SECONDS', _DEFAULT_BEARER_TTL))


def generate_magic_link_token(email):
    """Sign a short-lived token that embeds the (already normalized) email."""
    return _serializer().dumps({'email': email}, salt=MAGIC_LINK_SALT)


def verify_magic_link_token(token, *, max_age=None):
    """Return the email from a valid, unexpired magic-link token, else None."""
    if not token or not _secret():
        return None
    try:
        data = _serializer().loads(
            token,
            salt=MAGIC_LINK_SALT,
            max_age=_magic_link_ttl() if max_age is None else max_age,
        )
    except BadData:
        return None
    if not isinstance(data, dict):
        return None
    return normalize_email(data.get('email'))


def generate_bearer_token(user):
    """Sign a longer-lived bearer token that embeds the user id and email."""
    return _serializer().dumps(
        {'uid': user.id, 'email': user.email},
        salt=BEARER_TOKEN_SALT,
    )


def verify_bearer_token(token, *, max_age=None):
    """Return {'uid', 'email'} from a valid, unexpired bearer token, else None."""
    if not token or not _secret():
        return None
    try:
        data = _serializer().loads(
            token,
            salt=BEARER_TOKEN_SALT,
            max_age=_bearer_ttl() if max_age is None else max_age,
        )
    except BadData:
        return None
    if not isinstance(data, dict) or 'uid' not in data:
        return None
    return {'uid': data.get('uid'), 'email': data.get('email')}


def build_magic_link(token):
    """Build the frontend verify URL the magic-link email points to."""
    base = (current_app.config.get('FRONTEND_BASE_URL') or '').rstrip('/')
    return f'{base}/auth/verify?token={token}'
