"""CU-05 bounded Arm Read and Team State shadow recomputation.

Consumes only the accepted CU-04 result, reuses the production availability,
Arm Read, active-bullpen, and Team State authorities, and stops before every
read-model, publication, cache, and scheduling seam.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from time import perf_counter
from types import SimpleNamespace

from models.pitcher import Pitcher
from services.availability import classify_availability_inputs
from services.availability_snapshot import (
    CURRENT_AVAILABILITY_MODE,
    _apply_workload_fetch_failure,
    _unresolved_workload_fetch_failure_refs,
)
from services.incremental_workload_rest import (
    PARITY_MATCH,
    PARITY_MISMATCH,
    PARITY_NOT_COMPARABLE,
    STATUS_COMPLETE,
)
from services.share_artifact_generation import resolve_team_readiness_payload
from services.team_readiness_coverage import resolve_active_bullpen_membership
from services.team_state_public_vocabulary import (
    is_publishable_state,
    public_state_for,
)
from utils.db import db


STATUS_NO_ACTION = 'no_action'
STATUS_PARTIAL = 'partial'


@dataclass(frozen=True)
class ParityEntry:
    scope: str
    entity_id: int
    field: str
    status: str
    incremental_value: object
    authoritative_value: object


@dataclass(frozen=True)
class IncrementalArmReadTeamStateResult:
    game_pk: int | None
    data_through: str | None
    availability_reference_date: str | None
    status: str
    reason_code: str
    requested_pitcher_ids: tuple = ()
    requested_team_ids: tuple = ()
    arm_reads_recomputed: tuple = ()
    teams_recomputed: tuple = ()
    skipped_arm_read_pitcher_ids: tuple = ()
    arm_read_results: dict = field(default_factory=dict)
    team_state_results: dict = field(default_factory=dict)
    availability_results: dict = field(default_factory=dict)
    workload_rest_pitcher_results: dict = field(default_factory=dict)
    workload_rest_team_results: dict = field(default_factory=dict)
    parity_status: str = PARITY_NOT_COMPARABLE
    parity_entries: tuple = ()
    parity_mismatches: tuple = ()
    failures: tuple = ()
    recomputation_performed: bool = False
    arm_read_recomputation_ms: float = 0.0
    team_state_recomputation_ms: float = 0.0
    read_models_rebuilt: bool = False
    publication_affected: bool = False
    cache_invalidation_triggered: bool = False
    scheduling_affected: bool = False
    downstream_recomputation_triggered: bool = False

    def to_dict(self):
        value = asdict(self)
        for key in (
            'requested_pitcher_ids', 'requested_team_ids',
            'arm_reads_recomputed', 'teams_recomputed',
            'skipped_arm_read_pitcher_ids', 'parity_entries',
            'parity_mismatches', 'failures',
        ):
            value[key] = list(value[key])
        return value


def recompute_arm_reads_team_state(
    cu04_result,
    *,
    source_snapshot=None,
    compare_authoritative=True,
    readiness_provider=None,
    authoritative_readiness_provider=None,
    membership_provider=None,
):
    """Recompute only Arm Reads and Team States invalidated by CU-04 work."""
    pitcher_ids = tuple(sorted(set(_get(cu04_result, 'pitchers_recomputed') or ())))
    input_team_ids = tuple(sorted(set(_get(cu04_result, 'teams_recomputed') or ())))
    game_pk = _get(cu04_result, 'game_pk')
    data_through = _parse_date(_get(cu04_result, 'data_through'))
    availability_date = _parse_date(
        _get(cu04_result, 'availability_reference_date')
    )
    cu04_ready = (
        _get(cu04_result, 'status') == STATUS_COMPLETE
        and _get(cu04_result, 'parity_status') == PARITY_MATCH
        and bool(_get(cu04_result, 'recomputation_performed'))
    )
    if not cu04_ready or (not pitcher_ids and not input_team_ids):
        return IncrementalArmReadTeamStateResult(
            game_pk=game_pk,
            data_through=_iso(data_through),
            availability_reference_date=_iso(availability_date),
            status=STATUS_NO_ACTION,
            reason_code='cu04_no_action_or_untrusted',
            requested_pitcher_ids=pitcher_ids,
            requested_team_ids=input_team_ids,
        )
    if data_through is None or availability_date is None:
        raise ValueError('CU-05 requires CU-04 explicit represented dates')

    failures = []
    overrides = {}
    pitcher_started = perf_counter()
    for pitcher_id in pitcher_ids:
        try:
            overrides[pitcher_id] = _classified_override(
                pitcher_id,
                (_get(cu04_result, 'pitcher_results') or {})[pitcher_id],
                availability_date=availability_date,
            )
        except Exception as exc:  # shadow failure; dependent state is withheld
            failures.append({
                'scope': 'arm_read', 'entity_id': pitcher_id,
                'error': type(exc).__name__,
            })
    arm_ms = (perf_counter() - pitcher_started) * 1000.0

    membership_resolver = membership_provider or resolve_active_bullpen_membership
    team_ids = set(input_team_ids)
    active_affected_ids = set()
    for team_id in sorted(team_ids):
        member_ids, authority_complete = membership_resolver(team_id, data_through)
        if authority_complete:
            active_affected_ids.update(set(pitcher_ids).intersection(member_ids))
    for pitcher_id, record in overrides.items():
        pitcher = record['pitcher']
        current_team_id = getattr(pitcher, 'team_id', None)
        if current_team_id is None:
            continue
        member_ids, authority_complete = membership_resolver(
            current_team_id, data_through,
        )
        if authority_complete and pitcher_id in member_ids:
            active_affected_ids.add(pitcher_id)
            team_ids.add(int(current_team_id))

    provider = readiness_provider or resolve_team_readiness_payload
    authority_provider = authoritative_readiness_provider or provider
    team_results = {}
    arm_results = {}
    parity_entries = []
    team_started = perf_counter()
    for team_id in sorted(team_ids):
        try:
            incremental = _resolve_team(
                provider,
                team_id,
                overrides=overrides,
                source_snapshot=source_snapshot,
                represented_date=data_through,
            )
            if incremental is None:
                failures.append({
                    'scope': 'team_state', 'entity_id': team_id,
                    'error': 'ReadinessUnavailable',
                })
                continue
            team_results[team_id] = incremental['team_state']
            for pitcher_id, record in incremental['arm_reads'].items():
                if pitcher_id in active_affected_ids:
                    arm_results[pitcher_id] = record

            if compare_authoritative:
                authoritative = _resolve_team(
                    authority_provider,
                    team_id,
                    overrides=overrides,
                    source_snapshot=source_snapshot,
                    represented_date=data_through,
                )
                if authoritative is None:
                    failures.append({
                        'scope': 'parity', 'entity_id': team_id,
                        'error': 'AuthoritativeReadinessUnavailable',
                    })
                    continue
                parity_entries.extend(_compare_values(
                    'team', team_id,
                    incremental['team_state'], authoritative['team_state'],
                ))
                for pitcher_id in sorted(active_affected_ids):
                    left = incremental['arm_reads'].get(pitcher_id)
                    right = authoritative['arm_reads'].get(pitcher_id)
                    if left is None and right is None:
                        continue
                    parity_entries.extend(_compare_values(
                        'pitcher', pitcher_id, left or {}, right or {},
                    ))
        except Exception as exc:
            failures.append({
                'scope': 'team_state', 'entity_id': team_id,
                'error': type(exc).__name__,
            })
    team_ms = (perf_counter() - team_started) * 1000.0

    mismatches = tuple(
        asdict(entry) for entry in parity_entries
        if entry.status == PARITY_MISMATCH
    )
    if failures:
        status = STATUS_PARTIAL
        reason = 'bounded_recomputation_failed'
        parity_status = PARITY_NOT_COMPARABLE
    elif compare_authoritative and mismatches:
        status = STATUS_PARTIAL
        reason = 'parity_mismatch'
        parity_status = PARITY_MISMATCH
    else:
        status = STATUS_COMPLETE
        reason = 'parity_match' if compare_authoritative else 'recomputed_without_parity'
        parity_status = PARITY_MATCH if compare_authoritative else PARITY_NOT_COMPARABLE

    skipped = tuple(sorted(set(pitcher_ids).difference(arm_results)))
    return IncrementalArmReadTeamStateResult(
        game_pk=game_pk,
        data_through=data_through.isoformat(),
        availability_reference_date=availability_date.isoformat(),
        status=status,
        reason_code=reason,
        requested_pitcher_ids=pitcher_ids,
        requested_team_ids=tuple(sorted(team_ids)),
        arm_reads_recomputed=tuple(sorted(arm_results)),
        teams_recomputed=tuple(sorted(team_results)),
        skipped_arm_read_pitcher_ids=skipped,
        arm_read_results=arm_results,
        team_state_results=team_results,
        availability_results={
            pitcher_id: dict(record.get('availability') or {})
            for pitcher_id, record in overrides.items()
        },
        workload_rest_pitcher_results=dict(
            _get(cu04_result, 'pitcher_results') or {}
        ),
        workload_rest_team_results=dict(
            _get(cu04_result, 'team_results') or {}
        ),
        parity_status=parity_status,
        parity_entries=tuple(asdict(entry) for entry in parity_entries),
        parity_mismatches=mismatches,
        failures=tuple(failures),
        recomputation_performed=bool(arm_results or team_results),
        arm_read_recomputation_ms=round(arm_ms, 3),
        team_state_recomputation_ms=round(team_ms, 3),
    )


def _classified_override(pitcher_id, workload_result, *, availability_date):
    pitcher = db.session.get(Pitcher, pitcher_id)
    if pitcher is None:
        raise LookupError(f'pitcher {pitcher_id} not found')
    workload_result = dict(workload_result or {})
    inputs = dict(workload_result.get('rest_workload_inputs') or {})
    availability = classify_availability_inputs(inputs)
    if str(getattr(pitcher, 'mlb_id', '')) in _unresolved_workload_fetch_failure_refs(
        [pitcher]
    ):
        availability = _apply_workload_fetch_failure(availability)
    latest_game_date = _parse_date(inputs.get('latest_game_date'))
    score = SimpleNamespace(
        raw_score=inputs.get('fatigue_score'),
        risk_level=inputs.get('fatigue_risk_level'),
    )
    return {
        'pitcher_id': pitcher.id,
        'pitcher_name': pitcher.full_name,
        'team': pitcher.team_abbreviation,
        'score': score,
        'pitcher': pitcher,
        'availability': availability,
        'mode': CURRENT_AVAILABILITY_MODE,
        'evaluation_date': availability_date,
        'latest_game_date': latest_game_date,
    }


def _resolve_team(
    provider, team_id, *, overrides, source_snapshot, represented_date,
):
    arm_reads = {}
    references = {}
    payload = provider(
        team_id,
        source_snapshot=source_snapshot,
        reference_dates_out=references,
        arm_reads_out=arm_reads,
        classified_record_overrides=overrides,
        represented_date_override=represented_date,
    )
    if payload is None:
        return None
    arm_by_pitcher = {
        int(record['pitcher_id']): _arm_projection(record)
        for record in arm_reads.get('records') or ()
    }
    return {
        'arm_reads': arm_by_pitcher,
        'team_state': _team_projection(payload, arm_reads, references),
    }


def _arm_projection(record):
    return {
        'pitcher_id': record.get('pitcher_id'),
        'team_id': record.get('team_id'),
        'public_read': dict(record.get('public_read') or {}),
        'evidence_state': dict(record.get('evidence_state') or {}),
        'roster_authority': dict(record.get('roster_authority') or {}),
    }


def _team_projection(payload, arm_reads, references):
    readiness = dict(payload.get('readiness') or {})
    status_code = readiness.get('status_code')
    public_state = public_state_for(status_code) if is_publishable_state(status_code) else None
    return {
        'team_id': (payload.get('team') or {}).get('team_id'),
        'membership_reference_date': _iso(references.get('membership_reference_date')),
        'availability_reference_date': _iso(references.get('availability_reference_date')),
        'member_pitcher_ids': list(arm_reads.get('member_pitcher_ids') or ()),
        'missing_record_pitcher_ids': list(
            arm_reads.get('missing_record_pitcher_ids') or ()
        ),
        'readiness': readiness,
        'public_team_state': public_state,
        'availability_distribution': dict(
            payload.get('availability_distribution') or {}
        ),
        'coverage_inventory': dict(payload.get('coverage_inventory') or {}),
        'team_state_evidence': dict(payload.get('team_state_evidence') or {}),
    }


def _compare_values(scope, entity_id, incremental, authoritative, prefix=''):
    entries = []
    incremental = dict(incremental or {})
    authoritative = dict(authoritative or {})
    for key in sorted(set(incremental) | set(authoritative)):
        field_name = f'{prefix}.{key}' if prefix else str(key)
        left = incremental.get(key)
        right = authoritative.get(key)
        if isinstance(left, dict) and isinstance(right, dict):
            entries.extend(_compare_values(
                scope, entity_id, left, right, prefix=field_name,
            ))
            continue
        entries.append(ParityEntry(
            scope=scope,
            entity_id=entity_id,
            field=field_name,
            status=PARITY_MATCH if left == right else PARITY_MISMATCH,
            incremental_value=left,
            authoritative_value=right,
        ))
    return entries


def _parse_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _iso(value):
    return value.isoformat() if isinstance(value, date) else None


def _get(value, field):
    if isinstance(value, dict):
        return value.get(field)
    return getattr(value, field, None)
