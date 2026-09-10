from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable

from models.composed_read import ComposedRead
from models.dashboard_snapshot import DashboardSnapshot
from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.legacy_read_audit import LegacyReadAuditRun, LegacyReadDivergence
from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from models.play_by_play_foundation import GamePlayByPlayEvent, PlayByPlayProcessedGame
from models.roster_status_snapshot import RosterStatusSnapshot
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from services.appearance_context_evidence import BASE_STATE_LIMITATION
from services.composed_read import ComponentInput, build_composed_read
from services.inherited_traffic_evidence import HBP_ROE_LIMITATION
from services.legacy_read_reconciliation import run_reconciliation_audit
from services.reliever_daily_read import READ_TYPE as RELIEVER_READ_TYPE
from services.reliever_daily_read import READ_VERSION as RELIEVER_READ_VERSION
from services.reliever_daily_read import register_reliever_daily_read
from services.roster_depth_evidence import (
    LOWER_BOUND_COVERAGE_LIMITATION,
    NO_HEALTH_LIMITATION,
    PITCHER_SCOPED_SNAPSHOT_LIMITATION,
)
from services.starter_exposure_evidence import (
    APPEARANCES_NOT_DISTINCT_ARMS_LIMITATION,
    SCHEDULE_SUBJECT_TO_CHANGE_LIMITATION,
)
from services.team_daily_read import READ_TYPE as TEAM_READ_TYPE
from services.team_daily_read import READ_VERSION as TEAM_READ_VERSION
from services.team_daily_read import register_team_daily_read
from services.team_relief_composition_evidence import BASIS_DISCLAIMER
from utils.db import db


BASE_PRODUCT_DATE = date(2026, 7, 5)
INTERNAL_WATERMARK = 'INTERNAL ONLY - Phase 0E QA scenario fixture.'

SCENARIO_NAMES = (
    'opening_week_small_samples',
    'off_day_team',
    'doubleheader',
    'suspended_resumed_game',
    'incomplete_slate',
    'postponed_game',
    'trade_deadline_churn',
    'option_recall_churn',
    'il_placement_activation_timing',
    'september_call_up',
    'roster_snapshot_stale',
    'transaction_coverage_gap',
    'idle_team_trailing_windows',
    'relief_history_missing_membership',
    'rostered_cold_arm_gap',
    'missing_contributor_basis',
    'legacy_snapshot_missing',
    'composed_reads_missing',
    'conflict_state_evidence',
    'mid_window_correction_recompute',
    'locked_band_consumption_attempt',
    'legacy_factual_field_contradiction',
    'covered_window_zero_transactions',
)


@dataclass(frozen=True)
class ScenarioHandle:
    name: str
    product_date: date
    sync_run_id: int
    expected_state_map: dict
    pitcher_ids: dict[str, int] = field(default_factory=dict)
    team_ids: dict[str, int] = field(default_factory=dict)
    evidence_object_ids: tuple[int, ...] = ()
    composed_read_ids: tuple[int, ...] = ()
    audit_run_ids: tuple[int, ...] = ()
    divergence_ids: tuple[int, ...] = ()
    row_ids: dict[str, tuple[int, ...]] = field(default_factory=dict)


@dataclass
class _ScenarioContext:
    name: str
    product_date: date
    index: int
    sync_run: SyncRun
    pitcher_ids: dict[str, int] = field(default_factory=dict)
    team_ids: dict[str, int] = field(default_factory=dict)
    evidence_object_ids: list[int] = field(default_factory=list)
    composed_read_ids: list[int] = field(default_factory=list)
    audit_run_ids: list[int] = field(default_factory=list)
    divergence_ids: list[int] = field(default_factory=list)
    row_ids: dict[str, list[int]] = field(default_factory=dict)
    counter: int = 0

    def next(self, label: str) -> str:
        self.counter += 1
        return f'{self.name}:{label}:{self.counter}'


def opening_week_small_samples() -> ScenarioHandle:
    ctx, pitcher, game_log, snapshot, pbp = _base_context('opening_week_small_samples')
    read = _build_reliever_read(
        ctx,
        pitcher,
        game_log=game_log,
        roster_snapshot=snapshot,
        pbp_event=pbp,
        component_states={
            'workload_component': ComposedRead.COMPLETENESS_PARTIAL,
            'rest_component': ComposedRead.COMPLETENESS_PARTIAL,
        },
        component_reasons={
            'workload_component': ('opening_week_small_sample',),
            'rest_component': ('opening_week_small_sample',),
        },
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': RELIEVER_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_PARTIAL,
                'component_states': {
                    'workload_component': ComposedRead.COMPLETENESS_PARTIAL,
                    'rest_component': ComposedRead.COMPLETENESS_PARTIAL,
                },
                'reason_codes': (
                    'workload_component:opening_week_small_sample',
                    'rest_component:opening_week_small_sample',
                ),
            },
        },
        'audit_categories': (),
    })


def off_day_team() -> ScenarioHandle:
    ctx, pitcher, _game_log, snapshot, _pbp = _base_context('off_day_team')
    team_id = snapshot.team_id
    read = _build_team_read(
        ctx,
        team_id=team_id,
        roster_snapshot=snapshot,
        calendar=False,
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': TEAM_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_COMPLETE,
                'component_states': {
                    'calendar_component': 'absent',
                    'contributor_composition_component': ComposedRead.COMPLETENESS_COMPLETE,
                },
                'limitations': (BASIS_DISCLAIMER,),
            },
        },
        'audit_categories': (),
        'team_population_present': (team_id,),
        'pitcher_ids': (pitcher.id,),
    })


