"""Idempotent completion of League Board Team State artifacts.

The trusted Dashboard receipt is the baseball authority.  This service only
projects that immutable receipt into the already-governed published Share
Artifact contract consumed by the League Board.  It never recalculates Team
State from mutable roster or GameLog rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from models.share_artifact import (
    LIFECYCLE_PUBLISHED,
    SUBJECT_TYPE_LEAGUE_SNAPSHOT,
    SUBJECT_TYPE_TEAM_PROGRESSIVE,
)
from services.mlb_club_directory import MLB_TEAM_IDS
from services.published_team_state import project_published_team_state_artifact
from services.share_artifact_repository import list_team_state_artifacts_for_snapshot
from services.team_board_snapshot_team_state import receipt_value
from services.team_state_public_vocabulary import PUBLIC_STATE_LABELS


class LeagueTeamStateArtifactRecoveryError(RuntimeError):
    """The current trusted snapshot cannot supply complete League Board reads."""


@dataclass(frozen=True)
class LeagueTeamStateArtifactRecoveryResult:
    snapshot_id: int
    sync_run_id: int
    outcome: str
    artifact_count: int
    team_ids: tuple[int, ...]
    generated_count: int = 0
    reused_count: int = 0

    def to_dict(self):
        return {
            'snapshot_id': self.snapshot_id,
            'sync_run_id': self.sync_run_id,
            'outcome': self.outcome,
            'artifact_count': self.artifact_count,
            'team_ids': list(self.team_ids),
            'generated_count': self.generated_count,
            'reused_count': self.reused_count,
        }


def _published_by_team(snapshot, *, session=None):
    artifacts = list_team_state_artifacts_for_snapshot(
        snapshot.id,
        lifecycle_state=LIFECYCLE_PUBLISHED,
        exclude_subject_type=SUBJECT_TYPE_TEAM_PROGRESSIVE,
        session=session,
    )
    by_team = {}
    for artifact in artifacts:
        if getattr(artifact, 'subject_type', None) != SUBJECT_TYPE_LEAGUE_SNAPSHOT:
            raise LeagueTeamStateArtifactRecoveryError(
                'league_team_state_artifact_subject_type_mismatch'
            )
        team_id = int(artifact.team_id)
        if team_id in by_team:
            raise LeagueTeamStateArtifactRecoveryError(
                'league_team_state_artifact_duplicate_team'
            )
        by_team[team_id] = artifact
    return by_team


def require_complete_artifact_set(snapshot, *, session=None):
    """Require exact canonical, snapshot-bound artifacts matching frozen receipts."""
    expected = set(MLB_TEAM_IDS)
    by_team = _published_by_team(snapshot, session=session)
    if set(by_team) != expected:
        raise LeagueTeamStateArtifactRecoveryError(
            'league_team_state_artifact_set_incomplete'
        )

    for team_id in MLB_TEAM_IDS:
        artifact = by_team[team_id]
        if (
            artifact.source_snapshot_id != snapshot.id
            or artifact.source_sync_run_id != snapshot.sync_run_id
            or artifact.product_date != snapshot.data_through
        ):
            raise LeagueTeamStateArtifactRecoveryError(
                'league_team_state_artifact_identity_mismatch'
            )
        present, receipt = receipt_value(snapshot, team_id)
        if not present or not isinstance(receipt, dict) or receipt.get('available') is not True:
            raise LeagueTeamStateArtifactRecoveryError(
                'league_team_state_receipt_unavailable'
            )
        projected = project_published_team_state_artifact(
            artifact, data_through=snapshot.data_through,
        )
        if any((
            projected.get('available') is not True,
            projected.get('public_state') not in PUBLIC_STATE_LABELS,
            projected.get('public_state') != receipt.get('public_state'),
            projected.get('public_label') != receipt.get('public_label'),
            projected.get('data_through') != receipt.get('data_through'),
        )):
            raise LeagueTeamStateArtifactRecoveryError(
                'league_team_state_artifact_receipt_mismatch'
            )
    return by_team


def repair_current_snapshot_artifacts(snapshot, *, session=None, generator=None):
    """Complete a missing set once; a complete set is a zero-write no-op."""
    if (
        snapshot is None
        or not getattr(snapshot, 'is_published', False)
        or getattr(snapshot, 'status', None) != 'ready'
        or getattr(snapshot, 'sync_run_id', None) is None
    ):
        raise LeagueTeamStateArtifactRecoveryError(
            'league_team_state_snapshot_not_trusted'
        )

    try:
        by_team = require_complete_artifact_set(snapshot, session=session)
    except LeagueTeamStateArtifactRecoveryError as exc:
        if str(exc) != 'league_team_state_artifact_set_incomplete':
            raise
    else:
        return LeagueTeamStateArtifactRecoveryResult(
            snapshot.id, snapshot.sync_run_id, 'already_complete',
            len(by_team), tuple(sorted(by_team)),
        )

    from services.share_artifact_publication_hook import run_post_publication_generation
    from services.team_state_vnext_production_proof import (
        frozen_team_state_artifact_generator,
    )

    batch = run_post_publication_generation(
        snapshot,
        generator=frozen_team_state_artifact_generator(snapshot, generator),
    )
    if batch is None or batch.failed_count or batch.refused_count or batch.missing_count:
        raise LeagueTeamStateArtifactRecoveryError(
            'league_team_state_artifact_generation_incomplete'
        )
    by_team = require_complete_artifact_set(snapshot, session=session)
    return LeagueTeamStateArtifactRecoveryResult(
        snapshot.id, snapshot.sync_run_id, 'repaired', len(by_team),
        tuple(sorted(by_team)), batch.generated_count, batch.reused_count,
    )
