"""Digest delivery wiring + daily job (Phase D2D).

Connects the D2C composition engine to the D2B email seam and the existing
APScheduler infrastructure. A team digest is sent only when ALL hold:

  * the user explicitly opted in and the cadence is due,
  * the user's email is verified and usable,
  * the user has a primary followed team, and
  * the composition engine returns ``send=True`` (a meaningful, fresh change).

Suppressed digests are never sent. Email goes through the ``send_email`` seam —
no provider (Resend / SMTP) is referenced here, so the delivery layer stays
transport-neutral and provider-independent.
"""

from __future__ import annotations

import logging
from html import escape as _escape

from flask import current_app

from services.digest_composer import build_team_digest
from services.notification_prefs import cadence_due, get_digest_prefs
from utils.auth_tokens import (
    build_unsubscribe_url,
    generate_unsubscribe_token,
    normalize_email,
)
from utils.email_delivery import send_email
from utils.time import utc_now_naive


logger = logging.getLogger('baseballos.digest')

DIGEST_KIND = 'team_digest'
DIGEST_JOB_ID = 'daily_team_digest'

# Per-user delivery outcomes (used for tallying + admin observability).
SENT = 'sent'
SUPPRESSED = 'suppressed'
SKIPPED = 'skipped'
ERROR = 'error'

# Reasons a user is skipped before composition is even attempted.
SKIP_NOT_OPTED_IN = 'not_opted_in'
SKIP_CADENCE_NOT_DUE = 'cadence_not_due'
SKIP_UNVERIFIED_EMAIL = 'unverified_email'
SKIP_NO_EMAIL = 'no_email'


def render_digest_email(payload, *, unsubscribe_url=None, tracking=None):
    """Render (subject, text, html) from a ``compose_digest`` send=True payload.

    Pure string assembly over the transport-neutral payload — it neither sends
    nor decides. Neutral, plain language only; no new intelligence is added.

    When ``tracking`` (``{open_url, click_url}``) is supplied, the HTML CTA points
    through the click URL (a server redirect to the same deep link) and an
    invisible open pixel is appended, so opens/clicks are measurable
    provider-independently. The plain-text body always carries the real deep
    link. Without ``tracking`` the output is unchanged.
    """
    sections = payload.get('sections') or {}
    what_changed = sections.get('what_changed') or {}
    story = sections.get('team_story') or {}
    link = sections.get('deep_link') or {}
    trust = sections.get('trust') or {}
    tracking = tracking or {}

    subject = payload.get('subject') or 'Your team bullpen: what changed'

    lines = []
    headline = (sections.get('bullpen_picture') or {}).get('headline')
    if headline:
        lines.append(headline)
    summary = what_changed.get('summary')
    if summary and summary != headline:
        lines.append(summary)
    for change in (what_changed.get('changes') or []):
        name = change.get('name')
        detail = change.get('change') or change.get('detail')
        if name and detail:
            lines.append(f'- {name}: {detail}')
        elif name:
            lines.append(f'- {name}')
    if story.get('available') and story.get('beat'):
        lines.append(story['beat'])
    data_through = trust.get('data_through')
    if data_through:
        lines.append(f'Data through {data_through}.')

    cta_url = link.get('url')
    cta_label = link.get('label') or 'See your team'
    cta_href = tracking.get('click_url') or cta_url

    text_parts = list(lines)
    if cta_url:
        text_parts.append(f'{cta_label}: {cta_url}')
    if unsubscribe_url:
        text_parts.append(f'Unsubscribe: {unsubscribe_url}')
    text = '\n\n'.join(text_parts)

    html_body = ''.join(f'<p>{_escape(line)}</p>' for line in lines)
    if cta_href:
        html_body += f'<p><a href="{_escape(cta_href)}">{_escape(cta_label)}</a></p>'
    if unsubscribe_url:
        html_body += (
            '<p style="font-size:12px;color:#888;">'
            f'<a href="{_escape(unsubscribe_url)}">Unsubscribe from these emails</a></p>'
        )
    if tracking.get('open_url'):
        html_body += (
            f'<img src="{_escape(tracking["open_url"])}" width="1" height="1" '
            'alt="" style="display:none">'
        )

    return subject, text, html_body


