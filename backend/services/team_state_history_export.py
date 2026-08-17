"""Read-only export of historical Team State calibration evidence.

This module exists for one bounded operational purpose: to lift the Team State
evidence that production already froze at publication time into a JSON artifact
that can be analysed offline. It performs no calculation, no classification, no
repair, and no write of any kind.

Historical authority mapping
----------------------------
Two frozen sources carry Team State evidence. Neither is recomputed here.

1. ``ShareArtifact`` rows of type ``team_state`` (``services.team_state_payload``)
   are the authoritative published Team State for one ``(team, snapshot)``. Their
   immutable document preserves the readiness ``status_code``, the published
   summary sentence, the governed constraints, and the trust/freshness block.

2. ``DashboardSnapshot.payload['trusted_team_boards']``
   (``services.public_serving_authority.build_frozen_team_board_package``)
   preserves the per-arm board records that were captured at candidate time,
   plus ``default_pitcher_ids`` — the governed current-availability population
   for that team at that snapshot.

What historical authority does NOT preserve
-------------------------------------------
The Team State component vectors (``availability_distribution``,
``workload_pressure``, ``coverage_inventory``, ``handedness_coverage``) are
assembled at generation time by ``team_operations.bullpen_readiness`` and
consumed as a governed input. Only the resulting status survives into the
immutable artifact. They are therefore exported as ``None`` and are listed in
``UNPRESERVED_TEAM_LEVEL_FIELDS``.

The exporter never fills such a gap from current tables. A field that history
did not keep is emitted as ``None``, always, so an analyst can tell "not
recorded" apart from "recorded as zero".
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from services.public_serving_authority import (
    TEAM_BOARD_PACKAGE_CONTRACT,
    TEAM_BOARD_PACKAGE_KEY,
)
from services.team_state_public_vocabulary import INTERNAL_TO_PUBLIC_STATE, PUBLIC_STATE_LABELS


EXPORT_VERSION = 'team_state_calibration_history_v1'
SOURCE_CONTRACT = (
    'dashboard_snapshot.payload.trusted_team_boards + share_artifact.team_state'
)

# Arm availability families, as published on the frozen board record. These are
# the exact governed public reads; no new vocabulary is introduced here.
CLEAN_STATUSES = frozenset({'available'})
MODERATE_STATUSES = frozenset({'monitor', 'limited'})
SEVERE_STATUSES = frozenset({'avoid', 'unavailable'})

# Team-level fields the historical authority does not preserve. Every one of
# these is emitted as ``None`` on every row, under one consistent contract.
UNPRESERVED_TEAM_LEVEL_FIELDS = (
    'active_pitcher_count',
    'avail_available',
    'avail_monitor',
    'avail_limited',
    'avail_avoid',
    'avail_unavailable',
    'avail_unknown',
    'workload_low',
    'workload_moderate',
    'workload_elevated',
    'workload_unknown',
    'current_workload_data_count',
    'missing_workload_data_count',
    'availability_covered_count',
    'availability_missing_count',
    'coverage_state',
    'hand_left',
    'hand_right',
    'hand_unknown',
    'handedness_coverage_state',
)

# Arm-level fields the frozen board record does not preserve.
UNPRESERVED_ARM_FIELDS = ('workload_category', 'throwing_hand', 'has_current_workload')


def _mapping(value) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _iso(value):
    return value.isoformat() if value is not None else None


def _as_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _share(count, denominator):
    """Ratio guarded against a zero/absent denominator. Never invents a value."""
    if count is None or not denominator:
        return None
    return count / denominator


def public_state_for(status_code) -> Optional[str]:
    """Public label for an internal status, or None when it is not publishable.

    ``data_limited`` and ``refused`` have no public Team State and must never be
    converted into one. They return ``None`` rather than a label.
    """
    public_code = INTERNAL_TO_PUBLIC_STATE.get(status_code)
    if public_code is None:
        return None
    return PUBLIC_STATE_LABELS[public_code]


def _team_package(snapshot_payload: Mapping[str, Any], team_id) -> Optional[dict]:
    """The frozen board package for one team, or None when it was not captured."""
    package = snapshot_payload.get(TEAM_BOARD_PACKAGE_KEY)
    if not isinstance(package, Mapping) or package.get('contract') != TEAM_BOARD_PACKAGE_CONTRACT:
        return None
    by_team = package.get('by_team_id')
    if not isinstance(by_team, Mapping):
        return None
    team = by_team.get(str(team_id))
    if team is None:
        team = by_team.get(team_id)
    return dict(team) if isinstance(team, Mapping) else None


def _arm_rows(team_package: Mapping[str, Any]) -> list:
    """Arm-level rows carrying only values the frozen record actually preserved."""
    records = team_package.get('records')
    if not isinstance(records, (list, tuple)):
        return []
    arms = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        availability = _mapping(record.get('availability'))
        arms.append({
            'pitcher_id': _as_int(record.get('pitcher_id')),
            'availability_status': availability.get('availability_status'),
            'availability_data_state': availability.get('data_state'),
            # ``fatigue_score`` on the frozen record is the FatigueScore raw_score.
            'raw_score': record.get('fatigue_score'),
            'has_availability': bool(availability.get('availability_status')),
            # Not preserved by the frozen board record.
            'workload_category': None,
            'throwing_hand': None,
            'has_current_workload': None,
        })
    return arms


def _partition(arms: Sequence[Mapping[str, Any]], population_ids) -> dict:
    """Derive the clean/moderate/severe/unknown partition from frozen arm reads.

    This is a straight tally of values the snapshot already froze. It classifies
    nothing and recomputes no Team State. Arms outside the governed population
    are excluded so the denominator is the published board population.
    """
    ids = {value for value in (_as_int(item) for item in (population_ids or [])) if value is not None}
    counts = {'clean': 0, 'moderate': 0, 'severe': 0, 'unknown': 0}
    for arm in arms:
        if ids and arm.get('pitcher_id') not in ids:
            continue
        status = str(arm.get('availability_status') or '').strip().lower()
        if status in CLEAN_STATUSES:
            counts['clean'] += 1
        elif status in MODERATE_STATUSES:
            counts['moderate'] += 1
        elif status in SEVERE_STATUSES:
            counts['severe'] += 1
        else:
            counts['unknown'] += 1
    total = sum(counts.values())
    return {
        'derived': True,
        'derived_from': (
            'dashboard_snapshot.payload.trusted_team_boards'
            '.by_team_id[].records[].availability.availability_status'
        ),
        'population_basis': 'trusted_team_boards.default_pitcher_ids',
        'population_count': total,
        'clean_count': counts['clean'],
        'moderate_count': counts['moderate'],
        'severe_count': counts['severe'],
        'unknown_count': counts['unknown'],
        'clean_share': _share(counts['clean'], total),
        'moderate_share': _share(counts['moderate'], total),
        'severe_share': _share(counts['severe'], total),
        'unknown_share': _share(counts['unknown'], total),
    }


def _integrity(partition: Optional[Mapping[str, Any]], population_ids) -> dict:
    """Surface partition problems. Never repairs and never normalizes a row."""
    flags = []
    if partition is None:
        flags.append('frozen_board_package_missing')
        return {'ok': False, 'flags': flags}
    declared = len({value for value in (_as_int(item) for item in (population_ids or [])) if value is not None})
    counted = partition['population_count']
    summed = (
        partition['clean_count']
        + partition['moderate_count']
        + partition['severe_count']
        + partition['unknown_count']
    )
    if summed != counted:
        flags.append('partition_sum_mismatch')
    if declared and declared != counted:
        flags.append('population_count_mismatch')
    if counted == 0:
        flags.append('empty_population')
    return {
        'ok': not flags,
        'flags': flags,
        'declared_population_count': declared or None,
        'counted_population_count': counted,
    }


def _constraint_ids(document: Mapping[str, Any]) -> list:
    team_state = _mapping(document.get('team_state'))
    constraints = team_state.get('constraints')
    if not isinstance(constraints, (list, tuple)):
        return []
    return [
        item.get('constraint_id')
        for item in constraints
        if isinstance(item, Mapping) and item.get('constraint_id')
    ]


def build_row(snapshot, artifact) -> dict:
    """One team x trusted-snapshot calibration row, from frozen authority only."""
    document = _mapping(getattr(artifact, 'payload', None))
    team_block = _mapping(document.get('team'))
    state_block = _mapping(document.get('team_state'))
    trust_block = _mapping(document.get('trust'))

    status_code = state_block.get('status_code')
    team_id = _as_int(getattr(artifact, 'team_id', None))
    snapshot_payload = getattr(snapshot, 'payload', None)
    snapshot_payload = snapshot_payload if isinstance(snapshot_payload, Mapping) else {}

    team_package = _team_package(snapshot_payload, team_id)
    arms = _arm_rows(team_package) if team_package else []
    population_ids = team_package.get('default_pitcher_ids') if team_package else []
    partition = _partition(arms, population_ids) if team_package else None

    row = {
        'snapshot_id': _as_int(getattr(snapshot, 'id', None)),
        'sync_run_id': _as_int(getattr(snapshot, 'sync_run_id', None)),
        'published_at': _iso(getattr(snapshot, 'published_at', None)),
        'product_date': _iso(getattr(artifact, 'product_date', None)),
        'data_through': _iso(getattr(snapshot, 'data_through', None)),
        'contract_version': getattr(artifact, 'render_version', None),
        'team_id': team_id,
        'team_abbreviation': team_block.get('team_abbreviation'),
        'readiness_status_code': status_code,
        'public_team_state': public_state_for(status_code),
        'trust_confidence': trust_block.get('confidence'),
        'trust_data_state': trust_block.get('data_state'),
        'freshness_state': trust_block.get('freshness_state'),
        'published_why_text': state_block.get('summary'),
        'constraint_ids': _constraint_ids(document),
        'frozen_board_present': team_package is not None,
        'arms': arms,
        'derived_partition': partition,
        'integrity': _integrity(partition, population_ids),
    }
    # One consistent contract for everything history did not keep.
    for field in UNPRESERVED_TEAM_LEVEL_FIELDS:
        row[field] = None
    return row


def build_export(
    pairs: Sequence[tuple],
    *,
    generated_at: str,
    repository_sha: Optional[str],
    filters: Mapping[str, Any],
) -> dict:
    """Assemble the export artifact from ``(snapshot, artifact)`` pairs."""
    rows = [build_row(snapshot, artifact) for snapshot, artifact in pairs]
    return {
        'export_version': EXPORT_VERSION,
        'generated_at': generated_at,
        'repository_sha': repository_sha,
        'read_only': True,
        'filters': dict(filters),
        'source_contract': SOURCE_CONTRACT,
        'unpreserved_team_level_fields': list(UNPRESERVED_TEAM_LEVEL_FIELDS),
        'unpreserved_arm_fields': list(UNPRESERVED_ARM_FIELDS),
        'snapshot_count': len({row['snapshot_id'] for row in rows}),
        'team_classification_count': len(rows),
        'rows': rows,
    }
