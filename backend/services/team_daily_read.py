"""Internal Phase 0E team daily composed read."""

from __future__ import annotations

from datetime import date
import re

from sqlalchemy import asc, desc

from models.composed_read import ComposedRead
from models.evidence_contract import EvidenceObject
from models.roster_status_snapshot import RosterStatusSnapshot
from services.composed_read import ComponentInput, build_composed_read
from services.composed_read_registry import (
    ComponentSpec,
    ComposedReadTypeNotRegistered,
    ReadType,
    ReadTypeRegistry,
    read_type_registry,
)
from services.evidence_classification import EvidenceClassification
from services.team_relief_composition_evidence import BASIS_DISCLAIMER
from utils.db import db


READ_TYPE = 'team_daily_read'
READ_VERSION = 1
EVIDENCE_SOURCE = 'phase0e:team_daily_read'

CONTRIBUTOR_COMPOSITION_RULE_IDS = (
    'team_relief_contributor_basis',
    'team_relief_rest_distribution',
    'team_relief_density_usage_count',
    'team_relief_workload_concentration',
    'team_relief_outing_context_mix',
    'team_relief_finish_spread',
)
EXPOSURE_RULE_IDS = (
    'team_bullpen_share_of_outs',
    'team_bullpen_outs_window',
    'team_bullpen_pitches_window',
    'team_reliever_appearances_window',
    'team_short_start_count_window',
)
CALENDAR_RULE_IDS = (
    'team_consecutive_game_days',
    'team_doubleheader_today',
    'team_recent_doubleheader',
    'team_off_day_yesterday',
    'team_off_day_tomorrow',
    'team_calendar_density',
)
ROSTER_CHURN_RULE_IDS = (
    'team_active_pitcher_census',
    'team_public_il_count',
    'team_transaction_churn_window',
    'team_transaction_category_counts_window',
    'team_option_recall_churn',
    'team_roster_movement_churn',
    'team_depth_delta_daily',
    'team_roster_changes_explained',
    'team_roster_changes_unexplained',
)
SLATE_DATA_COMPLETENESS_EVIDENCE_TYPES = ('inherited_traffic_fact',)
SLATE_DATA_COMPLETENESS_RULE_IDS = ('outing_context_unknown',)

REQUIRED_COMPONENTS = (
    'contributor_composition_component',
    'exposure_component',
    'roster_churn_component',
    'slate_data_completeness_component',
)

ROSTER_CHURN_FORBIDDEN_CONTENT = (
    'thin',
    'deep',
    'depth',
    'shakeup',
    'available',
    'quality',
)

READ_DEFINITION = (
    'The team daily read bundles, for one team on one product day, the '
    'stored facts describing its recent relief context: the recent relief '
    'contributor composition (an appearance-evidenced set — not the team\'s '
    'roster reliever count, which remains unknown by design), how much '
    'relief work the team has had to cover, public roster and transaction '
    'facts, calendar facts where present, and a map of how complete the '
    'underlying data is. Relief work is defined per game as pitching by '
    'pitchers who did not start that game. Every component cites stored '
    'evidence objects. The read deliberately concludes nothing: it assigns '
    'no team state, quality, depth, trust, availability, readiness, or '
    'prediction, carries no score, grade, rank, color, or tier, and '
    'degrades honestly when evidence is missing, stale, partial, '
    'contradictory, or below threshold.'
)


def register_team_daily_read(
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
        subject_type=ComposedRead.SUBJECT_TEAM_DAY,
        plain_language_definition=READ_DEFINITION,
        classification=EvidenceClassification.INTERNAL_ONLY_FOR_NOW,
        components=(
            ComponentSpec(
                name='contributor_composition_component',
                required=True,
                allowed_evidence_types=CONTRIBUTOR_COMPOSITION_RULE_IDS,
                plain_language_definition='Bundles existing team relief contributor composition facts.',
            ),
            ComponentSpec(
                name='exposure_component',
                required=True,
                allowed_evidence_types=EXPOSURE_RULE_IDS,
                plain_language_definition='Bundles existing team relief coverage facts.',
            ),
            ComponentSpec(
                name='calendar_component',
                required=False,
                allowed_evidence_types=CALENDAR_RULE_IDS,
                plain_language_definition='Optional existing team calendar facts.',
            ),
            ComponentSpec(
                name='roster_churn_component',
                required=True,
                allowed_evidence_types=ROSTER_CHURN_RULE_IDS,
                plain_language_definition='Bundles existing public roster and movement facts.',
            ),
            ComponentSpec(
                name='slate_data_completeness_component',
                required=True,
                allowed_evidence_types=SLATE_DATA_COMPLETENESS_EVIDENCE_TYPES,
                plain_language_definition='Records source-family and component completeness states.',
            ),
        ),
    ))
    return read_registry


def build_team_daily_reads(
    product_date,
    *,
    team_ids=None,
    sync_run_id=None,
    source='manual',
    commit=False,
) -> dict:
    ref = _as_date(product_date)
    register_team_daily_read()
    population = _team_population(ref)
    if team_ids is not None:
        allowed_team_ids = {int(item) for item in team_ids}
        population = tuple(team_id for team_id in population if team_id in allowed_team_ids)

    reads = []
    for team_id in population:
        component_inputs = _component_inputs_for_team(team_id, ref)
        read = build_composed_read(
            read_type=READ_TYPE,
            read_version=READ_VERSION,
            subject_type=ComposedRead.SUBJECT_TEAM_DAY,
            subject_id=team_id,
            subject_key=f'team:{team_id}:{ref.isoformat()}:team-daily-read',
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
        'teams_considered': len(population),
        'reads_built': len(reads),
    }