def deliver_team_digest(
    user,
    *,
    reference_date=None,
    dry_run=False,
    digest_builder=build_team_digest,
    sender=send_email,
    recorder=None,
):
    """Compose and (unless ``dry_run``) send one user's team digest.

    Returns a result dict ``{status, reason, team_id, ...}``. Never sends a
    suppressed digest, and never sends without opt-in + a due cadence + a
    verified, usable email. The primary-team and meaningful-change gates are
    enforced by the composition engine (which suppresses), not duplicated here.

    ``digest_builder`` and ``sender`` are injectable for testing; the defaults
    call the real composition engine and the real email seam. ``recorder`` is an
    optional metrics sink (Phase D2E): on a real send it records a delivery and
    returns tracking URLs to embed; on a suppression it records the reason. When
    it is None (the default) nothing is recorded and behavior is identical.
    """
    prefs = get_digest_prefs(user)

    # Gate 1: explicit opt-in + cadence due (no send without opt-in).
    if not prefs['digest_enabled'] or prefs['digest_cadence'] == 'off':
        return {'status': SKIPPED, 'reason': SKIP_NOT_OPTED_IN, 'team_id': None}
    if not cadence_due(prefs['digest_cadence'], reference_date):
        return {'status': SKIPPED, 'reason': SKIP_CADENCE_NOT_DUE, 'team_id': None}

    # Gate 2: verified, usable email.
    if getattr(user, 'email_verified_at', None) is None:
        return {'status': SKIPPED, 'reason': SKIP_UNVERIFIED_EMAIL, 'team_id': None}
    to_email = normalize_email(getattr(user, 'email', None))
    if not to_email:
        return {'status': SKIPPED, 'reason': SKIP_NO_EMAIL, 'team_id': None}

    # Gate 3 + content: compose (the engine suppresses when there is no primary
    # team, the data is stale/unavailable, or nothing meaningful changed).
    frontend_base_url = current_app.config.get('FRONTEND_BASE_URL')
    payload = digest_builder(user, reference_date=reference_date, frontend_base_url=frontend_base_url)
    record = recorder if (recorder is not None and not dry_run) else None
    if not payload.get('send'):
        if record is not None:
            record.on_decision(user, status=SUPPRESSED, team_id=payload.get('team_id'),
                               reason=payload.get('reason'))
        return {'status': SUPPRESSED, 'reason': payload.get('reason'), 'team_id': payload.get('team_id')}

    # Record the send before rendering so the email can carry per-delivery
    # tracking URLs (open pixel + click redirect).
    tracking = None
    if record is not None:
        tracking = record.on_decision(user, status=SENT, team_id=payload.get('team_id'),
                                      sent_at=utc_now_naive())

    unsubscribe_url = build_unsubscribe_url(generate_unsubscribe_token(user))
    subject, text, html_body = render_digest_email(
        payload, unsubscribe_url=unsubscribe_url, tracking=tracking,
    )

    if dry_run:
        return {
            'status': SENT, 'reason': None, 'team_id': payload.get('team_id'),
            'to': to_email, 'subject': subject, 'delivered': False, 'dry_run': True,
        }

    send_result = sender(to_email, subject, text=text, html=html_body, kind=DIGEST_KIND)
    delivered = bool(send_result.get('ok'))
    return {
        'status': SENT if delivered else ERROR,
        'reason': None if delivered else send_result.get('error'),
        'team_id': payload.get('team_id'),
        'to': to_email,
        'provider': send_result.get('provider'),
        'delivered': delivered,
    }


