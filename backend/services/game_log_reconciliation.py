"""Canonical GameLog reconciliation planner (Foundation 3C parity repair).

ONE authority decides, for a single official pitching appearance, whether the
canonical appearance row is inserted, updated, left unchanged, or blocked —
which fields change, and what kind of change each one is.

Why this module exists
----------------------
Shadow mode and write mode previously answered that question independently.
Shadow compared eight fields drawn from the extracted-appearance vocabulary;
the canonical writer reconciled a much broader governed record built by
``sync._game_log_values_from_stats`` and additionally reconciled team-at-
appearance authority outside the field loop. In a controlled production run the
two disagreed: shadow projected 38 unchanged rows across five games, and the
writer then applied 14 updates to those same rows.

Two reconciliation authorities will always drift. There is now one. The
canonical writer asks this planner what to do and then applies exactly that;
shadow asks the same planner with the same inputs and reports the answer
without writing. Neither recalculates the decision.

Contract
--------
``plan_row`` is PURE: it reads the stored row and the governed values and
returns a deterministic, serializable plan. It performs no writes, opens no
transaction, and mutates neither the row nor the values. Applying a plan is the
writer's job and happens in exactly one place.
"""

from __future__ import annotations

import hashlib
import json

from services import appearance_team_authority
from services import pitcher_identity_reconciliation as identity


# The plan shape and the parity guarantee are versioned separately: the shape
# may gain fields without changing what parity means, and parity may tighten
# without reshaping the plan.
# Bumped from '2' by the pitcher-identity repair: a row plan now carries the
# identity decision, and the fingerprint commits to it, so a plan reviewed
# under the old contract no longer describes every database effect.
RECONCILIATION_PLAN_VERSION = '3'
PARITY_CONTRACT_VERSION = '3'

# The complete plan is GameLog + pitcher identity + appearance-team authority
# decided together and fingerprinted together. Versioned separately so the
# combination can tighten without reshaping either component.
COMPLETE_PLAN_VERSION = '1'


# ── Actions ─────────────────────────────────────────────────────────────────
ACTION_INSERT = 'insert'
ACTION_UPDATE = 'update'
ACTION_UNCHANGED = 'unchanged'
ACTION_BLOCKED = 'blocked'

ACTIONS = (ACTION_INSERT, ACTION_UPDATE, ACTION_UNCHANGED, ACTION_BLOCKED)


# ── Mutation categories ─────────────────────────────────────────────────────
CATEGORY_STATISTICAL_CORRECTION = 'official_statistical_correction'
CATEGORY_APPEARANCE_TEAM_AUTHORITY = 'appearance_team_authority_reconciliation'
CATEGORY_ROLE_SIGNAL = 'role_or_starter_signal_reconciliation'
CATEGORY_GAME_METADATA = 'game_metadata_reconciliation'
CATEGORY_PROVENANCE_ONLY = 'provenance_only_update'
CATEGORY_PITCHER_IDENTITY = 'pitcher_identity_reconciliation'
CATEGORY_UNCHANGED = 'unchanged_row'
CATEGORY_BLOCKED = 'unsafe_or_blocked_mutation'

CATEGORIES = (
    CATEGORY_STATISTICAL_CORRECTION,
    CATEGORY_APPEARANCE_TEAM_AUTHORITY,
    CATEGORY_ROLE_SIGNAL,
    CATEGORY_GAME_METADATA,
    CATEGORY_PROVENANCE_ONLY,
    CATEGORY_PITCHER_IDENTITY,
    CATEGORY_UNCHANGED,
    CATEGORY_BLOCKED,
)


# ── Field vocabulary ────────────────────────────────────────────────────────
# Every field the canonical writer may modify, and what kind of change it is.
# A field that reaches the writer without an entry here is a governance gap, so
# ``field_category`` fails closed rather than guessing.

STATISTICAL_FIELDS = (
    'innings_pitched',
    'innings_pitched_outs',
    'pitches_thrown',
    'strikes',
    'hits_allowed',
    'runs_allowed',
    'earned_runs',
    'walks',
    'strikeouts',
    'home_runs_allowed',
    'batters_faced',
    'balls',
    'games_finished',
    'inherited_runners',
    'inherited_runners_scored',
    'save_situation',
    'hold',
    'blown_save',
    'win',
    'loss',
    'save',
    'leverage_index',
)

