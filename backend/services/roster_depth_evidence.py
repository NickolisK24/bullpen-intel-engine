"""Internal Phase 0D roster-depth and transaction-churn evidence family."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
import re
import time

from sqlalchemy import asc, or_

from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from models.roster_status_snapshot import RosterStatusSnapshot
from services.evidence_contract import (
    EvidenceCitationInput,
    build_evidence_object,
    mark_dependent_evidence_for_recompute,
)
from services.evidence_language import EvidenceLanguageError
from services.evidence_rules import (
    ClaimTemplate,
    ClaimTemplateRegistry,
    EvidenceRule,
    EvidenceRuleError,
    EvidenceRuleRegistry,
)
from services.transaction_ingestion import (
    ALIGNMENT_ALIGNED,
    ALIGNMENT_MISALIGNED,
    ALIGNMENT_NO_SNAPSHOT,
    ALIGNMENT_UNKNOWN,
    CATEGORY_CONTRACT_SELECTION,
    CATEGORY_DFA,
    CATEGORY_IL_ACTIVATION,
    CATEGORY_IL_PLACEMENT,
    CATEGORY_OPTION,
    CATEGORY_OUTRIGHT,
    CATEGORY_RECALL,
    CATEGORY_RELEASE,
    CATEGORY_ROSTER_ACTIVATION,
    CATEGORY_ROSTER_DEACTIVATION,
    CATEGORY_TRADE,
    CATEGORY_UNKNOWN,
    WINDOW_STATUS_SUCCESS,
)
from utils.db import db


logger = logging.getLogger('baseballos.daily_sync')

RULE_VERSION = 1
EVIDENCE_SOURCE = 'phase0d:roster_depth_evidence'
SOURCE_READY = 'ready'

TEAM_ACTIVE_PITCHER_CENSUS_RULE_ID = 'team_active_pitcher_census'
TEAM_ACTIVE_RELIEVER_COUNT_RULE_ID = 'team_active_reliever_count'
TEAM_ROSTER_SNAPSHOT_STATE_RULE_ID = 'team_roster_snapshot_state'
PITCHER_IL_PLACEMENT_CONTEXT_RULE_ID = 'pitcher_il_placement_context'
PITCHER_IL_ACTIVATION_CONTEXT_RULE_ID = 'pitcher_il_activation_context'
TEAM_PUBLIC_IL_COUNT_RULE_ID = 'team_public_il_count'
TEAM_TRANSACTION_CHURN_WINDOW_RULE_ID = 'team_transaction_churn_window'
TEAM_TRANSACTION_CATEGORY_COUNTS_WINDOW_RULE_ID = 'team_transaction_category_counts_window'
TEAM_OPTION_RECALL_CHURN_RULE_ID = 'team_option_recall_churn'
TEAM_ROSTER_MOVEMENT_CHURN_RULE_ID = 'team_roster_movement_churn'
TEAM_DEPTH_DELTA_DAILY_RULE_ID = 'team_depth_delta_daily'
TEAM_ROSTER_CHANGES_EXPLAINED_RULE_ID = 'team_roster_changes_explained'
TEAM_ROSTER_CHANGES_UNEXPLAINED_RULE_ID = 'team_roster_changes_unexplained'
TEAM_TRANSACTION_ALIGNMENT_STATE_RULE_ID = 'team_transaction_alignment_state'

ROSTER_DEPTH_RULE_IDS = (
    TEAM_ACTIVE_PITCHER_CENSUS_RULE_ID,
    TEAM_ACTIVE_RELIEVER_COUNT_RULE_ID,
    TEAM_ROSTER_SNAPSHOT_STATE_RULE_ID,
    PITCHER_IL_PLACEMENT_CONTEXT_RULE_ID,
    PITCHER_IL_ACTIVATION_CONTEXT_RULE_ID,
    TEAM_PUBLIC_IL_COUNT_RULE_ID,
    TEAM_TRANSACTION_CHURN_WINDOW_RULE_ID,
    TEAM_TRANSACTION_CATEGORY_COUNTS_WINDOW_RULE_ID,
    TEAM_OPTION_RECALL_CHURN_RULE_ID,
    TEAM_ROSTER_MOVEMENT_CHURN_RULE_ID,
    TEAM_DEPTH_DELTA_DAILY_RULE_ID,
    TEAM_ROSTER_CHANGES_EXPLAINED_RULE_ID,
    TEAM_ROSTER_CHANGES_UNEXPLAINED_RULE_ID,
    TEAM_TRANSACTION_ALIGNMENT_STATE_RULE_ID,
)

WINDOW_DAYS = (7, 14)
WINDOWED_RULE_IDS = {
    TEAM_TRANSACTION_CHURN_WINDOW_RULE_ID,
    TEAM_TRANSACTION_CATEGORY_COUNTS_WINDOW_RULE_ID,
    TEAM_OPTION_RECALL_CHURN_RULE_ID,
    TEAM_ROSTER_MOVEMENT_CHURN_RULE_ID,
    TEAM_TRANSACTION_ALIGNMENT_STATE_RULE_ID,
}

SUPPORTED_TRANSACTION_CATEGORIES = (
    CATEGORY_OPTION,
    CATEGORY_RECALL,
    CATEGORY_TRADE,
    CATEGORY_DFA,
    CATEGORY_OUTRIGHT,
    CATEGORY_RELEASE,
    CATEGORY_CONTRACT_SELECTION,
    CATEGORY_ROSTER_ACTIVATION,
    CATEGORY_ROSTER_DEACTIVATION,
    CATEGORY_IL_PLACEMENT,
    CATEGORY_IL_ACTIVATION,
    CATEGORY_UNKNOWN,
)
MOVEMENT_CATEGORIES = (
    CATEGORY_DFA,
    CATEGORY_OUTRIGHT,
    CATEGORY_RELEASE,
    CATEGORY_TRADE,
    CATEGORY_CONTRACT_SELECTION,
)
OPTION_RECALL_CATEGORIES = (CATEGORY_OPTION, CATEGORY_RECALL)

REASON_SNAPSHOT_MISSING = 'snapshot_missing'
REASON_SNAPSHOT_STALE = 'snapshot_stale'
REASON_SNAPSHOT_MEMBERSHIP_UNKNOWN = 'snapshot_membership_unknown'
REASON_SNAPSHOT_COVERAGE_INCOMPLETE = 'snapshot_coverage_incomplete'
REASON_SNAPSHOT_CACHE_DIVERGENCE = 'snapshot_cache_divergence'
REASON_RELIEVER_PARTITION_UNAVAILABLE = 'reliever_partition_unavailable'
REASON_TRANSACTION_WINDOW_UNCOVERED = 'transaction_window_uncovered'
REASON_TRANSACTION_TYPE_UNKNOWN = 'transaction_type_unknown'
REASON_ALIGNMENT_MISALIGNED = 'alignment_misaligned'
REASON_ALIGNMENT_NO_SNAPSHOT = 'alignment_no_snapshot'
REASON_ALIGNMENT_UNKNOWN = 'alignment_unknown'
REASON_DELTA_PRIOR_SNAPSHOT_UNAVAILABLE = 'delta_prior_snapshot_unavailable'
REASON_CHANGE_UNEXPLAINED = 'change_unexplained'
REASON_NO_PUBLIC_IL_FACT = 'no_public_il_fact'
REASON_SOURCE_FAMILY_NOT_READY = 'source_family_not_ready'
REASON_ROSTER_DEPTH_CORRECTED = 'roster_depth_source_corrected'

PITCHER_SCOPED_SNAPSHOT_LIMITATION = (
    'Roster snapshots cover pitchers; this census counts pitchers only.'
)
RELIEVER_PARTITION_LIMITATION = (
    'Active reliever count is unknown because no official stored reliever partition exists.'
)
LOWER_BOUND_COVERAGE_LIMITATION = (
    'Transaction count is a lower bound because at least one day in the window lacks a successful sync-window row.'
)
NO_HEALTH_LIMITATION = (
    'IL evidence states public roster events only; it does not state health, cause, or timetable.'
)

_RULE_DEFINITIONS = {
    TEAM_ACTIVE_PITCHER_CENSUS_RULE_ID: (
        "The count of pitchers on the team's active roster per the current roster "
        'snapshot. The current snapshot is the latest roster_status_snapshots rows '
        'with snapshot_date on or before the evidence date. Same-day snapshots can '
        'produce complete evidence; earlier snapshots are unknown for the evidence '
        'date. This census does not partition starters from relievers and states '
        'roster membership only.'
    ),
    TEAM_ACTIVE_RELIEVER_COUNT_RULE_ID: (
        "How many active-roster pitchers are relievers. UNKNOWN by design because "
        'BaseballOS has no official stored reliever partition. Usage observations '
        'are not a roster partition. The Phase 0D-09 decision decides whether any '
        'starter/reliever partition is authorized.'
    ),
    TEAM_ROSTER_SNAPSHOT_STATE_RULE_ID: (
        "The team's roster-snapshot basis for the evidence date: latest snapshot "
        'date, snapshot age in days, row coverage, cache divergence state, and '
        'stored source-family state. This is descriptive data-state evidence only.'
    ),
    PITCHER_IL_PLACEMENT_CONTEXT_RULE_ID: (
        'A public IL placement fact for a pitcher from a typed transaction: IL '
        'list type as sourced, transaction date, and retroactive date when stored. '
        'No injury detail, severity, cause, or return timetable is stated.'
    ),
    PITCHER_IL_ACTIVATION_CONTEXT_RULE_ID: (
        'A public IL activation or removal fact for a pitcher from a typed '
        'transaction. It states the roster event only and never states recovery or '
        'current roster usability.'
    ),
    TEAM_PUBLIC_IL_COUNT_RULE_ID: (
        "The count of the team's pitchers whose current roster snapshot status is "
        'IL. The roster snapshot decides the count. Aligned IL placement '
        'transactions are cited as explanation where stored. A placement '
        'transaction without current snapshot IL status does not count as current '
        'IL.'
    ),
    TEAM_TRANSACTION_CHURN_WINDOW_RULE_ID: (
        'The count of stored typed transactions touching the team as source or '
        'destination over trailing 7-day and 14-day windows ending on the evidence '
        'date. Complete evidence requires transaction sync-window coverage for '
        'every date in the window.'
    ),
    TEAM_TRANSACTION_CATEGORY_COUNTS_WINDOW_RULE_ID: (
        "The team's windowed transaction counts broken out by stored normalized "
        'categories over trailing 7-day and 14-day windows. Unknown types are '
        'counted as unknown-type and never interpreted.'
    ),
    TEAM_OPTION_RECALL_CHURN_RULE_ID: (
        'Option and recall movement for the team over trailing 7-day and 14-day '
        'windows: option count, recall count, and count of players appearing in '
        'more than one option or recall event in the window.'
    ),
    TEAM_ROSTER_MOVEMENT_CHURN_RULE_ID: (
        'DFA, outright, release, trade, and contract-selection movement for the '
        'team over trailing 7-day and 14-day windows. Cross-team moves count for '
        "both teams from each team's perspective."
    ),
    TEAM_DEPTH_DELTA_DAILY_RULE_ID: (
        "The day-over-day change in the team's active-pitcher census between the "
        'prior product-day snapshot and the evidence-date snapshot. It states '
        'count change, additions, and removals only.'
    ),
    TEAM_ROSTER_CHANGES_EXPLAINED_RULE_ID: (
        "Of the evidence date's active-pitcher census additions and removals, "
        'those explained by an aligned, explanatory-eligible typed transaction '
        'matching player, team perspective, and date window.'
    ),
    TEAM_ROSTER_CHANGES_UNEXPLAINED_RULE_ID: (
        "Census additions and removals with no aligned explanatory transaction in "
        'stored data. The evidence states the change is unexplained and cites the '
        'snapshot rows plus the searched transaction-window basis.'
    ),
    TEAM_TRANSACTION_ALIGNMENT_STATE_RULE_ID: (
        "The alignment state of the team's windowed transactions against roster "
        'snapshots over trailing 7-day and 14-day windows, rolled up from stored '
        'per-row alignment values: aligned, misaligned, no-snapshot, unknown '
        'alignment, and unknown-type transactions.'
    ),
}

_RULE_THRESHOLDS = {
    rule_id: {'window_7': 7, 'window_14': 14}
    for rule_id in WINDOWED_RULE_IDS
}

_REQUIRED_FIELDS = {
    TEAM_ACTIVE_PITCHER_CENSUS_RULE_ID: (
        'roster_status_snapshots.snapshot_date',
        'roster_status_snapshots.roster_status',
        'roster_status_snapshots.active_roster',
    ),
    TEAM_ACTIVE_RELIEVER_COUNT_RULE_ID: (
        'roster_status_snapshots.snapshot_date',
        'roster_status_snapshots.active_roster',
    ),
    TEAM_ROSTER_SNAPSHOT_STATE_RULE_ID: (
        'roster_status_snapshots.snapshot_date',
        'roster_status_snapshots.team_id',
    ),
    PITCHER_IL_PLACEMENT_CONTEXT_RULE_ID: (
        'player_transactions.transaction_key',
        'player_transactions.transaction_date',
        'player_transactions.il_list_type',
    ),
    PITCHER_IL_ACTIVATION_CONTEXT_RULE_ID: (
        'player_transactions.transaction_key',
        'player_transactions.transaction_date',
        'player_transactions.il_list_type',
    ),
    TEAM_PUBLIC_IL_COUNT_RULE_ID: (
        'roster_status_snapshots.snapshot_date',
        'roster_status_snapshots.roster_status',
    ),
    TEAM_TRANSACTION_CHURN_WINDOW_RULE_ID: (
        'player_transactions.source_query_start_date',
        'player_transactions.source_query_end_date',
        'player_transactions.status',
    ),
    TEAM_TRANSACTION_CATEGORY_COUNTS_WINDOW_RULE_ID: (
        'player_transactions.source_query_start_date',
        'player_transactions.source_query_end_date',
        'player_transactions.status',
    ),
    TEAM_OPTION_RECALL_CHURN_RULE_ID: (
        'player_transactions.source_query_start_date',
        'player_transactions.source_query_end_date',
        'player_transactions.status',
    ),
    TEAM_ROSTER_MOVEMENT_CHURN_RULE_ID: (
        'player_transactions.source_query_start_date',
        'player_transactions.source_query_end_date',
        'player_transactions.status',
    ),
    TEAM_DEPTH_DELTA_DAILY_RULE_ID: (
        'roster_status_snapshots.snapshot_date',
        'roster_status_snapshots.active_roster',
    ),
    TEAM_ROSTER_CHANGES_EXPLAINED_RULE_ID: (
        'roster_status_snapshots.snapshot_date',
        'player_transactions.transaction_key',
        'player_transactions.roster_snapshot_alignment',
        'player_transactions.explanatory_linkage_eligible',
    ),
    TEAM_ROSTER_CHANGES_UNEXPLAINED_RULE_ID: (
        'roster_status_snapshots.snapshot_date',
        'roster_status_snapshots.active_roster',
    ),
    TEAM_TRANSACTION_ALIGNMENT_STATE_RULE_ID: (
        'player_transactions.source_query_start_date',
        'player_transactions.source_query_end_date',
        'player_transactions.status',
    ),
}

_FORBIDDEN_ROSTER_DEPTH_TERMS = (
    'availability',
    'available',
    'ready',
    'readiness',
    'usable',
    'healthy',
    'injury-free',
    'full strength',
    'nobody is hurt',
    'cleared',
    'recovered',
    'ahead of schedule',
    'fatigue',
    'pressure',
    'trust',
    'confidence',
    'thin',
    'depleted',
    'overworked',
    'quality',
    'manager intent',
    'front-office intent',
    'front office intent',
    'prediction',
    'predict',
    'betting',
    'odds',
    'score',
    'grade',
    'rank',
)


@dataclass(frozen=True)
class BuiltRosterDepthEvidence:
    evidence: EvidenceObject
    rule_id: str
    subject_key: str


@dataclass(frozen=True)
class SnapshotSet:
    team_id: int
    snapshot_date: date | None
    rows: tuple[RosterStatusSnapshot, ...]
    missing: bool = False

    @property
    def age_days(self) -> int | None:
        if self.snapshot_date is None:
            return None
        return None


@dataclass(frozen=True)
class CensusAnalysis:
    snapshot: SnapshotSet
    known_active_rows: tuple[RosterStatusSnapshot, ...]
    unknown_membership_rows: tuple[RosterStatusSnapshot, ...]
    two_way_rows: tuple[RosterStatusSnapshot, ...]
    non_active_rows: tuple[RosterStatusSnapshot, ...]


@dataclass(frozen=True)
class CoverageAnalysis:
    window_days: int
    start_date: date
    end_date: date
    rows: tuple[PlayerTransactionSyncWindow, ...]
    uncovered_dates: tuple[date, ...]

    @property
    def complete(self) -> bool:
        return not self.uncovered_dates

    @property
    def uncovered_ranges(self) -> tuple[tuple[date, date], ...]:
        return _date_ranges(self.uncovered_dates)


_LOCAL_RULE_REGISTRY: EvidenceRuleRegistry | None = None
_LOCAL_TEMPLATE_REGISTRY: ClaimTemplateRegistry | None = None


def roster_depth_rule_definitions() -> dict[str, str]:
    return dict(_RULE_DEFINITIONS)


def roster_depth_rule_ids() -> tuple[str, ...]:
    return ROSTER_DEPTH_RULE_IDS


def register_roster_depth_rules(
    *,
    registry: EvidenceRuleRegistry | None = None,
    template_registry: ClaimTemplateRegistry | None = None,
) -> tuple[EvidenceRuleRegistry, ClaimTemplateRegistry]:
    rule_registry = registry or EvidenceRuleRegistry()
    claim_registry = template_registry or ClaimTemplateRegistry()
    for rule_id in ROSTER_DEPTH_RULE_IDS:
        _register_roster_depth_rule(rule_registry, _roster_depth_rule(rule_id))
        if rule_id in WINDOWED_RULE_IDS:
            for window_days in WINDOW_DAYS:
                _register_roster_depth_template(
                    claim_registry,
                    ClaimTemplate(
                        template_id=_template_id(rule_id, window_days=window_days),
                        template_version=RULE_VERSION,
                        template_text='{claim}',
                    ),
                )
        else:
            _register_roster_depth_template(
                claim_registry,
                ClaimTemplate(
                    template_id=_template_id(rule_id),
                    template_version=RULE_VERSION,
                    template_text='{claim}',
                ),
            )
    return rule_registry, claim_registry


def build_roster_depth_evidence(
    product_date,
    *,
    sync_run_id=None,
    source='manual',
    commit=False,
    restrict_evidence_keys: set[str] | None = None,
) -> dict:
    started = time.perf_counter()
    ref = _as_date(product_date)
    logger.info(
        'Roster depth build starting: product_date=%s restrict_keys=%s.',
        ref.isoformat(),
        len(restrict_evidence_keys or ()),
    )
    context_started = time.perf_counter()
    registry, templates = _local_registries()
    snapshot_sets = _latest_snapshot_sets_by_team(ref)
    prior_snapshot_sets = _snapshot_sets_for_date(ref - timedelta(days=1))
    all_snapshot_by_pitcher_date = _snapshot_rows_by_pitcher_date(
        (ref - timedelta(days=1), ref)
    )
    transactions = _transactions_for_window(ref - timedelta(days=13), ref)
    coverage_rows = _transaction_sync_windows(ref - timedelta(days=13), ref)
    team_ids = _team_ids(snapshot_sets, prior_snapshot_sets, transactions)
    names = _pitcher_names(snapshot_sets, prior_snapshot_sets, transactions)
    source_state = _roster_source_state(ref)
    logger.info(
        'Roster depth context loaded: product_date=%s teams=%s '
        'current_snapshot_teams=%s prior_snapshot_teams=%s transactions=%s '
        'coverage_windows=%s elapsed_ms=%s.',
        ref.isoformat(),
        len(team_ids),
        len(snapshot_sets),
        len(prior_snapshot_sets),
        len(transactions),
        len(coverage_rows),
        round((time.perf_counter() - context_started) * 1000, 1),
    )
    assemble_started = time.perf_counter()
    evidence_to_upsert = []
    team_objects = 0
    player_il_objects = 0

    for team_id in team_ids:
        current = snapshot_sets.get(team_id) or SnapshotSet(team_id, None, (), missing=True)
        prior = prior_snapshot_sets.get(team_id)
        team_transactions = _transactions_for_team(transactions, team_id)
        built = _build_for_team(
            team_id=team_id,
            product_date=ref,
            current=current,
            prior=prior,
            transactions=team_transactions,
            coverage_rows=coverage_rows,
            all_snapshot_by_pitcher_date=all_snapshot_by_pitcher_date,
            pitcher_names=names,
            source_state=source_state,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
        for item in built:
            if restrict_evidence_keys is not None and item.evidence.evidence_key not in restrict_evidence_keys:
                continue
            evidence_to_upsert.append(item.evidence)
            team_objects += 1

    for transaction in transactions:
        for item in _build_player_il_objects(
            product_date=ref,
            transaction=transaction,
            current_snapshots=snapshot_sets,
            all_snapshot_by_pitcher_date=all_snapshot_by_pitcher_date,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        ):
            if restrict_evidence_keys is not None and item.evidence.evidence_key not in restrict_evidence_keys:
                continue
            evidence_to_upsert.append(item.evidence)
            player_il_objects += 1

    logger.info(
        'Roster depth evidence assembled: product_date=%s team_objects=%s '
        'player_il_objects=%s objects_built=%s elapsed_ms=%s.',
        ref.isoformat(),
        team_objects,
        player_il_objects,
        len(evidence_to_upsert),
        round((time.perf_counter() - assemble_started) * 1000, 1),
    )
    upsert_started = time.perf_counter()
    emitted = _upsert_evidence_batch(evidence_to_upsert)
    logger.info(
        'Roster depth persistence completed: product_date=%s objects_built=%s '
        'objects_created=%s objects_refreshed=%s elapsed_ms=%s.',
        ref.isoformat(),
        len(emitted),
        sum(1 for item in emitted if item == 'created'),
        sum(1 for item in emitted if item == 'refreshed'),
        round((time.perf_counter() - upsert_started) * 1000, 1),
    )

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        'Roster depth build completed: product_date=%s teams_considered=%s '
        'transactions_considered=%s objects_built=%s objects_created=%s '
        'objects_refreshed=%s elapsed_ms=%s.',
        ref.isoformat(),
        len(team_ids),
        len(transactions),
        len(emitted),
        sum(1 for item in emitted if item == 'created'),
        sum(1 for item in emitted if item == 'refreshed'),
        elapsed_ms,
    )
    return {
        'status': 'built',
        'product_date': ref.isoformat(),
        'rules': list(ROSTER_DEPTH_RULE_IDS),
        'teams_considered': len(team_ids),
        'transactions_considered': len(transactions),
        'objects_built': len(emitted),
        'objects_created': sum(1 for item in emitted if item == 'created'),
        'objects_refreshed': sum(1 for item in emitted if item == 'refreshed'),
        'transaction_sync_window_coverage': 'player_transaction_sync_windows',
        'elapsed_ms': elapsed_ms,
    }


def mark_roster_status_snapshot_correction_for_roster_depth(
    snapshot_row,
    *,
    sync_run_id=None,
    reason_code=REASON_ROSTER_DEPTH_CORRECTED,
    batch_size=100,
) -> dict:
    if snapshot_row is None or getattr(snapshot_row, 'id', None) is None:
        return {'marked_count': 0, 'evidence_ids': []}
    return mark_dependent_evidence_for_recompute(
        source_table='roster_status_snapshots',
        source_pk=snapshot_row.id,
        reason_code=reason_code,
        batch_size=batch_size,
        sync_run_id=sync_run_id,
    )


def mark_player_transaction_correction_for_roster_depth(
    transaction_row,
    *,
    sync_run_id=None,
    reason_code=REASON_ROSTER_DEPTH_CORRECTED,
    batch_size=100,
) -> dict:
    if transaction_row is None or getattr(transaction_row, 'id', None) is None:
        return {'marked_count': 0, 'evidence_ids': []}
    return mark_dependent_evidence_for_recompute(
        source_table='player_transactions',
        source_pk=transaction_row.id,
        reason_code=reason_code,
        batch_size=batch_size,
        sync_run_id=sync_run_id,
    )


def rebuild_marked_roster_depth_evidence(
    *,
    sync_run_id=None,
    source='manual',
    batch_size=100,
) -> dict:
    rows = (
        EvidenceObject.query
        .filter(EvidenceObject.rule_id.in_(ROSTER_DEPTH_RULE_IDS))
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_NEEDED)
        .order_by(asc(EvidenceObject.product_date), asc(EvidenceObject.id))
        .limit(batch_size)
        .all()
    )
    if not rows:
        return {'status': 'noop', 'objects_rebuilt': 0, 'dates_rebuilt': []}

    keys_by_date = defaultdict(set)
    for row in rows:
        keys_by_date[row.product_date].add(row.evidence_key)

    rebuilt = 0
    for evidence_date, keys in keys_by_date.items():
        result = build_roster_depth_evidence(
            evidence_date,
            sync_run_id=sync_run_id,
            source=source,
            restrict_evidence_keys=keys,
        )
        rebuilt += result['objects_created'] + result['objects_refreshed']

    db.session.flush()
    return {
        'status': 'rebuilt',
        'objects_rebuilt': rebuilt,
        'dates_rebuilt': [day.isoformat() for day in sorted(keys_by_date)],
    }


def _local_registries():
    global _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY
    if _LOCAL_RULE_REGISTRY is None or _LOCAL_TEMPLATE_REGISTRY is None:
        _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY = register_roster_depth_rules()
    return _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY


def _roster_depth_rule(rule_id):
    allowed = (
        (EvidenceObject.COMPLETENESS_UNKNOWN,)
        if rule_id == TEAM_ACTIVE_RELIEVER_COUNT_RULE_ID
        else (
            EvidenceObject.COMPLETENESS_COMPLETE,
            EvidenceObject.COMPLETENESS_PARTIAL,
            EvidenceObject.COMPLETENESS_UNKNOWN,
            EvidenceObject.COMPLETENESS_CONFLICT,
            EvidenceObject.COMPLETENESS_WITHHELD,
        )
    )
    required_families = ('roster_status_snapshots',)
    if rule_id in (
        PITCHER_IL_PLACEMENT_CONTEXT_RULE_ID,
        PITCHER_IL_ACTIVATION_CONTEXT_RULE_ID,
        TEAM_TRANSACTION_CHURN_WINDOW_RULE_ID,
        TEAM_TRANSACTION_CATEGORY_COUNTS_WINDOW_RULE_ID,
        TEAM_OPTION_RECALL_CHURN_RULE_ID,
        TEAM_ROSTER_MOVEMENT_CHURN_RULE_ID,
        TEAM_TRANSACTION_ALIGNMENT_STATE_RULE_ID,
    ):
        required_families = ('player_transactions',)
    elif rule_id in (
        TEAM_PUBLIC_IL_COUNT_RULE_ID,
        TEAM_DEPTH_DELTA_DAILY_RULE_ID,
        TEAM_ROSTER_CHANGES_EXPLAINED_RULE_ID,
        TEAM_ROSTER_CHANGES_UNEXPLAINED_RULE_ID,
    ):
        required_families = ('roster_status_snapshots', 'player_transactions')
    return EvidenceRule(
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        evidence_type=rule_id,
        plain_language_definition=_RULE_DEFINITIONS[rule_id],
        required_input_families=required_families,
        required_cited_fields=_REQUIRED_FIELDS[rule_id],
        allowed_completeness=allowed,
        posture_default=EvidenceObject.POSTURE_INTERNAL_ONLY,
        thresholds=_RULE_THRESHOLDS.get(rule_id, {}),
    )


def _register_roster_depth_rule(registry, rule):
    if rule.posture_default != EvidenceObject.POSTURE_INTERNAL_ONLY:
        raise EvidenceRuleError('roster depth evidence must remain internal_only')
    if rule.rule_id == TEAM_ACTIVE_RELIEVER_COUNT_RULE_ID and rule.allowed_completeness != (
        EvidenceObject.COMPLETENESS_UNKNOWN,
    ):
        raise EvidenceRuleError('team_active_reliever_count must stay unknown-only')
    _assert_text_has_no_roster_depth_forbidden_terms(rule.plain_language_definition)
    return registry.register(rule)


def _register_roster_depth_template(registry, template):
    _assert_text_has_no_roster_depth_forbidden_terms(template.template_text)
    return registry.register(template)


def _assert_text_has_no_roster_depth_forbidden_terms(text):
    lowered = f' {text or ""} '.lower()
    for term in _FORBIDDEN_ROSTER_DEPTH_TERMS:
        pattern = r'\b' + re.escape(term).replace(r'\ ', r'\s+') + r'\b'
        if re.search(pattern, lowered):
            raise EvidenceLanguageError(
                f'roster depth claim language uses forbidden term: {term}'
            )
    return True


def _build_for_team(
    *,
    team_id,
    product_date,
    current,
    prior,
    transactions,
    coverage_rows,
    all_snapshot_by_pitcher_date,
    pitcher_names,
    source_state,
    registry,
    templates,
    sync_run_id,
    source,
):
    built = []
    census = _analyze_census(current)
    built.extend([
        _active_pitcher_census_object(
            team_id, product_date, census, source_state, registry, templates, sync_run_id, source
        ),
        _active_reliever_count_object(
            team_id, product_date, current, registry, templates, sync_run_id, source
        ),
        _snapshot_state_object(
            team_id, product_date, current, source_state, registry, templates, sync_run_id, source
        ),
        _team_public_il_count_object(
            team_id, product_date, current, transactions, registry, templates, sync_run_id, source
        ),
        _depth_delta_object(
            team_id, product_date, current, prior, all_snapshot_by_pitcher_date,
            pitcher_names, transactions, registry, templates, sync_run_id, source
        ),
    ])

    explained, unexplained = _change_explanations(
        team_id=team_id,
        product_date=product_date,
        current=current,
        prior=prior,
        transactions=transactions,
        all_snapshot_by_pitcher_date=all_snapshot_by_pitcher_date,
        pitcher_names=pitcher_names,
    )
    if explained:
        built.append(_explained_changes_object(
            team_id, product_date, explained, registry, templates, sync_run_id, source
        ))
    if unexplained:
        built.append(_unexplained_changes_object(
            team_id, product_date, unexplained, coverage_rows, registry, templates, sync_run_id, source
        ))

    for window_days in WINDOW_DAYS:
        coverage = _coverage_for_window(product_date, window_days, coverage_rows)
        if not coverage.rows:
            continue
        window_transactions = _transactions_in_window(transactions, product_date, window_days)
        built.extend([
            _transaction_churn_object(
                team_id, product_date, window_days, window_transactions, coverage,
                registry, templates, sync_run_id, source
            ),
            _transaction_category_object(
                team_id, product_date, window_days, window_transactions, coverage,
                registry, templates, sync_run_id, source
            ),
            _option_recall_object(
                team_id, product_date, window_days, window_transactions, coverage,
                registry, templates, sync_run_id, source
            ),
            _movement_churn_object(
                team_id, product_date, window_days, window_transactions, coverage,
                registry, templates, sync_run_id, source
            ),
            _alignment_state_object(
                team_id, product_date, window_days, window_transactions, coverage,
                registry, templates, sync_run_id, source
            ),
        ])
    return [item for item in built if item is not None]


def _active_pitcher_census_object(
    team_id, product_date, census, source_state, registry, templates, sync_run_id, source
):
    citations = _snapshot_citations_for_set(census.snapshot)
    if not citations:
        citations = (_missing_snapshot_citation(team_id, product_date),)
    reasons = []
    trace = _census_trace(census, product_date, source_state)
    input_values = {
        'roster_status_snapshots.snapshot_date': _iso(census.snapshot.snapshot_date),
        'roster_status_snapshots.roster_status': _first_snapshot_value(
            census.snapshot.rows, 'roster_status'
        ),
        'roster_status_snapshots.active_roster': _first_snapshot_value(
            census.snapshot.rows, 'active_roster'
        ),
    }
    limitations = [PITCHER_SCOPED_SNAPSHOT_LIMITATION]
    state = EvidenceObject.COMPLETENESS_COMPLETE
    if census.snapshot.missing:
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        reasons.append(REASON_SNAPSHOT_MISSING)
        claim = (
            f'Active-pitcher census cannot be stated for team {team_id} on '
            f'{product_date.isoformat()}; no roster snapshot is stored for this team.'
        )
    elif census.snapshot.snapshot_date != product_date:
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        reasons.append(REASON_SNAPSHOT_STALE)
        age = (product_date - census.snapshot.snapshot_date).days
        claim = (
            f'Active-pitcher census cannot be stated for team {team_id} on '
            f'{product_date.isoformat()}; latest roster snapshot is '
            f'{census.snapshot.snapshot_date.isoformat()} ({age} days old).'
        )
    elif source_state.get('status') != SOURCE_READY:
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        reasons.extend(source_state.get('reason_codes') or [REASON_SOURCE_FAMILY_NOT_READY])
        claim = (
            f'Active-pitcher census cannot be stated for team {team_id} on '
            f'{product_date.isoformat()}; roster snapshot source state is degraded.'
        )
    elif census.unknown_membership_rows:
        state = EvidenceObject.COMPLETENESS_PARTIAL
        reasons.append(REASON_SNAPSHOT_MEMBERSHIP_UNKNOWN)
        claim = (
            f'At least {len(census.known_active_rows)} active pitchers: '
            f'{len(census.known_active_rows)} known active, '
            f'{len(census.unknown_membership_rows)} with unknown membership; '
            f'snapshot {product_date.isoformat()}.'
        )
    else:
        two_way = len(census.two_way_rows)
        suffix = (
            f' ({two_way} two-way pitcher included).'
            if two_way == 1
            else f' ({two_way} two-way pitchers included).'
            if two_way
            else '.'
        )
        claim = (
            f'{len(census.known_active_rows)} pitchers on the active roster per '
            f'the {product_date.isoformat()} snapshot{suffix}'
        )
    return _build_object(
        rule_id=TEAM_ACTIVE_PITCHER_CENSUS_RULE_ID,
        subject_type='team',
        subject_id=team_id,
        subject_key=f'team:{team_id}:{product_date.isoformat()}:active-pitcher-census',
        product_date=product_date,
        claim=claim,
        cited_inputs=citations,
        input_values=input_values,
        trace=trace,
        limitations=limitations,
        state=state,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _active_reliever_count_object(
    team_id, product_date, snapshot_set, registry, templates, sync_run_id, source
):
    citations = _snapshot_citations_for_set(snapshot_set) or (
        _missing_snapshot_citation(team_id, product_date),
    )
    claim = (
        f'Active reliever count is unknown for team {team_id}; no official stored '
        'reliever partition exists.'
    )
    return _build_object(
        rule_id=TEAM_ACTIVE_RELIEVER_COUNT_RULE_ID,
        subject_type='team',
        subject_id=team_id,
        subject_key=f'team:{team_id}:{product_date.isoformat()}:active-reliever-count',
        product_date=product_date,
        claim=claim,
        cited_inputs=citations,
        input_values={
            'roster_status_snapshots.snapshot_date': _iso(snapshot_set.snapshot_date),
            'roster_status_snapshots.active_roster': None,
        },
        trace={
            'steps': [
                'Read current team roster snapshot rows.',
                'Did not partition active pitchers into starters or relievers.',
                'Emitted the contract-locked unknown rule so the gap is citable.',
            ],
            'snapshot_date': _iso(snapshot_set.snapshot_date),
            'team_id': team_id,
            'decision': 'reliever_partition_unavailable',
        },
        limitations=(RELIEVER_PARTITION_LIMITATION,),
        state=EvidenceObject.COMPLETENESS_UNKNOWN,
        reason_codes=(REASON_RELIEVER_PARTITION_UNAVAILABLE,),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _snapshot_state_object(
    team_id, product_date, snapshot_set, source_state, registry, templates, sync_run_id, source
):
    citations = _snapshot_citations_for_set(snapshot_set) or (
        _missing_snapshot_citation(team_id, product_date),
    )
    if snapshot_set.snapshot_date is None:
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        reasons = [REASON_SNAPSHOT_MISSING]
        claim = (
            f'Roster snapshot state for team {team_id} on {product_date.isoformat()}: '
            'no roster snapshot row is stored.'
        )
        age = None
    else:
        age = (product_date - snapshot_set.snapshot_date).days
        state = EvidenceObject.COMPLETENESS_COMPLETE
        reasons = []
        if snapshot_set.snapshot_date != product_date:
            reasons.append(REASON_SNAPSHOT_STALE)
        if source_state.get('status') != SOURCE_READY:
            reasons.extend(source_state.get('reason_codes') or [REASON_SOURCE_FAMILY_NOT_READY])
        claim = (
            f'Roster snapshot state for team {team_id} on {product_date.isoformat()}: '
            f'latest snapshot {snapshot_set.snapshot_date.isoformat()}, age {age} days, '
            f'{len(snapshot_set.rows)} pitcher rows, cache divergence count '
            f'{source_state.get("cache_divergence_count", 0)}.'
        )
    return _build_object(
        rule_id=TEAM_ROSTER_SNAPSHOT_STATE_RULE_ID,
        subject_type='team',
        subject_id=team_id,
        subject_key=f'team:{team_id}:{product_date.isoformat()}:roster-snapshot-state',
        product_date=product_date,
        claim=claim,
        cited_inputs=citations,
        input_values={
            'roster_status_snapshots.snapshot_date': _iso(snapshot_set.snapshot_date),
            'roster_status_snapshots.team_id': team_id if snapshot_set.rows else None,
        },
        trace={
            'steps': [
                'Read latest roster_status_snapshots rows on or before the evidence date.',
                'Recorded snapshot date, age, row count, and source state.',
            ],
            'team_id': team_id,
            'product_date': product_date.isoformat(),
            'latest_snapshot_date': _iso(snapshot_set.snapshot_date),
            'snapshot_age_days': age,
            'row_count': len(snapshot_set.rows),
            'source_state': dict(source_state),
            'decision': 'snapshot_state_recorded',
        },
        state=state,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _team_public_il_count_object(
    team_id, product_date, snapshot_set, transactions, registry, templates, sync_run_id, source
):
    if snapshot_set.missing:
        return None
    census = _analyze_census(snapshot_set)
    il_rows = tuple(row for row in snapshot_set.rows if _is_il_status(row.roster_status))
    citations = [_snapshot_citation(row) for row in snapshot_set.rows]
    explanation_transactions = []
    missing_links = []
    for row in il_rows:
        match = _latest_aligned_il_placement(row.pitcher_id, transactions)
        if match is not None:
            explanation_transactions.append(match)
            citations.append(_transaction_citation(match, team_id=team_id))
        else:
            missing_links.append(row.pitcher_id)
    state = EvidenceObject.COMPLETENESS_COMPLETE
    reasons = []
    if snapshot_set.snapshot_date != product_date:
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        reasons.append(REASON_SNAPSHOT_STALE)
        claim = (
            f'Current IL count cannot be stated for team {team_id} on '
            f'{product_date.isoformat()}; latest roster snapshot is '
            f'{snapshot_set.snapshot_date.isoformat()}.'
        )
    elif census.unknown_membership_rows:
        state = EvidenceObject.COMPLETENESS_PARTIAL
        reasons.append(REASON_SNAPSHOT_MEMBERSHIP_UNKNOWN)
        claim = (
            f'At least {len(il_rows)} pitchers on the IL per current snapshot; '
            f'{len(census.unknown_membership_rows)} rows have unknown membership.'
        )
    else:
        if missing_links:
            reasons.append(REASON_NO_PUBLIC_IL_FACT)
        claim = (
            f'{len(il_rows)} pitchers on the IL per current snapshot; aligned '
            'placement transactions cited where stored.'
        )
    return _build_object(
        rule_id=TEAM_PUBLIC_IL_COUNT_RULE_ID,
        subject_type='team',
        subject_id=team_id,
        subject_key=f'team:{team_id}:{product_date.isoformat()}:public-il-count',
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(citations),
        input_values={
            'roster_status_snapshots.snapshot_date': _iso(snapshot_set.snapshot_date),
            'roster_status_snapshots.roster_status': _first_snapshot_value(
                snapshot_set.rows, 'roster_status'
            ),
        },
        trace={
            'steps': [
                'Read current team roster snapshot rows.',
                'Counted current IL status from snapshot rows only.',
                'Cited aligned IL placement transactions where stored.',
                'Did not let placement transactions override snapshot current state.',
            ],
            'team_id': team_id,
            'snapshot_date': _iso(snapshot_set.snapshot_date),
            'il_pitcher_ids': [row.pitcher_id for row in il_rows],
            'aligned_il_placement_transaction_keys': [
                tx.transaction_key for tx in explanation_transactions
            ],
            'snapshot_il_without_placement_pitcher_ids': missing_links,
            'placement_without_snapshot_il_transaction_keys': [
                tx.transaction_key
                for tx in transactions
                if tx.is_il_placement and tx.pitcher_id not in {row.pitcher_id for row in il_rows}
            ],
            'decision': 'snapshot_decides_current_il_count',
        },
        limitations=(NO_HEALTH_LIMITATION,),
        state=state,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _depth_delta_object(
    team_id,
    product_date,
    current,
    prior,
    all_snapshot_by_pitcher_date,
    pitcher_names,
    transactions,
    registry,
    templates,
    sync_run_id,
    source,
):
    citations = []
    if current and current.rows:
        citations.extend(_snapshot_citation(row) for row in current.rows)
    if prior and prior.rows:
        citations.extend(_snapshot_citation(row) for row in prior.rows)
    if not citations:
        citations.append(_missing_snapshot_citation(team_id, product_date))

    state = EvidenceObject.COMPLETENESS_COMPLETE
    reasons = []
    current_census = _analyze_census(current)
    prior_census = _analyze_census(prior) if prior else None
    if current.snapshot_date != product_date:
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        reasons.append(REASON_SNAPSHOT_STALE if current.snapshot_date else REASON_SNAPSHOT_MISSING)
        claim = (
            f'Daily active-pitcher census delta cannot be stated for team {team_id} '
            f'on {product_date.isoformat()}; evidence-date snapshot is not stored.'
        )
    elif prior is None or prior.snapshot_date != product_date - timedelta(days=1):
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        reasons.append(REASON_DELTA_PRIOR_SNAPSHOT_UNAVAILABLE)
        claim = (
            f'Daily active-pitcher census delta cannot be stated for team {team_id} '
            f'on {product_date.isoformat()}; prior product-day snapshot is not stored.'
        )
    elif current_census.unknown_membership_rows or prior_census.unknown_membership_rows:
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        reasons.append(REASON_SNAPSHOT_MEMBERSHIP_UNKNOWN)
        claim = (
            f'Daily active-pitcher census delta cannot be stated for team {team_id} '
            f'on {product_date.isoformat()}; at least one snapshot row has unknown membership.'
        )
    else:
        prior_ids = {row.pitcher_id for row in prior_census.known_active_rows}
        current_ids = {row.pitcher_id for row in current_census.known_active_rows}
        additions = sorted(current_ids - prior_ids)
        removals = sorted(prior_ids - current_ids)
        change = len(current_ids) - len(prior_ids)
        claim = (
            f'Active-pitcher census changed by {change:+d} for team {team_id}: '
            f'{_names(additions, pitcher_names) or "no additions"}, '
            f'{_names(removals, pitcher_names) or "no removals"}.'
        )
    trace = _delta_trace(
        team_id=team_id,
        product_date=product_date,
        current=current,
        prior=prior,
        all_snapshot_by_pitcher_date=all_snapshot_by_pitcher_date,
        pitcher_names=pitcher_names,
        transactions=transactions,
        decision='daily_delta_built' if state == EvidenceObject.COMPLETENESS_COMPLETE else 'daily_delta_unknown',
    )
    return _build_object(
        rule_id=TEAM_DEPTH_DELTA_DAILY_RULE_ID,
        subject_type='team',
        subject_id=team_id,
        subject_key=f'team:{team_id}:{product_date.isoformat()}:depth-delta-daily',
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(citations),
        input_values={
            'roster_status_snapshots.snapshot_date': _iso(current.snapshot_date),
            'roster_status_snapshots.active_roster': _first_snapshot_value(
                current.rows, 'active_roster'
            ),
        },
        trace=trace,
        limitations=(PITCHER_SCOPED_SNAPSHOT_LIMITATION,),
        state=state,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _explained_changes_object(team_id, product_date, changes, registry, templates, sync_run_id, source):
    citations = []
    for change in changes:
        citations.extend(change['snapshot_citations'])
        citations.append(_transaction_citation(change['transaction'], team_id=team_id))
    claim = (
        f'{len(changes)} active-pitcher census changes explained for team {team_id}: '
        f'{_change_summary(changes)}.'
    )
    return _build_object(
        rule_id=TEAM_ROSTER_CHANGES_EXPLAINED_RULE_ID,
        subject_type='team',
        subject_id=team_id,
        subject_key=f'team:{team_id}:{product_date.isoformat()}:roster-changes-explained',
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(citations),
        input_values={
            'roster_status_snapshots.snapshot_date': product_date.isoformat(),
            'player_transactions.transaction_key': changes[0]['transaction'].transaction_key,
            'player_transactions.roster_snapshot_alignment': (
                changes[0]['transaction'].roster_snapshot_alignment
            ),
            'player_transactions.explanatory_linkage_eligible': (
                changes[0]['transaction'].explanatory_linkage_eligible
            ),
        },
        trace={
            'steps': [
                'Computed active-pitcher census additions and removals from stored snapshots.',
                'Consumed stored roster_snapshot_alignment and explanatory_linkage_eligible.',
                'Matched player, team perspective, and date window without recomputing alignment.',
            ],
            'team_id': team_id,
            'product_date': product_date.isoformat(),
            'changes': [_change_trace(change) for change in changes],
            'local_alignment_recomputed': False,
            'decision': 'changes_explained_by_stored_alignment',
        },
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _unexplained_changes_object(
    team_id, product_date, changes, coverage_rows, registry, templates, sync_run_id, source
):
    citations = []
    for change in changes:
        citations.extend(change['snapshot_citations'])
    coverage = _coverage_for_window(product_date, 7, coverage_rows)
    citations.extend(_coverage_citations(coverage))
    claim = (
        f'{len(changes)} active-pitcher census changes unexplained for team {team_id}: '
        f'{_change_summary(changes)}.'
    )
    return _build_object(
        rule_id=TEAM_ROSTER_CHANGES_UNEXPLAINED_RULE_ID,
        subject_type='team',
        subject_id=team_id,
        subject_key=f'team:{team_id}:{product_date.isoformat()}:roster-changes-unexplained',
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(citations),
        input_values={
            'roster_status_snapshots.snapshot_date': product_date.isoformat(),
            'roster_status_snapshots.active_roster': True,
        },
        trace={
            'steps': [
                'Computed active-pitcher census additions and removals from stored snapshots.',
                'Searched aligned explanatory-eligible transactions in the product-day window.',
                'Left changes unexplained when stored alignment did not support an explanation.',
            ],
            'team_id': team_id,
            'product_date': product_date.isoformat(),
            'searched_transaction_window': {
                'start': (product_date - timedelta(days=6)).isoformat(),
                'end': product_date.isoformat(),
                'coverage_rows': [_coverage_row_ref(row) for row in coverage.rows],
                'uncovered_ranges': _range_payloads(coverage.uncovered_ranges),
            },
            'changes': [_change_trace(change) for change in changes],
            'decision': 'changes_unexplained',
        },
        state=EvidenceObject.COMPLETENESS_COMPLETE,
        reason_codes=(REASON_CHANGE_UNEXPLAINED,),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _transaction_churn_object(
    team_id, product_date, window_days, transactions, coverage, registry, templates, sync_run_id, source
):
    citations = _coverage_citations(coverage) + tuple(
        _transaction_citation(tx, team_id=team_id) for tx in transactions
    )
    state, reasons, limitations, prefix = _coverage_state(coverage)
    count = len(transactions)
    claim = (
        f'{prefix}{count} transactions touching team {team_id} in the trailing '
        f'{window_days}-day window ending {product_date.isoformat()}.'
    )
    return _window_object(
        TEAM_TRANSACTION_CHURN_WINDOW_RULE_ID,
        team_id,
        product_date,
        window_days,
        claim,
        citations,
        _coverage_input_values(coverage),
        _transaction_window_trace(
            team_id, product_date, window_days, transactions, coverage,
            decision='transaction_churn_counted',
        ),
        state,
        reasons,
        limitations,
        registry,
        templates,
        sync_run_id,
        source,
    )


def _transaction_category_object(
    team_id, product_date, window_days, transactions, coverage, registry, templates, sync_run_id, source
):
    counts = Counter(tx.normalized_category or CATEGORY_UNKNOWN for tx in transactions)
    ordered = {category: counts.get(category, 0) for category in SUPPORTED_TRANSACTION_CATEGORIES}
    extra = {
        category: count
        for category, count in sorted(counts.items())
        if category not in ordered
    }
    ordered.update(extra)
    category_text = _category_summary(ordered)
    state, reasons, limitations, prefix = _coverage_state(coverage)
    if counts.get(CATEGORY_UNKNOWN, 0):
        reasons = _dedupe(list(reasons) + [REASON_TRANSACTION_TYPE_UNKNOWN])
    claim = (
        f'{prefix}{len(transactions)} transactions touching team {team_id} in the '
        f'trailing {window_days}-day window ending {product_date.isoformat()} '
        f'({category_text}).'
    )
    return _window_object(
        TEAM_TRANSACTION_CATEGORY_COUNTS_WINDOW_RULE_ID,
        team_id,
        product_date,
        window_days,
        claim,
        _coverage_citations(coverage) + tuple(
            _transaction_citation(tx, team_id=team_id) for tx in transactions
        ),
        _coverage_input_values(coverage),
        _transaction_window_trace(
            team_id, product_date, window_days, transactions, coverage,
            decision='transaction_categories_counted',
            extra={'category_counts': ordered},
        ),
        state,
        reasons,
        limitations,
        registry,
        templates,
        sync_run_id,
        source,
    )


def _option_recall_object(
    team_id, product_date, window_days, transactions, coverage, registry, templates, sync_run_id, source
):
    filtered = [tx for tx in transactions if tx.normalized_category in OPTION_RECALL_CATEGORIES]
    option_count = sum(1 for tx in filtered if tx.normalized_category == CATEGORY_OPTION)
    recall_count = sum(1 for tx in filtered if tx.normalized_category == CATEGORY_RECALL)
    player_counts = Counter(tx.pitcher_id or tx.player_mlb_id for tx in filtered)
    repeat_players = sorted(player for player, count in player_counts.items() if count > 1)
    state, reasons, limitations, prefix = _coverage_state(coverage)
    claim = (
        f'{prefix}{option_count} options and {recall_count} recalls touching team '
        f'{team_id} in the trailing {window_days}-day window ending '
        f'{product_date.isoformat()}; {len(repeat_players)} players have more than '
        'one option or recall event.'
    )
    return _window_object(
        TEAM_OPTION_RECALL_CHURN_RULE_ID,
        team_id,
        product_date,
        window_days,
        claim,
        _coverage_citations(coverage) + tuple(
            _transaction_citation(tx, team_id=team_id) for tx in filtered
        ),
        _coverage_input_values(coverage),
        _transaction_window_trace(
            team_id, product_date, window_days, filtered, coverage,
            decision='option_recall_counted',
            extra={
                'option_count': option_count,
                'recall_count': recall_count,
                'repeat_player_ids': repeat_players,
            },
        ),
        state,
        reasons,
        limitations,
        registry,
        templates,
        sync_run_id,
        source,
    )


def _movement_churn_object(
    team_id, product_date, window_days, transactions, coverage, registry, templates, sync_run_id, source
):
    filtered = [tx for tx in transactions if tx.normalized_category in MOVEMENT_CATEGORIES]
    counts = Counter(tx.normalized_category for tx in filtered)
    state, reasons, limitations, prefix = _coverage_state(coverage)
    claim = (
        f'{prefix}{len(filtered)} roster-movement transactions touching team '
        f'{team_id} in the trailing {window_days}-day window ending '
        f'{product_date.isoformat()} ({_category_summary(counts)}).'
    )
    return _window_object(
        TEAM_ROSTER_MOVEMENT_CHURN_RULE_ID,
        team_id,
        product_date,
        window_days,
        claim,
        _coverage_citations(coverage) + tuple(
            _transaction_citation(tx, team_id=team_id) for tx in filtered
        ),
        _coverage_input_values(coverage),
        _transaction_window_trace(
            team_id, product_date, window_days, filtered, coverage,
            decision='roster_movement_counted',
            extra={'movement_category_counts': dict(counts)},
        ),
        state,
        reasons,
        limitations,
        registry,
        templates,
        sync_run_id,
        source,
    )


def _alignment_state_object(
    team_id, product_date, window_days, transactions, coverage, registry, templates, sync_run_id, source
):
    alignment_counts = Counter(tx.roster_snapshot_alignment for tx in transactions)
    unknown_type_count = sum(1 for tx in transactions if tx.normalized_category == CATEGORY_UNKNOWN)
    reasons = []
    if alignment_counts.get(ALIGNMENT_MISALIGNED, 0):
        reasons.append(REASON_ALIGNMENT_MISALIGNED)
    if alignment_counts.get(ALIGNMENT_NO_SNAPSHOT, 0):
        reasons.append(REASON_ALIGNMENT_NO_SNAPSHOT)
    if alignment_counts.get(ALIGNMENT_UNKNOWN, 0):
        reasons.append(REASON_ALIGNMENT_UNKNOWN)
    if unknown_type_count:
        reasons.append(REASON_TRANSACTION_TYPE_UNKNOWN)
    state, coverage_reasons, limitations, prefix = _coverage_state(coverage)
    reasons = _dedupe(list(coverage_reasons) + reasons)
    claim = (
        f'{prefix}Transaction alignment state for team {team_id} in the trailing '
        f'{window_days}-day window ending {product_date.isoformat()}: '
        f'{alignment_counts.get(ALIGNMENT_ALIGNED, 0)} aligned, '
        f'{alignment_counts.get(ALIGNMENT_MISALIGNED, 0)} misaligned, '
        f'{alignment_counts.get(ALIGNMENT_NO_SNAPSHOT, 0)} no-snapshot, '
        f'{alignment_counts.get(ALIGNMENT_UNKNOWN, 0)} unknown alignment, '
        f'{unknown_type_count} unknown-type transactions.'
    )
    return _window_object(
        TEAM_TRANSACTION_ALIGNMENT_STATE_RULE_ID,
        team_id,
        product_date,
        window_days,
        claim,
        _coverage_citations(coverage) + tuple(
            _transaction_citation(tx, team_id=team_id) for tx in transactions
        ),
        _coverage_input_values(coverage),
        _transaction_window_trace(
            team_id, product_date, window_days, transactions, coverage,
            decision='stored_alignment_rolled_up',
            extra={
                'alignment_counts': dict(alignment_counts),
                'unknown_type_count': unknown_type_count,
                'local_alignment_recomputed': False,
            },
        ),
        state,
        reasons,
        limitations,
        registry,
        templates,
        sync_run_id,
        source,
    )


def _window_object(
    rule_id,
    team_id,
    product_date,
    window_days,
    claim,
    citations,
    input_values,
    trace,
    state,
    reason_codes,
    limitations,
    registry,
    templates,
    sync_run_id,
    source,
):
    return _build_object(
        rule_id=rule_id,
        subject_type='team',
        subject_id=team_id,
        subject_key=f'team:{team_id}:{product_date.isoformat()}:window-{window_days}:{rule_id}',
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(citations),
        input_values=input_values,
        trace=trace,
        limitations=tuple(limitations),
        state=state,
        reason_codes=reason_codes,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
        window_days=window_days,
    )


def _build_player_il_objects(
    *,
    product_date,
    transaction,
    current_snapshots,
    all_snapshot_by_pitcher_date,
    registry,
    templates,
    sync_run_id,
    source,
):
    if transaction.pitcher_id is None:
        return []
    built = []
    current_snapshot = _current_snapshot_for_pitcher(
        transaction.pitcher_id, current_snapshots
    )
    snapshot_citations = (
        (_snapshot_citation(current_snapshot),)
        if current_snapshot is not None
        else ()
    )
    if transaction.is_il_placement:
        claim = _il_placement_claim(transaction)
        built.append(_build_object(
            rule_id=PITCHER_IL_PLACEMENT_CONTEXT_RULE_ID,
            subject_type='pitcher',
            subject_id=transaction.pitcher_id,
            subject_key=(
                f'pitcher:{transaction.pitcher_id}:{product_date.isoformat()}:'
                f'transaction:{transaction.transaction_key}:il-placement'
            ),
            product_date=product_date,
            claim=claim,
            cited_inputs=(_transaction_citation(transaction),) + snapshot_citations,
            input_values={
                'player_transactions.transaction_key': transaction.transaction_key,
                'player_transactions.transaction_date': _iso(transaction.transaction_date),
                'player_transactions.il_list_type': transaction.il_list_type,
            },
            trace=_il_transaction_trace(transaction, current_snapshot, 'il_placement_fact'),
            limitations=(NO_HEALTH_LIMITATION,),
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        ))
    if transaction.is_il_activation:
        claim = _il_activation_claim(transaction)
        built.append(_build_object(
            rule_id=PITCHER_IL_ACTIVATION_CONTEXT_RULE_ID,
            subject_type='pitcher',
            subject_id=transaction.pitcher_id,
            subject_key=(
                f'pitcher:{transaction.pitcher_id}:{product_date.isoformat()}:'
                f'transaction:{transaction.transaction_key}:il-activation'
            ),
            product_date=product_date,
            claim=claim,
            cited_inputs=(_transaction_citation(transaction),) + snapshot_citations,
            input_values={
                'player_transactions.transaction_key': transaction.transaction_key,
                'player_transactions.transaction_date': _iso(transaction.transaction_date),
                'player_transactions.il_list_type': transaction.il_list_type,
            },
            trace=_il_transaction_trace(transaction, current_snapshot, 'il_activation_fact'),
            limitations=(NO_HEALTH_LIMITATION,),
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        ))
    return built


def _build_object(
    *,
    rule_id,
    subject_type,
    subject_id,
    subject_key,
    product_date,
    claim,
    cited_inputs,
    input_values,
    trace,
    registry,
    templates,
    sync_run_id,
    source,
    limitations=(),
    state=EvidenceObject.COMPLETENESS_COMPLETE,
    reason_codes=None,
    window_days=None,
):
    _assert_text_has_no_roster_depth_forbidden_terms(claim)
    if not cited_inputs:
        return None
    rule = registry.get(rule_id, RULE_VERSION)
    template = templates.get(_template_id(rule_id, window_days=window_days), RULE_VERSION)
    evidence = build_evidence_object(
        rule_id=rule.rule_id,
        rule_version=RULE_VERSION,
        claim_template=template,
        claim_values={'claim': claim},
        subject_type=subject_type,
        subject_id=subject_id,
        subject_key=subject_key,
        product_date=product_date,
        cited_inputs=tuple(cited_inputs),
        computation_trace=trace,
        input_values=dict(input_values or {}),
        readiness_payload=_readiness_payload(rule.required_input_families),
        limitations=tuple(limitations or ()),
        registry=registry,
        sync_run_id=sync_run_id,
        source=EVIDENCE_SOURCE,
    )
    if state != EvidenceObject.COMPLETENESS_COMPLETE or reason_codes:
        evidence.completeness_state = state
        evidence.reason_codes = _dedupe(reason_codes or [])
        evidence.rendered_claim = claim
    return BuiltRosterDepthEvidence(
        evidence=evidence,
        rule_id=rule_id,
        subject_key=evidence.subject_key,
    )


def _upsert_evidence(new_evidence):
    return _upsert_evidence_batch([new_evidence])[0]


def _upsert_evidence_batch(new_evidence_rows):
    rows = list(new_evidence_rows or ())
    if not rows:
        return []
    keys = list(dict.fromkeys(row.evidence_key for row in rows))
    existing_by_key = {}
    for key_chunk in _chunks(keys, 500):
        existing_rows = (
            EvidenceObject.query
            .filter(EvidenceObject.evidence_key.in_(key_chunk))
            .all()
        )
        existing_by_key.update({
            row.evidence_key: row
            for row in existing_rows
        })
    emitted = []
    for new_evidence in rows:
        existing = existing_by_key.get(new_evidence.evidence_key)
        if existing is None:
            db.session.add(new_evidence)
            emitted.append('created')
            continue
        _refresh_existing_evidence(existing, new_evidence)
        emitted.append('refreshed')
    db.session.flush()
    return emitted


def _refresh_existing_evidence(existing, new_evidence):
    prior_trace = {
        'rendered_claim': existing.rendered_claim,
        'completeness_state': existing.completeness_state,
        'reason_codes': list(existing.reason_codes or []),
        'invalidated_at': _iso(existing.invalidated_at),
        'invalidated_by_source_table': existing.invalidated_by_source_table,
        'invalidated_by_source_pk': existing.invalidated_by_source_pk,
    }
    for field in (
        'evidence_type',
        'subject_type',
        'subject_id',
        'subject_key',
        'product_date',
        'claim_template_id',
        'rendered_claim',
        'rule_id',
        'rule_version',
        'rule_definition_hash',
        'typed_cited_inputs',
        'computation_trace',
        'completeness_state',
        'reason_codes',
        'limitations',
        'posture',
        'source',
        'sync_run_id',
    ):
        setattr(existing, field, getattr(new_evidence, field))
    existing.computation_trace = dict(existing.computation_trace or {})
    existing.computation_trace['superseded_prior'] = prior_trace
    existing.recompute_status = EvidenceObject.RECOMPUTE_CURRENT
    existing.recompute_reason_codes = []
    existing.citations = [
        EvidenceCitation(
            source_family=citation.source_family,
            source_table=citation.source_table,
            source_pk=citation.source_pk,
            source_field_names=list(citation.source_field_names or []),
            citation_role=citation.citation_role,
            cited_values=dict(citation.cited_values or {}),
            provenance=dict(citation.provenance or {}),
        )
        for citation in new_evidence.citations
    ]
    db.session.add(existing)


def _chunks(values, size):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _latest_snapshot_sets_by_team(product_date):
    rows = (
        RosterStatusSnapshot.query
        .filter(RosterStatusSnapshot.snapshot_date <= product_date)
        .order_by(
            asc(RosterStatusSnapshot.team_id),
            asc(RosterStatusSnapshot.snapshot_date),
            asc(RosterStatusSnapshot.pitcher_id),
            asc(RosterStatusSnapshot.id),
        )
        .all()
    )
    by_team_date = defaultdict(list)
    for row in rows:
        by_team_date[(row.team_id, row.snapshot_date)].append(row)
    result = {}
    for team_id in {team_id for team_id, _ in by_team_date}:
        latest_date = max(day for candidate_team, day in by_team_date if candidate_team == team_id)
        result[team_id] = SnapshotSet(
            team_id=team_id,
            snapshot_date=latest_date,
            rows=tuple(by_team_date[(team_id, latest_date)]),
        )
    return result


def _snapshot_sets_for_date(snapshot_date):
    rows = (
        RosterStatusSnapshot.query
        .filter(RosterStatusSnapshot.snapshot_date == snapshot_date)
        .order_by(asc(RosterStatusSnapshot.team_id), asc(RosterStatusSnapshot.pitcher_id))
        .all()
    )
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.team_id].append(row)
    return {
        team_id: SnapshotSet(team_id, snapshot_date, tuple(rows))
        for team_id, rows in grouped.items()
    }


def _snapshot_rows_by_pitcher_date(dates):
    rows = (
        RosterStatusSnapshot.query
        .filter(RosterStatusSnapshot.snapshot_date.in_(tuple(dates)))
        .order_by(asc(RosterStatusSnapshot.snapshot_date), asc(RosterStatusSnapshot.pitcher_id))
        .all()
    )
    return {(row.pitcher_id, row.snapshot_date): row for row in rows}


def _transactions_for_window(start_date, end_date):
    return (
        PlayerTransaction.query
        .filter(PlayerTransaction.transaction_date >= start_date)
        .filter(PlayerTransaction.transaction_date <= end_date)
        .order_by(
            asc(PlayerTransaction.transaction_date),
            asc(PlayerTransaction.transaction_key),
            asc(PlayerTransaction.id),
        )
        .all()
    )


def _transaction_sync_windows(start_date, end_date):
    return (
        PlayerTransactionSyncWindow.query
        .filter(PlayerTransactionSyncWindow.source_query_start_date <= end_date)
        .filter(PlayerTransactionSyncWindow.source_query_end_date >= start_date)
        .order_by(
            asc(PlayerTransactionSyncWindow.source_query_start_date),
            asc(PlayerTransactionSyncWindow.source_query_end_date),
            asc(PlayerTransactionSyncWindow.id),
        )
        .all()
    )


def _team_ids(snapshot_sets, prior_sets, transactions):
    teams = set(snapshot_sets) | set(prior_sets)
    for tx in transactions:
        if tx.from_team_id is not None:
            teams.add(tx.from_team_id)
        if tx.to_team_id is not None:
            teams.add(tx.to_team_id)
    return tuple(sorted(teams))


def _pitcher_names(snapshot_sets, prior_sets, transactions):
    ids = set()
    mlb_ids = set()
    for snapshot_set in list(snapshot_sets.values()) + list(prior_sets.values()):
        for row in snapshot_set.rows:
            ids.add(row.pitcher_id)
            mlb_ids.add(row.mlb_id)
    for tx in transactions:
        if tx.pitcher_id:
            ids.add(tx.pitcher_id)
        if tx.player_mlb_id:
            mlb_ids.add(tx.player_mlb_id)
    rows = Pitcher.query.filter(or_(Pitcher.id.in_(ids or {-1}), Pitcher.mlb_id.in_(mlb_ids or {-1}))).all()
    return {row.id: row.full_name for row in rows}


def _transactions_for_team(transactions, team_id):
    return tuple(
        tx for tx in transactions
        if tx.from_team_id == team_id or tx.to_team_id == team_id
    )


def _transactions_in_window(transactions, product_date, window_days):
    start = product_date - timedelta(days=window_days - 1)
    return tuple(tx for tx in transactions if start <= tx.transaction_date <= product_date)


def _coverage_for_window(product_date, window_days, coverage_rows):
    start = product_date - timedelta(days=window_days - 1)
    days = {start + timedelta(days=offset) for offset in range(window_days)}
    relevant = tuple(
        row for row in coverage_rows
        if row.source_query_start_date <= product_date and row.source_query_end_date >= start
    )
    covered = set()
    for row in relevant:
        if row.status != WINDOW_STATUS_SUCCESS:
            continue
        row_start = max(start, row.source_query_start_date)
        row_end = min(product_date, row.source_query_end_date)
        covered.update(_days_between(row_start, row_end))
    return CoverageAnalysis(
        window_days=window_days,
        start_date=start,
        end_date=product_date,
        rows=relevant,
        uncovered_dates=tuple(sorted(days - covered)),
    )


def _analyze_census(snapshot_set):
    if snapshot_set is None:
        snapshot_set = SnapshotSet(0, None, (), missing=True)
    known_active = []
    unknown_membership = []
    non_active = []
    two_way = []
    for row in snapshot_set.rows:
        if not _is_pitcher_scoped(row):
            continue
        if _active_status(row.roster_status) and row.active_roster is True:
            known_active.append(row)
            if _is_two_way(row):
                two_way.append(row)
        elif _active_status(row.roster_status) and row.active_roster is None:
            unknown_membership.append(row)
        else:
            non_active.append(row)
    return CensusAnalysis(
        snapshot=snapshot_set,
        known_active_rows=tuple(known_active),
        unknown_membership_rows=tuple(unknown_membership),
        two_way_rows=tuple(two_way),
        non_active_rows=tuple(non_active),
    )


def _change_explanations(
    *,
    team_id,
    product_date,
    current,
    prior,
    transactions,
    all_snapshot_by_pitcher_date,
    pitcher_names,
):
    if (
        current is None
        or prior is None
        or current.snapshot_date != product_date
        or prior.snapshot_date != product_date - timedelta(days=1)
    ):
        return [], []
    current_census = _analyze_census(current)
    prior_census = _analyze_census(prior)
    if current_census.unknown_membership_rows or prior_census.unknown_membership_rows:
        return [], []
    prior_ids = {row.pitcher_id for row in prior_census.known_active_rows}
    current_ids = {row.pitcher_id for row in current_census.known_active_rows}
    changes = []
    for pitcher_id in sorted(current_ids - prior_ids):
        changes.append(_change_payload(
            'added', pitcher_id, team_id, product_date, current, prior,
            all_snapshot_by_pitcher_date, pitcher_names,
        ))
    for pitcher_id in sorted(prior_ids - current_ids):
        changes.append(_change_payload(
            'removed', pitcher_id, team_id, product_date, current, prior,
            all_snapshot_by_pitcher_date, pitcher_names,
        ))
    explained = []
    unexplained = []
    for change in changes:
        transaction = _matching_explanatory_transaction(change, transactions, team_id)
        if transaction is None:
            unexplained.append(change)
        else:
            enriched = dict(change)
            enriched['transaction'] = transaction
            explained.append(enriched)
    return explained, unexplained


def _change_payload(
    direction,
    pitcher_id,
    team_id,
    product_date,
    current,
    prior,
    all_snapshot_by_pitcher_date,
    pitcher_names,
):
    prior_row = all_snapshot_by_pitcher_date.get((pitcher_id, product_date - timedelta(days=1)))
    current_row = all_snapshot_by_pitcher_date.get((pitcher_id, product_date))
    citations = []
    if prior_row is not None:
        citations.append(_snapshot_citation(prior_row, citation_role='prior_snapshot'))
    if current_row is not None:
        citations.append(_snapshot_citation(current_row, citation_role='current_snapshot'))
    return {
        'direction': direction,
        'pitcher_id': pitcher_id,
        'name': pitcher_names.get(pitcher_id, f'pitcher {pitcher_id}'),
        'team_id': team_id,
        'snapshot_citations': tuple(citations),
    }


def _matching_explanatory_transaction(change, transactions, team_id):
    for tx in transactions:
        if tx.pitcher_id != change['pitcher_id']:
            continue
        if tx.roster_snapshot_alignment != ALIGNMENT_ALIGNED:
            continue
        if not tx.explanatory_linkage_eligible:
            continue
        if change['direction'] == 'added' and tx.to_team_id == team_id:
            return tx
        if change['direction'] == 'removed' and tx.from_team_id == team_id:
            return tx
    return None


def _latest_aligned_il_placement(pitcher_id, transactions):
    matches = [
        tx for tx in transactions
        if tx.pitcher_id == pitcher_id
        and tx.is_il_placement
        and tx.roster_snapshot_alignment == ALIGNMENT_ALIGNED
    ]
    return sorted(matches, key=lambda tx: (tx.transaction_date, tx.id))[-1] if matches else None


def _current_snapshot_for_pitcher(pitcher_id, snapshot_sets):
    for snapshot_set in snapshot_sets.values():
        for row in snapshot_set.rows:
            if row.pitcher_id == pitcher_id:
                return row
    return None


def _il_placement_claim(transaction):
    il_type = _il_list_label(transaction.il_list_type)
    if transaction.retroactive_date:
        return (
            f'On the {il_type} IL per MLB transaction data, placed '
            f'{transaction.transaction_date.isoformat()}, retroactive to '
            f'{transaction.retroactive_date.isoformat()}.'
        )
    return (
        f'On the {il_type} IL per MLB transaction data, placed '
        f'{transaction.transaction_date.isoformat()}.'
    )


def _il_activation_claim(transaction):
    il_type = _il_list_label(transaction.il_list_type)
    return (
        f'Activated from the {il_type} IL per MLB transaction data on '
        f'{transaction.transaction_date.isoformat()}.'
    )


def _il_list_label(value):
    if not value:
        return 'stored-list'
    text = str(value).replace('_', '-')
    return text


def _il_transaction_trace(transaction, current_snapshot, decision):
    return {
        'steps': [
            'Read typed IL transaction fields only.',
            'Cited current roster snapshot when stored for team attribution.',
            'Did not read transaction prose or injury prose.',
        ],
        'transaction_key': transaction.transaction_key,
        'transaction_date': _iso(transaction.transaction_date),
        'effective_date': _iso(transaction.effective_date),
        'retroactive_date': _iso(transaction.retroactive_date),
        'il_list_type': transaction.il_list_type,
        'from_team_id': transaction.from_team_id,
        'to_team_id': transaction.to_team_id,
        'current_snapshot': _snapshot_ref(current_snapshot) if current_snapshot else None,
        'decision': decision,
    }


def _census_trace(census, product_date, source_state):
    return {
        'steps': [
            'Read latest roster_status_snapshots rows on or before the evidence date.',
            'Classified active roster membership from roster_status and active_roster.',
            'Counted two-way pitchers separately when stored fields supported it.',
            'Did not partition starters from relievers.',
        ],
        'product_date': product_date.isoformat(),
        'snapshot_dates_consulted': [_iso(census.snapshot.snapshot_date)],
        'membership_decisions': [
            {
                'snapshot_id': row.id,
                'pitcher_id': row.pitcher_id,
                'roster_status': row.roster_status,
                'active_roster': row.active_roster,
                'decision': 'known_active',
                'two_way_eligible': row.two_way_eligible,
            }
            for row in census.known_active_rows
        ] + [
            {
                'snapshot_id': row.id,
                'pitcher_id': row.pitcher_id,
                'roster_status': row.roster_status,
                'active_roster': row.active_roster,
                'decision': 'membership_unknown',
            }
            for row in census.unknown_membership_rows
        ],
        'active_pitcher_count': len(census.known_active_rows),
        'two_way_count': len(census.two_way_rows),
        'unknown_membership_count': len(census.unknown_membership_rows),
        'source_state': dict(source_state),
    }


def _delta_trace(
    *,
    team_id,
    product_date,
    current,
    prior,
    all_snapshot_by_pitcher_date,
    pitcher_names,
    transactions,
    decision,
):
    prior_census = _analyze_census(prior) if prior else None
    current_census = _analyze_census(current) if current else None
    prior_ids = {row.pitcher_id for row in prior_census.known_active_rows} if prior_census else set()
    current_ids = {row.pitcher_id for row in current_census.known_active_rows} if current_census else set()
    additions = sorted(current_ids - prior_ids)
    removals = sorted(prior_ids - current_ids)
    return {
        'steps': [
            'Read prior product-day and evidence-date roster snapshots.',
            'Excluded rows with unknown active_roster membership from set arithmetic.',
            'Computed additions and removals from known active-pitcher sets.',
            'Consumed stored transaction alignment only during explanation matching.',
        ],
        'team_id': team_id,
        'product_date': product_date.isoformat(),
        'prior_snapshot_date': _iso(getattr(prior, 'snapshot_date', None)),
        'current_snapshot_date': _iso(getattr(current, 'snapshot_date', None)),
        'prior_active_pitcher_ids': sorted(prior_ids),
        'current_active_pitcher_ids': sorted(current_ids),
        'additions': [{'pitcher_id': pid, 'name': pitcher_names.get(pid)} for pid in additions],
        'removals': [{'pitcher_id': pid, 'name': pitcher_names.get(pid)} for pid in removals],
        'unknown_membership_exclusions': [
            _snapshot_ref(row)
            for row in (
                list(getattr(prior_census, 'unknown_membership_rows', ()) or ())
                + list(getattr(current_census, 'unknown_membership_rows', ()) or ())
            )
        ],
        'candidate_explanatory_transactions': [
            _transaction_ref(tx) for tx in transactions
            if tx.explanatory_linkage_eligible
            and tx.roster_snapshot_alignment == ALIGNMENT_ALIGNED
        ],
        'local_alignment_recomputed': False,
        'decision': decision,
    }


def _transaction_window_trace(team_id, product_date, window_days, transactions, coverage, decision, extra=None):
    payload = {
        'steps': [
            'Read stored player_transactions rows touching the team as source or destination.',
            'Checked player_transaction_sync_windows for every date in the team window.',
            'Counted each stored event once from the team perspective.',
            'Consumed stored normalized_category and roster_snapshot_alignment values.',
            'Did not recompute transaction alignment locally.',
        ],
        'team_id': team_id,
        'window_days': window_days,
        'window_start': coverage.start_date.isoformat(),
        'window_end': product_date.isoformat(),
        'transaction_window_coverage_checks': {
            'coverage_rows': [_coverage_row_ref(row) for row in coverage.rows],
            'uncovered_ranges': _range_payloads(coverage.uncovered_ranges),
            'complete': coverage.complete,
        },
        'transactions': [_transaction_ref(tx, team_id=team_id) for tx in transactions],
        'category_bucketing': [
            {'transaction_key': tx.transaction_key, 'normalized_category': tx.normalized_category}
            for tx in transactions
        ],
        'alignment_consumption_from_stored_values': [
            {
                'transaction_key': tx.transaction_key,
                'roster_snapshot_alignment': tx.roster_snapshot_alignment,
                'explanatory_linkage_eligible': tx.explanatory_linkage_eligible,
            }
            for tx in transactions
        ],
        'repeat_player_counting': dict(Counter(tx.pitcher_id or tx.player_mlb_id for tx in transactions)),
        'cross_team_perspective': [
            {
                'transaction_key': tx.transaction_key,
                'perspective': _team_perspective(tx, team_id),
            }
            for tx in transactions
        ],
        'decision': decision,
    }
    payload.update(extra or {})
    return payload


def _snapshot_citations_for_set(snapshot_set):
    return tuple(_snapshot_citation(row) for row in (snapshot_set.rows if snapshot_set else ()))


def _snapshot_citation(row, *, citation_role='supporting_input'):
    fields = (
        'pitcher_id',
        'mlb_id',
        'team_id',
        'snapshot_date',
        'roster_status',
        'active_roster',
        'forty_man_roster',
        'position_code',
        'position_name',
        'position_type',
        'two_way_eligible',
    )
    return EvidenceCitationInput(
        source_family='roster_status_snapshots',
        source_table='roster_status_snapshots',
        source_pk=row.id,
        source_field_names=fields,
        citation_role=citation_role,
        cited_values={field: _citation_value(getattr(row, field, None)) for field in fields},
        provenance={
            'source': row.source,
            'sync_run_id': row.sync_run_id,
            'correction_count': row.correction_count or 0,
            'last_corrected_at': _iso(row.last_corrected_at),
            'correction_source': row.correction_source,
            'snapshot_date': _iso(row.snapshot_date),
        },
    )


def _missing_snapshot_citation(team_id, product_date):
    return EvidenceCitationInput(
        source_family='roster_status_snapshots',
        source_table='roster_status_snapshots',
        source_pk=f'missing:team:{team_id}:{product_date.isoformat()}',
        source_field_names=('snapshot_date', 'team_id', 'roster_status', 'active_roster'),
        citation_role='missing_input',
        cited_values={
            'team_id': team_id,
            'snapshot_date': None,
            'roster_status': None,
            'active_roster': None,
        },
        provenance={'source': EVIDENCE_SOURCE},
    )


def _transaction_citation(row, *, team_id=None, citation_role='supporting_input'):
    fields = (
        'transaction_key',
        'player_mlb_id',
        'pitcher_id',
        'from_team_id',
        'to_team_id',
        'transaction_date',
        'effective_date',
        'retroactive_date',
        'transaction_type_code',
        'normalized_category',
        'is_il_placement',
        'is_il_activation',
        'il_list_type',
        'roster_snapshot_alignment',
        'alignment_reason_code',
        'explanatory_linkage_eligible',
    )
    values = {field: _citation_value(getattr(row, field, None)) for field in fields}
    if team_id is not None:
        values['team_perspective'] = _team_perspective(row, team_id)
    return EvidenceCitationInput(
        source_family='player_transactions',
        source_table='player_transactions',
        source_pk=row.id,
        source_field_names=fields,
        citation_role=citation_role,
        cited_values=values,
        provenance={
            'source': row.source,
            'source_endpoint': row.source_endpoint,
            'sync_run_id': row.sync_run_id,
            'correction_count': row.correction_count or 0,
            'last_corrected_at': _iso(row.last_corrected_at),
            'correction_source': row.correction_source,
        },
    )


def _coverage_citations(coverage):
    return tuple(_coverage_citation(row) for row in coverage.rows)


def _coverage_citation(row):
    fields = (
        'source_query_start_date',
        'source_query_end_date',
        'status',
        'records_fetched',
        'records_stored',
        'unknown_type_count',
        'alignment_unknown_count',
        'alignment_misaligned_count',
        'alignment_no_snapshot_count',
    )
    return EvidenceCitationInput(
        source_family='player_transactions',
        source_table='player_transaction_sync_windows',
        source_pk=row.id,
        source_field_names=fields,
        citation_role='window_coverage',
        cited_values={field: _citation_value(getattr(row, field, None)) for field in fields},
        provenance={
            'source': row.source,
            'source_endpoint': row.source_endpoint,
            'sync_run_id': row.sync_run_id,
            'attempted_at': _iso(row.attempted_at),
            'successful_at': _iso(row.successful_at),
        },
    )


def _coverage_input_values(coverage):
    first = coverage.rows[0] if coverage.rows else None
    return {
        'player_transactions.source_query_start_date': _iso(getattr(first, 'source_query_start_date', None)),
        'player_transactions.source_query_end_date': _iso(getattr(first, 'source_query_end_date', None)),
        'player_transactions.status': getattr(first, 'status', None),
    }


def _coverage_state(coverage):
    if coverage.complete:
        return EvidenceObject.COMPLETENESS_COMPLETE, [], [], ''
    return (
        EvidenceObject.COMPLETENESS_PARTIAL,
        [REASON_TRANSACTION_WINDOW_UNCOVERED],
        [LOWER_BOUND_COVERAGE_LIMITATION],
        'At least ',
    )


def _roster_source_state(product_date):
    try:
        from services.roster_status_sync import roster_status_cache_divergence_count
        divergence_count = int(roster_status_cache_divergence_count() or 0)
    except Exception:
        divergence_count = 0
    return {
        'status': SOURCE_READY,
        'reason_codes': [],
        'cache_divergence_count': divergence_count,
        'product_date': product_date.isoformat(),
    }


def _readiness_payload(required_families):
    return {
        'families': {
            family: {'status': SOURCE_READY, 'reason_codes': []}
            for family in required_families
        }
    }


def _is_pitcher_scoped(row):
    return row is not None and row.pitcher_id is not None


def _active_status(value):
    return str(value or '').strip().lower() == 'active'


def _is_il_status(value):
    text = str(value or '').strip().lower().replace('_', ' ')
    return text in {'il', 'injured list'} or ' il' in f' {text}' or 'injured' in text


def _is_two_way(row):
    fields = (
        str(row.position_code or ''),
        str(row.position_name or ''),
        str(row.position_type or ''),
    )
    return bool(row.two_way_eligible) or any('two' in value.lower() for value in fields)


def _first_snapshot_value(rows, field_name):
    for row in rows or ():
        value = getattr(row, field_name, None)
        if value is not None:
            return _citation_value(value)
    return None


def _team_perspective(tx, team_id):
    perspectives = []
    if tx.from_team_id == team_id:
        perspectives.append('source')
    if tx.to_team_id == team_id:
        perspectives.append('destination')
    return '+'.join(perspectives) if perspectives else 'none'


def _category_summary(counts):
    if not counts:
        return '0 events'
    parts = []
    for category, count in sorted(dict(counts).items()):
        if count:
            label = 'unknown-type' if category == CATEGORY_UNKNOWN else category
            parts.append(f'{count} {label}')
    return ', '.join(parts) if parts else '0 events'


def _change_summary(changes):
    parts = []
    for change in changes:
        verb = 'added' if change['direction'] == 'added' else 'removed'
        parts.append(f"{change['name']} {verb}")
    return ', '.join(parts)


def _change_trace(change):
    payload = {
        'direction': change['direction'],
        'pitcher_id': change['pitcher_id'],
        'name': change['name'],
    }
    if change.get('transaction') is not None:
        payload['transaction_key'] = change['transaction'].transaction_key
        payload['stored_alignment'] = change['transaction'].roster_snapshot_alignment
        payload['explanatory_linkage_eligible'] = change['transaction'].explanatory_linkage_eligible
    return payload


def _names(ids, names):
    return ', '.join(names.get(pid, f'pitcher {pid}') for pid in ids)


def _snapshot_ref(row):
    if row is None:
        return None
    return {
        'id': row.id,
        'pitcher_id': row.pitcher_id,
        'team_id': row.team_id,
        'snapshot_date': _iso(row.snapshot_date),
        'roster_status': row.roster_status,
        'active_roster': row.active_roster,
    }


def _transaction_ref(row, *, team_id=None):
    payload = {
        'id': row.id,
        'transaction_key': row.transaction_key,
        'pitcher_id': row.pitcher_id,
        'player_mlb_id': row.player_mlb_id,
        'from_team_id': row.from_team_id,
        'to_team_id': row.to_team_id,
        'transaction_date': _iso(row.transaction_date),
        'normalized_category': row.normalized_category,
        'roster_snapshot_alignment': row.roster_snapshot_alignment,
        'alignment_reason_code': row.alignment_reason_code,
        'explanatory_linkage_eligible': row.explanatory_linkage_eligible,
    }
    if team_id is not None:
        payload['team_perspective'] = _team_perspective(row, team_id)
    return payload


def _coverage_row_ref(row):
    return {
        'id': row.id,
        'source_query_start_date': _iso(row.source_query_start_date),
        'source_query_end_date': _iso(row.source_query_end_date),
        'status': row.status,
        'records_fetched': row.records_fetched,
        'records_stored': row.records_stored,
    }


def _days_between(start, end):
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _date_ranges(days):
    if not days:
        return ()
    sorted_days = sorted(days)
    ranges = []
    start = previous = sorted_days[0]
    for day in sorted_days[1:]:
        if day == previous + timedelta(days=1):
            previous = day
            continue
        ranges.append((start, previous))
        start = previous = day
    ranges.append((start, previous))
    return tuple(ranges)


def _range_payloads(ranges):
    return [
        {'start': start.isoformat(), 'end': end.isoformat()}
        for start, end in ranges
    ]


def _citation_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _template_id(rule_id, *, window_days=None):
    if window_days is not None:
        return f'{rule_id}_{window_days}d_claim'
    return f'{rule_id}_claim'


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _iso(value):
    return value.isoformat() if value is not None else None


def _dedupe(values):
    result = []
    seen = set()
    for value in values or []:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