def _new_summary(*, dry_run, reference_date):
    return {
        'capability': 'team_digest_delivery',
        'dry_run': bool(dry_run),
        'reference_date': reference_date.isoformat() if hasattr(reference_date, 'isoformat') else reference_date,
        'considered': 0,
        'sent': 0,
        'suppressed': 0,
        'skipped': 0,
        'errors': 0,
        'suppressed_by_reason': {},
        'skipped_by_reason': {},
    }


def _tally(summary, result):
    status = (result or {}).get('status')
    reason = (result or {}).get('reason')
    if status == SENT:
        summary['sent'] += 1
    elif status == SUPPRESSED:
        summary['suppressed'] += 1
        if reason:
            summary['suppressed_by_reason'][reason] = summary['suppressed_by_reason'].get(reason, 0) + 1
    elif status == SKIPPED:
        summary['skipped'] += 1
        if reason:
            summary['skipped_by_reason'][reason] = summary['skipped_by_reason'].get(reason, 0) + 1
    else:
        summary['errors'] += 1


def _digest_roster():
    from models.user import User
    return User.query.order_by(User.id).all()


def run_digest_job(app, *, reference_date=None, dry_run=False, deliver=None, users=None, recorder=None):
    """Run the daily digest over every user once and return a summary.

    Each user is processed at most once, so a single run never sends a user more
    than one digest. Opt-in, cadence, verified email, primary team, and
    suppression are all honored by ``deliver``. Sends nothing when
    ``dry_run=True`` — useful for admin observability.

    Metrics (Phase D2E): on a live run (``dry_run`` False) that uses the default
    delivery path, a DB-backed recorder persists the run aggregate and each
    delivery. Passing a custom ``deliver`` opts out of auto-recording (the caller
    is in control), and ``dry_run`` never persists. A ``recorder`` may be
    injected for tests.
    """
    summary = _new_summary(dry_run=dry_run, reference_date=reference_date)

    with app.app_context():
        # Only auto-create the DB recorder on the real, persisted path: a live
        # run that did not inject its own delivery function.
        if recorder is None and not dry_run and deliver is None:
            from services.digest_metrics import DbDigestRecorder
            recorder = DbDigestRecorder()
        if recorder is not None:
            recorder.start_run(reference_date=reference_date, dry_run=dry_run)

        active_deliver = deliver
        if active_deliver is None:
            def active_deliver(user, *, reference_date=None, dry_run=False):
                return deliver_team_digest(
                    user, reference_date=reference_date, dry_run=dry_run, recorder=recorder,
                )

        roster = users if users is not None else _digest_roster()
        seen = set()
        for user in roster:
            uid = getattr(user, 'id', None)
            if uid is not None and uid in seen:
                continue
            if uid is not None:
                seen.add(uid)
            summary['considered'] += 1
            try:
                result = active_deliver(user, reference_date=reference_date, dry_run=dry_run)
            except Exception:
                logger.exception('digest delivery failed for user %s', uid)
                summary['errors'] += 1
                continue
            _tally(summary, result)

        if recorder is not None:
            recorder.finish_run(summary)

    logger.info('[digest] run summary: %s', summary)
    return summary


def register_digest_job(scheduler, app, *, trigger=None, hour=7, minute=0, timezone=None):
    """Register the daily digest job on an existing scheduler; returns the job.

    The job is a thin trigger that invokes ``run_digest_job(app)`` — all gating
    and suppression live in the flow. A pre-built ``trigger`` may be supplied
    (tests do this to avoid importing APScheduler).
    """
    if trigger is None:
        from apscheduler.triggers.cron import CronTrigger
        trigger = (
            CronTrigger(hour=hour, minute=minute, timezone=timezone)
            if timezone else CronTrigger(hour=hour, minute=minute)
        )
    return scheduler.add_job(
        func=lambda: run_digest_job(app),
        trigger=trigger,
        id=DIGEST_JOB_ID,
        name='Daily team digest',
        replace_existing=True,
        misfire_grace_time=60 * 60,
    )
