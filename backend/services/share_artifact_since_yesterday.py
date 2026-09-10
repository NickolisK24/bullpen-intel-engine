"""Immutable ShareArtifact publication for one governed Since Yesterday change."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from models.share_artifact import LIFECYCLE_PUBLISHED, ShareArtifact
from services.share_artifacts import publish_new_share_artifact, supersede_share_artifact
from services.what_changed_comparison_identity import (
    ComparisonIdentityInvalid,
    comparison_identity_from_payload,
    normalize_comparison_identity,
    resolve_snapshot_pair,
    validate_snapshot_pair,
)
from utils.db import db


ARTIFACT_TYPE = 'since_yesterday_change'
RENDER_VERSION = 'since-yesterday-change-1.1.0'
SUBJECT_TYPE = 'since_yesterday_change'
SOURCE = 'what_changed_since_yesterday_public_v1'


class SinceYesterdayArtifactUnavailable(Exception):
    """Raised when an exact governed public change cannot be cited."""


def _iso(value):
    return value.isoformat() if value is not None else None


def _as_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _mapping(value) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _public_item(snapshot, team_id: int, comparison_identity: Mapping) -> tuple[dict, list]:
    block = _mapping(_mapping(snapshot.payload).get('what_changed_since_yesterday'))
    comparison = _mapping(block.get('comparison'))
    if (
        block.get('state') != 'changes_detected'
        or comparison.get('comparison_available') is not True
        or comparison_identity_from_payload(snapshot.payload)
            != normalize_comparison_identity(comparison_identity)
    ):
        raise SinceYesterdayArtifactUnavailable('comparison_unavailable')
    for item in block.get('items') or ():
        if isinstance(item, Mapping) and str(item.get('team_id')) == str(team_id):
            return dict(item), list(block.get('limitations') or ())
    raise SinceYesterdayArtifactUnavailable('team_change_unavailable')


def _evidence(item: Mapping[str, Any]) -> list[dict]:
    frozen = []
    for index, evidence in enumerate(item.get('public_evidence') or ()):
        if not isinstance(evidence, Mapping):
            continue
        snapshot = {
            'label': evidence.get('label'),
            'yesterday': evidence.get('yesterday'),
            'today': evidence.get('today'),
        }
        frozen.append({
            'evidence_key': f'since-yesterday:{index}:{snapshot["label"] or "fact"}',
            'role': 'supporting_evidence',
            'claim': snapshot['label'],
            'completeness_state': 'complete',
            'snapshot': snapshot,
        })
    return frozen


def _payload(
    *, current_snapshot, prior_snapshot, team_id: int,
    item: Mapping[str, Any], limitations: list, comparison_identity: Mapping,
) -> dict:
    team = {
        'team_id': team_id,
        'team_name': item.get('team_name'),
        'team_abbreviation': item.get('team_abbreviation'),
    }
    authority = {
        'current_snapshot_id': current_snapshot.id,
        'prior_snapshot_id': prior_snapshot.id,
        'current_data_through': _iso(current_snapshot.data_through),
        'previous_data_through': _iso(prior_snapshot.data_through),
        'current_published_at': _iso(current_snapshot.published_at),
        'previous_published_at': _iso(prior_snapshot.published_at),
        'change_capability': 'what_changed_since_yesterday_public_v1',
        'comparison_identity': normalize_comparison_identity(comparison_identity),
    }
    change = {
        key: item.get(key)
        for key in (
            'movement_lane', 'movement_label', 'primary_delta',
            'public_headline', 'public_summary', 'public_context',
            'yesterday_rested_count', 'today_rested_count', 'workload_added',
        )
    }
    evidence = [entry['snapshot'] for entry in _evidence(item)]
    return {
        'payload_version': RENDER_VERSION,
        'team': team,
        'authority': authority,
        'change': change,
        'evidence': evidence,
        'limitations': limitations,
        'public_copy': {
            'headline': item.get('public_headline'),
            'summary': item.get('public_summary'),
            'why': item.get('public_context'),
            'description': item.get('public_summary'),
            'alt_text': item.get('public_headline'),
        },
    }


def publish_since_yesterday_change(
    team_id: int,
    *,
    comparison_identity,
    session=None,
    current_snapshot=None,
    prior_snapshot=None,
):
    """Publish the exact governed comparison identity already shown to readers."""
    session = session or db.session
    try:
        if current_snapshot is None or prior_snapshot is None:
            prior_snapshot, current_snapshot, identity = resolve_snapshot_pair(
                comparison_identity,
                session=session,
            )
        else:
            identity = validate_snapshot_pair(
                comparison_identity,
                prior_snapshot,
                current_snapshot,
            )
    except ComparisonIdentityInvalid as exc:
        raise SinceYesterdayArtifactUnavailable(str(exc)) from exc
    current_date = _as_date(identity['current_data_through'])
    prior_date = _as_date(identity['previous_data_through'])

    item, limitations = _public_item(current_snapshot, team_id, identity)
    payload = _payload(
        current_snapshot=current_snapshot,
        prior_snapshot=prior_snapshot,
        team_id=team_id,
        item=item,
        limitations=limitations,
        comparison_identity=identity,
    )
    artifact = publish_new_share_artifact(
        artifact_type=ARTIFACT_TYPE,
        render_version=RENDER_VERSION,
        team_id=team_id,
        source_snapshot_id=current_snapshot.id,
        source_sync_run_id=current_snapshot.sync_run_id,
        subject_type=SUBJECT_TYPE,
        subject_key=f'team:{team_id}:prior:{prior_snapshot.id}:current:{current_snapshot.id}',
        product_date=current_date,
        payload=payload,
        evidence=_evidence(item),
        trust_metadata={
            'comparison_available': True,
            'current_snapshot_id': current_snapshot.id,
            'prior_snapshot_id': prior_snapshot.id,
        },
        source=SOURCE,
        session=session,
    )
    # A corrected same-date publication produces a new immutable citation. Link
    # it as the replacement for any older active citation of the exact same
    # team/date pair; never mutate or silently redirect the original.
    candidates = (
        session.query(ShareArtifact)
        .filter(
            ShareArtifact.artifact_type == ARTIFACT_TYPE,
            ShareArtifact.subject_type == SUBJECT_TYPE,
            ShareArtifact.team_id == team_id,
            ShareArtifact.product_date == current_date,
            ShareArtifact.lifecycle_state == LIFECYCLE_PUBLISHED,
            ShareArtifact.id != artifact.id,
        )
        .all()
    )
    for previous in candidates:
        prior_authority = _mapping(_mapping(previous.payload).get('authority'))
        if (
            _as_date(prior_authority.get('current_data_through')) == current_date
            and _as_date(prior_authority.get('previous_data_through')) == prior_date
        ):
            supersede_share_artifact(
                previous,
                artifact,
                relation_metadata={'reason': 'corrected_source_publication'},
                session=session,
            )
    session.commit()
    return artifact


def publish_since_yesterday_changes_for_snapshot(current_snapshot, *, session=None) -> list:
    """Publish every governed team change carried by one trusted snapshot.

    This is called only by the post-publication artifact hook. The frozen public
    comparison block remains the semantic owner; this function only binds each
    item to its exact adjacent trusted snapshot pair and existing artifact
    lifecycle.
    """
    session = session or db.session
    if current_snapshot is None or not getattr(current_snapshot, 'is_published', False):
        raise SinceYesterdayArtifactUnavailable('current_snapshot_unpublished')
    block = _mapping(_mapping(current_snapshot.payload).get('what_changed_since_yesterday'))
    comparison = _mapping(block.get('comparison'))
    identity = comparison_identity_from_payload(current_snapshot.payload)
    if (
        block.get('state') != 'changes_detected'
        or comparison.get('comparison_available') is not True
        or identity is None
    ):
        return []
    try:
        prior_snapshot, resolved_current, identity = resolve_snapshot_pair(
            identity,
            session=session,
        )
    except ComparisonIdentityInvalid as exc:
        raise SinceYesterdayArtifactUnavailable(str(exc)) from exc
    if resolved_current.id != current_snapshot.id:
        raise SinceYesterdayArtifactUnavailable('comparison_current_snapshot_mismatch')

    artifacts = []
    for item in block.get('items') or ():
        if not isinstance(item, Mapping):
            continue
        try:
            team_id = int(item.get('team_id'))
        except (TypeError, ValueError):
            continue
        artifacts.append(publish_since_yesterday_change(
            team_id,
            comparison_identity=identity,
            session=session,
            current_snapshot=current_snapshot,
            prior_snapshot=prior_snapshot,
        ))
    return artifacts


__all__ = [
    'ARTIFACT_TYPE',
    'RENDER_VERSION',
    'SUBJECT_TYPE',
    'SinceYesterdayArtifactUnavailable',
    'publish_since_yesterday_change',
    'publish_since_yesterday_changes_for_snapshot',
]
