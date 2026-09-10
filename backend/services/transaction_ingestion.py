from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
import hashlib
import logging

from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from models.roster_membership import PlayerTransactionVersion
from models.roster_status_snapshot import RosterStatusSnapshot
from services import dead_letter, source_provenance
from services.canonical_transaction_pitcher_acquisition import (
    acquire_canonical_transaction_pitchers,
)
from services.mlb_api import mlb_client
from services.source_observations import (
    ObservationCompleteness,
    PayloadKind,
    SourceProvider,
    SourceSubjectType,
    build_source_identity,
    canonical_record_collection,
    record_source_fetch_failure,
    record_source_observation,
    stable_json_dumps,
    stable_json_value,
)
from services.sync_control_plane import SourceDomain
from services.transaction_participant_qualification import (
    AUTHORITY_MLB_TRANSACTION,
    qualification_from_position,
    qualify_transactions_with_people,
    pitcher_qualification,
    source_position,
    unresolved_qualification,
)
from services.transaction_rehab_assignment import classify_rehab_assignment
from services.transaction_roster_evidence import acquire_transaction_roster_evidence
from utils.db import db
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)

SOURCE_PREFIX = 'mlb_stats_api:transactions'
SOURCE_ENDPOINT = '/transactions'
TRANSACTION_SYNC_WINDOW_DAYS = 7
TRANSACTION_STALE_AFTER_DAYS = 2
TRANSACTION_FETCH_LIMIT = 1000
TRANSACTION_FACT_SCHEMA_VERSION = 1

TRANSACTION_FETCH_ENTITY_TYPE = 'player_transactions_fetch'
TRANSACTION_SHAPE_ENTITY_TYPE = 'player_transactions_shape'
TRANSACTION_IDENTITY_ENTITY_TYPE = 'player_transactions_identity'
TRANSACTION_FAILURE_ENTITY_TYPES = (
    TRANSACTION_FETCH_ENTITY_TYPE,
    TRANSACTION_SHAPE_ENTITY_TYPE,
    TRANSACTION_IDENTITY_ENTITY_TYPE,
)

CATEGORY_RECALL = 'recall'
CATEGORY_OPTION = 'option'
CATEGORY_IL_PLACEMENT = 'il_placement'
CATEGORY_IL_ACTIVATION = 'il_activation'
CATEGORY_ROSTER_ACTIVATION = 'roster_activation'
CATEGORY_ROSTER_DEACTIVATION = 'roster_deactivation'
CATEGORY_TRADE = 'trade'
CATEGORY_DFA = 'dfa'
CATEGORY_OUTRIGHT = 'outright'
CATEGORY_RELEASE = 'release'
CATEGORY_CONTRACT_SELECTION = 'contract_selection'
CATEGORY_WAIVER_CLAIM = 'waiver_claim'
CATEGORY_SUSPENSION = 'suspension'
CATEGORY_BEREAVEMENT = 'bereavement'
CATEGORY_PATERNITY = 'paternity'
CATEGORY_RESTRICTED = 'restricted'
CATEGORY_UNKNOWN = 'unknown'

ALIGNMENT_ALIGNED = 'aligned'
ALIGNMENT_MISALIGNED = 'misaligned'
ALIGNMENT_UNKNOWN = 'unknown'
ALIGNMENT_NO_SNAPSHOT = 'no_snapshot'
ALIGNMENT_NOT_APPLICABLE = 'not_applicable'

WINDOW_STATUS_SUCCESS = 'success'
WINDOW_STATUS_PARTIAL = 'partial'
WINDOW_STATUS_FAILED = 'failed'

NON_PLAYER_TRANSACTION_REASON = 'non_player_transaction'

_CATEGORY_BY_TYPE_CODE = {
    'RECALL': CATEGORY_RECALL,
    'RECALLED': CATEGORY_RECALL,
    'RC': CATEGORY_RECALL,
    'REC': CATEGORY_RECALL,
    'CU': CATEGORY_RECALL,
    'OPTION': CATEGORY_OPTION,
    'OPTIONED': CATEGORY_OPTION,
    'OPT': CATEGORY_OPTION,
    'IL': CATEGORY_IL_PLACEMENT,
    'IL_7': CATEGORY_IL_PLACEMENT,
    'IL_10': CATEGORY_IL_PLACEMENT,
    'IL_15': CATEGORY_IL_PLACEMENT,
    'IL_60': CATEGORY_IL_PLACEMENT,
    'D7': CATEGORY_IL_PLACEMENT,
    'D10': CATEGORY_IL_PLACEMENT,
    'D15': CATEGORY_IL_PLACEMENT,
    'D60': CATEGORY_IL_PLACEMENT,
    'PLACED_ON_IL': CATEGORY_IL_PLACEMENT,
    'IL_PLACEMENT': CATEGORY_IL_PLACEMENT,
    'ACTIVATED_FROM_IL': CATEGORY_IL_ACTIVATION,
    'REINSTATED_FROM_IL': CATEGORY_IL_ACTIVATION,
    'IL_ACTIVATION': CATEGORY_IL_ACTIVATION,
    'ACT': CATEGORY_ROSTER_ACTIVATION,
    'ACTIVATED': CATEGORY_ROSTER_ACTIVATION,
    'ROSTER_ACTIVATION': CATEGORY_ROSTER_ACTIVATION,
    'DEACTIVATED': CATEGORY_ROSTER_DEACTIVATION,
    'ROSTER_DEACTIVATION': CATEGORY_ROSTER_DEACTIVATION,
    'TRADE': CATEGORY_TRADE,
    'TRADED': CATEGORY_TRADE,
    'TRD': CATEGORY_TRADE,
    'DFA': CATEGORY_DFA,
    'DESIGNATED_FOR_ASSIGNMENT': CATEGORY_DFA,
    'DES': CATEGORY_DFA,
    'OUTRIGHT': CATEGORY_OUTRIGHT,
    'OUTRIGHTED': CATEGORY_OUTRIGHT,
    'OUT': CATEGORY_OUTRIGHT,
    'RELEASE': CATEGORY_RELEASE,
    'RELEASED': CATEGORY_RELEASE,
    'REL': CATEGORY_RELEASE,
    'CONTRACT_SELECTION': CATEGORY_CONTRACT_SELECTION,
    'SELECTED': CATEGORY_CONTRACT_SELECTION,
    'SELECTION': CATEGORY_CONTRACT_SELECTION,
    'SE': CATEGORY_CONTRACT_SELECTION,
    'CLW': CATEGORY_WAIVER_CLAIM,
    'SUSPENSION': CATEGORY_SUSPENSION,
    'SUSPENDED': CATEGORY_SUSPENSION,
    'SUS': CATEGORY_SUSPENSION,
    'BEREAVEMENT': CATEGORY_BEREAVEMENT,
    'BRV': CATEGORY_BEREAVEMENT,
    'PATERNITY': CATEGORY_PATERNITY,
    'PAT': CATEGORY_PATERNITY,
    'RESTRICTED': CATEGORY_RESTRICTED,
    'RST': CATEGORY_RESTRICTED,
}

