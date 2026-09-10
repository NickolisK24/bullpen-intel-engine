"""CU-07 atomic publication proof for a validated CU-06 cohort.

The production public routes remain bound to their existing snapshot types.  This
service deliberately publishes only to an isolated DashboardSnapshot namespace so
the real database transaction and pointer-rotation behavior can be proven without
installing the continuous chain as serving authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from hashlib import sha256
import json
from time import perf_counter

from sqlalchemy import text

from models.dashboard_snapshot import DashboardSnapshot
from services.incremental_read_model_rebuild import NON_SEMANTIC_FIELDS
from services.incremental_workload_rest import PARITY_MATCH, STATUS_COMPLETE
from utils.db import db
from utils.time import utc_now_naive


PROOF_SNAPSHOT_TYPE = 'cu07_incremental_proof'
PROOF_SOURCE = 'cu07_proof'
COHORT_CONTRACT = 'incremental_publication_cohort_v1'
STATUS_STAGED = 'pending'
STATUS_CURRENT = 'ready'

RESULT_NO_ACTION = 'no_action'
RESULT_STAGED = 'staged'
RESULT_COMMITTED = 'committed'
RESULT_CACHE_PENDING = 'committed_cache_pending'
RESULT_ABORTED = 'aborted'
RESULT_CONFLICT = 'conflict'
RESULT_STALE = 'stale'

_ADVISORY_LOCK_KEY = 707_000_001


@dataclass(frozen=True)
class PublicationCandidate:
    candidate_id: str
    semantic_fingerprint: str
    represented_date: str
    source_identity: str
    source_order: int
    affected_team_ids: tuple
    affected_game_ids: tuple
    payload: dict
    validation_errors: tuple = ()

    @property
    def valid(self):
        return not self.validation_errors


@dataclass(frozen=True)
class IncrementalPublicationResult:
    candidate_id: str | None
    status: str
    reason_code: str
    previous_publication_id: int | None = None
    new_publication_id: int | None = None
    affected_team_ids: tuple = ()
    affected_game_ids: tuple = ()
    validation_passed: bool = False
    committed: bool = False
    cache_handoff_status: str = 'not_attempted'
    cache_keys: tuple = ()
    rollback_performed: bool = False
    historical_payload_mutations: int = 0
    production_authority_affected: bool = False
    mixed_state_observed: bool = False
    build_validation_ms: float = 0.0
    stage_ms: float = 0.0
    commit_ms: float = 0.0
    cache_ms: float = 0.0
    errors: tuple = ()

    def to_dict(self):
        value = asdict(self)
        for key in ('affected_team_ids', 'affected_game_ids', 'cache_keys', 'errors'):
            value[key] = list(value[key])
        return value


def build_candidate(cu06_result, *, source_identity, source_order):
    """Build and validate one deterministic semantic publication cohort."""
    represented_date = _get(cu06_result, 'represented_date')
    team_ids = tuple(sorted(set(_get(cu06_result, 'requested_team_ids') or ())))
    game_pk = _get(cu06_result, 'game_pk')
    game_ids = (int(game_pk),) if game_pk is not None else ()
    boards = _string_keys(_get(cu06_result, 'team_board_results') or {})
    league = _string_keys(_get(cu06_result, 'league_row_results') or {})
    matchups = _string_keys(_get(cu06_result, 'matchup_results') or {})
    tonight = _string_keys(_get(cu06_result, 'tonight_results') or {})

    errors = []
    if _get(cu06_result, 'status') != STATUS_COMPLETE:
        errors.append('cu06_not_complete')
    if _get(cu06_result, 'parity_status') != PARITY_MATCH:
        errors.append('cu06_parity_not_matched')
    if not _get(cu06_result, 'rebuild_performed'):
        errors.append('cu06_rebuild_not_performed')
    if _get(cu06_result, 'failures'):
        errors.append('cu06_failures_present')
    if _get(cu06_result, 'parity_mismatches'):
        errors.append('cu06_parity_mismatches_present')
    if not represented_date:
        errors.append('represented_date_missing')
    else:
        try:
            date.fromisoformat(str(represented_date))
        except ValueError:
            errors.append('represented_date_invalid')
    if not str(source_identity or '').strip():
        errors.append('source_identity_missing')
    if not isinstance(source_order, int) or isinstance(source_order, bool) or source_order < 0:
        errors.append('source_order_invalid')
    if not team_ids:
        errors.append('affected_teams_missing')

    expected_teams = {str(value) for value in team_ids}
    if set(_get(cu06_result, 'team_boards_rebuilt') or ()) != set(team_ids):
        errors.append('team_board_rebuild_identity_mismatch')
    if set(_get(cu06_result, 'league_rows_rebuilt') or ()) != set(team_ids):
        errors.append('league_rebuild_identity_mismatch')
    if set(boards) != expected_teams:
        errors.append('team_board_cohort_incomplete')
    if set(league) != expected_teams:
        errors.append('league_cohort_incomplete')
    expected_games = {str(value) for value in game_ids}
    if set(_get(cu06_result, 'matchups_rebuilt') or ()) != set(game_ids):
        errors.append('matchup_rebuild_identity_mismatch')
    if set(_get(cu06_result, 'tonight_entries_rebuilt') or ()) != set(game_ids):
        errors.append('tonight_rebuild_identity_mismatch')
    if set(matchups) != expected_games:
        errors.append('matchup_cohort_incomplete')
    if set(tonight) != expected_games:
        errors.append('tonight_cohort_incomplete')

    semantic = _semantic({
        'contract': COHORT_CONTRACT,
        'represented_date': str(represented_date) if represented_date else None,
        'affected_team_ids': team_ids,
        'affected_game_ids': game_ids,
        'surfaces': {
            'team_boards': boards,
            'league_rows': league,
            'matchups': matchups,
            'tonight_entries': tonight,
        },
    })
    semantic_fingerprint = _fingerprint(semantic)
    identity = {
        'semantic_fingerprint': semantic_fingerprint,
        'source_identity': str(source_identity or ''),
        'source_order': source_order,
    }
    candidate_id = _fingerprint(identity)
    payload = {
        'publication': {
            'contract': COHORT_CONTRACT,
            'candidate_id': candidate_id,
            'semantic_fingerprint': semantic_fingerprint,
            'represented_date': str(represented_date) if represented_date else None,
            'source_identity': str(source_identity or ''),
            'source_order': source_order,
            'affected_team_ids': list(team_ids),
            'affected_game_ids': list(game_ids),
        },
        'surfaces': semantic['surfaces'],
    }
    return PublicationCandidate(
        candidate_id=candidate_id,
        semantic_fingerprint=semantic_fingerprint,
        represented_date=str(represented_date) if represented_date else '',
        source_identity=str(source_identity or ''),
        source_order=source_order,
        affected_team_ids=team_ids,
        affected_game_ids=game_ids,
        payload=payload,
        validation_errors=tuple(errors),
    )


def stage_candidate(candidate, *, sync_run_id):
    """Persist a validated, non-serving candidate in the isolated namespace."""
    if not candidate.valid:
        return None
    existing = _snapshot_for_candidate(candidate.candidate_id)
    if existing is not None:
        return existing
    row = DashboardSnapshot(
        snapshot_type=PROOF_SNAPSHOT_TYPE,
        sync_run_id=sync_run_id,
        status=STATUS_STAGED,
        is_published=False,
        payload=candidate.payload,
        payload_version=1,
        data_through=date.fromisoformat(candidate.represented_date),
        availability_reference_date=date.fromisoformat(candidate.represented_date),
        source=PROOF_SOURCE,
    )
    db.session.add(row)
    db.session.commit()
    return row


def publish_incremental(
    cu06_result,
    *,
    source_identity,
    source_order,
    sync_run_id,
    expected_current_id,
    cache_adapter=None,
    failure_hook=None,
):
    """Validate, stage, atomically commit, then hand off an optional test cache."""
    build_started = perf_counter()
    candidate = build_candidate(
        cu06_result, source_identity=source_identity, source_order=source_order,
    )
    build_validation_ms = _ms(build_started)
    if not candidate.valid:
        return _result(
            candidate, RESULT_ABORTED, 'cohort_validation_failed',
            build_validation_ms=build_validation_ms,
            errors=candidate.validation_errors,
        )

    current = get_current_publication()
    if current is not None:
        current_meta = _publication_meta(current)
        if current_meta.get('semantic_fingerprint') == candidate.semantic_fingerprint:
            return _result(
                candidate, RESULT_NO_ACTION, 'semantic_no_change',
                previous_publication_id=current.id,
                build_validation_ms=build_validation_ms,
            )

    stage_started = perf_counter()
    try:
        staged = stage_candidate(candidate, sync_run_id=sync_run_id)
    except Exception as exc:  # noqa: BLE001 - structured proof failure
        db.session.rollback()
        return _result(
            candidate, RESULT_ABORTED, 'stage_failed', rollback_performed=True,
            build_validation_ms=build_validation_ms,
            errors=(type(exc).__name__,),
        )
    stage_ms = _ms(stage_started)
    if failure_hook:
        try:
            failure_hook('after_stage', candidate, staged)
        except Exception as exc:  # noqa: BLE001 - staged rows remain non-serving
            db.session.rollback()
            return _result(
                candidate, RESULT_ABORTED, 'pre_commit_failed',
                previous_publication_id=current.id if current else None,
                rollback_performed=True, stage_ms=stage_ms,
                build_validation_ms=build_validation_ms,
                errors=(type(exc).__name__,),
            )

    commit_started = perf_counter()
    try:
        previous_id, new_id = _commit_candidate(
            staged.id,
            expected_current_id=expected_current_id,
            failure_hook=failure_hook,
        )
    except PublicationRejected as exc:
        db.session.rollback()
        return _result(
            candidate, exc.status, exc.reason_code,
            previous_publication_id=exc.current_id,
            build_validation_ms=build_validation_ms,
            stage_ms=stage_ms,
        )
    except Exception as exc:  # noqa: BLE001 - rollback is the contract
        db.session.rollback()
        return _result(
            candidate, RESULT_ABORTED, 'commit_failed',
            previous_publication_id=expected_current_id,
            rollback_performed=True, stage_ms=stage_ms,
            build_validation_ms=build_validation_ms,
            commit_ms=_ms(commit_started), errors=(type(exc).__name__,),
        )
    commit_ms = _ms(commit_started)

    keys = cache_keys(candidate)
    cache_status = 'not_configured'
    cache_ms = 0.0
    errors = ()
    status = RESULT_COMMITTED
    if cache_adapter is not None:
        cache_started = perf_counter()
        try:
            cache_adapter.handoff(new_id, candidate.payload, keys)
            cache_status = 'complete'
        except Exception as exc:  # noqa: BLE001 - cache is non-authoritative
            cache_status = 'retry_required'
            status = RESULT_CACHE_PENDING
            errors = (type(exc).__name__,)
        cache_ms = _ms(cache_started)
    return _result(
        candidate, status, 'authority_committed',
        previous_publication_id=previous_id,
        new_publication_id=new_id,
        committed=True,
        cache_handoff_status=cache_status,
        cache_keys=keys,
        build_validation_ms=build_validation_ms,
        stage_ms=stage_ms,
        commit_ms=commit_ms,
        cache_ms=cache_ms,
        errors=errors,
    )


def retry_cache_handoff(
    publication_id,
    cache_adapter,
    *,
    expected_candidate_id=None,
    expected_payload_version=None,
):
    """Idempotently populate versioned cache entries after durable commit."""
    row = db.session.get(DashboardSnapshot, publication_id)
    if row is None or row.snapshot_type != PROOF_SNAPSHOT_TYPE or not row.is_published:
        raise ValueError('Cache handoff requires the current CU-07 proof publication')
    meta = _publication_meta(row)
    if (
        expected_candidate_id is not None
        and meta.get('candidate_id') != expected_candidate_id
    ):
        raise ValueError('Cache handoff proof publication identity mismatch')
    if (
        expected_payload_version is not None
        and row.payload_version != expected_payload_version
    ):
        raise ValueError('Cache handoff proof publication version mismatch')
    candidate = PublicationCandidate(
        candidate_id=meta['candidate_id'],
        semantic_fingerprint=meta['semantic_fingerprint'],
        represented_date=meta['represented_date'],
        source_identity=meta['source_identity'],
        source_order=meta['source_order'],
        affected_team_ids=tuple(meta['affected_team_ids']),
        affected_game_ids=tuple(meta['affected_game_ids']),
        payload=row.payload,
    )
    keys = cache_keys(candidate)
    cache_adapter.handoff(row.id, row.payload, keys)
    return keys


def recover_committed_publication_receipt(
    candidate_id,
    *,
    expected_publication_id=None,
    expected_team_ids=(),
    expected_game_ids=(),
    expected_payload_version=1,
):
    """Recover one exact current proof publication after orchestration loss."""
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError('Proof publication recovery candidate identity is required')
    rows = (
        DashboardSnapshot.query
        .filter_by(
            snapshot_type=PROOF_SNAPSHOT_TYPE,
            is_published=True,
            status=STATUS_CURRENT,
        )
        .order_by(DashboardSnapshot.id.asc())
        .limit(2)
        .all()
    )
    if len(rows) > 1:
        raise ValueError('Proof publication recovery authority is ambiguous')
    if not rows:
        return None

    row = rows[0]
    if expected_publication_id is not None and row.id != expected_publication_id:
        raise ValueError('Proof publication recovery publication identity mismatch')
    if row.payload_version != expected_payload_version:
        raise ValueError('Proof publication recovery payload version mismatch')
    meta = _publication_meta(row)
    if meta.get('candidate_id') != candidate_id:
        return None
    if tuple(meta.get('affected_team_ids') or ()) != tuple(expected_team_ids):
        raise ValueError('Proof publication recovery team identity mismatch')
    if tuple(meta.get('affected_game_ids') or ()) != tuple(expected_game_ids):
        raise ValueError('Proof publication recovery game identity mismatch')
    return {
        'publication_id': row.id,
        'candidate_id': candidate_id,
        'snapshot_type': PROOF_SNAPSHOT_TYPE,
        'payload_version': row.payload_version,
    }


def get_current_publication():
    return (
        DashboardSnapshot.query
        .filter_by(
            snapshot_type=PROOF_SNAPSHOT_TYPE,
            is_published=True,
            status=STATUS_CURRENT,
        )
        .order_by(DashboardSnapshot.id.desc())
        .first()
    )


def read_current_cohort(*, cache_adapter=None):
    """Read one coherent manifest; cache entries are valid only for its DB id."""
    current = get_current_publication()
    if current is None:
        return None
    if cache_adapter is not None:
        cached = cache_adapter.read(current.id)
        if cached is not None:
            return cached
    return current.payload


def cache_keys(candidate):
    keys = [f'team_board:{team_id}' for team_id in candidate.affected_team_ids]
    keys.extend(f'league_row:{team_id}' for team_id in candidate.affected_team_ids)
    keys.extend(f'matchup:{game_id}' for game_id in candidate.affected_game_ids)
    keys.extend(f'tonight:{game_id}' for game_id in candidate.affected_game_ids)
    return tuple(keys)


class PublicationRejected(RuntimeError):
    def __init__(self, status, reason_code, current_id=None):
        super().__init__(reason_code)
        self.status = status
        self.reason_code = reason_code
        self.current_id = current_id


def _commit_candidate(staged_id, *, expected_current_id, failure_hook=None):
    _acquire_authority_lock()
    currents = (
        DashboardSnapshot.query
        .filter_by(snapshot_type=PROOF_SNAPSHOT_TYPE, is_published=True)
        .with_for_update()
        .all()
    )
    if len(currents) > 1:
        raise PublicationRejected(RESULT_CONFLICT, 'multiple_current_publications')
    current = currents[0] if currents else None
    current_id = current.id if current else None
    if current_id != expected_current_id:
        raise PublicationRejected(RESULT_CONFLICT, 'expected_current_mismatch', current_id)

    staged = (
        DashboardSnapshot.query
        .filter_by(id=staged_id, snapshot_type=PROOF_SNAPSHOT_TYPE)
        .with_for_update()
        .one()
    )
    candidate_meta = _publication_meta(staged)
    if staged.is_published:
        if staged.id == current_id:
            return current_id, staged.id
        raise PublicationRejected(RESULT_CONFLICT, 'candidate_already_published', current_id)
    if staged.status != STATUS_STAGED:
        raise PublicationRejected(RESULT_CONFLICT, 'candidate_not_staged', current_id)

    if current is not None:
        current_meta = _publication_meta(current)
        current_order = (
            current_meta.get('represented_date'), current_meta.get('source_order'),
        )
        candidate_order = (
            candidate_meta.get('represented_date'), candidate_meta.get('source_order'),
        )
        if candidate_order < current_order:
            raise PublicationRejected(RESULT_STALE, 'candidate_older_than_current', current_id)
        if candidate_order == current_order:
            raise PublicationRejected(RESULT_CONFLICT, 'candidate_order_ambiguous', current_id)

    if failure_hook:
        failure_hook('before_pointer_swap', staged, current)
    if current is not None:
        current.is_published = False
    staged.status = STATUS_CURRENT
    staged.is_published = True
    staged.published_at = utc_now_naive()
    db.session.flush()
    if failure_hook:
        failure_hook('before_commit', staged, current)
    db.session.commit()
    return current_id, staged.id


def _acquire_authority_lock():
    bind = db.session.get_bind()
    if bind.dialect.name == 'postgresql':
        db.session.execute(
            text('SELECT pg_advisory_xact_lock(:lock_key)'),
            {'lock_key': _ADVISORY_LOCK_KEY},
        )


def _snapshot_for_candidate(candidate_id):
    rows = (
        DashboardSnapshot.query
        .filter_by(snapshot_type=PROOF_SNAPSHOT_TYPE)
        .order_by(DashboardSnapshot.id.desc())
        .all()
    )
    return next(
        (row for row in rows if _publication_meta(row).get('candidate_id') == candidate_id),
        None,
    )


def _publication_meta(row):
    return ((row.payload or {}).get('publication') or {})


def _semantic(value):
    if isinstance(value, dict):
        return {
            str(key): _semantic(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
            if key not in NON_SEMANTIC_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_semantic(item) for item in value]
    return value


def _string_keys(value):
    return {str(key): item for key, item in value.items()}


def _fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), default=str)
    return sha256(encoded.encode('utf-8')).hexdigest()


def _result(candidate, status, reason_code, **kwargs):
    return IncrementalPublicationResult(
        candidate_id=candidate.candidate_id,
        status=status,
        reason_code=reason_code,
        affected_team_ids=candidate.affected_team_ids,
        affected_game_ids=candidate.affected_game_ids,
        validation_passed=candidate.valid,
        **kwargs,
    )


def _get(value, field):
    return value.get(field) if isinstance(value, dict) else getattr(value, field, None)


def _ms(started):
    return round((perf_counter() - started) * 1000.0, 3)
