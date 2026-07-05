"""Internal Phase 0D inherited traffic and clean outing evidence family."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
import re

from sqlalchemy import asc

from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.scheduled_game import ScheduledGame
from services import dead_letter
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
EVIDENCE_TYPE = 'inherited_traffic_fact'
EVIDENCE_SOURCE = 'phase0d:inherited_traffic_evidence'
SUBJECT_TYPE = 'pitcher_appearance'
CONTRADICTION_ENTITY_TYPE = 'inherited_traffic_contradiction'

APPEARANCE_ENTRY_RULE_ID = 'appearance_entry_context'
APPEARANCE_CONTEXT_EVIDENCE_TYPE = 'appearance_context_fact'

INHERITED_RUNNERS_RULE_ID = 'appearance_inherited_runners'
INHERITED_RUNNERS_SCORED_RULE_ID = 'appearance_inherited_runners_scored'
INHERITED_TRAFFIC_OUTCOME_RULE_ID = 'appearance_inherited_traffic_outcome'
ENTRY_CORROBORATION_RULE_ID = 'appearance_inherited_entry_corroboration'
CLEAN_RULE_ID = 'outing_clean'
TRAFFIC_RULE_ID = 'outing_traffic'
UNKNOWN_RULE_ID = 'outing_context_unknown'

INHERITED_TRAFFIC_RULE_IDS = (
    INHERITED_RUNNERS_RULE_ID,
    INHERITED_RUNNERS_SCORED_RULE_ID,
    INHERITED_TRAFFIC_OUTCOME_RULE_ID,
    ENTRY_CORROBORATION_RULE_ID,
    CLEAN_RULE_ID,
    TRAFFIC_RULE_ID,
    UNKNOWN_RULE_ID,
)

REASON_INHERITED_FIELDS_UNKNOWN = 'inherited_fields_unknown'
REASON_INHERITED_SCORED_UNKNOWN = 'inherited_scored_unknown'
REASON_OUTING_COMPONENT_UNKNOWN = 'outing_component_unknown'
REASON_LEGACY_ROW_PRE_EXPANSION = 'legacy_row_pre_expansion'
REASON_APPEARANCE_ROLE_UNKNOWN = 'appearance_role_unknown'
REASON_ENTRY_CONTEXT_UNAVAILABLE = 'entry_context_unavailable'
REASON_ENTRY_CONTEXT_INCOHERENT = 'entry_context_incoherent'
REASON_INHERITED_EXCEEDS_CONTEXT = 'inherited_exceeds_context'
REASON_EXTRAS_AUTOMATIC_RUNNER = 'extras_automatic_runner'

REASON_GAME_LOG_CORRECTED = 'game_log_corrected'
REASON_ENTRY_CONTEXT_SUPERSEDED = 'entry_context_incoherent'

HBP_ROE_LIMITATION = (
    'Hit-by-pitch and reach-on-error are not stored and are outside this definition.'
)
LEGACY_TRAFFIC_LIMITATION = (
    'Legacy row caveat: this row predates the post-expansion sentinel, so '
    'missing hit/walk values may appear as zero; this traffic flag can '
    'under-fire but not over-fire.'
)
AUTOMATIC_RUNNER_LIMITATION = (
    'Extra-inning automatic runner may explain a half-inning-start entry with '
    'inherited traffic; BaseballOS records this as a timing-coherence '
    'exception, not PBP-derived base state.'
)
RESUMED_GAME_LIMITATION = 'game was suspended and resumed; events may span calendar dates'

MIN_TRAFFIC_BASERUNNERS = 3

_NO_PARTIAL_COMPLETENESS = (
    EvidenceObject.COMPLETENESS_COMPLETE,
    EvidenceObject.COMPLETENESS_UNKNOWN,
    EvidenceObject.COMPLETENESS_CONFLICT,
    EvidenceObject.COMPLETENESS_WITHHELD,
)

_RULE_DEFINITIONS = {
    INHERITED_RUNNERS_RULE_ID: (
        'The number of runners already on base when the pitcher entered, as '
        'recorded on his stored final pitching line in game_logs.inherited_runners.'
    ),
    INHERITED_RUNNERS_SCORED_RULE_ID: (
        'Of the runners the pitcher inherited, how many scored, from '
        'game_logs.inherited_runners_scored.'
    ),
    INHERITED_TRAFFIC_OUTCOME_RULE_ID: (
        'The descriptive outcome of inherited traffic for an appearance with '
        'inherited_runners known and greater than zero and '
        'inherited_runners_scored known.'
    ),
    ENTRY_CORROBORATION_RULE_ID: (
        'The coherence between the boxscore inherited-runner count and the '
        'current Phase 0D appearance_entry_context evidence object.'
    ),
    CLEAN_RULE_ID: (
        'A relief appearance in which every required component is known and '
        'zero: hits_allowed, walks, runs_allowed, and '
        'inherited_runners_scored, with batters_faced present as the '
        'post-expansion sentinel.'
    ),
    TRAFFIC_RULE_ID: (
        'A relief appearance with three or more baserunners allowed by the '
        'pitcher, counted as hits_allowed + walks at or above the registered '
        '3-baserunner threshold.'
    ),
    UNKNOWN_RULE_ID: (
        "An explicit record that an appearance's outing context cannot be "
        'assessed because one or more required components are unknown.'
    ),
}

_RULE_THRESHOLDS = {
    TRAFFIC_RULE_ID: {'min_baserunners_allowed': MIN_TRAFFIC_BASERUNNERS},
}

_REQUIRED_FIELDS = {
    INHERITED_RUNNERS_RULE_ID: ('game_logs.inherited_runners',),
    INHERITED_RUNNERS_SCORED_RULE_ID: (
        'game_logs.inherited_runners',
        'game_logs.inherited_runners_scored',
    ),
    INHERITED_TRAFFIC_OUTCOME_RULE_ID: (
        'game_logs.inherited_runners',
        'game_logs.inherited_runners_scored',
    ),
    ENTRY_CORROBORATION_RULE_ID: ('game_logs.inherited_runners',),
    CLEAN_RULE_ID: (
        'game_logs.games_started',
        'game_logs.batters_faced',
        'game_logs.hits_allowed',
        'game_logs.walks',
        'game_logs.runs_allowed',
        'game_logs.inherited_runners',
        'game_logs.inherited_runners_scored',
    ),
    TRAFFIC_RULE_ID: (
        'game_logs.hits_allowed',
        'game_logs.walks',
        'game_logs.innings_pitched_outs',
    ),
    UNKNOWN_RULE_ID: ('game_logs.games_started',),
}

_REQUIRED_INPUT_FAMILIES = {
    INHERITED_RUNNERS_RULE_ID: ('game_logs',),
    INHERITED_RUNNERS_SCORED_RULE_ID: ('game_logs',),
    INHERITED_TRAFFIC_OUTCOME_RULE_ID: ('game_logs',),
    ENTRY_CORROBORATION_RULE_ID: ('game_logs', 'final_play_by_play'),
    CLEAN_RULE_ID: ('game_logs',),
    TRAFFIC_RULE_ID: ('game_logs',),
    UNKNOWN_RULE_ID: ('game_logs',),
}

_FORBIDDEN_INHERITED_CLAIM_TERMS = (
    'availability',
    'available',
    'fatigue',
    'fatigued',
    'leverage',
    'pressure',
    'readiness',
    'ready',
    'prediction',
    'predict',
    'manager intent',
    'sharp',
    'shaky',
    'dominant',
    'shutdown',
    'escape',
    'spotless',
    'perfect',
    'no baserunners',
)


@dataclass(frozen=True)
class BuiltInheritedTrafficEvidence:
    evidence: EvidenceObject
    rule_id: str
    subject_key: str


_LOCAL_RULE_REGISTRY: EvidenceRuleRegistry | None = None
_LOCAL_TEMPLATE_REGISTRY: ClaimTemplateRegistry | None = None


def inherited_traffic_rule_definitions() -> dict[str, str]:
    return dict(_RULE_DEFINITIONS)


def inherited_traffic_rule_ids() -> tuple[str, ...]:
    return INHERITED_TRAFFIC_RULE_IDS


def register_inherited_traffic_rules(
    *,
    registry: EvidenceRuleRegistry | None = None,
    template_registry: ClaimTemplateRegistry | None = None,
) -> tuple[EvidenceRuleRegistry, ClaimTemplateRegistry]:
    rule_registry = registry or EvidenceRuleRegistry()
    claim_registry = template_registry or ClaimTemplateRegistry()
    for rule_id in INHERITED_TRAFFIC_RULE_IDS:
        _register_inherited_traffic_rule(rule_registry, _inherited_traffic_rule(rule_id))
        _register_inherited_traffic_template(
            claim_registry,
            ClaimTemplate(
                template_id=_template_id(rule_id),
                template_version=RULE_VERSION,
                template_text='{claim}',
            ),
        )
    return rule_registry, claim_registry


def build_inherited_traffic_evidence(
    product_date,
    *,
    sync_run_id=None,
    source='manual',
    commit=False,
    restrict_evidence_keys: set[str] | None = None,
) -> dict:
    """Build internal inherited traffic and outing context evidence for one date."""
    ref = _as_date(product_date)
    registry, templates = _local_registries()
    logs = _logs_for_date(ref)
    emitted = []

    for log in logs:
        built = _build_for_log(
            log=log,
            product_date=ref,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
        for item in built:
            if restrict_evidence_keys is not None and item.evidence.evidence_key not in restrict_evidence_keys:
                continue
            emitted.append(_upsert_evidence(item.evidence))

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return {
        'status': 'built',
        'product_date': ref.isoformat(),
        'rules': list(INHERITED_TRAFFIC_RULE_IDS),
        'game_logs_considered': len(logs),
        'objects_built': len(emitted),
        'objects_created': sum(1 for item in emitted if item == 'created'),
        'objects_refreshed': sum(1 for item in emitted if item == 'refreshed'),
    }


def mark_game_log_correction_for_inherited_traffic(
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


def mark_entry_context_supersession_for_inherited_traffic(
    entry_context_evidence,
    *,
    sync_run_id=None,
    reason_code=REASON_ENTRY_CONTEXT_SUPERSEDED,
    batch_size=100,
) -> dict:
    if entry_context_evidence is None or getattr(entry_context_evidence, 'id', None) is None:
        return {'marked_count': 0, 'evidence_ids': []}
    return mark_dependent_evidence_for_recompute(
        source_table='evidence_objects',
        source_pk=entry_context_evidence.id,
        reason_code=reason_code,
        batch_size=batch_size,
        sync_run_id=sync_run_id,
    )


def rebuild_marked_inherited_traffic_evidence(
    *,
    sync_run_id=None,
    source='manual',
    batch_size=100,
) -> dict:
    rows = (
        EvidenceObject.query
        .filter(EvidenceObject.rule_id.in_(INHERITED_TRAFFIC_RULE_IDS))
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
        result = build_inherited_traffic_evidence(
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
        _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY = register_inherited_traffic_rules()
    return _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY


def _inherited_traffic_rule(rule_id):
    allowed = (
        (EvidenceObject.COMPLETENESS_UNKNOWN,)
        if rule_id == UNKNOWN_RULE_ID
        else _NO_PARTIAL_COMPLETENESS
    )
    return EvidenceRule(
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        evidence_type=EVIDENCE_TYPE,
        plain_language_definition=_RULE_DEFINITIONS[rule_id],
        required_input_families=_REQUIRED_INPUT_FAMILIES[rule_id],
        required_cited_fields=_REQUIRED_FIELDS[rule_id],
        allowed_completeness=allowed,
        posture_default=EvidenceObject.POSTURE_INTERNAL_ONLY,
        thresholds=_RULE_THRESHOLDS.get(rule_id, {}),
    )


def _register_inherited_traffic_rule(registry, rule):
    if rule.posture_default != EvidenceObject.POSTURE_INTERNAL_ONLY:
        raise EvidenceRuleError('inherited traffic evidence must remain internal_only')
    _assert_text_has_no_inherited_forbidden_terms(rule.plain_language_definition)
    return registry.register(rule)


def _register_inherited_traffic_template(registry, template):
    _assert_text_has_no_inherited_forbidden_terms(template.template_text)
    return registry.register(template)


def _assert_text_has_no_inherited_forbidden_terms(text):
    lowered = f' {text or ""} '.lower()
    for term in _FORBIDDEN_INHERITED_CLAIM_TERMS:
        pattern = r'\b' + re.escape(term).replace(r'\ ', r'\s+') + r'\b'
        if re.search(pattern, lowered):
            raise EvidenceLanguageError(
                f'inherited traffic claim language uses forbidden term: {term}'
            )
    return True


def _logs_for_date(product_date):
    return (
        GameLog.query
        .filter(GameLog.game_date == product_date)
        .order_by(asc(GameLog.mlb_game_pk), asc(GameLog.id))
        .all()
    )


def _build_for_log(
    *,
    log,
    product_date,
    registry,
    templates,
    sync_run_id,
    source,
):
    if log.games_started == 1:
        return []

    resumed = _is_resumed_game(log.mlb_game_pk)
    if log.games_started is None:
        return [_unknown_object(
            log=log,
            product_date=product_date,
            reasons=[REASON_APPEARANCE_ROLE_UNKNOWN],
            detail={'games_started': None},
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
            resumed=resumed,
        )]

    built = []
    unknown_reasons = []
    unknown_detail = {}
    ir = log.inherited_runners
    irs = log.inherited_runners_scored

    built.append(_inherited_runners_object(
        log=log,
        product_date=product_date,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
        resumed=resumed,
    ))

    if ir is None:
        unknown_reasons.append(REASON_INHERITED_FIELDS_UNKNOWN)
        unknown_detail['inherited_runners'] = None
    else:
        built.extend(_inherited_scored_and_outcome_objects(
            log=log,
            product_date=product_date,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
            resumed=resumed,
        ))
        built.append(_entry_corroboration_object(
            log=log,
            product_date=product_date,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
            resumed=resumed,
        ))

    traffic = _traffic_object(
        log=log,
        product_date=product_date,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
        resumed=resumed,
    )
    if traffic is not None:
        built.append(traffic)

    clean = _clean_object(
        log=log,
        product_date=product_date,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
        resumed=resumed,
    )
    if clean is not None:
        built.append(clean)
    else:
        reasons, detail = _unknown_outing_reasons(log, traffic_emitted=traffic is not None)
        unknown_reasons.extend(reasons)
        unknown_detail.update(detail)

    if unknown_reasons:
        built.append(_unknown_object(
            log=log,
            product_date=product_date,
            reasons=_dedupe(unknown_reasons),
            detail=unknown_detail,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
            resumed=resumed,
        ))

    return [item for item in built if item is not None]


def _inherited_runners_object(*, log, product_date, registry, templates, sync_run_id, source, resumed):
    ir = log.inherited_runners
    state = EvidenceObject.COMPLETENESS_COMPLETE
    reasons = []
    if ir is None:
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        reasons = [REASON_INHERITED_FIELDS_UNKNOWN]
        claim = (
            f'Inherited runner count is unknown for pitcher {log.pitcher_id} '
            f'in game {log.mlb_game_pk}; the stored game-log field is null.'
        )
    else:
        claim = (
            f'Pitcher {log.pitcher_id} inherited {ir} runner(s) in game '
            f'{log.mlb_game_pk}, from the stored game-log pitching line.'
        )
    return _build_object(
        rule_id=INHERITED_RUNNERS_RULE_ID,
        log=log,
        product_date=product_date,
        claim=claim,
        cited_inputs=(_game_log_citation(log, ('games_started', 'inherited_runners')),),
        input_values={
            'game_logs.inherited_runners': ir,
            'game_logs.games_started': log.games_started,
        },
        trace={
            'steps': ['Read game_logs.inherited_runners without PBP derivation.'],
            'field_reads': {'inherited_runners': ir},
            'known_checks': {'inherited_runners_known': ir is not None},
        },
        limitations=_resumed_limitations(resumed),
        state=state,
        reason_codes=reasons + _resumed_reason(resumed),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _inherited_scored_and_outcome_objects(*, log, product_date, registry, templates, sync_run_id, source, resumed):
    ir = log.inherited_runners
    irs = log.inherited_runners_scored
    if ir is None:
        return []
    built = []

    if ir > 0:
        if irs is None:
            built.append(_inherited_scored_object(
                log=log,
                product_date=product_date,
                state=EvidenceObject.COMPLETENESS_UNKNOWN,
                reasons=[REASON_INHERITED_SCORED_UNKNOWN],
                claim=(
                    f'Inherited runners scored is unknown for pitcher {log.pitcher_id} '
                    f'in game {log.mlb_game_pk}; {ir} inherited runner(s) were recorded.'
                ),
                registry=registry,
                templates=templates,
                sync_run_id=sync_run_id,
                source=source,
                resumed=resumed,
            ))
            return built
        if irs > ir:
            built.append(_inherited_scored_conflict(log, product_date, registry, templates, sync_run_id, source, resumed))
            _record_dead_letter(REASON_INHERITED_EXCEEDS_CONTEXT, log=log, sync_run_id=sync_run_id)
            return built
        built.append(_inherited_scored_object(
            log=log,
            product_date=product_date,
            state=EvidenceObject.COMPLETENESS_COMPLETE,
            reasons=[],
            claim=(
                f'Pitcher {log.pitcher_id} had {irs} of {ir} inherited '
                f'runner(s) charged as runs in game {log.mlb_game_pk}.'
            ),
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
            resumed=resumed,
        ))
        built.append(_inherited_outcome_object(
            log=log,
            product_date=product_date,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
            resumed=resumed,
        ))
        return built

    if ir == 0 and irs is not None and irs > 0:
        built.append(_inherited_scored_conflict(log, product_date, registry, templates, sync_run_id, source, resumed))
        _record_dead_letter(REASON_INHERITED_EXCEEDS_CONTEXT, log=log, sync_run_id=sync_run_id)
    return built


def _inherited_scored_conflict(log, product_date, registry, templates, sync_run_id, source, resumed):
    return _inherited_scored_object(
        log=log,
        product_date=product_date,
        state=EvidenceObject.COMPLETENESS_CONFLICT,
        reasons=[REASON_INHERITED_EXCEEDS_CONTEXT],
        claim=(
            f'Stored inherited-runner fields disagree for pitcher {log.pitcher_id} '
            f'in game {log.mlb_game_pk}: inherited_runners={log.inherited_runners}, '
            f'inherited_runners_scored={log.inherited_runners_scored}.'
        ),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
        resumed=resumed,
    )


def _inherited_scored_object(*, log, product_date, state, reasons, claim, registry, templates, sync_run_id, source, resumed):
    return _build_object(
        rule_id=INHERITED_RUNNERS_SCORED_RULE_ID,
        log=log,
        product_date=product_date,
        claim=claim,
        cited_inputs=(_game_log_citation(
            log,
            ('games_started', 'inherited_runners', 'inherited_runners_scored'),
        ),),
        input_values={
            'game_logs.inherited_runners': log.inherited_runners,
            'game_logs.inherited_runners_scored': log.inherited_runners_scored,
            'game_logs.games_started': log.games_started,
        },
        trace={
            'steps': ['Read inherited_runners and inherited_runners_scored from game_logs.'],
            'field_reads': {
                'inherited_runners': log.inherited_runners,
                'inherited_runners_scored': log.inherited_runners_scored,
            },
            'contradiction_checks': {
                'scored_gt_inherited': (
                    log.inherited_runners_scored is not None
                    and log.inherited_runners is not None
                    and log.inherited_runners_scored > log.inherited_runners
                ),
                'scored_positive_when_inherited_zero': (
                    log.inherited_runners == 0
                    and (log.inherited_runners_scored or 0) > 0
                ),
            },
        },
        limitations=_resumed_limitations(resumed),
        state=state,
        reason_codes=list(reasons or []) + _resumed_reason(resumed),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _inherited_outcome_object(*, log, product_date, registry, templates, sync_run_id, source, resumed):
    ir = log.inherited_runners
    irs = log.inherited_runners_scored
    if irs == 0:
        outcome = 'stranded_all'
    elif irs == ir:
        outcome = 'allowed_all'
    else:
        outcome = 'allowed_some'
    return _build_object(
        rule_id=INHERITED_TRAFFIC_OUTCOME_RULE_ID,
        log=log,
        product_date=product_date,
        claim=(
            f'Inherited traffic outcome for pitcher {log.pitcher_id} in game '
            f'{log.mlb_game_pk}: {outcome} ({irs} of {ir} inherited runner(s) scored).'
        ),
        cited_inputs=(_game_log_citation(
            log,
            ('games_started', 'inherited_runners', 'inherited_runners_scored'),
        ),),
        input_values={
            'game_logs.inherited_runners': ir,
            'game_logs.inherited_runners_scored': irs,
            'outcome': outcome,
        },
        trace={
            'steps': ['Classified inherited traffic outcome from game-log counts.'],
            'field_reads': {'inherited_runners': ir, 'inherited_runners_scored': irs},
            'outcome': outcome,
        },
        limitations=_resumed_limitations(resumed),
        reason_codes=_resumed_reason(resumed),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _entry_corroboration_object(*, log, product_date, registry, templates, sync_run_id, source, resumed):
    entry_lookup = _current_entry_context(log, product_date)
    citations = [_game_log_citation(log, ('games_started', 'inherited_runners'))]
    limitations = _resumed_limitations(resumed)
    reasons = []
    state = EvidenceObject.COMPLETENESS_COMPLETE
    entry_payload = None
    trace = {
        'steps': [
            'Read current 0D-03 appearance_entry_context evidence object.',
            'Compared entry timing text to inherited_runners count.',
        ],
        'field_reads': {'inherited_runners': log.inherited_runners},
        'entry_context_lookup': entry_lookup['status'],
    }

    if entry_lookup['status'] == 'multiple':
        reasons = [REASON_ENTRY_CONTEXT_INCOHERENT]
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        claim = (
            f'Entry corroboration is unknown for pitcher {log.pitcher_id} in '
            f'game {log.mlb_game_pk}: multiple current entry-context evidence '
            'objects require review.'
        )
        _record_dead_letter(
            REASON_ENTRY_CONTEXT_INCOHERENT,
            log=log,
            sync_run_id=sync_run_id,
            extra={'duplicate_current_entry_context_ids': entry_lookup['ids']},
        )
    elif entry_lookup['status'] == 'missing':
        reasons = [REASON_ENTRY_CONTEXT_UNAVAILABLE]
        state = EvidenceObject.COMPLETENESS_UNKNOWN
        claim = (
            f'Entry corroboration is unknown for pitcher {log.pitcher_id} in '
            f'game {log.mlb_game_pk}: no current entry-context evidence was found.'
        )
    else:
        entry = entry_lookup['entry']
        citations.append(_entry_context_citation(entry))
        if entry.completeness_state in (
            EvidenceObject.COMPLETENESS_UNKNOWN,
            EvidenceObject.COMPLETENESS_WITHHELD,
        ):
            reasons = [REASON_ENTRY_CONTEXT_UNAVAILABLE]
            state = EvidenceObject.COMPLETENESS_UNKNOWN
            claim = (
                f'Entry corroboration is unknown for pitcher {log.pitcher_id} in '
                f'game {log.mlb_game_pk}: entry-context evidence is not complete.'
            )
        elif entry.completeness_state == EvidenceObject.COMPLETENESS_CONFLICT:
            reasons = [REASON_ENTRY_CONTEXT_INCOHERENT]
            state = EvidenceObject.COMPLETENESS_UNKNOWN
            claim = (
                f'Entry corroboration is unknown for pitcher {log.pitcher_id} in '
                f'game {log.mlb_game_pk}: entry-context evidence is in conflict.'
            )
        else:
            entry_payload = _parse_entry_context(entry)
            trace['entry_context_values'] = dict(entry_payload or {})
            state, reasons, claim, extra_limitations = _corroboration_state(
                log=log,
                entry_payload=entry_payload,
                sync_run_id=sync_run_id,
            )
            limitations.extend(extra_limitations)

    trace['reason_codes'] = list(reasons)
    trace['corroboration_state'] = state
    return _build_object(
        rule_id=ENTRY_CORROBORATION_RULE_ID,
        log=log,
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(citations),
        input_values={
            'game_logs.inherited_runners': log.inherited_runners,
            'entry_context_status': entry_lookup['status'],
        },
        trace=trace,
        limitations=limitations,
        state=state,
        reason_codes=list(reasons or []) + _resumed_reason(resumed),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _corroboration_state(*, log, entry_payload, sync_run_id):
    if not entry_payload:
        return (
            EvidenceObject.COMPLETENESS_UNKNOWN,
            [REASON_ENTRY_CONTEXT_UNAVAILABLE],
            (
                f'Entry corroboration is unknown for pitcher {log.pitcher_id} in '
                f'game {log.mlb_game_pk}: entry timing could not be read from '
                'entry-context evidence.'
            ),
            [],
        )
    if entry_payload['mid_inning']:
        return (
            EvidenceObject.COMPLETENESS_COMPLETE,
            [],
            (
                f'Entry corroboration is coherent for pitcher {log.pitcher_id} '
                f'in game {log.mlb_game_pk}: mid-inning entry with '
                f'{log.inherited_runners} inherited runner(s) recorded.'
            ),
            [],
        )
    if log.inherited_runners == 0:
        return (
            EvidenceObject.COMPLETENESS_COMPLETE,
            [],
            (
                f'Entry corroboration is coherent for pitcher {log.pitcher_id} '
                f'in game {log.mlb_game_pk}: half-inning-start entry with zero '
                'inherited runners recorded.'
            ),
            [],
        )
    if (entry_payload.get('inning') or 0) >= 10:
        return (
            EvidenceObject.COMPLETENESS_COMPLETE,
            [REASON_EXTRAS_AUTOMATIC_RUNNER],
            (
                f'Entry corroboration is coherent_extras_exception for pitcher '
                f'{log.pitcher_id} in game {log.mlb_game_pk}: half-inning-start '
                f'extra-inning entry with {log.inherited_runners} inherited '
                'runner(s) recorded.'
            ),
            [AUTOMATIC_RUNNER_LIMITATION],
        )
    _record_dead_letter(
        REASON_INHERITED_EXCEEDS_CONTEXT,
        log=log,
        sync_run_id=sync_run_id,
        extra={'entry_context': entry_payload},
    )
    return (
        EvidenceObject.COMPLETENESS_CONFLICT,
        [REASON_INHERITED_EXCEEDS_CONTEXT],
        (
            f'Entry corroboration disagrees for pitcher {log.pitcher_id} in '
            f'game {log.mlb_game_pk}: regulation half-inning-start entry with '
            f'{log.inherited_runners} inherited runner(s) recorded.'
        ),
        [],
    )


def _clean_object(*, log, product_date, registry, templates, sync_run_id, source, resumed):
    if not _clean_components_satisfied(log):
        return None
    return _build_object(
        rule_id=CLEAN_RULE_ID,
        log=log,
        product_date=product_date,
        claim=(
            f'Clean outing by definition for pitcher {log.pitcher_id} in game '
            f'{log.mlb_game_pk}: 0 hits, 0 walks, 0 runs allowed, and 0 '
            'inherited runners scored.'
        ),
        cited_inputs=(_game_log_citation(
            log,
            (
                'games_started',
                'batters_faced',
                'hits_allowed',
                'walks',
                'runs_allowed',
                'inherited_runners',
                'inherited_runners_scored',
            ),
        ),),
        input_values={
            'game_logs.games_started': log.games_started,
            'game_logs.batters_faced': log.batters_faced,
            'game_logs.hits_allowed': log.hits_allowed,
            'game_logs.walks': log.walks,
            'game_logs.runs_allowed': log.runs_allowed,
            'game_logs.inherited_runners': log.inherited_runners,
            'game_logs.inherited_runners_scored': log.inherited_runners_scored,
        },
        trace={
            'steps': ['Checked every clean outing component for known zero values.'],
            'clean_component_checks': _clean_component_checks(log),
            'mutual_exclusion_check': {'traffic_baserunners': _traffic_total(log)},
        },
        limitations=[HBP_ROE_LIMITATION] + _resumed_limitations(resumed),
        reason_codes=_resumed_reason(resumed),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _traffic_object(*, log, product_date, registry, templates, sync_run_id, source, resumed):
    if log.hits_allowed is None or log.walks is None:
        return None
    total = _traffic_total(log)
    if total < MIN_TRAFFIC_BASERUNNERS:
        return None
    limitations = [HBP_ROE_LIMITATION] + _resumed_limitations(resumed)
    reasons = _resumed_reason(resumed)
    if log.batters_faced is None:
        limitations.append(LEGACY_TRAFFIC_LIMITATION)
        reasons.append(REASON_LEGACY_ROW_PRE_EXPANSION)
    return _build_object(
        rule_id=TRAFFIC_RULE_ID,
        log=log,
        product_date=product_date,
        claim=(
            f'Traffic outing: allowed {total} baserunners ({log.hits_allowed} '
            f'hits, {log.walks} walks) across {log.innings_pitched_outs} outs '
            f'recorded, at or above the registered {MIN_TRAFFIC_BASERUNNERS}-'
            'baserunner threshold.'
        ),
        cited_inputs=(_game_log_citation(
            log,
            ('games_started', 'hits_allowed', 'walks', 'innings_pitched_outs', 'batters_faced'),
        ),),
        input_values={
            'game_logs.hits_allowed': log.hits_allowed,
            'game_logs.walks': log.walks,
            'game_logs.innings_pitched_outs': log.innings_pitched_outs,
            'traffic_baserunners': total,
            'threshold': MIN_TRAFFIC_BASERUNNERS,
        },
        trace={
            'steps': ['Computed traffic baserunners as hits_allowed + walks.'],
            'traffic_threshold_math': {
                'hits_allowed': log.hits_allowed,
                'walks': log.walks,
                'total': total,
                'min_baserunners_allowed': MIN_TRAFFIC_BASERUNNERS,
                'emits': total >= MIN_TRAFFIC_BASERUNNERS,
            },
            'mutual_exclusion_check': {'clean_possible': _clean_components_satisfied(log)},
        },
        limitations=limitations,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _unknown_object(*, log, product_date, reasons, detail, registry, templates, sync_run_id, source, resumed):
    reasons = _dedupe(list(reasons or []) + _resumed_reason(resumed))
    return _build_object(
        rule_id=UNKNOWN_RULE_ID,
        log=log,
        product_date=product_date,
        claim=(
            f'Outing context is unknown for pitcher {log.pitcher_id} in game '
            f'{log.mlb_game_pk}: {", ".join(reasons)}.'
        ),
        cited_inputs=(_game_log_citation(
            log,
            (
                'games_started',
                'batters_faced',
                'hits_allowed',
                'walks',
                'runs_allowed',
                'inherited_runners',
                'inherited_runners_scored',
            ),
        ),),
        input_values={'game_logs.games_started': log.games_started},
        trace={
            'steps': ['Recorded unknown outing context with named missing components.'],
            'field_reads': _core_field_reads(log),
            'known_null_checks': _known_null_checks(log),
            'unknown_detail': dict(detail or {}),
            'reason_codes': reasons,
        },
        limitations=_resumed_limitations(resumed),
        state=EvidenceObject.COMPLETENESS_UNKNOWN,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _unknown_outing_reasons(log, *, traffic_emitted):
    reasons = []
    detail = {}
    if log.inherited_runners is None:
        reasons.append(REASON_INHERITED_FIELDS_UNKNOWN)
        detail['inherited_runners'] = None
    if log.inherited_runners is not None and log.inherited_runners_scored is None:
        reasons.append(REASON_INHERITED_SCORED_UNKNOWN)
        detail['inherited_runners_scored'] = None
    if log.batters_faced is None and not traffic_emitted:
        reasons.append(REASON_LEGACY_ROW_PRE_EXPANSION)
        detail['batters_faced'] = None
    unknown_components = [
        field
        for field in ('hits_allowed', 'walks', 'runs_allowed')
        if getattr(log, field) is None
    ]
    if unknown_components:
        reasons.append(REASON_OUTING_COMPONENT_UNKNOWN)
        detail['unknown_components'] = unknown_components
    return _dedupe(reasons), detail


def _clean_components_satisfied(log):
    return (
        log.games_started == 0
        and log.batters_faced is not None
        and log.hits_allowed == 0
        and log.walks == 0
        and log.runs_allowed == 0
        and log.inherited_runners is not None
        and log.inherited_runners_scored == 0
    )


def _clean_component_checks(log):
    return {
        'games_started_is_relief': log.games_started == 0,
        'batters_faced_present': log.batters_faced is not None,
        'hits_allowed_zero': log.hits_allowed == 0,
        'walks_zero': log.walks == 0,
        'runs_allowed_zero': log.runs_allowed == 0,
        'inherited_runners_known': log.inherited_runners is not None,
        'inherited_runners_scored_zero': log.inherited_runners_scored == 0,
    }


def _traffic_total(log):
    if log.hits_allowed is None or log.walks is None:
        return None
    return log.hits_allowed + log.walks


def _current_entry_context(log, product_date):
    subject_id = _subject_id(log)
    rows = (
        EvidenceObject.query
        .filter(EvidenceObject.subject_type == SUBJECT_TYPE)
        .filter(EvidenceObject.subject_id == subject_id)
        .filter(EvidenceObject.product_date == product_date)
        .filter(EvidenceObject.evidence_type == APPEARANCE_CONTEXT_EVIDENCE_TYPE)
        .filter(EvidenceObject.rule_id == APPEARANCE_ENTRY_RULE_ID)
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
        .filter(EvidenceObject.superseded_by_evidence_id.is_(None))
        .order_by(asc(EvidenceObject.id))
        .all()
    )
    if not rows:
        return {'status': 'missing', 'rows': [], 'ids': []}
    if len(rows) > 1:
        return {'status': 'multiple', 'rows': rows, 'ids': [row.id for row in rows]}
    return {'status': 'found', 'entry': rows[0], 'rows': rows, 'ids': [rows[0].id]}


def _parse_entry_context(entry):
    text = entry.rendered_claim or ''
    inning_match = re.search(r'\b(?:top|bottom) of the (\d+)\b', text, re.I)
    mid_inning = 'mid-inning entry' in text.lower()
    half_start = 'half-inning start' in text.lower()
    if not inning_match or (not mid_inning and not half_start):
        return None
    return {
        'entry_evidence_id': entry.id,
        'inning': int(inning_match.group(1)),
        'mid_inning': mid_inning,
        'half_inning_start': half_start,
        'completeness_state': entry.completeness_state,
        'rendered_claim': entry.rendered_claim,
    }


def _build_object(
    *,
    rule_id,
    log,
    product_date,
    claim,
    cited_inputs,
    input_values,
    trace,
    limitations,
    registry,
    templates,
    sync_run_id,
    source,
    state=EvidenceObject.COMPLETENESS_COMPLETE,
    reason_codes=None,
):
    _assert_text_has_no_inherited_forbidden_terms(claim)
    rule = registry.get(rule_id, RULE_VERSION)
    template = templates.get(_template_id(rule_id), RULE_VERSION)
    evidence = build_evidence_object(
        rule_id=rule.rule_id,
        rule_version=RULE_VERSION,
        claim_template=template,
        claim_values={'claim': claim},
        subject_type=SUBJECT_TYPE,
        subject_id=_subject_id(log),
        product_date=product_date,
        cited_inputs=tuple(cited_inputs),
        computation_trace=trace,
        input_values=dict(input_values or {}),
        readiness_payload=_readiness_payload(),
        limitations=tuple(limitations or ()),
        registry=registry,
        sync_run_id=sync_run_id,
        source=EVIDENCE_SOURCE,
    )
    if state != EvidenceObject.COMPLETENESS_COMPLETE or reason_codes:
        evidence.completeness_state = state
        evidence.reason_codes = _dedupe(reason_codes or [])
        evidence.rendered_claim = claim
    return BuiltInheritedTrafficEvidence(
        evidence=evidence,
        rule_id=rule_id,
        subject_key=evidence.subject_key,
    )


def _readiness_payload():
    return {
        'families': {
            'game_logs': {'status': 'ready', 'reason_codes': []},
            'final_play_by_play': {'status': 'ready', 'reason_codes': []},
        }
    }


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


def _entry_context_citation(row):
    fields = ('rule_id', 'completeness_state', 'rendered_claim', 'computation_trace')
    return EvidenceCitationInput(
        source_family='final_play_by_play',
        source_table='evidence_objects',
        source_pk=row.id,
        source_field_names=fields,
        citation_role='corroborating_evidence',
        cited_values={field: _citation_value(getattr(row, field, None)) for field in fields},
        provenance={
            'source': row.source,
            'sync_run_id': row.sync_run_id,
            'rule_id': row.rule_id,
            'rule_version': row.rule_version,
            'recompute_status': row.recompute_status,
        },
    )


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


def _record_dead_letter(reason_code, *, log, sync_run_id, extra=None):
    payload = {
        'reason': reason_code,
        'pitcher_id': log.pitcher_id,
        'mlb_game_pk': log.mlb_game_pk,
        'game_log_id': log.id,
        'subject_id': _subject_id(log),
        'game_date': _citation_value(log.game_date),
        'inherited_runners': log.inherited_runners,
        'inherited_runners_scored': log.inherited_runners_scored,
    }
    payload.update(extra or {})
    dead_letter.record_failure(
        CONTRADICTION_ENTITY_TYPE,
        reason_code,
        entity_ref=log.mlb_game_pk,
        payload=payload,
        sync_run_id=sync_run_id,
        job_name='phase0d_inherited_traffic',
    )


def _is_resumed_game(game_pk):
    rows = ScheduledGame.query.filter(ScheduledGame.game_pk == game_pk).all()
    for row in rows:
        if (
            row.resumed_from_game_pk is not None
            or row.resumed_to_game_pk is not None
            or row.original_product_date is not None
            or row.resumed_product_date is not None
        ):
            return True
    return False


def _subject_id(log):
    return f'{log.pitcher_id}:{log.mlb_game_pk}'


def _resumed_limitations(resumed):
    return [RESUMED_GAME_LIMITATION] if resumed else []


def _resumed_reason(resumed):
    return []


def _core_field_reads(log):
    return {
        'games_started': log.games_started,
        'batters_faced': log.batters_faced,
        'hits_allowed': log.hits_allowed,
        'walks': log.walks,
        'runs_allowed': log.runs_allowed,
        'innings_pitched_outs': log.innings_pitched_outs,
        'inherited_runners': log.inherited_runners,
        'inherited_runners_scored': log.inherited_runners_scored,
    }


def _known_null_checks(log):
    return {
        field: getattr(log, field) is not None
        for field in (
            'games_started',
            'batters_faced',
            'hits_allowed',
            'walks',
            'runs_allowed',
            'inherited_runners',
            'inherited_runners_scored',
        )
    }


def _template_id(rule_id):
    return f'{rule_id}_claim'


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
    return value.isoformat() if value is not None else None


def _dedupe(values):
    result = []
    for value in values or []:
        if value and value not in result:
            result.append(value)
    return result
