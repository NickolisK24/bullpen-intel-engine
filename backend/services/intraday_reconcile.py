"""Audit-only intraday reconciliation (Phase 1 — check-only, zero writes).

BaseballOS runs three authoritative sync modes today: ``daily`` (full morning
reconciliation), ``postgame`` (completed-game ingestion + trailing repair), and
``backfill`` (explicit historical replay). A fourth mode, ``intraday``, is meant
to be a lightweight, delta-aware reconciliation throughout the baseball day so a
midday roster change — for example the Phillies recalling Seth Johnson after the
morning daily sync on 2026-07-16 — is noticed before the next full sync.

This module is **Phase 1 of intraday only**: it is strictly AUDIT-ONLY. It
answers "what would need to change?" without changing anything. It:

* fetches current authoritative source state through the same MLB client, retry
  policy, and source-reading helpers the daily/postgame syncs already own;
* compares that source state with the currently stored BaseballOS state;
* reports detected roster, assignment, transaction, and schedule/finality
  differences, the affected teams and pitchers, and a dry-run impact plan;
* performs **no** canonical baseball-data writes, **no** snapshot publication,
  **no** fatigue recalculation, **no** story generation, and **no** public cache
  warming.

Everything here reuses the read-only acquisition and classification surface of
the production sync (``build_team_roster_status_index`` / ``classify_roster_evidence``,
``get_transactions`` + ``is_non_player_transaction`` + ``_values_from_transaction``,
``get_schedule`` + ``classify_status`` + ``resolve_scheduled_game_finality``).
It deliberately never calls the mutating orchestrators (``sync_roster_statuses``,
``sync_team_assignments``, ``sync_transactions``, ``ingest_schedule``), never
records or resolves dead letters, and never acquires the sync writer guard — an
audit writes nothing, so it neither blocks nor is blocked by a running sync.

Identity governance mirrors the production rule exactly: source rows are matched
to a stored pitcher only through the MLB numeric id. A source row that lacks a
usable id (or presents conflicting official team evidence) is reported as
unknown/unresolved and is never matched by name.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import logging

from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction
from models.scheduled_game import ScheduledGame
from services import sync_metadata
from services import transaction_ingestion as transactions_service
from services.availability_reference_date import product_current_date
from services.game_finality import (
    OTHER_STATUS_STATE,
    POSTPONED_STATUS_STATE,
    SCHEDULED_STATUS_STATE,
    classify_status,
    scheduled_rows_have_unresolved_resumed_linkage,
)
from services.mlb_api import mlb_client
from services.roster_status import (
    STATUS_ACTIVE,
    STATUS_DFA,
    STATUS_IL_10,
    STATUS_IL_15,
    STATUS_IL_60,
    STATUS_MINORS,
    STATUS_OPTIONED,
    classify_roster_status,
)
from services.roster_status_sync import (
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPES,
    build_team_roster_status_index,
    classify_roster_evidence,
)
from services.team_assignment_sync import MLB_TEAM_IDS
from utils.db import db
from utils.time import to_utc_iso, utc_now_naive


logger = logging.getLogger(__name__)

# Stable, versioned output contract identity. The capability string carries the
# contract major version so consumers (and the workflow's artifact validator)
# can pin to it; VERSION is the fine-grained contract version.
CAPABILITY = 'intraday_reconciliation_audit_v1'
# Fine-grained contract version.
#   1.0.0 -> 1.1.0 : signal-quality correction (benign inventory aggregated, not
#                    serialized; summary buckets; active-roster-only default).
#   1.1.0 -> 1.2.0 : bullpen-relevance correction (Production Observation #2).
#                    Transaction findings now prove bullpen relevance (pitcher /
#                    two-way) before becoming materially actionable; public team
#                    impact is scoped to the governed MLB clubs; exact
#                    transaction-state alignment is separated from public
#                    active-bullpen membership; historical option/IL effects are
#                    chronology- and current-membership-aware.
#   1.2.0 -> 1.3.0 : transaction-ledger vs public-materiality split (Production
#                    Observation #3). A missing/actionable transaction record is
#                    no longer conflated with a current public bullpen-state
#                    change: every meaningful transaction finding now exposes two
#                    independent axes (transaction_record_actionable and
#                    public_bullpen_material). Public impact (affected teams,
#                    targeted workload, snapshot, warm) is derived from the roster
#                    lane's current-state authority only; transaction-ledger-only
#                    findings get a separate would_refresh.transaction_ledger
#                    plan. Additive only (new fields / sub-plans / summary
#                    buckets; the flat would_refresh fields stay, now sourced from
#                    public_bullpen_state), and none of the fields the workflow
#                    validator checks change — a backward-compatible minor bump.
#   1.3.0 -> 1.4.0 : summary-contract clarification (Production Observation #4).
#                    The reconciliation, source acquisition, materiality
#                    decisions, and impact plan are UNCHANGED; only the aggregate
#                    summary counts are made unambiguous. Every summary count now
#                    has one explicit scope and one derivation source
#                    (_derive_summary_counts): all-lane finding tallies
#                    (total_meaningful_findings / total_actionable_findings), the
#                    transaction-LEDGER axis (transaction_record_actionable_count /
#                    transaction_ledger_only_findings /
#                    transaction_public_bullpen_material_count), the per-lane
#                    public tallies (public_roster_change_count /
#                    schedule_public_change_count), and the deduplicated GLOBAL
#                    public_bullpen_change_count (same roster authority + overlap
#                    rules as build_impact_plan). The ambiguous legacy names
#                    actionable_bullpen_differences, actionable_differences,
#                    public_bullpen_material_count, public_roster_changes,
#                    total_differences, and public_membership_mismatches are
#                    removed (no runtime consumer depended on them). Additive/
#                    clarifying only; capability identity and the fields the
#                    workflow validator checks are unchanged — a minor bump.
VERSION = '1.4.0'

MODE = 'intraday'
PHASE = 1

# Overall audit status values.
STATUS_SUCCESS = 'success'
STATUS_PARTIAL = 'partial'
STATUS_FAILED = 'failed'
STATUS_SKIPPED = 'skipped'
RECOGNIZED_STATUSES = (STATUS_SUCCESS, STATUS_PARTIAL, STATUS_FAILED, STATUS_SKIPPED)

# Reason code emitted when a public sync writer already holds the advisory lock.
REASON_PUBLIC_SYNC_WRITER_ACTIVE = 'public_sync_writer_active'
REASON_PUBLIC_SYNC_LOCK_UNAVAILABLE = 'public_sync_writer_lock_unavailable'
# Reason code emitted when production Flask initialization / audit startup fails
# before the audit could acquire the lock or read any source (e.g. a required
# production secret such as ADMIN_API_TOKEN is missing).
REASON_APPLICATION_BOOTSTRAP_FAILED = 'application_bootstrap_failed'

# Per-lane verification status.
LANE_COMPLETE = 'complete'
LANE_PARTIAL = 'partial'
LANE_FAILED = 'failed'
LANE_NOT_CHECKED = 'not_checked'

# The three reconciliation lanes this audit runs, plus the derived plan lane.
LANE_ROSTER_ASSIGNMENT = 'roster_assignment'
LANE_TRANSACTIONS = 'transactions'
LANE_SCHEDULE_FINALITY = 'schedule_finality'
ALL_LANES = (LANE_ROSTER_ASSIGNMENT, LANE_TRANSACTIONS, LANE_SCHEDULE_FINALITY)

# Roster source scope. The approved intraday question is only whether the current
# MLB *active*-roster state changed after the morning sync, so the production
# default fetches one active-roster request per team (~30 calls), not the full
# four-roster-type sweep (~120 calls). The deep set stays available for manual
# diagnostics where the specific inactive destination (IL / optioned / DFA) must
# be read directly from official evidence.
DEFAULT_ROSTER_TYPES = (ROSTER_TYPE_ACTIVE,)
DEEP_ROSTER_TYPES = ROSTER_TYPES

# How many trailing slate dates the schedule/finality lane inspects in addition
# to the current product date. One day back catches games that ended after
# midnight ET or that were still non-final when the morning sync ran.
DEFAULT_SCHEDULE_LOOKBACK_DAYS = 1

# Injured-list roster statuses (used only to name a status transition; the
# canonical membership decision comes from ``classify_roster_status``).
_IL_STATUSES = frozenset({STATUS_IL_10, STATUS_IL_15, STATUS_IL_60})
_OPTION_STATUSES = frozenset({STATUS_OPTIONED, STATUS_MINORS})

# Lane 1 change types.
CHANGE_RECALL = 'recall'
CHANGE_OPTION = 'option'
CHANGE_IL_ACTIVATION = 'il_activation'
CHANGE_IL_PLACEMENT = 'il_placement'
CHANGE_DFA = 'dfa'
CHANGE_ROSTER_ACTIVATION = 'roster_activation'
CHANGE_ROSTER_DEACTIVATION = 'roster_deactivation'
CHANGE_ROSTER_STATUS_CHANGE = 'roster_status_change'
CHANGE_TEAM_ASSIGNMENT_CHANGE = 'team_assignment_change'
CHANGE_NEWLY_DISCOVERED_ACTIVE = 'newly_discovered_active'
CHANGE_REMOVED_FROM_ACTIVE_ROSTER = 'removed_from_active_roster'
CHANGE_CONFLICTING_OFFICIAL_TEAM = 'conflicting_official_team_evidence'
CHANGE_UNRESOLVED_SOURCE_IDENTITY = 'unresolved_source_identity'

# Bullpen-population effect of a detected roster change.
EFFECT_ENTER = 'enter'
EFFECT_LEAVE = 'leave'
EFFECT_NONE = 'none'

# Finding severity — drives changed vs material_change semantics.
#   actionable      → a future authorized write / recompute would be required.
#   review_required → a real finding a human must resolve, but the audit cannot
#                     safely determine a write action (changed, but not material).
SEVERITY_ACTIONABLE = 'actionable'
SEVERITY_REVIEW = 'review_required'

# ── Bullpen-role verification (Correction 1) ────────────────────────────────
# BaseballOS is a bullpen-only product, so a transaction is materially actionable
# only when it is proven to involve a pitcher or two-way player. Role is resolved
# from the MLB numeric id alone — never inferred from transaction type, player
# name, destination team, or stored absence.
ROLE_PROVEN_PITCHER = 'proven_pitcher'
ROLE_PROVEN_TWO_WAY = 'proven_two_way'
ROLE_PROVEN_NON_PITCHER = 'proven_non_pitcher'
ROLE_UNRESOLVED = 'unresolved'
# Only these two roles may become materially actionable bullpen findings.
BULLPEN_RELEVANT_ROLES = frozenset({ROLE_PROVEN_PITCHER, ROLE_PROVEN_TWO_WAY})

# How the role was established (role_verification_status).
ROLE_SOURCE_STORED_PITCHER = 'stored_pitcher'          # tracked Pitcher row
ROLE_SOURCE_ROSTER_REUSE = 'roster_lane_reuse'         # already resolved by roster lane
ROLE_SOURCE_ROSTER_EVIDENCE = 'source_position_evidence'  # position on the source row
ROLE_SOURCE_PEOPLE_LOOKUP = 'mlb_people_lookup'        # /people/{id} primaryPosition
ROLE_SOURCE_LOOKUP_FAILED = 'people_lookup_failed'
ROLE_SOURCE_LOOKUP_BUDGET = 'people_lookup_budget_exceeded'
ROLE_SOURCE_NO_EVIDENCE = 'no_role_evidence'

# Bounded role acquisition (Correction 2): at most this many /people lookups per
# audit run. Beyond it, remaining roles stay unresolved with a limitation — never
# guessed as pitchers.
DEFAULT_MAX_ROLE_LOOKUPS = 40

# MLB pitcher / two-way identity from official position evidence.
_PITCHER_POSITION_CODES = frozenset({'1'})
_TWO_WAY_POSITION_CODES = frozenset({'Y'})
_PITCHER_POSITION_ABBRS = frozenset({'P'})
_TWO_WAY_POSITION_ABBRS = frozenset({'TWP'})

# ── MLB-team impact scope (Correction 3) ────────────────────────────────────
# Only the governed MLB clubs may enter public team-level recomputation or public
# snapshot planning. Minor-league / affiliate / academy / unknown team ids remain
# in transaction evidence but never in public impact fields.
MLB_TEAM_ID_SET = frozenset(MLB_TEAM_IDS)

# ── Lane 2 transaction classifications ──────────────────────────────────────
# Event-aware: single-player events use the player-level classes; compound events
# (multiple source components sharing one MLB transaction id) use the compound_*
# classes so one event never manufactures several per-component conflicts.
TX_NON_PLAYER = 'non_player_transaction'
TX_UNRESOLVED_IDENTITY = 'unresolved_identity'
TX_INVALID_SHAPE = 'invalid_shape'
TX_ACTIONABLE_NOT_STORED = 'actionable_not_stored'
TX_STORED_CONFLICT = 'stored_conflict'
TX_ALREADY_REFLECTED = 'already_reflected'
TX_COMPOUND_NEW = 'compound_transaction_new'
TX_COMPOUND_REVIEW = 'compound_transaction_review_required'
TX_COMPOUND_REFLECTED = 'compound_event_reflected'
# Bullpen-relevance (Correction 1) and refined membership semantics (Corrections
# 4/5/6). ``status_effect_unreflected`` is retained only as a deprecated alias —
# it is no longer emitted; the refined classes below replace it so an exact
# transaction-detail difference never masquerades as a material public-state
# change.
TX_STATUS_EFFECT_UNREFLECTED = 'status_effect_unreflected'  # deprecated (unused)
TX_NON_PITCHER = 'non_pitcher_transaction'
TX_BULLPEN_RELEVANCE_UNRESOLVED = 'bullpen_relevance_unresolved'
TX_PUBLIC_BULLPEN_EFFECT_UNREFLECTED = 'public_bullpen_effect_unreflected'
TX_TRANSACTION_DETAIL_MISMATCH = 'transaction_detail_mismatch'
TX_SUPERSEDED_TRANSACTION = 'superseded_transaction'
TX_CURRENT_STATE_ALIGNED = 'current_state_aligned'
TX_CHRONOLOGY_UNRESOLVED = 'chronology_unresolved'

# Which transaction classifications are meaningful (serialized into differences)
# and, of those, which imply an actionable future write. Only proven
# bullpen-relevant, current-state-material findings are actionable.
TX_ACTIONABLE_CLASSES = frozenset({
    TX_ACTIONABLE_NOT_STORED,
    TX_STORED_CONFLICT,
    TX_PUBLIC_BULLPEN_EFFECT_UNREFLECTED,
    TX_COMPOUND_NEW,
})
TX_REVIEW_CLASSES = frozenset({
    TX_UNRESOLVED_IDENTITY,
    TX_INVALID_SHAPE,
    TX_COMPOUND_REVIEW,
    TX_BULLPEN_RELEVANCE_UNRESOLVED,
    TX_CHRONOLOGY_UNRESOLVED,
})
TX_MEANINGFUL_CLASSES = TX_ACTIONABLE_CLASSES | TX_REVIEW_CLASSES
# Benign / informational classes are counted but never serialized row-by-row.
# Non-pitcher transactions, superseded historical effects, and exact non-governed
# detail differences whose current public bullpen membership is correct are all
# benign for a bullpen product.
TX_BENIGN_CLASSES = frozenset({
    TX_ALREADY_REFLECTED,
    TX_NON_PLAYER,
    TX_COMPOUND_REFLECTED,
    TX_NON_PITCHER,
    TX_TRANSACTION_DETAIL_MISMATCH,
    TX_SUPERSEDED_TRANSACTION,
    TX_CURRENT_STATE_ALIGNED,
})

# Roster-affecting transaction categories and the active-bullpen direction each
# implies (Correction 6 chronology). A category not listed here does not by
# itself flip active-roster membership.
_TX_ENTER_CATEGORIES = frozenset({
    transactions_service.CATEGORY_RECALL,
    transactions_service.CATEGORY_IL_ACTIVATION,
    transactions_service.CATEGORY_ROSTER_ACTIVATION,
    transactions_service.CATEGORY_CONTRACT_SELECTION,
})
_TX_LEAVE_CATEGORIES = frozenset({
    transactions_service.CATEGORY_OPTION,
    transactions_service.CATEGORY_IL_PLACEMENT,
    transactions_service.CATEGORY_ROSTER_DEACTIVATION,
    transactions_service.CATEGORY_DFA,
    transactions_service.CATEGORY_OUTRIGHT,
    transactions_service.CATEGORY_RELEASE,
})
_TX_ROSTER_AFFECTING_CATEGORIES = _TX_ENTER_CATEGORIES | _TX_LEAVE_CATEGORIES

# ── Transaction public-effect governance (Corrections 1/2/3, Observation #3) ──
# Whether a transaction TYPE can plausibly change current MLB active-bullpen
# membership. This is the single governed surface used to decide public
# materiality; the reconciliation loop never guesses inline.
EFFECT_SCOPE_ACTIVE_ROSTER = 'active_roster_affecting'
EFFECT_SCOPE_LEDGER_ONLY = 'organization_or_ledger_only'
EFFECT_SCOPE_CONTEXT_DEPENDENT = 'context_dependent'
EFFECT_SCOPE_UNKNOWN = 'unknown'

# Context-dependent categories: they MAY change active membership, but only a
# current roster confirmation can establish it — the transaction alone cannot.
_TX_CONTEXT_DEPENDENT_CATEGORIES = frozenset({
    transactions_service.CATEGORY_TRADE,
    transactions_service.CATEGORY_CONTRACT_SELECTION,
    transactions_service.CATEGORY_OUTRIGHT,
})
# Organization / transaction-ledger-only source type codes: signings, assignments
# and similar records that do NOT by themselves establish active MLB status.
# Normalized category is CATEGORY_UNKNOWN for these, so they are recognized by
# their raw source type code, failing closed to ledger-only.
_TX_LEDGER_ONLY_TYPE_CODES = frozenset({
    'SGN', 'SIGNED', 'SFA', 'FA', 'ASG', 'ASGN', 'ASSIGNED', 'AA', 'RELEASE_ANN',
    'ASG_ORG', 'SE', 'CLW_ORG',
})

# Roster-confirmation status of a transaction participant against the roster
# lane's current-state authority (Correction 4/7).
ROSTER_CONFIRM_CHANGE = 'confirmed_change'      # official != stored -> current change
ROSTER_CONFIRM_ALIGNED = 'confirmed_aligned'    # official == stored -> already reflected
ROSTER_CONFIRM_UNVERIFIED = 'unverified'        # not on a fetched roster / unknown
ROSTER_CONFIRM_NOT_APPLICABLE = 'not_applicable'

# Transaction classifications whose RECORD a future write phase would ingest or
# reconcile (transaction-ledger actionable). This is independent of whether the
# event proves a current public bullpen-state change.
TX_LEDGER_ACTIONABLE_CLASSES = frozenset({
    TX_ACTIONABLE_NOT_STORED,
    TX_STORED_CONFLICT,
    TX_COMPOUND_NEW,
})

# Current public active-bullpen membership alignment (Correction 4).
MEMBERSHIP_ALIGNED = 'aligned'
MEMBERSHIP_MISALIGNED = 'misaligned'
MEMBERSHIP_UNKNOWN = 'unknown'

# Chronology resolution states (Correction 6).
CHRONOLOGY_LATEST = 'latest_applicable'
CHRONOLOGY_SUPERSEDED = 'superseded'
CHRONOLOGY_UNRESOLVED = 'unresolved'
CHRONOLOGY_NOT_APPLICABLE = 'not_applicable'

# Provenance/query-window fields on a stored transaction are not substantive
# facts — a stored transaction is not "in conflict" merely because a later audit
# used a different query window. Compare only the substantive transaction facts.
_TX_PROVENANCE_FIELDS = frozenset({
    'source',
    'source_endpoint',
    'source_query_start_date',
    'source_query_end_date',
})
_TX_MEANINGFUL_FIELDS = tuple(
    field
    for field in transactions_service.TRANSACTION_FACT_FIELDS
    if field not in _TX_PROVENANCE_FIELDS
)
# Audit-derived fields (roster-snapshot alignment) are the audit's own
# computation, not source facts. They must not manufacture a stored_conflict —
# a misaligned alignment is surfaced through the status_effect_unreflected
# classification instead. Source-fact comparison excludes them.
_TX_DERIVED_FIELDS = frozenset({
    'roster_snapshot_alignment',
    'alignment_reason_code',
    'explanatory_linkage_eligible',
})
_TX_SOURCE_FACT_FIELDS = tuple(
    field for field in _TX_MEANINGFUL_FIELDS if field not in _TX_DERIVED_FIELDS
)
# Event-level facts shared by all components of one MLB transaction event. Only
# these are compared for a compound event — never per-component player fields.
_TX_EVENT_LEVEL_FIELDS = ('transaction_date', 'transaction_type_code', 'normalized_category')

# Maximum benign-record samples included per informational class (deterministic,
# with an explicit suppressed count). Actionable/review findings are NEVER capped.
DEFAULT_TX_SAMPLE_LIMIT = 3

# Lane 3 schedule/finality change types.
GAME_POSTPONED = 'game_postponed'
GAME_RESCHEDULED = 'game_rescheduled'
GAME_IN_PROGRESS = 'game_in_progress'
GAME_NOW_FINAL = 'game_now_final'
GAME_STORED_FINALITY_CONFLICT = 'stored_finality_conflict'
GAME_NEWLY_DISCOVERED = 'newly_discovered_game'
GAME_ABSENT_FROM_SOURCE = 'stored_game_absent_from_source'
GAME_RESCHEDULE_IDENTITY_ISSUE = 'reschedule_identity_issue'
GAME_SCHEDULE_STATUS_CHANGE = 'schedule_status_change'


# ── small pure helpers ──────────────────────────────────────────────────────

def _iso_date(value):
    return value.isoformat() if isinstance(value, date) else None


def _int_or_none(value):
    """Coerce a source value to int, or None. Local so the audit does not depend
    on any private coercion helper of another module."""
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


def _entry_is_pitcher(entry):
    """True when a raw MLB roster entry describes a pitcher (or two-way player).

    Only used to decide whether a source-only player is bullpen-relevant. MLB
    encodes the pitcher position as code ``1`` / abbreviation ``P`` and the
    two-way position as code ``Y`` / abbreviation ``TWP``.
    """
    entry = entry or {}
    position = entry.get('position') or {}
    person = entry.get('person') or {}
    primary = person.get('primaryPosition') or {}
    codes = {str(position.get('code') or ''), str(primary.get('code') or '')}
    abbrs = {
        str(position.get('abbreviation') or '').upper(),
        str(primary.get('abbreviation') or '').upper(),
    }
    types = {
        str(position.get('type') or '').lower(),
        str(primary.get('type') or '').lower(),
    }
    if '1' in codes or 'Y' in codes:
        return True
    if 'P' in abbrs or 'TWP' in abbrs:
        return True
    return 'pitcher' in types or 'two-way player' in types


def _first_entry(evidence):
    entries = (evidence or {}).get('entries') or {}
    for roster_type in ROSTER_TYPES:
        entry = entries.get(roster_type)
        if entry:
            return entry
    # Fall back to whatever roster type is present.
    return next(iter(entries.values()), None)


def _entry_player_name(entry):
    """Source player name for human-readable evidence (never used for matching)."""
    person = (entry or {}).get('person') or {}
    return _string_or_none(person.get('fullName'))


def _roster_severity(change_type):
    """Actionable roster changes imply a future write; conflicting/unresolved
    evidence is review-required (changed, but not safely writable)."""
    if change_type in (CHANGE_CONFLICTING_OFFICIAL_TEAM, CHANGE_UNRESOLVED_SOURCE_IDENTITY):
        return SEVERITY_REVIEW
    return SEVERITY_ACTIONABLE


def _status_is_active(status):
    return status == STATUS_ACTIVE


def _roster_change_type(*, stored_status, official_status, became_active, became_inactive):
    """Name the roster-status transition using the same vocabulary the daily
    sync and transaction ingestion already use."""
    if became_active:
        if stored_status in _IL_STATUSES:
            return CHANGE_IL_ACTIVATION
        if stored_status in _OPTION_STATUSES:
            return CHANGE_RECALL
        return CHANGE_ROSTER_ACTIVATION
    if became_inactive:
        if official_status in _IL_STATUSES:
            return CHANGE_IL_PLACEMENT
        if official_status in _OPTION_STATUSES:
            return CHANGE_OPTION
        if official_status == STATUS_DFA:
            return CHANGE_DFA
        return CHANGE_ROSTER_DEACTIVATION
    return CHANGE_ROSTER_STATUS_CHANGE


# ── team identity ───────────────────────────────────────────────────────────

def _build_team_identity_map(client):
    """Resolve MLB team id → {name, abbreviation} for human-readable reporting.

    Sourced from the same ``get_all_teams`` endpoint the assignment sync uses,
    seeded from stored pitcher rows so a team that fails to fetch still resolves
    to its cached abbreviation. Read-only.
    """
    team_map = {}
    rows = (
        db.session.query(
            Pitcher.team_id,
            Pitcher.team_name,
            Pitcher.team_abbreviation,
        )
        .filter(Pitcher.team_id.isnot(None))
        .distinct()
        .all()
    )
    for team_id, team_name, team_abbreviation in rows:
        if team_id is None:
            continue
        team_map[int(team_id)] = {
            'team_id': int(team_id),
            'team_name': team_name,
            'team_abbreviation': team_abbreviation,
        }

    try:
        teams = client.get_all_teams() or []
    except Exception as exc:  # noqa: BLE001 - identity labels degrade, audit continues
        logger.warning('intraday audit: get_all_teams failed for team labels: %s', exc)
        teams = []
    for team in teams:
        team_id = team.get('id') if isinstance(team, dict) else None
        if team_id is None:
            continue
        team_map[int(team_id)] = {
            'team_id': int(team_id),
            'team_name': team.get('name'),
            'team_abbreviation': team.get('abbreviation'),
        }
    return team_map


def _abbr(team_map, team_id):
    if team_id is None:
        return None
    return (team_map.get(int(team_id)) or {}).get('team_abbreviation')


# ── Lane 1: active roster + team assignment ─────────────────────────────────

def reconcile_active_rosters_and_assignments(
    *,
    client,
    team_map,
    check_timestamp_iso,
    team_ids=None,
    roster_types=DEFAULT_ROSTER_TYPES,
):
    """Compare official active-roster / team-assignment evidence for every MLB
    team against the stored BaseballOS pitcher state. Read-only.

    The production default fetches active-roster evidence only (one request per
    team). It still detects entry to / departure from the active roster, team
    movement, newly discovered active pitchers, duplicate active-roster evidence,
    unresolved source identities, and fetch failures. Where only entry or
    departure is proven, neutral change types (``roster_activation`` /
    ``removed_from_active_roster``) are used unless the stored status or
    transaction context safely provides a more specific reason; an exact inactive
    destination is never inferred from absence on the active roster alone. Pass
    ``roster_types=DEEP_ROSTER_TYPES`` for the manual deep-diagnostic sweep."""
    team_ids = list(team_ids or MLB_TEAM_IDS)
    requested_team_ids = {int(team_id) for team_id in team_ids}
    evidence_source = 'mlb_stats_api:roster'

    # Official evidence keyed by MLB player id. A player appearing on more than
    # one team's rosters is a genuine conflict and is never auto-resolved.
    official = defaultdict(dict)  # mlb_id -> {team_id: {...}}
    fetch_failures = []
    failed_team_ids = set()
    unresolved_source_identities = []

    for team_id in team_ids:
        index, errors = build_team_roster_status_index(
            team_id, client=client, roster_types=roster_types
        )
        for error in errors:
            reason = error.get('reason')
            if reason == 'fetch_failed':
                failed_team_ids.add(team_id)
                fetch_failures.append({
                    'team_id': team_id,
                    'team_abbreviation': _abbr(team_map, team_id),
                    'roster_type': error.get('roster_type'),
                    'error': error.get('error'),
                })
            elif reason == 'missing_player_identity':
                # Source row that cannot be safely matched to an MLB identity.
                unresolved_source_identities.append({
                    'team_id': team_id,
                    'team_abbreviation': _abbr(team_map, team_id),
                    'roster_type': error.get('roster_type'),
                    'change_type': CHANGE_UNRESOLVED_SOURCE_IDENTITY,
                    'evidence_source': evidence_source,
                    'check_timestamp': check_timestamp_iso,
                    'reason': 'source roster entry missing a usable MLB player id',
                })
        for mlb_id, evidence in index.items():
            classification = classify_roster_evidence(evidence)
            entry = _first_entry(evidence)
            official[int(mlb_id)][int(team_id)] = {
                'classification': classification,
                'is_pitcher': _entry_is_pitcher(entry),
                'active_roster': ROSTER_TYPE_ACTIVE in set(evidence.get('roster_types') or ()),
                # Source name is kept for human-readable evidence only; the MLB
                # numeric id remains the sole identity-matching authority.
                'player_name': _entry_player_name(entry),
            }

    differences = []
    stored_pitchers = Pitcher.query.all()
    stored_mlb_ids = set()

    for pitcher in stored_pitchers:
        mlb_id = pitcher.mlb_id
        stored_mlb_ids.add(mlb_id)

        official_teams_preview = official.get(mlb_id)
        # Only evaluate pitchers within the audited scope: those stored on a
        # team we actually fetched, or those the source now places on an audited
        # team (a move into scope). Pitchers entirely outside the requested team
        # set are neither fetched nor concludable, so they are skipped.
        in_scope = (
            (pitcher.team_id is not None and int(pitcher.team_id) in requested_team_ids)
            or bool(official_teams_preview)
        )
        if not in_scope:
            continue

        stored_state = classify_roster_status(pitcher)
        stored_status = stored_state['status']
        stored_active = stored_state['is_active_mlb']  # True / False / None
        stored_team_id = pitcher.team_id

        official_teams = official_teams_preview

        if not official_teams:
            # Absent from every official roster. Fail closed if the pitcher's
            # stored team could not be fetched this pass — never infer removal
            # from a fetch failure. Only a pitcher stored as active-and-present
            # who is now gone is a material bullpen delta.
            if stored_team_id in failed_team_ids:
                continue
            if stored_active is not True:
                continue
            differences.append(_lane1_difference(
                pitcher=pitcher,
                stored_state=stored_state,
                team_map=team_map,
                change_type=CHANGE_REMOVED_FROM_ACTIVE_ROSTER,
                observed_official_status=None,
                observed_official_team_id=None,
                bullpen_effect=EFFECT_LEAVE,
                targeted_recent_work_required=False,
                evidence_source=evidence_source,
                check_timestamp_iso=check_timestamp_iso,
            ))
            continue

        if len(official_teams) > 1:
            # Conflicting official team evidence — report, do not resolve.
            conflict_team_ids = sorted(official_teams.keys())
            differences.append(_lane1_difference(
                pitcher=pitcher,
                stored_state=stored_state,
                team_map=team_map,
                change_type=CHANGE_CONFLICTING_OFFICIAL_TEAM,
                observed_official_status=None,
                observed_official_team_id=None,
                bullpen_effect=EFFECT_NONE,
                targeted_recent_work_required=False,
                evidence_source=evidence_source,
                check_timestamp_iso=check_timestamp_iso,
                extra={'conflicting_official_team_ids': conflict_team_ids},
            ))
            continue

        official_team_id, official_entry = next(iter(official_teams.items()))
        official_status = official_entry['classification']['status']
        official_active = _status_is_active(official_status)

        team_changed = (
            stored_team_id is not None
            and int(official_team_id) != int(stored_team_id)
        )
        became_active = official_active and stored_active is not True
        became_inactive = (not official_active) and stored_active is True
        status_changed = official_status != stored_status

        if not (team_changed or status_changed or became_active or became_inactive):
            continue  # official and stored agree — no delta

        if team_changed:
            change_type = CHANGE_TEAM_ASSIGNMENT_CHANGE
        else:
            change_type = _roster_change_type(
                stored_status=stored_status,
                official_status=official_status,
                became_active=became_active,
                became_inactive=became_inactive,
            )

        if became_active:
            bullpen_effect = EFFECT_ENTER
        elif became_inactive:
            bullpen_effect = EFFECT_LEAVE
        else:
            bullpen_effect = EFFECT_NONE

        # A pitcher who becomes active (or moves to a new team while active)
        # would need targeted recent-work acquisition during a future write
        # phase so their recent appearances land in the bullpen reads.
        targeted_recent_work_required = bool(
            official_active and (became_active or team_changed)
        )

        differences.append(_lane1_difference(
            pitcher=pitcher,
            stored_state=stored_state,
            team_map=team_map,
            change_type=change_type,
            observed_official_status=official_status,
            observed_official_team_id=official_team_id,
            bullpen_effect=bullpen_effect,
            targeted_recent_work_required=targeted_recent_work_required,
            evidence_source=official_entry['classification'].get('source') or evidence_source,
            check_timestamp_iso=check_timestamp_iso,
        ))

    # Source-only pitchers on an official active roster with no stored pitcher
    # row: newly discovered active players. Restricted to pitching positions so
    # position players never enter the bullpen audit.
    for mlb_id, official_teams in official.items():
        if mlb_id in stored_mlb_ids:
            continue
        active_pitcher_team = next(
            (
                team_id
                for team_id, entry in official_teams.items()
                if entry['active_roster'] and entry['is_pitcher']
            ),
            None,
        )
        if active_pitcher_team is None:
            continue
        entry = official_teams[active_pitcher_team]
        differences.append({
            'mlb_player_id': mlb_id,
            'stored_pitcher_id': None,
            # Human-readable source name preserved when MLB supplies it.
            'player_name': entry.get('player_name'),
            'team_id': active_pitcher_team,
            'team_abbreviation': _abbr(team_map, active_pitcher_team),
            'stored_status': None,
            'observed_official_status': entry['classification']['status'],
            'stored_team_id': None,
            'stored_team_abbreviation': None,
            'observed_official_team_id': active_pitcher_team,
            'observed_official_team_abbreviation': _abbr(team_map, active_pitcher_team),
            'change_type': CHANGE_NEWLY_DISCOVERED_ACTIVE,
            'severity': SEVERITY_ACTIONABLE,
            'evidence_source': entry['classification'].get('source') or evidence_source,
            'check_timestamp': check_timestamp_iso,
            'bullpen_population_effect': EFFECT_ENTER,
            'targeted_recent_work_required': True,
        })

    # Fold unresolved source identities into differences as review-required
    # findings (they set changed=true but never drive a write plan), while also
    # keeping the named list for detailed reporting.
    for entry in unresolved_source_identities:
        entry['severity'] = SEVERITY_REVIEW
    differences.extend(unresolved_source_identities)

    roster_status_change_types = {
        CHANGE_RECALL, CHANGE_OPTION, CHANGE_IL_ACTIVATION, CHANGE_IL_PLACEMENT,
        CHANGE_DFA, CHANGE_ROSTER_ACTIVATION, CHANGE_ROSTER_DEACTIVATION,
        CHANGE_ROSTER_STATUS_CHANGE, CHANGE_REMOVED_FROM_ACTIVE_ROSTER,
        CHANGE_NEWLY_DISCOVERED_ACTIVE,
    }
    roster_status_diffs = [
        d for d in differences if d['change_type'] in roster_status_change_types
    ]
    assignment_diffs = [
        d for d in differences if d['change_type'] == CHANGE_TEAM_ASSIGNMENT_CHANGE
    ]

    # Deterministic ordering so identical inputs yield identical output.
    differences.sort(key=lambda d: (str(d.get('change_type')), d.get('mlb_player_id') or 0))
    unresolved_source_identities.sort(
        key=lambda e: (e.get('team_id') or 0, str(e.get('roster_type')))
    )

    # Affected identity sets are derived from ACTIONABLE roster findings only —
    # conflicting or unresolved evidence never adds a team or pitcher to a write
    # plan.
    actionable_diffs = [d for d in differences if d.get('severity') == SEVERITY_ACTIONABLE]
    # Public team impact is scoped to the governed MLB clubs (Correction 3).
    affected_team_ids = _mlb_team_ids({
        d['team_id'] for d in actionable_diffs if d.get('team_id') is not None
    } | {
        d['stored_team_id'] for d in actionable_diffs if d.get('stored_team_id') is not None
    })
    affected_pitcher_ids = sorted({
        d['stored_pitcher_id'] for d in actionable_diffs if d.get('stored_pitcher_id') is not None
    })
    affected_pitcher_mlb_ids = sorted({
        d['mlb_player_id'] for d in actionable_diffs if d.get('mlb_player_id') is not None
    })

    # Current active-bullpen membership authority for the cross-lane transaction
    # reconciliation (Correction 7): official active membership vs stored state,
    # keyed by MLB id. A player whose relevant team could not be fetched is left
    # unverified so the transaction lane never asserts a mismatch it cannot prove.
    current_state_index = _build_current_state_index(
        official, stored_pitchers, requested_team_ids, failed_team_ids,
    )

    # A team whose rosters could not be fully fetched means this lane could not
    # fully verify — its "no change" for that team is not proof of no change.
    limitations = []
    verification_status = LANE_COMPLETE
    if fetch_failures:
        verification_status = LANE_PARTIAL
        unfetched = sorted({f['team_id'] for f in fetch_failures if f.get('team_id') is not None})
        limitations.append(
            'roster source fetch failed for team_id(s) '
            f'{unfetched}; those teams were not fully verified and their absence '
            'of changes is not conclusive'
        )

    return {
        'verification_status': verification_status,
        'checked': {
            'teams_requested': len(team_ids),
            'teams_fetched': len(team_ids) - len(failed_team_ids),
            'teams_failed': len(failed_team_ids),
            'stored_pitchers': len(stored_pitchers),
            'source_players_seen': len(official),
            'roster_status_differences': len(roster_status_diffs),
            'team_assignment_differences': len(assignment_diffs),
            'unresolved_source_identities': len(unresolved_source_identities),
            'total_differences': len(differences),
        },
        'differences': differences,
        'unresolved_source_identities': unresolved_source_identities,
        'fetch_failures': fetch_failures,
        'limitations': limitations,
        'affected_team_ids': affected_team_ids,
        'affected_pitcher_ids': affected_pitcher_ids,
        'affected_pitcher_mlb_ids': affected_pitcher_mlb_ids,
        'current_state_index': current_state_index,
        'targeted_recent_work_pitcher_ids': sorted({
            d['stored_pitcher_id']
            for d in differences
            if d.get('targeted_recent_work_required') and d.get('stored_pitcher_id') is not None
        }),
        'targeted_recent_work_mlb_ids': sorted({
            d['mlb_player_id']
            for d in differences
            if d.get('targeted_recent_work_required') and d.get('mlb_player_id') is not None
        }),
    }


def _official_active_membership(official_teams):
    """Return (mlb_team_id, official_active) for a player's official evidence:
    active on a governed MLB club's active roster, or (None, False)."""
    for team_id, entry in (official_teams or {}).items():
        if int(team_id) in MLB_TEAM_ID_SET and entry.get('active_roster') \
                and _status_is_active(entry['classification']['status']):
            return int(team_id), True
    return None, False


