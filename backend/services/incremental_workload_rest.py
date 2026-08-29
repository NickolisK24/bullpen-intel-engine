"""CU-04 bounded workload/rest recomputation and shadow parity proof.

This service consumes mutation-scoped CU-03 output.  It deliberately reuses
the current authoritative calculators and stops before availability/arm reads,
Team State, read models, publication, cache invalidation, or scheduling.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from time import perf_counter

from sqlalchemy import desc

from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability import ACTIVE_WINDOW_DAYS, derive_workload_rest_inputs
from services.availability_reference_date import trusted_slate_reference_dates
from services.fatigue import calculate_fatigue
from services.public_team_relief_work import author_workload_windows
from utils.db import db


STATUS_NO_ACTION = 'no_action'
STATUS_COMPLETE = 'complete'
STATUS_PARTIAL = 'partial'
PARITY_MATCH = 'match'
PARITY_MISMATCH = 'mismatch'
PARITY_NOT_COMPARABLE = 'not_comparable'

PITCHER_FATIGUE_WORKLOAD_FIELDS = (
    'days_since_last_appearance',
    'appearances_last_7',
    'appearances_last_14',
    'pitches_last_7_days',
    'innings_last_7_days',
)
PITCHER_REST_INPUT_FIELDS = (
    'fatigue_score',
    'fatigue_risk_level',
    'pitches_yesterday',
    'pitches_last_3_days',
    'pitches_last_5_days',
    'appearances_last_3_days',
    'appearances_last_5_days',
    'days_rest',
    'back_to_back',
    'three_in_four',
    'four_in_five',
    'freshness_state',
    'latest_game_date',
    'reference_date',
)


@dataclass(frozen=True)
class ParityEntry:
    scope: str
    entity_id: int
    field: str
    status: str
    incremental_value: object
    authoritative_value: object


@dataclass(frozen=True)
class IncrementalWorkloadRestResult:
    game_pk: int | None
    data_through: str | None
    availability_reference_date: str | None
    status: str
    reason_code: str
    requested_pitcher_ids: tuple = ()
    requested_team_ids: tuple = ()
    pitchers_recomputed: tuple = ()
    teams_recomputed: tuple = ()
    pitcher_results: dict = field(default_factory=dict)
    team_results: dict = field(default_factory=dict)
    parity_status: str = PARITY_NOT_COMPARABLE
    parity_entries: tuple = ()
    parity_mismatches: tuple = ()
    failures: tuple = ()
    recomputation_performed: bool = False
    pitcher_recomputation_ms: float = 0.0
    team_recomputation_ms: float = 0.0
    team_state_recomputed: bool = False
    read_models_rebuilt: bool = False
    publication_affected: bool = False
    cache_invalidation_triggered: bool = False
    downstream_recomputation_triggered: bool = False

    def to_dict(self):
        value = asdict(self)
        for key in (
            'requested_pitcher_ids', 'requested_team_ids',
            'pitchers_recomputed', 'teams_recomputed',
            'parity_entries', 'parity_mismatches', 'failures',
        ):
            value[key] = list(value[key])
        return value


def recompute_workload_rest_impact(
    change_impact,
    *,
    data_through,
    compare_authoritative=True,
    authoritative_pitcher_provider=None,
    authoritative_team_provider=None,
):
    """Recompute only mutation-scoped workload/rest facts from CU-03 output."""
    pitcher_ids = tuple(sorted(set(_get(change_impact, 'affected_pitcher_ids') or ())))
    team_ids = tuple(sorted(set(_get(change_impact, 'affected_team_ids') or ())))
    canonical_mutation = bool(
        _get(change_impact, 'canonical_mutation_performed')
    )
    game_pk = _get(change_impact, 'game_pk')

    if not canonical_mutation or (not pitcher_ids and not team_ids):
        return IncrementalWorkloadRestResult(
            game_pk=game_pk,
            data_through=_iso_date(data_through),
            availability_reference_date=None,
            status=STATUS_NO_ACTION,
            reason_code='no_canonical_mutation',
            requested_pitcher_ids=pitcher_ids,
            requested_team_ids=team_ids,
        )

    represented = _parse_required_date(data_through)
    membership_date, availability_ref = trusted_slate_reference_dates(represented)
    if membership_date is None or availability_ref is None:
        raise ValueError('data_through must be an explicit represented baseball date')

    failures = []
    pitcher_results = {}
    pitcher_started = perf_counter()
    for pitcher_id in pitcher_ids:
        try:
            pitcher_results[pitcher_id] = _compute_pitcher_workload_rest(
                pitcher_id, data_through=membership_date,
                availability_reference_date=availability_ref,
            )
        except Exception as exc:  # structured shadow failure; never publish partial work
            failures.append({
                'scope': 'pitcher', 'entity_id': pitcher_id,
                'error': type(exc).__name__,
            })
    pitcher_ms = (perf_counter() - pitcher_started) * 1000.0

    team_results = {}
    team_started = perf_counter()
    for team_id in team_ids:
        try:
            team_results[team_id] = author_workload_windows(
                team_id, data_through=membership_date,
            )
        except Exception as exc:
            failures.append({
                'scope': 'team', 'entity_id': team_id,
                'error': type(exc).__name__,
            })
    team_ms = (perf_counter() - team_started) * 1000.0

    parity_entries = []
    if compare_authoritative and not failures:
        pitcher_provider = (
            authoritative_pitcher_provider or _compute_pitcher_workload_rest
        )
        team_provider = authoritative_team_provider or author_workload_windows
        for pitcher_id, incremental in pitcher_results.items():
            authoritative = pitcher_provider(
                pitcher_id,
                data_through=membership_date,
                availability_reference_date=availability_ref,
            )
            parity_entries.extend(_compare_values(
                'pitcher', pitcher_id, incremental, authoritative,
            ))
        for team_id, incremental in team_results.items():
            authoritative = team_provider(
                team_id, data_through=membership_date,
            )
            parity_entries.extend(_compare_values(
                'team', team_id, incremental, authoritative,
            ))

    mismatches = tuple(
        asdict(entry) for entry in parity_entries
        if entry.status == PARITY_MISMATCH
    )
    if failures:
        parity_status = PARITY_NOT_COMPARABLE
        status = STATUS_PARTIAL
        reason = 'bounded_recomputation_failed'
    elif compare_authoritative:
        parity_status = PARITY_MISMATCH if mismatches else PARITY_MATCH
        status = STATUS_COMPLETE if not mismatches else STATUS_PARTIAL
        reason = 'parity_match' if not mismatches else 'parity_mismatch'
    else:
        parity_status = PARITY_NOT_COMPARABLE
        status = STATUS_COMPLETE
        reason = 'recomputed_without_parity'

    return IncrementalWorkloadRestResult(
        game_pk=game_pk,
        data_through=membership_date.isoformat(),
        availability_reference_date=availability_ref.isoformat(),
        status=status,
        reason_code=reason,
        requested_pitcher_ids=pitcher_ids,
        requested_team_ids=team_ids,
        pitchers_recomputed=tuple(sorted(pitcher_results)),
        teams_recomputed=tuple(sorted(team_results)),
        pitcher_results=pitcher_results,
        team_results=team_results,
        parity_status=parity_status,
        parity_entries=tuple(asdict(entry) for entry in parity_entries),
        parity_mismatches=mismatches,
        failures=tuple(failures),
        recomputation_performed=bool(pitcher_results or team_results),
        pitcher_recomputation_ms=round(pitcher_ms, 3),
        team_recomputation_ms=round(team_ms, 3),
    )


def _compute_pitcher_workload_rest(
    pitcher_id, *, data_through, availability_reference_date,
):
    pitcher = db.session.get(Pitcher, pitcher_id)
    if pitcher is None:
        raise LookupError(f'pitcher {pitcher_id} not found')

    fatigue_start = availability_reference_date - timedelta(days=14)
    logs = (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_date >= fatigue_start,
            GameLog.game_date <= data_through,
        )
        .order_by(desc(GameLog.game_date), desc(GameLog.id))
        .all()
    )
    score = calculate_fatigue(
        pitcher, logs, reference_date=availability_reference_date,
    )
    latest_game_date = (
        db.session.query(db.func.max(GameLog.game_date))
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_date <= data_through,
        )
        .scalar()
    )
    availability_start = availability_reference_date - timedelta(days=4)
    availability_logs = [
        log for log in logs
        if availability_start <= log.game_date <= availability_reference_date
    ]
    rest_inputs = derive_workload_rest_inputs(
        score=score,
        game_logs=availability_logs,
        reference_date=availability_reference_date,
        latest_game_date=latest_game_date,
        active_window_days=ACTIVE_WINDOW_DAYS,
    )
    return {
        'pitcher_id': pitcher_id,
        'data_through': data_through.isoformat(),
        'availability_reference_date': availability_reference_date.isoformat(),
        'fatigue_workload': {
            field: getattr(score, field)
            for field in PITCHER_FATIGUE_WORKLOAD_FIELDS
        },
        'rest_workload_inputs': {
            field: rest_inputs[field]
            for field in PITCHER_REST_INPUT_FIELDS
        },
    }


def _compare_values(scope, entity_id, incremental, authoritative, prefix=''):
    entries = []
    keys = sorted(set(incremental) | set(authoritative))
    for key in keys:
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


def _parse_required_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(
            'data_through must be an explicit represented baseball date'
        ) from None


def _iso_date(value):
    try:
        return _parse_required_date(value).isoformat()
    except ValueError:
        return None


def _get(value, field):
    if isinstance(value, dict):
        return value.get(field)
    return getattr(value, field, None)
