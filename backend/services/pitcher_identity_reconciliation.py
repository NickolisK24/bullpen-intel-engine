"""Canonical pitcher-identity planner for completed-game evidence.

ONE authority decides, for a single official pitching line, what happens to the
`Pitcher` row behind that appearance — and under the permanent rule below, for
an existing row the answer is always *nothing*.

Why this module exists
----------------------
Production R2 reconciled 946 appearance rows to zero GameLog mutations and
reported PASS. The same report carried 942 `pitcher_identity_reconciliation`
categories: 940 metadata updates and 2 reactivations across 423 pitchers,
attached to rows whose GameLog action was `unchanged`. The GameLog reconciler
had been made pure and centralised; pitcher resolution had not. It stayed a
side-effecting path that mutated and flushed `Pitcher` rows before or alongside
GameLog reconciliation, and neither the reconciliation fingerprint nor the R1/R2
validators covered it. A run could therefore report zero mutations and an empty
update manifest while write mode would still change hundreds of rows.

That is two defects at once: shadow could not see what write would do, and
completed-game evidence was being used as current-roster authority.

Permanent authority rule (D-009)
--------------------------------
    completed-game pitching line
        = authority for APPEARANCE identity and HISTORICAL appearance context

    official current roster / assignment sources
        = authority for CURRENT state

A completed game proves that a person pitched in it and which team they
represented *in that appearance*. It cannot prove that the person is currently
active, currently on that team, currently on a roster, or currently classified
under any particular roster status. A game from three weeks ago is not evidence
about today, and letting it act as such silently rewrites roster truth from
history.

So for an EXISTING pitcher, this planner never plans a mutation. Differences
between historical appearance metadata and the current row are recorded as
SUPPRESSED evidence — visible, counted, reviewable, and never applied. Historical
team belongs on the GameLog appearance-team fields, which already carry it.

For a MISSING pitcher, a minimal identity may be created, because a new
appearance row cannot be persisted without one. That creation is a separate
governed action, it enters the reviewed fingerprint, and it claims no current
state: no team assignment, no active status, no official roster status.

This module is PURE. It reads a row and returns a deterministic, serializable
plan. It performs no writes, opens no transaction, and mutates nothing.
"""

from __future__ import annotations

import hashlib
import json

from services.roster_status import STATUS_ACTIVE, STATUS_UNKNOWN


IDENTITY_PLAN_VERSION = '1'

# ── Actions ─────────────────────────────────────────────────────────────────
# `update_metadata` and `reactivate` are deliberately absent. They were the two
# completed-game write actions this repair retires; an existing row resolves to
# `unchanged` or, on an identity safety failure, to `blocked`.
ACTION_UNCHANGED = 'unchanged'
ACTION_CREATE_MINIMAL_IDENTITY = 'create_minimal_identity'
ACTION_BLOCKED = 'blocked'

ACTIONS = (ACTION_UNCHANGED, ACTION_CREATE_MINIMAL_IDENTITY, ACTION_BLOCKED)

# Actions that would touch the database. Everything else is observation.
MUTATING_ACTIONS = (ACTION_CREATE_MINIMAL_IDENTITY,)

RETIRED_WRITE_ACTIONS = ('update_metadata', 'reactivate', 'create')

# ── Statuses ────────────────────────────────────────────────────────────────
STATUS_RESOLVED = 'resolved'
STATUS_WOULD_CREATE = 'would_create'
STATUS_BLOCKED = 'blocked'

# ── Field authority ─────────────────────────────────────────────────────────
# Current-state fields an existing Pitcher row owns. Completed-game evidence may
# NEVER write any of them. This is structural: the planner has no code path that
# emits one of these as a changed field for an existing row, so no combination
# of sources, precedence, or blocked-flags can produce one.
CURRENT_STATE_AUTHORITY_FIELDS = (
    'active',
    'roster_status',
    'roster_status_raw_code',
    'roster_status_raw_description',
    'roster_status_source',
    'roster_status_updated_at',
    'team_abbreviation',
    'team_assignment_source',
    'team_assignment_status',
    'team_assignment_updated_at',
    'team_id',
    'team_name',
)