_IL_LIST_BY_VALUE = {
    '7': '7_day',
    '7_DAY': '7_day',
    '7_DAY_IL': '7_day',
    '7-DAY': '7_day',
    '10': '10_day',
    '10_DAY': '10_day',
    '10_DAY_IL': '10_day',
    '10-DAY': '10_day',
    '15': '15_day',
    '15_DAY': '15_day',
    '15_DAY_IL': '15_day',
    '15-DAY': '15_day',
    '60': '60_day',
    '60_DAY': '60_day',
    '60_DAY_IL': '60_day',
    '60-DAY': '60_day',
}

_TRANSACTION_FACT_FIELDS = (
    'transaction_id',
    'pitcher_id',
    'player_mlb_id',
    'from_team_id',
    'to_team_id',
    'transaction_date',
    'effective_date',
    'resolution_date',
    'transaction_type_code',
    'transaction_type_description',
    'normalized_category',
    'is_il_placement',
    'is_il_activation',
    'il_list_type',
    'retroactive_date',
    'roster_snapshot_alignment',
    'alignment_reason_code',
    'explanatory_linkage_eligible',
    'participant_role',
    'participant_role_authority',
    'participant_position_code',
    'participant_position_abbreviation',
    'participant_position_type',
    'transaction_subtype',
    'transaction_materiality',
    'subtype_status',
    'subtype_authority',
    'subtype_reason_code',
    'subtype_evidence',
    'source',
    'source_endpoint',
    'source_query_start_date',
    'source_query_end_date',
)

_TRANSACTION_VERSION_FACT_FIELDS = tuple(
    field for field in _TRANSACTION_FACT_FIELDS
    if field not in {'source_query_start_date', 'source_query_end_date'}
)

_SNAPSHOT_NOT_PROVIDED = object()

# Public alias of the canonical stored-transaction fact fields, so read-only
# consumers (for example the intraday reconciliation audit) can compare a source
# transaction against a stored row without importing a private name.
TRANSACTION_FACT_FIELDS = _TRANSACTION_FACT_FIELDS


def normalize_transaction_category(type_code):
    code = _normalized_source_code(type_code)
    if not code:
        return CATEGORY_UNKNOWN
    return _CATEGORY_BY_TYPE_CODE.get(code, CATEGORY_UNKNOWN)


def is_non_player_transaction(transaction):
    """
    True when the source row carries no person reference of any kind.

    The MLB transactions feed includes team-level transaction components (for
    example cash considerations, players to be named later, or international
    slot money in a trade) that reference no person. The structured client
    maps every person-bearing source shape (``person``/``player`` objects and
    the flat id/name variants) into ``player_mlb_id`` and
    ``player_full_name``; when both are absent, the source row is a non-player
    fact, not a malformed player row, so requiring player identity from it is
    a category error. A row that does reference a person (a name is present)
    but lacks a usable id remains an identity failure and fails closed.
    """
    if not isinstance(transaction, dict):
        return False
    return (
        _int_or_none(transaction.get('player_mlb_id')) is None
        and _string_or_none(transaction.get('player_full_name')) is None
    )


