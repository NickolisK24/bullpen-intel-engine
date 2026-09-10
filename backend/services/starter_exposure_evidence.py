"""Internal Phase 0D starter exposure and calendar-density evidence family."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re

from sqlalchemy import asc

from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.team_game_pitching_split import TeamGamePitchingSplit
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
EVIDENCE_SOURCE = 'phase0d:starter_exposure_evidence'
SUBJECT_TYPE = 'team'
SOURCE_READY = 'ready'

SHARE_RULE_ID = 'team_bullpen_share_of_outs'
OUTS_RULE_ID = 'team_bullpen_outs_window'
PITCHES_RULE_ID = 'team_bullpen_pitches_window'
APPEARANCES_RULE_ID = 'team_reliever_appearances_window'
SHORT_START_RULE_ID = 'team_short_start_count_window'
CONSECUTIVE_RULE_ID = 'team_consecutive_game_days'
DOUBLEHEADER_TODAY_RULE_ID = 'team_doubleheader_today'
RECENT_DOUBLEHEADER_RULE_ID = 'team_recent_doubleheader'
OFF_DAY_YESTERDAY_RULE_ID = 'team_off_day_yesterday'
OFF_DAY_TOMORROW_RULE_ID = 'team_off_day_tomorrow'
DENSITY_RULE_ID = 'team_calendar_density'

STARTER_EXPOSURE_RULE_IDS = (
    SHARE_RULE_ID,
    OUTS_RULE_ID,
    PITCHES_RULE_ID,
    APPEARANCES_RULE_ID,
    SHORT_START_RULE_ID,
    CONSECUTIVE_RULE_ID,
    DOUBLEHEADER_TODAY_RULE_ID,
    RECENT_DOUBLEHEADER_RULE_ID,
    OFF_DAY_YESTERDAY_RULE_ID,
    OFF_DAY_TOMORROW_RULE_ID,
    DENSITY_RULE_ID,
)

WINDOW_DAYS = (7, 14)
DENSITY_WINDOW_DAYS = 7
SHORT_START_MAX_OUTS = 14

REASON_SPLIT_ROW_MISSING = 'split_row_missing'
REASON_SPLIT_ROW_PARTIAL = 'split_row_partial'
REASON_SPLIT_ROW_UNKNOWN = 'split_row_unknown'
REASON_STARTER_IDENTITY_UNKNOWN = 'starter_identity_unknown'
REASON_STARTER_OUTS_UNKNOWN = 'starter_outs_unknown'
REASON_BULLPEN_COMPONENT_UNKNOWN = 'bullpen_component_unknown'
REASON_UNKNOWN_PITCH_COUNT = 'unknown_pitch_count_in_window'
REASON_SHARE_DENOMINATOR_UNAVAILABLE = 'share_denominator_unavailable'
REASON_AMBIGUOUS_RESUMED_GAME = 'ambiguous_resumed_game_in_window'
REASON_CALENDAR_CONTEXT_UNAVAILABLE = 'calendar_context_unavailable'
REASON_CALENDAR_CONTEXT_STALE = 'calendar_context_stale'
REASON_WINDOW_PRECEDES_COVERAGE = 'window_precedes_coverage_history'
REASON_NO_FINAL_GAME_ON_DATE = 'no_final_game_on_date'
REASON_SOURCE_FAMILY_NOT_READY = 'source_family_not_ready'
REASON_SPLIT_ROW_CORRECTED = 'team_game_pitching_split_corrected'

APPEARANCES_NOT_DISTINCT_ARMS_LIMITATION = (
    'Relievers used is an appearance count, not a distinct-arm count; the same '
    'pitcher can count once per game.'
)
SCHEDULE_SUBJECT_TO_CHANGE_LIMITATION = (
    "Schedule fact as of last ingestion; postponements, makeups, and "
    "rescheduling can change tomorrow's schedule."
)
RESUMED_GAME_LIMITATION = 'game was suspended and resumed; events may span calendar dates'
EXPECTED_GAME_SET_LIMITATION = (
    'This branch does not reconstruct missing team games from game logs or play-by-play; '
    'missing expected team-game detection is limited to existing split/readiness signals.'
)

_WINDOW_RULE_IDS = {
    SHARE_RULE_ID,
    OUTS_RULE_ID,
    PITCHES_RULE_ID,
    APPEARANCES_RULE_ID,
    SHORT_START_RULE_ID,
    RECENT_DOUBLEHEADER_RULE_ID,
    DENSITY_RULE_ID,
}

_RULE_DEFINITIONS = {
    SHARE_RULE_ID: (
        "Of all outs the team's pitchers recorded over the trailing 7-day and "
        '14-day windows ending on the evidence date, the share recorded by '
        'relievers: sum of bullpen_outs_recorded divided by sum of '
        'total_team_outs across the team final games in the window.'
    ),
    OUTS_RULE_ID: (
        "Total outs recorded by the team's relievers across the team final "
        'games in the trailing 7-day and 14-day windows.'
    ),
    PITCHES_RULE_ID: (
        "Total pitches thrown by the team's relievers across the trailing "
        '7-day and 14-day windows.'
    ),
    APPEARANCES_RULE_ID: (
        'The sum of per-game relievers_used_count across the team final games '
        'in the trailing 7-day and 14-day windows; this is reliever '
        'appearances, not distinct arms.'
    ),
    SHORT_START_RULE_ID: (
        "How many of the team's final games in the trailing 7-day and 14-day "
        'windows had a start shorter than five innings, with '
        'starter_outs_recorded <= 14.'
    ),
    CONSECUTIVE_RULE_ID: (
        "The team's count of consecutive game days entering the evidence date, "
        "from the stored calendar context of that date's final game or games."
    ),
    DOUBLEHEADER_TODAY_RULE_ID: (
        'The team played two or more final games on the evidence date, based on '
        'per-game split rows carrying doubleheader flag or code and game numbers.'
    ),
    RECENT_DOUBLEHEADER_RULE_ID: (
        'The team played a doubleheader on at least one day within the trailing '
        '7-day window ending on the evidence date.'
    ),
    OFF_DAY_YESTERDAY_RULE_ID: (
        'The team had no game on the day before the evidence date, from the '
        "stored off_day_before calendar fact of the evidence date's final game."
    ),
    OFF_DAY_TOMORROW_RULE_ID: (
        'No game appears on the team schedule for the day after the evidence '
        'date, from the stored off_day_after calendar fact.'
    ),
    DENSITY_RULE_ID: (
        'A bundle of counted calendar facts for the team over the trailing '
        '7-day window ending on the evidence date: final games played, distinct '
        'game days, off days, doubleheader days, and consecutive game-day count '
        'entering the evidence date.'
    ),
}

_RULE_THRESHOLDS = {
    SHARE_RULE_ID: {'window_7': 7, 'window_14': 14},
    OUTS_RULE_ID: {'window_7': 7, 'window_14': 14},
    PITCHES_RULE_ID: {'window_7': 7, 'window_14': 14},
    APPEARANCES_RULE_ID: {'window_7': 7, 'window_14': 14},
    SHORT_START_RULE_ID: {
        'window_7': 7,
        'window_14': 14,
        'short_start_max_outs': SHORT_START_MAX_OUTS,
    },
    RECENT_DOUBLEHEADER_RULE_ID: {'window_days': 7},
    DENSITY_RULE_ID: {'window_days': 7},
}

_REQUIRED_FIELDS = {
    SHARE_RULE_ID: (
        'team_game_pitching_splits.bullpen_outs_recorded',
        'team_game_pitching_splits.total_team_outs',
    ),
    OUTS_RULE_ID: ('team_game_pitching_splits.bullpen_outs_recorded',),
    PITCHES_RULE_ID: ('team_game_pitching_splits.bullpen_pitches_thrown',),
    APPEARANCES_RULE_ID: ('team_game_pitching_splits.relievers_used_count',),
    SHORT_START_RULE_ID: (
        'team_game_pitching_splits.starter_identity_status',
        'team_game_pitching_splits.starter_outs_recorded',
    ),
    CONSECUTIVE_RULE_ID: (
        'team_game_pitching_splits.consecutive_game_day_count_entering',
    ),
    DOUBLEHEADER_TODAY_RULE_ID: (
        'team_game_pitching_splits.doubleheader_flag',
        'team_game_pitching_splits.game_number',
    ),
    RECENT_DOUBLEHEADER_RULE_ID: (
        'team_game_pitching_splits.doubleheader_flag',
        'team_game_pitching_splits.game_date',
    ),
    OFF_DAY_YESTERDAY_RULE_ID: ('team_game_pitching_splits.off_day_before',),
    OFF_DAY_TOMORROW_RULE_ID: ('team_game_pitching_splits.off_day_after',),
    DENSITY_RULE_ID: (
        'team_game_pitching_splits.game_date',
        'team_game_pitching_splits.doubleheader_flag',
        'team_game_pitching_splits.consecutive_game_day_count_entering',
    ),
}

_FORBIDDEN_STARTER_EXPOSURE_TERMS = (
    'availability',
    'available',
    'fatigue',
    'fatigued',
    'readiness',
    'ready',
    'leverage',
    'pressure',
    'prediction',
    'predict',
    'opener',
    'bulk',
    'overworked',
    'struggling',
    'travel',
    'quality',
    'rotation',
    'score',
    'grade',
    'rank',
    'rested',
    'likely',
    'should',
)


@dataclass(frozen=True)
class BuiltStarterExposureEvidence:
    evidence: EvidenceObject
    rule_id: str
    subject_key: str


@dataclass(frozen=True)
class Exclusion:
    row: TeamGamePitchingSplit
    reason: str
    detail: str


_LOCAL_RULE_REGISTRY: EvidenceRuleRegistry | None = None
_LOCAL_TEMPLATE_REGISTRY: ClaimTemplateRegistry | None = None


def starter_exposure_rule_definitions() -> dict[str, str]:
    return dict(_RULE_DEFINITIONS)


def starter_exposure_rule_ids() -> tuple[str, ...]:
    return STARTER_EXPOSURE_RULE_IDS


def register_starter_exposure_rules(
    *,
    registry: EvidenceRuleRegistry | None = None,
    template_registry: ClaimTemplateRegistry | None = None,
) -> tuple[EvidenceRuleRegistry, ClaimTemplateRegistry]:
    rule_registry = registry or EvidenceRuleRegistry()
    claim_registry = template_registry or ClaimTemplateRegistry()
    for rule_id in STARTER_EXPOSURE_RULE_IDS:
        _register_starter_exposure_rule(rule_registry, _starter_exposure_rule(rule_id))
        _register_starter_exposure_template(
            claim_registry,
            ClaimTemplate(
                template_id=_template_id(rule_id),
                template_version=RULE_VERSION,
                template_text='{claim}',
            ),
        )
    return rule_registry, claim_registry


def build_starter_exposure_evidence(
    product_date,
    *,
    sync_run_id=None,
    source='manual',
    commit=False,
    restrict_evidence_keys: set[str] | None = None,
) -> dict:
    """Build internal starter exposure and calendar-density evidence for one date."""
    ref = _as_date(product_date)
    registry, templates = _local_registries()
    rows_by_team = _split_rows_by_team(ref)
    emitted = []

    for team_id, rows in rows_by_team.items():
        built = _build_for_team(
            team_id=team_id,
            product_date=ref,
            rows=rows,
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
        'rules': list(STARTER_EXPOSURE_RULE_IDS),
        'teams_considered': len(rows_by_team),
        'objects_built': len(emitted),
        'objects_created': sum(1 for item in emitted if item == 'created'),
        'objects_refreshed': sum(1 for item in emitted if item == 'refreshed'),
    }


def mark_team_game_pitching_split_correction_for_starter_exposure(
    split_row,
    *,
    sync_run_id=None,
    reason_code=REASON_SPLIT_ROW_CORRECTED,
    batch_size=100,
) -> dict:
    if split_row is None or getattr(split_row, 'id', None) is None:
        return {'marked_count': 0, 'evidence_ids': []}
    return mark_dependent_evidence_for_recompute(
        source_table='team_game_pitching_splits',
        source_pk=split_row.id,
        reason_code=reason_code,
        batch_size=batch_size,
        sync_run_id=sync_run_id,
    )


def rebuild_marked_starter_exposure_evidence(
    *,
    sync_run_id=None,
    source='manual',
    batch_size=100,
) -> dict:
    rows = (
        EvidenceObject.query
        .filter(EvidenceObject.rule_id.in_(STARTER_EXPOSURE_RULE_IDS))
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
        result = build_starter_exposure_evidence(
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
        _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY = register_starter_exposure_rules()
    return _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY


def _starter_exposure_rule(rule_id):
    required_families = (
        ('team_game_pitching_splits', 'calendar_context', 'slate_coverage')
        if rule_id in _WINDOW_RULE_IDS
        else ('team_game_pitching_splits', 'calendar_context')
    )
    return EvidenceRule(
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        evidence_type=rule_id,
        plain_language_definition=_RULE_DEFINITIONS[rule_id],
        required_input_families=required_families,
        required_cited_fields=_REQUIRED_FIELDS[rule_id],
        posture_default=EvidenceObject.POSTURE_INTERNAL_ONLY,
        thresholds=_RULE_THRESHOLDS.get(rule_id, {}),
    )


def _register_starter_exposure_rule(registry, rule):
    if rule.posture_default != EvidenceObject.POSTURE_INTERNAL_ONLY:
        raise EvidenceRuleError('starter exposure evidence must remain internal_only')
    _assert_text_has_no_starter_exposure_forbidden_terms(rule.plain_language_definition)
    return registry.register(rule)


def _register_starter_exposure_template(registry, template):
    _assert_text_has_no_starter_exposure_forbidden_terms(template.template_text)
    return registry.register(template)


def _assert_text_has_no_starter_exposure_forbidden_terms(text):
    lowered = f' {text or ""} '.lower()
    for term in _FORBIDDEN_STARTER_EXPOSURE_TERMS:
        pattern = r'\b' + re.escape(term).replace(r'\ ', r'\s+') + r'\b'
        if re.search(pattern, lowered):
            raise EvidenceLanguageError(
                f'starter exposure claim language uses forbidden term: {term}'
            )
    return True


def _split_rows_by_team(product_date):
    start = product_date - timedelta(days=13)
    rows = (
        TeamGamePitchingSplit.query
        .filter(TeamGamePitchingSplit.game_date >= start)
        .filter(TeamGamePitchingSplit.game_date <= product_date)
        .order_by(
            asc(TeamGamePitchingSplit.team_id),
            asc(TeamGamePitchingSplit.game_date),
            asc(TeamGamePitchingSplit.game_number),
            asc(TeamGamePitchingSplit.mlb_game_pk),
            asc(TeamGamePitchingSplit.id),
        )
        .all()
    )
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.team_id].append(row)
    return dict(sorted(grouped.items()))


def _build_for_team(
    *,
    team_id,
    product_date,
    rows,
    registry,
    templates,
    sync_run_id,
    source,
):
    rows = list(rows or [])
    built = []
    for window_days in WINDOW_DAYS:
        window_rows = _window_rows(rows, product_date, window_days)
        if not window_rows:
            continue
        window = _analyze_window(window_rows, product_date, window_days)
        built.extend([
            _share_object(team_id, product_date, window, registry, templates, sync_run_id, source),
            _outs_object(team_id, product_date, window, registry, templates, sync_run_id, source),
            _pitches_object(team_id, product_date, window, registry, templates, sync_run_id, source),
            _appearances_object(team_id, product_date, window, registry, templates, sync_run_id, source),
            _short_start_object(team_id, product_date, window, registry, templates, sync_run_id, source),
        ])

    today_rows = [row for row in rows if row.game_date == product_date]
    if today_rows:
        today = _analyze_calendar_rows(today_rows)
        built.extend([
            _consecutive_object(team_id, product_date, today, registry, templates, sync_run_id, source),
            _doubleheader_today_object(team_id, product_date, today, registry, templates, sync_run_id, source),
            _off_day_yesterday_object(team_id, product_date, today, registry, templates, sync_run_id, source),
            _off_day_tomorrow_object(team_id, product_date, today, registry, templates, sync_run_id, source),
        ])
    density_rows = _window_rows(rows, product_date, DENSITY_WINDOW_DAYS)
    if density_rows:
        density = _analyze_window(density_rows, product_date, DENSITY_WINDOW_DAYS)
        built.extend([
            _recent_doubleheader_object(team_id, product_date, density, registry, templates, sync_run_id, source),
            _density_object(team_id, product_date, density, registry, templates, sync_run_id, source),
        ])
    return [item for item in built if item is not None]


def _share_object(team_id, product_date, window, registry, templates, sync_run_id, source):
    fields = ('game_date', 'mlb_game_pk', 'bullpen_outs_recorded', 'total_team_outs',
              'split_completeness_status', 'suspended_resumed_linkage_status')
    citations = _citations_for_window(window, fields)
    bullpen_unknown = [row for row in window.included_rows if row.bullpen_outs_recorded is None]
    total_unknown = [row for row in window.included_rows if row.total_team_outs is None]
    denominator = _sum_known(window.included_rows, 'total_team_outs')
    if window.exclusions or bullpen_unknown or total_unknown or not denominator:
        reasons = _dedupe(
            window.reason_codes
            + ([REASON_BULLPEN_COMPONENT_UNKNOWN] if bullpen_unknown or total_unknown else [])
            + ([REASON_SHARE_DENOMINATOR_UNAVAILABLE] if not denominator else [])
        )
        known_bullpen = _sum_known(window.included_rows, 'bullpen_outs_recorded')
        claim = (
            f'Bullpen share of team outs cannot be stated for team {team_id} '
            f'over the {window.window_days}-day window ending {product_date.isoformat()}; '
            f'{window.complete_row_count} complete split rows have known bullpen outs '
            f'{known_bullpen}.'
        )
        return _build_object(
            rule_id=SHARE_RULE_ID,
            team_id=team_id,
            product_date=product_date,
            subject_suffix=f'window-{window.window_days}',
            claim=claim,
            cited_inputs=citations,
            input_values={
                'team_game_pitching_splits.bullpen_outs_recorded': _first_value(window.rows, 'bullpen_outs_recorded'),
                'team_game_pitching_splits.total_team_outs': _first_value(window.rows, 'total_team_outs'),
                'known_bullpen_outs_subtotal': known_bullpen,
            },
            trace=window.trace('ratio_degrades_to_unknown'),
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=reasons or [REASON_SHARE_DENOMINATOR_UNAVAILABLE],
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )

    bullpen_outs = sum(row.bullpen_outs_recorded for row in window.included_rows)
    total_outs = sum(row.total_team_outs for row in window.included_rows)
    pct = round((bullpen_outs / total_outs) * 100)
    claim = (
        f'Relievers recorded {bullpen_outs} of {total_outs} team outs '
        f'({pct}%) over the {window.window_days}-day window ending '
        f'{product_date.isoformat()} ({len(window.included_rows)} final games, '
        'all splits complete).'
    )
    return _build_object(
        rule_id=SHARE_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix=f'window-{window.window_days}',
        claim=claim,
        cited_inputs=citations,
        input_values={
            'team_game_pitching_splits.bullpen_outs_recorded': bullpen_outs,
            'team_game_pitching_splits.total_team_outs': total_outs,
            'share_percent': pct,
        },
        trace=window.trace('ratio_complete'),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _outs_object(team_id, product_date, window, registry, templates, sync_run_id, source):
    fields = ('game_date', 'mlb_game_pk', 'bullpen_outs_recorded', 'split_completeness_status',
              'suspended_resumed_linkage_status')
    citations = _citations_for_window(window, fields)
    unknown = [row for row in window.included_rows if row.bullpen_outs_recorded is None]
    known_total = _sum_known(window.included_rows, 'bullpen_outs_recorded')
    if unknown:
        claim = (
            f'Reliever outs total cannot be stated for team {team_id} over the '
            f'{window.window_days}-day window ending {product_date.isoformat()}; '
            f'{len(window.included_rows) - len(unknown)} games have known-value subtotal {known_total}.'
        )
        return _build_object(
            rule_id=OUTS_RULE_ID,
            team_id=team_id,
            product_date=product_date,
            subject_suffix=f'window-{window.window_days}',
            claim=claim,
            cited_inputs=citations,
            input_values={'team_game_pitching_splits.bullpen_outs_recorded': _first_value(window.rows, 'bullpen_outs_recorded')},
            trace=window.trace('outs_unknown_component'),
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=[REASON_BULLPEN_COMPONENT_UNKNOWN],
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    if window.exclusions:
        claim = (
            f'Relievers recorded at least {known_total} outs over the '
            f'{window.window_days}-day window ending {product_date.isoformat()}; '
            f'{len(window.exclusions)} games excluded because {_reason_summary(window.exclusions)}.'
        )
        return _build_object(
            rule_id=OUTS_RULE_ID,
            team_id=team_id,
            product_date=product_date,
            subject_suffix=f'window-{window.window_days}',
            claim=claim,
            cited_inputs=citations,
            input_values={'team_game_pitching_splits.bullpen_outs_recorded': _first_value(window.rows, 'bullpen_outs_recorded')},
            trace=window.trace('count_lower_bound_partial'),
            state=EvidenceObject.COMPLETENESS_PARTIAL,
            reason_codes=window.reason_codes,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    claim = (
        f'Relievers recorded {known_total} outs over the {window.window_days}-day '
        f'window ending {product_date.isoformat()} across {len(window.included_rows)} final games.'
    )
    return _build_object(
        rule_id=OUTS_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix=f'window-{window.window_days}',
        claim=claim,
        cited_inputs=citations,
        input_values={'team_game_pitching_splits.bullpen_outs_recorded': known_total},
        trace=window.trace('count_complete'),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _pitches_object(team_id, product_date, window, registry, templates, sync_run_id, source):
    fields = ('game_date', 'mlb_game_pk', 'bullpen_pitches_thrown', 'split_completeness_status',
              'suspended_resumed_linkage_status')
    citations = _citations_for_window(window, fields)
    unknown = [row for row in window.included_rows if row.bullpen_pitches_thrown is None]
    if window.exclusions or unknown:
        known_rows = [row for row in window.included_rows if row.bullpen_pitches_thrown is not None]
        known_subtotal = sum(row.bullpen_pitches_thrown for row in known_rows)
        reasons = _dedupe(window.reason_codes + ([REASON_UNKNOWN_PITCH_COUNT] if unknown else []))
        claim = (
            f'Bullpen pitch total cannot be stated for team {team_id} over the '
            f'{window.window_days}-day window ending {product_date.isoformat()}: '
            f'{len(known_rows)} of {len(window.rows)} games have known bullpen pitch counts, '
            f'known-value subtotal {known_subtotal}.'
        )
        return _build_object(
            rule_id=PITCHES_RULE_ID,
            team_id=team_id,
            product_date=product_date,
            subject_suffix=f'window-{window.window_days}',
            claim=claim,
            cited_inputs=citations,
            input_values={'team_game_pitching_splits.bullpen_pitches_thrown': _first_value(window.rows, 'bullpen_pitches_thrown')},
            trace=window.trace('pitch_total_unknown', extra={
                'known_pitch_count': len(known_rows),
                'known_value_subtotal': known_subtotal,
            }),
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=reasons or [REASON_UNKNOWN_PITCH_COUNT],
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    total = sum(row.bullpen_pitches_thrown for row in window.included_rows)
    claim = (
        f'Relievers threw {total} pitches over the {window.window_days}-day '
        f'window ending {product_date.isoformat()} across {len(window.included_rows)} final games.'
    )
    return _build_object(
        rule_id=PITCHES_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix=f'window-{window.window_days}',
        claim=claim,
        cited_inputs=citations,
        input_values={'team_game_pitching_splits.bullpen_pitches_thrown': total},
        trace=window.trace('pitch_total_complete'),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _appearances_object(team_id, product_date, window, registry, templates, sync_run_id, source):
    fields = ('game_date', 'mlb_game_pk', 'relievers_used_count', 'split_completeness_status',
              'suspended_resumed_linkage_status')
    citations = _citations_for_window(window, fields)
    unknown = [row for row in window.included_rows if row.relievers_used_count is None]
    known_rows = [row for row in window.included_rows if row.relievers_used_count is not None]
    total = sum(row.relievers_used_count for row in known_rows)
    limitations = [APPEARANCES_NOT_DISTINCT_ARMS_LIMITATION] + _resumed_limitations(window.rows)
    if window.exclusions or unknown:
        reasons = _dedupe(window.reason_codes + ([REASON_SPLIT_ROW_UNKNOWN] if unknown else []))
        claim = (
            f'Relievers were used at least {total} times over the {window.window_days}-day '
            f'window ending {product_date.isoformat()}; '
            f'{len(window.exclusions) + len(unknown)} games excluded because '
            f'{_reason_summary(window.exclusions)}.'
        )
        return _build_object(
            rule_id=APPEARANCES_RULE_ID,
            team_id=team_id,
            product_date=product_date,
            subject_suffix=f'window-{window.window_days}',
            claim=claim,
            cited_inputs=citations,
            input_values={'team_game_pitching_splits.relievers_used_count': _first_value(window.rows, 'relievers_used_count')},
            trace=window.trace('appearance_count_lower_bound_partial'),
            limitations=limitations,
            state=EvidenceObject.COMPLETENESS_PARTIAL,
            reason_codes=reasons or [REASON_SPLIT_ROW_UNKNOWN],
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    claim = (
        f'Relievers were used {total} times over the {window.window_days}-day '
        f'window ending {product_date.isoformat()} across {len(window.included_rows)} final games.'
    )
    return _build_object(
        rule_id=APPEARANCES_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix=f'window-{window.window_days}',
        claim=claim,
        cited_inputs=citations,
        input_values={'team_game_pitching_splits.relievers_used_count': total},
        trace=window.trace('appearance_count_complete'),
        limitations=limitations,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _short_start_object(team_id, product_date, window, registry, templates, sync_run_id, source):
    fields = ('game_date', 'mlb_game_pk', 'starter_identity_status', 'starter_outs_recorded',
              'split_completeness_status', 'suspended_resumed_linkage_status')
    exclusions = list(window.exclusions)
    count = 0
    eligible = []
    for row in window.included_rows:
        if row.starter_identity_status != TeamGamePitchingSplit.STARTER_KNOWN:
            exclusions.append(Exclusion(row, REASON_STARTER_IDENTITY_UNKNOWN, 'starter identity unknown'))
            continue
        if row.starter_outs_recorded is None:
            exclusions.append(Exclusion(row, REASON_STARTER_OUTS_UNKNOWN, 'starter outs unknown'))
            continue
        eligible.append(row)
        if row.starter_outs_recorded <= SHORT_START_MAX_OUTS:
            count += 1
    citations = tuple(
        [_split_citation(row, fields) for row in eligible]
        + [_split_citation(exclusion.row, fields, citation_role='excluded_input') for exclusion in exclusions]
    )
    reasons = _dedupe([exclusion.reason for exclusion in exclusions])
    if exclusions:
        claim = (
            f'At least {count} starts shorter than five innings ({SHORT_START_MAX_OUTS} outs or fewer) '
            f'in team {team_id} games over the {window.window_days}-day window ending '
            f'{product_date.isoformat()}; {len(exclusions)} games excluded: '
            f'{_reason_summary(exclusions)}.'
        )
        state = EvidenceObject.COMPLETENESS_PARTIAL
    else:
        claim = (
            f'{count} starts shorter than five innings ({SHORT_START_MAX_OUTS} outs or fewer) '
            f'in team {team_id} games over the {window.window_days}-day window ending '
            f'{product_date.isoformat()}.'
        )
        state = EvidenceObject.COMPLETENESS_COMPLETE
    return _build_object(
        rule_id=SHORT_START_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix=f'window-{window.window_days}',
        claim=claim,
        cited_inputs=citations,
        input_values={
            'team_game_pitching_splits.starter_identity_status': _first_value(window.rows, 'starter_identity_status'),
            'team_game_pitching_splits.starter_outs_recorded': _first_value(window.rows, 'starter_outs_recorded'),
            'short_start_count': count,
        },
        trace=window.trace('short_start_count', extra={
            'short_start_max_outs': SHORT_START_MAX_OUTS,
            'eligible_games': [_row_ref(row) for row in eligible],
            'exclusions': [_exclusion_payload(item) for item in exclusions],
        }),
        state=state,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _consecutive_object(team_id, product_date, today, registry, templates, sync_run_id, source):
    fields = ('game_date', 'mlb_game_pk', 'consecutive_game_day_count_entering', 'calendar_context_status')
    citations = tuple(_split_citation(row, fields) for row in today.rows)
    reasons = today.calendar_reason_codes
    if reasons:
        claim = (
            f'Consecutive game-day count entering {product_date.isoformat()} '
            f'cannot be stated for team {team_id}; calendar context is not complete.'
        )
        return _build_object(
            rule_id=CONSECUTIVE_RULE_ID,
            team_id=team_id,
            product_date=product_date,
            subject_suffix='evidence-date',
            claim=claim,
            cited_inputs=citations,
            input_values={'team_game_pitching_splits.consecutive_game_day_count_entering': _first_value(today.rows, 'consecutive_game_day_count_entering')},
            trace=today.trace('consecutive_game_days_unknown'),
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=reasons,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    value = today.rows[0].consecutive_game_day_count_entering
    claim = (
        f'Team {team_id} had {value} consecutive game days entering '
        f'{product_date.isoformat()}, from stored calendar context.'
    )
    return _build_object(
        rule_id=CONSECUTIVE_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix='evidence-date',
        claim=claim,
        cited_inputs=citations,
        input_values={'team_game_pitching_splits.consecutive_game_day_count_entering': value},
        trace=today.trace('consecutive_game_days_complete'),
        limitations=_resumed_limitations(today.rows),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _doubleheader_today_object(team_id, product_date, today, registry, templates, sync_run_id, source):
    fields = ('game_date', 'mlb_game_pk', 'doubleheader_flag', 'doubleheader_code', 'game_number', 'calendar_context_status')
    citations = tuple(_split_citation(row, fields) for row in today.rows)
    if today.calendar_reason_codes:
        claim = (
            f'Doubleheader status on {product_date.isoformat()} cannot be stated '
            f'for team {team_id}; calendar context is not complete.'
        )
        return _build_object(
            rule_id=DOUBLEHEADER_TODAY_RULE_ID,
            team_id=team_id,
            product_date=product_date,
            subject_suffix='evidence-date',
            claim=claim,
            cited_inputs=citations,
            input_values={
                'team_game_pitching_splits.doubleheader_flag': _first_value(today.rows, 'doubleheader_flag'),
                'team_game_pitching_splits.game_number': _first_value(today.rows, 'game_number'),
            },
            trace=today.trace('doubleheader_today_unknown'),
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=today.calendar_reason_codes,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    if not _has_doubleheader(today.rows):
        return None
    games = ', '.join(str(row.mlb_game_pk) for row in today.rows)
    claim = (
        f'Team {team_id} played a doubleheader on {product_date.isoformat()} '
        f'(games {games} cited).'
    )
    return _build_object(
        rule_id=DOUBLEHEADER_TODAY_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix='evidence-date',
        claim=claim,
        cited_inputs=citations,
        input_values={
            'team_game_pitching_splits.doubleheader_flag': True,
            'team_game_pitching_splits.game_number': _first_value(today.rows, 'game_number'),
        },
        trace=today.trace('doubleheader_today_complete'),
        limitations=_resumed_limitations(today.rows),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _recent_doubleheader_object(team_id, product_date, window, registry, templates, sync_run_id, source):
    fields = ('game_date', 'mlb_game_pk', 'doubleheader_flag', 'doubleheader_code', 'game_number', 'calendar_context_status')
    citations = _citations_for_window(window, fields)
    calendar_reasons = _calendar_reasons(window.rows)
    if window.exclusions or calendar_reasons:
        reasons = _dedupe(window.reason_codes + calendar_reasons)
        claim = (
            f'Recent doubleheader status cannot be stated for team {team_id} over the '
            f'7-day window ending {product_date.isoformat()}; calendar context is not complete.'
        )
        return _build_object(
            rule_id=RECENT_DOUBLEHEADER_RULE_ID,
            team_id=team_id,
            product_date=product_date,
            subject_suffix='window-7',
            claim=claim,
            cited_inputs=citations,
            input_values={
                'team_game_pitching_splits.doubleheader_flag': _first_value(window.rows, 'doubleheader_flag'),
                'team_game_pitching_splits.game_date': _first_value(window.rows, 'game_date'),
            },
            trace=window.trace('recent_doubleheader_unknown'),
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=reasons or [REASON_CALENDAR_CONTEXT_UNAVAILABLE],
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    doubleheader_days = _doubleheader_days(window.rows)
    if not doubleheader_days:
        return None
    parts = []
    for day, rows in sorted(doubleheader_days.items()):
        games = ', '.join(str(row.mlb_game_pk) for row in rows)
        parts.append(f'{day.isoformat()} games {games}')
    claim = (
        f'Doubleheader within the trailing 7 days for team {team_id}: '
        f'{"; ".join(parts)}.'
    )
    return _build_object(
        rule_id=RECENT_DOUBLEHEADER_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix='window-7',
        claim=claim,
        cited_inputs=citations,
        input_values={
            'team_game_pitching_splits.doubleheader_flag': True,
            'team_game_pitching_splits.game_date': next(iter(doubleheader_days)).isoformat(),
        },
        trace=window.trace('recent_doubleheader_complete', extra={
            'doubleheader_days': {day.isoformat(): [_row_ref(row) for row in rows] for day, rows in doubleheader_days.items()},
        }),
        limitations=_resumed_limitations(window.rows),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _off_day_yesterday_object(team_id, product_date, today, registry, templates, sync_run_id, source):
    fields = ('game_date', 'mlb_game_pk', 'off_day_before', 'calendar_context_status')
    citations = tuple(_split_citation(row, fields) for row in today.rows)
    if today.calendar_reason_codes or any(row.off_day_before is None for row in today.rows):
        reasons = _dedupe(today.calendar_reason_codes or [REASON_CALENDAR_CONTEXT_UNAVAILABLE])
        claim = (
            f'Off-day-before status cannot be stated for team {team_id} on '
            f'{product_date.isoformat()}; calendar context is not complete.'
        )
        return _build_object(
            rule_id=OFF_DAY_YESTERDAY_RULE_ID,
            team_id=team_id,
            product_date=product_date,
            subject_suffix='evidence-date',
            claim=claim,
            cited_inputs=citations,
            input_values={'team_game_pitching_splits.off_day_before': _first_value(today.rows, 'off_day_before')},
            trace=today.trace('off_day_yesterday_unknown'),
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=reasons,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    if not any(row.off_day_before for row in today.rows):
        return None
    prior_day = product_date - timedelta(days=1)
    claim = (
        f'Team {team_id} had no game on {prior_day.isoformat()}, from stored '
        f'off-day-before calendar context for {product_date.isoformat()}.'
    )
    return _build_object(
        rule_id=OFF_DAY_YESTERDAY_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix='evidence-date',
        claim=claim,
        cited_inputs=citations,
        input_values={'team_game_pitching_splits.off_day_before': True},
        trace=today.trace('off_day_yesterday_complete'),
        limitations=_resumed_limitations(today.rows),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _off_day_tomorrow_object(team_id, product_date, today, registry, templates, sync_run_id, source):
    fields = ('game_date', 'mlb_game_pk', 'off_day_after', 'calendar_context_status')
    citations = tuple(_split_citation(row, fields) for row in today.rows)
    limitations = [SCHEDULE_SUBJECT_TO_CHANGE_LIMITATION] + _resumed_limitations(today.rows)
    if today.calendar_reason_codes or any(row.off_day_after is None for row in today.rows):
        reasons = _dedupe(today.calendar_reason_codes or [REASON_CALENDAR_CONTEXT_UNAVAILABLE])
        claim = (
            f'Next-day schedule status cannot be stated for team {team_id} after '
            f'{product_date.isoformat()}; calendar context is not complete.'
        )
        return _build_object(
            rule_id=OFF_DAY_TOMORROW_RULE_ID,
            team_id=team_id,
            product_date=product_date,
            subject_suffix='evidence-date',
            claim=claim,
            cited_inputs=citations,
            input_values={'team_game_pitching_splits.off_day_after': _first_value(today.rows, 'off_day_after')},
            trace=today.trace('off_day_tomorrow_unknown'),
            limitations=limitations,
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=reasons,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    if not any(row.off_day_after for row in today.rows):
        return None
    next_day = product_date + timedelta(days=1)
    claim = (
        f'No game appears on the team {team_id} schedule for {next_day.isoformat()} '
        'as of the last schedule ingestion.'
    )
    return _build_object(
        rule_id=OFF_DAY_TOMORROW_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix='evidence-date',
        claim=claim,
        cited_inputs=citations,
        input_values={'team_game_pitching_splits.off_day_after': True},
        trace=today.trace('off_day_tomorrow_complete'),
        limitations=limitations,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _density_object(team_id, product_date, window, registry, templates, sync_run_id, source):
    fields = ('game_date', 'mlb_game_pk', 'doubleheader_flag', 'calendar_context_status',
              'consecutive_game_day_count_entering')
    citations = _citations_for_window(window, fields)
    calendar_reasons = _calendar_reasons(window.rows)
    if calendar_reasons:
        claim = (
            f'Calendar density cannot be stated for team {team_id} over the '
            f'7-day window ending {product_date.isoformat()}; calendar context is not complete.'
        )
        return _build_object(
            rule_id=DENSITY_RULE_ID,
            team_id=team_id,
            product_date=product_date,
            subject_suffix='window-7',
            claim=claim,
            cited_inputs=citations,
            input_values={
                'team_game_pitching_splits.game_date': _first_value(window.rows, 'game_date'),
                'team_game_pitching_splits.doubleheader_flag': _first_value(window.rows, 'doubleheader_flag'),
                'team_game_pitching_splits.consecutive_game_day_count_entering': _first_value(window.rows, 'consecutive_game_day_count_entering'),
            },
            trace=window.trace('density_unknown'),
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=calendar_reasons,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
    game_days = {row.game_date for row in window.rows}
    doubleheader_days = _doubleheader_days(window.rows)
    off_days = window.window_days - len(game_days)
    current_day_rows = [row for row in window.rows if row.game_date == product_date]
    streak = (
        current_day_rows[0].consecutive_game_day_count_entering
        if current_day_rows
        else None
    )
    claim = (
        f'Calendar density for team {team_id} over the trailing 7-day window ending '
        f'{product_date.isoformat()}: {len(window.rows)} final games, '
        f'{len(game_days)} distinct game days, {off_days} off days, '
        f'{len(doubleheader_days)} doubleheader days, consecutive game-day count '
        f'entering the evidence date {streak}.'
    )
    return _build_object(
        rule_id=DENSITY_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix='window-7',
        claim=claim,
        cited_inputs=citations,
        input_values={
            'team_game_pitching_splits.game_date': _first_value(window.rows, 'game_date'),
            'team_game_pitching_splits.doubleheader_flag': _first_value(window.rows, 'doubleheader_flag'),
            'team_game_pitching_splits.consecutive_game_day_count_entering': streak,
        },
        trace=window.trace('density_complete', extra={
            'final_games_played': len(window.rows),
            'distinct_game_days': len(game_days),
            'off_days': off_days,
            'doubleheader_days': [day.isoformat() for day in sorted(doubleheader_days)],
            'consecutive_game_day_count_entering': streak,
            'components_independently_degradable': True,
        }),
        limitations=_resumed_limitations(window.rows),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


class _WindowAnalysis:
    def __init__(self, rows, product_date, window_days):
        self.rows = list(rows or [])
        self.product_date = product_date
        self.window_days = window_days
        self.start = product_date - timedelta(days=window_days - 1)
        self.exclusions = []
        self.included_rows = []
        for row in self.rows:
            exclusion = _row_exclusion(row)
            if exclusion:
                self.exclusions.append(exclusion)
            else:
                self.included_rows.append(row)
        self.reason_codes = _dedupe([item.reason for item in self.exclusions])
        self.complete_row_count = len(self.included_rows)

    def trace(self, decision, extra=None):
        payload = {
            'steps': [
                'Read team_game_pitching_splits rows in the team-scoped product-day window.',
                'Separated complete included rows from excluded rows.',
                'Applied count-versus-ratio degradation grammar.',
            ],
            'window_days': self.window_days,
            'window_start': self.start.isoformat(),
            'window_end': self.product_date.isoformat(),
            'rows_consulted': [_row_ref(row) for row in self.rows],
            'included_rows': [_row_ref(row) for row in self.included_rows],
            'exclusions': [_exclusion_payload(item) for item in self.exclusions],
            'reason_codes': self.reason_codes,
            'decision': decision,
            'missing_expected_game_detection': 'not_supportable_without_existing_team_scoped_helper',
            'team_scoped_window_validity': True,
        }
        payload.update(extra or {})
        return payload


class _CalendarAnalysis:
    def __init__(self, rows):
        self.rows = list(rows or [])
        self.calendar_reason_codes = _calendar_reasons(self.rows)

    def trace(self, decision):
        return {
            'steps': [
                'Read calendar context fields from evidence-date team split rows.',
                'Used stored calendar context directly without local schedule recomputation.',
            ],
            'rows_consulted': [_row_ref(row) for row in self.rows],
            'calendar_field_reads': [
                {
                    'mlb_game_pk': row.mlb_game_pk,
                    'off_day_before': row.off_day_before,
                    'off_day_after': row.off_day_after,
                    'consecutive_game_day_count_entering': row.consecutive_game_day_count_entering,
                    'doubleheader_flag': row.doubleheader_flag,
                    'doubleheader_code': row.doubleheader_code,
                    'game_number': row.game_number,
                    'calendar_context_status': row.calendar_context_status,
                }
                for row in self.rows
            ],
            'reason_codes': self.calendar_reason_codes,
            'decision': decision,
        }


def _analyze_window(rows, product_date, window_days):
    return _WindowAnalysis(rows, product_date, window_days)


def _analyze_calendar_rows(rows):
    return _CalendarAnalysis(rows)


def _row_exclusion(row):
    if row.suspended_resumed_linkage_status == TeamGamePitchingSplit.LINKAGE_AMBIGUOUS:
        return Exclusion(row, REASON_AMBIGUOUS_RESUMED_GAME, 'ambiguous suspended/resumed linkage')
    if row.split_completeness_status == TeamGamePitchingSplit.STATUS_PARTIAL:
        return Exclusion(row, REASON_SPLIT_ROW_PARTIAL, 'split row partial')
    if row.split_completeness_status == TeamGamePitchingSplit.STATUS_UNKNOWN:
        return Exclusion(row, REASON_SPLIT_ROW_UNKNOWN, 'split row unknown')
    return None


def _calendar_reasons(rows):
    reasons = []
    for row in rows:
        if row.calendar_context_status == TeamGamePitchingSplit.STATUS_UNKNOWN:
            reasons.append(REASON_CALENDAR_CONTEXT_UNAVAILABLE)
        elif row.calendar_context_status == TeamGamePitchingSplit.STATUS_PARTIAL:
            reasons.append(REASON_CALENDAR_CONTEXT_STALE)
        if row.suspended_resumed_linkage_status == TeamGamePitchingSplit.LINKAGE_AMBIGUOUS:
            reasons.append(REASON_AMBIGUOUS_RESUMED_GAME)
    return _dedupe(reasons)


def _window_rows(rows, product_date, window_days):
    start = product_date - timedelta(days=window_days - 1)
    return [row for row in rows if start <= row.game_date <= product_date]


def _citations_for_window(window, fields):
    return tuple(
        [_split_citation(row, fields) for row in window.included_rows]
        + [_split_citation(exclusion.row, fields, citation_role='excluded_input') for exclusion in window.exclusions]
    )


def _split_citation(row, fields, *, citation_role='supporting_input'):
    return EvidenceCitationInput(
        source_family='team_game_pitching_splits',
        source_table='team_game_pitching_splits',
        source_pk=row.id,
        source_field_names=tuple(fields),
        citation_role=citation_role,
        cited_values={field: _citation_value(getattr(row, field, None)) for field in fields},
        provenance={
            'source': row.source,
            'sync_run_id': row.sync_run_id,
            'correction_count': row.correction_count or 0,
            'last_corrected_at': _iso(row.last_corrected_at),
            'correction_source': row.correction_source,
            'last_derived_at': _iso(row.last_derived_at),
        },
    )


def _build_object(
    *,
    rule_id,
    team_id,
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
    limitations=None,
    state=EvidenceObject.COMPLETENESS_COMPLETE,
    reason_codes=None,
):
    _assert_text_has_no_starter_exposure_forbidden_terms(claim)
    rule = registry.get(rule_id, RULE_VERSION)
    template = templates.get(_template_id(rule_id), RULE_VERSION)
    evidence = build_evidence_object(
        rule_id=rule.rule_id,
        rule_version=RULE_VERSION,
        claim_template=template,
        claim_values={'claim': claim},
        subject_type=SUBJECT_TYPE,
        subject_id=team_id,
        subject_key=f'team:{team_id}:{product_date.isoformat()}:{subject_suffix}:{rule_id}',
        product_date=product_date,
        cited_inputs=tuple(cited_inputs),
        computation_trace=trace,
        input_values=dict(input_values or {}),
        readiness_payload=_readiness_payload(rule.required_input_families),
        limitations=tuple(limitations or ()),
        registry=registry,
        sync_run_id=sync_run_id,
        source=EVIDENCE_SOURCE,
    )
    if state != EvidenceObject.COMPLETENESS_COMPLETE or reason_codes:
        evidence.completeness_state = state
        evidence.reason_codes = _dedupe(reason_codes or [])
        evidence.rendered_claim = claim
    return BuiltStarterExposureEvidence(
        evidence=evidence,
        rule_id=rule_id,
        subject_key=evidence.subject_key,
    )


def _readiness_payload(required_families):
    return {
        'families': {
            family: {'status': SOURCE_READY, 'reason_codes': []}
            for family in required_families
        }
    }


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


def _sum_known(rows, field_name):
    return sum(getattr(row, field_name) for row in rows if getattr(row, field_name) is not None)


def _first_value(rows, field_name):
    for row in rows:
        value = getattr(row, field_name, None)
        if value is not None:
            return _citation_value(value)
    return None


def _has_doubleheader(rows):
    if len({row.mlb_game_pk for row in rows}) >= 2 and len({row.game_date for row in rows}) == 1:
        return True
    return any(bool(row.doubleheader_flag) for row in rows)


def _doubleheader_days(rows):
    by_day = defaultdict(list)
    for row in rows:
        by_day[row.game_date].append(row)
    return {
        day: day_rows
        for day, day_rows in by_day.items()
        if len({row.mlb_game_pk for row in day_rows}) >= 2 or any(row.doubleheader_flag for row in day_rows)
    }


def _reason_summary(exclusions):
    if not exclusions:
        return 'none'
    counts = defaultdict(int)
    for exclusion in exclusions:
        counts[exclusion.detail] += 1
    return ', '.join(f'{count} {detail}' for detail, count in sorted(counts.items()))


def _row_ref(row):
    return {
        'id': row.id,
        'team_id': row.team_id,
        'mlb_game_pk': row.mlb_game_pk,
        'game_date': row.game_date.isoformat() if row.game_date else None,
        'split_completeness_status': row.split_completeness_status,
        'calendar_context_status': row.calendar_context_status,
    }


def _exclusion_payload(exclusion):
    payload = _row_ref(exclusion.row)
    payload.update({'reason': exclusion.reason, 'detail': exclusion.detail})
    return payload


def _resumed_limitations(rows):
    if any(row.suspended_resumed_linkage_status == TeamGamePitchingSplit.LINKAGE_RESOLVED for row in rows):
        return [RESUMED_GAME_LIMITATION]
    return []


def _citation_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _template_id(rule_id):
    return f'{rule_id}_claim'


def _iso(value):
    return value.isoformat() if value is not None else None


def _dedupe(values):
    result = []
    seen = set()
    for value in values or []:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