def _build_current_state_index(official, stored_pitchers, requested_team_ids, failed_team_ids):
    index = {}
    for pitcher in stored_pitchers:
        mlb_id = pitcher.mlb_id
        if mlb_id is None:
            continue
        stored_state = classify_roster_status(pitcher)
        official_teams = official.get(mlb_id) or {}
        official_team_id, official_active = _official_active_membership(official_teams)
        team_fetched = (
            pitcher.team_id is not None
            and int(pitcher.team_id) in requested_team_ids
            and pitcher.team_id not in failed_team_ids
        )
        verified = bool(official_teams) or team_fetched
        index[mlb_id] = {
            'official_active': official_active if verified else None,
            'official_team_id': official_team_id,
            'stored_active': stored_state['is_active_mlb'],
            'stored_pitcher_id': pitcher.id,
            'verified': verified,
        }
    for mlb_id, official_teams in official.items():
        if mlb_id in index:
            continue
        official_team_id, official_active = _official_active_membership(official_teams)
        index[mlb_id] = {
            'official_active': official_active,
            'official_team_id': official_team_id,
            'stored_active': None,
            'stored_pitcher_id': None,
            'verified': True,
        }
    return index


def _lane1_difference(
    *,
    pitcher,
    stored_state,
    team_map,
    change_type,
    observed_official_status,
    observed_official_team_id,
    bullpen_effect,
    targeted_recent_work_required,
    evidence_source,
    check_timestamp_iso,
    extra=None,
):
    # The "relevant" team for at-a-glance reporting is the official team when
    # known, otherwise the stored team.
    relevant_team_id = (
        observed_official_team_id
        if observed_official_team_id is not None
        else pitcher.team_id
    )
    difference = {
        'mlb_player_id': pitcher.mlb_id,
        'stored_pitcher_id': pitcher.id,
        'player_name': pitcher.full_name,
        'team_id': relevant_team_id,
        'team_abbreviation': _abbr(team_map, relevant_team_id),
        'stored_status': stored_state['status'],
        'observed_official_status': observed_official_status,
        'stored_team_id': pitcher.team_id,
        'stored_team_abbreviation': pitcher.team_abbreviation,
        'observed_official_team_id': observed_official_team_id,
        'observed_official_team_abbreviation': _abbr(team_map, observed_official_team_id),
        'change_type': change_type,
        'severity': _roster_severity(change_type),
        'evidence_source': evidence_source,
        'check_timestamp': check_timestamp_iso,
        'bullpen_population_effect': bullpen_effect,
        'targeted_recent_work_required': bool(targeted_recent_work_required),
    }
    if extra:
        difference.update(extra)
    return difference


