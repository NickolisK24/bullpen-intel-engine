from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import desc

from models.availability_backtest_result import AvailabilityBacktestResult
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability import (
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
    classify_availability,
)
from services.fatigue import calculate_fatigue
from services.pitcher_role import ROLE_WINDOW_DAYS
from services.role_authority import (
    ROLE_AMBIGUOUS,
    ROLE_RELIEVER,
    classify_role,
)
from utils.db import db
from utils.time import utc_now_naive


METHOD_VERSION = 'availability_next_day_reliever_v1'
CADENCE = 'after_successful_daily_sync_or_manual_refresh'
DEFAULT_SEASONS = (2026, 2025)
PRIMARY_SEASON = 2026
TIER_ORDER = (
    STATUS_AVAILABLE,
    STATUS_MONITOR,
    STATUS_LIMITED,
    STATUS_AVOID,
    STATUS_UNAVAILABLE,
)


@dataclass
class SeasonBacktest:
    season: int
    window_label: str
    window_start: date | None
    window_end: date | None
    data_through: date | None
    tier_counts: dict[str, dict[str, int]]
    no_appearance_days: int
    no_appearance_tier_flips: int

    @property
    def no_appearance_tier_flip_rate(self) -> float:
        if self.no_appearance_days <= 0:
            return 0.0
        return self.no_appearance_tier_flips / self.no_appearance_days


def refresh_availability_backtest(seasons=DEFAULT_SEASONS):
    computed_at = utc_now_naive()
    season_results = compute_availability_backtest(seasons=seasons)
    rows = _rows_from_results(season_results, computed_at=computed_at)
    for row in rows:
        db.session.add(row)
    db.session.commit()
    return latest_backtest_payload()


def compute_availability_backtest(seasons=DEFAULT_SEASONS):
    seasons = tuple(int(season) for season in seasons)
    if not seasons:
        return []

    pitchers = Pitcher.query.order_by(Pitcher.id).all()
    logs = (
        GameLog.query
        .filter(GameLog.game_type == 'R')
        .order_by(GameLog.pitcher_id, GameLog.game_date, GameLog.id)
        .all()
    )
    logs_by_pitcher = _group_logs_by_pitcher(logs)

    results = []
    for season in seasons:
        season_logs = [
            log for log in logs
            if getattr(log, 'game_date', None) is not None
            and log.game_date.year == season
        ]
        if not season_logs:
            results.append(_empty_season_result(season))
            continue

        window_start = min(log.game_date for log in season_logs)
        data_through = max(log.game_date for log in season_logs)
        results.append(_compute_season(
            season,
            pitchers,
            logs_by_pitcher,
            window_start=window_start,
            data_through=data_through,
        ))
    return results


def latest_backtest_payload():
    latest_computed_at = (
        db.session.query(db.func.max(AvailabilityBacktestResult.computed_at))
        .filter(AvailabilityBacktestResult.method_version == METHOD_VERSION)
        .scalar()
    )
    if latest_computed_at is None:
        return _empty_payload()

    rows = (
        AvailabilityBacktestResult.query
        .filter(
            AvailabilityBacktestResult.method_version == METHOD_VERSION,
            AvailabilityBacktestResult.computed_at == latest_computed_at,
        )
        .order_by(
            desc(AvailabilityBacktestResult.season),
            AvailabilityBacktestResult.tier_order,
        )
        .all()
    )
    if not rows:
        return _empty_payload()

    return _payload_from_rows(rows)


def _group_logs_by_pitcher(logs):
    grouped = defaultdict(list)
    for log in logs:
        grouped[log.pitcher_id].append(log)
    return grouped


def _empty_season_result(season):
    return SeasonBacktest(
        season=season,
        window_label=_window_label(season),
        window_start=None,
        window_end=None,
        data_through=None,
        tier_counts=_empty_tier_counts(),
        no_appearance_days=0,
        no_appearance_tier_flips=0,
    )


