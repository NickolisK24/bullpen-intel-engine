from datetime import date, timedelta

from sqlalchemy import asc, desc, or_

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import board_freshness
from services import game_shape
from services import pitcher_season_ledger_coverage
from services import slate_coverage
from services import starter_assignment_context
from services import team_board_workload_coverage
from utils.games_started import RELIEF, START, games_started_state


CAPABILITY = 'public_team_relief_work'
RECENT_GAME_DATES_MAX = 5
LOOKBACK_DAYS = 30
WINDOW_DAYS = (7, 14)
WORKLOAD_OVERVIEW_WINDOW_DAYS = (3, 7, 14, 30)
WORKLOAD_OVERVIEW_CONTRACT = 'team_board_workload_overview_v1'
WORKLOAD_WINDOWS_METHOD_VERSION = 'public_team_relief_work_windows_v1'
WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION = (
    'public_team_relief_work_windows_public_v1'
)
WORKLOAD_WINDOWS_CARRIER_CONTRACT = 'team_board_workload_windows_carrier_v1'
WORKLOAD_WINDOWS_POPULATION_BASIS = 'official_appearance_team_relief_appearances'
WORKLOAD_WINDOWS_POPULATION_AUTHORITY = 'game_log.appearance_team_id_resolved'
WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY = (
    'historical_appearance_team_not_current_roster'
)
WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY = 'calendar_day_inclusive_through_date_v1'

DEPLOYMENT_PROFILE_WINDOW_DAYS = 14
DEPLOYMENT_PROFILE_METHOD_VERSION = 'public_team_deployment_profile_v1'
DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION = 'public_team_deployment_profile_public_v1'
DEPLOYMENT_PROFILE_CARRIER_CONTRACT = 'team_board_deployment_profile_carrier_v1'
DEPLOYMENT_PROFILE_POPULATION_BASIS = WORKLOAD_WINDOWS_POPULATION_BASIS
DEPLOYMENT_PROFILE_POPULATION_AUTHORITY = WORKLOAD_WINDOWS_POPULATION_AUTHORITY
DEPLOYMENT_PROFILE_MEMBERSHIP_AUTHORITY = WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY
DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY = WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY
DEPLOYMENT_PROFILE_MULTI_INNING_MIN_OUTS = 4
DEPLOYMENT_PROFILE_COMPLETE = 'complete'
DEPLOYMENT_PROFILE_WITHHELD = 'withheld'
DEPLOYMENT_PROFILE_DATA_THROUGH_MISSING = 'data_through_missing'

RECENT_USAGE_REST_CONTRACT = 'team_board_recent_usage_rest_v1'
RECENT_USAGE_REST_METHOD_VERSION = 'team_board_recent_usage_rest_v1'
RECENT_USAGE_REST_PUBLIC_CONTRACT_VERSION = 'team_board_recent_usage_rest_v1'
RECENT_USAGE_REST_REFERENCE_DATE_POLICY = 'calendar_day_inclusive_through_date_v1'
RECENT_USAGE_REST_POPULATION_BASIS = (
    'official_appearance_team_relief_appearances_and_frozen_active_bullpen'
)
RECENT_USAGE_REST_POPULATION_AUTHORITY = WORKLOAD_WINDOWS_POPULATION_AUTHORITY
RECENT_USAGE_REST_MEMBERSHIP_AUTHORITY = (
    'trusted_team_boards.default_pitcher_ids_and_historical_appearance_team'
)
RECENT_USAGE_REST_COMPLETE = 'complete'
RECENT_USAGE_REST_PARTIAL = 'partial'
RECENT_USAGE_REST_UNKNOWN = 'unknown'
RECENT_USAGE_REST_UNAVAILABLE = 'unavailable'
RECENT_USAGE_REST_WINDOW_DAYS = {
    'yesterday': 1,
    'last_3_days': 3,
    'last_7_days': 7,
}
RECENT_USAGE_REST_MAX_WINDOW_DAYS = 7
RECENT_USAGE_REST_BACK_TO_BACK_WINDOW_DAYS = 5
RECENT_USAGE_REST_THREE_IN_FOUR_DAYS = 4
RECENT_USAGE_REST_THREE_IN_FOUR_MIN_DAYS = 3
RECENT_USAGE_REST_FOUR_IN_SIX_DAYS = 6
RECENT_USAGE_REST_FOUR_IN_SIX_MIN_DAYS = 4
RECENT_USAGE_REST_MULTI_INNING_MIN_OUTS = 4
RECENT_USAGE_REST_HIGH_PITCH_MIN_PITCHES = 25

RECENT_USAGE_REST_REASON_COVERAGE_MISSING = 'slate_coverage_missing'
RECENT_USAGE_REST_REASON_COVERAGE_INCOMPLETE = 'slate_coverage_incomplete'
RECENT_USAGE_REST_REASON_START_RELIEF_UNKNOWN = 'start_relief_status_unknown'
RECENT_USAGE_REST_REASON_PITCHES_UNKNOWN = 'appearance_pitch_count_unknown'
RECENT_USAGE_REST_REASON_OUTS_UNKNOWN = 'appearance_outs_unknown'
RECENT_USAGE_REST_REASON_LAST_APPEARANCE_UNKNOWN = 'last_appearance_unknown'
RECENT_USAGE_REST_REASON_REFERENCE_DATE_INVALID = 'reference_date_invalid'
RECENT_USAGE_REST_REASON_SAME_DAY_ORDER_UNKNOWN = 'same_day_appearance_order_unknown'
# Which appearances the per-arm windows count. Bullpen workload is decided per
# appearance by services.game_shape (relief lines plus openers in an
# opener/bulk game); a conventional rotation start is physical workload only.
RECENT_USAGE_REST_APPEARANCE_POLICY = 'governed_game_shape_bullpen_workload_v1'
ACTIVE_BULLPEN_WORKLOAD_DISPLAY_CONTRACT = (
    'team_board_active_bullpen_workload_display_v1'
)

WORKLOAD_WINDOWS_COMPLETE = 'complete'
WORKLOAD_WINDOWS_WITHHELD = 'withheld'
WORKLOAD_WINDOWS_DATA_THROUGH_MISSING = 'data_through_missing'

# Every appearance on this board is owned by the team the pitcher REPRESENTED in
# that game (GameLog.appearance_team_id, Foundation 1), never by the pitcher's
# mutable current Pitcher.team_id. The current team is used only for the
# out-of-band diagnostic disclosure below and for the team's display name.
APPEARANCE_TEAM_RESOLVED = GameLog.APPEARANCE_TEAM_RESOLVED

# A game-level narrative is a starter-dependent public claim, so it additionally
# requires official final-game authority for this team side. Missing or
# non-final schedule authority suppresses the narrative; the appearance rows
# beneath it still render.
STARTER_AUTHORITY_OFFICIAL = 'official_completed_game_starter'

# Game-level context qualifier. Both bounds reuse the canonical game-shape
# constants: a credited start of two innings or fewer (6 outs) followed by
# five-plus relief innings (15 outs) qualifies as extended bullpen coverage.
EXTENDED_BULLPEN_COVERAGE_LABEL = 'Extended bullpen coverage'
EXTENDED_COVERAGE_STARTER_MAX_OUTS = game_shape.OPENER_MAX_OUTS
EXTENDED_COVERAGE_RELIEF_MIN_OUTS = game_shape.NORMAL_START_MIN_OUTS

# Shapes with exactly one credited starter and fully classified pitching
# lines. Any other shape (including unknown and no-credited-starter games)
# omits the game context block entirely.
CONTEXT_ELIGIBLE_GAME_SHAPES = (
    game_shape.SHAPE_NORMAL_START,
    game_shape.SHAPE_SHORT_START,
    game_shape.SHAPE_OPENER_BULK_GAME,
)

MONTH_NAMES = (
    None,
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
)


class TeamNotFoundError(LookupError):
    pass