def sync_transactions(
    *,
    start_date=None,
    end_date=None,
    client=None,
    timestamp=None,
    commit=True,
    sync_run_id=None,
    sync_job_id=None,
    team_id=None,
):
    client = client or mlb_client
    timestamp = timestamp or utc_now_naive()
    end_date = _coerce_date(end_date) or timestamp.date()
    start_date = (
        _coerce_date(start_date)
        or (end_date - timedelta(days=TRANSACTION_SYNC_WINDOW_DAYS))
    )
    window_ref = _window_ref(start_date, end_date)
    source_identity = _transaction_source_identity(start_date, end_date, team_id=team_id)
    fetch_started_at = utc_now_naive()

    counts = Counter()
    errors = []
    transactions = None
    try:
        collection_reader = getattr(
            type(client), 'get_transactions_with_completeness', None,
        )
        if callable(collection_reader):
            collection = client.get_transactions_with_completeness(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                team_id=team_id,
                limit=TRANSACTION_FETCH_LIMIT,
            )
            transactions = collection.records
            source_completeness = collection.completeness
            completeness_proof = dict(collection.proof or {})
        else:
            transactions = client.get_transactions(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                team_id=team_id,
            )
            source_completeness = (
                ObservationCompleteness.COMPLETE.value
                if isinstance(transactions, list)
                else ObservationCompleteness.UNKNOWN.value
            )
            completeness_proof = {'legacy_client_contract': True}
    except Exception as exc:  # noqa: BLE001 - source failure degrades this family only
        try:
            record_source_fetch_failure(
                identity=source_identity,
                error=exc,
                attempt_started_at=fetch_started_at,
                http_status=getattr(exc, 'status_code', None),
                sync_run_id=sync_run_id,
                sync_job_id=sync_job_id,
                commit=False,
            )
        except Exception:  # evidence failure must not replace established failure flow
            logger.exception('Could not persist failed transaction fetch evidence')
        detail = {
            'reason': 'fetch_failed',
            'source_endpoint': SOURCE_ENDPOINT,
            'source_query_start_date': start_date.isoformat(),
            'source_query_end_date': end_date.isoformat(),
            'error': str(exc),
        }
        if _record_transaction_failure(
            TRANSACTION_FETCH_ENTITY_TYPE,
            detail,
            entity_ref=window_ref,
            sync_run_id=sync_run_id,
        ):
            counts['records_failed'] += 1
        counts['errors'] += 1
        errors.append(detail)
        _record_sync_window(
            start_date=start_date,
            end_date=end_date,
            timestamp=timestamp,
            status=WINDOW_STATUS_FAILED,
            counts=counts,
            sync_run_id=sync_run_id,
        )
        if commit:
            db.session.commit()
        return _summary(start_date, end_date, counts, errors)

    response_was_list = isinstance(transactions, list)
    if not response_was_list:
        transactions = []

    try:
        completeness = ObservationCompleteness(source_completeness)
    except ValueError:
        completeness = ObservationCompleteness.UNKNOWN

    source_result = record_source_observation(
        identity=source_identity,
        payload=transactions,
        fingerprint_payload=canonical_record_collection(transactions),
        completeness=completeness,
        payload_schema_version=1,
        payload_kind=PayloadKind.NORMALIZED_JSON,
        record_count=len(transactions),
        empty_valid=(
            completeness == ObservationCompleteness.COMPLETE and not transactions
        ),
        attempt_started_at=fetch_started_at,
        sync_run_id=sync_run_id,
        sync_job_id=sync_job_id,
        commit=False,
    )
    counts['source_observation_id'] = source_result.observation.id
    counts['source_observation_outcome'] = source_result.outcome
    counts['source_observation_changed'] = source_result.changed

    counts['records_fetched'] = len(transactions)
    counts['completeness'] = completeness.value
    counts['completeness_proof'] = completeness_proof
    if completeness != ObservationCompleteness.COMPLETE:
        detail = {
            'reason': 'transaction_collection_not_complete',
            'completeness': completeness.value,
            'proof': completeness_proof,
        }
        errors.append(detail)
        counts['errors'] += 1
        _record_sync_window(
            start_date=start_date,
            end_date=end_date,
            timestamp=timestamp,
            status=WINDOW_STATUS_PARTIAL,
            counts=counts,
            sync_run_id=sync_run_id,
            source_observation_id=source_result.observation.id,
        )
        if commit:
            db.session.commit()
        return _summary(start_date, end_date, counts, errors)
    participant_ids = {
        _int_or_none(transaction.get('player_mlb_id'))
        for transaction in transactions
        if isinstance(transaction, dict)
    }
    participant_ids.discard(None)
    pitchers_by_mlb_id = {
        pitcher.mlb_id: pitcher
        for pitcher in (
            Pitcher.query.filter(Pitcher.mlb_id.in_(participant_ids)).all()
            if participant_ids else []
        )
    }
    qualification_batch = qualify_transactions_with_people(
        transactions,
        pitchers_by_mlb_id=pitchers_by_mlb_id,
        client=client,
    )
    participant_qualifications = qualification_batch.qualifications
    acquisition = acquire_canonical_transaction_pitchers(
        people_by_mlb_id=qualification_batch.people_by_mlb_id,
        pitchers_by_mlb_id=pitchers_by_mlb_id,
    )
    pitchers_by_mlb_id = acquisition['pitchers_by_mlb_id']
    for mlb_id in acquisition['candidate_ids']:
        if mlb_id in pitchers_by_mlb_id:
            participant_qualifications[mlb_id] = pitcher_qualification()
    transaction_dates = {
        value
        for value in (
            _coerce_date(transaction.get('transaction_date'))
            for transaction in transactions
            if isinstance(transaction, dict)
        )
        if value is not None
    }
    team_metadata_by_season = {}
    metadata_reader = getattr(client, 'get_team_metadata', None)
    for season in sorted({value.year for value in transaction_dates}):
        try:
            team_metadata_by_season[season] = (
                metadata_reader(season) if callable(metadata_reader) else {}
            ) or {}
        except Exception:  # fail closed; missing metadata cannot certify a subtype
            team_metadata_by_season[season] = {}
    roster_acquisition = acquire_transaction_roster_evidence(
        transactions=transactions,
        newly_resolved_mlb_ids=acquisition['candidate_ids'],
        pitchers_by_mlb_id=pitchers_by_mlb_id,
        team_metadata_by_season=team_metadata_by_season,
        client=client,
        timestamp=timestamp,
        sync_run_id=sync_run_id,
    )
    counts.update({
        f'exact_roster_{key}': value
        for key, value in roster_acquisition.items()
        if key != 'error_details'
    })
    roster_snapshots_by_pair = _exact_roster_snapshots_by_pitcher_and_date(
        pitcher_ids={pitcher.id for pitcher in pitchers_by_mlb_id.values()},
        snapshot_dates=transaction_dates,
    )
    for transaction in transactions:
        if not isinstance(transaction, dict):
            detail = {
                'reason': 'shape_surprise',
                'source_endpoint': SOURCE_ENDPOINT,
                'source_query_start_date': start_date.isoformat(),
                'source_query_end_date': end_date.isoformat(),
                'error': 'Transaction row is not an object',
            }
            if _record_transaction_failure(
                TRANSACTION_SHAPE_ENTITY_TYPE,
                detail,
                entity_ref=window_ref,
                sync_run_id=sync_run_id,
            ):
                counts['records_failed'] += 1
            counts['errors'] += 1
            errors.append(detail)
            continue

        if is_non_player_transaction(transaction):
            # Deterministic source-shape classification: no person reference
            # exists anywhere in the row, so player identity is not required.
            # The row is intentionally ignored for player roster purposes and
            # never enters player calculations. Prior identity dead letters
            # for this exact source record are resolved as reprocessed.
            counts['non_player_count'] += 1
            transaction_ref = _string_or_none(transaction.get('transaction_id'))
            logger.info(
                'Transaction %s classified %s (type_code=%s); '
                'player identity not required.',
                transaction_ref,
                NON_PLAYER_TRANSACTION_REASON,
                _string_or_none(transaction.get('transaction_type_code')),
            )
            if transaction_ref:
                dead_letter.resolve_entity_failures(
                    TRANSACTION_IDENTITY_ENTITY_TYPE,
                    transaction_ref,
                    job_name='daily_sync',
                )
            continue

        values, detail = _values_from_transaction(
            transaction,
            start_date=start_date,
            end_date=end_date,
            timestamp=timestamp,
            sync_run_id=sync_run_id,
            pitchers_by_mlb_id=pitchers_by_mlb_id,
            participant_qualifications=participant_qualifications,
            roster_snapshots_by_pair=roster_snapshots_by_pair,
            team_metadata_by_season=team_metadata_by_season,
        )
        if detail:
            if _record_transaction_failure(
                detail['entity_type'],
                detail,
                entity_ref=detail.get('entity_ref') or window_ref,
                sync_run_id=sync_run_id,
            ):
                counts['records_failed'] += 1
            counts['errors'] += 1
            errors.append(detail)
            continue

        row, action = _upsert_player_transaction(
            values,
            sync_run_id=sync_run_id,
            timestamp=timestamp,
            source_observation_id=source_result.observation.id,
        )
        if row is None:
            continue

        # Successful reprocessing of this exact source record resolves any
        # prior identity dead letters recorded against it (idempotent; the
        # historical rows are preserved with a resolution timestamp).
        stored_ref = _string_or_none(values.get('transaction_id'))
        if stored_ref:
            dead_letter.resolve_entity_failures(
                TRANSACTION_IDENTITY_ENTITY_TYPE,
                stored_ref,
                job_name='daily_sync',
            )

        counts['records_stored'] += 1
        counts[f'records_{action}'] += 1
        if action in {'created', 'corrected'}:
            affected_players = set(counts.get('affected_player_mlb_ids') or ())
            affected_players.add(row.player_mlb_id)
            counts['affected_player_mlb_ids'] = sorted(affected_players)
            affected_teams = set(counts.get('affected_team_ids') or ())
            affected_teams.update(
                value for value in (row.from_team_id, row.to_team_id)
                if value is not None
            )
            counts['affected_team_ids'] = sorted(affected_teams)
        if row.normalized_category == CATEGORY_UNKNOWN:
            counts['unknown_type_count'] += 1
        if row.roster_snapshot_alignment == ALIGNMENT_UNKNOWN:
            counts['alignment_unknown_count'] += 1
        elif row.roster_snapshot_alignment == ALIGNMENT_MISALIGNED:
            counts['alignment_misaligned_count'] += 1
        elif row.roster_snapshot_alignment == ALIGNMENT_NO_SNAPSHOT:
            counts['alignment_no_snapshot_count'] += 1

    if not errors:
        dead_letter.resolve_entity_failures(
            TRANSACTION_FETCH_ENTITY_TYPE,
            window_ref,
            job_name='daily_sync',
        )

    window_status = WINDOW_STATUS_PARTIAL if counts['records_failed'] else WINDOW_STATUS_SUCCESS
    _record_sync_window(
        start_date=start_date,
        end_date=end_date,
        timestamp=timestamp,
        status=window_status,
        counts=counts,
        sync_run_id=sync_run_id,
        source_observation_id=source_result.observation.id,
    )
    if commit:
        db.session.commit()
    return _summary(start_date, end_date, counts, errors)


