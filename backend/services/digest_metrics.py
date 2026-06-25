"""Digest metrics & return tracking (Phase D2E).

Durable measurement for the D2 return loop, answering: "is the digest actually
bringing users back?" Records each job run and each eligible per-user decision,
plus opens, clicks, and attributed returns — all on our own endpoints, so
tracking is provider-independent (no reliance on a mail provider's analytics).

This module records and aggregates measurement only. It never composes content,
never sends email, and never changes a send/suppress decision.
"""

from __future__ import annotations

from datetime import timedelta

from flask import current_app

from models.digest_metrics import (
    DEFAULT_DIGEST_TYPE,
    STATUS_SENT,
    STATUS_SUPPRESSED,
    DigestDelivery,
    DigestRun,
)
from services.product_events import (
    RETURN_VIA_CLICK,
    RETURN_VIA_SIGN_IN,
    SOURCE_CLICK_REDIRECT,
    SOURCE_SIGN_IN,
    record_digest_clicked,
    record_digest_generated,
    record_digest_opened,
    record_digest_returned,
    record_digest_sent,
    record_digest_suppressed,
)
from utils.auth_tokens import generate_tracking_token, verify_tracking_token
from utils.db import db
from utils.time import utc_now_naive


# How long after a send a subsequent visit still counts as a digest-driven return.
RETURN_ATTRIBUTION_WINDOW_DAYS = 7


# ── Run-level aggregate ───────────────────────────────────────────────────────

def create_run(*, reference_date=None, dry_run=False):
    """Open a DigestRun row (zeroed) and return it with an id assigned."""
    run = DigestRun(
        started_at=utc_now_naive(),
        dry_run=bool(dry_run),
        reference_date=_iso_date(reference_date),
    )
    db.session.add(run)
    db.session.flush()  # assign id without committing the whole job yet
    return run


def finish_run(run, summary):
    """Write the final aggregate counts onto a DigestRun row and commit."""
    if run is None:
        return None
    run.finished_at = utc_now_naive()
    run.considered = summary.get('considered', 0)
    run.sent = summary.get('sent', 0)
    run.suppressed = summary.get('suppressed', 0)
    run.skipped = summary.get('skipped', 0)
    run.errors = summary.get('errors', 0)
    run.breakdown = {
        'suppressed_by_reason': summary.get('suppressed_by_reason', {}),
        'skipped_by_reason': summary.get('skipped_by_reason', {}),
    }
    db.session.commit()
    return run


# ── Per-delivery records ──────────────────────────────────────────────────────

def record_delivery(*, user_id, team_id=None, status, reason=None, sent_at=None,
                    run_id=None, digest_type=DEFAULT_DIGEST_TYPE):
    """Persist one eligible decision (a send or an engine-level suppression)."""
    delivery = DigestDelivery(
        run_id=run_id,
        user_id=user_id,
        team_id=team_id,
        digest_type=digest_type,
        status=status,
        reason=reason,
        sent_at=sent_at if status == STATUS_SENT else None,
    )
    db.session.add(delivery)
    db.session.flush()  # assign id so a tracking token can be minted
    return delivery


def record_open(token, *, when=None):
    """Record an email open from a tracking token. Returns True if attributed."""
    delivery = _delivery_for_token(token)
    if delivery is None:
        return False
    when = when or utc_now_naive()
    if delivery.opened_at is None:
        delivery.opened_at = when
    delivery.open_count = (delivery.open_count or 0) + 1
    record_digest_opened(
        delivery_id=delivery.id, user_id=delivery.user_id,
        team_id=delivery.team_id, occurred_at=when,
    )
    db.session.commit()
    return True


def record_click(token, *, when=None):
    """Record a deep-link click from a tracking token.

    Also attributes a return (a click brings the user back). Returns the
    DigestDelivery (so the caller can redirect to the team), or None.
    """
    delivery = _delivery_for_token(token)
    if delivery is None:
        return None
    when = when or utc_now_naive()
    if delivery.clicked_at is None:
        delivery.clicked_at = when
    delivery.click_count = (delivery.click_count or 0) + 1
    newly_returned = _attribute_to_delivery(delivery, when)
    record_digest_clicked(
        delivery_id=delivery.id, user_id=delivery.user_id,
        team_id=delivery.team_id, occurred_at=when,
    )
    if newly_returned:
        record_digest_returned(
            user_id=delivery.user_id, delivery_id=delivery.id, team_id=delivery.team_id,
            attribution_source=RETURN_VIA_CLICK, source=SOURCE_CLICK_REDIRECT, occurred_at=when,
        )
    db.session.commit()
    return delivery


def attribute_return(user_id, *, when=None, window_days=RETURN_ATTRIBUTION_WINDOW_DAYS):
    """Attribute a return to a user's most recent un-returned sent digest.

    A return is the first time a user comes back after a digest (e.g. signs in
    or clicks through) within the attribution window. Idempotent: once a
    delivery has a ``returned_at`` it is never moved. Returns True if a return
    was newly attributed.
    """
    if user_id is None:
        return False
    when = when or utc_now_naive()
    cutoff = when - timedelta(days=window_days)
    delivery = (
        DigestDelivery.query
        .filter(
            DigestDelivery.user_id == user_id,
            DigestDelivery.status == STATUS_SENT,
            DigestDelivery.returned_at.is_(None),
            DigestDelivery.sent_at.isnot(None),
            DigestDelivery.sent_at >= cutoff,
            DigestDelivery.sent_at <= when,
        )
        .order_by(DigestDelivery.sent_at.desc())
        .first()
    )
    if delivery is None:
        return False
    delivery.returned_at = when
    record_digest_returned(
        user_id=user_id, delivery_id=delivery.id, team_id=delivery.team_id,
        attribution_source=RETURN_VIA_SIGN_IN, source=SOURCE_SIGN_IN, occurred_at=when,
    )
    db.session.commit()
    return True