ROLE_SIGNAL_FIELDS = ('games_started',)

GAME_METADATA_FIELDS = (
    'game_date',
    'game_type',
    'opponent',
    'opponent_abbreviation',
)

APPEARANCE_TEAM_FIELDS = (
    'appearance_team_id',
    'appearance_team_source',
    'appearance_team_status',
    'appearance_team_reason',
)

PROVENANCE_FIELDS = (
    'stat_correction_count',
    'last_stat_correction_at',
    'last_stat_correction_source',
    'last_stat_correction_sync_run_id',
)

# ── Semantic authority vs derived companion (D-008) ─────────────────────────
# Integer recorded outs are the permanent semantic innings authority; the
# decimal companion is derived from them and is not an independent official
# fact. It is stored for display and legacy compatibility, and it is written
# ONLY when its authority changes.
#
# Production proved why this must be enforced in the comparison itself rather
# than trusted to writer discipline: a stored float and a freshly derived float
# can differ in representation while describing the same canonical outs, so
# comparing the companion directly turned 323 non-changes into "official
# statistical corrections" and left an already-written game replaying the same
# non-correction forever.
SEMANTIC_AUTHORITY_BY_COMPANION = {
    'innings_pitched': 'innings_pitched_outs',
}
DERIVED_COMPANION_FIELDS = tuple(sorted(SEMANTIC_AUTHORITY_BY_COMPANION))

INNINGS_SEMANTICS_VERSION = '2'

# Fields whose change alters evidence a published bullpen read can consume.
# Provenance columns describe HOW a row was corrected, not WHAT it says.
PUBLISHED_EVIDENCE_FIELDS = frozenset(
    STATISTICAL_FIELDS + ROLE_SIGNAL_FIELDS + GAME_METADATA_FIELDS
    + APPEARANCE_TEAM_FIELDS
)

_FIELD_CATEGORY = {}
for _field in STATISTICAL_FIELDS:
    _FIELD_CATEGORY[_field] = CATEGORY_STATISTICAL_CORRECTION
for _field in ROLE_SIGNAL_FIELDS:
    _FIELD_CATEGORY[_field] = CATEGORY_ROLE_SIGNAL
for _field in GAME_METADATA_FIELDS:
    _FIELD_CATEGORY[_field] = CATEGORY_GAME_METADATA
for _field in APPEARANCE_TEAM_FIELDS:
    _FIELD_CATEGORY[_field] = CATEGORY_APPEARANCE_TEAM_AUTHORITY
for _field in PROVENANCE_FIELDS:
    _FIELD_CATEGORY[_field] = CATEGORY_PROVENANCE_ONLY
del _field


# Correction safety: an official line missing any of these cannot authorize a
# correction to an existing row. Owned here so the writer and the projection
# apply the same safety rule, and re-exported by ``services.sync`` under its
# historical private name so existing callers are unaffected.
REQUIRED_CORRECTION_STAT_KEYS = (
    'inningsPitched',
    'strikes',
    'hits',
    'runs',
    'earnedRuns',
    'baseOnBalls',
    'strikeOuts',
    'homeRuns',
)

OPTIONAL_BOOL_STAT_FIELDS = (
    ('saveOpportunities', 'save_situation'),
    ('holds', 'hold'),
    ('blownSaves', 'blown_save'),
    ('wins', 'win'),
    ('losses', 'loss'),
    ('saves', 'save'),
)

OPTIONAL_INT_STAT_FIELDS = (
    ('batters_faced', ('battersFaced', 'batters_faced')),
    ('balls', ('balls',)),
    ('games_finished', ('gamesFinished', 'games_finished')),
    ('inherited_runners', ('inheritedRunners', 'inherited_runners')),
    ('inherited_runners_scored',
     ('inheritedRunnersScored', 'inherited_runners_scored')),
)