def rebuild_marked_team_daily_reads(
    *,
    sync_run_id=None,
    source='manual',
    batch_size=100,
) -> dict:
    rows = (
        ComposedRead.query
        .filter(ComposedRead.read_type == READ_TYPE)
        .filter(ComposedRead.recompute_status == ComposedRead.RECOMPUTE_NEEDED)
        .order_by(asc(ComposedRead.product_date), asc(ComposedRead.id))
        .limit(batch_size)
        .all()
    )
    if not rows:
        return {'status': 'noop', 'reads_rebuilt': 0, 'dates_rebuilt': []}

    teams_by_date: dict[date, set[int]] = {}
    for row in rows:
        if row.subject_id is not None:
            teams_by_date.setdefault(row.product_date, set()).add(int(row.subject_id))

    rebuilt = 0
    for read_date, ids in teams_by_date.items():
        result = build_team_daily_reads(
            read_date,
            team_ids=sorted(ids),
            sync_run_id=sync_run_id,
            source=source,
        )
        rebuilt += result['reads_built']

    db.session.flush()
    return {
        'status': 'rebuilt',
        'reads_rebuilt': rebuilt,
        'dates_rebuilt': [day.isoformat() for day in sorted(teams_by_date)],
    }


def assert_roster_churn_content_allowed(text: str) -> bool:
    lowered = f' {text or ""} '.lower()
    for term in ROSTER_CHURN_FORBIDDEN_CONTENT:
        if re.search(rf'\b{re.escape(term)}\b', lowered):
            raise AssertionError(f'forbidden roster_churn_component language: {term}')
    return True


def _component_inputs_for_team(team_id, product_date):
    rows = _team_evidence(team_id, product_date)
    components = {
        'contributor_composition_component': _contributor_component(
            _evidence_by_rule(rows, CONTRIBUTOR_COMPOSITION_RULE_IDS),
        ),
        'exposure_component': _required_component(
            _evidence_by_rule(rows, EXPOSURE_RULE_IDS),
        ),
        'roster_churn_component': _roster_churn_component(
            _evidence_by_rule(rows, ROSTER_CHURN_RULE_IDS),
        ),
    }
    calendar = _evidence_by_rule(rows, CALENDAR_RULE_IDS)
    if calendar:
        components['calendar_component'] = _optional_component(calendar)
    components['slate_data_completeness_component'] = _slate_data_completeness_component(
        components,
        _evidence_by_rule(rows, SLATE_DATA_COMPLETENESS_RULE_IDS),
    )
    return components


def _contributor_component(evidence_objects):
    limitations = _component_limitations(evidence_objects)
    if BASIS_DISCLAIMER not in limitations:
        limitations = tuple(list(limitations) + [BASIS_DISCLAIMER])
    if not evidence_objects:
        return ComponentInput(
            component_state=ComposedRead.COMPLETENESS_UNKNOWN,
            reason_codes=('component_evidence_unavailable',),
            limitations=limitations,
        )
    return ComponentInput(
        component_state=_worst_evidence_state(evidence_objects),
        evidence_objects=tuple(evidence_objects),
        reason_codes=_component_reason_codes(evidence_objects),
        limitations=limitations,
    )


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


def _roster_churn_component(evidence_objects):
    component = _required_component(evidence_objects)
    for value in tuple(component.reason_codes or ()) + tuple(component.limitations or ()):
        assert_roster_churn_content_allowed(value)
    return component


def _slate_data_completeness_component(components, unknown_context_evidence):
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
            'source families reviewed: team game pitching splits, roster snapshots, transactions, slate coverage, final play by play, phase zero d evidence contract',
            'component states: ' + '; '.join(state_parts),
            'component reasons: ' + ('; '.join(reason_parts) if reason_parts else 'none'),
            'slate coverage: follows cited evidence state; transaction coverage: follows roster churn evidence state',
        ),
    )


def _team_evidence(team_id, product_date):
    return (
        EvidenceObject.query
        .filter(EvidenceObject.subject_type == 'team')
        .filter(EvidenceObject.subject_id == str(team_id))
        .filter(EvidenceObject.product_date == product_date)
        .order_by(asc(EvidenceObject.rule_id), desc(EvidenceObject.id))
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


def _team_population(product_date):
    rows = (
        RosterStatusSnapshot.query
        .filter(RosterStatusSnapshot.snapshot_date <= product_date)
        .order_by(
            asc(RosterStatusSnapshot.team_id),
            desc(RosterStatusSnapshot.snapshot_date),
            asc(RosterStatusSnapshot.id),
        )
        .all()
    )
    latest_by_team = {}
    for row in rows:
        current = latest_by_team.get(row.team_id)
        if current is None or row.snapshot_date > current:
            latest_by_team[row.team_id] = row.snapshot_date
    return tuple(sorted(latest_by_team))


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


register_team_daily_read()
