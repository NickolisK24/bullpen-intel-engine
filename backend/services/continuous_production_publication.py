"""Initial production publication adapter for continuous finalized-game updates.

The incremental chain owns acquisition and bounded recomputation.  For the
first public release, publication deliberately reuses the proven full Dashboard
snapshot writer instead of introducing a second serving format.  This is less
efficient than a future payload-level merge, but it makes the real Team Board
authority current with the smallest operational change.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from services import dashboard_snapshot
from services.availability_reference_date import product_current_date
from services.tonight_intelligence_snapshot import (
    generate_tonight_snapshot_for_date,
)


PUBLICATION_SOURCE = 'continuous_update'


@dataclass(frozen=True)
class ContinuousProductionPublicationResult:
    status: str
    reason_code: str
    committed: bool = False
    previous_publication_id: int | None = None
    new_publication_id: int | None = None
    cache_handoff_status: str = 'not_attempted'
    errors: tuple = ()

    def to_dict(self):
        value = asdict(self)
        value['errors'] = list(self.errors)
        return value


def current_publication_id():
    snapshot = dashboard_snapshot.get_latest_valid_dashboard_snapshot()
    return snapshot.id if snapshot is not None else None


def publish_continuous_update(
    _read_models,
    *,
    source_identity,
    source_order,
    sync_run_id,
    expected_current_id,
    cache_adapter=None,
):
    """Publish one complete serving snapshot after a bounded continuous cycle."""
    del source_identity, source_order, cache_adapter
    current_id = current_publication_id()
    if current_id != expected_current_id:
        return ContinuousProductionPublicationResult(
            status='conflict',
            reason_code='expected_current_mismatch',
            previous_publication_id=current_id,
        )

    snapshot = dashboard_snapshot.build_bullpen_dashboard_snapshot(
        sync_run_id=sync_run_id,
        source=PUBLICATION_SOURCE,
        publish=True,
        commit=True,
        raise_errors=True,
        publication_critical_complete=True,
    )
    if snapshot is None or not snapshot.is_published:
        return ContinuousProductionPublicationResult(
            status='withheld',
            reason_code=(
                getattr(snapshot, 'error_message', None)
                or 'dashboard_snapshot_not_published'
            ),
            previous_publication_id=current_id,
            new_publication_id=getattr(snapshot, 'id', None),
        )

    cache_status = 'complete'
    errors = ()
    try:
        generate_tonight_snapshot_for_date(
            product_current_date(),
            source=PUBLICATION_SOURCE,
        )
    except Exception as exc:  # Dashboard authority is already durable.
        cache_status = 'retry_required'
        errors = (type(exc).__name__,)

    return ContinuousProductionPublicationResult(
        status='committed',
        reason_code='production_snapshot_published',
        committed=True,
        previous_publication_id=current_id,
        new_publication_id=snapshot.id,
        cache_handoff_status=cache_status,
        errors=errors,
    )
