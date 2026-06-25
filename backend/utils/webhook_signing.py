"""Webhook signature verification (Svix scheme, used by the email provider).

The transactional email provider (Resend) signs webhooks with the Svix scheme:
an HMAC-SHA256 over ``"{id}.{timestamp}.{body}"`` keyed by the webhook signing
secret, base64-encoded, presented in the ``svix-signature`` header as
space-separated ``v1,<sig>`` entries. We verify it so spoofed deliverability
facts cannot be injected into the append-only Product Intelligence log.

This module verifies only; it never sends, parses business data, or records.
"""

from __future__ import annotations

import base64
import hashlib
import hmac


def _key_bytes(secret):
    """Derive the HMAC key bytes from a webhook secret.

    Svix secrets look like ``whsec_<base64>``; the bytes after the prefix are the
    base64-encoded key. If the value is not in that form, fall back to its raw
    UTF-8 bytes so a plain shared secret still works.
    """
    if not secret:
        return b''
    raw = secret.split('_', 1)[1] if secret.startswith('whsec_') else secret
    try:
        return base64.b64decode(raw)
    except Exception:
        return secret.encode('utf-8')


def expected_signature(secret, svix_id, svix_timestamp, body):
    """Compute the base64 HMAC-SHA256 signature for one webhook payload."""
    signed = f'{svix_id}.{svix_timestamp}.{body}'.encode('utf-8')
    digest = hmac.new(_key_bytes(secret), signed, hashlib.sha256).digest()
    return base64.b64encode(digest).decode('utf-8')


def verify_webhook_signature(secret, *, svix_id, svix_timestamp, body, signature_header):
    """Return True iff ``signature_header`` carries a valid ``v1`` signature.

    Constant-time comparison; any missing input fails closed.
    """
    if not (secret and svix_id and svix_timestamp and signature_header):
        return False
    expected = expected_signature(secret, svix_id, svix_timestamp, body)
    for part in str(signature_header).split():
        version, _, sig = part.partition(',')
        if version == 'v1' and sig and hmac.compare_digest(sig, expected):
            return True
    return False
