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
def _official_source_evidence(line) -> dict:
    """The normalized official evidence a line-level action is derived from."""
    return {
        'mlb_game_pk': int(line.game_pk),
        'game_date': completeness._iso_or_none(line.game_date),
        'official_side': line.side,
        'official_team_id': int(line.team_id),
        'official_team_name': line.team_name,
        'official_mlb_person_id': int(line.pitcher_id),
        'official_name': line.pitcher_name,
        'official_role': line.role,
        'official_stats': dict(line.stats),
    }


def _insert_action_id(line) -> str:
    return f'gamelog:insert:{int(line.game_pk)}:{int(line.pitcher_id)}:{int(line.team_id)}'


def _update_action_id(log_id, line) -> str:
    return f'gamelog:update:{int(log_id)}:{int(line.game_pk)}:{int(line.pitcher_id)}'


def _proposed_insert_fields(line, local_pitcher_id):
    """Derive every proposed GameLog field from official evidence. Nothing is invented."""
    blocking: List[str] = []
    stats = line.stats
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
    for attr, key in PLANNED_STAT_FIELDS:
        value = stats.get(key)
        if value is None:
            # Absent official evidence is never read as zero.
            blocking.append(BLOCK_OFFICIAL_STAT_ABSENT)
            continue
        proposed[attr] = int(value)
    outs = stats.get('outs')
    if outs is not None:
        # innings_pitched is a stored redundant representation of the integer outs, held
        # equal by a database CHECK constraint. It is derived, never independently sourced.
        proposed['innings_pitched'] = int(outs) / 3.0
    if line.game_date is None:
        blocking.append(BLOCK_OFFICIAL_STAT_ABSENT)
    return proposed, sorted(set(blocking))


def _insert_action(line, *, local_pitcher_id, identity_action_id) -> dict:
    proposed, blocking = _proposed_insert_fields(line, local_pitcher_id)
    dependencies = [identity_action_id] if identity_action_id else []
    if local_pitcher_id is None and not identity_action_id:
        blocking = sorted(set(blocking) | {BLOCK_DEPENDENCY_UNRESOLVED})
    source_evidence = _official_source_evidence(line)
    return {
        'action_id': _insert_action_id(line),
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


def _update_action(line, local, detail) -> dict:
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

    changed_fields = sorted(set(changed_fields))
    source_evidence = _official_source_evidence(line)
    comparison_evidence = {
        'local_game_log_id': int(log.id),
        'current_values': current_values,
        'proposed_values': proposed_values,
        'changed_fields': changed_fields,
        'reason_codes': sorted(set(detail['reason_codes'])),
        'official_source_evidence': source_evidence,
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
        'current_values': current_values,
        'proposed_values': proposed_values,
        'changed_fields': changed_fields,
        'field_reason_codes': field_reason_codes,
        'reason_codes': sorted(set(detail['reason_codes'])),
        'official_source_references': [f"/game/{int(line.game_pk)}/boxscore"],
        'official_source_evidence': source_evidence,
        'source_fingerprint': sha256_of(source_evidence),
        'comparison_fingerprint': sha256_of(comparison_evidence),
        'safe_to_apply': not blocking and bool(changed_fields),
        'blocking_reasons': sorted(set(blocking)),
    }


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
    selected_games, schedule_failed = completeness._select_official_games(
        client, season=season, as_of_date=as_of_date, team_id=team_id, game_pk=game_pk)
    boxscores: Dict[int, dict] = {}
    fetch_failures = 0
    for pk in sorted(selected_games):
        try:
            boxscores[pk] = client.get_game_boxscore(pk) or {}
        except Exception:  # noqa: BLE001 — bounded official failure => evidence gap
            fetch_failures += 1
    return selected_games, boxscores, schedule_failed, fetch_failures


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

    selected_games, boxscores, schedule_failed, fetch_failures = _fetch_official_evidence(
        client, season=season, as_of_date=as_of_date, team_id=team_filter, game_pk=game_filter)
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
    targeted_official_lines: set = set()
    targeted_local_rows: set = set()

    for pk in sorted(sides_by_game):
        sides = sides_by_game[pk]
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

                line_key = (pk, line.pitcher_id, line.team_id)
                if line_key in targeted_official_lines:
                    population.contradictions.append({
                        'kind': 'official_line_targeted_twice', 'game_pk': pk,
                        'official_mlb_person_id': line.pitcher_id, 'team_id': line.team_id})
                targeted_official_lines.add(line_key)

                local_pitcher_id = pitcher_rows.get(line.pitcher_id)
                if local_pitcher_id is None:
                    population.missing_line_count += 1
                    population.missing_lines_dependent_on_identity_creation += 1
                    identity_action_id = f'identity:create:{int(line.pitcher_id)}'
                    action = _insert_action(line, local_pitcher_id=None,
                                            identity_action_id=identity_action_id)
                    identity_dependents[line.pitcher_id].append(action['action_id'])
                    insert_actions.append(action)
                    continue

                matches = local_by_identity.get((pk, line.pitcher_id)) or []
                detail = completeness._compare_official_line(line, matches)
                reasons = detail['reason_codes']
                if reasons == [completeness.REASON_EXACT_MATCH]:
                    population.exact_match_count += 1
                    continue
                if completeness.REASON_OFFICIAL_LINE_MISSING in reasons:
                    population.missing_line_count += 1
                    population.missing_lines_using_existing_identity += 1
                    insert_actions.append(_insert_action(
                        line, local_pitcher_id=int(local_pitcher_id), identity_action_id=None))
                    continue

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
                update_actions.append(_update_action(line, primary, detail))

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
        targeted_official_lines=targeted_official_lines)

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
                     targeted_local_rows, targeted_official_lines) -> dict:
    defect_actions = len(insert_actions) + len(update_actions)
    identity_dependency_ids = {a['action_id'] for a in identity_actions}
    dependent_ids = {dep for a in identity_actions
                     for dep in a['dependent_game_log_action_ids']}
    insert_ids_with_dependency = {
        a['action_id'] for a in insert_actions if a['dependency_action_ids']}
    every_dependency_resolves = all(
        set(a['dependency_action_ids']) <= identity_dependency_ids for a in manifest)
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
        'every_dependency_references_one_identity_action': every_dependency_resolves,
        'every_official_defect_line_maps_to_one_action':
            len(targeted_official_lines) >= defect_actions
            and len({a['action_id'] for a in insert_actions + update_actions})
            == defect_actions,
        'every_local_row_targeted_at_most_once':
            len(targeted_local_rows) == len(update_actions),
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
