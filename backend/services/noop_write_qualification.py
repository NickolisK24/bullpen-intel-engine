"""Manual exact-scope no-op write qualification.

Proves the game-driven ingestion lane can enter its governed write-capable code
path for exactly one completed game while mutating no baseball data.

What this module is
-------------------
Governance and evidence only. It owns no writer, no comparator, and no
reconciliation logic. Every baseball decision is made by the canonical
components and read back out of their reports:

    services.game_ingestion_planner.plan_game_work   scope + finality
    services.game_driven_ingestion.run_game_driven_ingestion
                                                     the one lane entry point
    services.game_log_reconciliation                 the one planner + digests
    services.pitcher_identity_reconciliation         D-009 identity governance
    services.game_driven_realization                 the realization proof
    services.sync_metadata.acquire_sync_writer_guard the production writer lock

The two-phase shape
-------------------
1. ``shadow``  exclusive to the requested game. Reads only. Produces the
   reconciliation-plan fingerprint and the per-row plan a human reviews.
2. ``write``   exclusive to the same game, authorized by that fingerprint. The
   canonical lane re-fetches, re-plans, and refuses before its first mutation
   if either the source revision or the plan moved.

Step 2's drift check is the lane's own ``_authorize_reviewed_plan``. This module
does not re-implement it — a second comparator is exactly the drift this design
exists to prevent.

What "no-op" means here, precisely
----------------------------------
Measured against the canonical lane, an exclusive write over an
already-matching game produces:

    game_log_rows_written              0
    pitcher_rows_written               0
    appearance_team_rows_written       0
    correction_provenance_rows_written 0
    dead_letters_created               0
    work_items_updated                 1
    work_items_completed               1
    checkpoints_advanced               1
    commits_performed                  1

The first group is BASEBALL DATA. PASS requires every one of them to be zero,
and a single non-zero value is a hard failure.

The second group is the lane's own completion ledger. ``_process_one_game``
claims a work item before fetching and completes it after persisting, whenever
writes are enabled, independently of whether the plan mutates anything. Those
writes are therefore unavoidable on the canonical path. They are NOT reported as
zero and NOT hidden: they are carried in their own labelled group with their
real values, and the artifact states plainly that the lane ledger advanced while
no baseball data changed.

Making them zero would require either bypassing the canonical writer or changing
canonical completion semantics. Both are out of scope here, and both would cost
more safety than they buy.

Nothing in this module authorizes scheduled writes, automated writes,
authoritative publication, backfill, or any future mutation. A fingerprint is
evidence of what a plan was, never a token that permits a later write.
"""

from __future__ import annotations

import hashlib
import re

from models.game_log import GameLog
from models.pitcher import Pitcher
from services import game_driven_ingestion as lane
from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as pitcher_identity


SCHEMA_VERSION = '1'
QUALIFICATION_TYPE = 'manual_game_driven_noop_write_qualification'

RESULT_PASS = 'PASS'
RESULT_FAILED = 'FAILED'
RESULT_UNPROVEN = 'UNPROVEN'

EXIT_PASS = 0
EXIT_FAILED = 1
EXIT_UNPROVEN = 2

EXIT_CODES = {
    RESULT_PASS: EXIT_PASS,
    RESULT_FAILED: EXIT_FAILED,
    RESULT_UNPROVEN: EXIT_UNPROVEN,
}

# ── Authorization constants ─────────────────────────────────────────────────
REQUIRED_REPOSITORY = 'NickolisK24/bullpen-intel-engine'
REQUIRED_REF = 'refs/heads/main'
REQUIRED_EVENT_NAME = 'workflow_dispatch'
REQUIRED_ACTOR = 'NickolisK24'
CONFIRMATION_PREFIX = 'QUALIFY_NOOP_GAME_'

_SHA_PATTERN = re.compile(r'\A[0-9a-f]{40}\Z')
_GAME_PK_PATTERN = re.compile(r'\A[0-9]+\Z')

NON_AUTHORIZATION_STATEMENT = (
    'This qualification does not authorize scheduled writes, automated '
    'writes, authoritative publication, backfill, or future mutations.'
)

