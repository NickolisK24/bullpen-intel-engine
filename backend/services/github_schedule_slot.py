"""Resolve a delayed GitHub schedule delivery to its authorized cron slot."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.sync_execution_context import (
    MODE_DAILY, MODE_MORNING, MODE_POSTGAME, PRODUCTION_SCHEDULES,
    SOURCE_GITHUB_SCHEDULE, parse_utc_datetime,
)


GITHUB_CRON_EXPRESSIONS = {
    MODE_DAILY: '17 10 * * *',
    MODE_MORNING: '23 14 * * *',
    MODE_POSTGAME: '11 2,4,6 * * *',
}


class GitHubScheduleSlotError(ValueError):
    pass


def resolve_github_schedule_slot(*, mode, event_schedule, launched_at):
    """Return the nearest configured slot at or before a delayed launch."""
    normalized_mode = str(mode or '').strip().lower()
    expected_cron = GITHUB_CRON_EXPRESSIONS.get(normalized_mode)
    if expected_cron is None:
        raise GitHubScheduleSlotError('schedule_mode_invalid')
    if str(event_schedule or '').strip() != expected_cron:
        raise GitHubScheduleSlotError('event_schedule_mismatch')

    launched = parse_utc_datetime(launched_at)
    hours, minute = PRODUCTION_SCHEDULES[SOURCE_GITHUB_SCHEDULE][normalized_mode]
    candidates = []
    for day_offset in (0, 1):
        candidate_day = (launched - timedelta(days=day_offset)).date()
        for hour in hours:
            candidate = datetime(
                candidate_day.year, candidate_day.month, candidate_day.day,
                hour, minute, tzinfo=timezone.utc,
            )
            if candidate <= launched:
                candidates.append(candidate)
    if not candidates:
        raise GitHubScheduleSlotError('configured_slot_not_found')
    return max(candidates)
