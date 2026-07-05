"""Phase 0D evidence classification metadata and validation helpers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum

from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.play_by_play_foundation import GamePlayByPlayEvent, PlayByPlayProcessedGame
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from models.postgame_processed_game import PostgameProcessedGame
from models.roster_status_snapshot import RosterStatusSnapshot
from models.team_game_pitching_split import TeamGamePitchingSplit
from services.appearance_context_evidence import register_appearance_context_rules
from services.entry_band_usage_evidence import register_entry_band_usage_rules
from services.evidence_rules import (
    ClaimTemplateRegistry,
    EvidenceRule,
    EvidenceRuleRegistry,
)
from services.inherited_traffic_evidence import register_inherited_traffic_rules
from services.roster_depth_evidence import register_roster_depth_rules
from services.starter_exposure_evidence import register_starter_exposure_rules
from services.team_relief_composition_evidence import register_team_relief_composition_rules
from services.workload_recovery_evidence import register_workload_recovery_rules
from utils.db import db


class EvidenceClassification(str, Enum):
    PERMANENTLY_INTERNAL = 'PERMANENTLY_INTERNAL'
    INTERNAL_ONLY_FOR_NOW = 'INTERNAL_ONLY_FOR_NOW'
    ELIGIBLE_PUBLIC_CANDIDATE_LATER = 'ELIGIBLE_PUBLIC_CANDIDATE_LATER'
    PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE = 'PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE'
    DEFERRED = 'DEFERRED'
    REJECTED = 'REJECTED'


class EvidenceClassificationError(AssertionError):
    """Raised when Phase 0D classification metadata violates the exit contract."""


@dataclass(frozen=True)
class EvidenceClassificationEntry:
    rule_id: str
    classification: EvidenceClassification
    rationale: str
    preconditions: tuple[str, ...]
    required_language_ref: str | None = None
    global_gates: tuple[str, ...] = ()
    misuse_prevention_tags: tuple[str, ...] = ()
    decided_in: str = '0D-09'


@dataclass(frozen=True)
class DecisionRegisterClassification:
    subject_id: str
    classification: EvidenceClassification
    rationale: str
    decided_in: str = '0D-09'


PHASE0B_LEGAL_SOURCE_REVIEW_GATE = 'phase0b_legal_source_review'
EXPLICIT_SURFACE_PHASE_GATE = 'explicit_surface_phase'
PUBLIC_CANDIDATE_GATES = (
    PHASE0B_LEGAL_SOURCE_REVIEW_GATE,
    EXPLICIT_SURFACE_PHASE_GATE,
)

FULL_MISUSE_PREVENTION_TAGS = (
    'no_health_inference',
    'no_availability_inference',
    'no_role_assignment',
    'no_manager_intent',
    'no_team_quality_labels',
    'no_pressure_leverage_public',
    'no_scores_ranks_grades',
    'no_prediction_betting',
)

WORKLOAD_LANGUAGE = 'docs/phase0d/public_language_rules.md#workload-recovery'
APPEARANCE_LANGUAGE = 'docs/phase0d/public_language_rules.md#appearance-entry-exit'
INHERITED_LANGUAGE = 'docs/phase0d/public_language_rules.md#inherited-traffic-clean-outing'
STARTER_EXPOSURE_LANGUAGE = 'docs/phase0d/public_language_rules.md#starter-exposure-calendar-density'
ROSTER_LANGUAGE = 'docs/phase0d/public_language_rules.md#roster-depth-churn'
ENTRY_BAND_LANGUAGE = 'docs/phase0d/public_language_rules.md#entry-context-bands-usage-observations'
TEAM_RELIEF_LANGUAGE = 'docs/phase0d/public_language_rules.md#team-relief-contributor-composition'


def _entry(
    rule_id,
    classification,
    rationale,
    preconditions,
    required_language_ref=None,
    global_gates=(),
    misuse_prevention_tags=(),
):
    return EvidenceClassificationEntry(
        rule_id=rule_id,
        classification=classification,
        rationale=rationale,
        preconditions=tuple(preconditions),
        required_language_ref=required_language_ref,
        global_gates=tuple(global_gates),
        misuse_prevention_tags=tuple(misuse_prevention_tags),
    )


def _pc(rule_id, rationale, preconditions, language_ref):
    return _entry(
        rule_id,
        EvidenceClassification.PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE,
        rationale,
        preconditions,
        required_language_ref=language_ref,
        global_gates=PUBLIC_CANDIDATE_GATES,
        misuse_prevention_tags=FULL_MISUSE_PREVENTION_TAGS,
    )


def _el(rule_id, rationale, preconditions, language_ref):
    return _entry(
        rule_id,
        EvidenceClassification.ELIGIBLE_PUBLIC_CANDIDATE_LATER,
        rationale,
        preconditions,
        required_language_ref=language_ref,
        global_gates=PUBLIC_CANDIDATE_GATES,
        misuse_prevention_tags=FULL_MISUSE_PREVENTION_TAGS,
    )


def _io(rule_id, rationale, preconditions):
    return _entry(
        rule_id,
        EvidenceClassification.INTERNAL_ONLY_FOR_NOW,
        rationale,
        preconditions,
    )


def _pi(rule_id, rationale):
    return _entry(
        rule_id,
        EvidenceClassification.PERMANENTLY_INTERNAL,
        rationale,
        (),
    )


CLASSIFICATION_ENTRIES: dict[str, EvidenceClassificationEntry] = {
    entry.rule_id: entry
    for entry in (
        _pc('workload_last_final_appearance', 'Past dated workload fact.', ('past-tense date only',), WORKLOAD_LANGUAGE),
        _pc('workload_days_of_rest', 'Past rest-count fact with no public state meaning.', ('never renders availability',), WORKLOAD_LANGUAGE),
        _pc('workload_window_appearances', 'Window count fact.', ('window and count both shown',), WORKLOAD_LANGUAGE),
        _pc('workload_window_pitches', 'Window pitch-count subtotal fact.', ('unknown-subtotal language',), WORKLOAD_LANGUAGE),
        _pc('workload_window_outs', 'Window out-count fact.', ('window and count both shown',), WORKLOAD_LANGUAGE),
        _pc('workload_window_batters_faced', 'Window batters-faced subtotal fact.', ('unknown-subtotal language',), WORKLOAD_LANGUAGE),
        _pc('usage_back_to_back', 'Observed workload pattern fact.', ('threshold displayed beside flag',), WORKLOAD_LANGUAGE),
        _pc('usage_three_in_four', 'Observed workload pattern fact.', ('threshold displayed beside flag',), WORKLOAD_LANGUAGE),
        _pc('usage_four_in_six', 'Observed workload pattern fact.', ('threshold displayed beside flag',), WORKLOAD_LANGUAGE),
        _pc('outing_multi_inning', 'Past outing span fact.', ('threshold displayed beside flag',), WORKLOAD_LANGUAGE),
        _pc('outing_high_pitch', 'Past pitch-count threshold fact.', ('count always rendered beside threshold',), WORKLOAD_LANGUAGE),
        _pc('appearance_short_rest', 'Past appearance short-rest fact.', ('threshold displayed beside flag',), WORKLOAD_LANGUAGE),
        _pc('appearance_entry_context', 'Entry timing fact from stored final play-by-play.', ('base-state limitation always rendered',), APPEARANCE_LANGUAGE),
        _pc('appearance_exit_context', 'Exit timing fact from stored final play-by-play.', ('play-granularity note',), APPEARANCE_LANGUAGE),
        _pc('appearance_order_in_game', 'Appearance order fact.', ('sequence-fact-only phrasing',), APPEARANCE_LANGUAGE),
        _pc('appearance_innings_spanned', 'Inning span fact.', ('span-not-outs language',), APPEARANCE_LANGUAGE),
        _pc('appearance_game_phase', 'Inning band fact.', ('inning-band-only',), APPEARANCE_LANGUAGE),
        _pi('appearance_pbp_reconciliation', 'Pipeline diagnostic; may inform aggregate trust surfaces in Phase 0K but never a public claim.'),
        _pi('appearance_entry_base_state', 'Contract-locked UNKNOWN gap record.'),
        _pc('appearance_inherited_runners', 'Boxscore inherited-runner fact.', ('boxscore-source language',), INHERITED_LANGUAGE),
        _pc('appearance_inherited_runners_scored', 'Boxscore inherited-runner result fact.', ('boxscore-source language',), INHERITED_LANGUAGE),
        _pc('appearance_inherited_traffic_outcome', 'Boxscore inherited-traffic outcome fact.', ('boxscore-source language',), INHERITED_LANGUAGE),
        _pi('appearance_inherited_entry_corroboration', 'Coherence diagnostic.'),
        _pc('outing_clean', 'Clean outing fact with full source definition.', ('full definition display incl. HBP/ROE exclusion verbatim',), INHERITED_LANGUAGE),
        _pc('outing_traffic', 'Traffic outing fact with threshold count.', ('threshold plus counts rendered',), INHERITED_LANGUAGE),
        _io('outing_context_unknown', 'Accounting object that informs degraded phrasing.', ('public phrasing must be degraded and not claim an outing class',)),
        _pc('team_bullpen_share_of_outs', 'Team split share fact with numerator and denominator.', ('both sums shown',), STARTER_EXPOSURE_LANGUAGE),
        _pc('team_bullpen_outs_window', 'Team bullpen out-count fact.', ('window and count both shown',), STARTER_EXPOSURE_LANGUAGE),
        _pc('team_bullpen_pitches_window', 'Team bullpen pitch subtotal fact.', ('known-subtotal language',), STARTER_EXPOSURE_LANGUAGE),
        _pc('team_reliever_appearances_window', 'Team relief appearance count fact.', ('appearances-not-distinct-arms disclaimer verbatim',), STARTER_EXPOSURE_LANGUAGE),
        _pc('team_short_start_count_window', 'Team short-start count fact.', ('14-outs definition display',), STARTER_EXPOSURE_LANGUAGE),
        _pc('team_consecutive_game_days', 'Team schedule density fact.', ('componentized counts only',), STARTER_EXPOSURE_LANGUAGE),
        _pc('team_doubleheader_today', 'Team schedule fact.', ('schedule fact only',), STARTER_EXPOSURE_LANGUAGE),
        _pc('team_recent_doubleheader', 'Recent team schedule fact.', ('componentized counts only',), STARTER_EXPOSURE_LANGUAGE),
        _pc('team_off_day_yesterday', 'Team prior-day schedule fact.', ('schedule fact only',), STARTER_EXPOSURE_LANGUAGE),
        _pc('team_off_day_tomorrow', 'Team next-day schedule fact.', ('schedule-subject-to-change disclaimer mandatory',), STARTER_EXPOSURE_LANGUAGE),
        _pc('team_calendar_density', 'Team schedule density component facts.', ('componentized counts only',), STARTER_EXPOSURE_LANGUAGE),
        _pc('team_active_pitcher_census', 'Current active-pitcher census fact.', ('pitchers-not-relievers note',), ROSTER_LANGUAGE),
        _pi('team_active_reliever_count', 'Contract-locked UNKNOWN; partition refused.'),
        _pi('team_roster_snapshot_state', 'Roster snapshot diagnostic.'),
        _pc('pitcher_il_placement_context', 'Public IL transaction context fact.', ('exact safe phrasing only',), ROSTER_LANGUAGE),
        _pc('pitcher_il_activation_context', 'Public IL transaction context fact.', ('exact safe phrasing only',), ROSTER_LANGUAGE),
        _pc('team_public_il_count', 'Team public IL count fact.', ('counts presence only; never statements about non-IL pitchers',), ROSTER_LANGUAGE),
        _pc('team_transaction_churn_window', 'Team transaction churn count fact.', ('coverage caveat',), ROSTER_LANGUAGE),
        _pc('team_transaction_category_counts_window', 'Team transaction category count fact.', ('category definitions shown',), ROSTER_LANGUAGE),
        _pc('team_option_recall_churn', 'Team option/recall churn count fact.', ('coverage caveat',), ROSTER_LANGUAGE),
        _pc('team_roster_movement_churn', 'Team roster movement churn count fact.', ('coverage caveat',), ROSTER_LANGUAGE),
        _io('team_depth_delta_daily', 'Requires production season-segment proof before any public review.', ('production season-segment of snapshot/alignment quality',)),
        _io('team_roster_changes_explained', 'Requires production season-segment proof before any public review.', ('production season-segment of snapshot/alignment quality',)),
        _io('team_roster_changes_unexplained', 'Requires production season-segment proof and phrasing review.', ('production season-segment of snapshot/alignment quality', 'editorial review of unexplained public framing')),
        _pi('team_transaction_alignment_state', 'Transaction alignment diagnostic.'),
        _pi('appearance_entry_band', 'Internal proxy; posture-locked.'),
        _pi('pitcher_entry_band_distribution', 'Distribution over internal proxy; posture-locked.'),
        _pc('appearance_finish_context', 'Boxscore finish-context fact.', ('legacy under-fire caveat',), ENTRY_BAND_LANGUAGE),
        _pc('pitcher_save_hold_window', 'Pitcher save/hold count fact.', ('counts only, never rates',), ENTRY_BAND_LANGUAGE),
        _el('pitcher_finish_usage_observation', 'Candidate only after band-derived components are re-rendered as plain facts.', ('band-derived components re-rendered as plain inning/margin facts', 'mechanical cell names never public', 'k=0 language review', 'floors intact and displayed'), ENTRY_BAND_LANGUAGE),
        _el('pitcher_multi_inning_usage_observation', 'Candidate only with floor display and k=0 review.', ('k=0 review', 'floors intact'), ENTRY_BAND_LANGUAGE),
        _el('pitcher_first_reliever_usage_observation', 'Candidate only as a sequence fact.', ('k=0 review', 'floors intact', 'sequence-fact-only phrasing re-verified'), ENTRY_BAND_LANGUAGE),
        _el('team_relief_contributor_basis', 'Team composition basis candidate with denominator guard.', ('denominator disclaimer travels verbatim', 'production season-segment of attribution-exclusion rates'), TEAM_RELIEF_LANGUAGE),
        _el('team_relief_rest_distribution', 'Team basis composition candidate.', ('basis preconditions inherited',), TEAM_RELIEF_LANGUAGE),
        _el('team_relief_density_usage_count', 'Team basis composition candidate.', ('basis preconditions inherited',), TEAM_RELIEF_LANGUAGE),
        _el('team_relief_workload_concentration', 'Team basis composition candidate with corroboration guard.', ('basis preconditions inherited', 'corroboration-mismatch rate observed low'), TEAM_RELIEF_LANGUAGE),
        _el('team_relief_outing_context_mix', 'Team basis composition candidate with 0D-04 coupling.', ('basis preconditions inherited', '0D-04 emission-policy coupling documented at any surface'), TEAM_RELIEF_LANGUAGE),
        _el('team_relief_finish_spread', 'Team basis composition candidate.', ('basis preconditions inherited',), TEAM_RELIEF_LANGUAGE),
    )
}

DECISION_REGISTER_CLASSIFICATIONS = {
    item.subject_id: item
    for item in (
        DecisionRegisterClassification('base_state_addendum', EvidenceClassification.DEFERRED, 'Optional future foundation work.'),
        DecisionRegisterClassification('bequeathed_traffic', EvidenceClassification.DEFERRED, 'Chained to future base-state addendum.'),
        DecisionRegisterClassification('handedness_exposure', EvidenceClassification.DEFERRED, 'Not stored; requires scoped foundation addendum.'),
        DecisionRegisterClassification('opener_bulk_patterns', EvidenceClassification.DEFERRED, 'Intent-laden label remains out of scope.'),
        DecisionRegisterClassification('team_level_entry_band_aggregation', EvidenceClassification.REJECTED, 'Rejected while posture lock stands.'),
        DecisionRegisterClassification('pressure_leverage_vocabulary', EvidenceClassification.REJECTED, 'Rejected for rule ids, evidence types, claims, and public copy.'),
    )
}

PERMANENTLY_INTERNAL_RULE_IDS = frozenset({
    'appearance_entry_band',
    'pitcher_entry_band_distribution',
    'appearance_entry_base_state',
    'team_active_reliever_count',
    'appearance_pbp_reconciliation',
    'team_transaction_alignment_state',
    'team_roster_snapshot_state',
    'appearance_inherited_entry_corroboration',
})

EXPECTED_CLASSIFICATION_TALLIES = {
    EvidenceClassification.PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE: 43,
    EvidenceClassification.ELIGIBLE_PUBLIC_CANDIDATE_LATER: 9,
    EvidenceClassification.INTERNAL_ONLY_FOR_NOW: 4,
    EvidenceClassification.PERMANENTLY_INTERNAL: 8,
}

PHASE0D_RULE_REGISTRATION_FUNCTIONS = (
    register_workload_recovery_rules,
    register_appearance_context_rules,
    register_inherited_traffic_rules,
    register_starter_exposure_rules,
    register_roster_depth_rules,
    register_entry_band_usage_rules,
    register_team_relief_composition_rules,
)

RESOLVABLE_SOURCE_TABLES = {
    'evidence_objects': EvidenceObject,
    'game_logs': GameLog,
    'game_play_by_play_events': GamePlayByPlayEvent,
    'play_by_play_processed_games': PlayByPlayProcessedGame,
    'player_transactions': PlayerTransaction,
    'player_transaction_sync_windows': PlayerTransactionSyncWindow,
    'postgame_processed_games': PostgameProcessedGame,
    'roster_status_snapshots': RosterStatusSnapshot,
    'team_game_pitching_splits': TeamGamePitchingSplit,
}

SYNTHETIC_PROVENANCE_TABLES = frozenset({
    'slate_coverage',
})


def phase0d_rule_registry():
    registry = EvidenceRuleRegistry()
    templates = ClaimTemplateRegistry()
    for register in PHASE0D_RULE_REGISTRATION_FUNCTIONS:
        register(registry=registry, template_registry=templates)
    return registry, templates


def registered_phase0d_rules(registry=None) -> tuple[EvidenceRule, ...]:
    if registry is None:
        registry, _ = phase0d_rule_registry()
    return registry.all_rules()


def registered_phase0d_rule_ids(registry=None) -> tuple[str, ...]:
    return tuple(rule.rule_id for rule in registered_phase0d_rules(registry))


def classification_tallies(entries=None):
    rows = entries or CLASSIFICATION_ENTRIES
    return Counter(entry.classification for entry in rows.values())


def validate_evidence_classifications(*, registry=None, entries=None) -> dict:
    rows = entries or CLASSIFICATION_ENTRIES
    rule_ids = set(registered_phase0d_rule_ids(registry))
    classified_ids = set(rows)
    missing = sorted(rule_ids - classified_ids)
    orphan = sorted(classified_ids - rule_ids)
    errors = []
    if missing:
        errors.append(f'missing classifications: {missing}')
    if orphan:
        errors.append(f'orphan classifications: {orphan}')
    for rule_id, entry in sorted(rows.items()):
        if entry.rule_id != rule_id:
            errors.append(f'entry key mismatch: {rule_id} != {entry.rule_id}')
        if entry.decided_in != '0D-09':
            errors.append(f'{rule_id} decided_in must be 0D-09')
        if entry.classification in {
            EvidenceClassification.DEFERRED,
            EvidenceClassification.REJECTED,
        }:
            errors.append(f'{rule_id} cannot carry {entry.classification.value}')
        if entry.classification != EvidenceClassification.PERMANENTLY_INTERNAL and not entry.preconditions:
            errors.append(f'{rule_id} requires preconditions')
        if entry.classification in {
            EvidenceClassification.PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE,
            EvidenceClassification.ELIGIBLE_PUBLIC_CANDIDATE_LATER,
        }:
            if not entry.required_language_ref:
                errors.append(f'{rule_id} requires required_language_ref')
            for gate in PUBLIC_CANDIDATE_GATES:
                if gate not in entry.global_gates:
                    errors.append(f'{rule_id} missing global gate {gate}')
            if set(entry.misuse_prevention_tags) != set(FULL_MISUSE_PREVENTION_TAGS):
                errors.append(f'{rule_id} requires full misuse prevention tags')
        if entry.classification == EvidenceClassification.PERMANENTLY_INTERNAL and entry.preconditions:
            errors.append(f'{rule_id} permanently internal entry must not carry preconditions')
    if errors:
        raise EvidenceClassificationError('; '.join(errors))
    tallies = classification_tallies(rows)
    return {
        'rule_count': len(rule_ids),
        'classified_count': len(classified_ids),
        'tallies': {key.value: tallies.get(key, 0) for key in EvidenceClassification},
    }


def validate_stored_evidence_integrity() -> dict:
    registry, _ = phase0d_rule_registry()
    definitions = {rule.rule_id: rule.plain_language_definition for rule in registry.all_rules()}
    errors = []
    evidence_rows = EvidenceObject.query.order_by(EvidenceObject.id.asc()).all()
    for row in evidence_rows:
        if row.rule_id not in definitions or not definitions.get(row.rule_id):
            errors.append(f'evidence_object:{row.id}:unknown_rule:{row.rule_id}')
    citation_rows = EvidenceCitation.query.order_by(EvidenceCitation.id.asc()).all()
    for citation in citation_rows:
        if not _citation_resolves(citation):
            errors.append(
                f'evidence_citation:{citation.id}:unresolved_source:'
                f'{citation.source_table}:{citation.source_pk}'
            )
    if errors:
        raise EvidenceClassificationError('; '.join(errors))
    return {
        'evidence_rows_checked': len(evidence_rows),
        'citation_rows_checked': len(citation_rows),
    }


def _citation_resolves(citation):
    if str(citation.source_pk or '').startswith('missing:'):
        return bool((citation.provenance or {}).get('source'))
    if citation.source_table in SYNTHETIC_PROVENANCE_TABLES:
        return bool((citation.provenance or {}).get('source'))
    model = RESOLVABLE_SOURCE_TABLES.get(citation.source_table)
    if model is None:
        return False
    try:
        pk = int(citation.source_pk)
    except (TypeError, ValueError):
        return False
    return db.session.get(model, pk) is not None