# Fields that identify the person rather than describe their current situation.
# They are immutable from this path once set: a completed game is not a rename
# authority, and `position` here is the local record's classification, not the
# position the player happened to occupy in one game.
IDENTITY_FIELDS = ('full_name', 'mlb_id', 'position')

# The complete set a minimal creation may populate. Nothing outside this may be
# written by an identity creation, so a creation cannot smuggle in a team.
MINIMAL_CREATION_FIELDS = (
    'active',
    'full_name',
    'mlb_id',
    'position',
    'roster_status',
    'roster_status_raw_description',
    'roster_status_source',
)

KNOWN_IDENTITY_FIELDS = frozenset(
    CURRENT_STATE_AUTHORITY_FIELDS + IDENTITY_FIELDS
)

# ── Blocked reasons ─────────────────────────────────────────────────────────
BLOCKED_MISSING_PLAYER_ID = 'missing_or_invalid_player_id'
BLOCKED_CONFLICTING_IDENTITY = 'conflicting_player_identity'
BLOCKED_MISSING_NAME = 'missing_player_name'
BLOCKED_NON_PITCHER_POSITION = 'non_pitcher_position'
BLOCKED_LOCAL_RECORD_NOT_PITCHER = 'local_record_not_pitcher'

# Provenance for an identity created from a completed-game appearance. It names
# the appearance as the source precisely so a later roster sync can tell that
# this row's current state was never verified.
MINIMAL_IDENTITY_SOURCE = (
    'mlb_stats_api:completed_game_appearance_identity'
)
MINIMAL_IDENTITY_ROSTER_DESCRIPTION = (
    'Identity created from a completed-game appearance; current roster status '
    'unverified'
)

DEFAULT_PITCHER_POSITION = 'P'


def plan_identity(
    *,
    existing,
    player_mlb_id,
    line_name=None,
    line_position=None,
    appearance_team=None,
    position_override=False,
    blocked_reason=None,
) -> dict:
    """Decide what happens to the Pitcher row behind one official pitching line.

    Pure. ``existing`` is the stored row or ``None``. ``appearance_team`` is the
    historical team the line was recorded under — accepted only so the plan can
    REPORT that it differs from the current assignment, never so it can apply it.
    """
    base = {
        'identity_plan_version': IDENTITY_PLAN_VERSION,
        'player_mlb_id': player_mlb_id,
        'local_pitcher_id': getattr(existing, 'id', None),
        'identity_status': STATUS_RESOLVED,
        'action': ACTION_UNCHANGED,
        'changed_fields': [],
        'applied_fields': [],
        'suppressed_current_state_fields': [],
        'creation_values': {},
        'requires_creation': False,
        'current_authority_mutation_refused': False,
        'source_authority': MINIMAL_IDENTITY_SOURCE,
        'affects_published_evidence': False,
        'governed_and_safe': True,
        'blocked_reason': None,
        'mutation_digest': '',
    }

    # ── Blocked ─────────────────────────────────────────────────────────────
    # Identity safety failures are unchanged by this repair and still fail
    # closed. A SUPPRESSED current-state difference is not one of them.
    if blocked_reason:
        base.update({
            'action': ACTION_BLOCKED,
            'identity_status': STATUS_BLOCKED,
            'governed_and_safe': False,
            'blocked_reason': blocked_reason,
        })
        return base

    if player_mlb_id is None:
        base.update({
            'action': ACTION_BLOCKED,
            'identity_status': STATUS_BLOCKED,
            'governed_and_safe': False,
            'blocked_reason': BLOCKED_MISSING_PLAYER_ID,
        })
        return base

    # ── Missing row: minimal creation ───────────────────────────────────────
    if existing is None:
        if not line_name:
            base.update({
                'action': ACTION_BLOCKED,
                'identity_status': STATUS_BLOCKED,
                'governed_and_safe': False,
                'blocked_reason': BLOCKED_MISSING_NAME,
            })
            return base

        creation_values = minimal_identity_values(
            player_mlb_id=player_mlb_id,
            line_name=line_name,
            line_position=line_position,
            position_override=position_override,
        )
        base.update({
            'action': ACTION_CREATE_MINIMAL_IDENTITY,
            'identity_status': STATUS_WOULD_CREATE,
            'requires_creation': True,
            'changed_fields': sorted(creation_values),
            'applied_fields': sorted(creation_values),
            'creation_values': creation_values,
            # A created identity becomes visible to bullpen reads once roster
            # authority claims it, so the creation itself is evidence-bearing.
            'affects_published_evidence': True,
            'mutation_digest': _digest(
                ACTION_CREATE_MINIMAL_IDENTITY, creation_values,
            ),
        })
        return base

    # ── Existing row: never mutated ─────────────────────────────────────────
    # Everything the completed game could have said about current state is
    # recorded and refused. `changed_fields` stays empty by construction — there
    # is no branch below that can add to it.
    suppressed = suppressed_current_state_fields(
        existing=existing,
        line_name=line_name,
        appearance_team=appearance_team,
    )
    base.update({
        'suppressed_current_state_fields': suppressed,
        'current_authority_mutation_refused': bool(suppressed),
    })
    return base


