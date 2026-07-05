"""Internal Phase 0E reliever daily composed read."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import asc, desc

from models.composed_read import ComposedRead
from models.evidence_contract import EvidenceObject
from models.game_log import GameLog
from services.composed_read import ComponentInput, build_composed_read
from services.composed_read_registry import (
    ComponentSpec,
    ComposedReadTypeNotRegistered,
    ReadType,
    ReadTypeRegistry,
    read_type_registry,
)
from services.evidence_classification import EvidenceClassification
from services.roster_membership_evidence import (
    PITCHER_ROSTER_MEMBERSHIP_CONTEXT_RULE_ID,
    build_roster_membership_evidence,
    rebuild_marked_roster_membership_evidence,
)
from utils.db import db


READ_TYPE = 'reliever_daily_read'
READ_VERSION = 1
EVIDENCE_SOURCE = 'phase0e:reliever_daily_read'
LOOKBACK_DAYS = 30

WORKLOAD_EVIDENCE_TYPES = ('workload_recovery_fact',)
WORKLOAD_COMPONENT_RULE_IDS = (
    'workload_window_appearances',
    'workload_window_pitches',
    'workload_window_outs',
    'workload_window_batters_faced',
    'outing_multi_inning',
    'outing_high_pitch',
)
REST_COMPONENT_RULE_IDS = (
    'workload_last_final_appearance',
    'workload_days_of_rest',
    'usage_back_to_back',
    'usage_three_in_four',
    'usage_four_in_six',
    'appearance_short_rest',
)
RECENT_OUTING_EVIDENCE_TYPES = ('appearance_context_fact', 'inherited_traffic_fact')
RECENT_OUTING_COMPONENT_RULE_IDS = (
    'appearance_entry_context',
    'appearance_exit_context',
    'appearance_order_in_game',
    'appearance_innings_spanned',
    'appearance_game_phase',
    'appearance_inherited_runners',
    'appearance_inherited_runners_scored',
    'appearance_inherited_traffic_outcome',
    'outing_clean',
    'outing_traffic',
    'outing_context_unknown',
)
ROSTER_IL_EVIDENCE_TYPES = (
    PITCHER_ROSTER_MEMBERSHIP_CONTEXT_RULE_ID,
    'pitcher_il_placement_context',
    'pitcher_il_activation_context',
)
ROSTER_IL_COMPONENT_RULE_IDS = ROSTER_IL_EVIDENCE_TYPES
SITUATIONAL_EVIDENCE_TYPES = (
    'appearance_finish_context',
    'pitcher_save_hold_window',
)
SITUATIONAL_COMPONENT_RULE_IDS = SITUATIONAL_EVIDENCE_TYPES
USAGE_OBSERVATION_EVIDENCE_TYPES = (
    'pitcher_finish_usage_observation',
    'pitcher_multi_inning_usage_observation',
    'pitcher_first_reliever_usage_observation',
)
USAGE_OBSERVATION_COMPONENT_RULE_IDS = USAGE_OBSERVATION_EVIDENCE_TYPES
DATA_COMPLETENESS_EVIDENCE_TYPES = ('inherited_traffic_fact',)
DATA_COMPLETENESS_COMPONENT_RULE_IDS = ('outing_context_unknown',)

REQUIRED_COMPONENTS = (
    'workload_component',
    'rest_component',
    'recent_outing_component',
    'roster_il_context',
    'data_completeness_component',
)


def register_reliever_daily_read(
    *,
    registry: ReadTypeRegistry | None = None,
) -> ReadTypeRegistry:
    read_registry = registry or read_type_registry
    try:
        read_registry.get(READ_TYPE, READ_VERSION)
        return read_registry
    except ComposedReadTypeNotRegistered:
        pass

    read_registry.register(ReadType(
        read_type=READ_TYPE,
        read_version=READ_VERSION,
        subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
        plain_language_definition=(
            'The reliever daily read bundles, for one pitcher on one product day, '
            'the stored facts a bullpen reader needs: recent workload counts, '
            'rest and usage-density facts, the most recent relief outing\'s '
            'context, finishing/situational facts where present, public roster '
            'and IL facts, eligible usage observations, and a map of how complete '
            'the underlying data is. Every component cites stored evidence '
            'objects. The read deliberately concludes nothing: it assigns no '
            'availability, readiness, health, role, quality, or prediction, '
            'carries no single state, score, grade, or label, and degrades '
            'honestly - components with missing, stale, partial, contradictory, '
            'or below-threshold evidence say so instead of guessing. This read '
            'does not conclude anything beyond component completeness.'
        ),
        classification=EvidenceClassification.INTERNAL_ONLY_FOR_NOW,
        components=(
            ComponentSpec(
                name='workload_component',
                required=True,
                allowed_evidence_types=WORKLOAD_EVIDENCE_TYPES,
                plain_language_definition='Bundles recent workload-count evidence for the pitcher day.',
            ),
            ComponentSpec(
                name='rest_component',
                required=True,
                allowed_evidence_types=WORKLOAD_EVIDENCE_TYPES,
                plain_language_definition='Bundles stored rest and usage-density evidence.',
            ),
            ComponentSpec(
                name='recent_outing_component',
                required=True,
                allowed_evidence_types=RECENT_OUTING_EVIDENCE_TYPES,
                plain_language_definition='Bundles stored appearance and outing-context evidence for the recent relief outing.',
            ),
            ComponentSpec(
                name='roster_il_context',
                required=True,
                allowed_evidence_types=ROSTER_IL_EVIDENCE_TYPES,
                plain_language_definition='Bundles same-day roster membership and public IL-fact evidence.',
            ),
            ComponentSpec(
                name='situational_component',
                required=False,
                allowed_evidence_types=SITUATIONAL_EVIDENCE_TYPES,
                plain_language_definition='Optional stored finish and save-hold situation facts.',
            ),
            ComponentSpec(
                name='usage_observation_component',
                required=False,
                allowed_evidence_types=USAGE_OBSERVATION_EVIDENCE_TYPES,
                plain_language_definition='Optional stored floored usage observations.',
            ),
            ComponentSpec(
                name='data_completeness_component',
                required=True,
                allowed_evidence_types=DATA_COMPLETENESS_EVIDENCE_TYPES,
                plain_language_definition='Records source-family and component completeness states.',
            ),
        ),
    ))
    return read_registry


def build_reliever_daily_reads(
    product_date,
    *,
    pitcher_ids=None,
    sync_run_id=None,
    source='manual',
    commit=False,
) -> dict:
    ref = _as_date(product_date)
    register_reliever_daily_read()
    population = _relief_population_pitcher_ids(ref)
    if pitcher_ids is not None:
        allowed_pitchers = {int(item) for item in pitcher_ids}
        population = tuple(item for item in population if item in allowed_pitchers)
    membership_result = build_roster_membership_evidence(
        ref,
        pitcher_ids=population,
        sync_run_id=sync_run_id,
        source=source,
    )
    reads = []

    for pitcher_id in population:
        component_inputs = _component_inputs_for_pitcher(pitcher_id, ref)
        read = build_composed_read(
            read_type=READ_TYPE,
            read_version=READ_VERSION,
            subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
            subject_id=pitcher_id,
            subject_key=f'pitcher:{pitcher_id}:{ref.isoformat()}:reliever-daily-read',
            product_date=ref,
            component_inputs=component_inputs,
            sync_run_id=sync_run_id,
            source=EVIDENCE_SOURCE,
        )
        reads.append(read)

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return {
        'status': 'built',
        'product_date': ref.isoformat(),
        'read_type': READ_TYPE,
        'pitchers_considered': len(population),
        'reads_built': len(reads),
        'membership_evidence': membership_result,
    }


def rebuild_marked_reliever_daily_reads(
    *,
    sync_run_id=None,
    source='manual',
    batch_size=100,
) -> dict:
    membership_rebuild = rebuild_marked_roster_membership_evidence(
        sync_run_id=sync_run_id,
        source=source,
        batch_size=batch_size,
    )
    rows = (
        ComposedRead.query
        .filter(ComposedRead.read_type == READ_TYPE)
        .filter(ComposedRead.recompute_status == ComposedRead.RECOMPUTE_NEEDED)
        .order_by(asc(ComposedRead.product_date), asc(ComposedRead.id))
        .limit(batch_size)
        .all()
    )
    if not rows:
        return {
            'status': 'noop',
            'reads_rebuilt': 0,
            'dates_rebuilt': [],
            'membership_rebuild': membership_rebuild,
        }

    pitchers_by_date: dict[date, set[int]] = {}
    for row in rows:
        if row.subject_id is not None:
            pitchers_by_date.setdefault(row.product_date, set()).add(int(row.subject_id))

    rebuilt = 0
    for read_date, pitcher_ids in pitchers_by_date.items():
        result = build_reliever_daily_reads(
            read_date,
            pitcher_ids=sorted(pitcher_ids),
            sync_run_id=sync_run_id,
            source=source,
        )
        rebuilt += result['reads_built']

    db.session.flush()
    return {
        'status': 'rebuilt',
        'reads_rebuilt': rebuilt,
        'dates_rebuilt': [day.isoformat() for day in sorted(pitchers_by_date)],
        'membership_rebuild': membership_rebuild,
    }


def _component_inputs_for_pitcher(pitcher_id, product_date):
    pitcher_evidence = _pitcher_evidence(pitcher_id, product_date)
    membership = _evidence_by_rule(
        pitcher_evidence,
        (PITCHER_ROSTER_MEMBERSHIP_CONTEXT_RULE_ID,),
    )
    il_evidence = _evidence_by_rule(
        pitcher_evidence,
        ('pitcher_il_placement_context', 'pitcher_il_activation_context'),
    )
    components = {
        'workload_component': _required_component(
            _evidence_by_rule(pitcher_evidence, WORKLOAD_COMPONENT_RULE_IDS),
        ),
        'rest_component': _required_component(
            _evidence_by_rule(pitcher_evidence, REST_COMPONENT_RULE_IDS),
        ),
        'recent_outing_component': _required_component(
            _evidence_by_rule(pitcher_evidence, RECENT_OUTING_COMPONENT_RULE_IDS),
        ),
        'roster_il_context': _roster_il_component(membership, il_evidence),
    }

    situational = _evidence_by_rule(pitcher_evidence, SITUATIONAL_COMPONENT_RULE_IDS)
    if situational:
        components['situational_component'] = _optional_component(situational)

    usage_observation = _evidence_by_rule(
        pitcher_evidence,
        USAGE_OBSERVATION_COMPONENT_RULE_IDS,
    )
    if usage_observation:
        components['usage_observation_component'] = _optional_component(usage_observation)

    components['data_completeness_component'] = _data_completeness_component(
        components,
        _evidence_by_rule(pitcher_evidence, DATA_COMPLETENESS_COMPONENT_RULE_IDS),
    )
    return components


def _required_component(evidence_objects):
    if not evidence_objects:
        return ComponentInput(
            component_state=ComposedRead.COMPLETENESS_UNKNOWN,
            reason_codes=('component_evidence_unavailable',),
        )
    return ComponentInput(
        component_state=_worst_evidence_state(evidence_objects),
        evidence_objects=tuple(evidence_objects),
        reason_codes=_component_reason_codes(evidence_objects),
        limitations=_component_limitations(evidence_objects),
    )


def _optional_component(evidence_objects):
    return ComponentInput(
        component_state=_worst_evidence_state(evidence_objects),
        evidence_objects=tuple(evidence_objects),
        reason_codes=_component_reason_codes(evidence_objects),
        limitations=_component_limitations(evidence_objects),
    )


def _roster_il_component(membership, il_evidence):
    cited = tuple(membership + il_evidence)
    if not membership:
        return ComponentInput(
            component_state=ComposedRead.COMPLETENESS_UNKNOWN,
            reason_codes=('component_evidence_unavailable',),
        )
    state = _worst_evidence_state(cited)
    reasons = _component_reason_codes(cited)
    limitations = _component_limitations(cited)
    if membership and state != ComposedRead.COMPLETENESS_COMPLETE:
        reasons = tuple(_dedupe(list(reasons) + ['roster_membership_unknown']))
    if not il_evidence and state == ComposedRead.COMPLETENESS_COMPLETE:
        limitations = tuple(list(limitations) + ['no public IL fact cited'])
    return ComponentInput(
        component_state=state,
        evidence_objects=cited,
        reason_codes=reasons,
        limitations=limitations,
    )


def _data_completeness_component(components, unknown_context_evidence):
    state_parts = []
    reason_parts = []
    for name in REQUIRED_COMPONENTS[:-1]:
        component = components.get(name)
        state = component.component_state if component else 'absent'
        state_parts.append(f'{name}={state}')
        reasons = tuple(component.reason_codes or ()) if component else ()
        if reasons:
            reason_parts.append(f'{name} reasons: {", ".join(reasons)}')
    return ComponentInput(
        component_state=ComposedRead.COMPLETENESS_COMPLETE,
        evidence_objects=tuple(unknown_context_evidence),
        reason_codes=(),
        limitations=(
            'source families reviewed: game logs, roster snapshots, transactions, final play by play',
            'component states: ' + '; '.join(state_parts),
            'component reasons: ' + ('; '.join(reason_parts) if reason_parts else 'none'),
            'slate and window coverage validity follows cited component states',
        ),
    )


def _pitcher_evidence(pitcher_id, product_date):
    return (
        EvidenceObject.query
        .filter(EvidenceObject.subject_type == 'pitcher')
        .filter(EvidenceObject.subject_id == str(pitcher_id))
        .filter(EvidenceObject.product_date == product_date)
        .order_by(asc(EvidenceObject.evidence_type), desc(EvidenceObject.id))
        .all()
    )


def _evidence_by_rule(rows, rule_ids):
    allowed = set(rule_ids)
    return [row for row in rows if row.rule_id in allowed]


def _component_reason_codes(evidence_objects):
    values = []
    for evidence in evidence_objects:
        values.extend(evidence.reason_codes or [])
        if evidence.recompute_status == EvidenceObject.RECOMPUTE_NEEDED:
            values.append('component_evidence_superseded')
    return tuple(_dedupe(values))


def _component_limitations(evidence_objects):
    values = []
    for evidence in evidence_objects:
        values.extend(evidence.limitations or [])
    return tuple(_dedupe(values))


def _worst_evidence_state(evidence_objects):
    severity = {
        EvidenceObject.COMPLETENESS_COMPLETE: 0,
        EvidenceObject.COMPLETENESS_PARTIAL: 1,
        EvidenceObject.COMPLETENESS_UNKNOWN: 2,
        EvidenceObject.COMPLETENESS_CONFLICT: 3,
        EvidenceObject.COMPLETENESS_WITHHELD: 4,
    }
    worst = EvidenceObject.COMPLETENESS_COMPLETE
    worst_value = -1
    for evidence in evidence_objects:
        value = severity.get(evidence.completeness_state, 2)
        if value > worst_value:
            worst = evidence.completeness_state
            worst_value = value
    return worst


def _relief_population_pitcher_ids(product_date):
    start_date = product_date - timedelta(days=LOOKBACK_DAYS - 1)
    rows = (
        db.session.query(GameLog.pitcher_id)
        .filter(GameLog.game_date >= start_date)
        .filter(GameLog.game_date <= product_date)
        .filter(GameLog.games_started == 0)
        .distinct()
        .order_by(GameLog.pitcher_id.asc())
        .all()
    )
    return tuple(row[0] for row in rows)


def _as_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _dedupe(values):
    result = []
    seen = set()
    for value in values or []:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


register_reliever_daily_read()
