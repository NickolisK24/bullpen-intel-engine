"""Aggregate privacy-bounded traffic facts for the internal reporting dashboard."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func

from models.traffic_internal_visitor import TrafficInternalVisitor
from models.traffic_page_view import TrafficPageView


REPORTING_TIMEZONE = 'America/New_York'
CANONICAL_SITE_HOST = 'baseballos.app'
OWNED_REFERRER_DOMAINS = frozenset({
    'baseballos.app',
    'www.baseballos.app',
    'baseballos.vercel.app',
})
RANGE_DAYS = {'7d': 7, '30d': 30, '90d': 90}
RANGE_LABELS = {'7d': 'Last 7 days', '30d': 'Last 30 days', '90d': 'Last 90 days', 'all': 'All time'}
SHARE_ENTRY_SOURCES = frozenset({'share', 'share_link', 'share_card'})
DEEP_EVIDENCE_TARGETS = frozenset({
    'team_relief_work', 'pitcher_lanes', 'pitcher_detail', 'comparison_evidence',
})
TEAM_EVIDENCE_TARGETS = frozenset({
    'team_read', 'team_relief_work', 'pitcher_lanes', 'pitcher_detail',
})

METRIC_DEFINITIONS = {
    'external_visitors': 'Distinct qualifying browser identities active in the selected period; these are not verified individual people.',
    'sessions': 'Distinct qualifying browser sessions active in the selected period.',
    'page_views': 'Canonical public BaseballOS page-view rows recorded in the selected period.',
    'returning_visitors': 'Qualifying browser identities active in the period whose first-ever qualifying page view occurred before the period start.',
    'new_visitors': 'Qualifying browser identities whose first-ever qualifying page view occurred inside the selected period.',
    'multi_page_sessions': 'Qualifying sessions with at least two page views.',
    'pages_per_session': 'Qualifying page views divided by qualifying sessions; unavailable when there are no sessions.',
    'entry_source': 'Bounded navigation context attached to a canonical Bullpen URL; it is separate from campaign attribution.',
    'evidence_target_views': 'Canonical exact-destination page views; opening a destination does not prove every item was read.',
    'shared_link_landing_sessions': 'Qualifying sessions whose first page view begins from a BaseballOS share-oriented URL.',
    'evidence_depth': 'Qualifying Bullpen sessions that opened at least one deeper evidence destination.',
    'comparison_pairs': 'Descriptive canonical URL selections aggregated without left-right order; they are not game predictions.',
}


def _utc_naive(value):
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _aware_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value):
    if value is None:
        return None
    return _aware_utc(value).isoformat().replace('+00:00', 'Z')


def _external_filters():
    internal = exists().where(TrafficInternalVisitor.visitor_id == TrafficPageView.visitor_id)
    return (
        TrafficPageView.site_host == CANONICAL_SITE_HOST,
        TrafficPageView.is_bot.is_(False),
        ~internal,
    )


def _period_rows(start, end):
    query = TrafficPageView.query.filter(*_external_filters())
    if start is not None:
        query = query.filter(TrafficPageView.occurred_at >= _utc_naive(start))
    if end is not None:
        query = query.filter(TrafficPageView.occurred_at < _utc_naive(end))
    return query.order_by(TrafficPageView.occurred_at.asc(), TrafficPageView.id.asc()).all()


def _measurement_start():
    return (
        TrafficPageView.query
        .with_entities(func.min(TrafficPageView.occurred_at))
        .filter(TrafficPageView.site_host == CANONICAL_SITE_HOST)
        .scalar()
    )


def _first_views_for_visitors(visitor_ids):
    if not visitor_ids:
        return {}
    rows = (
        TrafficPageView.query
        .with_entities(TrafficPageView.visitor_id, func.min(TrafficPageView.occurred_at))
        .filter(*_external_filters(), TrafficPageView.visitor_id.in_(visitor_ids))
        .group_by(TrafficPageView.visitor_id)
        .all()
    )
    return {visitor_id: occurred_at for visitor_id, occurred_at in rows}


def _landing_views_for_sessions(session_ids):
    if not session_ids:
        return []
    rows = (
        TrafficPageView.query
        .filter(*_external_filters(), TrafficPageView.session_id.in_(session_ids))
        .order_by(TrafficPageView.occurred_at.asc(), TrafficPageView.id.asc())
        .all()
    )
    earliest = {}
    for row in rows:
        earliest.setdefault(row.session_id, row)
    return list(earliest.values())


def _summary(rows, start):
    visitor_ids = {row.visitor_id for row in rows}
    session_counts = Counter(row.session_id for row in rows)
    first_views = _first_views_for_visitors(visitor_ids)
    start_naive = _utc_naive(start)
    returning = sum(1 for occurred_at in first_views.values() if occurred_at < start_naive)
    new = sum(1 for occurred_at in first_views.values() if occurred_at >= start_naive)
    sessions = len(session_counts)
    page_views = len(rows)
    return {
        'external_visitors': len(visitor_ids),
        'sessions': sessions,
        'page_views': page_views,
        'returning_visitors': returning,
        'new_visitors': new,
        'multi_page_sessions': sum(1 for count in session_counts.values() if count >= 2),
        'pages_per_session': round(page_views / sessions, 2) if sessions else None,
    }


def _change(current, previous):
    if current is None or previous is None:
        return {'absolute': None, 'percent': None}
    absolute = round(current - previous, 2)
    percent = None if previous == 0 else round((current - previous) / previous * 100, 2)
    return {'absolute': absolute, 'percent': percent}


def _daily(rows, start, end):
    local_zone = ZoneInfo(REPORTING_TIMEZONE)
    counts = defaultdict(lambda: {'visitors': set(), 'sessions': set(), 'page_views': 0})
    for row in rows:
        day = _aware_utc(row.occurred_at).astimezone(local_zone).date().isoformat()
        counts[day]['visitors'].add(row.visitor_id)
        counts[day]['sessions'].add(row.session_id)
        counts[day]['page_views'] += 1

    start_day = _aware_utc(start).astimezone(local_zone).date()
    end_day = _aware_utc(end - timedelta(microseconds=1)).astimezone(local_zone).date()
    result = []
    day = start_day
    while day <= end_day:
        values = counts[day.isoformat()]
        result.append({
            'date': day.isoformat(),
            'visitors': len(values['visitors']),
            'sessions': len(values['sessions']),
            'page_views': values['page_views'],
        })
        day += timedelta(days=1)
    return result


def _external_referrer_domain(value):
    domain = (value or '').strip().lower().rstrip('.')
    if not domain or domain in OWNED_REFERRER_DOMAINS:
        return None
    return domain


def _acquisition(landing_views, total_sessions):
    categories = Counter()
    referrers = Counter()
    campaigns = Counter()
    landing_surfaces = Counter()
    for row in landing_views:
        utms = (row.utm_source, row.utm_medium, row.utm_campaign, row.utm_content)
        external_referrer = _external_referrer_domain(row.referrer_domain)
        if external_referrer:
            referrers[external_referrer] += 1
        if any(utms):
            categories['campaign'] += 1
            campaigns[(row.utm_source, row.utm_medium, row.utm_campaign)] += 1
        elif external_referrer:
            categories['referral'] += 1
        else:
            categories['direct_unknown'] += 1
        landing_surfaces[row.surface] += 1

    def category(key):
        sessions = categories[key]
        return {
            'sessions': sessions,
            'percentage': round(sessions / total_sessions * 100, 2) if total_sessions else None,
        }

    return {
        'categories': {
            'campaign': category('campaign'),
            'referral': category('referral'),
            'direct_unknown': category('direct_unknown'),
        },
        'top_referrers': [
            {'referrer_domain': domain, 'sessions': count}
            for domain, count in sorted(referrers.items(), key=lambda item: (-item[1], item[0]))[:20]
        ],
        'campaigns': [
            {
                'utm_source': source,
                'utm_medium': medium,
                'utm_campaign': campaign,
                'sessions': count,
            }
            for (source, medium, campaign), count in sorted(
                campaigns.items(), key=lambda item: (-item[1], tuple(value or '' for value in item[0])),
            )[:20]
        ],
        'landing_surfaces': [
            {'surface': surface, 'sessions': count}
            for surface, count in sorted(landing_surfaces.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def _visited_surfaces(rows):
    counts = Counter(row.surface for row in rows)
    return [
        {'surface': surface, 'page_views': count}
        for surface, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _bullpen_exploration(rows):
    surface_counts = Counter(row.surface for row in rows)
    team_counts = Counter(row.team_ref for row in rows if row.team_ref)
    return {
        'bullpen_board_views': surface_counts['bullpen_board'],
        'compare_bullpens_views': surface_counts['compare_bullpens'],
        'all_pitchers_views': surface_counts['all_pitchers'],
        'team_contexts': [
            {'team_ref': team_ref, 'page_views': count}
            for team_ref, count in sorted(team_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        'pitcher_context_page_views': sum(1 for row in rows if row.pitcher_id is not None),
    }


def _evidence_exploration(rows):
    target_counts = Counter(row.evidence_target for row in rows if row.evidence_target)
    team_counts = Counter(
        row.team_ref for row in rows
        if row.team_ref and row.evidence_target in TEAM_EVIDENCE_TARGETS
    )
    pair_counts = Counter()
    source_views = Counter()
    source_sessions = defaultdict(set)
    for row in rows:
        if row.team_a_ref and row.team_b_ref and row.team_a_ref != row.team_b_ref:
            pair_counts[tuple(sorted((row.team_a_ref, row.team_b_ref)))] += 1
        if row.entry_source:
            source_views[row.entry_source] += 1
            source_sessions[row.entry_source].add(row.session_id)

    return {
        'team_read_views': target_counts['team_read'],
        'team_relief_work_views': target_counts['team_relief_work'],
        'pitcher_lanes_views': target_counts['pitcher_lanes'],
        'pitcher_detail_views': target_counts['pitcher_detail'],
        'comparison_read_views': target_counts['comparison_read'],
        'comparison_evidence_views': target_counts['comparison_evidence'],
        'team_contexts': [
            {'team_ref': team_ref, 'page_views': count}
            for team_ref, count in sorted(team_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
        ],
        'comparison_pairs': [
            {
                'team_a_ref': pair[0],
                'team_b_ref': pair[1],
                'pair_key': f'{pair[0]}:{pair[1]}',
                'page_views': count,
            }
            for pair, count in sorted(pair_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
        ],
        'entry_sources': [
            {
                'entry_source': source,
                'page_views': count,
                'sessions': len(source_sessions[source]),
            }
            for source, count in sorted(source_views.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def _shared_link_landings(landing_views):
    share_landings = [row for row in landing_views if row.entry_source in SHARE_ENTRY_SOURCES]
    return {
        'share_origin_sessions': len({row.session_id for row in share_landings}),
        'share_origin_visitors': len({row.visitor_id for row in share_landings}),
        'share_origin_page_views': len(share_landings),
    }


def _evidence_depth(rows):
    bullpen_sessions = {
        row.session_id for row in rows
        if row.surface in {'bullpen_board', 'compare_bullpens', 'all_pitchers'}
    }
    deeper_sessions = {
        row.session_id for row in rows if row.evidence_target in DEEP_EVIDENCE_TARGETS
    }
    count = len(deeper_sessions)
    return {
        'sessions_opening_deeper_evidence': count,
        'percentage_of_bullpen_sessions_opening_deeper_evidence': (
            round(count / len(bullpen_sessions) * 100, 2) if bullpen_sessions else None
        ),
    }


def _measurement_health(start, end, external_rows):
    canonical_rows = (
        TrafficPageView.query
        .filter(
            TrafficPageView.site_host == CANONICAL_SITE_HOST,
            TrafficPageView.occurred_at >= _utc_naive(start),
            TrafficPageView.occurred_at < _utc_naive(end),
        )
        .order_by(TrafficPageView.occurred_at.asc())
        .all()
    )
    internal_rows = TrafficInternalVisitor.query.with_entities(TrafficInternalVisitor.visitor_id).all()
    internal_ids = {row.visitor_id for row in internal_rows}
    canonical_first, canonical_last = (
        TrafficPageView.query
        .with_entities(
            func.min(TrafficPageView.occurred_at),
            func.max(TrafficPageView.occurred_at),
        )
        .filter(TrafficPageView.site_host == CANONICAL_SITE_HOST)
        .one()
    )
    last_external = (
        TrafficPageView.query
        .with_entities(func.max(TrafficPageView.occurred_at))
        .filter(*_external_filters())
        .scalar()
    )
    return {
        'measurement_started_at': _iso(canonical_first),
        'last_external_page_view_at': _iso(last_external),
        'last_canonical_page_view_at': _iso(canonical_last),
        'registered_internal_browser_ids': len(internal_rows),
        'selected_period': {
            'canonical_page_views': len(canonical_rows),
            'external_page_views': len(external_rows),
            'excluded_bot_page_views': sum(1 for row in canonical_rows if row.is_bot),
            'excluded_internal_page_views': sum(
                1 for row in canonical_rows if row.visitor_id in internal_ids
            ),
            'unknown_device_external_page_views': sum(
                1 for row in external_rows if row.device_class == 'unknown'
            ),
        },
    }


def build_traffic_summary(range_key='7d', *, now=None):
    if range_key not in (*RANGE_DAYS, 'all'):
        raise ValueError('invalid_range')

    now_utc = _aware_utc(now or datetime.now(timezone.utc))
    local_now = now_utc.astimezone(ZoneInfo(REPORTING_TIMEZONE))
    measurement_start_naive = _measurement_start()
    measurement_start = _aware_utc(measurement_start_naive) if measurement_start_naive else None

    if range_key == 'all':
        start = measurement_start or now_utc
    else:
        days = RANGE_DAYS[range_key]
        local_start_date = local_now.date() - timedelta(days=days - 1)
        start = datetime.combine(local_start_date, time.min, ZoneInfo(REPORTING_TIMEZONE)).astimezone(timezone.utc)
    end = now_utc

    rows = _period_rows(start, end)
    summary = _summary(rows, start)
    landing_views = _landing_views_for_sessions({row.session_id for row in rows})
    acquisition = _acquisition(landing_views, summary['sessions'])

    if range_key == 'all':
        comparison = {
            'available': False,
            'reason': 'all_time_range_has_no_prior_equal_period',
            'period': None,
            'previous': None,
            'changes': None,
        }
    else:
        previous_end = start
        previous_start = start - (end - start)
        if measurement_start is None or measurement_start > previous_start:
            comparison = {
                'available': False,
                'reason': 'incomplete_prior_period',
                'period': {'start': _iso(previous_start), 'end': _iso(previous_end)},
                'previous': None,
                'changes': None,
            }
        else:
            previous_rows = _period_rows(previous_start, previous_end)
            previous_summary = _summary(previous_rows, previous_start)
            comparison = {
                'available': True,
                'reason': None,
                'period': {'start': _iso(previous_start), 'end': _iso(previous_end)},
                'previous': previous_summary,
                'changes': {
                    key: _change(summary[key], previous_summary[key])
                    for key in summary
                },
            }

    return {
        'generated_at': _iso(now_utc),
        'timezone': REPORTING_TIMEZONE,
        'selected_range': {
            'key': range_key,
            'label': RANGE_LABELS[range_key],
            'start': _iso(start),
            'end': _iso(end),
        },
        'measurement_start': _iso(measurement_start),
        'definitions': METRIC_DEFINITIONS,
        'summary': summary,
        'comparison': comparison,
        'daily': _daily(rows, start, end),
        'new_vs_returning': {
            'new_visitors': summary['new_visitors'],
            'returning_visitors': summary['returning_visitors'],
        },
        'session_depth': {
            'single_page_sessions': summary['sessions'] - summary['multi_page_sessions'],
            'multi_page_sessions': summary['multi_page_sessions'],
            'pages_per_session': summary['pages_per_session'],
        },
        'acquisition': acquisition['categories'],
        'top_referrers': acquisition['top_referrers'],
        'campaigns': acquisition['campaigns'],
        'landing_surfaces': acquisition['landing_surfaces'],
        'most_visited_surfaces': _visited_surfaces(rows),
        'bullpen_exploration': _bullpen_exploration(rows),
        'evidence_exploration': _evidence_exploration(rows),
        'shared_link_landings': _shared_link_landings(landing_views),
        'evidence_depth': _evidence_depth(rows),
        'measurement_health': _measurement_health(start, end, rows),
    }
