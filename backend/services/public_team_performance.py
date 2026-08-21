"""Governed Team Board projection of Current Active-Pen Performance.

The calculation remains owned by ``performance_intelligence``.  This module
only supplies the trusted Team Board's represented active population, invokes
the approved metric family over one common appearance selection, and shapes
the compact public contract.
"""

from __future__ import annotations

from datetime import date

from services import performance_intelligence
from services import performance_metrics


CAPABILITY = 'public_team_performance'
CONTRACT_VERSION = 'public_team_performance_v1'
POPULATION_BASIS = 'represented_default_visible_active_bullpen'
POPULATION_AUTHORITY = 'trusted_team_board.groups.default_visible_pitchers'
MEMBERSHIP_AUTHORITY = 'eligible_bullpen_pitcher_contexts'
WINDOW_POLICY = 'current_mlb_regular_season_through_represented_date'

STATUS_AVAILABLE = 'available'
STATUS_PARTIAL = 'partial'
STATUS_UNAVAILABLE = 'unavailable'

ADDITIONAL_METRICS_LIMITATION = (
    'K-BB%, home-run rate, and inherited-runner outcomes are not included '
    'because they do not yet have approved public metric and sample contracts.'
)
WHIP_INPUT_LIMITATION = (
    'Active Bullpen WHIP is withheld because at least one qualifying official '
    'pitching line lacks authoritative hits or walks.'
)

METRIC_IDS = (
    performance_metrics.METRIC_CURRENT_ACTIVE_PEN_ERA,
    performance_metrics.METRIC_CURRENT_ACTIVE_PEN_WHIP,
)


def build_public_team_performance_payload(team_id, *, board):
    represented = _represented_date(board)
    group = _represented_active_group(board, represented)
    if represented is None:
        return _unavailable('represented_date_unavailable', group=group)
    if not group['pitcher_ids']:
        return _unavailable('active_group_empty', group=group, through=represented)

    freshness = board.get('freshness') or {}
    reads = performance_intelligence.build_metric_reads(
        METRIC_IDS,
        team_id,
        season=represented.year,
        reference_date=represented,
        through_date=represented,
        freshness={
            'represented_date': represented.isoformat(),
            'data_through_date': represented.isoformat(),
            'freshness_state': freshness.get('freshness_state'),
            'fail_closed': bool(freshness.get('fail_closed')),
            'provable': not bool(freshness.get('fail_closed')),
            'authority': 'trusted_team_board_publication',
        },
        group=group,
        publication_surface=performance_intelligence.PUBLIC_SURFACE_TEAM_BOARD,
    )
    return _project_reads(reads, represented)


def _represented_date(board):
    team_state = board.get('team_state') or {}
    freshness = board.get('freshness') or {}
    raw = (
        team_state.get('data_through')
        or freshness.get('data_through')
        or freshness.get('latest_workload_date')
    )
    try:
        return date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


def _represented_active_group(board, represented):
    members = []
    seen = set()
    for group in board.get('groups') or []:
        for card in group.get('pitchers') or []:
            if (card.get('visibility') or {}).get('is_visible_by_default') is False:
                continue
            pitcher_id = card.get('pitcher_id')
            if not isinstance(pitcher_id, int) or pitcher_id in seen:
                continue
            seen.add(pitcher_id)
            members.append({
                'pitcher_id': pitcher_id,
                'pitcher_mlb_id': card.get('pitcher_mlb_id'),
                'pitcher_full_name': card.get('name'),
                'role_evidence': None,
            })
    return {
        'team_id': (board.get('team') or {}).get('team_id'),
        'reference_date': represented.isoformat() if represented else None,
        'membership_authority': MEMBERSHIP_AUTHORITY,
        'population_authority': POPULATION_AUTHORITY,
        'pitcher_ids': [member['pitcher_id'] for member in members],
        'members': members,
        'size': len(members),
    }


def _project_reads(reads, represented):
    era_read = reads[performance_metrics.METRIC_CURRENT_ACTIVE_PEN_ERA]
    whip_read = reads[performance_metrics.METRIC_CURRENT_ACTIVE_PEN_WHIP]
    metric_reads = (era_read, whip_read)
    metrics = [_metric_payload(read) for read in metric_reads]
    published = [metric for metric in metrics if metric['value'] is not None]
    below_sample = [
        metric for metric in metrics
        if metric['qualification']['status'] == 'below_minimum'
    ]

    if published:
        status = STATUS_PARTIAL
        reason_code = (
            'additional_metrics_not_governed'
            if len(published) == len(metrics)
            else 'metric_partially_available'
        )
        names = [metric['label'] for metric in published]
        summary = (
            f'{" and ".join(names)} describe recorded results for the current '
            'active bullpen and remain supporting context.'
        )
    elif below_sample:
        status = STATUS_PARTIAL
        reason_code = 'below_minimum_sample'
        summary = performance_metrics.ERA_BELOW_SAMPLE_WORDING
    else:
        status = STATUS_UNAVAILABLE
        reason_code = _first_reason(metric_reads)
        summary = None

    sample_read = next(
        (read for read in metric_reads if (read.get('sample') or {}).get('appearances')),
        era_read,
    )
    sample = sample_read.get('sample') or {}
    read_group = sample_read.get('group') or {}
    active_count = read_group.get('active_group_size')
    if not isinstance(active_count, int):
        active_count = read_group.get('size')
    contributing_count = read_group.get('contributing_pitcher_count')
    appearances = sample.get('appearances')
    innings = sample.get('innings_display')
    return {
        'capability': CAPABILITY,
        'contract_version': CONTRACT_VERSION,
        'status': status,
        'reason_code': reason_code,
        'through': represented.isoformat(),
        'window': {
            'policy': WINDOW_POLICY,
            'season': represented.year,
            'start': date(represented.year, 1, 1).isoformat(),
            'through': represented.isoformat(),
        },
        'population_basis': POPULATION_BASIS,
        'population_authority': POPULATION_AUTHORITY,
        'membership_authority': MEMBERSHIP_AUTHORITY,
        'active_pitcher_count': active_count,
        'pitchers_with_sample': contributing_count,
        'relief_appearances': appearances,
        'innings_pitched': innings,
        'metrics': metrics,
        'sample': {
            'recorded_outs': sample.get('outs'),
            'innings_pitched': innings,
            'minimum_recorded_outs': sample.get('minimum_sample'),
            'minimum_innings': performance_intelligence.innings_display(
                sample.get('minimum_sample') or 0
            ),
            'meets_minimum': sample.get('meets_minimum_sample'),
        },
        'summary': summary,
        'sample_summary': _sample_summary(
            active_count, contributing_count, appearances, innings, represented,
        ),
        'limitations': _limitations(metrics),
        'evidence': era_read.get('evidence'),
        'evidence_by_metric': {
            read.get('metric_id'): read.get('evidence') for read in metric_reads
        },
    }