def latest_transaction_sync_window(status=None):
    query = PlayerTransactionSyncWindow.query
    if status:
        query = query.filter_by(status=status)
    return (
        query
        .order_by(
            PlayerTransactionSyncWindow.attempted_at.desc(),
            PlayerTransactionSyncWindow.id.desc(),
        )
        .first()
    )


def _values_from_transaction(
    transaction,
    *,
    start_date,
    end_date,
    timestamp,
    sync_run_id,
    pitchers_by_mlb_id=None,
    participant_qualifications=None,
    roster_snapshots_by_pair=None,
    team_metadata_by_season=None,
):
    player_mlb_id = _int_or_none(transaction.get('player_mlb_id'))
    transaction_date = _coerce_date(transaction.get('transaction_date'))
    transaction_id = _string_or_none(transaction.get('transaction_id'))

    if player_mlb_id is None:
        return None, {
            'entity_type': TRANSACTION_IDENTITY_ENTITY_TYPE,
            'entity_ref': transaction_id,
            'reason': 'missing_player_identity',
            'transaction_id': transaction_id,
            'transaction_date': _string_or_none(transaction.get('transaction_date')),
            'transaction_type_code': _string_or_none(transaction.get('transaction_type_code')),
            'error': 'Transaction row missing player identity',
        }
    if transaction_date is None:
        return None, {
            'entity_type': TRANSACTION_SHAPE_ENTITY_TYPE,
            'entity_ref': transaction_id or player_mlb_id,
            'reason': 'missing_transaction_date',
            'transaction_id': transaction_id,
            'player_mlb_id': player_mlb_id,
            'transaction_type_code': _string_or_none(transaction.get('transaction_type_code')),
            'error': 'Transaction row missing transaction date',
        }

    type_code = _string_or_none(transaction.get('transaction_type_code'))
    normalized_category = normalize_transaction_category(type_code)
    pitcher = (
        pitchers_by_mlb_id.get(player_mlb_id)
        if pitchers_by_mlb_id is not None
        else Pitcher.query.filter_by(mlb_id=player_mlb_id).first()
    )
    from_team_id = _int_or_none(transaction.get('from_team_id'))
    to_team_id = _int_or_none(transaction.get('to_team_id'))
    il_list_type = _normalize_il_list_type(transaction.get('il_list_type'))
    qualification = (participant_qualifications or {}).get(player_mlb_id)
    if qualification is None and pitcher is not None:
        qualification = pitcher_qualification()
    if qualification is None:
        qualification = qualification_from_position(
            source_position(transaction),
            authority=AUTHORITY_MLB_TRANSACTION,
        )
    if qualification is None:
        qualification = unresolved_qualification()

    roster_snapshot = _SNAPSHOT_NOT_PROVIDED
    if roster_snapshots_by_pair is not None:
        roster_snapshot = (
            roster_snapshots_by_pair.get((pitcher.id, transaction_date))
            if pitcher is not None else None
        )
    if roster_snapshot is _SNAPSHOT_NOT_PROVIDED:
        roster_snapshot = _latest_exact_roster_snapshot(pitcher, transaction_date)
    values = {
        'transaction_id': transaction_id,
        'pitcher_id': pitcher.id if pitcher else None,
        'player_mlb_id': player_mlb_id,
        'from_team_id': from_team_id,
        'to_team_id': to_team_id,
        'transaction_date': transaction_date,
        'effective_date': _coerce_date(transaction.get('effective_date')),
        'resolution_date': _coerce_date(transaction.get('resolution_date')),
        'transaction_type_code': type_code,
        'transaction_type_description': _string_or_none(
            transaction.get('transaction_type_description')
        ),
        'normalized_category': normalized_category,
        'is_il_placement': normalized_category == CATEGORY_IL_PLACEMENT,
        'is_il_activation': normalized_category == CATEGORY_IL_ACTIVATION,
        'il_list_type': il_list_type,
        'retroactive_date': _coerce_date(transaction.get('retroactive_date')),
        'source': SOURCE_PREFIX,
        'source_endpoint': _string_or_none(transaction.get('source_endpoint')) or SOURCE_ENDPOINT,
        'source_query_start_date': start_date,
        'source_query_end_date': end_date,
        'sync_run_id': sync_run_id,
        'first_seen_at': timestamp,
        'created_at': timestamp,
        'updated_at': timestamp,
    }
    alignment, reason = _alignment_for(
        pitcher=pitcher,
        transaction_date=transaction_date,
        normalized_category=normalized_category,
        from_team_id=from_team_id,
        to_team_id=to_team_id,
        roster_snapshot=roster_snapshot,
    )
    values['roster_snapshot_alignment'] = alignment
    values['alignment_reason_code'] = reason
    values['explanatory_linkage_eligible'] = (
        normalized_category != CATEGORY_UNKNOWN
        and alignment == ALIGNMENT_ALIGNED
    )
    values.update(qualification)
    season_metadata = (team_metadata_by_season or {}).get(transaction_date.year, {})
    values.update(classify_rehab_assignment(
        transaction_type_code=type_code,
        pitcher=pitcher,
        participant_role=qualification.get('participant_role'),
        from_team_id=from_team_id,
        to_team_id=to_team_id,
        transaction_date=transaction_date,
        source_team_metadata=season_metadata.get(from_team_id),
        destination_team_metadata=season_metadata.get(to_team_id),
        roster_snapshot=roster_snapshot,
    ))
    values['transaction_key'] = _transaction_key(values)
    return values, None