def doubleheader() -> ScenarioHandle:
    ctx, _pitcher, game_log, snapshot, _pbp = _base_context('doubleheader')
    team_id = snapshot.team_id
    _scheduled_game(ctx, team_id, game_number=1, doubleheader='Y')
    _scheduled_game(ctx, team_id, game_number=2, doubleheader='Y', game_pk_offset=2)
    read = _build_team_read(
        ctx,
        team_id=team_id,
        roster_snapshot=snapshot,
        exposure_reason_codes=('doubleheader_today',),
        exposure_limitations=(APPEARANCES_NOT_DISTINCT_ARMS_LIMITATION,),
        calendar=True,
        calendar_reason_codes=('doubleheader_today',),
        source_row=game_log,
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': TEAM_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_COMPLETE,
                'component_states': {
                    'calendar_component': ComposedRead.COMPLETENESS_COMPLETE,
                    'exposure_component': ComposedRead.COMPLETENESS_COMPLETE,
                },
                'reason_codes': (
                    'exposure_component:doubleheader_today',
                    'calendar_component:doubleheader_today',
                ),
                'limitations': (APPEARANCES_NOT_DISTINCT_ARMS_LIMITATION,),
            },
        },
        'audit_categories': (),
    })


def suspended_resumed_game() -> ScenarioHandle:
    ctx, pitcher, game_log, snapshot, pbp = _base_context('suspended_resumed_game')
    _scheduled_game(ctx, snapshot.team_id, status_state=ScheduledGame.STATE_SUSPENDED)
    _processed_game(ctx, game_log, status=PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED)
    read = _build_reliever_read(
        ctx,
        pitcher,
        game_log=game_log,
        roster_snapshot=snapshot,
        pbp_event=pbp,
        recent_limitations=(
            BASE_STATE_LIMITATION,
            HBP_ROE_LIMITATION,
            'game was suspended and resumed; events may span calendar dates',
        ),
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': RELIEVER_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_COMPLETE,
                'component_states': {
                    'recent_outing_component': ComposedRead.COMPLETENESS_COMPLETE,
                },
                'limitations': (
                    BASE_STATE_LIMITATION,
                    HBP_ROE_LIMITATION,
                    'game was suspended and resumed; events may span calendar dates',
                ),
            },
        },
        'audit_categories': (),
    })


def incomplete_slate() -> ScenarioHandle:
    ctx, _pitcher, game_log, snapshot, _pbp = _base_context('incomplete_slate')
    read = _build_team_read(
        ctx,
        team_id=snapshot.team_id,
        roster_snapshot=snapshot,
        contributor_state=ComposedRead.COMPLETENESS_PARTIAL,
        contributor_reason_codes=('incomplete_slate_day_in_window',),
        contributor_limitations=('Counts are lower bounds when a cited product-day window has incomplete slate coverage.',),
        source_row=game_log,
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': TEAM_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_PARTIAL,
                'component_states': {
                    'contributor_composition_component': ComposedRead.COMPLETENESS_PARTIAL,
                },
                'reason_codes': (
                    'contributor_composition_component:incomplete_slate_day_in_window',
                ),
            },
        },
        'audit_categories': (),
    })


def postponed_game() -> ScenarioHandle:
    ctx, _pitcher, game_log, snapshot, _pbp = _base_context('postponed_game')
    _scheduled_game(ctx, snapshot.team_id, status_state=ScheduledGame.STATE_POSTPONED)
    read = _build_team_read(
        ctx,
        team_id=snapshot.team_id,
        roster_snapshot=snapshot,
        calendar=True,
        calendar_reason_codes=('postponed_game',),
        calendar_limitations=(SCHEDULE_SUBJECT_TO_CHANGE_LIMITATION,),
        source_row=game_log,
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': TEAM_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_COMPLETE,
                'component_states': {
                    'calendar_component': ComposedRead.COMPLETENESS_COMPLETE,
                },
                'reason_codes': ('calendar_component:postponed_game',),
                'limitations': (SCHEDULE_SUBJECT_TO_CHANGE_LIMITATION,),
            },
        },
        'audit_categories': (),
    })


def trade_deadline_churn() -> ScenarioHandle:
    ctx, _pitcher, game_log, snapshot, _pbp = _base_context('trade_deadline_churn')
    transaction = _transaction(ctx, snapshot.pitcher_id, snapshot.team_id, category='trade')
    read = _build_team_read(
        ctx,
        team_id=snapshot.team_id,
        roster_snapshot=snapshot,
        roster_source_row=transaction,
        roster_reason_codes=('trade_churn_window',),
        source_row=game_log,
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': TEAM_READ_TYPE,
                'component_states': {
                    'roster_churn_component': ComposedRead.COMPLETENESS_COMPLETE,
                },
                'reason_codes': ('roster_churn_component:trade_churn_window',),
            },
        },
        'audit_categories': (),
        'transactions': ('trade',),
    })


def option_recall_churn() -> ScenarioHandle:
    ctx, _pitcher, game_log, snapshot, _pbp = _base_context('option_recall_churn')
    option = _transaction(ctx, snapshot.pitcher_id, snapshot.team_id, category='option')
    _transaction(ctx, snapshot.pitcher_id, snapshot.team_id, category='recall')
    read = _build_team_read(
        ctx,
        team_id=snapshot.team_id,
        roster_snapshot=snapshot,
        roster_source_row=option,
        roster_reason_codes=('option_recall_churn',),
        source_row=game_log,
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': TEAM_READ_TYPE,
                'component_states': {
                    'roster_churn_component': ComposedRead.COMPLETENESS_COMPLETE,
                },
                'reason_codes': ('roster_churn_component:option_recall_churn',),
            },
        },
        'audit_categories': (),
        'transactions': ('option', 'recall'),
    })


def il_placement_activation_timing() -> ScenarioHandle:
    ctx, pitcher, game_log, snapshot, pbp = _base_context('il_placement_activation_timing')
    placement = _transaction(
        ctx,
        pitcher.id,
        snapshot.team_id,
        category='il_placement',
        is_il_placement=True,
    )
    _transaction(
        ctx,
        pitcher.id,
        snapshot.team_id,
        category='il_activation',
        is_il_activation=True,
    )
    read = _build_reliever_read(
        ctx,
        pitcher,
        game_log=game_log,
        roster_snapshot=snapshot,
        pbp_event=pbp,
        roster_source_row=placement,
        roster_limitations=(NO_HEALTH_LIMITATION,),
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': RELIEVER_READ_TYPE,
                'component_states': {
                    'roster_il_context': ComposedRead.COMPLETENESS_COMPLETE,
                },
                'limitations': (NO_HEALTH_LIMITATION,),
            },
        },
        'audit_categories': (),
        'transactions': ('il_placement', 'il_activation'),
    })


