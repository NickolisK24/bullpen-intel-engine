from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from sqlalchemy import text

from models.game_log import GameLog
from utils.innings import classify_existing_decimal_innings, outs_to_decimal_innings


@dataclass
class InningsBackfillStats:
    total_rows: int = 0
    rows_converted: int = 0
    rows_decimal_corrected: int = 0
    rows_already_canonical: int = 0
    rows_missing: int = 0
    rows_flagged_anomalous: int = 0
    aggregate_ip_before: float = 0.0
    aggregate_ip_after: float = 0.0
    anomalous_examples: list[dict] = field(default_factory=list)

    def to_dict(self):
        payload = asdict(self)
        payload['aggregate_ip_before'] = round(float(self.aggregate_ip_before), 6)
        payload['aggregate_ip_after'] = round(float(self.aggregate_ip_after), 6)
        return payload


def _numeric(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _canonical_for_existing_outs(log):
    outs = getattr(log, 'innings_pitched_outs', None)
    if outs is None:
        return None
    try:
        parsed = int(outs)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed, outs_to_decimal_innings(parsed)


def _has_raw_mlb_fraction(value, *, tolerance=1e-6):
    numeric = _numeric(value)
    if numeric is None:
        return False
    whole = math.floor(numeric + tolerance)
    fraction = numeric - whole
    return (
        math.isclose(fraction, 0.1, abs_tol=tolerance)
        or math.isclose(fraction, 0.2, abs_tol=tolerance)
    )


def count_raw_mlb_fraction_rows(session) -> int:
    count = 0
    for (value,) in session.query(GameLog.innings_pitched).all():
        if _has_raw_mlb_fraction(value):
            count += 1
    return count


def _apply_postgres_set_based(session, *, tolerance=1e-6):
    session.execute(text('SET LOCAL statement_timeout = 0'))
    session.execute(text(
        """
        WITH classified AS (
            SELECT
                id,
                CASE
                    WHEN abs((innings_pitched - floor(innings_pitched + :tol)) - 0.0) < :tol
                        THEN floor(innings_pitched + :tol)::integer * 3
                    WHEN abs((innings_pitched - floor(innings_pitched + :tol)) - 0.1) < :tol
                        THEN floor(innings_pitched + :tol)::integer * 3 + 1
                    WHEN abs((innings_pitched - floor(innings_pitched + :tol)) - 0.2) < :tol
                        THEN floor(innings_pitched + :tol)::integer * 3 + 2
                    WHEN abs((innings_pitched - floor(innings_pitched + :tol)) - (1.0 / 3.0)) < :tol
                        THEN floor(innings_pitched + :tol)::integer * 3 + 1
                    WHEN abs((innings_pitched - floor(innings_pitched + :tol)) - (2.0 / 3.0)) < :tol
                        THEN floor(innings_pitched + :tol)::integer * 3 + 2
                    ELSE NULL
                END AS outs
            FROM game_logs
            WHERE innings_pitched IS NOT NULL
        )
        UPDATE game_logs AS target
        SET
            innings_pitched_outs = classified.outs,
            innings_pitched = classified.outs / 3.0
        FROM classified
        WHERE target.id = classified.id
          AND classified.outs IS NOT NULL
          AND (
              target.innings_pitched_outs IS DISTINCT FROM classified.outs
              OR abs(target.innings_pitched - classified.outs / 3.0) > :tol
          )
        """
    ), {'tol': tolerance})
    session.commit()


def backfill_game_log_innings_outs(
    session,
    *,
    apply: bool = False,
    anomaly_limit: int = 20,
    batch_size: int = 1000,
) -> InningsBackfillStats:
    stats = InningsBackfillStats()
    logs = session.query(GameLog).order_by(GameLog.id).all()
    updates = []
    use_postgres_apply = (
        apply
        and session.get_bind() is not None
        and session.get_bind().dialect.name == 'postgresql'
    )

    def flush_updates():
        nonlocal updates
        if not apply or not updates:
            return
        session.bulk_update_mappings(GameLog, updates)
        session.commit()
        updates = []

    for log in logs:
        stats.total_rows += 1
        before = _numeric(log.innings_pitched)
        if before is not None:
            stats.aggregate_ip_before += before

        existing = _canonical_for_existing_outs(log)
        if existing is not None:
            _outs, canonical = existing
            if before is not None and math.isclose(before, canonical, abs_tol=1e-6):
                stats.rows_already_canonical += 1
                stats.aggregate_ip_after += canonical
                continue

        classification = classify_existing_decimal_innings(log.innings_pitched)
        if classification.state == 'missing':
            stats.rows_missing += 1
            continue
        if classification.state == 'anomalous':
            stats.rows_flagged_anomalous += 1
            if len(stats.anomalous_examples) < anomaly_limit:
                stats.anomalous_examples.append({
                    'id': log.id,
                    'pitcher_id': log.pitcher_id,
                    'mlb_game_pk': log.mlb_game_pk,
                    'innings_pitched': log.innings_pitched,
                })
            if before is not None:
                stats.aggregate_ip_after += before
            continue

        canonical = outs_to_decimal_innings(classification.outs)
        stats.aggregate_ip_after += canonical

        if classification.state == 'canonical':
            stats.rows_already_canonical += 1
            should_update = log.innings_pitched_outs != classification.outs
        else:
            stats.rows_converted += 1
            decimal_changed = before is None or not math.isclose(before, canonical, abs_tol=1e-6)
            if decimal_changed:
                stats.rows_decimal_corrected += 1
            should_update = (
                log.innings_pitched_outs != classification.outs
                or decimal_changed
            )

        if apply and should_update and not use_postgres_apply:
            updates.append({
                'id': log.id,
                'innings_pitched_outs': classification.outs,
                'innings_pitched': canonical,
            })
            if len(updates) >= batch_size:
                flush_updates()

    if apply:
        if use_postgres_apply:
            _apply_postgres_set_based(session)
        else:
            flush_updates()
    else:
        session.rollback()

    return stats
