#!/usr/bin/env python
"""Validate a Foundation 3C Stage R2 full-window shadow report. Fails closed.

R1 proved the D-008 innings repair against the five games the first controlled
write already reconciled. R2 asks the harder question: does the decimal-innings
regression stay dead across the COMPLETE governed window, and is anything still
outstanding there safe enough for a human to review?

Three outcomes, not two:

    pass             the whole governed window already reconciles; nothing to do
    review_required  the run was safe and some legitimate corrections remain
    failed           a foundational invariant broke; the rollout stops

``review_required`` is a successful evidence-gathering run and NOTHING MORE. It
authorizes no write. R3/R4 stay blocked until the update manifest is reviewed by
a human, so the validator deliberately cannot be configured to approve one.

The canonical vocabulary — which fields exist, what category each belongs to,
which field is a derived companion of which authority — is imported from
``services.game_log_reconciliation`` rather than restated here. A second list
would drift from the planner it is supposed to be checking. The single
exception is stated explicitly below: ``innings_pitched`` is a legitimate
member of the canonical statistical vocabulary, so the registry alone would
accept it as a semantic correction. R2 refuses it by name.

Output carries only safe structured values — counts, game ids, pitcher MLB ids,
governed field names, and the named invariant that failed. No payload, path,
credential, connection string, header, or exception text reaches it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services import game_log_reconciliation as reconciliation  # noqa: E402
from services import pitcher_identity_reconciliation as identity  # noqa: E402


EXIT_OK = 0
EXIT_FAILED = 1

RESULT_PASS = 'pass'
RESULT_REVIEW_REQUIRED = 'review_required'
RESULT_FAILED = 'failed'

REFERENCE_DATE = '2026-07-29'
EXPECTED_MODE = 'shadow'
EXPECTED_STATUS = 'complete'
EXPECTED_SCOPE_MODE = 'window'
EXPECTED_GAME_STATUS = 'projected'

# Taken from the merged planner so a version bump cannot silently pass an
# unrepaired report.
EXPECTED_INNINGS_SEMANTICS_VERSION = reconciliation.INNINGS_SEMANTICS_VERSION
EXPECTED_RECONCILIATION_PLAN_VERSION = reconciliation.RECONCILIATION_PLAN_VERSION
EXPECTED_PARITY_CONTRACT_VERSION = reconciliation.PARITY_CONTRACT_VERSION

# D-008. The decimal companion is derived from recorded outs and is never an
# independent official fact, so it may never appear as a SEMANTIC change — even
# though it is a real member of the canonical statistical field vocabulary and
# the category registry alone would happily accept it.
PROHIBITED_SEMANTIC_FIELDS = frozenset(reconciliation.DERIVED_COMPANION_FIELDS)

SEMANTIC_AUTHORITY_BY_COMPANION = dict(
    reconciliation.SEMANTIC_AUTHORITY_BY_COMPANION
)
AUTHORITY_FIELDS = frozenset(SEMANTIC_AUTHORITY_BY_COMPANION.values())

CATEGORY_PROVENANCE_ONLY = reconciliation.CATEGORY_PROVENANCE_ONLY
CATEGORY_BLOCKED = reconciliation.CATEGORY_BLOCKED

ACTION_INSERT = reconciliation.ACTION_INSERT
ACTION_UPDATE = reconciliation.ACTION_UPDATE
ACTION_UNCHANGED = reconciliation.ACTION_UNCHANGED
ACTION_BLOCKED = reconciliation.ACTION_BLOCKED

MAX_SUMMARY_UPDATE_EXAMPLES = 10

# ── Pitcher identity (D-009) ────────────────────────────────────────────────
# The retired completed-game write actions. Seeing any of them means the report
# came from unrepaired code, which is a stop rather than something to review.
RETIRED_IDENTITY_ACTIONS = frozenset(identity.RETIRED_WRITE_ACTIONS)
KNOWN_IDENTITY_ACTIONS = frozenset(identity.ACTIONS)
# The only identity action a human may be asked to review. Everything else that
# would write is a rollout stop.
REVIEWABLE_IDENTITY_ACTIONS = frozenset({
    identity.ACTION_CREATE_MINIMAL_IDENTITY,
})
CURRENT_STATE_AUTHORITY_FIELDS = frozenset(
    identity.CURRENT_STATE_AUTHORITY_FIELDS
)
ALLOWED_IDENTITY_CHANGED_FIELDS = frozenset(identity.MINIMAL_CREATION_FIELDS)

MUTATION_TARGET_GAME_LOG = 'game_log'
MUTATION_TARGET_IDENTITY = 'pitcher_identity'
MUTATION_TARGET_APPEARANCE_TEAM = 'appearance_team'
MUTATION_TARGET_ORDER = {
    MUTATION_TARGET_APPEARANCE_TEAM: 0,
    MUTATION_TARGET_GAME_LOG: 1,
    MUTATION_TARGET_IDENTITY: 2,
}


class ValidationFailure(Exception):
    """One named invariant did not hold. R2 stops here."""

    def __init__(self, invariant, expected, observed):
        super().__init__(invariant)
        self.invariant = invariant
        self.expected = expected
        self.observed = observed


def _require(invariant, expected, observed):
    if observed != expected:
        raise ValidationFailure(invariant, expected, observed)


def _require_true(invariant, observed):
    _require(invariant, True, bool(observed))


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _require_nonneg_int(invariant, value):
    parsed = _int(value)
    if parsed is None or parsed < 0:
        raise ValidationFailure(invariant, 'a nonnegative integer', value)
    return parsed


# ── Top level ───────────────────────────────────────────────────────────────


def _validate_identity(report):
    _require('status', EXPECTED_STATUS, report.get('status'))
    _require('mode', EXPECTED_MODE, report.get('mode'))
    _require('reference_date', REFERENCE_DATE, report.get('reference_date'))
    _require(
        'innings_semantics_version', EXPECTED_INNINGS_SEMANTICS_VERSION,
        report.get('innings_semantics_version'),
    )
    _require(
        'reconciliation_plan_version', EXPECTED_RECONCILIATION_PLAN_VERSION,
        report.get('reconciliation_plan_version'),
    )
    _require(
        'parity_contract_version', EXPECTED_PARITY_CONTRACT_VERSION,
        report.get('parity_contract_version'),
    )


def _validate_scope(report):
    """R2 must be the normal governed window — not a bounded subset."""
    _require('execution_scope_mode', EXPECTED_SCOPE_MODE,
             report.get('execution_scope_mode'))
    _require('requested_game_pks_is_empty', [],
             list(report.get('requested_game_pks') or []))
    _require('requested_game_count', 0, report.get('requested_game_count'))
    _require_true('execution_scope_exact_match',
                  report.get('execution_scope_exact_match'))
    _require('unexpected_planned_game_pks', [],
             list(report.get('unexpected_planned_game_pks') or []))
    _require('missing_requested_game_pks', [],
             list(report.get('missing_requested_game_pks') or []))

    _require('duplicate_requested_count', 0,
             report.get('duplicate_requested_count'))

    discovered = _require_nonneg_int('games_discovered',
                                     report.get('games_discovered'))
    planned = _require_nonneg_int('games_planned', report.get('games_planned'))
    # A bounded subset (--max-games) would truncate the executing items while
    # the planner still reports the full plan. Requiring these to agree makes
    # R2 provably the complete governed window rather than a sample of it.
    _require('planned_game_count_equals_games_planned', planned,
             report.get('planned_game_count'))
    _require('planned_game_pks_count_equals_games_planned', planned,
             len(report.get('planned_game_pks') or []))
    if planned < 1:
        raise ValidationFailure('games_planned_is_positive', '>= 1', planned)
    if discovered < planned:
        raise ValidationFailure(
            'games_discovered_at_least_games_planned', f'>= {planned}', discovered,
        )

    for field in ('games_attempted', 'games_fetched', 'games_completed'):
        _require(f'{field}_equals_games_planned', planned, report.get(field))
    _require('games_failed', 0, report.get('games_failed'))
    _require('games_remaining', 0, report.get('games_remaining'))

    _require('budget_stop_triggered', False,
             bool(report.get('budget_stop_triggered')))
    _require('budget_stop_is_null', None, report.get('budget_stop'))

    _require('finality_conflicts', 0, report.get('finality_conflicts'))
    _require('schedule_authority_missing', 0,
             report.get('schedule_authority_missing'))
    _require('failure_classes_is_empty', {},
             dict(report.get('failure_classes') or {}))
    _require('critical_games_unresolved', 0,
             report.get('critical_games_unresolved'))
    return {'games_discovered': discovered, 'games_planned': planned}


def _validate_row_accounting(report):
    expected = _require_nonneg_int('rows_expected', report.get('rows_expected'))
    if expected < 1:
        raise ValidationFailure('rows_expected_is_positive', '>= 1', expected)

    inserted = _require_nonneg_int('rows_inserted', report.get('rows_inserted'))
    updated = _require_nonneg_int('rows_updated', report.get('rows_updated'))
    unchanged = _require_nonneg_int('rows_unchanged', report.get('rows_unchanged'))
    blocked = _require_nonneg_int('rows_blocked', report.get('rows_blocked'))

    # A projected insert means the window no longer matches the population the
    # earlier full-window shadow already found fully represented. That needs
    # separate investigation before any bootstrap write, so it is a stop rather
    # than a reviewable correction.
    _require('rows_inserted', 0, inserted)
    _require('rows_blocked', 0, blocked)

    total = inserted + updated + unchanged + blocked
    _require('rows_expected_equals_row_actions', expected, total)
    return {
        'rows_expected': expected,
        'rows_inserted': inserted,
        'rows_updated': updated,
        'rows_unchanged': unchanged,
        'rows_blocked': blocked,
    }


# ── Rows ────────────────────────────────────────────────────────────────────


def _validate_row(row, *, game_pk):
    """Every invariant that must hold for one projected appearance row."""
    pitcher = row.get('pitcher_mlb_id')
    label = f'{game_pk}_{pitcher}'

    if pitcher is None:
        raise ValidationFailure(
            f'row_{game_pk}_pitcher_mlb_id_present', 'an mlb id', None,
        )
    _require(f'row_{label}_game_pk_matches_game', game_pk, row.get('game_pk'))

    identity_facts = _validate_row_identity(row, label=label)

    action = row.get('action')
    if action not in (ACTION_UPDATE, ACTION_UNCHANGED):
        # insert and blocked are both rollout stops; anything else is unknown.
        raise ValidationFailure(
            f'row_{label}_action', f'{ACTION_UNCHANGED} or {ACTION_UPDATE}', action,
        )

    changed = list(row.get('changed_fields') or [])
    semantic = list(row.get('semantic_changed_fields') or [])
    applied = list(row.get('applied_changed_fields') or [])
    companions = list(row.get('derived_companion_fields') or [])
    ignored = list(row.get('derived_companion_differences_ignored') or [])
    categories = list(row.get('mutation_categories') or [])

    # ── D-008, asserted before anything else can excuse it ──────────────────
    for field in PROHIBITED_SEMANTIC_FIELDS:
        if field in changed:
            raise ValidationFailure(
                f'row_{label}_changed_fields_excludes_{field}', 'absent', field,
            )
        if field in semantic:
            raise ValidationFailure(
                f'row_{label}_semantic_changed_fields_excludes_{field}',
                'absent', field,
            )

    # A companion may be APPLIED only as a consequence of its authority moving.
    for companion in companions:
        authority = SEMANTIC_AUTHORITY_BY_COMPANION.get(companion)
        if authority is None:
            raise ValidationFailure(
                f'row_{label}_derived_companion_is_known', 'a known companion',
                companion,
            )
        if authority not in semantic:
            raise ValidationFailure(
                f'row_{label}_companion_{companion}_requires_{authority}',
                f'{authority} in semantic_changed_fields', semantic,
            )

    # An ignored representation difference is not a change and must never also
    # be presented as an applied one.
    overlap = sorted(set(ignored) & set(companions))
    _require(f'row_{label}_ignored_and_applied_are_disjoint', [], overlap)
    for field in ignored:
        if field not in SEMANTIC_AUTHORITY_BY_COMPANION:
            raise ValidationFailure(
                f'row_{label}_ignored_difference_is_a_known_companion',
                'a known companion', field,
            )

    if action == ACTION_UNCHANGED:
        _require(f'row_{label}_changed_field_count', 0,
                 row.get('changed_field_count'))
        _require(f'row_{label}_changed_fields', [], changed)
        _require(f'row_{label}_semantic_changed_fields', [], semantic)
        _require(f'row_{label}_applied_changed_fields', [], applied)
        _require(f'row_{label}_derived_companion_fields', [], companions)
        _require_true(f'row_{label}_governed_and_safe', row.get('governed_and_safe'))
        _require(f'row_{label}_blocked_reason', None, row.get('blocked_reason'))
        _require(f'row_{label}_affects_published_evidence', False,
                 bool(row.get('affects_published_evidence')))
        # Ignored decimal drift on an unchanged row is exactly what the repair
        # is supposed to produce, so it is allowed and counted, not failed.
        return _row_facts(row, action=action, ignored=ignored,
                          semantic=semantic, companions=companions,
                          identity_facts=identity_facts)

    # ── action == update ────────────────────────────────────────────────────
    if not semantic:
        raise ValidationFailure(
            f'row_{label}_update_has_a_semantic_change', '>= 1 semantic field', [],
        )
    _require(f'row_{label}_changed_fields_match_semantic', sorted(semantic),
             sorted(changed))
    _require(f'row_{label}_changed_field_count', len(semantic),
             row.get('changed_field_count'))
    _require(f'row_{label}_changed_fields_are_sorted', sorted(changed), changed)
    _require(f'row_{label}_semantic_changed_fields_are_sorted', sorted(semantic),
             semantic)
    _require(f'row_{label}_applied_changed_fields',
             sorted(set(semantic) | set(companions)), sorted(applied))
    _require_true(f'row_{label}_governed_and_safe', row.get('governed_and_safe'))
    _require(f'row_{label}_blocked_reason', None, row.get('blocked_reason'))

    # Every semantic field must be governed by the canonical registry. An
    # unknown field is a governance gap, not a correction to review.
    for field in semantic:
        category = reconciliation.field_category(field)
        if category == CATEGORY_BLOCKED:
            raise ValidationFailure(
                f'row_{label}_field_{field}_is_governed',
                'a known canonical category', category,
            )

    if not categories:
        raise ValidationFailure(
            f'row_{label}_has_a_mutation_category', '>= 1 category', [],
        )
    if CATEGORY_BLOCKED in categories:
        raise ValidationFailure(
            f'row_{label}_is_not_blocked', 'no unsafe_or_blocked_mutation',
            CATEGORY_BLOCKED,
        )

    digest = row.get('mutation_digest')
    if not digest:
        raise ValidationFailure(
            f'row_{label}_has_a_mutation_digest', 'a reviewed-value digest',
            digest,
        )

    is_provenance_only = bool(row.get('is_provenance_only'))
    if not bool(row.get('affects_published_evidence')) and not is_provenance_only:
        raise ValidationFailure(
            f'row_{label}_affects_published_evidence', True, False,
        )
    if is_provenance_only:
        # The only canonical category permitted to leave published evidence
        # untouched. It must not be claimed alongside a real correction.
        _require(
            f'row_{label}_provenance_only_categories',
            [CATEGORY_PROVENANCE_ONLY],
            [c for c in categories if c != reconciliation.CATEGORY_PITCHER_IDENTITY],
        )

    return _row_facts(row, action=action, ignored=ignored, semantic=semantic,
                      companions=companions, identity_facts=identity_facts)


def _validate_row_identity(row, *, label):
    """D-009 for one appearance row.

    A completed game may never plan a current-state write, so an identity
    mutation is never excused by the GameLog action being `unchanged` — that
    combination is exactly the hidden-mutation class this gate exists to catch.
    """
    action = row.get('pitcher_identity_action')
    if action is None:
        raise ValidationFailure(
            f'row_{label}_reports_a_pitcher_identity_action',
            'an identity action', None,
        )
    if action in RETIRED_IDENTITY_ACTIONS:
        raise ValidationFailure(
            f'row_{label}_pitcher_identity_action_is_retired',
            f'not one of {sorted(RETIRED_IDENTITY_ACTIONS)}', action,
        )
    if action not in KNOWN_IDENTITY_ACTIONS:
        raise ValidationFailure(
            f'row_{label}_pitcher_identity_action_is_known',
            sorted(KNOWN_IDENTITY_ACTIONS), action,
        )
    if action == identity.ACTION_BLOCKED:
        raise ValidationFailure(
            f'row_{label}_pitcher_identity_is_not_blocked',
            identity.ACTION_UNCHANGED, action,
        )

    changed = list(row.get('pitcher_identity_changed_fields') or [])
    applied = list(row.get('pitcher_identity_applied_fields') or [])
    suppressed = list(row.get('pitcher_identity_suppressed_fields') or [])
    is_creation = action == identity.ACTION_CREATE_MINIMAL_IDENTITY

    for field in set(changed) | set(applied):
        # A current-state field may appear only as part of a minimal creation,
        # where it is a neutral, unverified starting value rather than a
        # historical claim overwriting roster authority.
        if field in CURRENT_STATE_AUTHORITY_FIELDS and not is_creation:
            raise ValidationFailure(
                f'row_{label}_identity_never_writes_current_state_{field}',
                'absent', field,
            )
        if field not in ALLOWED_IDENTITY_CHANGED_FIELDS:
            raise ValidationFailure(
                f'row_{label}_identity_field_{field}_is_governed',
                sorted(ALLOWED_IDENTITY_CHANGED_FIELDS), field,
            )
    for field in suppressed:
        if field not in identity.KNOWN_IDENTITY_FIELDS:
            raise ValidationFailure(
                f'row_{label}_suppressed_identity_field_{field}_is_known',
                'a known identity field', field,
            )

    _require_true(
        f'row_{label}_identity_governed_and_safe',
        row.get('pitcher_identity_governed_and_safe', True),
    )
    _require(
        f'row_{label}_identity_blocked_reason', None,
        row.get('pitcher_identity_blocked_reason'),
    )

    if is_creation:
        if not changed:
            raise ValidationFailure(
                f'row_{label}_identity_creation_has_fields', '>= 1 field', [],
            )
        _require(f'row_{label}_identity_changed_fields_are_sorted',
                 sorted(changed), changed)
        if not row.get('pitcher_identity_mutation_digest'):
            raise ValidationFailure(
                f'row_{label}_identity_creation_has_a_digest',
                'a reviewed-value digest', '',
            )
    else:
        _require(f'row_{label}_identity_changed_fields', [], changed)
        _require(f'row_{label}_identity_applied_fields', [], applied)
        _require(
            f'row_{label}_identity_mutation_digest', '',
            row.get('pitcher_identity_mutation_digest') or '',
        )

    return {
        'action': action,
        'is_mutation': action in REVIEWABLE_IDENTITY_ACTIONS,
        'changed_fields': changed,
        'applied_fields': applied,
        'suppressed_fields': sorted(suppressed),
        'suppressed_any': bool(suppressed),
    }


def _row_facts(row, *, action, ignored, semantic, companions, identity_facts):
    return {
        'identity': identity_facts,
        'action': action,
        'ignored_companion_differences': bool(ignored),
        'is_canonical_outs_correction': any(
            field in AUTHORITY_FIELDS for field in semantic
        ),
        'applied_companion': bool(companions),
        'is_statistical_correction': bool(row.get('is_statistical_correction')),
        'is_authority_reconciliation': bool(row.get('appearance_team_reason')),
        'is_provenance_only': bool(row.get('is_provenance_only')),
        'semantic_changed_fields': list(semantic),
        'mutation_categories': list(row.get('mutation_categories') or []),
    }


# ── Games ───────────────────────────────────────────────────────────────────


def _validate_games(report, totals):
    games = list(report.get('games') or [])
    _require('per_game_result_count', report.get('games_planned'), len(games))

    seen_games = set()
    recomputed = {
        'inserted': 0, 'updated': 0, 'unchanged': 0, 'blocked': 0, 'rows': 0,
    }
    changed_field_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    counters = {
        'ignored_rows': 0, 'outs_corrections': 0, 'applied_companions': 0,
        'statistical': 0, 'authority': 0, 'provenance_only': 0,
        'identity_rows': 0, 'identity_mutations': 0, 'identity_unchanged': 0,
        'identity_suppressed_rows': 0,
    }
    identity_action_counts: dict[str, int] = {}
    identity_changed_field_counts: dict[str, int] = {}
    suppressed_field_counts: dict[str, int] = {}
    identity_pitchers: set = set()
    updated_rows = []
    identity_rows = []

    for game in games:
        game_pk = game.get('game_pk')
        if game_pk is None:
            raise ValidationFailure('game_pk_present', 'a game id', None)
        if game_pk in seen_games:
            raise ValidationFailure('game_appears_once', 'unique game ids', game_pk)
        seen_games.add(game_pk)

        _require(f'game_{game_pk}_status', EXPECTED_GAME_STATUS, game.get('status'))
        _require(f'game_{game_pk}_error_class', None, game.get('error_class'))
        _require(f'game_{game_pk}_inserted', 0, game.get('inserted'))
        _require(f'game_{game_pk}_blocked', 0, game.get('blocked'))

        rows = list(game.get('rows') or [])
        extracted = _require_nonneg_int(
            f'game_{game_pk}_appearances_extracted',
            game.get('appearances_extracted'),
        )
        _require(f'game_{game_pk}_row_count_matches_appearances', extracted,
                 len(rows))
        if extracted < 1:
            raise ValidationFailure(
                f'game_{game_pk}_has_appearances', '>= 1', extracted,
            )

        game_actions = {
            ACTION_INSERT: 0, ACTION_UPDATE: 0,
            ACTION_UNCHANGED: 0, ACTION_BLOCKED: 0,
        }
        game_ignored = 0
        game_outs = 0
        game_applied = 0
        seen_rows = set()
        for row in rows:
            facts = _validate_row(row, game_pk=game_pk)
            key = (game_pk, row.get('pitcher_mlb_id'))
            if key in seen_rows:
                raise ValidationFailure(
                    f'game_{game_pk}_row_appears_once', 'unique pitcher ids',
                    row.get('pitcher_mlb_id'),
                )
            seen_rows.add(key)

            game_actions[facts['action']] += 1
            for field in row.get('changed_fields') or ():
                changed_field_counts[field] = changed_field_counts.get(field, 0) + 1
            for category in row.get('mutation_categories') or ():
                category_counts[category] = category_counts.get(category, 0) + 1
            if facts['ignored_companion_differences']:
                game_ignored += 1
                counters['ignored_rows'] += 1
            if facts['is_canonical_outs_correction']:
                game_outs += 1
                counters['outs_corrections'] += 1
            if facts['applied_companion']:
                game_applied += 1
                counters['applied_companions'] += 1
            if facts['is_statistical_correction']:
                counters['statistical'] += 1
            if facts['is_authority_reconciliation']:
                counters['authority'] += 1
            if facts['is_provenance_only']:
                counters['provenance_only'] += 1
            if facts['action'] == ACTION_UPDATE:
                updated_rows.append((game, row))

            identity_facts = facts['identity']
            counters['identity_rows'] += 1
            identity_action_counts[identity_facts['action']] = (
                identity_action_counts.get(identity_facts['action'], 0) + 1
            )
            for field in identity_facts['changed_fields']:
                identity_changed_field_counts[field] = (
                    identity_changed_field_counts.get(field, 0) + 1
                )
            for field in identity_facts['suppressed_fields']:
                suppressed_field_counts[field] = (
                    suppressed_field_counts.get(field, 0) + 1
                )
            if identity_facts['suppressed_any']:
                counters['identity_suppressed_rows'] += 1
            if identity_facts['is_mutation']:
                counters['identity_mutations'] += 1
                identity_pitchers.add(row.get('pitcher_mlb_id'))
                identity_rows.append((game, row, identity_facts))
            else:
                counters['identity_unchanged'] += 1

        # Per-game aggregate counters must agree with the per-game row list.
        _require(f'game_{game_pk}_updated_matches_rows',
                 game_actions[ACTION_UPDATE], game.get('updated'))
        _require(f'game_{game_pk}_unchanged_matches_rows',
                 game_actions[ACTION_UNCHANGED], game.get('unchanged'))
        _require(
            f'game_{game_pk}_action_total_matches_row_count', len(rows),
            sum(game_actions.values()),
        )
        _require(
            f'game_{game_pk}_derived_companion_differences_ignored', game_ignored,
            game.get('derived_companion_differences_ignored'),
        )
        _require(f'game_{game_pk}_canonical_outs_corrections', game_outs,
                 game.get('canonical_outs_corrections'))
        _require(f'game_{game_pk}_derived_companion_fields_applied', game_applied,
                 game.get('derived_companion_fields_applied'))

        recomputed['inserted'] += game_actions[ACTION_INSERT]
        recomputed['updated'] += game_actions[ACTION_UPDATE]
        recomputed['unchanged'] += game_actions[ACTION_UNCHANGED]
        recomputed['blocked'] += game_actions[ACTION_BLOCKED]
        recomputed['rows'] += len(rows)

    # Top-level totals must equal the sum of the games, which in turn equal the
    # sum of their rows. A passing aggregate over a miscounted set is not a pass.
    _require('rows_expected_matches_per_row_total', totals['rows_expected'],
             recomputed['rows'])
    _require('rows_updated_matches_per_row_total', totals['rows_updated'],
             recomputed['updated'])
    _require('rows_unchanged_matches_per_row_total', totals['rows_unchanged'],
             recomputed['unchanged'])
    _require('rows_inserted_matches_per_row_total', totals['rows_inserted'],
             recomputed['inserted'])
    _require('rows_blocked_matches_per_row_total', totals['rows_blocked'],
             recomputed['blocked'])

    _require('changed_fields_counts_match_rows',
             dict(sorted(changed_field_counts.items())),
             dict(sorted((report.get('changed_fields_counts') or {}).items())))
    _require('mutation_category_counts_match_rows',
             dict(sorted(category_counts.items())),
             dict(sorted((report.get('mutation_category_counts') or {}).items())))

    return {
        'updated_rows': updated_rows,
        'identity_rows': identity_rows,
        'identity_action_counts': dict(sorted(identity_action_counts.items())),
        'identity_changed_field_counts': dict(
            sorted(identity_changed_field_counts.items())
        ),
        'suppressed_field_counts': dict(sorted(suppressed_field_counts.items())),
        'identity_unique_pitchers': len(
            {value for value in identity_pitchers if value is not None}
        ),
        'updated_game_count': len({
            game.get('game_pk') for game, _row in updated_rows
        }),
        'changed_fields_counts': dict(sorted(changed_field_counts.items())),
        'mutation_category_counts': dict(sorted(category_counts.items())),
        'counters': counters,
    }


# ── Canonical innings counters ──────────────────────────────────────────────


def _validate_innings_counters(report, counters):
    ignored = _require_nonneg_int(
        'derived_companion_differences_ignored',
        report.get('derived_companion_differences_ignored'),
    )
    suppressed = _require_nonneg_int(
        'decimal_only_updates_suppressed',
        report.get('decimal_only_updates_suppressed'),
    )
    outs = _require_nonneg_int(
        'canonical_outs_corrections', report.get('canonical_outs_corrections'),
    )
    applied = _require_nonneg_int(
        'derived_companion_fields_applied',
        report.get('derived_companion_fields_applied'),
    )

    _require('decimal_only_updates_suppressed_equals_ignored', ignored, suppressed)
    _require('derived_companion_differences_ignored_matches_rows',
             counters['ignored_rows'], ignored)
    _require('canonical_outs_corrections_matches_rows',
             counters['outs_corrections'], outs)
    _require('derived_companion_fields_applied_matches_rows',
             counters['applied_companions'], applied)

    # A companion is applied only alongside its authority, so applied can never
    # exceed the number of genuine outs corrections.
    if applied > outs:
        raise ValidationFailure(
            'applied_companions_never_exceed_outs_corrections', f'<= {outs}',
            applied,
        )

    _require('changed_fields_counts_excludes_innings_pitched', False,
             any(field in (report.get('changed_fields_counts') or {})
                 for field in PROHIBITED_SEMANTIC_FIELDS))

    _require('statistical_corrections_matches_rows', counters['statistical'],
             report.get('statistical_corrections'))
    _require('authority_reconciliations_matches_rows', counters['authority'],
             report.get('authority_reconciliations'))
    _require('provenance_only_updates_matches_rows', counters['provenance_only'],
             report.get('provenance_only_updates'))

    return {
        'derived_companion_differences_ignored': ignored,
        'decimal_only_updates_suppressed': suppressed,
        'canonical_outs_corrections': outs,
        'derived_companion_fields_applied': applied,
    }


def _validate_identity_counters(report, games):
    """Top-level identity accounting, recomputed from the rows.

    Every one of these was absent before the repair, which is how 942 planned
    Pitcher writes coexisted with `rows_updated: 0` and an empty manifest.
    """
    counters = games['counters']

    examined = _require_nonneg_int(
        'pitcher_identity_rows_examined',
        report.get('pitcher_identity_rows_examined'),
    )
    mutations = _require_nonneg_int(
        'pitcher_identity_mutations', report.get('pitcher_identity_mutations'),
    )
    creations = _require_nonneg_int(
        'pitcher_identity_creations', report.get('pitcher_identity_creations'),
    )
    unchanged = _require_nonneg_int(
        'pitcher_identity_unchanged', report.get('pitcher_identity_unchanged'),
    )
    suppressed = _require_nonneg_int(
        'historical_current_state_changes_suppressed',
        report.get('historical_current_state_changes_suppressed'),
    )

    # Retired write actions and blocked identities are rollout stops, never
    # something to review.
    _require('pitcher_identity_reactivations', 0,
             report.get('pitcher_identity_reactivations'))
    _require('pitcher_identity_metadata_updates', 0,
             report.get('pitcher_identity_metadata_updates'))
    _require('pitcher_identity_blocked', 0,
             report.get('pitcher_identity_blocked'))

    action_counts = dict(report.get('pitcher_identity_action_counts') or {})
    for action in sorted(RETIRED_IDENTITY_ACTIONS):
        if action_counts.get(action):
            raise ValidationFailure(
                f'pitcher_identity_action_counts_excludes_{action}', 0,
                action_counts[action],
            )
    for action in action_counts:
        if action not in KNOWN_IDENTITY_ACTIONS:
            raise ValidationFailure(
                'pitcher_identity_action_is_known',
                sorted(KNOWN_IDENTITY_ACTIONS), action,
            )

    changed_counts = dict(
        report.get('pitcher_identity_changed_fields_counts') or {}
    )
    for field in changed_counts:
        if field in CURRENT_STATE_AUTHORITY_FIELDS and (
            not action_counts.get(identity.ACTION_CREATE_MINIMAL_IDENTITY)
        ):
            raise ValidationFailure(
                f'pitcher_identity_never_writes_current_state_{field}',
                'absent', changed_counts[field],
            )
        if field not in ALLOWED_IDENTITY_CHANGED_FIELDS:
            raise ValidationFailure(
                f'pitcher_identity_changed_field_{field}_is_governed',
                sorted(ALLOWED_IDENTITY_CHANGED_FIELDS), field,
            )

    # The rows are the authority; the counters must agree with them.
    _require('pitcher_identity_rows_examined_matches_rows',
             counters['identity_rows'], examined)
    _require('pitcher_identity_mutations_matches_rows',
             counters['identity_mutations'], mutations)
    _require('pitcher_identity_unchanged_matches_rows',
             counters['identity_unchanged'], unchanged)
    _require('pitcher_identity_creations_matches_rows',
             counters['identity_mutations'], creations)
    _require('pitcher_identity_action_counts_match_rows',
             games['identity_action_counts'], action_counts)
    _require('pitcher_identity_changed_fields_counts_match_rows',
             games['identity_changed_field_counts'], changed_counts)
    _require('suppressed_current_state_field_counts_match_rows',
             games['suppressed_field_counts'],
             dict(report.get('suppressed_current_state_field_counts') or {}))
    _require('historical_current_state_changes_suppressed_matches_rows',
             counters['identity_suppressed_rows'], suppressed)
    _require('pitcher_identity_unique_pitchers_affected_matches_rows',
             games['identity_unique_pitchers'],
             report.get('pitcher_identity_unique_pitchers_affected'))

    return {
        'pitcher_identity_rows_examined': examined,
        'pitcher_identity_mutations': mutations,
        'pitcher_identity_unchanged': unchanged,
        'pitcher_identity_creations': creations,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': 0,
        'pitcher_identity_action_counts': action_counts,
        'pitcher_identity_changed_fields_counts': changed_counts,
        'pitcher_identity_unique_pitchers_affected': games[
            'identity_unique_pitchers'
        ],
        'historical_current_state_changes_suppressed': suppressed,
        'suppressed_current_state_field_counts': games['suppressed_field_counts'],
    }


def _validate_complete_mutation_count(report, totals, identity_totals, games):
    """One number covering every database target this run would touch."""
    appearance_team_mutations = _require_nonneg_int(
        'appearance_team_mutations', report.get('appearance_team_mutations'),
    )
    _require('appearance_team_mutations_matches_rows',
             games['counters']['authority'], appearance_team_mutations)

    expected = (
        totals['rows_inserted'] + totals['rows_updated'] + totals['rows_blocked']
        + identity_totals['pitcher_identity_mutations']
        + identity_totals['pitcher_identity_blocked']
    )
    observed = _require_nonneg_int(
        'complete_mutation_count', report.get('complete_mutation_count'),
    )
    _require('complete_mutation_count_matches_targets', expected, observed)
    return {
        'appearance_team_mutations': appearance_team_mutations,
        'complete_mutation_count': observed,
    }


# ── Publication completeness ────────────────────────────────────────────────


def _validate_publication_completeness(report):
    """R2 writes nothing, so completeness may legitimately be false.

    Shadow mode creates no checkpoints, which means the games it read stay
    uncheckpointed and publication stays withheld. That is the designed
    behaviour, not a defect — so the object is checked for internal consistency
    and for the failure signals that WOULD matter, and is never rewritten to
    make R2 look green.
    """
    completeness = report.get('publication_completeness')
    if not isinstance(completeness, dict):
        raise ValidationFailure(
            'publication_completeness_is_an_object', 'object',
            type(completeness).__name__,
        )

    expected = _require_nonneg_int('completeness_expected_final_games',
                                   completeness.get('expected_final_games'))
    completed = _require_nonneg_int('completeness_completed_final_games',
                                    completeness.get('completed_final_games'))
    unresolved = _require_nonneg_int('completeness_unresolved_final_games',
                                     completeness.get('unresolved_final_games'))
    rows_expected = _require_nonneg_int(
        'completeness_critical_rows_expected',
        completeness.get('critical_appearance_rows_expected'),
    )
    rows_reconciled = _require_nonneg_int(
        'completeness_critical_rows_reconciled',
        completeness.get('critical_appearance_rows_reconciled'),
    )

    _require('completeness_terminal_failure_games', 0,
             completeness.get('terminal_failure_games'))
    _require('completeness_finality_conflicts', 0,
             completeness.get('finality_conflicts'))
    _require('completeness_schedule_authority_missing', 0,
             completeness.get('schedule_authority_missing'))

    if completed + unresolved > expected:
        raise ValidationFailure(
            'completeness_completed_plus_unresolved_within_expected',
            f'<= {expected}', completed + unresolved,
        )
    if rows_reconciled > rows_expected:
        raise ValidationFailure(
            'completeness_reconciled_rows_within_expected', f'<= {rows_expected}',
            rows_reconciled,
        )

    reasons = list(completeness.get('decision_reasons') or [])
    if not reasons:
        raise ValidationFailure(
            'completeness_states_a_decision_reason', '>= 1 reason', reasons,
        )

    return {
        'publication_complete': bool(completeness.get('publication_complete')),
        'expected_final_games': expected,
        'completed_final_games': completed,
        'unresolved_final_games': unresolved,
        'correction_pending_games': completeness.get('correction_pending_games'),
        'terminal_failure_games': completeness.get('terminal_failure_games'),
        'critical_appearance_rows_expected': rows_expected,
        'critical_appearance_rows_reconciled': rows_reconciled,
        'decision_reasons': reasons,
    }


# ── Manifest ────────────────────────────────────────────────────────────────


def build_manifest(report, updated_rows, identity_rows, aggregates) -> dict:
    """One deterministic entry per projected mutation, of EVERY class.

    The pre-repair manifest listed GameLog updates only, so a run planning 942
    Pitcher writes produced `updates: []`. Every entry now names its mutation
    target, and the identity rows appear whether or not their GameLog action
    changed.
    """
    entries = []
    for game, row in updated_rows:
        entries.append({
            'mutation_target': (
                MUTATION_TARGET_APPEARANCE_TEAM
                if row.get('appearance_team_reason')
                else MUTATION_TARGET_GAME_LOG
            ),
            'game_pk': game.get('game_pk'),
            'represented_date': game.get('represented_date'),
            'pitcher_mlb_id': row.get('pitcher_mlb_id'),
            'action': row.get('action'),
            'semantic_changed_fields': sorted(
                row.get('semantic_changed_fields') or []
            ),
            'applied_changed_fields': sorted(
                row.get('applied_changed_fields') or []
            ),
            'derived_companion_fields': sorted(
                row.get('derived_companion_fields') or []
            ),
            'derived_companion_differences_ignored': sorted(
                row.get('derived_companion_differences_ignored') or []
            ),
            'mutation_categories': list(row.get('mutation_categories') or []),
            'changed_field_count': row.get('changed_field_count'),
            'affects_published_evidence': bool(
                row.get('affects_published_evidence')
            ),
            'governed_and_safe': bool(row.get('governed_and_safe')),
            'blocked_reason': row.get('blocked_reason'),
            'is_statistical_correction': bool(
                row.get('is_statistical_correction')
            ),
            'is_provenance_only': bool(row.get('is_provenance_only')),
            'appearance_team_reason': row.get('appearance_team_reason'),
            'source_revision': game.get('source_revision'),
            'mutation_digest': row.get('mutation_digest'),
        })

    for game, row, facts in identity_rows:
        entries.append({
            'mutation_target': MUTATION_TARGET_IDENTITY,
            'game_pk': game.get('game_pk'),
            'represented_date': game.get('represented_date'),
            'pitcher_mlb_id': row.get('pitcher_mlb_id'),
            'action': facts['action'],
            'semantic_changed_fields': sorted(facts['changed_fields']),
            'applied_changed_fields': sorted(facts['applied_fields']),
            'derived_companion_fields': [],
            'derived_companion_differences_ignored': [],
            'suppressed_current_state_fields': facts['suppressed_fields'],
            'mutation_categories': [
                reconciliation.CATEGORY_PITCHER_IDENTITY,
            ],
            'changed_field_count': len(facts['changed_fields']),
            'affects_published_evidence': True,
            'governed_and_safe': bool(
                row.get('pitcher_identity_governed_and_safe', True)
            ),
            'blocked_reason': row.get('pitcher_identity_blocked_reason'),
            'is_statistical_correction': False,
            'is_provenance_only': False,
            'appearance_team_reason': None,
            'source_revision': game.get('source_revision'),
            'mutation_digest': row.get('pitcher_identity_mutation_digest'),
        })

    for entry in entries:
        entry.setdefault('suppressed_current_state_fields', [])
    entries.sort(key=lambda entry: (
        MUTATION_TARGET_ORDER.get(entry['mutation_target'], 99),
        entry['game_pk'] or 0,
        entry['pitcher_mlb_id'] or 0,
    ))

    return {
        'reference_date': REFERENCE_DATE,
        'updated_row_count': len(entries),
        'mutation_target_counts': {
            target: sum(
                1 for entry in entries if entry['mutation_target'] == target
            )
            for target in sorted(MUTATION_TARGET_ORDER)
        },
        'pitcher_identity_mutations': aggregates.get(
            'pitcher_identity_mutations', 0
        ),
        'appearance_team_mutations': aggregates.get(
            'appearance_team_mutations', 0
        ),
        'complete_mutation_count': aggregates.get('complete_mutation_count', 0),
        'historical_current_state_changes_suppressed': aggregates.get(
            'historical_current_state_changes_suppressed', 0
        ),
        'suppressed_current_state_field_counts': aggregates.get(
            'suppressed_current_state_field_counts', {}
        ),
        'updated_game_count': aggregates['updated_game_count'],
        'changed_fields_counts': aggregates['changed_fields_counts'],
        'mutation_category_counts': aggregates['mutation_category_counts'],
        'canonical_outs_corrections': aggregates['canonical_outs_corrections'],
        'authority_reconciliations': aggregates['authority_reconciliations'],
        'statistical_corrections': aggregates['statistical_corrections'],
        'provenance_only_updates': aggregates['provenance_only_updates'],
        'derived_companion_differences_ignored': aggregates[
            'derived_companion_differences_ignored'
        ],
        'reconciliation_plan_fingerprint': report.get(
            'reconciliation_plan_fingerprint'
        ),
        'write_approved': False,
        'updates': entries,
    }


def manifest_markdown(manifest) -> str:
    lines = [
        '# Foundation 3C R2 — update review manifest',
        '',
        f"- Reference date: {manifest['reference_date']}",
        f"- Mutations: {manifest['updated_row_count']}",
        f"- By target: {manifest.get('mutation_target_counts')}",
        f"- Pitcher identity mutations: {manifest.get('pitcher_identity_mutations')}",
        '- Suppressed historical current-state differences: '
        f"{manifest.get('historical_current_state_changes_suppressed')}",
        f"- Updated games: {manifest['updated_game_count']}",
        f"- Canonical outs corrections: {manifest['canonical_outs_corrections']}",
        '- Decimal-only differences safely ignored: '
        f"{manifest['derived_companion_differences_ignored']}",
        f"- Reconciliation fingerprint: `{manifest['reconciliation_plan_fingerprint']}`",
        '- Write approved: no',
        '',
    ]
    if manifest['changed_fields_counts']:
        lines.append('## Changed fields')
        lines.append('')
        for field, count in manifest['changed_fields_counts'].items():
            lines.append(f'- `{field}`: {count}')
        lines.append('')
    if not manifest['updates']:
        lines.append('No mutations were projected to any database target.')
        lines.append('')
        return '\n'.join(lines)

    lines.append('## Updates')
    lines.append('')
    lines.append(
        '| Target | Game | Date | Pitcher | Fields | Categories | Digest |'
    )
    lines.append('| --- | --- | --- | --- | --- | --- | --- |')
    for entry in manifest['updates']:
        fields = ', '.join(f"`{field}`" for field in entry['semantic_changed_fields'])
        categories = ', '.join(entry['mutation_categories'])
        lines.append(
            f"| {entry['mutation_target']} | {entry['game_pk']} "
            f"| {entry['represented_date']} "
            f"| {entry['pitcher_mlb_id']} | {fields} | {categories} "
            f"| `{entry['mutation_digest']}` |"
        )
    lines.append('')
    return '\n'.join(lines)


# ── Validation entry point ──────────────────────────────────────────────────


def validate(report) -> dict:
    """Assert every R2 invariant and classify the outcome.

    Returns a summary whose ``result`` is ``pass`` or ``review_required``.
    Raises ``ValidationFailure`` on the first broken invariant — never
    downgrades a foundational failure into ``review_required``.
    """
    if not isinstance(report, dict):
        raise ValidationFailure('report_is_an_object', 'object',
                                type(report).__name__)

    _validate_identity(report)
    scope = _validate_scope(report)
    totals = _validate_row_accounting(report)
    games = _validate_games(report, totals)
    innings = _validate_innings_counters(report, games['counters'])
    identity_totals = _validate_identity_counters(report, games)
    complete = _validate_complete_mutation_count(
        report, totals, identity_totals, games,
    )
    completeness = _validate_publication_completeness(report)

    aggregates = {
        'updated_game_count': games['updated_game_count'],
        'changed_fields_counts': games['changed_fields_counts'],
        'mutation_category_counts': games['mutation_category_counts'],
        'canonical_outs_corrections': innings['canonical_outs_corrections'],
        'authority_reconciliations': report.get('authority_reconciliations'),
        'statistical_corrections': report.get('statistical_corrections'),
        'provenance_only_updates': report.get('provenance_only_updates'),
        'derived_companion_differences_ignored': innings[
            'derived_companion_differences_ignored'
        ],
    }
    aggregates.update(identity_totals)
    aggregates.update(complete)
    manifest = build_manifest(
        report, games['updated_rows'], games['identity_rows'], aggregates,
    )

    # PASS requires zero mutations of EVERY class. Judging on the GameLog half
    # alone is what let 942 planned identity writes report as a clean window.
    result = (
        RESULT_PASS if complete['complete_mutation_count'] == 0
        else RESULT_REVIEW_REQUIRED
    )
    next_action = (
        'The complete governed window projects no mutations to any database '
        'target. Foundation 3C may proceed to selecting the next controlled '
        'sample.'
        if result == RESULT_PASS else
        'R3/R4 remain blocked until Nickolis reviews the update manifest. No '
        'write is approved.'
    )

    summary = {
        'result': result,
        'reference_date': REFERENCE_DATE,
        'execution_scope_mode': report.get('execution_scope_mode'),
        'games_discovered': scope['games_discovered'],
        'games_planned': scope['games_planned'],
        'games_completed': report.get('games_completed'),
        'games_failed': report.get('games_failed'),
        'rows_expected': totals['rows_expected'],
        'rows_inserted': totals['rows_inserted'],
        'rows_updated': totals['rows_updated'],
        'rows_unchanged': totals['rows_unchanged'],
        'rows_blocked': totals['rows_blocked'],
        'updated_game_count': games['updated_game_count'],
        'changed_fields_counts': games['changed_fields_counts'],
        'mutation_category_counts': games['mutation_category_counts'],
        'canonical_outs_corrections': innings['canonical_outs_corrections'],
        'derived_companion_differences_ignored': innings[
            'derived_companion_differences_ignored'
        ],
        'decimal_only_updates_suppressed': innings[
            'decimal_only_updates_suppressed'
        ],
        'derived_companion_fields_applied': innings[
            'derived_companion_fields_applied'
        ],
        'statistical_corrections': report.get('statistical_corrections'),
        'authority_reconciliations': report.get('authority_reconciliations'),
        'provenance_only_updates': report.get('provenance_only_updates'),
        'innings_pitched_semantic_corrections': 0,
        'reconciliation_plan_fingerprint': report.get(
            'reconciliation_plan_fingerprint'
        ),
        'innings_semantics_version': report.get('innings_semantics_version'),
        'reconciliation_plan_version': report.get('reconciliation_plan_version'),
        'parity_contract_version': report.get('parity_contract_version'),
        'publication_completeness': completeness,
        **identity_totals,
        **complete,
        'identity_plan_version': report.get('identity_plan_version'),
        'complete_plan_version': report.get('complete_plan_version'),
        'complete_reconciliation_fingerprint': report.get(
            'complete_reconciliation_fingerprint'
        ),
        'database_writes': 'none',
        'write_approved': False,
        'failed_invariant': None,
        'next_action': next_action,
    }
    return {'summary': summary, 'manifest': manifest}


# ── Summaries ───────────────────────────────────────────────────────────────


def _counts_block(summary):
    return [
        '### Window',
        f"- Reference date: {summary['reference_date']}",
        f"- Games planned: {summary['games_planned']}",
        f"- Games completed: {summary['games_completed']}",
        f"- Games failed: {summary['games_failed']}",
        '',
        '### Appearance rows',
        f"- Expected: {summary['rows_expected']}",
        f"- Inserted: {summary['rows_inserted']}",
        f"- Updated: {summary['rows_updated']}",
        f"- Unchanged: {summary['rows_unchanged']}",
        f"- Blocked: {summary['rows_blocked']}",
        '',
    ]


def _mutation_block(summary):
    return [
        '### Mutations by target',
        f"- GameLog: {summary['rows_inserted'] + summary['rows_updated']}",
        f"- Pitcher identity: {summary['pitcher_identity_mutations']}",
        f"- Appearance team: {summary['appearance_team_mutations']}",
        f"- Total complete-plan mutations: {summary['complete_mutation_count']}",
        '',
        '### Pitcher identity detail',
        f"- Reactivations: {summary['pitcher_identity_reactivations']}",
        f"- Metadata updates: {summary['pitcher_identity_metadata_updates']}",
        f"- Minimal identity creations: {summary['pitcher_identity_creations']}",
        f"- Blocked identity entries: {summary['pitcher_identity_blocked']}",
        '- Suppressed historical current-state differences: '
        f"{summary['historical_current_state_changes_suppressed']}",
        '',
    ]


def _innings_block(summary):
    return [
        '### Canonical innings',
        '- Decimal-only differences safely ignored: '
        f"{summary['derived_companion_differences_ignored']}",
        f"- Canonical outs corrections: {summary['canonical_outs_corrections']}",
        '- `innings_pitched` semantic corrections: '
        f"{summary['innings_pitched_semantic_corrections']}",
        '',
    ]


def pass_markdown(summary) -> str:
    lines = ['## FOUNDATION 3C R2 — PASS', '']
    lines += _counts_block(summary)
    lines += _mutation_block(summary)
    lines += _innings_block(summary)
    lines += [
        '### Result',
        # Only reachable when every target is at zero — the validator refuses to
        # classify PASS otherwise, so this sentence cannot appear over a
        # pending Pitcher write.
        '- The complete governed window projects no mutations to any database '
        'target.',
        '- No database writes were performed.',
        '- Foundation 3C may proceed to selecting the next controlled sample.',
        '',
    ]
    return '\n'.join(lines)


def review_markdown(summary, manifest) -> str:
    lines = ['## FOUNDATION 3C R2 — REVIEW REQUIRED', '']
    lines += _counts_block(summary)

    if summary['changed_fields_counts']:
        lines.append('### Changed fields')
        for field, count in summary['changed_fields_counts'].items():
            lines.append(f'- `{field}`: {count}')
        lines.append('')

    lines += _mutation_block(summary)
    lines += _innings_block(summary)

    updates = manifest['updates']
    shown = updates[:MAX_SUMMARY_UPDATE_EXAMPLES]
    if shown:
        lines.append(
            f'### Updates ({len(shown)} of {len(updates)} shown)'
        )
        lines.append('')
        lines.append('| Target | Game | Pitcher | Fields |')
        lines.append('| --- | --- | --- | --- |')
        for entry in shown:
            fields = ', '.join(
                f"`{field}`" for field in entry['semantic_changed_fields']
            )
            lines.append(
                f"| {entry['mutation_target']} | {entry['game_pk']} "
                f"| {entry['pitcher_mlb_id']} | {fields} |"
            )
        if len(updates) > len(shown):
            lines.append('')
            lines.append(
                f'The remaining {len(updates) - len(shown)} updates are in '
                '`r2-update-review.json`.'
            )
        lines.append('')

    lines += [
        '### Result',
        '- The shadow run completed safely.',
        '- The projected updates are recorded in `r2-update-review.json`.',
        '- No write is approved.',
        '- R3/R4 must not begin until Nickolis reviews the update manifest.',
        '- No database writes were performed.',
        '',
    ]
    return '\n'.join(lines)


def failed_markdown(summary) -> str:
    lines = [
        '## FOUNDATION 3C R2 — FAILED',
        '',
        f"- Failed invariant: `{summary.get('failed_invariant')}`",
        f"- Expected: `{summary.get('expected')}`",
        f"- Observed: `{summary.get('observed')}`",
        '',
        '### Observed totals',
        f"- Games planned: {summary.get('games_planned')}",
        f"- Games completed: {summary.get('games_completed')}",
        f"- Games failed: {summary.get('games_failed')}",
        f"- Rows expected: {summary.get('rows_expected')}",
        f"- Rows inserted: {summary.get('rows_inserted')}",
        f"- Rows updated: {summary.get('rows_updated')}",
        f"- Rows unchanged: {summary.get('rows_unchanged')}",
        f"- Rows blocked: {summary.get('rows_blocked')}",
        f"- Pitcher identity mutations: {summary.get('pitcher_identity_mutations')}",
        f"- Complete-plan mutations: {summary.get('complete_mutation_count')}",
        '',
        f"- Artifact: `{summary.get('artifact')}`",
        '',
        'This is a rollout stop. R3/R4 must not begin.',
        '',
    ]
    return '\n'.join(lines)


def _failure_summary(report, failure, artifact) -> dict:
    report = report if isinstance(report, dict) else {}
    return {
        'result': RESULT_FAILED,
        'reference_date': REFERENCE_DATE,
        'failed_invariant': failure.invariant,
        'expected': failure.expected,
        'observed': failure.observed,
        'games_planned': report.get('games_planned'),
        'games_completed': report.get('games_completed'),
        'games_failed': report.get('games_failed'),
        'rows_expected': report.get('rows_expected'),
        'rows_inserted': report.get('rows_inserted'),
        'rows_updated': report.get('rows_updated'),
        'rows_unchanged': report.get('rows_unchanged'),
        'rows_blocked': report.get('rows_blocked'),
        'pitcher_identity_mutations': report.get('pitcher_identity_mutations'),
        'complete_mutation_count': report.get('complete_mutation_count'),
        'database_writes': 'none',
        'write_approved': False,
        'artifact': artifact,
        'next_action': 'Rollout stops. R3/R4 must not begin.',
    }


# ── CLI ─────────────────────────────────────────────────────────────────────


def _write_text(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')


def _write_json(path, payload):
    _write_text(
        path, json.dumps(payload, indent=2, sort_keys=True, default=str) + '\n',
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Validate a Foundation 3C R2 full-window shadow report.',
    )
    parser.add_argument('--report', required=True)
    parser.add_argument('--summary-json', required=True)
    parser.add_argument('--summary-markdown', required=True)
    parser.add_argument('--manifest-json', required=True)
    parser.add_argument('--manifest-markdown', required=True)
    parser.add_argument('--repository-sha', default=None)
    parser.add_argument('--run-id', default=None)
    args = parser.parse_args(argv)

    artifact = Path(args.report).name
    report_path = Path(args.report)
    report = {}
    manifest = None

    if not report_path.exists():
        summary = _failure_summary(
            {}, ValidationFailure('report_file_exists', 'present', 'missing'),
            artifact,
        )
    else:
        try:
            report = json.loads(report_path.read_text(encoding='utf-8'))
        except Exception:  # noqa: BLE001 - the parse failure itself is the signal
            summary = _failure_summary(
                {},
                ValidationFailure('report_is_valid_json', 'json', 'unparsable'),
                artifact,
            )
        else:
            try:
                validated = validate(report)
                summary = validated['summary']
                manifest = validated['manifest']
                summary['artifact'] = artifact
            except ValidationFailure as failure:
                summary = _failure_summary(report, failure, artifact)

    summary['repository_sha'] = args.repository_sha
    summary['workflow_run_id'] = args.run_id

    if manifest is None:
        # A failed run still writes an empty manifest so the artifact set is
        # complete and a reviewer never wonders whether it was withheld.
        manifest = {
            'reference_date': REFERENCE_DATE,
            'updated_row_count': 0,
            'updated_game_count': 0,
            'mutation_target_counts': {},
            'pitcher_identity_mutations': 0,
            'appearance_team_mutations': 0,
            'complete_mutation_count': 0,
            'historical_current_state_changes_suppressed': 0,
            'suppressed_current_state_field_counts': {},
            'changed_fields_counts': {},
            'mutation_category_counts': {},
            'canonical_outs_corrections': 0,
            'authority_reconciliations': 0,
            'statistical_corrections': 0,
            'provenance_only_updates': 0,
            'derived_companion_differences_ignored': 0,
            'reconciliation_plan_fingerprint': None,
            'write_approved': False,
            'updates': [],
        }

    if summary['result'] == RESULT_PASS:
        markdown = pass_markdown(summary)
        exit_code = EXIT_OK
    elif summary['result'] == RESULT_REVIEW_REQUIRED:
        markdown = review_markdown(summary, manifest)
        exit_code = EXIT_OK
    else:
        markdown = failed_markdown(summary)
        exit_code = EXIT_FAILED

    _write_json(args.summary_json, summary)
    _write_text(args.summary_markdown, markdown)
    _write_json(args.manifest_json, manifest)
    _write_text(args.manifest_markdown, manifest_markdown(manifest))
    print(markdown)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