def september_call_up() -> ScenarioHandle:
    ctx, _pitcher, game_log, snapshot, _pbp = _base_context('september_call_up')
    recall = _transaction(ctx, snapshot.pitcher_id, snapshot.team_id, category='recall')
    read = _build_team_read(
        ctx,
        team_id=snapshot.team_id,
        roster_snapshot=snapshot,
        roster_source_row=recall,
        roster_reason_codes=('september_call_up',),
        source_row=game_log,
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': TEAM_READ_TYPE,
                'component_states': {
                    'roster_churn_component': ComposedRead.COMPLETENESS_COMPLETE,
                },
                'reason_codes': ('roster_churn_component:september_call_up',),
            },
        },
        'audit_categories': (),
    })


def roster_snapshot_stale() -> ScenarioHandle:
    ctx, pitcher, game_log, snapshot, pbp = _base_context(
        'roster_snapshot_stale',
        snapshot_date_offset=-1,
    )
    read = _build_reliever_read(
        ctx,
        pitcher,
        game_log=game_log,
        roster_snapshot=snapshot,
        pbp_event=pbp,
        component_states={'roster_il_context': ComposedRead.COMPLETENESS_UNKNOWN},
        component_reasons={'roster_il_context': ('snapshot_stale',)},
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': RELIEVER_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_UNKNOWN,
                'component_states': {
                    'roster_il_context': ComposedRead.COMPLETENESS_UNKNOWN,
                },
                'reason_codes': ('roster_il_context:snapshot_stale',),
            },
        },
        'audit_categories': (),
    })


def transaction_coverage_gap() -> ScenarioHandle:
    ctx, _pitcher, game_log, snapshot, _pbp = _base_context('transaction_coverage_gap')
    _transaction_window(ctx, status='failed')
    read = _build_team_read(
        ctx,
        team_id=snapshot.team_id,
        roster_snapshot=snapshot,
        roster_state=ComposedRead.COMPLETENESS_PARTIAL,
        roster_reason_codes=('transaction_window_uncovered',),
        roster_limitations=(LOWER_BOUND_COVERAGE_LIMITATION,),
        source_row=game_log,
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': TEAM_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_PARTIAL,
                'component_states': {
                    'roster_churn_component': ComposedRead.COMPLETENESS_PARTIAL,
                },
                'reason_codes': ('roster_churn_component:transaction_window_uncovered',),
                'limitations': (LOWER_BOUND_COVERAGE_LIMITATION,),
            },
        },
        'audit_categories': (),
    })


def idle_team_trailing_windows() -> ScenarioHandle:
    ctx, _pitcher, game_log, snapshot, _pbp = _base_context('idle_team_trailing_windows')
    read = _build_team_read(
        ctx,
        team_id=snapshot.team_id,
        roster_snapshot=snapshot,
        exposure_state=ComposedRead.COMPLETENESS_COMPLETE,
        exposure_reason_codes=('covered_window_zero_games',),
        source_row=game_log,
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': TEAM_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_COMPLETE,
                'component_states': {
                    'exposure_component': ComposedRead.COMPLETENESS_COMPLETE,
                },
                'reason_codes': ('exposure_component:covered_window_zero_games',),
            },
        },
        'audit_categories': (),
    })


def relief_history_missing_membership() -> ScenarioHandle:
    ctx, pitcher, game_log, snapshot, pbp = _base_context('relief_history_missing_membership')
    read = _build_reliever_read(
        ctx,
        pitcher,
        game_log=game_log,
        roster_snapshot=snapshot,
        pbp_event=pbp,
        component_states={'roster_il_context': ComposedRead.COMPLETENESS_UNKNOWN},
        component_reasons={'roster_il_context': ('roster_membership_unknown',)},
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': RELIEVER_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_UNKNOWN,
                'component_states': {
                    'roster_il_context': ComposedRead.COMPLETENESS_UNKNOWN,
                },
                'reason_codes': ('roster_il_context:roster_membership_unknown',),
            },
        },
        'audit_categories': (),
    })


def rostered_cold_arm_gap() -> ScenarioHandle:
    ctx, pitcher, _game_log, snapshot, _pbp = _base_context(
        'rostered_cold_arm_gap',
        create_game_log=False,
        create_pbp=False,
    )
    return _handle(ctx, {
        'reads': {},
        'expected_absences': {
            'reliever_daily_read': {
                'subject_id': str(pitcher.id),
                'reason': 'cold_arm_gap_no_trailing_relief_appearance',
            },
        },
        'audit_categories': (),
        'row_ids': {
            'roster_status_snapshots': (snapshot.id,),
        },
    })


def missing_contributor_basis() -> ScenarioHandle:
    ctx, _pitcher, game_log, snapshot, _pbp = _base_context('missing_contributor_basis')
    read = _build_team_read(
        ctx,
        team_id=snapshot.team_id,
        roster_snapshot=snapshot,
        contributor_state=ComposedRead.COMPLETENESS_UNKNOWN,
        contributor_reason_codes=('component_evidence_unavailable',),
        source_row=game_log,
        include_contributor_evidence=False,
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': TEAM_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_UNKNOWN,
                'component_states': {
                    'contributor_composition_component': ComposedRead.COMPLETENESS_UNKNOWN,
                },
                'reason_codes': (
                    'contributor_composition_component:component_evidence_unavailable',
                ),
                'limitations': (BASIS_DISCLAIMER,),
            },
        },
        'audit_categories': (),
    })


def legacy_snapshot_missing() -> ScenarioHandle:
    ctx, pitcher, game_log, snapshot, pbp = _base_context('legacy_snapshot_missing')
    _build_reliever_read(ctx, pitcher, game_log=game_log, roster_snapshot=snapshot, pbp_event=pbp)
    result = run_reconciliation_audit(
        ctx.product_date,
        subject_type=LegacyReadAuditRun.SUBJECT_PITCHER_DAY,
        source='qa_scenario',
    )
    _capture_audit_rows(ctx)
    return _handle(ctx, {
        'reads': {},
        'audit_run_status': result['subjects'][LegacyReadAuditRun.SUBJECT_PITCHER_DAY]['run_status'],
        'audit_categories': (),
    })