def build_public_team_relief_work_payload(
    team_id, *, data_through=None, freshness=None,
):
    team_pitcher = (
        Pitcher.query
        .filter(Pitcher.team_id == team_id)
        .order_by(asc(Pitcher.id))
        .first()
    )
    if team_pitcher is None:
        raise TeamNotFoundError(team_id)

    freshness = (
        dict(freshness)
        if isinstance(freshness, dict)
        else board_freshness.board_freshness_block()
    )
    anchor = _parse_data_through(data_through or freshness.get('data_through'))
    payload = {
        'capability': CAPABILITY,
        'team': _team_payload(team_pitcher, team_id),
        'data_through': anchor.isoformat() if anchor else None,
        'freshness': freshness,
        'scope_sentence': _scope_sentence(team_pitcher),
        'relief_by_date': [],
    }

    if anchor is None:
        return payload

    start_date = anchor - timedelta(days=LOOKBACK_DAYS - 1)
    rows = _appearance_rows(team_id, start_date, anchor)
    carrier = _workload_windows_from_rows(rows, anchor)
    deployment = _deployment_profile_from_rows(rows, anchor)
    relief_rows = [
        (log, pitcher)
        for log, pitcher in rows
        if _start_relief_state(log) == RELIEF
    ]
    all_rows_by_date = {}
    for log, pitcher in rows:
        all_rows_by_date.setdefault(log.game_date, []).append((log, pitcher))

    payload['relief_by_date'] = _relief_by_date(relief_rows, all_rows_by_date, team_id)
    if not relief_rows:
        payload['absence_sentence'] = (
            f'No relief appearances in the {LOOKBACK_DAYS} days through '
            f'{_month_day(anchor)}.'
        )
    unattributed = _unattributed_appearance_count(team_id, start_date, anchor)
    if unattributed:
        payload['unattributed_appearance_count'] = unattributed
        payload['unattributed_sentence'] = (
            f'Official team attribution is unavailable for {unattributed} '
            f'{_appearance_word(unattributed)} by pitchers on this roster in the '
            f'{LOOKBACK_DAYS} days through {_month_day(anchor)}; those '
            f'{_appearance_word(unattributed)} are not counted here.'
        )
    payload['windows'] = carrier['windows']
    payload['deployment_profile'] = deployment
    return payload


def author_workload_windows(team_id, *, data_through):
    """Author the exact governed 7/14-day public windows for one publication.

    The caller supplies the immutable publication's represented date. This is
    the same canonical calculation used by the public relief-work payload; it
    neither consults the current roster for membership nor reconstructs an old
    publication. A missing represented date freezes an explicit unavailable
    carrier rather than manufacturing zeroes.
    """
    anchor = _parse_data_through(data_through)
    if anchor is None:
        return {
            'contract': WORKLOAD_WINDOWS_CARRIER_CONTRACT,
            'status': WORKLOAD_WINDOWS_WITHHELD,
            'reason_code': WORKLOAD_WINDOWS_DATA_THROUGH_MISSING,
            'data_through': None,
            'windows': {},
        }

    start_date = anchor - timedelta(days=LOOKBACK_DAYS - 1)
    rows = _appearance_rows(team_id, start_date, anchor)
    return _workload_windows_from_rows(rows, anchor)


def author_public_team_relief_authority(
    team_id,
    *,
    data_through,
    reference_date=None,
    active_pitchers=None,
    coverage_by_date=None,
    include_publication_rows=False,
):
    """Author workload windows and deployment from one bounded row query."""
    anchor = _parse_data_through(data_through)
    if anchor is None:
        return {
            'workload_windows': author_workload_windows(
                team_id, data_through=None
            ),
            'deployment_profile': author_deployment_profile(
                team_id, data_through=None
            ),
            'recent_usage_rest': _unavailable_recent_usage_rest_carrier(
                reference_date=reference_date,
                reason_code='data_through_missing',
            ),
        }
    active_ids = {
        pitcher_id
        for pitcher_id in dict(active_pitchers or {})
        if type(pitcher_id) is int and pitcher_id > 0
    }
    start_date = anchor - timedelta(days=LOOKBACK_DAYS - 1)
    rows = _appearance_rows(
        team_id,
        start_date,
        anchor,
        pitcher_ids=active_ids,
    )
    team_rows = [
        (log, pitcher)
        for log, pitcher in rows
        if log.appearance_team_id == team_id
    ]
    result = {
        'workload_windows': _workload_windows_from_rows(
            team_rows, anchor, coverage_by_date=coverage_by_date,
            active_pitcher_ids=active_ids,
        ),
        'deployment_profile': _deployment_profile_from_rows(team_rows, anchor),
        'recent_usage_rest': build_recent_usage_rest_carrier(
            rows,
            data_through=anchor,
            reference_date=reference_date,
            active_pitchers=active_pitchers,
            coverage_by_date=coverage_by_date,
            team_game_logs=_start_team_game_logs(rows, anchor=anchor),
        ),
    }
    if include_publication_rows:
        # Ephemeral ORM rows for the publication assembler, never serialized.
        result['_publication_team_rows'] = team_rows
    return result


def build_recent_usage_rest_coverage(data_through, *, anchor_coverage=None):
    """Resolve seven league-day coverage decisions once for one publication.

    Coverage is team-independent, so the trusted publication builder calls this
    once and shares the immutable result with all team carriers.  The already
    admitted anchor-day coverage may be supplied to avoid recomputing it.
    """
    anchor = _parse_data_through(data_through)
    if anchor is None:
        return {}
    coverage = {}
    for offset in range(RECENT_USAGE_REST_MAX_WINDOW_DAYS):
        day = anchor - timedelta(days=offset)
        if (
            offset == 0
            and isinstance(anchor_coverage, dict)
            and anchor_coverage.get('slate_date') == day.isoformat()
        ):
            payload = dict(anchor_coverage)
        else:
            try:
                payload = slate_coverage.compute_slate_coverage(day)
            except Exception:
                payload = {
                    'slate_date': day.isoformat(),
                    'complete_enough_to_publish': False,
                    'coverage_known': False,
                    'reason_codes': ['slate_coverage_unavailable'],
                }
        coverage[day.isoformat()] = payload
    return coverage


def extend_team_workload_coverage(data_through, recent_coverage):
    """Reuse seven-day decisions and freeze the older league-day decisions."""
    anchor = _parse_data_through(data_through)
    if anchor is None:
        return dict(recent_coverage or {})
    return team_board_workload_coverage.extend_coverage(anchor, recent_coverage)


def build_recent_usage_rest_carrier(
    rows,
    *,
    data_through,
    reference_date,
    active_pitchers=None,
    coverage_by_date=None,
    team_game_logs=None,
):
    """Freeze named-arm workload observations from the full appearance row set.

    ``rows`` is the untruncated official appearance-team query also used by the
    existing public workload/deployment carriers.  No request-time state or
    five-date display chronology participates in this projection.

    Windows count governed bullpen workload only (see
    ``bullpen_workload_classes``). ``team_game_logs`` supplies every pitching
    line of the games in which a row is a credited start, so the start can be
    classified by its game's shape; when omitted, the rows themselves are the
    only game lines.
    """
    anchor = _parse_data_through(data_through)
    reference = _parse_data_through(reference_date)
    if anchor is None:
        return _unavailable_recent_usage_rest_carrier(
            reference_date=reference,
            reason_code='data_through_missing',
        )
    if reference is None or reference != anchor + timedelta(days=1):
        return _unavailable_recent_usage_rest_carrier(
            data_through=anchor,
            reference_date=reference,
            reason_code=RECENT_USAGE_REST_REASON_REFERENCE_DATE_INVALID,
        )

    active = {
        int(pitcher_id): dict(value or {})
        for pitcher_id, value in dict(active_pitchers or {}).items()
        if type(pitcher_id) is int and pitcher_id > 0
    }
    coverage = dict(coverage_by_date or {})
    classes = bullpen_workload_classes(
        [log for log, _pitcher in rows], team_game_logs=team_game_logs,
    )
    relief_rows = [
        (log, pitcher)
        for log, pitcher in rows
        if _bullpen_state(log, classes) == RELIEF
    ]
    seven_start = anchor - timedelta(days=RECENT_USAGE_REST_MAX_WINDOW_DAYS - 1)
    contributor_ids = {
        pitcher.id
        for log, pitcher in relief_rows
        if log.game_date is not None and log.game_date >= seven_start
    }
    relevant_ids = sorted(set(active) | contributor_ids)
    rows_by_pitcher = {}
    names = {}
    for log, pitcher in rows:
        rows_by_pitcher.setdefault(pitcher.id, []).append(log)
        names[pitcher.id] = pitcher.full_name

    active_pitchers = []
    off_active = []
    for pitcher_id in relevant_ids:
        active_source = active.get(pitcher_id) or {}
        item = _recent_usage_rest_pitcher(
            pitcher_id=pitcher_id,
            pitcher_name=active_source.get('name') or names.get(pitcher_id),
            rows=rows_by_pitcher.get(pitcher_id) or [],
            anchor=anchor,
            reference=reference,
            coverage=coverage,
            source_days_since=active_source.get('days_since_last_appearance'),
            roster_state='active' if pitcher_id in active else 'off_active_historical',
            classes=classes,
        )
        if pitcher_id in active:
            active_pitchers.append(item)
        else:
            off_active.append(item)

    all_items = active_pitchers + off_active
    carrier_status = (
        RECENT_USAGE_REST_COMPLETE
        if all(_pitcher_recent_usage_rest_complete(item) for item in all_items)
        else RECENT_USAGE_REST_PARTIAL
    )
    return {
        'contract': RECENT_USAGE_REST_CONTRACT,
        'status': carrier_status,
        'reason_code': (
            None if carrier_status == RECENT_USAGE_REST_COMPLETE
            else 'some_usage_rest_fields_incomplete'
        ),
        'data_through': anchor.isoformat(),
        'reference_date': reference.isoformat(),
        'window_policy': RECENT_USAGE_REST_REFERENCE_DATE_POLICY,
        'population_basis': RECENT_USAGE_REST_POPULATION_BASIS,
        'appearance_policy': RECENT_USAGE_REST_APPEARANCE_POLICY,
        'thresholds': {
            'multi_inning_minimum_outs': RECENT_USAGE_REST_MULTI_INNING_MIN_OUTS,
            'high_pitch_outing_minimum_pitches': RECENT_USAGE_REST_HIGH_PITCH_MIN_PITCHES,
            'three_in_four_minimum_distinct_days': RECENT_USAGE_REST_THREE_IN_FOUR_MIN_DAYS,
            'four_in_six_minimum_distinct_days': RECENT_USAGE_REST_FOUR_IN_SIX_MIN_DAYS,
        },
        'active_pitchers': active_pitchers,
        'off_active_historical_contributors': off_active,
    }


