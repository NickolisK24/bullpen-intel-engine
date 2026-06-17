from datetime import date, datetime
from types import SimpleNamespace

from services.roster_status import STATUS_BEREAVEMENT
from services.roster_status_audit import (
    AUDIT_LEGITIMATE,
    AUDIT_POSSIBLE_STALE,
    build_recent_inactive_roster_audit,
)


def _log(game_date, games_started=0):
    return SimpleNamespace(game_date=game_date, games_started=games_started)


def _bereavement_status(updated_at):
    return {
        'status': STATUS_BEREAVEMENT,
        'label': 'Bereavement List',
        'updated_at': updated_at,
        'is_inactive_context': True,
    }


def test_recent_relief_with_newer_inactive_status_is_legitimate():
    audit = build_recent_inactive_roster_audit(
        _bereavement_status(datetime(2026, 6, 17, 21, 17, 16).isoformat()),
        [_log(date(2026, 6, 14))],
        date(2026, 6, 17),
    )

    assert audit['classification'] == AUDIT_LEGITIMATE
    assert audit['latest_relief_date'] == '2026-06-14'
    assert audit['roster_status_updated_at'] == '2026-06-17T21:17:16'
    assert audit['label'] == 'Bereavement List'


def test_recent_relief_with_older_inactive_status_is_possible_stale():
    audit = build_recent_inactive_roster_audit(
        _bereavement_status(datetime(2026, 6, 10, 12, 0, 0).isoformat()),
        [_log(date(2026, 6, 14))],
        date(2026, 6, 17),
    )

    assert audit['classification'] == AUDIT_POSSIBLE_STALE
    assert 'predates a newer relief appearance' in audit['reason']


def test_audit_ignores_starts_and_old_relief_logs():
    started = build_recent_inactive_roster_audit(
        _bereavement_status(datetime(2026, 6, 17, 21, 17, 16).isoformat()),
        [_log(date(2026, 6, 14), games_started=1)],
        date(2026, 6, 17),
    )
    old_relief = build_recent_inactive_roster_audit(
        _bereavement_status(datetime(2026, 6, 17, 21, 17, 16).isoformat()),
        [_log(date(2026, 5, 20))],
        date(2026, 6, 17),
    )

    assert started is None
    assert old_relief is None
