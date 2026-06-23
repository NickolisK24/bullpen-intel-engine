"""Magic-link delivery adapter (Phase D1C).

MVP delivery: an in-memory outbox that dev and tests can inspect, plus redacted
logging. A production email provider is a config-driven placeholder — this phase
adds no provider dependency. The magic link / token is never returned in an HTTP
response and is never logged in production.
"""

from flask import current_app


# In-memory capture for dev/test inspection only. Never a real delivery channel.
outbox = []


def reset_outbox():
    """Clear the captured outbox (tests/dev only)."""
    outbox.clear()


def _redact(email):
    if not email or '@' not in email:
        return '***'
    name, _, domain = email.partition('@')
    head = name[0] if name else ''
    return f'{head}***@{domain}'


def send_magic_link(email, link, *, token=None):
    """Deliver a magic link. Captures to the outbox; logs redacted in production."""
    record = {'email': email, 'link': link}
    outbox.append(record)
    env = current_app.config.get('APP_ENV', 'development')
    if env == 'production':
        # A real provider integration belongs here. Never log the link or token.
        current_app.logger.info('Magic-link email queued for %s', _redact(email))
    else:
        current_app.logger.info('[dev] magic-link for %s -> %s', email, link)
    return record
