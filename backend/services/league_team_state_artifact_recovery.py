"""Idempotent completion of League Board Team State artifacts.

The trusted Dashboard receipt is the baseball authority.  This service only
projects that immutable receipt into the already-governed published Share
Artifact contract consumed by the League Board.  It never recalculates Team
State from mutable roster or GameLog rows.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from models.share_artifact import (
    LIFECYCLE_PUBLISHED,
    SUBJECT_TYPE_LEAGUE_SNAPSHOT,
    SUBJECT_TYPE_TEAM_PROGRESSIVE,
)
from services.mlb_club_directory import MLB_CLUBS, MLB_TEAM_IDS
from services.published_team_state import project_published_team_state_artifact
from services.share_artifact_repository import list_team_state_artifacts_for_snapshot
from services.team_board_snapshot_team_state import receipt_value
from services.team_state_public_vocabulary import PUBLIC_STATE_LABELS


class LeagueTeamStateArtifactRecoveryError(RuntimeError):
    """The current trusted snapshot cannot supply complete League Board reads."""

    def __init__(self, reason_code, *, result=None):
        self.reason_code = reason_code
        self.result = result
        message = reason_code
        if result is not None:
            histogram = ','.join(
                f'{key}:{value}' for key, value in result.reason_histogram
            ) or 'none'
            affected = ','.join(str(team_id) for team_id in result.affected_team_ids)
            message = (
                f'{reason_code}:generated={result.generated_count}:'
                f'reused={result.reused_count}:failed={result.failed_count}:'
                f'refused={result.refused_count}:missing={result.missing_count}:'
                f'reasons={histogram}:teams=[{affected}]'
            )
        super().__init__(message)


@dataclass(frozen=True)
class LeagueTeamStateArtifactTerminalOutcome:
    team_id: int
    team_abbreviation: str
    outcome: str
    reason_code: str | None
    exception_class: str | None
    exception_message: str | None
    source_snapshot_id: int | None
    source_sync_run_id: int | None
    product_date: object | None
    receipt_available: bool
    receipt_public_state: str | None

    def to_dict(self):
        return {
            'team_id': self.team_id,
            'team_abbreviation': self.team_abbreviation,
            'outcome': self.outcome,
            'reason_code': self.reason_code,
            'exception_class': self.exception_class,
            'exception_message': self.exception_message,
            'source_snapshot_id': self.source_snapshot_id,
            'source_sync_run_id': self.source_sync_run_id,
            'product_date': (
                self.product_date.isoformat()
                if hasattr(self.product_date, 'isoformat') else self.product_date
            ),
            'receipt_available': self.receipt_available,
            'receipt_public_state': self.receipt_public_state,
        }


@dataclass(frozen=True)
class LeagueTeamStateArtifactRecoveryResult:
    snapshot_id: int
    sync_run_id: int
    outcome: str
    artifact_count: int
    team_ids: tuple[int, ...]
    generated_count: int = 0
    reused_count: int = 0
    failed_count: int = 0
    refused_count: int = 0
    missing_count: int = 0
    reason_histogram: tuple = ()
    terminal_outcomes: tuple = ()

    @property
    def affected_team_ids(self):
        return tuple(
            item.team_id for item in self.terminal_outcomes
            if item.outcome in {'failed', 'refused', 'missing'}
        )

    def to_dict(self):
        return {
            'snapshot_id': self.snapshot_id,
            'sync_run_id': self.sync_run_id,
            'outcome': self.outcome,
            'artifact_count': self.artifact_count,
            'team_ids': list(self.team_ids),
            'generated_count': self.generated_count,
            'reused_count': self.reused_count,
            'failed_count': self.failed_count,
            'refused_count': self.refused_count,
            'missing_count': self.missing_count,
            'reason_histogram': dict(self.reason_histogram),
            'affected_team_ids': list(self.affected_team_ids),
            'terminal_outcomes': [item.to_dict() for item in self.terminal_outcomes],
        }


_ABBREVIATION_BY_TEAM_ID = {
    club.team_id: club.abbreviation for club in MLB_CLUBS
}


def _batch_recovery_result(snapshot, batch, *, artifact_count=0):
    by_team = {item.team_id: item for item in (batch.results if batch else ())}
    outcomes = []
    reasons = Counter()
    for team_id in MLB_TEAM_IDS:
        item = by_team.get(team_id)
        present, receipt = receipt_value(snapshot, team_id)
        receipt_available = bool(
            present and isinstance(receipt, dict) and receipt.get('available') is True
        )
        if item is None:
            outcome = 'missing'
            reason_code = 'missing_terminal_result'
            exception_class = exception_message = None
            source_snapshot_id = source_sync_run_id = product_date = None
        else:
            outcome = item.outcome
            reason_code = item.reason_code or item.failure_code
            exception_class = item.exception_class
            exception_message = item.exception_message
            source_snapshot_id = item.source_snapshot_id
            source_sync_run_id = getattr(item, 'source_sync_run_id', None)
            product_date = item.product_date
        if outcome in {'failed', 'refused', 'missing'}:
            reasons[reason_code or 'unspecified'] += 1
        outcomes.append(LeagueTeamStateArtifactTerminalOutcome(
            team_id=team_id,
            team_abbreviation=_ABBREVIATION_BY_TEAM_ID[team_id],
            outcome=outcome,
            reason_code=reason_code,
            exception_class=exception_class,
            exception_message=exception_message,
            source_snapshot_id=source_snapshot_id or snapshot.id,
            source_sync_run_id=source_sync_run_id or snapshot.sync_run_id,
            product_date=product_date or snapshot.data_through,
            receipt_available=receipt_available,
            receipt_public_state=(
                receipt.get('public_state') if isinstance(receipt, dict) else None
            ),
        ))
    return LeagueTeamStateArtifactRecoveryResult(
        snapshot.id,
        snapshot.sync_run_id,
        'generation_incomplete' if reasons else 'repaired',
        artifact_count,
        tuple(sorted(item.team_id for item in outcomes if item.outcome in {'generated', 'reused'})),
        batch.generated_count if batch else 0,
        batch.reused_count if batch else 0,
        batch.failed_count if batch else 0,
        batch.refused_count if batch else 0,
        batch.missing_count if batch else len(MLB_TEAM_IDS),
        tuple(sorted(reasons.items())),
        tuple(outcomes),
    )


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
    try:
        artifact_count = len(_published_by_team(snapshot, session=session))
    except LeagueTeamStateArtifactRecoveryError:
        artifact_count = 0
    batch_result = _batch_recovery_result(
        snapshot, batch, artifact_count=artifact_count,
    )
    if batch is None or batch.failed_count or batch.refused_count or batch.missing_count:
        raise LeagueTeamStateArtifactRecoveryError(
            'league_team_state_artifact_generation_incomplete',
            result=batch_result,
        )
    by_team = require_complete_artifact_set(snapshot, session=session)
    return LeagueTeamStateArtifactRecoveryResult(
        snapshot.id, snapshot.sync_run_id, 'repaired', len(by_team),
        tuple(sorted(by_team)), batch.generated_count, batch.reused_count,
        terminal_outcomes=batch_result.terminal_outcomes,
    )