# ── Reason codes ────────────────────────────────────────────────────────────
# FAILED: a definite contract violation was observed.
FAILED_EVENT_NOT_WORKFLOW_DISPATCH = 'event_not_workflow_dispatch'
FAILED_REPOSITORY_NOT_AUTHORIZED = 'repository_not_authorized'
FAILED_ACTOR_NOT_AUTHORIZED = 'actor_not_authorized'
FAILED_REF_NOT_MAIN = 'ref_not_main'
FAILED_EXPECTED_SHA_MALFORMED = 'expected_head_sha_malformed'
FAILED_EXPECTED_SHA_MISMATCH = 'expected_head_sha_mismatch'
FAILED_CONFIRMATION_MISMATCH = 'confirmation_mismatch'
FAILED_GAME_PK_EMPTY = 'game_pk_empty'
FAILED_GAME_PK_NOT_AN_INTEGER = 'game_pk_not_a_single_integer'
FAILED_GAME_PK_NOT_POSITIVE = 'game_pk_not_positive'
FAILED_GAME_NOT_PLANNABLE = 'requested_game_not_plannable_or_not_final'
FAILED_SCOPE_NOT_EXACT = 'execution_scope_not_exact'
FAILED_REQUESTED_COUNT_NOT_ONE = 'requested_game_count_not_one'
FAILED_PLANNED_COUNT_NOT_ONE = 'planned_game_count_not_one'
FAILED_FETCHED_COUNT_NOT_ONE = 'fetched_game_count_not_one'
FAILED_COMPLETED_COUNT_NOT_ONE = 'completed_game_count_not_one'
FAILED_DUPLICATE_REQUESTED_GAME = 'duplicate_requested_game'
FAILED_UNEXPECTED_PLANNED_GAME = 'unexpected_planned_game'
FAILED_MISSING_REQUESTED_GAME = 'missing_requested_game'
FAILED_PLAN_PROPOSES_MUTATION = 'plan_proposes_mutation'
FAILED_PLAN_UNKNOWN_ACTION = 'plan_contains_unknown_action'
FAILED_PROHIBITED_IDENTITY_ACTION = 'plan_proposes_identity_mutation'
FAILED_SOURCE_REVISION_CHANGED = 'source_revision_changed_before_execution'
FAILED_PLAN_FINGERPRINT_CHANGED = 'plan_fingerprint_changed_before_execution'
FAILED_BASEBALL_DATA_MUTATED = 'baseball_data_mutation_detected'
FAILED_STATE_DIGEST_MISMATCH = 'before_after_state_digest_mismatch'
FAILED_REALIZATION_UNRESOLVED = 'realization_reported_unresolved_rows'
FAILED_PUBLICATION_AUTHORITATIVE = 'publication_authoritative_enabled'
FAILED_WRITES_NOT_ENABLED = 'write_capable_path_not_entered'
FAILED_LANE_STATUS_NOT_COMPLETE = 'lane_run_did_not_complete'
FAILED_ARTIFACT_FORBIDDEN_CONTENT = 'artifact_forbidden_content_detected'

# UNPROVEN: trustworthy evidence could not be completed.
UNPROVEN_PRE_READBACK_UNAVAILABLE = 'pre_execution_readback_unavailable'
UNPROVEN_POST_READBACK_UNAVAILABLE = 'post_execution_readback_unavailable'
UNPROVEN_REALIZATION_UNAVAILABLE = 'realization_unavailable'
UNPROVEN_SOURCE_REVISION_MISSING = 'source_revision_missing'
UNPROVEN_PLAN_FINGERPRINT_MISSING = 'plan_fingerprint_missing'
UNPROVEN_EFFECT_COUNTERS_MISSING = 'execution_effect_counters_incomplete'
UNPROVEN_WRITER_GUARD_UNAVAILABLE = 'writer_guard_unavailable'
UNPROVEN_SHADOW_PHASE_UNUSABLE = 'shadow_phase_produced_no_usable_plan'
UNPROVEN_ARTIFACT_SCAN_UNAVAILABLE = 'artifact_scan_unavailable'
UNPROVEN_ARTIFACT_BUILD_FAILED = 'artifact_construction_failed'
UNPROVEN_LANE_ERROR = 'lane_execution_error'