BLOCKED_EMPTY_SOURCE_LINE = 'empty_source_line'
BLOCKED_PARTIAL_SOURCE_LINE = 'partial_source_line'


def field_category(field: str) -> str:
    """Category for a governed field. Unknown fields fail closed as blocked."""
    return _FIELD_CATEGORY.get(field, CATEGORY_BLOCKED)


def correction_source_state(stats: dict) -> tuple[bool, str | None, list[str]]:
    """Whether an official line is complete enough to authorize a correction."""
    if not stats:
        return False, BLOCKED_EMPTY_SOURCE_LINE, []
    missing = [
        key for key in REQUIRED_CORRECTION_STAT_KEYS
        if key not in stats or stats.get(key) in (None, '')
    ]
    if missing:
        return False, BLOCKED_PARTIAL_SOURCE_LINE, missing
    return True, None, []


def stat_key_present(stats: dict, keys: tuple[str, ...]) -> bool:
    stats = stats or {}
    return any(
        key in stats and stats.get(key) not in (None, '') for key in keys
    )


def correctable_fields(
    values: dict, stats: dict, *, include_leverage_index: bool,
) -> list[str]:
    """The exact field set the canonical writer is permitted to correct.

    Presence-driven, not truthiness-driven: an optional stat the source did not
    send is not silently rewritten to a default.
    """
    fields = [
        'game_date',
        'game_type',
        'innings_pitched',
        'innings_pitched_outs',
        'pitches_thrown',
        'strikes',
        'hits_allowed',
        'runs_allowed',
        'earned_runs',
        'walks',
        'strikeouts',
        'home_runs_allowed',
    ]
    for field in ('opponent', 'opponent_abbreviation', 'games_started'):
        if values.get(field) is not None:
            fields.append(field)
    for source_key, model_field in OPTIONAL_BOOL_STAT_FIELDS:
        if source_key in (stats or {}) and (stats or {}).get(source_key) not in (None, ''):
            fields.append(model_field)
    for model_field, source_keys in OPTIONAL_INT_STAT_FIELDS:
        if stat_key_present(stats, source_keys):
            fields.append(model_field)
    if include_leverage_index and values.get('leverage_index') is not None:
        fields.append('leverage_index')
    return fields


