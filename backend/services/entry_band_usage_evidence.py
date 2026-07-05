"""Internal Phase 0D entry-context band and usage-observation evidence family."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re

from sqlalchemy import asc

from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.scheduled_game import ScheduledGame
from services import dead_letter, slate_coverage
from services.evidence_contract import (
    EvidenceCitationInput,
    build_evidence_object,
    mark_dependent_evidence_for_recompute,
)
from services.evidence_language import EvidenceLanguageError
from services.evidence_rules import (
    ClaimTemplate,
    ClaimTemplateRegistry,
    EvidenceRule,
    EvidenceRuleError,
    EvidenceRuleRegistry,
)
from utils.db import db


RULE_VERSION = 1
EVIDENCE_SOURCE = 'phase0d:entry_band_usage_evidence'
SOURCE_READY = 'ready'
SUBJECT_APPEARANCE = 'pitcher_appearance'
SUBJECT_PITCHER = 'pitcher'
FINISH_CONTEXT_CONTRADICTION_ENTITY_TYPE = 'finish_context_contradiction'

APPEARANCE_ENTRY_BAND_RULE_ID = 'appearance_entry_band'
APPEARANCE_FINISH_CONTEXT_RULE_ID = 'appearance_finish_context'
PITCHER_SAVE_HOLD_WINDOW_RULE_ID = 'pitcher_save_hold_window'
PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID = 'pitcher_entry_band_distribution'
PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID = 'pitcher_finish_usage_observation'
PITCHER_MULTI_INNING_USAGE_OBSERVATION_RULE_ID = 'pitcher_multi_inning_usage_observation'
PITCHER_FIRST_RELIEVER_USAGE_OBSERVATION_RULE_ID = 'pitcher_first_reliever_usage_observation'

ENTRY_BAND_USAGE_RULE_IDS = (
    APPEARANCE_ENTRY_BAND_RULE_ID,
    APPEARANCE_FINISH_CONTEXT_RULE_ID,
    PITCHER_SAVE_HOLD_WINDOW_RULE_ID,
    PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID,
    PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID,
    PITCHER_MULTI_INNING_USAGE_OBSERVATION_RULE_ID,
    PITCHER_FIRST_RELIEVER_USAGE_OBSERVATION_RULE_ID,
)

LOCKED_INTERNAL_RULE_IDS = (
    APPEARANCE_ENTRY_BAND_RULE_ID,
    PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID,
)

REASON_ENTRY_CONTEXT_UNAVAILABLE = 'entry_context_unavailable'
REASON_ENTRY_CONTEXT_INCOHERENT = 'entry_context_incoherent'
REASON_INSUFFICIENT_SAMPLE = 'insufficient_sample'
REASON_INCOMPLETE_SLATE_DAY = 'incomplete_slate_day_in_window'
REASON_APPEARANCE_ROLE_UNKNOWN = 'appearance_role_unknown'
REASON_GAMES_FINISHED_UNKNOWN = 'games_finished_unknown'
REASON_BAND_UNKNOWN_IN_WINDOW = 'band_unknown_in_window'
REASON_ORDER_UNKNOWN_IN_WINDOW = 'order_unknown_in_window'
REASON_MULTI_INNING_UNKNOWN_IN_WINDOW = 'multi_inning_unknown_in_window'
REASON_LEGACY_ROW_DEFAULT_FALSE_CAVEAT = 'legacy_row_default_false_caveat'
REASON_SOURCE_FAMILY_NOT_READY = 'source_family_not_ready'

REASON_GAME_LOG_CORRECTED = 'game_log_corrected'
REASON_SOURCE_EVIDENCE_SUPERSEDED = 'source_evidence_superseded'

WINDOW_DAYS = (7, 14)
DISTRIBUTION_WINDOW_DAYS = 14
OBSERVATION_WINDOW_DAYS = 14
MIN_OBSERVATION_APPEARANCES = 5

ENTRY_PHASE_THRESHOLDS = {
    'early_max': 3,
    'middle_max': 6,
    'late_max': 9,
}
MARGIN_THRESHOLDS = {
    'one_run_max': 1,
    'two_three_max': 3,
}

ENTRY_BAND_CELLS = (
    'early_one_run',
    'early_two_three',
    'early_four_plus',
    'middle_one_run',
    'middle_two_three',
    'middle_four_plus',
    'late_one_run',
    'late_two_three',
    'late_four_plus',
    'extras_one_run',
    'extras_two_three',
    'extras_four_plus',
)

BASE_STATE_LIMITATION = (
    'The band classifies inning and margin only; runners at entry remain unknown.'
)
LEGACY_ROW_DEFAULT_FALSE_LIMITATION = (
    'Legacy row caveat: boolean finish flags on rows without batters faced can '
    'undercount unset false values, while sourced true values remain cited.'
)
LOWER_BOUND_LIMITATION = (
    'Window count is a lower bound because at least one day in the window lacks '
    'complete slate coverage.'
)

_RULE_DEFINITIONS = {
    APPEARANCE_ENTRY_BAND_RULE_ID: (
        'For a qualifying relief appearance, the cell of a 12-cell table crossing '
        'entry-inning phase with entry margin from the pitcher team perspective. '
        'Early is innings 1-3, middle 4-6, late 7-9, and extras 10 or later. '
        'one_run means margin magnitude <= 1 including tied, two_three means '
        'magnitude 2-3, and four_plus means magnitude >= 4. Thresholds: '
        'one_run_max 1, two_three_max 3, early_max 3, middle_max 6, late_max 9. '
        'The cell names are mechanical compounds and runners at entry remain unknown.'
    ),
    APPEARANCE_FINISH_CONTEXT_RULE_ID: (
        'For a qualifying relief appearance, the stored boxscore finishing facts '
        'as sourced: save opportunity, save, hold, blown save, win, loss, and '
        'games finished. Nullable games_finished remains unknown. Boolean flags '
        'on legacy sentinel rows can undercount unset false values.'
    ),
    PITCHER_SAVE_HOLD_WINDOW_RULE_ID: (
        'Trailing window counts for window_days [7, 14] of save opportunities, '
        'saves, holds, blown saves, and games finished across qualifying relief '
        'appearances from stored flags. Counts only, never a conversion value.'
    ),
    PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID: (
        'Trailing 14-day distribution for window_days [14] across the 12 '
        'appearance_entry_band cells for qualifying relief appearances, including '
        'zero counts and band-unknown appearances. The rule emits only when '
        'min_qualifying_appearances 5 is met and remains permanently internal.'
    ),
    PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID: (
        'Trailing 14-day observation for window_days [14]: of the pitcher '
        'qualifying relief appearances, how many he finished and how many of '
        'those finished appearances began in late or extras one_run cells. The '
        'rule emits only when min_qualifying_appearances 5 is met.'
    ),
    PITCHER_MULTI_INNING_USAGE_OBSERVATION_RULE_ID: (
        'Trailing 14-day observation for window_days [14]: of the pitcher '
        'qualifying relief appearances, at least how many were multi-inning per '
        'stored outing_multi_inning evidence objects. Unknown-state objects are '
        'counted separately. The rule emits only when min_qualifying_appearances 5 is met.'
    ),
    PITCHER_FIRST_RELIEVER_USAGE_OBSERVATION_RULE_ID: (
        'Trailing 14-day observation for window_days [14]: of the pitcher '
        'qualifying relief appearances, how many were the team first relief '
        'appearance of the game, defined by appearance_order_in_game value 2. '
        'The rule emits only when min_qualifying_appearances 5 is met.'
    ),
}

_RULE_THRESHOLDS = {
    APPEARANCE_ENTRY_BAND_RULE_ID: {
        **MARGIN_THRESHOLDS,
        **ENTRY_PHASE_THRESHOLDS,
    },
    PITCHER_SAVE_HOLD_WINDOW_RULE_ID: {'window_days': [7, 14]},
    PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID: {
        'window_days': [14],
        'min_qualifying_appearances': MIN_OBSERVATION_APPEARANCES,
    },
    PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID: {
        'window_days': [14],
        'min_qualifying_appearances': MIN_OBSERVATION_APPEARANCES,
    },
    PITCHER_MULTI_INNING_USAGE_OBSERVATION_RULE_ID: {
        'window_days': [14],
        'min_qualifying_appearances': MIN_OBSERVATION_APPEARANCES,
    },
    PITCHER_FIRST_RELIEVER_USAGE_OBSERVATION_RULE_ID: {
        'window_days': [14],
        'min_qualifying_appearances': MIN_OBSERVATION_APPEARANCES,
    },
}

_REQUIRED_FIELDS = {
    APPEARANCE_ENTRY_BAND_RULE_ID: (
        'game_logs.games_started',
        'final_play_by_play.mlb_game_pk',
    ),
    APPEARANCE_FINISH_CONTEXT_RULE_ID: (
        'game_logs.games_started',
        'game_logs.games_finished',
    ),
    PITCHER_SAVE_HOLD_WINDOW_RULE_ID: (
        'game_logs.games_started',
        'slate_coverage.slate_date',
    ),
    PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID: (
        'game_logs.games_started',
        'slate_coverage.slate_date',
    ),
    PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID: (
        'game_logs.games_started',
        'slate_coverage.slate_date',
    ),
    PITCHER_MULTI_INNING_USAGE_OBSERVATION_RULE_ID: (
        'game_logs.games_started',
        'slate_coverage.slate_date',
    ),
    PITCHER_FIRST_RELIEVER_USAGE_OBSERVATION_RULE_ID: (
        'game_logs.games_started',
        'slate_coverage.slate_date',
    ),
}

_REQUIRED_INPUT_FAMILIES = {
    APPEARANCE_ENTRY_BAND_RULE_ID: ('final_play_by_play', 'game_logs'),
    APPEARANCE_FINISH_CONTEXT_RULE_ID: ('game_logs',),
    PITCHER_SAVE_HOLD_WINDOW_RULE_ID: ('game_logs', 'slate_coverage'),
    PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID: (
        'game_logs',
        'slate_coverage',
        'final_play_by_play',
    ),
    PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID: (
        'game_logs',
        'slate_coverage',
        'final_play_by_play',
    ),
    PITCHER_MULTI_INNING_USAGE_OBSERVATION_RULE_ID: ('game_logs', 'slate_coverage'),
    PITCHER_FIRST_RELIEVER_USAGE_OBSERVATION_RULE_ID: (
        'game_logs',
        'slate_coverage',
        'final_play_by_play',
    ),
}

_NO_PARTIAL_COMPLETENESS = (
    EvidenceObject.COMPLETENESS_COMPLETE,
    EvidenceObject.COMPLETENESS_UNKNOWN,
    EvidenceObject.COMPLETENESS_CONFLICT,
    EvidenceObject.COMPLETENESS_WITHHELD,
)

_FORBIDDEN_ENTRY_BAND_TERMS = (
    'pres' + 'sure',
    'lever' + 'age',
    'high-' + 'lever' + 'age',
    'stress',
    'closer',
    'setup man',
    'fireman',
    'stopper',
    'long man',
    'bullpen ace',
    'ninth-inning guy',
    'trusted',
    'go-to',
    'leans on',
    'prefers',
    "manager's choice",
    'dominant',
    'reliable',
    'shaky',
    'will',
    'should',
    'expect',
    'likely',
    'available',
    'ready',
    'percentage',
    'percent',
    'rate',
    'score',
    'grade',
    'rank',
)


@dataclass(frozen=True)
class BuiltEntryBandUsageEvidence:
    evidence: EvidenceObject
    rule_id: str
    subject_key: str


_LOCAL_RULE_REGISTRY: EvidenceRuleRegistry | None = None
_LOCAL_TEMPLATE_REGISTRY: ClaimTemplateRegistry | None = None


def entry_band_usage_rule_definitions() -> dict[str, str]:
    return dict(_RULE_DEFINITIONS)


def entry_band_usage_rule_ids() -> tuple[str, ...]:
    return ENTRY_BAND_USAGE_RULE_IDS


def register_entry_band_usage_rules(
    *,
    registry: EvidenceRuleRegistry | None = None,
    template_registry: ClaimTemplateRegistry | None = None,
) -> tuple[EvidenceRuleRegistry, ClaimTemplateRegistry]:
    rule_registry = registry or EvidenceRuleRegistry()
    claim_registry = template_registry or ClaimTemplateRegistry()
    for rule_id in ENTRY_BAND_USAGE_RULE_IDS:
        _register_entry_band_usage_rule(rule_registry, _entry_band_usage_rule(rule_id))
        for template in _templates_for_rule(rule_id):
            _register_entry_band_usage_template(claim_registry, template)
    return rule_registry, claim_registry


def build_entry_band_usage_evidence(
    product_date,
    *,
    sync_run_id=None,
    source='manual',
    commit=False,
    restrict_evidence_keys: set[str] | None = None,
) -> dict:
    """Build internal entry-context band and usage-observation evidence."""
    ref = _as_date(product_date)
    registry, templates = _local_registries()
    coverage = _CoverageCache(ref)
    evidence_to_upsert = []

    product_logs = _logs_for_range(ref, ref)
    for log in product_logs:
        for item in _build_appearance_objects(
            log=log,
            product_date=ref,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        ):
            if restrict_evidence_keys is not None and item.evidence.evidence_key not in restrict_evidence_keys:
                continue
            evidence_to_upsert.append(item.evidence)

    window_start = ref - timedelta(days=OBSERVATION_WINDOW_DAYS - 1)
    window_logs = _logs_for_range(window_start, ref)
    for pitcher_id, rows in _logs_by_pitcher(window_logs).items():
        for item in _build_pitcher_window_objects(
            pitcher_id=pitcher_id,
            product_date=ref,
            rows=rows,
            coverage=coverage,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        ):
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
        'rules': list(ENTRY_BAND_USAGE_RULE_IDS),
        'objects_built': len(emitted),
        'objects_created': sum(1 for item in emitted if item == 'created'),
        'objects_refreshed': sum(1 for item in emitted if item == 'refreshed'),
    }


def mark_game_log_correction_for_entry_band_usage(
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


def mark_source_evidence_supersession_for_entry_band_usage(
    evidence_object,
    *,
    sync_run_id=None,
    reason_code=REASON_SOURCE_EVIDENCE_SUPERSEDED,
    batch_size=100,
) -> dict:
    if evidence_object is None or getattr(evidence_object, 'id', None) is None:
        return {'marked_count': 0, 'evidence_ids': []}
    return mark_dependent_evidence_for_recompute(
        source_table='evidence_objects',
        source_pk=evidence_object.id,
        reason_code=reason_code,
        batch_size=batch_size,
        sync_run_id=sync_run_id,
        correction_source='source_evidence_supersession',
    )


def rebuild_marked_entry_band_usage_evidence(
    *,
    sync_run_id=None,
    source='manual',
    batch_size=100,
) -> dict:
    rows = (
        EvidenceObject.query
        .filter(EvidenceObject.rule_id.in_(ENTRY_BAND_USAGE_RULE_IDS))
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
        result = build_entry_band_usage_evidence(
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
        _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY = register_entry_band_usage_rules()
    return _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY


def _entry_band_usage_rule(rule_id):
    return EvidenceRule(
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        evidence_type=rule_id,
        plain_language_definition=_RULE_DEFINITIONS[rule_id],
        required_input_families=_REQUIRED_INPUT_FAMILIES[rule_id],
        required_cited_fields=_REQUIRED_FIELDS[rule_id],
        allowed_completeness=_NO_PARTIAL_COMPLETENESS
        if rule_id in (APPEARANCE_ENTRY_BAND_RULE_ID, APPEARANCE_FINISH_CONTEXT_RULE_ID)
        else (
            EvidenceObject.COMPLETENESS_COMPLETE,
            EvidenceObject.COMPLETENESS_PARTIAL,
            EvidenceObject.COMPLETENESS_UNKNOWN,
            EvidenceObject.COMPLETENESS_CONFLICT,
            EvidenceObject.COMPLETENESS_WITHHELD,
        ),
        posture_default=EvidenceObject.POSTURE_INTERNAL_ONLY,
        thresholds=_RULE_THRESHOLDS.get(rule_id, {}),
    )


def _register_entry_band_usage_rule(registry, rule):
    if (
        rule.rule_id in LOCKED_INTERNAL_RULE_IDS
        and rule.posture_default != EvidenceObject.POSTURE_INTERNAL_ONLY
    ):
        raise EvidenceRuleError('entry-context band posture-locked rule cannot be public_candidate')
    if rule.posture_default != EvidenceObject.POSTURE_INTERNAL_ONLY:
        raise EvidenceRuleError('entry-context band evidence must remain internal_only')
    return registry.register(rule)


def _register_entry_band_usage_template(registry, template):
    _assert_text_has_no_entry_band_forbidden_terms(template.template_text)
    return registry.register(template)


def _templates_for_rule(rule_id):
    if rule_id == PITCHER_SAVE_HOLD_WINDOW_RULE_ID:
        for window_days in WINDOW_DAYS:
            yield ClaimTemplate(_template_id(rule_id, window_days=window_days), RULE_VERSION, '{claim}')
            yield ClaimTemplate(
                _template_id(rule_id, window_days=window_days, degraded=True),
                RULE_VERSION,
                '{claim}',
            )
        return
    if rule_id in (
        PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID,
        PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID,
        PITCHER_MULTI_INNING_USAGE_OBSERVATION_RULE_ID,
        PITCHER_FIRST_RELIEVER_USAGE_OBSERVATION_RULE_ID,
    ):
        yield ClaimTemplate(_template_id(rule_id, window_days=14), RULE_VERSION, '{claim}')
        yield ClaimTemplate(_template_id(rule_id, window_days=14, degraded=True), RULE_VERSION, '{claim}')
        return
    yield ClaimTemplate(_template_id(rule_id), RULE_VERSION, '{claim}')


def _assert_text_has_no_entry_band_forbidden_terms(text):
    lowered = f' {text or ""} '.lower()
    for term in _FORBIDDEN_ENTRY_BAND_TERMS:
        pattern = r'\b' + re.escape(term).replace(r'\ ', r'\s+') + r'\b'
        if re.search(pattern, lowered):
            raise EvidenceLanguageError(
                f'entry-context band claim language uses forbidden term: {term}'
            )
    if re.search(r'\b[a-z0-9_ -]+-like\s+role\b', lowered):
        raise EvidenceLanguageError('entry-context band claim language uses forbidden role pattern')
    if '%' in lowered:
        raise EvidenceLanguageError('entry-context band claim language uses forbidden percent symbol')
    return True


def _build_appearance_objects(
    *,
    log,
    product_date,
    registry,
    templates,
    sync_run_id,
    source,
):
    if not _is_finality_certified(log):
        return []
    if log.games_started == 1:
        if log.hold:
            return [
                _finish_context_object(
                    log=log,
                    product_date=product_date,
                    registry=registry,
                    templates=templates,
                    sync_run_id=sync_run_id,
                    source=source,
                    contradiction='hold_with_start',
                )
            ]
        return []
    if log.games_started is None:
        return [
            _appearance_role_unknown_object(
                APPEARANCE_ENTRY_BAND_RULE_ID,
                log,
                product_date,
                registry,
                templates,
                sync_run_id,
                source,
            ),
            _appearance_role_unknown_object(
                APPEARANCE_FINISH_CONTEXT_RULE_ID,
                log,
                product_date,
                registry,
                templates,
                sync_run_id,
                source,
            ),
        ]

    return [
        _entry_band_object(log, product_date, registry, templates, sync_run_id, source),
        _finish_context_object(
            log=log,
            product_date=product_date,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        ),
    ]


def _appearance_role_unknown_object(rule_id, log, product_date, registry, templates, sync_run_id, source):
    claim = (
        f'Evidence unknown for pitcher {log.pitcher_id} in game {log.mlb_game_pk}: '
        'the stored games-started value is unknown.'
    )
    return _build_object(
        rule_id=rule_id,
        subject_type=SUBJECT_APPEARANCE,
        subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}',
        subject_key=_appearance_subject_key(log, rule_id),
        product_date=product_date,
        claim=claim,
        cited_inputs=(_game_log_citation(log, ('games_started', 'mlb_game_pk')),),
        input_values={
            'game_logs.games_started': None,
            'final_play_by_play.mlb_game_pk': log.mlb_game_pk,
            'game_logs.games_finished': getattr(log, 'games_finished', None),
        },
        trace={
            'steps': ['Checked games_started before qualifying the appearance.'],
            'qualifying_decision': _qualifying_decision(log),
        },
        state=EvidenceObject.COMPLETENESS_UNKNOWN,
        reason_codes=[REASON_APPEARANCE_ROLE_UNKNOWN],
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _entry_band_object(log, product_date, registry, templates, sync_run_id, source):
    entry = _source_evidence(log, 'appearance_entry_context')
    if entry is None:
        claim = (
            f'Entry-context band unknown for pitcher {log.pitcher_id} in game '
            f'{log.mlb_game_pk}: stored entry context evidence is unavailable; '
            'runners at entry unknown.'
        )
        return _build_object(
            rule_id=APPEARANCE_ENTRY_BAND_RULE_ID,
            subject_type=SUBJECT_APPEARANCE,
            subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}',
            subject_key=_appearance_subject_key(log, APPEARANCE_ENTRY_BAND_RULE_ID),
            product_date=product_date,
            claim=claim,
            cited_inputs=(
                _game_log_citation(log, ('games_started', 'mlb_game_pk')),
                _missing_source_evidence_citation(log, 'appearance_entry_context'),
            ),
            input_values={
                'game_logs.games_started': log.games_started,
                'final_play_by_play.mlb_game_pk': log.mlb_game_pk,
            },
            trace=_entry_band_trace(log, None, None, 'missing_source_evidence'),
            limitations=(BASE_STATE_LIMITATION,),
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=[REASON_ENTRY_CONTEXT_UNAVAILABLE],
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )

    state = entry.completeness_state
    if state != EvidenceObject.COMPLETENESS_COMPLETE:
        reason = (
            REASON_ENTRY_CONTEXT_INCOHERENT
            if state == EvidenceObject.COMPLETENESS_CONFLICT
            else REASON_ENTRY_CONTEXT_UNAVAILABLE
        )
        claim = (
            f'Entry-context band unknown for pitcher {log.pitcher_id} in game '
            f'{log.mlb_game_pk}: stored entry context evidence is {state}; '
            'runners at entry unknown.'
        )
        return _build_object(
            rule_id=APPEARANCE_ENTRY_BAND_RULE_ID,
            subject_type=SUBJECT_APPEARANCE,
            subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}',
            subject_key=_appearance_subject_key(log, APPEARANCE_ENTRY_BAND_RULE_ID),
            product_date=product_date,
            claim=claim,
            cited_inputs=tuple(
                [_source_evidence_citation(entry, 'derived_from_evidence')]
                + _passthrough_citations(entry)
            ),
            input_values={
                'game_logs.games_started': log.games_started,
                'final_play_by_play.mlb_game_pk': _entry_source_game_pk(entry, log),
            },
            trace=_entry_band_trace(log, entry, None, f'source_evidence_{state}'),
            limitations=(BASE_STATE_LIMITATION,),
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=[reason],
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )

    entry_values = _entry_context_values(entry)
    if entry_values.get('entry_inning') is None or entry_values.get('margin') is None:
        claim = (
            f'Entry-context band unknown for pitcher {log.pitcher_id} in game '
            f'{log.mlb_game_pk}: stored entry context values are incomplete; '
            'runners at entry unknown.'
        )
        return _build_object(
            rule_id=APPEARANCE_ENTRY_BAND_RULE_ID,
            subject_type=SUBJECT_APPEARANCE,
            subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}',
            subject_key=_appearance_subject_key(log, APPEARANCE_ENTRY_BAND_RULE_ID),
            product_date=product_date,
            claim=claim,
            cited_inputs=tuple(
                [_source_evidence_citation(entry, 'derived_from_evidence')]
                + _passthrough_citations(entry)
            ),
            input_values={
                'game_logs.games_started': log.games_started,
                'final_play_by_play.mlb_game_pk': _entry_source_game_pk(entry, log),
            },
            trace=_entry_band_trace(log, entry, entry_values, 'incomplete_source_values'),
            limitations=(BASE_STATE_LIMITATION,),
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=[REASON_ENTRY_CONTEXT_UNAVAILABLE],
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )

    phase = _entry_phase(entry_values['entry_inning'])
    margin_band = _margin_band(entry_values['margin'])
    cell = f'{phase}_{margin_band}'
    claim = (
        f'Entered in the {_ordinal(entry_values["entry_inning"])} ({phase}) with '
        f'margin {_signed(entry_values["margin"])} ({margin_band}): band {cell} '
        'per the registered table; runners at entry unknown.'
    )
    return _build_object(
        rule_id=APPEARANCE_ENTRY_BAND_RULE_ID,
        subject_type=SUBJECT_APPEARANCE,
        subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}',
        subject_key=_appearance_subject_key(log, APPEARANCE_ENTRY_BAND_RULE_ID),
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(
            [_source_evidence_citation(entry, 'derived_from_evidence')]
            + _passthrough_citations(entry)
        ),
        input_values={
            'game_logs.games_started': log.games_started,
            'final_play_by_play.mlb_game_pk': _entry_source_game_pk(entry, log),
        },
        trace=_entry_band_trace(
            log,
            entry,
            {
                **entry_values,
                'entry_phase': phase,
                'margin_band': margin_band,
                'band_cell': cell,
            },
            'complete',
        ),
        limitations=(BASE_STATE_LIMITATION,),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _finish_context_object(
    *,
    log,
    product_date,
    registry,
    templates,
    sync_run_id,
    source,
    contradiction=None,
):
    contradiction = contradiction or (
        'save_and_blown_save'
        if bool(log.save) and bool(log.blown_save)
        else None
    )
    fields = (
        'games_started',
        'games_finished',
        'save_situation',
        'save',
        'hold',
        'blown_save',
        'win',
        'loss',
        'batters_faced',
    )
    values = _finish_values(log)
    limitations = []
    reasons = []
    state = EvidenceObject.COMPLETENESS_COMPLETE
    if log.batters_faced is None:
        limitations.append(LEGACY_ROW_DEFAULT_FALSE_LIMITATION)
        reasons.append(REASON_LEGACY_ROW_DEFAULT_FALSE_CAVEAT)
    if log.games_finished is None and contradiction is None:
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        reasons.append(REASON_GAMES_FINISHED_UNKNOWN)
    claim = _finish_claim(log, values, contradiction=contradiction)
    contradictions = ()
    if contradiction is not None:
        contradictions = ({'game_log_id': log.id, 'reason': contradiction},)
        state = EvidenceObject.COMPLETENESS_CONFLICT
        _record_finish_dead_letter(log, contradiction, sync_run_id)
    return _build_object(
        rule_id=APPEARANCE_FINISH_CONTEXT_RULE_ID,
        subject_type=SUBJECT_APPEARANCE,
        subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}',
        subject_key=_appearance_subject_key(log, APPEARANCE_FINISH_CONTEXT_RULE_ID),
        product_date=product_date,
        claim=claim,
        cited_inputs=(_game_log_citation(log, fields),),
        input_values={
            'game_logs.games_started': log.games_started,
            'game_logs.games_finished': log.games_finished,
        },
        trace={
            'steps': ['Read stored boxscore finishing fields from game_logs.'],
            'qualifying_decision': _qualifying_decision(log),
            'finish_values': values,
            'legacy_row_default_false_caveat': log.batters_faced is None,
            'contradiction': contradiction,
        },
        limitations=tuple(limitations),
        contradictions=contradictions,
        state=state,
        reason_codes=reasons if not contradictions else ['contradictory_inputs'],
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _build_pitcher_window_objects(
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
    emitted = []
    for window_days in WINDOW_DAYS:
        emitted.append(_save_hold_window_object(
            pitcher_id, product_date, rows, coverage, window_days, registry, templates, sync_run_id, source
        ))
    for builder in (
        _entry_band_distribution_object,
        _finish_usage_observation_object,
        _multi_inning_usage_observation_object,
        _first_reliever_usage_observation_object,
    ):
        emitted.append(builder(
            pitcher_id, product_date, rows, coverage, registry, templates, sync_run_id, source
        ))
    return [item for item in emitted if item is not None]


def _save_hold_window_object(
    pitcher_id,
    product_date,
    rows,
    coverage,
    window_days,
    registry,
    templates,
    sync_run_id,
    source,
):
    window_rows = _qualifying_rows(_window_rows(rows, product_date, window_days))
    if not window_rows:
        return None
    if not _denominator_citable(window_rows):
        return None
    coverage_window = coverage.window(product_date, window_days)
    counts = {
        'appearances': len(window_rows),
        'save_opportunities': sum(1 for row in window_rows if bool(row.save_situation)),
        'saves': sum(1 for row in window_rows if bool(row.save)),
        'holds': sum(1 for row in window_rows if bool(row.hold)),
        'blown_saves': sum(1 for row in window_rows if bool(row.blown_save)),
        'games_finished': sum(1 for row in window_rows if row.games_finished == 1),
        'legacy_rows': sum(1 for row in window_rows if row.batters_faced is None),
    }
    lower = '' if coverage_window.complete else 'At least '
    claim = (
        f'{lower}{window_days}-day save/hold counts for pitcher {pitcher_id}: '
        f'{counts["appearances"]} relief appearances, save opportunities '
        f'{counts["save_opportunities"]}, saves {counts["saves"]}, holds '
        f'{counts["holds"]}, blown saves {counts["blown_saves"]}, games finished '
        f'{counts["games_finished"]}.'
    )
    reasons = []
    limitations = []
    if not coverage_window.complete:
        reasons.append(REASON_INCOMPLETE_SLATE_DAY)
        limitations.append(LOWER_BOUND_LIMITATION)
    if counts['legacy_rows']:
        reasons.append(REASON_LEGACY_ROW_DEFAULT_FALSE_CAVEAT)
        limitations.append(LEGACY_ROW_DEFAULT_FALSE_LIMITATION)
    state = (
        EvidenceObject.COMPLETENESS_COMPLETE
        if coverage_window.complete
        else EvidenceObject.COMPLETENESS_PARTIAL
    )
    return _build_object(
        rule_id=PITCHER_SAVE_HOLD_WINDOW_RULE_ID,
        subject_type=SUBJECT_PITCHER,
        subject_id=pitcher_id,
        subject_key=f'pitcher:{pitcher_id}:{product_date.isoformat()}:save-hold-{window_days}',
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(
            [_game_log_citation(row, _finish_window_fields(), citation_role='denominator_row') for row in window_rows]
            + list(coverage_window.coverage_citations())
        ),
        input_values=_window_input_values(product_date, window_rows),
        trace=_window_trace(product_date, window_days, window_rows, coverage_window, extra={'counts': counts}),
        limitations=tuple(limitations),
        state=state,
        reason_codes=reasons,
        window_days=window_days,
        degraded=not coverage_window.complete,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _entry_band_distribution_object(
    pitcher_id,
    product_date,
    rows,
    coverage,
    registry,
    templates,
    sync_run_id,
    source,
):
    window_days = DISTRIBUTION_WINDOW_DAYS
    window_rows = _qualifying_rows(_window_rows(rows, product_date, window_days))
    if not window_rows or not _denominator_citable(window_rows):
        return None
    floor_object = _sample_floor_object(
        PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID,
        pitcher_id,
        product_date,
        window_rows,
        coverage,
        registry,
        templates,
        sync_run_id,
        source,
    )
    if floor_object is not None:
        return floor_object
    coverage_window = coverage.window(product_date, window_days)
    cells = Counter({cell: 0 for cell in ENTRY_BAND_CELLS})
    band_unknown = 0
    consumed = []
    citations = [_game_log_citation(row, ('game_date', 'mlb_game_pk', 'games_started'), citation_role='denominator_row') for row in window_rows]
    for row in window_rows:
        band = _source_evidence(row, APPEARANCE_ENTRY_BAND_RULE_ID)
        if band is not None:
            consumed.append(_source_ref(band))
            citations.append(_source_evidence_citation(band, 'derived_from_evidence'))
            citations.extend(_passthrough_citations(band))
        cell = _band_cell_from_evidence(band)
        if cell in ENTRY_BAND_CELLS and band.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE:
            cells[cell] += 1
        else:
            band_unknown += 1
    lower = '' if coverage_window.complete else 'At least '
    cell_text = ', '.join(f'{cell} {cells[cell]}' for cell in ENTRY_BAND_CELLS)
    claim = (
        f'{lower}14-day entry-context band distribution for pitcher {pitcher_id}: '
        f'n={len(window_rows)}; {cell_text}; band unknown {band_unknown}.'
    )
    reasons = []
    limitations = []
    if band_unknown:
        reasons.append(REASON_BAND_UNKNOWN_IN_WINDOW)
    if not coverage_window.complete:
        reasons.append(REASON_INCOMPLETE_SLATE_DAY)
        limitations.append(LOWER_BOUND_LIMITATION)
    return _build_object(
        rule_id=PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID,
        subject_type=SUBJECT_PITCHER,
        subject_id=pitcher_id,
        subject_key=f'pitcher:{pitcher_id}:{product_date.isoformat()}:entry-band-distribution-14',
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(citations + list(coverage_window.coverage_citations())),
        input_values=_window_input_values(product_date, window_rows),
        trace=_window_trace(
            product_date,
            window_days,
            window_rows,
            coverage_window,
            extra={
                'per_cell_tallies': dict(cells),
                'band_unknown_count': band_unknown,
                'consumed_evidence_objects': consumed,
                'floor_check': {'n': len(window_rows), 'minimum': MIN_OBSERVATION_APPEARANCES, 'passed': True},
            },
        ),
        limitations=tuple(limitations),
        state=EvidenceObject.COMPLETENESS_PARTIAL if not coverage_window.complete else EvidenceObject.COMPLETENESS_COMPLETE,
        reason_codes=reasons,
        window_days=window_days,
        degraded=not coverage_window.complete,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _finish_usage_observation_object(
    pitcher_id,
    product_date,
    rows,
    coverage,
    registry,
    templates,
    sync_run_id,
    source,
):
    window_days = OBSERVATION_WINDOW_DAYS
    window_rows = _qualifying_rows(_window_rows(rows, product_date, window_days))
    if not window_rows or not _denominator_citable(window_rows):
        return None
    floor_object = _sample_floor_object(
        PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID,
        pitcher_id,
        product_date,
        window_rows,
        coverage,
        registry,
        templates,
        sync_run_id,
        source,
    )
    if floor_object is not None:
        return floor_object
    coverage_window = coverage.window(product_date, window_days)
    finished = [row for row in window_rows if row.games_finished == 1]
    unknown_finished = [row for row in window_rows if row.games_finished is None]
    late_one_run = 0
    unknown_band = []
    citations = [_game_log_citation(row, _finish_window_fields(), citation_role='denominator_row') for row in window_rows]
    consumed = []
    for row in finished:
        band = _source_evidence(row, APPEARANCE_ENTRY_BAND_RULE_ID)
        if band is not None:
            consumed.append(_source_ref(band))
            citations.append(_source_evidence_citation(band, 'derived_from_evidence'))
            citations.extend(_passthrough_citations(band))
        cell = _band_cell_from_evidence(band)
        if cell in ('late_one_run', 'extras_one_run') and band.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE:
            late_one_run += 1
        elif band is None or band.completeness_state != EvidenceObject.COMPLETENESS_COMPLETE:
            unknown_band.append(row)
    lower = 'At least ' if unknown_finished or unknown_band or not coverage_window.complete else ''
    claim = (
        f'{lower}Finished {len(finished)} of {len(window_rows)} relief appearances '
        f'in the last 14 days; {late_one_run} of {len(finished)} finished '
        'appearances began in late/extras one_run cells.'
    )
    reasons = []
    limitations = []
    if unknown_finished:
        reasons.append(REASON_GAMES_FINISHED_UNKNOWN)
    if unknown_band:
        reasons.append(REASON_BAND_UNKNOWN_IN_WINDOW)
    if not coverage_window.complete:
        reasons.append(REASON_INCOMPLETE_SLATE_DAY)
        limitations.append(LOWER_BOUND_LIMITATION)
    return _build_object(
        rule_id=PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID,
        subject_type=SUBJECT_PITCHER,
        subject_id=pitcher_id,
        subject_key=f'pitcher:{pitcher_id}:{product_date.isoformat()}:finish-usage-14',
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(citations + list(coverage_window.coverage_citations())),
        input_values=_window_input_values(product_date, window_rows),
        trace=_window_trace(
            product_date,
            window_days,
            window_rows,
            coverage_window,
            extra={
                'finished_game_log_ids': [row.id for row in finished],
                'unknown_games_finished_ids': [row.id for row in unknown_finished],
                'late_or_extras_one_run_finished_count': late_one_run,
                'unknown_band_game_log_ids': [row.id for row in unknown_band],
                'consumed_evidence_objects': consumed,
                'floor_check': {'n': len(window_rows), 'minimum': MIN_OBSERVATION_APPEARANCES, 'passed': True},
            },
        ),
        limitations=tuple(limitations),
        state=EvidenceObject.COMPLETENESS_PARTIAL if reasons else EvidenceObject.COMPLETENESS_COMPLETE,
        reason_codes=reasons,
        window_days=window_days,
        degraded=bool(reasons),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _multi_inning_usage_observation_object(
    pitcher_id,
    product_date,
    rows,
    coverage,
    registry,
    templates,
    sync_run_id,
    source,
):
    window_days = OBSERVATION_WINDOW_DAYS
    window_rows = _qualifying_rows(_window_rows(rows, product_date, window_days))
    if not window_rows or not _denominator_citable(window_rows):
        return None
    floor_object = _sample_floor_object(
        PITCHER_MULTI_INNING_USAGE_OBSERVATION_RULE_ID,
        pitcher_id,
        product_date,
        window_rows,
        coverage,
        registry,
        templates,
        sync_run_id,
        source,
    )
    if floor_object is not None:
        return floor_object
    coverage_window = coverage.window(product_date, window_days)
    counted = []
    unknown = []
    citations = [_game_log_citation(row, ('game_date', 'mlb_game_pk', 'games_started'), citation_role='denominator_row') for row in window_rows]
    consumed = []
    for row in window_rows:
        source_object = _source_evidence_by_cited_game_log(row, 'outing_multi_inning')
        if source_object is None:
            continue
        consumed.append(_source_ref(source_object))
        citations.append(_source_evidence_citation(source_object, 'derived_from_evidence'))
        citations.extend(_passthrough_citations(source_object))
        if source_object.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE:
            counted.append(row)
        elif source_object.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN:
            unknown.append(row)
    lower = 'At least ' if unknown or not coverage_window.complete else ''
    claim = (
        f'{lower}{len(counted)} of {len(window_rows)} relief appearances in the '
        f'last 14 days were multi-inning per stored 0D-02 objects; '
        f'{len(unknown)} unassessable.'
    )
    reasons = []
    limitations = []
    if unknown:
        reasons.append(REASON_MULTI_INNING_UNKNOWN_IN_WINDOW)
    if not coverage_window.complete:
        reasons.append(REASON_INCOMPLETE_SLATE_DAY)
        limitations.append(LOWER_BOUND_LIMITATION)
    return _build_object(
        rule_id=PITCHER_MULTI_INNING_USAGE_OBSERVATION_RULE_ID,
        subject_type=SUBJECT_PITCHER,
        subject_id=pitcher_id,
        subject_key=f'pitcher:{pitcher_id}:{product_date.isoformat()}:multi-inning-usage-14',
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(citations + list(coverage_window.coverage_citations())),
        input_values=_window_input_values(product_date, window_rows),
        trace=_window_trace(
            product_date,
            window_days,
            window_rows,
            coverage_window,
            extra={
                'counted_game_log_ids': [row.id for row in counted],
                'unknown_game_log_ids': [row.id for row in unknown],
                'consumed_evidence_objects': consumed,
                'floor_check': {'n': len(window_rows), 'minimum': MIN_OBSERVATION_APPEARANCES, 'passed': True},
            },
        ),
        limitations=tuple(limitations),
        state=EvidenceObject.COMPLETENESS_PARTIAL if reasons else EvidenceObject.COMPLETENESS_COMPLETE,
        reason_codes=reasons,
        window_days=window_days,
        degraded=bool(reasons),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _first_reliever_usage_observation_object(
    pitcher_id,
    product_date,
    rows,
    coverage,
    registry,
    templates,
    sync_run_id,
    source,
):
    window_days = OBSERVATION_WINDOW_DAYS
    window_rows = _qualifying_rows(_window_rows(rows, product_date, window_days))
    if not window_rows or not _denominator_citable(window_rows):
        return None
    floor_object = _sample_floor_object(
        PITCHER_FIRST_RELIEVER_USAGE_OBSERVATION_RULE_ID,
        pitcher_id,
        product_date,
        window_rows,
        coverage,
        registry,
        templates,
        sync_run_id,
        source,
    )
    if floor_object is not None:
        return floor_object
    coverage_window = coverage.window(product_date, window_days)
    counted = []
    unknown = []
    consumed = []
    citations = [_game_log_citation(row, ('game_date', 'mlb_game_pk', 'games_started'), citation_role='denominator_row') for row in window_rows]
    for row in window_rows:
        order_object = _source_evidence(row, 'appearance_order_in_game')
        if order_object is not None:
            consumed.append(_source_ref(order_object))
            citations.append(_source_evidence_citation(order_object, 'derived_from_evidence'))
            citations.extend(_passthrough_citations(order_object))
        order = _order_from_evidence(order_object)
        if order_object is not None and order_object.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE and order == 2:
            counted.append(row)
        elif order_object is None or order_object.completeness_state != EvidenceObject.COMPLETENESS_COMPLETE or order is None:
            unknown.append(row)
    lower = 'At least ' if unknown or not coverage_window.complete else ''
    claim = (
        f'{lower}{len(counted)} of {len(window_rows)} relief appearances in the '
        f'last 14 days were first relief appearances for the team sequence; '
        f'{len(unknown)} order unknown.'
    )
    reasons = []
    limitations = []
    if unknown:
        reasons.append(REASON_ORDER_UNKNOWN_IN_WINDOW)
    if not coverage_window.complete:
        reasons.append(REASON_INCOMPLETE_SLATE_DAY)
        limitations.append(LOWER_BOUND_LIMITATION)
    return _build_object(
        rule_id=PITCHER_FIRST_RELIEVER_USAGE_OBSERVATION_RULE_ID,
        subject_type=SUBJECT_PITCHER,
        subject_id=pitcher_id,
        subject_key=f'pitcher:{pitcher_id}:{product_date.isoformat()}:first-relief-usage-14',
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(citations + list(coverage_window.coverage_citations())),
        input_values=_window_input_values(product_date, window_rows),
        trace=_window_trace(
            product_date,
            window_days,
            window_rows,
            coverage_window,
            extra={
                'counted_game_log_ids': [row.id for row in counted],
                'unknown_order_game_log_ids': [row.id for row in unknown],
                'consumed_evidence_objects': consumed,
                'floor_check': {'n': len(window_rows), 'minimum': MIN_OBSERVATION_APPEARANCES, 'passed': True},
            },
        ),
        limitations=tuple(limitations),
        state=EvidenceObject.COMPLETENESS_PARTIAL if reasons else EvidenceObject.COMPLETENESS_COMPLETE,
        reason_codes=reasons,
        window_days=window_days,
        degraded=bool(reasons),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _sample_floor_object(
    rule_id,
    pitcher_id,
    product_date,
    window_rows,
    coverage,
    registry,
    templates,
    sync_run_id,
    source,
):
    if len(window_rows) >= MIN_OBSERVATION_APPEARANCES:
        return None
    window = coverage.window(product_date, OBSERVATION_WINDOW_DAYS)
    claim = (
        f'Evidence withheld for pitcher {pitcher_id}: {len(window_rows)} qualifying '
        f'relief appearances in the last 14 days is below the required sample of '
        f'{MIN_OBSERVATION_APPEARANCES}.'
    )
    return _build_object(
        rule_id=rule_id,
        subject_type=SUBJECT_PITCHER,
        subject_id=pitcher_id,
        subject_key=f'pitcher:{pitcher_id}:{product_date.isoformat()}:{rule_id}:floor-14',
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(
            [_game_log_citation(row, ('game_date', 'mlb_game_pk', 'games_started'), citation_role='denominator_row') for row in window_rows]
            + list(window.coverage_citations())
        ),
        input_values=_window_input_values(product_date, window_rows),
        trace=_window_trace(
            product_date,
            OBSERVATION_WINDOW_DAYS,
            window_rows,
            window,
            extra={'floor_check': {'n': len(window_rows), 'minimum': MIN_OBSERVATION_APPEARANCES, 'passed': False}},
        ),
        state=EvidenceObject.COMPLETENESS_WITHHELD,
        reason_codes=[REASON_INSUFFICIENT_SAMPLE],
        window_days=OBSERVATION_WINDOW_DAYS,
        degraded=True,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _build_object(
    *,
    rule_id,
    subject_type,
    subject_id,
    subject_key,
    product_date,
    claim,
    cited_inputs,
    input_values,
    trace,
    registry,
    templates,
    sync_run_id,
    source,
    limitations=(),
    contradictions=(),
    state=EvidenceObject.COMPLETENESS_COMPLETE,
    reason_codes=None,
    window_days=None,
    degraded=False,
):
    _assert_text_has_no_entry_band_forbidden_terms(claim)
    if not cited_inputs:
        return None
    rule = registry.get(rule_id, RULE_VERSION)
    template = templates.get(_template_id(rule_id, window_days=window_days, degraded=degraded), RULE_VERSION)
    evidence = build_evidence_object(
        rule_id=rule.rule_id,
        rule_version=RULE_VERSION,
        claim_template=template,
        claim_values={'claim': claim},
        subject_type=subject_type,
        subject_id=subject_id,
        subject_key=subject_key,
        product_date=product_date,
        cited_inputs=tuple(cited_inputs),
        computation_trace=trace,
        input_values=dict(input_values or {}),
        readiness_payload=_readiness_payload(rule.required_input_families),
        limitations=tuple(limitations or ()),
        contradictions=tuple(contradictions or ()),
        registry=registry,
        sync_run_id=sync_run_id,
        source=EVIDENCE_SOURCE,
    )
    if state != EvidenceObject.COMPLETENESS_COMPLETE or reason_codes:
        evidence.completeness_state = state
        evidence.reason_codes = _dedupe(reason_codes or [])
        evidence.rendered_claim = claim
    if rule_id in LOCKED_INTERNAL_RULE_IDS and evidence.posture != EvidenceObject.POSTURE_INTERNAL_ONLY:
        raise EvidenceRuleError('posture-locked entry-context band evidence cannot be public_candidate')
    return BuiltEntryBandUsageEvidence(evidence=evidence, rule_id=rule_id, subject_key=evidence.subject_key)


def _upsert_evidence(new_evidence):
    return _upsert_evidence_batch([new_evidence])[0]


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


def _logs_for_range(start_date, end_date):
    return (
        GameLog.query
        .filter(GameLog.game_date >= start_date)
        .filter(GameLog.game_date <= end_date)
        .order_by(asc(GameLog.pitcher_id), asc(GameLog.game_date), asc(GameLog.mlb_game_pk), asc(GameLog.id))
        .all()
    )


def _logs_by_pitcher(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.pitcher_id].append(row)
    return grouped


def _window_rows(rows, product_date, window_days):
    start = product_date - timedelta(days=window_days - 1)
    return [row for row in rows if start <= row.game_date <= product_date and _is_finality_certified(row)]


def _qualifying_rows(rows):
    return [row for row in rows if row.games_started == 0]


def _denominator_citable(rows):
    return all(getattr(row, 'id', None) is not None for row in rows)


def _is_finality_certified(log):
    rows = ScheduledGame.query.filter_by(game_pk=log.mlb_game_pk).all()
    if not rows:
        return True
    return any(row.status_state == ScheduledGame.STATE_FINAL for row in rows)


def _source_evidence(log, rule_id):
    return (
        EvidenceObject.query
        .filter_by(
            rule_id=rule_id,
            subject_type=SUBJECT_APPEARANCE,
            subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}',
            product_date=log.game_date,
        )
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
        .order_by(asc(EvidenceObject.id))
        .first()
    )


def _source_evidence_by_cited_game_log(log, rule_id):
    citation = (
        EvidenceCitation.query
        .join(EvidenceObject)
        .filter(EvidenceObject.rule_id == rule_id)
        .filter(EvidenceObject.product_date == log.game_date)
        .filter(EvidenceCitation.source_table == 'game_logs')
        .filter(EvidenceCitation.source_pk == str(log.id))
        .order_by(asc(EvidenceObject.id))
        .first()
    )
    return citation.evidence_object if citation is not None else None


def _entry_context_values(entry):
    trace = dict(entry.computation_trace or {})
    margin_payload = trace.get('margin_arithmetic') or {}
    return {
        'entry_inning': _entry_inning_from_citations(entry),
        'margin': margin_payload.get('margin'),
    }


def _entry_inning_from_citations(entry):
    for citation in entry.citations or []:
        if citation.citation_role == 'entry_event':
            values = citation.cited_values or {}
            return values.get('inning')
    for payload in entry.typed_cited_inputs or []:
        if payload.get('citation_role') == 'entry_event':
            return (payload.get('cited_values') or {}).get('inning')
    return None


def _entry_source_game_pk(entry, log):
    for payload in entry.typed_cited_inputs or []:
        values = payload.get('cited_values') or {}
        if values.get('mlb_game_pk') is not None:
            return values.get('mlb_game_pk')
    return log.mlb_game_pk


def _band_cell_from_evidence(row):
    if row is None:
        return None
    return (row.computation_trace or {}).get('band_cell')


def _order_from_evidence(row):
    if row is None:
        return None
    return (row.computation_trace or {}).get('order')


def _entry_phase(inning):
    if inning <= ENTRY_PHASE_THRESHOLDS['early_max']:
        return 'early'
    if inning <= ENTRY_PHASE_THRESHOLDS['middle_max']:
        return 'middle'
    if inning <= ENTRY_PHASE_THRESHOLDS['late_max']:
        return 'late'
    return 'extras'


def _margin_band(margin):
    magnitude = abs(int(margin))
    if magnitude <= MARGIN_THRESHOLDS['one_run_max']:
        return 'one_run'
    if magnitude <= MARGIN_THRESHOLDS['two_three_max']:
        return 'two_three'
    return 'four_plus'


def _entry_band_trace(log, source_object, entry_values, decision):
    return {
        'steps': [
            'Consumed stored appearance_entry_context evidence.',
            'Read entry inning and margin from cited stored evidence.',
            'Mapped inning phase and margin band to the registered 12-cell table.',
            'Did not reconstruct runner base state.',
        ],
        'qualifying_decision': _qualifying_decision(log),
        'source_evidence_object': _source_ref(source_object) if source_object is not None else None,
        'entry_inning': (entry_values or {}).get('entry_inning'),
        'margin': (entry_values or {}).get('margin'),
        'entry_phase': (entry_values or {}).get('entry_phase'),
        'margin_band': (entry_values or {}).get('margin_band'),
        'band_cell': (entry_values or {}).get('band_cell'),
        'decision': decision,
    }


def _window_trace(product_date, window_days, rows, coverage_window, *, extra=None):
    payload = {
        'steps': [
            'Built trailing product-day window.',
            'Checked slate coverage for every window day.',
            'Evaluated qualifying-set decision for each appearance.',
            'Required every denominator row to be citable.',
        ],
        'product_date': product_date.isoformat(),
        'window_days': window_days,
        'window_start': coverage_window.start.isoformat(),
        'window_end': product_date.isoformat(),
        'window_day_list': [day.day.isoformat() for day in coverage_window.days],
        'coverage_complete': coverage_window.complete,
        'incomplete_days': coverage_window.incomplete_day_labels,
        'qualifying_set_decisions': [_qualifying_decision(row) for row in rows],
    }
    payload.update(extra or {})
    return payload


def _qualifying_decision(log):
    if not _is_finality_certified(log):
        decision = 'excluded_not_finality_certified'
    elif log.games_started == 0:
        decision = 'qualifying_relief_appearance'
    elif log.games_started is None:
        decision = REASON_APPEARANCE_ROLE_UNKNOWN
    else:
        decision = 'excluded_start'
    return {
        'game_log_id': log.id,
        'pitcher_id': log.pitcher_id,
        'mlb_game_pk': log.mlb_game_pk,
        'game_date': _iso(log.game_date),
        'games_started': log.games_started,
        'decision': decision,
    }


def _finish_values(log):
    return {
        'save_situation': bool(log.save_situation),
        'save': bool(log.save),
        'hold': bool(log.hold),
        'blown_save': bool(log.blown_save),
        'win': bool(log.win),
        'loss': bool(log.loss),
        'games_finished': log.games_finished,
    }


def _finish_claim(log, values, *, contradiction=None):
    if contradiction is not None:
        return (
            f'Finish-context conflict for pitcher {log.pitcher_id} in game '
            f'{log.mlb_game_pk}: stored finishing flags contradict each other.'
        )
    return (
        f'Finish-context flags for pitcher {log.pitcher_id} in game {log.mlb_game_pk}: '
        f'save opportunity {_yes_no(values["save_situation"])}, save {_yes_no(values["save"])}, '
        f'hold {_yes_no(values["hold"])}, blown save {_yes_no(values["blown_save"])}, '
        f'win {_yes_no(values["win"])}, loss {_yes_no(values["loss"])}, '
        f'games finished {_unknown_or_value(values["games_finished"])}.'
    )


def _finish_window_fields():
    return (
        'game_date',
        'mlb_game_pk',
        'games_started',
        'games_finished',
        'save_situation',
        'save',
        'hold',
        'blown_save',
        'win',
        'loss',
        'batters_faced',
    )


def _window_input_values(product_date, rows):
    return {
        'slate_coverage.slate_date': product_date.isoformat(),
        'game_logs.games_started': rows[0].games_started if rows else 0,
        'final_play_by_play.mlb_game_pk': rows[0].mlb_game_pk if rows else None,
    }


def _readiness_payload(required_families):
    return {
        'families': {
            family: {'status': SOURCE_READY, 'reason_codes': []}
            for family in required_families
        }
    }


def _source_ref(row):
    if row is None:
        return None
    return {
        'id': row.id,
        'rule_id': row.rule_id,
        'evidence_type': row.evidence_type,
        'subject_key': row.subject_key,
        'product_date': _iso(row.product_date),
        'state': row.completeness_state,
    }


def _source_evidence_citation(row, role):
    return EvidenceCitationInput(
        source_family='phase0d_evidence_contract',
        source_table='evidence_objects',
        source_pk=row.id,
        source_field_names=(
            'rule_id',
            'rule_version',
            'evidence_type',
            'subject_key',
            'product_date',
            'completeness_state',
            'rendered_claim',
            'computation_trace',
        ),
        citation_role=role,
        cited_values={
            'rule_id': row.rule_id,
            'rule_version': row.rule_version,
            'evidence_type': row.evidence_type,
            'subject_key': row.subject_key,
            'product_date': _iso(row.product_date),
            'completeness_state': row.completeness_state,
            'rendered_claim': row.rendered_claim,
            'computation_trace': dict(row.computation_trace or {}),
        },
        provenance={
            'source': row.source,
            'sync_run_id': row.sync_run_id,
            'correction_count': row.correction_count or 0,
            'last_corrected_at': _iso(row.last_corrected_at),
            'correction_source': row.correction_source,
        },
    )


def _missing_source_evidence_citation(log, rule_id):
    return EvidenceCitationInput(
        source_family='final_play_by_play',
        source_table='evidence_objects',
        source_pk=f'missing:{rule_id}:{log.pitcher_id}:{log.mlb_game_pk}',
        source_field_names=('mlb_game_pk',),
        citation_role='missing_input',
        cited_values={'mlb_game_pk': log.mlb_game_pk, 'rule_id': rule_id},
        provenance={'source': EVIDENCE_SOURCE},
    )


def _passthrough_citations(row):
    citations = []
    for citation in row.citations or []:
        citations.append(EvidenceCitationInput(
            source_family=citation.source_family,
            source_table=citation.source_table,
            source_pk=citation.source_pk,
            source_field_names=tuple(citation.source_field_names or ()),
            citation_role=citation.citation_role,
            cited_values=dict(citation.cited_values or {}),
            provenance=dict(citation.provenance or {'source': row.source}),
        ))
    return citations


def _game_log_citation(row, fields, citation_role='supporting_input'):
    return EvidenceCitationInput(
        source_family='game_logs',
        source_table='game_logs',
        source_pk=row.id,
        source_field_names=tuple(fields),
        citation_role=citation_role,
        cited_values={field: _citation_value(getattr(row, field, None)) for field in fields},
        provenance={
            'source': 'game_logs',
            'sync_run_id': row.last_stat_correction_sync_run_id,
            'stat_correction_count': row.stat_correction_count or 0,
            'last_stat_correction_at': _iso(row.last_stat_correction_at),
            'last_stat_correction_source': row.last_stat_correction_source,
        },
    )


def _record_finish_dead_letter(log, reason_code, sync_run_id):
    dead_letter.record_failure(
        FINISH_CONTEXT_CONTRADICTION_ENTITY_TYPE,
        reason_code,
        entity_ref=log.id,
        payload={
            'game_log_id': log.id,
            'pitcher_id': log.pitcher_id,
            'mlb_game_pk': log.mlb_game_pk,
            'save': bool(log.save),
            'blown_save': bool(log.blown_save),
            'hold': bool(log.hold),
            'games_started': log.games_started,
        },
        sync_run_id=sync_run_id,
        job_name='phase0d_entry_band_usage',
    )


def _appearance_subject_key(log, rule_id):
    return f'pitcher_appearance:{log.pitcher_id}:{log.mlb_game_pk}:{rule_id}'


def _template_id(rule_id, *, window_days=None, degraded=False):
    suffix = ''
    if window_days is not None:
        suffix += f'_{window_days}d'
    if degraded:
        suffix += '_degraded'
    return f'{rule_id}_claim{suffix}'


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

    def mapped_reasons(self):
        if self.complete:
            return []
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
        return [day.day.isoformat() for day in self.days if not day.complete]

    def coverage_citations(self):
        if self.complete:
            return tuple(day.citation() for day in self.days)
        return tuple(day.citation() for day in self.days if not day.complete)


class _CoverageCache:
    def __init__(self, product_date):
        self.product_date = product_date
        self._payloads = {}

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
            reasons.extend(day.mapped_reasons())
        return _CoverageWindow(start, end, days, reasons)


def _yes_no(value):
    return 'yes' if bool(value) else 'no'


def _unknown_or_value(value):
    return 'unknown' if value is None else str(value)


def _signed(value):
    if value is None:
        return 'unknown'
    value = int(value)
    return f'+{value}' if value > 0 else str(value)


def _ordinal(value):
    value = int(value)
    suffix = 'th'
    if value % 100 not in (11, 12, 13):
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(value % 10, 'th')
    return f'{value}{suffix}'


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _citation_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


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