def composed_reads_missing() -> ScenarioHandle:
    ctx, _pitcher, _game_log, _snapshot, _pbp = _base_context('composed_reads_missing')
    _dashboard(ctx, {'pitchers': [{'pitcher_id': 10001, 'availability_status': 'Available'}]})
    result = run_reconciliation_audit(
        ctx.product_date,
        subject_type=LegacyReadAuditRun.SUBJECT_PITCHER_DAY,
        source='qa_scenario',
    )
    _capture_audit_rows(ctx)
    return _handle(ctx, {
        'reads': {},
        'audit_run_status': result['subjects'][LegacyReadAuditRun.SUBJECT_PITCHER_DAY]['run_status'],
        'audit_categories': (),
    })


def conflict_state_evidence() -> ScenarioHandle:
    ctx, pitcher, game_log, snapshot, pbp = _base_context('conflict_state_evidence')
    read = _build_reliever_read(
        ctx,
        pitcher,
        game_log=game_log,
        roster_snapshot=snapshot,
        pbp_event=pbp,
        component_states={'recent_outing_component': ComposedRead.COMPLETENESS_CONFLICT},
        component_reasons={'recent_outing_component': ('component_evidence_conflict',)},
    )
    _dashboard(ctx, {
        'pitchers': [
            {'pitcher_id': pitcher.id, 'availability_status': 'Monitor'},
        ],
    })
    run_reconciliation_audit(ctx.product_date, subject_type='pitcher_day', source='qa_scenario')
    _capture_audit_rows(ctx)
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': RELIEVER_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_CONFLICT,
                'component_states': {
                    'recent_outing_component': ComposedRead.COMPLETENESS_CONFLICT,
                },
                'reason_codes': (
                    'recent_outing_component:component_evidence_conflict',
                ),
            },
        },
        'audit_categories': (LegacyReadDivergence.CATEGORY_ACTIONABLE_ON_DEGRADED_READ,),
        'material_categories': (LegacyReadDivergence.CATEGORY_ACTIONABLE_ON_DEGRADED_READ,),
    })


def mid_window_correction_recompute() -> ScenarioHandle:
    ctx, pitcher, game_log, snapshot, pbp = _base_context('mid_window_correction_recompute')
    read = _build_reliever_read(ctx, pitcher, game_log=game_log, roster_snapshot=snapshot, pbp_event=pbp)
    cited = read.components[0].evidence_citations[0].evidence_object
    cited.recompute_status = EvidenceObject.RECOMPUTE_NEEDED
    read.recompute_status = ComposedRead.RECOMPUTE_NEEDED
    read.recompute_reason_codes = ['component_evidence_superseded']
    db.session.flush()
    _dashboard(ctx, {
        'pitchers': [
            {'pitcher_id': pitcher.id, 'availability_status': 'Available'},
        ],
    })
    run_reconciliation_audit(
        ctx.product_date,
        subject_type='pitcher_day',
        source='qa_scenario',
        force_skip_reads_missing=True,
    )
    _capture_audit_rows(ctx)
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': RELIEVER_READ_TYPE,
                'recompute_status': ComposedRead.RECOMPUTE_NEEDED,
                'recompute_reason_codes': ('component_evidence_superseded',),
            },
        },
        'audit_run_status': LegacyReadAuditRun.STATUS_SKIPPED_READS_MISSING,
        'audit_categories': (),
        'cascade': ('evidence', 'read', 'audit_skip'),
    })


def locked_band_consumption_attempt() -> ScenarioHandle:
    ctx, pitcher, game_log, snapshot, pbp = _base_context('locked_band_consumption_attempt')
    locked = _evidence(
        ctx,
        rule_id='appearance_entry_band',
        evidence_type='appearance_entry_band',
        subject_type='pitcher',
        subject_id=pitcher.id,
        source_row=pbp,
        rendered_claim='Locked internal entry band captured for guard testing.',
    )
    team_locked = _evidence(
        ctx,
        rule_id='team_active_reliever_count',
        evidence_type='team_active_reliever_count',
        subject_type='team',
        subject_id=snapshot.team_id,
        source_row=snapshot,
        rendered_claim='Locked internal reliever partition captured for guard testing.',
    )
    failure_messages = []
    try:
        _build_reliever_read(
            ctx,
            pitcher,
            game_log=game_log,
            roster_snapshot=snapshot,
            pbp_event=pbp,
            recent_evidence=(locked,),
        )
    except Exception as exc:  # noqa: BLE001 - the handle records the contract failure.
        failure_messages.append(str(exc))
    try:
        _build_team_read(
            ctx,
            team_id=snapshot.team_id,
            roster_snapshot=snapshot,
            source_row=game_log,
            contributor_evidence=(team_locked,),
        )
    except Exception as exc:  # noqa: BLE001
        failure_messages.append(str(exc))
    return _handle(ctx, {
        'reads': {},
        'expected_failures': tuple(failure_messages),
        'audit_categories': (),
    })


def legacy_factual_field_contradiction() -> ScenarioHandle:
    ctx, pitcher, game_log, snapshot, pbp = _base_context('legacy_factual_field_contradiction')
    read = _build_reliever_read(
        ctx,
        pitcher,
        game_log=game_log,
        roster_snapshot=snapshot,
        pbp_event=pbp,
        rest_typed={'last_final_appearance': ctx.product_date.isoformat(), 'days_rest': 0},
    )
    _dashboard(ctx, {
        'pitchers': [
            {
                'pitcher_id': pitcher.id,
                'availability_status': 'Available',
                'last_final_appearance_date': (ctx.product_date - timedelta(days=2)).isoformat(),
                'days_rest': 2,
            },
        ],
    })
    run_reconciliation_audit(ctx.product_date, subject_type='pitcher_day', source='qa_scenario')
    _capture_audit_rows(ctx)
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': RELIEVER_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_COMPLETE,
            },
        },
        'audit_categories': (LegacyReadDivergence.CATEGORY_STATE_CONTRADICTS_FACT,),
        'material_categories': (LegacyReadDivergence.CATEGORY_STATE_CONTRADICTS_FACT,),
    })