# ── Effect groups ───────────────────────────────────────────────────────────
# Baseball data. Every one of these MUST be zero for PASS.
BASEBALL_DATA_EFFECT_FIELDS = (
    'game_log_rows_written',
    'pitcher_rows_written',
    'appearance_team_rows_written',
    'correction_provenance_rows_written',
    'dead_letters_created',
)

# The lane's own completion ledger. Reported with real values, never zeroed and
# never suppressed. See the module docstring for why these cannot be zero on the
# canonical path.
LANE_BOOKKEEPING_EFFECT_FIELDS = (
    'work_items_created',
    'work_items_updated',
    'work_items_completed',
    'checkpoints_advanced',
    'commits_performed',
)

REQUIRED_EFFECT_FIELDS = (
    ('writes_enabled', 'publication_authoritative')
    + BASEBALL_DATA_EFFECT_FIELDS
    + LANE_BOOKKEEPING_EFFECT_FIELDS
)

# Plan-level counters that must all be zero for a genuine no-op.
PROJECTED_MUTATION_COUNTERS = (
    'rows_inserted',
    'rows_updated',
    'rows_blocked',
    'statistical_corrections',
    'authority_reconciliations',
    'provenance_only_updates',
    'canonical_outs_corrections',
    'pitcher_identity_mutations',
    'pitcher_identity_creations',
    'pitcher_identity_reactivations',
    'pitcher_identity_metadata_updates',
    'pitcher_identity_blocked',
    'appearance_team_mutations',
    'complete_mutation_count',
)

KNOWN_ACTIONS = frozenset({
    reconciliation.ACTION_UNCHANGED,
    reconciliation.ACTION_INSERT,
    reconciliation.ACTION_UPDATE,
    reconciliation.ACTION_BLOCKED,
})

# The only row action a no-op qualification may contain.
PERMITTED_ACTIONS = frozenset({reconciliation.ACTION_UNCHANGED})

# The only identity decisions a no-op qualification may contain. Creation and
# reactivation are identity MUTATIONS and are refused here even though D-009
# permits them in a normal governed run.
PERMITTED_IDENTITY_ACTIONS = frozenset({
    pitcher_identity.ACTION_UNCHANGED,
    None,
})

# Canonical governed field vocabulary, reused rather than redeclared, so the
# before/after digest compares exactly the fields the reconciliation contract
# governs. Provenance and derived companions are excluded by construction:
# a provenance timestamp moving is not a baseball change, and a decimal
# companion difference is never a baseball repair (D-008).
STATE_DIGEST_FIELDS = tuple(sorted(
    set(
        reconciliation.STATISTICAL_FIELDS
        + reconciliation.ROLE_SIGNAL_FIELDS
        + reconciliation.APPEARANCE_TEAM_FIELDS
    )
    - set(reconciliation.PROVENANCE_FIELDS)
    # ``innings_pitched`` is a derived decimal companion of the integer
    # authority ``innings_pitched_outs`` (D-008). Digesting it would let a
    # representation difference read as a state change, which is precisely the
    # class of false positive the innings semantics contract exists to prevent.
    - set(reconciliation.DERIVED_COMPANION_FIELDS)
))


