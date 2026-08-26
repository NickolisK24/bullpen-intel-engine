"""Published Team State history and governed change markers for one bullpen.

The service serves only immutable Team State ShareArtifacts that BaseballOS
actually published. It never recalculates an old Team State, carries a state
across a missing date, or derives movement from adjacent labels. Transition
context and HIST-02 markers come only from the frozen Team Board delta substrate.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Mapping

from sqlalchemy.orm import selectinload

from models.dashboard_snapshot import DashboardSnapshot
from models.share_artifact import (
    LIFECYCLE_PUBLISHED,
    ShareArtifact,
    ShareArtifactRelation,
)
from services.share_artifact_public import project_public_share_artifact
from services.share_artifacts import verify_share_artifact_integrity
from services.team_board_delta_substrate import (
    COMPARABLE,
    SNAPSHOT_PAYLOAD_VERSION,
    SNAPSHOT_SOURCE_PREFIX,
    SNAPSHOT_TYPE,
    compare_snapshots,
)
from services.team_directory import valid_team_directory
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE
from utils.db import db


CAPABILITY = 'team_state_history'
CONTRACT = 'team_state_history_v2'
STATUS_AVAILABLE = 'available'
STATUS_QUIET = 'quiet'
COMPARISON_UNAVAILABLE = 'comparison_unavailable'
COMPARISON_COVERAGE_GAP = 'coverage_gap'
COMPARISON_AUTHORITY_MISSING = 'comparison_authority_missing'
EVENT_OVERLAY_AVAILABLE = 'available'
EVENT_OVERLAY_WITHHELD = 'withheld'
EVENT_OUTCOME_CHANGED = 'changed'
EVENT_OUTCOME_UNCHANGED = 'unchanged'
EVENT_OUTCOME_UNAVAILABLE = 'unavailable'
EVENT_PRIOR_PUBLICATION_MISSING = 'prior_publication_missing'
TEAM_STATE_CHANGE_EVENT = 'team_state_change'
TEAM_STATE_CHANGE_LABEL = 'Team State changed'


def _as_mapping(value):
    return dict(value) if isinstance(value, Mapping) else {}


def _season_bounds(season):
    return date(season, 1, 1), date(season, 12, 31)


def _team_for_abbreviation(abbreviation, directory):
    normalized = str(abbreviation or '').strip().upper()
    if not normalized:
        return None
    return next((
        dict(team)
        for team in directory.values()
        if str(team.get('team_abbreviation') or '').strip().upper() == normalized
    ), None)


def _artifact_candidates(team_id, season, session):
    start, end = _season_bounds(season)
    return (
        session.query(ShareArtifact)
        .options(
            selectinload(ShareArtifact.evidence),
            selectinload(ShareArtifact.outgoing_relations),
        )
        .filter(
            ShareArtifact.artifact_type == TEAM_STATE_ARTIFACT_TYPE,
            ShareArtifact.team_id == int(team_id),
            ShareArtifact.lifecycle_state == LIFECYCLE_PUBLISHED,
            ShareArtifact.product_date >= start,
            ShareArtifact.product_date <= end,
        )
        .order_by(
            ShareArtifact.product_date.desc(),
            ShareArtifact.published_at.desc(),
            ShareArtifact.id.desc(),
        )
        .all()
    )


def _healthy_artifacts_by_date(candidates):
    grouped = defaultdict(list)
    for artifact in candidates:
        if artifact.product_date is not None:
            grouped[artifact.product_date].append(artifact)

    healthy = {}
    invalid_dates = set()
    for represented_date, rows in grouped.items():
        for artifact in rows:
            try:
                verify_share_artifact_integrity(artifact)
                result = project_public_share_artifact(artifact)
            except Exception:  # fail closed per artifact; an older healthy candidate may remain
                invalid_dates.add(represented_date)
                continue
            if result.is_ok and result.view:
                healthy[represented_date] = (artifact, result.view)
                break
            invalid_dates.add(represented_date)
    return healthy, invalid_dates


def _sidecars(artifacts, team_id, session):
    artifact_ids = {artifact.id for artifact, _ in artifacts.values()}
    if not artifact_ids:
        return {}
    rows = (
        session.query(DashboardSnapshot)
        .filter(
            DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE,
            DashboardSnapshot.status == 'ready',
            DashboardSnapshot.payload_version == SNAPSHOT_PAYLOAD_VERSION,
            DashboardSnapshot.published_at.isnot(None),
            DashboardSnapshot.source == f'{SNAPSHOT_SOURCE_PREFIX}{int(team_id)}',
        )
        .order_by(DashboardSnapshot.data_through.desc(), DashboardSnapshot.id.desc())
        .all()
    )
    resolved = {}
    for row in rows:
        artifact_id = _as_mapping(_as_mapping(row.payload).get('source')).get('artifact_id')
        if artifact_id in artifact_ids and artifact_id not in resolved:
            resolved[artifact_id] = row
    return resolved


def _comparison(previous, current, sidecars):
    previous_date, previous_artifact, previous_view = previous
    current_date, current_artifact, current_view = current
    base = {
        'status': COMPARISON_UNAVAILABLE,
        'reason_code': COMPARISON_AUTHORITY_MISSING,
        'from_date': previous_date.isoformat(),
        'to_date': current_date.isoformat(),
        'transition': None,
        'boundary': False,
    }
    if current_date - previous_date != timedelta(days=1):
        return {**base, 'reason_code': COMPARISON_COVERAGE_GAP}

    previous_sidecar = sidecars.get(previous_artifact.id)
    current_sidecar = sidecars.get(current_artifact.id)
    if previous_sidecar is None or current_sidecar is None:
        return {
            **base,
            'boundary': bool(
                previous_artifact.render_version != current_artifact.render_version
                or previous_view.get('payload_version') != current_view.get('payload_version')
            ),
        }

    domain = compare_snapshots(previous_sidecar, current_sidecar)['domains']['team_state']
    if domain.get('status') != COMPARABLE:
        return {
            **base,
            'reason_code': domain.get('reason_code') or domain.get('status'),
            'boundary': True,
        }

    previous_state = _as_mapping(domain.get('previous'))
    current_state = _as_mapping(domain.get('current'))
    previous_public = _as_mapping(previous_state.get('public_state'))
    current_public = _as_mapping(current_state.get('public_state'))
    previous_code = previous_public.get('public_code') or previous_state.get('public_state')
    current_code = current_public.get('public_code') or current_state.get('public_state')
    previous_label = previous_public.get('public_label') or previous_state.get('public_label')
    current_label = current_public.get('public_label') or current_state.get('public_label')
    return {
        **base,
        'status': COMPARABLE,
        'reason_code': None,
        'transition': {
            'from_code': previous_code,
            'from_state': previous_label,
            'to_code': current_code,
            'to_state': current_label,
            'changed': previous_code != current_code,
        } if previous_label and current_label else None,
    }


def _citation(artifact, view):
    routes = _as_mapping(view.get('routes'))
    return {
        'public_id': artifact.public_id,
        'citation_url': routes.get('share_url'),
    }


def _event_state(view):
    team_state = _as_mapping(view.get('team_state'))
    return {
        'code': team_state.get('public_state'),
        'label': team_state.get('public_label'),
    }


def _withheld_event_overlay(reason_code):
    return {
        'status': EVENT_OVERLAY_WITHHELD,
        'outcome': EVENT_OUTCOME_UNAVAILABLE,
        'reason_code': reason_code or COMPARISON_AUTHORITY_MISSING,
    }


def _event_overlay(comparison, previous, current, team_id):
    if not comparison or comparison.get('status') != COMPARABLE:
        return _withheld_event_overlay(
            _as_mapping(comparison).get('reason_code')
            or EVENT_PRIOR_PUBLICATION_MISSING
        ), []

    transition = _as_mapping(comparison.get('transition'))
    if not transition:
        return _withheld_event_overlay(COMPARISON_AUTHORITY_MISSING), []

    if transition.get('changed') is not True:
        return {
            'status': EVENT_OVERLAY_AVAILABLE,
            'outcome': EVENT_OUTCOME_UNCHANGED,
            'reason_code': None,
        }, []

    previous_date, previous_artifact, previous_view = previous
    current_date, current_artifact, current_view = current
    from_state = _event_state(previous_view)
    to_state = _event_state(current_view)
    previous_citation = _citation(previous_artifact, previous_view)
    current_citation = _citation(current_artifact, current_view)
    required_values = (
        from_state.get('code'), from_state.get('label'),
        to_state.get('code'), to_state.get('label'),
        previous_citation.get('public_id'), previous_citation.get('citation_url'),
        current_citation.get('public_id'), current_citation.get('citation_url'),
    )
    comparison_matches_artifacts = (
        transition.get('from_code') == from_state.get('code')
        and transition.get('to_code') == to_state.get('code')
    )
    if (
        any(value in (None, '') for value in required_values)
        or not comparison_matches_artifacts
    ):
        return _withheld_event_overlay(COMPARISON_AUTHORITY_MISSING), []

    overlay = {
        'status': EVENT_OVERLAY_AVAILABLE,
        'outcome': EVENT_OUTCOME_CHANGED,
        'reason_code': None,
    }
    return overlay, [{
        'event_type': TEAM_STATE_CHANGE_EVENT,
        'event_id': (
            f'{TEAM_STATE_CHANGE_EVENT}:{int(team_id)}:'
            f'{previous_artifact.public_id}:{current_artifact.public_id}'
        ),
        'event_date': current_date.isoformat(),
        'from_date': previous_date.isoformat(),
        'to_date': current_date.isoformat(),
        'label': TEAM_STATE_CHANGE_LABEL,
        'from_state': from_state,
        'to_state': to_state,
        'citations': {
            'previous': previous_citation,
            'current': current_citation,
        },
    }]


def _history_row(artifact, view):
    copy = _as_mapping(view.get('copy'))
    team_state = _as_mapping(view.get('team_state'))
    routes = _as_mapping(view.get('routes'))
    corrected = any(
        relation.relation_type == ShareArtifactRelation.RELATION_SUPERSEDES
        for relation in artifact.outgoing_relations or ()
    )
    return {
        'represented_date': artifact.product_date.isoformat(),
        'team_state': {
            'public_code': team_state.get('public_state'),
            'public_label': team_state.get('public_label'),
        },
        'headline': copy.get('headline'),
        'explanation': copy.get('why') or copy.get('summary'),
        'limitations': list(view.get('limitations') or ()),
        'artifact': {
            'public_id': artifact.public_id,
            'citation_url': routes.get('share_url'),
            'schema_version': artifact.schema_version,
            'render_version': artifact.render_version,
            'payload_version': view.get('payload_version'),
            'published_at': artifact.published_at.isoformat() if artifact.published_at else None,
            'publication_scope': view.get('publication_scope'),
            'corrected_publication': corrected,
        },
        'comparison': None,
        'event_overlay': _withheld_event_overlay(EVENT_PRIOR_PUBLICATION_MISSING),
        'events': [],
    }


def build_team_state_history(team_abbreviation, *, season, session=None):
    """Return one bounded, immutable Team State timeline response."""
    session = session or db.session
    try:
        season = int(season)
    except (TypeError, ValueError):
        raise ValueError('season_invalid')
    if season < 1876 or season > 9999:
        raise ValueError('season_invalid')

    team = _team_for_abbreviation(team_abbreviation, valid_team_directory())
    if team is None:
        return None
    team_id = int(team['team_id'])
    candidates = _artifact_candidates(team_id, season, session)
    healthy, invalid_dates = _healthy_artifacts_by_date(candidates)
    ordered_dates = sorted(healthy)
    rows_by_date = {
        represented_date: _history_row(*healthy[represented_date])
        for represented_date in ordered_dates
    }

    sidecars = _sidecars(healthy, team_id, session)
    for index in range(1, len(ordered_dates)):
        previous_date = ordered_dates[index - 1]
        current_date = ordered_dates[index]
        previous = (previous_date, *healthy[previous_date])
        current = (current_date, *healthy[current_date])
        comparison = _comparison(
            previous,
            current,
            sidecars,
        )
        event_overlay, events = _event_overlay(
            comparison,
            previous,
            current,
            team_id,
        )
        rows_by_date[current_date]['comparison'] = comparison
        rows_by_date[current_date]['event_overlay'] = event_overlay
        rows_by_date[current_date]['events'] = events

    retained_candidate_dates = sorted({
        artifact.product_date
        for artifact in candidates
        if artifact.product_date is not None
    })
    coverage_start = retained_candidate_dates[0] if retained_candidate_dates else None
    coverage_end = retained_candidate_dates[-1] if retained_candidate_dates else None
    missing_dates = []
    if coverage_start and coverage_end:
        cursor = coverage_start
        covered = set(ordered_dates)
        while cursor <= coverage_end:
            if cursor not in covered:
                missing_dates.append(cursor.isoformat())
            cursor += timedelta(days=1)
    invalid_within_coverage = sorted(
        represented_date.isoformat()
        for represented_date in invalid_dates
        if coverage_start and coverage_end and coverage_start <= represented_date <= coverage_end
    )
    missing_dates = sorted(set(missing_dates) | set(invalid_within_coverage))
    season_start, season_end = _season_bounds(season)

    return {
        'capability': CAPABILITY,
        'contract': CONTRACT,
        'status': STATUS_AVAILABLE if ordered_dates else STATUS_QUIET,
        'team': {
            **team,
            'team_board_href': f'/bullpen?view=board&team={team["team_abbreviation"]}',
        },
        'season': season,
        'coverage': {
            'start': coverage_start.isoformat() if coverage_start else None,
            'end': coverage_end.isoformat() if coverage_end else None,
            'covered_date_count': len(ordered_dates),
            'missing_dates': missing_dates,
            'is_partial': bool(
                not ordered_dates
                or missing_dates
                or coverage_start > season_start
                or coverage_end < season_end
            ),
        },
        'rows': [rows_by_date[represented_date] for represented_date in reversed(ordered_dates)],
        'limitations': [
            'History includes only retained, integrity-verified Team State publications. Missing dates are not backfilled.'
        ],
    }


__all__ = ['CAPABILITY', 'CONTRACT', 'build_team_state_history']