def plan_row(
    *,
    existing,
    values: dict,
    stats: dict,
    include_leverage_index: bool = False,
    appearance_team=None,
    game_pk=None,
    pitcher_mlb_id=None,
    local_pitcher_id=None,
    identity_plan=None,
) -> dict:
    """Decide what happens to one canonical appearance row.

    Pure. Reads ``existing`` and returns a plan; changes nothing. The canonical
    writer applies this plan, and shadow reports it — so the two cannot reach
    different conclusions about the same row.
    """
    natural_key = {
        'pitcher_id': local_pitcher_id,
        'mlb_game_pk': game_pk if game_pk is not None else values.get('mlb_game_pk'),
    }
    base = {
        'plan_version': RECONCILIATION_PLAN_VERSION,
        'game_pk': natural_key['mlb_game_pk'],
        'pitcher_mlb_id': pitcher_mlb_id,
        'local_pitcher_id': local_pitcher_id,
        'natural_key': natural_key,
        'changed_fields': [],
        'semantic_changed_fields': [],
        'applied_changed_fields': [],
        'derived_companion_fields': [],
        'derived_companion_differences_ignored': [],
        'field_changes': [],
        'changed_field_count': 0,
        'mutation_categories': [],
        'innings_semantics_version': INNINGS_SEMANTICS_VERSION,
        'appearance_team_reason': None,
        'provenance_update': False,
        'affects_published_evidence': False,
        'is_statistical_correction': False,
        'is_provenance_only': False,
        'governed_and_safe': True,
        'mutation_digest': '',
        'blocked_reason': None,
        'unresolved_reason': None,
        'complete_plan_version': COMPLETE_PLAN_VERSION,
        'pitcher_identity': identity_plan or {},
        'pitcher_identity_action': (identity_plan or {}).get('action'),
        'source_authority': values.get('appearance_team_source'),
    }

    # An identity decision earns its own mutation category ONLY when it would
    # actually touch the database. Under D-009 an existing row always resolves
    # to `unchanged`, so a suppressed historical difference no longer decorates
    # 942 otherwise-unchanged rows with a category that implied a write.
    identity_categories = (
        [CATEGORY_PITCHER_IDENTITY] if identity.is_mutation(identity_plan) else []
    )

    # ── Insert ──────────────────────────────────────────────────────────────
    if existing is None:
        base.update({
            'action': ACTION_INSERT,
            'mutation_categories': _ordered(
                identity_categories + [CATEGORY_STATISTICAL_CORRECTION]
            ),
            'affects_published_evidence': True,
            # The official notation was parsed once into canonical outs when the
            # values were built; the companion is stored derived from those outs
            # and is never independently trusted.
            'derived_companion_fields': [
                companion for companion in DERIVED_COMPANION_FIELDS
                if companion in values
            ],
            'mutation_digest': mutation_digest(
                action=ACTION_INSERT, values=values, field_changes=(),
            ),
        })
        return base

    # ── Blocked ─────────────────────────────────────────────────────────────
    safe, reason, missing = correction_source_state(stats)
    if not safe:
        base.update({
            'action': ACTION_BLOCKED,
            'mutation_categories': _ordered(identity_categories + [CATEGORY_BLOCKED]),
            'governed_and_safe': False,
            'blocked_reason': reason,
            'blocked_missing_keys': sorted(missing),
        })
        return base

    # ── Field-level reconciliation ──────────────────────────────────────────
    # Semantic comparison only. A derived companion (D-008: decimal innings) is
    # never compared against the stored value — its authority is, and the
    # companion is re-derived from the authority when that authority moves.
    changed_fields = []
    field_changes = []
    companion_differences = []
    for field in correctable_fields(
        values, stats, include_leverage_index=include_leverage_index,
    ):
        new_value = values[field]
        current = getattr(existing, field, None)
        if field in SEMANTIC_AUTHORITY_BY_COMPANION:
            # Recorded only so an operator can see that representation drift
            # exists. It is NOT a change and never authorizes a correction.
            if current != new_value:
                companion_differences.append(field)
            continue
        if current != new_value:
            changed_fields.append(field)
            field_changes.append({
                'field': field,
                'category': field_category(field),
                'before': _safe_value(current),
                'after': _safe_value(new_value),
            })

    # Team-at-appearance authority is reconciled OUTSIDE the stat loop, exactly
    # as the writer does: a legacy row is attributed only on a genuine
    # correction, and an unchanged re-sweep never backfills one.
    appearance_decision = appearance_team_authority.plan_update(
        existing, appearance_team, correction_applied=bool(changed_fields),
    )
    appearance_reason = (
        appearance_decision['reason'] if appearance_decision else None
    )
    if appearance_decision:
        for field, after in sorted(appearance_decision['fields'].items()):
            before = getattr(existing, field, None)
            if before == after:
                continue
            changed_fields.append(field)
            field_changes.append({
                'field': field,
                'category': CATEGORY_APPEARANCE_TEAM_AUTHORITY,
                'before': _safe_value(before),
                'after': _safe_value(after),
            })

    if not changed_fields and appearance_reason is None:
        base.update({
            'action': ACTION_UNCHANGED,
            'mutation_categories': _ordered(
                identity_categories + [CATEGORY_UNCHANGED]
            ),
            'derived_companion_differences_ignored': sorted(companion_differences),
        })
        return base

    # The provenance stamp is applied only by a genuine field correction. An
    # authority-only reconciliation deliberately does not claim a stat
    # correction happened.
    stat_like_changed = [
        field for field in changed_fields
        if field_category(field) in (
            CATEGORY_STATISTICAL_CORRECTION,
            CATEGORY_ROLE_SIGNAL,
            CATEGORY_GAME_METADATA,
        )
    ]
    provenance_update = bool(stat_like_changed)

    categories = identity_categories + [
        field_category(field) for field in changed_fields
    ]
    if appearance_reason is not None:
        categories.append(CATEGORY_APPEARANCE_TEAM_AUTHORITY)
    if provenance_update:
        categories.append(CATEGORY_PROVENANCE_ONLY)

    evidence_changed = [
        field for field in changed_fields if field in PUBLISHED_EVIDENCE_FIELDS
    ]
    is_provenance_only = provenance_update and not evidence_changed
    if is_provenance_only:
        categories = identity_categories + [CATEGORY_PROVENANCE_ONLY]

    # A companion is APPLIED — never independently corrected — when its
    # semantic authority is part of this update. It is re-derived from the
    # governed values, not carried over from the stored row.
    applied_companions = [
        companion for companion, authority
        in sorted(SEMANTIC_AUTHORITY_BY_COMPANION.items())
        if authority in changed_fields and companion in values
    ]

    base.update({
        'action': ACTION_UPDATE,
        'changed_fields': sorted(changed_fields),
        'semantic_changed_fields': sorted(changed_fields),
        'applied_changed_fields': sorted(changed_fields + applied_companions),
        'derived_companion_fields': applied_companions,
        'derived_companion_differences_ignored': sorted(
            field for field in companion_differences
            if field not in applied_companions
        ),
        'field_changes': sorted(field_changes, key=lambda item: item['field']),
        'changed_field_count': len(changed_fields),
        'mutation_digest': mutation_digest(
            action=ACTION_UPDATE, values=values, field_changes=field_changes,
        ),
        'mutation_categories': _ordered(categories),
        'appearance_team_reason': appearance_reason,
        'appearance_team_decision': appearance_decision,
        'provenance_update': provenance_update,
        'affects_published_evidence': bool(evidence_changed),
        'is_statistical_correction': any(
            field_category(field) == CATEGORY_STATISTICAL_CORRECTION
            for field in changed_fields
        ),
        'is_provenance_only': is_provenance_only,
    })
    return base


