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
# Fine-grained contract version. Bumped 1.0.0 -> 1.1.0 for the signal-quality
# correction: transaction `differences` now carries only meaningful findings
# (benign inventory is aggregated, not serialized), several summary buckets were
# added, and the default roster scope is active-only. The capability major
# identifier is unchanged and the workflow validator (capability/mode/
# check_only/status) still accepts the artifact, so this is a backward-
# compatible minor bump, not a breaking major change.
VERSION = '1.1.0'

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

# Lane 2 transaction classifications. Event-aware: single-player events use the
# player-level classes; compound events (multiple source components sharing one
# MLB transaction id) use the compound_* classes so one event never manufactures
# several per-component conflicts.
TX_NON_PLAYER = 'non_player_transaction'
TX_UNRESOLVED_IDENTITY = 'unresolved_identity'
TX_INVALID_SHAPE = 'invalid_shape'
TX_ACTIONABLE_NOT_STORED = 'actionable_not_stored'
TX_STORED_CONFLICT = 'stored_conflict'
TX_STATUS_EFFECT_UNREFLECTED = 'status_effect_unreflected'
TX_ALREADY_REFLECTED = 'already_reflected'
TX_COMPOUND_NEW = 'compound_transaction_new'
TX_COMPOUND_REVIEW = 'compound_transaction_review_required'
TX_COMPOUND_REFLECTED = 'compound_event_reflected'

