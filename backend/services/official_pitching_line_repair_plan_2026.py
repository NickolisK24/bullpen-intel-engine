"""Official pitching-line repair PLAN generator (2026) — READ ONLY.

The merged completeness diagnostic proved the 2026 local ``GameLog`` ledger is short of the
official pitching-line population: 13,301 official lines against 12,856 local lines, with 445
official lines absent locally and 159 stored lines differing from official evidence. This
module turns that proof into a deterministic, reviewable REPAIR MANIFEST.

It plans. It never applies. There is no apply mode in this module, no writer, and no
code path that can insert, update, or delete a row.

Why the evidence is re-derived rather than read from the diagnostic artifact: the production
artifact is bounded to 100 returned details, so it can name only a fraction of the 604 defect
lines. A bounded report is acceptable evidence for an accepted COUNT; it is never an
acceptable source of proposed writes. Every proposed value in this manifest therefore comes
from a fresh fetch of official MLB evidence.

Authority is not reinterpreted here. Official game selection, box-score pitching-section
enumeration, unique-starter identification, official stat parsing, identity matching, local
row matching, and defect classification are all delegated to the merged
``official_pitching_line_completeness_2026`` module. This module adds only the planning layer
on top of those governed results, so the two can never drift into two incompatible readings
of the same evidence.

Fail-closed on baseline drift: the accepted production population is pinned. If re-derivation
observes a different governed count, the plan refuses to declare itself reviewable — a
manifest built against a population that has moved is not the manifest that was reviewed.

Boundaries: read-only. Historical appearance-team authority stays the official box-score side;
``Pitcher.team_id`` is never consulted and a historical appearance never populates a current
team, roster, or activity field. No delete action type exists. Foundation 3B, the public
reader, Team State performance, Share Card performance, and SC-05 all remain blocked.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
import hashlib
import json
from typing import Dict, List, Optional

from models.pitcher import Pitcher
from services import appearance_team_authority as ata
from services import official_pitching_line_completeness_2026 as completeness
from services import season_bullpen_aggregation_2026 as aggregation
from services import sync as sync_service
from services.mlb_api import mlb_client
from utils.db import db


CAPABILITY = 'official_pitching_line_repair_plan_2026_v1'
PLAN_CONTRACT_VERSION = 'official_pitching_line_repair_plan_2026.v1'
COMPARISON_AUTHORITY = completeness.DIAGNOSTIC_CONTRACT_VERSION
APPEARANCE_TEAM_CONTRACT = completeness.APPEARANCE_TEAM_CONTRACT
EXPECTED_MIGRATION_HEAD = completeness.EXPECTED_MIGRATION_HEAD

DEFAULT_SEASON = completeness.DEFAULT_SEASON
DEFAULT_AS_OF_DATE = completeness.DEFAULT_AS_OF_DATE
REGULAR_SEASON_GAME_TYPE = completeness.REGULAR_SEASON_GAME_TYPE

DEFAULT_PREVIEW_LIMIT = 100
MAX_PREVIEW_LIMIT = 500

MODE_READ_ONLY = completeness.MODE_READ_ONLY
RESULT_PASS = completeness.RESULT_PASS
RESULT_FAIL = completeness.RESULT_FAIL
RESULT_INCONCLUSIVE = completeness.RESULT_INCONCLUSIVE
EXIT_BY_RESULT = dict(completeness.EXIT_BY_RESULT)

ROLE_STARTER = completeness.ROLE_STARTER
ROLE_RELIEF = completeness.ROLE_RELIEF

# ── Action vocabulary (no delete type exists, by contract) ────────────────────
ACTION_IDENTITY_CREATE = 'identity_create_required'
ACTION_GAME_LOG_INSERT = 'game_log_insert_required'
ACTION_GAME_LOG_UPDATE = 'game_log_update_required'
ACTION_TYPES = (ACTION_IDENTITY_CREATE, ACTION_GAME_LOG_INSERT, ACTION_GAME_LOG_UPDATE)
_ACTION_PHASE = {ACTION_IDENTITY_CREATE: 0, ACTION_GAME_LOG_INSERT: 1, ACTION_GAME_LOG_UPDATE: 2}

PLAN_SCOPE_FULL = 'full_season'
PLAN_SCOPE_SUBSET = 'diagnostic_subset'

PLAN_READY = 'ready_for_apply_review'
PLAN_BLOCKED_BASELINE_DRIFT = 'blocked_by_baseline_drift'
PLAN_BLOCKED_CONTRADICTORY = 'blocked_by_contradictory_population'
PLAN_BLOCKED_EVIDENCE = 'blocked_by_incomplete_official_evidence'
PLAN_BLOCKED_IDENTITY_MODEL = 'blocked_by_identity_model_requirement'
PLAN_BLOCKED_SUBSET = 'diagnostic_subset_not_apply_eligible'
PLAN_BLOCKED_UNSUPPORTED = 'blocked_by_unsupported_mutation'

GATE_BLOCKED = 'blocked'
GATE_BLOCKED_PENDING_REVIEW = 'blocked_pending_fingerprint_review'
GATE_BLOCKED_SUBSET = 'blocked_subset_not_apply_eligible'

# ── Blocking reason vocabulary ────────────────────────────────────────────────
BLOCK_IDENTITY_EVIDENCE_UNAVAILABLE = 'official_identity_evidence_unavailable'
BLOCK_IDENTITY_NAME_ABSENT = 'official_name_evidence_absent'
BLOCK_IDENTITY_POSITION_ABSENT = 'official_position_evidence_absent'
BLOCK_IDENTITY_MODEL_REQUIREMENT = 'identity_creation_blocked_by_model_requirement'
BLOCK_OFFICIAL_STAT_ABSENT = 'official_stat_evidence_absent'
BLOCK_OFFICIAL_TEAM_ABSENT = 'official_appearance_team_absent'
BLOCK_DEPENDENCY_UNRESOLVED = 'identity_dependency_unresolved'
BLOCK_DEPENDENCY_BLOCKED = 'identity_dependency_blocked'
BLOCK_CORRECTION_SOURCE_INCOMPLETE = 'official_correction_source_incomplete'
BLOCK_RAW_SOURCE_UNAVAILABLE = 'official_raw_pitching_line_unavailable'
BLOCK_OPPONENT_NAME_ABSENT = 'official_opponent_name_absent'
BLOCK_OPPONENT_ABBREVIATION_ABSENT = 'official_opponent_abbreviation_absent'
BLOCK_OPPONENT_IDENTITY_CONFLICT = 'official_opponent_identity_conflict'

# Where each official opponent value was resolved from, in authority order.
OPPONENT_SOURCE_BOXSCORE = 'official_boxscore_opposing_side'
OPPONENT_SOURCE_SCHEDULE = 'official_schedule_team_metadata'
OPPONENT_SOURCE_TEAM_REGISTRY = 'official_team_registry'
BLOCK_UPDATE_WOULD_NULL_LOCAL_VALUE = 'update_would_replace_local_value_with_null'

# ── Official GameLog value authority (production ingestion contract) ──────────
# Official pitching statistics are parsed by the SAME helpers daily ingestion uses, so the
# planner cannot become a second interpretation of an official line. These are reused
# unchanged rather than extracted, because extraction would move code on the live
# ingestion path for no behavioural gain.
CORRECTION_SOURCE_CONTRACT = 'services.sync._game_log_values_from_stats'
REQUIRED_CORRECTION_STAT_KEYS = sync_service._REQUIRED_CORRECTION_STAT_KEYS
OPTIONAL_BOOL_STAT_FIELDS = sync_service._OPTIONAL_BOOL_STAT_FIELDS
OPTIONAL_INT_STAT_FIELDS = sync_service._OPTIONAL_INT_STAT_FIELDS

# Identity and authority columns a repair may never move. game_date is excluded from the
# correctable set even though ingestion may correct it: a defect line is keyed by its game,
# so moving the date would silently retarget the row.
UPDATE_FORBIDDEN_FIELDS = frozenset({
    'pitcher_id', 'mlb_game_pk', 'game_date',
    'appearance_team_id', 'appearance_team_source', 'appearance_team_status',
    'appearance_team_reason',
})

# Raw official stat keys retained per defect line, before the completeness diagnostic
# normalizes an official line to the seven mandatory comparison metrics.
RETAINED_OFFICIAL_STAT_KEYS = (
    'inningsPitched', 'numberOfPitches', 'strikes', 'hits', 'runs', 'earnedRuns',
    'baseOnBalls', 'strikeOuts', 'homeRuns', 'battersFaced', 'balls', 'gamesFinished',
    'inheritedRunners', 'inheritedRunnersScored', 'saveOpportunities', 'holds',
    'blownSaves', 'wins', 'losses', 'saves',
)

# ── Correction metadata policy (DESCRIPTIVE — never executed here) ────────────
# A future apply step must follow the governed correction-metadata contract already
# implemented by ``sync._upsert_game_log_from_authoritative_values``. It is declared here so
# review can approve it with the manifest; the planner performs none of it.
CORRECTION_METADATA_POLICY = {
    'correction_source': 'official_pitching_line_repair',
    'stat_correction_count': 'incremented once per updated GameLog, never per changed field',
    'last_stat_correction_at': 'set at apply time; excluded from the manifest fingerprint',
    'last_stat_correction_source': 'recorded as the correction source identifier above',
    'last_stat_correction_sync_run_id': 'supplied by the apply operation, not by the plan',
    'dependent_evidence_invalidation': (
        'workload, appearance-context, and inherited-traffic evidence are marked for '
        'recomputation through the existing governed notification path '
        '(sync._notify_workload_evidence_game_log_correction)'),
    'executed_by_planner': False,
}
BLOCK_BASELINE_DRIFT = 'accepted_baseline_drift'
BLOCK_SUBSET_SCOPE = 'diagnostic_subset_scope'

# The accepted production population (merged completeness diagnostic, season 2026 through
# 2026-07-25). Pinned so a moved population fails closed instead of silently replanning.
ACCEPTED_BASELINE = {
    'official_games_selected': 1570,
    'official_games_fetched': 1570,
    'official_team_game_sides': 3140,
    'official_pitching_lines': 13301,
    'official_starter_lines': 3140,
    'official_relief_lines': 10161,
    'local_pitching_lines': 12856,
    'local_starter_lines': 3110,
    'local_relief_lines': 9746,
    'exact_match_count': 12697,
    'missing_line_count': 445,
    'defective_matched_line_count': 159,
    'defect_line_action_count': 604,
    'missing_lines_dependent_on_identity_creation': 342,
    'role_corrections_planned': 2,
    'appearance_team_mismatch_count': 0,
    'extra_local_line_count': 0,
    'duplicate_local_line_count': 0,
    'local_pitcher_identity_missing_count': 0,
    'official_evidence_unavailable_count': 0,
}

# GameLog stat fields planned from official evidence. (local attribute, official stat key)
PLANNED_STAT_FIELDS = tuple(
    (attr, key) for attr, key, _reason in completeness.STAT_COMPARISONS
)
# Field-level reason code per planned stat field.
STAT_REASON_BY_FIELD = {
    attr: reason for attr, _key, reason in completeness.STAT_COMPARISONS
}
# Reason code for a workload/decision field the mandatory metric comparison never covers.
WORKLOAD_FIELD_REASON = 'official_workload_field_mismatch'

# The manifest fingerprint accepted by the first production planner run. That manifest
# carried only the seven mandatory season metrics plus role and identity, so applying it
# would have written permanently incomplete GameLog rows. It is pinned here so the enriched
# manifest can prove it supersedes it.
PRIOR_PRODUCTION_MANIFEST_FINGERPRINT = (
    'dbbc063a0711e57b0dc2d858b7d1d291c568c4990ecff7c9ebf3d1b138cbb2d6')

# Every field a safe insert must carry. Derived from the governed ingestion contract, not
# from the model's nullable columns: these are the values an official line always supplies.
REQUIRED_INSERT_FIELDS = (
    'pitcher_id', 'mlb_game_pk', 'game_date', 'game_type',
    'opponent', 'opponent_abbreviation', 'games_started',
    'innings_pitched', 'innings_pitched_outs', 'strikes',
    'hits_allowed', 'runs_allowed', 'earned_runs', 'walks', 'strikeouts',
    'home_runs_allowed',
    'appearance_team_id', 'appearance_team_source', 'appearance_team_status',
    'appearance_team_reason',
)

# Mutable Pitcher fields a historical appearance can never populate. Listed on every identity
# action so the omission is explicit evidence, not an oversight.
OMITTED_MUTABLE_IDENTITY_FIELDS = (
    'team_id',
    'team_name',
    'team_abbreviation',
    'team_assignment_source',
    'team_assignment_status',
    'team_assignment_updated_at',
    'age',
    'jersey_number',
    'roster_status',
    'roster_status_raw_code',
    'roster_status_raw_description',
    'roster_status_source',
    'roster_status_updated_at',
)

# Pitcher columns whose Python-side default would INVENT current state if the creation path
# simply omitted them. Each must be set explicitly by any future apply step.
IDENTITY_MODEL_DEFAULT_HAZARDS = {
    'position': "column default 'P' would classify a position player as a pitcher",
    'active': 'column default True would assert current activity a historical appearance '
              'cannot prove',
}
# ``active`` is nullable, and every current-roster consumer filters ``Pitcher.active == True``,
# so an explicit NULL keeps an unknown-activity historical identity out of every current read.
IDENTITY_EXPLICIT_NULL_FIELDS = ('active',)


# ── Deterministic serialization + fingerprints ────────────────────────────────
def canonical_json(value) -> str:
    """Deterministic UTF-8 JSON: sorted keys, no whitespace, null distinct from zero."""
    return json.dumps(
        value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False,
        default=str,
    )


def sha256_of(value) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def _clamp_preview(value) -> int:
    parsed = completeness._int_or_none(value)
    if parsed is None:
        return DEFAULT_PREVIEW_LIMIT
    return max(0, min(parsed, MAX_PREVIEW_LIMIT))


# ── Official identity evidence (person-level, not appearance-level) ───────────
def _person_evidence(client, mlb_person_id):
    """Official ``/people/{id}`` identity evidence, or None when unavailable.

    Only identity-stable attributes are read. Current team, organization, roster status, and
    active status are deliberately NOT read from this payload — a historical appearance never
    establishes present-day state.
    """
    try:
        person = client.get_player_info(mlb_person_id)
    except Exception:  # noqa: BLE001 — official source unavailable => blocked, never guessed
        return None
    if not isinstance(person, dict):
        return None
    primary = person.get('primaryPosition') or {}
    hand = person.get('pitchHand') or {}
    name = person.get('fullName')
    return {
        'official_mlb_person_id': completeness._pos_int(person.get('id')) or mlb_person_id,
        'official_name': str(name).strip() if name else None,
        'official_primary_position': (
            str(primary.get('abbreviation')).strip()
            if primary.get('abbreviation') else None),
        'official_primary_position_code': (
            str(primary.get('code')).strip() if primary.get('code') else None),
        'official_throws': str(hand.get('code')).strip() if hand.get('code') else None,
    }


def _identity_action(mlb_person_id, evidence, dependent_action_ids) -> dict:
    """Plan one prerequisite identity, or record exactly why it cannot be planned safely."""
    blocking: List[str] = []
    proposed: Dict[str, object] = {}

    if evidence is None:
        blocking.append(BLOCK_IDENTITY_EVIDENCE_UNAVAILABLE)
    else:
        name = evidence.get('official_name')
        position = evidence.get('official_primary_position')
        if not name:
            blocking.append(BLOCK_IDENTITY_NAME_ABSENT)
        if not position:
            # Appearing in a pitching section does NOT prove a primary position of P. Without
            # direct official position evidence the identity is not safely representable,
            # because the model's column default would invent one.
            blocking.append(BLOCK_IDENTITY_POSITION_ABSENT)
        if not blocking:
            proposed = {
                'mlb_id': int(mlb_person_id),
                'full_name': name[:100],
                'position': position,
            }
            if evidence.get('official_throws'):
                proposed['throws'] = evidence['official_throws']
    if blocking:
        blocking.append(BLOCK_IDENTITY_MODEL_REQUIREMENT)

    source_evidence = {
        'official_mlb_person_id': int(mlb_person_id),
        'official_person_evidence': evidence,
        'source_endpoint': f'/people/{int(mlb_person_id)}',
    }
    return {
        'action_id': f'identity:create:{int(mlb_person_id)}',
        'action_type': ACTION_IDENTITY_CREATE,
        'official_mlb_person_id': int(mlb_person_id),
        'official_name': (evidence or {}).get('official_name'),
        'official_identity_source': source_evidence['source_endpoint'],
        'official_source_evidence': source_evidence,
        'source_fingerprint': sha256_of(source_evidence),
        'proposed_identity_fields': proposed,
        'explicitly_null_fields': list(IDENTITY_EXPLICIT_NULL_FIELDS),
        'explicitly_omitted_mutable_fields': list(OMITTED_MUTABLE_IDENTITY_FIELDS),
        'model_default_hazards': dict(IDENTITY_MODEL_DEFAULT_HAZARDS),
        'dependent_game_log_action_ids': sorted(dependent_action_ids),
        'dependency_action_ids': [],
        'safe_to_apply': not blocking,
        'blocking_reasons': sorted(set(blocking)),
    }


# ── Line-level planning ───────────────────────────────────────────────────────
def _official_source_evidence(line, *, raw_stats=None, sides=None, opponent=None) -> dict:
    """The official evidence a line-level action is derived from.

    Carries BOTH the normalized mandatory comparison metrics and the retained raw official
    pitching-stat object, plus the official and opposing team sides, so the fingerprint
    covers every value the action proposes.
    """
    opposing = (sides or {}).get('opposing_team') or {}
    official_team = (sides or {}).get('official_team') or {}
    return {
        'mlb_game_pk': int(line.game_pk),
        'game_date': completeness._iso_or_none(line.game_date),
        'official_side': line.side,
        'official_team_id': int(line.team_id),
        'official_team_name': line.team_name,
        'official_team_abbreviation': official_team.get('team_abbreviation'),
        'opposing_team_id': (opponent or {}).get('opposing_team_id',
                                                   opposing.get('team_id')),
        'opposing_team_name': (opponent or {}).get('opponent_name',
                                                   opposing.get('team_name')),
        'opposing_team_abbreviation': (opponent or {}).get(
            'opponent_abbreviation', opposing.get('team_abbreviation')),
        'opponent_name_source': (opponent or {}).get('opponent_name_source'),
        'opponent_abbreviation_source': (opponent or {}).get('opponent_abbreviation_source'),
        'opponent_blocking_reasons': sorted((opponent or {}).get('blocking_reasons') or ()),
        'official_mlb_person_id': int(line.pitcher_id),
        'official_name': line.pitcher_name,
        'official_role': line.role,
        'official_stats': dict(line.stats),
        'official_raw_stats': _retained_raw_stats(raw_stats),
        'official_raw_stats_available': raw_stats is not None,
    }


def _insert_action_id(line) -> str:
    return f'gamelog:insert:{int(line.game_pk)}:{int(line.pitcher_id)}:{int(line.team_id)}'


def _update_action_id(log_id, line) -> str:
    return f'gamelog:update:{int(log_id)}:{int(line.game_pk)}:{int(line.pitcher_id)}'


def _proposed_insert_fields(line, local_pitcher_id, *, raw_stats, sides, opponent):
    """Every proposed GameLog field, parsed by the production ingestion contract.

    Nothing is invented and no required value is defaulted: an official line whose required
    correction keys are incomplete blocks the action instead of filling zeros. Optional
    fields appear only when their official source key is genuinely present, so an official
    zero stays distinct from official absence.
    """
    blocking: List[str] = []
    proposed: Dict[str, object] = {
        'pitcher_id': local_pitcher_id,
        'mlb_game_pk': int(line.game_pk),
        'game_date': completeness._iso_or_none(line.game_date),
        'game_type': REGULAR_SEASON_GAME_TYPE,
        'appearance_team_id': int(line.team_id),
        'appearance_team_status': ata.STATUS_RESOLVED,
        'appearance_team_source': ata.SOURCE_BOXSCORE,
        'appearance_team_reason': ata.REASON_RESOLVED_BOXSCORE,
        'games_started': 1 if line.role == ROLE_STARTER else 0,
    }
    if raw_stats is None:
        blocking.append(BLOCK_RAW_SOURCE_UNAVAILABLE)
        return proposed, sorted(set(blocking))

    safe, _reason, _missing = sync_service._correction_source_state(raw_stats)
    if not safe:
        # The governed authoritative-source contract is not satisfied. Nothing is proposed
        # from an incomplete official line.
        blocking.append(BLOCK_CORRECTION_SOURCE_INCOMPLETE)
        return proposed, sorted(set(blocking))

    values = _official_game_log_values(
        raw_stats, line=line, local_pitcher_id=local_pitcher_id, sides=sides)
    # Opponent is authoritative only when BOTH values resolve from the opposing official
    # team. A required field is never parked in proposed_values as None to satisfy a
    # key-presence check.
    opponent = opponent or {}
    values['opponent'] = opponent.get('opponent_name')
    values['opponent_abbreviation'] = opponent.get('opponent_abbreviation')
    blocking.extend(opponent.get('blocking_reasons') or ())
    present_optional = _present_optional_fields(raw_stats)
    optional_fields = {field for _key, field in OPTIONAL_BOOL_STAT_FIELDS}
    optional_fields |= {field for field, _keys in OPTIONAL_INT_STAT_FIELDS}

    for field, value in values.items():
        if field in ('pitcher_id', 'mlb_game_pk', 'game_date', 'game_type', 'games_started'):
            continue                       # already set from governed line authority above
        if field in optional_fields and field not in present_optional:
            continue                       # official evidence absent: never defaulted
        if field == 'pitches_thrown' and value is None:
            # numberOfPitches is genuinely absent from some official completed-game lines.
            # It stays NULL and is reported through workload-field coverage.
            continue
        if field in ('opponent', 'opponent_abbreviation') and not value:
            # Incomplete opponent evidence blocks the action; it is never planned as null.
            continue
        proposed[field] = value

    if line.game_date is None:
        blocking.append(BLOCK_OFFICIAL_STAT_ABSENT)
    for attr, key in PLANNED_STAT_FIELDS:
        if line.stats.get(key) is None:
            blocking.append(BLOCK_OFFICIAL_STAT_ABSENT)
    return proposed, sorted(set(blocking))


def _insert_action(line, *, local_pitcher_id, identity_action_id, raw_stats=None,
                   sides=None, team_metadata=None) -> dict:
    opponent = _resolve_opponent(sides, team_metadata)
    proposed, blocking = _proposed_insert_fields(
        line, local_pitcher_id, raw_stats=raw_stats, sides=sides, opponent=opponent)
    dependencies = [identity_action_id] if identity_action_id else []
    if local_pitcher_id is None and not identity_action_id:
        blocking = sorted(set(blocking) | {BLOCK_DEPENDENCY_UNRESOLVED})
    source_evidence = _official_source_evidence(
        line, raw_stats=raw_stats, sides=sides, opponent=opponent)
    return {
        'action_id': _insert_action_id(line),
        'official_opponent_evidence': opponent,
        'action_type': ACTION_GAME_LOG_INSERT,
        'dependency_action_ids': dependencies,
        'official_mlb_person_id': int(line.pitcher_id),
        'official_name': line.pitcher_name,
        'official_team_id': int(line.team_id),
        'official_team_name': line.team_name,
        'official_role': line.role,
        'mlb_game_pk': int(line.game_pk),
        'game_date': completeness._iso_or_none(line.game_date),
        'local_pitcher_id': local_pitcher_id,
        'local_game_log_id': None,
        'current_values': None,
        'proposed_values': proposed,
        'changed_fields': sorted(proposed),
        'reason_codes': [completeness.REASON_OFFICIAL_LINE_MISSING],
        'official_source_references': [f'/game/{int(line.game_pk)}/boxscore'],
        'official_source_evidence': source_evidence,
        'source_fingerprint': sha256_of(source_evidence),
        'safe_to_apply': not blocking,
        'blocking_reasons': blocking,
    }


def _update_action(line, local, detail, *, raw_stats=None, sides=None,
                   team_metadata=None) -> dict:
    """One normalized update per defective stored row, however many fields differ."""
    log = local.log
    blocking: List[str] = []
    current_values: Dict[str, object] = {}
    proposed_values: Dict[str, object] = {}
    changed_fields: List[str] = []
    field_reason_codes: Dict[str, str] = {}

    expected_started = 1 if line.role == ROLE_STARTER else 0
    if log.games_started != expected_started:
        current_values['games_started'] = log.games_started
        proposed_values['games_started'] = expected_started
        changed_fields.append('games_started')
        field_reason_codes['games_started'] = completeness.REASON_ROLE_MISMATCH

    local_stats = completeness._local_stats(log)
    for attr, key in PLANNED_STAT_FIELDS:
        official_value = line.stats.get(key)
        if official_value is None:
            # No official value => nothing may be proposed for this field.
            blocking.append(BLOCK_OFFICIAL_STAT_ABSENT)
            continue
        if local_stats.get(key) != official_value:
            current_values[attr] = local_stats.get(key)
            proposed_values[attr] = int(official_value)
            changed_fields.append(attr)
            field_reason_codes[attr] = STAT_REASON_BY_FIELD[attr]

    if 'innings_pitched_outs' in proposed_values:
        # Keep the stored decimal representation consistent with the integer outs so the
        # database CHECK constraint still holds after any future apply.
        current_values['innings_pitched'] = log.innings_pitched
        proposed_values['innings_pitched'] = int(proposed_values['innings_pitched_outs']) / 3.0
        changed_fields.append('innings_pitched')
        field_reason_codes['innings_pitched'] = completeness.REASON_OUTS_MISMATCH

    # ── Workload and decision fields the ingestion contract also governs ──────
    # The mandatory season metrics alone leave a repaired row incomplete. Every field
    # ``sync._authoritative_correction_fields`` permits is compared here, so one action
    # carries both the mandatory correction and the workload correction for the same row.
    null_guarded_fields: List[str] = []
    opponent = _resolve_opponent(sides, team_metadata)
    if raw_stats is None:
        blocking.append(BLOCK_RAW_SOURCE_UNAVAILABLE)
    else:
        safe, _reason, _missing = sync_service._correction_source_state(raw_stats)
        if not safe:
            blocking.append(BLOCK_CORRECTION_SOURCE_INCOMPLETE)
        else:
            values = _official_game_log_values(
                raw_stats, line=line, local_pitcher_id=local.pitcher_row_id, sides=sides)
            # An opponent correction is only proposed from complete, source-backed official
            # opponent evidence; otherwise the field stays null-guarded and the stored value
            # is left alone.
            values['opponent'] = opponent.get('opponent_name')
            values['opponent_abbreviation'] = opponent.get('opponent_abbreviation')
            # Incomplete official opponent evidence is recorded as an explicit null guard.
            # The ingestion contract simply omits an absent opponent from the correctable
            # set, which silently loses the fact that a stored value was deliberately kept.
            for opponent_field in ('opponent', 'opponent_abbreviation'):
                if not values.get(opponent_field) and getattr(log, opponent_field, None):
                    null_guarded_fields.append(opponent_field)
            correctable = sync_service._authoritative_correction_fields(
                values, raw_stats, include_leverage_index=False)
            for field in correctable:
                if field in UPDATE_FORBIDDEN_FIELDS or field in proposed_values:
                    continue
                proposed_value = values.get(field)
                current_value = getattr(log, field, None)
                if current_value == proposed_value:
                    continue
                if proposed_value is None and current_value is not None:
                    # A repair never erases a stored value with an absent official one.
                    null_guarded_fields.append(field)
                    continue
                current_values[field] = current_value
                proposed_values[field] = proposed_value
                changed_fields.append(field)
                field_reason_codes.setdefault(field, WORKLOAD_FIELD_REASON)

    changed_fields = sorted(set(changed_fields))
    source_evidence = _official_source_evidence(
        line, raw_stats=raw_stats, sides=sides, opponent=opponent)
    comparison_evidence = {
        'local_game_log_id': int(log.id),
        'current_values': current_values,
        'proposed_values': proposed_values,
        'changed_fields': changed_fields,
        'reason_codes': sorted(set(detail['reason_codes'])),
        'official_source_evidence': source_evidence,
        'null_guarded_fields': sorted(set(null_guarded_fields)),
    }
    return {
        'action_id': _update_action_id(log.id, line),
        'action_type': ACTION_GAME_LOG_UPDATE,
        'dependency_action_ids': [],
        'local_game_log_id': int(log.id),
        'local_pitcher_id': int(local.pitcher_row_id),
        'official_mlb_person_id': int(line.pitcher_id),
        'official_name': line.pitcher_name,
        'official_team_id': int(line.team_id),
        'official_team_name': line.team_name,
        'official_role': line.role,
        'mlb_game_pk': int(line.game_pk),
        'game_date': completeness._iso_or_none(line.game_date),
        'appearance_team_id': log.appearance_team_id,
        'official_opponent_evidence': opponent,
        'current_values': current_values,
        'proposed_values': proposed_values,
        'changed_fields': changed_fields,
        'field_reason_codes': field_reason_codes,
        'reason_codes': sorted(set(detail['reason_codes'])),
        'official_source_references': [f"/game/{int(line.game_pk)}/boxscore"],
        'official_source_evidence': source_evidence,
        'source_fingerprint': sha256_of(source_evidence),
        'comparison_fingerprint': sha256_of(comparison_evidence),
        'null_guarded_fields': sorted(set(null_guarded_fields)),
        'safe_to_apply': not blocking and bool(changed_fields),
        'blocking_reasons': sorted(set(blocking)),
    }


def _select_official_games(client, *, season, as_of_date, team_id, game_pk):
    """Select official games AND retain the schedule's hydrated team metadata.

    Selection semantics are the merged completeness diagnostic's, unchanged; this wrapper
    only additionally retains the official team objects the schedule already hydrates, so a
    missing box-score abbreviation can be supplemented for the SAME official team id.
    """
    selected: Dict[int, Optional[date]] = {}
    schedule_teams: Dict[int, dict] = {}
    for start, end in aggregation._month_windows(date(season, 1, 1), as_of_date):
        try:
            fetched = client.get_schedule(
                start_date=start.isoformat(), end_date=end.isoformat()) or []
        except Exception:  # noqa: BLE001 — official source unavailable => inconclusive
            return selected, schedule_teams, True
        for game in fetched:
            pk = completeness._pos_int((game or {}).get('gamePk'))
            if pk is None or not aggregation._is_official_final_regular(game):
                continue
            if game_pk is not None and pk != game_pk:
                continue
            if team_id is not None and team_id not in completeness._game_team_ids(game):
                continue
            official_date = (game or {}).get('officialDate') or (game or {}).get('gameDate')
            try:
                parsed_date = date.fromisoformat(str(official_date)[:10])
            except (TypeError, ValueError):
                parsed_date = None
            selected[pk] = parsed_date
            for side_key in ('home', 'away'):
                team = ((((game or {}).get('teams') or {}).get(side_key) or {})
                        .get('team')) or {}
                team_identifier = completeness._pos_int(team.get('id'))
                if team_identifier is None:
                    continue
                record = schedule_teams.setdefault(team_identifier,
                                                   {'team_id': team_identifier})
                if not record.get('team_name') and team.get('name'):
                    record['team_name'] = team['name']
                if not record.get('team_abbreviation'):
                    abbreviation = sync_service._team_abbreviation_from(team)
                    if abbreviation:
                        record['team_abbreviation'] = abbreviation
    return selected, schedule_teams, False


def _official_team_registry(client, schedule_teams) -> dict:
    """Third-tier official team metadata, keyed by official MLB team id.

    Consulted only when the box score and the schedule both lack an abbreviation for an
    already-resolved opposing team id. Never a source for WHICH team is the opponent.
    """
    if not schedule_teams:
        return {}
    try:
        teams = client.get_all_teams() or []
    except Exception:  # noqa: BLE001 — supplemental source; absence blocks, never guesses
        return {}
    registry: Dict[int, dict] = {}
    for team in teams:
        team_id = completeness._pos_int((team or {}).get('id'))
        if team_id is None:
            continue
        registry[team_id] = {
            'team_id': team_id,
            'team_name': (team or {}).get('name'),
            'team_abbreviation': sync_service._team_abbreviation_from(team),
        }
    return registry


def _resolve_opponent(sides, team_metadata) -> dict:
    """Resolve the opposing team's official name and abbreviation, fail-closed.

    The opposing BOX-SCORE side is the only authority for WHICH team is the opponent. Once
    that team id is fixed, supplemental official metadata may supply a missing abbreviation
    for that same id — the schedule's hydrated team object first, then the official team
    registry. No current-team assignment, roster assignment, or name match participates, and
    a supplemental record for a different team id is a conflict rather than a fallback.
    """
    opposing = (sides or {}).get('opposing_team') or {}
    team_id = completeness._pos_int(opposing.get('team_id'))
    resolved = {
        'opposing_team_id': team_id,
        'opponent_name': None,
        'opponent_abbreviation': None,
        'opponent_name_source': None,
        'opponent_abbreviation_source': None,
        'blocking_reasons': [],
    }
    if team_id is None:
        resolved['blocking_reasons'] = [BLOCK_OPPONENT_NAME_ABSENT,
                                        BLOCK_OPPONENT_ABBREVIATION_ABSENT]
        return resolved

    name = (opposing.get('team_name') or '').strip() or None
    abbreviation = (opposing.get('team_abbreviation') or '').strip() or None
    if name:
        resolved['opponent_name_source'] = OPPONENT_SOURCE_BOXSCORE
    if abbreviation:
        resolved['opponent_abbreviation_source'] = OPPONENT_SOURCE_BOXSCORE

    for source, registry in ((OPPONENT_SOURCE_SCHEDULE, (team_metadata or {}).get('schedule')),
                             (OPPONENT_SOURCE_TEAM_REGISTRY,
                              (team_metadata or {}).get('registry'))):
        if name and abbreviation:
            break
        record = (registry or {}).get(team_id)
        if not record:
            continue
        record_id = completeness._pos_int(record.get('team_id'))
        if record_id is not None and record_id != team_id:
            # Supplemental metadata that does not describe the resolved opposing team.
            resolved['blocking_reasons'].append(BLOCK_OPPONENT_IDENTITY_CONFLICT)
            continue
        if not name and (record.get('team_name') or '').strip():
            name = record['team_name'].strip()
            resolved['opponent_name_source'] = source
        if not abbreviation and (record.get('team_abbreviation') or '').strip():
            abbreviation = record['team_abbreviation'].strip()
            resolved['opponent_abbreviation_source'] = source

    resolved['opponent_name'] = name
    resolved['opponent_abbreviation'] = abbreviation
    if not name:
        resolved['blocking_reasons'].append(BLOCK_OPPONENT_NAME_ABSENT)
    if not abbreviation:
        resolved['blocking_reasons'].append(BLOCK_OPPONENT_ABBREVIATION_ABSENT)
    resolved['blocking_reasons'] = sorted(set(resolved['blocking_reasons']))
    return resolved


def _raw_official_evidence(boxscore, *, game_pk) -> tuple:
    """Retain the RAW official pitching-stat object and both official team sides.

    The completeness diagnostic normalizes an official line to the seven mandatory
    comparison metrics; a complete GameLog repair needs everything else the official line
    carries. The same governed extractor daily ingestion uses supplies the raw lines here,
    so no second reading of the box score is introduced.

    Returns ``(raw_by_key, sides_by_key)`` where ``raw_by_key`` maps
    ``(game_pk, person_id, team_id)`` to the raw stats dict, and ``sides_by_key`` maps the
    same key to that line's official side plus the OPPOSING side's team identity — so
    opponent is derived from official game authority, never from a mutable player
    assignment.
    """
    team_by_side = {}
    for side_key in ('home', 'away'):
        team = ((((boxscore or {}).get('teams') or {}).get(side_key) or {}).get('team')) or {}
        team_by_side[side_key] = {
            'team_id': completeness._pos_int(team.get('id')),
            'team_name': team.get('name'),
            'team_abbreviation': sync_service._team_abbreviation_from(team),
        }

    raw_by_key: Dict[tuple, dict] = {}
    sides_by_key: Dict[tuple, dict] = {}
    for raw in sync_service._extract_pitching_lines_from_boxscore(boxscore):
        person_id = (completeness._pos_int(raw.get('person_id'))
                     or completeness._pos_int(raw.get('player_id')))
        team_id = completeness._pos_int(raw.get('team_id'))
        side = raw.get('side')
        if person_id is None or team_id is None or side not in ('home', 'away'):
            continue
        key = (int(game_pk), int(person_id), int(team_id))
        raw_by_key[key] = raw.get('stats') or {}
        opposing = team_by_side['away' if side == 'home' else 'home']
        sides_by_key[key] = {
            'official_side': side,
            'official_team': team_by_side[side],
            'opposing_team': opposing,
        }
    return raw_by_key, sides_by_key


class _PitcherRef:
    """Minimal stand-in supplying the only attribute the ingestion helper reads."""

    __slots__ = ('id',)

    def __init__(self, pitcher_id):
        self.id = pitcher_id


def _official_game_log_values(raw_stats, *, line, local_pitcher_id, sides):
    """Every official GameLog value, parsed by the production ingestion contract."""
    opposing = (sides or {}).get('opposing_team') or {}
    return sync_service._game_log_values_from_stats(
        stats=raw_stats,
        pitcher=_PitcherRef(local_pitcher_id),
        game_pk=int(line.game_pk),
        game_date=line.game_date,
        game_type=REGULAR_SEASON_GAME_TYPE,
        opponent=opposing.get('team_name'),
        opponent_abbreviation=opposing.get('team_abbreviation'),
        games_started=1 if line.role == ROLE_STARTER else 0,
        include_leverage_index=False,
    )


def _present_optional_fields(raw_stats) -> set:
    """Optional model fields whose official source key is actually present.

    Presence, not truthiness: this mirrors ``sync._authoritative_correction_fields`` exactly,
    so an official zero is distinguished from official absence.
    """
    present = set()
    for source_key, model_field in OPTIONAL_BOOL_STAT_FIELDS:
        if source_key in (raw_stats or {}) and (raw_stats or {}).get(source_key) not in (None, ''):
            present.add(model_field)
    for model_field, source_keys in OPTIONAL_INT_STAT_FIELDS:
        if sync_service._stat_key_present(raw_stats, source_keys):
            present.add(model_field)
    return present


def _retained_raw_stats(raw_stats) -> dict:
    """The retained raw official stat object: present keys only, absence preserved."""
    stats = raw_stats or {}
    return {key: stats[key] for key in RETAINED_OFFICIAL_STAT_KEYS if key in stats}


def _propagate_dependency_safety(identity_actions, insert_actions) -> None:
    """Mark every insertion unsafe whose identity prerequisite is not itself safe.

    An insertion that waits on a blocked identity cannot be applied — the row it would
    create has no pitcher to reference. Existence of a dependency is not resolution of a
    SAFE dependency, so safety is propagated explicitly here rather than assumed. The
    insertion keeps its ``dependency_action_ids`` and stays in the manifest; only its
    ``safe_to_apply`` and ``blocking_reasons`` change, and both feed the fingerprint.
    """
    by_id: Dict[str, List[dict]] = defaultdict(list)
    for identity in identity_actions:
        by_id[identity['action_id']].append(identity)

    for action in insert_actions:
        dependency_ids = action.get('dependency_action_ids') or []
        if not dependency_ids:
            continue
        blocking = set(action.get('blocking_reasons') or ())
        for dependency_id in dependency_ids:
            candidates = by_id.get(dependency_id) or []
            if len(candidates) != 1:
                # Absent, or ambiguous: either way the dependency does not resolve.
                blocking.add(BLOCK_DEPENDENCY_UNRESOLVED)
                continue
            dependency = candidates[0]
            if not dependency['safe_to_apply'] or dependency['blocking_reasons']:
                blocking.add(BLOCK_DEPENDENCY_BLOCKED)
        action['blocking_reasons'] = sorted(blocking)
        action['safe_to_apply'] = not blocking


def _action_sort_key(action) -> tuple:
    """Dependency phase, then official person, game date, game_pk, local row, action id."""
    game_date = action.get('game_date')
    game_pk = action.get('mlb_game_pk')
    log_id = action.get('local_game_log_id')
    return (
        _ACTION_PHASE[action['action_type']],
        action.get('official_mlb_person_id') or 0,
        game_date is None, game_date or '',
        game_pk is None, game_pk or 0,
        log_id is None, log_id or 0,
        action['action_id'],
    )


# ── Observed population (delegated classification) ────────────────────────────
@dataclass
class _Population:
    official_games_selected: int = 0
    official_games_fetched: int = 0
    official_team_game_sides: int = 0
    official_pitching_lines: int = 0
    official_starter_lines: int = 0
    official_relief_lines: int = 0
    official_lines_compared: int = 0
    local_pitching_lines: int = 0
    local_starter_lines: int = 0
    local_relief_lines: int = 0
    local_unknown_role_lines: int = 0
    exact_match_count: int = 0
    missing_line_count: int = 0
    defective_matched_line_count: int = 0
    missing_lines_dependent_on_identity_creation: int = 0
    missing_lines_using_existing_identity: int = 0
    role_corrections_planned: int = 0
    stat_correction_rows_planned: int = 0
    appearance_team_mismatch_count: int = 0
    extra_local_line_count: int = 0
    duplicate_local_line_count: int = 0
    local_pitcher_identity_missing_count: int = 0
    official_evidence_unavailable_count: int = 0
    contradictions: list = field(default_factory=list)

    def as_dict(self) -> dict:
        data = {k: v for k, v in self.__dict__.items() if k != 'contradictions'}
        data['defect_line_action_count'] = (
            self.missing_line_count + self.defective_matched_line_count)
        return data


def _fetch_official_evidence(client, *, season, as_of_date, team_id, game_pk):
    """Re-fetch official schedule + box scores using the governed selection authority."""
    selected_games, schedule_teams, schedule_failed = _select_official_games(
        client, season=season, as_of_date=as_of_date, team_id=team_id, game_pk=game_pk)
    boxscores: Dict[int, dict] = {}
    fetch_failures = 0
    for pk in sorted(selected_games):
        try:
            boxscores[pk] = client.get_game_boxscore(pk) or {}
        except Exception:  # noqa: BLE001 — bounded official failure => evidence gap
            fetch_failures += 1
    return selected_games, schedule_teams, boxscores, schedule_failed, fetch_failures


# ── Public entry point ────────────────────────────────────────────────────────
def run_repair_plan(
    *,
    season: int = DEFAULT_SEASON,
    as_of_date: date = DEFAULT_AS_OF_DATE,
    game_type: str = REGULAR_SEASON_GAME_TYPE,
    preview_limit: int = DEFAULT_PREVIEW_LIMIT,
    team_id: Optional[int] = None,
    game_pk: Optional[int] = None,
    generated_at: Optional[str] = None,
    client=mlb_client,
    session=None,
) -> dict:
    """Produce the read-only repair manifest. Plans only; never applies."""
    if game_type != REGULAR_SEASON_GAME_TYPE:
        raise ValueError('this planner covers regular-season (R) games only')
    session = session or db.session
    preview_limit = _clamp_preview(preview_limit)
    team_filter = completeness._pos_int(team_id)
    game_filter = completeness._pos_int(game_pk)
    plan_scope = (PLAN_SCOPE_SUBSET if (team_filter or game_filter) else PLAN_SCOPE_FULL)

    migration_head = completeness._migration_head(session)
    population = _Population()
    evidence_gaps: List[str] = []

    (selected_games, schedule_teams, boxscores, schedule_failed,
     fetch_failures) = _fetch_official_evidence(
        client, season=season, as_of_date=as_of_date, team_id=team_filter, game_pk=game_filter)
    team_metadata = {
        'schedule': schedule_teams,
        'registry': _official_team_registry(client, schedule_teams),
    }
    population.official_games_selected = len(selected_games)
    population.official_games_fetched = len(boxscores)
    population.official_evidence_unavailable_count += fetch_failures
    if schedule_failed:
        evidence_gaps.append(completeness.REASON_OFFICIAL_EVIDENCE_UNAVAILABLE)
    if fetch_failures:
        evidence_gaps.append(completeness.REASON_OFFICIAL_EVIDENCE_UNAVAILABLE)

    sides_by_game = {
        pk: completeness._official_sides(boxscores[pk], game_pk=pk,
                                         game_date=selected_games.get(pk))
        for pk in sorted(boxscores)
    }
    # Raw official evidence retained BEFORE normalization, plus both official team sides.
    raw_evidence: Dict[int, tuple] = {
        pk: _raw_official_evidence(boxscores[pk], game_pk=pk) for pk in sorted(boxscores)
    }
    all_official_ids = {
        pid for sides in sides_by_game.values() for side in sides for pid in side.identities
    }
    pitcher_rows = {}
    if all_official_ids:
        pitcher_rows = {
            row[0]: row[1] for row in
            session.query(Pitcher.mlb_id, Pitcher.id)
            .filter(Pitcher.mlb_id.in_(sorted(all_official_ids))).all()
        }

    local_lines = completeness._local_lines(session, set(boxscores))
    population.local_pitching_lines = len(local_lines)
    local_by_game: Dict[int, list] = defaultdict(list)
    local_by_identity: Dict[tuple, list] = defaultdict(list)
    for local in local_lines:
        local_by_game[local.log.mlb_game_pk].append(local)
        if local.mlb_id is not None:
            local_by_identity[(local.log.mlb_game_pk, local.mlb_id)].append(local)
        if local.log.games_started == 1:
            population.local_starter_lines += 1
        elif local.log.games_started == 0:
            population.local_relief_lines += 1
        else:
            population.local_unknown_role_lines += 1

    insert_actions: List[dict] = []
    update_actions: List[dict] = []
    identity_dependents: Dict[int, List[str]] = defaultdict(list)
    # Typed line populations, keyed by the stable official line key
    # (game_pk, official_mlb_person_id, appearance_team_id). Every compared line enters
    # ``observed_official_line_keys``; only defect lines enter the defect populations, so an
    # exact match can never satisfy a coverage reconciliation.
    observed_official_line_keys: List[tuple] = []
    observed_defect_line_keys: List[tuple] = []
    targeted_local_rows: set = set()

    for pk in sorted(sides_by_game):
        sides = sides_by_game[pk]
        raw_by_key, sides_by_key = raw_evidence.get(pk, ({}, {}))
        official_identities_in_game: set = set()
        for side in sides:
            official_identities_in_game |= side.identities
            population.official_pitching_lines += side.enumerated_line_count
            if side.team_id is None:
                population.official_evidence_unavailable_count += 1
                evidence_gaps.append(completeness.REASON_OFFICIAL_EVIDENCE_UNAVAILABLE)
                continue
            population.official_team_game_sides += 1
            if side.starter_status != 'unique':
                population.official_evidence_unavailable_count += 1
                evidence_gaps.append(
                    completeness.REASON_OFFICIAL_STARTER_CONTRADICTORY
                    if side.starter_status == 'contradictory'
                    else completeness.REASON_OFFICIAL_STARTER_MISSING)
                continue

            for line in side.lines:
                population.official_lines_compared += 1
                if line.role == ROLE_STARTER:
                    population.official_starter_lines += 1
                else:
                    population.official_relief_lines += 1

                line_key = (int(pk), int(line.pitcher_id), int(line.team_id))
                if line_key in set(observed_official_line_keys):
                    # A duplicate official source line is a contradiction, never a plan.
                    population.contradictions.append({
                        'kind': 'duplicate_official_source_line', 'game_pk': pk,
                        'official_mlb_person_id': line.pitcher_id, 'team_id': line.team_id})
                observed_official_line_keys.append(line_key)

                local_pitcher_id = pitcher_rows.get(line.pitcher_id)
                if local_pitcher_id is None:
                    population.missing_line_count += 1
                    population.missing_lines_dependent_on_identity_creation += 1
                    observed_defect_line_keys.append(line_key)
                    identity_action_id = f'identity:create:{int(line.pitcher_id)}'
                    action = _insert_action(
                        line, local_pitcher_id=None,
                        identity_action_id=identity_action_id,
                        raw_stats=raw_by_key.get(line_key),
                        sides=sides_by_key.get(line_key),
                        team_metadata=team_metadata)
                    identity_dependents[line.pitcher_id].append(action['action_id'])
                    insert_actions.append(action)
                    continue

                matches = local_by_identity.get((pk, line.pitcher_id)) or []
                detail = completeness._compare_official_line(line, matches)
                reasons = detail['reason_codes']
                if reasons == [completeness.REASON_EXACT_MATCH]:
                    # An exact match is not a defect and never enters a defect population.
                    population.exact_match_count += 1
                    continue
                if completeness.REASON_OFFICIAL_LINE_MISSING in reasons:
                    population.missing_line_count += 1
                    population.missing_lines_using_existing_identity += 1
                    observed_defect_line_keys.append(line_key)
                    insert_actions.append(_insert_action(
                        line, local_pitcher_id=int(local_pitcher_id), identity_action_id=None,
                        raw_stats=raw_by_key.get(line_key),
                        sides=sides_by_key.get(line_key),
                        team_metadata=team_metadata))
                    continue

                observed_defect_line_keys.append(line_key)

                population.defective_matched_line_count += 1
                if completeness.REASON_LOCAL_DUPLICATE in reasons:
                    population.duplicate_local_line_count += 1
                    population.contradictions.append({
                        'kind': completeness.REASON_LOCAL_DUPLICATE, 'game_pk': pk,
                        'official_mlb_person_id': line.pitcher_id,
                        'local_match_count': len(matches)})
                if completeness.REASON_APPEARANCE_TEAM_MISMATCH in reasons:
                    population.appearance_team_mismatch_count += 1
                    population.contradictions.append({
                        'kind': completeness.REASON_APPEARANCE_TEAM_MISMATCH, 'game_pk': pk,
                        'official_mlb_person_id': line.pitcher_id,
                        'official_team_id': line.team_id,
                        'local_appearance_team_id': matches[0].log.appearance_team_id})
                if completeness.REASON_ROLE_MISMATCH in reasons:
                    population.role_corrections_planned += 1
                if any(reason in completeness.STAT_REASONS for reason in reasons):
                    population.stat_correction_rows_planned += 1

                primary = matches[0]
                if primary.log.id in targeted_local_rows:
                    population.contradictions.append({
                        'kind': 'local_row_targeted_twice',
                        'local_game_log_id': primary.log.id})
                targeted_local_rows.add(primary.log.id)
                update_actions.append(_update_action(
                    line, primary, detail,
                    raw_stats=raw_by_key.get(line_key),
                    sides=sides_by_key.get(line_key),
                    team_metadata=team_metadata))

        for local in local_by_game.get(pk, ()):
            if local.mlb_id is None:
                population.local_pitcher_identity_missing_count += 1
                population.contradictions.append({
                    'kind': completeness.REASON_LOCAL_IDENTITY_MISSING,
                    'local_game_log_id': local.log.id, 'game_pk': pk})
            elif local.mlb_id not in official_identities_in_game:
                population.extra_local_line_count += 1
                population.contradictions.append({
                    'kind': completeness.REASON_LOCAL_LINE_EXTRA,
                    'local_game_log_id': local.log.id, 'game_pk': pk,
                    'local_pitcher_mlb_id': local.mlb_id})

    # Identity prerequisites: one per UNIQUE official person, not per dependent appearance.
    identity_actions = []
    for mlb_person_id in sorted(identity_dependents):
        evidence = _person_evidence(client, mlb_person_id)
        if evidence is None:
            evidence_gaps.append(BLOCK_IDENTITY_EVIDENCE_UNAVAILABLE)
        identity_actions.append(_identity_action(
            mlb_person_id, evidence, identity_dependents[mlb_person_id]))

    # Dependency SAFETY, not merely dependency existence: an insertion is only applicable
    # when the identity it waits on is itself applicable.
    _propagate_dependency_safety(identity_actions, insert_actions)

    planned_defect_line_keys = [
        (int(a['mlb_game_pk']), int(a['official_mlb_person_id']), int(a['official_team_id']))
        for a in insert_actions + update_actions
    ]

    manifest = sorted(identity_actions + insert_actions + update_actions,
                      key=_action_sort_key)
    duplicate_action_ids = _duplicate_action_ids(manifest)
    manifest_fingerprint = sha256_of(manifest)

    observed = population.as_dict()
    baseline_comparison, baseline_matches = _compare_baseline(observed, plan_scope)

    reconciliations = _reconciliations(
        population=population, observed=observed, manifest=manifest,
        identity_actions=identity_actions, insert_actions=insert_actions,
        update_actions=update_actions, baseline_matches=baseline_matches,
        duplicate_action_ids=duplicate_action_ids,
        targeted_local_rows=targeted_local_rows,
        observed_official_line_keys=observed_official_line_keys,
        observed_defect_line_keys=observed_defect_line_keys,
        planned_defect_line_keys=planned_defect_line_keys,
        manifest_fingerprint=manifest_fingerprint)

    result, plan_status, decision_reasons = _decide(
        population=population, plan_scope=plan_scope, evidence_gaps=evidence_gaps,
        baseline_matches=baseline_matches, manifest=manifest,
        reconciliations=reconciliations, duplicate_action_ids=duplicate_action_ids)

    if plan_scope == PLAN_SCOPE_SUBSET:
        repair_apply_gate = GATE_BLOCKED_SUBSET
    elif result == RESULT_PASS:
        repair_apply_gate = GATE_BLOCKED_PENDING_REVIEW
    else:
        repair_apply_gate = GATE_BLOCKED

    preview = manifest[:preview_limit]
    return {
        'capability': CAPABILITY,
        'mode': MODE_READ_ONLY,
        'result': result,
        'exit_code': EXIT_BY_RESULT[result],
        'generated_at': generated_at,
        'git_sha': completeness._git_sha(),
        'migration_head': migration_head,
        'expected_migration_head': EXPECTED_MIGRATION_HEAD,
        'season': int(season),
        'as_of_date': as_of_date.isoformat(),
        'inputs': {
            'season': int(season),
            'as_of_date': as_of_date.isoformat(),
            'game_type': REGULAR_SEASON_GAME_TYPE,
            'preview_limit': preview_limit,
            'team_id': team_filter,
            'game_pk': game_filter,
        },
        'contracts': {
            'plan_contract_version': PLAN_CONTRACT_VERSION,
            'comparison_authority': COMPARISON_AUTHORITY,
            'appearance_team_contract': APPEARANCE_TEAM_CONTRACT,
            'identity_match_contract': completeness.IDENTITY_MATCH_CONTRACT,
            'starter_identity_contract': completeness.STARTER_IDENTITY_CONTRACT,
            'action_types': list(ACTION_TYPES),
        },
        'plan_scope': plan_scope,
        'accepted_baseline': dict(ACCEPTED_BASELINE),
        'observed_population': observed,
        'baseline_comparison': baseline_comparison,
        'baseline_matches_accepted_diagnostic': baseline_matches,
        'official_games_selected': population.official_games_selected,
        'official_games_fetched': population.official_games_fetched,
        'official_team_game_sides': population.official_team_game_sides,
        'official_pitching_lines': population.official_pitching_lines,
        'official_starter_lines': population.official_starter_lines,
        'official_relief_lines': population.official_relief_lines,
        'local_pitching_lines': population.local_pitching_lines,
        'local_starter_lines': population.local_starter_lines,
        'local_relief_lines': population.local_relief_lines,
        'exact_match_count': population.exact_match_count,
        'missing_line_count': population.missing_line_count,
        'defective_matched_line_count': population.defective_matched_line_count,
        'defect_line_action_count': observed['defect_line_action_count'],
        'unique_identities_requiring_creation': len(identity_actions),
        'missing_lines_dependent_on_identity_creation':
            population.missing_lines_dependent_on_identity_creation,
        'missing_lines_using_existing_identity':
            population.missing_lines_using_existing_identity,
        'game_log_inserts_planned': len(insert_actions),
        'existing_game_logs_requiring_updates': len(update_actions),
        'role_corrections_planned': population.role_corrections_planned,
        'stat_correction_rows_planned': population.stat_correction_rows_planned,
        'actions_by_type': {
            ACTION_IDENTITY_CREATE: len(identity_actions),
            ACTION_GAME_LOG_INSERT: len(insert_actions),
            ACTION_GAME_LOG_UPDATE: len(update_actions),
        },
        'actions_by_team': _actions_by_team(insert_actions, update_actions),
        'blocking_counts_by_reason': _blocking_counts(manifest),
        'no_action_confirmations': {
            'delete_actions': 0,
            'appearance_team_id_update_actions': 0,
            'duplicate_consolidation_actions': 0,
            'phantom_row_deletions': 0,
            'current_team_updates': 0,
            'current_role_updates': 0,
            'public_surface_changes': 0,
        },
        'workload_field_coverage': _workload_field_coverage(
            insert_actions, update_actions, manifest),
        'correction_metadata_policy': dict(CORRECTION_METADATA_POLICY),
        'prior_production_manifest_fingerprint': PRIOR_PRODUCTION_MANIFEST_FINGERPRINT,
        'repair_manifest_action_count': len(manifest),
        'repair_manifest': manifest,
        'repair_manifest_fingerprint': manifest_fingerprint,
        'duplicate_action_ids': sorted(duplicate_action_ids),
        'bounded_preview': preview,
        'preview_limit': preview_limit,
        'preview_truncated': len(manifest) > len(preview),
        'verification_plan': _verification_plan(),
        'reconciliations': reconciliations,
        'decision_reasons': decision_reasons,
        'plan_status': plan_status,
        'repair_apply_gate': repair_apply_gate,
        'foundation_3b_gate': GATE_BLOCKED,
        'public_reader_gate': GATE_BLOCKED,
        'share_card_performance_gate': GATE_BLOCKED,
        'database_writes_performed': False,
    }


def _required_insert_values_present(action) -> bool:
    """Required insert fields must carry a real VALUE, not merely a present key.

    ``opponent_abbreviation: None`` satisfies key presence and proves nothing, so required
    fields whose absence is meaningful are checked for a non-empty value.
    """
    proposed = action.get('proposed_values') or {}
    for field in REQUIRED_INSERT_FIELDS:
        if field not in proposed:
            return False
        value = proposed[field]
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
    return True


def _optional_fields_are_source_backed(action) -> bool:
    """An optional field may appear only when its official source key was present."""
    proposed = action.get('proposed_values') or {}
    raw = ((action.get('official_source_evidence') or {}).get('official_raw_stats') or {})
    if not raw:
        return True                      # blocked action proposes no optional field
    present = _present_optional_fields(raw)
    optional_fields = {field for _key, field in OPTIONAL_BOOL_STAT_FIELDS}
    optional_fields |= {field for field, _keys in OPTIONAL_INT_STAT_FIELDS}
    return all(field in present for field in optional_fields if field in proposed)


def _opponent_matches_official_side(action) -> bool:
    """A proposed opponent value must be non-empty AND trace to the opposing official team.

    ``None == None`` can never satisfy this: a proposed opponent field is only accepted when
    it carries a real value, that value equals the resolved opposing team's official value,
    and a resolution source is recorded for it.
    """
    proposed = action.get('proposed_values') or {}
    evidence = action.get('official_source_evidence') or {}
    opponent = action.get('official_opponent_evidence') or {}
    checks = (
        ('opponent', 'opposing_team_name', 'opponent_name_source'),
        ('opponent_abbreviation', 'opposing_team_abbreviation',
         'opponent_abbreviation_source'),
    )
    for field, evidence_key, source_key in checks:
        if field not in proposed:
            continue                     # blocked or unchanged: nothing claimed
        value = proposed.get(field)
        if not value:
            return False                 # a required opponent value is never null/empty
        if value != evidence.get(evidence_key):
            return False
        if not opponent.get(source_key):
            return False                 # no recorded official source authority
        if completeness._pos_int(opponent.get('opposing_team_id')) is None:
            return False
    return True


def _safe_action_has_complete_opponent_evidence(action) -> bool:
    """A safe insertion must carry a non-empty, source-backed opponent name AND code."""
    if not action.get('safe_to_apply'):
        return True
    proposed = action.get('proposed_values') or {}
    opponent = action.get('official_opponent_evidence') or {}
    return bool(proposed.get('opponent')) and bool(proposed.get('opponent_abbreviation')) \
        and bool(opponent.get('opponent_name_source')) \
        and bool(opponent.get('opponent_abbreviation_source')) \
        and completeness._pos_int(opponent.get('opposing_team_id')) is not None


def _workload_field_coverage(insert_actions, update_actions, manifest) -> dict:
    """Deterministic coverage of the official workload evidence each action carries.

    Absence is reported, never manufactured: an official line genuinely missing
    ``numberOfPitches`` is counted here rather than silently receiving a value.
    """
    def _proposed(action):
        return action.get('proposed_values') or {}

    def _raw(action):
        return ((action.get('official_source_evidence') or {}).get('official_raw_stats') or {})

    inherited_fields = ('inherited_runners', 'inherited_runners_scored')
    decision_fields = ('save_situation', 'hold', 'blown_save', 'win', 'loss', 'save')

    inserts_with_pitch_count = sum(
        1 for a in insert_actions if _proposed(a).get('pitches_thrown') is not None)
    inserts_with_strikes = sum(
        1 for a in insert_actions if 'strikes' in _proposed(a))
    inserts_with_batters_faced = sum(
        1 for a in insert_actions if 'batters_faced' in _proposed(a))
    inserts_with_inherited = sum(
        1 for a in insert_actions
        if any(field in _proposed(a) for field in inherited_fields))
    inserts_with_balls = sum(1 for a in insert_actions if 'balls' in _proposed(a))
    inserts_with_games_finished = sum(
        1 for a in insert_actions if 'games_finished' in _proposed(a))
    inserts_with_decisions = sum(
        1 for a in insert_actions
        if any(field in _proposed(a) for field in decision_fields))
    inserts_with_opponent_name = sum(
        1 for a in insert_actions if _proposed(a).get('opponent'))
    inserts_with_opponent_abbreviation = sum(
        1 for a in insert_actions if _proposed(a).get('opponent_abbreviation'))

    def _blocked_by(reason):
        return sum(1 for a in manifest if reason in (a.get('blocking_reasons') or ()))

    def _updates_changing(fields):
        return sum(1 for a in update_actions
                   if set(a.get('changed_fields') or ()) & set(fields))

    return {
        'insert_actions_total': len(insert_actions),
        'insert_actions_with_official_pitch_count': inserts_with_pitch_count,
        'insert_actions_without_official_pitch_count':
            len(insert_actions) - inserts_with_pitch_count,
        'insert_actions_with_official_strikes': inserts_with_strikes,
        'insert_actions_with_batters_faced': inserts_with_batters_faced,
        'insert_actions_with_balls': inserts_with_balls,
        'insert_actions_with_games_finished': inserts_with_games_finished,
        'insert_actions_with_inherited_runner_evidence': inserts_with_inherited,
        'insert_actions_with_decision_evidence': inserts_with_decisions,
        'insert_actions_with_official_opponent_name': inserts_with_opponent_name,
        'insert_actions_with_official_opponent_abbreviation':
            inserts_with_opponent_abbreviation,
        'actions_blocked_by_missing_opponent_name':
            _blocked_by(BLOCK_OPPONENT_NAME_ABSENT),
        'actions_blocked_by_missing_opponent_abbreviation':
            _blocked_by(BLOCK_OPPONENT_ABBREVIATION_ABSENT),
        'actions_blocked_by_opponent_identity_conflict':
            _blocked_by(BLOCK_OPPONENT_IDENTITY_CONFLICT),
        'update_actions_total': len(update_actions),
        'update_actions_correcting_pitch_count': _updates_changing(('pitches_thrown',)),
        'update_actions_correcting_strikes': _updates_changing(('strikes',)),
        'update_actions_correcting_batters_faced': _updates_changing(('batters_faced',)),
        'update_actions_correcting_inherited_runner_fields':
            _updates_changing(inherited_fields),
        'update_actions_correcting_decision_fields': _updates_changing(decision_fields),
        'update_actions_correcting_opponent':
            _updates_changing(('opponent', 'opponent_abbreviation')),
        'update_actions_with_null_guarded_fields': sum(
            1 for a in update_actions if a.get('null_guarded_fields')),
        'actions_blocked_by_incomplete_authoritative_source': sum(
            1 for a in manifest
            if {BLOCK_CORRECTION_SOURCE_INCOMPLETE, BLOCK_RAW_SOURCE_UNAVAILABLE}
            & set(a.get('blocking_reasons') or ())),
    }


def _duplicate_action_ids(manifest) -> set:
    seen, duplicates = set(), set()
    for action in manifest:
        if action['action_id'] in seen:
            duplicates.add(action['action_id'])
        seen.add(action['action_id'])
    return duplicates


def _compare_baseline(observed, plan_scope):
    """Compare every governed count to the accepted production baseline."""
    comparison = {}
    matches = True
    for key, expected in sorted(ACCEPTED_BASELINE.items()):
        actual = observed.get(key)
        difference = None if actual is None else actual - expected
        equal = actual == expected
        comparison[key] = {
            'expected_value': expected, 'observed_value': actual,
            'difference': difference, 'matches': equal,
        }
        if not equal:
            matches = False
    if plan_scope != PLAN_SCOPE_FULL:
        # A scoped run is a diagnostic subset; it can never satisfy the full-season baseline.
        matches = False
    return comparison, matches


def _actions_by_team(insert_actions, update_actions) -> dict:
    """Line-level actions grouped by official appearance team (identity actions have none)."""
    buckets: Dict[int, dict] = defaultdict(
        lambda: {ACTION_GAME_LOG_INSERT: 0, ACTION_GAME_LOG_UPDATE: 0})
    for action in insert_actions:
        buckets[action['official_team_id']][ACTION_GAME_LOG_INSERT] += 1
    for action in update_actions:
        buckets[action['official_team_id']][ACTION_GAME_LOG_UPDATE] += 1
    return {str(team): dict(counts) for team, counts in sorted(buckets.items())}


def _blocking_counts(manifest) -> dict:
    counts: Dict[str, int] = defaultdict(int)
    for action in manifest:
        for reason in action.get('blocking_reasons') or ():
            counts[reason] += 1
    return dict(sorted(counts.items()))


def _reconciliations(*, population, observed, manifest, identity_actions, insert_actions,
                     update_actions, baseline_matches, duplicate_action_ids,
                     targeted_local_rows, observed_official_line_keys,
                     observed_defect_line_keys, planned_defect_line_keys,
                     manifest_fingerprint) -> dict:
    defect_actions = len(insert_actions) + len(update_actions)
    identity_by_id = {a['action_id']: a for a in identity_actions}
    identity_dependency_ids = set(identity_by_id)
    dependent_ids = {dep for a in identity_actions
                     for dep in a['dependent_game_log_action_ids']}
    insert_ids_with_dependency = {
        a['action_id'] for a in insert_actions if a['dependency_action_ids']}
    every_dependency_resolves = all(
        set(a['dependency_action_ids']) <= identity_dependency_ids for a in manifest)
    dependency_reference_counts = [
        sum(1 for identity in identity_actions if identity['action_id'] == dependency_id)
        for a in manifest for dependency_id in (a.get('dependency_action_ids') or ())
    ]

    observed_defect_set = set(observed_defect_line_keys)
    planned_defect_set = set(planned_defect_line_keys)
    exact_match_keys = set(observed_official_line_keys) - observed_defect_set

    def _dependency_actions(action):
        return [identity_by_id[dep] for dep in (action.get('dependency_action_ids') or ())
                if dep in identity_by_id]

    safe_dependents_have_safe_dependencies = all(
        all(dep['safe_to_apply'] and not dep['blocking_reasons']
            for dep in _dependency_actions(a))
        for a in insert_actions if a['safe_to_apply']
    )
    blocked_identities_block_dependents = all(
        all(not action['safe_to_apply']
            and BLOCK_DEPENDENCY_BLOCKED in (action.get('blocking_reasons') or ())
            for action in insert_actions
            if identity['action_id'] in (action.get('dependency_action_ids') or ()))
        for identity in identity_actions
        if not identity['safe_to_apply'] or identity['blocking_reasons']
    )
    return {
        'official_lines_partition':
            population.official_lines_compared == (
                population.exact_match_count + population.missing_line_count
                + population.defective_matched_line_count),
        'official_lines_partition_matches_baseline':
            (not baseline_matches) or (
                ACCEPTED_BASELINE['official_pitching_lines']
                == ACCEPTED_BASELINE['exact_match_count']
                + ACCEPTED_BASELINE['missing_line_count']
                + ACCEPTED_BASELINE['defective_matched_line_count']),
        'defect_line_action_count_equals_defect_lines':
            defect_actions == (
                population.missing_line_count + population.defective_matched_line_count),
        'defect_line_action_count_matches_baseline':
            (not baseline_matches)
            or defect_actions == ACCEPTED_BASELINE['defect_line_action_count'],
        'missing_lines_partition':
            population.missing_line_count == (
                population.missing_lines_dependent_on_identity_creation
                + population.missing_lines_using_existing_identity),
        'planned_inserts_equal_missing_lines':
            len(insert_actions) == population.missing_line_count,
        'planned_updates_equal_defective_rows':
            len(update_actions) == population.defective_matched_line_count,
        'role_corrections_subset_of_updates':
            population.role_corrections_planned <= len(update_actions),
        'identity_actions_reconcile_to_dependent_appearances':
            dependent_ids == insert_ids_with_dependency
            and len(dependent_ids) == population.missing_lines_dependent_on_identity_creation,
        'every_dependency_references_one_identity_action':
            every_dependency_resolves
            and all(count == 1 for count in dependency_reference_counts),
        # ── Exact defect-line coverage ────────────────────────────────────────
        # Typed populations keyed by (game_pk, official person id, appearance_team_id).
        # An exact match never enters either defect population, so equality here is real
        # coverage: not "at least as many lines as actions", but the same lines.
        'observed_official_line_keys_unique':
            len(observed_official_line_keys) == len(set(observed_official_line_keys)),
        'observed_defect_line_keys_unique':
            len(observed_defect_line_keys) == len(set(observed_defect_line_keys)),
        'planned_defect_line_keys_unique':
            len(planned_defect_line_keys) == len(set(planned_defect_line_keys)),
        'observed_defect_keys_equal_planned_defect_keys':
            observed_defect_set == planned_defect_set,
        'observed_defect_key_count_equals_defect_lines':
            len(observed_defect_line_keys) == (
                population.missing_line_count + population.defective_matched_line_count),
        'planned_defect_key_count_equals_line_actions':
            len(planned_defect_line_keys) == defect_actions,
        'every_defect_line_maps_to_exactly_one_action':
            observed_defect_set == planned_defect_set
            and len(observed_defect_line_keys) == len(observed_defect_set)
            and len(planned_defect_line_keys) == len(planned_defect_set)
            and len(planned_defect_line_keys) == defect_actions,
        'no_exact_line_maps_to_a_repair_action':
            not (exact_match_keys & planned_defect_set),
        'defect_keys_are_a_subset_of_observed_official_lines':
            observed_defect_set <= set(observed_official_line_keys),
        # ── Dependency safety ─────────────────────────────────────────────────
        'every_safe_dependent_insertion_has_a_safe_dependency':
            safe_dependents_have_safe_dependencies,
        'every_blocked_identity_blocks_its_dependent_insertions':
            blocked_identities_block_dependents,
        'identity_dependent_lists_reconcile_to_insertion_references':
            dependent_ids == insert_ids_with_dependency,
        'every_local_row_targeted_at_most_once':
            len(targeted_local_rows) == len(update_actions),
        # ── Official GameLog evidence completeness ────────────────────────────
        'every_safe_insert_contains_every_required_correction_field': all(
            _required_insert_values_present(a)
            for a in insert_actions if a['safe_to_apply']),
        'no_required_official_value_is_defaulted': all(
            not a['safe_to_apply'] or _required_insert_values_present(a)
            for a in insert_actions),
        'optional_fields_planned_only_when_source_present': all(
            _optional_fields_are_source_backed(a) for a in insert_actions),
        'every_changed_field_has_current_and_proposed_values': all(
            set(a.get('changed_fields') or ()) <= set(a.get('proposed_values') or {})
            and set(a.get('changed_fields') or ()) <= set(a.get('current_values') or {})
            for a in update_actions),
        'no_update_replaces_a_local_value_with_null': all(
            not any(a.get('proposed_values', {}).get(field) is None
                    and (a.get('current_values') or {}).get(field) is not None
                    for field in (a.get('changed_fields') or ()))
            for a in update_actions),
        'opponent_comes_from_the_official_game_side': all(
            _opponent_matches_official_side(a) for a in insert_actions + update_actions),
        'every_safe_insertion_has_a_non_empty_opponent': all(
            bool((a.get('proposed_values') or {}).get('opponent'))
            for a in insert_actions if a['safe_to_apply']),
        'every_safe_insertion_has_a_non_empty_opponent_abbreviation': all(
            bool((a.get('proposed_values') or {}).get('opponent_abbreviation'))
            for a in insert_actions if a['safe_to_apply']),
        'opponent_values_resolve_from_one_opposing_official_team': all(
            _safe_action_has_complete_opponent_evidence(a)
            for a in insert_actions),
        'no_safe_action_has_missing_opponent_evidence': all(
            not ({BLOCK_OPPONENT_NAME_ABSENT, BLOCK_OPPONENT_ABBREVIATION_ABSENT,
                  BLOCK_OPPONENT_IDENTITY_CONFLICT}
                 & set(a.get('blocking_reasons') or ()))
            for a in insert_actions + update_actions if a['safe_to_apply']),
        'every_proposed_opponent_field_is_non_null_and_source_backed': all(
            _opponent_matches_official_side(a)
            and all((a.get('proposed_values') or {}).get(field)
                    for field in ('opponent', 'opponent_abbreviation')
                    if field in (a.get('changed_fields') or ()))
            for a in update_actions),
        'source_fingerprints_cover_the_enriched_raw_evidence': all(
            a.get('source_fingerprint') == sha256_of(a.get('official_source_evidence'))
            and 'official_raw_stats' in (a.get('official_source_evidence') or {})
            for a in insert_actions + update_actions),
        'manifest_fingerprint_differs_from_prior_production_fingerprint':
            manifest_fingerprint != PRIOR_PRODUCTION_MANIFEST_FINGERPRINT,
        'no_action_changes_appearance_team_id': not any(
            'appearance_team_id' in (a.get('changed_fields') or ())
            for a in update_actions),
        'no_action_changes_current_team_fields': not any(
            set(a.get('changed_fields') or ()) & {
                'team_id', 'team_name', 'team_abbreviation', 'active', 'roster_status'}
            for a in update_actions),
        'no_delete_action_exists': all(
            a['action_type'] in ACTION_TYPES for a in manifest),
        'manifest_action_count_equals_sum':
            len(manifest) == len(identity_actions) + len(insert_actions) + len(update_actions),
        'action_ids_unique': not duplicate_action_ids,
        'database_writes_performed_false': True,
    }


def _decide(*, population, plan_scope, evidence_gaps, baseline_matches, manifest,
            reconciliations, duplicate_action_ids):
    """FAIL on contradiction, INCONCLUSIVE on evidence gaps or drift, else PASS."""
    fail_reasons: List[str] = []
    inconclusive_reasons: List[str] = []

    if population.contradictions:
        fail_reasons.extend(sorted({c['kind'] for c in population.contradictions}))
    if duplicate_action_ids:
        fail_reasons.append('duplicate_action_id')
    if not all(reconciliations.values()):
        fail_reasons.extend(
            sorted(f'reconciliation_failed:{name}'
                   for name, ok in reconciliations.items() if not ok))
    if fail_reasons:
        return (RESULT_FAIL, PLAN_BLOCKED_CONTRADICTORY, sorted(set(fail_reasons)))

    unsafe = [a for a in manifest if not a['safe_to_apply']]
    identity_blocked = any(
        BLOCK_IDENTITY_MODEL_REQUIREMENT in (a.get('blocking_reasons') or ())
        for a in manifest)
    if evidence_gaps:
        inconclusive_reasons.extend(sorted(set(evidence_gaps)))
    if not baseline_matches:
        inconclusive_reasons.append(BLOCK_BASELINE_DRIFT)
    if unsafe:
        inconclusive_reasons.extend(sorted({
            reason for a in unsafe for reason in (a.get('blocking_reasons') or ())}))

    if inconclusive_reasons:
        if not baseline_matches and plan_scope == PLAN_SCOPE_FULL:
            status = PLAN_BLOCKED_BASELINE_DRIFT
        elif plan_scope != PLAN_SCOPE_FULL:
            status = PLAN_BLOCKED_SUBSET
        elif identity_blocked:
            status = PLAN_BLOCKED_IDENTITY_MODEL
        else:
            status = PLAN_BLOCKED_EVIDENCE
        return (RESULT_INCONCLUSIVE, status, sorted(set(inconclusive_reasons)))

    if plan_scope != PLAN_SCOPE_FULL:
        return (RESULT_INCONCLUSIVE, PLAN_BLOCKED_SUBSET, [BLOCK_SUBSET_SCOPE])
    return (RESULT_PASS, PLAN_READY, ['repair_manifest_ready_for_fingerprint_review'])


def _verification_plan() -> list:
    """Descriptive only. Nothing here is executed by this module."""
    return [
        {'step': 1, 'action': 'rerun_official_pitching_line_completeness_diagnostic',
         'requirement': 'every official pitching line matches one exact local counterpart'},
        {'step': 2, 'action': 'require_completeness_diagnostic_pass',
         'requirement': 'result == pass with zero missing, extra, or defective lines'},
        {'step': 3, 'action': 'rerun_canonical_season_bullpen_aggregation_local_only',
         'requirement': 'local_only aggregation completes'},
        {'step': 4, 'action': 'require_local_only_pass',
         'requirement': 'result == pass'},
        {'step': 5, 'action': 'rerun_canonical_season_bullpen_aggregation_official_validation',
         'requirement': 'official_validation mode completes'},
        {'step': 6, 'action': 'require_official_validation_pass',
         'requirement': 'result == pass with zero mandatory metric mismatches'},
        {'step': 7, 'action': 'review_generated_artifacts',
         'requirement': 'operator review of every produced artifact'},
        {'step': 8, 'action': 'consider_foundation_3b_reader_work',
         'requirement': 'only after every preceding gate passes'},
    ]
