"""Transactional email delivery (Phase D2B).

A single seam (``send_email``) behind which the provider is selected by
environment and config:

  • development / test         -> in-memory outbox, never a real send
  • production + EMAIL_PROVIDER -> a real transactional provider (Resend)

Provider calls live only here; callers (e.g. utils.auth_email) compose a message
and hand it to ``send_email``. No secret is stored in code — the API key and
sender come from config. The magic link / token is never logged in production,
and the in-memory outbox is never used as a production channel.
"""

from __future__ import annotations

from flask import current_app


PROVIDER_OUTBOX = 'outbox'
PROVIDER_RESEND = 'resend'

RESEND_ENDPOINT = 'https://api.resend.com/emails'
DEFAULT_SEND_TIMEOUT = 10.0

# In-memory capture for dev/test inspection only. Never used in production.
outbox = []


def reset_outbox():
    """Clear the captured outbox (dev/test only)."""
    outbox.clear()


def _redact(email):
    if not email or '@' not in str(email):
        return '***'
    name, _, domain = str(email).partition('@')
    head = name[0] if name else ''
    return f'{head}***@{domain}'


def _env():
    return current_app.config.get('APP_ENV', 'development')


def _provider_name():
    """Resolve the active provider. Non-production always uses the outbox."""
    if _env() != 'production':
        return PROVIDER_OUTBOX
    return (current_app.config.get('EMAIL_PROVIDER') or PROVIDER_RESEND).strip().lower()


def _capture(to, subject, text, html, extra):
    record = {
        'to': to,
        'email': to,            # backward-compatible alias (D1C outbox shape)
        'subject': subject,
        'text': text,
        'html': html,
    }
    if extra:
        record.update(extra)
    outbox.append(record)
    return record


def send_email(to, subject, *, text=None, html=None, **extra):
    """Send one email through the environment-appropriate provider.

    Returns a result dict ``{ok, provider, to, [error]}``. Never raises: a
    transport or provider failure is logged (redacted) and returned as ok=False
    so callers (and the magic-link flow) degrade gracefully instead of 500ing.
    """
    provider = _provider_name()

    if provider == PROVIDER_OUTBOX:
        _capture(to, subject, text, html, extra)
        if _env() == 'development' and extra.get('link'):
            current_app.logger.info('[dev] email to %s (%s) -> %s', to, subject, extra['link'])
        else:
            current_app.logger.info('[dev] email captured for %s (%s)', _redact(to), subject)
        return {'ok': True, 'provider': PROVIDER_OUTBOX, 'to': to}

    if provider == PROVIDER_RESEND:
        return _send_via_resend(to, subject, text, html)

    current_app.logger.error('Unknown EMAIL_PROVIDER %r; email to %s not sent.', provider, _redact(to))
    return {'ok': False, 'provider': provider, 'to': to, 'error': 'unknown_provider'}


def _send_via_resend(to, subject, text, html):
    api_key = current_app.config.get('EMAIL_API_KEY')
    sender = current_app.config.get('EMAIL_FROM')
    if not api_key or not sender:
        current_app.logger.error(
            'Email provider not configured (EMAIL_API_KEY/EMAIL_FROM); email to %s not sent.',
            _redact(to),
        )
        return {'ok': False, 'provider': PROVIDER_RESEND, 'to': to, 'error': 'not_configured'}

    payload = {'from': sender, 'to': [to], 'subject': subject}
    if html:
        payload['html'] = html
    if text:
        payload['text'] = text

    timeout = float(current_app.config.get('EMAIL_SEND_TIMEOUT', DEFAULT_SEND_TIMEOUT))
    try:
        import requests
        response = requests.post(
            RESEND_ENDPOINT,
            json=payload,
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
    except Exception as exc:  # transport-level failure
        current_app.logger.error('Email to %s failed (transport): %s', _redact(to), type(exc).__name__)
        return {'ok': False, 'provider': PROVIDER_RESEND, 'to': to, 'error': 'transport_error'}

    if 200 <= response.status_code < 300:
        current_app.logger.info('Email sent to %s via %s', _redact(to), PROVIDER_RESEND)
        return {'ok': True, 'provider': PROVIDER_RESEND, 'to': to}

    current_app.logger.error('Email to %s failed: provider status %s', _redact(to), response.status_code)
    return {'ok': False, 'provider': PROVIDER_RESEND, 'to': to, 'error': f'status_{response.status_code}'}


def email_delivery_health():
    """Lightweight readiness check: is the active provider configured to send?"""
    provider = _provider_name()
    issues = []
    if provider == PROVIDER_OUTBOX:
        ready = True
    elif provider == PROVIDER_RESEND:
        if not current_app.config.get('EMAIL_API_KEY'):
            issues.append('EMAIL_API_KEY is not set')
        if not current_app.config.get('EMAIL_FROM'):
            issues.append('EMAIL_FROM is not set')
        ready = not issues
    else:
        issues.append(f'unknown EMAIL_PROVIDER: {provider}')
        ready = False
    return {
        'environment': _env(),
        'provider': provider,
        'sender_configured': bool(current_app.config.get('EMAIL_FROM')),
        'ready': ready,
        'issues': issues,
    }