# Which transaction classifications are meaningful (serialized into differences)
# and, of those, which imply an actionable future write.
TX_ACTIONABLE_CLASSES = frozenset({
    TX_ACTIONABLE_NOT_STORED,
    TX_STORED_CONFLICT,
    TX_STATUS_EFFECT_UNREFLECTED,
    TX_COMPOUND_NEW,
})
TX_REVIEW_CLASSES = frozenset({
    TX_UNRESOLVED_IDENTITY,
    TX_INVALID_SHAPE,
    TX_COMPOUND_REVIEW,
})
TX_MEANINGFUL_CLASSES = TX_ACTIONABLE_CLASSES | TX_REVIEW_CLASSES
# Benign / informational classes are counted but never serialized row-by-row.
TX_BENIGN_CLASSES = frozenset({
    TX_ALREADY_REFLECTED,
    TX_NON_PLAYER,
    TX_COMPOUND_REFLECTED,
})

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
    affected_team_ids = sorted({
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
):
    """Compare recent official transactions against stored transaction evidence.

    Event-aware and signal-selective. Source records are grouped by their stable
    MLB transaction-event id, so a compound event (several player components plus
    a non-player component sharing one transaction id) never manufactures one
    stored-conflict per component. Only meaningful findings — actionable or
    review-required — are serialized into ``differences``; benign inventory
    (already-reflected, non-player, reflected compound events) is counted and
    optionally sampled, never repeated row-by-row. Read-only: no insert, update,
    resolution, or dead-letter write.
    """
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

    counts = defaultdict(int)
    differences = []
    benign_samples = defaultdict(list)

    # ── Phase 1: classify each source record into a component with an event key.
    events = {}          # event_key -> list of player component dicts
    event_order = []     # first-seen order of event keys (deterministic)
    non_player_by_event = defaultdict(int)

    for transaction in source_transactions:
        if not isinstance(transaction, dict):
            counts[TX_INVALID_SHAPE] += 1
            differences.append({
                'classification': TX_INVALID_SHAPE,
                'severity': SEVERITY_REVIEW,
                'reason': 'transaction row is not an object',
                'evidence_source': evidence_source,
                'check_timestamp': check_timestamp_iso,
            })
            continue

        if transactions_service.is_non_player_transaction(transaction):
            counts[TX_NON_PLAYER] += 1
            tx_id = _string_or_none(transaction.get('transaction_id'))
            if tx_id is not None:
                non_player_by_event[f'statsapi:{tx_id}'] += 1
            if len(benign_samples[TX_NON_PLAYER]) < sample_limit:
                benign_samples[TX_NON_PLAYER].append(_lane2_base_record(
                    transaction, team_map, evidence_source, check_timestamp_iso,
                    classification=TX_NON_PLAYER,
                ))
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
            counts[classification] += 1
            record = _lane2_base_record(
                transaction, team_map, evidence_source, check_timestamp_iso,
                classification=classification,
            )
            record['severity'] = SEVERITY_REVIEW
            record['reason'] = detail.get('reason')
            differences.append(record)
            continue

        # A resolvable player component. Group by the shared event key.
        event_key = values['transaction_key']
        component = {
            'transaction': transaction,
            'values': values,
            'player_mlb_id': values.get('player_mlb_id'),
            'from_team_id': values.get('from_team_id'),
            'to_team_id': values.get('to_team_id'),
            'normalized_category': values.get('normalized_category'),
            'pitcher_id': values.get('pitcher_id'),
            'status_effect_unreflected': (
                values.get('roster_snapshot_alignment') == transactions_service.ALIGNMENT_MISALIGNED
            ),
        }
        if event_key not in events:
            events[event_key] = []
            event_order.append(event_key)
        events[event_key].append(component)

    # ── Phase 2: reconcile each event (single-player or compound).
    for event_key in event_order:
        components = events[event_key]
        existing = PlayerTransaction.query.filter_by(transaction_key=event_key).first()
        if len(components) == 1:
            finding = _reconcile_single_player_event(
                components[0], existing, event_key, team_map,
                evidence_source, check_timestamp_iso,
            )
        else:
            finding = _reconcile_compound_event(
                components, existing, event_key, non_player_by_event.get(event_key, 0),
                team_map, evidence_source, check_timestamp_iso,
            )
        classification = finding['classification']
        counts[classification] += 1
        if classification in TX_MEANINGFUL_CLASSES:
            differences.append(finding)
        elif len(benign_samples[classification]) < sample_limit:
            benign_samples[classification].append(finding)

    actionable = [d for d in differences if d.get('severity') == SEVERITY_ACTIONABLE]
    review = [d for d in differences if d.get('severity') == SEVERITY_REVIEW]

    # Affected identity sets are derived from ACTIONABLE findings only — benign
    # or review-required rows never add teams or pitchers to a write plan.
    affected_team_ids = sorted({
        team_id for d in actionable for team_id in _finding_team_ids(d) if team_id is not None
    })
    affected_pitcher_ids = sorted({
        pid for d in actionable for pid in _finding_pitcher_ids(d) if pid is not None
    })
    affected_pitcher_mlb_ids = sorted({
        mid for d in actionable for mid in _finding_player_mlb_ids(d) if mid is not None
    })

    # Deterministic ordering of meaningful findings.
    differences.sort(key=lambda d: (
        str(d.get('classification')),
        str(d.get('event_key') or d.get('transaction_id') or ''),
        d.get('player_mlb_id') or 0,
    ))

    already_reflected_count = counts[TX_ALREADY_REFLECTED]
    non_player_count = counts[TX_NON_PLAYER]
    compound_reflected_count = counts[TX_COMPOUND_REFLECTED]
    benign_records_suppressed = (
        max(0, already_reflected_count - len(benign_samples[TX_ALREADY_REFLECTED]))
        + max(0, non_player_count - len(benign_samples[TX_NON_PLAYER]))
        + max(0, compound_reflected_count - len(benign_samples[TX_COMPOUND_REFLECTED]))
    )

    limitations = []
    if fetch_error is not None:
        verification_status = LANE_FAILED
        limitations.append(
            f'transaction source fetch failed ({fetch_error}); the transaction '
            'lane could not be verified this run'
        )
    else:
        verification_status = LANE_COMPLETE

    lane = {
        'verification_status': verification_status,
        'window': {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'window_days': window_days,
        },
        'checked': {
            'source_transactions': len(source_transactions),
            'source_events': len(event_order),
            'meaningful_differences': len(differences),
            'actionable_differences': len(actionable),
            'review_required_differences': len(review),
            # Back-compat alias for the pre-1.1 impact-plan reader.
            'actionable_player_transactions': len(actionable),
            'already_reflected': already_reflected_count,
            'non_player_transactions': non_player_count,
            'compound_events_reflected': compound_reflected_count,
            'compound_new': counts[TX_COMPOUND_NEW],
            'compound_review_required': counts[TX_COMPOUND_REVIEW],
            'stored_conflicts': counts[TX_STORED_CONFLICT],
            'status_effect_unreflected': counts[TX_STATUS_EFFECT_UNREFLECTED],
            'unresolved_identity': counts[TX_UNRESOLVED_IDENTITY],
            'invalid_shape': counts[TX_INVALID_SHAPE],
        },
        'differences': differences,
        'informational_counts': {
            'already_reflected_count': already_reflected_count,
            'non_player_count': non_player_count,
            'compound_events_reflected_count': compound_reflected_count,
        },
        'suppressed_counts': {
            'benign_records_suppressed': benign_records_suppressed,
        },
        'informational_samples': {
            cls: benign_samples[cls]
            for cls in (TX_ALREADY_REFLECTED, TX_NON_PLAYER, TX_COMPOUND_REFLECTED)
            if benign_samples[cls]
        },
        'limitations': limitations,
        'affected_team_ids': affected_team_ids,
        'affected_pitcher_ids': affected_pitcher_ids,
        'affected_pitcher_mlb_ids': affected_pitcher_mlb_ids,
    }
    if fetch_error is not None:
        lane['fetch_error'] = fetch_error
    return lane


def _reconcile_single_player_event(
    component, existing, event_key, team_map, evidence_source, check_timestamp_iso,
):
    """Classify a single-player transaction event with deterministic precedence:
    no stored evidence → genuine source-fact conflict → status-effect unreflected
    → already reflected."""
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
        'roster_snapshot_alignment': values.get('roster_snapshot_alignment'),
        'status_effect_unreflected': component['status_effect_unreflected'],
        'component_count': 1,
        'stored_transaction_row_id': existing.id if existing is not None else None,
    })

    if existing is None:
        record['classification'] = TX_ACTIONABLE_NOT_STORED
        record['severity'] = SEVERITY_ACTIONABLE
        return record

    differing = [
        field for field in _TX_SOURCE_FACT_FIELDS
        if getattr(existing, field) != values.get(field)
    ]
    if differing:
        record['classification'] = TX_STORED_CONFLICT
        record['severity'] = SEVERITY_ACTIONABLE
        record['conflicting_fields'] = differing
        return record

    if component['status_effect_unreflected']:
        # Stored, source facts match, but the transaction's roster effect is not
        # reflected in current roster state — its own class, above already-reflected.
        record['classification'] = TX_STATUS_EFFECT_UNREFLECTED
        record['severity'] = SEVERITY_ACTIONABLE
        return record

    record['classification'] = TX_ALREADY_REFLECTED
    record['severity'] = None
    return record