def _compute_season(season, pitchers, logs_by_pitcher, *, window_start, data_through):
    tier_counts = _empty_tier_counts()
    no_appearance_days = 0
    no_appearance_tier_flips = 0

    # Each sample is the state carried into a calendar date: workload through
    # yesterday is reconstructed from game logs, Role Authority confirms the
    # pitcher belongs to a bullpen population, and the outcome is whether he
    # appears in relief on that date. Starts are excluded from the sample.
    for pitcher in pitchers:
        pitcher_logs = logs_by_pitcher.get(pitcher.id, [])
        if not pitcher_logs:
            continue
        dates = [log.game_date for log in pitcher_logs]
        prior_status = None
        prior_reference_date = None

        reference_date = window_start + timedelta(days=1)
        while reference_date <= data_through:
            day_before = reference_date - timedelta(days=1)
            prior_idx = bisect_right(dates, day_before)
            if prior_idx == 0:
                reference_date += timedelta(days=1)
                continue

            next_day_logs = _logs_on_date(pitcher_logs, dates, reference_date)
            if any(_games_started(log) == 1 for log in next_day_logs):
                prior_status = None
                prior_reference_date = None
                reference_date += timedelta(days=1)
                continue

            recent_logs = _logs_between(
                pitcher_logs,
                dates,
                reference_date - timedelta(days=ROLE_WINDOW_DAYS),
                day_before,
            )
            if not recent_logs:
                prior_status = None
                prior_reference_date = None
                reference_date += timedelta(days=1)
                continue

            role = classify_role(pitcher, list(reversed(recent_logs)), reference_date=reference_date)
            if role.get('role') not in (ROLE_RELIEVER, ROLE_AMBIGUOUS) or not role.get('eligible'):
                prior_status = None
                prior_reference_date = None
                reference_date += timedelta(days=1)
                continue

            fatigue_logs = _logs_between(
                pitcher_logs,
                dates,
                reference_date - timedelta(days=14),
                day_before,
            )
            if not fatigue_logs:
                prior_status = None
                prior_reference_date = None
                reference_date += timedelta(days=1)
                continue

            fatigue_logs_desc = list(reversed(fatigue_logs))
            score = calculate_fatigue(
                pitcher,
                fatigue_logs_desc,
                reference_date=reference_date,
            )
            availability = classify_availability(
                score,
                game_logs=fatigue_logs_desc,
                reference_date=reference_date,
                latest_game_date=fatigue_logs_desc[0].game_date,
            )
            tier = availability.get('availability_status')
            if tier not in tier_counts:
                reference_date += timedelta(days=1)
                continue

            relief_next_day = any(_games_started(log) == 0 for log in next_day_logs)
            tier_counts[tier]['sample_size'] += 1
            tier_counts[tier]['next_day_appearances'] += 1 if relief_next_day else 0

            if prior_reference_date == reference_date - timedelta(days=1):
                intervening_logs = _logs_on_date(pitcher_logs, dates, day_before)
                if not intervening_logs:
                    no_appearance_days += 1
                    if prior_status != tier:
                        no_appearance_tier_flips += 1
            prior_status = tier
            prior_reference_date = reference_date
            reference_date += timedelta(days=1)

    return SeasonBacktest(
        season=season,
        window_label=_window_label(season),
        window_start=window_start,
        window_end=data_through,
        data_through=data_through,
        tier_counts=tier_counts,
        no_appearance_days=no_appearance_days,
        no_appearance_tier_flips=no_appearance_tier_flips,
    )


def _logs_between(logs, dates, start, end):
    left = bisect_left(dates, start)
    right = bisect_right(dates, end)
    return logs[left:right]


def _logs_on_date(logs, dates, target):
    return _logs_between(logs, dates, target, target)


