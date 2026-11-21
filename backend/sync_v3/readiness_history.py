"""Historical Team State and constituent arm reads for a represented club."""

from sync_v3.intelligence_history import record_intelligence, rebuild_intelligence


def record_readiness(connection, team, through):
    return record_intelligence(connection, 'readiness', team, through)


def rebuild_readiness(connection, receipt):
    return rebuild_intelligence(connection, receipt, domains=('readiness',))