def _unavailable_recent_usage_rest_carrier(
    *, data_through=None, reference_date=None, reason_code,
):
    return {
        'contract': RECENT_USAGE_REST_CONTRACT,
        'status': RECENT_USAGE_REST_UNAVAILABLE,
        'reason_code': reason_code,
        'data_through': _iso_date(data_through),
        'reference_date': _iso_date(reference_date),
        'window_policy': RECENT_USAGE_REST_REFERENCE_DATE_POLICY,
        'population_basis': RECENT_USAGE_REST_POPULATION_BASIS,
        'appearance_policy': RECENT_USAGE_REST_APPEARANCE_POLICY,
        'thresholds': {
            'multi_inning_minimum_outs': RECENT_USAGE_REST_MULTI_INNING_MIN_OUTS,
            'high_pitch_outing_minimum_pitches': RECENT_USAGE_REST_HIGH_PITCH_MIN_PITCHES,
            'three_in_four_minimum_distinct_days': RECENT_USAGE_REST_THREE_IN_FOUR_MIN_DAYS,
            'four_in_six_minimum_distinct_days': RECENT_USAGE_REST_FOUR_IN_SIX_MIN_DAYS,
        },
        'active_pitchers': [],
        'off_active_historical_contributors': [],
    }


def _recent_usage_rest_pitcher(
    *,
    pitcher_id,
    pitcher_name,
    rows,
    anchor,
    reference,
    coverage,
    source_days_since,
    roster_state,
    classes=None,
):
    windows = {
        key: _recent_usage_rest_window(
            rows,
            anchor=anchor,
            window_days=window_days,
            coverage=coverage,
            classes=classes,
        )
        for key, window_days in RECENT_USAGE_REST_WINDOW_DAYS.items()
    }
    relief_rows = [row for row in rows if _bullpen_state(row, classes) == RELIEF]
    relief_dates = {
        row.game_date for row in relief_rows if row.game_date is not None
    }

    days_since = _days_since_last_appearance_fact(
        relief_rows,
        anchor=anchor,
        reference=reference,
        coverage=coverage,
        source_value=source_days_since,
    )
    pitched_yesterday = _pattern_fact(
        matched=anchor in relief_dates,
        window_state=_classified_window_state(rows, coverage, anchor, anchor, classes),
    )

    back_to_back_start = reference - timedelta(
        days=RECENT_USAGE_REST_BACK_TO_BACK_WINDOW_DAYS - 1
    )
    back_to_back_dates = {
        day for day in relief_dates if back_to_back_start <= day <= anchor
    }
    observed_back_to_back = any(
        day - timedelta(days=1) in back_to_back_dates
        for day in back_to_back_dates
    )
    back_to_back = _pattern_fact(
        matched=observed_back_to_back,
        window_state=_classified_window_state(
            rows, coverage, back_to_back_start, anchor, classes,
        ),
    )

    three_start = anchor - timedelta(days=RECENT_USAGE_REST_THREE_IN_FOUR_DAYS - 1)
    three_dates = {day for day in relief_dates if three_start <= day <= anchor}
    three_in_four = _pattern_fact(
        matched=(
            anchor in three_dates
            and len(three_dates) >= RECENT_USAGE_REST_THREE_IN_FOUR_MIN_DAYS
        ),
        window_state=_classified_window_state(
            rows, coverage, three_start, anchor, classes,
        ),
    )

    four_start = anchor - timedelta(days=RECENT_USAGE_REST_FOUR_IN_SIX_DAYS - 1)
    four_dates = {day for day in relief_dates if four_start <= day <= anchor}
    four_in_six = _pattern_fact(
        matched=(
            anchor in four_dates
            and len(four_dates) >= RECENT_USAGE_REST_FOUR_IN_SIX_MIN_DAYS
        ),
        window_state=_classified_window_state(
            rows, coverage, four_start, anchor, classes,
        ),
    )

    seven_start = anchor - timedelta(days=RECENT_USAGE_REST_MAX_WINDOW_DAYS - 1)
    recent_rows = [
        row for row in relief_rows
        if row.game_date is not None and seven_start <= row.game_date <= anchor
    ]
    multi_inning = _threshold_pattern_fact(
        recent_rows,
        field_name='innings_pitched_outs',
        threshold=RECENT_USAGE_REST_MULTI_INNING_MIN_OUTS,
        window_state=_classified_window_state(
            rows, coverage, seven_start, anchor, classes,
        ),
        missing_reason=RECENT_USAGE_REST_REASON_OUTS_UNKNOWN,
    )
    high_pitch = _threshold_pattern_fact(
        recent_rows,
        field_name='pitches_thrown',
        threshold=RECENT_USAGE_REST_HIGH_PITCH_MIN_PITCHES,
        window_state=_classified_window_state(
            rows, coverage, seven_start, anchor, classes,
        ),
        missing_reason=RECENT_USAGE_REST_REASON_PITCHES_UNKNOWN,
    )

    last_bullpen_appearance = _last_bullpen_appearance_fact(
        rows,
        anchor=anchor,
        coverage=coverage,
        classes=classes,
    )

    return {
        'pitcher_id': pitcher_id,
        'pitcher_name': pitcher_name,
        'roster_state': roster_state,
        'windows': windows,
        'days_since_last_appearance': days_since,
        'pitched_yesterday': pitched_yesterday,
        'back_to_back': back_to_back,
        'three_in_four': three_in_four,
        'four_in_six': four_in_six,
        'recent_multi_inning': multi_inning,
        'high_pitch_outing': high_pitch,
        'last_bullpen_appearance': last_bullpen_appearance,
    }


def _recent_usage_rest_window(rows, *, anchor, window_days, coverage, classes=None):
    start = anchor - timedelta(days=window_days - 1)
    window_rows = [
        row for row in rows
        if row.game_date is not None and start <= row.game_date <= anchor
    ]
    relief_rows = [row for row in window_rows if _bullpen_state(row, classes) == RELIEF]
    start_relief_unknown = any(
        _bullpen_state(row, classes) not in (START, RELIEF) for row in window_rows
    )
    state, reasons = _coverage_state(coverage, start, anchor)
    if state != RECENT_USAGE_REST_COMPLETE:
        appearances = _fact(None, state, reasons)
        pitches = _fact(None, state, reasons)
        outs = _fact(None, state, reasons)
    elif start_relief_unknown:
        appearances = _fact(
            None, RECENT_USAGE_REST_UNKNOWN,
            [RECENT_USAGE_REST_REASON_START_RELIEF_UNKNOWN],
        )
        pitches = _fact(
            None, RECENT_USAGE_REST_UNKNOWN,
            [RECENT_USAGE_REST_REASON_START_RELIEF_UNKNOWN],
        )
        outs = _fact(
            None, RECENT_USAGE_REST_UNKNOWN,
            [RECENT_USAGE_REST_REASON_START_RELIEF_UNKNOWN],
        )
    else:
        appearances = _fact(
            len(relief_rows), RECENT_USAGE_REST_COMPLETE, [],
        )
        pitches = _sum_fact(
            relief_rows,
            'pitches_thrown',
            RECENT_USAGE_REST_REASON_PITCHES_UNKNOWN,
        )
        outs = _sum_fact(
            relief_rows,
            'innings_pitched_outs',
            RECENT_USAGE_REST_REASON_OUTS_UNKNOWN,
        )
    return {
        'window_days': window_days,
        'start_date': start.isoformat(),
        'through_date': anchor.isoformat(),
        'appearances': appearances,
        'pitches': pitches,
        'outs': outs,
    }


