"""Reusable provenance helpers for source-backed storage.

Phase 0C storage branches should carry source provenance from the start. This
module provides a small SQLAlchemy mixin for new tables plus helper functions
that can serialize or update equivalent provenance fields on existing models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from utils.db import db
from utils.time import utc_now_naive


@dataclass(frozen=True)
class SourceProvenance:
    source: str | None
    sync_run_id: int | None = None
    first_seen_at: datetime | None = None
    last_corrected_at: datetime | None = None
    correction_count: int = 0
    correction_source: str | None = None

    def to_dict(self) -> dict:
        return {
            'source': self.source,
            'sync_run_id': self.sync_run_id,
            'first_seen_at': _iso(self.first_seen_at),
            'last_corrected_at': _iso(self.last_corrected_at),
            'correction_count': self.correction_count or 0,
            'correction_source': self.correction_source,
        }


class SourceProvenanceMixin:
    """Column mixin for future source-backed tables.

    Existing Phase 0A tables are not rewritten to inherit this mixin. New 0C
    tables can use it directly when these generic field names fit.
    """

    source = db.Column(db.String(40), nullable=False)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    last_corrected_at = db.Column(db.DateTime)
    correction_count = db.Column(db.Integer, nullable=False, default=0)
    correction_source = db.Column(db.String(40))


def source_provenance_from_record(
    record,
    *,
    source_attr='source',
    sync_run_attr='sync_run_id',
    first_seen_attr='first_seen_at',
    last_corrected_attr='last_corrected_at',
    correction_count_attr='correction_count',
    correction_source_attr='correction_source',
) -> SourceProvenance:
    return SourceProvenance(
        source=getattr(record, source_attr, None),
        sync_run_id=getattr(record, sync_run_attr, None),
        first_seen_at=getattr(record, first_seen_attr, None),
        last_corrected_at=getattr(record, last_corrected_attr, None),
        correction_count=getattr(record, correction_count_attr, 0) or 0,
        correction_source=getattr(record, correction_source_attr, None),
    )


def apply_initial_source_provenance(
    record,
    *,
    source: str,
    sync_run_id: int | None = None,
    first_seen_at: datetime | None = None,
) -> None:
    """Set initial provenance on a record without clobbering first_seen_at."""
    if hasattr(record, 'source'):
        record.source = source
    if hasattr(record, 'sync_run_id'):
        record.sync_run_id = sync_run_id
    if hasattr(record, 'first_seen_at') and getattr(record, 'first_seen_at', None) is None:
        record.first_seen_at = first_seen_at or utc_now_naive()


def record_source_correction(
    record,
    *,
    correction_source: str,
    sync_run_id: int | None = None,
    corrected_at: datetime | None = None,
) -> None:
    """Increment generic correction provenance fields when a source updates."""
    if hasattr(record, 'correction_count'):
        record.correction_count = (getattr(record, 'correction_count', 0) or 0) + 1
    if hasattr(record, 'last_corrected_at'):
        record.last_corrected_at = corrected_at or utc_now_naive()
    if hasattr(record, 'correction_source'):
        record.correction_source = correction_source
    if hasattr(record, 'sync_run_id'):
        record.sync_run_id = sync_run_id


def game_log_stat_correction_provenance(game_log) -> SourceProvenance:
    """Adapter for existing Phase 0A game-log correction provenance fields."""
    return SourceProvenance(
        source='game_logs',
        sync_run_id=getattr(game_log, 'last_stat_correction_sync_run_id', None),
        first_seen_at=getattr(game_log, 'created_at', None),
        last_corrected_at=getattr(game_log, 'last_stat_correction_at', None),
        correction_count=getattr(game_log, 'stat_correction_count', 0) or 0,
        correction_source=getattr(game_log, 'last_stat_correction_source', None),
    )


def provenance_ready(provenance: SourceProvenance) -> bool:
    return bool(provenance.source) and provenance.first_seen_at is not None


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
