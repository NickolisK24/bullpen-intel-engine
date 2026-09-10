"""Exact-date roster evidence for identities acquired during transaction sync.

This closes only the roster-before-transaction ordering gap. It never scans
existing canonical pitchers, replays a historical range, reads nearest dates,
or derives ownership from the mutable ``Pitcher.team_id`` cache.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import logging

from services.roster_status_sync import (
    ROSTER_TYPES,
    build_exact_date_team_roster_status_index,
    persist_missing_exact_roster_status_snapshots,
)


logger = logging.getLogger(__name__)


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _coerce_date(value):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().split('T', 1)[0]
    for pattern in ('%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _is_mlb_team(team_id, transaction_date, team_metadata_by_season):
    if team_id is None or transaction_date is None:
        return False
    metadata = (team_metadata_by_season or {}).get(transaction_date.year) or {}
    team = metadata.get(team_id) or {}
    return _positive_int(team.get('sport_id')) == 1


def acquire_exact_transaction_roster_evidence(
    *,
    transactions,
    eligible_mlb_ids,
    pitchers_by_mlb_id,
    team_metadata_by_season,
    client,
    timestamp,
    sync_run_id=None,
):
    """Acquire exact-date endpoint evidence for an explicitly bounded identity set."""
    eligible = {
        value
        for value in (_positive_int(raw) for raw in eligible_mlb_ids or ())
        if value is not None and value in (pitchers_by_mlb_id or {})
    }
    targets_by_pair = defaultdict(set)
    eligible_identity_dates = set()
    for transaction in transactions or ():
        if not isinstance(transaction, dict):
            continue
        mlb_id = _positive_int(transaction.get('player_mlb_id'))
        transaction_date = _coerce_date(transaction.get('transaction_date'))
        if mlb_id not in eligible or transaction_date is None:
            continue
        endpoint_added = False
        for raw_team_id in (
            transaction.get('from_team_id'),
            transaction.get('to_team_id'),
        ):
            team_id = _positive_int(raw_team_id)
            if _is_mlb_team(
                team_id,
                transaction_date,
                team_metadata_by_season,
            ):
                targets_by_pair[(transaction_date, team_id)].add(mlb_id)
                endpoint_added = True
        if endpoint_added:
            eligible_identity_dates.add((mlb_id, transaction_date))

    matches_by_identity_date = defaultdict(list)
    fetch_errors = []
    source_match_count = 0
    failed_identity_dates = set()
    for (transaction_date, team_id), mlb_ids in sorted(targets_by_pair.items()):
        index, errors = build_exact_date_team_roster_status_index(
            team_id,
            transaction_date,
            client=client,
        )
        if errors:
            fetch_errors.extend(errors)
            failed_identity_dates.update(
                (mlb_id, transaction_date)
                for mlb_id in mlb_ids
            )
            continue
        for mlb_id in sorted(mlb_ids):
            evidence = index.get(mlb_id)
            if evidence is None:
                continue
            source_match_count += 1
            matches_by_identity_date[(mlb_id, transaction_date)].append({
                'team_id': team_id,
                'evidence': evidence,
            })

    candidates = []
    source_conflicts = 0
    for (mlb_id, transaction_date), matches in sorted(
        matches_by_identity_date.items()
    ):
        if (mlb_id, transaction_date) in failed_identity_dates:
            continue
        if len(matches) != 1:
            source_conflicts += 1
            logger.warning(
                'Exact-date transaction roster evidence conflict '
                'mlb_id=%s date=%s endpoint_teams=%s',
                mlb_id,
                transaction_date,
                sorted(match['team_id'] for match in matches),
            )
            continue
        match = matches[0]
        candidates.append({
            'pitcher': pitchers_by_mlb_id[mlb_id],
            'team_id': match['team_id'],
            'snapshot_date': transaction_date,
            'evidence': match['evidence'],
        })

    persistence = persist_missing_exact_roster_status_snapshots(
        candidates,
        timestamp=timestamp,
        sync_run_id=sync_run_id,
    )
    return {
        'eligible_pitchers': len(eligible),
        'eligible_team_date_pairs': len(targets_by_pair),
        'requests': len(targets_by_pair) * len(ROSTER_TYPES),
        'source_matches': source_match_count,
        'source_conflicts': source_conflicts,
        'source_omissions': (
            len(
                eligible_identity_dates
                - set(matches_by_identity_date)
                - failed_identity_dates
            )
        ),
        'fetch_failures': len(fetch_errors),
        'snapshots_created': persistence['created'],
        'snapshots_unchanged': persistence['unchanged'],
        'snapshot_conflicts': persistence['conflicts'],
        'failure_records': persistence['failure_records'],
        'error_details': fetch_errors,
    }


def acquire_transaction_roster_evidence(
    *,
    transactions,
    newly_resolved_mlb_ids,
    pitchers_by_mlb_id,
    team_metadata_by_season,
    client,
    timestamp,
    sync_run_id=None,
):
    """Acquire exact-date endpoint evidence for newly resolved identities only."""
    result = acquire_exact_transaction_roster_evidence(
        transactions=transactions,
        eligible_mlb_ids=newly_resolved_mlb_ids,
        pitchers_by_mlb_id=pitchers_by_mlb_id,
        team_metadata_by_season=team_metadata_by_season,
        client=client,
        timestamp=timestamp,
        sync_run_id=sync_run_id,
    )
    return {
        'newly_resolved_pitchers': result.pop('eligible_pitchers'),
        **result,
    }


__all__ = [
    'acquire_exact_transaction_roster_evidence',
    'acquire_transaction_roster_evidence',
]
