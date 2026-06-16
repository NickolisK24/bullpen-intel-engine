"""Single role/read label authority for public bullpen surfaces."""

from services.bullpen_population import usage_logs_by_pitcher
from services.pitcher_public_labels import build_pitcher_labels
from services.pitcher_role import ROLE_WINDOW_DAYS, classify_usage_role


def _value(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def role_logs_by_pitcher(pitcher_ids, reference_date=None):
    """Return the bounded role-window logs used by every public role label."""
    return usage_logs_by_pitcher(
        pitcher_ids,
        days=ROLE_WINDOW_DAYS,
        include_stale=False,
        reference_date=reference_date,
    )


def author_role_read_labels(record, logs_by_pitcher, reference_date=None):
    """Author observed role and public labels once from the shared role window."""
    pitcher = _value(record, 'pitcher')
    pitcher_id = _value(pitcher, 'id')
    logs = (logs_by_pitcher or {}).get(pitcher_id, [])
    role = classify_usage_role(logs or [], reference_date=reference_date)
    labels = build_pitcher_labels(
        availability=_value(record, 'availability'),
        role=role,
        eligibility=_value(record, 'eligibility'),
        roster_status=_value(record, 'roster_status'),
    )
    return role, labels