class QualificationInputError(ValueError):
    """A supplied operator input is not usable. Carries a safe reason code."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


# ── Input parsing ───────────────────────────────────────────────────────────


def parse_game_pk(raw) -> int:
    """Parse exactly one positive integer game id.

    Deliberately strict: a list, a range, a date, a wildcard, or anything with
    separators is refused rather than reinterpreted. "Exactly one game" is the
    entire safety property, so it is enforced at the narrowest possible point.
    """
    if raw is None:
        raise QualificationInputError(FAILED_GAME_PK_EMPTY)
    text = str(raw).strip()
    if not text:
        raise QualificationInputError(FAILED_GAME_PK_EMPTY)
    if not _GAME_PK_PATTERN.match(text):
        raise QualificationInputError(FAILED_GAME_PK_NOT_AN_INTEGER)
    value = int(text)
    if value <= 0:
        raise QualificationInputError(FAILED_GAME_PK_NOT_POSITIVE)
    return value


def expected_confirmation(game_pk) -> str:
    return f'{CONFIRMATION_PREFIX}{int(game_pk)}'


def normalize_sha(raw) -> str:
    return str(raw or '').strip().lower()


# ── Authorization ───────────────────────────────────────────────────────────


def validate_authorization(context, *, game_pk) -> list[str]:
    """Return every authorization reason code that failed.

    Every condition is evaluated rather than short-circuiting, so the artifact
    records all of them instead of only the first.
    """
    failures: list[str] = []

    if str(context.get('event_name') or '') != REQUIRED_EVENT_NAME:
        failures.append(FAILED_EVENT_NOT_WORKFLOW_DISPATCH)
    if str(context.get('repository') or '') != REQUIRED_REPOSITORY:
        failures.append(FAILED_REPOSITORY_NOT_AUTHORIZED)
    if str(context.get('actor') or '') != REQUIRED_ACTOR:
        failures.append(FAILED_ACTOR_NOT_AUTHORIZED)
    if str(context.get('ref') or '') != REQUIRED_REF:
        failures.append(FAILED_REF_NOT_MAIN)

    expected_sha = normalize_sha(context.get('expected_head_sha'))
    actual_sha = normalize_sha(context.get('github_sha'))
    if not _SHA_PATTERN.match(expected_sha):
        failures.append(FAILED_EXPECTED_SHA_MALFORMED)
    elif not _SHA_PATTERN.match(actual_sha) or expected_sha != actual_sha:
        failures.append(FAILED_EXPECTED_SHA_MISMATCH)

    supplied = str(context.get('confirmation') or '')
    if supplied != expected_confirmation(game_pk):
        failures.append(FAILED_CONFIRMATION_MISMATCH)

    return failures


def sanitize_note(raw, *, limit=280) -> str:
    """Reduce a free-text operator note to a safe, bounded token set.

    The note never affects authorization. It is reported, so it is stripped to
    characters that cannot carry a credential, URL, path, or header.
    """
    text = str(raw or '')
    kept = re.sub(r'[^A-Za-z0-9 .,_-]', ' ', text)
    return re.sub(r'\s+', ' ', kept).strip()[:limit]


# ── Plan governance ─────────────────────────────────────────────────────────


def plan_rows(report) -> list[dict]:
    return [
        row
        for game in (report.get('games') or ())
        for row in (game.get('rows') or ())
    ]


def evaluate_plan_governance(report) -> dict:
    """Classify every planned row. Any proposed mutation is a refusal.

    A row is acceptable only when the canonical planner said ``unchanged`` and
    proposed no identity decision beyond ``unchanged``. Anything else — an
    insert, an update, a delete, a block, an outs correction, a team
    reassignment, an identity creation, or an action this contract does not
    recognise — is counted as prohibited.
    """
    rows = plan_rows(report)
    action_counts: dict[str, int] = {}
    identity_action_counts: dict[str, int] = {}
    prohibited: dict[str, int] = {}
    unknown_actions = 0

    for row in rows:
        action = row.get('action')
        key = str(action)
        action_counts[key] = action_counts.get(key, 0) + 1
        if action not in KNOWN_ACTIONS:
            unknown_actions += 1
            prohibited[f'unknown_action:{key}'] = (
                prohibited.get(f'unknown_action:{key}', 0) + 1
            )
        elif action not in PERMITTED_ACTIONS:
            prohibited[f'action:{key}'] = prohibited.get(f'action:{key}', 0) + 1

        identity_action = row.get('pitcher_identity_action')
        identity_key = str(identity_action)
        identity_action_counts[identity_key] = (
            identity_action_counts.get(identity_key, 0) + 1
        )
        if identity_action not in PERMITTED_IDENTITY_ACTIONS:
            prohibited[f'identity:{identity_key}'] = (
                prohibited.get(f'identity:{identity_key}', 0) + 1
            )

        # A row the planner called unchanged must also carry no changed field.
        # Belt and braces: the action and the field list are produced by the
        # same planner, so disagreement between them is itself a defect.
        if row.get('changed_fields'):
            prohibited['changed_fields_on_unchanged_row'] = (
                prohibited.get('changed_fields_on_unchanged_row', 0) + 1
            )

    counters = {
        field: _as_int(report.get(field))
        for field in PROJECTED_MUTATION_COUNTERS
    }
    nonzero_counters = {
        field: value for field, value in counters.items() if value != 0
    }

    return {
        'planned_row_count': len(rows),
        'planned_unchanged_count': action_counts.get(
            reconciliation.ACTION_UNCHANGED, 0
        ),
        'planned_action_counts': dict(sorted(action_counts.items())),
        'planned_identity_action_counts': dict(
            sorted(identity_action_counts.items())
        ),
        'planned_mutation_counters': dict(sorted(counters.items())),
        'nonzero_mutation_counters': dict(sorted(nonzero_counters.items())),
        'prohibited_action_counts': dict(sorted(prohibited.items())),
        'prohibited_actions': sum(prohibited.values()),
        'unknown_action_count': unknown_actions,
        'all_rows_already_matching': bool(
            rows
            and not prohibited
            and not nonzero_counters
            and len(rows) == action_counts.get(reconciliation.ACTION_UNCHANGED, 0)
        ),
    }


def evaluate_scope(report, *, game_pk) -> dict:
    """Prove requested scope is exactly the one requested game."""
    requested = [_as_int(value) for value in (report.get('requested_game_pks') or ())]
    planned = [_as_int(value) for value in (report.get('planned_game_pks') or ())]
    unexpected = [
        _as_int(value) for value in (report.get('unexpected_planned_game_pks') or ())
    ]
    missing = [
        _as_int(value) for value in (report.get('missing_requested_game_pks') or ())
    ]
    return {
        'requested_game_pks': requested,
        'requested_game_count': len(requested),
        'planned_game_pks': planned,
        'planned_game_count': len(planned),
        # Fetch OPERATIONS, not distinct games. An authorized exclusive write
        # legitimately fetches the same single game twice: once to recompute the
        # plan for the reviewed-fingerprint comparison, and once to execute it.
        # Requiring one operation here would refuse the very drift re-validation
        # the contract asks for, so the count is reported and the distinct-game
        # property is asserted separately.
        'fetch_operations': _as_int(report.get('games_fetched')),
        'games_attempted': _as_int(report.get('games_attempted')),
        'distinct_games_fetched': len(planned),
        'games_completed': _as_int(report.get('games_completed')),
        'duplicate_requested_count': _as_int(
            report.get('duplicate_requested_count')
        ),
        'unexpected_planned_game_pks': unexpected,
        'missing_requested_game_pks': missing,
        'execution_scope_mode': report.get('execution_scope_mode'),
        'execution_scope_exact_match': bool(
            report.get('execution_scope_exact_match')
        ),
        'requested_is_exactly_target': requested == [int(game_pk)],
        'planned_is_exactly_target': planned == [int(game_pk)],
    }


def source_revisions(report) -> list[dict]:
    return [
        {
            'game_pk': _as_int(game.get('game_pk')),
            'source_revision': game.get('source_revision'),
        }
        for game in (report.get('games') or ())
    ]


# ── Canonical state readback ────────────────────────────────────────────────


def read_canonical_state(rows) -> dict | None:
    """Read stored canonical state for exactly the planned rows.

    Returns ``None`` when the read cannot be completed — the caller turns that
    into UNPROVEN rather than assuming the state was unchanged.
    """
    try:
        mlb_ids = sorted({
            row.get('pitcher_mlb_id') for row in rows
            if row.get('pitcher_mlb_id') is not None
        })
        game_pks = sorted({
            row.get('game_pk') for row in rows
            if row.get('game_pk') is not None
        })
        if not mlb_ids or not game_pks:
            return None

        local_ids = {
            pitcher.mlb_id: pitcher.id
            for pitcher in Pitcher.query.filter(Pitcher.mlb_id.in_(mlb_ids)).all()
        }
        stored: dict = {}
        for record in GameLog.query.filter(
            GameLog.mlb_game_pk.in_(game_pks)
        ).all():
            stored.setdefault((record.pitcher_id, record.mlb_game_pk), []).append(
                record
            )

        entries = []
        for row in rows:
            local_id = local_ids.get(row.get('pitcher_mlb_id'))
            matches = stored.get((local_id, row.get('game_pk'))) or []
            entries.append((
                _as_int(row.get('game_pk')),
                _as_int(row.get('pitcher_mlb_id')),
                len(matches),
                # Canonical digest helper over the canonical field vocabulary.
                reconciliation.stored_state_digest(
                    matches[0], STATE_DIGEST_FIELDS
                ) if len(matches) == 1 else '',
            ))

        return {
            'available': True,
            'row_count': sum(entry[2] for entry in entries),
            'identity_count': len([
                mlb_id for mlb_id in mlb_ids if local_ids.get(mlb_id) is not None
            ]),
            'projected_row_count': len(rows),
            'digest': _digest_entries(entries),
        }
    except Exception:  # noqa: BLE001 - a failed read is UNPROVEN, never PASS
        return None


def _digest_entries(entries) -> str:
    encoded = '|'.join(
        f'{game_pk}:{pitcher_mlb_id}:{count}:{digest}'
        for game_pk, pitcher_mlb_id, count, digest in sorted(entries)
    )
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


# ── Execution effects ───────────────────────────────────────────────────────


def split_execution_effects(report) -> dict:
    """Separate baseball-data effects from lane bookkeeping.

    Both groups carry their real measured values. Nothing is zeroed to make a
    verdict reachable — the split exists so the artifact can state which kind of
    write happened, not so one kind can be ignored.
    """
    effects = report.get('execution_effects')
    if not isinstance(effects, dict):
        return {
            'available': False,
            'missing_fields': list(REQUIRED_EFFECT_FIELDS),
            'baseball_data': {},
            'lane_bookkeeping': {},
            'baseball_data_total': None,
        }

    missing = [
        field for field in REQUIRED_EFFECT_FIELDS if field not in effects
    ]
    baseball = {
        field: _as_int(effects.get(field))
        for field in BASEBALL_DATA_EFFECT_FIELDS
    }
    bookkeeping = {
        field: _as_int(effects.get(field))
        for field in LANE_BOOKKEEPING_EFFECT_FIELDS
    }
    return {
        'available': not missing,
        'missing_fields': missing,
        'writes_enabled': bool(effects.get('writes_enabled')),
        'publication_authoritative': bool(
            effects.get('publication_authoritative')
        ),
        'baseball_data': baseball,
        'lane_bookkeeping': bookkeeping,
        'baseball_data_total': sum(baseball.values()),
        'transaction_boundary_entered': _as_int(
            effects.get('commits_performed')
        ) > 0,
        'baseball_row_mutation_performed': sum(baseball.values()) > 0,
    }


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ── Verdict ─────────────────────────────────────────────────────────────────


def decide(evidence) -> dict:
    """Reduce collected evidence to PASS, FAILED, or UNPROVEN.

    FAILED outranks UNPROVEN: an observed violation is a stronger statement than
    absent evidence, and reporting it as merely unproven would understate it.
    PASS is reachable only when every contract condition was positively
    observed — never because nothing raised.
    """
    failed = list(evidence.get('failed_reasons') or ())
    unproven = list(evidence.get('unproven_reasons') or ())

    if failed:
        result = RESULT_FAILED
    elif unproven:
        result = RESULT_UNPROVEN
    else:
        result = RESULT_PASS

    return {
        'result': result,
        'exit_code': EXIT_CODES[result],
        'failed_reasons': sorted(set(failed)),
        'unproven_reasons': sorted(set(unproven)),
        'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
    }


def assess(*, context, game_pk, shadow_report, write_report,
           before_state, after_state, realization, artifact_scan=None) -> dict:
    """Apply the full no-op contract to the collected evidence.

    Pure: takes reports and readbacks, returns reason codes. Every condition in
    the contract is checked here in one place so the failure matrix can be
    executed by tests rather than described in prose.
    """
    failed: list[str] = []
    unproven: list[str] = []

    failed.extend(validate_authorization(context, game_pk=game_pk))

    shadow_report = shadow_report or {}
    write_report = write_report or {}

    # ── Scope, proven on the phase that actually executed ────────────────────
    scope = evaluate_scope(write_report, game_pk=game_pk)
    shadow_scope = evaluate_scope(shadow_report, game_pk=game_pk)

    if shadow_scope['planned_game_count'] == 0:
        failed.append(FAILED_GAME_NOT_PLANNABLE)
    if scope['duplicate_requested_count'] or shadow_scope['duplicate_requested_count']:
        failed.append(FAILED_DUPLICATE_REQUESTED_GAME)
    if not scope['requested_is_exactly_target']:
        failed.append(FAILED_REQUESTED_COUNT_NOT_ONE)
    if scope['planned_game_count'] != 1:
        failed.append(FAILED_PLANNED_COUNT_NOT_ONE)
    elif not scope['planned_is_exactly_target']:
        failed.append(FAILED_UNEXPECTED_PLANNED_GAME)
    if scope['unexpected_planned_game_pks']:
        failed.append(FAILED_UNEXPECTED_PLANNED_GAME)
    if scope['missing_requested_game_pks']:
        failed.append(FAILED_MISSING_REQUESTED_GAME)
    if not scope['execution_scope_exact_match']:
        failed.append(FAILED_SCOPE_NOT_EXACT)
    if scope['distinct_games_fetched'] != 1 or scope['games_attempted'] != 1:
        failed.append(FAILED_FETCHED_COUNT_NOT_ONE)
    if scope['games_completed'] != 1:
        failed.append(FAILED_COMPLETED_COUNT_NOT_ONE)

    # ── Lane refusal statuses map to their specific causes ───────────────────
    write_status = write_report.get('status')
    if write_status == lane.STATUS_PLAN_FINGERPRINT_MISMATCH:
        failed.append(FAILED_PLAN_FINGERPRINT_CHANGED)
    elif write_status in (
        lane.STATUS_SCOPE_MISMATCH, lane.STATUS_SCOPE_INVALID,
    ):
        failed.append(FAILED_SCOPE_NOT_EXACT)
    elif write_status == lane.STATUS_PLAN_AUTHORIZATION_REQUIRED:
        unproven.append(UNPROVEN_PLAN_FINGERPRINT_MISSING)
    elif write_status != 'complete':
        failed.append(FAILED_LANE_STATUS_NOT_COMPLETE)

    # ── Plan governance, evaluated on both phases ────────────────────────────
    shadow_governance = evaluate_plan_governance(shadow_report)
    write_governance = evaluate_plan_governance(write_report)

    if not shadow_governance['planned_row_count']:
        unproven.append(UNPROVEN_SHADOW_PHASE_UNUSABLE)
    for governance in (shadow_governance, write_governance):
        if governance['unknown_action_count']:
            failed.append(FAILED_PLAN_UNKNOWN_ACTION)
        if any(
            key.startswith('identity:')
            for key in governance['prohibited_action_counts']
        ):
            failed.append(FAILED_PROHIBITED_IDENTITY_ACTION)
        if governance['planned_row_count'] and not governance[
            'all_rows_already_matching'
        ]:
            failed.append(FAILED_PLAN_PROPOSES_MUTATION)

    # ── Fingerprints and source revisions ───────────────────────────────────
    shadow_fingerprint = shadow_report.get('reconciliation_plan_fingerprint')
    authorized_fingerprint = write_report.get('authorized_plan_fingerprint')
    if not shadow_fingerprint:
        unproven.append(UNPROVEN_PLAN_FINGERPRINT_MISSING)

    shadow_revisions = source_revisions(shadow_report)
    write_revisions = source_revisions(write_report)
    if not shadow_revisions or any(
        entry['source_revision'] is None for entry in shadow_revisions
    ):
        unproven.append(UNPROVEN_SOURCE_REVISION_MISSING)
    elif write_revisions:
        before = {e['game_pk']: e['source_revision'] for e in shadow_revisions}
        after = {e['game_pk']: e['source_revision'] for e in write_revisions}
        if any(
            after.get(game) != revision for game, revision in before.items()
        ):
            failed.append(FAILED_SOURCE_REVISION_CHANGED)

    # ── Execution effects ───────────────────────────────────────────────────
    effects = split_execution_effects(write_report)
    if not effects['available']:
        unproven.append(UNPROVEN_EFFECT_COUNTERS_MISSING)
    else:
        if effects['baseball_data_total'] > 0:
            failed.append(FAILED_BASEBALL_DATA_MUTATED)
        if not effects['writes_enabled']:
            failed.append(FAILED_WRITES_NOT_ENABLED)
        if effects['publication_authoritative']:
            failed.append(FAILED_PUBLICATION_AUTHORITATIVE)

    # ── Before / after state ────────────────────────────────────────────────
    if not before_state or not before_state.get('available'):
        unproven.append(UNPROVEN_PRE_READBACK_UNAVAILABLE)
    if not after_state or not after_state.get('available'):
        unproven.append(UNPROVEN_POST_READBACK_UNAVAILABLE)
    if (
        before_state and after_state
        and before_state.get('available') and after_state.get('available')
        and before_state.get('digest') != after_state.get('digest')
    ):
        failed.append(FAILED_STATE_DIGEST_MISMATCH)

    # ── Realization ─────────────────────────────────────────────────────────
    if not realization or not realization.get('applicable'):
        unproven.append(UNPROVEN_REALIZATION_UNAVAILABLE)
    else:
        if _as_int(realization.get('unresolved_rows')):
            failed.append(FAILED_REALIZATION_UNRESOLVED)
        for field in ('divergent_rows', 'missing_rows', 'duplicate_rows'):
            if _as_int(realization.get(field)):
                failed.append(FAILED_REALIZATION_UNRESOLVED)
        if _as_int(realization.get('prohibited_identity_actions')):
            failed.append(FAILED_PROHIBITED_IDENTITY_ACTION)
        if not realization.get('all_projected_targets_realized'):
            failed.append(FAILED_REALIZATION_UNRESOLVED)

    # ── Artifact safety ─────────────────────────────────────────────────────
    if artifact_scan is not None:
        if not artifact_scan.get('available'):
            unproven.append(UNPROVEN_ARTIFACT_SCAN_UNAVAILABLE)
        elif not artifact_scan.get('safe'):
            failed.append(FAILED_ARTIFACT_FORBIDDEN_CONTENT)

    decision = decide({
        'failed_reasons': failed,
        'unproven_reasons': unproven,
    })
    decision['scope'] = scope
    decision['shadow_scope'] = shadow_scope
    decision['shadow_plan'] = shadow_governance
    decision['write_plan'] = write_governance
    decision['execution_effects'] = effects
    decision['shadow_plan_fingerprint'] = shadow_fingerprint
    decision['authorized_plan_fingerprint'] = authorized_fingerprint
    decision['plan_fingerprint_match'] = bool(
        shadow_fingerprint
        and authorized_fingerprint
        and shadow_fingerprint == authorized_fingerprint
    )
    decision['source_revisions_before'] = shadow_revisions
    decision['source_revisions_before_execution'] = write_revisions
    decision['source_revision_match'] = (
        FAILED_SOURCE_REVISION_CHANGED not in failed
    )
    decision['before_state'] = before_state or {'available': False}
    decision['after_state'] = after_state or {'available': False}
    decision['state_digest_match'] = (
        bool(before_state) and bool(after_state)
        and bool(before_state.get('available'))
        and bool(after_state.get('available'))
        and before_state.get('digest') == after_state.get('digest')
    )
    return decision