def minimal_identity_values(
    *, player_mlb_id, line_name, line_position=None, position_override=False,
) -> dict:
    """The smallest identity that can own an appearance row.

    No team, no assignment provenance, no assignment timestamp, and explicitly
    NOT active — the column defaults to active, so leaving it unset would make a
    historical appearance silently assert that the player is on a roster today.
    Roster status is recorded as unverified rather than claimed.

    ``position`` keeps the position the OFFICIAL line recorded rather than
    forcing 'P'. That is game evidence, not a current-state claim, and it is the
    conservative choice: flattening a two-way player's 'DH' record to 'P' would
    make them look like a bullpen arm to every downstream eligibility read.
    """
    position = (line_position or '').strip().upper() or DEFAULT_PITCHER_POSITION
    description = MINIMAL_IDENTITY_ROSTER_DESCRIPTION
    if position_override:
        description = f'{description}; position_override_from_pitching_line'
    return {
        'mlb_id': player_mlb_id,
        'full_name': line_name,
        'position': DEFAULT_PITCHER_POSITION if position == 'PITCHER' else position,
        'active': False,
        'roster_status': STATUS_UNKNOWN,
        'roster_status_source': MINIMAL_IDENTITY_SOURCE,
        'roster_status_raw_description': description,
    }


def suppressed_current_state_fields(
    *, existing, line_name=None, appearance_team=None,
) -> list[str]:
    """Current-state fields a completed game would have rewritten, and did not.

    Observation only. This is what makes the refusal auditable: an operator can
    see that 940 rows carried a historical/current difference without a single
    one of them becoming a mutation.
    """
    suppressed = []
    team = appearance_team or {}

    if not getattr(existing, 'active', False):
        # The retired path set active=True from any final-game appearance.
        suppressed.append('active')

    appearance_team_id = team.get('team_id')
    if appearance_team_id is not None:
        if getattr(existing, 'team_id', None) != appearance_team_id:
            suppressed.append('team_id')
        team_name = team.get('team_name')
        if team_name and getattr(existing, 'team_name', None) != team_name:
            suppressed.append('team_name')
        abbreviation = team.get('team_abbreviation')
        if (
            abbreviation
            and getattr(existing, 'team_abbreviation', None) != abbreviation
        ):
            suppressed.append('team_abbreviation')

    if getattr(existing, 'roster_status', None) != STATUS_ACTIVE:
        # The retired path overwrote any non-active status with UNKNOWN.
        suppressed.append('roster_status')

    if line_name and not getattr(existing, 'full_name', None):
        suppressed.append('full_name')
    if not getattr(existing, 'position', None):
        suppressed.append('position')

    return sorted(set(suppressed))


