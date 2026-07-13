from datetime import date, timedelta

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_run import SyncRun
from services.roster_status import STATUS_ACTIVE, STATUS_UNKNOWN
from utils.db import db
from utils.time import utc_now_naive


def seed_roster_readiness_snapshots(snapshot_dates=None):
    """Add official-roster readiness rows for tests that expect ready counts."""
    pitchers = (
        Pitcher.query
        .filter(Pitcher.active == True)
        .filter(Pitcher.team_id.isnot(None))
        .all()
    )
    dates = _snapshot_dates(snapshot_dates)
    pending = [
        (pitcher, snapshot_date)
        for pitcher in pitchers
        for snapshot_date in dates
        if not RosterStatusSnapshot.query.filter_by(
            pitcher_id=pitcher.id,
            snapshot_date=snapshot_date,
        ).first()
    ]
    if not pending:
        return

    timestamp = utc_now_naive()
    sync_run_id = db.session.query(db.func.max(SyncRun.id)).scalar() or 0

    for pitcher, snapshot_date in pending:
        status = pitcher.roster_status or STATUS_UNKNOWN
        source = pitcher.roster_status_source or 'mlb_stats_api:roster_sync:unavailable'
        if pitcher.roster_status is None:
            pitcher.roster_status = STATUS_UNKNOWN
            pitcher.roster_status_source = source
            pitcher.roster_status_updated_at = pitcher.roster_status_updated_at or timestamp
        db.session.add(RosterStatusSnapshot(
            pitcher_id=pitcher.id,
            mlb_id=pitcher.mlb_id,
            team_id=pitcher.team_id,
            snapshot_date=snapshot_date,
            roster_status=status,
            active_roster=status == STATUS_ACTIVE,
            forty_man_roster=True,
            roster_status_raw_code=pitcher.roster_status_raw_code,
            roster_status_raw_description=pitcher.roster_status_raw_description,
            source=source,
            sync_run_id=sync_run_id,
            first_seen_at=timestamp,
            updated_at=timestamp,
        ))
    db.session.commit()


def _snapshot_dates(extra_dates=None):
    dates = {date.today()}
    latest_game_date = db.session.query(db.func.max(GameLog.game_date)).scalar()
    if latest_game_date is not None:
        dates.add(latest_game_date)
        dates.add(latest_game_date + timedelta(days=1))
    for snapshot_date in extra_dates or ():
        if snapshot_date is not None:
            dates.add(snapshot_date)
    return dates