def _days_since_last_appearance_fact(
    relief_rows, *, anchor, reference, coverage, source_value,
):
    if type(source_value) is int and source_value >= 0:
        return _fact(source_value, RECENT_USAGE_REST_COMPLETE, [])
    dated = [
        row for row in relief_rows
        if row.game_date is not None and row.game_date <= anchor
    ]
    if not dated:
        state, reasons = _coverage_state(
            coverage,
            anchor - timedelta(days=RECENT_USAGE_REST_MAX_WINDOW_DAYS - 1),
            anchor,
        )
        if state == RECENT_USAGE_REST_COMPLETE:
            return _fact(
                None,
                RECENT_USAGE_REST_UNKNOWN,
                [RECENT_USAGE_REST_REASON_LAST_APPEARANCE_UNKNOWN],
            )
        return _fact(None, state, reasons)
    latest = max(row.game_date for row in dated)
    state, reasons = _coverage_state(coverage, max(latest, anchor - timedelta(days=6)), anchor)
    if state != RECENT_USAGE_REST_COMPLETE:
        return _fact(None, state, reasons)
    return _fact(
        (reference - latest).days,
        RECENT_USAGE_REST_COMPLETE,
        [],
        last_appearance_date=latest.isoformat(),
    )


def _threshold_pattern_fact(
    rows, *, field_name, threshold, window_state, missing_reason,
):
    matching = [
        row for row in rows
        if getattr(row, field_name, None) is not None
        and getattr(row, field_name) >= threshold
    ]
    if matching:
        most_recent = max(row.game_date for row in matching)
        return _fact(
            True,
            RECENT_USAGE_REST_COMPLETE,
            [],
            most_recent_date=most_recent.isoformat(),
            threshold=threshold,
        )
    state, reasons = window_state
    if state != RECENT_USAGE_REST_COMPLETE:
        return _fact(None, state, reasons, threshold=threshold)
    if any(getattr(row, field_name, None) is None for row in rows):
        return _fact(
            None,
            RECENT_USAGE_REST_UNKNOWN,
            [missing_reason],
            threshold=threshold,
        )
    return _fact(False, RECENT_USAGE_REST_COMPLETE, [], threshold=threshold)


def _pattern_fact(*, matched, window_state):
    state, reasons = window_state
    if state != RECENT_USAGE_REST_COMPLETE:
        return _fact(None, state, reasons)
    return _fact(bool(matched), RECENT_USAGE_REST_COMPLETE, [])


def _coverage_state(coverage, start, end):
    payloads = []
    current = start
    while current <= end:
        payload = coverage.get(current.isoformat())
        if not isinstance(payload, dict):
            return (
                RECENT_USAGE_REST_UNAVAILABLE,
                [RECENT_USAGE_REST_REASON_COVERAGE_MISSING],
            )
        payloads.append(payload)
        current += timedelta(days=1)
    incomplete = [
        payload for payload in payloads
        if payload.get('complete_enough_to_publish') is not True
    ]
    if incomplete:
        reasons = [RECENT_USAGE_REST_REASON_COVERAGE_INCOMPLETE]
        for payload in incomplete:
            reasons.extend(payload.get('reason_codes') or [])
        return RECENT_USAGE_REST_PARTIAL, _dedupe(reasons)
    return RECENT_USAGE_REST_COMPLETE, []


def _classified_window_state(rows, coverage, start, end, classes=None):
    state, reasons = _coverage_state(coverage, start, end)
    if state != RECENT_USAGE_REST_COMPLETE:
        return state, reasons
    if any(
        row.game_date is not None
        and start <= row.game_date <= end
        and _bullpen_state(row, classes) not in (START, RELIEF)
        for row in rows
    ):
        return (
            RECENT_USAGE_REST_UNKNOWN,
            [RECENT_USAGE_REST_REASON_START_RELIEF_UNKNOWN],
        )
    return state, reasons


def _last_bullpen_appearance_fact(rows, *, anchor, coverage, classes):
    """Pitches in the most recent single bullpen-workload appearance.

    Bounded to the governed seven-day window. A later or same-day appearance
    whose bullpen status is unknown, incomplete slate coverage after the
    outing, or two qualifying outings on one date (stored lines carry no
    in-day order) withhold the value instead of guessing.
    """
    start = anchor - timedelta(days=RECENT_USAGE_REST_MAX_WINDOW_DAYS - 1)
    window_rows = [
        row for row in rows
        if row.game_date is not None and start <= row.game_date <= anchor
    ]
    included = [row for row in window_rows if _bullpen_state(row, classes) == RELIEF]
    if not included:
        state, reasons = _classified_window_state(
            rows, coverage, start, anchor, classes,
        )
        return _fact(None, state, reasons)
    latest = max(row.game_date for row in included)
    state, reasons = _coverage_state(coverage, latest, anchor)
    if state != RECENT_USAGE_REST_COMPLETE:
        return _fact(None, state, reasons)
    if any(
        row.game_date >= latest
        and _bullpen_state(row, classes) not in (START, RELIEF)
        for row in window_rows
    ):
        return _fact(
            None, RECENT_USAGE_REST_UNKNOWN,
            [RECENT_USAGE_REST_REASON_START_RELIEF_UNKNOWN],
        )
    same_day = [row for row in included if row.game_date == latest]
    if len(same_day) != 1:
        return _fact(
            None, RECENT_USAGE_REST_UNKNOWN,
            [RECENT_USAGE_REST_REASON_SAME_DAY_ORDER_UNKNOWN],
            game_date=latest.isoformat(),
        )
    row = same_day[0]
    pitches = getattr(row, 'pitches_thrown', None)
    if pitches is None:
        return _fact(
            None, RECENT_USAGE_REST_UNKNOWN,
            [RECENT_USAGE_REST_REASON_PITCHES_UNKNOWN],
            game_date=latest.isoformat(),
        )
    return _fact(
        int(pitches),
        RECENT_USAGE_REST_COMPLETE,
        [],
        game_date=latest.isoformat(),
        game_pk=getattr(row, 'mlb_game_pk', None),
        appearance_class=_bullpen_class(row, classes),
    )


def author_active_bullpen_workload_display(carrier, pitcher_ids):
    """Freeze the Active Bullpen 7d App / 7d P / Last P from one carrier.

    The values are the carrier's own governed bullpen-workload facts, never a
    second aggregation. A fact that is not complete is frozen as ``None`` so
    the board withholds it rather than showing a total-pitching number.
    """
    carrier = carrier if isinstance(carrier, dict) else {}
    usable = (
        carrier.get('contract') == RECENT_USAGE_REST_CONTRACT
        and carrier.get('appearance_policy') == RECENT_USAGE_REST_APPEARANCE_POLICY
        and carrier.get('status') != RECENT_USAGE_REST_UNAVAILABLE
    )
    items = {
        item.get('pitcher_id'): item
        for item in (carrier.get('active_pitchers') or [])
        if isinstance(item, dict)
    } if usable else {}
    display = {}
    for pitcher_id in pitcher_ids:
        item = items.get(pitcher_id) or {}
        window = (item.get('windows') or {}).get('last_7_days') or {}
        last = item.get('last_bullpen_appearance') or {}
        last_pitches = _complete_value(last)
        display[pitcher_id] = {
            'contract': ACTIVE_BULLPEN_WORKLOAD_DISPLAY_CONTRACT,
            'appearance_policy': RECENT_USAGE_REST_APPEARANCE_POLICY,
            'data_through': carrier.get('data_through'),
            'appearances_last_7': _complete_value(window.get('appearances')),
            'pitches_last_7_days': _complete_value(window.get('pitches')),
            'last_appearance': (
                {'game_date': last.get('game_date'), 'pitches': last_pitches}
                if last_pitches is not None else None
            ),
        }
    return display


def _complete_value(fact):
    if not isinstance(fact, dict) or fact.get('status') != RECENT_USAGE_REST_COMPLETE:
        return None
    value = fact.get('value')
    return value if type(value) is int and value >= 0 else None


def _sum_fact(rows, field_name, missing_reason):
    values = [getattr(row, field_name, None) for row in rows]
    if any(value is None for value in values):
        return _fact(None, RECENT_USAGE_REST_UNKNOWN, [missing_reason])
    return _fact(sum(values), RECENT_USAGE_REST_COMPLETE, [])