def covered_window_zero_transactions() -> ScenarioHandle:
    ctx, _pitcher, game_log, snapshot, _pbp = _base_context('covered_window_zero_transactions')
    _transaction_window(ctx, status='success', records_fetched=0, records_stored=0)
    read = _build_team_read(
        ctx,
        team_id=snapshot.team_id,
        roster_snapshot=snapshot,
        roster_reason_codes=('covered_window_zero_transactions',),
        source_row=game_log,
    )
    return _handle(ctx, {
        'reads': {
            str(read.id): {
                'read_type': TEAM_READ_TYPE,
                'completeness_state': ComposedRead.COMPLETENESS_COMPLETE,
                'component_states': {
                    'roster_churn_component': ComposedRead.COMPLETENESS_COMPLETE,
                },
                'reason_codes': (
                    'roster_churn_component:covered_window_zero_transactions',
                ),
            },
        },
        'audit_categories': (),
        'transaction_window': 'provable_absence',
    })


def _base_context(
    name,
    *,
    create_game_log=True,
    create_pbp=True,
    snapshot_date_offset=0,
):
    index = SCENARIO_NAMES.index(name) + 1
    product_date = BASE_PRODUCT_DATE - timedelta(days=index)
    sync_run = SyncRun(
        job_name=f'qa_{name}'[:50],
        started_at=datetime(2026, 7, 5, 6, 0, index),
        completed_at=datetime(2026, 7, 5, 6, 1, index),
        status='success',
        stage='qa_fixture',
        source='qa_scenario',
    )
    db.session.add(sync_run)
    db.session.flush()
    ctx = _ScenarioContext(
        name=name,
        product_date=product_date,
        index=index,
        sync_run=sync_run,
    )
    pitcher = _pitcher(ctx, 'primary')
    game_log = _game_log(ctx, pitcher) if create_game_log else None
    snapshot = _roster_snapshot(
        ctx,
        pitcher,
        snapshot_date=product_date + timedelta(days=snapshot_date_offset),
    )
    pbp = _pbp_event(ctx, pitcher, game_log) if create_pbp and game_log is not None else None
    return ctx, pitcher, game_log, snapshot, pbp


def _pitcher(ctx: _ScenarioContext, label: str, *, team_id: int | None = None) -> Pitcher:
    team = team_id or (700 + ctx.index)
    row = Pitcher(
        mlb_id=900000 + ctx.index * 10 + len(ctx.pitcher_ids) + 1,
        full_name=f'QA Pitcher {ctx.index} {label}',
        team_id=team,
        team_name=f'QA Team {team}',
        team_abbreviation=f'Q{ctx.index}',
        position='P',
        active=True,
    )
    db.session.add(row)
    db.session.flush()
    ctx.pitcher_ids[label] = row.id
    ctx.team_ids.setdefault('primary', team)
    ctx.row_ids.setdefault('pitchers', []).append(row.id)
    return row


def _game_log(ctx: _ScenarioContext, pitcher: Pitcher, *, day: date | None = None) -> GameLog:
    row = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=800000 + ctx.index * 100 + len(ctx.row_ids.get('game_logs', ())),
        game_date=day or ctx.product_date,
        opponent='QA Opponent',
        opponent_abbreviation='QAO',
        game_type='R',
        games_started=0,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        pitches_thrown=14,
        strikes=9,
        hits_allowed=0,
        runs_allowed=0,
        earned_runs=0,
        walks=0,
        strikeouts=1,
        home_runs_allowed=0,
        batters_faced=3,
        inherited_runners=0,
        inherited_runners_scored=0,
    )
    db.session.add(row)
    db.session.flush()
    ctx.row_ids.setdefault('game_logs', []).append(row.id)
    return row


def _roster_snapshot(
    ctx: _ScenarioContext,
    pitcher: Pitcher,
    *,
    snapshot_date: date | None = None,
    active: bool = True,
) -> RosterStatusSnapshot:
    row = RosterStatusSnapshot(
        pitcher_id=pitcher.id,
        mlb_id=pitcher.mlb_id,
        team_id=pitcher.team_id,
        snapshot_date=snapshot_date or ctx.product_date,
        roster_status='active' if active else 'inactive',
        active_roster=active,
        forty_man_roster=True,
        position_code='P',
        position_name='Pitcher',
        position_type='Pitcher',
        source='qa_scenario',
        sync_run_id=ctx.sync_run.id,
    )
    db.session.add(row)
    db.session.flush()
    ctx.row_ids.setdefault('roster_status_snapshots', []).append(row.id)
    return row


def _pbp_event(
    ctx: _ScenarioContext,
    pitcher: Pitcher,
    game_log: GameLog,
) -> GamePlayByPlayEvent:
    row = GamePlayByPlayEvent(
        mlb_game_pk=game_log.mlb_game_pk,
        event_index=1,
        source_play_id=ctx.next('pbp'),
        at_bat_index=1,
        game_date=game_log.game_date,
        game_type='R',
        home_team_id=pitcher.team_id,
        away_team_id=pitcher.team_id + 1,
        event_type='plate_appearance',
        event_type_code='field_out',
        inning=7,
        half_inning='top',
        is_top_inning=True,
        outs_at_event=0,
        home_score_at_event=2,
        away_score_at_event=1,
        pitcher_mlb_id=pitcher.mlb_id,
        pitcher_id=pitcher.id,
        batter_mlb_id=910000 + ctx.index,
        batting_team_id=pitcher.team_id + 1,
        fielding_team_id=pitcher.team_id,
        source='qa_scenario',
        source_endpoint='synthetic',
        sync_run_id=ctx.sync_run.id,
    )
    db.session.add(row)
    db.session.flush()
    ctx.row_ids.setdefault('game_play_by_play_events', []).append(row.id)
    return row