def _digest(action, values) -> str:
    """Digest of the VALUES an identity plan would write, not merely its shape.

    Without this, creating one pitcher and creating a different one fingerprint
    identically, and a reviewed plan would authorize the wrong row.
    """
    payload = sorted(
        (field, _safe_value(value)) for field, value in (values or {}).items()
    )
    encoded = json.dumps(
        [action, payload], sort_keys=True, separators=(',', ':'), default=str,
    )
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:32]


def fingerprint_component(plan) -> tuple:
    """The identity contribution to the complete reconciliation fingerprint.

    Suppressed fields are deliberately excluded: they describe evidence that was
    REFUSED, so they must not move a fingerprint that authorizes mutations.
    """
    plan = plan or {}
    return (
        str(plan.get('player_mlb_id')),
        plan.get('action') or ACTION_UNCHANGED,
        plan.get('blocked_reason') or '',
        plan.get('mutation_digest') or '',
    )


def is_mutation(plan) -> bool:
    return bool(plan) and plan.get('action') in MUTATING_ACTIONS


def summarize(plans) -> dict:
    """Run-level aggregation over identity plans. Deterministic ordering."""
    plans = [plan for plan in (plans or ()) if plan]
    action_counts: dict[str, int] = {}
    changed_field_counts: dict[str, int] = {}
    suppressed_field_counts: dict[str, int] = {}
    mutations = unchanged = creations = blocked = 0
    refusals = 0
    affected: set = set()

    for plan in plans:
        action = plan.get('action') or ACTION_UNCHANGED
        action_counts[action] = action_counts.get(action, 0) + 1
        for field in plan.get('changed_fields') or ():
            changed_field_counts[field] = changed_field_counts.get(field, 0) + 1
        for field in plan.get('suppressed_current_state_fields') or ():
            suppressed_field_counts[field] = (
                suppressed_field_counts.get(field, 0) + 1
            )
        if action == ACTION_CREATE_MINIMAL_IDENTITY:
            creations += 1
            mutations += 1
            affected.add(plan.get('player_mlb_id'))
        elif action == ACTION_BLOCKED:
            blocked += 1
        else:
            unchanged += 1
        if plan.get('current_authority_mutation_refused'):
            refusals += 1

    return {
        'pitcher_identity_rows_examined': len(plans),
        'pitcher_identity_mutations': mutations,
        'pitcher_identity_unchanged': unchanged,
        'pitcher_identity_creations': creations,
        # Retired actions. Reported as explicit zeros rather than omitted, so a
        # validator asserting zero is asserting against a present field.
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': blocked,
        'pitcher_identity_action_counts': dict(sorted(action_counts.items())),
        'pitcher_identity_changed_fields_counts': dict(
            sorted(changed_field_counts.items())
        ),
        'pitcher_identity_unique_pitchers_affected': len(
            {value for value in affected if value is not None}
        ),
        'historical_current_state_changes_suppressed': refusals,
        'suppressed_current_state_field_counts': dict(
            sorted(suppressed_field_counts.items())
        ),
        'identity_plan_version': IDENTITY_PLAN_VERSION,
    }


def _safe_value(value):
    """Render a governed identity value for reporting."""
    if value is None or isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


def safe_row_entry(plan) -> dict:
    """Per-row identity report. Governed fields only, no payload fragments."""
    plan = plan or {}
    return {
        'pitcher_identity_action': plan.get('action'),
        'pitcher_identity_status': plan.get('identity_status'),
        'pitcher_identity_changed_fields': list(plan.get('changed_fields') or ()),
        'pitcher_identity_applied_fields': list(plan.get('applied_fields') or ()),
        'pitcher_identity_suppressed_fields': list(
            plan.get('suppressed_current_state_fields') or ()
        ),
        'pitcher_identity_governed_and_safe': bool(
            plan.get('governed_and_safe', True)
        ),
        'pitcher_identity_blocked_reason': plan.get('blocked_reason'),
        'pitcher_identity_mutation_digest': plan.get('mutation_digest') or '',
        'pitcher_identity_requires_creation': bool(plan.get('requires_creation')),
        'pitcher_identity_current_authority_mutation_refused': bool(
            plan.get('current_authority_mutation_refused')
        ),
    }