def _fact(value, status, reason_codes, **extra):
    payload = {
        'value': value,
        'status': status,
        'reason_codes': _dedupe(reason_codes),
    }
    payload.update(extra)
    return payload


def _pitcher_recent_usage_rest_complete(item):
    facts = [
        item.get('days_since_last_appearance'),
        item.get('pitched_yesterday'),
        item.get('back_to_back'),
        item.get('three_in_four'),
        item.get('four_in_six'),
        item.get('recent_multi_inning'),
        item.get('high_pitch_outing'),
    ]
    for window in (item.get('windows') or {}).values():
        facts.extend((window.get('appearances'), window.get('pitches'), window.get('outs')))
    return all(
        isinstance(fact, dict)
        and fact.get('status') == RECENT_USAGE_REST_COMPLETE
        for fact in facts
    )


def _dedupe(values):
    return list(dict.fromkeys(value for value in values if value))


def _iso_date(value):
    parsed = _parse_data_through(value)
    return parsed.isoformat() if parsed else None


def author_deployment_profile(team_id, *, data_through):
    """Author the exact public deployment profile for one publication.

    This is one bounded team/window query, never one query per pitcher.  It
    reuses the same official team-at-appearance relief rows as Recent Relief
    Work and does not infer bullpen job titles or managerial intent.
    """
    anchor = _parse_data_through(data_through)
    if anchor is None:
        return {
            'contract': DEPLOYMENT_PROFILE_CARRIER_CONTRACT,
            'status': DEPLOYMENT_PROFILE_WITHHELD,
            'reason_code': DEPLOYMENT_PROFILE_DATA_THROUGH_MISSING,
            'data_through': None,
            'window_days': DEPLOYMENT_PROFILE_WINDOW_DAYS,
            'profiles': [],
            'summary': None,
            'limitations': [],
        }

    start_date = anchor - timedelta(days=LOOKBACK_DAYS - 1)
    rows = _appearance_rows(team_id, start_date, anchor)
    return _deployment_profile_from_rows(rows, anchor)


def _deployment_profile_from_rows(rows, anchor):
    start = anchor - timedelta(days=DEPLOYMENT_PROFILE_WINDOW_DAYS - 1)
    relief_rows = [
        (log, pitcher)
        for log, pitcher in rows
        if log.game_date >= start and _start_relief_state(log) == RELIEF
    ]
    by_pitcher = {}
    for log, pitcher in relief_rows:
        entry = by_pitcher.setdefault(pitcher.id, {
            'pitcher_id': pitcher.id,
            'pitcher_mlb_id': pitcher.mlb_id,
            'pitcher_name': pitcher.full_name,
            'appearances_analyzed': 0,
            'saves': 0,
            'holds': 0,
            'games_finished': 0,
            'appearances_with_games_finished': 0,
            'multi_inning_appearances': 0,
            'appearances_with_outs': 0,
            'most_recent_multi_inning_date': None,
            'limitations': [],
        })
        entry['appearances_analyzed'] += 1
        entry['saves'] += int(bool(log.save))
        entry['holds'] += int(bool(log.hold))
        if log.games_finished is not None:
            entry['appearances_with_games_finished'] += 1
            entry['games_finished'] += int(log.games_finished == 1)
        outs = _known_outs(log)
        if outs is not None:
            entry['appearances_with_outs'] += 1
            if outs >= DEPLOYMENT_PROFILE_MULTI_INNING_MIN_OUTS:
                entry['multi_inning_appearances'] += 1
                represented = log.game_date.isoformat()
                if (
                    entry['most_recent_multi_inning_date'] is None
                    or represented > entry['most_recent_multi_inning_date']
                ):
                    entry['most_recent_multi_inning_date'] = represented

    profiles = []
    for profile in by_pitcher.values():
        limitations = []
        if profile['appearances_with_outs'] < profile['appearances_analyzed']:
            limitations.append(
                'Multi-inning counts include only appearances with recorded outs.'
            )
        if (
            profile['appearances_with_games_finished']
            < profile['appearances_analyzed']
        ):
            limitations.append(
                'Games-finished counts include only appearances with recorded finish authority.'
            )
        profile['limitations'] = limitations
        name = profile.get('pitcher_name') or 'This pitcher'
        profile['summary'] = (
            f'{name} recorded {profile["saves"]} {_plural(profile["saves"], "save")}, '
            f'{profile["holds"]} {_plural(profile["holds"], "hold")}, and worked '
            f'multiple innings in {profile["multi_inning_appearances"]} of '
            f'{profile["appearances_with_outs"]} relief '
            f'{_plural(profile["appearances_with_outs"], "appearance")} with recorded outs '
            f'during the {DEPLOYMENT_PROFILE_WINDOW_DAYS}-day window.'
        )
        profiles.append(profile)

    profiles.sort(key=lambda item: (
        -item['appearances_analyzed'],
        str(item.get('pitcher_name') or '').lower(),
        item['pitcher_id'],
    ))
    save_hold_pitchers = sum(
        1 for item in profiles if item['saves'] or item['holds']
    )
    multi_inning_pitchers = sum(
        1 for item in profiles if item['multi_inning_appearances']
    )
    summary = (
        f'Over the {DEPLOYMENT_PROFILE_WINDOW_DAYS} days through {_month_day(anchor)}, '
        f'{save_hold_pitchers} {_plural(save_hold_pitchers, "pitcher")} recorded a save or hold and '
        f'{multi_inning_pitchers} {_plural(multi_inning_pitchers, "pitcher")} worked multiple innings.'
    )
    return {
        'contract': DEPLOYMENT_PROFILE_CARRIER_CONTRACT,
        'status': DEPLOYMENT_PROFILE_COMPLETE,
        'reason_code': None,
        'data_through': anchor.isoformat(),
        'window_days': DEPLOYMENT_PROFILE_WINDOW_DAYS,
        'population_basis': DEPLOYMENT_PROFILE_POPULATION_BASIS,
        'profiles': profiles,
        'team_summary': {
            'represented_arm_count': len(profiles),
            'pitchers_with_save_or_hold': save_hold_pitchers,
            'pitchers_with_multi_inning_appearance': multi_inning_pitchers,
        },
        'summary': summary,
        'limitations': sorted({
            limitation
            for profile in profiles
            for limitation in profile.get('limitations') or []
        }),
    }


def _plural(count, singular):
    return singular if count == 1 else f'{singular}s'


def _workload_windows_from_rows(
    rows, anchor, *, coverage_by_date=None, active_pitcher_ids=None,
):
    return {
        'contract': WORKLOAD_WINDOWS_CARRIER_CONTRACT,
        'status': WORKLOAD_WINDOWS_COMPLETE,
        'reason_code': None,
        'data_through': anchor.isoformat(),
        'windows': {
            f'window_{window_days}': _window(rows, anchor, window_days)
            for window_days in WINDOW_DAYS
        },
        'overview': _team_workload_overview(
            rows, anchor, coverage_by_date or {}, active_pitcher_ids or set(),
        ),
    }