def _processed_game(
    ctx: _ScenarioContext,
    game_log: GameLog,
    *,
    status: str,
) -> PlayByPlayProcessedGame:
    row = PlayByPlayProcessedGame(
        mlb_game_pk=game_log.mlb_game_pk,
        game_date=game_log.game_date,
        game_type='R',
        home_team_id=ctx.team_ids['primary'],
        away_team_id=ctx.team_ids['primary'] + 1,
        final_state='final',
        processing_status=status,
        attempt_count=1,
        events_seen=1,
        events_stored=1,
        pitcher_events_seen=1,
        event_fingerprint=ctx.next('fingerprint'),
        source='qa_scenario',
        source_endpoint='synthetic',
        sync_run_id=ctx.sync_run.id,
        processed_at=datetime(2026, 7, 5, 7, 0),
    )
    db.session.add(row)
    db.session.flush()
    ctx.row_ids.setdefault('play_by_play_processed_games', []).append(row.id)
    return row


def _scheduled_game(
    ctx: _ScenarioContext,
    team_id: int,
    *,
    game_number: int = 1,
    doubleheader: str = 'N',
    game_pk_offset: int = 1,
    status_state: str = ScheduledGame.STATE_FINAL,
) -> ScheduledGame:
    row = ScheduledGame(
        team_id=team_id,
        game_pk=810000 + ctx.index * 100 + game_pk_offset,
        game_date=ctx.product_date,
        opponent_team_id=team_id + 1,
        home_away='home',
        game_type='R',
        status_code='F',
        status_state=status_state,
        doubleheader=doubleheader,
        game_number=game_number,
        series_game_number=game_number,
        games_in_series=3,
        source='qa_scenario',
    )
    db.session.add(row)
    db.session.flush()
    ctx.row_ids.setdefault('scheduled_games', []).append(row.id)
    return row


def _transaction(
    ctx: _ScenarioContext,
    pitcher_id: int,
    team_id: int,
    *,
    category: str,
    is_il_placement: bool = False,
    is_il_activation: bool = False,
) -> PlayerTransaction:
    pitcher = db.session.get(Pitcher, pitcher_id)
    row = PlayerTransaction(
        transaction_key=ctx.next(f'txn:{category}'),
        transaction_id=ctx.next('source-txn'),
        pitcher_id=pitcher_id,
        player_mlb_id=pitcher.mlb_id if pitcher else 990000 + ctx.index,
        from_team_id=team_id - 1,
        to_team_id=team_id,
        transaction_date=ctx.product_date,
        effective_date=ctx.product_date,
        transaction_type_code=category,
        normalized_category=category,
        is_il_placement=is_il_placement,
        is_il_activation=is_il_activation,
        il_list_type='15-day' if is_il_placement or is_il_activation else None,
        roster_snapshot_alignment='aligned',
        alignment_reason_code='qa_fixture',
        explanatory_linkage_eligible=True,
        source='qa_scenario',
        source_endpoint='synthetic',
        source_query_start_date=ctx.product_date - timedelta(days=14),
        source_query_end_date=ctx.product_date,
        sync_run_id=ctx.sync_run.id,
    )
    db.session.add(row)
    db.session.flush()
    ctx.row_ids.setdefault('player_transactions', []).append(row.id)
    return row


def _transaction_window(
    ctx: _ScenarioContext,
    *,
    status: str,
    records_fetched: int = 0,
    records_stored: int = 0,
) -> PlayerTransactionSyncWindow:
    row = PlayerTransactionSyncWindow(
        source='qa_scenario',
        source_endpoint='synthetic',
        source_query_start_date=ctx.product_date - timedelta(days=14),
        source_query_end_date=ctx.product_date,
        attempted_at=datetime(2026, 7, 5, 7, 0),
        successful_at=datetime(2026, 7, 5, 7, 1) if status == 'success' else None,
        status=status,
        records_fetched=records_fetched,
        records_stored=records_stored,
        records_created=records_stored,
        sync_run_id=ctx.sync_run.id,
    )
    db.session.add(row)
    db.session.flush()
    ctx.row_ids.setdefault('player_transaction_sync_windows', []).append(row.id)
    return row


def _evidence(
    ctx: _ScenarioContext,
    *,
    rule_id: str,
    evidence_type: str,
    subject_type: str,
    subject_id: int | str,
    source_row,
    state: str = EvidenceObject.COMPLETENESS_COMPLETE,
    reason_codes: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
    rendered_claim: str | None = None,
    typed: dict | None = None,
) -> EvidenceObject:
    key = ctx.next(f'evidence:{rule_id}')
    table, source_pk, source_family = _source_identity(source_row)
    evidence = EvidenceObject(
        evidence_key=f'qa:{key}',
        evidence_type=evidence_type,
        subject_type=subject_type,
        subject_id=str(subject_id),
        subject_key=f'{subject_type}:{subject_id}:{ctx.product_date.isoformat()}',
        product_date=ctx.product_date,
        claim_template_id=f'{rule_id}:qa',
        rendered_claim=rendered_claim or f'{rule_id} synthetic rendered claim.',
        rule_id=rule_id,
        rule_version=1,
        rule_definition_hash='qa-fixture',
        typed_cited_inputs=[typed or {}],
        computation_trace=typed or {},
        completeness_state=state,
        reason_codes=list(reason_codes),
        limitations=list(limitations),
        posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
        source='qa_scenario',
        sync_run_id=ctx.sync_run.id,
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
        recompute_reason_codes=[],
    )
    evidence.citations = [
        EvidenceCitation(
            source_family=source_family,
            source_table=table,
            source_pk=source_pk,
            source_field_names=sorted((typed or {'product_date': ctx.product_date.isoformat()}).keys()),
            citation_role='supporting_input',
            cited_values=typed or {'product_date': ctx.product_date.isoformat()},
            provenance={'source': 'qa_scenario', 'sync_run_id': ctx.sync_run.id},
        )
    ]
    db.session.add(evidence)
    db.session.flush()
    ctx.evidence_object_ids.append(evidence.id)
    return evidence