# ── Bullpen-role verification + MLB-team scope (Corrections 1, 2, 3) ─────────

def _classify_role_from_position(*, code, abbreviation, position_type):
    """Governed bullpen role from official MLB position evidence. Never inferred
    from transaction type, player name, or destination team."""
    code = _string_or_none(code)
    abbr = (_string_or_none(abbreviation) or '').upper()
    ptype = (_string_or_none(position_type) or '').lower()
    if code in _TWO_WAY_POSITION_CODES or abbr in _TWO_WAY_POSITION_ABBRS or 'two-way' in ptype:
        return ROLE_PROVEN_TWO_WAY
    if code in _PITCHER_POSITION_CODES or abbr in _PITCHER_POSITION_ABBRS or ptype == 'pitcher':
        return ROLE_PROVEN_PITCHER
    if code or abbr or ptype:
        return ROLE_PROVEN_NON_PITCHER
    return ROLE_UNRESOLVED


def _position_fields(position):
    position = position or {}
    return {
        'official_position_code': _string_or_none(position.get('code')),
        'official_position_abbreviation': _string_or_none(position.get('abbreviation')),
        'official_position_type': _string_or_none(position.get('type')),
    }


def _role_evidence_from_source(transaction):
    """Reuse any position evidence already present on the source transaction row.
    Most MLB transaction rows carry no position, so this usually returns None and
    a bounded ``/people`` lookup is used instead."""
    person = (transaction or {}).get('person') or {}
    position = (
        (transaction or {}).get('position')
        or person.get('primaryPosition')
        or {}
    )
    fields = _position_fields(position)
    if not any(fields.values()):
        return None
    relevance = _classify_role_from_position(
        code=fields['official_position_code'],
        abbreviation=fields['official_position_abbreviation'],
        position_type=fields['official_position_type'],
    )
    if relevance == ROLE_UNRESOLVED:
        return None
    return {
        'bullpen_relevance': relevance,
        'role_verification_status': ROLE_SOURCE_ROSTER_EVIDENCE,
        'role_evidence_source': ROLE_SOURCE_ROSTER_EVIDENCE,
        **fields,
    }


class _RoleResolver:
    """Resolve bullpen relevance for transaction participants, MLB id only.

    Precedence: a tracked Pitcher row → proven_pitcher; else position evidence on
    the source row; else a bounded, deduplicated, cached ``/people`` lookup. Fails
    closed (unresolved) on lookup error or when the per-run budget is exhausted —
    an unchecked player is never classified as a pitcher (Corrections 1 and 2)."""

    def __init__(self, client, *, max_lookups=DEFAULT_MAX_ROLE_LOOKUPS, roster_current_state=None):
        self._client = client
        self._max_lookups = max(0, int(max_lookups))
        self._roster_current_state = roster_current_state or {}
        self._cache = {}
        self._candidate_ids = set()
        self.lookups_used = 0
        self.lookups_avoided = 0
        self.budget_exceeded = False
        self.lookup_failures = 0

    @property
    def candidates(self):
        return len(self._candidate_ids)

    def _stored_role(self, status):
        return {
            'bullpen_relevance': ROLE_PROVEN_PITCHER,
            'role_verification_status': status,
            'role_evidence_source': status,
            'official_position_code': None,
            'official_position_abbreviation': None,
            'official_position_type': None,
        }

    def _unresolved(self, status):
        return {
            'bullpen_relevance': ROLE_UNRESOLVED,
            'role_verification_status': status,
            'role_evidence_source': status,
            'official_position_code': None,
            'official_position_abbreviation': None,
            'official_position_type': None,
        }

    def resolve(self, *, mlb_id, stored_pitcher_id, transaction=None):
        if mlb_id is None:
            if stored_pitcher_id is not None:
                return self._stored_role(ROLE_SOURCE_STORED_PITCHER)
            return self._unresolved(ROLE_SOURCE_NO_EVIDENCE)
        if mlb_id in self._cache:
            return self._cache[mlb_id]

        # This participant genuinely needs a role decision (a lookup candidate).
        self._candidate_ids.add(mlb_id)

        # A tracked Pitcher row exists — proven bullpen-relevant, no /people lookup.
        if stored_pitcher_id is not None:
            self.lookups_avoided += 1
            result = self._stored_role(ROLE_SOURCE_STORED_PITCHER)
            self._cache[mlb_id] = result
            return result

        # Reuse the roster lane's evidence: a player it already resolved to a
        # tracked pitcher needs no /people lookup (Correction 9).
        roster_state = self._roster_current_state.get(mlb_id)
        if roster_state and roster_state.get('stored_pitcher_id') is not None:
            self.lookups_avoided += 1
            result = self._stored_role(ROLE_SOURCE_ROSTER_REUSE)
            self._cache[mlb_id] = result
            return result

        evidence = _role_evidence_from_source(transaction)
        if evidence is not None:
            self.lookups_avoided += 1
            self._cache[mlb_id] = evidence
            return evidence

        if self.lookups_used >= self._max_lookups:
            self.budget_exceeded = True
            result = self._unresolved(ROLE_SOURCE_LOOKUP_BUDGET)
            self._cache[mlb_id] = result
            return result

        # Count the lookup before issuing it so a failure still consumes budget
        # and can never be silently retried into a pitcher classification.
        self.lookups_used += 1
        try:
            person = self._client.get_player_info(mlb_id)
        except Exception as exc:  # noqa: BLE001 - fail closed, never guess a role
            logger.warning('intraday audit: role lookup failed for mlb_id=%s: %s', mlb_id, exc)
            self.lookup_failures += 1
            result = self._unresolved(ROLE_SOURCE_LOOKUP_FAILED)
            self._cache[mlb_id] = result
            return result

        position = (person or {}).get('primaryPosition') or {}
        fields = _position_fields(position)
        relevance = _classify_role_from_position(
            code=fields['official_position_code'],
            abbreviation=fields['official_position_abbreviation'],
            position_type=fields['official_position_type'],
        )
        if relevance == ROLE_UNRESOLVED:
            # Position evidence absent/unusable — fail closed rather than guess.
            self.lookup_failures += 1
            result = self._unresolved(ROLE_SOURCE_LOOKUP_FAILED)
            self._cache[mlb_id] = result
            return result
        result = {
            'bullpen_relevance': relevance,
            'role_verification_status': ROLE_SOURCE_PEOPLE_LOOKUP,
            'role_evidence_source': ROLE_SOURCE_PEOPLE_LOOKUP,
            **fields,
        }
        self._cache[mlb_id] = result
        return result


def _mlb_team_ids(ids):
    """Filter an iterable of team ids to the governed MLB clubs only."""
    return sorted({int(t) for t in ids if t is not None and int(t) in MLB_TEAM_ID_SET})


def _non_mlb_team_ids(ids):
    """The non-MLB (affiliate / minor-league / unknown) team ids observed —
    preserved as evidence, never entered into public impact planning."""
    return sorted({int(t) for t in ids if t is not None and int(t) not in MLB_TEAM_ID_SET})


# ── Lane 2: transactions ────────────────────────────────────────────────────