def read_transaction_values(
    transaction,
    *,
    start_date,
    end_date,
    timestamp=None,
    sync_run_id=None,
):
    """Read-only classification of one source transaction.

    Returns ``(values, error_detail)`` exactly like the internal ingestion path
    (``values`` is the would-be-stored fact dict including ``transaction_key``,
    ``normalized_category``, resolved ``pitcher_id`` and
    ``roster_snapshot_alignment``; ``error_detail`` names an identity/shape
    failure). It performs only SELECT reads (pitcher + roster-snapshot lookups)
    and **never** adds, flushes, commits, dead-letters, or otherwise mutates the
    database — so audit callers can reuse the canonical classification and the
    ``transaction_key`` dedup without duplicating any logic. This is the public,
    side-effect-free entry point over ``_values_from_transaction``; the daily
    sync's persisting path is unchanged.
    """
    return _values_from_transaction(
        transaction,
        start_date=start_date,
        end_date=end_date,
        timestamp=timestamp or utc_now_naive(),
        sync_run_id=sync_run_id,
    )


def _upsert_player_transaction(
    values, *, sync_run_id=None, timestamp=None, source_observation_id=None,
):
    timestamp = timestamp or utc_now_naive()
    existing = PlayerTransaction.query.filter_by(
        transaction_key=values['transaction_key'],
    ).first()

    if existing is None:
        row = PlayerTransaction(**values)
        source_provenance.apply_initial_source_provenance(
            row,
            source=values['source'],
            sync_run_id=sync_run_id,
            first_seen_at=timestamp,
        )
        db.session.add(row)
        db.session.flush()
        row.source_observation_id = source_observation_id
        _append_transaction_version(
            row, values, source_observation_id=source_observation_id, timestamp=timestamp,
        )
        return row, 'created'

    if existing.current_version_number in (None, 0):
        # Additive migration preserves historical rows as-is. Before any later
        # correction can replace their compatibility projection, snapshot the
        # pre-SP-05 fact set as V1 (with nullable observation when unavailable).
        _append_transaction_version(
            existing,
            {
                field: getattr(existing, field)
                for field in _TRANSACTION_VERSION_FACT_FIELDS
            },
            source_observation_id=existing.source_observation_id,
            timestamp=existing.created_at or timestamp,
        )

    changed = False
    for field in _TRANSACTION_VERSION_FACT_FIELDS:
        if getattr(existing, field) != values[field]:
            setattr(existing, field, values[field])
            changed = True
    # Request-window provenance describes this fetch, not a correction to the
    # baseball event. Refresh it without manufacturing a semantic version.
    existing.source = values['source']
    existing.source_endpoint = values['source_endpoint']
    existing.source_query_start_date = values['source_query_start_date']
    existing.source_query_end_date = values['source_query_end_date']
    existing.sync_run_id = sync_run_id
    existing.source_observation_id = source_observation_id
    existing.updated_at = timestamp
    if changed:
        source_provenance.record_source_correction(
            existing,
            correction_source=values['source'],
            sync_run_id=sync_run_id,
            corrected_at=timestamp,
        )
        _notify_roster_depth_evidence_transaction_correction(
            existing,
            sync_run_id=sync_run_id,
        )
        db.session.add(existing)
        db.session.flush()
        _append_transaction_version(
            existing,
            values,
            source_observation_id=source_observation_id,
            timestamp=timestamp,
        )
        return existing, 'corrected'

    db.session.add(existing)
    db.session.flush()
    return existing, 'unchanged'