def _source_identity(row) -> tuple[str, str, str]:
    if isinstance(row, GameLog):
        return 'game_logs', str(row.id), 'game_logs'
    if isinstance(row, RosterStatusSnapshot):
        return 'roster_status_snapshots', str(row.id), 'roster_status_snapshots'
    if isinstance(row, PlayerTransaction):
        return 'player_transactions', str(row.id), 'player_transactions'
    if isinstance(row, PlayerTransactionSyncWindow):
        return 'player_transaction_sync_windows', str(row.id), 'player_transaction_sync_windows'
    if isinstance(row, GamePlayByPlayEvent):
        return 'game_play_by_play_events', str(row.id), 'final_play_by_play'
    if isinstance(row, PlayByPlayProcessedGame):
        return 'play_by_play_processed_games', str(row.id), 'final_play_by_play'
    return 'slate_coverage', f'qa:{id(row)}', 'slate_coverage'


def _build_reliever_read(
    ctx: _ScenarioContext,
    pitcher: Pitcher,
    *,
    game_log: GameLog,
    roster_snapshot: RosterStatusSnapshot,
    pbp_event: GamePlayByPlayEvent,
    component_states: dict[str, str] | None = None,
    component_reasons: dict[str, tuple[str, ...]] | None = None,
    recent_limitations: tuple[str, ...] = (BASE_STATE_LIMITATION, HBP_ROE_LIMITATION),
    roster_limitations: tuple[str, ...] = (),
    roster_source_row=None,
    recent_evidence: tuple[EvidenceObject, ...] | None = None,
    rest_typed: dict | None = None,
) -> ComposedRead:
    register_reliever_daily_read()
    component_states = component_states or {}
    component_reasons = component_reasons or {}
    workload = _evidence(
        ctx,
        rule_id='workload_window_appearances',
        evidence_type='workload_recovery_fact',
        subject_type='pitcher',
        subject_id=pitcher.id,
        source_row=game_log,
        state=component_states.get('workload_component', EvidenceObject.COMPLETENESS_COMPLETE),
        reason_codes=component_reasons.get('workload_component', ()),
    )
    rest = _evidence(
        ctx,
        rule_id='workload_days_of_rest',
        evidence_type='workload_recovery_fact',
        subject_type='pitcher',
        subject_id=pitcher.id,
        source_row=game_log,
        state=component_states.get('rest_component', EvidenceObject.COMPLETENESS_COMPLETE),
        reason_codes=component_reasons.get('rest_component', ()),
        typed=rest_typed or {'days_rest': 0, 'last_final_appearance': ctx.product_date.isoformat()},
    )
    if recent_evidence is None:
        recent_evidence = (
            _evidence(
                ctx,
                rule_id='appearance_entry_context',
                evidence_type='appearance_context_fact',
                subject_type='pitcher',
                subject_id=pitcher.id,
                source_row=pbp_event,
                state=component_states.get('recent_outing_component', EvidenceObject.COMPLETENESS_COMPLETE),
                reason_codes=component_reasons.get('recent_outing_component', ()),
                limitations=recent_limitations,
            ),
        )
    roster_state = component_states.get('roster_il_context', EvidenceObject.COMPLETENESS_COMPLETE)
    roster = _evidence(
        ctx,
        rule_id='pitcher_roster_membership_context',
        evidence_type='pitcher_roster_membership_context',
        subject_type='pitcher',
        subject_id=pitcher.id,
        source_row=roster_source_row or roster_snapshot,
        state=roster_state,
        reason_codes=component_reasons.get('roster_il_context', ()),
        limitations=roster_limitations,
        typed={'roster_membership_state': 'active' if roster_state == EvidenceObject.COMPLETENESS_COMPLETE else 'unknown'},
    )
    read = build_composed_read(
        read_type=RELIEVER_READ_TYPE,
        read_version=RELIEVER_READ_VERSION,
        subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
        subject_id=pitcher.id,
        subject_key=f'qa:{ctx.name}:pitcher:{pitcher.id}',
        product_date=ctx.product_date,
        component_inputs={
            'workload_component': ComponentInput(
                component_state=component_states.get('workload_component', ComposedRead.COMPLETENESS_COMPLETE),
                evidence_objects=(workload,),
                reason_codes=component_reasons.get('workload_component', ()),
            ),
            'rest_component': ComponentInput(
                component_state=component_states.get('rest_component', ComposedRead.COMPLETENESS_COMPLETE),
                evidence_objects=(rest,),
                reason_codes=component_reasons.get('rest_component', ()),
            ),
            'recent_outing_component': ComponentInput(
                component_state=component_states.get('recent_outing_component', ComposedRead.COMPLETENESS_COMPLETE),
                evidence_objects=tuple(recent_evidence),
                reason_codes=component_reasons.get('recent_outing_component', ()),
                limitations=recent_limitations,
            ),
            'roster_il_context': ComponentInput(
                component_state=roster_state,
                evidence_objects=(roster,),
                reason_codes=component_reasons.get('roster_il_context', ()),
                limitations=roster_limitations,
            ),
            'data_completeness_component': ComponentInput(
                component_state=ComposedRead.COMPLETENESS_COMPLETE,
                limitations=(
                    'component states are recorded mechanically from required components',
                ),
            ),
        },
        source='qa_scenario',
        sync_run_id=ctx.sync_run.id,
    )
    ctx.composed_read_ids.append(read.id)
    return read