def _reconcile_compound_event(
    components, existing, event_key, non_player_count, team_map,
    evidence_source, check_timestamp_iso,
):
    """Classify a compound event (multiple player components sharing one MLB
    transaction id). Produces at most one event-level finding — never one
    stored-conflict per component."""
    ordered = sorted(components, key=lambda c: c['player_mlb_id'] or 0)
    event_values = components[0]['values']
    player_mlb_ids = sorted({c['player_mlb_id'] for c in components if c['player_mlb_id'] is not None})
    from_team_ids = sorted({c['from_team_id'] for c in components if c['from_team_id'] is not None})
    to_team_ids = sorted({c['to_team_id'] for c in components if c['to_team_id'] is not None})
    any_unreflected = any(c['status_effect_unreflected'] for c in components)

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
        'component_summary': [{
            'player_mlb_id': c['player_mlb_id'],
            'from_team_id': c['from_team_id'],
            'to_team_id': c['to_team_id'],
            'normalized_category': c['normalized_category'],
            'stored_pitcher_id': c['pitcher_id'],
            'status_effect_unreflected': c['status_effect_unreflected'],
        } for c in ordered],
        'stored_transaction_row_id': existing.id if existing is not None else None,
        'evidence_source': evidence_source,
        'check_timestamp': check_timestamp_iso,
    }

    if existing is None:
        finding['classification'] = TX_COMPOUND_NEW
        finding['severity'] = SEVERITY_ACTIONABLE
        finding['reason'] = (
            'compound transaction event with multiple player components is not '
            'stored; a future write phase would need to ingest the event'
        )
        return finding

    # Compare only shared event-level facts — never per-component player fields.
    event_conflict_fields = [
        field for field in _TX_EVENT_LEVEL_FIELDS
        if getattr(existing, field) != event_values.get(field)
    ]
    if event_conflict_fields:
        finding['classification'] = TX_STORED_CONFLICT
        finding['severity'] = SEVERITY_ACTIONABLE
        finding['conflicting_fields'] = event_conflict_fields
        finding['reason'] = 'compound transaction event-level facts conflict with the stored row'
        return finding

    # The event is represented, but PlayerTransaction stores one row per MLB
    # transaction id, so per-component equivalence cannot be proven here.
    stored_player_in_components = existing.player_mlb_id in set(player_mlb_ids)
    if stored_player_in_components and not any_unreflected:
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