def _team_workload_overview(rows, anchor, coverage, active_pitcher_ids):
    """One frozen factual team projection; no roster membership filter."""
    windows = {}
    for days in WORKLOAD_OVERVIEW_WINDOW_DAYS:
        start = anchor - timedelta(days=days - 1)
        scoped = [(log, pitcher) for log, pitcher in rows if start <= log.game_date <= anchor]
        relief = [(log, pitcher) for log, pitcher in scoped if _start_relief_state(log) == RELIEF]
        state, reasons = _classified_window_state(
            [log for log, _ in scoped], coverage, start, anchor,
        )
        if any(
            (coverage.get((start + timedelta(days=offset)).isoformat()) or {})
            .get('coverage_known') is False
            for offset in range(days)
        ):
            state = RECENT_USAGE_REST_UNAVAILABLE
            reasons = _dedupe([*reasons, 'slate_coverage_unavailable'])
        if state == RECENT_USAGE_REST_COMPLETE:
            appearances = _fact(len(relief), state, [])
            pitches = _sum_fact(
                [log for log, _ in relief], 'pitches_thrown',
                RECENT_USAGE_REST_REASON_PITCHES_UNKNOWN,
            )
            outs = _sum_fact(
                [log for log, _ in relief], 'innings_pitched_outs',
                RECENT_USAGE_REST_REASON_OUTS_UNKNOWN,
            )
        else:
            appearances = _fact(None, state, reasons)
            pitches = _fact(None, state, reasons)
            outs = _fact(None, state, reasons)
        windows[f'window_{days}'] = {
            'start': start.isoformat(), 'through': anchor.isoformat(),
            'appearances': appearances, 'pitches': pitches, 'outs': outs,
        }

    seven = windows['window_7']
    if seven['pitches']['status'] != RECENT_USAGE_REST_COMPLETE:
        concentration = {
            'status': seven['pitches']['status'],
            'reason_codes': seven['pitches']['reason_codes'],
            'total_pitches': None, 'top_3_share': None,
            'pitcher_count': None, 'contributors': [],
            'top_contributor': None, 'top_3_contributors': [],
            'active_current_contribution': None,
            'off_active_contribution': None,
        }
    else:
        contributions = {}
        seven_start = anchor - timedelta(days=6)
        for log, pitcher in rows:
            if seven_start <= log.game_date <= anchor and _start_relief_state(log) == RELIEF:
                item = contributions.setdefault(pitcher.id, {
                    'pitcher_id': pitcher.id, 'name': pitcher.full_name,
                    'pitches': 0, 'appearances': 0, 'outs': 0,
                    'current_active': pitcher.id in active_pitcher_ids,
                })
                item['pitches'] += log.pitches_thrown
                item['appearances'] += 1
                if log.innings_pitched_outs is None:
                    item['outs'] = None
                elif item['outs'] is not None:
                    item['outs'] += log.innings_pitched_outs
        contributors = sorted(
            contributions.values(), key=lambda item: (-item['pitches'], item['pitcher_id']),
        )
        active_items = [item for item in contributors if item['current_active']]
        off_active_items = [item for item in contributors if not item['current_active']]

        def contribution(items):
            return {
                'pitches': sum(item['pitches'] for item in items),
                'appearances': sum(item['appearances'] for item in items),
                'outs': (
                    sum(item['outs'] for item in items)
                    if all(item['outs'] is not None for item in items) else None
                ),
            }

        active_contribution = contribution(active_items)
        off_active_contribution = contribution(off_active_items)
        total = seven['pitches']['value']
        concentration = {
            'status': RECENT_USAGE_REST_COMPLETE, 'reason_codes': [],
            'total_pitches': total,
            'top_3_share': (
                sum(item['pitches'] for item in contributors[:3]) / total
                if total else None
            ),
            'pitcher_count': len(contributors),
            'contributors': contributors,
            'top_contributor': contributors[0] if contributors else None,
            'top_3_contributors': contributors[:3],
            'active_current_contribution': active_contribution,
            'off_active_contribution': off_active_contribution,
        }
    return {
        'contract': WORKLOAD_OVERVIEW_CONTRACT,
        'data_through': anchor.isoformat(),
        'window_policy': WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY,
        'population_basis': WORKLOAD_WINDOWS_POPULATION_BASIS,
        'windows': windows, 'concentration_7_day': concentration,
        'trend_status': RECENT_USAGE_REST_UNAVAILABLE,
    }


def _appearance_rows(team_id, start_date, anchor, *, pitcher_ids=None):
    # Scoped by official game-side ownership, not by who is on the roster today.
    # This both keeps another club's game out of this board and keeps this
    # club's own game complete when a pitcher has since left the organization.
    team_scope = GameLog.appearance_team_id == team_id
    requested_pitcher_ids = sorted({
        pitcher_id
        for pitcher_id in (pitcher_ids or [])
        if type(pitcher_id) is int and pitcher_id > 0
    })
    appearance_scope = (
        or_(team_scope, GameLog.pitcher_id.in_(requested_pitcher_ids))
        if requested_pitcher_ids
        else team_scope
    )
    return (
        GameLog.query
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .add_entity(Pitcher)
        .filter(
            GameLog.appearance_team_status == APPEARANCE_TEAM_RESOLVED,
            appearance_scope,
            GameLog.game_date >= start_date,
            GameLog.game_date <= anchor,
        )
        .order_by(desc(GameLog.game_date), asc(Pitcher.full_name), asc(GameLog.id))
        .all()
    )


def _start_team_game_logs(rows, *, anchor):
    """Every stored line of the in-window games in which a row is a credited start.

    Only the seven-day per-arm windows and last outing use the classification,
    so older starts are not loaded.
    """
    start = anchor - timedelta(days=RECENT_USAGE_REST_MAX_WINDOW_DAYS - 1)
    game_pks = sorted({
        log.mlb_game_pk
        for log, _pitcher in rows
        if _start_relief_state(log) == START
        and log.mlb_game_pk is not None
        and log.game_date is not None
        and start <= log.game_date <= anchor
    })
    if not game_pks:
        return []
    return GameLog.query.filter(GameLog.mlb_game_pk.in_(game_pks)).all()


def bullpen_workload_classes(logs, *, team_game_logs=None):
    """Map ``(pitcher_id, mlb_game_pk)`` to its governed bullpen-workload class.

    Relief lines are classified on their own official flag. A credited start is
    classified by the shape of its team's game (services.game_shape), using the
    lines of that game grouped by official appearance team. A game with any
    line whose official side is not resolved cannot be grouped, so its start
    stays unknown.
    """
    logs = list(logs or [])
    pool = {}
    unresolved_games = set()
    for log in list(team_game_logs or []):
        if getattr(log, 'appearance_team_status', None) != APPEARANCE_TEAM_RESOLVED:
            unresolved_games.add(getattr(log, 'mlb_game_pk', None))
        pool.setdefault(_appearance_key(log), log)
    for log in logs:
        pool.setdefault(_appearance_key(log), log)
    games = {}
    for log in pool.values():
        games.setdefault(
            (getattr(log, 'mlb_game_pk', None), getattr(log, 'appearance_team_id', None)),
            [],
        ).append(log)
    classes = {}
    for log in logs:
        key = _appearance_key(log)
        if _start_relief_state(log) == START and key[1] in unresolved_games:
            classes[key] = game_shape.BULLPEN_WORKLOAD_UNKNOWN
            continue
        line = pool[key]
        team_logs = games.get((key[1], getattr(line, 'appearance_team_id', None)), [])
        classes[key] = game_shape.bullpen_workload_appearance_class(line, team_logs)
    return classes


def _appearance_key(log):
    return (getattr(log, 'pitcher_id', None), getattr(log, 'mlb_game_pk', None))


def _bullpen_class(log, classes):
    if classes is None:
        return None
    return classes.get(_appearance_key(log))


def _bullpen_state(log, classes):
    """RELIEF when the line is bullpen workload, START when it is a rotation
    start, anything else when unknown. ``classes=None`` keeps the raw official
    start/relief flag for the team-level reads that are not per-arm."""
    if classes is None:
        return _start_relief_state(log)
    value = _bullpen_class(log, classes)
    if value in game_shape.BULLPEN_WORKLOAD_INCLUDED:
        return RELIEF
    if value == game_shape.BULLPEN_WORKLOAD_ROTATION_START:
        return START
    return 'unknown'


def _start_relief_state(log):
    """Official per-game start signal, never a season pattern or row order."""
    try:
        return games_started_state(getattr(log, 'games_started', None))
    except Exception:
        # A malformed flag never counts as a start or a relief outing.
        return 'unknown'


def _parse_data_through(value):
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _team_payload(pitcher, team_id):
    return {
        'team_id': team_id,
        'team_name': pitcher.team_name,
        'team_abbreviation': pitcher.team_abbreviation,
    }


def _scope_sentence(pitcher):
    club = pitcher.team_abbreviation or pitcher.team_name or ''
    return f'Covers appearances made for {club} per official MLB game records.'


def _unattributed_appearance_count(team_id, start_date, anchor):
    """Out-of-band diagnostic only: never an attribution source.

    Counts in-window appearances by pitchers currently on this roster whose
    official game side is unresolved, so the board can disclose what it left
    out instead of silently under-reporting.
    """
    return (
        GameLog.query
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .filter(
            Pitcher.team_id == team_id,
            GameLog.game_date >= start_date,
            GameLog.game_date <= anchor,
            or_(
                GameLog.appearance_team_status.is_(None),
                GameLog.appearance_team_status != APPEARANCE_TEAM_RESOLVED,
            ),
        )
        .count()
    )


def _relief_by_date(relief_rows, all_rows_by_date, team_id):
    by_date = {}
    for log, pitcher in relief_rows:
        by_date.setdefault(log.game_date, []).append((log, pitcher))

    groups = []
    for game_date in sorted(by_date, reverse=True)[:RECENT_GAME_DATES_MAX]:
        entries = sorted(
            by_date[game_date],
            key=lambda item: (item[1].full_name or '', item[0].id or 0),
        )
        group = _date_group(game_date, entries)
        if not _group_totals_reconcile(group):
            groups.append(_unavailable_group(game_date))
            continue
        games = [
            block
            for block in _game_context_blocks(
                all_rows_by_date.get(game_date) or [], team_id
            )
            if _block_reconciles_with_appearances(block, group)
        ]
        if games:
            group['games'] = games
        groups.append(group)
    return groups