def _append_transaction_version(
    transaction, values, *, source_observation_id, timestamp,
):
    facts = stable_json_value({
        field: values.get(field) for field in _TRANSACTION_VERSION_FACT_FIELDS
    })
    fingerprint = hashlib.sha256(stable_json_dumps(facts).encode('utf-8')).hexdigest()
    prior = (
        PlayerTransactionVersion.query
        .filter_by(player_transaction_id=transaction.id)
        .order_by(PlayerTransactionVersion.version_number.desc())
        .first()
    )
    if prior is not None and prior.fact_fingerprint == fingerprint:
        transaction.current_version_number = prior.version_number
        return prior
    version = PlayerTransactionVersion(
        player_transaction_id=transaction.id,
        version_number=(prior.version_number + 1) if prior else 1,
        predecessor_version_id=prior.id if prior else None,
        source_observation_id=source_observation_id,
        fact_fingerprint=fingerprint,
        fact_schema_version=TRANSACTION_FACT_SCHEMA_VERSION,
        fact_json=facts,
        created_at=timestamp,
    )
    db.session.add(version)
    db.session.flush()
    transaction.current_version_number = version.version_number
    return version


def realign_stored_transactions_from_exact_roster(
    transactions,
    *,
    pitchers_by_id,
    roster_snapshots_by_pair,
    sync_run_id=None,
    timestamp=None,
    correction_source='mlb_stats_api:intraday_transaction_roster_repair',
):
    """Re-evaluate stored transactions from one bounded exact-snapshot map.

    The caller owns candidate selection and supplies a prefetched map keyed by
    ``(pitcher_id, transaction_date)``. This helper changes only the three
    roster-alignment facts; event, identity, participant, and historical-team
    authority remain untouched. Corrections share the canonical transaction
    provenance fields and are flushed once after the bounded batch.
    """
    timestamp = timestamp or utc_now_naive()
    corrected = 0
    unchanged = 0
    still_blocked = 0
    corrected_rows = []
    for row in transactions or ():
        snapshot = (roster_snapshots_by_pair or {}).get(
            (row.pitcher_id, row.transaction_date)
        )
        alignment, reason = _alignment_for(
            pitcher=(pitchers_by_id or {}).get(row.pitcher_id),
            transaction_date=row.transaction_date,
            normalized_category=row.normalized_category,
            from_team_id=row.from_team_id,
            to_team_id=row.to_team_id,
            roster_snapshot=snapshot,
        )
        eligible = (
            row.normalized_category != CATEGORY_UNKNOWN
            and alignment == ALIGNMENT_ALIGNED
        )
        changed = (
            row.roster_snapshot_alignment != alignment
            or row.alignment_reason_code != reason
            or bool(row.explanatory_linkage_eligible) != eligible
        )
        if changed:
            row.roster_snapshot_alignment = alignment
            row.alignment_reason_code = reason
            row.explanatory_linkage_eligible = eligible
            row.updated_at = timestamp
            source_provenance.record_source_correction(
                row,
                correction_source=correction_source,
                sync_run_id=sync_run_id,
                corrected_at=timestamp,
            )
            db.session.add(row)
            corrected += 1
            corrected_rows.append(row)
        else:
            unchanged += 1
        if alignment != ALIGNMENT_ALIGNED:
            still_blocked += 1

    db.session.flush()
    _notify_roster_depth_evidence_transaction_corrections(
        corrected_rows,
        sync_run_id=sync_run_id,
    )
    return {
        'corrected': corrected,
        'unchanged': unchanged,
        'still_blocked': still_blocked,
    }