def reconcile_transactions(
    *,
    client,
    team_map,
    check_timestamp,
    check_timestamp_iso,
    end_date,
    window_days=transactions_service.TRANSACTION_SYNC_WINDOW_DAYS,
    sample_limit=DEFAULT_TX_SAMPLE_LIMIT,
    role_resolver=None,
    roster_current_state=None,
):
    """Compare recent official transactions against stored transaction evidence.

    Event-aware, bullpen-relevance-gated, and current-membership-aware. Source
    records are grouped by their stable MLB transaction-event id. A transaction is
    materially actionable only when it is proven to involve a pitcher or two-way
    player (Correction 1): role is resolved from the MLB numeric id via a stored
    Pitcher row, source position evidence, or a bounded ``/people`` lookup
    (Correction 2). Exact stored-transaction alignment is separated from public
    active-bullpen membership (Correction 4); a historical option/IL effect whose
    latest applicable event and current official membership prove the player is
    correctly outside the active bullpen is benign, not material (Corrections
    5/6). Public team impact is scoped to the governed MLB clubs (Correction 3).
    Only meaningful findings are serialized; benign inventory is counted and
    bounded-sampled. Read-only: no insert, update, resolution, or dead-letter
    write.
    """
    role_resolver = role_resolver or _RoleResolver(client)
    roster_current_state = roster_current_state or {}
    start_date = end_date - timedelta(days=window_days)
    evidence_source = transactions_service.SOURCE_ENDPOINT

    fetch_error = None
    try:
        source_transactions = client.get_transactions(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
    except Exception as exc:  # noqa: BLE001 - source failure degrades this lane only
        fetch_error = str(exc)
        source_transactions = []
    if not isinstance(source_transactions, list):
        source_transactions = []

    all_findings = []
    non_player_by_event = defaultdict(int)

    # ── Phase 1: classify each source record into a component with an event key.
    events = {}          # event_key -> list of player component dicts
    event_order = []     # first-seen order of event keys (deterministic)
    player_events = defaultdict(list)  # mlb_id -> [component] for chronology

    for transaction in source_transactions:
        if not isinstance(transaction, dict):
            all_findings.append({
                'classification': TX_INVALID_SHAPE,
                'severity': SEVERITY_REVIEW,
                'reason': 'transaction row is not an object',
                'evidence_source': evidence_source,
                'check_timestamp': check_timestamp_iso,
            })
            continue

        if transactions_service.is_non_player_transaction(transaction):
            tx_id = _string_or_none(transaction.get('transaction_id'))
            if tx_id is not None:
                non_player_by_event[f'statsapi:{tx_id}'] += 1
            record = _lane2_base_record(
                transaction, team_map, evidence_source, check_timestamp_iso,
                classification=TX_NON_PLAYER,
            )
            record['severity'] = None
            all_findings.append(record)
            continue

        values, detail = transactions_service.read_transaction_values(
            transaction,
            start_date=start_date,
            end_date=end_date,
            timestamp=check_timestamp,
            sync_run_id=None,
        )
        if detail is not None:
            classification = (
                TX_UNRESOLVED_IDENTITY
                if detail.get('entity_type') == transactions_service.TRANSACTION_IDENTITY_ENTITY_TYPE
                else TX_INVALID_SHAPE
            )
            record = _lane2_base_record(
                transaction, team_map, evidence_source, check_timestamp_iso,
                classification=classification,
            )
            record['severity'] = SEVERITY_REVIEW
            record['reason'] = detail.get('reason')
            all_findings.append(record)
            continue

        # A resolvable player component. Group by the shared event key.
        event_key = values['transaction_key']
        category = values.get('normalized_category')
        component = {
            'transaction': transaction,
            'values': values,
            'event_key': event_key,
            'player_mlb_id': values.get('player_mlb_id'),
            'from_team_id': values.get('from_team_id'),
            'to_team_id': values.get('to_team_id'),
            'normalized_category': category,
            'pitcher_id': values.get('pitcher_id'),
            # Exact stored-state alignment (Correction 4): NOT public membership.
            'transaction_state_alignment': values.get('roster_snapshot_alignment'),
            'effect_direction': _tx_effect_direction(category),
        }
        if event_key not in events:
            events[event_key] = []
            event_order.append(event_key)
        events[event_key].append(component)
        if component['player_mlb_id'] is not None:
            player_events[component['player_mlb_id']].append(component)

    # ── Phase 2: reconcile each event (single-player or compound). Role is
    # resolved only for events that reach a meaningful/membership classification,
    # so lookups stay bounded to unstored, potentially-meaningful participants.
    for event_key in event_order:
        components = events[event_key]
        existing = PlayerTransaction.query.filter_by(transaction_key=event_key).first()
        if len(components) == 1:
            finding = _reconcile_single_player_event(
                components[0], existing, event_key, team_map,
                evidence_source, check_timestamp_iso,
                role_resolver, player_events, roster_current_state,
            )
        else:
            finding = _reconcile_compound_event(
                components, existing, event_key, non_player_by_event.get(event_key, 0),
                team_map, evidence_source, check_timestamp_iso, role_resolver,
            )
        all_findings.append(finding)

    limitations = []
    if fetch_error is not None:
        verification_status = LANE_FAILED
        limitations.append(
            f'transaction source fetch failed ({fetch_error}); the transaction '
            'lane could not be verified this run'
        )
    else:
        verification_status = LANE_COMPLETE
    if role_resolver.budget_exceeded:
        limitations.append(
            'role-verification lookup budget was exhausted this run; the remaining '
            'transaction participants could not be verified as bullpen-relevant and '
            'are reported unresolved (never assumed to be pitchers)'
        )
    if role_resolver.lookup_failures:
        limitations.append(
            f'{role_resolver.lookup_failures} role-verification lookup(s) failed; '
            'those participants are reported unresolved, not assumed pitchers'
        )

    lane = {
        'verification_status': verification_status,
        'window': {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'window_days': window_days,
        },
        '_all_findings': all_findings,
        'limitations': limitations,
        'role_verification': {
            'role_lookups_used': role_resolver.lookups_used,
            'role_lookups_avoided': role_resolver.lookups_avoided,
            'role_lookup_candidates': role_resolver.candidates,
            'role_lookup_budget': role_resolver._max_lookups,
            # Back-compat aliases.
            'lookups_used': role_resolver.lookups_used,
            'lookup_budget': role_resolver._max_lookups,
            'budget_exceeded': role_resolver.budget_exceeded,
            'lookup_failures': role_resolver.lookup_failures,
        },
        '_source_transactions': len(source_transactions),
        '_source_events': len(event_order),
    }
    if fetch_error is not None:
        lane['fetch_error'] = fetch_error
    _finalize_transaction_lane(lane, roster_current_state, sample_limit=sample_limit)
    return lane


def _tx_effect_direction(category):
    if category in _TX_ENTER_CATEGORIES:
        return EFFECT_ENTER
    if category in _TX_LEAVE_CATEGORIES:
        return EFFECT_LEAVE
    return EFFECT_NONE


def classify_transaction_public_effect(transaction_type_code, normalized_category):
    """Governed classification of whether a transaction TYPE can plausibly change
    current MLB active-bullpen membership (Correction 2). The single surface used
    to decide public materiality; unknown types fail closed (never public-material
    without independent current roster evidence).

    Returns a dict with ``transaction_effect_scope``,
    ``may_change_active_mlb_membership``, ``effect_direction``,
    ``requires_roster_confirmation``, ``ledger_relevant``, and
    ``public_effect_reason``.
    """
    code = (_string_or_none(transaction_type_code) or '').strip().upper()
    if normalized_category in _TX_ROSTER_AFFECTING_CATEGORIES:
        return {
            'transaction_effect_scope': EFFECT_SCOPE_ACTIVE_ROSTER,
            'may_change_active_mlb_membership': True,
            'effect_direction': _tx_effect_direction(normalized_category),
            'requires_roster_confirmation': True,
            'ledger_relevant': True,
            'public_effect_reason': (
                'active-roster-affecting transaction category; may change active '
                'MLB membership, subject to current roster confirmation'
            ),
        }
    if normalized_category in _TX_CONTEXT_DEPENDENT_CATEGORIES:
        return {
            'transaction_effect_scope': EFFECT_SCOPE_CONTEXT_DEPENDENT,
            'may_change_active_mlb_membership': True,
            'effect_direction': EFFECT_NONE,
            'requires_roster_confirmation': True,
            'ledger_relevant': True,
            'public_effect_reason': (
                'context-dependent transaction (trade / selection / outright); only '
                'current roster evidence can establish an active-membership change'
            ),
        }
    if code in _TX_LEDGER_ONLY_TYPE_CODES:
        return {
            'transaction_effect_scope': EFFECT_SCOPE_LEDGER_ONLY,
            'may_change_active_mlb_membership': False,
            'effect_direction': EFFECT_NONE,
            'requires_roster_confirmation': True,
            'ledger_relevant': True,
            'public_effect_reason': (
                'organization / transaction-ledger-only record (signing, assignment); '
                'does not establish current active MLB bullpen membership'
            ),
        }
    return {
        'transaction_effect_scope': EFFECT_SCOPE_UNKNOWN,
        'may_change_active_mlb_membership': False,
        'effect_direction': EFFECT_NONE,
        'requires_roster_confirmation': True,
        'ledger_relevant': True,
        'public_effect_reason': (
            'unknown / unsupported transaction type; fails closed — not '
            'public-material without independent current roster evidence'
        ),
    }


def _roster_confirmation(state):
    """Map a roster-lane current-state entry to a confirmation status + membership
    alignment for a transaction participant (Correction 4/7)."""
    if not state or not state.get('verified') or state.get('official_active') is None:
        return ROSTER_CONFIRM_UNVERIFIED, MEMBERSHIP_UNKNOWN
    official_active = bool(state.get('official_active'))
    stored_active = state.get('stored_active')
    if stored_active is None:
        # Source-only (unstored) player the roster lane sees as active — a current
        # bullpen-population change owned by the roster lane.
        if official_active:
            return ROSTER_CONFIRM_CHANGE, MEMBERSHIP_MISALIGNED
        return ROSTER_CONFIRM_UNVERIFIED, MEMBERSHIP_UNKNOWN
    if official_active != bool(stored_active):
        return ROSTER_CONFIRM_CHANGE, MEMBERSHIP_MISALIGNED
    return ROSTER_CONFIRM_ALIGNED, MEMBERSHIP_ALIGNED


def _apply_actionability_axes(record, roster_current_state):
    """Attach the two independent actionability axes to a meaningful transaction
    finding (Correction 1): ``transaction_record_actionable`` (does the ledger
    need this record?) and ``public_bullpen_material`` (does this event prove a
    current public MLB bullpen-state change?). Public materiality requires an
    active-roster-affecting type AND roster-lane confirmation of a current change
    for a proven bullpen-relevant player — never role, recency, or a missing
    record alone."""
    classification = record.get('classification')
    scope = classify_transaction_public_effect(
        record.get('transaction_type_code'), record.get('normalized_category'),
    )
    record['transaction_effect_scope'] = scope['transaction_effect_scope']
    record['may_change_active_mlb_membership'] = scope['may_change_active_mlb_membership']

    record['transaction_record_actionable'] = classification in TX_LEDGER_ACTIONABLE_CLASSES

    mlb_id = record.get('player_mlb_id')
    state = roster_current_state.get(mlb_id) if mlb_id is not None else None
    confirmation, membership = _roster_confirmation(state)
    record['roster_confirmation_status'] = confirmation

    relevant = record.get('bullpen_relevance') in BULLPEN_RELEVANT_ROLES
    if classification == TX_PUBLIC_BULLPEN_EFFECT_UNREFLECTED:
        record['public_bullpen_material'] = True
        record['public_bullpen_material_reason'] = (
            'roster lane confirms current active-bullpen membership differs from '
            'stored state for this proven pitcher'
        )
    elif (scope['may_change_active_mlb_membership'] and relevant
          and confirmation == ROSTER_CONFIRM_CHANGE):
        record['public_bullpen_material'] = True
        record['public_bullpen_material_reason'] = (
            'active-roster-affecting transaction for a proven pitcher whose current '
            'membership change is confirmed by roster evidence'
        )
    else:
        record['public_bullpen_material'] = False
        if not scope['may_change_active_mlb_membership']:
            record['public_bullpen_material_reason'] = (
                'transaction type cannot establish a current active MLB bullpen '
                'change; ledger-relevant only'
            )
        elif not relevant:
            record['public_bullpen_material_reason'] = (
                'participant is not a proven bullpen-relevant pitcher'
            )
        else:
            record['public_bullpen_material_reason'] = (
                'no current roster confirmation of an active-bullpen change'
            )
    return record


def _finalize_transaction_lane(lane, roster_current_state=None, *, sample_limit=DEFAULT_TX_SAMPLE_LIMIT):
    """Recompute serialized differences, counts, samples, and the two independent
    result surfaces from ``lane['_all_findings']`` (Observation #3, Correction 5):
    a PUBLIC surface (proven current bullpen-state changes only — a subset of the
    roster lane's authority) and a transaction-LEDGER surface (records a future
    write phase would ingest/reconcile). Idempotent."""
    roster_current_state = roster_current_state or {}
    all_findings = lane.get('_all_findings') or []
    counts = defaultdict(int)
    differences = []
    benign_samples = defaultdict(list)

    for finding in all_findings:
        _apply_actionability_axes(finding, roster_current_state)
        classification = finding.get('classification')
        counts[classification] += 1
        if classification in TX_MEANINGFUL_CLASSES:
            differences.append(finding)
        elif len(benign_samples[classification]) < sample_limit:
            benign_samples[classification].append(finding)

    actionable = [d for d in differences if d.get('severity') == SEVERITY_ACTIONABLE]
    review = [d for d in differences if d.get('severity') == SEVERITY_REVIEW]
    ledger_findings = [d for d in differences if d.get('transaction_record_actionable')]
    public_findings = [d for d in differences if d.get('public_bullpen_material')]

    # PUBLIC surface — only findings that prove a current public bullpen-state
    # change (always a subset of the roster lane's authority). Team ids MLB-scoped.
    public_pitcher_ids = set()
    public_pitcher_mlb_ids = set()
    public_team_ids_raw = set()
    for d in public_findings:
        public_pitcher_ids.update(_finding_bullpen_pitcher_ids(d))
        public_pitcher_mlb_ids.update(_finding_bullpen_mlb_ids(d))
        public_team_ids_raw.update(_finding_bullpen_team_ids(d))

    # LEDGER surface — records to ingest / reconcile, independent of public state.
    ledger_participant_mlb_ids = set()
    ledger_team_ids_raw = set()
    ingest_event_keys = set()
    reconcile_event_keys = set()
    for d in ledger_findings:
        ledger_participant_mlb_ids.update(_finding_bullpen_mlb_ids(d))
        ledger_team_ids_raw.update(t for t in _finding_team_ids(d) if t is not None)
        event_key = d.get('event_key')
        if event_key:
            if d.get('classification') == TX_STORED_CONFLICT:
                reconcile_event_keys.add(event_key)
            else:
                ingest_event_keys.add(event_key)

    all_team_ids_raw = set()
    for finding in all_findings:
        all_team_ids_raw.update(t for t in _finding_team_ids(finding) if t is not None)
    non_mlb_team_ids_observed = _non_mlb_team_ids(all_team_ids_raw)

    differences.sort(key=lambda d: (
        str(d.get('classification')),
        str(d.get('event_key') or d.get('transaction_id') or ''),
        d.get('player_mlb_id') or 0,
    ))

    already_reflected_count = counts[TX_ALREADY_REFLECTED]
    non_player_count = counts[TX_NON_PLAYER]
    compound_reflected_count = counts[TX_COMPOUND_REFLECTED]
    non_pitcher_count = counts[TX_NON_PITCHER]
    detail_mismatch_count = counts[TX_TRANSACTION_DETAIL_MISMATCH]
    superseded_count = counts[TX_SUPERSEDED_TRANSACTION]
    current_state_aligned_count = counts[TX_CURRENT_STATE_ALIGNED]

    benign_sample_classes = (
        TX_ALREADY_REFLECTED, TX_NON_PLAYER, TX_COMPOUND_REFLECTED, TX_NON_PITCHER,
        TX_TRANSACTION_DETAIL_MISMATCH, TX_SUPERSEDED_TRANSACTION, TX_CURRENT_STATE_ALIGNED,
    )
    benign_records_suppressed = sum(
        max(0, counts[cls] - len(benign_samples[cls])) for cls in benign_sample_classes
    )

    lane['checked'] = {
        'source_transactions': lane.get('_source_transactions', 0),
        'source_events': lane.get('_source_events', 0),
        'meaningful_differences': len(differences),
        'actionable_differences': len(actionable),
        'review_required_differences': len(review),
        # Two independent axes (Correction 1).
        'transaction_record_actionable': len(ledger_findings),
        'public_bullpen_material': len(public_findings),
        # Back-compat alias for the pre-1.1 impact-plan reader.
        'actionable_player_transactions': len(actionable),
        'already_reflected': already_reflected_count,
        'non_player_transactions': non_player_count,
        'non_pitcher_transactions': non_pitcher_count,
        'bullpen_relevance_unresolved': counts[TX_BULLPEN_RELEVANCE_UNRESOLVED],
        'public_bullpen_effect_unreflected': counts[TX_PUBLIC_BULLPEN_EFFECT_UNREFLECTED],
        'transaction_detail_mismatches': detail_mismatch_count,
        'superseded_transactions': superseded_count,
        'current_state_aligned': current_state_aligned_count,
        'chronology_unresolved': counts[TX_CHRONOLOGY_UNRESOLVED],
        'compound_events_reflected': compound_reflected_count,
        'compound_new': counts[TX_COMPOUND_NEW],
        'compound_review_required': counts[TX_COMPOUND_REVIEW],
        'stored_conflicts': counts[TX_STORED_CONFLICT],
        'unresolved_identity': counts[TX_UNRESOLVED_IDENTITY],
        'invalid_shape': counts[TX_INVALID_SHAPE],
    }
    lane['differences'] = differences
    lane['informational_counts'] = {
        'already_reflected_count': already_reflected_count,
        'non_player_count': non_player_count,
        'non_pitcher_count': non_pitcher_count,
        'transaction_detail_mismatch_count': detail_mismatch_count,
        'superseded_transaction_count': superseded_count,
        'current_state_aligned_count': current_state_aligned_count,
        'compound_events_reflected_count': compound_reflected_count,
    }
    lane['suppressed_counts'] = {'benign_records_suppressed': benign_records_suppressed}
    lane['informational_samples'] = {
        cls: benign_samples[cls] for cls in benign_sample_classes if benign_samples[cls]
    }
    # PUBLIC surface (subset of roster authority).
    lane['affected_team_ids'] = _mlb_team_ids(public_team_ids_raw)
    lane['affected_pitcher_ids'] = sorted(public_pitcher_ids)
    lane['affected_pitcher_mlb_ids'] = sorted(public_pitcher_mlb_ids)
    lane['related_non_mlb_team_ids'] = non_mlb_team_ids_observed
    # LEDGER surface.
    lane['transaction_ledger'] = {
        'ingest_transaction_event_keys': sorted(ingest_event_keys),
        'reconcile_transaction_event_keys': sorted(reconcile_event_keys),
        'transaction_participant_mlb_ids': sorted(ledger_participant_mlb_ids),
        'transaction_related_mlb_team_ids': _mlb_team_ids(ledger_team_ids_raw),
        'transaction_related_non_mlb_team_ids': _non_mlb_team_ids(ledger_team_ids_raw),
        'record_actionable_count': len(ledger_findings),
    }


def _apply_role_gate(record, role_evidence):
    """Attach role evidence and, when the participant is not a proven pitcher,
    downgrade a would-be-actionable finding: proven non-pitcher → informational,
    unresolved role → review-required. Returns True when the finding remains
    bullpen-relevant (proven pitcher / two-way) and may keep its classification."""
    record.update({
        'bullpen_relevance': role_evidence.get('bullpen_relevance'),
        'role_verification_status': role_evidence.get('role_verification_status'),
        'role_evidence_source': role_evidence.get('role_evidence_source'),
        'official_position_code': role_evidence.get('official_position_code'),
        'official_position_abbreviation': role_evidence.get('official_position_abbreviation'),
        'official_position_type': role_evidence.get('official_position_type'),
    })
    relevance = role_evidence.get('bullpen_relevance')
    if relevance in BULLPEN_RELEVANT_ROLES:
        return True
    if relevance == ROLE_PROVEN_NON_PITCHER:
        record['classification'] = TX_NON_PITCHER
        record['severity'] = None
        record['reason'] = (
            'transaction participant is a proven non-pitcher; not bullpen-relevant '
            'and never materially actionable for the bullpen product'
        )
    else:
        record['classification'] = TX_BULLPEN_RELEVANCE_UNRESOLVED
        record['severity'] = SEVERITY_REVIEW
        record['reason'] = (
            'transaction participant role could not be verified from official MLB '
            'position evidence; not assumed to be a pitcher and never materially '
            'actionable until resolved'
        )
    return False


def _reconcile_single_player_event(
    component, existing, event_key, team_map, evidence_source, check_timestamp_iso,
    role_resolver, player_events, roster_current_state,
):
    """Classify a single-player transaction event with deterministic precedence:
    no stored evidence → genuine governed-fact conflict → exact-state/membership
    resolution → already reflected. Bullpen relevance is proven before any
    actionable classification; membership materiality uses the roster lane's
    current-state authority."""
    values = component['values']
    record = _lane2_base_record(
        component['transaction'], team_map, evidence_source, check_timestamp_iso,
        classification=TX_ALREADY_REFLECTED,
    )
    record.update({
        'event_key': event_key,
        'transaction_key': event_key,
        'normalized_category': values.get('normalized_category'),
        'stored_pitcher_id': values.get('pitcher_id'),
        'transaction_state_alignment': component['transaction_state_alignment'],
        'effect_direction': component['effect_direction'],
        'component_count': 1,
        'stored_transaction_row_id': existing.id if existing is not None else None,
    })

    # Exact stored-state alignment is misaligned only when a same-day snapshot
    # existed and disagreed with the transaction's team.
    state_misaligned = (
        component['transaction_state_alignment'] == transactions_service.ALIGNMENT_MISALIGNED
    )

    if existing is None:
        role_evidence = role_resolver.resolve(
            mlb_id=component['player_mlb_id'],
            stored_pitcher_id=component['pitcher_id'],
            transaction=component['transaction'],
        )
        record['classification'] = TX_ACTIONABLE_NOT_STORED
        record['severity'] = SEVERITY_ACTIONABLE
        _apply_role_gate(record, role_evidence)
        return record

    differing = [
        field for field in _TX_SOURCE_FACT_FIELDS
        if getattr(existing, field) != values.get(field)
    ]
    if differing:
        role_evidence = role_resolver.resolve(
            mlb_id=component['player_mlb_id'],
            stored_pitcher_id=component['pitcher_id'],
            transaction=component['transaction'],
        )
        record['classification'] = TX_STORED_CONFLICT
        record['severity'] = SEVERITY_ACTIONABLE
        record['conflicting_fields'] = differing
        _apply_role_gate(record, role_evidence)
        return record

    if state_misaligned:
        # Stored, governed facts match, but the exact stored roster effect differs
        # from the transaction. Whether that is materially actionable depends on
        # bullpen relevance, chronology, and CURRENT public membership — resolved
        # against the roster lane's current-state authority (Corrections 4/5/6/7).
        role_evidence = role_resolver.resolve(
            mlb_id=component['player_mlb_id'],
            stored_pitcher_id=component['pitcher_id'],
            transaction=component['transaction'],
        )
        if not _apply_role_gate(record, role_evidence):
            return record  # non-pitcher (informational) or unresolved (review)
        _resolve_single_membership(record, component, player_events, roster_current_state)
        return record

    record['classification'] = TX_ALREADY_REFLECTED
    record['severity'] = None
    return record


def _chronology_for_player(component, player_events):
    """Resolve where ``component`` sits in the player's roster-affecting sequence.

    Returns (chronology_status, latest_event_key, superseded_by_event_key). Uses
    only stable, present source ordering signals; when ordering is ambiguous it
    returns ``unresolved`` rather than overstating supersession."""
    mlb_id = component['player_mlb_id']
    affecting = [
        c for c in player_events.get(mlb_id, [])
        if c['normalized_category'] in _TX_ROSTER_AFFECTING_CATEGORIES
    ]
    if len(affecting) <= 1:
        return CHRONOLOGY_LATEST, component['event_key'], None

    def _date_key(c):
        # Only real time signals order transactions; the transaction id is NOT a
        # chronology signal, so it is never used to disambiguate same-date events.
        v = c['values']
        return (_iso_date(v.get('transaction_date')) or '', _iso_date(v.get('effective_date')) or '')

    latest_date_key = max(_date_key(c) for c in affecting)
    latest_components = [c for c in affecting if _date_key(c) == latest_date_key]
    latest_key = sorted(str(c['event_key']) for c in latest_components)[-1]
    directions = {
        c['effect_direction'] for c in latest_components if c['effect_direction'] != EFFECT_NONE
    }
    if len(directions) > 1:
        # The latest-dated roster-affecting events disagree on direction and the
        # source gives no finer ordering — we cannot tell which is current.
        return CHRONOLOGY_UNRESOLVED, latest_key, None
    if _date_key(component) == latest_date_key:
        return CHRONOLOGY_LATEST, latest_key, None
    return CHRONOLOGY_SUPERSEDED, latest_key, latest_key


def _resolve_single_membership(record, component, player_events, roster_current_state):
    """Cross-lane public-membership resolution for a proven-pitcher transaction
    whose exact stored state is misaligned (Corrections 4/5/6/7). Uses roster-lane
    current-state authority; never claims a material mismatch when the roster lane
    proves current public membership is already correct."""
    # A transaction type that cannot establish a current active-bullpen change
    # (organization / ledger-only / unknown) is never public-material, even when
    # its exact stored detail differs (Correction 3).
    scope = classify_transaction_public_effect(
        record.get('transaction_type_code'), component['normalized_category'],
    )
    if not scope['may_change_active_mlb_membership']:
        record['classification'] = TX_TRANSACTION_DETAIL_MISMATCH
        record['severity'] = None
        record['public_bullpen_membership_alignment'] = MEMBERSHIP_UNKNOWN
        record['reason'] = (
            'transaction type cannot establish a current active-bullpen change; '
            'exact stored detail differs only'
        )
        return

    chronology_status, latest_key, superseded_by = _chronology_for_player(component, player_events)
    record['chronology_status'] = chronology_status
    record['latest_applicable_event_key'] = latest_key
    record['superseded_by_event_key'] = superseded_by

    if chronology_status == CHRONOLOGY_UNRESOLVED:
        record['classification'] = TX_CHRONOLOGY_UNRESOLVED
        record['severity'] = SEVERITY_REVIEW
        record['reason'] = (
            'the order of this player\'s roster-affecting transactions could not be '
            'resolved from available source timestamps; current bullpen effect is '
            'not asserted'
        )
        return

    if chronology_status == CHRONOLOGY_SUPERSEDED:
        record['classification'] = TX_SUPERSEDED_TRANSACTION
        record['severity'] = None
        record['reason'] = (
            'this roster-affecting transaction was superseded by a later applicable '
            'transaction for the same player; its historical effect is not currently '
            'unreflected'
        )
        return

    # This is the latest applicable roster-affecting transaction. Compare current
    # official active-bullpen membership (roster lane) against stored state.
    state = roster_current_state.get(component['player_mlb_id'])
    if not state or not state.get('verified') or state.get('official_active') is None:
        record['classification'] = TX_CHRONOLOGY_UNRESOLVED
        record['severity'] = SEVERITY_REVIEW
        record['chronology_status'] = CHRONOLOGY_UNRESOLVED
        record['current_official_active_state'] = None
        record['public_bullpen_membership_alignment'] = MEMBERSHIP_UNKNOWN
        record['reason'] = (
            'current official active-roster membership for this player was not '
            'verified this run; a material public-state mismatch is not asserted'
        )
        return

    official_active = bool(state.get('official_active'))
    stored_active = state.get('stored_active')
    record['current_official_active_state'] = official_active
    record['stored_active_state'] = stored_active
    expected_active = (
        True if component['effect_direction'] == EFFECT_ENTER
        else False if component['effect_direction'] == EFFECT_LEAVE
        else None
    )
    record['expected_active_after_transaction'] = expected_active

    # The latest applicable transaction should explain the current official state;
    # if it does not, something else moved the player — do not overclaim.
    if expected_active is not None and expected_active != official_active:
        record['classification'] = TX_CHRONOLOGY_UNRESOLVED
        record['severity'] = SEVERITY_REVIEW
        record['chronology_status'] = CHRONOLOGY_UNRESOLVED
        record['public_bullpen_membership_alignment'] = MEMBERSHIP_UNKNOWN
        record['reason'] = (
            'the latest applicable transaction does not match current official '
            'active-roster evidence; current bullpen effect is not asserted'
        )
        return

    if stored_active is not None and official_active != bool(stored_active):
        # Current official active-bullpen membership disagrees with stored state
        # for a proven pitcher — a genuine, materially actionable public mismatch.
        record['classification'] = TX_PUBLIC_BULLPEN_EFFECT_UNREFLECTED
        record['severity'] = SEVERITY_ACTIONABLE
        record['public_bullpen_membership_alignment'] = MEMBERSHIP_MISALIGNED
        record['bullpen_population_effect'] = EFFECT_ENTER if official_active else EFFECT_LEAVE
        record['reason'] = (
            'official active-bullpen membership for this proven pitcher differs '
            'from stored BaseballOS state; the transaction effect is not reflected'
        )
        return

    # Current public bullpen membership is already correct. The exact stored
    # detail (e.g. minor-league affiliate destination) may still differ, but that
    # is not a material public-state change for a bullpen product.
    record['public_bullpen_membership_alignment'] = MEMBERSHIP_ALIGNED
    if _state_misaligned_detail(component):
        record['classification'] = TX_TRANSACTION_DETAIL_MISMATCH
        record['reason'] = (
            'exact stored transaction detail differs (e.g. minor-league affiliate '
            'destination) but current public active-bullpen membership is correct; '
            'not materially actionable'
        )
    else:
        record['classification'] = TX_CURRENT_STATE_ALIGNED
        record['reason'] = (
            'the transaction effect is already reflected in current public '
            'active-bullpen membership'
        )
    record['severity'] = None


def _state_misaligned_detail(component):
    return component['transaction_state_alignment'] == transactions_service.ALIGNMENT_MISALIGNED


def _reconcile_compound_event(
    components, existing, event_key, non_player_count, team_map,
    evidence_source, check_timestamp_iso, role_resolver,
):
    """Classify a compound event (multiple player components sharing one MLB
    transaction id). Produces at most one event-level finding, gated by bullpen
    relevance across its components."""
    ordered = sorted(components, key=lambda c: c['player_mlb_id'] or 0)
    event_values = components[0]['values']
    player_mlb_ids = sorted({c['player_mlb_id'] for c in components if c['player_mlb_id'] is not None})
    from_team_ids = sorted({c['from_team_id'] for c in components if c['from_team_id'] is not None})
    to_team_ids = sorted({c['to_team_id'] for c in components if c['to_team_id'] is not None})

    # Resolve role for each component (MLB id only).
    component_summary = []
    bullpen_relevant_mlb_ids = []
    bullpen_relevant_pitcher_ids = []
    bullpen_relevant_team_ids = set()
    any_relevant = False
    any_unresolved = False
    for c in ordered:
        role_evidence = role_resolver.resolve(
            mlb_id=c['player_mlb_id'],
            stored_pitcher_id=c['pitcher_id'],
            transaction=c['transaction'],
        )
        relevance = role_evidence.get('bullpen_relevance')
        component_summary.append({
            'player_mlb_id': c['player_mlb_id'],
            'from_team_id': c['from_team_id'],
            'to_team_id': c['to_team_id'],
            'normalized_category': c['normalized_category'],
            'stored_pitcher_id': c['pitcher_id'],
            'bullpen_relevance': relevance,
            'role_verification_status': role_evidence.get('role_verification_status'),
        })
        if relevance in BULLPEN_RELEVANT_ROLES:
            any_relevant = True
            if c['player_mlb_id'] is not None:
                bullpen_relevant_mlb_ids.append(c['player_mlb_id'])
            if c['pitcher_id'] is not None:
                bullpen_relevant_pitcher_ids.append(c['pitcher_id'])
            for team_id in (c['from_team_id'], c['to_team_id']):
                if team_id is not None:
                    bullpen_relevant_team_ids.add(team_id)
        elif relevance == ROLE_UNRESOLVED:
            any_unresolved = True

    finding = {
        'event_key': event_key,
        'transaction_id': _string_or_none(components[0]['transaction'].get('transaction_id')),
        'transaction_date': _string_or_none(components[0]['transaction'].get('transaction_date')),
        'transaction_type_code': event_values.get('transaction_type_code'),
        'normalized_category': event_values.get('normalized_category'),
        'component_count': len(components),
        'player_component_count': len(components),
        'non_player_component_count': non_player_count,
        'player_mlb_ids': player_mlb_ids,
        'from_team_ids': from_team_ids,
        'to_team_ids': to_team_ids,
        'component_summary': component_summary,
        'bullpen_relevant_mlb_ids': sorted(bullpen_relevant_mlb_ids),
        'bullpen_relevant_pitcher_ids': sorted(bullpen_relevant_pitcher_ids),
        'bullpen_relevant_team_ids': sorted(bullpen_relevant_team_ids),
        'stored_transaction_row_id': existing.id if existing is not None else None,
        'evidence_source': evidence_source,
        'check_timestamp': check_timestamp_iso,
    }

    def _gate_compound(default_class):
        if any_relevant:
            return default_class, SEVERITY_ACTIONABLE
        if any_unresolved:
            finding['reason'] = (
                'compound transaction role could not be verified for any component; '
                'not assumed bullpen-relevant'
            )
            return TX_BULLPEN_RELEVANCE_UNRESOLVED, SEVERITY_REVIEW
        finding['reason'] = (
            'compound transaction involves no proven pitcher or two-way player; '
            'not bullpen-relevant'
        )
        return TX_NON_PITCHER, None

    if existing is None:
        cls, severity = _gate_compound(TX_COMPOUND_NEW)
        finding['classification'] = cls
        finding['severity'] = severity
        if cls == TX_COMPOUND_NEW:
            finding['reason'] = (
                'compound transaction event with a proven bullpen-relevant player '
                'component is not stored; a future write phase would ingest the event'
            )
        return finding

    event_conflict_fields = [
        field for field in _TX_EVENT_LEVEL_FIELDS
        if getattr(existing, field) != event_values.get(field)
    ]
    if event_conflict_fields:
        cls, severity = _gate_compound(TX_STORED_CONFLICT)
        finding['classification'] = cls
        finding['severity'] = severity
        finding['conflicting_fields'] = event_conflict_fields
        if cls == TX_STORED_CONFLICT:
            finding['reason'] = 'compound transaction event-level facts conflict with the stored row'
        return finding

    stored_player_in_components = existing.player_mlb_id in set(player_mlb_ids)
    if stored_player_in_components:
        finding['classification'] = TX_COMPOUND_REFLECTED
        finding['severity'] = None
        return finding

    finding['classification'] = TX_COMPOUND_REVIEW
    finding['severity'] = SEVERITY_REVIEW
    finding['reason'] = (
        'compound transaction event is represented by one stored row, but the '
        'PlayerTransaction schema stores a single row per MLB transaction id, so '
        'per-component equivalence cannot be proven; human review required '
        '(this audit makes no migration or schema change)'
    )
    return finding


def _finding_team_ids(finding):
    ids = [finding.get('from_team_id'), finding.get('to_team_id')]
    ids.extend(finding.get('from_team_ids') or [])
    ids.extend(finding.get('to_team_ids') or [])
    return ids


def _finding_bullpen_team_ids(finding):
    """Team ids that may enter public impact — from bullpen-relevant evidence
    only (MLB scoping is applied separately)."""
    if finding.get('component_summary'):
        return list(finding.get('bullpen_relevant_team_ids') or [])
    if finding.get('bullpen_relevance') in BULLPEN_RELEVANT_ROLES:
        return [t for t in (finding.get('from_team_id'), finding.get('to_team_id')) if t is not None]
    return []


def _finding_bullpen_pitcher_ids(finding):
    if finding.get('component_summary'):
        return list(finding.get('bullpen_relevant_pitcher_ids') or [])
    if finding.get('bullpen_relevance') in BULLPEN_RELEVANT_ROLES \
            and finding.get('stored_pitcher_id') is not None:
        return [finding['stored_pitcher_id']]
    return []


def _finding_bullpen_mlb_ids(finding):
    if finding.get('component_summary'):
        return list(finding.get('bullpen_relevant_mlb_ids') or [])
    if finding.get('bullpen_relevance') in BULLPEN_RELEVANT_ROLES \
            and finding.get('player_mlb_id') is not None:
        return [finding['player_mlb_id']]
    return []


def _lane2_base_record(transaction, team_map, evidence_source, check_timestamp_iso, *, classification):
    from_team_id = _int_or_none(transaction.get('from_team_id'))
    to_team_id = _int_or_none(transaction.get('to_team_id'))
    return {
        'classification': classification,
        'transaction_id': _string_or_none(transaction.get('transaction_id')),
        'player_mlb_id': _int_or_none(transaction.get('player_mlb_id')),
        'player_name': _string_or_none(transaction.get('player_full_name')),
        'transaction_date': _string_or_none(transaction.get('transaction_date')),
        'transaction_type_code': _string_or_none(transaction.get('transaction_type_code')),
        'from_team_id': from_team_id,
        'from_team_abbreviation': _abbr(team_map, from_team_id),
        'to_team_id': to_team_id,
        'to_team_abbreviation': _abbr(team_map, to_team_id),
        'evidence_source': evidence_source,
        'check_timestamp': check_timestamp_iso,
    }


# ── Lane 3: schedule + game finality ────────────────────────────────────────

def reconcile_schedule_finality(
    *,
    client,
    team_map,
    check_timestamp_iso,
    product_date,
    lookback_days=DEFAULT_SCHEDULE_LOOKBACK_DAYS,
):
    """Compare official schedule/finality for the current and adjacent slate
    dates against stored ``scheduled_games`` evidence. Read-only."""
    # Imported lazily: the stored-finality authority lives in the large sync
    # module; keeping the import here avoids paying its load cost unless the
    # schedule lane actually runs.
    from services.sync import SPLIT_FINALITY_FINAL, resolve_scheduled_game_finality

    window_dates = [
        product_date - timedelta(days=offset)
        for offset in range(lookback_days, -1, -1)
    ]
    start_date, end_date = window_dates[0], window_dates[-1]

    fetch_error = None
    try:
        official_games = client.get_schedule(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
    except Exception as exc:  # noqa: BLE001 - source failure degrades this lane only
        fetch_error = str(exc)
        official_games = []
    official_games = official_games or []

    # Stored rows for the window, grouped by game_pk.
    stored_rows = (
        ScheduledGame.query
        .filter(ScheduledGame.game_date.in_(window_dates))
        .all()
    )
    stored_by_pk = defaultdict(list)
    stored_pks_in_window = set()
    for row in stored_rows:
        stored_by_pk[row.game_pk].append(row)
        stored_pks_in_window.add(row.game_pk)

    differences = []
    completed_game_pks = set()
    source_pks = set()
    doubleheaders_by_date_team = defaultdict(set)

    for game in official_games:
        game_pk = _g_pk(game)
        if game_pk is None:
            continue
        source_pks.add(game_pk)
        game_date = _g_date(game, product_date)
        decision = classify_status(game.get('status'), game_pk=game_pk)
        official_state = decision.status_state
        official_final = decision.final_status
        home_id = _g_team_id(game, 'home')
        away_id = _g_team_id(game, 'away')
        for team_id in (home_id, away_id):
            if team_id is not None:
                doubleheaders_by_date_team[(game_date, int(team_id))].add(game_pk)

        rows = stored_by_pk.get(game_pk)
        change_type = None
        would_require_targeted_postgame = False

        if not rows:
            change_type = GAME_NEWLY_DISCOVERED
            stored_state = None
            stored_finality = 'unknown'
            would_require_targeted_postgame = official_final
        else:
            stored_finality = resolve_scheduled_game_finality(game_pk)
            stored_final = stored_finality == SPLIT_FINALITY_FINAL
            stored_state = _representative_stored_state(rows)
            linkage_unresolved = scheduled_rows_have_unresolved_resumed_linkage(rows)

            if official_state == POSTPONED_STATUS_STATE and stored_state != POSTPONED_STATUS_STATE:
                change_type = GAME_POSTPONED
            elif stored_state == POSTPONED_STATUS_STATE and official_state != POSTPONED_STATUS_STATE:
                change_type = GAME_RESCHEDULED
            elif decision.reason == 'live_or_in_progress_status' and stored_state == SCHEDULED_STATUS_STATE:
                change_type = GAME_IN_PROGRESS
            elif official_final and not stored_final:
                change_type = GAME_NOW_FINAL
                would_require_targeted_postgame = True
            elif stored_final and not official_final:
                change_type = GAME_STORED_FINALITY_CONFLICT
            elif linkage_unresolved:
                change_type = GAME_RESCHEDULE_IDENTITY_ISSUE
            elif official_state != stored_state:
                change_type = GAME_SCHEDULE_STATUS_CHANGE

        if change_type is None:
            continue
        if change_type == GAME_NOW_FINAL:
            completed_game_pks.add(game_pk)

        differences.append(_lane3_difference(
            game_pk=game_pk,
            game_date=game_date,
            home_id=home_id,
            away_id=away_id,
            team_map=team_map,
            official_state=official_state,
            official_status_code=(game.get('status') or {}).get('statusCode'),
            stored_state=stored_state,
            stored_finality=stored_finality,
            change_type=change_type,
            would_require_targeted_postgame=would_require_targeted_postgame,
            check_timestamp_iso=check_timestamp_iso,
            doubleheader=_game_is_doubleheader(game),
        ))

    # Stored games in the window that the source no longer lists for that slate
    # (a likely move/postponement) — a delta worth surfacing.
    for game_pk in sorted(stored_pks_in_window - source_pks):
        rows = stored_by_pk.get(game_pk) or []
        game_date = rows[0].game_date if rows else None
        home_id = next((r.team_id for r in rows if r.home_away == 'home'), None)
        away_id = next((r.team_id for r in rows if r.home_away == 'away'), None)
        differences.append(_lane3_difference(
            game_pk=game_pk,
            game_date=game_date,
            home_id=home_id,
            away_id=away_id,
            team_map=team_map,
            official_state=None,
            official_status_code=None,
            stored_state=_representative_stored_state(rows),
            stored_finality=None,
            change_type=GAME_ABSENT_FROM_SOURCE,
            would_require_targeted_postgame=False,
            check_timestamp_iso=check_timestamp_iso,
            doubleheader=any((r.doubleheader or 'N') not in ('N', '') for r in rows),
        ))

    # Public team impact is scoped to the governed MLB clubs (Correction 3).
    affected_team_ids = _mlb_team_ids({
        team_id
        for d in differences
        for team_id in d.get('affected_team_ids', [])
        if team_id is not None
    })

    # Deterministic ordering.
    differences.sort(key=lambda d: (d.get('game_pk') or 0, str(d.get('change_type'))))

    # If the schedule feed could not be fetched, the source side is unverified;
    # stored games in the window still surface as absent-from-source deltas, but
    # we must not present the lane as a fully-checked "no change".
    limitations = []
    if fetch_error is not None:
        verification_status = LANE_FAILED
        limitations.append(
            f'schedule source fetch failed ({fetch_error}); official schedule '
            'state could not be verified this run'
        )
    else:
        verification_status = LANE_COMPLETE

    lane = {
        'verification_status': verification_status,
        'product_date': product_date.isoformat(),
        'slate_window': [d.isoformat() for d in window_dates],
        'checked': {
            'source_games': len(source_pks),
            'stored_games': len(stored_pks_in_window),
            'total_differences': len(differences),
            'newly_final_games': len(completed_game_pks),
        },
        'differences': differences,
        'completed_game_pks': sorted(completed_game_pks),
        'limitations': limitations,
        'affected_team_ids': affected_team_ids,
    }
    if fetch_error is not None:
        lane['fetch_error'] = fetch_error
    return lane


def _representative_stored_state(rows):
    """Collapse a game's per-team stored rows into one representative state.

    Final/postponed/suspended states are surfaced ahead of scheduled so a
    partially-updated pair of rows never hides a meaningful state.
    """
    states = {getattr(row, 'status_state', None) for row in (rows or [])}
    for state in (
        ScheduledGame.STATE_FINAL,
        POSTPONED_STATUS_STATE,
        ScheduledGame.STATE_SUSPENDED,
        OTHER_STATUS_STATE,
        SCHEDULED_STATUS_STATE,
    ):
        if state in states:
            return state
    return next(iter(states), None) if states else None


def _lane3_difference(
    *,
    game_pk,
    game_date,
    home_id,
    away_id,
    team_map,
    official_state,
    official_status_code,
    stored_state,
    stored_finality,
    change_type,
    would_require_targeted_postgame,
    check_timestamp_iso,
    doubleheader,
):
    affected = [t for t in (home_id, away_id) if t is not None]
    return {
        'game_pk': game_pk,
        'game_date': _iso_date(game_date),
        'home_team_id': home_id,
        'home_team_abbreviation': _abbr(team_map, home_id),
        'away_team_id': away_id,
        'away_team_abbreviation': _abbr(team_map, away_id),
        'official_status_state': official_state,
        'official_status_code': official_status_code,
        'stored_status_state': stored_state,
        'stored_finality': stored_finality,
        'change_type': change_type,
        'severity': _schedule_severity(change_type),
        'evidence_source': 'mlb_stats_api:schedule',
        'check_timestamp': check_timestamp_iso,
        'affected_team_ids': affected,
        'doubleheader': bool(doubleheader),
        'would_require_targeted_postgame': bool(would_require_targeted_postgame),
    }


# Schedule findings that describe a concrete slate/finality change a future
# write phase would act on are actionable; ambiguous/stored-conflict findings
# are review-required (changed, but not safely writable).
_SCHEDULE_REVIEW_CHANGE_TYPES = frozenset({
    GAME_STORED_FINALITY_CONFLICT,
    GAME_ABSENT_FROM_SOURCE,
    GAME_RESCHEDULE_IDENTITY_ISSUE,
})


def _schedule_severity(change_type):
    return SEVERITY_REVIEW if change_type in _SCHEDULE_REVIEW_CHANGE_TYPES else SEVERITY_ACTIONABLE


def _g_pk(game):
    value = (game or {}).get('gamePk')
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _g_team(game, side):
    return (((game or {}).get('teams') or {}).get(side) or {}).get('team') or {}


def _g_team_id(game, side):
    value = _g_team(game, side).get('id')
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _g_date(game, fallback):
    raw = (game or {}).get('officialDate') or str((game or {}).get('gameDate') or '')[:10]
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return fallback


def _game_is_doubleheader(game):
    value = (game or {}).get('doubleHeader')
    if value in (None, '', 'N'):
        return False
    return True


# ── Lane 4: dry-run impact plan ─────────────────────────────────────────────

def build_impact_plan(lane_roster, lane_transactions, lane_schedule):
    """Produce a dry-run impact plan from the detected source differences.

    Every value is a projection of what a FUTURE, separately-authorized write
    phase WOULD do. This audit itself does none of it.
    """
    roster = lane_roster or {}
    transactions = lane_transactions or {}
    schedule = lane_schedule or {}

    # ── PUBLIC bullpen-state plan (Correction 4/5/6/7) ───────────────────────
    # The ROSTER lane is the sole authority for current active-bullpen membership,
    # targeted recent-work acquisition, and public team-read recomputation. The
    # transaction lane's public-material findings are, by construction, a subset of
    # the roster lane's authority (a confirmed current change is always also a
    # roster finding), so unioning them adds no NEW public teams/pitchers — it only
    # deduplicates. Transaction-ledger-only findings never enter this plan.
    roster_checked = roster.get('checked') or {}
    roster_statuses_changed = bool(roster_checked.get('roster_status_differences'))
    team_assignments_changed = bool(roster_checked.get('team_assignment_differences'))

    tx_checked = transactions.get('checked') or {}
    public_membership_mismatches = int(tx_checked.get('public_bullpen_material', 0))

    completed_game_pks = list(schedule.get('completed_game_pks') or [])
    schedule_actionable_diffs = [
        d for d in (schedule.get('differences') or [])
        if d.get('severity') == SEVERITY_ACTIONABLE
    ]
    schedule_actionable = bool(schedule_actionable_diffs)
    schedule_affected_team_ids = {
        team_id
        for d in schedule_actionable_diffs
        for team_id in (d.get('affected_team_ids') or [])
        if team_id is not None
    }

    # Public teams/pitchers come from the roster lane (+ schedule) and the deduped
    # transaction public-material subset. All MLB-scoped.
    public_team_ids = _mlb_team_ids(
        set(roster.get('affected_team_ids') or [])
        | set(transactions.get('affected_team_ids') or [])
        | schedule_affected_team_ids
    )
    targeted_pitcher_ids = sorted(
        set(roster.get('targeted_recent_work_pitcher_ids') or [])
        | set(transactions.get('affected_pitcher_ids') or [])
    )
    targeted_pitcher_mlb_ids = sorted(
        set(roster.get('targeted_recent_work_mlb_ids') or [])
        | set(transactions.get('affected_pitcher_mlb_ids') or [])
    )

    public_bullpen_change_detected = bool(
        roster_statuses_changed
        or team_assignments_changed
        or public_membership_mismatches
    )
    # material = a proven current public-state change requires a future public
    # write/recompute. Transaction-ledger gaps NEVER make it true.
    material_change = bool(public_bullpen_change_detected or completed_game_pks)

    public_bullpen_state = {
        'roster_statuses': roster_statuses_changed,
        'team_assignments': team_assignments_changed,
        'targeted_pitcher_logs': targeted_pitcher_ids,
        'targeted_pitcher_mlb_ids': targeted_pitcher_mlb_ids,
        'affected_team_ids': public_team_ids,
        'recalculate_team_reads': public_team_ids,
        'completed_game_pks': completed_game_pks,
        'publish_snapshot': material_change,
        # Only a proven roster-population or schedule delta warms Tonight.
        'warm_tonight': bool(
            schedule_actionable
            or roster_statuses_changed
            or team_assignments_changed
            or public_membership_mismatches
        ),
        'recalculate_current_pen_era': bool(completed_game_pks),
        'recalculate_league_era_rank': bool(completed_game_pks),
    }

    # ── TRANSACTION-LEDGER plan (Correction 5) ───────────────────────────────
    # Records a future write phase would ingest / reconcile — completely separate
    # from public state, and never sets any public field above.
    tx_ledger = transactions.get('transaction_ledger') or {}
    transaction_ledger = {
        'ingest_transaction_event_keys': list(tx_ledger.get('ingest_transaction_event_keys') or []),
        'reconcile_transaction_event_keys': list(tx_ledger.get('reconcile_transaction_event_keys') or []),
        'transaction_participant_mlb_ids': list(tx_ledger.get('transaction_participant_mlb_ids') or []),
        'transaction_related_mlb_team_ids': list(tx_ledger.get('transaction_related_mlb_team_ids') or []),
        'transaction_related_non_mlb_team_ids': list(tx_ledger.get('transaction_related_non_mlb_team_ids') or []),
        'record_actionable_count': int(tx_ledger.get('record_actionable_count', 0)),
    }
    transaction_ledger_change_detected = transaction_ledger['record_actionable_count'] > 0

    # Backward-compatible flat would_refresh: derived ONLY from public_bullpen_state
    # (Correction 5) plus the two sub-plans. The flat `transactions` flag reflects a
    # public transaction-driven change (a confirmed membership mismatch), never a
    # ledger-only gap.
    would_refresh = {
        'roster_statuses': public_bullpen_state['roster_statuses'],
        'team_assignments': public_bullpen_state['team_assignments'],
        'transactions': bool(public_membership_mismatches),
        'targeted_pitcher_logs': public_bullpen_state['targeted_pitcher_logs'],
        'targeted_pitcher_mlb_ids': public_bullpen_state['targeted_pitcher_mlb_ids'],
        'completed_game_pks': public_bullpen_state['completed_game_pks'],
        'affected_team_ids': public_bullpen_state['affected_team_ids'],
        'recalculate_team_reads': public_bullpen_state['recalculate_team_reads'],
        'recalculate_current_pen_era': public_bullpen_state['recalculate_current_pen_era'],
        'recalculate_league_era_rank': public_bullpen_state['recalculate_league_era_rank'],
        'publish_snapshot': public_bullpen_state['publish_snapshot'],
        'warm_tonight': public_bullpen_state['warm_tonight'],
        # Split sub-plans (Correction 5).
        'public_bullpen_state': public_bullpen_state,
        'transaction_ledger': transaction_ledger,
    }

    return {
        'would_refresh': would_refresh,
        'material_change_detected': material_change,
        'public_bullpen_change_detected': public_bullpen_change_detected,
        'transaction_ledger_change_detected': transaction_ledger_change_detected,
    }


_INTERNAL_LANE_KEYS = ('_all_findings', '_source_transactions', '_source_events', 'current_state_index')


def _strip_internal_lane_keys(lane_results):
    for lane in (lane_results or {}).values():
        if isinstance(lane, dict):
            for key in _INTERNAL_LANE_KEYS:
                lane.pop(key, None)


# ── Orchestrator ────────────────────────────────────────────────────────────

def run_intraday_audit(
    *,
    source='manual',
    client=None,
    now=None,
    product_date=None,
    team_ids=None,
    roster_types=DEFAULT_ROSTER_TYPES,
    transaction_window_days=transactions_service.TRANSACTION_SYNC_WINDOW_DAYS,
    schedule_lookback_days=DEFAULT_SCHEDULE_LOOKBACK_DAYS,
    lanes=ALL_LANES,
    use_writer_lock=True,
    max_role_lookups=DEFAULT_MAX_ROLE_LOOKUPS,
):
    """Run the audit-only intraday reconciliation and return a structured,
    versioned artifact. This function never writes canonical baseball data,
    never publishes a snapshot, never recalculates fatigue, never generates
    stories, and never warms any public cache. It must be run inside a Flask app
    context.

    To guarantee it can never overlap a public sync writer (daily / postgame /
    backfill / another intraday audit), it acquires the SAME public sync advisory
    lock — read-only, without creating or mutating any ``SyncRun`` row — before
    any source acquisition, and releases it in a ``finally``. If the lock is
    already held it returns an explicit ``skipped`` result and does no work.
    """
    client = client or mlb_client
    lanes = tuple(lanes or ALL_LANES)
    check_timestamp = utc_now_naive()
    check_timestamp_iso = to_utc_iso(check_timestamp)
    resolved_product_date = product_date or product_current_date(now)

    # Reset the MLB client metrics up front so the artifact — including a skipped
    # result — reports only this audit's source-read pressure. On a skip this
    # stays at zero, proving no source acquisition occurred.
    try:
        client.metrics.reset()
    except AttributeError:
        pass

    # Acquire the public sync writer advisory lock before ANY source acquisition.
    guard = None
    if use_writer_lock:
        try:
            guard = sync_metadata.acquire_public_sync_read_lock(source=source)
        except sync_metadata.SyncWriterConflict as conflict:
            logger.info(
                'intraday audit skipped: a public sync writer is active (%s) — '
                'no source acquisition and no writes performed',
                conflict.reason,
            )
            return _skipped_artifact(
                client=client,
                source=source,
                product_date=resolved_product_date,
                lanes=lanes,
                check_timestamp_iso=check_timestamp_iso,
                conflict=conflict,
            )

    try:
        logger.info(
            'intraday audit starting (source=%s product_date=%s lanes=%s) — '
            'audit-only, holding the public sync advisory lock, no writes',
            source, resolved_product_date.isoformat(), ','.join(lanes),
        )

        team_map = _build_team_identity_map(client)
        lane_results = {}
        # One shared, budgeted role resolver per run — dedups and caches /people
        # lookups across the transaction lane (Correction 2).
        role_resolver = _RoleResolver(client, max_lookups=max_role_lookups)

        if LANE_ROSTER_ASSIGNMENT in lanes:
            logger.info('intraday audit: lane 1 — active roster + team assignment check')
            lane_results[LANE_ROSTER_ASSIGNMENT] = reconcile_active_rosters_and_assignments(
                client=client,
                team_map=team_map,
                check_timestamp_iso=check_timestamp_iso,
                team_ids=team_ids,
                roster_types=roster_types,
            )

        if LANE_TRANSACTIONS in lanes:
            logger.info('intraday audit: lane 2 — transaction check')
            # Cross-lane authority: the roster lane's current active-bullpen
            # membership index resolves whether a transaction effect is genuinely
            # unreflected in current public state (Correction 7).
            roster_current_state = (
                (lane_results.get(LANE_ROSTER_ASSIGNMENT) or {}).get('current_state_index') or {}
            )
            # Let the role resolver reuse the roster lane's evidence (Correction 9).
            role_resolver._roster_current_state = roster_current_state
            lane_results[LANE_TRANSACTIONS] = reconcile_transactions(
                client=client,
                team_map=team_map,
                check_timestamp=check_timestamp,
                check_timestamp_iso=check_timestamp_iso,
                end_date=resolved_product_date,
                window_days=transaction_window_days,
                role_resolver=role_resolver,
                roster_current_state=roster_current_state,
            )

        if LANE_SCHEDULE_FINALITY in lanes:
            logger.info('intraday audit: lane 3 — schedule + game-finality check')
            lane_results[LANE_SCHEDULE_FINALITY] = reconcile_schedule_finality(
                client=client,
                team_map=team_map,
                check_timestamp_iso=check_timestamp_iso,
                product_date=resolved_product_date,
                lookback_days=schedule_lookback_days,
            )

        impact_plan = build_impact_plan(
            lane_results.get(LANE_ROSTER_ASSIGNMENT),
            lane_results.get(LANE_TRANSACTIONS),
            lane_results.get(LANE_SCHEDULE_FINALITY),
        )

        # Internal cross-lane working state (full finding inventory, current-state
        # authority index) is consumed above; drop it so the published artifact
        # stays compact and carries only serialized differences + bounded samples.
        _strip_internal_lane_keys(lane_results)

        try:
            api_metrics = client.metrics.snapshot()
        except AttributeError:
            api_metrics = {}

        # Defensive read-only guarantee: the audit must leave the ORM session
        # with no pending inserts/updates/deletes. If reuse of a read helper ever
        # dirties the session, discard it and record the violation.
        write_guard = _assert_no_pending_writes()

        artifact = _build_completed_artifact(
            source=source,
            product_date=resolved_product_date,
            lanes_run=lanes,
            lane_results=lane_results,
            impact_plan=impact_plan,
            check_timestamp_iso=check_timestamp_iso,
            api_metrics=api_metrics,
            write_guard=write_guard,
        )
        logger.info(
            'intraday audit complete: status=%s changed=%s differences=%d '
            '(no writes performed)',
            artifact['status'], artifact['changed'],
            artifact['summary']['total_meaningful_findings'],
        )
        return artifact
    finally:
        # The advisory lock is always released — on success, partial failure, or
        # any unexpected exception.
        if guard is not None:
            guard.release()


def _safety_block(write_guard=None):
    """The safety guarantees this audit certifies. These are structural facts of
    the audit-only design, not merely aspirational flags."""
    block = {
        'writes_performed': False,
        'canonical_writes': False,
        'snapshot_published': False,
        'snapshot_built': False,
        'fatigue_recalculated': False,
        'stories_generated': False,
        'public_cache_warmed': False,
        'tonight_warmed': False,
        'dead_letter_writes': False,
        'sync_run_created_or_mutated': False,
        'box_score_or_game_log_ingested': False,
    }
    if write_guard is not None:
        block['orm_pending_writes'] = write_guard
    return block


def _empty_public_bullpen_state():
    return {
        'roster_statuses': False,
        'team_assignments': False,
        'targeted_pitcher_logs': [],
        'targeted_pitcher_mlb_ids': [],
        'affected_team_ids': [],
        'recalculate_team_reads': [],
        'completed_game_pks': [],
        'publish_snapshot': False,
        'warm_tonight': False,
        'recalculate_current_pen_era': False,
        'recalculate_league_era_rank': False,
    }


def _empty_transaction_ledger():
    return {
        'ingest_transaction_event_keys': [],
        'reconcile_transaction_event_keys': [],
        'transaction_participant_mlb_ids': [],
        'transaction_related_mlb_team_ids': [],
        'transaction_related_non_mlb_team_ids': [],
        'record_actionable_count': 0,
    }


def _empty_would_refresh():
    return {
        'roster_statuses': False,
        'team_assignments': False,
        'transactions': False,
        'targeted_pitcher_logs': [],
        'targeted_pitcher_mlb_ids': [],
        'completed_game_pks': [],
        'affected_team_ids': [],
        'recalculate_team_reads': [],
        'recalculate_current_pen_era': False,
        'recalculate_league_era_rank': False,
        'publish_snapshot': False,
        'warm_tonight': False,
        'public_bullpen_state': _empty_public_bullpen_state(),
        'transaction_ledger': _empty_transaction_ledger(),
    }


def _empty_summary():
    """Canonical zero-work summary for skipped / bootstrap-failure artifacts.
    Carries the same explicitly-scoped count names as a completed artifact so a
    consumer can read them uniformly regardless of status (Correction 1)."""
    return {
        'records_checked': 0,
        'total_meaningful_findings': 0,
        'total_actionable_findings': 0,
        'review_required_findings': 0,
        'unresolved_findings': 0,
        'transaction_record_actionable_count': 0,
        'transaction_ledger_only_findings': 0,
        'transaction_public_bullpen_material_count': 0,
        'transaction_ledger_change_detected': False,
        'public_roster_change_count': 0,
        'schedule_public_change_count': 0,
        'public_bullpen_change_count': 0,
        'public_bullpen_change_detected': False,
        'material_change_detected': False,
        'affected_team_ids': [],
    }


def _base_artifact_fields(*, source, product_date, check_timestamp_iso, completed_iso, status, lanes_run):
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'mode': MODE,
        'phase': PHASE,
        'check_only': True,
        'audit_only': True,
        'status': status,
        'source': source,
        'product_date': product_date.isoformat(),
        'started_at': check_timestamp_iso,
        'completed_at': completed_iso,
        'check_timestamp': check_timestamp_iso,
        'lanes_run': list(lanes_run),
    }


def _derive_status(lane_results, lanes_run, write_guard_clean):
    if not write_guard_clean:
        return STATUS_FAILED
    statuses = [
        (lane_results.get(lane) or {}).get('verification_status', LANE_FAILED)
        for lane in lanes_run
    ]
    if not statuses or all(s == LANE_COMPLETE for s in statuses):
        return STATUS_SUCCESS
    if all(s == LANE_FAILED for s in statuses):
        return STATUS_FAILED
    return STATUS_PARTIAL


def _derive_summary_counts(lane_results, impact_plan):
    """Single derivation surface for every aggregate summary count (Corrections
    1/3/4). Each field has exactly one explicit scope and one source, so a
    downstream consumer never needs to know a count's provenance or inspect lane
    internals, and no two counts can silently diverge from one another or from the
    impact plan.

    Scopes:
      * total_meaningful_findings / total_actionable_findings /
        review_required_findings / unresolved_findings — ALL-lane finding tallies.
        A meaningful finding is any serialized difference (benign inventory is
        never serialized). This does not imply every finding affects the public
        bullpen.
      * transaction_record_actionable_count / transaction_ledger_only_findings /
        transaction_public_bullpen_material_count — the transaction-LEDGER axis,
        independent of public materiality.
      * public_roster_change_count / schedule_public_change_count — per-lane
        current-public-state change tallies.
      * public_bullpen_change_count — the deduplicated GLOBAL count of current
        public bullpen changes, using the SAME roster authority and cross-lane
        overlap rules as build_impact_plan: the roster lane owns current
        membership; a transaction public-material finding for a player the roster
        lane already proved is the same public change and is not counted twice;
        ledger-only records and completed-game/schedule findings never inflate it.
    """
    roster_lane = lane_results.get(LANE_ROSTER_ASSIGNMENT) or {}
    tx_lane = lane_results.get(LANE_TRANSACTIONS) or {}
    schedule_lane = lane_results.get(LANE_SCHEDULE_FINALITY) or {}
    roster_checked = roster_lane.get('checked') or {}
    tx_checked = tx_lane.get('checked') or {}

    all_diffs = [
        d
        for lane in ALL_LANES
        for d in ((lane_results.get(lane) or {}).get('differences') or [])
    ]
    total_meaningful_findings = len(all_diffs)
    total_actionable_findings = sum(
        1 for d in all_diffs if d.get('severity') == SEVERITY_ACTIONABLE
    )
    review_required_findings = sum(
        1 for d in all_diffs if d.get('severity') == SEVERITY_REVIEW
    )
    unresolved_findings = sum(1 for d in all_diffs if _is_unresolved_finding(d))

    # Transaction-LEDGER axis. transaction_ledger_only_findings is counted
    # precisely from the findings (ledger-actionable AND not public-material)
    # rather than by subtraction, so it stays correct even if a public-material
    # finding is not itself ledger-actionable.
    tx_diffs = tx_lane.get('differences') or []
    transaction_record_actionable_count = int(tx_checked.get('transaction_record_actionable', 0))
    transaction_public_bullpen_material_count = int(tx_checked.get('public_bullpen_material', 0))
    transaction_ledger_only_findings = sum(
        1
        for d in tx_diffs
        if d.get('transaction_record_actionable') and not d.get('public_bullpen_material')
    )

    # Per-lane current-public-state tallies.
    public_roster_change_count = (
        int(roster_checked.get('roster_status_differences', 0))
        + int(roster_checked.get('team_assignment_differences', 0))
    )
    schedule_public_change_count = sum(
        1
        for d in (schedule_lane.get('differences') or [])
        if d.get('severity') == SEVERITY_ACTIONABLE
    )

    # Deduplicated GLOBAL public bullpen-change count. The roster lane is the sole
    # authority for current membership; a transaction public-material finding for a
    # player the roster lane already proved is the SAME public change (matches
    # build_impact_plan's union-dedup of public players), so it is not added again.
    roster_public_mlb_ids = set(roster_lane.get('affected_pitcher_mlb_ids') or [])
    tx_public_mlb_ids = set(tx_lane.get('affected_pitcher_mlb_ids') or [])
    transaction_public_only = len(tx_public_mlb_ids - roster_public_mlb_ids)
    public_bullpen_change_count = public_roster_change_count + transaction_public_only

    return {
        'total_meaningful_findings': total_meaningful_findings,
        'total_actionable_findings': total_actionable_findings,
        'review_required_findings': review_required_findings,
        'unresolved_findings': unresolved_findings,
        'transaction_record_actionable_count': transaction_record_actionable_count,
        'transaction_ledger_only_findings': transaction_ledger_only_findings,
        'transaction_public_bullpen_material_count': transaction_public_bullpen_material_count,
        'public_roster_change_count': public_roster_change_count,
        'schedule_public_change_count': schedule_public_change_count,
        'public_bullpen_change_count': public_bullpen_change_count,
    }


def _summary_contract_invariants(summary, impact_plan):
    """Return the list of violated summary-arithmetic invariants (Correction 4),
    empty when the summary is internally consistent. Pure and side-effect free.
    Used by tests and as a defensive pre-return check; a violation signals a
    derivation bug, never a data condition, and never fails the audit."""
    impact_plan = impact_plan or {}
    tx_ledger = (impact_plan.get('would_refresh') or {}).get('transaction_ledger') or {}
    violations = []

    def check(name, condition):
        if not condition:
            violations.append(name)

    check(
        'transaction_record_actionable_count==transaction_ledger.record_actionable_count',
        summary['transaction_record_actionable_count'] == int(tx_ledger.get('record_actionable_count', 0)),
    )
    check(
        'transaction_ledger_only_findings<=transaction_record_actionable_count',
        summary['transaction_ledger_only_findings'] <= summary['transaction_record_actionable_count'],
    )
    check(
        'public_bullpen_change_detected==public_bullpen_change_count>0',
        bool(impact_plan.get('public_bullpen_change_detected'))
        == (summary['public_bullpen_change_count'] > 0),
    )
    check(
        'transaction_ledger_change_detected==transaction_record_actionable_count>0',
        bool(impact_plan.get('transaction_ledger_change_detected'))
        == (summary['transaction_record_actionable_count'] > 0),
    )
    check(
        'total_actionable_findings>=public_bullpen_change_count',
        summary['total_actionable_findings'] >= summary['public_bullpen_change_count'],
    )
    check(
        'total_meaningful_findings>=total_actionable_findings',
        summary['total_meaningful_findings'] >= summary['total_actionable_findings'],
    )
    return violations


def _build_completed_artifact(
    *,
    source,
    product_date,
    lanes_run,
    lane_results,
    impact_plan,
    check_timestamp_iso,
    api_metrics,
    write_guard,
):
    would_refresh = impact_plan['would_refresh']
    status = _derive_status(lane_results, lanes_run, write_guard['clean'])

    # Every serialized difference is meaningful (benign inventory is not
    # serialized). All aggregate counts come from ONE derivation source
    # (_derive_summary_counts) so no two can silently diverge (Correction 1/4).
    counts = _derive_summary_counts(lane_results, impact_plan)

    changed_lanes = sorted(
        lane for lane in lanes_run
        if (lane_results.get(lane) or {}).get('differences')
    )
    affected_pitcher_ids = sorted({
        pid
        for lane in ALL_LANES
        for pid in ((lane_results.get(lane) or {}).get('affected_pitcher_ids') or [])
    })
    affected_pitcher_mlb_ids = sorted({
        mid
        for lane in ALL_LANES
        for mid in ((lane_results.get(lane) or {}).get('affected_pitcher_mlb_ids') or [])
    })
    limitations = []
    for lane in lanes_run:
        limitations.extend((lane_results.get(lane) or {}).get('limitations') or [])

    tx_lane = lane_results.get(LANE_TRANSACTIONS) or {}
    tx_checked = tx_lane.get('checked') or {}
    tx_informational = tx_lane.get('informational_counts') or {}
    informational_records = sum(v for v in tx_informational.values() if isinstance(v, int))
    benign_records_suppressed = (tx_lane.get('suppressed_counts') or {}).get(
        'benign_records_suppressed', 0
    )
    records_checked = (
        tx_checked.get('source_transactions', 0)
        + ((lane_results.get(LANE_ROSTER_ASSIGNMENT) or {}).get('checked') or {}).get('stored_pitchers', 0)
        + ((lane_results.get(LANE_SCHEDULE_FINALITY) or {}).get('checked') or {}).get('source_games', 0)
    )
    # A meaningful, actionable difference is a proven bullpen-relevant change.
    non_mlb_team_ids_observed = list(tx_lane.get('related_non_mlb_team_ids') or [])

    artifact = _base_artifact_fields(
        source=source,
        product_date=product_date,
        check_timestamp_iso=check_timestamp_iso,
        completed_iso=to_utc_iso(utc_now_naive()),
        status=status,
        lanes_run=lanes_run,
    )
    tx_ledger = tx_lane.get('transaction_ledger') or {}
    role_verification = tx_lane.get('role_verification') or {}
    public_bullpen_change_detected = bool(impact_plan.get('public_bullpen_change_detected'))
    transaction_ledger_change_detected = bool(impact_plan.get('transaction_ledger_change_detected'))

    summary = {
        'records_checked': records_checked,
        # ── Canonical, explicitly-scoped counts (Correction 1) ───────────────
        # All-lane finding tallies. A meaningful finding is any serialized
        # difference; being meaningful/actionable does NOT imply a public bullpen
        # change (that is public_bullpen_change_count below).
        'total_meaningful_findings': counts['total_meaningful_findings'],
        'total_actionable_findings': counts['total_actionable_findings'],
        'review_required_findings': counts['review_required_findings'],
        'unresolved_findings': counts['unresolved_findings'],
        # Transaction-LEDGER axis — future ledger reconciliation only, never
        # public materiality.
        'transaction_record_actionable_count': counts['transaction_record_actionable_count'],
        'transaction_ledger_only_findings': counts['transaction_ledger_only_findings'],
        'transaction_public_bullpen_material_count': counts['transaction_public_bullpen_material_count'],
        'transaction_ledger_change_detected': transaction_ledger_change_detected,
        # Public current-state axis — per-lane tallies plus the deduplicated
        # GLOBAL public bullpen-change count.
        'public_roster_change_count': counts['public_roster_change_count'],
        'schedule_public_change_count': counts['schedule_public_change_count'],
        'public_bullpen_change_count': counts['public_bullpen_change_count'],
        'public_bullpen_change_detected': public_bullpen_change_detected,
        # Retained, unambiguous informational buckets.
        'role_unresolved_findings': tx_checked.get('bullpen_relevance_unresolved', 0),
        'non_pitcher_transactions': tx_checked.get('non_pitcher_transactions', 0),
        'transaction_detail_mismatches': tx_checked.get('transaction_detail_mismatches', 0),
        'superseded_transactions': tx_checked.get('superseded_transactions', 0),
        'chronology_unresolved_findings': tx_checked.get('chronology_unresolved', 0),
        'role_lookups_used': role_verification.get('role_lookups_used', 0),
        'role_lookups_avoided': role_verification.get('role_lookups_avoided', 0),
        'informational_records': informational_records,
        'benign_records_suppressed': benign_records_suppressed,
        'material_change_detected': impact_plan['material_change_detected'],
        'affected_team_ids': would_refresh['affected_team_ids'],
        'mlb_teams_affected': would_refresh['affected_team_ids'],
        'mlb_public_teams_affected': would_refresh['affected_team_ids'],
        'transaction_related_mlb_teams': list(tx_ledger.get('transaction_related_mlb_team_ids') or []),
        'non_mlb_team_ids_observed': non_mlb_team_ids_observed,
    }
    # Defensive, non-fatal: the single derivation source guarantees these hold, so
    # a violation is a derivation bug, never a data condition. It is logged, never
    # raised, and never changes the audit status (Correction 4).
    invariant_violations = _summary_contract_invariants(summary, impact_plan)
    if invariant_violations:
        logger.warning(
            'intraday summary invariant(s) violated (derivation bug, not a data '
            'condition): %s', ', '.join(invariant_violations),
        )

    artifact.update({
        'changed': bool(counts['total_meaningful_findings']),
        'changed_lanes': changed_lanes,
        'affected_team_ids': would_refresh['affected_team_ids'],
        'affected_pitcher_ids': affected_pitcher_ids,
        'affected_pitcher_mlb_ids': affected_pitcher_mlb_ids,
        'lanes': lane_results,
        'would_refresh': would_refresh,
        'material_change_detected': impact_plan['material_change_detected'],
        # Independent change axes (Correction 10, retained).
        'public_bullpen_change_detected': public_bullpen_change_detected,
        'transaction_ledger_change_detected': transaction_ledger_change_detected,
        'limitations': limitations,
        'source_api': api_metrics,
        'safety': _safety_block(write_guard),
        'write_guard': write_guard,
        'summary': summary,
    })
    return artifact


def _is_unresolved_finding(difference):
    return (
        difference.get('classification') in (
            TX_UNRESOLVED_IDENTITY,
            TX_INVALID_SHAPE,
            TX_BULLPEN_RELEVANCE_UNRESOLVED,
            TX_CHRONOLOGY_UNRESOLVED,
        )
        or difference.get('change_type') == CHANGE_UNRESOLVED_SOURCE_IDENTITY
    )


def _skipped_artifact(*, client, source, product_date, lanes, check_timestamp_iso, conflict):
    """Explicit skipped result when a public sync writer already holds the lock.

    Proves no work occurred: no lanes, zero API calls, empty would-refresh, and
    a clean write guard. The audit exits cleanly (status skipped) rather than
    waiting or queueing.
    """
    reason_code = (
        REASON_PUBLIC_SYNC_WRITER_ACTIVE
        if conflict.reason == sync_metadata.SYNC_WRITER_ALREADY_RUNNING
        else REASON_PUBLIC_SYNC_LOCK_UNAVAILABLE
    )
    try:
        api_metrics = client.metrics.snapshot()
    except AttributeError:
        api_metrics = {'api_calls': 0, 'retries': 0, 'by_endpoint': {}}

    artifact = _base_artifact_fields(
        source=source,
        product_date=product_date,
        check_timestamp_iso=check_timestamp_iso,
        completed_iso=to_utc_iso(utc_now_naive()),
        status=STATUS_SKIPPED,
        lanes_run=lanes,
    )
    artifact.update({
        'reason_code': reason_code,
        'changed': False,
        'changed_lanes': [],
        'affected_team_ids': [],
        'affected_pitcher_ids': [],
        'affected_pitcher_mlb_ids': [],
        'lanes': {},
        'would_refresh': _empty_would_refresh(),
        'material_change_detected': False,
        'public_bullpen_change_detected': False,
        'transaction_ledger_change_detected': False,
        'limitations': [conflict.message],
        'source_api': api_metrics,
        'safety': _safety_block({'clean': True, 'pending_new': 0, 'pending_dirty': 0, 'pending_deleted': 0}),
        'write_guard': {'clean': True, 'pending_new': 0, 'pending_dirty': 0, 'pending_deleted': 0},
        'conflict': conflict.to_dict(),
        'summary': _empty_summary(),
    })
    return artifact


def build_bootstrap_failure_artifact(
    *,
    source,
    started_at_iso,
    completed_at_iso=None,
    reason_code=REASON_APPLICATION_BOOTSTRAP_FAILED,
    exception_class=None,
    lanes=ALL_LANES,
):
    """Versioned ``failed`` artifact for a failure that occurs before or during
    application startup — before the audit can acquire the lock or read any
    source.

    This is a pure dict builder: it needs no Flask app context and no database,
    so a caller whose ``create_app()`` raised can still emit a valid, contract-
    shaped result. It proves no work occurred (no lanes checked, zero API calls,
    empty would-refresh, clean write guard) and records only a **sanitized**
    limitation — the exception *class* name at most, never its message, a
    traceback, or any secret / connection string. Callers must write the raw
    diagnostic detail to stderr, not into this artifact.
    """
    lanes = tuple(lanes or ALL_LANES)
    completed_at_iso = completed_at_iso or started_at_iso
    detail = f' ({exception_class})' if exception_class else ''
    limitation = (
        f'Application bootstrap failed{detail} before the audit could start '
        f'({reason_code}); this is a bootstrap failure, not a partial source '
        'verification. No source acquisition, no advisory-lock acquisition, and '
        'no writes occurred. See stderr for the sanitized traceback.'
    )
    clean_guard = {'clean': True, 'pending_new': 0, 'pending_dirty': 0, 'pending_deleted': 0}
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'mode': MODE,
        'phase': PHASE,
        'check_only': True,
        'audit_only': True,
        'status': STATUS_FAILED,
        'reason_code': reason_code,
        'source': source,
        # Not established when the app cannot initialize — explicitly null.
        'product_date': None,
        'started_at': started_at_iso,
        'completed_at': completed_at_iso,
        'check_timestamp': started_at_iso,
        'lanes_run': list(lanes),
        'changed': False,
        'changed_lanes': [],
        'affected_team_ids': [],
        'affected_pitcher_ids': [],
        'affected_pitcher_mlb_ids': [],
        # Every lane is explicitly not-checked — never falsely successful.
        'lanes': {lane: {'verification_status': LANE_NOT_CHECKED} for lane in lanes},
        'would_refresh': _empty_would_refresh(),
        'material_change_detected': False,
        'public_bullpen_change_detected': False,
        'transaction_ledger_change_detected': False,
        'limitations': [limitation],
        # Source acquisition never began.
        'source_api': {'api_calls': 0, 'retries': 0, 'by_endpoint': {}},
        'safety': _safety_block(clean_guard),
        'write_guard': clean_guard,
        'summary': _empty_summary(),
    }


def _assert_no_pending_writes():
    """Verify the audit produced no pending ORM writes; roll back defensively.

    Returns a small report so the artifact can prove it stayed read-only. Any
    non-empty pending set is rolled back so nothing can ever be committed by a
    caller.
    """
    pending_new = list(db.session.new)
    pending_dirty = list(db.session.dirty)
    pending_deleted = list(db.session.deleted)
    clean = not (pending_new or pending_dirty or pending_deleted)
    if not clean:
        logger.error(
            'intraday audit detected unexpected pending ORM state (new=%d dirty=%d deleted=%d); '
            'rolling back to preserve audit-only guarantee',
            len(pending_new), len(pending_dirty), len(pending_deleted),
        )
        db.session.rollback()
    return {
        'clean': clean,
        'pending_new': len(pending_new),
        'pending_dirty': len(pending_dirty),
        'pending_deleted': len(pending_deleted),
    }