def _game_context_blocks(date_entries, team_id):
    by_game = {}
    for log, pitcher in date_entries:
        if log.mlb_game_pk is None:
            continue
        by_game.setdefault(log.mlb_game_pk, []).append((log, pitcher))

    final_game_numbers = _final_game_numbers(team_id, by_game.keys())
    blocks = []
    for game_pk in sorted(by_game):
        if game_pk not in final_game_numbers:
            # No official final-game authority for this team side: a
            # starter-dependent narrative cannot be published.
            continue
        block = _game_context_block(game_pk, by_game[game_pk])
        if block is not None:
            block['game_number'] = final_game_numbers[game_pk]
            blocks.append(block)
    blocks.sort(key=_game_sort_key)
    return blocks


def _game_sort_key(entry):
    """Deterministic official ordering: MLB game number, then game_pk.

    A game whose number is unknown sorts after numbered games rather than
    borrowing a position it cannot prove.
    """
    number = entry.get('game_number')
    return (0, number, entry['mlb_game_pk']) if isinstance(number, int) else (
        1, 0, entry['mlb_game_pk']
    )


def _final_game_numbers(team_id, game_pks):
    """Official final-game authority and MLB game number for this team side.

    Returns ``{game_pk: game_number_or_None}`` for the games this team side
    officially completed. ``game_number`` is MLB's own ``gameNumber`` carried by
    the schedule ledger, so a doubleheader's first and second game are told
    apart by official authority rather than by list order.
    """
    wanted = sorted({pk for pk in game_pks if pk is not None})
    if not wanted:
        return {}
    rows = (
        ScheduledGame.query
        .filter(
            ScheduledGame.team_id == team_id,
            ScheduledGame.game_pk.in_(wanted),
        )
        .all()
    )
    return {
        row.game_pk: row.game_number
        for row in rows
        if row.status_state == ScheduledGame.STATE_FINAL
    }


def _game_context_block(game_pk, entries):
    shape_payload = game_shape.classify_game_shape(
        [log for log, _pitcher in entries]
    )
    if shape_payload['shape'] not in CONTEXT_ELIGIBLE_GAME_SHAPES:
        return None

    starters = [
        (log, pitcher)
        for log, pitcher in entries
        if _start_relief_state(log) == START
    ]
    relief = [
        (log, pitcher)
        for log, pitcher in entries
        if _start_relief_state(log) == RELIEF
    ]
    if len(starters) != 1 or not relief:
        return None
    if len(starters) + len(relief) != len(entries):
        # An unclassified line means the official starter set is not provably
        # complete for this team side.
        return None

    starter_log, starter_pitcher = starters[0]
    starter_outs = _known_outs(starter_log)
    relief_outs_each = [_known_outs(log) for log, _pitcher in relief]
    if starter_outs is None or any(outs is None for outs in relief_outs_each):
        return None

    relief_outs = sum(relief_outs_each)
    total_outs = starter_outs + relief_outs
    relief_count = len(relief)
    total_pitchers = 1 + relief_count

    starter_pitches = starter_log.pitches_thrown
    relief_known_pitches = [
        log.pitches_thrown
        for log, _pitcher in relief
        if log.pitches_thrown is not None
    ]
    relief_pitches = (
        sum(relief_known_pitches)
        if len(relief_known_pitches) == relief_count
        else None
    )
    total_pitches = (
        starter_pitches + relief_pitches
        if starter_pitches is not None and relief_pitches is not None
        else None
    )

    label = None
    if (
        starter_outs <= EXTENDED_COVERAGE_STARTER_MAX_OUTS
        and relief_outs >= EXTENDED_COVERAGE_RELIEF_MIN_OUTS
    ):
        label = EXTENDED_BULLPEN_COVERAGE_LABEL

    assignment = None
    if label is not None:
        history_coverage = (
            pitcher_season_ledger_coverage.history_coverage_for_game_log(
                starter_log,
                starter_pitcher,
            )
        )
        assignment = starter_assignment_context.build_starter_assignment_context(
            starter_log,
            starter_pitcher,
            history_coverage=history_coverage,
        )

    if assignment is not None:
        # The assignment lead already names the starter and carries the
        # combined-workload meaning, so the follow-up uses a pronoun and
        # the total-workload prose is left to the total block below.
        sentences = [
            assignment['sentence'],
            _starter_followup_sentence(starter_outs, starter_pitches),
            _relief_context_sentence(relief_count, relief_outs, relief_pitches),
        ]
    else:
        sentences = [
            _starter_context_sentence(starter_pitcher, starter_outs, starter_pitches),
            _relief_context_sentence(relief_count, relief_outs, relief_pitches),
        ]
        if label is not None:
            sentences.append(
                _total_context_sentence(total_pitchers, total_outs, total_pitches)
            )

    block = {
        'mlb_game_pk': game_pk,
        'appearance_team_id': starter_log.appearance_team_id,
        'opponent': starter_log.opponent,
        'opponent_abbreviation': starter_log.opponent_abbreviation,
        'game_shape': shape_payload['shape'],
        'context_label': label,
        'starter_authority': STARTER_AUTHORITY_OFFICIAL,
        'reconciled': True,
        'starter': {
            'pitcher_id': starter_pitcher.id,
            'pitcher_mlb_id': starter_pitcher.mlb_id,
            'pitcher_full_name': starter_pitcher.full_name,
            'outs': starter_outs,
            'innings': _ip_text(starter_outs),
            'pitches': starter_pitches,
        },
        'relief': {
            'pitcher_count': relief_count,
            'outs': relief_outs,
            'innings': _ip_text(relief_outs),
            'pitches': relief_pitches,
            'pitcher_ids': sorted(pitcher.id for _log, pitcher in relief),
        },
        'total': {
            'pitcher_count': total_pitchers,
            'outs': total_outs,
            'innings': _ip_text(total_outs),
            'pitches': total_pitches,
        },
        'context_sentences': sentences,
    }
    if assignment is not None:
        block['starter_assignment'] = assignment
    return block


def _known_outs(log):
    outs = log.innings_pitched_outs
    if outs is None:
        return None
    try:
        parsed = int(outs)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _starter_context_sentence(pitcher, outs, pitches):
    sentence = (
        f'{pitcher.full_name} started and recorded {_out_count_text(outs)} '
        f'({_ip_text(outs)} IP)'
    )
    if pitches is not None:
        sentence = f'{sentence} on {_pitch_count_text(pitches)}'
    return f'{sentence}.'


def _starter_followup_sentence(outs, pitches):
    sentence = f'He recorded {_out_count_text(outs)} ({_ip_text(outs)} IP)'
    if pitches is not None:
        sentence = f'{sentence} on {_pitch_count_text(pitches)}'
    return f'{sentence}.'


def _relief_context_sentence(relief_count, outs, pitches):
    sentence = (
        f'{_sentence_start_reliever_count_text(relief_count)} covered the remaining '
        f'{_out_count_text(outs)} ({_ip_text(outs)} IP)'
    )
    if pitches is not None:
        sentence = f'{sentence} on {_pitch_count_text(pitches)}'
    return f'{sentence}.'


def _total_context_sentence(pitcher_count, outs, pitches):
    sentence = (
        f'{_pitcher_count_text(pitcher_count)} combined for '
        f'{_out_count_text(outs)} ({_ip_text(outs)} IP)'
    )
    if pitches is not None:
        sentence = f'{sentence} and {_pitch_count_text(pitches)}'
    return f'{sentence}.'


def _out_count_text(count):
    return f'{count} {"out" if count == 1 else "outs"}'


def _reliever_count_text(count):
    return f'{count} {"reliever" if count == 1 else "relievers"}'


def _sentence_start_reliever_count_text(count):
    words = {
        1: 'One',
        2: 'Two',
        3: 'Three',
        4: 'Four',
        5: 'Five',
        6: 'Six',
        7: 'Seven',
        8: 'Eight',
        9: 'Nine',
    }
    label = words.get(count, str(count))
    return f'{label} {"reliever" if count == 1 else "relievers"}'