# Local surrogate identity is excluded from the digest. A projection cannot
# know the primary key a pitcher the writer would CREATE will receive, and the
# appearance is identified by (pitcher_mlb_id, game_pk) in the fingerprint
# tuple anyway — including the local id would make shadow and write differ for
# a reason that carries no baseball meaning.
_DIGEST_EXCLUDED_IDENTITY_FIELDS = frozenset({'pitcher_id'})


def mutation_digest(*, action, values, field_changes) -> str:
    """Digest of the VALUES a plan would write, not merely its shape.

    Without this, an insert of one earned run and an insert of seven fingerprint
    identically, and a reviewed plan would authorize a write of different
    numbers. Derived companions and provenance columns are excluded: the
    companion is a function of its authority (so including it would let float
    representation move the fingerprint, which D-008 forbids), and provenance
    is stamped by the act of correcting, not reviewed as evidence.
    """
    if action == ACTION_INSERT:
        payload = sorted(
            (field, _safe_value(value))
            for field, value in (values or {}).items()
            if field not in SEMANTIC_AUTHORITY_BY_COMPANION
            and field not in PROVENANCE_FIELDS
            and field not in _DIGEST_EXCLUDED_IDENTITY_FIELDS
        )
    elif action == ACTION_UPDATE:
        payload = sorted(
            (change['field'], change['after'])
            for change in (field_changes or ())
        )
    else:
        payload = []
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:32]


