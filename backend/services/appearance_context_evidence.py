"""Internal Phase 0D appearance entry and exit context evidence family."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
import re

from sqlalchemy import asc

from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.play_by_play_foundation import GamePlayByPlayEvent, PlayByPlayProcessedGame
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
EVIDENCE_TYPE = 'appearance_context_fact'
EVIDENCE_SOURCE = 'phase0d:appearance_context_evidence'
REQUIRED_INPUT_FAMILIES = ('final_play_by_play', 'game_logs')
SUBJECT_TYPE = 'pitcher_appearance'
RECONCILIATION_ENTITY_TYPE = 'appearance_context_reconciliation'

PLAY_GRANULARITY_LIMITATION = (
    'Entry and exit boundaries are play-granular; a mid-at-bat change resolves '
    'to the pitcher credited with the completed play.'
)
BASE_STATE_LIMITATION = (
    'Runners on base at entry are not available from stored play-by-play; '
    'entry traffic is unknown here. Inherited-runner facts, where recorded, '
    'come from the boxscore-backed game log.'
)
RESUMED_GAME_LIMITATION = 'game was suspended and resumed; events may span calendar dates'

REASON_PBP_MARKER_NOT_FULLY_PROCESSED = 'pbp_marker_not_fully_processed'
REASON_PRECEDING_EVENT_OUTS_UNKNOWN = 'preceding_event_outs_unknown'
REASON_EXIT_OUTS_UNKNOWN = 'exit_outs_unknown'
REASON_APPEARANCE_ROLE_UNKNOWN = 'appearance_role_unknown'
REASON_ENTRY_FLAG_MISSING = 'entry_flag_missing'
REASON_PBP_APPEARANCE_MISSING = 'pbp_appearance_missing'
REASON_GAME_LOG_ROW_MISSING = 'game_log_row_missing'
REASON_NON_CONTIGUOUS_PITCHER_SPAN = 'non_contiguous_pitcher_span'
REASON_ORDER_INCONSISTENT = 'order_inconsistent'
REASON_OUTS_IMPLAUSIBLE = 'outs_implausible'
REASON_BASE_STATE_UNAVAILABLE = 'base_state_unavailable'
REASON_RESUMED_GAME_SPANS_DATES = 'resumed_game_spans_dates'
REASON_GAME_LOG_CORRECTED = 'game_log_corrected'
REASON_PBP_EVENT_CORRECTED = 'pbp_event_corrected'

ENTRY_RULE_ID = 'appearance_entry_context'
EXIT_RULE_ID = 'appearance_exit_context'
ORDER_RULE_ID = 'appearance_order_in_game'
INNINGS_RULE_ID = 'appearance_innings_spanned'
PHASE_RULE_ID = 'appearance_game_phase'
RECONCILIATION_RULE_ID = 'appearance_pbp_reconciliation'
BASE_STATE_RULE_ID = 'appearance_entry_base_state'

APPEARANCE_RULE_IDS = (
    ENTRY_RULE_ID,
    EXIT_RULE_ID,
    ORDER_RULE_ID,
    INNINGS_RULE_ID,
    PHASE_RULE_ID,
    RECONCILIATION_RULE_ID,
    BASE_STATE_RULE_ID,
)

_NO_PARTIAL_COMPLETENESS = (
    EvidenceObject.COMPLETENESS_COMPLETE,
    EvidenceObject.COMPLETENESS_UNKNOWN,
    EvidenceObject.COMPLETENESS_CONFLICT,
    EvidenceObject.COMPLETENESS_WITHHELD,
)

_RULE_DEFINITIONS = {
    ENTRY_RULE_ID: (
        'For a relief appearance in a fully processed final game: the inning '
        "and half-inning of the pitcher's first stored play-by-play event, the "
        "outs at entry from the preceding same-half event's post-play outs or "
        'zero at a half-inning start, and the margin at entry from the '
        "pitcher's team's perspective. Runners on base at entry are not stored "
        'and are always UNKNOWN.'
    ),
    EXIT_RULE_ID: (
        "For the same appearance: the inning and half-inning of the pitcher's "
        'last stored event, the post-play outs at that final event, and the '
        'exit boundary type.'
    ),
    ORDER_RULE_ID: (
        "The pitcher's position in his team's pitching sequence for the game, "
        'based on the rank of his entry event index among distinct pitchers for '
        'that fielding team.'
    ),
    INNINGS_RULE_ID: (
        'The count of distinct innings the appearance touched: exit inning '
        '- entry inning + 1. This is a span of innings touched, not outs '
        'recorded.'
    ),
    PHASE_RULE_ID: (
        'A descriptive tag for the entry inning: early is innings 1-3, middle '
        'is innings 4-6, late is innings 7-9, and extras is inning 10 or later. '
        'The tag carries no importance meaning.'
    ),
    RECONCILIATION_RULE_ID: (
        "Agreement state between the appearance's play-by-play span and stored "
        'game-log row. Matched requires the pitcher in both sources, a '
        'contiguous span, consistent team ordering, plausible stored outs for '
        'the span, and positionally consistent entry/exit outs when known.'
    ),
    BASE_STATE_RULE_ID: (
        'Runners on base when the pitcher entered. Stored final play-by-play '
        'events do not carry base-runner state, so this evidence is UNKNOWN '
        'for every appearance by design.'
    ),
}

_RULE_THRESHOLDS = {
    PHASE_RULE_ID: {
        'early_max': 3,
        'middle_max': 6,
        'late_max': 9,
    },
}

_REQUIRED_FIELDS = {
    ENTRY_RULE_ID: ('final_play_by_play.mlb_game_pk', 'game_logs.games_started'),
    EXIT_RULE_ID: ('final_play_by_play.mlb_game_pk', 'game_logs.games_started'),
    ORDER_RULE_ID: ('final_play_by_play.mlb_game_pk', 'game_logs.games_started'),
    INNINGS_RULE_ID: ('final_play_by_play.mlb_game_pk', 'game_logs.games_started'),
    PHASE_RULE_ID: ('final_play_by_play.mlb_game_pk', 'game_logs.games_started'),
    RECONCILIATION_RULE_ID: ('final_play_by_play.mlb_game_pk',),
    BASE_STATE_RULE_ID: ('final_play_by_play.mlb_game_pk', 'game_logs.games_started'),
}

_FORBIDDEN_APPEARANCE_CLAIM_TERMS = (
    'availability',
    'available',
    'fatigue',
    'fatigued',
    'leverage',
    'pressure',
    'prediction',
    'predict',
    'usage pattern',
)


@dataclass(frozen=True)
class BuiltAppearanceEvidence:
    evidence: EvidenceObject
    rule_id: str
    subject_key: str


@dataclass
class PitchingSegment:
    team_id: int
    pitcher_mlb_id: int
    order: int
    entry_event: GamePlayByPlayEvent
    exit_event: GamePlayByPlayEvent
    events: list[GamePlayByPlayEvent]


_LOCAL_RULE_REGISTRY: EvidenceRuleRegistry | None = None
_LOCAL_TEMPLATE_REGISTRY: ClaimTemplateRegistry | None = None


def appearance_rule_definitions() -> dict[str, str]:
    return dict(_RULE_DEFINITIONS)


def appearance_rule_ids() -> tuple[str, ...]:
    return APPEARANCE_RULE_IDS


def register_appearance_context_rules(
    *,
    registry: EvidenceRuleRegistry | None = None,
    template_registry: ClaimTemplateRegistry | None = None,
) -> tuple[EvidenceRuleRegistry, ClaimTemplateRegistry]:
    rule_registry = registry or EvidenceRuleRegistry()
    claim_registry = template_registry or ClaimTemplateRegistry()
    for rule_id in APPEARANCE_RULE_IDS:
        _register_appearance_rule(rule_registry, _appearance_rule(rule_id))
        _register_appearance_template(
            claim_registry,
            ClaimTemplate(
                template_id=_template_id(rule_id),
                template_version=RULE_VERSION,
                template_text='{claim}',
            ),
        )
    return rule_registry, claim_registry


def build_appearance_context_evidence(
    product_date,
    *,
    sync_run_id=None,
    source='manual',
    commit=False,
    restrict_evidence_keys: set[str] | None = None,
) -> dict:
    """Build internal appearance context evidence for one product date."""
    ref = _as_date(product_date)
    registry, templates = _local_registries()
    markers = _markers_for_date(ref)
    emitted = []
    skipped = defaultdict(int)

    for marker in markers:
        if marker.processing_status != PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED:
            skipped[marker.processing_status or REASON_PBP_MARKER_NOT_FULLY_PROCESSED] += 1
            continue
        game_result = _build_for_game(
            marker=marker,
            product_date=ref,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
        for item in game_result:
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
        'rules': list(APPEARANCE_RULE_IDS),
        'games_considered': len(markers),
        'games_skipped': dict(skipped),
        'objects_built': len(emitted),
        'objects_created': sum(1 for item in emitted if item == 'created'),
        'objects_refreshed': sum(1 for item in emitted if item == 'refreshed'),
    }


def mark_game_log_correction_for_appearance_context(
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


def mark_pbp_event_correction_for_appearance_context(
    event,
    *,
    sync_run_id=None,
    reason_code=REASON_PBP_EVENT_CORRECTED,
    batch_size=100,
) -> dict:
    if event is None or getattr(event, 'id', None) is None:
        return {'marked_count': 0, 'evidence_ids': []}
    return mark_dependent_evidence_for_recompute(
        source_table='game_play_by_play_events',
        source_pk=event.id,
        reason_code=reason_code,
        batch_size=batch_size,
        sync_run_id=sync_run_id,
    )


def rebuild_marked_appearance_context_evidence(
    *,
    sync_run_id=None,
    source='manual',
    batch_size=100,
) -> dict:
    rows = (
        EvidenceObject.query
        .filter(EvidenceObject.rule_id.in_(APPEARANCE_RULE_IDS))
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
        result = build_appearance_context_evidence(
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
        _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY = register_appearance_context_rules()
    return _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY


def _appearance_rule(rule_id):
    allowed = (
        (EvidenceObject.COMPLETENESS_UNKNOWN,)
        if rule_id == BASE_STATE_RULE_ID
        else _NO_PARTIAL_COMPLETENESS
    )
    return EvidenceRule(
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        evidence_type=EVIDENCE_TYPE,
        plain_language_definition=_RULE_DEFINITIONS[rule_id],
        required_input_families=REQUIRED_INPUT_FAMILIES,
        required_cited_fields=_REQUIRED_FIELDS[rule_id],
        allowed_completeness=allowed,
        posture_default=EvidenceObject.POSTURE_INTERNAL_ONLY,
        thresholds=_RULE_THRESHOLDS.get(rule_id, {}),
    )


def _register_appearance_rule(registry, rule):
    if rule.posture_default != EvidenceObject.POSTURE_INTERNAL_ONLY:
        raise EvidenceRuleError('appearance context evidence must remain internal_only')
    return registry.register(rule)


def _register_appearance_template(registry, template):
    _assert_text_has_no_appearance_forbidden_terms(template.template_text)
    return registry.register(template)


def _assert_text_has_no_appearance_forbidden_terms(text):
    lowered = f' {text or ""} '.lower()
    for term in _FORBIDDEN_APPEARANCE_CLAIM_TERMS:
        pattern = r'\b' + re.escape(term).replace(r'\ ', r'\s+') + r'\b'
        if re.search(pattern, lowered):
            raise EvidenceLanguageError(
                f'appearance claim language uses forbidden term: {term}'
            )
    return True


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _markers_for_date(product_date):
    return (
        PlayByPlayProcessedGame.query
        .filter(PlayByPlayProcessedGame.game_date == product_date)
        .order_by(asc(PlayByPlayProcessedGame.mlb_game_pk), asc(PlayByPlayProcessedGame.id))
        .all()
    )


def _build_for_game(
    *,
    marker,
    product_date,
    registry,
    templates,
    sync_run_id,
    source,
):
    events = _game_events(marker.mlb_game_pk)
    logs = _game_logs(marker.mlb_game_pk)
    logs_by_mlb_id = _logs_by_mlb_id(logs)
    segments_by_key, segments_by_team, non_contiguous = _pitching_segments(events)
    order_inconsistent_teams = _order_inconsistent_teams(segments_by_team, logs)
    resumed = _is_resumed_game(marker.mlb_game_pk)
    built = []

    for log in logs:
        pitcher = getattr(log, 'pitcher', None) or db.session.get(Pitcher, log.pitcher_id)
        pitcher_mlb_id = getattr(pitcher, 'mlb_id', None)
        if pitcher_mlb_id is None:
            continue
        segment = _segment_for_log(log, pitcher_mlb_id, segments_by_key)
        if log.games_started == 1:
            continue
        if log.games_started is None:
            built.append(_role_unknown_reconciliation(
                marker=marker,
                log=log,
                pitcher=pitcher,
                segment=segment,
                product_date=product_date,
                registry=registry,
                templates=templates,
                sync_run_id=sync_run_id,
                source=source,
                resumed=resumed,
            ))
            continue
        if segment is None:
            built.append(_pbp_missing_reconciliation(
                marker=marker,
                log=log,
                pitcher=pitcher,
                product_date=product_date,
                registry=registry,
                templates=templates,
                sync_run_id=sync_run_id,
                source=source,
                resumed=resumed,
            ))
            continue

        context = _appearance_context(
            marker=marker,
            log=log,
            pitcher=pitcher,
            segment=segment,
            events=events,
            segments_by_team=segments_by_team,
            non_contiguous=non_contiguous,
            order_inconsistent_teams=order_inconsistent_teams,
            resumed=resumed,
        )
        if context['reconciliation_state'] == 'matched':
            built.extend(_matched_objects(
                marker=marker,
                log=log,
                pitcher=pitcher,
                segment=segment,
                context=context,
                product_date=product_date,
                registry=registry,
                templates=templates,
                sync_run_id=sync_run_id,
                source=source,
            ))
        else:
            built.append(_conflict_reconciliation(
                marker=marker,
                log=log,
                pitcher=pitcher,
                segment=segment,
                context=context,
                product_date=product_date,
                registry=registry,
                templates=templates,
                sync_run_id=sync_run_id,
                source=source,
            ))
            _record_reconciliation_dead_letter(
                reason_code=context['reconciliation_reason'],
                marker=marker,
                pitcher=pitcher,
                log=log,
                segment=segment,
                sync_run_id=sync_run_id,
            )

    for key, segment in segments_by_key.items():
        if key[1] in logs_by_mlb_id:
            continue
        pitcher = Pitcher.query.filter_by(mlb_id=segment.pitcher_mlb_id).first()
        if pitcher is None:
            _record_reconciliation_dead_letter(
                reason_code=REASON_GAME_LOG_ROW_MISSING,
                marker=marker,
                pitcher=None,
                log=None,
                segment=segment,
                sync_run_id=sync_run_id,
                extra={'identity_guard': 'internal_pitcher_not_found'},
            )
            continue
        context = _missing_game_log_context(
            marker=marker,
            pitcher=pitcher,
            segment=segment,
            resumed=resumed,
        )
        built.append(_conflict_reconciliation(
            marker=marker,
            log=None,
            pitcher=pitcher,
            segment=segment,
            context=context,
            product_date=product_date,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        ))
        _record_reconciliation_dead_letter(
            reason_code=REASON_GAME_LOG_ROW_MISSING,
            marker=marker,
            pitcher=pitcher,
            log=None,
            segment=segment,
            sync_run_id=sync_run_id,
        )

    return [item for item in built if item is not None]


def _game_events(game_pk):
    return (
        GamePlayByPlayEvent.query
        .filter(GamePlayByPlayEvent.mlb_game_pk == game_pk)
        .order_by(asc(GamePlayByPlayEvent.event_index), asc(GamePlayByPlayEvent.id))
        .all()
    )


def _game_logs(game_pk):
    return (
        GameLog.query
        .filter(GameLog.mlb_game_pk == game_pk)
        .order_by(asc(GameLog.id))
        .all()
    )


def _logs_by_mlb_id(logs):
    by_mlb_id = defaultdict(list)
    for log in logs:
        pitcher = getattr(log, 'pitcher', None) or db.session.get(Pitcher, log.pitcher_id)
        if pitcher is not None and pitcher.mlb_id is not None:
            by_mlb_id[pitcher.mlb_id].append(log)
    return by_mlb_id


def _pitching_segments(events):
    by_team = defaultdict(list)
    for event in events:
        if event.fielding_team_id is not None and event.pitcher_mlb_id is not None:
            by_team[event.fielding_team_id].append(event)

    segments_by_key = {}
    segments_by_team = {}
    non_contiguous = set()
    for team_id, team_events in by_team.items():
        segments = []
        current = None
        closed_pitchers = set()
        for event in sorted(team_events, key=lambda item: (item.event_index, item.id)):
            if current is None or current.pitcher_mlb_id != event.pitcher_mlb_id:
                if current is not None:
                    closed_pitchers.add(current.pitcher_mlb_id)
                if event.pitcher_mlb_id in closed_pitchers:
                    non_contiguous.add((team_id, event.pitcher_mlb_id))
                current = PitchingSegment(
                    team_id=team_id,
                    pitcher_mlb_id=event.pitcher_mlb_id,
                    order=len(segments) + 1,
                    entry_event=event,
                    exit_event=event,
                    events=[event],
                )
                segments.append(current)
            else:
                current.events.append(event)
                current.exit_event = event
        segments_by_team[team_id] = segments
        grouped = defaultdict(list)
        for segment in segments:
            grouped[segment.pitcher_mlb_id].append(segment)
        for pitcher_mlb_id, pitcher_segments in grouped.items():
            if len(pitcher_segments) > 1:
                non_contiguous.add((team_id, pitcher_mlb_id))
            segments_by_key[(team_id, pitcher_mlb_id)] = pitcher_segments[0]
    return segments_by_key, segments_by_team, non_contiguous


def _order_inconsistent_teams(segments_by_team, logs):
    starters_by_team = defaultdict(list)
    for log in logs:
        if log.games_started != 1:
            continue
        pitcher = getattr(log, 'pitcher', None) or db.session.get(Pitcher, log.pitcher_id)
        team_id = getattr(pitcher, 'team_id', None)
        if team_id is not None:
            starters_by_team[team_id].append(pitcher.mlb_id)

    inconsistent = set()
    for team_id, segments in segments_by_team.items():
        if not segments:
            continue
        starter_ids = starters_by_team.get(team_id) or []
        if len(starter_ids) != 1:
            inconsistent.add(team_id)
            continue
        if segments[0].pitcher_mlb_id != starter_ids[0]:
            inconsistent.add(team_id)
            continue
        entry_indexes = [segment.entry_event.event_index for segment in segments]
        if entry_indexes != sorted(entry_indexes) or len(entry_indexes) != len(set(entry_indexes)):
            inconsistent.add(team_id)
    return inconsistent


def _segment_for_log(log, pitcher_mlb_id, segments_by_key):
    candidates = [
        segment
        for (team_id, segment_pitcher_mlb_id), segment in segments_by_key.items()
        if segment_pitcher_mlb_id == pitcher_mlb_id
    ]
    if not candidates:
        return None
    pitcher = getattr(log, 'pitcher', None) or db.session.get(Pitcher, log.pitcher_id)
    team_id = getattr(pitcher, 'team_id', None)
    if team_id is not None:
        for segment in candidates:
            if segment.team_id == team_id:
                return segment
    return sorted(candidates, key=lambda item: item.entry_event.event_index)[0]


def _appearance_context(
    *,
    marker,
    log,
    pitcher,
    segment,
    events,
    segments_by_team,
    non_contiguous,
    order_inconsistent_teams,
    resumed,
):
    entry = _entry_state(segment, events)
    exit_state = _exit_state(segment, segments_by_team)
    innings_spanned = _innings_spanned(segment)
    phase = _game_phase(segment.entry_event.inning)
    reasons = []
    state = 'matched'

    if (segment.team_id, segment.pitcher_mlb_id) in non_contiguous:
        reasons.append(REASON_NON_CONTIGUOUS_PITCHER_SPAN)
        state = 'conflict'
    if segment.team_id in order_inconsistent_teams:
        reasons.append(REASON_ORDER_INCONSISTENT)
        state = 'conflict'
    if _outs_implausible(log, entry, exit_state, innings_spanned):
        reasons.append(REASON_OUTS_IMPLAUSIBLE)
        state = 'conflict'

    if resumed:
        reasons.append(REASON_RESUMED_GAME_SPANS_DATES)

    reconciliation_reason = next(
        (reason for reason in reasons if reason != REASON_RESUMED_GAME_SPANS_DATES),
        'matched',
    )
    return {
        'marker': marker,
        'pitcher_id': pitcher.id,
        'pitcher_mlb_id': pitcher.mlb_id,
        'entry': entry,
        'exit': exit_state,
        'order': segment.order,
        'innings_spanned': innings_spanned,
        'phase': phase,
        'team_segments': list(segments_by_team.get(segment.team_id) or []),
        'reasons': _dedupe(reasons),
        'reconciliation_state': state,
        'reconciliation_reason': reconciliation_reason,
        'limitations': _limitations(resumed=resumed),
        'resumed': resumed,
    }


def _missing_game_log_context(*, marker, pitcher, segment, resumed):
    return {
        'marker': marker,
        'pitcher_id': pitcher.id,
        'pitcher_mlb_id': pitcher.mlb_id,
        'entry': _entry_state(segment, _game_events(marker.mlb_game_pk)),
        'exit': _exit_state(segment, {segment.team_id: [segment]}),
        'order': segment.order,
        'innings_spanned': _innings_spanned(segment),
        'phase': _game_phase(segment.entry_event.inning),
        'team_segments': [segment],
        'reasons': _dedupe([
            REASON_GAME_LOG_ROW_MISSING,
            *( [REASON_RESUMED_GAME_SPANS_DATES] if resumed else [] ),
        ]),
        'reconciliation_state': 'conflict',
        'reconciliation_reason': REASON_GAME_LOG_ROW_MISSING,
        'limitations': _limitations(resumed=resumed),
        'resumed': resumed,
    }


def _entry_state(segment, events):
    entry_event = segment.entry_event
    prior_same_half = _previous_same_half_event(entry_event, events)
    prior_event = _previous_event(entry_event, events)
    if prior_same_half is None:
        outs_at_entry = 0
        half_start = True
        outs_reason = None
    else:
        outs_at_entry = prior_same_half.outs_at_event
        half_start = False
        outs_reason = (
            REASON_PRECEDING_EVENT_OUTS_UNKNOWN
            if outs_at_entry is None
            else None
        )

    if prior_event is None:
        home = 0
        away = 0
    else:
        home = prior_event.home_score_at_event
        away = prior_event.away_score_at_event

    fielding_score, batting_score, margin = _margin(entry_event, home, away)
    mid_inning = bool((outs_at_entry or 0) > 0 or not half_start)
    entry_flag_missing = (
        segment.order > 1
        and not half_start
        and not bool(entry_event.is_pitching_change)
    )
    return {
        'event': entry_event,
        'prior_same_half_event': prior_same_half,
        'prior_event': prior_event,
        'outs_at_entry': outs_at_entry,
        'half_start': half_start,
        'home_score': home,
        'away_score': away,
        'fielding_score': fielding_score,
        'batting_score': batting_score,
        'margin': margin,
        'mid_inning': mid_inning,
        'entry_flag_missing': entry_flag_missing,
        'outs_reason': outs_reason,
    }


def _exit_state(segment, segments_by_team):
    exit_event = segment.exit_event
    next_segment = _next_segment(segment, segments_by_team.get(segment.team_id) or [])
    if next_segment is None:
        boundary = 'finished_game'
        removed_mid_inning = False
    else:
        boundary = 'relieved'
        next_event = next_segment.entry_event
        removed_mid_inning = (
            next_event.inning == exit_event.inning
            and next_event.half_inning == exit_event.half_inning
        )
    return {
        'event': exit_event,
        'next_segment': next_segment,
        'outs_at_exit': exit_event.outs_at_event,
        'boundary_type': boundary,
        'removed_mid_inning': bool(removed_mid_inning),
        'outs_reason': REASON_EXIT_OUTS_UNKNOWN if exit_event.outs_at_event is None else None,
    }


def _previous_same_half_event(entry_event, events):
    same_half = [
        event
        for event in events
        if event.event_index < entry_event.event_index
        and event.inning == entry_event.inning
        and event.half_inning == entry_event.half_inning
    ]
    return same_half[-1] if same_half else None


def _previous_event(entry_event, events):
    prior = [event for event in events if event.event_index < entry_event.event_index]
    return prior[-1] if prior else None


def _next_segment(segment, segments):
    for candidate in segments:
        if candidate.order == segment.order + 1:
            return candidate
    return None


def _margin(event, home_score, away_score):
    if home_score is None or away_score is None:
        return None, None, None
    if event.fielding_team_id == event.home_team_id:
        return home_score, away_score, home_score - away_score
    if event.fielding_team_id == event.away_team_id:
        return away_score, home_score, away_score - home_score
    return None, None, None


def _innings_spanned(segment):
    entry_inning = segment.entry_event.inning
    exit_inning = segment.exit_event.inning
    if entry_inning is None or exit_inning is None:
        return None
    return exit_inning - entry_inning + 1


def _game_phase(inning):
    if inning is None:
        return None
    if inning <= 3:
        return 'early'
    if inning <= 6:
        return 'middle'
    if inning <= 9:
        return 'late'
    return 'extras'


def _outs_implausible(log, entry, exit_state, innings_spanned):
    outs = log.innings_pitched_outs
    if outs is None or innings_spanned is None:
        return False
    if innings_spanned * 3 < outs:
        return True
    entry_outs = entry.get('outs_at_entry')
    exit_outs = exit_state.get('outs_at_exit')
    entry_event = entry['event']
    exit_event = exit_state['event']
    if entry_outs is None or exit_outs is None:
        return False
    if entry_event.inning == exit_event.inning:
        max_possible = exit_outs - entry_outs
    else:
        max_possible = (
            (3 - entry_outs)
            + max(exit_event.inning - entry_event.inning - 1, 0) * 3
            + exit_outs
        )
    return outs > max_possible


def _matched_objects(
    *,
    marker,
    log,
    pitcher,
    segment,
    context,
    product_date,
    registry,
    templates,
    sync_run_id,
    source,
):
    return [
        _entry_object(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source),
        _exit_object(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source),
        _order_object(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source),
        _innings_object(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source),
        _phase_object(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source),
        _matched_reconciliation(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source),
        _base_state_object(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source),
    ]


def _entry_object(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source):
    entry = context['entry']
    reasons = []
    state = EvidenceObject.COMPLETENESS_COMPLETE
    if entry['outs_reason']:
        reasons.append(entry['outs_reason'])
        state = EvidenceObject.COMPLETENESS_UNKNOWN
    if entry['entry_flag_missing']:
        reasons.append(REASON_ENTRY_FLAG_MISSING)
    if context['resumed']:
        reasons.append(REASON_RESUMED_GAME_SPANS_DATES)
    claim = _entry_claim(segment, entry)
    return _build_object(
        rule_id=ENTRY_RULE_ID,
        marker=marker,
        log=log,
        pitcher=pitcher,
        product_date=product_date,
        claim=claim,
        cited_inputs=_entry_citations(marker, log, segment, entry),
        input_values={
            'final_play_by_play.mlb_game_pk': marker.mlb_game_pk,
            'game_logs.games_started': log.games_started,
            'entry_event_index': segment.entry_event.event_index,
            'outs_at_entry': entry['outs_at_entry'],
            'margin': entry['margin'],
        },
        trace={
            'steps': [
                'Selected the lowest event_index in the pitcher appearance span.',
                'Looked up the preceding same-half event for entry outs.',
                'Used the immediately preceding stored event for margin arithmetic.',
            ],
            'entry_event_index': segment.entry_event.event_index,
            'preceding_same_half_event_index': _event_index(entry['prior_same_half_event']),
            'preceding_margin_event_index': _event_index(entry['prior_event']),
            'margin_arithmetic': {
                'fielding_team_id': segment.entry_event.fielding_team_id,
                'batting_team_id': segment.entry_event.batting_team_id,
                'fielding_team_value': entry['fielding_score'],
                'batting_team_value': entry['batting_score'],
                'margin': entry['margin'],
            },
            'entry_flag_corroboration': bool(segment.entry_event.is_pitching_change),
        },
        limitations=[PLAY_GRANULARITY_LIMITATION, BASE_STATE_LIMITATION] + _resumed_limitations(context),
        state=state,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _exit_object(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source):
    exit_state = context['exit']
    reasons = []
    state = EvidenceObject.COMPLETENESS_COMPLETE
    if exit_state['outs_reason']:
        reasons.append(exit_state['outs_reason'])
        state = EvidenceObject.COMPLETENESS_UNKNOWN
    if context['resumed']:
        reasons.append(REASON_RESUMED_GAME_SPANS_DATES)
    return _build_object(
        rule_id=EXIT_RULE_ID,
        marker=marker,
        log=log,
        pitcher=pitcher,
        product_date=product_date,
        claim=_exit_claim(segment, exit_state),
        cited_inputs=_exit_citations(marker, log, segment, exit_state),
        input_values={
            'final_play_by_play.mlb_game_pk': marker.mlb_game_pk,
            'game_logs.games_started': log.games_started,
            'exit_event_index': segment.exit_event.event_index,
            'outs_at_exit': exit_state['outs_at_exit'],
        },
        trace={
            'steps': [
                'Selected the highest event_index in the pitcher appearance span.',
                'Checked the next team pitching segment for exit boundary type.',
            ],
            'exit_event_index': segment.exit_event.event_index,
            'next_pitcher_entry_event_index': _event_index(
                getattr(exit_state.get('next_segment'), 'entry_event', None)
            ),
            'boundary_type': exit_state['boundary_type'],
            'removed_mid_inning': exit_state['removed_mid_inning'],
        },
        limitations=[PLAY_GRANULARITY_LIMITATION] + _resumed_limitations(context),
        state=state,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _order_object(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source):
    team_segments = context['team_segments']
    citations = [_marker_citation(marker), _game_log_citation(log, ('games_started', 'innings_pitched_outs'))]
    citations.extend(_event_citation(item.entry_event, ('event_index', 'pitcher_mlb_id', 'fielding_team_id'), 'team_sequence_entry') for item in team_segments)
    if context['resumed']:
        reasons = [REASON_RESUMED_GAME_SPANS_DATES]
    else:
        reasons = []
    return _build_object(
        rule_id=ORDER_RULE_ID,
        marker=marker,
        log=log,
        pitcher=pitcher,
        product_date=product_date,
        claim=f'{_ordinal(segment.order)} pitcher used by the team in game {marker.mlb_game_pk}.',
        cited_inputs=tuple(citations),
        input_values={
            'final_play_by_play.mlb_game_pk': marker.mlb_game_pk,
            'game_logs.games_started': log.games_started,
            'order': segment.order,
        },
        trace={
            'steps': ['Ranked distinct team pitchers by first event_index.'],
            'order': segment.order,
            'team_entry_event_indexes': [item.entry_event.event_index for item in team_segments],
            'team_pitcher_mlb_ids': [item.pitcher_mlb_id for item in team_segments],
        },
        limitations=_resumed_limitations(context),
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _innings_object(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source):
    reasons = [REASON_RESUMED_GAME_SPANS_DATES] if context['resumed'] else []
    return _build_object(
        rule_id=INNINGS_RULE_ID,
        marker=marker,
        log=log,
        pitcher=pitcher,
        product_date=product_date,
        claim=(
            f'Appearance touched {context["innings_spanned"]} inning(s): '
            f'{segment.entry_event.inning} through {segment.exit_event.inning}.'
        ),
        cited_inputs=(
            _marker_citation(marker),
            _game_log_citation(log, ('games_started', 'innings_pitched_outs')),
            _event_citation(segment.entry_event, ('event_index', 'inning'), 'entry_event'),
            _event_citation(segment.exit_event, ('event_index', 'inning'), 'exit_event'),
        ),
        input_values={
            'final_play_by_play.mlb_game_pk': marker.mlb_game_pk,
            'game_logs.games_started': log.games_started,
            'innings_spanned': context['innings_spanned'],
        },
        trace={
            'steps': ['Computed exit inning - entry inning + 1.'],
            'entry_inning': segment.entry_event.inning,
            'exit_inning': segment.exit_event.inning,
            'innings_spanned': context['innings_spanned'],
            'stored_outs_recorded': log.innings_pitched_outs,
        },
        limitations=_resumed_limitations(context),
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _phase_object(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source):
    reasons = [REASON_RESUMED_GAME_SPANS_DATES] if context['resumed'] else []
    phase = context['phase']
    return _build_object(
        rule_id=PHASE_RULE_ID,
        marker=marker,
        log=log,
        pitcher=pitcher,
        product_date=product_date,
        claim=(
            f"Entry inning {segment.entry_event.inning} falls in the registered "
            f"'{phase}' band ({_phase_band(phase)})."
        ),
        cited_inputs=(
            _marker_citation(marker),
            _game_log_citation(log, ('games_started', 'innings_pitched_outs')),
            _event_citation(segment.entry_event, ('event_index', 'inning'), 'entry_event'),
        ),
        input_values={
            'final_play_by_play.mlb_game_pk': marker.mlb_game_pk,
            'game_logs.games_started': log.games_started,
            'entry_inning': segment.entry_event.inning,
            'phase': phase,
        },
        trace={
            'steps': ['Classified entry inning into early, middle, late, or extras band.'],
            'thresholds': {'early_max': 3, 'middle_max': 6, 'late_max': 9},
            'entry_inning': segment.entry_event.inning,
            'phase': phase,
        },
        limitations=_resumed_limitations(context),
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _matched_reconciliation(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source):
    reasons = [REASON_RESUMED_GAME_SPANS_DATES] if context['resumed'] else []
    return _build_object(
        rule_id=RECONCILIATION_RULE_ID,
        marker=marker,
        log=log,
        pitcher=pitcher,
        product_date=product_date,
        claim=(
            f'Play-by-play span and stored pitching line agree for pitcher '
            f'{pitcher.id} in game {marker.mlb_game_pk}.'
        ),
        cited_inputs=_reconciliation_citations(marker, log, segment),
        input_values={'final_play_by_play.mlb_game_pk': marker.mlb_game_pk},
        trace=_reconciliation_trace(segment, context, log),
        limitations=_resumed_limitations(context),
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _base_state_object(marker, log, pitcher, segment, context, product_date, registry, templates, sync_run_id, source):
    reasons = [REASON_BASE_STATE_UNAVAILABLE]
    if context['resumed']:
        reasons.append(REASON_RESUMED_GAME_SPANS_DATES)
    return _build_object(
        rule_id=BASE_STATE_RULE_ID,
        marker=marker,
        log=log,
        pitcher=pitcher,
        product_date=product_date,
        claim=(
            'Runners on base at entry: unknown by design; stored play-by-play '
            'events carry no base-runner state.'
        ),
        cited_inputs=(
            _marker_citation(marker),
            _game_log_citation(log, ('games_started', 'innings_pitched_outs', 'inherited_runners')),
            _event_citation(segment.entry_event, ('event_index', 'inning', 'half_inning'), 'entry_event'),
        ),
        input_values={
            'final_play_by_play.mlb_game_pk': marker.mlb_game_pk,
            'game_logs.games_started': log.games_started,
            'base_state_at_entry': None,
        },
        trace={
            'steps': [
                'Verified stored normalized play-by-play event schema has no base-runner state.',
                'Recorded base state as unknown by rule.',
            ],
            'entry_event_index': segment.entry_event.event_index,
            'base_state_source': 'unavailable_in_stored_final_play_by_play',
        },
        limitations=[BASE_STATE_LIMITATION] + _resumed_limitations(context),
        state=EvidenceObject.COMPLETENESS_UNKNOWN,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _role_unknown_reconciliation(
    *,
    marker,
    log,
    pitcher,
    segment,
    product_date,
    registry,
    templates,
    sync_run_id,
    source,
    resumed,
):
    reasons = [REASON_APPEARANCE_ROLE_UNKNOWN]
    if resumed:
        reasons.append(REASON_RESUMED_GAME_SPANS_DATES)
    claim = (
        f'Appearance context is unknown for pitcher {pitcher.id} in game '
        f'{marker.mlb_game_pk} because the stored games-started value is unknown.'
    )
    citations = [_marker_citation(marker), _game_log_citation(log, ('games_started', 'innings_pitched_outs'))]
    if segment is not None:
        citations.append(_event_citation(segment.entry_event, ('event_index', 'pitcher_mlb_id'), 'entry_event'))
    return _build_object(
        rule_id=RECONCILIATION_RULE_ID,
        marker=marker,
        log=log,
        pitcher=pitcher,
        product_date=product_date,
        claim=claim,
        cited_inputs=tuple(citations),
        input_values={'final_play_by_play.mlb_game_pk': marker.mlb_game_pk},
        trace={
            'steps': ['Checked games_started before emitting appearance-scoped context.'],
            'game_log_id': log.id,
            'games_started': log.games_started,
            'entry_event_index': _event_index(segment.entry_event if segment else None),
        },
        limitations=_limitations(resumed=resumed),
        state=EvidenceObject.COMPLETENESS_UNKNOWN,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _pbp_missing_reconciliation(
    *,
    marker,
    log,
    pitcher,
    product_date,
    registry,
    templates,
    sync_run_id,
    source,
    resumed,
):
    reasons = [REASON_PBP_APPEARANCE_MISSING]
    if resumed:
        reasons.append(REASON_RESUMED_GAME_SPANS_DATES)
    return _build_object(
        rule_id=RECONCILIATION_RULE_ID,
        marker=marker,
        log=log,
        pitcher=pitcher,
        product_date=product_date,
        claim=(
            f'Stored pitching line for pitcher {pitcher.id} in game '
            f'{marker.mlb_game_pk} has no matching play-by-play appearance; '
            'condition remains unknown because zero-batter substitutions can occur.'
        ),
        cited_inputs=(
            _marker_citation(marker),
            _game_log_citation(log, ('games_started', 'innings_pitched_outs')),
        ),
        input_values={'final_play_by_play.mlb_game_pk': marker.mlb_game_pk},
        trace={
            'steps': [
                'Searched stored play-by-play events for the pitcher MLB id.',
                'Found no matching stored event span.',
            ],
            'pitcher_mlb_id': pitcher.mlb_id,
            'game_log_id': log.id,
        },
        limitations=_limitations(resumed=resumed),
        state=EvidenceObject.COMPLETENESS_UNKNOWN,
        reason_codes=reasons,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _conflict_reconciliation(
    *,
    marker,
    log,
    pitcher,
    segment,
    context,
    product_date,
    registry,
    templates,
    sync_run_id,
    source,
):
    return _build_object(
        rule_id=RECONCILIATION_RULE_ID,
        marker=marker,
        log=log,
        pitcher=pitcher,
        product_date=product_date,
        claim=_conflict_claim(marker, log, pitcher, segment, context),
        cited_inputs=_reconciliation_citations(marker, log, segment),
        input_values={'final_play_by_play.mlb_game_pk': marker.mlb_game_pk},
        trace=_reconciliation_trace(segment, context, log),
        limitations=_limitations(resumed=context.get('resumed')),
        state=EvidenceObject.COMPLETENESS_CONFLICT,
        reason_codes=context['reasons'],
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _build_object(
    *,
    rule_id,
    marker,
    log,
    pitcher,
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
    _assert_text_has_no_appearance_forbidden_terms(claim)
    rule = registry.get(rule_id, RULE_VERSION)
    template = templates.get(_template_id(rule_id), RULE_VERSION)
    full_input_values = dict(input_values or {})
    evidence = build_evidence_object(
        rule_id=rule.rule_id,
        rule_version=RULE_VERSION,
        claim_template=template,
        claim_values={'claim': claim},
        subject_type=SUBJECT_TYPE,
        subject_id=f'{pitcher.id}:{marker.mlb_game_pk}',
        product_date=product_date,
        cited_inputs=tuple(cited_inputs),
        computation_trace=trace,
        input_values=full_input_values,
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
    return BuiltAppearanceEvidence(
        evidence=evidence,
        rule_id=rule_id,
        subject_key=evidence.subject_key,
    )


def _readiness_payload():
    return {
        'families': {
            'final_play_by_play': {'status': 'ready', 'reason_codes': []},
            'game_logs': {'status': 'ready', 'reason_codes': []},
        }
    }


def _entry_claim(segment, entry):
    inning = _half_label(segment.entry_event.half_inning, segment.entry_event.inning)
    outs = _outs_phrase(entry['outs_at_entry'])
    margin = _margin_phrase(entry)
    mid = 'mid-inning entry' if entry['mid_inning'] else 'half-inning start'
    return (
        f'Entered in the {inning} with {outs}, {margin}; {mid}; '
        'runners on base at entry unknown.'
    )


def _exit_claim(segment, exit_state):
    inning = _half_label(segment.exit_event.half_inning, segment.exit_event.inning)
    outs = _outs_phrase(exit_state['outs_at_exit'])
    boundary = (
        'removed mid-inning by a pitching change'
        if exit_state['removed_mid_inning']
        else (
            'relieved before the team next pitching event'
            if exit_state['boundary_type'] == 'relieved'
            else 'finished the team pitching sequence for the game'
        )
    )
    return f'Final event in the {inning} with {outs} recorded post-play; {boundary}.'


def _conflict_claim(marker, log, pitcher, segment, context):
    reason = context['reconciliation_reason']
    if reason == REASON_OUTS_IMPLAUSIBLE and log is not None:
        entry = context['entry']
        return (
            'Play-by-play span and stored pitching line disagree: game log '
            f'records {log.innings_pitched_outs} outs; span of '
            f'{context["innings_spanned"]} inning(s) with entry at '
            f'{entry["outs_at_entry"]} outs cannot hold that total. Both '
            'stored sides cited where present; no side preferred.'
        )
    if reason == REASON_NON_CONTIGUOUS_PITCHER_SPAN:
        return (
            f'Play-by-play span for pitcher {pitcher.id} in game '
            f'{marker.mlb_game_pk} is non-contiguous. Both stored sides cited '
            'where present; no side preferred.'
        )
    if reason == REASON_ORDER_INCONSISTENT:
        return (
            f'Team pitching order is inconsistent for pitcher {pitcher.id} in '
            f'game {marker.mlb_game_pk}. Both stored sides cited where present; '
            'no side preferred.'
        )
    return (
        f'Play-by-play shows pitcher {pitcher.id} in game {marker.mlb_game_pk}, '
        'but no stored pitching line exists. Both stored sides cited where '
        'present; no side preferred.'
    )


def _reconciliation_trace(segment, context, log):
    entry = context.get('entry') or {}
    exit_state = context.get('exit') or {}
    return {
        'steps': [
            'Compared play-by-play span to stored pitching line.',
            'Checked span contiguity.',
            'Checked team order ranking.',
            'Checked stored outs against innings spanned and entry/exit outs when known.',
        ],
        'entry_event_index': _event_index(segment.entry_event if segment else None),
        'exit_event_index': _event_index(segment.exit_event if segment else None),
        'order': context.get('order'),
        'innings_spanned': context.get('innings_spanned'),
        'stored_outs_recorded': getattr(log, 'innings_pitched_outs', None),
        'entry_outs': entry.get('outs_at_entry'),
        'exit_outs': exit_state.get('outs_at_exit'),
        'reconciliation_state': context.get('reconciliation_state'),
        'reconciliation_reason': context.get('reconciliation_reason'),
        'reason_codes': list(context.get('reasons') or []),
    }


def _entry_citations(marker, log, segment, entry):
    citations = [
        _marker_citation(marker),
        _game_log_citation(log, ('games_started', 'innings_pitched_outs')),
        _event_citation(
            segment.entry_event,
            (
                'event_index',
                'inning',
                'half_inning',
                'outs_at_event',
                'home_score_at_event',
                'away_score_at_event',
                'pitcher_mlb_id',
                'batting_team_id',
                'fielding_team_id',
                'is_pitching_change',
            ),
            'entry_event',
        ),
    ]
    if entry.get('prior_same_half_event') is not None:
        citations.append(_event_citation(
            entry['prior_same_half_event'],
            ('event_index', 'outs_at_event'),
            'preceding_state_event',
        ))
    if entry.get('prior_event') is not None and entry.get('prior_event') != entry.get('prior_same_half_event'):
        citations.append(_event_citation(
            entry['prior_event'],
            ('event_index', 'home_score_at_event', 'away_score_at_event'),
            'preceding_margin_event',
        ))
    return tuple(citations)


def _exit_citations(marker, log, segment, exit_state):
    citations = [
        _marker_citation(marker),
        _game_log_citation(log, ('games_started', 'innings_pitched_outs')),
        _event_citation(
            segment.exit_event,
            ('event_index', 'inning', 'half_inning', 'outs_at_event', 'pitcher_mlb_id', 'fielding_team_id'),
            'exit_event',
        ),
    ]
    next_segment = exit_state.get('next_segment')
    if next_segment is not None:
        citations.append(_event_citation(
            next_segment.entry_event,
            ('event_index', 'inning', 'half_inning', 'pitcher_mlb_id', 'fielding_team_id'),
            'next_pitcher_entry_event',
        ))
    return tuple(citations)


def _reconciliation_citations(marker, log, segment):
    citations = [_marker_citation(marker)]
    if log is not None:
        citations.append(_game_log_citation(log, ('games_started', 'innings_pitched_outs')))
    if segment is not None:
        citations.append(_event_citation(
            segment.entry_event,
            ('event_index', 'pitcher_mlb_id', 'fielding_team_id'),
            'entry_event',
        ))
        citations.append(_event_citation(
            segment.exit_event,
            ('event_index', 'pitcher_mlb_id', 'fielding_team_id', 'outs_at_event'),
            'exit_event',
        ))
    return tuple(citations)


def _marker_citation(marker):
    return EvidenceCitationInput(
        source_family='final_play_by_play',
        source_table='play_by_play_processed_games',
        source_pk=marker.id,
        source_field_names=('mlb_game_pk', 'processing_status'),
        citation_role='processing_gate',
        cited_values={
            'mlb_game_pk': marker.mlb_game_pk,
            'processing_status': marker.processing_status,
            'game_date': _citation_value(marker.game_date),
        },
        provenance={
            'source': marker.source,
            'sync_run_id': marker.sync_run_id,
            'correction_count': marker.correction_count or 0,
            'last_corrected_at': _iso(marker.last_corrected_at),
            'correction_source': marker.correction_source,
        },
    )


def _event_citation(event, fields, role):
    return EvidenceCitationInput(
        source_family='final_play_by_play',
        source_table='game_play_by_play_events',
        source_pk=event.id,
        source_field_names=tuple(fields),
        citation_role=role,
        cited_values={field: _citation_value(getattr(event, field, None)) for field in fields},
        provenance={
            'source': event.source,
            'sync_run_id': event.sync_run_id,
            'correction_count': event.correction_count or 0,
            'last_corrected_at': _iso(event.last_corrected_at),
            'correction_source': event.correction_source,
        },
    )


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


def _record_reconciliation_dead_letter(
    *,
    reason_code,
    marker,
    pitcher,
    log,
    segment,
    sync_run_id,
    extra=None,
):
    payload = {
        'reason': reason_code,
        'mlb_game_pk': marker.mlb_game_pk,
        'game_date': _citation_value(marker.game_date),
        'pitcher_id': getattr(pitcher, 'id', None),
        'pitcher_mlb_id': getattr(pitcher, 'mlb_id', None) or getattr(segment, 'pitcher_mlb_id', None),
        'game_log_id': getattr(log, 'id', None),
        'entry_event_id': getattr(getattr(segment, 'entry_event', None), 'id', None),
        'exit_event_id': getattr(getattr(segment, 'exit_event', None), 'id', None),
        'entry_event_index': _event_index(getattr(segment, 'entry_event', None)),
        'exit_event_index': _event_index(getattr(segment, 'exit_event', None)),
    }
    payload.update(extra or {})
    dead_letter.record_failure(
        RECONCILIATION_ENTITY_TYPE,
        reason_code,
        entity_ref=marker.mlb_game_pk,
        payload=payload,
        sync_run_id=sync_run_id,
        job_name='phase0d_appearance_context',
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


def _limitations(*, resumed):
    values = []
    if resumed:
        values.append(RESUMED_GAME_LIMITATION)
    return values


def _resumed_limitations(context):
    return [RESUMED_GAME_LIMITATION] if context.get('resumed') else []


def _half_label(half, inning):
    label = 'top' if half == 'top' else 'bottom' if half == 'bottom' else 'unknown half'
    return f'{label} of the {inning}'


def _outs_phrase(outs):
    if outs is None:
        return 'outs unknown'
    unit = 'out' if outs == 1 else 'outs'
    return f'{outs} {unit}'


def _margin_phrase(entry):
    fielding = entry.get('fielding_score')
    batting = entry.get('batting_score')
    margin = entry.get('margin')
    if fielding is None or batting is None or margin is None:
        return 'team margin unknown'
    if margin > 0:
        state = 'team leading'
    elif margin < 0:
        state = 'team trailing'
    else:
        state = 'teams tied'
    return f'{state} {fielding}-{batting} (margin {margin:+d})'


def _phase_band(phase):
    return {
        'early': 'innings 1-3',
        'middle': 'innings 4-6',
        'late': 'innings 7-9',
        'extras': 'inning 10 or later',
    }.get(phase, 'unknown band')


def _ordinal(value):
    names = {
        1: 'First',
        2: 'Second',
        3: 'Third',
        4: 'Fourth',
        5: 'Fifth',
        6: 'Sixth',
        7: 'Seventh',
        8: 'Eighth',
        9: 'Ninth',
    }
    return names.get(value, f'{value}th')


def _template_id(rule_id):
    return f'{rule_id}_claim'


def _event_index(event):
    return getattr(event, 'event_index', None)


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