def _date_group(game_date, entries):
    relief_count = len(entries)
    outs_total = sum((log.innings_pitched_outs or 0) for log, pitcher in entries)
    known_pitches = [
        log.pitches_thrown
        for log, pitcher in entries
        if log.pitches_thrown is not None
    ]
    pitches_total = (
        sum(known_pitches)
        if len(known_pitches) == relief_count
        else None
    )
    game_pks = sorted({
        log.mlb_game_pk for log, pitcher in entries if log.mlb_game_pk is not None
    })
    sentence = (
        f'{_month_day(game_date)} \u2014 {_relief_count_text(relief_count)}'
    )
    if len(game_pks) > 1:
        # A date total that spans more than one game says so, so no game-level
        # narrative beneath it can be mistaken for covering these totals.
        sentence = f'{sentence} across {_game_count_text(len(game_pks))}'
    sentence = f'{sentence}, {_ip_text(outs_total)} IP'
    if pitches_total is not None:
        sentence = f'{sentence}, {_pitch_count_text(pitches_total)}'
    return {
        'game_date': game_date.isoformat(),
        'relief_appearances': relief_count,
        'outs_total': outs_total,
        'pitches_total': pitches_total,
        'appearances_with_pitches': len(known_pitches),
        'game_pks': game_pks,
        'game_count': len(game_pks),
        'sentence': f'{sentence}.',
        'appearances': [
            _appearance_line(log, pitcher)
            for log, pitcher in entries
        ],
    }


def _group_totals_reconcile(group):
    """Every published summary number must equal the rows shown beneath it."""
    appearances = group.get('appearances') or []
    if group.get('relief_appearances') != len(appearances):
        return False
    outs = [row.get('innings_pitched_outs') for row in appearances]
    if any(value is None for value in outs):
        return False
    if group.get('outs_total') != sum(outs):
        return False
    known_pitches = [
        row.get('pitches_thrown')
        for row in appearances
        if row.get('pitches_thrown') is not None
    ]
    if group.get('appearances_with_pitches') != len(known_pitches):
        return False
    expected_pitches = (
        sum(known_pitches) if len(known_pitches) == len(appearances) else None
    )
    return group.get('pitches_total') == expected_pitches


def _block_reconciles_with_appearances(block, group):
    """A game narrative may only describe rows visible beneath it.

    Its relief pitcher set must equal that game's shown appearance rows, and
    its relief totals must equal those same rows.
    """
    game_pk = block.get('mlb_game_pk')
    if game_pk is None or game_pk not in (group.get('game_pks') or []):
        return False

    shown = [
        row for row in (group.get('appearances') or [])
        if row.get('mlb_game_pk') == game_pk
    ]
    claimed_ids = list((block.get('relief') or {}).get('pitcher_ids') or [])
    if sorted(row.get('pitcher_id') for row in shown) != sorted(claimed_ids):
        return False
    if (block.get('relief') or {}).get('pitcher_count') != len(shown):
        return False
    if block.get('starter', {}).get('pitcher_id') in claimed_ids:
        return False

    outs = [row.get('innings_pitched_outs') for row in shown]
    if any(value is None for value in outs):
        return False
    if (block.get('relief') or {}).get('outs') != sum(outs):
        return False
    known_pitches = [
        row.get('pitches_thrown')
        for row in shown
        if row.get('pitches_thrown') is not None
    ]
    expected_pitches = (
        sum(known_pitches) if len(known_pitches) == len(shown) else None
    )
    return (block.get('relief') or {}).get('pitches') == expected_pitches


def _unavailable_group(game_date):
    """Honest unavailable state \u2014 never a partial or substituted baseball claim."""
    return {
        'game_date': game_date.isoformat(),
        'unavailable': True,
        'sentence': (
            f'{_month_day(game_date)} \u2014 relief work is unavailable because '
            f'the summary and the appearance records do not reconcile.'
        ),
        'appearances': [],
    }


def _appearance_line(log, pitcher):
    return {
        'pitcher_id': pitcher.id,
        'pitcher_mlb_id': pitcher.mlb_id,
        'pitcher_full_name': pitcher.full_name,
        'roster_status_sentence': _roster_status_sentence(pitcher),
        'mlb_game_pk': log.mlb_game_pk,
        'appearance_team_id': log.appearance_team_id,
        'game_date': log.game_date.isoformat(),
        'opponent': log.opponent,
        'opponent_abbreviation': log.opponent_abbreviation,
        'innings_pitched': log.innings_pitched,
        'innings_pitched_outs': log.innings_pitched_outs,
        'pitches_thrown': log.pitches_thrown,
        'strikeouts': log.strikeouts or 0,
        'walks': log.walks or 0,
        'hits_allowed': log.hits_allowed or 0,
        'runs_allowed': log.runs_allowed or 0,
        'save': bool(log.save),
        'hold': bool(log.hold),
        'blown_save': bool(log.blown_save),
        'win': bool(log.win),
        'loss': bool(log.loss),
        'save_situation': bool(log.save_situation),
        'sentence': _appearance_sentence(log, pitcher),
    }


def _roster_status_sentence(pitcher):
    status = pitcher.roster_status
    if pitcher.active:
        return 'On the active roster per MLB roster data.'
    if status:
        return f'Roster status: {status} per MLB roster data.'
    return 'Roster status unavailable.'


def _appearance_sentence(log, pitcher):
    parts = [
        f'{pitcher.full_name} \u2014 {_ip_text(log.innings_pitched_outs)} IP',
    ]
    if log.pitches_thrown is not None:
        parts.append(f'{_pitch_count_text(log.pitches_thrown)}')
    parts.extend([
        f'{log.strikeouts or 0} K',
        f'{log.walks or 0} BB',
    ])
    hits = log.hits_allowed or 0
    runs = log.runs_allowed or 0
    if hits or runs:
        parts.extend([
            f'{hits} H',
            f'{runs} R',
        ])
    return f'{", ".join(parts)}.'


def _window(rows, anchor, window_days):
    start_date = anchor - timedelta(days=window_days - 1)
    window_rows = [
        (log, pitcher)
        for log, pitcher in rows
        if log.game_date >= start_date
    ]
    relief_rows = [
        (log, pitcher)
        for log, pitcher in window_rows
        if _start_relief_state(log) == RELIEF
    ]
    relief_count = len(relief_rows)
    pitcher_count = len({pitcher.id for log, pitcher in relief_rows})
    unknown_count = sum(
        1 for log, pitcher in window_rows
        if _start_relief_state(log) not in (START, RELIEF)
    )
    known_pitches = [
        log.pitches_thrown
        for log, pitcher in relief_rows
        if log.pitches_thrown is not None
    ]
    payload = {
        'through': anchor.isoformat(),
        'relief_appearances': relief_count,
        'pitchers_in_relief': pitcher_count,
        'pitches_total': _window_pitches_total(relief_count, known_pitches),
        'appearances_with_pitches': len(known_pitches),
        'start_relief_unknown': unknown_count,
        'sentence': (
            f'{_relief_count_text(relief_count)} in the {window_days} days '
            f'through {_month_day(anchor)}.'
        ),
        'pitchers_sentence': (
            f'{_pitcher_count_text(pitcher_count)} appeared in relief in the '
            f'{window_days} days through {_month_day(anchor)}.'
        ),
        'pitches_sentence': _pitches_sentence(relief_count, known_pitches),
    }
    if unknown_count:
        total = relief_count + unknown_count
        payload['start_relief_unknown_sentence'] = (
            f'Start/relief status unavailable for {unknown_count} of {total} '
            f'{_appearance_word(total)} in the {window_days} days through '
            f'{_month_day(anchor)}; relief totals cover the other {relief_count}.'
        )
    return payload


def _window_pitches_total(relief_count, known_pitches):
    if relief_count == 0:
        return 0
    if len(known_pitches) == relief_count:
        return sum(known_pitches)
    return None


def _pitches_sentence(relief_count, known_pitches):
    known_count = len(known_pitches)
    pitches_total = sum(known_pitches)
    if known_count == relief_count:
        return (
            f'{_pitch_count_text(pitches_total)} across those '
            f'{_relief_count_text(relief_count)}.'
        )
    missing_count = relief_count - known_count
    return (
        f'Pitch count unavailable for {missing_count} of {relief_count} '
        f'{_relief_appearance_word(relief_count)}; '
        f'{_pitch_count_text(pitches_total)} across the other {known_count}.'
    )


def _month_day(value):
    return f'{MONTH_NAMES[value.month]} {value.day}'


def _ip_text(innings_pitched_outs):
    outs = innings_pitched_outs or 0
    return f'{outs // 3}.{outs % 3}'


def _relief_count_text(count):
    return f'{count} {_relief_appearance_word(count)}'


def _relief_appearance_word(count):
    return 'relief appearance' if count == 1 else 'relief appearances'


def _game_count_text(count):
    return f'{count} {"game" if count == 1 else "games"}'


def _appearance_word(count):
    return 'appearance' if count == 1 else 'appearances'


def _pitcher_count_text(count):
    return f'{count} {"pitcher" if count == 1 else "pitchers"}'


def _pitch_count_text(count):
    pitch_word = 'pitch' if count == 1 else 'pitches'
    return f'{count} {pitch_word}'