def _metric_payload(read):
    sample = read.get('sample') or {}
    publication = read.get('publication') or {}
    publishable = publication.get('publishable') is True
    is_below = (
        read.get('value') is not None
        and sample.get('meets_minimum_sample') is False
    )
    if publishable:
        qualification_status = 'qualified'
        reason_code = None
    elif is_below:
        qualification_status = 'below_minimum'
        reason_code = publication.get('reason') or 'below_minimum_sample'
    else:
        qualification_status = 'unavailable'
        reason_code = read.get('reason_code') or publication.get('reason')
    metric_id = read.get('metric_id')
    return {
        'key': {
            performance_metrics.METRIC_CURRENT_ACTIVE_PEN_ERA:
                'active_bullpen_era',
            performance_metrics.METRIC_CURRENT_ACTIVE_PEN_WHIP:
                'active_bullpen_whip',
        }.get(metric_id),
        'metric_id': metric_id,
        'label': read.get('metric_name'),
        'value': read.get('display_value') if publishable else None,
        'method_version': read.get('metric_version'),
        'qualification': {
            'status': qualification_status,
            'reason_code': reason_code,
            'measured_sample': sample.get('measured_sample'),
            'minimum_sample': sample.get('minimum_sample'),
            'sample_unit': sample.get('minimum_sample_unit'),
            'sample_authority': sample.get('minimum_sample_authority'),
        },
    }


def _limitations(metrics):
    whip = next(
        (metric for metric in metrics if metric['metric_id'] ==
         performance_metrics.METRIC_CURRENT_ACTIVE_PEN_WHIP),
        None,
    )
    if whip and whip['qualification']['status'] == 'unavailable':
        reason = whip['qualification']['reason_code'] or ''
        if reason == performance_intelligence.REFUSAL_QUALIFYING_ROW_INVALID:
            return [WHIP_INPUT_LIMITATION, ADDITIONAL_METRICS_LIMITATION]
    return [ADDITIONAL_METRICS_LIMITATION]


def _first_reason(reads):
    for read in reads:
        reason = read.get('reason_code') or (read.get('publication') or {}).get('reason')
        if reason:
            return reason
    return 'performance_unavailable'


def _sample_summary(active_count, contributing_count, appearances, innings, represented):
    active = active_count if isinstance(active_count, int) else 0
    contributing = contributing_count if isinstance(contributing_count, int) else 0
    appearances = appearances if isinstance(appearances, int) else 0
    return (
        f'Current regular season · {active} active {_plural(active, "arm")} · '
        f'{contributing} with a sample · {appearances} relief '
        f'{_plural(appearances, "appearance")} · {innings or "0.0"} innings · '
        f'Through {_month_day(represented)}'
    )


def _unavailable(reason_code, *, group=None, through=None):
    represented = through.isoformat() if isinstance(through, date) else None
    active_count = (group or {}).get('size')
    return {
        'capability': CAPABILITY,
        'contract_version': CONTRACT_VERSION,
        'status': STATUS_UNAVAILABLE,
        'reason_code': reason_code,
        'through': represented,
        'window': None,
        'population_basis': POPULATION_BASIS,
        'population_authority': POPULATION_AUTHORITY,
        'membership_authority': MEMBERSHIP_AUTHORITY,
        'active_pitcher_count': active_count,
        'pitchers_with_sample': 0,
        'relief_appearances': 0,
        'innings_pitched': '0.0',
        'metrics': [],
        'sample': None,
        'summary': None,
        'sample_summary': None,
        'limitations': [ADDITIONAL_METRICS_LIMITATION],
        'evidence': None,
        'evidence_by_metric': {},
    }


def _plural(count, singular):
    return singular if count == 1 else f'{singular}s'


def _month_day(value):
    return f'{value.strftime("%b")} {value.day}, {value.year}'


__all__ = [
    'CAPABILITY',
    'CONTRACT_VERSION',
    'MEMBERSHIP_AUTHORITY',
    'POPULATION_AUTHORITY',
    'POPULATION_BASIS',
    'WHIP_INPUT_LIMITATION',
    'WINDOW_POLICY',
    'build_public_team_performance_payload',
]