def _build_team_read(
    ctx: _ScenarioContext,
    *,
    team_id: int,
    roster_snapshot: RosterStatusSnapshot,
    source_row=None,
    calendar=False,
    contributor_state=ComposedRead.COMPLETENESS_COMPLETE,
    contributor_reason_codes: tuple[str, ...] = (),
    contributor_limitations: tuple[str, ...] = (),
    contributor_evidence: tuple[EvidenceObject, ...] | None = None,
    include_contributor_evidence=True,
    exposure_state=ComposedRead.COMPLETENESS_COMPLETE,
    exposure_reason_codes: tuple[str, ...] = (),
    exposure_limitations: tuple[str, ...] = (),
    roster_state=ComposedRead.COMPLETENESS_COMPLETE,
    roster_reason_codes: tuple[str, ...] = (),
    roster_limitations: tuple[str, ...] = (),
    roster_source_row=None,
    calendar_reason_codes: tuple[str, ...] = (),
    calendar_limitations: tuple[str, ...] = (),
) -> ComposedRead:
    register_team_daily_read()
    source_row = source_row or roster_snapshot
    if contributor_evidence is None and include_contributor_evidence:
        contributor_evidence = (
            _evidence(
                ctx,
                rule_id='team_relief_contributor_basis',
                evidence_type='team_relief_contributor_basis',
                subject_type='team',
                subject_id=team_id,
                source_row=source_row,
                state=contributor_state,
                reason_codes=contributor_reason_codes,
                limitations=(BASIS_DISCLAIMER,) + tuple(contributor_limitations),
                typed={'relief_contributor_count': 3},
            ),
        )
    contributor_input = ComponentInput(
        component_state=contributor_state,
        evidence_objects=tuple(contributor_evidence or ()),
        reason_codes=contributor_reason_codes,
        limitations=(BASIS_DISCLAIMER,) + tuple(contributor_limitations),
    )
    exposure = _evidence(
        ctx,
        rule_id='team_reliever_appearances_window',
        evidence_type='team_reliever_appearances_window',
        subject_type='team',
        subject_id=team_id,
        source_row=source_row,
        state=exposure_state,
        reason_codes=exposure_reason_codes,
        limitations=exposure_limitations,
        typed={'appearance_count': 0},
    )
    roster = _evidence(
        ctx,
        rule_id='team_active_pitcher_census',
        evidence_type='team_active_pitcher_census',
        subject_type='team',
        subject_id=team_id,
        source_row=roster_source_row or roster_snapshot,
        state=roster_state,
        reason_codes=roster_reason_codes,
        limitations=(PITCHER_SCOPED_SNAPSHOT_LIMITATION,) + tuple(roster_limitations),
        typed={'active_pitcher_count': 12},
    )
    inputs = {
        'contributor_composition_component': contributor_input,
        'exposure_component': ComponentInput(
            component_state=exposure_state,
            evidence_objects=(exposure,),
            reason_codes=exposure_reason_codes,
            limitations=exposure_limitations,
        ),
        'roster_churn_component': ComponentInput(
            component_state=roster_state,
            evidence_objects=(roster,),
            reason_codes=roster_reason_codes,
            limitations=(PITCHER_SCOPED_SNAPSHOT_LIMITATION,) + tuple(roster_limitations),
        ),
        'slate_data_completeness_component': ComponentInput(
            component_state=ComposedRead.COMPLETENESS_COMPLETE,
            limitations=(
                'component states are recorded mechanically from required components',
            ),
        ),
    }
    if calendar:
        calendar_evidence = _evidence(
            ctx,
            rule_id='team_off_day_tomorrow',
            evidence_type='team_off_day_tomorrow',
            subject_type='team',
            subject_id=team_id,
            source_row=source_row,
            state=ComposedRead.COMPLETENESS_COMPLETE,
            reason_codes=calendar_reason_codes,
            limitations=calendar_limitations,
        )
        inputs['calendar_component'] = ComponentInput(
            component_state=ComposedRead.COMPLETENESS_COMPLETE,
            evidence_objects=(calendar_evidence,),
            reason_codes=calendar_reason_codes,
            limitations=calendar_limitations,
        )
    read = build_composed_read(
        read_type=TEAM_READ_TYPE,
        read_version=TEAM_READ_VERSION,
        subject_type=ComposedRead.SUBJECT_TEAM_DAY,
        subject_id=team_id,
        subject_key=f'qa:{ctx.name}:team:{team_id}',
        product_date=ctx.product_date,
        component_inputs=inputs,
        source='qa_scenario',
        sync_run_id=ctx.sync_run.id,
    )
    ctx.composed_read_ids.append(read.id)
    return read


def _dashboard(ctx: _ScenarioContext, payload: dict) -> DashboardSnapshot:
    row = DashboardSnapshot(
        snapshot_type='bullpen_dashboard',
        sync_run_id=ctx.sync_run.id,
        status='ready',
        is_published=True,
        published_at=datetime(2026, 7, 5, 8, 0),
        payload={'capability': 'bullpen_dashboard', **payload},
        payload_version=1,
        data_through=ctx.product_date,
        availability_reference_date=ctx.product_date,
        snapshot_generated_at=datetime(2026, 7, 5, 8, 0),
        source='qa_scenario',
    )
    db.session.add(row)
    db.session.flush()
    ctx.row_ids.setdefault('dashboard_snapshots', []).append(row.id)
    return row


def _capture_audit_rows(ctx: _ScenarioContext) -> None:
    runs = LegacyReadAuditRun.query.filter_by(product_date=ctx.product_date).all()
    divergences = LegacyReadDivergence.query.filter_by(product_date=ctx.product_date).all()
    ctx.audit_run_ids[:] = [row.id for row in runs]
    ctx.divergence_ids[:] = [row.id for row in divergences]


def _handle(ctx: _ScenarioContext, expected_state_map: dict) -> ScenarioHandle:
    db.session.flush()
    return ScenarioHandle(
        name=ctx.name,
        product_date=ctx.product_date,
        sync_run_id=ctx.sync_run.id,
        pitcher_ids=dict(ctx.pitcher_ids),
        team_ids=dict(ctx.team_ids),
        evidence_object_ids=tuple(ctx.evidence_object_ids),
        composed_read_ids=tuple(ctx.composed_read_ids),
        audit_run_ids=tuple(ctx.audit_run_ids),
        divergence_ids=tuple(ctx.divergence_ids),
        row_ids={key: tuple(value) for key, value in ctx.row_ids.items()},
        expected_state_map=expected_state_map,
    )


SCENARIO_BUILDERS: dict[str, Callable[[], ScenarioHandle]] = {
    name: globals()[name]
    for name in SCENARIO_NAMES
}
