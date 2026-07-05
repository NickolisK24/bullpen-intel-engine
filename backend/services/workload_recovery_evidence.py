"""Internal Phase 0D workload and recovery evidence family."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import asc

from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import slate_coverage
from services.evidence_contract import (
    EvidenceCitationInput,
    build_evidence_object,
    mark_dependent_evidence_for_recompute,
)
from services.evidence_language import (
    EvidenceLanguageError,
    assert_claim_language_allowed,
)
from services.evidence_rules import (
    ClaimTemplate,
    ClaimTemplateRegistry,
    EvidenceRule,
    EvidenceRuleError,
    EvidenceRuleRegistry,
)
from utils.db import db


RULE_VERSION = 1
EVIDENCE_TYPE = 'workload_recovery_fact'
EVIDENCE_SOURCE = 'phase0d:workload_recovery_evidence'
REQUIRED_INPUT_FAMILIES = ('game_logs', 'slate_coverage')
REQUIRED_CITED_FIELDS = ('slate_coverage.slate_date',)

LOOKBACK_DAYS = 30
WINDOW_DAYS = (3, 5, 7, 14)
MULTI_INNING_OUTS = 4
HIGH_PITCH_THRESHOLD = 25
SHORT_REST_MAX_FULL_OFF_DAYS = 1
THREE_IN_FOUR_DAYS = 4
THREE_IN_FOUR_MIN_DAYS = 3
FOUR_IN_SIX_DAYS = 6
FOUR_IN_SIX_MIN_DAYS = 4

REASON_INCOMPLETE_SLATE_DAY = 'incomplete_slate_day_in_window'
REASON_REST_COVERAGE_GAP = 'rest_window_coverage_gap'
REASON_UNKNOWN_PITCH_COUNT = 'unknown_pitch_count_in_window'
REASON_UNKNOWN_BATTERS_FACED = 'unknown_batters_faced_in_window'
REASON_UNKNOWN_OUTING_PITCH_COUNT = 'unknown_pitch_count_for_outing'
REASON_APPEARANCE_ROLE_UNKNOWN = 'appearance_role_unknown'
REASON_NO_RECENT_APPEARANCE = 'no_recent_appearance_in_lookback'
REASON_WINDOW_PRECEDES_COVERAGE = 'window_precedes_coverage_history'
REASON_AMBIGUOUS_RESUMED_GAME = 'ambiguous_resumed_game_in_window'
REASON_SOURCE_FAMILY_NOT_READY = 'source_family_not_ready'
REASON_GAME_LOG_CORRECTED = 'game_log_corrected'

WORKLOAD_RULE_IDS = (
    'workload_last_final_appearance',
    'workload_days_of_rest',
    'workload_window_appearances',
    'workload_window_pitches',
    'workload_window_outs',
    'workload_window_batters_faced',
    'usage_back_to_back',
    'usage_three_in_four',
    'usage_four_in_six',
    'outing_multi_inning',
    'outing_high_pitch',
    'appearance_short_rest',
)

_FORBIDDEN_WORKLOAD_CLAIM_TERMS = (
    'availability',
    'available',
    'freshness',
    'fresh',
    'fatigue',
    'fatigued',
    'readiness',
    'ready',
    'trust',
    'confidence',
    'pressure',
    'prediction',
    'score',
    'grade',
    'rank',
    'rested',
)

_RULE_DEFINITIONS = {
    'workload_last_final_appearance': (
        'Records the pitcher last final appearance date and game within the '
        'trailing 30 product-day lookback ending on the evidence date.'
    ),
    'workload_days_of_rest': (
        'Records the count of full off-days between the pitcher most recent '
        'final appearance and the evidence date within the trailing 30 '
        'product-day lookback.'
    ),
    'workload_window_appearances': (
        'Counts final appearances in each trailing 3, 5, 7, and 14 product-day '
        'window ending on the evidence date; doubleheader appearances count as '
        'separate appearances on one distinct appearance day.'
    ),
    'workload_window_pitches': (
        'Sums pitches thrown in final appearances for each trailing 3, 5, 7, '
        'and 14 product-day window ending on the evidence date when every '
        'included pitch count is known.'
    ),
    'workload_window_outs': (
        'Sums outs recorded in final appearances for each trailing 3, 5, 7, '
        'and 14 product-day window ending on the evidence date.'
    ),
    'workload_window_batters_faced': (
        'Sums batters faced in final appearances for each trailing 3, 5, 7, '
        'and 14 product-day window ending on the evidence date when every '
        'included batters-faced count is known.'
    ),
    'usage_back_to_back': (
        'Records that a relief-scoped appearance occurred on the evidence date '
        'and on the immediately prior product day.'
    ),
    'usage_three_in_four': (
        'Records that relief-scoped appearances occurred on at least 3 '
        'distinct appearance days in the trailing 4 product days ending on the '
        'evidence date.'
    ),
    'usage_four_in_six': (
        'Records that relief-scoped appearances occurred on at least 4 '
        'distinct appearance days in the trailing 6 product days ending on the '
        'evidence date.'
    ),
    'outing_multi_inning': (
        'Records a relief-scoped outing on the evidence date with at least 4 '
        'outs recorded.'
    ),
    'outing_high_pitch': (
        'Records a relief-scoped outing on the evidence date with at least 25 '
        'pitches thrown.'
    ),
    'appearance_short_rest': (
        'Records a relief-scoped appearance on the evidence date with at most '
        '1 full off-day since the previous final appearance.'
    ),
}

_RULE_THRESHOLDS = {
    'workload_last_final_appearance': {'lookback_days': LOOKBACK_DAYS},
    'workload_days_of_rest': {'lookback_days': LOOKBACK_DAYS},
    'workload_window_appearances': {
        'window_3': 3,
        'window_5': 5,
        'window_7': 7,
        'window_14': 14,
    },
    'workload_window_pitches': {
        'window_3': 3,
        'window_5': 5,
        'window_7': 7,
        'window_14': 14,
    },
    'workload_window_outs': {
        'window_3': 3,
        'window_5': 5,
        'window_7': 7,
        'window_14': 14,
    },
    'workload_window_batters_faced': {
        'window_3': 3,
        'window_5': 5,
        'window_7': 7,
        'window_14': 14,
    },
    'usage_three_in_four': {
        'minimum_distinct_days': THREE_IN_FOUR_MIN_DAYS,
        'window_days': THREE_IN_FOUR_DAYS,
    },
    'usage_four_in_six': {
        'minimum_distinct_days': FOUR_IN_SIX_MIN_DAYS,
        'window_days': FOUR_IN_SIX_DAYS,
    },
    'outing_multi_inning': {'minimum_outs': MULTI_INNING_OUTS},
    'outing_high_pitch': {'minimum_pitches': HIGH_PITCH_THRESHOLD},
    'appearance_short_rest': {'max_full_off_days': SHORT_REST_MAX_FULL_OFF_DAYS},
}


@dataclass(frozen=True)
class BuiltWorkloadEvidence:
    evidence: EvidenceObject
    rule_id: str
    subject_key: str


_LOCAL_RULE_REGISTRY: EvidenceRuleRegistry | None = None
_LOCAL_TEMPLATE_REGISTRY: ClaimTemplateRegistry | None = None


def workload_rule_definitions() -> dict[str, str]:
    return dict(_RULE_DEFINITIONS)


def workload_rule_ids() -> tuple[str, ...]:
    return WORKLOAD_RULE_IDS


def register_workload_recovery_rules(
    *,
    registry: EvidenceRuleRegistry | None = None,
    template_registry: ClaimTemplateRegistry | None = None,
) -> tuple[EvidenceRuleRegistry, ClaimTemplateRegistry]:
    rule_registry = registry or EvidenceRuleRegistry()
    claim_registry = template_registry or ClaimTemplateRegistry()
    for rule_id in WORKLOAD_RULE_IDS:
        _register_workload_rule(rule_registry, _workload_rule(rule_id))
        _register_workload_template(
            claim_registry,
            ClaimTemplate(
                template_id=_template_id(rule_id),
                template_version=RULE_VERSION,
                template_text='{claim}',
            ),
        )
    return rule_registry, claim_registry


def build_workload_recovery_evidence(
    product_date,
    *,
    sync_run_id=None,
    source='manual',
    commit=False,
    restrict_evidence_keys: set[str] | None = None,
) -> dict:
    """Build internal workload evidence for one product date."""
    ref = _as_date(product_date)
    registry, templates = _local_registries()
    coverage = _CoverageCache(ref)
    pitchers = _population_pitcher_ids(ref)
    rows_by_pitcher = _pitcher_rows_by_id(pitchers, ref)
    evidence_to_upsert = []

    for pitcher_id in pitchers:
        rows = rows_by_pitcher.get(pitcher_id, ())
        built = _build_for_pitcher(
            pitcher_id=pitcher_id,
            product_date=ref,
            rows=rows,
            coverage=coverage,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
        for item in built:
            if restrict_evidence_keys is not None and item.evidence.evidence_key not in restrict_evidence_keys:
                continue
            evidence_to_upsert.append(item.evidence)

    emitted = _upsert_evidence_batch(evidence_to_upsert)
    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return {
        'status': 'built',
        'product_date': ref.isoformat(),
        'rules': list(WORKLOAD_RULE_IDS),
        'pitchers_considered': len(pitchers),
        'objects_built': len(emitted),
        'objects_created': sum(1 for item in emitted if item == 'created'),
        'objects_refreshed': sum(1 for item in emitted if item == 'refreshed'),
    }


def mark_game_log_correction_for_workload_recovery(
    game_log,
    *,
    sync_run_id=None,
    reason_code=REASON_GAME_LOG_CORRECTED,
    batch_size=100,
) -> dict:
    if game_log is None or getattr(game_log, 'id', None) is None:
        return {'marked_count': 0, 'evidence_ids': []}
    return mark_dependent_evidence_for_recompute(
        source_table='game_logs',
        source_pk=game_log.id,
        reason_code=reason_code,
        batch_size=batch_size,
        sync_run_id=sync_run_id,
    )


def rebuild_marked_workload_recovery_evidence(
    *,
    sync_run_id=None,
    source='manual',
    batch_size=100,
) -> dict:
    rows = (
        EvidenceObject.query
        .filter(EvidenceObject.rule_id.in_(WORKLOAD_RULE_IDS))
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_NEEDED)
        .order_by(asc(EvidenceObject.product_date), asc(EvidenceObject.id))
        .limit(batch_size)
        .all()
    )
    if not rows:
        return {'status': 'noop', 'objects_rebuilt': 0, 'dates_rebuilt': []}

    keys_by_date = defaultdict(set)
    for row in rows:
        keys_by_date[row.product_date].add(row.evidence_key)

    rebuilt = 0
    for evidence_date, keys in keys_by_date.items():
        result = build_workload_recovery_evidence(
            evidence_date,
            sync_run_id=sync_run_id,
            source=source,
            restrict_evidence_keys=keys,
        )
        rebuilt += result['objects_created'] + result['objects_refreshed']

    db.session.flush()
    return {
        'status': 'rebuilt',
        'objects_rebuilt': rebuilt,
        'dates_rebuilt': [day.isoformat() for day in sorted(keys_by_date)],
    }


def _local_registries():
    global _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY
    if _LOCAL_RULE_REGISTRY is None or _LOCAL_TEMPLATE_REGISTRY is None:
        _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY = register_workload_recovery_rules()
    return _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY


def _workload_rule(rule_id):
    return EvidenceRule(
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        evidence_type=EVIDENCE_TYPE,
        plain_language_definition=_RULE_DEFINITIONS[rule_id],
        required_input_families=REQUIRED_INPUT_FAMILIES,
        required_cited_fields=REQUIRED_CITED_FIELDS,
        posture_default=EvidenceObject.POSTURE_INTERNAL_ONLY,
        thresholds=_RULE_THRESHOLDS.get(rule_id, {}),
    )


def _register_workload_rule(registry, rule):
    if rule.posture_default != EvidenceObject.POSTURE_INTERNAL_ONLY:
        raise EvidenceRuleError('workload recovery evidence must remain internal_only')
    _assert_text_has_no_workload_forbidden_terms(rule.plain_language_definition)
    return registry.register(rule)


def _register_workload_template(registry, template):
    _assert_text_has_no_workload_forbidden_terms(template.template_text)
    return registry.register(template)


def _assert_text_has_no_workload_forbidden_terms(text):
    lowered = f' {text or ""} '.lower()
    for term in _FORBIDDEN_WORKLOAD_CLAIM_TERMS:
        if f' {term} ' in lowered:
            raise EvidenceLanguageError(f'workload claim language uses forbidden term: {term}')
    assert_claim_language_allowed(text)
    return True


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _population_pitcher_ids(product_date):
    start = product_date - timedelta(days=LOOKBACK_DAYS - 1)
    recent = {
        row[0]
        for row in (
            db.session.query(GameLog.pitcher_id)
            .filter(GameLog.game_date >= start)
            .filter(GameLog.game_date <= product_date)
            .distinct()
            .all()
        )
    }
    historical_active = {
        row[0]
        for row in (
            db.session.query(GameLog.pitcher_id)
            .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
            .filter(Pitcher.active == True)
            .filter(GameLog.game_date < start)
            .filter(GameLog.game_date <= product_date)
            .distinct()
            .all()
        )
    }
    return tuple(sorted(recent | historical_active))


def _pitcher_rows(pitcher_id, product_date):
    start = product_date - timedelta(days=LOOKBACK_DAYS - 1)
    return (
        GameLog.query
        .filter(GameLog.pitcher_id == pitcher_id)
        .filter(GameLog.game_date >= start)
        .filter(GameLog.game_date <= product_date)
        .order_by(asc(GameLog.game_date), asc(GameLog.id))
        .all()
    )


def _pitcher_rows_by_id(pitcher_ids, product_date):
    ids = tuple(pitcher_ids or ())
    if not ids:
        return {}
    start = product_date - timedelta(days=LOOKBACK_DAYS - 1)
    rows = (
        GameLog.query
        .filter(GameLog.pitcher_id.in_(ids))
        .filter(GameLog.game_date >= start)
        .filter(GameLog.game_date <= product_date)
        .order_by(asc(GameLog.pitcher_id), asc(GameLog.game_date), asc(GameLog.id))
        .all()
    )
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.pitcher_id].append(row)
    return grouped


def _build_for_pitcher(
    *,
    pitcher_id,
    product_date,
    rows,
    coverage,
    registry,
    templates,
    sync_run_id,
    source,
):
    rows = list(rows or [])
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)

    built = []
    built.append(_last_appearance_object(
        pitcher_id, product_date, rows, coverage, registry, templates, sync_run_id, source
    ))
    if rows:
        built.append(_days_of_rest_object(
            pitcher_id, product_date, rows, coverage, registry, templates, sync_run_id, source
        ))
    for window_days in WINDOW_DAYS:
        window_rows = _window_rows(rows, product_date, window_days)
        window = coverage.window(product_date, window_days)
        built.append(_appearance_count_object(
            pitcher_id,
            product_date,
            window_days,
            window_rows,
            window,
            registry,
            templates,
            sync_run_id,
            source,
        ))
        if window_rows:
            built.append(_sum_object(
                'workload_window_pitches',
                pitcher_id,
                product_date,
                window_days,
                window_rows,
                window,
                'pitches_thrown',
                'pitches',
                REASON_UNKNOWN_PITCH_COUNT,
                registry,
                templates,
                sync_run_id,
                source,
            ))
            built.append(_sum_object(
                'workload_window_outs',
                pitcher_id,
                product_date,
                window_days,
                window_rows,
                window,
                'innings_pitched_outs',
                'outs',
                None,
                registry,
                templates,
                sync_run_id,
                source,
            ))
            built.append(_sum_object(
                'workload_window_batters_faced',
                pitcher_id,
                product_date,
                window_days,
                window_rows,
                window,
                'batters_faced',
                'batters faced',
                REASON_UNKNOWN_BATTERS_FACED,
                registry,
                templates,
                sync_run_id,
                source,
            ))

    built.extend(_flag_objects(
        pitcher_id=pitcher_id,
        product_date=product_date,
        rows=rows,
        by_date=by_date,
        coverage=coverage,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    ))
    return [item for item in built if item is not None]


def _last_appearance_object(
    pitcher_id, product_date, rows, coverage, registry, templates, sync_run_id, source
):
    rule_id = 'workload_last_final_appearance'
    if not rows:
        window = coverage.window(product_date, LOOKBACK_DAYS)
        claim = (
            f'No final appearance is recorded for pitcher {pitcher_id} in the '
            f'30 product-day lookback ending {product_date.isoformat()}.'
        )
        return _build_object(
            rule_id=rule_id,
            pitcher_id=pitcher_id,
            product_date=product_date,
            subject_suffix='lookback-30',
            claim=claim,
            cited_inputs=window.coverage_citations(),
            input_values={'lookback_days': LOOKBACK_DAYS},
            trace={
                'steps': ['Checked final game logs in the 30 product-day lookback.'],
                'notes': ['No final appearance row found in the bounded lookback.'],
                'lookback_days': LOOKBACK_DAYS,
            },
            state=EvidenceObject.COMPLETENESS_COMPLETE,
            reason_codes=[REASON_NO_RECENT_APPEARANCE],
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )

    latest = rows[-1]
    claim = (
        f'Last final appearance for pitcher {pitcher_id} was '
        f'{latest.game_date.isoformat()} in game {latest.mlb_game_pk}.'
    )
    return _build_object(
        rule_id=rule_id,
        pitcher_id=pitcher_id,
        product_date=product_date,
        subject_suffix='lookback-30',
        claim=claim,
        cited_inputs=(
            _game_log_citation(
                latest,
                ('game_date', 'mlb_game_pk'),
            ),
            coverage.day(product_date).citation(),
        ),
        input_values={
            'game_logs.game_date': latest.game_date.isoformat(),
            'game_logs.mlb_game_pk': latest.mlb_game_pk,
        },
        trace={
            'steps': ['Selected the latest final game-log row in the 30 product-day lookback.'],
            'lookback_days': LOOKBACK_DAYS,
            'appearance_date': latest.game_date.isoformat(),
        },
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _days_of_rest_object(
    pitcher_id, product_date, rows, coverage, registry, templates, sync_run_id, source
):
    latest = rows[-1]
    days = max((product_date - latest.game_date).days - 1, 0)
    claim = (
        f'Pitcher {pitcher_id} has {days} full off-days since the last final '
        f'appearance on {latest.game_date.isoformat()}.'
    )
    return _build_object(
        rule_id='workload_days_of_rest',
        pitcher_id=pitcher_id,
        product_date=product_date,
        subject_suffix='lookback-30',
        claim=claim,
        cited_inputs=(
            _game_log_citation(latest, ('game_date', 'mlb_game_pk')),
            coverage.day(product_date).citation(),
        ),
        input_values={'days_of_rest': days},
        trace={
            'steps': ['Counted full off-days after the most recent final appearance.'],
            'last_appearance_date': latest.game_date.isoformat(),
            'full_off_days': days,
        },
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _appearance_count_object(
    pitcher_id,
    product_date,
    window_days,
    window_rows,
    window,
    registry,
    templates,
    sync_run_id,
    source,
):
    count = len(window_rows)
    distinct_days = len({row.game_date for row in window_rows})
    citations = tuple(
        [_game_log_citation(row, ('game_date', 'mlb_game_pk')) for row in window_rows]
        + list(window.coverage_citations())
    )
    if window.complete:
        claim = (
            f'Pitcher {pitcher_id} recorded {count} final appearances across '
            f'{distinct_days} distinct appearance days in the trailing '
            f'{window_days} product days.'
        )
        state = EvidenceObject.COMPLETENESS_COMPLETE
        reasons = []
    else:
        claim = (
            f'At least {count} final appearances are recorded for pitcher '
            f'{pitcher_id} in the trailing {window_days} product days; window '
            f'coverage is incomplete for {", ".join(window.incomplete_day_labels)}.'
        )
        state = EvidenceObject.COMPLETENESS_PARTIAL
        reasons = window.reason_codes

    return _build_object(
        rule_id='workload_window_appearances',
        pitcher_id=pitcher_id,
        product_date=product_date,
        subject_suffix=f'window-{window_days}',
        claim=claim,
        cited_inputs=citations,
        input_values={'appearance_count': count, 'distinct_appearance_days': distinct_days},
        trace={
            'steps': ['Counted final game-log appearance rows in the product-day window.'],
            'window_days': window_days,
            'window_start': window.start.isoformat(),
            'window_end': product_date.isoformat(),
            'appearance_count': count,
            'distinct_appearance_days': distinct_days,
            'incomplete_days': window.incomplete_day_labels,
        },
        state=state,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _sum_object(
    rule_id,
    pitcher_id,
    product_date,
    window_days,
    window_rows,
    window,
    field_name,
    label,
    unknown_reason,
    registry,
    templates,
    sync_run_id,
    source,
):
    citations = tuple(
        [_game_log_citation(row, ('game_date', 'mlb_game_pk', field_name)) for row in window_rows]
        + list(window.coverage_citations())
    )
    known_values = [
        getattr(row, field_name)
        for row in window_rows
        if getattr(row, field_name) is not None
    ]
    known_count = len(known_values)
    known_subtotal = sum(known_values)

    if not window.complete:
        claim = (
            f'{label.title()} total is unknown for pitcher {pitcher_id} in the '
            f'trailing {window_days} product days because window coverage is '
            f'incomplete for {", ".join(window.incomplete_day_labels)}.'
        )
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        reasons = window.reason_codes
    elif known_count != len(window_rows):
        claim = (
            f'{label.title()} total is unknown for pitcher {pitcher_id} in the '
            f'trailing {window_days} product days; known subtotal is '
            f'{known_subtotal} across {known_count} cited row(s).'
        )
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        reasons = [unknown_reason]
    else:
        claim = (
            f'Pitcher {pitcher_id} recorded {known_subtotal} {label} in the '
            f'trailing {window_days} product days.'
        )
        state = EvidenceObject.COMPLETENESS_COMPLETE
        reasons = []

    return _build_object(
        rule_id=rule_id,
        pitcher_id=pitcher_id,
        product_date=product_date,
        subject_suffix=f'window-{window_days}',
        claim=claim,
        cited_inputs=citations,
        input_values={
            field_name: known_subtotal if state == EvidenceObject.COMPLETENESS_COMPLETE else 'unknown',
            'known_count': known_count,
            'known_subtotal': known_subtotal,
        },
        trace={
            'steps': [f'Summed {field_name} across cited final game-log rows.'],
            'window_days': window_days,
            'window_start': window.start.isoformat(),
            'window_end': product_date.isoformat(),
            'row_count': len(window_rows),
            'known_count': known_count,
            'known_subtotal': known_subtotal,
            'incomplete_days': window.incomplete_day_labels,
        },
        state=state,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _flag_objects(
    *,
    pitcher_id,
    product_date,
    rows,
    by_date,
    coverage,
    registry,
    templates,
    sync_run_id,
    source,
):
    today_rows = list(by_date.get(product_date) or [])
    if not today_rows:
        return []

    emitted = []
    current_relief = _relief_rows(today_rows)
    if _has_unknown_role(today_rows):
        emitted.extend(_role_unknown_flags(
            pitcher_id, product_date, today_rows, coverage, registry, templates, sync_run_id, source
        ))
        return emitted

    if not current_relief:
        return emitted

    back_to_back = _back_to_back_object(
        pitcher_id, product_date, rows, coverage, registry, templates, sync_run_id, source
    )
    if back_to_back is not None:
        emitted.append(back_to_back)
    three = _distinct_day_pattern_object(
        'usage_three_in_four',
        pitcher_id,
        product_date,
        rows,
        coverage,
        THREE_IN_FOUR_DAYS,
        THREE_IN_FOUR_MIN_DAYS,
        registry,
        templates,
        sync_run_id,
        source,
    )
    if three is not None:
        emitted.append(three)
    four = _distinct_day_pattern_object(
        'usage_four_in_six',
        pitcher_id,
        product_date,
        rows,
        coverage,
        FOUR_IN_SIX_DAYS,
        FOUR_IN_SIX_MIN_DAYS,
        registry,
        templates,
        sync_run_id,
        source,
    )
    if four is not None:
        emitted.append(four)

    multi = [row for row in current_relief if (row.innings_pitched_outs or 0) >= MULTI_INNING_OUTS]
    if multi:
        emitted.append(_outing_flag_object(
            'outing_multi_inning',
            pitcher_id,
            product_date,
            multi,
            coverage,
            f'Pitcher {pitcher_id} recorded a relief-scoped outing with at least '
            f'4 outs on {product_date.isoformat()}.',
            {'minimum_outs': MULTI_INNING_OUTS},
            registry,
            templates,
            sync_run_id,
            source,
        ))

    if any(row.pitches_thrown is None for row in current_relief):
        emitted.append(_unknown_outing_flag(
            'outing_high_pitch',
            pitcher_id,
            product_date,
            current_relief,
            coverage,
            REASON_UNKNOWN_OUTING_PITCH_COUNT,
            'Pitch count for a relief-scoped outing is unknown on '
            f'{product_date.isoformat()}.',
            registry,
            templates,
            sync_run_id,
            source,
        ))
    else:
        high_pitch = [row for row in current_relief if row.pitches_thrown >= HIGH_PITCH_THRESHOLD]
        if high_pitch:
            emitted.append(_outing_flag_object(
                'outing_high_pitch',
                pitcher_id,
                product_date,
                high_pitch,
                coverage,
                f'Pitcher {pitcher_id} recorded a relief-scoped outing with at least '
                f'25 pitches on {product_date.isoformat()}.',
                {'minimum_pitches': HIGH_PITCH_THRESHOLD},
                registry,
                templates,
                sync_run_id,
                source,
            ))

    short_rest = _short_rest_object(
        pitcher_id, product_date, rows, coverage, registry, templates, sync_run_id, source
    )
    if short_rest is not None:
        emitted.append(short_rest)
    return emitted


def _role_unknown_flags(
    pitcher_id, product_date, today_rows, coverage, registry, templates, sync_run_id, source
):
    citations = tuple(
        [_game_log_citation(row, ('game_date', 'mlb_game_pk', 'games_started')) for row in today_rows]
        + [coverage.day(product_date).citation()]
    )
    claim = (
        f'Relief-scoped outing flags are unknown for pitcher {pitcher_id} on '
        f'{product_date.isoformat()} because a cited appearance row has no '
        'games-started value.'
    )
    emitted = []
    for rule_id in (
        'usage_back_to_back',
        'usage_three_in_four',
        'usage_four_in_six',
        'outing_multi_inning',
        'outing_high_pitch',
        'appearance_short_rest',
    ):
        emitted.append(_build_object(
            rule_id=rule_id,
            pitcher_id=pitcher_id,
            product_date=product_date,
            subject_suffix='evidence-date',
            claim=claim,
            cited_inputs=citations,
            input_values={'games_started': 'unknown'},
            trace={
                'steps': ['Checked games_started before emitting relief-scoped flags.'],
                'unknown_game_log_ids': [row.id for row in today_rows if row.games_started is None],
            },
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=[REASON_APPEARANCE_ROLE_UNKNOWN],
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        ))
    return emitted


def _back_to_back_object(
    pitcher_id, product_date, rows, coverage, registry, templates, sync_run_id, source
):
    window = coverage.window(product_date, 2)
    window_rows = _window_rows(rows, product_date, 2)
    citations = tuple(
        [_game_log_citation(row, ('game_date', 'mlb_game_pk', 'games_started')) for row in window_rows]
        + list(window.coverage_citations())
    )
    if not window.complete:
        return _build_object(
            rule_id='usage_back_to_back',
            pitcher_id=pitcher_id,
            product_date=product_date,
            subject_suffix='evidence-date',
            claim=(
                f'Back-to-back usage is unknown for pitcher {pitcher_id} because '
                f'coverage is incomplete for {", ".join(window.incomplete_day_labels)}.'
            ),
            cited_inputs=citations,
            input_values={'pattern': 'unknown'},
            trace={'steps': ['Checked two-day product window coverage.']},
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=[REASON_REST_COVERAGE_GAP],
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    days = {row.game_date for row in _relief_rows(window_rows)}
    if product_date in days and (product_date - timedelta(days=1)) in days:
        return _build_object(
            rule_id='usage_back_to_back',
            pitcher_id=pitcher_id,
            product_date=product_date,
            subject_suffix='evidence-date',
            claim=(
                f'Pitcher {pitcher_id} recorded relief-scoped appearances on '
                f'{(product_date - timedelta(days=1)).isoformat()} and '
                f'{product_date.isoformat()}.'
            ),
            cited_inputs=citations,
            input_values={'distinct_appearance_days': 2},
            trace={'steps': ['Checked appearances on consecutive product days.']},
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    return None


def _distinct_day_pattern_object(
    rule_id,
    pitcher_id,
    product_date,
    rows,
    coverage,
    window_days,
    minimum_days,
    registry,
    templates,
    sync_run_id,
    source,
):
    window = coverage.window(product_date, window_days)
    window_rows = _window_rows(rows, product_date, window_days)
    citations = tuple(
        [_game_log_citation(row, ('game_date', 'mlb_game_pk', 'games_started')) for row in window_rows]
        + list(window.coverage_citations())
    )
    if not window.complete:
        return _build_object(
            rule_id=rule_id,
            pitcher_id=pitcher_id,
            product_date=product_date,
            subject_suffix='evidence-date',
            claim=(
                f'{minimum_days}-in-{window_days} usage is unknown for pitcher '
                f'{pitcher_id} because coverage is incomplete for '
                f'{", ".join(window.incomplete_day_labels)}.'
            ),
            cited_inputs=citations,
            input_values={'pattern': 'unknown'},
            trace={'steps': [f'Checked trailing {window_days} product-day coverage.']},
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=window.reason_codes,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    days = {row.game_date for row in _relief_rows(window_rows)}
    if product_date in days and len(days) >= minimum_days:
        return _build_object(
            rule_id=rule_id,
            pitcher_id=pitcher_id,
            product_date=product_date,
            subject_suffix='evidence-date',
            claim=(
                f'Pitcher {pitcher_id} recorded relief-scoped appearances on '
                f'{len(days)} distinct appearance days in the trailing '
                f'{window_days} product days.'
            ),
            cited_inputs=citations,
            input_values={'distinct_appearance_days': len(days), 'window_days': window_days},
            trace={
                'steps': [f'Counted distinct appearance days in trailing {window_days} product days.'],
                'appearance_days': [day.isoformat() for day in sorted(days)],
            },
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    return None


def _outing_flag_object(
    rule_id,
    pitcher_id,
    product_date,
    rows,
    coverage,
    claim,
    input_values,
    registry,
    templates,
    sync_run_id,
    source,
):
    return _build_object(
        rule_id=rule_id,
        pitcher_id=pitcher_id,
        product_date=product_date,
        subject_suffix='evidence-date',
        claim=claim,
        cited_inputs=tuple(
            [_game_log_citation(
                row,
                ('game_date', 'mlb_game_pk', 'games_started', 'innings_pitched_outs', 'pitches_thrown'),
            ) for row in rows]
            + [coverage.day(product_date).citation()]
        ),
        input_values=input_values,
        trace={'steps': ['Checked relief-scoped outing threshold on the evidence date.']},
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _unknown_outing_flag(
    rule_id,
    pitcher_id,
    product_date,
    rows,
    coverage,
    reason_code,
    claim,
    registry,
    templates,
    sync_run_id,
    source,
):
    return _build_object(
        rule_id=rule_id,
        pitcher_id=pitcher_id,
        product_date=product_date,
        subject_suffix='evidence-date',
        claim=claim,
        cited_inputs=tuple(
            [_game_log_citation(row, ('game_date', 'mlb_game_pk', 'pitches_thrown')) for row in rows]
            + [coverage.day(product_date).citation()]
        ),
        input_values={'outing_value': 'unknown'},
        trace={'steps': ['Checked relief-scoped outing threshold on the evidence date.']},
        state=EvidenceObject.COMPLETENESS_UNKNOWN,
        reason_codes=[reason_code],
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _short_rest_object(
    pitcher_id, product_date, rows, coverage, registry, templates, sync_run_id, source
):
    previous_rows = [row for row in rows if row.game_date < product_date]
    if not previous_rows:
        return None
    previous = previous_rows[-1]
    rest_start = previous.game_date + timedelta(days=1)
    rest_days = max((product_date - previous.game_date).days - 1, 0)
    span_days = max((product_date - rest_start).days + 1, 1)
    window = coverage.window(product_date, span_days)
    cited_rows = [row for row in rows if row.game_date in {previous.game_date, product_date}]
    citations = tuple(
        [_game_log_citation(row, ('game_date', 'mlb_game_pk', 'games_started')) for row in cited_rows]
        + list(window.coverage_citations())
    )
    if not window.complete:
        return _build_object(
            rule_id='appearance_short_rest',
            pitcher_id=pitcher_id,
            product_date=product_date,
            subject_suffix='evidence-date',
            claim=(
                f'Short-rest appearance is unknown for pitcher {pitcher_id} '
                f'because rest-window coverage is incomplete for '
                f'{", ".join(window.incomplete_day_labels)}.'
            ),
            cited_inputs=citations,
            input_values={'full_off_days': 'unknown'},
            trace={'steps': ['Checked rest-window coverage between appearances.']},
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=[REASON_REST_COVERAGE_GAP],
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    if rest_days <= SHORT_REST_MAX_FULL_OFF_DAYS:
        return _build_object(
            rule_id='appearance_short_rest',
            pitcher_id=pitcher_id,
            product_date=product_date,
            subject_suffix='evidence-date',
            claim=(
                f'Pitcher {pitcher_id} recorded a relief-scoped appearance on '
                f'{product_date.isoformat()} with {rest_days} full off-days '
                'since the previous final appearance.'
            ),
            cited_inputs=citations,
            input_values={'full_off_days': rest_days},
            trace={
                'steps': ['Counted full off-days since the previous final appearance.'],
                'previous_appearance_date': previous.game_date.isoformat(),
                'full_off_days': rest_days,
            },
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    return None


def _build_object(
    *,
    rule_id,
    pitcher_id,
    product_date,
    subject_suffix,
    claim,
    cited_inputs,
    input_values,
    trace,
    registry,
    templates,
    sync_run_id,
    source,
    state=EvidenceObject.COMPLETENESS_COMPLETE,
    reason_codes=None,
):
    _assert_text_has_no_workload_forbidden_terms(claim)
    rule = registry.get(rule_id, RULE_VERSION)
    template = templates.get(_template_id(rule_id), RULE_VERSION)
    full_input_values = {'slate_coverage.slate_date': product_date.isoformat()}
    full_input_values.update(input_values or {})
    evidence = build_evidence_object(
        rule_id=rule.rule_id,
        rule_version=RULE_VERSION,
        claim_template=template,
        claim_values={'claim': claim},
        subject_type='pitcher',
        subject_id=pitcher_id,
        subject_key=f'pitcher:{pitcher_id}:{product_date.isoformat()}:{subject_suffix}',
        product_date=product_date,
        cited_inputs=tuple(cited_inputs),
        computation_trace=trace,
        input_values=full_input_values,
        readiness_payload=_readiness_payload(),
        registry=registry,
        sync_run_id=sync_run_id,
        source=EVIDENCE_SOURCE,
    )
    if state != EvidenceObject.COMPLETENESS_COMPLETE or reason_codes:
        evidence.completeness_state = state
        evidence.reason_codes = _dedupe(reason_codes or [])
        evidence.rendered_claim = claim
    return BuiltWorkloadEvidence(
        evidence=evidence,
        rule_id=rule_id,
        subject_key=evidence.subject_key,
    )


def _readiness_payload():
    return {
        'families': {
            'game_logs': {'status': 'ready', 'reason_codes': []},
            'slate_coverage': {'status': 'ready', 'reason_codes': []},
        }
    }


def _window_rows(rows, product_date, window_days):
    start = product_date - timedelta(days=window_days - 1)
    return [row for row in rows if start <= row.game_date <= product_date]


def _relief_rows(rows):
    return [row for row in rows if row.games_started == 0]


def _has_unknown_role(rows):
    return any(row.games_started is None for row in rows)


def _game_log_citation(row, fields):
    return EvidenceCitationInput(
        source_family='game_logs',
        source_table='game_logs',
        source_pk=row.id,
        source_field_names=tuple(fields),
        cited_values={field: _citation_value(getattr(row, field, None)) for field in fields},
        provenance={
            'source': 'game_logs',
            'sync_run_id': row.last_stat_correction_sync_run_id,
            'stat_correction_count': row.stat_correction_count or 0,
            'last_stat_correction_at': _iso(row.last_stat_correction_at),
            'last_stat_correction_source': row.last_stat_correction_source,
        },
    )


def _citation_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _template_id(rule_id):
    return f'{rule_id}_claim'


def _upsert_evidence(new_evidence):
    existing = EvidenceObject.query.filter_by(evidence_key=new_evidence.evidence_key).first()
    if existing is None:
        db.session.add(new_evidence)
        db.session.flush()
        return 'created'

    prior_trace = {
        'rendered_claim': existing.rendered_claim,
        'completeness_state': existing.completeness_state,
        'reason_codes': list(existing.reason_codes or []),
        'invalidated_at': _iso(existing.invalidated_at),
        'invalidated_by_source_table': existing.invalidated_by_source_table,
        'invalidated_by_source_pk': existing.invalidated_by_source_pk,
    }
    for field in (
        'evidence_type',
        'subject_type',
        'subject_id',
        'subject_key',
        'product_date',
        'claim_template_id',
        'rendered_claim',
        'rule_id',
        'rule_version',
        'rule_definition_hash',
        'typed_cited_inputs',
        'computation_trace',
        'completeness_state',
        'reason_codes',
        'limitations',
        'posture',
        'source',
        'sync_run_id',
    ):
        setattr(existing, field, getattr(new_evidence, field))
    existing.computation_trace = dict(existing.computation_trace or {})
    existing.computation_trace['superseded_prior'] = prior_trace
    existing.recompute_status = EvidenceObject.RECOMPUTE_CURRENT
    existing.recompute_reason_codes = []
    existing.citations = [
        EvidenceCitation(
            source_family=citation.source_family,
            source_table=citation.source_table,
            source_pk=citation.source_pk,
            source_field_names=list(citation.source_field_names or []),
            citation_role=citation.citation_role,
            cited_values=dict(citation.cited_values or {}),
            provenance=dict(citation.provenance or {}),
        )
        for citation in new_evidence.citations
    ]
    db.session.add(existing)
    db.session.flush()
    return 'refreshed'


def _upsert_evidence_batch(new_evidence_rows):
    rows = list(new_evidence_rows or ())
    if not rows:
        return []
    keys = list(dict.fromkeys(row.evidence_key for row in rows))
    existing_by_key = {}
    for key_chunk in _chunks(keys, 500):
        existing_rows = (
            EvidenceObject.query
            .filter(EvidenceObject.evidence_key.in_(key_chunk))
            .all()
        )
        existing_by_key.update({
            row.evidence_key: row
            for row in existing_rows
        })
    emitted = []
    for new_evidence in rows:
        existing = existing_by_key.get(new_evidence.evidence_key)
        if existing is None:
            db.session.add(new_evidence)
            emitted.append('created')
            continue
        _refresh_existing_evidence(existing, new_evidence)
        emitted.append('refreshed')
    db.session.flush()
    return emitted


def _refresh_existing_evidence(existing, new_evidence):
    prior_trace = {
        'rendered_claim': existing.rendered_claim,
        'completeness_state': existing.completeness_state,
        'reason_codes': list(existing.reason_codes or []),
        'invalidated_at': _iso(existing.invalidated_at),
        'invalidated_by_source_table': existing.invalidated_by_source_table,
        'invalidated_by_source_pk': existing.invalidated_by_source_pk,
    }
    for field in (
        'evidence_type',
        'subject_type',
        'subject_id',
        'subject_key',
        'product_date',
        'claim_template_id',
        'rendered_claim',
        'rule_id',
        'rule_version',
        'rule_definition_hash',
        'typed_cited_inputs',
        'computation_trace',
        'completeness_state',
        'reason_codes',
        'limitations',
        'posture',
        'source',
        'sync_run_id',
    ):
        setattr(existing, field, getattr(new_evidence, field))
    existing.computation_trace = dict(existing.computation_trace or {})
    existing.computation_trace['superseded_prior'] = prior_trace
    existing.recompute_status = EvidenceObject.RECOMPUTE_CURRENT
    existing.recompute_reason_codes = []
    existing.citations = [
        EvidenceCitation(
            source_family=citation.source_family,
            source_table=citation.source_table,
            source_pk=citation.source_pk,
            source_field_names=list(citation.source_field_names or []),
            citation_role=citation.citation_role,
            cited_values=dict(citation.cited_values or {}),
            provenance=dict(citation.provenance or {}),
        )
        for citation in new_evidence.citations
    ]
    db.session.add(existing)


def _chunks(values, size):
    for index in range(0, len(values), size):
        yield values[index:index + size]


class _CoverageDay:
    def __init__(self, day, payload):
        self.day = day
        self.payload = payload

    @property
    def complete(self):
        return self.payload.get('complete_enough_to_publish') is True

    @property
    def reason_codes(self):
        return list(self.payload.get('reason_codes') or [])

    def mapped_reasons(self, earliest_schedule_date=None):
        if self.complete:
            return []
        if slate_coverage.REASON_RESUMED_LINKAGE_UNRESOLVED in self.reason_codes:
            return [REASON_AMBIGUOUS_RESUMED_GAME]
        if earliest_schedule_date is not None and self.day < earliest_schedule_date:
            return [REASON_WINDOW_PRECEDES_COVERAGE]
        return [REASON_INCOMPLETE_SLATE_DAY]

    def citation(self):
        return EvidenceCitationInput(
            source_family='slate_coverage',
            source_table='slate_coverage',
            source_pk=self.day.isoformat(),
            source_field_names=(
                'slate_date',
                'complete_enough_to_publish',
                'coverage_known',
                'reason_codes',
                'games_scheduled',
                'games_final',
                'games_fully_ingested',
                'games_included',
            ),
            citation_role='window_validity',
            cited_values={
                'slate_date': self.payload.get('slate_date'),
                'complete_enough_to_publish': self.payload.get('complete_enough_to_publish'),
                'coverage_known': self.payload.get('coverage_known'),
                'reason_codes': list(self.payload.get('reason_codes') or []),
                'games_scheduled': self.payload.get('games_scheduled'),
                'games_final': self.payload.get('games_final'),
                'games_fully_ingested': self.payload.get('games_fully_ingested'),
                'games_included': self.payload.get('games_included'),
            },
            provenance={
                'source': 'slate_coverage.compute_slate_coverage',
                'slate_date': self.day.isoformat(),
            },
        )


class _CoverageWindow:
    def __init__(self, start, end, days, reason_codes):
        self.start = start
        self.end = end
        self.days = days
        self.reason_codes = _dedupe(reason_codes)

    @property
    def complete(self):
        return not self.reason_codes

    @property
    def incomplete_day_labels(self):
        return [
            day.day.isoformat()
            for day in self.days
            if not day.complete
        ]

    def coverage_citations(self):
        if not self.days:
            return ()
        if self.complete:
            return tuple(day.citation() for day in self.days)
        return tuple(day.citation() for day in self.days if not day.complete)


class _CoverageCache:
    def __init__(self, product_date):
        self.product_date = product_date
        self._payloads = {}
        self._earliest_schedule_date = (
            db.session.query(db.func.min(ScheduledGame.game_date)).scalar()
        )

    def day(self, target_date):
        target = _as_date(target_date)
        if target not in self._payloads:
            self._payloads[target] = slate_coverage.compute_slate_coverage(target)
        return _CoverageDay(target, self._payloads[target])

    def window(self, product_date, window_days):
        end = _as_date(product_date)
        start = end - timedelta(days=window_days - 1)
        days = [self.day(start + timedelta(days=offset)) for offset in range(window_days)]
        reasons = []
        for day in days:
            reasons.extend(day.mapped_reasons(self._earliest_schedule_date))
        return _CoverageWindow(start, end, days, reasons)


def _iso(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _dedupe(values):
    result = []
    for value in values or []:
        if value not in result:
            result.append(value)
    return result