def _games_started(log):
    value = getattr(log, 'games_started', None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _empty_tier_counts():
    return {
        tier: {
            'sample_size': 0,
            'next_day_appearances': 0,
        }
        for tier in TIER_ORDER
    }


def _window_label(season):
    return f'{season} primary' if season == PRIMARY_SEASON else f'{season} secondary'


def _rows_from_results(results, *, computed_at):
    rows = []
    for result in results:
        for tier_order, tier in enumerate(TIER_ORDER, start=1):
            counts = result.tier_counts[tier]
            sample_size = counts['sample_size']
            next_day_appearances = counts['next_day_appearances']
            next_day_rate = (
                next_day_appearances / sample_size
                if sample_size
                else 0.0
            )
            rows.append(AvailabilityBacktestResult(
                method_version=METHOD_VERSION,
                cadence=CADENCE,
                computed_at=computed_at,
                data_through=result.data_through,
                season=result.season,
                window_label=result.window_label,
                window_start=result.window_start,
                window_end=result.window_end,
                tier=tier,
                tier_order=tier_order,
                sample_size=sample_size,
                next_day_appearances=next_day_appearances,
                next_day_rate=next_day_rate,
                no_appearance_days=result.no_appearance_days,
                no_appearance_tier_flips=result.no_appearance_tier_flips,
                no_appearance_tier_flip_rate=result.no_appearance_tier_flip_rate,
                created_at=computed_at,
            ))
    return rows


def _empty_payload():
    return {
        'capability': 'availability_operational_backtest',
        'status': 'not_computed',
        'method_version': METHOD_VERSION,
        'cadence': CADENCE,
        'computed_at': None,
        'data_through': None,
        'ranking_applied': False,
        'selection_made': False,
        'windows': [],
        'framing': _framing(),
    }


def _payload_from_rows(rows):
    windows = []
    by_season = defaultdict(list)
    for row in rows:
        by_season[row.season].append(row)

    data_through_values = [row.data_through for row in rows if row.data_through]
    for season in sorted(by_season.keys(), reverse=True):
        season_rows = sorted(by_season[season], key=lambda row: row.tier_order)
        first = season_rows[0]
        windows.append({
            'season': season,
            'label': first.window_label,
            'is_primary': season == PRIMARY_SEASON,
            'window_start': first.window_start.isoformat() if first.window_start else None,
            'window_end': first.window_end.isoformat() if first.window_end else None,
            'data_through': first.data_through.isoformat() if first.data_through else None,
            'tiers': [
                {
                    'tier': row.tier,
                    'n': row.sample_size,
                    'next_day_appearances': row.next_day_appearances,
                    'next_day_rate': row.next_day_rate,
                    'next_day_rate_pct': round(row.next_day_rate * 100, 1),
                }
                for row in season_rows
            ],
            'stability': {
                'no_appearance_days': first.no_appearance_days,
                'no_appearance_tier_flips': first.no_appearance_tier_flips,
                'no_appearance_tier_flip_rate': first.no_appearance_tier_flip_rate,
                'no_appearance_tier_flip_rate_pct': round(
                    first.no_appearance_tier_flip_rate * 100,
                    1,
                ),
            },
        })

    latest = rows[0]
    return {
        'capability': 'availability_operational_backtest',
        'status': 'ok',
        'method_version': latest.method_version,
        'cadence': latest.cadence,
        'computed_at': latest.computed_at.isoformat(),
        'data_through': max(data_through_values).isoformat() if data_through_values else None,
        'ranking_applied': False,
        'selection_made': False,
        'windows': windows,
        'framing': _framing(),
    }


def _framing():
    return {
        'title': 'Operational Availability Backtest',
        'summary': (
            'Observed next-day relief usage by availability tier, reconstructed '
            'from game logs and Role Authority reliever filtering.'
        ),
        'claim': (
            'Arms classified Avoid or Unavailable were used the next day far '
            'less often than arms classified Available.'
        ),
        'caveat': (
            'This is an observed association with bullpen management behavior, '
            'not a physiological proof or causal workload claim. Reverse '
            'causality is present: an arm can be Avoid because he was just used, '
            'and managers may sit him the next day for the same reason.'
        ),
    }