def _notify_roster_depth_evidence_transaction_correction(transaction_row, *, sync_run_id=None):
    try:
        from services.roster_depth_evidence import (
            mark_player_transaction_correction_for_roster_depth,
        )
        return mark_player_transaction_correction_for_roster_depth(
            transaction_row,
            sync_run_id=sync_run_id,
        )
    except Exception as exc:  # noqa: BLE001 - correction marking must not block sync
        logger.warning(
            'Could not mark roster depth evidence for transaction correction id=%s: %s',
            getattr(transaction_row, 'id', None),
            exc,
        )
        return {'marked_count': 0, 'evidence_ids': []}


def _notify_roster_depth_evidence_transaction_corrections(
    transaction_rows,
    *,
    sync_run_id=None,
):
    try:
        from services.roster_depth_evidence import (
            mark_player_transaction_corrections_for_roster_depth,
        )
        return mark_player_transaction_corrections_for_roster_depth(
            transaction_rows,
            sync_run_id=sync_run_id,
        )
    except Exception as exc:  # noqa: BLE001 - correction marking must not block sync
        logger.warning(
            'Could not batch-mark roster depth evidence for transaction '
            'corrections count=%s: %s',
            len(transaction_rows or ()),
            exc,
        )
        return {'marked_count': 0, 'evidence_ids': []}


def _alignment_for(
    *,
    pitcher,
    transaction_date,
    normalized_category,
    from_team_id,
    to_team_id,
    roster_snapshot=_SNAPSHOT_NOT_PROVIDED,
):
    if normalized_category == CATEGORY_UNKNOWN:
        return ALIGNMENT_NOT_APPLICABLE, 'unknown_transaction_category'
    if pitcher is None:
        return ALIGNMENT_UNKNOWN, 'untracked_player_identity'
    snapshot = (
        _latest_exact_roster_snapshot(pitcher, transaction_date)
        if roster_snapshot is _SNAPSHOT_NOT_PROVIDED
        else roster_snapshot
    )
    if snapshot is None:
        return ALIGNMENT_NO_SNAPSHOT, 'roster_snapshot_missing'
    source_team_ids = {team_id for team_id in (from_team_id, to_team_id) if team_id is not None}
    if not source_team_ids:
        return ALIGNMENT_UNKNOWN, 'transaction_team_missing'
    if snapshot.team_id in source_team_ids:
        return ALIGNMENT_ALIGNED, 'roster_snapshot_team_match'
    return ALIGNMENT_MISALIGNED, 'roster_snapshot_team_mismatch'


def _latest_exact_roster_snapshot(pitcher, snapshot_date):
    if pitcher is None or snapshot_date is None:
        return None
    return (
        RosterStatusSnapshot.query
        .filter_by(pitcher_id=pitcher.id, snapshot_date=snapshot_date)
        .order_by(
            RosterStatusSnapshot.updated_at.desc(),
            RosterStatusSnapshot.id.desc(),
        )
        .first()
    )


def _exact_roster_snapshots_by_pitcher_and_date(*, pitcher_ids, snapshot_dates):
    """Prefetch exact-date snapshot authority in one bounded SELECT."""
    pitcher_ids = set(pitcher_ids or ())
    snapshot_dates = set(snapshot_dates or ())
    if not pitcher_ids or not snapshot_dates:
        return {}
    rows = (
        RosterStatusSnapshot.query
        .filter(RosterStatusSnapshot.pitcher_id.in_(pitcher_ids))
        .filter(RosterStatusSnapshot.snapshot_date.in_(snapshot_dates))
        .order_by(
            RosterStatusSnapshot.updated_at.asc(),
            RosterStatusSnapshot.id.asc(),
        )
        .all()
    )
    return {
        (row.pitcher_id, row.snapshot_date): row
        for row in rows
    }


def _record_sync_window(
    *,
    start_date,
    end_date,
    timestamp,
    status,
    counts,
    sync_run_id=None,
    source_observation_id=None,
):
    window = PlayerTransactionSyncWindow(
        source=SOURCE_PREFIX,
        source_endpoint=SOURCE_ENDPOINT,
        source_query_start_date=start_date,
        source_query_end_date=end_date,
        attempted_at=timestamp,
        successful_at=timestamp if status in (WINDOW_STATUS_SUCCESS, WINDOW_STATUS_PARTIAL) else None,
        status=status,
        records_fetched=counts.get('records_fetched', 0),
        records_stored=counts.get('records_stored', 0),
        records_created=counts.get('records_created', 0),
        records_corrected=counts.get('records_corrected', 0),
        records_unchanged=counts.get('records_unchanged', 0),
        unknown_type_count=counts.get('unknown_type_count', 0),
        alignment_unknown_count=counts.get('alignment_unknown_count', 0),
        alignment_misaligned_count=counts.get('alignment_misaligned_count', 0),
        alignment_no_snapshot_count=counts.get('alignment_no_snapshot_count', 0),
        records_failed=counts.get('records_failed', 0),
        sync_run_id=sync_run_id,
        source_observation_id=source_observation_id,
        created_at=timestamp,
    )
    db.session.add(window)
    db.session.flush()
    return window


def _record_transaction_failure(entity_type, detail, *, entity_ref=None, sync_run_id=None):
    payload = dict(detail)
    payload.pop('entity_type', None)
    payload.pop('entity_ref', None)
    # A source record that keeps failing across runs still counts against this
    # run's honesty (records_failed / partial status are unchanged), but it
    # must not accumulate one duplicate unresolved dead-letter row per run.
    # The original row remains the durable record until it is resolved.
    if entity_ref is not None and _unresolved_failure_exists(entity_type, entity_ref):
        logger.warning(
            'Transaction failure repeated for entity_type=%s entity_ref=%s; '
            'existing unresolved dead letter retained without duplication.',
            entity_type,
            entity_ref,
        )
        return True
    failure = dead_letter.record_failure(
        entity_type,
        payload.get('error') or payload.get('reason') or 'Transaction ingest failed',
        entity_ref=entity_ref,
        payload=payload,
        sync_run_id=sync_run_id,
        job_name='daily_sync',
    )
    return failure is not None


