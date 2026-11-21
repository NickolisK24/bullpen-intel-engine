"""Minimal production health contract (WP-0.2, EOS-008).

One pure evaluation over what the public API already serves, so a scheduled
check can answer the operational questions without database credentials:

* Is the API serving requests, in production mode, from a known release?
* Did a publication happen when one was expected?
* Is the published data correctly dated?
* Is the public read model internally consistent?
* Is a stale historical read being presented as current?

Offseason rule: a quiet day is not an outage. BaseballOS publishes a trusted
snapshot on schedule every day whether or not games were played, so the
expected signal is a recent *publication*, not new games or appearances. A
``data_through`` that stops moving after the last game is normal; it is only a
failure when it is presented as a current Team State.

Severities:

``critical``  the answer to a question above is "no"; the check exits non-zero.
``warning``   degraded or unverifiable, worth a look, never paged alone.
``ok`` / ``info``  healthy, or a recorded fact (for example "offseason").
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Optional

CONTRACT = 'baseballos_production_health_v1'

SEVERITY_CRITICAL = 'critical'
SEVERITY_WARNING = 'warning'
SEVERITY_OK = 'ok'
SEVERITY_INFO = 'info'

EXPECTED_CLUB_COUNT = 30
# A trusted snapshot is published on schedule at least daily, in season and
# out. 36 hours tolerates one late or retried window without paging.
MAX_PUBLICATION_AGE = timedelta(hours=36)
# A current Team State read describes the next pregame. Beyond this many days
# past its data-through date it can only be a stale read shown as current
# (the October 2026 failure). In season the longest legitimate gap is the
# All-Star break.
MAX_CURRENT_READ_DATA_AGE_DAYS = 5
SEASON_COMPLETE_OUTCOME = 'season_complete'


def _mapping(value) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _parse_date(value) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _parse_datetime(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value)) if value else None
        except ValueError:
            return None
    if parsed is None:
        return None
    # Backend timestamps are naive UTC.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _check(name, severity, detail, **facts):
    return {'check': name, 'severity': severity, 'detail': detail, **facts}


def evaluate_production_health(
    *,
    health: Optional[Mapping[str, Any]],
    health_status_code: Optional[int],
    listing: Optional[Mapping[str, Any]],
    listing_status_code: Optional[int],
    now: datetime,
    expected_release: Optional[str] = None,
    release_is_current: Optional[bool] = None,
) -> dict:
    """Evaluate one observation of the public API.

    ``health`` is ``GET /api/health`` and ``listing`` is
    ``GET /api/bullpen/team-states``; either may be ``None`` when the request
    failed. ``release_is_current`` is the caller's comparison of the deployed
    release against ``expected_release`` (the latest commit that changed
    deployable backend code); ``None`` means it could not be compared.
    """
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    checks = []
    health = _mapping(health)
    listing = _mapping(listing)

    # 1. Serving.
    if health_status_code == 200 and health.get('status') == 'ok':
        checks.append(_check('api_serving', SEVERITY_OK, 'GET /api/health returned ok.'))
    else:
        checks.append(_check(
            'api_serving', SEVERITY_CRITICAL,
            'GET /api/health did not return ok.', http_status=health_status_code,
        ))
    if health and health.get('environment') != 'production':
        checks.append(_check(
            'api_environment', SEVERITY_CRITICAL,
            'The API does not report the production environment.',
            environment=health.get('environment'),
        ))

    # 2. Deployment identity.
    release = health.get('release')
    if not release:
        checks.append(_check(
            'deployed_release', SEVERITY_WARNING,
            'The API does not report its deployed commit; deployment identity is unverified.',
        ))
    elif release_is_current is False:
        checks.append(_check(
            'deployed_release', SEVERITY_CRITICAL,
            'The deployed commit does not contain the latest backend change on main.',
            release=release, expected_release=expected_release,
        ))
    elif release_is_current is True:
        checks.append(_check(
            'deployed_release', SEVERITY_OK,
            'The deployed commit contains the latest backend change on main.',
            release=release, expected_release=expected_release,
        ))
    else:
        checks.append(_check(
            'deployed_release', SEVERITY_INFO,
            'Deployed commit reported; it was not compared with main.', release=release,
        ))

    # 3. Read model.
    if listing_status_code != 200 or not listing:
        checks.append(_check(
            'read_model_serving', SEVERITY_CRITICAL,
            'GET /api/bullpen/team-states did not return a listing.',
            http_status=listing_status_code,
        ))
        return _result(checks, now)

    teams = listing.get('teams') if isinstance(listing.get('teams'), list) else []
    represented = listing.get('represented_team_count')
    withheld = listing.get('withheld_team_count')
    counted_represented = sum(
        1 for row in teams if _mapping(_mapping(row).get('team_state')).get('available') is True
    )
    consistent = (
        listing.get('expected_team_count') == EXPECTED_CLUB_COUNT
        and listing.get('team_count') == EXPECTED_CLUB_COUNT
        and len(teams) == EXPECTED_CLUB_COUNT
        and isinstance(represented, int) and isinstance(withheld, int)
        and represented + withheld == EXPECTED_CLUB_COUNT
        and represented == counted_represented
    )
    if consistent:
        checks.append(_check(
            'read_model_consistency', SEVERITY_OK,
            'The 30-club listing is internally consistent.',
            represented=represented, withheld=withheld,
        ))
    else:
        checks.append(_check(
            'read_model_consistency', SEVERITY_CRITICAL,
            'The 30-club listing is internally inconsistent.',
            team_count=listing.get('team_count'), rows=len(teams),
            represented=represented, withheld=withheld,
            counted_represented=counted_represented,
        ))

    # 4. Publication cadence.
    authority = _mapping(listing.get('publication_authority'))
    published_at = _parse_datetime(authority.get('published_at'))
    if authority.get('snapshot_id') is None or published_at is None:
        checks.append(_check(
            'publication_recent', SEVERITY_CRITICAL,
            'No trusted published snapshot is serving the read model.',
        ))
    else:
        age = now - published_at
        facts = {
            'snapshot_id': authority.get('snapshot_id'),
            'published_at': published_at.isoformat(),
            'age_hours': round(age.total_seconds() / 3600, 1),
        }
        if age > MAX_PUBLICATION_AGE:
            checks.append(_check(
                'publication_recent', SEVERITY_CRITICAL,
                'No scheduled publication within the expected window.', **facts,
            ))
        elif age < timedelta(minutes=-5):
            checks.append(_check(
                'publication_recent', SEVERITY_CRITICAL,
                'The publication timestamp is in the future.', **facts,
            ))
        else:
            checks.append(_check(
                'publication_recent', SEVERITY_OK, 'A recent scheduled publication is serving.',
                **facts,
            ))

    # 5. Dating.
    data_through = _parse_date(
        authority.get('data_through') or _mapping(listing.get('freshness')).get('data_through')
    )
    today = now.date()
    if data_through is None:
        checks.append(_check(
            'data_dating', SEVERITY_CRITICAL, 'The serving publication has no data-through date.',
        ))
    elif data_through > today or (published_at and data_through > published_at.date()):
        checks.append(_check(
            'data_dating', SEVERITY_CRITICAL,
            'The data-through date is later than the publication itself.',
            data_through=data_through.isoformat(),
        ))
    else:
        checks.append(_check(
            'data_dating', SEVERITY_OK, 'The data-through date precedes the publication.',
            data_through=data_through.isoformat(),
        ))

    # 6. Stale read presented as current / offseason quiet day.
    season_complete = sum(
        1 for row in teams
        if _mapping(_mapping(row).get('team_state')).get('outcome') == SEASON_COMPLETE_OUTCOME
    )
    if data_through is not None and isinstance(represented, int):
        data_age_days = (today - data_through).days
        if represented > 0 and data_age_days > MAX_CURRENT_READ_DATA_AGE_DAYS:
            checks.append(_check(
                'stale_read_presented_as_current', SEVERITY_CRITICAL,
                'Current Team State reads are served from data that is too old to be current.',
                represented=represented, data_age_days=data_age_days,
            ))
        elif represented == 0 and season_complete == EXPECTED_CLUB_COUNT:
            checks.append(_check(
                'season_phase', SEVERITY_INFO,
                'Offseason: every club is Season Complete; no current reads are expected.',
                data_age_days=data_age_days,
            ))
        elif represented == 0:
            checks.append(_check(
                'season_phase', SEVERITY_WARNING,
                'No club has a current read, and not every club is Season Complete.',
                season_complete=season_complete, data_age_days=data_age_days,
            ))
        else:
            checks.append(_check(
                'season_phase', SEVERITY_INFO, 'In season: current reads are being served.',
                represented=represented, data_age_days=data_age_days,
            ))
    return _result(checks, now)


def _result(checks, now):
    critical = [item['check'] for item in checks if item['severity'] == SEVERITY_CRITICAL]
    warnings = [item['check'] for item in checks if item['severity'] == SEVERITY_WARNING]
    return {
        'contract': CONTRACT,
        'observed_at': now.isoformat(),
        'status': 'critical' if critical else ('degraded' if warnings else 'healthy'),
        'critical_checks': critical,
        'warning_checks': warnings,
        'checks': checks,
    }