def plan_fingerprint(plans) -> str:
    """Deterministic fingerprint of a set of row plans.

    Covers the parity-relevant decision — action, natural key, changed fields,
    categories — AND the values that decision would write, so a reviewed
    fingerprint authorizes one specific mutation rather than a shape. Cosmetic
    plan additions do not look like drift, and a derived-companion
    representation difference cannot move it.
    """
    payload = sorted(
        (
            str(plan.get('game_pk')),
            str(plan.get('pitcher_mlb_id')),
            plan.get('action'),
            tuple(plan.get('changed_fields') or ()),
            tuple(plan.get('mutation_categories') or ()),
            plan.get('blocked_reason') or '',
            plan.get('mutation_digest') or '',
            # The identity decision and the values it would write. Without this
            # a reviewed fingerprint authorized only the GameLog half of a run.
            identity.fingerprint_component(plan.get('pitcher_identity')),
        )
        for plan in plans or ()
    )
    encoded = json.dumps(
        [PARITY_CONTRACT_VERSION, COMPLETE_PLAN_VERSION, payload],
        sort_keys=True, separators=(',', ':'), default=str,
    )
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def summarize(plans) -> dict:
    """Run-level aggregation over row plans. Deterministic ordering."""
    plans = list(plans or ())
    counts = {action: 0 for action in ACTIONS}
    changed_field_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    statistical = authority = provenance_only = 0
    canonical_outs_corrections = 0
    companion_applied = 0
    companion_ignored = 0

    for plan in plans:
        action = plan.get('action')
        if action in counts:
            counts[action] += 1
        for field in plan.get('changed_fields') or ():
            changed_field_counts[field] = changed_field_counts.get(field, 0) + 1
        for category in plan.get('mutation_categories') or ():
            category_counts[category] = category_counts.get(category, 0) + 1
        if plan.get('is_statistical_correction'):
            statistical += 1
        if plan.get('appearance_team_reason'):
            authority += 1
        if plan.get('is_provenance_only'):
            provenance_only += 1
        if any(
            authority_field in (plan.get('semantic_changed_fields') or ())
            for authority_field in SEMANTIC_AUTHORITY_BY_COMPANION.values()
        ):
            canonical_outs_corrections += 1
        if plan.get('derived_companion_fields'):
            companion_applied += 1
        # Counted once per ROW, so a row that both drifted and changed for a
        # real reason is never double-counted.
        if plan.get('derived_companion_differences_ignored'):
            companion_ignored += 1

    identity_summary = identity.summarize(
        [plan.get('pitcher_identity') for plan in plans]
    )
    # A run is only "no mutations" when EVERY target is untouched. Counting the
    # GameLog half alone is exactly how 942 planned identity writes reported as
    # zero.
    appearance_team_mutations = sum(
        1 for plan in plans if plan.get('appearance_team_reason')
    )
    complete_mutation_count = (
        counts[ACTION_INSERT]
        + counts[ACTION_UPDATE]
        + counts[ACTION_BLOCKED]
        + identity_summary['pitcher_identity_mutations']
        + identity_summary['pitcher_identity_blocked']
    )

    return {
        'rows_planned': len(plans),
        'rows_inserted': counts[ACTION_INSERT],
        'rows_updated': counts[ACTION_UPDATE],
        'rows_unchanged': counts[ACTION_UNCHANGED],
        'rows_blocked': counts[ACTION_BLOCKED],
        'changed_fields_counts': dict(sorted(changed_field_counts.items())),
        'mutation_category_counts': dict(sorted(category_counts.items())),
        'statistical_corrections': statistical,
        'authority_reconciliations': authority,
        'provenance_only_updates': provenance_only,
        'canonical_outs_corrections': canonical_outs_corrections,
        'derived_companion_fields_applied': companion_applied,
        'derived_companion_differences_ignored': companion_ignored,
        'decimal_only_updates_suppressed': companion_ignored,
        'innings_semantics_version': INNINGS_SEMANTICS_VERSION,
        'reconciliation_plan_version': RECONCILIATION_PLAN_VERSION,
        'parity_contract_version': PARITY_CONTRACT_VERSION,
        'complete_plan_version': COMPLETE_PLAN_VERSION,
        'appearance_team_mutations': appearance_team_mutations,
        'complete_mutation_count': complete_mutation_count,
        'reconciliation_plan_fingerprint': plan_fingerprint(plans),
        'complete_reconciliation_fingerprint': plan_fingerprint(plans),
        **identity_summary,
    }


def _ordered(values) -> list[str]:
    """Stable, de-duplicated category order (vocabulary order, not input order)."""
    present = set(values or ())
    return [category for category in CATEGORIES if category in present]


def _safe_value(value):
    """Render a governed baseball value for reporting.

    Only the governed field vocabulary above reaches this function, so no
    payload fragment, path, or credential can be carried into a report.
    """
    if value is None or isinstance(value, (int, float, bool, str)):
        return value
    return str(value)
