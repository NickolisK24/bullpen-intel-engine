from sqlalchemy import event

from utils.db import db
from utils.time import utc_now_naive


class TonightPublicationImmutable(RuntimeError):
    """A stored Tonight projection is never rewritten in place."""


class TonightPublication(db.Model):
    """One immutable Tonight read model bound to one trusted Dashboard snapshot.

    Separate from ``tonight_intelligence_snapshots`` on purpose: that legacy
    table is keyed by (reference_date, snapshot_version) and overwritten in
    place, while a ``tonight_v1`` row is written once per exact publication
    identity (reference_date, dashboard_snapshot_id, contract) and never
    updated. ``content_sha256`` covers the payload without its generation
    timestamp, so a deterministic rebuild of the same publication is
    recognisable as identical.
    """

    __tablename__ = 'tonight_publications'

    __table_args__ = (
        db.UniqueConstraint(
            'reference_date', 'dashboard_snapshot_id', 'contract',
            name='uq_tonight_publications_identity',
        ),
        db.Index('ix_tonight_publications_contract', 'contract'),
        db.Index('ix_tonight_publications_reference_date', 'reference_date'),
        db.Index('ix_tonight_publications_dashboard_snapshot_id', 'dashboard_snapshot_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    contract = db.Column(db.String(40), nullable=False)
    reference_date = db.Column(db.Date, nullable=False)
    dashboard_snapshot_id = db.Column(
        db.Integer, db.ForeignKey('dashboard_snapshots.id'), nullable=False,
    )
    sync_run_id = db.Column(db.Integer, nullable=True)
    data_through = db.Column(db.Date, nullable=False)
    availability_reference_date = db.Column(db.Date, nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    content_sha256 = db.Column(db.String(64), nullable=False)
    generated_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)


@event.listens_for(TonightPublication, 'before_update')
def _refuse_update(_mapper, _connection, target):
    raise TonightPublicationImmutable(
        f'tonight publication {target.id} is immutable'
    )
