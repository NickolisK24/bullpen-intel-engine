import re

from flask import current_app
from sqlalchemy.exc import IntegrityError

from models.audience_subscriber import (
    AUDIENCE_SUBSCRIBER_STATUS_SUBSCRIBED,
    AudienceSubscriber,
)
from utils.audience_email import send_audience_welcome_email
from utils.auth_tokens import normalize_email
from utils.db import db
from utils.email_delivery import email_delivery_health
from utils.time import utc_now_naive


AUDIENCE_SIGNUP_SUCCESS_MESSAGE = 'You are on the list for BaseballOS bullpen notes.'
AUDIENCE_SIGNUP_INVALID_MESSAGE = 'Enter a valid email address.'
AUDIENCE_SIGNUP_DEFAULT_SOURCE = 'homepage_hero'
AUDIENCE_SIGNUP_INVALID_REASON = 'invalid_email'
WELCOME_PROVIDER_MISSING_ERROR = 'email_provider_not_configured'
_SOURCE_PATTERN = re.compile(r'^[a-z0-9_.:-]+$')


def clean_audience_source(value):
    source = str(value or '').strip().lower().replace(' ', '_')[:64]
    if not source or not _SOURCE_PATTERN.match(source):
        return AUDIENCE_SIGNUP_DEFAULT_SOURCE
    return source


def _trim_original_email(value):
    if value is None:
        return None
    original = str(value).strip()
    return original[:320] if original else None


def _success_response(subscriber, *, created, welcome_sent=False):
    return {
        'success': True,
        'message': AUDIENCE_SIGNUP_SUCCESS_MESSAGE,
        'subscriber': subscriber,
        'created': bool(created),
        'welcome_sent': bool(welcome_sent),
    }


def _mark_welcome_result(subscriber, *, sent=False, error=None):
    if sent:
        subscriber.welcome_sent_at = utc_now_naive()
        subscriber.last_welcome_error = None
    else:
        subscriber.last_welcome_error = (error or 'send_failed')[:128]
    subscriber.updated_at = utc_now_naive()
    db.session.commit()


def send_welcome_if_available(subscriber):
    health = email_delivery_health()
    if not health.get('ready'):
        current_app.logger.warning(
            'Audience welcome email skipped because the email provider is not configured.'
        )
        _mark_welcome_result(
            subscriber,
            sent=False,
            error=WELCOME_PROVIDER_MISSING_ERROR,
        )
        return False

    result = send_audience_welcome_email(subscriber.email_normalized)
    if result.get('ok'):
        _mark_welcome_result(subscriber, sent=True)
        return True

    current_app.logger.warning(
        'Audience welcome email failed for subscriber id %s: %s',
        subscriber.id,
        result.get('error') or 'send_failed',
    )
    _mark_welcome_result(subscriber, sent=False, error=result.get('error'))
    return False


def signup_audience_subscriber(email, *, source=None):
    normalized = normalize_email(email)
    if not normalized:
        return {
            'success': False,
            'message': AUDIENCE_SIGNUP_INVALID_MESSAGE,
            'reason': AUDIENCE_SIGNUP_INVALID_REASON,
        }

    existing = AudienceSubscriber.query.filter_by(email_normalized=normalized).first()
    if existing is not None:
        return _success_response(existing, created=False)

    subscriber = AudienceSubscriber(
        email_normalized=normalized,
        email_original=_trim_original_email(email),
        source=clean_audience_source(source),
        status=AUDIENCE_SUBSCRIBER_STATUS_SUBSCRIBED,
    )
    db.session.add(subscriber)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = AudienceSubscriber.query.filter_by(email_normalized=normalized).first()
        if existing is not None:
            return _success_response(existing, created=False)
        raise

    subscriber_id = subscriber.id
    try:
        welcome_sent = send_welcome_if_available(subscriber)
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning(
            'Audience welcome email attempt failed after persistence for subscriber id %s: %s',
            subscriber_id,
            type(exc).__name__,
        )
        welcome_sent = False
    return _success_response(subscriber, created=True, welcome_sent=welcome_sent)
