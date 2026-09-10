"""Magic-link email seam (Phase D1C; delivery via D2B).

This stays the single seam the auth code calls. It composes the magic-link
message and hands it to utils.email_delivery, which selects the provider
(in-memory outbox in dev/test, a real transactional provider in production).
Auth code never talks to a provider directly. The outbox / reset_outbox names
are re-exported so existing callers and tests are unchanged.
"""

from utils.email_delivery import outbox, reset_outbox, send_email  # noqa: F401  (re-exported seam)


def send_magic_link(email, link, *, token=None):
    """Compose and deliver the sign-in magic link via the email delivery seam."""
    subject = 'Your BaseballOS sign-in link'
    text = (
        'Sign in to BaseballOS using the link below:\n\n'
        f'{link}\n\n'
        'This link expires shortly. If you did not request it, you can ignore this email.'
    )
    html = (
        '<p>Sign in to BaseballOS using the link below:</p>'
        f'<p><a href="{link}">Sign in to BaseballOS</a></p>'
        '<p>This link expires shortly. If you did not request it, you can ignore this email.</p>'
    )
    return send_email(email, subject, text=text, html=html, kind='magic_link', link=link)