def _attribute_to_delivery(delivery, when):
    """Mark this sent delivery as a return; return True if newly attributed."""
    if delivery.status == STATUS_SENT and delivery.returned_at is None and delivery.sent_at is not None:
        delivery.returned_at = when
        return True
    return False


def _delivery_for_token(token):
    delivery_id = verify_tracking_token(token)
    if delivery_id is None:
        return None
    return db.session.get(DigestDelivery, delivery_id)


# ── Tracking URLs (provider-independent; our own endpoints) ───────────────────

def tracking_urls_for(delivery_id):
    """Open-pixel + click URLs for a sent delivery, keyed by a signed token."""
    token = generate_tracking_token(delivery_id)
    base = (current_app.config.get('PUBLIC_API_BASE_URL') or '').rstrip('/')
    return {
        'open_url': f'{base}/api/digest/open?t={token}',
        'click_url': f'{base}/api/digest/click?t={token}',
        'token': token,
    }


# ── Aggregate overview (admin) ────────────────────────────────────────────────

def metrics_overview(*, recent_runs=10):
    """Lifetime digest metrics for the operator: the required totals + rates."""
    sent = _count(DigestDelivery.status == STATUS_SENT)
    suppressed = _count(DigestDelivery.status == STATUS_SUPPRESSED)
    opens = _count(DigestDelivery.status == STATUS_SENT, DigestDelivery.opened_at.isnot(None))
    clicks = _count(DigestDelivery.status == STATUS_SENT, DigestDelivery.clicked_at.isnot(None))
    returns = _count(DigestDelivery.status == STATUS_SENT, DigestDelivery.returned_at.isnot(None))

    considered = db.session.query(db.func.coalesce(db.func.sum(DigestRun.considered), 0)).scalar() or 0
    open_events = _sum(DigestDelivery.open_count)
    click_events = _sum(DigestDelivery.click_count)

    runs = DigestRun.query.order_by(DigestRun.id.desc()).limit(recent_runs).all()

    return {
        'capability': 'digest_metrics',
        'generated_at': utc_now_naive().isoformat(),
        'totals': {
            'considered': int(considered),
            'sent': sent,
            'suppressed': suppressed,
            'opens': opens,
            'open_events': open_events,
            'clicks': clicks,
            'click_events': click_events,
            'returns': returns,
        },
        'rates': {
            'open_rate': _rate(opens, sent),
            'click_rate': _rate(clicks, sent),
            'return_rate': _rate(returns, sent),
        },
        'suppressed_by_reason': _suppressed_by_reason(),
        'recent_runs': [run.to_dict() for run in runs],
    }


def _count(*conditions):
    query = DigestDelivery.query
    for condition in conditions:
        query = query.filter(condition)
    return query.count()


def _sum(column):
    return int(db.session.query(db.func.coalesce(db.func.sum(column), 0)).scalar() or 0)


def _rate(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else 0.0


def _suppressed_by_reason():
    rows = (
        db.session.query(DigestDelivery.reason, db.func.count(DigestDelivery.id))
        .filter(DigestDelivery.status == STATUS_SUPPRESSED)
        .group_by(DigestDelivery.reason)
        .all()
    )
    return {(reason or 'unknown'): count for reason, count in rows}


def _iso_date(value):
    if value is None:
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()[:10]
    return str(value)[:10]


# ── Recorder used by the digest job (binds run + delivery persistence) ────────

class DbDigestRecorder:
    """Persists run + delivery metrics for a live digest run.

    Passed to ``deliver_team_digest`` as the ``recorder``: on a send it records a
    delivery and returns tracking URLs to embed in the email; on a suppression it
    records the reason. The job calls ``start_run`` / ``finish_run`` around the
    pass. A null recorder (the default) records nothing — behavior is unchanged.
    """

    def __init__(self):
        self.run = None

    def start_run(self, *, reference_date=None, dry_run=False):
        self.run = create_run(reference_date=reference_date, dry_run=dry_run)
        return self.run

    def on_decision(self, user, *, status, team_id=None, reason=None, sent_at=None,
                    digest_type=DEFAULT_DIGEST_TYPE):
        delivery = record_delivery(
            run_id=self.run.id if self.run is not None else None,
            user_id=getattr(user, 'id', None),
            team_id=team_id,
            status=status,
            reason=reason,
            sent_at=sent_at,
            digest_type=digest_type,
        )

        # Canonical events: every eligible decision is first a generated payload,
        # then either a send or an engine suppression. Emitted on the same session
        # as the delivery, so they commit atomically with the run.
        user_id = getattr(user, 'id', None)
        run_id = self.run.id if self.run is not None else None
        reference_date = self.run.reference_date if self.run is not None else None
        record_digest_generated(
            user_id=user_id, team_id=team_id, run_id=run_id,
            reference_date=reference_date, digest_type=digest_type,
            has_meaningful_change=(status == STATUS_SENT), occurred_at=sent_at,
        )
        if status == STATUS_SENT:
            record_digest_sent(
                user_id=user_id, team_id=team_id, run_id=run_id,
                delivery_id=delivery.id, digest_type=digest_type, occurred_at=sent_at,
            )
            return tracking_urls_for(delivery.id)
        record_digest_suppressed(
            user_id=user_id, team_id=team_id, run_id=run_id,
            reason=reason, digest_type=digest_type,
        )
        return None

    def finish_run(self, summary):
        return finish_run(self.run, summary)
