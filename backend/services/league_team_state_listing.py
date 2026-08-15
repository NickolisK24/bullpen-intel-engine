"""Governed 30-club listing of already-published Team State artifacts (D-054).

This service selects one current trusted Dashboard snapshot, reads its published
Team State artifacts in one batch, and projects them through the existing public
Team State vocabulary. It computes no readiness, ranking, or selection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from models.share_artifact import LIFECYCLE_PUBLISHED, SUBJECT_TYPE_TEAM_PROGRESSIVE
from services import board_freshness
from services import dashboard_snapshot as dashboard_snapshot_service
from services import public_serving_authority
from services import sync_metadata
from services.mlb_club_directory import EXPECTED_CLUB_COUNT, MLB_CLUBS
from services.published_team_state import project_published_team_state_artifact
from services.share_artifact_repository import list_team_state_artifacts_for_snapshot
from services.team_directory import valid_team_directory
from services.team_state_public_vocabulary import (
    TEAM_STATE_READINESS_UNAVAILABLE,
    team_state_unavailable,
)


CAPABILITY = 'league_team_state_listing_v1'
VERSION = '1.0.0'
ORDERING_BASIS = 'team_name_then_team_id'
SNAPSHOT_READ_UNAVAILABLE = 'dashboard_snapshot_read_unavailable'
PUBLICATION_CONTEXT_MISMATCH = (
    'published_team_state_artifact_publication_context_mismatch'
)


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def resolve_current_trusted_dashboard_snapshot():
    """Resolve the existing Dashboard serving authority with guarded DB reads."""
    snapshot = dashboard_snapshot_service.get_latest_dashboard_snapshot_guarded()
    if snapshot is not None:
        reason = dashboard_snapshot_service.snapshot_unavailable_reason(snapshot)
        return (snapshot, None) if reason is None else (None, reason)

    latest_record = (
        dashboard_snapshot_service.get_latest_dashboard_snapshot_record_guarded()
    )
    return None, dashboard_snapshot_service.snapshot_unavailable_reason(latest_record)


def _live_directory(directory_loader):
    try:
        directory = directory_loader()
    except Exception:
        return {}
    return directory if isinstance(directory, Mapping) else {}


def _identity_rows(clubs, directory):
    rows = []
    for club in clubs:
        live = directory.get(club.team_id)
        live = live if isinstance(live, Mapping) else {}
        rows.append({
            'team_id': club.team_id,
            'team_abbreviation': (
                live.get('team_abbreviation') or club.abbreviation
            ),
            'team_name': live.get('team_name') or club.team_name,
        })
    return rows


def _artifact_sort_key(artifact):
    return (
        _iso(getattr(artifact, 'published_at', None)) or '',
        int(getattr(artifact, 'id', 0) or 0),
    )


def _artifact_by_team(artifacts, expected_team_ids):
    selected = {}
    ordered = sorted(artifacts or (), key=_artifact_sort_key, reverse=True)
    for artifact in ordered:
        if getattr(artifact, 'lifecycle_state', None) != LIFECYCLE_PUBLISHED:
            continue
        team_id = getattr(artifact, 'team_id', None)
        if team_id not in expected_team_ids or team_id in selected:
            continue
        selected[team_id] = artifact
    return selected


def _publication_context_matches(artifact, snapshot):
    if artifact is None:
        return True
    return (
        getattr(artifact, 'source_snapshot_id', None) == snapshot.id
        and getattr(artifact, 'source_sync_run_id', None) == snapshot.sync_run_id
    )


def _withheld_state(reason, *, data_through=None):
    return team_state_unavailable(
        TEAM_STATE_READINESS_UNAVAILABLE,
        data_through=_iso(data_through),
        reason_code=reason,
    )


def _row_state(artifact, snapshot):
    if not _publication_context_matches(artifact, snapshot):
        return _withheld_state(
            PUBLICATION_CONTEXT_MISMATCH,
            data_through=snapshot.data_through,
        )

    state = project_published_team_state_artifact(
        artifact,
        data_through=snapshot.data_through,
    )
    if state.get('available') and state.get('data_through') != _iso(snapshot.data_through):
        return _withheld_state(
            PUBLICATION_CONTEXT_MISMATCH,
            data_through=snapshot.data_through,
        )
    return state


def _freshness_for_snapshot(snapshot):
    freshness = board_freshness.published_snapshot_freshness_block(
        snapshot=snapshot,
        include_runtime_overlay=False,
    )
    freshness = dict(freshness or {})
    freshness.setdefault('data_through', _iso(snapshot.data_through))
    return freshness


def _envelope(*, rows, generated_at, status, reason, snapshot):
    represented = sum(1 for row in rows if row['team_state'].get('available'))
    team_count = len(rows)
    payload = {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'generated_at': generated_at,
        'status': status,
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'ordering_basis': ORDERING_BASIS,
        'expected_team_count': EXPECTED_CLUB_COUNT,
        'team_count': team_count,
        'represented_team_count': represented,
        'withheld_team_count': team_count - represented,
        'publication_authority': public_serving_authority.publication_authority(
            snapshot
        ),
        'freshness': (
            _freshness_for_snapshot(snapshot)
            if snapshot is not None
            else {
                'data_through': None,
                'freshness_state': sync_metadata.STATUS_METADATA_UNAVAILABLE,
                'reason_codes': [reason],
            }
        ),
        'teams': rows,
    }
    if reason is not None:
        payload['reason'] = reason
    return payload


def build_snapshot_unavailable_listing(
    reason,
    *,
    generated_at=None,
    clubs=MLB_CLUBS,
    directory_loader=valid_team_directory,
):
    """Build the complete fail-closed denominator without any artifact reads."""
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    identities = _identity_rows(clubs, _live_directory(directory_loader))
    rows = [
        {
            **identity,
            'team_state': _withheld_state(reason),
        }
        for identity in identities
    ]
    rows.sort(key=lambda row: (row['team_name'].casefold(), row['team_id']))
    return _envelope(
        rows=rows,
        generated_at=generated_at,
        status='snapshot_unavailable',
        reason=reason,
        snapshot=None,
    )


def build_league_team_state_listing(
    *,
    generated_at=None,
    clubs=MLB_CLUBS,
    snapshot_resolver=resolve_current_trusted_dashboard_snapshot,
    artifact_loader=list_team_state_artifacts_for_snapshot,
    directory_loader=valid_team_directory,
):
    """Build one complete, neutral listing from one publication context."""
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    snapshot, unavailable_reason = snapshot_resolver()
    if snapshot is None:
        return build_snapshot_unavailable_listing(
            unavailable_reason or 'dashboard_snapshot_missing',
            generated_at=generated_at,
            clubs=clubs,
            directory_loader=directory_loader,
        )

    directory = _live_directory(directory_loader)
    identities = _identity_rows(clubs, directory)
    expected_team_ids = {club.team_id for club in clubs}
    artifacts = artifact_loader(
        snapshot.id,
        lifecycle_state=LIFECYCLE_PUBLISHED,
        exclude_subject_type=SUBJECT_TYPE_TEAM_PROGRESSIVE,
    )
    selected = _artifact_by_team(artifacts, expected_team_ids)
    rows = [
        {
            **identity,
            'team_state': _row_state(selected.get(identity['team_id']), snapshot),
        }
        for identity in identities
    ]
    rows.sort(key=lambda row: (row['team_name'].casefold(), row['team_id']))
    return _envelope(
        rows=rows,
        generated_at=generated_at,
        status='ok',
        reason=None,
        snapshot=snapshot,
    )
