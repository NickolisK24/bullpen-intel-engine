"""Internal Phase 0D team relief contributor composition evidence family."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
import re
import time

from sqlalchemy import asc

from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.play_by_play_foundation import GamePlayByPlayEvent
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
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


logger = logging.getLogger('baseballos.daily_sync')

RULE_VERSION = 1
EVIDENCE_SOURCE = 'phase0d:team_relief_composition_evidence'
SOURCE_READY = 'ready'
SUBJECT_TEAM = 'team'
SUBJECT_APPEARANCE = 'pitcher_appearance'
SUBJECT_PITCHER = 'pitcher'

TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID = 'team_relief_contributor_basis'
TEAM_RELIEF_REST_DISTRIBUTION_RULE_ID = 'team_relief_rest_distribution'
TEAM_RELIEF_DENSITY_USAGE_COUNT_RULE_ID = 'team_relief_density_usage_count'
TEAM_RELIEF_WORKLOAD_CONCENTRATION_RULE_ID = 'team_relief_workload_concentration'
TEAM_RELIEF_OUTING_CONTEXT_MIX_RULE_ID = 'team_relief_outing_context_mix'
TEAM_RELIEF_FINISH_SPREAD_RULE_ID = 'team_relief_finish_spread'

TEAM_RELIEF_COMPOSITION_RULE_IDS = (
    TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID,
    TEAM_RELIEF_REST_DISTRIBUTION_RULE_ID,
    TEAM_RELIEF_DENSITY_USAGE_COUNT_RULE_ID,
    TEAM_RELIEF_WORKLOAD_CONCENTRATION_RULE_ID,
    TEAM_RELIEF_OUTING_CONTEXT_MIX_RULE_ID,
    TEAM_RELIEF_FINISH_SPREAD_RULE_ID,
)

WORKLOAD_DAYS_OF_REST_RULE_ID = 'workload_days_of_rest'
USAGE_BACK_TO_BACK_RULE_ID = 'usage_back_to_back'
USAGE_THREE_IN_FOUR_RULE_ID = 'usage_three_in_four'
USAGE_FOUR_IN_SIX_RULE_ID = 'usage_four_in_six'
TEAM_BULLPEN_OUTS_WINDOW_RULE_ID = 'team_bullpen_outs_window'
OUTING_CLEAN_RULE_ID = 'outing_clean'
OUTING_TRAFFIC_RULE_ID = 'outing_traffic'
OUTING_CONTEXT_UNKNOWN_RULE_ID = 'outing_context_unknown'
APPEARANCE_FINISH_CONTEXT_RULE_ID = 'appearance_finish_context'

LOCKED_BAND_RULE_IDS = (
    'appearance_entry_band',
    'pitcher_entry_band_distribution',
)
FLOORED_ENTRY_BAND_USAGE_OBSERVATION_RULE_IDS = (
    'pitcher_save_hold_window',
    'pitcher_finish_usage_observation',
    'pitcher_multi_inning_usage_observation',
    'pitcher_first_reliever_usage_observation',
)

REASON_ATTRIBUTION_UNKNOWN = 'attribution_unknown'
REASON_ATTRIBUTION_CONFLICT = 'attribution_conflict'
REASON_APPEARANCE_ROLE_UNKNOWN = 'appearance_role_unknown'
REASON_INCOMPLETE_SLATE_DAY = 'incomplete_slate_day_in_window'
REASON_BASIS_LOWER_BOUND = 'basis_lower_bound'
REASON_MEMBER_EVIDENCE_UNAVAILABLE = 'member_evidence_unavailable'
REASON_MEMBER_EVIDENCE_CONFLICT = 'member_evidence_conflict'
REASON_OUTING_FAMILY_COVERAGE_GAP = 'outing_family_coverage_gap'
REASON_CONCENTRATION_CORROBORATION_MISMATCH = 'concentration_corroboration_mismatch'
REASON_SHARE_EXCLUSION_PRESENT = 'share_exclusion_present'
REASON_ROSTER_MEMBERSHIP_UNKNOWN = 'roster_membership_unknown'
REASON_SOURCE_FAMILY_NOT_READY = 'source_family_not_ready'
REASON_GAME_LOG_CORRECTED = 'game_log_corrected'
REASON_ROSTER_SNAPSHOT_CORRECTED = 'roster_status_snapshot_corrected'
REASON_SOURCE_EVIDENCE_SUPERSEDED = 'source_evidence_superseded'
REASON_BASIS_SUPERSEDED = 'composition_basis_superseded'
REASON_LEGACY_ROW_DEFAULT_FALSE_CAVEAT = 'legacy_row_default_false_caveat'

COMPOSITION_ATTRIBUTION_CONFLICT_ENTITY_TYPE = 'composition_attribution_conflict'

BASIS_WINDOW_DAYS = 14
REST_WINDOW_DAYS = 14
DENSITY_WINDOW_DAYS = 14
CONCENTRATION_WINDOW_DAYS = (7, 14)
OUTING_CONTEXT_WINDOW_DAYS = 7
FINISH_SPREAD_WINDOW_DAYS = 14
TOP_N_VALUES = (1, 3)

BASIS_DISCLAIMER = (
    "This set is appearance-evidenced; the team's roster reliever count remains "
    'unknown by design.'
)
LOWER_BOUND_LIMITATION = (
    'Counts are lower bounds when a cited product-day window has incomplete slate coverage.'
)
LEGACY_FINISH_LIMITATION = (
    'Legacy row caveat from source finish-context evidence is carried forward.'
)

_RULE_DEFINITIONS = {
    TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID: (
        'For a team and product date, the 14-day recent relief contributor set: '
        'pitchers with one or more finality-certified relief appearances attributed '
        'by same-date roster snapshot authority, with play-by-play fielding team '
        'used only as corroboration where events exist. Thresholds: window_days [14]. '
        'The rendered claim carries the appearance-evidenced denominator disclaimer.'
    ),
    TEAM_RELIEF_REST_DISTRIBUTION_RULE_ID: (
        'For the 14-day basis set, counts of members by days-of-rest bucket from '
        'stored workload_days_of_rest evidence: 0, 1, 2, and 3-plus days, plus '
        'unknown member evidence. Thresholds: rest_bucket_edges [0, 1, 2].'
    ),
    TEAM_RELIEF_DENSITY_USAGE_COUNT_RULE_ID: (
        'For the 14-day basis set, counts of members with stored usage_back_to_back, '
        'usage_three_in_four, and usage_four_in_six evidence for the product date. '
        'Absent pattern objects remain false while unknown-state objects stay separate.'
    ),
    TEAM_RELIEF_WORKLOAD_CONCENTRATION_RULE_ID: (
        'For 7-day and 14-day windows, relief outs attributed to the team, the '
        'single largest contributor and three largest contributors by cited outs, '
        'and shares only when all appearances are attributed and complete. '
        'Thresholds: window_days [7, 14], top_n [1, 3].'
    ),
    TEAM_RELIEF_OUTING_CONTEXT_MIX_RULE_ID: (
        'For a 7-day window, counts of attributed qualifying relief appearances '
        'with stored outing_clean, outing_traffic, outing_context_unknown, and '
        'provably-neither outcomes. Thresholds: window_days [7].'
    ),
    TEAM_RELIEF_FINISH_SPREAD_RULE_ID: (
        'For the 14-day basis set, distinct member counts for games finished, save '
        'opportunity, save, hold, and blown save from stored per-appearance '
        'appearance_finish_context evidence only. Thresholds: window_days [14].'
    ),
}

_RULE_THRESHOLDS = {
    TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID: {'window_days': [14]},
    TEAM_RELIEF_REST_DISTRIBUTION_RULE_ID: {'rest_bucket_edges': [0, 1, 2]},
    TEAM_RELIEF_WORKLOAD_CONCENTRATION_RULE_ID: {
        'window_days': [7, 14],
        'top_n': [1, 3],
    },
    TEAM_RELIEF_OUTING_CONTEXT_MIX_RULE_ID: {'window_days': [7]},
    TEAM_RELIEF_FINISH_SPREAD_RULE_ID: {'window_days': [14]},
}

_REQUIRED_INPUT_FAMILIES = {
    TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID: (
        'game_logs',
        'roster_status_snapshots',
        'slate_coverage',
        'final_play_by_play',
    ),
    TEAM_RELIEF_REST_DISTRIBUTION_RULE_ID: (
        'game_logs',
        'roster_status_snapshots',
        'slate_coverage',
        'final_play_by_play',
        'phase0d_evidence_contract',
    ),
    TEAM_RELIEF_DENSITY_USAGE_COUNT_RULE_ID: (
        'game_logs',
        'roster_status_snapshots',
        'slate_coverage',
        'final_play_by_play',
        'phase0d_evidence_contract',
    ),
    TEAM_RELIEF_WORKLOAD_CONCENTRATION_RULE_ID: (
        'game_logs',
        'roster_status_snapshots',
        'slate_coverage',
        'final_play_by_play',
        'team_game_pitching_splits',
        'phase0d_evidence_contract',
    ),
    TEAM_RELIEF_OUTING_CONTEXT_MIX_RULE_ID: (
        'game_logs',
        'roster_status_snapshots',
        'slate_coverage',
        'final_play_by_play',
        'phase0d_evidence_contract',
    ),
    TEAM_RELIEF_FINISH_SPREAD_RULE_ID: (
        'game_logs',
        'roster_status_snapshots',
        'slate_coverage',
        'final_play_by_play',
        'phase0d_evidence_contract',
    ),
}

_REQUIRED_FIELDS = {
    TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID: (
        'game_logs.games_started',
        'roster_status_snapshots.team_id',
        'slate_coverage.slate_date',
    ),
    TEAM_RELIEF_REST_DISTRIBUTION_RULE_ID: (
        'phase0d_evidence_contract.rule_id',
        'phase0d_evidence_contract.completeness_state',
    ),
    TEAM_RELIEF_DENSITY_USAGE_COUNT_RULE_ID: (
        'phase0d_evidence_contract.rule_id',
        'phase0d_evidence_contract.completeness_state',
    ),
    TEAM_RELIEF_WORKLOAD_CONCENTRATION_RULE_ID: (
        'game_logs.innings_pitched_outs',
        'phase0d_evidence_contract.rule_id',
        'phase0d_evidence_contract.completeness_state',
    ),
    TEAM_RELIEF_OUTING_CONTEXT_MIX_RULE_ID: (
        'game_logs.mlb_game_pk',
        'phase0d_evidence_contract.rule_id',
        'phase0d_evidence_contract.completeness_state',
    ),
    TEAM_RELIEF_FINISH_SPREAD_RULE_ID: (
        'phase0d_evidence_contract.rule_id',
        'phase0d_evidence_contract.completeness_state',
    ),
}

_FORBIDDEN_TEAM_RELIEF_COMPOSITION_TERMS = (
    'struc' + 'ture',
    'hier' + 'archy',
    'peck' + 'ing order',
    'comm' + 'ittee',
    'thin',
    'deep',
    'depleted',
    'short-handed',
    'taxed',
    'gassed',
    'overworked',
    'fresh',
    'tired',
    'available',
    'unavailable',
    'ready',
    'trustworthy',
    'reliable',
    'workhorse',
    'go-to',
    'leaned on',
    'closer',
    'setup',
    'fireman',
    'long man',
    'quality',
    'grade',
    'rank',
    'ranking',
    'score',
    'green',
    'yellow',
    'red',
    'pres' + 'sure',
    'lever' + 'age',
    'predict',
    'prediction',
    'health',
    'healthy',
    'injury severity',
    'manager intent',
    'betting',
    'odds',
)


@dataclass(frozen=True)
class BuiltTeamReliefCompositionEvidence:
    evidence: EvidenceObject
    rule_id: str
    subject_key: str


@dataclass
class AttributionDecision:
    log: GameLog
    team_id: int | None
    pitcher_id: int
    pitcher_name: str
    included: bool
    reason_code: str | None
    snapshot: RosterStatusSnapshot | None
    current_snapshot: RosterStatusSnapshot | None
    pbp_events: tuple[GamePlayByPlayEvent, ...]

    @property
    def appearance_key(self) -> str:
        return f'{self.pitcher_id}:{self.log.mlb_game_pk}'


@dataclass
class AttributionWindow:
    product_date: date
    window_days: int
    start_date: date
    decisions: list[AttributionDecision]
    coverage_window: object

    def included_for_team(self, team_id: int) -> list[AttributionDecision]:
        return [
            item
            for item in self.decisions
            if item.team_id == team_id and item.included
        ]

    def exclusions_for_team(self, team_id: int) -> list[AttributionDecision]:
        return [
            item
            for item in self.decisions
            if item.team_id == team_id and not item.included
        ]

    def team_ids(self) -> list[int]:
        ids = {
            item.team_id
            for item in self.decisions
            if item.team_id is not None and (item.included or item.reason_code)
        }
        return sorted(ids)

    def lower_bound_reasons(self) -> list[str]:
        if self.coverage_window.complete:
            return []
        return [REASON_INCOMPLETE_SLATE_DAY, REASON_BASIS_LOWER_BOUND]


class TeamReliefCompositionBuildContext:
    def __init__(self, product_date, coverage, sync_run_id):
        self.product_date = _as_date(product_date)
        self.coverage = coverage
        self.sync_run_id = sync_run_id
        self.start_date = self.product_date - timedelta(days=BASIS_WINDOW_DAYS - 1)
        self.logs = _logs_for_range(self.start_date, self.product_date)
        self.pitcher_ids = sorted({row.pitcher_id for row in self.logs})
        self.game_pks = sorted({row.mlb_game_pk for row in self.logs})
        self.log_dates = sorted({row.game_date for row in self.logs})
        self.pitchers_by_id = _pitchers_by_id(self.pitcher_ids)
        self.scheduled_games_by_pk = _scheduled_games_by_pk(self.game_pks)
        self.snapshots_by_pitcher_date = _snapshots_by_pitcher_date(
            self.pitcher_ids,
            {*self.log_dates, self.product_date},
        )
        self.pbp_events_by_game_pk = _pbp_events_by_game_pk(self.game_pks)
        self.source_evidence = _source_evidence_cache(self.start_date, self.product_date)
        self._attribution_windows = {}
        self._conflict_windows_recorded = set()

    @property
    def source_evidence_count(self):
        return len(self.source_evidence['rows'])

    @property
    def roster_snapshot_count(self):
        return len(self.snapshots_by_pitcher_date)

    @property
    def pbp_event_count(self):
        return sum(len(rows) for rows in self.pbp_events_by_game_pk.values())

    def attribution_window(self, window_days, *, record_conflicts=False):
        if window_days not in self._attribution_windows:
            self._attribution_windows[window_days] = self._build_attribution_window(window_days)
        window = self._attribution_windows[window_days]
        if record_conflicts and window_days not in self._conflict_windows_recorded:
            for decision in window.decisions:
                if decision.reason_code == REASON_ATTRIBUTION_CONFLICT:
                    _record_attribution_dead_letter(decision, self.sync_run_id)
            self._conflict_windows_recorded.add(window_days)
        return window

    def _build_attribution_window(self, window_days):
        ref = self.product_date
        start = ref - timedelta(days=window_days - 1)
        coverage_window = self.coverage.window(ref, window_days)
        decisions = []
        for log in self.logs:
            if log.game_date < start or log.game_date > ref:
                continue
            if not self.is_finality_certified(log):
                continue
            pitcher = self.pitchers_by_id.get(log.pitcher_id)
            pitcher_name = getattr(pitcher, 'full_name', None) or f'Pitcher {log.pitcher_id}'
            snapshot = self.same_date_snapshot(log)
            current_snapshot = self.current_snapshot(log.pitcher_id)
            if log.games_started is None:
                decisions.append(AttributionDecision(
                    log=log,
                    team_id=_snapshot_team(snapshot, current_snapshot),
                    pitcher_id=log.pitcher_id,
                    pitcher_name=pitcher_name,
                    included=False,
                    reason_code=REASON_APPEARANCE_ROLE_UNKNOWN,
                    snapshot=snapshot,
                    current_snapshot=current_snapshot,
                    pbp_events=(),
                ))
                continue
            if log.games_started != 0:
                continue
            if snapshot is None:
                decisions.append(AttributionDecision(
                    log=log,
                    team_id=_snapshot_team(snapshot, current_snapshot),
                    pitcher_id=log.pitcher_id,
                    pitcher_name=pitcher_name,
                    included=False,
                    reason_code=REASON_ATTRIBUTION_UNKNOWN,
                    snapshot=snapshot,
                    current_snapshot=current_snapshot,
                    pbp_events=(),
                ))
                continue
            pbp_events = tuple(self.pbp_events_for_log(log))
            fielding_team_ids = {
                event.fielding_team_id
                for event in pbp_events
                if event.fielding_team_id is not None
            }
            if fielding_team_ids and snapshot.team_id not in fielding_team_ids:
                decisions.append(AttributionDecision(
                    log=log,
                    team_id=snapshot.team_id,
                    pitcher_id=log.pitcher_id,
                    pitcher_name=pitcher_name,
                    included=False,
                    reason_code=REASON_ATTRIBUTION_CONFLICT,
                    snapshot=snapshot,
                    current_snapshot=current_snapshot,
                    pbp_events=pbp_events,
                ))
                continue
            decisions.append(AttributionDecision(
                log=log,
                team_id=snapshot.team_id,
                pitcher_id=log.pitcher_id,
                pitcher_name=pitcher_name,
                included=True,
                reason_code=None,
                snapshot=snapshot,
                current_snapshot=current_snapshot,
                pbp_events=pbp_events,
            ))
        return AttributionWindow(
            product_date=ref,
            window_days=window_days,
            start_date=start,
            decisions=decisions,
            coverage_window=coverage_window,
        )

    def is_finality_certified(self, log):
        rows = self.scheduled_games_by_pk.get(log.mlb_game_pk, ())
        if not rows:
            return True
        return any(row.status_state == ScheduledGame.STATE_FINAL for row in rows)

    def same_date_snapshot(self, log):
        return self.snapshots_by_pitcher_date.get((log.pitcher_id, log.game_date))

    def current_snapshot(self, pitcher_id):
        return self.snapshots_by_pitcher_date.get((pitcher_id, self.product_date))

    def pbp_events_for_log(self, log):
        pitcher = self.pitchers_by_id.get(log.pitcher_id)
        mlb_id = getattr(pitcher, 'mlb_id', None)
        return [
            event
            for event in self.pbp_events_by_game_pk.get(log.mlb_game_pk, ())
            if event.pitcher_id == log.pitcher_id
            or (mlb_id is not None and event.pitcher_mlb_id == mlb_id)
        ]

    def source_member_evidence(self, rule_id, pitcher_id, product_date):
        return self.source_evidence['member'].get((
            rule_id,
            str(pitcher_id),
            _as_date(product_date),
        ))

    def source_team_window_evidence(self, rule_id, team_id, product_date, window_days):
        rows = self.source_evidence['team'].get((
            rule_id,
            str(team_id),
            _as_date(product_date),
        ), ())
        for row in rows:
            trace = dict(row.computation_trace or {})
            if trace.get('window_days') == window_days:
                return row
            if f'{window_days}d' in (row.subject_key or ''):
                return row
        return None

    def source_appearance_evidence(self, rule_id, log):
        return self.source_evidence['appearance'].get((
            rule_id,
            f'{log.pitcher_id}:{log.mlb_game_pk}',
            log.game_date,
        ))

    def outing_family_ran_for_day(self, day):
        return _as_date(day) in self.source_evidence['outing_family_days']


_LOCAL_RULE_REGISTRY: EvidenceRuleRegistry | None = None
_LOCAL_TEMPLATE_REGISTRY: ClaimTemplateRegistry | None = None


def team_relief_composition_rule_definitions() -> dict[str, str]:
    return dict(_RULE_DEFINITIONS)


def team_relief_composition_rule_ids() -> tuple[str, ...]:
    return TEAM_RELIEF_COMPOSITION_RULE_IDS


def register_team_relief_composition_rules(
    *,
    registry: EvidenceRuleRegistry | None = None,
    template_registry: ClaimTemplateRegistry | None = None,
) -> tuple[EvidenceRuleRegistry, ClaimTemplateRegistry]:
    rule_registry = registry or EvidenceRuleRegistry()
    claim_registry = template_registry or ClaimTemplateRegistry()
    for rule_id in TEAM_RELIEF_COMPOSITION_RULE_IDS:
        _register_team_relief_composition_rule(
            rule_registry,
            _team_relief_composition_rule(rule_id),
        )
        for template in _templates_for_rule(rule_id):
            _register_team_relief_composition_template(claim_registry, template)
    return rule_registry, claim_registry


def build_team_relief_composition_evidence(
    product_date,
    *,
    sync_run_id=None,
    source='manual',
    commit=False,
    restrict_evidence_keys: set[str] | None = None,
) -> dict:
    """Build internal team relief contributor composition evidence."""
    started = time.perf_counter()
    ref = _as_date(product_date)
    registry, templates = _local_registries()
    coverage = _CoverageCache(ref)
    logger.info(
        'Team relief composition build starting: product_date=%s restrict_keys=%s.',
        ref.isoformat(),
        len(restrict_evidence_keys or ()),
    )
    context_started = time.perf_counter()
    context = TeamReliefCompositionBuildContext(ref, coverage, sync_run_id)
    logger.info(
        'Team relief composition context loaded: product_date=%s game_logs=%s '
        'pitchers=%s roster_snapshots=%s pbp_events=%s source_evidence=%s '
        'elapsed_ms=%s.',
        ref.isoformat(),
        len(context.logs),
        len(context.pitcher_ids),
        context.roster_snapshot_count,
        context.pbp_event_count,
        context.source_evidence_count,
        round((time.perf_counter() - context_started) * 1000, 1),
    )
    basis_window = _attribution_window(
        ref,
        BASIS_WINDOW_DAYS,
        coverage,
        sync_run_id,
        record_conflicts=True,
        context=context,
    )
    basis_team_ids = basis_window.team_ids()
    basis_evidence = []
    basis_started = time.perf_counter()

    for team_id in basis_team_ids:
        item = _basis_object(
            team_id=team_id,
            product_date=ref,
            window=basis_window,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
            context=context,
        )
        if item is None:
            continue
        if restrict_evidence_keys is None or item.evidence.evidence_key in restrict_evidence_keys:
            basis_evidence.append(item.evidence)

    basis_statuses = _upsert_evidence_batch(basis_evidence)
    basis_by_team = _current_basis_objects_by_team(basis_team_ids, ref)
    logger.info(
        'Team relief composition basis stage completed: product_date=%s '
        'teams_considered=%s objects_built=%s objects_created=%s '
        'objects_refreshed=%s elapsed_ms=%s.',
        ref.isoformat(),
        len(basis_team_ids),
        len(basis_statuses),
        sum(1 for item in basis_statuses if item == 'created'),
        sum(1 for item in basis_statuses if item == 'refreshed'),
        round((time.perf_counter() - basis_started) * 1000, 1),
    )

    downstream_evidence = []
    downstream_started = time.perf_counter()
    for team_id in sorted(basis_team_ids):
        basis = basis_by_team.get(str(team_id))
        if basis is None:
            continue
        for item in _downstream_objects(
            team_id=team_id,
            product_date=ref,
            basis=basis,
            coverage=coverage,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
            context=context,
        ):
            if restrict_evidence_keys is not None and item.evidence.evidence_key not in restrict_evidence_keys:
                continue
            downstream_evidence.append(item.evidence)

    downstream_statuses = _upsert_evidence_batch(downstream_evidence)
    logger.info(
        'Team relief composition downstream stage completed: product_date=%s '
        'teams_considered=%s objects_built=%s objects_created=%s '
        'objects_refreshed=%s elapsed_ms=%s.',
        ref.isoformat(),
        len(basis_by_team),
        len(downstream_statuses),
        sum(1 for item in downstream_statuses if item == 'created'),
        sum(1 for item in downstream_statuses if item == 'refreshed'),
        round((time.perf_counter() - downstream_started) * 1000, 1),
    )

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    emitted = basis_statuses + downstream_statuses
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        'Team relief composition build completed: product_date=%s '
        'teams_considered=%s objects_built=%s objects_created=%s '
        'objects_refreshed=%s elapsed_ms=%s.',
        ref.isoformat(),
        len(basis_team_ids),
        len(emitted),
        sum(1 for item in emitted if item == 'created'),
        sum(1 for item in emitted if item == 'refreshed'),
        elapsed_ms,
    )
    return {
        'status': 'built',
        'product_date': ref.isoformat(),
        'rules': list(TEAM_RELIEF_COMPOSITION_RULE_IDS),
        'teams_considered': len(basis_team_ids),
        'game_logs_considered': len(context.logs),
        'objects_built': len(emitted),
        'objects_created': sum(1 for item in emitted if item == 'created'),
        'objects_refreshed': sum(1 for item in emitted if item == 'refreshed'),
        'basis_stage_completed': True,
        'downstream_stage_completed': True,
        'elapsed_ms': elapsed_ms,
    }


def mark_game_log_correction_for_team_relief_composition(
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


def mark_roster_status_snapshot_correction_for_team_relief_composition(
    roster_status_snapshot,
    *,
    sync_run_id=None,
    reason_code=REASON_ROSTER_SNAPSHOT_CORRECTED,
    batch_size=100,
) -> dict:
    if roster_status_snapshot is None or getattr(roster_status_snapshot, 'id', None) is None:
        return {'marked_count': 0, 'evidence_ids': []}
    return mark_dependent_evidence_for_recompute(
        source_table='roster_status_snapshots',
        source_pk=roster_status_snapshot.id,
        reason_code=reason_code,
        batch_size=batch_size,
        sync_run_id=sync_run_id,
    )


def mark_source_evidence_supersession_for_team_relief_composition(
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


def mark_basis_supersession_for_team_relief_composition(
    evidence_object,
    *,
    sync_run_id=None,
    reason_code=REASON_BASIS_SUPERSEDED,
    batch_size=100,
) -> dict:
    if evidence_object is None or getattr(evidence_object, 'id', None) is None:
        return {'marked_count': 0, 'evidence_ids': []}
    if evidence_object.rule_id != TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID:
        return {'marked_count': 0, 'evidence_ids': []}
    return mark_dependent_evidence_for_recompute(
        source_table='evidence_objects',
        source_pk=evidence_object.id,
        reason_code=reason_code,
        batch_size=batch_size,
        sync_run_id=sync_run_id,
        correction_source='composition_basis_supersession',
    )


def rebuild_marked_team_relief_composition_evidence(
    *,
    sync_run_id=None,
    source='manual',
    batch_size=100,
) -> dict:
    rows = (
        EvidenceObject.query
        .filter(EvidenceObject.rule_id.in_(TEAM_RELIEF_COMPOSITION_RULE_IDS))
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_NEEDED)
        .order_by(
            asc(EvidenceObject.product_date),
            asc(EvidenceObject.rule_id),
            asc(EvidenceObject.id),
        )
        .limit(batch_size)
        .all()
    )
    if not rows:
        return {
            'status': 'noop',
            'objects_rebuilt': 0,
            'dates_rebuilt': [],
            'basis_first': True,
        }

    basis_rows = [
        row for row in rows if row.rule_id == TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID
    ]
    dependent_rows = [
        row for row in rows if row.rule_id != TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID
    ]

    rebuilt = 0
    order = []
    for evidence_date, keys in _keys_by_date(basis_rows).items():
        result = build_team_relief_composition_evidence(
            evidence_date,
            sync_run_id=sync_run_id,
            source=source,
            restrict_evidence_keys=keys,
        )
        rebuilt += result['objects_created'] + result['objects_refreshed']
        order.append('basis')

    for row in basis_rows:
        mark_basis_supersession_for_team_relief_composition(
            row,
            sync_run_id=sync_run_id,
            batch_size=batch_size,
        )

    newly_marked_dependents = (
        EvidenceObject.query
        .filter(EvidenceObject.rule_id.in_(TEAM_RELIEF_COMPOSITION_RULE_IDS[1:]))
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_NEEDED)
        .order_by(asc(EvidenceObject.product_date), asc(EvidenceObject.id))
        .limit(batch_size)
        .all()
    )
    dependent_by_key = {row.evidence_key: row for row in dependent_rows}
    for row in newly_marked_dependents:
        dependent_by_key[row.evidence_key] = row

    for evidence_date, keys in _keys_by_date(dependent_by_key.values()).items():
        result = build_team_relief_composition_evidence(
            evidence_date,
            sync_run_id=sync_run_id,
            source=source,
            restrict_evidence_keys=keys,
        )
        rebuilt += result['objects_created'] + result['objects_refreshed']
        order.append('dependents')

    db.session.flush()
    dates = {row.product_date for row in rows}
    dates.update(row.product_date for row in newly_marked_dependents)
    return {
        'status': 'rebuilt',
        'objects_rebuilt': rebuilt,
        'dates_rebuilt': [day.isoformat() for day in sorted(dates)],
        'basis_first': True,
        'rebuild_order': order,
    }


def assert_team_relief_composition_language_allowed(text: str) -> bool:
    return _assert_text_has_no_team_relief_composition_forbidden_terms(text)


def _local_registries():
    global _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY
    if _LOCAL_RULE_REGISTRY is None or _LOCAL_TEMPLATE_REGISTRY is None:
        _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY = register_team_relief_composition_rules()
    return _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY


def _team_relief_composition_rule(rule_id):
    return EvidenceRule(
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        evidence_type=rule_id,
        plain_language_definition=_RULE_DEFINITIONS[rule_id],
        required_input_families=_REQUIRED_INPUT_FAMILIES[rule_id],
        required_cited_fields=_REQUIRED_FIELDS[rule_id],
        posture_default=EvidenceObject.POSTURE_INTERNAL_ONLY,
        thresholds=_RULE_THRESHOLDS.get(rule_id, {}),
    )


def _register_team_relief_composition_rule(registry, rule):
    if rule.posture_default != EvidenceObject.POSTURE_INTERNAL_ONLY:
        raise EvidenceRuleError('team relief contributor composition evidence must remain internal_only')
    _assert_text_has_no_team_relief_composition_forbidden_terms(rule.rule_id)
    _assert_text_has_no_team_relief_composition_forbidden_terms(rule.evidence_type)
    return registry.register(rule)


def _register_team_relief_composition_template(registry, template):
    _assert_text_has_no_team_relief_composition_forbidden_terms(template.template_text)
    return registry.register(template)


def _templates_for_rule(rule_id):
    templates = [
        ClaimTemplate(
            template_id=_template_id(rule_id),
            template_version=RULE_VERSION,
            template_text='{claim}',
        ),
        ClaimTemplate(
            template_id=_template_id(rule_id, degraded=True),
            template_version=RULE_VERSION,
            template_text='{claim}',
        ),
    ]
    if rule_id == TEAM_RELIEF_WORKLOAD_CONCENTRATION_RULE_ID:
        for window_days in CONCENTRATION_WINDOW_DAYS:
            templates.extend([
                ClaimTemplate(
                    template_id=_template_id(rule_id, window_days=window_days),
                    template_version=RULE_VERSION,
                    template_text='{claim}',
                ),
                ClaimTemplate(
                    template_id=_template_id(rule_id, window_days=window_days, degraded=True),
                    template_version=RULE_VERSION,
                    template_text='{claim}',
                ),
            ])
    elif rule_id == TEAM_RELIEF_OUTING_CONTEXT_MIX_RULE_ID:
        templates.extend([
            ClaimTemplate(
                template_id=_template_id(rule_id, window_days=OUTING_CONTEXT_WINDOW_DAYS),
                template_version=RULE_VERSION,
                template_text='{claim}',
            ),
            ClaimTemplate(
                template_id=_template_id(
                    rule_id,
                    window_days=OUTING_CONTEXT_WINDOW_DAYS,
                    degraded=True,
                ),
                template_version=RULE_VERSION,
                template_text='{claim}',
            ),
        ])
    elif rule_id in (
        TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID,
        TEAM_RELIEF_REST_DISTRIBUTION_RULE_ID,
        TEAM_RELIEF_DENSITY_USAGE_COUNT_RULE_ID,
        TEAM_RELIEF_FINISH_SPREAD_RULE_ID,
    ):
        window_days = BASIS_WINDOW_DAYS
        templates.extend([
            ClaimTemplate(
                template_id=_template_id(rule_id, window_days=window_days),
                template_version=RULE_VERSION,
                template_text='{claim}',
            ),
            ClaimTemplate(
                template_id=_template_id(rule_id, window_days=window_days, degraded=True),
                template_version=RULE_VERSION,
                template_text='{claim}',
            ),
        ])
    return tuple(templates)


def _downstream_objects(
    *,
    team_id,
    product_date,
    basis,
    coverage,
    registry,
    templates,
    sync_run_id,
    source,
    context=None,
):
    items = [
        _rest_distribution_object(team_id, product_date, basis, registry, templates, sync_run_id, source, context),
        _density_usage_count_object(team_id, product_date, basis, registry, templates, sync_run_id, source, context),
        _outing_context_mix_object(team_id, product_date, basis, coverage, registry, templates, sync_run_id, source, context),
        _finish_spread_object(team_id, product_date, basis, registry, templates, sync_run_id, source, context),
    ]
    for window_days in CONCENTRATION_WINDOW_DAYS:
        items.append(
            _workload_concentration_object(
                team_id,
                product_date,
                window_days,
                basis,
                coverage,
                registry,
                templates,
                sync_run_id,
                source,
                context,
            )
        )
    return [item for item in items if item is not None]


def _basis_object(
    *,
    team_id,
    product_date,
    window,
    registry,
    templates,
    sync_run_id,
    source,
    context=None,
):
    included = window.included_for_team(team_id)
    exclusions = window.exclusions_for_team(team_id)
    if not included and not exclusions:
        return None

    members = _members_from_decisions(included)
    relationships = _current_roster_relationships(members, team_id, product_date, context)
    counts = Counter(item['relationship'] for item in relationships)
    exclusion_counts = Counter(item.reason_code for item in exclusions if item.reason_code)
    reason_codes = _dedupe(
        list(exclusion_counts)
        + window.lower_bound_reasons()
        + ([REASON_ROSTER_MEMBERSHIP_UNKNOWN] if counts.get('unknown') else [])
    )
    citations = []
    citations.extend(window.coverage_window.coverage_citations())
    for decision in included + exclusions:
        citations.extend(_decision_citations(decision))

    lower_bound = bool(window.lower_bound_reasons() or exclusions)
    state = (
        EvidenceObject.COMPLETENESS_PARTIAL
        if lower_bound or reason_codes
        else EvidenceObject.COMPLETENESS_COMPLETE
    )
    claim = _basis_claim(
        team_id=team_id,
        product_date=product_date,
        member_count=len(members),
        relationships=counts,
        exclusions=exclusion_counts,
        lower_bound=lower_bound,
    )
    trace = {
        'steps': [
            'Built the 14-day product-date window.',
            'Required finality-certified game-log relief appearances.',
            'Attributed appearances by same-date roster snapshot authority.',
            'Read play-by-play fielding team only as corroboration where events exist.',
            'Built the downstream denominator basis before composing dependent evidence.',
        ],
        'product_date': product_date.isoformat(),
        'window_days': window.window_days,
        'window_start': window.start_date.isoformat(),
        'team_id': team_id,
        'members': members,
        'current_roster_relationships': relationships,
        'excluded_appearances_by_reason': dict(sorted(exclusion_counts.items())),
        'attribution_decisions': [_decision_trace(item) for item in included + exclusions],
        'basis_lower_bound': lower_bound,
        'denominator_disclaimer': BASIS_DISCLAIMER,
        'incomplete_slate_days': window.coverage_window.incomplete_day_labels,
    }
    input_values = {
        'game_logs.games_started': _first_decision_value(included + exclusions, 'games_started', 0),
        'roster_status_snapshots.team_id': team_id,
        'slate_coverage.slate_date': product_date.isoformat(),
    }
    return _build_object(
        rule_id=TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix='basis-14d',
        claim=claim,
        cited_inputs=tuple(citations),
        input_values=input_values,
        trace=trace,
        state=state,
        reason_codes=reason_codes,
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
        window_days=BASIS_WINDOW_DAYS,
        degraded=state != EvidenceObject.COMPLETENESS_COMPLETE,
        limitations=([LOWER_BOUND_LIMITATION] if lower_bound else []),
    )


def _rest_distribution_object(team_id, product_date, basis, registry, templates, sync_run_id, source, context=None):
    members = _basis_members(basis)
    if not members:
        return None
    citations = [_source_evidence_citation(basis, 'composition_basis')]
    buckets = {'0': [], '1': [], '2': [], '3+': [], 'unknown': []}
    reason_codes = list(basis.reason_codes or [])
    consumed = []
    for member in members:
        row = _source_member_evidence(
            WORKLOAD_DAYS_OF_REST_RULE_ID,
            member['pitcher_id'],
            product_date,
            context,
        )
        if row is None:
            buckets['unknown'].append(member)
            reason_codes.append(REASON_MEMBER_EVIDENCE_UNAVAILABLE)
            citations.append(_missing_member_evidence_citation(
                WORKLOAD_DAYS_OF_REST_RULE_ID,
                member['pitcher_id'],
                product_date,
                'excluded_input',
            ))
            continue
        citations.append(_source_evidence_citation(row, 'derived_from_evidence'))
        consumed.append(_source_ref(row))
        if row.completeness_state == EvidenceObject.COMPLETENESS_CONFLICT:
            buckets['unknown'].append(member)
            reason_codes.append(REASON_MEMBER_EVIDENCE_CONFLICT)
            continue
        days = _rest_days_from_evidence(row)
        if row.completeness_state != EvidenceObject.COMPLETENESS_COMPLETE or days is None:
            buckets['unknown'].append(member)
            reason_codes.append(REASON_MEMBER_EVIDENCE_UNAVAILABLE)
            continue
        buckets[_rest_bucket(days)].append(member)
    state = (
        EvidenceObject.COMPLETENESS_PARTIAL
        if _dedupe(reason_codes)
        else EvidenceObject.COMPLETENESS_COMPLETE
    )
    claim = (
        f'Team {team_id} contributor rest distribution for the 14-day basis set on '
        f'{product_date.isoformat()}: 0 days {len(buckets["0"])}, 1 day '
        f'{len(buckets["1"])}, 2 days {len(buckets["2"])}, 3+ days '
        f'{len(buckets["3+"])}, unknown {len(buckets["unknown"])}.'
    )
    trace = {
        'steps': [
            'Read the composition basis object.',
            'Consumed stored workload_days_of_rest evidence for each basis member.',
            'Counted missing, unknown, and conflicted member evidence in the unknown bucket.',
        ],
        'team_id': team_id,
        'basis': _source_ref(basis),
        'members': members,
        'buckets': {key: _member_labels(value) for key, value in buckets.items()},
        'consumed_evidence': consumed,
    }
    return _build_object(
        rule_id=TEAM_RELIEF_REST_DISTRIBUTION_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix='rest-distribution-14d',
        claim=claim,
        cited_inputs=tuple(citations),
        input_values={
            'phase0d_evidence_contract.rule_id': basis.rule_id,
            'phase0d_evidence_contract.completeness_state': basis.completeness_state,
        },
        trace=trace,
        state=state,
        reason_codes=_dedupe(reason_codes),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
        window_days=REST_WINDOW_DAYS,
        degraded=state != EvidenceObject.COMPLETENESS_COMPLETE,
    )


def _density_usage_count_object(team_id, product_date, basis, registry, templates, sync_run_id, source, context=None):
    members = _basis_members(basis)
    if not members:
        return None
    citations = [_source_evidence_citation(basis, 'composition_basis')]
    pattern_ids = (
        USAGE_BACK_TO_BACK_RULE_ID,
        USAGE_THREE_IN_FOUR_RULE_ID,
        USAGE_FOUR_IN_SIX_RULE_ID,
    )
    pattern_counts = {}
    consumed = []
    reason_codes = list(basis.reason_codes or [])
    for rule_id in pattern_ids:
        present = []
        unassessable = []
        absent = []
        for member in members:
            row = _source_member_evidence(rule_id, member['pitcher_id'], product_date, context)
            if row is None:
                absent.append(member)
                continue
            citations.append(_source_evidence_citation(row, 'derived_from_evidence'))
            consumed.append(_source_ref(row))
            if row.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE:
                present.append(member)
            else:
                unassessable.append(member)
                reason_codes.append(REASON_MEMBER_EVIDENCE_UNAVAILABLE)
        pattern_counts[rule_id] = {
            'present': present,
            'absent': absent,
            'unassessable': unassessable,
        }
    state = (
        EvidenceObject.COMPLETENESS_PARTIAL
        if _dedupe(reason_codes)
        else EvidenceObject.COMPLETENESS_COMPLETE
    )
    claim = (
        f'Team {team_id} contributor density usage counts for the 14-day basis set on '
        f'{product_date.isoformat()}: back-to-back {len(pattern_counts[USAGE_BACK_TO_BACK_RULE_ID]["present"])}, '
        f'three-in-four {len(pattern_counts[USAGE_THREE_IN_FOUR_RULE_ID]["present"])}, '
        f'four-in-six {len(pattern_counts[USAGE_FOUR_IN_SIX_RULE_ID]["present"])}, '
        f'unassessable member-pattern pairs {sum(len(value["unassessable"]) for value in pattern_counts.values())}.'
    )
    trace = {
        'steps': [
            'Read the composition basis object.',
            'Consumed stored 0D-02 density pattern evidence by member.',
            'Kept present, absent, and unassessable pattern states separate.',
        ],
        'team_id': team_id,
        'basis': _source_ref(basis),
        'patterns': {
            rule_id: {
                key: _member_labels(value)
                for key, value in payload.items()
            }
            for rule_id, payload in pattern_counts.items()
        },
        'consumed_evidence': consumed,
        'locked_band_rule_ids_consumed': [],
    }
    return _build_object(
        rule_id=TEAM_RELIEF_DENSITY_USAGE_COUNT_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix='density-usage-count-14d',
        claim=claim,
        cited_inputs=tuple(citations),
        input_values={
            'phase0d_evidence_contract.rule_id': basis.rule_id,
            'phase0d_evidence_contract.completeness_state': basis.completeness_state,
        },
        trace=trace,
        state=state,
        reason_codes=_dedupe(reason_codes),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
        window_days=DENSITY_WINDOW_DAYS,
        degraded=state != EvidenceObject.COMPLETENESS_COMPLETE,
    )


def _workload_concentration_object(
    team_id,
    product_date,
    window_days,
    basis,
    coverage,
    registry,
    templates,
    sync_run_id,
    source,
    context=None,
):
    window = _attribution_window(product_date, window_days, coverage, sync_run_id, context=context)
    included = window.included_for_team(team_id)
    if not included:
        return None
    exclusions = window.exclusions_for_team(team_id)
    members = _basis_members(basis)
    member_ids = {member['pitcher_id'] for member in members}
    per_pitcher = defaultdict(int)
    per_pitcher_names = {}
    citations = [_source_evidence_citation(basis, 'composition_basis')]
    for decision in included:
        if decision.pitcher_id not in member_ids:
            continue
        outs = decision.log.innings_pitched_outs or 0
        per_pitcher[decision.pitcher_id] += outs
        per_pitcher_names[decision.pitcher_id] = decision.pitcher_name
        citations.append(_game_log_citation(
            decision.log,
            ('innings_pitched_outs', 'games_started', 'mlb_game_pk', 'game_date'),
        ))
    for decision in exclusions:
        citations.extend(_decision_citations(decision))

    total_outs = sum(per_pitcher.values())
    ordered = sorted(per_pitcher.items(), key=lambda item: (-item[1], item[0]))
    top_one = ordered[:1]
    top_three = ordered[:3]
    top_one_outs = sum(value for _, value in top_one)
    top_three_outs = sum(value for _, value in top_three)
    reason_codes = _dedupe(list(basis.reason_codes or []) + window.lower_bound_reasons())
    if exclusions:
        reason_codes.append(REASON_SHARE_EXCLUSION_PRESENT)
    split_source = _source_team_window_evidence(
        TEAM_BULLPEN_OUTS_WINDOW_RULE_ID,
        team_id,
        product_date,
        window_days,
        context,
    )
    contradiction = None
    if split_source is not None:
        citations.append(_source_evidence_citation(split_source, 'derived_from_evidence'))
        split_total = _bullpen_outs_from_evidence(split_source)
        if not exclusions and split_total is not None and split_total != total_outs:
            contradiction = {
                'local_relief_outs': total_outs,
                'source_relief_outs': split_total,
                'window_days': window_days,
            }
            reason_codes.append(REASON_CONCENTRATION_CORROBORATION_MISMATCH)
            _record_concentration_dead_letter(
                team_id=team_id,
                product_date=product_date,
                window_days=window_days,
                contradiction=contradiction,
                sync_run_id=sync_run_id,
            )

    if contradiction is not None:
        state = EvidenceObject.COMPLETENESS_CONFLICT
        claim = (
            f'Team {team_id} relief out concentration has a corroboration mismatch '
            f'over the {window_days}-day window ending {product_date.isoformat()}: '
            f'local cited outs {total_outs}, source cited outs {contradiction["source_relief_outs"]}.'
        )
    elif exclusions or window.lower_bound_reasons() or basis.completeness_state != EvidenceObject.COMPLETENESS_COMPLETE:
        state = EvidenceObject.COMPLETENESS_PARTIAL
        claim = (
            f'Team {team_id} relief contributors recorded at least {total_outs} outs '
            f'over the {window_days}-day window ending {product_date.isoformat()}; '
            f'largest contributor {top_one_outs} outs, three largest contributors '
            f'{top_three_outs} outs across a {len(members)}-member contributor set; '
            'shares unknown because an exclusion is present.'
        )
        if REASON_SHARE_EXCLUSION_PRESENT not in reason_codes:
            reason_codes.append(REASON_SHARE_EXCLUSION_PRESENT)
    else:
        state = EvidenceObject.COMPLETENESS_COMPLETE
        top_one_share = _share(top_one_outs, total_outs)
        top_three_share = _share(top_three_outs, total_outs)
        claim = (
            f'Team {team_id} relief contributors recorded {total_outs} outs over the '
            f'{window_days}-day window ending {product_date.isoformat()}; largest '
            f'contributor {top_one_outs} outs ({top_one_share}), three largest '
            f'contributors {top_three_outs} outs ({top_three_share}) across a '
            f'{len(members)}-member contributor set.'
        )
    trace = {
        'steps': [
            'Read the composition basis object.',
            'Computed relief out sums from attributed game-log rows.',
            'Cross-checked stored team bullpen outs evidence when present.',
            'Stated shares only when all window appearances were attributed and complete.',
        ],
        'team_id': team_id,
        'window_days': window_days,
        'basis': _source_ref(basis),
        'per_pitcher_outs': [
            {
                'pitcher_id': pitcher_id,
                'pitcher_name': per_pitcher_names.get(pitcher_id),
                'outs': outs,
            }
            for pitcher_id, outs in ordered
        ],
        'total_outs': total_outs,
        'top_one_outs': top_one_outs,
        'top_three_outs': top_three_outs,
        'member_count': len(members),
        'share_state': 'unknown' if state != EvidenceObject.COMPLETENESS_COMPLETE else 'complete',
        'exclusion_accounting': [_decision_trace(item) for item in exclusions],
        'corroboration': _source_ref(split_source) if split_source is not None else None,
        'contradiction': contradiction,
    }
    return _build_object(
        rule_id=TEAM_RELIEF_WORKLOAD_CONCENTRATION_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix=f'workload-concentration-{window_days}d',
        claim=claim,
        cited_inputs=tuple(citations),
        input_values={
            'game_logs.innings_pitched_outs': total_outs,
            'phase0d_evidence_contract.rule_id': basis.rule_id,
            'phase0d_evidence_contract.completeness_state': basis.completeness_state,
        },
        trace=trace,
        state=state,
        reason_codes=_dedupe(reason_codes),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
        window_days=window_days,
        degraded=state != EvidenceObject.COMPLETENESS_COMPLETE,
        contradictions=(contradiction,) if contradiction is not None else (),
        limitations=([LOWER_BOUND_LIMITATION] if state == EvidenceObject.COMPLETENESS_PARTIAL else []),
    )


def _outing_context_mix_object(team_id, product_date, basis, coverage, registry, templates, sync_run_id, source, context=None):
    window = _attribution_window(
        product_date,
        OUTING_CONTEXT_WINDOW_DAYS,
        coverage,
        sync_run_id,
        context=context,
    )
    included = window.included_for_team(team_id)
    if not included:
        return None
    citations = [_source_evidence_citation(basis, 'composition_basis')]
    member_ids = {member['pitcher_id'] for member in _basis_members(basis)}
    included = [item for item in included if item.pitcher_id in member_ids]
    for decision in included:
        citations.append(_game_log_citation(
            decision.log,
            ('mlb_game_pk', 'games_started', 'game_date'),
        ))
    ran_gap_days = [
        day for day in sorted({item.log.game_date for item in included})
        if not _outing_family_ran_for_day(day, context)
    ]
    reason_codes = list(basis.reason_codes or [])
    if ran_gap_days:
        reason_codes.append(REASON_OUTING_FAMILY_COVERAGE_GAP)
        claim = (
            f'Team {team_id} outing context mix is unknown for the 7-day window ending '
            f'{product_date.isoformat()}; the source family did not run for every cited date.'
        )
        trace = {
            'steps': [
                'Read the composition basis object.',
                'Checked 0D-04 source-family run presence for each cited date.',
                'Withheld arithmetic because the source-family coverage gate failed.',
            ],
            'team_id': team_id,
            'window_days': OUTING_CONTEXT_WINDOW_DAYS,
            'basis': _source_ref(basis),
            'gap_days': [day.isoformat() for day in ran_gap_days],
            'partial_arithmetic_performed': False,
        }
        return _build_object(
            rule_id=TEAM_RELIEF_OUTING_CONTEXT_MIX_RULE_ID,
            team_id=team_id,
            product_date=product_date,
            subject_suffix='outing-context-mix-7d',
            claim=claim,
            cited_inputs=tuple(citations),
            input_values={
                'game_logs.mlb_game_pk': included[0].log.mlb_game_pk if included else product_date.isoformat(),
                'phase0d_evidence_contract.rule_id': basis.rule_id,
                'phase0d_evidence_contract.completeness_state': basis.completeness_state,
            },
            trace=trace,
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=_dedupe(reason_codes),
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
            window_days=OUTING_CONTEXT_WINDOW_DAYS,
            degraded=True,
        )

    counts = {'clean': [], 'traffic': [], 'unknown': [], 'provably_neither': []}
    consumed = []
    for decision in included:
        rows = _outing_context_objects(decision.log, context)
        for row in rows:
            citations.append(_source_evidence_citation(row, 'derived_from_evidence'))
            consumed.append(_source_ref(row))
        rule_ids = {row.rule_id for row in rows}
        if OUTING_CLEAN_RULE_ID in rule_ids:
            counts['clean'].append(decision)
        elif OUTING_TRAFFIC_RULE_ID in rule_ids:
            counts['traffic'].append(decision)
        elif OUTING_CONTEXT_UNKNOWN_RULE_ID in rule_ids:
            counts['unknown'].append(decision)
        else:
            counts['provably_neither'].append(decision)
    if basis.completeness_state != EvidenceObject.COMPLETENESS_COMPLETE:
        state = EvidenceObject.COMPLETENESS_PARTIAL
    else:
        state = EvidenceObject.COMPLETENESS_COMPLETE
    claim = (
        f'Team {team_id} outing context mix over the 7-day window ending '
        f'{product_date.isoformat()}: clean {len(counts["clean"])}, traffic '
        f'{len(counts["traffic"])}, unknown {len(counts["unknown"])}, '
        f'provably neither {len(counts["provably_neither"])}.'
    )
    trace = {
        'steps': [
            'Read the composition basis object.',
            'Consumed stored 0D-04 outing context evidence by appearance.',
            'Counted appearances with no 0D-04 object as provably neither only after the coverage gate passed.',
        ],
        'team_id': team_id,
        'window_days': OUTING_CONTEXT_WINDOW_DAYS,
        'basis': _source_ref(basis),
        'counts': {key: [_decision_trace(item) for item in value] for key, value in counts.items()},
        'consumed_evidence': consumed,
        'partial_arithmetic_performed': False,
        'emission_policy_dependency': '0D-04 absence after family run means provably neither',
    }
    return _build_object(
        rule_id=TEAM_RELIEF_OUTING_CONTEXT_MIX_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix='outing-context-mix-7d',
        claim=claim,
        cited_inputs=tuple(citations),
        input_values={
            'game_logs.mlb_game_pk': included[0].log.mlb_game_pk if included else product_date.isoformat(),
            'phase0d_evidence_contract.rule_id': basis.rule_id,
            'phase0d_evidence_contract.completeness_state': basis.completeness_state,
        },
        trace=trace,
        state=state,
        reason_codes=_dedupe(reason_codes),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
        window_days=OUTING_CONTEXT_WINDOW_DAYS,
        degraded=state != EvidenceObject.COMPLETENESS_COMPLETE,
    )


def _finish_spread_object(team_id, product_date, basis, registry, templates, sync_run_id, source, context=None):
    members = _basis_members(basis)
    if not members:
        return None
    member_ids = {member['pitcher_id'] for member in members}
    start = product_date - timedelta(days=FINISH_SPREAD_WINDOW_DAYS - 1)
    decisions = [
        item
        for item in _attribution_window(
            product_date,
            FINISH_SPREAD_WINDOW_DAYS,
            context.coverage if context is not None else _CoverageCache(product_date),
            sync_run_id,
            context=context,
        ).included_for_team(team_id)
        if item.pitcher_id in member_ids and start <= item.log.game_date <= product_date
    ]
    if not decisions:
        return None
    citations = [_source_evidence_citation(basis, 'composition_basis')]
    reason_codes = list(basis.reason_codes or [])
    finished = {}
    save_situation = {}
    saves = {}
    holds = {}
    blown_saves = {}
    games_finished_unknown = []
    consumed = []
    legacy_caveat = False
    for decision in decisions:
        row = _appearance_finish_context_object(decision.log, context)
        if row is None:
            reason_codes.append(REASON_MEMBER_EVIDENCE_UNAVAILABLE)
            citations.append(_missing_member_evidence_citation(
                APPEARANCE_FINISH_CONTEXT_RULE_ID,
                decision.pitcher_id,
                decision.log.game_date,
                'excluded_input',
                appearance_key=decision.appearance_key,
            ))
            games_finished_unknown.append(decision)
            continue
        citations.append(_source_evidence_citation(row, 'derived_from_evidence'))
        consumed.append(_source_ref(row))
        values = _finish_values_from_evidence(row)
        if REASON_LEGACY_ROW_DEFAULT_FALSE_CAVEAT in (row.reason_codes or []) or any(
            REASON_LEGACY_ROW_DEFAULT_FALSE_CAVEAT in str(item)
            for item in (row.limitations or [])
        ):
            legacy_caveat = True
        if row.completeness_state != EvidenceObject.COMPLETENESS_COMPLETE:
            games_finished_unknown.append(decision)
            reason_codes.append(REASON_MEMBER_EVIDENCE_UNAVAILABLE)
            continue
        if values.get('games_finished') is None:
            games_finished_unknown.append(decision)
        elif bool(values.get('games_finished')):
            finished[decision.pitcher_id] = decision.pitcher_name
        if bool(values.get('save_situation')):
            save_situation[decision.pitcher_id] = decision.pitcher_name
        if bool(values.get('save')):
            saves[decision.pitcher_id] = decision.pitcher_name
        if bool(values.get('hold')):
            holds[decision.pitcher_id] = decision.pitcher_name
        if bool(values.get('blown_save')):
            blown_saves[decision.pitcher_id] = decision.pitcher_name
    if legacy_caveat:
        reason_codes.append(REASON_LEGACY_ROW_DEFAULT_FALSE_CAVEAT)
    state = (
        EvidenceObject.COMPLETENESS_PARTIAL
        if _dedupe(reason_codes)
        else EvidenceObject.COMPLETENESS_COMPLETE
    )
    claim = (
        f'Team {team_id} finish spread over the 14-day basis set on '
        f'{product_date.isoformat()}: finished a game {len(finished)}, save '
        f'opportunity {len(save_situation)}, save {len(saves)}, hold {len(holds)}, '
        f'blown save {len(blown_saves)}, games-finished unknown '
        f'{len(games_finished_unknown)}.'
    )
    trace = {
        'steps': [
            'Read the composition basis object.',
            'Consumed stored per-appearance finish-context evidence only.',
            'Counted distinct basis members by finish fact.',
            'Did not consume floored 0D-07 observation evidence.',
        ],
        'team_id': team_id,
        'basis': _source_ref(basis),
        'distinct_pitchers': {
            'games_finished': finished,
            'save_situation': save_situation,
            'save': saves,
            'hold': holds,
            'blown_save': blown_saves,
        },
        'games_finished_unknown': [_decision_trace(item) for item in games_finished_unknown],
        'consumed_evidence': consumed,
        'floored_observation_rule_ids_consumed': [],
        'legacy_caveat_carried': legacy_caveat,
    }
    return _build_object(
        rule_id=TEAM_RELIEF_FINISH_SPREAD_RULE_ID,
        team_id=team_id,
        product_date=product_date,
        subject_suffix='finish-spread-14d',
        claim=claim,
        cited_inputs=tuple(citations),
        input_values={
            'phase0d_evidence_contract.rule_id': basis.rule_id,
            'phase0d_evidence_contract.completeness_state': basis.completeness_state,
        },
        trace=trace,
        state=state,
        reason_codes=_dedupe(reason_codes),
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
        window_days=FINISH_SPREAD_WINDOW_DAYS,
        degraded=state != EvidenceObject.COMPLETENESS_COMPLETE,
        limitations=([LEGACY_FINISH_LIMITATION] if legacy_caveat else []),
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
    state=EvidenceObject.COMPLETENESS_COMPLETE,
    reason_codes=(),
    window_days=None,
    degraded=False,
    contradictions=(),
    limitations=(),
):
    rule = registry.get(rule_id, RULE_VERSION)
    _assert_text_has_no_team_relief_composition_forbidden_terms(claim)
    template = templates.get(
        _template_id(rule_id, window_days=window_days, degraded=degraded)
    )
    evidence = build_evidence_object(
        rule_id=rule.rule_id,
        rule_version=RULE_VERSION,
        claim_template=template,
        claim_values={'claim': claim},
        subject_type=SUBJECT_TEAM,
        subject_id=team_id,
        subject_key=f'team:{team_id}:{subject_suffix}',
        product_date=product_date,
        cited_inputs=tuple(cited_inputs),
        computation_trace=trace,
        input_values=dict(input_values or {}),
        readiness_payload=_readiness_payload(rule.required_input_families),
        limitations=tuple(limitations or ()),
        contradictions=tuple(contradictions or ()),
        registry=registry,
        sync_run_id=sync_run_id,
        source=EVIDENCE_SOURCE if source in (None, 'manual') else f'{EVIDENCE_SOURCE}:{source}',
    )
    if state != EvidenceObject.COMPLETENESS_COMPLETE or reason_codes:
        evidence.completeness_state = state
        evidence.reason_codes = _dedupe(reason_codes or [])
        evidence.rendered_claim = claim
    if evidence.posture != EvidenceObject.POSTURE_INTERNAL_ONLY:
        raise EvidenceRuleError('team relief contributor composition evidence must remain internal_only')
    return BuiltTeamReliefCompositionEvidence(
        evidence=evidence,
        rule_id=rule_id,
        subject_key=evidence.subject_key,
    )


def _attribution_window(
    product_date,
    window_days,
    coverage,
    sync_run_id,
    *,
    record_conflicts=False,
    context=None,
):
    if context is not None:
        return context.attribution_window(
            window_days,
            record_conflicts=record_conflicts,
        )
    ref = _as_date(product_date)
    start = ref - timedelta(days=window_days - 1)
    logs = _logs_for_range(start, ref)
    coverage_window = coverage.window(ref, window_days)
    decisions = []
    for log in logs:
        if not _is_finality_certified(log):
            continue
        pitcher = _pitcher_row(log.pitcher_id)
        pitcher_name = getattr(pitcher, 'full_name', None) or f'Pitcher {log.pitcher_id}'
        snapshot = _same_date_snapshot(log)
        current_snapshot = _current_snapshot(log.pitcher_id, ref)
        if log.games_started is None:
            decisions.append(AttributionDecision(
                log=log,
                team_id=_snapshot_team(snapshot, current_snapshot),
                pitcher_id=log.pitcher_id,
                pitcher_name=pitcher_name,
                included=False,
                reason_code=REASON_APPEARANCE_ROLE_UNKNOWN,
                snapshot=snapshot,
                current_snapshot=current_snapshot,
                pbp_events=(),
            ))
            continue
        if log.games_started != 0:
            continue
        if snapshot is None:
            decisions.append(AttributionDecision(
                log=log,
                team_id=_snapshot_team(snapshot, current_snapshot),
                pitcher_id=log.pitcher_id,
                pitcher_name=pitcher_name,
                included=False,
                reason_code=REASON_ATTRIBUTION_UNKNOWN,
                snapshot=snapshot,
                current_snapshot=current_snapshot,
                pbp_events=(),
            ))
            continue
        pbp_events = tuple(_pbp_events_for_log(log))
        fielding_team_ids = {
            event.fielding_team_id
            for event in pbp_events
            if event.fielding_team_id is not None
        }
        if fielding_team_ids and snapshot.team_id not in fielding_team_ids:
            decision = AttributionDecision(
                log=log,
                team_id=snapshot.team_id,
                pitcher_id=log.pitcher_id,
                pitcher_name=pitcher_name,
                included=False,
                reason_code=REASON_ATTRIBUTION_CONFLICT,
                snapshot=snapshot,
                current_snapshot=current_snapshot,
                pbp_events=pbp_events,
            )
            decisions.append(decision)
            if record_conflicts:
                _record_attribution_dead_letter(decision, sync_run_id)
            continue
        decisions.append(AttributionDecision(
            log=log,
            team_id=snapshot.team_id,
            pitcher_id=log.pitcher_id,
            pitcher_name=pitcher_name,
            included=True,
            reason_code=None,
            snapshot=snapshot,
            current_snapshot=current_snapshot,
            pbp_events=pbp_events,
        ))
    return AttributionWindow(
        product_date=ref,
        window_days=window_days,
        start_date=start,
        decisions=decisions,
        coverage_window=coverage_window,
    )


def _logs_for_range(start_date, end_date):
    return (
        GameLog.query
        .filter(GameLog.game_date >= start_date)
        .filter(GameLog.game_date <= end_date)
        .order_by(asc(GameLog.game_date), asc(GameLog.mlb_game_pk), asc(GameLog.pitcher_id), asc(GameLog.id))
        .all()
    )


def _pitchers_by_id(pitcher_ids):
    ids = tuple(pitcher_ids or ())
    if not ids:
        return {}
    return {
        row.id: row
        for row in Pitcher.query.filter(Pitcher.id.in_(ids)).all()
    }


def _scheduled_games_by_pk(game_pks):
    pks = tuple(game_pks or ())
    if not pks:
        return {}
    rows = (
        ScheduledGame.query
        .filter(ScheduledGame.game_pk.in_(pks))
        .order_by(asc(ScheduledGame.game_pk), asc(ScheduledGame.id))
        .all()
    )
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.game_pk].append(row)
    return grouped


def _snapshots_by_pitcher_date(pitcher_ids, dates):
    ids = tuple(pitcher_ids or ())
    snapshot_dates = tuple(sorted(_as_date(day) for day in dates or ()))
    if not ids or not snapshot_dates:
        return {}
    rows = (
        RosterStatusSnapshot.query
        .filter(RosterStatusSnapshot.pitcher_id.in_(ids))
        .filter(RosterStatusSnapshot.snapshot_date.in_(snapshot_dates))
        .order_by(
            asc(RosterStatusSnapshot.pitcher_id),
            asc(RosterStatusSnapshot.snapshot_date),
            asc(RosterStatusSnapshot.id),
        )
        .all()
    )
    by_key = {}
    for row in rows:
        by_key.setdefault((row.pitcher_id, row.snapshot_date), row)
    return by_key


def _pbp_events_by_game_pk(game_pks):
    pks = tuple(game_pks or ())
    if not pks:
        return {}
    rows = (
        GamePlayByPlayEvent.query
        .filter(GamePlayByPlayEvent.mlb_game_pk.in_(pks))
        .order_by(
            asc(GamePlayByPlayEvent.mlb_game_pk),
            asc(GamePlayByPlayEvent.event_index),
            asc(GamePlayByPlayEvent.id),
        )
        .all()
    )
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.mlb_game_pk].append(row)
    return grouped


def _source_evidence_cache(start_date, product_date):
    source_rule_ids = (
        WORKLOAD_DAYS_OF_REST_RULE_ID,
        USAGE_BACK_TO_BACK_RULE_ID,
        USAGE_THREE_IN_FOUR_RULE_ID,
        USAGE_FOUR_IN_SIX_RULE_ID,
        TEAM_BULLPEN_OUTS_WINDOW_RULE_ID,
        OUTING_CLEAN_RULE_ID,
        OUTING_TRAFFIC_RULE_ID,
        OUTING_CONTEXT_UNKNOWN_RULE_ID,
        APPEARANCE_FINISH_CONTEXT_RULE_ID,
    )
    rows = (
        EvidenceObject.query
        .filter(EvidenceObject.rule_id.in_(source_rule_ids))
        .filter(EvidenceObject.product_date >= start_date)
        .filter(EvidenceObject.product_date <= product_date)
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
        .order_by(
            asc(EvidenceObject.rule_id),
            asc(EvidenceObject.subject_type),
            asc(EvidenceObject.subject_id),
            asc(EvidenceObject.product_date),
            asc(EvidenceObject.id),
        )
        .all()
    )
    member = {}
    appearance = {}
    team = defaultdict(list)
    outing_family_days = set()
    for row in rows:
        key = (row.rule_id, row.subject_id, row.product_date)
        if row.subject_type == SUBJECT_PITCHER:
            member.setdefault(key, row)
        elif row.subject_type == SUBJECT_APPEARANCE:
            appearance.setdefault(key, row)
        elif row.subject_type == SUBJECT_TEAM:
            team[key].append(row)
        if row.rule_id in (
            OUTING_CLEAN_RULE_ID,
            OUTING_TRAFFIC_RULE_ID,
            OUTING_CONTEXT_UNKNOWN_RULE_ID,
        ):
            outing_family_days.add(row.product_date)
    return {
        'rows': rows,
        'member': member,
        'appearance': appearance,
        'team': team,
        'outing_family_days': outing_family_days,
    }


def _is_finality_certified(log):
    rows = ScheduledGame.query.filter_by(game_pk=log.mlb_game_pk).all()
    if not rows:
        return True
    return any(row.status_state == ScheduledGame.STATE_FINAL for row in rows)


def _same_date_snapshot(log):
    return (
        RosterStatusSnapshot.query
        .filter_by(pitcher_id=log.pitcher_id, snapshot_date=log.game_date)
        .order_by(asc(RosterStatusSnapshot.id))
        .first()
    )


def _current_snapshot(pitcher_id, product_date):
    return (
        RosterStatusSnapshot.query
        .filter_by(pitcher_id=pitcher_id, snapshot_date=product_date)
        .order_by(asc(RosterStatusSnapshot.id))
        .first()
    )


def _snapshot_team(snapshot, current_snapshot):
    if snapshot is not None:
        return snapshot.team_id
    if current_snapshot is not None:
        return current_snapshot.team_id
    return None


def _pbp_events_for_log(log):
    conditions = [GamePlayByPlayEvent.pitcher_id == log.pitcher_id]
    mlb_id = _pitcher_mlb_id(log)
    if mlb_id is not None:
        conditions.append(GamePlayByPlayEvent.pitcher_mlb_id == mlb_id)
    query = (
        GamePlayByPlayEvent.query
        .filter(GamePlayByPlayEvent.mlb_game_pk == log.mlb_game_pk)
        .filter(db.or_(*conditions))
        .order_by(asc(GamePlayByPlayEvent.event_index), asc(GamePlayByPlayEvent.id))
    )
    return query.all()


def _pitcher_row(pitcher_id):
    return db.session.get(Pitcher, pitcher_id)


def _pitcher_mlb_id(log):
    pitcher = _pitcher_row(log.pitcher_id)
    return getattr(pitcher, 'mlb_id', None)


def _members_from_decisions(decisions):
    by_pitcher = {}
    for item in decisions:
        by_pitcher[item.pitcher_id] = {
            'pitcher_id': item.pitcher_id,
            'pitcher_name': item.pitcher_name,
            'appearance_count': by_pitcher.get(item.pitcher_id, {}).get('appearance_count', 0) + 1,
        }
    return [by_pitcher[key] for key in sorted(by_pitcher)]


def _current_roster_relationships(members, team_id, product_date, context=None):
    rows = []
    for member in members:
        snapshot = (
            context.current_snapshot(member['pitcher_id'])
            if context is not None
            else _current_snapshot(member['pitcher_id'], product_date)
        )
        if snapshot is None:
            relationship = 'unknown'
        elif snapshot.team_id != team_id or snapshot.active_roster is False:
            relationship = 'not_on_current_active_roster'
        elif snapshot.active_roster is True and snapshot.roster_status == 'active':
            relationship = 'on_current_active_roster'
        else:
            relationship = 'unknown'
        rows.append({
            **member,
            'relationship': relationship,
            'snapshot_id': snapshot.id if snapshot is not None else None,
        })
    return rows


def _basis_claim(*, team_id, product_date, member_count, relationships, exclusions, lower_bound):
    prefix = 'At least ' if lower_bound else ''
    excluded_total = sum(exclusions.values())
    exclusion_phrase = 'no appearances excluded'
    if excluded_total:
        exclusion_phrase = (
            f'{excluded_total} appearance{"s" if excluded_total != 1 else ""} excluded: '
            f'{_reason_summary(exclusions)}'
        )
    return (
        f'{prefix}{member_count} pitchers made a relief appearance attributed to team '
        f'{team_id} in the last 14 days ending {product_date.isoformat()} '
        f'({relationships.get("on_current_active_roster", 0)} on the current active roster, '
        f'{relationships.get("not_on_current_active_roster", 0)} not on the current active roster, '
        f'{relationships.get("unknown", 0)} roster-unknown); {exclusion_phrase}. '
        f'{BASIS_DISCLAIMER}'
    )


def _basis_members(basis):
    trace = dict(basis.computation_trace or {})
    return list(trace.get('members') or [])


def _current_basis_object(team_id, product_date):
    return (
        EvidenceObject.query
        .filter_by(
            rule_id=TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID,
            subject_type=SUBJECT_TEAM,
            subject_id=str(team_id),
            product_date=product_date,
        )
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
        .order_by(asc(EvidenceObject.id))
        .first()
    )


def _current_basis_objects_by_team(team_ids, product_date):
    subject_ids = [str(team_id) for team_id in team_ids or ()]
    if not subject_ids:
        return {}
    rows = (
        EvidenceObject.query
        .filter_by(
            rule_id=TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID,
            subject_type=SUBJECT_TEAM,
            product_date=product_date,
        )
        .filter(EvidenceObject.subject_id.in_(subject_ids))
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
        .order_by(asc(EvidenceObject.subject_id), asc(EvidenceObject.id))
        .all()
    )
    by_team = {}
    for row in rows:
        by_team.setdefault(row.subject_id, row)
    return by_team


def _source_member_evidence(rule_id, pitcher_id, product_date, context=None):
    if context is not None:
        return context.source_member_evidence(rule_id, pitcher_id, product_date)
    return (
        EvidenceObject.query
        .filter_by(
            rule_id=rule_id,
            subject_type=SUBJECT_PITCHER,
            subject_id=str(pitcher_id),
            product_date=product_date,
        )
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
        .order_by(asc(EvidenceObject.id))
        .first()
    )


def _source_team_window_evidence(rule_id, team_id, product_date, window_days, context=None):
    if context is not None:
        return context.source_team_window_evidence(
            rule_id,
            team_id,
            product_date,
            window_days,
        )
    rows = (
        EvidenceObject.query
        .filter_by(
            rule_id=rule_id,
            subject_type=SUBJECT_TEAM,
            subject_id=str(team_id),
            product_date=product_date,
        )
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
        .order_by(asc(EvidenceObject.id))
        .all()
    )
    for row in rows:
        trace = dict(row.computation_trace or {})
        if trace.get('window_days') == window_days:
            return row
        if f'{window_days}d' in (row.subject_key or ''):
            return row
    return None


def _source_appearance_evidence(rule_id, log, context=None):
    if context is not None:
        return context.source_appearance_evidence(rule_id, log)
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


def _outing_family_ran_for_day(day, context=None):
    if context is not None:
        return context.outing_family_ran_for_day(day)
    return (
        EvidenceObject.query
        .filter(EvidenceObject.rule_id.in_((
            OUTING_CLEAN_RULE_ID,
            OUTING_TRAFFIC_RULE_ID,
            OUTING_CONTEXT_UNKNOWN_RULE_ID,
        )))
        .filter(EvidenceObject.product_date == day)
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
        .first()
        is not None
    )


def _outing_context_objects(log, context=None):
    rows = []
    for rule_id in (
        OUTING_CLEAN_RULE_ID,
        OUTING_TRAFFIC_RULE_ID,
        OUTING_CONTEXT_UNKNOWN_RULE_ID,
    ):
        row = _source_appearance_evidence(rule_id, log, context)
        if row is not None:
            rows.append(row)
    return rows


def _appearance_finish_context_object(log, context=None):
    return _source_appearance_evidence(APPEARANCE_FINISH_CONTEXT_RULE_ID, log, context)


def _decision_citations(decision):
    citations = [_game_log_citation(
        decision.log,
        ('games_started', 'mlb_game_pk', 'game_date', 'innings_pitched_outs'),
        'supporting_input' if decision.included else 'excluded_input',
    )]
    if decision.snapshot is None:
        citations.append(_missing_roster_snapshot_citation(decision.log))
    else:
        citations.append(_roster_snapshot_citation(
            decision.snapshot,
            'supporting_input' if decision.included else 'excluded_input',
        ))
    for event in decision.pbp_events[:3]:
        citations.append(_pbp_event_citation(
            event,
            'supporting_input' if decision.included else 'excluded_input',
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


def _roster_snapshot_citation(row, citation_role='supporting_input'):
    return EvidenceCitationInput(
        source_family='roster_status_snapshots',
        source_table='roster_status_snapshots',
        source_pk=row.id,
        source_field_names=(
            'pitcher_id',
            'team_id',
            'snapshot_date',
            'roster_status',
            'active_roster',
        ),
        citation_role=citation_role,
        cited_values={
            'pitcher_id': row.pitcher_id,
            'team_id': row.team_id,
            'snapshot_date': _iso(row.snapshot_date),
            'roster_status': row.roster_status,
            'active_roster': row.active_roster,
        },
        provenance={
            'source': row.source,
            'sync_run_id': row.sync_run_id,
            'correction_count': row.correction_count or 0,
            'last_corrected_at': _iso(row.last_corrected_at),
            'correction_source': row.correction_source,
        },
    )


def _missing_roster_snapshot_citation(log):
    return EvidenceCitationInput(
        source_family='roster_status_snapshots',
        source_table='roster_status_snapshots',
        source_pk=f'missing:{log.pitcher_id}:{log.game_date.isoformat()}',
        source_field_names=('pitcher_id', 'snapshot_date', 'team_id'),
        citation_role='excluded_input',
        cited_values={
            'pitcher_id': log.pitcher_id,
            'snapshot_date': log.game_date.isoformat(),
            'team_id': None,
        },
        provenance={'source': EVIDENCE_SOURCE},
    )


def _pbp_event_citation(row, citation_role='supporting_input'):
    return EvidenceCitationInput(
        source_family='final_play_by_play',
        source_table='game_play_by_play_events',
        source_pk=row.id,
        source_field_names=(
            'mlb_game_pk',
            'event_index',
            'pitcher_id',
            'pitcher_mlb_id',
            'fielding_team_id',
        ),
        citation_role=citation_role,
        cited_values={
            'mlb_game_pk': row.mlb_game_pk,
            'event_index': row.event_index,
            'pitcher_id': row.pitcher_id,
            'pitcher_mlb_id': row.pitcher_mlb_id,
            'fielding_team_id': row.fielding_team_id,
        },
        provenance={
            'source': row.source,
            'sync_run_id': row.sync_run_id,
            'correction_count': row.correction_count or 0,
            'last_corrected_at': _iso(row.last_corrected_at),
            'correction_source': row.correction_source,
        },
    )


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


def _missing_member_evidence_citation(
    rule_id,
    pitcher_id,
    product_date,
    role,
    *,
    appearance_key=None,
):
    source_pk = appearance_key or f'{pitcher_id}:{product_date.isoformat()}'
    return EvidenceCitationInput(
        source_family='phase0d_evidence_contract',
        source_table='evidence_objects',
        source_pk=f'missing:{rule_id}:{source_pk}',
        source_field_names=('rule_id', 'subject_id', 'product_date', 'completeness_state'),
        citation_role=role,
        cited_values={
            'rule_id': rule_id,
            'subject_id': str(pitcher_id),
            'product_date': _iso(product_date),
            'completeness_state': None,
        },
        provenance={'source': EVIDENCE_SOURCE},
    )


def _readiness_payload(required_families):
    return {
        'families': {
            family: {'status': SOURCE_READY, 'reason_codes': []}
            for family in required_families
        }
    }


def _rest_days_from_evidence(row):
    trace = dict(row.computation_trace or {})
    for key in ('full_off_days', 'days_of_rest', 'rest_days'):
        if trace.get(key) is not None:
            return int(trace[key])
    for payload in row.typed_cited_inputs or []:
        values = payload.get('cited_values') or {}
        for key in ('full_off_days', 'days_of_rest', 'rest_days'):
            if values.get(key) is not None:
                return int(values[key])
    return None


def _rest_bucket(days):
    if days <= 0:
        return '0'
    if days == 1:
        return '1'
    if days == 2:
        return '2'
    return '3+'


def _bullpen_outs_from_evidence(row):
    trace = dict(row.computation_trace or {})
    for key in ('bullpen_outs', 'known_bullpen_outs', 'total_outs', 'known_total'):
        if trace.get(key) is not None:
            return int(trace[key])
    for payload in row.typed_cited_inputs or []:
        values = payload.get('cited_values') or {}
        for key in ('bullpen_outs_recorded', 'bullpen_outs'):
            if values.get(key) is not None:
                return int(values[key])
    match = re.search(r'\b(?:recorded|outs)\s+(\d+)\s+outs\b', row.rendered_claim or '', re.I)
    if match:
        return int(match.group(1))
    return None


def _finish_values_from_evidence(row):
    trace = dict(row.computation_trace or {})
    values = dict(trace.get('finish_values') or {})
    if values:
        return values
    for payload in row.typed_cited_inputs or []:
        cited = payload.get('cited_values') or {}
        for key in ('games_finished', 'save_situation', 'save', 'hold', 'blown_save'):
            if key in cited:
                values[key] = cited.get(key)
    return values


def _decision_trace(decision):
    return {
        'game_log_id': decision.log.id,
        'mlb_game_pk': decision.log.mlb_game_pk,
        'game_date': decision.log.game_date.isoformat(),
        'pitcher_id': decision.pitcher_id,
        'pitcher_name': decision.pitcher_name,
        'team_id': decision.team_id,
        'included': decision.included,
        'reason_code': decision.reason_code,
        'snapshot_id': decision.snapshot.id if decision.snapshot is not None else None,
        'pbp_event_ids': [event.id for event in decision.pbp_events],
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


def _member_labels(members):
    return [
        {
            'pitcher_id': member.get('pitcher_id'),
            'pitcher_name': member.get('pitcher_name'),
        }
        for member in members
    ]


def _first_decision_value(decisions, field, fallback):
    for item in decisions:
        value = getattr(item.log, field, None)
        if value is not None:
            return value
    return fallback


def _reason_summary(counts):
    parts = []
    for reason, count in sorted(counts.items()):
        parts.append(f'{reason} {count}')
    return ', '.join(parts)


def _share(part, total):
    if not total:
        return 'unknown share'
    return f'{round((part / total) * 100)} percent'


def _record_attribution_dead_letter(decision, sync_run_id):
    dead_letter.record_failure(
        COMPOSITION_ATTRIBUTION_CONFLICT_ENTITY_TYPE,
        REASON_ATTRIBUTION_CONFLICT,
        entity_ref=decision.log.id,
        payload={
            'game_log_id': decision.log.id,
            'pitcher_id': decision.pitcher_id,
            'mlb_game_pk': decision.log.mlb_game_pk,
            'snapshot_team_id': decision.snapshot.team_id if decision.snapshot is not None else None,
            'pbp_fielding_team_ids': sorted({
                event.fielding_team_id
                for event in decision.pbp_events
                if event.fielding_team_id is not None
            }),
        },
        sync_run_id=sync_run_id,
        job_name='phase0d_team_relief_composition',
    )


def _record_concentration_dead_letter(
    *,
    team_id,
    product_date,
    window_days,
    contradiction,
    sync_run_id,
):
    dead_letter.record_failure(
        'composition_concentration_conflict',
        REASON_CONCENTRATION_CORROBORATION_MISMATCH,
        entity_ref=f'{team_id}:{product_date.isoformat()}:{window_days}',
        payload={
            'team_id': team_id,
            'product_date': product_date.isoformat(),
            'window_days': window_days,
            'contradiction': contradiction,
        },
        sync_run_id=sync_run_id,
        job_name='phase0d_team_relief_composition',
    )


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

    created = []
    emitted = []
    for new_evidence in rows:
        existing = existing_by_key.get(new_evidence.evidence_key)
        if existing is None:
            db.session.add(new_evidence)
            created.append(new_evidence)
            emitted.append('created')
            continue
        _refresh_existing_evidence(existing, new_evidence)
        emitted.append('refreshed')
    db.session.flush()
    _supersede_template_variant_siblings_batch(created)
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


def _supersede_template_variant_siblings(new_evidence):
    siblings = (
        EvidenceObject.query
        .filter(EvidenceObject.id != new_evidence.id)
        .filter(EvidenceObject.rule_id == new_evidence.rule_id)
        .filter(EvidenceObject.subject_key == new_evidence.subject_key)
        .filter(EvidenceObject.product_date == new_evidence.product_date)
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
        .all()
    )
    for row in siblings:
        row.recompute_status = EvidenceObject.RECOMPUTE_SUPERSEDED
        row.superseded_by_evidence_id = new_evidence.id
    if siblings:
        db.session.flush()


def _supersede_template_variant_siblings_batch(new_rows):
    rows = [row for row in new_rows or () if getattr(row, 'id', None) is not None]
    if not rows:
        return
    replacement_by_key = {
        (row.rule_id, row.subject_key, row.product_date): row.id
        for row in rows
    }
    new_ids = {row.id for row in rows}
    changed = False
    for key_chunk in _chunks(list(replacement_by_key), 100):
        clauses = [
            db.and_(
                EvidenceObject.rule_id == rule_id,
                EvidenceObject.subject_key == subject_key,
                EvidenceObject.product_date == product_date,
            )
            for rule_id, subject_key, product_date in key_chunk
        ]
        siblings = (
            EvidenceObject.query
            .filter(db.or_(*clauses))
            .filter(EvidenceObject.id.notin_(new_ids))
            .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
            .all()
        )
        for sibling in siblings:
            key = (sibling.rule_id, sibling.subject_key, sibling.product_date)
            sibling.recompute_status = EvidenceObject.RECOMPUTE_SUPERSEDED
            sibling.superseded_by_evidence_id = replacement_by_key[key]
            changed = True
    if changed:
        db.session.flush()


def _keys_by_date(rows):
    grouped = defaultdict(set)
    for row in rows:
        grouped[row.product_date].add(row.evidence_key)
    return dict(sorted(grouped.items()))


def _chunks(values, size):
    for index in range(0, len(values), size):
        yield values[index:index + size]


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


def _assert_text_has_no_team_relief_composition_forbidden_terms(text):
    normalized = str(text or '').lower()
    for term in _FORBIDDEN_TEAM_RELIEF_COMPOSITION_TERMS:
        if re.search(rf'(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])', normalized, re.I):
            raise EvidenceLanguageError(
                f'team relief contributor composition language contains forbidden term: {term}'
            )
    return True


def _dedupe(items):
    seen = set()
    result = []
    for item in items or []:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _citation_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _iso(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