def _unresolved_failure_exists(entity_type, entity_ref):
    from models.sync_failure import SyncFailure

    try:
        return db.session.query(
            SyncFailure.query
            .filter_by(
                entity_type=entity_type,
                entity_ref=str(entity_ref),
                job_name='daily_sync',
                resolved=False,
            )
            .exists()
        ).scalar()
    except Exception:  # noqa: BLE001 - never let dedup checks hide a failure
        db.session.rollback()
        return False


def _summary(start_date, end_date, counts, errors):
    return {
        'source': SOURCE_PREFIX,
        'source_endpoint': SOURCE_ENDPOINT,
        'source_query_start_date': start_date.isoformat(),
        'source_query_end_date': end_date.isoformat(),
        'records_fetched': counts.get('records_fetched', 0),
        'records_stored': counts.get('records_stored', 0),
        'records_created': counts.get('records_created', 0),
        'records_corrected': counts.get('records_corrected', 0),
        'records_unchanged': counts.get('records_unchanged', 0),
        'unknown_type_count': counts.get('unknown_type_count', 0),
        'alignment_unknown_count': counts.get('alignment_unknown_count', 0),
        'alignment_misaligned_count': counts.get('alignment_misaligned_count', 0),
        'alignment_no_snapshot_count': counts.get('alignment_no_snapshot_count', 0),
        'non_player_count': counts.get('non_player_count', 0),
        'records_failed': counts.get('records_failed', 0),
        'errors': counts.get('errors', 0),
        'error_details': errors,
        'source_observation_id': counts.get('source_observation_id'),
        'source_observation_outcome': counts.get('source_observation_outcome'),
        'source_observation_changed': counts.get('source_observation_changed'),
        'completeness': counts.get('completeness'),
        'completeness_proof': counts.get('completeness_proof'),
        'affected_player_mlb_ids': counts.get('affected_player_mlb_ids', []),
        'affected_team_ids': counts.get('affected_team_ids', []),
        'exact_roster_newly_resolved_pitchers': counts.get(
            'exact_roster_newly_resolved_pitchers', 0,
        ),
        'exact_roster_eligible_team_date_pairs': counts.get(
            'exact_roster_eligible_team_date_pairs', 0,
        ),
        'exact_roster_requests': counts.get(
            'exact_roster_requests', 0,
        ),
        'exact_roster_source_matches': counts.get(
            'exact_roster_source_matches', 0,
        ),
        'exact_roster_source_omissions': counts.get(
            'exact_roster_source_omissions', 0,
        ),
        'exact_roster_source_conflicts': counts.get(
            'exact_roster_source_conflicts', 0,
        ),
        'exact_roster_fetch_failures': counts.get(
            'exact_roster_fetch_failures', 0,
        ),
        'exact_roster_snapshots_created': counts.get(
            'exact_roster_snapshots_created', 0,
        ),
        'exact_roster_snapshots_unchanged': counts.get(
            'exact_roster_snapshots_unchanged', 0,
        ),
        'exact_roster_snapshot_conflicts': counts.get(
            'exact_roster_snapshot_conflicts', 0,
        ),
    }


def _transaction_source_identity(start_date, end_date, *, team_id=None):
    parameters = {
        'sportId': 1,
        'startDate': start_date.isoformat(),
        'endDate': end_date.isoformat(),
        'limit': TRANSACTION_FETCH_LIMIT,
    }
    if team_id is not None:
        parameters['teamId'] = int(team_id)
    return build_source_identity(
        provider=SourceProvider.MLB_STATS_API,
        source_domain=SourceDomain.TRANSACTIONS,
        endpoint=SOURCE_ENDPOINT,
        subject_type=SourceSubjectType.DATE_RANGE,
        subject_key=(
            f'{start_date.isoformat()}:{end_date.isoformat()}:'
            f'{int(team_id) if team_id is not None else "league"}'
        ),
        request_parameters=parameters,
        range_start=start_date,
        range_end=end_date,
    )


def _transaction_key(values):
    if values.get('transaction_id'):
        return f"statsapi:{values['transaction_id']}"
    parts = [
        values.get('player_mlb_id'),
        values.get('transaction_date'),
        values.get('effective_date'),
        values.get('resolution_date'),
        values.get('transaction_type_code'),
        values.get('from_team_id'),
        values.get('to_team_id'),
        values.get('retroactive_date'),
    ]
    payload = '|'.join('' if value is None else str(value) for value in parts)
    digest = hashlib.sha1(payload.encode('utf-8')).hexdigest()
    return f'statsapi:fallback:{digest}'


def _normalized_source_code(value):
    text = _string_or_none(value)
    if not text:
        return None
    return text.strip().upper().replace('-', '_').replace(' ', '_')


def _normalize_il_list_type(value):
    code = _normalized_source_code(value)
    if not code:
        return None
    if code.endswith('_INJURED_LIST'):
        code = code.replace('_INJURED_LIST', '_IL')
    return _IL_LIST_BY_VALUE.get(code)


def _coerce_date(value):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if 'T' in text:
        text = text.split('T', 1)[0]
    for fmt in ('%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _int_or_none(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value):
    if value in (None, ''):
        return None
    return str(value)


def _window_ref(start_date, end_date):
    return f'{start_date.isoformat()}:{end_date.isoformat()}'