def _finding_pitcher_ids(finding):
    ids = []
    if finding.get('stored_pitcher_id') is not None:
        ids.append(finding['stored_pitcher_id'])
    for component in finding.get('component_summary') or []:
        if component.get('stored_pitcher_id') is not None:
            ids.append(component['stored_pitcher_id'])
    return ids


def _finding_player_mlb_ids(finding):
    ids = []
    if finding.get('player_mlb_id') is not None:
        ids.append(finding['player_mlb_id'])
    ids.extend(finding.get('player_mlb_ids') or [])
    return ids


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

    affected_team_ids = sorted({
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

    # Roster status/assignment change counts already exclude conflicting and
    # unresolved (review-required) findings.
    roster_checked = roster.get('checked') or {}
    roster_statuses_changed = bool(roster_checked.get('roster_status_differences'))
    team_assignments_changed = bool(roster_checked.get('team_assignment_differences'))

    # Transactions drive a write only through ACTIONABLE findings; benign
    # inventory and review-required findings never do.
    transactions_actionable = bool((transactions.get('checked') or {}).get('actionable_differences'))

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

    affected_team_ids = sorted(
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

    # A future authorized write / recompute is required only for actionable
    # findings (or newly final games). Review-required findings never plan a
    # write; benign inventory never plans anything.
    material_change = bool(
        roster_statuses_changed
        or team_assignments_changed
        or transactions_actionable
        or schedule_actionable
        or completed_game_pks
    )

    return {
        'would_refresh': {
            'roster_statuses': roster_statuses_changed,
            'team_assignments': team_assignments_changed,
            'transactions': transactions_actionable,
            'targeted_pitcher_logs': targeted_pitcher_ids,
            'targeted_pitcher_mlb_ids': targeted_pitcher_mlb_ids,
            'completed_game_pks': completed_game_pks,
            'affected_team_ids': affected_team_ids,
            'recalculate_team_reads': affected_team_ids,
            'recalculate_current_pen_era': bool(completed_game_pks),
            'recalculate_league_era_rank': bool(completed_game_pks),
            'publish_snapshot': material_change,
            # A transaction-only storage conflict never warms Tonight; only a
            # roster-population or schedule delta does.
            'warm_tonight': bool(schedule_actionable or roster_statuses_changed or team_assignments_changed),
        },
        'material_change_detected': material_change,
    }


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
            lane_results[LANE_TRANSACTIONS] = reconcile_transactions(
                client=client,
                team_map=team_map,
                check_timestamp=check_timestamp,
                check_timestamp_iso=check_timestamp_iso,
                end_date=resolved_product_date,
                window_days=transaction_window_days,
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
            artifact['status'], artifact['changed'], artifact['summary']['total_differences'],
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
    # serialized), so counts are honest by construction.
    all_diffs = [
        d
        for lane in ALL_LANES
        for d in ((lane_results.get(lane) or {}).get('differences') or [])
    ]
    total_differences = len(all_diffs)
    actionable_count = sum(1 for d in all_diffs if d.get('severity') == SEVERITY_ACTIONABLE)
    review_required_count = sum(1 for d in all_diffs if d.get('severity') == SEVERITY_REVIEW)
    unresolved_count = sum(1 for d in all_diffs if _is_unresolved_finding(d))

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
    tx_informational = tx_lane.get('informational_counts') or {}
    informational_records = sum(v for v in tx_informational.values() if isinstance(v, int))
    benign_records_suppressed = (tx_lane.get('suppressed_counts') or {}).get(
        'benign_records_suppressed', 0
    )
    records_checked = (
        (tx_lane.get('checked') or {}).get('source_transactions', 0)
        + ((lane_results.get(LANE_ROSTER_ASSIGNMENT) or {}).get('checked') or {}).get('stored_pitchers', 0)
        + ((lane_results.get(LANE_SCHEDULE_FINALITY) or {}).get('checked') or {}).get('source_games', 0)
    )

    artifact = _base_artifact_fields(
        source=source,
        product_date=product_date,
        check_timestamp_iso=check_timestamp_iso,
        completed_iso=to_utc_iso(utc_now_naive()),
        status=status,
        lanes_run=lanes_run,
    )
    artifact.update({
        'changed': bool(total_differences),
        'changed_lanes': changed_lanes,
        'affected_team_ids': would_refresh['affected_team_ids'],
        'affected_pitcher_ids': affected_pitcher_ids,
        'affected_pitcher_mlb_ids': affected_pitcher_mlb_ids,
        'lanes': lane_results,
        'would_refresh': would_refresh,
        'material_change_detected': impact_plan['material_change_detected'],
        'limitations': limitations,
        'source_api': api_metrics,
        'safety': _safety_block(write_guard),
        'write_guard': write_guard,
        'summary': {
            'total_differences': total_differences,
            'records_checked': records_checked,
            'actionable_differences': actionable_count,
            'review_required_findings': review_required_count,
            'unresolved_findings': unresolved_count,
            'informational_records': informational_records,
            'benign_records_suppressed': benign_records_suppressed,
            'material_change_detected': impact_plan['material_change_detected'],
            'affected_team_ids': would_refresh['affected_team_ids'],
        },
    })
    return artifact


def _is_unresolved_finding(difference):
    return (
        difference.get('classification') in (TX_UNRESOLVED_IDENTITY, TX_INVALID_SHAPE)
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
        'limitations': [conflict.message],
        'source_api': api_metrics,
        'safety': _safety_block({'clean': True, 'pending_new': 0, 'pending_dirty': 0, 'pending_deleted': 0}),
        'write_guard': {'clean': True, 'pending_new': 0, 'pending_dirty': 0, 'pending_deleted': 0},
        'conflict': conflict.to_dict(),
        'summary': {
            'total_differences': 0,
            'material_change_detected': False,
            'affected_team_ids': [],
        },
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
        'limitations': [limitation],
        # Source acquisition never began.
        'source_api': {'api_calls': 0, 'retries': 0, 'by_endpoint': {}},
        'safety': _safety_block(clean_guard),
        'write_guard': clean_guard,
        'summary': {
            'total_differences': 0,
            'material_change_detected': False,
            'affected_team_ids': [],
        },
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
